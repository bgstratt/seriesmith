"""
Magenta RealTime 2 (Google; the PyTorch port carried in _mrt2/, NOTICE.md there).

SeriesmithMRT2   a cue rendered from a style schedule: segments of frames (40 ms each),
                 each its own style (a text, or texts blended by weight, MusicCoCa's
                 embeddings averaged), drums (0 off, -1 the model's choice) and notes
                 (128 MIDI pitches: 0 off, 1 sustain, 2 onset, 3 either, -1 free), played
                 as one stream through the port's CUDA-graph streamer, which takes each
                 segment's conditioning as it comes (set_source). A cue's arc is a style a
                 bar (seriesmith/targets/music/mrt2/prompt.py), which it followed better than
                 any prompt did (docs/SOUND.md "Measured: MiniMax Music 3 and
                 Magenta RealTime 2"). An optional recording (a cue's theme) is blended into
                 every segment's style by MusicCoCa's audio embedding.

Its weights are read from models/magenta_rt/<repo id>/ (the Features window downloads them
there); nothing is fetched here.
"""
from __future__ import annotations

import json
import os

import torch

FOLDER = "magenta_rt"
MODELS = {"magenta-realtime-2": "magenta-community/magenta-realtime-2",
          "magenta-realtime-2-small": "magenta-community/magenta-realtime-2-small"}
MUSICCOCA = "magenta-community/magenta-rt-musiccoca-torch"
RATE = 48000
FRAME = 1920                                      # samples a frame: 40 ms at 48 kHz
_LOADED: dict = {}


def _register_folder() -> None:
    """models/magenta_rt/ known to ComfyUI (its /internal/folder_paths lists it)."""
    try:
        import folder_paths
        if FOLDER not in folder_paths.folder_names_and_paths:
            folder_paths.add_model_folder_path(FOLDER, os.path.join(folder_paths.models_dir, FOLDER))
    except Exception:                                     # noqa: BLE001  outside ComfyUI (tests)
        pass


_register_folder()


def repo_folder(repo: str) -> str:
    """models/magenta_rt/<org>/<name>/; RuntimeError saying how when it isn't there."""
    import folder_paths
    for base in folder_paths.get_folder_paths(FOLDER):
        d = os.path.join(base, *repo.split("/"))
        if os.path.isdir(d):
            return d
    raise RuntimeError(f"{repo} isn't in models/{FOLDER}: download it in seriesmith's Features "
                       f"window (Music: Magenta RealTime 2)")


def load(name: str):
    """The model and its MusicCoCa processor, loaded once (on the CPU between runs)."""
    if _LOADED.get("name") != name:
        _LOADED.clear()
        from ._mrt2.modeling_magenta_rt2 import MagentaRT2ForConditionalGeneration
        from ._mrt2.processing_musiccoca import MusicCoCaProcessor
        model = MagentaRT2ForConditionalGeneration.from_pretrained(
            repo_folder(MODELS[name]), dtype=torch.bfloat16).eval()
        model.set_processor(MusicCoCaProcessor.from_pretrained(repo_folder(MUSICCOCA), device="cpu"))
        _LOADED.update(name=name, model=model)
    return _LOADED["model"]


class _NoTorchTriton:
    """torch's own Triton kernels off while a cue renders (torch 2.15+, `torch._native`), and on
    again after. Inside ComfyUI with dynamic VRAM (comfy-aimdo hooks CUDA's allocator), a Triton
    kernel can't read that memory ("Pointer argument cannot be accessed from Triton (cpu
    tensor?)"), and the failed launch leaves CUDA broken for the next job. Off, torch uses its
    usual kernels. Nothing to do on a torch without them."""

    def __enter__(self):
        try:
            from torch._native import registry
            registry.deregister_op_overrides(disable_dsl_names="triton")
            self.registry = registry
        except Exception:                                 # noqa: BLE001  an older torch
            self.registry = None
        return self

    def __exit__(self, *exc):
        if self.registry is not None:
            try:
                self.registry.reenable_op_overrides(enable_dsl_names="triton")
            except Exception:                             # noqa: BLE001  leave them off
                pass
        return False


def _style(proc, style, cache: dict, theme=None, theme_weight: float = 0.0) -> list[int]:
    """12 style tokens: a text, or [[text, weight], ...] blended (MusicCoCa's embeddings
    averaged by weight), then the theme's embedding mixed in at `theme_weight`."""
    parts = [[style, 1.0]] if isinstance(style, str) else [[str(t), float(w)] for t, w in style]
    total = sum(w for _, w in parts) or 1.0
    emb = None
    for text, w in parts:
        if text not in cache:
            cache[text] = proc.embed(text)
        e = cache[text] * (w / total)
        emb = e if emb is None else emb + e
    if theme is not None and theme_weight > 0:
        emb = emb * (1 - theme_weight) + theme * theme_weight
    return [int(x) for x in proc.tokenize(emb)]


class SeriesmithMRT2:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "model": (list(MODELS), {"default": "magenta-realtime-2"}),
            "schedule": ("STRING", {"multiline": True, "default": json.dumps(
                {"segments": [{"frames": 250, "style": "cinematic orchestral strings"}]})}),
            # seriesmith's seeds are 63-bit (stable_seed); torch takes any to 2**64-1
            "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
            "temperature": ("FLOAT", {"default": 1.3, "min": 0.1, "max": 3.0, "step": 0.05}),
            "top_k": ("INT", {"default": 40, "min": 1, "max": 1024}),
            "cfg_musiccoca": ("FLOAT", {"default": 3.0, "min": -1.0, "max": 7.0, "step": 0.2}),
        }, "optional": {
            "theme": ("AUDIO",),
            "theme_weight": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.05}),
        }}

    RETURN_TYPES = ("AUDIO",)
    FUNCTION = "render"
    CATEGORY = "seriesmith/audio"

    @torch.no_grad()
    def render(self, model, schedule, seed, temperature, top_k, cfg_musiccoca, theme=None, theme_weight=0.5):
        import comfy.model_management as mm
        import comfy.utils
        segs = json.loads(schedule)["segments"]
        if not segs or any(int(s.get("frames") or 0) < 1 for s in segs):
            raise ValueError("SeriesmithMRT2: every segment needs one frame or more")
        m = load(model)
        proc = m.processor
        dev = mm.get_torch_device()
        mm.free_memory(12 * 1024 ** 3, dev)
        m.to(dev)
        proc.to(str(dev))
        quiet = _NoTorchTriton().__enter__()
        try:
            t_emb = None
            if theme is not None and theme_weight > 0:
                # MusicCoCa hears 16 kHz mono; resampled here with torchaudio (ComfyUI's), as
                # the port would with resampy, which ComfyUI hasn't
                import torchaudio.functional as AF
                from ._mrt2.musiccoca import AUDIO_SR
                w = theme["waveform"][0].float().mean(0).cpu()
                w = AF.resample(w, int(theme["sample_rate"]), AUDIO_SR)
                t_emb = proc._mc.embed_audio(w.numpy(), AUDIO_SR)
            cache: dict = {}

            def cond(s):
                toks = _style(proc, s.get("style") or "music", cache, t_emb, theme_weight)
                notes = s.get("notes")
                drums = [int(s["drums"])] if s.get("drums") is not None else None
                return toks, notes, drums

            total = sum(int(s["frames"]) for s in segs)
            bar = comfy.utils.ProgressBar(total)
            toks, notes, drums = cond(segs[0])
            streamer = m.make_cudagraph_streamer(style=toks, notes=notes, drums=drums,
                                                 cfg_musiccoca=cfg_musiccoca, temperature=temperature,
                                                 top_k=top_k, seed=int(seed))
            dec, out = m.init_decode_state(), []
            for i, s in enumerate(segs):
                mm.throw_exception_if_processing_interrupted()
                if i:
                    toks, notes, drums = cond(s)
                    c = m._resolve_conditioning(toks, notes, drums, cfg_musiccoca, None, None)
                    streamer.set_source(m.depthformer.encode(c).to(m._dt))
                frames = int(s["frames"])
                codes = [streamer.step() for _ in range(frames)]
                out.append(m.decode_stream(torch.cat(codes, dim=1), dec)[0].float().cpu())
                bar.update(frames)
            del streamer
            wave = torch.cat(out, dim=0).T.unsqueeze(0).contiguous()          # [1, 2, samples]
        finally:
            quiet.__exit__(None, None, None)
            m.to("cpu")
            proc.to("cpu")
            mm.soft_empty_cache()
        return ({"waveform": wave, "sample_rate": RATE},)


NODE_CLASS_MAPPINGS = {"SeriesmithMRT2": SeriesmithMRT2}
NODE_DISPLAY_NAME_MAPPINGS = {"SeriesmithMRT2": "Magenta RealTime 2 (seriesmith)"}
