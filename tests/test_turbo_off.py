"""
The turbo turned off (`lora: none` on a pass whose LoRA slot holds an
accelerator) renders the full model: the pass's base preset (its steps and
sampler, no LoRA), as when the turbo isn't installed; a shot's own steps
still win, and the sparse attention stays. `sla: off` (a shot, a sequence, a
profile, the series) is what leaves H3's sparse attention out.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import json  # noqa: E402

from seriesmith import jobs as J  # noqa: E402
from seriesmith.core import story as ST  # noqa: E402
from seriesmith.core.story import ScriptError  # noqa: E402
from test_render import FIXTURE  # noqa: E402
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
        g = self.graph(job)
        kinds = [v["class_type"] for v in g.values()]
        self.assertIn("H3SLAAttention", kinds)              # the sparse attention stays
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


class SlaTest(TurboOffTest):
    def series(self, **series):
        cfg = json.load(open(os.path.join(FIXTURE, "series.json"), encoding="utf-8"))
        cfg.setdefault("series", {}).update(series)
        with open(os.path.join(self.root, "series.json"), "w", encoding="utf-8") as fh:
            json.dump(cfg, fh)

    def test_sla_off_leaves_the_sparse_attention_out(self):
        self.series(sla="off")
        job = self.job()
        self.assertTrue(any("H3SLAAttention left out (sla: off)" in n for n in job.notes), job.notes)
        kinds = [v["class_type"] for v in self.graph(job).values()]
        self.assertNotIn("H3SLAAttention", kinds)
        self.assertIn("LoraLoaderModelOnly", kinds)          # the turbo stays: they're separate

    def test_on_is_the_default(self):
        self.series()
        self.assertEqual(J.shot_sla(self.job()), None)
        self.assertIn("H3SLAAttention", [v["class_type"] for v in self.graph(self.job()).values()])

    def test_the_script_says_it(self):
        text = """= ep01  T

# sq01  porch
sla: off

## sh010
size: wide
dur: 3
Rain.

## sh020
sla: on
size: wide
dur: 3
Rain.
"""
        story = ST.parse_story(text, set(), set())
        seq = story.sequences[0]
        self.assertEqual((seq.sla, seq.shots[0].sla, seq.shots[1].sla), ("off", None, "on"))
        self.assertEqual(seq.to_json()["sla"], "off")
        self.assertNotIn("sla", seq.shots[0].to_json())      # only when set: old stories unchanged
        with self.assertRaises(ScriptError):
            ST.parse_story(text.replace("sla: off", "sla: maybe"), set(), set())


if __name__ == "__main__":
    unittest.main()
