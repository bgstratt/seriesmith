"""
builtin:video_prose — the compile for a video target whose prompt is one
paragraph of prose: the story IR to shotlist entries, the ref slots, and the
graph helpers. A target.json says `"code": "builtin:video_prose"` and ships no
Python; the three Wan 2.2 targets bind it to their own wording and graph
surgery through targets/video/wan/common.py, and a custom target made from a
user's own workflow uses it as it is.

What a target brings to it:

    recipe.prompt         "prose" (the ltx2 writer: sound and spoken lines) or
                          "prose_silent" (the Wan writer: dialogue as acting).
                          Unset: chosen from whether the target makes sound.
    capabilities.audio    "none" makes every shot silent, warns once, and
                          switches the prompt to the silent writer.
    recipe.keyframes      which ends a shot may pin; `keyframe_required` makes
                          one a blocker (Wan 14B I2V's first frame).
    recipe.reference_image  compose the shot's subjects into one picture (VACE).
    binding.inputs        where a keyframe's LoadImage is, declaratively, for a
                          target with no patch_graph of its own (`keyframe_inputs`).

An entry carries the neutral keys every target's entries do (id, sequence,
subjects, background, size, length, seed, steps, audio_policy, prompt, plus
duration / audio_in-audio_out), `negative` (the preset's), `keyframes`
{first[, last]} (the conventional paths, as ltx2's), and for a target whose
recipe has a `reference_image` (VACE) `panels`: the shot's subjects, in order,
each {"subject", "kind", "path", "view"?} (the plate only when the recipe
asks for it). Paths are the series config's (the picked, live files).

Audio: a target that makes none (`capabilities.audio: "none"`, the Wan
targets) renders every policy as `silent` (recipe.policies ["silent"], the
fallback from any other), so each entry has audio_intent / audio_note and each
take says so; dialogue shots get one `--check` warning (the lines are acted
silently, prompt.acting). A target that does make sound keeps the intent it
was asked for.

Sizes: a target renders its own presets' sizes unless it is the series target:
another model's pass block (H3's 448x256 proxy) is far below the 480p/720p Wan
was trained at, so it lends no size.

Stdlib only.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

from seriesmith import targets as TG
from seriesmith.targets import moderate as MOD
from seriesmith.core import framing, ir
from seriesmith.targets.video.ltx2.compile import _duration, shotlist_extra
from seriesmith.core import paths as P
from seriesmith.targets import video_compile as VC
from seriesmith.targets.graph import of, consumers, new_id  # noqa: F401

SILENT = "silent"
PLATE = "plate"                      # the absent-set name of the plate


@dataclass
class Style:
    """What a prose target words its own way. `build_prompt(shot, seq,
    series_cfg)` writes the paragraph; `silent_dialogue` is the `--check`
    warning for dialogue a silent model can't voice, with {n} and {ids}
    ("" for none). Defaults come from the target (style_for)."""
    build_prompt: object
    silent_dialogue: str = ("{n} dialogue shot(s): no audio or lip-sync on {short} "
                            "(the lines are acted silently): {ids}")


def prose_writer(silent: bool):
    """The prose writer a target gets: the Wan one (dialogue as silent acting)
    for a model that makes no sound, else the ltx2 one (soundscape and spoken
    lines). Imported on use, so neither target package is needed until then."""
    if silent:
        from seriesmith.targets.video.wan.prompt import build_prompt as fn
    else:
        from seriesmith.targets.video.ltx2.prompt import build_prompt as fn
    return fn


def style_for(target, style: "Style | None" = None) -> Style:
    """`style`, else the one the target's own data asks for. A target that makes
    no sound gets the silent writer whatever else it says (a soundscape and
    quoted lines would describe something it can't render); `recipe.prompt:
    "prose_silent"` asks for that writer on a target that *can* make sound —
    a picture-only graph whose audio comes from the edit."""
    if style is not None:
        return style
    silent = (not makes_sound(target)
              or (target.recipe.get("prompt") or "").strip() == "prose_silent")
    return Style(prose_writer(silent))


def makes_sound(target) -> bool:
    """Whether this target renders audio at all (`capabilities.audio`)."""
    return (target.capabilities() or {}).get("audio", "generate") != "none"


def default_policy(target) -> str:
    """The `audio_policy` a shotlist's defaults carry: what this target renders
    when nothing asks for anything else."""
    policies = target.policies
    return "generate" if "generate" in policies else (policies[0] if policies else SILENT)


def keyframe_path(recipe: dict, shot_id: str, end: str) -> str:
    """Where a shot's keyframe lives (refs' `shot:<id>:<end>` ref)."""
    return recipe["keyframe_path"].format(shot=P.safe_id(shot_id),
                                          end=end)


def is_series_target(target, series_cfg: dict) -> bool:
    return ((series_cfg.get("series") or {}).get("target")
            or TG.machine_default("video")) == target.id


class Ctx:
    """One pass of one episode: the preset, the size, the report, and (VACE)
    the refs the shots need. `absent` names refs to compile WITHOUT (render
    anyway): subject ids and/or "plate"."""

    def __init__(self, target, series_cfg: dict, pass_: str, absent=None, style=None):
        self.target, self.series_cfg, self.pass_ = target, series_cfg, pass_
        self.style = style_for(target, style)
        self.silent = not makes_sound(target)
        self.recipe = target.recipe
        self.preset = target.preset(pass_, series_cfg)
        self.fps = target.template.fps_for(series_cfg)
        self.warnings: list[str] = []
        base = self.preset if is_series_target(target, series_cfg) else target.presets[pass_]
        self.width, self.height = VC.legal_size(target, base, pass_, self.warnings)
        self.total_req = self.total_raw = 0
        self.long: list[str] = []                 # "<shot> <frames>" past the trained length
        self.talking: list[str] = []              # shots with dialogue
        self.intents: dict[str, int] = {}         # audio intent -> shots (all render silent)
        self.fallbacks: dict[str, list[str]] = {}  # audio intent -> the shots it falls back on
        self.profiles = TG.series_profiles(series_cfg)
        self.recording = series_cfg.get("audio", {}).get("track", "")
        self.needed: dict[str, dict] = {}
        self.blocked: dict[str, list[str]] = {}
        self.image = TG.image_target(series_cfg)
        self.absent = set(absent or ())

    def need(self, req: TG.RefRequest, shot_id: str) -> None:
        if req.path:
            self.needed.setdefault(req.path, {"kind": req.kind,
                                              "prompt": self.image.ref_prompt(req, self.series_cfg)})
            if shot_id not in self.blocked.setdefault(req.path, []):
                self.blocked[req.path].append(shot_id)


# ---------------------------------------------------------------------------
# the reference image's panels (a recipe with `reference_image`: VACE)
# ---------------------------------------------------------------------------

def _hint(recipe: dict, kind: str) -> str:
    return (recipe.get("size_hints") or {}).get(kind, "")


def subject_request(recipe: dict, sid: str, entry: dict, slot: str | None = None) -> TG.RefRequest:
    if entry.get("kind", "character") == "character":
        r = recipe["refs"]["character"]
        label, views = r["kind"], int(r.get("views", 1))
    else:
        r = recipe["refs"]["object"]
        label, views = r["kind"].format(kind=entry.get("kind", "prop")), 1
    return TG.RefRequest(entry.get("sheet") or "", label, r["shape"], subject=sid,
                         views=views, slot=slot, entry=entry, size_hint=_hint(recipe, label))


def plate_request(recipe: dict, key: str, entry: dict, slot: str | None = None) -> TG.RefRequest:
    r = recipe["refs"]["location"]
    return TG.RefRequest(entry.get("plate") or "", r["kind"], r["shape"], location=key,
                         slot=slot, entry=entry, size_hint=_hint(recipe, r["kind"]))


def ordered(shot: ir.Shot, book: dict) -> list[str]:
    """The shot's subjects in panel order: characters, then props and
    vehicles, each in script order."""
    subjects = list(shot.cast) + [p for p in shot.props if p not in shot.cast]
    chars = [s for s in subjects if book[s].get("kind", "character") == "character"]
    return chars + [s for s in subjects if s not in chars]


def panel_view(ref: dict, subjects: list[str], book: dict, size: str) -> str:
    """Which panel of a character's 4-panel sheet goes on the reference: the
    face on a single-character close-up, else the three-quarter body (the H3
    loader's choice, as ltx2_ingredients)."""
    return ("face" if len(subjects) == 1
            and book[subjects[0]].get("kind", "character") == "character"
            and framing.in_sizes(size, ref.get("face_sizes", ())) else "body")


def panels(ctx: Ctx, shot: ir.Shot, loc_key: str) -> list[dict]:
    ref = ctx.recipe.get("reference_image")
    if not ref:
        return []
    book, series_cfg = ctx.series_cfg["subjects"], ctx.series_cfg
    subjects = ordered(shot, book)
    view = panel_view(ref, subjects, book, shot.size)
    out = []
    for s in subjects:
        e = book[s]
        ctx.need(subject_request(ctx.recipe, s, e), shot.id)
        if s in ctx.absent:
            continue
        p = {"subject": s, "kind": e.get("kind", "character"), "path": e.get("sheet", "")}
        if p["kind"] == "character" and int(e.get("sheet_panels") or 0) != 1:     # a whole picture: no view
            p["view"] = view
        out.append(p)
    loc = series_cfg["locations"][loc_key]
    if ref.get("plate") and loc.get("plate"):
        ctx.need(plate_request(ctx.recipe, loc_key, loc), shot.id)
        if PLATE not in ctx.absent:
            out.append({"location": loc_key, "kind": "plate", "path": loc["plate"]})
    return out


def capped(pics: list[dict], target) -> tuple[list[dict], list[dict]]:
    """(the panels a hosted model is sent, the ones it isn't), by the rule
    router_video.pictures sends them: the subjects up to its `max`, then the
    plate, all of it cut to its `max_total`. Everything for a local target."""
    refs = (((target.spec.get("router") or {}).get("inputs") or {}).get("references")
            if isinstance(target.spec.get("router"), dict) else None)
    if not refs:
        return list(pics), []
    most = refs.get("max") or target.capabilities().get("max_subjects") or 99
    subjects = [p for p in pics if p.get("subject")]
    sent = subjects[:most] + [p for p in pics if not p.get("subject")]
    if refs.get("max_total"):
        sent = sent[:refs["max_total"]]
    return sent, [p for p in pics if p not in sent]


def unsent_warning(ctx: Ctx, shot: ir.Shot, pics: list[dict]) -> str | None:
    """What --check says when a hosted model takes fewer pictures than the
    shot has: who isn't sent (the prose still describes them)."""
    sent, dropped = capped(pics, ctx.target)
    if not dropped:
        return None
    book = ctx.series_cfg.get("subjects") or {}
    names = [(book.get(p["subject"]) or {}).get("name", p["subject"]) if p.get("subject")
             else "the plate" for p in dropped]
    return (f"{shot.id}: {ctx.target.short} takes {len(sent)} picture(s); "
            f"{', '.join(names)} not sent as pictures (the prose still describes "
            f"{'them' if any(p.get('subject') for p in dropped) else 'the place'})")


# ---------------------------------------------------------------------------
# the compile
# ---------------------------------------------------------------------------

def compile_entry(ctx: Ctx, sq: ir.Sequence, shot: ir.Shot, ep_id: str) -> dict:
    series_cfg, template = ctx.series_cfg, ctx.target.template
    loc_key, pace = VC.check_shot(series_cfg, sq, shot)
    dur, windowed = _duration(ctx, shot, pace)
    req, raw = VC.snap_frames(ctx, shot, dur)
    if shot.dialogue:
        ctx.talking.append(shot.id)
    VC.crammed(ctx, shot, pace, raw)
    trained = int(template.spec.get("trained_frames") or 0)
    if trained and raw > trained:
        ctx.long.append(f"{shot.id} {raw}")
    VC.count_frames(ctx, req, raw)
    intent, policy, note = VC.shot_audio(ctx, shot)
    ctx.intents[intent] = ctx.intents.get(intent, 0) + 1
    layers = VC.shot_layers(series_cfg, sq, shot, ctx.profiles)
    entry = VC.entry_head(ctx, sq, shot, ep_id, loc_key, raw, layers, policy)
    # a hosted model's content filter reads it: its subjects' designs without
    # what describes a body (targets.moderate; the pictures carry the look)
    told = MOD.moderated_config(series_cfg) if ctx.target.moderated else series_cfg
    entry["prompt"] = ctx.style.build_prompt(shot, sq, told)
    entry["negative"] = ctx.preset.extra.get("negative", "")
    entry["keyframes"] = {end: keyframe_path(ctx.recipe, shot.id, end)
                          for end in TG.keyframe_ends(ctx.recipe, shot, sq)}
    if ctx.recipe.get("reference_image"):
        entry["panels"] = panels(ctx, shot, loc_key)
        note_ = unsent_warning(ctx, shot, entry["panels"])
        if note_:
            ctx.warnings.append(note_)
    return VC.entry_tail(ctx, sq, shot, entry, layers, intent, note, dur, windowed, pace)


def board_parts(shot: ir.Shot, series_cfg: dict, sent_of: dict) -> dict:
    """One shot of a storyboard (a model that takes each shot's own short
    prompt, Kling's 512 characters), in pieces router_video puts together by
    priority: `frame` (its framing and who is in it) and `lines` always, then
    `action`, `camera` and `sound` while there is room. The place and the
    people's looks are the pictures', so they aren't said; `subjects` are the
    pictures in it (the ids sent), for naming them (docs/MULTISHOT.md)."""
    book = series_cfg.get("subjects") or {}

    def name(s: str) -> str:
        e = book.get(s) or {}
        return e.get("name") or (book.get(e.get("of")) or {}).get("name") or s

    def cap(n: str) -> str:
        return n[:1].upper() + n[1:]

    on = list(shot.cast) + [p for p in shot.props if p not in shot.cast]
    who = [name(s) for s in on]
    frame = framing.article(framing.term(shot.size))
    listed = (", ".join(who[:-1]) + " and " + who[-1]) if len(who) > 1 else (who[0] if who else "")
    cam = framing.orbit((shot.camera or "").strip().rstrip("."), ", ".join(who))
    lines = []
    for d in shot.dialogue:
        how = f", {d.delivery.strip()}" if (d.delivery or "").strip() else ""
        where = {"vo": " in voiceover", "os": " from off screen"}.get(d.mode, "")
        lines.append(f'{cap(name(d.speaker))} says{where}{how}: "{d.line.strip()}"')
    return {"frame": f"{frame} of {listed}." if listed else f"{frame}.",
            "camera": f"The camera {cam}." if cam else "",
            "action": (shot.action or "").strip(),
            "lines": " ".join(lines),
            "sound": f"Sound: {shot.sound.strip().rstrip('.')}." if (shot.sound or "").strip() else "",
            "subjects": list(dict.fromkeys(sent_of.get(s, s) for s in on))}


def compile_group(ctx: Ctx, sq: ir.Sequence, group: list[ir.Shot], ep_id: str) -> dict:
    """One entry for a `continuous: multishot` group (docs/MULTISHOT.md) on a
    hosted model: each shot compiled as itself (its checks), then joined into
    one call: its pictures (each person once, the first picture named; as many
    plates as the target's `multishot.plates`, "all" for every shot's), one
    length on the model's grid, and the prompt in the target's form: `prose`,
    one paragraph per shot after the look, each a hard cut from the one
    before; `brief` (Kling v3 Omni) the same in one shorter prompt, the look,
    the place and who's who said once (a few features each), then each shot's
    framing, action, lines and sound under its whole seconds (board_parts);
    `storyboard` the prose as a fallback, and `storyboard`, each
    shot's own prose and whole seconds (adding up to the call's), which the
    call sends as the model's storyboard fields (router_video)."""
    spec = ctx.target.spec.get("multishot") or {}
    ids = f"{group[0].id}-{group[-1].id}"
    if not spec.get("form"):
        raise ValueError(f"shots {ids}: a `continuous: multishot` group, and {ctx.target.short} "
                         f"renders one shot a call (no multishot form): render the group on a "
                         f"model that has one, or break it with `continuous: none`")
    before = ctx.total_raw
    entries = [compile_entry(ctx, sq, s, ep_id) for s in group]
    fps = ctx.fps
    frames = [max(1, round((e["duration"] if "duration" in e else e["audio_out"] - e["audio_in"])
                           * fps)) for e in entries]
    want = sum(frames)
    try:
        raw = ctx.target.template.snap(want)
    except ValueError:
        raise ValueError(f"shots {ids}: {want / fps:.2f}s in one call, and {ctx.target.short} makes "
                         f"at most {ctx.target.template.max / fps:.0f}s: split the group "
                         f"(`continuous: none` on a shot starts the next one)") from None
    most = spec.get("max_shots")
    if most and len(group) > int(most):
        raise ValueError(f"shots {ids}: {len(group)} shots in one call, and {ctx.target.short} "
                         f"takes at most {most}: split the group")
    frames[-1] += raw - want
    starts, at = [], 0
    for f in frames:
        starts.append(at)
        at += f
    ctx.total_raw = before + raw
    # whole seconds a shot, at least one each, adding up to the call's
    secs = [max(1, round(f / fps)) for f in frames]
    secs[-1] = max(1, round(raw / fps) - sum(secs[:-1]))

    # the pictures: each person once (the first picture named), then the plates
    from seriesmith.core.series_config import variant_of
    variants = variant_of(ctx.series_cfg)
    people, places, seen = [], [], set()
    for e in entries:
        for p in e.get("panels") or []:
            if p.get("subject"):
                who = variants.get(p["subject"], p["subject"])
                if who not in seen:
                    seen.add(who)
                    people.append(p)
            elif p not in places:
                places.append(p)
    plates = spec.get("plates", 1)
    places = places if plates == "all" else places[:int(plates)]

    look = ((ctx.series_cfg.get("style") or {}).get("look") or "").strip().rstrip(".")
    lead = f"Style: {look}." if look else ""

    def body(e: dict) -> str:
        text = e["prompt"]
        return text[len(lead):].lstrip() if lead and text.startswith(lead) else text

    n = len(group)
    count = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}.get(n, str(n))
    paras = [f"{lead} A scene in {count} shots, each a hard cut from the one before.".strip()]
    # said once: a place already described is "the same place" after, and a
    # person's look (`<Name> is <design>.`) isn't said again
    places_said, looks_said = set(), set()
    for i, (s, e) in enumerate(zip(group, entries)):
        text = body(e)
        key = s.plate or sq.location
        env = ((ctx.series_cfg.get("locations") or {}).get(key) or {}).get("description", "")
        env = env.strip().rstrip(".")
        if env and key in places_said:
            text = text.replace(env, "the same place")
        places_said.add(key)
        kept = []
        for sent in re.findall(r'[^.!?"]*(?:"[^"]*"[^.!?"]*)*[.!?]+', text):
            sent = sent.strip()
            look = re.match(r'^[A-Z][^"]* is [^"]*\.$', sent) and not sent.startswith(("There is", "The sound is"))
            if look and sent in looks_said:
                continue
            if look:
                looks_said.add(sent)
            kept.append(sent)
        text = " ".join(kept) or text
        paras.append(f"Shot {i + 1}: {text}" if i == 0 else
                     f"Shot {i + 1}, a hard cut: {text}")
    entry = dict(entries[0])
    for k in ("audio_in", "audio_out"):
        entry.pop(k, None)
    keys = dict(entries[0].get("keyframes") or {})
    keys.pop("last", None)
    if "last" in (entries[-1].get("keyframes") or {}):
        keys["last"] = entries[-1]["keyframes"]["last"]
    entry.update({
        "subjects": list(dict.fromkeys(x for e in entries for x in e["subjects"])),
        "length": raw,
        "duration": round(raw / fps, 3),
        "keyframes": keys,
        "prompt": "\n\n".join(paras),
        "multishot": [{"id": s.id, "start": st, "frames": f, "size": s.size,
                       "plate": s.plate or sq.location}
                      for s, st, f in zip(group, starts, frames)],
    })
    if "panels" in entries[0]:
        entry["panels"] = people + places
    sent_of = {}
    for e in entries:
        for p in e.get("panels") or []:
            if p.get("subject"):
                sent_of[p["subject"]] = next(x["subject"] for x in people
                                             if variants.get(x["subject"], x["subject"])
                                             == variants.get(p["subject"], p["subject"]))
    if spec["form"] == "brief":
        entry["prompt"] = brief_prompt(ctx.series_cfg, sq, group, secs, [p["subject"] for p in people],
                                       sent_of)
    if spec["form"] == "storyboard":
        entry["storyboard"] = [dict(board_parts(s, ctx.series_cfg, sent_of), seconds=sec)
                               for s, sec in zip(group, secs)]
    return entry


def brief_prompt(series_cfg: dict, sq: ir.Sequence, group: list[ir.Shot], secs: list[int],
                 people: list[str], sent_of: dict) -> str:
    """A `continuous: multishot` group as one short prompt (the `brief` form,
    Kling v3 Omni's 2500 characters): the look, the scene's shots and place,
    who's who with a few features each (no body: targets.moderate), then a
    paragraph a shot under its whole seconds (board_parts). The form that held
    Kling's faces where its 512-character storyboard lost them
    (docs/MULTISHOT.md, 2026-10-26)."""
    from seriesmith.targets.generic.router_video import features
    book = series_cfg.get("subjects") or {}
    look = ((series_cfg.get("style") or {}).get("look") or "").strip().rstrip(".")
    place = ((series_cfg.get("locations") or {}).get(group[0].plate or sq.location) or {})
    where = features(place.get("description", ""), 14)

    def name(s: str) -> str:
        e = book.get(s) or {}
        return e.get("name") or (book.get(e.get("of")) or {}).get("name") or s

    n = len(group)
    count = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}.get(n, str(n))
    head = [f"{look[:1].upper()}{look[1:]}." if look else "",
            f"A scene in {count} shots, each a hard cut from the one before"
            + (f", in {where[:1].lower()}{where[1:]}." if where else ".")]
    who = [f"{name(s)}: {features((book.get(s) or {}).get('design', ''), 14, body=False)}"
           for s in people if (book.get(s) or {}).get("design")]
    if who:
        head.append(f"The people, the same in every shot: {'; '.join(who)}.")
    paras = [" ".join(x for x in head if x)]
    for i, (s, sec) in enumerate(zip(group, secs)):
        b = board_parts(s, series_cfg, sent_of)
        body = " ".join(x for x in (b["frame"], b["action"], b["camera"], b["lines"], b["sound"]) if x)
        paras.append(f"Shot {i + 1} ({sec} s): {body}" if i == 0 else
                     f"Shot {i + 1} ({sec} s), a hard cut: {body}")
    return "\n\n".join(paras)


def _ids(ids: list[str], n: int = 8) -> str:
    return ", ".join(ids[:n]) + (" …" if len(ids) > n else "")


def compile_episode(target, story: ir.Episode, series_cfg: dict, pass_: str,
                    only: set[str] | None = None, absent=None, style=None) -> tuple[dict, dict]:
    ctx = Ctx(target, series_cfg, pass_, absent, style)
    shots_out, seqs = [], 0
    for sq in story.sequences:
        mine = [s for s in sq.shots if only is None or s.id in only]
        if mine:
            seqs += 1
        # a `continuous: multishot` group compiles whole at its first shot, which
        # is the id a retargeted render asks for (docs/MULTISHOT.md)
        groups = {g[0].id: g for g in sq.multishot_groups()}
        grouped = {s.id for g in groups.values() for s in g[1:]}
        for s in mine:
            if s.id in groups:
                shots_out.append(compile_group(ctx, sq, groups[s.id], story.id))
            elif s.id not in grouped:
                shots_out.append(compile_entry(ctx, sq, s, story.id))
    p = ctx.preset
    extra = shotlist_extra(p)
    doc = {
        "episode": story.id,
        "title": story.title,
        "target": target.id,
        "defaults": {"width": ctx.width, "height": ctx.height, "fps": ctx.fps,
                     "steps": p.steps, "model": p.model, "lora": p.lora,
                     "audio_policy": default_policy(target),
                     "master_track": ctx.recording, **extra},
        "subjects": {s: {"kind": e.get("kind", "character"), "sheet": e.get("sheet", ""),
                         "voice_sample": e.get("voice_sample", "")}
                     for s, e in series_cfg["subjects"].items()},
        "shots": shots_out,
    }
    r = target.recipe
    if shots_out and ctx.silent:
        asked = ", ".join(f"{k} x{n}" for k, n in sorted(ctx.intents.items()))
        ctx.warnings.append(f"{target.short} makes no sound: {len(shots_out)} shot(s) render "
                            f"silent (asked for {asked}); lay the soundtrack in at the edit")
    if ctx.talking and ctx.silent and ctx.style.silent_dialogue:
        ctx.warnings.append(ctx.style.silent_dialogue.format(
            n=len(ctx.talking), short=target.short, ids=_ids(ctx.talking)))
    for end, why in (r.get("keyframe_required") or {}).items():
        if shots_out:
            ctx.warnings.append(f"{target.short} renders from a first frame: each of these "
                                f"{len(shots_out)} shot(s) is blocked until its "
                                f"{r['keyframe_path'].format(shot='<shot>', end=end)} exists "
                                f"({why.split(': ', 1)[-1]})")
    if ctx.long:
        ctx.warnings.append(f"{len(ctx.long)} shot(s) are longer than {target.short}'s trained "
                            f"{target.template.spec.get('trained_frames')} frames (motion may "
                            f"loop or drift; shot, frames): {_ids(ctx.long, 12)}")
    if not ctx.silent:
        # what a model that makes its own sound renders another way (a cloned
        # voice, a dub: Seedance's generate), said as ltx2's and H3's are; a
        # silent one's already said above
        VC.fallback_warnings(ctx, target)
    for sh in shots_out:
        VC.override_warnings(ctx, sh)
        if len(sh.get("panels") or []) > 4:
            ctx.warnings.append(f"{sh['id']}: {len(sh['panels'])} subjects on one reference "
                                f"image; small panels carry over worse")
    return doc, VC.episode_report(ctx, story, target, shots_out, seqs, ctx.needed, ctx.blocked,
                                  r.get("size_hints"))


def compile_shot(target, shot_ir: ir.Shot, series_cfg: dict, preset, ctx=None,
                 style=None) -> dict:
    """One shot's entry, as compile_episode builds it. `ctx` needs
    {"episode": ir.Episode}, and may give {"absent": [subject ids, "plate"]}."""
    ctx = dict(ctx or {})
    story = ctx.get("episode")
    if story is None:
        raise ValueError("compile_shot needs ctx['episode'], the shot's ir.Episode")
    pass_ = preset if isinstance(preset, str) else preset.name
    doc, _ = compile_episode(target, story, series_cfg, pass_, {shot_ir.id}, ctx.get("absent"),
                             style)
    if not doc["shots"]:
        raise ValueError(f"{shot_ir.id} is not in episode {story.id}")
    return doc["shots"][0]


def compile_without(target, story: ir.Episode, series_cfg: dict, pass_: str,
                    entry: dict, missing: list[dict], style=None) -> dict:
    """`entry` compiled again as if the `missing` refs (ref_slots dicts)
    didn't exist: they leave the reference image (the prose describes every
    subject in words anyway). ValueError when the build is out of date."""
    shot_ir = next((s for s in story.shots() if s.id == entry["id"]), None)
    if shot_ir is None:
        raise ValueError(f"{entry['id']} is not in shots.json")
    if compile_shot(target, shot_ir, series_cfg, pass_, {"episode": story}, style) != entry:
        raise ValueError(f"{entry['id']}: the build is out of date (rebuild the episode)")
    absent = {r["subject"] for r in missing if r.get("subject")}
    if any(r.get("location") for r in missing):
        absent.add(PLATE)
    return compile_shot(target, shot_ir, series_cfg, pass_,
                        {"episode": story, "absent": absent}, style)


def required_refs(target, shot_ir: ir.Shot, series_cfg: dict, ctx=None) -> list[TG.RefRequest]:
    """The refs a shot's reference image is made of, in panel order (VACE;
    [] for a target without one). Keyframes aren't made by the image target:
    they come from continuity or an import."""
    recipe = target.recipe
    ref = recipe.get("reference_image")
    if not ref:
        return []
    ctx = dict(ctx or {})
    book = series_cfg["subjects"]
    out = [subject_request(recipe, s, book[s], f"reference panel {i}")
           for i, s in enumerate(ordered(shot_ir, book), 1)]
    if ref.get("plate"):
        key = shot_ir.plate or (ctx["sequence"].location if ctx.get("sequence") else "")
        loc = series_cfg["locations"].get(key)
        if loc and loc.get("plate"):
            out.append(plate_request(recipe, key, loc, f"reference panel {len(out) + 1}"))
    return out


def ref_slots(target, doc: dict, shot: dict) -> list[dict]:
    """What a render reads: one slot per reference panel (required: a missing
    file blocks the shot unless rendering anyway), then the keyframes. A
    keyframe is optional unless the recipe's `keyframe_required` names it
    (Wan 14B I2V's first frame): then it is required and can't be rendered
    without (`anyway: false`, `why` says what to do)."""
    out = []
    for i, p in enumerate(shot.get("panels") or [], 1):
        r = {"slot": f"reference panel {i}", "kind": "image", "path": p.get("path", "")}
        if p.get("subject"):
            r["subject"] = p["subject"]
        else:
            r["location"] = p.get("location")
        out.append(r)
    hard = target.recipe.get("keyframe_required") or {}
    for end, p in (shot.get("keyframes") or {}).items():
        r = {"slot": f"{end} frame", "kind": "image", "path": p, "role": end}
        if end in hard:
            r.update(anyway=False, why=hard[end])
        else:
            r["optional"] = True
        out.append(r)
    return out


# ---------------------------------------------------------------------------
# the graph
# ---------------------------------------------------------------------------

def one(g: dict, ctype: str, title: str | None = None, what: str = "the") -> str:
    ids = of(g, ctype, title)
    if len(ids) != 1:
        raise ValueError(f"{what} workflow must have one {ctype}"
                         + (f" titled {title!r}" if title else "") + f" (found {len(ids)})")
    return ids[0]





def split_stages(target, g: dict, job) -> int:
    """A two-stage graph (the 14B high/low noise models): the high noise
    sampler runs steps [0, split), the low noise one [split, end). `split`
    is the preset's fraction of the job's steps (target.json
    `binding.stages`: the two samplers' titles), at least one step each.
    Returns the split step."""
    st = (target.spec.get("binding") or {}).get("stages") or {}
    frac = float(job.shot.get("split", job.doc.get("defaults", {}).get("split", 0.5)))
    steps = int(job.steps)
    split = max(1, min(steps - 1, int(round(steps * frac)))) if steps > 1 else 1
    hi = one(g, "KSamplerAdvanced", st["high"]["sampler"], target.id)
    lo = one(g, "KSamplerAdvanced", st["low"]["sampler"], target.id)
    g[hi]["inputs"].update(start_at_step=0, end_at_step=split)
    g[lo]["inputs"].update(start_at_step=split, end_at_step=10000)
    return split


def abs_path(root: str, p: str) -> str:
    return p if os.path.isabs(p) else os.path.join(root, p)


# ---------------------------------------------------------------------------
# keyframes without code (target.json `binding.inputs`)
# ---------------------------------------------------------------------------

def keyframe_inputs(target) -> dict:
    """target.json `binding.inputs`: {role: where that keyframe goes}, the
    declarative form of the graph surgery a target would otherwise write in
    Python. One entry per role the recipe's `keyframes` names:

        "first": {"class_type": "LoadImage", "field": "image",
                  "title": "First frame",            # when the class repeats
                  "disconnect": {"class_type": "Wan22ImageToVideoLatent",
                                 "input": "start_image"}}

    `field` defaults to "image". `disconnect` is what to unwire when the shot
    has no such keyframe (a list, or one entry): the node input is popped, so
    the graph renders from the prompt alone and `prune` drops the loader.
    Without it, every input the loader feeds is popped instead."""
    return dict((target.spec.get("binding") or {}).get("inputs") or {})


def patch_graph(target, g: dict, job, inputs: dict) -> None:
    """Put each staged keyframe into the node `binding.inputs` names, and
    unwire the ones the shot hasn't got. A target that declares no inputs (a
    text-to-video graph) needs nothing here."""
    for role, spec in keyframe_inputs(target).items():
        if not isinstance(spec, dict) or not spec.get("class_type"):
            raise ValueError(f"{target.id}: binding.inputs.{role} needs a class_type")
        node = one(g, spec["class_type"], spec.get("title"), target.id)
        name = (inputs or {}).get(role)
        if name:
            g[node]["inputs"][spec.get("field", "image")] = name
            continue
        drop = spec.get("disconnect")
        drop = [drop] if isinstance(drop, dict) else list(drop or [])
        if drop:
            for d in drop:
                for nid in of(g, d["class_type"], d.get("title")):
                    g[nid]["inputs"].pop(d["input"], None)
        else:
            for nid, inp in consumers(g, node):
                g[nid]["inputs"].pop(inp, None)
