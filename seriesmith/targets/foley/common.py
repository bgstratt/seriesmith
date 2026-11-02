"""
What every foley target shares (targets/foley/<id>/): a shot's effects in words.

A foley target's prompt.py has one function, the take's brief:

    foley_prompt(target, text, video) -> {"prompt": str, "negative": str | None,
                                          "values": {param: value}}

`text` is what the shot sounds like: its script `sound:` line, else its action (seriesmith/fx.py
shot_text). `video` is the take's picture as it goes to the model (fx.stage):
{"frames", "fps", "seconds", "width", "height"}. The prompt is the text and NO_VOICES: the
effects track is sync sound, never a line, a song or score (docs/SOUND.md phase 4).
`negative` None: the preset's. `values` are the binding's params beyond the prompt (the
length, the frame rate), set on the graph as they are.

Stdlib only.
"""
from __future__ import annotations

NO_VOICES = "No dialogue, no voices, no singing, no music."


def sentence(text: str) -> str:
    """`text` on one line, ending in a full stop."""
    t = " ".join((text or "").split()).strip()
    if t and t[-1] not in ".!?":
        t += "."
    return t


def effects_words(text: str) -> str:
    """The shot's words, then NO_VOICES."""
    return f"{sentence(text)} {NO_VOICES}".strip()


def foley_prompt(target, text: str, video: dict) -> dict:
    """The words, and the take's length in seconds at its frame rate (a model that takes
    seconds and a frame rate: HunyuanVideo-Foley)."""
    return {"prompt": effects_words(text), "negative": None,
            "values": {"seconds": round(float(video["seconds"]), 3), "fps": float(video["fps"])}}
