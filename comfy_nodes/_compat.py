"""
The parts of ComfyUI's own Python seriesmith's nodes call (not its node classes: the
pipeline checks those, seriesmith/features.py CORE_CLASSES), each with what uses it, looked
up once as the pack loads: a ComfyUI that renamed or dropped one says so at startup, naming
the seriesmith nodes it breaks, rather than failing mid-job. Checked against ComfyUI 0.43.

    missing()   [(the name, what of seriesmith's uses it)] for those not there
"""
from __future__ import annotations

import importlib
import logging

log = logging.getLogger("seriesmith")

MM = "comfy.model_management"
INTERNALS = [
    (MM, "get_torch_device", "the vocal stem, the latent upscalers, Magenta RT 2"),
    (MM, "soft_empty_cache", "the vocal stem, Magenta RT 2"),
    (MM, "free_memory", "Magenta RT 2"),
    (MM, "throw_exception_if_processing_interrupted", "Magenta RT 2 (cancelling a take)"),
    (MM, "load_models_gpu", "the pixel upscaler"),
    (MM, "load_model_gpu", "the frame interpolator (post)"),
    (MM, "intermediate_device", "the pixel upscaler"),
    (MM, "raise_non_oom", "the pixel upscaler (a smaller tile on out-of-memory)"),
    ("comfy.utils", "ProgressBar", "the upscalers, Magenta RT 2"),
    ("comfy.utils", "common_upscale", "latent chains, the upscalers"),
    ("comfy.utils", "tiled_scale", "the pixel upscaler"),
    ("comfy.nested_tensor", "NestedTensor", "latent chains, kept latents, the latent upscaler"),
    ("comfy.audio", "resample", "latent chains (a voice at another rate)"),
    ("folder_paths", "folder_names_and_paths", "the vocal stem's and Magenta RT 2's model folders"),
    ("folder_paths", "add_model_folder_path", "the vocal stem's and Magenta RT 2's model folders"),
    ("folder_paths", "get_folder_paths", "Magenta RT 2"),
    ("folder_paths", "get_full_path", "the vocal stem"),
    ("folder_paths", "get_annotated_filepath", "the shot loader, latent chains"),
    ("folder_paths", "get_output_directory", "the shot saver, the upscalers"),
    ("folder_paths", "models_dir", "the vocal stem's and Magenta RT 2's model folders"),
]


def missing() -> list[tuple[str, str]]:
    out = []
    for mod, attr, used_by in INTERNALS:
        try:
            ok = hasattr(importlib.import_module(mod), attr)
        except Exception:                                 # noqa: BLE001  the module itself gone
            ok = False
        if not ok:
            out.append((f"{mod}.{attr}", used_by))
    return out


def report() -> None:
    """One warning per missing part, at the pack's load."""
    for name, used_by in missing():
        log.warning("seriesmith: this ComfyUI has no %s, which %s use%s: update seriesmith, or "
                    "those won't work", name, used_by, "" if "," in used_by else "s")
