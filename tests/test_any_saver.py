"""
A user's workflow made a model whatever it ends in (inspector.generic_saver):
SaveWEBM, an animated WebP, Video Combine, a video made by a node of its own,
SaveImage or a preview -- and an image workflow made an image model for refs
(targets/generic/workflow_image.py), its LoadImage nodes the pictures a take
starts from. The notes say which of what was read is an error, a warning or
just how the graph was read.
"""
from __future__ import annotations

import copy
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from seriesmith import inspector as IN  # noqa: E402
from seriesmith import jobs as J  # noqa: E402
from seriesmith import targets as TG  # noqa: E402
from test_phase12 import OBJECT_INFO_INSPECT, folder_list, ti2v_graph  # noqa: E402


def _node(inputs: dict, output_node: bool, outputs: list) -> dict:
    return {"input": {"required": inputs}, "output": outputs, "output_node": output_node,
            "python_module": "comfy_extras.nodes_video"}


# as a ComfyUI of 2026-10 answers /object_info for these (trimmed)
EXTRA_INFO = {
    "SaveWEBM": _node({"images": ["IMAGE"], "filename_prefix": ["STRING"], "fps": ["FLOAT"]}, True, ["IMAGE"]),
    "SaveAnimatedWEBP": _node({"images": ["IMAGE"], "filename_prefix": ["STRING"], "fps": ["FLOAT"]}, True,
                              ["IMAGE"]),
    "VHS_VideoCombine": {"input": {"required": {"images": ["IMAGE"], "frame_rate": ["FLOAT"]},
                                   "optional": {"audio": ["AUDIO"]}},
                         "output": ["VHS_FILENAMES"], "output_node": True, "python_module": "custom_nodes.vhs"},
    "MyVideoMaker": _node({"frames": ["IMAGE"], "fps": ["FLOAT"]}, False, ["VIDEO"]),
    "SaveImage": _node({"images": ["IMAGE"], "filename_prefix": ["STRING"]}, True, ["IMAGE"]),
    "PreviewImage": _node({"images": ["IMAGE"]}, True, []),
    "EmptyLatentImage": _node({"width": ["INT", {"default": 1024, "step": 8}],
                               "height": ["INT", {"default": 1024, "step": 8}],
                               "batch_size": ["INT", {"default": 1}]}, False, ["LATENT"]),
    "VAEEncode": _node({"pixels": ["IMAGE"], "vae": ["VAE"]}, False, ["LATENT"]),
}
INFO = dict(OBJECT_INFO_INSPECT, **EXTRA_INFO)
INFO["SaveVideo"] = dict(INFO["SaveVideo"], output_node=True)


def video_graph(ending: dict) -> dict:
    """The stock ti2v graph with its CreateVideo / SaveVideo replaced by `ending`."""
    g = J.graph_from(ti2v_graph(), "ti2v")
    del g["11"], g["12"]
    g.update(copy.deepcopy(ending))
    return g


def image_graph(loads: int = 0) -> dict:
    """A text-to-image graph (the stock graph's loaders and sampler), ending
    in SaveImage and a preview; `loads` LoadImage nodes feed the latent."""
    g = J.graph_from(ti2v_graph(), "ti2v")
    for k in ("7", "8", "11", "12"):
        del g[k]
    g["8"] = {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}}
    g["11"] = {"class_type": "SaveImage", "inputs": {"images": ["10", 0], "filename_prefix": "x"}}
    g["12"] = {"class_type": "PreviewImage", "inputs": {"images": ["10", 0]}}
    for i in range(loads):
        nid = str(20 + i)
        g[nid] = {"class_type": "LoadImage", "inputs": {"image": "ref.png"},
                  "_meta": {"title": f"Load Image {i}"}}
        if i == 0:
            g["21" if loads > 1 else "30"] = g.get("21") or {}
        g[str(30 + i)] = {"class_type": "VAEEncode", "inputs": {"pixels": [nid, 0], "vae": ["4", 0]}}
    if loads:
        g["9"]["inputs"]["latent_image"] = ["30", 0]
        g = {k: v for k, v in g.items() if v}
    return g


def inspect(g: dict, kind: str = "auto") -> dict:
    return IN.inspect_graph(g, INFO, folder_list, workflow_name="mine.json", kind=kind)


class VideoSaversTest(unittest.TestCase):
    def test_webm_and_an_animated_webp(self):
        r = inspect(video_graph({
            "11": {"class_type": "SaveWEBM", "inputs": {"images": ["10", 0], "fps": 24.0}},
            "12": {"class_type": "SaveAnimatedWEBP", "inputs": {"images": ["10", 0], "fps": 24.0}}}))
        sv = r["proposal"]["binding"]["saver"]
        self.assertEqual(r["proposal"]["kind"], "video")
        self.assertEqual(sv["replace"], {"class_type": "SaveWEBM", "inputs": {"images": "images"}})
        self.assertEqual(sv["drop"], ["SaveAnimatedWEBP"])
        self.assertEqual(sv["class_type"], TG.load_target(TG.DEFAULT_VIDEO_TARGET, "video").binding.saver_class)
        # a render puts seriesmith's saver in SaveWEBM's place and drops the WebP
        t = TG.Target(TG.load_target(TG.DEFAULT_VIDEO_TARGET, "video").folder, r["proposal"])
        g = video_graph({"11": {"class_type": "SaveWEBM", "inputs": {"images": ["10", 0]}},
                         "12": {"class_type": "SaveAnimatedWEBP", "inputs": {"images": ["10", 0]}}})
        J.prepare_saver(g, t.binding)
        self.assertEqual(sorted(v["class_type"] for v in g.values() if "Save" in v["class_type"]),
                         [sv["class_type"]])
        self.assertEqual(g["h3_saver"]["inputs"]["images"], ["10", 0])

    def test_nothing_is_bound_to_a_dropped_node(self):
        """The animated WebP is dropped by a render: its fps widget can't be
        where the shot's frame rate goes (a dry run on a real workflow found
        nothing to set)."""
        r = inspect(video_graph({
            "11": {"class_type": "SaveWEBM", "inputs": {"images": ["10", 0], "fps": 24.0}},
            "12": {"class_type": "SaveAnimatedWEBP", "inputs": {"images": ["10", 0], "fps": 24.0}}}))
        for name, spec in r["proposal"]["binding"]["params"].items():
            for one in (spec if isinstance(spec, list) else [spec]):
                self.assertNotEqual(one.get("class_type"), "SaveAnimatedWEBP", name)

    def test_video_combine_takes_the_sound_too(self):
        g = video_graph({"11": {"class_type": "VHS_VideoCombine",
                                "inputs": {"images": ["10", 0], "audio": ["13", 0], "frame_rate": 24}},
                         "13": {"class_type": "LoadAudio", "inputs": {"audio": "a.wav"}}})
        sv = inspect(g)["proposal"]["binding"]["saver"]
        self.assertEqual(sv["replace"], {"class_type": "VHS_VideoCombine",
                                         "inputs": {"images": "images", "audio": "audio"}})

    def test_a_video_made_by_a_node_of_its_own(self):
        r = inspect(video_graph({"11": {"class_type": "MyVideoMaker", "inputs": {"frames": ["10", 0], "fps": 24}},
                                 "12": {"class_type": "SaveVideo", "inputs": {"video": ["11", 0]}}}))
        sv = r["proposal"]["binding"]["saver"]
        self.assertEqual(sv["replace"], {"class_type": "MyVideoMaker", "inputs": {"images": "frames"}})
        self.assertEqual(sv["drop"], ["SaveVideo"])

    def test_nothing_saved_is_an_error(self):
        g = video_graph({})
        with self.assertRaisesRegex(IN.InspectError, "saves or previews"):
            inspect(g, "video")

    def test_the_stock_graph_is_read_as_it_was(self):
        r = IN.inspect_graph(ti2v_graph(), OBJECT_INFO_INSPECT, folder_list, workflow_name="x.json")
        self.assertEqual(r["proposal"]["binding"]["saver"]["replace"]["class_type"], "CreateVideo")


class ImageWorkflowTest(unittest.TestCase):
    def test_text_to_image(self):
        r = inspect(image_graph())
        p = r["proposal"]
        self.assertEqual((p["kind"], p["code"]), ("image", "builtin:workflow_image"))
        self.assertEqual(p["capabilities"], {"mode": "t2i", "max_refs": 0})
        # SaveImage as the shipped image targets have it (the preview is pruned: the
        # take's graph keeps only what the save depends on)
        self.assertEqual({k: p["binding"]["saver"][k] for k in ("class_type", "replace")},
                         {"class_type": "H3SaveRefTake",
                          "replace": {"class_type": "SaveImage", "inputs": {"images": "images"}}})
        for name in ("prompt", "seed", "width", "height", "model"):
            self.assertIn(name, p["binding"]["params"], name)
        self.assertNotIn("references", p["binding"])
        self.assertEqual(IN.validate_spec(dict(p)), [])

    def test_an_edit_workflow_takes_pictures(self):
        r = inspect(image_graph(loads=2))
        p = r["proposal"]
        self.assertEqual(p["capabilities"], {"mode": "edit", "max_refs": 2})
        self.assertEqual(p["binding"]["references"], [{"class_type": "LoadImage", "title": "Load Image 0"},
                                                      {"class_type": "LoadImage", "title": "Load Image 1"}])
        self.assertTrue(any(n["level"] == "warning" and n["text"].startswith("pictures:") for n in r["notes"]))

    def test_the_pictures_go_into_the_slots(self):
        from seriesmith.targets.generic import workflow_image as W
        p = inspect(image_graph(loads=2))["proposal"]
        t = TG.Target(TG.load_target("krea2", "image").folder, p)
        g = image_graph(loads=2)
        W.patch_graph(t, g, None, {"references": ["seriesmith/a.png"]})
        self.assertEqual([g[n]["inputs"]["image"] for n in ("20", "21")], ["seriesmith/a.png"] * 2)
        W.patch_graph(t, g, None, {"references": ["a.png", "b.png", "c.png"]})
        self.assertEqual([g[n]["inputs"]["image"] for n in ("20", "21")], ["a.png", "b.png"])
        with self.assertRaisesRegex(ValueError, "edits a picture"):
            W.patch_graph(t, image_graph(loads=2), None, {})


class NotesTest(unittest.TestCase):
    def test_levels(self):
        r = IN.inspect_graph(ti2v_graph(), OBJECT_INFO_INSPECT, folder_list, workflow_name="x.json")
        levels = {n["level"] for n in r["notes"]}
        self.assertLessEqual(levels, {"error", "warning", "info"})
        by = {n["text"].split(":")[0]: n["level"] for n in r["notes"]}
        self.assertEqual(by["saving"], "info")
        self.assertEqual(by["keyframes"], "warning")
        self.assertEqual([n["level"] for n in r["notes"]], sorted((n["level"] for n in r["notes"]),
                         key=["error", "warning", "info"].index))


if __name__ == "__main__":
    unittest.main()
