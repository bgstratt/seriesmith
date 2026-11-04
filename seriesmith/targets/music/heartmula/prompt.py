"""
heartmula: HeartMuLa 3B (target.json beside this file). It takes tags and lyrics only: the
tags are the cue's head and the script's music: notes, comma-separated and lower case as its
examples write them; the lyrics its own section tags ([Verse], [Chorus]...) each followed
by the section's lines. It has no tempo, key or length input of its own: they're tags, and
the length is a cap (it ends when the song does).

Stdlib only.
"""
from __future__ import annotations

import math

from seriesmith.targets.music import common as C


def tags(cue: dict) -> str:
    words = C.head(cue, bpm_in_text=True).rstrip(".").split(",") + C.notes(cue).split(";")
    return ",".join(dict.fromkeys(w.strip().lower() for w in words if w.strip()))


def lyrics(cue: dict) -> str:
    """Its section tags, each with the section's lines (one without lines its tag alone: an
    instrumental passage); "" when no section has lines, which a song is refused for."""
    if not any((s.get("lyrics") or "").strip() for s in cue.get("sections") or []):
        return ""
    out = []
    for s in cue.get("sections") or []:
        name = " ".join((s.get("name") or "section").split()).title()
        lines = [ln.strip() for ln in (s.get("lyrics") or "").splitlines() if ln.strip()]
        out.append("\n".join([f"[{name}]"] + lines))
    return "\n\n".join(out)


def cue_prompt(target, cue: dict) -> dict:
    # its length input is whole seconds, 10 to 600 (the take is the cap, or shorter)
    secs = max(10, min(600, math.ceil(float(cue["seconds"]))))
    return {"prompt": tags(cue), "negative": None, "values": {"lyrics": lyrics(cue), "seconds": secs}}
