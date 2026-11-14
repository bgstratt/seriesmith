"""
downloads — what a target.json may ask the Features window to download.

A target's `downloads` and `fetches` are data: a shipped model's, but also one saved from
a workflow off the internet or sent to the API. So each record is checked here before
anything acts on it, and the installer checks again where it writes:

    url      https, on Hugging Face or Civitai (the hosts ComfyUI's own missing-models
             window downloads from), by the host's name and nothing else in the address
    folder   a models folder by name (`vae`, `ultralytics/bbox`): never a path, never
             custom_nodes, where a file would be code ComfyUI runs
    name     a model file (.safetensors, .sft, .gguf): weights, never a pickle or a script
    repo     a Hugging Face repo, `owner/name`
    files    patterns inside the repo, never one that climbs out of it

Stdlib only.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

MODEL_HOSTS = ("huggingface.co", "hf.co", "civitai.com")
MODEL_EXTS = (".safetensors", ".sft", ".gguf")
# folders of ComfyUI's that hold code or settings, not models
NOT_MODEL_FOLDERS = ("custom_nodes", "configs", "user", "input", "output", "temp")

_PART = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.+-]*\Z")
_REPO = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9_][A-Za-z0-9_.-]*\Z")
_SHA = re.compile(r"[0-9a-f]{40}\Z")


def _parts_ok(text, deep: int) -> bool:
    if not isinstance(text, str) or not text:
        return False
    parts = text.split("/")
    return len(parts) <= deep and all(_PART.match(p) and not p.endswith(".") for p in parts)


def host_ok(url) -> bool:
    """Whether a model may be downloaded from `url`: https, and the host is one of
    MODEL_HOSTS or a name under one."""
    if not isinstance(url, str):
        return False
    try:
        u = urlsplit(url)
        host = (u.hostname or "").lower()
    except ValueError:
        return False
    return u.scheme == "https" and not u.username and any(
        host == h or host.endswith("." + h) for h in MODEL_HOSTS)


def folder_problem(folder) -> str | None:
    """What's wrong with `folder` as a models folder's name (None: nothing)."""
    if not _parts_ok(folder, 3):
        return f"{folder!r} isn't a models folder's name"
    if folder.split("/")[0].lower() in NOT_MODEL_FOLDERS:
        return f"{folder} isn't a models folder"
    return None


def name_problem(name) -> str | None:
    """What's wrong with `name` as a model file's name (None: nothing)."""
    base = str(name or "").replace("\\", "/").rsplit("/", 1)[-1]
    if not _PART.match(base) or base.endswith("."):
        return f"{name!r} isn't a file name"
    if not base.lower().endswith(MODEL_EXTS):
        return f"{base} isn't a model file ({', '.join(MODEL_EXTS)})"
    return None


def download_problem(name, record: dict) -> str | None:
    """What's wrong with one `downloads` record that names a URL (None: nothing, or no
    URL: a file with no recorded download is only listed)."""
    url = record.get("url")
    if not url:
        return None
    return (name_problem(name) or folder_problem(record.get("folder"))
            or (None if host_ok(url) else
                "its URL isn't https on Hugging Face or Civitai, so it isn't downloaded"))


def pattern_ok(pattern) -> bool:
    """A file pattern inside a repo: relative, forward slashes, never `..`."""
    return (isinstance(pattern, str) and bool(pattern) and "\\" not in pattern and ":" not in pattern
            and not pattern.startswith("/") and ".." not in pattern.split("/"))


def fetch_problem(repo, record: dict) -> str | None:
    """What's wrong with one `fetches` record (None: nothing)."""
    if not isinstance(repo, str) or not _REPO.match(repo) or ".." in repo:
        return f"{repo!r} isn't a Hugging Face repo (owner/name)"
    into = record.get("into")
    if into not in ("hf", "torch"):
        why = folder_problem(into)
        if why:
            return why
    if record.get("dir") and not _parts_ok(record["dir"], 3):
        return f"{record['dir']!r} isn't a folder's name"
    for key in ("files", "extra"):
        got = record.get(key) or ()
        if not isinstance(got, (list, tuple)) or not all(pattern_ok(p) for p in got):
            return f"{repo}: `{key}` names a path outside the repo"
    return None


def repo_file_ok(path) -> bool:
    """A file's name as the Hub lists it, safe to join under the folder it goes in."""
    return pattern_ok(path) and all(p not in ("", ".") for p in path.split("/"))


def commit_ok(sha) -> bool:
    return isinstance(sha, str) and bool(_SHA.match(sha))


def spec_problems(spec: dict) -> list[str]:
    """Every problem in a target.json's `downloads` and `fetches`."""
    out = []
    for name, rec in (spec.get("downloads") or {}).items():
        if isinstance(rec, dict) and not str(name).startswith("_"):
            why = download_problem(name, rec)
            if why:
                out.append(f"downloads: {name}: {why}")
    for repo, rec in (spec.get("fetches") or {}).items():
        if isinstance(rec, dict) and not str(repo).startswith("_"):
            why = fetch_problem(repo, rec)
            if why:
                out.append(f"fetches: {why}")
    return out
