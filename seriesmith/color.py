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

Stdlib only.
"""
from __future__ import annotations

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
    full-range RGB (BT.709), the matrix (colorchannelmixer), the offset the
    contrast and black point add (lutrgb), and back to BT.709 4:2:0, limited
    range."""
    c = check(color)
    if not c:
        return []
    m, off = matrix(c)
    names = "rgb"
    mix = ":".join(f"{names[i]}{names[j]}={m[i][j]:.6f}" for i in range(3) for j in range(3))
    lut = ":".join(f"{names[i]}='clip(val+{off[i] * 255:.4f},0,255)'" for i in range(3))
    return ["scale=in_color_matrix=bt709:in_range=tv:out_range=pc", "format=gbrp",
            f"colorchannelmixer={mix}", f"lutrgb={lut}",
            "scale=out_color_matrix=bt709:out_range=tv", "format=yuv420p"]
