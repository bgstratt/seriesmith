"""
The episode's mix (seriesmith/mix.py, docs/SOUND.md): mix.json's stored form, anchors
placed against an assembled cut, ducking, loops, and real assembles where the effects,
ambience and music tracks go under the cut's own sound, with stems beside it.

The assemble tests build tiny episodes with ffmpeg (test_phase9d's fixtures) and are
skipped when ffmpeg/ffprobe isn't there.
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
from seriesmith import api as A  # noqa: E402
from seriesmith import mix as MX  # noqa: E402
from seriesmith import takes as T  # noqa: E402
from seriesmith import ff as FF  # noqa: E402
import test_api  # noqa: E402
from test_api import ApiTest  # noqa: E402
from test_phase9b import steps_wav  # noqa: E402
from test_phase9d import make_clip, probe_frames, tone_wav  # noqa: E402

HAVE_FF = bool(FF.have("ffmpeg") and FF.have("ffprobe"))
FPS = 24


def tearDownModule():
    test_api.tearDownModule()


def anchor(shot: str, frame: int = 0) -> dict:
    return {"shot": shot, "frame": frame}


class CheckTest(unittest.TestCase):
    def item(self, **kw) -> dict:
        return {"id": "m01", "track": "music", "path": "sound/m01.wav",
                "in": anchor("sh010"), **kw}

    def test_empty_is_empty(self):
        self.assertEqual(MX.check(None), {})
        self.assertEqual(MX.check({}), {})
        self.assertFalse(MX.active({}))

    def test_defaults_dropped(self):
        got = MX.check({"tracks": {"music": {"gain_db": 0, "duck_db": -9}},
                        "items": [self.item(gain_db=0, offset=0, fade_in=0, loop=False)],
                        "duck": {"threshold_db": -45}, "loudness": {"target_lufs": -16}})
        self.assertEqual(got, {"items": [{"id": "m01", "track": "music",
                                          "path": "sound/m01.wav",
                                          "in": {"shot": "sh010", "frame": 0}}]})
        self.assertTrue(MX.active(got))

    def test_a_track_level_alone_is_a_mix(self):
        self.assertTrue(MX.active(MX.check({"tracks": {"dialogue": {"gain_db": -3}}})))
        self.assertTrue(MX.active(MX.check({"tracks": {"music": {"mute": True}}})))

    def test_refusals(self):
        bad = [
            {"items": [self.item(track="drums")]},
            {"items": [self.item(path="")]},
            {"items": [self.item(**{"in": {"shot": "sh010", "frame": -1}})]},
            {"items": [self.item(gain_db=20)]},
            {"items": [self.item(fade_in=2.5)]},
            {"items": [self.item(), self.item()]},                 # two m01s
            {"items": [self.item(colour="red")]},
            {"tracks": {"dialogue": {"duck_db": -6}}},
            {"tracks": {"drums": {}}},
            {"regions": [{"from": anchor("sh010"), "to": anchor("sh020"), "music_duck_db": 3}]},
            {"loudness": {"target_lufs": -60}},
            {"hits": [{"id": "has space", "at": anchor("sh010")}]},
            {"sidechain": True},
        ]
        for raw in bad:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                MX.check(raw)

    def test_paths_use_slashes(self):
        got = MX.check({"items": [self.item(path="sound\\m01\\t01.wav")]})
        self.assertEqual(got["items"][0]["path"], "sound/m01/t01.wav")

    def test_round_trip_and_series_defaults(self):
        with tempfile.TemporaryDirectory() as root:
            MX.save(root, {"final": {"tracks": {"music": {"gain_db": -4}}}})
            self.assertEqual(MX.load(root)["proxy"], {})
            got = MX.for_pass(root, "final", {"sound": {
                "tracks": {"music": {"gain_db": -2, "duck_db": -12}, "ambience": {"gain_db": -8}},
                "loudness": {"target_lufs": -14}}})
            # the episode's level beats the series', the series' depth stays
            self.assertEqual(got["tracks"]["music"], {"gain_db": -4, "duck_db": -12})
            self.assertEqual(got["tracks"]["ambience"], {"gain_db": -8})
            self.assertEqual(got["loudness"], {"target_lufs": -14})


class AnchorTest(unittest.TestCase):
    def test_origins_follow_trims_and_dissolves(self):
        plan = [{"id": "sh010", "trim_in": 0, "used": 48},
                {"id": "sh020", "trim_in": 10, "used": 30, "dissolve_in": 12},
                {"id": "sh030", "trim_in": 0, "used": 24}]
        o = MX.shot_origins(plan)
        self.assertEqual(o["sh010"]["origin"], 0)
        # sh020 starts 12 frames early (the dissolve) and its frame 10 plays first
        self.assertEqual(MX.place(anchor("sh020", 10), o), 36)
        self.assertEqual(MX.place(anchor("sh020", 0), o), 26)
        self.assertEqual(MX.place(anchor("sh030", 5), o), 71)
        self.assertIsNone(MX.place(anchor("sh999"), o))


@unittest.skipUnless(HAVE_FF, "ffmpeg/ffprobe not on PATH")
class CurveTest(unittest.TestCase):
    def test_speech_curve_rises_and_falls(self):
        np = MX._np()
        sig = np.zeros((MX.RATE * 2, 2), dtype=np.float32)
        sig[MX.RATE // 2: MX.RATE] = 0.3                   # half a second of "speech"
        c = MX.speech_curve(sig, MX.DUCK)
        w = MX.WINDOW_S
        self.assertLess(c[int(0.4 / w)], 0.01)              # before it
        self.assertGreater(c[int(0.95 / w)], 0.95)          # well into it
        self.assertGreater(c[int(1.1 / w)], 0.5)            # released slowly
        self.assertLess(c[int(1.9 / w)], 0.2)

    def test_loop_fills_with_crossfades(self):
        np = MX._np()
        src = np.ones((MX.RATE, 2), dtype=np.float32)
        out = MX.looped(src, MX.RATE * 3)
        self.assertEqual(len(out), MX.RATE * 3)
        # a crossfade of two ones is one: no dip and no bump at the seams
        self.assertTrue(np.allclose(out[MX.RATE // 4: -MX.RATE // 4], 1.0, atol=1e-3))


@unittest.skipUnless(HAVE_FF, "ffmpeg/ffprobe not on PATH")
class AssembleMixTest(unittest.TestCase):
    """Two one-second clips: sh010 mute, sh020 a loud tone (its "dialogue"). A tone file is
    the music. Each test writes a mix and reads the stems and the cut back."""

    @classmethod
    def setUpClass(cls):
        cls._cache = tempfile.TemporaryDirectory()
        cls.tone = os.path.join(cls._cache.name, "tone.wav")
        tone_wav(cls.tone, 1.0, amp=20000)
        cls.long_tone = os.path.join(cls._cache.name, "long.wav")
        tone_wav(cls.long_tone, 2.0, amp=8000)
        cls.mute = os.path.join(cls._cache.name, "mute.mp4")
        cls.loud = os.path.join(cls._cache.name, "loud.mp4")
        make_clip(cls.mute, 24)
        make_clip(cls.loud, 24, wav=cls.tone)

    @classmethod
    def tearDownClass(cls):
        cls._cache.cleanup()

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        T.write_json(os.path.join(self.root, "shotlist", "shotlist.json"),
                     {"episode": "ep01", "defaults": {"width": 64, "height": 64},
                      "shots": [{"id": "sh010", "length": 24, "audio_policy": "keep"},
                                {"id": "sh020", "length": 24, "audio_policy": "keep"}]})
        for shot, clip in (("sh010", self.mute), ("sh020", self.loud)):
            t = T.reserve_take(self.root, "final", shot, {"status": "queued"})
            shutil.copy(clip, t.paths.mp4)
            T.update_sidecar(t.paths.sidecar, status="ok", frames=probe_frames(clip))
        os.makedirs(os.path.join(self.root, "sound"))
        shutil.copy(self.long_tone, os.path.join(self.root, "sound", "score.wav"))

    def tearDown(self):
        self._tmp.cleanup()

    def assemble(self, *args: str) -> str:
        r = subprocess.run([sys.executable, "-m", "seriesmith.assemble", "-o", self.root, *args],
                           capture_output=True, text=True, encoding="utf-8", timeout=600)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout

    @property
    def out(self) -> str:
        return os.path.join(self.root, "renders", "ep01.mp4")

    def stem(self, name: str):
        return MX.decode(os.path.join(self.root, "renders", "ep01_stems", f"{name}.wav"))

    def level(self, buf, a: float, b: float) -> float:
        """RMS of a stretch, in dB (very low for silence)."""
        np = MX._np()
        seg = buf[int(a * MX.RATE): int(b * MX.RATE)]
        return float(20 * np.log10(np.sqrt(np.mean(seg ** 2)) + 1e-9))

    def music(self, **kw) -> dict:
        return {"id": "m01", "track": "music", "path": "sound/score.wav",
                "in": anchor("sh010"), "out": anchor("sh020", 24), **kw}

    def test_no_mix_leaves_the_cut_alone(self):
        self.assemble()
        self.assertFalse(os.path.isdir(os.path.join(self.root, "renders", "ep01_stems")))

    def test_music_under_the_cut_with_stems(self):
        MX.save(self.root, {"final": {"items": [self.music()]}})
        out = self.assemble()
        self.assertIn("1 item(s)", out)
        self.assertEqual(probe_frames(self.out), 48)
        music, dialogue = self.stem("music"), self.stem("dialogue")
        self.assertGreater(self.level(music, 0.1, 0.9), -40)        # the score under sh010
        self.assertLess(self.level(dialogue, 0.1, 0.9), -80)       # sh010 is mute
        self.assertGreater(self.level(dialogue, 1.1, 1.9), -40)
        me = self.stem("me")
        self.assertAlmostEqual(self.level(me, 0.1, 0.9), self.level(music, 0.1, 0.9), delta=0.5)
        # the cut's sound is the mix: sound where only the music plays
        self.assertGreater(self.level(MX.decode(self.out), 0.1, 0.9), -50)

    def test_music_ducks_under_dialogue(self):
        MX.save(self.root, {"final": {"items": [self.music()]}})
        self.assemble()
        music = self.stem("music")
        dip = self.level(music, 0.2, 0.9) - self.level(music, 1.5, 1.9)
        self.assertAlmostEqual(dip, 9.0, delta=1.5)

    def test_score_forward_region_holds_the_music(self):
        MX.save(self.root, {"final": {"items": [self.music()], "regions": [
            {"from": anchor("sh020"), "to": anchor("sh020", 24),
             "music_duck_db": 0, "dialogue_db": -6}]}})
        self.assemble()
        music = self.stem("music")
        self.assertAlmostEqual(self.level(music, 0.2, 0.9), self.level(music, 1.5, 1.9),
                               delta=1.0)

    def test_anchor_moves_with_its_shot(self):
        # a one-second item on sh010; the cut plays sh020 first, so it lands in the 2nd second
        MX.save(self.root, {"final": {"items": [self.music(out=anchor("sh010", 24))]}})
        T.save_cut(self.root, {"final": [{"shot": "sh020"}, {"shot": "sh010"}], "proxy": []})
        self.assemble()
        music = self.stem("music")
        self.assertLess(self.level(music, 0.1, 0.9), -80)
        self.assertGreater(self.level(music, 1.1, 1.9), -40)

    def test_muted_track_and_missing_shot(self):
        MX.save(self.root, {"final": {
            "tracks": {"music": {"mute": True}},
            "items": [self.music(), self.music(id="m02", **{"in": anchor("sh999")})]}})
        out = self.assemble()
        self.assertIn("m02: sh999 isn't in the cut; left out", out)
        self.assertLess(self.level(self.stem("music"), 0.1, 1.9), -80)

    def test_loudness_target(self):
        MX.save(self.root, {"final": {"items": [self.music()],
                                      "loudness": {"target_lufs": -20}}})
        self.assemble()
        mix = os.path.join(self.root, "renders", "ep01_stems", "mix.wav")
        m = MX.measure(mix, -20, -1)
        self.assertAlmostEqual(m["input_i"], -20, delta=1.0)

    def test_xml_carries_the_tracks(self):
        import xml.etree.ElementTree as ET
        MX.save(self.root, {"final": {
            "tracks": {"music": {"gain_db": -6}},
            "items": [self.music(points=[{"at": anchor("sh020", 0), "db": 0},
                                         {"at": anchor("sh020", 12), "db": 6}],
                                 fade_out=12)],
            "hits": [{"id": "h1", "name": "the door", "at": anchor("sh020", 6)}]}})
        out = self.assemble("--xml")
        self.assertIn("1 item(s) on their own tracks, 1 hit(s) as markers", out)
        doc = ET.parse(os.path.join(self.root, "renders", "ep01.xml")).getroot()
        tracks = doc.findall("./sequence/media/audio/track")
        self.assertEqual(len(tracks), 4)                         # A1/A2 clips, A3/A4 music
        music = tracks[2].findall("clipitem")
        self.assertEqual([m.findtext("name") for m in music], ["score.wav"])
        self.assertEqual((music[0].findtext("start"), music[0].findtext("end")), ("0", "48"))
        level = music[0].find("./filter/effect/parameter")
        self.assertAlmostEqual(float(level.findtext("value")), 0.50119, places=4)   # -6 dB
        whens = [(k.findtext("when"), float(k.findtext("value")))
                 for k in level.findall("keyframe")]
        self.assertEqual([w for w, _ in whens], ["24", "36"])
        self.assertAlmostEqual(whens[1][1], 1.0, places=3)       # -6 + 6 dB
        self.assertEqual(len(tracks[2].findall("transitionitem")), 1)
        names = [m.findtext("name") for m in doc.findall("./sequence/marker")]
        self.assertIn("the door", names)

    def test_no_mix_flag(self):
        MX.save(self.root, {"final": {"items": [self.music()]}})
        out = self.assemble("--no-mix")
        self.assertNotIn("sound:", out)


class RouteTest(ApiTest):
    """GET / PUT /seriesmith/mix on test_api's built kitchen_sink episode."""

    def put(self, mix, status=200, pass_="final"):
        res = A.put_mix(self.ctx, {"ep": self.ep, "pass": pass_, "mix": mix})
        return self.ok(res)["mix"] if status == 200 else self.err(res, status)

    def score(self, rel="audio/score.wav"):
        steps_wav(os.path.join(self.ep, *rel.split("/")), [6000])
        return rel

    def item(self, **kw):
        return {"id": "m01", "track": "music", "path": self.score(), "in": anchor("sh010"),
                **kw}

    def test_get_empty_with_defaults(self):
        got = self.ok(A.get_mix(self.ctx, {"ep": self.ep, "pass": "final"}))
        self.assertEqual(got["mix"], {})
        self.assertEqual(got["defaults"]["tracks"], list(MX.TRACKS))
        self.assertEqual(got["defaults"]["loudness"], MX.LOUDNESS)

    def test_put_round_trip_and_history(self):
        got = self.put({"items": [self.item(gain_db=-3)], "tracks": {"music": {"gain_db": 0}}})
        self.assertEqual(got["items"][0]["gain_db"], -3)
        self.assertNotIn("tracks", got)                         # defaults dropped
        self.assertEqual(MX.load(self.ep)["final"], got)
        self.assertEqual(MX.load(self.ep)["proxy"], {})
        self.put({"items": [self.item(gain_db=-6)]})
        hist = os.path.join(self.ep, "_history")
        self.assertTrue(any(f.startswith(MX.MIX_FILE) for f in os.listdir(hist)))
        back = self.ok(A.get_mix(self.ctx, {"ep": self.ep, "pass": "final"}))["mix"]
        self.assertEqual(back["items"][0]["gain_db"], -6)

    def test_put_refusals(self):
        self.assertIn("track must be one of", self.put({"items": [self.item(track="x")]}, 400))
        self.assertIn("no file", self.put({"items": [self.item(path="audio/none.wav")]}, 404))
        self.assertIn("stay inside", self.put({"items": [self.item(path="../x.wav")]}, 400))
        self.assertIn("unknown mix field", self.put({"bus": {}}, 400))
        self.assertEqual(MX.load(self.ep)["final"], {})          # nothing written


if __name__ == "__main__":
    unittest.main()
