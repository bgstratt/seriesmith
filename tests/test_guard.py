"""
Which requests `seriesmith serve` answers (seriesmith/server/guard.py): the editor's own
page and programs, never another web page open in the same browser. The page from a
laptop on the network (an address, a machine name, a Tailscale name) is the server's own.
"""
from __future__ import annotations

import asyncio
import os
import sys
import unittest

try:
    from aiohttp.test_utils import TestClient, TestServer
except ImportError as exc:                               # pragma: no cover
    raise unittest.SkipTest(f"the server needs aiohttp: {exc}")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from seriesmith.server import guard as G  # noqa: E402
import test_server  # noqa: E402  (by module: its tests aren't collected twice)
from seriesmith.server import standalone  # noqa: E402


def refused(host, origin=None, site=None, local_only=True, method="POST", extra=None):
    return G.refused(method, host, origin, site, local_only, extra or set())


class RulesTest(unittest.TestCase):
    def test_the_editors_own_page(self):
        self.assertIsNone(refused("127.0.0.1:8190", "http://127.0.0.1:8190"))
        self.assertIsNone(refused("localhost:8190", "http://localhost:8190"))
        self.assertIsNone(refused("[::1]:8190", "http://[::1]:8190"))

    def test_programs_send_no_origin(self):
        self.assertIsNone(refused("127.0.0.1:8190"))
        self.assertIsNone(refused(None))

    def test_another_page_is_refused(self):
        self.assertIn("another site", refused("127.0.0.1:8190", "https://evil.example"))
        self.assertIn("another site", refused("127.0.0.1:8190", "http://127.0.0.1:9999"))
        self.assertIsNotNone(refused("127.0.0.1:8190", "null"))
        self.assertIsNotNone(refused("127.0.0.1:8190", site="cross-site", method="GET"))
        self.assertIsNone(refused("127.0.0.1:8190", site="same-origin", method="GET"))

    def test_dns_rebinding_on_this_machine_only(self):
        # evil.example resolving to 127.0.0.1: the page and the server share the name
        why = refused("evil.example:8190", "http://evil.example:8190")
        self.assertIn("this machine only", why)
        self.assertIsNotNone(refused("192.168.1.20:8190", "http://192.168.1.20:8190"))

    def test_on_the_network_a_laptop_and_tailscale(self):
        for host in ("192.168.1.20:8190", "100.101.102.103:8190", "desktop:8190",
                     "desktop.tail1234.ts.net:8190", "studio.local:8190", "[fd7a::1]:8190"):
            self.assertIsNone(refused(host, f"http://{host}", local_only=False), host)
        # a page elsewhere is still refused, and a name that isn't a local one needs --allow-host
        self.assertIsNotNone(refused("192.168.1.20:8190", "https://evil.example", local_only=False))
        self.assertIn("--allow-host", refused("studio.example.com:8190", local_only=False))
        self.assertIsNone(refused("studio.example.com:8190", local_only=False,
                                  extra={"studio.example.com"}))

    def test_allowed_hosts_from_the_environment(self):
        os.environ[G.ENV_HOSTS] = "Studio.Example.com, other.example"
        self.addCleanup(os.environ.pop, G.ENV_HOSTS, None)
        self.assertEqual(G.allowed_hosts(["x.example"]),
                         {"studio.example.com", "other.example", "x.example"})


class ServerTest(unittest.TestCase):
    """The guard on the running app: a post, a read and the live connection (test_server's
    episode and app, not its tests)."""
    setUp = test_server.StandaloneTest.setUp
    run_app = test_server.StandaloneTest.run_app

    def test_another_page_gets_nothing(self):
        async def body(client, app):
            own = f"http://{client.host}:{client.port}"
            out = {}
            r = await client.post("/seriesmith/source/check", json={"ep": self.ep},
                                  headers={"Origin": "https://evil.example"})
            out["post"] = r.status
            r = await client.get("/seriesmith/config", headers={"Origin": "https://evil.example"})
            out["get"] = r.status
            r = await client.get("/seriesmith/config", headers={"Sec-Fetch-Site": "cross-site"})
            out["cross-site"] = r.status
            r = await client.get("/seriesmith/config", headers={"Origin": own})
            out["own"] = r.status
            # a text/plain body: what another page can post without asking the browser
            r = await client.post("/seriesmith/source/check", data=b'{"ep": "x"}',
                                  headers={"Content-Type": "text/plain"})
            out["text"] = r.status
            r = await client.get("/seriesmith/config", headers={"Host": "evil.example"})
            out["rebound"] = r.status
            try:
                ws = await client.ws_connect("/ws", headers={"Origin": "https://evil.example"})
                await ws.close()
                out["ws"] = 101
            except Exception as e:                       # noqa: BLE001  refused at the handshake
                out["ws"] = getattr(e, "status", 0)
            ws = await client.ws_connect("/ws", headers={"Origin": own})
            await ws.close()
            return out
        out = self.run_app(body)
        self.assertEqual(out, {"post": 403, "get": 403, "cross-site": 403, "own": 200,
                               "text": 415, "rebound": 403, "ws": 403})

    def test_on_the_network_the_laptops_page_answers(self):
        async def go():
            app = standalone.make_app([self.shows], self.settings, host="0.0.0.0")
            async with TestClient(TestServer(app)) as client:
                h = {"Host": "desktop.tail1234.ts.net:8190",
                     "Origin": "http://desktop.tail1234.ts.net:8190"}
                ok = (await client.get("/seriesmith/config", headers=h)).status
                bad = (await client.get("/seriesmith/config",
                                        headers={**h, "Origin": "https://evil.example"})).status
                return ok, bad
        self.assertEqual(asyncio.run(go()), (200, 403))


class InComfyUITest(unittest.TestCase):
    """Inside ComfyUI each route checks the Origin itself (guarded); the Host is ComfyUI's."""

    def test_a_route_refuses_another_page(self):
        from aiohttp import web

        async def view(request):
            return web.json_response({"ok": True})

        async def go():
            app = web.Application()
            app.router.add_post("/seriesmith/x", G.guarded(view))
            async with TestClient(TestServer(app)) as client:
                own = f"http://{client.host}:{client.port}"
                return [(await client.post("/seriesmith/x", headers=h)).status for h in (
                    {"Origin": own},
                    {"Origin": "https://evil.example"},
                    {"Sec-Fetch-Site": "cross-site"},
                    {},                                              # a program
                    {"Host": "comfy.example:8188", "Origin": "http://comfy.example:8188"},
                )]
        self.assertEqual(asyncio.run(go()), [200, 403, 403, 200, 200])


if __name__ == "__main__":
    unittest.main()
