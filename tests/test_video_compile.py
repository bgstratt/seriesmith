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



class FallbackWarningTest(unittest.TestCase):
    """A model that makes its own sound and renders a cloned voice or a dub as
    generate says so in --check, as ltx2 and H3 do (the prose and Router
    targets didn't); a silent one's "makes no sound" line already says it."""

    SHOT = "## sh010\nwho: ada\nsize: ms\ndur: 3\nADA: Hello there.\n"   # clone: the series says so

    def test_a_sounding_router_model_says_what_falls_back(self):
        # Seedance hears voice samples now (router_video.sounds): Kling doesn't
        out = build("kling_v3_omni", self.SHOT).stdout
        self.assertIn("ask for audio clone, which Kling can't render", out)
        self.assertNotIn("can't render", build("seedance_2_5", self.SHOT).stdout)

    def test_a_silent_model_says_it_once(self):
        out = build("wan22_ti2v", self.SHOT).stdout
        self.assertNotIn("can't render", out)
        self.assertIn("makes no sound", out)

    def test_each_router_model_names_itself(self):
        import glob
        import json
        for f in glob.glob(os.path.join(ROOT, "seriesmith", "targets", "video", "*", "target.json")):
            with open(f, encoding="utf-8") as fh:
                spec = json.load(fh)
            why = ((spec.get("recipe") or {}).get("policy_fallback") or {}).get("why", "")
            if spec.get("code") == "builtin:router_video" and "makes its own sound" in why:
                with self.subTest(target=spec["id"]):
                    self.assertTrue(why.startswith(spec["short"] + " "), why)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class FullStopTest(unittest.TestCase):
    """A style, a place's description or a design that ends in a full stop is
    written into a sentence without it: "...long soft shadows., the camera"
    and "styling: ...glasses.." before (Ballroom ep03 sh130). Every writer
    the mixed episode compiles for (H3, ltx2), and the refs' image prompts."""

    def test_no_doubled_stops(self):
        import json
        import re
        with tempfile.TemporaryDirectory() as d:
            with open(MIXED, encoding="utf-8") as fh:
                cfg = json.load(fh)
            cfg["style"]["look"] = cfg["style"]["look"].rstrip(".") + "."
            for e in list(cfg["locations"].values()) + list(cfg["subjects"].values()):
                if isinstance(e, dict):
                    for k in ("description", "design"):
                        if e.get(k):
                            e[k] = e[k].rstrip(".") + "."
            with open(os.path.join(d, "series.json"), "w", encoding="utf-8") as fh:
                json.dump(cfg, fh)
            script = os.path.join(os.path.dirname(MIXED), "script.md")
            r = subprocess.run([sys.executable, "-m", "seriesmith.build",
                                os.path.join(d, "series.json"), script, "-o", d],
                               capture_output=True, text=True, encoding="utf-8", env=ENV)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            texts = []
            for name in ("shotlist.json", "shotlist.ltx2.json"):
                with open(os.path.join(d, "shotlist", name), encoding="utf-8") as fh:
                    for sh in json.load(fh)["shots"]:
                        p = sh["prompt"]
                        texts.append((name, sh["id"], "\n".join(p) if isinstance(p, list) else p))
            with open(os.path.join(d, "refs_todo.json"), encoding="utf-8") as fh:
                todo = json.load(fh)
            texts += [("refs_todo", k, json.dumps(v)) for k, v in
                      (todo.items() if isinstance(todo, dict) else enumerate(todo))]
        self.assertGreater(len(texts), 6)
        for where, sid, text in texts:
            with self.subTest(where=where, shot=sid):
                self.assertIsNone(re.search(r"(?<!\.)\.\.(?!\.)|\.,", text), text[:400])
