"""
board.py -- a script as the storyboard sees it (docs/PLAN.md, the storyboard).

    read(text)        -> the script as a list of blocks, each holding its own lines exactly
    text_of(doc)      -> the script again, byte for byte
    outline(doc)      -> acts, beats, the runs of a sequence inside a beat, and their shots

Model-free and stdlib only. A block is one thing the board can see (a beat line, a sequence, a
shot) and the lines that go with it: hand comments, blank lines and anything else the board doesn't
read stay inside a block, so whatever isn't edited comes back as it went in. A draft is an ordinary
script: nothing here needs a shot, a sequence, or for the script to be valid. It's what the
script says that is shown; the build (core/story.py) is still what checks it.

The comments the board reads, none of which the build does:

    // structure: Three-Act     which structure it follows (core/spotting.py reads this too)
    // duration: 22:00          the length it's aiming at; seconds, m:ss or h:mm:ss
    // act: My Own Act          the act of the beat below, when it isn't the structure's own
    // beat: Inciting Incident  a beat (the score reads this too)

An act holds until the next `// act:`, or a beat the structure itself puts in an act.
"""
from __future__ import annotations

import re

from seriesmith.core import spotting as SP
from seriesmith.core.story import META_KEYS

_MARK = re.compile(r"^//\s*(structure|duration|act|beat)\b:?\s*(.*?)\s*$")
_DIALOGUE = re.compile(r"^[A-Z][A-Z0-9_ '\-]*?\s*(?:\([^)]*\))?\s*:\s*.+$")
_FIELD = re.compile(r"^([a-z_]+)\s*:\s*(.*)$")
_AGAIN = re.compile(r"\s*\(again\)\s*$")


def seconds_of(value: str) -> float | None:
    """`90`, `1:30` or `1:02:30` in seconds; None for anything else, or for nothing above zero."""
    parts = value.strip().split(":")
    if not 1 <= len(parts) <= 3 or not all(re.fullmatch(r"\d+(\.\d+)?", p) for p in parts):
        return None
    total = 0.0
    for part in parts:
        total = total * 60 + float(part)
    return total if total > 0 else None


def _is_comment(line: str) -> bool:
    return line.strip().startswith("//")


def _starts(line: str) -> str | None:
    """The kind of block `line` opens, as core/story.py reads a line; None if it opens none."""
    if _is_comment(line):
        m = _MARK.match(line.strip())
        return m.group(1) if m else None
    bare = line.rstrip()
    if bare.startswith("## "):
        return "shot"
    if bare.startswith("# "):
        return "sequence"
    return None


def _shot_view(lines: list[str]) -> dict:
    """What the board shows of a shot, read from its own lines."""
    view: dict = {"id": "", "who": [], "target": None, "first": None, "continuous": None, "size": None,
                  "seconds": None, "timing": None, "action": "", "lines": 0}
    action: list[str] = []
    seen_header = False
    for raw in lines:
        line = raw.rstrip()
        if not line.strip() or _is_comment(line):
            continue
        if not seen_header:
            if line.startswith("## "):
                bits = line[3:].split()
                view["id"] = bits[0] if bits else ""
                seen_header = True
            continue
        if _DIALOGUE.match(line):
            view["lines"] += 1
            continue
        m = _FIELD.match(line)
        if not (m and m.group(1) in META_KEYS):
            action.append(line.strip())
            continue
        key, value = m.group(1), m.group(2).strip()
        if key in ("who", "cast"):
            view["who"] += [c.strip() for c in value.split(",") if c.strip() and c.strip() not in view["who"]]
        elif key in ("dur", "duration"):
            low = value.lower()
            if low == "auto" or low.split(" ")[0] == "model":
                view["timing"] = low.split(" ")[0]
            else:
                try:
                    view["seconds"] = float(value)
                except ValueError:
                    pass
        elif key in ("target", "first", "continuous", "size"):
            view[key] = value
    view["action"] = " ".join(action)
    view["held_empty"] = (view["target"] == "hold" and not view["first"] and view["continuous"] in (None, "none")
                          and not view["lines"])
    return view


def read(text: str) -> dict:
    """The script as blocks: {"blocks": [{"kind", "lines", ...what that kind says}]}. The first
    block is "head", everything before the first thing the board can see (it may be empty)."""
    lines = text.splitlines(keepends=True)
    starts: dict[int, str] = {}
    for i, line in enumerate(lines):
        kind = _starts(line)
        if kind:
            starts[i] = kind
    # the comments right above a sequence or a shot go with it (a `// theme:`, a note about it)
    opens = {}
    for i, kind in starts.items():
        first = i
        if kind in ("sequence", "shot"):
            while first > 0 and first - 1 not in starts and _is_comment(lines[first - 1]):
                first -= 1
        opens[first] = (kind, i)

    blocks: list[dict] = [{"kind": "head", "lines": []}]
    for i, line in enumerate(lines):
        if i in opens:
            kind, at = opens[i]
            blocks.append({"kind": kind, "lines": [], "at": at - i})
        blocks[-1]["lines"].append(line)
    for block in blocks:
        at = block.pop("at", 0)
        kind = block["kind"]
        if kind in ("structure", "act", "beat", "duration"):
            block["value"] = _MARK.match(block["lines"][at].strip()).group(2)
        elif kind == "sequence":
            bits = block["lines"][at].rstrip()[2:].split()
            block["id"] = bits[0] if bits else ""
            block["place"] = bits[1] if len(bits) > 1 else ""
        elif kind == "shot":
            block["shot"] = _shot_view(block["lines"])
    return {"blocks": blocks}


def text_of(doc: dict) -> str:
    return "".join(line for block in doc["blocks"] for line in block["lines"])


def _table(name: str | None) -> tuple[str | None, dict[str, list[dict]]]:
    """The structure's own name and its beats by every name they go by; (None, {}) if it has none."""
    if not name:
        return None, {}
    try:
        st = SP.structure(name)
    except SP.SpotError:
        return None, {}
    table: dict[str, list[dict]] = {}
    for beat in st["beats"]:
        for alias in {SP.norm(_AGAIN.sub("", n)) for n in beat["names"]}:
            table.setdefault(alias, []).append(beat)
    return st["name"], table


def _episode(head: list[str]) -> tuple[str, str]:
    for raw in head:
        if raw.startswith("= "):
            parts = raw[2:].split(None, 1)
            return (parts[0] if parts else ""), (parts[1].strip() if len(parts) > 1 else "")
    return "", ""


def outline(doc: dict) -> dict:
    """{"id", "title", "structure", "structure_known", "duration", "shots", "seconds", "untimed",
    "acts": [{"act", "own", "beats": [{"beat" (None: shots before any beat), "known", "guidance",
    "block", "runs": [{"sequence", "place", "opens", "block", "shots": [shot view + "block"]}]}]}]}.

    `block` is an index into doc["blocks"]. `opens` is false for a run carrying on a sequence begun
    in an earlier beat. A beat line right under a `#` header belongs with that header's shots, as
    `// beat:` does for the score, so the sequence opens inside that beat."""
    blocks = doc["blocks"]
    named = next((b["value"] for b in blocks if b["kind"] == "structure" and b["value"]), None)
    known_name, table = _table(named)
    duration = next((s for b in blocks if b["kind"] == "duration" for s in [seconds_of(b["value"])] if s), None)
    head = next((b["lines"] for b in blocks if any(ln.startswith("= ") for ln in b["lines"])), [])
    ep_id, title = _episode(head)

    acts: list[dict] = []
    act_now, own_now = "", False
    pending_own: str | None = None
    seen: dict[str, int] = {}
    sequence: dict | None = None
    n_shots, total, untimed = 0, 0.0, 0

    def open_beat(name: str | None, block: int | None, entry: dict | None, act: str, own: bool) -> dict:
        if not acts or acts[-1]["act"] != act or acts[-1]["own"] != own:
            acts.append({"act": act, "own": own, "beats": []})
        beat = {"beat": name, "known": entry is not None, "guidance": (entry or {}).get("guidance", ""),
                "block": block, "runs": []}
        acts[-1]["beats"].append(beat)
        return beat

    def current() -> dict:
        if acts and acts[-1]["beats"]:
            return acts[-1]["beats"][-1]
        return open_beat(None, None, None, act_now, own_now)

    for i, block in enumerate(blocks):
        kind = block["kind"]
        if kind == "act":
            pending_own = block["value"]
        elif kind == "beat":
            name = block["value"]
            key = SP.norm(_AGAIN.sub("", name))
            options = table.get(key, [])
            nth = seen.get(key, 0)
            seen[key] = nth + 1
            entry = options[min(nth, len(options) - 1)] if options else None
            if pending_own is not None:
                act_now, own_now = pending_own, True
            elif entry is not None and entry.get("act"):
                act_now, own_now = entry["act"], False
            pending_own = None
            # the header just above, whose shots are this beat's, comes along
            carried = None
            if acts and acts[-1]["beats"] and blocks[i + 1:i + 2] and blocks[i + 1]["kind"] == "shot":
                last = acts[-1]["beats"][-1]
                if last["runs"] and not last["runs"][-1]["shots"]:
                    carried = last["runs"].pop()
                    if last["beat"] is None and not last["runs"]:
                        acts[-1]["beats"].pop()
                        if not acts[-1]["beats"]:
                            acts.pop()
            beat = open_beat(name, i, entry, act_now, own_now)
            if carried:
                beat["runs"].append(carried)
        elif kind == "sequence":
            sequence = {"id": block["id"], "place": block["place"], "block": i}
            current()["runs"].append({"sequence": block["id"], "place": block["place"], "opens": True,
                                      "block": i, "shots": []})
        elif kind == "shot":
            beat = current()
            if not beat["runs"] or (sequence and beat["runs"][-1]["sequence"] != sequence["id"]):
                beat["runs"].append({"sequence": sequence["id"] if sequence else "",
                                     "place": sequence["place"] if sequence else "", "opens": False,
                                     "block": sequence["block"] if sequence else None, "shots": []})
            beat["runs"][-1]["shots"].append({**block["shot"], "block": i})
            n_shots += 1
            if block["shot"]["seconds"] is not None:
                total += block["shot"]["seconds"]
            else:
                untimed += 1
    return {"id": ep_id, "title": title, "structure": known_name or named, "structure_known": known_name is not None,
            "duration": duration, "shots": n_shots, "seconds": round(total, 3), "untimed": untimed, "acts": acts}
