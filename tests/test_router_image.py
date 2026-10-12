"""
Router image models (targets/generic/router_image.py): each built-in's
request for a ref take, as its schema (tests/fixtures/router_schemas) asks
for it -- the prompt and the pictures where the model takes them, the size as
it takes it -- and the pictures that come back inline (GPT Image's b64_json,
Gemini's inlineData).
"""
from __future__ import annotations

import base64
import os
import sys
import tempfile
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from seriesmith import targets as TG  # noqa: E402
from seriesmith.backends import File  # noqa: E402
from seriesmith.backends.router import RouterRun  # noqa: E402
from seriesmith.targets.generic import router_image as RIM  # noqa: E402


class Jobs(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.pics = []
        for n in range(3):
            p = os.path.join(self._tmp.name, f"ref{n}.png")
            with open(p, "wb") as fh:
                fh.write(b"png")
            self.pics.append(p)

    def job(self, refs=0, width=1344, height=768):
        return types.SimpleNamespace(prompt="Earl on his porch at dawn.", seed=123456789012, width=width,
                                     height=height, negative="blurry",
                                     references=[{"path": p} for p in self.pics[:refs]])

    def call(self, tid, **kw):
        t = TG.load_target(tid, "image")
        return t.module.router_call(t, self.job(**kw))


class RequestTest(Jobs):
    def test_gemini_is_a_message_with_the_pictures_inline_first(self):
        model, args = self.call("nano_banana_pro", refs=2)
        self.assertEqual(model, "vertexai/gemini-3-pro-image")
        parts = args["contents"][0]["parts"]
        self.assertEqual(args["contents"][0]["role"], "user")
        self.assertEqual([("inlineData" in p, "text" in p) for p in parts], [(True, False), (True, False), (False, True)])
        self.assertEqual(parts[0]["inlineData"]["mimeType"], "image/png")
        self.assertEqual(parts[0]["inlineData"]["data"], File(self.pics[0], via="base64"))
        cfg = args["generationConfig"]
        self.assertEqual((cfg["imageConfig"]["aspectRatio"], cfg["imageConfig"]["imageSize"]), ("16:9", "1K"))
        self.assertEqual(cfg["responseModalities"], ["IMAGE"])
        self.assertLessEqual(cfg["seed"], 2147483647)

    def test_gemini_with_no_pictures_is_text_alone(self):
        _, args = self.call("gemini_3_1_flash_image")
        self.assertEqual(args["contents"][0]["parts"], [{"text": "Earl on his porch at dawn."}])

    def test_seedream_one_picture_as_itself_and_a_size_over_its_floor(self):
        _, args = self.call("seedream_5_0", refs=1)
        self.assertEqual(args["image"], File(self.pics[0]))
        w, h = (int(x) for x in args["size"].split("x"))
        self.assertGreaterEqual(w * h, 3686400)
        self.assertAlmostEqual(w / h, 1344 / 768, places=1)
        self.assertEqual(args["response_format"], "url")
        _, two = self.call("seedream_5_0", refs=2)
        self.assertEqual(two["image"], [File(p) for p in self.pics[:2]])

    def test_gpt_image_sizes_and_the_edit(self):
        _, args = self.call("gpt_image_2")
        self.assertEqual(args["size"], "1536x1024")
        self.assertNotIn("image", args)                       # text to image
        _, edit = self.call("gpt_image_2", refs=1, width=1024, height=1024)
        self.assertEqual((edit["size"], edit["image"]), ("1024x1024", File(self.pics[0])))

    def test_flux_numbered_fields_and_its_sizes(self):
        _, k = self.call("flux_kontext_pro", refs=3)
        self.assertEqual([k.get(f) for f in ("input_image", "input_image_2", "input_image_3")],
                         [File(p) for p in self.pics])
        self.assertNotIn("input_image_4", k)
        self.assertEqual(k["aspect_ratio"], "16:9")
        _, f2 = self.call("flux_2_pro", width=1344, height=768)
        self.assertEqual((f2["width"], f2["height"]), (1344, 768))
        _, big = self.call("flux_2_pro", width=4096, height=2048)
        self.assertEqual((big["width"], big["height"]), (2048, 2048))

    def test_qwen_is_a_message_with_its_size_starred(self):
        _, args = self.call("qwen_image_3", refs=2)
        content = args["input"]["messages"][0]["content"]
        self.assertEqual([list(c) for c in content], [["image"], ["image"], ["text"]])
        self.assertRegex(args["parameters"]["size"], r"^\d+\*\d+$")
        self.assertEqual(args["parameters"]["negative_prompt"], "blurry")

    def test_kling_names_its_pictures(self):
        _, args = self.call("kling_image_o1", refs=2, width=1024, height=1024)
        self.assertEqual([i["image"] for i in args["image_list"]], [File(p) for p in self.pics[:2]])
        self.assertTrue(args["prompt"].endswith("<<<image_1>>> <<<image_2>>>."))
        self.assertEqual((args["aspect_ratio"], args["resolution"]), ("1:1", "1k"))

    def test_krea_asks_what_its_old_code_did(self):
        model, args = self.call("krea_2_router", width=1344, height=768)
        self.assertEqual(model, "krea/krea-2")
        self.assertEqual(args, {"creativity": "medium", "prompt": "Earl on his porch at dawn.",
                                "aspect_ratio": "16:9", "resolution": "1K",
                                "seed": 123456789012 % 4294967296})

    def test_every_image_model_says_what_it_takes(self):
        for t in TG.list_targets("image"):
            if not t.spec.get("router"):
                continue
            with self.subTest(t.id):
                caps = t.capabilities()
                takes = bool(t.spec["router"]["inputs"].get("images"))
                self.assertEqual(caps["mode"], "edit" if takes else "t2i")
                self.assertEqual(caps["backends"], ["router"])


class ProposeImageTest(unittest.TestCase):
    """The wizard's first reading of an image model's schema (router_inspect.
    propose_image), against the built-ins mapped by hand."""

    def propose(self, model):
        import json
        from seriesmith import router_inspect as RI
        with open(os.path.join(HERE, "fixtures", "router_schemas", model.replace("/", "__") + ".json"),
                  encoding="utf-8") as fh:
            return RI.propose_image(model, json.load(fh))

    def test_a_chat_message_model(self):
        r = self.propose("vertexai/gemini-3-pro-image")
        inp = r["proposal"]["router"]["inputs"]
        self.assertEqual(inp["prompt"], {"list": "contents.0.parts", "item": {"text": "$prompt"}})
        self.assertEqual(inp["images"]["item"], {"inlineData": {"mimeType": "$mime", "data": "$url"}})
        self.assertEqual((inp["via"], inp["resolution"]["values"]), ("base64", ["1K", "2K", "4K"]))
        self.assertEqual(r["proposal"]["router"]["arguments"]["contents"], [{"role": "user"}])
        self.assertEqual((r["proposal"]["kind"], r["proposal"]["code"]), ("image", "builtin:router_image"))
        q = self.propose("qwen/qwen-image-3.0")["proposal"]["router"]["inputs"]
        self.assertEqual(q["size"], {"name": "parameters.size", "format": "{w}*{h}", "multiple": 16,
                                     "min_pixels": 262144, "max_pixels": 6553600})

    def test_fields_lists_and_sizes(self):
        flux = self.propose("bfl/flux-kontext-pro")["proposal"]["router"]["inputs"]
        self.assertEqual(flux["images"]["fields"][:2], ["input_image", "input_image_2"])
        gpt = self.propose("openai/gpt-image-2")["proposal"]["router"]["inputs"]
        self.assertEqual(gpt["size"]["values"], ["1024x1024", "1536x1024", "1024x1536"])
        kling = self.propose("kling/kling-image-o1")["proposal"]["router"]["inputs"]
        self.assertEqual(kling["images"]["mention"], "<<<image_{n}>>>")
        grok = self.propose("xai/grok-imagine-image-2.0")
        self.assertNotIn("size", grok["proposal"]["router"]["inputs"])     # "(not supported)"
        self.assertEqual(grok["proposal"]["capabilities"]["mode"], "t2i")

    def test_seedreams_size_is_flagged_to_check(self):
        r = self.propose("byteplus/seedream-5-0-260128")
        self.assertEqual(r["proposal"]["router"]["inputs"]["size"]["format"], "{w}x{h}")
        self.assertEqual([x["input"] for x in r["shared"]["size"]], ["size"])
        self.assertTrue(any("Seedance library" in w for w in r["warnings"]))

    def test_every_built_in_reads_without_a_hole(self):
        for model in ("vertexai/gemini-3-pro-image", "byteplus/seedream-5-0-260128", "openai/gpt-image-2",
                      "bfl/flux-kontext-pro", "bfl/flux-2-pro", "qwen/qwen-image-3.0",
                      "kling/kling-image-o1", "krea/krea-2"):
            with self.subTest(model):
                r = self.propose(model)
                self.assertEqual(r["unplaced"], [])
                self.assertIn("prompt", r["proposal"]["router"]["inputs"])


class ImageLimitsTest(unittest.TestCase):
    def test_round_trip_and_changes(self):
        from seriesmith import limits as L
        for t in TG.list_targets("image"):
            if t.spec.get("router"):
                with self.subTest(t.id):
                    d = {k: v for k, v in L.describe(t.spec).items() if k != "editable"}
                    self.assertEqual(L.apply(t.spec, d), t.spec)
        spec = TG.load_target("nano_banana_pro", "image").spec
        out = L.apply(spec, {"pictures": {"references": 0}, "size": {"resolutions": ["1K"]}})
        self.assertNotIn("images", out["router"]["inputs"])
        self.assertEqual((out["capabilities"]["mode"], out["capabilities"]["max_refs"]), ("t2i", 0))
        self.assertEqual(out["router"]["inputs"]["resolution"]["values"], ["1K"])
        back = L.apply(out, {"pictures": {"references": 2}})
        self.assertEqual((back["capabilities"]["mode"], back["capabilities"]["max_refs"]), ("edit", 2))
        with self.assertRaises(ValueError):
            L.apply(TG.load_target("krea2", "image").spec, {"size": {"ratios": ["1:1"]}})


class SizesTest(unittest.TestCase):
    def test_named_resolutions_by_area(self):
        self.assertEqual(RIM.pick_resolution(1344, 768, ["1K", "2K", "4K"]), "1K")
        self.assertEqual(RIM.pick_resolution(2048, 2048, ["1K", "2K", "4K"]), "2K")
        self.assertEqual(RIM.pick_resolution(9000, 9000, ["1K", "2K"]), "2K")

    def test_ratios_with_decimals_and_auto(self):
        self.assertEqual(RIM.nearest_ratio(2350, 1000, ["16:9", "2.35:1", "auto"]), "2.35:1")


class InlineOutputTest(unittest.TestCase):
    def outputs(self, result):
        run = RouterRun(types.SimpleNamespace(request_id="r"), "m")
        run.status, run.result = "succeeded", result
        return run.outputs()

    def test_gpt_images_b64_json_and_geminis_inline_data(self):
        b = base64.b64encode(b"pic").decode()
        (o,) = self.outputs({"data": [{"b64_json": b}]})
        self.assertEqual(o.type, "image")
        (g,) = self.outputs({"candidates": [{"content": {"parts": [
            {"text": "here it is"}, {"inlineData": {"mimeType": "image/png", "data": b}}]}}]})
        self.assertEqual(g.type, "image")
        with tempfile.TemporaryDirectory() as d:
            with open(g.save(os.path.join(d, "x.png")), "rb") as fh:
                self.assertEqual(fh.read(), b"pic")


if __name__ == "__main__":
    unittest.main()
