"""
beats.py — what a music take did: its tempo, its beat grid, its level per bar, and how
far it is from what it was asked (docs/SOUND.md "Checking a take against the arc").

Plain numpy on float32 stereo at mix.RATE (mix.decode reads a file so):

    onsets(buf)                    -> the onset envelope (spectral flux), one value per HOP
    tempo(env, asked)              -> beats per minute, searched near the asked tempo
    grid(env, bpm, buf)            -> (the first beat, the first downbeat), in seconds
    bar_levels(buf, bpm, start, beats_per_bar, bars) -> dB per bar (RMS)
    hit_errors(hits, bpm, start, fps)                -> each hit's distance to its beat, frames
    shape_error(levels, arc)       -> 0 (the arc) .. 1, how far the level per bar strays
    file_grid(path)                -> a plain file's beat grid (a song on the Music track, the
                                      episode's recording), measured once and kept beside it

A take is never more than a cue's length (minutes), so everything is computed whole.
"""

from __future__ import annotations

import math

RATE = 48000
HOP = 512                                  # ~10.7 ms at 48 kHz
FFT = 2048
# an onset shows in the envelope about this much before it sounds (the window reaches it
# first); measured on clicks at 72-128 bpm
LATENCY = 0.023


def _np():
    import numpy as np
    return np


def mono(buf):
    np = _np()
    return buf.mean(axis=1).astype(np.float32) if buf.ndim == 2 else buf.astype(np.float32)


def onsets(buf, rate: int = RATE):
    """Spectral flux: the summed rise in log magnitude per HOP, half-wave rectified and
    with its local mean taken away, so steady sound reads as nothing."""
    np = _np()
    x = mono(buf)
    if len(x) < FFT:
        return np.zeros(0, dtype=np.float32)
    n = 1 + (len(x) - FFT) // HOP
    idx = np.arange(FFT)[None, :] + HOP * np.arange(n)[:, None]
    frames = x[idx] * np.hanning(FFT).astype(np.float32)
    mag = np.log1p(1000.0 * np.abs(np.fft.rfft(frames, axis=1)))
    flux = np.maximum(0.0, np.diff(mag, axis=0)).sum(axis=1)
    flux = np.concatenate([[0.0], flux]).astype(np.float32)
    k = max(1, int(0.4 * rate / HOP))                       # a 0.4 s local mean
    local = np.convolve(flux, np.ones(k) / k, mode="same")
    return np.maximum(0.0, flux - local)


def hop_s(rate: int = RATE) -> float:
    return HOP / rate


def tempo(env, asked: float | None = None, lo: float = 50.0, hi: float = 210.0,
          rate: int = RATE) -> float | None:
    """The tempo the envelope's autocorrelation likes best, in beats per minute. With
    `asked`, its octaves (half, double) are folded toward it, as a model asked for 92
    that plays in 184 or 46 played 92. None when there's nothing to go on."""
    np = _np()
    if len(env) < 8 or not env.any():
        return None
    e = env - env.mean()
    ac = np.correlate(e, e, mode="full")[len(e) - 1:]
    dt = hop_s(rate)
    lags = np.arange(len(ac))
    ok = (lags > 0) & (lags * dt >= 60.0 / hi) & (lags * dt <= 60.0 / lo)
    if not ok.any():
        return None
    cand = lags[ok]
    best = int(cand[np.argmax(ac[ok])])
    # a parabola through the peak and its neighbours, for a fraction of a hop
    if 0 < best < len(ac) - 1:
        a, b, c = ac[best - 1], ac[best], ac[best + 1]
        den = a - 2 * b + c
        frac = 0.5 * (a - c) / den if den else 0.0
    else:
        frac = 0.0
    bpm = 60.0 / ((best + frac) * dt)
    if asked:
        for f in (0.5, 2.0, 1 / 3, 3.0, 2 / 3, 1.5):
            if abs(bpm * f - asked) < abs(bpm - asked):
                bpm *= f
    return float(bpm)


def grid(env, bpm: float, buf=None, beats_per_bar: int = 4,
         rate: int = RATE) -> tuple[float, float]:
    """(the first beat, the first downbeat) in seconds, for a steady `bpm`: the phase
    whose beats sit on the most onset energy, moved to the first beat at or after the
    music starts; then, from `buf`, the beat of the bar with the most sound just after it
    (a downbeat is usually the strongest; the onset envelope, in log magnitude, hears
    accents too faintly to tell). Without `buf` the downbeat is the first beat."""
    np = _np()
    dt = hop_s(rate)
    period = 60.0 / bpm / dt                                 # in hops
    if not len(env) or period <= 0:
        return 0.0, 0.0
    best, phase = -1.0, 0.0
    for p in np.arange(0.0, period, 0.25):
        idx = np.round(np.arange(p, len(env), period)).astype(int)
        idx = idx[idx < len(env)]
        s = float(env[idx].sum())
        if s > best:
            best, phase = s, float(p)
    loud = np.nonzero(env > 0.1 * env.max())[0]
    if loud.size:
        while phase < loud[0] - period / 2:
            phase += period
    first = phase * dt + LATENCY
    if buf is None:
        return first, first
    return first, downbeat_of(buf, first, period * dt, beats_per_bar, rate)


def downbeat_of(buf, first: float, beat_s: float, beats_per_bar: int = 4,
                rate: int = RATE) -> float:
    """The first downbeat of a steady grid from `first` every `beat_s` seconds: the beat
    of the bar with the most sound just after it, summed over the whole take."""
    np = _np()
    x = mono(buf)
    win = int(min(0.08, beat_s / 2) * rate)
    weight = [0.0] * beats_per_bar
    t, k = first, 0
    while int(t * rate) + win <= len(x):
        a = max(0, int(t * rate))
        weight[k % beats_per_bar] += float(np.sqrt(np.mean(x[a: a + win] ** 2)))
        t, k = t + beat_s, k + 1
    return first + beat_s * int(np.argmax(weight))


def bar_levels(buf, bpm: float, start: float, beats_per_bar: int, bars: int,
               rate: int = RATE) -> list[float]:
    """The RMS level of each bar in dB (-120 for silence), the bars counted from `start`
    seconds at `bpm`; a bar past the end of the take is -120."""
    np = _np()
    x = mono(buf)
    bar_s = 60.0 / bpm * beats_per_bar
    out = []
    for k in range(bars):
        a, b = int((start + k * bar_s) * rate), int((start + (k + 1) * bar_s) * rate)
        seg = x[max(0, a): max(0, b)]
        rms = float(np.sqrt(np.mean(seg ** 2))) if len(seg) else 0.0
        out.append(round(20 * math.log10(rms), 2) if rms > 1e-6 else -120.0)
    return out


def onset_near(env, t: float, radius: float, rate: int = RATE) -> tuple[float | None, float]:
    """(the time of the strongest onset within `radius` seconds of `t`, its strength
    against the take's strongest, 0..1); (None, 0) when the window is outside the take."""
    np = _np()
    dt = hop_s(rate)
    a = max(0, int((t - LATENCY - radius) / dt))
    b = min(len(env), int((t - LATENCY + radius) / dt) + 1)
    if b <= a or not len(env) or env.max() <= 0:
        return None, 0.0
    i = a + int(np.argmax(env[a:b]))
    return i * dt + LATENCY, float(env[i] / env.max())


def hit_errors(hits: list[float], bpm: float, start: float, fps: float) -> list[float]:
    """For each hit (seconds into the take), how far it is from the nearest beat of the
    grid, in frames at `fps` (negative: the beat comes before the hit)."""
    beat = 60.0 / bpm
    out = []
    for t in hits:
        k = round((t - start) / beat)
        out.append(round((start + k * beat - t) * fps, 2))
    return out


def shape_error(levels: list[float], arc: list[float]) -> float | None:
    """How far a take's level per bar strays from the arc asked for it (one energy per
    bar, any scale), 0..1: both scaled to their own range, then the mean distance. A
    take that's loud where the arc is loud and quiet where it's quiet scores near 0,
    whatever its loudness. None when either is flat or they differ in length."""
    np = _np()
    if len(levels) != len(arc) or len(arc) < 2:
        return None
    lv = np.maximum(np.array(levels, dtype=float), -60.0)
    a = np.array(arc, dtype=float)
    if np.ptp(lv) < 1e-6 or np.ptp(a) < 1e-6:
        return None
    lv = (lv - lv.min()) / np.ptp(lv)
    a = (a - a.min()) / np.ptp(a)
    return round(float(np.mean(np.abs(lv - a))), 3)


# ---------------------------------------------------------------------------
# a plain file's beats (docs/SOUND.md phase 5: cutting to music): a song laid on the
# Music track, or the episode's recording when it is a song, has no take sidecar to
# say where its beats are, so they are measured once and kept beside the file
# ---------------------------------------------------------------------------

GRID_SUFFIX = ".beats.json"
GRID_VERSION = 1
# a grid is trusted for snapping when its tempo's comb (comb_tempo) is this strong and the
# file this long: a song with a pulse reads 0.8-2.8, soft score and speech 0.2-0.5, and a
# clip of a few seconds can read anything
STEADY_MIN = 0.5
STEADY_SECONDS = 8.0


def comb_tempo(env, lo: float = 70.0, hi: float = 180.0, step: float = 0.25,
               rate: int = RATE) -> tuple[float | None, float]:
    """(beats per minute, strength) of a file with no asked tempo: each tempo from `lo`
    to `hi` scored by the envelope's autocorrelation (as a share of its own power) at one,
    two, three and four beats summed, so a tempo whose bars line up too beats one that only
    fits a single lag (a 3:4 or swung sub-beat: tempo() took an ACE-Step cue heard at 98 for
    130). The strength is that sum: how much of a pulse there is. (None, 0) for silence."""
    np = _np()
    if len(env) < 8 or not env.any():
        return None, 0.0
    e = env - env.mean()
    ac = np.correlate(e, e, mode="full")[len(e) - 1:]
    if ac[0] <= 0:
        return None, 0.0
    ac = ac / ac[0]
    dt = hop_s(rate)
    best, at = -np.inf, None
    for bpm in np.arange(lo, hi + 1e-9, step):
        lag = 60.0 / bpm / dt
        s = 0.0
        for m in (1, 2, 3, 4):
            x = m * lag
            i = int(x)
            if i + 1 >= len(ac):
                break
            s += ac[i] + (ac[i + 1] - ac[i]) * (x - i)
        if s > best:
            best, at = s, float(bpm)
    return at, float(max(0.0, best))


def refine(env, bpm: float, first: float, seconds: float, rate: int = RATE,
           rounds: int = 2) -> tuple[float, float]:
    """(bpm, first beat) of a steady grid fitted to the onsets near its beats: each beat
    moved to the strongest onset within a sixth of a beat, then a straight line through
    them (least squares), twice. A tempo off by a tenth of a bpm drifts a beat's width
    over a song; the line takes that out. The grid as given when too few beats have one."""
    np = _np()
    for _ in range(rounds):
        beat = 60.0 / bpm
        ks, ts = [], []
        k = 0
        while first + k * beat < seconds:
            at, strength = onset_near(env, first + k * beat, beat / 6, rate)
            if at is not None and strength >= 0.1:
                ks.append(k)
                ts.append(at)
            k += 1
        if len(ks) < 8:
            break
        slope, icpt = np.polyfit(np.array(ks, dtype=float), np.array(ts, dtype=float), 1)
        if not slope > 0:
            break
        # the line's beat 0 is the grid's first (at or after the music starts)
        bpm, first = 60.0 / float(slope), float(icpt)
        if first < 0:
            first += 60.0 / bpm
    return bpm, first


def measure_grid(buf, beats_per_bar: int = 4, rate: int = RATE) -> dict | None:
    """A file's steady beat grid: {"bpm", "first" (the first beat, s), "downbeat" (the
    first downbeat, s), "beats_per_bar", "seconds", "strength" (comb_tempo's), "steady"
    (strong and long enough to snap to: STEADY_MIN, STEADY_SECONDS)}; None when it has
    no tempo to find. The meter isn't heard: four beats a bar."""
    env = onsets(buf, rate)
    bpm, strength = comb_tempo(env, rate=rate)
    if bpm is None:
        return None
    seconds = len(buf) / rate
    first, _ = grid(env, bpm, None, beats_per_bar, rate)
    bpm, first = refine(env, bpm, first, seconds, rate)
    down = downbeat_of(buf, first, 60.0 / bpm, beats_per_bar, rate)
    return {"bpm": round(bpm, 4), "first": round(first, 4), "downbeat": round(down, 4),
            "beats_per_bar": beats_per_bar, "seconds": round(seconds, 4),
            "strength": round(strength, 3),
            "steady": strength >= STEADY_MIN and seconds >= STEADY_SECONDS}


def file_grid(path: str) -> dict | None:
    """`path`'s beat grid (measure_grid), from `<path>.beats.json` when that was made from
    the file as it is now (its size and mtime), else measured and kept there (a folder that
    can't be written is measured again next time). None for a file with no sound or no
    tempo."""
    import os
    from seriesmith import mix as MX
    from seriesmith.core import fileio as F
    try:
        st = os.stat(path)
    except OSError:
        return None
    stamp = {"size": st.st_size, "mtime": round(st.st_mtime, 3), "version": GRID_VERSION}
    side = path + GRID_SUFFIX
    kept = F.read_json_or(side, None, dict)
    if kept and kept.get("of") == stamp:
        return kept.get("grid")
    buf = MX.decode(path)
    g = measure_grid(buf) if len(buf) else None
    try:
        F.write_json(side, {"of": stamp, "grid": g})
    except OSError:
        pass
    return g
