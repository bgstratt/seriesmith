"""
checks.py — the exported cut's picture checked, never changed (docs/FINISHING.md "The
export's checks"): black runs, frozen runs and flashes, each with its times and the shot
playing then. Written beside the cut as `<cut>_checks.json` (the loudness, the sound's check,
is `<cut>_loudness.json`: mix.loudness_check).

One ffmpeg pass over the cut's picture, scaled down to SCALE_W wide (the checks read the
frame's average and its changes, which the size doesn't change; the decode is most of the
cost): `blackdetect` (BLACK: at least 0.5 s with 98 % of the picture below 10 % luma),
`freezedetect` (FREEZE: at least 2 s with the frames within -60 dB of each other) and each
frame's average luma (`signalstats` YAVG) for the flash check.

**Flashes.** The common guideline (WCAG 2.3.1, after ITU-R BT.1702 and Ofcom's): no more than
three flashes in any one second, a flash being a pair of opposing changes in relative
luminance of 10 % or more of the maximum where the darker is below 0.80. Read here on the
whole frame's average: each frame's mean luma as relative luminance (limited range to 0-1,
gamma 2.2), its turns (the extremes between which it moves by FLASH_DELTA or more, the darker
end below FLASH_DARK), and a run where more than FLASH_PER_S flashes (2 x FLASH_PER_S turns)
fall in any one second. A whole-frame check: a flash over part of the picture (the guideline's
quarter of the screen), or a saturated red flash, is not seen; it is a warning to look, not a
broadcaster's test (a Harding test is that).

**What the cut explains** is left out: black or frozen frames inside a clip's own fade in or
out (the cut entry's `fade_in` / `fade_out`, as assemble laid them) or a held shot (the `hold`
target: a still on purpose), each a frame either side; a frozen run inside a black one is the
black run, said once.

Stdlib; ffmpeg through seriesmith.ff.
"""
from __future__ import annotations

import re
import subprocess

from seriesmith import ff as FF

SUFFIX = "_checks.json"
SCALE_W = 256
BLACK = {"d": 0.5, "pix_th": 0.10, "pic_th": 0.98}
FREEZE = {"n": "-60dB", "d": 2.0}
FLASH_DELTA = 0.10                 # relative luminance, of the maximum (1.0)
FLASH_DARK = 0.80                  # the darker end of a flash's change is below this
FLASH_PER_S = 3                    # more flashes than this in any one second is flagged
TIMEOUT = 3600

_BLACK = re.compile(r"black_start:\s*([\d.]+)\s+black_end:\s*([\d.]+)")
_FREEZE = re.compile(r"lavfi\.freezedetect\.freeze_(start|end):\s*([\d.]+)")
_PTS = re.compile(r"pts_time:\s*([-\d.]+)")
_YAVG = re.compile(r"lavfi\.signalstats\.YAVG=([\d.]+)")


def rules() -> dict:
    """The thresholds, as the report keeps them."""
    return {"black": {"min_seconds": BLACK["d"], "luma_below": BLACK["pix_th"], "of_picture": BLACK["pic_th"]},
            "frozen": {"min_seconds": FREEZE["d"], "noise": FREEZE["n"]},
            "flashes": {"luminance_change": FLASH_DELTA, "darker_below": FLASH_DARK,
                        "more_than_per_second": FLASH_PER_S, "area": "the whole frame's average"}}


def scan(path: str, timeout: int = TIMEOUT) -> dict:
    """The cut read once: {"black": [(start, end)], "frozen": [(start, end | None)], "luma":
    [(t, mean luma 0-255)]}. RuntimeError when ffmpeg fails."""
    vf = (f"scale={SCALE_W}:-2,"
          f"blackdetect=d={BLACK['d']}:pix_th={BLACK['pix_th']}:pic_th={BLACK['pic_th']},"
          f"freezedetect=n={FREEZE['n']}:d={FREEZE['d']},"
          "signalstats,metadata=mode=print:key=lavfi.signalstats.YAVG")
    r = subprocess.run([*FF.tool("ffmpeg"), "-hide_banner", "-nostats", "-v", "info", "-i", path,
                        "-map", "0:v:0", "-vf", vf, "-an", "-f", "null", "-"],
                       capture_output=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace")[-400:])
    return parse(r.stderr.decode("utf-8", "replace"))


def parse(log: str) -> dict:
    """What scan's ffmpeg said (its log), read: see scan."""
    black, frozen, luma = [], [], []
    t = None
    for line in log.splitlines():
        m = _BLACK.search(line)
        if m:
            black.append((float(m.group(1)), float(m.group(2))))
            continue
        m = _FREEZE.search(line)
        if m:
            if m.group(1) == "start":
                frozen.append((float(m.group(2)), None))
            elif frozen and frozen[-1][1] is None:
                frozen[-1] = (frozen[-1][0], float(m.group(2)))
            continue
        m = _PTS.search(line)
        if m and "frame:" in line:
            t = float(m.group(1))
            continue
        m = _YAVG.search(line)
        if m and t is not None:
            luma.append((t, float(m.group(1))))
            t = None
    return {"black": black, "frozen": frozen, "luma": luma}


def relative(y: float) -> float:
    """A frame's mean luma (8-bit, limited range) as relative luminance 0-1 (gamma 2.2)."""
    v = min(1.0, max(0.0, (y - 16.0) / 219.0))
    return v ** 2.2


def turns(luma: list[tuple[float, float]]) -> list[tuple[float, float, float]]:
    """The changes in relative luminance that count toward a flash: [(t, from, to)], `t` the
    frame each ends on. The luminance is followed from turn to turn (a zigzag: a turn is an
    extreme it then moves back from by FLASH_DELTA or more), and each move between two turns
    with its darker end below FLASH_DARK is a change."""
    if not luma:
        return []
    t0, v0 = luma[0][0], relative(luma[0][1])
    hi, lo = (t0, v0), (t0, v0)
    pivots, trend, ext = [], 0, None
    for t, y in luma[1:]:
        v = relative(y)
        if trend == 0:
            hi = (t, v) if v >= hi[1] else hi
            lo = (t, v) if v <= lo[1] else lo
            if hi[1] - lo[1] >= FLASH_DELTA:
                up = hi[0] > lo[0]
                pivots, trend, ext = [lo if up else hi], (1 if up else -1), (hi if up else lo)
        elif (v - ext[1]) * trend >= 0:
            ext = (t, v)                                 # further the same way
        elif abs(ext[1] - v) >= FLASH_DELTA:
            pivots.append(ext)                           # it turned
            trend, ext = -trend, (t, v)
    if trend:
        pivots.append(ext)
    return [(b[0], a[1], b[1]) for a, b in zip(pivots, pivots[1:]) if min(a[1], b[1]) < FLASH_DARK]


def flash_runs(luma: list[tuple[float, float]]) -> list[dict]:
    """The stretches where more than FLASH_PER_S flashes (pairs of opposing changes: turns)
    fall within one second: [{"start", "end", "flashes" (the most in any one second)}]."""
    ts = [t for t, _, _ in turns(luma)]
    limit = 2 * FLASH_PER_S              # changes: a flash is two
    runs = []
    j = 0
    for i in range(len(ts)):
        while ts[i] - ts[j] > 1.0:
            j += 1
        n = i - j + 1
        if n > limit:
            a, b = ts[j], ts[i]
            if runs and a <= runs[-1]["end"]:
                runs[-1]["end"] = b
                runs[-1]["flashes"] = max(runs[-1]["flashes"], n // 2)
            else:
                runs.append({"start": a, "end": b, "flashes": n // 2})
    return runs


def _covered(a: float, b: float, spans: list[tuple[float, float]], tol: float) -> bool:
    """Whether [a, b] lies inside the union of `spans` (each widened by `tol`)."""
    t = a
    for s, e in sorted(spans):
        if s - tol <= t <= e + tol:
            t = max(t, e + tol)
            if t >= b:
                return True
    return t >= b


def _minus(a: float, b: float, spans: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """[a, b] less the `spans`."""
    out = [(a, b)]
    for s, e in spans:
        nxt = []
        for x, y in out:
            if e <= x or s >= y:
                nxt.append((x, y))
                continue
            if s > x:
                nxt.append((x, s))
            if e < y:
                nxt.append((e, y))
        out = nxt
    return out


def shots_in(a: float, b: float, clips: list[dict]) -> list[str]:
    """The shots playing between a and b (seconds), in cut order."""
    return [c["id"] for c in clips if c["a"] < b and c["b"] > a] or [c["id"] for c in clips[-1:] if a >= c["a"]]


def check(path: str, clips: list[dict], fps: float, seconds: float | None = None,
          scanned: dict | None = None) -> dict:
    """The cut at `path` checked. `clips` are its shots as assemble laid them, in cut order
    ({"id", "a", "b" (seconds in the cut), "fade_in", "fade_out" (seconds), "held"}). The
    report: {"black": [run], "frozen": [run], "flashes": [run], "explained": {"black", "frozen"}
    (runs the cut's fades and held shots explain, left out), "rules", "ok", "verdict"}; a run
    is {"start", "end", "seconds", "shot" (the first shot in it), "shots"}, a flash run also
    "flashes" (the most in any one second)."""
    s = scanned if scanned is not None else scan(path)
    end = seconds if seconds is not None else (clips[-1]["b"] if clips else 0.0)
    tol = 1.0 / (fps or 24)
    fades, held = [], []
    for c in clips:
        if c.get("fade_in"):
            fades.append((c["a"], c["a"] + c["fade_in"]))
        if c.get("fade_out"):
            fades.append((c["b"] - c["fade_out"], c["b"]))
        if c.get("held"):
            held.append((c["a"], c["b"]))

    def run(a, b, **extra):
        sh = shots_in(a, b, clips)
        return {"start": round(a, 3), "end": round(b, 3), "seconds": round(b - a, 3),
                "shot": sh[0] if sh else None, "shots": sh, **extra}

    explained = {"black": 0, "frozen": 0}
    black = []
    for a, b in s["black"]:
        if _covered(a, b, fades + held, tol):
            explained["black"] += 1
        else:
            black.append(run(a, b))
    frozen = []
    for a, b in s["frozen"]:
        b = end if b is None else b
        # black frames are frozen too: a frozen run is what is left of it outside the black
        rest = [(x, y) for x, y in _minus(a, b, s["black"]) if y - x >= FREEZE["d"] - tol]
        if not rest:
            continue
        if all(_covered(x, y, fades + held, tol) for x, y in rest):
            explained["frozen"] += 1
            continue
        frozen += [run(x, y) for x, y in rest if not _covered(x, y, fades + held, tol)]
    flashes = [run(r["start"], r["end"], flashes=r["flashes"]) for r in flash_runs(s["luma"])]
    ok = not (black or frozen or flashes)
    return {"black": black, "frozen": frozen, "flashes": flashes, "explained": explained,
            "rules": rules(), "ok": ok, "verdict": verdict(black, frozen, flashes, explained)}


def _tc(t: float) -> str:
    m, s = divmod(t, 60.0)
    return f"{int(m):02d}:{s:04.1f}"


def verdict(black: list, frozen: list, flashes: list, explained: dict) -> str:
    """The report in words: "no black, frozen or flashing runs", else each kind counted."""
    parts = []
    for name, runs in (("black", black), ("frozen", frozen)):
        if runs:
            parts.append(f"{len(runs)} {name} run{'s' if len(runs) != 1 else ''} ("
                         + ", ".join(f"{r['shot']} {_tc(r['start'])} {r['seconds']:.1f} s" for r in runs[:3])
                         + (", ..." if len(runs) > 3 else "") + ")")
    if flashes:
        parts.append(f"{len(flashes)} flashing run{'s' if len(flashes) != 1 else ''} ("
                     + ", ".join(f"{r['shot']} {_tc(r['start'])}, {r['flashes']} a second" for r in flashes[:3])
                     + (", ..." if len(flashes) > 3 else "") + ")")
    said = "; ".join(parts) if parts else "no black, frozen or flashing runs"
    left = [f"{n} {k}" for k, n in explained.items() if n]
    return said + (f" ({' and '.join(left)} left out: the cut's own fades and held shots)" if left else "")
