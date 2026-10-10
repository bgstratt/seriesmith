"""
The ComfyUI host: the editor's API registered on ComfyUI's own server, its
events sent through ComfyUI's websocket. Loaded by seriesmith's node pack
(comfy_nodes/__init__.py), inside try/except, so nothing here can stop the
nodes loading. Ported from h3pipe's comfy_nodes/h3pipe_routes.py.
"""
from __future__ import annotations

import logging
import os

from seriesmith import api as A
from seriesmith.server.views import routes

log = logging.getLogger("seriesmith")
REGISTERED = False


def base_url(server) -> str:
    """This ComfyUI's own address, for queueing on it and reading its workflows."""
    port = getattr(server, "port", None)
    if not port:
        return A.DEFAULT_COMFY
    addr = str(getattr(server, "address", "") or "")
    if addr in ("", "0.0.0.0", "::", "[::]"):
        addr = "127.0.0.1"
    if ":" in addr and not addr.startswith("["):
        addr = f"[{addr}]"
    return f"http://{addr}:{port}"


def user_dir() -> str:
    try:
        import folder_paths
        return folder_paths.get_user_directory()
    except Exception:
        return os.path.join(os.getcwd(), "user")


def taken(server) -> list[str]:
    """The editor's paths some other pack already registered on this server
    (h3pipe's node pack serves the same API): registering them twice would
    break ComfyUI's startup, so seriesmith then stays out of the way."""
    have = {getattr(r, "path", None) for r in getattr(server, "routes", [])}
    return [path for _, path, _, _ in A.ROUTES if path in have]


def register(server) -> bool:
    """Add every route to `server.routes` (once). False, and nothing added,
    when another pack already serves them."""
    global REGISTERED
    if REGISTERED:
        return True
    clash = taken(server)
    if clash:
        log.warning("seriesmith: the editor's routes are already served (by h3pipe's node "
                    "pack?) -- %s; seriesmith's editor stays off in this ComfyUI", clash[0])
        return False

    def make_context():
        return A.Context(user_dir(), base_url(server), lambda event, data: server.send_sync(event, data))

    for method, path, view in routes(make_context):
        server.routes.route(method, path)(view)
    REGISTERED = True
    return True


def register_on_prompt_server() -> bool:
    from server import PromptServer
    return register(PromptServer.instance)
