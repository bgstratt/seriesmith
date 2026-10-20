"""
Every picture, clip and icon the editor, the docs site and the presets show is
in the repo: none of them may be gitignored. (A `*.png`, then a `*.jpg`, rule
once kept the preset pictures out of every clone; this catches the next one.)
"""
from __future__ import annotations

import os
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# the folders whose files are shown as they are
SHOWN = ("seriesmith/presets/img", "seriesmith/server/static", "web/src/brand", "docs/site",
         "comfy_nodes/web")
MEDIA = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".ico", ".mp4", ".webm", ".js", ".html", ".css")


@unittest.skipUnless(shutil.which("git") and os.path.isdir(os.path.join(ROOT, ".git")), "not a git checkout")
class ShippedAssetsTest(unittest.TestCase):
    def test_nothing_shown_is_ignored(self):
        files = [os.path.relpath(os.path.join(d, f), ROOT).replace(os.sep, "/")
                 for folder in SHOWN for d, _, fs in os.walk(os.path.join(ROOT, folder))
                 for f in fs if f.lower().endswith(MEDIA)]
        self.assertTrue(any(f.startswith("seriesmith/presets/img/") for f in files))
        # bytes: text mode on Windows would send "\r\n", and git would match no path
        r = subprocess.run(["git", "check-ignore", "--no-index", "--stdin"], cwd=ROOT,
                           input=("\n".join(files) + "\n").encode("utf-8"), capture_output=True)
        ignored = [f for f in r.stdout.decode("utf-8").splitlines() if f]
        self.assertEqual(ignored, [], "gitignored, so no clone would have them: add an exception to .gitignore")


if __name__ == "__main__":
    unittest.main()
