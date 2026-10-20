"""
A Comfy Router video model proposed as a target (docs/PLAN.md, "Router models
as data"): its published schema (GET /v2/models/<provider>/<model>/openapi.json,
the one Router validates requests against) read, and the target.json that
drives it through targets/generic/router_video.py proposed -- which of its
fields takes the prompt, the length, the size, the ratio, the seed, the sound,
the references and the frames, with the limits the schema states -- for a
person to look over before it's saved as a show's own (draft) target.

The proposal is a reading of names and types, not a promise: what it found
is listed (`mapped`), what the model requires that it didn't place
(`unplaced`), and what it guessed (`warnings`). A first render settles it.

Stdlib only.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

API_BASE = "https://api.comfy.org"
SEED_MAX = 2147483647

# longest prompts a schema doesn't state, by model id prefix: Veo 3.1 Fast
# took 930- and 968-character prompts with reference pictures and failed
# their 1278-character sum with provider_error (2026-10-12)
PROMPT_LIMITS = {"veo/": 1000}


def _known_limit(model: str) -> int | None:
    return next((n for pre, n in PROMPT_LIMITS.items() if model.startswith(pre)), None)


class RouterInspectError(ValueError):
    pass


def fetch_schema(model: str, api_key: str, timeout: float = 30.0) -> dict:
    """The model's openapi.json from Router."""
    if not re.fullmatch(r"[\w.\-]+/[\w.\-]+", model or ""):
        raise RouterInspectError(f"{model!r} isn't a Router model id (provider/model)")
    from seriesmith.backends import HTTPFailure, http_json
    try:
        return http_json(f"{API_BASE}/v2/models/{model}/openapi.json",
                         headers={"X-API-Key": api_key}, timeout=timeout)
    except HTTPFailure as e:
        if e.status == 404:
            raise RouterInspectError(f"Router has no model {model}") from None
        raise RouterInspectError(f"Router answered {e.status} for {model}'s schema") from None
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise RouterInspectError(f"Router's schema for {model} couldn't be read: {e}") from None


# -- the catalog ---------------------------------------------------------------------

# what a Router model makes, from its id (the catalog doesn't say): "video" in
# it first (pika-2.5-image-to-video), then image words, then video families
_VIDEO = re.compile(r"video|seedance|kling|veo|gen4_turbo|aleph|\bwan|happyhorse|ltx|\bray-|minimax-h3|"
                    r"h3-max|[it]2v|r2v|pika|lip-sync|sync-3|starfish|switchx")
_IMAGE = re.compile(r"image|seedream|flux|banana|krea|recraft|ideogram|photon|bria|imagen|[ti]2i|kontext|"
                    r"fibo|erase|expand|fill|vto|uni-1|skin|patina")
_OTHER = re.compile(r"upscal|seedvr|flashvsr|audio|eleven|meshy|hunyuan-3d|rigging|remesh|animations")


def kind_of(model_id: str) -> str:
    """"video", "image" or "other" (language, audio, 3D, upscalers) for a
    Router model id: a guess from its name, for narrowing a list."""
    s = model_id.lower()
    if _OTHER.search(s):
        return "other"
    if "video" in s:
        return "video"
    if _IMAGE.search(s):
        return "image"
    if _VIDEO.search(s):
        return "video"
    return "other"


_CATALOG: dict = {}                   # api key -> (monotonic time, [model ids])
CATALOG_TTL = 3600.0


def fetch_catalog(api_key: str, timeout: float = 30.0) -> list[str]:
    """Every model id Router serves (GET /v2/models, paged), kept an hour."""
    import time
    import urllib.parse
    hit = _CATALOG.get(api_key)
    if hit and time.monotonic() - hit[0] < CATALOG_TTL:
        return list(hit[1])
    from seriesmith.backends import HTTPFailure, http_json
    ids: list[str] = []
    cursor = None
    for _ in range(50):
        q = "?limit=100" + (f"&cursor={urllib.parse.quote(cursor)}" if cursor else "")
        try:
            page = http_json(f"{API_BASE}/v2/models{q}", headers={"X-API-Key": api_key},
                             timeout=timeout)
        except HTTPFailure as e:
            raise RouterInspectError(f"Router answered {e.status} for its model list") from None
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise RouterInspectError(f"Router's model list couldn't be read: {e}") from None
        ids += [str(m.get("id")) for m in page.get("data") or [] if m.get("id")]
        cursor = page.get("next_cursor")
        if not page.get("has_more") or not cursor:
            break
    _CATALOG.clear()
    _CATALOG[api_key] = (time.monotonic(), ids)
    return list(ids)


# -- the schema --------------------------------------------------------------------

def _resolve(doc: dict, s):
    seen = 0
    while isinstance(s, dict) and "$ref" in s and seen < 20:
        s = doc.get("components", {}).get("schemas", {}).get(s["$ref"].split("/")[-1], {})
        seen += 1
    if isinstance(s, dict) and "anyOf" in s and "type" not in s:
        typed = [x for x in (_resolve(doc, y) for y in s["anyOf"]) if isinstance(x, dict) and x.get("type")]
        if typed:
            merged = dict(typed[0])
            merged.update({k: v for k, v in s.items() if k != "anyOf"})
            return merged
    return s if isinstance(s, dict) else {}


def request_schema(doc: dict) -> dict:
    for ops in (doc.get("paths") or {}).values():
        post = (ops or {}).get("post") or {}
        s = (((post.get("requestBody") or {}).get("content") or {}).get("application/json") or {}).get("schema")
        if s:
            return _resolve(doc, s)
    raise RouterInspectError("the schema has no request body to read")


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def fields(doc: dict, s: dict, prefix: str = "", depth: int = 0):
    """(path, schema) of every field, objects walked into, an array of objects
    walked into as its first item (".0.") -- except a list of items, which is
    kept whole (a content or media list)."""
    for k, v in ((s.get("properties") or {}).items()):
        v = _resolve(doc, v)
        path = f"{prefix}{k}"
        yield path, v
        if depth >= 2:
            continue
        if v.get("type") == "object":
            yield from fields(doc, v, path + ".", depth + 1)
        elif v.get("type") == "array":
            item = _resolve(doc, v.get("items") or {})
            if item.get("type") == "object" and not _is_media_list(doc, item):
                if _norm(k) in ("instances",):
                    yield from fields(doc, item, path + ".0.", depth + 1)


def _is_media_list(doc: dict, item: dict) -> bool:
    props = {_norm(k) for k in (item.get("properties") or {})}
    return "type" in props and bool(props & {"text", "imageurl", "url", "role"})


def _text(v: dict) -> str:
    return json.dumps(v).lower()


# -- the proposal ------------------------------------------------------------------

NAMES = {
    "prompt": ["prompt", "prompttext", "text"],
    "negative": ["negativeprompt", "negative"],
    "duration": ["duration", "durationseconds", "seconds", "length", "videoduration"],
    "resolution": ["resolution", "quality", "videoresolution"],
    "ratio": ["aspectratio", "ratio"],
    "seed": ["seed"],
    "audio": ["generateaudio", "audio", "sound", "withaudio", "enableaudio"],
    "first": ["firstframe", "firstframeimage", "firstframeurl", "image", "imageurl", "imgurl",
              "startimage", "imagestart", "startframe", "startimageurl", "promptimage"],
    "last": ["lastframe", "lastframeimage", "lastframeurl", "endimage", "imageend", "tailimage",
             "endframe", "endimageurl", "imagetail"],
    "references": ["referenceimages", "referenceimage", "imageurls", "images", "referenceimageurls",
                   "refimages"],
}


def _picture_item(doc: dict, v: dict):
    """How one picture goes in a field or list item of schema `v`: "$url", or
    {"url": "$url"}, {"gcsUri": "$url", "mimeType": "image/png"}, ..."""
    v = _resolve(doc, v)
    if v.get("type") != "object":
        return "$url"
    props = {k: _resolve(doc, x) for k, x in (v.get("properties") or {}).items()}
    for k in props:
        if _norm(k) in ("url", "imageurl", "uri"):
            return {k: "$url"}
    mime = next((m for m in props if _norm(m) == "mimetype"), None)
    for k in props:
        # the picture's own bytes where offered (Veo): its gcsUri takes only
        # Google Cloud Storage, and a Comfy asset link came back invalid_input
        # (2026-10-12); the file goes in base64 (File.via "base64")
        if _norm(k) == "bytesbase64encoded":
            return {k: "$url", **({mime: "$mime"} if mime else {})}
    for k in props:
        if _norm(k) == "gcsuri":
            return {k: "$url", **({mime: "$mime"} if mime else {})}
    for k, x in props.items():
        if _norm(k) == "image":
            inner = _picture_item(doc, x)
            rest = {r: "asset" for r, y in props.items()
                    if _norm(r) == "referencetype" and "asset" in (y.get("enum") or [])}
            return {k: inner, **rest}
    return "$url"


def _sizes(values: list[str]) -> dict:
    """final and proxy (width, height) from a model's resolutions."""
    from seriesmith.targets.generic.router_video import size_of

    def dims(v):
        w, h = size_of(v)
        return (w or (round(h * 16 / 9 / 2) * 2), h) if h else None
    landscape = [d for d in (dims(v) for v in values) if d and d[0] >= d[1]]
    if not landscape:
        return {"final": (1280, 720), "proxy": (854, 480)}
    landscape.sort(key=lambda d: d[1])
    final = min(landscape, key=lambda d: abs(d[1] - 720))
    proxy = landscape[0]
    return {"final": final, "proxy": proxy}


def propose(model: str, doc: dict, base: dict | None = None) -> dict:
    """{"proposal": target.json, "mapped": {input: where}, "unplaced": [required
    fields not placed], "warnings": [...]} for Router model `model` from its
    schema `doc`. `base`: a target.json whose recipe and refs a new one starts
    from (Seedance's)."""
    body = request_schema(doc)
    required = set(body.get("required") or [])
    inputs: dict = {}
    mapped: dict = {}
    warnings: list[str] = []
    args: dict = {}
    all_fields = list(fields(doc, body))

    # a list of typed items: a content list (text and pictures with roles) or a
    # media list (pictures by type)
    for path, v in all_fields:
        if v.get("type") != "array":
            continue
        item = _resolve(doc, v.get("items") or {})
        if item.get("type") != "object" or not _is_media_list(doc, item):
            continue
        props = {_norm(k): k for k in (item.get("properties") or {})}
        roles_text = _text(item)
        if "text" in props and "prompt" not in inputs:
            inputs["prompt"] = {"list": path, "item": {props["type"]: "text", props["text"]: "$prompt"}}
        if "imageurl" in props:                                  # content: {type, image_url{url}, role}
            role_key = props.get("role")
            url_obj = _picture_item(doc, (item.get("properties") or {})[props["imageurl"]])
            for want, role in (("references", "reference_image"), ("first", "first_frame"),
                               ("last", "last_frame")):
                if role in roles_text or (want == "last" and "end_frame" in roles_text):
                    r = role if role in roles_text else "end_frame"
                    tpl = {props["type"]: "image_url", props["imageurl"]: url_obj}
                    if role_key:
                        tpl[role_key] = r
                    else:
                        tpl[props["type"]] = r
                    inputs.setdefault(want, {"list": path, "item": tpl})
            # Kling's image_list: an item without a type is a reference picture
            # (`type` only marks a first or last frame)
            if (not role_key and "type" in props and props["type"] not in (item.get("required") or [])
                    and "reference" in str(v.get("description", "")).lower()):
                inputs.setdefault("references", {"list": path, "item": {props["imageurl"]: url_obj}})
        elif "url" in props:                                      # media: {type, url}
            for want, role in (("references", "reference_image"), ("first", "first_frame"),
                               ("last", "last_frame")):
                if role in roles_text:
                    inputs.setdefault(want, {"list": path, "item": {props["type"]: role, props["url"]: "$url"}})
        for k in ("prompt", "references", "first", "last"):
            if k in inputs and k not in mapped:
                mapped[k] = f"{path}[] ({k})"

    # the fields, by name
    for path, v in all_fields:
        leaf = _norm(path.split(".")[-1])
        if any(path == m.get("list") or path.startswith(str(m.get("list")) + ".")
               for m in inputs.values() if isinstance(m, dict)):
            continue
        t = v.get("type")
        enum = v.get("enum")
        if leaf in NAMES["prompt"] and t == "string" and "prompt" not in inputs:
            # a longest prompt (Runway's 1000): the prose is cut to it, by sentence
            most = v["maxLength"] if isinstance(v.get("maxLength"), int) else None
            most = min(x for x in (most, _known_limit(model)) if x) if most or _known_limit(model) else None
            inputs["prompt"] = {"field": path, "max_chars": most} if most else path
        elif leaf in NAMES["negative"] and t == "string" and "negative" not in inputs:
            inputs["negative"] = path
        elif leaf in NAMES["duration"] and "duration" not in inputs and t in ("integer", "number", "string"):
            d = {"name": path}
            if enum:
                d["values"] = [int(float(x)) for x in enum if str(x).lstrip("-").replace(".", "").isdigit()
                               and float(x) > 0]
                if t == "string":
                    d["as"] = "str"
            else:
                lo, hi = v.get("minimum"), v.get("maximum")
                d["min"] = max(1, int(lo)) if isinstance(lo, (int, float)) and lo > 0 else 1
                if isinstance(hi, (int, float)):
                    d["max"] = int(hi)
                if not isinstance(hi, (int, float)):
                    warnings.append(f"{path}: the schema gives no longest length; check its description")
            inputs["duration"] = d
        elif leaf in NAMES["resolution"] and enum and "resolution" not in inputs:
            vals = [x for x in enum if not str(x).lower() in ("auto",)]
            # one spelling of each ("768P" and "768p"): the first
            seen, uniq = set(), []
            for x in vals:
                if str(x).lower() not in seen:
                    seen.add(str(x).lower())
                    uniq.append(x)
            inputs["resolution"] = {"name": path, "values": uniq}
        elif leaf == "mode" and enum and {"std", "pro"} <= set(enum) and "resolution" not in inputs:
            # Kling: std is 720p, pro 1080p (and the default: a proxy must say std)
            inputs["resolution"] = {"name": path, "values": {"720": "std", "1080": "pro"}}
        elif leaf == "size" and t == "string" and "resolution" not in inputs:
            warnings.append(f"{path}: a size as width*height with no list of values: left to the model")
        elif leaf in NAMES["ratio"] and "ratio" not in inputs and (enum or t == "string"):
            vals = list(enum) if enum else ["16:9", "9:16", "1:1"]
            if not enum:
                warnings.append(f"{path}: no ratios listed; 16:9, 9:16 and 1:1 assumed")
            d = {"name": path, "values": [x for x in vals if ":" in str(x)]}
            if "adaptive" in vals:
                d["with_frames"] = "adaptive"
            elif path in required:
                d["with_frames"] = "keep"            # Runway: asked for even with a frame
            inputs["ratio"] = d
        elif leaf in NAMES["seed"] and t in ("integer", "number") and "seed" not in inputs:
            # never past 2^31-1, whatever the schema says: BytePlus's said 2^32-1
            # and refused anything past 2^31-1 (2026-10-11)
            hi = v.get("maximum")
            inputs["seed"] = {"name": path, "max": min(int(hi), SEED_MAX)
                              if isinstance(hi, (int, float)) and hi > 0 else SEED_MAX}
        elif leaf in NAMES["audio"] and "audio" not in inputs:
            if t == "boolean":
                inputs["audio"] = {"name": path}
            elif enum and {"on", "off"} <= {str(x).lower() for x in enum}:
                inputs["audio"] = {"name": path, "on": "on", "off": "off"}
        elif leaf in NAMES["references"] and t == "array" and "references" not in inputs:
            item = _resolve(doc, v.get("items") or {})
            d = {"list": path}
            tpl = _picture_item(doc, item)
            if tpl != "$url":
                d["item"] = tpl
            if isinstance(v.get("maxItems"), int):
                d["max"] = v["maxItems"]
            inputs["references"] = d
        elif leaf in NAMES["first"] and "first" not in inputs and t in ("string", "object", None):
            tpl = _picture_item(doc, v)
            inputs["first"] = {"field": path, **({"item": tpl} if tpl != "$url" else {})}
        elif leaf in NAMES["last"] and "last" not in inputs and t in ("string", "object"):
            tpl = _picture_item(doc, v)
            inputs["last"] = {"field": path, **({"item": tpl} if tpl != "$url" else {})}
        elif leaf == "watermark" and t == "boolean":
            args[path] = False
        elif leaf in ("outputformat",) and enum and "mp4" in enum:
            args[path] = "mp4"
        elif leaf == "samplecount" and t == "integer":
            args[path] = 1
        elif leaf == "fps" and enum and 24 in enum:
            args[path] = 24                                  # the episode's rate

    # seriesmith draws from refs and keyframes: a model that takes no picture
    # (text to video) can't hold a character, and isn't offered
    if not any(k in inputs for k in ("references", "first", "last")):
        raise RouterInspectError(f"{model} takes no pictures (text to video only): seriesmith renders "
                                 f"from your refs and keyframes, so it can't be used for shots")
    # a prompt that names its pictures (Kling: <<<image_1>>>) says which is which
    ppath = inputs.get("prompt")
    ppath = _name(ppath) if isinstance(ppath, dict) else ppath
    pdesc = next((str(v.get("description", "")) for p, v in all_fields if p == ppath), "")
    if "references" in inputs and "<<<image_1>>>" in pdesc:
        inputs["references"]["mention"] = "<<<image_{n}>>>"

    # BytePlus's models take a person's picture only through the Seedance
    # virtual library (asset://): a plain URL is refused (2026-10-11)
    if model.startswith("byteplus/"):
        inputs["via"] = "seedance"
    elif '"$url"' in json.dumps(inputs) and "bytesBase64Encoded" in json.dumps(inputs):
        inputs["via"] = "base64"
    for k, where in inputs.items():
        if k == "via":
            continue
        mapped.setdefault(k, where if isinstance(where, str) else
                          (where.get("name") or where.get("field") or f"{where.get('list')}[]"))
    if "prompt" not in inputs:
        warnings.append("no field for the prompt was found: the model can't be told what to draw")
    if "first" in inputs and "references" in inputs:
        warnings.append("it takes frames and references: a shot with a first frame sends its frames")
    placed = {str(m.get("list") or _name(m)) if isinstance(m, dict) else m
              for k, m in inputs.items() if k != "via"}
    placed |= set(args)
    unplaced = sorted(f for f in required if not any(p == f or p.startswith(f + ".") for p in placed))

    # nested fixed arguments (sampleCount under parameters) go in by path
    arguments: dict = {}
    from seriesmith.targets.generic.router_video import put
    for path, value in args.items():
        put(arguments, path, value)

    res = (inputs.get("resolution") or {}).get("values") or []
    sizes = _sizes([f"{h}p" for h in res] if isinstance(res, dict) else res)
    d = inputs.get("duration") or {}
    lo = min(d["values"]) if d.get("values") else d.get("min", 4)
    hi = max(d["values"]) if d.get("values") else d.get("max", 10)
    tid = re.sub(r"[^a-z0-9]+", "_", model.split("/", 1)[1].lower()).strip("_")
    if not tid[:1].isalpha():
        tid = "m_" + tid
    base = json.loads(json.dumps(base or {}))
    recipe = base.get("recipe") or {"policies": ["generate"], "prompt": "prose"}
    recipe["keyframes"] = [e for e in ("first", "last") if e in inputs]
    if _name(inputs.get("first") or {}) in required:
        # an image-to-video model (Runway): a shot needs its first keyframe,
        # asked for like any missing picture (capabilities.requires_first)
        recipe["keyframe_required"] = {"first": f"{model} starts every shot from its first frame: "
                                                f"generate one, import one, or give the shot "
                                                f"`continuous: first`"}
    if "references" not in inputs:
        recipe.pop("reference_image", None)
    proposal = {
        "id": tid,
        "kind": "video",
        "label": f"{model.split('/', 1)[1]} (hosted, Comfy Router)",
        "short": model.split("/", 1)[1].split("-")[0].capitalize(),
        "code": "builtin:router_video",
        "draft": True,
        "capabilities": {
            "backends": ["router"],
            "seed": "provider",
            "max_subjects": (inputs.get("references") or {}).get("max", 4),
        },
        "template": {"fps": 24, "frames": {"step": 24, "base": max(1, int(lo)) * 24,
                                           "max": max(int(lo), int(hi)) * 24},
                     "size_multiple": 2, "size_fit": "snap"},
        "recipe": recipe,
        "router": {"model": model, "arguments": arguments, "inputs": inputs},
        "presets": {p: {"model": model, "lora": None, "steps": 0,
                        "width": sizes[p][0], "height": sizes[p][1]} for p in ("final", "proxy")},
    }
    if "refs" in base:
        proposal["refs"] = base["refs"]
    # a model that makes no sound (Runway: no sound field, no word of audio
    # anywhere): the silent prose, no quoted lines or soundscape -- Runway
    # failed every prompt carrying them with provider_error (2026-10-12)
    if "audio" not in inputs and not re.search(r"audio|\bsound", _text(doc)):
        proposal["capabilities"]["audio"] = "none"
        recipe["policies"] = ["silent"]
        recipe["policy_fallback"] = {"to": "silent", "why": f"{model} makes no sound: the take is "
                                                            f"mute, and the edit lays the sound under it"}
    return {"proposal": proposal, "mapped": mapped, "unplaced": unplaced, "warnings": warnings,
            "shared": shared_fields(inputs, all_fields)}


# a description written for several models at once: "- wan2.7-r2v: [2, 10]",
# "Seedance 2.0, 2.0 fast & 2.0 mini: [4,15]", "Veo 3/3.1: 4, 6, or 8"
PER_MODEL = re.compile(r"(?m)(?:^\s*-\s*[^\n:]{2,90}:|\b[A-Z][A-Za-z]+ \d[^\n:]{0,60}:)")
SECTION_OF = {"duration": "length", "resolution": "size", "prompt": "prompt",
              "references": "pictures", "first": "pictures", "last": "pictures",
              # image models'
              "size": "size", "ratio": "size", "images": "pictures"}


def shared_fields(inputs: dict, all_fields: list) -> dict[str, list[dict]]:
    """{limits section: [{"input", "field", "text"}]} for each placed input whose
    schema field is described for several models at once: the limit for this
    one is in that prose, not in the schema, and is what the proposal can't
    know (Seedance 2.0's [4,15], Wan 2.7's 720P/1080P, Veo's 4/6/8 were all
    there). The editor shows them beside the limits to check."""
    desc = {p: str(v.get("description") or "") for p, v in all_fields}
    out: dict[str, list[dict]] = {}
    for key, section in SECTION_OF.items():
        m = inputs.get(key)
        if m is None:
            continue
        path = m if isinstance(m, str) else (m.get("list") or _name(m))
        text = desc.get(path, "")
        if len(PER_MODEL.findall(text)) >= 2:
            out.setdefault(section, []).append({"input": key, "field": path, "text": text})
    return out


def _name(m: dict) -> str:
    return m.get("name") or m.get("field") or ""


# -- image models ---------------------------------------------------------------------
#
# An image model proposed as a target driven by targets/generic/router_image.py.
# Image requests vary more than video's -- a chat message's parts (Gemini,
# Qwen), numbered input fields (Flux), one field taking a picture or a list
# (GPT Image, Seedream), a ratio and a 1K/2K size, a WxH string -- so this is a
# first reading to look over (the editor's Limits, the target.json), and the
# models seriesmith ships are mapped by hand (tools/make_router_targets.py).

GEMINI_RATIOS = ["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"]
_PICTURE_NAMES = ("image", "images", "imageurls", "imagelist", "inputimage", "inputimages",
                  "referenceimages", "imageinput", "imageurl")


def propose_image(model: str, doc: dict) -> dict:
    """{"proposal": an image target.json, "mapped", "unplaced", "warnings",
    "shared"} for Router image model `model` from its schema `doc`."""
    body = request_schema(doc)
    required = set(body.get("required") or [])
    all_fields = list(fields(doc, body))
    by_path = dict(all_fields)
    inputs: dict = {}
    args: dict = {}
    warnings: list[str] = []

    # a chat message: an array whose items hold a list of parts with text
    for path, v in all_fields:
        if v.get("type") != "array" or "." in path and path.count(".") > 1:
            continue
        item = _resolve(doc, v.get("items") or {})
        props = item.get("properties") or {}
        parts_key = next((k for k in ("parts", "content") if k in props), None)
        if not parts_key:
            continue
        part = _resolve(doc, (_resolve(doc, props[parts_key]).get("items") or {}))
        pprops = {k: _resolve(doc, x) for k, x in (part.get("properties") or {}).items()}
        if "text" not in pprops:
            continue
        lst = f"{path}.0.{parts_key}"
        inputs["prompt"] = {"list": lst, "item": {"text": "$prompt"}}
        if "role" in props:
            put_path(args, f"{path}.0.role", "user")
        if "inlineData" in pprops:
            inputs["images"] = {"list": lst, "first": True, "max": 4,
                                "item": {"inlineData": {"mimeType": "$mime", "data": "$url"}}}
            inputs["via"] = "base64"
        elif "image" in pprops:
            inputs["images"] = {"list": lst, "item": {"image": "$url"}, "first": True,
                                "max": _max_from(pprops["image"], 3)}
        break

    numbered = sorted((p for p, _ in all_fields if re.fullmatch(r"input_image(_\d+)?", p)),
                      key=lambda p: int(p.rsplit("_", 1)[1]) if p[-1].isdigit() else 1)
    for path, v in all_fields:
        leaf = _norm(path.split(".")[-1])
        t = v.get("type")
        enum = v.get("enum")
        desc = str(v.get("description") or "")
        if any(path == m.get("list") or path.startswith(str(m.get("list")) + ".")
               for m in inputs.values() if isinstance(m, dict)):
            continue
        if "not supported" in desc.lower()[:80]:
            continue                                     # "Size of the image (not supported)"
        if leaf in ("prompt", "textprompt") and t == "string" and "prompt" not in inputs:
            inputs["prompt"] = {"field": path, "max_chars": v["maxLength"]} \
                if isinstance(v.get("maxLength"), int) else path
        elif leaf in ("negativeprompt",) and t == "string" and "negative" not in inputs:
            inputs["negative"] = path
        elif leaf in _PICTURE_NAMES and "images" not in inputs:
            if numbered and path == numbered[0]:
                inputs["images"] = {"fields": numbered, "max": len(numbered)}
            elif t == "array":
                item = _resolve(doc, v.get("items") or {})
                tpl = _picture_item(doc, item)
                inputs["images"] = {"list": path, **({"item": tpl} if tpl != "$url" else {}),
                                    "max": int(v.get("maxItems") or 4)}
            elif not numbered:
                inputs["images"] = {"field": path, "max": _max_from(v, 4)}
        elif leaf in ("aspectratio", "ratio") and "ratio" not in inputs:
            vals = [x for x in (enum or []) if ":" in str(x)] or GEMINI_RATIOS
            if not enum:
                warnings.append(f"{path}: no ratios listed; the common ones assumed")
            inputs["ratio"] = {"name": path, "values": vals}
        elif leaf in ("resolution", "imagesize") and "resolution" not in inputs and t == "string":
            vals = [x for x in (enum or []) if re.fullmatch(r"\d+(\.\d+)?k", str(x).lower())]
            if not vals and re.search(r"WIDTHxHEIGHT|\b\d{3,4}\s*[x*]\s*\d{3,4}\b", desc):
                inputs["size"] = {"name": path, "format": "{w}x{h}", "multiple": 16}    # Ideogram's
                continue
            if not vals:
                vals = [f"{k}K" for k in dict.fromkeys(re.findall(r"\b(\d)K\b", desc))]
            if vals:
                inputs["resolution"] = {"name": path, "values": vals}
        elif leaf == "size" and t == "string" and "size" not in inputs:
            star = "*" in re.sub(r"\s", "", desc[:400]) and re.search(r"\d+\*\d+", desc)
            sizes = re.findall(r"\b(\d{3,4}x\d{3,4})\b", desc)
            free = re.search(r"total pixels|pixel area|width and height in pixels", desc, re.I)
            if sizes and not star and not free and len(desc) < 300:
                # a short list ("e.g., 1024x1024, 1536x1024, auto"): those, and each
                # landscape one's portrait twin
                vals = list(dict.fromkeys(sizes))
                for v in list(vals):
                    a, b = v.split("x")
                    if int(a) > int(b) and f"{b}x{a}" not in vals:
                        vals.append(f"{b}x{a}")
                inputs["size"] = {"name": path, "values": vals}
            else:
                inputs["size"] = {"name": path, "format": "{w}*{h}" if star else "{w}x{h}", "multiple": 16}
                # "a pixel area between 262144 (512*512) and 6553600 (2560*2560)"
                big = [int(x) for x in re.findall(r"\b\d{5,}\b", desc)[:2]]
                if len(big) == 2 and big[0] < big[1]:
                    inputs["size"].update(min_pixels=big[0], max_pixels=big[1])
        elif leaf in ("width", "height") and t == "integer":
            d = {"name": path, "multiple": 16}
            for k, src in (("min", "minimum"), ("max", "maximum")):
                if isinstance(v.get(src), (int, float)):
                    d[k] = int(v[src])
            inputs[leaf] = d
        elif leaf == "seed" and t in ("integer", "number") and "seed" not in inputs:
            hi = v.get("maximum")
            inputs["seed"] = {"name": path, "max": min(int(hi), SEED_MAX)
                              if isinstance(hi, (int, float)) and hi > 0 else SEED_MAX}
        elif leaf in ("n", "numimages", "numberofimages", "samplecount") and t == "integer":
            args[path] = 1
        elif leaf == "responseformat" and enum and "url" in enum:
            args[path] = "url"
        elif leaf == "watermark" and t == "boolean":
            args[path] = False
        elif leaf == "outputformat" and enum and "png" in enum:
            args[path] = "png"
        elif leaf == "responsemodalities":
            args[path] = ["IMAGE"]
        elif leaf == "sequentialimagegeneration" and enum and "disabled" in enum:
            args[path] = "disabled"
        elif leaf == "promptupsampling" and t == "boolean":
            args[path] = False

    if "width" in inputs and "height" not in inputs or "height" in inputs and "width" not in inputs:
        inputs.pop("width", None)
        inputs.pop("height", None)
    imgs = inputs.get("images")
    if imgs and "<<<image_1>>>" in str((by_path.get(_name(inputs["prompt"]) if isinstance(inputs.get("prompt"), dict)
                                                       else inputs.get("prompt")) or {}).get("description")):
        imgs["mention"] = "<<<image_{n}>>>"
    if model.startswith("byteplus/") and imgs:
        warnings.append("BytePlus may refuse a photoreal person's picture as a plain link (as Seedance "
                        "did): if so, set Limits -> pictures sent as -> the Seedance library")
    if "prompt" not in inputs:
        warnings.append("no field for the prompt was found: set router.inputs.prompt")
    if not any(k in inputs for k in ("ratio", "resolution", "size", "width")):
        warnings.append("no size field was found: the model's own default size")

    arguments: dict = {}
    from seriesmith.targets.generic.router_video import put
    for path, value in args.items():
        put(arguments, path, value)
    placed = {str(m.get("list") or _name(m)) if isinstance(m, dict) else m
              for k, m in inputs.items() if k != "via"}
    placed |= set(args) | {f for m in inputs.values() if isinstance(m, dict) for f in (m.get("fields") or [])}
    unplaced = sorted(f for f in required if not any(p == f or p.startswith(f + ".") for p in placed))
    tid = re.sub(r"[^a-z0-9]+", "_", model.split("/", 1)[1].lower()).strip("_")
    if not tid[:1].isalpha():
        tid = "m_" + tid
    proposal = {
        "id": tid, "kind": "image",
        "label": f"{model.split('/', 1)[1]} (hosted, Comfy Router)",
        "short": model.split("/", 1)[1].split("-")[0].capitalize(),
        "code": "builtin:router_image", "draft": True,
        "capabilities": {"backends": ["router"], "seed": "provider",
                         "mode": "edit" if imgs else "t2i",
                         "max_refs": int(imgs.get("max") or 1) if imgs else 0},
        "template": {"view_size": [1024, 1024], "plate_size": [1344, 768], "object_size": [1024, 1024]},
        "recipe": {"views": ["01_threequarter", "02_side", "03_back", "04_face"], "ref_word": "image"},
        "router": {"model": model, "arguments": arguments, "inputs": inputs},
        "presets": {"final": {"model": model, "lora": "", "steps": 0, "cfg": 1.0}},
    }
    mapped = {k: (m if isinstance(m, str) else m.get("list") or _name(m) or ", ".join(m.get("fields") or []))
              for k, m in inputs.items() if k != "via"}
    return {"proposal": proposal, "mapped": mapped, "unplaced": unplaced, "warnings": warnings,
            "shared": shared_fields(inputs, all_fields)}


def _max_from(v: dict, default: int) -> int:
    """How many pictures a field takes: its maxItems, or one of its oneOf's."""
    for x in [v] + list(v.get("oneOf") or []):
        if isinstance(x, dict) and isinstance(x.get("maxItems"), int):
            return int(x["maxItems"])
    return default


def put_path(args: dict, path: str, value) -> None:
    from seriesmith.targets.generic.router_video import put
    put(args, path, value)
