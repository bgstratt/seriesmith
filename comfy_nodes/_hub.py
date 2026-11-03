"""
What the node pack reads from torch's hub cache and Hugging Face's, found
without downloading: a package asked for a model it hasn't got fetches it then
and there, so the nodes look first and, when it isn't there, say to download it
in seriesmith's Features window (seriesmith/features.py reads these constants;
seriesmith/hubcache.py downloads them to the same places).

    htdemucs       demucs's default model (dub_keep_foley's vocal strip, shot.py):
                   torch.hub's checkpoints/<file> from dl.fbaipublicfiles.com
                   (demucs/remote/files.txt, htdemucs.yaml: one model, 955717e8);
                   demucs 4.1 looks on the Hugging Face hub first
                   (adefossez/HTDemucs), which counts too
    Hybrid Demucs  torchaudio's HDEMUCS_HIGH_MUSDB_PLUS weights (the vocal stem,
                   audio.py): models/demucs/, or the copy torchaudio downloaded
                   into torch's hub cache before

Stdlib only (torch is asked for its hub folder when it's loaded).
"""
from __future__ import annotations

import os
import sys

HTDEMUCS = "checkpoints/955717e8-8726e21a.th"          # its path in torch's hub folder
HTDEMUCS_URL = "https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/955717e8-8726e21a.th"
HTDEMUCS_HF = ("adefossez/HTDemucs", ("htdemucs.yaml", "955717e8.safetensors"))
TORCHAUDIO_HDEMUCS = "torchaudio/models/hdemucs_high_trained.pt"
DEMUCS_FEATURE = "Keep H3's foley under your vocal"
VOCALS_FEATURE = "Vocal stem"


def _cache_home() -> str:
    return os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")


def torch_hub_dir() -> str:
    """torch.hub.get_dir() (its own when torch is loaded: a set_dir counts)."""
    torch = sys.modules.get("torch")
    if torch is not None:
        try:
            return torch.hub.get_dir()
        except Exception:                                 # noqa: BLE001
            pass
    home = os.environ.get("TORCH_HOME") or os.path.join(_cache_home(), "torch")
    return os.path.join(os.path.expanduser(home), "hub")


def hf_cache_dir() -> str:
    for var in ("HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE"):
        if os.environ.get(var):
            return os.path.expanduser(os.environ[var])
    home = os.environ.get("HF_HOME") or os.path.join(_cache_home(), "huggingface")
    return os.path.join(os.path.expanduser(home), "hub")


def _file(p: str) -> str | None:
    return p if os.path.isfile(p) and os.path.getsize(p) > 0 else None


def torch_file(rel: str) -> str | None:
    """A file in torch's hub folder, when it's there."""
    return _file(os.path.join(torch_hub_dir(), *rel.split("/")))


def hf_files(repo: str, files) -> str | None:
    """The snapshot of `repo` refs/main names, when it has each of `files`."""
    d = os.path.join(hf_cache_dir(), "models--" + repo.replace("/", "--"))
    try:
        with open(os.path.join(d, "refs", "main"), encoding="utf-8") as fh:
            snap = os.path.join(d, "snapshots", fh.read().strip())
    except OSError:
        return None
    return snap if all(_file(os.path.join(snap, f)) for f in files) else None


def htdemucs_here() -> bool:
    """demucs's htdemucs is downloaded: in torch's hub cache, or (demucs 4.1)
    in the Hugging Face cache."""
    return bool(torch_file(HTDEMUCS) or hf_files(*HTDEMUCS_HF))


def demucs_env() -> dict:
    """demucs's environment: offline for the Hugging Face hub, so demucs 4.1
    reads its cache there or falls back to torch's (where htdemucs_here found
    it) and never fetches from either."""
    return dict(os.environ, HF_HUB_OFFLINE="1")


def strip_blocked() -> str | None:
    """Why the vocal strip can't run (the take's note), or None."""
    if htdemucs_here():
        return None
    return ("demucs's htdemucs model isn't downloaded - foley bed skipped (download it in "
            f"seriesmith's Features window: {DEMUCS_FEATURE})")


def hdemucs_weights(in_models: str | None) -> str:
    """Hybrid Demucs's weights: models/demucs/ (`in_models`, when it's there),
    else torchaudio's own copy in torch's hub cache. RuntimeError saying to
    download them in the Features window when neither is: torchaudio's
    bundle would fetch them silently."""
    hit = (in_models if in_models and _file(in_models) else None) or torch_file(TORCHAUDIO_HDEMUCS)
    if hit:
        return hit
    raise RuntimeError("Hybrid Demucs's weights (hdemucs_high_trained.pt) aren't downloaded: "
                       f"download them in seriesmith's Features window ({VOCALS_FEATURE}), "
                       "into ComfyUI's models/demucs")


__all__ = ["DEMUCS_FEATURE", "HTDEMUCS", "HTDEMUCS_HF", "HTDEMUCS_URL", "TORCHAUDIO_HDEMUCS",
           "VOCALS_FEATURE", "demucs_env", "hdemucs_weights", "hf_files", "htdemucs_here",
           "strip_blocked", "torch_file", "torch_hub_dir"]
