"""
A shot flagged to come back to (cut.json `"flag": true`): a bookmark for a
re-render or a new prompt. It changes nothing the cut plays or assembles; a
locked entry takes one; reset and copying the other pass keep each pass's own.
Set by PUT /seriesmith/cut (the editor's M key), `seriesmith cut --flag / --unflag`.
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from test_phase9b import Base  # noqa: E402  (first: it sets the import paths)
from seriesmith import edit as E  # noqa: E402
from seriesmith import takes as T  # noqa: E402


class CutFlagTest(Base):
    def cli(self, *argv, code=0, pass_="proxy"):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            got = E.COMMANDS["cut"](self.ep, (["--proxy"] if pass_ == "proxy" else []) + list(argv))
        self.assertEqual(got, code, buf.getvalue())
        return buf.getvalue()

    def entry(self, shot, pass_="proxy"):
        return next((e for e in T.load_cut(self.ep).get(pass_, []) if e["shot"] == shot), None)

    def test_flag_and_unflag(self):
        a, b = self.order[:2]
        out = self.cli("--flag", b)
        self.assertIn("FLAGGED", out)
        self.assertEqual(self.entry(b), {"shot": b, "flag": True})
        _, shots = self.status()
        self.assertTrue(shots[b]["cut"]["flag"])
        self.assertFalse(shots[a]["cut"]["flag"])
        self.assertFalse(shots[b]["cut"]["out"])                 # still played
        self.cli("--unflag", b)
        self.assertEqual(self.entry(b), {"shot": b})

    def test_a_locked_entry_takes_one(self):
        b = self.order[1]
        self.cli("--lock", b)
        self.cli("--flag", b)
        self.assertEqual(self.entry(b), {"shot": b, "locked": True, "flag": True})

    def test_route(self):
        b = self.order[1]
        self.put_cut([{"shot": b, "flag": True}])
        self.assertTrue(self.entry(b)["flag"])
        self.put_cut([{"shot": b, "flag": "yes"}], status=400)
        self.put_cut([{"shot": b, "flag": False}])
        self.assertNotIn("flag", self.entry(b))

    def test_reset_and_copy_keep_each_pass_own(self):
        a, b = self.order[:2]
        E.set_cut_entry(self.ep, "proxy", b, flag=True)
        E.move_shot(self.ep, "proxy", b, a, after=False)
        E.reset_cut(self.ep, "proxy", "all")
        self.assertTrue(self.entry(b)["flag"])
        E.copy_cut(self.ep, "proxy", "final", "all")
        self.assertNotIn("flag", self.entry(b, "final") or {})


class FaceMarkTest(CutFlagTest):
    """A shot marked for the face pass (cut.json `"refine_faces": true`, the editor's R
    key, `seriesmith cut --mark-faces / --unmark-faces`): kept as a flag is, and its own."""

    def test_mark_and_unmark(self):
        a, b = self.order[:2]
        out = self.cli("--mark-faces", b)
        self.assertIn("REFINE FACES", out)
        self.assertEqual(self.entry(b), {"shot": b, "refine_faces": True})
        _, shots = self.status()
        self.assertTrue(shots[b]["cut"]["refine_faces"])
        self.assertFalse(shots[a]["cut"]["refine_faces"])
        self.assertFalse(shots[b]["cut"]["flag"])               # not a flag
        self.assertFalse(shots[b]["cut"]["out"])                # still played
        self.cli("--flag", b)
        self.assertEqual(self.entry(b), {"shot": b, "flag": True, "refine_faces": True})
        out = self.cli("--unmark-faces", b)                    # kept out: a mark too
        self.assertEqual(self.entry(b), {"shot": b, "flag": True, "refine_faces": False})
        self.assertIn("NO FACES", out)
        _, shots = self.status()
        self.assertIs(shots[b]["cut"]["refine_faces"], False)
        self.assertIs(shots[a]["cut"]["refine_faces"], None)
        self.assertIs(shots[b]["cut"]["faces_default"], False)
        self.cli("--clear-faces", b)                            # back to the series'
        self.assertEqual(self.entry(b), {"shot": b, "flag": True})

    def test_mark_route(self):
        b = self.order[1]
        self.put_cut([{"shot": b, "refine_faces": True}])
        self.assertTrue(self.entry(b)["refine_faces"])
        self.put_cut([{"shot": b, "refine_faces": 1}], status=400)
        self.put_cut([{"shot": b, "refine_faces": False}])
        self.assertIs(self.entry(b)["refine_faces"], False)
        self.put_cut([{"shot": b, "refine_faces": None}])
        self.assertNotIn("refine_faces", self.entry(b))

    def test_mark_kept_by_reset_and_lock(self):
        a, b = self.order[:2]
        self.cli("--lock", b)
        E.set_cut_entry(self.ep, "proxy", b, refine_faces=True)    # a locked entry takes one
        self.assertEqual(self.entry(b), {"shot": b, "locked": True, "refine_faces": True})
        self.cli("--unlock", b)
        E.move_shot(self.ep, "proxy", b, a, after=False)
        E.reset_cut(self.ep, "proxy", "all")
        self.assertEqual(self.entry(b), {"shot": b, "refine_faces": True})
        E.copy_cut(self.ep, "proxy", "final", "all")
        self.assertNotIn("refine_faces", self.entry(b, "final") or {})


if __name__ == "__main__":
    unittest.main()
