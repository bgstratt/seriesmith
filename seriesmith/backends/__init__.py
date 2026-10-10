"""
backends — where a job runs (docs/DESIGN.md, "Backends").

Every job has the same lifecycle wherever it runs: its input files go up, it
is submitted, its progress is followed, and its outputs come back. A backend
is one place that can do that:

    local        your own ComfyUI, through comfy-api-proxy     ComfyBackend
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
ComfyUI and Router backends import comfy-sdk when they are built.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from seriesmith.targets import BACKENDS

TERMINAL = ("succeeded", "failed", "canceled", "expired")


class BackendError(RuntimeError):
    """A backend that isn't configured, can't be reached, or refused a job."""


@dataclass(frozen=True)
class File:
    """A local file a job needs, uploaded by the backend that runs it."""
    path: str

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
    out["local"] = ComfyBackend("local", "local", s.local_url, None)
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
