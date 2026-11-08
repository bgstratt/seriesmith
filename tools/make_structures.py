#!/usr/bin/env python3
"""
make_structures.py — regenerate seriesmith/core/structures.json, the story structures' Music
tables as the first-pass score reads them (seriesmith/core/spotting.py, `seriesmith
score-draft`), from docs/STORY_STRUCTURES.md: the doc is the source.

Each `### N.N <name>` with a `**Music:**` table under it (| Beat | Music | Mood (energy) |
Theme | Hit |) becomes a structure: its beats, each row read by spotting.parse_row, a beat's
names split at " / " ("Cold Open / Teaser" is either). A structure whose text after its
table speaks of a bumper (the Sitcom) gets `"bumpers": true`. Each beat's place in the story
(`"at": [from, to]`, percent) is its row's `~%` in the structure's first table that has one
(its beats in order, named in a column the Music table's names match, a name's parenthetical
dropped: "Plot Point 1 (Break into Two)" is "Plot Point 1"; a name seen again is its
"(again)"; a beat at one point, "50", gets `"point": 50` instead, and one with none, "—",
neither: spotting.layout leaves both to the beats around it). The same row gives the
storyboard (docs/PLAN.md) the beat's `"guidance"` (the column before `~%`) and, when the
table's first column is `Act`, its `"act"` (a cell left empty is the act above it).

    python tools/make_structures.py            # rewrite it
    python tools/make_structures.py --check    # exit 1 if it is out of date

tests/test_docs.py runs --check. Run it after changing a Music table. Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from seriesmith.core import spotting as SP                        # noqa: E402

DOC = os.path.join(ROOT, "docs", "STORY_STRUCTURES.md")
OUT = SP.DATA


def _plain(name: str) -> str:
    return SP.norm(re.sub(r"\s*\([^)]*\)\s*$", "", name.replace("**", "")))


def _text(cell: str) -> str:
    """A table cell without its markdown emphasis."""
    return cell.replace("*", "").strip()


def _outline(lines: list[str], start: int, beats: list[dict]) -> dict[int, dict]:
    """What the first `~%` table after `start` says of each Music-table beat (by its index):
    `guidance`, and `at` or `point` and `act` when it has them; a name that appears twice is
    the next beat of that name each time."""
    for i in range(start, len(lines)):
        if lines[i].startswith(("### ", "## ")) and i > start:
            return {}
        if not (lines[i].startswith("|") and lines[i].rstrip().endswith("~% |")):
            continue
        hdr = [c.strip() for c in lines[i].strip().strip("|").split("|")]
        rows, j = [], i + 2
        while j < len(lines) and lines[j].startswith("|"):
            rows.append([c.strip() for c in lines[j].strip().strip("|").split("|")])
            j += 1
        want: dict[str, list[int]] = {}
        for k, b in enumerate(beats):
            for n in dict.fromkeys(_plain(x) for x in b["names"]):
                want.setdefault(n, []).append(k)
        # the column whose names are the Music table's
        col = max(range(len(hdr) - 1), key=lambda k: sum(_plain(r[k]) in want for r in rows))
        out, seen = {}, {}
        act = ""
        for r in rows:
            # an Act cell left empty is the act above it
            if hdr[0] == "Act" and r[0]:
                act = _text(r[0])
            name = _plain(r[col])
            if name not in want:
                continue
            n = seen.get(name, 0)
            seen[name] = n + 1
            if n >= len(want[name]):
                continue
            entry = {"guidance": _text(r[-2])}
            if act:
                entry["act"] = act
            span = re.match(r"^(\d+)\s*[–-]\s*(\d+)$", r[-1])
            if span and int(span.group(2)) > int(span.group(1)):
                entry["at"] = [int(span.group(1)), int(span.group(2))]
            elif re.match(r"^\d+$", r[-1]):
                entry["point"] = int(r[-1])
            out[want[name][n]] = entry
        return out
    return {}


def build(text: str) -> dict:
    lines = text.splitlines()
    out = []
    for i, line in enumerate(lines):
        m = re.match(r"^###\s+(\d+\.\d+)\s+(.+?)\s*$", line)
        if not m:
            continue
        j = i + 1
        while j < len(lines) and not lines[j].startswith(("### ", "## ")) and not lines[j].startswith("**Music:**"):
            j += 1
        if j >= len(lines) or not lines[j].startswith("**Music:**"):
            continue
        k = j + 1
        while k < len(lines) and not lines[k].startswith("|"):
            if lines[k].startswith(("### ", "## ")) or lines[k].startswith("**"):
                break
            k += 1
        if k >= len(lines) or not lines[k].startswith("| Beat | Music"):
            continue
        beats = []
        k += 2
        while k < len(lines) and lines[k].startswith("|"):
            cells = [c.strip() for c in lines[k].strip().strip("|").split("|")]
            beat = cells[0].replace("**", "").strip()
            names = [beat] + [n.strip() for n in beat.split(" / ") if " / " in beat]
            beats.append({"beat": beat, "names": names, **SP.parse_row(*cells[1:5])})
            k += 1
        after = []
        while k < len(lines) and not lines[k].startswith(("**Example", "**Pitfalls", "### ", "## ", "---")):
            after.append(lines[k])
            k += 1
        outline = _outline(lines, i, beats)
        act = ""
        for k, b in enumerate(beats):
            b.update(outline.get(k, {}))
            # a beat no outline row matches (the Spine's optional moral) is in the act before it
            act = b.get("act", act)
            if act:
                b["act"] = act
        st = {"id": m.group(1), "name": m.group(2), "beats": beats}
        if "bumper" in " ".join(after).lower():
            st["bumpers"] = True
        out.append(st)
    return {"_note": "Generated by tools/make_structures.py from docs/STORY_STRUCTURES.md's Music "
                     "tables; never edit by hand.", "structures": out}


def render(data: dict) -> str:
    return json.dumps(data, indent=1, ensure_ascii=False) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if structures.json is out of date")
    a = ap.parse_args()
    with open(DOC, encoding="utf-8") as fh:
        want = render(build(fh.read()))
    have = open(OUT, encoding="utf-8").read() if os.path.isfile(OUT) else ""
    if a.check:
        if have != want:
            print(f"{os.path.relpath(OUT, ROOT)} is out of date: python tools/make_structures.py")
            return 1
        return 0
    if have != want:
        from seriesmith.core import fileio as F
        F.write_bytes(OUT, want.encode("utf-8"))
        print(f"wrote {os.path.relpath(OUT, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
