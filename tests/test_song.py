"""
Songs and themes (docs/SOUND.md phase 2: the `yue2` target and the leitmotif reference):
YuE2's brief (the lyrics by section, the tempo for its plan's Q: line), a song with no
lyrics refused, the graph with its plan saved, a take's plan kept and read; a cue's theme
checked, and heard by each model its own way (YuE2 sings it: a take's own plan, or SheetSage2
transcribes it; ACE-Step takes its sound as the timbre; Stable Audio 3 is warned), and the
takes stale when it changes.
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
from seriesmith import ff as FF  # noqa: E402
from seriesmith import mix as MX  # noqa: E402
from seriesmith import targets as TG  # noqa: E402
from seriesmith.backends import File  # noqa: E402
from seriesmith.core import abc as ABC  # noqa: E402
from seriesmith.core import fileio as F  # noqa: E402
from test_cue import _Runner, anchor, episode  # noqa: E402

HAVE_FF = bool(FF.have("ffmpeg") and FF.have("ffprobe"))
FIX = os.path.join(HERE, "fixtures", "abc")
LYRICS = [{"name": "verse", "bars": 4, "lyrics": "Coffee in a paper cup\nNeon humming"},
          {"name": "chorus 2", "lyrics": "Stay a while"}, {"name": "solo", "words": "guitar"}]


def plan_text(name="yue2_s1.abc") -> str:
    with open(os.path.join(FIX, name), encoding="utf-8") as fh:
        return fh.read()


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        episode(self.root)
        MX.save(self.root, {"final": {"hits": [{"id": "h1", "name": "door", "at": anchor("sh020", 12)}]}})

    def tearDown(self):
        self._tmp.cleanup()

    def spec(self, **kw):
        return CU.check_spec({"id": "m02", "in": anchor("sh010"), "out": anchor("sh030", 100),
                              "bpm": 96, "kind": "song", "sections": LYRICS, **kw})

    def theme_take(self, plan: bool = True, status: str = "ok") -> None:
        """Cue m01 with a finished take 1 (a wav, and its plan when `plan`)."""
        CU.save_spec(self.root, {"id": "m01", "in": anchor("sh010"), "out": anchor("sh020", 60)})
        n = CU.reserve(self.root, "m01", {"pass": "final"})
        CU.update(self.root, "m01", n, status=status)
        MX.write_wav(CU.take_paths(self.root, "m01", n)["wav"], MX._np().zeros((4800, 2), dtype="float32"))
        if plan:
            F.write_text(os.path.join(CU.cue_dir(self.root, "m01"), "t01.abc"), ABC.set_tempo(plan_text(), 90))


class Yue2Test(_Base):
    def test_brief(self):
        p = CU.plan(self.root, "final", self.spec(key="D major"), {})
        self.assertEqual(p["target"], "yue2")
        v = p["prompt"]["values"]
        # the sections with lyrics, under their tags ("chorus 2" sings as a chorus); a section
        # without lyrics isn't sung
        self.assertEqual(v["lyrics"], "[Verse]\nCoffee in a paper cup\nNeon humming\n\n[Chorus]\nStay a while")
        self.assertEqual(v["mode"], "full")
        self.assertEqual(v["tempo"], f"Q:1/4={p['fit']['ask_bpm']}\nK:")
        self.assertIn("vocal", p["prompt"]["prompt"])
        self.assertIn(f"{p['fit']['ask_bpm']} BPM", p["prompt"]["prompt"])
        self.assertIn("D major", p["prompt"]["prompt"])
        self.assertNotIn("blocked", p)
        # 6/8: the plan's tempo counts eighths, as the cue's does
        self.assertTrue(CU.plan(self.root, "final", self.spec(meter="6/8"), {})["prompt"]["values"]["tempo"].startswith("Q:1/8="))

    def test_no_lyrics_no_song(self):
        p = CU.plan(self.root, "final", self.spec(sections=[{"name": "verse", "words": "warm"}]), {})
        self.assertIn("sings words", p["blocked"])
        # ACE-Step sings a song's sections as words: not refused
        self.assertNotIn("blocked", CU.plan(self.root, "final", self.spec(model="ace_step15", sections=[]), {}))

    def test_graph_keeps_the_plan(self):
        p = CU.plan(self.root, "final", self.spec(), {})
        g = CU.graph(TG.load_target("yue2"), p, 7, "proxy")
        cls = sorted(v["class_type"] for v in g.values())
        self.assertEqual(cls.count("SaveText"), 2)
        self.assertEqual(cls.count("RegexReplace"), 2)
        self.assertIn("YuE2GenerateABC", cls)
        roles = CU.plan_outputs(g)
        self.assertEqual(sorted(roles.values()), ["sung", "written"])
        sung = next(k for k, r in roles.items() if r == "sung")
        # the song sings what the sung plan saves: the plan with its tempo set
        music = next(v for v in g.values() if v["class_type"] == "YuE2GenerateMusic")
        self.assertEqual(music["inputs"]["abc"], g[sung]["inputs"]["text"])
        tempo = next(v for v in g.values() if v["_meta"]["title"] == "Plan at the cue's tempo")
        self.assertEqual(tempo["inputs"]["replace"], f"Q:1/4={p['fit']['ask_bpm']}\nK:")
        seeds = [v["inputs"]["seed"] for v in g.values() if "seed" in v["inputs"]]
        self.assertEqual(seeds, [7, 7, 7])
        self.assertEqual(music["inputs"]["mode"], "full")

    @unittest.skipUnless(HAVE_FF, "needs ffmpeg")
    def test_a_take_keeps_its_plan(self):
        from test_beats import clicks
        spec = CU.save_spec(self.root, self.spec())
        p = CU.plan(self.root, "final", spec, {})
        raw = os.path.join(self.root, "raw.wav")
        MX.write_wav(raw, clicks(p["fit"]["ask_bpm"], p["bars"], offset=0.0))
        n = CU.reserve(self.root, "m02", {"pass": "final"})
        sung = ABC.set_tempo(plan_text(), p["fit"]["ask_bpm"])
        sc = CU.finish_take(self.root, "m02", n, raw, p, {"written": plan_text(), "sung": sung})
        song = sc["song"]
        self.assertEqual(song["file"], "sound/m02/t01.abc")
        with open(os.path.join(self.root, "sound", "m02", "t01.abc"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), sung)
        self.assertEqual((song["tempo_written"], song["tempo"], song["source"]), (93.0, p["fit"]["ask_bpm"], "planned"))
        self.assertEqual(song["bars"], 101)
        self.assertEqual(song["plan_seconds"], round(202 * 60 / p["fit"]["ask_bpm"], 3))
        kept = MX.decode(os.path.join(self.root, "sound", "m02", "t01_raw.wav"))
        self.assertAlmostEqual(song["raw_seconds"], len(kept) / MX.RATE, places=2)
        self.assertAlmostEqual(song["short"], song["plan_seconds"] - song["raw_seconds"], places=2)
        first = song["sections"][0]
        self.assertEqual((first["name"], first["start"]), ("intro", 0.0))
        self.assertAlmostEqual(first["at"], -sc["measured"]["offset"], places=3)
        verse = song["sections"][1]
        self.assertAlmostEqual(verse["start"], 18 * 60 / p["fit"]["bpm"], places=2)
        self.assertAlmostEqual(verse["cue_bars"], verse["seconds"] / p["bar"], places=1)
        self.assertAlmostEqual(song["first_note"], 17 * 60 / p["fit"]["bpm"], places=2)


class ThemeSpecTest(_Base):
    def test_checked(self):
        self.assertEqual(self.spec(theme={"cue": "m01", "take": 2})["theme"], {"cue": "m01", "take": 2})
        self.assertEqual(self.spec(theme={"file": "audio\\theme.wav"})["theme"], {"file": "audio/theme.wav"})
        self.assertEqual(self.spec(theme={"file": "../refs/gallery/hum.flac"})["theme"]["file"], "../refs/gallery/hum.flac")
        for bad in ({"cue": "m02", "take": 1}, {"cue": "m01"}, {"cue": "m01", "take": 0},
                    {"file": "C:/x/theme.wav"}, {"file": "/x/theme.wav"}, {"file": "theme.txt"},
                    {"cue": "m01", "take": 1, "file": "a.wav"}, "m01"):
            with self.subTest(bad=bad), self.assertRaises(CU.CueError):
                self.spec(theme=bad)

    def test_the_cue_must_be_there_when_saved(self):
        with self.assertRaisesRegex(CU.CueError, "no cue m01"):
            CU.save_spec(self.root, self.spec(theme={"cue": "m01", "take": 1}))
        self.theme_take()
        CU.save_spec(self.root, self.spec(theme={"cue": "m01", "take": 1}))


class ThemeTest(_Base):
    def test_yue2_sings_a_takes_plan(self):
        self.theme_take()
        p = CU.plan(self.root, "final", self.spec(theme={"cue": "m01", "take": 1}), {})
        th = p["theme"]
        self.assertEqual((th["use"], th["label"], th["warning"]), ("plan", "m01 t01", None))
        self.assertEqual(p["prompt"]["values"]["mode"], "melody")
        # the plan's sections known before it renders, at this cue's tempo
        self.assertEqual(p["song"]["source"], "theme plan")
        self.assertEqual([s["name"] for s in p["song"]["sections"]][:3], ["intro", "verse", "chorus"])
        self.assertAlmostEqual(p["song"]["sections"][1]["start"], 18 * 60 / p["fit"]["bpm"], places=2)
        g = CU.graph(TG.load_target("yue2"), p, 3, "final")
        cls = [v["class_type"] for v in g.values()]
        self.assertNotIn("YuE2GenerateABC", cls)
        self.assertEqual(cls.count("SaveText"), 1)                 # the sung plan only
        first = next(v for v in g.values() if v["_meta"]["title"] == "Plan without its tempo")
        self.assertEqual(first["inputs"]["string"], th["abc"])
        self.assertNotIn('"D"', th["abc"])                          # its melody: no chords
        music = next(v for v in g.values() if v["class_type"] == "YuE2GenerateMusic")
        self.assertEqual(music["inputs"]["mode"], "melody")
        self.assertEqual(CU.fingerprint(p)["theme"], "m01 t01")

    def test_yue2_transcribes_a_recording(self):
        os.makedirs(os.path.join(self.root, "audio"))
        MX.write_wav(os.path.join(self.root, "audio", "hum.wav"), MX._np().zeros((4800, 2), dtype="float32"))
        p = CU.plan(self.root, "final", self.spec(theme={"file": "audio/hum.wav"}), {})
        self.assertEqual(p["theme"]["use"], "transcribe")
        self.assertNotIn("song", p)
        g = CU.graph(TG.load_target("yue2"), p, 3, "final")
        by = {v["class_type"]: v for v in g.values()}
        self.assertNotIn("YuE2GenerateABC", by)
        self.assertIsInstance(by["LoadAudio"]["inputs"]["audio"], File)
        self.assertEqual(by["AudioEncoderLoader"]["inputs"]["audio_encoder_name"], "sheetsage2_bf16.safetensors")
        self.assertEqual(by["SheetSage2AudioToABC"]["inputs"]["mode"], "melody")
        self.assertEqual(sorted(CU.plan_outputs(g).values()), ["sung", "written"])
        self.assertEqual(by["YuE2GenerateMusic"]["inputs"]["mode"], "melody")
        # a take without a plan (not a YuE2 one) is transcribed too
        self.theme_take(plan=False)
        p = CU.plan(self.root, "final", self.spec(theme={"cue": "m01", "take": 1}), {})
        self.assertEqual(p["theme"]["use"], "transcribe")

    def test_ace_step_hears_its_timbre(self):
        self.theme_take()
        p = CU.plan(self.root, "final", self.spec(model="ace_step15", theme={"cue": "m01", "take": 1}), {})
        self.assertEqual(p["theme"]["use"], "timbre")
        g = CU.graph(TG.load_target("ace_step15"), p, 3, "final")
        by = {v["class_type"]: (k, v) for k, v in g.items()}
        ref_id, ref = by["ReferenceTimbreAudio"]
        enc_id, _ = by["TextEncodeAceStepAudio1.5"]
        self.assertEqual(ref["inputs"]["conditioning"], [enc_id, 0])
        self.assertEqual(g[ref["inputs"]["latent"][0]]["class_type"], "VAEEncodeAudio")
        self.assertEqual(by["KSampler"][1]["inputs"]["positive"], [ref_id, 0])
        self.assertEqual(by["ConditioningZeroOut"][1]["inputs"]["conditioning"], [ref_id, 0])
        self.assertIsInstance(by["LoadAudio"][1]["inputs"]["audio"], File)
        # without a theme the graph is as it was
        plain = CU.graph(TG.load_target("ace_step15"), CU.plan(self.root, "final", self.spec(model="ace_step15"), {}), 3, "final")
        self.assertNotIn("ReferenceTimbreAudio", [v["class_type"] for v in plain.values()])

    def test_stable_audio_takes_none(self):
        self.theme_take()
        p = CU.plan(self.root, "final", self.spec(kind="score", sections=[], theme={"cue": "m01", "take": 1}), {})
        self.assertEqual(p["target"], "stable_audio3")
        self.assertIsNone(p["theme"]["use"])
        self.assertIn("takes no theme", p["warnings"][0])
        self.assertNotIn("blocked", p)

    def test_missing_theme_warns(self):
        p = CU.plan(self.root, "final", self.spec(theme={"file": "audio/none.wav"}), {})
        self.assertIsNone(p["theme"]["use"])
        self.assertIn("isn't there", p["warnings"][0])
        self.theme_take(status="failed")
        p = CU.plan(self.root, "final", self.spec(theme={"cue": "m01", "take": 1}), {})
        self.assertIn("isn't finished", p["warnings"][0])
        p = CU.plan(self.root, "final", self.spec(theme={"cue": "m01", "take": 5}), {})
        self.assertIn("no such take", p["warnings"][0])

    def test_stale_when_the_theme_changes(self):
        self.theme_take()
        p0 = CU.plan(self.root, "final", self.spec(), {})
        p1 = CU.plan(self.root, "final", self.spec(theme={"cue": "m01", "take": 1}), {})
        self.assertEqual(CU.stale({"rendered_for": CU.fingerprint(p0)}, p0), [])
        self.assertEqual(CU.stale({"rendered_for": CU.fingerprint(p0)}, p1), ["the theme is m01 t01"])
        self.assertEqual(CU.stale({"rendered_for": CU.fingerprint(p1)}, p0), ["the theme m01 t01 is gone"])
        p2 = CU.plan(self.root, "final", self.spec(theme={"file": "audio/x.wav"}), {})
        self.assertEqual(CU.stale({"rendered_for": CU.fingerprint(p1)}, p2), ["the theme is audio/x.wav, not m01 t01"])


class RouteTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.shows = os.path.join(self._tmp.name, "Shows")
        self.ep = os.path.join(self.shows, "ep01")
        os.makedirs(self.ep)
        episode(self.ep)
        self.ctx = A.Context(os.path.join(self._tmp.name, "user"), "http://127.0.0.1:0", env={},
                             runner=_Runner())
        code, _ = A.put_config(self.ctx, {"roots": [self.shows]})
        self.assertEqual(code, 200)

    def tearDown(self):
        self._tmp.cleanup()

    def call(self, fn, arg, status=200):
        code, data = fn(self.ctx, arg)
        self.assertEqual(code, status, data)
        return data

    def test_song_routes(self):
        spec = {"id": "m01", "kind": "song", "in": anchor("sh010"), "out": anchor("sh020", 60), "bpm": 92,
                "sections": [{"name": "verse"}]}
        self.call(A.put_cue, {"ep": self.ep, "cue": spec})
        got = self.call(A.get_cue, {"ep": self.ep, "pass": "final", "cue": "m01"})
        self.assertIn("sings words", got["plan"]["blocked"])
        self.assertIn("sings words", self.call(A.post_cue_render, {"ep": self.ep, "pass": "final", "cue": "m01"}, 400)["error"])
        spec["sections"] = [{"name": "verse", "lyrics": "la la"}]
        self.call(A.put_cue, {"ep": self.ep, "cue": spec})
        r = self.call(A.post_cue_render, {"ep": self.ep, "pass": "final", "cue": "m01", "takes": 2})
        self.assertEqual([q["take"] for q in r["queued"]], [1, 2])
        # a theme: another cue that isn't there is refused; one that is goes in the plan
        self.assertIn("no cue m09", self.call(A.put_cue, {"ep": self.ep, "cue": {**spec, "id": "m02", "theme": {"cue": "m09", "take": 1}}}, 400)["error"])
        self.call(A.put_cue, {"ep": self.ep, "cue": {**spec, "id": "m02", "theme": {"cue": "m01", "take": 1}}})
        got = self.call(A.get_cue, {"ep": self.ep, "pass": "final", "cue": "m02"})
        self.assertEqual(got["spec"]["theme"], {"cue": "m01", "take": 1})
        self.assertEqual(set(got["plan"]["theme"]), {"spec", "label", "use", "warning"})
        self.assertIn("isn't finished", got["plan"]["warnings"][0])


if __name__ == "__main__":
    unittest.main()
