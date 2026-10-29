#!/usr/bin/env python3
"""
colorstats.py — the colour that brings clips in line with a base clip
(seriesmith/color.py, `match`). numpy only, beside seriesmith/color.py's maths.

The pipeline is stdlib only, so color.py runs this file as a subprocess of the
running Python (ComfyUI's under the editor's routes, which has numpy), as
tour.py runs stills.py:

    python colorstats.py FFMPEG < JOB

JOB (stdin, JSON) is {"base": CLIP, "clips": [CLIP, ...]}, each CLIP {"path",
"frames": [n, ...], "color"?}: a video, the frames of it to look at (from 0),
and the colour it has in the cut (the base's is applied before it's measured;
a clip's own is replaced). Prints one JSON list, a colour (color.check's
shape) or {"error": ...} for each clip.

A clip's pixels (the frames scaled to WIDTH x HEIGHT, 0..1 BT.709 RGB, full
range: what color.filters works on) are put through color.matrix and clipped,
exactly as the export does, and the six sliders searched (Nelder-Mead) for the
look nearest the base's: each channel's 5th..95th percentiles (where its
blacks, mids and highlights sit, so exposure, contrast, the black point and
any cast) and the midtones' mean distance from grey (saturation).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from seriesmith import color as C  # noqa: E402  (stdlib: the same maths as the export)

WIDTH, HEIGHT = 160, 90
PIXELS = 12000                                # sampled for the search
LUMA = np.array(C.LUMA)
PERCENTILES = [5, 25, 50, 75, 95]
CHROMA_WEIGHT = 3.0                           # saturation counts as much as a channel's spread
MEAN_WEIGHT = 3.0                             # the mean colour: the cast, as the check reads it
SIMPLER = 2e-4                                # a pull towards 0, against what's equivalent


def _cmd(tool: str) -> list[str]:
    return json.loads(tool) if tool.startswith("[") else [tool]


def frames(ffmpeg: str, path: str, picks: list[int]) -> np.ndarray:
    """The frames `picks` of `path` as one (n * h * w, 3) float array, 0..1."""
    sel = "+".join(f"eq(n\\,{int(n)})" for n in picks)
    # a fixed size: percentiles and means don't mind the aspect
    r = subprocess.run([*_cmd(ffmpeg), "-v", "error", "-i", path, "-vf",
                        f"select='{sel}',scale={WIDTH}:{HEIGHT}:in_color_matrix=bt709:in_range=tv:"
                        "out_range=pc,format=rgb24", "-fps_mode", "passthrough",
                        "-f", "rawvideo", "-"], capture_output=True, check=True)
    data = np.frombuffer(r.stdout, dtype=np.uint8)
    n = data.size // (WIDTH * HEIGHT * 3)
    if not n:
        raise ValueError(f"no frames read from {path}")
    return data[: n * WIDTH * HEIGHT * 3].reshape(-1, 3).astype(np.float64) / 255.0


def apply(rgb: np.ndarray, color: dict) -> np.ndarray:
    m, off = C.matrix(color)
    return np.clip(rgb @ np.array(m).T + np.array(off), 0.0, 1.0)


def look(rgb: np.ndarray) -> np.ndarray:
    """What's compared: each channel's percentiles, its mean (as the timeline's
    out-of-line check sees a clip: color.out_of_line), then the midtones'
    chroma."""
    y = rgb @ LUMA
    mid = (y > 0.15) & (y < 0.85)
    if mid.sum() < 50:
        mid = np.ones_like(y, dtype=bool)
    chroma = np.sqrt(((rgb[mid] - y[mid, None]) ** 2).sum(axis=1)).mean()
    pct = np.percentile(rgb, PERCENTILES, axis=0).T.ravel()
    return np.concatenate([pct, MEAN_WEIGHT * rgb.mean(axis=0), [CHROMA_WEIGHT * chroma]])


FIELDS = list(C.FIELDS)
SPAN = np.array([C.RANGES[k][1] for k in FIELDS])        # a search unit: each field's range


def to_color(x: np.ndarray) -> dict:
    return {k: float(np.clip(v * s, C.RANGES[k][0], C.RANGES[k][1]))
            for k, v, s in zip(FIELDS, x, SPAN)}


def nelder_mead(f, x0: np.ndarray, step: float = 0.15, iters: int = 400,
                tol: float = 1e-7) -> np.ndarray:
    n = len(x0)
    pts = [x0] + [x0 + step * np.eye(n)[i] for i in range(n)]
    vals = [f(p) for p in pts]
    for _ in range(iters):
        order = np.argsort(vals)
        pts, vals = [pts[i] for i in order], [vals[i] for i in order]
        if vals[-1] - vals[0] < tol:
            break
        centre = np.mean(pts[:-1], axis=0)
        refl = centre + (centre - pts[-1])
        fr = f(refl)
        if fr < vals[0]:
            exp = centre + 2 * (centre - pts[-1])
            fe = f(exp)
            pts[-1], vals[-1] = (exp, fe) if fe < fr else (refl, fr)
        elif fr < vals[-2]:
            pts[-1], vals[-1] = refl, fr
        else:
            con = centre + 0.5 * (pts[-1] - centre)
            fc = f(con)
            if fc < vals[-1]:
                pts[-1], vals[-1] = con, fc
            else:                                 # shrink towards the best
                pts = [pts[0]] + [pts[0] + 0.5 * (p - pts[0]) for p in pts[1:]]
                vals = [vals[0]] + [f(p) for p in pts[1:]]
    return pts[int(np.argmin(vals))]


def guess(base_rgb: np.ndarray, clip_rgb: np.ndarray) -> np.ndarray:
    """A start: the exposure, warmth and tint that line up the mean colours."""
    b, c = base_rgb.mean(axis=0) + 1e-4, clip_rgb.mean(axis=0) + 1e-4
    x = dict.fromkeys(FIELDS, 0.0)
    x["exposure"] = float(np.log2((b @ LUMA) / (c @ LUMA)))
    q = (b[0] / b[2]) / (c[0] / c[2])
    x["warmth"] = float((q - 1) / (C.SHIFT * (q + 1)))
    g = (b[1] / np.sqrt(b[0] * b[2])) / (c[1] / np.sqrt(c[0] * c[2]))
    x["tint"] = float((1 - g) / C.SHIFT)
    return np.clip(np.array([x[k] for k in FIELDS]) / SPAN, -1, 1)


def match(base_rgb: np.ndarray, clip_rgb: np.ndarray) -> dict:
    want = look(base_rgb)

    def cost(x: np.ndarray) -> float:
        over = np.abs(x) > 1                      # outside a slider's range
        return float(((look(apply(clip_rgb, to_color(x))) - want) ** 2).sum()
                     + 10 * (np.abs(x[over]) - 1).sum()
                     # the least change that does it: exposure, contrast and the black
                     # point can make nearly the same picture between them
                     + SIMPLER * (x ** 2).sum())
    # from no change, and from what the mean colours say (exposure, warmth, tint):
    # the better of the two, searched again from there (past a local stall)
    tries = [nelder_mead(cost, np.zeros(len(FIELDS))), nelder_mead(cost, guess(base_rgb, clip_rgb))]
    x = min(tries, key=cost)
    x = nelder_mead(cost, x, step=0.05)
    return C.check({k: round(v, 3) for k, v in to_color(x).items()})


def sample(rgb: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    if len(rgb) <= PIXELS:
        return rgb
    return rgb[rng.choice(len(rgb), PIXELS, replace=False)]


def main() -> int:
    ffmpeg = sys.argv[1]
    job = json.load(sys.stdin)
    rng = np.random.default_rng(0)                # the same answer every time
    b = job["base"]
    base = sample(frames(ffmpeg, b["path"], b["frames"]), rng)
    if b.get("color"):
        base = apply(base, b["color"])
    out = []
    for c in job["clips"]:
        try:
            out.append(match(base, sample(frames(ffmpeg, c["path"], c["frames"]), rng)))
        except (subprocess.CalledProcessError, ValueError) as e:
            err = getattr(e, "stderr", b"") or b""
            out.append({"error": (str(e) + " " + err.decode("utf-8", "replace"))[-300:]})
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
