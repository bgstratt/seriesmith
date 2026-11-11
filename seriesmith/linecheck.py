"""
linecheck.py — a take of a line of dialogue (lines.py) checked once it's made: what a voice model
does that the line didn't ask for (docs/SOUND_GUIDE.md, "Line checks"). Recorded on the take in
lines.json as `checks`; a render that asked for retries makes another take of a line that fails,
and keeps the best (runner.enqueue_line).

- **words**: Whisper (on the CPU, the first model downloaded of takecheck.WORDS_MODELS) hears the
  take, matched word by word with the line (takecheck.match); under takecheck.WORDS_MATCH is a
  word dropped, said twice, or garbled.
- **long**: the take runs past LONG times the line's spoken length (core.speech, with its air)
  plus LONG_PAD seconds: a model that kept going after the words (Drama 3 ends at end of speech
  when it's well; a stall runs on to its limit).
- **gap**: a silence of GAP seconds or more between its first and last sound: a stall mid-line.

Never raises (a take that can't be read has none); a check is a reason to listen, not a verdict.
"""
from __future__ import annotations

import os
import wave

from seriesmith import takecheck as TC

VERSION = 1
LONG = 2.0
LONG_PAD = 2.0
GAP = 1.2                   # seconds of silence inside a line
WINDOW = 0.05               # seconds per level reading
QUIET_DB = -45.0            # a window this far under the take's loudest is silence


def levels(path: str) -> tuple[list[float], float]:
    """(each WINDOW's peak level in dB under the take's loudest, its seconds). numpy."""
    import numpy as np
    with wave.open(path, "rb") as w:
        rate, ch, width, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(n)
    if width != 2:
        raise ValueError(f"{os.path.basename(path)}: {8 * width}-bit, not 16")
    a = np.frombuffer(raw, "<i2").astype(np.float32)
    if ch > 1:
        a = a.reshape(-1, ch).mean(1)
    step = max(1, int(rate * WINDOW))
    k = len(a) // step
    if k == 0:
        return [], n / float(rate)
    peaks = np.abs(a[:k * step]).reshape(k, step).max(1)
    top = float(peaks.max()) or 1.0
    db = 20 * np.log10(np.maximum(peaks, 1e-6) / top)
    return [float(x) for x in db], n / float(rate)


def longest_gap(db: list[float]) -> float:
    """The longest run of silent windows between the first and the last that aren't, seconds."""
    loud = [i for i, x in enumerate(db) if x > QUIET_DB]
    if len(loud) < 2:
        return 0.0
    best = run = 0
    for x in db[loud[0]:loud[-1] + 1]:
        run = run + 1 if x <= QUIET_DB else 0
        best = max(best, run)
    return round(best * WINDOW, 2)


def check(ep: str, path: str, text: str, words: bool = True) -> dict:
    """A take's checks, read now: {"v", "seconds", "expected", "gap", "words": {...} | {"why"},
    "flags"}. ValueError / OSError when its file can't be read."""
    from seriesmith.targets.audio.common import spoken_seconds
    db, seconds = levels(path)
    expected = round(spoken_seconds(text), 2)
    gap = longest_gap(db)
    out = {"v": VERSION, "seconds": round(seconds, 2), "expected": expected, "gap": gap}
    flags = []
    if seconds > LONG * expected + LONG_PAD:
        flags.append("long")
    if gap >= GAP:
        flags.append("gap")
    if words:
        model, why = TC.words_model()
        if model is None:
            out["words"] = {"why": why}
        else:
            try:
                got = TC.heard(ep, path, model)
                out["words"] = {"heard": got, "match": TC.match(text, got), "model": model}
                if out["words"]["match"] < TC.WORDS_MATCH:
                    flags.append("words")
            except Exception as e:              # noqa: BLE001  TrackError, no faster-whisper, ...
                out["words"] = {"why": str(e)[:200]}
    out["flags"] = flags
    return out


def score(checks: dict | None) -> tuple:
    """How good a take looks by its checks, for keeping the best: no flags first, then the
    words heard, then the shortest silence."""
    c = checks or {}
    return (not c.get("flags"), (c.get("words") or {}).get("match") or 0.0, -(c.get("gap") or 0.0))


def reasons(checks: dict | None) -> list[str]:
    c = checks or {}
    out = []
    for f in c.get("flags") or []:
        if f == "words":
            out.append(f"its words {round(100 * c['words']['match'])}% of the line "
                       f"(heard \"{c['words'].get('heard') or ''}\")")
        elif f == "long":
            out.append(f"{c['seconds']} s for a line of about {c['expected']} s")
        elif f == "gap":
            out.append(f"a {c['gap']} s silence inside it")
    return out


def record(ep: str, line_id: str, n: int, text: str) -> dict | None:
    """Check take `n` of a line into lines.json; its checks, or None (not finished, unreadable)."""
    from seriesmith import lines as LN
    from seriesmith.core.paths import show_file
    row = (LN.load(ep)["lines"].get(line_id) or {})
    take = next((t for t in row.get("takes") or [] if t.get("take") == n), None)
    if not take or take.get("status") != "ok" or not take.get("file"):
        return None
    try:
        c = check(ep, show_file(ep, take["file"]), text)
    except (OSError, ValueError, EOFError, wave.Error):
        return None
    LN.set_take_fields(ep, line_id, n, checks=c)
    return c
