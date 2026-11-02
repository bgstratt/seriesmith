"""
stable_audio3: Stable Audio 3 Medium (target.json beside this file). It takes text and a
length, so the cue is one paragraph: its head (style, the tempo in words, meter, key), the
script's music: notes as its mood, and its sections told as a story, which it followed far
better than timestamps (docs/SOUND.md "Measured: Stable Audio 3 Medium").

Stdlib only.
"""
from __future__ import annotations

from seriesmith.targets.music import common as C


def cue_prompt(target, cue: dict) -> dict:
    mood = C.notes(cue)
    text = " ".join(x for x in (C.head(cue, bpm_in_text=True), f"Mood: {mood}." if mood else "",
                                C.story(cue)) if x)
    return {"prompt": text, "negative": None, "values": {"seconds": round(float(cue["seconds"]), 3)}}
