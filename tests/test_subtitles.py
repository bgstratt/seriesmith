"""
subtitles: the cut's lines timed by the words heard in each clip's sound (its take's, or the
recording it's dubbed to), else spread over the clip; written as SRT and WebVTT; carried by
publish, shifted by the intro (a cold open's head left where it is).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from seriesmith import lines as LN  # noqa: E402
from seriesmith import subtitles as SUB  # noqa: E402

FPS = 24.0


def _file(path: str, words: list[dict] | None = None) -> str:
    with open(path, "wb") as fh:
        fh.write(b"x")
    if words is not None:
        time.sleep(0.01)
        with open(path + ".words.json", "w", encoding="utf-8") as fh:
            json.dump(words, fh)
    return path


class CuesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="subs-")
        self.shots = [{"id": "sh010", "lines": [{"text": "That case isn't yours, Kess."}]},
                      {"id": "sh020", "lines": []},
                      {"id": "sh030", "lines": [{"text": "Neither's the city."}, {"text": "I'm borrowing both."}]}]

    def cues(self, plan, origins):
        with mock.patch.object(LN, "script_shots", lambda root: self.shots):
            return SUB.cues(self.tmp, plan, origins, FPS)

    def test_timed_by_the_words_and_spread_without_them(self):
        own = _file(os.path.join(self.tmp, "sh010_t01_h3.wav"), [
            {"word": "That", "start": 1.0, "end": 1.2}, {"word": "case", "start": 1.2, "end": 1.5},
            {"word": "isn't", "start": 1.5, "end": 1.8}, {"word": "yours,", "start": 1.8, "end": 2.1},
            {"word": "Kess.", "start": 2.1, "end": 2.6}])
        plan = [{"id": "sh010", "wav": own, "base": own, "audio_spec": None},
                {"id": "sh020", "wav": None, "base": None, "audio_spec": None},
                {"id": "sh030", "wav": _file(os.path.join(self.tmp, "sh030.wav")), "audio_spec": None}]
        # sh010 trimmed by 12 frames (0.5 s): its take's 1.0 s is the cut's 0.5 s
        origins = {"sh010": {"origin": -12, "first": 12, "used": 72},
                   "sh020": {"origin": 60, "first": 0, "used": 48},
                   "sh030": {"origin": 108, "first": 0, "used": 96}}
        cs = self.cues(plan, origins)
        self.assertEqual([c["shot"] for c in cs], ["sh010", "sh030", "sh030"])
        self.assertAlmostEqual(cs[0]["start"], 0.5)
        self.assertAlmostEqual(cs[0]["end"], 2.1)
        self.assertTrue(cs[0]["timed"])
        # not heard: its two lines share its 4 s (108-204 frames) by their length
        self.assertFalse(cs[1]["timed"])
        self.assertAlmostEqual(cs[1]["start"], 4.5)
        self.assertLess(cs[1]["end"], cs[2]["start"])
        self.assertAlmostEqual(cs[2]["end"], 8.5)

    def test_a_dubbed_clip_is_timed_in_its_recording(self):
        rec = _file(os.path.join(self.tmp, "rec.wav"), [
            {"word": "Neither's", "start": 30.2, "end": 30.6}, {"word": "the", "start": 30.6, "end": 30.7},
            {"word": "city.", "start": 30.7, "end": 31.1}, {"word": "I'm", "start": 31.5, "end": 31.6},
            {"word": "borrowing", "start": 31.6, "end": 32.0}, {"word": "both.", "start": 32.0, "end": 32.4},
            {"word": "elsewhere", "start": 50.0, "end": 50.5}])
        plan = [{"id": "sh030", "sourced": True, "audio_src": rec, "audio_spec": {"start": 30.0, "offset": 0.0}}]
        cs = self.cues(plan, {"sh030": {"origin": 48, "first": 0, "used": 72}})
        self.assertEqual(len(cs), 2)
        self.assertAlmostEqual(cs[0]["start"], 2.2)          # 30.2 in the recording, the clip from 2.0 s
        self.assertAlmostEqual(cs[1]["end"], 4.4)
        self.assertTrue(all(c["timed"] for c in cs))

    def test_the_files_and_publish(self):
        cs = [{"start": 0.5, "end": 2.1, "text": "That case isn't yours, Kess."},
              {"start": 61.25, "end": 3725.5, "text": SUB.wrap("A line long enough that it has to be wrapped onto two.")}]
        base = os.path.join(self.tmp, "ep01")
        paths = SUB.write(base, cs)
        with open(paths[0], encoding="utf-8") as fh:
            srt = fh.read()
        self.assertTrue(srt.startswith("1\n00:00:00,500 --> 00:00:02,100\nThat case isn't yours, Kess.\n\n2\n"))
        self.assertIn("01:02:05,500\nA line long enough that it\nhas to be wrapped onto two.", srt)
        with open(paths[1], encoding="utf-8") as fh:
            self.assertTrue(fh.read().startswith("WEBVTT\n\n00:00:00.500 --> 00:00:02.100\n"))
        self.assertEqual([(round(c["start"], 2), c["text"]) for c in SUB.read_srt(paths[0])][0],
                         (0.5, "That case isn't yours, Kess."))
        from seriesmith import publish as PB
        out = os.path.join(self.tmp, "publish", "ep01.mp4")
        os.makedirs(os.path.dirname(out))
        with mock.patch.object(PB, "probe", lambda p: {"frames": 120, "duration": 5.0}):
            got = PB.carry_subtitles(base + ".mp4", out, "INTRO.mp4", {"fps": FPS}, 48)   # a cold open: 2 s
        moved = SUB.read_srt(got[0])
        self.assertAlmostEqual(moved[0]["start"], 0.5)        # before the intro: where it was
        self.assertAlmostEqual(moved[1]["start"], 66.25)      # after it: 5 s on
        self.assertEqual(SUB.write(base, []), [])
        self.assertFalse(os.path.isfile(base + ".srt"))


if __name__ == "__main__":
    unittest.main()
