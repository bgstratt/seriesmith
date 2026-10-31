# Full setup

[Getting started](QUICKSTART.md) gets you writing, rendering, cutting and
exporting on the models you already have. This page is everything on top of that, grouped
by what it gives you: the node packs, model files, LoRAs and other software for each
feature.

You only need the parts for what you use. Install any of it in any order.

## Install it from the editor

You don't have to do any of this by hand. **Settings → Features…** lists every feature on
this page, grouped the same way:
- what's already installed is ticked;
- tick the rest you want, and the window shows how much it will download;
- press **Install**.

seriesmith then puts each piece in:
- **model files** go into ComfyUI's `models/` folders;
- **ffmpeg** is a full build downloaded into seriesmith's own folder.

The window shows each item's progress. A stopped download resumes where it left off next
time.

Two kinds of piece you put in yourself, and the window says how for each one missing:
- **node packs**: install them with ComfyUI-Manager (or clone the repo the window names
  into `custom_nodes/`), then restart ComfyUI;
- **Python packages**: the window gives the pip command for the Python that uses them,
  to copy and run.

A ComfyUI node pack may neither install Python packages while it runs nor install other
node packs (the Comfy Registry's rules), so seriesmith doesn't.

Mix and match as you like: for example, RTX Video Super Resolution instead of Real-ESRGAN
for pixel upscales, or SeedVR2 without the H3 latent upscaler.

The **What's missing** window has an **Install** button too, beside each missing file
that has a known download. For a missing node it says to install the pack that provides
it with ComfyUI-Manager, which can search by node name.

**Gated models.** LTX-2.5 and the FLUX models are gated on Hugging Face:
1. Accept the licence on the model's page (the window links it).
2. Make a read token on huggingface.co (Settings → Access Tokens).
3. Paste the token into **Settings → Hugging Face token**, or set `HF_TOKEN`.

**Where it installs.** Inside ComfyUI, seriesmith uses that ComfyUI's own folders. The
standalone editor asks the ComfyUI on this machine where its folders are. For a ComfyUI it
can't ask, set **Settings → Folders → ComfyUI folder**.

To see what's still missing without installing anything: each model picker's **What's
missing** window, or `seriesmith targets` with ComfyUI running.

This page isn't the list of every model seriesmith supports. That list, with every file,
folder and link, is [INSTALL.md, section 4](../INSTALL.md#4-models).

- [Install it from the editor](#install-it-from-the-editor)
- [At a glance](#at-a-glance)
- [Rendering video](#rendering-video)
- [Pictures: characters, places, props and keyframes](#pictures-characters-places-props-and-keyframes)
- [Sound: voices and recorded dialogue](#sound-voices-and-recorded-dialogue)
- [Upscaling](#upscaling)
- [Post-processing](#post-processing)
- [Master, publish and the export](#master-publish-and-the-export)
- [360s and turned views](#360s-and-turned-views)
- [Software outside ComfyUI](#software-outside-comfyui)

By hand instead: put each model file in the ComfyUI `models/` folder named beside it
(`models/loras/`, `models/vae/`, ...). ComfyUI also reads `models/unet/` for `diffusion_models` and
`models/clip/` for `text_encoders`. Install node packs with ComfyUI-Manager or by
cloning them into `custom_nodes/`, then restart ComfyUI.

## At a glance

| For | Node packs | Model files | Other |
|---|---|---|---|
| MiniMax H3 at full quality and speed | ComfyUI-PlagueKind-Nodes | H3's 4 files, 2 turbo LoRAs | |
| Shots that carry on from the one before | | H3 FL2VA's model, 2 turbo LoRAs | |
| Reference pictures and keyframes | | Krea 2's 3 files; FLUX.2 Klein's 3 | |
| Location tours | ComfyUI-PlagueKind-Nodes | H3 FL2VA's | |
| Generated voice samples | ComfyUI-LTXVideo | LTX-2.5's transformer, text encoder, audio VAE | |
| Recorded dialogue | | | faster-whisper; demucs for `dub_keep_foley` |
| Upscaling H3 takes | Comfyui_Minimax_h3_latent_Upscaler; comfyui-obvpm-timeline for takes over 5.5 s | H3's latent upscaler | |
| Upscaling any take | Nvidia RTX Nodes (optional) | RealESRGAN, or SeedVR2 | |
| Post-processing | | RealESRGAN / SeedVR2 7B / SUPIR + SDXL; RAFT for motion blur | |
| Master and publish | | | a title font (ffmpeg comes with seriesmith) |
| 360s and turned views | | 3 LoRAs | |

## Rendering video

seriesmith renders on whichever video model is installed: see
[Which models it uses](QUICKSTART.md#which-models-it-uses). The default, and the one every
feature is built around, is **MiniMax H3 Ref2VA**. It keeps characters and places like
their pictures and lip-syncs what they say.

**MiniMax H3 Ref2VA** (`minimax_h3_ref2va`):

| File | Folder | Download |
|---|---|---|
| `minimax_h3_ref2va_pruned_int8_convrot.safetensors` | `diffusion_models` | [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors) |
| `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | `text_encoders` | [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors) |
| `minimax_h3_video_vae_fp16.safetensors` | `vae` | [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/vae/minimax_h3_video_vae_fp16.safetensors) |
| `minimax_h3_audio_vae_fp32.safetensors` | `vae` | [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/vae/minimax_h3_audio_vae_fp32.safetensors) |
| `minimax_h3_ref2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors` (final pass) | `loras` | [lightx2v/Minimax-h3-Turbo](https://huggingface.co/lightx2v/Minimax-h3-Turbo/resolve/main/minimax_h3_ref2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors) |
| `minimax_h3_ref2v_lightx2v_turbo_4step_v0.1_resized_avg_rank_20_bf16.safetensors` (proxy pass) | `loras` | [Kijai/MiniMax-H3_comfy](https://huggingface.co/Kijai/MiniMax-H3_comfy/resolve/main/loras/minimax_h3_ref2v_lightx2v_turbo_4step_v0.1_resized_avg_rank_20_bf16.safetensors) |

- **The two LoRAs** are accelerators. Without them a pass still renders, on the slower
  base preset, and the take says so.
- **[ComfyUI-PlagueKind-Nodes](https://github.com/PlagueKind/ComfyUI-PlagueKind-Nodes)**
  adds `H3SLAAttention`, the sparse attention the turbo LoRAs were trained with.
  - Without it, H3 renders with the node left out, and the editor marks H3 as
    **degraded**.
  - With it, you get the quality and speed the LoRAs were made for.
- **The default H3 stack** wants a recent NVIDIA card. seriesmith is developed on a 32 GB
  RTX 5090.

**Shots that carry on from the one before** (`continuous: first`) render on
**MiniMax H3 FL2VA**. FL2VA uses H3's text encoder and VAEs, plus:

| File | Folder | Download |
|---|---|---|
| `minimax_h3_fl2va_pruned_int8_convrot.safetensors` | `diffusion_models` | [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors) |
| `minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors` | `loras` | [lightx2v/Minimax-h3-Turbo](https://huggingface.co/lightx2v/Minimax-h3-Turbo/resolve/main/minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors) |
| `minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors` | `loras` | [Kijai/MiniMax-H3_comfy](https://huggingface.co/Kijai/MiniMax-H3_comfy/resolve/main/loras/minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors) |

FL2VA also runs the editor's **location tours**. Tours still need
ComfyUI-PlagueKind-Nodes.

**Other models.** LTX-2.5 (it makes its own sound), LTX-2.3 ingredients, and Wan 2.2 I2V,
5B and VACE (Wan makes no sound) are listed file by file in
[INSTALL.md, Everything, by model family](../INSTALL.md#everything-by-model-family). All of
them use core ComfyUI nodes. The hosted models on Comfy Router need no files, only a Comfy
API key ([SETUP.md](SETUP.md)).

## What's installed: `seriesmith targets`

Run `seriesmith targets` (with ComfyUI running). It prints one
line per target, `ready`, `degraded`, `not_ready` or `unknown` (ComfyUI didn't answer),
and under it every file that target is missing, with the models folder it goes in and
where to download it:

```
  ltx2                 degraded   missing 1 optional
      optional    duration_head ltx-2.5-duration-head-bf16.safetensors  [feature off: dur: model (duration head)]
                  -> models/model_patches/   https://huggingface.co/Lightricks/LTX-2.5/...
```

Add an episode (`seriesmith targets Shows\ep05`) to use its series config (the pass
blocks' model and LoRA, `model_families`) and mark the episode's target. `--json` prints
the same as data.

- **Required** files (the model, text encoder, VAEs): without one the target can't render.
  Its shots are skipped when you queue them, and the message names the file, the folder
  and the download link.
- **Accelerators** (the turbo LoRAs, LTX 2.3's distilled checkpoint): without one the
  shot still renders, on the pass's slower `base` settings (more steps, no turbo LoRA),
  and the take says so.
- **Optional** files (the LTX duration head): only their feature is off (`dur: model`
  renders the estimate).

In the editor, a missing file with a link has an **Install** button in the model
picker's **What's missing** window, and **Settings → Features…** installs a whole model (or
an upscaler, a node pack, ffmpeg) at once. A link is only given when ComfyUI's own
templates, your saved workflows or ComfyUI-Manager's model list record it. Otherwise the line says to search for the exact
file name. If you have a file of the same family under another name (another
precision, a merge), it is used instead, and the take notes which file it was.

## Pictures: characters, places, props and keyframes

**Krea 2** draws the character sheets, props and location plates (`krea2`, the default
picture model):

| File | Folder | Download |
|---|---|---|
| `krea2_turbo_fp8_scaled.safetensors` | `diffusion_models` | [Comfy-Org/Krea-2](https://huggingface.co/Comfy-Org/Krea-2/resolve/main/diffusion_models/krea2_turbo_fp8_scaled.safetensors) |
| `qwen3vl_4b_fp8_scaled.safetensors` | `text_encoders` | [Comfy-Org/Krea-2](https://huggingface.co/Comfy-Org/Krea-2/resolve/main/text_encoders/qwen3vl_4b_fp8_scaled.safetensors) |
| `wan_2.1_vae.safetensors` | `vae` | [Comfy-Org/Wan_2.2_ComfyUI_Repackaged](https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors) |

**FLUX.2 Klein 9B edit** draws shot keyframes from the characters' and places' pictures
(`flux2_klein_edit`). Without it, keyframes are drawn on the picture model:

| File | Folder | Download |
|---|---|---|
| `flux-2-klein-9b-kv.safetensors` | `diffusion_models` | [black-forest-labs/FLUX.2-klein-9b-kv](https://huggingface.co/black-forest-labs/FLUX.2-klein-9b-kv/resolve/main/flux-2-klein-9b-kv.safetensors) |
| `qwen_3_8b_fp8mixed.safetensors` | `text_encoders` | [Comfy-Org/flux2-klein-9B](https://huggingface.co/Comfy-Org/flux2-klein-9B/resolve/main/split_files/text_encoders/qwen_3_8b_fp8mixed.safetensors) |
| `flux2-vae.safetensors` | `vae` | [Comfy-Org/flux2-dev](https://huggingface.co/Comfy-Org/flux2-dev/resolve/main/split_files/vae/flux2-vae.safetensors) |

The other picture models (Z-Image Turbo, Qwen-Image 2.1, FLUX.3 Klein, MOSS-Image, FLUX.1 Kontext,
Qwen-Image-Edit Rapid) are in [INSTALL.md](../INSTALL.md#everything-by-model-family).

Which one makes what is the series config's `refs` block (`target`, `keyframe_target`,
`voice_target`; [AUTHORING.md](AUTHORING.md)), the editor's per-episode choice, or a
ref's own. Every picture model, and the voice model:

| image target | what it is |
|---|---|
| `krea2` | Krea 2 turbo, text to image (the default for refs) |
| `z_image_turbo` | Z-Image Turbo, fast text to image |
| `flux2_klein` | FLUX.2 Klein 9B, text to image |
| `flux2_klein_edit` | FLUX.2 Klein 9B with up to 4 reference images (the default for keyframes when it is installed; otherwise keyframes use the refs model) |
| `flux_kontext` | FLUX.1 Kontext dev, with one reference image |
| `minimax_h3_still` | MiniMax H3 — the video model, rendering 5 frames and keeping the first, with up to 9 reference images. No second model stack to install if you already render on H3 |
| `qwen_image_21` | Qwen-Image 2.1 — one model for both jobs: text to image for a character's own views, an edit of up to 16 reference images for a variant's. Takes a real negative prompt, and its cfg, scheduler and denoise are ordinary sampler settings |
| `flux3_klein` | FLUX.3 Image Klein — like `qwen_image_21`, one model for both jobs: text to image, or an edit of up to 10 reference images. Takes a real negative prompt |
| `flux3_klein_turbo` | FLUX.3 Image Klein step-distilled: the same as `flux3_klein` in 16 steps, over twice as fast, without a negative prompt |
| `fasth3_omni_still` | FastH3 Omni as an image model, as `minimax_h3_still`: up to 9 reference images, 8 steps, no turbo LoRA |
| `fibo2_dev` | Bria's Fibo 2.0 Dev: text to image, or an edit of up to 4 reference images (relights too); 50 steps at cfg 5. Non-commercial licence (CC BY-NC 4.0) |
| `fibo2_edit_turbo` | Fibo 2.0 Edit Turbo: edits only (it needs a picture to start from), 4 steps at cfg 1. Non-commercial licence |
| `moss_image_sft` | MOSS-Image SFT, text to image: strong on lettering and layout, 50 steps at cfg 3 with a real negative prompt |
| `moss_image_base` | MOSS-Image Base: the model the SFT is tuned from, for LoRAs trained on the base |
| `qwen_rapid_aio` | Qwen-Image-Edit Rapid AIO: a 4-step all-in-one edit checkpoint, up to 3 reference images |
| `klein_erp_360` | FLUX.2 Klein 9B with a 360 outpaint LoRA: a plate as an equirectangular panorama (the Refs tab's **Make 360**) |
| hosted on Comfy Router: `krea_2_router`, `nano_banana_pro`, `nano_banana_2_1`, `gemini_3_1_flash_image`, `seedream_5_0`, `gpt_image_2`, `flux_kontext_pro`, `flux_2_pro`, `qwen_image_3`, `kling_image_o1` | one call a picture, nothing to install; most take reference images |

| audio target | what it is |
|---|---|
| `ltx2_voice` | LTX-2.5 audio-only: one speaking voice saying a line from the script, from the character's `voice` line, or continuing the voice ref's own sample when it has one (the default for voices) |

What each picture model takes (generated from the models by `python tools/make_refs_md.py`):

<!-- BEGIN PICTURE MODELS (generated by tools/make_refs_md.py — do not edit) -->

| Picture model | | Runs on | Reference pictures | Makes |
|---|---|---|---|---|
| `fasth3_omni_still` | Omni still | your ComfyUI | up to 9 | edits and new pictures |
| `fibo2_dev` | Fibo | your ComfyUI | up to 4 | edits and new pictures |
| `fibo2_edit_turbo` | Fibo turbo | your ComfyUI | up to 4 | edits and new pictures |
| `flux2_klein` | Klein | your ComfyUI | none | new pictures |
| `flux2_klein_edit` | Klein edit | your ComfyUI | up to 4 | edits and new pictures |
| `flux3_klein` | Klein 3 | your ComfyUI | up to 10 | edits and new pictures |
| `flux3_klein_turbo` | Klein 3 turbo | your ComfyUI | up to 10 | edits and new pictures |
| `flux_kontext` | Kontext | your ComfyUI | up to 1 | edits and new pictures |
| `klein_erp_360` | Klein 360 | your ComfyUI | up to 1 | new pictures |
| `krea2` | krea2 | your ComfyUI | none | new pictures |
| `minimax_h3_still` | H3 still | your ComfyUI | up to 9 | edits and new pictures |
| `moss_image_base` | MOSS base | your ComfyUI | none | new pictures |
| `moss_image_sft` | MOSS | your ComfyUI | none | new pictures |
| `qwen_image_21` | Qwen 2.1 | your ComfyUI | up to 16 | edits and new pictures |
| `qwen_rapid_aio` | Rapid AIO | your ComfyUI | up to 3 | edits and new pictures |
| `z_image_turbo` | Z-Image | your ComfyUI | none | new pictures |
| `flux_2_pro` | Flux 2 Pro | Comfy Router | up to 8, as links | edits and new pictures |
| `flux_kontext_pro` | Kontext Pro | Comfy Router | up to 4, as links | edits and new pictures |
| `gemini_3_1_flash_image` | Gemini Flash | Comfy Router | up to 3, inline | edits and new pictures |
| `gpt_image_2` | GPT Image | Comfy Router | up to 8, as links | edits and new pictures |
| `kling_image_o1` | Kling Image | Comfy Router | up to 10, as links | edits and new pictures |
| `krea_2_router` | Krea 2 (Router) | Comfy Router | none | new pictures |
| `nano_banana_2_1` | Nano Banana | Comfy Router | up to 6, inline | edits and new pictures |
| `nano_banana_pro` | Nano Banana Pro | Comfy Router | up to 6, inline | edits and new pictures |
| `qwen_image_3` | Qwen Image | Comfy Router | up to 3, as links | edits and new pictures |
| `seedream_5_0` | Seedream | Comfy Router | up to 10, as links | edits and new pictures |

<!-- END PICTURE MODELS -->

## Sound: voices and recorded dialogue

H3 and LTX-2.5 make a shot's sound themselves. These are for the rest.

**Generated voice samples** give each character a voice sample. A shot whose audio is
`clone` then speaks its lines in that voice (`ltx2_voice`). This needs
[ComfyUI-LTXVideo](https://github.com/Lightricks/ComfyUI-LTXVideo) (its audio-only nodes)
and three of LTX-2.5's files:

| File | Folder | Download |
|---|---|---|
| `ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors` | `diffusion_models` | [Lightricks/LTX-2.5](https://huggingface.co/Lightricks/LTX-2.5/resolve/main/diffusion_models/ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors) |
| `gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors` | `text_encoders` | [Lightricks/LTX-2.5](https://huggingface.co/Lightricks/LTX-2.5/resolve/main/text_encoders/gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors) |
| `ltx-2.5-audio-vae-bf16.safetensors` | `vae` | [Lightricks/LTX-2.5](https://huggingface.co/Lightricks/LTX-2.5/resolve/main/vae/ltx-2.5-audio-vae-bf16.safetensors) |

ComfyUI-LTXVideo also lets the `ltx2` video model read reference sheets.

A character with no `voice_sample` still has a voice ref: generating one and picking it
writes `refs/voices/<id>.wav` **and** adds the `voice_sample` line to `series.json` for
you (the only thing the editor writes there). `seriesmith refs <ep> --voices` does the
same from the command line, and `--from-take sh020:3:1.2-6.4` makes a sample out of a
line the model already spoke in a take, with no model at all.

Generating a voice that **already has a sample** copies it: the first 1.5–2.5 seconds of the
sample (cut in a pause between words) are played to `ltx2_voice`, which carries on in that
voice with the character's line, and that head is cut off again. So a short or rough
recording, or a few seconds cut from a take, becomes a clean sample of the character saying
their own words. The voice comes out close, not identical: listen before you pick.

**Recorded dialogue** lip-syncs an episode to lines you recorded
([RECORDED_DIALOGUE.md](RECORDED_DIALOGUE.md)):

- `pip install faster-whisper numpy` for `seriesmith align` and the editor's Recording
  window. Install them in seriesmith's Python, or in any Python on PATH; the Recording
  window names the one it found and prints the exact `pip install` line for it.
- `pip install demucs`, in the `python` first on ComfyUI's PATH, for the
  `dub_keep_foley` audio policy. It strips H3's own vocal and keeps the foley under yours.

## Upscaling

You only need this to upscale takes: `seriesmith upscale`, the editor's **Upscale**,
**Export 2x**, `master`. A render never needs it. Each method is independent: install the
ones you want.

**H3 takes, re-sampled at 2x** (the best for H3):
- **The node pack:**
  [Comfyui_Minimax_h3_latent_Upscaler](https://github.com/LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler).
  Use that one, **not its "Plus" fork**: the fork invents detail. ComfyUI-Manager lists only
  the fork, so clone this one into `custom_nodes` (or Manager's **Install via Git URL**).
- **The model:** `minimax_h3_latent_upscaler_3d_fp16.safetensors` in
  `models/latent_upscale_models/`. Its Hugging Face repo now publishes it as
  `minimax_h3_latent_upscaler_3d_conv_v1_fp16.safetensors`; save it under the old name
  ([download](https://huggingface.co/LBH-123-AI/Minimax_h3_latent_Upscaler)).
- **For takes longer than 5.5 s:**
  [comfyui-obvpm-timeline](https://github.com/chanon/comfyui-obvpm-timeline). Its context
  windows let a long shot at 2x fit a 32 GB card.

**LTX-2.5 takes** need nothing: an upscale runs the model's own latent upsampler again.

**Any take, through an upscale model** (the pixel method): put one or more in
`models/upscale_models/`. RealESRGAN_x2 is the default; RealESRGAN_x4 is the other choice.
Both come from the [xinntao/Real-ESRGAN releases](https://github.com/xinntao/Real-ESRGAN/releases).

**Any take, with SeedVR2**, which adds real detail and is slower. It runs on ComfyUI's
own nodes. You need the VAE and at least one model:

| File | Folder | Download |
|---|---|---|
| `seedvr2_ema_vae_fp16.safetensors` | `vae` | [Comfy-Org/SeedVR2](https://huggingface.co/Comfy-Org/SeedVR2/resolve/main/vae/seedvr2_ema_vae_fp16.safetensors) |
| `seedvr2_7b_int8_convrot.safetensors` | `diffusion_models` | [Comfy-Org/SeedVR2](https://huggingface.co/Comfy-Org/SeedVR2/resolve/main/diffusion_models/seedvr2_7b_int8_convrot.safetensors) |
| `seedvr2_3b_int8_convrot.safetensors` | `diffusion_models` | [Comfy-Org/SeedVR2](https://huggingface.co/Comfy-Org/SeedVR2/resolve/main/diffusion_models/seedvr2_3b_int8_convrot.safetensors) |

**Any take, on an NVIDIA RTX card, with RTX Video Super Resolution** (no model file, and
fast):
1. Install Comfy-Org's **Nvidia RTX Nodes** (ComfyUI-Manager: search "RTX"; it needs
   CUDA PyTorch cu130 or newer).
2. If ComfyUI's log says `No module named 'nvvfx'`, run
   `python_embeded\python.exe -m pip install nvidia-vfx --extra-index-url https://pypi.nvidia.com`
   and restart ComfyUI.

## Post-processing

Post-processing runs after the upscale: whole-frame enhancement, then motion blur
([POST_PROCESSING.md](POST_PROCESSING.md)).

| Tier | Needs |
|---|---|
| Draft | an upscale model (RealESRGAN_x2), as above |
| Production | SeedVR2 7B and its VAE, as above |
| Cinematic | `SUPIR-v0F_fp16.safetensors` in `models/model_patches/` ([Kijai/SUPIR_pruned](https://huggingface.co/Kijai/SUPIR_pruned/resolve/main/SUPIR-v0F_fp16.safetensors)), and the SDXL base checkpoint `sd_xl_base_1.0_0.9vae.safetensors` in `models/checkpoints/` ([stabilityai/stable-diffusion-xl-base-1.0](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0)) |
| Deblur on RTX | Nvidia RTX Nodes, as above |
| Motion blur | `raft_large_C_T_SKHT_V2-ff5fadd5.pth` in `models/optical_flow/` ([torchvision's weights](https://download.pytorch.org/models/raft_large_C_T_SKHT_V2-ff5fadd5.pth); ComfyUI doesn't download them) |

## Master, publish and the export

Assemble, master and publish cut with ffmpeg. You don't need to install it:
- **seriesmith's own install** brings a static ffmpeg build (imageio-ffmpeg) and PyAV;
- **inside ComfyUI**, PyAV is always there. `ffmpeg` itself comes from:
  - imageio-ffmpeg in ComfyUI's Python (ComfyUI-Manager installs it with seriesmith's
    pack);
  - otherwise the repo's `.venv`, once `run_seriesmith` has made it;
  - otherwise one on PATH.
- **Your own ffmpeg** comes first:
  - the folder named in **Settings → Folders → ffmpeg folder**;
  - else the full build **Features → ffmpeg and ffprobe** downloads (gyan.dev's on
    Windows, a static build on Linux);
  - else one on PATH (`winget install Gyan.FFmpeg`, `apt install ffmpeg`,
    `brew install ffmpeg`).

**Titles.** Publish writes the episode's title under the series title on the series'
intro and outro clips, with one font file for every episode. The default is
`C:\Windows\Fonts\segoescb.ttf`; set `publish.subtitle.font` in the series config to
any `.ttf` or `.otf` to use another. The intro and outro clips themselves are yours to
make, once per series ([COMMANDS.md](COMMANDS.md)).

## 360s and turned views

The Refs tab's **Make 360** and a character's **Turn** each use a LoRA in `models/loras/`.
Only the button that uses one needs it:

| File | Used by | Download |
|---|---|---|
| `flux-2-klein-9B-360-erp-outpaint-lora_V1.safetensors` | **Make 360** on FLUX.2 Klein (the default; also needs `flux-2-klein-base-9b-fp8.safetensors`) | [nomadoor/flux-2-klein-9B-360-erp-outpaint-lora](https://huggingface.co/nomadoor/flux-2-klein-9B-360-erp-outpaint-lora/resolve/main/flux-2-klein-9B-360-erp-outpaint-lora_V1.safetensors) |
| `pano360_qwen21_edit_v1.safetensors` | **Make 360** on Qwen-Image 2.1 | [Gogodr/qwen-image-2.1-edit-pano360-lora](https://huggingface.co/Gogodr/qwen-image-2.1-edit-pano360-lora/resolve/main/pano360_qwen21_edit_v1.safetensors) |
| `angles_v2_full_qwen21_multiple_angles_v2_qwen21_multiple_angles_v2_000001500.safetensors` | a character's **Turn** (Qwen-Image 2.1) | [akhaliq/Qwen-Image-2.1-Multiple-Angles-LoRA](https://huggingface.co/akhaliq/Qwen-Image-2.1-Multiple-Angles-LoRA/resolve/main/checkpoints_v2/angles_v2_full_qwen21_multiple_angles_v2_qwen21_multiple_angles_v2_000001500.safetensors) |

## Renamed or merged model files: `model_families`

Every model file a shot loads is checked against the model family its target needs
(LTX 2.5 for `ltx2`, H3 Ref2VA for `minimax_h3_ref2va`, ...) when it is queued. A file
named like the family passes. Any other name is identified from the file's own header
(the tensor names and shapes of a `.safetensors` file; the weights aren't loaded). If the
header says it's the right family, it renders with a note. If it says it's **another**
family, the shot is skipped ("wan2.2_i2v_low_noise_14B_fp8_scaled is Wan 2.2 I2V 14B
low-noise, but this LTX-2 target's model must be LTX 2.5") unless you render anyway.

A header can't tell every family apart. H3 Ref2VA and FL2VA files are identical inside, and
so are Wan 2.2's high- and low-noise experts and the LTX 2.3 and 2.5 upscalers. For
those, the name decides. If you rename or merge such a file, add its name to the series
config so the pipeline knows which one it is:

```json
"model_families": {
  "ltx2.5": ["my_ltx25_merge*"],
  "minimax-h3-ref2va": ["h3_faces_finetune*"]
}
```

- Keys are family ids: `minimax-h3-ref2va`, `minimax-h3-fl2va`, `ltx2.5`, `ltx2.3`,
  `ltx2.5-latent-upscaler`, `krea2`, `wan2.2-i2v-14b-high`, `wan2.2-i2v-14b-low`, ...
  (`targets/modelid.py` lists them all; each target's `target.json` `models` block says
  which one each of its model settings needs).
- Values are file-name patterns: `*` matches anything, case doesn't matter. They add to
  the target's own patterns; they don't replace them.
- A matching name is trusted without reading the file, so keep the patterns specific.

## Software outside ComfyUI

| Install | For |
|---|---|
| Python 3.10 or later | the editor on its own page and the `seriesmith` command (`run_seriesmith` sets up the rest) |
| `pip install faster-whisper numpy` | recorded dialogue: `align` and the Recording window |
| `pip install demucs`, for ComfyUI's `python` | the `dub_keep_foley` audio policy |
| Node.js 20.19+ and `npm install` in `web/` | only to rebuild the editor after changing `web/` |
| `pip install pytest` | the test suite |

Comfy Cloud, deployments and the hosted Router models need only a Comfy API key, set in
**Settings** ([SETUP.md](SETUP.md)). Saving it installs Comfy's SDK, which they run on,
into ComfyUI's Python if it isn't there; nothing to do by hand.
