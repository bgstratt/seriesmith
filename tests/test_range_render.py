"""
Frames of a take made again (RenderRequest.redo_range): what a range may be taken
from, what its frames ask, the size and length it renders at, and the graph it
makes. The nodes' tensor work needs ComfyUI; the frame math is shotplan's.
"""
from __future__ import annotations

import json
import os
import random
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
from seriesmith import jobs as J  # noqa: E402
from seriesmith import shotnodes as SN  # noqa: E402
from seriesmith import takes as T  # noqa: E402
from seriesmith.backends import File  # noqa: E402
from test_cloud import h3_shot  # noqa: E402
from test_render import build_episode, stub_refs  # noqa: E402


class FrameMath(unittest.TestCase):
    def test_steps_of_a_range_round_outward(self):
        sp = SN.shotplan()
        self.assertEqual(sp.range_steps(40, 60, 37), (12, 19))
        self.assertEqual(sp.range_steps(74, 123, 37), (22, 37))
        self.assertEqual(sp.range_steps(52, 87, 42), (15, 27))
        self.assertEqual(sp.range_steps(0, 0, 37), (0, 1))

    def test_ltx_has_a_coarser_grid(self):
        sp = SN.shotplan()
        self.assertEqual(sp.ltx_range_steps(30, 60, 12), (4, 9))
        self.assertEqual(sp.ltx_range_steps(0, 0, 12), (0, 1))
        self.assertEqual(sp.ltx_range_steps(1, 8, 12), (1, 2))
        self.assertEqual(sp.ltx_range_steps(80, 88, 12), (10, 12))

    def test_a_grid_knows_its_frames(self):
        sp = SN.shotplan()
        self.assertEqual(sp.GRIDS["h3"][0](37), 124)
        self.assertEqual(sp.GRIDS["ltx"][0](12), 89)

    def test_a_range_past_the_end_is_refused(self):
        with self.assertRaises(ValueError):
            SN.shotplan().range_steps(200, 210, 37)


class Episode(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        build_episode(self.root)
        self.doc = J.load_shotlist(self.root, "final")
        self.index = h3_shot(self.doc)
        self.shot = self.doc["shots"][self.index]
        first = J.plan_job(self.root, "final", self.doc, self.index, J.RenderRequest(self.shot["id"]), {})
        self.target, self.size = first.target, (first.width, first.height)
        self.base, _ = J.resolve_workflow(None, J.WORKFLOW_NAME, None, prefer_repo=True)

    def take(self, *, latent=True, sound=True, **record):
        t = T.reserve_take(self.root, "final", self.shot["id"], {"status": "queued"})
        fields = {"status": "ok", "target": self.target, "frames": self.shot["length"],
                  "length": self.shot["length"], "width": self.size[0], "height": self.size[1],
                  "fps": 24.0, **record}
        T.update_sidecar(t.paths.sidecar, **fields)
        open(t.paths.mp4, "wb").close()
        if latent:
            open(t.paths.latent, "wb").close()
        if sound:
            open(t.paths.h3_wav, "wb").close()
        with open(t.paths.shotlist, "w", encoding="utf-8", newline="\n") as fh:
            json.dump({"shots": [{"id": self.shot["id"], "prompt": ["what the take asked"]}]}, fh)
        return t

    def plan(self, take, first=10, last=20, **asked):
        return J.plan_job(self.root, "final", self.doc, self.index, J.RenderRequest(
            self.shot["id"], redo=True, seed_mode="new",
            redo_range={"take": take, "first": first, "last": last, **asked}), {}, rng=random.Random(7))


class Plan(Episode):
    def test_a_kept_latent_is_held_and_the_take_is_asked_again(self):
        t = self.take()
        job = self.plan(t.take)
        self.assertEqual(job.error or "", "")
        self.assertEqual(job.redo_range["via"], "latent")
        self.assertEqual(job.redo_range["latent"], t.paths.latent)
        self.assertEqual(job.redo_range["keep"], self.shot["length"])
        self.assertEqual(job.redo_range["sound"], t.paths.h3_wav)
        self.assertEqual(job.prompt, ["what the take asked"])
        self.assertTrue(job.save_latent)

    def test_its_frames_can_ask_something_else(self):
        job = self.plan(self.take().take, prompt=["a small yawn"])
        self.assertEqual(job.prompt, ["a small yawn"])

    def test_a_range_outside_the_take_is_refused(self):
        job = self.plan(self.take().take, first=5, last=self.shot["length"])
        self.assertIn("aren't inside", job.error)
        self.assertIn("aren't inside", self.plan(self.take().take, first=20, last=10).error)

    def test_a_missing_take_is_refused(self):
        self.assertIn("no usable take", self.plan(99).error)

    def test_a_take_keeps_its_own_size_and_length_when_the_shot_has_moved(self):
        longer = self.shot["length"] + 17
        job = self.plan(self.take(frames=longer, length=longer, width=1280, height=704).take, last=longer - 1)
        self.assertEqual(job.error or "", "")
        self.assertEqual(job.redo_range["via"], "latent")
        self.assertEqual((job.frames, job.redo_range["keep"]), (longer, longer))
        self.assertEqual((job.width, job.height), (1280, 704))
        self.assertTrue(job.save_latent)

    def test_a_take_with_no_latent_is_encoded(self):
        t = self.take(latent=False)
        job = self.plan(t.take)
        self.assertEqual(job.error or "", "")
        self.assertEqual((job.redo_range["via"], job.redo_range["latent"]), ("frames", ""))
        self.assertEqual(job.redo_range["video"], t.paths.mp4)

    def test_frames_can_be_asked_for_over_a_kept_latent(self):
        self.assertEqual(self.plan(self.take().take, via="frames").redo_range["via"], "frames")

    def test_another_models_take_keeps_its_length_and_size(self):
        t = self.take(target="seedance_2_5", frames=121, length=121, width=1280, height=704)
        built = self.doc["shots"][self.index]["prompt"]
        job = self.plan(t.take)
        self.assertEqual(job.error or "", "")
        self.assertEqual(job.frames, 124)                # sampled on H3's grid
        # the loader works its length out from the duration
        frozen = J.frozen_shotlist(job)["shots"][0]
        self.assertEqual(SN.shotplan().snap_up(round(frozen["duration"] * 24.0)), 124)
        self.assertEqual(job.redo_range["keep"], 121)    # trimmed back
        self.assertEqual((job.width, job.height), (1280, 704))
        self.assertFalse(job.save_latent)                # its latent would be 124 frames
        self.assertEqual(job.prompt, built)              # its prompt was written for Seedance
        self.assertEqual(self.doc["shots"][self.index]["length"], self.shot["length"])

    def test_a_model_that_cant_hold_a_take_is_refused(self):
        t = self.take()
        job = self.plan(t.take)
        job.target = "wan22_i2v"
        J.plan_range(job, {"take": t.take, "first": 10, "last": 20}, T.list_takes(self.root, "final", self.shot["id"]))
        self.assertIn("can't make frames", job.error)

    def test_another_frame_rate_is_refused(self):
        job = self.plan(self.take(target="wan22_i2v", frames=85, length=85, fps=16.0).take)
        self.assertIn("16 fps", job.error)

    def test_the_record_says_what_was_made_again(self):
        t = self.take()
        record = J.sidecar_for(self.plan(t.take))
        self.assertEqual(record["redo_range"], {"take": t.take, "first": 10, "last": 20, "via": "latent"})


class Graph(Episode):
    def graph(self, job):
        take = J.start_job(job)
        return J.graph_for(self.base, job, take)

    def node(self, g, kind):
        return g[next(k for k, v in g.items() if v["class_type"] == kind)]["inputs"]

    def test_the_sampler_gets_the_held_latent(self):
        t = self.take()
        g = self.graph(self.plan(t.take))
        r = self.node(g, "SeriesmithRangeLatent")
        self.assertIsInstance(r["take_latent"], File)
        self.assertEqual(r["take_latent"].path, t.paths.latent)
        self.assertEqual((r["first_frame"], r["last_frame"]), (10, 20))
        self.assertNotIn("video_vae", r)
        sampler = self.node(g, "SamplerCustomAdvanced")
        self.assertEqual(g[sampler["latent_image"][0]]["class_type"], "SeriesmithRangeLatent")

    def test_the_saver_gets_the_takes_sound_and_length(self):
        t = self.take()
        g = self.graph(self.plan(t.take))
        finish = self.node(g, "SeriesmithRangeFinish")
        self.assertEqual(finish["sound"].path, t.paths.h3_wav)
        self.assertNotIn("audio", finish)
        self.assertEqual(finish["frames"], self.shot["length"])
        saver = g[J.node_of(g, "H3SaveShot")]["inputs"]
        self.assertEqual(g[saver["images"][0]]["class_type"], "SeriesmithRangeFinish")
        self.assertEqual(g[saver["audio"][0]]["class_type"], "SeriesmithRangeFinish")
        self.assertEqual((saver["images"][1], saver["audio"][1]), (0, 1))

    def test_a_take_with_no_sound_keeps_what_the_render_made(self):
        g = self.graph(self.plan(self.take(sound=False).take))
        finish = self.node(g, "SeriesmithRangeFinish")
        self.assertEqual(finish["sound"], "")
        self.assertEqual(g[finish["audio"][0]]["class_type"], "VAEDecodeAudio")

    def test_an_encoded_take_is_given_the_vaes(self):
        t = self.take(latent=False)
        g = self.graph(self.plan(t.take))
        r = self.node(g, "SeriesmithRangeLatent")
        self.assertEqual(r["take_latent"], "")
        self.assertEqual(r["take_video"].path, t.paths.mp4)
        self.assertTrue(r["video_vae"] and r["audio_vae"])

    def test_a_normal_render_has_none_of_it(self):
        job = J.plan_job(self.root, "final", self.doc, self.index, J.RenderRequest(self.shot["id"]), {})
        kinds = {v["class_type"] for v in self.graph(job).values()}
        self.assertFalse(kinds & {"SeriesmithRangeLatent", "SeriesmithRangeFinish"})


class TwoStages(unittest.TestCase):
    """LTX-2: the first stage holds the take at its size, the second the kept latent."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ep = os.path.join(self._tmp.name, "ct01")
        os.makedirs(self.ep)
        fixture = os.path.join(HERE, "fixtures", "continuous")
        shutil.copy(os.path.join(fixture, "series.json"), self.ep)
        shutil.copy(os.path.join(fixture, "script.md"), os.path.join(self.ep, "ct01.md"))
        self.assertTrue(E.build_episode(self.ep)["ok"])
        stub_refs(self.ep)
        self.doc = J.load_shotlist(self.ep, "final")
        self.index = next(i for i, sh in enumerate(self.doc["shots"]) if sh["id"] == "sh010")

    def graph(self, *, kept=True):
        t = T.reserve_take(self.ep, "final", "sh010", {"status": "queued"})
        T.update_sidecar(t.paths.sidecar, status="ok", target="ltx2" if kept else "wan22_i2v", frames=97, length=97,
                         width=1344, height=768, fps=24.0)
        open(t.paths.mp4, "wb").close()
        open(t.paths.h3_wav, "wb").close()
        if kept:
            open(t.paths.latent, "wb").close()
        job = J.plan_job(self.ep, "final", self.doc, self.index, J.RenderRequest(
            "sh010", redo=True, seed_mode="new", target="ltx2",
            redo_range={"take": t.take, "first": 30, "last": 60}), {}, rng=random.Random(7))
        self.assertEqual(job.error or "", "")
        base, _ = J.target_workflow(J.job_target(job), prefer_repo=True)
        return t, job, J.graph_for(base, job, J.start_job(job))

    def kind(self, g, link):
        return g[link[0]]["class_type"]

    def test_each_stage_holds_the_take(self):
        t, job, g = self.graph()
        self.assertEqual(job.redo_range["via"], "latent")
        first = next(v for v in g.values() if v["class_type"] == "SeriesmithRangeLatent")["inputs"]
        second = next(v for v in g.values() if v["class_type"] == "SeriesmithRangeRefine")["inputs"]
        self.assertEqual(first["grid"], "ltx")
        self.assertEqual(first["take_latent"].path, t.paths.latent)
        self.assertEqual(first["take_video"].path, t.paths.mp4)      # the first stage is half its size
        self.assertTrue(first["video_vae"])
        self.assertEqual(second["take_latent"].path, t.paths.latent)
        self.assertNotIn("take_video", second)
        fed = [self.kind(g, v["inputs"]["latent_image"]) for v in g.values() if v["class_type"] == "SamplerCustomAdvanced"]
        self.assertEqual(sorted(fed), ["SeriesmithRangeLatent", "SeriesmithRangeRefine"])

    def test_the_saved_latent_is_the_second_stages(self):
        _, _, g = self.graph()
        saver = g[J.node_of(g, "H3SaveShot")]["inputs"]
        sampler = g[saver["latent"][0]]
        self.assertEqual(self.kind(g, sampler["inputs"]["latent_image"]), "SeriesmithRangeRefine")

    def test_a_take_from_another_model_is_encoded_at_both_stages(self):
        t, job, g = self.graph(kept=False)
        self.assertEqual(job.redo_range["via"], "frames")
        second = next(v for v in g.values() if v["class_type"] == "SeriesmithRangeRefine")["inputs"]
        self.assertEqual(second["take_latent"], "")
        self.assertEqual(second["take_video"].path, t.paths.mp4)
        self.assertTrue(second["video_vae"])


class Api(unittest.TestCase):
    def asks(self, redo_range):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = A.Context(os.path.join(tmp, "user"), "http://127.0.0.1:0", env={})
            A.put_config(ctx, {"roots": [tmp]})
            os.makedirs(os.path.join(tmp, "ep"))
            return A.post_render(ctx, {"ep": os.path.join(tmp, "ep"), "pass": "final",
                                       "redo_range": redo_range})

    def refused(self, redo_range):
        status, data = self.asks(redo_range)
        self.assertEqual(status, 400, data)
        return data["error"]

    def test_bad_ranges_are_refused(self):
        for bad in ("3-9", {"take": 1, "first": 2}, {"take": "1", "first": 2, "last": 3},
                    {"take": True, "first": 2, "last": 3}):
            self.assertIn("redo_range", self.refused(bad))

    def test_a_bad_prompt_or_via_is_refused(self):
        whole = {"take": 1, "first": 2, "last": 3}
        for bad in ("", "  ", [], [1], 5):
            self.assertIn("prompt", self.refused({**whole, "prompt": bad}))
        self.assertIn("via", self.refused({**whole, "via": "latent"}))


if __name__ == "__main__":
    unittest.main()
