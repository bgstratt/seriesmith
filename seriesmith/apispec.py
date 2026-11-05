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
        if value and all(isinstance(v, dict) for v in value):
            return {"type": "array", "items": _schema_of_items(value)}
        return {"type": "array", "items": _schema_of(value[0]) if value else {"type": "string"}}
    if isinstance(value, dict):
        return {"type": "object", "properties": {k: _schema_of(v) for k, v in value.items()}}
    return {}


def _schema_of_items(items: list[dict]) -> dict:
    """One schema for a list's objects: an example's list is often of different kinds (a text, then
    pictures), so every item counts, and its `type` and `role` say which values that list takes."""
    props: dict = {}
    for item in items:
        for k, v in item.items():
            if k not in props:
                props[k] = _schema_of(v)
            if k in ("type", "role") and isinstance(v, str):
                seen = props[k].setdefault("enum", [])
                if v not in seen:
                    seen.append(v)
    return {"type": "object", "properties": props}


def doc_from_example(body: dict, path: str = "/generate") -> dict:
    """The OpenAPI document an example request stands for. Nothing is marked required: an example
    doesn't say."""
    return {"paths": {path: {"post": {"requestBody": {"content": {"application/json": {
        "schema": _schema_of(body)}}}}}}}


def curl_in(text: str) -> str | None:
    """The cURL command in pasted text, and only it: docs often show one inside a little script
    (`response=$(curl ... --data '{...}')`, then a line with grep). None when there isn't one."""
    text = (text or "").strip()
    if text.startswith(("{", "[")):
        return None
    m = re.search(r"(?:^|(?<=[\s(]))curl\s", text, re.IGNORECASE)
    if not m:
        return None
    at = m.start()
    quote, i = "", at
    while i < len(text):
        c = text[i]
        if quote:
            if c == "\\" and quote == '"':
                i += 1
            elif c == quote:
                quote = ""
        elif c in "'\"":
            quote = c
        elif c == "\\":
            i += 1                               # a line carried on, or an escaped character
        elif c in ")|;&":
            break
        elif c == "\n":
            # a line that isn't carried on ends it, unless the next goes on with an option
            if not re.match(r"\s*-", text[i + 1:]):
                break
        i += 1
    return text[at:i].strip()


def parse_curl(text: str) -> dict:
    """{"method", "url", "body", "auth"} of a cURL line, the auth as how and never the key."""
    text = curl_in(text) or text
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
    if curl_in(text):
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


def doc_of_entry(entry: dict) -> dict:
    """The OpenAPI document a provider's catalog entry stands for."""
    return {"openapi": "3.0.0", "paths": {"/generate": {"post": {"requestBody": {"content": {"application/json": {
        "schema": {"type": "object", "properties": entry["fields"], "required": entry.get("required") or []}}}}}}}}


def _model_fields(d: dict) -> set[str]:
    """The fields a provider's steps fill with the model's id."""
    out = set()
    for step in d.get("steps") or []:
        for body in (step.get("json"), step.get("multipart")):
            if isinstance(body, dict):
                out |= {k for k, v in body.items() if v == "$model"}
    return out


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
    entry = None
    if not (text or "").strip():
        # nothing pasted: what the provider's catalog has written down of this model
        entry = next((m for m in PR.catalog(service) if m["id"] == model), None)
        if entry:
            kind = entry.get("kind") or kind
    read_ = ({"form": "catalog", "doc": doc_of_entry(entry), "paths": ["/generate"]} if entry
             else read(text, path))
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
    # Comfy's own way into the Seedance library, named by the model's prefix: a provider's own
    # definition says how its pictures go in
    if (block.get("inputs") or {}).get("via") == "seedance":
        del block["inputs"]["via"]
    # the model's id goes in the provider's own steps
    named_in_steps = {"model"} | _model_fields(defs[service])
    schema["fields"] = [f for f in schema["fields"] if f["path"] not in named_in_steps]
    schema["required"] = [f for f in schema["required"] if f not in named_in_steps]
    for gone in named_in_steps:
        block.get("arguments", {}).pop(gone, None)
    values = {}
    endpoint = (defs[service].get("endpoints") or {}).get(kind)
    if endpoint:
        values["endpoint"] = endpoint
    values["type"] = kind
    if entry:
        block.get("inputs", {}).update(entry.get("inputs") or {})
        if entry.get("models"):
            block["models"] = entry["models"]
        if "first" in block.get("inputs", {}) and "references" in block["inputs"]:
            # it does both: only a model that needs one has it as a must
            spec.get("recipe", {}).pop("keyframe_required", None)
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
    if entry and entry.get("note"):
        warnings.append(entry["note"])
    if entry:
        warnings.append("From what the provider's docs state, and not yet proved by a real take on this model.")
    if read_["form"] not in ("openapi", "catalog"):
        warnings.append("Read from an example: its limits and required fields aren't known. Check the "
                        "Fields tab, then probe one take.")
    return {"proposal": spec, "mapped": made.get("mapped") or {},
            "unplaced": [f for f in made.get("unplaced") or [] if f not in named_in_steps], "warnings": warnings,
            "form": read_["form"], "paths": read_["paths"], "schema": schema,
            **({"auth": read_["auth"]} if read_.get("auth") else {})}
