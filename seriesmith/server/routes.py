"""
Every route of the editor, for both hosts (`seriesmith serve`, server/
standalone.py; ComfyUI's own server, server/comfyui.py): one list, registered
by each host in one loop, so the two can't drift apart.

    api_routes       the editor's API (api.ROUTES, server/views.py)
    queue routes     Jobs, Render on, Settings, info (server/queue_views.py):
                     only when the host has seriesmith's queue
    feature routes   the Features window (server/features_views.py): always,
                     queue or not

`seriesmith serve` answers each path under /api as well, as ComfyUI does for
every route registered on it: the page inside ComfyUI asks through ComfyUI's
api.fetchApi, which adds that prefix. The routes only `seriesmith serve` has
(the page, its websocket, ComfyUI's /models and /queue passed on, stop) stay
in standalone.py.
"""
from __future__ import annotations

from typing import Callable

from seriesmith import api as A
from seriesmith.server import features_views as FV
from seriesmith.server import queue_views as QV
from seriesmith.server.views import routes as api_routes


def all_routes(make_context: Callable[[], "A.Context"], settings, runner=None,
               connected: Callable[[], bool] = lambda: False,
               in_comfyui: bool = False) -> list[tuple[str, str, Callable]]:
    """(method, path, view) of every route a host serves; the queue's only
    with a `runner` (the queue started)."""
    out = list(api_routes(make_context))
    if runner is not None:
        out += QV.queue_routes(settings, runner, connected)
    out += FV.feature_routes(settings, make_context, in_comfyui)
    return out


def all_paths() -> set[str]:
    """Every path all_routes may register, known before anything starts (a
    host checks them against routes another pack already has)."""
    return ({path for _, path, _, _ in A.ROUTES} | {path for _, path in QV.PATHS}
            | {path for _, path in FV.PATHS})


__all__ = ["all_paths", "all_routes"]
