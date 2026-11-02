"""
h3_foley (target.json beside this file): H3 FL2VA asked for the sound of the video it is
given. The prompt says so first (measured 2026-11-01, docs/SOUND.md "H3 as video-to-audio"):
"The exact video given, with its sound effects only: <the shot's words>. No dialogue, no
voices, no singing, no music."; the length is the take's frames at the size it's sent.

Stdlib only.
"""
from __future__ import annotations

from seriesmith.targets.foley.common import NO_VOICES, sentence

LEAD = "The exact video given, with its sound effects only:"


def foley_prompt(target, text: str, video: dict) -> dict:
    words = sentence(text)
    return {"prompt": f"{LEAD} {words} {NO_VOICES}" if words else f"{LEAD.rstrip(':')}. {NO_VOICES}",
            "negative": None,
            "values": {"length": int(video["frames"]), "width": int(video["width"]),
                       "height": int(video["height"])}}
