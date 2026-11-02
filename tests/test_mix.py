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
        got = MX.check({"items": [self.item(gain_db=0, offset=0, fade_in=0, loop=False)],
                        "duck": {"threshold_db": -45}, "loudness": {"target_lufs": -16}})
        self.assertEqual(got, {"items": [{"id": "m01", "track": "music",
                                          "path": "sound/m01.wav",
                                          "in": {"shot": "sh010", "frame": 0}}]})
        self.assertTrue(MX.active(got))

    def test_track_values_kept_as_given(self):
        # a 0 dB fader or an unmute overrides the series config's value
        got = MX.check({"tracks": {"music": {"gain_db": 0, "mute": False, "duck_db": -9}}})
        self.assertEqual(got["tracks"]["music"], {"gain_db": 0, "mute": False, "duck_db": -9})
        self.assertFalse(MX.active(got))
        with tempfile.TemporaryDirectory() as root:
            MX.save(root, {"final": got})
            eff = MX.for_pass(root, "final", {"sound": {"tracks": {"music": {"gain_db": -2,
                                                                            "mute": True}}}})
            self.assertEqual(eff["tracks"]["music"]["gain_db"], 0)
            self.assertFalse(eff["tracks"]["music"]["mute"])

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
            {"hits": [{"id": "h1", "at": anchor("sh010"), "kind": "swell"}]},
            {"hits": [{"id": "h1", "at": anchor("sh010"), "must": "yes"}]},
            {"sidechain": True},
        ]
        for raw in bad:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                MX.check(raw)

    def test_hit_kinds(self):
        got = MX.check({"hits": [
            {"id": "h1", "at": anchor("sh010"), "kind": "accent", "must": True},
            {"id": "h2", "at": anchor("sh020", 4), "kind": "drop", "must": False, "name": "silence"}]})
        self.assertEqual(got["hits"], [
            {"id": "h1", "at": {"shot": "sh010", "frame": 0}},
            {"id": "h2", "at": {"shot": "sh020", "frame": 4}, "name": "silence", "kind": "drop",
             "must": False}])

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


class TrackListTest(unittest.TestCase):
    """Tracks of your own (docs/SOUND.md phase 6): the mix's own list, the four by default."""

    SONG = [{"id": "dialogue", "kind": "dialogue"}, {"id": "effects", "kind": "effects"},
            {"id": "ambience", "kind": "ambience"}, {"id": "music", "kind": "music", "label": "Score"},
            {"id": "song", "kind": "music", "label": "Song"}]

    def test_defaults_when_none(self):
        self.assertEqual(MX.track_ids({}), list(MX.TRACKS))
        self.assertEqual(MX.track_list({})[3], {"id": "music", "kind": "music", "label": "Music"})
        # the defaults written out are no list of its own
        self.assertEqual(MX.check({"track_list": [{"id": k, "kind": k, "label": MX.LABELS[k]}
                                                  for k in MX.TRACKS]}), {})

    def test_own_list_kept_and_used(self):
        got = MX.check({"track_list": self.SONG, "tracks": {"song": {"gain_db": 0, "duck_db": -3}},
                        "items": [{"id": "s1", "track": "song", "path": "a.wav", "in": anchor("sh010")}]})
        self.assertEqual(got["track_list"], self.SONG)
        self.assertEqual(MX.kinds(got)["song"], "music")
        self.assertEqual(MX.fader(got["tracks"], "song", "music"), 0)
        self.assertEqual(MX.fader({}, "song", "music"), -12.0)        # its kind's default
        # a renamed default, a track list without effects: the effects go nowhere
        got = MX.check({"track_list": [{"id": "dialogue", "kind": "dialogue", "label": "Lines"},
                                       {"id": "walla", "kind": "ambience"},
                                       {"id": "music", "kind": "music"}]})
        self.assertEqual(MX.track_list(got)[0]["label"], "Lines")
        self.assertIsNone(MX.fx_track(got))
        self.assertEqual(MX.bed_track(got), "walla")                  # the first of its kind

    def test_refusals(self):
        for bad, said in (
                ([{"id": "music", "kind": "music"}], "can't be taken out"),
                ([{"id": "dialogue", "kind": "dialogue"}, {"id": "me", "kind": "music"}], "me.wav"),
                ([{"id": "dialogue", "kind": "dialogue"}, {"id": "music", "kind": "effects"}], "of kind music"),
                ([{"id": "dialogue", "kind": "dialogue"}, {"id": "x", "kind": "score"}], "kind must be"),
                ([{"id": "dialogue", "kind": "dialogue"}, {"id": "x", "kind": "music"},
                  {"id": "x", "kind": "music"}], "two tracks"),
                ([{"id": "dialogue", "kind": "dialogue", "gain_db": 0}], "a track takes"),
                ([], "a list of tracks")):
            with self.subTest(said=said), self.assertRaises(ValueError) as e:
                MX.check({"track_list": bad})
            self.assertIn(said, str(e.exception))
        own = {"track_list": [{"id": "dialogue", "kind": "dialogue"}, {"id": "adr", "kind": "dialogue"}]}
        with self.assertRaises(ValueError) as e:
            MX.check({**own, "tracks": {"adr": {"duck_db": -3}}})
        self.assertIn("doesn't duck", str(e.exception))
        with self.assertRaises(ValueError) as e:                       # its items' track is gone
            MX.check({**own, "items": [{"id": "m1", "track": "music", "path": "a.wav", "in": anchor("sh010")}]})
        self.assertIn("track must be one of dialogue, adr", str(e.exception))

    def test_series_levels_for_its_own_tracks(self):
        with tempfile.TemporaryDirectory() as root:
            MX.save(root, {"final": {"track_list": self.SONG}})
            got = MX.for_pass(root, "final", {"sound": {"tracks": {"song": {"gain_db": -3},
                                                                   "nope": {"gain_db": 1}}}})
            self.assertEqual(got["tracks"], {"song": {"gain_db": -3}})


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
        src = np.random.default_rng(7).standard_normal((MX.RATE * 2, 2)).astype(np.float32) * 0.1
        out = MX.looped(src, MX.RATE * 6)
        self.assertEqual(len(out), MX.RATE * 6)
        # a bed (noise: its tail and head unalike) holds its level through the seams, where a
        # linear crossfade dipped 3 dB
        rms = lambda a: 20 * np.log10(np.sqrt(np.mean(a ** 2)))
        whole = rms(src)
        xf = int(MX.LOOP_XFADE_S * MX.RATE) if MX.LOOP_XFADE_S * MX.RATE <= len(src) // 4 else len(src) // 4
        seam = len(src) - xf // 2
        self.assertAlmostEqual(rms(out[seam - xf // 4: seam + xf // 4]), whole, delta=0.6)


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
        self.assertGreater(self.level(music, 1.1, 1.9), -55)

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

    def test_loudness_checked_on_the_export(self):
        """docs/SOUND.md phase 5: the export measured against the target, reported and kept
        beside it, never changed."""
        side = os.path.join(self.root, "renders", "ep01_loudness.json")
        MX.save(self.root, {"final": {"items": [self.music()], "loudness": {"target_lufs": -20}}})
        out = self.assemble()
        got = T.read_json(side)
        self.assertTrue(got["mixed"])
        self.assertEqual(got["target_lufs"], -20)
        self.assertAlmostEqual(got["integrated_lufs"], -20, delta=1.0)
        self.assertTrue(got["on_target"])
        self.assertIn("loudness: ", out)
        self.assertIn("LUFS integrated (on the -20 target)", out)
        # no mix: the cut's own sound, measured as it came, against the default target
        MX.save(self.root, {"final": {}})
        out = self.assemble()
        got = T.read_json(side)
        self.assertFalse(got["mixed"])
        self.assertEqual(got["target_lufs"], MX.LOUDNESS["target_lufs"])
        self.assertEqual(got["off_lu"], round(got["integrated_lufs"] - got["target_lufs"], 1))
        if not got["on_target"]:
            self.assertIn("! loudness:", out)
            self.assertIn("no mix brings it to the target", out)
        st = os.stat(self.out)
        self.assertIsNotNone(MX.loudness_check(self.out, MX.LOUDNESS, False))
        self.assertEqual((os.stat(self.out).st_mtime, os.stat(self.out).st_size), (st.st_mtime, st.st_size))
        # --audio none: nothing to measure, and no stale report left
        self.assemble("--audio", "none")
        self.assertFalse(os.path.isfile(side))

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

    def test_tracks_of_its_own(self):
        """docs/SOUND.md phase 6: a second music track under the score and an ADR track of the
        dialogue kind, each its own stem; the M&E all but the dialogue kind; the XML a pair
        each in the mix's order."""
        import xml.etree.ElementTree as ET
        stems = os.path.join(self.root, "renders", "ep01_stems")
        os.makedirs(stems, exist_ok=True)
        with open(os.path.join(stems, "old.wav"), "wb") as fh:      # a track that's gone
            fh.write(b"RIFF")
        song = self.music(id="s1", track="song", out=anchor("sh010", 24))
        adr = self.music(id="d1", track="adr", **{"in": anchor("sh020"), "out": anchor("sh020", 24)})
        mix = {"track_list": [{"id": "dialogue", "kind": "dialogue"}, {"id": "adr", "kind": "dialogue"},
                              {"id": "music", "kind": "music"}, {"id": "song", "kind": "music"}],
               "tracks": {"song": {"gain_db": 0}}, "items": [self.music(), song, adr]}
        MX.save(self.root, {"final": mix})
        self.assemble()
        self.assertEqual(sorted(os.listdir(stems)),
                         ["adr.wav", "dialogue.wav", "me.wav", "mix.wav", "music.wav", "song.wav"])
        song_stem, adr_stem, me = self.stem("song"), self.stem("adr"), self.stem("me")
        self.assertGreater(self.level(song_stem, 0.1, 0.9), -40)     # under sh010
        self.assertLess(self.level(song_stem, 1.1, 1.9), -80)
        self.assertGreater(self.level(adr_stem, 1.1, 1.9), -40)
        # the M&E: the two music tracks, not the ADR
        music = self.stem("music")
        np = MX._np()
        self.assertLess(float(np.max(np.abs(me - (music + song_stem)))), 1e-3)
        # the XML: A1/A2 the clips, then adr, music, song a pair each
        out = self.assemble("--xml")
        self.assertIn("3 item(s) on their own tracks", out)
        doc = ET.parse(os.path.join(self.root, "renders", "ep01.xml")).getroot()
        tracks = doc.findall("./sequence/media/audio/track")
        self.assertEqual(len(tracks), 8)
        # (the tone is mono: the first of each pair)
        self.assertEqual([len(t.findall("clipitem")) for t in tracks[2:]], [1, 0, 1, 0, 1, 0])
        self.assertEqual((tracks[2].find("clipitem").findtext("start"),
                          tracks[6].find("clipitem").findtext("end")), ("24", "24"))

    def test_music_fader_defaults_to_minus_12(self):
        MX.save(self.root, {"final": {"items": [self.music()], "tracks": {"music": {"gain_db": 0}}}})
        # against the dialogue: the stems carry the mix's loudness gain, which moves with it
        rel = lambda: self.level(self.stem("dialogue"), 1.1, 1.9) - self.level(self.stem("music"), 0.1, 0.9)  # noqa: E731
        self.assemble()
        at0 = rel()
        MX.save(self.root, {"final": {"items": [self.music()]}})
        self.assemble()
        self.assertAlmostEqual(rel() - at0, 12.0, delta=0.5)

    def test_speech_curve_of_the_cut(self):
        from seriesmith import cue as CU
        layout, fps = CU.cut_layout(self.root, "final")
        self.assertEqual([x["sound"] is not None for x in layout], [False, True])   # sh010 is mute
        curve = MX.speech_of(layout, fps)
        self.assertEqual(len(curve), round(2.0 / MX.SPEECH_STEP))
        half = len(curve) // 2
        self.assertLess(max(curve[: half - 2]), 0.05)            # nobody speaks over sh010
        self.assertGreater(min(curve[half + 4: -2]), 0.9)        # the tone, eased in

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

    def test_duck_curve(self):
        got = self.ok(A.get_mix_duck(self.ctx, {"ep": self.ep, "pass": "final"}))
        self.assertEqual(got["step"], MX.SPEECH_STEP)
        self.assertIsInstance(got["curve"], list)

    def test_beats_of_the_music(self):
        """GET /seriesmith/mix/beats: a cue take's grid from its sidecar, a song's measured
        and kept beside it (docs/SOUND.md phase 5)."""
        from test_beats import clicks
        from seriesmith import cue as CU
        from seriesmith.core import fileio as FIO
        song = os.path.join(self.ep, "audio", "song.wav")
        os.makedirs(os.path.dirname(song), exist_ok=True)
        MX.write_wav(song, clicks(120.0, 12, offset=0.5))
        d = CU.cue_dir(self.ep, "m02")
        os.makedirs(d, exist_ok=True)
        steps_wav(os.path.join(d, "t01.wav"), [6000])
        FIO.write_json(os.path.join(d, "t01.json"), {"status": "ok", "plan": {"fit": {"bpm": 96.0}},
                                                     "measured": {"downbeat": 1.4}})
        self.put({"items": [
            {"id": "song", "track": "music", "path": "audio/song.wav", "in": anchor("sh010")},
            {"id": "m02", "track": "music", "path": "sound/m02/t01.wav", "in": anchor("sh010")},
            {"id": "a01", "track": "ambience", "path": self.score(), "in": anchor("sh010")}]})
        got = self.ok(A.get_mix_beats(self.ctx, {"ep": self.ep, "pass": "final"}))
        self.assertEqual([i["id"] for i in got["items"]], ["song", "m02"])     # music only
        g = got["items"][0]["grid"]
        self.assertEqual(g["source"], "measured")
        self.assertAlmostEqual(g["bpm"], 120.0, delta=0.5)
        self.assertAlmostEqual(g["downbeat"], 0.5, delta=1 / 24)
        self.assertTrue(os.path.isfile(song + ".beats.json"))
        cue = got["items"][1]["grid"]
        self.assertEqual(cue["source"], "cue")
        self.assertEqual(cue["bpm"], 96.0)
        self.assertEqual(cue["downbeat"], 1.4)
        self.assertAlmostEqual(cue["first"], 1.4 - 2 * 0.625, places=4)    # two beats before it
        self.assertEqual(got["recording"]["path"], "audio/ks01_mix.wav")       # the recording, whose
        self.assertFalse((got["recording"]["grid"] or {}).get("steady"))    # tone has no beat

    def test_get_empty_with_defaults(self):
        got = self.ok(A.get_mix(self.ctx, {"ep": self.ep, "pass": "final"}))
        self.assertEqual(got["defaults"]["gain_db"]["music"], -12.0)
        self.assertEqual(got["mix"], {})
        self.assertEqual(got["defaults"]["tracks"], list(MX.TRACKS))
        self.assertEqual(got["defaults"]["loudness"], MX.LOUDNESS)

    def test_put_round_trip_and_history(self):
        got = self.put({"items": [self.item(gain_db=-3, fade_in=0)]})
        self.assertEqual(got["items"][0]["gain_db"], -3)
        self.assertNotIn("fade_in", got["items"][0])            # defaults dropped
        files = self.ok(A.get_mix(self.ctx, {"ep": self.ep, "pass": "final"}))["files"]
        self.assertGreater(files["audio/score.wav"], 0)          # its length, for the lane
        self.assertEqual(MX.load(self.ep)["final"], got)
        self.assertEqual(MX.load(self.ep)["proxy"], {})
        self.put({"items": [self.item(gain_db=-6)]})
        hist = os.path.join(self.ep, "_history")
        self.assertTrue(any(f.startswith(MX.MIX_FILE) for f in os.listdir(hist)))
        back = self.ok(A.get_mix(self.ctx, {"ep": self.ep, "pass": "final"}))["mix"]
        self.assertEqual(back["items"][0]["gain_db"], -6)

    def test_track_list_through_the_routes(self):
        own = [{"id": "dialogue", "kind": "dialogue"}, {"id": "music", "kind": "music", "label": "Score"},
               {"id": "song", "kind": "music", "label": "Song"}]
        got = self.put({"track_list": own, "items": [self.item(track="song")]})
        self.assertEqual(got["track_list"], own)
        res = self.ok(A.get_mix(self.ctx, {"ep": self.ep, "pass": "final"}))
        self.assertEqual([t["id"] for t in res["track_list"]], ["dialogue", "music", "song"])
        self.assertEqual(res["track_list"][1]["label"], "Score")
        self.assertEqual(res["defaults"]["labels"]["effects"], "Effects")
        # a track taken out with its items still on it: refused, nothing written
        self.assertIn("track must be one of", self.put({"track_list": own[:2], "items": [self.item(track="song")]}, 400))
        self.assertEqual(MX.load(self.ep)["final"]["track_list"], own)
        # a cue placed again keeps the track it was moved to
        from seriesmith import cue as CU
        self.assertEqual(CU.MX.first_of({"track_list": own}, "music"), "music")
        self.assertIsNone(CU.MX.first_of({"track_list": own[:1]}, "music"))

    def test_put_refusals(self):
        self.assertIn("track must be one of", self.put({"items": [self.item(track="x")]}, 400))
        self.assertIn("no file", self.put({"items": [self.item(path="audio/none.wav")]}, 404))
        self.assertIn("stay inside", self.put({"items": [self.item(path="../x.wav")]}, 400))
        self.assertIn("unknown mix field", self.put({"bus": {}}, 400))
        self.assertEqual(MX.load(self.ep)["final"], {})          # nothing written


if __name__ == "__main__":
    unittest.main()
