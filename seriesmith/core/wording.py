"""What a script's words ask of a model that the writer didn't mean: a thing
named only to forbid it, a person named in the action who isn't in the shot,
and words spoken in the action rather than as a line. Standard library only;
build.story_warnings reports them (`seriesmith check`, the editor's check).

A video model attends to every word of its prompt, and most have no negative
prompt to steer away from anything (H3 and FastH3 run at cfg 1). So "no
photographs on the wall" asks for photographs, and "never looks at the
camera" turns heads to it. Say what is there instead: "bare plaster walls",
"his eyes down and off to frame left".
"""

from __future__ import annotations

import re

_WORD = r"[A-Za-z][A-Za-z'’-]*"
# a negation, then up to four words: what it forbids
_NEGATION = re.compile(
    r"(?<![A-Za-z'’-])(no one|nobody|nothing|none of|no|not|never|without|neither|nor|cannot|"
    + _WORD + r"n['’]t)(?![A-Za-z'’-])((?:[ \t]+" + _WORD + r"){0,4})",
    re.IGNORECASE)
# a negation that forbids nothing: a comparison or an emphasis
_IDIOMS = ("not only", "not just", "no doubt", "no matter", "no longer than", "no more than",
           "no less than", "no sooner", "not quite", "no further than", "nothing but", "not until")
# words that don't name the thing
_FILLER = {"a", "an", "the", "any", "of", "to", "be", "is", "are", "at", "in", "on", "it", "its",
           "their", "his", "her", "and", "or", "ever", "one", "other", "more", "appear", "appears",
           "anywhere", "there", "that", "this", "with", "for", "into", "from", "even", "once",
           "again", "yet", "so", "very", "too", "much"}
# a word that starts the next clause: what was forbidden ends before it
_CLAUSE = {"and", "or", "but", "while", "then", "as", "until", "because", "when"}


def negations(text: str, limit: int = 6) -> list[str]:
    """The phrases in `text` that name a thing in order to forbid it ("no
    photographs", "never looks at the camera"), as written, in reading order,
    each once. A negation that forbids nothing (no more than, not only) is
    passed over."""
    out: list[str] = []
    seen: set[str] = set()
    for m in _NEGATION.finditer(text or ""):
        neg, rest = m.group(1), m.group(2).split()
        if any(" ".join([neg, *rest]).lower().startswith(i) for i in _IDIOMS):
            continue
        kept, thing = [], 0
        for w in rest:
            if w.lower() in _CLAUSE:
                break
            kept.append(w)
            if w.lower() not in _FILLER:
                thing += 1
                if thing == 2:
                    break
        if not thing and neg.lower() not in ("nobody", "no one", "nothing"):
            continue
        while kept and kept[-1].lower() in _FILLER:
            kept.pop()
        phrase = " ".join([neg, *kept]).strip(" ,.;:")
        if phrase.lower() not in seen:
            seen.add(phrase.lower())
            out.append(phrase)
            if len(out) == limit:
                break
    return out


def named_absent(text: str, people: dict[str, str], cast: set[str]) -> list[str]:
    """The people `text` names who aren't in `cast`. `people` maps a name as
    written (Mara) to the person it is (their subject id, a wardrobe variant
    folded into its base); `cast` holds the persons in the shot. A name
    matches as written or in capitals (a screenplay's MARA), never as a
    lowercase word (a Will is not "will"). A name that opens a longer proper
    name (Marlowe House, Mara Street) is a place, not the person, and is
    passed over."""
    out: list[str] = []
    for name, who in sorted(people.items(), key=lambda kv: -len(kv[0])):
        name = name.strip()
        if who in cast or not name or name in out:
            continue
        forms = "|".join(re.escape(f) for f in dict.fromkeys((name, name.upper())))
        pat = re.compile(r"(?<![A-Za-z])(?:" + forms + r")(?![A-Za-z])(?![ \t]+[A-Z][a-z])")
        if pat.search(text or ""):
            out.append(name)
    return out


_SPEAKING = (r"(?:says?|said|saying|asks?|asked|asking|shouts?|shouted|shouting|yells?|yelled|"
             r"yelling|whispers?|whispered|whispering|mutters?|muttered|muttering|murmurs?|"
             r"murmured|calls?|called|calling|cries|cried|crying out|screams?|screamed|replies|"
             r"replied|answers?|answered|tells?|told|sings?|sang|singing|snaps?|snapped|"
             r"barks?|barked|hisses|hissed|growls?|growled|exclaims?|exclaimed|adds?|added)")
_QUOTE = r"[\"“”]([^\"“”]{2,}?)[\"“”]"
_SPOKEN = re.compile(
    r"\b" + _SPEAKING + r"\b[^\"“”.]{0,40}?[:,]?\s*" + _QUOTE      # says, "..."
    + r"|" + _QUOTE + r"\s*,?\s*(?:[A-Za-z]+\s+){0,3}?" + _SPEAKING + r"\b",  # "...", she says
    re.IGNORECASE)


def quoted_speech(text: str) -> list[str]:
    """The words `text` has someone say in quotation marks (`he says, "Run."`,
    `"Run," she says`): spoken words belong in a dialogue line, where the
    model voices them and the cut times them. Quoted words with no speaking
    verb (a sign that reads "OPEN") are passed over."""
    out: list[str] = []
    for m in _SPOKEN.finditer(text or ""):
        said = (m.group(1) or m.group(2) or "").strip()
        if len(said.split()) >= 1 and said not in out:
            out.append(said)
    return out
