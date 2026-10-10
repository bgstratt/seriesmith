"""
Refs through seriesmith's queue (runner.Runner.enqueue_ref): the workflow keeps
its own SaveImage, the reference pictures go up as uploads, and the picture the
backend hands back closes the ref take. On the fake backend.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from seriesmith import jobs as J  # noqa: E402
from seriesmith import refs as R  # noqa: E402
from seriesmith import takes as T  # noqa: E402
from seriesmith.backends import File, files_in  # noqa: E402
from seriesmith.backends.fake import FakeBackend  # noqa: E402
from seriesmith.queue import Queue  # noqa: E402
from seriesmith.runner import Runner  # noqa: E402
from test_refs import REFS_WF, built_episode  # noqa: E402
from test_render import png_bytes  # noqa: E402

LANE = "deployment:krea2"


def saved_picture(graph: dict) -> dict:
    """What a SaveImage node reports: one PNG."""
    node = next(k for k, v in graph.items() if v["class_type"] == "SaveImage")
    return {node: [("ComfyUI_00001_.png", "image", png_bytes(64, 48))],
            "99": [("preview.png", "image", png_bytes(8, 8))]}


def wait_for(cond, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return
        time.sleep(0.02)
    raise AssertionError("timed out")


class RefQueueTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ep = os.path.join(self._tmp.name, "ks01")
        shutil.copytree(built_episode(), self.ep)
        self.s = R.load_series(self.ep)
        self.events = []
        self.queue = Queue(lambda e, d: self.events.append((e, d)))
        self.addCleanup(setattr, T, "MANAGED", None)

    def generate(self, fb, ref="subject:kettle", **kw):
        runner = Runner(self.queue, {fb.name: fb}, lambda e, d: self.events.append((e, d)))
        return R.queue_generate(self.s, R.GenRequest(ref, None, **kw), None,
                                J.load_graph(REFS_WF), runner=runner, backend="deployment")

    def test_a_ref_is_made_on_its_backend(self):
        fb = FakeBackend(LANE, "deployment", outputs=saved_picture)
        res = self.generate(fb)
        self.assertEqual(res["errors"], [])
        (q,) = res["queued"]
        self.assertEqual(q["backend"], LANE)
        job = self.queue.jobs[q["prompt_id"]]
        wait_for(lambda: job.status in ("succeeded", "failed"))
        self.assertEqual(job.status, "succeeded", job.error)
        ref = R.find_ref(self.s, "subject:kettle")
        take = R.get_take(ref, None, q["take"])
        self.assertEqual(take.sidecar["status"], "ok")
        self.assertEqual((take.sidecar["width"], take.sidecar["height"]), (64, 48))
        self.assertEqual((take.sidecar["queue"], take.sidecar["backend"]), ("seriesmith", LANE))
        self.assertTrue(os.path.isfile(take.paths.image))
        # the graph kept its own SaveImage and points at nothing on this disk
        (g,) = fb.submitted
        kinds = {v["class_type"] for v in g.values()}
        self.assertIn("SaveImage", kinds)
        self.assertNotIn("H3SaveRefTake", kinds)
        self.assertFalse(any("sidecar" in (v.get("inputs") or {}) for v in g.values()))
        self.assertIn(("h3pipe.ref", {"ep": self.ep, "ref": "subject:kettle", "view": None,
                                      "take": q["take"], "status": "ok"}), self.events)

    def test_a_failed_job_fails_the_take(self):
        fb = FakeBackend(LANE, "deployment", final="failed", error="out of memory")
        (q,) = self.generate(fb)["queued"]
        job = self.queue.jobs[q["prompt_id"]]
        wait_for(lambda: job.status == "failed")
        take = R.get_take(R.find_ref(self.s, "subject:kettle"), None, q["take"])
        self.assertEqual(take.sidecar["status"], "failed")
        self.assertIn("out of memory", take.sidecar["save_notes"])

    def test_staged_pictures_become_uploads(self):
        collector = J.InputCollector(keep_dir=os.path.join(self._tmp.name, "kept"))
        src = os.path.join(self._tmp.name, "temp.png")
        with open(src, "wb") as fh:
            fh.write(png_bytes(4, 4))
        collector.upload_input(src, "h3pipe/abc.png")
        os.remove(src)                       # the caller cleans up; the kept copy stays
        g = {"1": {"class_type": "LoadImage", "inputs": {"image": "h3pipe/abc.png"}}}
        J.files_as_uploads(g, collector.files)
        (f,) = [f for _, _, f in files_in(g)]
        self.assertIsInstance(f, File)
        self.assertTrue(os.path.isfile(f.path))


if __name__ == "__main__":
    unittest.main()
