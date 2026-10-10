"""
seriesmith's job queue (docs/DESIGN.md, "The queue"): the server's list of
work, sent to backends. One lane per backend: your own ComfyUI renders one
job at a time (the proxy can't reorder ComfyUI's queue, so the order is ours),
a cloud backend several at once. A queued job can be cancelled, moved, or a
lane paused; a running one cancelled; a finished one retried.

A job is a description (what it is, for the Jobs window) and a `work`
function that does it: work(job, report) -> "succeeded" | "failed" |
"canceled", where report(...) updates its progress and log, and
job.cancel_run, set by the work once it has something to cancel, stops it.

Every change goes out as the event "seriesmith.job" (the job's to_json());
progress also goes out in ComfyUI's shapes ("progress", "execution_start",
"execution_success", "execution_error"), with the job's id as the prompt id,
which is how the editor's thumbnails already follow a render.
"""
from __future__ import annotations

import itertools
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Callable

STATUSES = ("queued", "running", "succeeded", "failed", "canceled")
DONE = ("succeeded", "failed", "canceled")
PARALLEL = 4                     # jobs at once on a backend that isn't your own ComfyUI
LOG_LINES = 200
KEEP_DONE = 200                  # finished jobs kept in the list


def now() -> float:
    return time.time()


@dataclass
class Job:
    kind: str                                    # "render", ...
    lane: str                                    # the backend's name
    title: str                                   # "ep02 sh180 t03"
    work: Callable = field(repr=False)
    info: dict = field(default_factory=dict)     # ep, pass, shot, take, target, ...
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: str = "queued"
    progress: float = 0.0                        # 0..1
    step: int | None = None
    steps: int | None = None
    created: float = field(default_factory=now)
    started: float | None = None
    finished: float | None = None
    error: str = ""
    log: list[str] = field(default_factory=list)
    cancel_run: Callable | None = field(default=None, repr=False)
    cancel_asked: bool = False
    retry: Callable | None = field(default=None, repr=False)   # () -> new Job or None
    # a queued job cancelled before it ran: what to undo (a render: its take)
    on_cancel: Callable | None = field(default=None, repr=False)
    # the job it waits for (a continuity shot: the one it continues), on any lane
    after: str | None = None

    def to_json(self) -> dict:
        return {"id": self.id, "kind": self.kind, "lane": self.lane, "title": self.title,
                "after": self.after,
                "info": self.info, "status": self.status, "progress": self.progress,
                "step": self.step, "steps": self.steps, "created": self.created,
                "started": self.started, "finished": self.finished, "error": self.error,
                "log": self.log[-20:], "can_retry": self.retry is not None}


class Lane:
    def __init__(self, name: str, parallel: int):
        self.name = name
        self.parallel = parallel
        self.waiting: deque[Job] = deque()
        self.running: set[str] = set()
        self.paused = False


class Queue:
    def __init__(self, emit: Callable[[str, object], None] | None = None,
                 serial: Callable[[str], bool] | None = None):
        """`emit(event, data)` sends to the page; `serial(lane)` says whether a
        lane runs one job at a time (default: the lane called "local")."""
        self._emit = emit or (lambda e, d: None)
        self._serial = serial or (lambda lane: lane == "local")
        self._lock = threading.RLock()
        self._wake = threading.Condition(self._lock)
        self.lanes: dict[str, Lane] = {}
        self.jobs: dict[str, Job] = {}
        self._order = itertools.count()
        self._last_progress: dict[str, float] = {}

    # -- what the page sees -------------------------------------------------

    def list(self) -> dict:
        with self._lock:
            jobs = sorted(self.jobs.values(), key=lambda j: (j.status in DONE, -j.created
                                                             if j.status in DONE else j.created))
            return {"jobs": [j.to_json() for j in jobs],
                    "lanes": {n: {"paused": l.paused, "parallel": l.parallel,
                                  "waiting": [j.id for j in l.waiting],
                                  "running": sorted(l.running)} for n, l in self.lanes.items()}}

    def alive(self) -> set[str]:
        """Ids of the jobs queued or running (a take's sweep asks)."""
        with self._lock:
            return {i for i, j in self.jobs.items() if j.status not in DONE}

    def _changed(self, job: Job) -> None:
        self._emit("seriesmith.job", job.to_json())

    # -- adding and running -------------------------------------------------

    def _lane(self, name: str) -> Lane:
        if name not in self.lanes:
            self.lanes[name] = Lane(name, 1 if self._serial(name) else PARALLEL)
        return self.lanes[name]

    def submit(self, job: Job) -> Job:
        with self._lock:
            self.jobs[job.id] = job
            self._lane(job.lane).waiting.append(job)
            self._trim()
        self._changed(job)
        self._dispatch()
        return job

    def _trim(self) -> None:
        done = sorted((j for j in self.jobs.values() if j.status in DONE),
                      key=lambda j: j.finished or 0)
        for j in done[:max(0, len(done) - KEEP_DONE)]:
            del self.jobs[j.id]

    def _dispatch(self) -> None:
        start = []
        with self._lock:
            for lane in self.lanes.values():
                while not lane.paused and len(lane.running) < lane.parallel:
                    # the first waiting job whose `after` is done (or gone)
                    job = next((j for j in lane.waiting if not self._waits(j)), None)
                    if job is None:
                        break
                    lane.waiting.remove(job)
                    lane.running.add(job.id)
                    job.status, job.started = "running", now()
                    start.append(job)
        for job in start:
            self._changed(job)
            self._emit("execution_start", {"prompt_id": job.id})
            threading.Thread(target=self._run, args=(job,), daemon=True,
                             name=f"seriesmith-{job.lane}").start()

    def _waits(self, job: Job) -> bool:
        """Still waiting for the job it comes after."""
        before = self.jobs.get(job.after) if job.after else None
        return before is not None and before.status not in DONE

    def _run(self, job: Job) -> None:
        def report(progress: float | None = None, step: int | None = None,
                   steps: int | None = None, line: str | None = None) -> None:
            with self._lock:
                if progress is not None:
                    job.progress = max(0.0, min(1.0, float(progress)))
                if step is not None:
                    job.step, job.steps = step, steps
                if line:
                    job.log.append(line)
                    del job.log[:-LOG_LINES]
            t = now()
            if line or t - self._last_progress.get(job.id, 0) >= 0.25:
                self._last_progress[job.id] = t
                self._emit("progress", {"prompt_id": job.id, "value": round(job.progress * 100),
                                        "max": 100})
                self._changed(job)

        try:
            status = job.work(job, report)
            if job.cancel_asked and status != "succeeded":
                status = "canceled"
        except Exception as e:                           # noqa: BLE001  the job fails, not us
            status, job.error = "failed", f"{type(e).__name__}: {e}"
        with self._lock:
            job.status = status if status in DONE else "failed"
            job.finished = now()
            if job.status == "succeeded":
                job.progress = 1.0
            self.lanes[job.lane].running.discard(job.id)
            self._last_progress.pop(job.id, None)
        if job.status == "failed":
            self._emit("execution_error", {"prompt_id": job.id, "exception_message": job.error})
        elif job.status == "canceled":
            self._emit("execution_interrupted", {"prompt_id": job.id})
        else:
            self._emit("execution_success", {"prompt_id": job.id})
        self._changed(job)
        self._dispatch()

    # -- what the page can do -----------------------------------------------

    def cancel(self, job_id: str) -> Job:
        """A queued job leaves the queue; a running one is asked to stop."""
        with self._lock:
            job = self.jobs[job_id]
            if job.status == "queued":
                self._lane(job.lane).waiting.remove(job)
                job.status, job.finished = "canceled", now()
                cancelled_waiting = True
            elif job.status == "running":
                job.cancel_asked = True
                cancelled_waiting = False
            else:
                return job
        if cancelled_waiting:
            if job.on_cancel is not None:
                job.on_cancel(job)
            self._emit("execution_interrupted", {"prompt_id": job.id})
            self._changed(job)
        elif job.cancel_run is not None:
            try:
                job.cancel_run()
            except Exception as e:                       # noqa: BLE001  best effort
                job.log.append(f"cancel: {e}")
        return job

    def move(self, job_id: str, index: int) -> Job:
        """A queued job to `index` in its lane's waiting line (0: next)."""
        with self._lock:
            job = self.jobs[job_id]
            if job.status != "queued":
                raise ValueError(f"{job.title} is {job.status}; only a queued job moves")
            lane = self._lane(job.lane)
            lane.waiting.remove(job)
            lane.waiting.insert(max(0, min(index, len(lane.waiting))), job)
        self._emit("seriesmith.queue", self.list()["lanes"])
        return job

    def pause(self, lane: str, paused: bool = True) -> None:
        with self._lock:
            self._lane(lane).paused = paused
        self._emit("seriesmith.queue", self.list()["lanes"])
        if not paused:
            self._dispatch()

    def retry(self, job_id: str) -> Job | None:
        """A finished job done again (a render: a new take with its settings)."""
        with self._lock:
            job = self.jobs[job_id]
            if job.status not in DONE or job.retry is None:
                raise ValueError(f"{job.title} can't be retried ({job.status})")
        new = job.retry()
        return self.submit(new) if new is not None else None
