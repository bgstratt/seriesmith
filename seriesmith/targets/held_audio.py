"""
A sound held in an LTX graph: given to the sampler as it is, with the model
making only what's around it. LTX samples one latent of picture and sound
together (LTXVConcatAVLatent), and a noise mask of 0 on part of it tells the
sampler to leave that part alone, so

    LoadAudio -> LTXVAudioVAEEncode -> SetLatentNoiseMask (SolidMask 0)

swapped into the audio of every latent a sampler samples (a second
LTXVConcatAVLatent around the stage's own: ComfyUI's swaps the audio of an
AV latent it is given, zero-padding or cutting it to the clip's length, the
padding left for the model) holds that sound through every stage. Three uses:

  * a voice sample held at the head of an audio-only clip, which LTX then
    continues in the same voice (targets/audio/ltx2_voice);
  * a shot's window of the recorded dialogue held as its whole soundtrack, so
    the picture is made to it: `dub` on the LTX video targets;
  * `clone` on ltx2: each line made in the shot's own graph by the audio-only
    model, continuing its speaker's held sample, the lines joined and held as
    the shot's soundtrack, so the voices are made with the picture, in one job.

Measured live 2026-10-28 (docs/PLAN.md, "Voices across models"): the held
sound came back unchanged through both stages of the two-stage graph
(envelope correlation 0.97-0.99), and mouths moved with it.

Stdlib only.
"""
from __future__ import annotations

from seriesmith.targets.graph import consumers as _consumers, new_id as _new_id, of as _of

DUB = ("dub", "dub_keep_foley")


def _src(g: dict, nid: str, name: str):
    v = g[nid]["inputs"].get(name)
    return v[0] if isinstance(v, list) and len(v) == 2 else None


def samplers(g: dict) -> list[str]:
    """Every sampler (SamplerCustomAdvanced, KSampler) whose latent is an
    LTXVConcatAVLatent: the stages a held sound has to reach."""
    return [k for k, v in g.items()
            if "latent_image" in (v.get("inputs") or {})
            and (_src(g, k, "latent_image") or "") in g
            and g[_src(g, k, "latent_image")]["class_type"] == "LTXVConcatAVLatent"]


def audio_vae(g: dict) -> list:
    """The link to the audio VAE the graph decodes its sound with."""
    dec = _of(g, "LTXVAudioVAEDecode")
    if len(dec) != 1:
        raise ValueError(f"an LTX graph holding a sound must have one LTXVAudioVAEDecode "
                         f"(found {len(dec)})")
    return list(g[dec[0]]["inputs"]["audio_vae"])


def hold(g: dict, name: str, what: str, stages: list[str] | None = None,
         vae: list | None = None) -> list[str]:
    """`name` (a file ComfyUI's LoadAudio reads) held through `stages` (every
    stage of `g` when None); `what` says what it is, in the new nodes'
    titles; `vae` the audio VAE link (the decode's when None). Returns the
    samplers it reaches."""
    return swap_in(g, held_file(g, name, what, vae), what, stages)


def hold_link(g: dict, audio: list, what: str, stages: list[str] | None = None,
              vae: list | None = None) -> list[str]:
    """The sound `audio` (a link to an AUDIO output) held through `stages`
    (every stage of `g` when None)."""
    return swap_in(g, held_latent(g, audio, what, vae), what, stages)


def held_file(g: dict, name: str, what: str, vae: list | None = None) -> str:
    """held_latent of a file ComfyUI's LoadAudio reads."""
    load = _new_id(g, "h3_held_load")
    g[load] = {"class_type": "LoadAudio", "inputs": {"audio": name},
               "_meta": {"title": f"{what} (held)"}}
    return held_latent(g, [load, 0], what, vae)


def held_latent(g: dict, audio: list, what: str, vae: list | None = None) -> str:
    """The node holding `audio` (an AUDIO link): encoded by the audio VAE
    (`vae`, else the decode's), with a noise mask of 0; swap_in puts it into
    as many samplers as want it."""
    enc = _new_id(g, "h3_held_encode")
    g[enc] = {"class_type": "LTXVAudioVAEEncode",
              "inputs": {"audio": list(audio), "audio_vae": list(vae or audio_vae(g))},
              "_meta": {"title": f"{what} encoded"}}
    mask = _new_id(g, "h3_held_mask")
    g[mask] = {"class_type": "SolidMask", "inputs": {"value": 0.0, "width": 32, "height": 32},
               "_meta": {"title": f"{what}: mask 0, left as it is"}}
    held = _new_id(g, "h3_held")
    g[held] = {"class_type": "SetLatentNoiseMask",
               "inputs": {"samples": [enc, 0], "mask": [mask, 0]},
               "_meta": {"title": f"{what} held"}}
    return held


def swap_in(g: dict, held: str, what: str, stages: list[str] | None = None) -> list[str]:
    """`held` (held_latent) as the sound of every latent `stages` sample (every
    stage of `g` when None). ValueError when there are none."""
    stages = samplers(g) if stages is None else list(stages)
    if not stages:
        raise ValueError("the graph has no sampler sampling an LTXVConcatAVLatent to hold "
                         "a sound in")
    for n, s in enumerate(stages, 1):
        swap = _new_id(g, f"h3_held_swap{n}_")
        g[swap] = {"class_type": "LTXVConcatAVLatent",
                   "inputs": {"video_latent": [_src(g, s, "latent_image"), 0],
                              "audio_latent": [held, 0]},
                   "_meta": {"title": f"{what} as the sound, stage {n}"}}
        g[s]["inputs"]["latent_image"] = [swap, 0]
    return stages


def trim_head(g: dict, start: float, seconds: float, what: str) -> str:
    """The decoded sound (the graph's one LTXVAudioVAEDecode) with its first
    `start` seconds taken off (and cut to `seconds`), for everything that
    read it."""
    dec = _of(g, "LTXVAudioVAEDecode")[0]
    readers = _consumers(g, dec, 0)
    trim = _new_id(g, "h3_held_trim")
    g[trim] = {"class_type": "TrimAudioDuration",
               "inputs": {"audio": [dec, 0], "start_index": round(start, 3),
                          "duration": round(seconds, 3)},
               "_meta": {"title": f"{what} trimmed off"}}
    for c, field in readers:
        g[c]["inputs"][field] = [trim, 0]
    return trim


# -- what a shot hears: a clone shot's voice samples, a dub shot's recording ------

def audio_slots(doc: dict, shot: dict) -> list[dict]:
    """The sound files a shot needs, as ref slots: a clone shot's voice
    samples, one per speaker (`voice_refs`), or a dub shot's recording. A
    missing one blocks the render, or renders anyway without it."""
    if shot.get("audio_policy") == "clone":
        return [{"slot": f"voice {i}", "kind": "audio", "subject": r["subject"],
                 "path": r.get("sample", "")}
                for i, r in enumerate(shot.get("voice_refs") or [], 1)]
    return recording_slot(doc, shot)


def recording_slot(doc: dict, shot: dict) -> list[dict]:
    """A dub shot's recorded track as a ref slot (as H3 declares it): a
    missing recording blocks the render, or renders anyway without it. No
    `role`: jobs.stage_inputs doesn't upload the whole track; stage_dub
    uploads the shot's window of it."""
    if shot.get("audio_policy") not in DUB:
        return []
    return [{"slot": "recording", "kind": "audio",
             "path": shot.get("audio_file") or (doc.get("defaults") or {}).get("master_track", "")}]


def stage_dub(target, job, comfy=None) -> dict:
    """{"audio": name}: the shot's window of the recorded track cut
    (audiocut.window) and uploaded, for patch_graph to hold as the whole
    soundtrack; {} for a shot that isn't a dub, or one rendering anyway
    without its recording (nothing is held, and the take says so; its mp4 is
    mute, as every dub's is, as H3's is then). Without `comfy` (a dry run)
    only the name is worked out."""
    import os

    from seriesmith import audiocut as AC
    from seriesmith import jobs as J
    entry = job.recompiled or job.shot
    policy = entry.get("audio_policy")
    if policy not in DUB or getattr(job, "lines_name", ""):
        # dubbed to another take's voice instead (jobs.stage_lines staged it)
        return {}
    (slot,) = recording_slot(job.doc, entry)
    track = J._abs(job.root, slot["path"]) if slot["path"] else ""
    if not track or not os.path.isfile(track):
        job.notes.append(f"{policy} without its recording ({slot['path'] or 'audio.track unset'}): "
                         f"nothing is held, so the lips follow {target.short}'s own sound, "
                         f"not the recording")
        return {}
    if "audio_in" in entry and not entry.get("audio_file"):
        a_in, a_out = float(entry["audio_in"]), float(entry["audio_out"])
        clip = AC.window(track, a_in, a_out) if comfy is not None else track
        span = f"{a_in:.2f}-{a_out:.2f}s of "
    else:
        clip, span = track, ""
    name = J.input_name(clip)
    if comfy is not None:
        comfy.upload_input(clip, name)
    job.notes.append(f"{policy}: {span}{os.path.basename(track)} held as the soundtrack, the "
                     f"picture made to it")
    if policy == "dub_keep_foley":
        job.notes.append(f"{target.short} keeps the recording as the whole soundtrack: it adds "
                         f"no sound under it, so the foley bed is near silent")
    return {"audio": name}


def patch_dub(g: dict, inputs: dict) -> None:
    """The staged window held through every stage (stage_dub)."""
    if inputs.get("audio"):
        hold(g, inputs["audio"], "the recording's window")


# -- clone: the lines made with the picture -----------------------------------------

def clone_entry(shot, book: dict) -> dict:
    """What a clone shot's entry carries for its voices to be made in its own
    graph: `voice_refs` (each speaker, in the order they first speak, with
    the sample the voice continues) and `lines` (who says what, in order;
    voiceover and off screen too: they are heard)."""
    lines = [{"who": d.speaker, "line": d.line} for d in shot.dialogue if d.speaker in book]
    who = list(dict.fromkeys(x["who"] for x in lines))
    return {"voice_refs": [{"subject": v, "sample": book[v].get("voice_sample", "")}
                           for v in who],
            "lines": lines}


def stage_clone(target, job, comfy=None) -> dict:
    """{"voices": {subject: {"audio": name, "seconds": s}}}: each speaker's
    sample head cut between words (audiocut.voice_clip) and uploaded, for
    patch_clone to continue; {} for a shot that isn't a clone. A speaker
    rendering anyway without a sample is spoken in a voice made from the
    wording, and the take says so. Without `comfy` (a dry run) only the
    names are worked out."""
    import os

    from seriesmith import audiocut as AC
    from seriesmith import jobs as J
    entry = job.recompiled or job.shot
    if entry.get("audio_policy") != "clone" or getattr(job, "lines_name", ""):
        return {}
    voices = {}
    for r in entry.get("voice_refs") or []:
        path = J._abs(job.root, r["sample"]) if r.get("sample") else ""
        if not path or not os.path.isfile(path):
            job.notes.append(f"clone: {r['subject']} has no voice sample "
                             f"({r.get('sample') or 'none named'}): the voice is made from "
                             f"the wording")
            continue
        clip, secs = AC.voice_clip(path) if comfy is not None else (path, AC.CLIP_MAX)
        name = J.input_name(clip)
        if comfy is not None:
            comfy.upload_input(clip, name)
        voices[r["subject"]] = {"audio": name, "seconds": secs}
    job.notes.append(f"clone: {len(entry.get('lines') or [])} line(s) made in the shot's own "
                     f"graph, in {len(voices)} held voice(s), the picture made to them")
    return {"voices": voices}


def _one(g: dict, ctype: str) -> str:
    found = _of(g, ctype)
    if len(found) != 1:
        raise ValueError(f"a clone shot's graph must have one {ctype} (found {len(found)})")
    return found[0]


def line_seconds(line: str, pace: str = "normal") -> float:
    """How long a line takes at `pace` (core.speech), with air after it."""
    from seriesmith.core import speech as SP
    return SP.syllables(line) / SP.SPEECH_RATE.get(pace, SP.SPEECH_RATE["normal"]) + SP.TAIL_AIR


def patch_clone(target, g: dict, job, inputs: dict) -> None:
    """A clone shot's lines made in its own graph, then held as its
    soundtrack through every video stage. Each line: the transformer the
    shot loads, as LTX's audio-only model, says it in the voice its brief
    describes (targets/audio/common.py, as a voice ref's) continuing its
    speaker's held sample (inputs["voices"], stage_clone), sampled as
    ltx2_voice samples (its workflow's scheduler and sampler, its preset's
    steps and audio cfg, the `base` ones on the dev transformer), the sample
    trimmed off. The lines are joined with the beats core.speech gives a
    shot (air before the first, a pause at each change of speaker), and that
    is what the picture is made to. Nothing for a shot that isn't a clone."""
    entry = (job.recompiled or job.shot) if job is not None else {}
    if entry.get("audio_policy") != "clone" or not entry.get("lines") or (inputs or {}).get("audio"):
        # nothing to make: not a clone, or a voice given to dub (patch_dub holds it)
        return
    stages = samplers(g)                       # the video's, before the lines add theirs
    vae = audio_vae(g)
    sound = make_lines(g, job, inputs, _one(g, "UNETLoader"),
                       list(g[_of(g, "CLIPTextEncode")[0]]["inputs"]["clip"]), vae)
    hold_link(g, sound, "the shot's lines", stages, vae)


def make_lines(g: dict, job, inputs: dict, unet: str, clip: list, vae) -> list:
    """A clone shot's lines, made in `g` and joined (patch_clone's), as the
    link of the joined sound. `unet` is the LTX transformer's loader (used as
    the audio-only model), `clip` the LTX text encoder's link, `vae` the LTX
    audio VAE's: the shot's own in an LTX graph; loaders of their own in
    another model's graph (H3 FL2VA dubs the lines it is given)."""
    import math

    from seriesmith import jobs as J
    from seriesmith import targets as TG
    from seriesmith.core import speech as SP
    from seriesmith.targets.audio import common as AC

    entry = job.recompiled or job.shot
    voices = (inputs or {}).get("voices") or {}
    cfg = J.series_config(job.root) or {}
    book = cfg.get("subjects") or {}
    pace = (cfg.get("speech") or {}).get("pace", "normal")
    fps = float(job.fps or 24.0)
    voice = TG.load_target("ltx2_voice", "audio")
    base = J.load_graph(voice.binding.workflow)
    sch_in = dict(base[_one(base, "LTXVScheduler")]["inputs"])
    preset = voice.presets["final"]
    sampler_name = (preset.extra.get("sampler")
                    or base[_one(base, "KSamplerSelect")]["inputs"]["sampler_name"])
    steps, audio_cfg = preset.steps, preset.extra.get("cfg", 1.0)
    if "dev" in str(g[unet]["inputs"].get("unet_name", "")).lower() and preset.base:
        steps = preset.base.get("steps", steps)
        audio_cfg = preset.base.get("cfg", audio_cfg)
    grid = (voice.spec.get("template") or {}).get("frames") or {}
    step, first = int(grid.get("step") or 8), int(grid.get("base") or 1)

    def node(prefix: str, ctype: str, title: str, **ins) -> str:
        k = _new_id(g, prefix)
        g[k] = {"class_type": ctype, "inputs": ins, "_meta": {"title": title}}
        return k

    model = node("h3_clone_model", "LTXVAudioOnlyModel", "the shot's transformer, audio only",
                 model=[unet, 0])
    neg = node("h3_clone_neg", "CLIPTextEncode", "voices: negative", clip=clip,
               text=preset.extra.get("negative") or AC.NEGATIVE)
    empty_v = node("h3_clone_video", "LTXVAudioOnlyEmptyVideoLatent", "voices: no picture")
    pick = node("h3_clone_sampler", "KSamplerSelect", "voices: sampler", sampler_name=sampler_name)
    sch = node("h3_clone_sched", "LTXVScheduler", f"voices: {steps} steps",
               **dict(sch_in, steps=int(steps)))
    sound = node("h3_clone_air", "EmptyAudio", "air before the first line",
                 duration=SP.HEAD_AIR, sample_rate=48000, channels=2)
    kept: dict[str, str] = {}                   # each speaker's sample, held once
    prev = None
    for i, ln in enumerate(entry["lines"], 1):
        who, e = ln["who"], book.get(ln["who"]) or {}
        name = e.get("name") or ln["who"]
        held = voices.get(who)
        head = float(held["seconds"]) if held else 0.0
        secs = line_seconds(ln["line"], pace)
        frames = first + step * math.ceil(max((head + secs) * fps - first, 0) / step)
        pos = node(f"h3_clone_pos{i}_", "CLIPTextEncode", f"line {i}: {name}", clip=clip,
                   text=AC.voice_prompt(name, e.get("voice", ""), e.get("design", ""), ln["line"]))
        cond = node(f"h3_clone_cond{i}_", "LTXVConditioning", f"line {i}: conditioning",
                    positive=[pos, 0], negative=[neg, 0], frame_rate=fps)
        lat = node(f"h3_clone_audio{i}_", "LTXVEmptyLatentAudio", f"line {i}: {frames} frames",
                   frames_number=frames, frame_rate=fps, batch_size=1, audio_vae=vae)
        av = node(f"h3_clone_av{i}_", "LTXVConcatAVLatent", f"line {i}: the clip",
                  video_latent=[empty_v, 0], audio_latent=[lat, 0])
        guide = node(f"h3_clone_guide{i}_", "LTXVDualCFGGuider", f"line {i}: guidance",
                     model=[model, 0], positive=[cond, 0], negative=[cond, 1],
                     video_cfg=1.0, audio_cfg=float(audio_cfg))
        noise = node(f"h3_clone_noise{i}_", "RandomNoise", f"line {i}: seed",
                     noise_seed=(int(job.seed) + i) & 0xFFFFFFFFFFFFFFFF)
        samp = node(f"h3_clone_sample{i}_", "SamplerCustomAdvanced", f"line {i}: {name}",
                    noise=[noise, 0], guider=[guide, 0], sampler=[pick, 0], sigmas=[sch, 0],
                    latent_image=[av, 0])
        if held:
            if who not in kept:
                kept[who] = held_file(g, held["audio"], f"{name}'s voice sample", vae)
            swap_in(g, kept[who], f"{name}'s voice sample", [samp])
        sep = node(f"h3_clone_sep{i}_", "LTXVSeparateAVLatent", f"line {i}: its sound",
                   av_latent=[samp, 0])
        dec = node(f"h3_clone_dec{i}_", "LTXVAudioVAEDecode", f"line {i}: decoded",
                   samples=[sep, 1], audio_vae=vae)
        said = node(f"h3_clone_line{i}_", "TrimAudioDuration", f"line {i}: the line alone",
                    audio=[dec, 0], start_index=round(head, 3), duration=round(secs, 3))
        if prev is not None:
            gap = node(f"h3_clone_gap{i}_", "EmptyAudio", f"beat before line {i}",
                       duration=SP.GAP_SPEAKER if prev != who else SP.GAP_SAME,
                       sample_rate=48000, channels=2)
            sound = node(f"h3_clone_join{i}_a", "AudioConcat", f"lines up to {i}",
                         audio1=[sound, 0], audio2=[gap, 0], direction="after")
        sound = node(f"h3_clone_join{i}_b", "AudioConcat", f"lines up to {i}",
                     audio1=[sound, 0], audio2=[said, 0], direction="after")
        prev = who
    return [sound, 0]
