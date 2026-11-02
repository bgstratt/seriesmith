"""
beats.py (docs/SOUND.md "Checking a take against the arc"): a synthetic click track of a
known tempo, with accented downbeats and a rising level, read back.
"""
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from seriesmith import beats as B  # noqa: E402

try:
    import numpy as np
except ImportError:                                  # pragma: no cover
    np = None


def clicks(bpm: float, bars: int, offset: float = 0.25, levels=None, beats_per_bar: int = 4):
    """Clicks on every beat (the downbeat twice as loud), `offset` seconds of silence first,
    each bar at its level (linear), as float32 stereo at B.RATE."""
    beat = 60.0 / bpm
    n = int((offset + bars * beats_per_bar * beat + 1.0) * B.RATE)
    x = np.zeros(n, dtype=np.float32)
    click = np.sin(2 * np.pi * 1000 * np.arange(int(0.03 * B.RATE)) / B.RATE).astype(np.float32)
    click *= np.linspace(1.0, 0.0, len(click), dtype=np.float32)
    for k in range(bars * beats_per_bar):
        a = int((offset + k * beat) * B.RATE)
        g = (levels[k // beats_per_bar] if levels else 0.5) * (1.0 if k % beats_per_bar == 0 else 0.5)
        x[a: a + len(click)] += click * g
    return np.stack([x, x], axis=1)


@unittest.skipIf(np is None, "numpy isn't installed")
class BeatsTest(unittest.TestCase):
    def test_tempo_and_grid(self):
        # within one frame at 24 fps, whatever the lead-in
        for bpm in (72.0, 92.0, 128.0):
            for offset in (0.25, 0.73):
                with self.subTest(bpm=bpm, offset=offset):
                    buf = clicks(bpm, 8, offset=offset)
                    env = B.onsets(buf)
                    got = B.tempo(env, asked=bpm)
                    self.assertAlmostEqual(got, bpm, delta=bpm * 0.01)
                    first, down = B.grid(env, got, buf)
                    self.assertAlmostEqual(first, offset, delta=1 / 24)
                    self.assertAlmostEqual(down, offset, delta=1 / 24)

    def test_downbeat_not_on_the_first_beat(self):
        # the music starts on beat 3 of a bar: the downbeat is two beats in
        buf = clicks(92.0, 8, offset=0.25)
        buf = buf[int((0.25 + 2 * 60 / 92 - 0.25) * B.RATE):]
        env = B.onsets(buf)
        first, down = B.grid(env, B.tempo(env, asked=92.0), buf)
        self.assertAlmostEqual(down - first, 2 * 60 / 92, delta=1 / 24)

    def test_octave_folded_toward_the_asked(self):
        buf = clicks(184.0, 8)
        self.assertAlmostEqual(B.tempo(B.onsets(buf), asked=92.0), 92.0, delta=1.5)

    def test_levels_and_shape(self):
        rising = [0.05, 0.1, 0.2, 0.4, 0.8, 0.4, 0.1, 0.05]
        buf = clicks(92.0, 8, levels=rising)
        lv = B.bar_levels(buf, 92.0, 0.25, 4, 8)
        self.assertEqual(int(np.argmax(lv)), 4)
        self.assertLess(B.shape_error(lv, [1, 2, 3, 4, 5, 4, 2, 1]), 0.1)
        self.assertGreater(B.shape_error(lv, [5, 4, 3, 2, 1, 1, 1, 1]), 0.3)    # a fade
        self.assertIsNone(B.shape_error(lv, [3] * 8))

    def test_hit_errors_in_frames(self):
        beat = 60.0 / 120.0                               # 0.5 s
        got = B.hit_errors([1.0, 1.25 + 1 / 24, 2.02], 120.0, 0.0, 24.0)
        self.assertEqual(got[0], 0.0)
        self.assertAlmostEqual(abs(got[1]), 0.25 * 24 - 1, delta=0.01)   # a quarter beat off
        self.assertAlmostEqual(got[2], -0.48, delta=0.01)
        self.assertEqual(beat, 0.5)


@unittest.skipIf(np is None, "numpy isn't installed")
class FileGridTest(unittest.TestCase):
    """A plain file's beats (docs/SOUND.md phase 5: a song on the Music track, the recording)."""

    def test_measured_with_no_asked_tempo(self):
        # 98 bpm, the tempo tempo() alone took for 130 on an ACE-Step cue: the comb finds it
        for bpm, offset in ((98.0, 0.4), (128.0, 1.1), (75.0, 0.25)):
            with self.subTest(bpm=bpm):
                g = B.measure_grid(clicks(bpm, 12, offset=offset))
                self.assertAlmostEqual(g["bpm"], bpm, delta=bpm * 0.003)
                self.assertAlmostEqual(g["first"], offset, delta=1 / 24)
                self.assertAlmostEqual(g["downbeat"], offset, delta=1 / 24)
                self.assertTrue(g["steady"])
                self.assertEqual(g["beats_per_bar"], 4)

    def test_no_pulse_isnt_steady(self):
        rng = np.random.default_rng(1)
        x = np.zeros(int(20 * B.RATE), dtype=np.float32)
        # bursts at random times, as speech is
        for t in rng.uniform(0, 19.5, 40):
            a = int(t * B.RATE)
            x[a: a + 2400] += rng.normal(0, 0.3, 2400).astype(np.float32)
        g = B.measure_grid(np.stack([x, x], axis=1))
        self.assertFalse(g and g["steady"])
        # a few seconds of clicks is too short to trust
        self.assertFalse(B.measure_grid(clicks(120.0, 2))["steady"])

    def test_kept_beside_the_file_until_it_changes(self):
        import tempfile
        from seriesmith import mix as MX
        d = tempfile.mkdtemp()
        path = os.path.join(d, "song.wav")
        MX.write_wav(path, clicks(110.0, 12))
        g = B.file_grid(path)
        self.assertAlmostEqual(g["bpm"], 110.0, delta=0.5)
        side = path + B.GRID_SUFFIX
        self.assertTrue(os.path.isfile(side))
        calls = []
        real = B.measure_grid
        B.measure_grid = lambda *a, **k: calls.append(1) or real(*a, **k)
        try:
            self.assertEqual(B.file_grid(path), g)               # from beside it
            self.assertEqual(calls, [])
            MX.write_wav(path, clicks(90.0, 12))                 # changed: measured again
            self.assertAlmostEqual(B.file_grid(path)["bpm"], 90.0, delta=0.5)
            self.assertEqual(calls, [1])
        finally:
            B.measure_grid = real
        self.assertIsNone(B.file_grid(os.path.join(d, "none.wav")))


if __name__ == "__main__":
    unittest.main()
