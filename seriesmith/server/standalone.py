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


def make_app(roots: list[str] | None = None, settings=None) -> web.Application:
    settings = settings or load_settings()
    events = Events()
    user_dir = os.path.dirname(settings_path())
    env = dict(os.environ)
    if roots:
        have = [r for r in env.get("H3PIPE_ROOTS", "").split(os.pathsep) if r]
        env["H3PIPE_ROOTS"] = os.pathsep.join(have + [os.path.abspath(r) for r in roots])

    def make_context():
        return A.Context(user_dir, settings.comfyui_url, events.emit, env=env)

    app = web.Application(client_max_size=A.MAX_UPLOAD + (1 << 20))
    app["events"], app["settings"], app["comfy_connected"] = events, settings, False
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

    app.router.add_get("/ws", ws_view)
    app.router.add_get("/seriesmith/info", info)
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
    print(f"  seriesmith editor: http://{args.host}:{args.port}/   (Ctrl+C stops it)", flush=True)
    web.run_app(app, host=args.host, port=args.port, print=None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
