"""
The Router backend: a hosted model through Comfy Router.

A call is the model id ("provider/model") and the provider's own arguments.
Input files are uploaded to Comfy Cloud as assets and passed as URLs, the only
kind of input a provider can fetch, so Router needs a Comfy API key even when
nothing else runs in the cloud. A file marked `via="seedance"` goes one step
further, into the Seedance virtual library (seedance_asset): BytePlus refuses a
picture of a photoreal person -- an AI-made one too -- as a plain URL
(content_policy_violation), and takes it as asset://<id>. The result is the
provider's own JSON; every http(s) URL in it is offered as an output.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import time
import shutil
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Iterable

from seriesmith.backends import Backend, BackendError, Output, Progress, Run, files_in, patiently, tls, transient
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


def inline_in(value: Any) -> Iterable[tuple[str, str]]:
    """(base64 data, mime type) of every file a provider's result carries
    inline, in order: Veo returns its video as {"bytesBase64Encoded",
    "mimeType"}, GPT Image its pictures as {"b64_json"}, Gemini as
    {"inlineData": {"mimeType", "data"}} -- not links."""
    if isinstance(value, dict):
        data = value.get("bytesBase64Encoded")
        if isinstance(data, str) and data:
            yield data, str(value.get("mimeType") or "video/mp4")
            return
        data = value.get("b64_json")
        if isinstance(data, str) and data:
            yield data, "image/" + str(value.get("output_format") or "png")
            return
        inline = value.get("inlineData") or value.get("inline_data")
        if isinstance(inline, dict) and isinstance(inline.get("data"), str) and inline["data"]:
            yield inline["data"], str(inline.get("mimeType") or inline.get("mime_type") or "image/png")
            return
        for x in value.values():
            yield from inline_in(x)
    elif isinstance(value, list):
        for x in value:
            yield from inline_in(x)


def _write_b64(data: str, path: str) -> None:
    with open(path, "wb") as fh:
        fh.write(base64.b64decode(data))


def download(url: str, path: str, timeout: float = 300.0) -> None:
    with urllib.request.urlopen(url, timeout=timeout, context=tls()) as r, open(path, "wb") as fh:
        shutil.copyfileobj(r, fh)


class RouterRun(Run):
    def __init__(self, handle, model: str):
        self.backend = "router"
        self._handle = handle
        self.model = model
        self.id = handle.request_id
        self.status = "queued"
        self.result: Any = None
        # another provider asked for, and the one Router says served it
        self.provider: str | None = None
        self.served_by: str | None = None

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
        out = [Output("", os.path.basename(urllib.parse.urlparse(u).path) or "output",
                      output_type(u), (lambda path, u=u: patiently(lambda: download(u, path))))
               for u in urls_in(self.result)]
        # a file the result carries itself (Veo: {"bytesBase64Encoded", "mimeType"})
        for i, (data, mime) in enumerate(inline_in(self.result)):
            kind = mime.split("/")[0] if mime.split("/")[0] in ("video", "image", "audio") else "file"
            ext = {"video": ".mp4", "image": ".png", "audio": ".wav"}.get(kind, ".bin")
            out.append(Output("", f"output_{i}{ext}", kind, (lambda path, d=data: _write_b64(d, path))))
        return out


API_BASE = "https://api.comfy.org"
# the key a call's arguments carry how Router is to serve it ({"provider",
# "fallback"}), taken off before the request is sent
ROUTING = "__router"
VIRTUAL_LIBRARY = "/proxy/seedance/virtual-library/assets"
ASSET = "/proxy/seedance/assets/{id}"


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
        # how Router serves it (router_video puts it here): another provider of
        # the model, and whether Router may fall back to one
        how = args.pop(ROUTING, None) or {}
        urls: dict[tuple, str] = {}
        for container, key, f in list(files_in(args)):
            k = (f.path, f.via)
            if k not in urls and f.via in ("base64", "datauri"):
                with open(f.path, "rb") as fh:
                    b64 = base64.b64encode(fh.read()).decode("ascii")
                mime = "image/jpeg" if f.path.lower().endswith((".jpg", ".jpeg")) else "image/png"
                urls[k] = b64 if f.via == "base64" else f"data:{mime};base64,{b64}"
            elif k not in urls:
                asset = self.client.assets.from_file(f.path)
                asset.commit()
                url = asset.get_download_url().url
                urls[k] = self.seedance_asset(f.path, url) if f.via == "seedance" else url
            container[key] = urls[k]
        provider, fallback = how.get("provider") or None, how.get("fallback")
        if provider is None and fallback is None:
            return RouterRun(self.client.models.submit(model, args), model)
        handle, served = self._submit(model, args, provider, fallback)
        run = RouterRun(handle, model)
        run.provider, run.served_by = provider, served
        return run

    def _submit(self, model: str, args: dict, provider: str | None, fallback):
        """models.submit with Router's alt-provider query (model_provider,
        fallback_provider), which comfy-sdk 0.4 sends on models.run only: the
        same queued request, built with its own helpers. (handle, the provider
        that served it when Router says)."""
        from comfy_low.transport import _router_run_query, model_submit_request
        from comfy_sdk._core import new_idempotency_key
        from comfy_sdk.exceptions import translating
        from comfy_sdk.model_requests import RequestHandle, _request_id_of
        models = self.client.models
        low = models._low
        key = new_idempotency_key()
        path, body, headers = model_submit_request(model, args, key)
        query = _router_run_query(provider, None, fallback)
        if query:
            path = f"{path}?{query}"
        with translating(idempotency_key=key):
            resp = low.raw_request("POST", low._p.router_base_url + path, headers=headers, json=body)
            out = low._p.parse_or_raise(resp, (200, 201, 202))
        served = resp.headers.get("X-Comfy-Router-Fallback-Provider") or provider
        return RequestHandle(low, model, _request_id_of(out), models._retry), served

    def _api(self, method: str, path: str, body: dict | None = None) -> dict:
        req = urllib.request.Request(
            API_BASE + path, method=method,
            data=json.dumps(body).encode("utf-8") if body is not None else None,
            headers={"X-API-KEY": self.api_key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60, context=tls()) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            raise BackendError(f"{method} {path}: {e.code} {e.read().decode('utf-8', 'replace')[:300]}")

    def seedance_asset(self, path: str, url: str, wait: float = 600.0) -> str:
        """`path` (uploaded, at `url`) in this account's Seedance virtual
        library, once it's Active: "asset://<id>". The library de-duplicates
        by the hash (the file's sha256), so a picture is registered once."""
        with open(path, "rb") as fh:
            digest = hashlib.sha256(fh.read()).hexdigest()
        made = patiently(lambda: self._api("POST", VIRTUAL_LIBRARY, {"url": url, "hash": digest}))
        aid = made.get("asset_id")
        if not aid:
            raise BackendError(f"the Seedance library gave no asset id for {os.path.basename(path)}: {made}")
        end = time.monotonic() + wait
        while True:
            got = patiently(lambda: self._api("GET", ASSET.format(id=aid)))
            status = got.get("status")
            if status == "Active":
                return f"asset://{aid}"
            if status == "Failed" or time.monotonic() > end:
                raise BackendError(f"the Seedance library didn't take {os.path.basename(path)} "
                                   f"({status}): {got.get('error')}")
            time.sleep(3)

    def attach(self, run_id: str, model: str | None = None) -> Run:
        """A request made through Router, by its model and request id
        (models.handle: no request of its own until it is asked)."""
        if not model:
            raise BackendError("a Router run is found by its model and request id: no model given")
        return RouterRun(self.client.models.handle(model, run_id), model)


__all__ = ["RouterBackend", "RouterRun", "download", "output_type", "urls_in"]
