"""
What a script's words ask of a model that the writer didn't mean
(seriesmith/core/wording.py), and the warnings the build gives for them
(build.wording_warnings): a thing named to forbid it, a person the action
names who isn't in `who:`, and words said in quotation marks in the action.
"""
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from seriesmith import build as B  # noqa: E402
from seriesmith.core import wording as W  # noqa: E402
from seriesmith.core.series_config import series_config_from  # noqa: E402
from test_checks import cfg, story  # noqa: E402


class NegationsTest(unittest.TestCase):
    def test_a_forbidden_thing_is_found(self):
        self.assertEqual(W.negations("No photographs appear on the wall."), ["No photographs"])
        self.assertEqual(W.negations("She never looks at the camera."), ["never looks at the camera"])
        self.assertEqual(W.negations("He walks out without a word."), ["without a word"])
        self.assertEqual(W.negations("He doesn't smile."), ["doesn't smile"])
        self.assertEqual(W.negations("Nobody."), ["Nobody"])

    def test_each_phrase_once_in_reading_order(self):
        self.assertEqual(W.negations("No dogs here. No cats. No dogs here."),
                         ["No dogs here", "No cats"])

    def test_what_forbids_nothing_is_quiet(self):
        for text in ("It lasts no more than a second.", "Not only rain but hail.",
                     "No doubt she runs.", "She runs, no matter what.", "Ada walks in.", ""):
            self.assertEqual(W.negations(text), [], text)

    def test_a_word_containing_no_is_quiet(self):
        self.assertEqual(W.negations("A notebook lies on the nightstand; she nods."), [])


class NamedAbsentTest(unittest.TestCase):
    PEOPLE = {"Ada": "ada", "Bo": "bo", "Will": "will"}

    def test_a_name_outside_who(self):
        self.assertEqual(W.named_absent("Ada turns to Bo.", self.PEOPLE, {"ada"}), ["Bo"])

    def test_in_who_is_quiet(self):
        self.assertEqual(W.named_absent("Ada turns to Bo.", self.PEOPLE, {"ada", "bo"}), [])

    def test_capitals_count_and_lowercase_words_dont(self):
        self.assertEqual(W.named_absent("BO bursts in.", self.PEOPLE, {"ada"}), ["Bo"])
        self.assertEqual(W.named_absent("She will go; a bow tie.", self.PEOPLE, {"ada"}), [])

    def test_a_place_named_after_them_is_quiet(self):
        self.assertEqual(W.named_absent("The sign of Bo Street flickers.", self.PEOPLE, {"ada"}), [])

    def test_a_possessive_is_them(self):
        self.assertEqual(W.named_absent("Bo's hand reaches in.", self.PEOPLE, {"ada"}), ["Bo"])


class QuotedSpeechTest(unittest.TestCase):
    def test_said_in_quotes(self):
        self.assertEqual(W.quoted_speech('Ada leans in and says, "Run."'), ["Run."])
        self.assertEqual(W.quoted_speech('"Get down," Bo whispers.'), ["Get down,"])
        self.assertEqual(W.quoted_speech("She shouts “Now!” at the door."), ["Now!"])

    def test_quotes_with_no_speaking_are_quiet(self):
        self.assertEqual(W.quoted_speech('A neon sign reads "OPEN ALL NIGHT".'), [])
        self.assertEqual(W.quoted_speech("Ada walks in."), [])


class WordingWarningsTest(unittest.TestCase):
    def warn(self, shot: str, who: str = "ada", c: dict | None = None) -> list[str]:
        c = series_config_from(c or cfg())
        st = story(f"= ep01 T\n\n# sq01 kitchen\n\n## sh010\nwho: {who}\ndur: 3\n{shot}\n", c)
        keys = ("names what it forbids", "not in its `who:` or `with:`", "said in quotation marks")
        return [w for w in B.story_warnings(st, c) if any(k in w for k in keys)]

    def test_a_negation_in_the_action(self):
        w = self.warn("Ada sets down her cup, never looking at the camera.")
        self.assertEqual(len(w), 1)
        self.assertTrue(w[0].startswith('sh010 action: "never looking at the camera"'), w[0])

    def test_a_negation_in_the_camera(self):
        w = self.warn("camera: no movement\nAda sets down her cup.")
        self.assertEqual(len(w), 1)
        self.assertTrue(w[0].startswith("sh010 camera:"), w[0])

    def test_a_person_named_outside_who(self):
        w = self.warn("Ada sets down her cup and looks at Bo.")
        self.assertEqual(len(w), 1)
        self.assertIn("names Bo, not in its `who:` or `with:`", w[0])
        self.assertEqual(self.warn("Ada sets down her cup and looks at Bo.", who="ada, bo"), [])

    def test_a_person_cast_in_with(self):
        # `with:` is cast too: a group or a character beside the principals
        self.assertEqual(self.warn("with: bo\nAda sets down her cup and looks at Bo."), [])

    def test_quoted_speech_in_the_action(self):
        w = self.warn('Ada sets down her cup and says, "Done."')
        self.assertEqual(len(w), 1)
        self.assertIn('"Done."', w[0])

    def test_the_series_configs_words(self):
        c = cfg(subjects__bo__voice="a boy's voice, never raised",
                locations__kitchen__description="a cramped diner kitchen with no windows")
        w = self.warn("Ada and Bo sit at the table.", who="ada, bo", c=c)
        self.assertEqual(sorted(x.split(":")[0] for x in w),
                         ["series.json locations.kitchen.description", "series.json subjects.bo.voice"])

    def test_a_subject_never_in_a_shot_is_described_freely(self):
        c = cfg(subjects__bo__design="a boy never seen on screen", subjects__bo__voice="never raised")
        self.assertEqual(self.warn("Ada sets down her cup.", c=c), [])

    def test_a_negation_ends_at_its_clause(self):
        self.assertEqual(W.negations("He walks without stopping and glances back."), ["without stopping"])

    def test_a_clean_shot_is_quiet(self):
        self.assertEqual(self.warn("Ada sets down her cup, her eyes on the window."), [])


if __name__ == "__main__":
    unittest.main()
