"""
The take's mp4 through PyAV (comfy_nodes/shot.py encode_av), the saver's way
when ffmpeg isn't on PATH: the same H.264, BT.709 tags, frame count and AAC as
the ffmpeg command. Runs where torch and PyAV are (ComfyUI's Python); skipped
elsewhere.
"""
from __future__ import annotations

import importlib.util
import math
import os
import shutil
import struct
import subprocess
import tempfile
import unittest
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
SHOT = os.path.join(os.path.dirname(HERE), "comfy_nodes", "shot.py")


def _have(*mods) -> bool:
    return all(importlib.util.find_spec(m) is not None for m in mods)


@unittest.skipUnless(_have("torch", "av", "numpy"), "needs torch and PyAV (ComfyUI's Python)")
class EncodeAvTest(unittest.TestCase):
    def test_a_take_mp4_without_ffmpeg(self):
        import torch
        spec = importlib.util.spec_from_file_location("seriesmith_shot_node", SHOT)
        shot = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(shot)
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        imgs = torch.zeros((29, 96, 160, 3))
        imgs[..., 0] = 1.0
        wav = os.path.join(d, "a.wav")
        with wave.open(wav, "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(48000)
            w.writeframes(b"".join(struct.pack("<hh", int(8000 * math.sin(i / 20)), 0)
                                   for i in range(48000 * 29 // 24)))
        mp4 = os.path.join(d, "t.mp4")
        shot.encode_av(imgs, mp4, 24, wav)
        import av
        with av.open(mp4) as c:
            v = c.streams.video[0]
            self.assertEqual((v.codec_context.name, v.width, v.height), ("h264", 160, 96))
            self.assertEqual(sum(1 for _ in c.decode(video=0)), 29)
        with av.open(mp4) as c:
            self.assertEqual(c.streams.audio[0].codec_context.name, "aac")
        if shutil.which("ffprobe"):
            tags = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                                   "-show_entries", "stream=color_range,color_space,"
                                   "color_primaries,color_transfer", "-of", "csv=p=0", mp4],
                                  capture_output=True, text=True).stdout.strip()
            self.assertEqual(tags, "tv,bt709,bt709,bt709")


if __name__ == "__main__":
    unittest.main()
