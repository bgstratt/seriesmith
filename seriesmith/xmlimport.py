"""
xmlimport.py — an edit made elsewhere, as an FCP7 XML (xmeml: Premiere, DaVinci Resolve,
Final Cut 7, and seriesmith's own `assemble --xml`, nle_xml.py), into a NEW show and
episode: a shot per clip, its footage the shot's take, the cut's trims, dissolves and
fades the XML's, the other sound the episode's mix. docs/PLAN.md, "Importing an FCP7 XML
(2026-11-02)", is the design; docs/IMPORT_XML.md the user's side.

    plan(text, parent, ...)          -> the import worked out, nothing written (a dry run)
    make(text, parent, ...)          -> the show and episode written and built; the media
                                        still to make (`groups`), each a job of its own
    run_group(ep, group, report)     -> one group's takes made (a source's clips, or the
                                        gaps' black)

The rules (each said in the summary's warnings where it loses something):

- **The sequence**: the document's first sequence (a nested one, inside a clip, isn't one).
  Its rate (timebase, ntsc: 24 NTSC is 23.976) is the series' fps; its format's size the
  series' size; its name the show's (`--name` beats it).
- **The picture is V1.** A clip on V2 or above isn't imported, and is listed. (Splitting
  V1 under whatever covers it is the other choice; V1 alone is predictable and loses only
  what's listed.)
- **A clip is a shot**: `## sh010` (sh010, sh020, ...; when every clip's name opens with a
  shot id, as seriesmith's own export's do, those ids), `dur:` its length on the timeline
  in seconds, its action line the clip's name (a placeholder: no model reads the footage).
  A clip whose file isn't there is still a shot, with no take, said so.
- **A gap** on V1 (and a generator there, a disabled clip) is a shot of black, so
  everything after it stays where the edit put it.
- **A transition** between two clips (Cross Dissolve and the like) is the second one's
  `dissolve`; its frames either side are the clips' own (an edit at the transition's middle
  hides them: they're taken back). A Dip to Black is a fade out and a fade in. One at a
  clip's head or tail with nothing beside it (or aligned start-black / end-black) is its
  `fade_in` / `fade_out`.
- **A clip's sound**: an audio clip linked to it, of its own file, is the take's own sound
  (disabled: the shot plays silent; a level: its gain). An audio clip of another file
  starting where it does on A1 or A2 (a voice stem, synced sound) is the shot's sound from
  that file (cut.json's `audio`). A clip with neither plays silent: the XML had none.
- **Every other audio clip** is an item of the mix (mix.json, both passes), its file copied
  into the episode's audio/ folder: where it starts and ends anchored to the shot playing
  there, its offset into the file, its level (Audio Levels: the value, and its keyframes as
  points), its fades, `mute` when disabled. Stereo laid as two mono tracks is one item.
  Its track: by what the XML's track, file and folder are called (sfx/fx/foley: effects;
  amb/room/bed/atmos: ambience; dialogue/dx/vo/adr: dialogue; else music); a second track
  of a kind is a track of its own (the mix's track_list). The XML's levels are the mix as
  it was made, so the imported tracks' faders sit at 0 dB and they don't duck.
- **Markers**: one whose comment is "hit" (as seriesmith exports hits) is a hit of the
  mix; every other starts a sequence at the shot playing there (its name the sequence's
  id when it is one, else a comment under it). None: one sequence.
- **Media** (`media`): "handles" (the default) cuts each clip's span plus `handles` seconds
  either side (as far as the file goes) out of its source, H.264 at master quality,
  frame-accurate; "reference" makes the take the source file whole, hard-linked where the
  volume allows (no copy), else copied, never re-encoded (a source that isn't H.264 in an
  mp4 doesn't play in the editor: said per clip); "proxies" is reference, but a source the
  editor can't play gets an H.264 proxy made once (in <ep>/_proxies/) that the take plays,
  the original recorded as the take's master, which assemble and the XML export cut from.
  The cut's trims make the cut play exactly the XML's in to out.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import math
import os
import re
import xml.etree.ElementTree as ET
from urllib.parse import unquote, urlparse

from seriesmith import mix as MX
from seriesmith import takes as T
from seriesmith.core import fileio

MEDIA = ("handles", "reference", "proxies")
HANDLES_S = 1.0
PASS = "final"
EPISODE = "ep01"
LOCATION = "footage"
IMPORT_DIR = "_import"
PLAN_FILE = "xml_media.json"
PROXY_DIR = "_proxies"
AUDIO_DIR = "audio"
NTSC_BASES = {24: 23.976, 30: 29.97, 48: 47.952, 60: 59.94}
SHOT_ID = re.compile(r"^[A-Za-z]{1,4}\d{2,5}[a-z]?$")
SEQ_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,39}$")
# what a track, a file or its folder says it is (whole words, lower case)
KIND_WORDS = (
    ("effects", {"sfx", "fx", "effect", "effects", "foley", "sound effects"}),
    ("ambience", {"amb", "ambience", "ambiance", "ambient", "room", "roomtone", "room tone",
                  "bed", "beds", "atmos", "atmosphere", "tone", "wild"}),
    ("dialogue", {"dialogue", "dialog", "dx", "vo", "adr", "voice", "voices", "recording"}),
    ("music", {"music", "score", "cue", "cues", "song", "songs", "mx"}),
)


class XmlImportError(ValueError):
    """An XML that can't be imported, said as it is (the API answers it 400)."""
    http_status = 400


# ---------------------------------------------------------------------------
# reading the XML
# ---------------------------------------------------------------------------

def local_path(url: str | None, base_dir: str | None = None) -> str | None:
    """A <pathurl> as a path on this machine: file://localhost/C%3a/My%20Show/a.mov,
    file:///C:/a.mov and file:///Users/me/a.mov (decoded, a drive letter kept),
    file://server/share/a.mov as a UNC path; a plain path as it is. When it isn't there
    and `base_dir` is given, the same name beside the XML (a project moved whole)."""
    if not url:
        return None
    url = url.strip()
    if url.lower().startswith("file:"):
        u = urlparse(url)
        p = unquote(u.path)
        host = u.netloc if u.netloc.lower() not in ("", "localhost") else ""
        if re.match(r"^/[A-Za-z]:", p):
            p = p[1:]
        elif host:
            p = "//" + host + p
        path = os.path.normpath(p)
    else:
        path = os.path.normpath(unquote(url))
    if not os.path.isfile(path) and base_dir:
        beside = os.path.join(base_dir, os.path.basename(path))
        if os.path.isfile(beside):
            return os.path.abspath(beside)
    return path


def _int(el, tag: str, default: int | None = None) -> int | None:
    v = el.findtext(tag) if el is not None else None
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return default


def _rate(el) -> float | None:
    """A <rate>'s frames per second (24 with <ntsc>TRUE is 23.976)."""
    r = el.find("rate") if el is not None else None
    if r is None:
        return None
    base = _int(r, "timebase")
    if not base:
        return None
    if (r.findtext("ntsc") or "").strip().upper() == "TRUE":
        return NTSC_BASES.get(base, round(base * 1000 / 1001, 3))
    return float(base)


def _enabled(el) -> bool:
    return (el.findtext("enabled") or "TRUE").strip().upper() != "FALSE"


def _level(item) -> tuple[float | None, list[tuple[int, float]]]:
    """An audio clip's Audio Levels: (its value, [(when, value)]), linear."""
    for fx in item.iter("effect"):
        eid = (fx.findtext("effectid") or fx.findtext("name") or "").lower().replace(" ", "")
        if eid not in ("audiolevels",):
            continue
        for p in fx.iter("parameter"):
            if (p.findtext("parameterid") or p.findtext("name") or "").lower() != "level":
                continue
            try:
                value = float(p.findtext("value"))
            except (TypeError, ValueError):
                value = None
            keys = []
            for k in p.findall("keyframe"):
                try:
                    keys.append((int(round(float(k.findtext("when")))), float(k.findtext("value"))))
                except (TypeError, ValueError):
                    continue
            return value, keys
    return None, []


def _db(v: float) -> float:
    return round(max(MX.GAIN_MIN, 20.0 * math.log10(v)) if v and v > 0 else MX.GAIN_MIN, 2)


class _Files:
    """Each <file> by its id: a later clip names one an earlier one defined."""

    def __init__(self, root, base_dir: str | None):
        self.paths: dict[str, str | None] = {}
        self.names: dict[str, str] = {}
        for f in root.iter("file"):
            fid = f.get("id")
            if fid and (f.find("pathurl") is not None or f.find("name") is not None):
                self.paths[fid] = local_path(f.findtext("pathurl"), base_dir)
                self.names[fid] = f.findtext("name") or ""

    def of(self, item) -> tuple[str | None, str | None]:
        f = item.find("file")
        if f is None:
            return None, None
        fid = f.get("id")
        if f.find("pathurl") is not None:
            return fid, local_path(f.findtext("pathurl"))
        return fid, self.paths.get(fid)


def _items(track, seq_fps: float, files: _Files, audio: bool) -> list[dict]:
    """A track's clips and transitions in its order, each clip's -1 ends (in a
    transition, as Premiere writes them) resolved, and each transition put on its clips:
    a dissolve's frames given back to both (their full spans overlap by it), a fade on the
    clip it's at."""
    kids = []
    for el in track:
        if el.tag == "clipitem":
            fid, path = files.of(el)
            level, keys = _level(el) if audio else (None, [])
            st = el.find("sourcetrack")
            kids.append({
                "kind": "clip", "id": el.get("id") or "", "name": (el.findtext("name") or "").strip(),
                "enabled": _enabled(el), "start": _int(el, "start", -1), "end": _int(el, "end", -1),
                "in": _int(el, "in", 0), "out": _int(el, "out", 0),
                "fps": _rate(el) or seq_fps, "file": fid, "path": path,
                "nested": el.find("sequence") is not None,
                "links": [ln.findtext("linkclipref") for ln in el.findall("link")
                          if ln.findtext("linkclipref")],
                "channel": _int(st, "trackindex", 1) if st is not None else 1,
                "level": level, "keys": keys, "fade_in": 0, "fade_out": 0, "dissolve": 0,
                "speed": any((e.findtext("effectid") or "").lower() in ("timeremap", "speed")
                             for e in el.iter("effect"))})
        elif el.tag == "generatoritem":
            kids.append({"kind": "generator", "name": (el.findtext("name") or "generator").strip(),
                         "start": _int(el, "start", -1), "end": _int(el, "end", -1),
                         "in": _int(el, "in", 0), "out": _int(el, "out", 0), "enabled": _enabled(el)})
        elif el.tag == "transitionitem":
            fx = el.find("effect")
            kids.append({"kind": "transition", "start": _int(el, "start", 0),
                         "end": _int(el, "end", 0),
                         "align": (el.findtext("alignment") or "center").strip().lower(),
                         "name": (fx.findtext("name") if fx is not None else "") or ""})
    # the -1 ends: a clip's length is out - in; one end said, the other follows; neither,
    # from the transition before it
    for i, k in enumerate(kids):
        if k["kind"] == "transition":
            continue
        n = k["out"] - k["in"]
        prev = kids[i - 1] if i and kids[i - 1]["kind"] == "transition" else None
        if k["start"] < 0 and k["end"] >= 0:
            k["start"] = k["end"] - n
        elif k["end"] < 0 and k["start"] >= 0:
            k["end"] = k["start"] + n
        elif k["start"] < 0:
            k["start"] = prev["start"] if prev else 0
            k["end"] = k["start"] + n
    # each transition by where it is, not where the track lists it: the clip that ends
    # inside it (a), the one that starts inside it (b)
    clips = [k for k in kids if k["kind"] != "transition"]
    for t in kids:
        if t["kind"] != "transition":
            continue
        n = t["end"] - t["start"]
        if n <= 0:
            continue
        a = next((c for c in clips if t["start"] < c["end"] <= t["end"]), None)
        b = next((c for c in clips if t["start"] <= c["start"] < t["end"] and c is not a), None)
        if t["align"] == "start-black" or (b is not None and a is None):
            if b is not None:
                b["fade_in"] = max(b["fade_in"], t["end"] - b["start"])
            continue
        if t["align"] == "end-black" or (a is not None and b is None):
            if a is not None:
                a["fade_out"] = max(a["fade_out"], a["end"] - t["start"])
            continue
        if a is None or b is None:
            continue
        if "dip" in t["name"].lower():
            edit = a["end"] if a["end"] <= b["start"] else (t["start"] + t["end"]) // 2
            a["fade_out"] = max(a["fade_out"], edit - t["start"])
            b["fade_in"] = max(b["fade_in"], t["end"] - edit)
            continue
        if b["start"] > t["start"]:
            b["in"] -= b["start"] - t["start"]
            b["start"] = t["start"]
        if a["end"] < t["end"]:
            a["out"] += t["end"] - a["end"]
            a["end"] = t["end"]
        b["dissolve"] = a["end"] - b["start"]
        if audio:
            a["fade_out"], b["fade_in"] = max(a["fade_out"], n), max(b["fade_in"], n)
            b["dissolve"] = 0
    return [k for k in kids if k["kind"] != "transition"]


def read(text: str, base_dir: str | None = None) -> dict:
    """The XML's first sequence: {"name", "fps", "size", "duration", "v1": [clips and
    generators], "upper": [{"track", "name", "start", "end"}], "audio": [{..., "track"}],
    "markers": [{"name", "comment", "at"}], "warnings"}. XmlImportError for a document
    that isn't xmeml or has no sequence."""
    try:
        root = ET.fromstring(text.encode("utf-8") if isinstance(text, str) else text)
    except ET.ParseError as e:
        raise XmlImportError(f"it isn't XML: {e}") from None
    if root.tag != "xmeml":
        raise XmlImportError(f"it isn't an FCP7 XML (xmeml): its root is <{root.tag}>")
    inner = {id(s) for c in root.iter("clipitem") for s in c.iter("sequence")}
    seqs = [s for s in root.iter("sequence") if id(s) not in inner]
    if not seqs:
        raise XmlImportError("the XML has no sequence")
    seq = seqs[0]
    warnings = []
    name = (seq.findtext("name") or "").strip() or "Imported edit"
    if len(seqs) > 1:
        warnings.append(f"the XML holds {len(seqs)} sequences; only the first ({name}) is imported")
    fps = _rate(seq) or 24.0
    media = seq.find("media")
    video = media.find("video") if media is not None else None
    size = None
    sc = video.find("format/samplecharacteristics") if video is not None else None
    if sc is not None and _int(sc, "width") and _int(sc, "height"):
        size = (_int(sc, "width"), _int(sc, "height"))
    files = _Files(root, base_dir)
    vtracks = video.findall("track") if video is not None else []
    v1 = _items(vtracks[0], fps, files, False) if vtracks else []
    upper = []
    for n, tr in enumerate(vtracks[1:], start=2):
        for c in _items(tr, fps, files, False):
            if c["enabled"]:
                upper.append({"track": n, "name": c["name"], "start": c["start"], "end": c["end"]})
    audio = []
    atracks = media.find("audio").findall("track") if media is not None and media.find("audio") is not None else []
    for n, tr in enumerate(atracks, start=1):
        label = (tr.findtext("name") or next((v for k, v in tr.attrib.items()
                                              if k.lower().endswith("trackname")), "") or "").strip()
        for c in _items(tr, fps, files, True):
            if c["kind"] == "clip":
                c["track"], c["track_name"] = n, label
                audio.append(c)
    markers = []
    for m in seq.findall("marker"):
        at = _int(m, "in", -1)
        if at is not None and at >= 0:
            markers.append({"name": (m.findtext("name") or "").strip(),
                            "comment": (m.findtext("comment") or "").strip(), "at": at})
    return {"name": name, "fps": fps, "size": size, "duration": _int(seq, "duration", 0),
            "v1": v1, "upper": upper, "audio": audio, "markers": sorted(markers, key=lambda m: m["at"]),
            "warnings": warnings}


# ---------------------------------------------------------------------------
# the sources
# ---------------------------------------------------------------------------

def probe_source(path: str) -> dict:
    """{"fps", "frames", "width", "height", "audio", "playable", "codec"} of a source;
    {"error"} when ffprobe can't read it."""
    from seriesmith import ff as FF
    from seriesmith import takeimport as TI
    try:
        out = FF.probe_json(path, "-show_streams", "-show_format", timeout=120)
    except (FF.FFError, OSError) as e:
        return {"error": str(e)[-200:]}
    streams = out.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    if v is None:
        return {"error": "it has no video"}
    num, _, den = str(v.get("r_frame_rate") or v.get("avg_frame_rate") or "24/1").partition("/")
    try:
        fps = float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        fps = 24.0
    try:
        frames = int(v.get("nb_frames") or 0)
    except ValueError:
        frames = 0
    if not frames:
        try:
            dur = float(v.get("duration") or (out.get("format") or {}).get("duration") or 0)
        except ValueError:
            dur = 0.0
        frames = int(round(dur * fps))
    try:
        playable = TI.playable(path)
    except TI.TakeImportError:
        playable = False
    return {"fps": round(fps, 3), "frames": frames, "width": int(v.get("width") or 0),
            "height": int(v.get("height") or 0), "codec": v.get("codec_name") or "?",
            "audio": any(s.get("codec_type") == "audio" for s in streams), "playable": playable}


# ---------------------------------------------------------------------------
# working the import out
# ---------------------------------------------------------------------------

def _tc(frame: int, fps: float) -> str:
    s = frame / fps
    return f"{int(s // 3600):02d}:{int(s % 3600 // 60):02d}:{s % 60:06.3f}"


def _kind_of(words: str) -> str | None:
    w = " " + re.sub(r"[^a-z0-9]+", " ", words.lower()) + " "
    for kind, names in KIND_WORDS:
        if any(f" {n} " in w for n in names):
            return kind
    return None


def _action(name: str) -> str:
    """A clip's name as an action line the script reads as one: one that would read as
    a field, dialogue, a heading or a comment opens with "Clip"."""
    text = " ".join((name or "").split()) or "an untitled clip"
    if (text.startswith(("=", "#", "//")) or re.match(r"^[a-z_]+\s*:", text)
            or re.match(r"^[A-Z][A-Z0-9_ '\-]*?\s*(?:\([^)]*\))?\s*:", text)):
        return f"Clip {text}"
    return text


def show_folder(title: str) -> str:
    """A show's folder name from its title, as clips.new_project makes one."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", " ".join(str(title or "").split())).strip("._-")


def _lay_shots(ed: dict, warnings: list[str]) -> list[dict]:
    """V1 as the cut's shots in timeline order, a gap (a generator, a disabled clip) a
    shot of black, so a shot's full span is where the XML has it."""
    fps = ed["fps"]
    clips = sorted((c for c in ed["v1"] if c["end"] > c["start"]), key=lambda c: c["start"])
    out, at = [], 0
    for c in clips:
        black = c["kind"] != "clip" or not c["enabled"]
        if black:
            what = (f"a generator ({c['name']})" if c["kind"] != "clip"
                    else f"{c['name']} (disabled)")
            warnings.append(f"V1 at {_tc(c['start'], fps)}: {what} is black")
            continue
        if c["start"] > at:
            out.append({"black": True, "start": at, "end": c["start"]})
        elif c["start"] < at and not c["dissolve"] and out:
            prev = out[-1]
            cut = prev["end"] - c["start"]
            if not prev.get("black"):
                prev["out"] -= cut
            prev["end"] = c["start"]
            warnings.append(f"{c['name']} overlaps the clip before it with no transition: "
                            f"that one ends where it starts")
        out.append(dict(c, black=False))
        at = max(at, c["end"])
    for s in out:
        if s["black"]:
            warnings.append(f"a {s['end'] - s['start']}-frame gap at {_tc(s['start'], fps)}: "
                            f"a shot of black")
    return out


def _ids(shots: list[dict]) -> None:
    """Each shot's id: its clip's own (sh010) when every clip's name opens with a shot id,
    unique; else sh010, sh020, ... in order, black included."""
    firsts = [(s["name"].split() or [""])[0] for s in shots if not s["black"]]
    own = (firsts and all(SHOT_ID.match(f) for f in firsts)
           and len({f.lower() for f in firsts}) == len(firsts))
    gap = 0
    for n, s in enumerate(shots, start=1):
        if own and not s["black"]:
            s["id"] = s["name"].split()[0]
        elif own:
            gap += 1
            s["id"] = f"gap{gap:02d}"
        else:
            s["id"] = f"sh{n * 10:03d}"


def _sequences(shots: list[dict], markers: list[dict]) -> tuple[list[dict], list[dict]]:
    """(the script's sequences [{"id", "note", "shots": [ids]}], the hits [{"name", "at"}]).
    A marker opens a sequence at the shot playing at its frame (the next one when it's in
    that shot's second half); one whose comment is "hit" is a hit."""
    hits = [m for m in markers if m["comment"].lower() == "hit"]
    breaks: dict[int, str] = {}
    for m in markers:
        if m in hits:
            continue
        k = next((i for i, s in enumerate(shots) if s["start"] <= m["at"] < s["end"]),
                 len(shots) - 1 if shots and m["at"] >= shots[-1]["end"] else 0)
        s = shots[k] if shots else None
        if s and m["at"] > (s["start"] + s["end"]) / 2 and k + 1 < len(shots):
            k += 1
        breaks.setdefault(k, m["name"])
    seqs, used = [], set()
    for i, s in enumerate(shots):
        if i == 0 or i in breaks:
            label = breaks.get(i, "")
            sid = label if SEQ_ID.match(label or "") and label.lower() not in used else ""
            if not sid:
                n = len(seqs) + 1
                while f"sq{n:02d}" in used:
                    n += 1
                sid = f"sq{n:02d}"
            used.add(sid.lower())
            seqs.append({"id": sid, "note": "" if sid == label else label, "shots": []})
        seqs[-1]["shots"].append(s["id"])
    return seqs, hits


def _media(shots: list[dict], probes: dict, mode: str, handles: float, fps: float,
           warnings: list[str]) -> None:
    """Each shot's take as it will be made (`take`: {"first", "frames"} of its source) and
    the cut's trims, so the cut plays the XML's in to out."""
    for s in shots:
        s["trim_in"] = s["trim_out"] = 0
        if s["black"]:
            continue
        pr = probes.get(s["path"]) if s["path"] else None
        if s.get("nested"):
            s["missing"] = "it's a nested sequence, not a file"
        elif not s["path"] or not os.path.isfile(s["path"]):
            s["missing"] = f"its file isn't there ({s['path'] or 'no path in the XML'})"
        elif not pr or pr.get("error"):
            s["missing"] = f"its file can't be read ({(pr or {}).get('error', '?')})"
        if s.get("missing"):
            warnings.append(f"{s['id']} ({s['name']}): {s['missing']}; the shot has no take")
            continue
        sfps, total = pr["fps"], pr["frames"]
        same = abs(s["fps"] - sfps) < 0.01
        k_in = s["in"] if same else round(s["in"] / s["fps"] * sfps)
        k_out = s["out"] if same else round(s["out"] / s["fps"] * sfps)
        if k_in < 0:
            warnings.append(f"{s['id']}: its dissolve reaches {-k_in} frame(s) before its file starts")
            k_in = 0
        if total and k_out > total:
            warnings.append(f"{s['id']}: the XML plays {k_out - total} frame(s) past the end of "
                            f"{os.path.basename(s['path'])}")
            k_out = total
        if s.get("speed") or abs((k_out - k_in) / sfps - (s["end"] - s["start"]) / fps) > 1.5 / fps:
            warnings.append(f"{s['id']}: a speed change isn't carried (it plays at its own speed)")
        if mode == "handles":
            h = round(handles * sfps)
            t0, t1 = max(0, k_in - h), min(total or k_out + h, k_out + h)
        else:
            t0, t1 = 0, total or k_out
        # head: the take's first frame the cut plays (the shot's keyframe is taken there)
        s["take"] = {"first": t0, "frames": t1 - t0, "head": k_in - t0}
        conv = (lambda n: n) if abs(sfps - fps) < 0.01 else (lambda n: round(n / sfps * fps))
        s["trim_in"], s["trim_out"] = conv(k_in - t0), conv(t1 - k_out)


def _sounds(shots: list[dict], audio: list[dict], fps: float) -> tuple[list[dict], list[str]]:
    """Each shot's sound ("sound": "own" | {"file", "at", "in", "gain"} | None, and
    "own_gain", "own_off") from the audio clips that are its; the rest, one per stereo
    pair, for the mix; and what's said about them."""
    said = []
    by_id = {s["id_xml"]: s for s in shots if not s["black"] and s.get("id_xml")}
    pic = [s for s in shots if not s["black"]]
    rest, seen = [], set()
    for a in sorted(audio, key=lambda a: (a["track"], a["start"])):
        key = (os.path.normcase(a["path"] or a["name"]), a["start"], a["end"], a["in"])
        if key in seen:
            continue                                   # the other channel of a pair
        seen.add(key)
        owner = next((by_id[x] for x in a["links"] if x in by_id), None)
        if owner is None and a["path"]:
            owner = next((s for s in pic if s["path"] and os.path.normcase(s["path"])
                          == os.path.normcase(a["path"]) and a["start"] < s["end"]
                          and a["end"] > s["start"] and not a["links"]), None)
        if owner is not None and owner["path"] and a["path"] and \
                os.path.normcase(owner["path"]) == os.path.normcase(a["path"]):
            if owner.get("sound") is None:
                owner["sound"] = "own"
                owner["own_on"] = a["enabled"]
                if a["level"] is not None and abs(a["level"] - 1.0) > 1e-4:
                    owner["own_gain"] = a["level"]
                if a["start"] - a["in"] != owner["start"] - owner["in"] and a["fps"] == owner["fps"]:
                    said.append(f"{owner['id']}: its sound is slipped against its picture; the "
                                f"take plays them as the file has them")
            continue
        if owner is None and a["track"] <= 2 and a["path"]:
            owner = next((s for s in pic if s.get("sound") is None and s["start"] <= a["start"]
                          < s["start"] + max(1, (s["end"] - s["start"]) // 2)
                          and abs(a["start"] - (s["start"] + s["dissolve"] // 2)) <= 1
                          and a["end"] <= s["end"] + 1), None)
            if owner is not None:
                owner["sound"] = {"file": a["path"], "at": a["start"] - a["in"],
                                  "gain": a["level"] if a["level"] is not None else 1.0,
                                  "on": a["enabled"]}
                continue
        rest.append(a)
    return rest, said


def _audio_name(path: str, taken: dict) -> str:
    """The file's name in audio/; one whose name another has is named by its folder too
    (sound/fx/final/sh020/t01.wav: sh020_t01.wav), then a number."""
    key = os.path.normcase(os.path.abspath(path))
    if key in taken:
        return taken[key]
    used = {v.lower() for v in taken.values()}
    stem, ext = os.path.splitext(os.path.basename(path))
    folder = re.sub(r"[^A-Za-z0-9._-]+", "_", os.path.basename(os.path.dirname(os.path.abspath(path))))
    name = stem + ext
    if name.lower() in used and folder:
        stem = f"{folder}_{stem}"
        name = stem + ext
    n = 1
    while name.lower() in used:
        n += 1
        name = f"{stem}_{n}{ext}"
    taken[key] = name
    return name


def _origins(shots: list[dict]) -> dict:
    """Where each shot's take sits on the timeline (mix.shot_origins' form). A shot whose
    file is missing isn't one: an anchor on it would drop its item from every cut until
    it has a take, so its frames are the shot's before it."""
    return {s["id"]: {"origin": s["start"] - s["trim_in"], "first": s["trim_in"],
                      "used": s["end"] - s["start"]} for s in shots if not s.get("missing")}


def _mix(rest: list[dict], shots: list[dict], hits: list[dict], fps: float,
         files: dict, warnings: list[str]) -> dict | None:
    """The mix (stored form) from the audio clips that aren't a shot's own."""
    origins = _origins(shots)
    lanes: dict[int, list[dict]] = {}
    for a in rest:
        if not a["path"] or not os.path.isfile(a["path"]):
            warnings.append(f"A{a['track']} {a['name']} at {_tc(a['start'], fps)}: its file "
                            f"isn't there ({a['path'] or 'no path'}); left out")
            continue
        if a.get("nested"):
            continue
        lanes.setdefault(a["track"], []).append(a)
    # each lane's kind: its track's name, else most of its clips' file and folder names
    tracks: list[dict] = []
    ids_of: dict[int, str] = {}
    count: dict[str, int] = {}
    for lane in sorted(lanes):
        items = lanes[lane]
        kind = _kind_of(items[0].get("track_name") or "")
        if kind is None:
            votes: dict[str, int] = {}
            for a in items:
                parts = os.path.normpath(a["path"]).split(os.sep)[-3:]
                k = _kind_of(" ".join(parts) + " " + a["name"])
                if k:
                    votes[k] = votes.get(k, 0) + 1
            kind = max(votes, key=votes.get) if votes else "music"
        count[kind] = count.get(kind, 0) + 1
        if count[kind] == 1:
            tid = kind
        else:
            tid = f"{kind}{count[kind]}"
            if len(MX.TRACKS) + len(tracks) >= MX.MAX_TRACKS:
                tid = kind
            else:
                label = items[0].get("track_name") or f"{MX.LABELS[kind]} {count[kind]}"
                tracks.append({"id": tid, "kind": kind, "label": label[:40]})
        ids_of[lane] = tid
    items, n = [], 0
    for lane in sorted(lanes):
        for a in sorted(lanes[lane], key=lambda a: a["start"]):
            n += 1
            ina, outa = MX.anchor_at(a["start"], origins), MX.anchor_at(a["end"], origins)
            if ina is None or outa is None:
                continue
            item = {"id": f"x{n:03d}", "track": ids_of[lane],
                    "path": f"{AUDIO_DIR}/{_audio_name(a['path'], files)}",
                    "in": ina, "out": outa, "label": a["name"][:120] or None}
            if a["in"]:
                item["offset"] = round(a["in"] / a["fps"], 4)
            base = a["level"] if a["level"] is not None else (a["keys"][0][1] if a["keys"] else 1.0)
            if abs(_db(base)) > 1e-6:
                item["gain_db"] = min(MX.GAIN_MAX, _db(base))
            src = a["in"] - a["start"]
            pts = []
            for when, v in a["keys"]:
                at = MX.anchor_at(when - src, origins)
                if at is not None:
                    pts.append({"at": at, "db": max(MX.GAIN_MIN, min(MX.GAIN_MAX, round(_db(v) - _db(base), 2)))})
            if pts:
                item["points"] = pts
            for k in ("fade_in", "fade_out"):
                if a[k]:
                    item[k] = min(a[k], MX.FADE_MAX)
            if not a["enabled"]:
                item["mute"] = True
            items.append({k: v for k, v in item.items() if v is not None})
    hit_list = []
    for i, h in enumerate(hits, start=1):
        at = MX.anchor_at(h["at"], origins)
        if at is not None:
            hit_list.append({"id": f"h{i}", "name": h["name"] or f"hit {i}", "at": at})
    if not items and not hit_list:
        return None
    used = {it["track"] for it in items}
    mix: dict = {"items": items}
    # the XML's levels are the mix as it was made: the faders at 0 dB, no ducking
    tr = {}
    for tid in used:
        kind = next((t["kind"] for t in tracks if t["id"] == tid), tid)
        if kind != "dialogue":
            tr[tid] = {"gain_db": 0.0, "duck_db": 0.0} if MX.GAIN_DEFAULT[kind] else {"duck_db": 0.0}
    if tr:
        mix["tracks"] = tr
    if hit_list:
        mix["hits"] = hit_list
    if tracks:
        mix["track_list"] = [{"id": k, "kind": k} for k in MX.TRACKS] + tracks
    return MX.check(mix)


def _cut(shots: list[dict], files: dict, fps: float) -> list[dict]:
    """The final pass's cut.json list."""
    out = []
    for s in shots:
        e: dict = {"shot": s["id"]}
        if s.get("missing"):
            e["note"] = f"from the XML: {s['name']}: {s['missing']}"
            out.append(e)
            continue
        e["take"] = 1
        for k in ("trim_in", "trim_out", "fade_in", "fade_out", "dissolve"):
            if s.get(k):
                e[k] = s[k]
        snd = s.get("sound")
        if s["black"]:
            pass
        elif snd == "own":
            if not s.get("own_on", True):
                e["audio"] = {"source": "none"}
            elif s.get("own_gain") is not None:
                e["audio"] = {"source": "take", "shot": s["id"], "take": 1, "pass": PASS,
                              "gain": round(min(T.GAIN_MAX, s["own_gain"]), 4)}
        elif isinstance(snd, dict):
            if not snd["on"]:
                e["audio"] = {"source": "none"}
            else:
                # where the file's first frame sits from the clip's first used frame (its
                # full start, as assemble lays it): later is an offset, earlier a start
                at = (snd["at"] - s["start"]) / fps
                a = {"source": "file", "path": f"{AUDIO_DIR}/{_audio_name(snd['file'], files)}"}
                if at < 0:
                    a["start"] = round(-at, 4)
                elif at > 0:
                    a["offset"] = round(at, 4)
                if abs(snd["gain"] - 1.0) > 1e-4:
                    a["gain"] = round(min(T.GAIN_MAX, snd["gain"]), 4)
                e["audio"] = T.audio_spec(a, PASS)
        else:
            e["audio"] = {"source": "none"}
        out.append(e)
    return out


def _script(title: str, name: str, xml_name: str, seqs: list[dict], shots: list[dict],
            fps: float) -> str:
    by = {s["id"]: s for s in shots}
    lines = [f"= {name}  {title}".rstrip(), "",
             f"// Imported from {xml_name} (an FCP7 XML) on {_dt.date.today().isoformat()}:",
             "// each shot is a clip of the edit, its take the clip's footage. Say what happens",
             "// in each in place of its clip's name before rendering it again.", ""]
    for q in seqs:
        lines.append(f"# {q['id']}  {LOCATION}")
        if q["note"]:
            lines.append(f"// {q['note']}")
        lines.append("")
        for sid in q["shots"]:
            s = by[sid]
            lines.append(f"## {sid}")
            lines.append(f"dur: {round((s['end'] - s['start']) / fps, 3):g}")
            if s["black"]:
                lines.append("Black.")
            else:
                lines.append(_action(s["name"]))
                src = os.path.basename(s["path"]) if s["path"] else "no file"
                lines.append(f"// {s['name']}: {src} {_tc(s['in'], s['fps'])}-{_tc(s['out'], s['fps'])}")
            lines.append("")
    return "\n".join(lines)


def _series(title: str, ident: str, fps: float, size: tuple[int, int]) -> dict:
    # the footage's own size, on `hold` (any even size, any length, no model): a generative
    # model's grid (H3's 32, LTX's 64) or its longest shot would refuse an edit's clips; a
    # shot rendered again picks its own model, whose rules then apply to that shot. The
    # proxy pass is half of it (its cut plays the final takes, scaled)
    w, h = (max(2, v - v % 2) for v in size)
    pw, ph = (max(2, v // 2 - (v // 2) % 2) for v in (w, h))
    return {"series": {"id": ident, "title": title, "fps": int(fps) if fps == int(fps) else fps,
                       "width": w, "height": h, "target": "hold"},
            "proxy": {"width": pw, "height": ph},
            "style": {"look": "live-action footage, as it was shot (imported from an edit: say "
                              "its look here before rendering a shot again)"},
            "subjects": {},
            "locations": {LOCATION: {"description": "the place the imported footage shows"}},
            "audio": {"mode": "generate"}}


def _groups(shots: list[dict], probes: dict, mode: str, size: tuple[int, int],
            fps: float) -> list[dict]:
    """The media still to make, a job each: one per source (its clips), the gaps' black."""
    groups: dict[str, dict] = {}
    black = []
    for s in shots:
        if s.get("missing"):
            continue
        if s["black"]:
            black.append({"shot": s["id"], "frames": s["end"] - s["start"], "head": 0})
            continue
        key = os.path.normcase(os.path.abspath(s["path"]))
        pr = probes[s["path"]]
        g = groups.setdefault(key, {"kind": "source", "source": os.path.abspath(s["path"]),
                                    "mode": mode, "fps": pr["fps"], "playable": pr["playable"],
                                    "clips": []})
        g["clips"].append({"shot": s["id"], "name": s["name"], **s["take"]})
    out = list(groups.values())
    if black:
        out.append({"kind": "black", "fps": fps, "size": list(size), "clips": black})
    for i, g in enumerate(out):
        g["index"] = i
    return out


def _next_series(raw: dict, fps: float, size: tuple[int, int], warnings: list[str]) -> dict:
    """A next episode's series config: its neighbour's (the cast, look, voices carry over)
    at the edit's rate and size, on `hold`, with the footage's location."""
    raw = json.loads(json.dumps(raw))
    fresh = _series("", "", fps, size)
    s = raw["series"]
    was = (s.get("fps"), s.get("width"), s.get("height"))
    for k in ("fps", "width", "height", "target"):
        s[k] = fresh["series"][k]
    if was[0] is not None and was != (s["fps"], s["width"], s["height"]):
        warnings.append(f"the show is {was[1]}x{was[2]} at {was[0]} fps; this episode is the "
                        f"edit's, {s['width']}x{s['height']} at {s['fps']} fps")
    raw["proxy"] = dict(raw.get("proxy") or {}, **fresh["proxy"])
    locs = raw.get("locations")
    if not isinstance(locs, dict):
        locs = raw["locations"] = {}
    locs.setdefault(LOCATION, fresh["locations"][LOCATION])
    return raw


def plan(text: str, parent: str, xml_name: str = "edit.xml", name: str | None = None,
         media: str = "handles", handles: float = HANDLES_S, base_dir: str | None = None,
         in_show: bool = False, allow=None) -> dict:
    """The import worked out, nothing written: the summary (what make answers), with
    `_shots`, `_files` etc. for make. `in_show`: `parent` is a show's folder and the edit
    its next episode (ep03 after ep02), the series config its newest episode's (else the
    edit's own); `name` then titles the episode. `allow(path)`: whether a media file the XML
    names may be used (from another device, one in the project folders); one that may not is
    left out as missing. XmlImportError for an XML or an option that can't be."""
    if media not in MEDIA:
        raise XmlImportError(f"media must be one of {', '.join(MEDIA)}, not {media!r}")
    try:
        handles = float(handles)
    except (TypeError, ValueError):
        raise XmlImportError(f"handles must be seconds, not {handles!r}") from None
    if not 0 <= handles <= 60:
        raise XmlImportError("handles must be 0 to 60 seconds")
    ed = read(text, base_dir)
    warnings = list(ed["warnings"])
    if allow is not None:
        refused = set()
        for c in ed["v1"] + ed["audio"]:
            if c.get("path") and not allow(c["path"]):
                refused.add(c["path"])
                c["path"] = None
        for p in sorted(refused):
            warnings.append(f"{p} is outside the project folders, so it isn't used from another "
                            "device: import the XML on the PC running seriesmith to bring it in")
    fps = ed["fps"]
    shots = _lay_shots(ed, warnings)
    if not any(not s["black"] for s in shots):
        raise XmlImportError("the sequence has no clips on V1")
    for s in shots:
        if not s["black"]:
            s["id_xml"] = s["id"]
    _ids(shots)
    probes = {}
    for s in shots:
        p = s.get("path")
        if not s["black"] and p and p not in probes and os.path.isfile(p):
            probes[p] = probe_source(p)
    size = ed["size"] or next(((pr["width"], pr["height"]) for pr in probes.values()
                               if pr.get("width")), (1920, 1080))
    _media(shots, probes, media, handles, fps, warnings)
    rest, said = _sounds(shots, ed["audio"], fps)
    warnings += said
    for u in ed["upper"]:
        warnings.append(f"V{u['track']}: {u['name']} at {_tc(u['start'], fps)} isn't imported "
                        f"(the picture is V1's)")
    seqs, hits = _sequences(shots, ed["markers"])
    files: dict = {}
    mix = _mix(rest, shots, hits, fps, files, warnings)
    cut = _cut(shots, files, fps)
    title = " ".join((name or ed["name"]).split())
    if in_show:
        from seriesmith import source as S
        tpl = S.episode_template(parent) if parent else {"name": EPISODE, "series": None, "from": None}
        episode, show = tpl["name"], os.path.basename(os.path.normpath(parent or "")) or None
        ep = os.path.join(os.path.abspath(parent), episode) if parent else None
    else:
        tpl, episode = None, EPISODE
        show = show_folder(title)
        if not show:
            raise XmlImportError("name the show: letters or digits")
        ep = os.path.join(os.path.abspath(parent), show, EPISODE) if parent else None
    silent = [s["id"] for s in shots if not s["black"] and not s.get("missing") and s.get("sound") is None]
    if silent:
        warnings.append(f"{len(silent)} clip(s) have no sound in the XML, so their shots play "
                        f"silent: {', '.join(silent[:8])}{' ...' if len(silent) > 8 else ''}")
    groups = _groups(shots, probes, media, size, fps)
    clips = []
    for s in shots:
        if s["black"]:
            continue
        pr = probes.get(s["path"]) or {}
        row = {"shot": s["id"], "name": s["name"], "source": s["path"],
               "dur": round((s["end"] - s["start"]) / fps, 3), "trim_in": s["trim_in"],
               "trim_out": s["trim_out"], "missing": s.get("missing")}
        if not s.get("missing"):
            row["codec"] = pr.get("codec")
            if media == "proxies" and not pr.get("playable"):
                row["proxy"] = True
            elif media == "reference" and not pr.get("playable"):
                row["plays"] = False
                row["note"] = (f"{pr.get('codec')} in {os.path.splitext(s['path'])[1] or 'its file'}: "
                               f"it won't play in the editor (assemble and the XML export still read it)")
        clips.append(row)
    ident = re.sub(r"[^a-z0-9_]+", "_", (show or "").lower()).strip("_") or "imported"
    series = _next_series(json.loads(tpl["series"]), fps, size, warnings) \
        if tpl and tpl.get("series") else _series(title, ident, fps, size)
    out = {
        "sequence": ed["name"], "title": title, "show": show, "episode": episode,
        "in_show": bool(in_show), "from": tpl.get("from") if tpl else None, "ep": ep,
        "fps": fps, "size": list(size), "media": media, "handles": handles if media == "handles" else None,
        "shots": len(shots), "black": sum(1 for s in shots if s["black"]),
        "takes": sum(len(g["clips"]) for g in groups),
        "missing": [c["shot"] for c in clips if c["missing"]],
        "sequences": [q["id"] for q in seqs],
        "audio_items": len((mix or {}).get("items") or []),
        "hits": len((mix or {}).get("hits") or []),
        "tracks": [t["id"] for t in MX.track_list(mix) if any(i["track"] == t["id"] for i in (mix or {}).get("items") or [])],
        "proxies": [c["shot"] for c in clips if c.get("proxy")],
        "unplayable": [c["shot"] for c in clips if c.get("plays") is False],
        "clips": clips, "warnings": warnings,
        "_shots": shots, "_seqs": seqs, "_files": files, "_mix": mix, "_cut": cut,
        "_groups": groups, "_series": series,
        "_script": _script(title, episode, xml_name, seqs, shots, fps), "_xml_name": xml_name,
    }
    return out


def public(summary: dict) -> dict:
    """The summary without its working parts."""
    return {k: v for k, v in summary.items() if not k.startswith("_")}


# ---------------------------------------------------------------------------
# writing it
# ---------------------------------------------------------------------------

def make(text: str, parent: str, xml_name: str = "edit.xml", name: str | None = None,
         media: str = "handles", handles: float = HANDLES_S, base_dir: str | None = None,
         in_show: bool = False, allow=None) -> dict:
    """The show and its episode (`in_show`: the show's next episode) written and built:
    series config, script, cut.json,
    mix.json (both passes), the mix's files in audio/, the XML kept in _import/, the media
    plan (_import/xml_media.json) whose `groups` are still to run (run_group). The
    summary, with `groups` (each {"index", "kind", "source", "clips"}) and `build`.
    SourceError 409 when the show's (or the episode's) folder is already there."""
    from seriesmith import edit as E
    from seriesmith import source as S
    if not parent or not os.path.isdir(parent):
        raise XmlImportError(f"no folder at {parent!r} to import into")
    p = plan(text, parent, xml_name, name, media, handles, base_dir, in_show, allow)
    if in_show:
        S.new_episode(parent, p["episode"], title=p["title"],
                      series=json.dumps(p["_series"], indent=2), script=p["_script"])
    else:
        show = S.check_name(p["show"])
        if os.path.exists(os.path.join(parent, show)):
            raise S.SourceError(409, f"there is already a {show} folder in {parent}")
        S.new_episode(parent, EPISODE, title=p["title"], show=show,
                      series=json.dumps(p["_series"], indent=2), script=p["_script"])
    ep = p["ep"]
    fileio.write_text(os.path.join(ep, IMPORT_DIR, os.path.basename(xml_name) or "edit.xml"),
                      text if isinstance(text, str) else text.decode("utf-8", "replace"))
    for src, nm in p["_files"].items():
        fileio.copy(src, os.path.join(ep, AUDIO_DIR, nm))
    cut = p["_cut"]
    proxy = [dict(e, **({"pass": PASS} if e.get("take") else {})) for e in cut]
    T.save_cut(ep, {PASS: cut, "proxy": proxy})
    if p["_mix"]:
        for ps in MX.PASSES:
            MX.write(ep, ps, p["_mix"])
    fileio.write_json(os.path.join(ep, IMPORT_DIR, PLAN_FILE),
                      {"xml": xml_name, "media": media, "groups": p["_groups"]})
    out = public(p)
    out["build"] = E.build_episode(ep)
    out["groups"] = [{"index": g["index"], "kind": g["kind"], "source": g.get("source"),
                      "clips": len(g["clips"])} for g in p["_groups"]]
    return out


def load_group(ep: str, index: int) -> dict:
    data = fileio.read_json(os.path.join(ep, IMPORT_DIR, PLAN_FILE)) or {}
    groups = data.get("groups") or []
    if not 0 <= index < len(groups):
        raise LookupError(f"{ep} has no import media group {index}")
    return groups[index]


def group_title(ep: str, g: dict) -> str:
    epn = os.path.basename(os.path.dirname(os.path.normpath(ep)))
    if g["kind"] == "black":
        return f"{epn} import: black ({len(g['clips'])})"
    what = "proxy" if g["mode"] == "proxies" and not g["playable"] else "import"
    return f"{epn} {what}: {os.path.basename(g['source'])} ({len(g['clips'])})"


def proxy_path(ep: str, source: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", os.path.splitext(os.path.basename(source))[0])[:60]
    h = hashlib.sha1(os.path.normcase(os.path.abspath(source)).encode("utf-8")).hexdigest()[:8]
    return os.path.join(ep, PROXY_DIR, f"{stem}_{h}.mp4")


def ensure_proxy(ep: str, source: str) -> tuple[str, bool]:
    """The source's proxy in <ep>/_proxies/, made unless one made from the source as it
    is now (its size and mtime) is there. (path, made)."""
    from seriesmith import takeimport as TI
    path = proxy_path(ep, source)
    rec_path = path[:-4] + ".json"
    want = TI.stamp(source)
    rec = fileio.read_json(rec_path) or {}
    if os.path.isfile(path) and rec.get("source") == want:
        return path, False
    TI.encode_proxy(source, path)
    fileio.write_json(rec_path, {"source": want, "made": T.now()})
    return path, True


def keyframe(ep: str, shot: str, mp4: str, frame: int, fps: float) -> str | None:
    """The shot's first keyframe (refs/shots/<shot>/first.png) as frame `frame` of its
    take, the first the cut plays, unless it has one: what `hold` (the imported series'
    model) holds, and where an image-to-video model starts when the shot is rendered
    again. The path, or None when there was one or ffmpeg couldn't."""
    import subprocess
    from seriesmith import ff as FF
    dst = os.path.join(ep, "refs", "shots", T.safe_id(shot), "first.png")
    if os.path.isfile(dst):
        return None
    tmp = fileio.temp_beside(dst, ".png")
    try:
        subprocess.run([*FF.tool("ffmpeg"), "-y", "-v", "error", "-ss",
                        f"{max(0.0, (frame - 0.25) / fps):.6f}", "-i", mp4, "-frames:v", "1", tmp],
                       check=True, capture_output=True, timeout=300)
        fileio.replace(tmp, dst)
        return dst
    except (subprocess.SubprocessError, OSError):
        try:
            os.remove(tmp)
        except OSError:
            pass
        return None


def _pin(ep: str, shot: str, take: int) -> None:
    """The cut's entries for `shot` on take `take` (the import pins take 1; another
    number when the shot had one already)."""
    if take == 1:
        return
    data = T.load_cut(ep)
    for ps in T.PASSES:
        for e in data.get(ps) or []:
            if e.get("shot") == shot and e.get("take") is not None:
                e["take"] = take
    T.save_cut(ep, data)


def run_group(ep: str, g: dict, report=None, on_take=None) -> dict:
    """A group's takes made, each `shot`'s next take in the final pass (one made by an
    earlier run of it, finished, is kept). report(progress=0..1, line=...) as it goes;
    on_take(take) for each. {"made", "kept", "failed": [why]}."""
    from seriesmith import takeimport as TI
    report = report or (lambda **k: None)
    made, kept, failed = 0, 0, []
    n = len(g["clips"])
    proxy = None
    if g["kind"] == "source" and g["mode"] == "proxies" and not g["playable"]:
        report(progress=0.0, line=f"making the proxy of {os.path.basename(g['source'])}")
        proxy, fresh = ensure_proxy(ep, g["source"])
        report(progress=0.5, line=("made " if fresh else "kept ") + os.path.relpath(proxy, ep))
    for i, c in enumerate(g["clips"]):
        old = T.get_take(ep, PASS, c["shot"], 1)
        if old is not None and old.usable and (old.sidecar or {}).get("source") == "imported":
            kept += 1
            continue
        try:
            if g["kind"] == "black":
                def fill(mp4, c=c):
                    TI.encode_black(mp4, c["frames"], g["fps"], tuple(g["size"]))
                    return [f"black, {c['frames']} frames (a gap in the edit)"]
                t = TI.import_made(ep, PASS, c["shot"], fill, "a gap in the edit", {"source_path": None})
            else:
                src = g["source"]
                fields = {}
                if g["mode"] == "handles":
                    def fill(mp4, c=c):
                        TI.encode_span(src, mp4, c["first"], c["frames"], g["fps"])
                        return [f"frames {c['first']}-{c['first'] + c['frames']} of {src} "
                                f"(the clip and its handles), H.264 at master quality"]
                elif proxy:
                    def fill(mp4):
                        how = TI.link_or_copy(proxy, mp4)
                        return [f"the proxy of {src} ({how}); assemble cuts from the original"]
                    fields["master"] = TI.stamp(src)
                else:
                    def fill(mp4):
                        how = TI.link_or_copy(src, mp4)
                        return [f"{src} whole ({how}, not re-encoded)"]
                t = TI.import_made(ep, PASS, c["shot"], fill, f"from the edit: {c['name']}",
                                   {"source_path": src}, **fields)
            _pin(ep, c["shot"], t.take)
            keyframe(ep, c["shot"], t.paths.mp4, c.get("head", 0),
                     float((t.sidecar or {}).get("fps") or g["fps"]))
            made += 1
            if on_take:
                on_take(t)
        except Exception as e:                           # noqa: BLE001  the next clip still goes
            failed.append(f"{c['shot']}: {e}")
        report(progress=(0.5 if proxy else 0.0) + (0.5 if proxy else 1.0) * (i + 1) / max(1, n),
               line=f"{c['shot']} ({i + 1}/{n})")
    return {"made": made, "kept": kept, "failed": failed}


# ---------------------------------------------------------------------------
# the command
# ---------------------------------------------------------------------------

def _print_summary(s: dict) -> None:
    print(f"  {s['sequence']}: {s['shots']} shot(s) ({s['black']} black), "
          f"{s['takes']} take(s) to make, {s['audio_items']} mix item(s)"
          + (f" on {', '.join(s['tracks'])}" if s["tracks"] else "")
          + (f", {s['hits']} hit(s)" if s["hits"] else "")
          + f"; {len(s['sequences'])} sequence(s); {s['fps']:g} fps, {s['size'][0]}x{s['size'][1]}")
    print(f"  media: {s['media']}" + (f" ({s['handles']:g} s handles)" if s.get("handles") else ""))
    if s["proxies"]:
        print(f"  proxies for: {', '.join(s['proxies'])}")
    for c in s["clips"]:
        if c.get("note"):
            print(f"  ~~ {c['shot']}: {c['note']}")
    for w in s["warnings"]:
        print(f"  ~~ {w}")


def cmd_import_xml(argv: list[str]) -> int:
    """`seriesmith import-xml <file.xml> [--into FOLDER] [--episode] [--name Show] [--media
    handles|reference|proxies] [--handles 1.0] [--dry-run]`."""
    import argparse
    ap = argparse.ArgumentParser(prog="seriesmith import-xml",
                                 description="an edit (FCP7 XML) into a new show and episode")
    ap.add_argument("xml", help="the FCP7 XML (Premiere, Resolve, Final Cut 7, assemble --xml)")
    ap.add_argument("--into", default=".", help="the folder of shows the new show goes in "
                                                "(default: here)")
    ap.add_argument("--name", default=None, help="the show's name (default: the sequence's); "
                                                 "with --episode, the episode's title")
    ap.add_argument("--episode", action="store_true",
                    help="--into is a show's folder: the edit becomes its next episode, "
                         "the series config its newest episode's")
    ap.add_argument("--media", choices=MEDIA, default="handles",
                    help="handles: each clip's span and handles, H.264 (default); reference: "
                         "each source whole, linked or copied, never re-encoded; proxies: "
                         "reference, with a playable proxy of each source the editor can't play")
    ap.add_argument("--handles", type=float, default=HANDLES_S,
                    help="seconds of handle either side of each clip (default %(default)s)")
    ap.add_argument("--dry-run", action="store_true", help="say what it would make; write nothing")
    args = ap.parse_args(argv)
    from seriesmith import source as S
    try:
        with open(args.xml, "rb") as fh:
            text = fh.read().decode("utf-8-sig", "replace")
    except OSError as e:
        print(f"  !! {e}")
        return 1
    base = os.path.dirname(os.path.abspath(args.xml))
    try:
        if args.dry_run:
            s = public(plan(text, os.path.abspath(args.into), os.path.basename(args.xml),
                            args.name, args.media, args.handles, base, args.episode))
            _print_summary(s)
            print(f"\n  (dry run) would make {s['ep']}")
            return 0
        s = make(text, os.path.abspath(args.into), os.path.basename(args.xml), args.name,
                 args.media, args.handles, base, args.episode)
    except (XmlImportError, S.SourceError) as e:
        print(f"  !! {e}")
        return 1
    _print_summary(s)
    print(f"  -- {s['ep']}" + ("" if s["build"]["ok"] else "  (the build failed: seriesmith check it)"))
    failed = []
    for g in (load_group(s["ep"], i) for i in range(len(s["groups"]))):
        print(f"  {group_title(s['ep'], g)}")
        res = run_group(s["ep"], g, report=lambda **k: k.get("line") and print(f"     {k['line']}"))
        failed += res["failed"]
    for f in failed:
        print(f"  !! {f}")
    print(f"\n  open it in the editor: {s['ep']}")
    return 1 if failed else 0
