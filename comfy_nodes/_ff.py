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
