"""
The script-writing skill's bundled checker runs on its own.

The skill carries a copy of the build (scripts/check.py, scripts/seriesmith/) so
an assistant can validate a script where seriesmith isn't installed (Claude's
sandbox). These build that bundle into a temporary folder and run it there, its
own package first on the path as it is in the skill: a check that reaches for a
module the bundle doesn't carry fails here, not in a user's chat.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import make_prompts as P  # noqa: E402

DEMO = os.path.join(ROOT, "examples", "demo")


class SkillBundleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="sm-skill-")
        P.bundle(P.body(), out=cls.tmp)
        cls.check = os.path.join(cls.tmp, P.NAME, "scripts", "check.py")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def run_check(self, series: str, script: str) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
        # -I -S: no site-packages, so not this venv's seriesmith either (as in an assistant's sandbox)
        return subprocess.run([sys.executable, "-I", "-S", self.check, series, script, "--check"],
                              capture_output=True, text=True, encoding="utf-8", env=env,
                              cwd=self.tmp, timeout=120)

    def test_the_bundle_carries_what_a_check_imports(self):
        pkg = os.path.join(self.tmp, P.NAME, "scripts", "seriesmith")
        for f in P.BUNDLE_FILES:
            self.assertTrue(os.path.isfile(os.path.join(pkg, f)), f)
        self.assertFalse(os.path.exists(os.path.join(pkg, "upscale.py")))

    def test_the_demo_checks_with_its_recipes_passed_over(self):
        """The demo's series config (as the skill wrote it) has an upscale recipe:
        checked with a note, not a crash."""
        r = self.run_check(os.path.join(DEMO, "series.json"), os.path.join(DEMO, "ep01.md"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("27 shots", r.stdout)
        self.assertIn("upscale.master isn't checked by this copy", r.stdout)
        self.assertNotIn("Traceback", r.stderr)

    def test_a_post_recipe_is_passed_over_too(self):
        with open(os.path.join(DEMO, "series.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        cfg["post"] = {"master": {"enhance": "production", "motion_blur": 0.3}}
        series = os.path.join(self.tmp, "series.json")
        with open(series, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        script = os.path.join(self.tmp, "ep01.md")
        shutil.copy(os.path.join(DEMO, "ep01.md"), script)
        r = self.run_check(series, script)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("post.master isn't checked by this copy", r.stdout)

    def test_the_starter_checks(self):
        starter = os.path.join(ROOT, "examples", "starter")
        r = self.run_check(os.path.join(starter, "series.json"), os.path.join(starter, "ep01.md"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("isn't checked by this copy", r.stdout)


if __name__ == "__main__":
    unittest.main()
