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
SeriesmithRangeLatent   between the empty latent and the sampler: a take's whole
                        kept latent and sound held, only a range of its frames
                        made again.

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
from ._inputs import input_file
from .shot import load_audio, load_latent
from .shotplan import GRIDS

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


def hold_range(latent: dict, v_old, a_old, first: int, last: int, grid: str = "h3") -> tuple[dict, dict]:
    """`latent` (the shot's empty joint AV latent) holding a take's whole latent,
    with only the steps of frames first..last open to the denoise, and all of
    its sound held. Returns (the latent, a record of what was made again)."""
    import comfy.nested_tensor

    new = latent["samples"]
    if not getattr(new, "is_nested", False):
        raise ValueError("SeriesmithRangeLatent needs H3's joint audio/video latent")
    v_new, a_new = new.unbind()[:2]
    if v_new.shape != v_old.shape:
        raise ValueError(f"the take's latent is {tuple(v_old.shape)}, this render's "
                         f"{tuple(v_new.shape)}: render the range at the take's size and length")
    start, end = GRIDS[grid][1](first, last, v_new.shape[2])
    v_mask = torch.zeros_like(v_new)
    v_mask[:, :, start:end] = 1.0
    held_audio = 0
    a_out, a_mask = a_new, torch.ones_like(a_new)
    if a_old is not None and a_old.shape == a_new.shape:
        a_out, a_mask = a_old.to(a_new), torch.zeros_like(a_new)
        held_audio = int(a_new.shape[-1])
    out = dict(latent)
    out["samples"] = comfy.nested_tensor.NestedTensor((v_old.to(v_new), a_out))
    out["noise_mask"] = comfy.nested_tensor.NestedTensor((v_mask, a_mask))
    return out, {"first": int(first), "last": int(last), "video_steps": [start, end],
                 "audio_steps_held": held_audio}


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
    # passthrough: each frame the file has, once (a file whose first frame starts late, as an
    # imported clip's can, would otherwise gain a copy of it to fill the gap)
    raw = subprocess.run([*_ff.tool("ffmpeg"), "-v", "error", "-i", path, "-fps_mode", "passthrough",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
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


def fit_audio_latent(a, shape):
    """An encoded sound's latent cut or filled with silence to a render's: its one
    time axis, wherever the model keeps it (H3's last, LTX's third)."""
    for dim in range(a.ndim):
        if a.shape[dim] > shape[dim]:
            a = a.narrow(dim, 0, shape[dim])
        elif a.shape[dim] < shape[dim]:
            pad = list(a.shape)
            pad[dim] = shape[dim] - a.shape[dim]
            a = torch.cat([a, torch.zeros(pad, dtype=a.dtype, device=a.device)], dim=dim)
    return a


def encoded_take(video: str, frames: int, width: int, height: int, audio_shape,
                 video_vae, audio_vae, fps: float):
    """(video, audio or None) latents of a whole video from any model, as a render
    of `frames` frames at width x height holds them: the picture fitted, extra frames
    cut, missing ones the last frame again, the sound cut or filled with silence."""
    import comfy.utils

    images = read_frames(video)
    pixels = images[:frames]
    if pixels.shape[0] < frames:
        pixels = torch.cat([pixels, pixels[-1:].repeat(frames - pixels.shape[0], 1, 1, 1)])
    if pixels.shape[1] != height or pixels.shape[2] != width:
        pixels = comfy.utils.common_upscale(pixels.movedim(-1, 1), width, height, "lanczos",
                                            "center").movedim(1, -1)
    v = video_vae.encode(pixels[:, :, :, :3])
    a = None
    if audio_vae is not None:
        try:
            audio = load_audio(video)
        except Exception:
            audio = None
        if audio is not None:
            import comfy.audio
            sr = audio["sample_rate"]
            want = getattr(audio_vae, "audio_sample_rate", 44100)
            wave = audio["waveform"] if sr == want else comfy.audio.resample(audio["waveform"], sr, want)
            if wave.shape[1] == 1:
                wave = wave.repeat(1, 2, 1)
            need = round(frames / fps * want)
            wave = wave[..., :need]
            if wave.shape[-1] < need:
                wave = torch.nn.functional.pad(wave, (0, need - wave.shape[-1]))
            a = fit_audio_latent(audio_vae.encode(wave.movedim(1, -1)), audio_shape)
    return v, a


def pixel_size(v_new, video_vae) -> tuple[int, int]:
    f = 32
    try:
        f = int(video_vae.spacial_compression_encode())
    except Exception:
        pass
    return int(v_new.shape[-1]) * f, int(v_new.shape[-2]) * f


def _input_file(name: str) -> str:
    """An uploaded input's path in ComfyUI's input folder ("" for none), never outside
    ComfyUI's own folders (_inputs.input_file)."""
    return input_file(name)


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


class SeriesmithRangeLatent:
    """A take's whole latent and sound held, a range of its frames made again."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "latent": ("LATENT",),
            "take_latent": ("STRING", {"default": "", "tooltip": "the take's kept latent, uploaded"}),
            "first_frame": ("INT", {"default": 0, "min": 0, "max": 100000}),
            "last_frame": ("INT", {"default": 0, "min": 0, "max": 100000}),
        }, "optional": {
            "source": ("STRING", {"default": "{}", "tooltip": "the take: {shot, take, pass}"}),
            "take_video": ("STRING", {"default": "", "tooltip": "the take's video, uploaded: encoded when no latent came"}),
            "video_vae": ("VAE",),
            "audio_vae": ("VAE",),
            "fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 120.0}),
            "grid": ("STRING", {"default": "h3", "tooltip": "the model's frame grid: h3, ltx"}),
        }}

    RETURN_TYPES = ("LATENT", "STRING")
    RETURN_NAMES = ("latent", "record")
    FUNCTION = "hold"
    CATEGORY = "seriesmith"

    def hold(self, latent, take_latent, first_frame, last_frame, source="{}", take_video="",
             video_vae=None, audio_vae=None, fps=24.0, grid="h3"):
        path, video = _input_file(take_latent), _input_file(take_video)
        v_new, a_new = latent["samples"].unbind()[:2]
        v_old = a_old = None
        if path:
            v_old, a_old = kept_latent(path)
        if v_old is None or v_old.shape != v_new.shape:
            # no latent, or the kept one is another stage's size (LTX's first stage is half
            # the take's): the take's frames at this size, its kept sound if it has any
            if not (video and video_vae is not None):
                raise ValueError("SeriesmithRangeLatent: neither a take latent of this size nor a video and VAE came")
            w, h = pixel_size(v_new, video_vae)
            frames = GRIDS[grid][0](v_new.shape[2])
            v_old, encoded = encoded_take(video, frames, w, h, a_new.shape, video_vae,
                                          None if a_old is not None else audio_vae, float(fps))
            a_old = a_old if a_old is not None else encoded
        out, rec = hold_range(latent, v_old, a_old, first_frame, last_frame, grid)
        rec["via"] = "latent" if path else "frames"
        try:
            src = json.loads(source or "{}")
        except ValueError:
            src = {}
        log.info("seriesmith: making frames %d-%d again (latent steps %d-%d), the rest held",
                 first_frame, last_frame, *rec["video_steps"])
        return (out, json.dumps(dict(src, **rec)))


class SeriesmithRangeRefine:
    """LTX's second stage of a range re-render: the take's kept full-size latent (or its
    frames encoded, with the sound the first stage held), the range's steps from the
    upscaled first stage (`latent`), and only those open to the denoise."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "latent": ("LATENT",),
            "first_frame": ("INT", {"default": 0, "min": 0, "max": 100000}),
            "last_frame": ("INT", {"default": 0, "min": 0, "max": 100000}),
        }, "optional": {
            "take_latent": ("STRING", {"default": "", "tooltip": "the take's kept latent, uploaded"}),
            "take_video": ("STRING", {"default": "", "tooltip": "the take's video, uploaded: encoded when no latent came"}),
            "video_vae": ("VAE",),
            "grid": ("STRING", {"default": "ltx"}),
        }}

    RETURN_TYPES = ("LATENT",)
    FUNCTION = "refine"
    CATEGORY = "seriesmith"

    def refine(self, latent, first_frame, last_frame, take_latent="", take_video="", video_vae=None, grid="ltx"):
        import comfy.nested_tensor

        v_new, a_new = latent["samples"].unbind()[:2]
        path, video = _input_file(take_latent), _input_file(take_video)
        if path:
            v_old, a_old = kept_latent(path)
        elif video and video_vae is not None:
            w, h = pixel_size(v_new, video_vae)
            v_old = encoded_take(video, GRIDS[grid][0](v_new.shape[2]), w, h, a_new.shape, video_vae, None, 24.0)[0]
            a_old = a_new                                # what the first stage held or made
        else:
            raise ValueError("SeriesmithRangeRefine: neither a take latent nor a video and VAE came")
        out, rec = hold_range(latent, v_old, a_old, first_frame, last_frame, grid)
        start, end = rec["video_steps"]
        v_out, a_out = out["samples"].unbind()[:2]
        v_out = v_out.clone()
        v_out[:, :, start:end] = v_new[:, :, start:end].to(v_out)
        out["samples"] = comfy.nested_tensor.NestedTensor((v_out, a_out))
        return (out,)


class SeriesmithRangeFinish:
    """After decoding a range re-render: the take's frame count again, and its own
    sound over the picture (the held audio latent only guided the new frames)."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "images": ("IMAGE",),
            "frames": ("INT", {"default": 124, "min": 1, "max": 100000}),
            "fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 120.0}),
        }, "optional": {
            "sound": ("STRING", {"default": "", "tooltip": "the take's sound, uploaded"}),
            "audio": ("AUDIO", {"tooltip": "what the render made, for a take with no sound"}),
        }}

    RETURN_TYPES = ("IMAGE", "AUDIO")
    RETURN_NAMES = ("images", "audio")
    FUNCTION = "finish"
    CATEGORY = "seriesmith"

    def finish(self, images, frames, fps, sound="", audio=None):
        frames = int(frames)
        path = _input_file(sound)
        if path:
            audio = load_audio(path)
        elif audio is not None:
            audio = dict(audio, waveform=audio["waveform"][..., :round(frames / float(fps) * audio["sample_rate"])])
        return (images[:frames], audio)


NODE_CLASS_MAPPINGS = {"SeriesmithChainLatent": SeriesmithChainLatent,
                       "SeriesmithChainTrim": SeriesmithChainTrim,
                       "SeriesmithRangeLatent": SeriesmithRangeLatent,
                       "SeriesmithRangeRefine": SeriesmithRangeRefine,
                       "SeriesmithRangeFinish": SeriesmithRangeFinish}
NODE_DISPLAY_NAME_MAPPINGS = {"SeriesmithChainLatent": "seriesmith Chain Latent (continuous: latent)",
                              "SeriesmithChainTrim": "seriesmith Chain Trim",
                              "SeriesmithRangeLatent": "seriesmith Range Latent (re-render frames)",
                              "SeriesmithRangeRefine": "seriesmith Range Refine (LTX's second stage)",
                              "SeriesmithRangeFinish": "seriesmith Range Finish (the take's length and sound)"}
