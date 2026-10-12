"""
A video model on Comfy Router, described by data: `"code":
"builtin:router_video"` in its target.json, and its `router` block saying how a
shot becomes that model's own arguments. Every Router model is called the same
way (comfy-sdk models.submit, by "provider/model" id); what differs is the
shape of its input, and that is what `router.inputs` maps:

    "router": {
      "model": "provider/model-id",
      "arguments": {...},                 # sent as they are
      "inputs": {
        "shape": "fields",                # or "content": BytePlus's list of typed items
        "prompt": "prompt",               # the field the prose goes in ("fields")
        "negative": "negative_prompt",    # optional
        "duration": {"name": "duration", "min": 4, "max": 30},       # whole seconds,
                    # or "values": [5, 10] (the nearest is sent), "as": "str" for "5"
        "resolution": {"name": "resolution", "values": {"480": "480p", "720": "720p"}},
        "ratio": {"name": "aspect_ratio", "values": ["16:9", "9:16", "1:1"],
                  "with_frames": "omit"},  # or a value ("adaptive") for frame mode
        "seed": {"name": "seed", "max": 2147483647},
        "audio": {"name": "generate_audio"},
        "references": {"name": "reference_images", "max": 4},   # a list of pictures,
                    # each the picture's URL, or {"wrap": "url"} for {"url": ...};
                    # "content": {"role": "reference_image"} instead
        "first": {"name": "first_frame_url"},                    # or {"role": "first_frame"}
        "last": {"name": "last_frame_url"},
        "via": "seedance"                 # how pictures go in (backends.File.via)
      },
      "draft": {"proxy": true, "resolution": "480p", "final_resolution": "1080p"}
    }

What a shot sends: its prose prompt (the shared prose compile, video_prose);
with a first keyframe on disk and an input for it, its frames (first, and
last when there is one), else its references -- the subjects' pictures, then
the plate, a character's 4-panel sheet cut to the one panel the shot wants
(no provider takes a 4:1 strip) -- its length, size and ratio snapped to what
the model takes, its seed folded into the model's range, and whether it
makes sound. `draft` (Seedance 2.5): a proxy take is a Draft, and a final
made from one (job.from_draft) sends that draft's task id alone.

Stdlib only (a panel is cut by helpers/refsheet.py, run as a subprocess).
"""
from __future__ import annotations

import os

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


def nearest_ratio(width: int, height: int, ratios: list[str]) -> str:
    """The ratio (e.g. "16:9") nearest the picture's shape ("adaptive" and
    the like are not shapes: left out)."""
    want = width / height
    shapes = [r for r in ratios if ":" in r]

    def off(r: str) -> float:
        a, b = (int(x) for x in r.split(":"))
        return abs(a / b - want)
    return min(shapes, key=off)


def nearest_resolution(height: int, named: dict[str, str]) -> str:
    """The model's name for the size nearest `height` ("720p")."""
    best = min(named, key=lambda h: abs(int(h) - height))
    return named[best]


def seconds_for(frames: int, fps: float, spec: dict):
    """A length in whole seconds the model takes: the nearest of `values`,
    else clamped to [min, max]; as a string when `as` says "str"."""
    s = max(1, round(frames / (fps or 24)))
    if spec.get("values"):
        s = min(spec["values"], key=lambda v: abs(float(v) - s))
    else:
        s = max(int(spec.get("min", s)), min(int(spec.get("max", s)), s))
    return str(s) if spec.get("as") == "str" else s


def pictures(target, job, shot: dict, inp: dict):
    """("frames" | "references", [(role, path)]): the frames when the model has
    an input for a first frame and the shot has one on disk, else the shot's
    references (subjects, up to max_subjects, then the rest), a sheet as the
    panel its `view` asks for."""
    from seriesmith import jobs as J

    def on_disk(rel: str) -> str | None:
        p = os.path.normpath(J._abs(job.root, rel)) if rel else ""
        return p if p and os.path.isfile(p) else None

    frames = {end: on_disk(p) for end, p in (shot.get("keyframes") or {}).items()}
    if inp.get("first") and frames.get("first"):
        return "frames", [(end, frames[end]) for end in ("first", "last")
                          if frames.get(end) and inp.get(end)]
    ref = target.recipe.get("reference_image") or {}
    panels = shot.get("panels") or []
    most = (inp.get("references") or {}).get("max") or target.capabilities().get("max_subjects") or 99
    subjects = [p for p in panels if p.get("subject")]
    out = []
    for p in subjects[:most] + [p for p in panels if not p.get("subject")]:
        path = on_disk(p.get("path", ""))
        if path and p.get("view") and p["view"] in (ref.get("views") or {}):
            path = panel_file(path, int(ref.get("sheet_panels") or 4), int(ref["views"][p["view"]]))
        if path:
            out.append(("references", path))
    return "references", out


def _name(spec) -> str | None:
    return spec if isinstance(spec, str) else (spec or {}).get("name")


def router_call(target, job) -> tuple[str, dict]:
    """(model, arguments) for one take of `job` (a seriesmith.jobs.Job), its
    pictures as backends.File, which the Router backend uploads."""
    from seriesmith import jobs as J
    from seriesmith.backends import File

    spec = target.spec["router"]
    inp = spec.get("inputs") or {}
    content = inp.get("shape") == "content"
    draft = spec.get("draft") or {}
    if getattr(job, "from_draft", None):
        # the final of a draft: its task id alone; the provider reuses the
        # draft's prompt, pictures, length, ratio, seed and sound
        return spec["model"], {"content": [{"type": "draft_task",
                                            "draft_task": {"id": job.from_draft["task"]}}],
                               _name(inp.get("resolution")) or "resolution":
                                   draft.get("final_resolution", "1080p")}
    shot = J.frozen_shotlist(job)["shots"][0]
    text = J._prompt_text(shot.get("prompt") or job.prompt)
    via = inp.get("via", "")
    mode, pics = pictures(target, job, shot, inp)
    args = dict(spec.get("arguments") or {})

    # the prompt and the pictures
    items = [{"type": "text", "text": text}] if content else None
    if not content:
        args[_name(inp.get("prompt")) or "prompt"] = text
    refs_spec = inp.get("references") or {}
    for role, path in pics:
        f = File(path, via=via)
        if content:
            r = (refs_spec.get("role") if role == "references"
                 else (inp.get(role) or {}).get("role")) or role
            items.append({"type": "image_url", "image_url": {"url": f}, "role": r})
        elif role == "references" and _name(refs_spec):
            item = {refs_spec["wrap"]: f} if refs_spec.get("wrap") else f
            args.setdefault(_name(refs_spec), []).append(item)
        elif role in ("first", "last") and _name(inp.get(role)):
            args[_name(inp[role])] = f
    if content:
        args["content"] = items
    neg = _name(inp.get("negative"))
    if neg and getattr(job, "negative", None):
        args[neg] = job.negative

    # length, size, ratio, seed, sound
    fps = job.fps or target.template.fps
    if inp.get("duration"):
        args[_name(inp["duration"])] = seconds_for(job.frames, fps, inp["duration"])
    if inp.get("resolution"):
        args[_name(inp["resolution"])] = nearest_resolution(int(job.height or 720),
                                                            inp["resolution"]["values"])
    ratio = inp.get("ratio")
    if ratio:
        if mode == "frames" and ratio.get("with_frames", "omit") != "keep":
            if ratio.get("with_frames", "omit") != "omit":
                args[_name(ratio)] = ratio["with_frames"]          # e.g. "adaptive"
        else:
            args[_name(ratio)] = nearest_ratio(int(job.width or 1280), int(job.height or 720),
                                               ratio["values"])
    if inp.get("seed"):
        args[_name(inp["seed"])] = int(job.seed) % (int(inp["seed"].get("max", 4294967295)) + 1)
    if inp.get("audio"):
        args[_name(inp["audio"])] = shot.get("audio_policy") != "silent"

    # a proxy is a draft (Seedance 2.5): its final can be made from it
    if job.pass_ == "proxy" and draft.get("proxy"):
        args["draft"] = True
        if draft.get("resolution") and inp.get("resolution"):
            args[_name(inp["resolution"])] = draft["resolution"]
    return spec["model"], args
