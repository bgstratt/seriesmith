# seriesmith

A series config and episode scripts in, finished episodes out: any shot on any
model, on your own GPU, on Comfy's cloud, or hosted through Comfy Router.

You describe a show once in `series.json` (the cast, the places, the voices, the
look) and write each episode as a screenplay-flavoured markdown script (`epNN.md`).
seriesmith parses the script into a model-free **story** (`shotlist/shots.json`),
compiles every shot for the **video target** that renders it (a model and how to
drive it), makes the reference pictures, keyframes and voices the shots need
through **image** and **audio targets**, renders each shot on a **backend**, and
cuts the takes together, through upscale, post and master.

You drive it from the **editor**, a page in your browser that `seriesmith serve`
opens (shots, takes, refs, the cut, the Jobs queue), or from one command,
`seriesmith`. Every shot is its own job, so a bad shot is rendered again alone and
the rest of the episode is untouched; a shot written `continuous:` reads the take
before it when its job starts, so a whole chain still queues at once. Every take is
kept with the exact settings that made it.

seriesmith is the successor to h3pipe, which did all this on one local ComfyUI.

New here? **[Getting started](docs/QUICKSTART.md)**: install it from ComfyUI-Manager and
it runs in ComfyUI on the models you already have; **[docs/AUTHORING.md](docs/AUTHORING.md)** is the script and
series config format.

### The documents

| | What it is | Read it when |
|---|---|---|
| **[docs/QUICKSTART.md](docs/QUICKSTART.md)** | Getting started: from ComfyUI-Manager, on a page of its own, or a clone in custom_nodes | First |
| **[docs/FULL_SETUP.md](docs/FULL_SETUP.md)** | The node packs, model files, LoRAs and software for every feature, by job: H3 at full quality, voices, upscale, post, master, 360s | Turning on a feature that says something is missing |
| **[INSTALL.md](INSTALL.md)** | Each part in detail: seriesmith, the node pack, the workflows, every model file with its folder and link, a first episode | Setting up by hand, or a model is missing |
| **[docs/SETUP.md](docs/SETUP.md)** | The backends: your ComfyUI, Comfy Cloud, deployments, Router; the default models; the settings file and the key | Choosing where shots render |
| **[docs/EDITOR.md](docs/EDITOR.md)** | Driving the editor: the order things happen in, every button, what click, double-click and right-click do in each panel, and the keyboard | Using the editor |
| **[docs/AUTHORING.md](docs/AUTHORING.md)** | The format, and the whole of it: a first episode to copy, every field of the script and the series config, framing, timing, camera and the reference rules | Writing or fixing an episode. Read once before the first one |
| **[docs/SCRIPT_CONVERSION.md](docs/SCRIPT_CONVERSION.md)** | A spec-format screenplay scene worked all the way through to shots | You have a screenplay and want it as an episode |
| **[docs/COMMANDS.md](docs/COMMANDS.md)** | The command line in depth: build, refs, render, assemble, takes and the cut, recorded dialogue, the project layout | Working from a terminal |
| **[docs/CONTINUOUS.md](docs/CONTINUOUS.md)**, **[docs/POST_PROCESSING.md](docs/POST_PROCESSING.md)**, **[docs/RECORDED_DIALOGUE.md](docs/RECORDED_DIALOGUE.md)**, **[docs/KREAGEN.md](docs/KREAGEN.md)** | Continuous shots; the post pass; lip sync to a recording; the reference-image generator | Using that part |
| **[docs/H3_TARGET.md](docs/H3_TARGET.md)** | The default video target, MiniMax H3 Ref2VA, in detail: its reference slots, sheets, voices, audio policies, pacing | Tuning shots for H3 |
| **[docs/API.md](docs/API.md)** | The editor's HTTP API and the on-disk contracts behind it (takes, overrides, the cut, references) | Changing the editor, or driving seriesmith from your own code |
| **[docs/DESIGN.md](docs/DESIGN.md)**, **[docs/PLAN.md](docs/PLAN.md)** | How seriesmith is built (backends, the queue, the two hosts) and the work list | Changing seriesmith |
| **[CONTRIBUTING.md](CONTRIBUTING.md)** | House rules: the golden tests, how the generated docs are regenerated | Sending a change |

`prompts/SKILL.md` and `prompts/seriesmith-script.instructions.md` are **generated**
from `docs/AUTHORING.md` by `python tools/make_prompts.py`, so an assistant drafting
a script reads exactly what you do; the same command builds the installable
script-writing skill (`build/skill/seriesmith-episode-script/` and its `.zip`). Edit
the guide, never the copies — a test fails if they drift.

```
  you write                     generated                                    rendered
  ─────────                     ─────────                                    ────────
  series.json ─┐                shotlist/shots.json (story)
  epNN.md     ─┼─ build ─▶      shotlist/shotlist[.<target>].json ─ render ─▶ renders/<shot>/<shot>_tNN.mp4
  (recording) ─┘  (align)       refs_todo.json ─── refs / keyframes ─▶ refs/       │
                                                                     assemble / master ─▶ epNN.mp4
```

## Targets and backends

A shot renders on MiniMax H3 Ref2VA unless the script (`target:`), a render profile,
the episode (chosen in the editor) or the series config (`series.target`) names
another. A shot retargeted in the editor or with `seriesmith override` is compiled
for its new target when it is queued; no rebuild.

| Video target | Label | Runs on |
|---|---|---|
| `minimax_h3_ref2va` (default) | MiniMax H3 Ref2VA | a ComfyUI: local, Comfy Cloud, a deployment |
| `fasth3_omni` | FastH3 Omni: FastVideo's 8-step H3, up to eight subjects a shot | a ComfyUI |
| `minimax_h3_fl2va` | MiniMax H3 FL2VA (first/last frames) | a ComfyUI |
| `ltx2` | LTX-2.5 distilled (text / keyframes to video + audio) | a ComfyUI |
| `ltx2_ingredients` | LTX-2.3 ingredients (character/plate refs) | a ComfyUI |
| `wan22_i2v` | Wan 2.2 14B I2V | a ComfyUI |
| `wan22_ti2v` | Wan 2.2 5B TI2V | a ComfyUI |
| `wan22_vace` | Wan 2.2 14B VACE (refs) | a ComfyUI |
| hosted video models (Seedance, Kling, Wan, Veo, Runway, hosted H3, …) | the models seriesmith has tried, plus drafts to probe; the Models window lists them, and adds any other from Router's catalog | Comfy Router |

| Image target | Label |
|---|---|
| `krea2` (default for refs) | Krea 2 turbo (text to image) |
| hosted image models (Nano Banana, Seedream, GPT Image, Flux, Qwen, Krea 2, …) | on Comfy Router; listed and added in the Models window |
| `z_image_turbo` | Z-Image Turbo (fast text to image) |
| `flux2_klein` | FLUX.2 Klein 9B (text to image) |
| `flux2_klein_edit` (default for keyframes, when installed) | FLUX.2 Klein 9B edit (uses reference images) |
| `flux_kontext` | FLUX.1 Kontext dev (edit, one reference) |
| `minimax_h3_still` | MiniMax H3 as an image model: renders 5 frames, keeps the first, up to 9 references |
| `fasth3_omni_still` | FastH3 Omni as an image model, as `minimax_h3_still` |
| `qwen_image_21` | Qwen-Image 2.1: text to image, or an edit of up to 16 reference images |
| `fibo2_dev` | Fibo 2.0 Dev: text to image, or an edit of up to 4 references (non-commercial licence) |
| `fibo2_edit_turbo` | Fibo 2.0 Edit Turbo: 4-step edits only (non-commercial licence) |
| `qwen_rapid_aio` | Qwen-Image-Edit Rapid AIO: a 4-step all-in-one edit checkpoint, up to 3 references |
| `klein_erp_360` | FLUX.2 Klein 9B with a 360 outpaint LoRA: a plate as an equirectangular panorama (the Refs tab's **Make 360**) |

| Audio target | Label |
|---|---|
| `ltx2_voice` (default for voices) | LTX-2.5 audio-only: one speaking voice from a character's `voice` line |

Each target lives in `seriesmith/targets/<kind>/<id>/`: `target.json` (presets, the
model files it needs with their tier and download links, how to drive it, which
backends can run it), its code (the prompt writer, the compile) and, for a workflow
target, `workflow.json`. A Comfy Router model is data only: its `target.json` says
where a shot's prompt, pictures, length, size and seed go in the provider's request
(`tools/make_router_targets.py` writes the built-in ones).

**Your own models.** The editor's **Models** window (beside every model picker) adds
another Comfy Router model from Router's catalog (its schema read, its limits checked,
a free dry run of the request), or turns a workflow saved in your ComfyUI into a model:
video for shots, or image for refs and keyframes, ending in any save node. Save one for
every show (`targets/` beside the settings file) or for one show
(`<show>/targets/<id>/`); a new one is a draft until you probe it and enable it. Every
video model and hosted image model has a **Limits** form (length, size, prompt length,
pictures, sound); a change to a built-in one is kept on this machine.
From the command line, `seriesmith target-from-workflow <workflow> <episode> --save`
saves a workflow as that show's model (`--save --every-show`: every show's).

**Backends** are where a job runs: `local` (your own ComfyUI, straight to its
own API), `cloud` (Comfy Cloud), `deployment:<target>` (a deployed
workflow) and `router` (a hosted model through Comfy Router). The last three need a
Comfy API key. A job runs on the request's backend, else the shot's, the episode's,
the series config's (`series.backend`), else its target's first.
`seriesmith backends` lists what this machine is set up for; [docs/SETUP.md](docs/SETUP.md)
sets them up.

**What's installed?** With ComfyUI running, `seriesmith targets` prints one line per
target (`ready`, `degraded`, `not_ready`, `unknown`) and every missing file under it
with its models folder and download link. A missing required file skips the shot
with its link; a missing accelerator (a turbo LoRA) renders the slower base preset,
and the take says so. The editor's model pickers and its **Models** window show the
same.

## Install

**[INSTALL.md](INSTALL.md) is the full walkthrough;
[docs/QUICKSTART.md](docs/QUICKSTART.md) the short one.** Three ways, one app:

- **Inside ComfyUI:** **Manager → Custom Nodes Manager**, search for **seriesmith**,
  install, restart ComfyUI (or `comfy node install seriesmith`). The editor is in its
  sidebar and renders on it. No other node pack is needed.
- **On a page of its own:** `git clone https://github.com/bgstratt/seriesmith.git`, then
  `run_seriesmith.bat` (this PC; `run_seriesmith_ext.bat`: your home network too;
  `run_seriesmith.sh` on Linux/macOS) sets itself up in the folder's `.venv` the first
  time, opens the editor at http://127.0.0.1:8190, and starts it again after the
  editor's **Restart**; `seriesmith stop [--restart]` stops it from a terminal. It
  renders on a ComfyUI, or with only a Comfy API key, on Comfy's cloud.
- **A clone in `custom_nodes`**, for following main: `git clone
  https://github.com/bgstratt/seriesmith.git` in ComfyUI's `custom_nodes`, and restart
  ComfyUI. (Cloud and Router want comfy-sdk in ComfyUI's Python: Settings gives the
  command. A clone kept elsewhere: link its `comfy_nodes` into `custom_nodes` instead.)

The default models are the ones you already have: H3, else LTX-2, else Wan 2.2 for video;
Krea 2, else FLUX.2 Klein, ... for pictures (docs/SETUP.md, "The default models").
Everything else is optional, and **Settings → Features…** lists it (downloading the
model files and ffmpeg itself; a node pack from ComfyUI-Manager, a Python package by the
pip command it gives):
- more models;
- H3's sparse attention (the PlagueKind pack: H3 renders without it, marked degraded);
- voices;
- upscalers;
- post-processing;
- a full ffmpeg.

[docs/FULL_SETUP.md](docs/FULL_SETUP.md) lists it all by feature. INSTALL.md has every
model file with its link, generated from the targets by `python tools/make_models_md.py`.

**Requirements**, in short:
- a recent local [ComfyUI](https://github.com/comfyanonymous/ComfyUI) and an NVIDIA GPU
  that can hold the models you use (developed on a 32 GB card), or a Comfy API key and
  the cloud;
- git;
- Python 3.10+, only for the editor on its own page and the command line.

ffmpeg comes with it (imageio-ffmpeg and PyAV), and your own wins if you have one.

## The editor

`seriesmith serve` (or `seriesmith serve --root Shows`) serves the editor at
http://127.0.0.1:8190:

- **Shots** (sidebar): the project folders (roots) and the episode, the pass
  (final / proxy) and the episode's model; build; every shot with its takes, status
  and stale marks; render, redo, cancel, pick the take the cut uses, discard a take.
  **Import series…** brings in a whole season's scripts at once, with one series
  config or one per episode.
- **Refs** (sidebar): every character view, prop, plate, voice and shot keyframe the
  series config and script call for, with candidates to generate, import, compare,
  edit, turn, discard and pick; a location's angles, its 360 panorama and its H3
  camera tour.
- **Timeline** (bottom): the cut as an editable track — reorder, trim frame by frame,
  lock, undo, **Play all** and **Export**.
- **Viewer** (docked in the middle): a shot's takes with A/B compare (side by side or
  wipe), a ref's candidates, a tour to keep any frame from, a 360 in its viewer.
- **Jobs** (the queue button, top right): every render, ref, upscale, post and tour
  queued, running and done, per backend — with progress, the log, cancel, reorder,
  pause a backend, and run again as a new take.
- **Script**, **Series config**, **Inspector**, **Recording**, **Audio from…**,
  **Promote**, **Upscale**, **Post-process**, **Master** and **Models** open as
  floating windows.
- **Settings** (top bar): this machine's Comfy API key, ComfyUI and deployment
  addresses, the default video and picture models, and, on the PC that runs the server, **Stop** and
  **Restart**.

**[docs/EDITOR.md](docs/EDITOR.md) is the guide to driving all of it.** Everything
the editor does is a file in the episode folder (`overrides.json`, `cut.json`, take
records, `_history/`), and the commands do the same.

## Quick start (command line)

```
seriesmith new      Shows\ep05             # a series config + script that build (from examples/starter/)
seriesmith check    Shows\ep05             # validate and check dialogue pacing (writes nothing)
seriesmith build    Shows\ep05             # the story, shotlists, reference work orders
seriesmith targets  Shows\ep05             # which targets this ComfyUI can render
seriesmith supply   Shows\ep05 C:\sheets   # pictures you already have, into their ref slots
seriesmith refs     Shows\ep05             # generate the views, props, plates still missing
seriesmith render   Shows\ep05 --proxy     # low-res animatic
seriesmith assemble Shows\ep05 --proxy     # join it into one mp4
seriesmith render   Shows\ep05             # full-res
seriesmith master   Shows\ep05             # the series recipe (upscale, post) on every shot, then the master
seriesmith publish  Shows\ep05             # the review cut between the series intro and outro
```

Every command has `--help`; `--backend NAME` picks where its jobs run. The command
line runs its jobs on a queue of its own and waits for them; the editor's server
runs its own queue. **[docs/COMMANDS.md](docs/COMMANDS.md)** covers every command.

## Tests

    pip install -e .[test]
    python -m pytest                  # every core: about a minute
    cd web && npx vitest run

The golden tests rebuild every fixture and compare the results byte for byte with
`tests/golden/`; no test reaches a real backend.

## License

MIT — see [LICENSE](LICENSE).
