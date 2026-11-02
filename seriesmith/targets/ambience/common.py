"""
What every ambience target shares (targets/ambience/<id>/): a place's bed in words.

An ambience target's prompt.py has one function, the bed's brief:

    ambience_prompt(target, words, seconds) -> {"prompt": str, "negative": str | None,
                                                "values": {param: value}}

`words` is the series config's `ambience` of the place (what's heard there: "Room tone of a
small roadside diner at night: a refrigerator hum, ..."), `seconds` how long a take is.
The prompt is the words and NO_VOICES: a bed is the room, never music or a line someone
says (docs/SOUND.md "Measured: ambience beds"). `negative` None: the preset's.

Stdlib only.
"""
from __future__ import annotations

NO_VOICES = "No music, no voices, no speech."


def bed_words(words: str) -> str:
    """The place's words as one sentence, then NO_VOICES."""
    text = " ".join((words or "").split()).strip()
    if text and text[-1] not in ".!?":
        text += "."
    return f"{text} {NO_VOICES}".strip()


def ambience_prompt(target, words: str, seconds: float) -> dict:
    return {"prompt": bed_words(words), "negative": None,
            "values": {"seconds": round(float(seconds), 3)}}
