"""
apispec -- a model's API reference, in whatever form its provider gives it, read into a proposed
target (docs/PLAN.md step 15.4): an OpenAPI document (pasted, or its URL), an example cURL, or an
example request's JSON. Each becomes the same small OpenAPI document, so one proposer serves
them all (router_inspect). An example shows names and values, not limits: what it can't say is a
guess, listed in `warnings`, which the Fields tab and a first paid probe settle.

A key pasted in a cURL is never kept: only the header's name is read, to say how the API
authenticates. YAML isn't read (stdlib only): the message says to paste JSON.
"""
from __future__ import annotations

import json
import re
import shlex
import urllib.parse

from seriesmith import providers as PR
from seriesmith import router_inspect as RI
from seriesmith import targets as TG


def PV_where(spec) -> str:
    from seriesmith.promptview import where
    return where(spec)


class SpecError(ValueError):
    pass


def _schema_of(value) -> dict:
    """A JSON Schema for an example value."""
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, int):
        return {"type": "integer"}
    if isinstance(value, float):
        return {"type": "number"}
    if isinstance(value, str):
        return {"type": "string"}
    if isinstance(value, list):
        return {"type": "array", "items": _schema_of(value[0]) if value else {"type": "string"}}
    if isinstance(value, dict):
        return {"type": "object", "properties": {k: _schema_of(v) for k, v in value.items()}}
    return {}


def doc_from_example(body: dict, path: str = "/generate") -> dict:
    """The OpenAPI document an example request stands for. Nothing is marked required: an example
    doesn't say."""
    return {"paths": {path: {"post": {"requestBody": {"content": {"application/json": {
        "schema": _schema_of(body)}}}}}}}


def parse_curl(text: str) -> dict:
    """{"method", "url", "body", "auth"} of a cURL line, the auth as how and never the key."""
    try:
        words = shlex.split(text.replace("\\\r\n", " ").replace("\\\n", " "), posix=True)
    except ValueError as e:
        raise SpecError(f"that cURL couldn't be read: {e}") from None
    url, method, data, form, auth = "", "", None, {}, None
    i = 1
    while i < len(words):
        w = words[i]
        following = words[i + 1] if i + 1 < len(words) else ""
        if w in ("-X", "--request"):
            method, i = following, i + 2
        elif w in ("-H", "--header"):
            name, _, value = following.partition(":")
            low, value = name.strip().lower(), value.strip()
            if low == "authorization":
                scheme = value.split(" ", 1)[0].lower() if " " in value else ""
                auth = {"type": "bearer"} if scheme == "bearer" else {
                    "type": "header", "name": name.strip(), "prefix": f"{value.split(' ', 1)[0]} " if scheme else ""}
            elif low in ("x-api-key", "api-key", "xi-api-key") or "key" in low or "token" in low:
                auth = {"type": "header", "name": name.strip()}
            i += 2
        elif w in ("-d", "--data", "--data-raw", "--data-binary"):
            data, i = following, i + 2
        elif w in ("-F", "--form"):
            name, _, value = following.partition("=")
            form[name] = "" if value.startswith("@") else value
            i += 2
        elif w.startswith("http"):
            url, i = w, i + 1
        elif w.startswith("-"):
            i += 1
        else:
            url, i = (w if not url else url), i + 1
    if not url:
        raise SpecError("that cURL has no address in it")
    body: dict = dict(form)
    if data is not None:
        try:
            got = json.loads(data)
        except ValueError:
            raise SpecError("that cURL's -d isn't JSON: put the JSON body in place of any variables") from None
        if not isinstance(got, dict):
            raise SpecError("that cURL's body isn't a JSON object")
        body = got
    return {"method": (method or ("POST" if body else "GET")).upper(),
            "url": url, "body": body, "auth": auth, "form": bool(form)}


def post_paths(doc: dict) -> list[str]:
    """The paths of an OpenAPI document that take a JSON request."""
    out = []
    for path, ops in (doc.get("paths") or {}).items():
        post = (ops or {}).get("post") if isinstance(ops, dict) else None
        if post and ((post.get("requestBody") or {}).get("content") or {}).get("application/json"):
            out.append(path)
    return out


def read(text: str, path: str | None = None) -> dict:
    """{"form": "openapi" | "curl" | "example", "doc": an OpenAPI document with one request,
    "paths": the requests to choose from, "url"?, "auth"?}. SpecError saying what to do."""
    text = (text or "").strip()
    if not text:
        raise SpecError("paste the API's reference: its OpenAPI document, an example cURL, or an example request's JSON")
    if text.lower().startswith("curl"):
        c = parse_curl(text)
        if not c["body"]:
            raise SpecError("that cURL sends no body, so it says nothing of the model's fields")
        u = urllib.parse.urlparse(c["url"])
        return {"form": "curl", "doc": doc_from_example(c["body"], u.path or "/generate"), "paths": [u.path],
                "url": c["url"], "auth": c["auth"], "multipart": c["form"]}
    try:
        parsed = json.loads(text)
    except ValueError:
        raise SpecError("that isn't JSON or a cURL. An OpenAPI document in YAML needs converting to JSON first") from None
    if not isinstance(parsed, dict):
        raise SpecError("that JSON isn't an object")
    if parsed.get("openapi") or parsed.get("swagger") or isinstance(parsed.get("paths"), dict):
        paths = post_paths(parsed)
        if not paths:
            raise SpecError("that OpenAPI document has no request that takes JSON")
        chosen = path if path in paths else (paths[0] if len(paths) == 1 else None)
        one = None
        if chosen:
            one = {**parsed, "paths": {chosen: parsed["paths"][chosen]}}
        return {"form": "openapi", "doc": one, "paths": paths, "chosen": chosen}
    return {"form": "example", "doc": doc_from_example(parsed), "paths": ["/generate"]}


def _as_api_block(spec: dict, service: str, values: dict, schema: dict) -> dict:
    block = spec.pop("router")
    spec["api"] = {"service": service, **block,
                   **({"values": values} if values else {}), "schema": schema}
    caps = dict(spec.get("capabilities") or {})
    caps["backends"] = ["api"]
    spec["capabilities"] = caps
    return spec


def propose(service: str, model: str, text: str, kind: str = "video", path: str | None = None,
            base: dict | None = None) -> dict:
    """{"proposal": target.json, "mapped", "unplaced", "warnings", "form", "paths", "schema",
    "auth"?} for a model on a provider. `paths`, with no proposal: an OpenAPI document with several
    requests, one to be chosen."""
    if not (model or "").strip():
        raise SpecError("model is the id the provider knows it by")
    defs = PR.definitions()
    if service not in defs:
        raise SpecError(f"there's no provider called {service}")
    read_ = read(text, path)
    if read_["doc"] is None:
        return {"form": read_["form"], "paths": read_["paths"], "proposal": None}
    doc = read_["doc"]
    # the proposer names a model by provider/model; what it writes of it is overwritten below
    named = model if "/" in model else f"{service}/{model}"
    try:
        made = RI.propose_image(named, doc) if kind == "image" else RI.propose(named, doc, base=base)
        schema = RI.schema_fields(doc)
    except RI.RouterInspectError as e:
        raise SpecError(str(e)) from None
    spec = made["proposal"]
    block = TG.hosted_block(spec)
    block["model"] = model
    for gone in ("provider", "fallback"):
        block.pop(gone, None)
    # the model's id goes in the provider's own steps
    schema["fields"] = [f for f in schema["fields"] if f["path"] != "model"]
    schema["required"] = [f for f in schema["required"] if f != "model"]
    block.get("arguments", {}).pop("model", None)
    values = {}
    endpoint = (defs[service].get("endpoints") or {}).get(kind)
    if endpoint:
        values["endpoint"] = endpoint
    values["type"] = kind
    spec = _as_api_block(spec, service, values, schema)
    spec["id"] = re.sub(r"[^a-z0-9_]+", "_", f"{service}_{model}".lower()).strip("_")[:40].rstrip("_")
    spec["label"] = f"{model} ({defs[service].get('label') or service})"
    spec["short"] = model.split("/")[-1] if "/" in model else model
    spec["draft"] = True
    warnings = list(made.get("warnings") or [])
    placed = {p.strip() for m in (block.get("inputs") or {}).values() for p in PV_where(m).split(",")}
    placed |= set(block.get("arguments") or {})
    left = sorted(f["path"] for f in schema["fields"] if "." not in f["path"] and f["path"] not in placed)
    if left:
        warnings.append(f"Nothing goes in {', '.join(left)} yet: look at each under Fields. A "
                        f"resolution needs its values listed before a proxy can ask for a small one.")
    if read_["form"] != "openapi":
        warnings.append("Read from an example: its limits and required fields aren't known. Check the "
                        "Fields tab, then probe one take.")
    return {"proposal": spec, "mapped": made.get("mapped") or {},
            "unplaced": [f for f in made.get("unplaced") or [] if f != "model"], "warnings": warnings,
            "form": read_["form"], "paths": read_["paths"], "schema": schema,
            **({"auth": read_["auth"]} if read_.get("auth") else {})}
