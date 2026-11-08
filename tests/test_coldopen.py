"""
coldopen (docs/TITLES_GUIDE.md "A cold open"): the script's `cold_open:` marks read, in the
cut's order, into where the series intro goes; a gap refused; the marks written back from
the cut ("Cold open ends here") with a history copy, and the routes.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from seriesmith import api as A  # noqa: E402
from seriesmith import coldopen as CO  # noqa: E402
from seriesmith import edit as E  # noqa: E402
from seriesmith import source as H  # noqa: E402
from seriesmith import takes as T  # noqa: E402
from seriesmith.core import fileio as F  # noqa: E402
from seriesmith.core.story import ScriptError, parse_story  # noqa: E402

STARTER = os.path.join(os.path.dirname(HERE), "examples", "starter", "series.json")


def shot(sid: str, dur: int, extra: str = "") -> str:
    return f"## {sid}\nwho: ada\nsize: wide\ndur: {dur}\n{extra}Ada waits on the porch.\n"


def script(head1: str = "", sh020: str = "", sh030: str = "") -> str:
    return ("= ep01  First Light\n\n"
            f"# sq01  porch\n{head1}\n" + shot("sh010", 2) + "\n" + shot("sh020", 3, sh020) + "\n"
            "# sq02  porch\n\n" + shot("sh030", 2, sh030) + "\n" + shot("sh040", 2))


class Parse(unittest.TestCase):
    def test_header_and_shot(self):
        ep = parse_story(script("cold_open: true\n", "cold_open: false\n", "cold_open: yes\n"),
                         {"ada"}, {"ada"})
        flags = CO.flags(ep)
        self.assertEqual(flags, {"sh010": True, "sh020": False, "sh030": True, "sh040": False})
        # carried in the IR only when set
        d = ep.to_json()
        self.assertTrue(d["sequences"][0]["cold_open"])
        self.assertNotIn("cold_open", d["sequences"][1])
        self.assertNotIn("cold_open", d["sequences"][1]["shots"][1])
        with self.assertRaises(ScriptError):
            parse_story(script("cold_open: maybe\n"), {"ada"}, {"ada"})


class Episode(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.shows = os.path.join(self._tmp.name, "Shows")
        self.ep = os.path.join(self.shows, "ep01")
        os.makedirs(self.ep)
        shutil.copyfile(STARTER, os.path.join(self.ep, "series.json"))
        self.write(script())

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, text: str) -> None:
        F.write_text(os.path.join(self.ep, "ep01.md"), text)
        b = E.build_episode(self.ep)
        self.assertTrue(b["ok"], b)
        for sid, n in (("sh010", 48), ("sh020", 72), ("sh030", 48), ("sh040", 48)):
            if not T.list_takes(self.ep, "final", sid):
                t = T.reserve_take(self.ep, "final", sid, {"status": "queued"})
                open(t.paths.mp4, "wb").close()
                T.update_sidecar(t.paths.sidecar, status="ok", frames=n)

    def text(self) -> str:
        return H.read_source(self.ep, "script").text

    def test_none(self):
        st = CO.state(self.ep, "final")
        self.assertEqual((st["shots"], st["frame"], st["error"]), ([], None, None))

    def test_a_sequence_then_a_shot(self):
        self.write(script("cold_open: true\n"))
        st = CO.state(self.ep, "final")
        self.assertEqual((st["shots"], st["end"], st["frame"]), (["sh010", "sh020"], "sh020", 120))
        self.assertEqual(st["frames"], 48 + 72 + 48 + 48)
        self.assertAlmostEqual(st["seconds"], 5.0)

    def test_a_gap_is_refused(self):
        # sh030 marked, sh020 (between it and the cut's head) not
        self.write(script("cold_open: true\n", "cold_open: false\n", "cold_open: true\n"))
        st = CO.state(self.ep, "final")
        self.assertEqual((st["shots"], st["gaps"], st["frame"]), (["sh010"], ["sh030"], None))
        self.assertIn("Cold open ends here", st["error"])

    def test_ends_here_writes_the_marks(self):
        self.write(script("cold_open: true\n", "cold_open: false\n"))
        res = CO.set_end(self.ep, "final", "sh030")
        self.assertTrue(res["changed"])
        self.assertEqual(res["shots"], ["sh010", "sh020", "sh030"])
        text = self.text()
        # sq01 whole: its header; sh030 alone: its own line; one of each
        self.assertEqual(text.count("cold_open: true"), 2)
        self.assertIn("# sq01  porch\ncold_open: true\n", text)
        self.assertIn("dur: 2\ncold_open: true\nAda", text.split("## sh030")[1])
        self.assertTrue(H.history(self.ep, "ep01.md"))          # the old script kept
        E.build_episode(self.ep)
        st = CO.state(self.ep, "final")
        self.assertEqual((st["end"], st["frame"], st["error"]), ("sh030", 168, None))
        # nothing more to change
        self.assertFalse(CO.set_end(self.ep, "final", "sh030")["changed"])
        # none: every mark goes
        CO.set_end(self.ep, "final", None)
        self.assertNotIn("cold_open", self.text())
        with self.assertRaises(CO.ColdOpenError):
            CO.set_end(self.ep, "final", "sh999")

    def shots_txt(self, rows: list[tuple[str, int, int]]) -> str:
        """An assembled cut's shot list as assemble writes it: (shot, start frame, frames)."""
        path = os.path.join(self.ep, "renders", "ep01_shots.txt")
        lines = ["# ep01.mp4   4 shots   00:00:09.000   final pass",
                 "#           in  shot       take  frames  policy"]
        for sid, start, n in rows:
            s = start / 24
            lines.append(f"  00:00:{s:06.3f}  {sid:10} {1:>4} {n:>7}  generate")
        F.write_text(path, "\n".join(lines) + "\n")
        return path

    def test_the_break_is_read_from_the_file(self):
        # sh040's file is 3 frames shorter than its record: the break still lands on sh030's
        # first frame as the file has it, whatever the plan says of the shots after it
        self.write(script("cold_open: true\n"))
        path = self.shots_txt([("sh010", 0, 48), ("sh020", 48, 72), ("sh030", 120, 48),
                               ("sh040", 168, 45)])
        self.assertEqual(CO.split_in_file(self.ep, path, 24), 120)
        # a shot list in another order: the marked shots after an unmarked one are a gap
        gap = self.shots_txt([("sh010", 0, 48), ("sh030", 48, 48), ("sh020", 96, 72),
                              ("sh040", 168, 45)])
        with self.assertRaisesRegex(CO.ColdOpenError, "sh020 marked cold open"):
            CO.split_in_file(self.ep, gap, 24)
        # a dissolve across the break: sh030 starts before sh020 ends
        dis = self.shots_txt([("sh010", 0, 48), ("sh020", 48, 72), ("sh030", 108, 48),
                              ("sh040", 156, 45)])
        with self.assertRaisesRegex(CO.ColdOpenError, "dissolves"):
            CO.split_in_file(self.ep, dis, 24)
        with self.assertRaisesRegex(CO.ColdOpenError, "no shot list"):
            CO.split_in_file(self.ep, path + ".nope", 24)
        # no cold open: nothing to read
        self.write(script())
        self.assertIsNone(CO.split_in_file(self.ep, path + ".nope", 24))

    def test_routes(self):
        ctx = A.Context(os.path.join(self._tmp.name, "user"), "http://127.0.0.1:0", env={})
        code, _ = A.put_config(ctx, {"roots": [self.shows]})
        self.assertEqual(code, 200)
        code, st = A.get_cold_open(ctx, {"ep": self.ep, "pass": "final"})
        self.assertEqual((code, st["end"]), (200, None))
        code, st = A.put_cold_open(ctx, {"ep": self.ep, "pass": "final", "end": "sh020"})
        self.assertEqual((code, st["end"], st["frame"], st["changed"]), (200, "sh020", 120, True))
        self.assertTrue(st["build"]["ok"])
        code, _ = A.put_cold_open(ctx, {"ep": self.ep, "pass": "final", "end": "nope"})
        self.assertEqual(code, 400)
        code, _ = A.put_cold_open(ctx, {"ep": self.ep, "pass": "final", "end": 3})
        self.assertEqual(code, 400)


if __name__ == "__main__":
    unittest.main()
