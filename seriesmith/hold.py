"""
hold — what the `hold` target renders: a shot's first keyframe held still for
its length (targets/video/hold/target.json). A card ("Two hours later"), a
title, a still, or a freeze frame (`continuous: first`, or a take's frame as
its first keyframe). No ComfyUI and no model: ffmpeg on this machine, on the
queue's local lane (runner.enqueue_hold), in a moment.

    encode(picture, dst, frames, fps, size, audio=None)
    render(job, take, report) -> "ok"            the take's mp4, thumbnail, strip, record

The picture is scaled to fit the pass's size and letterboxed in black,
BT.709, at the cut's frame rate, x264 CRF 12 (master quality, as an import).
Silent, unless the shot dubs a track (its sound set to dub): that track is
laid under it, cut or padded to the shot's length.

ffmpeg through seriesmith.ff.
"""
from __future__ import annotations

import os
import subprocess

from seriesmith import ff as FF
from seriesmith import finish as F
from seriesmith import takes as T
from seriesmith.core import fileio

TIMEOUT = 3600


class HoldError(RuntimeError):
    """A picture that couldn't be held (said as the take's error)."""


def is_hold(target) -> bool:
    """Whether `target` is rendered here, by hold (its target.json's
    `local_render`), not on a backend."""
    return (getattr(target, "spec", None) or {}).get("local_render") == "hold"


def encode(picture: str, dst: str, frames: int, fps: float, size: tuple[int, int],
           audio: str | None = None) -> None:
    """`picture` held for `frames` frames at `fps` as an H.264 mp4 of `size`
    (scaled to fit, letterboxed in black). `audio`, a sound file, is laid
    under it (AAC, cut or padded to the picture); else no sound."""
    w, h = (int(v) - int(v) % 2 for v in size)
    if frames < 1 or w < 2 or h < 2 or fps <= 0:
        raise HoldError(f"can't hold a picture for {frames} frames at {fps:g} fps, {w}x{h}")
    tmp = fileio.temp_beside(dst, ".mp4")
    cmd = [*FF.tool("ffmpeg"), "-y", "-v", "error", "-loop", "1", "-framerate", f"{fps:g}",
           "-i", picture]
    if audio:
        cmd += ["-i", audio]
    cmd += ["-frames:v", str(frames),
            "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                   f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,"
                   "scale=out_color_matrix=bt709:out_range=tv",
            "-c:v", "libx264", "-preset", "slow", "-crf", "12", "-pix_fmt", "yuv420p",
            "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
            "-r", f"{fps:g}"]
    if audio:
        cmd += ["-map", "0:v:0", "-map", "1:a:0", "-af", "apad", "-t", f"{frames / fps:.6f}",
                "-c:a", "aac", "-b:a", "192k"]
    else:
        cmd += ["-an"]
    cmd += ["-movflags", "+faststart", tmp]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=TIMEOUT)
    except subprocess.CalledProcessError as e:
        _drop(tmp)
        raise HoldError("ffmpeg couldn't hold it: "
                        + (e.stderr or b"").decode("utf-8", "replace")[-300:]) from None
    except BaseException:
        _drop(tmp)
        raise
    fileio.replace(tmp, dst)


def _drop(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def picture_of(job) -> str:
    """The picture a held shot holds: its first keyframe, on disk now (a
    continuity frame is cut into place when the job starts). HoldError when
    there's none."""
    rel = ((job.recompiled or job.shot).get("keyframes") or {}).get("first")
    if not rel:
        raise HoldError(f"{job.id} has no first keyframe to hold")
    path = rel if os.path.isabs(rel) else os.path.join(job.root, rel)
    if not os.path.isfile(path):
        raise HoldError(f"{job.id}'s first keyframe isn't there: {rel}")
    return path


def dub_audio(job) -> str | None:
    """A dub shot's sound to lay under the picture, as H3's and LTX's dubs
    hold it (held_audio.stage_dub): the recording's window of the shot, or
    the file it dubs. None for a shot that isn't a dub, or whose recording
    isn't there (the take says so)."""
    from seriesmith import audiocut as AC
    from seriesmith.targets import held_audio as HA
    entry = job.recompiled or job.shot
    if entry.get("audio_policy") not in HA.DUB:
        return None
    (slot,) = HA.recording_slot(job.doc, entry)
    track = slot["path"] and (slot["path"] if os.path.isabs(slot["path"])
                              else os.path.join(job.root, slot["path"]))
    if not track or not os.path.isfile(track):
        job.notes.append(f"dub without its recording ({slot['path'] or 'audio.track unset'}): "
                         "held silent")
        return None
    if "audio_in" in entry and not entry.get("audio_file"):
        return AC.window(track, float(entry["audio_in"]), float(entry["audio_out"]))
    return track


def render(job, take: T.Take, report, audio: str | None = None) -> str:
    """Hold `job`'s first keyframe into `take` (its mp4, thumbnail and strip;
    its record finished ok). `audio`: a track to lay under it (a dub)."""
    picture = picture_of(job)
    frames = int(job.frames)
    report(line=f"holding {os.path.relpath(picture, job.root)} for {frames} frames "
                f"at {job.fps:g} fps, {job.width}x{job.height}"
                + (", its dub under it" if audio else ""))
    encode(picture, take.paths.mp4, frames, job.fps, (job.width, job.height), audio)
    info = F.probe(take.paths.mp4)
    notes, thumb, strip = [], None, None
    try:
        F.thumb(take.paths.mp4, take.paths.thumb, info["frames"])
        thumb = os.path.basename(take.paths.thumb)
        F.strip(take.paths.mp4, take.paths.strip, info["frames"])
        strip = os.path.basename(take.paths.strip)
    except F.FinishError as e:
        notes.append(f"thumbnails failed: {e}")
    take.sidecar = T.update_sidecar(
        take.paths.sidecar, status="ok", finished=T.now(), frames=info["frames"],
        fps=info["fps"], width=info["width"], height=info["height"],
        mp4=os.path.basename(take.paths.mp4), thumb=thumb, strip=strip,
        save_notes="; ".join([f"{take.paths.stem}: held {frames} frames", *notes]))
    return "ok"
