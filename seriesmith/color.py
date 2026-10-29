"""
color — a shot's colour in the cut: exposure, contrast, black point,
saturation, warmth and tint, six sliders at 0 (docs/PLAN.md, "The cut,
finished in place").
Kept on the cut entry (`"color": {...}`), so nothing is rendered again and the
take is untouched; assemble applies it (`filters`), and the editor previews
it with the same numbers (web/src/lib/color.ts, an SVG feColorMatrix).

    check(raw) -> {name: value}         the non-zero ones, each in range (ValueError)
    matrix(color) -> (m, offset)        out = m . rgb + offset, rgb in 0..1
    filters(color) -> [ffmpeg filter]   the same, on a clip's frames
    match(base, clips) -> [color]       what brings each clip in line with the base
                                        (helpers/colorstats.py, numpy)
    look(mp4, frames) -> look           a take's look: a few numbers, kept in its record
    out_of_line({shot: (look, color)})  the clips of a sequence out of line with it

Not a grade: one linear map of the picture's (gamma-encoded) RGB, so the
preview and the export agree, and a match to another shot can solve for it.

    exposure    stops of gain, -2..2: every channel times 2**exposure
    contrast    -1..1: a gain of 2**contrast around mid grey (0.5): -1 half
                as much, 1 twice as much
    black       the black point, -0.25..0.25: positive lifts the blacks
                (x -> x(1-b) + b), negative crushes them (the same line)
    saturation  -1..1: 0 is as shot, -1 grey, 1 twice as colourful (around
                Rec.709 luma)
    warmth      -1..1: red up and blue down by SHIFT a unit (cooler below 0)
    tint        -1..1: green down by SHIFT a unit (magenta), up below 0
                (green); with warmth, any colour cast

In that order: saturation, the channel gains (exposure, warmth, tint), the
contrast, the black point.

Stdlib only; measuring runs helpers/colorstats.py (numpy) as a subprocess.
"""
from __future__ import annotations

import json
import math
import os
import random
import subprocess
import sys

RANGES = {"exposure": (-2.0, 2.0), "contrast": (-1.0, 1.0), "black": (-0.25, 0.25),
          "saturation": (-1.0, 1.0), "warmth": (-1.0, 1.0), "tint": (-1.0, 1.0)}
FIELDS = tuple(RANGES)
LUMA = (0.2126, 0.7152, 0.0722)                  # Rec.709
SHIFT = 0.15                                     # a channel's gain at warmth or tint 1


def check(raw) -> dict:
    """A cut entry's `color`: the fields that aren't 0, rounded to 3 places,
    each a number in its range. {} for None or all zeros. ValueError says
    what's wrong."""
    if raw in (None, {}):
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"color is {{{', '.join(FIELDS)}}}, not {raw!r}")
    out = {}
    for k, v in raw.items():
        if k not in RANGES:
            raise ValueError(f"color has no {k!r} (it's {', '.join(FIELDS)})")
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError(f"color {k} is a number, not {v!r}")
        lo, hi = RANGES[k]
        if not lo <= v <= hi:
            raise ValueError(f"color {k} is {lo:g} to {hi:g}, not {v:g}")
        v = round(float(v), 3)
        if v:
            out[k] = v
    return out


def matrix(color: dict) -> tuple[list[list[float]], list[float]]:
    """(m, offset): out = m . rgb + offset per pixel, rgb in 0..1 (clipped
    after). Saturation around luma, then the channel gains (exposure,
    warmth, tint), then the contrast around mid grey, then the black point."""
    c = check(color)
    s = 1.0 + c.get("saturation", 0.0)
    sat = [[(1 - s) * LUMA[j] + (s if i == j else 0.0) for j in range(3)] for i in range(3)]
    w, t = c.get("warmth", 0.0), c.get("tint", 0.0)
    gain = 2.0 ** c.get("exposure", 0.0)
    gains = (gain * (1 + SHIFT * w), gain * (1 - SHIFT * t), gain * (1 - SHIFT * w))
    k = 2.0 ** c.get("contrast", 0.0)
    b = c.get("black", 0.0)
    m = [[(1 - b) * k * gains[i] * sat[i][j] for j in range(3)] for i in range(3)]
    o = (1 - b) * 0.5 * (1 - k) + b
    return m, [o, o, o]


def filters(color: dict) -> list[str]:
    """ffmpeg filters applying `color` to a clip (none for {}): its frames to
    full-range 16-bit RGB (BT.709), the matrix (colorchannelmixer), the offset
    the contrast and black point add (lutrgb), and back to BT.709 4:2:0,
    limited range. colorchannelmixer takes -2..2 and exposure alone can ask for
    4x, so the matrix is scaled into that and lutrgb scales it back (16 bits:
    nothing lost to it)."""
    c = check(color)
    if not c:
        return []
    m, off = matrix(c)
    s = max(1.0, max(abs(v) for row in m for v in row) / 1.99)
    names = "rgb"
    mix = ":".join(f"{names[i]}{names[j]}={m[i][j] / s:.6f}" for i in range(3) for j in range(3))
    lut = ":".join(f"{names[i]}='clip(val*{s:.6f}+{off[i]:.6f}*maxval,0,maxval)'"
                   for i in range(3))
    return ["scale=in_color_matrix=bt709:in_range=tv:out_range=pc", "format=gbrp16le",
            f"colorchannelmixer={mix}", f"lutrgb={lut}",
            "scale=out_color_matrix=bt709:out_range=tv", "format=yuv420p"]


# ---------------------------------------------------------------------------
# matching one clip to another
# ---------------------------------------------------------------------------

HELPER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "helpers", "colorstats.py")
SAMPLES = 5                                      # frames looked at, spread over what the cut uses


def sample_frames(first: int, last: int, n: int = SAMPLES) -> list[int]:
    """`n` frames spread evenly over first..last (inclusive), ends kept off."""
    if last < first:
        return [max(0, first)]
    span = last - first + 1
    return sorted({first + int((i + 0.5) * span / n) for i in range(min(n, span))})


# what a match compares (helpers/colorstats.py): the whole frame (six sliders), the
# skin in it (exposure, warmth, tint, saturation), or its brightness alone (exposure,
# contrast, black point); the sliders it doesn't set are the clip's own
MATCH_BY = ("frame", "skin", "luma")


def match(base: dict, clips: list[dict], by: str = "frame", python: str | None = None,
          timeout: int = 900) -> list[dict]:
    """The colour that brings each of `clips` in line with `base` (each
    {"path", "frames", "color"?}: a video, the frames of it to look at, and its
    colour in the cut; the base's is applied before it's compared, a clip's own
    replaced but for the sliders `by` doesn't set): helpers/colorstats.py, on
    this Python (it has numpy). A colour (check()'s shape) or {"error"} each.
    ValueError when the helper fails or `by` isn't one of MATCH_BY."""
    from seriesmith import ff as FF
    if by not in MATCH_BY:
        raise ValueError(f"by must be one of {', '.join(MATCH_BY)}")
    job = {"base": base, "clips": clips, "by": by}
    r = subprocess.run([python or sys.executable, HELPER, json.dumps(FF.tool("ffmpeg"))],
                       input=json.dumps(job), capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise ValueError((r.stderr or r.stdout or "matching the clips failed").strip()[-600:])
    return json.loads(r.stdout.strip().splitlines()[-1])


# ---------------------------------------------------------------------------
# a take's look, and the clips that are out of line with their sequence
# ---------------------------------------------------------------------------

LOOK_SIZE = (80, 45)                             # small: a look is a few numbers
LOOK_PIXELS = 128                                # kept in the take's record, as hex
# how far a clip may sit from its sequence's middle before it's out of line
OFF = {"exposure": 0.5, "contrast": 0.45, "warmth": 0.1, "tint": 0.07, "saturation": 0.5}
MIN_CLIPS = 3                                    # fewer: no middle to be out of line with


def look(mp4: str, frames: int | None) -> dict:
    """A take's look: {"px": LOOK_PIXELS of its pixels as hex ("rrggbb..."),
    "size": the mp4's bytes}, drawn evenly from SAMPLES frames spread across
    it (BT.709 RGB, full range). Few enough to keep in its record; enough to
    put through a colour, clipping and all, as the export would (_traits).
    Stdlib. ValueError when ffmpeg can't read it."""
    from seriesmith import ff as FF
    picks = sample_frames(0, max(0, (frames or 1) - 1))
    sel = "+".join(f"eq(n\\,{n})" for n in picks)
    w, h = LOOK_SIZE
    r = subprocess.run([*FF.tool("ffmpeg"), "-v", "error", "-i", mp4, "-vf",
                        f"select='{sel}',scale={w}:{h}:in_color_matrix=bt709:in_range=tv:"
                        "out_range=pc,format=rgb24", "-fps_mode", "passthrough", "-f", "rawvideo",
                        "-"], capture_output=True, timeout=300)
    data = r.stdout
    if r.returncode != 0 or len(data) < w * h * 3:
        raise ValueError(f"can't read {os.path.basename(mp4)}: "
                         + r.stderr.decode("utf-8", "replace")[-200:])
    n = len(data) // 3
    picked = sorted(random.Random(0).sample(range(n), min(LOOK_PIXELS, n)))
    return {"px": b"".join(data[k * 3:k * 3 + 3] for k in picked).hex(),
            "size": os.path.getsize(mp4)}


def _pixels(lk: dict) -> list[tuple[float, float, float]]:
    raw = bytes.fromhex(lk["px"])
    return [(raw[i] / 255, raw[i + 1] / 255, raw[i + 2] / 255) for i in range(0, len(raw) - 2, 3)]


def _traits(lk: dict, color: dict | None) -> dict:
    """What's compared, of a look's pixels as a clip's colour leaves them (the
    matrix and its clipping: what the export does): the mean colour's
    brightness, red / blue and green balance, the luma's 5th..95th spread, the
    midtones' distance from grey."""
    m, off = matrix(color or {})
    px = [tuple(max(0.0, min(1.0, m[i][0] * p[0] + m[i][1] * p[1] + m[i][2] * p[2] + off[i]))
                for i in range(3)) for p in _pixels(lk)]
    n = len(px)
    mean = [max(1e-4, sum(p[c] for p in px) / n) for c in range(3)]
    lum = [LUMA[0] * p[0] + LUMA[1] * p[1] + LUMA[2] * p[2] for p in px]
    ys = sorted(lum)
    mids = [(p, y) for p, y in zip(px, lum) if 0.15 < y < 0.85]
    chroma = (sum(math.sqrt(sum((p[c] - y) ** 2 for c in range(3))) for p, y in mids) / len(mids)
              if mids else 0.0)
    return {"exposure": math.log2(sum(LUMA[i] * mean[i] for i in range(3))),
            "contrast": math.log2(max(1e-3, ys[int(0.95 * (n - 1))] - ys[int(0.05 * (n - 1))])),
            "warmth": math.log(mean[0] / mean[2]),
            "tint": math.log(mean[1] / math.sqrt(mean[0] * mean[2])),
            "saturation": math.log2(max(1e-4, chroma))}


def _median(vals: list[float]) -> float:
    v = sorted(vals)
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


WORDS = {"exposure": ("{:.1f} stop brighter", "{:.1f} stop darker"),
         "contrast": ("punchier", "flatter"), "warmth": ("warmer", "cooler"),
         "tint": ("greener", "more magenta"), "saturation": ("more colourful", "less colourful")}


def out_of_line(clips: dict[str, tuple[dict, dict | None]]) -> dict[str, list[str]]:
    """{shot: what's off} for the clips (shot -> (look, colour in the cut)) of
    one sequence that sit too far from its middle (OFF), each as words ("0.8
    stop darker", "cooler"); a clip in line isn't listed. Fewer than MIN_CLIPS
    looks: nothing (no middle to be out of line with)."""
    if len(clips) < MIN_CLIPS:
        return {}
    traits = {s: _traits(lk, col) for s, (lk, col) in clips.items()}
    middle = {k: _median([t[k] for t in traits.values()]) for k in OFF}
    out = {}
    for s, t in traits.items():
        said = []
        for k, limit in OFF.items():
            d = t[k] - middle[k]
            if abs(d) > limit:
                up, down = WORDS[k]
                said.append((up if d > 0 else down).format(abs(d)))
        if said:
            out[s] = said
    return out


def record_look(take) -> dict | None:
    """Measure a finished take's look into its record (`look`), once: what the
    timeline's out-of-line badge compares. Never raises (a take without one
    just isn't compared); the look, or None."""
    from seriesmith import takes as T
    try:
        sc = T.read_sidecar(take.paths.sidecar) or {}
        if sc.get("status") != "ok" or not os.path.isfile(take.paths.mp4):
            return None
        lk = look(take.paths.mp4, sc.get("frames"))
        take.sidecar = T.update_sidecar(take.paths.sidecar, look=lk)
        return lk
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def look_of(sidecar: dict | None, mp4: str | None = None) -> dict | None:
    """A take's recorded look, unless its mp4 has changed since (its size)."""
    lk = (sidecar or {}).get("look")
    if not isinstance(lk, dict) or not lk.get("px"):
        return None
    if mp4 and lk.get("size") and os.path.isfile(mp4) and os.path.getsize(mp4) != lk["size"]:
        return None
    return lk
