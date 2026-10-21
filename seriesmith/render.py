"""
seriesmith render — render an episode's shots, each as a new take, on its backend.

    seriesmith render Shows/ep05                       every shot without a take
    seriesmith render Shows/ep05 --only sh040,sh050 --redo
    seriesmith render Shows/ep05 --proxy
    seriesmith render Shows/ep05 --only sh040 --target seedance_2_5
    seriesmith render Shows/ep05 --only sh040 --list   what would run, where, and why not
    seriesmith render Shows/ep05 --only sh040 --dry-run   write what would be sent, run nothing

Planning is h3pipe's (seriesmith.jobs): the shot's target, its seed, model
files resolved against ComfyUI's loaders, overrides.json, missing refs. What
changes is how a take is made:

- A workflow target's graph is made portable (the shot and its reference files
  go up as inputs; the saver reports its files), the backend runs it, and
  seriesmith writes the take: its files into renders/<shot>/ and the saver's
  record into the take's record.
- A hosted target (Comfy Router) is one model call; its video becomes the
  take's mp4 and seriesmith makes the thumbnails (seriesmith.finish).

Backends
    Each shot runs where jobs.backend_choice says: --backend, else the shot's
    `backend` in overrides.json, the episode's, the series config's
    `series.backend`, else its target's own first (a Router target's is
    router; a workflow target's is local). A default that doesn't suit a
    target falls back to the target's own, with a note. local is your own
    ComfyUI, straight to its own API (or through comfy-api-proxy, with
    local_via "proxy": docs/SETUP.md); model files are resolved
    against its loaders. Each take is a job on this process's own queue
    (runner.Runner), run one at a time: its inputs are staged as it starts, so
    a `continuous: latent` shot holds the take rendered just before it, on any
    backend.

Takes and seeds
    A shot with a finished take (or one still queued) is skipped. --redo
    renders it again as the next take; --take N forces a number. The first
    take uses the shotlist's seed (from the ids); --redo picks a new one unless
    --same-seed; --seed N uses N; --new-seed forces a fresh one. A hosted
    model decides what a seed means, so its takes are marked
    `reproducible: false`.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

from seriesmith import jobs as J
from seriesmith import takes as T
from seriesmith import targets as TG
from seriesmith.backends import BackendError, File, available, files_in
from seriesmith.settings import load_settings


def fmt(sec: float) -> str:
    m, s = divmod(int(sec), 60)
    return f"{m}:{s:02d}"


def episode_bound(g: dict) -> list[str]:
    """Nodes of a portable graph that still read the episode folder (a
    continuous shot's chain or continuity node): they need a backend that
    shares this machine's disk."""
    return [f"{v['class_type']} ({k})" for k, v in g.items()
            if "project_root" in (v.get("inputs") or {})]


def hosted(target: TG.Target) -> bool:
    """A target rendered by a model call, not a workflow (target.json `router`)."""
    return bool(target.spec.get("router"))


def parse_args(argv):
    ap = argparse.ArgumentParser(prog="seriesmith render", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("episodes", nargs="+", help="episode folders (each holds shotlist/)")
    ap.add_argument("--backend",
                    help="render every shot here: local, cloud, router, deployment[:<target>] "
                         "(default: each shot's own; seriesmith backends lists them)")
    ap.add_argument("--proxy", action="store_true", help="render the proxy pass")
    ap.add_argument("--only", help="comma-separated shot ids, e.g. sh040,sh050")
    ap.add_argument("--redo", action="store_true", help="render finished shots again as a new take")
    ap.add_argument("--take", type=int, help="force this take number (overwrites it)")
    sd = ap.add_mutually_exclusive_group()
    sd.add_argument("--seed", type=int, help="render with this seed")
    sd.add_argument("--same-seed", action="store_true", help="keep the shotlist's seed on a redo")
    sd.add_argument("--new-seed", action="store_true", help="a fresh seed even on a first render")
    ap.add_argument("--lora", action="append", metavar="NAME[:STRENGTH]",
                    help="LoRA for this run; repeat to stack; 'none' for no LoRA")
    ap.add_argument("--model", help="model file for this run")
    ap.add_argument("--steps", type=int, help="sampler steps for this run")
    ap.add_argument("--size", metavar="WxH", help="render at this size for this run")
    ap.add_argument("--note", default="", help="free text stored in each take's record")
    ap.add_argument("--target", metavar="TARGET", help="render on this video target for this run")
    ap.add_argument("--allow-missing-refs", action="store_true",
                    help="render even when references are missing (flat grey stand-ins)")
    ap.add_argument("--allow-model-mismatch", action="store_true",
                    help="render even when a model file is another family than its target's")
    ap.add_argument("--panel-mode", choices=["auto", "full", "pair", "face", "body"])
    ap.add_argument("--save-frames", action="store_true", default=None,
                    help="keep each take's frames as PNGs too (frames/ beside it)")
    lt = ap.add_mutually_exclusive_group()
    lt.add_argument("--latent", dest="save_latent", action="store_true", default=None,
                    help="keep each take's latent (default: final pass only)")
    lt.add_argument("--no-latent", dest="save_latent", action="store_false")
    ap.add_argument("--list", action="store_true", help="show the job list and stop")
    ap.add_argument("--dry-run", action="store_true",
                    help="write what the first shot would send (render_graph.json, or "
                         "render_call.json for a hosted model), run nothing")
    ap.add_argument("--stop-on-error", action="store_true",
                    help="stop at the first failed shot")
    return ap, ap.parse_args(argv)


def as_json(value):
    """A graph or call with its File inputs shown as {"File": path}."""
    return json.loads(json.dumps(value, default=lambda f: {"File": f.path}))


def continuity_before_render(root: str, pass_: str, only, dry_run: bool = False):
    """Each `first: continuity` / `continuous: latent` shot of the render made to
    start from the take the cut uses now (refs.refresh_continuity, as the
    editor's render does: a missing or stale keyframe is cut again), said on
    the console. Returns (the shots to render: `only` less any with nothing to
    start from, None for all; the shots whose first frame is cut again as
    their render starts, for RenderRequest.continuity)."""
    from seriesmith import refs as R
    try:
        s = R.load_series(root)
    except Exception:                                     # noqa: BLE001  no series config
        return only, {}
    res = R.refresh_continuity(s, pass_, sorted(only) if only else None, dry_run=dry_run)
    for c in res["cut"]:
        print(f"  {'would cut' if dry_run else 'cut'} {c['shot']}'s first frame from {c['from']} "
              f"({c['why']})")
    for w in res["wait"]:
        what = (f"{w['after']} t{w['take']:02d}, still rendering" if w.get("take")
                else f"{w['after']}'s new take in this run")
        if w.get("chain"):
            print(f"  .. {w['shot']}: continues {what} (its latent, else its last frames)")
        else:
            print(f"  .. {w['shot']}: its first frame is cut from {what} when its render starts")
    for e in res["errors"]:
        print(f"  !! {e['shot']}: {e['error']}")
    held = {e["shot"] for e in res["errors"]}
    if held:
        only = {x for x in (only if only is not None else J.script_order(root)) if x not in held}
    return only, res["live"]


def main(argv: list[str] | None = None) -> int:
    ap, args = parse_args(argv)
    pass_ = "proxy" if args.proxy else "final"
    roots = [os.path.abspath(p) for p in args.episodes]
    for r in roots:
        TG.add_thread_root(r)
    if args.target:
        try:
            J.check_video_target(args.target)
        except Exception as e:
            ap.error(str(e))
    loras = [lo for spec in args.lora for lo in J.parse_lora(spec)] if args.lora else None
    template = J.RenderRequest(
        shot_id="", take=args.take, redo=args.redo, seed=args.seed,
        seed_mode="new" if args.new_seed else "same" if args.same_seed else "auto",
        model=args.model or None, loras=loras, steps=args.steps, note=args.note,
        allow_missing_refs=args.allow_missing_refs, target=args.target,
        allow_model_mismatch=args.allow_model_mismatch, save_latent=args.save_latent,
        size=args.size)
    only = {s.strip() for s in args.only.split(",")} if args.only else None

    try:
        settings = load_settings()
    except ValueError as e:
        print(f"seriesmith: {e}", file=sys.stderr)
        return 1
    backends = available(settings)
    if args.backend and J.backend_kind(args.backend) not in TG.BACKENDS:
        ap.error(f"{args.backend!r} is not a backend ({', '.join(TG.BACKENDS)})")

    # ComfyUI itself, for its loaders' model lists and its saved workflows. Asked only when a shot renders there.
    comfy = J.Comfy(settings.comfyui_url)
    workflows: dict = {}
    # a target's workflow as saved in that ComfyUI wins over the repo's copy,
    # but only for a run that renders there (set once the shots are planned)
    use_comfy = {"url": None}

    def base_for(target_id: str):
        if target_id not in workflows:
            t = TG.load_target(target_id, "video", root=roots[0])
            workflows[target_id] = J.target_workflow(t, None, use_comfy["url"])
        return workflows[target_id]

    model_resolve = J.model_resolver()
    model_cache = TG.modelid.temp_cache()
    listing = None
    cloud_listing: dict = {}                      # a cloud backend's name -> its model_lister
    plans = []
    where: dict[int, str] = {}                    # id(job) -> backend name
    total_frames = 0
    for root in roots:
        # continuity first, as the editor's render does: a shot with nothing
        # to start from isn't planned (it would render without its first frame)
        only_r, live = continuity_before_render(root, pass_, only, args.dry_run or args.list)
        template.continuity = live or None
        if only_r is not None and not only_r:
            print(f"\n  {os.path.basename(root)}  ·  nothing to render")
            continue
        try:
            jobs = J.plan_episode(root, pass_, default=template, only=only_r)
        except FileNotFoundError as e:
            print(f"  ! {e}")
            continue
        ov = T.load_overrides(root)
        for j in jobs:
            t = J.job_target(j)
            if j.runs:
                try:
                    name, _src, note = J.backend_choice(ov, j.id, t, args.backend, root)
                except ValueError as e:
                    j.action, j.error = "error", str(e)
                    continue
                if note:
                    j.notes.append(note)
                if name not in backends:
                    why = (f"{name} isn't set up on this machine"
                           + (" (it needs COMFY_API_KEY)" if J.backend_kind(name) != "local"
                              else "") + "; seriesmith backends lists what is")
                    if not (args.dry_run or args.list):
                        j.action, j.error = "error", why
                        continue
                    j.notes.append(why)      # still shown: nothing is sent
                where[id(j)] = name
            if hosted(t):
                continue                                  # no model files to resolve
            on = backends.get(where[id(j)]) if j.runs and id(j) in where else None
            if on is not None and on.own_models:
                # the files Comfy Cloud has, not this machine's: a missing
                # accelerator LoRA renders the base preset there
                if on.name not in cloud_listing:
                    cloud_listing[on.name] = J.model_lister(on)
                use = cloud_listing[on.name]
            else:
                if on is not None and on.shares_disk and listing is None \
                        and not args.dry_run:
                    listing = J.model_lister(comfy)
                use = listing
            J.resolve_models(j, use, model_resolve, model_cache)
            J.check_models(j, model_resolve, model_cache)
        todo = [j for j in jobs if j.runs]
        plans.append((root, jobs))
        total_frames += sum(j.frames for j in todo)
        not_run = [j for j in jobs if not j.runs and j.action not in ("skip", "busy")]
        on = sorted({where[id(j)] for j in todo if id(j) in where})
        print(f"\n  {os.path.basename(root)}  ·  {len(todo)} to render, "
              f"{sum(1 for j in jobs if j.action == 'skip')} done"
              + (f", {sum(1 for j in jobs if j.action == 'busy')} already queued"
                 if any(j.action == "busy" for j in jobs) else "")
              + (f", {len(not_run)} can't run" if not_run else "")
              + f"  ·  {pass_}" + (f"  ·  on {', '.join(on)}" if on else ""))
        for j in not_run[:12]:
            why = (j.error if j.action == "error" else
                   j.blocked_reason() if j.action == "blocked" and j.no_anyway else
                   f"missing {j.missing_note()}" if j.action == "blocked" else
                   j.mismatch_note() if j.action == "mismatch" else
                   j.missing_files_note() if j.action == "missing_files" else j.action)
            print(f"    ! {j.id}: {why}")
        for j in todo:
            for n in j.notes:
                print(f"    ~ {j.id}: {n}")
        if args.list or args.dry_run:
            for j in jobs:
                extra = (f"  on {where.get(id(j), '?')}  seed {j.seed} ({j.seed_source})"
                         if j.runs else "")
                print(f"    [{j.action:>9}] {j.id:<8} t{j.take:02d}  {j.frames:>4}f  "
                      f"{j.target:<18} {j.shot.get('audio_policy', '')}{extra}")
    n_todo = sum(1 for _, js in plans for j in js if j.runs)
    if any(n in backends and backends[n].shares_disk for n in where.values()):
        use_comfy["url"] = settings.comfyui_url
    if args.list:
        return 0
    gkw = dict(panel_mode=args.panel_mode, review_copy=False, portable=True)
    if args.dry_run:
        return dry_run(plans, pass_, base_for, gkw,
                       {id_: backends.get(n) for id_, n in where.items()})
    if not n_todo:
        print("\n  nothing to do: --redo renders new takes.\n")
        return 0
    for name in sorted(set(where.values())):
        why = backends[name].ping()
        if why:
            print(f"\n  !! {name}: {why}\n     (seriesmith backends; docs/SETUP.md)")
            return 1

    fps = next((j.fps for _, js in plans for j in js if j.runs), 24.0)
    print(f"\n  {n_todo} shot(s), {total_frames / fps:.1f}s of video\n")
    done = failed = 0
    failures = []
    t_start = time.time()
    frames_done = 0
    current = None
    # each take is a job on a queue of this process's own (runner.Runner), run
    # one at a time and waited for: its inputs are staged as it starts, so a
    # `continuous: latent` shot holds the take rendered just before it
    from seriesmith import runner as RN
    from seriesmith.queue import Queue
    shown = {"t0": time.time()}

    def heard(event, data):
        if event == "progress":
            print(f"\r     {data.get('value', 0):4d}%  [{fmt(time.time() - shown['t0'])}]   ",
                  end="", flush=True)
    runner = RN.Runner(Queue(heard), backends)
    current = None
    try:
        for root, jobs in plans:
            ep = os.path.basename(root)
            for j in (j for j in jobs if j.runs):
                t0 = shown["t0"] = time.time()
                label = f"{ep}/{j.id}"
                backend = backends[where[id(j)]]
                target = J.job_target(j)
                try:
                    base = None if hosted(target) else base_for(j.target)[0]
                    take, qid = runner.enqueue_render(
                        j, base, backend.name, probe=comfy if backend.shares_disk else None,
                        continuity=j.continuity, save_frames=args.save_frames,
                        review_copy=False, panel_mode=args.panel_mode)
                except (J.NotPortable, BackendError, ValueError, OSError, RuntimeError) as e:
                    failed += 1
                    failures.append(label)
                    print(f"  !! {label}: {e}", flush=True)
                    continue
                label = f"{ep}/{j.id} t{take.take:02d}"
                print(f"  .. {label}  ({j.frames}f, {j.target} on {backend.name}, "
                      f"{j.shot.get('audio_policy', '')}, seed {j.seed} {j.seed_source})",
                      flush=True)
                current = qid
                RN.wait(runner.queue, [qid])
                current = None
                print("\r" + " " * 60 + "\r", end="", flush=True)
                take = T.get_take(root, pass_, j.id, take.take) or take
                for line in runner.queue.jobs[qid].log:
                    if line.startswith("holds "):
                        print(f"     {line}")
                if take.status != "ok":
                    failed += 1
                    failures.append(label)
                    print(f"  !! {label}: {(take.sidecar or {}).get('save_notes') or take.status}",
                          flush=True)
                    if args.stop_on_error:
                        raise KeyboardInterrupt
                    continue
                done += 1
                frames_done += j.frames
                rate = (time.time() - t_start) / max(frames_done, 1)
                left = (total_frames - frames_done) * rate
                print(f"  -> {take.paths.mp4}  [{fmt(time.time() - t0)}, ~{fmt(left)} left]",
                      flush=True)
    except KeyboardInterrupt:
        print("\n  stopping")
        if current is not None:
            runner.queue.cancel(current)
            RN.wait(runner.queue, [current], 30)
    print(f"\n  done in {fmt(time.time() - t_start)}: {done} rendered"
          + (f", {failed} failed: {', '.join(failures)}" if failed else "") + "\n")
    return 1 if failed else 0


def dry_run(plans, pass_: str, base_for, gkw: dict, on: dict | None = None) -> int:
    """Write what the first shot that would run would send; nothing is
    reserved, written or uploaded. `on`: id(job) -> its backend (a Comfy
    Cloud one gets the graph made of Cloud's nodes, seriesmith.cloud.lower;
    the files it would upload are left in a folder it names)."""
    for root, jobs in plans:
        for j in (j for j in jobs if j.runs):
            take = T.Take(j.id, j.take, pass_, T.take_paths(root, pass_, j.id, j.take))
            target = J.job_target(j)
            if hosted(target):
                model, call = target.module.router_call(target, j)
                out = os.path.join(os.getcwd(), "render_call.json")
                with open(out, "w", encoding="utf-8") as fh:
                    json.dump({"model": model, "arguments": as_json(call)}, fh, indent=2,
                              ensure_ascii=False)
                n = sum(1 for c in call.get("content") or [] if isinstance(
                    (c.get("image_url") or {}).get("url"), File))
                print(f"\n  wrote {out} ({j.id}, {model}; {n} picture(s) to upload)")
                return 0
            backend = (on or {}).get(id(j))
            plan = None
            try:
                J.stage_portable(j)
                g = J.graph_for(base_for(j.target)[0], j, take, **gkw)
                if backend is not None:
                    g, plan = backend.prepare(g, j, take)
            finally:
                if plan is None:
                    unstage(j)
            out = os.path.join(os.getcwd(), "render_graph.json")
            with open(out, "w", encoding="utf-8") as fh:
                json.dump(as_json(g), fh, indent=2)
            if plan is not None:
                ups = len({f.path for _, _, f in files_in(g)})
                print(f"\n  wrote {out} ({j.id}, {j.target} as Comfy Cloud's nodes; {ups} "
                      f"file(s) to upload, made in {plan['staging']})")
                for n in plan["notes"]:
                    print(f"  ~ {n}")
                return 0
            ups = len(J.shot_files(j)) if J.job_target(j).binding.loader_class \
                else len(j.input_files)
            print(f"\n  wrote {out} ({j.id}, {j.target}; {ups} file(s) to upload)")
            bound = episode_bound(g)
            if bound:
                print(f"  ! reads the episode folder: {', '.join(bound)}")
            return 0
    return 0


def prepare(job: J.Job, take: T.Take, backend, base: dict | None, gkw: dict):
    """What a started take sends: ("call", (model, arguments)) for a hosted
    target; ("cloud", (graph, plan)) on Comfy Cloud, the portable graph made of
    Cloud's own nodes (seriesmith.cloud.lower; `plan` is what collecting it
    needs); else ("graph", the portable graph). NotPortable for a graph that
    still reads the episode folder, on a backend that doesn't share its disk."""
    target = J.job_target(job)
    if hosted(target):
        return "call", target.module.router_call(target, job)
    g = J.graph_for(base, job, take, **gkw)
    from seriesmith.shotnodes import uses_h3pipe
    if gkw.get("portable") and uses_h3pipe(g):
        raise J.NotPortable(f"still uses h3pipe's nodes: {', '.join(uses_h3pipe(g))}")
    g, plan = backend.prepare(g, job, take)
    if plan is not None:
        # lowered for where it runs (Comfy Cloud's own nodes): collected by the plan
        if plan["notes"]:
            had = (T.read_sidecar(take.paths.sidecar) or {}).get("notes") or []
            T.update_sidecar(take.paths.sidecar, notes=list(had) + plan["notes"])
        return "cloud", (g, plan)
    bound = episode_bound(g)
    if bound and not backend.shares_disk:
        raise J.NotPortable(f"reads the episode folder ({', '.join(bound)}): local only for now")
    return "graph", g


def run_take(job: J.Job, take: T.Take, backend, base: dict | None, gkw: dict,
             on_progress=None, on_run=None, prompt_id: str | None = None,
             on_resume=None, on_status=None) -> str:
    """Render a started take on `backend` and collect it: the portable graph
    (or a hosted model's call) submitted, followed (on_progress gets each
    backends.Progress), and its outputs written into the take. `on_run(run)`
    hears of the backend's run as soon as there is one (to cancel it);
    `on_resume(bits)` gets what collect_run needs to collect it again (after a
    restart: recover.py). `prompt_id` is what the take's record calls its job
    (seriesmith's queue's id; default the backend's). Returns the take's
    status: "ok", "failed"."""
    kind, what = prepare(job, take, backend, base, gkw)
    if kind == "cloud":
        from seriesmith import cloud as C
        what, plan = what
        try:
            run = backend.submit(what)
        finally:
            C.done_sending(plan)
    else:
        run = backend.call(*what) if kind == "call" else backend.submit(what)
    if on_run is not None:
        on_run(run)
    J.mark_submitted(take, backend.name, run.id, prompt_id)
    bits = ({"model": what[0], "arguments": as_json(what[1]), "saver": None} if kind == "call"
            else {"model": None, "arguments": None, "saver": None,
                  "cloud": {k: v for k, v in plan.items() if k != "staging"}}
            if kind == "cloud"
            else {"model": None, "arguments": None, "saver": J.node_of(what, J.PORTABLE_SAVER)})
    if on_resume is not None:
        on_resume(bits)
    status = run.watch(on_progress=on_progress,
                       on_status=(lambda st: on_status(run, st)) if on_status else None)
    return collect_run(take, run, status, bits)


def collect_run(take: T.Take, run, status: str, bits: dict) -> str:
    """A take's run, ended with `status`, collected into the take: a hosted
    model's video (bits["model"]), a Comfy Cloud run's (bits["cloud"]:
    seriesmith.cloud.collect) or the portable saver's files (bits["saver"])."""
    if bits.get("model"):
        return J.collect_router_take(take, run, status, bits.get("arguments"))
    if bits.get("cloud"):
        from seriesmith import cloud as C
        return C.collect(take, run, status, bits["cloud"])
    return J.collect_take(take, run, bits.get("saver"), status)


def start_job_portable(job: J.Job, probe=None) -> T.Take:
    """start_job, for a portable render: the job's inputs worked out and made
    (stage_portable: keyframes, a composed reference sheet), nothing uploaded
    yet; then the take reserved and its record and frozen shotlist written.
    `probe` is ComfyUI itself when the job renders there (asked about
    `dur: model`), else None."""
    J.stage_portable(job, probe)
    return J.start_job(job)


def unstage(job: J.Job) -> None:
    """Remove what stage_portable made for a job that won't run (a dry run)."""
    for f in job.staged:
        if os.path.isfile(f["tmp"]):
            os.remove(f["tmp"])
    job.staged = []


def progress_line(t0: float):
    def show(p) -> None:
        step = f"  step {p.step}/{p.steps}" if p.step and p.steps else ""
        print(f"\r     {p.value:4.0%}{step}  [{fmt(time.time() - t0)}]   ", end="", flush=True)
    return show


if __name__ == "__main__":
    raise SystemExit(main())
