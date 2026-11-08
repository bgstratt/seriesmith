"""
The storyboard's routes on a real episode folder (seriesmith/api.py; docs/PLAN.md, the storyboard):
what they answer, what they write, and that a script changed underneath is refused.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from seriesmith import api as A  # noqa: E402
from seriesmith import source as S  # noqa: E402
from seriesmith.core import board as B  # noqa: E402

DRAFT = "= ep01  Draft\n"


class TestStoryboardRoutes(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        shows = os.path.join(self._tmp.name, "Shows")
        self.ep = os.path.join(shows, "ep01")
        shutil.copytree(os.path.join(ROOT, "examples", "starter"), self.ep)
        self.script = os.path.join(self.ep, "ep01.md")
        self.ctx = A.Context(os.path.join(self._tmp.name, "user"), "http://127.0.0.1:0", env={})
        self.assertEqual(A.put_config(self.ctx, {"roots": [shows]})[0], 200)

    def tearDown(self):
        self._tmp.cleanup()

    def blank(self, text: str = DRAFT) -> None:
        with open(self.script, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)

    def text(self) -> str:
        with open(self.script, encoding="utf-8", newline="") as fh:
            return fh.read()

    def board(self, **query) -> dict:
        code, data = A.get_storyboard(self.ctx, {"ep": self.ep, **query})
        self.assertEqual(code, 200, data)
        return data

    def edit(self, status: int = 200, **body) -> dict:
        base = body.pop("base_hash", None) or self.board()["hash"]
        code, data = A.post_storyboard_edit(self.ctx, {"ep": self.ep, "base_hash": base, **body})
        self.assertEqual(code, status, data)
        return data

    @staticmethod
    def rows(data: dict) -> list[dict]:
        return [b for a in data["plan"]["acts"] for b in a["beats"]]

    def test_reading_writes_nothing(self):
        before = self.text()
        self.board(structure="Three-Act", duration="180")
        self.assertEqual(self.text(), before)

    def test_targets_come_with_a_structure_and_a_duration(self):
        self.blank()
        data = self.board(structure="Three-Act", duration="180")
        self.assertEqual(len(self.rows(data)), 11)
        self.assertEqual(data["plan"]["target_shots"], 51)

    def test_no_structure_no_targets(self):
        self.blank()
        self.assertEqual(self.rows(self.board(duration="180")), [])

    def test_the_scripts_own_marks_are_used(self):
        self.blank(DRAFT + "// structure: Three-Act\n// duration: 3:00\n")
        self.assertEqual(self.board()["plan"]["target_shots"], 51)

    def test_add_on_a_blank_script(self):
        self.blank()
        data = self.edit(op="add", structure="Three-Act", duration="180", beat={"plain": "Debate", "nth": 0})
        self.assertEqual(len(data["made"]), 1)
        written = self.text()
        self.assertIn("// structure: Three-Act", written)
        self.assertIn("// duration: 3:00", written)
        self.assertIn("// beat: Debate", written)
        self.assertIn("# sq01  porch", written)
        self.assertIn("target: hold", written)
        self.assertEqual(data["check"].get("errors", []) if isinstance(data["check"], dict) else [], [])
        row = next(b for b in self.rows(data) if b["plain"] == "Debate")
        self.assertEqual((row["shots"], row["target_shots"]), (1, 4))

    def test_it_can_be_read_back_and_built(self):
        self.blank()
        self.edit(op="add", structure="Three-Act", duration="180", beat={"plain": "Debate", "nth": 0})
        self.assertEqual(self.board()["plan"]["structure_known"], True)
        self.assertTrue(os.path.isfile(os.path.join(self.ep, "shotlist", "shots.json")))

    def test_fill_brings_beats_up_to_target(self):
        self.blank()
        beats = [{"plain": "Opening / Status Quo", "nth": 0}, {"plain": "Debate", "nth": 0}]
        data = self.edit(op="fill", structure="Three-Act", duration="180", beats=beats)
        self.assertEqual(len(data["made"]), 5 + 4)
        self.assertEqual(self.edit(op="fill", structure="Three-Act", duration="180", beats=beats)["made"], [])

    def test_fill_keeps_structure_order_when_done_out_of_order(self):
        self.blank()
        self.edit(op="add", structure="Three-Act", duration="180", beat={"plain": "Climax", "nth": 0})
        self.edit(op="add", beat={"plain": "Debate", "nth": 0})
        names = [b["value"] for b in B.read(self.text())["blocks"] if b["kind"] == "beat"]
        self.assertEqual(names, ["Debate", "Climax"])

    def test_an_edit_keeps_what_was_there(self):
        before = self.text()
        self.edit(op="add", structure="Three-Act", duration="180", beat={"plain": "Debate", "nth": 0})
        kept = [line for line in before.splitlines() if line.strip()]
        after = self.text().splitlines()
        at = 0
        for line in after:
            if at < len(kept) and line == kept[at]:
                at += 1
        self.assertEqual(at, len(kept), "every original line, in order")

    def test_a_script_changed_underneath_is_refused(self):
        self.blank()
        stale = self.board()["hash"]
        self.blank(DRAFT + "// someone typed\n")
        code, _data = A.post_storyboard_edit(self.ctx, {"ep": self.ep, "base_hash": stale, "op": "add",
                                                        "structure": "Three-Act", "duration": "180",
                                                        "beat": {"plain": "Debate", "nth": 0}})
        self.assertEqual(code, 409)
        self.assertEqual(self.text(), DRAFT + "// someone typed\n")

    def test_the_old_script_goes_to_history(self):
        self.blank()
        self.edit(op="add", structure="Three-Act", duration="180", beat={"plain": "Debate", "nth": 0})
        self.assertTrue(S.history(self.ep, "ep01.md"))

    def test_place(self):
        self.blank(DRAFT + "\n# sq01  porch\n\n## sh010\ndur: 2\nA thing.\n")
        data = self.board()
        block = self.rows(data)[0]["runs"][0]["block"]
        locations = list(__import__("json").load(open(os.path.join(self.ep, "series.json"), encoding="utf-8"))["locations"])
        self.edit(op="place", block=block, place=locations[0])
        self.assertIn(f"# sq01  {locations[0]}", self.text())

    def test_a_place_not_in_the_series_is_refused(self):
        self.blank(DRAFT + "\n# sq01  porch\n\n## sh010\ndur: 2\nA thing.\n")
        self.edit(status=400, op="place", block=1, place="the_moon")

    def test_cast_only_on_stand_ins(self):
        self.blank(DRAFT + "\n# sq01  porch\n\n## sh010\ntarget: hold\ndur: 2\nStand.\n\n## sh020\ndur: 2\nReal.\n")
        block = self.rows(self.board())[0]["runs"][0]["block"]
        self.edit(op="cast", block=block, who=["ada"])
        self.assertIn("## sh010\nwho: ada\n", self.text())
        self.assertIn("## sh020\ndur: 2\n", self.text())

    def test_a_dropped_picture_means_it_is_not_empty(self):
        self.blank(DRAFT + "\n# sq01  porch\n\n## sh010\ntarget: hold\ndur: 2\nStand.\n")
        self.assertTrue(self.rows(self.board())[0]["runs"][0]["shots"][0]["held_empty"])
        folder = os.path.join(self.ep, "refs", "shots", "sh010")
        os.makedirs(folder)
        open(os.path.join(folder, "first.png"), "wb").close()
        self.assertFalse(self.rows(self.board())[0]["runs"][0]["shots"][0]["held_empty"])

    def test_bad_requests(self):
        self.blank()
        self.edit(status=400, op="nonsense")
        self.edit(status=400, op="add", beat={"plain": "", "nth": 0}, structure="Three-Act", duration="180")
        self.edit(status=400, op="fill", beats=[], structure="Three-Act", duration="180")
        self.edit(status=400, op="cast", block=0, who="ada")
        code, _data = A.post_storyboard_edit(self.ctx, {"ep": self.ep, "op": "add"})
        self.assertEqual(code, 400)

    def test_a_scripts_own_structure_beats_the_dropdown(self):
        self.blank(DRAFT + "// structure: Three-Act\n// duration: 3:00\n")
        data = self.board(structure="Fable", duration="180")
        self.assertEqual(data["plan"]["structure"], "The Change Arc (Three-Act Structure)")
        self.assertEqual(len(self.rows(data)), 11)

    def test_a_shows_own_format_has_no_targets_and_adds_no_beats(self):
        self.blank(DRAFT + "// structure: Porch Lights\n\n// beat: Cold Open\n# sq01  porch\n\n## sh010\ndur: 2\nA thing.\n")
        data = self.board(structure="Episodic Drama", duration="420")
        self.assertEqual([b["plain"] for b in self.rows(data)], ["Cold Open"])
        self.assertIsNone(data["plan"]["target_shots"])
        self.assertEqual(data["plan"]["structure"], "Porch Lights")

    def test_adding_to_a_shows_own_format_keeps_its_structure_line(self):
        self.blank(DRAFT + "// structure: Porch Lights\n\n// beat: Cold Open\n# sq01  porch\n\n## sh010\ndur: 2\nA thing.\n")
        self.edit(op="add", structure="Episodic Drama", duration="420", beat={"plain": "Cold Open", "nth": 0})
        written = self.text()
        self.assertEqual(written.count("// structure:"), 1)
        self.assertIn("// structure: Porch Lights", written)

    def test_one_held_shot_per_beat(self):
        self.blank()
        rows = self.rows(self.board(structure="Three-Act", duration="1320"))
        beats = [{"plain": b["plain"], "nth": b["nth"]} for b in rows]
        data = self.edit(op="fill", structure="Three-Act", duration="1320", beats=beats, each=1)
        self.assertEqual(len(data["made"]), 11)
        self.assertTrue(all(b["shots"] == 1 for b in self.rows(data)))
        names = [b["value"] for b in B.read(self.text())["blocks"] if b["kind"] == "beat"]
        self.assertEqual(names, [b["plain"] for b in rows])

    def test_each_must_be_a_count(self):
        self.blank()
        self.edit(status=400, op="fill", beats=[{"plain": "A", "nth": 0}], each=0)


if __name__ == "__main__":
    unittest.main()
