"""
levels.py: each sound file's speech readings, measured once and cached, and Play all's levelling
worked out from them as the export's mix works it out (docs/LEVELLING.md); POST /seriesmith/levels.
"""
from __future__ import annotations

import os
import sys
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import numpy as np  # noqa: E402

from seriesmith import api as A  # noqa: E402
from seriesmith import levels as LV  # noqa: E402
from seriesmith import mix as MX  # noqa: E402
from test_api import ApiTest  # noqa: E402
from test_level import RATE, talk  # noqa: E402


def wav(path: str, *parts) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    MX.write_wav(path, np.concatenate(parts))
    return path


class ArithmeticTest(unittest.TestCase):
    def test_the_exports_measure(self):
        """The export's speech_level is level_of over the same readings, and its gains gains_of's."""
        buf = np.concatenate([talk(2, -14), np.zeros((RATE // 2, 2), np.float32)])
        db = LV.window_db(buf.mean(1))
        self.assertAlmostEqual(MX.speech_level(buf, RATE), LV.level_of(db), places=9)
        self.assertEqual(LV.level_of(db[:5]), None)                           # under half a second
        self.assertEqual(LV.level_of([]), None)
        middle, gains = LV.gains_of({"a": -10.0, "b": -20.0, "c": -40.0}, 9.0)
        self.assertEqual(middle, -20.0)
        self.assertEqual(gains, {"a": -9.0, "b": 0.0, "c": 9.0})
        self.assertEqual(LV.gains_of({"a": -10.0}, 9.0), (None, {}))         # one voice: nothing to meet
        self.assertEqual(LV.gains_of({"a": -10.0, "b": -20.0}, 0.0), (None, {}))   # off

    def test_a_span_of_readings(self):
        db = [-80.0] * 20 + [-20.0] * 20 + [-30.0] * 20                     # 1 s each, at 0.05 s
        self.assertAlmostEqual(LV.level_between(db, 1.0, 2.0), -20.0, places=6)
        self.assertAlmostEqual(LV.level_between(db, 2.0, None), -30.0, places=6)
        self.assertIsNone(LV.level_between(db, 0.0, 1.0))                    # under the floor


class CacheTest(ApiTest):
    def test_measured_once_and_fresh_when_the_file_changes(self):
        f = wav(os.path.join(self.ep, "renders", "x.wav"), talk(2, -18))
        db = LV.readings(self.ep, f)
        self.assertAlmostEqual(LV.level_between(db, 0, None), MX.speech_level(talk(2, -18), RATE), places=1)
        self.assertEqual(LV.cached(self.ep, f), db)
        with mock.patch.object(MX, "decode", side_effect=AssertionError("decoded again")):
            self.assertEqual(LV.readings(self.ep, f), db)                     # from the cache
        time.sleep(0.02)
        wav(f, talk(2, -30))                                                  # a new take into the same name
        self.assertIsNone(LV.cached(self.ep, f))
        self.assertAlmostEqual(LV.level_between(LV.readings(self.ep, f), 0, None), -30, delta=0.5)
        self.assertIsNone(LV.readings(self.ep, os.path.join(self.ep, "gone.wav")))

    def test_warm_measures_what_is_missing(self):
        a = wav(os.path.join(self.ep, "renders", "a.wav"), talk(1, -20))
        LV.warm(self.ep, [a])
        self.assertIsNone(LV.cached(self.ep, a))                              # off in the tests
        with mock.patch.object(LV, "WARM", True):
            LV.warm(self.ep, [a, a, os.path.join(self.ep, "gone.wav")])
        for _ in range(200):
            if LV.cached(self.ep, a) is not None:
                break
            time.sleep(0.02)
        self.assertIsNotNone(LV.cached(self.ep, a))

    def test_clip_gains(self):
        a = wav(os.path.join(self.ep, "renders", "a.wav"), talk(3, -12))
        b = wav(os.path.join(self.ep, "renders", "b.wav"), np.zeros((RATE, 2), np.float32), talk(3, -24))
        c = wav(os.path.join(self.ep, "renders", "c.wav"), talk(3, -6))
        clips = [{"shot": "sh010", "path": a, "from": 0, "to": None},
                 {"shot": "sh020", "path": b, "from": 1.0, "to": 4.0},     # its silent head trimmed off
                 {"shot": "sh030", "path": c, "from": 0, "to": None}]      # no lines: left
        r = LV.clip_gains(self.ep, clips, 9.0, {"sh010", "sh020"})
        self.assertAlmostEqual(r["gains"]["sh010"], -6.0, delta=0.2)
        self.assertAlmostEqual(r["gains"]["sh020"], 6.0, delta=0.2)
        self.assertNotIn("sh030", r["gains"])
        self.assertEqual(LV.clip_gains(self.ep, clips, 0.0, None)["gains"], {})
        silent = wav(os.path.join(self.ep, "renders", "s.wav"), np.zeros((RATE, 2), np.float32))
        r = LV.clip_gains(self.ep, clips[:1] + [{"shot": "sh020", "path": silent, "from": 0, "to": None}],
                          9.0, None)
        self.assertEqual((r["gains"], r["unmeasured"]), ({}, ["sh020"]))


class RouteTest(ApiTest):
    def setUp(self):
        super().setUp()
        wav(os.path.join(self.ep, "renders", "a.wav"), talk(3, -12))
        wav(os.path.join(self.ep, "renders", "b.wav"), talk(3, -24))
        self.clips = [{"shot": "sh010", "path": "renders/a.wav", "from": 0, "to": None},
                      {"shot": "sh020", "path": "renders/b.wav", "from": 0, "to": 3}]

    def test_levels_follow_the_mix(self):
        with mock.patch.object(MX, "speaking_shots", return_value={"sh010", "sh020"}):
            off = self.ok(A.post_levels(self.ctx, {"ep": self.ep, "pass": "final", "clips": self.clips}))
            self.assertEqual((off["limit_db"], off["gains"]), (0.0, {}))            # levelling off
            MX.save(self.ep, {"final": {"level": {"limit_db": 9}}})
            on = self.ok(A.post_levels(self.ctx, {"ep": self.ep, "pass": "final", "clips": self.clips}))
        self.assertEqual(on["limit_db"], 9.0)
        self.assertAlmostEqual(on["gains"]["sh010"], -6.0, delta=0.2)
        self.assertAlmostEqual(on["gains"]["sh020"], 6.0, delta=0.2)

    def test_refusals(self):
        bad = [{"shot": "sh010", "path": "../outside.wav"},
               {"shot": "sh010", "path": "renders/a.wav", "from": -1},
               {"shot": "sh010", "path": "renders/a.wav", "from": 2, "to": 1},
               {"path": "renders/a.wav"}]
        for c in bad:
            self.err(A.post_levels(self.ctx, {"ep": self.ep, "pass": "final", "clips": [c]}), 400)
        self.err(A.post_levels(self.ctx, {"ep": self.ep, "pass": "final", "clips": "all"}), 400)
        self.err(A.post_levels(self.ctx, {"ep": self.ep, "pass": "final",
                                          "clips": [{"shot": "x", "path": "renders/none.wav"}]}), 404)

    def test_an_opened_episode_warms_its_cut(self):
        with mock.patch.object(LV, "warm") as warm:
            A._levels_warmed.clear()
            A.warm_levels(self.ep, "final")
            A.warm_levels(self.ep, "final")                                    # once a minute
        self.assertEqual(warm.call_count, 1)


if __name__ == "__main__":
    unittest.main()
