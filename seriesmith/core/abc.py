"""
abc.py — ABC notation read for what a song's plan says (docs/SOUND.md "Measured: YuE2").

YuE2 plans a song as ABC before it sings it (YuE2GenerateABC; SheetSage2 transcribes a
recording into the same form): a header (`M:` meter, `L:` the unit note length, `Q:` tempo,
`K:` key, `V:` voices), then the body in blocks per voice, each section opened by a `%`
comment (`% verse`). This reads what the cue needs of it:

    read(text) -> {"meter": "2/4", "unit": "1/32", "tempo": 93.0 | None, "tempo_unit": "1/4",
                   "key": "D", "voices": ["Vocal", "Ins"], "melody": "Vocal",
                   "sections": [{"name": "intro", "start": 0.0, "beats": 18.0, "bars": 9}, ...],
                   "beats": 210.0, "bars": 105, "first_note": 16.5 | None}

`beats` count the tempo's beat (the `Q:` line's note, a quarter when it has none), so a
section starts `start x 60 / bpm` seconds into the song. A section's length is its longest
voice's: each note's length counted (the `L:` unit times its multiplier: `4`, `/2`, `3/2`,
`//`; a chord `[CEG]` by its first note; tuplets `(3`), ties and slurs, chord symbols in
quotes, decorations, grace notes and inline fields ignored; rests `z` / `x` counted, a
multi-bar rest `Z4` as four bars; `|` ends a bar, and a passage repeated with `|: ... :|` is
counted twice (approximately: endings `[1` / `[2` are not followed). Bars are bar lines
(a part bar at a section's end counts as one), so a pickup and a held note leave the beats
exact and the bars close. `first_note` is the first note (not a rest) of the melody voice
(the first declared, the vocal in YuE2's plans), in beats from the start.

`set_tempo(text, bpm)` sets the `Q:` line as the cue graph's two RegexReplace nodes do
(targets/music/yue2: every `Q:` line dropped, one put after the `L:` line, where YuE2 writes
it: put after the voices, before `K:`, it was sung at 88 of 96 bpm, twice, 2026-11-01);
`melody(text)`
drops the chord symbols, the form YuE2's `melody` mode and SheetSage2's melody transcription
use.

Stdlib only.
"""
from __future__ import annotations

import re
from fractions import Fraction

# the RegexReplace patterns the yue2 graph uses (multiline), here for the same result in Python
Q_LINE = r"^Q:.*\n?"
L_LINE = r"^(L:.*)$"
K_LINE = r"^K:"
_FIELD = re.compile(r"^([A-Za-z]):\s*(.*)$")
_LENGTH = re.compile(r"(\d*)(/*)(\d*)")
# the fields a body line may be (a voice, a key or meter change, words): any other is music
_BODY_FIELDS = "VKLMQPTNwW"
_TEMPO = re.compile(r"(\d+)\s*/\s*(\d+)\s*=\s*(\d+(?:\.\d+)?)")


def _frac(s: str, default: Fraction) -> Fraction:
    m = re.match(r"\s*(\d+)\s*/\s*(\d+)", s or "")
    if m and int(m.group(2)):
        return Fraction(int(m.group(1)), int(m.group(2)))
    return default


def _length(s: str, i: int) -> tuple[Fraction, int]:
    """The multiplier written after a note at s[i:] (`4`, `/2`, `3/2`, `//`) and where it ends."""
    m = _LENGTH.match(s, i)
    num, slashes, den = m.group(1), m.group(2), m.group(3)
    n = int(num) if num else 1
    if not slashes:
        return Fraction(n), m.end()
    d = int(den) * 2 ** (len(slashes) - 1) if den else 2 ** len(slashes)
    return Fraction(n, d or 1), m.end()


class _Voice:
    """One voice's count inside one section: its duration, its bar lines, where its first
    note fell."""

    def __init__(self):
        self.dur = Fraction(0)        # whole notes
        self.bars = 0
        self.since_bar = Fraction(0)
        self.rep_dur = Fraction(0)    # since the last |: (or the section's start)
        self.rep_bars = 0
        self.first = None             # whole notes into the section of its first note
        self.tuplet = (0, Fraction(1))

    def add(self, d: Fraction, note: bool) -> None:
        left, k = self.tuplet
        if left:
            d *= k
            self.tuplet = (left - 1, k)
        if note and self.first is None:
            self.first = self.dur
        self.dur += d
        self.since_bar += d
        self.rep_dur += d

    def bar(self, n: int = 1) -> None:
        if self.since_bar <= 0:
            return                    # a bar line with nothing before it (|: at the start)
        self.bars += n
        self.rep_bars += n
        self.since_bar = Fraction(0)

    def close(self) -> None:
        """The section ends: a part bar left over counts as one."""
        if self.since_bar > 0:
            self.bar()


def _scan(line: str, v: _Voice, unit: Fraction, bar_len: Fraction) -> None:
    """One body line of music into voice `v`'s count."""
    i, n = 0, len(line)
    while i < n:
        c = line[i]
        if c == "%":
            break
        if c == '"':                                   # a chord symbol or annotation
            j = line.find('"', i + 1)
            i = n if j < 0 else j + 1
        elif c in "!+":                                # a decoration !trill! / +trill+
            j = line.find(c, i + 1)
            i = n if j < 0 else j + 1
        elif c == "{":                                 # grace notes take no time
            j = line.find("}", i + 1)
            i = n if j < 0 else j + 1
        elif c == "[" and i + 2 < n and line[i + 1].isalpha() and line[i + 2] == ":":
            j = line.find("]", i)                      # an inline field [K:D]
            i = n if j < 0 else j + 1
        elif c == "[" and i + 1 < n and line[i + 1].isdigit():
            i += 2                                     # an ending [1
        elif c == "[" and i + 1 < n and line[i + 1] == "|":
            i += 2
            v.bar()
        elif c == "[":                                 # a chord: its first note's length
            j = line.find("]", i)
            if j < 0:
                break
            inner = line[i + 1:j]
            m = re.search(r"[A-Ga-g][',]*", inner)
            first = Fraction(1)
            if m:
                first, _ = _length(inner, m.end())
            mult, i = _length(line, j + 1)
            v.add(unit * first * mult, True)
        elif c in "|:":
            j = i
            while j < n and line[j] in "|:]":
                j += 1
            tok = line[i:j]
            while j < n and line[j].isdigit():         # |1 an ending
                j += 1
            i = j
            if "|" not in tok and tok != "::":
                continue
            v.bar()
            if tok.startswith(":"):                    # :| the passage again
                v.dur += v.rep_dur
                v.bars += v.rep_bars
            if tok.startswith(":") or tok.endswith(":"):   # |: a repeat starts (or :|: both)
                v.rep_dur, v.rep_bars = Fraction(0), 0
        elif c in "^_=":
            i += 1
        elif c in "ABCDEFGabcdefg":
            j = i + 1
            while j < n and line[j] in "',":
                j += 1
            mult, i = _length(line, j)
            v.add(unit * mult, True)
        elif c in "zx":
            mult, i = _length(line, i + 1)
            v.add(unit * mult, False)
        elif c in "ZX":
            m = re.match(r"\d+", line[i + 1:])
            bars = int(m.group(0)) if m else 1
            i += 1 + (len(m.group(0)) if m else 0)
            v.add(bar_len * bars, False)
            v.since_bar = Fraction(0)
            v.bars += bars
            v.rep_bars += bars
            # its own bar line follows: that one closes nothing more
            k = i
            while k < n and line[k] == " ":
                k += 1
            if k < n and line[k] == "|" and (k + 1 >= n or line[k + 1] != ":"):
                i = k + 1
        elif c == "(":
            m = re.match(r"\((\d)(?::(\d)?)?(?::(\d))?", line[i:])
            if m:
                p = int(m.group(1))
                q = int(m.group(2)) if m.group(2) else {2: 3, 3: 2, 4: 3, 6: 2, 8: 3}.get(p, 2)
                r = int(m.group(3)) if m.group(3) else p
                v.tuplet = (r, Fraction(q, p))
                i += len(m.group(0))
            else:
                i += 1                                 # a slur
        else:
            i += 1                                     # ties, slurs, spaces, decorations


def read(text: str) -> dict:
    """What a plan says: its header and its sections' lengths (the module's docstring)."""
    header: dict[str, str] = {}
    voices: list[str] = []
    sections: list[dict] = []          # {"name", "voices": {name: _Voice}}
    cur_voice = None
    in_body = False
    unit = bar_len = None

    def section(name: str) -> dict:
        s = {"name": name, "voices": {}}
        sections.append(s)
        return s

    for raw in (text or "").replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("%%"):
            continue
        if line.startswith("%"):
            if in_body:
                section(line[1:].strip())
            continue
        m = _FIELD.match(line)
        if m and (not in_body or m.group(1) in _BODY_FIELDS):
            key, val = m.group(1), m.group(2).strip()
            if key == "V":
                name = val.split()[0] if val.split() else "1"
                if name not in voices:
                    voices.append(name)
                cur_voice = name
                continue
            if key in "wW":
                continue
            if not in_body:
                header.setdefault(key, val)
                if key == "K":
                    in_body = True
            continue
        if not in_body:
            in_body = True
        if unit is None:
            unit = _frac(header.get("L", ""), Fraction(1, 8))
            meter = header.get("M", "4/4").strip()
            bar_len = Fraction(1) if meter in ("C", "C|") else _frac(meter, Fraction(1))
        if not sections:
            section("")
        name = cur_voice or (voices[0] if voices else "1")
        if name not in voices:
            voices.append(name)
        vs = sections[-1]["voices"]
        _scan(line, vs.setdefault(name, _Voice()), unit, bar_len)

    tempo_unit, tempo = Fraction(1, 4), None
    q = header.get("Q", "")
    m = _TEMPO.search(q)
    if m:
        tempo_unit, tempo = Fraction(int(m.group(1)), int(m.group(2))), float(m.group(3))
    elif re.fullmatch(r"\s*\d+(\.\d+)?\s*", q or ""):
        tempo_unit = unit or _frac(header.get("L", ""), Fraction(1, 8))
        tempo = float(q)
    melody = voices[0] if voices else None
    out_secs, start, first = [], Fraction(0), None
    for s in sections:
        for v in s["voices"].values():
            v.close()
        if not s["voices"]:
            continue
        longest = max(s["voices"].values(), key=lambda v: v.dur)
        if longest.dur == 0 and not s["name"]:
            continue
        mv = s["voices"].get(melody)
        if first is None and mv is not None and mv.first is not None:
            first = start + mv.first
        out_secs.append({"name": s["name"] or "start", "start": _beats(start, tempo_unit),
                         "beats": _beats(longest.dur, tempo_unit), "bars": longest.bars})
        start += longest.dur
    return {"meter": header.get("M", "4/4"), "unit": header.get("L", "1/8"),
            "tempo": tempo, "tempo_unit": f"{tempo_unit.numerator}/{tempo_unit.denominator}",
            "key": header.get("K", ""), "voices": voices, "melody": melody,
            "sections": out_secs, "beats": _beats(start, tempo_unit),
            "bars": sum(s["bars"] for s in out_secs),
            "first_note": _beats(first, tempo_unit) if first is not None else None}


def _beats(whole: Fraction, beat: Fraction) -> float:
    return round(float(whole / beat), 4)


def set_tempo(text: str, bpm: int | float, unit: str = "1/4") -> str:
    """The plan with its tempo `Q:{unit}={bpm}`: every Q: line dropped, one put after the
    first L: line, as the graph's RegexReplace nodes do it (with no L: line, before the K:
    line, or after X:, which the graph doesn't do)."""
    q = f"Q:{unit}={_num(bpm)}"
    out = re.sub(Q_LINE, "", text, flags=re.M)
    if re.search(L_LINE, out, flags=re.M):
        return re.sub(L_LINE, lambda m: m.group(1) + "\n" + q, out, count=1, flags=re.M)
    if re.search(K_LINE, out, flags=re.M):
        return re.sub(K_LINE, q + "\nK:", out, count=1, flags=re.M)
    if re.search(r"^X:.*$", out, flags=re.M):
        return re.sub(r"^(X:.*)$", lambda m: m.group(1) + "\n" + q, out, count=1, flags=re.M)
    return q + "\n" + out


def _num(x) -> str:
    return str(int(x)) if float(x) == int(x) else f"{float(x):g}"


def melody(text: str) -> str:
    """The plan without its chord symbols (the body's quoted "D", "A/C#"): YuE2's `melody`
    mode, as SheetSage2 transcribes for it."""
    out, body = [], False
    for line in text.replace("\r\n", "\n").split("\n"):
        if body and not line.lstrip().startswith("%") and not _FIELD.match(line.strip()):
            line = re.sub(r'"[^"]*"', "", line)
        if line.startswith("K:"):
            body = True
        out.append(line)
    return "\n".join(out)


def times(info: dict, bpm: float) -> list[dict]:
    """Each section's start and length in seconds at `bpm` (of the plan's beat):
    [{"name", "start", "seconds", "bars", "beats"}]."""
    k = 60.0 / bpm
    return [{"name": s["name"], "start": round(s["start"] * k, 3), "seconds": round(s["beats"] * k, 3),
             "bars": s["bars"], "beats": s["beats"]} for s in info.get("sections") or []]
