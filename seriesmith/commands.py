#!/usr/bin/env python3
"""
seriesmith's stage and editing commands (ported from h3pipe's h3.py; the
`seriesmith` command, seriesmith/cli.py, hands them here):

    seriesmith new      Shows\\ep02            # a new episode: series.json + ep02.md that build
    seriesmith supply   Shows\\ep05 C:\\sheets   # pictures you already have into their ref slots
                                                    # (a folder is matched by file name; --dry-run
                                                    #  prints the table, --ref id[:view] names one)
    seriesmith issues   Shows\\ep05 --proxy     # the notepad for the pass you are reviewing:
                                                    # --add sh0140 "the truck is on the wrong side",
                                                    # --export to paste into an assistant, --clear
    seriesmith align    Shows\\ep05 audio\\ep05_dialogue.wav   # align: time the script to a recording
    seriesmith build    Shows\\ep05            # build: shotlist + refs_todo (final AND proxy)
    seriesmith check    Shows\\ep05            # build --check and --pace, writes nothing
    seriesmith refs     Shows\\ep05 --list     # kreagen: generate missing reference images
    seriesmith render   Shows\\ep05 --proxy    # render: queue shots on ComfyUI
    seriesmith assemble Shows\\ep05 --proxy    # assemble: join renders into one mp4
    seriesmith upscale  Shows\\ep05            # upscale: the final cut's takes at 2x
                                                    # (--only sh020, --take N, --start-step N,
                                                    #  --vae, --redo, --check, --prune-latents)
    seriesmith post     Shows\\ep05 --enhance production
                                                    # post: the cut's upscales finished
                                                    # (--enhance draft|production|cinematic,
                                                    #  --blur 0.25, --recipe: post.master)
    seriesmith assemble Shows\\ep05 --upscaled # the final cut from its upscales
    seriesmith master   Shows\\ep05 [Shows\\ep06 ...] --wait
                                                    # the series recipe (upscale.master) on every
                                                    # shot of the cut, then the master assembled
                                                    # into ep05\\master\\, with the show's
                                                    # _titles\\INTRO.mp4 / OUTRO.mp4 when there
                                                    # (--check: the plan only,
                                                    #  --conform, --allow-gaps, --prores)
    seriesmith publish  Shows\\ep05            # the same intro + outro around the review
                                                    # cut, the episode title written under the
                                                    # series title, into ep05\\publish\\
    seriesmith all      Shows\\ep05 --proxy    # build -> refs -> render -> assemble
    seriesmith all      Shows\\ep05 --proxy --skip-build
                                                    # refs -> render -> assemble, using the
                                                    # shotlists already on disk (keeps hand edits)

    seriesmith takes    Shows\\ep05 [--proxy]      # every take: status, seed, why stale, which is in the cut
    seriesmith pick     Shows\\ep05 sh020 3        # the cut uses sh020 take 3 (cut.json)
    seriesmith pick     Shows\\ep05 sh020 latest   # back to the newest usable take
    seriesmith override Shows\\ep05 sh020 --seed 1234 --prompt-file p.txt
                                                    # overrides.json: used by the next render/redo
    seriesmith keyframe Shows\\ep05 sh020 --from-prev
                                                    # sh020's first keyframe = the previous
                                                    # shot's last frame (continuity)
    seriesmith override Shows\\ep05 --episode-target ltx2
                                                    # every shot the script gives no target
                                                    # renders on ltx2 (built: back to series.json's)
    seriesmith discard  Shows\\ep05 sh020 3 [--proxy]
                                                    # move sh020 take 3 to renders/_trash/sh020/
                                                    # (a cut pick of it goes back to latest)
    seriesmith cut      Shows\\ep05 [--proxy] --move sh050 --before sh020
                                                    # edit the cut: --show, --order, --move,
                                                    # --trim SH IN OUT, --lock/--unlock SH,
                                                    # --reset order|trims|audio|all,
                                                    # --copy-from final|proxy
                                                    #     [order|trims|audio|all],
                                                    # --audio SH take SH:N | file PATH
                                                    #     | none | own
                                                    #     [--from S] [--at S] [--gain G]
    (see edit.py for every takes/pick/override/keyframe/discard/cut flag)

    seriesmith promote  Shows\\ep05 [sh020]        # the plan: which overrides can move into
                                                    # the script / series config, the diffs
    seriesmith promote  Shows\\ep05 --all          # move them, drop those overrides, rebuild
    seriesmith promote  Shows\\ep05 --item shot:sh020:steps [--item ...] [--dry-run]
                                                    # (see promote.py for what maps where)

    seriesmith targets  [Shows\\ep05] [--json]     # which targets the running ComfyUI can
                                                    # render, what to download for the rest,
                                                    # and the workflow each one renders
    seriesmith targets  --install-workflow ltx2    # copy its graph into ComfyUI, to edit on
                                                    # the canvas (--revert-workflow undoes it)

The episode can be a folder (any name) holding series.json and one script .md,
or several folders at once, or a parent with --each:

    seriesmith build Shows --each              # every episode folder under Shows

Anything after the episode is passed straight through to the underlying
script, so every flag those scripts take still works here. `--proxy` is also
understood by assemble (it picks the proxy shotlist and renders_proxy/).
"""
from __future__ import annotations

import glob
import os
import subprocess
import sys

STAGES = ("align", "build", "check", "refs", "render", "assemble", "all")
EDIT = ("takes", "pick", "override", "keyframe", "discard", "cut")   # in-process, see edit.py
# `targets` (readiness) runs in-process too, with the episode optional
# the commands main() handles itself, before the stages
OTHER = ("new", "issues", "supply", "upscale", "post", "master", "publish", "targets",
         "target-from-workflow", "promote")


def episode_files(ep: str) -> tuple[str, str]:
    series_cfg = os.path.join(ep, "series.json")
    if not os.path.isfile(series_cfg):
        sys.exit(f"  !! {series_cfg} not found")
    base = os.path.basename(os.path.normpath(ep))
    md = os.path.join(ep, f"{base}.md")
    if not os.path.isfile(md):
        cands = [p for p in glob.glob(os.path.join(ep, "*.md"))
                 if not os.path.basename(p).lower().startswith(("refs_todo", "readme", "notes", "align_report"))]
        if len(cands) != 1:
            sys.exit(f"  !! can't tell which script to use in {ep}: "
                     f"{[os.path.basename(c) for c in cands] or 'no .md found'}")
        md = cands[0]
    return series_cfg, md


def run(cmd: list[str]) -> int:
    print("  $ " + " ".join(f'"{c}"' if " " in c else c for c in cmd), flush=True)
    return subprocess.call(cmd)


def stage(name: str, ep: str, extra: list[str], skip_build: bool = False) -> int:
    py = sys.executable
    proxy = "--proxy" in extra
    if name in ("build", "check"):
        series_cfg, md = episode_files(ep)
        base = [py, "-m", "seriesmith.build", series_cfg, md]
        if name == "check":
            return run(base + ["--check"]) or run(base + ["--pace"])
        rest = [a for a in extra if a != "--proxy"]
        return run(base + ["-o", ep] + rest) or run(base + ["-o", ep, "--proxy"] + rest)
    if name == "align":
        return run([py, "-m", "seriesmith.align", ep] + extra)
    if name == "refs":
        return run([py, "-m", "seriesmith.kreagen", "--project-root", ep] + extra)
    if name == "render":
        return run([py, "-m", "seriesmith.render", ep] + extra)
    if name == "assemble":
        rest = [a for a in extra if a != "--proxy"]
        if proxy:
            rest = ["--shotlist", "shotlist/shotlist_proxy.json",
                    "--subfolder", "renders_proxy"] + rest
        return run([py, "-m", "seriesmith.assemble", "-o", ep] + rest)
    if name == "all":
        # refs and build take no render flags; keep only --proxy for them
        steps = [("build", []), ("refs", []), ("build", []),
                 ("render", extra), ("assemble", ["--proxy"] if proxy else [])]
        if skip_build:
            # use the shotlists already on disk so hand edits (steps, sizes...) survive
            need = ["shotlist/shotlist.json", "refs_todo.json"]
            if proxy:
                need.append("shotlist/shotlist_proxy.json")
            missing = [n for n in need if not os.path.isfile(os.path.join(ep, n))]
            if missing:
                print(f"  !! --skip-build but {ep} has no {', '.join(missing)}; "
                      f"run `seriesmith build {ep}` once first")
                return 1
            print("  -- skipping build; using existing shotlists")
            steps = [st for st in steps if st[0] != "build"]
        for s, args in steps:
            rc = stage(s, ep, args)
            if rc:
                print(f"  !! {s} failed for {ep} (exit {rc}); stopping this episode")
                return rc
        return 0
    sys.exit(f"  !! unknown stage {name}")


def episode_folders(parent: str) -> list[str]:
    """Every folder directly under `parent`, whatever it is called: ep05, but
    also s2ep01 and the like. Hidden and generated folders are skipped; the
    caller decides what makes one an episode."""
    try:
        names = sorted(os.listdir(parent), key=str.lower)
    except OSError:
        return []
    return [os.path.join(parent, n) for n in names
            if not n.startswith((".", "_")) and os.path.isdir(os.path.join(parent, n))]


def main() -> int:
    argv = sys.argv[1:]
    if argv and argv[0] == "new":
        # the folder is the show's, its last part the new episode's name; the
        # template is the newest episode already there, else examples/starter
        from seriesmith import source as SRC
        return SRC.cmd_new(argv[1:])
    if argv and argv[0] == "issues":
        if len(argv) < 2 or argv[1].startswith("-"):
            sys.exit("  !! usage: seriesmith issues <episode> [--proxy] "
                     "[--add <shot> <note> | --export | --clear | --resolve <id>]")
        from seriesmith import issues as ISS
        return ISS.cmd_issues(os.path.abspath(argv[1]), argv[2:])
    if argv and argv[0] == "supply":
        if len(argv) < 2 or argv[1].startswith("-"):
            sys.exit("  !! usage: seriesmith supply <episode> <file-or-folder>... "
                     "[--ref id[:view]] [--no-pick] [--dry-run]")
        from seriesmith import refs as R
        return R.cmd_supply(os.path.abspath(argv[1]), argv[2:])
    if argv and argv[0] == "upscale":
        if len(argv) < 2 or argv[1].startswith("-"):
            sys.exit("  !! usage: seriesmith upscale <episode> [--only sh020,...] [--take N] "
                     "[--start-step N] [--vae] [--redo] [--check] [--prune-latents]")
        from seriesmith import upscale as U
        return U.main(argv[1:])
    if argv and argv[0] == "post":
        if len(argv) < 2 or argv[1].startswith("-"):
            sys.exit("  !! usage: seriesmith post <episode> [--only sh020,...] [--take N] "
                     "[--enhance draft|production|cinematic|pixel|seedvr2|supir|none] "
                     "[--strength 0.2] [--blur 0.25] [--recipe] [--redo] [--check]")
        from seriesmith import post as P
        return P.main(argv[1:])
    if argv and argv[0] == "master":
        if len(argv) < 2 or argv[1].startswith("-"):
            sys.exit("  !! usage: seriesmith master <episode> [<episode> ...] [--check] [--wait] "
                     "[--conform] [--allow-gaps] [--prores]")
        from seriesmith import master as M
        return M.main(argv[1:])
    if argv and argv[0] == "publish":
        if len(argv) < 2 or argv[1].startswith("-"):
            sys.exit("  !! usage: seriesmith publish <episode> [--proxy] [--input FILE] "
                     "[--out FILE] [--quality review|master] [--check]")
        from seriesmith import publish as PUB
        return PUB.main(argv[1:])
    if argv and argv[0] == "targets":
        # the episode is optional: it adds its series config (pass blocks,
        # model_families) and marks its target
        from seriesmith import edit as E
        rest = argv[1:]
        ep = os.path.abspath(rest.pop(0)) if rest and not rest[0].startswith("-") else None
        return E.cmd_targets(ep, rest)
    if argv and argv[0] == "target-from-workflow":
        from seriesmith import edit as E
        return E.cmd_target_from_workflow(argv[1:])
    if argv and argv[0] == "promote":
        if len(argv) < 2 or argv[1].startswith("-"):
            sys.exit("  !! usage: seriesmith promote <episode> [<shot>] [--all | --item ID ...] "
                     "[--dry-run]")
        from seriesmith import promote as PRM
        return PRM.cmd_promote(os.path.abspath(argv[1]), argv[2:])
    if argv and argv[0] in EDIT:
        if len(argv) < 2 or argv[1].startswith("-"):
            sys.exit(f"  !! usage: seriesmith {argv[0]} <episode> ...")
        from seriesmith import edit as E
        return E.COMMANDS[argv[0]](os.path.abspath(argv[1]), argv[2:])
    if not argv or argv[0] in ("-h", "--help") or argv[0] not in STAGES:
        print(__doc__)
        return 0 if argv[:1] in (["-h"], ["--help"], []) else 2
    name, rest = argv[0], argv[1:]
    each = "--each" in rest
    skip_build = any(a in ("--skip-build", "--no-build") for a in rest)
    rest = [a for a in rest if a not in ("--each", "--skip-build", "--no-build")]
    if skip_build and name != "all":
        sys.exit("  !! --skip-build only applies to `all` (the other stages never build)")

    eps, extra = [], []
    if name == "align":
        # one episode, then the recording path and flags go straight to align
        if not rest or rest[0].startswith("-"):
            sys.exit("  !! usage: seriesmith align <episode> [recording.wav] [flags]")
        return 1 if stage(name, rest[0], rest[1:]) else 0
    for i, a in enumerate(rest):
        if a.startswith("-"):
            extra = rest[i:]
            break
        eps.append(a)
    if not eps:
        sys.exit("  !! give an episode folder, e.g. Shows\\ep05")
    if each:
        eps = sorted(p for parent in eps for p in episode_folders(parent)
                     if os.path.isfile(os.path.join(p, "series.json")))

    failed = []
    for ep in eps:
        print(f"\n=== {name}: {ep}")
        if stage(name, ep, extra, skip_build):
            failed.append(ep)
    if len(eps) > 1:
        print(f"\n  {len(eps) - len(failed)}/{len(eps)} ok"
              + (f"; failed: {', '.join(failed)}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
