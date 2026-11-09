"""
own_structures -- the story structures you've saved yourself, for every show on this machine, in
`structures.json` beside the settings file. Plain JSON: to pass one along, hand over the file.

They're the storyboard's only (core/board.py, core/blocking.py): a beat's act, its share of the
story and a line of guidance. They have no Music table, so the score goes on as it did.
"""
from __future__ import annotations

import os

from seriesmith import settings as ST
from seriesmith.core import fileio as F
from seriesmith.core import spotting as SP

# tests point this at a folder of their own
PATH_OVERRIDE: str | None = None


class StructureError(ValueError):
    pass


def path() -> str:
    return PATH_OVERRIDE or os.path.join(os.path.dirname(os.path.abspath(ST.settings_path())), "structures.json")


def load() -> list[dict]:
    raw = F.read_json_or(path(), {}, dict)
    items = raw.get("structures")
    return [s for s in items if isinstance(s, dict) and s.get("name") and s.get("beats")] if isinstance(items, list) else []


def _write(items: list[dict]) -> None:
    os.makedirs(os.path.dirname(path()), exist_ok=True)
    F.write_json(path(), {"structures": items})


def build(name: str, beats: list[dict]) -> dict:
    """A structure from the table you filled in: each row's `beat`, `share` (any numbers above
    zero: they're scaled to the whole story), and optional `act` (empty: the act above it) and
    `guidance`."""
    if not isinstance(name, str) or not name.strip() or "\n" in name:
        raise StructureError("a structure needs a name, on one line")
    if not isinstance(beats, list) or not beats:
        raise StructureError("a structure needs at least one beat")
    shares: list[float] = []
    for row in beats:
        if not isinstance(row, dict) or not isinstance(row.get("beat"), str) or not row["beat"].strip():
            raise StructureError("every row needs a beat's name")
        share = row.get("share")
        if isinstance(share, bool) or not isinstance(share, (int, float)) or share <= 0:
            raise StructureError(f"{row['beat']}: its share has to be above zero")
        shares.append(float(share))
    whole, at, act = sum(shares), 0.0, ""
    out = []
    for row, share in zip(beats, shares):
        act = str(row.get("act") or "").strip() or act
        beat = row["beat"].strip()
        end = at + share / whole * 100
        entry = {"beat": beat, "names": [beat], "guidance": str(row.get("guidance") or "").strip(),
                 "at": [round(at, 2), round(end, 2)]}
        if act:
            entry["act"] = act
        out.append(entry)
        at = end
    out[-1]["at"][1] = 100
    return {"id": "own", "name": name.strip(), "own": True, "beats": out}


def _is_builtin(name: str) -> bool:
    try:
        SP.structure(name)
    except SP.SpotError:
        return False
    return True


def save(name: str, beats: list[dict], replace: bool = False) -> dict:
    """Keep it; StructureError for a name a built-in answers to, or one of yours without `replace`."""
    made = build(name, beats)
    if _is_builtin(made["name"]):
        raise StructureError(f"{made['name']} is a built-in structure's name: choose another")
    key = SP.norm(made["name"])
    items = load()
    if not replace and any(SP.norm(s["name"]) == key for s in items):
        raise StructureError(f"you already have a structure called {made['name']}")
    _write([s for s in items if SP.norm(s["name"]) != key] + [made])
    return made


def delete(name: str) -> bool:
    items = load()
    left = [s for s in items if SP.norm(s["name"]) != SP.norm(str(name))]
    if len(left) == len(items):
        return False
    _write(left)
    return True
