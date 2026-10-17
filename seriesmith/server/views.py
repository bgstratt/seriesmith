"""
The editor's API (seriesmith.api) as aiohttp views, for any host: parse the
query or JSON body (or, for a multipart upload, stream it to a temporary
file), run the handler off the event loop, answer JSON, or stream a file for
GET /seriesmith/file. A host supplies the Context for each request
(`make_context`). Ported from h3pipe's comfy_nodes/h3pipe_routes.py.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from typing import Callable

from aiohttp import BodyPartReader, web

from seriesmith import api as A

log = logging.getLogger("seriesmith")


_THUMBS = None


def _thumb_pool():
    """The thumbnails' own two threads (GET /seriesmith/thumb)."""
    global _THUMBS
    if _THUMBS is None:
        from concurrent.futures import ThreadPoolExecutor
        _THUMBS = ThreadPoolExecutor(max_workers=2, thread_name_prefix="seriesmith-thumb")
    return _THUMBS


COMPRESS_OVER = 64 * 1024        # a reply this big goes gzipped (the refs listing: megabytes)


def _json(status: int, data) -> web.Response:
    resp = web.json_response(data, status=status,
                             dumps=lambda o: json.dumps(o, ensure_ascii=False))
    if resp.body is not None and len(resp.body) > COMPRESS_OVER:
        resp.enable_compression()          # when the browser accepts it, as they all do
    return resp


class TooLarge(Exception):
    pass


async def read_form(request: web.Request) -> dict:
    """A multipart/form-data body as {name: text}, a file field as an
    A.Upload saved to a temporary file (streamed, never held in memory).
    TooLarge past A.MAX_UPLOAD; the temporary files are removed then."""
    form: dict = {}
    reader = await request.multipart()
    loop = asyncio.get_running_loop()
    try:
        while True:
            part = await reader.next()
            if part is None:
                break
            if not isinstance(part, BodyPartReader) or not part.name:
                continue
            if part.filename is None:
                form[part.name] = await part.text()
                continue
            ext = os.path.splitext(part.filename)[1][:16]
            fd, tmp = tempfile.mkstemp(prefix="seriesmith_upload_", suffix=ext)
            form[part.name] = A.Upload(tmp, part.filename, 0)
            with os.fdopen(fd, "wb") as fh:
                while True:
                    chunk = await part.read_chunk(1 << 20)
                    if not chunk:
                        break
                    form[part.name].size += len(chunk)
                    if form[part.name].size > A.MAX_UPLOAD:
                        raise TooLarge()
                    await loop.run_in_executor(None, fh.write, chunk)
    except BaseException:
        drop_uploads(form)
        raise
    return form


def drop_uploads(form) -> None:
    for v in (form.values() if isinstance(form, dict) else []):
        if isinstance(v, A.Upload) and os.path.isfile(v.path):
            try:
                os.remove(v.path)
            except OSError:
                pass


def make_view(make_context: Callable[[], "A.Context"], fn, takes: str, is_file: bool = False):
    async def view(request: web.Request) -> web.StreamResponse:
        if takes == "form" and request.content_type == "multipart/form-data":
            if (request.content_length or 0) > A.MAX_UPLOAD + (1 << 20):
                return _json(413, {"error": f"the file is over "
                                            f"{A.MAX_UPLOAD // (1024 * 1024)} MB"})
            try:
                arg = await read_form(request)
            except TooLarge:
                return _json(413, {"error": f"the file is over "
                                            f"{A.MAX_UPLOAD // (1024 * 1024)} MB"})
            except (ValueError, AssertionError, UnicodeDecodeError) as e:
                return _json(400, {"error": f"the multipart body can't be read: {e}"})
        elif takes in ("body", "form"):
            try:
                arg = await request.json()
            except (ValueError, UnicodeDecodeError):
                return _json(400, {"error": "the request body must be JSON"
                                            + (" or multipart/form-data" if takes == "form"
                                               else "")})
        else:
            arg = dict(request.query)
        ctx = make_context()
        ctx.sweep_later = True             # a server answers first, then tidies (get_refs)
        loop = asyncio.get_running_loop()
        # a request that queues work is kept with its jobs (runner.ASKED), so
        # one still waiting when the server stops can be asked for again
        req = ({"path": request.path[4:] if request.path.startswith("/api/") else request.path,
                "body": arg} if takes == "body" and request.method == "POST" else None)

        def call(ctx, arg):
            from seriesmith.runner import ASKED
            ASKED.req = req
            try:
                return fn(ctx, arg)
            finally:
                ASKED.req = None
        try:
            # a thumbnail (shrinking a picture: CPU) on a pool of its own, so a
            # Refs tab asking for hundreds never holds up the other requests
            pool = _thumb_pool() if fn is A.get_thumb else None
            status, data = await loop.run_in_executor(pool, call, ctx, arg)
        except Exception as e:                            # handler() already catches; belt
            log.exception("seriesmith: %s failed", request.path)
            return _json(500, {"error": f"{e.__class__.__name__}: {e}"})
        finally:
            drop_uploads(arg)
        if is_file and status == 200:
            return web.FileResponse(data["path"], headers={
                "Cache-Control": "no-cache", "Content-Type": data["content_type"]})
        return _json(status, data)
    view.__name__ = f"seriesmith_{fn.__name__}"
    return view


def routes(make_context: Callable[[], "A.Context"]) -> list[tuple[str, str, Callable]]:
    """(method, path, view) for every route of the editor's API."""
    return [(method, path, make_view(make_context, fn, takes, is_file=fn in (A.get_file, A.get_thumb)))
            for method, path, fn, takes in A.ROUTES]
