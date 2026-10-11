"""
`seriesmith serve`: the editor as a page of its own (docs/DESIGN.md, "The
editor, in two hosts").

    http://127.0.0.1:8190/              the editor (seriesmith/server/static/)
    /seriesmith/...                     its API (seriesmith.api) and the queue's
    /ws                                 events for the page: {"type", "data"}

Events are the API's own (seriesmith.take, seriesmith.ref, ...) and the
queue's (seriesmith.job, and each job's progress in ComfyUI's shapes, its id as
the prompt id). The server also listens on ComfyUI's websocket (as client
"seriesmith") and passes its messages on, for whether ComfyUI is there.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
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
API_CLIENT_ID = "seriesmith"            # the client id the API queues on ComfyUI under


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
        try:
            self.loop.call_soon_threadsafe(lambda: asyncio.ensure_future(self._send(msg)))
        except RuntimeError:                              # the server is stopping: nobody to tell
            pass

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


def recover(runner, ask=None, rebuild=None) -> list[str]:
    """The jobs this server had when it last stopped (the queue's journal):
    each one that had reached its backend is found again and collected
    (Runner.reattach); one still waiting in the queue had cost nothing, so
    its record is cleared and the request that queued it is asked again
    (runner.requeue_plan), through `ask(path, body)`, on a thread of its own
    and in the order they were queued (without `ask` it is failed, saying how
    to queue it again). A step of seriesmith's own still waiting (a clip's
    renders once its pictures are made, a frame's views) is made again by
    `rebuild(resume)` once those are asked for, so it waits on the pictures
    as they are now. Then the journal is the live queue again. Returns what
    was done."""
    from seriesmith.runner import requeue_plan
    out, waiting, steps = [], [], []
    for job_id, entry in runner.queue.read_journal().items():
        if not isinstance(entry, dict):
            continue
        if (entry.get("resume") or {}).get("kind") == "step":
            if entry.get("status") == "queued" and rebuild is not None:
                steps.append(entry)
            else:                                            # it was part done: not twice
                out.append(f"{entry.get('title')}: it was running when the server stopped; "
                           "queue it again if what it asks for isn't there")
            continue
        try:
            new = runner.reattach(job_id, entry, waiting if ask else None)
        except Exception as e:                               # noqa: BLE001  one bad entry
            out.append(f"{entry.get('title')}: couldn't pick it up again ({e})")
            continue
        if new:
            out.append(f"{entry.get('title')}: picked up again (its run is followed again)")
    runner.queue.write_journal()
    plan = requeue_plan(waiting)
    if plan:
        out.append(f"{len(waiting)} job(s) that hadn't started: queued again "
                   f"({len(plan)} request(s))")
    steps.sort(key=lambda e: e.get("created") or 0)
    if steps:
        out.append(f"{len(steps)} step(s) made again: "
                   + ", ".join(str(e.get("title")) for e in steps))

    def again():
        for r in plan:
            try:
                status, data = ask(r["path"], r["body"])
                if status >= 400:
                    log.warning("seriesmith: queuing %s again: %s", r["path"], data)
            except Exception:                                # noqa: BLE001  log, go on
                log.exception("seriesmith: queuing %s again failed", r["path"])
        for e in steps:                                      # after: they wait on those
            try:
                rebuild(e["resume"])
            except Exception:                                # noqa: BLE001  log, go on
                log.exception("seriesmith: making %s again failed", e.get("title"))
    if plan and ask is not None:
        threading.Thread(target=again, daemon=True, name="seriesmith-requeue").start()
    elif steps:
        again()
    return out


def start_queue(settings, user_dir: str, emit, comfy_url: str | None = None, env=None,
                backends: dict | None = None, journal: str = "queue.json"):
    """seriesmith's queue for a host (this server, or ComfyUI's: server/
    comfyui.py): renders from the page go through the backends, the live jobs
    journaled in <user_dir>/<journal>. Returns (runner, make_context, recover_all):
    recover_all() picks up what the journal had when the host last stopped
    (recover), for the host to call once the backends can answer."""
    from seriesmith.backends import available
    from seriesmith.queue import Queue
    from seriesmith.runner import Runner
    queue = Queue(emit, journal=os.path.join(user_dir, journal))
    queue.paid_limit = settings.paid_limit
    backends = backends if backends is not None else available(settings)
    runner = Runner(queue, backends, emit)
    url = comfy_url or settings.comfyui_url

    def make_context():
        return A.Context(user_dir, url, emit, env=env, runner=runner)

    def ask(path: str, body: dict):
        """A queuing request asked again (after a restart), as the page would,
        the request kept with its jobs as views.py does."""
        from seriesmith.runner import ASKED
        fn = next(f for m, p, f, _t in A.ROUTES if m == "POST" and p == path)
        ASKED.req = {"path": path, "body": body}
        try:
            return fn(make_context(), body)
        finally:
            ASKED.req = None

    runner.ask = ask

    def recover_all() -> list[str]:
        out = recover(runner, ask, lambda resume: A.rebuild_step(make_context(), resume))
        for line in out:
            log.info("seriesmith: %s", line)
        return out
    return runner, make_context, recover_all


def make_app(roots: list[str] | None = None, settings=None,
             backends: dict | None = None) -> web.Application:
    settings = settings or load_settings()
    events = Events()
    user_dir = os.path.dirname(settings_path())
    env = dict(os.environ)
    if roots:
        have = [r for r in env.get("SERIESMITH_ROOTS", "").split(os.pathsep) if r]
        env["SERIESMITH_ROOTS"] = os.pathsep.join(have + [os.path.abspath(r) for r in roots])
    runner, make_context, recover_all = start_queue(settings, user_dir, events.emit, env=env,
                                                    backends=backends)
    recover_all()
    queue, backends = runner.queue, runner.backends

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
            return [{"name": n, "kind": b.kind, "down": b.ping(),
                     "where": getattr(b, "base_url", None) or getattr(b, "cloud_url", "")}
                    for n, b in backends.items()]
        return web.json_response({"backends": await loop.run_in_executor(None, look),
                                  "api_key": bool(settings.api_key)})

    # -- the machine's settings (the Settings window) ----------------------

    async def settings_get(request: web.Request) -> web.Response:
        from seriesmith.settings import from_env
        return web.json_response({"settings": settings.describe(), "file": settings_path(),
                                  "from_env": from_env()})

    async def settings_put(request: web.Request) -> web.Response:
        """Save the settings file, then use it: the backends are made again
        from it (a job already running keeps the one it started on)."""
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
        for k in ("local_url", "comfyui_url", "cloud_url", "api_key", "deployments", "path",
                  "paid_limit"):
            setattr(settings, k, getattr(fresh, k))
        queue.paid_limit = settings.paid_limit
        from seriesmith.backends import available
        backends.clear()
        backends.update(available(settings))
        return web.json_response({"settings": settings.describe(), "file": settings_path(),
                                  "from_env": from_env()})

    async def comfy_models(request: web.Request) -> web.Response:
        folder = request.match_info.get("folder")
        url = settings.comfyui_url + "/models" + (f"/{folder}" if folder else "")
        try:
            async with ClientSession() as cs, cs.get(url, timeout=10) as r:
                if r.status == 200:
                    return web.json_response(await r.json())
                return web.json_response({"error": f"ComfyUI answered {r.status} for {url}"},
                                         status=r.status)
        except Exception as e:                            # noqa: BLE001  ComfyUI away
            return web.json_response({"error": f"ComfyUI ({settings.comfyui_url}) doesn't "
                                               f"answer: {e}"}, status=503)

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
    app.router.add_get("/seriesmith/settings", settings_get)
    # ComfyUI's model lists (GET /models, /models/{folder}: loras, checkpoints,
    # upscale_models, ...), as the page asks for them inside ComfyUI: passed
    # on to this machine's ComfyUI, an empty list when it doesn't answer
    for p in ("/models", "/api/models"):
        app.router.add_get(p, comfy_models)
        app.router.add_get(p + "/{folder}", comfy_models)
    app.router.add_put("/seriesmith/settings", settings_put)
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
    if not _answers(settings.comfyui_url):
        return f"comfy-api-proxy: not started (no ComfyUI at {settings.comfyui_url})"
    name = "comfy-api-proxy" + (".exe" if os.name == "nt" else "")
    here = os.path.dirname(sys.executable)
    # beside this Python: a venv's Scripts/, or ComfyUI's embedded Python's
    exe = next((p for p in (os.path.join(here, name), os.path.join(here, "Scripts", name))
                if os.path.isfile(p)), "")
    if not exe:
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
