"""
A sound held in an LTX graph: given to the sampler as it is, with the model
making only what's around it. LTX samples one latent of picture and sound
together (LTXVConcatAVLatent), and a noise mask of 0 on part of it tells the
sampler to leave that part alone, so

    LoadAudio -> LTXVAudioVAEEncode -> SetLatentNoiseMask (SolidMask 0)

swapped into the audio of every latent a sampler samples (a second
LTXVConcatAVLatent around the stage's own: ComfyUI's swaps the audio of an
AV latent it is given, zero-padding or cutting it to the clip's length, the
padding left for the model) holds that sound through every stage. Two uses:

  * a voice sample held at the head of an audio-only clip, which LTX then
    continues in the same voice (targets/audio/ltx2_voice);
  * a shot's window of the recorded dialogue held as its whole soundtrack, so
    the picture is made to it: `dub` on the LTX video targets.

Both measured live 2026-10-28 (docs/PLAN.md, "Voice clone by continuation"
and "LTX dub"): the held sound came back unchanged through both stages of
the two-stage graph (envelope correlation 0.97-0.99), and mouths moved with it.

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


def hold(g: dict, name: str, what: str) -> list[str]:
    """`name` (a file ComfyUI's LoadAudio reads) held through every stage of
    `g`; `what` says what it is, in the new nodes' titles. Returns the
    samplers it reaches (ValueError when there are none)."""
    stages = samplers(g)
    if not stages:
        raise ValueError("the graph has no sampler sampling an LTXVConcatAVLatent to hold "
                         "a sound in")
    load = _new_id(g, "h3_held_load")
    g[load] = {"class_type": "LoadAudio", "inputs": {"audio": name},
               "_meta": {"title": f"{what} (held)"}}
    enc = _new_id(g, "h3_held_encode")
    g[enc] = {"class_type": "LTXVAudioVAEEncode",
              "inputs": {"audio": [load, 0], "audio_vae": audio_vae(g)},
              "_meta": {"title": f"{what} encoded"}}
    mask = _new_id(g, "h3_held_mask")
    g[mask] = {"class_type": "SolidMask", "inputs": {"value": 0.0, "width": 32, "height": 32},
               "_meta": {"title": f"{what}: mask 0, left as it is"}}
    held = _new_id(g, "h3_held")
    g[held] = {"class_type": "SetLatentNoiseMask",
               "inputs": {"samples": [enc, 0], "mask": [mask, 0]},
               "_meta": {"title": f"{what} held"}}
    for n, s in enumerate(stages, 1):
        swap = _new_id(g, f"h3_held_swap{n}_")
        g[swap] = {"class_type": "LTXVConcatAVLatent",
                   "inputs": {"video_latent": [_src(g, s, "latent_image"), 0],
                              "audio_latent": [held, 0]},
                   "_meta": {"title": f"{what} as the sound, stage {n}"}}
        g[s]["inputs"]["latent_image"] = [swap, 0]
    return stages


def trim_head(g: dict, start: float, seconds: float, what: str) -> str:
    """The decoded sound with its first `start` seconds taken off (and cut to
    `seconds`), for everything that read it."""
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


# -- a dub shot's window of the recording ------------------------------------------

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
    if policy not in DUB:
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
