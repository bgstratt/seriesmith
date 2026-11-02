"""
A place's ambience bed (docs/SOUND.md phase 3): the series config's `ambience` and
`ambience_bed` by place (core.series_config), the `ambience` target kind, the bed as a ref
(refs.py `ambience:<place>`), refs_todo's beds (build), a take finished as it lands
(ambience.finish_bed), and the beds laid under the cut: runs, the mix's `beds`, the
render's ambience stem and the XML's ambience lane.

The render tests build tiny episodes with ffmpeg and are skipped without it.
"""
from __future__ import annotations

import json
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
from seriesmith import ambience as AMB  # noqa: E402
from seriesmith import ff as FF  # noqa: E402
from seriesmith import mix as MX  # noqa: E402
from seriesmith import refs as R  # noqa: E402
from seriesmith import takes as T  # noqa: E402
from seriesmith import targets as TG  # noqa: E402
from seriesmith.core import series_config as SC  # noqa: E402
from test_phase9d import make_clip, probe_frames, tone_wav  # noqa: E402

HAVE_FF = bool(FF.have("ffmpeg") and FF.have("ffprobe"))
DINER = "Room tone of a small roadside diner at night: a refrigerator hum"


def config(**locs) -> dict:
    return {"series": {"id": "t", "title": "T"}, "style": {"look": "film"}, "subjects": {},
            "locations": locs}


class PlaceTest(unittest.TestCase):
    def cfg(self):
        return SC.series_config_from(config(
            diner={"description": "a diner", "plate": "../refs/_bg/diner.png", "ambience": DINER},
            booth={"description": "the booth", "of": "diner"},
            booth_dusk={"description": "the booth at dusk", "of": "booth", "relight": "dusk"},
            hall={"description": "a hall", "plate": "refs/_bg/hall.png"},
            hall_gold={"description": "the hall at golden hour", "of": "hall",
                       "ambience": "evening birds"},
            yard={"description": "a yard", "ambience_bed": "sound/yard.wav"}))

    def test_a_variant_plays_its_place_bed(self):
        cfg = self.cfg()
        for lid in ("diner", "booth", "booth_dusk"):
            b = SC.ambience_bed_of(cfg, lid)
            self.assertEqual((b["id"], b["path"], b["words"]), ("diner", "../refs/_amb/diner.wav", DINER))

    def test_a_place_without_words_is_its_master(self):
        cfg = SC.series_config_from(config(
            hall={"description": "a hall", "name": "The Hall"},
            hall_door={"description": "the door", "of": "hall"},
            hall_gold={"description": "golden", "of": "hall", "ambience": "evening birds"}))
        lay = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        from unittest import mock
        with mock.patch.object(AMB, "shot_locations", return_value={"a": "hall_door", "b": "hall_gold", "c": ""}):
            self.assertEqual(AMB.places("x", lay, cfg), {
                "a": {"place": "hall", "name": "The Hall", "bed": False},
                "b": {"place": "hall_gold", "name": "hall_gold", "bed": True}})

    def test_nothing_is_automatic(self):
        self.assertIsNone(SC.ambience_bed_of(self.cfg(), "hall"))

    def test_a_variant_with_its_own_words_has_its_own_bed(self):
        b = SC.ambience_bed_of(self.cfg(), "hall_gold")
        self.assertEqual((b["id"], b["path"]), ("hall_gold", "refs/_amb/hall_gold.wav"))

    def test_a_file_without_words(self):
        b = SC.ambience_bed_of(self.cfg(), "yard")
        self.assertEqual((b["path"], b["words"]), ("sound/yard.wav", ""))

    def test_beds(self):
        beds = SC.ambience_beds(self.cfg())
        self.assertEqual(list(beds), ["diner", "hall_gold", "yard"])
        self.assertEqual(beds["diner"]["locations"], ["diner", "booth", "booth_dusk"])

    def test_checked(self):
        with self.assertRaises(ValueError):
            SC.series_config_from(config(x={"description": "x", "ambience": 3}))
        with self.assertRaises(ValueError):
            SC.series_config_from(config(x={"description": "x", "ambience_bed": " "}))


class TargetTest(unittest.TestCase):
    def test_the_kind_and_its_default(self):
        self.assertIn("ambience", TG.KINDS)
        self.assertEqual([t.id for t in TG.list_targets("ambience")],
                         ["mmaudio_ambience", "sa3_sfx_ambience"])
        self.assertEqual(TG.DEFAULT_TARGETS["ambience"], "mmaudio_ambience")

    def test_the_prompt(self):
        t = TG.load_target("mmaudio_ambience")
        got = t.ambience_prompt("Rain on a tin roof", 10)
        self.assertEqual(got["prompt"], "Rain on a tin roof. No music, no voices, no speech.")
        self.assertEqual(got["values"], {"seconds": 10.0})
        caps = t.capabilities()
        self.assertEqual((caps["default_seconds"], caps["mode"]), (10.0, "t2a"))
        self.assertEqual(TG.load_target("sa3_sfx_ambience").seconds_range()[0], 30.0)

    def test_every_file_has_a_download(self):
        for tid in ("mmaudio_ambience", "sa3_sfx_ambience"):
            t = TG.load_target(tid)
            for name in t.named_files():
                d = TG.download_for(t, name)
                self.assertTrue(d["url"] and d["folder"], (tid, name))


class RefTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.show = self._tmp.name
        self.ep = os.path.join(self.show, "ep01")
        os.makedirs(os.path.join(self.ep, "shotlist"))
        T.write_json(os.path.join(self.ep, "series.json"), config(
            diner={"description": "a diner", "plate": "../refs/_bg/diner.png", "ambience": DINER},
            booth={"description": "the booth", "of": "diner"},
            road={"description": "a road"}))
        T.write_json(os.path.join(self.ep, "shotlist", "shots.json"), {
            "episode": "ep01", "sequences": [
                {"id": "sq01", "location": "booth", "shots": [{"id": "sh010"}, {"id": "sh020"}]},
                {"id": "sq02", "location": "road", "shots": [{"id": "sh030"}]}]})

    def tearDown(self):
        self._tmp.cleanup()

    def test_listed_and_planned(self):
        s = R.load_series(self.ep)
        ref = R.find_ref(s, "ambience:diner")
        self.assertTrue(ref.is_audio)
        self.assertEqual(ref.file, os.path.join(self.show, "refs", "_amb", "diner.wav"))
        self.assertEqual(R.used_by(s, [ref])[ref.id]["final"], ["sh010", "sh020"])
        job = R.plan_generate(s, R.GenRequest("ambience:diner"))[0]
        self.assertEqual(job.target.id, "mmaudio_ambience")
        self.assertTrue(job.prompt.endswith("No music, no voices, no speech."))
        self.assertEqual(job.negative, "music, melody, singing, speech, talking, voices")
        self.assertEqual(job.values["seconds"], 10.0)
        self.assertEqual((job.seed, job.seed_source), (R.seed_for("ambience:diner"), "stable"))
        # not in the Refs tab's listing: the Ambience section's, takes fetched on opening
        self.assertNotIn("ambience:diner", [r["id"] for r in R.list_refs(self.ep)])
        beds = R.ambience_listing(self.ep)["beds"]
        self.assertEqual([(b["ref"], b["locations"], b["exists"]) for b in beds],
                         [("ambience:diner", ["diner", "booth"], False)])

    def test_another_target(self):
        s = R.load_series(self.ep)
        job = R.plan_generate(s, R.GenRequest("ambience:diner", target="sa3_sfx_ambience"))[0]
        self.assertEqual((job.values["seconds"], job.steps, job.negative_source), (30.0, 8, "none"))
        with self.assertRaises(R.RefError):
            R.plan_generate(s, R.GenRequest("ambience:diner", target="krea2"))

    def test_refs_todo(self):
        from seriesmith import build as B
        from seriesmith.core import ir
        s = R.load_series(self.ep)
        story = ir.Episode(id="ep01", sequences=[
            ir.Sequence(id="sq01", location="booth", shots=[ir.Shot(id="sh010")]),
            ir.Sequence(id="sq02", location="road", shots=[ir.Shot(id="sh020")])])
        rep = B.with_beds({"needed": {}, "blocked_shots": {}}, story, s.series_cfg)
        self.assertEqual(rep["needed"]["../refs/_amb/diner.wav"]["kind"], "ambience bed")
        self.assertEqual(rep["blocked_shots"]["../refs/_amb/diner.wav"], ["sh010"])


def layout(*shots):
    return [{"id": sid, "trim_in": 0, "used": n, "dissolve_in": 0} for sid, n in shots]


class RunsTest(unittest.TestCase):
    def test_runs_join_and_break(self):
        a, b = {"id": "a"}, {"id": "b"}
        got = AMB.runs(layout(("s1", 24), ("s2", 24), ("s3", 24), ("s4", 24), ("s5", 24)),
                       {"s1": a, "s2": a, "s3": None, "s4": b, "s5": a})
        self.assertEqual([(r["bed"]["id"], r["shots"], r["start"], r["end"]) for r in got],
                         [("a", ["s1", "s2"], 0, 48), ("b", ["s4"], 72, 96), ("a", ["s5"], 96, 120)])

    def test_check_keeps_only_changes(self):
        self.assertEqual(MX.check({"beds": {"diner": {"gain_db": 0, "mute": False}}}), {})
        self.assertEqual(MX.check({"beds": {"diner": {"gain_db": -3, "mute": True}}}),
                         {"beds": {"diner": {"gain_db": -3.0, "mute": True}}})
        with self.assertRaises(ValueError):
            MX.check({"beds": {"diner": {"level": 1}}})


@unittest.skipUnless(HAVE_FF, "ffmpeg/ffprobe not on PATH")
class RenderTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def level(self, buf, a, b):
        np = MX._np()
        seg = buf[int(a * MX.RATE): int(b * MX.RATE)]
        return float(20 * np.log10(np.sqrt(np.mean(seg ** 2)) + 1e-9))

    def test_finish_bed(self):
        src, dst = os.path.join(self.dir, "take.wav"), os.path.join(self.dir, "bed.wav")
        tone_wav(src, 8.0, amp=20000)
        got = AMB.finish_bed(src, dst)
        self.assertTrue(got["trimmed"])
        self.assertAlmostEqual(got["seconds"], 5.0, delta=0.01)
        self.assertAlmostEqual(MX.measure(dst, -32, -1)["input_i"], AMB.BED_LUFS, delta=0.5)
        tone_wav(src, 3.0, amp=20000)            # too short to lose its ends
        self.assertFalse(AMB.finish_bed(src, dst)["trimmed"])

    def test_beds_rendered(self):
        bed = os.path.join(self.dir, "bed.wav")
        tone_wav(bed, 0.7, amp=8000)
        beds = [{"place": "a", "path": bed, "exists": True, "start": 0, "end": 48, "gain_db": 0},
                {"place": "a", "path": bed, "exists": True, "start": 72, "end": 96, "gain_db": -6},
                {"place": "b", "path": bed, "exists": True, "start": 96, "end": 120, "mute": True}]
        buf = AMB.render_beds(beds, 120, 24.0, log=lambda *_: None)
        self.assertEqual(len(buf), 5 * MX.RATE)
        on = self.level(buf, 0.2, 1.7)
        self.assertGreater(on, -30)                         # looped past its 0.7 s
        self.assertLess(self.level(buf, 2.3, 2.7), -80)     # no bed
        self.assertAlmostEqual(self.level(buf, 3.3, 3.7), on - 6, delta=1.0)
        self.assertLess(self.level(buf, 4.3, 5.0), -80)     # muted
        lanes = AMB.bed_lanes(beds, lambda p: 17)
        self.assertEqual([(x["start"], x["end"]) for x in lanes][:3], [(0, 17), (17, 34), (34, 48)])


@unittest.skipUnless(HAVE_FF, "ffmpeg/ffprobe not on PATH")
class AssembleBedsTest(unittest.TestCase):
    """Two one-second clips in two sequences: sh010 in the diner (its bed a tone), sh020 on
    the road (no bed). No mix.json item: the bed alone makes the mix."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.show = self._tmp.name
        self.root = os.path.join(self.show, "ep01")
        mute = os.path.join(self.show, "mute.mp4")
        make_clip(mute, 24)
        T.write_json(os.path.join(self.root, "series.json"), config(
            diner={"description": "a diner", "plate": "../refs/_bg/diner.png", "ambience": DINER},
            road={"description": "a road"}))
        T.write_json(os.path.join(self.root, "shotlist", "shotlist.json"),
                     {"episode": "ep01", "defaults": {"width": 64, "height": 64},
                      "shots": [{"id": "sh010", "length": 24, "audio_policy": "keep"},
                                {"id": "sh020", "length": 24, "audio_policy": "keep"}]})
        T.write_json(os.path.join(self.root, "shotlist", "shots.json"), {
            "episode": "ep01", "sequences": [
                {"id": "sq01", "location": "diner", "shots": [{"id": "sh010"}]},
                {"id": "sq02", "location": "road", "shots": [{"id": "sh020"}]}]})
        for shot in ("sh010", "sh020"):
            t = T.reserve_take(self.root, "final", shot, {"status": "queued"})
            shutil.copy(mute, t.paths.mp4)
            T.update_sidecar(t.paths.sidecar, status="ok", frames=probe_frames(mute))
        tone_wav(os.path.join(self.show, "refs", "_amb", "diner.wav"), 0.6, amp=8000)

    def tearDown(self):
        self._tmp.cleanup()

    def assemble(self, *args):
        r = subprocess.run([sys.executable, "-m", "seriesmith.assemble", "-o", self.root, *args],
                           capture_output=True, text=True, encoding="utf-8", timeout=600)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout

    def test_the_bed_under_its_shots_only(self):
        out = self.assemble()
        self.assertIn("1 ambience bed run(s) (diner)", out)
        amb = MX.decode(os.path.join(self.root, "renders", "ep01_stems", "ambience.wav"))
        np = MX._np()

        def level(a, b):
            seg = amb[int(a * MX.RATE): int(b * MX.RATE)]
            return float(20 * np.log10(np.sqrt(np.mean(seg ** 2)) + 1e-9))
        self.assertGreater(level(0.1, 0.7), -40)
        self.assertLess(level(1.3, 1.9), -80)

    def test_muted_place_is_no_mix(self):
        MX.save(self.root, {"final": {"beds": {"diner": {"mute": True}}}})
        self.assemble()
        self.assertFalse(os.path.isdir(os.path.join(self.root, "renders", "ep01_stems")))

    def test_xml_lane(self):
        self.assemble("--xml")
        xml = open(os.path.join(self.root, "renders", "ep01.xml"), encoding="utf-8").read()
        self.assertIn("diner.wav", xml)

    def test_get_mix_beds(self):
        from seriesmith import cue as CU
        from seriesmith import jobs as J
        lay, fps = CU.cut_layout(self.root, "final")
        beds = AMB.laid(self.root, lay, J.series_config(self.root), {})
        self.assertEqual([(b["place"], b["shots"], b["rel"], b["in"], b["out"]) for b in beds],
                         [("diner", ["sh010"], "../refs/_amb/diner.wav",
                           {"shot": "sh010", "frame": 0}, {"shot": "sh010", "frame": 24})])

    def test_get_mix_places(self):
        from seriesmith import cue as CU
        from seriesmith import jobs as J
        lay, _ = CU.cut_layout(self.root, "final")
        self.assertEqual(AMB.places(self.root, lay, J.series_config(self.root)),
                         {"sh010": {"place": "diner", "name": "diner", "bed": True},
                          "sh020": {"place": "road", "name": "road", "bed": False}})


if __name__ == "__main__":
    unittest.main()
