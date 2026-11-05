"""
A hosted model on a provider of the user's own, run from its definition (seriesmith/providers.py):
a list of steps, each an HTTP request, the values taken from its answer, and optionally a status to
wait for. Asking the same of every provider is the point; what differs is data.

What the steps can't be careless about, and so isn't data:

- The key goes only to the provider's own hosts, and a redirect elsewhere drops it. A file's link
  gets no key unless the definition says that link needs it.
- A request that may have started a job isn't sent twice: a timeout on it says it may have been
  charged. Only waiting and fetching are asked again.
- A run's id holds what it needs to be followed after a restart (a provider's task id), never the
  key, and never the arguments.

Stdlib only.
"""
from __future__ import annotations

import copy
import json
import mimetypes
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Callable

from seriesmith.backends import (Backend, BackendError, File, HTTPFailure, Output, Progress, Run,
                                 files_in, patiently, tls)
from seriesmith.backends.router import ROUTING, inline_in, mime_of, output_type

_VAR = re.compile(r"\{([a-z_][a-z0-9_]*)\}")
TIMEOUT = 120.0
BIG_TIMEOUT = 600.0                     # a request whose answer is the file itself
MAX_REDIRECTS = 5
RAW = object()


class ProviderHTTP(HTTPFailure):
    """HTTPFailure that says its status the way backends.transient reads it."""

    def __init__(self, status: int, text: str):
        super().__init__(status, text)
        self.http_status = status


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):
        return None


def pick(doc: Any, path) -> Any:
    """What `doc` has at a dotted path ("data.outputs.0"), the first found of a list of paths."""
    if isinstance(path, (list, tuple)):
        for p in path:
            got = pick(doc, p)
            if got not in (None, ""):
                return got
        return None
    at = doc
    for name in str(path).split("."):
        if isinstance(at, list) and name.isdigit() and int(name) < len(at):
            at = at[int(name)]
        elif isinstance(at, dict) and name in at:
            at = at[name]
        else:
            return None
    return at


def fill(template: Any, values: dict, quote: bool = False) -> Any:
    """`template` with its values in: "$name" as the value itself (a File stays one), `{name}`
    inside text, and a "..." key merging an object in."""
    if isinstance(template, str):
        if template.startswith("$") and template[1:] in values:
            return values[template[1:]]

        def one(m):
            if m.group(1) not in values:
                return m.group(0)
            text = str(values[m.group(1)])
            return urllib.parse.quote(text, safe="/") if quote else text
        return _VAR.sub(one, template)
    if isinstance(template, list):
        return [fill(x, values) for x in template]
    if isinstance(template, dict):
        out = {}
        for k, v in template.items():
            if k == "...":
                got = fill(v, values)
                if isinstance(got, dict):
                    out.update(got)
            else:
                out[k] = fill(v, values)
        return out
    return template


def multipart(fields: dict) -> tuple[bytes, str]:
    """(body, content type) of a form: a File as its bytes, anything else as text."""
    boundary = uuid.uuid4().hex
    out = bytearray()

    def part(name, value):
        out.extend(f"--{boundary}\r\n".encode())
        if isinstance(value, File):
            kind = mimetypes.guess_type(value.path)[0] or mime_of(value.path)
            out.extend(f'Content-Disposition: form-data; name="{name}"; '
                       f'filename="{os.path.basename(value.path)}"\r\n'.encode())
            out.extend(f"Content-Type: {kind}\r\n\r\n".encode())
            with open(value.path, "rb") as fh:
                out.extend(fh.read())
        else:
            text = value if isinstance(value, str) else json.dumps(value)
            out.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
            out.extend(text.encode("utf-8"))
        out.extend(b"\r\n")

    for name, value in fields.items():
        for one in value if isinstance(value, list) else [value]:
            part(name, one)
    out.extend(f"--{boundary}--\r\n".encode())
    return bytes(out), f"multipart/form-data; boundary={boundary}"


class HttpBackend(Backend):
    kind = "api"

    def __init__(self, definition: dict, key: str):
        if not key:
            raise BackendError(f"{definition.get('id')} needs its API key (Settings)")
        self.d = definition
        self.id = definition["id"]
        self.name = f"api:{self.id}"
        self._key = key
        self.base = str(definition["base_url"]).rstrip("/")
        self.parallel = int(definition.get("parallel") or 3)
        # by host and port: another port on the same host is someone else
        hosts = [urllib.parse.urlparse(self.base).netloc] + list(definition.get("hosts") or [])
        self._hosts = {h.lower() for h in hosts if h}

    # -- one request ------------------------------------------------------------

    def url_of(self, url: str) -> str:
        return url if re.match(r"https?://", url) else f"{self.base}/{url.lstrip('/')}"

    def _ours(self, url: str) -> bool:
        return urllib.parse.urlparse(url).netloc.lower() in self._hosts

    def _with_key(self, url: str, headers: dict) -> str:
        """`url`, and `headers` given the key, on the provider's own hosts only."""
        if not self._ours(url):
            return url
        auth = self.d.get("auth") or {}
        kind = auth.get("type")
        if kind == "bearer":
            headers["Authorization"] = f"Bearer {self._key}"
        elif kind == "header":
            headers[auth["name"]] = f"{auth.get('prefix') or ''}{self._key}"
        elif kind == "query":
            join = "&" if "?" in url else "?"
            url += f"{join}{urllib.parse.quote(auth['name'])}={urllib.parse.quote(self._key)}"
        else:
            raise BackendError(f"{self.id}: no way to send its key ({kind})")
        return url

    def _clean(self, text: str) -> str:
        """A message safe to show and log: the key out of it, should a provider echo it."""
        return text.replace(self._key, "(key)")

    def send(self, method: str, url: str, data: bytes | None = None, headers: dict | None = None,
             keyed: bool = True, timeout: float = TIMEOUT) -> tuple[bytes, str]:
        """(the answer's bytes, its content type), redirects followed by hand: the key isn't
        carried to another host. ProviderHTTP for an error status."""
        url = self.url_of(url)
        for _ in range(MAX_REDIRECTS + 1):
            hdrs = dict(headers or {})
            full = self._with_key(url, hdrs) if keyed else url
            req = urllib.request.Request(full, data=data, method=method, headers=hdrs)
            try:
                ctx = tls() if full.startswith("https") else None
                https = [urllib.request.HTTPSHandler(context=ctx)] if ctx else []
                opener = urllib.request.build_opener(_NoRedirect(), *https)
                with opener.open(req, timeout=timeout) as r:
                    return r.read(), r.headers.get("Content-Type", "")
            except urllib.error.HTTPError as e:
                if e.code in (301, 302, 303, 307, 308) and e.headers.get("Location"):
                    url = urllib.parse.urljoin(url, e.headers["Location"])
                    if e.code == 303:
                        method, data = "GET", None
                    continue
                raise ProviderHTTP(e.code, self._clean(e.read().decode("utf-8", "replace")[:1000])) from None
        raise BackendError(f"{self.id}: too many redirects from {url.split('?')[0]}")

    def run_step(self, step: dict, values: dict) -> tuple[Any, bytes | None, str]:
        """One step: (its JSON answer or None, its bytes when it answers with a file, their type)."""
        url = fill(step["url"], values, quote=True)
        headers = {k: str(fill(v, values)) for k, v in (step.get("headers") or {}).items()}
        data = None
        if "json" in step:
            data = json.dumps(_plain(fill(step["json"], values))).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")
        elif "multipart" in step:
            data, kind = multipart(fill(step["multipart"], values))
            headers["Content-Type"] = kind
        wants_file = step.get("response") == "bytes"
        raw, kind = self.send(step.get("method") or ("POST" if data else "GET"), url, data, headers,
                              timeout=BIG_TIMEOUT if wants_file else TIMEOUT)
        if wants_file:
            return None, raw, kind
        if not raw.strip():
            return {}, None, kind
        try:
            return json.loads(raw.decode("utf-8")), None, kind
        except ValueError:
            raise BackendError(f"{self.id}: {url.split('?')[0]} didn't answer in JSON: "
                               f"{self._clean(raw[:200].decode('utf-8', 'replace'))}") from None

    def take(self, step: dict, doc: Any, values: dict) -> None:
        """The values a step's answer gives the steps after it."""
        for name, path in (step.get("take") or {}).items():
            got = pick(doc, path)
            if got is None:
                raise BackendError(f"{self.id}: its answer has no {path}, which the definition takes "
                                   f"as {name}: {self._clean(json.dumps(doc))[:300]}")
            values[name] = got

    # -- files ------------------------------------------------------------------

    def _resolve_files(self, args: dict, cache: dict) -> None:
        """Every File in `args` as what this provider takes in its place."""
        how = self.d.get("files") or {"via": "datauri"}
        for container, key, f in list(files_in(args)):
            via = f.via if f.via in ("base64", "datauri") else how.get("via")
            if via == "multipart":
                continue
            k = (f.path, via)
            if k not in cache:
                cache[k] = self._file_value(f, via, how)
            container[key] = cache[k]

    def _file_value(self, f: File, via: str, how: dict) -> str:
        if via in ("base64", "datauri"):
            import base64
            with open(f.path, "rb") as fh:
                b64 = base64.b64encode(fh.read()).decode("ascii")
            return b64 if via == "base64" else f"data:{mime_of(f.path)};base64,{b64}"
        values: dict = {"file": f, "name": os.path.basename(f.path)}
        for step in how.get("steps") or []:
            # no job has started: asked again while the network hiccups
            doc = self._wait_for(step, values) if step.get("until") else \
                patiently(lambda s=step: self.run_step(s, values)[0])
            self.take(step, doc, values)
        return fill(how.get("value") or "$url", values)

    def _wait_for(self, step: dict, values: dict, should_stop=None, on_status=None) -> Any:
        """Ask a step until its status says done. Its answer; BackendError on failed or too long."""
        until = step["until"]
        every = float(until.get("every") or 5)
        end = time.monotonic() + float(until.get("timeout") or 3600)
        done = [str(x).lower() for x in until.get("done") or []]
        failed = [str(x).lower() for x in until.get("failed") or []]
        while True:
            doc = patiently(lambda: self.run_step(step, values)[0])
            status = str(pick(doc, until["status"]) or "").lower()
            if status in done:
                return doc
            if status in failed:
                raise ProviderFailed(self._said(doc, until) or f"the provider says {status}")
            if on_status:
                on_status("running")
            if time.monotonic() > end:
                raise BackendError(f"{self.id} still says {status or 'nothing'} after "
                                   f"{until.get('timeout') or 3600}s: stopped waiting, and it may "
                                   f"still be running and charged there")
            if should_stop and should_stop(every):
                raise ProviderCanceled()
            if not should_stop:
                time.sleep(every)

    def _said(self, doc: Any, until: dict) -> str:
        err = pick(doc, until.get("error")) if until.get("error") else None
        if err in (None, "", [], {}):
            return ""
        return self._clean(err if isinstance(err, str) else json.dumps(err))[:800]

    # -- a job ------------------------------------------------------------------

    def call(self, model: str, arguments: dict) -> Run:
        args = copy.deepcopy(arguments)
        how = args.pop(ROUTING, None) or {}
        self._resolve_files(args, {})
        values = {"model": model, "args": args, **(how.get("values") or {})}
        return HttpRun(self, model, values, 0)

    def attach(self, run_id: str, model: str | None = None) -> Run:
        try:
            saved = json.loads(run_id)
            return HttpRun(self, saved["model"], saved["values"], int(saved["step"]), started=True)
        except (ValueError, KeyError, TypeError):
            raise BackendError(f"{run_id!r} isn't a run of {self.name}") from None

    def ping(self) -> str | None:
        try:
            self.send("GET", self.base + "/", keyed=False, timeout=20.0)
        except HTTPFailure:
            return None                         # it answered
        except (urllib.error.URLError, OSError) as e:
            return f"{self.base}: {e}"
        return None


class ProviderFailed(RuntimeError):
    """The provider's own answer: the job failed there."""


class ProviderCanceled(RuntimeError):
    pass


def _plain(v):
    """What's left of a value for a JSON body. A File here is a definition that didn't say how
    its files go in."""
    if isinstance(v, File):
        raise BackendError(f"{os.path.basename(v.path)}: this provider's files go by multipart, and "
                           f"this step sends JSON")
    if isinstance(v, dict):
        return {k: _plain(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_plain(x) for x in v]
    return v


class HttpRun(Run):
    def __init__(self, backend: HttpBackend, model: str, values: dict, step: int, started: bool = False):
        self.backend_obj = backend
        self.backend = backend.name
        self.model = model
        self.values = values
        self.step = step
        self.status = "running" if started else "queued"
        self.result: Any = None
        self.file: tuple[bytes, str] | None = None
        self._stop = threading.Event()
        self.id = ""
        if not started:
            self._to_first_wait()
        self._mark()

    def _mark(self) -> None:
        """The id: what following this run needs, after a restart too. A job's arguments aren't
        kept (they can be whole files), and steps after the first wait don't need them."""
        keep = {k: v for k, v in self.values.items() if k != "args" and not isinstance(v, File)}
        self.id = json.dumps({"model": self.model, "step": self.step, "values": keep})

    def _steps(self) -> list[dict]:
        return self.backend_obj.d.get("steps") or []

    def _to_first_wait(self) -> None:
        """The steps up to the first that waits: the job is started here. Never asked twice: it
        may have started and been charged."""
        steps = self._steps()
        while self.step < len(steps) and not steps[self.step].get("until"):
            self._run_once(steps[self.step])
            self.step += 1

    def _run_once(self, step: dict) -> None:
        b = self.backend_obj
        try:
            doc, raw, kind = b.run_step(step, self.values)
        except HTTPFailure:
            raise
        except (TimeoutError, urllib.error.URLError, OSError) as e:
            raise BackendError(f"{b.id}: no answer to {step.get('method', 'POST')} {step.get('url')} "
                               f"({e}). It wasn't sent again: the job may have started and been "
                               f"charged, so look at {b.id}'s own dashboard before trying again."
                               ) from None
        if raw is not None:
            self.file = (raw, kind)
        else:
            self.result = doc
            b.take(step, doc, self.values)

    def refresh(self) -> str:
        return self.status

    def watch(self, on_progress: Callable[[Progress], None] | None = None,
              on_status: Callable[[str], None] | None = None) -> str:
        b = self.backend_obj
        steps = self._steps()
        told = {"last": None}

        def say(st: str) -> None:
            self.status = st
            if on_status and st != told["last"]:
                told["last"] = st
                on_status(st)

        try:
            say("running")
            while self.step < len(steps):
                step = steps[self.step]
                if step.get("until"):
                    self.result = b._wait_for(step, self.values, should_stop=self._stop.wait,
                                              on_status=say)
                    b.take(step, self.result, self.values)
                else:
                    # a later step fetches; it starts no job
                    doc, raw, kind = patiently(lambda s=step: b.run_step(s, self.values))
                    if raw is not None:
                        self.file = (raw, kind)
                    else:
                        self.result = doc
                        b.take(step, doc, self.values)
                self.step += 1
                self._mark()
            # a provider can finish and still say it failed (fal: COMPLETED, with an error)
            said = b._said(self.result, b.d.get("result") or {}) if self.result else ""
            if said:
                self.error = said
                say("failed")
            else:
                say("succeeded")
        except ProviderCanceled:
            say("canceled")
        except ProviderFailed as e:
            self.error = str(e)
            say("failed")
        return self.status

    def cancel(self) -> None:
        self._stop.set()
        self.status = "canceled"
        step = (self.backend_obj.d.get("cancel") or None)
        if step:
            try:
                self.backend_obj.run_step(step, self.values)
            except (HTTPFailure, BackendError, OSError):
                pass                            # stopping here is what's asked; it may run on there

    def outputs(self) -> list[Output]:
        if self.status != "succeeded":
            return []
        b = self.backend_obj
        result = b.d.get("result") or {}
        want = result.get("type") or self.values.get("type")
        if self.file is not None:
            raw, kind = self.file
            ty = want or (kind.split("/")[0] if kind.split("/")[0] in ("video", "image", "audio") else "file")
            ext = mimetypes.guess_extension(kind.split(";")[0].strip()) or {"video": ".mp4", "image": ".png", "audio": ".mp3"}.get(ty, ".bin")

            def write(path, raw=raw):
                from seriesmith.core import fileio as F
                F.write_bytes(path, raw)
            return [Output("", f"output{ext}", ty, write)]
        urls: list[str] = []
        if result.get("url"):
            urls = [fill(result["url"], self.values, quote=True)]
        elif result.get("files"):
            got = pick(self.result, result["files"])
            urls = [x for x in (got if isinstance(got, list) else [got]) if isinstance(x, str) and x]
        keyed = bool(result.get("auth"))
        out = []
        for u in urls:
            name = os.path.basename(urllib.parse.urlparse(u).path) or "output"

            def fetch(path, u=u):
                from seriesmith.core import fileio as F
                F.write_bytes(path, patiently(lambda: b.send("GET", u, keyed=keyed, timeout=BIG_TIMEOUT))[0])
            guessed = output_type(u)
            out.append(Output("", name, (want if guessed in ("file", "", None) else guessed) or want or "file", fetch))
        if not urls:
            import base64
            for i, (data, mime) in enumerate(inline_in(self.result)):
                ty = mime.split("/")[0] if mime.split("/")[0] in ("video", "image", "audio") else "file"
                ext = {"video": ".mp4", "image": ".png", "audio": ".wav"}.get(ty, ".bin")

                def write(path, d=data):
                    from seriesmith.core import fileio as F
                    F.write_bytes(path, base64.b64decode(d))
                out.append(Output("", f"output_{i}{ext}", ty, write))
        return out
