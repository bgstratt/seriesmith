"""
core/score.py: a cue's tempo and pre-roll fitted to its hits.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from seriesmith.core import score as S  # noqa: E402

FPS = 24.0


class FitTempoTest(unittest.TestCase):
    def test_no_hits_keeps_the_asked(self):
        f = S.fit_tempo([], 92, FPS)
        self.assertEqual((f.bpm, f.preroll, f.ask_bpm, f.stretch), (92, 0.0, 92, 1.0))

    def test_hits_from_a_known_grid_are_found(self):
        # a 93.4 bpm cue with 0.3 s of pre-roll: hits on bars 3, 7 and 12
        bar = 60 / 93.4 * 4
        hits = [(n * bar - 0.3, True) for n in (3, 7, 12)]
        f = S.fit_tempo(hits, 92, FPS)
        self.assertLess(f.worst_must, 0.1)
        self.assertAlmostEqual(f.bar, bar, delta=0.01)
        self.assertEqual(f.ask_bpm, 93)
        self.assertAlmostEqual(f.stretch, f.bpm / 93, places=4)

    def test_must_hits_win_over_the_others(self):
        # two hits that one grid can't land at once within the spread; the must one is landed
        hits = [(5.0, True), (7.1, False)]
        f = S.fit_tempo(hits, 92, FPS, spread=0.01)
        self.assertLess(abs(f.errors[0]), 0.1)
        self.assertGreater(abs(f.errors[1]), 0.5)

    def test_stays_near_the_asked_and_says_the_error(self):
        f = S.fit_tempo([(3.0, True), (8.0, True), (13.7, True)], 120, FPS, spread=0.05)
        self.assertTrue(114 <= f.bpm <= 126)
        self.assertEqual(len(f.errors), 3)
        self.assertEqual(f.worst_must, max(abs(e) for e in f.errors))

    def test_accents_land_on_beats(self):
        # two bar-line hits and an accent half a bar between them: the accent needs a beat
        bar = 60 / 92 * 4
        hits = [(2 * bar, True, False), (2.5 * bar + 0.0, True, True), (5 * bar, True, False)]
        f = S.fit_tempo([(t - 0.4, m, b) for t, m, b in hits], 92, FPS)
        self.assertLess(f.worst_must, 0.1)
        as_bars = S.fit_tempo([(t - 0.4, m) for t, m, _ in hits], 92, FPS, spread=0.0)
        self.assertGreater(as_bars.worst_must, 5)                 # on a bar line it can't

    def test_beat_level(self):
        beat = 60 / 100
        f = S.fit_tempo([(5 * beat, True), (9 * beat, True)], 100, FPS, beat_level=True)
        self.assertLess(f.worst_must, 0.1)


if __name__ == "__main__":
    unittest.main()
