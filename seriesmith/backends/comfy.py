"""
The ComfyUI backends: your own ComfyUI (through comfy-api-proxy), Comfy Cloud,
and a Comfy API deployment. All three speak the Comfy API v2, so one class
serves them; they differ only in base URL and key.

comfy-sdk reads its server from the COMFY_BASE_URL environment variable when a
client is built (it has no base-URL argument), so clients are built under a
lock with the variable set for each, and it is put back afterwards.
"""
from __future__ import annotations

import copy
import json
import os
import threading
import urllib.error
import urllib.request
from typing import Callable

from seriesmith.backends import (TERMINAL, Backend, BackendError, File, Output, Progress, Run,
                                 files_in, patiently)

_ENV_LOCK = threading.Lock()


def sdk_client(base_url: str, api_key: str | None, *, router_url: str | None = None):
    """A comfy_sdk.Comfy aimed at `base_url` (and Router at `router_url`, else
    the SDK's default). Without a key, none is sent: the user's
    COMFY_API_KEY is not passed to a local proxy by accident."""
    try:
        import comfy_sdk
    except ImportError:
        raise BackendError("comfy-sdk is not installed (pip install comfy-sdk)") from None
    with _ENV_LOCK:
        saved = {k: os.environ.get(k) for k in (comfy_sdk.BASE_URL_ENV_VAR,
                                                comfy_sdk.ROUTER_BASE_URL_ENV_VAR,
                                                comfy_sdk.API_KEY_ENV_VAR)}
        try:
            os.environ[comfy_sdk.BASE_URL_ENV_VAR] = base_url
            if router_url:
                os.environ[comfy_sdk.ROUTER_BASE_URL_ENV_VAR] = router_url
            os.environ.pop(comfy_sdk.API_KEY_ENV_VAR, None)
            return comfy_sdk.Comfy(api_key=api_key, timeout=60.0,
                                   client_info="seriesmith")
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


def health(base_url: str, api_key: str | None = None, timeout: float = 5.0) -> str | None:
    """None when `base_url` answers the v2 health check, else why not."""
    req = urllib.request.Request(base_url.rstrip("/") + "/api/v2/health")
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return f"{base_url} answered {e.code} {e.reason}"
    except (urllib.error.URLError, OSError) as e:
        reason = getattr(e, "reason", e)
        return f"{base_url} doesn't answer ({reason})"
    try:
        status = json.loads(body).get("status")
    except (ValueError, AttributeError):
        status = None
    return None if status in (None, "healthy", "ok") else f"{base_url} says {status!r}"


class ComfyRun(Run):
    def __init__(self, backend: str, job):
        self.backend = backend
        self._job = job
        self.id = job.id

    @property
    def status(self) -> str:
        return self._job.status

    def refresh(self) -> str:
        patiently(self._job.refresh)
        self._note_error()
        return self._job.status

    def _note_error(self) -> None:
        if self._job.status in TERMINAL and self._job.status != "succeeded":
            err = self._job.error
            self.error = (str(getattr(err, "message", None) or err) if err
                          else f"the job ended {self._job.status}")

    def watch(self, on_progress: Callable[[Progress], None] | None = None,
              on_status: Callable[[str], None] | None = None) -> str:
        import comfy_sdk
        last = [None]

        def status(s: str) -> None:
            if on_status and s != last[0]:
                last[0] = s
                on_status(s)
        try:
            for ev in self._job.events():
                if isinstance(ev, comfy_sdk.Progress) and on_progress:
                    on_progress(Progress(ev.value, ev.step, ev.steps, ev.current_node,
                                         ev.message))
                elif isinstance(ev, comfy_sdk.StatusChange):
                    status(ev.status)
        except Exception:                    # noqa: BLE001  events are best effort
            pass
        # polled to the end; a dropped connection (the proxy restarting, the
        # network) is waited out rather than failing a job that goes on
        while self._job.status not in TERMINAL:
            patiently(self._job.refresh)
            if self._job.status not in TERMINAL:
                import time
                time.sleep(2.0)
        self._note_error()
        status(self._job.status)
        return self._job.status

    def cancel(self) -> None:
        self._job.cancel()

    def outputs(self) -> list[Output]:
        return [Output(o.node_id, o.name, o.type, (lambda path, o=o: patiently(lambda: o.to_file(path))))
                for o in self._job.outputs]


class ComfyBackend(Backend):
    """A Comfy API v2 surface: `kind` is local, cloud or deployment."""

    def __init__(self, name: str, kind: str, base_url: str, api_key: str | None):
        self.name, self.kind = name, kind
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client = None

    def __repr__(self) -> str:
        return f"<ComfyBackend {self.name} {self.base_url}>"

    @property
    def client(self):
        if self._client is None:
            if self.kind != "local" and not self.api_key:
                raise BackendError(f"{self.name} needs a Comfy API key (COMFY_API_KEY)")
            self._client = sdk_client(self.base_url, self.api_key)
        return self._client

    def ping(self) -> str | None:
        return health(self.base_url, self.api_key)

    def submit(self, graph: dict) -> Run:
        """Upload the graph's File inputs (each once, by content) and submit."""
        g = copy.deepcopy(graph)
        assets = {}
        for container, key, f in list(files_in(g)):
            if f.path not in assets:
                assets[f.path] = self.client.assets.from_file(f.path)
            container[key] = assets[f.path]
        job = self.client.submit(self.client.workflows.from_json(g))
        return ComfyRun(self.name, job)

    def attach(self, run_id: str, model: str | None = None) -> Run:
        """A job this backend runs, by its id (client.jobs.get)."""
        return ComfyRun(self.name, patiently(lambda: self.client.jobs.get(run_id)))


__all__ = ["ComfyBackend", "ComfyRun", "File", "health", "sdk_client"]
