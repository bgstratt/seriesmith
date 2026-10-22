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
        self.settings = Settings(comfyui_url="http://127.0.0.1:0")

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

    def test_the_settings_window_saves_and_uses_them(self):
        from unittest import mock
        env = {k: v for k, v in os.environ.items()
               if k not in ("COMFY_API_KEY", "SERIESMITH_CLOUD_URL", "SERIESMITH_LOCAL_URL",
                            "SERIESMITH_COMFYUI_URL")}

        async def body(client, app):
            got = await (await client.get("/seriesmith/settings")).json()
            put = await client.put("/seriesmith/settings", json={
                "api_key": "comfyui-test", "cloud_url": "https://cloud.example.com/",
                "deployments": {"minimax_h3_ref2va": "https://h3.example.com"}})
            saved = await put.json()
            with_key = sorted(app["backends"])
            bad = await client.put("/seriesmith/settings", json={"cloud_url": "ftp://x"})
            off = await (await client.put("/seriesmith/settings", json={"api_key": None})).json()
            return got, put.status, saved, with_key, bad.status, off, sorted(app["backends"])

        with mock.patch.dict(os.environ, env, clear=True):
            got, status, saved, with_key, bad, off, after = self.run_app(body)
        self.assertEqual(got["settings"]["api_key"], None)
        self.assertEqual(got["from_env"], {})
        self.assertEqual(status, 200)
        self.assertEqual(saved["settings"]["api_key"], "set")
        self.assertEqual(saved["settings"]["cloud_url"], "https://cloud.example.com")
        self.assertEqual(with_key, ["cloud", "deployment:minimax_h3_ref2va", "local", "router"])
        self.assertEqual(bad, 400)
        self.assertEqual(off["settings"]["api_key"], None)
        self.assertEqual(after, ["deployment:minimax_h3_ref2va", "local"])
        with open(os.environ["SERIESMITH_SETTINGS"], encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), {"cloud_url": "https://cloud.example.com",
                                             "deployments": {"minimax_h3_ref2va": "https://h3.example.com"}})

    def test_every_route_answers_under_api_too(self):
        """As inside ComfyUI: the queue's, Settings' and Features' routes were
        left out (/api/seriesmith/jobs was a 404 here, a 200 there)."""
        from seriesmith.server import features_views as FV
        from seriesmith.server import queue_views as QV

        async def body(client, app):
            have = {(r.method, r.resource.canonical) for r in app.router.routes()}
            jobs = await client.get("/api/seriesmith/jobs")
            return have, jobs.status
        have, jobs = self.run_app(body)
        self.assertEqual(jobs, 200)
        for method, path in QV.PATHS + FV.PATHS + [(m, p) for m, p, _f, _t in A.ROUTES]:
            self.assertIn((method, path), have)
            self.assertIn((method, "/api" + path), have)

    def test_a_slow_cancel_does_not_hold_up_the_editor(self):
        """Cancelling a running job asks its backend to stop it (a network call);
        that runs off the event loop, so other requests answer meanwhile."""
        import threading
        import time
        from seriesmith.queue import Job
        release = threading.Event()

        def work(job, report):
            release.wait(10)
            return "canceled"

        def slow_cancel():
            time.sleep(1.5)                     # a backend that's slow to answer
            release.set()

        async def body(client, app):
            job = Job(kind="render", lane="local", title="t", work=work)
            job.cancel_run = slow_cancel
            app["queue"].submit(job)
            for _ in range(50):
                if job.status == "running":
                    break
                await asyncio.sleep(0.05)
            self.assertEqual(job.status, "running")
            # the client shares the server's event loop: a blocked loop shows as
            # this whole stretch taking the cancel's 1.5 s
            t = time.monotonic()
            cancel = asyncio.ensure_future(client.post("/seriesmith/jobs/cancel",
                                                       json={"id": job.id}))
            await asyncio.sleep(0.2)            # the cancel is under way
            listed = await client.get("/seriesmith/jobs")
            took = time.monotonic() - t
            return took, listed.status, (await cancel).status
        took, listed, cancelled = self.run_app(body)
        self.assertEqual((listed, cancelled), (200, 200))
        self.assertLess(took, 1.0)

    def test_a_save_refreshes_every_setting(self):
        """Every field a PUT saves is what the reply and GET /settings say at once,
        not after a restart (enabled_drafts and target_limits were left stale)."""
        from seriesmith.settings import FIELDS
        changes = {"paid_limit": 0, "enabled_drafts": ["some_draft"],
                   "target_limits": {"ltx2": {"duration": {"max": 8}}}, "local_via": "proxy",
                   "default_targets": {"video": "ltx2"}}

        async def body(client, app):
            put = await (await client.put("/seriesmith/settings", json=changes)).json()
            got = await (await client.get("/seriesmith/settings")).json()
            return put, got
        put, got = self.run_app(body)
        for reply in (put, got):
            for k, v in changes.items():
                self.assertEqual(reply["settings"][k], v, k)
        self.assertLessEqual(set(FIELDS), set(put["settings"]))

    def test_stop_and_restart_from_this_machine_only(self):
        """POST /seriesmith/server/stop: the editor's Stop / Restart. Restart's
        exit code (3) is what run_seriesmith*.bat starts it again on."""
        from unittest import mock
        stops = []

        async def body(client, app):
            with mock.patch.object(standalone, "_graceful_exit", lambda: stops.append(True)):
                r = await client.post("/seriesmith/server/stop", json={"restart": True})
                ok = (r.status, await r.json(), app["exit_code"])
                await asyncio.sleep(0.5)
            with mock.patch.object(standalone, "LOOPBACK", ()):
                far = (await client.post("/seriesmith/server/stop", json={})).status
            return ok, far
        (status, data, code), far = self.run_app(body)
        self.assertEqual((status, data, code), (200, {"ok": True, "restart": True}, standalone.RESTART))
        self.assertEqual(stops, [True])
        self.assertEqual(far, 403)

    def test_a_stop_closes_the_pages_connection(self):
        """The editor's live connection is closed as the server shuts down:
        left open, the stop waited on it (aiohttp's 60 s), then was killed."""
        async def body(client, app):
            ws = await client.ws_connect("/ws")
            await asyncio.sleep(0.05)
            await app.shutdown()
            await asyncio.wait_for(ws.receive(), 5)
            return ws.close_code
        self.assertEqual(self.run_app(body), 1001)

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
        self.assertTrue(comfyui.register(server, wait=0))
        # the API, the queue's own routes (Jobs, Render on, Settings, info) and
        # the Features window's four
        from seriesmith.server import features_views as FV
        from seriesmith.server import queue_views as QV
        self.assertEqual(len(added), len(A.ROUTES) + len(QV.PATHS) + len(FV.PATHS))
        self.assertEqual(sorted(added[len(A.ROUTES):]), sorted(QV.PATHS + FV.PATHS))
        self.assertIn(("GET", "/seriesmith/jobs"), added)
        self.assertIn(("PUT", "/seriesmith/settings"), added)
        self.assertNotIn(("POST", "/seriesmith/sdk/install"), added)
        # the same app as `seriesmith serve`: its queue, its own journal
        ctx = comfyui.start(server, wait=0)[0]()
        self.assertIsNotNone(ctx.runner)
        self.assertTrue(ctx.runner.queue.journal.endswith("queue-comfyui.json"))
        self.assertEqual(ctx.comfy_url, "http://127.0.0.1:8188")

    def test_it_stays_off_when_another_pack_serves_the_api(self):
        server, added = self.server(["/seriesmith/episodes"])
        with self.assertLogs("seriesmith", "WARNING"):
            self.assertFalse(comfyui.register(server, wait=0))
        self.assertEqual(added, [])

    def test_features_stay_when_the_queue_cant_start(self):
        """The Features window doesn't need the queue: it was dropped with it."""
        from unittest import mock
        server, added = self.server()
        with mock.patch.object(standalone, "start_queue", side_effect=RuntimeError("no")), \
                self.assertLogs("seriesmith", "WARNING"):
            self.assertTrue(comfyui.register(server, wait=0))
        paths = {p for _, p in added}
        self.assertIn("/seriesmith/features", paths)
        self.assertIn("/seriesmith/episodes", paths)
        self.assertNotIn("/seriesmith/jobs", paths)

    def test_a_clash_on_any_route_keeps_it_off(self):
        """Not only the API's: a queue or Features path another pack has too."""
        server, added = self.server(["/seriesmith/features"])
        with self.assertLogs("seriesmith", "WARNING"):
            self.assertFalse(comfyui.register(server, wait=0))
        self.assertEqual(added, [])

    def test_its_own_address(self):
        self.assertEqual(comfyui.base_url(SimpleNamespace(port=8188, address="0.0.0.0")),
                         "http://127.0.0.1:8188")


if __name__ == "__main__":
    unittest.main()
