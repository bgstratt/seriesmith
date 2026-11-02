"""
The export's picture checks (seriesmith/checks.py, docs/FINISHING.md "The export's checks"):
black runs, frozen runs and flashes found on synthetic clips, each with its times and shot;
what the cut's own fades and held shots explain left out; the report's shape; and assemble
writing it beside the cut, never changing the cut.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
from seriesmith import checks as CK  # noqa: E402
from seriesmith import ff as FF  # noqa: E402

HAVE_FF = bool(FF.have("ffmpeg"))
FPS = 24


def luma(values, fps=FPS):
    return [(i / fps, v) for i, v in enumerate(values)]


class FlashTest(unittest.TestCase):
    def test_fast_flashing_is_flagged(self):
        # black and white every 3 frames: 4 flashes a second, for 4 s
        got = CK.flash_runs(luma([16 if (i // 3) % 2 == 0 else 235 for i in range(96)]))
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["flashes"], 4)
        self.assertLess(got[0]["start"], 0.5)
        self.assertGreater(got[0]["end"], 3.5)

    def test_slow_or_small_changes_are_not(self):
        # every 12 frames: one flash a second
        self.assertEqual(CK.flash_runs(luma([16 if (i // 12) % 2 == 0 else 235 for i in range(96)])), [])
        # every 3 frames but small (well under 10 % of the luminance range)
        self.assertEqual(CK.flash_runs(luma([100 if (i // 3) % 2 == 0 else 108 for i in range(96)])), [])
        # bright against bright (both ends above 0.8): not a flash
        self.assertEqual(CK.flash_runs(luma([222 if (i // 3) % 2 == 0 else 235 for i in range(96)])), [])
        # a fade: one change, however deep
        self.assertEqual(len(CK.turns(luma([16 + i * 2 for i in range(100)]))), 1)
        self.assertEqual(CK.flash_runs(luma([16 + i * 2 for i in range(100)])), [])

    def test_exactly_three_a_second_passes(self):
        # six changes in a second is three flashes: allowed; seven is flagged
        self.assertEqual(CK.flash_runs(luma([16 if (i // 4) % 2 == 0 else 235 for i in range(23)])), [])
        self.assertEqual(len(CK.flash_runs(luma([16 if (i // 3) % 2 == 0 else 235 for i in range(24)]))), 1)


class ParseTest(unittest.TestCase):
    LOG = """[blackdetect @ 0x1] black_start:2 black_end:3.5 black_duration:1.5
[Parsed_metadata_4 @ 0x2] frame:0    pts:0       pts_time:0
[Parsed_metadata_4 @ 0x2] lavfi.signalstats.YAVG=16.5
[freezedetect @ 0x3] lavfi.freezedetect.freeze_start: 4.5
[freezedetect @ 0x3] lavfi.freezedetect.freeze_duration: 3
[freezedetect @ 0x3] lavfi.freezedetect.freeze_end: 7.5
[Parsed_metadata_4 @ 0x2] frame:1    pts:1       pts_time:0.0416667
[Parsed_metadata_4 @ 0x2] lavfi.signalstats.YAVG=200
[freezedetect @ 0x3] lavfi.freezedetect.freeze_start: 9
"""

    def test_parse(self):
        got = CK.parse(self.LOG)
        self.assertEqual(got["black"], [(2.0, 3.5)])
        self.assertEqual(got["frozen"], [(4.5, 7.5), (9.0, None)])
        self.assertEqual(got["luma"], [(0.0, 16.5), (0.0416667, 200.0)])


class ExplainTest(unittest.TestCase):
    """What the cut explains, on a scan given (no ffmpeg)."""

    CLIPS = [{"id": "sh010", "a": 0.0, "b": 4.0, "fade_in": 0.0, "fade_out": 1.0, "held": False},
             {"id": "sh020", "a": 4.0, "b": 8.0, "fade_in": 0.5, "fade_out": 0.0, "held": False},
             {"id": "sh030", "a": 8.0, "b": 12.0, "fade_in": 0.0, "fade_out": 0.0, "held": True},
             {"id": "sh040", "a": 12.0, "b": 20.0, "fade_in": 0.0, "fade_out": 0.0, "held": False}]

    def test_fades_and_holds_explain(self):
        scan = {"black": [(3.6, 4.3), (14.0, 15.0)], "frozen": [(3.6, 6.8), (3.6, 5.0), (8.0, 12.0), (16.0, None)],
                "luma": []}
        got = CK.check("x.mp4", self.CLIPS, FPS, 20.0, scanned=scan)
        # the fade out of sh010 into sh020's fade in is black on purpose; sh040's isn't
        self.assertEqual([(r["start"], r["end"], r["shot"]) for r in got["black"]], [(14.0, 15.0, "sh040")])
        # frozen: what is left past the black (4.3-6.8) is frozen, 4.3-5.0 too short to say; the
        # held sh030 is a still on purpose; sh040's runs to the end of the cut
        self.assertEqual([(r["start"], r["end"], r["shots"]) for r in got["frozen"]],
                         [(4.3, 6.8, ["sh020"]), (16.0, 20.0, ["sh040"])])
        self.assertEqual(got["explained"], {"black": 1, "frozen": 1})
        self.assertFalse(got["ok"])
        self.assertIn("1 black run (sh040 00:14.0 1.0 s)", got["verdict"])
        self.assertIn("2 frozen runs", got["verdict"])
        self.assertIn("left out", got["verdict"])

    def test_a_frozen_black_run_is_said_once(self):
        scan = {"black": [(14.0, 17.0)], "frozen": [(14.0, 17.0)], "luma": []}
        got = CK.check("x.mp4", self.CLIPS, FPS, 20.0, scanned=scan)
        self.assertEqual(len(got["black"]), 1)
        self.assertEqual(got["frozen"], [])

    def test_clean(self):
        got = CK.check("x.mp4", self.CLIPS, FPS, 20.0, scanned={"black": [], "frozen": [], "luma": []})
        self.assertTrue(got["ok"])
        self.assertEqual(got["verdict"], "no black, frozen or flashing runs")
        self.assertEqual(set(got), {"black", "frozen", "flashes", "explained", "rules", "ok", "verdict"})
        self.assertEqual(got["rules"]["flashes"]["more_than_per_second"], 3)


def make_cut(path: str) -> None:
    """2 s moving, 1 s black, 1 s moving, 3 s a still grey, 1 s moving, 2 s flashing, 1 s moving."""
    def src(i):
        return ["-f", "lavfi", "-i", i]
    mv = f"testsrc2=s=160x90:r={FPS}:d=%s"
    inputs = (src(mv % 2) + src(f"color=black:s=160x90:r={FPS}:d=1") + src(mv % 1)
              + src(f"color=0x808080:s=160x90:r={FPS}:d=3") + src(mv % 1)
              + src(f"color=black:s=160x90:r={FPS}:d=2,geq=lum='if(lt(mod(N,6),3),16,235)':cb=128:cr=128")
              + src(mv % 1))
    fc = "".join(f"[{i}:v]format=yuv420p,setsar=1[v{i}];" for i in range(7))
    fc += "".join(f"[v{i}]" for i in range(7)) + "concat=n=7:v=1:a=0[out]"
    subprocess.run([*FF.tool("ffmpeg"), "-y", "-v", "error", *inputs, "-filter_complex", fc,
                    "-map", "[out]", "-c:v", "libx264", "-pix_fmt", "yuv420p", path], check=True)


@unittest.skipUnless(HAVE_FF, "needs ffmpeg")
class ScanTest(unittest.TestCase):
    def test_each_detector_on_a_synthetic_cut(self):
        with tempfile.TemporaryDirectory() as tmp:
            cut = os.path.join(tmp, "cut.mp4")
            make_cut(cut)
            clips = [{"id": f"sh{i}0", "a": float(a), "b": float(b), "fade_in": 0.0, "fade_out": 0.0, "held": False}
                     for i, (a, b) in enumerate([(0, 2), (2, 4), (4, 7), (7, 8), (8, 10), (10, 11)], 1)]
            st = os.stat(cut)
            got = CK.check(cut, clips, FPS, 11.0)
            self.assertEqual((os.stat(cut).st_mtime, os.stat(cut).st_size), (st.st_mtime, st.st_size))
            self.assertEqual(len(got["black"]), 1)
            b = got["black"][0]
            self.assertAlmostEqual(b["start"], 2.0, delta=0.1)
            self.assertAlmostEqual(b["end"], 3.0, delta=0.1)
            self.assertEqual(b["shot"], "sh20")
            self.assertEqual(len(got["frozen"]), 1)
            f = got["frozen"][0]
            self.assertAlmostEqual(f["start"], 4.0, delta=0.1)
            self.assertAlmostEqual(f["end"], 7.0, delta=0.1)
            self.assertEqual(f["shots"], ["sh30"])
            self.assertEqual(len(got["flashes"]), 1)
            fl = got["flashes"][0]
            self.assertEqual(fl["shot"], "sh50")
            self.assertEqual(fl["flashes"], 4)
            self.assertGreaterEqual(fl["start"], 7.9)
            self.assertLessEqual(fl["end"], 10.1)
            # the black second as a fade out and the grey as a held shot: left out
            clips[0]["fade_out"] = 0.1
            clips[1]["fade_in"] = 1.05
            clips[2]["held"] = True
            got = CK.check(cut, clips, FPS, 11.0)
            self.assertEqual((got["black"], got["frozen"]), ([], []))
            self.assertEqual(got["explained"], {"black": 1, "frozen": 1})


if __name__ == "__main__":
    unittest.main()
