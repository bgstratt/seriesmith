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

## Step 7 — the server, the queue and both hosts (the UI) ✅

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
- [x] Series and season import: a series config and a stack of scripts, or a
      season's folder with each episode's own series config (POST
      /h3pipe/import; "Import series…" in the episode browser). Porchlights
      season 2 (10 episodes, each with its own config) imports and checks clean.

## Step 8 — each stage portable, continuity, deployments

With the UI there to try each one:
- [x] Refs through targets and backends: generating a ref (and Generate
      missing) from the page goes on seriesmith's queue; the image or audio
      target's workflow keeps its own SaveImage / SaveAudio, its reference
      pictures and voice sample go up as uploads, and the file that comes back
      closes the take (runner.Runner.enqueue_ref). Live 2026-10-10: a new
      four-view sheet of Crane (ep02 scratch) on krea2, through the proxy,
      ~15 s a view.
- [x] The 360 tour and kreagen's command line. A tour from the page goes on
      seriesmith's queue (runner.Runner.enqueue_tour): the location's plate is
      the graph's upload, and the video that comes back is kept and its holds
      found here. `seriesmith kreagen --backend <name>` makes each take on a
      backend (Runner.enqueue_ref, waited for) and picks as before. Live
      2026-10-10: a 6 s tour of diner_counter_morning (ep02 scratch) on
      local, two holds.
- [x] A Router image target: krea_2_router (krea/krea-2, the same family as
      the local krea2), one call per ref take on seriesmith's queue
      (Runner.enqueue_ref's hosted path); the picture comes back as whatever
      the provider sends (.jpg / .webp kept as such). Tested on the fake
      backend only: the live run waits for an API key, with the rest below.
- [x] Continuity across backends: seriesmith's queue stages a take when its
      job starts, so `first: continuity` cuts the first frame from the take
      the cut uses then, and `continuous: latent` uploads that take's latent
      (else its mp4, for the VAE) to SeriesmithChainLatent (comfy_nodes/
      chain.py, h3pipe's H3ChainLatent reading uploads). A chain queued at once
      runs in order: each job waits for the one it continues (queue `after`),
      on any lane. Live 2026-10-10: ep02 scratch, sq07 made a latent chain,
      sh140 then sh150 (proxy) on local: sh150 held sh140's last 39 frames.
- [x] Upscale, post and master through the queue: from the page they go on
      seriesmith's queue (runner.Runner.enqueue_finish). Their graphs are built
      as before and made portable when the job starts (finishing.py): the
      take's latent, frames, shotlist and keyframes go up as uploads, and
      SeriesmithSaveUpscale (comfy_nodes/upscale.py) reports the .up.mp4, last
      frame, latent and record, which come back beside the take. A continuity
      shot's upscale and a `continuous: latent` take's hold use the previous
      upscale if it has run by then (queue `after`); a post is stamped with
      the upscale it started from. Live 2026-10-10, sh180 (ep02 scratch) on
      local: a pixel upscale; an H3 latent re-sample whose frames and last
      frame are identical to the old direct route; a post (fresh); a master
      (the post waited for its upscale). The command-line upscale / post /
      master still queue on ComfyUI directly, and the compute nodes
      (H3PixelUpscale, H3FinishUpscale, H3HoldAudio, H3MotionBlur, ...) are
      still h3pipe's (step 9).
- [ ] Deployments, and the live Router run (both need a Comfy API key; not
      before there is a UI to drive them from).

## Step 9 — leaving h3pipe behind

- [x] Nothing of h3pipe's node pack needed: every node seriesmith's graphs use
      is in its own pack.
      - [x] The upscale and post compute nodes (comfy_nodes/finish.py:
            SeriesmithPixelUpscale, FinishUpscale, HoldAudio, FramesToBatch,
            MotionBlur), copied unchanged under seriesmith's names; live
            2026-10-10, sh180's latent upscale and draft + blur post came out
            frame-identical to h3pipe's nodes.
      - [x] The direct routes are gone: every render, ref, voice, upscale,
            post, master and tour goes through seriesmith's queue and a
            backend -- the editor's routes on the server's queue (an
            api.Context without one makes its own), the command line on its
            own in-process queue (runner.cli_runner, which starts the proxy
            for `local`; `master` always waits now). The runner refuses a graph
            that still names an h3pipe node (shotnodes.uses_h3pipe). A voice
            from ComfyUI's SaveAudio (flac) is kept as a wav. Records are
            written safely across the queue's threads on Windows
            (takes._shared, a lock per record). Live 2026-10-10: a render of
            ep02 sh140 from the server and a pixel upscale from
            `seriesmith upscale`.
- [ ] The docs (AUTHORING.md and the rest) moved here, renamed where generic;
      the old h3 names inside the code (h3cli, the `h3` aliases) tidied away.

## Later

- The authoring docs (h3pipe's `docs/AUTHORING.md`) moved here, renamed where
  generic.
- The script-writing skill pointed at seriesmith.
- Publishing: the ComfyUI Manager listing for the node pack and the ComfyUI
  host; PyPI for the app.
