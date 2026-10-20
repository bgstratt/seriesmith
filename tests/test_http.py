"""
backends.http_json: seriesmith's own JSON calls to Comfy's APIs (Router, its
catalog and schemas, Cloud's node list), one way, against a local server here.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from seriesmith import router_inspect as RI  # noqa: E402
from seriesmith.backends import HTTPFailure, http_json  # noqa: E402


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def answer(self, status, body, ctype="application/json"):
        data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/ok":
            self.answer(200, {"key": self.headers.get("X-API-Key")})
        elif self.path == "/text":
            self.answer(200, "<html>not json</html>", "text/html")
        elif self.path.startswith("/v2/models/acme/missing"):
            self.answer(404, {"error": "no such model"})
        else:
            self.answer(500, "it broke")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        self.answer(201, {"got": json.loads(self.rfile.read(n)),
                          "type": self.headers.get("Content-Type")})


class HttpJsonTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_get_with_a_header(self):
        self.assertEqual(http_json(self.base + "/ok", headers={"X-API-Key": "k1"}), {"key": "k1"})

    def test_post_sends_json(self):
        got = http_json(self.base + "/make", "POST", {"url": "u", "hash": "h"})
        self.assertEqual(got, {"got": {"url": "u", "hash": "h"}, "type": "application/json"})

    def test_an_error_status_carries_its_status_and_body(self):
        with self.assertRaises(HTTPFailure) as cm:
            http_json(self.base + "/broken")
        self.assertEqual((cm.exception.status, cm.exception.text), (500, "it broke"))

    def test_not_json_and_no_answer_come_as_they_are(self):
        with self.assertRaises(ValueError):
            http_json(self.base + "/text")
        with self.assertRaises((urllib.error.URLError, OSError)):
            http_json("http://127.0.0.1:9/nothing", timeout=3)

    def test_a_caller_says_it_in_its_own_words(self):
        with mock.patch.object(RI, "API_BASE", self.base):
            with self.assertRaises(RI.RouterInspectError) as cm:
                RI.fetch_schema("acme/missing", "k")
        self.assertEqual(str(cm.exception), "Router has no model acme/missing")


if __name__ == "__main__":
    unittest.main(verbosity=2)
