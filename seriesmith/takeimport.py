"""
takeimport — a video from outside seriesmith as a shot's take, and a take of
one shot copied in as another's (docs/PLAN.md, "Takes from outside: import and
drag"); the shot-side counterpart of refs.import_take / copy_take.

    import_take(root, pass_, shot, source_path)       -> Take  (source "imported")
    copy_take(root, pass_, shot, from_shot, take)      -> Take  (copied_from)
    hold_take(root, pass_, shot, picture, seconds, ...) -> Take  (held)
    hold_frame(root, pass_, shot, from_shot, take, frame, seconds, ...) -> Take

An imported take is a take like any other on disk (<renders>/<shot>/<stem>.mp4,
its sidecar, thumbnail and strip), with nothing that made it: no seed, prompt,
model or hashes, so it is never stale, and nothing re-samples it (an upscale
is the pixel method or SeedVR2). Its frames, frame rate, size and audio are the
file's. An H.264 mp4 in 4:2:0 is copied as it is; anything else (ProRes,
HEVC, VP9, a .mov or .mkv) is encoded to H.264 at master quality so the editor
plays it and assemble treats it as its own, the audio as AAC. The original
isn't kept.

A held take is a picture (a card, "Two hours later"; or one frame of a take,
a freeze frame) held for a number of seconds: an H.264 mp4 at the pass's size
and the cut's frame rate, letterboxed if its aspect differs, with no sound
(assemble lays silence under it). Imported as any other, `held` in its record.

ffmpeg / ffprobe through seriesmith.ff.
"""
from __future__ import annotations

import os
import subprocess
import tempfile

from seriesmith import ff as FF
from seriesmith import finish as F
from seriesmith import takes as T
from seriesmith.core import fileio

VIDEO_EXTS = (".mp4", ".m4v", ".mov", ".webm", ".mkv", ".avi")
PICTURE_EXTS = (".png", ".jpg", ".jpeg", ".webp")
ENCODE_TIMEOUT = 3600
HOLD_MAX_SECONDS = 600


class TakeImportError(ValueError):
    """A file that can't become a take (said to the user as it is)."""
    http_status = 400


def check_import_type(name: str) -> str:
    """The extension a video called `name` is imported with, or TakeImportError."""
    ext = os.path.splitext(name or "")[1].lower()
    if ext not in VIDEO_EXTS:
        raise TakeImportError(f"a take is a video ({', '.join(VIDEO_EXTS)}), not "
                           f"{ext or 'a file with no extension'}")
    return ext


def playable(path: str, name: str | None = None) -> bool:
    """Whether a file is already what a take is: H.264 4:2:0 in an mp4
    (audio, if any, AAC), which every browser plays and assemble copies.
    ffprobe names .mov and .mp4 alike, so the name (`name`, else the path's)
    must say mp4 too."""
    if os.path.splitext(name or path)[1].lower() not in (".mp4", ".m4v"):
        _probe_video(path)
        return False
    out = _probe_video(path)
    streams = out.get("streams", [])
    video = next(s for s in streams if s.get("codec_type") == "video")
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    fmt = (out.get("format") or {}).get("format_name") or ""
    return ("mp4" in fmt.split(",") and video.get("codec_name") == "h264"
            and video.get("pix_fmt") in ("yuv420p", "yuvj420p")
            and all(a.get("codec_name") == "aac" for a in audio))


def _probe_video(path: str) -> dict:
    """ffprobe's streams and format, or TakeImportError for a file with no video."""
    try:
        out = FF.probe_json(path, "-show_streams", "-show_format", timeout=120)
    except FF.FFError as e:
        raise TakeImportError(f"ffprobe can't read it: {str(e)[-200:]}") from None
    streams = out.get("streams", [])
    if not any(st.get("codec_type") == "video" for st in streams):
        raise TakeImportError("it has no video stream")
    return out


def encode(src: str, dst: str) -> None:
    """`src` as an H.264 mp4 at master quality (x264 CRF 12, slow; as an
    upscale's `quality: master`), audio AAC, the frame rate kept."""
    tmp = fileio.temp_beside(dst, ".mp4")
    cmd = [*FF.tool("ffmpeg"), "-y", "-v", "error", "-i", src, "-map", "0:v:0", "-map", "0:a:0?",
           "-c:v", "libx264", "-preset", "slow", "-crf", "12", "-pix_fmt", "yuv420p",
           "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", "-fps_mode", "cfr",
           "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", tmp]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=ENCODE_TIMEOUT)
    except subprocess.CalledProcessError as e:
        _drop(tmp)
        raise TakeImportError("ffmpeg couldn't convert it: "
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


def _finish(take: T.Take, notes: list[str], **fields) -> T.Take:
    """The take's mp4 in place: probed, its thumbnail and strip made, its
    record closed ok."""
    info = F.probe(take.paths.mp4)
    thumb = strip = None
    try:
        F.thumb(take.paths.mp4, take.paths.thumb, info["frames"])
        thumb = os.path.basename(take.paths.thumb)
        F.strip(take.paths.mp4, take.paths.strip, info["frames"])
        strip = os.path.basename(take.paths.strip)
    except F.FinishError as e:
        notes.append(f"thumbnails failed: {e}")
    notes.append(f"{info['width']}x{info['height']} at {info['fps']:g} fps, "
                 f"{'with' if info['audio'] else 'no'} audio")
    take.sidecar = T.update_sidecar(
        take.paths.sidecar, status="ok", finished=T.now(), frames=info["frames"],
        fps=info["fps"], width=info["width"], height=info["height"],
        mp4=os.path.basename(take.paths.mp4), thumb=thumb, strip=strip,
        save_notes=f"{take.paths.stem}: " + "; ".join(notes), **fields)
    return take


def _reserve(root: str, pass_: str, shot: str, note: str, **origin) -> T.Take:
    return T.reserve_take(root, pass_, shot, {
        "status": "queued", "queued": T.now(), "source": "imported", **origin,
        "comfy_prompt_id": None, "seed": None, "seed_source": None, "prompt": None,
        "model": None, "loras": None, "steps": None, "target": None, "note": note})


def import_take(root: str, pass_: str, shot: str, source_path: str, note: str = "",
                original_name: str | None = None) -> T.Take:
    """A video on disk as `shot`'s next take in `pass_` (source "imported"),
    status ok. `original_name` is an upload's own name: `source_path` is then
    its temporary file, which isn't recorded, and the type is judged by the
    name."""
    if not isinstance(source_path, str) or not source_path:
        raise TakeImportError("source_path is required: a video on this machine")
    if not os.path.isabs(source_path):
        raise TakeImportError(f"source_path must be absolute, not {source_path!r}")
    if not os.path.isfile(source_path):
        raise FileNotFoundError(f"no file at {source_path}")
    check_import_type(original_name or source_path)
    copy = playable(source_path, original_name)
    origin = ({"source_path": None, "original_name": os.path.basename(original_name)}
              if original_name else {"source_path": source_path})
    take = _reserve(root, pass_, shot, note, **origin)
    notes = [f"uploaded as {os.path.basename(original_name)}" if original_name
             else f"imported from {source_path}"]
    try:
        if copy:
            fileio.copy(source_path, take.paths.mp4)
        else:
            encode(source_path, take.paths.mp4)
            notes.append("converted to H.264")
        return _finish(take, notes, converted=not copy)
    except BaseException as e:
        take.sidecar = T.record_failed(take.paths.sidecar, f"import failed: {e}")
        raise


def check_picture_type(name: str) -> str:
    """The extension a picture called `name` is held with, or TakeImportError."""
    ext = os.path.splitext(name or "")[1].lower()
    if ext not in PICTURE_EXTS:
        raise TakeImportError(f"a held picture is an image ({', '.join(PICTURE_EXTS)}), not "
                           f"{ext or 'a file with no extension'}")
    return ext


def check_hold(seconds, fps, size) -> tuple[float, float, tuple[int, int]]:
    """A hold's length, rate and (even) size, or TakeImportError."""
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) \
            or not 0 < seconds <= HOLD_MAX_SECONDS:
        raise TakeImportError(f"a hold's seconds are a number over 0, at most "
                           f"{HOLD_MAX_SECONDS}, not {seconds!r}")
    if isinstance(fps, bool) or not isinstance(fps, (int, float)) or fps <= 0:
        raise TakeImportError(f"a hold's frame rate must be over 0, not {fps!r}")
    try:
        w, h = (int(v) for v in size)
    except (TypeError, ValueError):
        raise TakeImportError(f"a hold's size is (width, height), not {size!r}") from None
    if w < 2 or h < 2:
        raise TakeImportError(f"a hold's size must be at least 2x2, not {w}x{h}")
    return float(seconds), float(fps), (w - w % 2, h - h % 2)


def hold_frames(seconds: float, fps: float) -> int:
    return max(1, round(seconds * fps))


def encode_hold(picture: str, dst: str, seconds: float, fps: float,
                size: tuple[int, int]) -> None:
    """`picture` held for `seconds` at `fps`, as an H.264 mp4 of `size`
    (scaled to fit, letterboxed in black), no sound; master quality, as
    encode()."""
    w, h = size
    tmp = fileio.temp_beside(dst, ".mp4")
    cmd = [*FF.tool("ffmpeg"), "-y", "-v", "error", "-loop", "1", "-framerate", f"{fps:g}",
           "-i", picture, "-frames:v", str(hold_frames(seconds, fps)),
           "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                  f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,"
                  "scale=out_color_matrix=bt709:out_range=tv",
           "-c:v", "libx264", "-preset", "slow", "-crf", "12", "-pix_fmt", "yuv420p",
           "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
           "-r", f"{fps:g}", "-an", "-movflags", "+faststart", tmp]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=ENCODE_TIMEOUT)
    except subprocess.CalledProcessError as e:
        _drop(tmp)
        raise TakeImportError("ffmpeg couldn't hold it: "
                           + (e.stderr or b"").decode("utf-8", "replace")[-300:]) from None
    except BaseException:
        _drop(tmp)
        raise
    fileio.replace(tmp, dst)


def hold_take(root: str, pass_: str, shot: str, picture: str, seconds: float, fps: float,
              size: tuple[int, int], original_name: str | None = None,
              note: str = "", held_from: dict | None = None) -> T.Take:
    """A picture held for `seconds` as `shot`'s next take in `pass_` (source
    "imported", `held` in its record). `original_name` is an upload's own name
    (`picture` its temporary file, not recorded); `held_from` the take a frame
    came from (hold_frame)."""
    seconds, fps, size = check_hold(seconds, fps, size)
    if not isinstance(picture, str) or not os.path.isabs(picture):
        raise TakeImportError(f"the picture's path must be absolute, not {picture!r}")
    if not os.path.isfile(picture):
        raise FileNotFoundError(f"no file at {picture}")
    if held_from is None:
        check_picture_type(original_name or picture)
    name = os.path.basename(original_name or picture)
    held = {"seconds": seconds, **({"from": held_from} if held_from else {"name": name})}
    origin = ({"source_path": None, "original_name": name}
              if original_name or held_from else {"source_path": picture})
    take = _reserve(root, pass_, shot, note, held=held, **origin)
    what = (f"frame {held_from['frame']} of {held_from['shot']} t{held_from['take']:02d}"
            if held_from else name)
    try:
        encode_hold(picture, take.paths.mp4, seconds, fps, size)
        return _finish(take, [f"{what} held {seconds:g} s"])
    except BaseException as e:
        take.sidecar = T.record_failed(take.paths.sidecar, f"hold failed: {e}")
        raise


def grab_frame(mp4: str, frame: int, dst: str) -> None:
    """Frame `frame` (from 0, decode order) of `mp4` as a png at `dst`;
    TakeImportError when the take has no such frame."""
    if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
        raise TakeImportError(f"frame is a frame number from 0, not {frame!r}")
    cmd = [*FF.tool("ffmpeg"), "-y", "-v", "error", "-i", mp4,
           "-vf", f"select=eq(n\\,{frame})", "-frames:v", "1", "-update", "1", dst]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=300)
    except subprocess.CalledProcessError as e:
        raise TakeImportError("ffmpeg couldn't take the frame: "
                           + (e.stderr or b"").decode("utf-8", "replace")[-300:]) from None
    if not os.path.isfile(dst) or os.path.getsize(dst) == 0:
        _drop(dst)
        raise TakeImportError(f"{os.path.basename(mp4)} has no frame {frame}")


def hold_frame(root: str, pass_: str, shot: str, from_shot: str, take: int, frame: int,
               seconds: float, fps: float, size: tuple[int, int],
               from_pass: str | None = None) -> T.Take:
    """Frame `frame` of take `take` of `from_shot` (in `from_pass`, default
    `pass_`) held for `seconds` as `shot`'s next take: a freeze frame."""
    check_hold(seconds, fps, size)
    src_pass = from_pass or pass_
    src = T.get_take(root, src_pass, from_shot, take)
    if src is None:
        raise LookupError(f"{from_shot} has no take {take} in {src_pass}")
    if not src.usable or not os.path.isfile(src.paths.mp4):
        raise TakeImportError(f"{from_shot} t{take:02d} isn't a finished take")
    fd, png = tempfile.mkstemp(prefix="seriesmith_hold_", suffix=".png")
    os.close(fd)
    try:
        grab_frame(src.paths.mp4, frame, png)
        return hold_take(root, pass_, shot, png, seconds, fps, size,
                         note=f"frame {frame} of {from_shot} t{take:02d}",
                         held_from={"shot": from_shot, "take": take, "pass": src_pass,
                                    "frame": frame})
    finally:
        _drop(png)


def copy_take(root: str, pass_: str, shot: str, from_shot: str, take: int,
              from_pass: str | None = None) -> T.Take:
    """Take `take` of `from_shot` (in `from_pass`, default `pass_`) copied in as
    `shot`'s next take in `pass_`: its video and sound (an `_h3.wav` too), the
    record saying where it came from (`copied_from`). Its upscale and post stay
    with the original. LookupError for a take that isn't there, TakeImportError
    for one that can't be copied (not finished, or the same shot and pass)."""
    src_pass = from_pass or pass_
    if from_shot == shot and src_pass == pass_:
        raise TakeImportError(f"{shot} t{take:02d} is already {shot}'s: pick it instead")
    src = T.get_take(root, src_pass, from_shot, take)
    if src is None:
        raise LookupError(f"{from_shot} has no take {take} in {src_pass}")
    if not src.usable or not os.path.isfile(src.paths.mp4):
        raise TakeImportError(f"{from_shot} t{take:02d} isn't a finished take")
    sc = src.sidecar or {}
    copied_from = {"shot": from_shot, "take": take, "pass": src_pass,
                   "target": sc.get("target"), "source": sc.get("source")}
    out = _reserve(root, pass_, shot, f"from {from_shot} t{take:02d}"
                   + (f" ({src_pass})" if src_pass != pass_ else ""), copied_from=copied_from)
    try:
        fileio.copy(src.paths.mp4, out.paths.mp4)
        if os.path.isfile(src.paths.h3_wav):
            fileio.copy(src.paths.h3_wav, out.paths.h3_wav)
        return _finish(out, [f"copied from {from_shot} t{take:02d} ({src_pass})"])
    except BaseException as e:
        out.sidecar = T.record_failed(out.paths.sidecar, f"copy failed: {e}")
        raise
