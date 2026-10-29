#!/usr/bin/env python3
"""
mcp.py — `seriesmith mcp`: the editor's API as an MCP server, for an LLM
client (Claude Code or Desktop, Cursor, a local model in an MCP client) to
make and drive episodes with (docs/PLAN.md, "An MCP server").

    seriesmith mcp [--url http://127.0.0.1:8190] [--read-only]
    python <repo>/seriesmith/mcp.py [...]      (the same, with any Python 3.10+)

The client starts it and talks over stdio: JSON-RPC 2.0, one message per
line (MCP's stdio transport), stdout for the protocol only, stderr for
anything else. Each tool is one route of a running `seriesmith serve` (or a
ComfyUI with seriesmith, `--url http://127.0.0.1:8188`), so every write goes
through the routes' own checks, an open editor sees it live, and there is
one queue. No LLM here and no key: the client brings the model.

`--read-only` leaves out every tool that writes a file or queues a job.
The script format (prompts/SKILL.md) is a resource, for a client without
the script-writing skill.

Stdlib only (urllib, json): nothing to install beside seriesmith.
"""
from __future__ import annotations

import os
import sys

if not __package__:
    # run as a file (`python <repo>/seriesmith/mcp.py`: any Python 3.10+, nothing
    # installed, as a ComfyUI-Manager install has no .venv): the repo, not this
    # folder, on the path -- this folder's queue.py would shadow the stdlib's. An
    # embedded Python (ComfyUI portable's ._pth) may not have put this folder first,
    # so it is taken out wherever it is rather than entry 0 replaced.
    _here = os.path.normcase(os.path.dirname(os.path.abspath(__file__)))
    sys.path[:] = [p for p in sys.path if os.path.normcase(os.path.abspath(p or os.curdir)) != _here]
    sys.path.insert(0, os.path.dirname(_here))

import argparse
import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Callable

from seriesmith import __version__

DEFAULT_URL = "http://127.0.0.1:8190"
# the newest first; a client asking for another gets the newest
PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
TIMEOUT = 900                     # a build or an assemble can take minutes
WAIT_POLL = 5.0
WAIT_DEFAULT = 300
WAIT_MAX = 1800
FORMAT_URI = "seriesmith://script-format"
FORMAT_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "prompts", "SKILL.md")

INSTRUCTIONS = """\
seriesmith turns a series config (series.json) and episode scripts (epNN.md) into
rendered episodes. Paths are absolute folders on the machine seriesmith runs on.

A new show: write series.json and ep01.md in seriesmith's script format (the
seriesmith://script-format resource, or the seriesmith-episode-script skill), check them
with check_pair until it answers ok, then new_episode (or import_series for several
scripts) in a folder list_episodes' roots allow, then build.
An existing episode: read_source, edit, check_source, save_source (with the hash
read_source gave; it rebuilds).
Then: generate_missing_refs (the pictures), wait_for_jobs, list_refs / view_picture /
pick_ref; render, wait_for_jobs, episode_status / view_picture / pick_take; edit_cut
(trims, order, out); assemble. A shot rendered differently without touching the script:
set_override, then promote_plan / promote to write it into the script.
Finishing the final pass: upscale_options, upscale, post; master_plan, master (queue,
then assemble), master_job.
Tools whose description starts QUEUES (generate_*, render, upscale, post, master) use
the GPU or cost Comfy credits: say what will run and ask before calling them."""


class ToolError(Exception):
    """A tool's failure, said to the model (the call's isError); `status` is
    the server's HTTP status when it answered."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


@dataclass
class Tool:
    name: str
    description: str
    params: dict                                    # JSON-schema properties
    required: tuple = ()
    run: Callable | None = None                     # (client, args) -> result
    writes: bool = False                            # left out by --read-only
    queues: bool = False                            # GPU time or credits
    extra: dict = field(default_factory=dict)       # more of the input schema

    def listing(self) -> dict:
        schema = {"type": "object", "properties": self.params, **self.extra}
        if self.required:
            schema["required"] = list(self.required)
        return {"name": self.name, "description": self.description, "inputSchema": schema,
                "annotations": {"readOnlyHint": not self.writes}}


# ---------------------------------------------------------------------------
# the server's API
# ---------------------------------------------------------------------------

class Client:
    """The routes of one seriesmith server."""

    def __init__(self, url: str):
        self.url = url.rstrip("/")

    def call(self, method: str, path: str, query: dict | None = None,
             body: dict | None = None, raw: bool = False):
        q = {k: v for k, v in (query or {}).items() if v is not None}
        url = self.url + path + ("?" + urllib.parse.urlencode(q) if q else "")
        data = None if body is None else json.dumps(
            {k: v for k, v in body.items() if v is not None}).encode("utf-8")
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json"} if data else {})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                payload = r.read()
                if raw:
                    return payload, r.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", "replace")
            try:
                err = json.loads(text)
            except ValueError:
                err = None
            if isinstance(err, dict) and err.get("error"):
                detail = {k: v for k, v in err.items() if k not in ("error", "text")}
                raise ToolError(f"HTTP {e.code}: {err['error']}"
                                + (f" {json.dumps(detail)}" if detail else ""), e.code) from None
            if e.code == 404:
                raise ToolError(f"{path} isn't there (HTTP 404): is the server older than "
                                "this seriesmith? Restart it.", e.code) from None
            raise ToolError(f"HTTP {e.code} from {path}: {text[:500]}", e.code) from None
        except (urllib.error.URLError, OSError) as e:
            raise ToolError(f"nothing answers at {self.url} ({e}): start the editor's server "
                            "(seriesmith serve, or ComfyUI with seriesmith) or pass --url") from None
        return json.loads(payload) if payload else None

    def get(self, path, **query):
        return self.call("GET", path, query=query)

    def post(self, path, body):
        return self.call("POST", path, body=body)

    def put(self, path, body):
        return self.call("PUT", path, body=body)


# ---------------------------------------------------------------------------
# the tools
# ---------------------------------------------------------------------------

def _s(description: str, **more) -> dict:
    return {"type": "string", "description": description, **more}


EP = _s("the episode's folder, absolute (as list_episodes gives it)")
PASS = _s("proxy (small, fast drafts) or final; proxy when left out", enum=["proxy", "final"])
FILE = _s("script (epNN.md) or series (series.json)", enum=["script", "series"])
SHOT = _s("a shot id, e.g. sh020")
REF = _s("a ref id as list_refs gives it, e.g. subject:dean")
VIEW = _s("a character's view, e.g. 01_threequarter (characters only)")
TAKE = {"type": "integer", "description": "a take number"}
BACKEND = _s("optional: where the jobs run (local, cloud, router, deployment:<id>); "
             "else each model's own, as the series config says")


def _body(*names):
    """A tool's arguments as the route's body, by the same names."""
    return lambda a: {n: a.get(n) for n in names}


def route(method: str, path: str, *names, query: bool = False,
          shape: Callable | None = None) -> Callable:
    def run(c: Client, a: dict):
        args = _body(*names)(a)
        res = c.call(method, path, query=args) if query else c.call(method, path, body=args)
        return shape(res) if shape else res
    return run


def _pick(d: dict, *keys) -> dict:
    return {k: d[k] for k in keys if k in d}


def episode_brief(res: dict) -> dict:
    """GET /seriesmith/episode trimmed to what a model acts on."""
    shots = []
    for s in res.get("shots", []):
        cut = s.get("cut") or {}
        shots.append(dict(
            _pick(s, "shot", "sequence", "seconds", "target", "subjects", "action",
                  "missing_refs", "retarget_error"),
            cut=_pick(cut, "take", "usable", "picked", "out", "flag"),
            takes=[dict(_pick(t, "take", "status", "stale", "frames", "target", "note",
                              "save_notes"),
                        **({"thumb": t["thumb"]} if t.get("thumb") else {}),
                        **({"strip": t["strip"]} if t.get("strip") else {}))
                   for t in s.get("takes", [])]))
    return dict(_pick(res, "episode", "title", "pass", "fps", "width", "height", "target"),
                shots=shots)


def targets_brief(res: dict) -> dict:
    return {"default": res.get("default"),
            "targets": [_pick(t, "id", "kind", "label", "short", "default", "draft", "custom",
                              "readiness", "limits", "capabilities")
                        for t in res.get("targets", [])]}


def jobs_brief(res: dict, ep: str | None = None) -> dict:
    jobs = [j for j in res.get("jobs", [])
            if not ep or os.path.normcase((j.get("info") or {}).get("ep") or "")
            == os.path.normcase(ep)]
    live = [j for j in jobs if j.get("status") in ("queued", "running")]
    done = [j for j in jobs if j.get("status") not in ("queued", "running")][:20]
    keep = ("id", "kind", "lane", "title", "status", "progress", "info", "error", "after")
    return {"running_or_queued": [_pick(j, *keep) for j in live],
            "finished_recently": [_pick(j, *keep) for j in done],
            "paid": res.get("paid")}


def settle_refs(c: Client, brief: dict, ep: str | None) -> None:
    """Once ref jobs have finished, have their episodes' refs swept and
    auto-picked (GET /seriesmith/refs?fresh=1), as the editor's reload on
    their events does, so a render that follows finds them."""
    eps = {ep} if ep else set()
    eps |= {(j.get("info") or {}).get("ep") for j in brief["finished_recently"]
            if j.get("kind") == "ref"}
    for e in sorted(x for x in eps if x):
        try:
            c.get("/seriesmith/refs", ep=e, fresh="1")
        except ToolError:
            pass


def wait_for_jobs(c: Client, a: dict) -> dict:
    """Poll GET /seriesmith/jobs until nothing (of `ep`'s) is queued or
    running, or `timeout` seconds pass."""
    limit = min(float(a.get("timeout") or WAIT_DEFAULT), WAIT_MAX)
    end = time.monotonic() + limit
    while True:
        brief = jobs_brief(c.get("/seriesmith/jobs"), a.get("ep"))
        if not brief["running_or_queued"]:
            settle_refs(c, brief, a.get("ep"))
            return dict(brief, done=True)
        if time.monotonic() >= end:
            return dict(brief, done=False,
                        note=f"still running after {limit:.0f} s: call wait_for_jobs again")
        time.sleep(WAIT_POLL)


def view_picture(c: Client, a: dict) -> dict:
    """A picture of the episode's (a ref candidate, a take's thumb or strip)
    as an image the model can see."""
    data, ctype = c.call("GET", "/seriesmith/thumb", raw=True,
                         query={"ep": a.get("ep"), "path": a.get("path"),
                                "w": int(a.get("width") or 768)})
    return {"_image": base64.b64encode(data).decode("ascii"),
            "_mime": ctype.split(";")[0] or "image/jpeg"}


def passthrough(method: str, path: str) -> Callable:
    """A route whose body is every argument given: one with many optional
    fields (docs/API.md), of which the schema spells out the common ones."""
    return lambda c, a: c.call(method, path, body=dict(a))


CUT_CHANGES = ("take", "trim_in", "trim_out", "locked", "note", "out", "flag", "audio")


def edit_cut(c: Client, a: dict) -> dict:
    """PUT /seriesmith/cut replaces the pass's whole list: read it
    (cut.json, as the editor does), change only the shots named, reorder if
    asked, and write it all back, so nothing else in the cut is lost."""
    ep, pass_ = a["ep"], a.get("pass") or "proxy"
    try:
        cut = c.call("GET", "/seriesmith/file", query={"ep": ep, "path": "cut.json"})
    except ToolError as e:
        if e.status != 404:                         # 404: no cut.json yet
            raise
        cut = None
    entries = (cut or {}).get(pass_) or []
    if not entries:                                 # no cut yet: the script's order
        status = c.get("/seriesmith/episode", ep=ep, **{"pass": pass_})
        entries = [{"shot": s["shot"]} for s in status.get("shots", [])
                   if not s.get("orphan")]
    by_shot = {e["shot"]: dict(e) for e in entries}
    for ch in a.get("changes") or []:
        shot = ch.get("shot")
        if shot not in by_shot:
            raise ToolError(f"{shot!r} isn't in the {pass_} cut")
        unknown = set(ch) - {"shot", *CUT_CHANGES}
        if unknown:
            raise ToolError(f"a cut change has no {', '.join(sorted(unknown))}: "
                            f"one of {', '.join(CUT_CHANGES)}")
        by_shot[shot].update({k: v for k, v in ch.items() if k != "shot"})
    order = a.get("order")
    if order is not None:
        if sorted(order) != sorted(by_shot):
            missing, extra = set(by_shot) - set(order), set(order) - set(by_shot)
            raise ToolError("order must name every shot of the cut once"
                            + (f"; missing {', '.join(sorted(missing))}" if missing else "")
                            + (f"; not in it {', '.join(sorted(extra))}" if extra else ""))
    else:
        order = [e["shot"] for e in entries]
    return c.put("/seriesmith/cut", {"ep": ep, "pass": pass_,
                                     "entries": [by_shot[s] for s in order]})


def issues_md(res: dict) -> str:
    return res.get("text", "") if isinstance(res, dict) else str(res)


TOOLS: list[Tool] = [
    # reading
    Tool("list_episodes", "Every episode under the configured roots: folder (ep), series, "
         "title, whether each pass is built, shot count. Also the roots, where new shows "
         "can go.", {},
         run=lambda c, a: {"roots": c.get("/seriesmith/config").get("roots"),
                           "episodes": c.get("/seriesmith/episodes")}),
    Tool("read_source", "An episode's script or series config as text, with the hash "
         "save_source needs and (script) each shot's lines.", {"ep": EP, "file": FILE},
         ("ep", "file"), route("GET", "/seriesmith/source", "ep", "file", query=True)),
    Tool("check_pair", "Check a series config and a script that aren't on disk yet (a new "
         "show), together, writing nothing. Answers ok, errors and warnings with file and "
         "1-based line, and the script's shots. Without script, the series config alone.",
         {"series": _s("series.json's text"), "script": _s("the script's text (epNN.md)"),
          "parent": _s("optional: the folder the show will go in, so its own models count")},
         ("series",), route("POST", "/seriesmith/check", "series", "script", "parent")),
    Tool("check_source", "Check an edited script or series config of an existing episode "
         "against the other file on disk, writing nothing (errors and warnings with line "
         "numbers).", {"ep": EP, "file": FILE, "text": _s("the whole file's new text")},
         ("ep", "file", "text"), route("POST", "/seriesmith/source/check", "ep", "file", "text")),
    Tool("preview_shot", "What one shot of a script text would render, compiled in memory: "
         "the model, the prompt it is told, frames, size, and whether its dialogue fits "
         "(pacing: ok, tight, CRAMMED).",
         {"ep": EP, "text": _s("the whole script, with the shot as edited"), "shot": SHOT,
          "pass": PASS}, ("ep", "text", "shot"),
         route("POST", "/seriesmith/shot/preview", "ep", "text", "shot", "pass")),
    Tool("list_targets", "The models shots and pictures can render on, and whether each is "
         "ready on this machine (readiness), with their limits (durations, references).",
         {"ep": _s("optional: an episode, to add its show's own models"),
          "kind": _s("video, image or audio", enum=["video", "image", "audio"])}, (),
         lambda c, a: targets_brief(c.get("/seriesmith/targets", ep=a.get("ep"),
                                          kind=a.get("kind"), ready="1"))),
    Tool("episode_status", "An episode's shots in cut order: each shot's model, length, "
         "missing refs, the take the cut uses, and every take (status, why stale, thumb "
         "and strip paths for view_picture).", {"ep": EP, "pass": PASS}, ("ep",),
         route("GET", "/seriesmith/episode", "ep", "pass", query=True, shape=episode_brief)),
    Tool("get_shot", "One shot in full: its built entry and prompt, what a render would use "
         "now, and every take's record.", {"ep": EP, "shot": SHOT, "pass": PASS},
         ("ep", "shot"), route("GET", "/seriesmith/shot", "ep", "shot", "pass", query=True)),
    Tool("list_refs", "The episode's reference pictures (characters and their views, props, "
         "locations, keyframes, voices): which shots use each, whether it exists, its "
         "candidates (takes, with image paths for view_picture) and which is picked.",
         {"ep": EP}, ("ep",),
         lambda c, a: c.get("/seriesmith/refs", ep=a["ep"], fresh="1")),
    Tool("view_picture", "Look at a picture of the episode: a ref candidate's image, a "
         "take's thumb or strip (paths as list_refs and episode_status give them).",
         {"ep": EP, "path": _s("relative to the episode"),
          "width": {"type": "integer", "description": "pixels wide, 768 when left out"}},
         ("ep", "path"), view_picture),
    Tool("get_issues", "The notes made while watching a pass (what is wrong with which "
         "take), as markdown.", {"ep": EP, "pass": PASS}, ("ep",),
         lambda c, a: issues_md(c.call("GET", "/seriesmith/issues/export", query={
             "ep": a["ep"], "pass": a.get("pass"), "format": "md"}))),
    Tool("list_jobs", "seriesmith's queue: what is queued or running, what finished lately "
         "(and why one failed).", {"ep": _s("optional: only this episode's")}, (),
         lambda c, a: jobs_brief(c.get("/seriesmith/jobs"), a.get("ep"))),
    Tool("wait_for_jobs", "Wait until nothing (of one episode's) is queued or running, or "
         "timeout seconds pass; then the queue as list_jobs gives it, with done.",
         {"ep": _s("optional: only this episode's"),
          "timeout": {"type": "integer", "description": f"seconds, {WAIT_DEFAULT} when left "
                      f"out, at most {WAIT_MAX}"}}, (), wait_for_jobs),

    # writing
    Tool("save_source", "Save an episode's script or series config (the old one is kept in "
         "_history/) and rebuild. base_hash is read_source's hash; a 409 means the file "
         "changed since: read it again.",
         {"ep": EP, "file": FILE, "text": _s("the whole file's new text"),
          "base_hash": _s("read_source's hash"),
          "rebuild": {"type": "boolean", "description": "true when left out"}},
         ("ep", "file", "text", "base_hash"),
         lambda c, a: c.put("/seriesmith/source", dict(_body("ep", "file", "text",
                                                             "base_hash")(a),
                                                       rebuild=a.get("rebuild", True))),
         writes=True),
    Tool("new_episode", "Make an episode folder from a series config and a script (check "
         "them with check_pair first). Never overwrites: an existing folder is a 409. Answers "
         "its folder (ep) and the check. Not built yet: call build.",
         {"parent": _s("the folder the episodes live in, inside a root"),
          "name": _s("the episode's folder and script name, e.g. ep01"),
          "title": _s("the episode's title"),
          "show": _s("optional: a show folder to make inside parent"),
          "series": _s("series.json's text (else the newest episode's there is copied)"),
          "script": _s("the script's text")}, ("parent", "name"),
         route("POST", "/seriesmith/episode/new", "parent", "name", "title", "show",
               "series", "script"), writes=True),
    Tool("import_series", "Several scripts and a series config into episode folders at once "
         "(each script's header names its folder). Not built yet: call build on each.",
         {"parent": _s("a folder inside a root"),
          "show": _s("optional: the show folder to make or fill inside parent"),
          "series": _s("series.json's text, for every script without its own"),
          "scripts": {"type": "array", "items": {
              "type": "object", "required": ["name", "text"],
              "properties": {"name": _s("the file's name, e.g. ep02.md"),
                             "text": _s("the script"),
                             "series": _s("optional: this script's own series config")}}}},
         ("parent", "scripts"),
         route("POST", "/seriesmith/import", "parent", "show", "series", "scripts"),
         writes=True),
    Tool("build", "Build an episode (final and proxy passes) from its script and series "
         "config: what renders and refs read. A script error is ok: false with the message.",
         {"ep": EP}, ("ep",), route("POST", "/seriesmith/build", "ep"), writes=True),
    Tool("import_ref", "A picture already on this machine as a ref's new candidate (or audio, "
         "for a voice), picked if pick is true.",
         {"ep": EP, "ref": REF, "view": VIEW, "source_path": _s("the file's absolute path"),
          "pick": {"type": "boolean"}}, ("ep", "ref", "source_path"),
         route("POST", "/seriesmith/refs/import", "ep", "ref", "view", "source_path", "pick"),
         writes=True),
    Tool("pick_ref", "The candidate a ref uses (for a character, per view; the sheet is "
         "stitched when all four are picked).", {"ep": EP, "ref": REF, "view": VIEW,
                                                  "take": TAKE},
         ("ep", "ref", "take"), route("PUT", "/seriesmith/refs/pick", "ep", "ref", "view",
                                      "take"), writes=True),
    Tool("pick_take", "The take a shot's cut uses; take null goes back to the latest usable.",
         {"ep": EP, "shot": SHOT, "take": {"type": ["integer", "null"]}, "pass": PASS},
         ("ep", "shot", "take"),
         route("PUT", "/seriesmith/pick", "ep", "pass", "shot", "take"), writes=True),
    Tool("assemble", "Cut the pass's picked takes together into one video (can take "
         "minutes). partial: true leaves shots without a usable take out instead of failing.",
         {"ep": EP, "pass": PASS, "partial": {"type": "boolean"}}, ("ep",),
         route("POST", "/seriesmith/assemble", "ep", "pass", "partial"), writes=True),
    Tool("import_take", "A video on this machine as a shot's new take (an H.264 mp4 copied, "
         "anything else converted to one), picked if pick is true. It keeps its own length; "
         "it has no seed or prompt, so it is never stale and can't be re-rendered as such.",
         {"ep": EP, "shot": SHOT, "pass": PASS, "source_path": _s("the video's absolute path"),
          "pick": {"type": "boolean"}, "note": _s("optional")}, ("ep", "shot", "source_path"),
         route("POST", "/seriesmith/take/import", "ep", "pass", "shot", "source_path", "pick",
               "note"), writes=True),
    Tool("copy_take", "Another shot's take (from_shot, take; from_pass for the other pass) "
         "copied in as this shot's new take, picked if pick is true. To put a clip between "
         "two shots, add a shot to the script there first (read_source, save_source).",
         {"ep": EP, "shot": SHOT, "pass": PASS, "from_shot": SHOT, "take": TAKE,
          "from_pass": PASS, "pick": {"type": "boolean"}}, ("ep", "shot", "from_shot", "take"),
         route("POST", "/seriesmith/take/copy", "ep", "pass", "shot", "from_shot", "take",
               "from_pass", "pick"), writes=True),
    Tool("discard_take", "Move a take into renders/_trash/ (out of the lists; the file is "
         "kept there).", {"ep": EP, "shot": SHOT, "take": TAKE, "pass": PASS},
         ("ep", "shot", "take"),
         route("POST", "/seriesmith/discard", "ep", "shot", "take", "pass"), writes=True),

    # the cut
    Tool("edit_cut", "Change the cut: per shot its take, trims (trim_in / trim_out, frames "
         "at the episode's fps), locked, note, out (left out of the cut, kept in the script), "
         "flag (a bookmark), audio (sound from another take or a file: docs/API.md); and/or "
         "its order (every shot of the cut, once). Only what is named changes.",
         {"ep": EP, "pass": PASS,
          "changes": {"type": "array", "items": {
              "type": "object", "required": ["shot"],
              "properties": {"shot": SHOT, "take": TAKE,
                             "trim_in": {"type": "integer"}, "trim_out": {"type": "integer"},
                             "locked": {"type": "boolean"}, "note": _s("a note"),
                             "out": {"type": "boolean"}, "flag": {"type": "boolean"},
                             "audio": {"type": ["object", "null"]}}}},
          "order": {"type": "array", "items": SHOT,
                    "description": "every shot of the cut in its new order"}},
         ("ep",), edit_cut, writes=True),
    Tool("reset_cut", "Put the cut back: what order (script order; picks, locks and notes "
         "kept), trims (none), audio (each shot's own) or all.",
         {"ep": EP, "pass": PASS, "what": _s("order, trims, audio or all",
                                             enum=["order", "trims", "audio", "all"])},
         ("ep", "what"), route("POST", "/seriesmith/cut/reset", "ep", "pass", "what"),
         writes=True),

    # overrides: a shot's settings for its next render, outside the script
    Tool("set_override", "Change a shot's next render without editing the script "
         "(overrides.json): fields prompt, seed (digits, as a string), model, loras, steps, "
         "size (WxH), note; null clears one. prompt, model, loras, steps and size are per "
         "pass (both: true sets both). get_shot shows what a render would use now.",
         {"ep": EP, "shot": SHOT, "pass": PASS, "both": {"type": "boolean"},
          "fields": {"type": "object", "properties": {
              "prompt": {"type": ["string", "null"]}, "seed": {"type": ["string", "null"]},
              "model": {"type": ["string", "null"]}, "loras": {"type": ["array", "null"]},
              "steps": {"type": ["integer", "null"]}, "size": {"type": ["string", "null"]},
              "note": {"type": ["string", "null"]}}}},
         ("ep", "shot", "fields"),
         route("PUT", "/seriesmith/override", "ep", "shot", "pass", "both", "fields"),
         writes=True),
    Tool("clear_override", "Remove a shot's override: one pass's fields, or all of it "
         "without pass.", {"ep": EP, "shot": SHOT, "pass": PASS}, ("ep", "shot"),
         route("DELETE", "/seriesmith/override", "ep", "shot", "pass", query=True),
         writes=True),
    Tool("promote_plan", "Which overrides the script or series config can express: the "
         "items, the diffs they would make, what has to stay an override and why, and the "
         "hashes promote needs.", {"ep": EP, "shot": _s("optional: one shot's only")},
         ("ep",), route("GET", "/seriesmith/promote", "ep", "shot", query=True)),
    Tool("promote", "Move overrides into the script / series config (old files kept in "
         "_history/), drop them from overrides.json and rebuild. items: ids from "
         "promote_plan, or \"all\"; hashes: promote_plan's (a 409 means a file changed: plan "
         "again).",
         {"ep": EP, "items": {"type": ["array", "string"], "items": {"type": "string"}},
          "hashes": {"type": "object"}, "shot": _s("optional")}, ("ep", "items", "hashes"),
         route("POST", "/seriesmith/promote", "ep", "items", "hashes", "shot"), writes=True),

    # finishing: upscale, post, master
    Tool("upscale_options", "What upscaling can run on this machine: pixel models, which "
         "video models can re-sample (latent), SeedVR2, delivery sizes; with ep, the "
         "series' master recipe.", {"ep": _s("optional: an episode, for its recipe")}, (),
         route("GET", "/seriesmith/upscale/options", "ep", query=True)),
    Tool("post_options", "What post-processing can run here (enhance tiers and methods, "
         "motion blur), with ep the series' post recipe.",
         {"ep": _s("optional: an episode, for its recipe")}, (),
         route("GET", "/seriesmith/post/options", "ep", query=True)),
    Tool("master_plan", "What making the master would do now: per shot of the final cut, "
         "whether its upscale is fresh (ok, kept), still to make (upscale), queued or a gap, "
         "and whether the master can be assembled (ready). Writes nothing.",
         {"ep": EP, "conform": {"type": "boolean"}, "post": _s("off, present or recipe")},
         ("ep",), lambda c, a: c.post("/seriesmith/master", dict(_body("ep", "conform",
                                                                       "post")(a),
                                                                 action="plan"))),
    Tool("master_job", "The master being assembled for an episode, or the last one: state "
         "(running, done with output, failed with error) and progress.", {"ep": EP},
         ("ep",), route("GET", "/seriesmith/master/job", "ep", query=True)),
    Tool("upscale_keep", "Mark a take's finished upscale Keep (a whole-cut upscale and the "
         "master leave it as it is), or not.",
         {"ep": EP, "shot": SHOT, "take": TAKE, "keep": {"type": "boolean"}, "pass": PASS},
         ("ep", "shot", "take", "keep"),
         route("PUT", "/seriesmith/upscale/keep", "ep", "shot", "take", "keep", "pass"),
         writes=True),
    Tool("delete_upscale", "Remove a take's upscale.",
         {"ep": EP, "shot": SHOT, "take": TAKE, "pass": PASS}, ("ep", "shot", "take"),
         route("DELETE", "/seriesmith/upscale", "ep", "shot", "take", "pass", query=True),
         writes=True),
    Tool("delete_post", "Remove a take's post-process.",
         {"ep": EP, "shot": SHOT, "take": TAKE, "pass": PASS}, ("ep", "shot", "take"),
         route("DELETE", "/seriesmith/post", "ep", "shot", "take", "pass", query=True),
         writes=True),

    # queueing: the GPU or Comfy credits
    Tool("generate_missing_refs", "QUEUES JOBS (GPU or credits): one candidate for every ref "
         "picture the episode lacks, and its needed keyframes. dry_run: true lists what "
         "would run, queuing nothing: do that first and say what it will make.",
         {"ep": EP, "pass": PASS, "dry_run": {"type": "boolean"},
          "target": _s("optional: the image model, as list_targets gives it"),
          "backend": BACKEND}, ("ep",),
         route("POST", "/seriesmith/refs/generate-missing", "ep", "pass", "dry_run",
               "target", "backend"), writes=True, queues=True),
    Tool("generate_ref", "QUEUES A JOB (GPU or credits): new candidates for one ref (or one "
         "view of a character), optionally with another prompt.",
         {"ep": EP, "ref": REF, "view": VIEW,
          "count": {"type": "integer", "description": "1 when left out"},
          "prompt": _s("optional: instead of the built prompt"), "note": _s("optional"),
          "backend": BACKEND},
         ("ep", "ref"), route("POST", "/seriesmith/refs/generate", "ep", "ref", "view",
                              "count", "prompt", "note", "backend"), writes=True, queues=True),
    Tool("render", "QUEUES JOBS (GPU or credits): a take of each shot (every shot when shots "
         "is left out). Shots that have a usable take are skipped unless redo is true. "
         "Answers queued, skipped and errors per shot; wait_for_jobs, then episode_status.",
         {"ep": EP, "pass": PASS, "shots": {"type": "array", "items": SHOT},
          "redo": {"type": "boolean"}, "note": _s("optional: kept with the take"),
          "target": _s("optional: a one-off video model for this run"),
          "backend": BACKEND}, ("ep",),
         route("POST", "/seriesmith/render", "ep", "pass", "shots", "redo", "note", "target",
               "backend"),
         writes=True, queues=True),
    Tool("upscale", "QUEUES JOBS (GPU or credits): the final cut's takes upscaled (the "
         "whole cut when shots and takes are left out; fresh ones skipped unless redo). "
         "Common fields below; every other field of POST /seriesmith/upscale passes "
         "through (then_pixel_model, then_method, seedvr2_model, detail, encoder, ...). "
         "upscale_options says what can run.",
         {"ep": EP, "pass": _s("final when left out", enum=["proxy", "final"]),
          "shots": {"type": "array", "items": SHOT},
          "takes": {"type": "array", "items": {"type": "object", "properties": {
              "shot": SHOT, "take": TAKE}}},
          "redo": {"type": "boolean"}, "scale": {"type": "number"},
          "method": _s("latent (re-sample), pixel or seedvr2"),
          "pixel_model": _s("a file in models/upscale_models, or rtx_vsr"),
          "deliver": _s("1080p, 1440p, 4k or WxH"), "fit": _s("crop or pad"),
          "quality": _s("review or master")}, ("ep",),
         passthrough("POST", "/seriesmith/upscale"), writes=True, queues=True),
    Tool("post", "QUEUES JOBS (GPU or credits): post-process takes' fresh upscales "
         "(enhance, then motion blur): by the series' recipe (recipe: true, or neither "
         "enhance nor blur) or as given. Fresh ones with the same settings skipped unless "
         "redo.",
         {"ep": EP, "pass": PASS, "shots": {"type": "array", "items": SHOT},
          "takes": {"type": "array", "items": {"type": "object"}},
          "redo": {"type": "boolean"}, "recipe": {"type": "boolean"},
          "enhance": {"description": "a tier (draft, production, cinematic), a method "
                      "(pixel, seedvr2, supir), an object or none"},
          "blur": {"type": "number", "description": "motion blur, 0-1 of the frame interval"},
          "quality": _s("review or master")}, ("ep",),
         passthrough("POST", "/seriesmith/post"), writes=True, queues=True),
    Tool("master", "Make the master by the series' recipe. action queue QUEUES JOBS (GPU "
         "or credits: the upscales master_plan lists); assemble writes master/ (a job: "
         "follow it with master_job); prores makes the .mov of the master made. Run "
         "master_plan first and say what it will do.",
         {"ep": EP, "action": _s("queue, assemble or prores",
                                 enum=["queue", "assemble", "prores"]),
          "conform": {"type": "boolean"}, "allow_gaps": {"type": "boolean"},
          "prores": {"type": "boolean"}, "order": _s("cut or target"),
          "post": _s("off, present or recipe")}, ("ep", "action"),
         route("POST", "/seriesmith/master", "ep", "action", "conform", "allow_gaps",
               "prores", "order", "post"), writes=True, queues=True),
    Tool("cancel_job", "Cancel a queued or running job (its id from list_jobs).",
         {"id": _s("the job's id")}, ("id",),
         route("POST", "/seriesmith/jobs/cancel", "id"), writes=True),
]


def launch(port: int | None = None) -> dict:
    """How an LLM client starts this install's MCP server (GET /seriesmith/mcp,
    the Features window): {"command", "args", "url", "how"}. With a .venv's
    `seriesmith` launcher beside this Python, that; else this Python running
    this file (a ComfyUI-Manager install). `--url` when the server isn't the
    default one (ComfyUI's port, another `--port`)."""
    exe = os.path.join(os.path.dirname(sys.executable), "seriesmith.exe" if os.name == "nt" else "seriesmith")
    if os.path.isfile(exe):
        command, args, how = exe, ["mcp"], "seriesmith"
    else:
        command, args, how = sys.executable, [os.path.abspath(__file__)], "python"
    url = f"http://127.0.0.1:{port}" if port else DEFAULT_URL
    if url != DEFAULT_URL:
        args += ["--url", url]
    return {"command": command, "args": args, "url": url, "how": how}


def tools(read_only: bool) -> list[Tool]:
    return [t for t in TOOLS if not (read_only and t.writes)]


# ---------------------------------------------------------------------------
# the protocol
# ---------------------------------------------------------------------------

class Server:
    def __init__(self, client: Client, read_only: bool = False):
        self.client = client
        self.tools = {t.name: t for t in tools(read_only)}

    def handle(self, msg: dict) -> dict | None:
        """One JSON-RPC message in, its answer out (None for a notification)."""
        mid, method = msg.get("id"), msg.get("method")
        if mid is None:
            return None
        try:
            result = self.dispatch(method, msg.get("params") or {})
        except RpcError as e:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": e.code, "message": str(e)}}
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    def dispatch(self, method: str, params: dict):
        if method == "initialize":
            asked = params.get("protocolVersion")
            return {"protocolVersion": asked if asked in PROTOCOL_VERSIONS
                    else PROTOCOL_VERSIONS[0],
                    "capabilities": {"tools": {}, "resources": {}},
                    "serverInfo": {"name": "seriesmith", "version": __version__},
                    "instructions": INSTRUCTIONS}
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": [t.listing() for t in self.tools.values()]}
        if method == "tools/call":
            return self.call_tool(params.get("name"), params.get("arguments") or {})
        if method == "resources/list":
            return {"resources": [{"uri": FORMAT_URI, "name": "seriesmith script format",
                                   "description": "How to write series.json and epNN.md "
                                   "(the script-writing skill's text)",
                                   "mimeType": "text/markdown"}]
                    if os.path.isfile(FORMAT_FILE) else []}
        if method == "resources/read":
            if params.get("uri") != FORMAT_URI or not os.path.isfile(FORMAT_FILE):
                raise RpcError(-32002, f"no resource {params.get('uri')!r}")
            with open(FORMAT_FILE, encoding="utf-8") as fh:
                return {"contents": [{"uri": FORMAT_URI, "mimeType": "text/markdown",
                                      "text": fh.read()}]}
        if method == "resources/templates/list":
            return {"resourceTemplates": []}
        raise RpcError(-32601, f"no method {method!r}")

    def call_tool(self, name: str, args: dict) -> dict:
        tool = self.tools.get(name)
        if tool is None:
            raise RpcError(-32602, f"no tool {name!r}")
        missing = [k for k in tool.required if k not in args]
        if missing:
            return _error(f"{name} needs {', '.join(missing)}")
        try:
            res = tool.run(self.client, args)
        except ToolError as e:
            return _error(str(e))
        if isinstance(res, dict) and "_image" in res:
            return {"content": [{"type": "image", "data": res["_image"],
                                 "mimeType": res["_mime"]}], "isError": False}
        text = res if isinstance(res, str) else json.dumps(res, indent=1, ensure_ascii=False)
        return {"content": [{"type": "text", "text": text}], "isError": False}


class RpcError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def _error(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": True}


def serve(server: Server, inp, out) -> None:
    """Read messages from `inp` (bytes, one per line) and answer on `out`
    until it closes."""
    for line in inp:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            answer = {"jsonrpc": "2.0", "id": None,
                      "error": {"code": -32700, "message": "not JSON"}}
        else:
            if isinstance(msg, list):                  # a batch (2025-03-26)
                answer = [a for a in map(server.handle, msg) if a is not None] or None
            else:
                answer = server.handle(msg)
        if answer is not None:
            out.write(json.dumps(answer, ensure_ascii=False).encode("utf-8") + b"\n")
            out.flush()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="seriesmith mcp", description=(
        "The editor's API as an MCP server on stdio, for an LLM client to start. Talks to "
        "a running seriesmith serve (or ComfyUI with seriesmith)."))
    ap.add_argument("--url", default=os.environ.get("SERIESMITH_URL", DEFAULT_URL),
                    help=f"the server's address ({DEFAULT_URL}: seriesmith serve; "
                         "http://127.0.0.1:8188 for ComfyUI's)")
    ap.add_argument("--read-only", action="store_true",
                    help="leave out every tool that writes a file or queues a job")
    args = ap.parse_args(argv)
    print(f"seriesmith mcp: serving {args.url} on stdio"
          + (" (read-only)" if args.read_only else ""), file=sys.stderr)
    serve(Server(Client(args.url), args.read_only), sys.stdin.buffer, sys.stdout.buffer)
    return 0


if __name__ == "__main__":
    sys.exit(main())
