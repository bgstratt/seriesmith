"""
Whether comfy-sdk is here (seriesmith/sdk.py), and the command that puts it in
this Python: said, never run (the Comfy Registry's rules: no node pack
installs Python packages at runtime).
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from seriesmith import sdk as SDK  # noqa: E402


class SdkTest(unittest.TestCase):
    def test_the_command_is_this_pythons_pip(self):
        cmd = SDK.command()
        self.assertEqual(cmd[:4], [sys.executable, "-m", "pip", "install"])
        self.assertEqual(cmd[-1], SDK.REQUIREMENT)

    def test_state_says_whether_it_is_here_and_how(self):
        with mock.patch.object(SDK, "have", lambda: False):
            st = SDK.state()
        self.assertEqual((st["status"], st["python"]), ("missing", sys.executable))
        self.assertIn(SDK.REQUIREMENT, st["command"])
        with mock.patch.object(SDK, "have", lambda: True):
            self.assertEqual(SDK.state()["status"], "ready")

    def test_it_installs_nothing(self):
        self.assertFalse(hasattr(SDK, "install"))
        self.assertFalse(hasattr(SDK, "ensure"))

    def test_the_requirement_is_the_one_manager_installs(self):
        root = os.path.dirname(HERE)
        with open(os.path.join(root, "requirements.txt"), encoding="utf-8") as fh:
            self.assertIn(SDK.REQUIREMENT, [ln.strip() for ln in fh])


if __name__ == "__main__":
    unittest.main()
