"""nle_xml: a cut as FCP7 XML, checked by parsing it back."""
from __future__ import annotations

import os
import sys
import unittest
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from seriesmith import nle_xml as NX  # noqa: E402


def clip(name: str, used: int, in_: int = 0, frames: int | None = None, **kw) -> dict:
    path = os.path.join(HERE, "My Show", f"{name}.mp4")
    c = {"name": name, "path": path, "frames": frames or in_ + used + 10, "fps": 24.0,
         "size": (64, 64), "in": in_, "used": used, "dissolve_in": 0, "fade_in": 0,
         "fade_out": 0, "marker": None,
         "audio": {"path": path, "channels": 2, "frames": frames or in_ + used + 10,
                   "at": -in_, "gain": 1.0}}
    c.update(kw)
    return c


def parse(text: str) -> ET.Element:
    return ET.fromstring(text.split("\n", 2)[2])


def items(track: ET.Element, tag: str = "clipitem") -> list[dict]:
    return [{k: int(e.findtext(k)) for k in ("start", "end", "in", "out") if e.find(k) is not None}
            | {"name": e.findtext("name"), "align": e.findtext("alignment")}
            for e in track.findall(tag)]


class WriteTest(unittest.TestCase):
    def doc(self, clips, fps=24.0, recording=None) -> ET.Element:
        return parse(NX.write("ep01 (final)", fps, (64, 64), clips, recording))

    def tracks(self, x: ET.Element) -> tuple[ET.Element, list[ET.Element]]:
        media = x.find("sequence/media")
        return media.find("video/track"), media.findall("audio/track")

    def test_clips_back_to_back_with_their_handles(self):
        x = self.doc([clip("sh010 t01", 56), clip("sh020 t02", 17, in_=3)])
        self.assertEqual(x.tag, "xmeml")
        self.assertEqual(x.findtext("sequence/duration"), "73")
        v1, (a1, a2) = self.tracks(x)
        got = items(v1)
        self.assertEqual([(g["start"], g["end"], g["in"], g["out"]) for g in got],
                         [(0, 56, 0, 56), (56, 73, 3, 20)])
        # the sound mirrors the picture, both channels, linked to it
        self.assertEqual([(g["start"], g["end"], g["in"], g["out"]) for g in items(a1)],
                         [(0, 56, 0, 56), (56, 73, 3, 20)])
        self.assertEqual(len(items(a2)), 2)
        self.assertEqual(len(v1.find("clipitem").findall("link")), 3)

    def test_each_file_defined_once(self):
        x = self.doc([clip("sh010 t01", 20)])
        files = x.findall(".//file")
        self.assertEqual(len(files), 3)                 # V1, A1, A2
        self.assertIsNotNone(files[0].find("pathurl"))
        self.assertIsNone(files[1].find("pathurl"))
        self.assertEqual({f.get("id") for f in files}, {"file-1"})

    def test_a_dissolve_is_centred_on_the_join(self):
        x = self.doc([clip("a", 56), clip("b", 22, dissolve_in=8)])
        v1, (a1, _) = self.tracks(x)
        a, b = items(v1)
        # the cut is 8 frames shorter; the edit at the dissolve's middle
        self.assertEqual(x.findtext("sequence/duration"), str(56 + 22 - 8))
        self.assertEqual((a["end"], a["out"]), (52, 52))
        self.assertEqual((b["start"], b["in"]), (52, 4))
        (t,) = items(v1, "transitionitem")
        self.assertEqual((t["start"], t["end"], t["align"]), (48, 56, "center"))
        self.assertEqual(len(a1.findall("transitionitem")), 1)
        kids = [e.tag for e in v1]
        self.assertEqual(kids, ["clipitem", "transitionitem", "clipitem"])

    def test_fades_from_and_to_black(self):
        x = self.doc([clip("a", 30, fade_in=10), clip("b", 20, fade_out=6)])
        v1, _ = self.tracks(x)
        ts = items(v1, "transitionitem")
        self.assertEqual([(t["start"], t["end"], t["align"]) for t in ts],
                         [(0, 10, "start-black"), (44, 50, "end-black")])
        self.assertEqual([e.tag for e in v1][:2], ["transitionitem", "clipitem"])

    def test_an_audio_source_from_another_file(self):
        other = os.path.join(HERE, "line.wav")
        x = self.doc([clip("a", 30, audio={"path": other, "channels": 1, "frames": 12,
                                           "at": 5, "gain": 0.5})])
        v1, (a1, a2) = self.tracks(x)
        (a,) = items(a1)
        self.assertEqual((a["start"], a["end"], a["in"], a["out"]), (5, 17, 0, 12))
        self.assertEqual(items(a2), [])                 # mono: A1 alone
        self.assertEqual(v1.find("clipitem").findall("link"), [])
        self.assertEqual(a1.findtext("clipitem/filter/effect/parameter/value"), "0.5")

    def test_no_sound(self):
        x = self.doc([clip("a", 30, audio=None)])
        _, (a1, a2) = self.tracks(x)
        self.assertEqual((items(a1), items(a2)), ([], []))

    def test_the_recording_on_a3(self):
        rec = os.path.join(HERE, "dialogue.wav")
        x = self.doc([clip("a", 30)], recording={"path": rec, "channels": 2, "frames": 500,
                                                 "at": -48})
        _, tracks = self.tracks(x)
        self.assertEqual(len(tracks), 4)
        (r,) = items(tracks[2])
        self.assertEqual((r["start"], r["end"], r["in"], r["out"]), (0, 30, 48, 78))

    def test_rates(self):
        self.assertEqual(NX.rate(23.976), (24, True))
        self.assertEqual(NX.rate(29.97), (30, True))
        self.assertEqual(NX.rate(25.0), (25, False))
        self.assertEqual(NX.rate(16.0), (16, False))
        x = self.doc([clip("a", 30)], fps=23.976)
        self.assertEqual(x.findtext("sequence/rate/ntsc"), "TRUE")

    def test_a_clip_at_another_rate_keeps_its_own(self):
        x = self.doc([clip("a", 30, fps=16.0)])
        f = x.find(".//file")
        self.assertEqual(f.findtext("rate/timebase"), "16")
        self.assertEqual(x.findtext(".//clipitem/rate/timebase"), "24")

    def test_paths_are_percent_encoded(self):
        url = NX.pathurl(os.path.join(HERE, "My Show", "sh010.mp4"))
        self.assertTrue(url.startswith("file://localhost/"))
        self.assertIn("My%20Show/sh010.mp4", url)
        self.assertNotIn("\\", url)
        if os.name == "nt":
            self.assertRegex(url, r"^file://localhost/[A-Za-z]%3a/")

    def test_a_sequence_marker(self):
        x = self.doc([clip("a", 30, marker="ms01"), clip("b", 20, marker="ms02")])
        ms = x.findall("sequence/marker")
        self.assertEqual([(m.findtext("name"), m.findtext("in")) for m in ms],
                         [("ms01", "0"), ("ms02", "30")])


if __name__ == "__main__":
    unittest.main()
