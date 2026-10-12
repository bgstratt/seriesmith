"""
An image model on Comfy Router, described by data: `"code":
"builtin:router_image"` in an image target.json, and its `router` block saying
how a ref take becomes that model's own request -- as router_video does for a
shot. Series refs and keyframes are worded as every image target words them
(targets/image/common.py); a take is one Router call, whatever comes back
(a link, or the picture inline: GPT Image's b64_json, Gemini's inlineData).

    "router": {
      "model": "provider/model-id",
      "arguments": {...},                         # sent as they are (n: 1, ...)
      "inputs": {
        "prompt": "prompt",                       # a field, {"field", "max_chars"},
                  # or a list item: {"list": "contents.0.parts", "item": {"text": "$prompt"}}
        "negative": "parameters.negative_prompt",
        "images": {"list": "image_list", "item": {"image": "$url"}, "max": 10,
                   "mention": "<<<image_{n}>>>"}
                  # or {"field": "image", "max": 14}: one picture as itself,
                  #   several as a list ("one": true sends only the first)
                  # or {"fields": ["input_image", "input_image_2", ...]};
                  # "first": true puts them before the prompt in a shared list (a chat
                  # message's parts: Gemini, Qwen)
        "ratio": {"name": "aspect_ratio", "values": ["1:1", "16:9", ...]},
        "resolution": {"name": "resolution", "values": ["1K", "2K"]},
                  # the smallest with the picture's pixels (1K: about 1 MP)
        "size": {"name": "size", "format": "{w}x{h}", "multiple": 16,
                 "min_pixels": 3686400, "max_pixels": 9437184, "max_side": 4096},
                  # or "values": ["1024x1024", "1536x1024"]: the nearest in shape
        "width": {"name": "width", "min": 256, "max": 2048, "multiple": 16},
        "height": {"name": "height", ...},
        "seed": {"name": "seed", "max": 2147483647},
        "via": "base64"                           # how pictures go in (File.via)
      }
    }

A job's reference pictures (an edit: the picture it starts from, a keyframe's
characters and plate, a wardrobe variant's base view) are the GenJob's
`references`, each with its local `file` (refs.hosted_references cuts a sheet's
panel or composes a composite first). Stdlib only.
"""
from __future__ import annotations

import copy
import math
import re

from seriesmith.targets.generic.router_video import _name, append, fill, fit, place, put
from seriesmith.targets.image.common import keyframe_prompt, ref_prompt  # noqa: F401


def nearest_ratio(width: int, height: int, ratios: list[str]) -> str:
    """The ratio ("16:9", "2.35:1") nearest the picture's shape; names that
    aren't shapes ("auto") are left out."""
    want = width / height
    shapes = [r for r in ratios if re.fullmatch(r"\d+(\.\d+)?:\d+(\.\d+)?", str(r))]

    def off(r: str) -> float:
        a, b = (float(x) for x in r.split(":"))
        return abs(math.log((a / b) / want))
    return min(shapes, key=off)


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


def router_call(target, job) -> tuple[str, dict]:
    """(model, arguments) for one ref take (refs.GenJob), its pictures as
    backends.File (the Router backend uploads them, or inlines them)."""
    from seriesmith.backends import File

    spec = target.spec["router"]
    inp = spec.get("inputs") or {}
    args = copy.deepcopy(spec.get("arguments") or {})
    w, h = int(job.width or 1024), int(job.height or 1024)
    via = inp.get("via", "")

    imgs = inp.get("images")
    files = [r.get("file") or r.get("path") for r in (getattr(job, "references", None) or [])]
    files = [f for f in files if f]
    if imgs and imgs.get("max"):
        files = files[:int(imgs["max"])]
    if not imgs:
        files = []

    # the prompt (the pictures named in it when the model takes them by name)
    text = job.prompt
    pspec = inp.get("prompt") or "prompt"
    tail = ""
    if imgs and imgs.get("mention") and files:
        tail = " ".join(f"{imgs['mention'].replace('{n}', str(n))}" for n in range(1, len(files) + 1))
        tail = f"Reference pictures: {tail}."
    limit = pspec.get("max_chars") if isinstance(pspec, dict) else None
    if limit:
        text = fit(text, limit - (len(tail) + 1 if tail else 0))
    if tail:
        text = f"{text} {tail}"
    if not (imgs and imgs.get("first") and files):
        place(args, pspec, prompt=text)
    if inp.get("negative") and getattr(job, "negative", ""):
        put(args, _name(inp["negative"]) or inp["negative"], job.negative)

    # the pictures
    if files:
        mime = lambda p: "image/jpeg" if p.lower().endswith((".jpg", ".jpeg")) else "image/png"  # noqa: E731
        made = [fill(imgs.get("item", "$url"), url=File(p, via=via), mime=mime(p)) for p in files]
        if imgs.get("list"):
            for item in made:
                append(args, imgs["list"], item)
        elif imgs.get("fields"):
            for name, item in zip(imgs["fields"], made):
                put(args, name, item)
        else:
            one = imgs.get("one") or len(made) == 1
            put(args, _name(imgs), made[0] if one else made)
        if imgs.get("first"):
            place(args, pspec, prompt=text)

    # the size
    if inp.get("ratio"):
        put(args, _name(inp["ratio"]), nearest_ratio(w, h, inp["ratio"]["values"]))
    if inp.get("resolution"):
        put(args, _name(inp["resolution"]), pick_resolution(w, h, inp["resolution"]["values"]))
    if inp.get("size"):
        s = inp["size"]
        if s.get("values"):
            put(args, _name(s), nearest_size(w, h, s["values"]))
        else:
            sw, sh = fit_size(w, h, s)
            put(args, _name(s), s.get("format", "{w}x{h}").format(w=sw, h=sh))
    if inp.get("width") and inp.get("height"):
        put(args, _name(inp["width"]), clamp(w, inp["width"]))
        put(args, _name(inp["height"]), clamp(h, inp["height"]))
    if inp.get("seed"):
        put(args, _name(inp["seed"]), int(job.seed) % (int(inp["seed"].get("max", 2147483647)) + 1))

    from seriesmith.targets.generic.router_video import with_routing
    return spec["model"], with_routing(args, spec)
