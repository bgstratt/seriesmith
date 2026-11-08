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


# ---------------------------------------------------------------------------
# the structure's targets against what the script has
# ---------------------------------------------------------------------------
class BoardError(ValueError):
    pass


def _plain_name(name: str) -> str:
    return _AGAIN.sub("", name).strip()


def _beat_row(beat: dict | None, entry: dict | None, plain: str | None, nth: int) -> dict:
    row = dict(beat) if beat else {"beat": plain, "known": True, "block": None, "runs": []}
    shots = [s for r in row["runs"] for s in r["shots"]]
    row.update({"plain": plain, "nth": nth, "in_script": beat is not None,
                "guidance": (entry or {}).get("guidance") or row.get("guidance", ""),
                "target_shots": entry["shots"] if entry else None,
                "target_seconds": entry["seconds"] if entry else None,
                "thin": bool(entry and entry["thin"]),
                "shots": len(shots), "seconds": round(sum(s["seconds"] or 0 for s in shots), 3)})
    if entry:
        row.update({k: entry[k] for k in ("at", "point") if k in entry})
    return row


def plan(doc: dict, block: dict | None) -> dict:
    """outline(doc), each beat with its target from `block` (core/blocking.py's answer, or None for
    no targets) and the structure's beats the script hasn't got yet, in the structure's order: every
    beat gains "plain" (its name as a script writes it), "nth" (which time that name comes),
    "in_script", "target_shots", "target_seconds", "thin", "shots", "seconds"; every act "shots",
    "target_shots". A beat of the script's own stays where it is, among the structure's."""
    view = outline(doc)
    table = [b for a in (block or {}).get("acts", []) for b in a["beats"]]
    keyed: dict[tuple[str, int], int] = {}
    nth_of: list[int] = []
    counts: dict[str, int] = {}
    for i, entry in enumerate(table):
        key = SP.norm(_plain_name(entry["beat"]))
        nth_of.append(counts.get(key, 0))
        keyed[(key, nth_of[i])] = i
        counts[key] = nth_of[i] + 1

    out: list[tuple[str, bool, dict]] = []
    next_up = 0

    def table_up_to(stop: int) -> None:
        nonlocal next_up
        while next_up < stop:
            entry = table[next_up]
            out.append((entry["act"], False, _beat_row(None, entry, _plain_name(entry["beat"]), nth_of[next_up])))
            next_up += 1

    seen: dict[str, int] = {}
    for act in view["acts"]:
        for beat in act["beats"]:
            if beat["beat"] is None:
                out.append((act["act"], act["own"], _beat_row(beat, None, None, 0)))
                continue
            plain = _plain_name(beat["beat"])
            key = SP.norm(plain)
            nth = seen.get(key, 0)
            seen[key] = nth + 1
            at = keyed.get((key, nth))
            if at is None:
                out.append((act["act"], act["own"], _beat_row(beat, None, plain, nth)))
                continue
            table_up_to(at)
            next_up = max(next_up, at + 1)
            out.append((act["act"], act["own"], _beat_row(beat, table[at], plain, nth)))
    table_up_to(len(table))

    acts: list[dict] = []
    for name, own, row in out:
        if not acts or acts[-1]["act"] != name or acts[-1]["own"] != own:
            acts.append({"act": name, "own": own, "beats": [], "shots": 0, "target_shots": 0})
        acts[-1]["beats"].append(row)
        acts[-1]["shots"] += row["shots"]
        acts[-1]["target_shots"] += row["target_shots"] or 0
    return {**view, "acts": acts, "warnings": (block or {}).get("warnings", []),
            "target_shots": (block or {}).get("shots"), "shot_seconds": (block or {}).get("shot_seconds")}


# ---------------------------------------------------------------------------
# edits: each adds or changes the blocks it means to and leaves the rest alone
# ---------------------------------------------------------------------------
def _clock(seconds: float) -> str:
    whole = max(1, round(seconds))
    h, m, s = whole // 3600, whole % 3600 // 60, whole % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _insert(doc: dict, at: int, text: str, blank_before: bool = True) -> int:
    """`text`'s blocks into the script before block `at`; how many went in. The block before ends
    its last line and, with `blank_before`, leaves a blank one."""
    made = read(text)["blocks"][1:]
    blocks = doc["blocks"]
    before = blocks[at - 1] if at > 0 else None
    if before and before["lines"]:
        if not before["lines"][-1].endswith(("\n", "\r")):
            before["lines"][-1] += "\n"
        if blank_before and before["lines"][-1].strip():
            before["lines"].append("\n")
    blocks[at:at] = made
    return len(made)


def set_marks(doc: dict, structure: str | None, duration: float | None) -> None:
    """The script's `// structure:` (only if it has none) and `// duration:` lines, under its head."""
    blocks = doc["blocks"]
    if structure and not any(b["kind"] == "structure" for b in blocks):
        _insert(doc, 1, f"// structure: {structure}\n")
    if duration is None:
        return
    line = f"// duration: {_clock(duration)}\n"
    for block in blocks:
        if block["kind"] == "duration":
            if seconds_of(block["value"]) != float(max(1, round(duration))):
                block["lines"][0] = line
                block["value"] = _clock(duration)
            return
    after = next((i + 1 for i, b in enumerate(blocks) if b["kind"] == "structure"), None)
    if after is None:
        _insert(doc, 1, line)
    else:
        _insert(doc, after, line, blank_before=False)


def _find_beat(doc: dict, plain: str, nth: int) -> int | None:
    key, seen = SP.norm(plain), 0
    for i, block in enumerate(doc["blocks"]):
        if block["kind"] == "beat" and SP.norm(_plain_name(block["value"])) == key:
            if seen == nth:
                return i
            seen += 1
    return None


def _before_its_header(blocks: list[dict], at: int) -> int:
    """From a beat line (or its `// act:`) back to what belongs in front of it: its act, and a `#`
    header right above it whose shots are that beat's."""
    beat = at + 1 if blocks[at]["kind"] == "act" else at
    if at > 0 and blocks[at - 1]["kind"] == "act":
        at -= 1
    shots_follow = beat + 1 < len(blocks) and blocks[beat + 1]["kind"] == "shot"
    if at > 0 and blocks[at - 1]["kind"] == "sequence" and shots_follow:
        at -= 1
    return at


def ensure_beat(doc: dict, plain: str, nth: int, later: list[tuple[str, int]]) -> int:
    """The block index of the beat, writing its line first if the script hasn't got it: in front of
    the first of `later` (the beats after it in the structure) that the script has, else at the end."""
    found = _find_beat(doc, plain, nth)
    if found is not None:
        return found
    blocks = doc["blocks"]
    at = len(blocks)
    for name, n in later:
        hit = _find_beat(doc, name, n)
        if hit is not None:
            at = _before_its_header(blocks, hit)
            break
    _insert(doc, at, f"// beat: {plain}\n\n")
    return at


def _end_of_beat(blocks: list[dict], beat: int) -> int:
    """Where a new shot of the beat goes: before the next beat, with its act and its header."""
    at = beat + 1
    while at < len(blocks) and blocks[at]["kind"] not in ("beat", "act"):
        at += 1
    return _before_its_header(blocks, at) if at < len(blocks) else at


def _number(block: dict) -> int | None:
    m = re.fullmatch(r"sh(\d+)", block["shot"]["id"])
    return int(m.group(1)) if m else None


def _new_shot_id(blocks: list[dict], at: int) -> str:
    """Ten past the shot before if that's clear of the next, between them if not, ten past the
    highest when they leave no room."""
    numbers = [n for b in blocks if b["kind"] == "shot" for n in [_number(b)] if n is not None]
    used = {b["shot"]["id"] for b in blocks if b["kind"] == "shot"}
    prev = next((n for b in reversed(blocks[:at]) if b["kind"] == "shot" for n in [_number(b)] if n is not None), 0)
    after = next((n for b in blocks[at:] if b["kind"] == "shot" for n in [_number(b)] if n is not None), None)
    wanted = prev + 10
    if after is not None and wanted >= after:
        wanted = (prev + after) // 2 if after - prev > 1 else 0
    if not wanted or f"sh{wanted:03d}" in used:
        wanted = max(numbers, default=0) + 10
    return f"sh{wanted:03d}"


def _new_sequence_id(blocks: list[dict]) -> str:
    numbers = [int(m.group(1)) for b in blocks if b["kind"] == "sequence"
               for m in [re.fullmatch(r"sq(\d+)", b["id"])] if m]
    return f"sq{max(numbers, default=0) + 1:02d}"


def add_stand_ins(doc: dict, beat: int, count: int, seconds: float, action: str,
                  who: list[str] | None = None, place: str | None = None) -> list[str]:
    """`count` held shots at the end of the beat at block `beat`; their ids. They join the sequence
    the script is in there, unless `place` is somewhere else: then a new sequence opens. BoardError
    when there's no sequence to join and no place to open one in. `who` omitted: the last shot's,
    if it's in the same sequence."""
    blocks = doc["blocks"]
    at = _end_of_beat(blocks, beat)
    current = next((b for b in reversed(blocks[:at]) if b["kind"] == "sequence"), None)
    if current is None and not place:
        # ahead of the script's first sequence: a shot has to be under one, so open one there
        place = next((b["place"] for b in blocks[at:] if b["kind"] == "sequence"), None)
    if place and (current is None or current["place"] != place):
        at += _insert(doc, at, f"# {_new_sequence_id(blocks)}  {place}\n\n")
    elif current is None:
        raise BoardError("the script has no sequence yet: choose a place for the first one")
    if who is None:
        who = []
        for block in reversed(blocks[:at]):
            if block["kind"] == "sequence":
                break
            if block["kind"] == "shot":
                who = block["shot"]["who"]
                break
    made = []
    text = action.strip() or "Stand-in."
    for _ in range(count):
        sid = _new_shot_id(blocks, at)
        lines = [f"## {sid}", "target: hold"] + ([f"who: {', '.join(who)}"] if who else [])
        lines += [f"dur: {seconds:g}", text]
        at += _insert(doc, at, "\n".join(lines) + "\n\n")
        made.append(sid)
    return made


def set_place(doc: dict, block: int, place: str) -> None:
    """The location of the sequence at block `block`."""
    target = doc["blocks"][block]
    if target["kind"] != "sequence":
        raise BoardError("that isn't a sequence")
    for i, raw in enumerate(target["lines"]):
        if raw.startswith("# "):
            ending = raw[len(raw.rstrip("\r\n")):]
            target["lines"][i] = f"# {target['id']}  {place}{ending}"
            target["place"] = place
            return


def set_cast(doc: dict, block: int, who: list[str]) -> int:
    """`who:` on the sequence's empty stand-ins (never a shot someone has worked on); how many."""
    blocks = doc["blocks"]
    if blocks[block]["kind"] != "sequence":
        raise BoardError("that isn't a sequence")
    changed = 0
    for target in blocks[block + 1:]:
        if target["kind"] == "sequence":
            break
        if target["kind"] != "shot" or not target["shot"]["held_empty"]:
            continue
        keep = [ln for ln in target["lines"] if not re.match(r"^(who|cast)\s*:", ln)]
        header = next(i for i, ln in enumerate(keep) if ln.startswith("## "))
        if who:
            keep.insert(header + 1, f"who: {', '.join(who)}\n")
        target["lines"] = keep
        target["shot"] = _shot_view(keep)
        changed += 1
    return changed
