"""
A shot's effects (docs/SOUND.md phase 4; seriesmith/fx.py): the `foley` target kind and its
prompts, what a take is asked against the cut, stale when the cut's picture changes, the
mix's `fx`, the effects laid under the cut (render, XML lane, GET /seriesmith/mix), and the
routes. The render tests build tiny episodes with ffmpeg and are skipped without it.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
from seriesmith import api as A  # noqa: E402
from seriesmith import ff as FF  # noqa: E402
from seriesmith import fx as FX  # noqa: E402
from seriesmith import mix as MX  # noqa: E402
from seriesmith import takes as T  # noqa: E402
from seriesmith import targets as TG  # noqa: E402
from seriesmith.backends import File  # noqa: E402

HAVE_FF = bool(FF.have("ffmpeg") and FF.have("ffprobe"))
FPS = 24
CLAPS = "Hands clap twice on a formica table."


def episode(root: str, frames=(120, 120, 120), story: bool = True) -> None:
    """Three shots, each with a finished take of `frames` frames (an mp4 of a few bytes:
    the plan reads the sidecar's count), and the story IR: sh010 with a sound: line, sh020
    with only its action, sh030 with neither."""
    ids = [f"sh{10 * (i + 1):03d}" for i in range(len(frames))]
    T.write_json(os.path.join(root, "shotlist", "shotlist.json"),
                 {"episode": "ep01", "defaults": {"width": 64, "height": 64, "fps": FPS},
                  "shots": [{"id": s, "length": n, "audio_policy": "generate"}
                            for s, n in zip(ids, frames)]})
    for s, n in zip(ids, frames):
        t = T.reserve_take(root, "final", s, {"status": "queued"})
        with open(t.paths.mp4, "wb") as fh:
            fh.write(b"take one")
        T.update_sidecar(t.paths.sidecar, status="ok", frames=n, fps=FPS, width=448, height=256)
    if story:
        T.write_json(os.path.join(root, "shotlist", "shots.json"), {"episode": "ep01", "sequences": [
            {"id": "sq01", "location": "diner", "shots": [
                {"id": "sh010", "action": "She claps.", "sound": CLAPS},
                {"id": "sh020", "action": "She taps the cup three times.", "sound": None},
                {"id": "sh030", "action": "", "sound": ""}]}]})


class TargetTest(unittest.TestCase):
    def test_the_kind_and_its_default(self):
        self.assertIn("foley", TG.KINDS)
        self.assertEqual(sorted(t.id for t in TG.list_targets("foley")),
                         ["h3_foley", "hunyuan_xl_foley", "ltx23_foley"])
        self.assertEqual(TG.DEFAULT_TARGETS["foley"], "h3_foley")
        self.assertEqual(TG.DEFAULT_FOLEY_TARGET, "h3_foley")

    def test_the_prompts(self):
        video = {"frames": 121, "fps": 24.0, "seconds": 5.0417, "width": 256, "height": 160}
        h3 = TG.load_target("h3_foley").foley_prompt("hands clap twice", video)
        self.assertEqual(h3["prompt"], "The exact video given, with its sound effects only: hands "
                                       "clap twice. No dialogue, no voices, no singing, no music.")
        self.assertEqual(h3["values"], {"length": 121, "width": 256, "height": 160})
        ltx = TG.load_target("ltx23_foley").foley_prompt("Boots splash.", video)
        self.assertEqual(ltx["prompt"], "Boots splash. No dialogue, no voices, no singing, no music.")
        self.assertEqual(ltx["values"], {"frames": 121, "fps": 24.0, "end_time": 6.042})
        hy = TG.load_target("hunyuan_xl_foley").foley_prompt("A door slams", video)
        self.assertEqual(hy["values"], {"seconds": 5.042, "fps": 24.0})

    def test_every_file_has_a_download(self):
        for t in TG.list_targets("foley"):
            for name in t.named_files():
                d = TG.download_for(t, name)
                self.assertTrue(d["url"] and d["folder"], (t.id, name))
                self.assertTrue(d["url"].startswith("https://huggingface.co/"), d["url"])

    def test_the_picture_each_is_given(self):
        h3, ltx, hy = (TG.load_target(x) for x in ("h3_foley", "ltx23_foley", "hunyuan_xl_foley"))
        self.assertEqual(FX.video_for(h3, 124, 24.0, 124 / 24, (896, 512)),
                         {"frames": 124, "fps": 24.0, "seconds": 5.1667, "width": 256, "height": 160})
        got = FX.video_for(ltx, 124, 24.0, 124 / 24, (896, 512))
        self.assertEqual((got["frames"], got["width"], got["height"]), (121, 512, 288))   # 8k+1
        got = FX.video_for(hy, 80, 16.0, 5.0, (832, 480))                                 # its own rate
        self.assertEqual((got["frames"], got["fps"], got["width"], got["height"]), (80, 16.0, 512, 296))

    def test_each_graph(self):
        with tempfile.TemporaryDirectory() as d:
            pic = os.path.join(d, "t01.picture.mp4")
            with open(pic, "wb") as fh:
                fh.write(b"x")
            for t in TG.list_targets("foley"):
                video = FX.video_for(t, 120, 24.0, 5.0, (448, 256))
                brief = t.foley_prompt(CLAPS, video)
                sc = {"prompt": brief["prompt"], "negative": brief["negative"],
                      "values": brief["values"], "seed": 1234}
                g = FX.graph(t, sc, File(pic))
                by = {v["class_type"]: v for v in g.values()}
                self.assertIsInstance(by["LoadVideo"]["inputs"]["file"], File, t.id)
                self.assertIn("SaveAudio", by)
                self.assertIn(1234, [v for n in g.values() for v in n["inputs"].values()], t.id)
                self.assertIn(brief["prompt"], [v for n in g.values() for v in n["inputs"].values()])
            g = FX.graph(TG.load_target("ltx23_foley"), {"prompt": "p", "seed": 1,
                         "values": {"frames": 121, "fps": 24.0, "end_time": 6.0}}, File(pic))
            by = {v["class_type"]: v["inputs"] for v in g.values()}
            self.assertEqual((by["LTXVEmptyLatentAudio"]["frames_number"], by["LTXVEmptyLatentAudio"]["frame_rate"],
                              by["LTXVSetAudioVideoMaskByTime"]["video_fps"]), (121, 24.0, 24.0))
            self.assertEqual(by["MultimodalGuider"]["skip_blocks"], "")             # STG off
            self.assertEqual([v["inputs"]["stg"] for v in g.values() if v["class_type"] == "GuiderParameters"],
                             [0.0, 0.0])


class MixFxTest(unittest.TestCase):
    def test_check(self):
        self.assertEqual(MX.check({"fx": {"sh010": {"take": 2, "gain_db": 0, "mute": False}}}),
                         {"fx": {"sh010": {"take": 2}}})
        self.assertEqual(MX.check({"fx": {"sh010": {"take": 1, "gain_db": -4, "keep_stale": True}}}),
                         {"fx": {"sh010": {"take": 1, "gain_db": -4.0, "keep_stale": True}}})
        for bad in ({"sh010": {"gain_db": -3}}, {"sh010": {"take": 0}}, {"sh010": {"take": 1, "level": 2}},
                    {"sh 010": {"take": 1}}, {"sh010": {"take": 1, "mute": "yes"}}):
            with self.assertRaises(ValueError, msg=bad):
                MX.check({"fx": bad})

    def test_check_trims_fades_points(self):
        # all optional, dropped when 0 / empty; frames whole and in range; points on the shot
        pt = {"at": {"shot": "sh010", "frame": 30}, "db": -6}
        self.assertEqual(MX.check({"fx": {"sh010": {"take": 1, "trim_in": 0, "trim_out": 0, "fade_in": 0,
                                                    "fade_out": 0, "points": []}}}),
                         {"fx": {"sh010": {"take": 1}}})
        self.assertEqual(MX.check({"fx": {"sh010": {"take": 1, "trim_out": 20, "fade_out": 6, "points": [pt]}}}),
                         {"fx": {"sh010": {"take": 1, "trim_out": 20, "fade_out": 6,
                                           "points": [{"at": {"shot": "sh010", "frame": 30}, "db": -6.0}]}}})
        for bad in ({"take": 1, "trim_in": -1}, {"take": 1, "trim_out": 1.5}, {"take": 1, "fade_in": True},
                    {"take": 1, "fade_out": MX.FADE_MAX + 1}, {"take": 1, "points": {"at": 1}},
                    {"take": 1, "points": [{"at": {"shot": "sh020", "frame": 3}, "db": 0}]},
                    {"take": 1, "points": [{"at": {"shot": "sh010", "frame": 3}, "db": 99}]}):
            with self.assertRaises(ValueError, msg=bad):
                MX.check({"fx": {"sh010": bad}})


class PlanTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self._tmp.name, "ep01")
        episode(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_the_words(self):
        self.assertEqual(FX.shot_text(self.root, "sh010"), (CLAPS, "sound"))
        self.assertEqual(FX.shot_text(self.root, "sh020"), ("She taps the cup three times.", "action"))
        with self.assertRaises(FX.FxError):
            FX.plan(self.root, "final", "sh030")                  # nothing to make them from
        with self.assertRaises(FX.FxError):
            FX.plan(self.root, "final", "sh099")                  # not in the cut

    def test_plan_and_record(self):
        p = FX.plan(self.root, "final", "sh020")
        self.assertEqual((p["target"], p["text_from"], p["take"].take), ("h3_foley", "action", 1))
        self.assertEqual(p["video"], {"frames": 120, "fps": 24.0, "seconds": 5.0, "width": 256, "height": 160})
        self.assertEqual(p["source"]["take"], 1)
        rec = FX.record(p, FX.seed_for(self.root, "sh020", 1), "final")
        self.assertEqual(rec["seed"], FX.seed_for(self.root, "sh020", 1))
        self.assertNotEqual(FX.seed_for(self.root, "sh020", 1), FX.seed_for(self.root, "sh020", 2))
        self.assertEqual(FX.plan(self.root, "final", "sh020", "ltx23_foley")["video"]["frames"], 113)

    def test_stale(self):
        p = FX.plan(self.root, "final", "sh010")
        n = FX.reserve(self.root, "final", "sh010", FX.record(p, 1, "final"))
        sc = FX.get_take(self.root, "final", "sh010", n)
        cut = FX.cut_takes(self.root, "final")
        self.assertIsNone(FX.stale_why(sc, cut["sh010"]))
        # the cut picks another take of sh010
        t2 = T.reserve_take(self.root, "final", "sh010", {"status": "queued"})
        with open(t2.paths.mp4, "wb") as fh:
            fh.write(b"take two")
        T.update_sidecar(t2.paths.sidecar, status="ok", frames=120, fps=FPS)
        T.save_cut(self.root, {"final": [{"shot": "sh010", "take": t2.take}, {"shot": "sh020"},
                                         {"shot": "sh030"}], "proxy": []})
        cut = FX.cut_takes(self.root, "final")
        self.assertEqual(FX.stale_why(sc, cut["sh010"]), "made from t01; the cut plays t02")
        # back on take 1, then take 1 rendered again (its mp4 written anew)
        T.save_cut(self.root, {"final": [], "proxy": []})
        T.discard_files([t2.paths.mp4, t2.paths.sidecar], os.path.join(self._tmp.name, "trash"))
        cut = FX.cut_takes(self.root, "final")
        self.assertIsNone(FX.stale_why(sc, cut["sh010"]))
        time.sleep(0.01)
        with open(cut["sh010"].paths.mp4, "wb") as fh:
            fh.write(b"take one, again")
        self.assertEqual(FX.stale_why(sc, cut["sh010"]), "t01 was rendered again since")
        self.assertEqual(FX.stale_why(sc, None), "the shot has no take in the cut")


def tone(path: str, seconds: float, rate: int = 48000, amp: float = 0.25, silent_first: float = 0.0):
    np = MX._np()
    n0, n = int(silent_first * rate), int(seconds * rate)
    buf = np.zeros((n0 + n, 2), dtype=np.float32)
    buf[n0:] = amp * np.sign(np.sin(np.arange(n) / 10.0))[:, None]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    MX.write_wav(path, buf)


def finished(root: str, shot: str, wav_seconds: float, silent_first: float = 0.0, pass_: str = "final") -> int:
    """A finished effects take of `shot` (a tone after `silent_first` s of silence), made
    from the take the cut plays."""
    p = FX.plan(root, pass_, shot)
    n = FX.reserve(root, pass_, shot, FX.record(p, 1, pass_))
    tone(FX.take_paths(root, pass_, shot, n)["wav"], wav_seconds - silent_first, silent_first=silent_first)
    FX.update(root, pass_, shot, n, status="ok")
    return n


@unittest.skipUnless(HAVE_FF, "ffmpeg/ffprobe not on PATH")
class LaidTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self._tmp.name, "ep01")
        episode(self.root, frames=(48, 48, 48))

    def tearDown(self):
        self._tmp.cleanup()

    def level(self, buf, a, b):
        np = MX._np()
        seg = buf[int(a * MX.RATE): int(b * MX.RATE)]
        return float(20 * np.log10(np.sqrt(np.mean(seg ** 2)) + 1e-9))

    def test_laid_at_the_clip_and_trimmed_with_it(self):
        # sh010's effects: silent for its first second, a tone in its second; the cut trims
        # 24 frames off sh010's head, so its clip plays the tone from the cut's frame 0
        n = finished(self.root, "sh010", 2.0, silent_first=1.0)
        finished(self.root, "sh020", 2.0)
        lay = [{"id": "sh010", "trim_in": 24, "used": 24, "dissolve_in": 0},
               {"id": "sh020", "trim_in": 0, "used": 48, "dissolve_in": 0},
               {"id": "sh030", "trim_in": 0, "used": 48, "dissolve_in": 0}]
        mix = {"fx": {"sh010": {"take": n}, "sh020": {"take": 1, "gain_db": -6}}}
        fx = FX.laid(self.root, "final", lay, mix)
        self.assertEqual([(f["shot"], f["origin"], f["start"], f["end"], f["in"], f["heard"]) for f in fx],
                         [("sh010", -24, 0, 24, {"shot": "sh010", "frame": 24}, True),
                          ("sh020", 24, 24, 72, {"shot": "sh020", "frame": 0}, True)])
        buf = FX.render_fx(fx, 120, 24.0, log=lambda *_: None)
        self.assertEqual(len(buf), 5 * MX.RATE)
        on = self.level(buf, 0.05, 0.95)
        self.assertGreater(on, -20)                                        # the tone, not the silence
        self.assertAlmostEqual(self.level(buf, 1.1, 2.9), on - 6, delta=0.5)
        self.assertLess(self.level(buf, 3.05, 5.0), -100)                  # sh030: nothing
        lanes = FX.fx_lanes(fx, lambda p: 48)
        self.assertEqual([(x["start"], x["end"], x["in"]) for x in lanes], [(0, 24, 24), (24, 72, 0)])

    def test_trimmed_faded_and_pointed(self):
        # sh010's effects: a steady tone over its 48-frame clip; the last 18 frames trimmed
        # (silent, the clip keeps its place and length), 12 at the head too, a point drops
        # the level 12 dB from frame 24 on
        n = finished(self.root, "sh010", 2.0)
        lay = [{"id": "sh010", "trim_in": 0, "used": 48, "dissolve_in": 0},
               {"id": "sh020", "trim_in": 0, "used": 48, "dissolve_in": 0}]
        pts = [{"at": {"shot": "sh010", "frame": 23}, "db": 0}, {"at": {"shot": "sh010", "frame": 24}, "db": -12}]
        mix = MX.check({"fx": {"sh010": {"take": n, "trim_in": 12, "trim_out": 18, "points": pts}}})
        fx = FX.laid(self.root, "final", lay, mix)
        self.assertEqual((fx[0]["start"], fx[0]["end"], fx[0]["trim_in"], fx[0]["trim_out"], fx[0]["points"]),
                         (0, 48, 12, 18, [(23, 0.0), (24, -12.0)]))
        self.assertEqual(FX.kept_span(fx[0]), (12, 30))
        buf = FX.render_fx(fx, 96, 24.0, log=lambda *_: None)
        self.assertLess(self.level(buf, 0.0, 0.49), -100)                    # trimmed head: silence
        on = self.level(buf, 0.55, 0.95)
        self.assertGreater(on, -20)
        self.assertAlmostEqual(self.level(buf, 1.02, 1.24), on - 12, delta=0.5)   # the point
        self.assertLess(self.level(buf, 1.26, 2.0), -100)                    # trimmed tail: silence
        # the XML: the clip trimmed to the kept span, its points there
        lanes = FX.fx_lanes(fx, lambda p: 48)
        self.assertEqual([(x["start"], x["end"], x["in"], x["points"]) for x in lanes],
                         [(12, 30, 12, [(23, 0.0), (24, -12.0)])])
        # fades at the kept span's edges: a fade out over its last 6 frames
        mix["fx"]["sh010"].update(fade_out=6, points=[])
        fx = FX.laid(self.root, "final", lay, MX.check(mix))
        buf = FX.render_fx(fx, 96, 24.0, log=lambda *_: None)
        self.assertLess(self.level(buf, 1.125, 1.25), on - 4)                # fading
        self.assertAlmostEqual(self.level(buf, 0.55, 0.95), on, delta=0.1)
        self.assertEqual(FX.fx_lanes(fx, lambda p: 48)[0]["fade_out"], 6)
        # trims that meet: nothing heard, nothing laid in the XML
        mix["fx"]["sh010"].update(trim_in=30, trim_out=18)
        fx = FX.laid(self.root, "final", lay, MX.check(mix))
        self.assertLess(self.level(FX.render_fx(fx, 96, 24.0), 0, 4), -100)
        self.assertEqual(FX.fx_lanes(fx, lambda p: 48), [])

    def test_stale_left_out_unless_kept(self):
        n = finished(self.root, "sh010", 2.0)
        FX.update(self.root, "final", "sh010", n, source={"pass": "final", "take": 7, "size": 1, "mtime": 0})
        lay = [{"id": "sh010", "trim_in": 0, "used": 48, "dissolve_in": 0}]
        fx = FX.laid(self.root, "final", lay, {"fx": {"sh010": {"take": n}}})
        self.assertEqual((fx[0]["stale"], fx[0]["heard"]), ("made from t07; the cut plays t01", False))
        self.assertLess(self.level(FX.render_fx(fx, 48, 24.0), 0, 2), -100)
        fx = FX.laid(self.root, "final", lay, {"fx": {"sh010": {"take": n, "keep_stale": True}}})
        self.assertTrue(fx[0]["heard"])
        self.assertGreater(self.level(FX.render_fx(fx, 48, 24.0), 0.1, 1.9), -20)
        fx = FX.laid(self.root, "final", lay, {"fx": {"sh010": {"take": n, "keep_stale": True, "mute": True}}})
        self.assertFalse(fx[0]["heard"])

    def test_pick(self):
        with self.assertRaises(FX.FxError):
            FX.pick(self.root, "final", "sh010", 1)                       # none finished
        n = finished(self.root, "sh010", 2.0)
        MX.write(self.root, "final", {"fx": {"sh010": {"take": n, "gain_db": -3, "keep_stale": True}}})
        n2 = finished(self.root, "sh010", 2.0)
        mix = FX.pick(self.root, "final", "sh010", n2)
        self.assertEqual(mix["fx"], {"sh010": {"take": n2, "gain_db": -3.0}})   # level kept, keep_stale not
        # the trims, fades and points are the user's, kept too
        pts = [{"at": {"shot": "sh010", "frame": 30}, "db": -6.0}]
        MX.write(self.root, "final", {"fx": {"sh010": {"take": n2, "trim_out": 20, "fade_out": 4,
                                                       "trim_in": 2, "fade_in": 3, "points": pts}}})
        self.assertEqual(FX.pick(self.root, "final", "sh010", n)["fx"],
                         {"sh010": {"take": n, "trim_in": 2, "trim_out": 20, "fade_in": 3, "fade_out": 4,
                                    "points": pts}})
        self.assertNotIn("fx", FX.pick(self.root, "final", "sh010", None))
        info = FX.shot_takes(self.root, "final", "sh010")
        self.assertEqual([t["take"] for t in info["takes"]], [n2, n])
        self.assertEqual((info["cut_take"], info["text_from"]), ({"pass": "final", "take": 1}, "sound"))

    def test_a_new_take_is_picked_and_listed(self):
        # made and asked for, a shot's effects are heard and shown: each new take is picked
        # (Make again means "this one"), its level and mute kept
        self.assertEqual(FX.shots(self.root, "final"), [])
        n = finished(self.root, "sh010", 2.0)
        self.assertTrue(FX.pick_new(self.root, "final", "sh010", n))
        FX.pick(self.root, "final", "sh010", n)
        mix = MX.load(self.root)["final"]
        mix["fx"]["sh010"]["gain_db"] = -4.0
        MX.write(self.root, "final", mix)
        n2 = finished(self.root, "sh010", 2.0)
        self.assertTrue(FX.pick_new(self.root, "final", "sh010", n2))
        self.assertEqual(MX.load(self.root)["final"]["fx"], {"sh010": {"take": n2, "gain_db": -4.0}})
        self.assertEqual(FX.shots(self.root, "final"),
                         [{"shot": "sh010", "takes": 2, "ok": 2, "queued": 0, "failed": 0, "picked": n2}])


class _Runner:
    """seriesmith's queue, stood in for: it remembers what it was asked."""

    def __init__(self):
        self.asked = []

    def enqueue_fx(self, root, pass_, shot, n, backend):
        self.asked.append((shot, n, backend))
        return f"job{shot}{n}"


class RouteTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.shows = os.path.join(self._tmp.name, "Shows")
        self.ep = os.path.join(self.shows, "ep01")
        os.makedirs(self.ep)
        episode(self.ep)
        self.ctx = A.Context(os.path.join(self._tmp.name, "user"), "http://127.0.0.1:0", env={},
                             runner=_Runner())
        self.call(A.put_config, {"roots": [self.shows]})

    def tearDown(self):
        self._tmp.cleanup()

    def call(self, fn, arg, status=200):
        code, data = fn(self.ctx, arg)
        self.assertEqual(code, status, data)
        return data

    def test_shots(self):
        self.assertEqual(self.call(A.get_fx_shots, {"ep": self.ep, "pass": "final"}), {"shots": []})
        self.call(A.post_fx_render, {"ep": self.ep, "pass": "final", "shots": ["sh010"]})
        got = self.call(A.get_fx_shots, {"ep": self.ep, "pass": "final"})["shots"]
        self.assertEqual([(s["shot"], s["takes"], s["queued"], s["picked"]) for s in got], [("sh010", 1, 1, None)])

    def test_render_list_pick(self):
        r = self.call(A.post_fx_render, {"ep": self.ep, "pass": "final", "shots": ["sh010", "sh020", "sh030"]})
        self.assertEqual([(q["shot"], q["take"], q["target"]) for q in r["queued"]],
                         [("sh010", 1, "h3_foley"), ("sh020", 1, "h3_foley")])
        self.assertEqual([x["shot"] for x in r["skipped"]], ["sh030"])
        self.assertEqual(self.ctx.runner.asked, [("sh010", 1, "local"), ("sh020", 1, "local")])
        r = self.call(A.post_fx_render, {"ep": self.ep, "pass": "final", "shots": ["sh010"],
                                         "target": "ltx23_foley", "n": 2})
        self.assertEqual([q["take"] for q in r["queued"]], [2, 3])
        self.assertEqual(len({q["seed"] for q in r["queued"]}), 2)
        self.call(A.post_fx_render, {"ep": self.ep, "pass": "final", "shots": ["sh030"]}, 400)
        self.call(A.post_fx_render, {"ep": self.ep, "pass": "final", "shots": ["sh010"], "target": "krea2"}, 400)
        self.call(A.post_fx_render, {"ep": self.ep, "pass": "final", "shots": []}, 400)
        got = self.call(A.get_fx, {"ep": self.ep, "pass": "final", "shot": "sh010"})
        self.assertEqual([(t["take"], t["status"], t["target"]) for t in got["takes"]],
                         [(3, "queued", "ltx23_foley"), (2, "queued", "ltx23_foley"), (1, "queued", "h3_foley")])
        self.assertEqual(got["text"], CLAPS)
        self.assertIn("no finished effects take", self.call(
            A.post_fx_pick, {"ep": self.ep, "pass": "final", "shot": "sh010", "take": 1}, 409)["error"])
        FX.update(self.ep, "final", "sh010", 1, status="ok")
        mix = self.call(A.post_fx_pick, {"ep": self.ep, "pass": "final", "shot": "sh010", "take": 1})["mix"]
        self.assertEqual(mix["fx"], {"sh010": {"take": 1}})
        got = self.call(A.get_mix, {"ep": self.ep, "pass": "final"})
        f = got["fx"][0]
        self.assertEqual((f["shot"], f["take"], f["model"], f["path"], f["start"], f["end"], f["offset"], f["stale"]),
                         ("sh010", 1, "h3_foley", "sound/fx/final/sh010/t01.wav", 0.0, 5.0, 0.0, None))
        self.assertFalse(f["exists"])                                       # no wav written here
        self.call(A.get_fx, {"ep": self.ep, "pass": "final"}, 400)


@unittest.skipUnless(HAVE_FF, "ffmpeg/ffprobe not on PATH")
class AssembleFxTest(unittest.TestCase):
    """Two one-second clips: sh010's picked effects a tone, sh020 none. No mix.json item: the
    effects alone make the mix."""

    def setUp(self):
        from test_phase9d import make_clip, probe_frames
        self._tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self._tmp.name, "ep01")
        mute = os.path.join(self._tmp.name, "mute.mp4")
        make_clip(mute, 24)
        T.write_json(os.path.join(self.root, "shotlist", "shotlist.json"),
                     {"episode": "ep01", "defaults": {"width": 64, "height": 64},
                      "shots": [{"id": "sh010", "length": 24, "audio_policy": "keep"},
                                {"id": "sh020", "length": 24, "audio_policy": "keep"}]})
        T.write_json(os.path.join(self.root, "shotlist", "shots.json"), {"episode": "ep01", "sequences": [
            {"id": "sq01", "location": "road", "shots": [{"id": "sh010", "sound": CLAPS},
                                                         {"id": "sh020", "action": "A car passes."}]}]})
        for shot in ("sh010", "sh020"):
            t = T.reserve_take(self.root, "final", shot, {"status": "queued"})
            shutil.copy(mute, t.paths.mp4)
            T.update_sidecar(t.paths.sidecar, status="ok", frames=probe_frames(mute), fps=24)
        self.n = finished(self.root, "sh010", 1.0)
        MX.save(self.root, {"final": {"fx": {"sh010": {"take": self.n}}}})

    def tearDown(self):
        self._tmp.cleanup()

    def assemble(self, *args):
        r = subprocess.run([sys.executable, "-m", "seriesmith.assemble", "-o", self.root, *args],
                           capture_output=True, text=True, encoding="utf-8", timeout=600)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout

    def test_effects_under_their_shot_only(self):
        out = self.assemble()
        self.assertIn("effects under 1 shot(s)", out)
        stems = os.path.join(self.root, "renders", "ep01_stems")
        np = MX._np()
        for name in ("effects", "me"):
            buf = MX.decode(os.path.join(stems, f"{name}.wav"))
            on = buf[int(0.05 * MX.RATE): int(0.95 * MX.RATE)]
            off = buf[int(1.05 * MX.RATE): int(1.95 * MX.RATE)]
            self.assertGreater(float(np.sqrt(np.mean(on ** 2))), 0.01, name)
            self.assertEqual(float(np.abs(off).max()), 0.0, name)

    def test_trimmed_effects_stem(self):
        # sh010's effects trimmed: its last 12 frames silent in the effects stem, the rest heard
        MX.save(self.root, {"final": {"fx": {"sh010": {"take": self.n, "trim_out": 12, "fade_out": 2}}}})
        self.assemble()
        np = MX._np()
        buf = MX.decode(os.path.join(self.root, "renders", "ep01_stems", "effects.wav"))
        self.assertGreater(float(np.sqrt(np.mean(buf[int(0.05 * MX.RATE): int(0.4 * MX.RATE)] ** 2))), 0.01)
        self.assertEqual(float(np.abs(buf[int(0.5 * MX.RATE):]).max()), 0.0)

    def test_stale_is_no_mix(self):
        FX.update(self.root, "final", "sh010", self.n, source={"pass": "final", "take": 9})
        out = self.assemble()
        self.assertIn("stale (made from t09; the cut plays t01)", out)
        self.assertFalse(os.path.isdir(os.path.join(self.root, "renders", "ep01_stems")))

    def test_xml_lane(self):
        self.assemble("--xml")
        xml = open(os.path.join(self.root, "renders", "ep01.xml"), encoding="utf-8").read()
        self.assertIn("t01.wav", xml)


if __name__ == "__main__":
    unittest.main()
