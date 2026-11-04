"""
scoredraft.py — an episode's first-pass score, drafted from its script's structure and written
as cues for a person to adjust and render (docs/SOUND.md phase 8, "The simple first pass";
core/spotting.py the rules).

    draft(root, pass_)                     -> what the draft would write, nothing written
    write(root, pass_, d, replace=False)   -> the draft's cues and hits written
    mark_script(root, d)                   -> a laid-out draft's structure and beat lines
                                              written into the script

What it reads: the script's `// structure:`, `// beat:`, `// theme:` and `// flashback` lines
(comments: the build ignores them), the story IR (shotlist/shots.json: who is in each shot,
their lines, its `sound:`, `music:` and target), the pass's cut (each shot's length and
trim as assemble lays it; a shot with no take yet at its shotlist length), and the series
config (`sound.format`, `sound.themes`, the speech pace).

What it writes: each draft cue a cue like any other (`sound/<id>/spec.json`, ids d01, d02 ...,
labelled "Draft: ..."): its in and out anchors, a section per beat (its bars at the tempo it
will most likely be asked: the theme's, else cue.DEFAULT_BPM), its theme (`story`: the take of
the cue that makes it; a series theme by name), and its hits in the pass's mix (ids dh01 ...,
`must: false`: the fit lands them when it can). Nothing is rendered. A cue of the person's own
(an id not dNN) is never touched: a draft cue that would play over one is left out, and said.
A script with no beat lines drafts flat (a cue a sequence), or, given a `structure`, with that
structure's beats laid over the cut by where each falls in a story (spotting.layout): a start
the person can then keep in the script (mark_script: `// structure:` and `// beat:` lines, the
build's parse unchanged, the old script to _history) and correct by hand.

`replace` first deletes the earlier draft's cues (cue.delete: to _history) and hits. A draft cue
with a finished take is the person's now: kept, as a cue of their own is, its id and hits too,
unless `rendered` (the draft drafted again over them: their takes to _history as well). A
series theme's cue, and a cue a kept one takes its theme from, is always kept. A draft cue
that would play over a kept cue is trimmed to the longest stretch free of them (TRIM_MIN or
more, else left out); one that would have made the story theme where a kept cue now plays
takes that cue's take as its theme.
"""

from __future__ import annotations

import os
import re

from seriesmith import cue as CU
from seriesmith import edit as E
from seriesmith import jobs as J
from seriesmith import mix as MX
from seriesmith.core import paths as P
from seriesmith.core import spotting as SP
from seriesmith.core.speech import speech_seconds

DRAFT_ID = re.compile(r"^d\d{2,3}$")
DRAFT_HIT = re.compile(r"^dh\d{2,3}$")
LABEL = "Draft: "
STING_TAIL = 1.0       # seconds a sting rings past its out point
TRIM_MIN = 8.0         # seconds: a draft cue trimmed around a kept cue shorter than this is left out


class DraftError(ValueError):
    pass


def _story(root: str):
    from seriesmith.core import ir
    try:
        with open(os.path.join(root, "shotlist", "shots.json"), encoding="utf-8") as fh:
            return ir.Episode.loads(fh.read())
    except (OSError, ValueError, KeyError):
        raise DraftError("the episode isn't built (shotlist/shots.json): build it first") from None


def _drafts(root: str, rendered: bool = False) -> tuple[list[dict], list[dict]]:
    """The episode's draft cues (dNN): (those a new draft replaces, those it keeps). Kept: a
    series theme's (sound.themes names it), one with a finished take unless `rendered`, and a
    cue a kept one takes its theme from (`{"cue"}`)."""
    ep = os.path.basename(os.path.normpath(root))
    pinned = {t.get("cue") for n, t in CU.series_themes(J.series_config(root)).items()
              if n != "_errors" and t.get("ep") == ep}
    drafts = [c for c in CU.list_cues(root) if DRAFT_ID.match(c["id"])]
    keep = {c["id"] for c in drafts if c["id"] in pinned or (not rendered and any(
        t.get("status") == "ok" for t in CU.list_takes(root, c["id"])))}
    while True:                                          # what a kept cue takes its theme from
        more = {(c.get("theme") or {}).get("cue") for c in drafts if c["id"] in keep} - keep - {None}
        if not more:
            break
        keep |= more
    return [c for c in drafts if c["id"] not in keep], [c for c in drafts if c["id"] in keep]


def timeline(root: str, pass_: str, series: dict | None) -> tuple[list[dict], float, list[str]]:
    """The cut's shots for the draft, in cut order (spotting.draft's `shots`, plus "trim_in"
    and "frames"), its frame rate, and the shots with no take (at their shotlist length)."""
    story = _story(root)
    meta = {}
    pace = ((series or {}).get("speech") or {}).get("pace", "normal")
    for sq in story.sequences:
        for s in sq.shots:
            lines = [{"who": x.speaker, "line": x.line} for x in s.dialogue if x.line]
            meta[s.id] = {"seq": sq.id, "loc": sq.location, "who": list(s.cast),
                          "speakers": [x.speaker for x in s.dialogue if x.mode == "on"],
                          "talk": speech_seconds(lines, pace) if lines else 0.0,
                          "sound": s.sound or "", "music": s.music or "", "target": s.target or ""}
    layout, fps = CU.cut_layout(root, pass_)
    laid = {x["id"]: x for x in layout}
    try:
        lengths = {d["shots"][i]["id"]: int(d["shots"][i].get("length") or 0)
                   for d, i in J.episode_shots(root, pass_)}
    except FileNotFoundError:
        lengths = {}
    shots, t, missing = [], 0.0, []
    for e in E.cut_entries(root, pass_):
        if e.orphan or e.out or e.shot not in meta:
            continue
        x = laid.get(e.shot)
        if x is None:
            frames = lengths.get(e.shot, 0)
            if frames < 1:
                continue
            missing.append(e.shot)
            trim, used, dis = 0, frames, 0
        else:
            trim, used, dis = x["trim_in"], x["used"], x["dissolve_in"]
        t -= dis / fps
        shots.append({"id": e.shot, **meta[e.shot], "t": round(t, 4), "d": round(used / fps, 4),
                      "trim_in": trim, "frames": used})
        t += used / fps
    return shots, fps, missing


def _script(root: str) -> str:
    path = P.episode_script(root)
    if not path:
        raise DraftError("no script in the episode folder")
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def draft(root: str, pass_: str = "final", rendered: bool = False, structure: str | None = None) -> dict:
    """The draft for the pass's cut, nothing written: spotting.draft's, each cue with its
    `id`, its spec (`spec`), its hits as the mix's (`mix_hits`), `skip` (why it is left out,
    when it is) and `trim` (what it was trimmed around); plus "missing" (shots with no take
    yet), "fps", "voices_only" (whether the mix plays voices only already), "drafted" (the
    earlier draft cues a write replaces), "kept" (those it keeps), "rendered", "marked"
    (whether the script has beat lines), "laid" (the structure laid over the cut, given
    `structure` and no beat lines: its beats are where it put them), "structures" (every
    structure's id and name, to pick from). DraftError when the episode can't be read, or
    `structure` names none."""
    series = J.series_config(root) or {}
    sound = series.get("sound") or {}
    fmt = {}
    if sound.get("format"):
        try:
            fmt = SP.check_format(sound["format"])
        except SP.SpotError as e:
            raise DraftError(str(e)) from None
    named = CU.series_themes(series)
    themes = [{"name": n, "role": t.get("role"), "for": t.get("for") or [], "bpm": t.get("bpm")}
              for n, t in named.items() if n != "_errors"]
    shots, fps, missing = timeline(root, pass_, series)
    marks = SP.read_marks(_script(root))
    marked = bool(marks["beats"])
    laid = None
    if structure and not marked:
        try:
            st = SP.structure(structure)
        except SP.SpotError as e:
            raise DraftError(str(e)) from None
        marks = {**marks, "structure": st["name"], "beats": SP.layout(shots, st)}
        laid = st["name"]
    out = SP.draft(shots, marks, fmt, themes)
    if laid:
        out["notes"] = [n for n in out["notes"] if "no // beat: lines" not in n]
    by_id = {s["id"]: s for s in shots}

    def frame(a: dict) -> dict:
        s = by_id[a["shot"]]
        return {"shot": a["shot"], "frame": int(s["trim_in"] + min(s["frames"], round(a["at"] * fps)))}

    # the episode's own cues: where they play, so a draft cue never lands on one
    origins = {s["id"]: s["t"] * fps - s["trim_in"] for s in shots}
    fresh, kept = _drafts(root, rendered)
    kept_ids = {c["id"] for c in kept}
    used_hits = {h for c in kept for h in c.get("hits") or []}
    mine = []
    for c in CU.list_cues(root):
        if DRAFT_ID.match(c["id"]) and c["id"] not in kept_ids:
            continue
        a, b = origins.get(c["in"]["shot"]), origins.get(c["out"]["shot"])
        if a is not None and b is not None:
            mine.append((c["id"], (a + c["in"]["frame"]) / fps, (b + c["out"]["frame"]) / fps))
    bpm_of = {t["name"]: t.get("bpm") for t in themes}
    n = h = 0
    maker = None
    for c in out["cues"]:
        over = [(cid, a, b) for cid, a, b in mine if a < c["t1"] and c["t0"] < b]
        if over:
            names = sorted({cid for cid, _, _ in over})
            span = None if c["kind"] != "cue" else _free(c["t0"], c["t1"], [(a, b) for _, a, b in over])
            if span is None or span[1] - span[0] < TRIM_MIN:
                c["skip"] = f"{', '.join(names)} already play{'s' if len(names) == 1 else ''} there"
                if c.get("makes") == "story" and maker is None:
                    maker = names[0]                # the kept cue made the story theme
                continue
            before = [cid for cid, a, b in over if b <= span[0] + 1e-6]
            _trim(c, span, shots)
            c["trim"] = f"trimmed around {', '.join(names)}"
            if c.get("makes") == "story" and before and maker is None:
                maker = before[-1]                  # the kept cue before it states the theme
                c["makes"], c["theme"] = None, "story"
        n += 1
        while f"d{n:02d}" in kept_ids:
            n += 1
        c["id"] = f"d{n:02d}"
        if c.get("makes") == "story":
            maker = c["id"]
        bpm = bpm_of.get(c["theme"]) or CU.DEFAULT_BPM
        bar = 60.0 / bpm * 4
        sections = []
        for s in c["sections"]:
            sec = {"name": s["name"] or "section", "from": s["from"], "to": s["to"]}
            if len(c["sections"]) > 1:
                sec["bars"] = max(1, round(s["seconds"] / bar))
            if s["words"]:
                sec["words"] = s["words"]
            sections.append(sec)
        hits = []
        for x in c["hits"]:
            h += 1
            while f"dh{h:02d}" in used_hits:
                h += 1
            s = by_id[x["shot"]]
            at = {"shot": x["shot"], "frame": s["trim_in"] + (s["frames"] if x["end"] else 0)}
            hits.append({"id": f"dh{h:02d}", "name": x["name"][:80], "at": at, "kind": x["kind"], "must": False})
        spec = {"id": c["id"], "label": (LABEL + c["label"])[:500], "in": frame(c["in"]), "out": frame(c["out"]),
                "sections": sections, "hits": [x["id"] for x in hits]}
        if c["kind"] != "cue":
            spec["tail"] = STING_TAIL
        if c["theme"] == "story":
            if maker:
                spec["theme"] = {"cue": maker}
        elif c["theme"]:
            spec["theme"] = {"theme": c["theme"]}
        if spec.get("theme") and c.get("strength") is not None:
            spec["theme"]["strength"] = c["strength"]
        c["spec"] = CU.check_spec(spec)
        c["mix_hits"] = hits
    mix = MX.check(MX.load(root).get(pass_))
    out.update({"pass": pass_, "fps": fps, "missing": missing,
                "voices_only": bool(((mix.get("tracks") or {}).get("dialogue") or {}).get("voices_only")),
                "drafted": [c["id"] for c in fresh], "kept": sorted(kept_ids), "rendered": rendered,
                "marked": marked, "laid": laid,
                "structures": [{"id": s["id"], "name": s["name"]} for s in SP.structures()]})
    return out


def mark_script(root: str, d: dict) -> bool:
    """A laid-out draft's structure and beat lines written into the script: `// structure:`
    at its top (after its `=` title line), `// beat:` above each beat's first shot (above its
    sequence's header when it starts one). The old script to _history (source.write_source);
    DraftError, nothing written, when the build would read the script differently. False when
    there's nothing to write (not laid out, or marked already)."""
    from seriesmith import build as BLD
    from seriesmith import source as SRC
    if not d.get("laid"):
        return False
    try:
        src = SRC.read_source(root, "script")
    except SRC.SourceError as e:
        raise DraftError(str(e)) from None
    if SP.read_marks(src.text)["beats"]:
        return False
    starts = {b["shot"]: re.sub(r"\s*\(again\)\s*$", "", b["beat"]) for b in d["beats"] if b.get("beat")}
    first_of = {}
    seq = None
    for line in src.text.splitlines():
        m = re.match(r"^#\s+(\S+)", line)
        if m and not line.startswith("##"):
            seq = line
        m = re.match(r"^##\s+(\S+)", line)
        if m and seq is not None:
            first_of[m.group(1)] = seq
            seq = None
    lines = src.text.split("\n")
    out, top = [], False
    for i, line in enumerate(lines):
        if not top and not line.startswith(("=", "//")) and line.strip():
            out += [f"// structure: {d['laid']}", ""]
            top = True
        m = re.match(r"^##\s+(\S+)", line)
        if m and m.group(1) in starts and first_of.get(m.group(1)) is None:
            out.append(f"// beat: {starts[m.group(1)]}")
        m = re.match(r"^#\s+\S+", line)
        if m and not line.startswith("##"):
            # the beat whose first shot opens this sequence goes above its header
            nxt = next((re.match(r"^##\s+(\S+)", x).group(1) for x in lines[i + 1:]
                        if re.match(r"^##\s+\S+", x)), None)
            if nxt in starts and first_of.get(nxt) == line:
                out.append(f"// beat: {starts[nxt]}")
        out.append(line)
    text = "\n".join(out)
    from seriesmith.core.series_config import load_series_config
    try:
        cfg = load_series_config(P.series_config_path(root))
    except (OSError, ValueError) as e:
        raise DraftError(f"the series config doesn't load ({e}): its beat lines not written") from None
    args = (BLD.subject_ids(cfg), BLD.character_ids(cfg), BLD.variant_of(cfg))
    try:
        same = repr(BLD.parse_script(src.text, *args)) == repr(BLD.parse_script(text, *args))
    except Exception as e:                       # the script doesn't parse now: leave it alone
        raise DraftError(f"the script doesn't build as it is ({e}): its beat lines not written") from None
    if not same:
        raise DraftError("the beat lines would change how the script is read: not written")
    SRC.write_source(src, text)
    return True


def _free(t0: float, t1: float, busy: list[tuple[float, float]]) -> tuple[float, float] | None:
    """The longest stretch of [t0, t1] none of `busy` covers."""
    spans, cur = [], t0
    for a, b in sorted(busy):
        if a > cur:
            spans.append((cur, min(a, t1)))
        cur = max(cur, b)
    if cur < t1:
        spans.append((cur, t1))
    spans = [x for x in spans if x[1] > x[0]]
    return max(spans, key=lambda x: x[1] - x[0]) if spans else None


def _trim(c: dict, span: tuple[float, float], shots: list[dict]) -> None:
    """A draft cue cut to [a, b]: its anchors, and the sections and hits there."""
    a, b = span
    secs, t = [], c["t0"]
    for sec in c["sections"]:
        s0, s1 = t, t + sec["seconds"]
        t = s1
        lo, hi = max(s0, a), min(s1, b)
        if hi - lo >= 0.5:
            secs.append(dict(sec, seconds=round(hi - lo, 3)))
    start = {s["id"]: s["t"] for s in shots}
    ends = {s["id"]: s["t"] + s["d"] for s in shots}
    c["hits"] = [h for h in c["hits"] if a <= (ends if h["end"] else start)[h["shot"]] <= b]
    c["sections"] = secs or c["sections"][:1]
    # its label the beats it still plays over
    c["label"] = " → ".join(dict.fromkeys(re.sub(r" \(cont\.\)$", "", x["name"]) for x in c["sections"]))
    c["in"], c["out"] = SP.anchor_at(shots, a), SP.anchor_at(shots, b, end=True)
    c["t0"], c["t1"] = round(a, 3), round(b, 3)


def write(root: str, pass_: str, d: dict, replace: bool = False, voices: bool = True) -> dict:
    """The draft's cues written (their specs) and its hits put in the pass's mix; `voices`
    turns the mix's dialogue to voices only, so the takes' own music is gone under the score.
    DraftError when an earlier draft is there and `replace` isn't set. Returns {"cues",
    "hits", "removed", "voices_only"}."""
    fresh, kept = _drafts(root, d.get("rendered", False))
    old = [c["id"] for c in fresh]
    keep_hits = {h for c in kept for h in c.get("hits") or []}
    if old and not replace:
        raise DraftError(f"the episode has a draft already ({', '.join(old)}): replace it, "
                         f"or delete those cues first")
    removed = []
    left = {c["id"]: c for c in fresh}
    while left:
        # a cue another one still takes its theme from goes after it
        used = {(c.get("theme") or {}).get("cue") for c in left.values()}
        now = [cid for cid in sorted(left) if cid not in used] or sorted(left)[:1]
        for cid in now:
            try:
                CU.delete(root, cid)
                removed.append(cid)
            except CU.CueError as e:
                raise DraftError(f"{cid} can't be replaced: {e}") from None
            left.pop(cid)
    cues = [c for c in d["cues"] if c.get("spec")]
    # earlier drafts' hits out; the story maker first, so a cue taking its theme finds it
    raw = MX.check(MX.load(root).get(pass_))
    hits = [x for x in raw.get("hits") or [] if not DRAFT_HIT.match(x["id"]) or x["id"] in keep_hits]
    for c in sorted(cues, key=lambda c: c.get("makes") != "story"):
        CU.save_spec(root, c["spec"])
        hits += c["mix_hits"]
    mix = dict(raw)
    if hits:
        mix["hits"] = hits
    else:
        mix.pop("hits", None)
    if voices:
        tracks = dict(mix.get("tracks") or {})
        tracks["dialogue"] = {**(tracks.get("dialogue") or {}), "voices_only": True}
        mix["tracks"] = tracks
    MX.write(root, pass_, mix)
    return {"cues": [c["id"] for c in cues], "hits": sum(len(c["mix_hits"]) for c in cues),
            "removed": removed, "voices_only": voices or d.get("voices_only", False)}


def _mmss(t: float) -> str:
    return f"{int(t // 60)}:{t % 60:04.1f}"


def summary(d: dict) -> str:
    """The draft as text: its cues, what the rules flag, and the notes."""
    lines = [] if d.get("marked", True) or d.get("laid") else [
        "  ! the script has no beat lines: drafted flat, a cue a sequence (--structure lays one out)"]
    lines += [f"{d['structure'] or 'no structure'}{' (laid out)' if d.get('laid') else ''}: {len(d['beats'])} beat(s), "
             f"{sum(1 for c in d['cues'] if c.get('spec'))} cue(s)"]
    for c in d["cues"]:
        theme = (f"from {c['spec']['theme'].get('cue') or c['spec']['theme'].get('theme')}"
                 if c.get("spec", {}).get("theme") else "makes the story theme" if c.get("makes") else "")
        secs = " | ".join(f"{s['name']}: {s['words'] or '—'} ({s['from']:g}→{s['to']:g})" for s in c["sections"])
        head = f"  {c.get('id', '--'):4} {c['kind']:6} {_mmss(c['t0'])}–{_mmss(c['t1'])} {c['t1'] - c['t0']:5.1f} s"
        lines.append(f"{head}  {secs}" + (f"  [{theme}]" if theme else "")
                     + (f"  ({c['trim']})" if c.get("trim") else "")
                     + (f"  ({len(c['hits'])} hit(s))" if c["hits"] else "")
                     + (f"  -- left out: {c['skip']}" if c.get("skip") else ""))
    for f in d["flags"]:
        lines.append(f"  ! {f['shot']}: {f['text']}")
    for n in d["notes"]:
        lines.append(f"  - {n}")
    if d.get("missing"):
        lines.append(f"  - {len(d['missing'])} shot(s) have no take yet, timed at their shotlist length "
                     f"({', '.join(d['missing'][:6])}{'...' if len(d['missing']) > 6 else ''})")
    return "\n".join(lines)


def cmd_score_draft(root: str, argv: list[str]) -> int:
    """`seriesmith score-draft <episode> [--pass proxy|final] [--write] [--replace]
    [--keep-sound]`: the first-pass score from the script's structure; shown, and written
    with --write (its cues, its hits, the dialogue to voices only unless --keep-sound)."""
    import argparse

    from seriesmith import takes as T
    ap = argparse.ArgumentParser(prog="seriesmith score-draft")
    ap.add_argument("--pass", dest="pass_", choices=list(T.PASSES), default="final")
    ap.add_argument("--proxy", action="store_const", const="proxy", dest="pass_")
    ap.add_argument("--write", action="store_true", help="write the cues and hits (shown only, without it)")
    ap.add_argument("--replace", action="store_true", help="the earlier draft's cues (dNN) and hits replaced")
    ap.add_argument("--rendered", action="store_true",
                    help="its cues with finished takes replaced too (their takes to _history; a series theme's kept)")
    ap.add_argument("--keep-sound", action="store_true", help="leave the dialogue track as it plays")
    ap.add_argument("--structure", default=None,
                    help="a script with no beat lines: this structure's beats laid over the cut (its name or number)")
    ap.add_argument("--mark", action="store_true", help="with --structure and --write: its beat lines written into the script")
    a = ap.parse_args(argv)
    try:
        d = draft(root, a.pass_, rendered=a.rendered, structure=a.structure)
        print(summary(d))
        if not a.write:
            print("  (nothing written: --write writes it)")
            return 0
        marked = a.mark and mark_script(root, d)
        r = write(root, a.pass_, d, replace=a.replace, voices=not a.keep_sound)
    except (DraftError, CU.CueError, ValueError) as e:
        print(f"  ! {e}")
        return 1
    print(f"  wrote {len(r['cues'])} cue(s) and {r['hits']} hit(s)"
          + (f", replacing {', '.join(r['removed'])}" if r["removed"] else "")
          + ("; the dialogue plays voices only" if not a.keep_sound else "")
          + ("; its beat lines written into the script" if marked else ""))
    return 0
