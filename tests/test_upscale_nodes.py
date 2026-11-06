"""Which nodes an H3 re-sample uses: ComfyUI's own (0.44 or later), a node pack on
an older ComfyUI or when asked for (LBH's, or its Plus; obvpm's windows), and what
it says with neither."""
import unittest

import test_phase13 as P13
from seriesmith import upscale as U

MODEL = "minimax_h3_latent_upscaler_3d_fp16.safetensors"
LOADER = {"input": {"required": {"model_name": [[MODEL], {}]}}}
CORE = {"MiniMaxH3LatentUpscaleWithModel": {"input": {}}, "LatentUpscaleModelLoader": LOADER,
        "MiniMaxH3ContextWindows": {"input": {}}}
# the Plus version: the same node, without temporal chunking
PLUS = {"input": {"required": {"latent": ["*", {}], "model_name": [[MODEL], {}]}}}


def comfy(*extra: dict) -> dict:
    out = {c: {"input": {}} for c in U.UPSCALE_NODES}
    for e in extra:
        out.update(e)
    return out


LBH = {"MinimaxH3LatentUpscaler3D": P13.UPSCALER}
OBVPM = {"H3ContextWindows": {"input": {}}}


class NodesTest(P13.UpscaleTest):
    def take_of(self, seconds: float):
        from seriesmith import takes as T
        t = self.final_take()
        T.update_sidecar(t.paths.sidecar, length=int(seconds * 24) + 1, fps=24)
        return T.get_take(self.ep, "final", "sh010", 1)

    def plan(self, seconds=11.5, **kw):
        return U.plan_upscale(self.ep, self.take_of(seconds), **kw)

    def test_comfyuis_own_are_the_default_with_the_packs_installed_too(self):
        up = self.plan()
        self.assertEqual(U.not_ready([up], comfy(CORE, LBH, OBVPM)), [])
        g = U.upscale_graph(self.base(), up)
        scale = g["up_scale"]
        self.assertEqual(scale["class_type"], "MiniMaxH3LatentUpscaleWithModel")
        self.assertEqual((scale["inputs"]["width"], scale["inputs"]["height"]), (up.width, up.height))
        self.assertEqual(scale["inputs"]["model"], ["up_scale_model", 0])
        self.assertEqual(g["up_scale_model"]["class_type"], "LatentUpscaleModelLoader")
        self.assertEqual(g["up_scale_model"]["inputs"]["model_name"], MODEL)
        self.assertEqual(scale["inputs"]["samples"], ["up_split_av", 0])

    def test_comfyuis_windows_match_what_the_ab_ran(self):
        up = self.plan()
        U.not_ready([up], comfy(CORE))
        w = U.upscale_graph(self.base(), up)["up_windows"]
        self.assertEqual(w["class_type"], "MiniMaxH3ContextWindows")
        i = w["inputs"]
        self.assertEqual((i["context_length"], i["context_overlap"]), (124, 39))
        self.assertEqual((i["fuse_method"], i["freenoise"], i["split_conds_to_windows"]), ("pyramid", False, False))
        self.assertEqual(U.settings_of(up)["window"], [5.5, 1.25])

    def test_window_frames_land_on_17n_plus_5(self):
        self.assertEqual(U.window_frames(5.5, 1.25, 24, 17, 5), (124, 39))
        self.assertEqual(U.window_frames(73 / 24, 22 / 24, 24, 17, 5), (73, 22))
        for secs in (2, 2.5, 3, 4, 7.25, 10, 30):
            for over in (0.25, 1, 1.25, secs / 2):
                length, overlap = U.window_frames(secs, over, 24, 17, 5)
                self.assertEqual((length - 5) % 17, 0, (secs, over))
                self.assertEqual((overlap - 5) % 17, 0, (secs, over))
                self.assertGreaterEqual(length, 22)
                self.assertLess(overlap, length)

    def test_an_older_comfyui_uses_the_packs(self):
        up = self.plan()
        self.assertEqual(U.not_ready([up], comfy(LBH, OBVPM)), [])
        g = U.upscale_graph(self.base(), up)
        self.assertEqual(g["up_scale"]["class_type"], "MinimaxH3LatentUpscaler3D")
        self.assertEqual(g["up_scale"]["inputs"]["mode.scale"], up.scale)
        self.assertNotIn("up_scale_model", g)
        self.assertEqual(g["up_windows"]["class_type"], "H3ContextWindows")
        self.assertEqual((g["up_windows"]["inputs"]["window_seconds"],
                          g["up_windows"]["inputs"]["overlap_seconds"]), (5.5, 1.25))
        self.assertEqual(U.nodes_used(up), {"upscaler": "MinimaxH3LatentUpscaler3D", "windows": "H3ContextWindows"})

    def test_the_plus_version_is_as_good_as_lbhs(self):
        up = self.plan(3.0)
        self.assertEqual(U.not_ready([up], comfy({"MinimaxH3LatentUpscaler3D": PLUS})), [])
        self.assertTrue(up.upscaler_pack)
        self.assertEqual(U.upscale_readiness(up.target, comfy({"MinimaxH3LatentUpscaler3D": PLUS}))["status"], "ready")

    def test_with_neither_it_names_all_three_ways_out(self):
        up = self.plan(3.0)
        why = " ".join(U.not_ready([up], comfy()))
        for word in ("update ComfyUI to 0.44", "Comfyui_Minimax_h3_latent_Upscaler", "Plus"):
            self.assertIn(word, why)
        self.assertNotIn("sparkle", why)
        self.assertEqual(U.upscale_readiness(up.target, comfy())["status"], "not_ready")

    def test_a_long_take_with_no_windows_says_what_to_do(self):
        up = self.plan()
        why = " ".join(U.not_ready([up], comfy({k: CORE[k] for k in ("MiniMaxH3LatentUpscaleWithModel",
                                                                     "LatentUpscaleModelLoader")})))
        for word in ("update ComfyUI to 0.44", "comfyui-obvpm-timeline", "window to 0"):
            self.assertIn(word, why)
        short = self.plan(3.0)
        self.assertEqual(U.not_ready([short], comfy({k: CORE[k] for k in ("MiniMaxH3LatentUpscaleWithModel",
                                                                          "LatentUpscaleModelLoader")})), [])

    def test_choosing_each_pack(self):
        up = self.plan(upscaler="pack")
        self.assertEqual(U.not_ready([up], comfy(CORE, LBH, OBVPM)), [])
        g = U.upscale_graph(self.base(), up)
        self.assertEqual(g["up_scale"]["class_type"], "MinimaxH3LatentUpscaler3D")
        self.assertEqual(g["up_windows"]["class_type"], "MiniMaxH3ContextWindows")
        self.assertEqual(U.settings_of(up)["upscaler"], "pack")

        up = self.plan(windowing="pack")
        self.assertEqual(U.not_ready([up], comfy(CORE, LBH, OBVPM)), [])
        g = U.upscale_graph(self.base(), up)
        self.assertEqual(g["up_scale"]["class_type"], "MiniMaxH3LatentUpscaleWithModel")
        self.assertEqual(g["up_windows"]["class_type"], "H3ContextWindows")
        self.assertEqual(U.settings_of(up)["windowing"], "pack")

    def test_a_chosen_pack_that_isnt_there_says_so(self):
        up = self.plan(3.0, upscaler="pack")
        why = " ".join(U.not_ready([up], comfy(CORE)))
        self.assertIn("Comfyui_Minimax_h3_latent_Upscaler", why)
        up = self.plan(windowing="pack")
        self.assertTrue(any("comfyui-obvpm-timeline" in m for m in U.not_ready([up], comfy(CORE))))

    def test_only_pack_is_a_choice(self):
        self.assertEqual(self.plan(upscaler="lbh").action, "error")
        self.assertEqual(U.check_fields({"windowing": "core"})[0][:9], "windowing")
        self.assertEqual(U.check_fields({"upscaler": "pack", "windowing": "pack"}), [])

    def test_the_default_settings_stay_the_same_either_way(self):
        # a fallback isn't a recipe change: the same recipe on an older ComfyUI
        a, b = self.plan(), self.plan()
        U.not_ready([a], comfy(CORE))
        U.not_ready([b], comfy(LBH, OBVPM))
        self.assertEqual(U.settings_of(a), U.settings_of(b))

    def test_any_h3_scale_is_still_allowed(self):
        self.assertIsNone(U.fixed_scale(self.plan(3.0).spec))

    def test_the_model_file_is_still_checked(self):
        up = self.plan(3.0)
        loader = {"LatentUpscaleModelLoader": {"input": {"required": {"model_name": [["other.safetensors"], {}]}}}}
        why = U.not_ready([up], comfy(CORE, loader))
        self.assertTrue(any(MODEL in m for m in why), why)


if __name__ == "__main__":
    unittest.main()
