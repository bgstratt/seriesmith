"""
The shot saver's wav (comfy_nodes/shot.py save_audio): a waveform that peaks
past full scale is scaled down whole, never flat-topped. Runs where torch is
(ComfyUI's Python); skipped elsewhere.
"""
from __future__ import annotations

import importlib.util
import math
import os
import shutil
import tempfile
import unittest
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
SHOT = os.path.join(os.path.dirname(HERE), "comfy_nodes", "shot.py")


def _have(*mods) -> bool:
    return all(importlib.util.find_spec(m) is not None for m in mods)


@unittest.skipUnless(_have("torch", "numpy"), "needs torch (ComfyUI's Python)")
class SaveAudioTest(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("seriesmith_shot_node", SHOT)
        self.shot = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.shot)
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)

    def _read(self, path):
        import numpy as np
        with wave.open(path) as w:
            self.assertEqual(w.getsampwidth(), 2)
            ch = w.getnchannels()
            a = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
        return a.reshape(-1, ch).T.astype("float64") / 32767.0

    def test_over_full_scale_is_scaled_not_clipped(self):
        import torch
        t = torch.arange(4800, dtype=torch.float32) / 48000.0
        sine = 1.4 * torch.sin(2 * math.pi * 440.0 * t)
        wav = torch.stack([sine, 0.5 * sine])[None]          # [B, C, T], left peaks at 1.4
        path = os.path.join(self.dir, "over.wav")
        down = self.shot.save_audio({"waveform": wav, "sample_rate": 48000}, path)
        self.assertAlmostEqual(down, -20 * math.log10(1.4), places=2)
        got = self._read(path)
        want = (wav[0] / 1.4).numpy()
        # the shape kept: every sample within 16-bit rounding, the peak at full scale
        self.assertLess(float(abs(got - want).max()), 1.0 / 32767.0 + 1e-9)
        self.assertGreater(float(abs(got[0]).max()), 0.999)
        # no flat top: never three full-scale samples in a row
        full = abs(got[0]) >= 32767 / 32767.0
        self.assertFalse(any(full[i] and full[i + 1] and full[i + 2] for i in range(len(full) - 2)))

    def test_in_range_is_untouched(self):
        import torch
        wav = torch.tensor([[0.0, 0.25, -0.5, 0.999, -1.0]])
        path = os.path.join(self.dir, "in.wav")
        self.assertEqual(self.shot.save_audio({"waveform": wav, "sample_rate": 44100}, path), 0.0)
        got = self._read(path)
        self.assertLess(float(abs(got - wav.numpy()).max()), 1.0 / 32767.0 + 1e-9)

    def test_nan_is_silence(self):
        import torch
        wav = torch.tensor([[0.5, float("nan"), -0.5]])
        path = os.path.join(self.dir, "nan.wav")
        self.assertEqual(self.shot.save_audio({"waveform": wav, "sample_rate": 44100}, path), 0.0)
        self.assertEqual(float(self._read(path)[0][1]), 0.0)


if __name__ == "__main__":
    unittest.main()
