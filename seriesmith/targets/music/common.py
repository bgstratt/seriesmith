"""
What every music target shares (targets/music/<id>/): a cue's sections in words.

A music target's prompt.py has one function, the cue's brief:

    cue_prompt(target, cue) -> {"prompt": str, "negative": str | None, "values": {param: value}}

`cue` is what cue.plan worked out (docs/SOUND.md "From an arc to words"):

    {"style": "romantic orchestral, period strings",  the series' direction and the cue's
     "bpm": 92 (whole), "meter": 4, "key": "D minor" | "", "seconds": 52.17,
     "sections": [{"name": "intro", "bars": 4, "words": "solo french horn",
                   "from": 1, "to": 1}, ...]}       energy 1-5 at its start and end

`values` are the binding's params beyond the prompt (bpm, key, the lyrics...), set on the
graph as they are. The words for a level and for a section's direction are here, so the
two targets say the same thing in their own forms: a story (Stable Audio 3), or section
tags with a line per bar (ACE-Step).

Stdlib only.
"""
from __future__ import annotations

# energy 1-5 as words (docs/SOUND.md: sparse, quiet ... full orchestra, fortissimo)
LEVELS = {1: "very quiet, sparse", 2: "quiet", 3: "moderate", 4: "strong, full",
          5: "fortissimo, full orchestra"}


def level(x: float) -> int:
    return max(1, min(5, int(round(float(x)))))


def dynamics(sec: dict) -> str:
    """A section's energy as words: steady at one level, or rising / falling between two."""
    a, b = level(sec.get("from", 3)), level(sec.get("to", sec.get("from", 3)))
    if b > a:
        return f"rising from {LEVELS[a].split(',')[0]} to {LEVELS[b].split(',')[0]}, building"
    if b < a:
        return f"falling from {LEVELS[a].split(',')[0]} to {LEVELS[b].split(',')[0]}, receding"
    return f"{LEVELS[a]}, sustained"


def section_words(sec: dict) -> str:
    """What plays in a section and how loud: "strings enter, timpani, rising from quiet to
    strong, building"."""
    words = " ".join((sec.get("words") or "").split()).strip(" ,.")
    return ", ".join(w for w in (words, dynamics(sec)) if w)


def head(cue: dict, bpm_in_text: bool) -> str:
    """The cue's opening line: style, tempo, meter, key, instrumental."""
    bits = [" ".join((cue.get("style") or "cinematic film score").split()).strip(" ,.")]
    if bpm_in_text and cue.get("bpm"):
        bits.append(f"{int(cue['bpm'])} BPM")
    if cue.get("meter"):
        bits.append(f"{int(cue['meter'])}/4")
    if cue.get("key"):
        bits.append(cue["key"])
    bits.append("instrumental")
    return ", ".join(bits) + "."


def story(cue: dict) -> str:
    """The sections as one story, in order: "Opens with ..., then ... build in a long
    crescendo to ..., then a sudden drop to ..., ending with ...". A fall of two levels or
    more into a section is sudden; a section that rises is a crescendo."""
    secs = cue.get("sections") or []
    if not secs:
        return ""
    parts = []
    for i, s in enumerate(secs):
        words = " ".join((s.get("words") or "the ensemble").split()).strip(" ,.")
        a, b = level(s.get("from", 3)), level(s.get("to", s.get("from", 3)))
        prev = level(secs[i - 1].get("to", secs[i - 1].get("from", 3))) if i else None
        if b > a:
            what = f"{words} build in a long crescendo to {LEVELS[b]}"
        elif b < a:
            what = f"{words}, receding from {LEVELS[a].split(',')[0]} to {LEVELS[b].split(',')[0]}"
        else:
            what = f"{LEVELS[a].split(',')[0]} {words}" if a != 3 else words
        if i == 0:
            parts.append(f"Opens with {what}")
        elif prev is not None and prev - a >= 2:
            parts.append(f"then a sudden drop to {what}")
        elif i == len(secs) - 1:
            parts.append(f"ending with {what}")
        else:
            parts.append(f"then {what}")
    return ", ".join(parts) + "."
