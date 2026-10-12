"""
Seedance 2.5, hosted (Comfy Router): the story IR compiled into shotlist
entries by the shared prose compile, and each take rendered as one Router call.

    compile_episode / compile_shot / required_refs / ref_slots
        builtin video_prose (targets/generic/video_prose.py): prose with the
        spoken lines, and `panels` -- the shot's subjects' sheets, then its
        plate -- which the build asks for like VACE's reference image
    router_call(target, job) -> (model, arguments)
        the provider's request for one take (target.json `router`)

Which pictures go up (Seedance takes a shot's frames or its references, and
the two are not mixed here): with a first keyframe on disk the take is
first-frame (and last-frame, when there is one) generation, and the ratio is
left to the picture, as the provider requires; otherwise each panel is a
reference image and the ratio is the render size's nearest. A character's
4-panel sheet (4:1) is refused by the provider as invalid_input, so it goes up
as its one panel the shot wants (the three-quarter body, or the face on a
single-character close-up: the recipe's `views`), cut out once and kept in
`_panels/` beside the sheet. The seed is the take's, folded into the
provider's range (2^31: past it the provider refuses the request); the
provider decides what it means (capabilities.seed "provider"), so takes are
not promised to repeat.

Tried live 2026-10-11 (docs/PLAN.md, step 4): the seed's range and the
sheets were what it refused.
Stdlib only (the panel is cut by helpers/refsheet.py, run as a subprocess).
"""
from __future__ import annotations

import os

from seriesmith.targets.generic import video_prose as G

compile_episode = G.compile_episode
compile_shot = G.compile_shot
required_refs = G.required_refs
ref_slots = G.ref_slots

ROLES = {"first": "first_frame", "last": "last_frame"}
# every picture goes in through the Seedance virtual library (asset://<id>), as
# ComfyUI's own Seedance nodes send them: BytePlus refuses a photoreal person
# -- an AI-made one too -- as a plain URL (content_policy_violation, 2026-10-11)
VIA = "seedance"


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
    """The ratio (e.g. "16:9") nearest the picture's shape."""
    want = width / height

    def off(r: str) -> float:
        a, b = (int(x) for x in r.split(":"))
        return abs(a / b - want)
    return min(ratios, key=off)


def resolution(height: int, named: dict[str, str]) -> str:
    """The provider's name for the size nearest `height` ("720p")."""
    best = min(named, key=lambda h: abs(int(h) - height))
    return named[best]


def router_call(target, job) -> tuple[str, dict]:
    """(model, arguments) for one take of `job` (a seriesmith.jobs.Job),
    with input pictures as backends.File, which the Router backend uploads."""
    from seriesmith import jobs as J
    from seriesmith.backends import File

    spec = target.spec["router"]
    shot = J.frozen_shotlist(job)["shots"][0]
    text = J._prompt_text(shot.get("prompt") or job.prompt)

    def on_disk(rel: str) -> str | None:
        p = os.path.normpath(J._abs(job.root, rel)) if rel else ""
        return p if p and os.path.isfile(p) else None

    content: list[dict] = [{"type": "text", "text": text}]
    frames = {end: on_disk(p) for end, p in (shot.get("keyframes") or {}).items()}
    by_frames = bool(frames.get("first"))
    if by_frames:
        for end in ("first", "last"):
            if frames.get(end):
                content.append({"type": "image_url", "image_url": {"url": File(frames[end], via=VIA)},
                                "role": ROLES[end]})
    else:
        panels = shot.get("panels") or []
        most = target.capabilities()["max_subjects"]
        subjects = [p for p in panels if p.get("subject")]
        ref = target.recipe.get("reference_image") or {}
        for p in subjects[:most] + [p for p in panels if not p.get("subject")]:
            path = on_disk(p.get("path", ""))
            if path and p.get("view") and p["view"] in (ref.get("views") or {}):
                # a character's sheet: the one panel the shot wants, not the 4:1 strip
                path = panel_file(path, int(ref.get("sheet_panels") or 4), int(ref["views"][p["view"]]))
            if path:
                content.append({"type": "image_url", "image_url": {"url": File(path, via=VIA)},
                                "role": "reference_image"})
    fps = job.fps or target.template.fps
    args = dict(spec.get("arguments") or {})
    args.update({
        "content": content,
        "duration": max(1, round(job.frames / fps)),
        "resolution": resolution(int(job.height or 720), spec["resolutions"]),
        "seed": int(job.seed) % (int(spec.get("seed_max", 4294967295)) + 1),
        "generate_audio": shot.get("audio_policy") != "silent",
    })
    if not by_frames:
        args["ratio"] = nearest_ratio(int(job.width or 1280), int(job.height or 720),
                                      spec["ratios"])
    return spec["model"], args
