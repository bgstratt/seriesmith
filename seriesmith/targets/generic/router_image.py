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

from seriesmith.targets import hosted_block
from seriesmith.targets import prompt_template as TP
from seriesmith.targets.generic.request_map import (  # noqa: F401
    append, clamp, field_name, fill, fit, fit_size, k_of, max_chars, nearest_ratio, nearest_size,
    pick_resolution, place, put, put_seed)
from seriesmith.targets.image.common import keyframe_prompt, ref_prompt  # noqa: F401


def router_call(target, job) -> tuple[str, dict]:
    """(model, arguments) for one ref take (refs.GenJob), its pictures as
    backends.File (the Router backend uploads them, or inlines them)."""
    from seriesmith.backends import File

    spec = hosted_block(target.spec)
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
    text = TP.request_prompt(TP.request_template(target, "image"), text, max_chars(pspec), fit,
                             mentions=tail)
    if not (imgs and imgs.get("first") and files):
        place(args, pspec, prompt=text)
    if inp.get("negative") and getattr(job, "negative", ""):
        put(args, field_name(inp["negative"]) or inp["negative"], job.negative)

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
            put(args, field_name(imgs), made[0] if one else made)
        if imgs.get("first"):
            place(args, pspec, prompt=text)

    # the size
    if inp.get("ratio"):
        put(args, field_name(inp["ratio"]), nearest_ratio(w, h, inp["ratio"]["values"]))
    if inp.get("resolution"):
        put(args, field_name(inp["resolution"]), pick_resolution(w, h, inp["resolution"]["values"]))
    if inp.get("size"):
        s = inp["size"]
        if s.get("values"):
            put(args, field_name(s), nearest_size(w, h, s["values"]))
        else:
            sw, sh = fit_size(w, h, s)
            put(args, field_name(s), s.get("format", "{w}x{h}").format(w=sw, h=sh))
    if inp.get("width") and inp.get("height"):
        put(args, field_name(inp["width"]), clamp(w, inp["width"]))
        put(args, field_name(inp["height"]), clamp(h, inp["height"]))
    if inp.get("seed"):
        put_seed(args, inp["seed"], job.seed, 2147483647)

    from seriesmith.targets.generic.router_video import with_routing
    return spec["model"], with_routing(args, spec)
