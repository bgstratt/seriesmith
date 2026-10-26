"""
seriesmith.api — the editor's HTTP routes (h3pipe's docs/API.md) as plain
functions.

No aiohttp and no ComfyUI in here, so it runs (and is tested) with any Python:
every handler takes a Context plus the query dict and/or the JSON body and
returns (status, json-able value). A host mounts them: seriesmith's own server,
or ComfyUI's (docs/DESIGN.md, "The editor, in two hosts"). The work itself is
the pipeline's (edit, jobs, refs, takes); this layer checks input, keeps
episodes inside the configured roots, turns seeds into strings and back, and
sends the live-update events.

Ported from h3pipe's comfy_nodes/h3pipe_api.py.
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading

# ---------------------------------------------------------------------------
# the pipeline
# ---------------------------------------------------------------------------

from seriesmith import edit as E  # noqa: E402
from seriesmith import inspector as IN  # noqa: E402
from seriesmith import issues as IS  # noqa: E402
from seriesmith import jobs as J  # noqa: E402
from seriesmith import peaks as PK  # noqa: E402
from seriesmith import promote as P  # noqa: E402
from seriesmith import refs as R  # noqa: E402
from seriesmith import takes as T  # noqa: E402
from seriesmith import upscale as U  # noqa: E402
from seriesmith import track as K  # noqa: E402
from seriesmith import targets as TG  # noqa: E402
from seriesmith.core import fileio as F

HOME = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
# kept for the hosts' sake: always None now that the pipeline is a package
IMPORT_ERROR: str | None = None

DEFAULT_COMFY = "http://127.0.0.1:8188"
CONFIG_VERSION = 1
PASSES = ("final", "proxy")
DEFAULT_PASS = "proxy"
CONTENT_TYPES = {
    ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp", ".wav": "audio/wav", ".mp3": "audio/mpeg",
    ".flac": "audio/flac", ".json": "application/json; charset=utf-8",
    ".md": "text/markdown; charset=utf-8", ".txt": "text/plain; charset=utf-8",
}


_UNSET = object()


class ApiError(Exception):
    """An answer other than 200: {"error": message, **data}."""

    def __init__(self, status: int, message: str, **data):
        super().__init__(message)
        self.status = status
        self.data = data


class Context:
    """What a handler needs from its host.

    user_dir   ComfyUI's user folder (config lives in <user_dir>/default/seriesmith/)
    comfy_url  this ComfyUI's own base URL
    emit       emit(event, data): a live-update event to every open editor
    comfy      a jobs.Comfy-like client (default: one for comfy_url, with
               client_id "seriesmith"); tests pass a fake
    env        environment for $SERIESMITH_ROOTS (default os.environ)
    model_resolve  resolve(folder, name) -> a model file's path or None
               (default jobs.model_resolver(): ComfyUI's folder_paths);
               None checks model files by name only
    model_list list(folder, class_type, field) -> the files ComfyUI offers
               (default: folder_paths.get_filename_list, else /object_info)
    """

    def __init__(self, user_dir: str, comfy_url: str = DEFAULT_COMFY, emit=None,
                 comfy=None, env: dict | None = None, model_resolve=_UNSET, model_list=None,
                 runner=None):
        self.user_dir = user_dir
        self.comfy_url = (comfy_url or DEFAULT_COMFY).rstrip("/")
        self._emit = emit
        self._comfy = comfy
        # seriesmith's queue (runner.Runner): every job goes through it and the
        # backends. A host that gives none gets one on first use (`runner`).
        self._runner = runner
        self.env = os.environ if env is None else env
        if model_resolve is _UNSET:
            model_resolve = J.model_resolver() if J is not None else None
        self.model_resolve = model_resolve
        self._model_list = model_list
        self._model_cache = None
        # a server sets it: work that can follow a reply (get_refs' sweep) is
        # done after it, on a thread; a direct caller (the CLI, tests) waits
        self.sweep_later = False

    @property
    def runner(self):
        """seriesmith's queue and runner: the host's, else one of this
        context's own on the backends the settings set up, its events going
        out through `emit`."""
        if self._runner is None:
            from seriesmith.backends import available
            from seriesmith.runner import Runner, queue_for
            from seriesmith.settings import load_settings
            settings = load_settings()
            self._runner = Runner(queue_for(settings, self.emit), available(settings),
                                  emit=self.emit)
        return self._runner

    @runner.setter
    def runner(self, value) -> None:
        self._runner = value

    @property
    def model_cache(self):
        """identify() results, in <user_dir>/default/seriesmith/modelid_cache.json."""
        if self._model_cache is None:
            self._model_cache = TG.modelid.user_cache(self.user_dir)
        return self._model_cache

    def model_list(self, folder: str | None, class_type: str | None, field: str | None) -> list:
        if self._model_list is not None:
            return list(self._model_list(folder, class_type, field) or [])
        if folder:
            try:
                import folder_paths                       # only inside ComfyUI
                return list(folder_paths.get_filename_list(folder))
            except Exception:
                pass
        if class_type and field:
            return list(self.comfy.choices(class_type, field) or [])
        return []

    def model_choices(self, folder: str | None, class_type: str | None,
                      field: str | None) -> list | None:
        """model_list, except that None means "can't tell" (no folder_paths
        and no answer from /object_info for that loader), so queue-time
        resolution leaves the param alone instead of calling it missing."""
        if self._model_list is not None:
            got = self._model_list(folder, class_type, field)
            return None if got is None else list(got)
        if folder:
            try:
                import folder_paths                       # only inside ComfyUI
                return list(folder_paths.get_filename_list(folder))
            except Exception:
                pass
        if class_type and field:
            try:
                got = self.comfy.choices(class_type, field, strict=True)
            except Exception:
                return None
            return None if got is None else list(got)
        return None

    @property
    def comfy(self):
        if self._comfy is None:
            self._comfy = J.Comfy(self.comfy_url, client_id="seriesmith")
        return self._comfy

    def emit(self, event: str, data: dict) -> None:
        if self._emit is not None:
            try:
                self._emit(event, data)
            except Exception:
                pass


def handler(fn):
    """Turn ApiError and stray exceptions into (status, {"error": ...}).

    Also scopes the custom targets a request may see (Phase 12): check_ep puts
    the episode's show in force for this thread, and it must not outlive the
    handler — the routes reuse threads, so the next request would inherit
    another show's targets. Cleared here rather than in the route layer, so a
    direct caller (the CLI, the tests) gets the same guarantee."""
    def wrapped(*args, **kw):
        if TG is not None:
            TG.clear_thread_roots()
        try:
            return fn(*args, **kw)
        except ApiError as e:
            return e.status, dict({"error": str(e)}, **e.data)
        except Exception as e:                            # the message is for a person
            # an error that always means the same answer says which (http_status:
            # refs' RefError 400, UnknownRef 404, master's MasterError 409, ...)
            status = getattr(type(e), "http_status", None)
            if status is not None:
                return status, {"error": str(e)}
            if isinstance(e, FileNotFoundError):
                return 404, {"error": str(e)}
            # the modules that carry their own HTTP status (source's Conflict,
            # issues' refusals) answer with it rather than a 500
            if P is not None and isinstance(e, P.H.SourceError):
                return e.status, dict({"error": str(e)}, **e.data)
            if IS is not None and isinstance(e, IS.IssueError):
                return e.status, dict({"error": str(e)}, **e.data)
            return 500, {"error": f"{e.__class__.__name__}: {e}"}
        finally:
            if TG is not None:
                TG.clear_thread_roots()
    wrapped.__name__ = fn.__name__
    wrapped.__doc__ = fn.__doc__
    return wrapped


# ---------------------------------------------------------------------------
# seeds: strings on the wire (63-bit seeds don't survive a JS number)
# ---------------------------------------------------------------------------

def seeds_out(obj):
    """A copy of `obj` with the value of every "seed" key as a string."""
    if isinstance(obj, dict):
        return {k: (str(v) if k == "seed" and isinstance(v, int) and not isinstance(v, bool)
                    else seeds_out(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [seeds_out(v) for v in obj]
    return obj


def seed_in(v, what: str = "seed") -> int | None:
    """A seed from a request: a string of digits (or, tolerated, an integer)."""
    if v is None:
        return None
    if isinstance(v, bool):
        raise ApiError(400, f"{what} must be a string of digits")
    if isinstance(v, int):
        n = v
    elif isinstance(v, str) and re.fullmatch(r"\s*\d+\s*", v):
        n = int(v)
    else:
        raise ApiError(400, f"{what} must be a string of digits, not {v!r}")
    if n < 0 or n >= 2 ** 64:
        raise ApiError(400, f"{what} must be between 0 and 2^64-1")
    return n


# ---------------------------------------------------------------------------
# config and roots
# ---------------------------------------------------------------------------

def config_path(ctx: Context) -> str:
    return os.path.join(ctx.user_dir, "default", "seriesmith", "config.json")


def load_roots(ctx: Context) -> list[str]:
    p = config_path(ctx)
    if os.path.isfile(p):
        try:
            with open(p, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as e:
            raise ApiError(500, f"{p} is unreadable: {e}")
        roots = data.get("roots") if isinstance(data, dict) else None
        return [r for r in (roots or []) if isinstance(r, str) and r]
    env = ctx.env.get("SERIESMITH_ROOTS", "")
    return [r for r in env.split(os.pathsep) if r.strip()]


def load_config(ctx: Context) -> dict:
    """The editor's config file, {} when there is none."""
    p = config_path(ctx)
    if not os.path.isfile(p):
        return {}
    try:
        with open(p, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as e:
        raise ApiError(500, f"{p} is unreadable: {e}")
    return data if isinstance(data, dict) else {}


def review_copy(ctx: Context) -> bool:
    """Whether a render also leaves the workflow's own copy in ComfyUI's output
    folder (config `review_copy`, off by default).

    Only a target whose binding keeps `review_nodes` has one at all
    (minimax_h3_ref2va's SaveVideo / CreateVideo branch): every take is written
    into the episode by the saver, so the second copy is a convenience for
    watching in ComfyUI, and it is off unless asked for."""
    return bool(load_config(ctx).get("review_copy", False))


def config_json(ctx: Context) -> dict:
    return {"roots": load_roots(ctx), "comfy": ctx.comfy_url,
            "review_copy": review_copy(ctx), "version": CONFIG_VERSION}


def _real(p: str) -> str:
    return os.path.normcase(os.path.realpath(os.path.abspath(p)))


def _inside(path: str, root: str) -> bool:
    try:
        return os.path.commonpath([path, root]) == root
    except ValueError:                                    # another drive
        return False


def check_ep(ctx: Context, ep) -> str:
    """The episode folder `ep` (absolute, inside a configured root), or ApiError.

    Validating it also puts that show's own targets in force for this thread
    (Phase 12: `<show>/targets/<id>/target.json`), so every loader below —
    planning, a retarget, readiness — sees them without being passed the root.
    Only a folder that passed the checks above is registered, and the route
    wrapper clears them before each handler."""
    if not ep or not isinstance(ep, str):
        raise ApiError(400, "ep is required: the episode's absolute folder path")
    if not os.path.isabs(ep):
        raise ApiError(400, f"ep must be an absolute path, not {ep!r}")
    real = _real(ep)
    if not any(_inside(real, _real(r)) for r in load_roots(ctx)):
        raise ApiError(403, f"{ep} is not inside a configured root "
                            "(set them with PUT /seriesmith/config)")
    if not os.path.isdir(ep):
        raise ApiError(404, f"no episode folder at {ep}")
    ep = os.path.abspath(ep)
    TG.add_thread_root(ep)
    return ep


def check_pass(v, default: str = DEFAULT_PASS) -> str:
    if v is None or v == "":
        return default
    if v not in PASSES:
        raise ApiError(400, f"pass must be 'final' or 'proxy', not {v!r}")
    return v


def check_shot(v) -> str:
    if not v or not isinstance(v, str):
        raise ApiError(400, "shot is required")
    return v


def check_take(v, what: str = "take", nullable: bool = False) -> int | None:
    if v is None and nullable:
        return None
    if isinstance(v, bool) or not isinstance(v, int) or v < 1:
        if isinstance(v, str) and v.strip().isdigit() and int(v) >= 1:
            return int(v)
        raise ApiError(400, f"{what} must be a take number (1 or more)")
    return v


def body_dict(body) -> dict:
    if not isinstance(body, dict):
        raise ApiError(400, "the request body must be a JSON object")
    return body


def take_event(ctx: Context, ep: str, t, status: str | None = None) -> None:
    ctx.emit("seriesmith.take", {"ep": ep, "pass": t.pass_, "shot": t.shot, "take": t.take,
                             "status": status or t.status,
                             "thumb": E.rel(ep, t.paths.thumb)})


def episode_event(ctx: Context, ep: str) -> None:
    ctx.emit("seriesmith.episode", {"ep": ep})


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------

@handler
def get_config(ctx: Context, query: dict):
    return 200, config_json(ctx)


@handler
def put_config(ctx: Context, body):
    body = body_dict(body)
    roots = body.get("roots")
    if not isinstance(roots, list) or not all(isinstance(r, str) and r.strip() for r in roots):
        raise ApiError(400, "roots must be a list of folder paths")
    missing = [r for r in roots if not os.path.isdir(r)]
    if missing:
        raise ApiError(400, "no such folder: " + ", ".join(missing))
    clean = []
    for r in roots:
        a = os.path.abspath(r)
        if os.path.normcase(a) not in {os.path.normcase(c) for c in clean}:
            clean.append(a)
    keep = body.get("review_copy", load_config(ctx).get("review_copy", False))
    if not isinstance(keep, bool):
        raise ApiError(400, "review_copy must be true or false")
    T.write_json(config_path(ctx), {"roots": clean, "review_copy": keep,
                                    "version": CONFIG_VERSION})
    return 200, config_json(ctx)


# ---------------------------------------------------------------------------
# episodes
# ---------------------------------------------------------------------------

@handler
def get_episodes(ctx: Context, query: dict):
    return 200, E.find_episodes(load_roots(ctx))


def sweep(ctx: Context, ep: str, pass_: str, listed: dict | None = None) -> list:
    """Close queued takes whose job is gone (see edit.sweep_takes; `listed`
    gets the takes it listed). A ComfyUI that doesn't answer means no sweep
    this time, not an error."""
    try:
        changed = E.sweep_takes(ep, pass_, ctx.comfy, listed=listed)
    except FileNotFoundError:
        raise
    except Exception:
        if listed is not None:
            listed.clear()                    # cut short: its listing isn't to be trusted
        return []
    for t in changed:
        take_event(ctx, ep, t)
    return changed


@handler
def get_episode(ctx: Context, query: dict):
    ep = check_ep(ctx, query.get("ep"))
    pass_ = check_pass(query.get("pass"))
    J.load_shotlist(ep, pass_)                           # 404 before touching ComfyUI
    listed: dict = {}
    changed = sweep(ctx, ep, pass_, listed)
    # the sweep's listing serves the status too, unless it closed a take
    return 200, seeds_out(E.episode_status(ep, pass_, listed=None if changed else listed))


@handler
def get_shot(ctx: Context, query: dict):
    """The inspector's detail for one shot. `target` (P9, optional) answers for a
    ONE-OFF run on that video target instead of the shot's own -- the size and
    length a redo there would really produce, since the frame grid is the
    target's. Nothing is saved; 400 for a target that isn't there."""
    ep = check_ep(ctx, query.get("ep"))
    pass_ = check_pass(query.get("pass"))
    shot = check_shot(query.get("shot"))
    target = _opt_target(query.get("target"))
    try:
        detail = E.shot_detail(ep, pass_, shot, target=target)
    except KeyError as e:
        raise ApiError(404, e.args[0])
    return 200, seeds_out(detail)


@handler
def get_browse(ctx: Context, query: dict):
    """Folder picker. Not limited to the roots: it is how roots are chosen.
    Lists folder names only, never file contents."""
    try:
        return 200, E.browse(query.get("path") or None, query.get("files") or None)
    except ValueError as e:
        raise ApiError(400, str(e))
    except FileNotFoundError as e:
        raise ApiError(404, str(e))
    except PermissionError as e:
        raise ApiError(403, str(e))


@handler
def post_build(ctx: Context, body):
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep"))
    result = E.build_episode(ep)
    episode_event(ctx, ep)
    return 200, result


@handler
def post_episode_new(ctx: Context, body):
    """A new episode: `<parent>/<name>/` with a series config and a script that
    build (source.new_episode).

    `parent` is the folder the episodes live in — the show's folder, not the
    episode's — and must be inside a configured root. 400 for a name that isn't
    a folder name, 409 when the folder is already there."""
    body = body_dict(body)
    parent = check_folder(ctx, body.get("parent"), "parent")
    for k in ("show", "series", "script"):
        if body.get(k) is not None and not isinstance(body.get(k), str):
            raise ApiError(400, f"{k} must be text")
    res = P.H.new_episode(parent, body.get("name"),
                          series_id=body.get("series_id") or None,
                          title=body.get("title") or None,
                          show=body.get("show") or None,
                          series=body.get("series"), script=body.get("script"))
    episode_event(ctx, res["ep"])
    return 200, res


@handler
def post_clips_ensure(ctx: Context, body):
    """Simple mode's Clips project (clips.ensure_clips): in `root` (default the
    first project root), made the first time. {"ep", "made"}."""
    from seriesmith import clips as CL
    body = body_dict(body)
    roots = load_roots(ctx)
    root = body.get("root") or (roots[0] if roots else None)
    if not root:
        raise ApiError(409, "no project folder yet: add one (Project folders) first")
    root = check_folder(ctx, root, "root")
    res = CL.ensure_clips(root)
    if res["made"]:
        episode_event(ctx, res["ep"])
    return 200, res


@handler
def post_clips_new(ctx: Context, body):
    """A Simple project of its own (clips.new_project): {"title", "root"?}
    (default the first project root) -> {"ep"}."""
    from seriesmith import clips as CL
    body = body_dict(body)
    roots = load_roots(ctx)
    root = body.get("root") or (roots[0] if roots else None)
    if not root:
        raise ApiError(409, "no project folder yet: add one (Project folders) first")
    root = check_folder(ctx, root, "root")
    res = CL.new_project(root, body.get("title"))
    episode_event(ctx, res["ep"])
    return 200, res


@handler
def post_clip_queue(ctx: Context, body):
    """Queue a clip (a shot of the Clips project, or of any episode): the
    pictures it still needs are generated first (clips.needed_refs; one
    already on its way is waited for, not made twice), then a step waits for
    them all, makes each live and asks for `takes` renders of the shot
    (POST /seriesmith/render). With every picture there, the renders are
    asked for at once. Body {ep, shot, pass (proxy), takes (1-8), backend?}.
    `still` (with `image_target`) makes a picture instead: `takes` candidates
    of the shot's first keyframe (its script says `first: generate`) on that
    image model, made live when they're done; an edit model waits for the
    people's and the place's pictures it draws from, a text-to-image one
    doesn't. Returns {"refs": [{ref, view, take, prompt_id}], "waiting_on":
    [ids], "step": id | null, "renders": [render answers], "stills": [...]}."""
    from seriesmith import clips as CL
    from seriesmith import refs as R
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep"))
    pass_ = check_pass(body.get("pass"), "proxy")
    shot = check_shot(body.get("shot"))
    takes = body.get("takes", 1)
    if isinstance(takes, bool) or not isinstance(takes, int) or not 1 <= takes <= 8:
        raise ApiError(400, "takes must be 1 to 8")
    backend = _opt_backend(ctx, body)
    still = bool(body.get("still"))
    image_target = body.get("image_target") if still else None
    edit_model = False
    if still:
        if not isinstance(image_target, str) or not image_target:
            raise ApiError(400, "a still needs image_target: the image model that makes it")
        try:
            it = TG.load_target(image_target, "image")
        except Exception as e:                           # noqa: BLE001
            raise ApiError(400, f"no image model {image_target!r}: {e}")
        edit_model = (it.spec.get("capabilities") or {}).get("mode") == "edit"
    if ctx.runner is None:
        raise ApiError(409, "clips need seriesmith's queue (seriesmith serve)")
    if not any(s["id"] == shot for d, i in J.episode_shots(ep, pass_) for s in [d["shots"][i]]):
        raise ApiError(404, f"{shot} isn't in {pass_}'s shotlist: build first")
    p ={"ep": ep, "pass": pass_, "shot": shot, "takes": takes, "backend": backend,
         "still": still, "image_target": image_target}
    need = [r for r in CL.needed_refs(ep, pass_, shot) if not r.id.startswith(f"shot:{shot}:")]
    if still and not edit_model:
        need = []                                        # words only: nothing to draw from
    if not need:
        return 200, {"refs": [], "waiting_on": [], "step": None, "renders": _clip_renders(ctx, p),
                     "stills": _clip_stills(ctx, p) if still else []}
    made, waiting = [], []
    for ref in need:
        on_way = CL.queued_takes(ref)
        if on_way:
            waiting += on_way
            continue
        status, data = _generate(ctx, {"ep": ep, "ref": ref.id, "count": 1,
                                       **({"backend": backend} if backend else {})})
        if status >= 400:
            raise ApiError(status, f"{ref.id}: {data.get('error')}")
        for q in data.get("queued") or []:
            made.append({k: q.get(k) for k in ("ref", "view", "take", "prompt_id")})
            if q.get("prompt_id"):
                waiting.append(q["prompt_id"])
    step = _clip_step(ctx, {**p, "refs": [r.id for r in need]})
    return 200, {"refs": made, "waiting_on": waiting, "step": step, "renders": [], "stills": []}


# -- steps: seriesmith's own jobs that ask for others once pictures are made.
# Each is made from plain parameters (its `spec`), so the queue's journal
# keeps it and a restart makes it again (rebuild_step, standalone.recover);
# each waits on its pictures' takes (still queued, on a live job) rather than
# on job ids, which a restart changes.

def _generate(ctx: Context, body: dict):
    """POST /seriesmith/refs/generate from inside another request or a step,
    its jobs kept with this request (runner.ASKED), not the one around it: a
    job still waiting at a restart is asked for again as itself (a clip's
    picture, a frame's edit), not as the whole clip or frame again."""
    from seriesmith.runner import ASKED
    before = getattr(ASKED, "req", None)
    ASKED.req = {"path": "/seriesmith/refs/generate", "body": body}
    try:
        return post_refs_generate(ctx, body)
    finally:
        ASKED.req = before


def _refs_waiting(ctx: Context, ep: str, rids: list, views: list | None = None):
    """wait() for a step: true while any take of the refs `rids` (their
    `views`; None: every view) is queued on a job that's alive."""
    from seriesmith import refs as R
    queue = ctx.runner.queue

    def wait() -> bool:
        alive = queue.alive()
        s = R.load_series(ep)
        for rid in rids:
            ref = R.find_ref(s, rid)
            for v in (views if views is not None else
                      (R.VIEW_TAGS if ref.has_views else [None])):
                for t in R.list_takes(ref, v):
                    if t.status == "queued" and (t.sidecar or {}).get("comfy_prompt_id") in alive:
                        return True
        return False
    return wait


def _clip_stills(ctx: Context, p: dict) -> list:
    """A still clip's picture: `takes` candidates of its first keyframe on the
    image model; each one finished is made live by the refs listing
    (auto_pick) when there is none yet."""
    keyframe = f"shot:{p['shot']}:first"
    status, data = _generate(ctx, {"ep": p["ep"], "ref": keyframe, "count": p["takes"],
                                   "target": p["image_target"],
                                   **({"backend": p["backend"]} if p.get("backend") else {})})
    if status >= 400:
        raise ApiError(status, f"{keyframe}: {data.get('error')}")
    return data.get("queued") or []


def _clip_renders(ctx: Context, p: dict) -> list:
    if p.get("still"):
        return []
    body = {"ep": p["ep"], "pass": p["pass"], "shots": [p["shot"]], "redo": True,
            **({"backend": p["backend"]} if p.get("backend") else {})}
    out = []
    for _ in range(p["takes"]):
        status, data = post_render(ctx, body) if ctx.runner.ask is None \
            else ctx.runner.ask("/seriesmith/render", body)
        out.append(data)
    return out


def _clip_step(ctx: Context, p: dict) -> str:
    """A clip's step: once its pictures (`p["refs"]`) are made, each is made
    live and its renders (or its still) asked for."""
    from seriesmith import clips as CL
    from seriesmith import refs as R
    ep, pass_, shot = p["ep"], p["pass"], p["shot"]

    def then(report) -> str:
        s = R.load_series(ep)
        for rid in p["refs"]:
            ref = R.find_ref(s, rid)
            for res in R.auto_pick(s, ref):
                report(line=f"{rid}: {getattr(res, 'note', '') or 'live'}")
        left = [r.id for r in CL.needed_refs(ep, pass_, shot)
                if not r.id.startswith(f"shot:{shot}:")]
        if left:
            raise RuntimeError(f"its pictures didn't all come out ({', '.join(left)}): "
                               "see the Refs tab, then queue it again")
        if p.get("still"):
            report(line=f"{len(_clip_stills(ctx, p))} picture(s) asked for")
            return "succeeded"
        got = _clip_renders(ctx, p)
        report(line=f"{p['takes']} take(s) asked for")
        bad = [d for d in got if d.get("errors")]
        if bad:
            raise RuntimeError(str(bad[0]["errors"][0].get("error"))[:400])
        return "succeeded"
    return ctx.runner.enqueue_step(
        f"{os.path.basename(os.path.normpath(ep))} {shot}: render once its pictures are made",
        then, info={"ep": ep, "shot": shot, "pass": pass_},
        wait=_refs_waiting(ctx, ep, p["refs"]), spec={"step": "clip", "params": p})


def _frame_gen(ctx: Context, p: dict, view, edit: dict, prompt: str) -> list[str]:
    """An edit of a frame-made ref's `view` queued: its job ids."""
    target = p.get("target")
    status, data = _generate(ctx, {"ep": p["ep"], "ref": p["ref"], "view": view, "edit": edit,
                                   "prompt": prompt, **({"target": target} if target else {})})
    if status >= 400:
        raise ApiError(status, data.get("error") or "the edit wasn't queued")
    return [q["prompt_id"] for q in data.get("queued") or [] if q.get("prompt_id")]


def _newest_ok(ep: str, rid: str, view):
    from seriesmith import refs as R
    ok = [x for x in R.list_takes(R.find_ref(R.load_series(ep), rid), view) if x.status == "ok"]
    return ok[-1] if ok else None


def _pick_newest(ep: str, rid: str, view, report=None) -> None:
    from seriesmith import refs as R
    s2 = R.load_series(ep)
    r2 = R.find_ref(s2, rid)
    nt = _newest_ok(ep, rid, view)
    if nt is not None:
        try:
            R.pick_take(s2, r2, view, nt.take)
        except Exception as e:                           # noqa: BLE001  a stitch waits for the rest
            if report:
                report(line=f"{view or rid}: picked t{nt.take:02d} ({e})")


def _frame_step(ctx: Context, p: dict) -> str:
    """A frame-made ref's step (post_refs_from_frame): once the frame's edit
    is done, it is picked (`pick`) and -- a character with `views` -- the
    other three views drawn from it, then picked in turn (_views_step)."""
    from seriesmith import refs as R
    ep, rid, view = p["ep"], p["ref"], p["view"]

    def then(report) -> str:
        # the first view as it came out, then the others drawn from it
        if p.get("pick"):
            _pick_newest(ep, rid, view, report)
        ref = R.find_ref(R.load_series(ep), rid)
        if not (p.get("views") and ref.has_views):
            return "succeeded"
        others = [v for v in R.VIEW_TAGS if v != view]
        ids = []
        for v in others:
            nt = _newest_ok(ep, rid, view)
            ids += _frame_gen(ctx, p, v, {"take": None, "from_view": view} if p.get("pick") else
                              {"take": nt.take if nt else p["frame_take"], "from_view": view},
                              R.view_from(v))
        report(line=f"{len(ids)} view(s) asked for, from {view}")
        if p.get("pick"):
            _views_step(ctx, {"ep": ep, "ref": rid, "views": others})
        return "succeeded"
    return ctx.runner.enqueue_step(
        f"{rid}: from the frame, then its views" if p.get("views") else f"{rid}: from the frame",
        then, info={"ep": ep, "ref": rid}, wait=_refs_waiting(ctx, ep, [rid], [view]),
        spec={"step": "frame", "params": p})


def _views_step(ctx: Context, p: dict) -> str:
    """Once a frame-made character's other views are drawn, each is picked."""
    ep, rid = p["ep"], p["ref"]

    def done(report) -> str:
        for v in p["views"]:
            _pick_newest(ep, rid, v, report)
        return "succeeded"
    return ctx.runner.enqueue_step(f"{rid}: pick its views", done, info={"ep": ep, "ref": rid},
                                   wait=_refs_waiting(ctx, ep, [rid], p["views"]),
                                   spec={"step": "views", "params": p})


STEPS = {"clip": _clip_step, "frame": _frame_step, "views": _views_step}


def rebuild_step(ctx: Context, resume: dict) -> str | None:
    """A step the journal kept (its `resume`: {"kind": "step", "step",
    "params"}) made again after a restart: its id, or None for one this
    version doesn't know."""
    make = STEPS.get(resume.get("step") or "")
    params = resume.get("params")
    if make is None or not isinstance(params, dict) or ctx.runner is None:
        return None
    return make(ctx, params)


def _video_path(s, video) -> str:
    """A kept video's path (relative to the episode, as POST /refs/video
    answers) as a file in the show's refs/_videos/."""
    from seriesmith import refs as R
    if not isinstance(video, str) or not video.strip():
        raise ApiError(400, "video must be the video's path, as POST /seriesmith/refs/video gave it")
    path = os.path.normpath(os.path.join(s.ep, video))
    d = os.path.normpath(R.videos_dir(s))
    if os.path.normcase(os.path.dirname(path)) != os.path.normcase(d):
        raise ApiError(400, f"{video} isn't one of the show's videos (refs/{R.VIDEOS_DIR}/)")
    if not os.path.isfile(path):
        raise ApiError(404, f"no video at {video}")
    return path


@handler
def post_refs_video(ctx: Context, body):
    """A video of your own to take frames from (docs/PLAN.md step 5): kept in
    the show's refs/_videos/ (refs.import_video), where the editor plays it.
    `source_path` (a file on this machine) or `file` (multipart). Returns
    {path (relative to the episode), name, size, modified, copied, duration}."""
    from seriesmith import refs as R
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep"))
    s = _series(ep)
    up = body.get("file")
    src = body.get("source_path")
    if isinstance(up, Upload):
        if up.size > MAX_UPLOAD:
            raise ApiError(413, f"the file is over {MAX_UPLOAD // (1024 * 1024)} MB: "
                                "pick it from this machine's folders instead")
        return 200, R.import_video(s, up.path, up.filename or "")
    if up is not None:
        raise ApiError(400, "file must be sent as multipart/form-data")
    if isinstance(src, str) and src.strip():
        return 200, R.import_video(s, src.strip())
    raise ApiError(400, "send source_path (a video on this machine) or a multipart `file`")


@handler
def get_refs_videos(ctx: Context, query: dict):
    """The videos kept to take frames from, newest first."""
    from seriesmith import refs as R
    ep = check_ep(ctx, query.get("ep"))
    return 200, {"videos": R.list_videos(_series(ep))}


@handler
def post_refs_from_frame(ctx: Context, body):
    """A character or a place from a frame of a take (docs/PLAN.md step 13):
    the frame becomes a candidate of `ref` (a character's `view`, default the
    three-quarter), then -- with an `instruction` -- an edit model makes it
    into the reference ("cut out the woman in the red coat onto a plain
    background"; "remove the people"); for a character with `views`, its
    other three views are then drawn from that one. With `pick` (a new one)
    each comes out picked, so the sheet stitches; without, they're
    candidates beside what it has. Body {ep, pass, shot, take, frame,
    ref, view?, instruction?, target? (an edit model), views?, pick?}; or,
    a video of your own (POST /seriesmith/refs/video) instead of a take,
    {ep, video (its path, relative to the episode), time (seconds), ref, ...}.
    Returns {"frame": take, "edits": [ids], "step": id | null}."""
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep"))
    video = body.get("video")
    if video is None:
        pass_ = check_pass(body.get("pass"))
        shot = check_shot(body.get("shot"))
        take_n = check_take(body.get("take"), "take")
        frame = body.get("frame", 0)
        if isinstance(frame, str) and frame.lstrip("-").isdigit():
            frame = int(frame)
    s = _series(ep)
    ref = _ref(s, body.get("ref"))
    if ref.is_audio:
        raise ApiError(400, f"{ref.id} is a voice: a frame is a picture")
    view = body.get("view") or ("01_threequarter" if ref.has_views else None)
    instruction = (body.get("instruction") or "").strip()
    target = body.get("target") or None
    views, pick = bool(body.get("views")), bool(body.get("pick"))
    try:
        if video is not None:
            path = _video_path(s, video)
            t = R.frame_from_video(s, ref, view, path, body.get("time", 0),
                                   note=f"from {os.path.basename(path)}")
        else:
            src = T.get_take(ep, pass_, shot, take_n)
            if src is None or not src.has_video:
                raise ApiError(404, f"{shot} {pass_} t{take_n:02d} has no video")
            t, _source = R.frame_into(s, ref, view, src, pass_, frame,
                                      note=f"from {shot} t{take_n:02d}")
    except R.RefError as e:
        raise ApiError(400, str(e))
    except R.FfmpegMissing as e:
        raise ApiError(500, str(e))
    ref_event(ctx, ep, ref.id, view, t.take, "ok")
    p = {"ep": ep, "ref": ref.id, "view": view, "views": views, "pick": pick, "target": target,
         "frame_take": t.take}
    edits = _frame_gen(ctx, p, view, {"take": t.take}, instruction) if instruction else []
    if not edits:
        if pick:
            _pick_newest(ep, ref.id, view)
        if not (views and ref.has_views):
            return 200, {"frame": R.take_json(ep, ref, t), "edits": [], "step": None}
    if ctx.runner is None:
        raise ApiError(409, "this needs seriesmith's queue (seriesmith serve)")
    step = _frame_step(ctx, p)
    return 200, {"frame": R.take_json(ep, ref, t), "edits": edits, "step": step}


@handler
def get_episode_template(ctx: Context, query: dict):
    """The new episode wizard's start: what an episode made in `parent` (or in
    a new show folder `show` inside it) would start from (source.episode_template)."""
    parent = check_folder(ctx, query.get("parent"), "parent")
    return 200, P.H.episode_template(parent, query.get("show") or None)


@handler
def post_import(ctx: Context, body):
    """seriesmith: a series config and a stack of scripts in, episode folders
    out (source.import_series). Body: {"parent": a folder of shows inside a
    root, "show": the show's folder to make or fill (optional: the episodes go
    straight into `parent`), "series": the series config's text, for every
    script without its own (optional when each has one), "scripts": [{"name":
    the file's name, "text", "series": its own series config's text
    (optional)}]}. Nothing is built."""
    body = body_dict(body)
    parent = check_folder(ctx, body.get("parent"), "parent")
    series = body.get("series") or None
    if series is not None and not isinstance(series, str):
        raise ApiError(400, "series must be the series config's text")
    scripts = body.get("scripts")
    if (not isinstance(scripts, list) or not scripts
            or not all(isinstance(s, dict) and isinstance(s.get("text"), str)
                       and isinstance(s.get("series") or "", str) for s in scripts)):
        raise ApiError(400, "scripts must be a list of {name, text, series?}")
    show = body.get("show") or None
    if show is not None and not isinstance(show, str):
        raise ApiError(400, "show must be a folder name")
    res = P.H.import_series(parent, series,
                            [(str(s.get("name") or ""), s["text"], s.get("series") or None)
                             for s in scripts], show=show)
    for e in res["episodes"]:
        episode_event(ctx, e["ep"])
    return 200, res


def check_folder(ctx: Context, path, what: str = "folder") -> str:
    """An existing folder inside a configured root (the same check as an
    episode's, for a folder that isn't an episode yet)."""
    if not path or not isinstance(path, str):
        raise ApiError(400, f"{what} is required: an absolute folder path")
    if not os.path.isabs(path):
        raise ApiError(400, f"{what} must be an absolute path, not {path!r}")
    if not any(_inside(_real(path), _real(r)) for r in load_roots(ctx)):
        raise ApiError(403, f"{path} is not inside a configured root "
                            "(set them with PUT /seriesmith/config)")
    if not os.path.isdir(path):
        raise ApiError(404, f"no folder at {path}")
    return os.path.abspath(path)


# ---------------------------------------------------------------------------
# files
# ---------------------------------------------------------------------------

@handler
def get_file(ctx: Context, query: dict):
    """(200, {"path", "content_type"}) for the adapter to stream."""
    ep = check_ep(ctx, query.get("ep"))
    full, rel = ep_file(ctx, ep, query.get("path"))
    ext = os.path.splitext(full)[1].lower()
    return 200, {"path": full, "content_type": CONTENT_TYPES.get(ext, "application/octet-stream")}


THUMB_WIDTHS = (128, 256, 512, 1024)
THUMB_EXT = (".png", ".jpg", ".jpeg", ".webp")


@handler
def get_thumb(ctx: Context, query: dict):
    """A picture inside the episode (as GET /seriesmith/file finds it), made
    small: `w` wide (rounded up to one of THUMB_WIDTHS), a JPEG kept in the
    settings folder's thumbs/ by the file's path, size and time, so it is made
    once (a shared ref's for every episode) and again when the file changes.
    The Refs tab shows hundreds of reference pictures at a few dozen pixels
    each; the files are full size. A picture Pillow can't shrink is served as
    it is."""
    ep = check_ep(ctx, query.get("ep"))
    full, _ = ep_file(ctx, ep, query.get("path"))
    try:
        want = int(query.get("w") or 256)
    except (TypeError, ValueError):
        raise ApiError(400, f"w must be a width in pixels, not {query.get('w')!r}")
    width = next((x for x in THUMB_WIDTHS if x >= want), THUMB_WIDTHS[-1])
    ext = os.path.splitext(full)[1].lower()
    small = thumb_file(ctx, full, width) if ext in THUMB_EXT else None
    if small is None:
        return 200, {"path": full, "content_type": CONTENT_TYPES.get(ext, "application/octet-stream")}
    return 200, {"path": small, "content_type": "image/jpeg"}


def thumb_file(ctx: Context, full: str, width: int) -> str | None:
    """The thumbnail of `full` at `width`, made when missing (None: it can't be)."""
    import hashlib
    try:
        st = os.stat(full)
    except OSError:
        return None
    # "upright": thumbnails made before a phone photo's orientation was read
    # came out sideways, and are made again rather than served
    key = hashlib.sha1(f"{os.path.normcase(os.path.abspath(full))}|{st.st_mtime_ns}|{st.st_size}|{width}"
                       f"|upright".encode("utf-8")).hexdigest()
    out = os.path.join(ctx.user_dir, "default", "seriesmith", "thumbs", key[:2], key + ".jpg")
    if os.path.isfile(out):
        return out
    try:
        from PIL import Image, ImageOps
        with Image.open(full) as src:
            # a JPEG decodes small to begin with; a photo shot sideways (its
            # orientation tag 5-8) is turned after, so its sides swap
            sideways = src.getexif().get(0x0112) in (5, 6, 7, 8)
            src.draft("RGB", (width * 4, width) if sideways else (width, width * 4))
            im = ImageOps.exif_transpose(src)            # a phone photo, the way up it was shot
            im.thumbnail((width, width * 4))
            if im.mode in ("RGBA", "LA", "P"):
                im = im.convert("RGBA")
                flat = Image.new("RGB", im.size, (255, 255, 255))
                flat.paste(im, mask=im.getchannel("A"))
                im = flat
            elif im.mode != "RGB":
                im = im.convert("RGB")
            tmp = F.temp_beside(out, ".jpg")          # its own: two threads may make one
            im.save(tmp, "JPEG", quality=84)
        F.replace(tmp, out)
        return out
    except Exception:                                     # noqa: BLE001 -- the original will do
        return None


def ep_file(ctx: Context, ep: str, rel, escape_status: int = 403) -> tuple[str, str]:
    """(full path, the relative path with forward slashes) of an existing file
    inside the episode (or its parent-folder series config's folder). 400 for
    a path that isn't relative or climbs out, `escape_status` for one that
    leads outside through a link, 404 for no such file."""
    if not rel or not isinstance(rel, str):
        raise ApiError(400, "path is required")
    parts = rel.replace("\\", "/").split("/")
    if (rel.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", rel) or "\x00" in rel
            or (".." in parts and not _in_series_home(ctx, ep, parts))):
        raise ApiError(400, f"path must be relative to the episode and stay inside it: {rel!r}")
    full = os.path.normpath(os.path.join(ep, *[p for p in parts if p not in ("", ".")]))
    if not (_inside(_real(full), _real(ep)) or _in_series_home(ctx, ep, parts)):
        raise ApiError(escape_status, f"{rel} leads outside the episode")
    if not os.path.isfile(full):
        raise ApiError(404, f"no file {rel} in {ep}")
    return full, "/".join(p for p in parts if p not in ("", "."))


# The folders a series config may point at outside its own episode. A show with
# one refs folder and a series config per episode (each naming `../refs/...`) is
# the arrangement a multi-episode series wants: the sheets and plates are shared,
# while an episode can still add props and locations of its own.
SHARED_DIRS = ("refs", "audio")


def _in_series_home(ctx: Context, ep: str, parts: list[str]) -> bool:
    """Whether a path that climbs out of the episode may still be served.

    Two arrangements are allowed, both of them ways a series config legitimately
    names a file above its episode, and neither reaching anything the API
    doesn't already serve for some episode:

    - the series config lives in the episode's **parent** (one config for the
      show): anything inside that folder;
    - the series config lives in the **episode** but names `../refs/...` or
      `../audio/...` (shared assets, per-episode config): only those two
      folders of the parent, so a sibling episode's renders and the show
      folder's own files stay out of reach. A sibling episode's ref
      candidates (`../<sibling>/refs/_takes/...`) are served too: a shared
      ref's live file can be another episode's pick, and its candidates are
      that episode's (refs.owner_takes).

    Either way the file must also be inside a configured root.
    """
    series_cfg = E.episode_series_config(ep)
    if not series_cfg:
        return False
    home = _real(os.path.dirname(os.path.abspath(series_cfg)))
    full = _real(os.path.join(ep, *[p for p in parts if p not in ("", ".")]))
    if not any(_inside(full, _real(r)) for r in load_roots(ctx)):
        return False
    if home != _real(ep):
        return _inside(full, home)
    show = os.path.dirname(os.path.abspath(ep))
    if any(_inside(full, _real(os.path.join(show, d))) for d in SHARED_DIRS):
        return True
    from seriesmith import refs as R
    return any(_inside(full, _real(os.path.join(sib, "refs", "_takes"))) for sib in R.sibling_episodes(ep))


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

def _opt_str(body: dict, key: str) -> str | None:
    v = body.get(key)
    if v is not None and not isinstance(v, str):
        raise ApiError(400, f"{key} must be a string or null")
    return v


def _opt_steps(v) -> int | None:
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, int) or v < 1:
        raise ApiError(400, "steps must be a whole number of 1 or more, or null")
    return v


def _opt_size(v) -> str | None:
    """A render size ("1344x768" or [1344, 768]) as "WxH", or None (the shotlist's).
    Whether the target takes it is checked when the take is planned."""
    if v is None or v == "":
        return None
    try:
        w, h = J.parse_size(v)
    except ValueError as e:
        raise ApiError(400, f"size: {e}")
    return f"{w}x{h}"


def _opt_prompt(v):
    if v is None or isinstance(v, str):
        return v
    if isinstance(v, list) and all(isinstance(x, str) for x in v):
        return list(v)
    raise ApiError(400, "prompt must be text, a list of sections, or null")


def _opt_loras(v) -> list[dict] | None:
    if v is None:
        return None
    if not isinstance(v, list):
        raise ApiError(400, "loras must be a list of {name, strength}, or null")
    out = []
    for lo in v:
        if isinstance(lo, str):
            out += J.parse_lora(lo)
            continue
        if not isinstance(lo, dict) or not isinstance(lo.get("name"), str) or not lo["name"]:
            raise ApiError(400, "each LoRA needs a name: {\"name\": ..., \"strength\": 1.0}")
        s = lo.get("strength", 1.0)
        if isinstance(s, bool) or not isinstance(s, (int, float)):
            raise ApiError(400, f"LoRA {lo['name']}: strength must be a number")
        out.append({"name": lo["name"], "strength": float(s)})
    return out


def _opt_negative(v) -> str | None:
    """A negative prompt from a request: text ("" is an explicit empty one),
    or null for not set."""
    if v is None:
        return None
    if not isinstance(v, str):
        raise ApiError(400, "negative must be text or null")
    return v


def _opt_target(v) -> str | None:
    """A video target id from a request (null: not set), 400 if unknown."""
    if v is None or v == "":
        return None
    if not isinstance(v, str):
        raise ApiError(400, "target must be a video target id or null")
    try:
        return J.check_video_target(v)
    except Exception as e:
        raise ApiError(400, str(e))


def _opt_backend(ctx: Context, body: dict) -> str | None:
    """A request's `backend` (seriesmith's queue only): where its work runs,
    or None for each job's own (jobs.backend_choice)."""
    backend = body.get("backend") if isinstance(body, dict) else None
    if backend is None:
        return None
    if not isinstance(backend, str) or J.backend_kind(backend) not in TG.BACKENDS:
        raise ApiError(400, f"backend must be one of {', '.join(TG.BACKENDS)} "
                            f"(deployment[:<target>]), not {backend!r}")
    return backend


def _drafts_asked(ep: str, asked) -> tuple[dict, str, list]:
    """from_draft ({shot: take}) checked against the proxy takes: each a
    finished Seedance draft whose task id hasn't expired. Returns
    ({shot: {"task", "take", "pass"}}, the drafts' target, [shots])."""
    if not isinstance(asked, dict) or not asked:
        raise ApiError(400, "from_draft must be {shot: its proxy draft take}")
    out, targets = {}, set()
    for shot, take_n in asked.items():
        shot = check_shot(shot)
        n = check_take(take_n, "from_draft take")
        t = T.get_take(ep, "proxy", shot, n)
        d = J.draft_of(t.sidecar if t else None)
        if t is None or t.status != "ok" or d is None:
            raise ApiError(400, f"{shot} proxy t{n:02d} isn't a finished draft")
        if d["expired"]:
            raise ApiError(409, f"{shot} proxy t{n:02d}'s draft has expired (drafts last "
                                f"{J.DRAFT_DAYS} days): render its final instead")
        out[shot] = {"task": d["task"], "take": n, "pass": "proxy"}
        targets.add((t.sidecar or {}).get("target"))
    if len(targets) != 1 or None in targets:
        raise ApiError(400, "the drafts must all be from the one model")
    return out, targets.pop(), list(out)


@handler
def get_drafts(ctx: Context, query: dict):
    """The Seedance drafts an episode's finals could be made from: each
    shot's take in the proxy cut that is a draft, with its thumbnail, when
    its task id expires, and whether the shot has a final already (the
    dialog ticks the ones without). {"drafts": [...]}."""
    ep = check_ep(ctx, query.get("ep"))
    out = []
    for e in E.cut_entries(ep, "proxy"):
        t, n, ok = E.cut_take(ep, e)
        d = J.draft_of(t.sidecar if t else None) if ok else None
        if d is None:
            continue
        finals = [x for x in T.list_takes(ep, "final", e.shot) if x.status == "ok"]
        from_it = [x.take for x in finals
                   if ((x.sidecar or {}).get("from_draft") or {}).get("task") == d["task"]]
        out.append({"shot": e.shot, "take": n, "thumb": E.rel(ep, t.paths.thumb),
                    "mp4": E.rel(ep, t.paths.mp4), "expires": d["expires"],
                    "expired": d["expired"], "finals": len(finals), "made_from_it": from_it,
                    "target": (t.sidecar or {}).get("target")})
    return 200, {"drafts": out}


@handler
def post_render(ctx: Context, body):
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep"))
    pass_ = check_pass(body.get("pass"))
    shots = body.get("shots")
    if shots is not None and (not isinstance(shots, list)
                              or not all(isinstance(s, str) and s for s in shots)):
        raise ApiError(400, "shots must be a list of shot ids (or null for every shot)")
    seed_mode = body.get("seed_mode") or "auto"
    if seed_mode not in ("auto", "new", "same"):
        raise ApiError(400, f"seed_mode must be auto, new or same, not {seed_mode!r}")
    redo = body.get("redo", False)
    if not isinstance(redo, bool):
        raise ApiError(400, "redo must be true or false")
    allow_missing = body.get("allow_missing_refs", False)
    if not isinstance(allow_missing, bool):
        raise ApiError(400, "allow_missing_refs must be true or false")
    allow_mismatch = body.get("allow_model_mismatch", False)
    if not isinstance(allow_mismatch, bool):
        raise ApiError(400, "allow_model_mismatch must be true or false")
    # keep the frames as a PNG sequence beside the take (H3SaveShot's
    # save_frames). Absent leaves the workflow's own setting alone.
    save_frames = body.get("save_frames")
    if save_frames is not None and not isinstance(save_frames, bool):
        raise ApiError(400, "save_frames must be true or false")
    # keep each take's latent for an upscale (null: the pass's default)
    save_latent = body.get("save_latent")
    if save_latent is not None and not isinstance(save_latent, bool):
        raise ApiError(400, "save_latent must be true, false or null")
    # where every shot of this request renders (seriesmith's queue only;
    # absent: each shot's own, jobs.backend_choice)
    backend = _opt_backend(ctx, body)
    template = J.RenderRequest(
        shot_id="", redo=redo, seed=seed_in(body.get("seed")), seed_mode=seed_mode,
        model=_opt_str(body, "model") or None, loras=_opt_loras(body.get("loras")),
        steps=_opt_steps(body.get("steps")), prompt=_opt_prompt(body.get("prompt")),
        parent_take=check_take(body.get("parent_take"), "parent_take", nullable=True),
        note=_opt_str(body, "note") or "", allow_missing_refs=allow_missing,
        target=_opt_target(body.get("target")), allow_model_mismatch=allow_mismatch,
        negative=_opt_negative(body.get("negative")), save_latent=save_latent,
        size=_opt_size(body.get("size")))
    J.load_shotlist(ep, pass_)                           # 404 before anything else
    if body.get("from_draft") is not None:
        # finals made from Seedance drafts: {shot: its proxy draft take}
        if pass_ != "final":
            raise ApiError(400, "from_draft makes final takes: pass must be final")
        template.from_draft, template.target, shots = _drafts_asked(ep, body["from_draft"])
    workflows: dict = {}

    def base_for(target_id: str) -> dict:
        """The workflow of a job's target, resolved once per request; a target
        whose workflow can't be read fails every shot on it (reported per shot)."""
        if target_id not in workflows:
            t = TG.load_target(target_id, "video")
            b = t.binding
            try:
                base, _ = J.target_workflow(t, None, ctx.comfy_url)
                if b.loader_class:
                    J.node_of(base, b.loader_class)
                if not (b.saver.get("replace") and any(
                        v["class_type"] == b.saver["replace"]["class_type"] for v in base.values())):
                    J.node_of(base, b.saver_class)
                workflows[target_id] = base
            except Exception as e:
                workflows[target_id] = RuntimeError(f"no usable {b.workflow_name}: {e}")
        got = workflows[target_id]
        if isinstance(got, Exception):
            raise got
        return got

    # continuity: each `first: continuity` shot's first frame is cut again as its
    # render starts, from the take the cut uses then (a take queued ahead of it in
    # this run has rendered by then), so a whole chain queues at once; one with
    # nothing to start from isn't queued (it would render without its first frame)
    cont = continuity_before_render(ep, pass_, shots)
    template.continuity = cont["live"] or None
    held = {e["shot"] for e in cont["errors"]}
    todo = shots
    if held or cont["live"]:
        todo = [s for s in (shots if shots is not None else J.built_order(ep, pass_)) if s not in held]
    if cont["live"]:
        # a chain queues in cut order: each shot behind the one it continues
        order = {e.shot: n for n, e in enumerate(E.cut_entries(ep, pass_))}
        todo.sort(key=lambda s: order.get(s, len(order)))
    if todo == []:
        result = {"queued": [], "skipped": [], "errors": []}
    else:
        result = E.queue_shots(ep, pass_, todo, template, ctx.comfy, base_for,
                               model_resolve=ctx.model_resolve, model_cache=ctx.model_cache,
                               model_list=ctx.model_choices, review_copy=review_copy(ctx),
                               save_frames=save_frames, runner=ctx.runner, backend=backend)
    result["errors"] += [{"shot": e["shot"], "error": e["error"]} for e in cont["errors"]]
    result["continuity"] = cont["cut"]
    result["continuity_at_start"] = [{"shot": w["shot"], "after": wait_reason(w)}
                                     for w in cont["wait"]]
    for c in cont["cut"]:
        ref_event(ctx, ep, f"shot:{c['shot']}:first", None, None, "ok")
    for q in result["queued"]:
        # "queued" even if the job has already finished: the saver sends its own event
        take_event(ctx, ep, T.get_take(ep, pass_, q["shot"], q["take"]), "queued")
    for err in result["errors"]:
        if err.get("take"):
            take_event(ctx, ep, T.get_take(ep, pass_, err["shot"], err["take"]))
    if result["queued"] or any(e.get("take") for e in result["errors"]):
        episode_event(ctx, ep)
    return 200, seeds_out(result)


def wait_reason(w: dict) -> str:
    """Where a chained continuity shot's first frame will come from (refresh_continuity's `wait`)."""
    what = (f"{w['after']} t{w['take']:02d}, still rendering" if w.get("take")
            else f"{w['after']}'s new take in this run")
    if w.get("chain"):
        return f"it continues {what} (its latent, else its last frames)"
    return f"its first frame is cut from {what} when its render starts"


def continuity_before_render(ep: str, pass_: str, shots) -> dict:
    """refs.refresh_continuity for a render's shots ({"cut", "wait", "errors"});
    nothing to do for an episode whose series config can't be read."""
    try:
        s = R.load_series(ep)
    except Exception:
        return {"live": {}, "cut": [], "wait": [], "errors": []}
    # seriesmith's queue cuts a first frame as the render starts (runner.enqueue_render)
    return R.refresh_continuity(s, pass_, shots, cut_at_start=True)


@handler
def post_cancel(ctx: Context, body):
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep"))
    pass_ = check_pass(body.get("pass"))
    shot = check_shot(body.get("shot"))
    take = check_take(body.get("take"))
    owned = T.get_take(ep, pass_, shot, take)
    sc = (owned.sidecar or {}) if owned else {}
    if sc.get("queue") == "seriesmith" and sc.get("status") == "queued":
        # seriesmith's queue has it: a waiting job leaves it, a running one stops
        try:
            ctx.runner.queue.cancel(sc.get("comfy_prompt_id"))
            # a running one stops in a moment: answer with how it ended
            from seriesmith import runner as RN
            RN.wait(ctx.runner.queue, [sc.get("comfy_prompt_id")], 15, poll=0.05)
        except KeyError:
            J.mark_failed(owned, "canceled (its queue job was gone)")
        t = T.get_take(ep, pass_, shot, take)
        take_event(ctx, ep, t)
        sc = t.sidecar or {}
        return 200, {"shot": shot, "pass": pass_, "take": take, "status": t.status,
                     "save_notes": sc.get("save_notes", ""), "finished": sc.get("finished")}
    try:
        t = E.cancel_take(ep, pass_, shot, take, ctx.comfy)
    except E.NotQueued as e:
        raise ApiError(409, str(e))
    except LookupError as e:
        raise ApiError(404, str(e))
    except (OSError, RuntimeError) as e:
        raise ApiError(500, f"couldn't reach ComfyUI to cancel: {e}")
    take_event(ctx, ep, t)
    sc = t.sidecar or {}
    return 200, {"shot": shot, "pass": pass_, "take": take, "status": t.status,
                 "save_notes": sc.get("save_notes", ""), "finished": sc.get("finished")}


@handler
def post_discard(ctx: Context, body):
    """Move a take to renders[_proxy]/_trash/<shot>/ (edit.discard_take);
    a cut entry that picked it goes back to the latest usable take."""
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep"))
    pass_ = check_pass(body.get("pass"))
    shot = check_shot(body.get("shot"))
    take = check_take(body.get("take"))
    try:
        res = E.discard_take(ep, pass_, shot, take)
    except T.StillQueued as e:
        raise ApiError(409, str(e))
    except LookupError as e:
        raise ApiError(404, str(e))
    episode_event(ctx, ep)
    return 200, res


# ---------------------------------------------------------------------------
# upscale (Phase 13)
# ---------------------------------------------------------------------------

def finish_backend(ctx: Context, body: dict) -> str:
    """Where an upscale, post or tour runs: the request's `backend`, else this
    machine's own ComfyUI ("local")."""
    return _opt_backend(ctx, body) or "local"


def still_queued(ctx: Context) -> set:
    """The job ids still queued or running: ComfyUI's, and seriesmith's queue's."""
    try:
        alive = set(ctx.comfy.alive())
    except Exception:
        alive = set()
    alive |= ctx.runner.queue.alive()
    return alive


def upscale_event(ctx: Context, ep: str, shot: str, take: int, status: str) -> None:
    ctx.emit("seriesmith.upscale", {"ep": ep, "shot": shot, "take": take, "status": status})


@handler
def post_upscale(ctx: Context, body):
    """Queue upscales of a pass's takes (upscale; `pass`, default final):
    `shots` (their cut takes; null
    for the whole final cut) or `takes` ([{shot, take}]), with optional `redo`,
    `scale`, `start_step` and `vae`. `recipe: true` upscales each take by the
    series config's `upscale.master` recipe (its target's section, its shot's
    override) instead of the body's choices. 409 when this ComfyUI can't
    upscale, or there is no recipe."""
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep"))
    pass_ = check_pass(body.get("pass"), "final")
    shots, takes = body.get("shots"), body.get("takes")
    if shots is not None and (not isinstance(shots, list)
                              or not all(isinstance(s, str) and s for s in shots)):
        raise ApiError(400, "shots must be a list of shot ids (or null for the final cut)")
    if takes is not None and (not isinstance(takes, list) or not all(
            isinstance(x, dict) and isinstance(x.get("shot"), str) for x in takes)):
        raise ApiError(400, "takes must be a list of {shot, take}")
    redo, vae = body.get("redo", False), body.get("vae", False)
    if not isinstance(redo, bool) or not isinstance(vae, bool):
        raise ApiError(400, "redo and vae must be true or false")
    scale, start_step = body.get("scale"), body.get("start_step")
    if scale is not None and (isinstance(scale, bool) or not isinstance(scale, (int, float))):
        raise ApiError(400, "scale must be a number or null")
    if start_step is not None and (isinstance(start_step, bool) or not isinstance(start_step, int)):
        raise ApiError(400, "start_step must be a whole number or null")
    method = body.get("method")
    if method is not None and method not in U.METHODS:
        raise ApiError(400, "method must be latent, pixel, seedvr2 or null (each take's default)")
    seedvr2_model = body.get("seedvr2_model")
    if seedvr2_model is not None and (not isinstance(seedvr2_model, str) or not seedvr2_model):
        raise ApiError(400, "seedvr2_model must be 7b, 3b or a model file name, or null")
    pixel_model = body.get("pixel_model")
    if pixel_model is not None and (not isinstance(pixel_model, str) or not pixel_model):
        raise ApiError(400, "pixel_model must be an upscale model's file name (or rtx_vsr), or null")
    detail = body.get("detail")
    if detail is not None and detail not in U.DETAILS:
        raise ApiError(400, "detail must be 0, 1 or 2, or null")
    then_model = body.get("then_pixel_model")
    if then_model is not None and (not isinstance(then_model, str) or not then_model):
        raise ApiError(400, "then_pixel_model must be an upscale model's file name (or rtx_vsr), or null")
    encoder = body.get("encoder") or "auto"
    if encoder not in U.ENCODERS:
        raise ApiError(400, f"encoder must be one of {', '.join(U.ENCODERS)}")
    precision = body.get("precision") or "fp16"
    if precision not in U.PRECISIONS:
        raise ApiError(400, "precision must be fp16 or fp32")
    frequency_split = body.get("frequency_split", True)
    if not isinstance(frequency_split, bool):
        raise ApiError(400, "frequency_split must be true or false")
    keep_soft, grain = body.get("keep_soft", 0), body.get("grain", 0)
    for name, v, hi in (("keep_soft", keep_soft, 1.0), ("grain", grain, 0.2)):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= hi:
            raise ApiError(400, f"{name} must be a number from 0 to {hi:g}")
    from_upscale = body.get("from_upscale", False)
    if not isinstance(from_upscale, bool):
        raise ApiError(400, "from_upscale must be true or false")
    then_scale = body.get("then_scale")
    if then_scale is not None and (isinstance(then_scale, bool) or not isinstance(then_scale, (int, float))):
        raise ApiError(400, "then_scale must be a number or null")
    quality = body.get("quality") or "review"
    if quality not in U.QUALITIES:
        raise ApiError(400, "quality must be review or master")
    then_method = body.get("then_method")
    if then_method not in (None, "pixel", "seedvr2"):
        raise ApiError(400, "then_method must be pixel, seedvr2 or null")
    # the whole cut's upscales redone wholesale leave a Keep alone; naming shots
    # or takes redoes them
    whole = shots is None and takes is None
    use_recipe = body.get("recipe", False)
    if not isinstance(use_recipe, bool):
        raise ApiError(400, "recipe must be true or false")
    recipe = shot_rs = None
    if use_recipe:
        recipe = U.master_recipe(ep)
        if not recipe:
            raise ApiError(409, "the series config has no upscale.master recipe")
        shot_rs = U.shot_recipes(ep)
    deliver, fit = body.get("deliver"), body.get("fit") or "crop"
    try:
        U.parse_deliver(deliver)
    except U.UpscaleError as e:
        raise ApiError(400, str(e))
    if fit not in U.FITS:
        raise ApiError(400, "fit must be crop or pad")
    if takes is not None:
        found = []
        for x in takes:
            n = check_take(x.get("take"))
            found.append((x["shot"], T.get_take(ep, pass_, x["shot"], n),
                          f"{pass_} take {n} of {x['shot']} doesn't exist"))
    else:
        found = U.cut_takes(ep, set(shots) if shots is not None else None, pass_=pass_)
    jobs, skipped, errors = [], [], []
    for shot, t, why in found:
        if t is None:
            skipped.append({"shot": shot, "reason": why})
            continue
        if use_recipe:
            try:
                kw = U.recipe_for(ep, t, recipe, shot_rs)
            except U.UpscaleError as e:
                errors.append({"shot": shot, "take": t.take, "error": str(e)})
                continue
            up = U.plan_upscale(ep, t, redo=redo, respect_keep=whole, **kw)
        else:
            up = U.plan_upscale(ep, t, scale=scale, start_step=start_step,
                                route="vae" if vae else None, redo=redo, method=method,
                                respect_keep=whole,
                                pixel_model=pixel_model, detail=detail,
                                then_model=then_model, then_scale=then_scale,
                                then_method=then_method,
                                from_upscale=from_upscale, encoder=encoder, precision=precision,
                                frequency_split=frequency_split, keep_soft=keep_soft, grain=grain,
                                seedvr2_model=seedvr2_model, deliver=deliver, fit=fit,
                                quality=quality)
        if up.action == "skip":
            skipped.append({"shot": shot, "take": t.take, "reason": up.why})
        elif up.action == "error":
            errors.append({"shot": shot, "take": t.take, "error": up.why})
        else:
            jobs.append(up)
    queued = []
    if jobs:
        missing = missing_on_comfy(ctx, lambda info: U.not_ready(jobs, info))
        if missing:
            raise ApiError(409, "this ComfyUI can't run these upscales: " + "; ".join(missing))
        from seriesmith import finishing as F
        bases: dict = {}
        backend = finish_backend(ctx, body)
        ids: dict = {}
        for up in jobs:
            try:
                g = U.graph_of(up, bases, ctx.comfy_url)
                U.start(up)
                pid = ids[up.shot] = ctx.runner.enqueue_finish(
                    F.of_upscale(up, g), backend, after=U.waits_for(up, ids))
            except Exception as e:
                if os.path.isfile(up.take.paths.up_sidecar):
                    U.mark_failed(up, str(e)[:800])
                errors.append({"shot": up.shot, "take": up.take.take, "error": str(e)})
                continue
            queued.append({"shot": up.shot, "take": up.take.take, "route": up.route,
                           "method": up.method, "pixel_model": up.pixel_model or None,
                           "seedvr2_model": up.seedvr2_model or None,
                           "scale": up.scale, "start_step": up.start_step,
                           "then_pixel_model": up.then_model or None,
                           "width": up.out_size[0], "height": up.out_size[1], "prompt_id": pid})
            upscale_event(ctx, ep, up.shot, up.take.take, "queued")
    return 200, {"queued": queued, "skipped": skipped, "errors": errors}


def recipe_view(ep: str) -> dict | None:
    """The episode's master recipe for the dialog (None: the series config has
    none): the master's size and encoding, each video target's section in words
    (null: none covers it), each shot's override, and what's wrong with it."""
    r = U.master_recipe(ep)
    if not r:
        return None
    targets = {}
    for t in TG.list_targets("video"):
        key, sec = U.recipe_section(r, t.id)
        targets[t.id] = None if key is None else {
            "key": key, "fields": sec, "text": U.describe_recipe({**(r.get("finish") or {}), **sec}, r)}
    return {"deliver": r.get("deliver"), "fit": r.get("fit") or "crop",
            "quality": r.get("quality") or "review", "encoder": r.get("encoder") or "auto",
            "targets": targets,
            "shots": {s: {"fields": f, "text": U.describe_recipe(f)} for s, f in U.shot_recipes(ep).items()},
            "problems": U.check_recipe(r)}


# ---------------------------------------------------------------------------
# the post pass (post, docs/POST_PROCESSING.md)
# ---------------------------------------------------------------------------

def post_event(ctx: Context, ep: str, shot: str, take: int, status: str) -> None:
    ctx.emit("seriesmith.post", {"ep": ep, "shot": shot, "take": take, "status": status})


@handler
def queue_post(ctx: Context, body):
    """Queue posts of a pass's takes (post; `pass`, default final): `shots`
    (their cut takes; null for the whole cut) or `takes` ([{shot, take}]). Each
    take needs a fresh upscale. `recipe: true` (or neither `enhance` nor `blur`
    given) posts each by the series config's `post.master` with its shot's
    override; else `enhance` (a tier, a method, an object or "none") and `blur`
    (0-1). `redo` posts again even if fresh. 409 when this ComfyUI can't, or
    there is no recipe."""
    from seriesmith import post as P
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep"))
    pass_ = check_pass(body.get("pass"), "final")
    shots, takes = body.get("shots"), body.get("takes")
    if shots is not None and (not isinstance(shots, list)
                              or not all(isinstance(s, str) and s for s in shots)):
        raise ApiError(400, "shots must be a list of shot ids (or null for the final cut)")
    if takes is not None and (not isinstance(takes, list) or not all(
            isinstance(x, dict) and isinstance(x.get("shot"), str) for x in takes)):
        raise ApiError(400, "takes must be a list of {shot, take}")
    redo = body.get("redo", False)
    if not isinstance(redo, bool):
        raise ApiError(400, "redo must be true or false")
    enhance, blur = body.get("enhance"), body.get("blur")
    if blur is not None and (isinstance(blur, bool) or not isinstance(blur, (int, float))):
        raise ApiError(400, "blur must be a number from 0 to 1, or null")
    quality = body.get("quality")
    if quality is not None and quality not in U.QUALITIES:
        raise ApiError(400, "quality must be review or master, or null (as each upscale was)")
    use_recipe = body.get("recipe", enhance is None and blur is None)
    if not isinstance(use_recipe, bool):
        raise ApiError(400, "recipe must be true or false")
    recipe = shot_rs = None
    if use_recipe:
        recipe = P.master_recipe(ep)
        if not recipe:
            raise ApiError(409, "the series config has no post.master recipe")
        shot_rs = P.shot_recipes(ep)
    if takes is not None:
        found = []
        for x in takes:
            n = check_take(x.get("take"))
            found.append((x["shot"], T.get_take(ep, pass_, x["shot"], n),
                          f"{pass_} take {n} of {x['shot']} doesn't exist"))
    else:
        found = U.cut_takes(ep, set(shots) if shots is not None else None, pass_=pass_)
    jobs, skipped, errors = [], [], []
    for shot, t, why in found:
        if t is None:
            skipped.append({"shot": shot, "reason": why})
            continue
        kw = (P.recipe_for(ep, shot, recipe, shot_rs) if use_recipe
              else {"enhance": enhance, "blur": blur or 0.0})
        if quality is not None:
            kw["quality"] = quality
        job = P.plan_post(ep, t, redo=redo, **kw)
        if job.action == "skip":
            skipped.append({"shot": shot, "take": t.take, "reason": job.why})
        elif job.action == "error":
            errors.append({"shot": shot, "take": t.take, "error": job.why})
        else:
            jobs.append(job)
    queued = []
    if jobs:
        missing = missing_on_comfy(ctx, lambda info: P.not_ready(jobs, info))
        if missing:
            raise ApiError(409, "this ComfyUI can't run these posts: " + "; ".join(missing))
        from seriesmith import finishing as F
        backend = finish_backend(ctx, body)
        for job in jobs:
            try:
                P.start(job)
                pid = ctx.runner.enqueue_finish(F.of_post(job, P.post_graph(job)), backend)
            except Exception as e:
                if os.path.isfile(job.take.paths.post_sidecar):
                    P.mark_failed(job, str(e)[:800])
                errors.append({"shot": job.shot, "take": job.take.take, "error": str(e)})
                continue
            queued.append({"shot": job.shot, "take": job.take.take, "what": P.describe(job),
                           "width": job.width, "height": job.height, "prompt_id": pid})
            post_event(ctx, ep, job.shot, job.take.take, "queued")
    return 200, {"queued": queued, "skipped": skipped, "errors": errors}


def post_recipe_view(ep: str) -> dict | None:
    """The episode's post recipe for the dialogs (None: the series config has
    none): its fields and words, each shot's override, what's wrong with it."""
    from seriesmith import post as P
    r = P.master_recipe(ep)
    if not r:
        return None
    return {"fields": r, "text": P.describe_recipe(P.recipe_for(ep, "", r, {})),
            "shots": {s: {"fields": f, "text": P.describe_recipe(
                P.recipe_for(ep, s, r, {s: f}))} for s, f in P.shot_recipes(ep).items()},
            "problems": P.check_recipe(r)}


@handler
def get_post_options(ctx: Context, query: dict):
    """What the Post-process dialog offers: the tiers (what each runs), the
    methods, the blur range, whether this ComfyUI can run each step, and the
    episode's post recipe (`ep`)."""
    from seriesmith import post as P
    try:
        info = comfy_object_info(ctx)
    except Exception:
        info = None

    def ready(enhance=None, blur=0.0):
        job = P.PostJob(root="", take=None, enhance=P.resolve_enhance(enhance), blur=blur)
        if info is None:
            return {"status": "unknown", "missing": []}
        missing = P.not_ready([job], info)
        return {"status": "not_ready" if missing else "ready", "missing": missing}

    tiers = [{"id": k, "enhance": v, "text": P.describe_recipe({"enhance": k}),
              "readiness": ready(k)} for k, v in P.TIERS.items()]
    ep = check_ep(ctx, query["ep"]) if query.get("ep") else None
    return 200, {"tiers": tiers, "methods": list(P.METHODS),
                 "blur": {"min": P.BLUR[0], "max": P.BLUR[1], "default": 0.3,
                          "readiness": ready(None, 0.3)},
                 "strength": {"min": P.STRENGTH[0], "max": P.STRENGTH[1], "default": 0.2},
                 "recipe": post_recipe_view(ep) if ep else None}


@handler
def delete_post(ctx: Context, query: dict):
    """Remove a take's post (<stem>.post.mp4 and .post.json). 409 while ComfyUI
    still has it queued or running."""
    ep = check_ep(ctx, query.get("ep"))
    shot = check_shot(query.get("shot"))
    try:
        n = int(query.get("take"))
    except (TypeError, ValueError):
        raise ApiError(400, "take must be a take number")
    pass_ = check_pass(query.get("pass"), "final")
    t = T.get_take(ep, pass_, shot, check_take(n))
    if t is None:
        raise ApiError(404, f"{pass_} take {n} of {shot} doesn't exist")
    po = T.post_of(t)
    if po is None:
        raise ApiError(404, f"{shot} take {n} has no post")
    pid = po.get("comfy_prompt_id")
    if po.get("status") == "queued" and pid:
        alive = still_queued(ctx)
        if pid in alive:
            raise ApiError(409, f"{shot} take {n}'s post is still in ComfyUI's queue")
    for p in (t.paths.post_mp4, t.paths.post_sidecar):
        if os.path.isfile(p):
            os.remove(p)
    post_event(ctx, ep, shot, n, "deleted")
    return 200, {"shot": shot, "take": n, "deleted": True}


@handler
def post_master(ctx: Context, body):
    """Phase 13e: an episode's master (master). `action`: "plan" (what each
    shot of the cut is: upscale / post / ok / kept / queued / gap), "queue"
    (queue the upscale ones by the recipe, and with `post` their posts behind
    them and the post ones) or "assemble" (the master from the upscales, or with
    `post` the posts, into <episode>/master/; 409 while any are to do, or with
    gaps unless `allow_gaps`). `conform` redoes upscales (and posts) made with
    other settings (never a Keep); `prores` adds the ProRes .mov; `post` is the
    dialog's Post-process (the series config's post.master on every shot).
    Every answer carries the plan."""
    from seriesmith import master as M
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep"))
    pass_ = check_pass(body.get("pass"), "final")
    action = body.get("action") or "plan"
    if action not in ("plan", "queue", "assemble", "prores"):
        raise ApiError(400, "action must be plan, queue, assemble or prores")
    if action == "prores":
        # the .mov of the master already made: nothing is planned or assembled
        M.check_prores(ep)
        return 200, start_master(ctx, M, ep, pass_, "prores", {})
    flags = {k: body.get(k, False) for k in ("conform", "allow_gaps", "prores")}
    if not all(isinstance(v, bool) for v in flags.values()):
        raise ApiError(400, "conform, allow_gaps and prores must be true or false")
    # post: false / "off", "present" (posts where there are fresh ones), true / "recipe"
    flags["post"] = body.get("post", False)
    try:
        M.post_mode(flags["post"])
    except M.MasterError:
        raise ApiError(400, "post must be true, false, \"off\", \"present\" or \"recipe\"")
    order = body.get("order") or "cut"
    if order not in M.ORDERS:
        raise ApiError(400, "order must be cut or target")
    plan = M.plan_master(ep, pass_, flags["conform"], flags["post"])
    out: dict = {}
    if action == "queue":
        backend = finish_backend(ctx, body)
        queued, errors = M.queue_master(plan, ctx.comfy, ctx.comfy_url, order,
                                        runner=ctx.runner, backend=backend)
        for r in queued:
            if r.job is not None:                      # this run queued its upscale
                upscale_event(ctx, ep, r.shot, r.take.take, "queued")
            if r.post_job is not None:
                post_event(ctx, ep, r.shot, r.take.take, "queued")
        out = {"queued": [r.shot for r in queued],
               "errors": [{"shot": r.shot, "error": e} for r, e in errors]}
    elif action == "assemble":
        M.check_assemble(plan, flags["allow_gaps"])
        out = start_master(ctx, M, ep, pass_, "assemble", flags)
    have = M.existing_master(ep)
    return 200, {"plan": plan.view(), **out,
                 "existing": ({"output": E.rel(ep, have),
                               "mov": E.rel(ep, have[:-4] + ".mov")
                               if os.path.isfile(have[:-4] + ".mov") else None}
                              if have else None)}


# ---------------------------------------------------------------------------
# long work of seriesmith's own (a master, align): a job on the queue's serial
# "cpu" lane (Runner.local_job), the route answering at once with it. What the
# page follows is the job's `result`, sent as the work's own events as it goes
# (seriesmith.master, seriesmith.align). Without a queue it runs in the request.
# ---------------------------------------------------------------------------

_LOCAL_GUARD = threading.Lock()      # looking for a live one and queuing, one at a time


def _ep_key(ep: str) -> str:
    return os.path.normcase(os.path.abspath(ep))


def _local_jobs(ctx: Context, kind: str, ep: str) -> list:
    """This server's jobs of `kind` for the episode, newest first."""
    if ctx.runner is None:
        return []
    key = _ep_key(ep)
    jobs = [j for j in list(ctx.runner.queue.jobs.values())
            if j.kind == kind and _ep_key(j.info.get("ep") or "") == key]
    return sorted(jobs, key=lambda j: j.created, reverse=True)


def _live(ctx: Context, kind: str, ep: str):
    from seriesmith.queue import DONE
    return next((j for j in _local_jobs(ctx, kind, ep) if j.status not in DONE), None)


def _local(ctx: Context, kind: str, params: dict):
    """The job doing `kind` with `params` (LOCAL), not queued yet, and its work."""
    from seriesmith.queue import Job as QJob
    title, info, result, work = LOCAL[kind](ctx, params)
    if ctx.runner is None:
        qjob = QJob(kind=kind, lane="cpu", title=title, work=None, info=info)
    else:
        qjob = ctx.runner.local_job(kind, title, work, info,
                                    spec={"task": kind, "params": params},
                                    again=lambda: _local(ctx, kind, params)[0])
    qjob.result = dict(result, id=qjob.id)
    return qjob, work


def _start_local(ctx: Context, kind: str, params: dict):
    """Queue it (answer the job), or without a queue run it here and now."""
    qjob, work = _local(ctx, kind, params)
    if ctx.runner is not None:
        ctx.runner.enqueue_local(qjob)
    else:
        qjob.status = work(qjob, lambda **k: None, lambda kill: None)
    return qjob


def rebuild_local(ctx: Context, entry: dict) -> str | None:
    """A master or align the journal kept (its `resume`: {"kind": "local",
    "task", "params"}) after a restart: one still waiting is queued again;
    one that was running died with the server, so it is listed failed, saying
    so, for Retry. Its id, or None for one this version doesn't know."""
    resume = entry.get("resume") or {}
    kind, params = resume.get("task"), resume.get("params")
    if kind not in LOCAL or not isinstance(params, dict) or ctx.runner is None:
        return None
    qjob, _work = _local(ctx, kind, params)
    if entry.get("status") == "queued":
        ctx.runner.enqueue_local(qjob)
        return qjob.id
    why = "the server stopped while it ran: retry it"
    qjob.status, qjob.error = "failed", why
    qjob.result.update(state="failed", error=why, finished=T.now())
    ctx.runner.queue.add_done(qjob)
    return qjob.id


def master_job(ctx: Context, M, ep: str) -> dict | None:
    """The episode's master job: this server's (waiting, running, done or
    failed), or {"state": "running", "elsewhere": true, ...} for a run this
    server didn't start (`seriesmith master`), from the episode's master lock;
    None for neither."""
    jobs = _local_jobs(ctx, "master", ep)
    live = _live(ctx, "master", ep)
    if live is not None:
        return dict(live.result)
    held = M.assembling(ep)
    if held:
        return {"ep": ep, "pass": None, "state": "running", "elsewhere": True,
                "by": held.get("by"), "started": held.get("started"), "step": None,
                "stage": None, "done": None, "total": None, "text": "", "finished": None,
                "output": None, "mov": None, "report": None, "titles": None, "error": ""}
    return dict(jobs[0].result) if jobs and jobs[0].result else None


def _master_fraction(job: dict) -> float:
    """How far a master is, for Jobs' bar (as the dialog's masterFraction)."""
    part = min(1.0, job["done"] / job["total"]) if job.get("done") is not None and job.get("total") else 0.0
    if job.get("step") == "titles":
        return 0.85 + 0.15 * part if job.get("stage") == "reencode" else 0.85
    return {"probe": 0.1 * part, "clips": 0.1 + 0.7 * part, "join": 0.8, "prores": 0.82,
            "verify": 0.82}.get(job.get("stage") or "", 0.0)


def _master_task(ctx: Context, params: dict):
    """A master assembled ("assemble"), or the ProRes .mov of the one made
    ("prores"): planned again when it starts, as the episode is then."""
    from seriesmith import master as M
    ep, pass_, action, flags = params["ep"], params["pass"], params["action"], params["flags"]
    job = {"ep": ep, "pass": pass_, "action": action, "state": "running", "elsewhere": False,
           "by": "the editor", "started": T.now(), "step": "assemble", "stage": "waiting", "done": None,
           "total": None, "text": "", "finished": None, "output": None, "mov": None,
           "report": None, "titles": None, "error": ""}
    rel = (lambda p: E.rel(ep, p) if p else None)
    title = f"{os.path.basename(os.path.normpath(ep))} master" + (" ProRes" if action == "prores" else "")

    def work(qjob, report, stop) -> str:
        job = qjob.result

        def tell():
            ctx.emit("seriesmith.master", dict(job))

        def progress(ev: dict) -> None:
            job.update(step=ev.get("step"), stage=ev.get("stage"), done=ev.get("done"),
                       total=ev.get("total"), text=ev.get("text") or "")
            report(progress=_master_fraction(job))
            tell()

        def failed(why: str) -> str:
            job.update(state="failed", error=why, finished=T.now())
            qjob.error = why
            tell()
            return "failed"

        job.update(started=T.now(), stage="prores" if action == "prores" else "start")
        tell()
        try:
            if action == "prores":
                res = M.prores_only(ep, by="the editor")
                job.update(output=rel(res["output"]), mov=rel(res["mov"]), state="done",
                           stage="done", finished=T.now())
                tell()
                return "succeeded"
            plan = M.plan_master(ep, pass_, flags["conform"], flags["post"])
            res = M.assemble_master(plan, flags["allow_gaps"], flags["prores"], progress=progress,
                                    by="the editor", stop=stop)
        except M.MasterError as e:                       # busy, nothing to master, not ready
            return failed(str(e))
        except Exception as e:                           # noqa: BLE001  the job fails
            return failed(f"assembling the master failed: {e}")
        if not res["ok"] and qjob.cancel_asked:
            # what this run left (an untitled cut) isn't the episode's master
            for path in (res.get("output"), res.get("mov")):
                if path and os.path.isfile(path):
                    os.remove(path)
            return failed("canceled: no master was kept")
        job.update(output=rel(res.get("output")), mov=rel(res.get("mov")),
                   report=rel(res.get("report_md")), titles=res.get("titles"), finished=T.now())
        if not res["ok"]:
            return failed(res["error"] if res["output"]
                          else f"assembling the master failed: {res['error']}")
        job.update(state="done", stage="done")
        tell()
        return "succeeded"

    return title, {"ep": ep, "pass": pass_, "action": action}, job, work


def start_master(ctx: Context, M, ep: str, pass_: str, action: str, flags: dict) -> dict:
    """A master (or its ProRes) queued as a job others can see (master_job, the
    `seriesmith.master` events): 409 while another is waiting or running for
    this episode, from this editor or `seriesmith master`. Without a queue it
    runs here, and the answer is what it made."""
    with _LOCAL_GUARD:
        current = master_job(ctx, M, ep)
        if current and current["state"] == "running":
            msg = M.busy_message({"by": current.get("by") or "the editor",
                                  "started": current["started"]})
            raise ApiError(409, msg, job=current)
        qjob = _start_local(ctx, "master", {"ep": ep, "pass": pass_, "action": action,
                                            "flags": flags})
    job = dict(qjob.result)
    if ctx.runner is not None:
        return {"job": job}
    if job["state"] == "failed":
        busy = "already being assembled" in job["error"]
        raise ApiError(409 if busy or action == "prores" else 500, job["error"], job=job)
    return {"output": job["output"], "mov": job["mov"], "report": job["report"],
            "titles": job["titles"], "job": job}


@handler
def get_master_job(ctx: Context, query: dict):
    """The episode's master job (master_job): running with its step and counts,
    done with what it made, failed with why; null when there is none."""
    from seriesmith import master as M
    ep = check_ep(ctx, query.get("ep"))
    return 200, {"job": master_job(ctx, M, ep)}


@handler
def put_upscale_keep(ctx: Context, body):
    """Mark a take's finished upscale Keep (`keep`: true) or clear it."""
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep"))
    pass_ = check_pass(body.get("pass"), "final")
    shot = check_shot(body.get("shot"))
    n = check_take(body.get("take"))
    keep = body.get("keep")
    if not isinstance(keep, bool):
        raise ApiError(400, "keep must be true or false")
    t = T.get_take(ep, pass_, shot, n)
    if t is None:
        raise ApiError(404, f"{pass_} take {n} of {shot} doesn't exist")
    try:
        rec = U.set_keep(t, keep)
    except U.UpscaleError as e:
        raise ApiError(409, str(e))
    upscale_event(ctx, ep, shot, n, "kept" if keep else "unkept")
    return 200, {"shot": shot, "take": n, "keep": bool(rec.get("keep"))}


@handler
def put_upscale_recipe(ctx: Context, body):
    """One shot's upscale recipe (overrides.json's "upscale"): `recipe` is the
    upscale request's fields (method, scale, detail, pixel_model, then_pixel_model
    or then_method, the finish...) as the dialog sends them; null clears it."""
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep"))
    shot = check_shot(body.get("shot"))
    rec = body.get("recipe")
    if rec is not None and not isinstance(rec, dict):
        raise ApiError(400, "recipe must be an object or null")
    fields = U.recipe_from_request(rec) if rec else None
    problems = U.check_fields(fields or {})
    if problems:
        raise ApiError(400, "; ".join(problems))
    now = U.set_shot_recipe(ep, shot, fields)
    return 200, {"shot": shot, "recipe": now or None,
                 "text": U.describe_recipe(now) if now else None}


@handler
def get_upscale_options(ctx: Context, query: dict):
    """What the Upscale dialog offers: the pixel method's models (this ComfyUI's
    models/upscale_models) and default, and each video target's latent upscale
    (null: it has none; else its readiness)."""
    try:
        info = comfy_object_info(ctx)
    except Exception:
        info = None
    px = U.pixel_readiness(info)
    sv2 = U.seedvr2_readiness(info)
    latent = {}
    for t in TG.list_targets("video"):
        r = U.upscale_readiness(t, info)
        if r is not None:
            spec = U.upscale_spec(t) or {}
            # what the dialog needs to judge a scale: LTX's is fixed, H3's sizes
            # land on `align`
            r = dict(r, mode=spec.get("mode", U.RESAMPLE), align=U.align_of(spec),
                     fixed_scale=U.fixed_scale(spec))
        latent[t.id] = r
    ep = check_ep(ctx, query["ep"]) if query.get("ep") else None
    return 200, {"pixel": px, "seedvr2": sv2, "latent": latent, "details": list(U.DETAILS),
                 "recipe": recipe_view(ep) if ep else None,
                 "max_scale": U.MAX_SCALE, "encoders": list(U.ENCODERS),
                 "precisions": list(U.PRECISIONS),
                 "delivers": [{"id": k, "width": w, "height": h} for k, (w, h) in U.DELIVER.items()],
                 "fits": list(U.FITS)}


@handler
def delete_upscale(ctx: Context, query: dict):
    """Remove a take's upscale (<stem>.up.mp4 and .up.json). 409 while ComfyUI
    still has it queued or running."""
    ep = check_ep(ctx, query.get("ep"))
    shot = check_shot(query.get("shot"))
    try:
        n = int(query.get("take"))
    except (TypeError, ValueError):
        raise ApiError(400, "take must be a take number")
    pass_ = check_pass(query.get("pass"), "final")
    t = T.get_take(ep, pass_, shot, check_take(n))
    if t is None:
        raise ApiError(404, f"{pass_} take {n} of {shot} doesn't exist")
    up = T.upscale_of(t)
    if up is None:
        raise ApiError(404, f"{shot} take {n} has no upscale")
    pid = up.get("comfy_prompt_id")
    if up.get("status") == "queued" and pid:
        alive = still_queued(ctx)
        if pid in alive:
            raise ApiError(409, f"{shot} take {n}'s upscale is still in ComfyUI's queue")
    for p in (t.paths.up_mp4, t.paths.up_sidecar):
        if os.path.isfile(p):
            os.remove(p)
    upscale_event(ctx, ep, shot, n, "deleted")
    return 200, {"shot": shot, "take": n, "deleted": True}


# ---------------------------------------------------------------------------
# cut and overrides
# ---------------------------------------------------------------------------

@handler
def put_pick(ctx: Context, body):
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep"))
    pass_ = check_pass(body.get("pass"))
    shot = check_shot(body.get("shot"))
    take = check_take(body.get("take"), nullable=True)
    src = body.get("from_pass")
    if src is not None:
        src = check_pass(src)
    force = body.get("force", False)
    if not isinstance(force, bool):
        raise ApiError(400, "force must be true or false")
    try:
        cut = E.pick_take(ep, pass_, shot, take, from_pass=src, force=force)
    except E.NotUsable as e:
        raise ApiError(409, f"{e}; pick it anyway with \"force\": true")
    except E.Locked as e:
        raise ApiError(409, f"{e}: unlock it first, or pick anyway with \"force\": true",
                       locked=True)
    except KeyError as e:
        raise ApiError(404, e.args[0])
    except LookupError as e:
        raise ApiError(404, str(e))
    episode_event(ctx, ep)
    return 200, {"cut": cut}


def _cut_entry(raw) -> dict:
    if not isinstance(raw, dict) or not isinstance(raw.get("shot"), str) or not raw["shot"]:
        raise ApiError(400, "each cut entry needs a shot id")
    e = {"shot": raw["shot"]}
    if raw.get("take") is not None:
        e["take"] = check_take(raw["take"], f"{raw['shot']}: take")
    if raw.get("pass") is not None:
        e["pass"] = check_pass(raw["pass"])
    for k in ("trim_in", "trim_out"):
        v = raw.get(k)
        if v is None:
            continue
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            raise ApiError(400, f"{raw['shot']}: {k} must be a whole number of frames >= 0")
        if v:
            e[k] = v
    if raw.get("locked") is not None:
        if not isinstance(raw["locked"], bool):
            raise ApiError(400, f"{raw['shot']}: locked must be true or false")
        if raw["locked"]:
            e["locked"] = True
    if raw.get("note") is not None:
        if not isinstance(raw["note"], str):
            raise ApiError(400, f"{raw['shot']}: note must be text")
        if raw["note"]:
            e["note"] = raw["note"]
    if raw.get("out") is not None:
        if not isinstance(raw["out"], bool):
            raise ApiError(400, f"{raw['shot']}: out must be true or false")
        if raw["out"]:
            e["out"] = True
    if raw.get("flag") is not None:
        if not isinstance(raw["flag"], bool):
            raise ApiError(400, f"{raw['shot']}: flag must be true or false")
        if raw["flag"]:
            e["flag"] = True
    if raw.get("audio") is not None:
        # the shape and what it points at are checked together, in
        # edit.check_audio (E.replace_cut), so the CLI checks them too
        e["audio"] = raw["audio"]
    unknown = set(raw) - set(T.ENTRY_FIELDS)
    if unknown:
        raise ApiError(400, f"{raw['shot']}: unknown cut field(s) {', '.join(sorted(unknown))}")
    return e


@handler
def put_cut(ctx: Context, body):
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep"))
    pass_ = check_pass(body.get("pass"))
    entries = body.get("entries")
    if not isinstance(entries, list):
        raise ApiError(400, "entries must be a list of cut entries")
    clean = [_cut_entry(e) for e in entries]
    seen = set()
    for e in clean:
        if e["shot"] in seen:
            raise ApiError(400, f"{e['shot']} is in the cut twice")
        seen.add(e["shot"])
    cut = E.replace_cut(ep, pass_, clean)
    episode_event(ctx, ep)
    return 200, {"cut": cut}


def _cut_what(v) -> str:
    if v not in E.CUT_WHAT:
        raise ApiError(400, f"what must be one of {', '.join(E.CUT_WHAT)}, not {v!r}")
    return v


@handler
def post_cut_reset(ctx: Context, body):
    """Script order (picks, locks, notes kept), no trims and/or no audio
    sources (edit.reset_cut)."""
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep"))
    pass_ = check_pass(body.get("pass"))
    what = _cut_what(body.get("what"))
    J.load_shotlist(ep, pass_)                           # 404: not built
    cut = E.reset_cut(ep, pass_, what)
    episode_event(ctx, ep)
    return 200, {"cut": cut}


@handler
def post_cut_copy(ctx: Context, body):
    """One pass's order, trims and/or audio sources onto the other
    (edit.copy_cut)."""
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep"))
    for k in ("from", "to"):
        if body.get(k) not in PASSES:
            raise ApiError(400, f"{k} must be 'final' or 'proxy', not {body.get(k)!r}")
    src, dst = body["from"], body["to"]
    what = _cut_what(body.get("what"))
    if src == dst:
        raise ApiError(400, "from and to must be different passes")
    J.load_shotlist(ep, src)                             # 404: not built
    J.load_shotlist(ep, dst)
    cut = E.copy_cut(ep, src, dst, what)
    episode_event(ctx, ep)
    return 200, {"cut": cut}


def _num(query: dict, key: str, cast, lo=None):
    v = query.get(key)
    if v is None or v == "":
        return None
    try:
        n = cast(v)
    except (TypeError, ValueError):
        raise ApiError(400, f"{key} must be a number, not {v!r}")
    if cast is float and n != n:                          # NaN
        raise ApiError(400, f"{key} must be a number")
    if lo is not None and n < lo:
        raise ApiError(400, f"{key} must be {lo} or more")
    return n


@handler
def get_peaks(ctx: Context, query: dict):
    """A media file's waveform (peaks.peaks): max |amplitude| per bin, 0..255."""
    ep = check_ep(ctx, query.get("ep"))
    full, rel = ep_file(ctx, ep, query.get("path"), escape_status=400)
    bins = _num(query, "bins", int, 1)
    if bins is not None and bins > PK.MAX_BINS:
        raise ApiError(400, f"bins must be {PK.MAX_BINS} or fewer")
    start = _num(query, "start", float, 0)
    end = _num(query, "end", float, 0)
    try:
        return 200, PK.peaks(ep, full, rel, bins, start, end)
    except ValueError as e:
        raise ApiError(400, str(e))
    except PK.PeaksError as e:
        raise ApiError(500, str(e))


OVERRIDE_FIELDS = ("prompt", "seed", "model", "loras", "steps", "note", "target", "negative",
                   "model_low", "size")


@handler
def put_override(ctx: Context, body):
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep"))
    pass_ = check_pass(body.get("pass"))
    shot = check_shot(body.get("shot"))
    both = body.get("both", False)
    if not isinstance(both, bool):
        raise ApiError(400, "both must be true or false")
    fields = body.get("fields")
    if not isinstance(fields, dict):
        raise ApiError(400, "fields must be an object, e.g. {\"seed\": \"1234\"}")
    unknown = set(fields) - set(OVERRIDE_FIELDS)
    if unknown:
        raise ApiError(400, f"unknown override field(s) {', '.join(sorted(unknown))}: "
                            f"one of {', '.join(OVERRIDE_FIELDS)}")
    shot_fields, pass_fields = {}, {}
    if "seed" in fields:
        shot_fields["seed"] = seed_in(fields["seed"])
    if "note" in fields:
        if fields["note"] is not None and not isinstance(fields["note"], str):
            raise ApiError(400, "note must be text or null")
        shot_fields["note"] = fields["note"] or None
    if "prompt" in fields:
        pass_fields["prompt"] = _opt_prompt(fields["prompt"])
    if "model" in fields:
        m = fields["model"]
        if m is not None and not isinstance(m, str):
            raise ApiError(400, "model must be a file name or null")
        pass_fields["model"] = m or None
    if "loras" in fields:
        pass_fields["loras"] = _opt_loras(fields["loras"])
    if "steps" in fields:
        pass_fields["steps"] = _opt_steps(fields["steps"])
    if "size" in fields:
        pass_fields["size"] = _opt_size(fields["size"])
    if "negative" in fields:
        # "" is an explicit empty negative; null clears the override
        n = fields["negative"]
        if n is not None and not isinstance(n, str):
            raise ApiError(400, "negative must be text or null")
        pass_fields["negative"] = n
    if "model_low" in fields:
        m = fields["model_low"]
        if m is not None and not isinstance(m, str):
            raise ApiError(400, "model_low must be a file name or null")
        pass_fields["model_low"] = m or None

    built_target = E.shot_built_target(ep, shot)
    if built_target is None:
        raise ApiError(404, f"{shot} is in no built shotlist of this episode")
    ov = T.load_overrides(ep)
    if "target" in fields:
        # shared by both passes; null clears it, and so does the built target
        # itself unless an episode target is set (then it pins the shot there)
        want = _opt_target(fields["target"])
        T.set_shot_target(ov, shot, E.keeps_shot_target(ov, want, built_target))
    # overrides are keyed by the target the shot renders on (after this change)
    target = J.effective_target(ov, shot, built_target, root=ep)
    built = E.pass_entries(ep, shot, target)
    passes = list(T.PASSES) if both else [pass_]
    missing = [ps for ps in passes if ps not in built]
    if pass_fields and missing:
        raise ApiError(409, f"{shot} has no {'/'.join(missing)} build"
                            + (f" that compiles for {target}" if target != built_target else "")
                            + ": build the episode first")
    E.set_shot_override(ov, shot, built, passes, shot_fields, pass_fields, target)
    if "episode" not in ov:
        ov["episode"] = next((J.load_shotlist(ep, ps).get("episode", "") for ps in T.PASSES
                              if os.path.isfile(os.path.join(ep, J.shotlist_rel(ps)))), "")
    T.save_overrides(ep, ov)
    episode_event(ctx, ep)
    return 200, seeds_out({"override": E.override_view(ov, shot, built, target),
                           "target": target, "built_target": built_target})


@handler
def delete_override(ctx: Context, query: dict):
    ep = check_ep(ctx, query.get("ep"))
    shot = check_shot(query.get("shot"))
    p = query.get("pass")
    pass_ = check_pass(p) if p else None
    built_target = E.shot_built_target(ep, shot) or TG.machine_default("video")
    ov = T.load_overrides(ep)
    target = J.effective_target(ov, shot, built_target, root=ep)
    E.clear_shot_override(ov, shot, pass_, target)
    if pass_ is None:                                   # everything: the retarget too
        T.set_shot_target(ov, shot, None)
        # back to the script's target, else the episode's, else the build's
        target = J.effective_target(ov, shot, built_target, root=ep)
    T.save_overrides(ep, ov)
    episode_event(ctx, ep)
    built = E.pass_entries(ep, shot, target)
    return 200, seeds_out({"override": E.override_view(ov, shot, built, target),
                           "target": target, "built_target": built_target})


# ---------------------------------------------------------------------------
# targets (Phase 7)
# ---------------------------------------------------------------------------

@handler
def get_targets(ctx: Context, query: dict):
    """Every video, image and audio target: id, kind, label, presets, and the
    widgets its binding exposes (for pickers). `kind` narrows to one kind; `ep`
    adds that show's own targets (Phase 12)."""
    if query.get("ep"):
        check_ep(ctx, query.get("ep"))                    # registers its custom targets
    kind = query.get("kind") or None
    if kind is not None and kind not in TG.KINDS:
        raise ApiError(400, f"kind must be one of {', '.join(TG.KINDS)}, not {kind!r}")
    ready = query.get("ready")
    if ready not in (None, "", "0", "1", "true", "false"):
        raise ApiError(400, f"ready must be 1 or 0, not {ready!r}")
    targets = TG.list_targets(kind)
    out = [t.describe() for t in targets]
    graphs = target_graphs(ctx)
    for d in out:
        g = graphs.get(d["id"])
        if g is not None:
            d["graph"] = {k: v for k, v in g.items() if k != "graph"}
    if ready in ("1", "true"):
        rd = target_readiness(ctx)
        for d in out:
            d["readiness"] = rd.get(d["id"]) or {"status": "unknown", "missing": [],
                                                 "resolved": {}, "features_off": [],
                                                 "nodes_missing": []}
    return 200, {"targets": out, "default": dict(TG.DEFAULT_TARGETS,
                                                 **{k: TG.machine_default(k) for k in ("video", "image")})}


READY_TTL = 30.0                                          # seconds a readiness answer is kept
_READY: dict = {}
_READY_LOCK = None
_GRAPHS: dict = {}                                        # (Phase 11) the graph in force
_INFO: dict = {}                                          # ComfyUI's /object_info, per address

# On a server (the hosts set it, beside DETECT_DEFAULTS), an answer kept past
# READY_TTL is still given at once while a thread asks ComfyUI again behind it:
# readiness and /object_info took 1.5-2.5 s to remake, and every episode
# opened after the 30 s waited on them. forget_comfy (an install) still makes
# the next answer wait for a fresh one. Off for the tests and the CLI.
REFRESH_BEHIND = False
_BEHIND: set = set()
_BEHIND_LOCK = threading.Lock()
_GEN = [0]                                                # forget_comfy's count


def _refresh_behind(key: tuple, work) -> None:
    """work() on a thread of its own, one per key at a time, with this
    request's shows in force (their own targets count)."""
    with _BEHIND_LOCK:
        if key in _BEHIND:
            return
        _BEHIND.add(key)
    roots = TG.thread_roots()

    def run():
        try:
            for r in roots:
                TG.add_thread_root(r)
            work()
        except Exception:                                 # noqa: BLE001  the next ask tries again
            pass
        finally:
            with _BEHIND_LOCK:
                _BEHIND.discard(key)
    threading.Thread(target=run, daemon=True, name="seriesmith-refresh").start()


def comfy_object_info(ctx: Context, fresh: bool = False) -> dict:
    """ComfyUI's /object_info (every node class it knows: megabytes, a second to
    answer), kept READY_TTL seconds per address like readiness, for the
    dialogs and checks that ask what this ComfyUI can run. Raises as
    ctx.comfy.object_info does, and a failure isn't kept. `fresh` asks again
    (before refusing work for a missing node: it may have just gone in). Only
    a context's own client is cached; a fake one given in (tests) is asked."""
    import time
    if ctx._comfy is not None and not isinstance(ctx._comfy, J.Comfy):
        return ctx.comfy.object_info()
    hit = _INFO.get(ctx.comfy_url)
    if hit and not fresh:
        if time.monotonic() - hit[0] < READY_TTL:
            return hit[1]
        if REFRESH_BEHIND:
            _refresh_behind(("info", ctx.comfy_url), lambda: comfy_object_info(ctx, fresh=True))
            return hit[1]
    gen = _GEN[0]
    info = ctx.comfy.object_info()
    if gen == _GEN[0]:                                    # not from before an install
        _INFO[ctx.comfy_url] = (time.monotonic(), info)
    return info


def missing_on_comfy(ctx: Context, not_ready) -> list[str]:
    """not_ready(object_info) on this ComfyUI: the kept answer first, and asked
    again before anything is reported missing (it may have just gone in). 502
    when ComfyUI doesn't answer."""
    for fresh in (False, True):
        try:
            info = comfy_object_info(ctx, fresh=fresh)
        except Exception as e:
            raise ApiError(502, f"ComfyUI didn't answer: {e}")
        missing = not_ready(info)
        if not missing:
            break
    return missing


def forget_comfy() -> None:
    """Drop what was kept of every ComfyUI (readiness, /object_info): a file or
    node pack went in, so the next answer asks again."""
    _GEN[0] += 1
    _READY.clear()
    _INFO.clear()


def target_graphs(ctx: Context, refresh: bool = False) -> dict:
    """{target id: which workflow its next render uses} (edit.target_graphs:
    $ENV, the running ComfyUI's saved workflows, $COMFYUI_PATH, then the repo's
    copy), kept READY_TTL seconds per ComfyUI address. Each entry carries the
    graph itself, for readiness' node check; the route strips it."""
    import time
    hit = _GRAPHS.get(ctx.comfy_url)
    if hit and not refresh:
        if time.monotonic() - hit[0] < READY_TTL:
            return hit[1]
        if REFRESH_BEHIND:
            _refresh_behind(("graphs", ctx.comfy_url), lambda: target_graphs(ctx, refresh=True))
            return hit[1]
    graphs = E.target_graphs(TG.list_targets(), ctx.comfy_url)
    _GRAPHS[ctx.comfy_url] = (time.monotonic(), graphs)
    return graphs


def forget_graphs(ctx: Context) -> None:
    """Drop the cached answers that depend on which workflow is in force: the
    graph itself, and readiness (its node check reads that graph)."""
    _GRAPHS.pop(ctx.comfy_url, None)
    _READY.pop(ctx.comfy_url, None)
    _INFO.pop(ctx.comfy_url, None)


@handler
def post_workflow_install(ctx: Context, body):
    """Copy a target's repo workflow into this ComfyUI's saved workflows, so it
    can be opened and edited on the canvas. Written verbatim under the name the
    binding looks up (`name` saves a scratch copy under another name instead);
    from then on that saved copy is what the target's renders use."""
    body = body_dict(body)
    t = _workflow_target(body.get("target"))
    name = _opt_str(body, "name") or None
    overwrite = body.get("overwrite", False)
    if not isinstance(overwrite, bool):
        raise ApiError(400, "overwrite must be true or false")
    try:
        r = E.install_workflow(t, ctx.comfy, name, overwrite=overwrite)
    except FileNotFoundError as e:
        raise ApiError(400, str(e))
    except ValueError as e:
        raise ApiError(400, str(e))
    except RuntimeError as e:
        if "ComfyUI 409" in str(e):
            raise ApiError(409, f"workflows/{name or t.binding.workflow_name} is already saved "
                                f"in ComfyUI — pass overwrite: true to replace it")
        raise ApiError(502, f"couldn't write the workflow to ComfyUI: {e}")
    forget_graphs(ctx)
    return 200, {"ok": True, "target": t.id, "installed": r["name"], "renders": r["renders"],
                 "graph": _graph_view(ctx, t)}


@handler
def delete_workflow_install(ctx: Context, query: dict):
    """Delete a target's workflow from this ComfyUI's saved workflows: its
    renders go back to the repo's copy. $ENV is never touched."""
    t = _workflow_target(query.get("target"))
    try:
        r = E.revert_workflow(t, ctx.comfy, query.get("name") or None)
    except ValueError as e:
        raise ApiError(400, str(e))
    except RuntimeError as e:
        raise ApiError(502, f"couldn't delete the workflow in ComfyUI: {e}")
    forget_graphs(ctx)
    return 200, {"ok": True, "target": t.id, "deleted": r["deleted"], "name": r["name"],
                 "graph": _graph_view(ctx, t)}


# ---------------------------------------------------------------------------
# custom targets from a workflow (Phase 12b)
# ---------------------------------------------------------------------------

@handler
def get_workflows(ctx: Context, query: dict):
    """The workflows saved in this ComfyUI, for the picker that turns one into a
    target. Names only; `h3pipe/` copies and this repo's own are marked."""
    try:
        names = ctx.comfy.list_userdata("workflows")
    except Exception as e:
        raise ApiError(502, f"couldn't list ComfyUI's workflows: {e}")
    mine = {t.binding.workflow_name for t in TG.list_targets()}
    return 200, {"workflows": [{"name": n, "target": n in mine} for n in names]}


@handler
def post_targets_inspect(ctx: Context, body):
    """Propose the target.json for a workflow (inspector). Read-only: it writes
    nothing, and says what it could not work out (`ambiguous`, `warnings`)."""
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep")) if body.get("ep") else None
    data = _workflow_data(ctx, body)
    try:
        info = ctx.comfy.object_info()
    except Exception as e:
        raise ApiError(502, f"ComfyUI didn't answer /object_info: {e}")
    extra = {}
    if ep:
        try:
            extra = J.series_model_families(ep)
        except ValueError:
            extra = {}
    try:
        out = IN.inspect_graph(data, info, ctx.model_list,
                               target_id=_opt_str(body, "id") or "",
                               label=_opt_str(body, "label") or "",
                               workflow_name=_opt_str(body, "workflow") or "",
                               kind=_opt_str(body, "kind") or "auto",
                               extra=extra,
                               series_cfg=J.series_config(ep) if ep else None)
    except (IN.InspectError, ValueError) as e:
        raise ApiError(400, str(e))
    out["problems"] = out.get("problems") or []
    out["can_save"] = not out["problems"]
    return 200, out


def _workflow_data(ctx: Context, body: dict) -> dict:
    """The graph a request names: `workflow` (saved in ComfyUI) or `graph` (sent
    with the request, for a file the editor read)."""
    if isinstance(body.get("graph"), dict) and body["graph"]:
        return body["graph"]
    name = _opt_str(body, "workflow")
    if not name:
        raise ApiError(400, "give `workflow` (a name among ComfyUI's saved workflows) "
                            "or `graph` (the workflow itself)")
    try:
        data = ctx.comfy.userdata(f"workflows/{name}")
    except Exception as e:
        raise ApiError(502, f"couldn't read workflows/{name} from ComfyUI: {e}")
    if data is None:
        raise ApiError(404, f"ComfyUI has no saved workflow called {name}")
    return data


@handler
def post_targets_router_inspect(ctx: Context, body):
    """A Comfy Router video model proposed as a target (router_inspect): its
    schema read from Router (the account's Comfy API key) and the target.json
    that drives it proposed -- where each part of a shot goes, its limits, its
    presets -- with what was placed, what it requires that wasn't, and what
    was guessed. Read-only: saving is PUT /seriesmith/targets/custom (a draft,
    until a probe render proves it). Body {model, ep?}."""
    from seriesmith import router_inspect as RI
    from seriesmith.settings import load_settings
    body = body_dict(body)
    model = (_opt_str(body, "model") or "").strip()
    key = load_settings().api_key
    if not key:
        raise ApiError(409, "reading a Router model needs your Comfy API key (Settings)")
    try:
        doc = RI.fetch_schema(model, key)
        if RI.kind_of(model) == "image":
            out = RI.propose_image(model, doc)
        else:
            base = TG.load_target("seedance_2_5", "video").spec
            out = RI.propose(model, doc, base=base)
    except RI.RouterInspectError as e:
        raise ApiError(400, str(e))
    ep = check_ep(ctx, body.get("ep")) if body.get("ep") else None
    from seriesmith import limits as L
    out["limits"] = L.describe(out["proposal"])
    tid = out["proposal"]["id"]
    if tid in {t.id for t in TG.list_targets(root=ep)}:
        out["warnings"].append(f"there is already a target called {tid}: saving replaces this show's own, "
                               f"a built-in one can't be replaced (change the id)")
    return 200, out


@handler
def get_router_models(ctx: Context, query: dict):
    """Router's model catalog for the wizard's picker: [{id, provider, model,
    kind ("video" | "image" | "other", guessed from the name), text_only (its
    name says text-to-video), added (a target already drives it: its id)}],
    read with the account's Comfy API key and kept an hour. Query {ep?}."""
    from seriesmith import router_inspect as RI
    from seriesmith.settings import load_settings
    key = load_settings().api_key
    if not key:
        raise ApiError(409, "Router's model list needs your Comfy API key (Settings)")
    try:
        ids = RI.fetch_catalog(key)
    except RI.RouterInspectError as e:
        raise ApiError(502, str(e))
    ep = check_ep(ctx, query.get("ep")) if query.get("ep") else None
    added = {}
    for t in TG.list_targets(root=ep):
        m = (t.spec.get("router") or {}).get("model")
        if m:
            added.setdefault(m, t.id)
    out = []
    for i in sorted(ids):
        prov, _, name = i.partition("/")
        out.append({"id": i, "provider": prov, "model": name, "kind": RI.kind_of(i),
                    "text_only": bool(re.search(r"t2v|text-to-video", name)),
                    **({"added": added[i]} if i in added else {})})
    return 200, {"models": out}


@handler
def put_targets_custom(ctx: Context, body):
    """Save a show's own target (`<show>/targets/<id>/target.json`). Validated
    first, against the workflow it names as a render would resolve it."""
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep"))
    spec = body.get("target")
    if spec is None and body.get("id") and "draft" in body:
        # the small edit the editor makes after a probe render: stop being a
        # draft (or go back to being one), without sending the whole target.json
        if not isinstance(body["draft"], bool):
            raise ApiError(400, "draft must be true or false")
        try:
            t = TG.load_target(str(body["id"]), root=ep)
        except TG.TargetError as e:
            raise ApiError(404, str(e))
        if t.shipped_draft:
            # a built-in that ships as a draft: switched on (or off) for every
            # show in the settings, its target.json left as it is
            from seriesmith import settings as S
            on = set(S.load_settings().enabled_drafts)
            on = on - {t.id} if body["draft"] else on | {t.id}
            try:
                S.save_settings({"enabled_drafts": sorted(on)})
            except (OSError, ValueError) as e:
                raise ApiError(500, f"the settings couldn't be saved: {e}")
            episode_event(ctx, ep)
            return 200, {"ok": True, "id": t.id, "path": S.settings_path(),
                         "draft": body["draft"], "targets": IN.custom_targets(ep)}
        if not t.custom:
            raise ApiError(400, f"{t.id} is a built-in target, not this show's")
        spec = dict(t.spec)
        if body["draft"]:
            spec["draft"] = True
        else:
            spec.pop("draft", None)
    if not isinstance(spec, dict) or not spec:
        raise ApiError(400, "target must be the target.json to save, as an object")
    spec = _with_limits(spec, body.get("limits"))
    graph, info = None, None
    try:
        info = ctx.comfy.object_info()
    except Exception:
        info = None
    name = ((spec.get("binding") or {}).get("workflow_name") or "")
    if name and spec.get("router") is None:
        try:
            data = ctx.comfy.userdata(f"workflows/{name}")
        except Exception:
            data = None
        if data is None:
            data = None if not TG.repo_workflow(name) else J.load_graph(TG.repo_workflow(name))
            graph = data
        else:
            graph = J.graph_from(data, name)
    problems = IN.validate_spec(spec, graph, info)
    if graph is None and spec.get("router") is None:
        problems = [p for p in problems] + [
            f"no workflow called {name} is saved in ComfyUI, so the binding can't be checked: "
            f"save the graph there first (its name is binding.workflow_name)"]
    if problems:
        raise ApiError(400, "this target.json can't be used yet: " + problems[0],
                       problems=problems)
    # where it goes: back where it was (a draft switch), else the show's own,
    # or every show's (`scope: "user"`, the user folder beside the settings)
    if body.get("scope") not in (None, "show", "user"):
        raise ApiError(400, 'scope is "show" or "user" (every show)')
    if spec is not None and body.get("target") is None and body.get("id"):
        base = os.path.dirname(TG.load_target(spec["id"], root=ep).folder)
    else:
        base = TG.user_folder() if body.get("scope") == "user" else None
    path = IN.save_spec(ep, spec, base=base)
    episode_event(ctx, ep)
    return 200, {"ok": True, "id": spec["id"], "path": path,
                 "draft": bool(spec.get("draft")),
                 "targets": IN.custom_targets(ep)}


LOCAL_LIMITS = {"length", "size", "pictures"}       # a local target's: its graph has the rest
IMAGE_DRYRUN_BASE = "nano_banana_pro"   # a hosted edit model: plans a ref job with its pictures


def _image_dryrun(ep: str, spec: dict, ref_id: str | None, view: str | None):
    """What a Router image target would send for one ref take (the router
    dry run's image half): the ref planned as a hosted edit model plans it
    (its references chosen), then this target's request made from it."""
    from seriesmith import refs as R
    from seriesmith.backends import File
    s = R.load_series(ep)
    refs = R.series_refs(s)
    if ref_id:
        try:
            ref = R.find_ref(s, ref_id)
        except Exception as e:                          # noqa: BLE001  an unknown id
            raise ApiError(404, str(e))
    else:
        ref = next((r for r in refs if r.kind == "character"), refs[0] if refs else None)
        if ref is None:
            raise ApiError(404, "this episode has no refs to try it on")
    jobs = R.plan_generate(s, R.GenRequest(ref=ref.id, view=view, target=IMAGE_DRYRUN_BASE))
    if not jobs:
        raise ApiError(400, f"{ref.id}: nothing to generate")
    job = jobs[0]
    t = TG.Target(TG.load_target(IMAGE_DRYRUN_BASE, "image").folder, spec)
    job.target = t
    R.hosted_references(s, job)
    model, args = t.module.router_call(t, job)

    def plain(v):
        if isinstance(v, File):
            return {"file": v.path, **({"via": v.via} if v.via else {})}
        if isinstance(v, dict):
            return {k: plain(x) for k, x in v.items()}
        if isinstance(v, list):
            return [plain(x) for x in v]
        return v
    from seriesmith.backends.router import ROUTING
    routing = args.pop(ROUTING, None)
    return 200, {"ok": True, "shot": f"{ref.id}{' ' + job.view if job.view else ''}", "ref": ref.id,
                 "view": job.view, "model": model, "arguments": plain(args),
                 **({"routing": routing} if routing else {}),
                 "prompt_chars": {"written": len(job.prompt or "")}}


def _with_limits(spec: dict, limits) -> dict:
    """`spec` with the editor's limit changes written in (seriesmith.limits):
    the Router wizard sends the proposal and what was changed in its form."""
    if not limits:
        return spec
    from seriesmith import limits as L
    if not isinstance(limits, dict):
        raise ApiError(400, "limits must be an object (seriesmith.limits sections)")
    try:
        return L.apply(spec, {k: v for k, v in limits.items() if k in L.SECTIONS})
    except ValueError as e:
        raise ApiError(400, str(e))


@handler
def put_targets_limits(ctx: Context, body):
    """Change a video target's limits (seriesmith.limits): a built-in's on this
    machine (settings `target_limits`; `limits: null` puts it back as
    shipped), a user or show target's in its own target.json. A local target's
    pictures and sound are its graph's, so only its length, size and
    needs-a-first-frame change. Body {ep?, id, limits}."""
    from seriesmith import limits as L
    from seriesmith import settings as S
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep")) if body.get("ep") else None
    tid = _opt_str(body, "id") or ""
    try:
        t = TG.load_target(tid, root=ep)
    except TG.TargetError as e:
        raise ApiError(404, str(e))
    if t.kind not in ("video", "image"):
        raise ApiError(400, f"{t.id} is an {t.kind} target: it has no limits to change here")
    limits = body.get("limits")
    if limits is not None and not isinstance(limits, dict):
        raise ApiError(400, "limits must be an object (seriesmith.limits sections), or null")
    limits = {k: v for k, v in (limits or {}).items() if k in L.SECTIONS}
    if t.spec.get("router") is None and t.kind == "image" and limits:
        raise ApiError(400, f"{t.id} is a local workflow: its limits are what its graph does")
    if t.spec.get("router") is None and t.kind == "video":
        extra = set(limits) - LOCAL_LIMITS
        pics = set((limits.get("pictures") or {})) - {"needs_first"}
        if extra or pics:
            raise ApiError(400, f"{t.id} is a local workflow: its pictures and sound are what the graph "
                                f"wires; only its length, size and needs-a-first-frame change here")
    if not t.custom:
        base = t.shipped_spec or t.spec
        try:
            L.apply(base, limits)
        except ValueError as e:
            raise ApiError(400, str(e))
        overrides = dict(S.load_settings().target_limits)
        if limits:
            overrides[t.id] = limits
        else:
            overrides.pop(t.id, None)
        try:
            S.save_settings({"target_limits": overrides})
        except (OSError, ValueError) as e:
            raise ApiError(500, f"the settings couldn't be saved: {e}")
        path = S.settings_path()
    else:
        if body.get("limits") is None:
            raise ApiError(400, f"{t.id} is your own target: there is no shipped version to go back to")
        try:
            spec = L.apply(t.spec, limits)
        except ValueError as e:
            raise ApiError(400, str(e))
        problems = IN.validate_spec(dict(spec)) if spec.get("router") is not None else []
        problems = [p for p in problems if "built-in target's name" not in p]
        if problems:
            raise ApiError(400, "those limits can't be used: " + problems[0], problems=problems)
        path = IN.save_spec(ep or "", spec, base=os.path.dirname(t.folder))
    TG.forget_targets()
    if ep:
        episode_event(ctx, ep)
    return 200, {"ok": True, "id": t.id, "path": path,
                 "target": TG.load_target(t.id, t.kind, root=ep).describe()}


@handler
def post_targets_router_dryrun(ctx: Context, body):
    """What a Router target -- saved, or proposed and not saved yet -- would send
    for one shot: {model, arguments, prompt_chars}, each picture as its local
    path. Nothing is uploaded or sent. Body {ep, shot?, pass?, target:
    target.json (or its id)}."""
    import dataclasses
    from seriesmith.backends import File
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep"))
    pass_ = check_pass(body.get("pass"), "proxy")
    spec = body.get("target")
    if isinstance(spec, str):
        try:
            spec = TG.load_target(spec, "video", root=ep).spec
        except TG.TargetError as e:
            raise ApiError(404, str(e))
    if not isinstance(spec, dict) or not isinstance(spec.get("router"), dict):
        raise ApiError(400, "target must be a Router target's target.json, or its id")
    spec = _with_limits(spec, body.get("limits"))
    if spec.get("kind") == "image":
        return _image_dryrun(ep, spec, _opt_str(body, "ref"), _opt_str(body, "view"))
    try:
        doc = J.load_shotlist(ep, pass_)
    except FileNotFoundError:
        raise ApiError(404, "this episode has no build yet")
    shots = doc.get("shots") or []
    want = _opt_str(body, "shot")
    index = next((i for i, s in enumerate(shots) if s.get("id") == want), None) if want else \
        next((i for i, s in enumerate(shots) if s.get("subjects")), 0 if shots else None)
    if index is None:
        raise ApiError(404, f"no shot {want} in this episode" if want else "this episode has no shots")
    base = TG.load_target("seedance_2_5", "video")
    t = TG.Target(base.folder, spec)
    # the shot as every Router model gets it (the same prose and pictures),
    # sized and timed for this one
    job = J.plan_job(ep, pass_, doc, index, J.RenderRequest(shots[index]["id"], target=base.id), {})
    if job.action == "error":
        raise ApiError(400, job.error)
    preset = (spec.get("presets") or {}).get(pass_) or {}
    try:
        length = t.template.snap(job.frames)
    except ValueError as e:
        raise ApiError(400, str(e))
    job = dataclasses.replace(job, shot=dict(job.shot, length=length),
                              size=(preset["width"], preset["height"]) if preset.get("width") else job.size)
    try:
        model, args = t.module.router_call(t, job)
    except ValueError as e:
        return 200, {"ok": False, "shot": job.shot["id"], "why": str(e)}

    def plain(v):
        if isinstance(v, File):
            return {"file": v.path, **({"via": v.via} if v.via else {})}
        if isinstance(v, dict):
            return {k: plain(x) for k, x in v.items()}
        if isinstance(v, list):
            return [plain(x) for x in v]
        return v
    from seriesmith.backends.router import ROUTING
    routing = args.pop(ROUTING, None)
    text = J._prompt_text(job.shot.get("prompt") or job.prompt)
    return 200, {"ok": True, "shot": job.shot["id"], "pass": pass_, "model": model,
                 "arguments": plain(args), **({"routing": routing} if routing else {}),
                 "prompt_chars": {"written": len(text)}}


@handler
def delete_targets_custom(ctx: Context, query: dict):
    """Remove a show's own target."""
    ep = check_ep(ctx, query.get("ep"))
    tid = query.get("id") or ""
    if not tid:
        raise ApiError(400, "id is required: the custom target to remove")
    gone = IN.delete_spec(ep, tid)
    if gone:
        episode_event(ctx, ep)
    return 200, {"ok": True, "id": tid, "deleted": gone, "targets": IN.custom_targets(ep)}


def _workflow_target(tid):
    if not tid or not isinstance(tid, str):
        raise ApiError(400, "target is required: a target id")
    try:
        return TG.load_target(tid)
    except TG.TargetError as e:
        raise ApiError(400, str(e))


def _graph_view(ctx: Context, t) -> dict:
    """One target's graph block, fresh (after an install or a revert)."""
    g = J.target_graph_source(t, ctx.comfy_url)
    return {k: v for k, v in g.items() if k != "graph"}


def target_readiness(ctx: Context) -> dict:
    """Every target's readiness (edit.readiness) on this ComfyUI, from its
    /object_info and model folders, kept READY_TTL seconds per ComfyUI
    address. The handler runs off the event loop (h3pipe_routes); /object_info
    is one self-request, and headers are only read to find a family
    substitute (cached in the user folder)."""
    import threading
    import time
    global _READY_LOCK
    if _READY_LOCK is None:
        _READY_LOCK = threading.Lock()
    hit = _READY.get(ctx.comfy_url)
    if hit and time.monotonic() - hit[0] >= READY_TTL and REFRESH_BEHIND:
        _refresh_behind(("ready", ctx.comfy_url), lambda: _make_readiness(ctx, fresh=True))
        return hit[1]
    with _READY_LOCK:
        hit = _READY.get(ctx.comfy_url)
        if hit and time.monotonic() - hit[0] < READY_TTL:
            return hit[1]
        return _make_readiness(ctx, locked=True)


def _make_readiness(ctx: Context, fresh: bool = False, locked: bool = False) -> dict:
    """target_readiness worked out now and kept; `fresh` asks ComfyUI again for
    what it was built from (a refresh behind a kept answer)."""
    import time
    if not locked:
        with _READY_LOCK:
            return _make_readiness(ctx, fresh, locked=True)
    gen = _GEN[0]
    try:
        info, error = comfy_object_info(ctx, fresh=fresh), ""
    except Exception as e:
        info, error = None, f"ComfyUI didn't answer /object_info: {e}"
    rd = E.readiness(TG.list_targets(), info, ctx.model_resolve, ctx.model_cache,
                     error=error, graph_of=E.graph_lookup(target_graphs(ctx, refresh=fresh)))
    # an unanswered ComfyUI isn't worth remembering, nor one from before an install
    if info is not None and gen == _GEN[0]:
        _READY[ctx.comfy_url] = (time.monotonic(), rd)
        if DETECT_DEFAULTS:
            remember_defaults(rd)
    return rd


# whether readiness answers update the settings' detected_targets (the
# models found installed): set by the hosts (`seriesmith serve`, ComfyUI's),
# never by the CLI or the tests
DETECT_DEFAULTS = False


def remember_defaults(rd: dict) -> dict:
    """The default video and image models found installed (edit.detect_defaults)
    written to the settings' `detected_targets` when they changed: a series
    naming no model renders on them (targets.machine_default). Returns them."""
    from seriesmith import settings as S
    found = E.detect_defaults(rd, {k: TG.default_candidates(k) for k in S.DEFAULT_KINDS})
    try:
        if S.load_settings().detected_targets != found:
            S.save_settings({"detected_targets": found or None})
    except (OSError, ValueError):
        pass                                              # a settings file it can't write: next time
    return found


@handler
def put_episode_target(ctx: Context, body):
    """The episode's video target (overrides.json's episode.target): the
    default of every shot the script gives no target. null clears it. Never
    writes series.json."""
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep"))
    if "target" not in body:
        raise ApiError(400, "target is required: a video target id, or null to clear it")
    want = _opt_target(body.get("target"))
    if not any(os.path.isfile(os.path.join(ep, J.shotlist_rel(ps))) for ps in T.PASSES):
        raise ApiError(404, f"{ep} has no build: build the episode first")
    info = E.set_episode_target(ep, want)
    episode_event(ctx, ep)
    return 200, {k: info[k] for k in ("target", "target_source", "series_target")}


MATCH_ORDER = {"name": 0, "fingerprint": 1, "other": 2}


@handler
def get_models(ctx: Context, query: dict):
    """The files ComfyUI offers for one model param of a target, each checked
    against the family the target wants: `match` "name" (named like it),
    "fingerprint" (its header says so) or "other" (anything else: unknown,
    unreadable, or another family, `mismatch` true). Matching files first, in
    ComfyUI's order. Headers are read only for files whose name doesn't
    match, and cached (<user dir>/default/seriesmith/modelid_cache.json). `ep`
    (optional) adds that series config's model_families."""
    tid = query.get("target")
    if not tid or not isinstance(tid, str):
        raise ApiError(400, "target is required (a target id from /seriesmith/targets)")
    try:
        t = TG.load_target(tid)
    except TG.TargetError as e:
        raise ApiError(400, str(e))
    param = query.get("param") or "model"
    spec = t.models.get(param)
    if spec is None:
        raise ApiError(400, f"{t.id} declares no model family for {param!r} "
                            f"(it does for: {', '.join(t.models) or 'nothing'})")
    extra = {}
    ep = None
    if query.get("ep"):
        ep = check_ep(ctx, query.get("ep"))
        try:
            extra = J.series_model_families(ep)
        except ValueError as e:
            raise ApiError(400, str(e))
    cloud = _listing_cloud(ctx, query, ep, t)
    if cloud is not None:
        # the files Comfy Cloud has (its own, and any the account imported):
        # named, not read, so only names are checked
        try:
            names = cloud.choices(spec["class_type"], spec["field"]) or []
        except Exception as e:                            # noqa: BLE001  said to the page
            raise ApiError(502, f"Comfy Cloud didn't list its models: {e}")
        resolve = None
    else:
        names = ctx.model_list(spec["folder"], spec["class_type"], spec["field"])
        resolve = ctx.model_resolve
    files = []
    for n in names:
        c = TG.check_model(t, param, n, resolve, extra, ctx.model_cache) or {}
        found = c.get("found") or {}
        m = c.get("match")
        files.append({"name": n,
                      "match": m if m in ("name", "fingerprint") else "other",
                      "mismatch": bool(c.get("block")),
                      "family": spec["family"] if m == "name" else found.get("family"),
                      "label": c.get("label") if m == "name" else found.get("label") or "",
                      "confidence": "name" if m == "name" else found.get("confidence", "unknown"),
                      "detail": c.get("message") or "",
                      **({"base": found["base"]} if found.get("base") else {})})
    files.sort(key=lambda f: MATCH_ORDER[f["match"]])        # stable: ComfyUI's order within
    return 200, {"target": t.id, "param": param, "family": spec["family"],
                 "label": TG.modelid.family_label(spec["family"]),
                 "patterns": spec["patterns"] + [p for p in extra.get(spec["family"], [])
                                                 if p not in spec["patterns"]],
                 "folder": spec["folder"], "class_type": spec["class_type"],
                 "field": spec["field"], "fingerprint": resolve is not None,
                 "backend": cloud.name if cloud is not None else "local",
                 "files": files}


def _listing_cloud(ctx: Context, query: dict, ep: str | None, t):
    """The Comfy Cloud backend a model list is for, or None (this machine's):
    the request's `backend`, else the shot's / episode's / series config's
    (jobs.backend_choice; `shot` optional), when that is a cloud one."""
    name = query.get("backend") or None
    if not name and ep:
        try:
            name = J.backend_choice(T.load_overrides(ep), query.get("shot") or "", t, None, ep)[0]
        except ValueError:
            name = None
    if not isinstance(name, str) or J.backend_kind(name) != "cloud":
        return None
    backend = ctx.runner.backends.get(name) if ctx.runner is not None else None
    if backend is None:
        raise ApiError(409, f"{name} isn't set up here: a Comfy API key turns it on (Settings)")
    return backend


@handler
def get_presets(ctx: Context, query: dict):
    """The pictures the editor offers to pick from (seriesmith/presets): the
    relight presets of the edit window, the series form's looks, the shot
    form's framings and camera moves, each with its sample's name for GET
    /seriesmith/presets/image when made. `kind` answers with that one alone."""
    from seriesmith import preset_pictures as PP
    from seriesmith import presets as PR
    kinds = [query["kind"]] if query.get("kind") else list(PR.KINDS)
    PP.finish()                     # a render of one of your presets' pictures, done
    return 200, {k: PR.listing(k) for k in kinds}


PRESET_PICTURE = 480                    # an own preset's tile, its long side


@handler
def post_preset_own(ctx: Context, body):
    """Keep one of your own presets for every show on this machine
    (presets.save_own): `{kind: "look" | "relight", label, id?, text?, parts?,
    place?, subject?, picture?: {ep, ref, view?, take?}}`. `id` replaces that
    one of yours; `picture` (a ref's take, or its live picture) becomes its
    tile. Returns the preset as GET /seriesmith/presets lists it."""
    from seriesmith import preset_pictures as PP
    from seriesmith import presets as PR
    body = body_dict(body)
    kind, label = body.get("kind"), body.get("label")
    pid = body.get("id")
    if pid is not None and (not isinstance(pid, str) or not pid):
        raise ApiError(400, "id must be one of your presets' ids, or null")
    pic = body.get("picture")
    data = None
    if pic is not None:
        if not isinstance(pic, dict):
            raise ApiError(400, 'picture must be {"ep", "ref", "view"?, "take"?} or null')
        ep = check_ep(ctx, pic.get("ep"))
        s = _series(ep)
        ref = _ref(s, pic.get("ref"))
        view = _view(ref, pic.get("view"))
        take = check_take(pic.get("take"), "picture.take", nullable=True)
        path = R._picture_of(s, ref, view, take, "the preset's picture")["path"]
        try:
            data = PP.shrink(path, PRESET_PICTURE)
        except PP.PictureError as e:
            raise ApiError(400, str(e).replace("the picture", "the preset's picture", 1))
    return 200, PR.save_own(kind, label, body, pid, data)


@handler
def post_preset_own_picture(ctx: Context, body):
    """A picture for one of your presets (seriesmith/preset_pictures.py), as you
    choose: `{kind, id, from: {ep, ref, view?, take?}}` (a ref's picture or
    take), `{kind, id, from: {ep, pass, shot, take, time}}` (a frame of a
    shot's take), or a multipart `file` (a picture of your own). Returns the
    preset as the list gives it."""
    from seriesmith import preset_pictures as PP
    from seriesmith import presets as PR
    body = body_dict(body)
    kind, pid = body.get("kind"), body.get("id")
    up = body.get("file")
    src = body.get("from")
    try:
        PR.own_preset(kind, pid)
        if isinstance(up, Upload):
            if up.size > MAX_UPLOAD:
                raise ApiError(413, f"the file is over {MAX_UPLOAD // (1024 * 1024)} MB")
            if os.path.splitext(up.filename or "")[1].lower() not in R.IMAGE_EXTS:
                raise ApiError(400, f"a preset's picture is an image ({', '.join(R.IMAGE_EXTS)})")
            PP.from_file(kind, pid, up.path)
        elif up is not None:
            raise ApiError(400, "file must be sent as multipart/form-data")
        elif isinstance(src, dict) and src.get("shot") is not None:
            ep = check_ep(ctx, src.get("ep"))
            seconds = src.get("time", 0)
            if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or seconds < 0:
                raise ApiError(400, "from.time must be a number of seconds")
            PP.from_shot(kind, pid, ep, check_pass(src.get("pass")), check_shot(src.get("shot")),
                         check_take(src.get("take")), seconds)
        elif isinstance(src, dict):
            ep = check_ep(ctx, src.get("ep"))
            s = _series(ep)
            ref = _ref(s, src.get("ref"))
            PP.from_ref(kind, pid, ep, ref.id, _view(ref, src.get("view")),
                        check_take(src.get("take"), "from.take", nullable=True))
        else:
            raise ApiError(400, 'give the picture: from {ep, ref, view?, take?}, from {ep, pass, shot, '
                                'take, time}, or a file')
        return 200, next(p for p in PR.listing(kind) if p["id"] == pid)
    except (PR.PresetError, PP.PictureError) as e:
        raise ApiError(400, str(e))
    except R.UnknownRef as e:
        raise ApiError(404, str(e))


@handler
def post_preset_own_render(ctx: Context, body):
    """Render the picture of one of your presets on the sample scene, as the
    shipped ones are (preset_pictures.render): `{kind, id, target, backend?}`,
    `target` an image model for a look, an edit model for a relight. It goes on
    the queue; the list gives the preset `rendering: true` until it lands."""
    from seriesmith import preset_pictures as PP
    from seriesmith import presets as PR
    body = body_dict(body)
    kind, pid = body.get("kind"), body.get("id")
    target = _opt_image_target(body, "target")
    if not target:
        raise ApiError(400, "target is required: the model to render the picture on")
    try:
        PR.own_preset(kind, pid)
        if kind == "relight":
            t = TG.load_target(target, "image")
            if not R.is_edit_target(t):
                raise ApiError(400, f"{t.short} draws from text only: a relight's picture is an edit, "
                                    f"so pick an edit model")
        try:
            base, _ = R.resolve_workflow(ctx.comfy_url)
        except Exception as e:
            raise ApiError(500, f"{R.REFS_WORKFLOW} can't be read: {e}")
        q = PP.render(kind, pid, target, ctx.comfy, base, ctx.runner,
                      listing=J.model_lister(ctx.comfy, ctx.model_choices), resolve=ctx.model_resolve,
                      cache=ctx.model_cache, backend=_opt_backend(ctx, body))
    except (PR.PresetError, PP.PictureError, TG.TargetError) as e:
        raise ApiError(400, str(e))
    return 200, seeds_out(q)


@handler
def post_preset_own_delete(ctx: Context, body):
    """Forget one of your own presets: `{kind, id}`."""
    from seriesmith import presets as PR
    body = body_dict(body)
    PR.delete_own(body.get("kind"), body.get("id"))
    return 200, {"ok": True}


@handler
def get_preset_image(ctx: Context, query: dict):
    """A preset's sample (a JPEG, a camera move's an mp4), by the name GET
    /seriesmith/presets gave."""
    from seriesmith import presets as PR
    path = PR.image_path(str(query.get("name") or ""))
    if path is None:
        raise ApiError(404, f"no preset picture {query.get('name')!r}")
    return 200, {"path": path, "content_type": "video/mp4" if path.endswith(".mp4") else "image/jpeg"}


# ---------------------------------------------------------------------------
# assemble
# ---------------------------------------------------------------------------

@handler
def post_assemble(ctx: Context, body):
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep"))
    pass_ = check_pass(body.get("pass"))
    partial = body.get("partial", True)
    if not isinstance(partial, bool):
        raise ApiError(400, "partial must be true or false")
    # Phase 13: the cut from its upscales, and/or at a set size
    upscaled = body.get("upscaled", False)
    if not isinstance(upscaled, bool):
        raise ApiError(400, "upscaled must be true or false")
    size = body.get("size")
    if size is not None and (not isinstance(size, str) or not re.fullmatch(r"\d+x\d+", size)):
        raise ApiError(400, "size must look like 1920x1080, or be null")
    # the cut with the series intro and outro around it (publish)
    publish = body.get("publish", False)
    if not isinstance(publish, bool):
        raise ApiError(400, "publish must be true or false")
    J.load_shotlist(ep, pass_)
    res = E.assemble_episode(ep, pass_, partial, upscaled=upscaled, size=size)
    if not publish or not res["ok"]:
        return 200, res
    pub = E.publish_episode(ep, res["output"])
    return 200, {"ok": pub["ok"], "output": pub["output"] if pub["ok"] else res["output"],
                 "cut": res["output"], "published": pub["output"],
                 "report": res["report"] + "\n" + pub["report"], "error": pub["error"]}

# ---------------------------------------------------------------------------
# references (Phase 5)
# ---------------------------------------------------------------------------

def _series(ep: str):
    try:
        return R.load_series(ep)
    except FileNotFoundError as e:
        raise ApiError(404, str(e))
    except ValueError as e:
        raise ApiError(500, f"series.json can't be read: {e}")


def _ref(s, ref_id):
    try:
        return R.find_ref(s, ref_id)
    except R.RefError as e:
        raise ApiError(400, str(e))
    except R.UnknownRef as e:
        raise ApiError(404, str(e))


def _view(ref, v, required: bool = False, sheet: bool = False):
    """A view for this ref, or 400. `sheet` also takes `"sheet"`, a character's
    whole supplied sheet (P8): the routes that move a file or a pick around take
    it, the ones that generate or word a view do not."""
    if v is not None and not isinstance(v, str):
        raise ApiError(400, "view must be a view name or null")
    return R.check_view(ref, v, required=required, allow_sheet=sheet)


def ref_event(ctx: Context, ep: str, ref_id: str, view, take, status: str) -> None:
    ctx.emit("seriesmith.ref", {"ep": ep, "ref": ref_id, "view": view, "take": take,
                            "status": status})


def sweep_refs(ctx: Context, s) -> list:
    """Close queued ref takes whose job is gone (refs.sweep). A ComfyUI that
    doesn't answer means no sweep this time, not an error."""
    try:
        changed = R.sweep(s, ctx.comfy)
    except Exception:
        return []
    for t in changed:
        ref_event(ctx, s.ep, t.ref, t.view, t.take, t.status)
    auto_pick_refs(ctx, s)
    return changed


def auto_pick_refs(ctx: Context, s) -> None:
    """Refs with no live file yet take their first finished candidate
    (refs.auto_pick); a stitch failure is left for an explicit pick to report."""
    picked = False
    for ref in R.series_refs(s) + R.keyframe_refs(s.ep):
        try:
            for res in R.auto_pick(s, ref):
                ref_event(ctx, s.ep, ref.id, res.take.view, res.take.take, "picked")
                picked = True
        except Exception:
            continue
    if picked:
        episode_event(ctx, s.ep)


def image_ready(ctx: Context):
    """ready(target) for the image-target defaults: its required files are
    among what ComfyUI offers (refs.target_ready)."""
    return R.target_ready(J.model_lister(ctx.comfy, ctx.model_choices))


@handler
def get_refs(ctx: Context, query: dict):
    ep = check_ep(ctx, query.get("ep"))
    s = _series(ep)
    if not ctx.sweep_later:
        sweep_refs(ctx, s)
    # one listing per folder, one resolution of each cut, one look at each file
    with T.one_look(), E.cut_memo():
        out = seeds_out(R.refs_listing(ep, ready=image_ready(ctx)))
    if ctx.sweep_later:
        # a server closes the takes whose job is gone (every take's record
        # read, ComfyUI asked) after the listing has gone, not before it: what
        # it changes reaches the page as ref events, which reload it
        import threading
        threading.Thread(target=sweep_refs, args=(ctx, s), daemon=True, name="seriesmith-sweep-refs").start()
    return 200, out


@handler
def get_refs_owner_takes(ctx: Context, query: dict):
    """A shared ref whose live file another episode picked (its `live_owner`):
    that episode's candidates for it, read-only (refs.owner_takes). Asked for
    when its row opens, so the listing doesn't read every sibling's. {"owner",
    "takes"}; an empty list when this episode is the owner or there is none."""
    ep = check_ep(ctx, query.get("ep"))
    s = _series(ep)
    ref = R.find_ref(s, query.get("ref"))
    live = ref.file
    sha = T.file_sha1(live) if live and os.path.isfile(live) else None
    owner = R.shared_context(ep)["owner"].get(sha) if sha else None
    if not owner or owner == R.ep_name(ep):
        return 200, {"owner": owner, "takes": []}
    return 200, seeds_out({"owner": owner, "takes": R.owner_takes(ep, ref, owner)})


@handler
def put_refs_defaults(ctx: Context, body):
    """The episode's ref-target choices (overrides.json's
    episode.refs_target / episode.keyframe_target / episode.voice_target):
    `target` for series refs, `keyframe_target` for shot keyframes,
    `voice_target` for voices (an audio target); null clears one, a key left
    out is kept. Never writes series.json. Returns the defaults as GET
    /seriesmith/refs gives them."""
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep"))
    s = _series(ep)
    fields = {}
    for k, kind in (("target", "image"), ("keyframe_target", "image"),
                    ("voice_target", "audio")):
        if k in body:
            v = body[k]
            if v is not None and (not isinstance(v, str)):
                raise ApiError(400, f"{k} must be an {kind} target id or null")
            fields[k] = v or None
    if not fields:
        raise ApiError(400, "give target, keyframe_target and/or voice_target (a target id "
                            "of that kind, or null to clear it)")
    R.set_image_defaults(ep, fields)
    d = R.image_defaults(s, image_ready(ctx))
    episode_event(ctx, ep)
    return 200, {"defaults": d}


@handler
def delete_refs_pick(ctx: Context, query: dict):
    """Unpick a ref (refs.clear_pick): its live file goes, every take stays,
    and auto-pick leaves it alone until something is picked. For a shot
    keyframe this is Clear: the shot no longer uses one. Returns the ref as
    GET /seriesmith/refs lists it."""
    ep = check_ep(ctx, query.get("ep"))
    s = _series(ep)
    ref = _ref(s, query.get("ref"))
    view = _view(ref, query.get("view") or None, sheet=True)
    res = R.clear_pick(s, ref, view)
    ref_event(ctx, ep, ref.id, view, res.was, "cleared")
    episode_event(ctx, ep)
    return 200, seeds_out(R.ref_json(s, ref, R.used_by(s, [ref]), ready=image_ready(ctx)))


@handler
def post_refs_generate(ctx: Context, body):
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep"))
    s = _series(ep)
    ref = _ref(s, body.get("ref"))
    view = _view(ref, body.get("view"))
    count = body.get("count", 1)
    if count is None:
        count = 1
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 16:
        raise ApiError(400, "count must be a whole number from 1 to 16")
    seed_mode = body.get("seed_mode") or "auto"
    if seed_mode not in ("auto", "new", "same"):
        raise ApiError(400, f"seed_mode must be auto, new or same, not {seed_mode!r}")
    prompt = body.get("prompt")
    if prompt is not None and not isinstance(prompt, str):
        raise ApiError(400, "prompt must be text or null")
    kind = R.ref_target_kind(ref)
    target = body.get("target")
    if target is not None and (not isinstance(target, str) or not target):
        raise ApiError(400, f"target must be an {kind} target id or null")
    if target:
        try:
            TG.load_target(target, kind)
        except TG.TargetError as e:
            raise ApiError(400, str(e))
    negative = body.get("negative")
    if negative is not None and not isinstance(negative, str):
        raise ApiError(400, "negative must be text or null")
    seconds = body.get("seconds")
    if seconds is not None:
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
            raise ApiError(400, "seconds must be a number of seconds, or null")
        if kind != "audio":
            raise ApiError(400, f"seconds is only for a voice ref, not {ref.id}")
    pass_ = check_pass(body.get("pass"), "final")
    # an edit of a picture the ref already has (refs.plan_edit): `prompt` is
    # the instruction, `edit` says which picture and what else comes along
    cfg = body.get("cfg")
    if cfg is not None and (isinstance(cfg, bool) or not isinstance(cfg, (int, float))):
        raise ApiError(400, "cfg must be a number or null")
    size = body.get("size")
    if size is not None:
        R.parse_override_size(size)
    params = body.get("params")
    if params is not None:
        R.check_override_value("params", params)
    pano = body.get("pano")
    if pano is not None and not isinstance(pano, dict):
        raise ApiError(400, 'pano must be {"with": [location ids]} or null')
    edit = body.get("edit")
    if edit is not None and not isinstance(edit, dict):
        raise ApiError(400, 'edit must be {"take": n or null, "with": [...], "wrap": bool} '
                            'or null')
    req = R.GenRequest(ref=ref.id, view=view, count=count, seed_mode=seed_mode,
                       seed=seed_in(body.get("seed")), prompt=prompt or None,
                       model=_opt_str(body, "model") or None,
                       loras=_opt_loras(body.get("loras")),
                       steps=_opt_steps(body.get("steps")), note=_opt_str(body, "note") or "",
                       target=target or None, negative=negative, pass_=pass_,
                       seconds=seconds, edit=edit, cfg=cfg, size=size or None,
                       params=params or None, pano=pano)
    why = None if (edit is not None or pano is not None) else R.can_generate(s, ref)
    if why:
        raise ApiError(400, why)
    try:
        base, _ = R.resolve_workflow(ctx.comfy_url)
    except Exception as e:
        raise ApiError(500, f"{R.REFS_WORKFLOW} can't be read: {e}")
    try:
        result = R.queue_generate(s, req, ctx.comfy, base, save_node=True,
                                  listing=J.model_lister(ctx.comfy, ctx.model_choices),
                                  resolve=ctx.model_resolve, cache=ctx.model_cache,
                                  runner=ctx.runner, backend=_opt_backend(ctx, body))
    except R.RefError as e:
        raise ApiError(400, str(e))
    except R.UnknownRef as e:
        raise ApiError(404, str(e))
    for q in result["queued"]:
        # "queued" even if the job has already finished: the saver sends its own event
        ref_event(ctx, ep, q["ref"], q["view"], q["take"], "queued")
    for err in result["errors"]:
        if err.get("take"):
            ref_event(ctx, ep, err["ref"], err["view"], err["take"], "failed")
    if result["queued"] or any(e.get("take") for e in result["errors"]):
        episode_event(ctx, ep)
    return 200, seeds_out(result)


@handler
def post_refs_tour(ctx: Context, body):
    """P5: a camera tour of a location on H3 (tour.py), from its live plate:
    `{ep, ref, move, seconds?, count?}`. Queues the videos and answers at once;
    a background thread waits for each, finds its held frames and adds them as
    the location's `tour` takes, sending `seriesmith.ref` as each lands. Returns
    {"queued": [{tour, comfy_prompt_id}]}."""
    from seriesmith import tour as TR
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep"))
    s = _series(ep)
    ref = _ref(s, body.get("ref"))
    seconds = body.get("seconds", TR.DEFAULT_SECONDS)
    count = body.get("count", 1)
    seed = seed_in(body.get("seed")) if body.get("seed") else None
    backend = finish_backend(ctx, body)
    # each tour a job on seriesmith's queue: its plate uploaded, its holds
    # found when the video comes back
    ids = [ctx.runner.enqueue_tour(s, ref, side, g, backend) for side, g in
           TR.plan_tours(s, ref, body.get("move") or "", None, seconds, count, seed)]
    episode_event(ctx, ep)
    return 200, {"queued": [{"tour": n, "comfy_prompt_id": i} for n, i in ids]}


@handler
def post_refs_tour_frame(ctx: Context, body):
    """P5: any moment of a finished tour's video as a hold: `{ep, ref, tour,
    seconds}` (tour.grab_frame). Returns the new take."""
    from seriesmith import tour as TR
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep"))
    s = _series(ep)
    ref = _ref(s, body.get("ref"))
    tour = check_take(body.get("tour"), "tour")
    t = TR.grab_frame(s, ref, tour, body.get("seconds"))
    ref_event(ctx, ep, ref.id, R.TOUR_VIEW, t.take, "ok")
    episode_event(ctx, ep)
    return 200, R.take_json(ep, ref, t)


@handler
def post_refs_copy_take(ctx: Context, body):
    """P5: copy a finished take into another ref as a new candidate (a tour's
    hold into a location or an angle of it): `{ep, ref, view?, take, to}`.
    Returns the new take."""
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep"))
    s = _series(ep)
    src = _ref(s, body.get("ref"))
    dest = _ref(s, body.get("to"))
    take = check_take(body.get("take"))
    view = body.get("view")
    try:
        t = R.copy_take(s, src, view, take, dest)
    except R.RefError as e:
        raise ApiError(400, str(e))
    except R.UnknownRef as e:
        raise ApiError(404, str(e))
    ref_event(ctx, ep, dest.id, None, t.take, "ok")
    episode_event(ctx, ep)
    return 200, R.take_json(ep, dest, t)


@handler
def post_refs_relight(ctx: Context, body):
    """A sequence relight (seriesmith.relight): `{ep, relight, sequence? |
    locations?, suffix?, target?, count?, repoint?, dry_run?}`. Each plate the
    sequence uses (or each of `locations`) gets a relit location in the series
    config (`<id>_<suffix>`, of: it, relight: the preset or instruction), and a
    generate of each is queued on the edit target (the request's, else the
    episode's), an edit of the source's live plate. `repoint` (a sequence
    only) points the sequence and its shots' `plate:` lines at the relit ones
    and rebuilds. Returns {locations: [{source, id, exists}], queued, errors,
    repointed}; `dry_run` writes and queues nothing."""
    from seriesmith import relight as RL
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep"))
    sequence, locations = body.get("sequence"), body.get("locations")
    if (sequence is None) == (locations is None):
        raise ApiError(400, "give a sequence or a list of locations")
    if sequence is not None and (not isinstance(sequence, str) or not sequence):
        raise ApiError(400, "sequence must be a sequence id")
    if locations is not None and (not isinstance(locations, list) or not locations
                                  or not all(isinstance(x, str) and x for x in locations)):
        raise ApiError(400, "locations must be a list of location ids")
    relight = body.get("relight")
    if not isinstance(relight, str) or not relight.strip():
        raise ApiError(400, "relight must be a relight preset id or the instruction")
    suffix = body.get("suffix")
    if suffix is not None and not isinstance(suffix, str):
        raise ApiError(400, "suffix must be text or null")
    target = _opt_image_target(body, "target")
    count = body.get("count", 1)
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 16:
        raise ApiError(400, "count must be a whole number from 1 to 16")
    repoint, dry_run = body.get("repoint", False), body.get("dry_run", False)
    if not isinstance(repoint, bool) or not isinstance(dry_run, bool):
        raise ApiError(400, "repoint and dry_run must be true or false")
    if repoint and sequence is None:
        raise ApiError(400, "repoint is for a sequence: its shots are what get re-pointed")
    s = _series(ep)
    if sequence is not None:
        locations = RL.sequence_locations(ep, sequence)
    planned = RL.plan(s, locations, relight, suffix or None)
    out = {"locations": [{"source": p["source"], "id": p["id"], "exists": p["exists"],
                          "entry": p["entry"]} for p in planned],
           "queued": [], "errors": [], "repointed": []}
    if dry_run:
        return 200, out
    RL.write_locations(s, planned)
    s = _series(ep)
    try:
        base, _ = R.resolve_workflow(ctx.comfy_url)
    except Exception as e:
        raise ApiError(500, f"{R.REFS_WORKFLOW} can't be read: {e}")
    listing = J.model_lister(ctx.comfy, ctx.model_choices)
    for p in planned:
        ref = _ref(s, f"location:{p['id']}")
        try:
            t = R.edit_target_for(s, ref, target)
            req = R.GenRequest(ref=ref.id, count=count, target=t.id)
            result = R.queue_generate(s, req, ctx.comfy, base, save_node=True, listing=listing,
                                      resolve=ctx.model_resolve, cache=ctx.model_cache,
                                      runner=ctx.runner, backend=_opt_backend(ctx, body))
        except (R.RefError, R.UnknownRef) as e:
            out["errors"].append({"ref": ref.id, "error": str(e)})
            continue
        for q in result["queued"]:
            ref_event(ctx, ep, q["ref"], q["view"], q["take"], "queued")
        for err in result["errors"]:
            if err.get("take"):
                ref_event(ctx, ep, err["ref"], err["view"], err["take"], "failed")
        out["queued"] += result["queued"]
        out["errors"] += result["errors"]
    if repoint:
        out["repointed"] = RL.repoint(ep, sequence, {p["from"]: p["id"] for p in planned})
        if out["repointed"]:
            E.build_episode(ep)
    episode_event(ctx, ep)
    return 200, seeds_out(out)


@handler
def put_refs_pick(ctx: Context, body):
    """Make a candidate the live file. A voice whose character has no
    `voice_sample` yet is written to refs/voices/<id>.wav and the series
    config gains that line through the Phase 9a save path: the answer then
    carries `series_changed: true` and `path`."""
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep"))
    s = _series(ep)
    ref = _ref(s, body.get("ref"))
    view = _view(ref, body.get("view"), required=True, sheet=True)
    take = check_take(body.get("take"))
    force = body.get("force", False)
    if not isinstance(force, bool):
        raise ApiError(400, "force must be true or false")
    try:
        res = R.pick_take(s, ref, view, take, force=force)
    except R.NotUsable as e:
        raise ApiError(409, f"{e}; pick it anyway with \"force\": true")
    except R.UnknownRef as e:
        raise ApiError(404, str(e))
    except R.RefError as e:
        raise ApiError(400, str(e))
    except R.StitchError as e:
        ref_event(ctx, ep, ref.id, view, take, "picked")
        episode_event(ctx, ep)
        raise ApiError(500, f"picked, but the sheet could not be stitched: {e}")
    ref_event(ctx, ep, ref.id, view, take, "picked")
    episode_event(ctx, ep)
    if res.series_changed:
        s = _series(ep)                                   # series.json gained voice_sample
        ref = _ref(s, ref.id)
    out = seeds_out(R.ref_json(s, ref, R.used_by(s, [ref])))
    out["series_changed"] = res.series_changed
    return 200, out


MAX_UPLOAD = 64 * 1024 * 1024        # POST /seriesmith/refs/import as multipart
MATCH_LIMIT = 500                    # names in one POST /seriesmith/refs/match


class Upload:
    """A file the adapter received in a multipart POST /seriesmith/refs/import
    and saved to a temporary file (it deletes it after the handler)."""

    def __init__(self, path: str, filename: str, size: int):
        self.path, self.filename, self.size = path, filename, size


def _pick_flag(v) -> bool:
    """`pick` from JSON (true/false/null) or a form field ("1", "true", "0", "")."""
    if v is None or v is False or v == "":
        return False
    if v is True:
        return True
    if isinstance(v, str) and v.strip().lower() in ("1", "true", "yes", "on"):
        return True
    if isinstance(v, str) and v.strip().lower() in ("0", "false", "no", "off"):
        return False
    raise ApiError(400, "pick must be true or false (a form sends \"1\" or \"0\")")


@handler
def post_refs_import(ctx: Context, body):
    """A file as a new take (source "imported"): `source_path`, a file on
    this machine (JSON), or `file`, an upload (multipart, which the adapter
    hands over as an Upload). `pick` picks it."""
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep"))
    s = _series(ep)
    ref = _ref(s, body.get("ref"))
    view = _view(ref, body.get("view") or None, required=True, sheet=True)
    pick = _pick_flag(body.get("pick"))
    up = body.get("file")
    if isinstance(up, Upload):
        if up.size > MAX_UPLOAD:
            raise ApiError(413, f"the file is over {MAX_UPLOAD // (1024 * 1024)} MB")
        src, name = up.path, up.filename or ""
        R.check_import_type(ref, name)
    elif up is not None:
        raise ApiError(400, "file must be sent as multipart/form-data")
    else:
        src, name = body.get("source_path"), None
        if not isinstance(src, str) or not src.strip():
            raise ApiError(400, "source_path is required: the file's absolute path on this "
                                "machine (or upload it as multipart `file`)")
        src = src.strip()
    t = R.import_take(s, ref, view, src, note=_opt_str(body, "note") or "",
                      original_name=name)
    ref_event(ctx, ep, ref.id, view, t.take, t.status)
    if pick:
        try:
            R.pick_take(s, ref, view, t.take)
        except R.StitchError as e:
            ref_event(ctx, ep, ref.id, view, t.take, "picked")
            episode_event(ctx, ep)
            raise ApiError(500, f"imported and picked, but the sheet could not be stitched: {e}")
        except (R.RefError, R.NotUsable) as e:
            episode_event(ctx, ep)
            raise ApiError(400, f"imported as take {t.take}, but not picked: {e}")
        ref_event(ctx, ep, ref.id, view, t.take, "picked")
        t = R.get_take(ref, view, t.take)
    episode_event(ctx, ep)
    return 200, seeds_out(R.take_json(ep, ref, t))


@handler
def post_refs_match(ctx: Context, body):
    """P8: which slot does each of these file names mean? Body `{ep, names}`,
    answer `{matched, unmatched}` (refs.match_files). Read-only, and the names
    are names -- no file is sent, so the editor can show the table it is about
    to act on before a single byte is uploaded."""
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep"))
    names = body.get("names")
    if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
        raise ApiError(400, "names must be a list of file names")
    if len(names) > MATCH_LIMIT:
        raise ApiError(400, f"{len(names)} names is more than {MATCH_LIMIT} at a time")
    return 200, R.match_files(_series(ep), names)


@handler
def post_refs_discard(ctx: Context, body):
    """Move a ref candidate to refs/_takes/_trash/ (refs.discard_take); if it
    was the pick, the ref (view) is cleared as DELETE /seriesmith/refs/pick does.
    Returns the ref as GET /seriesmith/refs lists it."""
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep"))
    s = _series(ep)
    ref = _ref(s, body.get("ref"))
    view = _view(ref, body.get("view") or None, required=True, sheet=True)
    take = check_take(body.get("take"))
    try:
        res = R.discard_take(s, ref, view, take)
    except T.StillQueued as e:
        raise ApiError(409, str(e))
    except R.UnknownRef as e:
        raise ApiError(404, str(e))
    except R.RefError as e:
        raise ApiError(400, str(e))
    ref_event(ctx, ep, ref.id, view, take, "discarded")
    if res.cleared is not None:
        ref_event(ctx, ep, ref.id, view, take, "cleared")
    episode_event(ctx, ep)
    return 200, seeds_out(R.ref_json(s, ref, R.used_by(s, [ref]), ready=image_ready(ctx)))


def _opt_image_target(body: dict, key: str) -> str | None:
    v = body.get(key)
    if v is None or v == "":
        return None
    if not isinstance(v, str):
        raise ApiError(400, f"{key} must be an image target id or null")
    try:
        TG.load_target(v, "image")
    except TG.TargetError as e:
        raise ApiError(400, str(e))
    return v


@handler
def post_refs_generate_missing(ctx: Context, body):
    """Every missing ref at once (refs.generate_missing): a candidate for
    each series ref this pass uses with no live file (not cleared, nothing
    queued or waiting), and every needed keyframe filled as `seriesmith keyframe
    --missing` does. Returns {queued, picked, skipped, errors}; `dry_run`
    writes and queues nothing."""
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep"))
    pass_ = check_pass(body.get("pass"))
    kinds = body.get("kinds")
    if kinds is None:
        kinds = list(R.MISSING_KINDS)
    if (not isinstance(kinds, list) or not kinds
            or not all(k in R.MISSING_KINDS for k in kinds)):
        raise ApiError(400, "kinds must be a list of \"series\" and/or \"keyframe\"")
    target = _opt_image_target(body, "target")
    keyframe_target = _opt_image_target(body, "keyframe_target")
    dry_run = body.get("dry_run", False)
    if not isinstance(dry_run, bool):
        raise ApiError(400, "dry_run must be true or false")
    s = _series(ep)
    J.load_shotlist(ep, pass_)                           # 404 without a build
    base = None
    if not dry_run:
        try:
            base, _ = R.resolve_workflow(ctx.comfy_url)
        except Exception as e:
            raise ApiError(500, f"{R.REFS_WORKFLOW} can't be read: {e}")
    listing = J.model_lister(ctx.comfy, ctx.model_choices)
    result = R.generate_missing(s, None if dry_run else ctx.comfy, pass_, kinds, target,
                                keyframe_target, dry_run, base, listing=listing,
                                resolve=ctx.model_resolve, cache=ctx.model_cache,
                                runner=None if dry_run else ctx.runner,
                                backend=_opt_backend(ctx, body))
    if not dry_run:
        for q in result["queued"]:
            ref_event(ctx, ep, q["ref"], q["view"], q["take"], "queued")
        for p in result["picked"]:
            ref_event(ctx, ep, p["ref"], None, p["take"], "ok")
            ref_event(ctx, ep, p["ref"], None, p["take"], "picked")
        for err in result["errors"]:
            if err.get("take"):
                ref_event(ctx, ep, err["ref"], err.get("view"), err["take"], "failed")
        if result["queued"] or result["picked"] or any(e.get("take") for e in result["errors"]):
            episode_event(ctx, ep)
    return 200, seeds_out(result)


@handler
def post_refs_keyframe(ctx: Context, body):
    """A shot's first (or last) keyframe from a frame of another shot's take:
    by default the previous (next) shot in the pass's cut, the take its cut
    entry uses, its last (first) frame (refs.keyframe_from_take)."""
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep"))
    pass_ = check_pass(body.get("pass"))
    shot = check_shot(body.get("shot"))
    which = body.get("which") or "first"
    if which not in ("first", "last"):
        raise ApiError(400, f"which must be \"first\" or \"last\", not {which!r}")
    source_shot = body.get("source_shot")
    if source_shot is not None and (not isinstance(source_shot, str) or not source_shot):
        raise ApiError(400, "source_shot must be a shot id or null")
    source_take = check_take(body.get("source_take"), "source_take", nullable=True)
    frame = body.get("frame")
    if isinstance(frame, str) and re.fullmatch(r"\s*-?\d+\s*", frame):
        frame = int(frame)
    if frame is not None and frame not in ("first", "last") and (
            isinstance(frame, bool) or not isinstance(frame, int)):
        raise ApiError(400, "frame must be a frame number, \"first\", \"last\" or null")
    pick = body.get("pick")
    if pick is not None and not isinstance(pick, bool):
        raise ApiError(400, "pick must be true, false or null")
    note = _opt_str(body, "note") or ""
    s = _series(ep)
    try:
        res = R.keyframe_from_take(s, shot, which, source_shot, source_take, frame, pass_,
                                   pick=pick, note=note)
    except R.RefError as e:
        raise ApiError(400, str(e))
    except R.UnknownRef as e:
        raise ApiError(404, str(e))
    except R.NotUsable as e:
        raise ApiError(409, str(e))
    except R.FfmpegMissing as e:
        raise ApiError(500, str(e))
    ref_event(ctx, ep, res.ref.id, None, res.take.take, res.take.status)
    if res.picked:
        ref_event(ctx, ep, res.ref.id, None, res.take.take, "picked")
    episode_event(ctx, ep)
    return 200, seeds_out(R.ref_json(s, res.ref, R.used_by(s, [res.ref])))


def _span(body: dict, key: str):
    """One end of a span in seconds, or None (`start` then means 0, `end` the
    end of the take)."""
    v = body.get(key)
    if v is None:
        return None
    if isinstance(v, str):
        try:
            v = float(v)
        except ValueError:
            raise ApiError(400, f"{key} must be a number of seconds") from None
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ApiError(400, f"{key} must be a number of seconds")
    return float(v)


@handler
def post_refs_voice_from_take(ctx: Context, body):
    """A line the model already spoke becomes a voice sample: cut
    `start`..`end` seconds out of a shot take's sound into a new candidate of
    the voice ref (refs.voice_from_take, source "from_take"). No model
    runs. Picked when the voice has no live file yet (`pick` forces or
    forbids it); picking a voice whose character has no `voice_sample` also
    writes the series config."""
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep"))
    s = _series(ep)
    ref = _ref(s, body.get("ref"))
    shot = check_shot(body.get("shot"))
    take = check_take(body.get("take"))
    pass_ = check_pass(body.get("pass"))
    start = _span(body, "start") or 0.0
    end = _span(body, "end")
    pick = body.get("pick")
    if pick is not None and not isinstance(pick, bool):
        raise ApiError(400, "pick must be true, false or null")
    try:
        res = R.voice_from_take(s, ref, shot, take, pass_, start, end, pick=pick,
                                note=_opt_str(body, "note") or "")
    except R.RefError as e:
        raise ApiError(400, str(e))
    except R.UnknownRef as e:
        raise ApiError(404, str(e))
    except R.NotUsable as e:
        raise ApiError(409, str(e))
    except R.FfmpegMissing as e:
        raise ApiError(500, str(e))
    ref_event(ctx, ep, ref.id, None, res.take.take, res.take.status)
    if res.picked:
        ref_event(ctx, ep, ref.id, None, res.take.take, "picked")
        s = _series(ep)                                   # a pick may have written series.json
        ref = _ref(s, ref.id)
    episode_event(ctx, ep)
    out = seeds_out(R.ref_json(s, ref, R.used_by(s, [ref])))
    out.update(picked=res.picked, take=res.take.take, source=res.source)
    return 200, out


REF_OVERRIDE_FIELDS = ("prompt", "seed", "model", "loras", "steps", "note", "target",
                       "size", "cfg", "negative", "params")


def _ref_override_json(s, ref, view) -> dict:
    o = R.override_view(s, ref, view, R.load_overrides(ref.home))
    return dict(o["values"], stale=o["stale"])


@handler
def put_refs_override(ctx: Context, body):
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep"))
    s = _series(ep)
    ref = _ref(s, body.get("ref"))
    view = _view(ref, body.get("view"))
    fields = body.get("fields")
    if not isinstance(fields, dict):
        raise ApiError(400, "fields must be an object, e.g. {\"seed\": \"1234\"}")
    unknown = set(fields) - set(REF_OVERRIDE_FIELDS)
    if unknown:
        raise ApiError(400, f"unknown override field(s) {', '.join(sorted(unknown))}: "
                            f"one of {', '.join(REF_OVERRIDE_FIELDS)}")
    clean = {}
    if "seed" in fields:
        clean["seed"] = seed_in(fields["seed"])
    if "note" in fields:
        if fields["note"] is not None and not isinstance(fields["note"], str):
            raise ApiError(400, "note must be text or null")
        clean["note"] = fields["note"] or None
    if "prompt" in fields:
        if fields["prompt"] is not None and not isinstance(fields["prompt"], str):
            raise ApiError(400, "prompt must be text or null")
        clean["prompt"] = fields["prompt"] or None
    if "model" in fields:
        m = fields["model"]
        if m is not None and not isinstance(m, str):
            raise ApiError(400, "model must be a file name or null")
        clean["model"] = m or None
    if "loras" in fields:
        clean["loras"] = _opt_loras(fields["loras"])
    if "steps" in fields:
        clean["steps"] = _opt_steps(fields["steps"])
    if "target" in fields:
        t = fields["target"]
        if t is not None and not isinstance(t, str):
            raise ApiError(400, "target must be an image target id or null")
        clean["target"] = t or None
    # P4: size ("WxH"), cfg, negative and params (sampler knobs) are checked
    # by refs.set_ref_override
    for k in ("size", "cfg", "negative", "params"):
        if k in fields:
            v = fields[k]
            clean[k] = None if v in ("", {}) else v
    ov = R.load_overrides(ref.home)
    R.set_ref_override(ov, ref, view, clean,
                       R.prompt_hash(R.built_prompt(s, ref, view)))
    R.save_overrides(ref.home, ov)
    episode_event(ctx, ep)
    return 200, seeds_out({"override": _ref_override_json(s, ref, view)})


@handler
def delete_refs_override(ctx: Context, query: dict):
    ep = check_ep(ctx, query.get("ep"))
    s = _series(ep)
    ref = _ref(s, query.get("ref"))
    view = _view(ref, query.get("view") or None)
    ov = R.load_overrides(ref.home)
    R.clear_ref_override(ov, ref.id, view)
    R.save_overrides(ref.home, ov)
    episode_event(ctx, ep)
    return 200, seeds_out({"override": _ref_override_json(s, ref, view)})


# ---------------------------------------------------------------------------
# the script and the series config (Phase 9a)
# ---------------------------------------------------------------------------

def _file(v) -> str:
    if v not in P.H.FILES:
        raise ApiError(400, f"file must be 'script' or 'series', not {v!r}")
    return v


def _flag(v) -> bool:
    return v is True or (isinstance(v, str) and v.lower() in ("1", "true", "yes"))


@handler
def get_source(ctx: Context, query: dict):
    ep = check_ep(ctx, query.get("ep"))
    src = P.H.read_source(ep, _file(query.get("file")))
    return 200, P.H.source_json(src, hash_only=_flag(query.get("hash_only")))


@handler
def post_source_check(ctx: Context, body):
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep"))
    file = _file(body.get("file"))
    text = body.get("text")
    if not isinstance(text, str):
        raise ApiError(400, "text must be the file's text")
    return 200, P.H.check_text(ep, file, text)


@handler
def post_shot_preview(ctx: Context, body):
    """The shot form's preview: `{ep, pass, text, shot}` -- the script with the
    shot as edited -- compiled in memory (source.preview_shot)."""
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep"))
    pass_ = check_pass(body.get("pass"), "proxy")
    text, shot = body.get("text"), body.get("shot")
    if not isinstance(text, str) or not isinstance(shot, str) or not shot:
        raise ApiError(400, "text (the script) and shot (its id) are required")
    return 200, P.H.preview_shot(ep, text, shot, pass_)


@handler
def put_source(ctx: Context, body):
    """Save the script or the series config (409 when it changed on disk
    since `base_hash`), then rebuild unless `rebuild` is false."""
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep"))
    file = _file(body.get("file"))
    base_hash = body.get("base_hash")
    if not isinstance(base_hash, str) or not base_hash:
        raise ApiError(400, "base_hash is required: the hash the text was read at")
    rebuild = body.get("rebuild", True)
    if not isinstance(rebuild, bool):
        raise ApiError(400, "rebuild must be true or false")
    saved = P.H.save_source(ep, file, body.get("text"), base_hash)
    build = E.build_episode(ep) if rebuild else None
    episode_event(ctx, ep)
    return 200, {"hash": saved["hash"], "check": saved["check"], "build": build}


@handler
def get_promote(ctx: Context, query: dict):
    ep = check_ep(ctx, query.get("ep"))
    return 200, seeds_out(P.plan(ep, query.get("shot") or None))


@handler
def post_promote(ctx: Context, body):
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep"))
    items = body.get("items")
    if items != "all" and not (isinstance(items, list)
                               and all(isinstance(i, str) for i in items)):
        raise ApiError(400, "items must be a list of item ids from the plan, or \"all\"")
    hashes = body.get("hashes")
    if not isinstance(hashes, dict):
        raise ApiError(400, "hashes is required: {\"script\", \"series\"} from the plan")
    shot = body.get("shot") or None
    if shot is not None and not isinstance(shot, str):
        raise ApiError(400, "shot must be a shot id")
    result = P.apply(ep, items, hashes, shot)
    refs = result.pop("refs", [])
    if result["promoted"]:
        episode_event(ctx, ep)
        for ref_id in refs:
            ref_event(ctx, ep, ref_id, None, None, "promoted")
    return 200, seeds_out(result)


# ---------------------------------------------------------------------------
# the dialogue recording: attaching one, and aligning to it (Phase 9c A)
# ---------------------------------------------------------------------------

@handler
def get_align_ready(ctx: Context, query: dict):
    """What align needs (ffmpeg, numpy, a Whisper), checked against the
    Python that would run it, with the pip line for whatever is missing."""
    return 200, K.align_ready()


@handler
def post_track(ctx: Context, body):
    """Attach a dialogue recording: `source_path` (a file on this machine) or
    `file` (multipart, as /refs/import). It lands in <ep>/audio/, the series
    config's `audio.track` and `audio.mode` are written through the Phase 9a
    save path, and the episode is rebuilt. `track: null` clears it."""
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep"))
    pass_ = check_pass(body.get("pass"))
    up = body.get("file")
    src = body.get("source_path")
    if isinstance(up, Upload):
        if up.size > MAX_UPLOAD:
            raise ApiError(413, f"the file is over {MAX_UPLOAD // (1024 * 1024)} MB")
        res = K.attach_track(ep, up.path, up.filename or "")
    elif up is not None:
        raise ApiError(400, "file must be sent as multipart/form-data")
    elif isinstance(src, str) and src.strip():
        res = K.attach_track(ep, src.strip())
    elif src is not None:
        raise ApiError(400, "source_path must be the recording's absolute path on this "
                            "machine (or upload it as multipart `file`)")
    elif "track" in body and body.get("track") is None:
        res = K.clear_track(ep)
    else:
        raise ApiError(400, "send source_path (or a multipart `file`) to attach a "
                            "recording, or track: null to clear it")
    build = E.build_episode(ep)
    episode_event(ctx, ep)
    return 200, {"track": E.track_info(ep, pass_), "hash": res["hash"], "build": build,
                 "path": res["path"], "copied": res["copied"],
                 "reformatted": res["reformatted"]}


@handler
def post_audio_import(ctx: Context, body):
    """A media file into <ep>/audio/, for a cut entry's `audio.path`
    (track.import_audio): `source_path` (a file on this machine) or `file`
    (multipart, as /refs/import and /track). The answer's `path` is relative
    to the episode and goes straight into PUT /seriesmith/cut.

    It is only a file in the episode: it does not become the episode's
    dialogue recording and it is not a ref candidate, so nothing is rebuilt
    and no event is sent."""
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep"))
    up = body.get("file")
    src = body.get("source_path")
    if isinstance(up, Upload):
        if up.size > MAX_UPLOAD:
            raise ApiError(413, f"the file is over {MAX_UPLOAD // (1024 * 1024)} MB")
        res = K.import_audio(ep, up.path, up.filename or "")
    elif up is not None:
        raise ApiError(400, "file must be sent as multipart/form-data")
    elif isinstance(src, str) and src.strip():
        res = K.import_audio(ep, src.strip())
    else:
        raise ApiError(400, "source_path must be the file's absolute path on this "
                            "machine (or upload it as multipart `file`)")
    return 200, res


@handler
def post_align(ctx: Context, body):
    """Run align on the episode (a subprocess), sending `seriesmith.align` as it
    goes. 409 with `missing` when a dependency isn't installed; `dry_run`
    writes nothing."""
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep"))
    pass_ = check_pass(body.get("pass"))
    track = body.get("track")
    if track is not None and (not isinstance(track, str) or not track.strip()):
        raise ApiError(400, "track must be the recording's path (relative to the episode)")
    if isinstance(track, str):
        track = ep_file(ctx, ep, track.strip(), escape_status=400)[0]
    model = body.get("model")
    if model is not None and (not isinstance(model, str) or not model.strip()):
        raise ApiError(400, "model must be a Whisper model name, e.g. medium.en")
    snap = body.get("snap", True)
    dry = body.get("dry_run", False)
    for name, v in (("snap", snap), ("dry_run", dry)):
        if not isinstance(v, bool):
            raise ApiError(400, f"{name} must be true or false")

    K.check_align(ep, track)
    params = {"ep": ep, "pass": pass_, "track": track, "model": (model or "").strip() or None,
              "snap": snap, "dry_run": dry}
    with _LOCAL_GUARD:
        live = _live(ctx, "align", ep)
        if live is not None:
            raise ApiError(409, "align is already running for this episode; wait for it to "
                                "finish (or cancel it in Jobs)", job=dict(live.result))
        qjob = _start_local(ctx, "align", params)
    if ctx.runner is not None:
        return 200, {"job": dict(qjob.result)}
    run = qjob.result
    if run["state"] == "failed":
        raise ApiError(run.get("status") or 500, run["error"], log=run.get("log", ""))
    return 200, run["result"]


def _align_task(ctx: Context, params: dict):
    """align on the episode (a subprocess), sending `seriesmith.align` as it
    goes and once more as it ends, with the answer (`result`) or why not."""
    ep, pass_, dry = params["ep"], params["pass"], params["dry_run"]
    run = {"ep": ep, "state": "running", "dry_run": dry, "stage": "waiting", "pct": 0,
           "text": "", "result": None, "error": "", "started": T.now(), "finished": None}
    title = f"{os.path.basename(os.path.normpath(ep))} align" + (" (dry run)" if dry else "")

    def work(qjob, report, stop) -> str:
        run = qjob.result

        def tell(**more):
            ctx.emit("seriesmith.align", {"ep": ep, "stage": run["stage"], "pct": run["pct"],
                                          "text": run["text"], "job": qjob.id, **more})

        def progress(ev):
            run.update(stage=ev["stage"], pct=ev["pct"], text=ev["text"])
            if isinstance(ev["pct"], (int, float)):
                report(progress=ev["pct"] / 100)
            tell()

        run.update(stage="start", text="starting (dry run)" if dry else "starting")
        tell()
        try:
            res = K.align(ep, track=params["track"], model=params["model"], snap=params["snap"],
                          dry_run=dry, progress=progress, check_deps=False, stop=stop)
        except Exception as e:                           # noqa: BLE001  the job fails
            why = "canceled" if qjob.cancel_asked else str(e)
            run.update(state="failed", error=why, finished=T.now(),
                       status=getattr(e, "status", 500), log=getattr(e, "data", {}).get("log", ""))
            qjob.error = why
            tell(state="failed", error=why)
            return "failed"
        build = None if dry else E.build_episode(ep)
        if not dry:
            episode_event(ctx, ep)
        answer = {"ok": bool(res.get("ok")), "dry_run": dry, "report": res.get("report", ""),
                  "report_path": res.get("report_path"), "changes": res.get("changes", []),
                  "notes": res.get("notes", []), "recording": res.get("recording"),
                  "duration": res.get("duration"), "words": res.get("words"),
                  "script_hash": res.get("script_hash"), "series_hash": res.get("series_hash"),
                  "track": E.track_info(ep, pass_), "build": build, "log": res.get("log", "")}
        run.update(state="done", stage="done", pct=100, result=answer, finished=T.now())
        tell(state="done", result=answer)
        return "succeeded"

    return title, {"ep": ep, "pass": pass_, "dry_run": dry}, run, work


@handler
def get_align_job(ctx: Context, query: dict):
    """The episode's align (waiting, running, or the last one this server
    ran, with its answer as `result`); null when there is none."""
    ep = check_ep(ctx, query.get("ep"))
    jobs = _local_jobs(ctx, "align", ep)
    return 200, {"job": dict(jobs[0].result) if jobs and jobs[0].result else None}


LOCAL = {"master": _master_task, "align": _align_task}


# ---------------------------------------------------------------------------
# issues: a pass's notepad (P10)
# ---------------------------------------------------------------------------

@handler
def get_issues(ctx: Context, query: dict):
    """The issues noted for a pass (issues.list_issues), each with
    `addressed`: its shot has been rebuilt or rendered again since."""
    ep = check_ep(ctx, query.get("ep"))
    pass_ = query.get("pass")
    return 200, {"issues": IS.list_issues(ep, check_pass(pass_) if pass_ else None)}


@handler
def post_issues(ctx: Context, body):
    """Note what is wrong with a shot as it was rendered. Body
    `{ep, pass, shot, note, take?}`; the answer is the issue, snapshotted. 404
    for a shot that isn't in the pass, 400 for a note that says nothing."""
    body = body_dict(body)
    ep = check_ep(ctx, body.get("ep"))
    item = IS.add(ep, check_pass(body.get("pass")), check_shot(body.get("shot")),
                  body.get("note"), check_take(body.get("take"), nullable=True))
    ctx.emit("seriesmith.issues", {"ep": ep, "pass": item["pass"], "shot": item["shot"],
                               "id": item["id"]})
    return 200, item


@handler
def delete_issues(ctx: Context, query: dict):
    """Drop issues: `id` (one, repeatable as a comma-separated list), or
    `clear=1` for a whole pass, or `clear=1&addressed=1` for only the ones whose
    shot has moved on. Answers what is left."""
    ep = check_ep(ctx, query.get("ep"))
    pass_ = check_pass(query["pass"]) if query.get("pass") else None
    ids = [x for x in str(query.get("id") or "").split(",") if x]
    if ids:
        gone = IS.resolve(ep, ids)
    elif _flag(query.get("clear")):
        gone = IS.clear(ep, pass_, _flag(query.get("addressed")))
    else:
        raise ApiError(400, "give an `id` to resolve, or clear=1 to empty the pass")
    ctx.emit("seriesmith.issues", {"ep": ep, "pass": pass_, "removed": gone})
    return 200, {"removed": gone, "issues": IS.list_issues(ep, pass_)}


@handler
def get_issues_export(ctx: Context, query: dict):
    """One document to hand to an assistant: `format=md` (default) or `json`.
    Generated from the file every time, one way -- nothing parses it back."""
    ep = check_ep(ctx, query.get("ep"))
    pass_ = check_pass(query["pass"]) if query.get("pass") else None
    fmt = (query.get("format") or "md").lower()
    if fmt not in ("md", "markdown", "json"):
        raise ApiError(400, "format must be 'md' or 'json'")
    everything = _flag(query.get("addressed"))
    if fmt == "json":
        return 200, IS.export_json(ep, pass_, everything)
    return 200, {"format": "md", "text": IS.export_markdown(ep, pass_, everything)}

# (method, path, handler, what it takes: "query", "body" (JSON) or "form" (JSON, or
# multipart/form-data whose file field arrives as an Upload))
# how a route answers, read by server/views.make_view: these three stream a file
# (`reply`), and thumbnails (CPU: shrinking pictures) have threads of their own
# (`pool`), so a Refs tab asking for hundreds never holds up the other requests
for _fn in (get_file, get_thumb, get_preset_image):
    _fn.reply = "file"
get_thumb.pool = "thumb"

ROUTES = [
    ("GET", "/seriesmith/config", get_config, "query"),
    ("PUT", "/seriesmith/config", put_config, "body"),
    ("GET", "/seriesmith/episodes", get_episodes, "query"),
    ("GET", "/seriesmith/browse", get_browse, "query"),
    ("GET", "/seriesmith/episode", get_episode, "query"),
    ("GET", "/seriesmith/shot", get_shot, "query"),
    ("POST", "/seriesmith/build", post_build, "body"),
    ("POST", "/seriesmith/episode/new", post_episode_new, "body"),
    ("GET", "/seriesmith/episode/new", get_episode_template, "query"),
    ("POST", "/seriesmith/clips/ensure", post_clips_ensure, "body"),
    ("POST", "/seriesmith/clips/new", post_clips_new, "body"),
    ("POST", "/seriesmith/clip/queue", post_clip_queue, "body"),
    ("POST", "/seriesmith/refs/from-frame", post_refs_from_frame, "body"),
    ("POST", "/seriesmith/refs/video", post_refs_video, "form"),
    ("GET", "/seriesmith/drafts", get_drafts, "query"),
    ("GET", "/seriesmith/refs/videos", get_refs_videos, "query"),
    ("POST", "/seriesmith/import", post_import, "body"),
    ("GET", "/seriesmith/issues", get_issues, "query"),
    ("POST", "/seriesmith/issues", post_issues, "body"),
    ("DELETE", "/seriesmith/issues", delete_issues, "query"),
    ("GET", "/seriesmith/issues/export", get_issues_export, "query"),
    ("GET", "/seriesmith/file", get_file, "query"),
    ("GET", "/seriesmith/thumb", get_thumb, "query"),
    ("GET", "/seriesmith/presets", get_presets, "query"),
    ("GET", "/seriesmith/presets/image", get_preset_image, "query"),
    ("POST", "/seriesmith/presets/own", post_preset_own, "body"),
    ("POST", "/seriesmith/presets/own/delete", post_preset_own_delete, "body"),
    ("POST", "/seriesmith/presets/own/picture", post_preset_own_picture, "form"),
    ("POST", "/seriesmith/presets/own/render", post_preset_own_render, "body"),
    ("POST", "/seriesmith/render", post_render, "body"),
    ("POST", "/seriesmith/cancel", post_cancel, "body"),
    ("POST", "/seriesmith/discard", post_discard, "body"),
    ("POST", "/seriesmith/upscale", post_upscale, "body"),
    ("GET", "/seriesmith/upscale/options", get_upscale_options, "query"),
    ("PUT", "/seriesmith/upscale/recipe", put_upscale_recipe, "body"),
    ("PUT", "/seriesmith/upscale/keep", put_upscale_keep, "body"),
    ("POST", "/seriesmith/master", post_master, "body"),
    ("GET", "/seriesmith/master/job", get_master_job, "query"),
    ("DELETE", "/seriesmith/upscale", delete_upscale, "query"),
    ("POST", "/seriesmith/post", queue_post, "body"),
    ("GET", "/seriesmith/post/options", get_post_options, "query"),
    ("DELETE", "/seriesmith/post", delete_post, "query"),
    ("PUT", "/seriesmith/pick", put_pick, "body"),
    ("PUT", "/seriesmith/cut", put_cut, "body"),
    ("POST", "/seriesmith/cut/reset", post_cut_reset, "body"),
    ("POST", "/seriesmith/cut/copy", post_cut_copy, "body"),
    ("GET", "/seriesmith/peaks", get_peaks, "query"),
    ("PUT", "/seriesmith/override", put_override, "body"),
    ("DELETE", "/seriesmith/override", delete_override, "query"),
    ("PUT", "/seriesmith/episode-target", put_episode_target, "body"),
    ("POST", "/seriesmith/assemble", post_assemble, "body"),
    ("GET", "/seriesmith/targets", get_targets, "query"),
    ("GET", "/seriesmith/models", get_models, "query"),
    ("GET", "/seriesmith/workflows", get_workflows, "query"),
    ("POST", "/seriesmith/targets/inspect", post_targets_inspect, "body"),
    ("PUT", "/seriesmith/targets/custom", put_targets_custom, "body"),
    ("POST", "/seriesmith/targets/router-inspect", post_targets_router_inspect, "body"),
    ("POST", "/seriesmith/targets/router-dryrun", post_targets_router_dryrun, "body"),
    ("GET", "/seriesmith/router/models", get_router_models, "query"),
    ("PUT", "/seriesmith/targets/limits", put_targets_limits, "body"),
    ("DELETE", "/seriesmith/targets/custom", delete_targets_custom, "query"),
    ("POST", "/seriesmith/workflow/install", post_workflow_install, "body"),
    ("DELETE", "/seriesmith/workflow/install", delete_workflow_install, "query"),
    ("GET", "/seriesmith/refs", get_refs, "query"),
    ("GET", "/seriesmith/refs/owner-takes", get_refs_owner_takes, "query"),
    ("POST", "/seriesmith/refs/generate", post_refs_generate, "body"),
    ("POST", "/seriesmith/refs/tour", post_refs_tour, "body"),
    ("POST", "/seriesmith/refs/copy-take", post_refs_copy_take, "body"),
    ("POST", "/seriesmith/refs/relight", post_refs_relight, "body"),
    ("POST", "/seriesmith/refs/tour-frame", post_refs_tour_frame, "body"),
    ("PUT", "/seriesmith/refs/pick", put_refs_pick, "body"),
    ("DELETE", "/seriesmith/refs/pick", delete_refs_pick, "query"),
    ("PUT", "/seriesmith/refs/defaults", put_refs_defaults, "body"),
    ("POST", "/seriesmith/refs/import", post_refs_import, "form"),
    ("POST", "/seriesmith/refs/match", post_refs_match, "body"),
    ("POST", "/seriesmith/refs/discard", post_refs_discard, "body"),
    ("POST", "/seriesmith/refs/generate-missing", post_refs_generate_missing, "body"),
    ("POST", "/seriesmith/refs/keyframe", post_refs_keyframe, "body"),
    ("POST", "/seriesmith/refs/voice-from-take", post_refs_voice_from_take, "body"),
    ("PUT", "/seriesmith/refs/override", put_refs_override, "body"),
    ("DELETE", "/seriesmith/refs/override", delete_refs_override, "query"),
    ("GET", "/seriesmith/source", get_source, "query"),
    ("POST", "/seriesmith/source/check", post_source_check, "body"),
    ("PUT", "/seriesmith/source", put_source, "body"),
    ("POST", "/seriesmith/shot/preview", post_shot_preview, "body"),
    ("GET", "/seriesmith/promote", get_promote, "query"),
    ("POST", "/seriesmith/promote", post_promote, "body"),
    ("GET", "/seriesmith/align/ready", get_align_ready, "query"),
    ("POST", "/seriesmith/track", post_track, "form"),
    ("POST", "/seriesmith/audio/import", post_audio_import, "form"),
    ("POST", "/seriesmith/align", post_align, "body"),
    ("GET", "/seriesmith/align/job", get_align_job, "query"),
]
