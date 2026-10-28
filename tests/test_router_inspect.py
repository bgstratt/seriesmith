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
        # seriesmith ships it under that id: a show's own copy needs another
        self.assertEqual(IN.validate_spec(dict(p, id="my_h3")), [])
        self.assertTrue(IN.validate_spec(p))

    def test_veo_is_nested(self):
        inp = proposal("veo/veo-3.1-generate-001")["proposal"]["router"]["inputs"]
        # a limit the schema doesn't state: a 1278-character prompt failed (2026-10-12)
        self.assertEqual(inp["prompt"], {"field": "instances.0.prompt", "max_chars": 1000})
        # the bytes, not a link: gcsUri takes Google Cloud Storage only (2026-10-12)
        self.assertEqual(inp["first"], {"field": "instances.0.image",
                                        "item": {"bytesBase64Encoded": "$url", "mimeType": "$mime"}})
        self.assertEqual(inp["via"], "base64")
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

    def test_flux3_keyframes_and_mode(self):
        """FLUX 3 video's pictures are `keyframes` (they become frames: the
        shot's first, then last), and its `mode` says whether any went."""
        r = proposal("bfl/flux-3-video")
        inp = r["proposal"]["router"]["inputs"]
        self.assertEqual((inp["first"], inp["last"]), ({"list": "keyframes"}, {"list": "keyframes"}))
        self.assertEqual(inp["mode"], {"name": "mode", "frames": "i2v", "text": "t2v"})
        self.assertNotIn("references", inp)
        self.assertEqual(r["unplaced"], [])

    def test_runway_needs_a_first_frame(self):
        r = proposal("runway/gen4_turbo")
        p = r["proposal"]
        self.assertEqual(p["router"]["inputs"]["first"], {"field": "promptImage"})
        self.assertIn("first", p["recipe"]["keyframe_required"])
        self.assertEqual(r["unplaced"], [])
        sd = TG.load_target("seedance_2_5", "video")
        self.assertTrue(TG.Target(sd.folder, p).capabilities()["requires_first"])
        # Router refused a 1421-character promptText (2026-10-12)
        self.assertEqual(p["router"]["inputs"]["prompt"], {"field": "promptText", "max_chars": 1000})
        self.assertNotIn("via", p["router"]["inputs"])                  # an asset link does
        # it makes no sound: the silent prose (quoted lines failed, 2026-10-12)
        self.assertEqual((p["capabilities"]["audio"], p["recipe"]["policies"]), ("none", ["silent"]))
        self.assertNotIn("audio", proposal("minimax/minimax-h3")["proposal"]["capabilities"])

    def test_a_long_prompt_keeps_whole_sentences(self):
        from seriesmith.targets.generic.router_video import fit
        text = 'Style: film. A porch. A man sits. He says: "Hi there." The sound is wind.'
        self.assertEqual(fit(text, 100), text)
        self.assertEqual(fit(text, 70), 'A porch. A man sits. He says: "Hi there." The sound is wind.')
        self.assertEqual(fit(text, 40), 'He says: "Hi there." The sound is wind.')
        self.assertEqual(fit(text, 6), "The so")
        # the ratio Runway requires goes out with its first frame
        p = proposal("runway/gen4_turbo")["proposal"]
        self.assertEqual(p["router"]["inputs"]["ratio"]["with_frames"], "keep")

    def test_byteplus_goes_through_the_library_and_seeds_stay_under_2_31(self):
        inp = proposal("byteplus/dreamina-seedance-2-0-260128")["proposal"]["router"]["inputs"]
        self.assertEqual(inp["via"], "seedance")
        self.assertEqual(inp["seed"]["max"], 2147483647)                 # the schema says 2^32-1
        self.assertEqual(proposal("runway/gen4_turbo")["proposal"]["router"]["inputs"]["seed"]["max"],
                         2147483647)

    def test_a_bad_id(self):
        with self.assertRaises(RI.RouterInspectError):
            RI.fetch_schema("not a model", "key")


class ShippedRouterTargetsTest(unittest.TestCase):
    @staticmethod
    def tool():
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import make_router_targets
        return make_router_targets

    def test_they_are_what_the_schemas_make(self):
        """seriesmith/targets/video's Router models are generated: change
        tools/make_router_targets.py (or a schema) and run it."""
        self.assertEqual(self.tool().main(["--check"]), 0)

    def test_every_one_is_built_in_and_the_drafts_say_so(self):
        ids = {t.id: t for t in TG.list_targets("video")}
        for model, tid, _label, _short, _limits, draft, _extra in self.tool().MODELS:
            self.assertFalse(ids[tid].custom, tid)
            self.assertEqual(bool(ids[tid].spec.get("draft")), draft, tid)


class InlineOutputTest(unittest.TestCase):
    def test_a_video_in_the_result_is_an_output(self):
        """Veo's result carries its video as base64, not a link: a take that
        only looked for links was lost after it was paid for (2026-10-12)."""
        import base64
        import tempfile
        import types
        from seriesmith.backends.router import RouterRun
        run = RouterRun(types.SimpleNamespace(request_id="r1"), "veo/veo-3.1-fast-generate-001")
        run.status = "succeeded"
        run.result = {"done": True, "response": {"raiMediaFilteredCount": 0, "videos": [
            {"bytesBase64Encoded": base64.b64encode(b"mp4 bytes").decode(), "mimeType": "video/mp4"}]}}
        (out,) = run.outputs()
        self.assertEqual((out.type, out.name), ("video", "output_0.mp4"))
        with tempfile.TemporaryDirectory() as d:
            with open(out.save(os.path.join(d, "t.mp4")), "rb") as fh:
                self.assertEqual(fh.read(), b"mp4 bytes")


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

    def test_a_hand_edit_is_read_again(self):
        """A running server sent the old length after target.json was edited
        by hand (2026-10-12): the cache is kept only while the file is the same."""
        p = proposal("runway/gen4_turbo")["proposal"]
        path = IN.save_spec(self.root, p)
        with TG.use_roots(self.root):
            t = TG.load_target(p["id"], "video", root=self.root)
            self.assertIn(2, t.spec["router"]["inputs"]["duration"]["values"])
            p["router"]["inputs"]["duration"]["values"] = [5, 10]
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(p, fh)
            st = os.stat(path)
            os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
            t = TG.load_target(p["id"], "video", root=self.root)
            self.assertEqual(t.spec["router"]["inputs"]["duration"]["values"], [5, 10])

    def test_a_saved_target_can_be_enabled(self):
        """Enabling re-checks the target with the show's targets in force: it
        mustn't find itself and call its own name a built-in's."""
        p = dict(proposal("minimax/minimax-h3")["proposal"], id="my_h3")    # minimax_h3 ships
        IN.save_spec(self.root, p)
        with TG.use_roots(self.root):
            t = TG.load_target(p["id"], "video", root=self.root)
            self.assertTrue(t.custom)
            self.assertEqual(IN.validate_spec(dict(t.spec)), [])
            self.assertTrue(IN.validate_spec(dict(t.spec, id="seedance_2_5")))     # a built-in's name


if __name__ == "__main__":
    unittest.main()
