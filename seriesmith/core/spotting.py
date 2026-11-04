"""
spotting.py — a first-pass score spotted from a script's structure, without an LLM (docs/SOUND.md
phase 8, "The simple first pass"). Model-free and standard library only, like the rest of core.

    read_marks(text)                      -> the script's `// structure:`, `// beat:`, `// theme:`
                                             and `// flashback` lines, each on the shot below it
    parse_row(music, mood, theme, hit)    -> a Music table row as a beat's treatment
    structure(name)                       -> a structure's Music table (structures.json)
    check_format(raw)                     -> the series config's `sound.format`, checked
    layout(shots, st)                     -> a structure's beats laid over a cut with no beat
                                             lines (each beat's `at`, snapped to a sequence)
    draft(shots, marks, ...)              -> the draft: cues and stings, their sections and
                                             hits, and what the rules flag for a person

A beat's **treatment** (a Music table row, or a beat of `sound.format`):

    {"music": "score" | "under" | "gaps" | "sting" | "dry",   gaps: only where no one speaks
     "sting_at": "start" | "end",          a sting: where in the beat
     "last_scene": true,                   held to the beat's last sequence
     "words": "warm, soft",                its mood: the section's words in the prompt
     "energy": [1, 2],                     from and to, 1 (barely there) to 5 (everything)
     "theme": "story" | "show" | "runner" | "lead" | <a series theme's name> | null,
     "theme_words": "echo, slowed",        how the theme plays (statement, echo, and words)
     "theme_else": "mark",                 `lead`'s theme when no series theme is `for` the lead
     "then": "runner",                     the theme of the sting at its end, when another
     "strength": 0.86,                     the theme's strength, when not the model's
     "hits": [{"kind": "turn" | "arrive" | "drop", "at": "start" | "last" | "end"}],
     "sting_end": true,                    a sting at its end besides (an act-out, the title)
     "talk_max": 0.3}                      `sound.format`'s `other`: dry above this talk share

`structures.json` is tools/make_structures.py's, from docs/STORY_STRUCTURES.md's Music tables:
the doc is the source, never the file. A show's own format (`sound.format` in the series
config) names its own beats, `like` a structure for the ones it doesn't, `other` for a beat
neither names, and `marks` for how a theme marked by hand plays (`{"glance": "sting"}`).

The draft, by rule: beats in a row with music are one cue, a section and a `turn` each (split
where the theme changes or the cue would run past CUE_MAX); a cue starts PRELAP before the cut
into its beat and ends on a cut; a sting is STING seconds at its beat's start or end; `story`
is the episode's own melody, made by its first scored cue (no theme) and taken by the later
ones (that cue's take); `show` and `runner` are the series themes of that role; `lead` the theme
`for` the beat's lead (the most shots in `who:` and lines on screen). A character's theme (a
series theme `for` the episode's lead) is its `story` theme, carried from episode to episode,
in place of one each episode makes. A sitcom's bumpers (a structure
whose `bumpers` is set) go at each new sequence location, unless a sting or a cue is there. A
`// theme: <theme>, <words>` mark holds that theme low from its shot to its scene's end, or is
a sting on the shot (`sting` in its words, or the format's `marks`). Flagged, not drafted:
music in the scene (a shot's `sound:`), a montage (a run of short shots with no lines; a cue
when none covers it), a title or credits card (`target: hold` first or last), a flashback.
"""

from __future__ import annotations

import json
import os
import re

PRELAP = 1.0          # seconds a cue starts before the cut into its beat
STING = 3.0           # seconds of a sting or a bumper
CUE_MAX = 180.0       # seconds: a cue longer is split at a beat (or a sequence) boundary
GAP_MIN = 10.0        # seconds: `gaps` scores the runs of shots with no lines this long or longer
GAP_JOIN = 10.0       # seconds: runs with less than this of lines between them are one cue
MONTAGE_SHOTS = 4     # a run of this many short shots with no lines is a montage
MONTAGE_SHOT = 3.0    # seconds: a montage's shots are this short or shorter
MUSICS = ("score", "under", "gaps", "sting", "dry")
ROLES = ("story", "show", "runner")
HIT_KINDS = ("turn", "arrive", "drop")
HIT_AT = ("start", "last", "end")
TREATMENT_FIELDS = ("music", "sting_at", "last_scene", "words", "energy", "theme", "theme_else", "theme_words",
                    "then", "strength", "hits", "sting_end", "talk_max")
FORMAT_FIELDS = ("like", "beats", "other", "marks")
# a shot's `sound:` that has music in the scene
IN_SCENE = re.compile(r"\b(radio|jukebox|stereo|record player|band (?:plays|playing)|song|music|"
                      r"singing|sings|carousel|organ|piano plays)\b", re.I)
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "structures.json")
_MARK = re.compile(r"^//\s*(structure|beat|theme|flashback)\b:?\s*(.*?)\s*$")
_SHOT = re.compile(r"^##\s+(\S+)")
_ENERGY = re.compile(r"\((\d)(?:\s*(?:→|->)\s*(\d))?\)\s*$")


class SpotError(ValueError):
    pass


def _words(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", s.lower())) - {"the", "a", "an", "s"}


def norm(name: str) -> str:
    """A beat's or a structure's name as compared: lower case, words only ("Once upon a
    time…" and "once upon a time" are one)."""
    return " ".join(re.findall(r"[a-z0-9]+", (name or "").lower()))


# ---------------------------------------------------------------------------
# the script's marks
# ---------------------------------------------------------------------------

def read_marks(text: str) -> dict:
    """The script's comment marks, each on the first shot below it: {"structure": name |
    None, "beats": {shot: beat}, "themes": {shot: words}, "flashback": [shot]} (a beat seen
    again is `<beat> (again)` from its second time on, as the tables name a repeat)."""
    out: dict = {"structure": None, "beats": {}, "themes": {}, "flashback": []}
    pending: dict = {}
    seen: dict[str, int] = {}
    for line in text.splitlines():
        line = line.strip()
        m = _MARK.match(line)
        if m:
            kind, rest = m.group(1), m.group(2)
            if kind == "structure" and rest and out["structure"] is None:
                out["structure"] = rest
            elif kind == "beat" and rest:
                n = norm(rest)
                seen[n] = seen.get(n, 0) + 1
                pending["beat"] = rest if seen[n] == 1 else f"{rest} (again)"
            elif kind == "theme" and rest:
                pending["theme"] = rest
            elif kind == "flashback":
                pending["flashback"] = True
            continue
        m = _SHOT.match(line)
        if m and pending:
            sid = m.group(1)
            if "beat" in pending:
                out["beats"][sid] = pending["beat"]
            if "theme" in pending:
                out["themes"][sid] = pending["theme"]
            if pending.get("flashback"):
                out["flashback"].append(sid)
            pending = {}
    return out


# ---------------------------------------------------------------------------
# a beat's treatment
# ---------------------------------------------------------------------------

def parse_row(music: str, mood: str, theme: str, hit: str) -> dict:
    """A Music table row (docs/STORY_STRUCTURES.md) as a beat's treatment."""
    music, mood, theme, hit = (" ".join(x.replace("—", "").split()) for x in (music, mood, theme, hit))
    out: dict = {}
    m = music.lower()
    if m.startswith("sting"):
        out["music"] = "sting"
        out["sting_at"] = "start" if "start" in m else "end"
    elif m.startswith("under"):
        out["music"] = "under"
    elif m.startswith("score") or "structure underneath" in m:
        out["music"] = "score"
    else:
        out["music"] = "dry"
    if "last scene" in m:
        out["last_scene"] = True
    if out["music"] == "dry":
        return out
    e = _ENERGY.search(mood)
    if e:
        a = int(e.group(1))
        out["energy"] = [a, int(e.group(2) or a)]
        mood = mood[:e.start()]
    if mood.strip() and "music table" not in mood.lower():
        out["words"] = mood.strip(" ,.;")
    first, _, rest = theme.partition(";")
    bits = [b.strip() for b in first.split(",") if b.strip()]
    if bits and bits[0].lower() in ROLES:
        out["theme"] = bits[0].lower()
        if bits[1:]:
            out["theme_words"] = ", ".join(bits[1:])
    then = rest.strip()
    if then.lower().startswith("then "):
        role = then[5:].split(",")[0].strip().lower()
        if role in ROLES:
            out["then"] = role
    h = hit.lower()
    hits = []
    for mm in re.finditer(r"\b(turn|arrive|drop)\b(\s*\(([^)]*)\)|\s+at its end)?", h):
        kind, how = mm.group(1), (mm.group(2) or "")
        at = {"turn": "start", "arrive": "last", "drop": "end"}[kind]
        if "as it starts" in how or "first shot" in how:
            at = "start"
        elif "its end" in how:
            at = "end"
        hits.append({"kind": kind, "at": at})
    if hits:
        out["hits"] = hits
    if "a sting at its end" in h:
        out["sting_end"] = True
    return out


def check_treatment(raw, what: str) -> dict:
    """A beat's treatment from the series config's `sound.format`. SpotError says what's
    wrong."""
    if not isinstance(raw, dict):
        raise SpotError(f"{what} must be an object")
    unknown = set(raw) - set(TREATMENT_FIELDS)
    if unknown:
        raise SpotError(f"{what}: unknown field(s) {', '.join(sorted(unknown))}")
    music = raw.get("music", "score")
    if music not in MUSICS:
        raise SpotError(f"{what}'s music is {', '.join(MUSICS)}, not {music!r}")
    out: dict = {"music": music}
    if music == "sting":
        at = raw.get("sting_at", "end")
        if at not in ("start", "end"):
            raise SpotError(f"{what}'s sting_at is start or end, not {at!r}")
        out["sting_at"] = at
    if raw.get("last_scene"):
        out["last_scene"] = True
    for k in ("words", "theme_words"):
        if raw.get(k) is not None:
            if not isinstance(raw[k], str):
                raise SpotError(f"{what}'s {k} is text")
            if raw[k].strip():
                out[k] = " ".join(raw[k].split())
    for k in ("theme", "theme_else", "then"):
        if raw.get(k) is not None:
            if not isinstance(raw[k], str) or not raw[k].strip():
                raise SpotError(f"{what}'s {k} is a role ({', '.join(ROLES)}, lead) or a series theme's name")
            out[k] = raw[k].strip()
    if raw.get("energy") is not None:
        en = raw["energy"]
        en = [en, en] if isinstance(en, (int, float)) and not isinstance(en, bool) else en
        if not isinstance(en, list) or len(en) != 2 or not all(
                isinstance(x, (int, float)) and not isinstance(x, bool) and 1 <= x <= 5 for x in en):
            raise SpotError(f"{what}'s energy is 1-5, or [from, to]")
        out["energy"] = [float(x) for x in en]
    if raw.get("strength") is not None:
        s = raw["strength"]
        if isinstance(s, bool) or not isinstance(s, (int, float)) or not 0.5 <= s <= 0.99:
            raise SpotError(f"{what}'s strength is 0.5 to 0.99, not {s!r}")
        out["strength"] = round(float(s), 2)
    if raw.get("talk_max") is not None:
        t = raw["talk_max"]
        if isinstance(t, bool) or not isinstance(t, (int, float)) or not 0 <= t <= 1:
            raise SpotError(f"{what}'s talk_max is a share, 0 to 1")
        out["talk_max"] = float(t)
    hits = []
    for i, h in enumerate(raw.get("hits") or []):
        if isinstance(h, str):
            h = {"kind": h}
        if not isinstance(h, dict) or h.get("kind") not in HIT_KINDS:
            raise SpotError(f"{what}'s hit {i + 1} is {{\"kind\": {' | '.join(HIT_KINDS)}, \"at\"}}")
        at = h.get("at") or {"turn": "start", "arrive": "last", "drop": "end"}[h["kind"]]
        if at not in HIT_AT:
            raise SpotError(f"{what}'s hit {i + 1}'s at is {', '.join(HIT_AT)}")
        hits.append({"kind": h["kind"], "at": at})
    if hits:
        out["hits"] = hits
    if raw.get("sting_end"):
        out["sting_end"] = True
    return out


def check_format(raw) -> dict:
    """The series config's `sound.format`: {"like": a structure, "beats": {beat: treatment},
    "other": treatment, "marks": {theme: "sting" | "under"}}. SpotError says what's wrong."""
    if not isinstance(raw, dict):
        raise SpotError("sound.format must be an object")
    unknown = set(raw) - set(FORMAT_FIELDS)
    if unknown:
        raise SpotError(f"sound.format: unknown field(s) {', '.join(sorted(unknown))}")
    out: dict = {}
    if raw.get("like"):
        out["like"] = structure(str(raw["like"]))["name"]
    beats = raw.get("beats") or {}
    if not isinstance(beats, dict):
        raise SpotError("sound.format's beats is {beat: its treatment}")
    out["beats"] = {str(k): check_treatment(v, f"sound.format beat {k!r}") for k, v in beats.items()}
    if raw.get("other") is not None:
        out["other"] = check_treatment(raw["other"], "sound.format's other")
    marks = raw.get("marks") or {}
    if not isinstance(marks, dict) or not all(v in ("sting", "under") for v in marks.values()):
        raise SpotError("sound.format's marks is {theme: \"sting\" | \"under\"}")
    if marks:
        out["marks"] = {str(k): v for k, v in marks.items()}
    return out


# ---------------------------------------------------------------------------
# the structures
# ---------------------------------------------------------------------------

_STRUCTURES: list | None = None


def structures() -> list[dict]:
    """Every structure with a Music table: [{"id": "2.1", "name", "bumpers", "beats":
    [{"beat", "names", ...treatment}]}] (structures.json)."""
    global _STRUCTURES
    if _STRUCTURES is None:
        with open(DATA, encoding="utf-8") as fh:
            _STRUCTURES = json.load(fh)["structures"]
    return _STRUCTURES


def structure(name: str) -> dict:
    """The structure `name` names: every word of it in the heading's ("Pixar Story Spine",
    "Sitcom", "Episodic Drama"), or its number ("2.1"). SpotError when none does, or more
    than one."""
    want = _words(name)
    if not want:
        raise SpotError("a structure needs its name")
    hits = [s for s in structures() if s["id"] == name.strip() or want <= _words(s["name"])]
    if len(hits) != 1:
        names = ", ".join(s["name"] for s in structures())
        raise SpotError(f"{name!r} is {'more than one structure' if hits else 'no structure'} "
                        f"of docs/STORY_STRUCTURES.md with a Music table ({names})")
    return hits[0]


LAYOUT_SHOT = 0.04    # of the episode: what a beat starting on a shot, not a sequence, costs


def layout(shots: list[dict], st: dict) -> dict[str, str]:
    """A structure's beats laid over a cut whose script has no beat lines: {shot: beat}, each
    beat (one with an `at`, its place in the story in percent: a beat at a point, or with
    none, is left to the beats around it) starting on the shot nearest its place, a sequence's
    first shot rather than another when one is near (LAYOUT_SHOT), each after the one before;
    a beat with no shot left after it is left out. A beat named again is its "(again)", as
    read_marks reads a repeat (a script writes the plain name: scoredraft.mark_script)."""
    if not shots:
        return {}
    total = shots[-1]["t"] + shots[-1]["d"]
    beats = [b for b in st["beats"] if b.get("at")]
    out: dict[str, str] = {}
    prev = -1
    for n, b in enumerate(beats):
        name = b["beat"]
        if name in out.values() and not name.endswith("(again)"):
            name += " (again)"
        if n == 0:
            out[shots[0]["id"]] = name
            prev = 0
            continue
        want = b["at"][0] / 100 * total
        # room for the beats still to come, a shot each, while there are shots for them
        last = min(len(shots) - 1, max(prev + 1, len(shots) - (len(beats) - n)))
        cands = range(prev + 1, last + 1)
        if not cands:
            break

        def cost(i: int) -> float:
            seq_start = shots[i]["seq"] != shots[i - 1]["seq"]
            return abs(shots[i]["t"] - want) + (0 if seq_start else LAYOUT_SHOT * total)
        prev = min(cands, key=cost)
        out[shots[prev]["id"]] = name
    return out


def table_of(st: dict) -> dict[str, dict]:
    """A structure's beats by each of their names, normalized: {"cold open": treatment,
    "teaser": treatment, ...}."""
    out = {}
    for b in st["beats"]:
        t = {k: v for k, v in b.items() if k not in ("beat", "names")}
        for n in b["names"]:
            out[norm(n)] = t
    return out


# ---------------------------------------------------------------------------
# the draft
# ---------------------------------------------------------------------------

def anchor_at(shots: list[dict], t: float, end: bool = False) -> dict:
    """Cue seconds as a shot and seconds into it: the shot playing then (an end on a cut: the
    shot before's end). Within a millisecond of a cut counts as on it (shot times are rounded)."""
    eps = 1e-3
    if end:
        cands = [s for s in shots if s["t"] < t - eps] or shots[:1]
    else:
        cands = [s for s in shots if s["t"] <= t + eps] or shots[:1]
    s = cands[-1]
    return {"shot": s["id"], "at": round(min(s["d"], max(0.0, t - s["t"])), 3)}


def _lead(shots: list[dict]) -> str | None:
    """Who leads these shots: the most shots in `who:` and lines."""
    count: dict[str, int] = {}
    for s in shots:
        for c in s.get("who") or []:
            count[c] = count.get(c, 0) + 1
        for c in s.get("speakers") or []:
            count[c] = count.get(c, 0) + 1
    return max(sorted(count), key=lambda c: count[c]) if count else None


def _span(shots: list[dict]) -> tuple[float, float]:
    return shots[0]["t"], shots[-1]["t"] + shots[-1]["d"]


def _beats(shots: list[dict], marks: dict, by_seq: bool) -> list[dict]:
    """The shots grouped into beats, in order: [{"beat": name | None, "shots"}]. Without
    beat lines (`by_seq`), each sequence is one."""
    out: list[dict] = []
    cur = None
    for s in shots:
        b = s["seq"] if by_seq else marks["beats"].get(s["id"], cur)
        if not out or b != cur:
            out.append({"beat": b, "shots": []})
        cur = b
        out[-1]["shots"].append(s)
    return out


def _treatment(beat: str | None, shots: list[dict], fmt: dict, table: dict) -> tuple[dict, str]:
    """A beat's treatment and where it came from ("format", "structure", "other", "unknown")."""
    n = norm(beat or "")
    own = {norm(k): v for k, v in (fmt.get("beats") or {}).items()}
    if n in own:
        return own[n], "format"
    if n in table:
        return table[n], "structure"
    # a repeat the table doesn't name ("Because of that… (again)" where only the first is)
    base = norm(re.sub(r"\s*\(again\)\s*$", "", beat or ""))
    if base in own:
        return own[base], "format"
    if base in table:
        return table[base], "structure"
    other = fmt.get("other")
    if other:
        talk = sum(s.get("talk", 0.0) for s in shots) / max(1e-6, sum(s["d"] for s in shots))
        if other.get("talk_max") is not None and talk >= other["talk_max"]:
            return {"music": "dry"}, "other"
        return other, "other"
    return {"music": "dry"}, "unknown"


def _theme_of(name: str | None, lead: str | None, themes: list[dict],
              other: str | None = None) -> tuple[str | None, str | None]:
    """A beat's theme ("story", "show", "runner", "lead" or a series theme's name) as a series
    theme's name, or "story"; with a note when the series has none to give. `other`: lead's
    theme when no series theme is `for` the lead."""
    if not name:
        return None, None
    if name == "story":
        return "story", None
    if name in ("show", "runner"):
        for t in themes:
            if t.get("role") == name:
                return t["name"], None
        return None, f"no {name} theme in the series config yet (sound.themes, role {name}): make one from a take (★)"
    if name == "lead":
        for t in themes:
            if lead and lead in (t.get("for") or []):
                return t["name"], None
        return _theme_of(other, None, themes) if other else (None, None)
    if any(t["name"] == name for t in themes):
        return name, None
    return None, f"no theme {name!r} in the series config yet (sound.themes): make one from a take (★)"


def draft(shots: list[dict], marks: dict, fmt: dict | None = None, themes: list[dict] | None = None) -> dict:
    """The first-pass score of an episode.

    `shots`, in cut order: [{"id", "seq", "loc", "t" (seconds), "d" (seconds), "talk" (seconds
    of dialogue), "who": [ids], "speakers": [ids, a line each], "sound", "music", "target"}];
    `marks` read_marks'; `fmt` the series config's `sound.format`, checked; `themes` the
    series config's themes, [{"name", "role", "for"}].

    Returns {"structure", "beats": [{"beat", "from" (format, structure, other, unknown),
    "music", "t0", "t1", "shot"}], "cues": [{"kind": "cue" | "sting" | "bumper", "label",
    "in" {"shot", "at" (seconds into it; negative: before it, in the shot before)}, "out"
    {"shot", "at"}, "t0", "t1", "theme" ("story", a series theme, or None), "makes"
    ("story": this cue makes the episode's theme), "strength", "sections": [{"name",
    "words", "from", "to", "seconds"}], "hits": [{"kind", "shot", "name"}]}], "flags":
    [{"kind", "shot", "text"}], "notes": [text]}."""
    fmt = fmt or {}
    themes = themes or []
    notes: list[str] = []
    flags: list[dict] = []
    if not shots:
        return {"structure": None, "beats": [], "cues": [], "flags": [], "notes": ["no shots in the cut"]}
    name = marks.get("structure")
    st = None
    if fmt.get("like"):
        st = structure(fmt["like"])
    if name and not fmt.get("beats"):
        try:
            st = structure(name)
        except SpotError as e:
            notes.append(str(e))
    table = table_of(st) if st else {}
    by_seq = not marks.get("beats")
    if by_seq:
        notes.append("no // beat: lines: one cue per sequence, flat (the skill writes the beat lines: "
                     "STORY_STRUCTURES' From beats to shots)")
    pos = {s["id"]: i for i, s in enumerate(shots)}
    total = shots[-1]["t"] + shots[-1]["d"]

    def anchor(t: float, end: bool = False) -> dict:
        return anchor_at(shots, t, end)

    beats = []
    for b in _beats(shots, marks, by_seq):
        if b["beat"] is None and not by_seq:
            # the shots before the first beat line
            tr, src = {"music": "dry"}, "unmarked"
        elif by_seq:
            tr, src = {"music": "under", "energy": [2, 2], "theme": "story"}, "sequence"
        else:
            tr, src = _treatment(b["beat"], b["shots"], fmt, table)
        sh = b["shots"]
        if tr.get("last_scene"):
            sh = [s for s in sh if s["seq"] == sh[-1]["seq"]]
        t0, t1 = _span(sh)
        beats.append({"beat": b["beat"] if not by_seq else f"sequence {b['beat']}", "from": src,
                      "tr": tr, "shots": sh, "all": b["shots"], "t0": t0, "t1": t1})
        if src == "unknown":
            notes.append(f"beat {b['beat']!r} isn't in {st['name'] if st else 'the format'}'s table: played dry")

    flash = set()
    for sid in marks.get("flashback") or []:
        if sid in pos:
            seq = shots[pos[sid]]["seq"]
            flash |= {s["id"] for s in shots if s["seq"] == seq}

    cues: list[dict] = []
    story_made = None
    # the episode's lead's theme, when the series has one: the story theme, already made
    lead = _lead(shots)
    own = next((t["name"] for t in themes if lead and lead in (t.get("for") or [])), None)
    if own:
        notes.append(f"the episode's theme is {lead}'s, {own} (sound.themes.{own}, for {lead})")

    def story(theme):
        return own if theme == "story" and own else theme

    def section(b: dict, tr: dict, t0: float, t1: float) -> dict:
        words = tr.get("words") or ""
        extra = [w.strip() for w in (tr.get("theme_words") or "").split(",")
                 if w.strip() and w.strip().lower() not in ("statement", "echo")]
        if extra:
            words = ", ".join(x for x in (words, ", ".join(extra)) if x)
        if any(s["id"] in flash for s in b["shots"]):
            words = ", ".join(x for x in (words, "thinner, further away, an echo") if x)
        en = tr.get("energy") or [2, 2]
        return {"name": (b["beat"] or "")[:40], "words": words, "from": float(en[0]), "to": float(en[1]),
                "seconds": round(t1 - t0, 3)}

    def gaps(sh: list[dict]) -> list[list[dict]]:
        """A beat's runs of shots with no lines, GAP_MIN or longer; two runs with less than
        GAP_JOIN of lines between them are one (the music held, ducked, under the line)."""
        runs, run = [], []
        for s in sh + [None]:
            if s is not None and not s.get("talk"):
                run.append(s)
                continue
            if run:
                runs.append(run)
            run = []
        joined: list[list[dict]] = []
        for r in runs:
            if joined and r[0]["t"] - _span(joined[-1])[1] < GAP_JOIN:
                last = joined[-1]
                joined[-1] = sh[sh.index(last[0]):sh.index(r[-1]) + 1]
            else:
                joined.append(r)
        return [r for r in joined if _span(r)[1] - _span(r)[0] >= GAP_MIN]

    def split(sh: list[dict]) -> list[list[dict]]:
        """Shots in pieces of CUE_MAX at most, cut where a sequence starts (else at any shot)."""
        out = []
        while sh and _span(sh)[1] - sh[0]["t"] > CUE_MAX:
            fits = [i for i in range(1, len(sh)) if sh[i]["t"] - sh[0]["t"] <= CUE_MAX]
            at = [i for i in fits if sh[i]["seq"] != sh[i - 1]["seq"]] or fits
            if not at:
                break
            out.append(sh[:at[-1]])
            sh = sh[at[-1]:]
        return out + [sh] if sh else out

    # the beats with music, as cues; beats in a row with the same theme are one
    for b in beats:
        tr = b["tr"]
        if tr["music"] not in ("score", "under", "gaps"):
            continue
        theme, why = _theme_of(tr.get("theme"), _lead(b["shots"]), themes, tr.get("theme_else"))
        theme = story(theme)
        if why and why not in notes:
            notes.append(why)
        hits = []
        for h in tr.get("hits") or []:
            s = {"start": b["shots"][0], "last": b["shots"][-1], "end": b["shots"][-1]}[h["at"]]
            hits.append({"kind": h["kind"], "shot": s["id"], "end": h["at"] == "end",
                         "name": f"{b['beat']}: {h['kind']}"})
        pieces = [p for g in gaps(b["shots"]) for p in split(g)] if tr["music"] == "gaps" else split(b["shots"])
        for n, sh in enumerate(pieces):
            t0, t1 = _span(sh)
            ids = {s["id"] for s in sh}
            mine = [h for h in hits if h["shot"] in ids]
            sec = section(b, tr, t0, t1)
            if n:
                sec["name"] = (sec["name"] + " (cont.)")[:40]
            prev = cues[-1] if cues else None
            joins = (not by_seq and prev is not None and prev["kind"] == "cue" and tr["music"] != "gaps"
                     and not prev.get("gaps")
                     and n == 0 and t0 <= prev["t1"] + 1e-3
                     and (prev["theme"] == theme or (prev.get("makes") == "story" and theme == "story"))
                     and t1 - prev["t0"] <= CUE_MAX
                     and not any(h["kind"] == "drop" and h["end"] for h in prev["hits"]))
            if joins:
                prev["t1"] = t1
                prev["sections"].append(sec)
                prev["beats"].append(b["beat"])
                # a turn where the beat starts, unless one of its own hits is there already
                if not any(h["shot"] == sh[0]["id"] and not h["end"] for h in mine):
                    mine.insert(0, {"kind": "turn", "shot": sh[0]["id"], "end": False,
                                    "name": f"{b['beat']}: turn"})
                prev["hits"] += mine
                continue
            cue = {"kind": "cue", "t0": t0, "t1": t1, "theme": theme, "beats": [b["beat"]],
                   "sections": [sec], "hits": mine, "strength": tr.get("strength"),
                   "gaps": tr["music"] == "gaps"}
            if theme == "story" and story_made is None:
                story_made = cue
                cue["theme"] = None
                cue["makes"] = "story"
            cues.append(cue)

    def sting(t0: float, theme_name, b_name: str, words: str, kind: str = "sting", en=(3, 3), strength=None):
        t0 = max(0.0, min(t0, total - 0.5))
        t1 = min(total, t0 + STING)
        theme, why = _theme_of(theme_name, None, themes)
        theme = story(theme)
        if why and why not in notes:
            notes.append(why)
        if theme == "story":
            theme = None if story_made is None else "story"
        return {"kind": kind, "t0": t0, "t1": t1, "theme": theme, "beats": [b_name], "hits": [],
                "strength": strength,
                "sections": [{"name": b_name[:40], "words": words, "from": float(en[0]), "to": float(en[1]),
                              "seconds": round(t1 - t0, 3)}]}

    for b in beats:
        tr = b["tr"]
        if tr["music"] == "sting":
            t0 = b["t0"] if tr.get("sting_at") == "start" else b["t1"] - STING
            cues.append(sting(t0, tr.get("theme"), b["beat"], tr.get("words") or "", en=tr.get("energy") or (3, 3),
                              strength=tr.get("strength")))
        elif tr.get("sting_end"):
            cues.append(sting(b["t1"] - STING, tr.get("then") or tr.get("theme"), f"{b['beat']}: out",
                              tr.get("words") or "", en=tr.get("energy") or (3, 3)))

    def covered(t0: float, t1: float) -> bool:
        return any(c["t0"] < t1 and t0 < c["t1"] for c in cues)

    # `// theme:` marks
    for sid, words in (marks.get("themes") or {}).items():
        if sid not in pos:
            continue
        s = shots[pos[sid]]
        theme_name, _, how = (w.strip() for w in words.partition(","))
        mode = (fmt.get("marks") or {}).get(theme_name) or ("sting" if "sting" in how.lower() else "under")
        if mode == "sting":
            st_ = sting(s["t"], theme_name, f"{sid}: {theme_name}", how, en=(2, 2))
            st_["kind"] = "mark"
            cues.append(st_)
            continue
        scene = [x for x in shots[pos[sid]:] if x["seq"] == s["seq"]]
        t0, t1 = _span(scene)
        if covered(t0, t1):
            flags.append({"kind": "theme", "shot": sid,
                          "text": f"// theme: {words}: a cue already plays there; give it this theme by hand"})
            continue
        theme, why = _theme_of(theme_name, None, themes)
        theme = story(theme)
        if why and why not in notes:
            notes.append(why)
        if theme == "story" and story_made is None:
            theme = None
        cues.append({"kind": "cue", "t0": t0, "t1": t1, "theme": theme, "beats": [f"{sid}: {theme_name}"],
                     "hits": [], "strength": None,
                     "sections": [{"name": f"{sid}: {theme_name}"[:40], "words": ", ".join(x for x in (how, "held low") if x),
                                   "from": 1.0, "to": 2.0, "seconds": round(t1 - t0, 3)}]})

    # a sitcom's bumpers: a show echo at each new sequence location
    if st and st.get("bumpers"):
        for a, b in zip(shots, shots[1:]):
            if a["seq"] == b["seq"] or a["loc"] == b["loc"]:
                continue
            t = b["t"]
            if any(abs(c["t0"] - t) < STING or abs(c["t1"] - t) < 0.5 or c["t0"] < t < c["t1"] for c in cues):
                continue
            cues.append(sting(t - STING / 2, "show", f"bumper {a['loc'] or a['seq']} to {b['loc'] or b['seq']}"[:40],
                              "the show's theme, a short bumper", kind="bumper"))

    # music in the scene, a montage, a title card, a flashback: flagged
    for s in shots:
        m = IN_SCENE.search(s.get("sound") or "")
        if m:
            flags.append({"kind": "in-scene", "shot": s["id"],
                          "text": f"music in the scene (\"{m.group(0)}\"): the score sits out, or takes up its tune"})
    run: list[dict] = []
    for s in shots + [None]:
        if s is not None and not s.get("talk") and s["d"] <= MONTAGE_SHOT:
            run.append(s)
            continue
        if len(run) >= MONTAGE_SHOTS:
            t0, t1 = _span(run)
            if covered(t0, t1):
                flags.append({"kind": "montage", "shot": run[0]["id"],
                              "text": f"a montage ({run[0]['id']}–{run[-1]['id']}, {len(run)} shots): fuller under it"})
            else:
                cues.append({"kind": "cue", "t0": t0, "t1": t1,
                             "theme": "story" if story_made else None, "beats": ["montage"], "hits": [],
                             "strength": None,
                             "sections": [{"name": "montage", "words": "fuller, moving", "from": 3.0, "to": 3.0,
                                           "seconds": round(t1 - t0, 3)}]})
                flags.append({"kind": "montage", "shot": run[0]["id"],
                              "text": f"a montage ({run[0]['id']}–{run[-1]['id']}, {len(run)} shots): one cue across it"})
        run = []
    for s in {shots[0]["id"]: shots[0], shots[-1]["id"]: shots[-1]}.values():
        if s.get("target") == "hold":
            if covered(s["t"], s["t"] + s["d"]):
                flags.append({"kind": "card", "shot": s["id"], "text": "a title or credits card: the show theme, stated"})
            else:
                c = sting(s["t"], "show", f"{s['id']}: card", "the main title, stated", en=(3, 3))
                c["t1"] = s["t"] + s["d"]
                c["sections"][0]["seconds"] = round(s["d"], 3)
                cues.append(c)
    for sid in marks.get("flashback") or []:
        if sid in pos:
            flags.append({"kind": "flashback", "shot": sid,
                          "text": "a flashback: its theme's echo, thinner and further away"})

    cues.sort(key=lambda c: (c["t0"], c["kind"] != "cue"))
    out_cues = []
    for c in cues:
        prelap = PRELAP if c["kind"] == "cue" and c["t0"] > 0 else 0.0
        a = anchor(max(0.0, c["t0"] - prelap))
        z = anchor(c["t1"], end=True)
        if c["kind"] == "cue" and prelap:
            c["sections"][0]["seconds"] = round(c["sections"][0]["seconds"] + prelap, 3)
        label = " → ".join(dict.fromkeys(x for x in c["beats"] if x))
        out_cues.append({"kind": c["kind"], "label": label, "in": a, "out": z,
                         "t0": round(c["t0"] - prelap, 3), "t1": round(c["t1"], 3),
                         "theme": c["theme"], "makes": c.get("makes"), "strength": c.get("strength"),
                         "sections": c["sections"], "hits": c["hits"]})
    out_beats = [{"beat": b["beat"], "from": b["from"], "music": b["tr"]["music"], "t0": round(b["t0"], 3),
                  "t1": round(b["t1"], 3), "shot": b["shots"][0]["id"]} for b in beats]
    return {"structure": st["name"] if st else None, "beats": out_beats, "cues": out_cues,
            "flags": flags, "notes": notes}
