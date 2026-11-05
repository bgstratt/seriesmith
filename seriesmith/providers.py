"""
providers -- who serves a hosted model that isn't on Comfy Router: where it is, how it's told who
is asking, how files get in, and how a job is followed (docs/DESIGN.md, section 9). A definition
is plain data, run by backends/http.py:

    {
      "id": "atlas", "label": "Atlas Cloud",
      "base_url": "https://api.atlascloud.ai/api/v1",
      "auth": {"type": "bearer"},            # or {"type": "header", "name": "xi-api-key", "prefix": ""}
                                             # or {"type": "query", "name": "key"}
      "hosts": ["other.host"],               # more hosts that may have the key (default: base_url's)
      "headers": {"X-Version": "1"},         # sent with every request to those hosts
      "parallel": 3,                         # jobs at once
      "endpoints": {"video": "generateVideo",    # {endpoint} in a step, by what a model makes
                    "video_text": "..."},        # and for a shot with no pictures, if that differs
      "files": {"via": "upload",             # or "base64", "datauri"
                "steps": [{"method": "POST", "url": "/model/uploadMedia",
                           "multipart": {"file": "$file"}, "take": {"url": "url"}}],
                "value": "$url"},            # or in two: ask where, then put it there (higgsfield.json):
                                             # {"json": {"content_type": "$mime"}, "take": {...}}, then
                                             # {"method": "PUT", "url": "$to", "headers": "$its_headers",
                                             #  "body": "$file", "key": false}
      "steps": [
        {"method": "POST", "url": "/model/{endpoint}", "json": {"model": "$model", "...": "$args"},
         "take": {"task": ["data.id", "id"]}},
        {"method": "GET", "url": "/model/prediction/{task}",
         "until": {"status": "data.status", "done": ["completed"], "failed": ["failed"],
                   "error": "data.error", "every": 5, "timeout": 3600}}
      ],
      "result": {"files": "data.outputs"},   # or {"url": "/videos/{task}/content", "auth": true, "type": "video"}
      "voices": {"id": "voice_id", "name": "name", "preview": "preview_url", "browse": "https://...",
                 "lists": [{"id": "own", "label": "Its own voices", "url": "/v1/voices", "list": "voices",
                            "free": true}]}
                                             # where its speakers are listed, if it has them; a `free`
                                             # list can be read with no key, to hear them first
    }

Definitions live on this machine, beside the settings, with their keys: a show names a provider
and never defines one, so a show from someone else can't send a key to a host of its choosing.
Keys are in the settings (`provider_keys`) or the environment (SERIESMITH_KEY_<ID>), and never
leave through a listing. Some ship as untested drafts (presets/providers/). Stdlib only.
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse

from seriesmith.core import fileio as F

DIR = "providers"
SHIPPED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "presets", "providers")
AUTH_TYPES = ("bearer", "header", "query")
FILE_WAYS = ("upload", "base64", "datauri", "multipart")


class ProviderError(ValueError):
    pass


def user_dir() -> str:
    from seriesmith import settings as S
    return os.path.join(os.path.dirname(os.path.abspath(S.settings_path())), DIR)


def env_name(pid: str) -> str:
    return "SERIESMITH_KEY_" + re.sub(r"[^A-Z0-9]", "_", pid.upper())


def _read(folder: str) -> dict[str, dict]:
    out = {}
    if not os.path.isdir(folder):
        return out
    for name in sorted(os.listdir(folder)):
        if name.endswith(".json"):
            d = F.read_json_or(os.path.join(folder, name), {}, want=dict)
            if d.get("id") == name[:-5]:
                out[d["id"]] = d
    return out


def definitions() -> dict[str, dict]:
    """Every provider by id: what ships, this machine's own over it."""
    return {**{k: {**v, "source": "shipped"} for k, v in _read(SHIPPED).items()},
            **{k: {**v, "source": "yours"} for k, v in _read(user_dir()).items()}}


def catalog(pid: str) -> list[dict]:
    """The models a shipped provider has written down (presets/providers/<id>.models.json): each
    {"id", "label", "kind", "fields": JSON Schema properties, "required"?, "inputs"?, "models"?,
    "note"?}. Read from its docs, so what they state and no more; none proved unless said."""
    got = F.read_json_or(os.path.join(SHIPPED, f"{pid}.models.json"), {}, want=dict)
    return list(got.get("models") or [])


def problems(d: dict) -> list[str]:
    """What's wrong with a definition ([]: nothing)."""
    out = []
    pid = d.get("id")
    if not isinstance(pid, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", pid):
        out.append("id must be lower-case letters, numbers, - and _")
    base = str(d.get("base_url") or "")
    u = urllib.parse.urlparse(base)
    if not u.hostname or u.scheme not in ("http", "https"):
        out.append("base_url must be a web address")
    elif u.scheme == "http" and u.hostname not in ("127.0.0.1", "localhost"):
        out.append("base_url must be https: the key goes to it")
    auth = d.get("auth")
    if not isinstance(auth, dict) or auth.get("type") not in AUTH_TYPES:
        out.append(f"auth.type must be one of {', '.join(AUTH_TYPES)}")
    elif auth["type"] in ("header", "query") and not auth.get("name"):
        out.append(f"auth.name says which {auth['type']} takes the key")
    extra = d.get("headers")
    if extra is not None and not (isinstance(extra, dict) and all(isinstance(v, (str, int)) for v in extra.values())):
        out.append("headers must be names and their values")
    steps = d.get("steps")
    if not isinstance(steps, list) or not steps:
        out.append("steps must list at least one request")
    else:
        for i, s in enumerate(steps, 1):
            if not isinstance(s, dict) or not s.get("url"):
                out.append(f"step {i} needs a url")
                continue
            if "webhook" in json.dumps(s).lower():
                out.append(f"step {i} uses a webhook: nothing can call back to this machine")
            until = s.get("until")
            if until is not None and not (isinstance(until, dict) and until.get("status")
                                          and until.get("done")):
                out.append(f"step {i}: until needs a status field and its done values")
    result = d.get("result")
    last = (steps or [{}])[-1] if isinstance(steps, list) else {}
    bytes_back = isinstance(last, dict) and last.get("response") == "bytes"
    if not bytes_back and not (isinstance(result, dict) and (result.get("files") or result.get("url"))):
        out.append("result must say where the files are (files, or url), unless the last step answers with the file")
    files = d.get("files")
    if files is not None:
        if not isinstance(files, dict) or files.get("via") not in FILE_WAYS:
            out.append(f"files.via must be one of {', '.join(FILE_WAYS)}")
        elif files["via"] == "upload" and not files.get("steps"):
            out.append("files.steps says how a file is uploaded")
    return out


def save(d: dict) -> str:
    """Save a definition for this machine. ProviderError saying what's wrong; the path."""
    wrong = problems(d)
    if wrong:
        raise ProviderError(wrong[0])
    os.makedirs(user_dir(), exist_ok=True)
    path = os.path.join(user_dir(), f"{d['id']}.json")
    F.write_json(path, {k: v for k, v in d.items() if k != "source"})
    return path


def delete(pid: str) -> bool:
    """Remove this machine's own (what ships comes back in its place, if any)."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", pid or ""):
        return False
    path = os.path.join(user_dir(), f"{pid}.json")
    if not os.path.isfile(path):
        return False
    os.remove(path)
    return True


def key_of(pid: str, settings=None, env=None) -> str | None:
    """A provider's key: the environment's, else the settings'."""
    env = os.environ if env is None else env
    if env.get(env_name(pid)):
        return env[env_name(pid)]
    if settings is None:
        from seriesmith.settings import load_settings
        settings = load_settings()
    return (getattr(settings, "provider_keys", None) or {}).get(pid) or None


def voices_of(d: dict) -> dict | None:
    """How a provider's speakers can be listed, for the editor; None when it has none to list."""
    how = d.get("voices")
    lists = how.get("lists") if isinstance(how, dict) else None
    if not lists:
        return None
    return {"browse": how.get("browse") or "",
            "lists": [{"id": x.get("id"), "label": x.get("label") or x.get("id"), "free": bool(x.get("free")),
                       "searches": bool(x.get("search_param"))} for x in lists]}


def listing(settings=None, env=None) -> list[dict]:
    """Every provider, for the editor: whether it has a key, and never the key."""
    env = os.environ if env is None else env
    out = []
    for pid, d in definitions().items():
        out.append({"id": pid, "label": d.get("label") or pid, "base_url": d.get("base_url"),
                    "source": d["source"], "untested": bool(d.get("untested")),
                    "has_key": bool(key_of(pid, settings, env)),
                    "key_from_env": env_name(pid) if env.get(env_name(pid)) else None,
                    "env_name": env_name(pid), "endpoints": d.get("endpoints") or {},
                    "catalog": [{k: m.get(k) for k in ("id", "label", "kind", "note") if m.get(k)} for m in catalog(pid)],
                    "docs": d.get("docs") or "", "key_hint": d.get("key_hint") or "",
                    "key_url": d.get("key_url") or "",
                    "voices": voices_of(d),
                    "definition": {k: v for k, v in d.items() if k != "source"}})
    return out
