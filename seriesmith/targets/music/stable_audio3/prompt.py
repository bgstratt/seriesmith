"""
stable_audio3: Stable Audio 3 Medium (target.json beside this file). It takes text and a
length, so the cue is one paragraph: its head (style, the tempo in words, meter, key), the
script's music: notes as its mood, and its sections told as a story, which it followed far
better than timestamps (docs/SOUND.md "Measured: Stable Audio 3 Medium").

`cue_graph` is the graph surgery a theme needs (cue.graph calls it): the theme's sound is
where the sampler starts, at the theme's strength, and with SheetSage2 the take and the
theme are transcribed for the take's melody score.

Stdlib only.
"""
from __future__ import annotations

from seriesmith.targets.music import common as C


def sigmas(t0: float, steps: int = 8) -> list[float]:
    """The schedule from a strength: `steps` even steps of t from `t0` down, then 0, as SA3's
    sigmas (a flow model at shift 2: sigma = 2t / (1 + t)). KSampler's denoise snaps at 8
    steps (to t0 0.80 and 0.889); this is any t0 (docs/SOUND.md "Measured: leitmotifs")."""
    out = []
    for i in range(steps):
        t = t0 * (steps - i) / steps
        out.append(2 * t / (1 + t))
    return out + [0.0]


def cue_graph(target, g: dict, plan: dict, values: dict, audio) -> None:
    """A theme rendered from (plan["theme"]["use"] "audio"; `audio` its sound reshaped to the
    cue, as the backend uploads it): LoadAudio -> VAEEncodeAudio (the checkpoint's VAE) is the
    latent in place of the empty one, and KSampler becomes SamplerCustom on ManualSigmas
    (`sigmas` from the theme's strength), its sampler and cfg kept. With the plan's `melody`
    (SheetSage2 installed), the take and the theme are both transcribed (SheetSage2AudioToABC,
    melody) and saved as text, `cue_melody` and `theme_melody`, for the take's melody score."""
    th = plan.get("theme") or {}
    if th.get("use") != "audio" or audio is None:
        return
    ks = [k for k, v in g.items() if v["class_type"] == "KSampler"]
    ck = [k for k, v in g.items() if v["class_type"] == "CheckpointLoaderSimple"]
    dec = [k for k, v in g.items() if v["class_type"] == "VAEDecodeAudio"]
    if len(ks) != 1 or len(ck) != 1 or len(dec) != 1:
        return
    k = g[ks[0]]["inputs"]
    t0 = float(th.get("strength") or target.capabilities().get("theme_strength") or 0.86)
    g["r1"] = {"class_type": "LoadAudio", "inputs": {"audio": audio}, "_meta": {"title": "Theme"}}
    g["r2"] = {"class_type": "VAEEncodeAudio", "inputs": {"audio": ["r1", 0], "vae": [ck[0], 2]},
               "_meta": {"title": "Theme encoded"}}
    g["r3"] = {"class_type": "ManualSigmas",
               "inputs": {"sigmas": ", ".join(f"{s:.6f}" for s in sigmas(t0, int(k.get("steps") or 8)))},
               "_meta": {"title": f"From the theme at {t0:g}"}}
    g["r4"] = {"class_type": "KSamplerSelect", "inputs": {"sampler_name": k.get("sampler_name") or "lcm"}}
    g["r5"] = {"class_type": "SamplerCustom", "inputs": {
        "model": k["model"], "add_noise": True, "noise_seed": k.get("seed", 0), "cfg": k.get("cfg", 1.0),
        "positive": k["positive"], "negative": k["negative"], "sampler": ["r4", 0], "sigmas": ["r3", 0],
        "latent_image": ["r2", 0]}, "_meta": {"title": "Sampler, from the theme"}}
    g[dec[0]]["inputs"]["samples"] = ["r5", 0]
    empty = k.get("latent_image")
    del g[ks[0]]
    if isinstance(empty, list) and empty[0] in g and g[empty[0]]["class_type"] == "EmptyLatentAudio":
        del g[empty[0]]
    if plan.get("melody"):
        g["m1"] = {"class_type": "AudioEncoderLoader",
                   "inputs": {"audio_encoder_name": values.get("sheetsage") or "sheetsage2_bf16.safetensors"},
                   "_meta": {"title": "Transcriber"}}
        for nid, src, name in (("m2", [dec[0], 0], "cue_melody"), ("m4", ["r1", 0], "theme_melody")):
            g[nid] = {"class_type": "SheetSage2AudioToABC",
                      "inputs": {"audio_encoder": ["m1", 0], "audio": src, "mode": "melody"},
                      "_meta": {"title": name.replace("_", " ")}}
            g[nid + "s"] = {"class_type": "SaveText", "inputs": {
                "text": [nid, 0], "filename_prefix": f"seriesmith/{name}", "format": "txt"}}


def cue_prompt(target, cue: dict) -> dict:
    mood = C.notes(cue)
    text = " ".join(x for x in (C.head(cue, bpm_in_text=True), f"Mood: {mood}." if mood else "",
                                C.story(cue)) if x)
    return {"prompt": text, "negative": None, "values": {"seconds": round(float(cue["seconds"]), 3)}}
