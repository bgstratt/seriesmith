#!/usr/bin/env python3
"""
publish.py — the episode as it goes out: the series intro, the cut, the outro.

    seriesmith publish Shows\\ep05              # the final review cut
    seriesmith publish Shows\\ep05 --proxy      # the proxy review cut
    seriesmith publish Shows\\ep05 --input some.mp4 --check

`seriesmith master` (and the editor's Master) run this on the master they make, so a
master is the finished episode, titles included, whenever the clips are there.

The intro and outro are clips made once for the whole series: _titles/INTRO.mp4
and _titles/OUTRO.mp4 in the show folder (or the episode's), unless the series
config's `publish` block names others (paths relative to the episode folder). The
episode's title, from the script's `= ep05  Title` line, is written under the
series title the clips already carry: faded in on the intro, faded out with the
title on the outro. One font file, size and colour for every episode, so the
titles match. Output: <episode>/publish/<input name>.mp4.

The cut's picture is copied, not re-encoded. Only the two title clips are
encoded, scaled to the cut's size and rate with the same libx264 settings
assemble used for the cut (its `master` or `review` quality, whichever gives
the cut's own H.264 headers), and the three are joined with the concat
demuxer. The sound is re-encoded as one track, so there are no gaps at the
joins. Before it is kept, the result is checked: the frame count adds up and
the frames on both sides of each join decode to exactly the frames that went
in. When the cut can't be copied (not an assemble encode, another codec, a
check fails), the whole thing is re-encoded instead and the reason is printed;
`--reencode` asks for that directly.

    "publish": {
      "intro": "../_titles/INTRO.mp4",
      "outro": "../_titles/OUTRO.mp4",
      "subtitle": {
        "font": "C:/Windows/Fonts/segoescb.ttf",
        "size": 0.058,           # text height, a fraction of the frame height
        "y": 0.56,               # top of the text, a fraction of the frame height
        "color": "#F4E6D0", "glow": "#FFB45A@0.8", "glow_size": 0.008,
        "intro_in": [4.0, 5.0],  # seconds into the intro: fade starts, fully on
        "outro_in": [0.0, 1.0],  # seconds into the outro: fade in ...
        "outro_out": [4.5, 5.5]  # ... and out
      },
      "loudness": {"match": true, "under_lu": 0}
    }

The title clips' sound is brought to the episode's loudness (the mix's target,
mix.loudness_target: -16 LUFS, -1 dBTP unless set): each measured by loudnorm
and moved by one gain to the target less `under_lu` (a theme tucked under the
episode: 1-2), held under the ceiling by the mix's true-peak limiter when that
gain would cross it. `"match": false` leaves them as they came. The cut's own
sound is never touched: its mix brought it to the target already.

Every `subtitle` key is optional; the values above are the defaults, and
`intro` / `outro` default to the _titles files. Stdlib only; needs ffmpeg and
ffprobe on PATH.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

from seriesmith import assemble as ASM  # noqa: E402
from seriesmith import edit as E  # noqa: E402
from seriesmith import takes as T  # noqa: E402
from seriesmith import ff as FF  # noqa: E402

LEVEL = {"match": True, "under_lu": 0.0}
# the title's font when the series config names none and the default (Windows' Segoe Script)
# isn't on this machine: the first of these that is
FONT_FALLBACKS = (
    "C:/Windows/Fonts/segoesc.ttf", "C:/Windows/Fonts/georgia.ttf", "C:/Windows/Fonts/arial.ttf",
    "/System/Library/Fonts/Supplemental/Georgia.ttf", "/Library/Fonts/Georgia.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
)
SUBTITLE = {
    "font": "C:/Windows/Fonts/segoescb.ttf",
    "size": 0.058,
    "y": 0.56,
    "color": "#F4E6D0",
    "glow": "#FFB45A@0.8",
    "glow_size": 0.008,
    "intro_in": [4.0, 5.0],
    "outro_in": [0.0, 1.0],
    "outro_out": [4.5, 5.5],
}
AUDIO = ["-c:a", "aac", "-b:a", "256k"]
JOIN_FRAMES = 12      # frames checked on each side of a join
# --progress: `##publish {"stage", "done", "total", "text"}` per step (titles,
# join, verify, reencode with a frame count), then one `done` line saying how the
# picture got there: {"stage": "done", "picture": "copied" | "re-encoded", "why"}.
# master reads it into the master's report.
PROGRESS = "##publish "
# what has to agree for the cut's picture to be copied next to the title clips
MATCH = ("codec_name", "profile", "pix_fmt", "width", "height", "r_frame_rate",
         "field_order", "color_range", "color_space", "color_primaries", "color_transfer")


class PublishError(Exception):
    pass


def run(cmd: list[str], cwd: str | None = None, timeout: int = 3600) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)


_progress = False


def say(stage: str, done: int | None = None, total: int | None = None, text: str = "",
        **more) -> None:
    """A progress line, when --progress asked for them."""
    if _progress:
        E.progress_line(PROGRESS, {"stage": stage, "done": done, "total": total,
                                        "text": text, **more})


def run_counted(cmd: list[str], total: int, stage: str, cwd: str | None = None,
                timeout: int = 3600) -> subprocess.CompletedProcess:
    """`run`, with ffmpeg's frame count sent as progress lines as it goes (only
    when --progress asked for them; otherwise it is `run`)."""
    if not _progress:
        return run(cmd, cwd, timeout)
    import threading
    cmd = cmd[:1] + ["-progress", "pipe:1", "-nostats"] + cmd[1:]
    p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    err: list[str] = []
    drain = threading.Thread(target=lambda: err.append(p.stderr.read()), daemon=True)
    drain.start()
    killer = threading.Timer(timeout, p.kill)
    killer.start()
    last = -1
    try:
        for line in p.stdout:
            if line.startswith("frame="):
                try:
                    n = int(line[6:].strip())
                except ValueError:
                    continue
                if n // 240 != last // 240:            # every 10 s of picture or so
                    say(stage, n, total)
                last = n
    finally:
        p.stdout.close()
        rc = p.wait()
        killer.cancel()
        drain.join(5)
    return subprocess.CompletedProcess(cmd, rc, "", "".join(err))


# ---------------------------------------------------------------------------
# what goes in
# ---------------------------------------------------------------------------

def episode_title(script: str) -> str:
    """The title on the script's `= ep05  Title` line ('' when it has none)."""
    with open(script, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if s.startswith("="):
                parts = s[1:].strip().split(None, 1)
                return parts[1].strip() if len(parts) > 1 else ""
    return ""


def title_font(font: str, named: bool) -> str:
    """The font file the episode's title is drawn with: `font` when it's there. One the series
    config named and that isn't there is an error (it says so); the default missing (it's
    Windows') falls back to the first of FONT_FALLBACKS on this machine, saying which."""
    if os.path.isfile(font):
        return font
    if named:
        raise PublishError(f"publish.subtitle.font {font} isn't there: set it to a .ttf or .otf "
                           f"file on this machine")
    got = next((f for f in FONT_FALLBACKS if os.path.isfile(f)), None)
    if not got:
        raise PublishError(f"no font for the episode's title: the default ({font}) isn't on this "
                           f"machine. Set publish.subtitle.font in the series config to a .ttf or "
                           f".otf file")
    print(f"  ! the title font {font} isn't here: using {got} (set publish.subtitle.font to choose)")
    return got


def publish_config(series_cfg: dict) -> dict:
    """The series config's `publish` block with the subtitle defaults filled in (`_named`:
    what the config set itself)."""
    block = dict(series_cfg.get("publish") or {})
    block["_named"] = dict(block.get("subtitle") or {})
    block["subtitle"] = {**SUBTITLE, **(block.get("subtitle") or {})}
    block["loudness"] = {**LEVEL, **(block.get("loudness") or {})}
    return block


def default_input(root: str, pass_: str) -> str | None:
    """The pass's review cut. (A master gets its titles from master itself.)"""
    name = os.path.basename(os.path.normpath(root))
    cut = os.path.join(root, T.pass_subfolder(pass_), f"{name}.mp4")
    return cut if os.path.isfile(cut) else None


def probe(path: str) -> dict:
    """The picture's stream (plus `extradata`, its H.264 headers), frame count,
    duration and whether there is sound."""
    try:
        d = FF.probe_json(path, "-count_packets", "-show_streams", "-show_data",
                          "-show_entries", "format=duration", timeout=600)
    except FF.FFError as e:
        raise PublishError(f"ffprobe can't read {path}: {e}") from None
    streams = d.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    if not v:
        raise PublishError(f"{path} has no picture")
    num, _, den = v["r_frame_rate"].partition("/")
    tb = v.get("time_base", "1/12288").partition("/")[2]
    return {**{k: v.get(k) for k in MATCH},
            "width": int(v["width"]), "height": int(v["height"]),
            "fps": float(num) / float(den or 1),
            "frames": int(v.get("nb_read_packets") or 0),
            "start": float(v.get("start_time") or 0),
            "timescale": int(tb or 12288),
            "sar": v.get("sample_aspect_ratio") or "N/A",
            "extradata": (v.get("extradata") or "").strip(),
            "duration": float(d.get("format", {}).get("duration") or 0),
            "picture_s": float(v.get("duration") or 0),
            "audio": any(s.get("codec_type") == "audio" for s in streams)}


# ---------------------------------------------------------------------------
# the filter graphs
# ---------------------------------------------------------------------------

def alpha_expr(fade_in: list | None, fade_out: list | None = None) -> str:
    """drawtext's alpha over t: 0 before the fade in, 1 held, 0 after the fade out."""
    def ramp(a: float, b: float) -> str:  # 0 at a, 1 at b
        return f"clip((t-{a:g})/{max(b - a, 1e-3):g},0,1)" if b > a else f"gte(t,{a:g})"
    up = ramp(*fade_in) if fade_in else "1"
    if not fade_out:
        return up
    down = f"(1-{ramp(*fade_out)})"
    return f"{up}*{down}"


def _text(sub: dict, h: int, color: str, alpha: str) -> str:
    # textfile/fontfile are bare names in ffmpeg's working folder: no drive
    # colons or backslashes to escape on Windows.
    return (f"drawtext=textfile=title.txt:fontfile=font{os.path.splitext(sub['font'])[1]}"
            f":fontsize={max(8, round(sub['size'] * h))}:fontcolor={color}"
            f":x=(w-text_w)/2:y={round(sub['y'] * h)}:alpha='{alpha}'")


def titled(label: str, out: str, sub: dict, w: int, h: int, fps: float,
           dur: float, alpha: str, tags: str = "setsar=1," + ASM.BT709_TAGS,
           matrix: str = "bt709") -> list[str]:
    """[label] scaled to the cut, the subtitle drawn with a soft glow under it -> [out]v.
    `tags` sets the picture's aspect and colour tags (see cut_tags); `matrix` is
    the title clip's own colour matrix, converted to BT.709 when it isn't."""
    glow = max(0.5, sub["glow_size"] * h)
    conv = "" if matrix == "bt709" else ASM.BT601_TO_709 + ","
    return [
        f"[{label}]{conv}scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
        f"fps={fps:g},format=yuv420p[{out}b]",
        f"color=c=black@0:s={w}x{h}:r={fps:g}:d={dur:.3f},format=rgba,"
        f"{_text(sub, h, sub['glow'], alpha)},gblur=sigma={glow:.2f}[{out}g]",
        f"[{out}b][{out}g]overlay=format=auto,{_text(sub, h, sub['color'], alpha)},"
        f"format=yuv420p,{tags}[{out}v]",
    ]


def sound_graph(pieces: list[tuple], silence: int, first: int = 0) -> list[str]:
    """(input, has sound, seconds[, level]) per piece -> each cut or padded to its
    picture, in one rate and layout, joined into [a]; `level` (clip_level's filter)
    goes first on a piece with sound."""
    fmt = "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"
    lines, labels = [], ""
    for n, (idx, has, secs, *rest) in enumerate(pieces, first):
        src = idx if has else silence
        level = (rest[0] + ",") if has and rest and rest[0] else ""
        lines.append(f"[{src}:a]{level}{fmt},apad,atrim=0:{secs:.6f},asetpts=PTS-STARTPTS[a{n}]")
        labels += f"[a{n}]"
    lines.append(f"{labels}concat=n={len(pieces)}:v=0:a=1[a]")
    return lines


def filter_graph(cut: dict, intro: dict | None, outro: dict | None, sub: dict,
                 levels: dict | None = None, split: int | None = None) -> str:
    """The full re-encode. Inputs in order: [intro], cut, [outro], silence. Output [v] [a].
    `levels`: clip_level's filter for "intro" and "outro". `split` (a cold open's end, in
    the cut's frames): the inputs are cut, [intro], cut again, [outro], silence, and the
    intro plays between the cut's frames before `split` and the rest."""
    levels = levels or {}
    w, h, fps = cut["width"], cut["height"], cut["fps"]
    lines, parts, pieces, i = [], [], [], 0
    silence = int(intro is not None) + 1 + int(outro is not None) + int(split is not None)
    tags = ",".join(ASM.to_bt709(cut.get("color_space") or ""))
    if split is not None:
        at = split / fps
        lines.append(f"[{i}:v]setsar=1,{tags},trim=end_frame={split},setpts=PTS-STARTPTS[cv0]")
        parts.append("[cv0]")
        pieces.append((i, cut["audio"], at))
        i += 1
    if intro:
        lines += titled(f"{i}:v", "in", sub, w, h, fps, intro["duration"],
                        alpha_expr(sub["intro_in"]), matrix=intro.get("color_space") or "")
        parts.append("[inv]")
        pieces.append((i, intro["audio"], intro["duration"], levels.get("intro")))
        i += 1
    if split is not None:
        lines.append(f"[{i}:v]setsar=1,{tags},trim=start_frame={split},setpts=PTS-STARTPTS[cv]")
        pieces.append((i, cut["audio"], cut["duration"] - at,
                       f"atrim=start={at:.6f},asetpts=PTS-STARTPTS"))
    else:
        lines.append(f"[{i}:v]setsar=1,{tags}[cv]")
        pieces.append((i, cut["audio"], cut["duration"]))
    parts.append("[cv]")
    i += 1
    if outro:
        lines += titled(f"{i}:v", "out", sub, w, h, fps, outro["duration"],
                        alpha_expr(sub["outro_in"], sub["outro_out"]),
                        matrix=outro.get("color_space") or "")
        parts.append("[outv]")
        pieces.append((i, outro["audio"], outro["duration"], levels.get("outro")))
    lines.append(f"{''.join(parts)}concat=n={len(parts)}:v=1:a=0[v]")
    lines += sound_graph(pieces, silence)
    return ";\n".join(lines)


# ---------------------------------------------------------------------------
# copying the cut's picture
# ---------------------------------------------------------------------------

def cut_tags(cut: dict) -> str:
    """Filters giving a title clip the cut's pixel aspect and colour tags: x264
    writes both into the stream's headers, which must match the cut's. A clip
    from ComfyUI is tagged BT.709; an assemble cut is untagged."""
    sar = "setsar=1" if cut["sar"] not in ("N/A", "0:1") else "setsar=0"
    tag = {"range": "color_range", "color_primaries": "color_primaries",
           "color_trc": "color_transfer", "colorspace": "color_space"}
    return sar + ",setparams=" + ":".join(f"{k}={cut[v] or 'unknown'}" for k, v in tag.items())


def x264_crf(path: str) -> float | None:
    """The crf x264 wrote into the file's settings message, if it is there."""
    with open(path, "rb") as f:
        head = f.read(4 << 20)
    m = re.search(rb"x264 - core.*?crf=([0-9.]+)", head, re.S)
    return float(m.group(1)) if m else None


def quality_order(path: str) -> list[str]:
    """assemble's qualities, the one the cut's crf names first."""
    crf = x264_crf(path)
    order = sorted(ASM.QUALITY_ARGS)
    for q in order:
        args = ASM.QUALITY_ARGS[q]
        if crf is not None and float(args[args.index("-crf") + 1]) == crf:
            order.remove(q)
            return [q] + order
    return order


def copy_blocker(cut: dict) -> str | None:
    """Why the cut's picture can't be copied as it is, or None."""
    if cut["codec_name"] != "h264":
        return f"the cut is {cut['codec_name']}, not H.264"
    if cut["pix_fmt"] != "yuv420p":
        return f"the cut is {cut['pix_fmt']}, not yuv420p"
    if cut["sar"] not in ("N/A", "1:1", "0:1"):
        return f"the cut's pixels aren't square ({cut['sar']})"
    if not cut["extradata"]:
        return "the cut has no H.264 headers to match"
    if not cut["frames"]:
        return "the cut's frames can't be counted"
    if cut.get("color_space") != "bt709":
        # assembled before 2026-10-05: BT.601 and untagged, which players read
        # as BT.709; only a re-encode can convert it (assemble.to_bt709)
        return "the cut isn't BT.709 (assembled before the colour fix): re-encoded to convert it"
    return None


def encode_title(clip: str, dst: str, tmp: str, cut: dict, sub: dict, alpha: str,
                 quality: str) -> None:
    """The title clip with the subtitle drawn on, picture only, encoded the way
    assemble.conform encodes a clip at `quality`."""
    w, h, fps = cut["width"], cut["height"], cut["fps"]
    src = probe(clip)
    frames = src["frames"] or round(src["duration"] * fps)
    graph = ";\n".join(titled("0:v", "t", sub, w, h, fps, frames / fps, alpha,
                                cut_tags(cut), matrix=src.get("color_space") or ""))
    with open(os.path.join(tmp, "title_graph.txt"), "w", encoding="utf-8") as f:
        f.write(graph)
    r = run([*FF.tool("ffmpeg"), "-y", "-v", "error", "-i", clip, "-/filter_complex", "title_graph.txt",
             "-map", "[tv]", "-frames:v", str(frames),
             "-c:v", "libx264", *ASM.QUALITY_ARGS[quality], "-pix_fmt", "yuv420p",
             "-r", f"{fps:g}", "-video_track_timescale", str(cut["timescale"]), "-an", dst],
            cwd=tmp)
    if r.returncode != 0:
        raise PublishError(f"encoding {os.path.basename(clip)} failed:\n{r.stderr.strip()}")


def frame_hashes(path: str, first: int, count: int, info: dict) -> list[str]:
    """framemd5 of `count` decoded frames from frame `first` on."""
    try:
        return FF.frame_md5s(path, ASM.picture_offset(path) + (first - 0.5) / info["fps"], count)
    except FF.FFError as e:
        raise PublishError(f"{os.path.basename(path)} doesn't decode cleanly at frame {first}: "
                           f"{str(e)[-300:]}") from None


def check_joins(out: str, pieces: list[tuple[str, dict]]) -> str | None:
    """None when the output holds every frame and each join decodes to the
    frames that went in; else what is wrong."""
    got = probe(out)
    want = sum(p["frames"] for _, p in pieces)
    if got["frames"] != want:
        return f"the output has {got['frames']} frames, the pieces {want}"
    # every frame there, but a hole in their timing shows only in the length:
    # each frame after it plays late, by less than a frame-content check sees
    if got["picture_s"] and abs(got["picture_s"] - want / got["fps"]) > 0.5 / got["fps"]:
        return (f"the picture runs {got['picture_s'] - want / got['fps']:+.3f}s from its "
                f"{want} frames: a gap in its timing")
    n, at = JOIN_FRAMES, 0
    for (a, pa), (b, pb) in zip(pieces, pieces[1:]):
        at += pa["frames"]
        k = min(n, pa["frames"], pb["frames"])
        expect = frame_hashes(a, pa["frames"] - k, k, pa) + frame_hashes(b, 0, k, pb)
        seen = frame_hashes(out, at - k, 2 * k, got)
        if seen != expect:
            return (f"the frames around the join at frame {at} "
                    f"({os.path.basename(a)} -> {os.path.basename(b)}) don't match what went in")
    return None


def split_picture(pic: str, frames: int, at: int, tmp: str) -> tuple[str, str] | str:
    """The cut's picture (copied out, `frames` long) in two at frame `at`, each copied:
    (head, tail), or why it can't be (`at` isn't a keyframe: every clip assemble writes
    starts on one, so a cold open ending on a clip's last frame always is)."""
    r = run([*FF.tool("ffmpeg"), "-y", "-v", "error", "-i", pic, "-map", "0:v:0", "-c", "copy",
             "-f", "segment", "-segment_frames", str(at), "-reset_timestamps", "1",
             "-segment_format", "mp4", "part%d.mp4"], cwd=tmp)
    head, tail = os.path.join(tmp, "part0.mp4"), os.path.join(tmp, "part1.mp4")
    if r.returncode != 0 or not os.path.isfile(tail):
        return f"the cut couldn't be split at the cold open's end: {r.stderr.strip()[-300:]}"
    if probe(head)["frames"] != at or probe(tail)["frames"] != frames - at:
        return f"the cold open's end (frame {at}) isn't a keyframe of the cut"
    return head, tail


def publish_copy(src: str, cut: dict, intro: str | None, outro: str | None, sub: dict,
                 out: str, tmp: str, levels: dict | None = None,
                 split: int | None = None) -> str | None:
    """Intro + cut + outro with the cut's picture copied. Writes `out` and
    returns None, or returns why it couldn't (and writes nothing)."""
    why = copy_blocker(cut)
    if why:
        return why
    titles = [(intro, "intro", alpha_expr(sub["intro_in"])),
              (outro, "outro", alpha_expr(sub["outro_in"], sub["outro_out"]))]
    made: dict[str, str] = {}
    used = None
    for quality in quality_order(src):
        for clip, kind, alpha in titles:
            if clip:
                made[kind] = os.path.join(tmp, f"{kind}.mp4")
                say("titles", text=kind)
                encode_title(clip, made[kind], tmp, cut, sub, alpha, quality)
        if all(probe(p)["extradata"] == cut["extradata"] for p in made.values()):
            used = quality
            break
    if not used:
        return "the title clips can't be encoded with the cut's H.264 headers " \
               "(the cut wasn't encoded by assemble)"
    for kind, path in made.items():
        p = probe(path)
        diff = [k for k in MATCH if p[k] != cut[k]]
        if diff:
            return f"the {kind} doesn't match the cut: {', '.join(diff)}"

    # the cut's picture alone goes into the join: the concat demuxer starts the
    # next clip where a clip's longer stream ends, and a cut's sound runs a few
    # milliseconds past its picture (its last clip's AAC), which pushed the outro
    # late and failed check_joins on every real master (ep01, 2026-10-04). Its
    # sound is laid separately below either way.
    pic_only = os.path.join(tmp, "cut_picture.mp4")
    r = run([*FF.tool("ffmpeg"), "-y", "-v", "error", "-i", src, "-map", "0:v:0", "-c", "copy",
             pic_only], cwd=tmp)
    if r.returncode != 0:
        return f"the cut's picture couldn't be copied out: {r.stderr.strip()[-300:]}"
    levels = levels or {}
    # (picture, sound, what it is): the cut's head and tail around the intro when a cold
    # open ends at `split`, else the cut whole
    parts: list[tuple[str, str, str]] = []
    if split is not None:
        halves = split_picture(pic_only, cut["frames"], split, tmp)
        if isinstance(halves, str):
            return halves
        parts.append((halves[0], src, "head"))
    if intro:
        parts.append((made["intro"], intro, "intro"))
    parts.append((halves[1], src, "tail") if split is not None else (pic_only, src, "cut"))
    if outro:
        parts.append((made["outro"], outro, "outro"))
    order = [pic for pic, _, _ in parts]
    sounds = [snd for _, snd, _ in parts]
    infos = {p: (cut if p == pic_only else probe(p)) for p in order}
    with open(os.path.join(tmp, "join.txt"), "w", encoding="utf-8") as f:
        for p in order:
            f.write(f"file '{p.replace(os.sep, '/')}'\n")
    pieces = []
    for i, (pic, snd, kind) in enumerate(parts, 1):
        if kind == "tail":
            pre = f"atrim=start={split / cut['fps']:.6f},asetpts=PTS-STARTPTS"
        else:
            pre = levels.get(kind)
        pieces.append((i, probe(snd)["audio"] if snd != src else cut["audio"],
                       infos[pic]["frames"] / cut["fps"], pre))
    silence = len(order) + 1
    with open(os.path.join(tmp, "sound_graph.txt"), "w", encoding="utf-8") as f:
        f.write(";\n".join(sound_graph(pieces, silence)))
    cmd = [*FF.tool("ffmpeg"), "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", "join.txt"]
    for s in sounds:
        cmd += ["-i", s]
    joined = os.path.join(tmp, "joined.mp4")
    cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
            "-/filter_complex", "sound_graph.txt", "-map", "0:v:0", "-map", "[a]",
            "-c:v", "copy", *AUDIO, "-video_track_timescale", str(cut["timescale"]),
            "-movflags", "+faststart", joined]
    say("join")
    r = run(cmd, cwd=tmp)
    if r.returncode != 0:
        return f"joining failed: {r.stderr.strip()[-300:]}"
    say("verify", text="checking the joins")
    try:
        why = check_joins(joined, [(p, infos[p]) for p in order])
    except PublishError as e:
        why = str(e)
    if why:
        return why
    shutil.move(joined, out)
    print(f"    picture copied{' (split at the cold open)' if split is not None else ''}; "
          f"title clips encoded at assemble's {used} quality, "
          f"sound re-encoded")
    return None


def publish_reencode(src: str, cut: dict, intro: str | None, outro: str | None, sub: dict,
                     out: str, tmp: str, quality: str, levels: dict | None = None,
                     split: int | None = None) -> None:
    pi, po = (probe(intro) if intro else None), (probe(outro) if outro else None)
    with open(os.path.join(tmp, "graph.txt"), "w", encoding="utf-8") as f:
        f.write(filter_graph(cut, pi, po, sub, levels, split))
    cmd = [*FF.tool("ffmpeg"), "-y", "-v", "error"]
    for p in ((src, intro, src, outro) if split is not None else (intro, src, outro)):
        if p:
            cmd += ["-i", p]
    cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
            "-/filter_complex", "graph.txt", "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", *ASM.QUALITY_ARGS[quality],
            *AUDIO, "-movflags", "+faststart", os.path.join(tmp, "out.mp4")]
    total = sum((i["frames"] or round(i["duration"] * cut["fps"])) for i in (pi, cut, po) if i)
    r = run_counted(cmd, total, "reencode", cwd=tmp)
    if r.returncode != 0:
        raise PublishError(f"ffmpeg failed:\n{r.stderr.strip()}")
    shutil.move(os.path.join(tmp, "out.mp4"), out)
    print(f"    re-encoded at {quality} quality")


# ---------------------------------------------------------------------------
# the title clips' loudness
# ---------------------------------------------------------------------------

def loudness_target(root: str, pass_: str, series_cfg: dict) -> dict:
    """The loudness the episode's export is held to (its pass's mix's, else the
    series config's, else mix.LOUDNESS)."""
    from seriesmith import mix as MX
    try:
        mix = MX.load(root).get(pass_)
    except (OSError, ValueError):
        mix = None
    return MX.loudness_target(mix if isinstance(mix, dict) else None, series_cfg)


def clip_level(path: str, target: dict, under_lu: float = 0.0) -> tuple[str | None, str]:
    """A title clip's sound brought to `target` less `under_lu`: (the filter that does it,
    or None to leave it; what was done, in words). One gain, as the mix's; the mix's
    true-peak limiter (oversampled, LOSSY_MARGIN_DB under the ceiling for the AAC) when
    the gain would cross it. A clip that can't be measured, or is silent, is left."""
    from seriesmith import mix as MX
    want = float(target["target_lufs"]) - float(under_lu or 0.0)
    m = MX.measure(path, want, float(target["true_peak_db"]))
    if not m or not (m.get("input_i", float("-inf")) > -70):
        return None, "left as it is (silent, or it couldn't be measured)"
    gain = want - m["input_i"]
    words = f"{m['input_i']:g} LUFS, {gain:+.1f} dB to {want:g}"
    level = f"volume={gain:.2f}dB"
    hold = float(target["true_peak_db"]) - MX.LOSSY_MARGIN_DB
    peak = m.get("input_tp", float("-inf")) + gain
    if peak > hold:
        level += (f",aresample={48000 * MX.TP_OVERSAMPLE},alimiter=limit={10 ** (hold / 20):.4f}"
                  f":level=false:attack=5:release=50")
        words += f", limited to {hold:g} dBTP (it would peak at {peak:+.1f})"
    return level, words


# ---------------------------------------------------------------------------
# the command
# ---------------------------------------------------------------------------

TITLES = {"intro": "INTRO.mp4", "outro": "OUTRO.mp4"}


def _clip(root: str, block: dict, key: str) -> str | None:
    """The series config's publish.<key>, else _titles/INTRO.mp4 (OUTRO.mp4) in
    the episode folder or the show folder above it, else None."""
    rel = block.get(key)
    if rel:
        path = os.path.normpath(os.path.join(root, rel))
        if not os.path.isfile(path):
            raise PublishError(f"publish.{key} is {rel}, which isn't there ({path})")
        return path
    for d in (root, os.path.dirname(os.path.normpath(root))):
        path = os.path.join(d, "_titles", TITLES[key])
        if os.path.isfile(path):
            return path
    return None


def cold_open_split(root: str, src: str, fps: float, intro: str | None,
                    pass_: str = "final") -> int | None:
    """Where the intro goes in the cut `src` (its frame) when the script marks a cold open,
    else None (at the start): read from the shot list assemble wrote beside it
    (`<cut>_shots.txt`, coldopen.split_in_file), so it's where the file's shots really are.
    PublishError when the marks don't make one run at the cut's head. Without an intro
    there's nothing to put in."""
    if not intro:
        return None
    from seriesmith import coldopen as CO
    try:
        at = CO.split_in_file(root, os.path.splitext(src)[0] + "_shots.txt", fps)
    except CO.ColdOpenError as e:
        raise PublishError(f"cold open: {e}") from None
    if at is not None:
        try:
            cross = CO.state(root, pass_)["crossing"]
        except (OSError, ValueError):
            cross = []
        if cross:
            print(f"  ! cold open: {', '.join(c['label'] for c in cross)} "
                  f"play{'s' if len(cross) == 1 else ''} across its end: cut there by the intro")
    return at


def titles(root: str) -> tuple[str | None, str | None]:
    """The episode's (intro, outro) clips, either None when there isn't one:
    the series config's publish block, else the _titles files."""
    cfg = E.episode_series_config(root)
    block = {}
    if cfg:
        with open(cfg, encoding="utf-8") as f:
            block = publish_config(json.load(f))
    return _clip(root, block, "intro"), _clip(root, block, "outro")


def publish(root: str, src: str | None = None, pass_: str = "final", out: str | None = None,
            quality: str | None = None, check: bool = False, reencode: bool = False) -> str:
    root = os.path.abspath(root)
    script = E.episode_script(root)
    cfg_path = E.episode_series_config(root)
    if not script or not cfg_path:
        raise PublishError(f"{root} needs its script and a series.json")
    with open(cfg_path, encoding="utf-8") as f:
        block = publish_config(json.load(f))
    sub = block["subtitle"]
    sub["font"] = title_font(sub["font"], named=bool((block.get("_named") or {}).get("font")))
    src = os.path.abspath(src) if src else default_input(root, pass_)
    if not src or not os.path.isfile(src):
        raise PublishError("nothing to publish: assemble the episode first, "
                           "or name a file with --input")
    intro, outro = _clip(root, block, "intro"), _clip(root, block, "outro")
    if not intro and not outro:
        raise PublishError("no intro or outro: put INTRO.mp4 / OUTRO.mp4 in the show's _titles "
                           "folder, or name them in the series config's publish block")
    title = episode_title(script)
    name = os.path.splitext(os.path.basename(src))[0]
    out = os.path.abspath(out or os.path.join(root, "publish", f"{name}.mp4"))
    if quality is None:
        quality = "master" if os.path.basename(os.path.dirname(src)) == "master" else "review"

    cut = probe(src)
    split = cold_open_split(root, src, cut["fps"], intro, pass_)
    print(f"  {os.path.basename(root)}  \"{title}\"")
    print(f"    intro  {intro or '(none)'}")
    print(f"    cut    {src}  {cut['width']}x{cut['height']} {cut['fps']:g}fps "
          f"{cut['duration']:.1f}s")
    if split is not None:
        print(f"    cold open: the intro goes in at frame {split} ({split / cut['fps']:.2f}s)")
    print(f"    outro  {outro or '(none)'}")
    print(f"    font   {sub['font']}")
    print(f"    -> {out}")
    levels: dict[str, str] = {}
    lv = block["loudness"]
    if not check and lv.get("match", True):
        with open(cfg_path, encoding="utf-8") as f:
            target = loudness_target(root, pass_, json.load(f))
        for kind, clip in (("intro", intro), ("outro", outro)):
            if clip and probe(clip)["audio"]:
                level, words = clip_level(clip, target, lv.get("under_lu") or 0.0)
                print(f"    {kind} sound: {words}")
                if level:
                    levels[kind] = level
    if check:
        why = copy_blocker(cut)
        print(f"    {'picture would be re-encoded: ' + why if why else 'picture can be copied'}")
        return out
    if not title:
        print("  ! the script's = line has no title: the intro and outro go out without one")

    os.makedirs(os.path.dirname(out), exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="h3publish_") as tmp:
        with open(os.path.join(tmp, "title.txt"), "w", encoding="utf-8") as f:
            f.write(title)
        shutil.copyfile(sub["font"], os.path.join(tmp, "font" + os.path.splitext(sub["font"])[1]))
        why = "--reencode" if reencode else publish_copy(src, cut, intro, outro, sub, out, tmp,
                                                         levels, split)
        if why:
            print(f"  ! re-encoding the whole cut: {why}")
            say("reencode", 0, None, why)
            publish_reencode(src, cut, intro, outro, sub, out, tmp, quality, levels, split)
    got = probe(out)
    print(f"    {got['duration']:.1f}s, {got['frames']} frames")
    print(f"  -> {out}")
    say("done", picture="re-encoded" if why else "copied", why=why or "")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="seriesmith publish", description="Intro + cut + outro, titled, into <episode>/publish/.")
    ap.add_argument("episode")
    ap.add_argument("--input", default=None,
                    help="the cut to publish (default: the review cut)")
    ap.add_argument("--proxy", dest="pass_", action="store_const", const="proxy", default="final",
                    help="the proxy review cut")
    ap.add_argument("--out", default=None, help="output file (default <episode>/publish/<input>.mp4)")
    ap.add_argument("--reencode", action="store_true",
                    help="re-encode the whole cut instead of copying its picture")
    ap.add_argument("--quality", choices=sorted(ASM.QUALITY_ARGS), default=None,
                    help="x264 settings when re-encoding (default: master for a master, "
                         "else review)")
    ap.add_argument("--check", action="store_true", help="report only")
    ap.add_argument("--progress", action="store_true",
                    help="print a ##publish progress line per step (for master)")
    a = ap.parse_args(argv)
    global _progress
    _progress = a.progress
    try:
        publish(a.episode, a.input, a.pass_, a.out, a.quality, a.check, a.reencode)
    except PublishError as e:
        print(f"  !! {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
