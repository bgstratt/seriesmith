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
            self.assertEqual(p["image_url"]["url"].via, "seedance")   # through the virtual library
        panels = J.frozen_shotlist(job)["shots"][0]["panels"]
        self.assertEqual(len(pictures), len(panels))
        self.assertEqual(args["ratio"], "16:9")
        self.assertEqual(args["resolution"], "720p")
        self.assertTrue(4 <= args["duration"] <= 30)
        self.assertEqual(args["duration"] * 24, job.frames)
        self.assertTrue(0 <= args["seed"] <= 2147483647)      # BytePlus refuses past 2^31-1
        self.assertIs(args["watermark"], False)

    def test_a_sheet_goes_up_as_its_one_panel(self):
        """The provider refuses a 4:1 sheet (invalid_input, 2026-10-11): a
        character's sheet is sent as the panel the shot wants, cut once."""
        from PIL import Image
        job = self.job()
        panels = J.frozen_shotlist(job)["shots"][0]["panels"]
        sheet = next(p for p in panels if p.get("view"))
        path = os.path.normpath(J._abs(job.root, sheet["path"]))
        img = Image.new("RGB", (400, 100))
        for i, c in enumerate([(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]):
            img.paste(c, (i * 100, 0, (i + 1) * 100, 100))
        img.save(path)
        _, (_, args) = self.call(job)
        sent = [p["image_url"]["url"].path for p in args["content"][1:]]
        cut = next(s for s in sent if "_panels" in s)
        with Image.open(cut) as got:
            self.assertEqual(got.size, (100, 100))
            want = {"body": (255, 0, 0), "face": (255, 255, 0)}[sheet["view"]]
            self.assertEqual(got.getpixel((50, 50)), want)
        self.assertNotIn(path, sent)

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


class DraftTest(Episode):
    """Seedance's Draft -> Final: a proxy take is a draft (draft: true, 480p),
    its record keeps the provider's task id, and a final made from it sends
    only that id, at 1080p (POST /seriesmith/render with from_draft)."""

    def proxy_job(self) -> J.Job:
        doc = J.load_shotlist(self.root, "proxy")
        i = next(n for n, s in enumerate(doc["shots"]) if s["id"] == self.shot_id)
        return J.plan_job(self.root, "proxy", doc, i, J.RenderRequest(self.shot_id, target=SEEDANCE), {})

    def test_a_proxy_is_a_draft_and_a_final_from_it_is_its_id_alone(self):
        t = TG.load_target(SEEDANCE, "video")
        _, args = t.module.router_call(t, self.proxy_job())
        self.assertEqual((args["draft"], args["resolution"]), (True, "480p"))
        _, args = t.module.router_call(t, self.job())                 # a final: no draft
        self.assertNotIn("draft", args)
        job = self.job()
        job.from_draft = {"task": "cgt-1", "take": 2, "pass": "proxy"}
        _, args = t.module.router_call(t, job)
        self.assertEqual(args, {"content": [{"type": "draft_task", "draft_task": {"id": "cgt-1"}}],
                                "resolution": "1080p"})

    def draft_take(self, made: float):
        job = self.proxy_job()
        take = J.start_job(job)

        class Out:
            type, name = "video", "v.mp4"

            def save(self, path):
                with open(path, "wb") as fh:
                    fh.write(tiny_mp4())

        class Run:
            id, model, backend, error = "r1", MODEL, "router", ""
            result = {"id": "cgt-draft", "draft": True, "created_at": made, "seed": 5}

            def outputs(self):
                return [Out()]
        self.assertEqual(J.collect_router_take(take, Run(), "succeeded", {"content": []}), "ok")
        return T.get_take(self.root, "proxy", self.shot_id, take.take)

    @unittest.skipUnless(HAVE_FFMPEG, "needs ffmpeg")
    def test_a_draft_keeps_its_task_id_for_a_week(self):
        import time
        from seriesmith import api as A
        t = self.draft_take(time.time())
        d = J.draft_of(t.sidecar)
        self.assertEqual((d["task"], d["expired"]), ("cgt-draft", False))
        self.assertEqual(t.sidecar["model_request"]["provider"]["id"], "cgt-draft")
        drafts, target, shots = A._drafts_asked(self.root, {self.shot_id: t.take})
        self.assertEqual((drafts[self.shot_id]["task"], target, shots),
                         ("cgt-draft", SEEDANCE, [self.shot_id]))
        # eight days on, its final can't be made from it
        old = self.draft_take(time.time() - 8 * 86400)
        self.assertTrue(J.draft_of(old.sidecar)["expired"])
        with self.assertRaises(A.ApiError) as cm:
            A._drafts_asked(self.root, {self.shot_id: old.take})
        self.assertEqual(cm.exception.status, 409)
        with self.assertRaises(A.ApiError):
            A._drafts_asked(self.root, {self.shot_id: 99})          # no such draft


class GenericRouterTest(Episode):
    """targets/generic/router_video: a Router model described by data. Its
    `router.inputs` maps a shot onto the model's own fields."""

    def target(self, inputs: dict, **router):
        sd = TG.load_target(SEEDANCE, "video")
        spec = json.loads(json.dumps(sd.spec))
        spec["id"] = "kling_like"
        spec["router"] = {"model": "kling/kling-v3", "arguments": {"mode": "pro"},
                          "inputs": inputs, **router}
        return TG.Target(sd.folder, spec)

    def test_a_model_with_plain_fields(self):
        t = self.target({
            "prompt": "prompt", "negative": "negative_prompt",
            "duration": {"name": "duration", "values": [5, 10], "as": "str"},
            "ratio": {"name": "aspect_ratio", "values": ["16:9", "9:16", "1:1"]},
            "seed": {"name": "seed", "max": 99},
            "audio": {"name": "sound", "on": "on", "off": "off"},
            "references": {"list": "image_urls", "max": 2},
        })
        job = self.job()
        model, args = t.module.router_call(t, job)
        self.assertEqual(model, "kling/kling-v3")
        self.assertEqual(args["mode"], "pro")
        self.assertEqual(args["prompt"], J._prompt_text(job.prompt))
        self.assertIn(args["duration"], ("5", "10"))                  # snapped, as text
        self.assertEqual(args["aspect_ratio"], "16:9")
        self.assertTrue(0 <= args["seed"] <= 99)
        self.assertIn(args["sound"], ("on", "off"))
        self.assertTrue(args["image_urls"] and all(isinstance(f, File) for f in args["image_urls"]))
        self.assertTrue(all(f.via == "" for f in args["image_urls"]))   # plain URLs
        self.assertNotIn("content", args)

    def test_wrapped_references_and_no_draft(self):
        t = self.target({"references": {"list": "references", "item": {"url": "$url"}}},
                        draft={"proxy": False})
        _, args = t.module.router_call(t, self.job())
        self.assertTrue(all(set(r) == {"url"} and isinstance(r["url"], File) for r in args["references"]))
        self.assertNotIn("draft", args)

    def test_a_nested_request(self):
        """Veo's shape: the prompt and pictures in instances[0], the rest in
        parameters; a resolution by name, the size by WxH for another model."""
        t = self.target({
            "prompt": "instances.0.prompt",
            "duration": {"name": "parameters.durationSeconds", "values": [4, 6, 8]},
            "resolution": {"name": "parameters.resolution", "values": ["720p", "1080p", "4k"]},
            "ratio": {"name": "parameters.aspectRatio", "values": ["16:9", "9:16"]},
            "seed": {"name": "parameters.seed"},
            "audio": {"name": "parameters.generateAudio"},
            "references": {"list": "instances.0.referenceImages", "max": 3,
                           "item": {"image": {"gcsUri": "$url", "mimeType": "image/png"},
                                    "referenceType": "asset"}},
        })
        job = self.job()
        _, args = t.module.router_call(t, job)
        inst = args["instances"][0]
        self.assertEqual(inst["prompt"], J._prompt_text(job.prompt))
        self.assertTrue(inst["referenceImages"])
        self.assertIsInstance(inst["referenceImages"][0]["image"]["gcsUri"], File)
        self.assertEqual(inst["referenceImages"][0]["referenceType"], "asset")
        p = args["parameters"]
        self.assertIn(p["durationSeconds"], (4, 6, 8))
        self.assertEqual((p["resolution"], p["aspectRatio"]), ("720p", "16:9"))
        self.assertIsInstance(p["generateAudio"], bool)
        from seriesmith.targets.generic import router_video as RV
        self.assertEqual(RV.nearest_resolution(1280, 720, ["1280x720", "720x1280", "1920x1080"]), "1280x720")
        self.assertEqual(RV.nearest_resolution(720, 1280, ["1280x720", "720x1280"]), "720x1280")
        self.assertEqual(RV.nearest_resolution(1280, 720, ["768P", "2K"]), "768P")
        self.assertEqual(RV.size_of("1280*720"), (1280, 720))

    def test_lengths_snap_to_what_the_model_takes(self):
        from seriesmith.targets.generic import router_video as RV
        self.assertEqual(RV.seconds_for(96, 24, {"min": 4, "max": 30}), 4)
        self.assertEqual(RV.seconds_for(48, 24, {"min": 4, "max": 30}), 4)       # clamped up
        self.assertEqual(RV.seconds_for(170, 24, {"values": [5, 10]}), 5)
        self.assertEqual(RV.seconds_for(200, 24, {"values": [5, 10], "as": "str"}), "10")
        self.assertEqual(RV.nearest_ratio(1280, 720, ["adaptive", "16:9", "4:3"]), "16:9")


if __name__ == "__main__":
    unittest.main()
