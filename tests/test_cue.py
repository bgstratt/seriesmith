"""
cue.py (docs/SOUND.md "Music: a cue is written to its hits"): a cue's spec, its plan against
a tiny episode's cut and mix, the graphs both music targets get, a synthetic take measured
(stretched to the tempo, its downbeat, hits and shape), the gain fit, a take placed in the
mix, and the routes (with a stand-in for the queue).
"""
from __future__ import annotations

import json
import math
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
        self.assertEqual(CU.model_for(CU.check_spec(self.spec(kind="song")), {}), "yue2")
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

    def test_why_a_cue_cant_be_planned(self):
        # a fourth shot in the script with no take yet
        doc = T.read_json(os.path.join(self.root, "shotlist", "shotlist.json"))
        doc["shots"].append({"id": "sh040", "length": 120, "audio_policy": "generate"})
        T.write_json(os.path.join(self.root, "shotlist", "shotlist.json"), doc)
        spec = CU.check_spec({"id": "m09", "in": anchor("sh020"), "out": anchor("sh040", 60)})
        with self.assertRaises(CU.CueError) as e:
            CU.plan(self.root, "final", spec, {})
        self.assertIn("sh040 has no final take yet: a cue is timed to the rendered shots it plays over", str(e.exception))
        # one left out of the cut
        T.save_cut(self.root, {"final": [{"shot": "sh010"}, {"shot": "sh020", "out": True}, {"shot": "sh030"}], "proxy": []})
        spec = CU.check_spec({"id": "m09", "in": anchor("sh020"), "out": anchor("sh030", 60)})
        with self.assertRaises(CU.CueError) as e:
            CU.plan(self.root, "final", spec, {})
        self.assertIn("sh020 is left out of the final cut: put it back, or move the cue's in", str(e.exception))

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
        self.assertEqual(p["direction"], "")
        self.assertEqual(CU.plan(self.root, "final", self.spec(), {"sound": {"score": "sparse strings."}})["direction"],
                         "sparse strings.")
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
        self.assertEqual(p["target"], "yue2")                       # a song's default sings
        self.assertNotIn("instrumental", p["prompt"]["prompt"])
        # YuE2: the sections with lyrics, each under its tag
        self.assertEqual(p["prompt"]["values"]["lyrics"], "[Verse]\nUnder the rain\nwe run")
        p = CU.plan(self.root, "final", self.spec(kind="song", model="ace_step15", sections=[
            {"name": "verse", "bars": 4, "lyrics": "Under the rain\nwe run"},
            {"name": "chorus", "words": "full band"}]), {})
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
        pm = CU.plan(self.root, "final", self.spec(model="minimax_music3"), {})
        g = CU.graph(TG.load_target("minimax_music3"), pm, 11, "final")
        by = {v["class_type"]: v["inputs"] for v in g.values()}
        enc = by["MiniMaxMusic3TextEncode"]
        self.assertEqual((enc["seed"], by["KSampler"]["seed"]), (11, 11))
        self.assertEqual(enc["max_duration"], round(pm["ask_seconds"], 3))
        # score: the sections as its tags only, and no voice in the caption
        self.assertEqual(enc["lyrics"].splitlines(), [f"[{s['name'].lower()}]" for s in pm["sections"]])
        self.assertIn("Vocal Details: None.", enc["caption"])
        self.assertIn(f"{int(pm['fit']['ask_bpm'])} BPM", enc["caption"])
        # on Comfy Cloud: the partner node, marked so the backend sends the key; a score
        # cue's lyrics empty (the hosted model's instrumental switch)
        pc = CU.plan(self.root, "final", self.spec(model="minimax_music3_cloud"), {})
        g = CU.graph(TG.load_target("minimax_music3_cloud"), pc, 11, "final")
        node = next(v for v in g.values() if v["class_type"] == "ComfyCloudMiniMaxMusic3TextToAudioNode")
        self.assertTrue(node["_meta"]["partner"])
        self.assertEqual((node["inputs"]["seed"], node["inputs"]["lyrics"]), (11, ""))
        self.assertEqual(node["inputs"]["prompt"], enc["caption"])
        # Magenta RealTime 2: the arc as a style a bar, the frames the cue's length
        pr = CU.plan(self.root, "final", self.spec(model="mrt2"), {})
        g = CU.graph(TG.load_target("mrt2"), pr, 13, "proxy")
        node = next(v["inputs"] for v in g.values() if v["class_type"] == "SeriesmithMRT2")
        segs = json.loads(node["schedule"])["segments"]
        self.assertEqual((node["seed"], node["model"]), (13, "magenta-realtime-2-small"))
        self.assertEqual(len(segs), pr["bars"])
        self.assertEqual(sum(s["frames"] for s in segs), round(pr["ask_seconds"] * 25))
        # quiet bars have drums off; the rest leave them to the model
        self.assertTrue(all(s.get("drums", 0) == 0 for s in segs))
        # Pika Music on Router: one call, the brief at the fields its router block names
        pk = CU.plan(self.root, "final", self.spec(model="pika_music"), {})
        model, args = CU.hosted_call(TG.load_target("pika_music"), pk, 2 ** 40 + 3)
        self.assertEqual(model, "pika/pika-music")
        self.assertEqual(args["mode"], "text_to_music")
        self.assertEqual(args["prompt"], pk["prompt"]["prompt"])
        self.assertNotIn("lyrics", args)                  # score: none sent
        self.assertEqual(args["duration"], max(10, math.ceil(pk["ask_seconds"])))
        self.assertLessEqual(args["seed"], 2147483647)

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


class RepaintTest(TakeTest):
    """Bars of a take made again (cue.repaint, docs/SOUND.md "Measured: repaint"): where the
    bars fall in the take's own file, the graph, and the take's audio spliced back outside
    them when the job's audio comes back."""

    def ace_take(self, seed: int = 5) -> tuple[dict, int]:
        spec = CU.save_spec(self.root, self.spec(model="ace_step15"))
        p = CU.plan(self.root, "final", spec, {})
        n = CU.reserve(self.root, "m01", {"pass": "final", "target": "ace_step15", "seed": seed,
                                          "prompt": p["prompt"], "rendered_for": CU.fingerprint(p),
                                          "plan": {"fit": p["fit"]}})
        CU.finish_take(self.root, "m01", n, self.make_take(p), p)
        return p, n

    def test_span_codes_and_graph(self):
        sc = {"measured": {"downbeat": 0.5, "stretch": 1.02}}
        self.assertEqual(CU.repaint_span(sc, 2.0, (1, 3), 8, 20.0), (round(2.5 * 1.02, 4), round(6.5 * 1.02, 4)))
        self.assertEqual(CU.repaint_span(sc, 2.0, (6, 8), 8, 20.0)[1], 20.0)     # the last bar: to the end
        takes = {1: {"seed": 11}, 2: {"seed": None, "comp": {"base": 1, "from": 3}},
                 3: {"seed": 40, "repaint": {"from": 1, "codes": 11}}, 4: {"seed": None}}
        self.assertEqual([CU.codes_seed(takes, n) for n in (1, 2, 3, 4, 9)], [11, 11, 11, None, None])
        pa = CU.plan(self.root, "final", self.spec(model="ace_step15"), {})
        raw = os.path.join(self.root, "raw.wav")
        open(raw, "wb").close()
        g = CU.repaint_graph(CU.graph(TG.load_target("ace_step15"), pa, 9, "proxy"), raw, 30.0, (4.0, 8.0), 77)
        by = {v["class_type"]: v["inputs"] for v in g.values()}
        self.assertNotIn("EmptyAceStep1.5LatentAudio", by)                     # sampled from the take
        self.assertEqual((by["TextEncodeAceStepAudio1.5"]["seed"], by["KSampler"]["seed"]), (9, 77))
        mask = by[CU.REPAINT_NODE]
        self.assertEqual((mask["seconds"], mask["start"], mask["end"]), (30.0, 4.0, 8.0))
        self.assertEqual(g[by["KSampler"]["latent_image"][0]]["class_type"], CU.REPAINT_NODE)
        self.assertEqual(by["VAEEncodeAudio"]["vae"], by["VAEDecodeAudio"]["vae"])
        self.assertTrue(CU.can_repaint(TG.load_target("ace_step15")))
        self.assertFalse(CU.can_repaint(TG.load_target("yue2")))
        self.assertFalse(CU.can_repaint(TG.load_target("stable_audio3")))

    @unittest.skipUnless(HAVE_FF, "ffmpeg isn't installed")
    def test_repaint_splices_the_take_back(self):
        p, n = self.ace_take(seed=5)
        base = CU.list_takes(self.root, "m01")[0]
        g, fin, n2 = CU.repaint(self.root, "final", "m01", n, (3, 5))
        self.assertEqual(n2, 2)
        by = {v["class_type"]: v["inputs"] for v in g.values()}
        self.assertEqual(by["TextEncodeAceStepAudio1.5"]["seed"], 5)            # the take's codes
        self.assertNotEqual(by["KSampler"]["seed"], 5)
        sc = CU.list_takes(self.root, "m01")[1]
        self.assertEqual(sc["status"], "queued")
        self.assertEqual((sc["repaint"]["from"], sc["repaint"]["bars"], sc["repaint"]["codes"]), (1, [3, 5], 5))
        self.assertEqual(sc["repaint"]["span"], [by[CU.REPAINT_NODE]["start"], by[CU.REPAINT_NODE]["end"]])
        # the model's audio: the whole take a quarter as loud (as if the round trip changed
        # it all): outside bars 3-5 the take's own comes back, inside the new
        raw = os.path.join(self.root, *base["raw"].split("/"))
        back = os.path.join(self.root, "back.wav")
        MX.write_wav(back, MX.decode(raw) * 0.25)
        done = CU.finish_take(self.root, "m01", n2, back, fin)
        self.assertFalse(os.path.exists(back))
        m, bm = done["measured"], base["measured"]
        self.assertEqual(done["status"], "ok")
        self.assertEqual((m["stretch"], m["downbeat"]), (bm["stretch"], bm["downbeat"]))   # as the take
        # the file as it came: the take's own samples outside the span (and its crossfades)
        a_, b_ = (int(t * MX.RATE) for t in sc["repaint"]["span"])
        mine, was = MX.decode(os.path.join(self.root, *done["raw"].split("/"))), MX.decode(raw)
        x = int(CU.COMP_XFADE * MX.RATE)
        self.assertEqual(len(mine), len(was))
        self.assertLess(float(abs(mine[:a_ - x] - was[:a_ - x]).max()), 1e-4)
        self.assertLess(float(abs(mine[b_ + x:] - was[b_ + x:]).max()), 1e-4)
        for b in (0, 1, 6, 7):
            self.assertAlmostEqual(m["levels"][b], bm["levels"][b], delta=0.05)
        for b in (3, 4):
            self.assertAlmostEqual(m["levels"][b], bm["levels"][b] - 12.0, delta=1.0)
        chk = done["repaint_check"]
        self.assertGreater(chk["beats"], 4)
        self.assertEqual(chk["on"], chk["on_before"])                             # the clicks stay put
        # a take with no seed (a comp) repaints from its base's codes; `fresh` from its own
        g, _, n3 = CU.repaint(self.root, "final", "m01", n2, (0, 1), seed=123, fresh=True)
        self.assertEqual(by_class(g, "TextEncodeAceStepAudio1.5")["seed"], 123)
        CU.update(self.root, "m01", n3, status="failed")
        g, _, _ = CU.repaint(self.root, "final", "m01", n2, (0, 1), seed=124)
        self.assertEqual(by_class(g, "TextEncodeAceStepAudio1.5")["seed"], 5)

    @unittest.skipUnless(HAVE_FF, "ffmpeg isn't installed")
    def test_a_followed_theme_is_the_one_it_was_made_with(self):
        # cue m09 with two finished takes; m01 follows its pick, made when t01 was picked
        CU.save_spec(self.root, {"id": "m09", "in": anchor("sh010"), "out": anchor("sh020", 60)})
        for _ in range(2):
            k = CU.reserve(self.root, "m09", {"pass": "final"})
            CU.update(self.root, "m09", k, status="ok")
            MX.write_wav(CU.take_paths(self.root, "m09", k)["wav"], MX._np().zeros((4800, 2), dtype="float32"))
        spec = CU.save_spec(self.root, self.spec(model="ace_step15", theme={"cue": "m09"}))
        CU.update(self.root, "m09", 1, measured={"score": 1.0})
        p = CU.plan(self.root, "final", spec, {})
        self.assertEqual(p["theme"]["label"], "m09 t01")
        n = CU.reserve(self.root, "m01", {"pass": "final", "target": "ace_step15", "seed": 5,
                                          "prompt": p["prompt"], "rendered_for": CU.fingerprint(p),
                                          "plan": {"fit": p["fit"]}, "theme": CU.theme_record(p["theme"])})
        CU.finish_take(self.root, "m01", n, self.make_take(p), p)
        # m09's t02 picked since: m01's take is stale, and a repaint of it still hears t01
        mix = MX.check(MX.load(self.root).get("final"))
        mix["items"] = [{"id": "m09", "track": "music", "path": "sound/m09/t02.wav",
                         "in": anchor("sh010"), "out": anchor("sh020", 60)}]
        MX.write(self.root, "final", mix)
        self.assertEqual(CU.stale(CU.list_takes(self.root, "m01")[0], CU.plan(self.root, "final", spec, {})),
                         ["the theme is m09 t02, not m09 t01"])
        g, _, n2 = CU.repaint(self.root, "final", "m01", n, (3, 5))
        refs = [v["inputs"]["audio"].path for v in g.values() if v["class_type"] == "LoadAudio"]
        self.assertIn(CU.take_paths(self.root, "m09", 1)["wav"], refs)
        self.assertNotIn(CU.take_paths(self.root, "m09", 2)["wav"], refs)
        self.assertEqual(CU.list_takes(self.root, "m01")[1]["theme"], {"label": "m09 t01", "use": "timbre", "from": "best"})

    @unittest.skipUnless(HAVE_FF, "ffmpeg isn't installed")
    def test_refusals(self):
        p, n = self.ace_take()
        with self.assertRaises(CU.CueError):
            CU.repaint(self.root, "final", "m01", n, (0, p["bars"] + 1))
        with self.assertRaises(CU.CueError):
            CU.repaint(self.root, "final", "m01", 9, (0, 1))
        CU.update(self.root, "m01", n, target="yue2")
        with self.assertRaisesRegex(CU.CueError, "can't make bars"):
            CU.repaint(self.root, "final", "m01", n, (0, 1))


def by_class(g: dict, ctype: str) -> dict:
    return next(v["inputs"] for v in g.values() if v["class_type"] == ctype)


class ThemeSpecTest(unittest.TestCase):
    def test_theme_forms(self):
        self.assertEqual(CU.check_theme({"theme": "porch"}, "m02"), {"theme": "porch"})
        self.assertEqual(CU.check_theme({"theme": "porch", "strength": 0.9}, "m02"),
                         {"theme": "porch", "strength": 0.9})
        self.assertEqual(CU.check_theme({"cue": "m01", "take": 2, "strength": 0.86}, "m02"),
                         {"cue": "m01", "take": 2, "strength": 0.86})
        for bad in ({"theme": "a b"}, {"theme": "porch", "strength": 1.2}, {"cue": "m01", "strength": "hi"},
                    {"theme": "porch", "cue": "m01"}):
            with self.subTest(bad=bad), self.assertRaises(CU.CueError):
                CU.check_theme(bad, "m02")
        self.assertEqual(CU.theme_text({"theme": "porch"}), "porch")

    def test_series_themes(self):
        got = CU.series_themes({"sound": {"themes": {
            "porch": {"ep": "ep01", "cue": "m01", "take": 3, "role": "show", "words": " warm,  hopeful "},
            "glance": {"file": "themes/glance.wav", "for": ["hank"]},
            "kell": {"ep": "ep01", "cue": "m02"},                        # a take is pinned
            "bad": {"file": "x.txt"}, "residence": {"ep": "ep07", "cue": "m01", "take": 1, "role": "villain"}}}})
        self.assertEqual(got["porch"], {"ep": "ep01", "cue": "m01", "take": 3, "role": "show", "words": "warm, hopeful"})
        self.assertEqual(got["glance"], {"file": "themes/glance.wav", "for": ["hank"]})
        self.assertEqual(sorted(got["_errors"]), ["bad", "kell", "residence"])
        self.assertEqual(CU.series_themes({}), {})


@unittest.skipUnless(HAVE_FF, "ffmpeg/ffprobe not on PATH")
class SeriesThemeTest(unittest.TestCase):
    """A theme from another episode (the series config's `sound.themes`): Stable Audio 3
    renders from its take, reshaped to the cue; its melody score and the ranking."""

    def setUp(self):
        from test_beats import clicks
        self._tmp = tempfile.TemporaryDirectory()
        self.shows = os.path.join(self._tmp.name, "Shows")
        self.ep1, self.ep2 = (os.path.join(self.shows, e) for e in ("ep01", "ep02"))
        for ep in (self.ep1, self.ep2):
            os.makedirs(ep)
            episode(ep)
        self.series = {"sound": {"themes": {"porch": {"ep": "ep01", "cue": "m01", "take": 1, "role": "show"}}}}
        F.write_json(os.path.join(self.shows, "series.json"), self.series)
        # ep01's m01, one finished take: the theme
        spec = CU.save_spec(self.ep1, {"id": "m01", "in": anchor("sh010"), "out": anchor("sh020", 60), "bpm": 92})
        p = CU.plan(self.ep1, "final", spec, self.series)
        n = CU.reserve(self.ep1, "m01", {"pass": "final", "rendered_for": CU.fingerprint(p), "plan": {"fit": p["fit"]}})
        raw = os.path.join(self.ep1, "raw.wav")
        MX.write_wav(raw, clicks(p["fit"]["ask_bpm"], p["bars"], offset=0.25))
        CU.finish_take(self.ep1, "m01", n, raw, p)
        self.theme_bpm = p["fit"]["bpm"]

    def tearDown(self):
        self._tmp.cleanup()

    def plan2(self, **kw):
        spec = CU.save_spec(self.ep2, {"id": "m02", "in": anchor("sh010"), "out": anchor("sh030", 100),
                                       "bpm": 92, "theme": {"theme": "porch"}, **kw})
        return CU.plan(self.ep2, "final", spec, self.series)

    def test_resolved_staged_and_rendered_from(self):
        p = self.plan2()
        th = p["theme"]
        self.assertEqual((th["use"], th["label"], th["strength"]), ("audio", "porch (ep01 m01 t01)", 0.86))
        self.assertAlmostEqual(th["grid"]["bpm"], self.theme_bpm, places=2)
        self.assertEqual(CU.fingerprint(p)["theme"], "porch (ep01 m01 t01)")
        CU.stage_theme(self.ep2, "m02", p)
        staged = p["theme"]["audio"]
        self.assertTrue(staged.startswith(os.path.join(self.ep2, "sound", "m02", "theme_")))
        self.assertAlmostEqual(len(MX.decode(staged)) / MX.RATE, p["ask_seconds"], delta=0.05)
        self.assertGreater(p["theme"]["staged"]["bars"], 0)
        self.assertNotIn("warnings", p)                                # the same tempo near enough
        g = CU.graph(TG.load_target("stable_audio3"), p, 5, "final")
        kinds = {v["class_type"] for v in g.values()}
        self.assertFalse(kinds & {"KSampler", "EmptyLatentAudio", "SheetSage2AudioToABC"})
        sig = [float(x) for x in by_class(g, "ManualSigmas")["sigmas"].split(",")]
        self.assertEqual((len(sig), sig[-1]), (9, 0.0))
        self.assertAlmostEqual(sig[0], 2 * 0.86 / 1.86, places=5)      # SA3's shift 2 at t0
        self.assertEqual(by_class(g, "SamplerCustom")["noise_seed"], 5)
        dec = by_class(g, "VAEDecodeAudio")["samples"]
        self.assertEqual(g[dec[0]]["class_type"], "SamplerCustom")
        # with the melody score: both transcribed, each saved as its role
        g = CU.graph(TG.load_target("stable_audio3"), dict(p, melody=True), 5, "final")
        self.assertEqual(sum(v["class_type"] == "SheetSage2AudioToABC" for v in g.values()), 2)
        self.assertEqual(sorted(CU.plan_outputs(g).values()), ["melody", "theme_melody"])
        # a stronger theme starts the schedule later
        g = CU.graph(TG.load_target("stable_audio3"), self.plan2(theme={"theme": "porch", "strength": 0.7}), 5, "final")
        self.assertAlmostEqual(float(by_class(g, "ManualSigmas")["sigmas"].split(",")[0]), 2 * 0.7 / 1.7, places=5)

    def test_a_cue_takes_its_themes_tempo(self):
        spec = CU.save_spec(self.ep2, {"id": "m02", "in": anchor("sh010"), "out": anchor("sh030", 100),
                                       "theme": {"theme": "porch"}})
        p = CU.plan(self.ep2, "final", spec, self.series)
        self.assertAlmostEqual(p["fit"]["bpm"], self.theme_bpm, delta=self.theme_bpm * CU.FIT_SPREAD)
        self.assertNotIn("warnings", CU.stage_theme(self.ep2, "m02", p))

    def test_a_file_theme_says_its_tempo(self):
        from test_beats import clicks
        MX.write_wav(os.path.join(self.shows, "glance.wav"), clicks(80, 4, offset=0.0))
        series = {"sound": {"themes": {"glance": {"file": "glance.wav", "bpm": 80}}}}
        self.assertEqual(CU.series_themes(series)["glance"], {"file": "glance.wav", "bpm": 80.0})
        spec = CU.save_spec(self.ep2, {"id": "m02", "in": anchor("sh010"), "out": anchor("sh030", 100),
                                       "theme": {"theme": "glance"}})
        p = CU.stage_theme(self.ep2, "m02", CU.plan(self.ep2, "final", spec, series))
        self.assertEqual((p["theme"]["label"], p["theme"]["grid"]["bpm"]), ("glance (glance.wav)", 80.0))
        self.assertAlmostEqual(p["theme"]["staged"]["stretch"], p["fit"]["ask_bpm"] / 80, places=3)
        # without its bpm, and a tempo far from the cue's: played at its own, and said
        far = CU.save_spec(self.ep2, {**spec, "bpm": 140, "fixed_tempo": True})
        p = CU.stage_theme(self.ep2, "m02", CU.plan(self.ep2, "final", far, {"sound": {"themes": {
            "glance": {"file": "glance.wav"}}}}))
        self.assertEqual(p["theme"]["staged"]["stretch"], 1.0)
        self.assertTrue(any("tempo couldn't be told" in w for w in p["warnings"]), p.get("warnings"))

    def test_a_far_tempo_is_said(self):
        p = CU.stage_theme(self.ep2, "m02", self.plan2(bpm=120, fixed_tempo=True))
        self.assertAlmostEqual(p["theme"]["staged"]["stretch"], 120 / self.theme_bpm, places=2)
        self.assertTrue(any("faster than it was made" in w for w in p["warnings"]), p.get("warnings"))

    def test_missing_theme_is_a_warning(self):
        p = CU.plan(self.ep2, "final", CU.save_spec(self.ep2, {"id": "m02", "in": anchor("sh010"),
                                                              "out": anchor("sh030"), "theme": {"theme": "kell"}}),
                    self.series)
        self.assertIsNone(p["theme"]["use"])
        self.assertIn("no theme kell", p["warnings"][0])

    def test_melody_score_and_ranking(self):
        from test_beats import clicks
        p = CU.stage_theme(self.ep2, "m02", self.plan2())
        theme = "X:1\nM:4/4\nL:1/8\nK:D\nV:1\nD2 E2 F2 G2 | A4 F4 | G3 F E4 | D8\n"
        lost = "X:1\nM:4/4\nL:1/8\nK:D\nV:1\nB,2 B,2 B,2 B,2 | B,8 | B,8 | B,8\n"
        for melody in (lost, theme):
            n = CU.reserve(self.ep2, "m02", {"pass": "final"})
            raw = os.path.join(self.ep2, f"raw{n}.wav")
            MX.write_wav(raw, clicks(p["fit"]["ask_bpm"], p["bars"], offset=0.25))
            CU.finish_take(self.ep2, "m02", n, raw, p, {"melody": melody, "theme_melody": theme})
        takes = CU.list_takes(self.ep2, "m02")
        self.assertEqual([(t["measured"]["melody"], t["measured"]["on_theme"]) for t in takes],
                         [(0.0, False), (1.0, True)])
        self.assertTrue(os.path.isfile(os.path.join(self.ep2, "sound", "m02", "t02.melody.abc")))
        self.assertEqual([t["take"] for t in CU.ranked(takes)], [2, 1])   # the one that kept it first

    def test_pin_a_take_as_a_series_theme(self):
        # each episode with a series config of its own (as new episodes get), and a script
        for ep in (self.ep1, self.ep2):
            F.write_json(os.path.join(ep, "series.json"), {"title": "Shows", "sound": {"score": "dark"}})
            F.write_text(os.path.join(ep, os.path.basename(ep) + ".md"), "= x\n")
        with self.assertRaisesRegex(CU.CueError, "no finished take 9"):
            CU.pin_series_theme(self.ep1, "m01", 9, "mark")
        r = CU.pin_series_theme(self.ep1, "m01", 1, "mark", role="story", words="the week's mark")
        self.assertEqual((r["written"], r["same"]), (["ep01", "ep02"], []))
        self.assertEqual(r["theme"], {"name": "mark", "ep": "ep01", "cue": "m01", "take": 1, "role": "story",
                                      "words": "the week's mark"})
        for ep in (self.ep1, self.ep2):
            cfg = F.read_json_or(os.path.join(ep, "series.json"), {})
            self.assertEqual(cfg["sound"], {"score": "dark", "themes": {"mark": {
                "ep": "ep01", "cue": "m01", "take": 1, "role": "story", "words": "the week's mark"}}})
        self.assertTrue(os.listdir(os.path.join(self.ep2, "_history")))     # the old config kept
        # again: nothing to write
        self.assertEqual(CU.pin_series_theme(self.ep1, "m01", 1, "mark", role="story",
                                             words="the week's mark")["same"], ["ep01", "ep02"])
        # ep02 sees it, as the window offers it, and plans a cue on it
        names = [(t["name"], t["label"], t["error"]) for t in CU.theme_list(self.ep2)]
        self.assertEqual(names, [("mark", "mark (ep01 m01 t01)", None)])
        spec = CU.save_spec(self.ep2, {"id": "m02", "in": anchor("sh010"), "out": anchor("sh030"),
                                       "theme": {"theme": "mark"}})
        self.assertEqual(CU.plan(self.ep2, "final", spec)["theme"]["use"], "audio")

    def test_a_series_theme_cant_be_deleted(self):
        with self.assertRaisesRegex(CU.CueError, "series theme porch"):
            CU.delete(self.ep1, "m01")

    def test_render_route(self):
        ctx = A.Context(os.path.join(self._tmp.name, "user"), "http://127.0.0.1:0", env={}, runner=_Runner())
        code, _ = A.put_config(ctx, {"roots": [self.shows]})
        self.assertEqual(code, 200)
        code, _ = A.put_cue(ctx, {"ep": self.ep2, "cue": {"id": "m02", "in": anchor("sh010"),
                                                          "out": anchor("sh030", 100), "bpm": 92,
                                                          "theme": {"theme": "porch"}}})
        self.assertEqual(code, 200)
        code, r = A.post_cue_render(ctx, {"ep": self.ep2, "pass": "final", "cue": "m02", "takes": 2})
        self.assertEqual(code, 200, r)
        _, _, g, _ = ctx.runner.asked[0]
        self.assertIn("SamplerCustom", {v["class_type"] for v in g.values()})
        # ComfyUI can't be asked here: no SheetSage2, no melody score
        self.assertNotIn("SheetSage2AudioToABC", {v["class_type"] for v in g.values()})
        sc = CU.list_takes(self.ep2, "m02")[0]
        self.assertEqual((sc["theme"]["label"], sc["theme"]["use"], sc["theme"]["strength"]),
                         ("porch (ep01 m01 t01)", "audio", 0.86))
        self.assertIn("bars", sc["theme"]["staged"])


class _Runner:
    """seriesmith's queue, stood in for: it remembers what it was asked."""

    def __init__(self):
        self.asked = []
        self.calls = []
        self.backends = {"local"}

    def backend(self, name):
        return name if name in self.backends else None

    def enqueue_cue(self, root, cid, n, graph, p, backend, call=None, tracks=1):
        self.tracks = tracks
        self.asked.append((cid, n, graph, backend))
        self.calls.append(call)
        return f"job{n}"


class _Job:
    def __init__(self, cue, status="queued"):
        self.kind, self.info, self.status, self.created = "cue", {"cue": cue}, status, 0.0


class _QRunner(_Runner):
    """_Runner with a queue of its own: each cue take asked for is a job, queued."""

    def __init__(self):
        super().__init__()
        self.queue = type("Q", (), {"jobs": {}})()

    def enqueue_cue(self, root, cid, n, graph, p, backend, call=None, tracks=1):
        job = super().enqueue_cue(root, cid, n, graph, p, backend, call, tracks)
        j = _Job(cid)
        j.info["ep"] = root
        self.queue.jobs[job + cid] = j
        return job


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

    def test_a_hosted_model_renders_as_router_calls(self):
        self.call(A.put_cue, {"ep": self.ep, "cue": {"id": "m01", "in": anchor("sh010"),
                                                     "out": anchor("sh020", 60), "bpm": 92,
                                                     "model": "pika_music"}})
        body = {"ep": self.ep, "pass": "final", "cue": "m01", "takes": 2, "backend": "local"}
        self.assertIn("Comfy API key", self.call(A.post_cue_render, body, 409)["error"])
        self.assertEqual(self.ctx.runner.asked, [])
        self.ctx.runner.backends.add("router")
        self.call(A.post_cue_render, body)
        # on Router whatever the body asked, each take a call of its own seed, no graph
        self.assertEqual([(g, b) for _, _, g, b in self.ctx.runner.asked], [(None, "router")] * 2)
        self.assertEqual([c[0] for c in self.ctx.runner.calls], ["pika/pika-music"] * 2)
        self.assertNotEqual(self.ctx.runner.calls[0][1]["seed"], self.ctx.runner.calls[1][1]["seed"])

    @unittest.skipUnless(HAVE_FF, "ffmpeg isn't installed")
    def test_repaint(self):
        self.call(A.put_cue, {"ep": self.ep, "cue": {"id": "m01", "in": anchor("sh010"),
                                                     "out": anchor("sh020", 60), "bpm": 92,
                                                     "model": "ace_step15"}})
        self.call(A.post_cue_render, {"ep": self.ep, "pass": "final", "cue": "m01", "takes": 1})
        body = {"ep": self.ep, "pass": "final", "cue": "m01", "take": 1, "bars": [1, 3]}
        self.assertIn("no finished take", self.call(A.post_cue_repaint, body, 409)["error"])
        p = CU.plan(self.ep, "final", CU.load_spec(self.ep, "m01"))
        from test_beats import clicks
        raw = os.path.join(self.ep, "raw.wav")
        MX.write_wav(raw, clicks(p["fit"]["ask_bpm"], p["bars"], offset=0.4))
        CU.finish_take(self.ep, "m01", 1, raw, p)
        self.call(A.post_cue_repaint, {**body, "bars": [1]}, 400)
        self.call(A.post_cue_repaint, {**body, "fresh": "yes"}, 400)
        self.call(A.post_cue_repaint, {**body, "bars": [0, p["bars"] + 2]}, 409)
        r = self.call(A.post_cue_repaint, {**body, "seed": 4})["queued"]
        self.assertEqual((r["take"], r["job"], r["seed"]), (2, "job2", 4))
        _, n, g, backend = self.ctx.runner.asked[-1]
        self.assertEqual((n, backend), (2, "local"))
        self.assertIn(CU.REPAINT_NODE, {v["class_type"] for v in g.values()})
        sc = self.call(A.get_cue, {"ep": self.ep, "pass": "final", "cue": "m01"})["takes"]
        self.assertEqual(next(t for t in sc if t["take"] == 2)["repaint"]["bars"], [1, 3])
        # a finished take's length (its wav's), for the window to show the whole of it; none queued
        secs = {t["take"]: t["seconds"] for t in sc}
        self.assertIsNone(secs[2])
        self.assertGreater(secs[1], p["bars"] * p["bar"] * 0.9)
        self.assertLess(secs[1], p["bars"] * p["bar"] * 1.2)
        # a model that can't repaint
        CU.update(self.ep, "m01", 1, target="stable_audio3")
        self.assertIn("can't make bars", self.call(A.post_cue_repaint, body, 409)["error"])

    def test_delete(self):
        self.ctx.runner = _QRunner()
        for cid in ("m01", "m02"):
            self.call(A.put_cue, {"ep": self.ep, "cue": {"id": cid, "in": anchor("sh010"),
                                                         "out": anchor("sh020", 60)}})
        self.call(A.post_cue_render, {"ep": self.ep, "pass": "final", "cue": "m01", "takes": 2})
        own = {"id": "s01", "track": "music", "path": "sound/score.wav", "in": anchor("sh010")}
        MX.save(self.ep, {p: {"items": [{"id": "m01", "track": "music", "path": "sound/m01/t02.wav",
                                         "in": anchor("sh010"), "mute": True}, own]}
                          for p in ("final", "proxy")})
        # its takes on the queue: refused until they're done
        q = {"ep": self.ep, "cue": "m01"}
        self.assertIn("2 takes queued", self.call(A.delete_cue, q, 409)["error"])
        for j in self.ctx.runner.queue.jobs.values():
            j.status = "canceled"
        # another cue's theme: refused
        self.call(A.put_cue, {"ep": self.ep, "cue": {"id": "m02", "in": anchor("sh010"),
                                                     "out": anchor("sh020", 60),
                                                     "theme": {"cue": "m01", "take": 1}}})
        self.assertIn("theme of m02", self.call(A.delete_cue, q, 409)["error"])
        self.call(A.put_cue, {"ep": self.ep, "cue": {"id": "m02", "in": anchor("sh010"),
                                                     "out": anchor("sh020", 60)}})
        r = self.call(A.delete_cue, q)
        self.assertEqual((r["cue"], r["takes"], r["mixes"]), ("m01", 2, ["final", "proxy"]))
        self.assertRegex(r["moved_to"], r"^_history/cue-m01\.\d{8}-\d{6}$")
        kept = os.path.join(self.ep, *r["moved_to"].split("/"))
        self.assertEqual(sorted(os.listdir(kept)), ["spec.json", "t01.json", "t02.json"])
        self.assertFalse(os.path.exists(os.path.join(self.ep, "sound", "m01")))
        # both passes' mixes without it, the rest kept; the old mix.json in _history
        self.assertEqual({p: m["items"] for p, m in MX.load(self.ep).items()},
                         {"final": [own], "proxy": [own]})
        self.assertTrue(any(n.startswith("mix.json.") for n in os.listdir(os.path.join(self.ep, "_history"))))
        self.assertEqual([c["spec"]["id"] for c in self.call(A.get_cues, {"ep": self.ep})["cues"]], ["m02"])
        self.call(A.delete_cue, q, 404)
        self.call(A.delete_cue, {"ep": self.ep, "cue": "../x"}, 404)

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

    def test_a_cue_that_doesnt_read_is_said_not_dropped(self):
        self.call(A.put_cue, {"ep": self.ep, "cue": {"id": "m01", "in": anchor("sh010"),
                                                     "out": anchor("sh020", 60)}})
        F.write_json(os.path.join(CU.cue_dir(self.ep, "m02"), "spec.json"),
                     {"id": "m02", "in": anchor("sh010"), "out": anchor("sh020", 60), "model": "not_here"})
        os.makedirs(CU.cue_dir(self.ep, "not_a_cue"), exist_ok=True)
        r = self.call(A.get_cues, {"ep": self.ep, "pass": "final"})
        self.assertEqual([c["spec"]["id"] for c in r["cues"]], ["m01"])
        self.assertEqual([u["id"] for u in r["unreadable"]], ["m02"])
        self.assertIn("not_here", r["unreadable"][0]["error"])

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
