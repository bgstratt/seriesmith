"""
A Comfy Router model proposed as a target from its published schema
(seriesmith/router_inspect.py): real schemas (tests/fixtures/
router_schemas, as Router served them on 2026-10-12), what each proposal
places where, and a proposed target driving a real shot's request through
targets/generic/router_video.
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

from seriesmith import inspector as IN  # noqa: E402
from seriesmith import jobs as J  # noqa: E402
from seriesmith import router_inspect as RI  # noqa: E402
from seriesmith import targets as TG  # noqa: E402
from seriesmith.backends import File  # noqa: E402
from test_router_render import Episode  # noqa: E402

SCHEMAS = os.path.join(HERE, "fixtures", "router_schemas")


def proposal(model: str) -> dict:
    with open(os.path.join(SCHEMAS, model.replace("/", "__") + ".json"), encoding="utf-8") as fh:
        doc = json.load(fh)
    return RI.propose(model, doc, base=TG.load_target("seedance_2_5", "video").spec)


class ProposeTest(unittest.TestCase):
    def test_minimax_h3_hosted_is_a_content_list(self):
        r = proposal("minimax/minimax-h3")
        p, inp = r["proposal"], r["proposal"]["router"]["inputs"]
        self.assertEqual((p["id"], p["code"], p["draft"]), ("minimax_h3", "builtin:router_video", True))
        self.assertEqual(inp["prompt"], {"list": "content", "item": {"type": "text", "text": "$prompt"}})
        self.assertEqual(inp["references"]["item"]["role"], "reference_image")
        self.assertEqual((inp["first"]["item"]["role"], inp["last"]["item"]["role"]),
                         ("first_frame", "last_frame"))
        self.assertEqual(inp["duration"], {"name": "duration", "min": 4, "max": 15})
        self.assertEqual(inp["resolution"]["values"], ["2K", "768P"])
        self.assertEqual((p["presets"]["final"]["width"], p["presets"]["final"]["height"]), (1366, 768))
        self.assertEqual(r["unplaced"], [])
        self.assertEqual(IN.validate_spec(p), [])

    def test_veo_is_nested(self):
        inp = proposal("veo/veo-3.1-generate-001")["proposal"]["router"]["inputs"]
        self.assertEqual(inp["prompt"], "instances.0.prompt")
        self.assertEqual(inp["first"], {"field": "instances.0.image",
                                        "item": {"gcsUri": "$url", "mimeType": "image/png"}})
        self.assertEqual(inp["references"]["item"]["referenceType"], "asset")
        self.assertEqual(inp["resolution"]["name"], "parameters.resolution")
        self.assertEqual(proposal("veo/veo-3.1-generate-001")["proposal"]["router"]["arguments"],
                         {"parameters": {"sampleCount": 1}})

    def test_wan_media_list_and_kling_values(self):
        wan = proposal("wan/wan2.6-r2v")["proposal"]["router"]["inputs"]
        self.assertEqual(wan["references"], {"list": "input.media",
                                             "item": {"type": "reference_image", "url": "$url"}})
        self.assertEqual(wan["ratio"]["with_frames"], "adaptive")
        omni = proposal("kling/kling-v3-omni")["proposal"]["router"]["inputs"]
        self.assertEqual(omni["duration"]["as"], "str")
        self.assertEqual(omni["audio"], {"name": "sound", "on": "on", "off": "off"})
        self.assertEqual(omni["last"]["item"], {"image_url": "$url", "type": "end_frame"})

    def test_kling_omni_takes_references_by_name_and_says_std(self):
        for m in ("kling/kling-v3-omni", "kling/kling-video-o1"):
            inp = proposal(m)["proposal"]["router"]["inputs"]
            self.assertEqual(inp["references"], {"list": "image_list", "item": {"image_url": "$url"},
                                                 "mention": "<<<image_{n}>>>"})
            self.assertEqual(inp["resolution"], {"name": "mode", "values": {"720": "std", "1080": "pro"}})

    def test_a_text_only_model_is_refused(self):
        for m in ("kling/kling-v3", "kling/kling-3.0-turbo", "ltx/ltx-2-5-pro"):
            with self.assertRaisesRegex(RI.RouterInspectError, "takes no pictures"):
                proposal(m)

    def test_runway_needs_a_first_frame(self):
        r = proposal("runway/gen4_turbo")
        p = r["proposal"]
        self.assertEqual(p["router"]["inputs"]["first"], {"field": "promptImage"})
        self.assertIn("first", p["recipe"]["keyframe_required"])
        self.assertEqual(r["unplaced"], [])
        sd = TG.load_target("seedance_2_5", "video")
        self.assertTrue(TG.Target(sd.folder, p).capabilities()["requires_first"])

    def test_byteplus_goes_through_the_library_and_seeds_stay_under_2_31(self):
        inp = proposal("byteplus/dreamina-seedance-2-0-260128")["proposal"]["router"]["inputs"]
        self.assertEqual(inp["via"], "seedance")
        self.assertEqual(inp["seed"]["max"], 2147483647)                 # the schema says 2^32-1
        self.assertEqual(proposal("runway/gen4_turbo")["proposal"]["router"]["inputs"]["seed"]["max"],
                         2147483647)

    def test_a_bad_id(self):
        with self.assertRaises(RI.RouterInspectError):
            RI.fetch_schema("not a model", "key")


class ProposedTargetRendersTest(Episode):
    def test_a_proposed_target_makes_a_request_for_a_shot(self):
        p = proposal("minimax/minimax-h3")["proposal"]
        sd = TG.load_target("seedance_2_5", "video")
        t = TG.Target(sd.folder, p)
        job = self.job()
        model, args = t.module.router_call(t, job)
        self.assertEqual(model, "minimax/minimax-h3")
        text, *pics = args["content"]
        self.assertEqual(text, {"type": "text", "text": J._prompt_text(job.prompt)})
        self.assertTrue(pics and all(c["role"] == "reference_image" and isinstance(c["image_url"]["url"], File)
                                     for c in pics))
        self.assertTrue(4 <= args["duration"] <= 15)
        self.assertIn(args["resolution"], ("768P", "2K"))
        self.assertTrue(0 <= args["seed"] <= 2147483647)

    def test_kling_omni_names_each_reference_in_the_prompt(self):
        p = proposal("kling/kling-v3-omni")["proposal"]
        t = TG.Target(TG.load_target("seedance_2_5", "video").folder, p)
        model, args = t.module.router_call(t, self.job())
        pics = args["image_list"]
        self.assertTrue(pics and all(set(c) == {"image_url"} and isinstance(c["image_url"], File) for c in pics))
        for n in range(1, len(pics) + 1):
            self.assertIn(f"<<<image_{n}>>> is ", args["prompt"])
        self.assertNotIn(f"<<<image_{len(pics) + 1}>>>", args["prompt"])
        self.assertEqual(args["mode"], "std")

    def test_a_first_frame_model_refuses_a_shot_without_one(self):
        p = proposal("runway/gen4_turbo")["proposal"]
        t = TG.Target(TG.load_target("seedance_2_5", "video").folder, p)
        with self.assertRaisesRegex(ValueError, "first keyframe"):
            t.module.router_call(t, self.job())

    def test_a_saved_target_can_be_enabled(self):
        """Enabling re-checks the target with the show's targets in force: it
        mustn't find itself and call its own name a built-in's."""
        p = proposal("minimax/minimax-h3")["proposal"]
        IN.save_spec(self.root, p)
        with TG.use_roots(self.root):
            t = TG.load_target(p["id"], "video", root=self.root)
            self.assertTrue(t.custom)
            self.assertEqual(IN.validate_spec(dict(t.spec)), [])
            self.assertTrue(IN.validate_spec(dict(t.spec, id="seedance_2_5")))     # a built-in's name


if __name__ == "__main__":
    unittest.main()
