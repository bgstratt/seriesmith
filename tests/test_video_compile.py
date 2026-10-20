"""
targets/video_compile: the compile steps every video target does the same way
(ltx2, H3 FL2VA, ltx2_ingredients, the prose and Router targets). The goldens
pin what they write for each target; these say what the shared steps are for.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
from test_render import ENV  # noqa: E402

MIXED = os.path.join(HERE, "fixtures", "mixed", "series.json")


def build(target: str, shot: str) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as d:
        shutil.copy(MIXED, d)
        with open(os.path.join(d, "x01.md"), "w", encoding="utf-8") as fh:
            fh.write(f"= x01  T\n\n# sq01  kitchen\ntarget: {target}\n\n{shot}")
        return subprocess.run([sys.executable, "-m", "seriesmith.build",
                               os.path.join(d, "series.json"), os.path.join(d, "x01.md"),
                               "-o", d, "--check"],
                              capture_output=True, text=True, encoding="utf-8", env=ENV)


class TooLongTest(unittest.TestCase):
    """A shot past a target's longest names itself and says what to do, on
    every target that compiles through the shared steps (ltx2 said only
    "2160 frames is longer than LTX-2's maximum of 481 (20.04s)")."""

    def test_it_names_the_shot_in_seconds(self):
        for target in ("ltx2", "ltx2_ingredients", "wan22_ti2v"):
            with self.subTest(target=target):
                r = build(target, "## sh010\nwho: ada\nsize: ws\ndur: 90\nAda waits.\n")
                out = r.stdout + r.stderr
                self.assertNotEqual(r.returncode, 0, out)
                self.assertIn("shot sh010: 90.00s is longer than", out)
                self.assertIn("Split the shot, or render it on another target.", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
