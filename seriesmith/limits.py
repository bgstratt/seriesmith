"""
limits — what a video target takes, in one place: how long a shot may be,
what sizes, how long a prompt, which pictures and how they are sent, whether
it makes sound. A target.json already says all of this, spread over its
`template` (the frame grid, the size rules), its `router.inputs` (a hosted
model's lengths, resolutions, prompt limit, pictures), its `capabilities` and
its `recipe`; `describe` reads it into one dict and `apply` writes such a
dict back where each limit lives, so the editor shows and edits one form for
every target, local or hosted.

    {"length":   {"frames": {"step": 8, "base": 1, "max": 481}, "fps": 24,
                  "trained": 81,                              local: the frame grid
                  "seconds": {"min": 4, "max": 15}            hosted: whole seconds,
                             | {"values": [4, 6, 8]}},          or a set of them
     "size":     {"multiple": 32, "fit": "snap",
                  "long_side": 1536, "pixels": 1048576,
                  "sizes": [[1280, 720], [720, 1280]],        only these (local)
                  "resolutions": ["480p", "720p"]},           named (hosted)
     "prompt":   {"max_chars": 1000},                         hosted
     "pictures": {"references": 3, "first": true, "last": true,
                  "needs_first": false, "via": "base64"},
     "sound":    true,
     "editable": ["length", "size", ...]}                     what apply may change

A local target's pictures and sound are its graph's (what the workflow wires),
so only its length, size and needs-a-first-frame are editable; a hosted one's
are all data. An input switched off on a hosted target is kept under
`router.off`, so switching it back on restores how it was sent.

Stdlib only.
"""
from __future__ import annotations

import copy

SECTIONS = ("length", "size", "prompt", "pictures", "sound")
VIAS = ("", "seedance", "base64", "datauri")
NEEDS_FIRST = ("{model} starts every shot from its first frame: generate one, import one, "
               "or give the shot `continuous: first`")


def _router(spec: dict) -> dict | None:
    return spec.get("router") if isinstance(spec.get("router"), dict) else None


def describe(spec: dict) -> dict:
    """The limits a target.json states (see the module docstring)."""
    tpl = spec.get("template") or {}
    caps = spec.get("capabilities") or {}
    recipe = spec.get("recipe") or {}
    router = _router(spec)
    inp = (router or {}).get("inputs") or {}
    fr = tpl.get("frames") or {}
    length: dict = {"frames": {k: fr[k] for k in ("step", "base", "max") if k in fr}}
    fps = tpl.get("fps", 24)
    length["fps"] = tpl.get("default_fps", 24) if fps == "series" else fps
    if fps == "series":
        length["fps_from_series"] = True
    if tpl.get("trained_frames"):
        length["trained"] = int(tpl["trained_frames"])
    d = inp.get("duration")
    if isinstance(d, dict):
        length["seconds"] = ({"values": list(d["values"])} if d.get("values")
                             else {k: d[k] for k in ("min", "max") if k in d})
    size: dict = {"multiple": int(tpl.get("size_multiple", 1)), "fit": tpl.get("size_fit", "error")}
    ms = tpl.get("max_size") or {}
    for k in ("long_side", "pixels"):
        if ms.get(k):
            size[k] = int(ms[k])
    if tpl.get("sizes"):
        size["sizes"] = [list(s) for s in tpl["sizes"]]
    res = inp.get("resolution")
    if isinstance(res, dict) and res.get("values") is not None:
        vals = res["values"]
        size["resolutions"] = list(vals.values()) if isinstance(vals, dict) else list(vals)
    p = inp.get("prompt")
    prompt = {"max_chars": p.get("max_chars")} if isinstance(p, dict) and p.get("max_chars") else {}
    hard = recipe.get("keyframe_required") or {}
    keyframes = recipe.get("keyframes") or []
    if router is not None:
        refs = inp.get("references")
        pictures = {"references": _refs_max(refs, caps) if refs else 0,
                    "first": "first" in inp, "last": "last" in inp, "via": inp.get("via", "")}
    else:
        pictures = {"references": caps.get("max_subjects"), "first": "first" in keyframes,
                    "last": "last" in keyframes}
    pictures["needs_first"] = "first" in hard
    out = {"length": length, "size": size, "prompt": prompt, "pictures": pictures,
           "sound": caps.get("audio", "generate") != "none",
           "editable": list(SECTIONS) if router is not None else ["length", "size", "pictures.needs_first"]}
    return out


def apply(spec: dict, limits: dict) -> dict:
    """A copy of target.json `spec` with `limits` (all of describe's dict, or
    some sections of it) written where each lives. ValueError for a limit that
    can't be (an empty grid, a size list with a bad entry, an unknown via)."""
    spec = copy.deepcopy(spec)
    router = _router(spec)
    hosted = router is not None
    had = {k: k in spec for k in ("template", "capabilities", "recipe")}
    tpl = spec.setdefault("template", {})
    caps = spec.setdefault("capabilities", {})
    recipe = spec.setdefault("recipe", {})
    inp = router.setdefault("inputs", {}) if hosted else {}
    model = (router or {}).get("model") or spec.get("id", "this model")

    length = limits.get("length")
    if length:
        fr = length.get("frames")
        if fr:
            step, base, top = int(fr.get("step", 1)), int(fr.get("base", 1)), int(fr.get("max", 1))
            if step < 1 or base < 1 or top < base:
                raise ValueError("length: the frame grid needs step >= 1, base >= 1 and max >= base")
            tpl["frames"] = {"step": step, "base": base, "max": top}
        if "trained" in length:
            if length["trained"]:
                tpl["trained_frames"] = int(length["trained"])
            else:
                tpl.pop("trained_frames", None)
        sec = length.get("seconds")
        if sec and hosted:
            d = inp.get("duration") or {"name": "duration"}
            keep = {k: d[k] for k in ("name", "as", "_note") if k in d}
            if sec.get("values"):
                vals = sorted({int(v) for v in sec["values"]})
                if not vals or vals[0] < 1:
                    raise ValueError("length: the seconds a model takes are whole numbers from 1")
                inp["duration"] = {**keep, "values": vals}
                lo, hi = vals[0], vals[-1]
            else:
                lo, hi = int(sec.get("min", 1)), int(sec.get("max", sec.get("min", 1)))
                if lo < 1 or hi < lo:
                    raise ValueError("length: seconds need 1 <= min <= max")
                inp["duration"] = {**keep, "min": lo, "max": hi}
            # a hosted model's frame grid is its seconds at 24 fps
            if not fr:
                tpl["frames"] = {"step": 24, "base": lo * 24, "max": hi * 24}

    size = limits.get("size")
    if size:
        if "multiple" in size:
            m = int(size["multiple"])
            if m < 1:
                raise ValueError("size: the multiple is 1 or more")
            tpl["size_multiple"] = m
        if "fit" in size:
            if size["fit"] not in ("error", "snap"):
                raise ValueError('size: fit is "error" or "snap"')
            if size["fit"] != tpl.get("size_fit", "error"):
                tpl["size_fit"] = size["fit"]
        ms = dict(tpl.get("max_size") or {})
        for k in ("long_side", "pixels"):
            if k in size:
                if size[k]:
                    ms[k] = int(size[k])
                else:
                    ms.pop(k, None)
        if ms:
            tpl["max_size"] = ms
        else:
            tpl.pop("max_size", None)
        if "sizes" in size:
            sizes = size["sizes"] or []
            for s in sizes:
                if not (isinstance(s, (list, tuple)) and len(s) == 2 and all(int(x) > 0 for x in s)):
                    raise ValueError(f"size: {s!r} isn't a [width, height]")
            if sizes:
                tpl["sizes"] = [[int(w), int(h)] for w, h in sizes]
            else:
                tpl.pop("sizes", None)
        if "resolutions" in size and hosted:
            res = inp.get("resolution")
            if not isinstance(res, dict):
                raise ValueError("size: this model's request has no resolution field")
            want = list(size["resolutions"])
            if not want:
                raise ValueError("size: keep at least one resolution")
            vals = res.get("values")
            if isinstance(vals, dict):                 # by height ({"720": "std"}): keep those named
                res["values"] = {h: n for h, n in vals.items() if n in want}
            else:
                res["values"] = want
            from seriesmith.router_inspect import _sizes
            names = [f"{h}p" for h in res["values"]] if isinstance(res["values"], dict) else res["values"]
            sz = _sizes(names)
            for k in ("final", "proxy"):
                if isinstance(spec.get("presets", {}).get(k), dict):
                    spec["presets"][k].update(width=sz[k][0], height=sz[k][1])

    prompt = limits.get("prompt")
    if prompt is not None and hosted:
        p = inp.get("prompt") or "prompt"
        n = prompt.get("max_chars")
        if isinstance(p, str):
            p = {"field": p}
        if n:
            p["max_chars"] = int(n)
        else:
            p.pop("max_chars", None)
        inp["prompt"] = p if (n or "list" in p) else (p.get("field") or "prompt")

    pics = limits.get("pictures")
    if pics:
        if "needs_first" in pics:
            hard = dict(recipe.get("keyframe_required") or {})
            if pics["needs_first"]:
                hard.setdefault("first", NEEDS_FIRST.format(model=model))
            else:
                hard.pop("first", None)
            if hard:
                recipe["keyframe_required"] = hard
            else:
                recipe.pop("keyframe_required", None)
        if hosted:
            off = router.setdefault("off", {})
            for k in ("first", "last"):
                if k in pics:
                    _switch(inp, off, k, bool(pics[k]))
            if "references" in pics:
                n = int(pics["references"] or 0)
                _switch(inp, off, "references", n > 0)
                if n > 0 and "references" in inp:
                    # pictures in all, the place's plate included ("up to 3
                    # asset images"): subjects first, the plate when there's room
                    refs = inp["references"]
                    if _refs_max(refs, caps) != n:
                        refs["max"] = refs["max_total"] = n
                    if caps.get("max_subjects", 4) != n:
                        caps["max_subjects"] = n
            if not off:
                router.pop("off", None)
            recipe["keyframes"] = [e for e in ("first", "last") if e in inp]
            if "references" not in inp:
                recipe.pop("reference_image", None)
            if "via" in pics:
                if pics["via"] not in VIAS:
                    raise ValueError(f"pictures: via is one of {', '.join(v or 'link' for v in VIAS)}")
                if pics["via"]:
                    inp["via"] = pics["via"]
                else:
                    inp.pop("via", None)

    if "sound" in limits and hosted:
        if limits["sound"]:
            if caps.get("audio") == "none":
                caps.pop("audio", None)
                recipe["policies"] = ["generate"]
                recipe.pop("policy_fallback", None)
        else:
            caps["audio"] = "none"
            recipe["policies"] = ["silent"]
            recipe["policy_fallback"] = {"to": "silent", "why": f"{model} makes no sound: the take is "
                                                                f"mute, and the edit lays the sound under it"}
    for k, was in had.items():                          # no empty block a target didn't have
        if not was and not spec.get(k):
            spec.pop(k, None)
    return spec


def _refs_max(refs: dict, caps: dict) -> int:
    """How many reference pictures a hosted model takes: its total when set
    (router_video's max_total), else its subjects' cap."""
    return int(refs.get("max_total") or refs.get("max") or caps.get("max_subjects") or 4)


def _switch(inp: dict, off: dict, key: str, on: bool) -> None:
    """Move a hosted model's input between `inputs` and `router.off`."""
    if on and key not in inp and key in off:
        inp[key] = off.pop(key)
    elif not on and key in inp:
        off[key] = inp.pop(key)
