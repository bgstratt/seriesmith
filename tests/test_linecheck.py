"""
linecheck: a take of a line checked (a stall: too long, a silence inside it; its words), the best
of a line's retried takes kept, and the runner going on from a take that fails.
"""
from __future__ import annotations

import json
import math
import os
import struct
import sys
import tempfile
import threading
import unittest
import wave
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from seriesmith import linecheck as LC  # noqa: E402
from seriesmith import lines as LN  # noqa: E402
from seriesmith import retries as RT  # noqa: E402
from seriesmith import runner as RN  # noqa: E402

RATE = 16000


def _wav(path: str, parts: list[tuple[str, float]]) -> None:
    """("tone" | "quiet", seconds) one after another, 16-bit mono."""
    frames = bytearray()
    for kind, secs in parts:
        for i in range(int(secs * RATE)):
            v = int(9000 * math.sin(2 * math.pi * 220 * i / RATE)) if kind == "tone" else 0
            frames += struct.pack("<h", v)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(bytes(frames))


class CheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="linecheck-")

    def test_a_clean_line(self):
        p = os.path.join(self.tmp, "ok.wav")
        _wav(p, [("quiet", 0.2), ("tone", 0.8), ("quiet", 0.3), ("tone", 0.9), ("quiet", 0.2)])
        c = LC.check(self.tmp, p, "Still alive. Good. Let's get you home.", words=False)
        self.assertEqual(c["flags"], [])
        self.assertEqual(c["gap"], 0.3)

    def test_a_stall_inside_and_one_that_runs_on(self):
        p = os.path.join(self.tmp, "gap.wav")
        _wav(p, [("tone", 0.8), ("quiet", 1.6), ("tone", 0.8)])
        self.assertEqual(LC.check(self.tmp, p, "Cut it now.", words=False)["flags"], ["gap"])
        q = os.path.join(self.tmp, "long.wav")
        _wav(q, [("tone", 9.0)])
        c = LC.check(self.tmp, q, "Cut it.", words=False)
        self.assertEqual(c["flags"], ["long"])
        self.assertIn("for a line of about", LC.reasons(c)[0])

    def test_the_best_take(self):
        good = {"flags": [], "words": {"match": 1.0}, "gap": 0.2}
        heard_less = {"flags": ["words"], "words": {"match": 0.7}, "gap": 0.2}
        stalled = {"flags": ["gap"], "words": {"match": 1.0}, "gap": 1.8}
        self.assertGreater(LC.score(good), LC.score(stalled))
        self.assertGreater(LC.score(stalled), LC.score(heard_less))
        ep = self.tmp
        os.makedirs(LN.folder(ep))
        with open(LN.record_path(ep), "w", encoding="utf-8") as fh:
            json.dump({"lines": {"sh010.1": {"picked": 3, "takes": [
                {"take": 1, "status": "ok", "checks": heard_less}, {"take": 2, "status": "ok", "checks": good},
                {"take": 3, "status": "ok", "checks": stalled}, {"take": 4, "status": "failed"}]}}}, fh)
        self.assertEqual(LN.pick_best(ep, "sh010.1", [1, 2, 3, 4], LC.score), 2)
        self.assertEqual(LN.load(ep)["lines"]["sh010.1"]["picked"], 2)
        LN.set_take_fields(ep, "sh010.1", 1, checks=good)
        self.assertEqual(LN.load(ep)["lines"]["sh010.1"]["takes"][0]["checks"], good)


class RetryTest(unittest.TestCase):
    """runner._check_line: a failed take of a line asks for another while it has tries, then the
    best is kept; a paid model only when the run said it may cost."""

    def go(self, checks, retry, tried, hosted=False):
        asked, emitted = [], []
        fake = SimpleNamespace(enqueue_line=lambda *a: asked.append(a) or (9, "q"),
                               _emit=lambda *a: emitted.append(a))
        target = SimpleNamespace(spec={"api": {}} if hosted else {})
        picks = []
        with mock.patch.object(RN, "CHECK_TAKES", True), \
                mock.patch.object(LC, "record", lambda *a: checks), \
                mock.patch.object(LN, "pick_best", lambda ep, lid, takes, score: picks.append(takes) or takes[-1]), \
                mock.patch("seriesmith.targets.runs_partner", lambda t: False):
            before = set(threading.enumerate())
            RN.Runner._check_line(fake, "ep", {"id": "sh010.1", "text": "Cut it."}, tried[-1], target,
                                  "local", None, retry, tried)
            for th in set(threading.enumerate()) - before:
                th.join(5)
        return asked, picks

    def test_a_failed_line_is_made_again_then_the_best_kept(self):
        bad = {"flags": ["words"]}
        asked, picks = self.go(bad, RT.Plan(2), [1])
        self.assertEqual(len(asked), 1)
        self.assertEqual(asked[0][5].tries, 1)               # the next take's own plan
        self.assertEqual(asked[0][6], [1])
        asked, picks = self.go(bad, RT.Plan(0), [1, 2, 3])   # out of tries: the best of the three
        self.assertEqual((asked, picks), ([], [[1, 2, 3]]))
        asked, picks = self.go({"flags": []}, RT.Plan(1), [1, 2])   # this one passed
        self.assertEqual((asked, picks), ([], [[1, 2]]))

    def test_no_retries_asked_or_a_paid_model(self):
        self.assertEqual(self.go({"flags": ["gap"]}, None, [1]), ([], []))
        asked, picks = self.go({"flags": ["gap"]}, RT.Plan(2), [1], hosted=True)
        self.assertEqual((asked, picks), ([], [[1]]))
        asked, _ = self.go({"flags": ["gap"]}, RT.Plan(2, paid=True), [1], hosted=True)
        self.assertEqual(len(asked), 1)


if __name__ == "__main__":
    unittest.main()
