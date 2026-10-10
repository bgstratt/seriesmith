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
reference image and the ratio is the render size's nearest. The seed is the
take's, folded into the provider's range; the provider decides what it means
(capabilities.seed "provider"), so takes are not promised to repeat.

Not yet tried against the live service (docs/PLAN.md, step 4).
Stdlib only.
"""
from __future__ import annotations

import os

from seriesmith.targets.generic import video_prose as G

compile_episode = G.compile_episode
compile_shot = G.compile_shot
required_refs = G.required_refs
ref_slots = G.ref_slots

ROLES = {"first": "first_frame", "last": "last_frame"}


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
                content.append({"type": "image_url", "image_url": {"url": File(frames[end])},
                                "role": ROLES[end]})
    else:
        panels = shot.get("panels") or []
        most = target.capabilities()["max_subjects"]
        subjects = [p for p in panels if p.get("subject")]
        for p in subjects[:most] + [p for p in panels if not p.get("subject")]:
            path = on_disk(p.get("path", ""))
            if path:
                content.append({"type": "image_url", "image_url": {"url": File(path)},
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
