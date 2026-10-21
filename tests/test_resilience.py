"""
Resilience (docs/PLAN.md, step 11): a job past its time limit is stopped and
failed; the queue lists its live jobs in a journal; paid runs are counted and
capped; after a restart a job that had reached its backend is found again and
collected (not run again), one that hadn't is failed saying how to queue it
again; a retry of a paid run that finished after all collects it instead of
paying twice.
"""
from __future__ import annotations

import asyncio
import json
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
from seriesmith.backends.fake import FakeBackend, FakeRun  # noqa: E402
from seriesmith.queue import DONE, Job, PaidLimit, Queue  # noqa: E402
from seriesmith.runner import Runner  # noqa: E402
from test_queue import Gate, settle_queue_threads, wait_for  # noqa: E402
from test_render import FIXTURE, build_episode  # noqa: E402


class QueueResilienceTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(settle_queue_threads)              # runs first: cleanups are LIFO
        self.journal = os.path.join(self._tmp.name, "queue.json")
        self.q = Queue(journal=self.journal)

    def test_a_job_past_its_time_limit_is_stopped_and_failed(self):
        g = Gate()
        stopped = []
        job = Job(kind="render", lane="local", title="hangs", work=g.work(), limit=0.2)
        job.cancel_run = lambda: stopped.append(1)
        self.q.submit(job)
        wait_for(lambda: job.status in DONE, 5)
        self.assertEqual(job.status, "failed")
        self.assertIn("time limit", job.error)
        self.assertEqual(stopped, [1])                    # its run was asked to stop

    def test_closing_keeps_the_journal_and_stops_local_work(self):
        """The server stopping (Queue.close): a master or align running is
        stopped, not left going with no server, and stays in the journal as
        running, for the next start to list; a render is left to its backend."""
        g, r = Gate(), Gate()
        killed = []
        local = Job(kind="master", lane="cpu", title="ks01 master", work=g.work(),
                    resume={"kind": "local", "task": "master", "params": {}})
        render = Job(kind="render", lane="local", title="sh010", work=r.work(),
                     record="r.json", resume={"kind": "render"})
        self.q.submit(local)
        self.q.submit(render)
        g.started.wait(5)
        r.started.wait(5)
        self.q.arm_cancel(local, lambda: (killed.append("master"), g.go.set()))
        self.q.arm_cancel(render, lambda: killed.append("render"))
        self.q.close()
        self.assertEqual(killed, ["master"])
        wait_for(lambda: local.status in DONE, 5)
        live = json.load(open(self.journal, encoding="utf-8"))
        self.assertEqual({e["title"]: e["status"] for e in live.values()},
                         {"ks01 master": "running", "sh010": "running"})
        r.go.set()

    def test_the_journal_lists_live_jobs_with_a_record(self):
        g = Gate()
        a = self.q.submit(Job(kind="render", lane="local", title="a", work=g.work(),
                              record="r.json", resume={"kind": "render"}))
        self.q.submit(Job(kind="test", lane="local", title="no record", work=g.work()))
        g.started.wait(5)
        with open(self.journal, encoding="utf-8") as fh:
            live = json.load(fh)
        self.assertEqual(list(live), [a.id])
        self.assertEqual((live[a.id]["record"], live[a.id]["resume"]), ("r.json", {"kind": "render"}))
        g.go.set()
        wait_for(lambda: all(j.status in DONE for j in self.q.jobs.values()), 5)
        self.assertEqual(self.q.read_journal(), {})

    def test_a_step_waits_on_its_test_and_is_made_again_after_a_restart(self):
        from seriesmith.server.standalone import recover
        held = [True]
        ran = []
        runner = Runner(self.q, {}, lambda e, d: None)
        step = runner.enqueue_step("clip: render once its pictures are made",
                                   lambda report: ran.append(1) or "succeeded",
                                   wait=lambda: held[0], spec={"step": "clip", "params": {"x": 1}})
        time.sleep(0.1)
        self.assertEqual((self.q.jobs[step].status, ran), ("queued", []))   # its pictures aren't made
        live = self.q.read_journal()
        self.assertEqual(live[step]["resume"], {"kind": "step", "step": "clip", "params": {"x": 1}})
        # the server stops; started again, the step is made again from the journal
        q2 = Queue(journal=self.journal)
        made = []
        out = recover(Runner(q2, {}, lambda e, d: None), None, made.append)
        self.assertEqual(made, [live[step]["resume"]])
        self.assertIn("step(s) made again", " ".join(out))
        # one that was running when it stopped isn't done twice
        live[step]["status"] = "running"
        with open(self.journal, "w", encoding="utf-8") as fh:
            json.dump(live, fh)
        made.clear()
        out = recover(Runner(Queue(journal=self.journal), {}, lambda e, d: None), None, made.append)
        self.assertEqual(made, [])
        self.assertIn("was running", " ".join(out))
        # its pictures made, the first one runs
        held[0] = False
        self.q.pause("steps", True)
        self.q.pause("steps", False)                      # a dispatch, as a finished job does
        wait_for(lambda: self.q.jobs[step].status in DONE, 5)
        self.assertEqual(ran, [1])

    def test_long_local_work_is_journaled_and_handed_back_after_a_restart(self):
        """A master or align (Runner.local_job) is journaled; after a restart
        recover hands each entry to `local` (api.rebuild_local), saying which
        were queued again and which had been running."""
        from seriesmith.server.standalone import recover
        g = Gate()
        runner = Runner(self.q, {}, lambda e, d: None)
        spec = {"task": "master", "params": {"ep": "x"}}
        first = runner.enqueue_local(runner.local_job("master", "ks01 master",
                                                      lambda j, r, stop: g.work()(j, r),
                                                      {"ep": "x"}, spec))
        second = runner.enqueue_local(runner.local_job("align", "ks01 align",
                                                       lambda j, r, stop: "succeeded",
                                                       {"ep": "x"}, dict(spec, task="align")))
        g.started.wait(5)
        live = self.q.read_journal()
        self.assertEqual((live[first.id]["status"], live[second.id]["status"]),
                         ("running", "queued"))
        self.assertEqual(live[first.id]["resume"], {"kind": "local", **spec})
        handed = []
        out = recover(Runner(Queue(journal=self.journal), {}, lambda e, d: None), None,
                      None, lambda entry: handed.append(entry) or "new-id")
        self.assertEqual(sorted(e["title"] for e in handed), ["ks01 align", "ks01 master"])
        said = " ".join(out)
        self.assertIn("ks01 master: it was running when the server stopped", said)
        self.assertIn("ks01 align: queued again", said)
        g.go.set()
        wait_for(lambda: second.status in DONE, 5)
        self.assertEqual(self.q.read_journal(), {})

    def test_paid_runs_are_counted_and_capped(self):
        self.q.paid_limit = 2
        self.q.charge("router")
        self.q.charge("router")
        with self.assertRaises(PaidLimit):
            self.q.charge("router")
        self.assertEqual(self.q.list()["paid"], {"count": 2, "limit": 2})
        self.q.paid_limit = None
        self.q.charge("cloud")
        self.assertEqual(self.q.paid()["count"], 3)


class HoldRun(FakeRun):
    """A run that never ends here: the server stops while it goes on."""

    def watch(self, on_progress=None, on_status=None):
        threading.Event().wait()


class Holding(FakeBackend):
    def submit(self, graph):
        g = self._upload(graph)
        self.submitted.append(g)
        return HoldRun(self, g)


class EpisodeCase(unittest.TestCase):
    def setUp(self):
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

    def serve(self, backend, body):
        from aiohttp.test_utils import TestClient, TestServer

        from seriesmith.server import standalone
        from seriesmith.settings import Settings

        async def go():
            app = standalone.make_app([self.shows], Settings(comfyui_url="http://127.0.0.1:9"),
                                      backends={backend.name: backend})
            async with TestClient(TestServer(app)) as client:
                return await body(client, app)
        return asyncio.run(go())


class RestartTest(EpisodeCase):
    """The standalone server stopped mid-render, then started again."""

    def test_a_running_render_is_found_again_and_collected(self):
        from fakes import saver_outputs
        first = Holding("deployment:minimax_h3_ref2va", "deployment")

        async def start(client, app):
            r = await client.post("/seriesmith/render", json={
                "ep": self.ep, "pass": "proxy", "shots": ["sh010"], "backend": "deployment"})
            (q,) = (await r.json())["queued"]
            take = None
            for _ in range(500):                         # until its run is the backend's
                take = T.get_take(self.ep, "proxy", "sh010", q["take"])
                if take.sidecar.get("backend_job"):
                    break
                await asyncio.sleep(0.02)
            return q, take.sidecar["backend_job"]
        q, run_id = self.serve(first, start)             # ... and the server stops here

        again = FakeBackend("deployment:minimax_h3_ref2va", "deployment", outputs=saver_outputs)
        again.attached[run_id] = first.submitted[0]      # the run went on at the backend

        async def after(client, app):
            for _ in range(500):
                t = T.get_take(self.ep, "proxy", "sh010", q["take"])
                if t.status != "queued":
                    return t, (await (await client.get("/seriesmith/jobs")).json())
                await asyncio.sleep(0.02)
            return t, None
        take, jobs = self.serve(again, after)
        self.assertEqual(take.status, "ok", take.sidecar)
        self.assertEqual(again.attaches, [(run_id, None)])
        self.assertEqual(again.submitted, [])            # collected, not run again
        self.assertNotEqual(take.sidecar["comfy_prompt_id"], q["prompt_id"])
        self.assertIn("(found again)", jobs["jobs"][0]["title"])

    def test_renders_still_waiting_are_queued_again_with_their_numbers(self):
        """Three shots on your own ComfyUI (one at a time): the first is at the
        backend when the server stops, the other two still wait in seriesmith's
        queue. After the restart the first is collected, the two are asked for
        again, and nothing is left failed."""
        from fakes import saver_outputs
        first = Holding("local", "local")
        shots = ["sh010", "sh020", "sh030"]

        async def start(client, app):
            r = await client.post("/seriesmith/render", json={
                "ep": self.ep, "pass": "proxy", "shots": shots, "backend": "local"})
            queued = (await r.json())["queued"]
            for _ in range(500):
                t = T.get_take(self.ep, "proxy", "sh010", queued[0]["take"])
                if t.sidecar.get("backend_job"):
                    break
                await asyncio.sleep(0.02)
            return queued, t.sidecar["backend_job"]
        queued, run_id = self.serve(first, start)
        self.assertEqual(len(queued), 3)
        self.assertEqual(len(first.submitted), 1)        # the others never left the queue

        again = FakeBackend("local", "local", outputs=saver_outputs)
        again.attached[run_id] = first.submitted[0]

        async def after(client, app):
            for _ in range(1000):
                takes = {s: T.list_takes(self.ep, "proxy", s) for s in shots}
                if all(ts and all(t.status == "ok" for t in ts) for ts in takes.values()):
                    break
                await asyncio.sleep(0.02)
            return takes
        takes = self.serve(again, after)
        for q in queued:
            got = takes[q["shot"]]
            self.assertEqual([(t.take, t.status) for t in got], [(q["take"], "ok")], q["shot"])
        self.assertEqual(again.attaches, [(run_id, None)])
        self.assertEqual(len(again.submitted), 2)        # sh020, sh030: asked for again

    def test_a_render_that_never_reached_its_backend_is_failed_saying_how_to_queue_it(self):
        take = T.reserve_take(self.ep, "proxy", "sh010", {"status": "queued"})
        T.update_sidecar(take.paths.sidecar, backend="local", queue="seriesmith",
                         comfy_prompt_id="old-job")
        q = Queue(journal=os.path.join(self._tmp.name, "q.json"))
        runner = Runner(q, {"local": FakeBackend()})
        entry = {"kind": "render", "title": "ks01 sh010 t01", "record": take.paths.sidecar,
                 "resume": {"kind": "render", "ep": self.ep, "pass": "proxy", "shot": "sh010",
                            "take": take.take}}
        self.assertIsNone(runner.reattach("old-job", entry))
        sc = T.read_sidecar(take.paths.sidecar)
        self.assertEqual(sc["status"], "failed")
        self.assertIn("Generate missing (Shots tab)", sc["save_notes"])
        # a record another job owns now, or one already done, is left alone
        T.update_sidecar(take.paths.sidecar, status="queued", comfy_prompt_id="newer")
        self.assertIsNone(runner.reattach("old-job", entry))
        self.assertEqual(T.read_sidecar(take.paths.sidecar)["status"], "queued")


class RetryCollectsTest(EpisodeCase):
    def test_a_paid_retry_collects_a_run_that_finished_after_all(self):
        from fakes import saver_outputs
        fb = FakeBackend("deployment:minimax_h3_ref2va", "deployment", outputs=saver_outputs,
                         final="failed", error="connection lost")

        async def body(client, app):
            r = await client.post("/seriesmith/render", json={
                "ep": self.ep, "pass": "proxy", "shots": ["sh010"], "backend": "deployment"})
            (q,) = (await r.json())["queued"]
            queue = app["queue"]
            for _ in range(500):
                if queue.jobs[q["prompt_id"]].status in DONE:
                    break
                await asyncio.sleep(0.02)
            sc = T.get_take(self.ep, "proxy", "sh010", q["take"]).sidecar
            self.assertEqual(sc["status"], "failed")
            # it had finished at the backend after all
            fb.final = "succeeded"
            fb.attached[sc["backend_job"]] = fb.submitted[0]
            r = await client.post("/seriesmith/jobs/retry", json={"id": q["prompt_id"]})
            self.assertEqual(r.status, 200)
            for _ in range(500):
                t = T.get_take(self.ep, "proxy", "sh010", q["take"])
                if t.status == "ok":
                    break
                await asyncio.sleep(0.02)
            return q, t
        q, take = self.serve(fb, body)
        self.assertEqual(take.status, "ok", take.sidecar)
        self.assertEqual(len(fb.submitted), 1)            # not paid for twice
        self.assertEqual(T.take_numbers(self.ep, "proxy", "sh010"), [q["take"]])


if __name__ == "__main__":
    unittest.main()


class RoomTest(unittest.TestCase):
    def test_a_full_disk_is_said_before_anything_is_queued(self):
        from collections import namedtuple
        from unittest import mock

        from seriesmith import runner as RN
        usage = namedtuple("usage", "total used free")
        with mock.patch("shutil.disk_usage", return_value=usage(100e9, 99.5e9, 0.5e9)):
            with self.assertRaises(ValueError) as cm:
                RN.room(".", "upscale")
            self.assertIn("0.5 GB free", str(cm.exception))
            RN.room(".", "ref")                          # 0.2 GB is enough for a picture
