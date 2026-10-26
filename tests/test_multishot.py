"""
`continuous: multishot` (docs/MULTISHOT.md): a run of shots rendered as one
generation. The field (a shot's own line, a `#` header's for the shots after
its first, `none` breaking a group), the groups it makes, the target a group
renders on (its first shot's), and what `check` says about a group: errors for
one no target can render, warnings for what isn't sent as a picture.
"""
from __future__ import annotations

import copy
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from seriesmith import build as B  # noqa: E402
from seriesmith import targets as TG  # noqa: E402
from seriesmith.core.series_config import (character_ids, series_config_from, series_info,  # noqa: E402
                                           subject_ids, variant_of)
from seriesmith.core.story import ScriptError, parse_story  # noqa: E402

CFG = {
    "series": {"id": "t", "title": "T", "fps": 24, "target": "fasth3_omni"},
    "style": {"look": "a flat cartoon"},
    "audio": {"mode": "generate"},
    "subjects": {
        name: {"kind": "character", "name": name.title(), "design": f"{name}, drawn plainly",
               "sheet": f"refs/{name}/{name}_sheet_4panel.png"}
        for name in ("ada", "bo", "cy", "di")},
    "locations": {
        "kitchen": {"description": "a cramped diner kitchen", "plate": "refs/_bg/k.png"},
        "kitchen_on_bo": {"of": "kitchen", "description": "the kitchen from Ada's side",
                          "plate": "refs/_bg/k_bo.png"},
        "street": {"description": "a wet street at night", "plate": "refs/_bg/s.png"},
    },
}
CFG["subjects"]["ada_wet"] = {"of": "ada", "design": "Ada soaked through"}


def cfg(**series) -> dict:
    c = copy.deepcopy(CFG)
    c["series"].update(series)
    return series_config_from(c)


def story(body: str, c: dict | None = None):
    c = c or cfg()
    return parse_story("= e01  Test\n" + body, subject_ids(c), character_ids(c),
                       series_info(c), variant_of(c))


def shot(sid: str, who: str = "ada", extra: str = "", size: str = "ms") -> str:
    return f"## {sid}\nwho: {who}\nsize: {size}\ndur: 2\n{extra}{who.split(',')[0].title()} waits.\n"


THREE = ("# sq01  kitchen\n" + shot("sh010") + shot("sh020", "bo", "continuous: multishot\n", "cu")
         + shot("sh030", "ada", "continuous: multishot\n", "ws"))


class ParseTest(unittest.TestCase):
    def test_the_shots_after_the_first_join_it(self):
        sq = story(THREE).sequences[0]
        self.assertEqual([[s.id for s in g] for g in sq.multishot_groups()],
                         [["sh010", "sh020", "sh030"]])
        self.assertEqual([s.continues(sq) for s in sq.shots], [None, "multishot", "multishot"])

    def test_a_header_groups_its_sequence_and_none_starts_again(self):
        sq = story("# sq01  kitchen\ncontinuous: multishot\n" + shot("sh010") + shot("sh020", "bo")
                   + shot("sh030", "ada", "continuous: none\n") + shot("sh040", "bo")
                   + shot("sh050", "cy", "continuous: none\n")).sequences[0]
        # sh030 breaks the group and starts the next one; sh050 stands alone
        self.assertEqual([[s.id for s in g] for g in sq.multishot_groups()],
                         [["sh010", "sh020"], ["sh030", "sh040"]])

    def test_a_group_never_crosses_a_header(self):
        st = story(THREE + "# sq02  street\ncontinuous: multishot\n" + shot("sh040") + shot("sh050", "bo"))
        self.assertEqual([[[s.id for s in g] for g in sq.multishot_groups()] for sq in st.sequences],
                         [[["sh010", "sh020", "sh030"]], [["sh040", "sh050"]]])

    def test_a_bad_value_names_multishot(self):
        with self.assertRaises(ScriptError) as cm:
            story("# sq01  kitchen\n" + shot("sh010", extra="continuous: together\n"))
        self.assertIn("multishot", str(cm.exception))


class TargetTest(unittest.TestCase):
    def test_the_h3_targets_render_it(self):
        for tid in ("minimax_h3_ref2va", "fasth3_omni", "minimax_h3_fl2va"):
            self.assertIn("multishot", TG.continuous_modes(TG.load_target(tid, "video")), tid)
        self.assertNotIn("multishot", TG.continuous_modes(TG.load_target("ltx2", "video")))

    def test_the_group_renders_on_its_first_shots_target(self):
        c = cfg(target="minimax_h3_ref2va")
        text = THREE.replace("## sh010\n", "## sh010\ntarget: fasth3_omni\n")
        self.assertEqual(set(TG.shot_targets(story(text, c), c).values()), {"fasth3_omni"})

    def test_a_target_without_a_form_is_refused(self):
        c = cfg()
        text = THREE.replace("## sh010\n", "## sh010\ntarget: ltx2\n")
        with self.assertRaises(ValueError) as cm:
            TG.shot_targets(story(text, c), c)
        msg = str(cm.exception)
        self.assertIn("sh020", msg)
        self.assertIn("ltx2", msg)
        self.assertIn("fasth3_omni", msg)          # which targets can
        self.assertIn("continuous: none", msg)

    def test_a_shot_naming_another_target_is_refused(self):
        c = cfg()
        text = THREE.replace("## sh020\n", "## sh020\ntarget: minimax_h3_ref2va\n")
        with self.assertRaises(ValueError) as cm:
            TG.shot_targets(story(text, c), c)
        self.assertIn("a group is one target", str(cm.exception))

    def test_the_first_shot_of_a_sequence_is_refused(self):
        c = cfg()
        with self.assertRaises(ValueError) as cm:
            TG.shot_targets(story("# sq01  kitchen\n" + shot("sh010", extra="continuous: multishot\n")
                                  + shot("sh020", "bo"), c), c)
        self.assertIn("first shot of # sq01", str(cm.exception))


class CheckTest(unittest.TestCase):
    def check(self, text: str, c: dict | None = None) -> list[str]:
        c = c or cfg()
        return TG.multishot_check(story(text, c), c)

    def test_a_clean_group_says_nothing(self):
        self.assertEqual(self.check(THREE), [])

    def test_more_subjects_than_slots_is_refused(self):
        # Ref2VA takes three subjects a generation; the group names four
        c = cfg(target="minimax_h3_ref2va")
        text = THREE.replace("who: ada\nsize: ws", "who: cy, di\nsize: ws")
        with self.assertRaises(ValueError) as cm:
            self.check(text, c)
        self.assertIn("4 (Ada, Bo, Cy, Di)", str(cm.exception))
        self.assertIn("`members`", str(cm.exception))     # background people as one group subject
        self.assertEqual(self.check(text), [])      # Omni takes eight

    def test_a_second_picture_of_one_person_warns(self):
        w = self.check(THREE.replace("who: ada\nsize: ws", "who: ada_wet\nsize: ws"))
        self.assertEqual(len(w), 1)
        self.assertIn("sh030 names ada_wet, but the group already sends ada", w[0])

    def test_another_plate_warns_where_a_generation_takes_one(self):
        text = THREE.replace("## sh020\n", "## sh020\nplate: kitchen_on_bo\n")
        w = self.check(text)
        self.assertEqual(len(w), 1)
        self.assertIn("kitchen_on_bo, isn't sent as a picture", w[0])
        # FL2VA takes no plate at all: nothing to say
        self.assertEqual(self.check(text, cfg(target="minimax_h3_fl2va")), [])

    def test_a_group_opening_on_a_first_keyframe_warns_and_moves_with_it(self):
        c = cfg()
        text = ("# sq01  kitchen\n" + shot("sh005", "cy") + shot("sh010", extra="continuous: first\n")
                + shot("sh020", "bo", "continuous: multishot\n", "cu"))
        st = story(text, c)
        by = TG.shot_targets(st, c)
        # Omni reads no first keyframe: sh010 renders on FL2VA, and its group with it
        self.assertEqual((by["sh010"], by["sh020"]), ("minimax_h3_fl2va", "minimax_h3_fl2va"))
        w = TG.multishot_check(st, c)
        self.assertEqual(len(w), 1)
        self.assertIn("without its subjects' pictures", w[0])

    def test_the_warnings_reach_a_build(self):
        c = cfg()
        text = THREE.replace("## sh020\n", "## sh020\nplate: kitchen_on_bo\n")
        built = B.compile_groups(story(text, c), c, "final")
        self.assertTrue(any("isn't sent as a picture" in w for w in built[0][2]["warnings"]))


DIALOGUE = """# sq01  kitchen
## sh010
who: ada, bo
size: ms
dur: 3.04
Ada and Bo face each other.
ADA (flatly): You're late.
## sh020
continuous: multishot
who: bo
size: cu
dur: 1.62
Bo looks down at his hands.
BO: Traffic.
## sh030
continuous: multishot
who: ada_wet, bo
size: ms
dur: 2.33
Ada wrings out her soaked sleeve.
ADA: It isn't raining.
"""


class BuildTest(unittest.TestCase):
    """A group compiles into one shotlist entry: one generation of its shots."""

    def build(self, text: str, c: dict | None = None, target: str = "fasth3_omni") -> dict:
        c = c or cfg()
        built = B.compile_groups(story(text, c), c, "final")
        return next(doc for t, doc, _ in built if t.id == target)

    def test_one_entry_with_each_shot_and_where_it_starts(self):
        doc = self.build(DIALOGUE)
        self.assertEqual([e["id"] for e in doc["shots"]], ["sh010"])
        e = doc["shots"][0]
        # 73 + 39 + 56 frames = 168; H3's grid (17k+5) takes it to 175, the padding the last shot's
        self.assertEqual(e["length"], 175)
        self.assertEqual(e["multishot"], [
            {"id": "sh010", "start": 0, "frames": 73, "size": "ms"},
            {"id": "sh020", "start": 73, "frames": 39, "size": "cu"},
            {"id": "sh030", "start": 112, "frames": 63, "size": "ms"}])

    def test_the_prompt_cuts_at_each_shots_start(self):
        desc = self.build(DIALOGUE)["shots"][0]["prompt"][3]
        self.assertIn("[Shot 1] A medium shot frames", desc)
        self.assertIn("[Shot 2] At 00:03.042, the shot cuts. A close-up frames <Subject 2>", desc)
        self.assertIn("[Shot 3] At 00:04.667, the shot cuts.", desc)

    def test_a_person_keeps_one_speaker_id_and_one_picture(self):
        e = self.build(DIALOGUE)["shots"][0]
        # ada_wet, named in sh030, is Ada: the group sends Ada's picture once
        self.assertEqual(e["subjects"], ["ada", "bo"])
        desc = e["prompt"][3]
        self.assertIn("<Subject 1> (S1), flatly, says, <d>[English] You're late.</d>", desc)
        self.assertIn("<Subject 2> (S2) says, <d>[English] Traffic.</d>", desc)
        self.assertIn("<Subject 1> (S1) says, <d>[English] It isn't raining.</d>", desc)
        self.assertIn("Exactly two characters appear in this video", e["prompt"][0])
        self.assertIn("<Subject 2> (appears in [Shot 1], [Shot 2], [Shot 3])", e["prompt"][2])

    def test_a_group_opening_on_a_held_latent_counts_the_hold_in_its_cut_times(self):
        text = "# sq00  kitchen\n" + shot("sh005", "cy") + DIALOGUE.replace(
            "# sq01  kitchen\n## sh010\n", "## sh010\ncontinuous: latent\n")
        e = self.build(text)["shots"][1]
        self.assertEqual(e["hold"], 39)
        # the 39 held frames come first in the render, so the cuts are 39 frames later
        self.assertIn("[Shot 2] At 00:04.667, the shot cuts.", e["prompt"][3])

    def test_fl2va_takes_the_first_shots_first_keyframe_and_the_last_ones_last(self):
        doc = self.build(DIALOGUE, cfg(target="minimax_h3_fl2va"), "minimax_h3_fl2va")
        e = doc["shots"][0]
        self.assertEqual([x["id"] for x in doc["shots"]], ["sh010"])
        self.assertEqual(e["multishot"][1], {"id": "sh020", "start": 73, "frames": 39, "size": "cu"})
        self.assertIn("[Shot 2] At 00:03.042, the shot cuts.", e["prompt"])
        self.assertIn("Bo (S2) says: <d>[English] Traffic.</d>", e["prompt"])
        self.assertEqual(e["keyframes"].get("first"), "refs/shots/sh010/first.png")

    def test_a_dubbed_shot_in_a_group_is_refused(self):
        c = cfg()
        c["audio"] = {"mode": "generate"}
        text = DIALOGUE.replace("## sh020\ncontinuous: multishot\n",
                                "## sh020\ncontinuous: multishot\npolicy: clone\n")
        c["subjects"]["bo"]["voice_sample"] = "audio/voices/bo.wav"
        with self.assertRaises(ValueError) as cm:
            B.compile_groups(story(text, c), c, "final")
        self.assertIn("sh020 is clone", str(cm.exception))

    def test_shots_outside_a_group_compile_as_they_always_have(self):
        c = cfg()
        lone = "# sq01  kitchen\n" + shot("sh010") + shot("sh020", "bo", "", "cu")
        grouped = self.build(lone.replace("## sh020\n", "## sh020\ncontinuous: multishot\n"), c)
        plain = self.build(lone, c)
        self.assertEqual([e["id"] for e in plain["shots"]], ["sh010", "sh020"])
        self.assertEqual(len(grouped["shots"]), 1)


class JumpCutTest(unittest.TestCase):
    def test_a_cut_inside_a_group_is_still_a_cut(self):
        """The model draws the cut the script asks for: the same two people,
        the same plate, one size apart, is a jump cut in one generation too."""
        c = cfg()
        text = "# sq01  kitchen\n" + shot("sh010", "ada, bo") + shot("sh020", "ada, bo", "continuous: multishot\n", "mcu")
        st = story(text, c)
        warned = [w for w in B.story_warnings(st, c) if "jump cut" in w]
        self.assertEqual(len(warned), 1)
        latent = story(text.replace("continuous: multishot", "continuous: latent"), c)
        self.assertEqual([w for w in B.story_warnings(latent, c) if "jump cut" in w], [])


if __name__ == "__main__":
    unittest.main()
