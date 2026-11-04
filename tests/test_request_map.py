"""
The hosted request's seams (docs/PLAN.md step 15.1): one check for a hosted model, one
reader of its block, and the mapping's functions shared by video, image and sound. What the
requests contain is pinned elsewhere (test_router_golden.py, tests/golden/router_calls/).
"""
from __future__ import annotations

import os
import re
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from seriesmith import cue as CU  # noqa: E402
from seriesmith import targets as TG  # noqa: E402
from seriesmith.targets.generic import request_map as M  # noqa: E402


class TheOneCheck(unittest.TestCase):
    def test_is_hosted(self):
        self.assertTrue(TG.is_hosted({"router": {"model": "a/b"}}))
        self.assertFalse(TG.is_hosted({"binding": {}}))
        self.assertFalse(TG.is_hosted({"router": None}))

    def test_an_empty_block_is_still_hosted_so_validation_can_say_whats_missing(self):
        self.assertTrue(TG.is_hosted({"router": {}}))

    def test_hosted_block(self):
        self.assertEqual(TG.hosted_block({"router": {"model": "a/b"}}), {"model": "a/b"})
        self.assertEqual(TG.hosted_block({}), {})
        self.assertEqual(TG.hosted_block({"router": "not a block"}), {})

    def test_nothing_else_looks_for_the_block_by_name(self):
        """A new place a model can be hosted is then added in one place. limits writes into
        the block; the dry run's route takes a Router target's target.json by name."""
        allowed = {os.path.join("targets", "__init__.py"), "limits.py"}
        found = []
        top = os.path.join(ROOT, "seriesmith")
        for folder, _, files in os.walk(top):
            for name in files:
                path = os.path.join(folder, name)
                rel = os.path.relpath(path, top)
                if not name.endswith(".py") or rel in allowed:
                    continue
                with open(path, encoding="utf-8") as fh:
                    for line in fh:
                        if (re.search(r'spec(\.get\("router"\)|\["router"\])', line)
                                and "a Router target's, by name" not in line):
                            found.append(f"{rel}: {line.strip()}")
        self.assertEqual(found, [])


class Mapping(unittest.TestCase):
    def test_a_seed_folds_into_the_models_range(self):
        args = {}
        M.put_seed(args, {"name": "seed", "max": 9}, 25, 100)
        self.assertEqual(args, {"seed": 5})
        M.put_seed(args, {"name": "parameters.seed"}, 150, 99)
        self.assertEqual(args["parameters"], {"seed": 50})

    def test_a_cue_is_never_asked_for_less_than_it_needs(self):
        self.assertEqual(M.ceil_seconds(30.2, {"min": 10, "max": 360}), 31)
        self.assertEqual(M.ceil_seconds(4.0, {"min": 10, "max": 360}), 10)
        self.assertEqual(M.ceil_seconds(999, {"min": 10, "max": 360}), 360)

    def test_max_chars(self):
        self.assertEqual(M.max_chars({"field": "prompt", "max_chars": 1000}), 1000)
        self.assertIsNone(M.max_chars("prompt"))

    def test_a_wide_picture_is_never_sent_as_a_tall_one(self):
        """By plain difference, anything from square to 1.17 wide came out 9:16 (Veo's list)."""
        for w in (1001, 1100, 1170, 1280):
            self.assertEqual(M.nearest_ratio(w, 1000, ["16:9", "9:16"]), "16:9", w)
            self.assertEqual(M.nearest_ratio(1000, w, ["16:9", "9:16"]), "9:16", w)

    def test_a_tie_goes_to_the_ratio_listed_first(self):
        self.assertEqual(M.nearest_ratio(1024, 1024, ["16:9", "9:16"]), "16:9")
        self.assertEqual(M.nearest_ratio(1024, 1024, ["9:16", "16:9"]), "9:16")
        self.assertEqual(M.nearest_ratio(1440, 1080, ["16:9", "9:16", "1:1"]), "16:9")
        self.assertEqual(M.nearest_ratio(1440, 1080, ["1:1", "16:9"]), "1:1")

    def test_a_decimal_ratio_can_be_read(self):
        self.assertEqual(M.nearest_ratio(2350, 1000, ["16:9", "2.35:1", "auto"]), "2.35:1")

    def test_video_and_image_use_the_same_rule(self):
        from seriesmith.targets.generic import router_image, router_video
        self.assertIs(router_video.nearest_ratio, M.nearest_ratio)
        self.assertIs(router_image.nearest_ratio, M.nearest_ratio)


class HostedSound(unittest.TestCase):
    def call(self, inputs, values=None, seed=7):
        target = types.SimpleNamespace(spec={"router": {"model": "a/b", "arguments": {"mode": "x"},
                                                        "inputs": inputs}})
        return CU.hosted_call(target, {"prompt": {"prompt": "words", "values": values or {}}}, seed)

    def test_the_fields_named(self):
        model, args = self.call({"prompt": "prompt", "lyrics": "lyrics",
                                 "seconds": {"name": "duration", "min": 10, "max": 360},
                                 "seed": {"name": "seed", "max": 5}},
                                {"lyrics": "la", "seconds": 30.2})
        self.assertEqual(model, "a/b")
        self.assertEqual(args, {"mode": "x", "prompt": "words", "lyrics": "la", "duration": 31, "seed": 1})

    def test_empty_lyrics_are_left_out(self):
        _, args = self.call({"prompt": "prompt", "lyrics": "lyrics"}, {"lyrics": "  "})
        self.assertNotIn("lyrics", args)

    def test_a_prompt_can_go_anywhere_a_video_models_can(self):
        _, args = self.call({"prompt": {"list": "content", "item": {"type": "text", "text": "$prompt"}}})
        self.assertEqual(args["content"], [{"type": "text", "text": "words"}])


if __name__ == "__main__":
    unittest.main()
