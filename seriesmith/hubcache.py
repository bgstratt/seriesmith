"""
hubcache — the models a package fetches by itself the first time it runs, read
and downloaded where that package looks, so nothing downloads behind a job's
back: the Features window downloads each one (features kind "hub"), and the
job that needs one refuses, saying so, until it's there.

Three places, as the item's `folder` says:

    hf          Hugging Face's cache (HF_HUB_CACHE, else HF_HOME/hub, else
                ~/.cache/huggingface/hub): models--org--name/snapshots/<commit>/
                and refs/main naming the commit. huggingface_hub's own layout
                on a system without symlinks (Windows): the files themselves in
                the snapshot, no blobs. faster-whisper, transformers'
                from_pretrained (HunyuanVideo-Foley's SigLIP2 and CLAP) read it.
    torch       torch's hub folder (TORCH_HOME/hub, else ~/.cache/torch/hub):
                the item's name is the file's path inside it
                (checkpoints/<file>: torch.hub.load_state_dict_from_url; demucs's
                htdemucs).
    <folder>    a ComfyUI models folder: the repo's files straight into
                <models>/<folder>/<name>/ (a pack's own snapshot_download with
                local_dir: ComfyUI-MMAudio's BigVGAN in models/mmaudio/nvidia/),
                or <models>/<folder>/<dir>/ when the fetch names a `dir`: the
                pack reads it by another name (ComfyUI-Qwen-TTS: the model's
                name alone, models/qwen-tts/Qwen3-TTS-12Hz-1.7B-Base/).

A repo's files are fetched one by one through installer.download (a .part,
resumed), from the commit main names now; refs/main is written last, so a
snapshot half-fetched isn't taken for one that's there.

Stdlib only.
"""
from __future__ import annotations

import fnmatch
import glob
import json
import os
import urllib.parse
import urllib.request
from typing import Callable

from seriesmith.core import fileio as F

HF = "https://huggingface.co"
PLACES = ("hf", "torch")            # the two caches; anything else is a models folder


def _cache_home() -> str:
    return os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")


def hf_cache_dir() -> str:
    """Hugging Face's hub cache, as huggingface_hub works it out (its env vars)."""
    for var in ("HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE"):
        if os.environ.get(var):
            return os.path.expanduser(os.environ[var])
    home = os.environ.get("HF_HOME") or os.path.join(_cache_home(), "huggingface")
    return os.path.join(os.path.expanduser(home), "hub")


def torch_hub_dir() -> str:
    """torch.hub.get_dir() without torch: TORCH_HOME/hub, else ~/.cache/torch/hub."""
    home = os.environ.get("TORCH_HOME") or os.path.join(_cache_home(), "torch")
    return os.path.join(os.path.expanduser(home), "hub")


def repo_dir(repo: str) -> str:
    return os.path.join(hf_cache_dir(), "models--" + repo.replace("/", "--"))


def _has_all(folder: str, files) -> bool:
    """Each pattern of `files` matches a file (not empty) in `folder`."""
    if not os.path.isdir(folder):
        return False
    for pat in files:
        hits = [p for p in glob.glob(os.path.join(glob.escape(folder), *pat.split("/")))
                if os.path.isfile(p) and os.path.getsize(p) > 0]
        if not hits:
            return False
    return True


def hf_snapshot(repo: str, files=()) -> str | None:
    """The cached snapshot of `repo` that refs/main names, when it has every
    one of `files` (patterns), else None."""
    try:
        with open(os.path.join(repo_dir(repo), "refs", "main"), encoding="utf-8") as fh:
            sha = fh.read().strip()
    except OSError:
        return None
    snap = os.path.join(repo_dir(repo), "snapshots", sha)
    return snap if sha and _has_all(snap, files or ["*"]) else None


def path_of(item, models_dir: Callable[[str], str | None] | None = None) -> str | None:
    """Where an item lives: the snapshot folder (hf), the file (torch), the
    folder in a models folder (None: that models folder isn't known here)."""
    if item.folder == "hf":
        return os.path.join(repo_dir(item.name), "snapshots")
    if item.folder == "torch":
        return os.path.join(torch_hub_dir(), *item.name.split("/"))
    d = models_dir(item.folder) if models_dir else None
    return os.path.join(d, *in_folder(item).split("/")) if d else None


def in_folder(item) -> str:
    """Where a repo goes in its models folder: the item's `dir` when its pack
    reads it by another name, else the repo's own name."""
    return getattr(item, "dir", "") or item.name


def present(item, models_dir: Callable[[str], str | None] | None = None) -> bool | None:
    """Whether a hub item is there (None: can't tell: its models folder isn't
    known here)."""
    if item.folder == "hf":
        return hf_snapshot(item.name, item.files) is not None
    p = path_of(item, models_dir)
    if p is None:
        return None
    if item.folder == "torch":
        return os.path.isfile(p) and os.path.getsize(p) > 0
    return _has_all(p, item.files or ["*"])


def where_text(item) -> str:
    """Where it goes, as the window says it."""
    if item.folder == "hf":
        return "the Hugging Face cache"
    if item.folder == "torch":
        return "torch's hub cache"
    return f"models/{item.folder}/{in_folder(item)}"


# ---------------------------------------------------------------------------
# downloading
# ---------------------------------------------------------------------------

def is_hub(url: str) -> bool:
    """Whether `url` is Hugging Face's own (huggingface.co, hf.co, or a name under them): by its
    host, never by what the rest of the address says."""
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    return url.lower().startswith("https://") and any(
        host == h or host.endswith("." + h) for h in ("huggingface.co", "hf.co"))


def with_token(req: urllib.request.Request, token: str | None) -> urllib.request.Request:
    """`req` with the Hugging Face token, when it goes to Hugging Face, and on that request only:
    a redirect (the Hub's to its file servers, which need no token) never carries it on."""
    if token and is_hub(req.full_url):
        req.add_unredirected_header("Authorization", f"Bearer {token}")
    return req


def repo_listing(repo: str, token: str | None = None, opener=None) -> tuple[str, list[tuple[str, int | None]]]:
    """(the commit main names, [(file, size)]) from the Hub's API."""
    url = f"{HF}/api/models/{repo}/revision/main?blobs=true"
    req = with_token(urllib.request.Request(url, headers={"User-Agent": "seriesmith"}), token)
    if opener is not None:
        r = opener(req, timeout=60)
    else:
        from seriesmith.backends import tls
        r = urllib.request.urlopen(req, timeout=60, context=tls())
    with r:
        d = json.loads(r.read() or b"{}")
    sha = d.get("sha") or ""
    if not sha:
        raise ValueError(f"the Hub named no commit for {repo}")
    return sha, [(s["rfilename"], s.get("size")) for s in d.get("siblings") or []
                 if isinstance(s, dict) and s.get("rfilename")]


def fetch_repo(item, into: str | None, download, token: str | None = None,
               progress: Callable[[int, int | None], None] | None = None,
               cancelled: Callable[[], bool] = lambda: False, listing=repo_listing) -> str:
    """A repo's files (`item.files` and `item.extra`, patterns) downloaded:
    into Hugging Face's cache (`into` None: the snapshot of main's commit,
    then refs/main), or straight into the folder `into`. `download(url, dest,
    token, progress, cancelled)` is installer.download. Returns the folder.
    ValueError when the repo has no file for one of `item.files`."""
    sha, sibs = listing(item.name, token)
    pats = list(item.files) + list(item.extra)
    want = [(p, s) for p, s in sibs if any(fnmatch.fnmatch(p, pat) for pat in pats)]
    for pat in item.files:
        if not any(fnmatch.fnmatch(p, pat) for p, _ in want):
            raise ValueError(f"{item.name} has no {pat} (it may have changed: update seriesmith)")
    root = into or os.path.join(repo_dir(item.name), "snapshots", sha)
    sizes = [s for _, s in want]
    total = sum(sizes) if all(isinstance(s, int) for s in sizes) else None
    done = 0
    for path, size in want:
        dest = os.path.join(root, *path.split("/"))
        if os.path.isfile(dest) and (size is None or os.path.getsize(dest) == size):
            done += os.path.getsize(dest)
            continue
        url = f"{HF}/{item.name}/resolve/{sha}/{urllib.parse.quote(path)}"
        base = done
        download(url, dest, token,
                 (lambda d, _t, b=base: progress(b + d, total)) if progress else None, cancelled)
        done += os.path.getsize(dest)
    if into is None:
        F.write_text(os.path.join(repo_dir(item.name), "refs", "main"), sha)
    return root


# ---------------------------------------------------------------------------
# a job held back
# ---------------------------------------------------------------------------

def missing_message(item, feature: str = "") -> str:
    """What a job that needs a missing item says."""
    where = f" ({feature})" if feature else ""
    return (f"{item.name} isn't downloaded: download it in seriesmith's Features window{where}. "
            f"It isn't fetched by itself the first time the job runs.")


def loopback(url: str | None) -> bool:
    host = (urllib.parse.urlparse(url or "").hostname or "").lower()
    return host in ("127.0.0.1", "localhost", "::1")


def check_target(target, backend=None, models_dir=None) -> None:
    """RuntimeError when a file `target`'s node pack would fetch by itself
    (target.json `fetches`) isn't here: asked before its job goes to a
    ComfyUI on this machine (a backend elsewhere: its own cache, not this
    machine's, so nothing is said)."""
    if backend is not None and (getattr(backend, "kind", "") != "local"
                                or not loopback(getattr(backend, "base_url", ""))):
        return
    from seriesmith import features as FT
    items = FT.fetch_items(target)
    if not items:
        return
    if models_dir is None and any(i.folder not in PLACES for i in items):
        models_dir = local_models_dir(getattr(backend, "base_url", None))
    for i in items:
        if present(i, models_dir) is False:
            raise RuntimeError(missing_message(i, FT.feature_label_of(i)))


def local_models_dir(comfy_url: str | None = None) -> Callable[[str], str | None] | None:
    """models_dir(folder) for the ComfyUI on this machine (installer.Place):
    its own folder_paths inside ComfyUI, else asked of it, else the
    settings' comfyui_dir; None when it isn't known."""
    from seriesmith import installer as INS
    try:
        import folder_paths  # noqa: F401  inside ComfyUI
        place = INS.place_in_comfyui()
    except ImportError:
        from seriesmith import settings as S
        st = S.load_settings()
        place = INS.place_from_url(comfy_url or st.local_comfyui, st.comfyui_dir)
    return place.models_dir if place.root() else None


__all__ = ["HF", "PLACES", "check_target", "fetch_repo", "hf_cache_dir", "hf_snapshot",
           "in_folder", "local_models_dir", "loopback", "missing_message", "path_of", "present",
           "repo_dir", "repo_listing", "torch_hub_dir", "where_text"]
