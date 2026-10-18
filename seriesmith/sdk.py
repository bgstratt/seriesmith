"""
sdk — comfy-sdk, put in when it's needed: Comfy Cloud, deployments, Router (and
local renders through comfy-api-proxy) use it; nothing else does. seriesmith's
own install brings it; ComfyUI's Python doesn't have it, so the editor inside
ComfyUI installs it there the first time a Comfy API key is set (Settings, or
COMFY_API_KEY at startup), in the background, and says how it went. Nobody
without a key gets anything installed, and SERIESMITH_NO_AUTO_INSTALL=1 turns
that off (the Install button still works).

    state()       {"status": "ready" | "missing" | "installing" | "failed",
                   "error", "command", "python"}
    ensure(s)     install it when settings `s` have a key and it's missing
    install()     install it now (the Settings window's Install)

Stdlib only.
"""
from __future__ import annotations

import importlib
import importlib.util
import logging
import os
import subprocess
import sys
import threading

# as pyproject.toml declares it
REQUIREMENT = "comfy-sdk>=0.4,<0.5"
log = logging.getLogger("seriesmith")

_LOCK = threading.Lock()
_STATE = {"status": None, "error": None}


def have() -> bool:
    return importlib.util.find_spec("comfy_sdk") is not None


def command() -> list[str]:
    """The install, as run: pip of the Python seriesmith runs on (inside
    ComfyUI, ComfyUI's own)."""
    return [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", REQUIREMENT]


def _describe() -> dict:
    """state(), with _LOCK held."""
    status = _STATE["status"]
    if status != "installing":
        status = "ready" if have() else ("failed" if status == "failed" else "missing")
    return {"status": status, "error": _STATE["error"] if status == "failed" else None,
            "command": subprocess.list2cmdline(command()), "python": sys.executable}


def state() -> dict:
    with _LOCK:
        return _describe()


def _run(cmd: list[str]) -> tuple[int, str]:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    return r.returncode, (r.stderr or r.stdout or "").strip()


def install(background: bool = True, run=None, on_done=None) -> dict:
    """pip install comfy-sdk into this Python (in a thread of its own unless
    `background` is False). `run(cmd) -> (returncode, output)` stands in for
    the subprocess (tests). Asking again while it runs does nothing. Returns
    state() as it is once started (or, not in the background, finished)."""
    with _LOCK:
        if _STATE["status"] == "installing":
            return _describe()
        if have():
            _STATE.update(status="ready", error=None)
            return _describe()
        _STATE.update(status="installing", error=None)

    def work():
        try:
            code, out = (run or _run)(command())
        except Exception as e:                            # noqa: BLE001  said in the state
            code, out = 1, f"{type(e).__name__}: {e}"
        importlib.invalidate_caches()
        with _LOCK:
            if code == 0 and have():
                _STATE.update(status="ready", error=None)
                log.info("seriesmith: comfy-sdk installed: Comfy Cloud and Router are ready")
            else:
                tail = "\n".join(out.splitlines()[-6:]) if out else f"pip exited {code}"
                _STATE.update(status="failed", error=tail[-800:])
                log.warning("seriesmith: installing comfy-sdk failed: %s", tail[-300:])
        if on_done:
            on_done(state())
    if background:
        threading.Thread(target=work, daemon=True, name="seriesmith-sdk").start()
        return state()
    work()
    return state()


def ensure(settings, run=None, on_done=None) -> dict:
    """When `settings` have a Comfy API key and comfy-sdk isn't here, install
    it in the background (once: a failed install waits for the Install button
    rather than trying on every save). Returns state()."""
    if not getattr(settings, "api_key", None) or have() or             os.environ.get("SERIESMITH_NO_AUTO_INSTALL") not in (None, "", "0"):
        return state()
    with _LOCK:
        failed = _STATE["status"] == "failed"
    return state() if failed else install(run=run, on_done=on_done)


def reset() -> None:
    """Forget what happened (tests)."""
    with _LOCK:
        _STATE.update(status=None, error=None)


__all__ = ["REQUIREMENT", "command", "ensure", "have", "install", "reset", "state"]
