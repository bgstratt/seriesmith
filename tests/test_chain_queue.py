"""
`continuous: latent` through seriesmith's queue: a chain queued at once runs in
order (each job waits for the one it continues, even on a lane that runs
several at once), and each chained graph holds the take the cut uses when its
job starts, sent as uploads to SeriesmithChainLatent -- nothing reads the
episode folder. On the fake backend.
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

from seriesmith import edit as E  # noqa: E402
from seriesmith import jobs as J  # noqa: E402
from seriesmith import render  # noqa: E402
from seriesmith import takes as T  # noqa: E402
from seriesmith.backends import File  # noqa: E402
from seriesmith.backends.fake import FakeBackend  # noqa: E402
from seriesmith.queue import Queue  # noqa: E402
from seriesmith.runner import Runner  # noqa: E402
from fakes import saver_outputs  # noqa: E402
from test_render import stub_refs  # noqa: E402

FIXTURE = os.path.join(HERE, "fixtures", "continuous")
LANE = "deployment:minimax_h3_ref2va"


def wait_for(cond, timeout=15.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return
        time.sleep(0.02)
    raise AssertionError("timed out")


class ChainQueueTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ep = os.path.join(self._tmp.name, "ct01")
        os.makedirs(self.ep)
        shutil.copy(os.path.join(FIXTURE, "series.json"), self.ep)
        shutil.copy(os.path.join(FIXTURE, "script.md"), os.path.join(self.ep, "ct01.md"))
        r = E.build_episode(self.ep)
        self.assertTrue(r["ok"], r)
        stub_refs(self.ep)
        self.addCleanup(setattr, T, "MANAGED", None)

    def test_a_chain_queued_at_once_holds_each_previous_take(self):
        fb = FakeBackend(LANE, "deployment", outputs=saver_outputs, progress=[0.5, 1.0])
        q = Queue()
        runner = Runner(q, {fb.name: fb})
        base, _ = J.target_workflow(J.TG.load_target("minimax_h3_ref2va", "video"), None, None)
        res = E.queue_shots(self.ep, "final", ["sh070", "sh080", "sh090"],
                            J.RenderRequest(""), None, base, runner=runner,
                            backend="deployment")
        self.assertEqual(res["errors"], [])
        by = {x["shot"]: x for x in res["queued"]}
        jobs = {s: q.jobs[by[s]["prompt_id"]] for s in by}
        self.assertEqual((jobs["sh080"].after, jobs["sh090"].after),
                         (jobs["sh070"].id, jobs["sh080"].id))
        wait_for(lambda: all(j.status in ("succeeded", "failed") for j in jobs.values()))
        for s, j in jobs.items():
            self.assertEqual(j.status, "succeeded", (s, j.error, j.log))
        # in order, each after the one it continues
        self.assertLess(jobs["sh070"].finished, jobs["sh080"].started)
        self.assertLess(jobs["sh080"].finished, jobs["sh090"].started)

        graphs = {}
        for g in fb.submitted:
            shot = next(v for v in g.values() if v["class_type"] == J.PORTABLE_LOADER)
            graphs[__import__("json").loads(shot["inputs"]["shotlist"])["shots"][0]["id"]] = g
        self.assertNotIn("SeriesmithChainLatent", {v["class_type"] for v in graphs["sh070"].values()})
        for shot, prev in (("sh080", "sh070"), ("sh090", "sh080")):
            g = graphs[shot]
            kinds = {v["class_type"] for v in g.values()}
            self.assertIn("SeriesmithChainLatent", kinds)
            self.assertIn("SeriesmithChainTrim", kinds)
            self.assertNotIn("H3ChainLatent", kinds)
            self.assertEqual(render.episode_bound(g), [])
            chain = next(v for v in g.values() if v["class_type"] == "SeriesmithChainLatent")
            before = T.get_take(self.ep, "final", prev, by[prev]["take"])
            self.assertIsInstance(chain["inputs"]["previous"], File)
            self.assertEqual(os.path.normcase(chain["inputs"]["previous"].path),
                             os.path.normcase(before.paths.latent))
            self.assertEqual(os.path.normcase(chain["inputs"]["previous_video"].path),
                             os.path.normcase(before.paths.mp4))
            self.assertIn(f'"shot": "{prev}"', chain["inputs"]["source"])
            self.assertEqual(chain["inputs"]["overlap"], 39)
        self.assertTrue(any("holds sh070" in line for line in jobs["sh080"].log))


if __name__ == "__main__":
    unittest.main()
