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


def lyrics(cue: dict) -> str:
    if cue.get("kind") != "song":
        return ""
    out = []
    for s in cue.get("sections") or []:
        lines = [ln.strip() for ln in (s.get("lyrics") or "").splitlines() if ln.strip()]
        if lines:
            name = " ".join((s.get("name") or "section").split()).title()
            out.append("\n".join([f"[{name}]"] + lines))
    return "\n\n".join(out)


def cue_prompt(target, cue: dict) -> dict:
    mood = C.notes(cue)
    text = " ".join(x for x in (C.head(cue, bpm_in_text=True), f"Mood: {mood}." if mood else "",
                                C.story(cue)) if x)
    return {"prompt": text, "negative": None,
            "values": {"lyrics": lyrics(cue), "seconds": round(float(cue["seconds"]), 3)}}
