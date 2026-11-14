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
import sys
from seriesmith import proc as PROC

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
    r = PROC.run([*tool("ffprobe"), "-v", "error", *args, "-of", "json", path],
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
    r = PROC.run([*tool("ffmpeg"), "-v", "error", "-ss", f"{max(0.0, at):.6f}", "-i", path,
                        "-map", "0:v:0", "-frames:v", str(count), "-f", "framemd5", "-"],
                       capture_output=True, timeout=timeout)
    err = r.stderr.decode("utf-8", "replace").strip()
    if r.returncode != 0 or err:
        raise FFError(err or f"ffmpeg exited {r.returncode}")
    return [ln.rsplit(",", 1)[1].strip() for ln in r.stdout.decode("utf-8", "replace").splitlines()
            if ln and not ln.startswith("#")]


# ---------------------------------------------------------------------------
# what ffmpeg and ffprobe may read
# ---------------------------------------------------------------------------

# An input is a file on this PC (or what seriesmith pipes in): never an address ffmpeg
# would fetch.
INPUT_PROTOCOLS = "file,pipe,fd"
# ...and one of the kinds of file seriesmith works with: video, sound and pictures. Not a
# playlist or a script of other files (hls, dash, concat, sdp, ...), which ffmpeg would
# otherwise take for media whatever the file is called, and follow to the files it names.
# Names as `ffmpeg -demuxers` lists them; one a build doesn't have is ignored.
INPUT_FORMATS = ",".join((
    "mov,mp4,m4a,3gp,3g2,mj2", "matroska,webm", "avi", "mxf", "mpegts", "mpeg", "flv", "dv", "m4v",
    "h264", "hevc", "mjpeg", "yuv4mpegpipe", "ivf",
    "wav", "w64", "mp3", "flac", "ogg", "aac", "aiff", "asf", "ac3", "eac3", "caf", "amr",
    "image2", "png_pipe", "jpeg_pipe", "webp_pipe", "tiff_pipe", "bmp_pipe", "exr_pipe", "dpx_pipe",
    "psd_pipe", "gif", "apng", "jpegxl_pipe", "qoi_pipe", "hdr_pipe", "pgm_pipe", "ppm_pipe"))


def _program(cmd0: str, name: str) -> bool:
    base = os.path.basename(str(cmd0)).lower()
    return base == name or base.startswith((name + ".", name + "-"))   # ffmpeg.exe, imageio's ffmpeg-win-...


def limited(cmd: list[str]) -> list[str]:
    """`cmd` with each input of an ffmpeg or ffprobe command held to INPUT_PROTOCOLS and
    INPUT_FORMATS; any other command as it is. An input whose format the command itself
    names (`-f lavfi`, `-f concat` over a list seriesmith wrote, `-f rawvideo` from a pipe)
    keeps that format. seriesmith.proc applies it to every program it starts."""
    if not cmd:
        return cmd
    guard = ["-protocol_whitelist", INPUT_PROTOCOLS]
    kinds = ["-format_whitelist", INPUT_FORMATS]
    if _program(cmd[0], "ffprobe"):
        if "-protocol_whitelist" in cmd:
            return cmd
        return [cmd[0], *guard, *([] if "-f" in cmd else kinds), *cmd[1:]]
    if not _program(cmd[0], "ffmpeg"):
        return cmd
    out, start, i = [cmd[0]], 1, 1
    while i < len(cmd):
        if cmd[i] == "-i" and i + 1 < len(cmd):
            mine = out[start:]                            # this input's own options
            if "-protocol_whitelist" not in mine:
                out += guard + ([] if "-f" in mine else kinds)
            out += [cmd[i], cmd[i + 1]]
            start, i = len(out), i + 2
            continue
        out.append(cmd[i])
        i += 1
    return out


__all__ = ["FFError", "find", "forget", "frame_md5s", "have", "limited", "managed", "probe_json", "tool",
           "where"]
