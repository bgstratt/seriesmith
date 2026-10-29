"""
A shot's colour in the cut (seriesmith/color.py): the check, the matrix (held
to tests/fixtures/color_cases.json, which web/test/color.test.ts holds the
editor's copy to), and ffmpeg's filters doing what the matrix says.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from seriesmith import color as C  # noqa: E402
from seriesmith import ff as FF  # noqa: E402

CASES = os.path.join(HERE, "fixtures", "color_cases.json")

try:
    from PIL import Image
except ImportError:                                      # pragma: no cover
    Image = None


class ColorTest(unittest.TestCase):
    def test_check(self):
        self.assertEqual(C.check(None), {})
        self.assertEqual(C.check({"exposure": 0, "warmth": 0.12345}), {"warmth": 0.123})
        for bad in ({"hue": 1}, {"exposure": 3}, {"contrast": -1.5}, {"black": "0.1"},
                    {"saturation": True}, [1]):
            with self.assertRaises(ValueError):
                C.check(bad)

    def test_matrix_is_the_shared_cases(self):
        with open(CASES, encoding="utf-8") as fh:
            cases = json.load(fh)["cases"]
        for case in cases:
            m, off = C.matrix(case["color"])
            for row, want in zip(m, case["m"]):
                for v, w in zip(row, want):
                    self.assertAlmostEqual(v, w, places=7)
            for v, w in zip(off, case["offset"]):
                self.assertAlmostEqual(v, w, places=7)
        self.assertEqual(C.filters({}), [])

    @unittest.skipUnless(Image, "reading the frame needs Pillow")
    def test_ffmpeg_does_what_the_matrix_says(self):
        with tempfile.TemporaryDirectory() as d:
            def frame(color) -> tuple:
                out = os.path.join(d, "f.png")
                vf = ",".join(["format=yuv420p", *C.filters(color)])
                subprocess.run([*FF.tool("ffmpeg"), "-y", "-v", "error", "-f", "lavfi", "-i",
                                "color=c=0x806040:size=64x64:d=0.2", "-vf", vf, "-frames:v", "1",
                                out], check=True, capture_output=True)
                with Image.open(out) as im:
                    return im.convert("RGB").getpixel((32, 32))
            base = [v / 255 for v in frame({})]
            for color in ({"exposure": 1}, {"black": 0.1}, {"saturation": -1}, {"warmth": 1},
                          {"contrast": 0.7}, {"contrast": -1}, {"tint": 1}, {"tint": -1},
                          {"exposure": 2, "contrast": 1},    # past colorchannelmixer's 2x
                          {"exposure": -0.5, "saturation": 0.5, "warmth": -0.5, "black": -0.05,
                           "contrast": 0.2, "tint": 0.4}):
                m, off = C.matrix(color)
                want = [max(0.0, min(1.0, sum(m[i][j] * base[j] for j in range(3)) + off[i])) * 255
                        for i in range(3)]
                got = frame(color)
                for g, w in zip(got, want):
                    # 4:2:0 and back costs a few levels
                    self.assertLess(abs(g - w), 8, (color, got, want))


try:
    import numpy as np
except ImportError:                                      # pragma: no cover
    np = None


@unittest.skipUnless(np, "matching needs numpy")
class MatchByTest(unittest.TestCase):
    """What a match compares (color.MATCH_BY, helpers/colorstats.py), on made-up
    pixels: a face (skin) before a background. The clip is the base's face a
    little darker and cooler before a pale window instead of a green wall: by
    skin, it comes back brighter and warmer, the window not counted; by luma,
    only the brightness sliders move and the clip's own colour stays."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.join(os.path.dirname(HERE), "seriesmith", "helpers"))
        import colorstats
        cls.S = colorstats
        rng = np.random.default_rng(1)

        def picture(skin, background, n=4000, share=0.3):
            k = int(n * share)
            face = np.clip(np.array(skin) + rng.normal(0, 0.03, (k, 3)), 0, 1)
            rest = np.clip(np.array(background) + rng.normal(0, 0.03, (n - k, 3)), 0, 1)
            return np.vstack([face, rest])
        face = (0.78, 0.56, 0.44)
        cls.base = picture(face, (0.2, 0.45, 0.25))               # a green wall
        dim = cls.S.apply(np.array([face]), {"exposure": -0.4, "warmth": -0.5})[0]
        cls.clip = picture(tuple(dim), (0.9, 0.92, 0.95))          # a pale window

    def test_the_skin(self):
        self.assertGreater(self.S.is_skin(self.base).mean(), 0.2)
        got = self.S.match(self.base, self.clip, "skin")
        self.assertGreater(got["exposure"], 0.2)
        self.assertGreater(got["warmth"], 0.25)
        self.assertNotIn("contrast", got)                         # skin leaves it be
        self.assertNotIn("black", got)
        # the whole frame sees the green wall and the window as well
        frame = self.S.match(self.base, self.clip, "frame")
        self.assertNotEqual(frame, got)

    def test_too_little_skin_is_said(self):
        wall = self.base[self.base[:, 1] > self.base[:, 0]]
        with self.assertRaisesRegex(ValueError, "too little skin"):
            self.S.match(wall, self.clip, "skin")

    def test_luma_keeps_the_clips_colour(self):
        own = {"warmth": 0.3, "saturation": -0.2, "exposure": 1.0}
        got = self.S.match(self.base, self.clip, "luma", own)
        self.assertEqual((got.get("warmth"), got.get("saturation")), (0.3, -0.2))
        self.assertNotEqual(got.get("exposure"), 1.0)             # its own brightness replaced
        self.assertNotIn("tint", got)

    def test_by_is_checked(self):
        with self.assertRaisesRegex(ValueError, "by must be"):
            C.match({"path": "x", "frames": [0]}, [], by="hue")


if __name__ == "__main__":
    unittest.main()
