"""
core/abc.py: ABC read for a song's plan (YuE2's and SheetSage2's, tests/fixtures/abc/:
three YuE2 plans from docs/SOUND.md "Measured: YuE2" and a SheetSage2 melody transcription of
one of its songs), the note lengths counted, the tempo set as the yue2 graph sets it.
"""
from __future__ import annotations

import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from seriesmith.core import abc as A  # noqa: E402

FIX = os.path.join(HERE, "fixtures", "abc")


def fixture(name: str) -> str:
    with open(os.path.join(FIX, name), encoding="utf-8") as fh:
        return fh.read()


def song(body: str, meter="4/4", unit="1/8", q="1/4=120") -> str:
    return f"X:1\nM:{meter}\nL:{unit}\nQ:{q}\nV: A\nK:C\n{body}\n"


class ReadTest(unittest.TestCase):
    def test_a_yue2_plan(self):
        d = A.read(fixture("yue2_s1.abc"))
        self.assertEqual((d["meter"], d["unit"], d["tempo"], d["tempo_unit"], d["key"]),
                         ("2/4", "1/32", 93.0, "1/4", "D"))
        self.assertEqual(d["voices"], ["Vocal", "Ins"])
        self.assertEqual(d["melody"], "Vocal")
        self.assertEqual([(s["name"], s["bars"]) for s in d["sections"]],
                         [("intro", 9), ("verse", 16), ("chorus", 25), ("verse", 16),
                          ("chorus", 17), ("outro", 18)])
        # 2/4: two beats a bar; each section starts where the last ended
        for s in d["sections"]:
            self.assertEqual(s["beats"], 2 * s["bars"])
        for a, b in zip(d["sections"], d["sections"][1:]):
            self.assertEqual(b["start"], a["start"] + a["beats"])
        self.assertEqual((d["bars"], d["beats"]), (101, 202.0))
        # its first sung note: bar 9's second beat (z8 in 1/32 is a quarter)
        self.assertEqual(d["first_note"], 17.0)

    def test_four_four_and_another_key(self):
        d = A.read(fixture("yue2_s3.abc"))
        self.assertEqual((d["meter"], d["key"], d["tempo"]), ("4/4", "Eb", 94.0))
        self.assertEqual([s["name"] for s in d["sections"]],
                         ["intro", "verse", "chorus", "interlude", "verse", "chorus", "outro"])
        self.assertEqual(d["sections"][0]["bars"], 9)
        self.assertEqual(d["sections"][0]["beats"], 36.0)
        self.assertEqual(d["first_note"], 33.0)

    def test_sheetsage_melody(self):
        """SheetSage2's melody transcription: the same form, no chord symbols, Z4 rests."""
        d = A.read(fixture("sheetsage2_melody.abc"))
        self.assertEqual((d["tempo"], d["meter"]), (96.0, "2/4"))
        self.assertEqual(d["sections"][0], {"name": "intro", "start": 0.0, "beats": 18.0, "bars": 9})
        self.assertEqual(d["first_note"], 17.0)

    def test_note_lengths(self):
        # L:1/8 in 4/4: a bar is 8 units. A2 B/2 c/ d3/2 ... each bar counted to its beats
        d = A.read(song("A2 B/2c/ d3/2 e//f//g/ z2 g/ | [CEG]4 \"Am\"A2 x2 |"))
        self.assertEqual(d["beats"], 8.0)
        self.assertEqual(d["bars"], 2)

    def test_pickup_tie_and_part_bar(self):
        # a pickup (one eighth), a held note tied over the bar line, a last bar left open
        d = A.read(song("e | a4- a4 | a8- | a4"))
        self.assertEqual(d["beats"], 0.5 + 4 + 4 + 2)
        self.assertEqual(d["bars"], 4)                    # the pickup, two bars, the part bar
        self.assertEqual(d["first_note"], 0.0)

    def test_multibar_rests_and_tuplets(self):
        d = A.read(song("Z4 | (3abc d2 z4 |"))
        self.assertEqual(d["bars"], 5)
        self.assertEqual(d["beats"], 16 + 1 + 1 + 2)      # a triplet of eighths is a quarter
        self.assertEqual(d["first_note"], 16.0)

    def test_repeats_counted_twice(self):
        d = A.read(song("|: a8 | b8 :| c8 |"))
        self.assertEqual(d["bars"], 5)
        self.assertEqual(d["beats"], 20.0)

    def test_sections_take_their_longest_voice(self):
        text = ("X:1\nM:4/4\nL:1/4\nQ:1/4=100\nV: Vox\nV: Ins\nK:C\n% intro\nV: Vox\nZ|\nV: Ins\nc4|d4|\n"
                "% verse\nV: Vox\nc4|d4|e4|\nV: Ins\nZ3|\n")
        d = A.read(text)
        self.assertEqual([(s["name"], s["bars"], s["start"]) for s in d["sections"]],
                         [("intro", 2, 0.0), ("verse", 3, 8.0)])
        self.assertEqual(d["first_note"], 8.0)             # the melody voice (the first declared)

    def test_times(self):
        d = A.read(fixture("yue2_s1.abc"))
        t = A.times(d, 96)
        self.assertEqual(t[1]["start"], round(18 * 60 / 96, 3))
        self.assertEqual(t[1]["seconds"], 20.0)


class EditTest(unittest.TestCase):
    def test_set_tempo_as_the_graph_does(self):
        text = fixture("yue2_s1.abc")
        out = A.set_tempo(text, 96)
        self.assertEqual(re.findall(r"^Q:.*$", out, re.M), ["Q:1/4=96"])
        self.assertIn("L:1/32\nQ:1/4=96\nV:", out)           # where YuE2 writes it
        self.assertEqual(A.read(out)["tempo"], 96.0)
        self.assertEqual(A.read(out)["sections"], A.read(text)["sections"])
        # what the graph's RegexReplace nodes do (case sensitive, multiline)
        g = re.sub(A.L_LINE, "\\1\nQ:1/4=96", re.sub(A.Q_LINE, "", text, flags=re.M), count=1, flags=re.M)
        self.assertEqual(g, out)
        # a plan with no Q:; one with no L:, and one with neither L: nor K:
        self.assertIn("L:1/8\nQ:1/8=70\nK:C", A.set_tempo("X:1\nL:1/8\nK:C\nabc|", 70, "1/8"))
        self.assertIn("Q:1/8=70\nK:C", A.set_tempo("X:1\nK:C\nabc|", 70, "1/8"))
        self.assertTrue(A.set_tempo("X:1\nabc|", 70).startswith("X:1\nQ:1/4=70\n"))

    def test_melody_drops_the_chords(self):
        out = A.melody(fixture("yue2_s1.abc"))
        body = out.split("K:D", 1)[1]
        self.assertNotIn('"', body)
        self.assertIn('name="Vocal Melody"', out)          # the header's quotes stay
        self.assertEqual(A.read(out)["sections"], A.read(fixture("yue2_s1.abc"))["sections"])


def tune(body: str, key="D", unit="1/8") -> str:
    return f"X:1\nM:4/4\nL:{unit}\nQ:1/4=92\nK:{key}\nV:1\n{body}\n"


class MelodyTest(unittest.TestCase):
    """A melody's pitches read, and how much of a theme a take keeps (a theme in a cue)."""

    def test_key_signatures(self):
        self.assertEqual(A.key_signature("D"), {"F": 1, "C": 1})
        self.assertEqual(A.key_signature("Bm"), {"F": 1, "C": 1})           # D's relative minor
        self.assertEqual(A.key_signature("F#m"), {"F": 1, "C": 1, "G": 1})
        self.assertEqual(A.key_signature("Eb"), {"B": -1, "E": -1, "A": -1})
        self.assertEqual(A.key_signature("D dor"), {})                       # C's notes
        self.assertEqual(A.key_signature("C"), {})
        self.assertEqual(A.key_signature("none"), {})

    def test_notes_with_key_and_bar_accidentals(self):
        # D major: F and C sharp; =F holds to the bar line, then the key again
        got = A.notes(tune("D2 F2 =F2 F2 | F4 z4 | [DFA]4 c4"))["1"]
        self.assertEqual([p for _, _, p in got], [2, 6, 5, 5, 6, None, 2, 1])
        self.assertEqual([(s, d) for s, d, _ in got][:3], [(0, 4), (4, 4), (8, 4)])   # eighths: 2 sixteenths
        self.assertEqual(got[-1], (40, 8, 1))                                # c4: a half note, C#

    def test_a_take_keeps_its_theme(self):
        theme = tune("D2 E2 F2 G2 | A4 F4 | G3 F E4 | D8")
        self.assertEqual(A.melody_match(theme, theme), 1.0)
        # the same tune a beat late, in another voice beside a bass: still all of it
        late = "X:1\nM:4/4\nL:1/8\nK:D\nV:1\nz2 D2 E2 F2 G2 | A4 F4 | G3 F E4 | D8\nV:2\nD,8 | D,8 | D,8 | D,8\n"
        self.assertEqual(A.melody_match(theme, late), 1.0)
        # half its notes changed: about half kept
        half = tune("D2 E2 F2 G2 | B4 c4 | e3 d B4 | D8")
        self.assertAlmostEqual(A.melody_match(theme, half), 0.5, delta=0.1)
        # three beats late is past the shift: not found there
        self.assertLess(A.melody_match(theme, tune("z6 D2 E2 F2 G2 | A4 F4 | G3 F E4 | D8")), 0.5)
        self.assertIsNone(A.melody_match(tune("z8"), theme))


if __name__ == "__main__":
    unittest.main()
