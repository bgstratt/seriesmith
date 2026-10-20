"""
seriesmith/ff's shared asks: ffprobe's JSON (probe_json) and framemd5s of a
stretch of picture (frame_md5s), which assemble, publish, finish and peaks each
ran their own way.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from seriesmith import ff as FF  # noqa: E402

HAVE = FF.have("ffmpeg") and FF.have("ffprobe")


@unittest.skipUnless(HAVE, "needs ffmpeg and ffprobe")
class FFTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.clip = os.path.join(cls._tmp.name, "c.mp4")
        subprocess.run([*FF.tool("ffmpeg"), "-y", "-v", "error", "-f", "lavfi", "-i",
                        "testsrc=size=64x48:rate=24", "-frames:v", "12", "-c:v", "libx264",
                        "-preset", "ultrafast", "-pix_fmt", "yuv420p", cls.clip], check=True)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_probe_json(self):
        d = FF.probe_json(self.clip, "-show_entries", "stream=codec_type,width,nb_frames")
        v = d["streams"][0]
        self.assertEqual((v["codec_type"], v["width"], v["nb_frames"]), ("video", 64, "12"))

    def test_probe_json_says_why_it_failed(self):
        bad = os.path.join(self._tmp.name, "bad.mp4")
        with open(bad, "wb") as fh:
            fh.write(b"not a video")
        with self.assertRaises(FF.FFError) as cm:
            FF.probe_json(bad, "-show_streams")
        self.assertTrue(str(cm.exception))

    def test_no_ffprobe_is_file_not_found(self):
        with mock.patch.object(FF, "tool", lambda name: ["no-such-ffprobe-here"]):
            with self.assertRaises(FileNotFoundError):
                FF.probe_json(self.clip, "-show_streams")

    def test_frame_md5s(self):
        every = FF.frame_md5s(self.clip, 0, 12)
        self.assertEqual(len(every), 12)
        self.assertEqual(len(set(every)), 12)                 # testsrc changes every frame
        # from frame 4 (half a frame early, as the callers seek)
        self.assertEqual(FF.frame_md5s(self.clip, 3.5 / 24, 3), every[4:7])

    def test_frame_md5s_that_dont_decode(self):
        with self.assertRaises(FF.FFError):
            FF.frame_md5s(os.path.join(self._tmp.name, "missing.mp4"), 0, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
