# seriesmith — design

seriesmith turns a series config (`series.json`: the cast, the places, the voices,
the look) and episode scripts (`epNN.md`) into finished episodes. It writes every
shot's prompt for the model that renders it, runs the renders on your own GPU or on
Comfy's cloud, and gives you an editor to review takes, pick the cut, take notes
and master the result.

It is the successor to h3pipe, which did all of this for one model (MiniMax H3) on
a local ComfyUI. seriesmith keeps h3pipe's story layer and editor and changes
where the work runs: any shot, on any model, local or hosted.

Started from h3pipe `c5f9be0` (2026-10-09).

## What stays the same

- **The authored inputs.** `series.json` and `epNN.md`, in h3pipe's format
  (h3pipe's `docs/AUTHORING.md`). Everything else is generated.
- **The story IR.** The script parses to a model-free story (`shots.json`):
  sequences, shots, who is in them, what they say, how long. Nothing in it knows
  about a model.
- **Targets.** A target is one model's way of rendering: its legal lengths and
  sizes (template), how subjects, plates and voices become inputs (recipe), its
  prompt writer, and its presets. Each shot picks one; the series config sets the
  default and a script can change it per sequence or shot.
- **Seeds.** A shot's seed comes from its episode, sequence and shot ids
  (`stable_seed`), so an untouched shot re-renders identically on a backend that
  can promise that.
- **Takes and the cut.** Every render is a take, kept with a record of how it was
  made. You pick takes into a cut; overrides change one shot without touching the
  script.

## What changes

### 1. Backends: where a job runs

Every job, whatever the stage, has the same lifecycle: upload the inputs, submit,
follow its progress, download the outputs. A backend is one place that can do
that:

| Backend | Reached with | Cost | Runs |
|---|---|---|---|
| Local ComfyUI | Comfy SDK, through `comfy-api-proxy` | your GPU | any workflow, your custom nodes |
| Comfy Cloud | Comfy SDK (v2 API) | Comfy subscription | workflows on Cloud's node set |
| Comfy API deployment | Comfy SDK (v2 API), the deployment's URL | paid plan, per GPU-second | your exact workflow, built and pinned |
| Comfy Router | Comfy SDK's Router client | Comfy credits per request | hosted models (Seedance, Kling, hosted H3, Nano Banana, …) |

The first three are one client with a different base URL: a workflow in API
format, assets in, a job, assets out. Router is a model call (a model string and
arguments), with an mp4 or png back.

One Comfy API key covers Cloud, Comfy API and Router.

**seriesmith writes the takes.** In h3pipe, our own save nodes write the take,
its frames and latents straight into the episode folder through absolute paths.
That only works when ComfyUI shares the disk. In seriesmith a workflow saves its
outputs the normal way, the backend hands them back, and seriesmith writes the take
and its record. This is what makes every backend possible.

### 2. Capabilities: what a target can do

A target declares what it accepts and returns:

- reference images (how many), reference audio, first/last frame
- camera moves, durations (a grid or a fixed list), sizes
- latent output and latent continuity
- reproducible seeds
- which backends can run it (`local`, `cloud`, `deployment`, `router`)

A shot asks for features and the compile adapts or warns. For example,
`continuous: latent` on a Router target falls back to last-frame continuity (pull
the last frame, feed it as the next shot's first frame) and `check` says so. A
take made on a backend that can't promise a seed is marked non-reproducible.

Hosted models return finished video only: no latents. A Comfy API deployment
returns whatever its workflow saves, so a latent saved as a file should come back
as an asset (to be confirmed against the v2 API).

### 3. Where a job goes

Defaults cascade, later wins, as render settings already do:

    target's allowed backends -> series config default -> episode -> sequence
      -> shot -> the request (the render dialog / CLI)

So the series renders locally, one sequence goes to a deployment while your GPU
is busy, and one shot goes to Seedance through Router.

### 4. Stages

Refs (characters, props, locations, voices), the 360 tour, shot renders, upscale,
post, master and publish are all the same shape: inputs plus a recipe, a target,
a backend, outputs. Each is ported as its own step. Stages that need latents (the
H3 latent upscale, chained takes) only run where latents exist: local or a
deployment.

### 5. The queue

seriesmith owns the queue. Its server keeps the job list, dispatches each job to
its backend, and sends progress to the editor as events. Local ComfyUI runs one
job at a time; Router and deployments run several at once.

### 6. The editor, in two hosts

The editor is h3pipe's React app. Its components only talk to two interfaces,
`api()` and `host()`; all ComfyUI glue lives in one file. So it runs in two
places from one codebase:

- **Standalone** (`seriesmith serve`, the main product): seriesmith's own server
  serves the page and the API. No ComfyUI needed if every job goes to the cloud.
- **Inside ComfyUI** (a thin second host): ComfyUI serves the page and mounts the
  same route table; the editor lives in its sidebar and bottom panel, as in h3pipe.
  Installed through the ComfyUI Manager.

The standalone layout:

```
┌──────────────────────────────────────────────────────────────┐
│ Series ▸ episode            [▶ 2 running · 5 queued ▓▓░ 63%] │  jobs button
├────────────┬─────────────────────────────────────────────────┤
│ Shots│Refs │  Viewer (docked)                ┌─ Jobs ──────┐ │
│ (sidebar)  │  video · ref · A|B compare      │ by backend   │ │
│            │                                 │ cancel/retry │ │
│            │                                 │ Log ▾        │ │
├────────────┴─────────────────────────────────┴──────────────┤
│ Timeline                                                      │
└──────────────────────────────────────────────────────────────┘
  + the editor's floating windows: Inspector, Issues, Script, dialogs
```

- **Sidebar:** the Shots and Refs tabs.
- **Viewer, docked in the middle:** video, a ref, or two takes side by side.
- **Timeline:** along the bottom.
- **Jobs:** a button in the top bar (counts and current progress) opening a
  window grouped by backend: progress, elapsed time, credits for Router jobs,
  cancel, retry, reorder and pause for the local queue, and a Log section for
  each backend's messages and errors. Thumbnails in Shots, Refs and the
  timeline keep showing a take's progress in place.

New beside h3pipe's editor: series and season import (a series config and a stack
of scripts), and notes that stay on a shot (h3pipe's issues notepad, kept).

## Package layout

```
seriesmith/
  core/        script parser, story IR, series config, framing, speech pacing
  targets/     one folder per model (target.json, prompt writer, workflow)
  build.py     script + series config -> story IR -> each target's shotlist
  cli.py       the `seriesmith` command
  backends/    local / cloud / deployment / router            (step 2)
  jobs.py      the job lifecycle and the queue               (step 2-3)
  takes.py     takes, the cut, overrides, notes              (step 4)
  server/      the HTTP API and events, mountable anywhere   (step 5)
web/           the editor (React/Vite)                        (step 5)
tests/         golden outputs and unit tests
docs/
```

Python 3.10+. The core needs nothing outside the standard library; backends use
`comfy-sdk`.

## Build order

Each step ends with something that runs.

1. **Core and compile.** h3pipe's `h3core/`, `h3build.py` and `targets/` as the
   `seriesmith` package; `seriesmith build` and `seriesmith check`. The golden
   tests come along and must match h3pipe's outputs byte for byte, except the
   renames listed in the commit. Then capabilities on each target.
2. **Backends.** The job lifecycle; the Comfy backend on the SDK (local through
   the proxy, Cloud and deployments by URL); the Router backend. One local target
   (H3 ref2va) and one Router target rendering end to end.
3. **seriesmith writes the takes.** Outputs come back from the backend; the take,
   its record and its latents are written by seriesmith. h3pipe's save nodes go.
4. **Takes, picks, cuts, overrides, notes.** h3pipe's `h3takes`, the pick and
   override parts of `h3edit`, `h3issues` and `h3promote`.
5. **The server and both hosts.** The route table mounted by `seriesmith serve`
   and inside ComfyUI; the standalone layout; the Jobs window; series import.
6. **Stages.** Refs and the 360 tour, then upscale, post, master and publish,
   each through a target and a backend.

## Open questions

- Does Comfy Cloud accept arbitrary custom node packs, or only a curated set?
  (Deployments clearly do.)
- Which inputs does Router's hosted H3 take: reference images, audio?
- Does the v2 API return non-media outputs (a latent file) as assets?
- Comfy's docs disagree on whether Router is generally available.
- The Comfy Dev Platform Challenge was postponed; check its rules when it is
  re-posted. Our reading: the entry must run its generation through the
  Developer Platform, Comfy Cloud or the SDK; where the UI lives doesn't matter.
  The feature to lead with is character and location consistency across a series.

## Notes from the port

- h3pipe's build also checked the series config's `upscale.master` and
  `post.master` recipes. Those checks belong to the upscale and post stages and
  come back with step 6; until then a recipe in the series config is not
  validated by `check`.
- Render-time code inside targets (graph patches, staged inputs) still refers to
  h3pipe's job and take modules under their new names. It is not called by the
  build and gets reworked with step 2.
