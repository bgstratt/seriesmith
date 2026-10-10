"""
seriesmith render — render an episode's shots, each as a new take, on a backend.

    seriesmith render Shows/ep05                       every shot without a take
    seriesmith render Shows/ep05 --only sh040,sh050 --redo
    seriesmith render Shows/ep05 --proxy
    seriesmith render Shows/ep05 --only sh040 --list   what would run, and why not
    seriesmith render Shows/ep05 --only sh040 --dry-run   write the graph, run nothing

Planning is h3pipe's (seriesmith.jobs): the shot's target, its seed, model
files resolved against ComfyUI's loaders, overrides.json, missing refs. What
changes is how a take is made: the target's workflow is made portable (the
shot and its reference files go up as inputs; the saver reports its files),
the backend runs it, and seriesmith writes the take: its files into
renders/<shot>/ and the saver's record into the take's record.

Takes and seeds
    A shot with a finished take (or one still queued) is skipped. --redo
    renders it again as the next take; --take N forces a number. The first
    take uses the shotlist's seed (from the ids); --redo picks a new one unless
    --same-seed; --seed N uses N; --new-seed forces a fresh one.

Backends
    --backend local (the default) is your own ComfyUI through comfy-api-proxy
    (docs/SETUP.md). Model files are resolved against that ComfyUI's loaders.
    Continuous shots (`continuous: latent`) still read the previous take from
    the episode folder, so they render on local only (docs/PLAN.md, step 5).
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
from seriesmith.backends import BackendError, available
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


def parse_args(argv):
    ap = argparse.ArgumentParser(prog="seriesmith render", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("episodes", nargs="+", help="episode folders (each holds shotlist/)")
    ap.add_argument("--backend", default="local",
                    help="where to render: local (default), cloud, deployment:<target> "
                         "(seriesmith backends lists them)")
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
    lt = ap.add_mutually_exclusive_group()
    lt.add_argument("--latent", dest="save_latent", action="store_true", default=None,
                    help="keep each take's latent (default: final pass only)")
    lt.add_argument("--no-latent", dest="save_latent", action="store_false")
    ap.add_argument("--list", action="store_true", help="show the job list and stop")
    ap.add_argument("--dry-run", action="store_true",
                    help="write the first shot's portable graph to render_graph.json, run nothing")
    ap.add_argument("--stop-on-error", action="store_true",
                    help="stop at the first failed shot")
    return ap, ap.parse_args(argv)


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
    backend = backends.get(args.backend)
    if backend is None:
        ap.error(f"no backend called {args.backend!r} ({', '.join(backends)})")
    # ComfyUI itself: its loaders' model lists and its saved workflows (the
    # proxy serves neither). Only meaningful when the backend is that ComfyUI.
    comfy = J.Comfy(settings.comfyui_url) if backend.kind == "local" else None

    workflows: dict = {}

    def base_for(target_id: str):
        if target_id not in workflows:
            t = TG.load_target(target_id, "video", root=roots[0])
            workflows[target_id] = J.target_workflow(t, None, settings.comfyui_url
                                                     if comfy else None)
        return workflows[target_id]

    model_resolve = J.model_resolver()
    model_cache = TG.modelid.temp_cache()
    listing = None
    if comfy is not None and not args.dry_run:
        listing = J.model_lister(comfy)
    plans = []
    total_frames = 0
    for root in roots:
        try:
            jobs = J.plan_episode(root, pass_, default=template, only=only)
        except FileNotFoundError as e:
            print(f"  ! {e}")
            continue
        for j in jobs:
            J.resolve_models(j, listing, model_resolve, model_cache)
            J.check_models(j, model_resolve, model_cache)
        todo = [j for j in jobs if j.runs]
        plans.append((root, jobs))
        total_frames += sum(j.frames for j in todo)
        not_run = [j for j in jobs if not j.runs and j.action not in ("skip", "busy")]
        print(f"\n  {os.path.basename(root)}  ·  {len(todo)} to render, "
              f"{sum(1 for j in jobs if j.action == 'skip')} done"
              + (f", {sum(1 for j in jobs if j.action == 'busy')} already queued"
                 if any(j.action == "busy" for j in jobs) else "")
              + (f", {len(not_run)} can't run" if not_run else "")
              + f"  ·  {pass_}  ·  on {backend.name}")
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
                extra = f"  seed {j.seed} ({j.seed_source})" if j.runs else ""
                print(f"    [{j.action:>9}] {j.id:<8} t{j.take:02d}  {j.frames:>4}f  "
                      f"{j.target:<18} {j.shot.get('audio_policy', '')}{extra}")
    n_todo = sum(1 for _, js in plans for j in js if j.runs)
    if args.list:
        return 0
    gkw = dict(panel_mode=args.panel_mode, review_copy=False, portable=True)
    if args.dry_run:
        for root, jobs in plans:
            for j in (j for j in jobs if j.runs):
                take = T.Take(j.id, j.take, pass_, T.take_paths(root, pass_, j.id, j.take))
                g = J.graph_for(base_for(j.target)[0], j, take, **gkw)
                out = os.path.join(os.getcwd(), "render_graph.json")
                with open(out, "w", encoding="utf-8") as fh:
                    json.dump(g, fh, indent=2, default=lambda f: {"File": f.path})
                print(f"\n  wrote {out} ({j.id}, {j.target}; "
                      f"{len(J.shot_files(j))} file(s) to upload)")
                bound = episode_bound(g)
                if bound:
                    print(f"  ! reads the episode folder: {', '.join(bound)}")
                return 0
        return 0
    if not n_todo:
        print("\n  nothing to do: --redo renders new takes.\n")
        return 0
    why = backend.ping()
    if why:
        print(f"\n  !! {backend.name}: {why}\n     (seriesmith backends; docs/SETUP.md)")
        return 1

    fps = next((j.fps for _, js in plans for j in js if j.runs), 24.0)
    print(f"\n  {n_todo} shot(s), {total_frames / fps:.1f}s of video\n")
    done = failed = 0
    failures = []
    t_start = time.time()
    frames_done = 0
    current = None
    try:
        for root, jobs in plans:
            ep = os.path.basename(root)
            for j in (j for j in jobs if j.runs):
                t0 = time.time()
                label = f"{ep}/{j.id}"
                take = None
                try:
                    base = base_for(j.target)[0]
                    take = start_job_portable(j)
                    label = f"{ep}/{j.id} t{take.take:02d}"
                    g = J.graph_for(base, j, take, **gkw)
                    bound = episode_bound(g)
                    if bound and backend.kind != "local":
                        raise J.NotPortable(f"reads the episode folder ({', '.join(bound)}): "
                                            f"local only for now")
                except (J.NotPortable, ValueError, FileNotFoundError) as e:
                    failed += 1
                    failures.append(label)
                    if take is not None:
                        J.mark_failed(take, str(e)[:800])
                    print(f"  !! {label}: {e}", flush=True)
                    continue
                print(f"  .. {label}  ({j.frames}f, {j.target}, "
                      f"{j.shot.get('audio_policy', '')}, seed {j.seed} {j.seed_source})",
                      flush=True)
                try:
                    current = (take, None)
                    run = backend.submit(g)
                    current = (take, run)
                    J.mark_submitted(take, backend.name, run.id)
                    status = run.watch(on_progress=progress_line(t0))
                    print("\r" + " " * 60 + "\r", end="", flush=True)
                    result = J.collect_take(take, run, J.node_of(g, J.PORTABLE_SAVER), status)
                    current = None
                    if result != "ok":
                        raise RuntimeError((take.sidecar or {}).get("save_notes")
                                           or f"the take ended {result}")
                    done += 1
                    frames_done += j.frames
                    rate = (time.time() - t_start) / max(frames_done, 1)
                    left = (total_frames - frames_done) * rate
                    print(f"  -> {take.paths.mp4}  [{fmt(time.time() - t0)}, ~{fmt(left)} left]",
                          flush=True)
                except (BackendError, RuntimeError, OSError) as e:
                    current = None
                    if (take.sidecar or {}).get("status") == "queued":
                        J.mark_failed(take, str(e)[:800])
                    failed += 1
                    failures.append(label)
                    print(f"  !! {label}: {e}", flush=True)
                    if args.stop_on_error:
                        raise KeyboardInterrupt
    except KeyboardInterrupt:
        print("\n  stopping")
        if current is not None:
            take, run = current
            if run is not None:
                try:
                    run.cancel()
                except Exception:                 # noqa: BLE001  best effort
                    pass
            J.mark_failed(take, "interrupted")
    print(f"\n  done in {fmt(time.time() - t_start)}: {done} rendered"
          + (f", {failed} failed: {', '.join(failures)}" if failed else "") + "\n")
    return 1 if failed else 0


def start_job_portable(job: J.Job) -> T.Take:
    """start_job, for a portable render: the take reserved, its record and
    frozen shotlist written, nothing staged in ComfyUI."""
    if job.staged or job.inputs:
        raise J.NotPortable(f"{job.target} stages input files in ComfyUI; it renders "
                            f"portably once ported (docs/PLAN.md, step 5)")
    return J.start_job(job)


def progress_line(t0: float):
    def show(p) -> None:
        step = f"  step {p.step}/{p.steps}" if p.step and p.steps else ""
        print(f"\r     {p.value:4.0%}{step}  [{fmt(time.time() - t0)}]   ", end="", flush=True)
    return show


if __name__ == "__main__":
    raise SystemExit(main())
