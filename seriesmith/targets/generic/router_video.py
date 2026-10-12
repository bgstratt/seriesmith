"""
A video model on Comfy Router, described by data: `"code":
"builtin:router_video"` in its target.json, and its `router` block saying how a
shot becomes that model's own arguments. Every Router model is called the same
way (comfy-sdk models.submit, by "provider/model" id); what differs is the
shape of its input, and that is what `router.inputs` maps. Each input names
where it goes -- a field (a dotted path: "prompt", "parameters.seed",
"instances.0.prompt") or a list it is appended to, with an item template
("$prompt" and "$url" are filled in):

    "router": {
      "model": "provider/model-id",
      "arguments": {...},                         # sent as they are
      "inputs": {
        "prompt": "prompt",                       # a field, or
                  # {"list": "content", "item": {"type": "text", "text": "$prompt"}}
        "negative": "negative_prompt",
        "duration": {"name": "duration", "min": 4, "max": 30},   # whole seconds,
                    # or "values": [5, 10] (the nearest), "as": "str" for "5"
        "resolution": {"name": "resolution", "values": ["480p", "720p", "1080p"]},
                    # names ("768P", "2K") or sizes ("1280x720", "1280*720"),
                    # or {"480": "480p", ...} by height
        "ratio": {"name": "aspect_ratio", "values": ["16:9", "9:16"], "with_frames": "omit"},
        "seed": {"name": "seed", "max": 2147483647},
        "audio": {"name": "generate_audio"},      # or "on": "on", "off": "off"
        "references": {"list": "image_urls", "max": 4},           # item default "$url";
                    # "mention": "<<<image_{n}>>>" names each in the prompt (Kling)
        "first": {"field": "image_url"},          # or a list and an item, e.g.
                  # {"list": "content", "item": {"type": "image_url",
                  #   "image_url": {"url": "$url"}, "role": "first_frame"}}
        "last": {"field": "last_frame_url"},
        "via": "seedance"                         # how pictures go in (File.via)
      },
      "draft": {"proxy": true, "resolution": "480p", "final_resolution": "1080p"},
      "provider": "fal",                            # another provider of the model
      "fallback": false                             # Router may not try another
    }

What a shot sends: its prose prompt (the shared prose compile, video_prose);
with a first keyframe on disk and an input for it, its frames (first, and
last when there is one), else its references -- the subjects' pictures, then
the plate, a character's 4-panel sheet cut to the one panel the shot wants
(no provider takes a 4:1 strip) -- its length, size and ratio snapped to what
the model takes, its seed folded into the model's range, and whether it
makes sound. `draft` (Seedance 2.5): a proxy take is a Draft, and a final
made from one (job.from_draft) sends that draft's task id alone. `provider`:
another provider serves the model (Router translates the model's own
arguments to its input), `fallback: false` stops Router trying another when
that one is down; both ride in the arguments under backends.router.ROUTING.

Stdlib only (a panel is cut by helpers/refsheet.py, run as a subprocess).
"""
from __future__ import annotations

import copy
import os
import re

from seriesmith.targets.generic import video_prose as G

compile_episode = G.compile_episode
compile_shot = G.compile_shot
required_refs = G.required_refs
ref_slots = G.ref_slots


def panel_file(sheet: str, panels: int, index: int) -> str:
    """Panel `index` of the `panels`-panel strip `sheet`, as its own picture:
    `_panels/<name>_p<index>_<sha1>.png` beside the sheet, cut once (a new
    sheet has a new sha1, so a new file). One whose size can't be read is
    sent as it is."""
    from seriesmith import refs as R
    from seriesmith import takes as T
    from seriesmith.targets.video.ltx2_ingredients import sheet as S
    d = os.path.join(os.path.dirname(sheet), "_panels")
    name = os.path.splitext(os.path.basename(sheet))[0]
    out = os.path.join(d, f"{name}_p{index}_{T.file_sha1(sheet)[:10]}.png")
    if os.path.isfile(out):
        return out
    w, h = R.image_size(sheet) or (0, 0)
    if not w or not h or w < panels:
        return sheet
    os.makedirs(d, exist_ok=True)
    S.compose({"width": w // panels, "height": h, "background": "white", "gap": 0,
               "panels": [{"path": sheet, "fit": "cover",
                           "crop": {"panels": panels, "index": index}}]}, out)
    return out


# -- snapping to what the model takes ------------------------------------------

def nearest_ratio(width: int, height: int, ratios: list[str]) -> str:
    """The ratio (e.g. "16:9") nearest the picture's shape ("adaptive" and
    the like are not shapes: left out)."""
    want = width / height
    shapes = [r for r in ratios if ":" in r]

    def off(r: str) -> float:
        a, b = (int(x) for x in r.split(":"))
        return abs(a / b - want)
    return min(shapes, key=off)


# named sizes, by their height
NAMED = {"2k": 1440, "4k": 2160, "8k": 4320, "uhd": 2160, "fhd": 1080, "hd": 720, "sd": 480}


def size_of(name: str) -> tuple[int | None, int]:
    """A size's (width or None, height): "1280x720" / "1280*720" -> (1280, 720),
    "720p" / "768P" -> (None, 720), "2K" -> (None, 1440)."""
    s = str(name).strip().lower()
    m = re.fullmatch(r"(\d+)\s*[x*]\s*(\d+)", s)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.fullmatch(r"(\d+)p", s)
    if m:
        return None, int(m.group(1))
    return None, NAMED.get(s, 0)


def nearest_resolution(width: int, height: int, values) -> str:
    """The model's name for the size nearest (width, height): `values` is
    {"480": "480p", ...} by height, or a list of names or WxH sizes (one of
    the same shape preferred)."""
    if isinstance(values, dict):
        best = min(values, key=lambda h: abs(int(h) - height))
        return values[best]
    landscape = width >= height

    def off(v):
        w, h = size_of(v)
        if w is None:
            return (0, abs(h - min(width, height) if not landscape else h - height))
        same = (w >= h) == landscape
        return (0 if same else 1, abs(w * h - width * height))
    return min(values, key=off)


def seconds_for(frames: int, fps: float, spec: dict):
    """A length in whole seconds the model takes: the nearest of `values`,
    else clamped to [min, max]; as a string when `as` says "str"."""
    s = max(1, round(frames / (fps or 24)))
    if spec.get("values"):
        s = min(spec["values"], key=lambda v: abs(float(v) - s))
        s = int(float(s))
    else:
        s = max(int(spec.get("min", s)), min(int(spec.get("max", s)), s))
    return str(s) if spec.get("as") == "str" else s


# -- where values go -------------------------------------------------------------

def _name(spec) -> str | None:
    """The field an input names: "x", {"name": "x"} or {"field": "x"}."""
    if isinstance(spec, str):
        return spec
    return (spec or {}).get("name") or (spec or {}).get("field")


def put(args: dict, path: str, value) -> None:
    """Set `value` at the dotted `path` ("instances.0.image"), making the
    dicts and lists on the way."""
    keys = path.split(".")
    cur = args
    for i, k in enumerate(keys):
        last = i == len(keys) - 1
        nxt = None if last else ([] if keys[i + 1].isdigit() else {})
        if isinstance(cur, list):
            n = int(k)
            while len(cur) <= n:
                cur.append({} if nxt is None or isinstance(nxt, dict) else [])
            if last:
                cur[n] = value
            else:
                if not isinstance(cur[n], type(nxt)):
                    cur[n] = nxt
                cur = cur[n]
        else:
            if last:
                cur[k] = value
            else:
                if not isinstance(cur.get(k), type(nxt)):
                    cur[k] = nxt
                cur = cur[k]


def append(args: dict, path: str, item) -> None:
    """Append `item` to the list at `path`, made when it isn't there."""
    keys = path.split(".")
    cur = args
    for k in keys[:-1]:
        cur = cur[int(k)] if isinstance(cur, list) else cur.setdefault(k, [] if k.isdigit() else {})
    lst = cur.setdefault(keys[-1], []) if isinstance(cur, dict) else cur[int(keys[-1])]
    lst.append(item)


def fill(template, **values):
    """The item `template` with "$prompt", "$url"... filled in."""
    if isinstance(template, str) and template.startswith("$") and template[1:] in values:
        return values[template[1:]]
    if isinstance(template, dict):
        return {k: fill(v, **values) for k, v in template.items()}
    if isinstance(template, list):
        return [fill(v, **values) for v in template]
    return template


def place(args: dict, spec, **values) -> None:
    """One input set where `spec` says: a field (the value itself, or its
    `item` filled in) or a list it is appended to (its `item` filled in)."""
    if isinstance(spec, str):
        put(args, spec, next(iter(values.values())))
        return
    item = fill(spec["item"], **values) if "item" in spec else next(iter(values.values()))
    if spec.get("list"):
        append(args, spec["list"], item)
    else:
        put(args, _name(spec), item)


# -- the shot's pictures -----------------------------------------------------------

def pictures(target, job, shot: dict, inp: dict):
    """("frames" | "references", [(role, path, what)]): the frames when the
    model has an input for a first frame and the shot has one on disk, else the
    shot's references (subjects, up to max_subjects, then the rest), a sheet as
    the panel its `view` asks for; `what` is the subject or the location."""
    from seriesmith import jobs as J

    def on_disk(rel: str) -> str | None:
        p = os.path.normpath(J._abs(job.root, rel)) if rel else ""
        return p if p and os.path.isfile(p) else None

    frames = {end: on_disk(p) for end, p in (shot.get("keyframes") or {}).items()}
    if inp.get("first") and frames.get("first"):
        return "frames", [(end, frames[end], end) for end in ("first", "last")
                          if frames.get(end) and inp.get(end)]
    if not inp.get("references"):
        return "references", []
    ref = target.recipe.get("reference_image") or {}
    panels = shot.get("panels") or []
    most = inp["references"].get("max") or target.capabilities().get("max_subjects") or 99
    subjects = [p for p in panels if p.get("subject")]
    out = []
    for p in subjects[:most] + [p for p in panels if not p.get("subject")]:
        path = on_disk(p.get("path", ""))
        if path and p.get("view") and p["view"] in (ref.get("views") or {}):
            path = panel_file(path, int(ref.get("sheet_panels") or 4), int(ref["views"][p["view"]]))
        if path:
            out.append(("references", path, p.get("subject") or p.get("location") or ""))
    total = inp["references"].get("max_total")
    return "references", out[:total] if total else out


def mentions(template: str, pics: list, shot: dict) -> str:
    """The line naming each reference picture in the prompt, for a model that
    takes them by name, e.g. <<<image_1>>> is Earl Booker. <<<image_2>>> is
    the place, Pond Side."""
    out = []
    for n, (_, _, what) in enumerate(pics, 1):
        name = str(what).replace("_", " ").title()
        place_ = what and any(p.get("location") == what for p in shot.get("panels") or [])
        out.append(f"{template.replace('{n}', str(n))} is {'the place, ' + name if place_ else name}.")
    return " ".join(out)


def router_call(target, job) -> tuple[str, dict]:
    """(model, arguments) for one take of `job` (a seriesmith.jobs.Job), its
    pictures as backends.File, which the Router backend uploads."""
    from seriesmith import jobs as J
    from seriesmith.backends import File

    spec = target.spec["router"]
    inp = spec.get("inputs") or {}
    draft = spec.get("draft") or {}
    res_name = _name(inp.get("resolution")) or "resolution"
    if getattr(job, "from_draft", None):
        # the final of a draft: its task id alone; the provider reuses the
        # draft's prompt, pictures, length, ratio, seed and sound
        return spec["model"], with_routing({"content": [{"type": "draft_task",
                                                         "draft_task": {"id": job.from_draft["task"]}}],
                                            res_name: draft.get("final_resolution", "1080p")}, spec)
    shot = J.frozen_shotlist(job)["shots"][0]
    text = J._prompt_text(shot.get("prompt") or job.prompt)
    via = inp.get("via", "")
    mode, pics = pictures(target, job, shot, inp)
    if target.capabilities().get("requires_first") and mode != "frames":
        # an image-to-video model (Runway): nothing to start from, nothing to send
        raise ValueError(f"{target.short or target.id} starts every shot from its first keyframe, and "
                         f"{shot.get('id', 'this shot')} has none yet: make it first (the shot's "
                         f"menu, or first: generate in the script)")
    args = copy.deepcopy(spec.get("arguments") or {})

    mention = (inp.get("references") or {}).get("mention")
    if mention and mode == "references" and pics:
        text = f"{text}\n\n{mentions(mention, pics, shot)}"

    # the prompt, then the pictures, in that order (a content list keeps it)
    place(args, inp.get("prompt") or "prompt", prompt=text)
    for role, path, _ in pics:
        place(args, inp[role], url=File(path, via=via))
    neg = inp.get("negative")
    if neg and getattr(job, "negative", None):
        place(args, neg, negative=job.negative)

    # length, size, ratio, seed, sound
    fps = job.fps or target.template.fps
    w, h = int(job.width or 1280), int(job.height or 720)
    if inp.get("duration"):
        put(args, _name(inp["duration"]), seconds_for(job.frames, fps, inp["duration"]))
    if inp.get("resolution"):
        put(args, res_name, nearest_resolution(w, h, inp["resolution"]["values"]))
    ratio = inp.get("ratio")
    if ratio:
        frames_mode = ratio.get("with_frames", "omit")
        if mode == "frames" and frames_mode != "keep":
            if frames_mode != "omit":
                put(args, _name(ratio), frames_mode)                 # e.g. "adaptive"
        else:
            put(args, _name(ratio), nearest_ratio(w, h, ratio["values"]))
    if inp.get("seed"):
        put(args, _name(inp["seed"]), int(job.seed) % (int(inp["seed"].get("max", 4294967295)) + 1))
    if inp.get("audio"):
        a = inp["audio"]
        on = shot.get("audio_policy") != "silent"
        put(args, _name(a), a.get("on", True) if on else a.get("off", False))

    # a proxy is a draft (Seedance 2.5): its final can be made from it
    if job.pass_ == "proxy" and draft.get("proxy"):
        args["draft"] = True
        if draft.get("resolution"):
            put(args, res_name, draft["resolution"])
    return spec["model"], with_routing(args, spec)


def with_routing(args: dict, spec: dict) -> dict:
    """`args` with how Router is to serve the call (the model's provider, and
    whether it may fall back), when the target says."""
    from seriesmith.backends.router import ROUTING
    how = {k: spec[k] for k in ("provider", "fallback") if spec.get(k) is not None}
    if how:
        args[ROUTING] = how
    return args
