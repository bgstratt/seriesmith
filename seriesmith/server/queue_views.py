"""
The queue's own routes, for both hosts (`seriesmith serve` and ComfyUI's,
server/comfyui.py): the Jobs window (GET /seriesmith/jobs, POST
/seriesmith/jobs/<action>), "Render on" (GET /seriesmith/backends), the
Settings window (GET / PUT /seriesmith/settings, POST /seriesmith/sdk/install:
comfy-sdk put in for Cloud and Router, seriesmith.sdk) and GET /seriesmith/info.
They read the host's settings and runner (standalone.start_queue), so they
live beside the API rather than in it; they are handlers as the API's are
((ctx, arg) -> (status, data), api.handler), served by views.make_view: the
same parsing, errors, JSON and worker threads.
"""
from __future__ import annotations

from seriesmith import api as A
from seriesmith import sdk as SDK
from seriesmith.settings import load_settings, settings_path

# the backends that run through comfy-sdk (Comfy Cloud, deployments, Router)
SDK_KINDS = ("cloud", "deployment", "router")
ACTIONS = ("cancel", "move", "pause", "retry", "paid-reset")

# what queue_routes registers (server/routes.all_paths: known before the queue starts);
# an action the page doesn't know answers 404 from the catch-all, after the five
PATHS = ([("GET", "/seriesmith/info"), ("GET", "/seriesmith/jobs")]
         + [("POST", f"/seriesmith/jobs/{a}") for a in ACTIONS]
         + [("POST", "/seriesmith/jobs/{action}"), ("GET", "/seriesmith/backends"),
            ("GET", "/seriesmith/settings"), ("PUT", "/seriesmith/settings"),
            ("POST", "/seriesmith/sdk/install")])


def _field(body: dict, key: str, kind=str):
    """`body[key]` as `kind`: 400 when it's missing or isn't one."""
    if key not in body:
        raise A.ApiError(400, f"{key} is required")
    try:
        return kind(body[key])
    except (TypeError, ValueError):
        raise A.ApiError(400, f"{key} must be {'a whole number' if kind is int else 'text'}") from None


def queue_routes(settings, runner, connected=lambda: False,
                 make_context=None) -> list[tuple]:
    """[(method, path, view)] over this host's `settings` and `runner`;
    connected() says whether the page's ComfyUI answers (for /info)."""
    from seriesmith.server.views import make_view
    queue, backends = runner.queue, runner.backends

    @A.handler
    def info(ctx, query):
        from seriesmith import __version__
        return 200, {"version": __version__, "settings": settings.describe(),
                     "comfy_connected": connected()}

    @A.handler
    def jobs(ctx, query):
        return 200, queue.list()

    def job_action(what: str):
        @A.handler
        def act(ctx, body):
            body = A.body_dict(body)
            if what == "paid-reset":
                queue.paid_count = 0
                return 200, queue.list()
            try:
                if what == "cancel":
                    queue.cancel(_field(body, "id"))
                elif what == "move":
                    job_id, index = _field(body, "id"), _field(body, "index", int)
                    queue.move(job_id, index)
                elif what == "pause":
                    queue.pause(_field(body, "lane"), bool(body.get("paused", True)))
                else:
                    queue.retry(_field(body, "id"))
            except KeyError as e:
                raise A.ApiError(404, f"no such job: {e}") from None
            except (ValueError, TypeError) as e:
                raise A.ApiError(409, str(e)) from None
            return 200, queue.list()
        act.__name__ = f"job_{what.replace('-', '_')}"
        return act

    @A.handler
    def no_action(ctx, body):
        raise A.ApiError(404, "no such action: the Jobs window's are " + ", ".join(ACTIONS))

    @A.handler
    def backend_list(ctx, query):
        """Each backend and whether it answers."""
        no_sdk = None if SDK.have() else (
            "Comfy's SDK is being installed" if SDK.state()["status"] == "installing"
            else "Comfy's SDK isn't installed (Settings: Install)")
        return 200, {"backends": [{"name": n, "kind": b.kind,
                                   "down": (no_sdk if b.kind in SDK_KINDS else None) or b.ping(),
                                   "where": getattr(b, "base_url", None) or getattr(b, "cloud_url", "")}
                                  for n, b in backends.items()],
                     "api_key": bool(settings.api_key)}

    @A.handler
    def settings_get(ctx, query):
        from seriesmith.settings import from_env
        return 200, {"settings": settings.describe(), "file": settings_path(),
                     "from_env": from_env(), "sdk": SDK.state()}

    @A.handler
    def sdk_install(ctx, query):
        """comfy-sdk installed into this Python, in the background (the
        Settings window's Install): its state, to poll GET /seriesmith/settings."""
        return 200, {"sdk": SDK.install()}

    @A.handler
    def settings_put(ctx, body):
        """Save the settings file, then use it: the backends are made again
        from it (a job already running keeps the one it started on)."""
        from seriesmith import ff as FF
        from seriesmith.backends import available
        from seriesmith.settings import FIELDS, from_env, save_settings
        body = A.body_dict(body)
        try:
            save_settings({k: v for k, v in body.items() if k in FIELDS})
            fresh = load_settings()
        except ValueError as e:
            raise A.ApiError(400, str(e)) from None
        for k in FIELDS + ("path",):              # every one, so a new field can't go stale
            setattr(settings, k, getattr(fresh, k))
        queue.paid_limit = settings.paid_limit
        FF.forget()                               # ffmpeg_dir may have changed
        made = available(settings)                # made first: never an empty set in between
        backends.clear()
        backends.update(made)
        # a key set, and comfy-sdk not here (ComfyUI's Python): put it in now
        sdk = SDK.ensure(settings)
        return 200, {"settings": settings.describe(), "file": settings_path(),
                     "from_env": from_env(), "sdk": sdk}

    if make_context is None:
        make_context = lambda: A.Context(".", env={})          # noqa: E731  (unused by these)
    table = ([("GET", "/seriesmith/info", info, "query"),
              ("GET", "/seriesmith/jobs", jobs, "query")]
             + [("POST", f"/seriesmith/jobs/{a}", job_action(a), "body") for a in ACTIONS]
             + [("POST", "/seriesmith/jobs/{action}", no_action, "query"),
                ("GET", "/seriesmith/backends", backend_list, "query"),
                ("GET", "/seriesmith/settings", settings_get, "query"),
                ("PUT", "/seriesmith/settings", settings_put, "body"),
                ("POST", "/seriesmith/sdk/install", sdk_install, "query")])
    return [(m, p, make_view(make_context, fn, takes)) for m, p, fn, takes in table]
