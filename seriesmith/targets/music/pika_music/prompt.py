"""
pika_music: Pika Music on Comfy Router (target.json beside this file). It takes a
description, lyrics and a length, so the cue is one paragraph as Stable Audio 3's is (its
head with the tempo in words, the script's music: notes as its mood, the sections told as a
story); a song's lyrics are its sections' lines under their tags, a score cue sends none.
cue.hosted_call puts each value where target.json's `router.inputs` says.

Stdlib only.
"""
from __future__ import annotations

from seriesmith.targets.music import common as C


def cue_prompt(target, cue: dict) -> dict:
    return {"prompt": C.described(cue), "negative": None,
            "values": {"lyrics": C.tagged_lyrics(cue), "seconds": round(float(cue["seconds"]), 3)}}
