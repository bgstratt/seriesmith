"""
The steps of a shot's compile that every video target's compile does the same
way, whatever the model: they were copies in ltx2, H3 FL2VA, ltx2_ingredients
and the prose targets (video_prose: Wan, every Comfy Router model, a workflow of
yours). A target's own compile still runs its own steps in its own order: these
are plain functions it calls, not a base it fits into, so a model that takes
things its own way says so where it compiles. H3 Ref2VA's legacy path is its
own (its entries' shape, voices and retention, the latent hold).

    check_shot(series_cfg, sq, shot)          -> (location key, pace)
    shot_duration(ctx, shot, pace)            -> (seconds, from a recording window)
    snap_frames(ctx, shot, dur)               -> (frames asked, frames rendered)
    crammed(ctx, shot, pace, raw, advice)     the CRAMMED warning
    shot_audio(ctx, shot)                     -> (intent, policy, note)
    shot_layers(series_cfg, sq, shot, profiles)
    entry_head(ctx, sq, shot, ...)            id ... audio_policy, in the shotlist's order
    entry_tail(ctx, sq, shot, ...)            audio note, model, LoRA, profile, length
    fallback_warnings / override_warnings / episode_report
    legal_size(target, base, pass_, warnings)

A ctx is any object with target, series_cfg, pass_, preset, fps, warnings,
total_req, total_raw and fallbacks. Every shotlist, prompt and check line these
write is in the goldens. Stdlib only.
"""
from __future__ import annotations

from seriesmith import targets as TG
from seriesmith.core import ir
from seriesmith.core.ir import stable_seed
from seriesmith.core.speech import (RATE_CEILING, SPEECH_RATE, forced_rate, pacing,
                                    speech_seconds)


def lines(shot: ir.Shot) -> list[dict]:
    return [{"who": d.speaker, "line": d.line} for d in shot.dialogue]


def check_shot(series_cfg: dict, sq: ir.Sequence, shot: ir.Shot) -> tuple[str, str]:
    """(its location key, its pace), or ValueError naming what's wrong."""
    book = series_cfg["subjects"]
    for s in list(shot.cast) + list(shot.props):
        if s not in book:
            raise ValueError(f"shot {shot.id}: '{s}' is not in series.json's subjects")
    loc_key = shot.plate or sq.location
    if loc_key not in series_cfg["locations"]:
        raise ValueError(f"shot {shot.id}: location '{loc_key}' is not in series.json "
                         f"({', '.join(series_cfg['locations'])})")
    if not shot.cast and not shot.props and not shot.dialogue and not shot.action:
        raise ValueError(f"shot {shot.id}: nothing in it. Add `who:`, `with:`, action "
                         f"text, or dialogue.")
    pace = shot.pace or series_cfg.get("speech", {}).get("pace", "normal")
    if pace not in SPEECH_RATE:
        raise ValueError(f"series.json speech.pace '{pace}' must be one of {sorted(SPEECH_RATE)}")
    return loc_key, pace


def model_duration(ctx, shot: ir.Shot, pace: str) -> tuple[float, dict | None, str]:
    """`dur: model`: (the estimate, the predictor's range or None, a warning
    or ""); see targets.duration_estimate. The range never passes the
    template's longest shot."""
    speech = speech_seconds(lines(shot), pace) if shot.dialogue else None
    est, predict, note = TG.duration_estimate(ctx.target, shot.timing or {}, ctx.preset, speech)
    if predict:
        top = round(ctx.target.template.max / ctx.fps, 2)
        predict["max_seconds"] = min(predict["max_seconds"], top)
        # LTXVDurationPredictor takes 0.5 s at least
        predict["min_seconds"] = max(0.5, min(predict["min_seconds"], predict["max_seconds"]))
        est = min(max(est, predict["min_seconds"]), predict["max_seconds"])
    return est, predict, note


def put_model_duration(ctx, shot: ir.Shot, pace: str, entry: dict) -> None:
    """A `dur: model` entry's own keys: `length_estimated` (its length is the
    build's estimate) and, on a target that predicts, `duration_predict`
    {"min_seconds", "max_seconds"}; elsewhere a warning that the estimate is
    what renders."""
    if not (shot.timing or {}).get("model"):
        return
    _, predict, note = model_duration(ctx, shot, pace)
    entry["length_estimated"] = True
    if predict:
        entry["duration_predict"] = predict
    if note:
        ctx.warnings.append(f"{shot.id}: {note}")


def shotlist_extra(preset) -> dict:
    """The preset values a shotlist's `defaults` carries (not the `dur: model`
    ones, which jobs reads from the target)."""
    return {k: v for k, v in preset.extra.items()
            if not k.startswith("_") and k not in TG.DURATION_PRESET_KEYS}


def shot_duration(ctx, shot: ir.Shot, pace: str) -> tuple[float, bool]:
    """(seconds, from a recording window) as the script asks."""
    t = shot.timing or {}
    if "audio_in" in t:
        return t["audio_out"] - t["audio_in"], True
    if t.get("model"):
        return model_duration(ctx, shot, pace)[0], False
    if t.get("auto"):
        if not shot.dialogue:
            raise ValueError(f"shot {shot.id}: `dur: auto` needs dialogue to measure. "
                             f"Give a silent shot an explicit `dur:`.")
        return speech_seconds(lines(shot), pace), False
    if "seconds" in t:
        return float(t["seconds"]), False
    raise ValueError(f"shot {shot.id}: needs `audio: 3.10-7.40`, `dur: 3.04`, or `dur: auto`")


def snap_frames(ctx, shot: ir.Shot, dur: float) -> tuple[int, int]:
    """(the frames `dur` asks for, the frames the target renders: its grid),
    counted into the episode's totals. A shot past the target's longest says
    so in words."""
    template, fps = ctx.target.template, ctx.fps
    req = max(1, round(dur * fps))
    try:
        raw = template.snap(req)
    except ValueError:
        raise ValueError(f"shot {shot.id}: {dur:.2f}s is longer than {ctx.target.short}'s "
                         f"maximum of {template.max} frames ({template.max / fps:.2f}s at "
                         f"{fps:g} fps). Split the shot, or render it on another "
                         f"target.") from None
    return req, raw


def count_frames(ctx, req: int, raw: int) -> None:
    ctx.total_req += req
    ctx.total_raw += raw


def crammed(ctx, shot: ir.Shot, pace: str, raw: int, advice: str | None = None) -> None:
    """The CRAMMED warning for lines too many for the frames they get; its
    advice by default the length that gives them room."""
    if not shot.dialogue:
        return
    template, fps = ctx.target.template, ctx.fps
    held = raw / fps
    rate = forced_rate(lines(shot), held)
    syl, _ = pacing(lines(shot))
    if rate > RATE_CEILING:
        if advice is None:
            fits = template.snap(max(1, round(speech_seconds(lines(shot), pace) * fps))) / fps
            advice = f"`dur: {fits:.2f}` gives it room."
        ctx.warnings.append(f"{shot.id}: CRAMMED — {syl} syllables in {held:.2f}s forces "
                            f"{rate:.1f} syl/s (ceiling {RATE_CEILING}). {advice}")


def shot_audio(ctx, shot: ir.Shot) -> tuple[str, str, str]:
    """(the audio the script asks for, the policy the target renders it with,
    why they differ or ""); a fallback is noted for fallback_warnings."""
    intent = TG.audio_intent(shot, ctx.series_cfg, ctx.pass_)
    policy, note = ctx.target.audio_policy(intent)
    if note:
        ctx.fallbacks.setdefault(intent, []).append(shot.id)
    return intent, policy, note


def check_dub_window(ctx, shot: ir.Shot, policy: str) -> None:
    """A dub is spoken to its window of the recorded track: ValueError for a
    dub shot without one, as H3's compile says it."""
    if policy in ("dub", "dub_keep_foley") and "audio_in" not in (shot.timing or {}):
        raise ValueError(f"shot {shot.id}: policy {policy} needs an `audio: in-out` window "
                         f"on the recorded track (`seriesmith align` writes these).")


def shot_layers(series_cfg: dict, sq: ir.Sequence, shot: ir.Shot, profiles) -> list:
    """The settings that apply to the shot, sequence then shot (targets.render_layers)."""
    seq = {"id": sq.id, "profile": sq.profile, "target": sq.target,
           **{k: v for k, v in (sq.overrides or {}).items() if v is not None}}
    sh = {"id": shot.id, "profile": shot.profile, "target": shot.target,
          **{k: v for k, v in (shot.overrides or {}).items() if v is not None}}
    for node in (sq, shot):
        if "steps" in node.unparsed:
            raise ValueError(f"{'shot' if node is shot else 'sequence'} {node.id}: steps "
                             f"must be a whole number, not {node.unparsed['steps']!r}")
    return TG.render_layers(series_cfg, seq, sh, profiles)


def entry_head(ctx, sq: ir.Sequence, shot: ir.Shot, ep_id: str, loc_key: str, raw: int,
               layers, policy: str) -> dict:
    """An entry's first keys, id to audio_policy, in the shotlist's order; the
    target adds its prompt and its own keys after them."""
    return {
        "id": shot.id,
        "sequence": sq.id,
        "subjects": list(shot.cast) + [p for p in shot.props if p not in shot.cast],
        "background": ctx.series_cfg["locations"][loc_key].get("plate", ""),
        "size": shot.size,
        "length": raw,
        "seed": stable_seed(ep_id, sq.id, shot.id),
        "steps": int(TG.layered(layers, "steps", ctx.preset.steps, present=True)),
        "audio_policy": policy,
    }


def entry_tail(ctx, sq: ir.Sequence, shot: ir.Shot, entry: dict, layers, intent: str,
               note: str, dur: float, windowed: bool, pace: str) -> dict:
    """An entry's last keys: the audio fallback's note, model, LoRA, profile,
    then the recording window or the length (and `dur: model`'s)."""
    if note:
        entry["audio_intent"] = intent
        entry["audio_note"] = note
    model = TG.layered(layers, "model")
    if model:
        entry["model"] = model
    lora = TG.layered_lora(layers)
    if lora:
        entry[lora[0]] = lora[1]
    profile = shot.profile or sq.profile
    if profile:
        entry["profile"] = profile
    t = shot.timing or {}
    if windowed:
        entry["audio_in"], entry["audio_out"] = t["audio_in"], t["audio_out"]
    else:
        entry["duration"] = round(dur, 3)
    put_model_duration(ctx, shot, pace, entry)
    return entry


def legal_size(target, base, pass_: str, warnings: list) -> tuple[int, int]:
    """`base`'s size fitted to what the target can render, saying so when it moved."""
    w, h = int(base.width), int(base.height)
    width, height = target.template.fit_size(w, h)
    if (width, height) != (w, h):
        warnings.append(f"{pass_} size {w}x{h} is not legal on {target.short}; "
                        f"rendering {width}x{height}")
    return width, height


def fallback_warnings(ctx, target) -> None:
    """One line per audio the script asks for that the target renders as generate."""
    for intent, ids in sorted(ctx.fallbacks.items()):
        ctx.warnings.append(f"{len(ids)} shot(s) ask for audio {intent}, which {target.short} "
                            f"can't render ({(target.recipe.get('policy_fallback') or {}).get('why', '')}): "
                            f"they render with generate: {', '.join(ids[:8])}"
                            + (" …" if len(ids) > 8 else ""))


def override_warnings(ctx, entry: dict) -> None:
    for k in ("model", "lora"):
        if k in entry:
            ctx.warnings.append(f"{entry['id']} overrides {k}: {entry[k]}")


def episode_report(ctx, story: ir.Episode, target, shots_out: list, seqs: int,
                   needed: dict, blocked: dict, size_hints: dict) -> dict:
    """The build's report of a pass on a target (build --check prints it)."""
    p, fps = ctx.preset, ctx.fps
    return {
        "episode": story.id, "title": story.title,
        "mode": "proxy" if ctx.pass_ == "proxy" else "final",
        "resolution": f"{ctx.width}x{ctx.height}", "steps": p.steps,
        "model": p.model, "lora": p.lora or "none", "fps": fps,
        "shots": len(shots_out), "sequences": seqs,
        "target_s": ctx.total_req / fps, "delivered_s": ctx.total_raw / fps,
        "pad_frames": ctx.total_raw - ctx.total_req,
        "policies": {pol: sum(1 for s in shots_out if s["audio_policy"] == pol)
                     for pol in sorted({s["audio_policy"] for s in shots_out})},
        "needed": needed, "blocked_shots": blocked, "warnings": ctx.warnings,
        "target": target.id, "size_hints": dict(size_hints or {}),
    }
