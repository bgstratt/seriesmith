"""
plates.py — a crop's plate made from its master's (docs/PLATE_VARIANTS.md).

A crop is a location of its own with `of`, `crop` (which part: core/series_config.CROPS) and
`zoom` (how much closer). Its picture is its master's plate cut to that part and enlarged back
to the plate's size, with no model. A record beside it (`<plate>.crop.json`) says what it was
made from:

    {"of", "crop", "zoom", "master_sha1", "sha1"}

so it's made again when the master's plate, the crop or the zoom changes, and a picture that
isn't the one made here (its sha1 isn't the record's, or there's no record) is yours: kept,
never replaced.

    make_crops(ep, only=None) -> [{"id", "status", "path", "why"?}]
        status: made | current | yours | waiting (the master has no plate yet)

Run before a render or a ref generation needs a plate, and at the end of a build. Pillow.
"""
from __future__ import annotations

import io
import os

from seriesmith.core import fileio as F
from seriesmith.core.series_config import ZOOM, crop_box


def record_path(plate: str) -> str:
    return os.path.splitext(plate)[0] + ".crop.json"


def _crop(master: str, where: str, zoom: float) -> bytes:
    from PIL import Image
    with Image.open(master) as im:
        im.load()
        size = im.size
        part = im.crop(crop_box(size[0], size[1], where, zoom)).resize(size, Image.LANCZOS)
    buf = io.BytesIO()
    part.save(buf, format="PNG")
    return buf.getvalue()


def make_crops(ep: str, only: list[str] | None = None) -> list[dict]:
    """Each crop's plate, made when it's missing or out of date (see the module). Never raises
    for one crop: its entry says why."""
    from seriesmith import refs as R
    s = R.load_series(ep)
    locs = s.series_cfg.get("locations") or {}
    out = []
    for lid, e in locs.items():
        if e.get("crop") is None or (only and lid not in only):
            continue
        master = locs.get(e["of"]) or {}
        if not e.get("plate") or not master.get("plate"):
            out.append({"id": lid, "status": "waiting", "path": None,
                        "why": f"'{e['of']}' has no plate yet"})
            continue
        path = R.ref_file(s.home, e["plate"])
        src = R.ref_file(s.home, master["plate"])
        item = {"id": lid, "path": path}
        if not os.path.isfile(src):
            out.append(dict(item, status="waiting", why=f"'{e['of']}' has no plate yet"))
            continue
        want = {"of": e["of"], "crop": e["crop"], "zoom": float(e.get("zoom") or ZOOM),
                "master_sha1": F.file_digest(src)}
        rec = F.read_json_or(record_path(path), None, want=dict)
        if os.path.isfile(path):
            if rec is None or rec.get("sha1") != F.file_digest(path):
                out.append(dict(item, status="yours"))      # not the picture made here: kept
                continue
            if all(rec.get(k) == v for k, v in want.items()):
                out.append(dict(item, status="current"))
                continue
        try:
            data = _crop(src, e["crop"], want["zoom"])
        except (OSError, ValueError) as err:
            out.append(dict(item, status="waiting", why=f"the master's plate can't be read: {err}"))
            continue
        F.write_bytes(path, data)
        F.write_json(record_path(path), dict(want, sha1=F.file_digest(path)))
        out.append(dict(item, status="made"))
    return out


def ensure(ep: str) -> list[dict]:
    """make_crops, never raising (a render or a build goes on without it): [] when the episode's
    series config can't be read."""
    try:
        return make_crops(ep)
    except (OSError, ValueError, FileNotFoundError):
        return []


__all__ = ["ensure", "make_crops", "record_path"]
