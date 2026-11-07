"""
Editing a ref's picture (refs.plan_edit): a take, or the live picture, changed
as an instruction says, on an edit target, as a new take of the same ref and
view -- with other refs' pictures brought in for the change.
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

from seriesmith import jobs as J  # noqa: E402
from seriesmith import refs as R  # noqa: E402
from test_render import png_bytes  # noqa: E402

FIXTURE = os.path.join(HERE, "fixtures", "kitchen_sink")


class EditTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ep = os.path.join(self._tmp.name, "ks01")
        os.makedirs(self.ep)
        shutil.copy(os.path.join(FIXTURE, "series.json"), self.ep)
        shutil.copy(os.path.join(FIXTURE, "script.md"), os.path.join(self.ep, "ks01.md"))
        from seriesmith import edit as E
        self.assertTrue(E.build_episode(self.ep)["ok"])
        s = R.load_series(self.ep)
        self.plate = os.path.join(self._tmp.name, "plate.png")
        with open(self.plate, "wb") as fh:
            fh.write(png_bytes(1344, 768))
        view = os.path.join(self._tmp.name, "view.png")
        with open(view, "wb") as fh:
            fh.write(png_bytes(64, 64))
        kitchen = R.find_ref(s, "location:kitchen")
        R.pick_take(s, kitchen, None, R.import_take(s, kitchen, None, self.plate).take)
        ada = R.find_ref(s, "subject:ada")
        for v in R.VIEW_TAGS:
            R.pick_take(s, ada, v, R.import_take(s, ada, v, view).take)
        self.s = R.load_series(self.ep)

    def tearDown(self):
        self._tmp.cleanup()

    def plan(self, ref="location:kitchen", view=None, prompt="make it night", **kw):
        target = kw.pop("target", "flux2_klein_edit")
        edit = kw.pop("edit", {"take": None})
        return R.plan_generate(self.s, R.GenRequest(ref, view, prompt=prompt, edit=edit,
                                                    target=target, **kw),
                               rng=random.Random(0))

    def test_the_live_picture_is_image_1(self):
        (job,) = self.plan()
        self.assertEqual(len(job.references), 1)
        self.assertEqual(job.references[0]["role"], "source")
        self.assertEqual(job.references[0]["ref"], "location:kitchen")
        self.assertTrue(job.prompt.startswith("Edit the image: make it night."))
        self.assertIn("Keep everything the instruction doesn't change exactly as it is in the image", job.prompt)
        self.assertEqual((job.width, job.height), (1344, 768))     # its own size
        self.assertEqual(job.edit["instruction"], "make it night")
        self.assertIsNone(job.edit["take"])

    def test_a_named_take_and_a_picture_brought_in(self):
        (job,) = self.plan(edit={"take": 1, "with": [{"ref": "subject:ada"}]},
                           prompt="put Ada at the counter")
        self.assertEqual([r.get("ref") for r in job.references],
                         ["location:kitchen", "subject:ada"])
        self.assertEqual(job.references[1]["view"], "01_threequarter")
        self.assertIn("Edit image 1: put Ada at the counter.", job.prompt)
        self.assertIn("Image 2 is Ada:", job.prompt)
        self.assertEqual(job.edit["with"], [{"ref": "subject:ada", "view": "01_threequarter"}])

    def test_a_character_view_is_edited_one_view_at_a_time(self):
        (job,) = self.plan("subject:ada", "02_side", prompt="give her a red scarf")
        self.assertEqual(job.view, "02_side")
        self.assertEqual(job.references[0]["view"], "02_side")
        # a small picture goes up to the target's minimum, on its grid
        self.assertEqual((job.width, job.height), R.scaled_size(job.target, 64, 64))
        self.assertGreater(job.width, 800)
        self.assertEqual(job.width % 16, 0)
        self.assertIn("edited at", job.notes[0])
        with self.assertRaisesRegex(R.RefError, "one view at a time"):
            self.plan("subject:ada", None)

    def test_unwrapped_sends_the_instruction_as_typed(self):
        (job,) = self.plan(prompt="<mva> front-left quarter view, elevated shot",
                           edit={"take": None, "wrap": False}, target="qwen_image_21")
        self.assertEqual(job.prompt, "<mva> front-left quarter view, elevated shot")

    def test_candidates_get_new_seeds_and_a_typed_one_is_kept(self):
        a, b = self.plan(count=2, seed=7)
        self.assertEqual((a.seed, a.seed_source), (7, "typed"))
        self.assertEqual(b.seed_source, "new")

    def test_the_default_target_is_one_that_can_edit(self):
        (job,) = self.plan(target=None)
        self.assertTrue(R.is_edit_target(job.target))

    def test_the_edit_model_is_a_setting_of_its_own(self):
        # nothing chosen: Qwen 2.1, and FLUX.3 Klein for a character
        d = R.image_defaults(self.s)
        self.assertEqual((d["edit_target"], d["edit_target_person"], d["edit_target_source"]),
                         ("qwen_image_21", "flux3_klein", "default"))
        # the series config's refs.edit_target
        cfg_path = os.path.join(self.ep, "series.json")
        with open(cfg_path, encoding="utf-8") as fh:
            cfg = json.load(fh)
        cfg["refs"] = {"edit_target": "qwen_image_21"}
        with open(cfg_path, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh)
        self.s = R.load_series(self.ep)
        d = R.image_defaults(self.s)
        self.assertEqual((d["edit_target"], d["edit_target_source"]), ("qwen_image_21", "series"))
        (job,) = self.plan(target=None)
        self.assertEqual(job.target.id, "qwen_image_21")
        # the episode's choice beats it
        R.set_image_defaults(self.ep, {"edit_target": "flux_kontext"})
        d = R.image_defaults(self.s)
        self.assertEqual((d["edit_target"], d["edit_target_source"]), ("flux_kontext", "editor"))
        self.assertEqual(self.plan(target=None)[0].target.id, "flux_kontext")
        # a model that only draws from text is refused, in the episode and the series config
        with self.assertRaisesRegex(R.RefError, "can't edit a picture"):
            R.set_image_defaults(self.ep, {"edit_target": "krea2"})
        cfg["refs"] = {"edit_target": "krea2"}
        with open(cfg_path, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh)
        with self.assertRaisesRegex(R.RefError, "refs.edit_target.*can edit a picture"):
            R.image_defaults(R.load_series(self.ep))
        R.set_image_defaults(self.ep, {"edit_target": None})
        from seriesmith import takes as T
        self.assertIsNone(T.episode_field(T.load_overrides(self.ep), "edit_target"))

    def test_the_built_in_edit_models(self):
        place = R.find_ref(self.s, "location:kitchen")
        person = next(r for r in R.series_refs(self.s) if r.kind == "character")
        self.assertEqual(R.edit_target_for(self.s, place).id, "qwen_image_21")
        self.assertEqual(R.edit_target_for(self.s, person).id, "flux3_klein")

        # each falls back to the other, then to the keyframe and refs targets that can edit
        def only(*ids):
            return lambda t: t.id in ids
        d = R.image_defaults(self.s, only("flux3_klein"))
        self.assertEqual((d["edit_target"], d["edit_target_person"]), ("flux3_klein", "flux3_klein"))
        d = R.image_defaults(self.s, only("qwen_image_21"))
        self.assertEqual((d["edit_target"], d["edit_target_person"]), ("qwen_image_21", "qwen_image_21"))
        d = R.image_defaults(self.s, only("flux2_klein_edit"))
        self.assertEqual((d["edit_target"], d["edit_target_person"]), ("flux2_klein_edit", "flux2_klein_edit"))

        # a choice is every edit's, a character's too
        R.set_image_defaults(self.ep, {"edit_target": "flux_kontext"})
        self.assertEqual(R.edit_target_for(self.s, person).id, "flux_kontext")
        self.assertEqual(R.image_defaults(self.s)["edit_target_person"], "flux_kontext")

    def test_edit_target_for_order(self):
        ref = R.find_ref(self.s, "location:kitchen")
        R.set_image_defaults(self.ep, {"edit_target": "qwen_image_21",
                                       "keyframe_target": "flux_kontext"})
        # the episode's edit model before its keyframe model
        self.assertEqual(R.edit_target_for(self.s, ref).id, "qwen_image_21")
        # the request's beats everything
        self.assertEqual(R.edit_target_for(self.s, ref, "flux2_klein_edit").id, "flux2_klein_edit")
        # the ref's own model, when it can edit, beats the episode's
        ov = R.set_ref_override(R.load_overrides(self.s.home), ref, None,
                                {"target": "flux_kontext"}, None)
        self.assertEqual(R.edit_target_for(self.s, ref, None, ov).id, "flux_kontext")
        # one that draws from text only is passed over
        ov = R.set_ref_override(R.load_overrides(self.s.home), ref, None,
                                {"target": "krea2"}, None)
        self.assertEqual(R.edit_target_for(self.s, ref, None, ov).id, "qwen_image_21")
        # no edit model chosen and neither built-in one ready: the keyframe model
        R.set_image_defaults(self.ep, {"edit_target": None})
        self.assertEqual(R.edit_target_for(self.s, ref, ready=lambda t: t.id == "flux_kontext").id,
                         "flux_kontext")

    def test_what_is_refused(self):
        bad = [
            ({"prompt": "  "}, "instruction"),
            ({"target": "krea2"}, "can't edit a picture"),
            ({"target": "flux_kontext", "edit": {"take": None, "with": [{"ref": "subject:ada"}]}},
             "at most 1 picture"),
            ({"edit": {"take": 99}}, "no take 99"),
            ({"edit": {"take": None, "zoom": 2}}, "not zoom"),
            ({"edit": {"take": "1"}}, "take number"),
            ({"edit": {"take": None, "wrap": "no"}}, "wrap"),
            ({"edit": {"take": None, "with": [{"ref": "voice:ada"}]}}, "a voice"),
        ]
        for kw, why in bad:
            with self.subTest(kw=kw), self.assertRaisesRegex((R.RefError, R.UnknownRef), why):
                self.plan(**kw)

    def test_the_take_records_what_it_was_edited_from(self):
        (job,) = self.plan(edit={"take": 1, "with": [{"ref": "subject:ada"}]})
        R.stage_references(self.s, job, None)
        take = R.start_gen(self.s, job)
        sc = take.sidecar
        self.assertEqual(sc["source"], "edited")
        self.assertEqual(sc["edit"]["take"], 1)
        self.assertEqual(sc["edit"]["instruction"], "make it night")
        self.assertEqual([r["ref"] for r in sc["references"]],
                         ["location:kitchen", "subject:ada"])
        ref = R.find_ref(self.s, "location:kitchen")
        js = R.take_json(self.ep, ref, R.get_take(ref, None, take.take))
        self.assertEqual(js["source"], "edited")
        self.assertEqual(js["edit"]["instruction"], "make it night")
        self.assertEqual(js["target"], "flux2_klein_edit")

    def test_the_qwen_graph_edits_from_the_picture(self):
        (job,) = self.plan(target="qwen_image_21")
        job.inputs = {"references": ["h3pipe/src.png"]}
        with open(os.path.join(ROOT, "seriesmith", "targets", "image", "qwen_image_21", "workflow.json"),
                  encoding="utf-8") as fh:
            g = R.image_graph(J.graph_from(json.load(fh)), job, None)
        enc = next(v for v in g.values() if v["class_type"] == "TextEncodeQwenImage21")
        self.assertIn("images.image_1", enc["inputs"])
        sw = next(v for v in g.values() if v["class_type"] == "ComfySwitchNode")
        self.assertIs(sw["inputs"]["switch"], False)

    def test_a_lora_comes_along(self):
        (job,) = self.plan(target="qwen_image_21",
                           loras=[{"name": "angles.safetensors", "strength": 0.9}])
        job.inputs = {"references": ["h3pipe/src.png"]}
        with open(os.path.join(ROOT, "seriesmith", "targets", "image", "qwen_image_21", "workflow.json"),
                  encoding="utf-8") as fh:
            g = R.image_graph(J.graph_from(json.load(fh)), job, None)
        lo = [v for v in g.values() if v["class_type"] == "LoraLoaderModelOnly"]
        self.assertEqual([v["inputs"]["lora_name"] for v in lo], ["angles.safetensors"])


if __name__ == "__main__":
    unittest.main()
