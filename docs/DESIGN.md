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
  ([AUTHORING.md](AUTHORING.md)). Everything else is generated.
- **The story IR.** The script parses to a model-free story (`shots.json`):
  sequences, shots, who is in them, what they say, how long. Nothing in it knows
  about a model.
- **Targets.** A target is one model's way of rendering: its legal lengths and
  sizes (template), how subjects, plates and voices become inputs (recipe), its
  prompt writer, and its presets. Each shot picks one; the series config sets the
  default and a script can change it per sequence or shot. A series config that
  names none renders on this machine's default: picked in Settings, else the
  first one installed in ComfyUI (target.json `default_rank`: H3 Ref2VA, LTX-2,
  Wan 2.2, ...), else H3 Ref2VA (`targets.machine_default`; SETUP.md, "The
  default models"). A new series is given it in its series config. (The editor
  calls a target a model.)
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
| Local ComfyUI | its own API (`/prompt`, `/history`, `/view`: `backends/native.py`), or the Comfy SDK through `comfy-api-proxy` (`local_via`) | your GPU | any workflow, your custom nodes |
| Comfy Cloud | Comfy SDK (v2 API) | Comfy subscription | workflows on Cloud's node set: a shot's graph is made of them (`cloud.py`) |
| Comfy API deployment | Comfy SDK (v2 API), the deployment's URL | paid plan, per GPU-second | your exact workflow, built and pinned |
| Comfy Router | Comfy SDK's Router client | Comfy credits per request | hosted models (Seedance, Kling, hosted H3, Nano Banana, …) |

Cloud and deployments are one client with a different base URL: a workflow in
API format, assets in, a job, assets out. The local ComfyUI is the same shape
over ComfyUI's own API (inputs uploaded to `input/seriesmith/`, the graph
queued, its outputs fetched as /history lists them, read as comfy-api-proxy
reads them), so nothing has to be installed beside it; the proxy, which served
the v2 API in front of it before, is opt-in. Router is a model call (a model
string and arguments), with an mp4 or png back.

Comfy Cloud runs ComfyUI's nodes and the packs Comfy installed there, not
seriesmith's (its /api/object_info lists them: 2026-10-18, 3795 classes, the
core MiniMax H3 and SeedVR2 nodes among them, neither seriesmith's pack nor
PlagueKind's). So a render sent there is made of Cloud's own nodes
(`seriesmith/cloud.py`). The loader's decisions (size, length, which panels of
which sheet, the voice slices, prompt, seed, steps) live in
`comfy_nodes/shotplan.py`, standard library only, which the loader node and
seriesmith both use: seriesmith cuts the pictures and sounds the plan names and
they go up for LoadImage / LoadAudio, and the values are written into the nodes
that read them. The saver becomes CreateVideo + SaveVideo (H.264 CRF 16, BT.709)
and SaveAudio, and seriesmith makes the thumbnail, strip and record as for a
hosted take. A job for Cloud is planned against Cloud's own model lists (its
loaders' choices), so a missing accelerator LoRA renders the base preset there,
and a `bypass_if_missing` node Cloud hasn't is spliced out. Not on Cloud:
`continuous: latent` (the chain nodes), the take's latent, PNG frames, a foley bed.

One Comfy API key covers Cloud, Comfy API and Router.

**seriesmith writes the takes.** In h3pipe, our own save nodes write the take,
its frames and latents straight into the episode folder through absolute paths.
That only works when ComfyUI shares the disk. In seriesmith a workflow saves its
outputs the normal way, the backend hands them back, and seriesmith writes the take
and its record. This is what makes every backend possible.

**Callers ask a backend what it can do, never what kind it is** (REFACTOR.md 3.5).
`Backend` answers `shares_disk` (this machine's ComfyUI: a graph may read the episode
folder, and it is what's probed for nodes and model files), `serial` (one job at a time),
`own_models` (its model files are its own: Comfy Cloud) and `prepare(graph, job, take)`
(the graph as it runs there: Comfy Cloud's lowering to its own nodes is
`ComfyBackend.prepare`); a run says `reports_position` (Router). A new kind of backend
answers these in its own file; nothing in render, runner or edit checks `kind`.

### 2. Capabilities: what a target can do

A target declares what it accepts and returns:

- reference images (how many), reference audio, first/last frame
- camera moves, durations (a grid or a fixed list), sizes
- latent output and latent continuity
- reproducible seeds
- which backends can run it (`local`, `cloud`, `deployment`, `router`)

A shot asks for features and the build adapts or refuses. `continuous: first`
(the previous take's last frame as this shot's first keyframe) on a target that
reads no first keyframe renders on that target's partner (H3 Ref2VA -> H3 FL2VA);
`continuous: latent` on a target that can't chain latents is a build error naming
the ones that can ([CONTINUOUS.md](CONTINUOUS.md)). A take from a target whose seed
the provider decides (`capabilities.seed`) is marked `reproducible: false`. A hosted
model is `moderated` (its provider's content filter reads the request; `capabilities.moderated`
overrides): a subject's design reaches it without what describes a body, in the prose and in a
reference picture's prompt (`targets/moderate.py`), and a Seedance prompt opens by defining
each picture (`Define … in @Image N as …`, BytePlus's prompt guide).

Hosted models return finished video only: no latents. A Comfy API deployment
returns whatever its workflow saves and reports: ComfyUI's /history (and the
proxy and the v2 API) hand back a saved latent as an output like any picture
(PLAN.md, "Facts the plan rests on"); whether Comfy Cloud does the same is still
to be confirmed.

A node a target can do without (binding `bypass_if_missing`, e.g. H3's
`H3SLAAttention` from a third-party pack) is spliced out by the local backend
where ComfyUI hasn't it, the take noting it, and readiness calls the target
degraded rather than not ready: a render needs no pack beyond core ComfyUI and
seriesmith's own.

A model's limits (its lengths, sizes, longest prompt, how many pictures and how
they're sent, whether it makes sound) are read into one form by
`seriesmith/limits.py` and written back where each lives in its target.json, so the
editor has one Limits form for every video model and hosted image model.

### 3. Models as data

A target is a folder with a `target.json`; most need no code of their own. A
target names shared code with `"code": "builtin:<name>"` (`seriesmith/targets/generic/`):

- `video_prose`: the prose prompt and compile the hosted video models share.
- `router_video` / `router_image`: any Comfy Router model, from the target.json's
  `router` block (the model string, fixed arguments, and where the prompt, pictures,
  length, size, seed and sound go in the provider's JSON). `router_inspect.py`
  proposes that block from the model's published schema; the Router models
  seriesmith ships are written by `tools/make_router_targets.py` from saved
  schemas. Pictures reach the provider as Comfy Cloud asset links, inline
  (base64), or through Seedance's virtual library, as the target's `via` says.
- `workflow_image`: an image workflow of your own as an image model (its LoadImage
  nodes take the ref's pictures). A video workflow of your own is proposed by
  `inspector.py` from the graph and `/object_info`, ending in any save node.

Models live in three places (a later one can't take an earlier one's id):

| Where | Scope | Written by |
|---|---|---|
| `seriesmith/targets/<kind>/<id>/` | built-in | the repo |
| `targets/<id>/` beside the settings file | every show on this machine | the editor's Models window |
| `<show>/targets/<id>/` | one show | the Models window, `seriesmith target-from-workflow --save` |

A new or untested model is a **draft**: listed and probed, but not offered for
shots or refs until it's enabled. A built-in that ships as a draft is switched on
per machine (settings `enabled_drafts`), and a built-in's limits changed on this
machine are kept in settings `target_limits`; a shipped target.json is never
edited. Machine settings (`seriesmith/settings.py`: backend URLs, the API key,
deployments, the paid-run cap and those two) never go in the series config.

### 4. Where a job goes

Defaults cascade, later wins, as the target choice already does:

    the target's own first backend -> the series config's `series.backend`
      -> the episode's (overrides.json "episode".backend) -> the shot's
      (overrides.json, beside its `target`) -> the request (render dialog / CLI)

So the series renders locally, an episode goes to a deployment while your GPU
is busy, and one shot goes to Seedance through Router. Where a shot renders is
a production choice, not part of the story, so the script has no line for it.
A default that doesn't suit a shot's target gives way to the target's own (a
series on local still renders its Router shots on Router), with a note; asking
for it by name on that shot is an error (`jobs.backend_choice`).

### 5. Stages

Refs (characters, props, locations, voices), the 360 tour, shot renders, upscale,
post, master and publish are all the same shape: inputs plus a recipe, a target,
a backend, outputs. Each is ported as its own step. Stages that need latents (the
H3 latent upscale, chained takes) only run where latents exist: local or a
deployment.

The command line is one table (`commands.COMMANDS`: each command's usage, help and what
runs it; REFACTOR.md 3.6). `seriesmith` and `seriesmith <command> --help` come from it; a
stage runs in the same process (align keeps a subprocess: it can need the Python with a
Whisper); a usage mistake exits 2 with the usage line.

### 6. The queue

seriesmith owns the queue (`queue.py`, fed by `runner.py`). Its server keeps the
job list, one lane per backend, dispatches each job to its backend, and sends
progress to the editor as events. Local ComfyUI runs one job at a time (so order,
reorder and pause are ours: the queue asks each backend whether it is `serial`); Cloud,
Router and deployments run up to four at once. Long work of seriesmith's own on this
machine (a master, align) is a job too, on a serial `cpu` lane beside the renders
(`Runner.local_job`; REFACTOR.md 3.3): it shows in Jobs with progress, Cancel kills the
tool it is running, and the route that asks for it answers at once with the job.
A job's inputs are staged when it starts, so a continuity shot reads the take it
follows as it is by then, and a job can wait for the one it continues (`after`).
The command line runs the same queue in-process (`runner.cli_runner`).

It survives a restart: live jobs are journaled, a job that reached its backend is
reattached by its run id and collected, and one still waiting is asked for again. A
master or align that was running died with the server, so it is listed failed for
Retry; a server that stops (`Queue.close`) stops their tools rather than leaving them
running. A hung job is stopped at its time limit; paid runs (Cloud, Router, deployments)
are counted, confirmed in batches and capped by an optional limit in Settings, on every
queue: the editor's and the command line's (`runner.queue_for`; REFACTOR.md 3.6). While
Router holds a job in line, the Jobs window says where it is.

### 7. The editor, in two hosts

The editor is h3pipe's React app. Its components only talk to two interfaces,
`api()` and `host()`; all ComfyUI glue lives in one file. So it runs in two
places from one codebase:

- **Standalone** (`seriesmith serve`, the main product): seriesmith's own server
  (aiohttp, port 8190) serves the page and the API (and starts comfy-api-proxy,
  when local renders go through it). No ComfyUI needed if every job goes to the
  cloud. `run_seriesmith.bat` / `.sh` set up the repo's `.venv` on first start.
  `seriesmith stop [--restart]` (or Settings' Stop / Restart, on the machine that
  runs it) stops it cleanly; under a `run_seriesmith` launcher, Restart starts it
  again.
- **Inside ComfyUI** (a thin second host, `server/comfyui.py`): seriesmith's node
  pack mounts the same route table on ComfyUI's server, with its own queue and
  journal; the editor lives in its sidebar and bottom panel, as in h3pipe. The pack
  is linked into ComfyUI's `custom_nodes` for now; a ComfyUI Manager listing comes
  with publishing (PLAN.md, "Later").

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
  window grouped by backend: progress, elapsed time, where Router has a job,
  cancel, retry, reorder and pause for the local queue, and a Log section for
  each backend's messages and errors. Thumbnails in Shots, Refs and the
  timeline keep showing a take's progress in place.

New beside h3pipe's editor: series and season import (a series config and a stack
of scripts), and notes that stay on a shot (h3pipe's issues notepad, kept).

Both hosts register one route list (`server/routes.py`: the API's, the queue's, Settings'
and Features'), every route at its path and under `/api`, and the page reaches them only
through its host (`api().fetch` inside ComfyUI is `fetchApi`). A route is a function of
(context, query or body) -> (status, data) served by `views.make_view` (JSON, gzip, the
executor, the error body in one place); an error that always means one answer says so
itself (`http_status`: RefError 400, UnknownRef 404, MasterError 409, ...; REFACTOR.md 3.2).

### 8. Loading an episode

An episode's status describes every take of every shot. What a take's own files say
(its sidecar, its upscale and post records and whether they're fresh, the file its sound
plays from) is kept keyed on those files' size and modified time, from one listing of
each shot folder, and kept on disk per episode and pass (`takefiles.py`; REFACTOR.md
3.4): a change made anywhere, in the editor or not, is read on the next load, and a
restart starts warm. What depends on more than the take's files (staleness, the chain, the
upscale recipe match) is worked out each time. Within one answer a pass's cut is resolved
once (`edit.cut_memo`) and each reference file looked at once (`takes.one_look`). The page
asks for the episode it had open as it starts, and refs once the shots are in.

## Package layout

```
seriesmith/
  core/        script parser, story IR, series config, framing, speech pacing
  targets/     one folder per model; generic/ the code data-only models use
  build.py     script + series config -> story IR -> each target's shotlist
  cli.py       the `seriesmith` entry point; commands.py every command in one table
  settings.py  this machine's settings (never the series config)
  limits.py    a model's limits in one form; router_inspect.py a Router model's schema
  backends/    local, cloud, deployments (comfy.py); router.py; a fake for tests
  jobs.py      planning a take; takes.py its files and record; takefiles.py what they
               say, kept; render.py
  queue.py     the job queue; runner.py what goes on it; finishing.py
  api.py       the editor's routes as functions
  server/      standalone.py (`serve`), views.py (aiohttp), comfyui.py (the ComfyUI host)
  helpers/     PIL/numpy helpers run as subprocesses
  ff.py        ffmpeg / ffprobe, found once; core/fileio.py every write (atomic, LF, the
               Windows retry); core/paths.py where an episode's series config and script are
comfy_nodes/   seriesmith's ComfyUI node pack
web/           the editor (React/Vite)
tests/         golden outputs and unit tests
tools/         generators: prompts/, INSTALL.md's model list, the Router built-ins
docs/
```

Python 3.10+. The core and build need nothing outside the standard library; the
rest uses `comfy-sdk`, Pillow and numpy.

## Build order

Vertical slices, each ending with something that runs: core and compile;
backends; the first render (H3 on your own GPU); the first hosted render
(Router); every local target; refs, the 360 tour and continuity; takes,
picks, cuts and notes; the server, the queue and both hosts; finishing; then
forms, resilience, simple mode, pictures from a frame, and hosted models as data.
The work list, with what "done" means for each step, is [PLAN.md](PLAN.md).

## Open questions

- Does Comfy Cloud return a saved latent as an output, as the proxy does? (Not
  needed while Cloud's renders keep none: an H3 latent is a nested tensor its
  SaveLatent may not take.)


Answered since: Router's hosted H3 (`minimax_h3`) takes reference images and
first/last frames, no reference audio (it makes its own sound); Router answers an
ordinary Comfy API key (live since 2026-10-11). Comfy Cloud runs a curated node set,
not your packs (2026-10-18): a shot goes there as Cloud's own nodes (`cloud.py`).

## Notes from the port

- h3pipe's build also checked the series config's `upscale.master` and
  `post.master` recipes. The first port left them out; they came back with step 6,
  and `check` validates them again.
- Render-time code inside targets (graph patches, staged inputs) referred to
  h3pipe's job and take modules under their new names; it runs on seriesmith's own
  since steps 2-3.
