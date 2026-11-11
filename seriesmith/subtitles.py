"""
subtitles.py — the cut's lines as subtitles (SRT and WebVTT), written beside the export by
assemble and carried, shifted by the intro, by publish (docs/EDITOR.md "Subtitles").

Each speaking clip's lines (the script's, lines.script_shots) are timed by the words heard in
the sound the clip plays: its take's own (takecheck's word check leaves `<sound>.words.json`
beside it) or the recording it's dubbed to (align leaves one beside the recording), matched
to the lines in order (align.align_lines), then placed on the cut (`clip_time`). A clip
whose sound hasn't been heard spreads its lines over its span by their length. Every cue is
kept inside its clip, at least MIN_SECONDS long where the clip allows, and never over the
next one.

    cues(root, plan, origins, fps) -> [{"start", "end", "text", "shot", "timed"}]
    write(base, cues) -> [paths]          base.srt and base.vtt
    shifted(cues, seconds) -> cues        publish: the intro before them

Stdlib only.
"""
from __future__ import annotations

import os

from seriesmith.core import fileio as F

MIN_SECONDS = 0.8
GAP = 0.04                       # seconds kept between two cues
MAX_LINE = 42                    # characters a subtitle line holds (the common broadcast rule)


def _words(path: str | None) -> list[dict] | None:
    if not path:
        return None
    from seriesmith import edit as E
    if not E.has_words(path):
        return None
    got = F.read_json_or(E.words_cache(path), None, want=list)
    return got or None


def clip_source(p: dict, origin: dict, fps: float) -> tuple[str | None, float, float, float]:
    """(the file a clip's sound plays from, the cut's second its time 0 lands on, and the
    clip's start and end in the cut, seconds). A dubbed clip plays its source from `start`
    (shifted by `offset`); a clip of its own sound plays its take from the take's frame 0."""
    a = (origin["origin"] + origin["first"]) / fps
    b = a + origin["used"] / fps
    if p.get("sourced") or p.get("audio_spec"):
        spec = p.get("audio_spec") or {}
        offset = float(spec.get("offset") or 0.0)
        start = float(spec.get("start") or 0.0) + max(0.0, -offset)
        return p.get("audio_src"), a + max(0.0, offset) - start, a, b
    return p.get("wav") or p.get("base"), origin["origin"] / fps, a, b


def wrap(text: str) -> str:
    """At most two lines of about MAX_LINE characters, split at the space nearest the middle."""
    t = " ".join(text.split())
    if len(t) <= MAX_LINE:
        return t
    mid = len(t) // 2
    cut = min((i for i, ch in enumerate(t) if ch == " "), key=lambda i: abs(i - mid), default=None)
    return t if cut is None else t[:cut] + "\n" + t[cut + 1:]


def cues(root: str, plan: list[dict], origins: dict, fps: float) -> list[dict]:
    from seriesmith import align as AL
    from seriesmith import lines as LN
    by_shot = {s["id"]: s["lines"] for s in LN.script_shots(root)}
    out = []
    for p in plan:
        lines = [dict(ln) for ln in by_shot.get(p["id"]) or []]
        o = origins.get(p["id"])
        if not lines or o is None:
            continue
        src, zero, a, b = clip_source(p, o, fps)
        words = _words(src)
        timed = False
        if words:
            # only the words the clip plays
            inside = [w for w in words if a - 0.25 <= zero + float(w["start"]) <= b + 0.25]
            if inside:
                AL.align_lines(lines, inside)
                timed = all(not ln.get("estimated") for ln in lines)
                for ln in lines:
                    ln["start"], ln["end"] = zero + float(ln["start"]), zero + float(ln["end"])
        if not timed:
            total = sum(max(1, len(ln["text"])) for ln in lines)
            t = a
            for ln in lines:
                d = (b - a) * max(1, len(ln["text"])) / total
                ln["start"], ln["end"], t = t, t + d, t + d
        for ln in lines:
            s, e = max(a, ln["start"]), min(b, ln["end"])
            if e - s < MIN_SECONDS:
                e = min(b, s + MIN_SECONDS)
            if e > s:
                out.append({"start": s, "end": e, "text": wrap(ln["text"]), "shot": p["id"],
                            "timed": timed})
    out.sort(key=lambda c: c["start"])
    for c, nxt in zip(out, out[1:]):
        c["end"] = min(c["end"], nxt["start"] - GAP) if nxt["start"] - GAP > c["start"] else c["end"]
    return out


def shifted(cs: list[dict], seconds: float) -> list[dict]:
    return [{**c, "start": c["start"] + seconds, "end": c["end"] + seconds} for c in cs]


def _stamp(t: float, sep: str) -> str:
    ms = max(0, round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def srt(cs: list[dict]) -> str:
    return "".join(f"{i}\n{_stamp(c['start'], ',')} --> {_stamp(c['end'], ',')}\n{c['text']}\n\n"
                   for i, c in enumerate(cs, 1))


def vtt(cs: list[dict]) -> str:
    return "WEBVTT\n\n" + "".join(f"{_stamp(c['start'], '.')} --> {_stamp(c['end'], '.')}\n{c['text']}\n\n"
                                  for c in cs)


def write(base: str, cs: list[dict]) -> list[str]:
    """`base`.srt and `base`.vtt (UTF-8, LF); none when there are no cues (an old pair removed)."""
    paths = [base + ".srt", base + ".vtt"]
    if not cs:
        for p in paths:
            if os.path.isfile(p):
                os.remove(p)
        return []
    F.write_text(paths[0], srt(cs))
    F.write_text(paths[1], vtt(cs))
    return paths


def read_srt(path: str) -> list[dict]:
    """An SRT written by `write`, back as cues (publish shifts them)."""
    out = []
    with open(path, encoding="utf-8") as fh:
        blocks = fh.read().strip().split("\n\n")

    def sec(stamp: str) -> float:
        h, m, rest = stamp.strip().split(":")
        s, ms = rest.split(",")
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000
    for b in blocks:
        rows = b.split("\n")
        if len(rows) >= 3 and "-->" in rows[1]:
            a, z = rows[1].split("-->")
            out.append({"start": sec(a), "end": sec(z), "text": "\n".join(rows[2:])})
    return out
