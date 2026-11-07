"""A take of another model re-sampled through an H3 model (upscale `through`): its
frames through that model's VAEs, its prompt and references compiled for that
model from the script, its frame count and sound kept."""
import json
import os
import unittest

import test_phase13 as P13
from seriesmith import finishing as FN
from seriesmith import takes as T
from seriesmith import upscale as U

H3 = "minimax_h3_ref2va"


class ThroughTest(P13.UpscaleTest):
    def wan_take(self, width=832, height=480, frames=109, fps=24, **fields):
        t = self.final_take()
        T.update_sidecar(t.paths.sidecar, target="wan22_i2v", width=width, height=height, frames=frames,
                         length=frames, fps=fps, steps=4, model="wan2.2_i2v_high.safetensors",
                         loras=[{"name": "wan_lora.safetensors", "strength": 1.0}],
                         inputs={"first": "seriesmith/abc.png"}, **fields)
        return T.get_take(self.ep, "final", "sh010", t.take)

    def plan(self, take=None, **kw):
        return U.plan_upscale(self.ep, take or self.wan_take(), through=H3, **kw)

    def graph(self, up):
        return U.upscale_graph(self.base(), up)

    def test_it_plans_on_the_model_asked_for(self):
        up = self.plan()
        self.assertEqual(up.action, "upscale", up.why)
        self.assertEqual((up.target.id, up.route, up.method), (H3, "vae", "latent"))
        self.assertEqual((up.width, up.height), (1664, 960))
        self.assertEqual((up.keep_frames, up.through_doc["shots"][0]["length"]), (109, 124))
        self.assertAlmostEqual(up.through_doc["shots"][0]["duration"], 109 / 24)
        self.assertTrue(any("re-sampled through" in n for n in up.notes))

    def test_without_asking_nothing_changes(self):
        up = U.plan_upscale(self.ep, self.wan_take())
        self.assertEqual((up.target.id, up.through_doc), ("wan22_i2v", None))

    def test_a_take_of_the_same_family_keeps_its_own(self):
        t = self.final_take()
        up = U.plan_upscale(self.ep, t, through="fasth3_omni")
        self.assertIsNone(up.through_doc)
        self.assertEqual(up.target.id, (t.sidecar or {}).get("target") or T.DEFAULT_TARGET)

    def test_other_methods_ignore_it(self):
        up = self.plan(method="seedvr2")
        self.assertEqual((up.method, up.through_doc), ("seedvr2", None))
        self.assertEqual(self.plan(method="pixel").method, "pixel")

    def test_only_a_model_that_takes_any_take(self):
        for bad, words in (("wan22_i2v", "can't re-sample"), ("minimax_h3_fl2va", "can't re-sample"), ("nope", "no such")):
            up = U.plan_upscale(self.ep, self.wan_take(), through=bad)
            self.assertEqual(up.action, "error")
            self.assertIn(words, up.why)

    def test_another_frame_rate_is_refused(self):
        up = self.plan(self.wan_take(fps=16))
        self.assertEqual(up.action, "error")
        self.assertIn("16 fps", up.why)

    def test_a_held_take_is_refused(self):
        up = self.plan(self.wan_take(hold=22))
        self.assertEqual(up.action, "error")
        self.assertIn("only its own model", up.why)

    def test_a_shot_gone_from_the_script_is_refused(self):
        t = self.wan_take()
        t2 = T.Take("sh999", t.take, t.pass_, t.paths, t.sidecar)
        up = self.plan(t2)
        self.assertEqual(up.action, "error")
        self.assertIn("no prompt", up.why)

    def test_the_graph_starts_from_the_takes_frames(self):
        up = self.plan()
        g = self.graph(up)
        self.assertEqual(g["up_video"]["inputs"]["frames"], 124)
        self.assertTrue(g["up_video"]["inputs"]["video_file"].endswith("sh010_t01.mp4"))
        self.assertEqual(g["up_venc"]["inputs"]["pixels"], ["up_video", 0])
        self.assertNotIn("up_fit", g)
        self.assertEqual(g["up_keep"]["class_type"], "ImageFromBatch")
        self.assertEqual((g["up_keep"]["inputs"]["batch_index"], g["up_keep"]["inputs"]["length"]), (0, 109))
        self.assertEqual(g["up_save"]["inputs"]["images"], ["up_keep", 0])
        self.assertEqual(os.path.normpath(os.path.join(self.ep, g["up_save"]["inputs"]["source_mp4"])),
                         os.path.normpath(up.take.paths.mp4))

    def test_nothing_of_the_other_models_render_reaches_the_graph(self):
        up = self.plan()
        text = json.dumps(self.graph(up))
        self.assertNotIn("wan2.2", text)
        self.assertNotIn("wan_lora", text)
        self.assertNotIn("seriesmith/abc.png", text)

    def test_the_loader_reads_the_models_own_shotlist(self):
        up = self.plan()
        g = self.graph(up)
        loaders = [v for v in g.values() if v["class_type"] == up.target.binding.loader_class]
        self.assertEqual(len(loaders), 1)
        path = os.path.join(self.ep, loaders[0]["inputs"]["shotlist_file"])
        self.assertEqual(os.path.normpath(path), os.path.normpath(up.take.paths.up_shotlist))
        self.assertEqual(T.read_json(path)["shots"][0]["length"], 124)

    def test_portable_carries_the_frame_count(self):
        up = self.plan()
        pg, _ = FN.portable(FN.of_upscale(up, self.graph(up)))
        v = next(x for x in pg.values() if x["class_type"] == "SeriesmithLoadTakeVideo")
        self.assertEqual(v["inputs"]["frames"], 124)

    def test_a_size_off_the_grid_is_fitted_up(self):
        up = self.plan(self.wan_take(width=1280, height=720))
        self.assertEqual(up.through_size, (1280, 736))
        self.assertEqual((up.width, up.height), (2560, 1472))
        g = self.graph(up)
        self.assertEqual(g["up_fit"]["class_type"], "ImageScale")
        self.assertEqual((g["up_fit"]["inputs"]["width"], g["up_fit"]["inputs"]["height"]), (1280, 736))
        self.assertEqual(g["up_fit"]["inputs"]["crop"], "center")
        self.assertEqual(g["up_venc"]["inputs"]["pixels"], ["up_fit", 0])

    def test_frames_already_on_the_grid_arent_cut(self):
        self.assertNotIn("up_keep", self.graph(self.plan(self.wan_take(frames=107))))

    def test_it_doesnt_follow_continuity(self):
        up = self.plan(self.wan_take(continuity={"shot": "sh010", "take": 1, "pass": "final"}))
        self.assertIsNone(up.first_from)
        self.assertIsNone(up.held_from)

    def test_settings_and_record_say_so(self):
        up = self.plan()
        self.assertEqual(U.settings_of(up)["through"], H3)
        self.assertIn(f"through {up.target.short}", U.describe(up))
        self.assertNotIn("through", U.settings_of(U.plan_upscale(self.ep, self.wan_take())))

    def test_a_recipe_carries_it(self):
        fields = {"method": "latent", "through": H3, "scale": 2}
        self.assertEqual(U.check_fields(fields), [])
        self.assertEqual(U.recipe_kwargs(fields)["through"], H3)
        self.assertEqual(U.recipe_from_request({"through": H3})["through"], H3)
        self.assertIn(f"through {H3}", U.describe_recipe(fields))
        self.assertEqual(len(U.check_fields({"method": "pixel", "through": H3})), 1)
        self.assertEqual(len(U.check_fields({"through": 3})), 1)

    def test_auto_scale_uses_the_models_grid(self):
        up = self.plan(self.wan_take(width=1280, height=720), scale=U.AUTO, deliver="1440p")
        self.assertEqual(up.action, "upscale", up.why)
        self.assertEqual((up.scale, up.width, up.height), (2.0, 2560, 1472))

    def test_a_missing_model_or_node_is_said(self):
        up = self.plan()
        info = {c: {"input": {}} for c in U.UPSCALE_NODES}
        self.assertTrue(any("ImageFromBatch" in m for m in U.not_ready([up], info)))

    def test_the_choices_are_the_ref_models(self):
        ids = {c["id"] for c in U.through_choices(None)}
        self.assertEqual(ids, {"minimax_h3_ref2va", "fasth3_omni", "h3_singularity", "pika_h3_flex"})


if __name__ == "__main__":
    unittest.main()
