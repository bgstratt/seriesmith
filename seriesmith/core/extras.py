"""
A shot's `extras:` read as people: how many it names, and which of them come back in other
shots (stdlib only: the build's warnings and the count check both use it).

    people(text) -> [(n, words)] | None    each person or group the line names, with how many;
                                           None when its words leave the number open
    count(text) -> n | None                how many people in all
    recurring(shots) -> [[(shot, words)]]  the same people named in two shots or more

An extras line names its people in parts, each starting with how many ("a night nurse in green
scrubs", "two paramedics in dark uniforms"), joined by "and", ";" or a comma before the next
"a"/"two"/.... A part after a plural one that only describes its members ("two guards, a man and
a woman") is the same people, not more. Crowds ("day-shift nurses", "a few", "a dozen") leave
the number open: they are background, and never recur as anyone in particular.
"""
from __future__ import annotations

import re

NUMBERS = {"a": 1, "an": 1, "one": 1, "another": 1, "single": 1, "lone": 1, "two": 2,
           "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
           "ten": 10, "pair": 2, "couple": 2}
# a number of people the words leave open
OPEN = {"few", "several", "some", "many", "dozen", "dozens", "crowd", "crowds", "group",
        "groups", "handful", "line", "row", "rows", "number", "lots", "hundreds", "scores",
        "stream", "streams", "bunch", "cluster", "knot", "throng", "gaggle", "queue", "team"}
# a part that only says what one member of the plural part before it is
MEMBER = re.compile(r"^(?:a|an|one|the other)\s+(?:[\w-]+\s+){0,3}?"
                    r"(?:man|woman|boy|girl|men|women|one)\b(?![\w ]*\b(?:in|with|at)\b)", re.I)
# "nobody else in frame": no one
NOBODY = re.compile(r"^(?:nobody|no one|no-one|none|no other|no extras|empty)\b", re.I)
_COUNT = r"(?=(?:a|an|one|two|three|four|five|six|seven|eight|nine|ten|another|the other)\b)"
# a new part starts at ";", or at "and" or a comma before how many ("small and soft" doesn't)
_PART = re.compile(r"\s*(?:;|,?\s+and\s+" + _COUNT + r"|,\s+" + _COUNT + r")\s*", re.I)
_WORD = re.compile(r"[a-z]+|\d+")

# words that say where someone is or what they're doing, not who they are: left out when two
# shots' extras are compared
_NOT_WHO = {
    "a", "an", "the", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "and", "of", "in", "on", "at", "by", "to", "with", "her", "his", "him", "their", "them", "its",
    "behind", "beside", "across", "along", "down", "up", "past", "far", "off", "away", "toward",
    "towards", "into", "out", "from", "over", "under", "near", "next", "other", "way", "edge",
    "already", "still", "just", "only", "soft", "blurred", "background", "foreground", "frame",
    "room", "corridor", "hall", "station", "door", "doors", "window", "glass", "desk", "wall",
    "chairs", "chair", "counter", "register", "street", "cars", "small", "visible", "seen", "rear", "front",
    "stretcher", "gurney", "cart", "trolley",
    "standing", "sitting", "seated", "walking", "passing", "pushing", "stepping", "waiting",
    "watching", "looking", "ringing", "hurrying", "rushing", "holding", "aside", "back",
    "camera", "sliding",
}
SAME = 0.65      # who-words in common, of all either has (Jaccard), to be the same people


def parts(text: str | None) -> list[tuple[int | None, str]]:
    """[(how many, the part's words)] for each person or group an extras line names; the number
    None when the part's words leave it open ("day-shift nurses", "a few", "a dozen")."""
    text = (text or "").strip()
    out: list[tuple[int | None, str]] = []
    absorb, listed = 0, False        # members of the plural part before, still to say; said after ":"
    for part in _PART.split(text):
        words = _WORD.findall(part.lower())
        if not words or NOBODY.match(part.strip()):
            continue
        if absorb and (MEMBER.match(part.strip()) or (listed and words[0] in ("a", "an", "one"))):
            absorb -= 1
            continue
        absorb = 0
        n: int | None
        if any(w in OPEN for w in words[:3]):
            n = None
        elif words[0].isdigit():
            n = int(words[0])
        elif words[0] in NUMBERS:
            n = NUMBERS[words[0]]
            if words[0] in ("a", "an") and len(words) > 1 and words[1] in ("pair", "couple"):
                n = 2
        else:
            n = None                             # "nurses passing", "the shoulders of ..."
        out.append((n, part.strip()))
        if n and n > 1:
            # "three plant workers: an older man ..., a young woman ..." lists its members
            listed = ":" in part
            absorb = n - 1 if listed else n
    return out


def people(text: str | None) -> list[tuple[int, str]] | None:
    """parts(), when every part says how many; [] for none; None when one leaves it open."""
    got = parts(text)
    if any(n is None for n, _ in got):
        return None
    return [(n, p) for n, p in got]                     # type: ignore[misc]


def count(text: str | None) -> int | None:
    """How many people an extras line names: 0 for none, None when its words leave it open."""
    got = people(text)
    return None if got is None else sum(n for n, _ in got)


# what a who-phrase passes over ("a night nurse in teal scrubs": "a", "in")
_SKIP = set(NUMBERS) | OPEN | {"the", "in", "with", "of", "wearing", "and", "all", "her", "his",
                               "their", "its", "other", "nearest", "who"}


# words ending in -ing that are things, not doing
_ING_NOUNS = {"wearing", "housekeeping", "clothing", "building", "ceiling", "morning", "evening",
              "wedding", "bedding", "stocking", "stockings", "earring", "earrings", "lining",
              "padding", "trimming", "piping", "dining", "nursing", "shipping", "parking"}


def _stops(t: str) -> bool:
    """A word that says where someone is or what they're doing: the who-phrase ends there."""
    return (t in ",:;" or t in _NOT_WHO - _SKIP
            or (t.endswith("ing") and len(t) > 4 and t not in _ING_NOUNS))


def who_phrase(part: str) -> str:
    """A part's opening phrase as written ("a night nurse in teal scrubs"), up to where they are
    or what they're doing ("passing in the corridor ...") or the first comma."""
    end, kept = 0, False
    for m in re.finditer(r"[A-Za-z]+|\d+|[,:;]", part):
        t = m.group().lower()
        if _stops(t):
            if kept:
                break
            continue
        if not (t in _SKIP or t.isdigit()):
            end, kept = m.end(), True
    return part[:end].strip()


def who_words(part: str) -> set[str]:
    """The words of who_phrase that say who they are ("night", "nurse", "teal", "scrubs")."""
    return {t for t in re.findall(r"[a-z]+|\d+", who_phrase(part).lower())
            if t not in _SKIP and not t.isdigit()}


def same_people(a: str, b: str) -> bool:
    """Whether two parts name the same people: their who-words mostly the same (SAME, of all
    either has), or one's three or more all in the other's ("day-shift nurses" and "day-shift
    nurses in colorful scrubs")."""
    wa, wb = who_words(a), who_words(b)
    if len(wa) < 2 or len(wb) < 2:
        return False
    small, big = sorted((wa, wb), key=len)
    if len(small) >= 3 and small <= big:
        return True
    return len(wa & wb) / len(wa | wb) >= SAME


def recurring(shots: list[tuple]) -> list[list[tuple[str, str]]]:
    """The people that recur: of [(shot id, its extras[, its place])], each person, group or
    crowd named in two shots or more at the same place (any, when no place is given), as
    [(shot id, the part)], in script order. Described the same way twice, they're meant to be
    the same people, and a model draws them afresh each time."""
    seen: list[tuple[object, list[tuple[str, str]]]] = []
    for sid, text, *where in shots:
        place = where[0] if where else None
        for _, part in parts(text):
            for at, group in seen:
                if at == place and any(same_people(p, part) for _, p in group):
                    if group[-1][0] != sid:
                        group.append((sid, part))
                    break
            else:
                seen.append((place, [(sid, part)]))
    return [g for _, g in seen if len(g) > 1]


__all__ = ["count", "parts", "people", "recurring", "same_people", "who_phrase", "who_words"]
