"""The ffmpeg / ffprobe the nodes run: seriesmith.ff's (on PATH, else
imageio-ffmpeg's, else ffprobe through PyAV), found from the repo this pack is
linked from; a copied pack, without seriesmith, asks PATH and imageio-ffmpeg."""
from __future__ import annotations

import shutil


def tool(name: str) -> list[str]:
    """The command for `name`, to put the arguments after ([name] when none)."""
    try:
        from seriesmith import ff
        return ff.tool(name)
    except ImportError:
        pass
    exe = shutil.which(name)
    if not exe and name == "ffmpeg":
        try:
            import imageio_ffmpeg
            exe = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:                                 # noqa: BLE001  not there
            exe = None
    return [exe or name]


# ---------------------------------------------------------------------------
# starting a program: the one place the nodes do (seriesmith.proc's rules)
# ---------------------------------------------------------------------------

_SECRETS = ("COMFY_API_KEY", "HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HUGGINGFACE_HUB_TOKEN")


def _checked(cmd, kw: dict) -> list:
    """`cmd` as an argument list (never a shell line), and an environment without the keys
    a program the nodes run never needs, unless the caller passes its own."""
    import os
    if isinstance(cmd, (str, bytes)) or kw.pop("shell", None):
        raise ValueError("a program is started from an argument list, never a shell line")
    if kw.get("env") is None:
        kw["env"] = {k: v for k, v in os.environ.items()
                     if k.upper() not in _SECRETS and not k.upper().startswith("SERIESMITH_KEY_")}
    return [os.fspath(a) for a in cmd]


def run(cmd, **kw):
    import subprocess
    return subprocess.run(_checked(cmd, kw), **kw)


def popen(cmd, **kw):
    import subprocess
    return subprocess.Popen(_checked(cmd, kw), **kw)
