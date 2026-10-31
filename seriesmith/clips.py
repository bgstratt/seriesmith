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

Simple mode can make more projects than Clips, each a show of its own
(`<root>/<Name>/<name>/`, its pictures in `<root>/<Name>/refs/`): new_project.
A project's series config says `"simple": true`, which is how its project
picker tells them from the episodes Advanced mode makes (is_simple).

Stdlib only.
"""
from __future__ import annotations

import copy
import json
import os
import re

SHOW = "Clips"
NAME = "clips"

# a new Clips project's series config: the series defaults, a proxy of their shape,
# nobody and nowhere yet (each clip adds what it needs)
SERIES = {
    "series": {"id": "clips", "title": "Clips", "fps": 24, "width": 1344, "height": 768},
    "proxy": {"width": 896, "height": 512, "audio_mode": "generate"},
    "style": {"look": "a cinematic live-action film, natural light"},
    "subjects": {},
    "locations": {},
    "audio": {"mode": "generate"},
    "simple": True,
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


def project_series(title: str, ident: str) -> dict:
    """A new Simple project's series config: the Clips one, titled."""
    cfg = copy.deepcopy(SERIES)
    cfg["series"].update(id=ident, title=title)
    return cfg


def new_project(root: str, title: str) -> dict:
    """A Simple project of its own: `<root>/<Name>/<name>/`, Name from the
    title (`Storm at the lighthouse` -> `Storm_at_the_lighthouse/
    storm_at_the_lighthouse/`), so its pictures are its show's. Returns
    {"ep"}; source.SourceError 400 for a title with nothing to name a folder
    by, 409 when that show folder is already there."""
    from seriesmith import source as S
    title = " ".join(str(title or "").split())
    show = re.sub(r"[^A-Za-z0-9._-]+", "_", title).strip("._-")
    if not show:
        raise S.SourceError(400, "name the project: letters or digits")
    show = S.check_name(show)
    if os.path.exists(os.path.join(root, show)):
        raise S.SourceError(409, f"there is already a {show} folder in {root}")
    name = S.check_name(show.lower())
    S.new_episode(root, name, title=title, show=show,
                  series=json.dumps(project_series(title, name), indent=2),
                  script=f"= {name}  {title}\n")
    return {"ep": os.path.join(os.path.abspath(root), show, name)}


def is_simple(ep: str, series_cfg: dict | None) -> bool:
    """Whether an episode is one of Simple mode's projects: its series config
    says so, or it is the Clips project (made before configs did)."""
    if (series_cfg or {}).get("simple") is True:
        return True
    norm = os.path.normcase(os.path.normpath(os.path.abspath(ep)))
    return norm.endswith(os.path.normcase(os.path.join(os.sep + SHOW, NAME)))


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
