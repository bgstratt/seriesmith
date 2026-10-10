"""
Rendering in tests without a GPU: `seriesmith render` in-process on a fake
backend whose saver reports what SeriesmithSaveTake would (an empty mp4,
thumbnails, a latent and the record), as h3pipe's fake ComfyUI did.
"""
from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from seriesmith import jobs as J
from seriesmith import render
from seriesmith import shotnodes as SN
from seriesmith import takes as T
from seriesmith.backends.fake import FakeBackend

# a deployment: it runs the workflow targets, and render asks no real ComfyUI
# for model lists the way it does for `local`
DEPLOY = "deployment"


def saver_outputs(graph: dict, *, status: str = "ok", record: bool = True,
                  mp4: bytes = b"") -> dict:
    """What SeriesmithSaveTake reports for the take `graph` renders."""
    saver = J.node_of(graph, J.PORTABLE_SAVER)
    shot = None
    for v in graph.values():
        if v["class_type"] == J.PORTABLE_LOADER:
            shot = json.loads(v["inputs"]["shotlist"])["shots"][0]
    take = graph[saver]["inputs"]["take"]
    shot_id = shot["id"] if shot else graph[saver]["inputs"]["run"].split("_")[-3]
    stem = T.stem(shot_id, take)
    frames = int((shot or {}).get("length") or 73)
    items = [(f"{stem}.mp4", "video", mp4), (f"{stem}.jpg", "image", b"jpg"),
             (f"{stem}_strip.jpg", "image", b"strip"),
             (f"{stem}.latent.safetensors", "latent", b"latent")]
    if record:
        items.append((stem + SN.RECORD_SUFFIX, "file", json.dumps({
            "shot": shot_id, "take": take, "status": status,
            "finished": "2026-10-10T12:00:00-04:00", "frames": frames, "fps": 24.0,
            "mp4": f"{stem}.mp4", "thumb": f"{stem}.jpg", "strip": f"{stem}_strip.jpg",
            "latent": f"{stem}.latent.safetensors", "save_notes": f"{stem}: mp4 written",
            "loaded_refs": ["ada (character) ada.png [512x512, body of 4 panels]"]}).encode()))
    return {saver: items, "999": [("preview.png", "image", b"not the take's")]}


def render_fake(*args, backend: FakeBackend | None = None) -> tuple[int, str, FakeBackend]:
    """`seriesmith render *args` on a fake deployment backend (args name the
    episode and flags; `--backend deployment` is added). (exit code, what it
    printed, the backend)."""
    fb = backend or FakeBackend(DEPLOY, "deployment", outputs=saver_outputs)
    out = io.StringIO()
    with mock.patch.object(render, "available",
                           side_effect=lambda s=None: {f"deployment:{t}": fb for t in
                                                      _targets()} | {fb.name: fb}), \
            redirect_stdout(out), redirect_stderr(out):
        rc = render.main([*args, "--backend", "deployment"])
    return rc, out.getvalue(), fb


def _targets() -> list[str]:
    from seriesmith import targets as TG
    return [t.id for t in TG.list_targets("video")]
