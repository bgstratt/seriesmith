"""
A script as the storyboard sees it (seriesmith/core/board.py; docs/PLAN.md, the storyboard): every
script comes back byte for byte, and what the board reads agrees with the build's own parser.
"""
from __future__ import annotations

import glob
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from seriesmith.core import board as B  # noqa: E402
from seriesmith.core import spotting as SP  # noqa: E402
from seriesmith.core import story  # noqa: E402

HEAD = "= ep01  Draft\n\n"
SHOT = "## {id}\ntarget: hold\nwho: june\ndur: 3.5\nSomething happens.\n\n"


def scripts() -> list[str]:
    found: list[str] = []
    for where in ("examples", "tests/fixtures", "tests/local/fixtures"):
        found += glob.glob(os.path.join(ROOT, where, "**", "*.md"), recursive=True)
    return [p for p in found if os.path.basename(p).lower() != "readme.md"]


def valid_pairs() -> list[tuple[str, str, dict]]:
    """Scripts with a series config beside them that the build itself accepts."""
    out = []
    for path in scripts():
        config = os.path.join(os.path.dirname(path), "series.json")
        if not os.path.isfile(config):
            continue
        with open(path, encoding="utf-8", newline="") as fh:
            text = fh.read()
        with open(config, encoding="utf-8") as fh:
            series = json.load(fh)
        subjects = {k: v for k, v in series.get("subjects", {}).items() if isinstance(v, dict)}
        out.append((path, text, subjects))
    return out


def all_beats(result: dict) -> list[dict]:
    return [b for act in result["acts"] for b in act["beats"]]


def all_shots(result: dict) -> list[dict]:
    return [s for b in all_beats(result) for r in b["runs"] for s in r["shots"]]


class TestByteForByte(unittest.TestCase):
    def test_every_script_comes_back_exactly(self):
        paths = scripts()
        self.assertGreater(len(paths), 20)
        for path in paths:
            with self.subTest(path):
                with open(path, encoding="utf-8", newline="") as fh:
                    text = fh.read()
                self.assertEqual(B.text_of(B.read(text)), text)

    def test_odd_shapes(self):
        for text in ("", "\n", "no newline at end", "= ep01  T", "= ep01  T\r\n\r\n# sq01  a\r\n\r\n## sh010\r\nx\r\n",
                     "// beat: A", "\n\n// a note\n\n# sq01  a\n", "## sh010\n", "# \n", "##\n", "// beat:\n"):
            with self.subTest(repr(text)):
                self.assertEqual(B.text_of(B.read(text)), text)

    def test_hand_comments_and_blanks_stay_where_they_are(self):
        text = HEAD + "// a note\n\n# sq01  porch\n// under the header\n\n\n## sh010\n// dur: 5 (align)\nAction.\n\n// after it\n"
        self.assertEqual(B.text_of(B.read(text)), text)


class TestAgreesWithTheBuild(unittest.TestCase):
    def test_same_shots_in_the_same_order(self):
        checked = 0
        for path, text, subjects in valid_pairs():
            characters = {k for k, v in subjects.items() if v.get("kind") == "character"}
            try:
                ep = story.parse_script(text, set(subjects), characters)
            except (story.ScriptError, ValueError):
                continue
            checked += 1
            with self.subTest(path):
                theirs = [s for q in ep["sequences"] for s in q["shots"]]
                ours = all_shots(B.outline(B.read(text)))
                self.assertEqual([s["id"] for s in ours], [s["id"] for s in theirs])
                for mine, built in zip(ours, theirs):
                    self.assertEqual(mine["action"], built["action"], built["id"])
                    self.assertEqual(mine["seconds"], built.get("duration"), built["id"])
                    self.assertEqual(mine["lines"], len(built["dialogue"]), built["id"])
        self.assertGreaterEqual(checked, 3)  # examples and fixtures; more with tests/local

    def test_each_beat_starts_on_the_shot_the_score_says(self):
        for path, text, _subjects in valid_pairs():
            marks = SP.read_marks(text)["beats"]
            if not marks:
                continue
            with self.subTest(path):
                got = {b["runs"][0]["shots"][0]["id"]: b["beat"] for b in all_beats(B.outline(B.read(text)))
                       if b["beat"] and b["runs"] and b["runs"][0]["shots"]}
                self.assertEqual({k: v.replace(" (again)", "") for k, v in marks.items()}, got)


class TestOutline(unittest.TestCase):
    def outline(self, body: str) -> dict:
        return B.outline(B.read(HEAD + body))

    def test_the_episode(self):
        got = self.outline("")
        self.assertEqual((got["id"], got["title"]), ("ep01", "Draft"))
        self.assertEqual(got["shots"], 0)
        self.assertEqual(got["acts"], [])

    def test_a_beat_with_no_shots_is_still_on_the_board(self):
        got = self.outline("// structure: Three-Act\n// beat: Opening / Status Quo\n// beat: Debate\n")
        self.assertEqual([b["beat"] for b in all_beats(got)], ["Opening / Status Quo", "Debate"])
        self.assertTrue(all(b["runs"] == [] for b in all_beats(got)))

    def test_empty_sequences_stay_in_their_beats(self):
        got = self.outline("// structure: Three-Act\n// beat: Opening / Status Quo\n# sq01  porch\n\n// beat: Debate\n# sq02  street\n")
        beats = all_beats(got)
        self.assertEqual([r["sequence"] for r in beats[0]["runs"]], ["sq01"])
        self.assertEqual([r["sequence"] for r in beats[1]["runs"]], ["sq02"])

    def test_a_beat_under_a_header_owns_that_header(self):
        got = self.outline("# sq01  porch\n\n// beat: Debate\n" + SHOT.format(id="sh010"))
        beats = all_beats(got)
        self.assertEqual([b["beat"] for b in beats], ["Debate"])
        self.assertTrue(beats[0]["runs"][0]["opens"])
        self.assertEqual(beats[0]["runs"][0]["place"], "porch")

    def test_a_beat_can_start_inside_a_sequence(self):
        got = self.outline("// beat: A\n# sq01  porch\n\n" + SHOT.format(id="sh010") + "// beat: B\n" + SHOT.format(id="sh020"))
        beats = all_beats(got)
        self.assertTrue(beats[0]["runs"][0]["opens"])
        self.assertFalse(beats[1]["runs"][0]["opens"])
        self.assertEqual(beats[1]["runs"][0]["sequence"], "sq01")

    def test_a_beat_can_span_sequences(self):
        got = self.outline("// beat: A\n# sq01  a\n\n" + SHOT.format(id="sh010") + "# sq02  b\n\n" + SHOT.format(id="sh020"))
        self.assertEqual([r["place"] for r in all_beats(got)[0]["runs"]], ["a", "b"])

    def test_shots_before_any_beat(self):
        got = self.outline("# sq01  a\n\n" + SHOT.format(id="sh010"))
        beats = all_beats(got)
        self.assertEqual(len(beats), 1)
        self.assertIsNone(beats[0]["beat"])
        self.assertEqual(beats[0]["runs"][0]["shots"][0]["id"], "sh010")

    def test_acts_come_from_the_structure(self):
        got = self.outline("// structure: Three-Act\n// beat: Debate\n// beat: Midpoint\n// beat: Climax\n")
        self.assertEqual([(a["act"], a["own"]) for a in got["acts"]],
                         [("I: Setup", False), ("II: Confrontation", False), ("III: Resolution", False)])
        self.assertTrue(all_beats(got)[0]["guidance"])

    def test_the_structure_is_named_as_the_table_names_it(self):
        got = self.outline("// structure: Three-Act\n")
        self.assertEqual(got["structure"], "The Change Arc (Three-Act Structure)")
        self.assertTrue(got["structure_known"])

    def test_an_unknown_structure_is_shown_as_written(self):
        got = self.outline("// structure: My Shape\n// beat: One\n")
        self.assertEqual((got["structure"], got["structure_known"]), ("My Shape", False))
        self.assertFalse(all_beats(got)[0]["known"])

    def test_your_own_act(self):
        got = self.outline("// structure: Three-Act\n// beat: Debate\n// act: Interlude\n// beat: My Own Beat\n// beat: Another\n// beat: Climax\n")
        self.assertEqual([(a["act"], a["own"], len(a["beats"])) for a in got["acts"]],
                         [("I: Setup", False, 1), ("Interlude", True, 2), ("III: Resolution", False, 1)])

    def test_your_own_act_on_a_beat_the_structure_knows(self):
        got = self.outline("// structure: Three-Act\n// act: Mine\n// beat: Climax\n")
        self.assertEqual([(a["act"], a["own"]) for a in got["acts"]], [("Mine", True)])
        self.assertTrue(all_beats(got)[0]["known"])

    def test_a_repeated_beat_takes_the_tables_next(self):
        got = self.outline("// structure: Pixar Story Spine\n// beat: Because of that…\n// beat: Because of that…\n")
        beats = all_beats(got)
        self.assertEqual(beats[0]["guidance"], "The first consequence.")
        self.assertIn("next consequence", beats[1]["guidance"])

    def test_duration_forms(self):
        for written, seconds in (("22:00", 1320.0), ("90", 90.0), ("1:02:30", 3750.0), ("2.5", 2.5)):
            self.assertEqual(self.outline(f"// duration: {written}\n")["duration"], seconds, written)
        for written in ("soon", "", "0", "1:2:3:4", "-5"):
            self.assertIsNone(self.outline(f"// duration: {written}\n")["duration"], written)

    def test_seconds_add_up_and_untimed_are_counted(self):
        body = "# sq01  a\n\n" + SHOT.format(id="sh010") + "## sh020\ndur: auto\nJUNE: Hello.\n\n## sh030\nDoes a thing.\n"
        got = self.outline(body)
        self.assertEqual((got["shots"], got["seconds"], got["untimed"]), (3, 3.5, 2))


class TestShotView(unittest.TestCase):
    def view(self, body: str) -> dict:
        return all_shots(B.outline(B.read(HEAD + "# sq01  a\n\n" + body)))[0]

    def test_a_stand_in(self):
        got = self.view(SHOT.format(id="sh010"))
        self.assertTrue(got["held_empty"])
        self.assertEqual((got["who"], got["seconds"], got["action"]), (["june"], 3.5, "Something happens."))

    def test_a_card_with_a_picture_isnt_empty(self):
        self.assertFalse(self.view("## sh010\ntarget: hold\nfirst: cards/a.png\ndur: 2\nA card.\n")["held_empty"])

    def test_a_freeze_frame_isnt_empty(self):
        self.assertFalse(self.view("## sh010\ntarget: hold\ncontinuous: first\ndur: 2\nHeld.\n")["held_empty"])

    def test_a_shot_on_a_model_isnt_empty(self):
        self.assertFalse(self.view("## sh010\ndur: 2\nA shot.\n")["held_empty"])

    def test_a_line_makes_it_not_empty(self):
        self.assertFalse(self.view("## sh010\ntarget: hold\ndur: 2\nJUNE: Hello.\n")["held_empty"])

    def test_dur_auto_and_model(self):
        self.assertEqual(self.view("## sh010\ndur: auto\nJUNE: Hi.\n")["timing"], "auto")
        self.assertEqual(self.view("## sh010\ndur: model 3-8\nA thing.\n")["timing"], "model")

    def test_comments_arent_action(self):
        self.assertEqual(self.view("## sh010\n// dur: 5   (align)\ndur: 2\nReal action.\n")["action"], "Real action.")

    def test_a_note_above_a_shot_goes_with_it(self):
        doc = B.read(HEAD + "# sq01  a\n\n// theme: show, tender\n## sh010\ndur: 2\nX.\n")
        shot = next(b for b in doc["blocks"] if b["kind"] == "shot")
        self.assertEqual(shot["lines"][0], "// theme: show, tender\n")
        self.assertEqual(shot["shot"]["id"], "sh010")


if __name__ == "__main__":
    unittest.main()
