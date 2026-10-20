"""
ff — the ffmpeg and ffprobe seriesmith runs, found once:

    first     the folder Settings names (ffmpeg_dir: your own build), else the
              build the Features window downloaded (beside the settings file,
              ffmpeg/), when it has the tool
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
import json
import os
import shutil
import subprocess
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


def _in(folder: str | None, name: str) -> str | None:
    if not folder:
        return None
    for n in (name + ".exe", name) if os.name == "nt" else (name,):
        p = os.path.join(folder, n)
        if os.path.isfile(p):
            return p
    return None


def _settings_dir() -> str | None:
    try:
        from seriesmith.settings import load_settings
        return load_settings().ffmpeg_dir
    except (OSError, ValueError):
        return None


def managed() -> str | None:
    """The folder of the build the Features window downloaded, if it's there."""
    from seriesmith.settings import settings_path
    d = os.path.join(os.path.dirname(settings_path()), "ffmpeg")
    return d if _in(d, "ffmpeg") and _in(d, "ffprobe") else None


def forget() -> None:
    """Find them again (a build downloaded, the settings' folder changed)."""
    _FOUND.clear()


def find(name: str) -> list[str] | None:
    """The command that runs `name` ("ffmpeg" or "ffprobe") here, or None."""
    if name in _FOUND:
        return _FOUND[name]
    exe = _in(_settings_dir(), name) or _in(managed(), name) or shutil.which(name)
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


class FFError(RuntimeError):
    """ffprobe or ffmpeg ran and failed; the message is what it said."""


def probe_json(path: str, *args: str, timeout: float = 60) -> dict:
    """ffprobe's JSON for `path`, asked with `args` (each caller its own:
    "-show_entries", "-count_frames", "-show_data", ...). FFError when it
    fails or says something that isn't JSON; FileNotFoundError when there is
    no ffprobe at all (tool() is then the bare name)."""
    r = subprocess.run([*tool("ffprobe"), "-v", "error", *args, "-of", "json", path],
                       capture_output=True, timeout=timeout)
    err = r.stderr.decode("utf-8", "replace").strip()
    if r.returncode != 0:
        raise FFError(err or f"ffprobe exited {r.returncode}")
    try:
        d = json.loads(r.stdout.decode("utf-8", "replace") or "{}")
    except ValueError:
        raise FFError(f"ffprobe's answer isn't JSON: {r.stdout[:200]!r}") from None
    if not isinstance(d, dict):
        raise FFError(f"ffprobe's answer isn't an object: {r.stdout[:200]!r}")
    return d


def frame_md5s(path: str, at: float, count: int, timeout: float = 600) -> list[str]:
    """framemd5 of `count` decoded frames of `path`'s picture from `at` seconds
    (input seeking: a caller works out `at` from the frame it wants). FFError
    when they don't decode cleanly (anything on stderr counts)."""
    r = subprocess.run([*tool("ffmpeg"), "-v", "error", "-ss", f"{max(0.0, at):.6f}", "-i", path,
                        "-map", "0:v:0", "-frames:v", str(count), "-f", "framemd5", "-"],
                       capture_output=True, timeout=timeout)
    err = r.stderr.decode("utf-8", "replace").strip()
    if r.returncode != 0 or err:
        raise FFError(err or f"ffmpeg exited {r.returncode}")
    return [ln.rsplit(",", 1)[1].strip() for ln in r.stdout.decode("utf-8", "replace").splitlines()
            if ln and not ln.startswith("#")]


__all__ = ["FFError", "find", "forget", "frame_md5s", "have", "managed", "probe_json", "tool",
           "where"]
