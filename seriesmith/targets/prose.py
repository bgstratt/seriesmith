"""
The small pieces of English every target's prompt writer builds sentences
from (they were four copies, in the image targets, ltx2, H3 FL2VA and H3
Ref2VA). Stdlib only. Every prompt they write is in the goldens: change one
and those change.
"""
from __future__ import annotations

from seriesmith.core import framing
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


def scene_parts(shot, seq, series_cfg: dict) -> dict:
    """A shot's parts that don't depend on sound (`shot` a core.ir.Shot, `seq` its
    ir.Sequence): the look, the framing and camera, who is in frame, the action and the
    on-screen text (targets.prompt_template.PARTS)."""
    book = series_cfg.get("subjects", {})
    # a description's own last full stop goes: the camera clause follows it
    # ("...long soft shadows., the camera" before; the Wan writer's rule)
    look = ((series_cfg.get("style") or {}).get("look") or "").strip().rstrip(".")
    loc = series_cfg.get("locations", {}).get(shot.plate or seq.location, {})
    env = (loc.get("description") or "").strip().rstrip(".")

    def name_of(s: str) -> str:
        return (book.get(s) or {}).get("name", s)

    # camera first: the framing, where, and how the camera moves (static unless the script says)
    size = framing.term(shot.size)
    names = join_and([name_of(s) for s in shot.cast])
    cam = framing.orbit((shot.camera or "").strip().rstrip("."), names)
    camera = f"the camera {cam}" if cam else "the camera remains static"

    # who is in frame, in words
    on_screen = list(shot.cast) + [p for p in shot.props if p not in shot.cast]
    subjects, plain = [], []
    for s in on_screen:
        design = ((book.get(s) or {}).get("design") or "").strip().rstrip(".")
        if design:
            subjects.append(sentence(subject_sentence(name_of(s), design, book.get(s) or {})))
        else:
            plain.append(name_of(s))
    if plain:
        subjects.append(sentence(f"{join_and(plain)} {'is' if len(plain) == 1 else 'are'} in frame"))
    extras = (sentence(f"Also in frame are {shot.extras}, unnamed background figures "
                       f"who look nothing like {names or 'anyone named'}") if shot.extras else "")
    return {
        "style": f"Style: {look}." if look else "",
        "framing": sentence(f"{article(size)}{' of ' + env if env else ''}, {camera}"),
        "subjects": " ".join(subjects),
        "extras": extras,
        "action": sentence(shot.action) if shot.action else "",
        "text": f'Visible on-screen text reads "{shot.text}".' if shot.text else "",
        "look": look,
        "size": size,
        "place": env,
        "camera_move": cam or "",
        "names": join_and([name_of(s) for s in on_screen]),
    }
