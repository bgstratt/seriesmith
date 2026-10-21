"""
seriesmith — one command for every stage. The commands, their usage and help
are one table: seriesmith/commands.py (COMMANDS). `seriesmith` lists them.
"""
from __future__ import annotations

import sys

from seriesmith import commands
from seriesmith.commands import backends_cmd  # noqa: F401  (seriesmith.cli.backends_cmd)


def main(argv: list[str] | None = None) -> int:
    return commands.main(list(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    raise SystemExit(main())
