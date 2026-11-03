"""
Music nodes.

SeriesmithAudioSpanMask   a noise mask over a span of seconds of an audio latent
                          (ACE-Step 1.5's, YuE2's: [batch, channels, frames]),
                          so the sampler makes that span again and keeps the
                          rest: a cue take's bars repainted (seriesmith/cue.py).
                          ComfyUI's SetLatentNoiseMask makes a picture's mask
                          (height by width), which a 1-D audio latent can't take.
SeriesmithVocals          a recording split into its vocal stem and the rest
                          (torchaudio's Hybrid Demucs, HDEMUCS_HIGH_MUSDB_PLUS):
                          a song's singing, for align to transcribe and, when
                          the episode asks, for a singing shot's window
                          (seriesmith/vocals.py, docs/SOUND.md phase 7).
"""
from __future__ import annotations

import torch

try:
    from . import _hub
except ImportError:                       # this file loaded on its own (a test), not as the pack
    import importlib.util as _iu
    import os as _os
    _spec = _iu.spec_from_file_location(
        "seriesmith_nodes_hub", _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "_hub.py"))
    _hub = _iu.module_from_spec(_spec)
    _spec.loader.exec_module(_hub)


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


# Hybrid Demucs's weights (torchaudio's HDEMUCS_HIGH_MUSDB_PLUS): read from
# models/demucs/ (the Features window puts them there), else from the copy
# torchaudio's bundle downloaded into torch's hub cache before; never fetched
# here (the bundle would, silently): without them the split fails saying so
DEMUCS_FOLDER = "demucs"
DEMUCS_FILE = "hdemucs_high_trained.pt"
DEMUCS_RATE = 44100
DEMUCS_SOURCES = ["drums", "bass", "other", "vocals"]
_MODEL: dict = {}


def _register_folder() -> None:
    """models/demucs/ known to ComfyUI (its /internal/folder_paths lists it)."""
    try:
        import os

        import folder_paths
        if DEMUCS_FOLDER not in folder_paths.folder_names_and_paths:
            folder_paths.add_model_folder_path(
                DEMUCS_FOLDER, os.path.join(folder_paths.models_dir, DEMUCS_FOLDER))
    except Exception:                                     # noqa: BLE001  outside ComfyUI (tests)
        pass


_register_folder()


def demucs_weights() -> str:
    """The weights file: models/demucs/, else torchaudio's copy in torch's hub
    cache; RuntimeError saying to download them in the Features window."""
    try:
        import folder_paths
        mine = folder_paths.get_full_path(DEMUCS_FOLDER, DEMUCS_FILE)
    except Exception:                                     # noqa: BLE001
        mine = None
    return _hub.hdemucs_weights(mine)


def demucs_model(device):
    """Hybrid Demucs (four sources, 44.1 kHz), loaded once and kept."""
    if "model" not in _MODEL:
        from torchaudio.models import hdemucs_high
        path = demucs_weights()
        model = hdemucs_high(sources=DEMUCS_SOURCES)
        model.load_state_dict(torch.load(path, map_location="cpu", weights_only=True))
        _MODEL["model"] = model.eval()
    return _MODEL["model"].to(device)


def separate(model, mix, rate: int = DEMUCS_RATE, segment: float = 10.0,
             overlap: float = 0.1):
    """`mix` [batch, channels, samples] split by `model` into [batch, sources,
    channels, samples]: `segment`-second chunks with `overlap` of each faded
    into the next (torchaudio's Hybrid Demucs tutorial), so a whole song fits
    a card. Normalized as the tutorial does, and put back."""
    from torchaudio.transforms import Fade
    batch, channels, length = mix.shape
    ref = mix.mean(1)
    mean, std = ref.mean(), ref.std().clamp_min(1e-8)
    mix = (mix - mean) / std
    chunk = int(rate * segment * (1 + overlap))
    over = int(overlap * rate)
    fade = Fade(fade_in_len=0, fade_out_len=over, fade_shape="linear")
    final = torch.zeros(batch, len(model.sources), channels, length, device=mix.device)
    start, end = 0, chunk
    while start < length - over:
        piece = mix[:, :, start:end]
        with torch.no_grad():
            out = model(piece)
        out = fade(out)
        final[:, :, :, start:start + out.shape[-1]] += out
        if start == 0:
            fade.fade_in_len = over
            start += chunk - over
        else:
            start += chunk
        end += chunk
        if end >= length:
            fade.fade_out_len = 0
    return final * std + mean


class SeriesmithVocals:
    """A recording split by Hybrid Demucs (torchaudio's HDEMUCS_HIGH_MUSDB_PLUS)
    into its vocal stem and its accompaniment (drums, bass and the rest summed),
    both at 44.1 kHz stereo. A mono recording is split as two channels of it."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "audio": ("AUDIO",),
            "segment": ("FLOAT", {"default": 10.0, "min": 2.0, "max": 60.0, "step": 0.5}),
            "overlap": ("FLOAT", {"default": 0.1, "min": 0.0, "max": 0.5, "step": 0.01}),
        }}

    RETURN_TYPES = ("AUDIO", "AUDIO")
    RETURN_NAMES = ("vocals", "accompaniment")
    FUNCTION = "split"
    CATEGORY = "seriesmith/audio"

    def split(self, audio, segment=10.0, overlap=0.1):
        import torchaudio.functional as AF
        try:
            import comfy.model_management as mm
            device = mm.get_torch_device()
        except Exception:                                 # noqa: BLE001  outside ComfyUI
            device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        wave = audio["waveform"].float()
        rate = int(audio["sample_rate"])
        if wave.dim() == 2:
            wave = wave.unsqueeze(0)
        if wave.shape[1] == 1:
            wave = wave.repeat(1, 2, 1)
        elif wave.shape[1] > 2:
            wave = wave[:, :2]
        if rate != DEMUCS_RATE:
            wave = AF.resample(wave, rate, DEMUCS_RATE)
        model = demucs_model(device)
        try:
            parts = separate(model, wave.to(device), DEMUCS_RATE, segment, overlap).cpu()
        finally:
            model.to("cpu")
            try:
                import comfy.model_management as mm
                mm.soft_empty_cache()
            except Exception:                             # noqa: BLE001
                pass
        v = DEMUCS_SOURCES.index("vocals")
        vocals = parts[:, v]
        rest = parts.sum(1) - vocals
        return ({"waveform": vocals.contiguous(), "sample_rate": DEMUCS_RATE},
                {"waveform": rest.contiguous(), "sample_rate": DEMUCS_RATE})


NODE_CLASS_MAPPINGS = {"SeriesmithAudioSpanMask": SeriesmithAudioSpanMask,
                       "SeriesmithVocals": SeriesmithVocals}

NODE_DISPLAY_NAME_MAPPINGS = {"SeriesmithAudioSpanMask": "Audio Span Mask (seriesmith)",
                              "SeriesmithVocals": "Vocal Stem (seriesmith, Hybrid Demucs)"}
