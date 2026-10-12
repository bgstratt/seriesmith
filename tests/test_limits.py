"""
seriesmith.limits: a video target's limits read into one dict and written
back where each lives; a built-in's changed on this machine (settings
target_limits) and put back; a Router model saved for every show (the user
folder); a proposed Router target's request for one shot (the dry run); the
schema fields written for several models at once.
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

from seriesmith import api as A  # noqa: E402
from seriesmith import limits as L  # noqa: E402
from seriesmith import router_inspect as RI  # noqa: E402
from seriesmith import targets as TG  # noqa: E402
from test_api import ApiTest  # noqa: E402

SCHEMAS = os.path.join(HERE, "fixtures", "router_schemas")
NO_SETTINGS = os.path.join(ROOT, "tests", "_no_settings.json")


def proposal(model: str) -> dict:
    with open(os.path.join(SCHEMAS, model.replace("/", "__") + ".json"), encoding="utf-8") as fh:
        return RI.propose(model, json.load(fh), base=TG.load_target("seedance_2_5", "video").spec)


class DescribeApplyTest(unittest.TestCase):
    def test_every_video_target_round_trips(self):
        """Writing a target's own limits back changes nothing."""
        for t in TG.list_targets("video"):
            with self.subTest(t.id):
                d = {k: v for k, v in L.describe(t.spec).items() if k != "editable"}
                self.assertEqual(L.apply(t.spec, d), t.spec)

    def test_local_and_hosted(self):
        ltx = L.describe(TG.load_target("ltx2", "video").spec)
        self.assertEqual((ltx["length"]["frames"]["step"], ltx["size"]["multiple"]), (8, 64))
        self.assertNotIn("prompt", ltx["editable"])
        veo = L.describe(TG.load_target("veo_3_1_fast", "video").spec)
        self.assertEqual(veo["length"]["seconds"], {"values": [4, 6, 8]})
        self.assertEqual((veo["prompt"]["max_chars"], veo["pictures"]["references"], veo["pictures"]["via"]),
                         (1000, 3, "base64"))
        self.assertFalse(L.describe(TG.load_target("runway_gen4_turbo", "video").spec)["sound"])

    def test_an_input_switched_off_comes_back_as_it_was(self):
        spec = TG.load_target("kling_v3_omni", "video").spec
        off = L.apply(spec, {"pictures": {"last": False}})
        self.assertNotIn("last", off["router"]["inputs"])
        self.assertEqual(off["recipe"]["keyframes"], ["first"])
        back = L.apply(off, {"pictures": {"last": True}})
        self.assertEqual(back["router"]["inputs"]["last"], spec["router"]["inputs"]["last"])
        self.assertNotIn("off", back["router"])

    def test_seconds_set_the_frame_grid_and_resolutions_the_presets(self):
        spec = proposal("byteplus/dreamina-seedance-2-0-260128")["proposal"]
        out = L.apply(spec, {"length": {"seconds": {"min": 4, "max": 15}},
                             "size": {"resolutions": ["480p", "720p"]}})
        self.assertEqual(out["template"]["frames"], {"step": 24, "base": 96, "max": 360})
        self.assertEqual((out["presets"]["final"]["height"], out["presets"]["proxy"]["height"]), (720, 480))

    def test_bad_limits_are_refused(self):
        spec = TG.load_target("ltx2", "video").spec
        for bad in ({"length": {"frames": {"step": 0, "base": 1, "max": 9}}},
                    {"size": {"multiple": 0}}, {"size": {"sizes": [[1280]]}}):
            with self.assertRaises(ValueError):
                L.apply(spec, bad)
        with self.assertRaises(ValueError):
            L.apply(TG.load_target("veo_3_1_fast", "video").spec, {"pictures": {"via": "ftp"}})


class FixedSizesTest(unittest.TestCase):
    def test_a_size_goes_to_the_nearest_listed_one(self):
        t = TG.Template({"sizes": [[1280, 720], [720, 1280], [960, 960]]}, "X")
        self.assertEqual(t.fit_size(1366, 768), (1280, 720))
        self.assertEqual(t.fit_size(600, 1000), (720, 1280))
        with self.assertRaisesRegex(ValueError, "nearest: 1280x720"):
            t.validate_size(1920, 1080)
        t.validate_size(960, 960)


class SharedFieldsTest(unittest.TestCase):
    def test_the_fields_that_hid_a_limit_are_named(self):
        sd = proposal("byteplus/dreamina-seedance-2-0-260128")["shared"]
        self.assertEqual({k: [x["input"] for x in v] for k, v in sd.items()},
                         {"length": ["duration"], "size": ["resolution"]})
        self.assertIn("[4,15]", sd["length"][0]["text"])
        self.assertEqual(proposal("kling/kling-v3-omni")["shared"], {})


class LimitsRoutesTest(ApiTest):
    def setUp(self):
        super().setUp()
        os.environ["SERIESMITH_SETTINGS"] = os.path.join(self.tmp, "user", "settings.json")
        self.addCleanup(os.environ.__setitem__, "SERIESMITH_SETTINGS", NO_SETTINGS)
        self.addCleanup(TG.forget_targets)
        TG.forget_targets()

    def limits(self, tid):
        return TG.load_target(tid, "video", root=self.ep).describe()["limits"]

    def test_a_built_in_is_changed_on_this_machine_and_put_back(self):
        d = self.ok(A.put_targets_limits(self.ctx, {"ep": self.ep, "id": "ltx2",
                                                    "limits": {"size": {"multiple": 32}}}))
        self.assertEqual(d["target"]["limits"]["size"]["multiple"], 32)
        self.assertTrue(d["target"]["limits"]["overridden"])
        self.assertEqual(d["target"]["limits"]["shipped"]["size"]["multiple"], 64)
        self.assertEqual(TG.load_target("ltx2", "video").template.size_multiple, 32)
        self.ok(A.put_targets_limits(self.ctx, {"ep": self.ep, "id": "ltx2", "limits": None}))
        self.assertEqual(self.limits("ltx2")["size"]["multiple"], 64)
        self.assertNotIn("overridden", self.limits("ltx2"))

    def test_a_local_target_keeps_its_graphs_pictures(self):
        self.ok(A.put_targets_limits(self.ctx, {"ep": self.ep, "id": "ltx2",
                                                "limits": {"pictures": {"references": 2}}}), 400)
        self.ok(A.put_targets_limits(self.ctx, {"ep": self.ep, "id": "ltx2",
                                                "limits": {"pictures": {"needs_first": True}}}))

    def test_a_router_model_for_every_show(self):
        p = dict(proposal("kling/kling-v3-omni")["proposal"], id="my_kling")
        d = self.ok(A.put_targets_custom(self.ctx, {"ep": self.ep, "target": p, "scope": "user"}))
        self.assertTrue(d["path"].startswith(TG.user_folder()))
        t = TG.load_target("my_kling", "video")                  # no show needed
        self.assertEqual(TG.scope_of(t.folder), "user")
        self.ok(A.put_targets_limits(self.ctx, {"ep": self.ep, "id": "my_kling",
                                                "limits": {"pictures": {"references": 2}}}))
        self.assertEqual(self.limits("my_kling")["pictures"]["references"], 2)
        with open(os.path.join(TG.user_folder(), "my_kling", "target.json"), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["router"]["inputs"]["references"]["max"], 2)

    def test_a_proposed_target_is_dry_run_on_a_shot(self):
        p = proposal("kling/kling-v3-omni")["proposal"]
        d = self.ok(A.post_targets_router_dryrun(self.ctx, {"ep": self.ep, "target": p}))
        self.assertTrue(d["ok"], d)
        self.assertEqual(d["model"], "kling/kling-v3-omni")
        self.assertEqual(d["arguments"]["mode"], "std")
        self.assertTrue(all("file" in x["image_url"] for x in d["arguments"]["image_list"]))
        runway = self.ok(A.post_targets_router_dryrun(self.ctx, {"ep": self.ep, "target": "runway_gen4_turbo"}))
        self.assertFalse(runway["ok"])
        self.assertIn("first keyframe", runway["why"])


if __name__ == "__main__":
    unittest.main()
