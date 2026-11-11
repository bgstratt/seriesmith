"""
H3's video VAE: every H3 target renders with the fp16 file when it is installed,
else the int8_convrot one (target.json `prefer`). Measured 2026-11-10 on an RTX 5090,
the same take latents decoded by both: int8 is 58-61 dB PSNR from fp16, decodes
~3 s faster at 1344x768 x 73 frames (10-13 s at a 1440p upscale) and takes 2.3 GB
less VRAM, but its gradients band a little (skin tones, zoomed in), so fp16 leads.
"""
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from seriesmith import targets as TG  # noqa: E402

FP16 = "minimax_h3_video_vae_fp16.safetensors"
INT8 = "minimax_h3_video_vae_int8_convrot.safetensors"
TARGETS = os.path.join(os.path.dirname(HERE), "seriesmith", "targets")


def h3_targets():
    for kind in sorted(os.listdir(TARGETS)):
        d = os.path.join(TARGETS, kind)
        if not os.path.isdir(d):
            continue
        for tid in sorted(os.listdir(d)):
            if os.path.isfile(os.path.join(d, tid, "target.json")):
                t = TG.load_target(tid, kind)
                spec = t.models.get("video_vae") or {}
                if spec.get("family") == "minimax-h3-video-vae":
                    yield t


class H3VaeTest(unittest.TestCase):
    def test_every_h3_target_prefers_fp16(self):
        found = list(h3_targets())
        self.assertGreaterEqual(len(found), 11)
        for t in found:
            for installed, using in (([FP16, INT8], FP16), ([FP16], FP16), ([INT8], INT8),
                                     (["minimax_h3_sol_vae_fp16.safetensors"], None)):
                got = TG.resolve_file(t, "video_vae", FP16, installed)
                self.assertEqual(got and got["using"], using, f"{t.id}: {installed}")


if __name__ == "__main__":
    unittest.main()
