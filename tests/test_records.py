"""
A job's record as it goes (takes.record_queued / record_failed), the same for
a take, a ref, an upscale, a post and a finish; and settings_hash, which records
store to tell later whether a recipe changed, so its value must never move.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from seriesmith import post as P  # noqa: E402
from seriesmith import takes as T  # noqa: E402
from seriesmith import upscale as U  # noqa: E402


class RecordTest(unittest.TestCase):
    def test_queued_then_failed(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "sh010_t01.json")
            T.write_json(p, {"status": "queued", "seed": 7})
            self.assertEqual(T.record_queued(p, "pid-1")["comfy_prompt_id"], "pid-1")
            got = T.record_failed(p, "ComfyUI said no")
            self.assertEqual((got["status"], got["save_notes"], got["seed"], got["comfy_prompt_id"]),
                             ("failed", "ComfyUI said no", 7, "pid-1"))
            self.assertTrue(got["finished"])
            self.assertEqual(T.read_json(p), got)

    def test_settings_hash_never_moves(self):
        s = {"enhance": "seedvr2", "blur": 0.3, "z": [1, 2], "a": None}
        self.assertEqual(T.settings_hash(s), "3eedc5b4c275")      # what records hold
        self.assertIs(U.settings_hash, T.settings_hash)
        self.assertIs(P.settings_hash, T.settings_hash)


if __name__ == "__main__":
    unittest.main(verbosity=2)
