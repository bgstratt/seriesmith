"""The gallery's Sound tab: every take of the episode's sound in one listing, a section per
cue, place, shot, voice or line, each take with the file it plays and whether it's the one in
use. Read from the takes' records alone (sidecars, picks, lines.json, the pass's mix): no
audio is decoded, nothing is measured. What one take was made with is `take_detail`, fetched
when it's opened.

Kinds:
- `music`: the episode's cues (`sound/<cue>/tNN.wav`), theme songs among them; in use: the
  take the cue's item in the pass's mix plays. A take pinned as a series theme says so.
- `ambience`: each place's bed (an `ambience:<place>` ref); in use: its picked take.
- `effects`: each shot's effects for the pass (`sound/fx/<pass>/<shot>/tNN.wav`); in use: the
  take the pass's mix plays for it.
- `voices`: each voice ref's samples (`voice:<id>`); in use: the picked one.
- `lines`: each script line's takes from a voice model on a provider (lines.json); in use:
  the picked one.

Left out: a video take's own sound (it's on the take), and stems made from other sound (a
take's voices-only stem, a recording's vocal stem).
"""

from __future__ import annotations

import os

from seriesmith import cue as CU
from seriesmith import fx as FX
from seriesmith import lines as LN
from seriesmith import mix as MX
from seriesmith import refs as R
from seriesmith import targets as TG

KINDS = ("music", "ambience", "effects", "voices", "lines")


def _key(kind: str, sid: str, take: int) -> str:
    return f"{kind}|{sid}|{take}"


def _item(kind: str, sid: str, take: int, path: str | None, use: bool, model: str | None,
          seed, made: str | None, seconds: float | None = None, **more) -> dict:
    return {"key": _key(kind, sid, take), "take": take, "path": path, "use": use, "model": model,
            "seed": seed, "made": made, "seconds": seconds, **more}


def _counts(statuses: list) -> dict:
    return {"queued": sum(1 for s in statuses if s in ("queued", "running")),
            "failed": sum(1 for s in statuses if s == "failed")}


def _mix(ep: str, pass_: str) -> dict:
    try:
        return MX.check(MX.load(ep).get(pass_))
    except ValueError:
        return {}


def _themes(ep: str) -> dict[tuple[str, int], str]:
    """(cue, take) -> the series theme that is that take of this episode's cue."""
    out: dict[tuple[str, int], str] = {}
    try:
        series = CU.J.series_config(ep)
    except Exception:  # noqa: BLE001 - a series config that doesn't read: no themes
        return out
    for name in CU.series_themes(series):
        if name == "_errors":
            continue
        found, _why = CU.series_theme(ep, series, name)
        if found and found.get("root") and os.path.normcase(os.path.normpath(found["root"])) \
                == os.path.normcase(os.path.normpath(ep)):
            out[(found["cue"], int(found["take"]))] = name
    return out


def _billing(ep: str, spec: dict, series: dict | None, seen: dict) -> str | None:
    """targets.billing for the cue's model, each model looked at once."""
    try:
        tid = CU.model_for(spec, series or {})
    except (CU.CueError, ValueError):
        return None
    if tid not in seen:
        try:
            seen[tid] = TG.billing(TG.load_target(tid))
        except (TG.TargetError, ValueError, OSError):
            seen[tid] = None
    return seen[tid]


def music(ep: str, pass_: str) -> list[dict]:
    themes = _themes(ep)
    try:
        series = CU.J.series_config(ep)
    except Exception:  # noqa: BLE001 - no series config: each cue's own model, else the default
        series = None
    seen: dict = {}
    out = []
    for spec in CU.list_cues(ep):
        cid = spec["id"]
        takes = CU.list_takes(ep, cid)
        in_mix = CU.mix_take(ep, pass_, cid)
        items = []
        for sc in sorted(takes, key=lambda t: -t["take"]):
            if sc.get("status") != "ok" or not sc.get("file"):
                continue
            n = sc["take"]
            items.append(_item("music", cid, n, sc["file"], n == in_mix, sc.get("target"), sc.get("seed"),
                               sc.get("finished") or sc.get("created"), CU.take_seconds(ep, sc),
                               theme=themes.get((cid, n))))
        label = spec.get("label") or cid
        out.append({"kind": "music", "id": cid, "name": label if label == cid else f"{label} ({cid})",
                    "note": "song" if spec.get("kind") == "song" else "", "items": items,
                    "paid": _billing(ep, spec, series, seen), **_counts([t.get("status") for t in takes])})
    return out


def _ref_sections(ep: str, kind: str, ref_kind: str) -> list[dict]:
    try:
        s = R.load_series(ep)
    except Exception:  # noqa: BLE001 - no series config: no refs
        return []
    picks: dict[str, dict] = {}
    out = []
    for r in R.series_refs(s):
        if r.kind != ref_kind:
            continue
        if r.home not in picks:
            picks[r.home] = R.read_picks(r.home)
        picked = R.picked_take(picks[r.home], r.id)
        takes = R.list_takes(r)
        items = []
        for t in sorted(takes, key=lambda t: -t.take):
            j = R.take_json(ep, r, t)
            if not t.usable or not j.get("audio"):
                continue
            items.append(_item(kind, r.id, t.take, j["audio"], t.take == picked, j.get("model") or j.get("target"),
                               j.get("seed"), j.get("finished") or j.get("queued"), j.get("seconds"),
                               text=j.get("line") or None))
        note = ", ".join((r.entry.get("locations") or [])) if ref_kind == "ambience" else ""
        out.append({"kind": kind, "id": r.id, "name": r.name, "note": note, "items": items,
                    **_counts([t.status for t in takes])})
    return out


def effects(ep: str, pass_: str, mix: dict) -> list[dict]:
    out = []
    for s in FX.shots(ep, pass_, mix):
        shot = s["shot"]
        takes = FX.list_takes(ep, pass_, shot)
        items = []
        for sc in sorted(takes, key=lambda t: -t["take"]):
            if sc.get("status") != "ok":
                continue
            p = FX.take_paths(ep, pass_, shot, sc["take"])
            if not os.path.isfile(p["wav"]):
                continue
            items.append(_item("effects", shot, sc["take"], p["rel"], sc["take"] == s.get("picked"),
                               sc.get("target"), sc.get("seed"), sc.get("finished") or sc.get("created"),
                               sc.get("take_seconds")))
        out.append({"kind": "effects", "id": shot, "name": shot, "note": "", "items": items,
                    **_counts([t.get("status") for t in takes])})
    return out


def lines(ep: str) -> list[dict]:
    record = LN.load(ep)
    out = []
    for lid, row in (record.get("lines") or {}).items():
        takes = row.get("takes") or []
        items = []
        for t in sorted(takes, key=lambda t: -t.get("take", 0)):
            if t.get("status") != "ok" or not t.get("file"):
                continue
            items.append(_item("lines", lid, t["take"], t["file"], t["take"] == row.get("picked"),
                               t.get("target") or ("a file" if t.get("source") == "file" else None),
                               None, t.get("finished"), t.get("seconds"), text=t.get("text"),
                               who=t.get("voice_name")))
        said = next((t.get("text") for t in takes if t.get("text")), "")
        who = next((t.get("voice_name") for t in takes if t.get("voice_name")), "")
        out.append({"kind": "lines", "id": lid, "name": lid,
                    "note": " · ".join(x for x in (who, f"“{said}”" if said else "") if x),
                    "items": items, **_counts([t.get("status") for t in takes])})
    return out


def listing(ep: str, pass_: str) -> dict:
    """{"sections": [{"kind", "id", "name", "note", "items", "queued", "failed"}], in KINDS'
    order, each section's items newest first: {"key", "take", "path" (relative to the episode),
    "use", "model", "seed", "made", "seconds", and a kind's own: "theme" (music), "text" (a
    line's words, a voice sample's), "who" (a line's voice)}; "errors": a kind that couldn't
    be read, [{"kind", "error"}], the rest still listed}."""
    mix = _mix(ep, pass_)
    makers = {"music": lambda: music(ep, pass_), "ambience": lambda: _ref_sections(ep, "ambience", "ambience"),
              "effects": lambda: effects(ep, pass_, mix), "voices": lambda: _ref_sections(ep, "voices", "voice"),
              "lines": lambda: lines(ep)}
    sections, errors = [], []
    for kind in KINDS:
        try:
            # a cue, place or voice with no take at all isn't sound yet
            sections += [x for x in makers[kind]() if x["items"] or x["queued"] or x["failed"]]
        except (OSError, ValueError) as e:
            errors.append({"kind": kind, "error": str(e)})
    return {"sections": sections, "errors": errors}


def _row(label: str, value) -> list | None:
    if value is None or value == "" or value == [] or value == {}:
        return None
    return [label, value if isinstance(value, str) else str(value)]


def take_detail(ep: str, pass_: str, kind: str, sid: str, take: int) -> dict:
    """What one take was made with, for the gallery's panel when it opens: {"prompt" (the words
    it was made from, or null), "rows": [[label, value]]}. KeyError when there's no such take."""
    rows: list = []
    prompt = None
    if kind == "music":
        sc = next((t for t in CU.list_takes(ep, sid) if t["take"] == take), None)
        if sc is None:
            raise KeyError(f"{sid} has no take {take}")
        p = sc.get("prompt") or {}
        prompt = p.get("prompt") if isinstance(p, dict) else str(p)
        fit = (sc.get("plan") or {}).get("fit") or {}
        heard = sc.get("measured") or {}
        rf = sc.get("rendered_for") or {}
        rows = [_row("Model", sc.get("target")), _row("Seed", sc.get("seed")), _row("Made", sc.get("finished")),
                _row("Asked", f"{rf['bpm']:g} BPM, {rf.get('bars')} bars" if rf.get("bpm") else None),
                _row("Tempo", f"{fit['bpm']:g} BPM" if fit.get("bpm") else None),
                _row("Heard", f"{heard['bpm_heard']:g} BPM" if heard.get("bpm_heard") else None),
                _row("Score", heard.get("score")), _row("Length", CU.take_seconds(ep, sc))]
    elif kind == "effects":
        sc = FX.get_take(ep, pass_, sid, take)
        if sc is None:
            raise KeyError(f"{sid} has no effects take {take}")
        src = sc.get("source") if isinstance(sc.get("source"), dict) else {}
        p = sc.get("prompt")
        prompt = p.get("prompt") if isinstance(p, dict) else (p or sc.get("text"))
        rows = [_row("Model", sc.get("target")), _row("Seed", sc.get("seed")), _row("Made", sc.get("finished")),
                _row("Made from", f"{sid} t{src['take']:02d} ({src.get('pass') or pass_})" if src.get("take") else None),
                _row("Length", sc.get("take_seconds"))]
    elif kind in ("ambience", "voices"):
        s = R.load_series(ep)
        r = next((x for x in R.series_refs(s) if x.id == sid), None)
        if r is None:
            raise KeyError(f"there's no {sid}")
        t = next((x for x in R.list_takes(r) if x.take == take), None)
        if t is None:
            raise KeyError(f"{sid} has no take {take}")
        j = R.take_json(ep, r, t)
        prompt = j.get("prompt") or j.get("line")
        rows = [_row("Model", j.get("model") or j.get("target")), _row("Seed", j.get("seed")),
                _row("Made", j.get("finished")), _row("Source", j.get("source")), _row("Length", j.get("seconds")),
                _row("Note", j.get("note"))]
    elif kind == "lines":
        row = (LN.load(ep).get("lines") or {}).get(sid) or {}
        t = next((x for x in row.get("takes") or [] if x.get("take") == take), None)
        if t is None:
            raise KeyError(f"{sid} has no take {take}")
        prompt = t.get("text")
        rows = [_row("Voice", t.get("voice_name")), _row("Model", t.get("target")),
                _row("Source", "cut from a file" if t.get("source") == "file" else None),
                _row("Length", t.get("seconds"))]
    else:
        raise KeyError(f"no sound kind {kind}")
    return {"prompt": prompt, "rows": [r for r in rows if r]}
