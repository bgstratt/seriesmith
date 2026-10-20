#!/usr/bin/env python3
"""
How long seriesmith takes, measured the same way before and after a change
(docs/REFACTOR.md). Not a test: nothing imports it.

routes     the editor's read routes on a running `seriesmith serve`, each asked
           twice (the first answer, then a repeat), per episode: milliseconds,
           status and size. --ep keeps the episodes whose folder contains any
           of the words; --save writes the numbers to JSON and --against
           compares with a saved run; --dump DIR writes every reply's JSON
           (keys sorted) so two runs can be diffed for identical answers.
profile    one api.py handler run in this process under cProfile.
assemble   `seriesmith assemble` of an episode, in this process: the total and
           every ffmpeg / ffprobe run it starts, counted and timed. It writes
           the episode's renders/: give it a scratch copy, never a real show.

Always 127.0.0.1, never localhost: on Windows, Python tries ::1 first and
spends ~2 s per request on it.

    python tools/bench.py routes --ep Porchlights FRTEST --save before.json
    python tools/bench.py routes --ep Porchlights --against before.json --dump after/
    python tools/bench.py profile get_refs C:/Users/me/ComfyProjects/Porchlights/ep01
    python tools/bench.py assemble C:/Users/me/ComfyProjects/Ballroom-refactor/ep01
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

GLOBAL = ["/seriesmith/config", "/seriesmith/episodes", "/seriesmith/browse",
          "/seriesmith/targets", "/seriesmith/workflows", "/seriesmith/presets",
          "/seriesmith/upscale/options", "/seriesmith/post/options",
          "/seriesmith/router/models"]
PER_EP = ["/seriesmith/episode", "/seriesmith/refs", "/seriesmith/issues",
          "/seriesmith/promote", "/seriesmith/align/ready", "/seriesmith/refs/videos"]


def get(base: str, path: str, **query) -> tuple[float, int, bytes]:
    url = base + path + ("?" + urllib.parse.urlencode(query) if query else "")
    t = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=300) as r:
            body, status = r.read(), r.status
    except urllib.error.HTTPError as e:
        body, status = e.read(), e.code
    return time.perf_counter() - t, status, body


def dump(folder: str, name: str, body: bytes) -> None:
    os.makedirs(folder, exist_ok=True)
    try:
        text = json.dumps(json.loads(body), indent=1, sort_keys=True, ensure_ascii=False)
    except ValueError:
        text = body.decode("utf-8", "replace")
    with open(os.path.join(folder, name + ".json"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text + "\n")


def safe(text: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in text).strip("_")


def routes(args) -> int:
    base = args.base.rstrip("/")
    before = {}
    if args.against:
        with open(args.against, encoding="utf-8") as fh:
            before = json.load(fh)
    out: dict = {}

    def show(key: str, label: str, first, again=None) -> None:
        ms = round(first[0] * 1000)
        rep = round(again[0] * 1000) if again else None
        out[key] = {"ms": ms, "again_ms": rep, "status": first[1], "kb": len(first[2]) // 1024}
        was = before.get(key)
        delta = ""
        if was:
            delta = f"   was {was['ms']:>6}" + (f" / {was['again_ms']:>6}" if was.get("again_ms") is not None else "")
        rep_s = f" / {rep:>6}" if rep is not None else "         "
        print(f"{ms:>8}{rep_s} ms  {first[1]}  {len(first[2]) // 1024:>6} KB  {label}{delta}",
              flush=True)
        if args.dump and first[1] == 200:
            dump(args.dump, safe(key), first[2])

    if not args.no_global:
        for p in GLOBAL:
            show(p, p, get(base, p))
    _, status, body = get(base, "/seriesmith/episodes")
    if status != 200:
        print(f"!! /seriesmith/episodes answered {status}: is `seriesmith serve` running at {base}?")
        return 1
    for e in json.loads(body):
        here = e["ep"].replace("\\", "/").lower()
        if args.ep and not any(w.replace("\\", "/").lower() in here for w in args.ep):
            continue
        print(f"--- {e['ep']}  ({e['shots']} shots)", flush=True)
        for p in PER_EP:
            show(f"{e['ep']}|{p}", p, get(base, p, ep=e["ep"]), get(base, p, ep=e["ep"]))
    if args.save:
        with open(args.save, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=1)
        print(f"  -> {args.save}")
    return 0


def profile(args) -> int:
    import cProfile
    import pstats
    import tempfile
    from seriesmith import api as A
    fn = getattr(A, args.route)
    ep = os.path.abspath(args.ep)
    ctx = A.Context(tempfile.mkdtemp(prefix="bench_"), args.comfy,
                    env={"SERIESMITH_ROOTS": os.path.dirname(ep)})
    for label in ("first", "again"):
        t = time.perf_counter()
        status, data = fn(ctx, {"ep": ep})
        took = time.perf_counter() - t
        size = len(json.dumps(data, ensure_ascii=False)) // 1024
        print(f"{label:>6}  {status}  {took * 1000:8.0f} ms  {size} KB")
    pr = cProfile.Profile()
    pr.enable()
    fn(ctx, {"ep": ep})
    pr.disable()
    pstats.Stats(pr).sort_stats("cumulative").print_stats(args.top)
    return 0


def assemble(args) -> int:
    import subprocess
    calls: dict = collections.defaultdict(lambda: [0, 0.0])
    real_run = subprocess.run

    def run(cmd, *a, **kw):
        t = time.perf_counter()
        try:
            return real_run(cmd, *a, **kw)
        finally:
            exe = os.path.splitext(os.path.basename(str(cmd[0])))[0].lower()
            what = " ".join(str(c) for c in cmd[1:] if str(c).startswith(("stream", "format")))
            key = f"{exe} {what}".strip() if exe == "ffprobe" else exe
            calls[key][0] += 1
            calls[key][1] += time.perf_counter() - t

    subprocess.run = run
    from seriesmith import assemble as ASM
    ep = os.path.abspath(args.ep)
    here = os.getcwd()
    os.chdir(ep)                       # as commands.stage runs it
    sys.argv = ["assemble"] + args.rest
    t = time.perf_counter()
    try:
        ASM.main()
    except SystemExit:
        pass
    finally:
        os.chdir(here)
        subprocess.run = real_run
    print(f"\n  total {time.perf_counter() - t:6.2f} s")
    for key, (n, took) in sorted(calls.items(), key=lambda kv: -kv[1][1]):
        print(f"  {n:4d} runs {took:6.2f} s  {key}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="what", required=True)
    r = sub.add_parser("routes", help="the editor's read routes on a running server")
    r.add_argument("--base", default="http://127.0.0.1:8190")
    r.add_argument("--ep", nargs="*", default=[], help="only episodes whose folder holds any of these")
    r.add_argument("--no-global", action="store_true", help="only the per-episode routes")
    r.add_argument("--save", help="write the numbers to this JSON file")
    r.add_argument("--against", help="a saved run to compare with")
    r.add_argument("--dump", help="write each reply's JSON into this folder")
    p = sub.add_parser("profile", help="one api.py handler under cProfile")
    p.add_argument("route", help="the handler, e.g. get_refs")
    p.add_argument("ep", help="the episode folder")
    p.add_argument("--comfy", default="http://127.0.0.1:8188")
    p.add_argument("--top", type=int, default=35)
    a = sub.add_parser("assemble", help="an assemble, its ffmpeg and ffprobe runs counted")
    a.add_argument("ep", help="the episode folder (a scratch copy: it writes renders/)")
    a.add_argument("rest", nargs=argparse.REMAINDER, help="assemble's own options")
    args = ap.parse_args(argv)
    return {"routes": routes, "profile": profile, "assemble": assemble}[args.what](args)


if __name__ == "__main__":
    sys.exit(main())
