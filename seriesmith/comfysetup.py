"""
comfysetup — for someone with no ComfyUI yet: the official ways to get one on this
computer's system (guide), and finding one that's running (find), so the Features window
can say what to do instead of only that there's none. seriesmith installs nothing here: the
choices are ComfyUI's own (docs.comfy.org, read 2026-11-04: v0.44.0, the repo
Comfy-Org/ComfyUI).

    guide(platform)   [{"id", "label", "for", "url", "steps": [...]}], best first
    find(urls)        {"found": the first that answers as a ComfyUI | None,
                       "tried": [{"url", "ok", "version"}]}

Stdlib only.
"""
from __future__ import annotations

import json
import threading
import urllib.request

RELEASES = "https://github.com/Comfy-Org/ComfyUI/releases/latest/download/"
DESKTOP = "https://comfy.org/download"
MANUAL = "https://docs.comfy.org/installation/manual_install"
CLI = "https://docs.comfy.org/comfy-cli/getting-started"
# where a ComfyUI usually answers: the portable build and a manual install on 8188;
# ComfyUI Desktop on a port of its own (8000 by default)
PORTS = (8188, 8000)
THEN = ("Then come back here and press Find my ComfyUI: seriesmith finds it, and its Features "
        "window can add seriesmith's node pack and the models you want.")


def _portable() -> dict:
    return {"id": "portable", "label": "Windows portable",
            "for": "An NVIDIA card, a folder you can move or delete: nothing installed in Windows.",
            "url": RELEASES + "ComfyUI_windows_portable_nvidia.7z",
            "steps": ["Download it (RTX cards; a GTX 10-series or older wants "
                      "ComfyUI_windows_portable_nvidia_cu126.7z, AMD _amd, Intel _intel, from the "
                      "same release).",
                      "Extract it with 7-Zip (7-zip.org) into a folder of your own, such as C:\\AI.",
                      "Double-click run_nvidia_gpu.bat in it (run_amd_gpu.bat, run_intel_gpu.bat). "
                      "Keep its window open: ComfyUI runs at http://127.0.0.1:8188.", THEN]}


def _desktop(system: str) -> dict:
    need = {"win": "Windows 10 or later", "mac": "an Apple Silicon Mac (M1 or later), macOS 13 or later",
            "linux": "Linux (an AppImage or a .deb)"}[system]
    return {"id": "desktop", "label": "ComfyUI Desktop",
            "for": f"The simplest: an app with an installer, for {need}.",
            "url": DESKTOP,
            "steps": ["Download it from comfy.org (it picks your system) and install it.",
                      "Open it and let it finish setting up. Its address is in its settings "
                      "(usually http://127.0.0.1:8000).", THEN]}


def _manual() -> dict:
    return {"id": "manual", "label": "By hand (git and Python)",
            "for": "Full control: your own Python environment, updated with git.",
            "url": MANUAL,
            "steps": ["git clone https://github.com/Comfy-Org/ComfyUI.git",
                      "In a Python 3.13 environment: the PyTorch for your card (the page has the "
                      "command), then pip install -r requirements.txt in the ComfyUI folder.",
                      "python main.py: ComfyUI runs at http://127.0.0.1:8188.", THEN]}


def _cli() -> dict:
    return {"id": "cli", "label": "comfy-cli",
            "for": "One command installs it, with the PyTorch for your card.",
            "url": CLI,
            "steps": ["In a Python 3.10+ environment: pip install comfy-cli",
                      "comfy install (it asks which card you have), then comfy launch: ComfyUI "
                      "runs at http://127.0.0.1:8188.", THEN]}


def guide(platform: str) -> list[dict]:
    """The ways to get ComfyUI on `platform` (sys.platform), best first."""
    if platform.startswith("win"):
        return [_desktop("win"), _portable(), _manual()]
    if platform == "darwin":
        return [_desktop("mac"), _cli(), _manual()]
    return [_cli(), _desktop("linux"), _manual()]


def candidates(configured: str | None) -> list[str]:
    """The addresses to try: the one in Settings first, then this computer's usual ports."""
    out = [configured.rstrip("/")] if configured else []
    for port in PORTS:
        u = f"http://127.0.0.1:{port}"
        if u not in out:
            out.append(u)
    return out


def _probe(url: str, timeout: float) -> dict:
    """A ComfyUI answers /system_stats with its version."""
    try:
        with urllib.request.urlopen(url + "/system_stats", timeout=timeout) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
        ver = ((d.get("system") or {}).get("comfyui_version")) if isinstance(d, dict) else None
        return {"url": url, "ok": isinstance(d, dict) and "system" in d, "version": ver}
    except (OSError, ValueError):
        return {"url": url, "ok": False, "version": None}


def find(urls: list[str], timeout: float = 3.0) -> dict:
    """Each address tried at once (a refused local port can take two seconds on Windows);
    the first in `urls` order that answers as a ComfyUI is found."""
    got: dict[str, dict] = {}

    def one(u: str) -> None:
        got[u] = _probe(u, timeout)
    threads = [threading.Thread(target=one, args=(u,), daemon=True) for u in urls]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout + 1)
    tried = [got.get(u) or {"url": u, "ok": False, "version": None} for u in urls]
    return {"found": next((t["url"] for t in tried if t["ok"]), None), "tried": tried}


__all__ = ["DESKTOP", "PORTS", "RELEASES", "candidates", "find", "guide"]
