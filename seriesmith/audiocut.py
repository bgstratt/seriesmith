"""
audiocut.py — short pieces of a recording, cut for a model to hear: the head of
a voice sample an audio target continues (`voice_clip`), the window of the
recorded track a dub shot is spoken to (`window`), and a voice take's sound
brought to one loudness for a dub (`levelled`).

A cut is a 16-bit PCM wav kept beside its source, in `_cuts/`, named by the
source's sha1 and the span: the same cut is made once, and a re-recorded
source makes a new one. `quiet_point` finds where a cut should end so it
doesn't stop mid-word: the quietest 20 ms in a range.

Stdlib only (ffmpeg through subprocess, found by seriesmith.ff).
"""
from __future__ import annotations

import array
import os
import subprocess
import sys

from seriesmith import ff as FF
from seriesmith import peaks as PK
from seriesmith.core import fileio as F

CUTS = "_cuts"
RATE = 8000                      # quiet_point decodes to mono s16le at this rate
WINDOW = 0.02                    # ...and compares 20 ms windows

# A voice sample's head, for a model that continues it (ltx2_voice): long
# enough to carry who is speaking, short enough to leave the rest of the
# clip to the line. Measured live 2026-10-28: 1.4 s and 2.45 s both carried
# the voice (docs/PLAN.md, "Voice clone by continuation").
CLIP_MIN, CLIP_MAX = 1.5, 2.5


class CutError(Exception):
    """A cut ffmpeg couldn't make (no ffmpeg, a file it can't read)."""


def duration(path: str) -> float | None:
    return PK.media_info(path).get("duration")


def _decode(path: str, start: float, end: float) -> array.array:
    exe = FF.find("ffmpeg")
    if not exe:
        raise CutError("ffmpeg isn't installed")
    r = subprocess.run([*exe, "-v", "error", "-nostdin", "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
                        "-i", path, "-vn", "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-"],
                       capture_output=True, timeout=120)
    if r.returncode != 0:
        raise CutError(f"ffmpeg could not read {os.path.basename(path)}: "
                       f"{r.stderr.decode('utf-8', 'replace').strip()[-300:]}")
    a = array.array("h")
    a.frombytes(r.stdout[: len(r.stdout) // 2 * 2])
    if sys.byteorder != "little":
        a.byteswap()
    return a


def quiet_point(path: str, lo: float, hi: float) -> float:
    """The middle of the quietest 20 ms of `path` between `lo` and `hi`
    seconds (`hi` itself when there's nothing to compare)."""
    a = _decode(path, lo, hi)
    n = int(RATE * WINDOW)
    best, at = None, None
    for i in range(0, len(a) - n + 1, n // 2):
        e = sum(x * x for x in a[i:i + n])
        if best is None or e < best:
            best, at = e, i
    return hi if at is None else lo + (at + n / 2) / RATE


# Where speech ends: the last 20 ms window within SPEECH_DB of the loudest,
# and a little after it so the last consonant isn't clipped.
SPEECH_DB, SPEECH_TAIL = -30.0, 0.08


def speech_end(path: str, upto: float) -> float:
    """Where the last sound of speech in `path`'s first `upto` seconds ends
    (`upto` when it's all sound, 0 when it's all silence)."""
    a = _decode(path, 0.0, upto)
    n = int(RATE * WINDOW)
    rms = [(sum(x * x for x in a[i:i + n]) / n) ** 0.5 for i in range(0, len(a) - n + 1, n)]
    if not rms or max(rms) <= 0:
        return 0.0
    floor = max(rms) * 10 ** (SPEECH_DB / 20)
    last = max(k for k, v in enumerate(rms) if v >= floor)
    return min(upto, (last + 1) * WINDOW + SPEECH_TAIL)


def cut(src: str, start: float, end: float, at_least: float = 0.0) -> str:
    """`start..end` seconds of `src` as a wav in `_cuts/` beside it, made once;
    padded with silence to `at_least` seconds when it's shorter (a model with
    a shortest clip it hears)."""
    sha = (F.file_digest(src) or "")[:12]
    stem = os.path.splitext(os.path.basename(src))[0]
    pad = at_least if at_least > end - start else 0.0
    out = os.path.join(os.path.dirname(os.path.abspath(src)), CUTS,
                       f"{stem}_{sha}_{round(start * 1000)}-{round(end * 1000)}"
                       + (f"_pad{round(pad * 1000)}" if pad else "") + ".wav")
    if os.path.isfile(out):
        return out
    exe = FF.find("ffmpeg")
    if not exe:
        raise CutError("ffmpeg isn't installed")
    tmp = F.temp_beside(out, ".wav")
    try:
        r = subprocess.run([*exe, "-v", "error", "-nostdin", "-y", "-ss", f"{start:.3f}",
                            "-to", f"{end:.3f}", "-i", src, "-vn",
                            *(["-af", f"apad=whole_dur={pad:.3f}"] if pad else []),
                            "-c:a", "pcm_s16le", tmp],
                           capture_output=True, timeout=300)
        if r.returncode != 0 or not os.path.isfile(tmp):
            raise CutError(f"ffmpeg could not cut {start:.2f}-{end:.2f}s out of "
                           f"{os.path.basename(src)}: "
                           f"{r.stderr.decode('utf-8', 'replace').strip()[-300:]}")
        F.replace(tmp, out)
    finally:
        if os.path.isfile(tmp):
            os.remove(tmp)
    return out


def voice_clip(sample: str, lo: float = CLIP_MIN, hi: float = CLIP_MAX) -> tuple[str, float]:
    """(the head of voice sample `sample`, its length in seconds): cut at its
    quietest point between `lo` and `hi` seconds, so it ends between words, and
    the silence after its last word taken off: a model continuing a head that
    ends in silence continues the silence (Mia's 2 s sample, 1.1 s of speech,
    came back silent every time, live 2026-10-28). A sample no longer than `hi`
    is used whole but for that silence."""
    total = duration(sample)
    end = float(total) if total is not None and total <= hi else quiet_point(sample, lo, hi)
    said = speech_end(sample, end)
    if 0 < said < end - WINDOW:
        end = said
    end = round(end, 3)
    if total is not None and end >= round(float(total), 3):
        return sample, float(total)
    return cut(sample, 0.0, end), end


def window(track: str, start: float, end: float, at_least: float = 0.0) -> str:
    """The `start..end` window of a recorded track, for a shot spoken to it
    (padded with silence to `at_least` seconds)."""
    return cut(track, max(0.0, float(start)), float(end), at_least)


# A voice take's sound, for a dub: H3 at a tiny size speaks the line well but its
# level wanders with the size (measured live 2026-10-28: -13.5 to -20.3 dBFS
# RMS, two takes peaking over full scale), so it is brought to one loudness
# with its peaks kept under full scale before a model is given it.
LEVEL = "loudnorm=I=-16:TP=-1.5:LRA=11"


def levelled(src: str) -> str:
    """`src`'s sound (a wav, or a video's audio) at one loudness (LEVEL), 48 kHz
    stereo, as a wav in `_cuts/` beside it, made once per source."""
    sha = (F.file_digest(src) or "")[:12]
    stem = os.path.splitext(os.path.basename(src))[0]
    out = os.path.join(os.path.dirname(os.path.abspath(src)), CUTS, f"{stem}_{sha}_level.wav")
    if os.path.isfile(out):
        return out
    exe = FF.find("ffmpeg")
    if not exe:
        raise CutError("ffmpeg isn't installed")
    tmp = F.temp_beside(out, ".wav")
    try:
        r = subprocess.run([*exe, "-v", "error", "-nostdin", "-y", "-i", src, "-vn",
                            "-af", LEVEL, "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", tmp],
                           capture_output=True, timeout=300)
        if r.returncode != 0 or not os.path.isfile(tmp):
            raise CutError(f"ffmpeg could not level the sound of {os.path.basename(src)}: "
                           f"{r.stderr.decode('utf-8', 'replace').strip()[-300:]}")
        F.replace(tmp, out)
    finally:
        if os.path.isfile(tmp):
            os.remove(tmp)
    return out
