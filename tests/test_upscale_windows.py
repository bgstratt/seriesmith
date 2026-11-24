"""
A long take's re-sample sampled in windows along time (upscale.set_window /
windowed: the H3 targets' `upscale.windows`, obvpm's H3 Context Windowing), so
1344x768 x2 = 2688x1536 fits the card on a shot longer than one window. A
short take is sampled in one pass, as before; the recipe's `window` sets the
length, and 0 turns it off.
"""
from __future__ import annotations

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
from seriesmith import takes as T  # noqa: E402
from seriesmith import upscale as U  # noqa: E402
from test_api import ApiTest  # noqa: E402
import test_phase13 as P13  # noqa: E402


class WindowTest(ApiTest):
    final_take = P13.UpscaleTest.final_take
    base = P13.UpscaleTest.base

    def take_of(self, seconds: float) -> T.Take:
        t = self.final_take()
        T.update_sidecar(t.paths.sidecar, length=int(seconds * 24) + 1, fps=24)
        return T.get_take(self.ep, "final", "sh010", 1)

    def test_a_long_take_is_sampled_in_windows(self):
        up = U.plan_upscale(self.ep, self.take_of(11.5))
        self.assertEqual((up.window, up.window_overlap), (5.5, 1.25))
        self.assertTrue(any("5.5s windows" in n for n in up.notes))
        g = U.upscale_graph(self.base(), up)
        w = g["up_windows"]
        self.assertEqual(w["class_type"], "MiniMaxH3ContextWindows")
        self.assertEqual((w["inputs"]["context_length"], w["inputs"]["context_overlap"]), (124, 39))
        # the windows go between the model and H3's guider
        sampler = next(v for v in g.values() if v["class_type"] == "SamplerCustomAdvanced")
        guider = g[sampler["inputs"]["guider"][0]]
        self.assertEqual(guider["inputs"]["model"], ["up_windows", 0])
        self.assertNotEqual(w["inputs"]["model"], ["up_windows", 0])
        self.assertEqual(U.settings_of(up)["window"], [5.5, 1.25])

    def test_an_imported_long_take_is_windowed_too(self):
        """An imported take's sidecar has `frames` and no `length`: still windowed."""
        t = self.final_take()
        T.update_sidecar(t.paths.sidecar, length=None, frames=241, fps=24)
        up = U.plan_upscale(self.ep, T.get_take(self.ep, "final", "sh010", 1))
        self.assertEqual((up.window, up.window_overlap), (5.5, 1.25))

    def test_an_imported_take_starts_on_its_shotlists_schedule(self):
        """No `steps` in an imported take's sidecar: the start step comes from the
        frozen shotlist's steps (what the graph samples), not 8."""
        from seriesmith import jobs as J
        t = self.final_take()
        T.update_sidecar(t.paths.sidecar, steps=None)
        t = T.get_take(self.ep, "final", "sh010", 1)
        with open(t.paths.shotlist, encoding="utf-8") as f:
            doc = json.load(f)
        steps = J.built_values(doc["shots"][0], doc.get("defaults") or {})[2]
        self.assertEqual(U.frozen_steps(t), steps)
        up = U.plan_upscale(self.ep, t)
        spec = U.upscale_spec(up.target)
        self.assertEqual(up.start_step, U.start_of(U.schedule_steps(spec, steps), spec))

    def test_a_short_take_is_one_pass(self):
        up = U.plan_upscale(self.ep, self.take_of(5.2))     # a usual shot: one pass
        self.assertEqual(up.window, 0.0)
        self.assertNotIn("up_windows", U.upscale_graph(self.base(), up))
        self.assertNotIn("window", U.settings_of(up))

    def test_the_recipe_sets_the_length_or_turns_it_off(self):
        t = self.take_of(11.5)
        self.assertEqual(U.plan_upscale(self.ep, t, window=6).window, 6.0)
        self.assertEqual(U.plan_upscale(self.ep, t, window=0).window, 0.0)
        self.assertEqual(U.plan_upscale(self.ep, t, window=20).window, 0.0)   # the take fits
        bad = U.plan_upscale(self.ep, t, window=1)
        self.assertEqual(bad.action, "error")
        self.assertIn("window", bad.why)
        self.assertEqual(U.check_fields({"window": 1}), ["window 1: 0 (off), or 2 to 30 seconds"])
        self.assertEqual(U.check_fields({"window": 0}), [])

    def test_the_pixel_method_is_never_windowed(self):
        up = U.plan_upscale(self.ep, self.take_of(11.5), method="pixel")
        self.assertEqual(up.window, 0.0)

    def test_without_the_node_a_long_take_says_so(self):
        up = U.plan_upscale(self.ep, self.take_of(11.5))
        why = U.not_ready([up], {"SamplerCustomAdvanced": {}})
        self.assertTrue(any("longer than one" in m and "comfyui-obvpm-timeline" in m
                            for m in why), why)
        short = U.plan_upscale(self.ep, self.take_of(3.0))
        self.assertFalse([m for m in U.not_ready([short], {}) if "longer than one" in m])


if __name__ == "__main__":
    unittest.main()
