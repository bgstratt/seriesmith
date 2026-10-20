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

import threading
import urllib.error
import urllib.request


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


# what feature_routes registers (server/routes.all_paths)
PATHS = [("GET", "/seriesmith/features"), ("GET", "/seriesmith/features/sizes"),
         ("POST", "/seriesmith/features/install"), ("POST", "/seriesmith/features/cancel")]


def feature_routes(settings, make_context, in_comfyui: bool = False) -> list[tuple]:
    """[(method, path, view)] over this host's settings; `make_context()`
    gives an api.Context (readiness, ComfyUI's /object_info). Handlers as the
    API's are, served by views.make_view."""
    from seriesmith import api as A
    from seriesmith.server.views import make_view

    def place() -> INS.Place:
        if in_comfyui:
            return INS.place_in_comfyui()
        return INS.place_from_url(settings.local_comfyui, settings.comfyui_dir)

    def changed():
        # a file or pack went in: readiness and /object_info ask ComfyUI again
        A.forget_comfy()

    installer = INS.Installer(place, token=lambda: settings.hf_token, on_change=changed)

    def here(ctx) -> tuple[INS.Place, dict]:
        """Where things go, and what's there now (readiness, ComfyUI's nodes;
        nothing of either when it doesn't answer)."""
        p = place()
        try:
            readiness = A.target_readiness(ctx)
        except Exception:                                 # noqa: BLE001  ComfyUI away
            readiness = {}
        try:
            info = A.comfy_object_info(ctx)
        except Exception:                                 # noqa: BLE001
            info = None
        return p, INS.env_for(p, readiness, info)

    @A.handler
    def features(ctx, query):
        p, env = here(ctx)
        return 200, {"groups": [{"id": g, "label": label, "about": about}
                                for g, label, about in FT.GROUPS],
                     "features": FT.status(FT.catalog(), env), "place": p.to_json(),
                     "hf_token": bool(settings.hf_token), "job": installer.state()}

    @A.handler
    def sizes(ctx, query):
        urls = sorted({i.url for f in FT.catalog() for i in f.items if i.kind == "model" and i.url})
        todo = [u for u in urls if u not in _SIZES]
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
        return 200, {"sizes": {u: _SIZES.get(u) for u in urls}}

    @A.handler
    def install(ctx, body):
        body = A.body_dict(body)
        p, env = here(ctx)
        items, skipped = FT.resolve(body.get("features") or [], body.get("files") or [],
                                    body.get("classes") or [], env=env)
        if items and p.why_not and any(i.kind in ("model", "pack") for i in items):
            return 409, {"error": p.why_not, "skipped": skipped}
        return 200, {"job": installer.start(items) if items else installer.state(),
                     "queued": [i.key for i in items], "skipped": skipped}

    @A.handler
    def cancel(ctx, query):
        return 200, {"job": installer.cancel()}

    return [(m, p, make_view(make_context, fn, takes)) for m, p, fn, takes in (
        ("GET", "/seriesmith/features", features, "query"),
        ("GET", "/seriesmith/features/sizes", sizes, "query"),
        ("POST", "/seriesmith/features/install", install, "body"),
        ("POST", "/seriesmith/features/cancel", cancel, "query"))]


__all__ = ["feature_routes", "head_size"]
