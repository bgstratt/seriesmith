"""
Voice takes and dubbing to them (jobs.RenderRequest.voice_only / lines_from):
a voice take is the shot rendered for its sound only (H3 Ref2VA at 64x64, its
voices cloned from their samples), never in the cut; a take dubbed to one is
the shot on its own model with that take's sound, levelled, as the recording
it dubs (H3 FL2VA anchors it, LTX holds it).

Run:  python -m pytest tests/test_voice_takes.py
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
from seriesmith import ff as FF  # noqa: E402
from seriesmith import jobs as J  # noqa: E402
from seriesmith import takes as T  # noqa: E402
from seriesmith.targets.graph import of  # noqa: E402
from test_render import FIXTURE, FakeComfy, build_episode, wav_bytes  # noqa: E402

FL = "minimax_h3_fl2va"
WF = os.path.join(HERE, "fixtures", "workflows")
OBJECT_INFO = json.load(open(os.path.join(WF, "object_info_h3_fl2va.json"), encoding="utf-8"))


class VoiceTakeTest(unittest.TestCase):
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
        return J.plan_job(self.root, pass_, doc, i, J.RenderRequest(sid, **req), {})

    def voice_take(self, sid="sh020", n=None, pass_="final"):
        """A finished voice take of `sid` on disk, with sound."""
        sc = {"status": "ok", "target": J.VOICE_TARGET, "voice_only": True,
              "width": 64, "height": 64}
        t = T.reserve_take(self.root, pass_, sid, sc, n)
        with open(t.paths.mp4, "wb") as fh:
            fh.write(b"not really a video")
        with open(t.paths.h3_wav, "wb") as fh:
            fh.write(wav_bytes(2.0, freq=300.0))
        return t

    def test_a_voice_take_is_tiny_ref2va_asking_for_the_dialogue_alone(self):
        job = self.plan("sh020", voice_only=True)
        self.assertEqual((job.action, job.target, job.width, job.height),
                         ("render", J.VOICE_TARGET, 64, 64))
        self.assertEqual(job.shot["audio_policy"], "clone")
        sections = {x.split(":", 1)[0]: x for x in job.prompt}
        self.assertEqual(sections["overall_soundscape"], f"overall_soundscape: {J.VOICE_SOUND}")
        self.assertEqual(sections["non_diegetic_music"], "non_diegetic_music: N/A")
        self.assertIn("summary", sections)                     # the rest as it was
        self.assertTrue(J.sidecar_for(job)["voice_only"])
        self.assertTrue(any("a voice take" in n for n in job.notes))
        # a voice take is always a new one, even with one already there
        t = self.voice_take()
        again = self.plan("sh020", voice_only=True)
        self.assertTrue(again.runs)
        self.assertEqual(again.take, t.take + 1)

    def test_a_build_behind_seriesmith_still_retargets(self):
        """A target's compile changed since the build (an update): the built entry
        no longer matches a fresh compile, but the script is the build's own, so
        a render on another model (a voice take on an FL2VA shot) still plans,
        and says so. It used to refuse: "rebuild the episode"."""
        doc, i = J.find_shot(self.root, "final", "sh020")
        path = os.path.join(self.root, J.shotlist_rel("final"))
        sl = json.load(open(path, encoding="utf-8"))
        sl["shots"][i]["prompt"] = ["written by an older seriesmith"]
        T.write_json(path, sl)
        # (the kitchen sink builds on Ref2VA, the voice model: another model retargets)
        job = self.plan("sh020", target="ltx2")
        self.assertTrue(job.runs, job.error)
        self.assertTrue(any("build is older than the series config or seriesmith" in n
                            for n in job.notes), job.notes)

    def test_a_voice_take_never_makes_the_shot_done_nor_goes_into_the_cut(self):
        t = self.voice_take()
        # the shot still renders (Generate missing), on its own model too
        job = self.plan("sh020", target=J.VOICE_TARGET)
        self.assertEqual(job.action, "retry")
        self.assertIsNone(T.latest_usable(T.list_takes(self.root, "final", "sh020")))
        real = T.reserve_take(self.root, "final", "sh020", {"status": "ok"})
        with open(real.paths.mp4, "wb") as fh:
            fh.write(b"x")
        self.assertEqual(T.latest_usable(T.list_takes(self.root, "final", "sh020")).take, real.take)
        self.assertLess(t.take, real.take)

    @unittest.skipUnless(FF.have("ffmpeg"), "ffmpeg not on PATH")
    def test_fl2va_dubs_a_voice_take(self):
        """The voice take's sound, levelled, is anchored as a recording: no lines
        are made in the graph, and the take keeps what it was dubbed to."""
        v = self.voice_take()
        job = self.plan("sh020", target=FL, lines_from=v.take, loras=[])
        self.assertEqual((job.action, job.lines_from), ("render", v.take))
        self.assertTrue(any(f"dubbed to t{v.take:02d}'s voice (a voice take)" in n
                            for n in job.notes))
        comfy = FakeComfy()
        try:
            got = J.stage_inputs(job, J.Comfy(comfy.url))
            take = J.start_job(job)
        finally:
            comfy.close()
        self.assertEqual(list(got), ["audio"])
        self.assertNotIn("voices", got)
        kept = os.path.join(take.paths.dir, take.paths.stem + "_lines.wav")
        self.assertEqual(comfy.uploads[got["audio"]], open(kept, "rb").read())
        sc = T.read_sidecar(take.paths.sidecar)
        self.assertEqual(sc["lines_from"], v.take)
        self.assertTrue(any(r.get("slot") == "lines" and r.get("sha1") for r in sc["refs"]))
        base = J.load_graph(os.path.join(ROOT, "seriesmith", "targets", "video", FL, "workflow.json"))
        g = J.graph_for(base, job, take)
        self.assertEqual(J.check_graph(g, OBJECT_INFO), [])
        self.assertFalse(of(g, "LTXVAudioOnlyModel"))
        guide = g[J.node_of(g, "MiniMaxH3AddGuide")]["inputs"]
        self.assertEqual(g[guide["audio"][0]]["inputs"]["audio"], got["audio"])

    @unittest.skipUnless(FF.have("ffmpeg"), "ffmpeg not on PATH")
    def test_ltx_holds_a_voice_take_and_makes_no_lines(self):
        v = self.voice_take()
        job = self.plan("sh020", target="ltx2", lines_from="voice", loras=[])
        self.assertEqual(job.lines_from, v.take)
        comfy = FakeComfy()
        try:
            got = J.stage_inputs(job, J.Comfy(comfy.url))
        finally:
            comfy.close()
        self.assertEqual(sorted(got), ["audio"])            # no voice samples staged
        from test_ltx import OBJECT_INFO as LTX_INFO
        base = J.load_graph(os.path.join(ROOT, "seriesmith", "targets", "video", "ltx2",
                                         "workflow.json"))
        take = J.start_job(job)
        g = J.graph_for(base, job, take)
        self.assertEqual(J.check_graph(g, LTX_INFO), [])
        self.assertFalse(of(g, "LTXVAudioOnlyModel"))
        self.assertEqual([g[k]["inputs"]["audio"] for k in of(g, "LoadAudio")], [got["audio"]])

    def test_the_editor_installs_the_voice_model_from_its_features_entry(self):
        # web/src/lib/readiness.ts VOICE_FEATURE: the Features entry a voice take
        # opens when its model isn't installed
        from seriesmith import features as FE
        by = {f.id: f for f in FE.catalog()}
        self.assertIn("video.h3", by)
        self.assertTrue(any(i.target == J.VOICE_TARGET for i in by["video.h3"].items))

    def test_what_cant_be_dubbed_is_said(self):
        # no voice take yet
        job = self.plan("sh020", target=FL, lines_from="voice")
        self.assertEqual(job.action, "error")
        self.assertIn("it has none yet", job.error)
        v = self.voice_take()
        # a model that takes no recording to dub
        job = self.plan("sh020", target=J.VOICE_TARGET, lines_from=v.take)
        self.assertEqual(job.action, "error")
        self.assertIn("can't be given a voice to dub", job.error)
        # a take that isn't there
        job = self.plan("sh020", target=FL, lines_from=v.take + 5)
        self.assertIn("isn't a finished take", job.error)


if __name__ == "__main__":
    unittest.main()
