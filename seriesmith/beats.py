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
    x = mono(buf)
    beat_s = period * dt
    win = int(min(0.08, beat_s / 2) * rate)
    weight = [0.0] * beats_per_bar
    t, k = first, 0
    while int(t * rate) + win <= len(x):
        a = max(0, int(t * rate))
        weight[k % beats_per_bar] += float(np.sqrt(np.mean(x[a: a + win] ** 2)))
        t, k = t + beat_s, k + 1
    return first, first + beat_s * int(np.argmax(weight))


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
