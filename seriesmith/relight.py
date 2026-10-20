"""A sequence relight: every plate a sequence uses, under another light, at once.

Each relit plate is a location of its own in the series config, written
beside its source:

    "porch_dusk": {"name": "Porch (dusk)", "of": "porch", "relight": "dusk",
                   "description": "<porch's>. It is dusk, ...",
                   "plate": "../refs/_bg/porch_dusk.png"}

`of` names the plate it is relit from, `relight` a relight preset's id
(presets/relight.json, its `place` wording) or the instruction itself. An
edit target generates its plate as an edit of the source's live plate with
that instruction (refs.built_prompt, refs.angle_reference_images), so the
place stays and only the light changes; a target that draws from text only
draws it from the description, which carries the new light too. Every relit
plate of one relight is the same instruction, so a sequence's plates change
alike. Re-pointing rewrites the sequence's `# sqNN <location>` line and its
shots' `plate:` lines to the relit ones, so a flashback or a night version of
a sequence is one request (POST /seriesmith/refs/relight).
"""

from __future__ import annotations

import json
import os
import re

from seriesmith import presets as PR
from seriesmith import refs as R
from seriesmith import source as H


class RelightError(ValueError):
    pass


ID_RE = re.compile(r"^[A-Za-z0-9_]+$")


def _preset(relight: str) -> dict | None:
    return next((p for p in PR.presets_of("relight") if p["id"] == relight), None)


def instruction(relight: str) -> str:
    """The edit instruction of a `relight` value: a preset's place wording,
    else the text as written."""
    p = _preset(relight)
    return p["place"] if p and p.get("place") else relight.strip()


def light_note(relight: str) -> str:
    """The sentence a relit location's description gains, so a prompt read
    from the description (a shot's, a text-only plate) has the new light: the
    instruction without its "Change only ...:" lead-in."""
    text = instruction(relight).strip().rstrip(".")
    if text.lower().startswith("change only") and ":" in text:
        text = text.split(":", 1)[1].strip()
    return (text[:1].upper() + text[1:] + ".") if text else ""


def default_suffix(relight: str) -> str:
    """The id a relit location gets after its source's: the preset's id, else
    "relit"."""
    return relight if _preset(relight) else "relit"


def sequence_locations(ep: str, sequence: str) -> list[str]:
    """The locations a sequence's shots are on (its own and any `plate:`), in
    script order, from the build (shotlist/shots.json). RelightError without a
    build or without that sequence."""
    story = R.episode_story(ep)
    if story is None:
        raise RelightError("the episode isn't built: build it to relight a sequence")
    for sq in story.sequences:
        if sq.id == sequence:
            out = [sq.location]
            for sh in sq.shots:
                if sh.plate and sh.plate not in out:
                    out.append(sh.plate)
            return out
    raise RelightError(f"no sequence {sequence!r} in the build")


def plan(s: R.Series, locations: list[str], relight: str, suffix: str | None = None) -> list[dict]:
    """[{"source", "from", "id", "entry", "exists"}]: the relit location each
    source gets (`from`: the location as given, which may be a relit one of
    `source`: a plate already relit is relit again from its source). One already in the series config with the same `of` and `relight`
    is reused (`exists`); one by that id that is something else is an error,
    as is a source with no live plate to relight."""
    if not isinstance(relight, str) or not relight.strip():
        raise RelightError("relight must be a relight preset id or the instruction")
    relight = relight.strip()
    suffix = suffix or default_suffix(relight)
    if not ID_RE.match(suffix):
        raise RelightError(f"suffix {suffix!r}: letters, digits and _ only")
    preset = _preset(relight)
    label = preset["label"] if preset else suffix.replace("_", " ")
    locs = s.series_cfg.get("locations") or {}
    out, seen = [], set()
    for cur in locations:
        e = locs.get(cur)
        if e is None:
            raise RelightError(f"no location {cur!r} in the series config")
        # a plate that is already relit is relit again from its source
        src = e["of"] if e.get("relight") else cur
        e = locs.get(src) or {}
        if src in seen:
            continue
        seen.add(src)
        plate = e.get("plate")
        if not (plate and os.path.isfile(R.ref_file(s.home, plate))):
            raise RelightError(f"{src!r} has no plate yet: generate or import it first")
        vid = f"{src}_{suffix}"
        have = locs.get(vid)
        if have is not None:
            if have.get("of") != src or have.get("relight") != relight:
                raise RelightError(f"the series config already has a location {vid!r} that "
                                   f"isn't {src!r} relit {relight!r}: pick another suffix")
            out.append({"source": src, "from": cur, "id": vid, "entry": have, "exists": True})
            continue
        folder = plate[:max(plate.rfind("/"), plate.rfind("\\")) + 1]
        ext = os.path.splitext(plate)[1] or ".png"
        note = light_note(relight)
        entry = {"name": f"{e.get('name') or src.replace('_', ' ')} ({label})",
                 "of": src, "relight": relight,
                 "description": e["description"].rstrip().rstrip(".") + "." + (" " + note if note else ""),
                 "plate": f"{folder}{vid}{ext}"}
        out.append({"source": src, "from": cur, "id": vid, "entry": entry, "exists": False})
    if not out:
        raise RelightError("no locations to relight")
    return out


def write_locations(s: R.Series, planned: list[dict]) -> list[str]:
    """Add the planned relit locations that aren't there yet to the series
    config, each right after its source (the save path: a history copy, an
    atomic write, the file's own format). Returns the ids added."""
    new = [p for p in planned if not p["exists"]]
    if not new:
        return []
    try:
        src = H.read_source(s.ep, "series")
        raw = json.loads(src.text)
    except H.SourceError as e:
        raise RelightError(str(e)) from None
    except ValueError as e:
        raise RelightError(f"series.json is not valid JSON ({e}): fix it first") from None
    locs = raw.get("locations")
    if not isinstance(locs, dict):
        raise RelightError("series.json has no locations")
    after: dict[str, list[dict]] = {}
    for p in new:
        after.setdefault(p["source"], []).append(p)
    out = {}
    for k, v in locs.items():
        out[k] = v
        for p in after.get(k, []):
            out[p["id"]] = p["entry"]
    raw["locations"] = out
    H.write_source(src, H.dump_series(raw, src.text))
    return [p["id"] for p in new]


def repoint(ep: str, sequence: str, mapping: dict[str, str]) -> list[str]:
    """Point sequence `sequence` at the relit locations (`mapping`: source ->
    relit): its `# sqNN <location>` line and its shots' `plate:` lines.
    Returns what changed ("sq01", "sh020", ...); the script is written only
    when something did."""
    from seriesmith import promote as P
    from seriesmith.core.series_config import load_series_config
    src = H.read_source(ep, "script")
    cfg = load_series_config(R.load_series(ep).config_file)
    spans, seq_lines = H.script_spans(src.text, H._ids(cfg))
    if sequence not in seq_lines:
        raise RelightError(f"no sequence {sequence!r} in the script (does it parse?)")
    lines = src.text.split("\n")
    changed = []
    head = lines[seq_lines[sequence] - 1]
    m = re.match(r"^(#\s+\S+\s+)(\S+)(.*)$", head)
    if m and m.group(2) in mapping:
        lines[seq_lines[sequence] - 1] = m.group(1) + mapping[m.group(2)] + m.group(3)
        changed.append(sequence)
    text = "\n".join(lines)
    story = R.episode_story(ep)
    shots = next((sq.shots for sq in (story.sequences if story else []) if sq.id == sequence), [])
    edits = {}
    for sh in shots:
        if sh.id not in spans:
            continue
        n = P.key_line(text, spans[sh.id], "plate")
        if n is None:
            continue
        value = text.split("\n")[n - 1].split(":", 1)[1].strip()
        if value in mapping:
            edits[sh.id] = [("plate", mapping[value])]
            changed.append(sh.id)
    if edits:
        text = P.edit_script(text, spans, edits)
    if changed:
        H.write_source(src, text)
    return changed
