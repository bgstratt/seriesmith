"""
settings — the machine's own settings: where the backends are and the Comfy
API key. Never in the series config, which gets shared.

Read from a JSON file, then the environment over it:

    file   %APPDATA%\\seriesmith\\settings.json (Windows), else
           ~/.config/seriesmith/settings.json; SERIESMITH_SETTINGS names another

    {"comfyui_url": "http://127.0.0.1:8188",     your ComfyUI: local renders, model lists
     "local_via":   "comfyui",                   "proxy": local renders through
     "local_url":   "http://127.0.0.1:8189",     comfy-api-proxy at local_url instead
     "cloud_url":   "https://cloud.comfy.org",
     "api_key":     "comfyui-...",               better kept in COMFY_API_KEY
     "deployments": {"minimax_h3_ref2va": "https://<build>.run.comfy.app"},
     "enabled_drafts": ["veo_3_1_lite"],          built-in draft targets switched on
     "target_limits": {"ltx2": {"size": {"multiple": 32}}},
                                                  this machine's changes to built-in
                                                  targets' limits (seriesmith.limits)
     "default_targets":  {"video": "ltx2"},      the model a series without one uses
     "detected_targets": {"video": "ltx2", "image": "krea2"}}
                                                  what seriesmith found installed in
                                                  ComfyUI (edit.detect_defaults); the
                                                  default when default_targets hasn't one

    environment   SERIESMITH_LOCAL_URL, SERIESMITH_COMFYUI_URL, SERIESMITH_CLOUD_URL,
                  SERIESMITH_LOCAL_VIA, COMFY_API_KEY

Stdlib only.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

LOCAL_URL = "http://127.0.0.1:8189"
LOCAL_VIA = ("comfyui", "proxy")
DEFAULT_KINDS = ("video", "image")
COMFYUI_URL = "http://127.0.0.1:8188"
CLOUD_URL = "https://cloud.comfy.org"


@dataclass
class Settings:
    local_url: str = LOCAL_URL
    comfyui_url: str = COMFYUI_URL
    cloud_url: str = CLOUD_URL
    api_key: str | None = None
    deployments: dict[str, str] = field(default_factory=dict)
    path: str | None = None          # the file these came from, if any
    # paid runs (Cloud, Router, a deployment) one server session may queue; None: no cap
    paid_limit: int | None = None
    # built-in targets that ship as drafts (an untested Router model) and are
    # switched on here, for every show (the editor's Enable)
    enabled_drafts: list[str] = field(default_factory=list)
    # this machine's changes to built-in targets' limits: {id: seriesmith.limits
    # sections}, applied as the target loads (the editor's Limits form)
    target_limits: dict[str, dict] = field(default_factory=dict)
    # how local renders reach ComfyUI: "comfyui" (its own API, at comfyui_url)
    # or "proxy" (comfy-api-proxy at local_url)
    local_via: str = "comfyui"
    # the video / image model a series that names none uses on this machine:
    # the user's choice, else what was found installed, else the built-in
    default_targets: dict[str, str] = field(default_factory=dict)
    detected_targets: dict[str, str] = field(default_factory=dict)
    # not a setting: the ComfyUI this server runs inside (server/comfyui.py),
    # which local renders go to whatever comfyui_url says
    host_url: str | None = None

    @property
    def local_comfyui(self) -> str:
        """The ComfyUI local renders go to straight (local_via "comfyui")."""
        return self.host_url or self.comfyui_url

    def describe(self) -> dict:
        """The settings without the key itself (for listings and logs)."""
        return {"local_url": self.local_url, "comfyui_url": self.comfyui_url,
                "cloud_url": self.cloud_url, "api_key": "set" if self.api_key else None,
                "deployments": dict(self.deployments), "path": self.path,
                "paid_limit": self.paid_limit, "enabled_drafts": list(self.enabled_drafts),
                "target_limits": dict(self.target_limits), "local_via": self.local_via,
                "default_targets": dict(self.default_targets),
                "detected_targets": dict(self.detected_targets)}


def settings_path() -> str:
    explicit = os.environ.get("SERIESMITH_SETTINGS")
    if explicit:
        return explicit
    if os.name == "nt" and os.environ.get("APPDATA"):
        return os.path.join(os.environ["APPDATA"], "seriesmith", "settings.json")
    return os.path.join(os.path.expanduser("~"), ".config", "seriesmith", "settings.json")


def load_settings(path: str | None = None, env: dict | None = None) -> Settings:
    """The settings file (if there is one) with the environment over it."""
    env = os.environ if env is None else env
    path = path or settings_path()
    data: dict = {}
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            try:
                data = json.load(fh)
            except json.JSONDecodeError as e:
                raise ValueError(f"{path} is not valid JSON: {e}") from None
        if not isinstance(data, dict):
            raise ValueError(f"{path} must hold a JSON object")
    else:
        path = None
    deployments = data.get("deployments") or {}
    if not isinstance(deployments, dict):
        raise ValueError("settings: deployments must map a target id to its URL")
    return Settings(
        local_url=(env.get("SERIESMITH_LOCAL_URL") or data.get("local_url") or LOCAL_URL).rstrip("/"),
        comfyui_url=(env.get("SERIESMITH_COMFYUI_URL") or data.get("comfyui_url")
                     or COMFYUI_URL).rstrip("/"),
        cloud_url=(env.get("SERIESMITH_CLOUD_URL") or data.get("cloud_url") or CLOUD_URL).rstrip("/"),
        api_key=env.get("COMFY_API_KEY") or data.get("api_key") or None,
        deployments={str(k): str(v).rstrip("/") for k, v in deployments.items()},
        path=path,
        paid_limit=_paid_limit(data.get("paid_limit")),
        enabled_drafts=[str(x) for x in data.get("enabled_drafts") or [] if isinstance(x, str)],
        target_limits={str(k): v for k, v in (data.get("target_limits") or {}).items()
                       if isinstance(v, dict)} if isinstance(data.get("target_limits"), dict) else {},
        local_via=_local_via(env.get("SERIESMITH_LOCAL_VIA") or data.get("local_via")),
        default_targets=_by_kind(data.get("default_targets")),
        detected_targets=_by_kind(data.get("detected_targets")))


def _local_via(v) -> str:
    return v if v in LOCAL_VIA else LOCAL_VIA[0]


def _by_kind(v) -> dict[str, str]:
    """{kind: target id} for the kinds that have a default, the rest dropped."""
    if not isinstance(v, dict):
        return {}
    return {k: t for k, t in v.items() if k in DEFAULT_KINDS and isinstance(t, str) and t}


def _paid_limit(v) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else None


FIELDS = ("local_url", "comfyui_url", "cloud_url", "api_key", "deployments", "paid_limit",
          "enabled_drafts", "target_limits", "local_via", "default_targets", "detected_targets")
ENV_NAMES = {"local_url": "SERIESMITH_LOCAL_URL", "comfyui_url": "SERIESMITH_COMFYUI_URL",
             "cloud_url": "SERIESMITH_CLOUD_URL", "api_key": "COMFY_API_KEY",
             "local_via": "SERIESMITH_LOCAL_VIA"}


def from_env(env: dict | None = None) -> dict[str, str]:
    """The settings the environment sets ({field: its variable}): those win over
    the file, so the editor can't change them."""
    env = os.environ if env is None else env
    return {k: v for k, v in ENV_NAMES.items() if env.get(v)}


def save_settings(updates: dict, path: str | None = None) -> str:
    """Write `updates` into the settings file (made if missing; its other keys
    kept). A field absent from `updates` is left as it is; an empty URL or
    key, or null, removes it (the default, or no key). `deployments` replaces
    the whole map. ValueError for anything else; returns the file's path."""
    path = path or settings_path()
    bad = sorted(set(updates) - set(FIELDS))
    if bad:
        raise ValueError(f"not a setting: {', '.join(bad)}")
    data: dict = {}
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            try:
                data = json.load(fh)
            except json.JSONDecodeError as e:
                raise ValueError(f"{path} is not valid JSON: {e}") from None
        if not isinstance(data, dict):
            raise ValueError(f"{path} must hold a JSON object")
    for k, v in updates.items():
        if k == "paid_limit":
            if v in (None, ""):
                data.pop(k, None)
            elif isinstance(v, bool) or not isinstance(v, int) or v < 0:
                raise ValueError("paid_limit: a whole number of runs (0 or more), or empty for none")
            else:
                data[k] = v
            continue
        if k == "enabled_drafts":
            if v in (None, []):
                data.pop(k, None)
            elif not isinstance(v, list) or not all(isinstance(x, str) and x for x in v):
                raise ValueError("enabled_drafts: a list of target ids")
            else:
                data[k] = sorted(set(v))
            continue
        if k == "target_limits":
            if v in (None, {}):
                data.pop(k, None)
            elif not isinstance(v, dict) or not all(isinstance(x, dict) for x in v.values()):
                raise ValueError("target_limits: {target id: its limits}")
            else:
                data[k] = {str(t): x for t, x in v.items() if x}
                if not data[k]:
                    data.pop(k)
            continue
        if k == "local_via":
            if v in (None, ""):
                data.pop(k, None)
            elif v not in LOCAL_VIA:
                raise ValueError(f"local_via: one of {', '.join(LOCAL_VIA)}")
            else:
                data[k] = v
            continue
        if k in ("default_targets", "detected_targets"):
            if v in (None, {}):
                data.pop(k, None)
                continue
            if not isinstance(v, dict) or set(v) - set(DEFAULT_KINDS) or                     not all(t is None or isinstance(t, str) for t in v.values()):
                raise ValueError(f"{k}: {{kind: target id}}, the kinds {', '.join(DEFAULT_KINDS)}")
            data[k] = {kind: t for kind, t in v.items() if t}
            if not data[k]:
                data.pop(k)
            continue
        if k == "deployments":
            if v in (None, {}):
                data.pop(k, None)
                continue
            if not isinstance(v, dict):
                raise ValueError("deployments must map a target id to its URL")
            for t, u in v.items():
                if not isinstance(u, str) or not u.startswith(("http://", "https://")):
                    raise ValueError(f"deployment {t}: its URL must start with http:// or https://")
            data[k] = {str(t): u.rstrip("/") for t, u in v.items()}
            continue
        if v in (None, ""):
            data.pop(k, None)
            continue
        if not isinstance(v, str):
            raise ValueError(f"{k} must be text")
        v = v.strip()
        if k != "api_key" and not v.startswith(("http://", "https://")):
            raise ValueError(f"{k}: a URL starting with http:// or https://")
        data[k] = v.rstrip("/") if k != "api_key" else v
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)
    return path
