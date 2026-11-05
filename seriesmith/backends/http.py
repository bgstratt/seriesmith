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
# who's asking. Python's default gets a provider behind Cloudflare a flat 403, "error code: 1010",
# before the request reaches it (Atlas, 2026-11-04)
USER_AGENT = "seriesmith"


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


def file_type(path: str) -> str:
    """A file's media type as an upload declares it. What's declared can have to match what's sent
    (Higgsfield's upload address), so a .webp isn't called a png."""
    return mimetypes.guess_type(path)[0] or mime_of(path)


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
        for name, value in (self.d.get("headers") or {}).items():
            headers.setdefault(name, str(value))         # what it asks of every request (Runway's version)
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
            hdrs = {"User-Agent": USER_AGENT, **(headers or {})}
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
        # a step's headers can be a whole object an earlier answer gave ("$upload_headers")
        told = fill(step.get("headers") or {}, values)
        headers = {str(k): str(v) for k, v in told.items()} if isinstance(told, dict) else {}
        data = None
        raw_file = "body" in step
        if raw_file:
            got = fill(step["body"], values)
            if not isinstance(got, File):
                raise BackendError(f"{self.id}: a step's body is a file (\"$file\"), and this has none")
            with open(got.path, "rb") as fh:
                data = fh.read()
            headers.setdefault("Content-Type", file_type(got.path))
        elif "json" in step:
            data = json.dumps(_plain(fill(step["json"], values))).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")
        elif "multipart" in step:
            data, kind = multipart(fill(step["multipart"], values))
            headers["Content-Type"] = kind
        wants_file = step.get("response") == "bytes"
        raw, kind = self.send(step.get("method") or ("PUT" if raw_file else "POST" if data else "GET"), url, data, headers,
                              keyed=step.get("key") is not False,
                              timeout=BIG_TIMEOUT if wants_file or raw_file else TIMEOUT)
        if wants_file:
            return None, raw, kind
        if raw_file or step.get("response") == "none":
            return {}, None, kind               # storage's answer, if any, isn't the provider's JSON
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
                # a signed address in the answer isn't for a log: its query is what signs it
                said = re.sub(r"(https?://[^\s\"'?]*)\?[^\s\"']*", r"\1?...", self._clean(json.dumps(doc)))
                raise BackendError(f"{self.id}: its answer has no {path}, which the definition takes "
                                   f"as {name}: {said[:300]}")
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
        values: dict = {"file": f, "name": os.path.basename(f.path), "mime": file_type(f.path)}
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
                # a job can end as done with an error beside it (fal's queue has no failed status)
                said = self._said(doc, until)
                if said:
                    raise ProviderFailed(said)
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


def planned_calls(d: dict, model: str, arguments: dict) -> list[dict]:
    """The calls a job on provider definition `d` would make, for the panel: nothing is sent, and
    the key shows as what it's sent as. Values only an answer gives stay as {task}."""
    args = copy.deepcopy(arguments)
    how = args.pop(ROUTING, None) or {}
    values = {"model": model, "args": args, **(how.get("values") or {})}
    base = str(d.get("base_url") or "").rstrip("/")
    auth = d.get("auth") or {}
    key = ("Authorization: Bearer (your key)" if auth.get("type") == "bearer"
           else f"{auth.get('name')}: {auth.get('prefix') or ''}(your key)" if auth.get("type") == "header"
           else f"?{auth.get('name')}=(your key)")
    key = ", ".join([key] + [f"{k}: {v}" for k, v in (d.get("headers") or {}).items()])
    out = []
    has_files = bool(list(files_in(args)))
    how_files = d.get("files") or {}
    if values.get("use") == "timed" and isinstance(d.get("timed"), dict):
        d = {**d, **d["timed"]}
    if has_files and how_files.get("via") == "upload":
        for step in how_files.get("steps") or []:
            sends = ({"body": "(the file)"} if "body" in step else
                     fill(step["json"], {"mime": "(its type)", "name": "(its name)"}) if "json" in step else
                     {("(the fields its answer gives)" if k == "..." else k): "(the file)" if v == "$file" else "..."
                      for k, v in (step.get("multipart") or {}).items()})
            out.append({"what": "upload, for each picture", "method": step.get("method") or ("PUT" if "body" in step else "POST"),
                        "url": _full(base, step["url"]), "key": "no key" if step.get("key") is False else key,
                        "sends": sends, "takes": step.get("take")})
    for i, step in enumerate(d.get("steps") or []):
        url = str(fill(step["url"], values, quote=True))
        body = None
        for kind in ("json", "multipart"):
            if kind in step:
                body = _shown(fill(step[kind], values))
        waits = step.get("until")
        out.append({"what": ("wait" if waits else "generate" if i == 0 else "fetch"),
                    "method": step.get("method") or ("POST" if body is not None else "GET"),
                    "url": _full(base, url), "key": key,
                    **({"sends": body} if body is not None else {}),
                    **({"takes": step["take"]} if step.get("take") else {}),
                    **({"until": waits} if waits else {}),
                    **({"answers": "the file itself"} if step.get("response") == "bytes" else {})})
    result = d.get("result") or {}
    if result.get("files"):
        out.append({"what": "download", "method": "GET", "url": f"(the links at {result['files']})",
                    "key": key if result.get("auth") else "no key"})
    elif result.get("url"):
        out.append({"what": "download", "method": "GET", "url": _full(base, str(fill(result["url"], values, quote=True))),
                    "key": key if result.get("auth") else "no key"})
    return out


def _full(base: str, url: str) -> str:
    return url if re.match(r"https?://|\$", url) else f"{base}/{url.lstrip('/')}"


def _shown(v):
    if isinstance(v, File):
        return {"file": v.path}
    if isinstance(v, dict):
        return {k: _shown(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_shown(x) for x in v]
    return v


def list_voices(d: dict, key: str | None, which: str = "", search: str = "", after: str = "") -> dict:
    """The speakers a provider has, from one of its definition's `voices.lists`: one read that costs
    nothing. A `free` list goes with no key when there isn't one, and as it answers an anonymous
    reader only its plain address is asked. {"voices": [{"id", "name", "preview", "about", "category",
    "labels"}], "next": the page after, if any}. HTTPFailure and URLError as a request's."""
    how = d.get("voices") if isinstance(d.get("voices"), dict) else {}
    lists = how.get("lists") or []
    one = next((x for x in lists if x.get("id") == which), lists[0] if lists and not which else None)
    if not one or not one.get("url"):
        raise BackendError(f"{d.get('id')}: its definition doesn't list voices called {which or 'anything'}")
    if not key and not one.get("free"):
        raise BackendError(f"{d.get('label') or d.get('id')} needs its key for that list")
    b = HttpBackend(d, key or "(no key)")
    url = str(one["url"])
    if key:
        for name, value in ((one.get("search_param"), search),
                            (one.get("next_param") or one.get("page_param"), after)):
            if name and value:
                url += ("&" if "?" in url else "?") + f"{urllib.parse.quote(str(name))}={urllib.parse.quote(value, safe='')}"
    raw, _ = patiently(lambda: b.send("GET", url, keyed=bool(key)))
    try:
        doc = json.loads(raw.decode("utf-8"))
    except ValueError:
        raise BackendError(f"{b.id}: its list of voices wasn't JSON") from None
    rows = pick(doc, one.get("list")) if one.get("list") else doc
    out = []
    for row in rows if isinstance(rows, list) else []:
        vid = pick(row, how.get("id") or "id")
        if not vid:
            continue
        labels = pick(row, how["labels"]) if how.get("labels") else None
        labels = dict(labels) if isinstance(labels, dict) else {}
        for name in how.get("label_fields") or []:
            if row.get(name) and name not in labels:
                labels[name] = row[name]
        out.append({"id": str(vid), "name": str(pick(row, how.get("name") or "name") or vid),
                    "preview": (pick(row, how["preview"]) if how.get("preview") else None) or "",
                    "about": (pick(row, how["about"]) if how.get("about") else None) or "",
                    "category": (pick(row, how["category"]) if how.get("category") else None) or "",
                    "labels": {str(k): str(v) for k, v in labels.items()}})
    following = ""
    if one.get("next"):
        following = str(pick(doc, one["next"]) or "")
    elif one.get("page_param") and key and pick(doc, one.get("has_more") or "has_more"):
        following = str(int(after or 0) + 1)
    return {"voices": out, "next": following}


def check_key(d: dict, key: str) -> dict:
    """Whether a provider can be reached with a key, by one read that starts nothing: asking after
    a job that doesn't exist. {"reached", "key_ok", "proves_key", "status", "says"}. A 401 or 403 can
    be the key or a firewall in front of it; the answer is shown either way. `proves_key` false: no
    address to ask (its answers give the one that checks on a job, or it needs a model's id), so
    only the provider's front door was asked, and a key it doesn't refuse there may still be wrong."""
    b = HttpBackend(d, key)
    wait = next((s for s in d.get("steps") or [] if s.get("until")), None)
    target = d.get("check") or (str(wait["url"]) if wait else "")
    proves = bool(target) and not target.startswith("$") and "{model}" not in target
    url = fill(target if proves else b.base, {"task": "seriesmith-check-does-not-exist"}, quote=True)
    try:
        raw, _ = b.send("GET", url, timeout=20.0)
        return {"reached": True, "key_ok": True, "proves_key": proves, "status": 200,
                "says": b._clean(raw[:300].decode("utf-8", "replace"))}
    except HTTPFailure as e:
        return {"reached": True, "key_ok": e.status not in (401, 403), "proves_key": proves,
                "status": e.status, "says": e.text[:300]}
    except (urllib.error.URLError, OSError) as e:
        return {"reached": False, "key_ok": False, "proves_key": proves, "status": None, "says": b._clean(str(e))[:300]}


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

    def _how(self) -> dict:
        """What this run follows: the definition's, or its `timed` way when it was asked for and
        the provider has one (a voice with its timings)."""
        d = self.backend_obj.d
        return (d.get("timed") if self.values.get("use") == "timed" and isinstance(d.get("timed"), dict) else None) or d

    def _steps(self) -> list[dict]:
        return self._how().get("steps") or []

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
            said = b._said(self.result, self._how().get("result") or {}) if self.result else ""
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
        result = self._how().get("result") or {}
        want = result.get("type") or self.values.get("type")
        if result.get("inline"):
            # the file inside the answer, as base64 (ElevenLabs' with-timestamps)
            import base64
            data = pick(self.result, result["inline"])
            if not isinstance(data, str) or not data:
                return []
            mime = str(result.get("mime") or "application/octet-stream")
            ext = mimetypes.guess_extension(mime) or ".bin"

            def inside(path, d=data):
                from seriesmith.core import fileio as F
                F.write_bytes(path, base64.b64decode(d))
            return [Output("", f"output{ext}", want or "file", inside)]
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
