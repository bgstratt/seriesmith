"""
The runner: what puts a planned take on seriesmith's queue (seriesmith.queue)
and has a backend render it, for the editor (api.post_render through
edit.queue_shots) as `seriesmith render` does from the command line.

    enqueue_render(job, base, backend_name, probe) -> (take, queue job id)

The take is staged and reserved at once (its record says `queued`, which
backend, and the queue's job id as its prompt id, which is how the editor
follows it); the queue's job then renders it (render.run_take) on its
backend's lane and, when it ends, sends the editor "h3pipe.take" as h3pipe's
save node did.
"""
from __future__ import annotations

import copy

from seriesmith import jobs as J
from seriesmith import takes as T
from seriesmith.queue import Job as QJob
from seriesmith.queue import Queue


class Runner:
    def __init__(self, queue: Queue, backends: dict, emit=None, review_copy: bool = False):
        self.queue = queue
        self.backends = backends
        self._emit = emit or (lambda e, d: None)
        self.review_copy = review_copy
        # takes this runner owns are checked against its queue, not ComfyUI's
        T.MANAGED = queue.alive

    def backend(self, name: str):
        return self.backends.get(name)

    def enqueue_render(self, job: J.Job, base: dict | None, backend_name: str,
                       probe=None) -> tuple[T.Take, str]:
        """Stage and reserve the take, then queue its render. ValueError when
        the backend isn't set up here (nothing is reserved then)."""
        from seriesmith import render as RD

        backend = self.backends.get(backend_name)
        if backend is None:
            raise ValueError(f"{backend_name} isn't set up on this machine (seriesmith backends)")
        take = RD.start_job_portable(job, probe if backend.kind == "local" else None)
        ep = job.root
        title = f"{_ep_name(ep)} {job.id} t{take.take:02d}"
        gkw = dict(review_copy=self.review_copy, portable=True)

        def work(qjob: QJob, report) -> str:
            def progress(p):
                report(p.value, p.step, p.steps)

            def got_run(run):
                qjob.cancel_run = run.cancel
                report(line=f"on {backend.name}: {run.id}")
            try:
                status = RD.run_take(job, take, backend, base, gkw, on_progress=progress,
                                     on_run=got_run, prompt_id=qjob.id)
            except Exception as e:                       # noqa: BLE001  the take fails
                J.mark_failed(take, str(e)[:800])
                qjob.error = str(e)[:800]
                status = "failed"
            sc = T.read_sidecar(take.paths.sidecar) or {}
            if status != "ok" and not qjob.error:
                qjob.error = str(sc.get("save_notes") or f"the take ended {status}")[:800]
            if qjob.cancel_asked and status != "ok":
                J.mark_failed(take, "canceled")
            report(line=f"take {status}")
            self._take_event(ep, take)
            return "succeeded" if status == "ok" else (
                "canceled" if qjob.cancel_asked else "failed")

        def cancelled(qjob: QJob) -> None:
            J.mark_failed(take, "canceled before it ran")
            self._take_event(ep, take)

        def again():
            """A retry: the same shot and settings, as a new take."""
            j2 = copy.copy(job)
            j2.take, j2.forced, j2.staged, j2.input_files = job.take + 1, False, [], {}
            t2, _ = self.enqueue_render(j2, base, backend_name, probe)
            return None                                  # enqueue_render submitted it

        qjob = QJob(kind="render", lane=backend.name, title=title, work=work,
                    info={"ep": ep, "pass": job.pass_, "shot": job.id, "take": take.take,
                          "target": job.target, "backend": backend.name},
                    on_cancel=cancelled, retry=again)
        T.update_sidecar(take.paths.sidecar, backend=backend.name, comfy_prompt_id=qjob.id,
                         queue="seriesmith")
        take.sidecar = T.read_sidecar(take.paths.sidecar)
        self.queue.submit(qjob)
        return take, qjob.id

    def _take_event(self, ep: str, take: T.Take) -> None:
        t = T.get_take(take_root(take), take.pass_, take.shot, take.take) or take
        from seriesmith import edit as E
        self._emit("h3pipe.take", {"ep": ep, "pass": t.pass_, "shot": t.shot, "take": t.take,
                                   "status": t.status, "thumb": E.rel(ep, t.paths.thumb)})
        self._emit("h3pipe.episode", {"ep": ep})


def _ep_name(ep: str) -> str:
    import os
    return os.path.basename(os.path.normpath(ep))


def take_root(take: T.Take) -> str:
    """The episode folder a take belongs to (renders/<shot>/ -> the episode)."""
    import os
    return os.path.dirname(os.path.dirname(take.paths.dir))
