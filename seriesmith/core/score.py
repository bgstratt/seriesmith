"""
score.py — a cue's timing worked out from its hits (docs/SOUND.md "Music: a cue is
written to its hits"). Model-free and standard library only, like the rest of core.

    fit_tempo(hits, asked, fps, ...) -> Fit: the tempo, the pre-roll and each hit's error

A hit is (seconds from the cue's start, must, on_beat). A cue lands a hit when the hit falls
on a bar line of its grid, `preroll + t = n x bar`, or for an accent (on_beat) on any beat.
The search runs over tempos near the asked one (fractional: ACE-Step takes a whole bpm, so a
take is asked for `ask_bpm` and stretched by `stretch`, under 1 % near any usable tempo) and,
for each, the pre-rolls that put a must-hit exactly on its line: the must-hits' worst error
first, then all the hits' total, then the distance from the asked tempo.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class Fit:
    bpm: float                      # the cue's tempo
    preroll: float                  # seconds of music before the cue's start (its first bar line)
    beats_per_bar: int
    errors: list[float] = field(default_factory=list)   # each hit's distance to its bar line, frames
    worst_must: float = 0.0         # frames
    ask_bpm: int = 0                # the whole tempo the model is asked for
    stretch: float = 1.0            # bpm / ask_bpm: the take is played this much faster

    @property
    def bar(self) -> float:
        return 60.0 / self.bpm * self.beats_per_bar


def _circ(x: float, period: float) -> float:
    """x folded to (-period/2, period/2]."""
    return (x + period / 2) % period - period / 2


def fit_tempo(hits: list[tuple], asked: float, fps: float, beats_per_bar: int = 4,
              spread: float = 0.08, step: float = 0.01, beat_level: bool = False) -> Fit:
    """The tempo within `spread` (a fraction) of `asked` that lands the hits on their
    lines, and the pre-roll that puts them there. A hit is (seconds, must) or (seconds,
    must, on_beat): on_beat (an accent) lands on any beat, the others on a bar line
    (`beat_level`: every hit on a beat). No hits: the asked tempo, no pre-roll."""
    if not hits:
        return Fit(asked, 0.0, beats_per_bar, [], 0.0, round(asked), asked / round(asked))
    hits = [(h[0], h[1], beat_level or (len(h) > 2 and bool(h[2]))) for h in hits]
    musts = [h for h in hits if h[1]] or hits
    best = None
    lo, hi = asked * (1 - spread), asked * (1 + spread)
    n = int(round((hi - lo) / step)) + 1
    for k in range(n):
        bpm = lo + k * step
        beat = 60.0 / bpm
        bar = beat * beats_per_bar
        units = [beat if on_beat else bar for _, _, on_beat in hits]
        # the pre-rolls that put one must-hit exactly on its line (a bar line: one; a
        # beat: each of the bar's beats), each tried; the one landing all of them best wins
        cands = set()
        for t, _, on_beat in musts:
            p0 = (-t) % bar
            cands.update(((p0 + j * beat) % bar) for j in range(beats_per_bar if on_beat else 1))
        for pre in cands:
            errs = [_circ(t + pre, u) * fps for (t, _, _), u in zip(hits, units)]
            worst = max(abs(e) for e, h in zip(errs, hits) if h in musts)
            key = (round(worst, 2), round(sum(abs(e) for e in errs), 2), abs(bpm - asked))
            if best is None or key < best[0]:
                best = (key, bpm, pre, errs, worst)
    _, bpm, pre, errs, worst = best
    ask = max(10, min(300, round(bpm)))
    return Fit(round(bpm, 3), round(pre, 4), beats_per_bar, [round(-e, 2) for e in errs],
               round(worst, 2), ask, round(bpm / ask, 5))
