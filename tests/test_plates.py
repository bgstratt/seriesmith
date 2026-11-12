"""
Plate variants (docs/PLATE_VARIANTS.md): a crop is a location `of` another with `crop` and
`zoom`; its plate is the master's cut to that part and enlarged, made by seriesmith when missing
or out of date, and never over a picture of yours.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from seriesmith import plates as PL  # noqa: E402
from seriesmith.core import series_config as SC  # noqa: E402


def cfg(**alcove):
    return {"series": {"id": "t", "title": "T"}, "style": {"look": "a live-action drama"},
            "subjects": {"ada": {"kind": "character", "name": "Ada", "design": "a girl"}},
            "locations": {
                "alcove": {"description": "a vending alcove, two machines, a fountain",
                           "plate": "../refs/_bg/alcove.png"},
                "alcove_left": dict({"of": "alcove", "crop": "left"}, **alcove)}}


class ConfigTest(unittest.TestCase):
    def test_defaults(self):
        c = SC.series_config_from(cfg())
        e = c["locations"]["alcove_left"]
        self.assertEqual(e["plate"], "../refs/_bg/alcove_left.png")
        self.assertEqual(e["description"], "a vending alcove, two machines, a fountain")

    def test_its_own_win(self):
        e = SC.series_config_from(cfg(description="the drinks machine", plate="x/mine.png"))["locations"]["alcove_left"]
        self.assertEqual((e["description"], e["plate"]), ("the drinks machine", "x/mine.png"))

    def test_checked(self):
        for bad, why in [({"crop": "middle"}, "one of"), ({"zoom": 5}, "zoom"),
                         ({"zoom": True}, "zoom"), ({"relight": "dusk"}, "relight")]:
            with self.assertRaises(ValueError, msg=bad) as cm:
                SC.series_config_from(cfg(**bad))
            self.assertIn(why, str(cm.exception))

    def test_not_a_crop_of_a_crop(self):
        c = cfg()
        c["locations"]["alcove_far_left"] = {"of": "alcove_left", "crop": "left"}
        with self.assertRaises(ValueError):
            SC.series_config_from(c)

    def test_a_crop_of_an_angle(self):
        c = cfg()
        c["locations"]["alcove_back"] = {"of": "alcove", "description": "the other way",
                                         "plate": "../refs/_bg/back.png"}
        c["locations"]["alcove_back_right"] = {"of": "alcove_back", "crop": "right"}
        got = SC.series_config_from(c)
        self.assertEqual(SC.location_master(got, "alcove_back_right"), "alcove")


class BoxTest(unittest.TestCase):
    def test_parts(self):
        self.assertEqual(SC.crop_box(1600, 900, "center", 2), (400, 225, 1200, 675))
        self.assertEqual(SC.crop_box(1600, 900, "left", 2), (0, 225, 800, 675))
        self.assertEqual(SC.crop_box(1600, 900, "bottom-right", 2), (800, 450, 1600, 900))
        self.assertEqual(SC.crop_box(1600, 900, "top", 2), (400, 0, 1200, 450))

    def test_the_same_shape(self):
        l, t, r, b = SC.crop_box(1344, 768, "top-left")
        self.assertAlmostEqual((r - l) / (b - t), 1344 / 768, places=2)


class MakeTest(unittest.TestCase):
    def setUp(self):
        from PIL import Image
        self.tmp = tempfile.mkdtemp(prefix="plates-")
        self.ep = os.path.join(self.tmp, "show", "ep01")
        os.makedirs(self.ep)
        os.makedirs(os.path.join(self.tmp, "show", "refs", "_bg"))
        self.master = os.path.join(self.tmp, "show", "refs", "_bg", "alcove.png")
        im = Image.new("RGB", (160, 90), "white")
        for x in range(80):                      # the left half red
            for y in range(90):
                im.putpixel((x, y), (255, 0, 0))
        im.save(self.master)
        self.write(cfg())
        self.crop = os.path.join(self.tmp, "show", "refs", "_bg", "alcove_left.png")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, c):
        with open(os.path.join(self.ep, "series.json"), "w", encoding="utf-8") as fh:
            json.dump(c, fh)

    def status(self):
        return [(c["id"], c["status"]) for c in PL.make_crops(self.ep)]

    def test_made_then_current(self):
        from PIL import Image
        self.assertEqual(self.status(), [("alcove_left", "made")])
        with Image.open(self.crop) as im:
            self.assertEqual(im.size, (160, 90))
            self.assertEqual(im.getpixel((10, 45)), (255, 0, 0))   # the left part, closer
        self.assertEqual(self.status(), [("alcove_left", "current")])

    def test_made_again_when_the_master_changes(self):
        from PIL import Image
        self.status()
        Image.new("RGB", (160, 90), "blue").save(self.master)
        self.assertEqual(self.status(), [("alcove_left", "made")])

    def test_made_again_when_the_crop_changes(self):
        self.status()
        self.write(cfg(zoom=2.5))
        self.assertEqual(self.status(), [("alcove_left", "made")])

    def test_yours_is_kept(self):
        from PIL import Image
        self.status()
        Image.new("RGB", (160, 90), "green").save(self.crop)    # made by hand, or an edit
        self.write(cfg(zoom=2.5))
        self.assertEqual(self.status(), [("alcove_left", "yours")])
        with Image.open(self.crop) as im:
            self.assertEqual(im.getpixel((10, 10)), (0, 128, 0))

    def test_waiting_for_the_master(self):
        os.remove(self.master)
        got = PL.make_crops(self.ep)
        self.assertEqual(got[0]["status"], "waiting")
        self.assertFalse(os.path.exists(self.crop))

    def test_the_edit_instruction(self):
        from seriesmith import refs as R
        s = R.load_series(self.ep)
        ref = next(r for r in R.series_refs(s) if r.id == "location:alcove_left")
        got = R.built_prompt(s, ref, refs=[{"role": "plate", "path": self.master}])
        self.assertIn("left part of this place 1.6 times closer", got)

    def test_listed_as_a_crop(self):
        from seriesmith import refs as R
        s = R.load_series(self.ep)
        by = {r.id: r for r in R.series_refs(s)}
        got = R.ref_json(s, by["location:alcove_left"])
        self.assertEqual((got["of"], got["crop"], got["zoom"]), ("alcove", "left", 1.6))
        self.assertNotIn("crop", R.ref_json(s, by["location:alcove"]))


if __name__ == "__main__":
    unittest.main()
