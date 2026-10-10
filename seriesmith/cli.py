"""
seriesmith — one command for every stage.

    seriesmith build series.json ep01.md -o <episode folder> [--proxy]
    seriesmith check series.json ep01.md [--proxy] [--pace]

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
    print(f"seriesmith: unknown command {cmd!r}\n\n{USAGE}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
