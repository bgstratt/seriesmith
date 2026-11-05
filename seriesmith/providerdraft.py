"""
providerdraft -- a provider set up from what its docs give you, not from a definition written by
hand (providers.py is what it comes to). Paste the cURL that starts a generation, or an OpenAPI
document, and this proposes a form: where it is, how it takes its key, the generate call, how the
answer comes back. Paste an example answer, or the cURL that checks on a job, and more of it fills
in. Everything is a suggestion in a form a person looks over.

    draft(text, answer, poll, poll_answer) -> {"form", "notes", "model"}
    from_page(html, address)               -> what a docs page shows: its OpenAPI link, its cURLs
    definition(form)                       -> a provider definition

A key pasted in a cURL is never kept: only how it was sent. Stdlib only.
"""
from __future__ import annotations

import html
import json
import re
import urllib.parse

from seriesmith import apispec as AS

DONE = ["completed", "succeeded", "success", "done", "finished"]
FAILED = ["failed", "error", "canceled", "cancelled", "rejected", "expired", "nsfw"]
MODEL_KEYS = ("model", "model_id", "modelId", "model_name", "modelName")
ID_KEYS = ("id", "request_id", "requestId", "task_id", "taskId", "prediction_id", "predictionId",
           "job_id", "jobId", "generation_id", "uuid")
STATUS_KEYS = ("status", "state", "task_status", "taskStatus")
ERROR_KEYS = ("error", "error_message", "errorMessage", "failure", "failure_reason", "detail")
FOLLOW_KEYS = ("status_url", "statusUrl", "polling_url", "pollingUrl", "get", "get_url", "poll_url")
FETCH_KEYS = ("response_url", "responseUrl", "result_url", "resultUrl")
KEY_PARAMS = ("key", "api_key", "apikey", "token", "access_token")


def _walk(doc, path=""):
    """(dotted path, leaf name, value) of everything in an answer, shallowest first."""
    level = [(doc, path)]
    while level:
        following = []
        for at, prefix in level:
            items = at.items() if isinstance(at, dict) else enumerate(at) if isinstance(at, list) else ()
            for k, v in items:
                p = f"{prefix}.{k}" if prefix else str(k)
                yield p, str(k), v
                if isinstance(v, (dict, list)):
                    following.append((v, p))
        level = following


def _find(doc, names, want=str) -> str:
    """The shallowest path whose leaf is one of `names`, in the order they're listed."""
    found = [(p, n, v) for p, n, v in _walk(doc) if n in names and isinstance(v, want) and v not in ("", None)]
    if not found:
        return ""
    return min(found, key=lambda x: (x[0].count("."), names.index(x[1])))[0]


def _is_link(v) -> bool:
    return isinstance(v, str) and v.startswith(("http://", "https://"))


def links_in(doc) -> str:
    """Where an answer's files are: the shallowest list of links, else a link that isn't a way of
    following the job."""
    best = ""
    for p, name, v in _walk(doc):
        if isinstance(v, list) and v and all(_is_link(x) for x in v):
            return p
        if not best and _is_link(v) and name not in FOLLOW_KEYS + FETCH_KEYS + ("cancel_url", "cancel", "self", "web"):
            best = p
    return best


def _json(text: str | None) -> dict | None:
    if not (text or "").strip():
        return None
    try:
        got = json.loads(text)
    except ValueError:
        raise AS.SpecError("that example answer isn't JSON") from None
    if not isinstance(got, dict):
        raise AS.SpecError("that example answer isn't a JSON object")
    return got


def _base_and_path(url: str) -> tuple[str, str]:
    u = urllib.parse.urlparse(url)
    return f"{u.scheme}://{u.netloc}", u.path or "/"


def _name_of(host: str) -> str:
    """"api.atlascloud.ai" -> "atlascloud"."""
    parts = [p for p in host.split(":")[0].split(".") if p not in ("api", "www", "queue", "app", "platform", "cloud")]
    return parts[-2] if len(parts) >= 2 else (parts[0] if parts else "provider")


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9_-]+", "_", name.lower()).strip("_") or "provider"


def _key_in_query(url: str) -> tuple[str, dict | None]:
    """`url` without a key in its query, and how the key was sent."""
    u = urllib.parse.urlparse(url)
    q = urllib.parse.parse_qsl(u.query, keep_blank_values=True)
    hit = next((k for k, _ in q if k.lower() in KEY_PARAMS), None)
    if not hit:
        return url, None
    kept = urllib.parse.urlencode([(k, v) for k, v in q if k != hit])
    return urllib.parse.urlunparse(u._replace(query=kept)), {"type": "query", "name": hit}


def _empty_form() -> dict:
    return {"id": "", "label": "", "base_url": "", "auth_type": "bearer", "auth_name": "", "auth_prefix": "",
            "method": "POST", "url": "", "body": "json", "model_field": "", "answer": "job",
            "id_path": "", "poll_url": "", "status_path": "", "done": ", ".join(DONE), "failed": ", ".join(FAILED),
            "error_path": "", "files_path": "", "fetch_url": "", "download_auth": False, "every": 5,
            "files_via": "datauri", "upload_url": "", "upload_field": "file", "upload_link": "",
            "upload_type_field": "content_type", "upload_put": "", "upload_headers": "",
            "check_url": ""}


def _apply_answer(form: dict, answer: dict, notes: list[str]) -> None:
    """What an answer to the generate call says of how the job comes back."""
    files = links_in(answer)
    status = _find(answer, STATUS_KEYS)
    task = _find(answer, ID_KEYS)
    follow = _find(answer, FOLLOW_KEYS)
    if follow or task:
        form["answer"] = "job"
        form["id_path"] = task
        if follow:
            form["poll_url"] = "$" + follow.split(".")[-1]
            form["follow_path"] = follow
            notes.append(f"Its answer gives the address to check on a job ({follow}). The key goes "
                         f"to it only if it's the provider's own address.")
        fetch = _find(answer, FETCH_KEYS)
        if fetch:
            form["fetch_url"] = "$" + fetch.split(".")[-1]
            form["fetch_path"] = fetch
        if status:
            form["status_path"] = status
    elif files:
        form["answer"] = "links"
        form["files_path"] = files
    else:
        notes.append("That answer has no job id and no links: say how it comes back below.")


def _apply_poll_answer(form: dict, answer: dict) -> None:
    status = _find(answer, STATUS_KEYS)
    if status:
        form["status_path"] = status
        value = str(next(v for p, _, v in _walk(answer) if p == status)).lower()
        done = [x.strip() for x in form["done"].split(",")]
        if value not in done + [x.strip() for x in form["failed"].split(",")] and value not in ("queued", "processing", "running", "pending", "starting", "in_progress"):
            form["done"] = ", ".join([value] + done)
    err = _find(answer, ERROR_KEYS, (str, dict))
    if err:
        form["error_path"] = err
    files = links_in(answer)
    if files:
        form["files_path"] = files


def from_page(page: str, address: str) -> dict:
    """What a docs page shows, in its HTML or as Markdown: {"openapi": a link to its OpenAPI document
    on the same host, "post": the cURL that starts a generation, "poll": the one that checks on it,
    "schema": a request's JSON Schema, "answer" and "poll_answer": example answers}, each None when
    the page doesn't have it (many draw themselves in the browser)."""
    host = urllib.parse.urlparse(address).netloc
    openapi = None
    for link in re.findall(r"""[^"'\s<>\\]*openapi[^"'\s<>\\]*\.json[^"'\s<>\\]*""", page):
        full = urllib.parse.urljoin(address, html.unescape(link))
        if urllib.parse.urlparse(full).netloc == host:
            openapi = full
            break
    post = poll = other = None
    fenced = _fences(page)
    shown = [html.unescape(re.sub(r"<[^>]+>", "", m.group())).strip()
             for m in re.finditer(r"curl(?:\s|<[^>]+>)+-[\s\S]{0,40000}?(?=</code>|</pre>)", page)]
    for text in shown + [x for x in fenced if AS.curl_in(x)]:
        try:
            c = AS.parse_curl(text)
        except (AS.SpecError, ValueError):
            continue
        if c["body"] and c["method"] == "POST":
            post = post or text
        elif c["method"] == "GET":
            if urllib.parse.urlparse(c["url"]).path.rstrip("/").endswith("status"):
                poll = poll or text
            else:
                other = other or text
    examples = []
    for x in fenced:
        try:
            got = json.loads(x)
        except ValueError:
            continue                            # the page's other code: Python, TypeScript
        if isinstance(got, dict):
            examples.append(got)
    schema = next((x for x in examples if x.get("type") == "object" and isinstance(x.get("properties"), dict)), None)
    answers = [x for x in examples if x is not schema and _find(x, STATUS_KEYS)]
    return {"openapi": openapi, "post": post, "poll": poll or other, "schema": schema,
            "answer": next((json.dumps(x) for x in answers if not links_in(x)), None),
            "poll_answer": next((json.dumps(x) for x in answers if links_in(x)), None)}


def _fences(page: str) -> list[str]:
    """The code blocks of a Markdown page, a block inside a quote (`> ```json`) included."""
    plain = "\n".join(re.sub(r"^(?:> ?)+", "", line) for line in page.splitlines())
    return [m.group(1) for m in re.finditer(r"^```[^\n]*\n([\s\S]*?)^```", plain, re.MULTILINE)]


def document_of(schema: dict, curl: str) -> dict:
    """The one request a docs page describes, as an OpenAPI document."""
    path = urllib.parse.urlparse(AS.parse_curl(curl)["url"]).path or "/"
    return {"openapi": "3.1.0", "paths": {path: {"post": {"requestBody": {"content": {
        "application/json": {"schema": schema}}}}}}}


def _example(doc: dict, schema, name: str = "", depth: int = 0):
    """An answer as a schema describes it, for reading paths from: its own example where it has one."""
    from seriesmith.router_inspect import _resolve
    if not isinstance(schema, dict) or depth > 6:
        return None
    if isinstance(schema.get("examples"), list) and schema["examples"]:
        return schema["examples"][0]
    if "example" in schema:
        return schema["example"]
    s = _resolve(doc, schema)
    for key in ("allOf", "anyOf", "oneOf"):
        choices = [c for c in s.get(key) or [] if _resolve(doc, c).get("type") != "null"]
        if choices and key == "allOf":
            merged = {}
            for c in choices:
                got = _example(doc, c, name, depth + 1)
                if isinstance(got, dict):
                    merged.update(got)
            return merged
        if choices:
            return _example(doc, choices[0], name, depth + 1)
    kind = s.get("type")
    if kind == "object" or s.get("properties"):
        return {k: _example(doc, v, k, depth + 1) for k, v in (s.get("properties") or {}).items()}
    if kind == "array":
        return [_example(doc, s.get("items"), name, depth + 1)]
    if kind == "string":
        enum = [str(x) for x in s.get("enum") or []]
        if name in STATUS_KEYS:
            # the value a finished job has, so that it's read as done
            return next((x for x in enum if x.lower() in DONE), "processing")
        if enum:
            return enum[0]
        low = name.lower()
        if low.endswith(("url", "uri", "link")) or s.get("format") == "uri":
            return "https://example.invalid/file"
        return "x"
    return {"integer": 0, "number": 0, "boolean": False}.get(kind)


def _answer_of(doc: dict, op: dict):
    for code in ("200", "201", "202"):
        schema = (((op.get("responses") or {}).get(code) or {}).get("content") or {}).get("application/json", {}).get("schema")
        if schema:
            return _example(doc, schema)
    return None


def _answers_in(doc: dict, chosen: str) -> dict:
    """What an OpenAPI document says comes back from the request at `chosen`: {"answer", "status",
    "status_path", "result", "result_path", "statuses"}, whichever it describes."""
    paths = doc.get("paths") or {}
    out = {"answer": _answer_of(doc, (paths.get(chosen) or {}).get("post") or {})}
    ours = sorted((p for p, ops in paths.items() if "{" in p and isinstance(ops, dict) and ops.get("get")),
                  key=lambda p: not p.startswith(chosen))
    for p in ours:
        got = _answer_of(doc, paths[p]["get"])
        if not isinstance(got, dict):
            continue
        if _find(got, STATUS_KEYS) and "status" not in out:
            out.update(status=got, status_path=p, statuses=_status_values(doc, paths[p]["get"]))
        elif links_in(got) and "result" not in out:
            out.update(result=got, result_path=p)
    return out


def _status_values(doc: dict, op: dict) -> list[str]:
    from seriesmith.router_inspect import _resolve
    schema = (((op.get("responses") or {}).get("200") or {}).get("content") or {}).get("application/json", {}).get("schema") or {}
    props = _resolve(doc, schema).get("properties") or {}
    for k in STATUS_KEYS:
        if k in props:
            return [str(x).lower() for x in _resolve(doc, props[k]).get("enum") or []]
    return []


def draft(text: str, answer: str | None = None, poll: str | None = None,
          poll_answer: str | None = None, path: str | None = None, doc: dict | None = None) -> dict:
    """{"form", "notes", "model", "paths"?} from what's pasted. `doc`: an OpenAPI document that goes
    with a pasted cURL. SpecError saying what to do."""
    text = (text or "").strip()
    if not text:
        raise AS.SpecError("paste the cURL that starts a generation, or the API's OpenAPI document")
    form, notes, model = _empty_form(), [], ""
    chosen = None
    if AS.curl_in(text):
        c = AS.parse_curl(text)
        url, query_auth = _key_in_query(c["url"])
        base, rest = _base_and_path(url)
        auth = query_auth or c["auth"]
        if not auth:
            notes.append("That cURL doesn't show a key. Bearer is assumed: change it below if the docs say otherwise.")
        if auth:
            form.update(auth_type=auth["type"], auth_name=auth.get("name", ""), auth_prefix=auth.get("prefix", ""))
        form.update(base_url=base, method=c["method"], body="multipart" if c["form"] else "json", url=rest)
        if c["form"]:
            form["files_via"] = "multipart"
        field = next((k for k in MODEL_KEYS if k in c["body"]), "")
        if field:
            form["model_field"] = field
            model = str(c["body"][field])
        else:
            # no model in the body: on many APIs (fal's, Replicate's) it's in the address
            model = rest.strip("/")
            form["url"] = "/{model}"
            notes.append("The body names no model, so the whole address is taken as the model's id. If "
                         "only part of it is, change the address below and put {model} there.")
        if doc and rest in (doc.get("paths") or {}):
            chosen = rest
    else:
        got = AS.read(text, path)
        if got["form"] != "openapi":
            raise AS.SpecError("to set up a provider, paste its cURL or OpenAPI document: an example body "
                               "doesn't say where it is")
        doc = json.loads(text)
        servers = doc.get("servers") or []
        base = str((servers[0] or {}).get("url") or "").rstrip("/") if servers else ""
        if not base:
            notes.append("That document doesn't say its address: fill it in below.")
        form["base_url"] = base
        if got["doc"] is None:
            return {"form": form, "notes": notes, "model": "", "paths": got["paths"]}
        form["url"] = got["chosen"]
        schemes = (doc.get("components") or {}).get("securitySchemes") or doc.get("securityDefinitions") or {}
        for s in schemes.values():
            if s.get("scheme") == "bearer" or s.get("type") == "oauth2":
                form.update(auth_type="bearer")
                break
            if s.get("type") == "apiKey":
                form.update(auth_type="query" if s.get("in") == "query" else "header", auth_name=s.get("name", ""))
                if form["auth_type"] == "header" and str(s.get("name")).lower() == "authorization":
                    notes.append("That document doesn't say what goes before the key in the Authorization "
                                 "header. Its docs' cURL shows it (\"Key\", \"Token\"...): put it under the key's "
                                 "prefix below, or Check it will be refused.")
                break
        props = next(iter(next(iter(got["doc"]["paths"].values())).values()))
        schema = ((props.get("requestBody") or {}).get("content") or {}).get("application/json", {}).get("schema") or {}
        from seriesmith.router_inspect import _resolve
        names = (_resolve(doc, schema).get("properties") or {})
        form["model_field"] = next((k for k in MODEL_KEYS if k in names), "")
        chosen = got["chosen"]
        if not form["model_field"] and "{" not in chosen:
            model = chosen.strip("/")
            form["url"] = "/{model}"
            notes.append("The body names no model, so the whole address is taken as the model's id. If "
                         "only part of it is, change the address below and put {model} there.")
    host = urllib.parse.urlparse(form["base_url"]).netloc
    name = _name_of(host) if host else "provider"
    form.update(id=_slug(name), label=name.capitalize())
    parsed = _json(answer)
    told = _answers_in(doc, chosen) if doc and chosen else {}
    if parsed or told.get("answer"):
        _apply_answer(form, parsed or told["answer"], notes)
    if (poll or "").strip():
        p = AS.parse_curl(poll)
        purl, _ = _key_in_query(p["url"])
        pbase, prest = _base_and_path(purl)
        task = str(next((v for q, _, v in _walk(parsed or {}) if q == form["id_path"]), "") or "")
        if task and task in prest:
            prest = prest.replace(task, "{task}")
        elif re.search(r"\$\{?\w+\}?|\{\w+\}|<[^/>]+>", prest):        # a docs' $REQUEST_ID
            prest = re.sub(r"\$\{?\w+\}?|\{\w+\}|<[^/>]+>", "{task}", prest)
        else:
            prest = re.sub(r"/(?:[^/]*)$", "/{task}", prest)
        addr = prest if pbase == form["base_url"] else pbase + prest
        if str(form["poll_url"]).startswith("$"):
            form["check_url"] = addr             # its answers give the address: this one proves a key
        else:
            form["poll_url"] = addr
        form["answer"] = "job"
    pa = _json(poll_answer)
    if pa or told.get("status"):
        _apply_poll_answer(form, pa or told["status"])
    if told:
        _apply_document(form, told, chosen, notes, bool(pa))
    return {"form": form, "notes": notes, "model": model}


def _apply_document(form: dict, told: dict, chosen: str, notes: list[str], status_seen: bool) -> None:
    """What's still empty, from the answers an OpenAPI document describes."""
    def ours(p: str) -> str:
        if form["url"] == "/{model}" and p.startswith(chosen):
            p = "/{model}" + p[len(chosen):]
        return re.sub(r"\{(?!model\})[^}]+\}", "{task}", p)

    if not form["poll_url"] and told.get("status_path"):
        form["poll_url"] = ours(told["status_path"])
    if told.get("result") and not form["files_path"]:
        form["files_path"] = links_in(told["result"])
        if not form["fetch_url"] and told.get("result_path"):
            form["fetch_url"] = ours(told["result_path"])
    statuses = told.get("statuses") or []
    if statuses and not status_seen and not form["error_path"] and not set(statuses) & set(FAILED):
        # no status for a failure: it ends as done, with an error beside it (fal's queue)
        form["error_path"] = "error"
        notes.append("Its statuses have no failed one, so a failed job ends as done: its answer's error field "
                     "is read for that. Check that's where this provider says it.")
    if told.get("status") or told.get("result") or told.get("answer"):
        notes.append("How it answers is read from what its document describes, not a real answer: the first "
                     "take is what proves it.")


def _words(text) -> list[str]:
    return [x.strip() for x in str(text or "").split(",") if x.strip()]


def definition(form: dict) -> dict:
    """The provider definition a form comes to."""
    f = {**_empty_form(), **form}
    auth = {"type": f["auth_type"]}
    if f["auth_type"] in ("header", "query"):
        auth["name"] = f["auth_name"]
    if f["auth_type"] == "header" and f["auth_prefix"]:
        auth["prefix"] = f["auth_prefix"]
    args = {f["model_field"]: "$model", "...": "$args"} if f["model_field"] else "$args"
    if f["body"] == "multipart" and not isinstance(args, dict):
        args = {"...": "$args"}
    generate: dict = {"method": f["method"] or "POST", "url": f["url"], ("multipart" if f["body"] == "multipart" else "json"): args}
    steps, result = [generate], {}
    if f["answer"] == "file":
        generate["response"] = "bytes"
    elif f["answer"] == "links":
        result = {"files": f["files_path"]}
    else:
        take = {}
        if f["id_path"]:
            take["task"] = f["id_path"]
        for url_key, path_key in (("poll_url", "follow_path"), ("fetch_url", "fetch_path")):
            if str(f[url_key]).startswith("$") and f.get(path_key):
                take[f[url_key][1:]] = f[path_key]
        if take:
            generate["take"] = take
        until = {"status": f["status_path"], "done": _words(f["done"]), "failed": _words(f["failed"]),
                 "every": f["every"] or 5, "timeout": 3600}
        if f["error_path"]:
            until["error"] = f["error_path"]
        steps.append({"method": "GET", "url": f["poll_url"], "until": until})
        if f["fetch_url"]:
            steps.append({"method": "GET", "url": f["fetch_url"]})
        result = {"files": f["files_path"]}
        if f["error_path"]:
            result["error"] = f["error_path"]
    out = {"id": f["id"], "label": f["label"] or f["id"], "base_url": str(f["base_url"]).rstrip("/"),
           "auth": auth, "parallel": 3, "steps": steps}
    if result:
        out["result"] = result
    if f["download_auth"] and result:
        result["auth"] = True
    if f["check_url"]:
        out["check"] = f["check_url"]
    if f["files_via"] == "upload":
        out["files"] = {"via": "upload", "value": "$url", "steps": [
            {"method": "POST", "url": f["upload_url"], "multipart": {f["upload_field"] or "file": "$file"},
             "take": {"url": f["upload_link"]}}]}
    elif f["files_via"] == "presigned":
        # ask where, then put the file there: storage gets the file and never the key
        take = {"put_to": f["upload_put"], "link": f["upload_link"]}
        put = {"method": "PUT", "url": "$put_to", "key": False, "body": "$file"}
        if f["upload_headers"]:
            take["put_headers"] = f["upload_headers"]
            put["headers"] = "$put_headers"
        out["files"] = {"via": "upload", "value": "$link", "steps": [
            {"method": "POST", "url": f["upload_url"], "json": {f["upload_type_field"] or "content_type": "$mime"},
             "take": take}, put]}
    else:
        out["files"] = {"via": f["files_via"]}
    return out


def form_problems(form: dict) -> list[str]:
    """What's left to fill in, in the form's own words."""
    f = {**_empty_form(), **form}
    out = []
    if f["answer"] == "job":
        if not f["id_path"] and not str(f["poll_url"]).startswith("$"):
            out.append("Say where its answer has the job's id")
        if not f["poll_url"]:
            out.append("Say the address that checks on a job")
        if not f["status_path"]:
            out.append("Say which field of that answer is the status")
        if not f["files_path"]:
            out.append("Say where the finished links are")
    if f["answer"] == "links" and not f["files_path"]:
        out.append("Say where its answer has the links")
    if f["files_via"] == "upload" and not (f["upload_url"] and f["upload_link"]):
        out.append("Say the upload address, and where its answer has the file's link")
    if f["files_via"] == "presigned" and not (f["upload_url"] and f["upload_put"] and f["upload_link"]):
        out.append("Say the address that gives an upload address, and where its answer has that address and the file's link")
    return out
