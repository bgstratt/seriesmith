"""
api_music: a music model on a provider of the user's own, added from its API reference
(apispec.propose, kind "music"). The cue told as one paragraph (music/common.described) is the
description; a song's lyrics, under their section tags, go in a field of their own when the model
has one (target.json `api.inputs.lyrics`), else after the description, as Eleven Music takes them.
A score cue sends no lyrics and sets the instrumental switch, when the model has one
(cue.hosted_call places every value).

Stdlib only.
"""
from __future__ import annotations

from seriesmith import targets as TG
from seriesmith.targets.music import common as C


def cue_prompt(target, cue: dict) -> dict:
    lyrics = C.tagged_lyrics(cue)
    own_field = bool((TG.hosted_block(target.spec).get("inputs") or {}).get("lyrics"))
    text = C.described(cue)
    if lyrics and not own_field:
        text += f"\n\nLyrics:\n{lyrics}"
    # the lyrics ride along either way: cue.hosted_call places them only in a field of their own,
    # and a song's turns the instrumental switch off whichever way they go
    return {"prompt": text, "negative": None,
            "values": {"lyrics": lyrics, "seconds": round(float(cue["seconds"]), 3)}}
