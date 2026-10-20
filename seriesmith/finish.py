"""
finish — what seriesmith makes from a take's mp4 itself, when no save node
did it (a hosted model returns only the video): its frame count, frame rate
and size (ffprobe), the thumbnail and the hover strip, in the save node's
sizes (comfy_nodes/shot.py: the middle frame at 480 px on its long side;
STRIP_FRAMES frames 192 px wide each).

Needs ffmpeg and ffprobe on PATH. Stdlib otherwise.
"""
from __future__ import annotations

import subprocess

from seriesmith import ff as FF
from seriesmith.takes import STRIP_FRAMES

THUMB_LONG_SIDE = 480
STRIP_CELL_WIDTH = 192
JPEG_Q = 3                     # ffmpeg's mjpeg scale (2-31, lower is better): ~quality 85


class FinishError(RuntimeError):
    pass


def _run(cmd: list[str]) -> bytes:
    try:
        return subprocess.run(cmd, check=True, capture_output=True, timeout=600).stdout
    except FileNotFoundError:
        raise FinishError(f"{cmd[0]} is not on PATH") from None
    except subprocess.CalledProcessError as e:
        raise FinishError(f"{cmd[0]} failed: {(e.stderr or b'').decode('utf-8', 'replace')[-200:]}") \
            from None


def probe(mp4: str) -> dict:
    """{"frames", "fps", "width", "height", "audio"} of a video file."""
    try:
        out = FF.probe_json(mp4, "-count_frames", "-show_streams", timeout=600)
    except FileNotFoundError:
        raise FinishError("ffprobe is not on PATH") from None
    except FF.FFError as e:
        raise FinishError(f"ffprobe failed: {str(e)[-200:]}") from None
    video = next((s for s in out.get("streams", []) if s.get("codec_type") == "video"), None)
    if video is None:
        raise FinishError(f"{mp4} has no video stream")
    num, _, den = str(video.get("avg_frame_rate") or video.get("r_frame_rate") or "24/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 24.0
    frames = int(video.get("nb_read_frames") or video.get("nb_frames") or 0)
    return {"frames": frames, "fps": round(fps, 3), "width": int(video["width"]),
            "height": int(video["height"]),
            "audio": any(s.get("codec_type") == "audio" for s in out.get("streams", []))}


def strip_indices(n: int) -> list[int]:
    """The save node's: the centre frame of each of STRIP_FRAMES equal parts."""
    k = min(STRIP_FRAMES, n)
    return [min(n - 1, int((i + 0.5) * n / k)) for i in range(k)]


def _select(indices: list[int]) -> str:
    return "select='" + "+".join(f"eq(n\\,{i})" for i in indices) + "'"


def thumb(mp4: str, path: str, frames: int) -> None:
    """The middle frame, its long side THUMB_LONG_SIDE."""
    scale = (f"scale='if(gte(iw,ih),{THUMB_LONG_SIDE},-2)':'if(gte(iw,ih),-2,{THUMB_LONG_SIDE})'"
             ":flags=lanczos")
    _run([*FF.tool("ffmpeg"), "-y", "-v", "error", "-i", mp4, "-vf",
          f"{_select([max(0, frames // 2)])},{scale}", "-frames:v", "1", "-q:v", str(JPEG_Q),
          path])


def strip(mp4: str, path: str, frames: int) -> None:
    """strip_indices' frames side by side, STRIP_CELL_WIDTH wide each."""
    idx = strip_indices(max(1, frames))
    _run([*FF.tool("ffmpeg"), "-y", "-v", "error", "-i", mp4, "-vf",
          f"{_select(idx)},scale={STRIP_CELL_WIDTH}:-2:flags=lanczos,tile={len(idx)}x1",
          "-fps_mode", "passthrough",
          "-frames:v", "1", "-q:v", str(JPEG_Q), path])
