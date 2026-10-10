# seriesmith — plan

The work list behind [DESIGN.md](DESIGN.md): what gets built, in what order, and
how each step is known to be done. Tick items off as they land; change the plan
here when a step teaches us something.

Each step is a vertical slice: it ends with something you can run.

## Facts the plan rests on

From reading comfy-sdk 0.4.0 and comfy-api-proxy 0.1.6 (2026-10-10):

- **The SDK takes its server from the environment.** `Comfy()` has no base-URL
  argument; it reads `COMFY_BASE_URL` (jobs, assets) and `COMFY_ROUTER_BASE_URL`
  when constructed. A local client and a cloud client in one process means
  building each under a lock with the variable set.
- **Workflows go in as API-format JSON.** `WorkflowFactory.from_json(graph)`,
  `set_input(node, field, value)` for any value, `submit()` / `run()`. A job
  has `events()` (progress, previews, outputs, status, logs), `wait()`,
  `cancel()`, `outputs`. Polling is the source of truth; events are best effort.
- **Outputs are what nodes report.** The proxy builds a job's outputs from
  ComfyUI's history: `images`, `gifs` (video), `audio`, `text`, `files`,
  `latents`. A file a node writes without reporting it, or outside ComfyUI's
  output/temp folders, cannot be fetched. SaveLatent's latents come back.
- **Inputs are uploaded assets.** Any file type; deduplicated by hash; a
  workflow input set to an asset becomes the filename a LoadImage-style node
  expects. The proxy uploads into ComfyUI's `input/` (100 MB default cap).
- **The local queue is ours to manage.** The proxy can cancel a job but not
  reorder or prioritise. seriesmith keeps its own queue and gives the local GPU
  one job at a time, so reorder and pause are ours.
- **Router is a model call.** `models.submit(model, arguments)` with the
  provider's own JSON; results are the provider's JSON (usually URLs). Media
  inputs are URLs, which providers can only fetch from Comfy Cloud assets, so a
  Router job needs a Comfy key and uploads its inputs to Cloud even when
  everything else is local. No cost fields come back.
- **The proxy serves no `object_info` or model lists.** Readiness checks (is
  the node pack installed, are the models there) still ask ComfyUI directly,
  for the local backend only.
- **The proxy needs `--state-dir`**, or a restart forgets its assets and jobs.

## Step 1 — core and compile ✅

- [x] h3pipe's core, targets and build as the `seriesmith` package; `seriesmith
      build` / `check`; goldens byte-identical but for the one intended line.
- [x] Capabilities: `backends`, `reproducible`, `max_subjects`, `max_voices`,
      `continuous`, `latents`.

## Step 2 — backends ✅

The job lifecycle, behind one interface, with nothing seriesmith-specific in it.

- [x] `seriesmith/backends/`: `Backend` (upload an input, submit, follow, cancel,
      fetch outputs) and the job record it returns (id, status, progress,
      outputs with name, type and node).
- [x] `ComfyBackend` on comfy-sdk: one class for local (through the proxy),
      Cloud and a deployment, differing only in base URL and key. Builds its SDK
      client under the environment lock.
- [x] `RouterBackend`: model + arguments in, the provider's result out; inputs
      uploaded as Cloud assets and passed as URLs; outputs downloaded.
- [x] `FakeBackend` for tests: records submissions, plays back canned progress
      and outputs.
- [x] Settings: where the proxy is, the Comfy API key, deployment URLs per
      target. Read from the environment and a user settings file, never from the
      series config (it gets shared).
- [x] `seriesmith backends`: lists each configured backend and whether it
      answers.
- [x] Setup notes: installing comfy-api-proxy beside ComfyUI, with `--state-dir`.

**Done when** a trivial core workflow (an empty image, saved) runs on local
ComfyUI through the proxy and its output is downloaded, from a test that is
skipped when no proxy is running.

Done 2026-10-10: `seriesmith backends --try local` uploads a picture, inverts it
on ComfyUI 0.39 and checks what comes back (`tests/test_backends.py`,
LiveLocalTest). The Router backend is written but untested against the real
service until step 4 (it needs a key and credits).

## Step 3 — the first render: H3 on your own GPU ✅

One target, end to end, the way every target will work.

- [x] Port from h3pipe: takes and their records (`h3takes`), job planning and
      the graph builder (`h3jobs`: plan_job, Job, graph_for and the binding
      code), the readiness checks that ask ComfyUI directly.
- [x] A portable graph: the shot's references go in as uploaded assets (core
      LoadImage / LoadAudio), its compiled shot as a text input, so nothing in
      the graph reads the episode folder.
- [x] A small seriesmith node pack (successor to h3pipe's `comfy_nodes/`): the
      shot loader that takes those inputs (panel cropping, audio slicing), and a
      save node that writes into ComfyUI's output folder and reports every file
      (the mp4, the latent, a thumbnail).
- [x] seriesmith writes the take: downloads the outputs into
      `renders/<shot>/`, writes the take record (settings, seed, backend,
      timings) itself.
- [x] `seriesmith render <episode> --only sh010`.

**Done when** a Porchlights shot renders on local H3 through the proxy and its
take matches what h3pipe makes for the same shot and seed (same prompt, same
graph apart from the loader and saver, same picture).

Done 2026-10-10: Porchlights ep02 sh180, in a scratch copy of the episode,
rendered by h3pipe (t01) and by `seriesmith render --redo --same-seed` through
comfy-api-proxy (t02): the decoded frames are identical and so is H3's sound;
the take records differ only in take number, times, job id and `backend`.

Left for later steps:
- The readiness checks (model files, node classes) still ask ComfyUI
  directly, so they only mean something for the local backend.
- Continuous shots (`continuous: latent`, H3ChainLatent) and continuity first
  frames (H3ContinuityFrame) still read the episode folder: local only (step 5).
- Each run leaves its files in ComfyUI's output/seriesmith/<run>/ after they
  are copied into the take; the API can't delete them. A cleanup command, or
  the proxy's retention, is needed before long episodes.

## Step 4 — the first hosted render: Router (built; live run waits for a key)

- [x] A Router target kind: no workflow; target.json `router` (the model
      string, its named sizes and ratios, fixed arguments) and a
      `router_call(target, job)` in the target's code, with the shared prose
      compile (`builtin:video_prose`).
- [x] One video target: `seedance_2_5` (Seedance 2.5: references or
      first/last frames, 4-30 s, its own sound). The image target for refs
      moves to step 8, with the refs stage.
- [x] Choosing the backend: request, shot, episode (overrides.json), series
      config, target (DESIGN.md, "Where a job goes"); a shot that can't run
      where it was sent says why at render time. Nothing at build time: the
      build doesn't know this machine's backends.
- [x] Takes from a non-reproducible target say so (`reproducible: false`), and
      record what was sent (`model_request`, without the pictures).
- [x] A hosted take is finished by seriesmith: the video in, ffprobe for its
      length, thumbnail and strip by ffmpeg (`seriesmith/finish.py`).
- [ ] **Live:** one real Router call with a Comfy API key (COMFY_API_KEY), to
      confirm the request shape, the upload of inputs as Cloud assets, and the
      result's `content.video_url`. `seriesmith render <ep> --only <shot>
      --target seedance_2_5 --dry-run` shows the request without a key.

Provider inputs can also be sent inline as base64 data URIs (the Seedance
docs), which would spare small pictures the Cloud upload; worth trying when the
live run happens.

**Done when** one Porchlights episode renders with some shots on local H3 and
some on the hosted model, from the same script. Without a key: tested end to
end on the fake backend (tests/test_router_render.py), and Porchlights ep02
sh180's request checked by eye (2026-10-10).

## Step 5 — every local target; continuity and deployments (partly)

- [x] LTX-2, LTX ingredients, Wan (I2V, TI2V, VACE), H3 FL2V on the portable
      graph: their staged inputs (keyframes, a composed reference sheet, the
      FL2V dialogue slice) go up as uploads (`jobs.stage_portable`,
      `make_portable`). The sheet helper runs in seriesmith's own Python
      (Pillow).

Done 2026-10-10, Porchlights ep02 sh180 in the scratch copy, h3pipe's take
against seriesmith's through the proxy, same seed:
- LTX-2: identical pictures. The sound differs, and differs just as much
  between two fresh seriesmith renders of the same graph after clearing
  ComfyUI's cache: LTX-2's audio isn't deterministic on this machine, whoever
  queues it. (So an untouched LTX-2 shot re-renders with the same picture but
  not the same sound.)
- Wan VACE: identical pictures, and byte-identical composed reference sheets.
- ltx2_ingredients wasn't tried: its checkpoint isn't installed here.

Moved:
- **Continuity** (`first: continuity`, `continuous: latent`) waits for the
  refs stage (now step 6): in h3pipe a shot's keyframes are ref takes with
  picks and freshness (h3refs), and the previous take a chain holds is found
  through the cut. With those ported, seriesmith -- which hands the GPU one
  job at a time and collects each take before the next -- cuts the first
  frame, or uploads the previous take's latent (else its mp4) to a portable
  chain node, just before staging the shot. Until then such shots render on
  local only, through h3pipe's nodes.
- **Deployments** wait for a Comfy API key, with the Router live run.

## Step 6 — the rest of h3pipe, as it is ✅

Every module after the core needs the others at load time (refs needs edit,
edit needs upscale, the editor's API needs nearly all), so they came over
together rather than stage by stage: refs, edit, source, promote, issues,
tour, track, align, upscale, master, post, assemble, publish, inspector,
kreagen, mksheet, the editor's API (`seriesmith/api.py`) and h3pipe's command
dispatcher (`seriesmith/h3cli.py`; `seriesmith <command>` reaches every h3.py
command). They behave as h3pipe does: where a stage isn't portable yet, it
talks to your local ComfyUI directly and uses h3pipe's ComfyUI nodes.

- Scripts that ran each other by file path run as package modules
  (`edit.tool_cmd`, still inside ComfyUI's embedded Python).
- The PIL/numpy helpers (reference sheets, tour stills, the 360 canvas) are in
  `seriesmith/helpers/` and run in seriesmith's own Python (Pillow, numpy are
  dependencies).
- The build checks the series config's upscale.master and post.master recipes
  again.

Done 2026-10-10: h3pipe's whole test suite, ported: 1226 passed, 12 skipped
(the ComfyUI route adapter until step 8; h3pipe's own node checks, which need
torch). Left behind: h3pipe's docs tooling tests (docs come later) and tests
of h3pipe's ComfyUI nodes, which stay in h3pipe until each stage is portable.
Tests that ran h3render against a fake ComfyUI render on seriesmith's fake
backend now (tests/fakes.py).

## Step 7 — the server, the queue and both hosts (the UI)

- [x] The server: the route table (h3pipe's comfy_nodes/h3pipe_routes.py)
      mounted by `seriesmith serve` (the ComfyUI host is written, and stays off
      while h3pipe's node pack serves the same routes).
- [x] The editor (h3pipe's `web/`): a standalone host beside the ComfyUI one;
      the layout (Shots/Refs sidebar, docked viewer, timeline).
- [x] Rendering from the editor through the backends; the queue: seriesmith's
      job list, one job at a time on local, several at once elsewhere; cancel,
      retry, reorder, pause; the jobs button and Jobs window with its Log;
      "Render on" in the top bar and the render dialog.

Done 2026-10-10: Porchlights ep02 sh180 (proxy), Render from the page's API on
`local`: queued, rendered through comfy-api-proxy, collected, 16 s; the Jobs
window shows it. Renders other than shots (refs, upscale, post, master) still
go to the local ComfyUI directly, as in h3pipe, until step 8 moves them.
- [ ] Series and season import: a series config and a stack of scripts.

## Step 8 — each stage portable, continuity, deployments

With the UI there to try each one:
- [ ] Refs and the 360 tour through targets and backends: the image targets'
      graphs portable, a portable ref saver; a Router image target.
- [ ] Continuity across backends: `first: continuity` cut before staging;
      `continuous: latent` with the previous take's latent (or mp4) uploaded
      to a portable chain node.
- [ ] Upscale, post and master portable (their nodes into seriesmith's pack).
- [ ] Deployments, and the live Router run (both need a Comfy API key; not
      before there is a UI to drive them from).

## Step 9 — leaving h3pipe behind

- [ ] Nothing of h3pipe's node pack needed: every node seriesmith's graphs use
      is in its own pack.
- [ ] The docs (AUTHORING.md and the rest) moved here, renamed where generic;
      the old h3 names inside the code (h3cli, the `h3` aliases) tidied away.

## Later

- The authoring docs (h3pipe's `docs/AUTHORING.md`) moved here, renamed where
  generic.
- The script-writing skill pointed at seriesmith.
- Publishing: the ComfyUI Manager listing for the node pack and the ComfyUI
  host; PyPI for the app.
