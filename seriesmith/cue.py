"""
cue.py — a music cue: what it is asked, its takes, and the one in the mix (docs/SOUND.md
"Music: a cue is written to its hits").

A cue lives in `<ep>/sound/<cue id>/`:

    spec.json   what it is asked (check_spec):
                {"id": "m01", "label": "1M3 The Proposal", "model": "stable_audio3",
                 "in": {"shot", "frame"}, "out": {"shot", "frame"},
                 "style": "romantic, solo horn for Edmund", "bpm": 92, "fixed_tempo": false,
                 "meter": 4, "key": "D minor", "tail": 2.0,
                 "sections": [{"name": "intro", "bars": 4, "words": "solo french horn",
                               "from": 1, "to": 1, "lyrics": ""}, ...],
                 "arc": [{"at": {"shot", "frame"}, "level": 1-5}, ...],
                 "hits": null (every hit of the mix in its span) | ["h1", ...],
                 "takes": null (the model's preset) | 8, "seed": null (from the ids)}
    tNN.wav     a take, stretched to the cue's exact tempo (tNN_raw.<ext> as it came)
    tNN.json    its sidecar: what it was asked (prompt, values, seed, model, the plan's
                tempo), its status, and what was measured (measure)

Planning (`plan`): the cut is laid out as assemble lays it (cut_layout) so the cue's anchors
become seconds; the hits in its span are fitted (core/score.fit_tempo: the tempo within 8 %
of the asked one, and the pre-roll, that put the must-hits on bar lines); the cue runs from
the bar line before its in point through its out point and `tail`, in whole bars; its
sections fill those bars (given, else from the hits: a section ends where the music arrives,
drops or turns); its arc is one energy per bar (the spec's points, else its sections');
the model's prompt is its target's (cue_prompt). A model takes a whole bpm, so a take is
asked for `ask_bpm` and `seconds x stretch`, then stretched to the exact tempo.

A take, when it comes back (`measure`): converted to a wav, stretched by what its measured
tempo says (within 8 %; the plan's stretch when it can't be measured, as in soft music
without onsets), its downbeat found (beats.grid), so its first bar line is where the
cue's pre-roll starts (the fit has put each hit on a bar line of that grid); at each hit,
the strongest onset within half a beat and its distance in frames (whether the music does
something there); its level per bar against the arc (shape error); and a score that ranks
the takes (the worst must-hit error, then the shape).

Picking (`place`): the take becomes the cue's item on the music track of the pass's mix
(mix.py): anchored at the cue's in point, played from where its pre-roll ends, to its out
point with a one-bar fade, and (`fit_gain`) breakpoints at each bar that pull its level
toward the arc, ±6 dB at most.
"""

from __future__ import annotations

import math
import os
import re
import subprocess

from seriesmith import beats as B
from seriesmith import edit as E
from seriesmith import ff as FF
from seriesmith import jobs as J
from seriesmith import mix as MX
from seriesmith import takes as T
from seriesmith import targets as TG
from seriesmith.core import fileio as F
from seriesmith.core import score as SC
from seriesmith.core.ir import stable_seed

SOUND_DIR = "sound"
SPEC = "spec.json"
SPEC_FIELDS = ("id", "label", "model", "in", "out", "style", "bpm", "fixed_tempo", "meter", "key",
               "tail", "sections", "arc", "hits", "takes", "seed")
SECTION_FIELDS = ("name", "bars", "words", "from", "to", "lyrics")
DEFAULT_BPM = 100.0
TAKES_MAX = 16
STRETCH_MAX = 0.08                     # how far a take is stretched to its tempo, either way
# a tempo heard this close to the asked one is the model's drift, and believed; further off
# it is most likely the beat tracker lost in soft music (measured 81-108 on a 93 bpm cue),
# and the plan's stretch is used
TEMPO_TRUST = 0.03
GAIN_FIT_DB = 6.0                      # how far fit_gain moves a bar, either way
ONSET_MIN = 0.15                       # an onset this strong (of the take's strongest) marks a hit
_TAKE = re.compile(r"^t(\d{2,3})\.json$")


class CueError(ValueError):
    pass


# ---------------------------------------------------------------------------
# the spec
# ---------------------------------------------------------------------------

def _level(v, what: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not 1 <= v <= 5:
        raise CueError(f"{what} is an energy from 1 to 5, not {v!r}")
    return float(v)


def check_spec(raw) -> dict:
    """A cue's spec in its stored form. CueError says what's wrong."""
    if not isinstance(raw, dict):
        raise CueError("a cue must be an object")
    unknown = set(raw) - set(SPEC_FIELDS)
    if unknown:
        raise CueError(f"unknown cue field(s) {', '.join(sorted(unknown))}")
    cid = raw.get("id")
    if not isinstance(cid, str) or not MX._ID.match(cid):
        raise CueError(f"a cue's id is 1-40 letters, digits, _ or -, not {cid!r}")
    out: dict = {"id": cid}
    try:
        out["in"] = MX.check_anchor(raw.get("in"), f"cue {cid}'s in")
        out["out"] = MX.check_anchor(raw.get("out"), f"cue {cid}'s out")
    except ValueError as e:
        raise CueError(str(e)) from None
    for k in ("label", "style", "key"):
        if raw.get(k) is not None:
            if not isinstance(raw[k], str):
                raise CueError(f"cue {cid}'s {k} is text")
            if raw[k].strip():
                out[k] = " ".join(raw[k].split())[:500]
    if raw.get("model") is not None:
        try:
            t = TG.load_target(raw["model"])
        except Exception:
            raise CueError(f"cue {cid}'s model {raw['model']!r} isn't a target") from None
        if t.kind != "music":
            raise CueError(f"cue {cid}'s model {raw['model']!r} is a {t.kind} target, not music")
        out["model"] = t.id
    if raw.get("bpm") is not None:
        b = raw["bpm"]
        if isinstance(b, bool) or not isinstance(b, (int, float)) or not 30 <= b <= 240:
            raise CueError(f"cue {cid}'s bpm is 30 to 240, not {b!r}")
        out["bpm"] = round(float(b), 3)
    if raw.get("fixed_tempo"):
        out["fixed_tempo"] = True
    m = raw.get("meter", 4)
    if m not in (2, 3, 4, 6):
        raise CueError(f"cue {cid}'s meter is 2, 3, 4 or 6 beats to the bar, not {m!r}")
    if m != 4:
        out["meter"] = m
    tail = raw.get("tail", 2.0)
    if isinstance(tail, bool) or not isinstance(tail, (int, float)) or not 0 <= tail <= 30:
        raise CueError(f"cue {cid}'s tail is 0 to 30 seconds, not {tail!r}")
    if tail != 2.0:
        out["tail"] = float(tail)
    secs = []
    for i, s in enumerate(raw.get("sections") or []):
        if not isinstance(s, dict) or set(s) - set(SECTION_FIELDS):
            raise CueError(f"cue {cid}'s section {i + 1} takes {', '.join(SECTION_FIELDS)}")
        sec: dict = {"name": " ".join(str(s.get("name") or f"section {i + 1}").split())[:40]}
        if s.get("bars") is not None:
            if isinstance(s["bars"], bool) or not isinstance(s["bars"], int) or not 1 <= s["bars"] <= 256:
                raise CueError(f"cue {cid}'s section {i + 1}'s bars is a whole number, 1 or more")
            sec["bars"] = s["bars"]
        for k in ("words", "lyrics"):
            if s.get(k):
                sec[k] = str(s[k]).strip()[:2000]
        for k in ("from", "to"):
            if s.get(k) is not None:
                sec[k] = _level(s[k], f"cue {cid}'s section {i + 1}'s {k}")
        secs.append(sec)
    if secs:
        out["sections"] = secs
    arc = []
    for i, p in enumerate(raw.get("arc") or []):
        if not isinstance(p, dict) or set(p) - {"at", "level"}:
            raise CueError(f"cue {cid}'s arc point {i + 1} is {{\"at\", \"level\"}}")
        try:
            at = MX.check_anchor(p.get("at"), f"cue {cid}'s arc point {i + 1}")
        except ValueError as e:
            raise CueError(str(e)) from None
        arc.append({"at": at, "level": _level(p.get("level"), f"cue {cid}'s arc point {i + 1}")})
    if arc:
        out["arc"] = arc
    if raw.get("hits") is not None:
        if not isinstance(raw["hits"], list) or not all(isinstance(h, str) for h in raw["hits"]):
            raise CueError(f"cue {cid}'s hits are the ids of the mix's hits it lands")
        out["hits"] = list(raw["hits"])
    for k, hi in (("takes", TAKES_MAX), ("seed", 2 ** 63 - 1)):
        v = raw.get(k)
        if v is not None:
            if isinstance(v, bool) or not isinstance(v, int) or not (1 if k == "takes" else 0) <= v <= hi:
                raise CueError(f"cue {cid}'s {k} is a whole number up to {hi}")
            out[k] = v
    return out


def cue_dir(root: str, cid: str) -> str:
    return os.path.join(root, SOUND_DIR, cid)


def load_spec(root: str, cid: str) -> dict:
    raw = F.read_json_or(os.path.join(cue_dir(root, cid), SPEC), None)
    if raw is None:
        raise FileNotFoundError(f"no cue {cid} in {root}")
    return check_spec(raw)


def save_spec(root: str, raw) -> dict:
    spec = check_spec(raw)
    F.write_json(os.path.join(cue_dir(root, spec["id"]), SPEC), spec)
    return spec


def list_cues(root: str) -> list[dict]:
    """Every cue's spec in the episode, by id (one that doesn't read is left out)."""
    base = os.path.join(root, SOUND_DIR)
    out = []
    for name in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        try:
            out.append(load_spec(root, name))
        except (FileNotFoundError, CueError):
            continue
    return out


# ---------------------------------------------------------------------------
# the cut, laid out
# ---------------------------------------------------------------------------

def cut_layout(root: str, pass_: str) -> tuple[list[dict], float]:
    """The pass's cut as assemble lays it, without probing a file: [{"id", "trim_in",
    "used", "dissolve_in"}] in cut order (orphans, shots left out and shots with no
    usable take skipped), and the cut's frame rate. A take's length is its sidecar's;
    a shot with a dialogue window keeps the window; a dissolve that doesn't fit beside
    its neighbours is left out, as assemble leaves it."""
    fps = E.pass_fps(root, pass_)
    try:
        shots = {s["id"]: s for d, i in J.episode_shots(root, pass_) for s in [d["shots"][i]]}
    except FileNotFoundError:
        shots = {}
    windows = E.dialogue_windows(root, pass_, fps)
    out = []
    for e in E.cut_entries(root, pass_):
        if e.orphan or e.out:
            continue
        chosen, _, ok = E.cut_take(root, e)
        if not ok:
            continue
        span = windows.get(e.shot) or E.take_span(root, e, fps) \
            or int((shots.get(e.shot) or {}).get("length") or 0)
        used = span - max(0, e.trim_in) - max(0, e.trim_out)
        if used < 1:
            continue
        d = e.dissolve if out and e.dissolve * 2 <= min(used, out[-1]["used"]) else 0
        out.append({"id": e.shot, "trim_in": max(0, e.trim_in), "used": used, "dissolve_in": d})
    return out, fps


# ---------------------------------------------------------------------------
# planning
# ---------------------------------------------------------------------------

def _arc_per_bar(points: list[tuple[float, float]], bars: int, bar: float, start: float) -> list[float]:
    """One energy per bar from (cue seconds, level) points: linear between them, held
    beyond; each bar's value at its middle."""
    pts = sorted(points)
    out = []
    for b in range(bars):
        t = start + (b + 0.5) * bar
        if t <= pts[0][0]:
            out.append(pts[0][1])
        elif t >= pts[-1][0]:
            out.append(pts[-1][1])
        else:
            for (t0, a), (t1, c) in zip(pts, pts[1:]):
                if t0 <= t <= t1:
                    out.append(a + (c - a) * (t - t0) / (t1 - t0) if t1 > t0 else c)
                    break
    return [round(x, 2) for x in out]


def _sections_from_hits(bars: int, hits: list[dict], preroll: float, bar: float) -> list[dict]:
    """Sections when the spec gives none: a boundary at each hit that arrives, drops or
    turns (on its bar), a build into an arrival and quiet after a drop."""
    cuts = []
    for h in hits:
        if h["kind"] in ("arrive", "drop", "turn"):
            b = int(round((h["t"] + preroll) / bar))
            if 0 < b < bars and b not in [c[0] for c in cuts]:
                cuts.append((b, h["kind"]))
    cuts.sort()
    edges = [0] + [c[0] for c in cuts] + [bars]
    kinds = [None] + [c[1] for c in cuts]
    out = []
    for i in range(len(edges) - 1):
        start_kind, end_kind = kinds[i], (kinds[i + 1] if i + 1 < len(kinds) else None)
        a, b = 2.0, 3.0
        if end_kind == "arrive":
            a, b = 2.0, 5.0
        if start_kind == "arrive":
            a, b = 5.0, 4.0
        if start_kind == "drop":
            a, b = 1.0, 1.5
        name = {"arrive": "climax", "drop": "drop", "turn": "turn"}.get(start_kind or "", "") \
            or ("build" if end_kind == "arrive" else "intro" if i == 0 else "section")
        out.append({"name": name, "bars": edges[i + 1] - edges[i], "from": a, "to": b})
    return out


def _fill_bars(sections: list[dict], bars: int) -> list[dict]:
    """The spec's sections fitted to the cue's bars: those without a count share what the
    others leave, the last one takes up any difference."""
    secs = [dict(s) for s in sections]
    fixed = sum(s["bars"] for s in secs if s.get("bars"))
    loose = [s for s in secs if not s.get("bars")]
    left = max(len(loose), bars - fixed)
    for i, s in enumerate(loose):
        s["bars"] = left // len(loose) + (1 if i < left % len(loose) else 0)
    diff = bars - sum(s["bars"] for s in secs)
    if secs and diff:
        secs[-1]["bars"] = max(1, secs[-1]["bars"] + diff)
    for s in secs:
        s.setdefault("from", 3.0)
        s.setdefault("to", s["from"])
    return secs


def plan(root: str, pass_: str, spec: dict, series: dict | None = None) -> dict:
    """What a cue is asked, from its spec, the pass's cut and mix: {"spec", "target",
    "fps", "start_frame", "end_frame", "span", "hits": [{"id", "name", "kind", "must",
    "t"}], "fit": {...}, "bars", "bar", "preroll", "seconds", "ask_seconds", "sections",
    "arc", "cue" (what the prompt writer gets), "prompt"}. CueError when its anchors
    aren't in the cut."""
    series = series if series is not None else (J.series_config(root) or {})
    layout, fps = cut_layout(root, pass_)
    origins = MX.shot_origins(layout)
    a, b = MX.place(spec["in"], origins), MX.place(spec["out"], origins)
    if a is None or b is None:
        raise CueError(f"cue {spec['id']}: {spec['in']['shot'] if a is None else spec['out']['shot']} "
                       f"isn't in the {pass_} cut")
    if b <= a:
        raise CueError(f"cue {spec['id']}: its out is at or before its in")
    span = (b - a) / fps
    mix = MX.check(MX.load(root).get(pass_))
    want = set(spec["hits"]) if spec.get("hits") is not None else None
    hits = []
    for h in mix.get("hits") or []:
        f = MX.place(h["at"], origins)
        if f is None or (want is not None and h["id"] not in want):
            continue
        if want is None and not a <= f <= b:
            continue
        hits.append({"id": h["id"], "name": h.get("name") or h["id"],
                     "kind": h.get("kind", "accent"), "must": h.get("must", True),
                     "t": round((f - a) / fps, 4)})
    meter = spec.get("meter", 4)
    asked = spec.get("bpm") or DEFAULT_BPM
    fit = SC.fit_tempo([(h["t"], h["must"], h["kind"] == "accent") for h in hits], asked, fps, meter,
                       spread=0.0 if spec.get("fixed_tempo") else 0.08)
    bar = fit.bar
    preroll = fit.preroll
    tail = spec.get("tail", 2.0)
    bars = max(1, math.ceil((preroll + span + tail) / bar - 1e-6))
    seconds = round(bars * bar, 3)
    if spec.get("sections"):
        sections = _fill_bars(spec["sections"], bars)
    else:
        sections = _sections_from_hits(bars, hits, preroll, bar)
    if spec.get("arc"):
        pts = [((MX.place(p["at"], origins) - a) / fps, p["level"]) for p in spec["arc"]
               if MX.place(p["at"], origins) is not None]
    else:
        pts, t = [], -preroll
        for s in sections:
            pts += [(t + 0.01, s["from"]), (t + s["bars"] * bar - 0.01, s["to"])]
            t += s["bars"] * bar
    arc = _arc_per_bar(pts, bars, bar, -preroll) if pts else [3.0] * bars
    target = TG.load_target(spec.get("model") or ((series.get("sound") or {}).get("music_model"))
                            or TG.DEFAULT_MUSIC_TARGET)
    direction = ((series.get("sound") or {}).get("score") or "").strip()
    style = ", ".join(x for x in (direction.rstrip("."), spec.get("style", "")) if x)
    cue = {"style": style or "cinematic orchestral film score", "bpm": fit.ask_bpm,
           "meter": meter, "key": spec.get("key", ""), "seconds": round(seconds * fit.stretch, 3),
           "sections": sections}
    brief = target.cue_prompt(cue)
    return {"spec": spec, "target": target.id, "fps": fps, "start_frame": a, "end_frame": b,
            "span": round(span, 3), "hits": hits,
            "fit": {"bpm": fit.bpm, "ask_bpm": fit.ask_bpm, "stretch": fit.stretch,
                    "errors": fit.errors, "worst_must": fit.worst_must},
            "bars": bars, "bar": round(bar, 5), "preroll": preroll, "seconds": seconds,
            "ask_seconds": cue["seconds"], "sections": sections, "arc": arc, "cue": cue,
            "prompt": brief}


# ---------------------------------------------------------------------------
# takes
# ---------------------------------------------------------------------------

def take_paths(root: str, cid: str, n: int) -> dict:
    d = cue_dir(root, cid)
    return {"sidecar": os.path.join(d, f"t{n:02d}.json"), "wav": os.path.join(d, f"t{n:02d}.wav"),
            "rel": f"{SOUND_DIR}/{cid}/t{n:02d}.wav"}


def list_takes(root: str, cid: str) -> list[dict]:
    """Every take's sidecar (with its `take` number), by number."""
    d = cue_dir(root, cid)
    out = []
    for name in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        m = _TAKE.match(name)
        if m:
            sc = F.read_json_or(os.path.join(d, name), None)
            if isinstance(sc, dict):
                out.append({**sc, "take": int(m.group(1))})
    return out


def ranked(takes: list[dict]) -> list[dict]:
    """The finished takes best first (their measured score), then the rest."""
    done = [t for t in takes if t.get("status") == "ok" and (t.get("measured") or {}).get("score") is not None]
    rest = [t for t in takes if t not in done]
    return sorted(done, key=lambda t: t["measured"]["score"]) + rest


def reserve(root: str, cid: str, record: dict) -> int:
    """The next take number, its sidecar written `queued` with `record`."""
    os.makedirs(cue_dir(root, cid), exist_ok=True)
    n = max([t["take"] for t in list_takes(root, cid)] + [0]) + 1
    F.write_json(take_paths(root, cid, n)["sidecar"], {**record, "status": "queued", "created": T.now()})
    return n


def update(root: str, cid: str, n: int, **fields) -> dict:
    path = take_paths(root, cid, n)["sidecar"]
    sc = F.read_json_or(path, {}) or {}
    sc.update(fields)
    F.write_json(path, sc)
    return sc


def graph(target, p: dict, seed: int, pass_: str) -> dict:
    """The API graph for one take: the target's workflow, its preset's model files,
    steps, cfg, sampler and negative, the brief and the seed, pruned to the saver."""
    import copy
    base, _ = J.target_workflow(target, None, None, required=True, prefer_repo=True)
    g = copy.deepcopy(base)
    b = target.binding
    preset = target.presets.get(pass_) or target.presets.get("final")
    vals = {}
    if preset is not None:
        if preset.model:
            vals["model"] = preset.model
        if preset.steps:
            vals["steps"] = preset.steps
        vals.update({k: v for k, v in preset.extra.items() if not k.startswith("_")})
    brief = p["prompt"]
    vals["prompt"] = brief["prompt"]
    if brief.get("negative") is not None:
        vals["negative"] = brief["negative"]
    vals.update(brief.get("values") or {})
    vals["seed"] = seed
    for name, v in vals.items():
        if v is not None and b.specs(name):
            J.patch_param(g, b, name, v)
    saver = J.node_of(g, b.saver_class or "SaveAudio")
    if b.prune:
        J.prune(g, saver)
    return g


def seeds(root: str, spec: dict, count: int, already: int) -> list[int]:
    """`count` seeds for new takes: from the spec's seed, else the episode and cue ids,
    each the next after the takes already made (a re-render gets new ones)."""
    base = spec.get("seed")
    ep = os.path.basename(os.path.normpath(root))
    return [(base + already + k) if base is not None else stable_seed(ep, "cue", spec["id"], str(already + k))
            for k in range(count)]


def takes_wanted(target, pass_: str, spec: dict) -> int:
    preset = target.presets.get(pass_) or target.presets.get("final")
    n = spec.get("takes") or (preset.extra.get("takes") if preset is not None else None) or 8
    return max(1, min(TAKES_MAX, int(n)))


# ---------------------------------------------------------------------------
# a take measured
# ---------------------------------------------------------------------------

def stretch_file(src: str, dst: str, factor: float) -> None:
    """`src` played `factor` times faster (atempo: the pitch kept) as a 24-bit wav."""
    af = [] if abs(factor - 1.0) < 1e-4 else ["-af", f"atempo={factor:.6f}"]
    tmp = F.temp_beside(dst, ".wav")
    r = subprocess.run([*FF.tool("ffmpeg"), "-y", "-v", "error", "-i", src, *af, "-ar", str(MX.RATE),
                        "-ac", "2", "-c:a", "pcm_s24le", tmp], capture_output=True, timeout=600)
    if r.returncode != 0:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise RuntimeError("stretching the take: " + r.stderr.decode("utf-8", "replace")[-300:])
    F.replace(tmp, dst)


def measure(raw_file: str, wav: str, p: dict) -> dict:
    """A take that came back (`raw_file`) stretched to the cue's tempo into `wav`, and
    measured: {"bpm_heard", "stretch", "downbeat", "offset", "hit_errors", "worst_must",
    "levels", "shape_error", "score", "tempo_heard"}. `offset` is where in the wav the cue's
    in point falls (its first bar line, plus the pre-roll)."""
    fit, bar_s, fps = p["fit"], p["bar"], p["fps"]
    buf = MX.decode(raw_file)
    env = B.onsets(buf)
    heard = B.tempo(env, asked=fit["ask_bpm"])
    # a tempo it can't tell (soft music) or far off: the plan's stretch
    believed = heard is not None and abs(heard - fit["ask_bpm"]) / fit["ask_bpm"] <= TEMPO_TRUST
    factor = (fit["bpm"] / heard) if believed else fit["stretch"]
    factor = max(1 - STRETCH_MAX, min(1 + STRETCH_MAX, factor))
    stretch_file(raw_file, wav, factor)
    buf = MX.decode(wav)
    env = B.onsets(buf)
    meter = p["spec"].get("meter", 4)
    first, down = B.grid(env, fit["bpm"], buf, meter)
    # the first bar line the music has: a downbeat a bar or more in is the same grid earlier
    down = down - bar_s * math.floor(down / bar_s + 1e-9) if down >= bar_s else down
    offset = down + p["preroll"]
    # the grid puts every hit on its bar line (the fit's doing); what a take adds is whether
    # the music does something there: the strongest onset within half a beat of the hit,
    # its distance in frames (None: nothing there, counted as half a beat off)
    beat_s = bar_s / meter
    errs = []
    for h in p["hits"]:
        f = offset + h["t"]
        at, strength = B.onset_near(env, f, beat_s / 2)
        errs.append(round((at - f) * fps, 2) if at is not None and strength >= ONSET_MIN else None)
    musts = [abs(e) if e is not None else beat_s / 2 * fps
             for e, h in zip(errs, p["hits"]) if h["must"]]
    worst = max(musts) if musts else 0.0
    levels = B.bar_levels(buf, fit["bpm"], down, meter, p["bars"])
    shape = B.shape_error(levels, p["arc"])
    score = round(worst / max(1.0, fps / 8) + (shape if shape is not None else 0.5), 4)
    return {"bpm_heard": round(heard, 2) if heard else None, "tempo_heard": believed,
            "stretch": round(factor, 5), "downbeat": round(down, 4), "offset": round(offset, 4),
            "hit_errors": errs, "worst_must": round(worst, 2), "levels": levels,
            "shape_error": shape, "score": score}


def finish_take(root: str, cid: str, n: int, raw_path: str, p: dict) -> dict:
    """A take's file is back: kept as tNN_raw, stretched and measured into tNN.wav, its
    sidecar closed."""
    paths = take_paths(root, cid, n)
    keep = os.path.join(cue_dir(root, cid), f"t{n:02d}_raw{os.path.splitext(raw_path)[1] or '.flac'}")
    F.replace(raw_path, keep)
    m = measure(keep, paths["wav"], p)
    return update(root, cid, n, status="ok", finished=T.now(), file=paths["rel"],
                  raw=os.path.relpath(keep, root).replace(os.sep, "/"), measured=m)


# ---------------------------------------------------------------------------
# into the mix
# ---------------------------------------------------------------------------

def fit_gain(levels: list[float], arc: list[float], bound: float = GAIN_FIT_DB) -> list[float]:
    """dB per bar that move a take's level toward the arc: the arc mapped onto the take's
    own loudness range (its mean and spread), each bar's difference, at most `bound` either
    way, half a dB steps. A silent bar (or a flat arc) gets 0."""
    heard = [x for x in levels if x > -60]
    if len(heard) < 2 or max(arc) - min(arc) < 1e-6:
        return [0.0] * len(levels)
    mean = sum(heard) / len(heard)
    spread = max(max(heard) - min(heard), 6.0)
    amean = sum(arc) / len(arc)
    k = spread / (max(arc) - min(arc))
    out = []
    for lv, a in zip(levels, arc):
        if lv <= -60:
            out.append(0.0)
            continue
        want = mean + (a - amean) * k
        out.append(round(max(-bound, min(bound, want - lv)) * 2) / 2)
    return out


def place(root: str, pass_: str, cid: str, n: int, gain: bool = True) -> dict:
    """Take `n` as the cue's item on the music track of the pass's mix: anchored at the
    cue's in point, from its offset, to the out point with a one-bar fade out, and (`gain`)
    a breakpoint at each bar fitting its level to the arc. Returns the mix as written."""
    spec = load_spec(root, cid)
    sc = next((t for t in list_takes(root, cid) if t["take"] == n), None)
    if sc is None or sc.get("status") != "ok":
        raise CueError(f"cue {cid} has no finished take {n}")
    p = plan(root, pass_, spec)
    m = sc["measured"]
    layout, fps = cut_layout(root, pass_)
    origins = MX.shot_origins(layout)
    item = {"id": cid, "track": "music", "path": take_paths(root, cid, n)["rel"],
            "in": spec["in"], "out": spec["out"], "offset": max(0.0, round(m["offset"], 3)),
            "fade_out": max(1, round(p["bar"] * fps)), "label": spec.get("label") or cid}
    if gain:
        pts = []
        for b, db in enumerate(fit_gain(m["levels"], p["arc"])):
            # the bar's start, from the cue's in point (the pre-roll is before it)
            t = -p["preroll"] + b * p["bar"]
            if t < 0:
                continue
            at = MX.anchor_at(p["start_frame"] + round(t * fps), origins)
            if at is not None:
                pts.append({"at": at, "db": db})
        if any(x["db"] for x in pts):
            item["points"] = pts
    mix = MX.check(MX.load(root).get(pass_))
    items = [i for i in mix.get("items") or [] if i["id"] != cid] + [item]
    mix["items"] = items
    out = MX.write(root, pass_, mix)
    update(root, cid, n, placed=pass_)
    return out
