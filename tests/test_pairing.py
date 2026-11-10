"""
Another device pairs once, with a code from Settings on the PC (seriesmith/server/pairing.py):
the PC is always answered; a laptop gets the page and the pairing routes until it's paired,
then everything, until it's removed.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest import mock

try:
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer
except ImportError as exc:                               # pragma: no cover
    raise unittest.SkipTest(f"the server needs aiohttp: {exc}")

from seriesmith.server import pairing as PR

LAPTOP = "192.168.1.20"


class PairingTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.p = PR.Pairing(os.path.join(tmp.name, "devices.json"))

    def test_a_code_pairs_one_device(self):
        code = self.p.new_code()["code"]
        self.assertRegex(code, r"^\d{6}$")
        token = self.p.pair(code, "Laptop", LAPTOP)
        self.assertTrue(self.p.known(token))
        self.assertFalse(self.p.known(token + "x"))
        self.assertFalse(self.p.known(None))
        with self.assertRaises(PR.PairError):                # used
            self.p.pair(code, "Another")
        (d,) = self.p.devices()
        self.assertEqual((d["name"], d["address"]), ("Laptop", LAPTOP))
        with open(self.p.path, encoding="utf-8") as f:
            self.assertNotIn(token, f.read())               # its hash only

    def test_five_tries(self):
        code = self.p.new_code()["code"]
        wrong = "000000" if code != "000000" else "111111"
        for _ in range(PR.CODE_TRIES):
            with self.assertRaises(PR.PairError):
                self.p.pair(wrong)
        with self.assertRaises(PR.PairError):                # gone, the right one too
            self.p.pair(code)

    def test_a_code_runs_out(self):
        code = self.p.new_code()["code"]
        self.p.code["expires"] = time.time() - 1
        with self.assertRaises(PR.PairError):
            self.p.pair(code)

    def test_removed(self):
        token = self.p.pair(self.p.new_code()["code"], "Phone")
        (d,) = self.p.devices()
        self.assertTrue(self.p.remove(d["id"]))
        self.assertFalse(self.p.known(token))
        self.assertFalse(self.p.remove(d["id"]))

    def test_who_must_pair(self):
        def req(remote, path, cookie=None):
            return SimpleNamespace(remote=remote, path=path,
                                   cookies={PR.COOKIE: cookie} if cookie else {})
        with mock.patch.object(PR, "pairing", return_value=self.p):
            self.assertFalse(PR.refused(req("127.0.0.1", "/seriesmith/episodes")))
            self.assertFalse(PR.refused(req("::1", "/ws")))
            self.assertTrue(PR.refused(req(LAPTOP, "/seriesmith/episodes")))
            self.assertTrue(PR.refused(req(LAPTOP, "/api/seriesmith/settings")))
            self.assertTrue(PR.refused(req(LAPTOP, "/ws")))
            for open_ in ("/", "/assets/index-abc.js", "/seriesmith/pair", "/api/seriesmith/pair"):
                self.assertFalse(PR.refused(req(LAPTOP, open_)), open_)
            token = self.p.pair(self.p.new_code()["code"])
            self.assertFalse(PR.refused(req(LAPTOP, "/seriesmith/episodes", token)))


class RoutesTest(unittest.TestCase):
    """The routes and the gate on an app, a request's address from X-Test-Remote."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        p = mock.patch.object(PR, "pairing", return_value=PR.Pairing(os.path.join(tmp.name, "d.json")))
        p.start()
        self.addCleanup(p.stop)

    def run_app(self, body):
        @web.middleware
        async def as_remote(request, handler):
            request = request.clone(remote=request.headers.get("X-Test-Remote", "127.0.0.1"))
            if PR.refused(request):
                return PR.refusal()
            return await handler(request)

        async def episodes(request):
            return web.json_response({"episodes": []})

        app = web.Application(middlewares=[as_remote])
        for m, path, view in PR.routes():
            app.router.add_route(m, path, view)
        app.router.add_get("/seriesmith/episodes", episodes)

        async def go():
            async with TestClient(TestServer(app)) as client:
                await body(client)
        asyncio.run(go())

    def test_a_laptop_pairs(self):
        laptop = {"X-Test-Remote": LAPTOP}

        async def body(client):
            r = await client.get("/seriesmith/episodes", headers=laptop)
            self.assertEqual(r.status, 401)
            self.assertTrue((await r.json())["pair"])
            self.assertEqual((await (await client.get("/seriesmith/pair", headers=laptop)).json()),
                             {"local": False, "paired": False})
            # the laptop can't make a code; the PC can
            self.assertEqual((await client.post("/seriesmith/pair/code", headers=laptop)).status, 401)
            code = (await (await client.post("/seriesmith/pair/code")).json())["code"]
            bad = await client.post("/seriesmith/pair", json={"code": "x"}, headers=laptop)
            self.assertEqual(bad.status, 403)
            r = await client.post("/seriesmith/pair", json={"code": code, "name": "Laptop"},
                                  headers=laptop)
            self.assertEqual(r.status, 200)
            cookie = r.cookies[PR.COOKIE]
            self.assertTrue(cookie["httponly"])
            self.assertEqual(cookie["samesite"], "Strict")
            self.assertEqual((await client.get("/seriesmith/episodes", headers=laptop)).status, 200)
            # the PC sees it, the laptop doesn't get the list; removed, it's out
            self.assertEqual((await client.get("/seriesmith/devices", headers=laptop)).status, 403)
            (d,) = (await (await client.get("/seriesmith/devices")).json())["devices"]
            self.assertEqual(d["name"], "Laptop")
            await client.post("/seriesmith/devices/remove", json={"id": d["id"]})
            self.assertEqual((await client.get("/seriesmith/episodes", headers=laptop)).status, 401)
        self.run_app(body)

    def test_this_pc_never_pairs(self):
        async def body(client):
            self.assertEqual((await client.get("/seriesmith/episodes")).status, 200)
            self.assertEqual((await (await client.get("/seriesmith/pair")).json()),
                             {"local": True, "paired": True})
        self.run_app(body)


if __name__ == "__main__":
    unittest.main()
