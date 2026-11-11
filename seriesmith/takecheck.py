"""
takecheck.py — a finished take looked over for what it wasn't asked to do, never changed
(docs/EDITOR.md, "Take checks"). Two checks, recorded in the take's record as `checks`:

**A cut it wasn't asked for.** A video model asked for one continuous shot sometimes cuts to
another place partway through. One ffmpeg pass over the picture at SCALE_W wide (`scdet`: each
frame's scene-change score, 0-100); a frame scoring CUT_SCORE or more is a hard cut. Measured
2026-11-10 on 213 takes (H3 Ref2VA, FastH3 Omni, FL2VA): every real cut scored 12.6 to 54, while
an explosion's flash, fast running and a whip pan scored 10.6 at most; the median take's highest
frame is under 1. A `continuous: multishot` group's own cuts (its members' starts, within
ASKED_FRAMES) were asked for. A place that drifts into another during a continuous camera move
isn't a cut, and isn't seen here.

**Its words.** When the model voiced the take's lines (audio_policy `generate` or `clone`) and the shot has
lines, Whisper (the first of WORDS_MODELS downloaded: small.en is quick and plenty; on the CPU, so
the GPU stays ComfyUI's) hears the take's sound through
align (track.transcribe_file, which keeps `<sound>.words.json` beside it), and what it heard is
compared with the script's lines, word by word (difflib over lowercase words). Below WORDS_MATCH
is flagged: a line dropped, cut short or garbled. A take whose shot's lines changed since it was
rendered compares against the new ones (its staleness says so). Measured 2026-11-10: 1.7 s a take
on the CPU; LAST LIGHT's and the A/B's speaking takes all heard word for word. Skipped (`words`
null, `why` said) when faster-whisper or the model isn't there.

    check(root, take) -> checks           both, read now
    record(root, take)                    checks into its record; never raises
    checks_of(sidecar, mp4) -> checks     the recorded ones, unless the mp4 changed since
    flags(checks) -> ["cut", "words"]     what to look at

A check is a reason to look, not a verdict: nothing is re-rendered or picked by it.
"""
from __future__ import annotations

import difflib
import os
import re
import subprocess

from seriesmith import ff as FF

VERSION = 1
SCALE_W = 256
CUT_SCORE = 12.0
ASKED_FRAMES = 3
WORDS_MODELS = ("small.en", "base.en", "medium.en", "large-v3-turbo", "large-v3", "tiny.en")
WORDS_MATCH = 0.85
MODEL_SPEAKS = ("generate", "clone")        # the audio policies whose lines the model voices
TIMEOUT = 300

_SCORE = re.compile(r"lavfi\.scd\.score=([\d.]+)")
_WORD = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)*")


# ---------------------------------------------------------------------------
# cuts
# ---------------------------------------------------------------------------

def scores(mp4: str, timeout: int = TIMEOUT) -> list[float]:
    """Each frame's scene-change score (scdet, 0-100), in order. RuntimeError when ffmpeg fails."""
    r = subprocess.run([*FF.tool("ffmpeg"), "-hide_banner", "-nostats", "-v", "info", "-i", mp4,
                        "-map", "0:v:0", "-vf",
                        f"scale={SCALE_W}:-2,scdet=threshold=100,metadata=mode=print:key=lavfi.scd.score",
                        "-an", "-f", "null", "-"], capture_output=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace")[-400:])
    return [float(x) for x in _SCORE.findall(r.stderr.decode("utf-8", "replace"))]


def cuts(per_frame: list[float], fps: float, asked: list[int] = ()) -> list[dict]:
    """The hard cuts in a take's scores that weren't asked for: [{"frame", "t", "score"}]."""
    out = []
    for n, s in enumerate(per_frame):
        if n == 0 or s < CUT_SCORE:
            continue
        if any(abs(n - a) <= ASKED_FRAMES for a in asked):
            continue
        out.append({"frame": n, "t": round(n / fps, 2) if fps else None, "score": round(s, 1)})
    return out


def asked_cuts(frozen_shot: dict | None) -> list[int]:
    """The frames a take was asked to cut at: a multishot group's members' starts after the first."""
    members = (frozen_shot or {}).get("multishot") or []
    return [int(m.get("start") or 0) for m in members[1:] if isinstance(m, dict)]


# ---------------------------------------------------------------------------
# words
# ---------------------------------------------------------------------------

def words_of(text: str) -> list[str]:
    return _WORD.findall((text or "").lower().replace("’", "'"))


def match(want: str, heard: str) -> float:
    """How closely what was heard follows what was wanted, 0-1, word by word."""
    a, b = words_of(want), words_of(heard)
    if not a and not b:
        return 1.0
    return round(difflib.SequenceMatcher(None, a, b, autojunk=False).ratio(), 2)


def wanted_words(root: str, shot_ids: list[str]) -> str:
    """The script's lines of these shots, in order, joined."""
    from seriesmith import lines as LN
    by_id = {s["id"]: s for s in LN.script_shots(root)}
    return " ".join(ln["text"] for sid in shot_ids for ln in (by_id.get(sid) or {}).get("lines", []))


def words_model() -> tuple[str | None, str | None]:
    """(the Whisper model the word check listens with, None) or (None, why there's none)."""
    from seriesmith import track as K
    first = None
    for m in WORDS_MODELS:
        why = K.whisper_missing(m)
        if why is None:
            return m, None
        first = first or why
    return None, first


def heard(root: str, sound: str, model: str) -> str:
    """What Whisper hears in a take's sound, on the CPU. TrackError when it can't."""
    from seriesmith import track as K
    got = K.transcribe_file(sound, root, "", model=model, device="cpu")
    return " ".join(str(w.get("word") or "").strip() for w in got).strip()


def words_check(root: str, take, frozen_shot: dict | None) -> dict | None:
    """{"want", "heard", "match"} for a take whose sound the model made and whose shot speaks;
    {"why"} when it can't be heard here; None when there's nothing to hear."""
    from seriesmith import takes as T
    shot = frozen_shot or {}
    if (shot.get("audio_policy") or "generate") not in MODEL_SPEAKS:
        return None
    ids = [m["id"] for m in shot.get("multishot") or [] if isinstance(m, dict) and m.get("id")] \
        or [take.shot]
    try:
        want = wanted_words(root, ids)
    except (OSError, ValueError, KeyError) as e:   # no script to read, or two
        return {"why": f"the script's lines can't be read: {str(e)[:160]}"}
    if not words_of(want):
        return None
    sound = T.take_sound(take)
    if not sound:
        return {"why": "the take has no sound"}
    model, why = words_model()
    if model is None:
        return {"why": why}
    try:
        got = heard(root, sound, model)
    except Exception as e:                      # noqa: BLE001  TrackError, no faster-whisper, ...
        return {"why": str(e)[:200]}
    return {"want": want, "heard": got, "match": match(want, got), "model": model}


# ---------------------------------------------------------------------------
# the record
# ---------------------------------------------------------------------------

def _frozen_shot(take) -> dict | None:
    from seriesmith.core import fileio as F
    doc = F.read_json_or(take.paths.shotlist, None, want=dict)
    shots = (doc or {}).get("shots") or []
    return shots[0] if shots and isinstance(shots[0], dict) else None


def check(root: str, take, words: bool = True) -> dict:
    """A finished take's checks, read now. RuntimeError when its picture can't be read."""
    sc = take.sidecar or {}
    shot = _frozen_shot(take)
    fps = float(sc.get("fps") or (shot or {}).get("fps") or 24.0)
    found = cuts(scores(take.paths.mp4), fps, asked_cuts(shot))
    out = {"v": VERSION, "size": os.path.getsize(take.paths.mp4),
           "cuts": found, "cut_score": CUT_SCORE}
    if words:
        out["words"] = words_check(root, take, shot)
        out["words_match"] = WORDS_MATCH
    return out


def flags(checks: dict | None) -> list[str]:
    """What a take's checks ask to look at: "cut", "words"."""
    if not checks:
        return []
    out = ["cut"] if checks.get("cuts") else []
    w = checks.get("words") or {}
    if w.get("match") is not None and w["match"] < checks.get("words_match", WORDS_MATCH):
        out.append("words")
    return out


def checks_of(sidecar: dict | None, mp4: str | None = None, size: int | None = None) -> dict | None:
    """A take's recorded checks, unless its mp4 has changed since (its size: `size` when the
    caller has it, else read) or they're an older kind."""
    c = (sidecar or {}).get("checks")
    if not isinstance(c, dict) or c.get("v") != VERSION:
        return None
    if size is None and mp4 and c.get("size") and os.path.isfile(mp4):
        size = os.path.getsize(mp4)
    if size is not None and c.get("size") and size != c["size"]:
        return None
    return c


def summary(sidecar: dict | None, mp4: str | None = None, size: int | None = None) -> dict | None:
    """What the editor shows of a take's checks: {"flags", "cuts": [t], "match", "heard",
    "want", "why"}; None when it hasn't any (or they're out of date)."""
    c = checks_of(sidecar, mp4, size)
    if c is None:
        return None
    w = c.get("words") or {}
    return {"flags": flags(c), "cuts": [x.get("t") for x in c.get("cuts") or []],
            "match": w.get("match"), "heard": w.get("heard"), "want": w.get("want"),
            "why": w.get("why")}


def record(root: str, take, words: bool = True) -> dict | None:
    """Check a finished take into its record (`checks`), once its status is ok. Never raises
    (a take that can't be read just has none); the checks, or None."""
    from seriesmith import takes as T
    try:
        sc = T.read_sidecar(take.paths.sidecar) or {}
        if sc.get("status") != "ok" or not os.path.isfile(take.paths.mp4):
            return None
        take.sidecar = sc
        c = check(root, take, words=words)
        take.sidecar = T.update_sidecar(take.paths.sidecar, checks=c)
        return c
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        return None
