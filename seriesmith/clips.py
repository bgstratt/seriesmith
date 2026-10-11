"""
Simple mode's clips (docs/PLAN.md, step 12): a scratch project for one-off
clips, without setting up a series. It is an ordinary series underneath --
`<root>/Clips/clips/` with its own series config and script, written by the
editor's forms -- so refs, renders, takes, upscales and the queue work on it
unchanged, and any clip can later go into a real series.

A clip is one sequence of one shot (`# cl007  <place>` / `## c007`). Queuing
one (queue_clip) makes the pictures it still needs first (its characters'
sheets, its place's plate: refs.generate) and then, when they have come out,
its takes: a follow-up job on seriesmith's queue waits for those pictures,
makes each live (refs.auto_pick) and asks for the renders.

Stdlib only.
"""
from __future__ import annotations

import json
import os

SHOW = "Clips"
NAME = "clips"

# a new Clips project's series config: the series defaults, a 480p proxy,
# nobody and nowhere yet (each clip adds what it needs)
SERIES = {
    "series": {"id": "clips", "title": "Clips", "fps": 24, "width": 1344, "height": 768},
    "proxy": {"width": 864, "height": 480, "audio_mode": "generate"},
    "style": {"look": "a cinematic live-action film, natural light"},
    "subjects": {},
    "locations": {},
    "audio": {"mode": "generate"},
}


def clips_ep(root: str) -> str:
    return os.path.join(root, SHOW, NAME)


def ensure_clips(root: str) -> dict:
    """The Clips project in `root` (made the first time: source.new_episode).
    Returns {"ep", "made"}."""
    from seriesmith import source as S
    ep = clips_ep(root)
    if os.path.isfile(os.path.join(ep, "series.json")):
        return {"ep": ep, "made": False}
    S.new_episode(root, NAME, title="Clips", show=SHOW,
                  series=json.dumps(SERIES, indent=2), script=f"= {NAME}  Clips\n")
    return {"ep": ep, "made": True}


def needed_refs(ep: str, pass_: str, shot: str) -> list:
    """The refs (a character's sheet, a place's plate, a keyframe) `shot` uses
    in `pass_` that have no live file yet."""
    from seriesmith import refs as R
    s = R.load_series(ep)
    refs = R.series_refs(s) + R.keyframe_refs(ep)
    usage = R.used_by(s, refs)
    return [r for r in refs
            if shot in ((usage.get(r.id) or {}).get(pass_) or [])
            and not r.is_audio and r.path and not os.path.isfile(r.file)]


def queued_takes(ref) -> list[str]:
    """The queue jobs of a ref's candidates still on their way."""
    from seriesmith import refs as R
    out = []
    for v in (R.VIEW_TAGS if ref.has_views else [None]):
        for t in R.list_takes(ref, v):
            pid = (t.sidecar or {}).get("comfy_prompt_id")
            if t.status == "queued" and pid:
                out.append(pid)
    return out
