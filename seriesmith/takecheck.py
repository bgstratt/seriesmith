"""
takecheck.py — a finished take looked over for what it wasn't asked to do, never changed
(docs/EDITOR.md, "Take checks"). Two checks, recorded in the take's record as `checks`:

**A cut it wasn't asked for.** A video model asked for one continuous shot sometimes cuts to
another place partway through. One ffmpeg pass over the picture at SCALE_W wide (`scdet`: each
frame's scene-change score, 0-100); a frame scoring CUT_SCORE or more is a hard cut. Measured
2026-11-10 on 213 takes (H3 Ref2VA, FastH3 Omni, FL2VA): every real cut scored 12.6 to 54, while
an explosion's flash, fast running and a whip pan scored 10.6 at most; the median take's highest
frame is under 1. A flash isn't a cut: a jump past the line whose picture comes back (the frames a
few after it as near the frames a few before as RETURNS of the jump itself; every cut measured
stayed 0.32-1.9 of it, LAST LIGHT sh090's lightning came back to 0.13, a white frame to 0) is let
go, the jump in and the jump out. A `continuous:
multishot` group's own cuts (its members' starts, within ASKED_FRAMES) were asked for. A place that drifts into another during a continuous camera move
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

**More checks** (a vision-language model's look at the frames, say) join through `register(name,
fn)`: fn(root, take, frozen_shot) -> {"flag": bool, "why": str, ...} or None (nothing to say),
kept under `checks["more"][name]`; a flagged one is one of `flags`, so the badges and the retry
ladder (api's retry step) treat it as they do a cut. A check that raises is recorded as
{"flag": false, "why": the error}: a check is never the reason a take has none.

    check(root, take) -> checks           all of them, read now
    record(root, take)                    checks into its record; never raises
    checks_of(sidecar, mp4) -> checks     the recorded ones, unless the mp4 changed since
    flags(checks) -> ["cut", "words", ...]  what to look at
    register(name, fn)                    another check

A check is a reason to look, not a verdict: nothing is picked by it, and a take is rendered
again only when its render asked for retries (docs/EDITOR.md, "Retries").
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
RETURNS = 0.25              # a flash: the picture after it this near the picture before (is_flash)
THUMB = (64, 36)
WORDS_MODELS = ("small.en", "base.en", "medium.en", "large-v3-turbo", "large-v3", "tiny.en")
WORDS_MATCH = 0.85
MODEL_SPEAKS = ("generate", "clone")        # the audio policies whose lines the model voices
TIMEOUT = 300

# more checks than the cut and the words (register): {name: fn(root, take, frozen_shot)}
CHECKERS: dict = {}

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


def thumbs(mp4: str, timeout: int = TIMEOUT) -> list[bytes]:
    """Each frame at THUMB size, RGB bytes. RuntimeError when ffmpeg fails."""
    w, h = THUMB
    r = subprocess.run([*FF.tool("ffmpeg"), "-v", "error", "-i", mp4, "-map", "0:v:0", "-vf",
                        f"scale={w}:{h},format=rgb24", "-f", "rawvideo", "-"],
                       capture_output=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace")[-400:])
    size = w * h * 3
    return [r.stdout[i:i + size] for i in range(0, len(r.stdout) - size + 1, size)]


def _mean(frames: list[bytes]) -> list[float]:
    return [sum(px) / len(frames) for px in zip(*frames)]


def _apart(a, b) -> float:
    return sum(abs(x - y) for x, y in zip(a, b)) / max(1, len(a))


def is_flash(frames: list[bytes], n: int) -> bool:
    """Whether the jump into frame n is a flash: the picture a few frames after it (n+3..n+5) is
    back within RETURNS of the jump of the picture a few frames before (n-6..n-4), so the jump in
    and the jump back out of a flash both go. A cut stays apart."""
    if n < 1 or n + 3 >= len(frames):
        return False
    jump = _apart(frames[n - 1], frames[n])
    if jump <= 0:
        return False
    before = _mean(frames[max(0, n - 6):max(1, n - 3)])
    after = _mean(frames[n + 3:n + 6])
    return _apart(before, after) / jump < RETURNS


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
    if found:
        frames = thumbs(take.paths.mp4)
        found = [c for c in found if not is_flash(frames, c["frame"])]
    out = {"v": VERSION, "size": os.path.getsize(take.paths.mp4),
           "cuts": found, "cut_score": CUT_SCORE}
    if words:
        out["words"] = words_check(root, take, shot)
        out["words_match"] = WORDS_MATCH
    more = {}
    for name, fn in list(CHECKERS.items()):
        try:
            got = fn(root, take, shot)
        except Exception as e:                  # noqa: BLE001  a check never costs the others
            got = {"flag": False, "why": f"{name} failed: {str(e)[:200]}"}
        if got is not None:
            more[name] = got
    if more:
        out["more"] = more
    return out


def register(name: str, fn) -> None:
    """Another check, run on every finished take after the cut and the words: fn(root, take,
    frozen_shot) -> {"flag": bool, "why": str, ...} | None. `name` is its flag."""
    if name in ("cut", "words"):
        raise ValueError(f"{name} is one of takecheck's own checks")
    CHECKERS[name] = fn


def flags(checks: dict | None) -> list[str]:
    """What a take's checks ask to look at: "cut", "words"."""
    if not checks:
        return []
    out = ["cut"] if checks.get("cuts") else []
    w = checks.get("words") or {}
    if w.get("match") is not None and w["match"] < checks.get("words_match", WORDS_MATCH):
        out.append("words")
    out += [name for name, got in (checks.get("more") or {}).items()
            if isinstance(got, dict) and got.get("flag")]
    return out


def reasons(checks: dict | None) -> list[str]:
    """Each flag in words, as a take's note says it: "a cut at 0.58 s", ..."""
    out = []
    for f in flags(checks):
        if f == "cut":
            out.append("a cut at " + ", ".join(f"{c.get('t')} s" for c in checks.get("cuts") or []))
        elif f == "words":
            out.append(f"its words {round(100 * checks['words']['match'])}% of the lines")
        else:
            out.append(f"{f}: {(checks.get('more') or {}).get(f, {}).get('why') or 'flagged'}")
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
            "why": w.get("why"),
            "more": {k: v.get("why") for k, v in (c.get("more") or {}).items()
                     if isinstance(v, dict) and v.get("flag")}}


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
