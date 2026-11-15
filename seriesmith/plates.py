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
                out.append(dict(item, status="current", upscaled=rec.get("upscaled") or None))
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


# -- upscaled: the part through an upscale model instead of stretched --------------------------
#
# A crop is an enlargement, so its picture is soft. Upscaling it, queued from the crop as any
# variant's picture is: the part cut from the master's plate (no enlargement), through an
# upscale model on this machine's ComfyUI, scaled to the plate's size. The record says which
# model ("upscaled"); when the master's plate changes the crop is stretched again at once (a
# render never uses a crop of the old picture) and can be upscaled again. The master is never
# touched.

UPSCALERS = ("4x-UltraSharp.pth", "RealESRGAN_x4.pth", "RealESRGAN_x2.pth")   # preferred first


def pick_model(listed: list[str] | None, wanted: str | None = None) -> str:
    """The upscale model to use from those the backend lists: `wanted` when given (and listed,
    when the backend can say), else the first of UPSCALERS it has, else its first. ValueError
    when it has none."""
    if wanted:
        if listed is not None and wanted not in listed:
            raise ValueError(f"this ComfyUI has no upscale model {wanted!r}")
        return wanted
    if listed is None:
        return UPSCALERS[0]
    for m in UPSCALERS:
        if m in listed:
            return m
    if listed:
        return listed[0]
    raise ValueError("this ComfyUI has no upscale model (models/upscale_models): add one "
                     "(4x-UltraSharp or RealESRGAN) to upscale crops")


def crop_of(ep: str, cid: str) -> dict:
    """What upscaling crop `cid` works from: {"id", "path" (its picture), "master" (the master's
    plate), "want" (the record's keys), "size" (the plate's size)}. ValueError when `cid` isn't a
    crop or its master has no plate yet."""
    from PIL import Image

    from seriesmith import refs as R
    s = R.load_series(ep)
    locs = s.series_cfg.get("locations") or {}
    e = locs.get(cid)
    if not e or e.get("crop") is None:
        raise ValueError(f"{cid!r} isn't a crop (a location with `of` and `crop`)")
    master = locs.get(e["of"]) or {}
    src = R.ref_file(s.home, master["plate"]) if master.get("plate") else None
    if not src or not os.path.isfile(src):
        raise ValueError(f"'{e['of']}' has no plate yet")
    with Image.open(src) as im:
        size = im.size
    return {"id": cid, "path": R.ref_file(s.home, e["plate"]), "master": src, "size": size,
            "want": {"of": e["of"], "crop": e["crop"], "zoom": float(e.get("zoom") or ZOOM),
                     "master_sha1": F.file_digest(src)}}


def stage_part(c: dict) -> str:
    """The crop's part of the master's plate, cut and not enlarged, as a temporary PNG (the
    job's input; the caller removes it)."""
    import tempfile

    from PIL import Image
    w = c["want"]
    with Image.open(c["master"]) as im:
        im.load()
        part = im.crop(crop_box(im.size[0], im.size[1], w["crop"], w["zoom"])).convert("RGB")
    fd, path = tempfile.mkstemp(prefix="seriesmith-crop-", suffix=".png")
    os.close(fd)
    part.save(path, format="PNG")
    return path


def upscale_graph(part: str, model: str, width: int, height: int) -> dict:
    """The job: the part loaded (uploaded by the backend), through `model`, scaled to the
    plate's size, saved."""
    from seriesmith.backends import File
    return {
        "load": {"class_type": "LoadImage", "inputs": {"image": File(part)},
                 "_meta": {"title": "The crop's part of the plate"}},
        "model": {"class_type": "UpscaleModelLoader", "inputs": {"model_name": model}},
        "up": {"class_type": "ImageUpscaleWithModel",
               "inputs": {"upscale_model": ["model", 0], "image": ["load", 0]}},
        "fit": {"class_type": "ImageScale",
                "inputs": {"image": ["up", 0], "upscale_method": "lanczos", "width": int(width),
                           "height": int(height), "crop": "disabled"}},
        "save": {"class_type": "SaveImage",
                 "inputs": {"images": ["fit", 0], "filename_prefix": "seriesmith/crop"},
                 "_meta": {"title": "The crop, upscaled"}},
    }


def collect_upscale(ep: str, c: dict, model: str, run, status: str) -> str:
    """The run, ended with `status`: its picture written as the crop's, with its record
    (`upscaled`: the model). Kept only while the crop is still what was upscaled (the same
    master's plate, part and zoom). Returns the path; RuntimeError otherwise."""
    import tempfile
    if status != "succeeded":
        raise RuntimeError(getattr(run, "error", None) or f"the job ended {status}")
    outs = [o for o in run.outputs() if o.type in ("image", "file")]
    if not outs:
        raise RuntimeError("the job finished but returned no picture")
    now = crop_of(ep, c["id"])
    if now["want"] != c["want"] or now["path"] != c["path"]:
        raise RuntimeError("the crop changed while it was upscaled (its master's plate, part or "
                           "zoom): upscale it again")
    rec = F.read_json_or(record_path(c["path"]), None, want=dict)
    if os.path.isfile(c["path"]) and (rec is None or rec.get("sha1") != F.file_digest(c["path"])):
        raise RuntimeError("the crop's picture is one of yours now: kept, not replaced")
    fd, raw = tempfile.mkstemp(suffix=os.path.splitext(outs[0].name)[1] or ".png")
    os.close(fd)
    try:
        outs[0].save(raw)
        from PIL import Image
        with Image.open(raw) as im:
            im.load()
            if im.size != tuple(c["size"]):
                im = im.resize(tuple(c["size"]), Image.LANCZOS)
            buf = io.BytesIO()
            im.convert("RGB").save(buf, format="PNG")
    finally:
        os.remove(raw)
    F.write_bytes(c["path"], buf.getvalue())
    F.write_json(record_path(c["path"]), dict(c["want"], sha1=F.file_digest(c["path"]),
                                              upscaled=model))
    return c["path"]


def upscaled(path: str) -> str | None:
    """The upscale model crop picture `path` was made with, when it's the one seriesmith made
    and it was upscaled; None when stretched (or not seriesmith's)."""
    rec = F.read_json_or(record_path(path), None, want=dict)
    if not rec or not os.path.isfile(path) or rec.get("sha1") != F.file_digest(path):
        return None
    return rec.get("upscaled") or None


def upscale(backend, ep: str, cid: str, model: str | None = None, progress=None) -> str:
    """Crop `cid` upscaled now on `backend` (submitted and watched here): its path."""
    make_crops(ep, [cid])
    c = crop_of(ep, cid)
    m = pick_model(backend_models(backend), model)
    part = stage_part(c)
    try:
        run = backend.submit(upscale_graph(part, m, *c["size"]))
        status = run.watch(on_progress=progress)
        return collect_upscale(ep, c, m, run, status)
    finally:
        os.remove(part)


def backend_models(backend) -> list[str] | None:
    """The upscale models `backend`'s ComfyUI lists, None when it can't say."""
    try:
        ask = getattr(backend, "choices", None)
        if ask is not None:
            return ask("UpscaleModelLoader", "model_name")
        info = getattr(backend, "object_info", None)
        if info is None:
            return None
        from seriesmith.jobs import choices_in
        return choices_in(info(), "UpscaleModelLoader", "model_name")
    except Exception:                                    # noqa: BLE001  it can't say: the job will
        return None


def ensure(ep: str) -> list[dict]:
    """make_crops, never raising (a render or a build goes on without it): [] when the episode's
    series config can't be read."""
    try:
        return make_crops(ep)
    except (OSError, ValueError, FileNotFoundError):
        return []


__all__ = ["ensure", "make_crops", "record_path"]
