"""
seriesmith — one command for every stage.

    seriesmith build series.json ep01.md -o <episode folder> [--proxy]
    seriesmith check series.json ep01.md [--proxy] [--pace]
    seriesmith backends [--try NAME]        where jobs can run, and whether each answers

More commands arrive as their stages are ported (docs/DESIGN.md).
"""
from __future__ import annotations

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
    if cmd == "build":
        from seriesmith import build
        return build.main(rest, prog="seriesmith build")
    if cmd == "check":
        from seriesmith import build
        return build.main(rest + ["--check"], prog="seriesmith check")
    if cmd == "backends":
        return backends_cmd(rest)
    print(f"seriesmith: unknown command {cmd!r}\n\n{USAGE}", file=sys.stderr)
    return 2


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
