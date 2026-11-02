"""
mix.py — an episode's sound beyond the takes: four tracks, their items, a mix.

docs/SOUND.md is the design. `mix.json` beside `cut.json` holds one mix per pass:

    {"final": {
       "tracks": {"dialogue": {"gain_db": 0}, "music": {"gain_db": -2, "duck_db": -9},
                  "ambience": {"mute": true}},
       "items": [{"id": "m01", "track": "music", "path": "sound/m01/t02.wav",
                  "in": {"shot": "sh010", "frame": 12}, "out": {"shot": "sh050", "frame": 40},
                  "offset": 1.5, "gain_db": -3, "fade_in": 24, "fade_out": 48,
                  "points": [{"at": {"shot": "sh040", "frame": 0}, "db": 0},
                             {"at": {"shot": "sh050", "frame": 12}, "db": 6}]},
                 {"id": "a01", "track": "ambience", "path": "sound/beds/harbour.wav",
                  "in": {"shot": "sh010", "frame": 0}, "out": {"shot": "sh030", "frame": 96},
                  "loop": true}],
       "hits": [{"id": "h1", "name": "the door bursts", "at": {"shot": "sh030", "frame": 17},
                 "kind": "accent"},
                {"id": "h2", "name": "reveal", "at": {"shot": "sh060", "frame": 4},
                 "kind": "arrive", "must": false}],
       "regions": [{"from": {"shot": "sh050", "frame": 0}, "to": {"shot": "sh060", "frame": 48},
                    "music_duck_db": 0, "dialogue_db": -4}],
       "duck": {"threshold_db": -45, "attack_ms": 60, "release_ms": 450},
       "loudness": {"target_lufs": -16, "true_peak_db": -1},
       "beds": {"diner": {"gain_db": -3}, "platform": {"mute": true}},
       "fx": {"sh010": {"take": 2, "gain_db": -4}, "sh030": {"take": 1, "keep_stale": true}}},
     "proxy": {}}

- **Tracks**: dialogue (the cut's own sound, each clip's take as assemble joins it, plus
  any items put on it), effects, ambience, music. Each has a fader (`gain_db`; GAIN_DEFAULT
  when nothing sets it: music -12 dB), `mute`,
  `solo`, and (all but dialogue) `duck_db`, how far it dips while someone speaks.
- **An anchor** is a shot and a frame of it: a frame of the shot's take at the cut's rate,
  counted from the take's first frame, before any trim. A trim or a reorder moves it with its
  shot, and a hit stays on the action it marks. One whose shot isn't in the cut is dropped
  with its item (and said so).
- **A hit** is a named anchor a cue is written to land: its `kind` (accent, the default;
  arrive, the peak lands here; drop, the music cuts out or thins; turn, a change of key or
  mood) and whether it `must` land (the default) or may miss when one tempo can't land them
  all.
- **An item** plays `path` (relative to the episode) from `offset` seconds into it, from its
  `in` anchor to its `out` (none: until the file ends), at `gain_db`, faded in and out over
  `fade_in` / `fade_out` frames, its level shaped by `points` (dB at anchors, linear between,
  held beyond the first and last), and `loop`ed with a crossfade when the file is shorter.
- **Ducking** is a gain curve computed from the dialogue track (its level in 10 ms windows
  against `threshold_db`, smoothed by attack and release), so the editor's preview and the
  render apply the same dips. A **region** changes it for a stretch: `music_duck_db` (0 is
  "score forward": no dip) and `dialogue_db` (the dialogue lowered under it).
- **Beds** (docs/SOUND.md phase 3, ambience.py): a place's ambience bed is laid under its
  shots from the cut and the series config, never stored as an item; `beds` keeps only what
  you change of one place's: its `gain_db` and `mute`. The beds sit on the ambience track
  (its fader and ducking apply; its items play over them).
- **Effects** (docs/SOUND.md phase 4, fx.py): a shot's effects take, made from the frames of
  the take the cut plays, is laid from the cut at its clip, never stored as an item; `fx`
  keeps which take each shot plays (`take`), its `gain_db`, `mute`, and `keep_stale` (play it
  though its picture has changed). They sit on the effects track (its fader applies).
- **Loudness**: the mix is brought to `target_lufs` (default -16) by one gain, measured by
  ffmpeg's loudnorm, and held under `true_peak_db` (default -1) by a limiter when the gain
  would push it over. The stems take the same gain, so they sum to the mix but for the
  limiter.

A pass with no items and every track at its defaults is no mix (`active`): assemble then
leaves the cut's sound as it always was.
"""

from __future__ import annotations

import json
import math
import os
import re
import subprocess

from seriesmith import ff as FF
from seriesmith.core import fileio as F

MIX_FILE = "mix.json"
PASSES = ("final", "proxy")
TRACKS = ("dialogue", "effects", "ambience", "music")
RATE = 48000

# how far each track dips while someone speaks, dB; the dialogue never ducks
DUCK_DEFAULT = {"effects": 0.0, "ambience": -6.0, "music": -9.0}
# each track's fader when nothing sets it: score sits well under the lines (Ballroom ep03: at
# 0 dB the music was louder than the dialogue under a line, even dipped; at -12 dB it sat 5-10 dB
# under the lines and level with them on a swell)
GAIN_DEFAULT = {"dialogue": 0.0, "effects": 0.0, "ambience": 0.0, "music": -12.0}
DUCK = {"threshold_db": -45.0, "attack_ms": 60.0, "release_ms": 450.0}
LOUDNESS = {"target_lufs": -16.0, "true_peak_db": -1.0}

GAIN_MIN, GAIN_MAX = -60.0, 12.0
FADE_MAX = 2400                                   # frames: 100 s at 24 fps
WINDOW_S = 0.010                                  # the ducking detector's window
LOOP_XFADE_S = 1.0                                # a loop's crossfade, at most

ITEM_FIELDS = ("id", "track", "path", "in", "out", "offset", "gain_db", "fade_in", "fade_out",
               "points", "loop", "label")
TRACK_FIELDS = ("gain_db", "mute", "solo", "duck_db")
REGION_FIELDS = ("from", "to", "music_duck_db", "ambience_duck_db", "dialogue_db")
HIT_FIELDS = ("id", "name", "at", "kind", "must")
# what a hit asks of the music (docs/SOUND.md "The cue window"): a sting or downbeat on
# the frame, the peak arriving there, the music cutting out or thinning, a change of key
# or mood; accent is the default
HIT_KINDS = ("accent", "arrive", "drop", "turn")
MIX_FIELDS = ("tracks", "items", "hits", "regions", "duck", "loudness", "beds", "fx")
BED_FIELDS = ("gain_db", "mute")
FX_FIELDS = ("take", "gain_db", "mute", "keep_stale")
_ID = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


# ---------------------------------------------------------------------------
# the stored form
# ---------------------------------------------------------------------------

def _num(v, what: str, lo: float, hi: float, default: float | None = None) -> float:
    if v is None and default is not None:
        return default
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:
        raise ValueError(f"{what} must be a number, not {v!r}")
    if not lo <= v <= hi:
        raise ValueError(f"{what} must be between {lo:g} and {hi:g}, not {v:g}")
    return round(float(v), 3)


def _frames(v, what: str) -> int:
    if v is None:
        return 0
    if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= FADE_MAX:
        raise ValueError(f"{what} is a whole number of frames, 0 to {FADE_MAX}, not {v!r}")
    return v


def check_anchor(raw, what: str) -> dict:
    """{"shot", "frame"}: a shot id and a frame of its take (0 or more)."""
    if not isinstance(raw, dict) or set(raw) - {"shot", "frame"}:
        raise ValueError(f"{what} must be {{\"shot\", \"frame\"}}, not {raw!r}")
    shot, frame = raw.get("shot"), raw.get("frame", 0)
    if not isinstance(shot, str) or not shot.strip():
        raise ValueError(f"{what} needs its shot")
    if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
        raise ValueError(f"{what}'s frame must be a whole number, 0 or more, not {frame!r}")
    return {"shot": shot.strip(), "frame": frame}


def _id(v, what: str) -> str:
    if not isinstance(v, str) or not _ID.match(v):
        raise ValueError(f"{what} id must be 1-40 letters, digits, _ or -, not {v!r}")
    return v


def check_item(raw) -> dict:
    """One item in its stored form (defaults dropped). ValueError says what's wrong."""
    if not isinstance(raw, dict):
        raise ValueError("an item must be an object")
    unknown = set(raw) - set(ITEM_FIELDS)
    if unknown:
        raise ValueError(f"unknown item field(s) {', '.join(sorted(unknown))}")
    out: dict = {"id": _id(raw.get("id"), "an item's")}
    if raw.get("track") not in TRACKS:
        raise ValueError(f"item {out['id']}: track must be one of {', '.join(TRACKS)}, "
                         f"not {raw.get('track')!r}")
    out["track"] = raw["track"]
    path = raw.get("path")
    if not isinstance(path, str) or not path.strip():
        raise ValueError(f"item {out['id']} needs the path of its sound, relative to the episode")
    out["path"] = path.strip().replace("\\", "/")
    out["in"] = check_anchor(raw.get("in"), f"item {out['id']}'s in")
    if raw.get("out") is not None:
        out["out"] = check_anchor(raw["out"], f"item {out['id']}'s out")
    for k, (lo, hi) in {"offset": (0.0, 86400.0), "gain_db": (GAIN_MIN, GAIN_MAX)}.items():
        v = _num(raw.get(k), f"item {out['id']}'s {k}", lo, hi, 0.0)
        if v:
            out[k] = v
    for k in ("fade_in", "fade_out"):
        v = _frames(raw.get(k), f"item {out['id']}'s {k}")
        if v:
            out[k] = v
    if raw.get("points"):
        if not isinstance(raw["points"], list):
            raise ValueError(f"item {out['id']}'s points must be a list")
        pts = []
        for i, p in enumerate(raw["points"]):
            if not isinstance(p, dict) or set(p) - {"at", "db"}:
                raise ValueError(f"item {out['id']}'s point {i + 1} must be {{\"at\", \"db\"}}")
            pts.append({"at": check_anchor(p.get("at"), f"item {out['id']}'s point {i + 1}"),
                        "db": _num(p.get("db"), f"item {out['id']}'s point {i + 1}'s db",
                                   GAIN_MIN, GAIN_MAX)})
        out["points"] = pts
    if raw.get("loop"):
        out["loop"] = True
    if isinstance(raw.get("label"), str) and raw["label"].strip():
        out["label"] = raw["label"].strip()[:120]
    return out


def check(raw) -> dict:
    """A pass's mix in its stored form (defaults dropped, so an empty mix is {}; a track's
    values are kept as given, to override the series config's). ValueError for anything
    that isn't one."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("a mix must be an object")
    unknown = set(raw) - set(MIX_FIELDS)
    if unknown:
        raise ValueError(f"unknown mix field(s) {', '.join(sorted(unknown))}: one of "
                         f"{', '.join(MIX_FIELDS)}")
    out: dict = {}
    tracks = {}
    for name, t in (raw.get("tracks") or {}).items():
        if name not in TRACKS:
            raise ValueError(f"unknown track {name!r}: one of {', '.join(TRACKS)}")
        if not isinstance(t, dict) or set(t) - set(TRACK_FIELDS):
            raise ValueError(f"track {name} takes {', '.join(TRACK_FIELDS)}")
        if name == "dialogue" and t.get("duck_db") is not None:
            raise ValueError("the dialogue track doesn't duck")
        # a track's values are kept when given, defaults or not: a 0 dB fader or an
        # unmute here overrides the series config's `sound.tracks`
        o: dict = {}
        if t.get("gain_db") is not None:
            o["gain_db"] = _num(t["gain_db"], f"track {name}'s gain_db", GAIN_MIN, GAIN_MAX)
        for k in ("mute", "solo"):
            if t.get(k) is not None:
                if not isinstance(t[k], bool):
                    raise ValueError(f"track {name}'s {k} is true or false")
                o[k] = t[k]
        if name != "dialogue" and t.get("duck_db") is not None:
            o["duck_db"] = _num(t["duck_db"], f"track {name}'s duck_db", -40.0, 0.0)
        if o:
            tracks[name] = o
    if tracks:
        out["tracks"] = tracks
    items, seen = [], set()
    for raw_item in raw.get("items") or []:
        it = check_item(raw_item)
        if it["id"] in seen:
            raise ValueError(f"two items are called {it['id']}")
        seen.add(it["id"])
        items.append(it)
    if items:
        out["items"] = items
    hits, seen = [], set()
    for h in raw.get("hits") or []:
        if not isinstance(h, dict) or set(h) - set(HIT_FIELDS):
            raise ValueError(f"a hit takes {', '.join(HIT_FIELDS)}")
        hid = _id(h.get("id"), "a hit's")
        if hid in seen:
            raise ValueError(f"two hits are called {hid}")
        seen.add(hid)
        hit = {"id": hid, "at": check_anchor(h.get("at"), f"hit {hid}")}
        if isinstance(h.get("name"), str) and h["name"].strip():
            hit["name"] = h["name"].strip()[:120]
        kind = h.get("kind") or HIT_KINDS[0]
        if kind not in HIT_KINDS:
            raise ValueError(f"hit {hid}'s kind must be one of {', '.join(HIT_KINDS)}, "
                             f"not {kind!r}")
        if kind != HIT_KINDS[0]:
            hit["kind"] = kind
        if h.get("must") is not None and not isinstance(h["must"], bool):
            raise ValueError(f"hit {hid}'s must is true or false")
        if h.get("must") is False:
            hit["must"] = False
        hits.append(hit)
    if hits:
        out["hits"] = hits
    regions = []
    for i, r in enumerate(raw.get("regions") or []):
        if not isinstance(r, dict) or set(r) - set(REGION_FIELDS):
            raise ValueError(f"region {i + 1} takes {', '.join(REGION_FIELDS)}")
        reg = {"from": check_anchor(r.get("from"), f"region {i + 1}'s from"),
               "to": check_anchor(r.get("to"), f"region {i + 1}'s to")}
        for k, lo in (("music_duck_db", -40.0), ("ambience_duck_db", -40.0),
                      ("dialogue_db", GAIN_MIN)):
            if r.get(k) is not None:
                reg[k] = _num(r[k], f"region {i + 1}'s {k}", lo, 0.0)
        regions.append(reg)
    if regions:
        out["regions"] = regions
    beds = {}
    for place, b in (raw.get("beds") or {}).items():
        if not isinstance(place, str) or not _ID.match(place):
            raise ValueError(f"a bed is named by its place's id, not {place!r}")
        if not isinstance(b, dict) or set(b) - set(BED_FIELDS):
            raise ValueError(f"bed {place} takes {', '.join(BED_FIELDS)}")
        o = {}
        if b.get("gain_db"):
            o["gain_db"] = _num(b["gain_db"], f"bed {place}'s gain_db", GAIN_MIN, GAIN_MAX)
        if b.get("mute") is not None and not isinstance(b["mute"], bool):
            raise ValueError(f"bed {place}'s mute is true or false")
        if b.get("mute"):
            o["mute"] = True
        if o:
            beds[place] = o
    if beds:
        out["beds"] = beds
    fx = {}
    for shot, f in (raw.get("fx") or {}).items():
        if not isinstance(shot, str) or not _ID.match(shot):
            raise ValueError(f"a shot's effects are named by its id, not {shot!r}")
        if not isinstance(f, dict) or set(f) - set(FX_FIELDS):
            raise ValueError(f"effects {shot} take {', '.join(FX_FIELDS)}")
        n = f.get("take")
        if isinstance(n, bool) or not isinstance(n, int) or n < 1:
            raise ValueError(f"effects {shot}'s take is a take number, not {n!r}")
        o = {"take": n}
        if f.get("gain_db"):
            o["gain_db"] = _num(f["gain_db"], f"effects {shot}'s gain_db", GAIN_MIN, GAIN_MAX)
        for k in ("mute", "keep_stale"):
            if f.get(k) is not None and not isinstance(f[k], bool):
                raise ValueError(f"effects {shot}'s {k} is true or false")
            if f.get(k):
                o[k] = True
        fx[shot] = o
    if fx:
        out["fx"] = fx
    for key, defaults, bounds in (
            ("duck", DUCK, {"threshold_db": (-80.0, 0.0), "attack_ms": (1.0, 2000.0),
                            "release_ms": (1.0, 5000.0)}),
            ("loudness", LOUDNESS, {"target_lufs": (-40.0, -5.0), "true_peak_db": (-9.0, 0.0)})):
        given = raw.get(key)
        if given is None:
            continue
        if not isinstance(given, dict) or set(given) - set(defaults):
            raise ValueError(f"{key} takes {', '.join(defaults)}")
        o = {}
        for k, (lo, hi) in bounds.items():
            if given.get(k) is not None:
                v = _num(given[k], f"{key}'s {k}", lo, hi)
                if v != defaults[k]:
                    o[k] = v
        if o:
            out[key] = o
    return out


def load(root: str) -> dict:
    """Every pass's mix, as `mix.json` holds them ({} for a pass with none)."""
    data = F.read_json_copy(os.path.join(root, MIX_FILE)) or {}
    return {p: data.get(p) if isinstance(data.get(p), dict) else {} for p in PASSES}


def save(root: str, data: dict) -> None:
    F.write_json(os.path.join(root, MIX_FILE), {p: data.get(p) or {} for p in PASSES})


def write(root: str, pass_: str, raw) -> dict:
    """Check `raw` and write it as pass `pass_`'s mix; returns it as stored. The file as
    it was goes to <ep>/_history/mix.json.<stamp> first, as cut.json's does; a mix that
    changes nothing writes nothing. ValueError for one that doesn't check."""
    from seriesmith import source as SRC                # it imports edit: not at the top
    if pass_ not in PASSES:
        raise ValueError(f"pass must be one of {', '.join(PASSES)}, not {pass_!r}")
    mix = check(raw)
    data = load(root)
    if data.get(pass_) == mix:
        return mix
    path = os.path.join(root, MIX_FILE)
    if os.path.isfile(path):
        with open(path, "rb") as fh:
            SRC.save_history_bytes(root, MIX_FILE, fh.read())
    data[pass_] = mix
    save(root, data)
    return mix


def for_pass(root: str, pass_: str, series: dict | None = None) -> dict:
    """A pass's mix, checked, with the series config's `sound` defaults under it (track
    levels, the loudness target). A hand-edited file that doesn't check is ValueError."""
    mix = check(load(root).get(pass_))
    snd = (series or {}).get("sound") or {}
    out = dict(mix)
    if isinstance(snd.get("tracks"), dict):
        merged = {k: dict(v) for k, v in snd["tracks"].items() if k in TRACKS}
        for k, v in (mix.get("tracks") or {}).items():
            merged.setdefault(k, {}).update(v)
        out["tracks"] = merged
    if isinstance(snd.get("loudness"), dict):
        out["loudness"] = {**snd["loudness"], **(mix.get("loudness") or {})}
    return out


def fader(tracks: dict, name: str) -> float:
    """A track's fader in dB: the mix's (or the series config's), else GAIN_DEFAULT."""
    v = (tracks.get(name) or {}).get("gain_db")
    return float(GAIN_DEFAULT[name] if v is None else v)


def active(mix: dict) -> bool:
    """Whether a mix changes anything: an item, or a track's level or mute."""
    return bool(mix.get("items") or any(
        t.get("gain_db") or t.get("mute") or t.get("solo")
        for t in (mix.get("tracks") or {}).values()))


# ---------------------------------------------------------------------------
# anchors against the cut
# ---------------------------------------------------------------------------

def shot_origins(plan: list[dict]) -> dict[str, dict]:
    """Where each shot of an assembled cut sits: {shot: {"origin", "first", "used"}} in
    the cut's frames. `origin` is where the take's frame 0 would play, `first` the frame
    of the take the clip starts on (its trim_in), `used` how many it plays. A dissolve
    overlaps a clip with the one before it, as assemble lays them."""
    out, t = {}, 0
    for p in plan:
        t -= p.get("dissolve_in", 0)
        out[p["id"]] = {"origin": t - p["trim_in"], "first": p["trim_in"], "used": p["used"]}
        t += p["used"]
    return out


def place(anchor: dict, origins: dict) -> int | None:
    """An anchor's frame in the cut, or None when its shot isn't in it."""
    o = origins.get(anchor["shot"])
    return None if o is None else o["origin"] + anchor["frame"]


def anchor_at(frame: int, origins: dict) -> dict | None:
    """The anchor for a frame of the cut: the shot playing there (the later one where a
    dissolve overlaps two) and the frame of its take. A frame before the first shot is
    the first shot's, after the last the last's (its take's frames past its end); None
    for a cut with no shots."""
    if not origins:
        return None
    best = None
    for shot, o in origins.items():
        start = o["origin"] + o["first"]
        if start <= frame and (best is None or start >= best[1]):
            best = (shot, start)
    if best is None:                                  # before the first shot
        best = min(((s, o["origin"] + o["first"]) for s, o in origins.items()),
                   key=lambda x: x[1])
    return {"shot": best[0], "frame": max(0, frame - origins[best[0]]["origin"])}


def placed(mix: dict, origins: dict, total: int, fps: float, root: str,
           length=None, beds: list[dict] | None = None,
           fx: list[dict] | None = None) -> tuple[dict[str, list[dict]], list[str]]:
    """Each track's items laid on the cut, for a timeline that plays files (the FCP7
    export): ({track: [{"id", "label", "path" (absolute), "start", "end" (cut frames),
    "in" (the file's frame at start), "gain_db" (the item's and its track's),
    "points": [(cut frame, dB)], "fade_in", "fade_out"}]}, what was left out). A loop is
    its file laid again end to end. `length(path)` is a file's length in the cut's frames
    (None: it can't be read). `beds` (ambience.laid) go on the ambience lane first, each
    run its bed laid end to end at its gain and the track's fader; `fx` (fx.laid) on the
    effects lane, each heard one at its clip. Ducking isn't here: it's computed, and a
    timeline has no place for it."""
    tracks = mix.get("tracks") or {}
    lanes: dict[str, list[dict]] = {t: [] for t in TRACKS}
    dropped = []
    if beds and length:
        from seriesmith import ambience as AMB
        for b in AMB.bed_lanes(beds, length):
            b["gain_db"] += fader(tracks, "ambience")
            lanes["ambience"].append(b)
    if fx and length:
        from seriesmith import fx as FXM
        for f in FXM.fx_lanes(fx, length):
            f["gain_db"] += fader(tracks, "effects")
            lanes["effects"].append(f)
    for item in mix.get("items") or []:
        s = place(item["in"], origins)
        e = place(item["out"], origins) if item.get("out") else None
        path = os.path.normpath(os.path.join(root, *item["path"].split("/")))
        n = length(path) if length and os.path.isfile(path) else None
        if s is None or (item.get("out") and e is None):
            dropped.append(f"{item['id']}: its shot isn't in the cut")
            continue
        if not n:
            dropped.append(f"{item['id']}: {item['path']} isn't there or has no sound")
            continue
        first = round(item.get("offset", 0.0) * fps)
        if e is None:
            e = s + max(0, n - first)
        s, e = max(0, s), min(total, e)
        if e <= s:
            dropped.append(f"{item['id']}: nothing of it falls in the cut")
            continue
        gain = item.get("gain_db", 0.0) + fader(tracks, item["track"])
        pts = sorted((f, p["db"]) for p in item.get("points") or []
                     for f in [place(p["at"], origins)] if f is not None)
        at, src_in, k = s, first, 0
        while at < e:
            run = min(e - at, n - src_in) if item.get("loop") else e - at
            if run <= 0:
                break
            lanes[item["track"]].append({
                "id": item["id"] + (f".{k + 1}" if k else ""),
                "label": item.get("label") or os.path.basename(item["path"]),
                "path": path, "start": at, "end": at + run, "in": src_in, "frames": n,
                "gain_db": gain, "points": [(f, d) for f, d in pts if at <= f < at + run],
                "fade_in": item.get("fade_in", 0) if at == s else 0,
                "fade_out": item.get("fade_out", 0) if at + run == e else 0})
            at, src_in, k = at + run, 0, k + 1
            if not item.get("loop"):
                break
    return lanes, dropped


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

def _np():
    import numpy as np                             # only a render needs it
    return np


def decode(path: str, start: float = 0.0, seconds: float | None = None,
           rate: int = RATE, channels: int = 2):
    """A file's first audio stream as float32 at `rate`, (n, channels); empty when it has
    none or can't be read."""
    np = _np()
    cmd = [*FF.tool("ffmpeg"), "-v", "error"]
    if start > 0:
        cmd += ["-ss", f"{start:.6f}"]
    cmd += ["-i", path]
    if seconds is not None:
        cmd += ["-t", f"{max(0.0, seconds):.6f}"]
    cmd += ["-vn", "-map", "0:a:0?", "-f", "f32le", "-ac", str(channels), "-ar", str(rate), "-"]
    r = subprocess.run(cmd, capture_output=True, timeout=1800)
    if r.returncode != 0 or not r.stdout:
        return np.zeros((0, channels), dtype=np.float32)
    return np.frombuffer(r.stdout, dtype=np.float32).reshape(-1, channels).copy()


def write_wav(path: str, buf) -> None:
    """24-bit PCM at RATE, written beside and moved into place."""
    tmp = F.temp_beside(path, ".wav")
    r = subprocess.run([*FF.tool("ffmpeg"), "-y", "-v", "error", "-f", "f32le", "-ac", "2",
                        "-ar", str(RATE), "-i", "-", "-c:a", "pcm_s24le", tmp],
                       input=buf.astype("float32").tobytes(), capture_output=True, timeout=1800)
    if r.returncode != 0:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise RuntimeError(f"writing {os.path.basename(path)}: "
                           f"{r.stderr.decode('utf-8', 'replace')[-300:]}")
    F.replace(tmp, path)


def _db(x):
    return 10.0 ** (x / 20.0)


def looped(src, n: int):
    """`src` repeated to `n` samples, each repeat crossfaded into the next at equal power:
    a bed's tail and head are unalike (room tone, rain), and a linear fade between two
    unalike signals dips 3 dB at every seam (docs/SOUND.md "Measured: ambience beds")."""
    np = _np()
    if len(src) >= n or len(src) == 0:
        return src[:n]
    xf = int(min(LOOP_XFADE_S * RATE, len(src) // 4))
    out = np.zeros((n, 2), dtype=np.float32)
    t = np.linspace(0.0, np.pi / 2, xf, dtype=np.float32)[:, None] if xf else None
    fade_in, fade_out = (np.sin(t), np.cos(t)) if xf else (None, None)
    pos, step = 0, len(src) - xf
    while pos < n:
        seg = src[: min(len(src), n - pos)].copy()
        if pos and xf:
            k = min(xf, len(seg))
            seg[:k] *= fade_in[:k]
        if pos + len(src) < n and xf:
            seg[-xf:] *= fade_out
        out[pos: pos + len(seg)] += seg
        pos += step
    return out


def render_item(item: dict, origins: dict, total: int, fps: float, root: str):
    """(start sample, samples) of one item laid on the cut, or (None, why) when it can't be.
    Gain, points, fades and the loop are applied; the track's fader and ducking aren't."""
    np = _np()
    start_f = place(item["in"], origins)
    if start_f is None:
        return None, f"{item['id']}: {item['in']['shot']} isn't in the cut"
    end_f = place(item["out"], origins) if item.get("out") else None
    if item.get("out") and end_f is None:
        return None, f"{item['id']}: {item['out']['shot']} isn't in the cut"
    path = os.path.normpath(os.path.join(root, *item["path"].split("/")))
    if not os.path.isfile(path):
        return None, f"{item['id']}: {item['path']} isn't there"
    start_f = max(0, start_f)
    end_f = total if end_f is None else min(total, end_f)
    if end_f is not None and end_f <= start_f:
        return None, f"{item['id']}: its out is at or before its in"
    s0 = round(start_f / fps * RATE)
    want = round(end_f / fps * RATE) - s0
    offset = item.get("offset", 0.0)
    src = decode(path, offset, None if item.get("loop") else want / RATE)
    if len(src) == 0:
        return None, f"{item['id']}: {item['path']} has no sound"
    if item.get("loop"):
        src = looped(src, want)
    elif not item.get("out"):
        want = min(want, len(src))
    buf = np.zeros((want, 2), dtype=np.float32)
    buf[: min(want, len(src))] = src[:want]
    gain = np.full(want, item.get("gain_db", 0.0), dtype=np.float32)
    pts = sorted(((place(p["at"], origins), p["db"]) for p in item.get("points") or []
                  if place(p["at"], origins) is not None), key=lambda x: x[0])
    if pts:
        xs = [round(f / fps * RATE) - s0 for f, _ in pts]
        gain += np.interp(np.arange(want), xs, [d for _, d in pts]).astype(np.float32)
    env = _db(gain)
    for key, head in (("fade_in", True), ("fade_out", False)):
        n = min(want, round(item.get(key, 0) / fps * RATE))
        if n > 0:
            ramp = np.linspace(0.0, 1.0, n, dtype=np.float32)
            if head:
                env[:n] *= ramp
            else:
                env[-n:] *= ramp[::-1]
    buf *= env[:, None]
    return s0, buf


def speech_curve(dialogue, duck: dict, rate: int = RATE):
    """How much someone is speaking in each WINDOW_S window, 0..1: the dialogue's level
    against the threshold, eased in over the attack and out over the release. `dialogue`
    is stereo (n, 2) or mono at `rate`."""
    np = _np()
    if dialogue.ndim == 1:
        dialogue = dialogue[:, None]
    ch = dialogue.shape[1]
    w = int(WINDOW_S * rate)
    n = len(dialogue) // w + (1 if len(dialogue) % w else 0)
    if n == 0:
        return np.zeros(0, dtype=np.float32)
    padded = np.zeros((n * w, ch), dtype=np.float32)
    padded[: len(dialogue)] = dialogue
    rms = np.sqrt(np.mean(padded.reshape(n, w * ch) ** 2, axis=1) + 1e-12)
    on = (20 * np.log10(rms) > duck["threshold_db"]).astype(np.float32)
    up = 1 - math.exp(-WINDOW_S * 1000 / duck["attack_ms"])
    down = 1 - math.exp(-WINDOW_S * 1000 / duck["release_ms"])
    out = np.empty(n, dtype=np.float32)
    level = 0.0
    for i in range(n):
        level += (on[i] - level) * (up if on[i] > level else down)
        out[i] = level
    return out


SPEECH_RATE = 8000                     # enough to tell speech from silence
SPEECH_STEP = 0.05                     # seconds a step of the curve the editor plays


def speech_of(layout: list[dict], fps: float, duck: dict | None = None) -> list[float]:
    """The cut's "someone is speaking" curve, as the render computes it from the dialogue
    (speech_curve), one value 0..1 per SPEECH_STEP seconds of the cut: each clip's own
    sound (layout's `sound`, from `sound_start` seconds into it) laid where the cut plays
    it, decoded small. The editor's Play all ducks with it as the export does."""
    np = _np()
    duck = {**DUCK, **(duck or {})}
    origins = shot_origins(layout)
    total = sum(x["used"] - x.get("dissolve_in", 0) for x in layout)
    n = round(total / fps * SPEECH_RATE)
    buf = np.zeros(n, dtype=np.float32)
    for x in layout:
        if not x.get("sound"):
            continue
        at = round((origins[x["id"]]["origin"] + x["trim_in"]) / fps * SPEECH_RATE)
        got = decode(x["sound"], max(0.0, x.get("sound_start", 0.0)), x["used"] / fps,
                     SPEECH_RATE, 1)[:, 0]
        a, b = max(0, at), min(n, at + len(got))
        if b > a:
            buf[a:b] += got[a - at: b - at]
    curve = speech_curve(buf, duck, rate=SPEECH_RATE)
    k = max(1, round(SPEECH_STEP / WINDOW_S))
    steps = len(curve) // k + (1 if len(curve) % k else 0)
    return [round(float(curve[i * k:(i + 1) * k].max()), 3) for i in range(steps)]


def _per_sample(curve, n: int):
    np = _np()
    w = int(WINDOW_S * RATE)
    return np.repeat(curve, w)[:n] if len(curve) else np.zeros(n, dtype=np.float32)


def measure(path: str, target: float, peak: float) -> dict | None:
    """loudnorm's measurement of a file: {"input_i", "input_tp", ...} as floats, or None."""
    r = subprocess.run([*FF.tool("ffmpeg"), "-hide_banner", "-nostats", "-i", path, "-af",
                        f"loudnorm=I={target:g}:TP={peak:g}:LRA=11:print_format=json",
                        "-f", "null", "-"], capture_output=True, timeout=1800)
    text = r.stderr.decode("utf-8", "replace")
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", text)
    if not m:
        return None
    try:
        raw = json.loads(m.group(0))
        return {k: float(v) for k, v in raw.items() if k.startswith(("input_", "target_"))}
    except ValueError:
        return None


def render(mix: dict, origins: dict, total: int, fps: float, root: str, dialogue_src: str,
           stems_dir: str, log=print, beds: list[dict] | None = None,
           fx: list[dict] | None = None) -> str:
    """Render a pass's mix for a cut of `total` frames: each track as a stem in
    `stems_dir` (dialogue.wav, effects.wav, ambience.wav, music.wav, and me.wav: all but
    the dialogue), the mix as mix.wav, brought to the loudness target. `dialogue_src` is
    the assembled cut, whose own sound is the dialogue track. `beds` (ambience.laid) are
    laid on the ambience track under its items, `fx` (fx.laid) on the effects track.
    Returns mix.wav's path."""
    np = _np()
    n = round(total / fps * RATE)
    tracks = mix.get("tracks") or {}
    duck = {**DUCK, **(mix.get("duck") or {})}
    loud = {**LOUDNESS, **(mix.get("loudness") or {})}
    solo = {k for k, t in tracks.items() if t.get("solo")}

    def audible(name: str) -> bool:
        t = tracks.get(name) or {}
        return not t.get("mute") and (not solo or name in solo)

    bufs = {name: np.zeros((n, 2), dtype=np.float32) for name in TRACKS}
    own = decode(dialogue_src)
    bufs["dialogue"][: min(n, len(own))] = own[:n]
    del own
    if beds:
        from seriesmith import ambience as AMB
        bufs["ambience"] += AMB.render_beds(beds, total, fps, log)[:n]
    if fx:
        from seriesmith import fx as FXM
        bufs["effects"] += FXM.render_fx(fx, total, fps, log)[:n]
    for item in mix.get("items") or []:
        s0, got = render_item(item, origins, total, fps, root)
        if s0 is None:
            log(f"  ! sound: {got}; left out")
            continue
        end = min(n, s0 + len(got))
        if end > s0:
            bufs[item["track"]][s0:end] += got[: end - s0]

    # ducking and regions, from the dialogue as its fader leaves it
    dial_gain = _db(fader(tracks, "dialogue"))
    speech = _per_sample(speech_curve(bufs["dialogue"] * dial_gain, duck), n)
    region_db = {k: np.full(n, np.nan, dtype=np.float32) for k in ("music", "ambience")}
    dial_db = np.zeros(n, dtype=np.float32)
    for r in mix.get("regions") or []:
        a, b = place(r["from"], origins), place(r["to"], origins)
        if a is None or b is None or b <= a:
            log("  ! sound: a region whose shots aren't in the cut, or ends before it starts; "
                "left out")
            continue
        sa, sb = max(0, round(a / fps * RATE)), min(n, round(b / fps * RATE))
        for k in ("music", "ambience"):
            if f"{k}_duck_db" in r:
                region_db[k][sa:sb] = r[f"{k}_duck_db"]
        if r.get("dialogue_db"):
            dial_db[sa:sb] += r["dialogue_db"]

    for name in TRACKS:
        t = tracks.get(name) or {}
        g = np.full(n, fader(tracks, name), dtype=np.float32)
        if name == "dialogue":
            g += dial_db
        else:
            depth = np.full(n, t.get("duck_db", DUCK_DEFAULT[name]), dtype=np.float32)
            if name in region_db:
                depth = np.where(np.isnan(region_db[name]), depth, region_db[name])
            g += depth * speech
        bufs[name] *= _db(g)[:, None]
        if not audible(name):
            bufs[name][:] = 0.0

    mixed = sum(bufs[name] for name in TRACKS)
    os.makedirs(stems_dir, exist_ok=True)
    raw_mix = os.path.join(stems_dir, "mix.wav")
    write_wav(raw_mix, mixed)
    m = measure(raw_mix, loud["target_lufs"], loud["true_peak_db"])
    gain = 0.0
    if m and math.isfinite(m.get("input_i", float("-inf"))) and m["input_i"] > -70:
        gain = loud["target_lufs"] - m["input_i"]
    lin = _db(gain)
    for name in TRACKS:
        write_wav(os.path.join(stems_dir, f"{name}.wav"), bufs[name] * lin)
    write_wav(os.path.join(stems_dir, "me.wav"),
              (bufs["effects"] + bufs["ambience"] + bufs["music"]) * lin)
    peak = (m["input_tp"] + gain) if m else None
    if peak is not None and peak > loud["true_peak_db"]:
        # the gain pushes it over the true peak: limited, a little under the ceiling
        tmp = F.temp_beside(raw_mix, ".wav")
        write_wav(tmp, mixed * lin)
        limit = _db(loud["true_peak_db"] - 0.5)
        out = F.temp_beside(raw_mix, ".wav")
        r = subprocess.run([*FF.tool("ffmpeg"), "-y", "-v", "error", "-i", tmp, "-af",
                            f"alimiter=limit={limit:.4f}:level=false:attack=5:release=50",
                            "-c:a", "pcm_s24le", out], capture_output=True, timeout=1800)
        os.remove(tmp)
        if r.returncode != 0:
            raise RuntimeError("limiting the mix: "
                               + r.stderr.decode("utf-8", "replace")[-300:])
        F.replace(out, raw_mix)
        log(f"  sound: {gain:+.1f} dB to {loud['target_lufs']:g} LUFS, limited to "
            f"{loud['true_peak_db']:g} dBTP (it peaked at {peak:+.1f})")
    else:
        write_wav(raw_mix, mixed * lin)
        if m:
            log(f"  sound: {gain:+.1f} dB to {loud['target_lufs']:g} LUFS"
                + (f", true peak {peak:+.1f} dBTP" if peak is not None else ""))
        else:
            log("  ! sound: the mix couldn't be measured; left at its level")
    return raw_mix


def mux(video: str, wav: str, total: int, fps: float) -> None:
    """Lay `wav` under `video` as its only sound (AAC), the picture copied, in place."""
    tmp = F.temp_beside(video, ".mp4")
    r = subprocess.run([*FF.tool("ffmpeg"), "-y", "-v", "error", "-i", video, "-i", wav,
                        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
                        "-b:a", "256k", "-t", f"{total / fps:.6f}", tmp],
                       capture_output=True, timeout=1800)
    if r.returncode != 0:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise RuntimeError("laying the mix under the cut: "
                           + r.stderr.decode("utf-8", "replace")[-300:])
    F.replace(tmp, video)
