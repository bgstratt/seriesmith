"""
A show's change to how a model's prompt is written (<show>/targets/overrides.json), the preview
the Prompt & mapping panel shows, and the `mapping` stale reason (docs/PLAN.md step 15.3).
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from seriesmith import api as A  # noqa: E402
from seriesmith import jobs as J  # noqa: E402
from seriesmith import promptview as PV  # noqa: E402
from seriesmith import targets as TG  # noqa: E402
from seriesmith.core import fileio as F  # noqa: E402
from seriesmith.targets import prompt_template as TP  # noqa: E402
from test_render import FIXTURE, build_episode  # noqa: E402
from test_api import ApiTest  # noqa: E402

MODEL = "seedance_2_5"
MINE = "[[Look: {look}.]] {action}"


class Show(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(TG.forget_targets)
        self.root = self.tmp.name
        build_episode(self.root)
        shutil.copy(os.path.join(FIXTURE, "series.json"), self.root)
        TG.forget_targets()

    def save(self, target=MODEL, **fields):
        TG.save_show_overrides(self.root, target, fields)

    def load(self, target=MODEL):
        return TG.load_target(target, "video", root=self.root)


class Overrides(Show):
    def test_the_show_changes_the_model_and_only_for_itself(self):
        self.save(**{PV.TEMPLATE: MINE})
        self.assertEqual(TP.shot_template(self.load()), MINE)
        self.assertEqual(self.load().show_fields, {PV.TEMPLATE: MINE})
        other = tempfile.mkdtemp(dir=self.root + os.sep + "..")
        self.addCleanup(shutil.rmtree, other, True)
        self.assertNotEqual(TP.shot_template(TG.load_target(MODEL, "video", root=other)), MINE)
        self.assertNotEqual(TP.shot_template(TG.load_target(MODEL, "video")), MINE)

    def test_a_thread_root_counts_as_a_show_in_force(self):
        self.save(**{PV.TEMPLATE: MINE})
        with TG.use_roots(self.root):
            self.assertEqual(TP.shot_template(TG.load_target(MODEL, "video")), MINE)

    def test_only_the_prompt_can_be_changed_from_a_show(self):
        """A shared show can't repoint a model at another host."""
        path = TG.overrides_path(self.root)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        F.write_json(path, {MODEL: {"router.model": "someone/else", PV.TEMPLATE: MINE}})
        TG.forget_targets()
        t = self.load()
        self.assertNotEqual(TG.hosted_block(t.spec)["model"], "someone/else")
        self.assertEqual(TP.shot_template(t), MINE)
        self.save(**{"router.model": "someone/else"})
        self.assertEqual(TG.show_overrides(self.root), {})

    def test_back_to_shipped_clears_it(self):
        shipped = TP.shot_template(self.load())
        self.save(**{PV.TEMPLATE: MINE})
        self.save(**{PV.TEMPLATE: ""})
        self.assertEqual(TP.shot_template(self.load()), shipped)
        self.assertEqual(self.load().show_fields, {})

    def test_the_shipped_file_is_left_alone(self):
        self.save(**{PV.TEMPLATE: MINE})
        with open(os.path.join(self.load().folder, "target.json"), encoding="utf-8") as fh:
            self.assertNotIn("prompt_template", json.load(fh)["recipe"])

    def test_it_is_not_taken_for_a_target(self):
        self.save(**{PV.TEMPLATE: MINE})
        self.assertEqual(TG.custom_folders(self.root), [])

    def test_a_render_gets_it(self):
        self.save(**{PV.TEMPLATE: MINE})
        doc, i = J.find_shot(self.root, "final", "sh010")
        job = J.plan_job(self.root, "final", doc, i, J.RenderRequest("sh010", target=MODEL), {})
        self.assertEqual(job.error, "")
        prompt = J._prompt_text(J.frozen_shotlist(job)["shots"][0]["prompt"])
        self.assertTrue(prompt.startswith("Look: "), prompt)


class Preview(Show):
    def test_it_shows_the_shot_the_parts_and_what_is_sent(self):
        got = PV.preview(self.root, MODEL, shot="sh010")
        self.assertTrue(got["ok"], got.get("why"))
        self.assertTrue(got["editable"])
        self.assertEqual(got["entry"]["id"], "sh010")
        self.assertEqual(got["entry"]["prompt"], got["prompt"])
        self.assertIn(got["prompt"], got["sent"])
        self.assertEqual({p["name"] for p in got["parts"]}, set(TP.PARTS))
        self.assertEqual({p["name"] for p in got["request_parts"]}, set(TP.REQUEST_PARTS))
        self.assertIn("content", got["arguments"])

    def test_a_template_being_edited_is_shown_and_not_saved(self):
        got = PV.preview(self.root, MODEL, shot="sh010", template=MINE)
        self.assertTrue(got["prompt"].startswith("Look: "), got["prompt"])
        self.assertEqual(got["template"], MINE)
        self.assertFalse(got["changed"])
        self.assertEqual(TG.show_overrides(self.root), {})
        self.assertNotEqual(TP.shot_template(self.load()), MINE)

    def test_the_request_template_is_shown_in_what_is_sent(self):
        got = PV.preview(self.root, MODEL, shot="sh010", request="NOTE {prompt}")
        self.assertEqual(got["sent"], "NOTE " + got["prompt"])

    def test_an_empty_template_previews_the_models_own_over_a_saved_one(self):
        shipped = PV.preview(self.root, MODEL, shot="sh010")
        self.save(**{PV.TEMPLATE: MINE})
        got = PV.preview(self.root, MODEL, shot="sh010", template="")
        self.assertEqual(got["prompt"], shipped["prompt"])
        self.assertTrue(got["changed"])
        self.assertEqual(got["shipped"]["template"], shipped["template"])

    def test_a_wrong_template_is_named_and_the_rest_still_shown(self):
        got = PV.preview(self.root, MODEL, shot="sh010", template="{nope}")
        self.assertIn("nope", got["problems"]["template"][0])
        self.assertTrue(got["ok"])
        self.assertEqual(got["prompt"], PV.preview(self.root, MODEL, shot="sh010")["prompt"])

    def test_a_shot_built_on_the_model_uses_the_new_template_not_the_build(self):
        """The built entry holds the old prompt; the preview compiles anew."""
        doc, _ = J.find_shot(self.root, "proxy", "sh010")
        built = J.shotlist_target(doc).id
        got = PV.preview(self.root, built, shot="sh010", template="X {action}") \
            if PV.editable(self.load(built)) else None
        if got:
            self.assertTrue(got["prompt"].startswith("X "), got["prompt"])

    def test_a_model_that_writes_its_own_is_shown_read_only(self):
        got = PV.preview(self.root, "minimax_h3_ref2va", shot="sh010")
        self.assertTrue(got["ok"], got.get("why"))
        self.assertFalse(got["editable"])
        self.assertEqual(got["parts"], [])
        self.assertTrue(got["prompt"])
        self.assertNotIn("arguments", got)

    def test_a_local_prose_model(self):
        got = PV.preview(self.root, "ltx2", shot="sh010", template="X {action}")
        self.assertTrue(got["ok"], got.get("why"))
        self.assertTrue(got["sent"].startswith("X "), got["sent"])

    def test_a_model_not_saved_yet(self):
        spec = json.loads(json.dumps(self.load().spec))
        spec.update(id="brand_new", draft=True)
        got = PV.preview(self.root, "brand_new", shot="sh010", template=MINE, spec=spec)
        self.assertTrue(got["ok"], got.get("why"))
        self.assertTrue(got["prompt"].startswith("Look: "), got["prompt"])
        with self.assertRaises(TG.TargetError):
            TG.load_target("brand_new", "video", root=self.root)

    def test_no_such_shot(self):
        with self.assertRaises(PV.PreviewError):
            PV.preview(self.root, MODEL, shot="sh999")

    def test_the_takes_it_would_touch_are_only_counted_when_asked(self):
        self.assertNotIn("takes_on_model", PV.preview(self.root, MODEL, shot="sh010"))
        self.assertEqual(PV.preview(self.root, MODEL, shot="sh010", count=True)["takes_on_model"], 0)


class Mapping(Show):
    def test_each_value_says_where_it_goes_and_what_it_comes_to(self):
        got = PV.preview(self.root, MODEL, shot="sh010")
        by = {r["role"]: r for r in got["rows"]}
        self.assertEqual(by["duration"]["field"], "duration")
        self.assertEqual(by["duration"]["now"], got["arguments"]["duration"])
        self.assertEqual(by["prompt"]["field"], "content")
        self.assertEqual(by["negative"]["now"], None)

    def test_moving_a_value_shows_in_the_request_and_saves_nothing(self):
        got = PV.preview(self.root, MODEL, shot="sh010", inputs={"duration": {"name": "seconds", "min": 4, "max": 30}})
        self.assertIn("seconds", got["arguments"])
        self.assertNotIn("duration", got["arguments"])
        self.assertEqual(TG.show_overrides(self.root), {})

    def test_a_null_sends_none(self):
        got = PV.preview(self.root, MODEL, shot="sh010", inputs={"seed": None})
        self.assertNotIn("seed", got["arguments"])

    def test_a_mapping_that_breaks_the_request_is_said_not_raised(self):
        got = PV.preview(self.root, MODEL, shot="sh010", inputs={"ratio": {"name": "ratio"}})
        self.assertTrue(got["ok"])
        self.assertIn("request_error", got)
        self.assertTrue(got["prompt"])

    def test_fixed_arguments_are_sent(self):
        got = PV.preview(self.root, MODEL, shot="sh010", arguments={"watermark": False})
        self.assertIs(got["arguments"]["watermark"], False)

    def test_what_is_required_and_unfilled(self):
        got = PV.preview(self.root, MODEL, shot="sh010", required=["content", "duration", "watermark_id"])
        self.assertEqual(got["unfilled"], ["watermark_id"])
        got = PV.preview(self.root, MODEL, shot="sh010", required=["duration"], inputs={"duration": None})
        self.assertEqual(got["unfilled"], ["duration"])
        got = PV.preview(self.root, MODEL, shot="sh010", required=["watermark_id"], arguments={"watermark_id": "x"})
        self.assertEqual(got["unfilled"], [])

    def test_a_saved_mapping_reaches_a_render_and_the_model_itself_can_not_change(self):
        self.save(**{"router.inputs.duration": {"name": "seconds", "min": 4, "max": 30}, "router.model": "other/one"})
        t = self.load()
        self.assertEqual(TG.hosted_block(t.spec)["inputs"]["duration"]["name"], "seconds")
        self.assertNotEqual(TG.hosted_block(t.spec)["model"], "other/one")
        doc, i = J.find_shot(self.root, "final", "sh010")
        job = J.plan_job(self.root, "final", doc, i, J.RenderRequest("sh010", target=MODEL), {})
        self.assertIn("seconds", t.module.router_call(t, job)[1])

    def test_a_shared_show_can_not_set_the_block_whole(self):
        path = TG.overrides_path(self.root)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        F.write_json(path, {MODEL: {"router": {"model": "other/one"}, "router.provider": "x", "router.fallback": False}})
        TG.forget_targets()
        self.assertEqual(TG.show_overrides(self.root), {MODEL: {}})
        self.assertNotIn("provider", TG.hosted_block(self.load().spec))

    def test_a_mapping_change_is_a_mapping_stale_reason(self):
        self.assertEqual(TP.signature(self.load()), "")
        self.save(**{"router.inputs.duration": {"name": "seconds"}})
        self.assertTrue(TP.signature(self.load()))

    def test_samples_are_a_shot_of_each_kind(self):
        got = PV.preview(self.root, MODEL, count=True)
        self.assertIn("no_first_frame", got["samples"])
        ids = set(J.shot_order(self.root)) if hasattr(J, "shot_order") else None
        for v in got["samples"].values():
            self.assertTrue(v.startswith("sh"), v)
        if ids:
            self.assertTrue(set(got["samples"].values()) <= ids)
        self.assertNotIn("samples", PV.preview(self.root, MODEL, shot="sh010"))

    def test_a_local_model_has_no_fields(self):
        self.assertNotIn("rows", PV.preview(self.root, "ltx2", shot="sh010"))


class ImageModels(Show):
    def test_a_hosted_image_model_shows_its_request_and_fields(self):
        got = PV.preview(self.root, "nano_banana_pro")
        self.assertTrue(got["ok"], got.get("why"))
        self.assertEqual(got["kind"], "image")
        self.assertFalse(got["editable"])
        self.assertTrue(got["sent"])
        self.assertTrue(got["arguments"])
        self.assertIn("images", {r["role"] for r in got["rows"]})

    def test_its_request_template(self):
        got = PV.preview(self.root, "nano_banana_pro", request="NOTE {prompt}")
        self.assertTrue(got["sent"].startswith("NOTE "), got["sent"])


class EveryModel(unittest.TestCase):
    def test_a_model_is_editable_exactly_when_a_template_reaches_its_prompt(self):
        """The panel's promise, for every model shipped: it offers a template only where one
        changes what's compiled."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        build_episode(tmp.name)
        shutil.copy(os.path.join(FIXTURE, "series.json"), tmp.name)
        off, on = [], []
        for t in TG.list_targets("video"):
            with self.subTest(t.id):
                got = PV.preview(tmp.name, t.id, shot="sh010", template="MARKER {action}", count=False)
                if not got["ok"]:          # a shot this model can't take, whatever the prompt
                    continue
                (on if got["editable"] else off).append(t.id)
                if got["editable"]:
                    self.assertIn("MARKER", got["prompt"], t.id)
                else:
                    self.assertNotIn("MARKER", got["prompt"], t.id)
        self.assertIn(MODEL, on)
        self.assertIn("ltx2", on)
        self.assertIn("wan22_ti2v", on)
        self.assertIn("minimax_h3_ref2va", off)


class ReadingASchema(unittest.TestCase):
    def test_a_shipped_models_schema_reads_into_fields(self):
        from seriesmith import router_inspect as RI
        folder = os.path.join(HERE, "fixtures", "router_schemas")
        with open(os.path.join(folder, sorted(os.listdir(folder))[0]), encoding="utf-8") as fh:
            got = RI.schema_fields(json.load(fh))
        self.assertTrue(got["fields"])
        paths = {f["path"] for f in got["fields"]}
        self.assertTrue(all(r in paths for r in got["required"]), got["required"])


class Stale(Show):
    SIDE = {"target": MODEL}

    def entry(self):
        doc, i = J.find_shot(self.root, "proxy", "sh010")
        sdoc, shot = J.retarget(self.root, "proxy", doc, doc["shots"][i], MODEL)
        return {k: v for k, v in sdoc.items() if k != J.BEHIND}, shot

    def sidecar(self):
        doc, shot = self.entry()
        out = {"target": MODEL, "shot_hash": J.story_hash(shot), "preset_hash": J.preset_hash(doc, shot)}
        t = self.load()
        if TP.signature(t):
            out.update(mapping_hash=TP.signature(t), shot_bare_hash=J.bare_hash(shot))
        return out

    def stale(self, sidecar):
        doc, shot = self.entry()
        return J.stale_reasons(self.root, doc, shot, sidecar)

    def test_nothing_changed(self):
        self.assertEqual(self.stale(self.sidecar()), [])

    def test_a_new_template_says_mapping_not_script(self):
        before = self.sidecar()
        self.save(**{PV.TEMPLATE: MINE})
        self.assertEqual(self.stale(before), ["mapping"])

    def test_back_to_shipped_makes_the_old_takes_current_again(self):
        before = self.sidecar()
        self.save(**{PV.TEMPLATE: MINE})
        self.save(**{PV.TEMPLATE: ""})
        self.assertEqual(self.stale(before), [])

    def test_a_take_made_with_a_template_goes_stale_when_it_goes(self):
        self.save(**{PV.TEMPLATE: MINE})
        made = self.sidecar()
        self.assertEqual(self.stale(made), [])
        self.save(**{PV.TEMPLATE: ""})
        self.assertEqual(self.stale(made), ["mapping"])

    def test_the_request_template_counts(self):
        before = self.sidecar()
        self.save(**{PV.REQUEST: "{prompt}"})
        self.assertEqual(self.stale(before), ["mapping"])

    def test_a_script_change_under_a_template_is_still_script(self):
        self.save(**{PV.TEMPLATE: MINE})
        made = self.sidecar()
        made["shot_hash"] = "other"
        self.assertEqual(self.stale(made), ["script"])

    def test_both_changing_says_both(self):
        self.save(**{PV.TEMPLATE: MINE})
        made = self.sidecar()
        made["shot_bare_hash"] = "other"
        self.save(**{PV.TEMPLATE: "{action}"})
        self.assertEqual(self.stale(made), ["script", "mapping"])

    def test_a_take_with_no_template_is_as_it_was(self):
        doc, shot = self.entry()
        side = {"target": MODEL, "shot_hash": "other"}
        self.assertEqual(J.stale_reasons(self.root, doc, shot, side), ["script"])

    def test_the_sidecar_says_nothing_when_the_model_has_no_template(self):
        doc, i = J.find_shot(self.root, "final", "sh010")
        job = J.plan_job(self.root, "final", doc, i, J.RenderRequest("sh010", target=MODEL), {})
        self.assertEqual(J._mapping_fields(job), {})
        self.save(**{PV.TEMPLATE: MINE})
        job = J.plan_job(self.root, "final", doc, i, J.RenderRequest("sh010", target=MODEL), {})
        self.assertEqual(set(J._mapping_fields(job)), {"mapping_hash", "shot_bare_hash"})


class Routes(ApiTest):
    def test_a_mapping_saved_then_back_to_shipped(self):
        place = {"name": "seconds", "min": 4, "max": 30}
        self.ok(A.put_targets_prompt(self.ctx, {"ep": self.ep, "id": MODEL, "inputs": {"duration": place}}))
        self.assertEqual(TG.show_overrides(self.ep), {MODEL: {"router.inputs.duration": place}})
        got = self.ok(A.post_targets_prompt_preview(self.ctx, {"ep": self.ep, "id": MODEL, "shot": "sh010"}))
        self.assertTrue(got["changed"])
        self.assertIn("seconds", got["arguments"])
        self.assertEqual(got["shipped"]["inputs"]["duration"]["name"], "duration")
        self.ok(A.put_targets_prompt(self.ctx, {"ep": self.ep, "id": MODEL}))
        self.assertEqual(TG.show_overrides(self.ep), {})

    def test_a_local_model_refuses_a_mapping(self):
        self.err(A.put_targets_prompt(self.ctx, {"ep": self.ep, "id": "ltx2", "inputs": {"seed": None}}), 400)

    def test_saving_is_refused_while_a_required_field_is_unfilled(self):
        from unittest import mock
        with mock.patch.object(A, "_required_of", return_value=["duration"]):
            self.err(A.put_targets_prompt(self.ctx, {"ep": self.ep, "id": MODEL, "inputs": {"duration": None}}), 400)
        self.assertEqual(TG.show_overrides(self.ep), {})

    def test_the_schema_needs_a_key_and_says_so(self):
        got = self.ok(A.post_targets_schema(self.ctx, {"model": "bytedance/seedance"}))
        self.assertFalse(got["available"])
        self.assertIn("key", got["why"])

    def test_preview_saves_nothing_and_says_what_is_sent(self):
        d = self.ok(A.post_targets_prompt_preview(self.ctx, {"ep": self.ep, "id": MODEL, "shot": "sh010",
                                                             "template": MINE, "count": True}))
        self.assertTrue(d["prompt"].startswith("Look: "), d["prompt"])
        self.assertEqual(d["takes_on_model"], 0)
        self.assertFalse(os.path.exists(TG.overrides_path(self.ep)))

    def test_preview_of_an_unknown_model_or_shot(self):
        self.err(A.post_targets_prompt_preview(self.ctx, {"ep": self.ep, "id": "nope"}), 404)
        self.err(A.post_targets_prompt_preview(self.ctx, {"ep": self.ep, "id": MODEL, "shot": "sh999"}), 404)

    def test_save_then_back_to_shipped(self):
        d = self.ok(A.put_targets_prompt(self.ctx, {"ep": self.ep, "id": MODEL, "template": MINE, "request": ""}))
        self.assertTrue(d["changed"])
        self.assertEqual(TG.show_overrides(self.ep), {MODEL: {PV.TEMPLATE: MINE}})
        listed = self.ok(A.post_targets_prompt_preview(self.ctx, {"ep": self.ep, "id": MODEL, "shot": "sh010"}))
        self.assertTrue(listed["changed"])
        self.assertEqual(listed["template"], MINE)
        self.assertNotEqual(listed["shipped"]["template"], MINE)
        self.ok(A.put_targets_prompt(self.ctx, {"ep": self.ep, "id": MODEL, "template": "", "request": ""}))
        self.assertEqual(TG.show_overrides(self.ep), {})

    def test_a_wrong_template_is_refused_and_nothing_written(self):
        self.err(A.put_targets_prompt(self.ctx, {"ep": self.ep, "id": MODEL, "template": "{nope}"}), 400)
        self.err(A.put_targets_prompt(self.ctx, {"ep": self.ep, "id": MODEL, "request": "[[ {prompt}"}), 400)
        self.assertEqual(TG.show_overrides(self.ep), {})

    def test_a_model_that_writes_its_own_is_refused(self):
        self.err(A.put_targets_prompt(self.ctx, {"ep": self.ep, "id": "minimax_h3_ref2va", "template": "{action}"}), 400)

    def test_a_shows_own_model_keeps_it_in_its_target_json(self):
        with open(os.path.join(TG.load_target(MODEL, "video").folder, "target.json"), encoding="utf-8") as fh:
            spec = json.load(fh)
        spec.update(id="my_model", draft=False)
        folder = os.path.join(TG.show_folder(self.ep), "targets", "my_model")
        os.makedirs(folder)
        F.write_json(os.path.join(folder, "target.json"), spec)
        TG.forget_targets()
        self.ok(A.put_targets_prompt(self.ctx, {"ep": self.ep, "id": "my_model", "template": MINE}))
        self.assertEqual(TG.show_overrides(self.ep), {})
        self.assertEqual(F.read_json_or(os.path.join(folder, "target.json"), {})["recipe"]["prompt_template"], MINE)
        got = self.ok(A.post_targets_prompt_preview(self.ctx, {"ep": self.ep, "id": "my_model", "shot": "sh010"}))
        self.assertTrue(got["changed"])
        self.assertNotEqual(got["shipped"]["template"], MINE)


if __name__ == "__main__":
    unittest.main()
