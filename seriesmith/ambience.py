"""
ambience.py — a place's ambience bed: finished as it lands, and laid under the cut
(docs/SOUND.md phase 3).

A bed is a ref (refs.py `ambience:<place>`): the series config's `ambience` words of a
location's place (core.series_config.ambience_bed_of) made into a take on an `ambience`
target (targets/ambience/), one take picked into the bed's file. A take is **finished as it
lands** (finish_bed): its first and last EDGE_S seconds dropped (a model's bed swells in and
trails off: "Measured: ambience beds"), then brought to BED_LUFS by one gain, so the
Ambience fader means the same for every place.

**Laid from the cut, never stored** (laid): each run of consecutive shots in the cut whose
sequence is set in one place with a bed gets that bed, looped (mix.looped, equal power),
the runs crossfaded RUN_XFADE_S into each other at the boundaries; a shot whose place has
no bed gets none. The mix keeps only what you change, `beds: {place: {gain_db, mute}}`
(mix.check). The beds then sit on the Ambience track: its fader and its ducking apply,
and an item you put on the track plays over them.
"""

from __future__ import annotations

import json
import os

from seriesmith import mix as MX
from seriesmith.core import fileio as F
from seriesmith.core import paths as P
from seriesmith.core import series_config as SC

BED_LUFS = -32.0          # room tone well under the lines at the fader's 0 dB
EDGE_S = 1.5              # off each end of a take: the model's swell in and trail off
EDGE_MIN_S = 3.0 * EDGE_S  # a take shorter than this keeps its ends
RUN_XFADE_S = 0.5         # two places' beds crossfaded at the cut between them


# ---------------------------------------------------------------------------
# a take, finished as it lands
# ---------------------------------------------------------------------------

def finish_bed(src: str, dst: str) -> dict:
    """`src` (any audio file) as a bed in `dst` (24-bit 48 kHz stereo wav): EDGE_S off
    each end when it's long enough, then one gain to BED_LUFS (loudnorm's measure).
    Returns {"seconds", "trimmed", "measured_lufs", "gain_db"}. RuntimeError when it has
    no sound."""
    np = MX._np()
    buf = MX.decode(src)
    if len(buf) == 0:
        raise RuntimeError(f"{os.path.basename(src)} has no sound")
    edge = int(EDGE_S * MX.RATE)
    trimmed = len(buf) >= EDGE_MIN_S * MX.RATE
    if trimmed:
        buf = buf[edge: len(buf) - edge]
    tmp = F.temp_beside(dst, ".wav")
    try:
        MX.write_wav(tmp, buf)
        m = MX.measure(tmp, BED_LUFS, -1.0)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    lufs = (m or {}).get("input_i")
    gain = 0.0
    if lufs is not None and np.isfinite(lufs) and lufs > -70:
        gain = BED_LUFS - lufs
    MX.write_wav(dst, buf * MX._db(gain))
    return {"seconds": round(len(buf) / MX.RATE, 3), "trimmed": trimmed,
            "measured_lufs": None if lufs is None else round(float(lufs), 2),
            "gain_db": round(gain, 2)}


# ---------------------------------------------------------------------------
# the beds under the cut
# ---------------------------------------------------------------------------

def shot_locations(root: str) -> dict[str, str]:
    """{shot id: its sequence's location} from the episode's story IR
    (shotlist/shots.json); {} when it can't be read."""
    try:
        with open(os.path.join(root, "shotlist", "shots.json"), encoding="utf-8") as fh:
            story = json.load(fh)
    except (OSError, ValueError):
        return {}
    out = {}
    for sq in story.get("sequences") or []:
        for sh in sq.get("shots") or []:
            if isinstance(sh, dict) and sh.get("id"):
                out[sh["id"]] = sq.get("location") or ""
    return out


def series_home(root: str) -> str | None:
    """The folder holding the episode's series config (bed paths start there)."""
    p = P.series_config_path(root)
    return os.path.dirname(os.path.abspath(p)) if p else None


def runs(layout: list[dict], beds_of: dict[str, dict | None]) -> list[dict]:
    """Runs of consecutive clips of the cut (`layout`: [{"id", "trim_in", "used",
    "dissolve_in"}] as assemble lays them) that play over one bed: [{"bed": its dict,
    "shots": [ids], "start", "end" (cut frames)}]. `beds_of[shot]` is the shot's bed
    (None: none). A dissolve's overlap goes to the later clip."""
    origins = MX.shot_origins(layout)
    out: list[dict] = []
    for x in layout:
        bed = beds_of.get(x["id"])
        o = origins[x["id"]]
        s, e = o["origin"] + o["first"], o["origin"] + o["first"] + x["used"]
        if out and out[-1]["end"] > s:
            out[-1]["end"] = max(out[-1]["start"], s)     # the later clip has the overlap
        if bed is None:
            continue
        if out and out[-1]["bed"]["id"] == bed["id"] and out[-1]["end"] >= s:
            out[-1]["end"] = e
            out[-1]["shots"].append(x["id"])
        else:
            out.append({"bed": bed, "shots": [x["id"]], "start": s, "end": e})
    return [r for r in out if r["end"] > r["start"]]


def laid(root: str, layout: list[dict], series_cfg: dict | None, mix: dict | None = None
         ) -> list[dict]:
    """The beds under a cut: one per run (runs), [{"place" (the bed's id), "label" (its
    location's name), "path" (absolute), "rel" (relative to the episode), "words",
    "exists", "shots", "start", "end" (cut frames), "in" / "out" (anchors: the first
    shot's first frame played, the last's frame after its last), "gain_db", "mute"
    (the mix's `beds`)}]. Nothing decoded: cheap enough for every GET of the mix."""
    if not series_cfg or not layout:
        return []
    home = series_home(root) or root
    locs = shot_locations(root)
    cache: dict[str, dict | None] = {}

    def bed_of(lid: str):
        if lid not in cache:
            cache[lid] = SC.ambience_bed_of(series_cfg, lid) if lid else None
        return cache[lid]
    beds_of = {x["id"]: bed_of(locs.get(x["id"], "")) for x in layout}
    own = (mix or {}).get("beds") or {}
    by = {x["id"]: x for x in layout}
    out = []
    for r in runs(layout, beds_of):
        b = r["bed"]
        full = os.path.normpath(b["path"] if os.path.isabs(b["path"])
                                else os.path.join(home, *b["path"].split("/")))
        try:
            rel = os.path.relpath(full, root).replace(os.sep, "/")
        except ValueError:                                # another drive
            rel = full.replace(os.sep, "/")
        first, last = by[r["shots"][0]], by[r["shots"][-1]]
        mine = own.get(b["id"]) or {}
        out.append({"place": b["id"], "label": b["name"], "path": full, "rel": rel,
                    "words": b["words"], "exists": os.path.isfile(full),
                    "shots": r["shots"], "start": r["start"], "end": r["end"],
                    "in": {"shot": first["id"], "frame": first["trim_in"]},
                    "out": {"shot": last["id"], "frame": last["trim_in"] + last["used"]},
                    "gain_db": float(mine.get("gain_db") or 0.0),
                    "mute": bool(mine.get("mute"))})
    return out


def render_beds(beds: list[dict], total: int, fps: float, log=print):
    """The beds as one stereo buffer of the cut's length at mix.RATE: each run its bed
    looped, at its gain (a muted place silent), faded in and out over RUN_XFADE_S
    across a boundary inside the cut (equal power, centred on the cut), so two places
    crossfade and a bed gives way to none smoothly. A bed whose file isn't there is
    left out (said so)."""
    np = MX._np()
    n = round(total / fps * MX.RATE)
    out = np.zeros((n, 2), dtype=np.float32)
    srcs: dict[str, object] = {}
    half = int(RUN_XFADE_S * MX.RATE / 2)
    for b in beds:
        if b.get("mute"):
            continue
        if not b.get("exists") or not os.path.isfile(b["path"]):
            log(f"  ! sound: {b['place']}'s ambience bed {b.get('rel') or b['path']} isn't "
                f"there (make it: seriesmith refs); left out")
            continue
        if b["path"] not in srcs:
            srcs[b["path"]] = MX.decode(b["path"])
        src = srcs[b["path"]]
        if len(src) == 0:
            log(f"  ! sound: {b['rel']} has no sound; left out")
            continue
        s0 = round(b["start"] / fps * MX.RATE)
        s1 = min(n, round(b["end"] / fps * MX.RATE))
        head = half if s0 > 0 else 0
        tail = half if s1 < n else 0
        a, z = max(0, s0 - head), min(n, s1 + tail)
        if z <= a:
            continue
        buf = MX.looped(src, z - a).astype(np.float32)
        env = np.full(z - a, MX._db(b.get("gain_db") or 0.0), dtype=np.float32)
        for k, at_head in ((s0 - a + half if head else 0, True), (z - s1 + half if tail else 0, False)):
            k = min(k, z - a)
            if k <= 0:
                continue
            t = np.linspace(0.0, np.pi / 2, k, dtype=np.float32)
            if at_head:
                env[:k] *= np.sin(t)
            else:
                env[-k:] *= np.cos(t)
        out[a:z] += buf[: z - a] * env[:, None]
    return out


def bed_lanes(beds: list[dict], length) -> list[dict]:
    """The beds as clips on the XML's ambience lane (mix.placed's shape, without the
    track's fader): each run its file laid end to end. `length(path)`: a file's length in
    the cut's frames (None: unreadable)."""
    out = []
    for b in beds:
        if b.get("mute") or not b.get("exists"):
            continue
        n = length(b["path"]) if os.path.isfile(b["path"]) else None
        if not n:
            continue
        at, k = b["start"], 0
        while at < b["end"]:
            run = min(b["end"] - at, n)
            out.append({"id": f"bed_{b['place']}" + (f".{k + 1}" if k else ""),
                        "label": b.get("label") or b["place"], "path": b["path"], "start": at, "end": at + run,
                        "in": 0, "frames": n, "gain_db": b.get("gain_db") or 0.0,
                        "points": [], "fade_in": 0, "fade_out": 0})
            at, k = at + run, k + 1
    return out
