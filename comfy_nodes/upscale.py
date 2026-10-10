"""
The upscale and post nodes that touch files, made portable: what h3pipe's
H3LoadTakeLatent / H3LoadTakeVideo / H3SaveUpscale read and wrote in the
episode folder comes as uploads and goes back as reported outputs, so any
backend can run an upscale or a post (seriesmith/finishing.py builds and
collects them). The compute nodes (H3PixelUpscale, H3FinishUpscale,
H3HoldAudio, H3MotionBlur, ...) are still h3pipe's (docs/PLAN.md, step 9).

SeriesmithLoadTakeLatent   a take's kept latent (an uploaded
                           <stem>.latent.safetensors), as the sampler made it
SeriesmithLoadTakeVideo    a take's frames and the audio its lips were made
                           against (an uploaded mp4, and its _h3.wav if any)
SeriesmithSaveUpscale      the frames as <name>.mp4 with the `source` mp4's
                           audio stream copied on unchanged, optionally the
                           last frame (<name>_last.png) and the re-sampled
                           latent (<name>.latent.safetensors), and a record
                           (<name>.record.json: the fields of the .up.json /
                           .post.json it closes), all in
                           <output>/seriesmith/<run>/ and reported

Ported from h3pipe's comfy_nodes/h3_upscale.py; the encoding helpers are its.
"""
from __future__ import annotations

import json
import math
import os
import re
import subprocess
import tempfile
import time

import numpy as np
import torch

from .chain import _input_file, read_frames
from .shot import RGB_TO_BT709, _now, _write_json_atomic, load_audio, load_latent, save_latent

RECORD_SUFFIX = ".record.json"


class SeriesmithLoadTakeLatent:
    """A take's kept latent, uploaded, as the sampler made it."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "latent": ("STRING", {"default": "", "tooltip": "the take's .latent.safetensors, uploaded"}),
        }}

    RETURN_TYPES = ("LATENT",)
    FUNCTION = "load"
    CATEGORY = "seriesmith/upscale"

    def load(self, latent):
        return (load_latent(_input_file(latent)),)


class SeriesmithLoadTakeVideo:
    """A take's frames and the audio its lips were made against: `audio` (H3's
    own mix, uploaded) wins over the video's audio stream; a mute take gives
    silence of its length."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "video": ("STRING", {"default": "", "tooltip": "the take's mp4, uploaded"}),
            "audio": ("STRING", {"default": "", "tooltip": "its _h3.wav, uploaded (optional)"}),
        }}

    RETURN_TYPES = ("IMAGE", "AUDIO")
    RETURN_NAMES = ("images", "audio")
    FUNCTION = "load"
    CATEGORY = "seriesmith/upscale"

    def load(self, video, audio=""):
        path = _input_file(video)
        images = read_frames(path)
        try:
            sound = load_audio(_input_file(audio) if (audio or "").strip() else path)
        except Exception:
            seconds = images.shape[0] / 24.0
            sound = {"waveform": torch.zeros(1, 1, max(1, int(44100 * seconds))),
                     "sample_rate": 44100}
        return (images, sound)


# ---------------------------------------------------------------------------
# encoding (h3pipe's h3_upscale.py, verbatim)
# ---------------------------------------------------------------------------

def has_audio(path: str) -> bool:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a",
                          "-show_entries", "stream=index", "-of", "csv=p=0", path],
                         capture_output=True, text=True, timeout=60).stdout
    return bool(out.strip())


def copy_audio(picture: str, source: str, out: str) -> str:
    """`out`: `picture`'s video with `source`'s audio stream copied on, bit for
    bit (no re-encode), or the picture alone when the source is mute. Returns
    "copied" or "none"."""
    if source and has_audio(source):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", picture, "-i", source,
                        "-map", "0:v:0", "-map", "1:a:0", "-c", "copy", out],
                       capture_output=True, check=True, timeout=300)
        return "copied"
    os.replace(picture, out)
    return "none"


ENCODERS = ("auto", "nvenc", "x264")
QUALITIES = ("review", "master")
_NVENC: set | None = None


def nvenc_encoders() -> set:
    """The NVENC encoders this ffmpeg has (h264_nvenc, hevc_nvenc, ...), asked once."""
    global _NVENC
    if _NVENC is None:
        try:
            out = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True,
                                 text=True, timeout=60).stdout
            _NVENC = {w for line in out.splitlines() for w in line.split() if w.endswith("_nvenc")}
        except Exception:
            _NVENC = set()
    return _NVENC


def x264_args(w: int, h: int, quality: str = "review") -> list:
    """x264 at `review` (CRF 16) or `master` quality (CRF 12, a slower preset:
    for delivery, still 8-bit 4:2:0 High so the editor's browser plays it)."""
    big = w * h > 4096 * 2304
    if quality == "master":
        return ["-c:v", "libx264", "-crf", "12", "-preset", "medium" if big else "slow",
                "-profile:v", "high", "-pix_fmt", "yuv420p"]
    # a frame past 4K takes the faster preset: CRF 16 on "medium" is ~1 fps at 5376x3072
    return ["-c:v", "libx264", "-crf", "16", "-preset", "fast" if big else "medium",
            "-pix_fmt", "yuv420p"]


def encoder_args(encoder: str, w: int, h: int, quality: str = "review") -> tuple[str, list]:
    """(the encoder used, its ffmpeg args). auto: H.264 on the GPU (NVENC) up to 4096
    on a side, x264 past that or without NVENC: always H.264, which the editor's
    browser plays. nvenc forces the GPU: H.264 up to 4096, HEVC past it; it raises
    without NVENC. `master` quality: auto is x264 at master quality; a forced
    NVENC runs its slowest preset at a lower CQ."""
    if encoder == "auto" and quality == "master":
        return "libx264", x264_args(w, h, quality)
    if encoder in ("auto", "nvenc"):
        have = nvenc_encoders()
        small = w <= 4096 and h <= 4096
        name = ("h264_nvenc" if small and "h264_nvenc" in have
                else "hevc_nvenc" if encoder == "nvenc" and "hevc_nvenc" in have else None)
        if name:
            hq = quality == "master"
            args = ["-c:v", name, "-preset", "p7" if hq else "p5", *(["-tune", "hq"] if hq else []),
                    "-rc", "vbr", "-cq", "14" if hq else "19", "-b:v", "0", "-pix_fmt", "yuv420p"]
            return name, args + (["-tag:v", "hvc1"] if name == "hevc_nvenc" else [])
        if encoder == "nvenc":
            raise RuntimeError("this ffmpeg has no NVENC encoder (h264_nvenc / hevc_nvenc)")
    return "libx264", x264_args(w, h, quality)


def fit_size(w: int, h: int, W: int, H: int, fit: str = "crop") -> tuple[int, int]:
    """What a w x h frame is scaled to, keeping its aspect, before it is cropped
    (`crop`: it covers W x H) or padded (`pad`: it fits inside) to W x H; even sides."""
    if fit == "crop":
        s = max(W / w, H / h)
        return (max(W, 2 * math.ceil(w * s / 2 - 1e-9)), max(H, 2 * math.ceil(h * s / 2 - 1e-9)))
    s = min(W / w, H / h)
    return (min(W, 2 * math.floor(w * s / 2 + 1e-9)), min(H, 2 * math.floor(h * s / 2 + 1e-9)))


def fit_filter(w: int, h: int, W: int, H: int, fit: str = "crop") -> str | None:
    """The ffmpeg -vf that makes a w x h frame exactly W x H (None: it is)."""
    if not W or not H or (w, h) == (W, H):
        return None
    iw, ih = fit_size(w, h, W, H, fit)
    parts = [f"scale={iw}:{ih}:flags=lanczos"] if (iw, ih) != (w, h) else []
    parts.append(f"crop={W}:{H}" if fit == "crop" else f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black")
    return ",".join(parts)


def encode_stream(images, path: str, fps: float, encoder: str = "auto",
                  size: tuple = (0, 0), fit: str = "crop", quality: str = "review") -> str:
    """Write `images` (IMAGE [T, H, W, 3]) to a mute mp4, one frame at a time into
    ffmpeg, made exactly `size` (W, H) by fit_filter when one is given. Returns
    the encoder used; on auto, a failed NVENC encode is retried on x264."""
    n, h, w = int(images.shape[0]), int(images.shape[1]), int(images.shape[2])
    fit_vf = fit_filter(w, h, int(size[0]), int(size[1]), fit)
    ow, oh = (int(size[0]), int(size[1])) if fit_vf else (w, h)
    vf = ",".join(f for f in (fit_vf, RGB_TO_BT709) if f)
    name, args = encoder_args(encoder, ow, oh, quality)

    def run(args: list) -> None:
        cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", f"{w}x{h}", "-framerate", str(fps), "-i", "-", "-frames:v", str(n),
               *(["-vf", vf] if vf else []), *args, path]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            for i in range(n):
                frame = (images[i].float().clamp(0, 1) * 255.0 + 0.5).to(torch.uint8)
                proc.stdin.write(frame.cpu().numpy().tobytes())
            proc.stdin.close()
            err = proc.stderr.read()
            if proc.wait(timeout=1800):
                raise RuntimeError(err.decode("utf-8", "replace")[-300:] or "ffmpeg failed")
        except BaseException:
            proc.kill()
            for fh in (proc.stdin, proc.stderr):
                try:
                    fh.close()
                except Exception:
                    pass
            proc.wait()
            raise

    try:
        run(args)
    except Exception:
        if encoder != "auto" or name == "libx264":
            raise
        name = "libx264"
        run(x264_args(ow, oh, quality))
    return name


def save_frame(image: torch.Tensor, path: str) -> None:
    """One IMAGE frame [H, W, 3] in 0..1 as a PNG, written atomically."""
    from PIL import Image
    arr = (image.clamp(0, 1).cpu().numpy() * 255.0 + 0.5).astype(np.uint8)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp.png"
    Image.fromarray(arr).save(tmp)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# SeriesmithSaveUpscale
# ---------------------------------------------------------------------------

class SeriesmithSaveUpscale:
    """Write an upscale (or a post) into <output>/seriesmith/<run>/ and report
    each file: <name>.mp4 (the picture, with `source`'s audio stream copied on:
    what plays is the take's, not a VAE round trip), <name>_last.png
    (`last_frame`: the last frame at the size it was made, before the delivery
    crop -- a continuity shot's upscale starts from it), <name>.latent.safetensors
    (`latent`, linked: a `continuous: latent` next shot's upscale holds its
    tail) and <name>.record.json (status, finished, frames, width, height, mp4,
    audio, encoder, quality, save_ms, save_notes, chain_hold: what seriesmith
    merges into the take's .up.json / .post.json). The mp4 comes first; the
    rest never fails it."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "images": ("IMAGE",),
            "source": ("STRING", {"default": "", "tooltip": "the mp4 whose audio is copied on, uploaded"}),
            "run": ("STRING", {"default": "upscale"}),
            "name": ("STRING", {"default": "take.up"}),
            "fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 60.0, "step": 1.0}),
            "encoder": (list(ENCODERS), {"default": "auto"}),
        }, "optional": {
            "width": ("INT", {"default": 0, "min": 0, "max": 8192, "step": 2}),
            "height": ("INT", {"default": 0, "min": 0, "max": 8192, "step": 2}),
            "fit": (["crop", "pad"], {"default": "crop"}),
            "quality": (list(QUALITIES), {"default": "review"}),
            "last_frame": ("BOOLEAN", {"default": False}),
            "latent": ("LATENT",),
            "chain_hold": ("STRING", {"default": "", "forceInput": True}),
        }}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("status",)
    FUNCTION = "save"
    OUTPUT_NODE = True
    CATEGORY = "seriesmith/upscale"

    def save(self, images, source, run, name, fps, encoder="auto", width=0, height=0,
             fit="crop", quality="review", last_frame=False, latent=None, chain_hold=""):
        import folder_paths

        run_safe = re.sub(r"[^A-Za-z0-9_.-]", "_", run) or "upscale"
        name = re.sub(r"[^A-Za-z0-9_.-]", "_", name) or "take.up"
        subfolder = f"seriesmith/{run_safe}"
        out_dir = os.path.join(folder_paths.get_output_directory(), "seriesmith", run_safe)
        os.makedirs(out_dir, exist_ok=True)
        out = os.path.join(out_dir, f"{name}.mp4")
        src = _input_file(source)
        notes, ms, clock = [], {}, time.perf_counter
        audio, ok, used = None, False, None
        fd, picture = tempfile.mkstemp(prefix=".tmp_", suffix=".mp4", dir=out_dir)
        os.close(fd)
        try:
            t0 = clock()
            used = encode_stream(images, picture, float(fps), encoder, (width, height), fit, quality)
            ms["mp4"] = round((clock() - t0) * 1000)
            notes.append(f"mp4 written ({used})")
            if os.path.isfile(picture):
                t0 = clock()
                audio = copy_audio(picture, src, out)
                ms["audio"] = round((clock() - t0) * 1000)
                notes.append("take's audio copied" if audio == "copied" else "the take is mute")
                ok = os.path.isfile(out)
        except Exception as exc:
            notes.append(f"failed: {exc}")
        finally:
            if os.path.exists(picture):
                os.remove(picture)
        last = lat = None
        if ok and last_frame:
            try:
                last = f"{name}_last.png"
                save_frame(images[-1], os.path.join(out_dir, last))
                notes.append("last frame kept")
            except Exception as exc:                        # the upscale itself is fine
                last = None
                notes.append(f"last frame not kept: {exc}")
        if ok and latent is not None:
            try:
                lat = save_latent(latent, os.path.join(out_dir, f"{name}.latent.safetensors"))
                notes.append("latent kept")
            except Exception as exc:
                lat = None
                notes.append(f"latent not kept: {exc}")
        ms["total"] = sum(ms.values())
        data = {"status": "ok" if ok else "failed", "finished": _now(),
                "frames": int(images.shape[0]),
                "width": int(width) if width and height else int(images.shape[2]),
                "height": int(height) if width and height else int(images.shape[1]),
                "audio": audio, "encoder": used, "quality": quality, "save_ms": ms,
                "save_notes": f"{name}.mp4: " + "; ".join(notes)}
        if chain_hold:
            try:
                data["chain_hold"] = json.loads(chain_hold)
            except ValueError:
                pass
        record = f"{name}{RECORD_SUFFIX}"
        _write_json_atomic(os.path.join(out_dir, record), data)

        def item(n):
            return {"filename": n, "subfolder": subfolder, "type": "output"}
        ui = {"files": [item(record)]}
        if ok:
            ui["gifs"] = [dict(item(os.path.basename(out)), format="video/h264-mp4")]
        if last:
            ui["images"] = [item(last)]
        if lat:
            ui["latents"] = [item(lat)]
        return {"ui": ui, "result": (data["save_notes"],)}


NODE_CLASS_MAPPINGS = {
    "SeriesmithLoadTakeLatent": SeriesmithLoadTakeLatent,
    "SeriesmithLoadTakeVideo": SeriesmithLoadTakeVideo,
    "SeriesmithSaveUpscale": SeriesmithSaveUpscale,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SeriesmithLoadTakeLatent": "Load Take Latent (seriesmith)",
    "SeriesmithLoadTakeVideo": "Load Take Video (seriesmith)",
    "SeriesmithSaveUpscale": "Save Upscale (seriesmith)",
}
