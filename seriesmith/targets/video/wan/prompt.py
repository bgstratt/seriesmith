"""
The Wan 2.2 prompt: one paragraph of plain prose, for every Wan target.

Wan's UMT5 text encoder reads a plain description (Wan's prompt guide: the
subject and what it looks like, the scene, the motion, the camera, the look).
The structure is the ltx2 target's (targets/video/ltx2/prompt.py), minus
everything about sound: Wan makes no audio, so there is no soundscape, music
or quoted dialogue. A line of dialogue becomes silent acting, so the picture
still carries the performance the edit lays the voice over:

    Style: <look>. A <size> of <location description>, <camera>. <Name> is
    <design>. <action> <Name> talks, <delivery>, mouth moving with the words.

A voiceover by someone in frame keeps their lips closed; a line from off
screen adds nothing (nobody in frame speaks it). The negative prompt is a
preset value (Wan's standard Chinese one, from ComfyUI's Wan templates).

Stdlib only.
"""
from __future__ import annotations

from seriesmith.targets import prompt_template as TP
from seriesmith.targets.prose import scene_parts
from seriesmith.targets.video.ltx2.prompt import _sentence


def acting(shot, book: dict) -> list[str]:
    """The dialogue as silent acting: one sentence per run of lines by one
    speaker, in script order."""
    out, last = [], None
    closed: set[str] = set()
    for d in shot.dialogue:
        e = book.get(d.speaker) or {}
        name = e.get("name", d.speaker)
        delivery = (d.delivery or "").strip().rstrip(".")
        if d.mode == "vo":
            if d.speaker in shot.cast and d.speaker not in closed:
                closed.add(d.speaker)
                out.append(_sentence(f"{name} stays silent, lips closed"))
            last = None
            continue
        if d.mode == "os":
            last = None
            continue
        if d.speaker == last:
            continue
        last = d.speaker
        out.append(_sentence(f"{name} talks{', ' + delivery if delivery else ''}, "
                             f"mouth moving with the words"))
    return out


def shot_parts(shot, seq, series_cfg: dict) -> dict:
    """The parts of the prose prompt for one shot, with no sound: the lines as silent
    acting (targets.prompt_template.PARTS)."""
    return {**scene_parts(shot, seq, series_cfg),
            "lines": " ".join(acting(shot, series_cfg.get("subjects", {}))),
            "spoken": "", "sound": "", "sound_words": "", "music": "", "music_words": ""}


def build_prompt(shot, seq, series_cfg: dict) -> str:
    """The prose prompt for one shot (`shot` an core.ir.Shot, `seq` its
    ir.Sequence), as the silent prose profile words it."""
    return TP.render(TP.profile("prose_silent")["template"], shot_parts(shot, seq, series_cfg))
