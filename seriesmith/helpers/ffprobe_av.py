"""
ffprobe, the part of it seriesmith asks for, through PyAV (ffmpeg's own
libraries, which every ComfyUI has): for a machine with no ffprobe on PATH
(seriesmith/ff.py runs this in its place). Run with the Python that has PyAV:

    python ffprobe_av.py [-v LEVEL] [-select_streams v|a|v:N|a:N] [-count_frames]
        [-count_packets] [-show_streams] [-show_format] [-show_data]
        [-show_entries stream=a,b:format=c] [-of json|default|csv=p=0[:s=x]] FILE

Fields are named, typed and formatted as ffprobe's (csv in its own field
order), so a caller reads the same answer either way. Exit 1, the reason on
stderr, for a file it can't read.

Stdlib and PyAV only.
"""
from __future__ import annotations

import json
import sys
from fractions import Fraction

# ffprobe's own order of a stream's and the format's fields (csv prints them so)
STREAM_ORDER = (
    "index", "codec_name", "codec_long_name", "profile", "codec_type", "codec_tag_string",
    "codec_tag", "width", "height", "coded_width", "coded_height", "has_b_frames",
    "sample_aspect_ratio", "display_aspect_ratio", "pix_fmt", "level", "color_range",
    "color_space", "color_transfer", "color_primaries", "chroma_location", "field_order",
    "refs", "sample_fmt", "sample_rate", "channels", "channel_layout", "bits_per_sample",
    "id", "r_frame_rate", "avg_frame_rate", "time_base", "start_pts", "start_time",
    "duration_ts", "duration", "bit_rate", "nb_frames", "nb_read_frames", "nb_read_packets",
    "extradata_size", "extradata")
FORMAT_ORDER = ("filename", "nb_streams", "format_name", "format_long_name", "start_time",
                "duration", "size", "bit_rate")
# fields only one kind of stream has: ffprobe leaves them out of the other's
VIDEO_ONLY = {"width", "height", "coded_width", "coded_height", "has_b_frames",
              "sample_aspect_ratio", "display_aspect_ratio", "pix_fmt", "level", "color_range",
              "color_space", "color_transfer", "color_primaries", "chroma_location",
              "field_order", "refs"}
AUDIO_ONLY = {"sample_fmt", "sample_rate", "channels", "channel_layout", "bits_per_sample"}
# JSON numbers in ffprobe's output; every other value is a string
INTS = {"index", "width", "height", "coded_width", "coded_height", "has_b_frames", "level",
        "refs", "channels", "bits_per_sample", "start_pts", "duration_ts", "nb_streams",
        "extradata_size"}

# AVColorRange / AVColorSpace / AVColorPrimaries / AVColorTransferCharacteristic
RANGE = {0: "unknown", 1: "tv", 2: "pc"}
SPACE = {0: "gbr", 1: "bt709", 2: "unknown", 4: "fcc", 5: "bt470bg", 6: "smpte170m",
         7: "smpte240m", 8: "ycgco", 9: "bt2020nc", 10: "bt2020c"}
PRIMARIES = {1: "bt709", 2: "unknown", 4: "bt470m", 5: "bt470bg", 6: "smpte170m",
             7: "smpte240m", 8: "film", 9: "bt2020"}
TRC = {1: "bt709", 2: "unknown", 4: "gamma22", 5: "gamma28", 6: "smpte170m", 7: "smpte240m",
       8: "linear", 13: "iec61966-2-1", 14: "bt2020-10", 15: "bt2020-12", 16: "smpte2084",
       18: "arib-std-b67"}


def ratio(r) -> str:
    if not r:
        return "0/0"
    r = Fraction(r)
    return f"{r.numerator}/{r.denominator}"


def secs(v) -> str | None:
    return None if v is None else f"{float(v):.6f}"


def hexdump(data: bytes) -> str:
    """ffprobe's -show_data layout: 16 bytes a line, offset, hex pairs, text."""
    lines = []
    for off in range(0, len(data), 16):
        chunk = data[off:off + 16]
        hx = " ".join(chunk[i:i + 2].hex() for i in range(0, len(chunk), 2))
        text = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{off:08x}: {hx:<40} {text}")
    return "\n" + "\n".join(lines) + "\n" if lines else ""


def _colour(cc, attr: str, names: dict) -> str | None:
    try:
        v = getattr(cc, attr)
    except AttributeError:
        return None
    v = getattr(v, "value", v)
    return names.get(int(v), "unknown") if isinstance(v, int) else (str(v).lower() if v else None)


def stream_fields(s) -> dict:
    cc = s.codec_context
    tb = s.time_base
    f = {"index": s.index, "codec_type": s.type, "codec_name": cc.name,
         "time_base": ratio(tb) if tb else None,
         "start_pts": s.start_time,
         "start_time": secs(s.start_time * tb) if s.start_time is not None and tb else None,
         "duration_ts": s.duration,
         "duration": secs(s.duration * tb) if s.duration is not None and tb else None,
         "nb_frames": str(s.frames) if s.frames else None,
         "bit_rate": str(cc.bit_rate) if getattr(cc, "bit_rate", None) else None}
    try:
        f["profile"] = cc.profile or None
    except Exception:                                     # noqa: BLE001  not every codec says
        f["profile"] = None
    extradata = getattr(cc, "extradata", None) or b""
    f["extradata_size"] = len(extradata)
    f["_extradata"] = extradata
    if s.type == "video":
        f.update(width=cc.width, height=cc.height,
                 pix_fmt=getattr(cc, "pix_fmt", None) or getattr(getattr(cc, "format", None), "name", None),
                 level=getattr(cc, "level", None),
                 r_frame_rate=ratio(s.base_rate or s.guessed_rate),
                 avg_frame_rate=ratio(s.average_rate),
                 field_order="progressive",
                 color_range=_colour(cc, "color_range", RANGE),
                 color_space=_colour(cc, "colorspace", SPACE),
                 color_primaries=_colour(cc, "color_primaries", PRIMARIES),
                 color_transfer=_colour(cc, "color_trc", TRC))
        sar = getattr(cc, "sample_aspect_ratio", None)
        f["sample_aspect_ratio"] = f"{sar.numerator}:{sar.denominator}" if sar else None
    elif s.type == "audio":
        layout = getattr(cc, "layout", None)
        f.update(sample_rate=str(cc.sample_rate), r_frame_rate="0/0", avg_frame_rate="0/0",
                 channels=getattr(cc, "channels", None) or (len(layout.channels) if layout else None),
                 channel_layout=getattr(layout, "name", None),
                 sample_fmt=getattr(getattr(cc, "format", None), "name", None))
    return f


def parse(argv: list[str]) -> dict:
    o = {"select": None, "count_frames": False, "count_packets": False, "streams": False,
         "format": False, "data": False, "entries": {}, "of": "default", "file": None}
    it = iter(argv)
    for a in it:
        if a == "-v" or a == "-loglevel":
            next(it, None)
        elif a == "-select_streams":
            o["select"] = next(it)
        elif a == "-count_frames":
            o["count_frames"] = True
        elif a == "-count_packets":
            o["count_packets"] = True
        elif a == "-show_streams":
            o["streams"] = True
        elif a == "-show_format":
            o["format"] = True
        elif a == "-show_data":
            o["data"] = True
        elif a == "-show_entries":
            for part in next(it).split(":"):
                sect, _, keys = part.partition("=")
                o["entries"].setdefault(sect, []).extend(k for k in keys.split(",") if k)
        elif a in ("-of", "-print_format"):
            o["of"] = next(it)
        elif a.startswith("-"):
            raise SystemExit(f"ffprobe_av: {a} isn't one it knows")
        else:
            o["file"] = a
    return o


def selected(streams, spec: str | None):
    if not spec:
        return list(streams)
    kind, _, n = spec.partition(":")
    want = {"v": "video", "a": "audio", "s": "subtitle", "d": "data"}.get(kind)
    if want is None:                                      # a bare index
        return [s for s in streams if str(s.index) == spec]
    of = [s for s in streams if s.type == want]
    return of[int(n):int(n) + 1] if n else of


def probe(o: dict) -> dict:
    import av
    with av.open(o["file"]) as c:
        streams = selected(c.streams, o["select"])
        fields = {s.index: stream_fields(s) for s in streams}
        if o["count_packets"] or o["count_frames"]:
            for s in streams:
                fields[s.index]["_packets"] = fields[s.index]["_frames"] = 0
            for packet in c.demux(*streams):
                if packet.size == 0:                      # the flush packet
                    continue
                fields[packet.stream.index]["_packets"] += 1
                if o["count_frames"]:
                    for _ in packet.decode():
                        fields[packet.stream.index]["_frames"] += 1
            if o["count_frames"]:
                for s in streams:                         # what the decoder still held
                    try:
                        fields[s.index]["_frames"] += sum(1 for _ in s.codec_context.decode(None))
                    except Exception:                     # noqa: BLE001
                        pass
            for f in fields.values():
                if o["count_packets"]:
                    f["nb_read_packets"] = str(f["_packets"])
                if o["count_frames"]:
                    f["nb_read_frames"] = str(f["_frames"])
        fmt = {"filename": o["file"], "nb_streams": len(c.streams),
               "format_name": c.format.name, "format_long_name": c.format.long_name,
               "start_time": secs(c.start_time / 1e6) if c.start_time is not None else None,
               "duration": secs(c.duration / 1e6) if c.duration is not None else None,
               "size": str(c.size) if getattr(c, "size", None) else None,
               "bit_rate": str(c.bit_rate) if getattr(c, "bit_rate", None) else None}
        rows = [fields[s.index] for s in streams]        # a stream can't be asked once closed
    return {"streams": rows, "format": fmt}


def shown(o: dict, got: dict) -> dict:
    """What to print: {"streams": [{k: v}], "format": {k: v}}, as asked."""
    out = {}
    skeys = None if o["streams"] else o["entries"].get("stream")
    if o["streams"] or "stream" in o["entries"]:
        rows = []
        for f in got["streams"]:
            other = AUDIO_ONLY if f["codec_type"] == "video" else                 VIDEO_ONLY if f["codec_type"] == "audio" else set()
            keys = [k for k in STREAM_ORDER if (skeys is None or k in skeys) and k not in other]
            row = {}
            for k in keys:
                if k == "extradata":
                    if o["data"]:
                        row[k] = hexdump(f["_extradata"])
                    continue
                if skeys is None and (f.get(k) is None or
                                      (k.startswith("color_") and f.get(k) == "unknown")):
                    continue                              # -show_streams leaves out the empty
                row[k] = f.get(k)
            rows.append(row)
        out["streams"] = rows
    fkeys = None if o["format"] else o["entries"].get("format")
    if o["format"] or "format" in o["entries"]:
        out["format"] = {k: got["format"].get(k) for k in FORMAT_ORDER
                         if (fkeys is None or k in fkeys)
                         and (fkeys is not None or got["format"].get(k) is not None)}
    return out


def typed(row: dict) -> dict:
    return {k: (int(v) if k in INTS and v is not None and str(v).lstrip("-").isdigit() else v)
            for k, v in row.items() if v is not None}


def render(o: dict, out: dict) -> str:
    of = o["of"]
    if of.startswith("json"):
        d = {}
        if "streams" in out:
            if not o["streams"]:                         # as ffprobe: only for -show_entries
                d["programs"] = []
                d["stream_groups"] = []
            d["streams"] = [typed(r) for r in out["streams"]]
        if "format" in out:
            d["format"] = typed(out["format"])
        return json.dumps(d, indent=4) + "\n"
    if of.startswith("csv"):
        opts = dict(p.split("=", 1) for p in of.partition("=")[2].split(":") if "=" in p)
        sep, label = opts.get("s", ","), opts.get("p", "1") not in ("0", "false")
        lines = []
        for sect, rows in (("stream", out.get("streams") or []),
                           ("format", [out["format"]] if "format" in out else [])):
            for r in rows:
                vals = ["N/A" if v is None else str(v).strip() for v in r.values()]
                lines.append(sep.join(([sect] if label else []) + vals))
        return "\n".join(lines) + ("\n" if lines else "")
    # default, with its nw (noprint_wrappers) and nk (nokey) options
    opts = dict(p.split("=", 1) for p in of.partition("=")[2].split(":") if "=" in p)
    wrap = opts.get("nw", opts.get("noprint_wrappers", "0")) in ("0", "false")
    key = opts.get("nk", opts.get("nokey", "0")) in ("0", "false")

    def section(name, row):
        body = [(f"{k}=" if key else "") + ("N/A" if v is None else str(v)) for k, v in row.items()]
        return ([f"[{name}]"] + body + [f"[/{name}]"]) if wrap else body
    lines = []
    for r in out.get("streams") or []:
        lines += section("STREAM", r)
    if "format" in out:
        lines += section("FORMAT", out["format"])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    o = parse(sys.argv[1:] if argv is None else argv)
    if not o["file"]:
        print("ffprobe_av: no input file", file=sys.stderr)
        return 1
    try:
        got = probe(o)
    except Exception as e:                                # noqa: BLE001  ffprobe's way: say it, exit 1
        print(f"{o['file']}: {e}", file=sys.stderr)
        return 1
    sys.stdout.write(render(o, shown(o, got)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
