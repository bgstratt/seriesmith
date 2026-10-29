# Installing seriesmith

From nothing to a rendered proxy episode. Windows first (the development machine); the
Linux/macOS differences are called out where they exist. The commands are written with
Windows paths: on Linux/macOS use forward slashes, and `python3` where `python` is
missing.

What you end up with: seriesmith's node pack in ComfyUI, its editor inside ComfyUI or
on a page of its own (`seriesmith serve`), the `seriesmith` command, and one episode
folder holding a series config, a script, and everything seriesmith generated from them.

**In a hurry?** [Getting started](docs/QUICKSTART.md): install seriesmith from
ComfyUI-Manager (or run it on a page of its own, or clone it into `custom_nodes`), start
ComfyUI. No other node packs, no ffmpeg to install; it renders on the models you already
have.
[Full setup](docs/FULL_SETUP.md) lists the node packs, model files and software each extra
feature needs, and **Settings → Features…** in the editor lists them all, downloading the
model files itself. This page is every part in detail.

1. [Requirements](#1-requirements)
2. [seriesmith and the node pack](#2-seriesmith-and-the-node-pack)
3. [Workflows](#3-workflows)
4. [Models](#4-models)
5. [First run](#5-first-run)
6. [Troubleshooting](#6-troubleshooting)

The format of what you write is [docs/AUTHORING.md](docs/AUTHORING.md); the backends
(Comfy Cloud, deployments, Router) are [docs/SETUP.md](docs/SETUP.md); what seriesmith
does with it all is the [README](README.md).

---

## 1. Requirements

- **Python 3.10 or later**, for the editor on its own page and the `seriesmith` command
  (inside ComfyUI, seriesmith runs on ComfyUI's own Python; ComfyUI-Manager installs the
  two packages it needs there, comfy-sdk and imageio-ffmpeg).
  `run_seriesmith.bat` makes the repo's `.venv` and runs `pip install -e .` there the
  first time; that installs what seriesmith needs (comfy-sdk, aiohttp, Pillow, numpy,
  imageio-ffmpeg, PyAV). The build and `check` themselves need nothing beyond the
  standard library.
- **ffmpeg: nothing to install.** Assemble, master and publish cut with `ffmpeg` and
  measure with `ffprobe`; so do the waveform peaks, the audio import, `align`, the
  Recording window and a frame cut out of a take. seriesmith takes the first it finds
  (`seriesmith/ff.py`):
  - **First, your own:** the folder named in **Settings → Folders → ffmpeg folder**,
    else the full build **Settings → Features → ffmpeg and ffprobe** downloads into
    seriesmith's folder (gyan.dev's on Windows, a static build on Linux);
  - **`ffmpeg`:** else the one on PATH, else imageio-ffmpeg's (a static ffmpeg 7 build
    that comes with seriesmith's own install; inside ComfyUI, there when a node pack
    brought it, else the one in the repo's `.venv` once `run_seriesmith` has made it);
  - **`ffprobe`:** else the one on PATH, else a stand-in that answers the same questions
    through PyAV (ffmpeg's own libraries, in ComfyUI's requirements and seriesmith's).
  - A render needs neither: without ffmpeg, the saver writes the take's mp4 through PyAV,
    the same H.264 / BT.709 / AAC file, and the take's record says so.

  An ffmpeg on PATH counts too (`winget install Gyan.FFmpeg`; `apt install ffmpeg`,
  `brew install ffmpeg`).
- **Somewhere to render**, one or both:
  - **your own ComfyUI** (a recent local [ComfyUI](https://github.com/comfyanonymous/ComfyUI);
    seriesmith is developed against 0.38 — the MiniMax H3, Krea 2 and SeedVR2 nodes are
    recent core additions), with the model files of the targets you use (section 4) and a
    GPU that can hold them. seriesmith has only been run on an NVIDIA RTX 5090 (32 GB)
    under Windows; the default H3 stack (an int8 diffusion model and a 32B text encoder in
    nvfp4) wants a recent NVIDIA card. seriesmith expects it at `http://127.0.0.1:8188`.
  - **Comfy's cloud**: a Comfy API key (platform.comfy.org) for Comfy Cloud, your
    deployments and the hosted models through Comfy Router ([docs/SETUP.md](docs/SETUP.md)).
    A hosted model (Seedance, Kling, Veo, Nano Banana, ...) needs no GPU and no model
    files; paid use is billed to the key's account.
- **Optional node packs** for some extras — see [the table below](#optional-node-packs).

### Optional node packs

A render needs nothing beyond core ComfyUI and seriesmith's own pack (section 2). The packs
below add something; `seriesmith targets` names a missing node class under the target that
uses it.

| Pack | Provides | Used by |
|---|---|---|
| [ComfyUI-PlagueKind-Nodes](https://github.com/PlagueKind/ComfyUI-PlagueKind-Nodes) | `H3SLAAttention` (sparse attention the H3 turbo LoRAs were distilled against) | `minimax_h3_ref2va` and `minimax_h3_still`. Without the pack they render with the node spliced out, show as **degraded**, and the take notes it. The location tours (`seriesmith/workflows/h3_tour.json`) still need it |
| [ComfyUI-LTXVideo](https://github.com/Lightricks/ComfyUI-LTXVideo) | `LTXVAudioOnlyModel`, `LTXVAudioOnlyEmptyVideoLatent`; `LTXICLoRALoaderModelOnly`, `LTXAddVideoICLoRAGuide` | `ltx2_voice` (the default voice target); `ltx2` only for reference sheets |
| [Comfyui_Minimax_h3_latent_Upscaler](https://github.com/LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler) | `MinimaxH3LatentUpscaler3D` | `seriesmith upscale` on H3 takes only — see **The upscaler**, below |
| [comfyui-obvpm-timeline](https://github.com/chanon/comfyui-obvpm-timeline) | `H3ContextWindows` (H3 Context Windowing: sampling along time in overlapping windows) | an H3 upscale of a take longer than 5.5 s, so it fits a 32 GB card — see **The upscaler**. Its README also asks for [comfyui-obvpm](https://github.com/chanon/comfyui-obvpm); that's for its own timeline workflows, not this node |

Install them with ComfyUI-Manager or by cloning into `custom_nodes`, then restart ComfyUI.
A deployment needs the same packs there. Comfy Cloud has its own set: seriesmith sends it
Cloud's own nodes, leaving out what a model can do without ([docs/SETUP.md](docs/SETUP.md),
"Comfy Cloud").

### Optional, and what each one unlocks

| Install | Unlocks |
|---|---|
| `pip install faster-whisper numpy` | `seriesmith align` / the editor's Recording window: transcribe a dialogue recording and write `audio:` windows onto every shot |
| `pip install demucs`, for the `python` first on **ComfyUI's** PATH | the `dub_keep_foley` audio policy (H3's foley kept under your own vocal): the saver node shells out to `python -m demucs` |
| `pip install -e .[test]` | `python -m pytest`, the test suite (six workers in parallel) |
| Node.js 20.19+ (or 22.12+) and `npm install` in `web/` | rebuilding the editor. Only if you change `web/`; the built pages are committed |
| The Comfyui_Minimax_h3_latent_Upscaler node pack and its model (**The upscaler**, below) | `seriesmith upscale` and the editor's Upscale on H3 takes |
| The comfyui-obvpm-timeline node pack (**The upscaler**) | upscaling H3 takes longer than 5.5 s without running out of memory |
| Three LoRAs (**For the editor's 360s and turned views**, section 4) | the Refs tab's **Make 360** and a character's **Turn** |

**Which Python gets faster-whisper.** `align` runs as a subprocess, and seriesmith picks
its interpreter, best first:

1. `$SERIESMITH_ALIGN_PYTHON`, if set to an interpreter path
2. the Python seriesmith runs on
3. `python`, then `python3`, as found on PATH

— the first of those that has both `numpy` and a Whisper. The editor's Recording window
names the interpreter it settled on and prints the exact `pip install` line for it;
`GET /seriesmith/align/ready` reports the same.

---

## 2. seriesmith and the node pack

### seriesmith

```
git clone https://github.com/bgstratt/seriesmith.git C:\code\seriesmith
```

Anywhere you like (`C:\code\seriesmith` and `C:\AI\ComfyUI` in this guide are only
examples) — it does not have to live near ComfyUI. For the editor inside ComfyUI that is
all. For the editor on its own page, `run_seriesmith.bat` sets up the rest the first time
it runs. For the `seriesmith` command, set it up yourself:

```
cd C:\code\seriesmith
python -m venv .venv
.venv\Scripts\activate          (source .venv/bin/activate elsewhere)
pip install -e .
seriesmith --help
```

Local renders go straight to your ComfyUI, through its own API (`/prompt`, `/history`,
`/view`). [comfy-api-proxy](https://pypi.org/project/comfy-api-proxy/), which earlier
versions needed in front of ComfyUI, is now optional: **Settings → Through
comfy-api-proxy**, or `"local_via": "proxy"` in the settings file
([docs/SETUP.md](docs/SETUP.md)).

### The node pack

`comfy_nodes/` is seriesmith's side of ComfyUI: the shot loader and saver, the
`continuous: latent` chain, the upscale loaders and saver, and the upscale and post
compute nodes. Everything seriesmith sends a backend runs on these; they never read or
write an episode folder (files go up with each job and come back as its outputs).

**From ComfyUI-Manager** (the usual way): **Manager → Custom Nodes Manager**, search for
**seriesmith**, install the latest **nightly** (the Comfy Registry hasn't approved a
numbered release yet), restart ComfyUI (or, once one is, `comfy node install seriesmith`). Manager
installs the whole of seriesmith into `custom_nodes\seriesmith`, with comfy-sdk and
imageio-ffmpeg into ComfyUI's Python (`requirements.txt`). Nothing else is needed; the
clone above is then only for the page of its own or the command line, and
`run_seriesmith.bat` in that folder serves for those too.

**Or a clone in `custom_nodes`** (following main, or working on seriesmith): the repo is
a node pack as it stands, so clone it there and restart ComfyUI. `git pull` in it updates
what ComfyUI loads. Not both this and Manager: the two take the same folder.

```
cd C:\AI\ComfyUI\ComfyUI\custom_nodes
git clone https://github.com/bgstratt/seriesmith.git
```

Optional, what Manager would also have put in: comfy-sdk (Comfy Cloud and Router;
Settings gives the command once a key is set) and imageio-ffmpeg (an ffmpeg; Features
downloads a full one instead). Both at once, with ComfyUI's Python:
`C:\AI\ComfyUI\python_embeded\python.exe -m pip install -r seriesmith\requirements.txt`.

**Or link a clone kept elsewhere** (as `C:\code\seriesmith` above): link its `comfy_nodes`
folder into `custom_nodes`, so pulling the repo updates what ComfyUI loads.

Windows, in an ordinary (non-elevated) Command Prompt — `mklink /J` makes a directory
junction and needs no administrator rights:

```
mklink /J "C:\AI\ComfyUI\ComfyUI\custom_nodes\seriesmith" "C:\code\seriesmith\comfy_nodes"
```

PowerShell has no `mklink`; use `cmd /c mklink /J ...` or `New-Item -ItemType Junction`.
Linux/macOS:

```
ln -s /path/to/seriesmith/comfy_nodes /path/to/ComfyUI/custom_nodes/seriesmith
```

Restart ComfyUI whenever a `comfy_nodes/*.py` file changes, since ComfyUI imports the node
classes once at startup. The pack sits happily beside h3pipe's, if you keep that for
h3pipe.

### The editor inside ComfyUI

The same pack also puts seriesmith's editor inside ComfyUI: **seriesmith Shots** and
**seriesmith Refs** in the sidebar, **seriesmith Timeline** in the bottom panel. It's
the same app as `seriesmith serve`, with the same project folders, settings and queue,
and it renders on the ComfyUI it runs in. It loads seriesmith from beside the pack (the
Manager install or a clone in `custom_nodes`, or the repo the pack is linked from), on
ComfyUI's own Python. (A copied
rather than linked `comfy_nodes` folder can't find the rest; its nodes still load and the
editor stays off, and ComfyUI's console says so.) Comfy Cloud, deployments and Router run
on Comfy's SDK (comfy-sdk): Manager installs it; a clone's ComfyUI has it once its
`requirements.txt` is installed.
Once a Comfy API key is set, **Settings** says so if it's missing and gives the command
that puts it in ComfyUI's Python (`<ComfyUI's python> -m pip install
"comfy-sdk>=0.4,<0.5"`); run it and restart ComfyUI. seriesmith never installs Python
packages itself.

Inside ComfyUI, a bar on top of **seriesmith Shots** has **Render on**, the **Jobs**
button and **Settings**, as the standalone page's top bar does. The ComfyUI host keeps
its own queue journal (`queue-comfyui.json`), so it and `seriesmith serve` can run at the
same time.

### Check it

```
seriesmith backends               # each backend, and whether it answers
seriesmith backends --try local   # a picture up through ComfyUI and back
seriesmith targets                # what this ComfyUI can render, and what's missing
```

The first time either host sees ComfyUI answer, it checks which models are installed
(the same check as `seriesmith targets`). It keeps the default video and picture model
it found in the settings file (`detected_targets`) and logs them
(`seriesmith: default models: video ltx2, image krea2`).

Then `seriesmith serve` (add `--root C:\Shows` to name your project folders) and open
http://127.0.0.1:8190. Set your **project roots** — the folders holding your episodes —
in the Shots tab if you didn't pass `--root`; every episode the editor touches has to
live inside one of them. They are kept in seriesmith's folder beside its settings file
(`%APPDATA%\seriesmith\default\seriesmith\config.json`; `~/.config/seriesmith/...`
on Linux/macOS), else read from `SERIESMITH_ROOTS` (`;`-separated, `:` on Linux/macOS).

On Windows the repo has two launchers, like ComfyUI's: **`run_seriesmith.bat`** (this PC
only) and **`run_seriesmith_ext.bat`** (other devices on your network too: it listens on
every interface, `--host 0.0.0.0`, and prints the address to open on a laptop or phone).
On Linux/macOS, `./run_seriesmith.sh` (add `--ext` for the network). The first start of
any of them makes the repo's `.venv` and installs seriesmith in it. Double-click one, or make a desktop shortcut to it: it opens the editor in your browser
(`--auto-launch`) once the server is up, as ComfyUI's do. Each starts seriesmith again when the
editor's **Settings → This server → Restart** (or `seriesmith stop --restart`) asks it
to, and closes when it is stopped (**Stop**, `seriesmith stop`, or Ctrl+C, without cmd's
"Terminate batch job" question). Stop and Restart are offered only on the PC that runs
the server. The network one has no password:
anyone on that network can open your project folders, import files from the PC, see the
API key in Settings and queue paid runs, so use it on home Wi-Fi you trust and never
port-forward it. Away from home, a private network between your own devices (Tailscale)
is the safe way in: `seriesmith serve --host <the PC's Tailscale address>`.

### The upscaler (optional)

Only for upscaling takes (`seriesmith upscale`, the editor's **Upscale**, `master`); a
render never needs it. It is for takes made on `minimax_h3_ref2va`. Takes made on `ltx2`
upscale with what LTX-2 already has (its own latent upsampler), so they need nothing from
here.

**The pixel method** upscales a take on any target with an upscale model instead. Put one
or more in `models/upscale_models/` — RealESRGAN_x2 (the default: exactly 2x, gentle on
film grain) and RealESRGAN_x4 from the `xinntao/Real-ESRGAN` releases, or 4x-UltraSharp
from OpenModelDB (check its licence: it may be non-commercial). ComfyUI-Manager's Model
Manager installs them too. They load with core ComfyUI nodes.

On an NVIDIA RTX card, **RTX Video Super Resolution** can stand in for an upscale model (no
model file): install Comfy-Org's **Nvidia RTX Nodes** pack (ComfyUI-Manager: search "RTX";
it needs CUDA PyTorch cu130 or newer) and restart ComfyUI. Its `nvidia-vfx` wheel is on
NVIDIA's own index, and PyPI's is a stub that fails to install, so if ComfyUI's log says
`No module named 'nvvfx'`, install it into ComfyUI's Python and restart again:
`python_embeded\python.exe -m pip install nvidia-vfx --extra-index-url https://pypi.nvidia.com`. The Upscale dialog then lists "RTX Video Super Resolution" beside the models
(`rtx_vsr`; `rtx_vsr:HIGHBITRATE_ULTRA` for its level tuned to clean sources).

1. Clone **LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler** into `custom_nodes`:
   ```
   cd C:\AI\ComfyUI\ComfyUI\custom_nodes
   git clone https://github.com/LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler
   ```
   **Not its "Plus" fork**: that registers the same node without temporal chunking, and the
   re-sample then invents detail (sparkles on hair, marks on faces). Only one of the two can
   be installed.
2. Put `minimax_h3_latent_upscaler_3d_fp16.safetensors` in `models/latent_upscale_models/`.
   Its Hugging Face repo, LBH-123-AI/Minimax_h3_latent_Upscaler, now publishes it as
   `minimax_h3_latent_upscaler_3d_conv_v1_fp16.safetensors` (the same file): download that
   and save it under the old name (section 4, **For upscaling**, has the link).
3. Restart ComfyUI. `seriesmith targets` then prints `upscale  ready` under
   `minimax_h3_ref2va`, or names what's missing.
4. For takes longer than 5.5 s, clone **chanon/comfyui-obvpm-timeline** into `custom_nodes`
   too. Its H3 Context Windowing node samples the re-sample in overlapping windows along
   time, so a long shot at 2x (2688×1536) fits a 32 GB card; without it such an upscale says
   it needs the pack instead of running out of memory. The series' upscale recipe's
   `window` changes the length (0: off).

---

## 3. Workflows

Every target names one ComfyUI workflow, by the name it expects among ComfyUI's **saved**
workflows (`<ComfyUI>/user/default/workflows/`):

| Target | Saved workflow it looks for | Override with |
|---|---|---|
| `minimax_h3_ref2va` | `H3_Ref2VA_Shotlist_v1.json` | `$SERIESMITH_MINIMAX_H3_REF2VA_WORKFLOW` |
| `minimax_h3_fl2va` | `seriesmith_minimax_h3_fl2va.json` | `$SERIESMITH_MINIMAX_H3_FL2VA_WORKFLOW` |
| `ltx2` | `seriesmith_ltx2_5.json` | `$SERIESMITH_LTX2_WORKFLOW` |
| `ltx2_ingredients` | `seriesmith_ltx2_3_ingredients.json` | `$SERIESMITH_LTX2_INGREDIENTS_WORKFLOW` |
| `wan22_i2v` | `seriesmith_wan22_14b_i2v.json` | `$SERIESMITH_WAN22_I2V_WORKFLOW` |
| `wan22_ti2v` | `seriesmith_wan22_5b_ti2v.json` | `$SERIESMITH_WAN22_TI2V_WORKFLOW` |
| `wan22_vace` | `seriesmith_wan22_14b_vace.json` | `$SERIESMITH_WAN22_VACE_WORKFLOW` |
| `krea2` | `krea2_refs_t2i.json` | `$KREA_WORKFLOW` |
| `z_image_turbo` | `seriesmith_z_image_turbo.json` | `$SERIESMITH_Z_IMAGE_TURBO_WORKFLOW` |
| `moss_image_sft` | `seriesmith_moss_image_sft.json` | `$SERIESMITH_MOSS_IMAGE_SFT_WORKFLOW` |
| `moss_image_base` | `seriesmith_moss_image_base.json` | `$SERIESMITH_MOSS_IMAGE_BASE_WORKFLOW` |
| `flux2_klein` | `seriesmith_flux2_klein_t2i.json` | `$SERIESMITH_FLUX2_KLEIN_WORKFLOW` |
| `flux2_klein_edit` | `seriesmith_flux2_klein_edit.json` | `$SERIESMITH_FLUX2_KLEIN_EDIT_WORKFLOW` |
| `flux_kontext` | `seriesmith_flux_kontext.json` | `$SERIESMITH_FLUX_KONTEXT_WORKFLOW` |
| `minimax_h3_still` | `seriesmith_minimax_h3_still.json` | `$SERIESMITH_MINIMAX_H3_STILL_WORKFLOW` |
| `qwen_image_21` | `seriesmith_qwen_image_21.json` | `$SERIESMITH_QWEN_IMAGE_21_WORKFLOW` |
| `qwen_rapid_aio` | `seriesmith_qwen_rapid_aio.json` | `$SERIESMITH_QWEN_RAPID_AIO_WORKFLOW` |
| `klein_erp_360` | `seriesmith_klein_erp_360.json` | `$SERIESMITH_KLEIN_ERP_360_WORKFLOW` |
| `ltx2_voice` | `seriesmith_ltx2_voice.json` | `$SERIESMITH_LTX2_VOICE_WORKFLOW` |

**You usually need to do nothing.** The lookup order is:

1. `--workflow <path>` on the command line
2. the target's environment variable, if it points at a file
3. the workflow of that name **as saved in the running ComfyUI** (fetched over its API, so
   it always matches your node versions)
4. `$COMFYUI_PATH\user\default\workflows\<name>`
5. **the copy in this repo**, `targets/<kind>/<id>/workflow.json`

Step 5 is why a fresh install renders without you saving anything. The repo copies are
checked in and kept working.

Saving a workflow in ComfyUI under the expected name is how you take over: from then on
that graph is what renders, and it is a ComfyUI-native way to change the sampler,
scheduler, or splice in a LoRA without touching Python. Keep the saved
`krea2_refs_t2i.json` free of style LoRAs (experiment under another name) — the reference
images have to follow the look your series config describes.

Two targets bend the order slightly:

- **`krea2`** has one more fallback: finding no file at all, it uses a built-in Krea 2
  turbo graph (`seriesmith/targets/image/krea2/graph.py`). `--no-workflow` forces that.
- **`ltx2_voice`** (and any audio target) puts the repo copy *ahead* of `$COMFYUI_PATH`,
  because no saved canvas is likely to hold an audio-only LTX graph and one of that name
  would be somebody's experiment. The running ComfyUI's saved copy still wins.

The editor's location **tour** isn't a target: it runs `seriesmith/workflows/h3_tour.json` (H3 FL2VA
from the plate) from the repo, and needs H3 FL2VA's models and the PlagueKind pack.

`seriesmith render <episode> --only sh010 --dry-run` writes the graph a shot would send,
running nothing; `seriesmith targets` asks the running ComfyUI whether it knows every node
each target uses — worth running once after a ComfyUI update.

---

## 4. Models

Put each file in the ComfyUI models folder named beside it, e.g.
`C:\AI\ComfyUI\ComfyUI\models\diffusion_models\`. ComfyUI also accepts `models\unet\` for
`diffusion_models` and `models\clip\` for `text_encoders`.

**Check before you download.** With ComfyUI running:

```
seriesmith targets
```

prints one line per target — `ready`, `degraded`, `not_ready` or `unknown` — and under it
every file it cannot find, with the folder it belongs in and the download link. `--kind
video`, `--kind image` or `--kind audio` narrows it; `--json` prints data. In the editor,
the model pickers and the **Models** window (the button beside each picker) show the same
thing. A file you already have under another name usually still counts: seriesmith
identifies models by family (names first, then the safetensors header), so a re-quantized
or renamed copy of the same model is accepted and the take's sidecar records what was
actually used.

**Hosted models need no files.** The Comfy Router targets (`seedance_2_5`,
`krea_2_router`, `nano_banana_pro`, ...) run on Router with your API key, so nothing
below applies to them.

**Nodes count too.** Some targets need node classes as well as files. Most are core
ComfyUI (MiniMax H3 FL2VA's `MiniMaxH3AddGuide`, the Wan 2.2 and LTX-2.5 video graphs);
the rest come from the [optional packs](#optional-node-packs) in section 1.
`seriesmith targets` lists a missing one as `node <Class> (update ComfyUI, or install the node
pack)`.

The list below is generated from the targets themselves
(`python tools/make_models_md.py`), so it cannot drift from what the code asks ComfyUI to
load. No URL is guessed: a file whose download record has no trustworthy source is listed
as having none.

<!-- BEGIN MODELS (generated by tools/make_models_md.py — do not edit) -->

### The minimum set

The two default targets — `minimax_h3_ref2va` (the video model every shot renders on unless the script says otherwise) and `krea2` (the image model that draws the character sheets, props and location plates) — need 7 required files:

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | `models/text_encoders/` | required | `minimax_h3_ref2va` | [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors) |
| `minimax_h3_video_vae_fp16.safetensors` | `models/vae/` | required | `minimax_h3_ref2va` | [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/vae/minimax_h3_video_vae_fp16.safetensors) |
| `minimax_h3_audio_vae_fp32.safetensors` | `models/vae/` | required | `minimax_h3_ref2va` | [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/vae/minimax_h3_audio_vae_fp32.safetensors) |
| `minimax_h3_ref2va_pruned_int8_convrot.safetensors` | `models/diffusion_models/` | required | `minimax_h3_ref2va` | [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors) |
| `wan_2.1_vae.safetensors` | `models/vae/` | required | `krea2` | [Comfy-Org/Wan_2.2_ComfyUI_Repackaged](https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors) |
| `krea2_turbo_fp8_scaled.safetensors` | `models/diffusion_models/` | required | `krea2` | [Comfy-Org/Krea-2](https://huggingface.co/Comfy-Org/Krea-2/resolve/main/diffusion_models/krea2_turbo_fp8_scaled.safetensors) |
| `qwen3vl_4b_fp8_scaled.safetensors` | `models/text_encoders/` | required | `krea2` | [Comfy-Org/Krea-2](https://huggingface.co/Comfy-Org/Krea-2/resolve/main/text_encoders/qwen3vl_4b_fp8_scaled.safetensors) |

Plus, for those two targets:

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `minimax_h3_ref2v_lightx2v_turbo_4step_v0.1_resized_avg_rank_20_bf16.safetensors` | `models/loras/` | accelerator | `minimax_h3_ref2va` | [Kijai/MiniMax-H3_comfy](https://huggingface.co/Kijai/MiniMax-H3_comfy/resolve/main/loras/minimax_h3_ref2v_lightx2v_turbo_4step_v0.1_resized_avg_rank_20_bf16.safetensors) |
| `minimax_h3_ref2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors` | `models/loras/` | accelerator | `minimax_h3_ref2va` | [lightx2v/Minimax-h3-Turbo](https://huggingface.co/lightx2v/Minimax-h3-Turbo/resolve/main/minimax_h3_ref2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors) |

An **accelerator** is a turbo/distilled LoRA or checkpoint: without it the pass still renders, on its slower `base` preset (more steps, no LoRA), and the take's sidecar says so. A **required** file missing skips the shot. An **optional** file only switches off the feature named beside it.

### Everything, by model family

Every file any target names. `seriesmith targets` tells you which of these your ComfyUI is actually missing — you only need the families of the targets you use.

**FastH3 Omni (FastVideo's 8-step H3)** (`fasth3-omni`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `fasth3_omniref_8step_pruned_int8_convrot.safetensors` | `models/diffusion_models/` | required | `fasth3_omni`, `fasth3_omni_still` | [FastVideo/FastH3-Omni-Comfy](https://huggingface.co/FastVideo/FastH3-Omni-Comfy/resolve/main/diffusion_models/fasth3_omniref_8step_pruned_int8_convrot.safetensors) |

**Qwen3-VL 32B (MiniMax H3's text encoder)** (`qwen3vl-32b`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | `models/text_encoders/` | required | `fasth3_omni`, `h3_singularity`, `minimax_h3_fl2va`, `minimax_h3_ref2va`, `fasth3_omni_still`, `minimax_h3_still` | [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors) |

**MiniMax H3 video VAE** (`minimax-h3-video-vae`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `minimax_h3_video_vae_fp16.safetensors` | `models/vae/` | required | `fasth3_omni`, `h3_singularity`, `minimax_h3_fl2va`, `minimax_h3_ref2va`, `fasth3_omni_still`, `minimax_h3_still` | [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/vae/minimax_h3_video_vae_fp16.safetensors) |

**MiniMax H3 audio VAE** (`minimax-h3-audio-vae`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `minimax_h3_audio_vae_fp32.safetensors` | `models/vae/` | required | `fasth3_omni`, `h3_singularity`, `minimax_h3_fl2va`, `minimax_h3_ref2va` | [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/vae/minimax_h3_audio_vae_fp32.safetensors) |

**MiniMax H3 Ref2VA** (`minimax-h3-ref2va`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `Minimax-h3_Singularity_ref2va_v2_pruned_int8.safetensors` | `models/diffusion_models/` | required | `h3_singularity` | [WarmBloodAban/Minimax-h3_Singularity](https://huggingface.co/WarmBloodAban/Minimax-h3_Singularity/resolve/main/Minimax-h3_Singularity_ref2va_v2_pruned_int8.safetensors) |
| `minimax_h3_ref2va_pruned_int8_convrot.safetensors` | `models/diffusion_models/` | required | `minimax_h3_ref2va`, `minimax_h3_still` | [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors) |

**MiniMax H3 Ref2V turbo LoRA** (`minimax-h3-ref2v-turbo-lora`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `minimax_h3_ref2v_lightx2v_turbo_4step_v0.1_resized_avg_rank_20_bf16.safetensors` | `models/loras/` | accelerator | `h3_singularity`, `minimax_h3_ref2va` | [Kijai/MiniMax-H3_comfy](https://huggingface.co/Kijai/MiniMax-H3_comfy/resolve/main/loras/minimax_h3_ref2v_lightx2v_turbo_4step_v0.1_resized_avg_rank_20_bf16.safetensors) |
| `minimax_h3_ref2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors` | `models/loras/` | accelerator | `h3_singularity`, `minimax_h3_ref2va`, `minimax_h3_still` | [lightx2v/Minimax-h3-Turbo](https://huggingface.co/lightx2v/Minimax-h3-Turbo/resolve/main/minimax_h3_ref2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors) |

**LTX 2.5** (`ltx2.5`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors` | `models/diffusion_models/` | required | `ltx2` (accelerator), `ltx2_msr`, `minimax_h3_fl2va` (optional: clone, its lines made by LTX-2.5 audio-only), `ltx2_voice` (accelerator) | [Lightricks/LTX-2.5](https://huggingface.co/Lightricks/LTX-2.5/resolve/main/diffusion_models/ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors) |
| `ltx-2.5-22b-dev-transformer-comfy-int8-convrot.safetensors` | `models/diffusion_models/` | accelerator | `ltx2`, `ltx2_voice` | [Lightricks/LTX-2.5](https://huggingface.co/Lightricks/LTX-2.5/resolve/main/diffusion_models/ltx-2.5-22b-dev-transformer-comfy-int8-convrot.safetensors) |

**Gemma 4 12B with the LTX 2.5 projection** (`ltx2.5-text-encoder`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors` | `models/text_encoders/` | required | `ltx2`, `ltx2_msr`, `minimax_h3_fl2va` (optional: clone, its lines made by LTX-2.5 audio-only), `ltx2_voice` | [Lightricks/LTX-2.5](https://huggingface.co/Lightricks/LTX-2.5/resolve/main/text_encoders/gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors) |

**LTX 2.5 video VAE** (`ltx2.5-video-vae`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `ltx-2.5-video-vae-bf16.safetensors` | `models/vae/` | required | `ltx2`, `ltx2_msr` | [Lightricks/LTX-2.5](https://huggingface.co/Lightricks/LTX-2.5/resolve/main/vae/ltx-2.5-video-vae-bf16.safetensors) |

**LTX 2.5 audio VAE** (`ltx2.5-audio-vae`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `ltx-2.5-audio-vae-bf16.safetensors` | `models/vae/` | required | `ltx2`, `ltx2_msr`, `minimax_h3_fl2va` (optional: clone, its lines made by LTX-2.5 audio-only), `ltx2_voice` | [Lightricks/LTX-2.5](https://huggingface.co/Lightricks/LTX-2.5/resolve/main/vae/ltx-2.5-audio-vae-bf16.safetensors) |

**LTX 2.5 latent upscaler** (`ltx2.5-latent-upscaler`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors` | `models/latent_upscale_models/` | required | `ltx2`, `ltx2_msr` | [Lightricks/LTX-2.5](https://huggingface.co/Lightricks/LTX-2.5/resolve/main/latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors) |

**LTX 2.5 duration head** (`ltx2.5-duration-head`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `ltx-2.5-duration-head-bf16.safetensors` | `models/model_patches/` | optional — dur: model (duration head) | `ltx2` | [Lightricks/LTX-2.5](https://huggingface.co/Lightricks/LTX-2.5/resolve/main/model_patches/ltx-2.5-duration-head-bf16.safetensors) |

**LTX 2.5 ingredients IC-LoRA** (`ltx2.5-ic-lora-ingredients`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `ltx-2.5-22b-ic-lora-ingredients-0.9.safetensors` | `models/loras/` | optional — reference sheets (LTX-2.5 ingredients IC-LoRA) | `ltx2` | [Lightricks/LTX-2.5-22b-IC-LoRA-Ingredients](https://huggingface.co/Lightricks/LTX-2.5-22b-IC-LoRA-Ingredients/resolve/main/ltx-2.5-22b-ic-lora-ingredients-0.9.safetensors) |

**LTX 2.3** (`ltx2.3`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `ltx-2.3-22b-dev-fp8.safetensors` | `models/checkpoints/` | accelerator | `ltx2_ingredients` | [Lightricks/LTX-2.3-fp8](https://huggingface.co/Lightricks/LTX-2.3-fp8/resolve/main/ltx-2.3-22b-dev-fp8.safetensors) |
| `ltx-2.3-22b-distilled-fp8.safetensors` | `models/checkpoints/` | accelerator | `ltx2_ingredients` | [Lightricks/LTX-2.3-fp8](https://huggingface.co/Lightricks/LTX-2.3-fp8/resolve/main/ltx-2.3-22b-distilled-fp8.safetensors) |

**LTX 2.3 ingredients IC-LoRA** (`ltx2.3-ic-lora-ingredients`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `ltx-2.3-22b-ic-lora-ingredients-0.9.safetensors` | `models/loras/` | required | `ltx2_ingredients` | [Comfy-Org/ltx-2.3](https://huggingface.co/Comfy-Org/ltx-2.3/resolve/main/split_files/loras/ltx-2.3-22b-ic-lora-ingredients-0.9.safetensors) |

**Gemma 3 12B (LTX 2.3's text encoder)** (`gemma3-12b`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `gemma_3_12B_it_fp4_mixed.safetensors` | `models/text_encoders/` | required | `ltx2_ingredients` | [Comfy-Org/ltx-2](https://huggingface.co/Comfy-Org/ltx-2/resolve/main/split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors) |

**ltx2.5-msr** (`ltx2.5-msr`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `LTX-2.5-Licon-MSR-V2.safetensors` | `models/loras/` | required | `ltx2_msr` | [LiconStudio/LTX-2.5-Multiple-Subject-Reference](https://huggingface.co/LiconStudio/LTX-2.5-Multiple-Subject-Reference/resolve/main/LTX-2.5-Licon-MSR-V2.safetensors) |

**MiniMax H3 FL2VA** (`minimax-h3-fl2va`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `minimax_h3_fl2va_pruned_int8_convrot.safetensors` | `models/diffusion_models/` | required | `minimax_h3_fl2va` | [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors) |

**MiniMax H3 FL2V turbo LoRA** (`minimax-h3-fl2v-turbo-lora`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors` | `models/loras/` | accelerator | `minimax_h3_fl2va` | [Kijai/MiniMax-H3_comfy](https://huggingface.co/Kijai/MiniMax-H3_comfy/resolve/main/loras/minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors) |
| `minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors` | `models/loras/` | accelerator | `minimax_h3_fl2va` | [lightx2v/Minimax-h3-Turbo](https://huggingface.co/lightx2v/Minimax-h3-Turbo/resolve/main/minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors) |

**Wan 2.2 I2V 14B high-noise** (`wan2.2-i2v-14b-high`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors` | `models/diffusion_models/` | required | `wan22_i2v` | [Comfy-Org/Wan_2.2_ComfyUI_Repackaged](https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors) |

**Wan 2.2 I2V 14B low-noise** (`wan2.2-i2v-14b-low`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors` | `models/diffusion_models/` | required | `wan22_i2v` | [Comfy-Org/Wan_2.2_ComfyUI_Repackaged](https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors) |

**Wan 2.2 I2V lightx2v 4-step LoRA** (`wan2.2-i2v-lightx2v-lora`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors` | `models/loras/` | accelerator | `wan22_i2v` | [Comfy-Org/Wan_2.2_ComfyUI_Repackaged](https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors) |
| `wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors` | `models/loras/` | accelerator | `wan22_i2v` | [Comfy-Org/Wan_2.2_ComfyUI_Repackaged](https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors) |

**UMT5-XXL (Wan's text encoder)** (`umt5-xxl`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `umt5_xxl_fp8_e4m3fn_scaled.safetensors` | `models/text_encoders/` | required | `wan22_i2v`, `wan22_ti2v`, `wan22_vace` | [Comfy-Org/Wan_2.1_ComfyUI_repackaged](https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors) |

**Wan 2.1 VAE** (`wan2.1-vae`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `wan_2.1_vae.safetensors` | `models/vae/` | required | `wan22_i2v`, `wan22_vace`, `krea2` | [Comfy-Org/Wan_2.2_ComfyUI_Repackaged](https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors) |

**Wan 2.2 TI2V 5B** (`wan2.2-ti2v-5b`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `wan2.2_ti2v_5B_fp16.safetensors` | `models/diffusion_models/` | required | `wan22_ti2v` | [Comfy-Org/Wan_2.2_ComfyUI_Repackaged](https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_ti2v_5B_fp16.safetensors) |

**Wan 2.2 VAE** (`wan2.2-vae`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `wan2.2_vae.safetensors` | `models/vae/` | required | `wan22_ti2v` | [Comfy-Org/Wan_2.2_ComfyUI_Repackaged](https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/vae/wan2.2_vae.safetensors) |

**Wan 2.2 Fun VACE 14B high-noise** (`wan2.2-vace-14b-high`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `wan2.2_fun_vace_high_noise_14B_fp8_scaled.safetensors` | `models/diffusion_models/` | required | `wan22_vace` | [Comfy-Org/Wan_2.2_ComfyUI_Repackaged](https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_fun_vace_high_noise_14B_fp8_scaled.safetensors) |

**Wan 2.2 Fun VACE 14B low-noise** (`wan2.2-vace-14b-low`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `wan2.2_fun_vace_low_noise_14B_fp8_scaled.safetensors` | `models/diffusion_models/` | required | `wan22_vace` | [Comfy-Org/Wan_2.2_ComfyUI_Repackaged](https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/diffusion_models/wan2.2_fun_vace_low_noise_14B_fp8_scaled.safetensors) |

**Wan 2.2 T2V lightx2v 4-step LoRA** (`wan2.2-t2v-lightx2v-lora`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `wan2.2_t2v_lightx2v_4steps_lora_250928_high_noise.safetensors` | `models/loras/` | accelerator | `wan22_vace` | [lightx2v/Wan2.2-Lightning](https://huggingface.co/lightx2v/Wan2.2-Lightning/resolve/main/Wan2.2-T2V-A14B-4steps-lora-250928/high_noise_model.safetensors) |
| `wan2.2_t2v_lightx2v_4steps_lora_250928_low_noise.safetensors` | `models/loras/` | accelerator | `wan22_vace` | [lightx2v/Wan2.2-Lightning](https://huggingface.co/lightx2v/Wan2.2-Lightning/resolve/main/Wan2.2-T2V-A14B-4steps-lora-250928/low_noise_model.safetensors) |

**Fibo 2.0 Dev** (`fibo2-dev`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `fibo2_dev_bf16.safetensors` | `models/diffusion_models/` | required | `fibo2_dev` | [Comfy-Org/Fibo-2.0](https://huggingface.co/Comfy-Org/Fibo-2.0/resolve/main/diffusion_models/fibo2_dev_bf16.safetensors) |

**Qwen3-VL 4B (Krea 2's, FLUX.3 Klein's and Fibo 2.0's text encoder)** (`qwen3vl-4b`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `qwen3vl_4b_fp8_scaled.safetensors` | `models/text_encoders/` | required | `krea2` | [Comfy-Org/Krea-2](https://huggingface.co/Comfy-Org/Krea-2/resolve/main/text_encoders/qwen3vl_4b_fp8_scaled.safetensors) |
| `qwen3vl_4b_int8_convrot.safetensors` | `models/text_encoders/` | required | `fibo2_dev`, `fibo2_edit_turbo`, `flux3_klein`, `flux3_klein_turbo` | [Comfy-Org/Fibo-2.0](https://huggingface.co/Comfy-Org/Fibo-2.0/resolve/main/text_encoders/qwen3vl_4b_int8_convrot.safetensors) |

**FLUX.2 VAE** (`flux2-vae`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `flux2-vae.safetensors` | `models/vae/` | required | `fibo2_dev`, `fibo2_edit_turbo`, `flux2_klein_edit`, `flux3_klein`, `flux3_klein_turbo`, `klein_erp_360`, `moss_image_base`, `moss_image_sft` | [Comfy-Org/flux2-dev](https://huggingface.co/Comfy-Org/flux2-dev/resolve/main/split_files/vae/flux2-vae.safetensors) |
| `full_encoder_small_decoder.safetensors` | `models/vae/` | required | `flux2_klein` | [black-forest-labs/FLUX.2-small-decoder](https://huggingface.co/black-forest-labs/FLUX.2-small-decoder/resolve/main/full_encoder_small_decoder.safetensors) |

**Fibo 2.0 Edit Turbo** (`fibo2-edit-turbo`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `fibo2_edit_turbo_bf16.safetensors` | `models/diffusion_models/` | required | `fibo2_edit_turbo` | [Comfy-Org/Fibo-2.0](https://huggingface.co/Comfy-Org/Fibo-2.0/resolve/main/diffusion_models/fibo2_edit_turbo_bf16.safetensors) |

**FLUX.2 Klein 9B** (`flux2-klein-9b`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `flux-2-klein-9b-kv.safetensors` | `models/diffusion_models/` | accelerator | `flux2_klein`, `flux2_klein_edit` | [black-forest-labs/FLUX.2-klein-9b-kv](https://huggingface.co/black-forest-labs/FLUX.2-klein-9b-kv/resolve/main/flux-2-klein-9b-kv.safetensors) |
| `flux-2-klein-base-9b-fp8.safetensors` | `models/diffusion_models/` | accelerator | `flux2_klein`, `flux2_klein_edit` | [black-forest-labs/FLUX.2-klein-base-9b-fp8](https://huggingface.co/black-forest-labs/FLUX.2-klein-base-9b-fp8/resolve/main/flux-2-klein-base-9b-fp8.safetensors) |

**Qwen3 8B (FLUX.2 Klein 9B's text encoder)** (`qwen3-8b`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `qwen_3_8b_fp8mixed.safetensors` | `models/text_encoders/` | required | `flux2_klein`, `flux2_klein_edit`, `klein_erp_360` | [Comfy-Org/flux2-klein-9B](https://huggingface.co/Comfy-Org/flux2-klein-9B/resolve/main/split_files/text_encoders/qwen_3_8b_fp8mixed.safetensors) |

**FLUX.3 Image Klein** (`flux3-klein`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `flux3_image_klein_int8_convrot.safetensors` | `models/diffusion_models/` | required | `flux3_klein` | [black-forest-labs/flux-3-image-klein-comfy](https://huggingface.co/black-forest-labs/flux-3-image-klein-comfy/resolve/main/diffusion_models/flux3_image_klein_int8_convrot.safetensors) |

**FLUX.3 Image Klein step-distilled (turbo)** (`flux3-klein-distilled`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `flux3_image_klein_sd_int8_convrot.safetensors` | `models/diffusion_models/` | required | `flux3_klein_turbo` | [black-forest-labs/flux-3-image-klein-comfy](https://huggingface.co/black-forest-labs/flux-3-image-klein-comfy/resolve/main/diffusion_models/flux3_image_klein_sd_int8_convrot.safetensors) |

**FLUX.1 Kontext dev** (`flux1-kontext-dev`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `flux1-dev-kontext_fp8_scaled.safetensors` | `models/diffusion_models/` | required | `flux_kontext` | [Comfy-Org/flux1-kontext-dev_ComfyUI](https://huggingface.co/Comfy-Org/flux1-kontext-dev_ComfyUI/resolve/main/split_files/diffusion_models/flux1-dev-kontext_fp8_scaled.safetensors) |

**CLIP-L** (`clip-l`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `clip_l.safetensors` | `models/text_encoders/` | required | `flux_kontext` | [comfyanonymous/flux_text_encoders](https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors) |

**T5-XXL (FLUX.1's text encoder)** (`t5-xxl`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `t5xxl_fp16.safetensors` | `models/text_encoders/` | required | `flux_kontext` | [comfyanonymous/flux_text_encoders](https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp16.safetensors) |

**FLUX.1 VAE (ae)** (`flux1-vae`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `ae.safetensors` | `models/vae/` | required | `flux_kontext`, `z_image_turbo` | [Comfy-Org/Lumina_Image_2.0_Repackaged](https://huggingface.co/Comfy-Org/Lumina_Image_2.0_Repackaged/resolve/main/split_files/vae/ae.safetensors) |

**FLUX.2 Klein 9B base** (`flux2-klein-9b-base`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `flux-2-klein-base-9b-fp8.safetensors` | `models/diffusion_models/` | required | `klein_erp_360` | [black-forest-labs/FLUX.2-klein-base-9b-fp8](https://huggingface.co/black-forest-labs/FLUX.2-klein-base-9b-fp8/resolve/main/flux-2-klein-base-9b-fp8.safetensors) |

**Krea 2** (`krea2`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `krea2_turbo_fp8_scaled.safetensors` | `models/diffusion_models/` | required | `krea2` | [Comfy-Org/Krea-2](https://huggingface.co/Comfy-Org/Krea-2/resolve/main/diffusion_models/krea2_turbo_fp8_scaled.safetensors) |

**MOSS-Image Base** (`moss-image-base`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `moss_image_base_int8_convrot.safetensors` | `models/diffusion_models/` | required | `moss_image_base` | [Comfy-Org/MOSS-Image](https://huggingface.co/Comfy-Org/MOSS-Image/resolve/main/diffusion_models/moss_image_base_int8_convrot.safetensors) |

**Qwen3.5 9B (MOSS-Image's text encoder)** (`qwen3.5-9b`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `qwen3.5_9b_int8_convrot.safetensors` | `models/text_encoders/` | required | `moss_image_base`, `moss_image_sft` | [Comfy-Org/MOSS-Image](https://huggingface.co/Comfy-Org/MOSS-Image/resolve/main/text_encoders/qwen3.5_9b_int8_convrot.safetensors) |

**MOSS-Image SFT** (`moss-image-sft`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `moss_image_sft_int8_convrot.safetensors` | `models/diffusion_models/` | required | `moss_image_sft` | [Comfy-Org/MOSS-Image](https://huggingface.co/Comfy-Org/MOSS-Image/resolve/main/diffusion_models/moss_image_sft_int8_convrot.safetensors) |

**Qwen-Image 2.1** (`qwen-image-2.1`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `qwen_image_2.1_int8_convrot.safetensors` | `models/diffusion_models/` | required | `qwen_image_21` | [Comfy-Org/Qwen-Image-2.1](https://huggingface.co/Comfy-Org/Qwen-Image-2.1/resolve/main/diffusion_models/qwen_image_2.1_int8_convrot.safetensors) |

**Qwen3-VL 8B (Qwen-Image 2.1's text encoder)** (`qwen3vl-8b`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `qwen3vl_8b_int8_convrot.safetensors` | `models/text_encoders/` | required | `qwen_image_21` | [Comfy-Org/Qwen-Image-2.1](https://huggingface.co/Comfy-Org/Qwen-Image-2.1/resolve/main/text_encoders/qwen3vl_8b_int8_convrot.safetensors) |

**Qwen-Image 2.1 VAE** (`qwen-image-2.1-vae`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `qwen_image_2.1_vae_bf16.safetensors` | `models/vae/` | required | `qwen_image_21` | [Comfy-Org/Qwen-Image-2.1](https://huggingface.co/Comfy-Org/Qwen-Image-2.1/resolve/main/vae/qwen_image_2.1_vae_bf16.safetensors) |

**Qwen-Image-Edit Rapid AIO** (`qwen-rapid-aio`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `Qwen-Rapid-AIO-SFW-v19.safetensors` | `models/checkpoints/` | required | `qwen_rapid_aio` | [Phr00t/Qwen-Image-Edit-Rapid-AIO](https://huggingface.co/Phr00t/Qwen-Image-Edit-Rapid-AIO/resolve/main/v19/Qwen-Rapid-AIO-SFW-v19.safetensors) |

**Z-Image Turbo** (`z-image-turbo`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `z_image_turbo_bf16.safetensors` | `models/diffusion_models/` | required | `z_image_turbo` | [Comfy-Org/z_image_turbo](https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/diffusion_models/z_image_turbo_bf16.safetensors) |

**Qwen3 4B (Z-Image's text encoder)** (`qwen3-4b`)

| File | ComfyUI folder | Tier | Targets | Download |
|---|---|---|---|---|
| `qwen_3_4b.safetensors` | `models/text_encoders/` | required | `z_image_turbo` | [Comfy-Org/z_image_turbo](https://huggingface.co/Comfy-Org/z_image_turbo/resolve/main/split_files/text_encoders/qwen_3_4b.safetensors) |

### For upscaling (optional)

Only to upscale takes (`seriesmith upscale`), never to render. H3's MinimaxH3LatentUpscaler3D comes from the Comfyui_Minimax_h3_latent_Upscaler pack (LBH-123-AI) — not its "Plus" fork, which has the same node without temporal chunking; LTX's LTXVLatentUpsampler is ComfyUI's own. `seriesmith targets` says whether this ComfyUI can upscale.

- `minimax_h3_latent_upscaler_3d_fp16.safetensors` → `models/latent_upscale_models/` (MinimaxH3LatentUpscaler3D, for `fasth3_omni`, `h3_singularity`, `minimax_h3_fl2va`, `minimax_h3_ref2va`) — [download](https://huggingface.co/LBH-123-AI/Minimax_h3_latent_Upscaler/resolve/main/minimax_h3_latent_upscaler_3d_conv_v1/minimax_h3_latent_upscaler_3d_conv_v1_fp16.safetensors) (the Hugging Face repo LBH-123-AI/Minimax_h3_latent_Upscaler, which now publishes it as minimax_h3_latent_upscaler_3d_conv_v1/minimax_h3_latent_upscaler_3d_conv_v1_fp16.safetensors (the same file: sha256 043e5a48e161..., checked 2026-10-09): save it under this name. Only needed to upscale, never to render.)
- `ltx-2.3-spatial-upscaler-x2-1.1.safetensors` → `models/latent_upscale_models/` (LTXVLatentUpsampler, for `ltx2_ingredients`) — [download](https://huggingface.co/Lightricks/LTX-2.3/resolve/main/ltx-2.3-spatial-upscaler-x2-1.1.safetensors) (ComfyUI-Manager model list (model-list.json; ComfyUI's blueprint Image to Video (LTX-2.3).json has the same URL). Only needed to upscale, never to render.)

**SeedVR2** (any take; ComfyUI's own nodes, the models Apache 2.0): the VAE and at least one model.

- `seedvr2_ema_vae_fp16.safetensors` → `models/vae/` — [download](https://huggingface.co/Comfy-Org/SeedVR2/resolve/main/vae/seedvr2_ema_vae_fp16.safetensors) (ComfyUI templates utility_seedvr2_3b_int8_upscale_video.json / utility_seedvr2_7b_int8_upscale_image.json (properties.models))
- `seedvr2_7b_int8_convrot.safetensors` → `models/diffusion_models/` — [download](https://huggingface.co/Comfy-Org/SeedVR2/resolve/main/diffusion_models/seedvr2_7b_int8_convrot.safetensors) (ComfyUI templates utility_seedvr2_3b_int8_upscale_video.json / utility_seedvr2_7b_int8_upscale_image.json (properties.models))
- `seedvr2_3b_int8_convrot.safetensors` → `models/diffusion_models/` — [download](https://huggingface.co/Comfy-Org/SeedVR2/resolve/main/diffusion_models/seedvr2_3b_int8_convrot.safetensors) (ComfyUI templates utility_seedvr2_3b_int8_upscale_video.json / utility_seedvr2_7b_int8_upscale_image.json (properties.models))

- `ltx2`: nothing extra. Its render already has a latent upsampler, and an upscale runs that second stage again on the take
- `wan22_i2v`: an upscale model from `models/upscale_models/` (RealESRGAN_x2.pth by default), then its own sampler
- `wan22_ti2v`: an upscale model from `models/upscale_models/` (RealESRGAN_x2.pth by default), then its own sampler
- `wan22_vace`: an upscale model from `models/upscale_models/` (RealESRGAN_x2.pth by default), then its own sampler

<!-- END MODELS -->

### For the editor's 360s and turned views (optional)

Three LoRAs the Refs tab uses, outside any target's list above. Each goes in
`models/loras/`. Only the button that uses one needs it; without it, that job fails on the
missing file.

| File | Used by | Download |
|---|---|---|
| `flux-2-klein-9B-360-erp-outpaint-lora_V1.safetensors` | **Make 360** on Klein (the default engine; the `klein_erp_360` target, with FLUX.2 Klein 9B base) | [nomadoor/flux-2-klein-9B-360-erp-outpaint-lora](https://huggingface.co/nomadoor/flux-2-klein-9B-360-erp-outpaint-lora/resolve/main/flux-2-klein-9B-360-erp-outpaint-lora_V1.safetensors) |
| `pano360_qwen21_edit_v1.safetensors` | **Make 360** on Qwen-Image 2.1 | [Gogodr/qwen-image-2.1-edit-pano360-lora](https://huggingface.co/Gogodr/qwen-image-2.1-edit-pano360-lora/resolve/main/pano360_qwen21_edit_v1.safetensors) |
| `angles_v2_full_qwen21_multiple_angles_v2_qwen21_multiple_angles_v2_000001500.safetensors` | a character view's **Turn** (Qwen-Image 2.1's multi-angle LoRA; characters only: it turns a location into a diorama) | [akhaliq/Qwen-Image-2.1-Multiple-Angles-LoRA](https://huggingface.co/akhaliq/Qwen-Image-2.1-Multiple-Angles-LoRA/resolve/main/checkpoints_v2/angles_v2_full_qwen21_multiple_angles_v2_qwen21_multiple_angles_v2_000001500.safetensors) (`checkpoints_v2/`) |

---

## 5. First run

An **episode** is one folder holding a series config and a script. Everything else in it
is generated.

```
Shows\
  MyShow\
    refs\            the pictures, shared by every episode (`../refs/...` in the configs)
    ep01\
      series.json    the series config: the look, the cast, the locations, the voices
      ep01.md        the script
    ep02\
      series.json    its own, so this episode can add a character
      ep02.md
```

Two rules that save an hour of confusion:

- The script should be named after its folder — `ep01\ep01.md`. Any other single `.md` in
  the folder is accepted, but two of them and nothing can tell which is the script.
- `series.json` goes **in the episode folder**. `seriesmith build` and `check` insist on it;
  the editor falls back to a config in the parent folder.

You don't have to type either file: `seriesmith new Shows\MyShow\ep02` writes both,
starting from the episode beside it (its cast, look and profiles) or from
`examples/starter/` when the show is new. **New episode…** in the editor's project folders
does the same.

### Something to copy from

- `examples/starter/` — the smallest correct pair: one character, one prop, one location,
  three shots. It is what `seriesmith new` writes and what **Your first episode** in the
  authoring guide quotes, so it builds with no warnings as it stands.
- `examples/series_example.json` and `examples/script_example.md` — a full three-sequence
  episode with props, a voice-only character and `audio:` windows. Note that it is written
  for a **recorded** dialogue mix (`audio.mode: source_track`), so its dialogue shots stay
  blocked until you supply `audio/ep01_dialogue_mix.wav` or change the mode.
- `tests/fixtures/kitchen_sink/` and `tests/fixtures/mixed/` — small episodes that
  exercise most of the format, including shots retargeted onto other models.
- [docs/AUTHORING.md](docs/AUTHORING.md) is the format itself: every field, the frame
  grids, the syllable budget, how to break a scene into shots.
- To draft with an AI assistant, the guide comes as a skill:
  `prompts/seriesmith-episode-script.zip` (in the repo, and in a Manager install's
  `custom_nodes\seriesmith\prompts\`). Upload it in Claude (Settings → Skills →
  Upload a skill), or unzip it into `.claude/skills/` for Claude Code. It carries the build, so the
  assistant can check a script with nothing installed.

### A first episode

```
seriesmith new Shows\ep01 --title "First Light"
seriesmith build Shows\ep01
```

That writes the two files (the starter pair) and compiles them. Writing your own is the
authoring guide's job, not this one's: [docs/AUTHORING.md](docs/AUTHORING.md) opens with
**Your first episode** — the same pair, field by field. Come back here for the commands
that render it.

### The command line

Each command runs its jobs on a queue of its own and waits for them; `--backend NAME`
sends them somewhere other than each target's own (usually `local`).

```
seriesmith targets                      # what this ComfyUI can render (ComfyUI must be up)
seriesmith check    Shows\ep01          # validate + dialogue pacing; writes nothing
seriesmith build    Shows\ep01          # story IR, shotlists (final AND proxy), refs_todo
seriesmith refs     Shows\ep01 --list   # the reference images it would draw
seriesmith refs     Shows\ep01          # draw them
seriesmith supply   Shows\ep01 C:\sheets --dry-run
                                          # pictures you already have: which ref each file
                                          # name means (drop --dry-run to put them in)
seriesmith render   Shows\ep01 --proxy  # queue the shots, one take each -> renders_proxy\
seriesmith assemble Shows\ep01 --proxy  # join them -> renders_proxy\ep01_proxy.mp4
```

Then the full-size pass, once the animatic reads right:

```
seriesmith render   Shows\ep01
seriesmith assemble Shows\ep01          # -> renders\ep01.mp4
```

With the upscaler installed and the final pass rendering at 960×544 (docs/AUTHORING.md,
**Final resolution**), the picked takes go to 2x once the cut is locked:

```
seriesmith upscale  Shows\ep01 --check  # what it would upscale, and how
seriesmith upscale  Shows\ep01          # the cut's final takes -> <take>.up.mp4 (--proxy: the animatic's)
seriesmith assemble Shows\ep01 --upscaled --size 1920x1080   # -> renders\ep01_up.mp4
```

`seriesmith all Shows\ep01 --proxy` runs build → refs → render → assemble in one go.
`seriesmith master` and `publish` make the finished episode, `issues` keeps review notes,
and `seriesmith` on its own prints every command.

What to expect along the way:

- `check` prints the shot count, the runtime, and a pacing table — every dialogue shot
  with the syllables-per-second it forces on the performance. `0 crammed` is what you want.
- `build` writes `shotlist\`, `refs_todo.md` and `refs_todo.json` and prints the model,
  LoRA and step count each pass will use.
- `refs --list` shows what is missing before it spends any GPU time; `refs` then draws
  each one, keeping every attempt as a take under `refs\_takes\`.
- `render --list` is the dry run. Shots whose reference images are still missing show as
  `blocked`, and the report names the exact file each one wants —
  `--allow-missing-refs` renders them against flat grey stand-ins if you want to see the
  motion first.
- `assemble --proxy --check` reports the cut (order, take, trims) and writes nothing.

`--only sh020,sh030` narrows `render`, `refs` and `upscale` to a few shots; `--redo` makes
a new take instead of reusing the one on disk. Every command has `--help`.

### The same thing in the editor

[docs/EDITOR.md](docs/EDITOR.md) is the guide to the editor itself — the order to do things
in, every button, and the keyboard. The short version follows.

Run `seriesmith serve --root Shows` and open http://127.0.0.1:8190:

1. In the **Shots** tab, check the **project roots** hold `Shows\` (or set them). The
   episode list fills in.
2. Pick **ep01** and the **proxy** pass.
3. **Build** — the same `build` the command line runs, with its report in the panel.
4. Open the **Refs** tab and generate the character sheet and the plate. Every candidate
   is a take; pick the one you want.
5. Back in **Shots**, render — a shot, a selection or the episode. Each take is a job in
   the **Jobs** window (the queue button, top right), with its progress and log; takes
   appear as they finish, and the **Viewer** plays them and compares two side by side or
   under a wipe.
6. The **Timeline** (bottom) is the cut: reorder, trim, pick a take per shot, **Play all**
   to watch it without rendering anything, then **Export** to assemble the one mp4.

Everything the editor does is a plain file in the episode folder — `overrides.json`,
`cut.json`, the per-take sidecars — the same files `seriesmith override`, `seriesmith pick` and
`seriesmith cut` write. You can move between the two freely.

---

## 6. Troubleshooting

**`!! can't tell which script to use in <folder>: ['draft.md', 'notes2.md']`**
The episode folder has more than one candidate `.md`. Name the script after the folder
(`ep01\ep01.md`) or delete the spare. The editor's failure mode is quieter: a folder it
cannot resolve a script for simply never appears in the episode list.

**`!! <folder>\series.json not found`**
`seriesmith build` and `check` need the series config in the episode folder itself (the
editor would fall back to the parent folder's). Copy it in, or run
`seriesmith new` to make one.

**The animatic renders at a size you did not ask for.**
With no `proxy` block in the series config, the proxy pass falls back to the *target's*
own proxy preset — 512×288 for MiniMax H3 — rather than a scaled-down copy of your final
size. That is fine until your final size is not 16:9, at which point the proxy and the
final have different aspect ratios and proxy placeholders in a final cut get scaled
oddly. Add a `proxy` block (the Series settings form's **Size (proxy)**): a new series gets
864×480; 896×512 is exactly 1344×768's shape, both axes on H3's /32 grid.

**Shots skipped with a missing-model message.**
Run `seriesmith targets` (add the episode folder to include its series config's model
choices). It names every missing file, the models folder it belongs in, and its download
link. A missing **required** file skips the shot; a missing **accelerator** (a turbo
LoRA) is not an error — the pass renders on its slower `base` preset and the take's
sidecar records that.

**`ComfyUI at http://127.0.0.1:8188 didn't answer`, or every target is `unknown`.**
ComfyUI is not running, or not on that port. Work on `local` needs it up, and the
readiness checks ask it. `comfyui_url` in the settings ([docs/SETUP.md](docs/SETUP.md))
points seriesmith elsewhere.

**`seriesmith backends` says `local` doesn't answer.**
Local renders go to `comfyui_url` (inside ComfyUI: that ComfyUI itself), so it is the
same as above: ComfyUI isn't up there. Only if you set renders to go through the proxy
(`"local_via": "proxy"`): the proxy isn't running and couldn't be started.
`pip install comfy-api-proxy` into the same Python as seriesmith, and check ComfyUI is up
(the proxy is only started in front of a ComfyUI that answers). `comfy-api-proxy status`
says whether it's running.

**Simple mode or a new series picked a model you didn't expect.**
A series that names no model uses this machine's default: the one you picked in
**Settings**, else the first one installed (H3, LTX-2, Wan 2.2 for video; Krea 2, FLUX.2
Klein, ... for pictures), else H3 and Krea 2. `seriesmith targets` shows what is ready.
The found ones are kept in the settings file as `detected_targets`, and are checked again
each time seriesmith starts.

**A job fails with a missing node class (`SeriesmithShotLoader`, `SeriesmithSaveTake`, ...).**
seriesmith's node pack isn't in that ComfyUI, or ComfyUI wasn't restarted since it was
linked or updated. Link `comfy_nodes\` into `custom_nodes\` (section 2) and restart
ComfyUI. A deployment needs the pack too; Comfy Cloud doesn't (seriesmith sends it Cloud's
own nodes).

**You changed `web/` and nothing changed in the browser.**
The editor is served from the committed pages, not from `web/`: `seriesmith serve` from
`seriesmith\server\static\`, the editor inside ComfyUI from
`comfy_nodes\web\seriesmith-editor.js`. Rebuild both:

```
cd web
npm install                  # once
npm run build:standalone     # -> ../seriesmith/server/static/
npm run build                # -> ../comfy_nodes/web/seriesmith-editor.js
```

then hard-reload the tab (Ctrl-Shift-R). `npm run dev` serves `dev.html` against a mock
API for UI work without a server; it never opens a browser by itself.

**`align` says faster-whisper is missing, but you installed it.**
You installed it into a different interpreter from the one seriesmith picked. The
Recording window names the interpreter it chose and prints the exact `pip install` line
for it. To force one, set `SERIESMITH_ALIGN_PYTHON` to that interpreter's full path in the
environment `seriesmith serve` (or your shell) starts in, and restart it.

**No foley bed on `dub_keep_foley` shots.**
The saver node shells out to `python -m demucs`, so `demucs` has to be importable by
the `python` first on ComfyUI's PATH — not necessarily ComfyUI's own interpreter. The
take's status line says `demucs not installed - foley bed skipped`.

**A workflow ComfyUI refuses.**
seriesmith converts a canvas workflow to API format itself. If your graph uses something the
converter cannot express faithfully, save it with **Workflow → Export (API)** and point the
target's environment variable (section 3) at that file.

**Never hand-edit generated files.** `shotlist\`, `refs_todo.*` and the per-take
`*.shotlist.json` are outputs. Change the script, the series config or `overrides.json`
and rebuild — seeds are derived from the episode, sequence and shot ids, so untouched
shots re-render identically.
