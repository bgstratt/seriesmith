"""
sdk — whether comfy-sdk is here: Comfy Cloud, deployments, Router (and local
renders through comfy-api-proxy) use it; nothing else does. seriesmith's own
install brings it, and so does ComfyUI-Manager's (requirements.txt). A node
pack linked from a clone into a ComfyUI whose Python lacks it gets the command
that puts it there, never an install of seriesmith's own: the Comfy Registry's
rules let no node pack install Python packages at runtime.

    have()        comfy-sdk importable in this Python
    state()       {"status": "ready" | "missing", "command", "python"}
    command()     the pip install that puts it in this Python

Stdlib only.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys

# as pyproject.toml and requirements.txt declare it
REQUIREMENT = "comfy-sdk>=0.4,<0.5"


def have() -> bool:
    return importlib.util.find_spec("comfy_sdk") is not None


def command() -> list[str]:
    """The install, for you to run: pip of the Python seriesmith runs on
    (inside ComfyUI, ComfyUI's own)."""
    return [sys.executable, "-m", "pip", "install", REQUIREMENT]


def state() -> dict:
    return {"status": "ready" if have() else "missing",
            "command": subprocess.list2cmdline(command()), "python": sys.executable}


__all__ = ["REQUIREMENT", "command", "have", "state"]
