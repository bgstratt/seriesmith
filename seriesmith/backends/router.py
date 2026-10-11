"""
The Router backend: a hosted model through Comfy Router.

A call is the model id ("provider/model") and the provider's own arguments.
Input files are uploaded to Comfy Cloud as assets and passed as URLs, the only
kind of input a provider can fetch, so Router needs a Comfy API key even when
nothing else runs in the cloud. The result is the provider's own JSON; every
http(s) URL in it is offered as an output.
"""
from __future__ import annotations

import copy
import os
import shutil
import urllib.parse
import urllib.request
from typing import Any, Callable, Iterable

from seriesmith.backends import Backend, BackendError, Output, Progress, Run, files_in, patiently, transient
from seriesmith.backends.comfy import sdk_client

COMPLETED = "COMPLETED"

_TYPES = {".mp4": "video", ".webm": "video", ".mov": "video", ".png": "image", ".jpg": "image",
          ".jpeg": "image", ".webp": "image", ".wav": "audio", ".mp3": "audio",
          ".flac": "audio", ".txt": "text", ".json": "text"}


def output_type(url: str) -> str:
    return _TYPES.get(os.path.splitext(urllib.parse.urlparse(url).path)[1].lower(), "file")


def urls_in(value: Any) -> Iterable[str]:
    """Every http(s) URL in a provider's result, in order, once each."""
    seen: set[str] = set()

    def walk(v):
        if isinstance(v, str):
            if v.startswith(("http://", "https://")) and v not in seen:
                seen.add(v)
                yield v
        elif isinstance(v, dict):
            for x in v.values():
                yield from walk(x)
        elif isinstance(v, list):
            for x in v:
                yield from walk(x)
    yield from walk(value)


def download(url: str, path: str, timeout: float = 300.0) -> None:
    with urllib.request.urlopen(url, timeout=timeout) as r, open(path, "wb") as fh:
        shutil.copyfileobj(r, fh)


class RouterRun(Run):
    def __init__(self, handle, model: str):
        self.backend = "router"
        self._handle = handle
        self.model = model
        self.id = handle.request_id
        self.status = "queued"
        self.result: Any = None

    def _settle(self) -> None:
        """Collect the result of a completed request (or its error). A dropped
        connection is asked again (backends.patiently): the provider has the
        result, and giving up here would lose a generation already billed."""
        try:
            self.result = patiently(self._handle.get)
            self.status = "succeeded"
        except Exception as e:                # noqa: BLE001  the router's typed errors
            self.status, self.error = "failed", f"{type(e).__name__}: {e}"

    def refresh(self) -> str:
        if self.status in ("succeeded", "failed", "canceled"):
            return self.status
        upd = patiently(self._handle.status)
        if upd.status == COMPLETED:
            self._settle()
        elif upd.status:
            self.status = "running" if upd.queue_position in (None, 0) else "queued"
        return self.status

    def watch(self, on_progress: Callable[[Progress], None] | None = None,
              on_status: Callable[[str], None] | None = None) -> str:
        if self.status not in ("succeeded", "failed", "canceled"):
            # the request runs on the provider whatever happens to this
            # connection: a poll that fails transiently is followed by asking
            # its status again (patiently), not by failing the run
            while True:
                try:
                    for upd in self._handle.iter_events():
                        if upd.status == COMPLETED:
                            break
                        self.status = "running" if upd.queue_position in (None, 0) else "queued"
                        if on_status:
                            on_status(self.status)
                    break
                except Exception as e:            # noqa: BLE001  sorted by transient()
                    if not transient(e):
                        raise
                    if patiently(self._handle.status).status == COMPLETED:
                        break
            self._settle()
        if on_status:
            on_status(self.status)
        return self.status

    def cancel(self) -> None:
        self._handle.cancel()
        self.status = "canceled"

    def outputs(self) -> list[Output]:
        if self.status != "succeeded":
            return []
        return [Output("", os.path.basename(urllib.parse.urlparse(u).path) or "output",
                       output_type(u), (lambda path, u=u: patiently(lambda: download(u, path))))
                for u in urls_in(self.result)]


class RouterBackend(Backend):
    name = kind = "router"

    def __init__(self, api_key: str, cloud_url: str):
        if not api_key:
            raise BackendError("router needs a Comfy API key (COMFY_API_KEY)")
        self.api_key = api_key
        self.cloud_url = cloud_url
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = sdk_client(self.cloud_url, self.api_key)
        return self._client

    def ping(self) -> str | None:
        # Router has no health check of its own; its inputs go through Cloud
        from seriesmith.backends.comfy import health
        return health(self.cloud_url, self.api_key)

    def call(self, model: str, arguments: dict) -> Run:
        args = copy.deepcopy(arguments)
        urls: dict[str, str] = {}
        for container, key, f in list(files_in(args)):
            if f.path not in urls:
                asset = self.client.assets.from_file(f.path)
                asset.commit()
                urls[f.path] = asset.get_download_url().url
            container[key] = urls[f.path]
        return RouterRun(self.client.models.submit(model, args), model)

    def attach(self, run_id: str, model: str | None = None) -> Run:
        """A request made through Router, by its model and request id
        (models.handle: no request of its own until it is asked)."""
        if not model:
            raise BackendError("a Router run is found by its model and request id: no model given")
        return RouterRun(self.client.models.handle(model, run_id), model)


__all__ = ["RouterBackend", "RouterRun", "download", "output_type", "urls_in"]
