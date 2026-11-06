"""
suno_chirp_v6: Suno v6 on Atlas Cloud (target.json beside this file). The cue told as one
paragraph, as Stable Audio 3's is, goes in as the style; a song's lyrics go separately, under
their section tags; a score cue sends none and sets the instrumental switch (cue.hosted_call).

Stdlib only.
"""
from __future__ import annotations

from seriesmith.targets.music import common as C


def cue_prompt(target, cue: dict) -> dict:
    return {"prompt": C.described(cue), "negative": None,
            "values": {"lyrics": C.tagged_lyrics(cue), "seconds": round(float(cue["seconds"]), 3)}}
