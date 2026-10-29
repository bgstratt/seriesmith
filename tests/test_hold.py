"""
The `hold` target (targets/video/hold, seriesmith/hold.py): a shot whose
model is a picture held still. It builds as any shot (its first keyframe a
required picture), and Generate holds that picture on the queue's local lane
with ffmpeg, nothing sent to a backend: a take of the shot's length, at the
pass's size and the cut's rate, silent or with its dub under it; stale as any
take when the shot or its picture changes. On the built kitchen_sink episode.
"""
from __future__ import annotations

import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from seriesmith import api as A  # noqa: E402
from seriesmith import ff as FF  # noqa: E402
from seriesmith import finish as F  # noqa: E402
from seriesmith import hold as H  # noqa: E402
from seriesmith import jobs as J  # noqa: E402
from seriesmith import takes as T  # noqa: E402
from seriesmith import targets as TG  # noqa: E402
import test_api  # noqa: E402
from test_api import ApiTest  # noqa: E402
from test_render import ENV  # noqa: E402


def tearDownModule():
    test_api.tearDownModule()


def picture(path: str, color: str = "red", size: str = "300x300") -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    subprocess.run([*FF.tool("ffmpeg"), "-y", "-v", "error", "-f", "lavfi", "-i",
                    f"color=c={color}:size={size}", "-frames:v", "1", path],
                   check=True, capture_output=True)
    return path


class HoldTest(ApiTest):
    def setUp(self):
        super().setUp()
        self.script = os.path.join(self.ep, "ks01.md")
        with open(self.script, encoding="utf-8") as fh:
            text = fh.read()
        # sh010 held: its model is hold, and 2.5 s long
        text = text.replace("## sh010\nwho: ada\n", "## sh010\nwho: ada\ntarget: hold\n", 1)
        self.rebuild(text)
        self.first = os.path.join(self.ep, "refs", "shots", "sh010", "first.png")

    def rebuild(self, text: str) -> None:
        with open(self.script, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        for flags in ([], ["--proxy"]):
            subprocess.run([sys.executable, "-m", "seriesmith", "build",
                            os.path.join(self.ep, "series.json"), self.script, "-o", self.ep,
                            *flags], check=True, capture_output=True, env=ENV)

    def entry(self, pass_="proxy") -> dict:
        doc, i = J.find_shot(self.ep, pass_, "sh010")
        return doc["shots"][i]

    def test_the_target_loads_and_builds(self):
        t = TG.load_target("hold", "video")
        self.assertTrue(H.is_hold(t))
        self.assertEqual(t.backends, ["local"])
        e = self.entry()
        self.assertEqual(e["keyframes"], {"first": "refs/shots/sh010/first.png"})
        self.assertEqual(e["audio_policy"], "silent")

    def test_without_its_picture_it_is_blocked(self):
        got = self.render("sh010")
        self.assertEqual(got["queued"], [])
        self.assertIn("first keyframe", got["skipped"][0]["reason"])

    def test_generate_holds_its_picture(self):
        picture(self.first)
        graphs = len(self.comfy.graphs)
        got = self.render("sh010")
        (q,) = got["queued"]
        self.assertEqual((q["target"], q["backend"]), ("hold", "this machine"))
        self.settle()
        self.assertEqual(len(self.comfy.graphs), graphs)       # nothing sent to ComfyUI
        t = T.get_take(self.ep, "proxy", "sh010", q["take"])
        e = self.entry()
        sc = t.sidecar
        self.assertEqual(sc["status"], "ok", sc.get("save_notes"))
        self.assertEqual(sc["target"], "hold")
        info = F.probe(t.paths.mp4)
        self.assertEqual(info["frames"], e["length"])
        self.assertEqual((info["width"], info["height"]),
                         (J.find_shot(self.ep, "proxy", "sh010")[0]["defaults"]["width"],
                          J.find_shot(self.ep, "proxy", "sh010")[0]["defaults"]["height"]))
        self.assertFalse(info["audio"])
        self.assertTrue(os.path.isfile(t.paths.thumb))
        # fresh, then stale when the picture changes, and when its length does
        _, shots = self.status()
        tk = next(x for x in shots["sh010"]["takes"] if x["take"] == q["take"])
        self.assertEqual(tk["stale"], [])
        picture(self.first, "blue")
        _, shots = self.status()
        tk = next(x for x in shots["sh010"]["takes"] if x["take"] == q["take"])
        self.assertIn("ref", tk["stale"])
        with open(self.script, encoding="utf-8") as fh:
            text = fh.read()
        self.rebuild(text.replace("dur: 2.5", "dur: 4", 1))
        _, shots = self.status()
        tk = next(x for x in shots["sh010"]["takes"] if x["take"] == q["take"])
        self.assertIn("script", tk["stale"])

    def test_encode_lays_a_track_under_it(self):
        pic = picture(os.path.join(self.tmp, "p.png"))
        wav = os.path.join(self.tmp, "a.wav")
        subprocess.run([*FF.tool("ffmpeg"), "-y", "-v", "error", "-f", "lavfi", "-i",
                        "sine=frequency=440:duration=1", wav], check=True, capture_output=True)
        out = os.path.join(self.tmp, "held.mp4")
        H.encode(pic, out, 48, 24, (320, 180), wav)
        info = F.probe(out)
        self.assertEqual((info["frames"], info["width"], info["height"], info["audio"]),
                         (48, 320, 180, True))
        with self.assertRaises(H.HoldError):
            H.encode(pic, out, 0, 24, (320, 180))


if __name__ == "__main__":
    unittest.main()
