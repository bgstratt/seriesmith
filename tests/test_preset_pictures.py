"""
Pictures for your own presets (seriesmith/preset_pictures.py,
POST /seriesmith/presets/own/picture and /own/render): from your work, a
picture of yours, or rendered on the sample scene, each only when asked.
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from seriesmith import api as A  # noqa: E402
from seriesmith import preset_pictures as PP  # noqa: E402
from seriesmith import presets as PR  # noqa: E402
from seriesmith import refs as R  # noqa: E402
import test_api  # noqa: E402
from test_api import ApiTest  # noqa: E402
from test_render import png_bytes  # noqa: E402


def tearDownModule():
    test_api.tearDownModule()


class PictureTest(ApiTest):
    def setUp(self):
        super().setUp()
        env = mock.patch.dict(os.environ, {"SERIESMITH_SETTINGS": os.path.join(self.tmp, "cfg", "settings.json")})
        env.start()
        self.addCleanup(env.stop)
        PR.save_own("look", "Mine", {"text": "a look of mine"})
        PR.save_own("relight", "Glow", {"place": "Change only the light: a green glow"})
        self.png = os.path.join(self.tmp, "pic.png")
        with open(self.png, "wb") as fh:
            fh.write(png_bytes(960, 540))

    def tile(self, kind, pid):
        p = next(x for x in PR.listing(kind) if x["id"] == pid)
        return p.get("image") or (p.get("images") or {}).get("place")

    def test_a_picture_of_yours(self):
        self.assertIsNone(self.tile("look", "mine"))
        PP.from_file("look", "mine", self.png)
        name = self.tile("look", "mine")
        from PIL import Image
        with Image.open(PR.image_path(name)) as im:
            self.assertEqual(im.size, (480, 270))                 # shrunk to a tile

    def test_from_your_work(self):
        s = R.load_series(self.ep)
        ref = R.find_ref(s, "location:street")
        R.pick_take(s, ref, None, R.import_take(s, ref, None, self.png).take)
        p = self.ok(A.post_preset_own_picture(self.ctx, {"kind": "relight", "id": "glow",
                                                        "from": {"ep": self.ep, "ref": "location:street"}}))
        self.assertTrue(p["images"]["place"].startswith("own/relight/glow.jpg"))
        # a frame of a shot's take
        with mock.patch.object(PP.T, "get_take") as gt, mock.patch.object(PP.R, "extract_frame_at") as ex:
            gt.return_value = mock.Mock(has_video=True, paths=mock.Mock(mp4="x.mp4"))
            ex.side_effect = lambda mp4, sec, out: __import__("shutil").copyfile(self.png, out)
            self.ok(A.post_preset_own_picture(self.ctx, {"kind": "look", "id": "mine", "from": {
                "ep": self.ep, "pass": "proxy", "shot": "sh010", "take": 1, "time": 1.5}}))
            self.assertEqual(ex.call_args[0][1], 1.5)
        self.assertTrue(self.tile("look", "mine"))

    def test_refused(self):
        self.err(A.post_preset_own_picture(self.ctx, {"kind": "look", "id": "nope", "from": {}}), 400)
        self.err(A.post_preset_own_picture(self.ctx, {"kind": "look", "id": "mine"}), 400)
        self.err(A.post_preset_own_render(self.ctx, {"kind": "look", "id": "mine"}), 400)     # no model
        self.err(A.post_preset_own_render(self.ctx, {"kind": "relight", "id": "glow",
                                                     "target": "krea2"}), 400)              # not an edit model

    def test_rendered_on_the_sample_scene(self):
        req = PP.request("look", "mine", "krea2")
        self.assertEqual((req.ref, req.prompt), ("location:porch", f"a look of mine. {PR.LOOK_SCENE}"))
        req = PP.request("relight", "glow", "flux2_klein_edit")
        self.assertEqual((req.ref, req.edit["take"]), ("location:porch", 1))     # the base, not the live one
        self.ok(A.post_preset_own_render(self.ctx, {"kind": "look", "id": "mine", "target": "krea2"}))
        self.settle()
        data = self.ok(A.get_presets(self.ctx, {"kind": "look"}))      # finished: the tile
        mine = next(x for x in data["look"] if x["id"] == "mine")
        self.assertNotIn("rendering", mine)
        self.assertTrue(mine["image"].startswith("own/look/mine.jpg"))


if __name__ == "__main__":
    unittest.main()
