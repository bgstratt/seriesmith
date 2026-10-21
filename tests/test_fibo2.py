"""
Fibo 2.0 (targets/image/fibo2_dev, fibo2_edit_turbo): one graph that is text
to image or an edit, decided by whether there are references.
`TextEncodeFibo2` (ComfyUI's native node) takes the prompt and the pictures
on its autogrow slots (`images.image_1`, counting from one) and gives the
sampler both conditionings and the latent. The Edit Turbo only edits.
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

from seriesmith import jobs as J  # noqa: E402
from seriesmith import targets as TG  # noqa: E402
from seriesmith.targets import modelid as M  # noqa: E402

DEV, TURBO = "fibo2_dev", "fibo2_edit_turbo"


def api_graph(tid: str) -> dict:
    with open(os.path.join(ROOT, "seriesmith", "targets", "image", tid, "workflow.json"),
              encoding="utf-8") as fh:
        return J.graph_from(json.load(fh))


class TargetTest(unittest.TestCase):
    def test_both_are_edit_targets_with_four_references(self):
        for tid in (DEV, TURBO):
            t = TG.load_target(tid, "image")
            self.assertEqual((t.capabilities()["mode"], t.capabilities()["max_refs"]),
                             ("edit", 4), tid)

    def test_the_presets_are_brias(self):
        dev = TG.load_target(DEV).presets["final"]
        turbo = TG.load_target(TURBO).presets["final"]
        self.assertEqual((dev.steps, dev.extra["cfg"]), (50, 5.0))
        self.assertEqual((turbo.steps, turbo.extra["cfg"]), (4, 1.0))

    def test_every_model_it_names_has_a_download(self):
        for tid in (DEV, TURBO):
            t = TG.load_target(tid)
            p = t.presets["final"]
            named = {p.model} | {v for v in p.extra.values()
                                 if isinstance(v, str) and v.endswith(".safetensors")}
            for f in named:
                d = t.spec["downloads"][f]
                self.assertTrue(d["url"].startswith("https://huggingface.co/Comfy-Org/"), d["url"])
                self.assertTrue(d["url"].endswith(f), d["url"])

    def test_the_name_tells_the_checkpoints_apart(self):
        self.assertEqual(M.relation("fibo2", "fibo2-dev"), "ambiguous")
        self.assertEqual(M.relation("fibo2-edit-turbo", "fibo2-dev"), "different")
        self.assertEqual(M.name_family("fibo2_edit_turbo_bf16.safetensors",
                                       {k: M.FAMILIES[k]["names"]
                                        for k in ("fibo2-dev", "fibo2-edit-turbo")}),
                         ["fibo2-edit-turbo"])


class GraphTest(unittest.TestCase):
    def setUp(self):
        self.g = api_graph(DEV)
        self.enc = next(k for k, v in self.g.items() if v["class_type"] == "TextEncodeFibo2")

    def slots(self):
        return sorted(k for k in self.g[self.enc]["inputs"] if k.startswith("images."))

    def test_the_sampler_reads_everything_from_the_encoder(self):
        ks = next(v for v in self.g.values() if v["class_type"] == "KSampler")
        self.assertEqual([ks["inputs"][k] for k in ("positive", "negative", "latent_image")],
                         [[self.enc, 0], [self.enc, 1], [self.enc, 2]])
        clip = next(v for v in self.g.values() if v["class_type"] == "CLIPLoader")
        self.assertEqual(clip["inputs"]["type"], "fibo2")

    def test_references_grow_the_group(self):
        TG.load_target(DEV).patch_graph(self.g, None, {"references": ["a.png", "b.png"]})
        self.assertEqual(self.slots(), ["images.image_1", "images.image_2"])
        got = [self.g[self.g[self.enc]["inputs"][s][0]]["inputs"]["image"] for s in self.slots()]
        self.assertEqual(got, ["a.png", "b.png"])

    def test_no_references_is_text_to_image(self):
        TG.load_target(DEV).patch_graph(self.g, None, {"references": []})
        self.assertEqual(self.slots(), [])
        self.assertFalse(any(v["class_type"] == "LoadImage" for v in self.g.values()))

    def test_it_never_exceeds_max_refs(self):
        TG.load_target(DEV).patch_graph(self.g, None, {"references": [f"{i}.png" for i in range(9)]})
        self.assertEqual(len(self.slots()), 4)

    def test_the_turbo_only_edits(self):
        t = TG.load_target(TURBO)
        g = api_graph(TURBO)
        with self.assertRaises(ValueError) as cm:
            t.patch_graph(g, None, {"references": []})
        self.assertIn("only edits", str(cm.exception))
        t.patch_graph(g, None, {"references": ["a.png"]})
        enc = next(v for v in g.values() if v["class_type"] == "TextEncodeFibo2")
        self.assertIn("images.image_1", enc["inputs"])


if __name__ == "__main__":
    unittest.main()
