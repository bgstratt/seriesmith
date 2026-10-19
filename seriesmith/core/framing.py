"""
framing.py — a shot's `size:`: the names a script may use, what each frames,
and which of three families it belongs to.

A script writes any of the names below (case, spaces and hyphens don't
matter: `MCU`, `medium close-up` and `medium-close-up` are one size). The
shot keeps the name as written, so a shotlist built before a name existed
reads the same; everything that acts on the size goes through canonical().

The family decides what the targets do with the reference images (how much of
the location plate a shot keeps, the face or body panel of a sheet), so the
new in-between sizes reuse the three families' handling:

    close    ecu, cu, mcu
    medium   ms, cowboy, mws, and the angles: pov, ots, low, high
    wide     fs, ws, ews

The angles (a POV shot, over the shoulder, from below, from above) are
framings H3's guide names beside the sizes; they say where the camera looks
from, not how much it holds, so they have no place in ORDER and two shots one
of which is an angle are never called a jump cut.

The words are what the prompt says. H3's own guide names most of these
framings; for the ones it doesn't (cowboy, full, extreme wide) the extent
says in plain words what the frame holds, so a model that doesn't know the
term still frames it.

Stdlib only.
"""
from __future__ import annotations

import re

# canonical size: (term, how much of the subject it holds or None, family)
SIZES = {
    "ecu":    ("extreme close-up", "a single detail filling the frame", "close"),
    "cu":     ("close-up", None, "close"),
    "mcu":    ("medium close-up", "from the chest up", "close"),
    "ms":     ("medium shot", None, "medium"),
    "cowboy": ("cowboy shot", "from mid-thigh up", "medium"),
    "mws":    ("medium-wide shot", "from the knees up", "medium"),
    "fs":     ("full shot", "from head to toe", "wide"),
    "ws":     ("wide shot", None, "wide"),
    "ews":    ("extreme wide shot", "small within the vastness of the setting", "wide"),
    "pov":    ("POV shot", "seen through another character's own eyes", "medium"),
    "ots":    ("over-the-shoulder shot", "past the shoulder of the person facing them", "medium"),
    "low":    ("low-angle shot", "seen from below, the camera looking up", "medium"),
    "high":   ("high-angle shot", "seen from above, the camera looking down", "medium"),
}

# every name a script may write, normalised (see _key), to its canonical size
ALIASES = {
    "ecu": "ecu", "xcu": "ecu", "extremecloseup": "ecu", "extremeclose": "ecu",
    "cu": "cu", "close": "cu", "closeup": "cu",
    "mcu": "mcu", "mediumcloseup": "mcu", "mediumclose": "mcu",
    "ms": "ms", "medium": "ms", "mediumshot": "ms", "mid": "ms", "midshot": "ms",
    "cowboy": "cowboy", "cowboyshot": "cowboy", "americanshot": "cowboy",
    "mws": "mws", "mediumwide": "mws", "mediumwideshot": "mws", "mls": "mws",
    "mediumlong": "mws", "mediumlongshot": "mws",
    "fs": "fs", "full": "fs", "fullshot": "fs",
    "ws": "ws", "wide": "ws", "wideshot": "ws", "ls": "ws", "long": "ws", "longshot": "ws",
    "ews": "ews", "xws": "ews", "els": "ews", "xls": "ews", "extremewide": "ews",
    "extremewideshot": "ews", "extremelong": "ews", "extremelongshot": "ews",
    "pov": "pov", "povshot": "pov", "pointofview": "pov", "pointofviewshot": "pov",
    "ots": "ots", "overtheshoulder": "ots", "overtheshouldershot": "ots", "overshoulder": "ots",
    "low": "low", "lowangle": "low", "lowangleshot": "low", "lowshot": "low",
    "high": "high", "highangle": "high", "highangleshot": "high", "highshot": "high",
}

FAMILIES = ("close", "medium", "wide")

# tightest to widest: how far apart two sizes are (steps_apart); the angles aren't distances
ORDER = ("ecu", "cu", "mcu", "ms", "cowboy", "mws", "fs", "ws", "ews")
ANGLES = ("pov", "ots", "low", "high")


def _key(name: str) -> str:
    return re.sub(r"[^a-z]", "", (name or "").lower())


def canonical(name: str | None) -> str | None:
    """The canonical size a script name means ("Medium close-up" -> "mcu"),
    or None when it isn't one."""
    return ALIASES.get(_key(name or ""))


def is_size(name: str | None) -> bool:
    return canonical(name) is not None


def family(name: str | None, default: str = "medium") -> str:
    """close, medium or wide; `default` for a size that isn't one (an old or
    hand-edited shotlist)."""
    c = canonical(name)
    return SIZES[c][2] if c else default


def term(name: str | None, default: str = "medium shot") -> str:
    """The framing's name in words: "medium close-up"."""
    c = canonical(name)
    return SIZES[c][0] if c else default


def extent(name: str | None) -> str | None:
    """What the frame holds of the subject ("from the chest up"), or None for
    the three sizes whose name says it."""
    c = canonical(name)
    return SIZES[c][1] if c else None


def article(words: str) -> str:
    """'A medium shot', 'An extreme close-up'."""
    return ("An " if words[:1].lower() in "aeiou" else "A ") + words


def in_sizes(name: str | None, names) -> bool:
    """Whether `name` is one of `names` (a target's face_sizes, say), any
    spelling of either."""
    c = canonical(name)
    return c is not None and c in {canonical(n) for n in (names or ())}


def steps_apart(a: str | None, b: str | None) -> int | None:
    """How many sizes apart two framings are (mws and mcu: 3), or None when
    either isn't a size. Two shots of the same people on the same plate want
    two or more, or the cut reads as a jump cut. None too when either is an
    angle (pov, ots, low, high): a change of angle is a cut of its own."""
    ca, cb = canonical(a), canonical(b)
    if ca is None or cb is None or ca in ANGLES or cb in ANGLES:
        return None
    return abs(ORDER.index(ca) - ORDER.index(cb))


# `lens:` (a shot's, or its sequence's for all its shots): the look builder's
# Lens row (seriesmith/presets/look_builder.json, the same clauses; a test keeps
# them alike). The shot's action opens with it (lens_sentence),
# so every model reads it. Shallow focus shows the most; with a plate as the
# reference, the plate fixes the geometry and the rest show less.
LENSES = {
    "spherical": "spherical lenses: true geometry, round bokeh",
    "anamorphic": "anamorphic lenses: oval bokeh, horizontal lens flares, slight distortion at the edges",
    "vintage": "vintage lenses: soft edges, a gentle glow around the highlights, lower contrast",
    "wide": "wide-angle lenses: deep focus, the space stretched around the subject",
    "long": "long lenses: compressed depth, the background pulled close and soft",
    "shallow": "shallow depth of field: the subject sharp, the background falling into soft bokeh",
    "tilt_shift": "tilt-shift lenses: a thin plane of focus that makes the world look miniature",
    "deep": "deep focus: everything sharp from the foreground to the far distance",
}


def lens(name: str | None) -> str | None:
    """A `lens:` value's id (tilt-shift and tilt_shift alike), or None."""
    k = (name or "").strip().lower().replace("-", "_").replace(" ", "_")
    return k if k in LENSES else None


def lens_sentence(name: str) -> str:
    """The sentence a shot's action opens with for `lens: name`."""
    c = LENSES[lens(name)]
    return c[0].upper() + c[1:] + "."


def describe() -> str:
    """The sizes and their short names, for an error message."""
    short = {c: [a for a, v in ALIASES.items() if v == c and len(a) <= 6] for c in SIZES}
    return ", ".join(f"{SIZES[c][0]} ({'/'.join(dict.fromkeys([c] + short[c]))})"
                     for c in SIZES)
