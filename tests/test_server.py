"""
The editor's server (seriesmith/server): `seriesmith serve`'s app answers the
API at the paths ComfyUI serves it on (and under /api), serves the page, and
sends the API's events to the page's websocket; the ComfyUI host stays out of
the way when another pack already serves the API.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace

try:
    from aiohttp.test_utils import TestClient, TestServer
except ImportError as exc:                               # pragma: no cover
    raise unittest.SkipTest(f"the server needs aiohttp: {exc}")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from seriesmith import api as A  # noqa: E402
from seriesmith.server import comfyui, standalone  # noqa: E402
from seriesmith.settings import Settings  # noqa: E402
from test_render import FIXTURE, build_episode  # noqa: E402


class StandaloneTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.shows = os.path.join(self._tmp.name, "Shows")
        self.ep = os.path.join(self.shows, "ks01")
        os.makedirs(self.ep)
        shutil.copy(os.path.join(FIXTURE, "series.json"), self.ep)
        shutil.copy(os.path.join(FIXTURE, "script.md"), os.path.join(self.ep, "ks01.md"))
        build_episode(self.ep)
        os.environ["SERIESMITH_SETTINGS"] = os.path.join(self._tmp.name, "user", "settings.json")
        self.addCleanup(os.environ.pop, "SERIESMITH_SETTINGS", None)
        # no ComfyUI here: the relay keeps retrying quietly
        self.settings = Settings(comfyui_url="http://127.0.0.1:9")

    def run_app(self, body):
        async def go():
            app = standalone.make_app([self.shows], self.settings)
            async with TestClient(TestServer(app)) as client:
                return await body(client, app)
        return asyncio.run(go())

    def test_the_api_answers_on_both_paths(self):
        async def body(client, app):
            out = []
            for path in ("/seriesmith/episodes", "/api/seriesmith/episodes"):
                r = await client.get(path)
                out.append((r.status, await r.json()))
            return out
        for status, data in self.run_app(body):
            self.assertEqual(status, 200)
            self.assertEqual([e["name"] for e in data], ["ks01"])

    def test_the_root_given_on_the_command_line_counts(self):
        async def body(client, app):
            r = await client.get("/seriesmith/config")
            return await r.json()
        self.assertIn(os.path.abspath(self.shows), self.run_app(body)["roots"])

    def test_the_page_and_the_info(self):
        async def body(client, app):
            page = await client.get("/")
            info = await (await client.get("/seriesmith/info")).json()
            return page.status, info
        status, info = self.run_app(body)
        built = os.path.isfile(os.path.join(standalone.STATIC, "standalone.html"))
        self.assertEqual(status, 200 if built else 503)
        self.assertEqual(info["settings"]["api_key"], None)
        self.assertFalse(info["comfy_connected"])

    def test_the_apis_events_reach_the_page(self):
        async def body(client, app):
            ws = await client.ws_connect("/ws")
            await asyncio.sleep(0.05)
            app["events"].emit("seriesmith.take", {"shot": "sh010", "status": "ok"})
            msg = await asyncio.wait_for(ws.receive_str(), 5)
            await ws.close()
            return json.loads(msg)
        self.assertEqual(self.run_app(body),
                         {"type": "seriesmith.take", "data": {"shot": "sh010", "status": "ok"}})


class ComfyHostTest(unittest.TestCase):
    def server(self, have_paths=()):
        routes = [SimpleNamespace(path=p) for p in have_paths]
        added = []

        class Table(list):
            def route(self, method, path):
                def deco(view):
                    added.append((method, path))
                    return view
                return deco
        return SimpleNamespace(routes=Table(routes), port=8188, address="0.0.0.0",
                               send_sync=lambda e, d: None), added

    def setUp(self):
        comfyui.REGISTERED = False
        self.addCleanup(setattr, comfyui, "REGISTERED", False)

    def test_it_registers_every_route(self):
        server, added = self.server()
        self.assertTrue(comfyui.register(server))
        self.assertEqual(len(added), len(A.ROUTES))

    def test_it_stays_off_when_another_pack_serves_the_api(self):
        server, added = self.server(["/seriesmith/episodes"])
        with self.assertLogs("seriesmith", "WARNING"):
            self.assertFalse(comfyui.register(server))
        self.assertEqual(added, [])

    def test_its_own_address(self):
        self.assertEqual(comfyui.base_url(SimpleNamespace(port=8188, address="0.0.0.0")),
                         "http://127.0.0.1:8188")


if __name__ == "__main__":
    unittest.main()
