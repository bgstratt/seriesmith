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


class HoldEpisode(ApiTest):
    """kitchen_sink with sh010 on the hold model."""
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


class HoldTest(HoldEpisode):

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


class ColorMatchTest(HoldEpisode):
    """Matching clips' colour (POST /seriesmith/color/match), on held takes:
    sh020 holds a darker, cooler copy of sh010's picture; matched to sh010 it
    comes back brighter and warmer. The rest of sq01 has no takes (skipped,
    said why); sq02's shots aren't asked."""

    def setUp(self):
        super().setUp()
        with open(self.script, encoding="utf-8") as fh:
            text = fh.read()
        self.rebuild(text.replace("## sh020\n", "## sh020\ntarget: hold\n", 1))

    def test_match_brings_a_clip_in_line(self):
        from seriesmith import color as COL
        src = os.path.join(self.tmp, "grad.png")
        subprocess.run([*FF.tool("ffmpeg"), "-y", "-v", "error", "-f", "lavfi", "-i",
                        "gradients=size=320x180:seed=7:c0=0x704020:c1=0x3060a0:c2=0xd0c0a0:"
                        "c3=0x202818:nb_colors=4", "-frames:v", "1", src], check=True, capture_output=True)
        picture(self.first)
        os.replace(src, self.first)
        dark = os.path.join(self.ep, "refs", "shots", "sh020", "first.png")
        os.makedirs(os.path.dirname(dark), exist_ok=True)
        subprocess.run([*FF.tool("ffmpeg"), "-y", "-v", "error", "-i", self.first, "-vf",
                        ",".join(COL.filters({"exposure": -0.5, "warmth": -0.6})), dark],
                       check=True, capture_output=True)
        self.render("sh010", "sh020")
        self.settle()
        got = self.ok(A.post_color_match(self.ctx, {"ep": self.ep, "base": "sh010"}))
        self.assertEqual(got["base"], "sh010")
        c = got["colors"]["sh020"]
        self.assertGreater(c.get("exposure", 0), 0.3)
        self.assertGreater(c.get("warmth", 0), 0.3)
        # the rest of sq01, without takes, skipped; nothing of sq02's asked
        why = {s["shot"]: s["why"] for s in got["skipped"]}
        self.assertEqual(why.get("sh030"), "it has no finished take in the cut")
        self.assertNotIn("sh110", why)
        self.assertEqual(list(got["colors"]), ["sh020"])
        # named shots; a locked one and the base itself are skipped, said why
        self.ok(A.put_cut(self.ctx, {"ep": self.ep, "pass": "proxy", "entries": [
            {"shot": "sh010"}, {"shot": "sh020", "locked": True}]}))
        got = self.ok(A.post_color_match(self.ctx, {"ep": self.ep, "base": "sh010",
                                                    "shots": ["sh020", "sh010"]}))
        self.assertEqual(got["colors"], {})
        self.assertEqual({s["shot"]: s["why"] for s in got["skipped"]},
                         {"sh020": "it's locked", "sh010": "it's the base"})
        # a base with no take
        self.err(A.post_color_match(self.ctx, {"ep": self.ep, "base": "sh030"}), 400)


class LookTest(HoldEpisode):
    """A take's look is recorded when it's made, and a clip out of line with
    the rest of its sequence says so in the status (`cut.look_off`), its colour
    in the cut counted: the timeline's badge."""

    def setUp(self):
        super().setUp()
        with open(self.script, encoding="utf-8") as fh:
            text = fh.read()
        for sid in ("sh020", "sh030", "sh040"):
            text = text.replace(f"## {sid}\n", f"## {sid}\ntarget: hold\n", 1)
        self.rebuild(text)

    def held(self, sid: str, mix: str | None = None) -> None:
        """sid's picture: a gradient, its channels scaled by `mix` (colorchannelmixer)."""
        dst = os.path.join(self.ep, "refs", "shots", sid, "first.png")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        vf = f"colorchannelmixer={mix}" if mix else "null"
        subprocess.run([*FF.tool("ffmpeg"), "-y", "-v", "error", "-f", "lavfi", "-i",
                        "gradients=size=320x180:seed=7:c0=0x704020:c1=0x3060a0:c2=0xd0c0a0:"
                        "c3=0x202818:nb_colors=4", "-vf", vf, "-frames:v", "1", dst],
                       check=True, capture_output=True)

    def test_the_odd_one_out_is_flagged_until_its_colour_fixes_it(self):
        for sid in ("sh010", "sh020", "sh030"):
            self.held(sid)
        self.held("sh040", "rr=0.5:gg=0.55:bb=0.62")         # darker and cooler
        self.render("sh010", "sh020", "sh030", "sh040")
        self.settle()
        t = T.get_take(self.ep, "proxy", "sh040", 1)
        self.assertEqual(len(t.sidecar["look"]["px"]), 6 * 128)   # recorded as it was made
        _, shots = self.status()
        off = shots["sh040"]["cut"]["look_off"]
        self.assertTrue(any("darker" in w for w in off), off)
        self.assertIn("cooler", off)
        self.assertIsNone(shots["sh010"]["cut"]["look_off"])
        # matched to sh010, its colour in the cut brings it back in line
        got = self.ok(A.post_color_match(self.ctx, {"ep": self.ep, "base": "sh010",
                                                    "shots": ["sh040"]}))
        self.ok(A.put_cut(self.ctx, {"ep": self.ep, "pass": "proxy", "entries": [
            {"shot": "sh040", "color": got["colors"]["sh040"]}]}))
        _, shots = self.status()
        self.assertIsNone(shots["sh040"]["cut"]["look_off"])

    def test_older_takes_are_measured_on_asking(self):
        for sid in ("sh010", "sh020", "sh030"):
            self.held(sid)
        self.render("sh010", "sh020", "sh030")
        self.settle()
        for sid in ("sh010", "sh020"):
            t = T.get_take(self.ep, "proxy", sid, 1)
            T.update_sidecar(t.paths.sidecar, look=None)
        got = self.ok(A.post_color_measure(self.ctx, {"ep": self.ep}))
        self.assertEqual((sorted(got["measured"]), got["had"]), (["sh010", "sh020"], 1))
        got = self.ok(A.post_color_measure(self.ctx, {"ep": self.ep}))
        self.assertEqual((got["measured"], got["had"]), ([], 3))
