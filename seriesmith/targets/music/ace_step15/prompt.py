"""
ace_step15: ACE-Step 1.5 XL (target.json beside this file). Its tags are the cue's head
without the tempo (the bpm is its own input) and the script's music: notes; its lyrics are
the sections as its own tags, each followed by one line per bar carrying the section's
words, which timed sections best and made the climax loudest (docs/SOUND.md "Measured: ACE-Step 1.5 XL Turbo"); a song's
lyrics, when a section has them, are its lines instead.

Stdlib only.
"""
from __future__ import annotations

from seriesmith.targets.music import common as C

# the keys TextEncodeAceStepAudio1.5 offers (its `keyscale` combo): a note and major/minor
NOTES = ("C", "C#", "Db", "D", "D#", "Eb", "E", "F", "F#", "Gb", "G", "G#", "Ab", "A", "A#",
         "Bb", "B")


def keyscale(key: str) -> str | None:
    """The cue's key as the node's combo spells it ("D minor"), or None when it isn't one."""
    parts = (key or "").split()
    if len(parts) != 2:
        return None
    note = parts[0][0].upper() + parts[0][1:]
    mode = parts[1].lower()
    return f"{note} {mode}" if note in NOTES and mode in ("major", "minor") else None


def lyrics(cue: dict) -> str:
    out = []
    for s in cue.get("sections") or []:
        name = " ".join((s.get("name") or "section").split()).title()
        out.append(f"[{name}]")
        own = [ln.strip() for ln in (s.get("lyrics") or "").splitlines() if ln.strip()]
        if own:
            out += own
        else:
            out += [f"({C.section_words(s)})"] * max(1, int(s.get("bars") or 1))
    return "\n".join(out) or "[Instrumental]"


def cue_prompt(target, cue: dict) -> dict:
    values = {"lyrics": lyrics(cue), "bpm": int(cue.get("bpm") or 120),
              "seconds": round(float(cue["seconds"]), 3),
              "timesignature": str(int(cue.get("meter") or 4))}
    k = keyscale(cue.get("key") or "")
    if k:
        values["keyscale"] = k
    tags = ", ".join(x for x in (C.head(cue, bpm_in_text=False).rstrip("."), C.notes(cue)) if x)
    return {"prompt": tags, "negative": None, "values": values}
