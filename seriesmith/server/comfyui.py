"""
The ComfyUI host: the editor's API registered on ComfyUI's own server, its
events sent through ComfyUI's websocket. Loaded by seriesmith's node pack
(comfy_nodes/__init__.py), inside try/except, so nothing here can stop the
nodes loading. Ported from h3pipe's comfy_nodes/h3pipe_routes.py.

The same app as `seriesmith serve`: the same settings and project folders
(seriesmith's own folder, settings.settings_path), and seriesmith's queue
(standalone.start_queue) with its backends, its own journal
(queue-comfyui.json, so the two hosts never recover each other's jobs), its
local renders queued on this ComfyUI itself (or through comfy-api-proxy, with
local_via "proxy", started here). What the journal had is
picked up once this ComfyUI answers (in the background: at load time its
server isn't up yet).
"""
from __future__ import annotations

import logging
import os

from seriesmith import api as A
from seriesmith.server.routes import all_paths, all_routes

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
    """seriesmith's own folder: the standalone server's too, so both see the
    same project folders and settings."""
    from seriesmith.settings import settings_path
    return os.path.dirname(settings_path())


def taken(server) -> list[str]:
    """The editor's paths some other pack already registered on this server
    (h3pipe's node pack serves the same API): registering them twice would
    break ComfyUI's startup, so seriesmith then stays out of the way."""
    have = {getattr(r, "path", None) for r in getattr(server, "routes", [])}
    return sorted(path for path in all_paths() if path in have)


def register(server, wait: float = 120.0) -> bool:
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

    make_context, settings, runner = start(server, wait=wait)
    # every route (server/routes.py, as `seriesmith serve` has them); ComfyUI
    # answers each under /api itself
    for method, path, view in all_routes(make_context, settings, runner, lambda: True,
                                         in_comfyui=True):
        server.routes.route(method, path)(view)
    REGISTERED = True
    return True


def start(server, settings=None, wait: float = 120.0):
    """seriesmith's queue on this ComfyUI (standalone.start_queue), and, in
    the background once the server answers: comfy-api-proxy for the local
    backend, then what the journal had. Returns (make_context, settings, the
    runner). Without a queue (it can't start) the editor still works, rendering
    as h3pipe did: the runner is None, and only the queue's own routes are left
    out (the Features window doesn't need it)."""
    import threading
    import time

    from seriesmith.server.standalone import _answers, detect_models, ensure_proxy, start_queue
    from seriesmith.settings import load_settings
    url = base_url(server)

    def emit(event, data):
        server.send_sync(event, data)
    try:
        settings = settings or load_settings()
    except Exception as e:                                # noqa: BLE001  the editor still loads
        log.warning("seriesmith: the settings can't be read (%s): the defaults for now", e)
        from seriesmith.settings import Settings
        settings = Settings()
    try:
        # local renders go to this ComfyUI, on whatever port it was started
        settings.host_url = url
        runner, make_context, recover_all = start_queue(settings, user_dir(), emit, comfy_url=url,
                                                        journal="queue-comfyui.json")
    except Exception as e:                                # noqa: BLE001  the editor still loads
        log.warning("seriesmith: the queue didn't start in this ComfyUI (%s): renders go "
                    "straight to ComfyUI", e)
        return (lambda: A.Context(user_dir(), url, emit)), settings, None
    # ComfyUI exiting: the journal kept as the jobs stand, a master or align
    # running stopped rather than left going without us (Queue.close)
    import atexit
    atexit.register(runner.queue.close)

    # a Comfy API key already set (Settings, COMFY_API_KEY) but no comfy-sdk in
    # ComfyUI's Python: put it in, in the background (seriesmith.sdk)
    from seriesmith import sdk as SDK
    try:
        SDK.ensure(settings)
    except Exception as e:                                # noqa: BLE001  never stop the load
        log.warning("seriesmith: comfy-sdk: %s", e)

    def when_up():
        end = time.time() + wait
        while time.time() < end and not _answers(url):
            time.sleep(1.0)
        try:
            log.info("seriesmith: %s", ensure_proxy(settings))
        except Exception as e:                            # noqa: BLE001  log, go on
            log.warning("seriesmith: comfy-api-proxy: %s", e)
        try:
            log.info("seriesmith: %s", detect_models(make_context))
        except Exception as e:                            # noqa: BLE001  log, go on
            log.warning("seriesmith: finding the installed models failed: %s", e)
        try:
            recover_all()
        except Exception:                                 # noqa: BLE001  log, go on
            log.exception("seriesmith: picking up the last session's jobs failed")
    if wait:
        threading.Thread(target=when_up, daemon=True, name="seriesmith-start").start()
    return make_context, settings, runner


def register_on_prompt_server() -> bool:
    from server import PromptServer
    return register(PromptServer.instance)
