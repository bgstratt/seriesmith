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
                       probe=None, continuity: dict | None = None,
                       after: str | None = None) -> tuple[T.Take, str]:
        """Reserve the take and queue its render; its inputs are staged when
        the job starts (stage_portable), so a continuity shot cuts its first
        frame from the take the cut uses then (`continuity`: h3pipe's live
        continuity entry), and a `continuous: latent` one holds that take
        (refs.chain_source) -- including one rendered just before it in the
        same batch. `after`: the queue job it waits for (the shot it
        continues). ValueError when the backend isn't set up here (nothing is
        reserved then)."""
        import os

        from seriesmith import render as RD

        backend = self.backends.get(backend_name)
        if backend is None:
            raise ValueError(f"{backend_name} isn't set up on this machine (seriesmith backends)")
        local_probe = probe if backend.kind == "local" else None
        # the continuity node of h3pipe's way (H3ContinuityFrame) isn't used:
        # the first frame is cut when the job starts, below
        job.continuity = None
        take = J.start_job(job)
        ep = job.root
        title = f"{_ep_name(ep)} {job.id} t{take.take:02d}"
        gkw = dict(review_copy=self.review_copy, portable=True)
        chained = bool((job.recompiled or job.shot).get("hold"))

        def stage(report) -> None:
            from seriesmith import refs as R
            if continuity is not None:
                rel = os.path.relpath(take.paths.sidecar, ep)
                res = R.continuity_at_start(ep, job.id, job.pass_, rel)
                if res.get("note"):
                    report(line=res["note"])
            if chained:
                job.chain_from = R.chain_source(ep, job.id, job.pass_)
                f = job.chain_from.get("from") or {}
                report(line=f"holds {f.get('shot')} {f.get('pass')} t{int(f.get('take') or 0):02d} "
                            f"({'its latent' if job.chain_from.get('latent') else 'its frames'})")
            J.stage_portable(job, local_probe)
            J.place_staged(job, take)

        def work(qjob: QJob, report) -> str:
            def progress(p):
                report(p.value, p.step, p.steps)

            def got_run(run):
                qjob.cancel_run = run.cancel
                report(line=f"on {backend.name}: {run.id}")
            try:
                stage(report)
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
            j2.chain_from = None
            self.enqueue_render(j2, base, backend_name, probe, continuity)
            return None                                  # enqueue_render submitted it

        qjob = QJob(kind="render", lane=backend.name, title=title, work=work,
                    info={"ep": ep, "pass": job.pass_, "shot": job.id, "take": take.take,
                          "target": job.target, "backend": backend.name,
                          **({"continues": "first frame"} if continuity is not None else {}),
                          **({"continues": "latent"} if chained else {})},
                    on_cancel=cancelled, retry=again, after=after)
        T.update_sidecar(take.paths.sidecar, backend=backend.name, comfy_prompt_id=qjob.id,
                         queue="seriesmith")
        take.sidecar = T.read_sidecar(take.paths.sidecar)
        self.queue.submit(qjob)
        return take, qjob.id

    def enqueue_ref(self, s, job, base: dict | None, backend_name: str,
                    lora_clip: bool = True) -> tuple[object, str]:
        """A reference take (refs.GenJob: a character sheet, a plate, a
        keyframe, a voice) staged, reserved and queued: its reference pictures
        and voice sample go up as uploads, the workflow keeps its own
        SaveImage / SaveAudio, and the file the backend hands back closes the
        take (refs.close_take). Returns (the ref take, the queue's job id)."""
        import os
        import tempfile

        from seriesmith import refs as R

        backend = self.backends.get(backend_name)
        if backend is None:
            raise ValueError(f"{backend_name} isn't set up on this machine (seriesmith backends)")
        collector = J.InputCollector(keep_dir=os.path.join(R.takes_dir(job.ref), "_staged"))
        R.stage_references(s, job, collector)
        R.stage_voice_reference(s, job, collector)
        take = R.start_gen(s, job)
        g = R.graph_for(base, job, take, lora_clip=lora_clip, portable=True)
        J.files_as_uploads(g, collector.files)
        savers = [k for k, v in g.items() if v["class_type"] in ("SaveImage", "SaveAudio")]
        want = "audio" if job.is_audio else "image"
        ep = s.ep
        title = f"{_ep_name(ep)} {job.ref.id}{' ' + job.view if job.view else ''} t{take.take:02d}"

        def work(qjob: QJob, report) -> str:
            def progress(p):
                report(p.value, p.step, p.steps)
            try:
                run = backend.submit(g)
                qjob.cancel_run = run.cancel
                report(line=f"on {backend.name}: {run.id}")
                T.update_sidecar(take.paths.sidecar, backend_job=run.id)
                status = run.watch(on_progress=progress)
                if status != "succeeded":
                    raise RuntimeError(run.error or f"the job ended {status}")
                outs = [o for o in run.outputs() if o.type == want]
                outs = [o for o in outs if o.node in savers] or outs
                if not outs:
                    raise RuntimeError(f"the job finished but returned no {want}")
                fd, tmp = tempfile.mkstemp(suffix=os.path.splitext(outs[0].name)[1])
                os.close(fd)
                try:
                    with open(outs[0].save(tmp), "rb") as fh:
                        data = fh.read()
                finally:
                    os.remove(tmp)
                ext = os.path.splitext(outs[0].name)[1].lower() if job.is_audio else None
                result = R.close_take(take, data, f"from {backend.name}: {outs[0].name}", ext=ext)
            except Exception as e:                       # noqa: BLE001  the take fails
                R.mark_failed(take, "canceled" if qjob.cancel_asked else str(e)[:800])
                qjob.error = str(e)[:800]
                result = "failed"
            report(line=f"take {result}")
            self._emit("h3pipe.ref", {"ep": ep, "ref": job.ref.id, "view": job.view,
                                      "take": take.take, "status": result})
            self._emit("h3pipe.episode", {"ep": ep})
            return "succeeded" if result == "ok" else (
                "canceled" if qjob.cancel_asked else "failed")

        def cancelled(qjob: QJob) -> None:
            R.mark_failed(take, "canceled before it ran")
            self._emit("h3pipe.ref", {"ep": ep, "ref": job.ref.id, "view": job.view,
                                      "take": take.take, "status": "failed"})

        qjob = QJob(kind="ref", lane=backend.name, title=title, work=work,
                    info={"ep": ep, "ref": job.ref.id, "view": job.view, "take": take.take,
                          "target": job.target.id, "backend": backend.name},
                    on_cancel=cancelled)
        R.mark_queued(take, qjob.id)
        T.update_sidecar(take.paths.sidecar, backend=backend.name, queue="seriesmith")
        self.queue.submit(qjob)
        return take, qjob.id

    def enqueue_finish(self, fin, backend_name: str, after: str | None = None) -> str:
        """An upscale or a post (finishing.Finish, its record already started:
        upscale.start / post.start) queued: when its job starts its graph is
        made portable (finishing.portable: a continuity frame or a held latent
        from the previous upscale if it has run by then), run on the backend,
        and its files and record collected into the take. `after`: the queue
        job it waits for (the upscale a post is made from, or the previous
        shot's upscale this one starts from). Returns the queue's job id."""
        from seriesmith import finishing as F

        backend = self.backends.get(backend_name)
        if backend is None:
            raise ValueError(f"{backend_name} isn't set up on this machine (seriesmith backends)")
        ep, take = fin.root, fin.take
        event = F.EVENTS[fin.kind]

        def tell(status: str) -> None:
            self._emit(event, {"ep": ep, "shot": take.shot, "take": take.take, "status": status})
            self._emit("h3pipe.episode", {"ep": ep})

        def work(qjob: QJob, report) -> str:
            def progress(p):
                report(p.value, p.step, p.steps)
            try:
                g, extra = F.portable(fin)
                for n in fin.notes:
                    report(line=n)
                run = backend.submit(g)
                qjob.cancel_run = run.cancel
                report(line=f"on {backend.name}: {run.id}")
                T.update_sidecar(fin.sidecar, backend_job=run.id)
                status = run.watch(on_progress=progress)
                result = F.collect(fin, run, J.node_of(g, F.SAVER), status, extra)
                if result != "ok":
                    qjob.error = str((T.read_sidecar(fin.sidecar) or {}).get("save_notes")
                                     or f"the {fin.kind} ended {status}")[:800]
            except Exception as e:                       # noqa: BLE001  the finish fails
                F.mark_failed(fin, "canceled" if qjob.cancel_asked else str(e)[:800])
                qjob.error = str(e)[:800]
                result = "failed"
            if qjob.cancel_asked and result != "ok":
                F.mark_failed(fin, "canceled")
            report(line=f"{fin.kind} {result}")
            tell(result)
            return "succeeded" if result == "ok" else (
                "canceled" if qjob.cancel_asked else "failed")

        def cancelled(qjob: QJob) -> None:
            F.mark_failed(fin, "canceled before it ran")
            tell("failed")

        qjob = QJob(kind=fin.kind, lane=backend.name,
                    title=f"{_ep_name(ep)} {fin.label} {fin.kind}", work=work,
                    info={"ep": ep, "pass": take.pass_, "shot": take.shot, "take": take.take,
                          "backend": backend.name},
                    on_cancel=cancelled, after=after)
        T.update_sidecar(fin.sidecar, backend=backend.name, comfy_prompt_id=qjob.id,
                         queue="seriesmith")
        self.queue.submit(qjob)
        return qjob.id

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
