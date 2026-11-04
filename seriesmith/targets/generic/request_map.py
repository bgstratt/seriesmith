"""
request_map -- a job's values put where a hosted model's own request wants them, whatever
serves the model. The `inputs` block of a target.json names each value's place (a field, a
dotted path, a list and an item template) and what the model accepts (a set of values, a
range, a multiple); these are the functions that read it, for pictures and video
(router_image, router_video) and for sound (cue.hosted_call).

What a model's request contains is decided by its caller; here is only how a value gets
there and how it is snapped to what the model takes.

Stdlib only.
"""
from __future__ import annotations

import math
import re


# -- where values go -------------------------------------------------------------

def field_name(spec) -> str | None:
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
        put(args, field_name(spec), item)


def max_chars(spec) -> int | None:
    """The longest prompt the prompt's input says the model takes, if it says."""
    return spec.get("max_chars") if isinstance(spec, dict) else None


def put_seed(args: dict, spec: dict, seed: int, largest: int) -> None:
    """The seed folded into the model's range: `spec`'s `max`, else `largest`."""
    put(args, field_name(spec), int(seed) % (int(spec.get("max", largest)) + 1))


# -- what the model takes ----------------------------------------------------------

def nearest_ratio(width: int, height: int, ratios: list[str]) -> str:
    """The ratio ("16:9", "2.35:1") nearest the picture's shape; names that aren't shapes
    ("auto", "adaptive") are left out. Nearest by the logs of the shapes, so landscape and
    portrait count alike: by plain difference a slightly wide picture was nearer 9:16 than
    16:9. A tie goes to the ratio the model lists first."""
    want = width / height
    shapes = [r for r in ratios if re.fullmatch(r"\d+(\.\d+)?:\d+(\.\d+)?", str(r))]

    def off(r: str) -> float:
        a, b = (float(x) for x in r.split(":"))
        return round(abs(math.log((a / b) / want)), 9)
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


def k_of(name: str) -> int | None:
    """A resolution name's long side: "1K" / "1k" -> 1024, "2K" -> 2048."""
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*k", str(name).strip().lower())
    return int(float(m.group(1)) * 1024) if m else None


def pick_resolution(width: int, height: int, values: list[str]) -> str:
    """The smallest named resolution with the picture's pixels, else the
    largest: "1K" is about a megapixel in any shape (Gemini's 16:9 1K is
    1376x768), so a 1344x768 plate is 1K and a 2048x2048 one 2K."""
    named = sorted((k_of(v), v) for v in values if k_of(v))
    if not named:
        return values[0]
    need = width * height
    return next((v for k, v in named if k * k >= need * 0.9), named[-1][1])


def fit_size(width: int, height: int, spec: dict) -> tuple[int, int]:
    """(width, height) in the shape asked for, scaled into the model's pixel
    range and longest side, on its multiple."""
    m = int(spec.get("multiple") or 8)
    w, h = float(width), float(height)
    lo, hi = spec.get("min_pixels"), spec.get("max_pixels")
    if lo and w * h < lo:
        k = math.sqrt(lo / (w * h))
        w, h = w * k, h * k
    if hi and w * h > hi:
        k = math.sqrt(hi / (w * h))
        w, h = w * k, h * k
    side = spec.get("max_side")
    if side and max(w, h) > side:
        k = side / max(w, h)
        w, h = w * k, h * k
    def snap(v: float) -> int:
        # rounded up when there's a floor to stay above, else down
        return max(m, (math.ceil(v / m) if lo else int(v // m)) * m)
    return snap(w), snap(h)


def nearest_size(width: int, height: int, values: list[str]) -> str:
    """The listed size ("1536x1024", "1024*1024") nearest in shape, then area."""
    def dims(v):
        m = re.fullmatch(r"(\d+)\s*[x*]\s*(\d+)", str(v).strip().lower())
        return (int(m.group(1)), int(m.group(2))) if m else None
    sized = [(dims(v), v) for v in values if dims(v)]
    want = width / height
    return min(sized, key=lambda d: (round(abs(math.log((d[0][0] / d[0][1]) / want)), 3),
                                      abs(d[0][0] * d[0][1] - width * height)))[1]


def clamp(v: int, spec: dict) -> int:
    m = int(spec.get("multiple") or 1)
    v = max(int(spec.get("min", 1)), min(int(spec.get("max", v)), v))
    return max(m, v // m * m)


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


def ceil_seconds(seconds: float, spec: dict) -> int:
    """A length in whole seconds, rounded up (a music cue must not come back short) and
    clamped to [min, max]."""
    return max(spec.get("min", 1), min(spec.get("max", 3600), math.ceil(float(seconds))))


def fit(text: str, most: int) -> str:
    """`text` in at most `most` characters, by whole sentences: the style line
    goes first, then sentences from the start (the place, then the people's
    looks, which the pictures carry), so what happens -- the action, the
    dialogue, the sound, at the end -- stays; cut mid-sentence only when the
    last one alone is longer than that."""
    if len(text) <= most:
        return text
    sents = [s.strip() for s in re.findall(r"[^.!?]*[.!?]+[\"”')]*|[^.!?]+$", text) if s.strip()]
    sents = [s for s in sents if not s.startswith("Style:")] or sents
    while len(sents) > 1 and len(" ".join(sents)) > most:
        sents.pop(0)
    out = " ".join(sents)
    return out if len(out) <= most else out[:most].rstrip()
