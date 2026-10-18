"""
The Features window's routes, for both hosts (seriesmith.features: what can be
added; seriesmith.installer: putting it in):

    GET  /seriesmith/features          every feature, its items and whether each
                                       is installed here; where things would go;
                                       the installer's progress
    GET  /seriesmith/features/sizes    each download's size ({url: bytes | null}),
                                       asked of its server once (HEAD), apart since
                                       it's slow
    POST /seriesmith/features/install  {features: [id], files: [name], classes: [node
                                       class]}: what isn't installed yet, queued
    POST /seriesmith/features/cancel   stop after the current item (a download's
                                       .part is kept and resumes)

Files are asked for by name only: the server downloads only URLs the code
records (features.known_files), never one the page sends.
"""
from __future__ import annotations

import asyncio
import threading
import urllib.error
import urllib.request

from aiohttp import web

from seriesmith import features as FT
from seriesmith import installer as INS

_SIZES: dict[str, int | None] = {}


def head_size(url: str, token: str | None) -> int | None:
    """A download's size from its server (HEAD, redirects followed); None when
    it won't say (or refuses: a gated file without a token)."""
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "seriesmith"})
    if token and "huggingface.co" in url:
        req.add_header("Authorization", f"Bearer {token}")
    from seriesmith.backends import tls
    try:
        with urllib.request.urlopen(req, timeout=20, context=tls() if url.startswith("https") else None) as r:
            n = r.headers.get("Content-Length")
            return int(n) if n and n.isdigit() else None
    except (urllib.error.URLError, OSError, ValueError):
        return None


def feature_routes(settings, make_context, in_comfyui: bool = False) -> list[tuple]:
    """[(method, path, handler)] over this host's settings; `make_context()`
    gives an api.Context (readiness, ComfyUI's /object_info)."""
    from seriesmith import api as A

    def place() -> INS.Place:
        if in_comfyui:
            return INS.place_in_comfyui()
        return INS.place_from_url(settings.local_comfyui, settings.comfyui_dir)

    def changed():
        # a file or pack went in: readiness asks ComfyUI again
        A._READY.clear()

    installer = INS.Installer(place, token=lambda: settings.hf_token, on_change=changed)

    def look() -> dict:
        ctx = make_context()
        p = place()
        try:
            readiness = A.target_readiness(ctx)
        except Exception:                                 # noqa: BLE001  ComfyUI away
            readiness = {}
        try:
            info = ctx.comfy.object_info()
        except Exception:                                 # noqa: BLE001
            info = None
        env = INS.env_for(p, readiness, info)
        feats = FT.catalog()
        return {"groups": [{"id": g, "label": label, "about": about} for g, label, about in FT.GROUPS],
                "features": FT.status(feats, env), "place": p.to_json(),
                "hf_token": bool(settings.hf_token), "job": installer.state()}

    async def features(request: web.Request) -> web.Response:
        return web.json_response(await asyncio.get_running_loop().run_in_executor(None, look))

    async def sizes(request: web.Request) -> web.Response:
        urls = sorted({i.url for f in FT.catalog() for i in f.items if i.kind == "model" and i.url})
        todo = [u for u in urls if u not in _SIZES]

        def ask():
            lock = threading.Lock()

            def one(u):
                n = head_size(u, settings.hf_token)
                with lock:
                    _SIZES[u] = n
            threads = [threading.Thread(target=one, args=(u,), daemon=True) for u in todo]
            for t in threads:
                t.start()
            for t in threads:
                t.join(30)
        if todo:
            await asyncio.get_running_loop().run_in_executor(None, ask)
        return web.json_response({"sizes": {u: _SIZES.get(u) for u in urls}})

    async def install(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except ValueError:
            return web.json_response({"error": "the body must be JSON"}, status=400)
        if not isinstance(body, dict):
            return web.json_response({"error": "the body must be an object"}, status=400)

        def go():
            ctx = make_context()
            p = place()
            try:
                readiness = A.target_readiness(ctx)
            except Exception:                             # noqa: BLE001
                readiness = {}
            try:
                info = ctx.comfy.object_info()
            except Exception:                             # noqa: BLE001
                info = None
            items, skipped = FT.resolve(body.get("features") or [], body.get("files") or [],
                                        body.get("classes") or [], env=INS.env_for(p, readiness, info))
            if items and p.why_not and any(i.kind in ("model", "pack") for i in items):
                return {"error": p.why_not, "skipped": skipped}, 409
            return {"job": installer.start(items) if items else installer.state(),
                    "queued": [i.key for i in items], "skipped": skipped}, 200
        out, status = await asyncio.get_running_loop().run_in_executor(None, go)
        return web.json_response(out, status=status)

    async def cancel(request: web.Request) -> web.Response:
        return web.json_response({"job": installer.cancel()})

    return [("GET", "/seriesmith/features", features),
            ("GET", "/seriesmith/features/sizes", sizes),
            ("POST", "/seriesmith/features/install", install),
            ("POST", "/seriesmith/features/cancel", cancel)]


__all__ = ["feature_routes", "head_size"]
