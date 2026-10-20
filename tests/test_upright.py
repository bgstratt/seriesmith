"""
A phone photo is stored sideways with an orientation tag saying how to show
it. ComfyUI's LoadImage turns it, so renders were right, but the editor's
thumbnails, a preset's tile and mksheet's sheets showed it on its side.
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

try:
    from PIL import Image
except ImportError:                                      # pragma: no cover
    Image = None


@unittest.skipIf(Image is None, "needs PIL")
class UprightTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.photo = os.path.join(self._tmp.name, "phone.jpg")
        ex = Image.Exif()
        ex[0x0112] = 6                                   # stored landscape: show it turned
        Image.new("RGB", (400, 200), (200, 30, 30)).save(self.photo, "JPEG", exif=ex)
        self.plain = os.path.join(self._tmp.name, "plain.png")
        Image.new("RGB", (400, 200), (30, 200, 30)).save(self.plain)

    def portrait(self, size):
        self.assertLess(size[0], size[1], size)

    def test_thumbnail(self):
        from seriesmith import api as A
        ctx = A.Context(self._tmp.name, env={})
        with Image.open(A.thumb_file(ctx, self.photo, 160)) as im:
            self.assertEqual(im.size, (160, 320))
        with Image.open(A.thumb_file(ctx, self.plain, 160)) as im:
            self.assertEqual(im.size, (160, 80))         # an untagged picture as it is

    def test_preset_tile(self):
        from seriesmith import preset_pictures as PP
        with Image.open(io.BytesIO(PP.shrink(self.photo))) as im:
            self.portrait(im.size)
        with Image.open(io.BytesIO(PP.shrink(self.plain, 100))) as im:
            self.assertEqual(im.size, (100, 50))

    def test_sheet_panels(self):
        from seriesmith import mksheet as M
        self.portrait(M.load_flat(self.photo, (255, 255, 255)).size)


if __name__ == "__main__":
    unittest.main(verbosity=2)
