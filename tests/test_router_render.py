"""
Hosted renders (docs/PLAN.md, step 4) without a key: where a shot runs
(jobs.backend_choice), what a Router target sends (Seedance 2.5's request),
finishing a take from a returned video (jobs.collect_router_take, needs
ffmpeg), and `seriesmith render` end to end on the fake backend.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from seriesmith import jobs as J  # noqa: E402
from seriesmith import render  # noqa: E402
from seriesmith import takes as T  # noqa: E402
from seriesmith import targets as TG  # noqa: E402
from seriesmith.backends import File  # noqa: E402
from seriesmith.backends.fake import FakeBackend  # noqa: E402
from test_render import FIXTURE, build_episode  # noqa: E402

SEEDANCE = "seedance_2_5"
MODEL = "byteplus/dreamina-seedance-2-5-260628"
HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def tiny_mp4(seconds: float = 1.0) -> bytes:
    """A real 320x180, 24 fps mp4 with sound: what a provider might return."""
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "v.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                        f"testsrc=size=320x180:rate=24:duration={seconds}", "-f", "lavfi",
                        "-i", f"sine=frequency=440:duration={seconds}", "-shortest",
                        "-pix_fmt", "yuv420p", out], check=True, capture_output=True)
        with open(out, "rb") as fh:
            return fh.read()


class BackendChoiceTest(unittest.TestCase):
    def setUp(self):
        self.h3 = TG.load_target("minimax_h3_ref2va", "video")
        self.sd = TG.load_target(SEEDANCE, "video")

    def test_with_nothing_said_a_shot_runs_where_its_target_does(self):
        self.assertEqual(J.backend_choice({}, "sh010", self.h3), ("local", "target", ""))
        self.assertEqual(J.backend_choice({}, "sh010", self.sd), ("router", "target", ""))

    def test_the_request_then_the_shot_then_the_episode(self):
        ov = T.set_shot_backend({"episode": {"backend": "deployment"}}, "sh010", "local")
        self.assertEqual(J.backend_choice(ov, "sh010", self.h3, "deployment")[:2],
                         ("deployment:minimax_h3_ref2va", "request"))
        self.assertEqual(J.backend_choice(ov, "sh010", self.h3)[:2], ("local", "override"))
        self.assertEqual(J.backend_choice(ov, "sh020", self.h3)[:2],
                         ("deployment:minimax_h3_ref2va", "episode"))

    def test_a_default_that_doesnt_suit_the_target_gives_way_with_a_note(self):
        ov = {"episode": {"backend": "local"}}
        name, source, note = J.backend_choice(ov, "sh010", self.sd)
        self.assertEqual((name, source), ("router", "target"))
        self.assertIn("doesn't run on local", note)

    def test_asking_for_a_backend_the_target_cant_use_is_an_error(self):
        with self.assertRaises(ValueError):
            J.backend_choice({}, "sh010", self.sd, "local")
        with self.assertRaises(ValueError):
            J.backend_choice(T.set_shot_backend({}, "sh010", "cloud"), "sh010", self.h3)

    def test_clearing_a_shots_backend_leaves_nothing_behind(self):
        ov = T.set_shot_backend({}, "sh010", "router")
        self.assertEqual(T.shot_backend(ov, "sh010"), "router")
        self.assertEqual(T.set_shot_backend(ov, "sh010", None), {"shots": {}})


class Episode(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        build_episode(self.root)
        # retargeting a shot recompiles it from the episode's series config
        shutil.copy(os.path.join(FIXTURE, "series.json"), self.root)
        self.doc = J.load_shotlist(self.root, "final")
        # a shot with a character and a plate, rendered on Seedance this run
        self.index = next(i for i, s in enumerate(self.doc["shots"])
                          if s.get("subjects") and not s.get("hold"))
        self.shot_id = self.doc["shots"][self.index]["id"]

    def job(self, **req) -> J.Job:
        return J.plan_job(self.root, "final", self.doc, self.index,
                          J.RenderRequest(self.shot_id, target=SEEDANCE, **req), {})


class RouterCallTest(Episode):
    def call(self, job=None):
        job = job or self.job()
        t = J.job_target(job)
        return job, t.module.router_call(t, job)

    def test_the_prompt_and_the_references_go_to_the_model(self):
        job, (model, args) = self.call()
        self.assertEqual(model, MODEL)
        self.assertTrue(job.runs, job.error)
        text, *pictures = args["content"]
        self.assertEqual(text, {"type": "text", "text": J._prompt_text(job.prompt)})
        self.assertTrue(pictures)
        for p in pictures:
            self.assertEqual((p["type"], p["role"]), ("image_url", "reference_image"))
            self.assertIsInstance(p["image_url"]["url"], File)
        panels = J.frozen_shotlist(job)["shots"][0]["panels"]
        self.assertEqual(len(pictures), len(panels))
        self.assertEqual(args["ratio"], "16:9")
        self.assertEqual(args["resolution"], "720p")
        self.assertTrue(4 <= args["duration"] <= 30)
        self.assertEqual(args["duration"] * 24, job.frames)
        self.assertTrue(0 <= args["seed"] <= 4294967295)
        self.assertIs(args["watermark"], False)

    def test_a_first_keyframe_makes_it_frame_generation(self):
        job = self.job()
        kf = J.frozen_shotlist(job)["shots"][0]["keyframes"]["first"]
        path = os.path.join(self.root, kf)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "wb").close()
        _, (_, args) = self.call(self.job())
        roles = [c.get("role") for c in args["content"][1:]]
        self.assertEqual(roles, ["first_frame"])
        self.assertNotIn("ratio", args)

    def test_the_take_is_marked_as_not_repeatable(self):
        take = J.start_job(self.job())
        self.assertIs(take.sidecar["reproducible"], False)
        self.assertEqual(take.sidecar["target"], SEEDANCE)


@unittest.skipUnless(HAVE_FFMPEG, "needs ffmpeg and ffprobe")
class CollectRouterTest(Episode):
    def test_the_returned_video_becomes_the_take(self):
        mp4 = tiny_mp4()
        fb = FakeBackend("router", "router",
                         outputs={"": [("out.mp4", "video", mp4), ("last.png", "image", b"png")]})
        job = self.job()
        take = J.start_job(job)
        t = J.job_target(job)
        model, args = t.module.router_call(t, job)
        run = fb.call(model, args)
        J.mark_submitted(take, fb.name, run.id)
        status = J.collect_router_take(take, run, run.watch(), render.as_json(args))
        self.assertEqual(status, "ok")
        sc = T.read_sidecar(take.paths.sidecar)
        self.assertEqual((sc["status"], sc["frames"], sc["fps"]), ("ok", 24, 24.0))
        self.assertEqual((sc["backend"], sc["reproducible"]), ("router", False))
        for p in (take.paths.mp4, take.paths.thumb, take.paths.strip):
            self.assertTrue(os.path.getsize(p) > 0, p)
        req = sc["model_request"]
        self.assertEqual(req["seed"], args["seed"])
        self.assertNotIn("content", req)
        self.assertEqual(req["inputs"][0], "text")

    def test_no_video_fails_the_take(self):
        fb = FakeBackend("router", "router", outputs={"": [("x.json", "text", b"{}")]})
        take = J.start_job(self.job())
        run = fb.call(MODEL, {})
        self.assertEqual(J.collect_router_take(take, run, run.watch()), "failed")
        self.assertIn("no video", T.read_sidecar(take.paths.sidecar)["save_notes"])


@unittest.skipUnless(HAVE_FFMPEG, "needs ffmpeg and ffprobe")
class RenderRouterTest(Episode):
    def render(self, fb, *args):
        with mock.patch.object(render, "available", return_value={fb.name: fb}), \
                mock.patch("builtins.print"):
            return render.main([self.root, "--only", self.shot_id, *args])

    def test_render_on_a_hosted_model(self):
        fb = FakeBackend("router", "router", outputs={"": [("out.mp4", "video", tiny_mp4())]})
        self.assertEqual(self.render(fb, "--target", SEEDANCE), 0)
        (take,) = T.list_takes(self.root, "final", self.shot_id)
        self.assertEqual((take.sidecar["status"], take.sidecar["backend"]), ("ok", "router"))
        ((model, args),) = fb.calls
        self.assertEqual(model, MODEL)
        self.assertTrue(fb.uploaded)
        self.assertEqual(fb.submitted, [])

    def test_a_series_on_local_still_sends_hosted_shots_to_router(self):
        with open(os.path.join(self.root, T.OVERRIDES_FILE), "w", encoding="utf-8") as fh:
            json.dump({"episode": {"backend": "local"}}, fh)
        fb = FakeBackend("router", "router", outputs={"": [("out.mp4", "video", tiny_mp4())]})
        self.assertEqual(self.render(fb, "--target", SEEDANCE), 0)
        self.assertEqual(len(fb.calls), 1)

    def test_without_router_set_up_the_shot_says_so(self):
        fb = FakeBackend("local", "local")
        self.assertEqual(self.render(fb, "--target", SEEDANCE), 0)    # nothing ran
        self.assertEqual((fb.calls, T.list_takes(self.root, "final", self.shot_id)), ([], []))

    def test_dry_run_writes_the_request(self):
        fb = FakeBackend("router", "router")
        with tempfile.TemporaryDirectory() as cwd:
            old = os.getcwd()
            os.chdir(cwd)
            try:
                self.assertEqual(self.render(fb, "--target", SEEDANCE, "--dry-run"), 0)
                with open("render_call.json", encoding="utf-8") as fh:
                    call = json.load(fh)
            finally:
                os.chdir(old)
        self.assertEqual(call["model"], MODEL)
        self.assertIn("File", call["arguments"]["content"][1]["image_url"]["url"])
        self.assertEqual((fb.calls, fb.uploaded), ([], []))


if __name__ == "__main__":
    unittest.main()
