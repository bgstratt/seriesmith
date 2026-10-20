"""
seriesmith's queue (seriesmith/queue.py) and the editor rendering through it
(runner.Runner, api.post_render through the standalone server), on the fake
backend.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from seriesmith import takes as T  # noqa: E402
from seriesmith.backends.fake import FakeBackend  # noqa: E402
from seriesmith.queue import Job, Queue  # noqa: E402


def settle_queue_threads(timeout: float = 3.0) -> None:
    """Let the queue's workers (threads named seriesmith-<lane>) finish before a
    test's folder is deleted: a worker marks its job done, then rewrites the
    journal in that folder, and a cleanup racing the write fails with "the
    directory is not empty" (seen under the full suite's load). A worker that
    never ends (HoldRun) is waited on for what's left of `timeout`, no more."""
    import threading
    end = time.time() + timeout
    for t in [t for t in threading.enumerate() if t.name.startswith("seriesmith-")]:
        t.join(max(0.0, end - time.time()))


def wait_for(cond, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    raise AssertionError("timed out")


class Gate:
    """Work that waits until let go, so a test can see a job running."""

    def __init__(self):
        self.go = threading.Event()
        self.started = threading.Event()

    def work(self, status="succeeded"):
        def run(job, report):
            self.started.set()
            report(0.5, 4, 8, "half way")
            while not self.go.wait(0.01):
                if job.cancel_asked:
                    return "canceled"
            return status
        return run


class QueueTest(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.q = Queue(lambda e, d: self.events.append((e, d)))

    def job(self, work, lane="local", **kw):
        return self.q.submit(Job(kind="test", lane=lane, title=kw.pop("title", "a job"),
                                 work=work, **kw))

    def test_your_own_comfyui_runs_one_job_at_a_time(self):
        g = Gate()
        a = self.job(g.work(), title="a")
        b = self.job(g.work(), title="b")
        g.started.wait(5)
        self.assertEqual((a.status, b.status), ("running", "queued"))
        g.go.set()
        wait_for(lambda: b.status == "succeeded")
        self.assertEqual(a.status, "succeeded")

    def test_a_cloud_lane_runs_several(self):
        g = Gate()
        jobs = [self.job(g.work(), lane="router") for _ in range(3)]
        wait_for(lambda: all(j.status == "running" for j in jobs))
        g.go.set()
        wait_for(lambda: all(j.status == "succeeded" for j in jobs))

    def test_cancel_a_waiting_job_and_a_running_one(self):
        g = Gate()
        undone = []
        a = self.job(g.work())
        b = self.job(g.work(), on_cancel=lambda j: undone.append(j.id))
        g.started.wait(5)
        self.q.cancel(b.id)
        self.assertEqual((b.status, undone), ("canceled", [b.id]))
        self.q.cancel(a.id)
        wait_for(lambda: a.status == "canceled")

    def test_a_cancel_asked_while_staging_stops_the_run_once_it_starts(self):
        """Cancel before the work has a run to stop (it's uploading, staging):
        the run is stopped as soon as it starts, not left to render to the end.
        Asked after it started: stopped then. Either way, once."""
        for early in (True, False):
            with self.subTest(early=early):
                staging, armed, stops = threading.Event(), threading.Event(), []

                def work(job, report):
                    staging.set()
                    if early:
                        wait_for(lambda: job.cancel_asked)        # still staging
                    self.q.arm_cancel(job, lambda: stops.append(1))
                    armed.set()
                    wait_for(lambda: job.cancel_asked)
                    return "canceled"
                j = self.job(work)
                staging.wait(5)
                if not early:
                    armed.wait(5)
                self.q.cancel(j.id)
                wait_for(lambda: j.status == "canceled")
                self.assertEqual(stops, [1])

    def test_move_and_pause(self):
        g = Gate()
        self.q.pause("local")
        a, b, c = (self.job(g.work(), title=t) for t in "abc")
        self.q.move(c.id, 0)
        self.assertEqual(self.q.list()["lanes"]["local"]["waiting"], [c.id, a.id, b.id])
        self.assertEqual(a.status, "queued")
        self.q.pause("local", False)
        wait_for(lambda: c.status == "running")
        g.go.set()
        wait_for(lambda: all(j.status == "succeeded" for j in (a, b, c)))
        with self.assertRaises(ValueError):
            self.q.move(a.id, 0)

    def test_a_failure_is_the_jobs_and_says_why(self):
        def boom(job, report):
            raise RuntimeError("CUDA out of memory")
        j = self.job(boom)
        wait_for(lambda: j.status == "failed")
        self.assertIn("CUDA out of memory", j.error)
        self.assertIn(("execution_error", {"prompt_id": j.id,
                                           "exception_message": j.error}), self.events)

    def test_retry_does_it_again(self):
        made = []

        def again():
            made.append(1)
            return Job(kind="test", lane="local", title="again", work=lambda j, r: "succeeded")
        j = self.job(lambda job, r: "failed", retry=again)
        wait_for(lambda: j.status == "failed")
        new = self.q.retry(j.id)
        wait_for(lambda: new.status == "succeeded")
        self.assertEqual(made, [1])

    def test_events_in_comfyuis_shapes_with_the_job_id(self):
        g = Gate()
        j = self.job(g.work())
        g.started.wait(5)
        g.go.set()
        wait_for(lambda: j.status == "succeeded")
        kinds = [e for e, d in self.events if isinstance(d, dict) and d.get("prompt_id") == j.id]
        self.assertEqual(kinds[0], "execution_start")
        self.assertIn("progress", kinds)
        self.assertEqual(kinds[-1], "execution_success")
        self.assertTrue(any(e == "seriesmith.job" and d["log"] == ["half way"]
                            for e, d in self.events))


class EditorRenderTest(unittest.TestCase):
    """The editor's Render, through `seriesmith serve`: the take goes on the
    queue and is rendered on its backend; its record says so."""

    def setUp(self):
        try:
            from aiohttp.test_utils import TestClient, TestServer  # noqa: F401
        except ImportError as e:                          # pragma: no cover
            self.skipTest(f"needs aiohttp: {e}")
        from test_render import FIXTURE, build_episode
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(settle_queue_threads)              # runs first: cleanups are LIFO
        self.shows = os.path.join(self._tmp.name, "Shows")
        self.ep = os.path.join(self.shows, "ks01")
        os.makedirs(self.ep)
        shutil.copy(os.path.join(FIXTURE, "series.json"), self.ep)
        shutil.copy(os.path.join(FIXTURE, "script.md"), os.path.join(self.ep, "ks01.md"))
        build_episode(self.ep)
        os.environ["SERIESMITH_SETTINGS"] = os.path.join(self._tmp.name, "user", "settings.json")
        self.addCleanup(os.environ.pop, "SERIESMITH_SETTINGS", None)
        self.addCleanup(setattr, T, "MANAGED", None)

    def test_render_from_the_editor_goes_through_the_queue(self):
        from aiohttp.test_utils import TestClient, TestServer

        from fakes import saver_outputs
        from seriesmith.server import standalone
        from seriesmith.settings import Settings
        fb = FakeBackend("deployment:minimax_h3_ref2va", "deployment", outputs=saver_outputs)

        async def go():
            app = standalone.make_app([self.shows], Settings(comfyui_url="http://127.0.0.1:9"),
                                      backends={fb.name: fb})
            async with TestClient(TestServer(app)) as client:
                ws = await client.ws_connect("/ws")
                r = await client.post("/seriesmith/render", json={
                    "ep": self.ep, "pass": "proxy", "shots": ["sh010"],
                    "backend": "deployment"})
                res = await r.json()
                self.assertEqual(r.status, 200, res)
                (q,) = res["queued"]
                heard = []
                while True:
                    m = await asyncio.wait_for(ws.receive_json(), 10)
                    heard.append(m["type"])
                    if m["type"] == "seriesmith.take" and m["data"]["status"] == "ok":
                        break
                jobs = await (await client.get("/seriesmith/jobs")).json()
                await ws.close()
                return q, heard, jobs
        q, heard, jobs = asyncio.run(go())
        self.assertEqual(q["backend"], "deployment:minimax_h3_ref2va")
        take = T.get_take(self.ep, "proxy", "sh010", q["take"])
        self.assertEqual(take.status, "ok")
        sc = take.sidecar
        self.assertEqual((sc["queue"], sc["backend"], sc["comfy_prompt_id"]),
                         ("seriesmith", fb.name, q["prompt_id"]))
        self.assertTrue(sc["backend_job"].startswith("fake-"))
        self.assertIn("execution_start", heard)
        self.assertEqual(jobs["jobs"][0]["status"], "succeeded")
        self.assertEqual(len(fb.submitted), 1)


if __name__ == "__main__":
    unittest.main()
