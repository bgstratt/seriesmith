"""A video whose first frame starts late (an imported clip's can: start_time one frame in)
reads back as the frames it has, no more: ffmpeg's default output timing filled the gap
with a copy of the first frame, so an upscale of such a take came out a frame long (59 ->
60) and a frame number read from it was one off. Both raw-frame readers (the node pack's
read_frames, the stills helper's frames) decode with passthrough timing."""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from seriesmith import ff as FF  # noqa: E402


def _have(*mods) -> bool:
    return all(importlib.util.find_spec(m) is not None for m in mods)


class LateStartTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        cls.mp4 = os.path.join(cls.dir, "late.mp4")
        # 30 frames at 24 fps, the first at 1/24 s, its sound from 0 (as the imported takes
        # that showed it: ffmpeg times its output from the sound's start)
        subprocess.run([*FF.tool("ffmpeg"), "-y", "-v", "error", "-f", "lavfi", "-i",
                        "testsrc=size=64x36:rate=24:duration=1.25", "-f", "lavfi", "-i",
                        "sine=frequency=440:duration=1.3", "-map", "0:v", "-map", "1:a",
                        "-vf", "setpts=PTS+1/(24*TB)", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", cls.mp4], check=True, timeout=60)
        s = FF.probe_json(cls.mp4, "-show_streams", "-select_streams", "v:0")["streams"][0]
        assert float(s["start_time"]) > 0.03, s

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, True)

    def test_the_stills_reader(self):
        from seriesmith.helpers import stills
        got = list(stills.frames(json.dumps(FF.tool("ffmpeg")), self.mp4, 64, 36))
        self.assertEqual(len(got), 30)

    @unittest.skipUnless(_have("torch", "numpy"), "needs torch (ComfyUI's Python)")
    def test_the_node_packs_reader(self):
        chain = importlib.import_module("comfy_nodes.chain")     # its imports are the package's
        self.assertEqual(int(chain.read_frames(self.mp4).shape[0]), 30)


if __name__ == "__main__":
    unittest.main()
