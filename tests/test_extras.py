"""
A shot's extras as people (core/extras.py), and the same people named in several shots: the
warning that they'd change from cut to cut, and should be a character or a group subject.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from seriesmith.core import extras as X  # noqa: E402


class RecurringTest(unittest.TestCase):
    def test_the_same_people_described_a_little_differently(self):
        shots = [
            ("sh010", "a skinny young man with a shaved head in a red store vest behind the register, soft"),
            ("sh020", "a skinny young man with a shaved head in a red store vest, ringing her up"),
            ("sh030", None),
            ("sh040", "a young mother asleep across two chairs with a toddler"),
            ("sh050", "a young mother asleep across two chairs far off in the room, soft"),
        ]
        got = X.recurring(shots)
        self.assertEqual([[s for s, _ in g] for g in got], [["sh010", "sh020"], ["sh040", "sh050"]])

    def test_different_people_are_not(self):
        shots = [("sh010", "a night nurse in teal scrubs passing behind him, blurred"),
                 ("sh020", "a night nurse in green scrubs walking away, blurred"),
                 ("sh030", "an old man in a flat cap at the bar")]
        self.assertEqual(X.recurring(shots), [])

    def test_crowds_too(self):
        """The same crowd described twice is meant to be the same people (Porchlights ep01's
        lunch table: certain people one shot, others the next)."""
        shots = [("sh010", "day-shift nurses walking past, soft"),
                 ("sh020", "day-shift nurses in colorful scrubs arriving with coffees, soft"),
                 ("sh030", "a few old diners at the far tables"),
                 ("sh040", "a few old diners at the far tables")]
        self.assertEqual([[s for s, _ in g] for g in X.recurring(shots)],
                         [["sh010", "sh020"], ["sh030", "sh040"]])

    def test_only_at_one_place(self):
        shots = [("sh010", "plant workers in hoodies walking", "lot"),
                 ("sh020", "plant workers in hoodies eating", "breakroom"),
                 ("sh030", "plant workers in hoodies at the tables", "breakroom")]
        self.assertEqual([[s for s, _ in g] for g in X.recurring(shots)], [["sh020", "sh030"]])

    def test_nobody_is_no_one(self):
        self.assertEqual(X.parts("nobody else in frame"), [])
        self.assertEqual(X.recurring([("sh010", "nobody else in frame"), ("sh020", "nobody else in frame")]), [])

    def test_the_phrase_is_who_not_where(self):
        self.assertEqual(X.who_phrase("a night nurse in teal scrubs passing in the corridor, blurred"),
                         "a night nurse in teal scrubs")
        self.assertEqual(X.who_phrase("a middle-aged woman in a housekeeping uniform being seated"),
                         "a middle-aged woman in a housekeeping uniform")
        self.assertEqual(X.who_phrase("day-shift nurses already walking ahead"), "day-shift nurses")

    def test_members_listed_after_a_colon(self):
        self.assertEqual(X.count("three plant workers: an older man with a grey mustache, a young "
                                 "woman in a grey hoodie, and a heavyset bald man, eating"), 3)

    def test_one_shot_twice_is_once(self):
        self.assertEqual(X.recurring([("sh010", "two guards in grey blazers; two guards in grey blazers")]), [])

    def test_a_group_matches_across_its_parts(self):
        shots = [("sh010", "two paramedics in dark uniforms at the rear doors, a young man on the stretcher"),
                 ("sh020", "two paramedics in dark uniforms with one stretcher and two night nurses")]
        (g,) = X.recurring(shots)
        self.assertEqual([s for s, _ in g], ["sh010", "sh020"])


class WarningTest(unittest.TestCase):
    def test_check_says_to_make_them_a_character_or_a_group(self):
        from seriesmith import build as BLD
        from seriesmith.core import ir

        def shot(sid, extras):
            return ir.Shot(id=sid, cast=["ada"], props=[], size="ms", extras=extras)
        story = ir.Episode(id="ep01", sequences=[ir.Sequence(id="sq01", location="yard", shots=[
            shot("sh010", "two guards in grey blazers at the gate"),
            shot("sh020", "two guards in grey blazers, soft"),
            shot("sh030", "an old man in a flat cap"),
            shot("sh040", "an old man in a flat cap by the bar"),
        ])])
        got = BLD.recurring_extras(story)
        self.assertEqual(len(got), 2)
        self.assertIn("sh010, sh020", got[0])
        self.assertIn('"two guards in grey blazers"', got[0])
        self.assertIn("members: 2", got[0])
        self.assertIn("a character with a sheet", got[1])


if __name__ == "__main__":
    unittest.main()
