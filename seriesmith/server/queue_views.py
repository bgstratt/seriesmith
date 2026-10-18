"""
The queue's own routes, for both hosts (`seriesmith serve` and ComfyUI's,
server/comfyui.py): the Jobs window (GET /seriesmith/jobs, POST
/seriesmith/jobs/{action}), "Render on" (GET /seriesmith/backends), the
Settings window (GET / PUT /seriesmith/settings, POST /seriesmith/sdk/install:
comfy-sdk put in for Cloud and Router, seriesmith.sdk) and GET /seriesmith/info.
They read the host's settings and runner (standalone.start_queue), so they
live beside the API rather than in it.
"""
from __future__ import annotations

import asyncio

from aiohttp import web

from seriesmith import sdk as SDK
from seriesmith.settings import load_settings, settings_path

# the backends that run through comfy-sdk (Comfy Cloud, deployments, Router)
SDK_KINDS = ("cloud", "deployment", "router")


def queue_routes(settings, runner, connected=lambda: False) -> list[tuple]:
    """[(method, path, handler)] over this host's `settings` and `runner`;
    connected() says whether the page's ComfyUI answers (for /info)."""
    queue, backends = runner.queue, runner.backends

    async def info(request: web.Request) -> web.Response:
        from seriesmith import __version__
        return web.json_response({"version": __version__, "settings": settings.describe(),
                                  "comfy_connected": connected()})

    async def jobs(request: web.Request) -> web.Response:
        return web.json_response(queue.list())

    async def job_action(request: web.Request) -> web.Response:
        what = request.match_info["action"]
        try:
            body = await request.json()
        except ValueError:
            return web.json_response({"error": "the body must be JSON"}, status=400)
        try:
            if what == "cancel":
                queue.cancel(str(body["id"]))
            elif what == "move":
                queue.move(str(body["id"]), int(body["index"]))
            elif what == "pause":
                queue.pause(str(body["lane"]), bool(body.get("paused", True)))
            elif what == "retry":
                await asyncio.get_running_loop().run_in_executor(None, queue.retry, str(body["id"]))
            elif what == "paid-reset":
                queue.paid_count = 0
            else:
                return web.json_response({"error": f"no action {what!r}"}, status=404)
        except KeyError as e:
            return web.json_response({"error": f"no such job or field: {e}"}, status=404)
        except (ValueError, TypeError) as e:
            return web.json_response({"error": str(e)}, status=409)
        return web.json_response(queue.list())

    async def backend_list(request: web.Request) -> web.Response:
        """Each backend and whether it answers (asked off the event loop)."""
        loop = asyncio.get_running_loop()

        def look():
            no_sdk = None if SDK.have() else (
                "Comfy's SDK is being installed" if SDK.state()["status"] == "installing"
                else "Comfy's SDK isn't installed (Settings: Install)")
            return [{"name": n, "kind": b.kind,
                     "down": (no_sdk if b.kind in SDK_KINDS else None) or b.ping(),
                     "where": getattr(b, "base_url", None) or getattr(b, "cloud_url", "")}
                    for n, b in backends.items()]
        return web.json_response({"backends": await loop.run_in_executor(None, look),
                                  "api_key": bool(settings.api_key)})

    async def settings_get(request: web.Request) -> web.Response:
        from seriesmith.settings import from_env
        return web.json_response({"settings": settings.describe(), "file": settings_path(),
                                  "from_env": from_env(), "sdk": SDK.state()})

    async def sdk_install(request: web.Request) -> web.Response:
        """comfy-sdk installed into this Python, in the background (the
        Settings window's Install): its state, to poll GET /seriesmith/settings."""
        return web.json_response({"sdk": SDK.install()})

    async def settings_put(request: web.Request) -> web.Response:
        """Save the settings file, then use it: the backends are made again
        from it (a job already running keeps the one it started on)."""
        from seriesmith.backends import available
        from seriesmith.settings import FIELDS, from_env, save_settings
        try:
            body = await request.json()
        except ValueError:
            return web.json_response({"error": "the body must be JSON"}, status=400)
        if not isinstance(body, dict):
            return web.json_response({"error": "the body must be an object"}, status=400)
        try:
            save_settings({k: v for k, v in body.items() if k in FIELDS})
            fresh = load_settings()
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=400)
        for k in ("local_url", "comfyui_url", "cloud_url", "api_key", "hf_token", "ffmpeg_dir",
                  "comfyui_dir", "deployments", "path",
                  "paid_limit", "local_via", "default_targets", "detected_targets"):
            setattr(settings, k, getattr(fresh, k))
        queue.paid_limit = settings.paid_limit
        from seriesmith import ff as FF
        FF.forget()                                       # ffmpeg_dir may have changed
        backends.clear()
        backends.update(available(settings))
        # a key set, and comfy-sdk not here (ComfyUI's Python): put it in now
        sdk = SDK.ensure(settings)
        return web.json_response({"settings": settings.describe(), "file": settings_path(),
                                  "from_env": from_env(), "sdk": sdk})

    return [("GET", "/seriesmith/info", info),
            ("GET", "/seriesmith/jobs", jobs),
            ("POST", "/seriesmith/jobs/{action}", job_action),
            ("GET", "/seriesmith/backends", backend_list),
            ("GET", "/seriesmith/settings", settings_get),
            ("PUT", "/seriesmith/settings", settings_put),
            ("POST", "/seriesmith/sdk/install", sdk_install)]
