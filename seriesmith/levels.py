"""
levels.py — how loud the lines are: each sound file's speech readings, measured once and
cached, and the levelling the export does (mix.level_dialogue) worked out from them for Play
all (docs/LEVELLING.md).

A file's readings are its mono power every WINDOW seconds, in dB full scale, from its start:
<ep>/_cache/levels/<sha1 of path|size|mtime>.json, so a new take, voice stem or dub is a new
file and is measured fresh. They're made as the sound is (a finished take, beside its checks;
a voice stem as it's split off), when an episode opens (whatever its cut still lacks), and
on the spot for anything else asked for; a span's speech level is read from them, so a trim
needs no new measurement.

The arithmetic is the export's: a stretch's speech level is the mean power of its readings
within GATE dB of its loudest and above FLOOR (level_of); each speaking clip is moved to the
middle (the median) of their levels, at most the mix's limit_db either way (gains_of).
"""
from __future__ import annotations

import hashlib
import json
import os
import threading

from seriesmith.core import fileio as F

WINDOW = 0.05          # seconds per reading
GATE = 30.0            # dB under a stretch's loudest reading: quieter isn't speech
FLOOR = -60.0          # dBFS: nothing quieter is speech
MIN_SPEECH = 0.5       # seconds of speech a stretch needs to be measured
RATE = 48000           # what a file is decoded at to measure it (the mix's rate)
CACHE_DIR = os.path.join("_cache", "levels")
VERSION = 2
# whether warm() measures in the background (off in the tests, which measure by name)
WARM = os.environ.get("SERIESMITH_LEVELS_WARM", "1") != "0"

_lock = threading.Lock()
_warming: set[str] = set()


def _np():
    import numpy as np
    return np


def window_db(mono):
    """A mono buffer's readings: its mean power every WINDOW seconds at RATE, dB."""
    np = _np()
    w = max(1, int(RATE * WINDOW))
    k = len(mono) // w
    if k == 0:
        return np.zeros(0, dtype=np.float64)
    power = (mono[:k * w].astype(np.float64).reshape(k, w) ** 2).mean(1)
    return 10 * np.log10(np.maximum(power, 1e-12))


def level_of(db) -> float | None:
    """A stretch's speech level from its readings, dB: the mean power of those within GATE dB
    of its loudest and above FLOOR; None with less than MIN_SPEECH seconds of them."""
    np = _np()
    db = np.asarray(db, dtype=np.float64)
    if not len(db):
        return None
    keep = db[(db >= db.max() - GATE) & (db >= FLOOR)]
    if len(keep) * WINDOW < MIN_SPEECH:
        return None
    return float(10 * np.log10((10 ** (keep / 10)).mean()))


def gains_of(levels: dict[str, float], limit_db: float) -> tuple[float | None, dict[str, float]]:
    """(the middle level, each clip's change in dB): every clip moved to the median of
    `levels`, at most `limit_db` up or down. Nothing with fewer than two levels or no limit."""
    np = _np()
    if limit_db <= 0 or len(levels) < 2:
        return None, {}
    middle = float(np.median(list(levels.values())))
    return middle, {s: max(-limit_db, min(limit_db, middle - lv)) for s, lv in levels.items()}


def _cache_path(ep: str, path: str) -> str:
    st = os.stat(path)
    key = f"{os.path.normcase(os.path.abspath(path))}|{st.st_size}|{st.st_mtime_ns}"
    return os.path.join(ep, CACHE_DIR, hashlib.sha1(key.encode("utf-8")).hexdigest() + ".json")


def cached(ep: str, path: str) -> list[float] | None:
    """A file's readings when they're measured already (None: not yet, or no such file)."""
    try:
        got = F.read_json_or(_cache_path(ep, path), None)
    except OSError:
        return None
    if isinstance(got, dict) and got.get("v") == VERSION and isinstance(got.get("db"), list):
        return got["db"]
    return None


def readings(ep: str, path: str) -> list[float] | None:
    """A file's readings, measured now unless cached (an empty list: it has no sound). None
    when there's no such file. RuntimeError-free: a file that won't decode reads as silent."""
    if not path or not os.path.isfile(path):
        return None
    got = cached(ep, path)
    if got is not None:
        return got
    from seriesmith import mix as MX
    # stereo, averaged, as the export lays and measures it (ffmpeg's own mono downmix keeps
    # the power of both channels: 3 dB over the export's level)
    buf = MX.decode(path, rate=RATE, channels=2)
    db = [round(float(x), 2) for x in window_db(buf.mean(1) if len(buf) else buf[:, 0])]
    try:
        F.write_json(_cache_path(ep, path), {"v": VERSION, "window": WINDOW, "db": db})
    except OSError:
        pass
    return db


def level_between(db: list[float], start: float, end: float | None) -> float | None:
    """The speech level of a file's readings from `start` to `end` seconds (None: to its end)."""
    a = max(0, int(round(start / WINDOW)))
    b = len(db) if end is None else max(a, int(round(end / WINDOW)))
    return level_of(db[a:b])


def clip_gains(ep: str, clips: list[dict], limit_db: float,
               speaking: set[str] | None) -> dict:
    """Play all's levelling: `clips` [{"shot", "path" (absolute), "from", "to" (seconds of the
    file the cut plays)}], the clips of shots with lines (`speaking`; None: every one) measured
    and moved as the export moves them. {"limit_db", "middle", "gains": {shot: dB},
    "unmeasured": [shots with no speech found or no file]}."""
    levels, unmeasured = {}, []
    if limit_db > 0:
        for c in clips:
            shot = c.get("shot")
            if not shot or (speaking is not None and shot not in speaking):
                continue
            db = readings(ep, c.get("path") or "")
            lv = level_between(db, float(c.get("from") or 0), c.get("to")) if db else None
            if lv is None:
                unmeasured.append(shot)
            else:
                levels[shot] = lv
    middle, gains = gains_of(levels, limit_db)
    return {"limit_db": limit_db, "middle": None if middle is None else round(middle, 2),
            "gains": {s: round(v, 2) for s, v in gains.items()}, "unmeasured": unmeasured}


def warm(ep: str, paths: list[str]) -> None:
    """Measure whichever of `paths` aren't yet, on a thread of their own (one per episode at
    a time): what a finished take, a new stem or an opened episode calls, so Play all and the
    export find them ready."""
    if not WARM:
        return
    todo = [p for p in dict.fromkeys(paths) if p and os.path.isfile(p) and cached(ep, p) is None]
    if not todo:
        return
    key = os.path.normcase(os.path.abspath(ep))
    with _lock:
        if key in _warming:
            return
        _warming.add(key)

    def run() -> None:
        try:
            for p in todo:
                try:
                    readings(ep, p)
                except Exception:                        # noqa: BLE001  a nicety: asked later, it's measured then
                    pass
        finally:
            with _lock:
                _warming.discard(key)
    threading.Thread(target=run, name="levels", daemon=True).start()


def cut_sounds(ep: str, pass_: str) -> list[str]:
    """Every sound file the pass's cut can play for its clips' lines: each clip's take, its
    voice stem when it has one, its own audio source."""
    from seriesmith import edit as E
    from seriesmith import takes as T
    out = []
    for e in E.cut_entries(ep, pass_):
        try:
            t, _, ok = E.cut_take(ep, e)
            if t is not None and ok:
                out += [t.paths.mp4, t.paths.voice]
            if e.audio:
                f = T.audio_source_file(ep, e.audio, pass_)
                if f:
                    out.append(f)
        except Exception:                                # noqa: BLE001  a clip it can't read: asked later
            continue
    return out
