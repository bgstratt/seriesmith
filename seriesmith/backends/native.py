"""
The local backend straight to ComfyUI: its own API (/prompt, /history,
/queue, /view, /upload/image, /ws), so nothing sits between seriesmith and
your ComfyUI -- no comfy-api-proxy, no comfy-sdk. Status and outputs are read
as comfy-api-proxy reads them (its job states and output kinds), so a run
here looks to the runner exactly like one through the proxy.

Input files go up once each (named by their content) to ComfyUI's
input/seriesmith/, and the graph names them there, as a LoadImage widget does.
A node a target can do without (binding `bypass_if_missing`: H3's sparse
attention, from a third-party pack) is spliced out when this ComfyUI hasn't
it, and the run says so (`notes`).

Stdlib, plus aiohttp (a declared dependency, and in every ComfyUI) for the
live progress over /ws; without it a run is followed by polling alone.
"""
from __future__ import annotations

import copy
import json
import os
import time
import uuid
from typing import Callable

from seriesmith.backends import (TERMINAL, Backend, BackendError, File, Output, Progress, Run,
                                 files_in, patiently)
from seriesmith.core import fileio as F

# ComfyUI's ui output key -> the output's type (comfy-api-proxy's _OUTPUT_KIND)
OUTPUT_KIND = {"images": "image", "gifs": "video", "audio": "audio", "text": "text",
               "files": "file", "latents": "latent"}

UPLOAD_FOLDER = "seriesmith"


def _client(base_url: str, client_id: str):
    from seriesmith.jobs import Comfy
    return Comfy(base_url, client_id=client_id)


def _upstream(e: BaseException) -> Exception:
    """ComfyUI's HTTP errors come from jobs.Comfy as RuntimeError; a 5xx is
    worth asking again (patiently), a 4xx is its answer."""
    msg = str(e)
    if msg.startswith("ComfyUI 5"):
        return ConnectionError(msg)
    return e


def status_of(entry: dict | None, running: set, pending: set, pid: str) -> str:
    """A prompt's status from its /history entry and one /queue snapshot, as
    comfy-api-proxy decides it; "unknown" when ComfyUI has no trace of it."""
    if entry is not None:
        st = entry.get("status") or {}
        messages = st.get("messages") or []
        if any(isinstance(m, (list, tuple)) and m and m[0] == "execution_interrupted"
               for m in messages):
            return "canceled"
        return "succeeded" if st.get("status_str", "success") == "success" else "failed"
    if pid in running:
        return "running"
    if pid in pending:
        return "queued"
    return "unknown"


def error_of(entry: dict | None) -> str:
    """What failed, from a failed prompt's history messages."""
    for m in ((entry or {}).get("status") or {}).get("messages") or []:
        if isinstance(m, (list, tuple)) and len(m) == 2 and m[0] == "execution_error":
            d = m[1] if isinstance(m[1], dict) else {}
            where = d.get("node_type") or ""
            if d.get("node_id"):
                where = f"{where} (node {d['node_id']})" if where else f"node {d['node_id']}"
            text = (d.get("exception_message") or "").strip() or "execution failed"
            return f"{where}: {text}" if where else text
    return "execution failed"


def outputs_of(entry: dict | None) -> list[tuple[str, str, str, dict]]:
    """(node, filename, type, the /view reference) for every file a prompt's
    nodes reported."""
    out = []
    for node, node_out in ((entry or {}).get("outputs") or {}).items():
        if not isinstance(node_out, dict):
            continue
        for key, items in node_out.items():
            kind = OUTPUT_KIND.get(key)
            if not kind or not isinstance(items, list):
                continue
            for it in items:
                if isinstance(it, dict) and it.get("filename"):
                    out.append((str(node), it["filename"], kind,
                                {"filename": it["filename"], "subfolder": it.get("subfolder", ""),
                                 "type": it.get("type", "output")}))
    return out


def node_errors_text(body: str) -> str:
    """ComfyUI's refusal of a graph (POST /prompt 400), as one readable line."""
    try:
        got = json.loads(body[body.index("{"):])
    except ValueError:
        return body[:600]
    parts = []
    err = got.get("error") or {}
    if isinstance(err, dict) and err.get("message"):
        parts.append(err["message"] + (f" ({err['details']})" if err.get("details") else ""))
    for nid, ne in (got.get("node_errors") or {}).items():
        for e in (ne or {}).get("errors") or []:
            parts.append(f"{ne.get('class_type', '?')} (node {nid}): {e.get('message', '')}"
                         + (f" -- {e['details']}" if e.get("details") else ""))
    return "; ".join(parts)[:1500] or body[:600]


class NativeRun(Run):
    def __init__(self, backend: str, base_url: str, pid: str, client_id: str):
        self.backend = backend
        self.id = pid
        self._base = base_url
        self._client_id = client_id
        self._comfy = _client(base_url, client_id)
        self._entry: dict | None = None
        self._status = "queued"
        self.notes: list[str] = []

    @property
    def status(self) -> str:
        return self._status

    def _ask(self) -> str:
        try:
            entry = self._comfy.history(self.id)
            running, pending = (set(), set()) if entry is not None else self._comfy.queue_ids()
        except RuntimeError as e:
            raise _upstream(e) from None
        s = status_of(entry, running, pending, self.id)
        if s == "unknown":
            # gone from ComfyUI (restarted, its history cleared): over. A
            # prompt is in the queue as soon as POST /prompt answers, so this
            # never catches one just submitted
            s = "expired"
        self._entry = entry
        self._status = s
        if s in TERMINAL and s != "succeeded":
            self.error = (error_of(entry) if s == "failed" else
                          "the job was canceled in ComfyUI" if s == "canceled" else
                          "ComfyUI no longer knows this job (restarted?)")
        return s

    def refresh(self) -> str:
        return patiently(self._ask)

    def watch(self, on_progress: Callable[[Progress], None] | None = None,
              on_status: Callable[[str], None] | None = None) -> str:
        last = [None]

        def status(s: str) -> None:
            if on_status and s != last[0]:
                last[0] = s
                on_status(s)
        try:
            self._follow_ws(on_progress, status)
        except Exception:                    # noqa: BLE001  live events are best effort
            pass
        while self.refresh() not in TERMINAL:
            status(self._status)
            time.sleep(2.0)
        status(self._status)
        return self._status

    def _follow_ws(self, on_progress, status) -> None:
        """ComfyUI's live events for this prompt until it finishes, from /ws
        (a client id of our own, so ComfyUI sends the progress to us)."""
        import asyncio

        import aiohttp
        if self.refresh() in TERMINAL:
            return
        ws_url = self._base.replace("http://", "ws://", 1).replace("https://", "wss://", 1)
        ws_url += f"/ws?clientId={self._client_id}"
        pid = self.id

        async def follow():
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(ws_url, heartbeat=30) as ws:
                    # it may have ended between submit and connect
                    if await asyncio.to_thread(self.refresh) in TERMINAL:
                        return
                    status(self._status)
                    while True:
                        try:
                            msg = await ws.receive(timeout=20)
                        except asyncio.TimeoutError:
                            if await asyncio.to_thread(self.refresh) in TERMINAL:
                                return
                            status(self._status)
                            continue
                        if msg.type != aiohttp.WSMsgType.TEXT:
                            if msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR,
                                            aiohttp.WSMsgType.CLOSE):
                                return
                            continue          # previews (binary)
                        try:
                            ev = json.loads(msg.data)
                        except ValueError:
                            continue
                        kind, data = ev.get("type"), ev.get("data") or {}
                        if data.get("prompt_id") not in (None, pid):
                            continue
                        if kind == "execution_start" and data.get("prompt_id") == pid:
                            status("running")
                        elif kind == "progress" and on_progress and data.get("prompt_id") == pid:
                            step, steps = data.get("value"), data.get("max")
                            value = (step / steps) if isinstance(step, (int, float)) and steps else 0.0
                            on_progress(Progress(float(value), step, steps,
                                                 str(data.get("node") or "") or None))
                        elif kind == "executing" and data.get("prompt_id") == pid:
                            if data.get("node") is None:
                                return        # the prompt is done
                            if on_progress:
                                on_progress(Progress(0.0, None, None, str(data["node"])))
                        elif kind in ("execution_success", "execution_error",
                                      "execution_interrupted") and data.get("prompt_id") == pid:
                            return
        asyncio.run(follow())

    def cancel(self) -> None:
        try:
            running, pending = self._comfy.queue_ids()
        except RuntimeError:
            running, pending = set(), set()
        if self.id in pending:
            self._comfy.delete_queued([self.id])
        else:
            self._comfy.interrupt(self.id)

    def outputs(self) -> list[Output]:
        if self._entry is None:
            self.refresh()
        comfy = self._comfy

        def fetcher(ref):
            def fetch(path: str) -> None:
                data = patiently(lambda: comfy.view(ref))
                F.write_bytes(path, data)
            return fetch
        return [Output(node, name, kind, fetcher(ref))
                for node, name, kind, ref in outputs_of(self._entry)]


def upload_name(path: str) -> str:
    """Where an input file goes in ComfyUI's input folder: named by its
    content, so the same file is sent once and two files never clash."""
    ext = os.path.splitext(path)[1].lower()
    return f"{UPLOAD_FOLDER}/{F.file_digest(path)[:20]}{ext}"


class ComfyUIBackend(Backend):
    """Your own ComfyUI, through its own API (kind "local")."""

    def __init__(self, name: str, base_url: str, kind: str = "local"):
        self.name, self.kind = name, kind
        self.base_url = base_url.rstrip("/")
        self.api_key = None
        self.client_id = f"seriesmith-{uuid.uuid4().hex[:12]}"
        self._has: dict[str, tuple[bool, float]] = {}

    def has_node(self, ctype: str) -> bool:
        """Whether this ComfyUI knows `ctype` (asked once a minute at most;
        True when it can't be asked: the job then says for itself)."""
        known = self._has.get(ctype)
        if known and time.monotonic() - known[1] < 60:
            return known[0]
        try:
            ok = _client(self.base_url, self.client_id).has_node(ctype)
        except (RuntimeError, OSError, ValueError):
            return True
        self._has[ctype] = (ok, time.monotonic())
        return ok

    def without_missing(self, g: dict) -> list[str]:
        """The nodes in `g` a target can do without that this ComfyUI hasn't,
        spliced out (jobs.bypass_nodes); a note for each class."""
        from seriesmith.jobs import bypass_nodes
        from seriesmith.targets import bypassable
        can = bypassable()
        present = {v.get("class_type") for v in g.values() if isinstance(v, dict)}
        gone = {c: via for c, via in can.items() if c in present and not self.has_node(c)}
        return [f"{c} isn't in this ComfyUI: rendered without it (INSTALL.md, optional node packs)"
                for c in bypass_nodes(g, gone)] if gone else []

    def __repr__(self) -> str:
        return f"<ComfyUIBackend {self.name} {self.base_url}>"

    def ping(self) -> str | None:
        try:
            _client(self.base_url, self.client_id).ping()
        except RuntimeError as e:
            return f"{self.base_url} answered: {str(e)[:200]}"
        except OSError as e:
            return f"{self.base_url} doesn't answer ({getattr(e, 'reason', e)})"
        return None

    def submit(self, graph: dict) -> Run:
        """Upload the graph's File inputs (each once, by content) and queue it."""
        comfy = _client(self.base_url, self.client_id)
        g = copy.deepcopy(graph)
        notes = self.without_missing(g)
        sent: dict[str, str] = {}
        for container, key, f in list(files_in(g)):
            if f.path not in sent:
                name = upload_name(f.path)
                try:
                    sent[f.path] = patiently(lambda: comfy.upload_input(f.path, name), window=120)
                except RuntimeError as e:
                    raise BackendError(f"ComfyUI didn't take {os.path.basename(f.path)}: {e}") from None
            container[key] = sent[f.path]
        try:
            got = comfy._json("/prompt", {"prompt": g, "client_id": self.client_id})
        except RuntimeError as e:
            raise BackendError(f"ComfyUI refused the job: {node_errors_text(str(e))}") from None
        except OSError as e:
            raise BackendError(f"{self.base_url} doesn't answer ({getattr(e, 'reason', e)})") from None
        if got.get("node_errors"):
            raise BackendError("ComfyUI refused the job: "
                               + node_errors_text(json.dumps(got)))
        run = NativeRun(self.name, self.base_url, got["prompt_id"], self.client_id)
        run.notes = notes
        return run

    def attach(self, run_id: str, model: str | None = None) -> Run:
        return NativeRun(self.name, self.base_url, run_id, self.client_id)


__all__ = ["ComfyUIBackend", "NativeRun", "OUTPUT_KIND", "error_of", "outputs_of", "status_of",
           "upload_name"]
