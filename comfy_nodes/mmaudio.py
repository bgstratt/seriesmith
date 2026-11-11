"""
SeriesmithMMAudioSampler: kijai's ComfyUI-MMAudio sampler, its frames taken by time.

MMAudio reads a video twice: CLIP frames at 8 fps and Synchformer frames at 25 fps. The pack's
process_video_tensor takes the first 8 x seconds frames for one and the first 25 x seconds for
the other, as if the frames came at those rates. From a 24 fps take the CLIP frames are then its
first third, spread over the whole length, and the sync frames run 4% slow and stop short. Here
each 8 fps and 25 fps frame is the take's frame at that moment (nearest), from `fps`, then sized
and normalised as the pack does (`prepared`); the rest is the pack's sampler as it is (its model,
its generate), its process_video_tensor stood in for during the call.

`frames: "as the pack takes them"` runs the pack's own way, for comparing. Needs ComfyUI-MMAudio
(its MMAudioSampler is found in ComfyUI's node mappings, not imported by path).
"""
from __future__ import annotations

import sys

import torch

FRAMES = ("by time", "as the pack takes them")


def at_rate(images: torch.Tensor, fps: float, rate: float, seconds: float) -> torch.Tensor:
    """The frames of `images` (n, h, w, c at `fps`) nearest each 1/rate second over `seconds`
    (no further than the video goes)."""
    n = int(images.shape[0])
    count = max(1, min(int(rate * seconds), int(rate * n / fps)))
    idx = [min(n - 1, int(round(i * fps / rate))) for i in range(count)]
    return images[idx]


CLIP_RATE, CLIP_SIZE = 8.0, 384
SYNC_RATE, SYNC_SIZE = 25.0, 224


def prepared(video: torch.Tensor, fps: float, seconds: float):
    """(CLIP frames, Synchformer frames, seconds) as the pack's process_video_tensor makes them
    (the same sizes and normalising: CLIP's 384 square, Synchformer's 224 crop at mean and std
    0.5), each frame taken at its moment. `video` is (n, h, w, c) in 0..1 at `fps`."""
    from torchvision.transforms import v2
    seconds = min(seconds, video.shape[0] / fps)
    clip = at_rate(video, fps, CLIP_RATE, seconds).permute(0, 3, 1, 2)
    sync = at_rate(video, fps, SYNC_RATE, seconds).permute(0, 3, 1, 2)
    clip = v2.Resize((CLIP_SIZE, CLIP_SIZE), interpolation=v2.InterpolationMode.BICUBIC)(clip)
    sync = v2.CenterCrop(SYNC_SIZE)(v2.Resize(SYNC_SIZE, interpolation=v2.InterpolationMode.BICUBIC)(sync))
    clip = clip.clamp(0, 1).float()
    sync = ((sync.clamp(0, 1) - 0.5) / 0.5).float()
    secs = min(seconds, clip.shape[0] / CLIP_RATE, sync.shape[0] / SYNC_RATE)
    return clip[:int(CLIP_RATE * secs)], sync[:int(SYNC_RATE * secs)], secs


def _pack_sampler():
    import nodes                                            # ComfyUI's own: every pack's mappings
    cls = nodes.NODE_CLASS_MAPPINGS.get("MMAudioSampler")
    if cls is None:
        raise RuntimeError("ComfyUI-MMAudio isn't installed: its MMAudioSampler isn't a node here")
    return cls, sys.modules[cls.__module__]


class SeriesmithMMAudioSampler:
    """MMAudio from a video, its 8 fps and 25 fps frames each taken at their moment."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "mmaudio_model": ("MMAUDIO_MODEL",),
            "feature_utils": ("MMAUDIO_FEATUREUTILS",),
            "images": ("IMAGE",),
            "fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 240.0, "step": 0.001,
                              "tooltip": "The frame rate the images come at"}),
            "duration": ("FLOAT", {"default": 8, "step": 0.01, "tooltip": "Seconds of sound"}),
            "steps": ("INT", {"default": 25, "step": 1}),
            "cfg": ("FLOAT", {"default": 4.5, "step": 0.1}),
            "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
            "prompt": ("STRING", {"default": "", "multiline": True}),
            "negative_prompt": ("STRING", {"default": "", "multiline": True}),
            "frames": (list(FRAMES), {"default": FRAMES[0]}),
            "force_offload": ("BOOLEAN", {"default": True}),
        }}

    RETURN_TYPES = ("AUDIO",)
    RETURN_NAMES = ("audio",)
    FUNCTION = "sample"
    CATEGORY = "seriesmith/audio"

    def sample(self, mmaudio_model, feature_utils, images, fps, duration, steps, cfg, seed, prompt,
               negative_prompt, frames=FRAMES[0], force_offload=True):
        cls, mod = _pack_sampler()
        run = lambda: cls().sample(mmaudio_model, seed, feature_utils, duration, steps, cfg,  # noqa: E731
                                   prompt, negative_prompt, False, force_offload, images=images)
        if frames != FRAMES[0]:
            return run()
        own = mod.process_video_tensor

        def by_time(video, seconds):
            return prepared(video, float(fps), float(seconds))
        mod.process_video_tensor = by_time
        try:
            return run()
        finally:
            mod.process_video_tensor = own


NODE_CLASS_MAPPINGS = {"SeriesmithMMAudioSampler": SeriesmithMMAudioSampler}
NODE_DISPLAY_NAME_MAPPINGS = {"SeriesmithMMAudioSampler": "MMAudio Sampler, frames by time (seriesmith)"}
