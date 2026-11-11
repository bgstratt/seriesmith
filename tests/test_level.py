"""
mix.level_dialogue: each speaking clip's dialogue brought to the middle of their speech levels,
within the limit, a clip with no speech (or a shot with no lines) left alone.
"""
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import numpy as np  # noqa: E402

from seriesmith import mix as MX  # noqa: E402

RATE = 48000


def talk(seconds: float, db: float) -> np.ndarray:
    """Speech-like: a tone in syllables (on 0.2 s, off 0.1 s) at `db` RMS while on, stereo."""
    t = np.arange(int(seconds * RATE)) / RATE
    on = (t % 0.3) < 0.2
    x = np.sin(2 * np.pi * 180 * t) * np.sqrt(2) * 10 ** (db / 20) * on
    return np.stack([x, x], 1).astype(np.float32)


def level(buf) -> float:
    return MX.speech_level(buf, RATE)


class LevelTest(unittest.TestCase):
    def test_two_voices_meet_in_the_middle(self):
        loud, quiet, fx = talk(3, -12), talk(3, -24), talk(3, -6)
        buf = np.concatenate([loud, quiet, fx])
        spans = [("sh010", 0, 3 * RATE), ("sh020", 3 * RATE, 6 * RATE)]   # sh030 has no lines
        gains = MX.level_dialogue(buf, spans, 9.0, RATE, log=lambda *a: None)
        self.assertAlmostEqual(gains["sh010"], -6.0, delta=0.2)
        self.assertAlmostEqual(gains["sh020"], 6.0, delta=0.2)
        self.assertAlmostEqual(level(buf[RATE // 2:3 * RATE - RATE // 2]),
                               level(buf[3 * RATE + RATE // 2:6 * RATE - RATE // 2]), delta=0.3)
        self.assertAlmostEqual(level(buf[6 * RATE + RATE // 2:]), level(fx), delta=0.1)   # left alone

    def test_the_limit_and_off(self):
        buf = np.concatenate([talk(2, -6), talk(2, -40)])
        spans = [("a", 0, 2 * RATE), ("b", 2 * RATE, 4 * RATE)]
        gains = MX.level_dialogue(buf.copy(), spans, 9.0, RATE, log=lambda *a: None)
        self.assertEqual((gains["a"], gains["b"]), (-9.0, 9.0))
        self.assertEqual(MX.level_dialogue(buf.copy(), spans, 0.0, RATE), {})

    def test_silence_and_one_voice_are_left(self):
        buf = np.concatenate([talk(2, -20), np.zeros((2 * RATE, 2), np.float32)])
        spans = [("a", 0, 2 * RATE), ("b", 2 * RATE, 4 * RATE)]
        self.assertEqual(MX.level_dialogue(buf, spans, 9.0, RATE), {})     # only one has speech

    def test_spans_and_the_setting(self):
        origins = {"sh010": {"origin": 0, "first": 0, "used": 48}, "sh020": {"origin": 40, "first": 8, "used": 24}}
        self.assertEqual(MX.speech_spans(origins, 24.0, 10 ** 6, {"sh020"}, RATE), [("sh020", 96000, 144000)])
        self.assertEqual(MX.check({"level": {"limit_db": 6}})["level"], {"limit_db": 6.0})
        self.assertEqual(MX.check({"level": {"limit_db": 9}})["level"], {"limit_db": 9.0})   # set: kept
        with self.assertRaises(ValueError):
            MX.check({"level": {"limit_db": 30}})
        self.assertTrue(MX.active({"level": {"limit_db": 6}}))
        self.assertFalse(MX.active({}))
        self.assertFalse(MX.active(MX.check({"level": {"limit_db": 0}})))      # set off


if __name__ == "__main__":
    unittest.main()
