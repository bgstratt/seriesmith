#!/usr/bin/env python3
"""
The `seriesmith` command: every subcommand in one table (COMMANDS), each with
its usage, its one-line help and what runs it. `seriesmith` (or --help) lists
them; `seriesmith <command> --help` gives a command's usage and flags; the
examples are in docs/COMMANDS.md.

A stage (build, check, refs, render, assemble, and so `all`) runs in this
process; align keeps a subprocess (it can need another Python: the one with a
Whisper, track.align_python). A usage mistake exits 2 with the usage line on
stderr, as argparse's own errors do.

The episode can be a folder (any name) holding one script .md and series.json
(or a series folder above it holding the series.json its episodes share), or
several folders at once, or a parent with --each:

    seriesmith build Shows --each              # every episode folder under Shows

Anything after the episode is passed straight through to the stage, so every
flag it takes works here. `--proxy` is also understood by assemble (it picks
the proxy shotlist and renders_proxy/).
"""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable

from seriesmith import __version__
from seriesmith.core import paths as PATHS

HELP_FLAGS = ("-h", "--help")


class UsageError(Exception):
    """A command asked for wrongly: main() says why with its usage, exit 2."""


@dataclass(frozen=True)
class Command:
    name: str
    args: str                          # what follows the name on its usage line
    help: str                          # one line, for `seriesmith --help`
    run: Callable[[list[str]], int]
    own_help: bool = False             # its own parser answers `<command> --help`


def usage(c: Command) -> str:
    return f"usage: seriesmith {c.name} {c.args}".rstrip()


# ---------------------------------------------------------------------------
# stages, in this process
# ---------------------------------------------------------------------------

def episode_files(ep: str) -> tuple[str, str]:
    """(series.json, the script): the series config in the episode folder or
    its parent, as everywhere else (core/paths)."""
    try:
        return PATHS.episode_files(ep)
    except ValueError as e:
        sys.exit(f"  !! {e}")


def call(what: str, fn, args: list[str]) -> int:
    """fn(args) in this process, said first; a SystemExit (argparse, a
    sys.exit("!! ...")) is its exit code, as it was from a subprocess."""
    print("  > " + what + " " + " ".join(f'"{a}"' if " " in a else a for a in args), flush=True)
    try:
        return int(fn(args) or 0)
    except SystemExit as e:
        if isinstance(e.code, str):
            print(e.code, file=sys.stderr)
            return 1
        return int(e.code or 0)


def run(cmd: list[str]) -> int:
    """A subprocess (align), said first."""
    print("  $ " + " ".join(f'"{c}"' if " " in c else c for c in cmd), flush=True)
    return subprocess.call(cmd)


def _build(args):
    from seriesmith import build
    return build.main(args, prog="seriesmith build")


def _check(args):
    from seriesmith import build
    return build.main(args, prog="seriesmith check")


def _refs(args):
    from seriesmith import kreagen
    return kreagen.main(args)


def _render(args):
    from seriesmith import render
    return render.main(args)


def _assemble(args):
    from seriesmith import assemble
    return assemble.main(args)


def stage(name: str, ep: str, extra: list[str], skip_build: bool = False) -> int:
    proxy = "--proxy" in extra
    if name in ("build", "check"):
        series_cfg, md = episode_files(ep)
        base = [series_cfg, md]
        if name == "check":
            return call("check", _check, base + ["--check"]) or call("check", _check, base + ["--pace"])
        rest = [a for a in extra if a != "--proxy"]
        return (call("build", _build, base + ["-o", ep] + rest)
                or call("build", _build, base + ["-o", ep, "--proxy"] + rest))
    if name == "align":
        return run([sys.executable, "-m", "seriesmith.align", ep] + extra)
    if name == "refs":
        return call("refs", _refs, ["--project-root", ep] + extra)
    if name == "render":
        return call("render", _render, [ep] + extra)
    if name == "assemble":
        rest = [a for a in extra if a != "--proxy"]
        if proxy:
            rest = ["--shotlist", "shotlist/shotlist_proxy.json",
                    "--subfolder", "renders_proxy"] + rest
        return call("assemble", _assemble, ["-o", ep] + rest)
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
    raise ValueError(f"unknown stage {name}")


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


def on_episodes(name: str, rest: list[str]) -> int:
    """A stage on each episode folder named (or each under a parent, --each),
    every one run even when one fails."""
    each = "--each" in rest
    skip_build = any(a in ("--skip-build", "--no-build") for a in rest)
    rest = [a for a in rest if a not in ("--each", "--skip-build", "--no-build")]
    if skip_build and name != "all":
        raise UsageError("--skip-build only applies to `all` (the other stages never build)")
    eps, extra = [], []
    for i, a in enumerate(rest):
        if a.startswith("-"):
            extra = rest[i:]
            break
        eps.append(a)
    if not eps:
        raise UsageError("give an episode folder, e.g. Shows\\ep05")
    if each:
        eps = sorted(p for parent in eps for p in episode_folders(parent)
                     if PATHS.series_config_path(p) and PATHS.episode_script(p))
    failed = []
    for ep in eps:
        print(f"\n=== {name}: {ep}")
        try:
            rc = stage(name, ep, extra, skip_build)
        except SystemExit as e:              # episode_files: no series config / script
            if isinstance(e.code, str):
                print(e.code, file=sys.stderr)
            rc = 1 if isinstance(e.code, str) or e.code is None else int(e.code)
        if rc:
            failed.append(ep)
    if len(eps) > 1:
        print(f"\n  {len(eps) - len(failed)}/{len(eps)} ok"
              + (f"; failed: {', '.join(failed)}" if failed else ""))
    return 1 if failed else 0


def _stage_cmd(name: str, own: Callable | None = None):
    """A stage over episodes; `<stage> --help` is the stage's own parser's."""
    def go(rest: list[str]) -> int:
        if own is not None and rest[:1] and rest[0] in HELP_FLAGS:
            try:
                return int(own(["--help"]) or 0)
            except SystemExit as e:
                return int(e.code or 0)
        return on_episodes(name, rest)
    return go


def _folder_or_files(name: str, own: Callable):
    """build / check: on episode folders (their series config and script
    found), else build's own arguments (series.json ep01.md -o <folder>)."""
    def go(rest: list[str]) -> int:
        if rest and os.path.isdir(rest[0]):
            return on_episodes(name, rest)
        args = rest + (["--check"] if name == "check" and "--check" not in rest else [])
        try:
            return int(own(args) or 0)
        except SystemExit as e:
            return e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    return go


def _align(rest: list[str]) -> int:
    if rest[:1] and rest[0] in HELP_FLAGS:
        return subprocess.call([sys.executable, "-m", "seriesmith.align", "--help"])
    # one episode, then the recording path and flags go straight to align
    if not rest or rest[0].startswith("-"):
        raise UsageError("give the episode folder first")
    return 1 if stage("align", rest[0], rest[1:]) else 0


# ---------------------------------------------------------------------------
# the rest
# ---------------------------------------------------------------------------

def episode_first(fn):
    """A command of `(episode, rest)`: the episode checked and made absolute."""
    def go(rest: list[str]) -> int:
        if not rest or rest[0].startswith("-"):
            raise UsageError("give the episode folder first")
        return fn(os.path.abspath(rest[0]), rest[1:])
    return go


def _edit(name: str):
    def go(ep: str, rest: list[str]) -> int:
        from seriesmith import edit as E
        return E.COMMANDS[name](ep, rest)
    return episode_first(go)


def _issues(ep, rest):
    from seriesmith import issues as ISS
    return ISS.cmd_issues(ep, rest)


def _supply(ep, rest):
    from seriesmith import refs as R
    return R.cmd_supply(ep, rest)


def _promote(ep, rest):
    from seriesmith import promote as PRM
    return PRM.cmd_promote(ep, rest)


def _new(rest):
    from seriesmith import source as SRC
    return SRC.cmd_new(rest)


def _targets(rest):
    # the episode is optional: it adds its series config (pass blocks,
    # model_families) and marks its target
    from seriesmith import edit as E
    ep = os.path.abspath(rest[0]) if rest and not rest[0].startswith("-") else None
    return E.cmd_targets(ep, rest[1:] if ep else rest)


def _target_from_workflow(rest):
    from seriesmith import edit as E
    return E.cmd_target_from_workflow(rest)


def _module_main(module: str):
    def go(rest: list[str]) -> int:
        import importlib
        return importlib.import_module(module).main(rest)
    return go


def _serve(rest):
    from seriesmith.server import standalone
    return standalone.main(rest)


def _stop(rest):
    from seriesmith.server import standalone
    return standalone.stop_main(rest)


def backends_cmd(argv: list[str]) -> int:
    import argparse

    from seriesmith import backends as B
    from seriesmith.settings import load_settings
    ap = argparse.ArgumentParser(prog="seriesmith backends",
                                 description="List the backends this machine is set up for "
                                             "and whether each answers.")
    ap.add_argument("--try", dest="try_", metavar="NAME",
                    help="run a small round trip on that ComfyUI backend (a picture up, "
                         "inverted, and back)")
    args = ap.parse_args(argv)
    try:
        settings = load_settings()
    except ValueError as e:
        print(f"seriesmith: {e}", file=sys.stderr)
        return 1
    found = B.available(settings)
    print(f"  settings  {settings.path or '(no settings file; defaults and environment)'}")
    print(f"  api key   {'set' if settings.api_key else 'not set (cloud, router and deployments need COMFY_API_KEY)'}")
    print()
    for name, b in found.items():
        why = b.ping()
        where = getattr(b, "base_url", None) or getattr(b, "cloud_url", "")
        print(f"  {name:28} {'ok ' if why is None else 'no '} {where}"
              + (f"\n  {'':28}     {why}" if why else ""))
    if not args.try_:
        return 0
    b = found.get(args.try_)
    if b is None:
        print(f"\nseriesmith: no backend called {args.try_!r} ({', '.join(found)})",
              file=sys.stderr)
        return 1
    from seriesmith.backends.smoke import round_trip
    print(f"\n  round trip on {b.name}...")
    try:
        out = round_trip(b, on_progress=lambda p: print(f"    {p.value:4.0%}"),
                         on_status=lambda s: print(f"    {s}"))
    except B.BackendError as e:
        print(f"  failed: {e}", file=sys.stderr)
        return 1
    print(f"  ok: {out}")
    return 0


# ---------------------------------------------------------------------------
# the table
# ---------------------------------------------------------------------------

_TABLE = [
    Command("new", "<show>\\<name> [--title T] [--series-id ID]",
            "a new episode (series.json + script) that builds", _new),
    Command("build", "<episode>... [--each] [--proxy]  |  series.json ep01.md -o <folder>",
            "the script and series config into the shotlists and refs_todo (final and proxy)",
            _folder_or_files("build", _build), own_help=True),
    Command("check", "<episode>... [--each]  |  series.json ep01.md [--pace]",
            "build --check and --pace: errors, warnings, crammed lines; writes nothing",
            _folder_or_files("check", _check), own_help=True),
    Command("refs", "<episode>... [--each] [--list] [--only ID] [--voices]",
            "reference pictures (and voice samples) for what refs_todo lists",
            _stage_cmd("refs", _refs), own_help=True),
    Command("supply", "<episode> <file-or-folder>... [--ref id[:view]] [--no-pick] [--dry-run]",
            "pictures you already have, into their ref slots", episode_first(_supply)),
    Command("render", "<episode>... [--proxy] [--only sh010,...] [--redo] [--backend NAME]",
            "each shot as a take, on its backend", _render, own_help=True),
    Command("takes", "<episode> [--proxy]", "every take: status, seed, why stale, the cut's",
            _edit("takes")),
    Command("pick", "<episode> <shot> <take|latest> [--proxy]", "the take the cut uses",
            _edit("pick")),
    Command("override", "<episode> [<shot>] [--seed N] [--prompt-file F] [--target ID] ...",
            "a shot's settings for its next render (overrides.json)", _edit("override")),
    Command("keyframe", "<episode> <shot> [--from-prev] ...",
            "a shot's first or last keyframe", _edit("keyframe")),
    Command("discard", "<episode> <shot> <take> [--proxy]",
            "a take into renders/_trash/", _edit("discard")),
    Command("cut", "<episode> [--proxy] [--show | --move SH --before SH | --trim SH IN OUT ...]",
            "the cut: order, trims, locks, sound", _edit("cut")),
    Command("promote", "<episode> [<shot>] [--all | --item ID ...] [--dry-run]",
            "overrides moved into the script or the series config", episode_first(_promote)),
    Command("issues", "<episode> [--proxy] [--add <shot> <note> | --export | --clear | --resolve <id>]",
            "the pass's notepad", episode_first(_issues)),
    Command("align", "<episode> [recording.wav] [flags]",
            "the script timed against a dialogue recording", _align, own_help=True),
    Command("assemble", "<episode>... [--each] [--proxy] [--upscaled] [--partial]",
            "the review cut", _stage_cmd("assemble", _assemble), own_help=True),
    Command("upscale", "<episode> [--only sh020,...] [--take N] [--redo] [--check]",
            "the final cut's takes upscaled", _module_main("seriesmith.upscale"), own_help=True),
    Command("post", "<episode> [--enhance draft|production|cinematic|...] [--recipe] [--check]",
            "the cut's upscales post-processed", _module_main("seriesmith.post"), own_help=True),
    Command("master", "<episode>... [--check] [--wait] [--conform] [--allow-gaps] [--prores]",
            "the series recipe on every shot, then the master assembled",
            _module_main("seriesmith.master"), own_help=True),
    Command("publish", "<episode> [--proxy] [--input FILE] [--out FILE] [--check]",
            "the intro and outro around the review cut", _module_main("seriesmith.publish"),
            own_help=True),
    Command("all", "<episode>... [--each] [--proxy] [--skip-build] [render flags]",
            "build -> refs -> build -> render -> assemble", _stage_cmd("all")),
    Command("targets", "[<episode>] [--json] [--install-workflow ID]",
            "which models the running ComfyUI can render, what to download for the rest",
            _targets, own_help=True),
    Command("target-from-workflow", "<workflow> [<episode>] [--save]",
            "a ComfyUI workflow proposed as a model", _target_from_workflow, own_help=True),
    Command("backends", "[--try NAME]", "where jobs can run on this machine, and whether each answers",
            backends_cmd, own_help=True),
    Command("serve", "[--root FOLDER] [--port N] [--host H]", "the editor in your browser (port 8190)",
            _serve, own_help=True),
    Command("stop", "[--restart]", "stop (or restart) that editor's server cleanly",
            _stop, own_help=True),
    Command("mcp", "[--url URL] [--read-only]",
            "that server's API as an MCP server on stdio, for an LLM client to start",
            _module_main("seriesmith.mcp"), own_help=True),
]
COMMANDS: dict[str, Command] = {c.name: c for c in _TABLE}


def help_text() -> str:
    width = max(len(c.name) for c in _TABLE) + 2
    lines = ["seriesmith: series config + episode scripts into finished episodes.", "",
             "usage: seriesmith <command> [<episode>] [flags]", ""]
    lines += [f"  {c.name:<{width}}{c.help}" for c in _TABLE]
    lines += ["", "`seriesmith <command> --help` gives a command's usage and flags; the "
                  "examples are in docs/COMMANDS.md."]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in HELP_FLAGS + ("help",):
        print(help_text())
        return 0
    if argv[0] in ("-V", "--version"):
        print(f"seriesmith {__version__}")
        return 0
    c = COMMANDS.get(argv[0])
    if c is None:
        print(f"seriesmith: unknown command {argv[0]!r}\n\n{help_text()}", file=sys.stderr)
        return 2
    rest = argv[1:]
    if rest[:1] and rest[0] in HELP_FLAGS and not c.own_help:
        print(f"{usage(c)}\n\n  {c.help}")
        return 0
    try:
        return int(c.run(rest) or 0)
    except UsageError as e:
        print(f"seriesmith {c.name}: {e}\n{usage(c)}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
