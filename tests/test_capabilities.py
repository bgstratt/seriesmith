"""
What a target can do, as the core and a picker see it (Target.capabilities):
where its jobs can run, whether a take can be made again, how many subjects
and voices a shot can carry, and whether a take keeps its latent
(docs/DESIGN.md, "Capabilities").
"""
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from seriesmith import targets as TG  # noqa: E402


def target(**caps) -> TG.Target:
    """A minimal video target with `caps` as its target.json capabilities."""
    return TG.Target(HERE, {"id": "probe", "kind": "video", "capabilities": caps})


class BackendsTest(unittest.TestCase):
    def test_a_workflow_target_runs_locally_or_on_a_deployment(self):
        for t in TG.list_targets():
            if t.spec.get("router"):
                continue                        # a hosted model: RouterTargetTest
            with self.subTest(target=t.id):
                self.assertEqual(t.capabilities()["backends"], ["local", "deployment"])

    def test_a_target_can_name_its_own(self):
        self.assertEqual(target(backends=["router"]).backends, ["router"])
        self.assertEqual(target(backends="cloud").backends, ["cloud"])

    def test_an_unknown_backend_is_refused_when_the_target_loads(self):
        with self.assertRaises(TG.TargetError) as cm:
            target(backends=["local", "runpod"])
        self.assertIn("'runpod' is not a backend", str(cm.exception))


class RouterTargetTest(unittest.TestCase):
    def test_a_hosted_model_runs_on_router_and_promises_no_repeat(self):
        c = TG.load_target("seedance_2_5", "video").capabilities()
        self.assertEqual((c["backends"], c["reproducible"]), (["router"], False))
        self.assertEqual(c["max_subjects"], 4)
        self.assertEqual(c["continuous"], ["first"])
        self.assertFalse(c["latents"])


class ReproducibleTest(unittest.TestCase):
    def test_a_fixed_seed_is_the_default(self):
        self.assertTrue(target().reproducible)

    def test_a_hosted_model_says_its_provider_decides(self):
        self.assertFalse(target(seed="provider").reproducible)
        self.assertFalse(target(seed="provider").capabilities()["reproducible"])


class VideoCapabilitiesTest(unittest.TestCase):
    def caps(self, target_id: str) -> dict:
        return TG.load_target(target_id, "video").capabilities()

    def test_h3_takes_three_subjects_and_three_voices_and_chains_latents(self):
        c = self.caps("minimax_h3_ref2va")
        self.assertEqual((c["max_subjects"], c["max_voices"]), (3, 3))
        self.assertEqual(c["continuous"], ["latent"])
        self.assertTrue(c["latents"])

    def test_a_reference_sheet_has_no_fixed_subject_limit(self):
        for t in ("ltx2", "ltx2_ingredients", "wan22_vace"):
            with self.subTest(target=t):
                self.assertIsNone(self.caps(t)["max_subjects"])

    def test_a_keyframe_target_takes_no_subjects_and_continues_from_a_first_frame(self):
        for t in ("minimax_h3_fl2va", "wan22_i2v", "wan22_ti2v"):
            with self.subTest(target=t):
                c = self.caps(t)
                self.assertEqual((c["max_subjects"], c["max_voices"]), (0, 0))
                self.assertEqual(c["continuous"], ["first"])
                self.assertFalse(c["latents"])

    def test_target_json_can_say_so_itself(self):
        c = target(max_subjects=6, max_voices=2, latents=True).capabilities()
        self.assertEqual((c["max_subjects"], c["max_voices"], c["latents"]), (6, 2, True))


if __name__ == "__main__":
    unittest.main()
