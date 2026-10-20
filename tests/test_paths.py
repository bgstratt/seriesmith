"""
seriesmith/core/paths: where an episode's files are, the same for everything.
The series config is the episode folder's, else its parent's (a series folder
every episode shares); align and the stage commands (`seriesmith build`)
didn't look in the parent.
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
from seriesmith.core import paths as P  # noqa: E402

STARTER = os.path.join(ROOT, "examples", "starter")


class PathsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.show = os.path.join(self._tmp.name, "Show")
        self.ep = os.path.join(self.show, "ep01")
        os.makedirs(self.ep)

    def touch(self, *parts):
        p = os.path.join(*parts)
        open(p, "w").close()
        return p

    def test_the_episode_folder_then_its_parent(self):
        self.assertIsNone(P.series_config_path(self.ep))
        shared = self.touch(self.show, "series.json")
        self.assertEqual((P.series_home(self.ep), P.series_config_path(self.ep)),
                         (self.show, shared))
        own = self.touch(self.ep, "series.json")
        self.assertEqual(P.series_config_path(self.ep), own)

    def test_the_script(self):
        self.assertIsNone(P.episode_script(self.ep))
        self.touch(self.ep, "refs_todo.md")
        self.touch(self.ep, "notes.md")
        other = self.touch(self.ep, "pilot.md")
        self.assertEqual(P.episode_script(self.ep), other)          # the only real one
        self.touch(self.ep, "draft.md")
        self.assertIsNone(P.episode_script(self.ep))                 # two: can't tell
        named = self.touch(self.ep, "ep01.md")
        self.assertEqual(P.episode_script(self.ep), named)           # its own name wins

    def test_episode_files_say_what_is_missing(self):
        with self.assertRaises(ValueError) as cm:
            P.episode_files(self.ep)
        self.assertIn("no series.json", str(cm.exception))
        self.touch(self.show, "series.json")
        with self.assertRaises(ValueError) as cm:
            P.episode_files(self.ep)
        self.assertIn("no .md found", str(cm.exception))
        self.touch(self.ep, "ep01.md")
        self.assertEqual(P.episode_files(self.ep),
                         (os.path.join(self.show, "series.json"), os.path.join(self.ep, "ep01.md")))

    def test_safe_id(self):
        self.assertEqual(P.safe_id("sh 010/a:b"), "sh_010_a_b")
        self.assertEqual(P.safe_id("", "shot"), "shot")
        self.assertEqual(P.safe_id(""), "")


class SharedSeriesConfigCommandTest(unittest.TestCase):
    """`seriesmith build <episode>` and `--each` with the series config in the
    series folder, as the editor has always built them."""

    def test_build_and_each(self):
        with tempfile.TemporaryDirectory() as tmp:
            show = os.path.join(tmp, "Show")
            ep = os.path.join(show, "ep01")
            os.makedirs(ep)
            shutil.copy(os.path.join(STARTER, "series.json"), show)
            shutil.copy(os.path.join(STARTER, "ep01.md"), ep)
            os.makedirs(os.path.join(show, "refs"))                  # not an episode
            env = dict(os.environ)
            r = subprocess.run([sys.executable, "-m", "seriesmith.commands", "build", ep],
                               capture_output=True, text=True, encoding="utf-8", env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertTrue(os.path.isfile(os.path.join(ep, "shotlist", "shotlist.json")))
            r = subprocess.run([sys.executable, "-m", "seriesmith.commands", "check", show,
                                "--each"], capture_output=True, text=True, encoding="utf-8", env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("=== check: " + ep, r.stdout)
            self.assertNotIn(os.path.join(show, "refs"), r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
