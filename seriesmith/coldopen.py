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

from seriesmith.core.paths import show_file
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
    assemble lays it; None without a cold open), "marked" (every shot the script marks, in
    the cut or not: the timeline's badges), "crossing" (the music items of the pass's mix that
    play across the break, [{"id", "label"}]: a master cuts them there)}. Shots with no usable
    take are left out of the run, as assemble leaves them."""
    story = R.episode_story(root)
    marked = flags(story) if story else {}
    out = {"shots": [], "end": None, "frame": None, "seconds": None, "gaps": [], "error": None,
           "frames": None, "marked": [k for k, v in marked.items() if v], "crossing": []}
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
        out["error"] = (f"every shot with a take in the {pass_} cut is in the cold open, so the titles "
                        f"would have nothing after them" + (" (render the shots after it in this pass)"
                                                            if len(order) < len(marked) else ""))
        return out
    if layout[i].get("dissolve_in"):
        out["error"] = (f"{order[i]} dissolves in from {run[-1]}, the cold open's last shot: the "
                        f"titles go in on a cut, so take the dissolve out there")
        return out
    origins = MX.shot_origins(layout)
    o = origins[order[i]]
    frame = o["origin"] + o["first"]
    out.update(frame=frame, seconds=round(frame / fps, 6),
               crossing=crossing(root, pass_, frame, origins, fps))
    return out


def crossing(root: str, pass_: str, frame: int, origins: dict, fps: float) -> list[dict]:
    """The music items of the pass's mix that play across cut frame `frame` (a cold open's
    end): [{"id", "label"}]. An item with no out point runs to its file's end (a wav's header;
    another kind of file, when it can't be read, isn't counted)."""
    import os
    import wave
    try:
        mix = MX.check(MX.load(root).get(pass_))
    except ValueError:
        return []
    ks = MX.kinds(mix)
    out = []
    for item in mix.get("items") or []:
        if ks.get(item.get("track")) != "music" or item.get("mute"):
            continue
        s = MX.place(item["in"], origins)
        e = MX.place(item["out"], origins) if item.get("out") else None
        if s is None:
            continue
        if e is None and not item.get("out"):
            try:
                with wave.open(show_file(root, item["path"]), "rb") as w:
                    secs = w.getnframes() / float(w.getframerate())
                e = s + round(max(0.0, secs - float(item.get("offset") or 0.0)) * fps)
            except (OSError, EOFError, wave.Error):
                continue
        if e is not None and s < frame < e:
            out.append({"id": item["id"], "label": item.get("label") or item["id"]})
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


def file_shots(path: str, fps: float) -> list[dict]:
    """An assembled cut's shot list (assemble writes `<cut>_shots.txt` beside every cut it
    makes, a master's too): [{"id", "start" (its first frame in the file), "frames"}] in the
    file's order. [] when there's none."""
    out = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                parts = line.split()
                if not parts or line.lstrip().startswith("#") or len(parts) < 4:
                    continue
                h, m, s = parts[0].split(":")
                secs = int(h) * 3600 + int(m) * 60 + float(s)
                out.append({"id": parts[1], "start": round(secs * fps), "frames": int(parts[3])})
    except (OSError, ValueError):
        return []
    return out


def split_in_file(root: str, shots_txt: str, fps: float) -> int | None:
    """Where the intro goes in an assembled cut, read from its own shot list (`file_shots`):
    the first frame of the shot after the cold open, as the file has it (a take shorter than
    its record is laid as the file is, so the cut's plan can be a frame or three off). None
    without a cold open. ColdOpenError for a gap, a dissolve across the break, every shot
    marked, or a cut with no shot list."""
    story = R.episode_story(root)
    marked = flags(story) if story else {}
    if not any(marked.values()):
        return None
    rows = file_shots(shots_txt, fps)
    if not rows:
        raise ColdOpenError(f"the cut has no shot list beside it ({shots_txt}): export it again")
    i = 0
    while i < len(rows) and marked.get(rows[i]["id"]):
        i += 1
    gaps = [r["id"] for r in rows[i:] if marked.get(r["id"])]
    if gaps:
        raise ColdOpenError(f"{', '.join(gaps)} marked cold open but play after "
                            f"{rows[i]['id']}, which isn't: right-click the last shot it should "
                            f"hold, Cold open ends here")
    if i == 0:
        return None
    if i == len(rows):
        raise ColdOpenError("every shot in the cut is marked cold open: the titles would have "
                            "nothing after them")
    last, nxt = rows[i - 1], rows[i]
    if nxt["start"] < last["start"] + last["frames"]:
        raise ColdOpenError(f"{nxt['id']} dissolves in from {last['id']}, the cold open's last "
                            f"shot: the titles go in on a cut, so take the dissolve out there")
    return nxt["start"]
