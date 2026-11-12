"""
The count check (countcheck.py): more people or faces in a take than its shot has.

  - An extras line counts from its words, or leaves the number open (and the take unchecked).
  - A span over the shot's number for a quarter second or more flags; a frame or so doesn't,
    and fewer never does.
  - With no weights or no ultralytics here, it says why and flags nothing. The tests never
    reach a real model: conftest points at empty settings and an unreachable ComfyUI.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from seriesmith import countcheck as CC  # noqa: E402
from seriesmith import takecheck as TC  # noqa: E402


class ExtrasTest(unittest.TestCase):
    def test_none(self):
        self.assertEqual(CC.extras_count(None), 0)
        self.assertEqual(CC.extras_count(""), 0)

    def test_said(self):
        for text, n in [
            ("a night nurse in green scrubs stepping aside against the wall, soft", 1),
            ("an older librarian in a cardigan already standing behind the desk", 1),
            ("two paramedics wheeling a gurney", 2),
            ("a nurse and a porter by the lift", 2),
            ("one masked man in black tails, his back mostly to camera", 1),
            ("a skinny young man behind the register; two customers in line", 3),
            ("a couple at the far table", 2),
            ("3 guards at the gate", 3),
        ]:
            self.assertEqual(CC.extras_count(text), n, text)

    def test_left_open(self):
        for text in ["day-shift nurses passing", "a few night staff already at work",
                     "a dozen reporters", "two dozen dancers", "nurses rushing past",
                     "the shoulders of the crowd", "a crowd at the rail"]:
            self.assertIsNone(CC.extras_count(text), text)


def rows(counts, col=1, fps=CC.SAMPLE_FPS):
    """[[t, people, faces]] with `counts` in column `col`, the other at 1."""
    return [[round(i / fps, 3), *( (n, 1) if col == 1 else (1, n) )] for i, n in enumerate(counts)]


class JudgeTest(unittest.TestCase):
    def test_a_run_over_flags(self):
        got = CC.judge(rows([1, 1, 2, 2, 2, 1]), 1)
        self.assertTrue(got["flag"])
        self.assertEqual(got["at"], [0.25, 0.5])
        self.assertIn("2 people for 1", got["why"])

    def test_one_frame_over_does_not(self):
        self.assertFalse(CC.judge(rows([1, 2, 1, 2, 1]), 1)["flag"])

    def test_a_peak_the_median_hides(self):
        """sh1570: 4 on the median, 5 for a while."""
        got = CC.judge(rows([4, 4, 5, 5, 5, 4, 4, 4, 4, 4]), 4)
        self.assertTrue(got["flag"])

    def test_faces_too(self):
        got = CC.judge(rows([1, 2, 2, 2], col=2), 1)
        self.assertTrue(got["flag"])
        self.assertIn("faces", got["why"])

    def test_fewer_never(self):
        self.assertFalse(CC.judge(rows([0, 0, 0, 0]), 3)["flag"])

    def test_no_frames(self):
        self.assertFalse(CC.judge([], 1)["flag"])


SERIES = """{"series": {"id": "t", "title": "T", "fps": 24, "width": 1344, "height": 768},
 "subjects": {
  "ada": {"kind": "character", "name": "Ada", "design": "a girl"},
  "ada_coat": {"of": "ada", "design": "in a coat"},
  "ben": {"kind": "character", "name": "Ben", "design": "a boy"},
  "box": {"kind": "prop", "name": "the box", "design": "a box"}},
 "locations": {"yard": {"description": "a yard"}}}
"""
SCRIPT = """= t01  T

# sq01  yard

## sh010
who: ada_coat
with: ben, box
size: medium
dur: 3
Ada hands Ben the box.

## sh020
who: ada
size: wide
dur: 3
extras: two neighbours at the fence
Ada waves.

## sh030
who: ada
size: wide
dur: 3
extras: neighbours at the fence
Ada waves again.
"""


class ExpectedTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="countcheck-")
        self.ep = os.path.join(self.tmp, "t01")
        os.makedirs(self.ep)
        with open(os.path.join(self.ep, "series.json"), "w", encoding="utf-8") as fh:
            fh.write(SERIES)
        with open(os.path.join(self.ep, "t01.md"), "w", encoding="utf-8") as fh:
            fh.write(SCRIPT)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_cast_once_each_props_not(self):
        self.assertEqual(CC.expected(self.ep, "sh010"), (2, ""))

    def test_extras_said(self):
        self.assertEqual(CC.expected(self.ep, "sh020"), (3, ""))

    def test_extras_open(self):
        n, why = CC.expected(self.ep, "sh030")
        self.assertIsNone(n)
        self.assertIn("extras", why)

    def test_a_shot_gone(self):
        self.assertIsNone(CC.expected(self.ep, "sh999")[0])

    def test_unchecked_here_says_why(self):
        take = mock.Mock(shot="sh010")
        got = CC.check(self.ep, take, {})
        self.assertFalse(got["flag"])
        self.assertTrue(got["why"])

    def test_measured(self):
        take = mock.Mock(shot="sh010")
        take.paths.mp4 = "x.mp4"
        with mock.patch.object(CC, "weights", return_value=({"person": "p", "face": "f"}, "")), \
                mock.patch.object(CC, "python", return_value=("py", "")), \
                mock.patch.object(CC, "measure", return_value=rows([2, 3, 3, 3])):
            got = CC.check(self.ep, take, {})
        self.assertTrue(got["flag"])
        self.assertEqual(got["want"], 2)

    def test_a_multishot_group_is_not_checked(self):
        self.assertIsNone(CC.check(self.ep, mock.Mock(shot="sh010"), {"multishot": [{"id": "sh010"}]}))


class RegisteredTest(unittest.TestCase):
    def test_it_is_a_take_check(self):
        self.assertIs(TC.CHECKERS.get("count"), CC.check)


class HelperTest(unittest.TestCase):
    def test_a_file_that_isnt_the_known_one_is_refused(self):
        from seriesmith.helpers import counts as H
        with tempfile.NamedTemporaryFile(suffix=".pt", delete=False) as fh:
            fh.write(b"not the weights")
        try:
            with self.assertRaises(ValueError):
                H.trusted(fh.name, "person")
        finally:
            os.remove(fh.name)


if __name__ == "__main__":
    unittest.main()
