"""
A sequence relight (seriesmith/relight.py, POST /seriesmith/refs/relight): each
plate a sequence uses gets a relit location (`of:` + `relight:`), generated as
an edit of the source's plate, and the sequence can be pointed at them.
"""
from __future__ import annotations

import json
import os
import random
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from seriesmith import api as A  # noqa: E402
from seriesmith import refs as R  # noqa: E402
from seriesmith import relight as RL  # noqa: E402
from seriesmith.core.series_config import location_master, series_config_from  # noqa: E402
import test_api  # noqa: E402
from test_api import ApiTest  # noqa: E402
from test_location_angles import cfg  # noqa: E402
from test_render import png_bytes  # noqa: E402


def tearDownModule():
    test_api.tearDownModule()


class ConfigTest(unittest.TestCase):
    def test_a_relit_location(self):
        c = series_config_from(cfg(bay_drive={"of": "bay", "description": "from the drive"},
                                   bay_drive_dusk={"of": "bay_drive", "relight": "dusk",
                                                   "description": "d"}))
        self.assertEqual(location_master(c, "bay_drive_dusk"), "bay")

    def test_what_is_refused(self):
        for locs, why in (({"x": {"relight": "dusk", "description": "d"}}, "no `of`"),
                          ({"x": {"of": "bay", "relight": "", "description": "d"}}, "as text"),
                          ({"x": {"of": "bay", "relight": "dusk", "description": "d"},
                            "y": {"of": "x", "relight": "night", "description": "d"}},
                           "itself relit")):
            with self.subTest(locs=locs), self.assertRaisesRegex(ValueError, why):
                series_config_from(cfg(**locs))

    def test_the_wording(self):
        self.assertTrue(RL.instruction("dawn").startswith("Change only the time of day"))
        self.assertEqual(RL.instruction(" make it rain "), "make it rain")
        self.assertTrue(RL.light_note("dawn").startswith("It is dawn, "))
        self.assertEqual(RL.light_note("make it rain"), "Make it rain.")
        self.assertEqual((RL.default_suffix("dawn"), RL.default_suffix("make it rain")),
                         ("dawn", "relit"))


class RelightApiTest(ApiTest):
    def setUp(self):
        super().setUp()
        s = R.load_series(self.ep)
        for lid in ("street", "kitchen_window"):
            p = os.path.join(self.tmp, f"{lid}.png")
            with open(p, "wb") as fh:
                fh.write(png_bytes(64, 36))
            ref = R.find_ref(s, f"location:{lid}")
            R.pick_take(s, ref, None, R.import_take(s, ref, None, p).take)

    def relight(self, **kw):
        return A.post_refs_relight(self.ctx, dict({"ep": self.ep}, **kw))

    def series(self):
        with open(os.path.join(self.ep, "series.json"), encoding="utf-8") as fh:
            return json.load(fh)

    def test_a_sequence_and_its_plates(self):
        self.assertEqual(RL.sequence_locations(self.ep, "sq02"), ["street", "kitchen_window"])
        data = self.ok(self.relight(sequence="sq02", relight="dusk", dry_run=True))
        self.assertEqual([(x["source"], x["id"]) for x in data["locations"]],
                         [("street", "street_dusk"), ("kitchen_window", "kitchen_window_dusk")])
        self.assertNotIn("street_dusk", self.series()["locations"])      # a dry run writes nothing

    def test_relight_and_repoint(self):
        data = self.ok(self.relight(sequence="sq02", relight="dusk", target="flux2_klein_edit",
                                    repoint=True))
        self.assertEqual(data["errors"], [])
        self.assertEqual(sorted(q["ref"] for q in data["queued"]),
                         ["location:kitchen_window_dusk", "location:street_dusk"])
        locs = self.series()["locations"]
        self.assertEqual(list(locs).index("street_dusk"), list(locs).index("street") + 1)
        e = locs["street_dusk"]
        self.assertEqual((e["of"], e["relight"], e["plate"]),
                         ("street", "dusk", "refs/_bg/street_dusk.png"))
        self.assertIn("It is dusk", e["description"])
        self.assertEqual(data["repointed"][0], "sq02")
        story = R.episode_story(self.ep)
        sq = next(q for q in story.sequences if q.id == "sq02")
        self.assertEqual(sq.location, "street_dusk")
        self.assertEqual({sh.plate for sh in sq.shots}, {"street_dusk", "kitchen_window_dusk"})
        # the same again reuses them
        again = self.ok(self.relight(sequence="sq02", relight="dusk", dry_run=True))
        self.assertTrue(all(x["exists"] for x in again["locations"]))
        # and another light starts from the original plates, not the dusk ones
        night = self.ok(self.relight(sequence="sq02", relight="night", repoint=True,
                                     target="flux2_klein_edit"))
        self.assertEqual([(x["source"], x["id"]) for x in night["locations"]],
                         [("street", "street_night"), ("kitchen_window", "kitchen_window_night")])
        sq = next(q for q in R.episode_story(self.ep).sequences if q.id == "sq02")
        self.assertEqual(sq.location, "street_night")

    def test_the_edit_starts_from_the_source_plate(self):
        self.ok(self.relight(locations=["street"], relight="make it snow", dry_run=False,
                             target="flux2_klein_edit"))
        s = R.load_series(self.ep)
        job = R.plan_generate(s, R.GenRequest("location:street_relit", target="flux2_klein_edit"),
                              rng=random.Random(0))[0]
        self.assertEqual([r["location"] for r in job.references], ["street"])
        self.assertTrue(job.prompt.startswith("Edit the "), job.prompt)
        self.assertIn("make it snow", job.prompt)

    def test_refused(self):
        self.err(self.relight(relight="dusk"), 400)                       # neither
        self.err(self.relight(sequence="sq02", locations=["street"], relight="dusk"), 400)
        self.err(self.relight(sequence="sq99", relight="dusk"), 400)
        self.err(self.relight(sequence="sq02"), 400)                      # no relight
        self.err(self.relight(locations=["street"], relight="dusk", repoint=True), 400)
        os.remove(R.find_ref(R.load_series(self.ep), "location:kitchen").file)
        self.err(self.relight(locations=["kitchen"], relight="dusk"), 400)  # no plate yet
        self.err(self.relight(locations=["street"], relight="dusk", suffix="a b"), 400)


if __name__ == "__main__":
    unittest.main()


class OwnRelightApiTest(RelightApiTest):
    """A relight of yours, saved from the edit window with its picture, then
    used for a sequence relight."""

    def test_saved_with_its_picture_and_used(self):
        from unittest import mock
        with mock.patch.dict(os.environ, {"SERIESMITH_SETTINGS": os.path.join(self.tmp, "settings.json")}):
            p = self.ok(A.post_preset_own(self.ctx, {
                "kind": "relight", "label": "Amber memory", "place": "Change only the light: an amber haze",
                "picture": {"ep": self.ep, "ref": "location:street"}}))
            self.assertEqual(p["images"], {"place": "own/relight/amber_memory.jpg"})
            data = self.ok(self.relight(locations=["street"], relight="amber_memory", dry_run=True))
            self.assertEqual(data["locations"][0]["id"], "street_amber_memory")
            self.assertIn("An amber haze.", data["locations"][0]["entry"]["description"])
            self.err(A.post_preset_own(self.ctx, {"kind": "relight", "label": "x", "place": "p",
                                                  "picture": {"ep": self.ep, "ref": "location:nowhere"}}), 404)

    # the parent's tests needn't run twice
    test_a_sequence_and_its_plates = test_relight_and_repoint = None
    test_the_edit_starts_from_the_source_plate = test_refused = None
