"""
Music nodes.

SeriesmithAudioSpanMask   a noise mask over a span of seconds of an audio latent
                          (ACE-Step 1.5's, YuE2's: [batch, channels, frames]),
                          so the sampler makes that span again and keeps the
                          rest: a cue take's bars repainted (seriesmith/cue.py).
                          ComfyUI's SetLatentNoiseMask makes a picture's mask
                          (height by width), which a 1-D audio latent can't take.
"""
from __future__ import annotations

import torch


class SeriesmithAudioSpanMask:
    """The latent with a noise mask of ones from `start` to `end` seconds (the
    span made again) and zeros elsewhere (kept), its edges ramped over
    `feather` seconds inside the span. `seconds` is the length of the audio the
    latent was encoded from, which places a second on the latent's frames."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "samples": ("LATENT",),
            "seconds": ("FLOAT", {"default": 30.0, "min": 0.01, "max": 10000.0, "step": 0.001}),
            "start": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 10000.0, "step": 0.001}),
            "end": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 10000.0, "step": 0.001}),
            "feather": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 10.0, "step": 0.01}),
        }}

    RETURN_TYPES = ("LATENT",)
    FUNCTION = "mask"
    CATEGORY = "seriesmith/audio"

    def mask(self, samples, seconds, start, end, feather):
        lat = samples["samples"]
        if getattr(lat, "is_nested", False) or lat.dim() != 3:
            raise ValueError("SeriesmithAudioSpanMask needs an audio latent [batch, channels, frames]")
        if not 0 <= start < end:
            raise ValueError(f"the span {start}-{end} s is empty")
        frames = lat.shape[-1]
        rate = frames / float(seconds)
        t = (torch.arange(frames, dtype=torch.float32) + 0.5) / rate      # each frame's centre
        m = ((t >= start) & (t < end)).float()
        if feather > 0:
            up = ((t - start) / feather).clamp(0, 1)
            down = ((end - t) / feather).clamp(0, 1)
            m = m * torch.minimum(up, down)
        out = dict(samples)
        out["noise_mask"] = m.reshape(1, 1, frames)
        return (out,)


NODE_CLASS_MAPPINGS = {"SeriesmithAudioSpanMask": SeriesmithAudioSpanMask}

NODE_DISPLAY_NAME_MAPPINGS = {"SeriesmithAudioSpanMask": "Audio Span Mask (seriesmith)"}
