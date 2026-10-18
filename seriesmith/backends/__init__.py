"""
backends — where a job runs (docs/DESIGN.md, "Backends").

Every job has the same lifecycle wherever it runs: its input files go up, it
is submitted, its progress is followed, and its outputs come back. A backend
is one place that can do that:

    local        your own ComfyUI, straight to its own API     ComfyUIBackend (native)
                 (or through comfy-api-proxy: local_via)       ComfyBackend
    cloud        Comfy Cloud                                   ComfyBackend
    deployment   a Comfy API deployment of one workflow        ComfyBackend
    router       a hosted model through Comfy Router           RouterBackend

A ComfyUI backend runs an API-format workflow (`submit`); Router calls a model
with arguments (`call`). Either way the result is a `Run`: its status, its
progress, cancel, and its outputs, each of which can be saved to a file.

Input files are marked where they are used, with `File(path)`: in a graph's
node inputs, or anywhere in a Router call's arguments. The backend uploads each
and puts what that backend expects in its place (the filename a LoadImage node
reads; a URL a provider can fetch).

This module and `settings` need nothing outside the standard library; the
Comfy API and Router backends import comfy-sdk when they are built (the
native local one doesn't need it).
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from seriesmith.targets import BACKENDS

TERMINAL = ("succeeded", "failed", "canceled", "expired")


class BackendError(RuntimeError):
    """A backend that isn't configured, can't be reached, or refused a job."""


# How long a run's backend may stay out of reach before the run is given up
# on: a dropped connection, a restarting proxy, a 5xx. The job itself goes on
# where it runs; this is only how long we keep asking about it.
PATIENCE = 15 * 60.0


_TLS = None


def tls():
    """The TLS context seriesmith's own https calls use (the health check,
    downloads, the Seedance library, Router schemas): certifi's CA list when
    it's there -- comfy-sdk's (httpx's) list, so both see the same web --
    else the system's. On Windows the system store can hold an expired copy
    of a Let's Encrypt cross-signed root that OpenSSL picks over the valid
    one: cloud.comfy.org then reads "certificate has expired" to Python while
    curl and comfy-sdk reach it (2026-10-12)."""
    global _TLS
    if _TLS is None:
        import ssl
        try:
            import certifi
            _TLS = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            _TLS = ssl.create_default_context()
    return _TLS


def transient(exc: BaseException) -> bool:
    """Whether `exc` is the network or the service hiccupping (worth asking
    again) rather than an answer (a 4xx: not found, unauthorized, no credits).
    comfy-sdk's errors carry the HTTP status they came with, None when no
    response came at all."""
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True
    # a Router request that finished with an error (InvalidInput, a content
    # refusal...) carries its `error_type` and no HTTP status: that is the
    # provider's answer, final, not a dropped connection -- asking again
    # only kept a failed run "running" for PATIENCE (Seedance, 2026-10-11)
    if getattr(exc, "error_type", "") and getattr(exc, "http_status", None) is None:
        return False
    status = getattr(exc, "http_status", "absent")
    if status != "absent":
        return status is None or status == 429 or (isinstance(status, int) and status >= 500)
    name = type(exc).__name__
    mod = type(exc).__module__ or ""
    # httpx's transport errors (ConnectError, ReadTimeout, RemoteProtocolError...)
    if mod.startswith(("httpx", "httpcore")):
        return True
    return isinstance(exc, OSError) and name not in ("FileNotFoundError", "PermissionError")


def patiently(fn: Callable[[], Any], window: float | None = None,
              on_wait: Callable[[str], None] | None = None,
              sleep: Callable[[float], None] | None = None) -> Any:
    """fn(), asked again while it fails transiently (backoff to 30 s), for up
    to `window` seconds (PATIENCE) in all; then, or on any other error, that
    error is raised. `on_wait(why)` hears of each wait."""
    window = PATIENCE if window is None else window
    end = time.monotonic() + window
    delay = 2.0
    while True:
        try:
            return fn()
        except Exception as e:                           # noqa: BLE001  sorted below
            if not transient(e) or time.monotonic() + delay > end:
                raise
            if on_wait:
                on_wait(f"{type(e).__name__}: {e}"[:200])
            (sleep or time.sleep)(delay)
            delay = min(delay * 2, 30.0)


@dataclass(frozen=True)
class File:
    """A local file a job needs, uploaded by the backend that runs it.
    `via` names a provider's own way in, when a plain URL won't do
    ("seedance": registered in the Seedance virtual library, sent as
    asset://<id>, as ComfyUI's own Seedance nodes do: BytePlus refuses
    pictures of photoreal people any other way; "base64": the file's bytes
    themselves, not uploaded -- Veo's gcsUri takes Google Cloud Storage only;
    "datauri": the same as a data: URI, for a field that takes a URL or one)."""
    path: str
    via: str = ""

    def __post_init__(self):
        if not os.path.isfile(self.path):
            raise BackendError(f"input file not found: {self.path}")


@dataclass
class Progress:
    """How far a run has got: `value` 0-1, and the sampler's step when known."""
    value: float
    step: int | None = None
    steps: int | None = None
    node: str | None = None
    message: str | None = None


@dataclass
class Output:
    """One file a run produced: the node that saved it (or "" for a hosted
    model), its file name, its type (image, video, audio, text, file, latent)
    and how to fetch it."""
    node: str
    name: str
    type: str
    fetch: Callable[[str], None] = field(repr=False)

    def save(self, path: str) -> str:
        """Write the output to `path` (folders made as needed); returns it."""
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.fetch(path)
        return path


class Run:
    """One submitted job. Subclasses fill in the backend's calls."""

    id: str = ""
    backend: str = ""
    error: str | None = None
    # what the backend changed to run it (a node it hasn't, spliced out), for
    # the job's log
    notes: tuple = ()

    def refresh(self) -> str:
        """The run's status now (queued, running, or one of TERMINAL)."""
        raise NotImplementedError

    def watch(self, on_progress: Callable[[Progress], None] | None = None,
              on_status: Callable[[str], None] | None = None) -> str:
        """Follow the run to its end, calling back as it goes; returns the
        final status. Live events are best effort; the final status comes
        from asking the backend."""
        raise NotImplementedError

    def cancel(self) -> None:
        raise NotImplementedError

    def outputs(self) -> list[Output]:
        """What the run produced (empty until it succeeds)."""
        raise NotImplementedError


class Backend:
    """One place jobs can run. `name` is how settings and the queue refer to
    it ("local", "cloud", "router", "deployment:<id>"); `kind` is one of
    targets.BACKENDS, what a target's capabilities name."""

    name: str = ""
    kind: str = ""

    def ping(self) -> str | None:
        """None when the backend answers, else why it doesn't."""
        raise NotImplementedError

    def submit(self, graph: dict) -> Run:
        """Run an API-format ComfyUI workflow. Inputs given as File are
        uploaded first."""
        raise BackendError(f"{self.name} runs hosted models, not workflows")

    def call(self, model: str, arguments: dict) -> Run:
        """Call a hosted model with the provider's own arguments. Inputs given
        as File are uploaded first."""
        raise BackendError(f"{self.name} runs workflows, not hosted models")

    def attach(self, run_id: str, model: str | None = None) -> Run:
        """The run `run_id` (a hosted call's also needs its `model`), started
        by this backend in this process or an earlier one: a job that was
        running when the server stopped is followed and collected again."""
        raise BackendError(f"{self.name} can't look up a run")

    @property
    def paid(self) -> bool:
        """Whether a run here is billed (Comfy Cloud, Router, a deployment)."""
        return self.kind != "local"


def files_in(value: Any) -> Iterable[tuple[Any, Any, File]]:
    """(container, key, File) for every File inside `value` (dicts and lists),
    so a backend can replace each in place."""
    if isinstance(value, dict):
        items = value.items()
    elif isinstance(value, list):
        items = enumerate(value)
    else:
        return
    for k, v in list(items):
        if isinstance(v, File):
            yield value, k, v
        else:
            yield from files_in(v)


def available(settings=None) -> dict[str, Backend]:
    """Every backend the settings configure, by name. Building one checks
    nothing over the network; `ping` does."""
    from seriesmith.settings import load_settings
    s = settings or load_settings()
    out: dict[str, Backend] = {}
    from seriesmith.backends.comfy import ComfyBackend
    if s.local_via == "proxy":
        out["local"] = ComfyBackend("local", "local", s.local_url, None)
    else:
        from seriesmith.backends.native import ComfyUIBackend
        out["local"] = ComfyUIBackend("local", s.local_comfyui)
    if s.api_key:
        out["cloud"] = ComfyBackend("cloud", "cloud", s.cloud_url, s.api_key)
        from seriesmith.backends.router import RouterBackend
        out["router"] = RouterBackend(s.api_key, s.cloud_url)
    for target_id, url in sorted(s.deployments.items()):
        out[f"deployment:{target_id}"] = ComfyBackend(f"deployment:{target_id}", "deployment",
                                                      url, s.api_key)
    return out


__all__ = ["BACKENDS", "TERMINAL", "Backend", "BackendError", "File", "Output", "Progress",
           "Run", "available", "files_in"]
