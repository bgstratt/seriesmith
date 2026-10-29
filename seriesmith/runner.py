"""
The runner: what puts a planned take on seriesmith's queue (seriesmith.queue)
and has a backend render it, for the editor (api.post_render through
edit.queue_shots) as `seriesmith render` does from the command line.

    enqueue_render(job, base, backend_name, probe) -> (take, queue job id)

The take is staged and reserved at once (its record says `queued`, which
backend, and the queue's job id as its prompt id, which is how the editor
follows it); the queue's job then renders it (render.run_take) on its
backend's lane and, when it ends, sends the editor "seriesmith.take" as h3pipe's
save node did.
"""
from __future__ import annotations

import copy

import json
import os
import threading

from seriesmith import jobs as J
from seriesmith import takes as T
from seriesmith.queue import Job as QJob
from seriesmith.queue import Queue
from seriesmith.core import fileio as F

# The API request being handled on this thread ({"path", "body"}; views.py
# sets it): each job it queues keeps it, so a job still waiting in the queue
# when the server stops can be asked for again (requeue_plan).
ASKED = threading.local()


def asked() -> dict | None:
    return getattr(ASKED, "req", None)

# How long a job may run before it is taken as hung, stopped and failed:
# several times the longest such job seen (a 4K SeedVR2 post is the slow one).
LIMITS = {"render": 2 * 3600, "ref": 1800, "upscale": 4 * 3600, "post": 6 * 3600,
          "tour": 3600}

# The least free disk a job needs where its files land (GB): a take is a few
# hundred MB with its latent and frames, a 4K upscale or post a few GB.
ROOM_GB = {"render": 1.0, "ref": 0.2, "upscale": 3.0, "post": 3.0, "tour": 1.0}


def room(folder: str, kind: str) -> None:
    """ValueError when `folder`'s disk has less free than a `kind` job needs:
    said before anything is reserved, not as a write failing half way."""
    import os
    import shutil
    need = ROOM_GB.get(kind, 1.0)
    try:
        free = shutil.disk_usage(folder).free / 1e9
    except OSError:
        return                                           # can't tell: let it try
    if free < need:
        drive = os.path.splitdrive(os.path.abspath(folder))[0] or folder
        raise ValueError(f"only {free:.1f} GB free on {drive}: a {kind} needs at least "
                         f"{need:g} GB there. Free some space and queue it again.")


LOCAL_LANE = "cpu"                   # long work of seriesmith's own (local_job)


def progress_to(report):
    """A backend's Progress handed to the queue's report()."""
    return lambda p: report(p.value, p.step, p.steps)


def ending(qjob: QJob, ok: bool) -> str:
    """The queue's status for a job that ended ok or not (canceled when Cancel
    was asked)."""
    return "succeeded" if ok else ("canceled" if qjob.cancel_asked else "failed")


def stopped(qjob: QJob) -> str:
    """What a stopped job's record says: the queue's reason (a time limit) or
    "canceled" (the user)."""
    return qjob.stop_note or "canceled"


class Runner:
    def __init__(self, queue: Queue, backends: dict, emit=None, review_copy: bool = False):
        self.queue = queue
        self.backends = backends
        self._emit = emit or (lambda e, d: None)
        self.review_copy = review_copy
        # ask(path, body) -> (status, data): an API request made from a job (the
        # server sets it; a clip's renders are asked for once its pictures exist)
        self.ask = None
        # takes this runner owns are checked against its queue, not ComfyUI's;
        # another queue's (the server's, while the command line renders) aren't
        T.MANAGED = queue.alive
        T.QUEUE = queue.name
        self._told: set[str] = set()         # backends the page was told have no node pack

    def backend(self, name: str):
        return self.backends.get(name)

    # -- what every job on a backend does (render, ref, finish, tour) --------

    def backend_for(self, name: str):
        """The backend `name`; ValueError when it isn't set up here (asked
        before anything is reserved)."""
        backend = self.backends.get(name)
        if backend is None:
            raise ValueError(f"{name} isn't set up on this machine (seriesmith backends)")
        return backend

    def reserve(self, backend, root: str, kind: str) -> None:
        """Before a job's take or record is reserved: room on the disk for what
        it makes, and a paid run counted (PaidLimit past Settings' limit), so a
        refusal leaves nothing behind."""
        room(root, kind)
        if backend.paid:
            self.queue.charge(backend.name)

    def started(self, qjob: QJob, run, backend, report) -> None:
        """A job's run started on its backend: Cancel stops it from now on, and
        the job's log says where it runs and what the backend changed."""
        self.queue.arm_cancel(qjob, run.cancel)
        report(line=f"on {backend.name}: {run.id}")
        for n in run.notes:
            report(line=n)
        if getattr(backend, "without_pack", False):
            report(line="without seriesmith's node pack: through ComfyUI's own nodes")
            if backend.name not in self._told:
                # once per backend while this server runs: a toast, not a note per take
                self._told.add(backend.name)
                self._emit("seriesmith.notice", {
                    "level": "warn", "key": f"no-pack:{backend.name}",
                    "title": "Rendering without seriesmith's node pack",
                    "text": "This ComfyUI hasn't seriesmith's nodes, so shots render through "
                            "ComfyUI's own nodes: no latent continuity, kept latents, upscales "
                            "or posts. Link it in Features (seriesmith's node pack), then "
                            "restart ComfyUI."})

    def enqueue_render(self, job: J.Job, base: dict | None, backend_name: str,
                       probe=None, continuity: dict | None = None,
                       after: str | None = None,
                       save_frames: bool | None = None,
                       review_copy: bool | None = None,
                       panel_mode: str | None = None) -> tuple[T.Take, str]:
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

        backend = self.backend_for(backend_name)
        local_probe = probe if backend.shares_disk else None
        self.reserve(backend, job.root, "render")
        # the continuity node of h3pipe's way (H3ContinuityFrame) isn't used:
        # the first frame is cut when the job starts, below
        job.continuity = None
        take = J.start_job(job)
        ep = job.root
        title = f"{_ep_name(ep)} {job.id} t{take.take:02d}"
        gkw = dict(review_copy=self.review_copy if review_copy is None else review_copy,
                   portable=True,
                   **({"save_frames": save_frames} if save_frames is not None else {}),
                   **({"panel_mode": panel_mode} if panel_mode else {}))
        chained = bool((job.recompiled or job.shot).get("hold"))

        def stage(report) -> None:
            from seriesmith import refs as R
            # a `continuous: latent` shot holds the take itself (below): no
            # first frame is cut for it
            if continuity is not None and not chained:
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
            # what staging decided (`dur: model`: predicted or the estimate, and
            # why) goes into the record reserved before it
            take.sidecar = T.update_sidecar(
                take.paths.sidecar, length_source=job.length_source,
                **({"notes": list(job.notes)} if job.notes else {}))

        def work(qjob: QJob, report) -> str:
            progress = progress_to(report)

            def got_run(run):
                self.started(qjob, run, backend, report)
                if run.notes:
                    had = (T.read_sidecar(take.paths.sidecar) or {}).get("notes") or []
                    T.update_sidecar(take.paths.sidecar, notes=list(had) + list(run.notes))

            def resume(bits):
                qjob.resume.update(bits)
                self.queue.write_journal()
            try:
                stage(report)
                status = RD.run_take(job, take, backend, base, gkw, on_progress=progress,
                                     on_run=got_run, prompt_id=qjob.id, on_resume=resume,
                                     on_status=self._remote(qjob, take.paths.sidecar, report))
            except Exception as e:                       # noqa: BLE001  the take fails
                J.mark_failed(take, str(e)[:800])
                qjob.error = str(e)[:800]
                status = "failed"
            sc = T.read_sidecar(take.paths.sidecar) or {}
            if status != "ok" and not qjob.error:
                qjob.error = str(sc.get("save_notes") or f"the take ended {status}")[:800]
            if qjob.cancel_asked and status != "ok":
                J.mark_failed(take, stopped(qjob))
            report(line=f"take {status}")
            self._take_event(ep, take)
            return ending(qjob, status == "ok")

        def cancelled(qjob: QJob) -> None:
            J.mark_failed(take, "canceled before it ran")
            self._take_event(ep, take)

        def again():
            """A retry: the same shot and settings, as a new take -- unless the
            run it had finished after all (a hosted run whose connection was
            lost): then that run is collected into the take, not paid again."""
            if self._collect_finished(qjob, backend):
                return None
            j2 = copy.copy(job)
            j2.take, j2.forced, j2.staged, j2.input_files = job.take + 1, False, [], {}
            j2.chain_from = None
            self.enqueue_render(j2, base, backend_name, probe, continuity,
                                save_frames=save_frames, review_copy=review_copy,
                                panel_mode=panel_mode)
            return None                                  # enqueue_render submitted it

        qjob = QJob(kind="render", lane=backend.name, title=title, work=work,
                    info={"ep": ep, "pass": job.pass_, "shot": job.id, "take": take.take,
                          "target": job.target, "backend": backend.name,
                          **({"continues": "first frame"} if continuity is not None else {}),
                          **({"continues": "latent"} if chained else {})},
                    on_cancel=cancelled, retry=again, after=after, limit=LIMITS["render"],
                    record=take.paths.sidecar,
                    resume={"kind": "render", "ep": ep, "pass": job.pass_, "shot": job.id,
                            "take": take.take, "asked": asked()})
        T.update_sidecar(take.paths.sidecar, backend=backend.name, comfy_prompt_id=qjob.id,
                         queue=self.queue.name)
        take.sidecar = T.read_sidecar(take.paths.sidecar)
        self._submit(qjob)
        return take, qjob.id

    def _remote(self, qjob: QJob, sidecar: str, report):
        """A run's status listener for a backend that runs requests in turn
        (Router): "waiting at Router (#2 in line)" or "running on Router", on
        the job (`info.remote`, which the Jobs window shows) and the take's
        record (`remote`), each time it changes. A take stays "queued" until it
        is collected; this says where it is meanwhile."""
        said = {"text": None}

        def on_status(run, status):
            if not run.reports_position or status not in ("queued", "running"):
                return
            pos = getattr(run, "position", None)
            text = ("running on Router" if status == "running"
                    else f"waiting at Router{f' (#{pos} in line)' if pos else ''}")
            if text == said["text"]:
                return
            said["text"] = text
            qjob.info["remote"] = text
            report(line=text)
            try:
                T.update_sidecar(sidecar, remote=text)
            except OSError:
                pass
            self.queue._changed(qjob)
        return on_status

    def enqueue_ref(self, s, job, base: dict | None, backend_name: str,
                    lora_clip: bool = True) -> tuple[object, str]:
        """A reference take (refs.GenJob: a character sheet, a plate, a
        keyframe, a voice) staged, reserved and queued: its reference pictures
        and voice sample go up as uploads, the workflow keeps its own
        SaveImage / SaveAudio, and the file the backend hands back closes the
        take (refs.close_take). Returns (the ref take, the queue's job id)."""
        import os

        from seriesmith import refs as R

        backend = self.backend_for(backend_name)
        hosted = bool(job.target.spec.get("router"))
        self.reserve(backend, s.ep, "ref")
        collector = J.InputCollector(keep_dir=os.path.join(R.takes_dir(job.ref), "_staged"))
        if not hosted:
            R.stage_references(s, job, collector)
            R.stage_voice_reference(s, job, collector)
        else:
            R.hosted_references(s, job)          # the pictures it sends, as local files
        take = R.start_gen(s, job)
        if hosted:
            # a hosted model (target.json `router`): one call, whatever it returns
            call = job.target.module.router_call(job.target, job)
            g, savers = None, []
        else:
            g = R.graph_for(base, job, take, lora_clip=lora_clip, portable=True)
            J.files_as_uploads(g, collector.files)
            from seriesmith.shotnodes import uses_h3pipe
            if uses_h3pipe(g):
                R.mark_failed(take, f"still uses h3pipe's nodes: {', '.join(uses_h3pipe(g))}")
                raise J.NotPortable(f"{job.ref.id} still uses h3pipe's nodes: "
                                    f"{', '.join(uses_h3pipe(g))}")
            # the picture comes back from the workflow's own save node: SaveImage,
            # or whatever an image workflow of the user's ends in (binding.saver.replace)
            own = ((job.target.binding.saver or {}).get("replace") or {}).get("class_type")
            savers = [k for k, v in g.items() if v["class_type"] in ("SaveImage", "SaveAudio", own)]
        want = "audio" if job.is_audio else "image"
        ep = s.ep
        title = f"{_ep_name(ep)} {job.ref.id}{' ' + job.view if job.view else ''} t{take.take:02d}"
        res = {"kind": "ref", "ep": ep, "ref": job.ref.id, "view": job.view, "take": take.take,
               "want": want, "savers": savers, "hosted": hosted, "is_audio": job.is_audio,
               "model": call[0] if hosted else None, "asked": asked()}

        def work(qjob: QJob, report) -> str:
            progress = progress_to(report)
            try:
                run = backend.call(*call) if hosted else backend.submit(g)
                self.started(qjob, run, backend, report)
                T.update_sidecar(take.paths.sidecar, backend_job=run.id)
                remote = self._remote(qjob, take.paths.sidecar, report)
                status = run.watch(on_progress=progress, on_status=lambda st: remote(run, st))
                result = collect_ref(take, run, status, res, backend.name)
            except Exception as e:                       # noqa: BLE001  the take fails
                R.mark_failed(take, stopped(qjob) if qjob.cancel_asked else str(e)[:800])
                qjob.error = str(e)[:800]
                result = "failed"
            report(line=f"take {result}")
            self._emit("seriesmith.ref", {"ep": ep, "ref": job.ref.id, "view": job.view,
                                      "take": take.take, "status": result})
            self._emit("seriesmith.episode", {"ep": ep})
            return ending(qjob, result == "ok")

        def cancelled(qjob: QJob) -> None:
            R.mark_failed(take, "canceled before it ran")
            self._emit("seriesmith.ref", {"ep": ep, "ref": job.ref.id, "view": job.view,
                                      "take": take.take, "status": "failed"})

        qjob = QJob(kind="ref", lane=backend.name, title=title, work=work,
                    info={"ep": ep, "ref": job.ref.id, "view": job.view, "take": take.take,
                          "target": job.target.id, "backend": backend.name},
                    on_cancel=cancelled, limit=LIMITS["ref"], record=take.paths.sidecar,
                    resume=res)
        R.mark_queued(take, qjob.id)
        T.update_sidecar(take.paths.sidecar, backend=backend.name, queue=self.queue.name)
        self._submit(qjob)
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

        backend = self.backend_for(backend_name)
        self.reserve(backend, fin.root, fin.kind)
        ep, take = fin.root, fin.take
        event = F.EVENTS[fin.kind]

        def tell(status: str) -> None:
            self._emit(event, {"ep": ep, "shot": take.shot, "take": take.take, "status": status})
            self._emit("seriesmith.episode", {"ep": ep})

        def work(qjob: QJob, report) -> str:
            progress = progress_to(report)
            try:
                g, extra = F.portable(fin)
                from seriesmith.shotnodes import uses_h3pipe
                if uses_h3pipe(g):
                    raise J.NotPortable(f"still uses h3pipe's nodes: {', '.join(uses_h3pipe(g))}")
                for n in fin.notes:
                    report(line=n)
                run = backend.submit(g)
                self.started(qjob, run, backend, report)
                T.update_sidecar(fin.sidecar, backend_job=run.id)
                qjob.resume.update(saver=J.node_of(g, F.SAVER), extra=extra)
                self.queue.write_journal()
                status = run.watch(on_progress=progress)
                result = F.collect(fin, run, J.node_of(g, F.SAVER), status, extra)
                if result != "ok":
                    qjob.error = str((T.read_sidecar(fin.sidecar) or {}).get("save_notes")
                                     or f"the {fin.kind} ended {status}")[:800]
            except Exception as e:                       # noqa: BLE001  the finish fails
                F.mark_failed(fin, stopped(qjob) if qjob.cancel_asked else str(e)[:800])
                qjob.error = str(e)[:800]
                result = "failed"
            if qjob.cancel_asked and result != "ok":
                F.mark_failed(fin, stopped(qjob))
            report(line=f"{fin.kind} {result}")
            tell(result)
            return ending(qjob, result == "ok")

        def cancelled(qjob: QJob) -> None:
            F.mark_failed(fin, "canceled before it ran")
            tell("failed")

        qjob = QJob(kind=fin.kind, lane=backend.name,
                    title=f"{_ep_name(ep)} {fin.label} {fin.kind}", work=work,
                    info={"ep": ep, "pass": take.pass_, "shot": take.shot, "take": take.take,
                          "backend": backend.name},
                    on_cancel=cancelled, after=after, limit=LIMITS.get(fin.kind),
                    record=fin.sidecar,
                    resume={"kind": fin.kind, "ep": ep, "pass": take.pass_, "shot": take.shot,
                            "take": take.take, "sidecar": fin.sidecar, "out_mp4": fin.out_mp4,
                            "last": fin.last, "latent": fin.latent, "asked": asked()})
        T.update_sidecar(fin.sidecar, backend=backend.name, comfy_prompt_id=qjob.id,
                         queue=self.queue.name)
        self._submit(qjob)
        return qjob.id

    def enqueue_tour(self, s, ref, side: dict, graph: dict, backend_name: str) -> tuple[int, str]:
        """A camera tour of a location (tour.plan_tours: its sidecar reserved,
        its graph) queued: the location's plate goes up as the graph's
        LoadImage, and the video that comes back is kept and its holds found
        (tour.keep_tour), each a take of the location's `tour` view. Returns
        (the tour's number, the queue's job id)."""

        from seriesmith import refs as R
        from seriesmith import tour as TR
        from seriesmith.backends import File

        backend = self.backend_for(backend_name)
        start = TR.tour_source(s, ref) or ref.file            # an angle: its place's plate
        for v in graph.values():
            if v["class_type"] == "LoadImage":
                v["inputs"]["image"] = File(start)
        self.reserve(backend, s.ep, "tour")
        ep, n = s.ep, side["tour"]

        def hold(take) -> None:
            self._emit("seriesmith.ref", {"ep": ep, "ref": ref.id, "view": R.TOUR_VIEW,
                                      "take": take.take, "status": "ok"})

        def work(qjob: QJob, report) -> str:
            progress = progress_to(report)
            try:
                run = backend.submit(graph)
                self.started(qjob, run, backend, report)
                side.update(backend_job=run.id)
                TR.save_side(ref, side)
                status = run.watch(on_progress=progress)
                collect_tour(s, ref, side, run, status, hold)
                report(line=f"{len(side.get('holds') or [])} hold(s)")
                result = "succeeded"
            except Exception as e:                       # noqa: BLE001  the tour fails
                qjob.error = str(e)[:800]
                if side.get("status") != "failed":
                    side.update(status="failed", finished=T.now(),
                                error=stopped(qjob) if qjob.cancel_asked else str(e)[:800])
                    TR.save_side(ref, side)
                result = "canceled" if qjob.cancel_asked else "failed"
            self._emit("seriesmith.episode", {"ep": ep})
            return result

        def cancelled(qjob: QJob) -> None:
            side.update(status="failed", finished=T.now(), error="canceled before it ran")
            TR.save_side(ref, side)
            self._emit("seriesmith.episode", {"ep": ep})

        qjob = QJob(kind="tour", lane=backend.name, title=f"{_ep_name(ep)} {ref.id} tour t{n:02d}",
                    work=work, info={"ep": ep, "ref": ref.id, "tour": n, "backend": backend.name},
                    on_cancel=cancelled, limit=LIMITS["tour"],
                    record=TR._tour_file(ref, n, ".json"),
                    resume={"kind": "tour", "ep": ep, "ref": ref.id, "tour": n, "asked": asked()})
        side.update(comfy_prompt_id=qjob.id, backend=backend.name, queue=self.queue.name)
        TR.save_side(ref, side)
        self._submit(qjob)
        return n, qjob.id

    def _submit(self, qjob: QJob) -> None:
        """Queue `qjob` with the shows whose own targets are in force here
        (targets.thread_roots, set by the request or the CLI) in force on the
        thread that runs it too, and its episode's: a show's own target (a
        Router model it added) is otherwise unknown to the queue's thread."""
        from seriesmith import targets as TG
        roots = list(TG.thread_roots())
        ep = (qjob.info or {}).get("ep")
        if ep:
            roots.append(ep)
        work = qjob.work

        def in_roots(job, report):
            with TG.use_roots(*roots):
                return work(job, report)
        qjob.work = in_roots
        self.queue.submit(qjob)

    def enqueue_step(self, title: str, work, after: list | str | None = None,
                     info: dict | None = None, wait=None, spec: dict | None = None) -> str:
        """A step of seriesmith's own (no backend: it asks for other jobs, as a
        clip asks for its renders once its pictures exist), on the "steps"
        lane, after `after` and while wait() is true. work(report) ->
        "succeeded" | "failed". With `spec` ({"step": name, "params": {...}})
        it is journaled, and made again from that after a restart
        (api.rebuild_step)."""
        def run(qjob: QJob, report) -> str:
            try:
                return work(report)
            except Exception as e:                       # noqa: BLE001  the step fails
                qjob.error = str(e)[:800]
                return "failed"
        qjob = QJob(kind="step", lane="steps", title=title, work=run, info=info or {},
                    after=after or None, wait=wait,
                    resume=({"kind": "step", **spec} if spec else None))
        self._submit(qjob)
        return qjob.id

    def local_job(self, kind: str, title: str, work, info: dict | None = None,
                  spec: dict | None = None, again=None) -> QJob:
        """Long work of seriesmith's own on this machine (a master, align), for
        the serial "cpu" lane: one at a time, never in the way of the renders.
        work(qjob, report, stop) -> "succeeded" | "failed", what it made in
        qjob.result; stop(kill) is how the run it starts is cancelled
        (Queue.arm_cancel). With `spec` ({"task", "params"}) it is journaled
        (api.rebuild_local); `again()` makes it anew for Retry. Not queued yet:
        enqueue_local."""
        def run(qjob: QJob, report) -> str:
            return work(qjob, report, lambda kill: self.queue.arm_cancel(qjob, kill))
        qjob = QJob(kind=kind, lane=LOCAL_LANE, title=title, work=run, info=info or {},
                    resume=({"kind": "local", **spec} if spec else None))
        qjob.retry = again
        return qjob

    def enqueue_local(self, qjob: QJob) -> QJob:
        return self.queue.submit(qjob)

    # -- a run found again: after a restart (recover.py), or by a retry ------

    def reattach(self, job_id: str, entry: dict, requeue: list | None = None) -> str | None:
        """A journal `entry` (queue.write_journal) of a job this server had
        when it stopped. Its record still `queued` under that job: when the
        job had reached its backend (the record's `backend_job`), the run is
        found again and followed and collected on a new queue job (its id
        returned). When it hadn't, nothing was spent on it: given `requeue`
        (a list) and the request that queued it, its record is cleared (it
        never ran) and the entry added to `requeue`, to be asked for again
        (requeue_plan); otherwise the record is failed, saying how to queue it
        again. Anything else (the record is done, or another job owns it now)
        is left alone: None."""
        path, res = entry.get("record"), entry.get("resume") or {}
        rec = T.read_json(path) if path else None
        if not isinstance(rec, dict) or rec.get("status") != "queued" \
                or rec.get("comfy_prompt_id") != job_id:
            return None
        backend = self.backends.get(rec.get("backend") or "")
        run_id = rec.get("backend_job")
        if not run_id and requeue is not None and res.get("asked") and res.get("kind") in AGAIN:
            clear_unrun(path, res["kind"])
            requeue.append(entry)
            return None
        if not run_id or backend is None or not res.get("kind"):
            why = ("the server stopped before it reached its backend, so nothing was spent: "
                   + AGAIN.get(res.get("kind") or entry.get("kind"), "queue it again"))
            if run_id and backend is None:
                why = f"its backend ({rec.get('backend')}) isn't set up any more"
            T.update_sidecar(path, status="failed", finished=T.now(), save_notes=why, error=why)
            self._emit("seriesmith.episode", {"ep": res.get("ep")})
            return None
        return self._attach(entry.get("title") or res.get("kind"), path, res, backend, run_id,
                            "picked up again after a restart")

    def _attach(self, title: str, path: str, res: dict, backend, run_id: str, why: str) -> str:
        """A queue job that follows run `run_id` on `backend` and collects it
        into the record at `path` (kind and where: `res`)."""
        kind, ep = res["kind"], res.get("ep")

        def work(qjob: QJob, report) -> str:
            progress = progress_to(report)
            report(line=f"{why}: run {run_id} on {backend.name}")
            try:
                run = backend.attach(run_id, res.get("model"))
                self.queue.arm_cancel(qjob, run.cancel)
                status = run.watch(on_progress=progress)
                result = self._collect(res, run, status, backend.name)
            except Exception as e:                       # noqa: BLE001  the record fails
                note = stopped(qjob) if qjob.cancel_asked else f"found again, then: {e}"[:800]
                T.update_sidecar(path, status="failed", finished=T.now(), save_notes=note,
                                 error=note)
                qjob.error, result = note, "failed"
            report(line=f"{kind} {result}")
            self._emit("seriesmith.episode", {"ep": ep})
            if kind == "render":
                take = T.get_take(ep, res["pass"], res["shot"], res["take"])
                if take is not None:
                    self._take_event(ep, take)
            return ending(qjob, result == "ok")

        qjob = QJob(kind=kind, lane=backend.name, title=f"{title} (found again)", work=work,
                    info={k: res.get(k) for k in ("ep", "pass", "shot", "take", "ref", "view", "tour")
                          if res.get(k) is not None} | {"backend": backend.name},
                    limit=LIMITS.get(kind), record=path, resume=res)
        # the record is followed under the new job (the editor's progress, the
        # sweeps' "is its job alive"), then the job queued
        T.update_sidecar(path, comfy_prompt_id=qjob.id, status="queued")
        self._submit(qjob)
        return qjob.id

    def _collect(self, res: dict, run, status: str, backend_name: str) -> str:
        """A run collected into its record, by kind: "ok" or "failed"."""
        from seriesmith import finishing as F
        from seriesmith import refs as R
        from seriesmith import render as RD
        from seriesmith import tour as TR
        kind, ep = res["kind"], res["ep"]
        if kind == "render":
            take = T.get_take(ep, res["pass"], res["shot"], res["take"])
            if take is None:
                raise RuntimeError("its take is gone")
            return RD.collect_run(take, run, status, res)
        if kind == "ref":
            s = R.load_series(ep)
            take = R.get_take(R.find_ref(s, res["ref"]), res.get("view"), res["take"])
            return collect_ref(take, run, status, res, backend_name)
        if kind in ("upscale", "post"):
            take = T.get_take(ep, res["pass"], res["shot"], res["take"])
            if take is None:
                raise RuntimeError("its take is gone")
            fin = F.Finish(kind, ep, take, {}, res["sidecar"], res["out_mp4"],
                           res.get("last"), res.get("latent"))
            if not res.get("saver"):
                raise RuntimeError("it was found again, but which node saves it wasn't recorded")
            return F.collect(fin, run, res["saver"], status, res.get("extra"))
        if kind == "tour":
            s = R.load_series(ep)
            ref = R.find_ref(s, res["ref"])
            side = next(d for d in TR.list_tours(ref) if d.get("tour") == res["tour"])
            collect_tour(s, ref, side, run, status, None)
            return "ok"
        raise RuntimeError(f"no way to collect a {kind}")

    def _collect_finished(self, qjob: QJob, backend) -> bool:
        """A retry of a failed job that reached a paid backend: when its run
        finished after all (the connection to it was lost, not the run), it is
        collected again into the same record rather than paid for twice.
        Whether it was isn't known from here without asking: so asked."""
        if not backend.paid or not qjob.record:
            return False
        rec = T.read_json(qjob.record) or {}
        run_id = rec.get("backend_job")
        if not run_id or rec.get("status") == "ok":
            return False
        try:
            if backend.attach(run_id, (qjob.resume or {}).get("model")).refresh() != "succeeded":
                return False
        except Exception:                                # noqa: BLE001  can't tell: run it again
            return False
        self._attach(qjob.title, qjob.record, qjob.resume or {}, backend, run_id,
                     "it had finished after all")
        return True

    def _take_event(self, ep: str, take: T.Take) -> None:
        t = T.get_take(take_root(take), take.pass_, take.shot, take.take) or take
        from seriesmith import edit as E
        self._emit("seriesmith.take", {"ep": ep, "pass": t.pass_, "shot": t.shot, "take": t.take,
                                   "status": t.status, "thumb": E.rel(ep, t.paths.thumb)})
        self._emit("seriesmith.episode", {"ep": ep})


def clear_unrun(path: str, kind: str) -> None:
    """A record that never ran (it was still waiting in the queue), and what
    was reserved with it, removed: a take's record, frozen shotlist and staged
    inputs (renders/<shot>/<stem>.*, <stem>_*), a ref take's the same in its
    folder, an upscale's or post's record, a tour's record. Asked for again,
    it gets its number back."""
    folder, name = os.path.split(path)
    if kind in ("upscale", "post", "tour"):
        stems = [name]
    else:
        stem = name[:-len(".json")] if name.endswith(".json") else name
        stems = [stem + ".", stem + "_"]
    for f in os.listdir(folder) if os.path.isdir(folder) else []:
        if any(f == s or (s.endswith((".", "_")) and f.startswith(s)) for s in stems):
            full = os.path.join(folder, f)
            try:
                if os.path.isfile(full):
                    os.remove(full)
            except OSError:
                pass


def requeue_plan(entries: list[dict]) -> list[dict]:
    """The requests to ask again for jobs that were waiting when the server
    stopped: each queuing request once, in the order its jobs were queued,
    narrowed to what was still waiting (renders: those shots; ref pictures:
    as many as were waiting of that ref view; upscales and posts: those
    takes; tours: that many). Master and Generate missing plan only what
    isn't done or queued, so they are asked again as they were.
    [{"path", "body"}]."""
    groups: dict[str, dict] = {}
    for e in sorted(entries, key=lambda e: e.get("created") or 0):
        res = e.get("resume") or {}
        a = res.get("asked") or {}
        if not a.get("path") or not isinstance(a.get("body"), dict):
            continue
        key = a["path"] + "\n" + json.dumps(a["body"], sort_keys=True, default=str)
        g = groups.setdefault(key, {"path": a["path"], "body": dict(a["body"]), "items": []})
        g["items"].append(res)
    out = []
    for g in groups.values():
        path, body, items = g["path"], g["body"], g["items"]
        if path.endswith("/render"):
            shots = list(dict.fromkeys(r["shot"] for r in items))
            body["shots"] = shots
        elif path.endswith("/refs/generate"):
            body["count"] = len(items)
        elif path.endswith(("/upscale", "/post")):
            body["shots"] = None
            body["takes"] = [{"shot": r["shot"], "take": r["take"]} for r in items]
        elif path.endswith("/refs/tour"):
            body["count"] = len(items)
        out.append({"path": path, "body": body})
    return out


# how a job the server lost before it ran is queued again, by kind
AGAIN = {"render": "Generate missing (Shots tab) queues it again",
         "ref": "Generate missing (Refs tab) queues it again",
         "upscale": "Master (or Upscale) runs it again",
         "post": "Master (or Post-process) runs it again",
         "tour": "start the tour again"}


def collect_ref(take, run, status: str, res: dict, backend_name: str) -> str:
    """A reference take's run, ended with `status`, collected: the picture (or
    voice) it returned closes the take (refs.close_take). Raises when there's
    nothing to close it with."""
    import os
    import tempfile

    from seriesmith import refs as R
    if status != "succeeded":
        raise RuntimeError(run.error or f"the job ended {status}")
    want, hosted, is_audio = res["want"], res.get("hosted"), res.get("is_audio")
    outs = [o for o in run.outputs() if o.type == want]
    if hosted and not outs:
        # a provider's signed URLs often have no extension to type them by
        outs = [o for o in run.outputs() if o.type in (want, "file")]
    outs = [o for o in outs if o.node in (res.get("savers") or [])] or outs
    if not outs:
        raise RuntimeError(f"the job finished but returned no {want}")
    fd, tmp = tempfile.mkstemp(suffix=os.path.splitext(outs[0].name)[1])
    os.close(fd)
    try:
        outs[0].save(tmp)
        ext = os.path.splitext(outs[0].name)[1].lower() if is_audio else None
        if is_audio and ext != ".wav":
            # ComfyUI's own SaveAudio writes flac; a voice sample is a wav (as
            # h3pipe's saver made it), so it is converted here
            ext = ".wav" if _to_wav(tmp) else ext
        with open(tmp, "rb") as fh:
            data = fh.read()
    finally:
        os.remove(tmp)
    if not is_audio and hosted:
        ext = R.image_ext(data)
    out = R.close_take(take, data, f"from {backend_name}: {outs[0].name}", ext=ext)
    result = getattr(run, "result", None)
    if hosted and isinstance(result, dict):
        # what the provider says of it (its own task id, usage, its own cost figure)
        provider = {k: result[k] for k in ("id", "seed", "usage", "cost") if k in result}
        if provider:
            try:
                T.update_sidecar(take.paths.sidecar, provider=provider)
            except OSError:
                pass
    return out


def collect_tour(s, ref, side: dict, run, status: str, hold) -> None:
    """A tour's run, ended with `status`, collected: its video kept and its
    holds found (tour.keep_tour, which updates `side`). Raises when it failed."""
    import os
    import tempfile

    from seriesmith import tour as TR
    if status != "succeeded":
        raise RuntimeError(run.error or f"the job ended {status}")
    outs = [o for o in run.outputs() if o.name.lower().endswith((".mp4", ".webm", ".mov"))]
    if not outs:
        raise RuntimeError("the job finished without a video")
    fd, tmp = tempfile.mkstemp(suffix=os.path.splitext(outs[0].name)[1])
    os.close(fd)
    try:
        outs[0].save(tmp)

        def write(path):
            F.replace(tmp, path)
        side.update(TR.keep_tour(s, ref, side, write, os.path.splitext(outs[0].name)[1], hold))
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    if side.get("status") != "ok":
        raise RuntimeError(side.get("error") or "the tour failed")


def _to_wav(path: str) -> bool:
    """`path` (any audio ffmpeg reads) rewritten in place as a 16-bit PCM wav;
    False (left as it was) when there's no ffmpeg or it fails."""
    import os
    import subprocess

    from seriesmith import ff as FF
    exe = FF.find("ffmpeg")
    if not exe:
        return False
    out = path + ".wav"
    try:
        subprocess.run([*exe, "-v", "error", "-y", "-i", path, "-c:a", "pcm_s16le", out],
                       capture_output=True, check=True, timeout=120)
        F.replace(out, path)
        return True
    except Exception:                                    # noqa: BLE001  keep what came back
        if os.path.exists(out):
            os.remove(out)
        return False


def _ep_name(ep: str) -> str:
    import os
    return os.path.basename(os.path.normpath(ep))


def take_root(take: T.Take) -> str:
    """The episode folder a take belongs to (renders/<shot>/ -> the episode)."""
    import os
    return os.path.dirname(os.path.dirname(take.paths.dir))


def wait(queue: Queue, ids, timeout: float | None = None, poll: float = 0.25) -> dict[str, str]:
    """Wait for the queue's jobs `ids` to end: {id: status}. A job still queued
    or running at `timeout` (seconds; None: no limit) is cancelled and comes
    back as "timeout"."""
    import time

    from seriesmith.queue import DONE
    ids = [i for i in ids if i]
    end = None if timeout is None else time.time() + timeout
    while True:
        jobs = {i: queue.jobs.get(i) for i in ids}
        if all(j is None or j.status in DONE for j in jobs.values()):
            return {i: (j.status if j is not None else "gone") for i, j in jobs.items()}
        if end is not None and time.time() > end:
            out = {}
            for i, j in jobs.items():
                if j is not None and j.status not in DONE:
                    queue.cancel(i)
                    out[i] = "timeout"
                else:
                    out[i] = j.status if j is not None else "gone"
            return out
        time.sleep(poll)


def queue_for(settings, emit=None, **kw) -> Queue:
    """A queue that keeps this machine's paid limit (Settings: `paid_limit`, None
    no cap): the editor's server and the command line alike, so a paid run past
    it is refused before anything is reserved wherever it is asked for."""
    q = Queue(emit, **kw)
    q.paid_limit = settings.paid_limit
    return q


def cli_runner(backend: str | None = None, settings=None, log=print) -> Runner:
    """A queue and runner of the command line's own, on the backends the
    settings set up. When the work will run on this machine's ComfyUI
    (`backend` local, or None: each job's own, usually local) through
    comfy-api-proxy (local_via "proxy"), the proxy is started in front of it if
    it isn't running (server.standalone.ensure_proxy).
    ValueError when `backend` isn't set up here."""
    from seriesmith.backends import available
    from seriesmith.settings import load_settings
    s = settings or load_settings()
    backends = available(s)
    if backend and J.backend_kind(backend) != "deployment" and backend not in backends:
        raise ValueError(f"{backend} isn't set up on this machine (seriesmith backends: "
                         f"{', '.join(backends)})")
    if backend in (None, "", "local"):
        from seriesmith.server.standalone import ensure_proxy
        note = ensure_proxy(s)
        if log and "not" in note:
            log(f"  ! {note}")
    return Runner(queue_for(s, name="cli"), backends)
