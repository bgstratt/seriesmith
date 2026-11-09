"""
What the storyboard reads of each story structure (docs/PLAN.md, the storyboard): a beat's act,
guidance and place in the story, in structures.json from docs/STORY_STRUCTURES.md
(tools/make_structures.py).
"""
from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import make_structures as MS  # noqa: E402
from seriesmith.core import spotting as SP  # noqa: E402

TABLE = """\
### 9.1 Sample

**Beats:**

| Act | Beat | What happens | ~% |
|---|---|---|---|
| **I: Setup** | **Opening** | The *world* as it is. | 0–10 |
| | **Turn (Big)** | It breaks. | 10 |
| **II: End** | **Close** | It ends. | 10–100 |
| | **Coda** | No place. | — |

**Music:**

| Beat | Music | Mood (energy) | Theme | Hit |
|---|---|---|---|---|
| Opening | score | calm (2) | story, statement | — |
| Turn | score | sharp (3) | story, echo | turn |
| Close | score | settled (2) | story, statement | the end |
| Coda | dry | — | — | — |
"""


class TestOutlineFromTheDoc(unittest.TestCase):
    def setUp(self):
        self.beats = {b["beat"]: b for b in MS.build(TABLE)["structures"][0]["beats"]}

    def test_guidance_loses_its_emphasis(self):
        self.assertEqual(self.beats["Opening"]["guidance"], "The world as it is.")

    def test_an_empty_act_cell_is_the_act_above(self):
        self.assertEqual(self.beats["Opening"]["act"], "I: Setup")
        self.assertEqual(self.beats["Turn"]["act"], "I: Setup")
        self.assertEqual(self.beats["Close"]["act"], "II: End")

    def test_a_span_is_at_and_a_point_is_point(self):
        self.assertEqual(self.beats["Opening"]["at"], [0, 10])
        self.assertEqual(self.beats["Turn"]["point"], 10)
        self.assertNotIn("at", self.beats["Turn"])

    def test_no_place_is_neither(self):
        self.assertNotIn("at", self.beats["Coda"])
        self.assertNotIn("point", self.beats["Coda"])

    def test_a_numbered_table_has_no_acts(self):
        text = TABLE.replace("| Act | Beat", "| # | Beat").replace("**I: Setup**", "1").replace("**II: End**", "2")
        for beat in MS.build(text)["structures"][0]["beats"]:
            self.assertNotIn("act", beat)


class TestTheShippedStructures(unittest.TestCase):
    def test_every_structure_is_guided_and_placed(self):
        for st in SP.structures():
            for beat in st["beats"]:
                if beat["beat"] == "(And the moral is…)":  # the Spine's optional coda: named differently in its outline table
                    continue
                self.assertTrue(beat.get("guidance"), f"{st['name']}: {beat['beat']}")
                self.assertTrue("at" in beat or "point" in beat, f"{st['name']}: {beat['beat']}")

    def test_every_structure_has_its_rows(self):
        rows = {"1.1": 3, "1.2": 4, "1.3": 3, "2.1": 4, "2.2": 6, "2.3": 4, "2.4": 4, "3.1": 5, "3.2": 5,
                "3.3": 3, "4.1": 5, "4.2": 4, "4.3": 5, "5.1": 3}
        self.assertEqual({st["id"] for st in SP.structures()}, set(rows))
        for st in SP.structures():
            self.assertTrue(all(b.get("act") for b in st["beats"]), st["name"])
            self.assertEqual(len({b["act"] for b in st["beats"]}), rows[st["id"]], st["name"])

    def test_an_act_is_one_run_of_beats(self):
        for st in SP.structures():
            runs = [b["act"] for n, b in enumerate(st["beats"]) if n == 0 or b["act"] != st["beats"][n - 1]["act"]]
            self.assertEqual(len(runs), len(set(runs)), st["name"])

    def test_the_spines_moral_is_in_the_last_act(self):
        self.assertEqual(SP.structure("Pixar Story Spine")["beats"][-1]["act"], "The End")

    def test_a_script_that_says_build_up_still_scores(self):
        beats = SP.structure("In Medias Res")["beats"]
        self.assertIn("Build-Up", next(b for b in beats if b["beat"] == "The Calm / Build-Up")["names"])

    def test_three_act_is_three_acts_in_order(self):
        beats = SP.structure("Three-Act")["beats"]
        self.assertEqual(list(dict.fromkeys(b["act"] for b in beats)),
                         ["I: Setup", "II: Confrontation", "III: Resolution"])

    def test_a_point_beat_is_not_laid_out(self):
        """spotting.layout still places only the beats with a span: the score draft is unchanged."""
        st = SP.structure("Three-Act")
        shots = [{"id": f"sh{n:03d}", "t": n * 4.0, "d": 4.0, "seq": "sq01"} for n in range(40)]
        names = set(SP.layout(shots, st).values())
        self.assertNotIn("Midpoint", names)
        self.assertNotIn("Low Point", names)
        self.assertIn("Climax", names)


if __name__ == "__main__":
    unittest.main()
