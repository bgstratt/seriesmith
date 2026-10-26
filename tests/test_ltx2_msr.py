"""
ltx2_msr: LTX-2.5 with Licon's MSR LoRA (docs/MULTISHOT.md, "LTX MSR
revisited"). What an entry carries (the guide's pictures, PromptRelay's two
prompts), how a `continuous: multishot` group is written (one prompt, a
paragraph a shot with its seconds), each person's sheet at queue time, and the
pictures into the graph. Offline: nothing reaches a ComfyUI.
"""
from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from seriesmith import targets as TG  # noqa: E402
from seriesmith.targets.video.ltx2_msr import compile as M  # noqa: E402
from test_multishot import CFG, DIALOGUE  # noqa: E402

# Ada alone, then Bo, back to Ada: Bo is named in Ada's shot but isn't in it
LOOKS_AT = """# sq01  kitchen
## sh010
who: ada
size: ms
dur: 3
Ada looks at Bo across the counter.
ADA: You're late.
ADA: Again.
## sh020
continuous: multishot
who: bo
size: cu
dur: 2
Bo shrugs.
"""


class Episode:
    """A built episode on ltx2_msr in a temporary folder, its pictures on disk."""

    def __init__(self, test: unittest.TestCase, script: str, face: bool = True):
        from seriesmith import edit as E
        from test_render import png_bytes
        tmp = tempfile.TemporaryDirectory()
        test.addCleanup(tmp.cleanup)
        self.ep = os.path.join(tmp.name, "e01")
        c = copy.deepcopy(CFG)
        c["series"]["target"] = "ltx2_msr"
        if face:
            c["subjects"]["bo_face"] = {"of": "bo", "design": "Bo's face",
                                        "sheet": "refs/bo/bo_face.png"}
        files = [(e["sheet"], (2048, 512)) for e in c["subjects"].values() if e.get("sheet")]
        if face:
            files[-1] = (c["subjects"]["bo_face"]["sheet"], (512, 512))
        files += [(e["plate"], (1344, 768)) for e in c["locations"].values()]
        for path, (w, h) in files:
            full = os.path.join(self.ep, path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "wb") as fh:
                fh.write(png_bytes(w, h))
        with open(os.path.join(self.ep, "series.json"), "w", encoding="utf-8") as fh:
            json.dump(c, fh)
        with open(os.path.join(self.ep, "e01.md"), "w", encoding="utf-8") as fh:
            fh.write("= e01  Test\n" + script)
        test.assertTrue(E.build_episode(self.ep)["ok"])

    def entry(self, sid: str = "sh010") -> dict:
        from seriesmith import jobs as J
        doc, i = J.find_shot(self.ep, "final", sid)
        return doc["shots"][i]


class EntryTest(unittest.TestCase):
    def test_a_group_is_one_prompt_a_paragraph_a_shot_with_its_seconds(self):
        e = Episode(self, DIALOGUE).entry()
        self.assertEqual([m["id"] for m in e["multishot"]], ["sh010", "sh020", "sh030"])
        local = e["prompt"]
        self.assertTrue(local.startswith(M.P.CONTINUITY))
        self.assertIn("Shot 1 (3.0 seconds): A medium shot of Image 1 and Image 2, in the place "
                      "matching Image 3. All faces clearly visible.", local)
        self.assertIn("Shot 2 (1.6 seconds), a hard cut: A close-up of Image 2 alone, in the place "
                      "matching Image 3. No other characters are visible.", local)
        self.assertIn('Image 1 speaks with visible lip movement, flatly: "You\'re late."', local)
        self.assertIn("The others listen with their lips closed.", local)
        self.assertNotIn("|", local)                      # one PromptRelay segment: the model cuts

    def test_the_pictures_are_each_person_once_then_the_plate(self):
        e = Episode(self, DIALOGUE).entry()
        refs = e["references"]
        self.assertEqual([r.get("subject") or r.get("location") for r in refs],
                         ["ada", "bo", "kitchen"])        # ada_wet in sh030 is Ada: not sent again
        self.assertEqual(refs[1]["face"], "refs/bo/bo_face.png")
        g = e["global_prompt"]
        self.assertIn("Image 1: Ada, ada, drawn plainly.", g)
        self.assertIn("Image 3: Scene, a cramped diner kitchen.", g)
        self.assertTrue(g.endswith("The whole video is a flat cartoon."))

    def test_someone_off_this_shot_is_someone_and_a_speakers_lines_run_on(self):
        local = Episode(self, LOOKS_AT).entry()["prompt"]
        self.assertIn("Image 1 looks at someone across the counter.", local)
        self.assertIn('Image 1 speaks with visible lip movement: "You\'re late. Again."', local)
        self.assertIn("Image 2 shrugs.", local)

    def test_a_shot_with_no_one_pictured_is_words_alone(self):
        script = "# sq01  kitchen\n## sh010\nsize: ws\ndur: 2\nSteam rises from a pot.\n"
        e = Episode(self, script).entry()
        self.assertEqual(e["references"], [])
        self.assertNotIn("Image", e["prompt"] + e["global_prompt"])

    def test_the_group_renders_on_it(self):
        self.assertIn("multishot", TG.continuous_modes(TG.load_target("ltx2_msr", "video")))
        self.assertEqual(TG.subject_slots(TG.load_target("ltx2_msr", "video")), 4)


class SheetTest(unittest.TestCase):
    """Each person's picture as Licon's own: 16:9 on grey at the render size."""

    def job(self, root: str):
        return SimpleNamespace(root=root, width=1664, height=960)

    def test_a_strip_gives_the_body_the_face_and_the_back(self):
        e = Episode(self, DIALOGUE, face=False)
        spec = M.sheet_spec(self.job(e.ep), {"subject": "ada", "path": "refs/ada/ada_sheet_4panel.png"},
                            CFG["subjects"])
        self.assertEqual([p["crop"]["index"] for p in spec["panels"]], [0, 3, 2])
        self.assertEqual((spec["width"], spec["height"], spec["background"]), (1664, 960, "grey"))

    def test_a_face_picture_takes_the_face_panel(self):
        e = Episode(self, DIALOGUE)
        spec = M.sheet_spec(self.job(e.ep), e.entry()["references"][1], CFG["subjects"])
        self.assertTrue(spec["panels"][1]["path"].endswith("bo_face.png"))
        self.assertNotIn("crop", spec["panels"][1])

    def test_a_whole_picture_without_a_face_gives_its_head(self):
        from test_render import png_bytes
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "p.png"), "wb") as fh:
                fh.write(png_bytes(1280, 1712))
            spec = M.sheet_spec(self.job(d), {"subject": "ada", "path": "p.png"}, CFG["subjects"])
        whole, face = spec["panels"]
        self.assertNotIn("crop", whole)
        l, t, r, b = face["crop"]["box"]
        self.assertAlmostEqual(b - t, (r - l) * 1280 / 1712)     # a square of the picture

    def test_the_helper_cuts_a_box(self):
        from seriesmith.helpers import refsheet as RS
        from test_render import png_bytes
        try:
            import PIL  # noqa: F401
        except ImportError:
            self.skipTest("PIL")
        with tempfile.TemporaryDirectory() as d:
            src, out = os.path.join(d, "p.png"), os.path.join(d, "s.png")
            with open(src, "wb") as fh:
                fh.write(png_bytes(400, 800))
            rep = RS.compose({"width": 640, "height": 360, "background": "grey", "panels": [
                {"path": src, "fit": "figure"},
                {"path": src, "fit": "figure", "crop": {"box": [0.25, 0.0, 0.75, 0.25]}}]}, out)
            self.assertEqual((rep["width"], rep["height"]), (640, 360))
            self.assertTrue(os.path.isfile(out))


class GraphTest(unittest.TestCase):
    def graph(self) -> dict:
        from seriesmith import jobs as J
        return J.load_graph(os.path.join(ROOT, "seriesmith", "targets", "video", "ltx2_msr",
                                         "workflow.json"))

    def test_the_pictures_go_into_both_guides_and_an_empty_slot_is_left_out(self):
        g = self.graph()
        M.patch_graph(M.TARGET, g, None, {"pic1": "a.png", "pic2": "b.png", "background": "k.png"})
        for k in ("guide1", "guide2"):
            i = g[k]["inputs"]
            self.assertEqual((i["pic1"], i["pic2"], i["background"]),
                             (["load_pic1", 0], ["load_pic2", 0], ["load_background", 0]))
            self.assertNotIn("pic3", i)
        self.assertEqual(g["load_pic2"]["inputs"]["image"], "b.png")
        self.assertNotIn("load_pic3", g)

    def test_no_picture_splices_the_guides_out(self):
        g = self.graph()
        M.patch_graph(M.TARGET, g, None, {})
        self.assertFalse([k for k, v in g.items() if v["class_type"] == M.GUIDE])
        self.assertEqual(g["guider1"]["inputs"]["positive"], ["cond1", 0])
        self.assertEqual(g["concat1"]["inputs"]["video_latent"], ["latent", 0])
        self.assertEqual(g["cond2"]["inputs"]["positive"], ["relay2", 1])
        self.assertEqual(g["concat2"]["inputs"]["video_latent"], ["upscale", 0])

    def test_stage_two_refines_from_0_6(self):
        self.assertEqual(self.graph()["sigmas2"]["inputs"]["sigmas"], "0.6, 0.4219, 0.2, 0.0")


if __name__ == "__main__":
    unittest.main()
