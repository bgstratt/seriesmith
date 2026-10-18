"""
ff — the ffmpeg and ffprobe seriesmith runs, found once:

    ffmpeg    on PATH, else imageio-ffmpeg's (a dependency of seriesmith, so in
              its own venv; inside ComfyUI, there when a node pack brought it),
              else the one in the repo's .venv (the editor inside ComfyUI, once
              run_seriesmith has set that up)
    ffprobe   on PATH, else helpers/ffprobe_av.py on this Python, when it has
              PyAV (every ComfyUI does): the same answers, through ffmpeg's own
              libraries (imageio-ffmpeg brings no ffprobe)

`tool(name)` is the command to put in front of the arguments: a list, since
the stand-in is a Python and a script. With nothing found it is just [name],
so the caller's FileNotFoundError says what it always said.

Stdlib only.
"""
from __future__ import annotations

import glob
import importlib.util
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FFPROBE_AV = os.path.join(HERE, "helpers", "ffprobe_av.py")
_FOUND: dict[str, list[str] | None] = {}


def _imageio_ffmpeg() -> str | None:
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        return exe if exe and os.path.isfile(exe) else None
    except Exception:                                     # noqa: BLE001  not installed, or no binary
        return None


def _repo_venv_ffmpeg() -> str | None:
    repo = os.path.dirname(HERE)
    pats = [os.path.join(repo, ".venv", "Lib", "site-packages", "imageio_ffmpeg", "binaries", "ffmpeg*"),
            os.path.join(repo, ".venv", "lib", "python*", "site-packages", "imageio_ffmpeg",
                         "binaries", "ffmpeg*")]
    for pat in pats:
        for exe in sorted(glob.glob(pat)):
            if os.path.isfile(exe) and os.access(exe, os.X_OK) and not exe.endswith(".txt"):
                return exe
    return None


def find(name: str) -> list[str] | None:
    """The command that runs `name` ("ffmpeg" or "ffprobe") here, or None."""
    if name in _FOUND:
        return _FOUND[name]
    exe = shutil.which(name)
    got = [exe] if exe else None
    if got is None and name == "ffmpeg":
        exe = _imageio_ffmpeg() or _repo_venv_ffmpeg()
        got = [exe] if exe else None
    if got is None and name == "ffprobe" and importlib.util.find_spec("av") is not None:
        got = [sys.executable, FFPROBE_AV]
    _FOUND[name] = got
    return got


def tool(name: str) -> list[str]:
    """The command for `name`, to put the arguments after; [name] when none
    was found (running it then fails as a missing program does)."""
    return list(find(name) or [name])


def have(name: str) -> bool:
    return find(name) is not None


def where(name: str) -> str:
    """What `name` resolves to, for a log or a readiness line."""
    got = find(name)
    if not got:
        return f"{name}: not found"
    return f"{name}: {got[0]}" if len(got) == 1 else f"{name}: PyAV ({os.path.basename(got[1])})"


__all__ = ["find", "have", "tool", "where"]
