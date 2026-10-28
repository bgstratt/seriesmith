"""
The `seriesmith` command's one table (commands.COMMANDS, docs/REFACTOR.md 3.6):
every command listed once, in the help and in docs/COMMANDS.md; `--help` answers
for each; a usage mistake exits 2 with the usage line; the stages run in this
process.
"""
from __future__ import annotations

import contextlib
import io
import os
import re
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from seriesmith import cli  # noqa: E402
from seriesmith import commands as C  # noqa: E402


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = cli.main(list(argv))
        except SystemExit as e:                  # argparse's --help and errors
            code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    return code, out.getvalue(), err.getvalue()


class TableTest(unittest.TestCase):
    def test_every_command_is_in_the_help_once(self):
        code, out, _ = run()
        self.assertEqual(code, 0)
        for name in C.COMMANDS:
            self.assertEqual(len(re.findall(rf"^  {re.escape(name)}\s", out, re.M)), 1, name)
        self.assertEqual(run("--help")[1], out)

    def test_docs_commands_lists_the_same_commands(self):
        text = open(os.path.join(ROOT, "docs", "COMMANDS.md"), encoding="utf-8").read()
        table = text.split("## Every command", 1)[1].split("\n\n", 2)[1]
        listed = set(re.findall(r"(?:`seriesmith |` / `)([a-z][a-z-]*)", table))
        self.assertEqual(listed, set(C.COMMANDS))

    def test_help_answers_for_every_command(self):
        for name in C.COMMANDS:
            code, out, err = run(name, "--help")
            self.assertEqual(code, 0, (name, err))
            if name != "align":                  # align's help is its subprocess's
                self.assertIn(f"seriesmith {name}", out, name)

    def test_a_usage_mistake_exits_2_with_the_usage(self):
        for name, c in C.COMMANDS.items():
            if name in ("serve", "stop", "targets", "backends", "new", "mcp"):
                continue                         # a bare call does something (or asks a question)
            code, out, err = run(name)
            self.assertEqual(code, 2, (name, out, err))
            self.assertIn("usage: seriesmith " + name, err, name)
        code, _, err = run("refs", "--skip-build")
        self.assertEqual(code, 2)
        self.assertIn("--skip-build only applies to `all`", err)

    def test_an_unknown_command_exits_2(self):
        code, _, err = run("nope")
        self.assertEqual(code, 2)
        self.assertIn("unknown command 'nope'", err)

    def test_stages_run_in_this_process(self):
        """build on an episode folder calls build.main here, twice (final, proxy),
        no Python started; a SystemExit in a stage is its exit code."""
        import subprocess
        import tempfile
        from seriesmith import build
        with tempfile.TemporaryDirectory() as d:
            for f in ("series.json", "ep.md"):
                open(os.path.join(d, f), "w").close()
            calls = []
            with mock.patch.object(build, "main", lambda args, prog=None: calls.append(args) or 0), \
                    mock.patch.object(subprocess, "call", side_effect=AssertionError("a subprocess")), \
                    mock.patch.object(C.PATHS, "episode_files",
                                      return_value=(os.path.join(d, "series.json"), os.path.join(d, "ep.md"))):
                code, out, _ = run("build", d)
            self.assertEqual(code, 0)
            self.assertEqual([("--proxy" in a) for a in calls], [False, True])

            def fails(args, prog=None):
                raise SystemExit("  !! no script here")
            with mock.patch.object(build, "main", fails), \
                    mock.patch.object(C.PATHS, "episode_files",
                                      return_value=(os.path.join(d, "series.json"), os.path.join(d, "ep.md"))):
                code, _, err = run("build", d)
            self.assertEqual(code, 1)
            self.assertIn("no script here", err)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class VersionTest(unittest.TestCase):
    def test_the_package_says_the_release(self):
        """seriesmith.__version__ (`seriesmith --version`, /seriesmith/info, the MCP
        server's serverInfo) is pyproject.toml's: a release bumps both. A literal,
        not read from pyproject.toml, because the skill's bundle carries
        seriesmith/__init__.py without it."""
        import seriesmith
        text = open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8").read()
        self.assertEqual(seriesmith.__version__, re.search(r'^version\s*=\s*"([^"]+)"', text, re.M).group(1))
