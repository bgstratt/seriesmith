"""
Upscales and posts through seriesmith's queue (finishing.py,
Runner.enqueue_finish), on the fake backend: the graph is made portable when
the job starts (every file an upload, SeriesmithSaveUpscale for the saver),
and what the saver reports lands where H3SaveUpscale wrote it, its record
merged into the take's .up.json / .post.json.
"""
from __future__ import annotations

import json
import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from seriesmith import api as A  # noqa: E402
from seriesmith import finishing as F  # noqa: E402
from seriesmith import post as P  # noqa: E402
from seriesmith import render as RD  # noqa: E402
from seriesmith import takes as T  # noqa: E402
from seriesmith import upscale as U  # noqa: E402
from seriesmith.backends import File  # noqa: E402
from seriesmith.backends.fake import FakeBackend  # noqa: E402
from seriesmith.queue import Queue  # noqa: E402
from seriesmith.runner import Runner  # noqa: E402
import test_phase13 as P13  # noqa: E402
import test_post as TP  # noqa: E402
from test_api import ApiTest  # noqa: E402


def wait_for(cond, timeout=15.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return
        time.sleep(0.02)
    raise AssertionError("timed out")


def saver_outputs(graph: dict, *, status: str = "ok") -> dict:
    """What SeriesmithSaveUpscale reports for `graph`."""
    saver = next(k for k, v in graph.items() if v["class_type"] == F.SAVER)
    ins = graph[saver]["inputs"]
    name = ins["name"]
    items = [(f"{name}.mp4", "video", b"upscaled")]
    if ins.get("last_frame"):
        items.append((f"{name}_last.png", "image", b"last"))
    if "latent" in ins:
        items.append((f"{name}.latent.safetensors", "latent", b"uplatent"))
    items.append((name + F.RECORD_SUFFIX, "file", json.dumps({
        "status": status, "finished": "2026-10-10T12:00:00-04:00", "frames": 73,
        "width": 1536, "height": 896, "audio": "copied", "encoder": "h264_nvenc",
        "quality": "review", "save_ms": {"mp4": 1}, "save_notes": f"{name}.mp4: mp4 written",
        **({"chain_hold": {"held": True}} if "chain_hold" in ins else {})}).encode()))
    return {saver: items}


class FinishQueueTest(ApiTest):
    final_take = P13.UpscaleTest.final_take
    base = P13.UpscaleTest.base

    def setUp(self):
        super().setUp()
        self.fb = FakeBackend("local", "local", outputs=saver_outputs, progress=[0.5, 1.0])
        self.runner = Runner(Queue(), {"local": self.fb}, emit=lambda e, d: self.events.append((e, d)))
        self.addCleanup(setattr, T, "MANAGED", None)

    def finished(self, qid):
        q = self.runner.queue
        wait_for(lambda: q.jobs[qid].status in ("succeeded", "failed", "canceled"))
        return q.jobs[qid]

    def test_a_latent_upscale_runs_portable_and_lands_beside_the_take(self):
        t = self.final_take()
        up = U.plan_upscale(self.ep, t)
        g = U.upscale_graph(self.base(), up)
        U.start(up)
        qid = self.runner.enqueue_finish(F.of_upscale(up, g), "local")
        sc = T.read_sidecar(t.paths.up_sidecar)
        self.assertEqual((sc["status"], sc["backend"], sc["queue"], sc["comfy_prompt_id"]),
                         ("queued", "local", "seriesmith", qid))
        job = self.finished(qid)
        self.assertEqual(job.status, "succeeded", (job.error, job.log))

        sent = self.fb.submitted[0]
        self.assertEqual(RD.episode_bound(sent), [])
        kinds = {v["class_type"] for v in sent.values()}
        self.assertTrue({"SeriesmithLoadTakeLatent", "SeriesmithShotLoader", F.SAVER} <= kinds)
        self.assertFalse(kinds & {"H3LoadTakeLatent", "H3ShotListLoader", F.H3_SAVER})
        src = next(v for v in sent.values() if v["class_type"] == "SeriesmithLoadTakeLatent")
        self.assertIsInstance(src["inputs"]["latent"], File)
        self.assertEqual(os.path.normcase(src["inputs"]["latent"].path), os.path.normcase(t.paths.latent))
        loader = next(v for v in sent.values() if v["class_type"] == "SeriesmithShotLoader")["inputs"]
        self.assertEqual(json.loads(loader["shotlist"]), T.read_json(t.paths.shotlist))
        self.assertEqual(loader["resolution_override"], f"{up.width}x{up.height}")
        save = sent[F.SAVER if F.SAVER in sent else "up_save"]["inputs"]
        self.assertEqual(os.path.normcase(save["source"].path), os.path.normcase(t.paths.mp4))
        self.assertEqual(save["name"], os.path.basename(t.paths.up_mp4)[:-4])
        self.assertTrue(save["last_frame"])

        with open(t.paths.up_mp4, "rb") as fh:
            self.assertEqual(fh.read(), b"upscaled")
        with open(t.paths.up_last, "rb") as fh:
            self.assertEqual(fh.read(), b"last")
        rec = T.upscale_of(T.get_take(self.ep, "final", "sh010", 1))
        self.assertEqual((rec["status"], rec["mp4"], rec["width"], rec["encoder"]),
                         ("ok", os.path.basename(t.paths.up_mp4), 1536, "h264_nvenc"))
        self.assertEqual(rec["scale"], up.scale)                     # the queuer's fields kept
        self.assertIn(("seriesmith.upscale", {"ep": self.ep, "shot": "sh010", "take": 1,
                                          "status": "ok"}), self.events)

    def test_a_failed_save_fails_the_upscale(self):
        self.fb.outputs = lambda g: saver_outputs(g, status="failed")
        t = self.final_take()
        up = U.plan_upscale(self.ep, t)
        U.start(up)
        job = self.finished(self.runner.enqueue_finish(F.of_upscale(up, U.upscale_graph(self.base(), up)),
                                                       "local"))
        self.assertEqual(job.status, "failed")
        self.assertEqual(T.read_sidecar(t.paths.up_sidecar)["status"], "failed")

    def test_cancelled_before_it_ran(self):
        self.runner.queue.pause("local")
        t = self.final_take()
        up = U.plan_upscale(self.ep, t)
        U.start(up)
        qid = self.runner.enqueue_finish(F.of_upscale(up, U.upscale_graph(self.base(), up)), "local")
        self.runner.queue.cancel(qid)
        sc = T.read_sidecar(t.paths.up_sidecar)
        self.assertEqual((sc["status"], sc["save_notes"]), ("failed", "canceled before it ran"))
        self.assertEqual(self.fb.submitted, [])


class PortableTest(ApiTest):
    """finishing.portable on the nodes decided when the job starts."""
    final_take = P13.UpscaleTest.final_take

    def fin(self, g, t):
        return F.Finish("upscale", self.ep, t, g, t.paths.up_sidecar, t.paths.up_mp4)

    def saver(self, t):
        return {"class_type": F.H3_SAVER, "inputs": {
            "images": ["1", 0], "project_root": self.ep, "source_mp4": os.path.relpath(t.paths.mp4, self.ep),
            "out_mp4": os.path.relpath(t.paths.up_mp4, self.ep), "fps": 24.0,
            "sidecar": os.path.relpath(t.paths.up_sidecar, self.ep), "encoder": "auto",
            "chain_hold": ["9", 1]}}

    def test_continuity_frame_the_previous_upscale_or_the_keyframe(self):
        t = self.final_take()
        key = os.path.join(self.ep, "refs", "key.png")
        os.makedirs(os.path.dirname(key), exist_ok=True)
        with open(key, "wb") as fh:
            fh.write(b"key")
        sha = T.file_sha1(key)
        T.update_sidecar(t.paths.sidecar, inputs={"first": f"h3pipe/{sha[:20]}.png"},
                         refs=[{"slot": "first", "role": "first", "path": "refs/key.png", "sha1": sha}])
        t = T.get_take(self.ep, "final", "sh010", 1)
        prev = os.path.join(self.ep, "prev.up_last.png")
        g = {"1": {"class_type": "H3LoadTakeFrame", "inputs": {
            "project_root": self.ep, "image_file": "prev.up_last.png",
            "fallback": f"h3pipe/{sha[:20]}.png"}}}
        out, _ = F.portable(self.fin(g, t))                        # not there yet: the keyframe
        self.assertEqual(out["1"]["class_type"], "LoadImage")
        self.assertEqual(os.path.normcase(out["1"]["inputs"]["image"].path), os.path.normcase(key))
        with open(prev, "wb") as fh:
            fh.write(b"up")
        out, _ = F.portable(self.fin(g, t))                        # there: the upscale's last frame
        self.assertEqual(os.path.normcase(out["1"]["inputs"]["image"].path), os.path.normcase(prev))

    def test_a_held_upscale_holds_the_previous_upscales_latent_if_it_is_there(self):
        t = self.final_take()
        prev = os.path.join(self.ep, "sh005_t02.up.latent.safetensors")
        g = {"1": {"class_type": "Sampler", "inputs": {"latent_image": ["9", 0]}},
             "8": {"class_type": "EmptyLatent", "inputs": {}},
             "9": {"class_type": "H3ChainLatent", "inputs": {
                 "latent": ["8", 0], "project_root": self.ep, "shot": "sh010", "pass_": "final",
                 "overlap": 39, "hold_audio": False, "fps": 24.0, "missing_ok": True,
                 "previous_latent": os.path.basename(prev)}},
             "up_save": self.saver(t)}
        out, _ = F.portable(self.fin(g, t))                        # not there: unheld
        self.assertNotIn("9", out)
        self.assertEqual(out["1"]["inputs"]["latent_image"], ["8", 0])
        self.assertNotIn("chain_hold", out["up_save"]["inputs"])
        with open(prev, "wb") as fh:
            fh.write(b"lat")
        fin = self.fin(g, t)
        out, _ = F.portable(fin)
        self.assertEqual(out["9"]["class_type"], "SeriesmithChainLatent")
        self.assertEqual(out["9"]["inputs"]["previous"].path, prev)
        self.assertEqual(json.loads(out["9"]["inputs"]["source"])["shot"], "sh005")
        self.assertEqual(out["up_save"]["inputs"]["chain_hold"], ["9", 1])
        self.assertEqual(RD.episode_bound(out), [])


class PostQueueTest(ApiTest):
    final_take = P13.UpscaleTest.final_take
    upscaled = TP.PostTest.upscaled
    ready_comfy = TP.PostTest.ready_comfy

    def queue_on(self):
        """seriesmith's queue for what follows (the take was rendered without it)."""
        self.fb = FakeBackend("local", "local", outputs=saver_outputs)
        self.ctx.runner = Runner(Queue(), {"local": self.fb},
                                 emit=lambda e, d: self.events.append((e, d)))
        self.addCleanup(setattr, T, "MANAGED", None)

    def test_a_post_through_the_queue_is_stamped_with_its_upscale(self):
        self.ready_comfy()
        t = self.upscaled()
        self.queue_on()
        out = self.ok(A.queue_post(self.ctx, {"ep": self.ep, "takes": [{"shot": "sh010", "take": 1}],
                                              "enhance": "draft"}))
        qid = out["queued"][0]["prompt_id"]
        q = self.ctx.runner.queue
        wait_for(lambda: q.jobs[qid].status in ("succeeded", "failed"))
        self.assertEqual(q.jobs[qid].status, "succeeded", q.jobs[qid].log)
        sent = self.fb.submitted[0]
        video = next(v for v in sent.values() if v["class_type"] == "SeriesmithLoadTakeVideo")
        self.assertEqual(os.path.normcase(video["inputs"]["video"].path), os.path.normcase(t.paths.up_mp4))
        with open(t.paths.post_mp4, "rb") as fh:
            self.assertEqual(fh.read(), b"upscaled")
        po = T.post_of(T.get_take(self.ep, "final", "sh010", 1))
        self.assertEqual((po["status"], po["mp4"]), ("ok", os.path.basename(t.paths.post_mp4)))
        self.assertTrue(po["fresh"])                                   # stamped with the upscale
        self.assertIn(("seriesmith.post", {"ep": self.ep, "shot": "sh010", "take": 1,
                                       "status": "ok"}), self.events)

    def test_a_backend_not_set_up_is_an_error(self):
        self.ready_comfy()
        self.upscaled()
        out = self.ok(A.queue_post(self.ctx, {"ep": self.ep, "takes": [{"shot": "sh010", "take": 1}],
                                              "enhance": "draft", "backend": "cloud"}))
        self.assertEqual(out["queued"], [])
        self.assertIn("cloud isn't set up", out["errors"][0]["error"])

if __name__ == "__main__":
    unittest.main()
