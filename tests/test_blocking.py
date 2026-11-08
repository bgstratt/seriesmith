"""
A story structure and a duration as shots per beat (seriesmith/core/blocking.py; docs/PLAN.md,
the storyboard).
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from seriesmith.core import blocking as B  # noqa: E402
from seriesmith.core import spotting as SP  # noqa: E402

MINUTES = (3, 7, 22, 100)


def beats_of(result: dict) -> list[dict]:
    return [b for act in result["acts"] for b in act["beats"]]


def beat(result: dict, name: str) -> dict:
    return next(b for b in beats_of(result) if b["beat"] == name)


class TestLengths(unittest.TestCase):
    def test_the_episode_comes_to_about_the_plans_counts(self):
        for minutes, shots in zip(MINUTES, (51, 120, 377, 1714)):
            self.assertEqual(B.block("Three-Act", minutes * 60.0)["shots"], shots, minutes)

    def test_the_inciting_incident_grows_with_the_episode(self):
        for minutes, low, high in ((3, 1, 1), (7, 2, 3), (22, 7, 8), (100, 34, 35)):
            shots = beat(B.block("Three-Act", minutes * 60.0), "Inciting Incident")["shots"]
            self.assertTrue(low <= shots <= high, f"{minutes} min: {shots}")

    def test_every_structure_adds_up_at_every_length(self):
        for st in SP.structures():
            for minutes in MINUTES:
                with self.subTest(st["name"], minutes=minutes):
                    r = B.block(st["name"].split(" (")[0], minutes * 60.0)
                    all_beats = beats_of(r)
                    self.assertEqual(sum(b["shots"] for b in all_beats), r["shots"])
                    self.assertAlmostEqual(sum(b["seconds"] for b in all_beats), minutes * 60.0, delta=0.5)
                    self.assertTrue(all(b["shots"] >= 1 for b in all_beats))

    def test_a_beats_share_of_the_shots_is_its_share_of_the_story(self):
        r = B.block("Three-Act", 22 * 60.0)
        rising, opening = beat(r, "Rising Complications"), beat(r, "Opening / Status Quo")
        self.assertAlmostEqual(rising["shots"] / opening["shots"], 2.5, delta=0.1)


class TestPointBeats(unittest.TestCase):
    def test_one_shot_on_a_short_two_on_a_long(self):
        self.assertEqual(beat(B.block("Three-Act", 180.0), "Midpoint")["shots"], 1)
        self.assertEqual(beat(B.block("Three-Act", 1320.0), "Midpoint")["shots"], 2)

    def test_it_keeps_its_percentage(self):
        self.assertEqual(beat(B.block("Three-Act", 180.0), "Low Point")["point"], 75)

    def test_a_beat_with_no_place_is_not_blocked(self):
        names = [b["beat"] for b in beats_of(B.block("Pixar Story Spine", 180.0))]
        self.assertNotIn("(And the moral is…)", names)


class TestOrder(unittest.TestCase):
    def test_first_shots_follow_on(self):
        at = 0
        for b in beats_of(B.block("Hero's Journey", 420.0)):
            self.assertEqual(b["first_shot"], at)
            at += b["shots"]

    def test_acts_are_the_structures_in_order(self):
        r = B.block("Hero's Journey", 420.0)
        self.assertEqual([a["act"] for a in r["acts"]], ["Departure", "Initiation", "Return"])
        for act in r["acts"]:
            self.assertEqual(act["shots"], sum(b["shots"] for b in act["beats"]))

    def test_guidance_comes_along(self):
        self.assertIn("status quo", beat(B.block("Three-Act", 180.0), "Inciting Incident")["guidance"])


class TestWarnings(unittest.TestCase):
    def test_a_thin_beat_is_flagged(self):
        r = B.block("Three-Act", 180.0)
        self.assertTrue(beat(r, "Inciting Incident")["thin"])
        self.assertFalse(beat(r, "Rising Complications")["thin"])
        self.assertTrue(any("Inciting Incident" in w for w in r["warnings"]))

    def test_a_long_episode_has_no_thin_beats(self):
        r = B.block("Three-Act", 6000.0)
        self.assertFalse(any(b["thin"] for b in beats_of(r)))
        self.assertEqual(r["warnings"], [])

    def test_too_many_beats_for_the_duration(self):
        r = B.block("Hero's Journey", 20.0)
        self.assertEqual(r["shots"], 12)
        self.assertGreater(r["shots"], r["wanted_shots"])
        self.assertIn("more beats", r["warnings"][0])
        self.assertAlmostEqual(sum(b["seconds"] for b in beats_of(r)), 20.0, delta=0.05)


class TestArguments(unittest.TestCase):
    def test_a_longer_typical_shot_means_fewer_shots(self):
        self.assertLess(B.block("Three-Act", 420.0, 6.0)["shots"], B.block("Three-Act", 420.0, 3.0)["shots"])

    def test_bad_numbers(self):
        for duration, shot in ((0, 3.5), (-5, 3.5), (60, 0), (True, 3.5), ("60", 3.5)):
            with self.assertRaises(B.BlockError):
                B.block("Three-Act", duration, shot)

    def test_an_unknown_structure(self):
        with self.assertRaises(B.BlockError):
            B.block("Nonsense Shape", 60.0)


if __name__ == "__main__":
    unittest.main()
