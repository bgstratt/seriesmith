"""
nle_xml.py — a cut as FCP7 XML (xmeml v4), the timeline Premiere, Resolve, Avid,
Final Cut 7, Kdenlive and Shotcut all import.

assemble --xml hands it the cut's clips as its plan lays them; nothing is
encoded. Each clip points at its own file, in and out where the cut uses it, so
the frames a trim or a dialogue window leaves out are there as handles. Every
time here is in the sequence's frames (a clip at another rate is too, as
assemble counts it; its file carries its own rate and the editor conforms it).

    clips: [{"name": "sh010 t03", "path", "frames" (the file's, in sequence
              frames), "fps" (the file's), "size" (w, h) | None,
              "in" (the cut's first frame of it), "used", "dissolve_in",
              "fade_in", "fade_out", "marker" (a sequence's name at its first
              clip) | None,
              "audio": {"path", "channels", "frames", "at" (where the file's
                        first frame sits, from the clip's first used frame),
                        "gain"} | None}]
    recording: {"path", "channels", "frames", "at" (from the cut's start)} | None

A dissolve of n frames on a clip is a centred Cross Dissolve on its join: the
edit at the clip before's frame used - n + n//2, the frames either side its
handles, the frames assemble's xfade uses. A fade is a Cross Dissolve from or to
black at the clip's own head or tail. Clip sound is on A1/A2 (a mono file A1
alone), the recording on A3/A4.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from urllib.parse import quote

NTSC = {23.976: 24, 29.97: 30, 47.952: 48, 59.94: 60}
SAMPLE_RATE = 48000


def rate(fps: float) -> tuple[int, bool]:
    """(timebase, ntsc) for a frame rate: 23.976 is 24 NTSC."""
    for v, base in NTSC.items():
        if abs(fps - v) < 0.01:
            return base, True
    return max(1, round(fps)), False


def pathurl(path: str) -> str:
    """A file's URL as Premiere writes one: file://localhost/C%3a/My%20Show/sh010.mp4."""
    p = os.path.abspath(path).replace(os.sep, "/")
    return "file://localhost/" + quote(p.lstrip("/"), safe="/").replace("%3A", "%3a")


def _sub(parent: ET.Element, tag: str, text=None, **attrs) -> ET.Element:
    e = ET.SubElement(parent, tag, {k: str(v) for k, v in attrs.items()})
    if text is not None:
        e.text = "TRUE" if text is True else "FALSE" if text is False else str(text)
    return e


def _rate(parent: ET.Element, fps: float) -> None:
    base, ntsc = rate(fps)
    r = _sub(parent, "rate")
    _sub(r, "timebase", base)
    _sub(r, "ntsc", ntsc)


class _Files:
    """Each file once: its first clipitem defines it, the rest name it."""

    def __init__(self, fps: float):
        self.fps = fps
        self.ids: dict[str, str] = {}

    def ref(self, parent: ET.Element, path: str, frames: int, fps: float,
            size: tuple[int, int] | None, channels: int) -> str:
        key = os.path.normcase(os.path.abspath(path))
        if key in self.ids:
            _sub(parent, "file", id=self.ids[key])
            return self.ids[key]
        fid = self.ids[key] = f"file-{len(self.ids) + 1}"
        f = _sub(parent, "file", id=fid)
        _sub(f, "name", os.path.basename(path))
        _sub(f, "pathurl", pathurl(path))
        _rate(f, fps)
        _sub(f, "duration", frames)
        media = _sub(f, "media")
        if size:
            sc = _sub(_sub(media, "video"), "samplecharacteristics")
            _rate(sc, fps)
            _sub(sc, "width", size[0])
            _sub(sc, "height", size[1])
            _sub(sc, "anamorphic", False)
            _sub(sc, "pixelaspectratio", "square")
            _sub(sc, "fielddominance", "none")
        if channels:
            a = _sub(media, "audio")
            sc = _sub(a, "samplecharacteristics")
            _sub(sc, "depth", 16)
            _sub(sc, "samplerate", SAMPLE_RATE)
            _sub(a, "channelcount", channels)
        return fid


def _transition(track: ET.Element, fps: float, start: int, end: int, align: str,
                audio: bool) -> None:
    t = _sub(track, "transitionitem")
    _rate(t, fps)
    _sub(t, "start", start)
    _sub(t, "end", end)
    _sub(t, "alignment", align)
    fx = _sub(t, "effect")
    if audio:
        _sub(fx, "name", "Cross Fade (+3dB)")
        _sub(fx, "effectid", "KGAudioTransCrossFade3dB")
        _sub(fx, "effectcategory", "Audio Transitions")
        _sub(fx, "effecttype", "transition")
        _sub(fx, "mediatype", "audio")
    else:
        _sub(fx, "name", "Cross Dissolve")
        _sub(fx, "effectid", "Cross Dissolve")
        _sub(fx, "effectcategory", "Dissolve")
        _sub(fx, "effecttype", "transition")
        _sub(fx, "mediatype", "video")
        _sub(fx, "wipecode", 0)
        _sub(fx, "wipeaccuracy", 100)
        _sub(fx, "startratio", 0)
        _sub(fx, "endratio", 1)
        _sub(fx, "reverse", False)


def _gain(item: ET.Element, gain: float) -> None:
    fx = _sub(_sub(item, "filter"), "effect")
    _sub(fx, "name", "Audio Levels")
    _sub(fx, "effectid", "audiolevels")
    _sub(fx, "effectcategory", "audiolevels")
    _sub(fx, "effecttype", "audiolevels")
    _sub(fx, "mediatype", "audio")
    p = _sub(fx, "parameter")
    _sub(p, "parameterid", "level")
    _sub(p, "name", "Level")
    _sub(p, "valuemin", 0)
    _sub(p, "valuemax", "3.98109")
    _sub(p, "value", f"{gain:g}")


def lay(clips: list[dict]) -> list[dict]:
    """Where each clip sits: {"T" (its first used frame on the timeline), "start",
    "end" (where it's seen, the edits at its dissolves' middles), "in", "out"
    (in its file)}, and the cut's length as the last one's end."""
    out, at = [], 0
    for k, c in enumerate(clips):
        if k:
            at -= c["dissolve_in"]
        nxt = clips[k + 1]["dissolve_in"] if k + 1 < len(clips) else 0
        head = c["dissolve_in"] // 2
        tail = nxt - nxt // 2
        out.append({"T": at, "start": at + head, "end": at + c["used"] - tail,
                    "in": c["in"] + head, "out": c["in"] + c["used"] - tail})
        at += c["used"]
    return out


def write(name: str, fps: float, size: tuple[int, int] | None, clips: list[dict],
          recording: dict | None = None) -> str:
    """The xmeml document for a cut, as text."""
    spots = lay(clips)
    total = spots[-1]["end"] if spots else 0
    files = _Files(fps)
    ids = iter(range(1, 1 << 30))

    root = ET.Element("xmeml", version="4")
    seq = _sub(root, "sequence", id="sequence-1")
    _sub(seq, "name", name)
    _sub(seq, "duration", total)
    _rate(seq, fps)
    tc = _sub(seq, "timecode")
    _rate(tc, fps)
    _sub(tc, "string", "00:00:00:00")
    _sub(tc, "frame", 0)
    _sub(tc, "displayformat", "NDF")
    media = _sub(seq, "media")

    video = _sub(media, "video")
    sc = _sub(_sub(video, "format"), "samplecharacteristics")
    _rate(sc, fps)
    if size:
        _sub(sc, "width", size[0])
        _sub(sc, "height", size[1])
    _sub(sc, "anamorphic", False)
    _sub(sc, "pixelaspectratio", "square")
    _sub(sc, "fielddominance", "none")
    v1 = _sub(video, "track")

    audio = _sub(media, "audio")
    _sub(audio, "numOutputChannels", 2)
    asc = _sub(_sub(audio, "format"), "samplecharacteristics")
    _sub(asc, "depth", 16)
    _sub(asc, "samplerate", SAMPLE_RATE)
    a_tracks = [_sub(audio, "track") for _ in range(4 if recording else 2)]

    def item(track: ET.Element, label: str, path: str, frames: int, file_fps: float,
             fsize, channels: int, start: int, end: int, in_: int, out: int,
             kind: str, src_track: int = 1) -> ET.Element:
        cid = f"clipitem-{next(ids)}"
        it = _sub(track, "clipitem", id=cid)
        _sub(it, "name", label)
        _sub(it, "enabled", True)
        _sub(it, "duration", frames)
        _rate(it, fps)
        _sub(it, "start", start)
        _sub(it, "end", end)
        _sub(it, "in", in_)
        _sub(it, "out", out)
        fid = files.ref(it, path, frames, file_fps, fsize, channels)
        it.insert(0, ET.Element("masterclipid"))
        it[0].text = "masterclip-" + fid.split("-", 1)[1]
        if kind == "audio":
            st = _sub(it, "sourcetrack")
            _sub(st, "mediatype", "audio")
            _sub(st, "trackindex", src_track)
        return it

    def link(items: list[tuple[ET.Element, str, int]]) -> None:
        for it, _, _ in items:
            for other, kind, track in items:
                ln = _sub(it, "link")
                _sub(ln, "linkclipref", other.get("id"))
                _sub(ln, "mediatype", kind)
                _sub(ln, "trackindex", track)

    # (start, end) of each clip's sound on A1, for its transitions
    heard: list[tuple[int, int] | None] = []
    for k, (c, sp) in enumerate(zip(clips, spots)):
        if c.get("marker"):
            m = _sub(seq, "marker")
            _sub(m, "name", c["marker"])
            _sub(m, "comment", "")
            _sub(m, "in", sp["start"])
            _sub(m, "out", -1)
        if k and c["dissolve_in"]:
            n = c["dissolve_in"]
            _transition(v1, fps, sp["T"], sp["T"] + n, "center", False)
        if c["fade_in"]:
            _transition(v1, fps, sp["start"], sp["start"] + c["fade_in"], "start-black", False)
        vid = item(v1, c["name"], c["path"], c["frames"], c["fps"], c.get("size"),
                   (c["audio"] or {}).get("channels", 0)
                   if (c["audio"] or {}).get("path") == c["path"] else 0,
                   sp["start"], sp["end"], sp["in"], sp["out"], "video")
        group = [(vid, "video", 1)]
        a = c.get("audio")
        heard.append(None)
        if a:
            # the file's frame 0 at T + at: what of it falls in the clip's span
            zero = sp["T"] + a["at"]
            s, e = max(sp["start"], zero), min(sp["end"], zero + a["frames"])
            if e > s:
                own = a["path"] == c["path"]
                for ch in range(min(2, a["channels"])):
                    ai = item(a_tracks[ch], c["name"], a["path"], a["frames"], c["fps"] if own
                              else fps, c.get("size") if own else None, a["channels"],
                              s, e, s - zero, e - zero, "audio", ch + 1)
                    if abs(a.get("gain", 1.0) - 1.0) > 1e-9:
                        _gain(ai, a["gain"])
                    if own:
                        group.append((ai, "audio", ch + 1))
                heard[-1] = (s, e)
        if len(group) > 1:
            link(group)
        if c["fade_out"]:
            _transition(v1, fps, sp["end"] - c["fade_out"], sp["end"], "end-black", False)

    # the sound's own transitions, where it meets its clip's edges
    for k, (c, sp) in enumerate(zip(clips, spots)):
        h = heard[k]
        if not h:
            continue
        chans = min(2, c["audio"]["channels"])
        n = c["dissolve_in"]
        if k and n and heard[k - 1] and heard[k - 1][1] == sp["start"] == h[0]:
            for t in a_tracks[:chans]:
                _transition(t, fps, sp["T"], sp["T"] + n, "center", True)
        if c["fade_in"] and h[0] == sp["start"]:
            for t in a_tracks[:chans]:
                _transition(t, fps, sp["start"], sp["start"] + c["fade_in"], "start-black", True)
        if c["fade_out"] and h[1] == sp["end"]:
            for t in a_tracks[:chans]:
                _transition(t, fps, sp["end"] - c["fade_out"], sp["end"], "end-black", True)
    # each track's items in timeline order (a transition before its clip)
    for t in [v1, *a_tracks]:
        kids = list(t)
        kids.sort(key=lambda e: (int(e.findtext("start")), e.tag != "transitionitem"))
        t[:] = kids

    if recording:
        zero = recording["at"]
        s, e = max(0, zero), min(total, zero + recording["frames"])
        if e > s:
            label = os.path.basename(recording["path"])
            for ch in range(min(2, recording["channels"])):
                item(a_tracks[2 + ch], label, recording["path"], recording["frames"], fps,
                     None, recording["channels"], s, e, s - zero, e - zero, "audio", ch + 1)

    ET.indent(root, "  ")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n'
            + ET.tostring(root, encoding="unicode") + "\n")
