"""
elevenlabs_music: Eleven Music on ElevenLabs' own API (target.json beside this file). The cue told
as one paragraph, with a song's lyrics after it under their section tags. A score cue sets
force_instrumental (cue.hosted_call).

Stdlib only.
"""
from __future__ import annotations

from seriesmith.targets.music import common as C


def cue_prompt(target, cue: dict) -> dict:
    lyrics = C.tagged_lyrics(cue)
    text = C.described(cue) + (f"\n\nLyrics:\n{lyrics}" if lyrics else "")
    return {"prompt": text, "negative": None,
            "values": {"lyrics": lyrics, "seconds": round(float(cue["seconds"]), 3)}}
