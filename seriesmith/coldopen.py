"""
coldopen: the shots that play before the opening titles (docs/TITLES_GUIDE.md).

The script marks them: `cold_open: true` under a `#` header (every shot of the sequence) or on
a `## shot` (that shot; `cold_open: false` takes one out of its sequence's). They are the cut's
first shots, one after another: a master (and Titles) puts the series intro in right after the
last of them, else at the start. The cut decides the order, so the run is read in cut order:
a marked shot after one that isn't is a gap, and a master is refused until it's fixed (the
editor's "Cold open ends here" rewrites the marks to the cut as it is).

`state` is what the editor shows and master reads; `set_end` writes the marks.
"""
from __future__ import annotations

import re

from seriesmith import cue as CU
from seriesmith import edit as E
from seriesmith import mix as MX
from seriesmith import refs as R
from seriesmith import source as H

KEY_LINE = re.compile(r"^\s*cold_open\s*:")


class ColdOpenError(Exception):
    pass


def flags(story) -> dict[str, bool]:
    """{shot id: whether it's in the cold open} for every shot of the story IR."""
    return {sh.id: sh.in_cold_open(sq) for sq in story.sequences for sh in sq.shots}


def state(root: str, pass_: str) -> dict:
    """The cold open against the pass's cut: {"shots" (the run, in cut order), "end" (its
    last shot, None for none), "frame" and "seconds" (where the titles go in the assembled
    cut; None without a cold open), "gaps" (marked shots that play after one that isn't),
    "error" (why a master can't put the titles in, else None), "frames" (the cut's length as
    assemble lays it, to check a file against; None without a cold open)}. Shots with no usable take
    are left out, as assemble leaves them."""
    story = R.episode_story(root)
    marked = flags(story) if story else {}
    out = {"shots": [], "end": None, "frame": None, "seconds": None, "gaps": [], "error": None,
           "frames": None}
    if not any(marked.values()):
        return out
    layout, fps = CU.cut_layout(root, pass_)
    order = [p["id"] for p in layout]
    out["frames"] = sum(p["used"] - p.get("dissolve_in", 0) for p in layout)
    i = 0
    while i < len(order) and marked.get(order[i]):
        i += 1
    run, gaps = order[:i], [s for s in order[i:] if marked.get(s)]
    out.update(shots=run, end=run[-1] if run else None, gaps=gaps)
    if gaps:
        first = order[i] if i < len(order) else None
        out["error"] = (f"{', '.join(gaps)} {'is' if len(gaps) == 1 else 'are'} marked cold open but "
                        f"play{'s' if len(gaps) == 1 else ''} after {first}, which isn't: the cold "
                        f"open is the cut's first shots, one after another. Right-click the last "
                        f"shot it should hold, Cold open ends here")
        return out
    if not run:
        return out
    if i == len(order):
        out["error"] = "every shot in the cut is marked cold open: the titles would have nothing after them"
        return out
    if layout[i].get("dissolve_in"):
        out["error"] = (f"{order[i]} dissolves in from {run[-1]}, the cold open's last shot: the "
                        f"titles go in on a cut, so take the dissolve out there")
        return out
    o = MX.shot_origins(layout)[order[i]]
    frame = o["origin"] + o["first"]
    out.update(frame=frame, seconds=round(frame / fps, 6))
    return out


def set_end(root: str, pass_: str, end: str | None) -> dict:
    """Mark the cold open as the pass's cut has it: every shot from the cut's first to `end`
    (None: no cold open). A `#` header whose shots are all in it gets `cold_open: true`, the
    rest of them each their own line; every other `cold_open:` line goes. The script is
    written with a history copy (source.write_source) only when it changes. Returns
    {"shots", "changed"}."""
    entries = [e for e in E.cut_entries(root, pass_) if not e.orphan and not e.out]
    order = [e.shot for e in entries]
    if end is not None and end not in order:
        raise ColdOpenError(f"{end} isn't in the {pass_} cut")
    want = set(order[:order.index(end) + 1]) if end is not None else set()
    src = H.read_source(root, "script")
    lines = [ln for ln in src.text.split("\n") if not KEY_LINE.match(ln)]
    text = "\n".join(lines)
    ids = H._ids(H._load_cfg(root))
    from seriesmith.core.story import ScriptError, _parse
    try:
        ep, seq_lines, spans = _parse(text, *ids) if ids else (None, [], {})
    except ScriptError as e:
        raise ColdOpenError(f"the script doesn't parse: {e}") from None
    if ep is None:
        raise ColdOpenError("the series config doesn't load")
    heads, shots = [], {}
    for sq, line in zip(ep["sequences"], seq_lines):
        ids_in = [sh["id"] for sh in sq["shots"]]
        if ids_in and all(s in want for s in ids_in):
            heads.append(line)
        else:
            shots.update({s: [("cold_open", "true")] for s in ids_in if s in want})
    from seriesmith import promote as P
    if shots:
        text = P.edit_script(text, spans, shots)
        _, seq_lines, _ = _parse(text, *ids)
        heads = [ln for sq, ln in zip(ep["sequences"], seq_lines)
                 if [sh["id"] for sh in sq["shots"]] and all(sh["id"] in want for sh in sq["shots"])]
    lines = text.split("\n")
    for line in sorted(heads, reverse=True):
        lines.insert(line, "cold_open: true")
    text = "\n".join(lines)
    before = src.hash
    after = H.write_source(src, text)
    return {"shots": [s for s in order if s in want], "changed": after != before}
