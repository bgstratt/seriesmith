"""
comfy-sdk put in when it's needed (seriesmith/sdk.py): only with a Comfy API
key, once, in the background, saying how it went. pip itself is stood in for:
no test installs anything.
"""
from __future__ import annotations

import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from seriesmith import sdk as SDK  # noqa: E402


class SdkTest(unittest.TestCase):
    def setUp(self):
        SDK.reset()
        self.addCleanup(SDK.reset)
        p = mock.patch.dict(os.environ, {"SERIESMITH_NO_AUTO_INSTALL": ""})
        p.start()
        self.addCleanup(p.stop)
        self.installed = False
        p = mock.patch.object(SDK, "have", lambda: self.installed)
        p.start()
        self.addCleanup(p.stop)
        self.ran = []

    def pip(self, code=0, out="", installs=True):
        def run(cmd):
            self.ran.append(cmd)
            if code == 0 and installs:
                self.installed = True
            return code, out
        return run

    def test_the_command_is_this_pythons_pip(self):
        cmd = SDK.command()
        self.assertEqual(cmd[:4], [sys.executable, "-m", "pip", "install"])
        self.assertEqual(cmd[-1], SDK.REQUIREMENT)

    def test_switched_off(self):
        with mock.patch.dict(os.environ, {"SERIESMITH_NO_AUTO_INSTALL": "1"}):
            st = SDK.ensure(SimpleNamespace(api_key="k"), run=self.pip())
        self.assertEqual((st["status"], self.ran), ("missing", []))

    def test_nothing_without_a_key(self):
        st = SDK.ensure(SimpleNamespace(api_key=None), run=self.pip())
        self.assertEqual((st["status"], self.ran), ("missing", []))

    def test_nothing_when_it_is_already_there(self):
        self.installed = True
        st = SDK.ensure(SimpleNamespace(api_key="k"), run=self.pip())
        self.assertEqual((st["status"], self.ran), ("ready", []))

    def test_a_key_installs_it(self):
        done = []
        with mock.patch.object(SDK, "install", wraps=SDK.install) as inst:
            SDK.ensure(SimpleNamespace(api_key="k"), run=self.pip(), on_done=done.append)
        inst.assert_called_once()
        # the background thread: wait for it
        for _ in range(200):
            if done:
                break
            import time
            time.sleep(0.01)
        self.assertEqual(done[0]["status"], "ready")
        self.assertEqual(len(self.ran), 1)
        self.assertEqual(SDK.state()["status"], "ready")

    def test_a_failed_install_says_why_and_waits_for_the_button(self):
        st = SDK.install(background=False, run=self.pip(1, "ERROR: no network\nlast line"))
        self.assertEqual(st["status"], "failed")
        self.assertIn("last line", st["error"])
        # saving the key again doesn't try again by itself
        st = SDK.ensure(SimpleNamespace(api_key="k"), run=self.pip())
        self.assertEqual((st["status"], len(self.ran)), ("failed", 1))
        # the Install button does
        st = SDK.install(background=False, run=self.pip())
        self.assertEqual((st["status"], len(self.ran)), ("ready", 2))

    def test_pip_succeeding_without_the_package_appearing_is_a_failure(self):
        st = SDK.install(background=False, run=self.pip(0, "odd", installs=False))
        self.assertEqual(st["status"], "failed")

    def test_asking_while_it_installs_does_nothing_more(self):
        import threading
        gate = threading.Event()

        def slow(cmd):
            self.ran.append(cmd)
            gate.wait(5)
            self.installed = True
            return 0, ""
        st = SDK.install(run=slow)
        self.assertEqual(st["status"], "installing")
        self.assertEqual(SDK.install(run=slow)["status"], "installing")
        gate.set()
        for _ in range(200):
            if SDK.state()["status"] != "installing":
                break
            import time
            time.sleep(0.01)
        self.assertEqual((SDK.state()["status"], len(self.ran)), ("ready", 1))


if __name__ == "__main__":
    unittest.main()
