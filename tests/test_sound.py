"""
A shot's sound (overrides.json `sound`, takes.shot_sound): generate, clone, or
dub a track -- the recorded track's window, a take's sound (either pass), or
a generated dub track (jobs.RenderRequest.dub_track: the shot rendered tiny on
a voice model for its sound only, kept in <episode>/dub/<shot>/). A dub of a
file is the shot's own recording, levelled (jobs.apply_sound): H3 FL2VA
anchors it, LTX holds it, H3 Ref2VA / FastH3 Omni's Shot Loader reads it.

Run:  python -m pytest tests/test_sound.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
from seriesmith import api as A  # noqa: E402
from seriesmith import edit as E  # noqa: E402
from seriesmith import ff as FF  # noqa: E402
from seriesmith import jobs as J  # noqa: E402
from seriesmith import takes as T  # noqa: E402
from seriesmith.targets.graph import of  # noqa: E402
from test_render import FIXTURE, FakeComfy, build_episode, wav_bytes  # noqa: E402

FL = "minimax_h3_fl2va"
WF = os.path.join(HERE, "fixtures", "workflows")
FL_INFO = json.load(open(os.path.join(WF, "object_info_h3_fl2va.json"), encoding="utf-8"))


class SoundTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.src = os.path.join(cls._tmp.name, "ks01")
        os.makedirs(cls.src)
        build_episode(cls.src)
        shutil.copy(os.path.join(FIXTURE, "series.json"), cls.src)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.root = os.path.join(self._t.name, "ks01")
        shutil.copytree(self.src, self.root)

    def tearDown(self):
        self._t.cleanup()

    def plan(self, sid, pass_="final", **req):
        doc, i = J.find_shot(self.root, pass_, sid)
        return J.plan_job(self.root, pass_, doc, i, J.RenderRequest(sid, **req),
                          T.load_overrides(self.root))

    def sound(self, sid, sound):
        E.set_sound(self.root, [sid], sound)

    def finished(self, sid="sh020", pass_="final", folder=None, **sc):
        """A finished take with sound on disk (in `folder`: a dub track)."""
        t = T.reserve_take(self.root, pass_, sid, {"status": "ok", **sc}, None, folder)
        with open(t.paths.mp4, "wb") as fh:
            fh.write(b"not really a video")
        with open(t.paths.h3_wav, "wb") as fh:
            fh.write(wav_bytes(2.0, freq=300.0))
        return t

    # -- the setting -------------------------------------------------------

    def test_the_setting_is_checked_and_kept_apart_from_the_target_blocks(self):
        self.sound("sh020", {"mode": "dub", "dub": {"from": "take", "pass": "proxy", "take": 2}})
        ov = T.load_overrides(self.root)
        self.assertEqual(ov["sound"]["sh020"], {"mode": "dub", "dub": {"from": "take", "pass": "proxy", "take": 2}})
        self.assertNotIn("sh020", ov.get("shots", {}))
        for bad in ({"mode": "loud"}, {"mode": "dub"}, {"mode": "dub", "dub": {"from": "take", "take": 2}},
                    {"mode": "dub", "dub": {"from": "dub", "take": 0}}):
            with self.assertRaises(ValueError):
                T.check_sound(bad)
        with self.assertRaises(ValueError):                    # a take is one shot's
            E.set_sound(self.root, ["sh020", "sh030"], {"mode": "dub", "dub": {"from": "dub", "take": 1}})
        self.sound("sh020", None)
        self.assertNotIn("sound", T.load_overrides(self.root))

    # -- dub tracks --------------------------------------------------------

    def test_a_dub_track_is_tiny_ref2va_cloning_kept_in_the_dub_folder(self):
        job = self.plan("sh020", dub_track=True)
        self.assertEqual((job.action, job.target, job.width, job.height, job.folder),
                         ("render", J.VOICE_TARGET, 64, 64, T.DUB_FOLDER))
        self.assertEqual(job.shot["audio_policy"], "clone")
        sections = {x.split(":", 1)[0]: x for x in job.prompt}
        self.assertEqual(sections["overall_soundscape"], f"overall_soundscape: {J.VOICE_SOUND}")
        self.assertEqual(sections["non_diegetic_music"], "non_diegetic_music: N/A")
        take = J.start_job(job)
        self.assertEqual(os.path.dirname(take.paths.dir), os.path.join(self.root, "dub"))
        self.assertTrue(T.read_sidecar(take.paths.sidecar)["dub_track"])
        self.assertEqual([t.take for t in T.dub_tracks(self.root, "sh020")], [take.take])
        self.assertEqual(T.list_takes(self.root, "final", "sh020"), [])      # not a take
        # another voice model, at its own size
        job = self.plan("sh020", dub_track=True, target="fasth3_omni")
        self.assertEqual((job.target, job.folder), ("fasth3_omni", T.DUB_FOLDER))

    # -- generate / clone --------------------------------------------------

    def test_generate_or_clone_recompiles_the_shot_when_its_policy_differs(self):
        built = self.plan("sh020")
        self.assertEqual(built.shot["audio_policy"], "clone")        # the series clones
        self.sound("sh020", {"mode": "generate"})
        job = self.plan("sh020")
        self.assertEqual(job.shot["audio_policy"], "generate")
        self.assertEqual(job.sound, {"mode": "generate"})
        self.assertEqual(J.sidecar_for(job)["sound"], {"mode": "generate"})
        self.sound("sh020", {"mode": "clone"})
        self.assertEqual(self.plan("sh020").shot, built.shot)         # nothing to change

    # -- dub a file --------------------------------------------------------

    @unittest.skipUnless(FF.have("ffmpeg"), "ffmpeg not on PATH")
    def test_ref2va_dubs_a_dub_track_through_its_shot_loader(self):
        """...in a series with no recorded track (Ballroom: "uses an audio window
        but series.json has no audio.track set")."""
        p = os.path.join(self.root, "series.json")
        cfg = json.load(open(p, encoding="utf-8"))
        cfg.get("audio", {}).pop("track", None)
        T.write_json(p, cfg)
        d = self.finished(folder=T.DUB_FOLDER, dub_track=True, target=J.VOICE_TARGET)
        self.sound("sh020", {"mode": "dub", "dub": {"from": "dub", "take": d.take}})
        job = self.plan("sh020")
        self.assertTrue(job.runs, job.error)
        # prompted as dub_keep_foley (its sound laid under the voice), saved as a dub:
        # no voice stripping (demucs) for a mix the take gets whole anyway
        self.assertEqual(job.shot["audio_policy"], "dub")
        self.assertEqual(job.shot["audio_retention"], "partially_copy")  # dub_keep_foley's
        self.assertTrue(job.shot["audio_file"].endswith("_level.wav"))
        self.assertTrue(os.path.isfile(os.path.join(self.root, job.shot["audio_file"])))
        doc, i = J.find_shot(self.root, "final", "sh020")
        self.assertEqual(job.frames, doc["shots"][i]["length"])
        self.assertIn("<Audio 1>", J._prompt_text(job.prompt))
        self.assertEqual([(r["slot"], r["path"]) for r in J.ref_slots(job.doc, job.shot)
                          if r["kind"] == "audio"], [("Audio 1", job.shot["audio_file"])])
        self.assertEqual(job.dub_label, f"dub track {d.take}")
        # the voice alone: prompted as a dub, nothing of the model's under it
        self.sound("sh020", {"mode": "dub", "dub": {"from": "dub", "take": d.take}, "keep_foley": False})
        self.assertEqual(T.shot_sound(T.load_overrides(self.root), "sh020")["keep_foley"], False)
        job = self.plan("sh020")
        self.assertEqual((job.shot["audio_policy"], job.shot["audio_retention"]), ("dub", "fully_copy"))

    @unittest.skipUnless(FF.have("ffmpeg"), "ffmpeg not on PATH")
    def test_fl2va_anchors_a_takes_sound(self):
        t = self.finished(pass_="proxy")                   # the proxy's delivery, for the final
        self.sound("sh020", {"mode": "dub", "dub": {"from": "take", "pass": "proxy", "take": t.take}})
        job = self.plan("sh020", target=FL, loras=[])
        self.assertTrue(job.runs, job.error)
        comfy = FakeComfy()
        try:
            got = J.stage_inputs(job, J.Comfy(comfy.url))
            take = J.start_job(job)
        finally:
            comfy.close()
        self.assertEqual(list(got), ["audio"])
        base = J.load_graph(os.path.join(ROOT, "seriesmith", "targets", "video", FL, "workflow.json"))
        g = J.graph_for(base, job, take)
        self.assertEqual(J.check_graph(g, FL_INFO), [])
        self.assertFalse(of(g, "LTXVAudioOnlyModel"))                 # nothing made
        guide = g[J.node_of(g, "MiniMaxH3AddGuide")]["inputs"]
        self.assertEqual(g[guide["audio"][0]]["inputs"]["audio"], got["audio"])

    @unittest.skipUnless(FF.have("ffmpeg"), "ffmpeg not on PATH")
    def test_ltx_holds_a_dub_track(self):
        d = self.finished(folder=T.DUB_FOLDER, dub_track=True)
        self.sound("sh020", {"mode": "dub", "dub": {"from": "dub", "take": d.take}})
        job = self.plan("sh020", target="ltx2", loras=[])
        self.assertTrue(job.runs, job.error)
        comfy = FakeComfy()
        try:
            got = J.stage_inputs(job, J.Comfy(comfy.url))
        finally:
            comfy.close()
        self.assertEqual(sorted(got), ["audio"])            # no voice samples staged
        from test_ltx import OBJECT_INFO as LTX_INFO
        base = J.load_graph(os.path.join(ROOT, "seriesmith", "targets", "video", "ltx2",
                                         "workflow.json"))
        g = J.graph_for(base, job, J.start_job(job))
        self.assertEqual(J.check_graph(g, LTX_INFO), [])
        self.assertFalse(of(g, "LTXVAudioOnlyModel"))
        self.assertEqual([g[k]["inputs"]["audio"] for k in of(g, "LoadAudio")], [got["audio"]])

    def test_what_cant_be_dubbed_is_said(self):
        self.sound("sh020", {"mode": "dub", "dub": {"from": "dub", "take": 3}})
        job = self.plan("sh020")
        self.assertEqual(job.action, "error")
        self.assertIn("dub track 3, isn't a finished take with sound", job.error)
        d = self.finished(folder=T.DUB_FOLDER)
        self.sound("sh020", {"mode": "dub", "dub": {"from": "dub", "take": d.take}})
        job = self.plan("sh020", target="wan22_ti2v")
        self.assertIn("can't dub a track of its own", job.error)

    def test_which_models_dub_a_track(self):
        from seriesmith import targets as TG
        caps = {t: TG.load_target(t, "video").describe()["capabilities"]["dubs_tracks"]
                for t in (FL, "ltx2", "ltx2_msr", "ltx2_ingredients", J.VOICE_TARGET,
                          "fasth3_omni", "seedance_2_5", "wan22_ti2v")}
        self.assertEqual({t for t, ok in caps.items() if ok},
                         {FL, "ltx2", "ltx2_msr", "ltx2_ingredients", J.VOICE_TARGET, "fasth3_omni"})

    @unittest.skipUnless(FF.have("ffmpeg"), "ffmpeg not on PATH")
    def test_a_dubbed_take_carries_its_mix(self):
        """dub_keep_foley's saver muxes the foley alone (a recording is laid in at
        the cut); a take dubbed to a file plays the model's whole mix instead."""
        import subprocess
        t = T.reserve_take(self.root, "final", "sh020", {"status": "ok",
                                                          "sound": {"mode": "dub", "dub": {"from": "dub", "take": 1}}})
        subprocess.run([*FF.tool("ffmpeg"), "-v", "error", "-f", "lavfi", "-i", "color=black:s=64x64:d=2",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", t.paths.mp4], check=True)
        with open(t.paths.h3_wav, "wb") as fh:
            fh.write(wav_bytes(2.0))
        from seriesmith import peaks as PK
        self.assertFalse(PK.has_audio(t.paths.mp4))
        self.assertEqual(J.remux_dub(t), "the mp4 carries the dubbed mix")
        self.assertTrue(PK.has_audio(t.paths.mp4))

    # -- stale, and the routes ----------------------------------------------

    def test_a_take_with_another_sound_is_stale_and_the_routes(self):
        t = self.finished()
        st = lambda: next(s for s in E.episode_status(self.root, "final")["shots"] if s["shot"] == "sh020")  # noqa: E731
        self.assertNotIn("sound", st()["takes"][0]["stale"])
        d = self.finished(folder=T.DUB_FOLDER, dub_track=True)
        ctx = A.Context(os.path.join(self._t.name, "user"), "http://127.0.0.1:0", env={})
        self.assertEqual(A.put_config(ctx, {"roots": [self._t.name]})[0], 200)
        code, out = A.put_sound(ctx, {"ep": self.root, "shots": ["sh020"],
                                      "sound": {"mode": "dub", "dub": {"from": "dub", "take": d.take}}})
        self.assertEqual(code, 200, out)
        s = st()
        self.assertIn("sound", s["takes"][0]["stale"])
        self.assertEqual((s["sound"]["mode"], s["sound"]["label"]), ("dub", f"dub track {d.take}"))
        self.assertTrue(s["sound"]["file"].endswith("_h3.wav"))
        code, out = A.get_dubs(ctx, {"ep": self.root, "shot": "sh020"})
        self.assertEqual(code, 200, out)
        self.assertEqual([x["take"] for x in out["dubs"]], [d.take])
        self.assertEqual([(x["pass"], x["take"]) for x in out["takes"]], [("final", t.take)])
        self.assertEqual(out["sound"]["dub"]["take"], d.take)
        code, out = A.put_sound(ctx, {"ep": self.root, "shots": ["sh020"], "sound": {"mode": "loud"}})
        self.assertEqual(code, 400)


if __name__ == "__main__":
    unittest.main()
