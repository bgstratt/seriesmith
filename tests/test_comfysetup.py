"""
comfysetup: the ways to get ComfyUI on each system, and finding one that runs (a fake
ComfyUI's /system_stats; an address nothing answers at, refused at once).
"""
from __future__ import annotations

import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from seriesmith import comfysetup as CS  # noqa: E402


class FakeComfy:
    def __init__(self, body: dict):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                data = json.dumps(body).encode()
                self.send_response(200 if self.path == "/system_stats" else 404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(data)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class GuideTest(unittest.TestCase):
    def test_each_system_its_own_ways_best_first(self):
        ids = {p: [w["id"] for w in CS.guide(p)] for p in ("win32", "darwin", "linux")}
        self.assertEqual(ids, {"win32": ["desktop", "portable", "manual"],
                               "darwin": ["desktop", "cli", "manual"],
                               "linux": ["cli", "desktop", "manual"]})
        for p in ids:
            for w in CS.guide(p):
                self.assertTrue(w["url"].startswith("https://"), w)
                self.assertTrue(w["steps"] and w["for"] and w["label"], w)
                # each ends by sending them back to find it
                self.assertIn("Find my ComfyUI", w["steps"][-1])
        portable = next(w for w in CS.guide("win32") if w["id"] == "portable")
        self.assertEqual(portable["url"], CS.RELEASES + "ComfyUI_windows_portable_nvidia.7z")
        self.assertIn("7-Zip", " ".join(portable["steps"]))

    def test_the_address_in_settings_first_then_the_usual_ports(self):
        self.assertEqual(CS.candidates("http://127.0.0.1:8188/"),
                         ["http://127.0.0.1:8188", "http://127.0.0.1:8000"])
        self.assertEqual(CS.candidates("http://pc:9000"),
                         ["http://pc:9000", "http://127.0.0.1:8188", "http://127.0.0.1:8000"])
        self.assertEqual(CS.candidates(None), ["http://127.0.0.1:8188", "http://127.0.0.1:8000"])


class FindTest(unittest.TestCase):
    def test_the_first_that_answers_as_a_comfyui(self):
        comfy = FakeComfy({"system": {"comfyui_version": "0.44.0"}})
        other = FakeComfy({"not": "comfyui"})
        self.addCleanup(comfy.close)
        self.addCleanup(other.close)
        got = CS.find(["http://127.0.0.1:0", other.url, comfy.url])
        self.assertEqual(got["found"], comfy.url)
        self.assertEqual([(t["url"], t["ok"], t["version"]) for t in got["tried"]],
                         [("http://127.0.0.1:0", False, None), (other.url, False, None),
                          (comfy.url, True, "0.44.0")])

    def test_none_running(self):
        got = CS.find(["http://127.0.0.1:0"])
        self.assertIsNone(got["found"])


if __name__ == "__main__":
    unittest.main()
