"""
FastH3 Omni (targets/video/fasth3_omni, image/fasth3_omni_still): FastVideo's
8-step H3, compiled as Ref2VA is but with the node's nine picture sockets --
eight subjects and the plate as <Picture 9> -- where Ref2VA keeps three and
<Picture 4>. What matters: the slots follow the target (compile, prompt, the
shot plan, Cloud's lowering), Ref2VA's shotlists don't change, and the
workflow wires the loader's last outputs into the extra sockets.
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from seriesmith import cloud as C  # noqa: E402
from seriesmith import jobs as J  # noqa: E402
from seriesmith import shotnodes as SN  # noqa: E402
from seriesmith import targets as TG  # noqa: E402
from seriesmith.backends import File  # noqa: E402
from seriesmith.targets import modelid as M  # noqa: E402
from test_cloud import write_png  # noqa: E402
from test_ltx_ingredients import kitchen_sink  # noqa: E402

OMNI, H3 = "fasth3_omni", "minimax_h3_ref2va"


def pictures(prompt) -> set[str]:
    text = "\n".join(prompt) if isinstance(prompt, list) else prompt
    return set(re.findall(r"<Picture \d+>", text))


def api_graph(tid: str, kind: str = "video") -> dict:
    with open(os.path.join(ROOT, "seriesmith", "targets", kind, tid, "workflow.json"),
              encoding="utf-8") as fh:
        return J.graph_from(json.load(fh))


class CompileTest(unittest.TestCase):
    def setUp(self):
        self.cfg, self.story = kitchen_sink()

    def compile(self, tid):
        return TG.load_target(tid, "video").compile_episode(self.story, self.cfg, "final")

    def test_the_plate_is_picture_9(self):
        doc, _ = self.compile(OMNI)
        self.assertEqual(doc["defaults"]["subject_slots"], 8)
        t = TG.load_target(OMNI)
        for sh in doc["shots"]:
            slots = {r["slot"] for r in t.ref_slots(doc, sh) if r["kind"] == "image"}
            if not sh.get("text_place"):
                self.assertIn("Picture 9", slots, sh["id"])
            self.assertNotIn("Picture 4", slots - {f"Picture {i}" for i in
                                                   range(1, len(sh["subjects"]) + 1)})
            if sh["background"]:
                self.assertIn("<Picture 9>", pictures(sh["prompt"]), sh["id"])
                self.assertNotIn("<Picture 4>", pictures(sh["prompt"]) if len(sh["subjects"]) < 4
                                 else set(), sh["id"])

    def test_its_shotlist_says_whose_it_is(self):
        """A shotlist without `target` is read as Ref2VA's (jobs.shotlist_target),
        which would recompile an Omni shot with three slots."""
        doc, _ = self.compile(OMNI)
        self.assertEqual(doc["target"], OMNI)
        self.assertEqual(J.shotlist_target(doc).id, OMNI)

    def test_ref2va_is_unchanged(self):
        doc, _ = self.compile(H3)
        self.assertNotIn("target", doc)
        self.assertNotIn("subject_slots", doc["defaults"])
        for sh in doc["shots"]:
            if sh["background"]:
                self.assertIn("<Picture 4>", pictures(sh["prompt"]), sh["id"])

    def test_its_own_model_and_no_lora(self):
        doc, _ = self.compile(OMNI)
        d = doc["defaults"]
        self.assertEqual((d["model"], d["lora"], d["steps"]),
                         ("fasth3_omniref_8step_pruned_int8_convrot.safetensors", "", 8))

    def test_eight_subjects_fit_and_nine_do_not(self):
        t = TG.load_target(OMNI)
        self.assertEqual(len(t.recipe["subject_slots"]), 8)
        self.assertEqual(t.recipe["plate_slot"], "Picture 9")


class ShotPlanTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.sp = SN.shotplan()
        self.files = {}
        for name in ("plate.png", *(f"s{i}.png" for i in range(1, 10))):
            p = os.path.join(self._tmp.name, name)
            write_png(p)
            self.files[name] = p

    def doc(self, n_subjects: int, slots: int | None) -> dict:
        subjects = [f"s{i}" for i in range(1, n_subjects + 1)]
        d = {"defaults": {"width": 512, "height": 288, "sheet_panels": 4},
             "subjects": {s: {"kind": "prop", "sheet": f"{s}.png"} for s in subjects},
             "shots": [{"id": "sh010", "subjects": subjects, "background": "plate.png",
                        "duration": 3.0, "prompt": "p", "seed": 1, "steps": 8}]}
        if slots is not None:
            d["defaults"]["subject_slots"] = slots
        return d

    def plan(self, doc):
        return self.sp.plan_shot(doc, 0, "auto", 24.0, "", lambda p: self.files.get(p, ""))

    def test_ref2va_keeps_three_sockets(self):
        p = self.plan(self.doc(1, None))
        self.assertEqual(len(p["refs"]), 3)
        self.assertIn("<Picture 4>", p["bg_note"])

    def test_omni_fills_eight_sockets_and_the_plate_is_picture_9(self):
        p = self.plan(self.doc(2, 8))
        self.assertEqual(len(p["refs"]), 8)
        self.assertEqual(sum(1 for r in p["refs"] if r.get("placeholder")), 6)
        self.assertIn("<Picture 9>", p["bg_note"])

    def test_eight_subjects_render_and_nine_are_refused(self):
        self.assertEqual(len(self.plan(self.doc(8, 8))["refs"]), 8)
        with self.assertRaises(ValueError) as cm:
            self.plan(self.doc(9, 8))
        self.assertIn("slot 9 is the background", str(cm.exception))


class WorkflowTest(unittest.TestCase):
    def setUp(self):
        self.g = api_graph(OMNI)
        self.h3 = next(v for v in self.g.values() if v["class_type"] == "MiniMaxH3ReferenceToVideo")
        self.loader = J.node_of(self.g, TG.load_target(OMNI).binding.loader_class)

    def test_the_loader_feeds_all_nine_sockets(self):
        got = {k: self.h3["inputs"][k] for k in self.h3["inputs"] if k.startswith("ref_images.")}
        want = {f"ref_images.ref_image_{i}": [self.loader, o]
                for i, o in enumerate([2, 3, 4, 17, 18, 19, 20, 21, 5])}
        self.assertEqual(got, want)

    def test_the_model_chain_is_fasth3s(self):
        types = {v["class_type"] for v in self.g.values()}
        self.assertNotIn("LoraLoaderModelOnly", types)
        self.assertNotIn("H3SLAAttention", types)
        shift = next(v for v in self.g.values() if v["class_type"] == "MiniMaxH3SigmaShift")
        self.assertEqual((shift["inputs"]["shift_video"], shift["inputs"]["shift_audio"]), (12, 3))
        vsa = next(v for v in self.g.values() if v["class_type"] == "BlockSparseAttention")
        self.assertEqual((vsa["inputs"]["selection"], vsa["inputs"]["selection.keep_percent"]),
                         ("vsa", 10))

    def test_the_loader_declares_the_extra_outputs_last(self):
        from importlib import util
        spec = util.spec_from_file_location("sm_shot_nodes", os.path.join(ROOT, "comfy_nodes",
                                                                          "shot.py"))
        try:
            mod = util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        except ImportError:
            self.skipTest("torch is not installed here")
        names = mod.SeriesmithShotLoader.RETURN_NAMES
        self.assertEqual(names[2:6], ("ref_1", "ref_2", "ref_3", "ref_bg"))
        self.assertEqual(names[17:], ("ref_4", "ref_5", "ref_6", "ref_7", "ref_8"))
        self.assertEqual(len(mod.SeriesmithShotLoader.RETURN_TYPES), len(names))


class CloudLowerTest(unittest.TestCase):
    """The loader's pictures put where they were read, in <Picture N> order."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.staging = os.path.join(self._tmp.name, "staging")
        os.makedirs(self.staging)
        self.paths = {}
        for name in ("plate.png", "a.png", "b.png"):
            p = os.path.join(self._tmp.name, name)
            write_png(p)
            self.paths[name] = p

    def lowered(self, slots: int | None) -> dict:
        doc = {"defaults": {"width": 512, "height": 288},
               "subjects": {"a": {"kind": "prop", "sheet": "a.png"},
                            "b": {"kind": "prop", "sheet": "b.png"}},
               "shots": [{"id": "sh010", "subjects": ["a", "b"], "background": "plate.png",
                          "duration": 3.0, "prompt": "p", "seed": 1, "steps": 8}]}
        if slots:
            doc["defaults"]["subject_slots"] = slots
        files = ["a.png", "b.png", "plate.png"]
        li = {"shotlist": json.dumps(doc), "files": json.dumps(files), "index": 0,
              "panel_mode": "auto", "fps": 24.0,
              **{SN.file_input(i): File(self.paths[f]) for i, f in enumerate(files)}}
        outs = [2, 3, 4, 17, 18, 19, 20, 21, 5] if slots else [2, 3, 4, 5]
        g = {"L": {"class_type": "SeriesmithShotLoader", "inputs": li},
             "H": {"class_type": "MiniMaxH3ReferenceToVideo",
                   "inputs": {f"ref_images.ref_image_{i}": ["L", o] for i, o in enumerate(outs)}}}
        C._lower_loader(g, "L", self.staging)
        return g

    def source(self, g, k):
        return g[g["H"]["inputs"][k][0]]["_meta"]["title"]

    def test_omni_sends_nine_pictures_the_plate_last(self):
        g = self.lowered(8)
        ins = g["H"]["inputs"]
        self.assertEqual(len([k for k in ins if k.startswith("ref_images.")]), 9)
        self.assertEqual([self.source(g, f"ref_images.ref_image_{i}") for i in range(9)],
                         [f"<Picture {i}>" for i in range(1, 10)])
        plate = g[ins["ref_images.ref_image_8"][0]]["inputs"]["image"]
        self.assertEqual(plate.path, self.paths["plate.png"])

    def test_ref2va_sends_four(self):
        g = self.lowered(None)
        self.assertEqual([self.source(g, f"ref_images.ref_image_{i}") for i in range(4)],
                         [f"<Picture {i}>" for i in range(1, 5)])
        plate = g[g["H"]["inputs"]["ref_images.ref_image_3"][0]]["inputs"]["image"]
        self.assertEqual(plate.path, self.paths["plate.png"])


class ModelFamilyTest(unittest.TestCase):
    def test_omni_is_an_h3_variant_of_its_own(self):
        self.assertEqual(M.relation("fasth3-omni", "fasth3-omni"), "same")
        self.assertEqual(M.relation("fasth3-omni", "minimax-h3-ref2va"), "different")
        self.assertEqual(M.relation("minimax-h3", "fasth3-omni"), "ambiguous")

    def test_its_targets_want_it(self):
        for tid, kind in ((OMNI, "video"), ("fasth3_omni_still", "image")):
            t = TG.load_target(tid, kind)
            self.assertEqual(t.models["model"]["family"], "fasth3-omni")
            self.assertNotIn("loras", t.models)
            p = t.presets["final"]
            self.assertEqual((p.model, p.steps), (
                "fasth3_omniref_8step_pruned_int8_convrot.safetensors", 8))
            for f in {p.model} | {v for v in p.extra.values()
                                  if isinstance(v, str) and v.endswith(".safetensors")}:
                self.assertIn(f, t.spec["downloads"], (tid, f))


class StillTest(unittest.TestCase):
    def test_it_is_an_edit_target_with_nine_references(self):
        t = TG.load_target("fasth3_omni_still", "image")
        self.assertEqual((t.capabilities()["mode"], t.capabilities()["max_refs"]), ("edit", 9))

    def test_the_graph_is_the_h3_stills_with_fasth3s_chain(self):
        g = api_graph("fasth3_omni_still", "image")
        types = {v["class_type"] for v in g.values()}
        self.assertTrue({"BlockSparseAttention", "MiniMaxH3SigmaShift",
                         "MiniMaxH3ReferenceToVideo", "ImageFromBatch"} <= types)
        self.assertFalse({"LoraLoaderModelOnly", "H3SLAAttention"} & types)
        t = TG.load_target("fasth3_omni_still", "image")
        t.patch_graph(g, None, {"references": ["a.png", "b.png"]})
        h3 = next(v for v in g.values() if v["class_type"] == "MiniMaxH3ReferenceToVideo")
        self.assertEqual(sorted(k for k in h3["inputs"] if k.startswith("ref_images.")),
                         ["ref_images.ref_image_0", "ref_images.ref_image_1"])


if __name__ == "__main__":
    unittest.main()
