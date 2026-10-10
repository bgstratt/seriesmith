"""
`seriesmith serve`: the editor as a page of its own (docs/DESIGN.md, "The
editor, in two hosts").

    http://127.0.0.1:8190/              the editor (seriesmith/server/static/)
    /h3pipe/...                         its API (seriesmith.api), as under ComfyUI
    /ws                                 events for the page: {"type", "data"}

Events are the API's own (h3pipe.take, h3pipe.ref, ...) and, while the editor
still queues some work on your ComfyUI directly (docs/PLAN.md, step 8), that
ComfyUI's progress messages for it: the server listens on ComfyUI's websocket
as the client the API queues under ("h3pipe") and passes them on.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

from aiohttp import ClientSession, WSMsgType, web

from seriesmith import api as A
from seriesmith.server.views import routes
from seriesmith.settings import load_settings, settings_path

log = logging.getLogger("seriesmith")
HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "static")
DEFAULT_PORT = 8190
# what the page listens for from ComfyUI (web/src/host.ts HostEvent)
COMFY_EVENTS = {"progress", "executing", "execution_start", "execution_success",
                "execution_error", "execution_interrupted", "execution_cached"}
API_CLIENT_ID = "h3pipe"            # the client id the API queues on ComfyUI under


class Events:
    """The page's websockets, and a thread-safe way to send to all of them."""

    def __init__(self):
        self.sockets: set[web.WebSocketResponse] = set()
        self.loop: asyncio.AbstractEventLoop | None = None

    def emit(self, event: str, data) -> None:
        """From any thread (the API's handlers run in a worker pool)."""
        if self.loop is None:
            return
        msg = json.dumps({"type": event, "data": data}, ensure_ascii=False)
        self.loop.call_soon_threadsafe(lambda: asyncio.ensure_future(self._send(msg)))

    async def _send(self, msg: str) -> None:
        for ws in list(self.sockets):
            try:
                await ws.send_str(msg)
            except (ConnectionError, RuntimeError):
                self.sockets.discard(ws)


async def comfy_relay(app: web.Application) -> None:
    """Listen on ComfyUI's websocket as the API's client and pass its
    progress messages to the page; reconnect when it goes away."""
    events: Events = app["events"]
    url = app["settings"].comfyui_url.replace("http", "ws", 1) + f"/ws?clientId={API_CLIENT_ID}"
    wait = 1.0
    while True:
        try:
            async with ClientSession() as session, session.ws_connect(url, heartbeat=30) as ws:
                wait = 1.0
                app["comfy_connected"] = True
                async for msg in ws:
                    if msg.type != WSMsgType.TEXT:
                        continue
                    try:
                        m = json.loads(msg.data)
                    except ValueError:
                        continue
                    if m.get("type") in COMFY_EVENTS:
                        await events._send(json.dumps(m))
        except asyncio.CancelledError:
            raise
        except Exception as e:                            # noqa: BLE001  not up yet, or gone
            log.debug("seriesmith: ComfyUI websocket: %s", e)
        app["comfy_connected"] = False
        await asyncio.sleep(wait)
        wait = min(wait * 2, 30.0)


def make_app(roots: list[str] | None = None, settings=None,
             backends: dict | None = None) -> web.Application:
    settings = settings or load_settings()
    events = Events()
    user_dir = os.path.dirname(settings_path())
    env = dict(os.environ)
    if roots:
        have = [r for r in env.get("H3PIPE_ROOTS", "").split(os.pathsep) if r]
        env["H3PIPE_ROOTS"] = os.pathsep.join(have + [os.path.abspath(r) for r in roots])

    # seriesmith's queue: renders from the page go through the backends
    from seriesmith.backends import available
    from seriesmith.queue import Queue
    from seriesmith.runner import Runner
    queue = Queue(events.emit)
    backends = backends if backends is not None else available(settings)
    runner = Runner(queue, backends, events.emit)

    def make_context():
        return A.Context(user_dir, settings.comfyui_url, events.emit, env=env, runner=runner)

    app = web.Application(client_max_size=A.MAX_UPLOAD + (1 << 20))
    app["events"], app["settings"], app["comfy_connected"] = events, settings, False
    app["queue"], app["runner"], app["backends"] = queue, runner, backends
    for method, path, view in routes(make_context):
        app.router.add_route(method, path, view)
        # as ComfyUI serves them too, under /api
        app.router.add_route(method, "/api" + path, view)

    async def ws_view(request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=30)
        await ws.prepare(request)
        events.sockets.add(ws)
        try:
            async for _ in ws:
                pass
        finally:
            events.sockets.discard(ws)
        return ws

    async def info(request: web.Request) -> web.Response:
        from seriesmith import __version__
        return web.json_response({"version": __version__, "settings": settings.describe(),
                                  "comfy_connected": request.app["comfy_connected"]})

    async def index(request: web.Request) -> web.StreamResponse:
        page = os.path.join(STATIC, "standalone.html")
        if not os.path.isfile(page):
            return web.Response(status=503, text="The editor isn't built: cd web && npm run "
                                                 "build:standalone")
        return web.FileResponse(page, headers={"Cache-Control": "no-cache"})

    # -- the Jobs window ---------------------------------------------------

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
            return [{"name": n, "kind": b.kind, "down": b.ping(),
                     "where": getattr(b, "base_url", None) or getattr(b, "cloud_url", "")}
                    for n, b in backends.items()]
        return web.json_response({"backends": await loop.run_in_executor(None, look),
                                  "api_key": bool(settings.api_key)})

    async def comfy_queue(request: web.Request) -> web.Response:
        """ComfyUI's /queue, as the editor reads it (running and pending prompt
        ids), with seriesmith's queue's jobs in it: ComfyUI's own (work the
        API still queues there), then ours."""
        running, pending = [], []
        try:
            async with ClientSession() as s, s.get(settings.comfyui_url + "/queue",
                                                   timeout=3) as r:
                q = await r.json()
                running += q.get("queue_running") or []
                pending += q.get("queue_pending") or []
        except Exception:                                 # noqa: BLE001  no ComfyUI: ours only
            pass
        lst = queue.list()
        for n, lane in lst["lanes"].items():
            running += [[0, i] for i in lane["running"]]
            pending += [[k, i] for k, i in enumerate(lane["waiting"], 1)]
        return web.json_response({"queue_running": running, "queue_pending": pending})

    app.router.add_get("/ws", ws_view)
    app.router.add_get("/seriesmith/info", info)
    app.router.add_get("/seriesmith/jobs", jobs)
    app.router.add_post("/seriesmith/jobs/{action}", job_action)
    app.router.add_get("/seriesmith/backends", backend_list)
    for p in ("/queue", "/api/queue"):
        app.router.add_get(p, comfy_queue)
    app.router.add_get("/", index)
    if os.path.isdir(os.path.join(STATIC, "assets")):
        app.router.add_static("/assets", os.path.join(STATIC, "assets"))

    async def start(app: web.Application) -> None:
        events.loop = asyncio.get_running_loop()
        app["relay"] = asyncio.create_task(comfy_relay(app))

    async def stop(app: web.Application) -> None:
        app["relay"].cancel()
        for ws in list(events.sockets):
            await ws.close()

    app.on_startup.append(start)
    app.on_cleanup.append(stop)
    return app


def ensure_proxy(settings) -> str:
    """comfy-api-proxy answering at settings.local_url: started beside this
    Python (its own background process, state in %LOCALAPPDATA%\\seriesmith\\
    proxy) when it isn't and the local ComfyUI is up. Returns what happened."""
    import shutil
    import subprocess
    from urllib.parse import urlparse

    from seriesmith.backends.comfy import health
    if health(settings.local_url, timeout=2.0) is None:
        return f"comfy-api-proxy: {settings.local_url}"
    if health(settings.comfyui_url.rstrip("/") + "/..", timeout=2.0) and \
            not _answers(settings.comfyui_url):
        return f"comfy-api-proxy: not started (no ComfyUI at {settings.comfyui_url})"
    exe = os.path.join(os.path.dirname(sys.executable), "comfy-api-proxy" +
                       (".exe" if os.name == "nt" else ""))
    if not os.path.isfile(exe):
        exe = shutil.which("comfy-api-proxy") or ""
    if not exe:
        return "comfy-api-proxy: not installed (pip install comfy-api-proxy; docs/SETUP.md)"
    u = urlparse(settings.local_url)
    if u.hostname not in ("127.0.0.1", "localhost"):
        return f"comfy-api-proxy: {settings.local_url} doesn't answer (not started: not this machine)"
    state = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
                         "seriesmith", "proxy")
    os.makedirs(state, exist_ok=True)
    r = subprocess.run([exe, "start", "--comfyui", settings.comfyui_url, "--port",
                        str(u.port or 8189), "--state-dir", state],
                       capture_output=True, text=True, timeout=60)
    return "comfy-api-proxy: " + ((r.stdout or r.stderr).strip().splitlines() or ["started"])[-1]


def _answers(url: str) -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/system_stats", timeout=2):
            return True
    except Exception:                                     # noqa: BLE001
        return False


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="seriesmith serve",
                                 description="The editor in your browser: "
                                             "http://127.0.0.1:%d/" % DEFAULT_PORT)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--host", default="127.0.0.1",
                    help="the address to listen on (default 127.0.0.1: this machine only)")
    ap.add_argument("--root", action="append", metavar="FOLDER",
                    help="a folder of shows the editor may open (repeat for more; it also "
                         "keeps the ones you add in the editor)")
    args = ap.parse_args(argv)
    try:
        app = make_app(args.root)
    except ValueError as e:
        print(f"seriesmith: {e}", file=sys.stderr)
        return 1
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if "local" in app["backends"]:
        print("  " + ensure_proxy(app["settings"]), flush=True)
    print(f"  seriesmith editor: http://{args.host}:{args.port}/   (Ctrl+C stops it)", flush=True)
    web.run_app(app, host=args.host, port=args.port, print=None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
