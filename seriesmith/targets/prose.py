"""
The small pieces of English every target's prompt writer builds sentences
from (they were four copies, in the image targets, ltx2, H3 FL2VA and H3
Ref2VA). Stdlib only. Every prompt they write is in the goldens: change one
and those change.
"""
from __future__ import annotations

from seriesmith.core.series_config import members


def sentence(text: str) -> str:
    """`text` as a sentence: capitalised, ending in . (unless it already ends
    in a stop or a quote); "" for nothing."""
    text = (text or "").strip()
    if not text:
        return ""
    text = text[0].upper() + text[1:]
    return text if text[-1] in ".!?\"'" else text + "."


def clause(text: str) -> str:
    """A series config's description, design or look as it goes inside a
    sentence: trimmed, without its own last full stop (a writer adds the
    punctuation that follows: "...long soft shadows., the camera" before)."""
    return (text or "").strip().rstrip(".").rstrip()


def join_and(items: list[str]) -> str:
    """"a", "a and b", "a, b, and c"."""
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + (", and " if len(items) > 2 else " and ") + items[-1]


def article(phrase: str) -> str:
    """"a phrase" or "an phrase", by its first letter."""
    return ("an " if phrase[:1].lower() in "aeiou" else "a ") + phrase


def subject_sentence(name: str, design: str, entry: dict) -> str:
    """"<Name> is <design>", or for a group (`members: N`) "<Name> are N
    different people, each appearing once: <design>"."""
    n = members(entry)
    if n:
        return f"{name} are {n} different people, each appearing once: {design}"
    return f"{name} is {design}"
