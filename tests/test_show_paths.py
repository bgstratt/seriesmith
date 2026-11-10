"""core.paths.show_file: a path a show's own files name stays inside the show or a project
folder, so a show handed over by someone else can't make a render read, or upload, a file
elsewhere on the disk."""
import os
import tempfile
import unittest

from seriesmith import publish as PUB
from seriesmith import refs as R
from seriesmith.core import paths as P


def touch(path: str, text: str = "x") -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


class ShowFileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(P.set_project_roots, [])
        self.top = self.tmp.name
        self.show = os.path.join(self.top, "show")
        self.ep = os.path.join(self.show, "ep01")
        touch(os.path.join(self.ep, "series.json"), "{}")
        touch(os.path.join(self.ep, "ep01.md"), "= ep01\n")
        self.shared = touch(os.path.join(self.show, "refs", "ada.png"))
        self.private = touch(os.path.join(self.top, "private", "secret.txt"))

    def test_the_show_and_its_shared_folders(self):
        self.assertEqual(P.show_file(self.ep, "refs/x.png"), os.path.join(self.ep, "refs", "x.png"))
        self.assertEqual(P.show_file(self.ep, "../refs/ada.png"), self.shared)
        self.assertEqual(P.show_file(self.ep, self.shared), self.shared)

    def test_nothing_outside_it(self):
        for p in (self.private, "../../private/secret.txt", "..\\..\\private\\secret.txt", "a\x00b", ""):
            with self.subTest(p=p), self.assertRaises(P.OutsideShow):
                P.show_file(self.ep, p)

    def test_a_series_folder_is_the_show(self):
        """One series config for the show, the episodes under it: its paths start there."""
        top = os.path.join(self.top, "series")
        touch(os.path.join(top, "series.json"), "{}")
        touch(os.path.join(top, "ep01", "ep01.md"), "= ep01\n")
        self.assertEqual(P.show_folder(top), os.path.normpath(top))
        self.assertEqual(P.show_folder(os.path.join(top, "ep01")), os.path.normpath(top))
        with self.assertRaises(P.OutsideShow):
            P.show_file(top, "../show/refs/ada.png")

    def test_an_episode_before_its_script(self):
        ep = os.path.join(self.show, "ep02")
        touch(os.path.join(ep, "series.json"), "{}")
        self.assertEqual(P.show_file(ep, "../refs/ada.png"), self.shared)

    def test_a_project_folder(self):
        P.set_project_roots([os.path.dirname(self.private)])
        self.assertEqual(P.show_file(self.ep, self.private), self.private)

    @unittest.skipUnless(hasattr(os, "symlink"), "no symlinks")
    def test_a_link_out(self):
        link = os.path.join(self.ep, "refs", "out.txt")
        os.makedirs(os.path.dirname(link), exist_ok=True)
        try:
            os.symlink(self.private, link)
        except OSError:
            self.skipTest("this account can't make symlinks")
        with self.assertRaises(P.OutsideShow):
            P.show_file(self.ep, "refs/out.txt")

    def test_a_ref(self):
        self.assertEqual(R.ref_file(self.ep, "../refs/ada.png"), self.shared)
        with self.assertRaises(P.OutsideShow):
            R.ref_file(self.ep, self.private)

    def test_a_font(self):
        """A title font may be the show's or one of this machine's; nothing else."""
        mine = touch(os.path.join(self.show, "fonts", "Title.ttf"))
        self.assertEqual(PUB.find_font(mine, self.ep), mine)
        with self.assertRaises(P.OutsideShow):
            PUB.find_font(self.private, self.ep)
        dirs = PUB.font_dirs()
        if dirs:
            sys_fonts = [os.path.join(dirs[0], f) for f in os.listdir(dirs[0])
                         if os.path.isfile(os.path.join(dirs[0], f))]
            if sys_fonts:
                self.assertEqual(PUB.find_font(sys_fonts[0], self.ep), sys_fonts[0])


if __name__ == "__main__":
    unittest.main()
