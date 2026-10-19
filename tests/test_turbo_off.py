"""
The turbo turned off (`lora: none` on a pass whose LoRA slot holds an
accelerator) renders the full model: the pass's base preset (its steps and
sampler, no LoRA), and what goes with the turbo left out too (H3's sparse
attention, which the turbo LoRAs were distilled against), as when the turbo
isn't installed. A shot's own steps still win; with the turbo on nothing
changes.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from seriesmith import jobs as J  # noqa: E402
from test_render import build_episode  # noqa: E402
from test_render_take import h3_shot  # noqa: E402


class TurboOffTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        build_episode(self.root)
        self.doc = J.load_shotlist(self.root, "final")
        self.index = h3_shot(self.doc)
        self.shot_id = self.doc["shots"][self.index]["id"]
        self.base, _ = J.resolve_workflow(None, J.WORKFLOW_NAME, None, prefer_repo=True)

    def job(self, **req) -> J.Job:
        job = J.plan_job(self.root, "final", self.doc, self.index,
                         J.RenderRequest(self.shot_id, **req), {})
        # no ComfyUI to ask: nothing is resolved against its files (listing None)
        J.resolve_models(job, None, resolve=None, cache=None, extra={})
        return job

    def graph(self, job: J.Job) -> dict:
        return J.graph_for(self.base, job, J.start_job(job))

    def test_lora_none_renders_the_full_model(self):
        job = self.job(loras=[])
        self.assertTrue(job.based)
        self.assertEqual(job.steps, 20)
        self.assertTrue(any("turbo off (lora: none)" in n for n in job.notes), job.notes)
        self.assertTrue(any("H3SLAAttention left out" in n for n in job.notes), job.notes)
        g = self.graph(job)
        kinds = [v["class_type"] for v in g.values()]
        self.assertNotIn("H3SLAAttention", kinds)
        self.assertNotIn("LoraLoaderModelOnly", kinds)
        self.assertEqual([v["inputs"]["sampler_name"] for v in g.values() if v["class_type"] == "KSamplerSelect"],
                         ["res_multistep"])

    def test_a_shots_own_steps_win(self):
        job = self.job(loras=[], steps=12)
        self.assertTrue(job.based)
        self.assertEqual(job.steps, 12)

    def test_with_the_turbo_on_nothing_changes(self):
        job = self.job()
        self.assertFalse(job.based)
        g = self.graph(job)
        self.assertIn("H3SLAAttention", [v["class_type"] for v in g.values()])
        self.assertFalse(any("turbo off" in n for n in job.notes))


if __name__ == "__main__":
    unittest.main()
