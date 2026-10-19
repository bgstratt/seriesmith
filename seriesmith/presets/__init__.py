"""
Presets the editor offers as pictures to pick from, each filling a text that
stays editable: relighting a ref's picture (relight.json: the edit window's
Relight, a plate's wording and a character's or prop's), the series' look
(look.json: the series form's Look), a shot's framing (framing.json: its
`size:`) and its camera move (camera.json: how its `camera:` line starts).
Each preset's sample is under img/ (made by tools/make_preset_samples.py,
with seriesmith itself): a JPEG, or for a camera move a short silent clip;
one not made yet is simply left out of the answer.

Standard library only.
"""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
KINDS = ("relight", "look", "framing", "camera")
# a camera move's sample is a clip, the rest pictures
EXT = {"camera": ".mp4"}
# which of a relight preset's texts a ref kind reads
WORDING = {"location": "place", "character": "subject", "prop": "subject", "vehicle": "subject"}


class PresetError(ValueError):
    pass


def _load(kind: str) -> list[dict]:
    if kind not in KINDS:
        raise PresetError(f"preset kind must be one of {', '.join(KINDS)}, not {kind!r}")
    with open(os.path.join(HERE, f"{kind}.json"), encoding="utf-8") as fh:
        return json.load(fh)["presets"]


def image_name(kind: str, pid: str, wording: str | None = None) -> str:
    """A preset's sample, under img/: look/<id>.jpg, relight/<id>-<wording>.jpg,
    camera/<id>.mp4."""
    return f"{kind}/{pid}{'-' + wording if wording else ''}{EXT.get(kind, '.jpg')}"


def image_path(name: str) -> str | None:
    """The file of a sample picture named as image_name names it, or None
    (not made yet, or a name that isn't one)."""
    parts = name.replace("\\", "/").split("/")
    if (len(parts) != 2 or parts[0] not in KINDS or not parts[1].endswith(EXT.get(parts[0], ".jpg"))
            or any(c in parts[1] for c in "/\\:") or parts[1].startswith(".")):
        return None
    p = os.path.join(HERE, "img", parts[0], parts[1])
    return p if os.path.isfile(p) else None


def listing(kind: str) -> list[dict]:
    """The presets of `kind`, as the editor shows them. A look: {id, label,
    group, text, image}. A relight: {id, label, group, for: [wordings],
    texts: {wording: text}, images: {wording: name}}. A framing: {id, label,
    group, hint, image}. A camera move: {id, label, group, move, image}. An
    image is the sample's name for GET /seriesmith/presets/image, present
    only when made."""
    out = []
    for p in _load(kind):
        if kind in ("framing", "camera"):
            name = image_name(kind, p["id"])
            keep = ("hint",) if kind == "framing" else ("move",)
            out.append({"id": p["id"], "label": p["label"], "group": p.get("group", ""),
                        **{k: p[k] for k in keep}, **({"image": name} if image_path(name) else {})})
            continue
        if kind == "look":
            name = image_name(kind, p["id"])
            out.append({"id": p["id"], "label": p["label"], "group": p.get("group", ""),
                        "text": p["text"], **({"image": name} if image_path(name) else {})})
            continue
        words = [w for w in (p.get("for") or ("place", "subject")) if p.get(w)]
        images = {w: image_name(kind, p["id"], w) for w in words}
        out.append({"id": p["id"], "label": p["label"], "group": p.get("group", ""),
                    "for": words, "texts": {w: p[w] for w in words},
                    "images": {w: n for w, n in images.items() if image_path(n)}})
    return out


def relight_text(pid: str, ref_kind: str) -> str:
    """A relight preset's instruction for a ref of `ref_kind`."""
    wording = WORDING.get(ref_kind, "subject")
    for p in _load("relight"):
        if p["id"] == pid:
            text = p.get(wording)
            if not text:
                raise PresetError(f"relight {pid!r} has no wording for a {ref_kind}")
            return text
    raise PresetError(f"no relight preset {pid!r}")
