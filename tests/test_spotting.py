"""
core/spotting.py and scoredraft.py (docs/SOUND.md phase 8, "The simple first pass"): the
script's marks read, the Music tables read from the doc, a structure found by its name, the
draft's rules (beats in a row one cue, the story theme made then taken, stings, a sitcom's
bumpers, `// theme:` marks, `gaps`, a show's format and its lead's theme, flags), and an
episode's draft written as cues and hits, then replaced.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from seriesmith import api as A  # noqa: E402
from seriesmith import cue as CU  # noqa: E402
from seriesmith import mix as MX  # noqa: E402
from seriesmith import scoredraft as SD  # noqa: E402
from seriesmith.core import fileio as F  # noqa: E402
from seriesmith.core import ir  # noqa: E402
from seriesmith.core import spotting as SP  # noqa: E402
from test_cue import _Runner, episode  # noqa: E402


def shots(*spec):
    """(id, seq, seconds, talk seconds[, who]) in a row from 0."""
    out, t = [], 0.0
    for s in spec:
        sid, seq, d, talk = s[:4]
        who = s[4] if len(s) > 4 else []
        out.append({"id": sid, "seq": seq, "loc": f"loc_{seq}", "t": t, "d": d, "talk": talk,
                    "who": who, "speakers": [], "sound": "", "music": "", "target": ""})
        t += d
    return out


def marks(structure, beats=None, themes=None, flashback=None):
    return {"structure": structure, "beats": beats or {}, "themes": themes or {}, "flashback": flashback or []}


class MarksTest(unittest.TestCase):
    def test_each_mark_on_the_shot_below_it(self):
        m = SP.read_marks("\n".join([
            "// structure: Pixar Story Spine", "// a note", "// beat: Once upon a time…",
            "# sq01 kitchen", "## sh010", "who: ann", "// beat: Because of that…", "## sh020",
            "// theme: show, tender", "## sh030", "// beat: Because of that…", "// flashback",
            "## sh040  (a memory)"]))
        self.assertEqual(m["structure"], "Pixar Story Spine")
        self.assertEqual(m["beats"], {"sh010": "Once upon a time…", "sh020": "Because of that…",
                                      "sh040": "Because of that… (again)"})
        self.assertEqual(m["themes"], {"sh030": "show, tender"})
        self.assertEqual(m["flashback"], ["sh040"])


class TableTest(unittest.TestCase):
    def test_rows(self):
        self.assertEqual(SP.parse_row("sting (at its end)", "the act out (4)", "show, echo", "—"),
                         {"music": "sting", "sting_at": "end", "energy": [4, 4], "words": "the act out",
                          "theme": "show", "theme_words": "echo"})
        r = SP.parse_row("score", "watchful, a question (2→3)", "story, statement",
                         "turn (on the first shot), a sting at its end (the title)")
        self.assertEqual((r["energy"], r["hits"], r["sting_end"]), ([2, 3], [{"kind": "turn", "at": "start"}], True))
        r = SP.parse_row("score", "dark, sudden (4→5)", "story, echo, dark", "turn, then drop at its end")
        self.assertEqual(r["hits"], [{"kind": "turn", "at": "start"}, {"kind": "drop", "at": "end"}])
        self.assertEqual(SP.parse_row("under", "near silence (1)", "story", "drop (as it starts)")["hits"],
                         [{"kind": "drop", "at": "start"}])
        self.assertEqual(SP.parse_row("score", "the aftermath (2→3)", "show, echo; then runner, statement", "")["then"],
                         "runner")
        self.assertEqual(SP.parse_row("under (its last scene)", "warm (1→2)", "show", "—")["last_scene"], True)
        self.assertEqual(SP.parse_row("dry", "—", "—", "—"), {"music": "dry"})

    def test_structures_by_name(self):
        self.assertEqual(SP.structure("Sitcom")["id"], "2.1")
        self.assertTrue(SP.structure("Sitcom").get("bumpers"))
        self.assertEqual(SP.structure("Pixar Story Spine")["id"], "5.1")
        self.assertEqual(SP.structure("episodic drama")["id"], "2.2")
        self.assertEqual(SP.structure("4.3")["name"], "In Medias Res (Flashback Structure)")
        with self.assertRaises(SP.SpotError):
            SP.structure("Porch Lights")
        # every structure in the doc with a Music table has its beats
        self.assertEqual(len(SP.structures()), 14)
        self.assertTrue(all(s["beats"] for s in SP.structures()))
        self.assertIn("teaser", SP.table_of(SP.structure("Sitcom")))

    def test_format_checked(self):
        f = SP.check_format({"like": "episodic drama", "beats": {"Cold Open": {"music": "score", "energy": 2,
                                                                              "hits": ["turn"]}},
                             "marks": {"glance": "sting"}})
        self.assertEqual(f["like"], "Episodic Drama (Teaser and Acts)")
        self.assertEqual(f["beats"]["Cold Open"], {"music": "score", "energy": [2.0, 2.0],
                                                    "hits": [{"kind": "turn", "at": "start"}]})
        for bad in ({"beats": {"x": {"music": "loud"}}}, {"beats": {"x": {"energy": 7}}}, {"colour": 1},
                    {"marks": {"glance": "loud"}}, {"beats": {"x": {"strength": 0.2}}}):
            with self.assertRaises(SP.SpotError, msg=bad):
                SP.check_format(bad)


class DraftTest(unittest.TestCase):
    def test_spine_is_one_cue_that_makes_the_story_theme(self):
        sh = shots(("sh010", "sq1", 8, 0), ("sh020", "sq1", 10, 0), ("sh030", "sq2", 12, 0), ("sh040", "sq2", 8, 0))
        d = SP.draft(sh, marks("Pixar Story Spine", {"sh010": "Once upon a time…", "sh020": "Every day…",
                                                     "sh030": "Until one day…", "sh040": "Until finally…"}))
        self.assertEqual(len(d["cues"]), 1)
        c = d["cues"][0]
        self.assertEqual((c["makes"], c["theme"], c["t0"], c["t1"]), ("story", None, 0.0, 38.0))
        self.assertEqual([s["name"] for s in c["sections"]],
                         ["Once upon a time…", "Every day…", "Until one day…", "Until finally…"])
        self.assertEqual(sum(s["seconds"] for s in c["sections"]), 38.0)
        # a turn at each beat after the first, an arrive on the last beat's last shot
        self.assertEqual([(h["kind"], h["shot"]) for h in c["hits"]],
                         [("turn", "sh020"), ("turn", "sh030"), ("arrive", "sh040")])
        self.assertEqual((c["in"], c["out"]), ({"shot": "sh010", "at": 0.0}, {"shot": "sh040", "at": 8.0}))

    def test_the_leads_character_theme_is_the_story_theme(self):
        sh = shots(("sh010", "sq1", 8, 0, ["dean"]), ("sh020", "sq1", 10, 0, ["dean", "wallace"]))
        themes = [{"name": "dean_theme", "for": ["dean"]}]
        d = SP.draft(sh, marks("Pixar Story Spine", {"sh010": "Once upon a time…", "sh020": "Every day…"}), themes=themes)
        (c,) = d["cues"]
        self.assertEqual((c["theme"], c["makes"]), ("dean_theme", None))   # carried, not made
        self.assertIn("dean's", d["notes"][0])
        # someone else leads: the episode makes its own
        d = SP.draft(sh, marks("Pixar Story Spine", {"sh010": "Once upon a time…"}), themes=[{"name": "x", "for": ["ann"]}])
        self.assertEqual(d["cues"][0]["makes"], "story")

    def test_a_dry_beat_splits_and_the_story_theme_is_taken(self):
        sh = shots(("sh010", "sq1", 10, 0), ("sh020", "sq1", 10, 0), ("sh030", "sq2", 10, 0))
        fmt = {"beats": {"A": {"music": "score", "theme": "story"}, "B": {"music": "dry"},
                         "C": {"music": "under", "theme": "story"}}}
        d = SP.draft(sh, marks("Mine", {"sh010": "A", "sh020": "B", "sh030": "C"}), SP.check_format(fmt))
        a, c = d["cues"]
        self.assertEqual((a["makes"], c["theme"], c["makes"]), ("story", "story", None))
        # the second starts a second before its beat's cut: in the shot before
        self.assertEqual((c["t0"], c["in"]), (19.0, {"shot": "sh020", "at": 9.0}))

    def test_sitcom_stings_bumpers_and_marks(self):
        sh = shots(("sh010", "sq1", 20, 10), ("sh020", "sq2", 20, 10), ("sh030", "sq3", 20, 10),
                   ("sh040", "sq3", 20, 10), ("sh050", "sq4", 20, 10))
        themes = [{"name": "fair", "role": "show"}]
        d = SP.draft(sh, marks("Sitcom", {"sh010": "Cold Open / Teaser", "sh020": "Status Quo",
                                          "sh050": "Tag"}, {"sh040": "show, tender"}), themes=themes)
        kinds = [(c["kind"], round(c["t0"], 1), c["theme"]) for c in d["cues"]]
        self.assertIn(("sting", 17.0, "fair"), kinds)                  # the cold open's, at its end
        self.assertIn(("sting", 97.0, "fair"), kinds)                  # the tag's
        self.assertIn(("bumper", 38.5, "fair"), kinds)                 # sq2 to sq3, a new place
        self.assertNotIn(("bumper", 18.5, "fair"), kinds)              # the cold open's sting is there
        self.assertIn(("cue", 59.0, "fair"), kinds)                    # held low from sh040 to its scene's end
        held = next(c for c in d["cues"] if c["kind"] == "cue")
        self.assertEqual(held["out"], {"shot": "sh040", "at": 20.0})
        self.assertFalse(d["notes"])

    def test_gaps_score_only_where_no_one_speaks(self):
        sh = shots(("sh010", "sq1", 12, 0), ("sh020", "sq1", 5, 4), ("sh030", "sq1", 12, 0),
                   ("sh040", "sq1", 20, 18), ("sh050", "sq1", 4, 0), ("sh060", "sq1", 15, 0))
        d = SP.draft(sh, marks("Mine", {"sh010": "Squeeze"}), SP.check_format({"beats": {"Squeeze": {"music": "gaps"}}}))
        # sh010-sh030 one (5 s of lines between); sh040's 20 s of lines splits; sh050-sh060 one
        self.assertEqual([(c["t0"], c["t1"]) for c in d["cues"]], [(0.0, 29.0), (48.0, 68.0)])

    def test_other_beats_take_their_leads_theme(self):
        sh = shots(("sh010", "sq1", 10, 0, ["kell"]), ("sh020", "sq1", 10, 0, ["kell", "ann"]),
                   ("sh030", "sq2", 10, 0, ["ann"]), ("sh040", "sq2", 10, 9, ["bob"]))
        fmt = SP.check_format({"other": {"music": "score", "theme": "lead", "theme_else": "mark", "talk_max": 0.5}})
        themes = [{"name": "kell", "for": ["kell"]}, {"name": "mark"}]
        d = SP.draft(sh, marks("Mine", {"sh010": "The Bureau", "sh030": "Holding", "sh040": "Court"}), fmt, themes)
        self.assertEqual([(c["label"], c["theme"]) for c in d["cues"]],
                         [("The Bureau", "kell"), ("Holding", "mark")])     # Court talks: dry
        self.assertEqual([b["from"] for b in d["beats"]], ["other", "other", "other"])

    def test_a_long_beat_splits_at_a_sequence(self):
        sh = shots(*[(f"sh{i:03d}", f"sq{i // 4}", 30, 0) for i in range(10)])
        d = SP.draft(sh, marks("Mine", {"sh000": "Long"}), SP.check_format({"beats": {"Long": {"music": "score"}}}))
        # cut where sq1 starts; the rest, 180 s, is one
        self.assertEqual([(c["t0"], c["t1"]) for c in d["cues"]], [(0.0, 120.0), (119.0, 300.0)])
        self.assertTrue(all(c["t1"] - c["t0"] <= SP.CUE_MAX + SP.PRELAP for c in d["cues"]))

    def test_flags(self):
        sh = shots(("sh010", "sq1", 4, 0), *[(f"sh0{i}", "sq2", 2, 0) for i in range(2, 7)], ("sh070", "sq3", 10, 5))
        sh[0]["target"] = "hold"
        sh[-1]["sound"] = "a radio plays an old song"
        d = SP.draft(sh, marks(None))
        kinds = sorted(f["kind"] for f in d["flags"])
        self.assertEqual(kinds, ["card", "in-scene", "montage"])
        # no beat lines: a cue a sequence; the card is covered by the first, so flagged, no sting
        self.assertEqual([c["kind"] for c in d["cues"]], ["cue", "cue", "cue"])
        self.assertTrue(any("no // beat: lines" in n for n in d["notes"]))


class EpisodeTest(unittest.TestCase):
    """An episode's draft: written as cues and hits, replaced, a cue of the person's own kept."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self._tmp.name, "Show", "ep01")
        os.makedirs(self.root)
        episode(self.root)
        F.write_json(os.path.join(self._tmp.name, "Show", "series.json"),
                     {"sound": {"themes": {"porch": {"file": "theme.wav", "role": "show"}}}})
        story = ir.Episode(id="ep01", sequences=[
            ir.Sequence(id="sq01", location="kitchen", shots=[
                ir.Shot(id="sh010", cast=["ann"]), ir.Shot(id="sh020", cast=["ann"])]),
            ir.Sequence(id="sq02", location="porch", shots=[ir.Shot(id="sh030", cast=["bob"])])])
        F.write_text(os.path.join(self.root, "shotlist", "shots.json"), json.dumps(story.to_json()))
        F.write_text(os.path.join(self.root, "ep01.md"), "\n".join([
            "// structure: Pixar Story Spine", "# sq01 kitchen", "// beat: Once upon a time…", "## sh010",
            "// beat: Until one day…", "## sh020", "# sq02 porch", "// beat: And ever since then…", "## sh030"]))

    def tearDown(self):
        self._tmp.cleanup()

    def test_written_then_replaced(self):
        d = SD.draft(self.root, "final")
        self.assertEqual(d["structure"], "The Pixar Story Spine")
        self.assertEqual(d["missing"], [])
        (c,) = [c for c in d["cues"] if c.get("spec")]
        spec = c["spec"]
        self.assertEqual((spec["id"], spec["in"], spec["out"]),
                         ("d01", {"shot": "sh010", "frame": 0}, {"shot": "sh030", "frame": 120}))
        self.assertEqual([s["name"] for s in spec["sections"]],
                         ["Once upon a time…", "Until one day…", "And ever since then…"])
        self.assertTrue(spec["label"].startswith("Draft: "))
        r = SD.write(self.root, "final", d)
        self.assertEqual((r["cues"], r["hits"]), (["d01"], 2))           # a turn at each later beat
        mix = MX.check(MX.load(self.root)["final"])
        self.assertEqual([(h["id"], h["kind"], h["at"]["shot"], h["must"]) for h in mix["hits"]],
                         [("dh01", "turn", "sh020", False), ("dh02", "turn", "sh030", False)])
        self.assertTrue(mix["tracks"]["dialogue"]["voices_only"])
        self.assertEqual(CU.load_spec(self.root, "d01")["hits"], ["dh01", "dh02"])
        # the cue plans against the cut as any cue does
        p = CU.plan(self.root, "final", CU.load_spec(self.root, "d01"))
        self.assertEqual(len(p["sections"]), 3)
        # a second draft refuses, unless it replaces the first
        with self.assertRaises(SD.DraftError):
            SD.write(self.root, "final", SD.draft(self.root, "final"))
        r = SD.write(self.root, "final", SD.draft(self.root, "final"), replace=True)
        self.assertEqual((r["removed"], r["cues"]), (["d01"], ["d01"]))
        self.assertEqual([h["id"] for h in MX.check(MX.load(self.root)["final"])["hits"]], ["dh01", "dh02"])

    def test_a_rendered_draft_cue_is_kept_on_replace(self):
        SD.write(self.root, "final", SD.draft(self.root, "final"))
        n = CU.reserve(self.root, "d01", {"pass": "final"})
        CU.update(self.root, "d01", n, status="ok")                     # a finished take: the person's now
        d = SD.draft(self.root, "final")
        self.assertEqual((d["drafted"], d["kept"]), ([], ["d01"]))
        self.assertIn("d01 already plays there", d["cues"][0]["skip"])
        r = SD.write(self.root, "final", d)                             # nothing to replace: no refusal
        self.assertEqual((r["removed"], r["cues"]), ([], []))
        self.assertEqual([c["id"] for c in CU.list_cues(self.root)], ["d01"])
        # its hits stay with it
        self.assertEqual([h["id"] for h in MX.check(MX.load(self.root)["final"])["hits"]], ["dh01", "dh02"])

    def test_rendered_ones_replaced_too_but_a_series_theme_kept(self):
        SD.write(self.root, "final", SD.draft(self.root, "final"))
        n = CU.reserve(self.root, "d01", {"pass": "final"})
        CU.update(self.root, "d01", n, status="ok")
        d = SD.draft(self.root, "final", rendered=True)
        self.assertEqual((d["drafted"], d["kept"]), (["d01"], []))
        r = SD.write(self.root, "final", d, replace=True)
        self.assertEqual((r["removed"], r["cues"]), (["d01"], ["d01"]))
        self.assertEqual(CU.list_takes(self.root, "d01"), [])          # the new one, no takes
        # a series theme's cue is kept, rendered or not
        n = CU.reserve(self.root, "d01", {"pass": "final"})
        CU.update(self.root, "d01", n, status="ok")
        F.write_json(os.path.join(self._tmp.name, "Show", "series.json"),
                     {"sound": {"themes": {"intro": {"ep": "ep01", "cue": "d01", "take": n}}}})
        d = SD.draft(self.root, "final", rendered=True)
        self.assertEqual((d["drafted"], d["kept"]), ([], ["d01"]))

    def test_trimmed_around_a_kept_cue(self):
        self.assertEqual(SD._free(0.0, 80.0, [(0.0, 11.0)]), (11.0, 80.0))
        self.assertEqual(SD._free(0.0, 80.0, [(30.0, 40.0)]), (40.0, 80.0))
        self.assertIsNone(SD._free(0.0, 10.0, [(0.0, 12.0)]))
        sh = shots(("sh010", "sq1", 11.0417, 0), ("sh020", "sq2", 20, 0), ("sh030", "sq2", 20, 0))
        c = {"t0": 0.0, "t1": 51.0417, "hits": [{"kind": "turn", "shot": "sh020", "end": False},
                                                 {"kind": "arrive", "shot": "sh010", "end": False}],
             "sections": [{"name": "A", "seconds": 11.0417}, {"name": "B", "seconds": 40.0}]}
        # a cut rounded a hair after the kept cue's end still starts the trimmed cue on its shot
        SD._trim(c, (11.04163, 51.0417), sh)
        self.assertEqual((c["in"], c["out"]), ({"shot": "sh020", "at": 0.0}, {"shot": "sh030", "at": 20.0}))
        self.assertEqual([x["name"] for x in c["sections"]], ["B"])
        self.assertEqual([h["shot"] for h in c["hits"]], ["sh020"])

    def test_a_cue_of_ones_own_is_kept(self):
        CU.save_spec(self.root, {"id": "m01", "in": {"shot": "sh020", "frame": 0}, "out": {"shot": "sh020", "frame": 100}})
        d = SD.draft(self.root, "final")
        self.assertIn("m01 already plays there", d["cues"][0]["skip"])
        self.assertFalse(SD.write(self.root, "final", d)["cues"])
        self.assertEqual([c["id"] for c in CU.list_cues(self.root)], ["m01"])

    def test_pinned_for_a_character(self):
        SD.write(self.root, "final", SD.draft(self.root, "final"))
        n = CU.reserve(self.root, "d01", {"pass": "final"})
        CU.update(self.root, "d01", n, status="ok")
        ctx = A.Context(os.path.join(self._tmp.name, "user"), "http://127.0.0.1:0", env={}, runner=_Runner())
        A.put_config(ctx, {"roots": [os.path.join(self._tmp.name, "Show")]})
        code, r = A.post_cue_theme(ctx, {"ep": self.root, "cue": "d01", "take": n, "name": "ann", "for": ["ann"]})
        self.assertEqual((code, r["theme"]["for"]), (200, ["ann"]))
        self.assertEqual(A.post_cue_theme(ctx, {"ep": self.root, "cue": "d01", "take": n, "name": "x", "for": "ann"})[0], 400)
        # drafted again: ann leads the episode, so her theme is its theme
        d = SD.draft(self.root, "final", rendered=True)
        self.assertIn("ann's", " ".join(d["notes"]))

    def test_route(self):
        ctx = A.Context(os.path.join(self._tmp.name, "user"), "http://127.0.0.1:0", env={}, runner=_Runner())
        A.put_config(ctx, {"roots": [os.path.join(self._tmp.name, "Show")]})
        code, r = A.post_cue_draft(ctx, {"ep": self.root, "pass": "final"})
        self.assertEqual(code, 200, r)
        self.assertIsNone(r["written"])
        self.assertIn("The Pixar Story Spine", r["text"])
        self.assertEqual(CU.list_cues(self.root), [])                   # shown, not written
        code, r = A.post_cue_draft(ctx, {"ep": self.root, "pass": "final", "write": True, "keep_sound": True})
        self.assertEqual((code, r["written"]["cues"]), (200, ["d01"]))
        self.assertNotIn("dialogue", MX.check(MX.load(self.root)["final"]).get("tracks") or {})
        code, r = A.post_cue_draft(ctx, {"ep": self.root, "pass": "final", "write": True})
        self.assertEqual(code, 409)
        self.assertIn("has a draft already", r["error"])
        self.assertEqual(A.post_cue_draft(ctx, {"ep": self.root, "write": "yes"})[0], 400)


if __name__ == "__main__":
    unittest.main()
