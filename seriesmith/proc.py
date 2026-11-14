"""
proc — the one place seriesmith starts another program.

Every ffmpeg, ffprobe, pipeline tool and helper is started here, so what holds for one
holds for all of them, and there is one place to read to check it:

    an argument list     never a string, never through a shell: no value in a command is
                         ever read as shell syntax
    no keys              the program's environment is this one less the keys it never needs
                         (the Comfy API key, a provider's SERIESMITH_KEY_*, the Hugging Face
                         token), unless the caller passes an environment of its own
    ffmpeg reads media   an ffmpeg or ffprobe command's inputs are held to files on this PC
                         and to video, sound and pictures (ff.limited): never an address,
                         never a playlist of other files

What may be run is decided where the command is made: ffmpeg and ffprobe from `ff.tool`,
seriesmith's own modules from `edit.tool_cmd` (through `_run.py`), a helper file of the
package by its own path. Nothing a show or a request names.

    module(py, name)     the command for one of seriesmith's own modules, through _run.py
    run(cmd, ...)        subprocess.run
    popen(cmd, ...)      subprocess.Popen
    call(cmd, ...)       subprocess.call
    clean_env()          the environment those run in

Stdlib only.
"""
from __future__ import annotations

import os
import subprocess

# never a child's to have: it reads files and writes files
SECRET_NAMES = ("COMFY_API_KEY", "HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HUGGINGFACE_HUB_TOKEN",
                "REGISTRY_ACCESS_TOKEN")
SECRET_PREFIXES = ("SERIESMITH_KEY_",)


def clean_env(extra: dict | None = None) -> dict[str, str]:
    """This environment without the keys (SECRET_NAMES, SECRET_PREFIXES), plus `extra`."""
    env = {k: v for k, v in os.environ.items()
           if k.upper() not in SECRET_NAMES and not k.upper().startswith(SECRET_PREFIXES)}
    env.update(extra or {})
    return env


def _checked(cmd, kw: dict) -> list[str]:
    if isinstance(cmd, (str, bytes)) or kw.get("shell"):
        raise ValueError("a program is started from an argument list, never a shell line")
    cmd = [os.fspath(a) for a in cmd]
    if not cmd or not all(isinstance(a, str) for a in cmd):
        raise ValueError("a program is started from a list of text arguments")
    kw.pop("shell", None)
    if kw.get("env") is None:
        kw["env"] = clean_env()
    from seriesmith import ff                             # here: ff starts programs through this module
    return ff.limited(cmd)


RUNNER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_run.py")


def module(python: str | None, name: str, *args: str) -> list[str]:
    """The command that runs one of seriesmith's own modules (`helpers.erp`, `align`) with
    `python` (this one when None), through _run.py: the only way a Python of seriesmith's
    is started. ValueError for a name that isn't a module's."""
    import sys
    if not name or not all(part.isidentifier() for part in name.split(".")):
        raise ValueError(f"{name!r} isn't one of seriesmith's modules")
    return [python or sys.executable, RUNNER, "seriesmith." + name, *args]


def run(cmd, **kw) -> subprocess.CompletedProcess:
    cmd = _checked(cmd, kw)
    return subprocess.run(cmd, **kw)


def popen(cmd, **kw) -> subprocess.Popen:
    cmd = _checked(cmd, kw)
    return subprocess.Popen(cmd, **kw)


def call(cmd, **kw) -> int:
    cmd = _checked(cmd, kw)
    return subprocess.call(cmd, **kw)


__all__ = ["call", "clean_env", "module", "popen", "run"]
