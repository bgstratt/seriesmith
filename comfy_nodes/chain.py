"""
`continuous: latent` for any backend (h3pipe's docs/CONTINUOUS.md, phase b): a
shot that carries straight on from the previous take holds that take's last
frames at its own head, in latent space, and H3 generates the rest from there.

SeriesmithChainLatent   between the empty joint AV latent and the sampler, as
                        h3pipe's H3ChainLatent, but the previous take comes as
                        uploaded files, not from the episode folder:
                        `previous` its kept <stem>.latent.safetensors,
                        `previous_video` its mp4 (the fallback: its last frames
                        and sound through the VAEs). seriesmith finds the take
                        the cut uses when the job starts and uploads them.
                        `record` (JSON) says what was held, for the take's
                        record (`continued_from`).
SeriesmithChainTrim     after decoding: the held frames and their sound off the
                        front (h3pipe's H3ChainTrim).

H3's grids: a clip of 17k+5 frames is 5k+2 video latent steps; a hold of 17j+5
frames is the last 5j+2 steps of a take. Audio is 40 latent steps a second.
Ported from h3pipe's comfy_nodes/h3_chain.py.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess

import numpy as np
import torch

from . import _ff
from .shot import load_audio, load_latent

log = logging.getLogger("seriesmith")

FPS = 24
AUDIO_STEPS_PER_SECOND = 40


def frames_to_latents(frames: int) -> int:
    """Video latent steps for a 17k+5-frame clip (core's video_latent_t)."""
    return max(1, (int(frames) - 5) // 17 * 5 + 2) if frames > 5 else 2


def audio_steps(frames: int, fps: float = FPS) -> int:
    return round(int(frames) / fps * AUDIO_STEPS_PER_SECOND)


def chain(latent: dict, v_old, a_old, overlap: int, hold_audio: bool,
          fps: float = FPS) -> tuple[dict, dict]:
    """`latent` (the new shot's empty joint AV latent) with the previous take's
    last `overlap` frames (its video latent `v_old`, audio latent `a_old` or
    None) written into its head and masked out of the denoise. Returns (the
    latent, a record of what was held)."""
    import comfy.nested_tensor

    new = latent["samples"]
    if not getattr(new, "is_nested", False):
        raise ValueError("SeriesmithChainLatent needs H3's joint audio/video latent")
    v_new, a_new = [t.clone() for t in new.unbind()[:2]]
    if v_new.shape[1] != v_old.shape[1] or v_new.shape[3:] != v_old.shape[3:]:
        raise ValueError(f"the previous take's latent is {tuple(v_old.shape)}, this shot's "
                         f"{tuple(v_new.shape)}")
    steps = frames_to_latents(overlap)
    if steps >= v_new.shape[2] or steps > v_old.shape[2]:
        raise ValueError(f"a hold of {overlap} frames ({steps} latent steps) doesn't fit "
                         f"(this shot {v_new.shape[2]} steps, the previous {v_old.shape[2]})")
    v_new[:, :, :steps] = v_old[:, :, -steps:].to(v_new)
    v_mask = torch.ones_like(v_new)
    v_mask[:, :, :steps] = 0.0
    a_mask = torch.ones_like(a_new)
    held_audio = 0
    if hold_audio and a_old is not None:
        held_audio = min(audio_steps(overlap, fps), a_old.shape[-1], a_new.shape[-1] - 1)
        a_new[..., :held_audio] = a_old[..., -held_audio:].to(a_new)
        a_mask[..., :held_audio] = 0.0
    mask = latent.get("noise_mask")
    if getattr(mask, "is_nested", False):
        vm, am = mask.unbind()[:2]
        v_mask, a_mask = v_mask * vm.to(v_mask), a_mask * am.to(a_mask)
    out = dict(latent)
    out["samples"] = comfy.nested_tensor.NestedTensor((v_new, a_new))
    out["noise_mask"] = comfy.nested_tensor.NestedTensor((v_mask, a_mask))
    return out, {"overlap": int(overlap), "video_steps": steps, "audio_steps": held_audio}


def kept_latent(path: str):
    lat = load_latent(path)["samples"]
    if not getattr(lat, "is_nested", False):
        raise ValueError(f"{os.path.basename(path)} isn't an H3 joint audio/video latent")
    v, a = lat.unbind()[:2]
    return v, a


def read_frames(path: str) -> torch.Tensor:
    """Every frame of a video as a float IMAGE batch [T, H, W, 3] in 0..1."""
    wh = subprocess.run([*_ff.tool("ffprobe"), "-v", "error", "-select_streams", "v:0", "-show_entries",
                         "stream=width,height", "-of", "csv=p=0:s=x", path],
                        capture_output=True, text=True, check=True, timeout=60).stdout.strip()
    w, h = (int(x) for x in wh.split("x")[:2])
    raw = subprocess.run([*_ff.tool("ffmpeg"), "-v", "error", "-i", path, "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True, timeout=900).stdout
    arr = np.frombuffer(raw, dtype=np.uint8).reshape(-1, h, w, 3)
    return torch.from_numpy(arr.astype(np.float32) / 255.0)


def encoded_tail(video: str, frames: int, width: int, height: int, video_vae,
                 audio_vae, fps: float):
    """(video, audio or None) latents of a video's last `frames` frames and their
    sound, through the VAEs, the picture fitted to width x height."""
    import comfy.utils

    images = read_frames(video)
    total = int(images.shape[0])
    if total < frames:
        raise ValueError(f"{os.path.basename(video)} has {total} frames, fewer than the "
                         f"{frames} to hold")
    pixels = images[total - frames:]
    if pixels.shape[1] != height or pixels.shape[2] != width:
        pixels = comfy.utils.common_upscale(pixels.movedim(-1, 1), width, height, "lanczos",
                                            "center").movedim(1, -1)
    v = video_vae.encode(pixels[:, :, :, :3])
    a = None
    if audio_vae is not None:
        try:
            audio = load_audio(video, (total - frames) / fps, total / fps)
        except Exception:
            audio = None
        if audio is not None:
            import comfy.audio
            sr = audio["sample_rate"]
            want = getattr(audio_vae, "audio_sample_rate", 44100)
            wave = audio["waveform"] if sr == want else comfy.audio.resample(
                audio["waveform"], sr, want)
            a = audio_vae.encode(wave.movedim(1, -1))
    return v, a


def pixel_size(v_new, video_vae) -> tuple[int, int]:
    f = 32
    try:
        f = int(video_vae.spacial_compression_encode())
    except Exception:
        pass
    return int(v_new.shape[-1]) * f, int(v_new.shape[-2]) * f


def _input_file(name: str) -> str:
    """An uploaded input's path in ComfyUI's input folder ("" for none)."""
    if not (name or "").strip():
        return ""
    import folder_paths
    return folder_paths.get_annotated_filepath(name.strip())


class SeriesmithChainLatent:
    """Hold the previous take's last frames at this shot's head (see the module)."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "latent": ("LATENT",),
            "overlap": ("INT", {"default": 39, "min": 5, "max": 360, "step": 17}),
            "hold_audio": ("BOOLEAN", {"default": True}),
        }, "optional": {
            "previous": ("STRING", {"default": "", "tooltip": "the previous take's kept latent, uploaded"}),
            "previous_video": ("STRING", {"default": "", "tooltip": "the previous take's mp4, uploaded"}),
            "source": ("STRING", {"default": "{}", "tooltip": "the previous take: {shot, take, pass, sha1}"}),
            "video_vae": ("VAE",),
            "audio_vae": ("VAE",),
            "fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 120.0}),
        }}

    RETURN_TYPES = ("LATENT", "STRING")
    RETURN_NAMES = ("latent", "record")
    FUNCTION = "chain"
    CATEGORY = "seriesmith"

    def chain(self, latent, overlap, hold_audio, previous="", previous_video="", source="{}",
              video_vae=None, audio_vae=None, fps=24.0):
        overlap, fps = int(overlap), float(fps)
        try:
            src = json.loads(source or "{}")
        except ValueError:
            src = {}
        lat, video = _input_file(previous), _input_file(previous_video)
        out = rec = via = None
        why = ""
        if lat:
            try:
                v_old, a_old = kept_latent(lat)
                out, rec = chain(latent, v_old, a_old, overlap, hold_audio, fps)
                via = "latent"
            except Exception as e:                       # another size or model: its frames
                if not video:
                    raise
                why = f"its latent wasn't usable ({e}); "
        if out is None:
            if not video:
                raise ValueError("no previous take to hold: neither a latent nor a video came")
            if video_vae is None:
                raise ValueError("the previous take kept no latent, and no VAE is wired to "
                                 "encode its frames")
            v_new = latent["samples"].unbind()[0]
            w, h = pixel_size(v_new, video_vae)
            v_old, a_old = encoded_tail(video, overlap, w, h, video_vae,
                                        audio_vae if hold_audio else None, fps)
            out, rec = chain(latent, v_old, a_old, overlap, hold_audio, fps)
            via = "frames"
        log.info("seriesmith: held %d video steps%s (%d frames, from its %s)%s",
                 rec["video_steps"],
                 f" and {rec['audio_steps']} audio steps" if rec["audio_steps"] else "",
                 overlap, via, f"; {why}" if why else "")
        return (out, json.dumps(dict(src, via=via, **rec)))


class SeriesmithChainTrim:
    """The held frames (and the sound under them) off the front of a decoded
    `continuous: latent` render."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "images": ("IMAGE",),
            "frames": ("INT", {"default": 39, "min": 0, "max": 4096}),
            "fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 120.0}),
        }, "optional": {
            "audio": ("AUDIO",),
        }}

    RETURN_TYPES = ("IMAGE", "AUDIO")
    RETURN_NAMES = ("images", "audio")
    FUNCTION = "trim"
    CATEGORY = "seriesmith"

    def trim(self, images, frames, fps, audio=None):
        frames = int(frames)
        if frames >= images.shape[0]:
            raise ValueError(f"SeriesmithChainTrim: {images.shape[0]} frames, {frames} to trim")
        if audio is not None:
            cut = round(frames / float(fps) * audio["sample_rate"])
            audio = dict(audio, waveform=audio["waveform"][..., cut:])
        return (images[frames:], audio)


NODE_CLASS_MAPPINGS = {"SeriesmithChainLatent": SeriesmithChainLatent,
                       "SeriesmithChainTrim": SeriesmithChainTrim}
NODE_DISPLAY_NAME_MAPPINGS = {"SeriesmithChainLatent": "seriesmith Chain Latent (continuous: latent)",
                              "SeriesmithChainTrim": "seriesmith Chain Trim"}
