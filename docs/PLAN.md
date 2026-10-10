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

## Step 4 — the first hosted render: Router

- [ ] A Router target kind: no workflow; a model string, an argument map, and a
      prompt writer (the `builtin:video_prose` writer to start).
- [ ] One video target (Seedance or hosted H3, whichever takes reference images)
      and one image target for refs.
- [ ] Choosing the backend: series config default, episode, sequence, shot,
      request (DESIGN.md, "Where a job goes"); `check` warns when a shot asks
      for something its target can't do there.
- [ ] Takes from a non-reproducible target say so.

**Done when** one Porchlights episode renders with some shots on local H3 and
some on the hosted model, from the same script.

## Step 5 — every local target, continuity, deployments

- [ ] LTX-2, LTX ingredients, Wan (I2V, TI2V, VACE), H3 FL2V on the portable
      graph.
- [ ] Continuity across backends: `first: continuity` from the previous take's
      last frame (uploaded), `continuous: latent` by uploading the previous
      latent; pixel fallback where latents don't exist.
- [ ] Deployments: building a target's workflow with its node packs and models
      (`comfy build` / `comfy deploy`), the deployment URL in settings, rendering
      there.

## Step 6 — takes, picks, cuts, overrides, notes

- [ ] Port `h3takes` (rest), the pick / override / cut parts of `h3edit`,
      `h3promote`, `h3source`, `h3issues` (notes that stay on a shot).
- [ ] CLI: `takes`, `pick`, `override`, `issues`.

## Step 7 — the server, the queue and both hosts

- [ ] The server: h3pipe's route table and API (`comfy_nodes/h3pipe_api.py`,
      `docs/API.md`), mountable on seriesmith's own server and on ComfyUI's.
- [ ] The queue: seriesmith's job list, one job at a time on local, several at
      once elsewhere; cancel, retry, reorder, pause; events to the editor.
- [ ] The editor (h3pipe's `web/`): a standalone host beside the ComfyUI one;
      the layout (Shots/Refs sidebar, docked viewer with A|B compare, timeline);
      the jobs button and Jobs window with its Log.
- [ ] Series and season import: a series config and a stack of scripts.
- [ ] `seriesmith serve`.

## Step 8 — refs and the 360 tour

- [ ] Port `h3refs`, `kreagen`, `mksheet`, `h3tour` onto targets and backends.

## Step 9 — finishing

- [ ] Upscale, post, master, publish, assemble; the recipe checks the build
      used to make (`build.RECIPE_CHECKS`).
- [ ] Align and track (a dialogue recording against the script), peaks.

## Later

- The authoring docs (h3pipe's `docs/AUTHORING.md`) moved here, renamed where
  generic.
- The script-writing skill pointed at seriesmith.
- Publishing: the ComfyUI Manager listing for the node pack and the ComfyUI
  host; PyPI for the app.
