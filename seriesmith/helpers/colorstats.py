#!/usr/bin/env python3
"""
colorstats.py — the colour that brings clips in line with a base clip
(seriesmith/color.py, `match`). numpy only, beside seriesmith/color.py's maths.

The pipeline is stdlib only, so color.py runs this file as a subprocess of the
running Python (ComfyUI's under the editor's routes, which has numpy), as
tour.py runs stills.py:

    python colorstats.py FFMPEG < JOB

JOB (stdin, JSON) is {"base": CLIP, "clips": [CLIP, ...], "by"?}, each CLIP
{"path", "frames": [n, ...], "color"?}: a video, the frames of it to look at
(from 0), and the colour it has in the cut (the base's is applied before it's
measured; a clip's own is replaced, but for what `by` leaves alone). Prints one
JSON list, a colour (color.check's shape) or {"error": ...} for each clip.

A clip's pixels (the frames scaled to WIDTH x HEIGHT, 0..1 BT.709 RGB, full
range: what color.filters works on) are put through color.matrix and clipped,
exactly as the export does, and the sliders searched (Nelder-Mead) for the look
nearest the base's. What's compared is `by` (color.MATCH_BY):

    frame   the whole picture, six sliders: each channel's 5th..95th
            percentiles (where its blacks, mids and highlights sit, so
            exposure, contrast, the black point and any cast), its mean, and
            the midtones' mean distance from grey (saturation). It matches
            what's in the picture as well as its light: a frame of green
            dresses pulls a pale close-up green.
    skin    the skin in each (found once, on the pictures as they are: lit,
            red over green over blue, neither grey nor hair), six sliders: its
            brightness and spread, its cast, its saturation. The light on the
            people, whatever else is in the frame; a clip (or a base) with too
            little skin is said, not matched.
    luma    the brightness alone (luma's 5th..95th percentiles): exposure,
            contrast and the black point; the clip's warmth, tint and
            saturation in the cut kept.
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


def is_skin(rgb: np.ndarray) -> np.ndarray:
    """The pixels that look like lit skin: YCbCr's skin box (narrowed), red over
    green over blue, some colour but not much (not grey walls, not wood in
    shadow, not blond hair), not clipped."""
    r, g, b = (rgb * 255).T
    y = 0.299 * r + 0.587 * g + 0.114 * b
    cb = 128 - 0.168736 * r - 0.331264 * g + 0.5 * b
    cr = 128 + 0.5 * r - 0.418688 * g - 0.081312 * b
    hi, lo = rgb.max(axis=1), rgb.min(axis=1)
    sat = (hi - lo) / np.maximum(hi, 1e-3)
    return ((cb > 85) & (cb < 125) & (cr > 138) & (cr < 168) & (y > 70) & (y < 240)
            & (r > g) & (g > b) & (r - g > 12) & (sat > 0.1) & (sat < 0.6) & (hi < 0.97))


SKIN_LEAST = 0.02                             # of a clip's pixels: fewer, and it isn't matched by skin


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


def look_skin(rgb: np.ndarray) -> np.ndarray:
    """What's compared of the skin: its brightness (median luma), its cast (red /
    blue, green / both), its saturation. Not its spread: how hard a face is lit
    is the shot's, and matching it moved the exposure a stop."""
    y = rgb @ LUMA
    m = rgb.mean(axis=0) + 1e-4
    chroma = np.sqrt(((rgb - y[:, None]) ** 2).sum(axis=1)).mean()
    return np.array([3 * np.log2(np.median(y) + 1e-4),
                     2 * np.log(m[0] / m[2]), 2 * np.log(m[1] / np.sqrt(m[0] * m[2])),
                     np.log2(chroma + 1e-4)])


def look_luma(rgb: np.ndarray) -> np.ndarray:
    return np.percentile(rgb @ LUMA, PERCENTILES)


LOOKS = {"frame": look, "skin": look_skin, "luma": look_luma}
FIELDS = list(C.FIELDS)
SEARCHED = {"frame": FIELDS, "skin": ["exposure", "saturation", "warmth", "tint"],
            "luma": ["exposure", "contrast", "black"]}
SPAN = {k: C.RANGES[k][1] for k in FIELDS}              # a search unit: each field's range


def to_color(x: np.ndarray, fields: list[str] | None = None, keep: dict | None = None) -> dict:
    """The colour of search point `x` (one value per `fields`), the rest from `keep`."""
    out = {k: float((keep or {}).get(k, 0.0)) for k in FIELDS}
    out.update({k: float(np.clip(v * SPAN[k], C.RANGES[k][0], C.RANGES[k][1]))
                for k, v in zip(fields or FIELDS, x)})
    return out


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
    return {k: float(np.clip(x[k] / SPAN[k], -1, 1)) for k in FIELDS}


def match(base_rgb: np.ndarray, clip_rgb: np.ndarray, by: str = "frame",
          keep: dict | None = None) -> dict:
    """The colour bringing `clip_rgb` in line with `base_rgb` (as the cut colours
    it), compared `by` (frame, skin, luma); `keep`: the clip's colour in the cut,
    its fields that `by` doesn't search kept. ValueError when skin is asked of a
    picture with too little."""
    fields, keep = SEARCHED[by], keep or {}
    if by == "skin":
        # found once, on the pictures as they are: a trial colour mustn't move it
        bs, cs = is_skin(base_rgb), is_skin(clip_rgb)
        if bs.mean() < SKIN_LEAST:
            raise ValueError("too little skin in the base clip to match by (try Frame)")
        if cs.mean() < SKIN_LEAST:
            raise ValueError("too little skin in it to match by (try Frame)")
        rng = np.random.default_rng(0)
        base_rgb, clip_rgb = sample(base_rgb[bs], rng), sample(clip_rgb[cs], rng)
        start = guess(base_rgb, clip_rgb)
    else:
        start = guess(base_rgb, clip_rgb)
    see = LOOKS[by]
    want = see(base_rgb)

    def cost(x: np.ndarray) -> float:
        over = np.abs(x) > 1                      # outside a slider's range
        return float(((see(apply(clip_rgb, to_color(x, fields, keep))) - want) ** 2).sum()
                     + 10 * (np.abs(x[over]) - 1).sum()
                     # the least change that does it: exposure, contrast and the black
                     # point can make nearly the same picture between them
                     + SIMPLER * (x ** 2).sum())
    # from no change, and from what the mean colours say (exposure, warmth, tint):
    # the better of the two, searched again from there (past a local stall)
    tries = [nelder_mead(cost, np.zeros(len(fields))),
             nelder_mead(cost, np.array([start[k] for k in fields]))]
    x = min(tries, key=cost)
    x = nelder_mead(cost, x, step=0.05)
    return C.check({k: round(v, 3) for k, v in to_color(x, fields, keep).items()})


def sample(rgb: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    if len(rgb) <= PIXELS:
        return rgb
    return rgb[rng.choice(len(rgb), PIXELS, replace=False)]


def main() -> int:
    ffmpeg = sys.argv[1]
    job = json.load(sys.stdin)
    rng = np.random.default_rng(0)                # the same answer every time
    by = job.get("by") or "frame"
    # skin is a few percent of a picture: found among all its pixels, sampled after
    pick = (lambda rgb: rgb) if by == "skin" else (lambda rgb: sample(rgb, rng))
    b = job["base"]
    base = pick(frames(ffmpeg, b["path"], b["frames"]))
    if b.get("color"):
        base = apply(base, b["color"])
    out = []
    for c in job["clips"]:
        try:
            out.append(match(base, pick(frames(ffmpeg, c["path"], c["frames"])), by,
                             c.get("color")))
        except (subprocess.CalledProcessError, ValueError) as e:
            err = getattr(e, "stderr", b"") or b""
            out.append({"error": (str(e) + " " + err.decode("utf-8", "replace"))[-300:]})
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
