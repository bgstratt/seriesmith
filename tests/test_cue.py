"""
cue.py (docs/SOUND.md "Music: a cue is written to its hits"): a cue's spec, its plan against
a tiny episode's cut and mix, the graphs both music targets get, a synthetic take measured
(stretched to the tempo, its downbeat, hits and shape), the gain fit, a take placed in the
mix, and the routes (with a stand-in for the queue).
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from seriesmith import api as A  # noqa: E402
from seriesmith import cue as CU  # noqa: E402
from seriesmith import mix as MX  # noqa: E402
from seriesmith import takes as T  # noqa: E402
from seriesmith import targets as TG  # noqa: E402
from seriesmith import ff as FF  # noqa: E402
from seriesmith.core import fileio as F  # noqa: E402

HAVE_FF = bool(FF.have("ffmpeg") and FF.have("ffprobe"))
FPS = 24


def anchor(shot: str, frame: int = 0) -> dict:
    return {"shot": shot, "frame": frame}


def episode(root: str, frames=(120, 120, 120)) -> None:
    """Three shots of 5 s each, each with a finished take of that many frames (no file:
    the plan reads the sidecar's count)."""
    ids = [f"sh{10 * (i + 1):03d}" for i in range(len(frames))]
    T.write_json(os.path.join(root, "shotlist", "shotlist.json"),
                 {"episode": "ep01", "defaults": {"width": 64, "height": 64, "fps": FPS},
                  "shots": [{"id": s, "length": n, "audio_policy": "generate"}
                            for s, n in zip(ids, frames)]})
    for s, n in zip(ids, frames):
        t = T.reserve_take(root, "final", s, {"status": "queued"})
        open(t.paths.mp4, "wb").close()
        T.update_sidecar(t.paths.sidecar, status="ok", frames=n)


class SpecTest(unittest.TestCase):
    def spec(self, **kw):
        return {"id": "m01", "in": anchor("sh010"), "out": anchor("sh030", 100), **kw}

    def test_round_trip_drops_defaults(self):
        got = CU.check_spec(self.spec(meter=4, tail=2.0, fixed_tempo=False, style="  dark,  slow "))
        self.assertEqual(got, {"id": "m01", "in": anchor("sh010"), "out": anchor("sh030", 100),
                               "style": "dark, slow"})

    def test_refusals(self):
        for bad in (self.spec(model="krea2"), self.spec(model="nope"), self.spec(bpm=400),
                    self.spec(meter="7/3"), self.spec(meter=17), self.spec(meter="swing"), self.spec(sections=[{"name": "a", "from": 9}]),
                    self.spec(arc=[{"at": anchor("sh010"), "level": 0}]), self.spec(takes=40),
                    self.spec(colour=1), {"id": "x y", "in": anchor("a"), "out": anchor("b")}):
            with self.subTest(bad=bad), self.assertRaises(CU.CueError):
                CU.check_spec(bad)

    def test_kind(self):
        self.assertNotIn("kind", CU.check_spec(self.spec(kind="score")))       # the default
        self.assertEqual(CU.check_spec(self.spec(kind="song"))["kind"], "song")
        with self.assertRaises(CU.CueError):
            CU.check_spec(self.spec(kind="jingle"))
        with self.assertRaisesRegex(CU.CueError, "sings no lyrics"):
            CU.check_spec(self.spec(kind="song", model="stable_audio3"))
        self.assertEqual(CU.model_for(CU.check_spec(self.spec()), {}), "stable_audio3")
        self.assertEqual(CU.model_for(CU.check_spec(self.spec(kind="song")), {}), "ace_step15")
        self.assertEqual(CU.model_for(CU.check_spec(self.spec()), {"sound": {"music_model": "ace_step15"}}),
                         "ace_step15")

    def test_meters(self):
        self.assertNotIn("meter", CU.check_spec(self.spec(meter=4)))           # 4/4: the default
        self.assertEqual(CU.check_spec(self.spec(meter=3))["meter"], "3/4")   # a bare number of beats
        self.assertEqual(CU.check_spec(self.spec(meter=" 7 / 8 "))["meter"], "7/8")
        self.assertEqual(CU.parse_meter("12/8"), (12, 8))

    def test_model_must_be_music(self):
        self.assertEqual(CU.check_spec(self.spec(model="ace_step15"))["model"], "ace_step15")


class PlanTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        episode(self.root)
        MX.save(self.root, {"final": {"hits": [
            {"id": "h1", "name": "door", "at": anchor("sh020", 12), "kind": "accent"},
            {"id": "h2", "name": "reveal", "at": anchor("sh030", 24), "kind": "arrive"},
            {"id": "h3", "name": "silence", "at": anchor("sh030", 84), "kind": "drop",
             "must": False}]}})

    def tearDown(self):
        self._tmp.cleanup()

    def spec(self, **kw):
        return CU.check_spec({"id": "m01", "in": anchor("sh010"), "out": anchor("sh030", 120),
                              "bpm": 92, "key": "D minor", **kw})

    def test_layout_follows_the_cut(self):
        layout, fps = CU.cut_layout(self.root, "final")
        self.assertEqual(fps, FPS)
        self.assertEqual([(x["id"], x["used"]) for x in layout],
                         [("sh010", 120), ("sh020", 120), ("sh030", 120)])
        T.save_cut(self.root, {"final": [{"shot": "sh020", "trim_in": 24}, {"shot": "sh010"},
                                         {"shot": "sh030", "out": True}], "proxy": []})
        layout, _ = CU.cut_layout(self.root, "final")
        self.assertEqual([(x["id"], x["trim_in"], x["used"]) for x in layout],
                         [("sh020", 24, 96), ("sh010", 0, 120)])

    def test_plan_lands_the_hits(self):
        p = CU.plan(self.root, "final", self.spec(), {})
        self.assertEqual(p["target"], "stable_audio3")
        self.assertEqual([h["t"] for h in p["hits"]], [5.5, 11.0, 13.5])
        self.assertTrue(84 <= p["fit"]["bpm"] <= 100)
        self.assertLess(p["fit"]["worst_must"], 0.5)                # the must-hits on bar lines
        bar = p["bar"]
        for h in p["hits"][:2]:
            # an arrival on a bar line, an accent (the door) on a beat
            unit = bar / 4 if h["kind"] == "accent" else bar
            pos = (h["t"] + p["preroll"]) / unit
            self.assertAlmostEqual(pos, round(pos), delta=0.5 / FPS / unit)
        # whole bars, from the pre-roll through the out point and the tail
        self.assertAlmostEqual(p["seconds"], p["bars"] * bar, places=2)
        self.assertGreaterEqual(p["seconds"], p["preroll"] + 15.0 + 2.0)
        self.assertEqual(sum(s["bars"] for s in p["sections"]), p["bars"])
        self.assertEqual(len(p["arc"]), p["bars"])
        # sections from the hits: a build into the arrival, a climax, a drop
        self.assertEqual([s["name"] for s in p["sections"]], ["build", "climax", "drop"])
        build = p["sections"][0]["bars"]
        self.assertLess(p["arc"][0], p["arc"][build - 1])            # rising through the build
        self.assertLess(p["arc"][-1], p["arc"][build])               # quiet after the drop
        self.assertIn("crescendo", p["prompt"]["prompt"])
        self.assertIn(f"{p['fit']['ask_bpm']} BPM", p["prompt"]["prompt"])
        self.assertAlmostEqual(p["ask_seconds"], p["seconds"] * p["fit"]["stretch"], places=2)

    def test_plan_offers_other_tempos(self):
        p = CU.plan(self.root, "final", self.spec(), {})
        self.assertEqual(p["hits"][0]["at"], anchor("sh020", 12))      # each hit's anchor
        alts = p["alternatives"]
        self.assertEqual(len(alts), CU.ALTERNATIVES)
        self.assertEqual((alts[0]["bpm"], alts[0]["worst_must"]), (p["fit"]["bpm"], p["fit"]["worst_must"]))
        for a in alts:
            self.assertTrue(92 * 0.92 - 1e-6 <= a["bpm"] <= 92 * 1.08 + 1e-6)
            self.assertEqual(set(a), {"bpm", "preroll", "worst_must", "total"})
        # a fixed tempo is kept, and the others near it still offered
        fixed = CU.plan(self.root, "final", self.spec(fixed_tempo=True), {})
        self.assertEqual(fixed["fit"]["bpm"], 92)
        self.assertEqual([a["bpm"] for a in fixed["alternatives"]], [a["bpm"] for a in alts])

    def test_fixed_tempo_and_given_sections(self):
        p = CU.plan(self.root, "final", self.spec(
            fixed_tempo=True, model="ace_step15",
            sections=[{"name": "intro", "bars": 2, "words": "solo horn", "from": 1},
                      {"name": "build", "words": "strings", "from": 2, "to": 5}]), {})
        self.assertEqual(p["fit"]["bpm"], 92)
        self.assertEqual(p["sections"][0]["bars"], 2)
        self.assertEqual(p["sections"][1]["bars"], p["bars"] - 2)
        v = p["prompt"]["values"]
        self.assertEqual(v["bpm"], 92)
        self.assertEqual(v["keyscale"], "D minor")
        self.assertEqual(v["lyrics"].count("(solo horn"), 2)        # a line per bar

    def test_script_notes_in_the_prompt(self):
        from seriesmith.core import ir
        story = ir.Episode(id="ep01", sequences=[ir.Sequence(id="sq01", location="hall", shots=[
            ir.Shot(id="sh010", music="tension rises as he kneels"),
            ir.Shot(id="sh020"),
            ir.Shot(id="sh030", music="swells, full, on her face"),
            ir.Shot(id="sh040", music="not under the cue")])])
        F.write_text(os.path.join(self.root, "shotlist", "shots.json"), story.dumps())
        p = CU.plan(self.root, "final", self.spec(), {})
        self.assertEqual([n["shot"] for n in p["notes"]], ["sh010", "sh030"])
        self.assertIn("Mood: tension rises as he kneels; swells, full, on her face.",
                      p["prompt"]["prompt"])
        pa = CU.plan(self.root, "final", self.spec(model="ace_step15"), {})
        self.assertTrue(pa["prompt"]["prompt"].endswith("tension rises as he kneels; swells, full, on her face"))

    def test_a_song_sings(self):
        p = CU.plan(self.root, "final", self.spec(kind="song", sections=[
            {"name": "verse", "bars": 4, "lyrics": "Under the rain\nwe run"},
            {"name": "chorus", "words": "full band"}]), {})
        self.assertEqual(p["target"], "ace_step15")
        self.assertNotIn("instrumental", p["prompt"]["prompt"])
        self.assertIn("[Verse]\nUnder the rain\nwe run", p["prompt"]["values"]["lyrics"])
        self.assertIn("instrumental", CU.plan(self.root, "final", self.spec(), {})["prompt"]["prompt"])

    def test_a_drop_on_the_out_point_is_the_end(self):
        # the drop (sh030 frame 84) is where the cue stops: not fitted, nothing to measure
        p = CU.plan(self.root, "final", self.spec(out=anchor("sh030", 84)), {})
        ends = [h for h in p["hits"] if h.get("ends")]
        self.assertEqual([h["id"] for h in ends], ["h3"])
        self.assertIsNone(p["fit"]["errors"][2])
        self.assertEqual(len(p["fit"]["errors"]), 3)

    def test_orchestra_in_the_words(self):
        spec = self.spec(sections=[{"name": "intro", "bars": 2, "words": "quiet"}, {"name": "rest"}],
                         orchestra={"strings": [1, 1, 3, 3, 3, 3, 3, 3, 3], "solo horn": [2, 2],
                                    "timpani": [0, 0, 0, 1], "choir": [0, 0]})
        self.assertNotIn("choir", spec["orchestra"])                  # off throughout: dropped
        p = CU.plan(self.root, "final", spec, {})
        self.assertEqual(p["sections"][0]["words"], "quiet, solo horn present, strings under")
        self.assertEqual(p["sections"][1]["words"], "strings lead, timpani under")
        with self.assertRaises(CU.CueError):
            CU.check_spec(self.spec(orchestra={"brass": [4]}))

    def test_a_drawn_arc_sets_the_sections_energies(self):
        # the sections say 3 throughout; the arc rises from 1 to 5 over the cue
        p0 = CU.plan(self.root, "final", self.spec(sections=[{"name": "a", "bars": 2, "from": 3},
                                                             {"name": "b", "from": 3}]), {})
        spec = self.spec(sections=[{"name": "a", "bars": 2, "from": 3}, {"name": "b", "from": 3}],
                         arc=[{"at": anchor("sh010"), "level": 1}, {"at": anchor("sh030", 120), "level": 5}])
        p = CU.plan(self.root, "final", spec, {})
        self.assertLess(p["sections"][0]["from"], 2)
        self.assertGreater(p["sections"][1]["to"], 4)
        self.assertNotEqual(p["prompt"]["prompt"], p0["prompt"]["prompt"])   # the words follow

    def test_an_odd_meter(self):
        p = CU.plan(self.root, "final", self.spec(meter="7/8"), {})
        self.assertAlmostEqual(p["bar"], 7 * 60 / p["fit"]["bpm"], places=3)   # seven beats a bar
        self.assertIn("7/8", p["prompt"]["prompt"])                            # Stable Audio hears it
        pa = CU.plan(self.root, "final", self.spec(meter="7/8", model="ace_step15"), {})
        self.assertEqual(pa["prompt"]["values"]["timesignature"], "6")        # ACE-Step's nearest
        self.assertIn("7/8", pa["prompt"]["prompt"])                           # and in its tags

    def test_anchor_not_in_the_cut(self):
        with self.assertRaises(CU.CueError):
            CU.plan(self.root, "final", CU.check_spec(
                {"id": "m01", "in": anchor("sh999"), "out": anchor("sh030")}), {})

    def test_graphs(self):
        p = CU.plan(self.root, "final", self.spec(), {})
        g = CU.graph(TG.load_target("stable_audio3"), p, 7, "final")
        by = {v["class_type"]: v["inputs"] for v in g.values()}
        self.assertEqual(by["EmptyLatentAudio"]["seconds"], round(p["ask_seconds"], 3))
        self.assertEqual(by["KSampler"]["seed"], 7)
        self.assertIn("SaveAudio", by)
        texts = sorted(v["inputs"]["text"] for v in g.values() if v["class_type"] == "CLIPTextEncode")
        self.assertIn(p["prompt"]["prompt"], texts)
        pa = CU.plan(self.root, "final", self.spec(model="ace_step15"), {})
        g = CU.graph(TG.load_target("ace_step15"), pa, 9, "proxy")
        by = {v["class_type"]: v["inputs"] for v in g.values()}
        enc = by["TextEncodeAceStepAudio1.5"]
        self.assertEqual((enc["seed"], by["KSampler"]["seed"]), (9, 9))
        self.assertEqual(enc["bpm"], pa["fit"]["ask_bpm"])
        self.assertEqual(enc["duration"], by["EmptyAceStep1.5LatentAudio"]["seconds"])
        self.assertEqual(by["UNETLoader"]["unet_name"], "acestep_v1.5_xl_turbo_bf16.safetensors")
        self.assertEqual(by["KSampler"]["steps"], 8)

    def test_seeds_differ_and_follow_on(self):
        spec = self.spec()
        a = CU.seeds(self.root, spec, 3, 0)
        self.assertEqual(len(set(a)), 3)
        self.assertEqual(CU.seeds(self.root, spec, 2, 1), a[1:3])
        self.assertEqual(CU.seeds(self.root, self.spec(seed=100), 2, 3), [103, 104])


class GainFitTest(unittest.TestCase):
    def test_pulls_toward_the_arc(self):
        levels = [-20, -20, -20, -20]
        # a flat take: the arc mapped onto at least 6 dB, 2 dB a level here
        self.assertEqual(CU.fit_gain(levels, [1, 2, 3, 4]), [-3.0, -1.0, 1.0, 3.0])

    def test_bounded_and_silence_left(self):
        got = CU.fit_gain([-30, -10, -120, -20], [5, 1, 3, 3])
        self.assertTrue(all(abs(x) <= CU.GAIN_FIT_DB for x in got))
        self.assertEqual(got[2], 0.0)
        self.assertEqual(CU.fit_gain([-20, -10], [3, 3]), [0.0, 0.0])


@unittest.skipUnless(HAVE_FF, "ffmpeg/ffprobe not on PATH")
class TakeTest(PlanTest):
    """A synthetic take: clicks at the asked tempo (a little slow, as a model plays),
    louder in the middle, with half a second of lead-in, measured and placed."""

    def make_take(self, p: dict, lead: float = 0.5, slow: float = 0.98) -> str:
        sys.path.insert(0, HERE)
        from test_beats import clicks
        bars = p["bars"]
        levels = [0.1 + 0.8 * a / 5 for a in p["arc"]]
        buf = clicks(p["fit"]["ask_bpm"] * slow, bars, offset=lead, levels=levels)
        path = os.path.join(self.root, "raw.wav")
        MX.write_wav(path, buf)
        return path

    def test_measure_and_place(self):
        spec = CU.save_spec(self.root, self.spec())
        p = CU.plan(self.root, "final", spec, {})
        n = CU.reserve(self.root, "m01", {"pass": "final"})
        sc = CU.finish_take(self.root, "m01", n, self.make_take(p), p)
        m = sc["measured"]
        self.assertEqual(sc["status"], "ok")
        self.assertTrue(m["tempo_heard"])
        self.assertAlmostEqual(m["stretch"], p["fit"]["bpm"] / (p["fit"]["ask_bpm"] * 0.98), delta=0.01)
        # the lead-in, stretched, is where its first bar line is
        self.assertAlmostEqual(m["downbeat"], 0.5 / m["stretch"], delta=1.5 / FPS)
        self.assertAlmostEqual(m["offset"], m["downbeat"] + p["preroll"], places=3)
        self.assertLess(m["shape_error"], 0.15)
        self.assertEqual(len(m["hit_errors"]), 3)
        self.assertTrue(os.path.isfile(os.path.join(self.root, "sound", "m01", "t01.wav")))
        self.assertTrue(os.path.isfile(os.path.join(self.root, "sound", "m01", "t01_raw.wav")))
        self.assertEqual(CU.ranked(CU.list_takes(self.root, "m01"))[0]["take"], 1)

        # measured again against the same plan: the same numbers, no render
        again = CU.remeasure(self.root, "m01", n, p)["measured"]
        self.assertEqual(again["offset"], m["offset"])
        self.assertEqual(again["levels"], m["levels"])

        # a comp: take 1 with bars 3-5 from a second take, louder there (its clicks are)
        p2 = dict(p, arc=[5.0] * p["bars"])
        n2 = CU.reserve(self.root, "m01", {"pass": "final"})
        CU.finish_take(self.root, "m01", n2, self.make_take(p2, lead=0.3), p)
        sc = CU.comp(self.root, "final", "m01", n, n2, (3, 5))
        self.assertEqual(sc["comp"], {"base": n, "from": n2, "bars": [3, 5]})
        self.assertEqual(sc["status"], "ok")
        lv, base_lv, src_lv = sc["measured"]["levels"], m["levels"], CU.list_takes(self.root, "m01")[1]["measured"]["levels"]
        self.assertAlmostEqual(lv[1], base_lv[1], delta=1.0)               # its own bars kept
        self.assertAlmostEqual(lv[4], src_lv[4], delta=1.0)                # bars 3-5 the other's
        with self.assertRaises(CU.CueError):
            CU.comp(self.root, "final", "m01", n, n2, (0, p["bars"] + 3))

        mix = CU.place(self.root, "final", "m01", n)
        item = next(i for i in mix["items"] if i["id"] == "m01")
        self.assertEqual(item["track"], "music")
        self.assertEqual(item["path"], "sound/m01/t01.wav")
        self.assertAlmostEqual(item["offset"], m["offset"], places=2)
        self.assertEqual(item["in"], spec["in"])
        self.assertEqual(MX.check(mix), mix)                     # a mix the mix accepts
        # placing again replaces the item, it doesn't add one
        mix = CU.place(self.root, "final", "m01", n, gain=False)
        self.assertEqual([i["id"] for i in mix["items"]].count("m01"), 1)
        self.assertNotIn("points", next(i for i in mix["items"] if i["id"] == "m01"))
        self.assertEqual(CU.list_takes(self.root, "m01")[0]["placed"], "final")


class _Runner:
    """seriesmith's queue, stood in for: it remembers what it was asked."""

    def __init__(self):
        self.asked = []

    def enqueue_cue(self, root, cid, n, graph, p, backend):
        self.asked.append((cid, n, graph, backend))
        return f"job{n}"


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

    def test_put_get_render(self):
        spec = {"id": "m01", "in": anchor("sh010"), "out": anchor("sh020", 60), "bpm": 92}
        self.assertIn("unknown cue field", self.call(A.put_cue, {"ep": self.ep, "cue": {**spec, "x": 1}}, 400)["error"])
        self.call(A.put_cue, {"ep": self.ep, "cue": spec})
        got = self.call(A.get_cue, {"ep": self.ep, "pass": "final", "cue": "m01"})
        self.assertEqual(got["spec"]["bpm"], 92)
        self.assertIsNone(got["plan_error"])
        self.assertIn("prompt", got["plan"])
        self.assertEqual(got["plan"]["notes"], [])                 # the script's music: notes
        r = self.call(A.post_cue_render, {"ep": self.ep, "pass": "final", "cue": "m01", "takes": 3})
        self.assertEqual([q["take"] for q in r["queued"]], [1, 2, 3])
        self.assertEqual(len(self.ctx.runner.asked), 3)
        self.assertEqual(len({q["seed"] for q in r["queued"]}), 3)
        listing = self.call(A.get_cues, {"ep": self.ep})["cues"]
        self.assertEqual((listing[0]["spec"]["id"], listing[0]["takes"], listing[0]["ok"]), ("m01", 3, 0))
        self.call(A.get_cue, {"ep": self.ep, "pass": "final", "cue": "nope"}, 404)
        self.assertIn("no finished take", self.call(
            A.post_cue_pick, {"ep": self.ep, "pass": "final", "cue": "m01", "take": 1}, 409)["error"])

    def test_stale_when_the_cut_moves(self):
        MX.save(self.ep, {"final": {"hits": [{"id": "h1", "name": "door", "at": anchor("sh020", 12)}]}})
        self.call(A.put_cue, {"ep": self.ep, "cue": {"id": "m01", "in": anchor("sh010"),
                                                     "out": anchor("sh020", 60), "bpm": 92}})
        self.call(A.post_cue_render, {"ep": self.ep, "pass": "final", "cue": "m01", "takes": 1})
        got = self.call(A.get_cue, {"ep": self.ep, "pass": "final", "cue": "m01"})
        self.assertEqual(got["takes"][0]["stale"], [])
        # sh010 trimmed by 24 frames at its tail: the span shorter, the door a second earlier
        T.save_cut(self.ep, {"final": [{"shot": "sh010", "trim_out": 24}, {"shot": "sh020"},
                                       {"shot": "sh030"}], "proxy": []})
        why = self.call(A.get_cue, {"ep": self.ep, "pass": "final", "cue": "m01"})["takes"][0]["stale"]
        self.assertIn("door moved -24 frames", why)
        self.assertTrue(any("1.0 s shorter" in w for w in why), why)

    def test_cues_listed_against_a_pass(self):
        MX.save(self.ep, {"final": {"hits": [{"id": "h1", "name": "door", "at": anchor("sh020", 12)}]}})
        self.call(A.put_cue, {"ep": self.ep, "cue": {"id": "m01", "in": anchor("sh010"),
                                                     "out": anchor("sh020", 60), "bpm": 92}})
        self.call(A.put_cue, {"ep": self.ep, "cue": {"id": "m02", "in": anchor("sh090"),
                                                     "out": anchor("sh090", 60)}})
        self.call(A.post_cue_render, {"ep": self.ep, "pass": "final", "cue": "m01", "takes": 2})
        for n in (1, 2):
            CU.update(self.ep, "m01", n, status="ok")
        # take 2 is the one in the mix
        mix = MX.check(MX.load(self.ep)["final"])
        mix["items"] = [{"id": "m01", "track": "music", "path": "sound/m01/t02.wav",
                         "in": anchor("sh010"), "out": anchor("sh020", 60)}]
        MX.save(self.ep, {"final": mix})
        plain = self.call(A.get_cues, {"ep": self.ep})["cues"]
        self.assertNotIn("stale", plain[0])                            # no pass: not planned
        rows = {c["spec"]["id"]: c for c in self.call(A.get_cues, {"ep": self.ep, "pass": "final"})["cues"]}
        self.assertEqual((rows["m01"]["in_mix"], rows["m01"]["stale"], rows["m01"]["stale_takes"]), (2, [], []))
        self.assertIsInstance(rows["m01"]["bpm"], float)
        self.assertIn("sh090", rows["m02"]["plan_error"])
        self.assertEqual(rows["m02"]["stale"], [])
        T.save_cut(self.ep, {"final": [{"shot": "sh010", "trim_out": 24}, {"shot": "sh020"},
                                       {"shot": "sh030"}], "proxy": []})
        m01 = self.call(A.get_cues, {"ep": self.ep, "pass": "final"})["cues"][0]
        self.assertEqual(m01["stale_takes"], [1, 2])
        self.assertIn("door moved -24 frames", m01["stale"])
        self.call(A.get_cues, {"ep": self.ep, "pass": "draft"}, 400)


if __name__ == "__main__":
    unittest.main()
