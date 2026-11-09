"""
A prompt as a template over a shot's parts (targets/prompt_template.py; docs/PLAN.md step
15.2). That the default templates reproduce every prompt as it was is held by the goldens
(tests/golden/, tests/golden/router_calls/); this is the template itself and how a target's
own one reaches a shot and a request.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from seriesmith import jobs as J  # noqa: E402
from seriesmith import targets as TG  # noqa: E402
from seriesmith.core import fileio as F  # noqa: E402
from seriesmith.core import ir  # noqa: E402
from seriesmith.targets import prompt_template as TP  # noqa: E402
from test_render import FIXTURE, build_episode  # noqa: E402
from seriesmith.targets.generic import router_video as RV  # noqa: E402
from seriesmith.targets.video.ltx2 import prompt as LTX  # noqa: E402
from seriesmith.targets.video.wan import prompt as WAN  # noqa: E402


def target(**recipe):
    return types.SimpleNamespace(recipe=recipe)


class Render(unittest.TestCase):
    def test_parts_go_in(self):
        self.assertEqual(TP.render("{a} and {b}", {"a": "x", "b": "y"}), "x and y")

    def test_an_empty_part_leaves_no_gap(self):
        values = {"a": "A", "b": "", "c": "C"}
        self.assertEqual(TP.render("{a} {b} {c}", values), "A C")
        self.assertEqual(TP.render("{b} {a}", values), "A")
        self.assertEqual(TP.render("{a} {b}", values), "A")
        self.assertEqual(TP.render("{b} {b} {b}", values), "")

    def test_the_larger_space_stays(self):
        values = {"a": "A", "b": "", "c": "C"}
        self.assertEqual(TP.render("{a} {b}\n\n{c}", values), "A\n\nC")
        self.assertEqual(TP.render("{a}\n\n{b} {c}", values), "A\n\nC")
        self.assertEqual(TP.render("{a}\n\n{b}\n\n{c}", values), "A\n\nC")

    def test_a_section_goes_whole_when_a_part_in_it_is_empty(self):
        template = "{a} [[The sound is {b}.]] [[Music: {c}.]]"
        self.assertEqual(TP.render(template, {"a": "A", "b": "rain", "c": ""}), "A The sound is rain.")
        self.assertEqual(TP.render(template, {"a": "A", "b": "", "c": ""}), "A")

    def test_a_shots_words_are_never_template(self):
        said = "she types {b} and [[ then ]] {a}"
        self.assertEqual(TP.render("{a} [[{a}]]", {"a": said, "b": "NO"}), f"{said} {said}")

    def test_spaces_inside_a_value_are_kept(self):
        self.assertEqual(TP.render("{a} {b}", {"a": "two  spaces", "b": "x\n\ny"}), "two  spaces x\n\ny")

    def test_none_is_empty(self):
        self.assertEqual(TP.render("{a} {b}", {"a": "A", "b": None}), "A")

    def test_other_braces_are_only_words(self):
        self.assertEqual(TP.render("@Image {N} {a}", {"a": "A"}), "@Image {N} A")


class Problems(unittest.TestCase):
    def test_a_good_template(self):
        self.assertEqual(TP.problems("{a} [[x {b}]]", ["a", "b"]), [])

    def test_an_unknown_part_is_named_with_the_parts_there_are(self):
        (said,) = TP.problems("{a} {nope}", ["a", "b"])
        self.assertIn("nope", said)
        self.assertIn("a, b", said)
        with self.assertRaisesRegex(ValueError, "nope"):
            TP.render("{nope}", {"a": ""})

    def test_unmatched_and_nested_sections(self):
        self.assertTrue(TP.problems("[[ {a}", ["a"]))
        self.assertTrue(TP.problems("{a} ]]", ["a"]))
        self.assertTrue(TP.problems("[[ [[{a}]] ]]", ["a"]))


class Profiles(unittest.TestCase):
    def test_a_profile_is_found_or_nothing(self):
        self.assertEqual(TP.profile("prose")["writer"], "prose")
        self.assertEqual(TP.profile("fields"), {})
        self.assertEqual(TP.profile(None), {})

    def test_the_recipes_template_wins_over_its_profiles(self):
        self.assertEqual(TP.shot_template(target(prompt="prose")), TP.profile("prose")["template"])
        self.assertEqual(TP.shot_template(target(prompt="prose", prompt_template="{action}")), "{action}")
        self.assertEqual(TP.shot_template(target(prompt="fields")), "")

    def test_the_request_template(self):
        self.assertEqual(TP.request_template(target(prompt="prose")), TP.profile("prose")["request"])
        self.assertEqual(TP.request_template(target(prompt_request="{prompt}")), "{prompt}")
        self.assertEqual(TP.request_template(target()), TP.profile("prose")["request"])
        self.assertEqual(TP.request_template(target(), "image"), "{prompt} {mentions}")

    def test_every_template_shipped_uses_real_parts(self):
        for name, p in TP.profiles().items():
            self.assertEqual(TP.problems(p.get("template", ""), TP.PARTS), [], name)
            self.assertEqual(TP.problems(p.get("request", ""), TP.REQUEST_PARTS), [], name)


class Writers(unittest.TestCase):
    def setUp(self):
        self.shot = ir.Shot(id="sh010", size="medium", action="she waits", sound="rain",
                            music="a slow piano", cast=["ada"],
                            dialogue=[ir.Line(speaker="ada", line="Hello.")])
        self.seq = types.SimpleNamespace(location="kitchen")
        self.cfg = {"subjects": {"ada": {"name": "Ada", "design": "a tall woman"}},
                    "locations": {"kitchen": {"description": "a cramped kitchen"}},
                    "style": {"look": "flat vector"}}

    def test_both_writers_give_every_part(self):
        for writer in (LTX, WAN):
            self.assertEqual(set(writer.shot_parts(self.shot, self.seq, self.cfg)), set(TP.PARTS),
                             writer.__name__)

    def test_a_silent_writer_says_nothing_of_sound(self):
        parts = WAN.shot_parts(self.shot, self.seq, self.cfg)
        for name in ("sound", "music", "sound_words", "music_words", "spoken"):
            self.assertEqual(parts[name], "", name)

    def test_the_raw_parts_are_there_to_write_around(self):
        parts = LTX.shot_parts(self.shot, self.seq, self.cfg)
        self.assertEqual(parts["look"], "flat vector")
        self.assertEqual(parts["place"], "a cramped kitchen")
        self.assertEqual(parts["sound_words"], "rain")
        self.assertEqual(parts["music_words"], "a slow piano")
        self.assertEqual(parts["names"], "Ada")

    def test_a_template_of_ones_own(self):
        parts = LTX.shot_parts(self.shot, self.seq, self.cfg)
        self.assertEqual(TP.render("[[{look}, {size}.]] {action}", parts),
                         f"flat vector, {parts['size']}. She waits.")


class WhoSaysIt(unittest.TestCase):
    """"says" comes right before the words: told otherwise, a model gave a narrator's words to
    the character on screen (2026-11-04)."""
    CFG = {"subjects": {"dean": {"name": "Dean", "design": "a boy"},
                        "narrator": {"name": "The narrator", "voice": "warm"}},
           "locations": {"room": {"description": "a room"}}, "style": {"look": "flat"}}

    def lines(self, cast, *dialogue):
        shot = ir.Shot(id="sh010", size="medium", action="", cast=cast, dialogue=list(dialogue))
        return LTX.shot_parts(shot, types.SimpleNamespace(location="room"), self.CFG)["lines"]

    def test_a_narrator_over_someone_in_frame(self):
        got = self.lines(["dean"], ir.Line(speaker="narrator", line="Once upon a time.", mode="vo"))
        self.assertEqual(got, 'The narrator, in a voice that is warm, in an off-screen voiceover, says: '
                              '"Once upon a time."')

    def test_someone_in_frame_keeps_their_own_mouth_shut(self):
        got = self.lines(["dean"], ir.Line(speaker="dean", line="Always.", mode="vo"))
        self.assertEqual(got, 'Dean, in an off-screen voiceover, their lips staying closed, says: "Always."')

    def test_on_screen_the_delivery_comes_before_says_too(self):
        got = self.lines(["dean"], ir.Line(speaker="dean", line="Hi.", delivery="warmly"))
        self.assertEqual(got, 'Dean, warmly, says: "Hi."')
        self.assertEqual(self.lines(["dean"], ir.Line(speaker="dean", line="Hi.")), 'Dean says: "Hi."')


class RequestPrompt(unittest.TestCase):
    TEMPLATE = TP.profile("prose")["request"]

    def request(self, text, limit=None, **values):
        values = {"definitions": "", "voices": "", "mentions": "", **values}
        return TP.request_prompt(self.TEMPLATE, text, limit, RV.fit, **values)

    def test_with_nothing_to_add_it_is_the_text_as_it_was(self):
        self.assertEqual(self.request("  as written  "), "  as written  ")

    def test_each_in_its_place(self):
        self.assertEqual(self.request("P", definitions="D", voices="V", mentions="M"), "D\n\nV\n\nP\n\nM")
        self.assertEqual(self.request("P", voices="V"), "V\n\nP")
        self.assertEqual(self.request("P", mentions="M"), "P\n\nM")

    def test_the_whole_fits_the_limit(self):
        text = " ".join(f"Sentence number {i}." for i in range(40))
        out = self.request(text, limit=200, definitions="D" * 50, mentions="M" * 50)
        self.assertLessEqual(len(out), 200)
        self.assertTrue(out.startswith("D" * 50) and out.endswith("M" * 50))

    def test_the_room_is_what_the_old_sum_left(self):
        """limit - (head + 2) - (tail + 2), from when these were joined by hand."""
        seen = []

        def fit(text, most):
            seen.append(most)
            return text
        TP.request_prompt(self.TEMPLATE, "P", 1000, fit, definitions="D" * 10, voices="V" * 5, mentions="M" * 20)
        head = len("D" * 10 + "\n\n" + "V" * 5)
        self.assertEqual(seen, [1000 - (head + 2) - (20 + 2)])
        seen.clear()
        TP.request_prompt(self.TEMPLATE, "P", 1000, fit, definitions="", voices="", mentions="")
        self.assertEqual(seen, [1000])


class AShowsOwnModel(unittest.TestCase):
    """From a show's target.json to the request, as a render plans it: <show>/targets/<id>/,
    the shot retargeted to it and compiled again."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        build_episode(self.root)
        shutil.copy(os.path.join(FIXTURE, "series.json"), self.root)

    def plan(self, sid="sh010", **recipe):
        """The shot's job on a copy of Seedance 2.5 with `recipe` added."""
        with open(os.path.join(ROOT, "seriesmith", "targets", "video", "seedance_2_5", "target.json"),
                  encoding="utf-8") as fh:
            spec = json.load(fh)
        spec.update(id="my_seedance", draft=False)
        spec["recipe"].update(recipe)
        folder = os.path.join(self.root, "targets", "my_seedance")
        os.makedirs(folder, exist_ok=True)
        F.write_json(os.path.join(folder, "target.json"), spec)
        with TG.use_roots(self.root):
            doc, i = J.find_shot(self.root, "final", sid)
            return J.plan_job(self.root, "final", doc, i, J.RenderRequest(sid, target="my_seedance"), {})

    def request(self, sid="sh010", **recipe):
        """(the shot's prompt in its take's shotlist, the arguments sent)."""
        job = self.plan(sid, **recipe)
        self.assertEqual(job.error, "")
        with TG.use_roots(self.root):
            t = J.job_target(job)
            self.assertEqual(t.id, "my_seedance")
            _, args = t.module.router_call(t, job)
        return J._prompt_text(J.frozen_shotlist(job)["shots"][0]["prompt"]), args

    def sent(self, args) -> str:
        return next(c["text"] for c in args["content"] if c["type"] == "text")

    def test_the_default_is_what_seedance_itself_sends(self):
        with open(os.path.join(HERE, "golden", "router_calls", "seedance_2_5.json"), encoding="utf-8") as fh:
            pinned = json.load(fh)["sh010"]["arguments"]
        self.assertEqual(self.sent(self.request()[1]), self.sent(pinned))

    def test_a_template_changes_the_prompt_the_shotlist_and_the_request(self):
        prompt, args = self.request(prompt_template="[[Look: {look}.]] {action}")
        self.assertTrue(prompt.startswith("Look: "), prompt)
        self.assertNotIn("Style:", prompt)
        self.assertIn(prompt, self.sent(args))

    def test_a_request_template_moves_what_only_the_request_knows(self):
        args = self.request(prompt_request="{prompt}\n\n{definitions}")[1]
        text = self.sent(args)
        self.assertFalse(text.startswith("Define"), text)
        self.assertIn("\n\nDefine ", text)
        args = self.request(prompt_request="{prompt}")[1]
        self.assertNotIn("Define ", self.sent(args))

    def test_a_wrong_shot_template_stops_the_job_and_says_why(self):
        job = self.plan(prompt_template="{nope}")
        self.assertEqual(job.action, "error")
        self.assertIn("nope", job.error)

    def test_a_wrong_request_template_stops_the_call(self):
        with self.assertRaisesRegex(ValueError, "nope"):
            self.request(prompt_request="{prompt} {nope}")


if __name__ == "__main__":
    unittest.main()
