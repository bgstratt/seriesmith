"""
H3's video VAE: every H3 target renders with the int8_convrot file when it is
installed, else the fp16 one (target.json `prefer`). Measured 2026-11-10 on an
RTX 5090, the same take latents decoded by both: int8 matches fp16 at 58-60 dB
PSNR, decodes ~3 s faster at 1344x768 x 73 frames and takes 2.3 GB less VRAM.
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
    def test_every_h3_target_prefers_int8(self):
        found = list(h3_targets())
        self.assertGreaterEqual(len(found), 11)
        for t in found:
            for installed, using in (([FP16, INT8], INT8), ([FP16], FP16), ([INT8], INT8),
                                     (["minimax_h3_sol_vae_fp16.safetensors"], None)):
                got = TG.resolve_file(t, "video_vae", FP16, installed)
                self.assertEqual(got and got["using"], using, f"{t.id}: {installed}")


if __name__ == "__main__":
    unittest.main()
