"""
takecheck: a finished take's checks (a cut it wasn't asked for, its words) and how
they're recorded, shown and kept. The cut check runs ffmpeg on made-up clips: a hard
cut between two pictures, and a picture that moves the whole time without one.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from seriesmith import edit as E  # noqa: E402
from seriesmith import ff as FF  # noqa: E402
from seriesmith import takecheck as TC  # noqa: E402
from seriesmith import takes as T  # noqa: E402


def _clip(path: str, *sources: str) -> None:
    """An mp4 of the lavfi sources one after another, 24 fps, 160x90."""
    ins = []
    for src in sources:
        ins += ["-f", "lavfi", "-i", f"{src}{':' if '=' in src else '='}s=160x90:r=24:d=1"]
    n = len(sources)
    fc = "".join(f"[{i}:v]" for i in range(n)) + f"concat=n={n}:v=1:a=0,format=yuv420p[v]"
    subprocess.run([*FF.tool("ffmpeg"), "-y", "-v", "error", *ins, "-filter_complex", fc,
                    "-map", "[v]", "-c:v", "libx264", "-crf", "18", path], check=True)


class RulesTest(unittest.TestCase):
    def test_a_hard_cut_scores_past_the_line(self):
        per = [0.0, 0.4, 0.6, 30.0, 0.5, 11.9, 12.0]
        self.assertEqual(TC.cuts(per, 24.0), [{"frame": 3, "t": 0.12, "score": 30.0},
                                              {"frame": 6, "t": 0.25, "score": 12.0}])

    def test_a_multishot_groups_own_cuts_are_asked_for(self):
        shot = {"multishot": [{"id": "sh040", "start": 0, "frames": 50}, {"id": "sh050", "start": 50}]}
        self.assertEqual(TC.asked_cuts(shot), [50])
        per = [0.0] * 100
        per[52], per[80] = 40.0, 40.0
        self.assertEqual([c["frame"] for c in TC.cuts(per, 24.0, TC.asked_cuts(shot))], [80])

    def test_words_matched_word_by_word(self):
        self.assertEqual(TC.match("That case isn't yours, Kess.", "That case isn’t yours Kess"), 1.0)
        self.assertEqual(TC.match("Are you lost, little owl?", "Are you lost, window owl?"), 0.8)
        self.assertEqual(TC.match("Cut it.", ""), 0.0)

    def test_flags(self):
        self.assertEqual(TC.flags(None), [])
        self.assertEqual(TC.flags({"cuts": [{"frame": 3}], "words": {"match": 0.8}, "words_match": 0.85}),
                         ["cut", "words"])
        self.assertEqual(TC.flags({"cuts": [], "words": {"why": "no Whisper"}}), [])
        self.assertEqual(TC.flags({"cuts": [], "words": None}), [])

    def test_checks_kept_only_while_the_mp4_is_the_same(self):
        sc = {"checks": {"v": TC.VERSION, "size": 100, "cuts": [], "words": None}}
        self.assertIsNotNone(TC.checks_of(sc, size=100))
        self.assertIsNone(TC.checks_of(sc, size=101))
        self.assertIsNone(TC.checks_of({"checks": {"v": 0, "size": 100}}, size=100))

    def test_the_line_takes_prints(self):
        self.assertEqual(E.check_line(None), "")
        self.assertEqual(E.check_line({"flags": ["cut", "words"], "cuts": [0.58], "match": 0.8,
                                       "heard": "Are you lost, window owl?"}),
                         'check: CUT at 0.58s; WORDS 0.80: heard "Are you lost, window owl?"')


@unittest.skipUnless(FF.have("ffmpeg"), "needs ffmpeg")
class PictureTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="takecheck-")

    def test_a_cut_between_two_pictures_is_found(self):
        p = os.path.join(self.tmp, "cut.mp4")
        _clip(p, "testsrc2", "color=c=0x2040c0")
        got = TC.cuts(TC.scores(p), 24.0)
        self.assertEqual(len(got), 1)
        self.assertIn(got[0]["frame"], (23, 24, 25))

    def test_a_moving_picture_without_a_cut_is_not(self):
        p = os.path.join(self.tmp, "moving.mp4")
        _clip(p, "testsrc2", "testsrc2")
        self.assertEqual(TC.cuts(TC.scores(p), 24.0), [])

    def test_recorded_into_the_take(self):
        d = os.path.join(self.tmp, "renders", "sh010")
        os.makedirs(d)
        _clip(os.path.join(d, "sh010_t01.mp4"), "testsrc2", "color=c=0x2040c0")
        with open(os.path.join(d, "sh010_t01.json"), "w", encoding="utf-8") as fh:
            json.dump({"status": "ok", "fps": 24.0}, fh)
        with open(os.path.join(d, "sh010_t01.shotlist.json"), "w", encoding="utf-8") as fh:
            json.dump({"shots": [{"id": "sh010", "audio_policy": "dub"}]}, fh)
        take = T.get_take(self.tmp, "final", "sh010", 1)
        got = TC.record(self.tmp, take)
        self.assertEqual(len(got["cuts"]), 1)
        self.assertIsNone(got["words"])                  # dubbed: the model didn't speak
        sc = T.read_sidecar(take.paths.sidecar)
        self.assertEqual(TC.summary(sc, take.paths.mp4)["flags"], ["cut"])
        # its words can't be heard without a script to read: the cut is still recorded
        T.update_sidecar(take.paths.sidecar, checks=None)
        with open(take.paths.shotlist, "w", encoding="utf-8") as fh:
            json.dump({"shots": [{"id": "sh010", "audio_policy": "generate"}]}, fh)
        got = TC.record(self.tmp, take)
        self.assertEqual(len(got["cuts"]), 1)
        self.assertIn("script", got["words"]["why"])
        # a take still rendering isn't checked
        T.update_sidecar(take.paths.sidecar, status="queued")
        self.assertIsNone(TC.record(self.tmp, T.get_take(self.tmp, "final", "sh010", 1)))


if __name__ == "__main__":
    unittest.main()
