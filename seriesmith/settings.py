"""
settings — the machine's own settings: where the backends are and the Comfy
API key. Never in the series config, which gets shared.

Read from a JSON file, then the environment over it:

    file   %APPDATA%\\seriesmith\\settings.json (Windows), else
           ~/.config/seriesmith/settings.json; SERIESMITH_SETTINGS names another

    {"local_url":   "http://127.0.0.1:8189",     comfy-api-proxy beside your ComfyUI
     "comfyui_url": "http://127.0.0.1:8188",     ComfyUI itself (model lists, node checks)
     "cloud_url":   "https://cloud.comfy.org",
     "api_key":     "comfyui-...",               better kept in COMFY_API_KEY
     "deployments": {"minimax_h3_ref2va": "https://<build>.run.comfy.app"}}

    environment   SERIESMITH_LOCAL_URL, SERIESMITH_COMFYUI_URL, SERIESMITH_CLOUD_URL,
                  COMFY_API_KEY

Stdlib only.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

LOCAL_URL = "http://127.0.0.1:8189"
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

    def describe(self) -> dict:
        """The settings without the key itself (for listings and logs)."""
        return {"local_url": self.local_url, "comfyui_url": self.comfyui_url,
                "cloud_url": self.cloud_url, "api_key": "set" if self.api_key else None,
                "deployments": dict(self.deployments), "path": self.path}


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
        path=path)
