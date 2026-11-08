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

    def test_change_the_structure_keeps_every_beat(self):
        self.blank(DRAFT + "// structure: Porch Lights\n\n// beat: Cold Open\n# sq01  porch\n\n## sh010\ndur: 2\nA.\n\n// beat: Climax\n## sh020\ndur: 2\nB.\n")
        data = self.edit(op="structure", name="Three-Act", duration="180")
        self.assertIn("// structure: Three-Act", self.text())
        self.assertNotIn("Porch Lights", self.text())
        rows = self.rows(data)
        cold = next(b for b in rows if b["plain"] == "Cold Open")
        climax = next(b for b in rows if b["plain"] == "Climax")
        self.assertEqual((cold["known"], cold["target_shots"], cold["shots"]), (False, None, 1))
        self.assertEqual((climax["known"], climax["target_shots"], climax["shots"]), (True, 7, 1))
        self.assertEqual(len(rows), 12)
        self.assertEqual(len(self.edit(op="structure", name="Porch Lights", duration="180")["plan"]["acts"]), 1)

    def test_rename_a_beat(self):
        self.blank(DRAFT + "// beat: Old Name\n# sq01  porch\n\n## sh010\ndur: 2\nA.\n")
        block = self.rows(self.board())[0]["block"]
        self.edit(op="rename_beat", block=block, name="New Name")
        self.assertIn("// beat: New Name\n", self.text())
        self.assertNotIn("Old Name", self.text())

    def test_bad_renames(self):
        self.blank(DRAFT + "\n// beat: A\n# sq01  porch\n\n## sh010\ndur: 2\nA.\n")
        row = self.rows(self.board())[0]
        self.edit(status=400, op="rename_beat", block=row["runs"][0]["block"], name="x")
        self.edit(status=400, op="rename_beat", block=row["block"], name="  ")
        self.edit(status=400, op="structure", name="")
        self.edit(status=400, op="rename_sequence", block=row["runs"][0]["block"], name="sq09")

    SCRIPT = DRAFT + "\n// beat: A\n# sq01  porch\n\n## sh010\nwho: ada\ndur: 2\nA.\n\n## sh020\ndur: 2\nB.\n\n// beat: B\n# sq02  porch\n\n## sh030\ndur: 2\nC.\n"

    def shots(self) -> list[str]:
        return [b["shot"]["id"] for b in B.read(self.text())["blocks"] if b["kind"] == "shot"]

    def shot_block(self, sid: str) -> int:
        return next(i for i, b in enumerate(B.read(self.text())["blocks"]) if b["kind"] == "shot" and b["shot"]["id"] == sid)

    def beat_block(self, name: str) -> int:
        return next(i for i, b in enumerate(B.read(self.text())["blocks"]) if b["kind"] == "beat" and b["value"] == name)

    def test_add_a_shot_after_a_shot(self):
        self.blank(self.SCRIPT)
        made = self.edit(op="add_after", block=self.shot_block("sh010"))["made"]
        self.assertEqual(self.shots(), ["sh010", made[0], "sh020", "sh030"])
        self.assertIn(f"## {made[0]}\ntarget: hold\nwho: ada\n", self.text())

    def test_delete_a_shot(self):
        self.blank(self.SCRIPT)
        self.edit(op="delete_shot", block=self.shot_block("sh020"))
        self.assertEqual(self.shots(), ["sh010", "sh030"])

    def test_delete_needs_a_shot(self):
        self.blank(self.SCRIPT)
        self.edit(status=400, op="delete_shot", block=self.beat_block("A"))

    def test_a_new_sequence_after_a_sequences_last_shot(self):
        self.blank(self.SCRIPT)
        made = self.edit(op="add_sequence", block=self.shot_block("sh020"), place="porch")["made"]
        self.assertIn("# sq03  porch", self.text())
        self.assertEqual(self.shots(), ["sh010", "sh020", made[0], "sh030"])

    def test_no_new_sequence_in_the_middle_of_one(self):
        self.blank(self.SCRIPT)
        self.edit(status=400, op="add_sequence", block=self.shot_block("sh010"), place="porch")

    def test_add_a_beat_after_a_beat(self):
        self.blank(self.SCRIPT)
        self.edit(op="add_beat", beat={"plain": "A", "nth": 0}, name="Mine")
        names = [b["value"] for b in B.read(self.text())["blocks"] if b["kind"] == "beat"]
        self.assertEqual(names, ["A", "Mine", "B"])

    def test_add_an_act(self):
        self.blank(self.SCRIPT)
        data = self.edit(op="add_beat", beat={"plain": "A", "nth": 0}, name="New beat", act="Interlude")
        self.assertIn("// act: Interlude\n// beat: New beat\n", self.text())
        self.assertIn("Interlude", [a["act"] for a in data["plan"]["acts"]])

    def test_remove_a_beat_keeps_its_shots(self):
        self.blank(self.SCRIPT)
        self.edit(op="remove_beat", block=self.beat_block("B"))
        self.assertNotIn("// beat: B", self.text())
        self.assertEqual(self.shots(), ["sh010", "sh020", "sh030"])

    def test_rename_and_remove_your_own_act(self):
        self.blank(DRAFT + "\n// act: Mine\n// beat: A\n")
        self.edit(op="rename_act", block=self.beat_block("A"), name="Yours")
        self.assertIn("// act: Yours\n", self.text())
        self.edit(op="remove_act", block=self.beat_block("A"))
        self.assertNotIn("// act:", self.text())
        self.assertIn("// beat: A", self.text())

    def test_the_structures_acts_cant_be_changed(self):
        self.blank(self.SCRIPT)
        self.edit(status=400, op="rename_act", block=self.beat_block("A"), name="X")
        self.edit(status=400, op="remove_act", block=self.beat_block("A"))

    def test_add_a_beat_after_one_the_script_hasnt_got_yet(self):
        self.blank()
        self.edit(op="add_beat", structure="Three-Act", duration="180", beat={"plain": "Debate", "nth": 0}, name="Mine")
        names = [b["value"] for b in B.read(self.text())["blocks"] if b["kind"] == "beat"]
        self.assertEqual(names, ["Debate", "Mine"])

    def test_every_edit_can_be_undone_by_saving_the_old_text(self):
        self.blank(self.SCRIPT)
        before = self.text()
        self.edit(op="delete_shot", block=self.shot_block("sh020"))
        code, _data = A.put_source(self.ctx, {"ep": self.ep, "file": "script", "text": before, "base_hash": self.board()["hash"]})
        self.assertEqual(code, 200)
        self.assertEqual(self.text(), before)

    PLAIN = DRAFT + "\n# sq01  porch\n\n" + "".join(f"## sh{n:03d}\ndur: 4\nThing {n}.\n\n" for n in range(10, 410, 10))

    def test_lay_a_structure_over_a_script_with_no_beats(self):
        self.blank(self.PLAIN)
        data = self.edit(op="lay_out", name="Three-Act", duration="160")
        written = self.text()
        self.assertIn("// structure: Three-Act", written)
        beats = [b for b in B.read(written)["blocks"] if b["kind"] == "beat"]
        self.assertGreater(len(beats), 5)
        self.assertEqual([b["shot"]["id"] for b in B.read(written)["blocks"] if b["kind"] == "shot"],
                         [f"sh{n:03d}" for n in range(10, 410, 10)])
        counted = sum(b["shots"] for b in self.rows(data))
        self.assertEqual(counted, 40)
        self.assertIsNone(next((b for b in self.rows(data) if b["plain"] is None and b["shots"]), None))

    def test_laying_out_only_adds_comments(self):
        self.blank(self.PLAIN)
        self.edit(op="lay_out", name="Three-Act", duration="160")
        kept = [ln for ln in self.text().splitlines() if not ln.startswith("//")]
        self.assertEqual([ln for ln in kept if ln.strip()], [ln for ln in self.PLAIN.splitlines() if ln.strip()])

    def test_a_beat_that_starts_a_sequence_goes_above_its_header(self):
        self.blank(self.PLAIN)
        self.edit(op="lay_out", name="Three-Act", duration="160")
        lines = self.text().splitlines()
        self.assertTrue(lines[lines.index("# sq01  porch") - 1].startswith("// beat:"))

    def test_laying_out_is_refused_once_there_are_beats(self):
        self.blank(self.SCRIPT)
        self.edit(status=400, op="lay_out", name="Three-Act")

    def test_laying_out_needs_shots_and_a_real_structure(self):
        self.blank()
        self.edit(status=400, op="lay_out", name="Three-Act")
        self.blank(self.PLAIN)
        self.edit(status=400, op="lay_out", name="Nonsense Shape")

    def test_a_new_episode_can_start_with_no_shots(self):
        parent = os.path.dirname(self.ep)
        series = open(os.path.join(self.ep, "series.json"), encoding="utf-8").read()
        script = "= ep09  Blocked\n\n// structure: Three-Act\n// duration: 3:00\n"
        code, res = A.post_episode_new(self.ctx, {"parent": parent, "name": "ep09", "template": "form", "series": series, "script": script})
        self.assertEqual(code, 200, res)
        self.assertTrue(res["check"]["ok"], res["check"])
        code, data = A.get_storyboard(self.ctx, {"ep": res["ep"]})
        self.assertEqual(code, 200, data)
        self.assertEqual((data["plan"]["shots"], data["plan"]["target_shots"]), (0, 51))
        code, done = A.post_storyboard_edit(self.ctx, {"ep": res["ep"], "base_hash": data["hash"], "op": "fill", "each": 1,
                                                        "beats": [{"plain": "Debate", "nth": 0}]})
        self.assertEqual(code, 200, done)
        self.assertEqual(len(done["made"]), 1)

    def test_a_stand_in_takes_a_picture_as_its_first_frame(self):
        self.blank(DRAFT + "\n# sq01  porch\n\n## sh010\ntarget: hold\ndur: 2\nStand.\n")
        self.assertEqual(A.post_build(self.ctx, {"ep": self.ep})[0], 200)
        from PIL import Image
        png = os.path.join(self._tmp.name, "frame.png")
        Image.new("RGB", (64, 36), (200, 40, 40)).save(png)
        code, data = A.post_refs_import(self.ctx, {"ep": self.ep, "ref": "shot:sh010:first", "source_path": png, "pick": True})
        self.assertEqual(code, 200, data)
        shot = self.rows(self.board())[0]["runs"][0]["shots"][0]
        self.assertFalse(shot["held_empty"])
        self.assertEqual(shot["picture"], "refs/shots/sh010/first.png")
        self.assertTrue(shot["picture_version"])

    def test_a_shot_without_a_picture_says_so(self):
        self.blank(DRAFT + "\n# sq01  porch\n\n## sh010\ntarget: hold\ndur: 2\nStand.\n")
        self.assertIsNone(self.rows(self.board())[0]["runs"][0]["shots"][0]["picture"])

    def first_png(self, sid: str) -> str:
        return os.path.join(self.ep, "refs", "shots", sid, "first.png")

    def test_a_stand_in_holds_the_gray_card(self):
        self.blank()
        made = self.edit(op="add", structure="Three-Act", duration="180", beat={"plain": "Debate", "nth": 0})["made"]
        with open(self.first_png(made[0]), "rb") as fh:
            self.assertEqual(fh.read(), B.gray_card())
        self.assertNotIn("first:", self.text())
        held = next(b for b in self.rows(self.board(structure="Three-Act", duration="180")) if b["plain"] == "Debate")["runs"][0]["shots"][0]
        self.assertTrue(held["held_empty"])
        self.assertTrue(held["card"])
        self.assertIsNone(held["picture"])

    def test_the_gray_card_is_a_picture_the_hold_can_use(self):
        self.blank()
        made = self.edit(op="add", structure="Three-Act", duration="180", beat={"plain": "Debate", "nth": 0})["made"]
        with open(os.path.join(self.ep, "shotlist", "shotlist.hold.json"), encoding="utf-8") as fh:
            entry = __import__("json").load(fh)["shots"][0]
        self.assertEqual(os.path.normpath(os.path.join(self.ep, entry["keyframes"]["first"])), os.path.normpath(self.first_png(made[0])))
        from seriesmith import finish as F
        from seriesmith import hold as H
        out = os.path.join(self._tmp.name, "held.mp4")
        H.encode(self.first_png(made[0]), out, 12, 24.0, (640, 360))
        self.assertEqual(F.probe(out)["frames"], 12)

    def test_a_real_picture_replaces_the_card_and_it_stops_being_empty(self):
        self.blank()
        made = self.edit(op="add", structure="Three-Act", duration="180", beat={"plain": "Debate", "nth": 0})["made"]
        from PIL import Image
        png = os.path.join(self._tmp.name, "frame.png")
        Image.new("RGB", (64, 36), (200, 40, 40)).save(png)
        code, data = A.post_refs_import(self.ctx, {"ep": self.ep, "ref": f"shot:{made[0]}:first", "source_path": png, "pick": True})
        self.assertEqual(code, 200, data)
        held = next(b for b in self.rows(self.board(structure="Three-Act", duration="180")) if b["plain"] == "Debate")["runs"][0]["shots"][0]
        self.assertFalse(held["held_empty"])
        self.assertFalse(held["card"])
        self.assertEqual(held["picture"], f"refs/shots/{made[0]}/first.png")

    def test_a_new_stand_in_never_overwrites_a_picture_already_there(self):
        self.blank()
        os.makedirs(os.path.dirname(self.first_png("sh010")))
        with open(self.first_png("sh010"), "wb") as fh:
            fh.write(b"mine")
        self.edit(op="add", structure="Three-Act", duration="180", beat={"plain": "Debate", "nth": 0})
        with open(self.first_png("sh010"), "rb") as fh:
            self.assertEqual(fh.read(), b"mine")


if __name__ == "__main__":
    unittest.main()
