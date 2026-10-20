"""
Presets the editor offers as pictures to pick from, each filling a text that
stays editable: relighting a ref's picture (relight.json: the edit window's
Relight, a plate's wording and a character's or prop's), the series' look
(look.json: the series form's Look), a shot's framing (framing.json: its
`size:`) and its camera move (camera.json: how its `camera:` line starts).
Each preset's sample is under img/ (made by tools/make_preset_samples.py,
with seriesmith itself): a JPEG, or for a camera move a short silent clip;
one not made yet is simply left out of the answer.

Your own looks and relights (OWN_KINDS) are kept for every show on this
machine, beside its settings file: presets.json ({kind: [preset]}, the same
shape as the shipped ones) and their pictures under presets/<kind>/. They are
listed after the shipped ones in the group "yours", with `own: true`.

Standard library only.
"""
from __future__ import annotations

import json
import os
from seriesmith.core import fileio as F

HERE = os.path.dirname(os.path.abspath(__file__))
KINDS = ("relight", "look", "framing", "camera", "look_builder")
# a camera move's sample is a clip, the rest pictures
EXT = {"camera": ".mp4"}
# which of a relight preset's texts a ref kind reads
WORDING = {"location": "place", "character": "subject", "prop": "subject", "vehicle": "subject"}


# the sample scene every look is drawn in (tools/make_preset_samples.py, and a
# look of yours rendered by preset_pictures): a figure in a place, so a look shows on both
LOOK_SCENE = ("A woman in her thirties with short dark hair and a red wool coat waits at a tram stop "
              "on a city street at dusk, a lit cafe window behind her, a streetlamp just coming on")
# a figure's relight wording relights the figure; on the sample the street behind
# her is asked into the same light, or she'd stand lit by neon in a daylit street
SUBJECT_SCENE = "; the street behind her in the same light, as one picture"
# what a relight sample edits: the sample street (place) and the woman on it (subject)
BASE = {"place": os.path.join(HERE, "img", "base", "place.jpg"),
        "subject": os.path.join(HERE, "img", "base", "subject.jpg")}

OWN_KINDS = ("look", "relight")
OWN_GROUP = "yours"
OWN_IMG = "own"                     # an own preset's picture name: own/<kind>/<id>.jpg


class PresetError(ValueError):
    http_status = 400               # api.handler answers it with this


def own_dir() -> str:
    """The folder beside this machine's settings file."""
    from seriesmith.settings import settings_path
    return os.path.dirname(os.path.abspath(settings_path()))


def own_file() -> str:
    return os.path.join(own_dir(), "presets.json")


def _own_all() -> dict:
    try:
        with open(own_file(), encoding="utf-8") as fh:
            d = json.load(fh)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        raise PresetError(f"{own_file()} can't be read: {e}") from None
    return d if isinstance(d, dict) else {}


def own(kind: str) -> list[dict]:
    """Your own presets of `kind` (none for a kind that can't have them)."""
    if kind not in OWN_KINDS:
        return []
    return [p for p in (_own_all().get(kind) or []) if isinstance(p, dict) and p.get("id")]


def presets_of(kind: str) -> list[dict]:
    """The shipped presets of `kind`, then your own."""
    return _load(kind) + own(kind)


def _slug(label: str) -> str:
    s = "".join(c if c.isalnum() else "_" for c in label.strip().lower())
    return "_".join(x for x in s.split("_") if x)[:40] or "preset"


def save_own(kind: str, label: str, fields: dict, pid: str | None = None,
             picture: bytes | None = None) -> dict:
    """Keep one of your own presets: a look ({"text", "parts"?}) or a relight
    ({"place"?, "subject"?}). `pid` replaces that one of yours; without it the
    id comes from the label, made unique against the shipped ones and yours.
    `picture` (JPEG bytes) becomes its tile. Returns it as listing() does."""
    if kind not in OWN_KINDS:
        raise PresetError(f"you can save a {' or a '.join(OWN_KINDS)}, not a {kind!r}")
    if not isinstance(label, str) or not label.strip():
        raise PresetError("a preset needs a name")
    if kind == "look":
        text = fields.get("text")
        if not isinstance(text, str) or not text.strip():
            raise PresetError("a look preset needs its look line (text)")
        parts = fields.get("parts") or {}
        if not isinstance(parts, dict) or not all(isinstance(v, str) for v in parts.values()):
            raise PresetError("parts must be {row: option id}")
        body = {"text": text.strip(), **({"parts": parts} if parts else {})}
    else:
        body = {}
        for w in ("place", "subject"):
            v = fields.get(w)
            if v is not None and (not isinstance(v, str) or not v.strip()):
                raise PresetError(f"{w} must be the instruction, as text")
            if v:
                body[w] = v.strip()
        if not body:
            raise PresetError("a relight preset needs its instruction for a place or a subject")
    data = _own_all()
    mine = [p for p in (data.get(kind) or []) if isinstance(p, dict)]
    if pid is not None:
        if not any(p.get("id") == pid for p in mine):
            raise PresetError(f"you have no {kind} preset {pid!r} to replace")
    else:
        taken = {p["id"] for p in _load(kind)} | {p.get("id") for p in mine}
        base = pid = _slug(label)
        n = 2
        while pid in taken:
            pid, n = f"{base}_{n}", n + 1
    entry = {"id": pid, "label": label.strip(), "group": OWN_GROUP, **body}
    mine = [entry if p.get("id") == pid else p for p in mine]
    if not any(p is entry for p in mine):
        mine.append(entry)
    data[kind] = mine
    _write_own(data)
    if picture is not None:
        set_own_picture(kind, pid, picture)
    return next(p for p in listing(kind) if p["id"] == pid)


def own_preset(kind: str, pid: str) -> dict:
    """One of your presets, or PresetError."""
    p = next((p for p in own(kind) if p["id"] == pid), None)
    if p is None:
        raise PresetError(f"you have no {kind} preset {pid!r}")
    return p


def set_own_picture(kind: str, pid: str, picture: bytes) -> None:
    """`picture` (JPEG bytes) as the tile of one of your presets."""
    own_preset(kind, pid)
    F.write_bytes(os.path.join(own_dir(), "presets", kind, f"{pid}.jpg"), picture)


def set_own_field(kind: str, pid: str, key: str, value) -> None:
    """Set (or with None drop) one field of one of your presets: its picture's
    render while it is being made (`render`)."""
    data = _own_all()
    mine = [p for p in (data.get(kind) or []) if isinstance(p, dict)]
    hit = next((p for p in mine if p.get("id") == pid), None)
    if hit is None:
        raise PresetError(f"you have no {kind} preset {pid!r}")
    if value is None:
        hit.pop(key, None)
    else:
        hit[key] = value
    data[kind] = mine
    _write_own(data)


def delete_own(kind: str, pid: str) -> None:
    """Forget one of your own presets (and its picture)."""
    data = _own_all()
    mine = [p for p in (data.get(kind) or []) if isinstance(p, dict)]
    if not any(p.get("id") == pid for p in mine):
        raise PresetError(f"you have no {kind} preset {pid!r}")
    data[kind] = [p for p in mine if p.get("id") != pid]
    _write_own(data)
    pic = os.path.join(own_dir(), "presets", kind, f"{pid}.jpg")
    if os.path.isfile(pic):
        os.remove(pic)


def _write_own(data: dict) -> None:
    F.write_json(own_file(), data)


def _own_image(kind: str, pid: str) -> str | None:
    """Its picture's name, with the file's time on it so a new picture isn't
    served from a cache under the old name."""
    name = f"{OWN_IMG}/{kind}/{pid}.jpg"
    path = image_path(name)
    return f"{name}?v={int(os.path.getmtime(path))}" if path else None


def _load(kind: str) -> list[dict]:
    if kind not in KINDS:
        raise PresetError(f"preset kind must be one of {', '.join(KINDS)}, not {kind!r}")
    with open(os.path.join(HERE, f"{kind}.json"), encoding="utf-8") as fh:
        d = json.load(fh)
    return d["rows"] if kind == "look_builder" else d["presets"]


def compose_look(parts: dict) -> str:
    """The look line the builder writes from its picks ({row: option id}):
    the medium's clause, then the other rows' in order, all joined by semicolons;
    a drawn medium leaves the camera rows (camera, lens, film) out. "" for no
    medium picked."""
    rows = _load("look_builder")
    by = {r["id"]: {o["id"]: o for o in r["options"]} for r in rows}
    medium = by["medium"].get(parts.get("medium") or "")
    if medium is None:
        return ""
    clauses = []
    for r in rows[1:]:
        if medium.get("drawn") and r.get("camera_row"):
            continue
        o = by[r["id"]].get(parts.get(r["id"]) or "")
        if o:
            clauses.append(o["clause"])
    return "; ".join([medium["clause"], *clauses])


def image_name(kind: str, pid: str, wording: str | None = None) -> str:
    """A preset's sample, under img/: look/<id>.jpg, relight/<id>-<wording>.jpg,
    camera/<id>.mp4."""
    return f"{kind}/{pid}{'-' + wording if wording else ''}{EXT.get(kind, '.jpg')}"


def image_path(name: str) -> str | None:
    """The file of a sample picture named as image_name names it, or None
    (not made yet, or a name that isn't one)."""
    name = name.split("?", 1)[0]              # an own picture's ?v= (its time)
    parts = name.replace("\\", "/").split("/")
    if len(parts) == 3 and parts[0] == OWN_IMG:
        kind, file = parts[1], parts[2]
        if kind not in OWN_KINDS or not file.endswith(".jpg") or file.startswith(".") \
                or any(c in file for c in ":"):
            return None
        p = os.path.join(own_dir(), "presets", kind, file)
        return p if os.path.isfile(p) else None
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
        if kind == "look_builder":
            opts = []
            for o in p["options"]:
                name = image_name(kind, f"{p['id']}-{o['id']}")
                opts.append({**o, **({"image": name} if image_path(name) else {})})
            out.append({"id": p["id"], "label": p["label"], "camera_row": bool(p.get("camera_row")),
                        "options": opts})
            continue
        if kind == "look":
            name = image_name(kind, p["id"])
            out.append({"id": p["id"], "label": p["label"], "group": p.get("group", ""),
                        "text": p["text"], "parts": p.get("parts") or {},
                        **({"image": name} if image_path(name) else {})})
            continue
        words = [w for w in (p.get("for") or ("place", "subject")) if p.get(w)]
        images = {w: image_name(kind, p["id"], w) for w in words}
        out.append({"id": p["id"], "label": p["label"], "group": p.get("group", ""),
                    "for": words, "texts": {w: p[w] for w in words},
                    "images": {w: n for w, n in images.items() if image_path(n)}})
    for p in own(kind):
        pic = _own_image(kind, p["id"])
        # a picture being rendered for it (preset_pictures.render), or why the last one failed
        extra = {**({"rendering": True} if p.get("render") else {}),
                 **({"picture_error": p["picture_error"]} if p.get("picture_error") else {})}
        if kind == "look":
            out.append({"id": p["id"], "label": p.get("label") or p["id"], "group": OWN_GROUP,
                        "text": p.get("text", ""), "parts": p.get("parts") or {}, "own": True,
                        **({"image": pic} if pic else {}), **extra})
        else:
            words = [w for w in ("place", "subject") if p.get(w)]
            out.append({"id": p["id"], "label": p.get("label") or p["id"], "group": OWN_GROUP,
                        "for": words, "texts": {w: p[w] for w in words}, "own": True,
                        "images": {w: pic for w in words} if pic else {}, **extra})
    return out


def relight_text(pid: str, ref_kind: str) -> str:
    """A relight preset's instruction for a ref of `ref_kind`."""
    wording = WORDING.get(ref_kind, "subject")
    for p in presets_of("relight"):
        if p["id"] == pid:
            text = p.get(wording)
            if not text:
                raise PresetError(f"relight {pid!r} has no wording for a {ref_kind}")
            return text
    raise PresetError(f"no relight preset {pid!r}")
