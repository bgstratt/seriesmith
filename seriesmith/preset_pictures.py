"""Pictures for your own presets (seriesmith.presets OWN_KINDS), three ways, each
asked for (nothing renders on its own):

- **render** it on the sample scene, as the shipped presets' are, on the model you
  pick: a look drawn on the woman in red at the tram stop (presets.LOOK_SCENE); a
  relight as an edit of the sample street or of the woman on it (presets.BASE).
  It runs on seriesmith's queue in a scratch episode beside this machine's
  settings (presets/_work, the starter series), and becomes the tile when it is
  done (`finish`, run as the presets are listed);
- **from your work**: a ref's picture or take, or a frame of a shot's take;
- **import** a picture of your own.

Every picture is kept as a JPEG, PICTURE px on its long side.
"""
from __future__ import annotations

import io
import os
import shutil
import tempfile

from seriesmith import presets as PR
from seriesmith import refs as R
from seriesmith import takes as T

PICTURE = 480
STARTER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples", "starter")
PLATE, FIGURE, FIGURE_VIEW = "location:porch", "subject:ada", "01_threequarter"


class PictureError(ValueError):
    pass


def shrink(path: str, size: int = PICTURE) -> bytes:
    """A picture file as a tile: JPEG bytes, `size` px on its long side, the
    way up it was shot (a phone photo's orientation tag read)."""
    from PIL import Image, ImageOps
    try:
        with Image.open(path) as src:
            im = ImageOps.exif_transpose(src).convert("RGB")
            im.thumbnail((size, size))
            out = io.BytesIO()
            im.save(out, "JPEG", quality=85)
    except OSError as e:
        raise PictureError(f"the picture can't be read: {e}") from None
    return out.getvalue()


# ---------------------------------------------------------------------------
# from your work, or a picture of yours
# ---------------------------------------------------------------------------

def from_ref(kind: str, pid: str, ep: str, ref_id: str, view: str | None,
             take: int | None) -> None:
    """A ref's take (or, without `take`, its live picture) as the tile."""
    s = R.load_series(ep)
    ref = R.find_ref(s, ref_id)
    try:
        path = R._picture_of(s, ref, view, take, "the preset's picture")["path"]
    except R.RefError as e:
        raise PictureError(str(e)) from None
    PR.set_own_picture(kind, pid, shrink(path))


def from_shot(kind: str, pid: str, ep: str, pass_: str, shot: str, take: int,
              seconds: float) -> None:
    """The frame at `seconds` into a shot's take as the tile."""
    src = T.get_take(ep, pass_, shot, take)
    if src is None or not src.has_video:
        raise PictureError(f"{shot} {pass_} t{take:02d} has no video")
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "frame.png")
        try:
            R.extract_frame_at(src.paths.mp4, max(0.0, float(seconds)), out)
        except R.RefError as e:
            raise PictureError(str(e)) from None
        PR.set_own_picture(kind, pid, shrink(out))


def from_file(kind: str, pid: str, path: str) -> None:
    """A picture file of yours as the tile."""
    PR.set_own_picture(kind, pid, shrink(path))


# ---------------------------------------------------------------------------
# rendered on the sample scene
# ---------------------------------------------------------------------------

def work_episode() -> str:
    """The scratch episode the renders run in (the starter series, built once,
    its plate and its woman's three-quarter view the shipped bases)."""
    from seriesmith import edit as E
    ep = os.path.join(PR.own_dir(), "presets", "_work", "ep01")
    if not os.path.isfile(os.path.join(ep, "shotlist", "shots.json")):
        os.makedirs(ep, exist_ok=True)
        for name in ("series.json", "ep01.md"):
            shutil.copyfile(os.path.join(STARTER, name), os.path.join(ep, name))
        if not E.build_episode(ep).get("ok"):
            raise PictureError("the sample scene's episode didn't build")
    s = R.load_series(ep)
    for ref_id, view, base in ((PLATE, None, PR.BASE["place"]), (FIGURE, FIGURE_VIEW, PR.BASE["subject"])):
        ref = R.find_ref(s, ref_id)
        if base_take(ref, view) is None:
            R.pick_take(s, ref, view, R.import_take(s, ref, view, base, note=BASE_NOTE).take)
            s = R.load_series(ep)
    return ep


BASE_NOTE = "the presets' sample base"


def base_take(ref: R.Ref, view: str | None) -> int | None:
    """The take of `ref` that is the shipped base a relight renders on. Always
    that take, never the live picture: a render that got picked mustn't become
    what the next relight edits."""
    for t in R.list_takes(ref, view):
        if (t.sidecar or {}).get("note") == BASE_NOTE and t.usable:
            return t.take
    return None


def request(kind: str, pid: str, target: str) -> R.GenRequest:
    """What rendering one of your presets' pictures asks for."""
    p = PR.own_preset(kind, pid)
    if kind == "look":
        return R.GenRequest(ref=PLATE, prompt=f"{p['text']}. {PR.LOOK_SCENE}", target=target,
                            note=f"preset picture: {p['label']}")
    if p.get("place"):
        ref, view, text = PLATE, None, p["place"]
    else:
        ref, view, text = FIGURE, FIGURE_VIEW, p["subject"].rstrip(".") + PR.SUBJECT_SCENE
    base = base_take(R.find_ref(R.load_series(work_episode()), ref), view)
    return R.GenRequest(ref=ref, view=view, prompt=text, target=target, note=f"preset picture: {p['label']}",
                        edit={"take": base, "with": [], "wrap": True})


def render(kind: str, pid: str, target: str, comfy, base, runner, listing=None, resolve=None,
           cache=None, backend: str | None = None) -> dict:
    """Queue the picture of one of your presets on `target` (an image model for
    a look, an edit model for a relight). Returns the queued take; `finish`
    makes it the tile once it is done."""
    ep = work_episode()
    s = R.load_series(ep)
    req = request(kind, pid, target)
    try:
        result = R.queue_generate(s, req, comfy, base, save_node=True, listing=listing, resolve=resolve,
                                  cache=cache, runner=runner, backend=backend)
    except (R.RefError, R.UnknownRef) as e:
        raise PictureError(str(e)) from None
    if not result["queued"]:
        raise PictureError("; ".join(e.get("error", "") for e in result["errors"]) or "nothing was queued")
    q = result["queued"][0]
    PR.set_own_field(kind, pid, "picture_error", None)
    PR.set_own_field(kind, pid, "render", {"ref": q["ref"], "view": q["view"], "take": q["take"]})
    return q


def finish() -> None:
    """Make each finished render the tile of its preset (and note a failed one).
    Cheap when nothing is rendering; run before the presets are listed."""
    pending = [(k, p) for k in PR.OWN_KINDS for p in PR.own(k) if p.get("render")]
    if not pending:
        return
    ep = os.path.join(PR.own_dir(), "presets", "_work", "ep01")
    try:
        s = R.load_series(ep)
    except (FileNotFoundError, ValueError):
        for k, p in pending:
            PR.set_own_field(k, p["id"], "render", None)
        return
    for kind, p in pending:
        r = p["render"]
        try:
            t = R.get_take(R.find_ref(s, r["ref"]), r.get("view"), r["take"])
        except (R.RefError, R.UnknownRef, KeyError):
            PR.set_own_field(kind, p["id"], "render", None)
            continue
        if t.usable:
            PR.set_own_picture(kind, p["id"], shrink(t.paths.image))
            PR.set_own_field(kind, p["id"], "render", None)
        elif t.status == "failed":
            PR.set_own_field(kind, p["id"], "render", None)
            sc = t.sidecar or {}
            PR.set_own_field(kind, p["id"], "picture_error",
                             sc.get("error") or sc.get("save_notes") or "the render failed")
