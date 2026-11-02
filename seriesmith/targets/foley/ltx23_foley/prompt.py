"""
ltx23_foley (target.json beside this file): the shot's words and "No dialogue, no voices, no
singing, no music." (targets/foley/common.py); the audio latent as long as the picture's
frames (LTX's 8k+1, fx.stage cuts the picture to them) at its frame rate, and the sound
unmasked over all of it.

Stdlib only.
"""
from __future__ import annotations

from seriesmith.targets.foley.common import effects_words


def foley_prompt(target, text: str, video: dict) -> dict:
    return {"prompt": effects_words(text), "negative": None,
            "values": {"frames": int(video["frames"]), "fps": float(video["fps"]),
                       # the mask's end: past the take's last frame
                       "end_time": round(float(video["seconds"]) + 1.0, 3)}}
