"""
seriesmith — one command for every stage.

    seriesmith build <episode>   (or series.json ep01.md -o <episode folder>) [--proxy]
    seriesmith check <episode>   (or series.json ep01.md) [--proxy] [--pace]
    seriesmith render <episode> [--only sh010] [--redo] [--backend local]
    seriesmith backends [--try NAME]        where jobs can run, and whether each answers
    seriesmith serve [--root FOLDER]        the editor in your browser (port 8190)
    seriesmith stop [--restart]             stop (or restart) that editor's server cleanly

and h3pipe's commands, through seriesmith.commands (`seriesmith <command> --help`):

    new, takes, pick, override, keyframe, discard, cut, issues, supply, promote,
    targets, target-from-workflow, refs, align, assemble, upscale, post, master,
    publish, all
"""
from __future__ import annotations

import os
import sys

from seriesmith import __version__

USAGE = __doc__.strip()


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0
    if argv[0] in ("-V", "--version"):
        print(f"seriesmith {__version__}")
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd in ("build", "check") and rest and os.path.isdir(rest[0]):
        # an episode folder (or several): the commands' build / check, which
        # find its series config and script
        return _commands(cmd, rest)
    if cmd == "build":
        from seriesmith import build
        return build.main(rest, prog="seriesmith build")
    if cmd == "check":
        from seriesmith import build
        return build.main(rest + ["--check"], prog="seriesmith check")
    if cmd == "backends":
        return backends_cmd(rest)
    if cmd == "render":
        from seriesmith import render
        return render.main(rest)
    if cmd == "serve":
        from seriesmith.server import standalone
        return standalone.main(rest)
    if cmd == "stop":
        from seriesmith.server import standalone
        return standalone.stop_main(rest)
    # everything else h3pipe's `h3.py` did (takes, pick, override, cut, refs,
    # supply, issues, promote, assemble, upscale, post, master, publish, new,
    # targets, align, all): its dispatcher, ported as seriesmith.commands
    from seriesmith import commands
    if cmd in commands.STAGES or cmd in commands.EDIT or cmd in commands.OTHER:
        return _commands(cmd, rest)
    print(f"seriesmith: unknown command {cmd!r}\n\n{USAGE}", file=sys.stderr)
    return 2


def _commands(cmd: str, rest: list[str]) -> int:
    from seriesmith import commands
    saved = sys.argv
    sys.argv = ["seriesmith", cmd, *rest]
    try:
        return commands.main()
    finally:
        sys.argv = saved


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


if __name__ == "__main__":
    raise SystemExit(main())
