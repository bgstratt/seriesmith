"""
MiniMax H3 FL2VA (first/last frame to video + audio): the story IR compiled
into shotlist entries that jobs patches straight into ComfyUI's MiniMax H3
image-to-video workflow (target.json beside this file). There is no loader
node: every render value is a widget, as with ltx2.

    compile_episode(target, story, series_cfg, pass_, only=None) -> (doc, report)
    compile_shot(target, shot_ir, series_cfg, preset, ctx) -> one entry
    compile_without(target, story, series_cfg, pass_, entry, missing) -> entry
    required_refs(target, shot_ir, series_cfg, ctx) -> []   (nothing to make)
    ref_slots(target, doc, shot) -> the optional keyframes, and the recording
                                    a dub shot anchors
    stage_inputs(target, job, comfy) -> the keyframe alignment in the prompt,
                                    and the dub slice uploaded
    patch_graph(target, graph, job, inputs) -> keyframes, the audio anchor,
                                    or text-to-video

A shotlist entry carries the neutral keys every target's entries have (id,
sequence, subjects, background, size, length, seed, steps, audio_policy,
prompt, duration or audio_in / audio_out) plus `keyframes` {first, last} (the
conventional paths; optional), and for a clone shot `voice_refs` and `lines`
(held_audio.clone_entry: who speaks, with which sample, and what each says).
`background` is the plate
the script names; FL2VA never reads it (the location is described in words).

Audio: generate is H3's own soundtrack. dub / dub_keep_foley anchor the
shot's slice of the recording at frame 0 with MiniMaxH3AddGuide (the model
packs it as conditioning audio on the target's time axis, as it does a
keyframe's latent); the prompt says the dialogue is the recording's, and dub
adds nothing else while dub_keep_foley keeps the soundscape. H3 FL2VA has no
voice-reference slot, so a clone shot's lines are made first, in the same
graph, by LTX-2.5's audio-only model continuing each speaker's held sample
(held_audio.make_lines, as ltx2's clone makes them), and anchored as a
recording is; its prompt is dub_keep_foley's (the voice is given, H3 lays its
sound under it), and the take keeps H3's mix with the lines beside it.

Stdlib only.
"""
from __future__ import annotations

import os
import re
import uuid

from seriesmith import targets as TG
from seriesmith.core import ir
from seriesmith.targets import held_audio as HA
from seriesmith.targets import video_compile as VC
from seriesmith.targets.video_compile import shot_duration as _duration

from .prompt import build_multishot_prompt, build_prompt, with_keyframes
from seriesmith.core import paths as P
from seriesmith.targets.graph import abs_path as _abs, consumers as _consumers, of as _of, new_id as _new_id  # noqa: F401

ID = "minimax_h3_fl2va"
TARGET = TG.load_target(ID, "video")
RECIPE = TARGET.recipe
KEYFRAMES = tuple(RECIPE.get("keyframes") or ())
ANCHOR = dict(RECIPE.get("audio_anchor") or {})
DUB = ("dub", "dub_keep_foley")


def keyframe_path(shot_id: str, end: str) -> str:
    """Where a shot's keyframe lives (refs' `shot:<id>:<end>` ref)."""
    return RECIPE["keyframe_path"].format(shot=P.safe_id(shot_id),
                                          end=end)


class Ctx:
    """One pass of one episode: the preset, the legal size, and the report.
    `absent` is what a render-anyway recompile leaves out ("audio")."""

    def __init__(self, target, series_cfg: dict, pass_: str, absent=()):
        self.target, self.series_cfg, self.pass_ = target, series_cfg, pass_
        self.preset = target.preset(pass_, series_cfg)
        self.fps = target.template.fps_for(series_cfg)
        self.warnings: list[str] = []
        self.width, self.height = int(self.preset.width), int(self.preset.height)
        target.template.validate_size(self.width, self.height)
        self.total_req = self.total_raw = 0
        self.fallbacks: dict[str, list[str]] = {}
        self.long: list[str] = []
        self.profiles = TG.series_profiles(series_cfg)
        self.recording = series_cfg.get("audio", {}).get("track", "")
        self.absent = set(absent or ())


def _compile(ctx: Ctx, sq: ir.Sequence, shot: ir.Shot, ep_id: str) -> dict:
    series_cfg, template = ctx.series_cfg, ctx.target.template
    loc_key, pace = VC.check_shot(series_cfg, sq, shot)
    dur, windowed = _duration(ctx, shot, pace)
    req, raw = VC.snap_frames(ctx, shot, dur)
    VC.crammed(ctx, shot, pace, raw)
    trained = int(template.spec.get("trained_frames") or 0)
    if trained and raw > trained:
        ctx.long.append(shot.id)
    VC.count_frames(ctx, req, raw)
    intent, policy, note = VC.shot_audio(ctx, shot)
    if policy in DUB:
        if "audio" in ctx.absent:
            # render anyway without the recording: H3 voices the lines itself
            policy, note = "generate", (f"audio {intent} renders as generate: the "
                                        f"recording is missing")
        elif not windowed:
            raise ValueError(f"shot {shot.id}: policy {policy} needs an `audio: in-out` "
                             f"window on the recorded track (`seriesmith align` writes these).")
        elif not ctx.recording:
            raise ValueError(f"shot {shot.id}: uses an `audio:` window but series.json has "
                             f"no audio.track set.")

    layers = VC.shot_layers(series_cfg, sq, shot, ctx.profiles)
    entry = VC.entry_head(ctx, sq, shot, ep_id, loc_key, raw, layers, policy)
    voiced = HA.clone_entry(shot, series_cfg["subjects"]) if policy == "clone" else {}
    # a clone is dubbed with the lines LTX makes: the prompt says the voice is
    # given (a clone shot with no lines is prompted as generate)
    entry["prompt"] = build_prompt(shot, sq, series_cfg,
                                   "dub_keep_foley" if voiced.get("lines") else
                                   "generate" if policy == "clone" else policy)
    entry["keyframes"] = {end: keyframe_path(shot.id, end)
                          for end in TG.keyframe_ends(RECIPE, shot, sq)}
    entry.update(voiced)
    return VC.entry_tail(ctx, sq, shot, entry, layers, intent, note, dur, windowed, pace)


def _compile_group(ctx: Ctx, sq: ir.Sequence, group: list, ep_id: str) -> dict:
    """One entry for a `continuous: multishot` group (docs/MULTISHOT.md): each
    shot compiles as itself (its checks), then they are joined into one
    generation: the first shot's settings and first keyframe, the last shot's
    last keyframe, one length on the grid, the timed `[Shot N]` prompt, and
    `multishot` (each shot and the frame it starts on)."""
    before = ctx.total_raw
    entries = [_compile(ctx, sq, s, ep_id) for s in group]
    ids = f"{group[0].id}-{group[-1].id}"
    for s, e in zip(group, entries):
        if e["audio_policy"] != "generate":
            raise ValueError(f"shots {ids}: a multishot group generates its sound, and {s.id} is "
                             f"{e['audio_policy']}: a dubbed voice is one shot at a time for now. "
                             f"Give it `policy: generate`, or break the group with "
                             f"`continuous: none`")
    fps = ctx.fps
    frames = [max(1, round((e["duration"] if "duration" in e else e["audio_out"] - e["audio_in"])
                           * fps)) for e in entries]
    want = sum(frames)
    raw = ctx.target.template.snap(want)
    frames[-1] += raw - want
    starts, at = [], 0
    for f in frames:
        starts.append(at)
        at += f
    ctx.total_raw = before + raw
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
        "multishot": [{"id": s.id, "start": st, "frames": f, "size": s.size}
                      for s, st, f in zip(group, starts, frames)],
        "prompt": build_multishot_prompt(group, sq, ctx.series_cfg, [st / fps for st in starts]),
    })
    return entry


def compile_episode(target, story: ir.Episode, series_cfg: dict, pass_: str,
                    only: set[str] | None = None, absent=()) -> tuple[dict, dict]:
    ctx = Ctx(target, series_cfg, pass_, absent)
    shots_out, seqs = [], 0
    for sq in story.sequences:
        mine = [s for s in sq.shots if only is None or s.id in only]
        if mine:
            seqs += 1
        groups = {g[0].id: g for g in sq.multishot_groups()}
        grouped = {s.id for g in groups.values() for s in g[1:]}
        for s in mine:
            if s.id in groups:
                shots_out.append(_compile_group(ctx, sq, groups[s.id], story.id))
            elif s.id not in grouped:
                shots_out.append(_compile(ctx, sq, s, story.id))
    p = ctx.preset
    extra = {k: v for k, v in p.extra.items() if not k.startswith("_")}
    doc = {
        "episode": story.id,
        "title": story.title,
        "target": target.id,
        "defaults": {"width": ctx.width, "height": ctx.height, "fps": ctx.fps,
                     "steps": p.steps, "model": p.model, "lora": p.lora,
                     "audio_policy": "generate", "master_track": ctx.recording, **extra},
        "subjects": {s: {"kind": e.get("kind", "character"), "sheet": e.get("sheet", ""),
                         "voice_sample": e.get("voice_sample", "")}
                     for s, e in series_cfg["subjects"].items()},
        "shots": shots_out,
    }
    for intent, ids in sorted(ctx.fallbacks.items()):
        ctx.warnings.append(f"{len(ids)} shot(s) ask for audio {intent}, which {target.short} "
                            f"can't render ({(target.recipe.get('policy_fallback') or {}).get('why', '')}): "
                            f"they render with generate: {', '.join(ids[:8])}"
                            + (" …" if len(ids) > 8 else ""))
    if ctx.long:
        ctx.warnings.append(f"{len(ctx.long)} shot(s) are longer than {target.short}'s trained "
                            f"range ({target.template.spec.get('trained_frames')} frames): "
                            f"{', '.join(ctx.long[:8])}" + (" …" if len(ctx.long) > 8 else ""))
    for sh in shots_out:
        for k in ("model", "lora"):
            if k in sh:
                ctx.warnings.append(f"{sh['id']} overrides {k}: {sh[k]}")
    m = re.search(r"(\d+)step", p.lora or "")
    if m and int(m.group(1)) != int(p.steps):
        ctx.warnings.append(f"{pass_} steps is {p.steps} but the LoRA {p.lora} is distilled "
                            f"for {m.group(1)} steps")
    fps = ctx.fps
    report = {
        "episode": story.id, "title": story.title,
        "mode": "proxy" if pass_ == "proxy" else "final",
        "resolution": f"{ctx.width}x{ctx.height}", "steps": p.steps,
        "model": p.model, "lora": p.lora or "none", "fps": fps,
        "shots": len(shots_out), "sequences": seqs,
        "target_s": ctx.total_req / fps, "delivered_s": ctx.total_raw / fps,
        "pad_frames": ctx.total_raw - ctx.total_req,
        "policies": {pol: sum(1 for s in shots_out if s["audio_policy"] == pol)
                     for pol in sorted({s["audio_policy"] for s in shots_out})},
        "needed": {}, "blocked_shots": {}, "warnings": ctx.warnings,
        "target": target.id, "size_hints": dict(RECIPE.get("size_hints") or {}),
    }
    return doc, report


def compile_shot(target, shot_ir: ir.Shot, series_cfg: dict, preset, ctx=None) -> dict:
    """One shot's entry, as compile_episode builds it. `ctx` needs
    {"episode": ir.Episode}; {"absent": ["audio"]} compiles it without the
    recording."""
    ctx = dict(ctx or {})
    story = ctx.get("episode")
    if story is None:
        raise ValueError("compile_shot needs ctx['episode'], the shot's ir.Episode")
    pass_ = preset if isinstance(preset, str) else preset.name
    doc, _ = compile_episode(target, story, series_cfg, pass_, only={shot_ir.id},
                             absent=ctx.get("absent") or ())
    if not doc["shots"]:
        raise ValueError(f"{shot_ir.id} is not in episode {story.id}")
    return doc["shots"][0]


def compile_without(target, story: ir.Episode, series_cfg: dict, pass_: str,
                    entry: dict, missing: list[dict]) -> dict:
    """Render anyway: the only ref a shot needs is a dub shot's recording;
    without it the shot is compiled as generate (H3 voices the lines from
    the prompt). ValueError when the build is out of date."""
    shot_ir = next((s for s in story.shots() if s.id == entry["id"]), None)
    if shot_ir is None:
        raise ValueError(f"{entry['id']} is not in shots.json")
    if compile_shot(target, shot_ir, series_cfg, pass_, {"episode": story}) != entry:
        raise ValueError(f"{entry['id']}: the build is out of date (rebuild the episode)")
    absent = {"audio"} if any(r.get("kind") == "audio" for r in missing) else set()
    return compile_shot(target, shot_ir, series_cfg, pass_,
                        {"episode": story, "absent": absent})


def required_refs(target, shot_ir: ir.Shot, series_cfg: dict, ctx=None) -> list:
    """Nothing to make: subjects and the location are written in words, and
    keyframes are optional (a shot without them is text-to-video). A dub
    shot's recording is the series config's track, not a ref request."""
    return []


def _recording(doc: dict, shot: dict) -> str:
    return shot.get("audio_file") or doc.get("defaults", {}).get("master_track", "")


def ref_slots(target, doc: dict, shot: dict) -> list[dict]:
    """The keyframes a render reads when they exist (`optional`: missing ones
    never block a render), and for a dub shot the recording it anchors. The
    recording has no `role`: jobs.stage_inputs doesn't upload the whole
    file; this target's stage_inputs cuts and uploads the shot's slice."""
    out = [{"slot": f"{end} frame", "kind": "image", "path": p, "role": end,
            "optional": True}
           for end, p in (shot.get("keyframes") or {}).items()]
    if shot.get("audio_policy") in DUB:
        out.append({"slot": ANCHOR.get("slot", "dialogue recording"), "kind": "audio",
                    "path": _recording(doc, shot)})
    # a clone shot: each speaker's voice sample, which its lines continue
    return out + (HA.audio_slots(doc, shot) if shot.get("audio_policy") == "clone" else [])


# ---------------------------------------------------------------------------
# queue time: the keyframes in the prompt, the dub slice
# ---------------------------------------------------------------------------

def present_keyframes(job) -> tuple[str, ...]:
    """The keyframe roles on disk for this job, in first/last order."""
    have = set()
    for r in ref_slots(None, job.doc, job.shot):
        if r.get("role") in KEYFRAMES and r.get("path") \
                and os.path.isfile(_abs(job.root, r["path"])):
            have.add(r["role"])
    return tuple(e for e in KEYFRAMES if e in have)


def stage_inputs(target, job, comfy=None) -> dict:
    """Before the take is reserved: the prompt gets the H3 alignment line for
    the keyframes this render has (prompt.with_keyframes; none: the text-to-
    video prompt), and a dub shot's slice of the recording is cut, uploaded
    to ComfyUI's input folder and kept in the take ({"audio": its name}).
    A dry run (`comfy` None) cuts nothing: the name is a stand-in."""
    from seriesmith import jobs as J
    from seriesmith import takes as T
    from . import audio as A
    roles = present_keyframes(job)
    job.prompt = with_keyframes(J._prompt_text(job.prompt), roles, job.frames, job.fps)
    out = {}
    shot = job.recompiled or job.shot
    if job.lines_name:
        # dubbed to another take's voice (jobs.stage_lines): anchored as a recording
        return out
    if shot.get("audio_policy") == "clone":
        _voice_files_installed(job)
        return HA.stage_clone(target, job, comfy)
    if shot.get("audio_policy") not in DUB:
        return out
    rec = _recording(job.doc, shot)
    src = _abs(job.root, rec) if rec else ""
    if not src or not os.path.isfile(src):
        # only reached rendering anyway with the build's own prompt (the
        # "blank" fallback): no anchor, H3 voices the lines itself
        job.notes.append(f"no dialogue anchor: the recording {rec or '(none named)'} "
                         f"is missing")
        return out
    start = end = None
    if not shot.get("audio_file") and "audio_in" in shot:
        start, end = float(shot["audio_in"]), float(shot["audio_out"])
    if comfy is None:
        return {"audio": f"{J.INPUT_SUBFOLDER}/dry_run_{T.safe_id(job.id)}_dub.wav"}
    d = T.shot_dir(job.root, job.pass_, job.id, job.folder)
    os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, f".tmp_dub_{uuid.uuid4().hex}.wav")
    try:
        A.cut(src, tmp, start, end)
        name = J.input_name(tmp)
        comfy.upload_input(tmp, name)
    except BaseException:
        if os.path.isfile(tmp):
            os.remove(tmp)
        raise
    job.staged.append({"tmp": tmp, "suffix": ANCHOR.get("take_suffix", "_dub.wav"),
                       "slot": "dialogue slice", "kind": "audio", "role": "audio"})
    out["audio"] = name
    return out


VOICE = ("voice_model", "voice_text_encoder", "voice_audio_vae")

# a take's voice can be dubbed (jobs.lines_from): anchored as a recording is
TAKES_LINES = True


def _voice_files_installed(job) -> None:
    """A clone shot's lines need LTX-2.5's audio-only files (optional for
    every other shot): ValueError naming what to download when resolve_models
    found one missing on this ComfyUI."""
    off = [p for p in VOICE if (job.resolved or {}).get(p, {}).get("how") == "off"]
    if off:
        missing = [TG.missing_message(TG._missing(TARGET, p, TARGET.models[p],
                                                  job.resolved[p]["want"], "optional"))
                   for p in off]
        raise ValueError(f"{job.id}: clone on {TARGET.short} makes the lines with LTX-2.5 "
                         f"audio-only first, and this ComfyUI lacks its files: "
                         + "; ".join(missing))


def _voice_value(job, param: str) -> str:
    """The LTX voice file a clone shot loads: as resolved, else the preset's."""
    from seriesmith import jobs as J
    return J.model_values(job).get(param) or ""


# ---------------------------------------------------------------------------
# the graph
# ---------------------------------------------------------------------------

def _one(g: dict, ctype: str) -> str:
    ids = _of(g, ctype)
    if len(ids) != 1:
        raise ValueError(f"the {ID} workflow must have one {ctype} (found {len(ids)})")
    return ids[0]


def _load_image(g: dict, name: str, title: str, reuse: str | None = None) -> str:
    if reuse:
        g[reuse]["inputs"]["image"] = name
        return reuse
    nid = _new_id(g, "h3_keyframe_")
    g[nid] = {"class_type": "LoadImage", "inputs": {"image": name},
              "_meta": {"title": f"{title} (h3pipe)"}}
    return nid


def _clone_lines(g: dict, job, inputs: dict) -> list | None:
    """A clone shot's lines, made in `g` before H3 runs: LTX-2.5's own loaders
    (the voice_* files) and held_audio.make_lines, each line continuing its
    speaker's held sample (inputs["voices"], stage_clone). The joined lines go
    to the saver too (`lines`: the take's _lines.wav). The link of the joined
    sound, or None for a shot that isn't a clone."""
    entry = (job.recompiled or job.shot) if job is not None else {}
    if entry.get("audio_policy") != "clone" or not entry.get("lines") or inputs.get("audio"):
        return None

    def loader(prefix: str, ctype: str, title: str, **ins) -> str:
        k = _new_id(g, prefix)
        g[k] = {"class_type": ctype, "inputs": ins, "_meta": {"title": f"{title} (seriesmith)"}}
        return k

    unet = loader("h3_voice_unet_", "UNETLoader", "LTX-2.5 transformer, for the lines",
                  unet_name=_voice_value(job, "voice_model"), weight_dtype="default")
    clip = loader("h3_voice_clip_", "CLIPLoader", "LTX-2.5 text encoder, for the lines",
                  clip_name=_voice_value(job, "voice_text_encoder"), type="ltxv", device="default")
    vae = loader("h3_voice_vae_", "VAELoader", "LTX-2.5 audio VAE, for the lines",
                 vae_name=_voice_value(job, "voice_audio_vae"))
    sound = HA.make_lines(g, job, inputs, unet, [clip, 0], [vae, 0])
    for k, v in g.items():
        if v.get("class_type") in ("H3SaveShot", "SeriesmithSaveTake"):
            v["inputs"]["lines"] = list(sound)
    return sound


def patch_graph(target, g: dict, job, inputs: dict) -> None:
    """Keyframes: `inputs["first"]` / `inputs["last"]` (names LoadImage reads)
    go straight into MiniMaxH3ImageToVideo's first_frame / last_frame; an end
    without one is disconnected (neither: text-to-video). `inputs["audio"]`
    (a name LoadAudio reads) is anchored at frame 0 by a MiniMaxH3AddGuide
    between the node's conditioning and the guider; a clone shot's lines,
    made in the graph (_clone_lines), are anchored the same way."""
    i2v = _one(g, "MiniMaxH3ImageToVideo")
    ii = g[i2v]["inputs"]
    # the template's LoadImage (the first frame), reused for it
    loads = [k for k in _of(g, "LoadImage")]
    for end in ("first", "last"):
        ii.pop(f"{end}_frame", None)
    if inputs.get("first"):
        nid = _load_image(g, inputs["first"], "first frame", loads[0] if len(loads) == 1 else None)
        ii["first_frame"] = [nid, 0]
    if inputs.get("last"):
        nid = _load_image(g, inputs["last"], "last frame")
        ii["last_frame"] = [nid, 0]
    lines = _clone_lines(g, job, inputs)
    if inputs.get("audio") or lines:
        dec = _one(g, "VAEDecodeAudio")
        audio_vae = g[dec]["inputs"]["vae"]
        if lines:
            sound = lines
        else:
            load = _new_id(g, "h3_dub_load_")
            g[load] = {"class_type": "LoadAudio", "inputs": {"audio": inputs["audio"]},
                       "_meta": {"title": "dialogue slice (h3pipe)"}}
            sound = [load, 0]
        guide = _new_id(g, "h3_dub_guide_")
        consumers = _consumers(g, i2v, 0)
        g[guide] = {"class_type": "MiniMaxH3AddGuide",
                    "inputs": {"positive": [i2v, 0], "latent": [i2v, 1],
                               "audio_vae": list(audio_vae), "audio": sound,
                               "frame_idx": int(ANCHOR.get("frame_idx", 0))},
                    "_meta": {"title": "dialogue anchor at frame 0 (h3pipe)"}}
        for k, name in consumers:
            g[k]["inputs"][name] = [guide, 0]
