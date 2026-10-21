"""
targets.moderate: a hosted (moderated) model is told a subject's design without
what describes a body, in the prose and in a reference picture's prompt; a
local model keeps the design as written; places are untouched.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
from seriesmith import jobs as J  # noqa: E402
from seriesmith import refs as R  # noqa: E402
from seriesmith import targets as TG  # noqa: E402
from seriesmith.targets import moderate as MOD  # noqa: E402
from test_render import FIXTURE, build_episode  # noqa: E402

CINDY = ("a young woman large round breasts pushing out of the top of her dress with blonde hair "
         "swept up into a loose bun, a small silver tiara, a pale-blue off-the-shoulder corseted "
         "gown, white lace-topped stockings and clear glass heels")
ELLA = ("a woman with green skin and long curly bright-red hair under a tall pointed black "
        "witch's hat, a black off-the-shoulder ruffled crop top, large breasts and extreme "
        "cleavage pushing out of her top, a short tiered black ruffled skirt")
BODY = ("breast", "cleavage", "busty", "curvy")


class ModerateTest(unittest.TestCase):
    def test_a_design_keeps_its_category_hair_and_wardrobe(self):
        self.assertEqual(MOD.moderate(CINDY),
                         "a young woman with blonde hair swept up into a loose bun, a small silver "
                         "tiara, a pale-blue off-the-shoulder corseted gown, white lace-topped "
                         "stockings and clear glass heels")
        self.assertEqual(MOD.moderate(ELLA),
                         "a woman with green skin and long curly bright-red hair under a tall "
                         "pointed black witch's hat, a black off-the-shoulder ruffled crop top, "
                         "a short tiered black ruffled skirt")
        clean = "a stocky teenage boy with a shaved head, an oversized green bomber jacket."
        self.assertEqual(MOD.moderate(clean), clean)                        # as written

    def test_the_config_moderates_subjects_only_and_leaves_the_original(self):
        cfg = {"subjects": {"c": {"name": "C", "design": CINDY}},
               "locations": {"x": {"description": "a hall, its curves of marble"}}}
        before = copy.deepcopy(cfg)
        told = MOD.moderated_config(cfg)
        self.assertNotIn("breasts", told["subjects"]["c"]["design"])
        self.assertEqual(told["locations"], cfg["locations"])
        self.assertEqual(cfg, before)

    def test_hosted_models_are_moderated_local_ones_are_not(self):
        for tid, kind in (("seedance_2_5", "video"), ("kling_v3_omni", "video"),
                          ("seedream_5_0", "image"), ("nano_banana_pro", "image")):
            self.assertTrue(TG.load_target(tid, kind).moderated, tid)
        for tid, kind in (("ltx2", "video"), ("minimax_h3_ref2va", "video"), ("krea2", "image")):
            self.assertFalse(TG.load_target(tid, kind).moderated, tid)
        t = copy.copy(TG.load_target("seedance_2_5", "video"))
        t.spec = dict(t.spec, capabilities=dict(t.spec.get("capabilities") or {}, moderated=False))
        self.assertFalse(t.moderated)                                       # target.json says so


class EpisodeTest(unittest.TestCase):
    """The same shot told to a hosted and a local model, and a reference
    picture's prompt on a hosted and a local picture model."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        build_episode(self.root)
        shutil.copy(os.path.join(FIXTURE, "series.json"), self.root)
        path = os.path.join(self.root, "series.json")
        with open(path, encoding="utf-8") as fh:
            cfg = json.load(fh)
        cfg["subjects"]["ada"]["design"] = ("a busty woman with a short grey bob, large breasts, "
                                            "a mustard apron over a striped shirt")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh)
        # built again from it: the shot's own (local) entry says the design as written
        from seriesmith import build
        build.main([path, os.path.join(FIXTURE, "script.md"), "-o", self.root])

    def prompt(self, tid: str) -> str:
        doc, i = J.find_shot(self.root, "final", "sh010")
        job = J.plan_job(self.root, "final", doc, i, J.RenderRequest("sh010", target=tid), {})
        return J._prompt_text(job.prompt)

    def test_the_prose(self):
        hosted, local = self.prompt("seedance_2_5"), self.prompt(None)    # None: its own, local
        self.assertFalse([w for w in BODY if w in hosted.lower()], hosted)
        self.assertIn("a mustard apron over a striped shirt", hosted)
        self.assertIn("large breasts", local)                               # as written

    def test_a_reference_pictures_prompt(self):
        s = R.load_series(self.root)
        ada = R.find_ref(s, "subject:ada")
        view = R.VIEW_TAGS[0]
        hosted = R.built_prompt(s, ada, view, target=TG.load_target("seedream_5_0", "image"))
        local = R.built_prompt(s, ada, view, target=TG.load_target("krea2", "image"))
        self.assertFalse([w for w in BODY if w in hosted.lower()], hosted)
        self.assertIn("mustard apron", hosted)
        self.assertIn("large breasts", local)


if __name__ == "__main__":
    unittest.main(verbosity=2)
