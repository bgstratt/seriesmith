"""
`continuous:` (docs/CONTINUOUS.md): how a shot follows the previous one. The
parser and the IR -- a shot's own line, a `#` header's default for the shots
after its first, `none` breaking the chain, the old forms read as the new ones
with a warning -- and the first keyframe a `first` shot gets.
"""
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from seriesmith import build  # noqa: E402
from seriesmith.core.story import ScriptError, parse_story  # noqa: E402


def story(body: str):
    text = "= e01  Test\n" + body
    return parse_story(text, {"ada"}, {"ada"})


def shots(st):
    return {sh.id: (sh, sq) for sq in st.sequences for sh in sq.shots}


SEQ = """# sq01  kitchen
continuous: first
## sh010
who: ada
Ada waits.
## sh020
who: ada
Ada waits more.
## sh030
continuous: none
who: ada
Ada leaves.
# sq02  street
## sh040
continuous: latent
who: ada
Ada walks.
## sh050
who: ada
Ada stops.
"""


class ParseTest(unittest.TestCase):
    def test_a_header_covers_the_shots_after_its_first(self):
        by = shots(story(SEQ))
        self.assertEqual({k: sh.continues(sq) for k, (sh, sq) in by.items()},
                         {"sh010": None, "sh020": "first", "sh030": None,
                          "sh040": "latent", "sh050": None})

    def test_first_makes_the_first_keyframe_continuity(self):
        by = shots(story(SEQ))
        sh, sq = by["sh020"]
        self.assertEqual(sh.keyframe("first", sq), "continuity")
        sh, sq = by["sh010"]
        self.assertIsNone(sh.keyframe("first", sq))
        sh, sq = by["sh040"]                      # latent isn't a keyframe
        self.assertIsNone(sh.keyframe("first", sq))

    def test_the_old_forms_read_as_the_new_ones_with_a_warning(self):
        st = story("""# sq01  kitchen
continuous: yes
## sh010
who: ada
Ada waits.
## sh020
first: continuity
who: ada
Ada waits more.
""")
        by = shots(st)
        self.assertEqual(st.sequences[0].continuous, "latent")
        sh, sq = by["sh020"]
        self.assertEqual(sh.continuous, "first")         # its own old line beats the header
        self.assertIsNone(sh.first)
        warnings = build.story_warnings(st, {})
        self.assertTrue(any("`continuous: yes`" in w and "continuous: latent" in w for w in warnings))
        self.assertTrue(any("`first: continuity` on shot sh020" in w for w in warnings))

    def test_overlap(self):
        st = story("""# sq01  kitchen
overlap: 22
## sh010
who: ada
Ada waits.
## sh020
continuous: latent
overlap: 39
who: ada
Ada waits more.
""")
        self.assertEqual(st.sequences[0].overlap, 22)
        self.assertEqual(shots(st)["sh020"][0].overlap, 39)

    def test_what_is_refused(self):
        for body, why in (("## sh010\ncontinuous: yes\nwho: ada\nAda.\n", "must be first"),
                          ("## sh010\ncontinuous: frame\nwho: ada\nAda.\n", "must be first"),
                          ("## sh010\noverlap: 0\nwho: ada\nAda.\n", "1 to 360"),
                          ("## sh010\nfirst: continue\nwho: ada\nAda.\n", "continuous: first")):
            with self.subTest(body=body), self.assertRaisesRegex(ScriptError, why):
                story("# sq01  kitchen\n" + body)

    def test_the_ir_round_trips(self):
        from seriesmith.core.ir import Episode
        st = story(SEQ)
        back = Episode.from_json(st.to_json())
        self.assertEqual({sh.id: sh.continues(sq) for sq in back.sequences for sh in sq.shots},
                         {sh.id: sh.continues(sq) for sq in st.sequences for sh in sq.shots})
        # an old IR's `"continuous": true` was the chaining `latent` names
        d = st.to_json()
        d["sequences"][1]["continuous"] = True
        self.assertEqual(Episode.from_json(d).sequences[1].continuous, "latent")


if __name__ == "__main__":
    unittest.main()


class PartnerTest(unittest.TestCase):
    """A `continuous: first` shot on a target that reads no first keyframe
    renders on its partner (target.json `continuous.first`): H3 Ref2VA's is
    H3 FL2VA, FastH3 Omni's fasth3_fl2va. The render keeps it there when the
    target came from the script (a `#` header), not only from the series
    config (jobs.script_targets reads the build's routing). H3 Singularity
    reads one when asked (keyframes_when_asked): its shot stays on it."""

    def test_a_sequence_target_keeps_its_partner_at_render(self):
        import shutil
        import subprocess
        import tempfile
        from seriesmith import jobs as J
        from test_render import ENV, FIXTURE
        with tempfile.TemporaryDirectory() as ep:
            shutil.copy(os.path.join(FIXTURE, "series.json"), ep)
            with open(os.path.join(FIXTURE, "script.md"), encoding="utf-8") as fh:
                text = fh.read()
            text = text.replace("# sq01  kitchen\n", "# sq01  kitchen\ntarget: h3_singularity\n", 1)
            text = text.replace("# sq02  street\n", "# sq02  street\ntarget: fasth3_omni\n", 1)
            text = text.replace("## sh020\n", "## sh020\ncontinuous: first\n", 1)
            text = text.replace("## sh120\n", "## sh120\ncontinuous: first\n", 1)
            script = os.path.join(ep, "ep.md")
            with open(script, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
            subprocess.run([sys.executable, "-m", "seriesmith", "build",
                            os.path.join(ep, "series.json"), script, "-o", ep],
                           check=True, capture_output=True, env=ENV)
            got = J.script_targets(ep)
            self.assertEqual((got["sh010"], got["sh020"]), ("h3_singularity", "h3_singularity"))
            self.assertEqual((got["sh110"], got["sh120"]), ("fasth3_omni", "fasth3_fl2va"))
            self.assertEqual(J.target_choice({}, "sh120", "fasth3_fl2va", root=ep),
                             ("fasth3_fl2va", "script"))
            # Singularity's shot carries its first frame; the others' don't ask
            doc, i = J.find_shot(ep, "final", "sh020")
            self.assertEqual(doc["shots"][i]["keyframes"], {"first": "refs/shots/sh020/first.png"})
            doc, i = J.find_shot(ep, "final", "sh010")
            self.assertNotIn("keyframes", doc["shots"][i])
            # the Refs tab asks only the shot that asks for one (not every Singularity shot)
            from seriesmith import refs as R
            needs = R.keyframe_needs(ep)
            self.assertIn(("sh020", "first"), needs)
            self.assertNotIn(("sh010", "first"), needs)
            self.assertNotIn(("sh030", "first"), needs)

    def test_the_series_config_names_the_first_frame_model(self):
        from seriesmith import targets as TG
        from seriesmith.core.story import parse_story
        text = ("= e01  Test\n# sq01  kitchen\n## sh010\nwho: ada\nAda waits.\n"
                "## sh020\ncontinuous: first\nwho: ada\nAda waits more.\n"
                "# sq02  street\ntarget: fasth3_omni\n## sh030\nwho: ada\nAda walks.\n"
                "## sh040\ncontinuous: first\nwho: ada\nAda stops.\n")
        st = parse_story(text, {"ada"}, {"ada"})
        cfg = {"series": {"target": "minimax_h3_ref2va"}}
        by = TG.shot_targets(st, cfg)
        # each target's own partner
        self.assertEqual((by["sh020"], by["sh040"]), ("minimax_h3_fl2va", "fasth3_fl2va"))
        # the series config's, over every partner
        cfg["series"]["first_target"] = "h3_singularity_fl2va"
        by = TG.shot_targets(st, cfg)
        self.assertEqual((by["sh020"], by["sh040"]), ("h3_singularity_fl2va", "h3_singularity_fl2va"))
        self.assertEqual(by["sh030"], "fasth3_omni")
        # Ref2VA itself: it opens on the frame, its pictures kept
        cfg["series"]["first_target"] = "minimax_h3_ref2va"
        by = TG.shot_targets(st, cfg)
        self.assertEqual((by["sh020"], by["sh040"]), ("minimax_h3_ref2va", "minimax_h3_ref2va"))
        for bad in ("fasth3_omni", "nope", 3):
            cfg["series"]["first_target"] = bad
            with self.assertRaises(ValueError) as cm:
                TG.shot_targets(st, cfg)
            self.assertIn("first_target", str(cm.exception))
