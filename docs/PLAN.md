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
- **ComfyUI's own API is enough for a local job** (2026-10-18). `/upload/image`
  takes any file into `input/<subfolder>/`; `/prompt` queues the graph (a 400
  with `node_errors` when it can't); `/history/<id>` lists every file a node
  reported (the ui keys the proxy maps: `images`, `gifs`, `audio`, `text`,
  `files`, `latents`) and how the run ended; `/view` fetches each; `/ws` with a
  client id of our own carries its progress. So the local backend talks to
  ComfyUI directly (`backends/native.py`) and the proxy is opt-in
  (`local_via: "proxy"`).

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
  (Done in step 8: portable, on any backend.)
- Each run leaves its files in ComfyUI's output/seriesmith/<run>/ after they
  are copied into the take; the API can't delete them. (Left to you: those
  folders are copies, safe to empty by hand; an automatic cleanup was
  dropped, 2026-10-12.)

## Step 4 — the first hosted render: Router ✅ (live since 2026-10-11)

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
- [x] **Live** (2026-10-11): Seedance 2.5 on Porchlights ep02 (once its
      pictures went through the Seedance virtual library: BytePlus refuses a
      photoreal person as a plain link), hosted MiniMax H3 on ep03, a restart
      reattaching a run. Then the rest of Router, as step 14. `seriesmith render <ep> --only <shot>
      --target seedance_2_5 --dry-run` shows the request without a key.

Provider inputs can also be sent inline as base64 data URIs (the Seedance
docs), which would spare small pictures the Cloud upload; worth trying when the
live run happens. (Done in step 14: a target's `pictures.via` sends them as Cloud
links, inline, or through Seedance's virtual library; Veo 3.1 Fast takes them
inline.)

**Done when** one Porchlights episode renders with some shots on local H3 and
some on the hosted model, from the same script. Without a key: tested end to
end on the fake backend (tests/test_router_render.py), and Porchlights ep02
sh180's request checked by eye (2026-10-10). With a key: live 2026-10-11 (above).

## Step 5 — every local target ✅; continuity and deployments moved

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
- LTX ingredients (2026-10-11, once its LTX-2.3 checkpoint was installed):
  sh010, identical pictures and identical sound, and byte-identical composed
  reference sheets (the same sha1).
- Comparing it found the CLI's `seriesmith render` skipping continuity: the
  editor's render ran refs.refresh_continuity first, the CLI didn't, so a
  `continuous: latent` shot with nothing to continue was rendered as a fresh
  one. It runs it now, as h3pipe's h3render does (render.continuity_before_render).
  Both had let a shot wait on a take to come from a shot held in the same
  run (sh180 behind sh170, which had nothing to continue): seriesmith holds it
  too now, saying why (refs.hold_behind_held); h3pipe still doesn't.

Moved:
- **Continuity** (`first: continuity`, `continuous: latent`) waits for the
  refs stage (now step 6): in h3pipe a shot's keyframes are ref takes with
  picks and freshness (h3refs), and the previous take a chain holds is found
  through the cut. With those ported, seriesmith -- which hands the GPU one
  job at a time and collects each take before the next -- cuts the first
  frame, or uploads the previous take's latent (else its mp4) to a portable
  chain node, just before staging the shot. Until then such shots render on
  local only, through h3pipe's nodes. (Done in step 8, on any backend.)
- **Deployments** wait for a Comfy API key, with the Router live run. (The key
  came with that run, 2026-10-11; a deployment hasn't been run live yet: step 8's
  last item.)

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
      while h3pipe's node pack serves the same routes). Switched on 2026-10-11
      (f2c7352): seriesmith's node pack serves the editor inside ComfyUI, with its
      own queue and journal, Jobs, Render on and Settings (526065d).
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

## Step 8 — each stage portable, continuity, deployments (live but deployments: supported, not pursued)

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
      found here. `seriesmith refs --backend <name>` (kreagen's) makes each take on a
      backend (Runner.enqueue_ref, waited for) and picks as before. Live
      2026-10-10: a 6 s tour of diner_counter_morning (ep02 scratch) on
      local, two holds.
- [x] A Router image target: krea_2_router (krea/krea-2, the same family as
      the local krea2), one call per ref take on seriesmith's queue
      (Runner.enqueue_ref's hosted path); the picture comes back as whatever
      the provider sends (.jpg / .webp kept as such). Tested on the fake
      backend only: the live run waits for an API key, with the rest below.
      Live 2026-10-12 with the other Router image models (step 14), now driven
      by `builtin:router_image` like them.
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
- [~] Deployments: supported, not pursued (2026-10-18). A deployment is a pinned
      ComfyUI (custom nodes, models) behind the same Comfy API: seriesmith sends it
      the graphs it sends a local ComfyUI (`deployments` in the settings). Comfy Cloud
      now covers the no-GPU case ("Comfy Cloud: a shot as Cloud's own nodes"); a
      deployment would only add seriesmith's own nodes there (chains, kept latents,
      upscale and post), for an upload of the weights, cold starts and GPU-second
      billing. Not run live.

## Step 9 — leaving h3pipe behind ✅

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
- [x] The docs moved here and made seriesmith's: AUTHORING, SCRIPT_CONVERSION,
      EDITOR (the editor as its own page: Jobs, where shots render, the viewer,
      Import series), API (the server, the queue's routes and events), CONTINUOUS,
      POST_PROCESSING, RECORDED_DIALOGUE, KREAGEN; INSTALL (seriesmith, the proxy,
      the node pack; the model list generated as before); a new README, COMMANDS
      (h3pipe README's command chapters) and H3_TARGET (its Ref2VA reference);
      CONTRIBUTING. tools/ (make_prompts, make_models_md, sync_starter_doc) and
      tests/test_docs.py came with them; `python tools/make_prompts.py` writes
      prompts/ and the script-writing skill, seriesmith-episode-script, which
      bundles the build (scripts/check.py) so a script can be checked with nothing
      installed.
- [x] The skill's zip committed (2026-10-22): prompts/seriesmith-episode-script.zip,
      so installing it is a download, not a clone and a Python tool (and a Manager
      install has it in custom_nodes\seriesmith\prompts\). Stamped with
      pyproject's version, not the commit, so the same sources give the same zip;
      test_docs checks its text against AUTHORING.md, not the build it bundles
      (refreshed by make_prompts before a release).
- [x] The h3 names tidied away: routes /seriesmith/..., events seriesmith.*,
      seriesmith.commands (was h3cli), the h3<module> aliases, the config folder,
      SERIESMITH_* variables (each target's workflow override is
      SERIESMITH_<TARGET>_WORKFLOW), saved workflows seriesmith_<target>.json.
      Kept: the h3pipe-latent/1 header of latents on disk, H3_Ref2VA_Shotlist_v1.json
      and everything that really is MiniMax H3.

## Step 10 — forms instead of files ✅

The two authored files stay the source of truth (the text windows stay one click
away); forms read them, change only what they show, and save through the same
check, history copy and rebuild.

- [x] Series settings (Refs tab **Series**, Shots tab cog): title and id, fps,
      final and proxy sizes on the video model's grid, look, speech pace, dialogue
      mode and track, the video / refs / keyframe / voice models with what each is
      for and whether it's installed, the master and post recipes' main settings,
      the intro and outro; steps, LoRAs, model files, negative and backend under
      More. A new series' proxy is 896×512 (480p is the minimum that reads, and
      896×512 is 1344×768's exact shape; it was 864×480 until 2026-10-31, which
      the form itself flagged as another shape), and the form says when the shapes
      differ. Checked live on an imported Porchlights S2 episode: a proxy change
      saved as just those two lines, rebuilt, with a history copy.
- [x] Cast and places: a card per character, group, prop, vehicle, voice-only
      character and location (name, design, voice, description; variant /
      angle, picture file, layout, voice sample under More), with the Refs tab's
      own takes, generate, import and pick under it. Opened from a ref row's pencil,
      a group's **+**, or the series form's Cast and places (with a find box: a
      season's config has hundreds). A new one gets its id from its name and its
      picture path from the show's own layout (`../refs/...` or `refs/...`);
      Remove takes it out of series.json. Checked live: a new character added to
      an imported Porchlights episode wrote that one entry and nothing else.
- [x] The shot form: **+ Shot** and the pencil in the Shots tab, **Edit shot…** and
      **Add a shot after** in the context menu — sequence (or a new one, with its
      location), id in the script's own numbering, who / with (from the cast, or
      add one on its card), size, length on H3's grid, background, action, dialogue rows
      (speaker, V.O./O.S., how it's said), camera with a builder from H3's words,
      sound, extras, on-screen text; music, model, continuity, keyframes, audio,
      pace and render settings under More. Beside it, compiled as you type
      (`POST /seriesmith/shot/preview`, nothing written): the target, size,
      frames, the pacing meter and the prompt the model is told. Save rewrites only
      that shot's lines in the script (not overrides.json); Save and render queues a
      take on the current pass. Checked live: a new shot after sh010 of an imported
      Porchlights episode went in as sh015, seven lines and nothing else.
- [x] New series / New episode as a short wizard (Project folders): where (a new
      series' title and show folder; the episode's name and title), the series (a
      new one: id, video model, sizes, look, dialogue, pace), the cast and places
      (a next episode carries its neighbour's over; add what's new), the first
      shot. One POST /seriesmith/episode/new writes both files
      (`GET /seriesmith/episode/new` says what it starts from); the episode opens
      built. Checked live: a new series with one character and one location, then
      its ep02 carrying them over.
- [x] Pictures beside the names: the shot form's and the wizard's who / with
      chips and location buttons, and the series form's cast list, show each
      one's picture (a character's face: the sheet's last panel, since a
      three-quarter view won't read small; a group's, a one-picture character's
      or a prop's whole picture; a location's plate; initials until there is
      one), larger on hover; select… and the location buttons pick from the
      pictures. From the Refs list when it's loaded (a variant's derived sheet,
      the hash to refresh by), else the series config's paths. Checked live on
      a Porchlights episode's own sheets and plates.

## Step 11 — resilience ✅

A restart, a dropped connection or a hung job must never leave work stuck,
lose a paid result, or spend money twice. (Done before it: a record whose job
the queue lost is failed, not queued forever, f270b20 / 1de4e1d.)

- [x] A hosted run survives a network blip: Router's polling retries for a
      while before it gives up, and a run that loses its connection reattaches
      by its request id (models.handle) instead of failing a run the provider
      finishes and bills.
- [x] Paid runs are guarded: a batch on a paid backend (Router, Cloud, a
      deployment) asks first, saying how many calls; the Jobs window counts
      the paid calls this session; an optional cap in Settings stops new ones
      past it.
- [x] A hung job is stopped: each kind of job has a generous time limit, after
      which it is cancelled and failed (a stuck ComfyUI otherwise holds its
      lane for good).
- [x] Retry reattaches before it resubmits: a hosted job that may have
      finished is looked up first, so a retry doesn't pay twice.
- [x] The queue outlives the server: its live jobs are kept in a journal; on
      start, jobs that had reached their backend are reattached by their run id
      (local through the proxy, Cloud, deployments, Router: comfy-sdk's
      jobs.get / models.handle) and collected. Ones still waiting in
      seriesmith's queue had cost nothing: their never-run records are cleared
      and the request that queued them is asked again, narrowed to them
      (runner.requeue_plan: those shots, ref views, takes; Master and Generate
      missing as they were), in their order, so they keep their take numbers.
      Checked with the fake backend: a render stopped mid-run is collected
      after the restart without being sent again, and the two waiting behind
      it render again as their own t01.
      Checked live on the local GPU (2026-10-11): seriesmith stopped while
      an H3 render ran, ComfyUI left to finish it, seriesmith started again:
      the take was found again through comfy-api-proxy and collected
      ("picked up again after a restart"), not sent twice. The proxy keeps its
      jobs in its --state-dir and answers from ComfyUI's history, so a
      finished local job stays collectable until ComfyUI itself restarts
      (after that the proxy calls it expired; not tried live).
- [x] Disk space is checked before upscales and masters (they write gigabytes
      at 4K): a job that wouldn't fit says so instead of failing mid-write.
- [x] A step outlives the server too: a clip's "render once its pictures are
      made" and a frame's "draw its views" are made from plain parameters
      (api.STEPS), journaled, and made again on start once the requeued
      jobs are asked for; a step waits on its pictures' takes (queued, on a
      live job) rather than on job ids, which a restart changes. One that
      was running when the server stopped isn't run twice: it says so. The
      pictures a clip or a frame asks for are kept as their own requests
      (/refs/generate), so a waiting one is asked again as itself.

## Step 12 — simple mode ✅

A **Simple / Advanced** toggle on the editor, not a separate app: the same
projects, queue and takes underneath, with most of the settings out of sight.
The aim is a very easy way to queue clips: one video or image clip, a
multi-shot clip, or a series with episodes.

- [x] The toggle (remembered): Simple hides the render settings (steps,
      LoRAs, model files, seeds, profiles, policies, keyframe methods,
      continuity, finishing recipes, the text windows) and keeps choosing the
      model, writing the prompt, the cast, and queueing.
- [x] What you're making: a **standalone clip** (one shot, video or image), a
      **multi-shot clip** (a few shots in order, played and exported as one),
      or a **series / episode** (the wizard). The first two are a scratch
      project made on first use: an ordinary series config and script
      underneath, written by the forms, so refs, renders, takes, upscales and
      the queue work unchanged, and any of it can later go into a series.
- [x] Models: H3 for video and Krea 2 for pictures by default, with the full
      list to pick from (LTX-2, Wan, Z-Image Turbo, FLUX and the rest, local
      or hosted), each with a plain one-line note on what it's good at.
- [x] Adding a character, a location / background or a prop simplified: a
      name and a picture you have, or a name and a description to generate
      one; nothing else asked. (A picture you have is imported and picked; a
      character's is one whole picture, sheet_panels 1.)
- [x] A shot is a prompt box (what happens, what's said) with who and where
      picked by picture, a length, and Queue N takes; the takes come in beside
      it. POST /seriesmith/clip/queue makes the clip's missing pictures first,
      then a step waits for them, makes them live and asks for the takes.
      Checked live (the local lane paused): the place's picture and the
      waiting step queued in order.
- [x] Where without a place picked is **from description** (2026-10-22): the
      clip's own `c007_place`, the prompt in words, kept out of Where. A place to
      keep is **+ Create** (its card: a name, a picture or words), no quick form
      beside it; one decided on later comes from a frame of the clip. Was a
      words box and a "Make a picture of it first" box, whose place was saved as
      `c007_place` but hidden from Where (one such, with its plate, shows again).
      Labels: Who **select…** / **+ Create** (was add… / + Someone; select… in
      every cast picker), Where **+ Create** (was + Place). What a + Create's
      card adds is picked: the person into Who, the place as Where.
- [x] A picture: the clip's first keyframe (`first: generate`, marked
      `// a picture`) on the image model picked, its candidates made live as
      they finish; an edit model waits for the people's and the place's
      pictures it draws from. Several shots: one sequence (`c007a`,
      `c007b`, ...), each shot queued, played cut together (Play all limited
      to those shots). Checked live (the lane paused): two Krea 2 pictures;
      two shots of two takes each.
- [x] Projects (2026-10-16): **+ New project** makes a Simple project of its
      own, a show folder (`<Name>/<name>/`, its pictures in `<Name>/refs/`),
      so a piece of work keeps its clips, people and places together; the
      picker lists Simple's projects only (`"simple": true`, or Clips), so a
      clip never lands in a series' script. One take by default.
- [x] Length: a box for seconds, always on screen, filled from a menu of the
      shot form's lengths (what each suits), auto and model among them
      (LengthPicker: the shot form's and the wizard's too, whose "other…"
      never opened its box), with what the picked model renders shown:
      rounded up onto its frame grid, capped at its longest.
- [x] Size: the project's width × height for the pass on, typed or filled
      from a menu of common sizes (H3's, 480p / 720p / 1080p, vertical,
      square), written as the project's model takes it, with what the clip's
      model renders shown. (A size per clip would need a script key.) The New
      take dialog and the inspector's override ask the same way (SizePicker).
- [x] A look of its own (2026-10-16): warm paper, light and dark (the
      standalone page's palette; inside ComfyUI, its theme), DM Sans with
      Newsreader for titles, cards, rounder controls and windows. Simple mode
      as the mockups chose: the project as the panel's title (a dropdown over
      its name, cut off rather than wrapped), who and where inside the What
      happens card, a settings card, one Generate button (one take a click:
      no Takes), the clips as a thumbnail grid.

## Step 13 — a character (or a place) from a frame ✅

Once a clip exists (rendered or uploaded), the best reference is often a
frame of it: scrub to the moment the character reads well and make their
pictures from that, so a look found by accident becomes the look kept.

- [x] Scrub any take in the viewer and **Character or place from this
      frame…** (its right-click): the frame is kept as a candidate (refs.
      frame_into, which the continuity keyframes use too).
- [x] **New character from a frame**: the frame goes to an edit model (Qwen
      Image edit, Z-Image Turbo, FLUX.2 Klein edit; the series' keyframe or
      refs model by default) with an instruction made from what you say
      ("the woman in the red coat, on the left"): the one person cut out onto
      a plain background, full figure. That picture becomes the new
      character's first candidate; the four views (three-quarter, side,
      back, face) are then drawn from it, as a variant's are from its base,
      and stitched into the sheet. Name and design asked as in Simple mode,
      the design suggested from the picture.
- [x] **Update a character from a frame**: the same, as a new candidate of
      an existing character (its sheet, or one view), beside today's ways:
      generate from the design (Krea 2 and the other text-to-image models)
      or edit a picture it has (Edit, with other refs' pictures as image 2
      onward).
- [x] **A place from a frame**: the frame with the people removed (the edit
      model again: "the empty room"), as a location's plate; or a location
      described in words given its first picture this way.
- [x] A clip's character or place written in words can be given its picture
      this way after the fact: the shots after it keep it (step 12's
      words-only places and people). (For one there is: its first picture.)

How (POST /seriesmith/refs/from-frame): the frame becomes a candidate of the
ref (a character's three-quarter view); an edit of it on an edit model, with
an instruction made from who you point out, makes the reference; for a
character a step then draws the other three views from that one (an edit
from_view, refs.VIEW_FROM), and for a new one a last step picks each, so the
sheet stitches. Not the Qwen angles LoRA (`turn`): it isn't always
installed; any edit model works this way. Checked live (the lane paused): the new character written,
the frame in as t01, the cut-out queued and the views' step waiting.

Run live on the local GPU (Second Light, 2026-10-11): a place from a frame on
FLUX.2 Klein edit took the girl out of the pond cleanly; a character's cut-out
on Klein left a ghost of the scene behind her and kept the frame's crop, while
Qwen-Image-Edit Rapid with a firm background instruction gave the whole figure
on clean grey, and its side, back and face views drawn from that matched it.
So a character's cut-out (and its views) default to Qwen Rapid when it's
installed. Tours: "walks along the dock" barely moved; "pushes in with large
amplitude" went the dock's length into the meadow: the presets now use H3's
camera words, and the box says which words it follows.

- [x] **A video of your own**, not just a take: the Refs tab's Add, **From a
      video…** picks one on this machine (Browse, any size) or uploads it
      (up to 64 MB); it's kept in the show's refs/_videos/ (POST
      /seriesmith/refs/video; GET /seriesmith/refs/videos lists them), played
      and scrubbed in the same window, and the frame the player shows is
      taken by time (refs.frame_from_video: ffmpeg -ss before -i decodes to
      it). Everything after is the frame's way above. Checked in the
      browser: a clip uploaded, scrubbed to 4.5s, made a new place's plate.

## Step 14 — hosted models as data, limits, your own workflows ✅ (2026-10-12)

- [x] **Router models as data:** `builtin:router_video` / `builtin:router_image` drive
      any Router model from its target.json `router` block (where the prompt, pictures,
      length, size, seed and sound go); `router_inspect` proposes one from the model's
      published schema (video, refusing text-to-video; image), and flags the fields written
      for several models, where a limit hides in prose.
- [x] **Live, on Porchlights ep03:** video — Seedance 2.0, Kling v3 Omni and Video O1,
      Wan 3.0, Runway Gen-4 Turbo (its prompt: no quoted lines; it makes no sound) and
      Veo 3.1 Fast (a prompt over ~1000 characters fails; pictures inline); image — Nano
      Banana Pro and 2.1, Gemini 3.1 Flash, Seedream 5.0, GPT Image 2, Flux Kontext Pro,
      Flux 2 Pro, Qwen Image 3.0, Kling Image O1 (each on sh350's keyframe), Krea 2.
      Shipped as built-ins (`tools/make_router_targets.py`); untested ones as drafts,
      switched on per machine (`enabled_drafts`).
- [x] **Limits:** one form for every video model and hosted image model
      (`seriesmith/limits.py`); a built-in's changes kept per machine (`target_limits`).
- [x] **The Models window:** reached from every model picker; the Router catalog picker,
      a free dry run of a proposed model, models for every show (the user folder).
- [x] **Your own workflows:** any save node (read from /object_info), image workflows as
      models for refs (their LoadImage nodes the take's pictures), the reading's notes as
      errors, warnings and info. Live: Wan 2.2 5B from a SaveWEBM workflow rendered sh350.
- [x] Jobs say where Router has a take (waiting, its place in line, running); a cost the
      provider reports is recorded in its own units. `seriesmith stop [--restart]` and
      Settings' Stop / Restart for the standalone server.

## The editor: its look, and loading fast (2026-10-16)

The look Simple mode set (step 12) carried into Advanced, and an episode of a
big show (Porchlights: 13 episodes on one `../refs`, ~280 shots, ~480 refs
each) made quick to open.

- [x] One head for the sidebars (ProjectHead): what is open as the panel's
      title, its series above it, a dropdown over its name whose last choice
      is **Browse and add new…** (Project folders: New series/project…, New
      episode…, Import series…). Shots and Refs tabs; the timeline keeps its
      small dropdown. The sidebar runs full height on the standalone page, as
      in ComfyUI, the timeline under the viewer.
- [x] Shots: the toolbar in groups, the episode's work in one card (model,
      pass, Build, Re-render stale, a wide Generate missing, progress), and
      **List / Board** (remembered): the board each sequence's shots as
      pictures, each with its length, status and the first sentence of what
      happens (`action` in the episode status, from the script).
- [x] Refs: the models folded to a "Made with" line; each group's add button
      labelled (+ Character, + Prop, + Place, + Voice); **List / Board**, the
      board's head a ring of how many are made and chips for one group, each
      group ending in an add tile. A character shows its face (its face
      view's pick, else three-quarter, else the sheet's face panel); a
      one-picture character (`sheet_panels: 1`) its whole picture, and one
      marked so whose picture is a strip of panels says so (`panels_conflict`:
      renders send the whole strip; the card no longer marks a supplied sheet
      one picture).
- [x] A shared ref whose live file another episode picked lists that
      episode's candidates, read-only, when its row opens (**From ep01**,
      `GET /seriesmith/refs/owner-takes`).
- [x] Readiness asks for the nodes a job sends (seriesmith's loader, saver
      and chain nodes; an image or voice workflow's own SaveImage / SaveAudio),
      not h3pipe's, which no render needs; H3 Ref2VA's workflow is on
      seriesmith's nodes.
- [x] Loading, measured on Porchlights (refs: 12-23 s the first time, 3-10 s
      after; now ~1 s the first time after a restart, 0.5-0.8 s after):
  - [x] targets.one_load(): a load works each target answer out once (a
        listing had built the image model list 3,185 times); the series
        config and the refs list too.
  - [x] A folder resolved once, not each of a show's ~57,000 files (on
        Windows a realpath is a system call: 9.5 of 11.7 s cold).
  - [x] diskcache: file sha1s and each sibling's live files kept in the
        settings folder's cache/ between runs, by the files' own stamps.
  - [x] Thumbnails (`GET /seriesmith/thumb`): the Refs tab drew full-size
        pictures (722 MB for one episode); now JPEGs made once (1.15 MB), on
        two threads of their own, asked for only when near the screen.
  - [x] Replies over 64 KB gzipped (the refs listing: 2.8 MB, 0.12 MB sent).
  - [x] The refs listed before the sweep (on a thread after the reply), and
        asked for as soon as an episode's shots are in.
- [x] The rest of Advanced in this look (2026-10-17): the inspector and New
      take as cards (Generate, Generate proxy take), Settings with a dot for
      what answers, Jobs a card per lane with a picture per job, the open ref
      row a card, every two- or three-way choice a sliding toggle, the
      timeline's toolbar grouped and its badges soft chips. The clips stay
      square and the sound stays waveforms.
- [x] A size per clip in Simple mode (2026-10-17): Generate renders at the
      boxes; a clip at another size than the project's keeps it as its size
      override (as Inspect shot saves one); Save as the project's size makes
      it the default. The editor inside ComfyUI looked at: fine. The timeline's
      drawing: not a concern (it draws after the shots and renders).

## The thirty-second install (2026-10-18)

Clone, link `comfy_nodes` into ComfyUI, start ComfyUI: the editor is there and
renders. Or start `run_seriesmith.bat` beside it. No pip into ComfyUI, no proxy,
no other node pack; the default models are the ones installed.

- [x] The node pack finds the seriesmith package in the repo it is linked from
      (the junction resolved), so the editor inside ComfyUI needs nothing in
      ComfyUI's Python (it has aiohttp, Pillow and numpy; comfy-sdk is only for
      Cloud and Router, imported when used).
- [x] The local backend straight to ComfyUI (`backends/native.py`): uploads by
      content to `input/seriesmith/`, `/prompt`, status and outputs from
      `/history` as the proxy reads them, progress over `/ws`, cancel, and
      attach by prompt id after a restart. comfy-api-proxy stays, behind
      `local_via: "proxy"` (Settings → Through comfy-api-proxy). Inside ComfyUI
      the local backend is that ComfyUI on its own port (`Settings.host_url`),
      which fixes the proxy having been pointed at `comfyui_url` there.
- [x] `run_seriesmith.bat` / `_ext.bat` / `run_seriesmith.sh` make the repo's
      `.venv` and `pip install -e .` on their first start.
- [x] `H3SLAAttention` (ComfyUI-PlagueKind-Nodes) optional: the binding's
      `bypass_if_missing` splices it out where ComfyUI hasn't it (the take
      notes it), and readiness calls the target degraded. The location tour
      still needs it.
- [x] The default models from what's installed: target.json `default_rank`
      orders the local candidates; each host, when ComfyUI first answers (and
      on each readiness check after), keeps the first ready one per kind
      (else the first degraded) in the settings' `detected_targets`;
      `targets.machine_default` is the user's `default_targets` (Settings),
      else that, else H3 Ref2VA / Krea 2. A series naming no model renders on
      it, and a new series (the starter, the wizard, Simple mode) is given it
      in its series config. Router models are never picked by themselves.
- [x] comfy-sdk put in when it's needed (`seriesmith/sdk.py`): Cloud,
      deployments and Router run on it, nothing else does, and ComfyUI's
      Python hasn't it. Saving a Comfy API key (or starting with one set)
      pip-installs it into the running Python in the background, once; the
      Settings window says how it went and has Install; Render on says why
      those backends are down meanwhile. `SERIESMITH_NO_AUTO_INSTALL=1` turns
      it off (the tests set it). Tried in a fresh venv: 8 s, importable at
      once, no restart.
- [x] The Features window (Settings → Features…, and Install in What's missing):
      every feature of FULL_SETUP.md as a checkbox, installed ones ticked;
      model files downloaded into ComfyUI's models folders (resumed from a
      .part, the Hugging Face token for the gated ones), node packs cloned into
      custom_nodes with their requirements pip-installed into ComfyUI's Python
      (then a restart), pip packages, a full ffmpeg build (gyan.dev / a static
      Linux build) that seriesmith.ff uses first. The catalog
      (`seriesmith/features.py`) takes each target's files from the target, and
      only ever downloads URLs the code records; the node packs' repos and the
      last few download links (Real-ESRGAN, SDXL base, the 360 and Turn LoRAs)
      are recorded now. Checked 2026-10-18: every recorded link answers; 16 are
      gated (all of LTX-2.5, all of Black Forest Labs'). Tried for real into a
      scratch ComfyUI folder: RAFT downloaded, PlagueKind cloned (restart),
      gyan.dev's ffmpeg 9.0.2 downloaded and used first.
- [x] Nothing downloads behind a job's back (2026-11-02): what a package would
      fetch by itself the first time it runs is a Features line (kind `hub`,
      `seriesmith/hubcache.py`) downloaded where that package looks, and the job
      refuses until it's there. faster-whisper's models (the Hugging Face cache;
      align reads them with local_files_only, 409 / exit naming the Features
      line), demucs's htdemucs (torch's hub cache; the foley strip skipped with a
      note, demucs run offline for the Hub), the vocal stem's Hybrid Demucs
      (models/demucs or torchaudio's own copy, never the bundle's download),
      ComfyUI-MMAudio's BigVGAN (two files into models/mmaudio/nvidia, not its
      4 GB snapshot) and HunyuanVideo-Foley's SigLIP2 and CLAP (target.json
      `fetches`: readiness not_ready, a bed or effects take refused on this
      machine's ComfyUI). The Hub's files fetched one by one through the
      installer's download (stdlib; huggingface_hub's own layout, refs/main last).
- [x] MOSS-Image as two image targets (2026-10-18): `moss_image_sft` (the one
      to draw with; default_rank 55, after FLUX.3 Klein) and `moss_image_base`
      (for LoRAs trained on the base; never a default by itself). ComfyUI 0.41's
      own support (CLIPLoader type moss_image, the FLUX.2 latent), the model
      card's 50 steps, cfg 3, euler, shift 5; the int8 files by default, the
      bf16 ones by family. Rendered on the RTX 5090: 28 s a 1024x1024 picture.
- [ ] Tried on a fresh ComfyUI portable with only LTX-2's files: Simple mode
      defaults to LTX-2 and renders; then H3's files without the PlagueKind
      pack: H3 is the default, degraded, and renders.
- [x] A render without ffmpeg: the saver's mp4 through PyAV (`encode_av`, `av`
      is in ComfyUI's requirements) when `ffmpeg` isn't on PATH. Measured
      against the ffmpeg command on 73 frames at 864x480: the same H.264
      yuv420p, BT.709 tv-range tags, frame count, red at Y 63, and AAC; 0.70 s
      against 0.49 s.
- [x] No ffmpeg to install at all: every `ffmpeg` / `ffprobe` command goes
      through `seriesmith/ff.py` (the node pack through `comfy_nodes/_ff.py`).
      `ffmpeg`: PATH, else imageio-ffmpeg's static 7.1 build (now a dependency;
      it has libx264, aac, NVENC, drawtext, scale, concat, amix and everything
      else the graphs use), else the repo `.venv`'s. `ffprobe`: PATH, else
      `helpers/ffprobe_av.py` on PyAV (also a dependency), answering the 14
      ways seriesmith asks (json, csv, default; -count_frames / -count_packets;
      -show_data's extradata dump) as ffprobe does: compared field for field on
      12 files (takes, upscales, hosted renders, old untagged takes), no
      difference. The ffmpeg tests run with no ffmpeg on PATH.

## Comfy Cloud: a shot as Cloud's own nodes (2026-10-18)

Comfy Cloud runs a curated node set (its /api/object_info: 3795 classes, the core
MiniMax H3 and SeedVR2 nodes and every open-weights model file our workflows load,
not seriesmith's pack or PlagueKind's), so a workflow target's shot goes there made of
Cloud's nodes (DESIGN.md, "Backends"; SETUP.md, "Comfy Cloud").

- [x] The loader's decisions in `comfy_nodes/shotplan.py` (standard library only),
      used by the loader node and by seriesmith (`shotnodes.shotplan()`). The node's
      outputs are unchanged: the old and new loader compared in ComfyUI's Python on
      390 cases (four shows' shotlists; every panel mode, clone, dub, a dub window
      with a held head, missing refs, declared panels, plate only, a bad width),
      every tensor and value equal.
- [x] `seriesmith/cloud.py`: the loader's pictures (cut to their panels) and sounds
      (the recording's slice, sample-exact) as LoadImage / LoadAudio uploads, its
      values written in; the saver as CreateVideo + SaveVideo (H.264 CRF 16, BT.709)
      and SaveAudio; the take's thumbnail, strip and record made here; a
      `bypass_if_missing` node Cloud hasn't spliced out; anything else it hasn't,
      refused before anything is sent. Workflow targets run on `cloud`
      (`GRAPH_BACKENDS`); a job for Cloud is planned against Cloud's model lists, so
      H3 renders its base preset there (20 steps, res_multistep, no LoRA: Cloud has
      no 8-step Ref2VA LoRA). `render --dry-run --backend cloud` writes the graph.
- [x] Live 2026-10-18, LAST LIGHT sh040 (a copy), 73 frames: the Cloud graph on the
      local ComfyUI first (2:42 on the RTX 5090, free), then on Comfy Cloud (1:56 from
      queueing to the take): mp4 BT.709 with H3's sound, `_h3.wav`, thumbnail, strip,
      record with the loaded refs.
- [ ] Not on Cloud yet: `continuous: latent` shots (the chain nodes), a take's latent,
      PNG frames, the foley bed; refs, tours, upscales and posts on Cloud (their graphs
      use the pack's nodes or keep theirs; untried there).

## Presets as pictures: relighting refs, the series' look (2026-10-19)

Comfy-Org's comfy-cinematic-studio (a Router sample: four dropdowns of fixed phrases joined
into one FLUX.2 Pro prompt) was looked at for what to borrow. Its per-image light and lens
axes aren't needed in the script: the look line and the location's own light already carry
them, and the plate carries a shot's light. What is worth having is the picking: presets
shown as pictures, each filling a text that stays editable.

- [x] `seriesmith/presets/`: `relight.json` (24: time of day, weather, light setups, and
      portrait lights for a figure only), each with a plate's wording (`place`, naming the
      sources the light comes from) and a figure's or prop's (`subject`); `look.json` (13
      look lines written as a DP's brief: live action, animation, illustration). The old
      edit window's seven text buttons (Dawn ... Rain) are among them, unchanged.
- [x] `GET /seriesmith/presets`, `GET /seriesmith/presets/image` (both hosts).
- [x] The editor: the edit window's Relight is a picker of picture tiles in the ref's
      wording (plates wide, figures square); the series form's and the new-series wizard's
      Look gets the same, open while the look is empty. A pick fills the text; the text
      stays the person's to edit.
- [x] `tools/make_preset_samples.py`: the sample pictures rendered with seriesmith itself on
      a scratch episode (the starter): each look on one scene, each relight on a base plate
      and a base figure through an edit model; small JPEGs in `presets/img/`.
- [x] The samples rendered on this machine (2026-10-19): looks on Krea 2, relights on FLUX
      Kontext; nine wordings rewritten after the first pass, where Kontext crushed a night to
      black or recoloured a figure (a relight now names something visibly lit, and a figure's
      keeps its hair and clothes' colors). Four (night, moonlight and top light on the figure,
      the flashlight on the plate) are FLUX.2 Klein edit's: it relit them where Kontext
      couldn't, keeping the figure's own colors. Klein is the better relighter of the two.
- [x] Sequence relight (2026-10-19): a relit plate is a location with `of:` + `relight:` (a
      preset id or the instruction), generated as an edit of the source's plate
      (refs.built_prompt: edit_prompt of the relight; refs.angle_reference_images). One request
      (`POST /seriesmith/refs/relight`, `seriesmith/relight.py`) writes a sequence's relit
      locations, queues their edits and can re-point the sequence (`# sq` line, `plate:` lines).
      The Shots tab's sequence header: **Relight…**. Checked on Klein (porch -> dusk).
- [x] Genre looks (2026-10-19): western, thriller, road movie, horror, fantasy, romance, war,
      Technicolor musical, 80s VHS (`group: genre`). A look may carry its own sample `scene`
      (the genre's setting around the same woman in red); the look line stays light, lens,
      grade and stock, so a series' own locations decide the setting. The genre-like looks
      (neo-noir, sci-fi, period, documentary, b&w noir, 70s) got scenes too.
- [x] Your own presets (2026-10-19). Looks and relights of yours for every show on this
      machine: `presets.json` beside the settings file, pictures under `presets/<kind>/`
      (`presets.save_own`, `POST /seriesmith/presets/own` and `/own/delete`), listed under
      **Yours**. Saved from the look field (with its builder picks), the edit window's Relight,
      or an edited take (its picture becomes the tile); a sequence relight offers them too.
      Profiles, per series in its series config, now carry `look` (words added to the look)
      and `lens`: `parse_story(styles=series_config.profile_styles(cfg))` opens each shot's
      action with them (shot line, shot profile, sequence line, sequence profile). Series
      settings' **Profiles** section edits them; New take's **Profile…** applies one to a take.
- [x] Pictures for your presets (2026-10-19), only when asked (`preset_pictures.py`):
      rendered on the sample scene on a model you pick (a scratch episode beside the
      settings; a relight edits the shipped bases, `presets/img/base/`), a frame of a shot's
      take or a ref's picture, or a picture you import. `POST /seriesmith/presets/own/picture`
      and `/own/render`; the list makes a finished render the tile.
- [x] "Save as profile…" from the shot form (2026-10-19): the shot's lens, video model, model
      file, LoRAs, steps and `sla:` as a profile (`lib/profiles.ts` profileFromShot), the
      series config saved, the shot put on it with those lines taken off (shotOnProfile).
- [x] A per-shot `lens:` (2026-10-19; also under a `#` header): the look builder's Lens row
      and `deep` (core/framing.py LENSES, a test keeps them equal to look_builder.json). The
      IR shot's action opens with the lens sentence, so every target reads it with no code of
      its own. The shot form: **Lens** beside Framing, with the builder's pictures. The test
      (8 H3 shots, one seed, a plate as the reference): only shallow focus visibly changes the
      picture, anamorphic a little; the plate fixes the geometry, so wide, long and tilt-shift
      barely show. Kept as a full list anyway: other models may follow more.

## Shot direction as pictures: framing and camera moves (2026-10-19)

- [x] `presets/framing.json` (the nine `size:` values, each with how much the frame holds)
      and `presets/camera.json` (the 20 moves the `camera:` line starts with, grouped:
      still, dolly, zoom, pan and tilt, truck and pedestal, around, handheld and roll).
- [x] Their samples, made by `tools/make_preset_samples.py`: each framing on Krea 2 (the same
      woman and street at every size); each move as a shot of a scratch episode rendered by
      `seriesmith render` on H3 (the base plate, the woman written into the action), its
      take made a 360 px silent loop. A move's sample is rendered with large amplitude so
      the clip shows it (the tile still hands over the plain move); the extreme close-up is
      cut from the close-up's render (`crop`), as Krea 2 won't frame the eyes alone. Pull out
      and tilt down were faint on the turbo over three seeds (see below).
- [x] The shot form: **Framing, as pictures** under Framing; **Camera moves, as clips** in
      Camera (a clip plays while pointed at; a pick starts the line with the move, its
      amplitude and speed still the menus beside it).
- [x] The angles as framings (2026-10-19): `pov`, `ots`, `low`, `high` in core/framing.py,
      named by H3's guide beside the sizes; medium for the plate and sheet, outside ORDER, so
      never a jump cut. AUTHORING's size table, the shot form and four more framing tiles.
- [x] A camera line says where it goes: AUTHORING's camera section (the guide ends every move
      on what it travels toward or reveals; a large move wants slow speed; a truck or pedestal
      reads by its foreground), and the builder's **where it goes** box. The camera samples
      were redrawn so: each with its own line (`sample` in camera.json), a starting framing that
      suits the move, and a longer, smaller move where H3 flickered (every fourth frame, its
      latents) on a big one in three seconds; measured, not eyeballed (frame-to-frame brightness).
      Pull out, pan left and tilt down are H3's base preset (20 steps, res_multistep, no turbo
      LoRA, no SLA attention: the Cloud-shaped graph run on this machine): the 8-step turbo
      left them faint or flickering, the full model made each move whole and steady (largest
      frame-to-frame jump 0.9-2.5). For a big camera move, H3's base beats its turbo.
- [x] The turbo off renders the full model (2026-10-19): `lora: none` (a shot, a sequence, a
      profile, the series) where the pass's LoRA slot holds an accelerator takes the path a
      missing turbo takes, the pass's base preset (its steps and sampler; a shot's own steps
      win). It needs no model list. AUTHORING's `lora:` row and a `full` profile for big moves.
- [x] `sla: off` (2026-10-19): a shot's, a sequence's, a profile's or the series' switch that
      splices out the target's `bypass_if_missing` nodes (H3's sparse attention); on by
      default, turbo or not. Measured on pull out, same seed, 20 steps, no LoRA: with SLA
      1:16, without 2:02; both moves whole (first-to-last change 83 / 82); largest
      frame-to-frame jump 13.2 with, 2.6 without. So SLA stays on the full model unless a
      shot wants every frame smooth.
- [x] The look builder (2026-10-19): `presets/look_builder.json`, six rows (medium, camera,
      lens, film, light, grade), each option a clause of the brief and a sample picture (the
      looks' scene in a live-action base with only that option set). `compose_look` (and
      `lib/lookBuilder.ts`, the same strings tested on both sides) joins the medium and the
      picks by semicolons, a drawn medium folding the camera rows away. The 13 look presets
      carry `parts`, so one sets the rows. Series settings and the wizard: **Build the look**;
      the picks in `style.look_parts`, rewriting the line only while it's theirs.
- [x] No people in a look (2026-10-23): the look opens every picture's prompt, an empty
      plate's too, and "soft rounded character design with expressive faces" drew round
      little people into a moonlit garden. Six looks and builder clauses reworded to say how
      things are rendered (forms, surfaces, tones); test_presets refuses characters, faces,
      figures, skin or people in any of them; AUTHORING says so for a look of your own. The
      ref's panel is **What the model is told, and settings**, as it holds the whole prompt.
      A series keeps the line it copied: re-pick the look, or edit `style.look`. The sample
      pictures weren't re-rendered (the same looks, reworded). Then places and things too
      (2026-10-23): neon noir's "night streets lit by neon signs" turned a lighthouse shot
      into a close-up of the lighthouse; ten more looks and builder clauses reworded
      (lamps, windows, skies, vistas, smoke, puppets, silhouettes), and the test refuses
      those as well. The shot form's Lens says it's one sentence of the shot's prompt, which
      a plate's own focus can outweigh on H3.
- [x] A per-shot lens beside framing: `lens:` (2026-10-19, under "Presets as pictures" with
      the sequence relight).
- [x] Relights light what's there (2026-10-23): a place relight that named its source
      ("the street lamps lit", "a brazier burning") drew it in; the sources became "any …
      already there" or off-frame, and the "add nothing new: no lamps, signs…" tail was
      dropped again (a negation still puts the word in the prompt). Both dialogs warn.
- [ ] Relights that name no fixture at all: dusk and night still say "any windows or lamps
      already there", neon "as if from neon signs off-frame", streetlight "street lamps just
      out of frame". Describe only the light ("warm pools of light", "hard orange sodium
      light from above")? Needs a test pass across plates with and without lamps first.

## Refactor pass ✅ (2026-10-20)

Fixes, speed, duplicated code combined and the architecture standardized, item by item
with a live check each (PRs #16-#28): the record is [REFACTOR.md](REFACTOR.md), the
architecture it arrived at is in DESIGN.md. Among what it changed: an episode opens in
about a second (Porchlights ep01's final pass: 7.4 s before), Master and Align are queue
jobs with Cancel, the command line keeps the paid limit, and every align that had to
transcribe works again.

## FastH3 Omni and Fibo 2.0 (2026-10-20)

- [x] `fasth3_omni`: FastVideo's 8-step distilled H3 (FastH3-Omni-Comfy) as a target of its
      own, compiled by Ref2VA's code with the node's nine picture sockets: eight subjects
      and the plate as `<Picture 9>`. Ref2VA keeps three and `<Picture 4>`; the compile
      reads the slots from the target it is given, the shotlist's
      `defaults.subject_slots` tells the shot plan (only when not 3, so Ref2VA's shotlists
      are unchanged), and the Shot Loader's extra subjects are its last outputs
      (`ref_4`..`ref_8`), so no existing output moves. No turbo LoRA; shift 12 / 3; ComfyUI's
      `BlockSparseAttention` in `vsa` mode at 10% in place of SLA (the checkpoint carries
      VSA's gate tensors, which also tell it apart from the other H3 files).
- [x] `fasth3_omni_still`: the same model as an image target, as `minimax_h3_still`.
- [x] `fibo2_dev` / `fibo2_edit_turbo`: Bria's Fibo 2.0 on ComfyUI's native support
      (TextEncodeFibo2; ComfyUI after 2026-10-20). Dev is text to image and edits (so
      relights) at 50 steps / cfg 5; the Edit Turbo is edits only at 4 / cfg 1 and refuses
      a job with no picture. Non-commercial licence.
- [x] Live, 2026-10-21: an Omni shot with four subjects (two characters, a prop, a vehicle
      through the loader's `ref_4`) and an Omni still, on local ComfyUI.
- [x] Live, 2026-10-21: a Fibo 2.0 Dev relight of Ballroom ep02's right-of-way plate to fog:
      it works well; 50 steps is slow, worth it where quality or style matter.
- [x] Seedance takes what it can: 2.5 up to 30 reference pictures (BytePlus: 30 images,
      10 videos, 10 audio clips), the 2.0 family 9 (`tools/make_router_targets.py`), where
      both sent four subjects and the plate. A shot's extra subjects past the cap still
      drop silently.
- [x] Seedance's prompt defines each picture first, as BytePlus's prompt guide asks: "Define
      [core features] in @Image N as <label>", numbered from 1 within each type in the
      request's content order; asset ids can't stand for a picture in the text
      (`router_video.definitions`; `references.define` on the Seedance targets). A subject's
      features are its design's opening clauses without what describes a body: BytePlus
      refused a prompt that opened with one (content_policy_violation), where the same prose
      had passed. Live 2026-10-21, Ballroom-refactor sh010 (Cindy, Ella, the ballroom) on 2.5:
      each matches her own picture, on her own side of frame. The library keeps a picture
      registered by its hash (the same asset id on a second registration); each take still
      uploads and registers its pictures again, ~4-5 s each, which keeping the ids would skip.

## The ComfyUI Manager listing (next; 2026-10-21)

seriesmith's node pack in the Comfy Registry (registry.comfy.org), so ComfyUI-Manager
installs it: the editor inside ComfyUI with no clone and no link. Registry rules
(docs.comfy.org/registry: specifications, publishing, standards): the repo root is the
pack (`comfy node publish` zips every git-tracked file, less `.comfyignore`, plus
`[tool.comfy].includes`); pyproject `[project]` name, X.Y.Z version, repository URL and
`[tool.comfy]` PublisherId; Manager pip-installs `requirements.txt` into ComfyUI's Python at
install; banned: eval/exec, obfuscation, "runtime package installation through subprocess
calls", interfering with other packs' installation. A published version can't change.
ComfyUI loads a folder pack under its full path, so a folder named `seriesmith` doesn't
collide with the package.

- [x] **The whole repo is the pack** (not a second repo): a root `__init__.py` re-exporting
      `comfy_nodes` (its `WEB_DIRECTORY` as `./comfy_nodes/web`); `[tool.comfy]` in the
      existing pyproject (PublisherId `bgstratt`, DisplayName, Icon: docs/site/favicon.png
      on GitHub); a `.comfyignore` dropping `/tests/`, `/docs/`, `/tools/`, `/web/`,
      CLAUDE.md, CONTRIBUTING.md (anchored: a bare `web/` dropped `comfy_nodes/web/` too).
      A root `__init__.py` leaves pytest's collection as it was (1641 tests, the same
      names). `comfy node validate` passes (its ruff check: S102, S307, E702);
      `comfy node pack` makes 406 files, 11.5 MB, both built editor pages in. Loaded from
      the zip by ComfyUI's own `load_custom_node` (2026-10-21): 12 nodes, the web folder
      found. The pack's own seriesmith now comes first on sys.path: an editable or older
      pip-installed seriesmith (this machine has one in ComfyUI's Python) had answered
      instead.
- [x] **requirements.txt:** comfy-sdk and imageio-ffmpeg, what ComfyUI's Python lacks of
      seriesmith's needs (ComfyUI's own requirements have aiohttp, Pillow, numpy, av>=17).
- [x] **No installing at runtime in the shipped code:** `sdk.py` says whether comfy-sdk is
      here and the command, never runs it (`POST /seriesmith/sdk/install` and the auto
      install on a key are gone; Settings shows the command to copy). The installer
      downloads model files and ffmpeg and links seriesmith's own pack; a node pack or a
      pip package is `manual`: `features.status` gives each missing one its `how`
      (ComfyUI-Manager, or the pip command for its Python), `resolve` hands it back in
      `skipped`, never queued. The What's missing window's node Install button became the
      Manager pointer. The launchers still make the standalone's own `.venv` (a shell
      script the user runs, not the pack at runtime).
- [x] **Publishing set up:** publisher `bgstratt`, the key as the repo secret
      `REGISTRY_ACCESS_TOKEN`; `.github/workflows/publish_action.yml` runs
      Comfy-Org/publish-node-action only on main (a push changing pyproject.toml, which
      publishes only when its version changed; or Run workflow, main only). Feature
      branches and PRs never publish; a merge without a version bump publishes nothing.
      VideoHelperSuite is out of Features (requirements.txt brings the imageio-ffmpeg it
      was there for).
- [x] **First publish** (2026-10-21): 0.1.0 by Run workflow on main. A new version is
      Pending until the Registry's scan passes, and until then Manager can't resolve
      `seriesmith@latest` (the node has no `latest_version`); picking 0.1.0 by number
      installs it. QUICKSTART is now Getting started: three ways (ComfyUI-Manager, the page
      of its own, a linked clone) in place of the thirty-second install; INSTALL, README,
      SETUP and the docs site lead with Manager.
- [x] **0.1.3** (2026-10-25, `release-0.1.3`): H3 dialogue keeps its delivery note out of
      the spoken line; close-ups blur the plate away and leave the location's words out;
      `seriesmith check` warns on light sources in a look; AUTHORING on blurred close-up
      plates and an ECU's tightness; the docs site's Tutorials; Simple mode's Who and Where
      from + Create; relights and looks name no places or things. Published by the merge's
      version bump (publish_action.yml); Pending until the Registry's scan passes.
- [x] **0.1.4** (2026-10-26, `release-0.1.4`): `continuous: multishot`, a run of shots as one
      generation (docs/MULTISHOT.md): timed `[Shot N]` sections on H3 (Ref2VA, FastH3 Omni,
      FL2VA), prose on Seedance 2.5/2.0, one brief prompt on Kling v3 Omni, the storyboard on
      Kling Video O1; the editor's timeline and Shots tab show a group; upscale and master
      walk the built order. Hosted models refuse a picture of a shape they won't take
      (0.4 to 2.5) before sending, never cropping it; WebP sizes read; Kling v3 Omni takes 7
      pictures; an input ComfyUI holds isn't uploaded again. Kling 4 isn't on Router yet
      (its catalog, 2026-10-26). Published by the merge's version bump.
- [x] **0.1.5** (2026-10-26, `release-0.1.5`): `target: ltx2_msr`, LTX-2.5 with Licon's MSR
      LoRA: up to four people's pictures and the plate on one shot (a group refused), two
      stages; the Features window's "LTX-2.5 + MSR" with its two node packs; a LoRA of the
      user's on it. AUTHORING says what LTX references hold: one person on `ltx2`'s
      ingredients sheet, a group on MSR, speech by seed. Published by the merge's version bump.
- [x] **0.1.6** (2026-10-27, `release-0.1.6`): the gallery (#55): every picture of an episode's
      refs and every take of its shots, large, in one window; arrow through them; what each
      was made with (a take's own prompt and the pictures it was sent); Regenerate; a selection
      saved as one zip; a shared ref's pictures from the other episodes. New routes
      `GET /seriesmith/take`, `GET /seriesmith/refs/shared-takes`, `POST` / `GET
      /seriesmith/download`. A bonus tutorial (https://youtu.be/KnWEI-0d6PA). Published by
      the merge's version bump.
- [x] **0.1.7** (2026-10-27, `release-0.1.7`): an LLM drives seriesmith and takes come from
      outside (#59). `seriesmith mcp`: the editor's API as an MCP server on stdio for an LLM
      client to start (44 tools: write, check and build episodes, refs, render, the cut,
      overrides and promote, upscale, post, master; `--read-only`), with Settings › This
      computer › Use from an LLM showing this install's command to copy. A video file, or
      another shot's take, as a shot's take: Import video…, a file or a gallery take dropped
      onto a timeline clip, or between two (a new shot in the script there). New routes
      `POST /seriesmith/check`, `GET /seriesmith/mcp`, `POST /seriesmith/take/import`,
      `POST /seriesmith/take/copy`; `GET /seriesmith/refs?fresh=1`. Published by the merge's
      version bump.
- [x] **0.1.8** (2026-10-28, `release-0.1.8`): a shot's sound and dub tracks (#67): each shot
      set to the series' default, generate, clone, or dub (a recording, a dub track, or a
      take's sound), in one Sound card (the shot form, Sound…, Replace audio…); dub tracks (the
      shot rendered tiny on H3 Ref2VA for its voice alone, kept in `dub/<shot>/`) listed in the
      Refs tab with the shot's lines, Voices' Generate missing; FL2VA clone; drafts that survive
      renders and reloads, a check before Export, multi-select queueing, a picture dropped on a
      shot as its first keyframe. Voices across models (#62: LTX dub and clone, Seedance
      audio), whole-picture keyframes (#63), FLUX 3 video on Router (#64), Adding models in the
      docs (#66), the gallery showing a ref's live file with no candidate behind it at its own
      shape (#68). New routes `GET /seriesmith/dubs`, `PUT /seriesmith/sound`. Published by the
      merge's version bump.
- [x] **0.1.9** (2026-10-29, `release-0.1.9`): finishing in the cut (#72): a picture held as
      a shot on seriesmith's own model (`target: hold`, ffmpeg, dub audio under it; dropped on
      the timeline, its edges set its length; Hold this frame after it…); a clip's colour
      (exposure, contrast, black point, saturation, warmth, tint, applied on export, previewed
      live); Match the sequence to this by skin, frame or luma; a badge on a clip out of line
      with its sequence; fades in and out and dissolves, drawn as curves. H3 Singularity as a
      local model, FastH3's and Singularity's own FL2VA, and `series.first_target` naming the
      first-frame model (Ref2VA can open on a frame itself). Fades and dissolves dragged on the
      timeline, the clip menu in groups, the gallery's search box and layout (#73). A dub
      track then the render in one request (#70); voice samples as long as the character's
      lines (#71). New routes `POST /seriesmith/color/match`, `POST /seriesmith/color/measure`.
      Published by the merge's version bump.
- [x] **0.1.10** (2026-10-30, `release-0.1.10`): the cut as an FCP7 XML timeline (#76):
      `assemble --xml`, each clip its take's own file with its handles, sound and the
      recording on their tracks, fades and dissolves as cross dissolves; tried in Resolve and
      FilmCraft. The timeline's buttons as one Export ▾ menu (Export, Titles, the XML, each
      2x; Master). The lost-tour test naming its own queue (#75). The `xml` flag on
      `POST /seriesmith/assemble` and the MCP's assemble. Published by the merge's version bump.
- [x] **0.1.11** (2026-10-31, `release-0.1.11`): how a shot continues shown in the inspector,
      the shot form and its badges (#78); the three continuous modes in one place, and latent
      continuing a take from any model (#79). The skill trimmed to the format (#80): finishing
      to FINISHING.md, setup to FULL_SETUP.md, a required/optional table; story structures
      bundled as `references/story_structures.md`. Defaults: an absent `audio.mode` generates
      (a named `audio.track` still dubs), a new series' proxy is 896×512 (1344×768's shape).
      Published by the merge's version bump.
- [x] **0.1.12** (2026-10-31, `release-0.1.12`): a faster episode open (#82): the refs fetched
      on first use instead of with every open, one targets load per `GET /seriesmith/targets`,
      the takes' prompt ids only while queued and save notes only when failed (Porchlights
      ep01 cold: ~5.3 s -> ~3.5 s). `render --dry-run` writes into the episode folder.
      Published by the merge's version bump.
- [x] **0.1.13** (2026-11-02, `release-0.1.13`): the episode's sound (#86): four tracks
      (Dialogue, Effects, Ambience, Music) in `mix.json` per pass, with faders, fades, volume
      points, ducking under speech and duck regions, loudness to -16 LUFS with a true-peak
      limiter, float stems and the XML's tracks; music cues on Stable Audio 3 / ACE-Step 1.5
      and songs on YuE2 (non-commercial), written to land hits, with the spotting sheet, the
      cue window (Score, Arc, Orchestration & takes), themes and repaint; a place's ambience
      bed; effects from the take (H3, LTX-2.3, HunyuanVideo-Foley) trimmed and faded; voices
      only; beats as trim snaps; tracks of your own; the export's checks; music videos (the
      song as the recording, an optional vocal stem; MUSIC_VIDEO.md, SCORING.md); one voice
      model list; align on the GPU (cuBLAS) and Whisper turbo. An edit as a new show or a
      show's next episode (#87): FCP7 XML from Premiere, Resolve, Final Cut 7 or our own,
      footage as handles, reference or proxies (`import-xml`, Import…, the wizard's From an
      edit; IMPORT_XML.md); the Edits and Turn models (`refs.edit_target`, `refs.turn_target`,
      ↻ Turn with); preview zoom; RTX VSR a window at a time; `continuous: first` chains on
      the CLI; frames read with `-fps_mode passthrough`. Features covers everything (#88,
      #89): a line for every pack, model, package and the API key (`key`, `hub` kinds), no
      download behind a job's back (Whisper, htdemucs, Hybrid Demucs, BigVGAN, SigLIP2/CLAP),
      demucs in ComfyUI's Python, quoted pip commands, align's packages naming their Python.
      Story structures not in the reference outlined the same way (#84); the skill with no
      links into the repo (#85). Published by the merge's version bump.
- [x] **0.1.14** (2026-11-04, `release-0.1.14`): themes across a show and a first-pass score
      (#92): a picked take made a series theme (★ Series theme, `sound.themes`, whose it is),
      any cue rendered from it on Stable Audio 3 (audio-to-audio at 0.86, fitted to the cue's
      tempo and bars) with a melody score where SheetSage2 is installed; the score drafted from
      the script's `// structure:` and `// beat:` lines and each structure's Music table
      (`seriesmith score-draft`, the spotting sheet's Draft…, MCP `score_draft`): beats in a row
      one cue, stings, a sitcom's bumpers, `// theme:` marks, a show's own `sound.format` with
      `gaps`, drafting again around rendered cues, a character's theme as the episode's, a
      structure laid over a script with no beat lines; the cue window's cue picker and fit on
      open, hits dragged on the spotting map, the shot form's beat, theme mark and hit, a cue
      that can't be planned saying why; SOUND_GUIDE.md. Render quality (#91): leaner H3
      prompts (a character with a sheet named by its picture), `check` on eyelines and
      letterboxed plates, the plate as the camera in AUTHORING. Published by the merge's
      version bump.
- [x] **0.1.15** (2026-11-04, `release-0.1.15`): more music models, Pika H3 Flex, a way to
      ComfyUI (#94): MiniMax Music 3 for songs (local, and on Comfy Cloud through a partner node
      on your own ComfyUI: the Comfy API key sent with the job, the take counted as paid);
      Magenta RealTime 2 for score on seriesmith's own node (the PyTorch port carried in the
      node pack, the arc a style a bar, a theme blended into its style); Pika Music on Comfy
      Router (a draft until Router serves it) and hosted music models generally; Pika H3 Flex
      (Ref2VA and FL2VA, six steps); without a ComfyUI, the Features window's guide to ComfyUI's
      own installs and Find my ComfyUI; startup checks naming what a ComfyUI update renamed or
      dropped. Published by the merge's version bump.
- [x] **0.1.16** (2026-11-05, `release-0.1.16`): Export's dialogue (#96): Export, 2x Export and
      Master follow Play all's audio switch, on recording the recording as the dialogue under the
      mix; a take dubbed to the recording with its effects kept no longer exports with no line (the
      model's whole mix in its video, an older take's `_h3.wav`). Published by the merge's version bump.
- [x] **0.1.17** (2026-11-06, `release-0.1.17`): re-render part of a take (#98): a stretch of a take made
      again as a new take on the H3 family or LTX-2, the rest held and its sound kept, from any model's take; H3 Ref2VA, Singularity,
      Pika H3 Flex and FastH3 Omni take eight subjects round the plate on `<Picture 4>` (existing FastH3 takes read as stale).
      Published by the merge's version bump.
- [x] **0.1.18** (2026-11-07, `release-0.1.18`): H3 upscales on ComfyUI's own latent upscaler and context windows
      from 0.44, the packs the fallback; upscales get their keyframes back; new default edit and keyframe models
      (#100). Any model's take re-sampled through an H3 model; Play all plays a replaced sound; on dub the cut and
      export play the dub (#101). Published by the merge's version bump.
- [x] **0.1.19** (2026-11-09, `release-0.1.19`): models and voices on providers of your own (#103); the
      storyboard (#104, #106); one guided wizard, the guide and sketches, drops on the board and the add
      buttons, Rename on an unused entry (#107); instructions for your own agent in the guide (#108).
      Published by the merge's version bump.
- [x] **0.1.20** (2026-11-09, `release-0.1.20`): the guide's Make the pictures makes the pictures no
      shot uses yet, as a new episode has no shots (#110); the shot form's model picker at the top, in
      What renders (#111). Published by the merge's version bump.
- [x] **0.1.21** (2026-11-09, `release-0.1.21`): the script-writing skill's zip under claude.ai's 200
      files, with no zip inside it (#113). Published by the merge's version bump.
- [x] **Live:** a clean ComfyUI (no clone, no link), installed from Manager: the nodes, the
      editor in the sidebar, a local render, a Router render. Done by the user.
- Ask Comfy: whether our page may ask Manager's own API to install a missing pack (the user
  clicking, Manager installing); whether routes on PromptServer and a served editor page
  are fine (the docs don't say); the icon's size (400x400 in the spec, 800x400 in
  `comfy node init`'s template).

## Multi-shot generations: `continuous: multishot` (designing; 2026-10-26)

A run of shots rendered as one generation on the models that take more than one shot (H3
by timed `[Shot N]` sections, Kling v3 Omni and Seedance in prose, Kling O1 by storyboard fields), the episode
keeping its shots. The design, what each model did on the same three-shot beat, the open
questions and the checklist are docs/MULTISHOT.md. Merged in 0.1.4. LTX stays off the list:
with MSR's references it cut on its own but drew people into shots they weren't in.
`ltx2_msr` (merged 2026-10-26, #52) is LTX-2.5 with Licon's MSR LoRA as a
reference model for single shots: up to four people's 16:9 sheets made at queue time and the
plate, one PromptRelay prompt, two stages, the refine from 0.6. Measured on ms04 (2026-10-26,
local, two to three seeds a shot): one person holds at any length; three people hold in a
4.7 s shot and lose one or two in a 1.7 s one; speech is seed luck (Whisper-checked: one seed
garbled at both sizes, the others clean); a 960×544 first stage was no better than 832×480.
Against it, plain `ltx2` with the 2.5 ingredients sheet holds one person but, with three on the
sheet, renders the sheet itself (figures on white, panel for panel); a rewritten prompt and a
negative prompt didn't stop it. Left as is and written up in AUTHORING (one person on the
sheet; a group on `ltx2_msr`). Untried: a weaker guide, a faces-only sheet for a group.

## The gallery: every picture and take, large ✅ (2026-10-27)

The sidebar shows one ref's candidates or one shot's takes at a time, small. The gallery
is one big window over all of them: a grid of every version (picks badged, not just the
picks), opened scoped from where you double-click and widened from inside, and a viewer
that steps through the grid with the arrow keys instead of going back to it for the next
one. Design: DESIGN.md §7, "The gallery".

- [x] **Refs.** A window of its own (`gallery` in the store, `Gallery.tsx`), chips for the
      Refs tab's groups (Characters · Props & vehicles · Locations · Shot keyframes; voices
      have no pictures). Double-click a ref (row or tile) opens it on that ref, its live
      picture open; a group's head, on that group; a Gallery button, on everything. A
      section per ref, every candidate of every view (a character's four, its sheets; a
      location's plate, 360s and tour holds), newest first, live badged; or Flow, one run of
      justified rows with each ref's pictures together (its name on the first). Tiles at the
      picture's own shape (S/M/L), the view and take on hover; the episode picker in its
      head. A picture opens over the grid (closing it comes back to the grid where it was):
      ←/→ through the grid in order across refs, Esc back, F full screen; beside it, its
      prompt with Copy, model, size, seed, steps, what it was drawn from (each a link to
      that ref in the gallery), Pick, Compare with live (side by side in the gallery
      itself, C; the docked viewer sits under a floating window on the standalone page),
      Download (the file route, saved by the browser). A ref's takes come with the refs
      listing already: nothing more is fetched.
- [x] **Shots.** Refs | Shots in its head; in Shots a list (an episode has dozens of
      sequences): every sequence, in the cut, or one; and "cut only", as Refs' "live only"
      (In the cut is every sequence with it on; a sequence picked keeps it).
      A section per shot under its sequence, every finished take newest first, the cut's
      badged, a fresh upscale 2x (the 2x switch plays it); the action line on hover. Double-click a sequence's head opens it there; the Shots tab's gallery
      button, on every take. Tiles are each take's thumbnail (hover scrubs its strip); the
      viewer plays the take (space, `,` `.` a frame, the transport), Use, Compare with cut
      (in step, C), Download, Copy prompt. What a take was made with is read when it is
      opened, `GET /seriesmith/take` (its sidecar and its frozen shotlist, ~3 ms), never for
      the grid: the shot's current prompt is not what an older take was rendered with. The
      pictures it was sent, each a link to that ref's pictures, "changed since" where the
      ref's sha1 isn't the one the take recorded.
- [x] **Regenerate.** A ref's candidate queued again with its own settings (prompt as drawn,
      target, model, LoRAs, steps, cfg, knobs, size) and a new seed; an edited one, the same
      edit of the same picture; nothing for what wasn't drawn. A take: the shot as it is now
      and a new seed, that take its parent (the Inspector's Generate (new seed)); a take's
      old prompt isn't remade, since the pictures it was sent may have changed since.
- [x] **Shared refs across the show.** A ref other episodes share (`shared_with`) shows their
      candidates after this episode's, badged with the episode, read-only (no Pick or
      Regenerate here; Download, Copy prompt, Compare with live), live where that episode's
      pick wrote the file this one reads. Asked for one ref at a time as its section comes
      near (`GET /seriesmith/refs/shared-takes`, two at once, ~50-200 ms each on Porchlights'
      40 episodes). "Unused too" (was "whole series": it adds the series config's refs this
      episode's shots don't use) brings another episode's cast in with their pictures. The
      count reads "289…" while some are still to ask for.
- [x] **Selecting and saving.** On hover each tile has a tick (top left) and Download
      (bottom right). With some ticked, a click ticks, shift-click ticks a range, and the head
      has N selected · Download · Select all · Clear (Esc clears). Kept across scopes, cleared
      with the episode. Download saves one as itself (the picture whole, a take's video or,
      under 2x, its upscale) and more as one zip (`POST /seriesmith/download`: stored, not
      compressed, kept an hour; `<episode>-gallery-<n>.zip`).

## An MCP server: the editor's API for an LLM (designing; 2026-10-27)

Writing the story stays outside seriesmith: the user's own LLM (Claude Code or Cowork,
Claude Desktop, Cursor, a local model in an MCP client) works out the story with them,
and the script-writing skill turns it into `series.json` and `epNN.md`. What it can't do
today is hand them over: the user imports them (Import series…) or pastes them into the
wizard. An MCP server lets the LLM do that step, and then drive the rest as the editor
does: refs made or imported and picked, shots rendered, takes picked, the episode
assembled. No LLM and no key in seriesmith: the client brings the model.

- [x] **`POST /seriesmith/check`** `{series, script?, parent?}` (2026-10-27): a pair that
      isn't on disk, checked together (`source.check_pair`, which `check_text` now calls
      with the other file read from disk). An LLM drafting a new show checks it before
      anything is written, instead of creating an episode to read its `check`.
- [x] **`seriesmith mcp [--url …] [--read-only]`** (`seriesmith/mcp.py`, 2026-10-27): stdio,
      a thin client over HTTP to a running `seriesmith serve` or ComfyUI-hosted seriesmith,
      so every write goes through the routes (their checks, `seriesmith.episode` events for
      an open editor, one queue). **Stdlib only**, not the `mcp` SDK: MCP's stdio transport
      is JSON-RPC a line at a time, and the SDK (2.x by then) would have brought pydantic,
      httpx and more for it. Protocol versions 2024-11-05 to 2025-11-25.
- [x] **Tools**, each a route (`TOOLS`; a test holds every one to a route the server has):
      list episodes; read, check and save the two files (`source`, `source/check`, `check`,
      `PUT source` with its `base_hash`); preview a shot; new episode; import; build; the
      targets ready here; episode status (trimmed to shots, takes and what's stale); one
      shot; issues as markdown; refs (list, generate missing, generate one, import, pick);
      a picture as an image the model sees (`/thumb`); render; jobs (list, wait by polling,
      cancel); pick and discard a take; assemble. The cut (`edit_cut`: reads cut.json, changes
      only the shots named, reorders when given every shot, writes the whole list back, since
      `PUT /seriesmith/cut` replaces it; `reset_cut`); overrides (set, clear) and promote (plan,
      apply); finishing (upscale and post with their options, Keep, delete; master: plan,
      queue / assemble / prores, its job). The tools that queue say QUEUES in their
      descriptions and the server's instructions ask the model to confirm with the user first;
      `--read-only` leaves out everything that writes or queues. Tested end to end against
      seriesmith serve's app (`tests/test_mcp.py`, LiveTest), and live, read-only.
- [x] **Resources:** the script format (`prompts/SKILL.md`, read from the repo), so a
      client without the skill still writes scripts that check.
- [x] Docs: COMMANDS ("An LLM driving seriesmith"), with Claude Code's, Desktop's and Cursor's
      config for both kinds of install. `python <repo>/seriesmith/mcp.py` runs with any Python
      3.10+ (a ComfyUI-Manager install has no .venv; the file puts the repo, not its own folder,
      on the path: its queue.py would shadow the stdlib's).
- [x] **Settings › This computer › Use from an LLM (MCP)** (2026-10-27): a dropdown like Folders,
      asked of `GET /seriesmith/mcp` when it's opened (the server knows where seriesmith is and
      which Python runs it; the page's port is the server it talks to): a client's command line
      (`claude mcp add seriesmith -- …`; Codex and Copilot CLI alike), the `mcpServers` JSON,
      the bare command, each to copy, a read-only switch. Not in Features: nothing to install,
      and seriesmith never starts it (the client does).
- [x] `import_take` and `copy_take` tools (with the routes below).
- [ ] Not yet: MCP prompts (a client's slash commands) if a flow proves worth one; refs'
      overrides and keyframes, align, publish, targets from workflows as tools.

## Takes from outside: import and drag (2026-10-27)

A shot's take that seriesmith didn't render, as refs already have: a video file, or another
shot's take dragged from the gallery onto the timeline. docs/API.md, "Takes from outside".

- [x] **Backend** (`seriesmith/takeimport.py`): `POST /seriesmith/take/import` (a path, or an
      upload up to 4 GB: the route's own `max_upload`, read in `views.read_form`) and
      `POST /seriesmith/take/copy`. `source: "imported"`, no seed / prompt / hashes, so never
      stale; its own frames, fps, size and sound. An H.264 mp4 copied; anything else converted
      to H.264 (decided 2026-10-27: every take plays in the editor; the original not kept).
      `copied_from` on a copy. Tests: `tests/test_takeimport.py`.
- [x] **Import video…** on a shot (Shots tab, its context menu), and a video file dropped on a
      shot's row or onto a timeline clip: that shot's take, picked. Progress as the refs'
      uploads.
- [x] **The gallery's take tiles draggable**, and the timeline a drop target (`lib/takeDrop.ts`,
      `takeActions.ts`; `web/test/takeDrop.test.ts`):
      - onto a clip of the same shot: a pick; of another shot: copied in and picked;
      - between two clips: a new shot in the script after the left one (decided
        2026-10-27), numbered as "Add a shot after" (`shotIdBetween`), its lines copied from
        the take's shot, `dur:` the take's length; saved through the source route (history,
        rebuild); the take copied in, picked, the clip moved to the gap.
- [x] **A video file dropped between two clips**: the shot form opens there, prefilled
      (sequence, position, `dur:` from the file), the file attached; Save makes the shot and
      imports the file as its take (decided 2026-10-27: the action needs writing).
- [x] Where a take came from, shown: "imported (name)" / "from sh020 t03" in the take row
      and the gallery's viewer (the episode status's `source`, `original_name`, `copied_from`).
- [x] Checked live (2026-10-27, by hand): gallery takes and files dropped onto clips and between
      them, in seriesmith serve and in ComfyUI (after a refresh); a .mov converted. The file
      between two clips: the form wants the action written, and **Save and generate** also
      queues a render beside the imported take (documented in EDITOR.md, left as it is).

## Voices across models: a held sound, and audio references (2026-10-28)

From Frameforge (Chain Motion AI Video Editor)'s Speech Studio: a sound can be **held** in an
LTX graph (encoded, a noise mask of 0, swapped into the AV latent the sampler samples), and
LTX makes only what's around it. `targets/held_audio.py` does it for every LTX sampler;
`audiocut.py` cuts what is held (a sample's head between words, a shot's window).

- [x] **Voice clone by continuation** (`ltx2_voice`): a voice ref with a sample is continued
      from its head (1.5-2.5 s) and the head trimmed off. Measured live 2026-10-28 on a real
      1.4 s / 2.45 s recording (scratch graphs, then seriesmith's own): Whisper heard the line
      word for word every time; median pitch 110-129 Hz against the speaker's 101-107 Hz,
      153 Hz described only. Close, not exact. LTXVReferenceAudio (ID-LoRA) dropped.
- [x] **LTX dub** (`ltx2`, `ltx2_ingredients`, `ltx2_msr`): a dub shot's window held as its
      whole soundtrack through every stage. Measured live 2026-10-28: the held sound came back
      at envelope correlation 0.97-0.99 (Whisper the same words), mouth motion +0.31/+0.36
      against its own sound and 0.00-0.17 against another take's (LTX's own sound: +0.41).
      Rendered through `seriesmith render` (the mixed fixture's sh040 on ltx2): 0.97, the
      window's words. Not yet checked: a shot with a first keyframe, the two variants live,
      two speakers in a shot.
- [x] **Seedance audio references** (2.0, fast, mini, 2.5): clone sends each speaker's
      sample, dub the window (padded to 2 s), named in the prompt (`@Audio N`) after the
      pictures. Tried live 2026-10-28 on Seedance 2.0 fast (two calls, a scratch episode):
      the Seedance library refuses audio ("get image info ... not supported"), so audio goes
      inline (`via: datauri`); frames can't be mixed with reference media (`invalid_input`;
      BytePlus: "first/last frame content cannot be mixed with reference media content"),
      so a shot sending audio goes by its references (`voices.with_frames: false`). Then:
      **clone** spoke the new line word for word at 108 Hz against the sample's 101 Hz;
      **dub** came back with the window's words in its voice (106 Hz, as the window) but
      re-performed slower over the 4 s clip (envelope 0.50 against the window), so its lips
      follow its own sound, not the recording: a voice-matched re-read, not a true dub.
- [x] **LTX clone** (`ltx2`, `ltx2_msr`): each line made in the shot's own graph by the
      audio-only model (the shot's transformer), continuing its speaker's held sample, the
      lines joined with core.speech's beats (AudioConcat, EmptyAudio) and held as for a dub
      (`held_audio.patch_clone`). Decided 2026-10-28: made with the picture, in one job, as
      there's no time to review voice takes separately; a recording goes align -> dub
      instead. Rendered live through `seriesmith render` (sh050, the narrator off screen):
      Whisper heard the line on both, median pitch 110 Hz (ltx2) and 115 Hz (ltx2_msr)
      against the sample's 101 Hz. Not yet live: two speakers in one shot (unit-tested).
      `ltx2_ingredients` (LTX-2.3) still renders clone as generate: untried there.
- [x] A voice sample's length follows its lines (2026-10-28): a short line in an 8 s sample
      was padded with invented words (seen live, with and without a held sample). Now the
      character's lines, longest first, fill the length (`common.voice_line`), and with less
      to say the sample is as long as they take, 2 s at least (`refs.voice_seconds`). Live on
      a scratch copy of Ballroom ep03 (ltx2_voice, no held sample, seeds 11 and 22, Whisper
      small.en): the old way's leftover time came back as silence before the line (Mia's 4
      words began at 5.4 s and 2.4 s of 8) or the line dragged out (Charming's 5 words over
      6.2 s); the new samples (Stepmother 6 s, four lines; Charming 3.7 s, two; Mia 2 s)
      spoke from 0 s, every word as asked, one "preparation" for "preparations". No invented
      words came back either way in these six. With a held sample (each character's new
      sample picked, two seeds): the old way read the prompt aloud once ("Charming says, ...
      a tall young man", the invented words) and came back silent once; Mia's 2 s sample (1.1
      s of speech) came back silent every time, the head held whole, its silence and all; and
      Charming's continuation skipped "Cindy... the selection is over.", which his sample's
      head said. So: the held head loses the silence after its last word
      (`audiocut.speech_end`), and a sample from the script opens with a sentence no shot
      says (`common.OPENER`, "Hello, this is Mia speaking.", ~1.8 s, where the head is cut;
      `OPENER_HELD`, "And this is how I sound.", for a generate continuing a held sample, so
      its take, picked, still does). Again live: all six held takes said every script line,
      nothing invented, Mia at 193-206 Hz against her sample's 200; the heads were the
      opener alone. Ref2VA, which takes the whole sample: sh040 dub tracks from Stepmother's
      6 s sample and the same cut to 2 s both said every word (Mia's part at her sample's
      226 Hz): a short sample is no problem there.

## Voices before the picture (2026-10-28)

- [x] **H3 FL2VA clones**: the lines made first in the same graph by LTX-2.5's audio-only
      model (`held_audio.make_lines`, LTX's own loaders: FL2VA's optional `voice_*` models,
      resolved for clone shots only: a models spec's `policies`), anchored as a recording;
      the take keeps them as `_lines.wav` (`SeriesmithSaveTake`'s `lines`). Not yet live.
- [x] **Dub tracks** (render `dub_track`): the shot on H3 Ref2VA at 64x64 (or FastH3 Omni,
      or LTX) for its sound, kept in `<episode>/dub/<shot>/`. Measured live 2026-10-28 (Dean
      ep01 sh025, one seed, as "voice takes"): 1344x768, 448x256, 256x160, 64x64 and 32x32 all
      said the line word for word (Whisper), pitch 262-296 Hz against the sample's 267, a
      rough timbre match 0.93-0.94 (LTX's clone: 242 Hz, 0.905, and it dropped a word); the
      read differs with the size (the noise does), the level too (-13.5 to -20.3 dBFS RMS,
      448x256 and 256x160 peaking over full scale), so a dub levels it first; ~13-15 s a
      take once H3 is loaded; a size and seed give the same sound again.
- [x] **A shot's sound** (overrides.json `sound`): generate, clone, or dub a track (the
      recorded track's window, any take's sound in either pass, a dub track); a dub of a
      file is the shot's own recording, levelled, on every H3 and LTX model, the take's mp4
      remuxed with the model's mix; takes made otherwise go stale `sound`. The editor's
      Sound dialog, chip, menus and the shot form's Sound…. Replaced the day's voice takes
      and lines_from. Not yet live.
- [x] A dub track, then the render, in one request (2026-10-28): `POST /seriesmith/render`'s
      `then_render` with `dub_track`. A journaled queue step per shot (`api._dub_step`, waiting
      on the track's take, not a job id, so it survives a restart) sets the shot to dub with
      it and asks for the render; the editor's **…then render**, **Dub track, then render**,
      and the selection's **then render**.
- [ ] `seriesmith render --dub-track` / a sound on the command line; ElevenLabs and the
      like as voice models (an audio target writing a dub track).

## FLUX 3 video (2026-10-28)

- [x] **`flux_3_video`** on Comfy Router (`bfl/flux-3-video`), generated from its schema
      (`tools/make_router_targets.py`): `router_inspect.propose` now knows a `keyframes` field
      (pictures that become frames: the shot's first, then last) and a `mode` naming t2v / i2v,
      which `router_video` sets by whether frames went. The rest from its prose (`flux3_video`):
      its seven ratios (omitted with frames: BFL's `auto`), hd / fhd / qhd / uhd by height,
      5-20 s. Sound on; no seed, no negative. Not yet rendered live.
- [ ] **Reference pictures.** BFL's FLUX 3 takes them (Runware's `referenceImages`; the
      request shape `reference_images` named `<ref_image_N>` in the prompt), but Router
      refuses the field for bfl/flux-3-video: "property reference_images is unsupported"
      (HTTP 422, extra_forbidden; probed 2026-10-28, nothing billed). When Router's schema
      lists it: the shot's panels as `reference_images`, named with `<ref_image_{n}>` from 0.
- [ ] Timed keyframes (`[[seconds, image], ...]`): seriesmith has first and last only.
- [ ] Its draft mode (a fast preview, then `draft_enhance` from the returned `draft_cache`)
      as the proxy pass: not Seedance's draft (a task id), so not wired yet.

## The cut, finished in place: holds, colour, continuity, two transitions (planned; 2026-10-29)

Ideas from reading two other projects (gobo, OpenKatana; decided 2026-10-29): written our
own way, in seriesmith's own code, nothing copied or depended on. Not a grading suite or an editor:
real colour work and real editing go to Premiere / Resolve with the cut's clips. What's
here is what a cut needs before that, and what a cut that never leaves seriesmith needs.

- [x] **A held picture is a shot on a model of seriesmith's own** (decided 2026-10-29, after
      two tries that bolted it on beside the shot: an imported take, then routes to make
      and re-length one): `target: hold` (targets/video/hold/target.json, the generic
      `video_prose` compile). Its first keyframe (required) held still for its `dur:`, at
      the pass's size and the cut's rate, letterboxed (seriesmith/hold.py). Generate plans
      it as any shot (`plan_job`: blocked without its picture; `sidecar_for`'s hashes, so
      it goes stale when `dur:` or the picture changes) and then, instead of a backend, runs
      it on the local lane (`runner.enqueue_hold`, from `edit.queue_shots` and
      `seriesmith render`); always ready, never paid (`backends: ["local"]`). Sound: silent,
      or a dub's track laid under it (`hold.dub_audio`). Upscale: pixel or SeedVR2 (no
      latent). The editor: a picture dropped between two clips writes a hold shot
      (`takeDrop.heldShot`), uploads the picture as its first keyframe and generates it; a
      held clip's edge sets its `dur:` (`withDur`) and generates it again; a take's **Hold
      this frame after it…** writes one after it (`insertedShot`'s `held`) with that frame
      as its first keyframe. Tests: `tests/test_hold.py`, `web/test/takeDrop.test.ts`,
      `web/test/shotPicks.test.ts`. Not yet live.
      - [ ] Later, maybe: a held shot's upscale as the picture held again at the bigger size
        (sharper than any upscale of the held frames), and `first:` paths imported when it's
        generated rather than by Generate missing.
- Not doing: an animatic (decided 2026-10-29). Holding pictures on the timeline was the
  point; a pass or an export of keyframes isn't wanted.
- [x] **A clip's colour** (2026-10-29): exposure (stops), contrast, black point, saturation,
      warmth, tint, six sliders at 0 in the inspector's cut section (tint and contrast added
      the same day: warmth alone is one axis of a cast, and models differ most in contrast). Kept on the cut entry (`"color"`, only
      the non-zero ones; `takes.CutEntry.color`), so nothing re-renders and the take is
      untouched. One linear map of the picture's RGB (seriesmith/color.py, mirrored in
      web/src/lib/color.ts and held to the same numbers by tests/fixtures/color_cases.json):
      assemble applies it as the clip is re-encoded (colorchannelmixer + lutrgb in
      full-range RGB; `--no-color`), so Export, Titles, 2x and Master all get it; the viewer
      and the timeline preview the same matrix as an SVG feColorMatrix while the sliders are
      dragged (`colorPreview`), saved when let go. Undo, locks, the MCP's `edit_cut`. Not
      copied between passes (each pass's cut has its own, as flags). Tests:
      tests/test_color.py, test_assemble's colour case, test_api's `test_cut_colour`,
      web/test/color.test.ts. Not yet live.
- [x] **Match to this shot** (2026-10-29): `POST /seriesmith/color/match` (`edit.match_colors`,
      `color.match`): the colour bringing the rest of a clip's sequence (or the shots named)
      in line with it, worked out, not written; the editor sets them as one cut edit. A
      closed-form fit of luma percentiles and midtone means was tried first and failed
      wherever a correction clips (bright, saturated pictures: the percentiles bunch at 0
      and 1); so helpers/colorstats.py (numpy, a subprocess) searches the six sliders
      (Nelder-Mead) through color.matrix with the clipping, comparing each channel's
      percentiles and the midtones' chroma, with a slight pull towards 0 (exposure,
      contrast and blacks overlap). Measured on a gradient picture with a known colour
      applied: warmth, tint, saturation and exposure come back within a few hundredths;
      exposure / contrast / blacks may come back as another mix giving the same look. The
      inspector's **Match the sequence to this**, the clip menu's item, the MCP's
      `match_color`. Tests: tests/test_hold.py's ColorMatchTest (held takes), web/test/color.test.ts.
      Tried live 2026-10-29 on Ballroom ms04 (base a Seedance clip, the rest LTX-2 and H3):
      fine where the content was alike (sh070), wrong on a pale close-up before a bright
      window (sh030: -1.2 stops, warmth 1, a magenta cast), because the whole frame's
      percentiles and mean see the content (the base's green and blue dresses) as much as the
      light. So three ways, a button each (`by`, color.MATCH_BY): **skin** (the pixels that
      look like lit skin, found once on each picture: median brightness, cast, saturation;
      exposure / warmth / tint / saturation, not contrast, whose spread is the shot's
      lighting and moved the exposure a stop), **frame** (the old one), **luma** (brightness
      alone; the clip's own warmth / tint / saturation kept). Tried first and dropped: the
      whole frame less clipped pixels, the cast from the near-grey ones (sh030 worse: -1
      stop, saturation +1). Skin on ms04: sh070 and sh110 close to the base, sh030 gentle but
      a little green (that actress's skin is pinker than the base's cast's). Tests:
      tests/test_color.py's MatchByTest.
- [x] **A clip out of line: a badge, not a report** (decided 2026-10-29: a small mark on the
      clip, not another export). A take's look (color.look: 128 pixels from five frames, hex
      in its sidecar) is measured as it's made (runner, hold, takeimport; `color/measure` and
      the Cut menu's **Check colour** for older takes). The episode status compares each
      clip of a sequence (three at least), through its own colour with the clipping, with the
      sequence's middle: brightness, contrast, warmth, tint, saturation (color.OFF's limits);
      `cut.look_off` says what's off, the timeline's badge (three colour circles in a ring)
      shows it. Not the continuity rules of a cut to the next shot (light may change across
      a cut): the odd one out of its sequence. Built on the way: colorchannelmixer takes
      -2..2, so filters() scales the matrix into it and lutrgb back (16-bit; +2 stops failed
      to export before); Match compares the mean colour too, and starts from it. Tests:
      tests/test_hold.py's LookTest. Not yet live.
- [x] **Fades and dissolves** (2026-10-29): on the cut entry, in frames, `fade_in` /
      `fade_out` (from / to black at the clip's own head / tail) and `dissolve` (overlapping
      the clip before; the cut that much shorter). Decided the same day: a fade in and a fade
      out are each their own (a scene fades out, the next comes in on a cut), not one "fade"
      transition across a join; only a dissolve spans one, and a join with one has no fades.
      Assemble (`lay_transitions`, `dissolve`): every clip re-encoded when any is set; a
      dissolve is three pieces (the clip before less its last n frames, n frames of xfade /
      acrossfade, this clip less its first n), a fade is fade / afade on the clip's own frames;
      what doesn't fit is left out and said; `--no-transitions`. The editor: the timeline
      draws them as thin curves over the clips, their length (`JoinCurves`; a dissolve an X
      across the join, each clip giving half, as the playlist lays it: `withDissolves`); Play
      all dims a fade (`fadeLevel`) and cuts a dissolve at its middle; the clip menu toggles
      each at 12 frames, the inspector sets the frames. Tests: test_assemble's three,
      test_api's `test_cut_fades_and_dissolves`, web/test/joins.test.ts. Not yet live.
- [x] Checks on the exported cut (integrated loudness and true peak, black and frozen runs,
      flashes), reported, never changing it. The loudness part 2026-11-02 (docs/SOUND.md
      phase 5: `<cut>_loudness.json`, assemble's report, Export's toast); the picture's the
      same day (`seriesmith/checks.py`, docs/FINISHING.md "The export's checks"): one ffmpeg
      pass, scaled to 256 wide, `blackdetect` (0.5 s, 10 % luma, 98 % of the picture),
      `freezedetect` (2 s, -60 dB) and each frame's mean luma for flashes (WCAG 2.3.1's rule
      on the whole frame: more than three pairs of opposing 10 % changes in relative
      luminance, the darker below 0.80, in any second), each run with its shot; black and
      frozen runs inside a clip's own fade or a held (`hold`) shot left out and counted.
      Kept as a sibling `<cut>_checks.json` (not inside the loudness file: that one is the
      sound's and keeps its shape), printed under the loudness line, returned from
      `POST /seriesmith/assemble` as `checks`, a **Checks:** line in Export's toast;
      `--no-checks`. Tests: tests/test_export_checks.py (each detector on a synthetic cut,
      the explained runs, the flash rule's edges, the report's shape), test_assemble's
      progress steps. Measured on CupsMV ep01's proxy (2 min, 33 shots, a
      scratch name, deleted after): 25.0 s assembled with the checks, 23.8 s without (the scan
      1.2 s; 0.8 s a minute at 1080p, 2.4 s at 4K, synthetic); it found nothing there.

## H3 Singularity, and continuous shots that keep their model (2026-10-29)

- [x] **`h3_singularity`**: AIGC-Singularity's community fine-tune of H3 Ref2VA
      (huggingface.co/WarmBloodAban/Minimax-h3_Singularity, Apache-2.0 over H3's licence):
      Ref2VA's node, prompt, compile, encoders, VAEs and turbo LoRAs with its v2 pruned INT8
      (21 GB; the v2 bf16 is 66.3 GB and the full INT8 34 GB, past the 5090's 32 GB beside the
      text encoder). Its header is stock H3's (932 tensors, the same shapes and INT8 packing,
      a `model.diffusion_model.` prefix ComfyUI strips); it ships Ref2VA weights only. The
      stock Ref2VA's model pattern now excludes `*singularity*`. Rendered live 2026-10-29
      (last-light sh020, proxy): 33 s, on model.
- [x] **Continuous shots keep their model** (decided 2026-10-29): `fasth3_fl2va` and
      `h3_singularity_fl2va`, FL2VA's graph with FastH3 Omni's / Singularity's weights (H3
      Ref2VA and FL2VA have the same tensors), the `continuous.first` partners of
      `fasth3_omni` and `h3_singularity`. Tried live (last-light sh030 from a keyframe, proxy,
      one seed): both opened on the keyframe and gave the shot the script asked for (stock
      FL2VA held the frame more smoothly but missed the close-up). FastH3's runs as FastH3
      does (no LoRA, 8 steps; res_multistep), without its workflow's shifts (12 / 3) or sparse
      attention, which FL2VA's graph doesn't set. Fixed on the way: a render re-read the
      script's target (a `#` header's) and undid the build's move of a `continuous: first`
      shot to its partner; `jobs.script_targets` now reads the build's routing (this hit
      Ref2VA -> FL2VA too). Tests: tests/test_continuous.py's PartnerTest.
- [x] **`series.first_target`** (decided 2026-10-29): the series config names the first-frame
      model as it names the video, picture and keyframe ones (Series settings › Models ›
      First frames). A `continuous: first` shot whose model reads no first frame (H3 Ref2VA,
      FastH3 Omni, Singularity) goes there over its model's own partner; a model that reads
      one (LTX-2, Wan, the hosted ones) keeps its shots either way. `targets.first_target`,
      validated (a video target reading a first keyframe). Tests: PartnerTest's.
- [x] **Singularity opens on a first frame itself** (2026-10-29): ComfyUI's `MiniMaxH3AddGuide`
      anchors a picture at frame 0 of the reference node's render (as FL2VA anchors a dub), so
      a shot that asks for one (`continuous: first`, a `first:` line) stays on Singularity with
      its pictures, which FL2VA can't read (minimax_h3_ref2va/first_frame.py; recipe
      `keyframes_when_asked`: the Refs tab lists a first keyframe only for a shot that asks).
      Live (last-light sh030 from sh020's last frame, proxy): frame 0 the keyframe, then the
      close-up the script asks for, Mara's sheet and the plate sent. FastH3 Omni tried the same
      way ignored the anchor (frame 0 not the keyframe: its 8 distilled steps), so it keeps
      `fasth3_fl2va`. `h3_singularity_fl2va` stays as a model to name or set as `first_target`.
- [x] **Stock H3 Ref2VA can open on a first frame too** (2026-10-29), by the same anchor (the
      step moved into Ref2VA's compile, for any target whose recipe says
      `keyframes_when_asked`). Live (last-light sh030 from sh020's last frame, proxy, the same
      seed): frame 0 the keyframe, then the close-up the script asks for, Mara's sheet and the
      plate sent; stock FL2VA held the frame more smoothly but stayed wide. Opt-in, so no
      existing series changes: its `continuous: first` shots still go to FL2VA unless the series
      config's `first_target` names `minimax_h3_ref2va` (or the shot names it, which used to be
      an error). The golden error case now names fasth3_omni, which still can't.
- [ ] More seeds at final size before trusting the anchor or the FL2VA partners.

## The cut as an editor's timeline: FCP7 XML, and one Export menu (2026-10-30)

Real editing goes to Premiere / Resolve (above), but until now only as one flattened mp4
(or its ProRes .mov) and a `_shots.txt`. This hands the editor the cut itself: every clip,
its take, its trims, on a timeline it opens. Branch `fcp-xml-export`.

Decided 2026-10-30: **FCP7 XML** (xmeml v4, `.xml`) only. It's the one Premiere, Resolve,
Avid (via import), Final Cut 7, Kdenlive and Shotcut all read, it carries several tracks and
each clip's file path, and it's plain text (the standard library writes it). Not EDL (one
video track and no file paths: it needs the media gathered and named by reel first, and the
XML covers every editor that reads one), not FCPXML (Final Cut X; less portable), not AAF
(binary, Avid's), not OpenTimelineIO (a dependency for formats we don't want).

- [x] **assemble's plan, written as XML, nothing encoded.** `assemble --xml` stops after
      the plan (as `--check` does, after `lay_transitions` and the timings; `write_xml`) and
      writes `<sub>/<episode>.xml` beside where the mp4 would go (`_up.xml` with
      `--upscaled`), so it picks exactly what Export picks: cut.json's order, picks, `out`,
      placeholders from the other pass, `--upscaled` / `--post` clips. Pulling the plan out
      of `main()` first wasn't needed: the branch sits where `--check`'s does, so the mp4
      path is untouched. The writer is its own stdlib module (`seriesmith/nle_xml.py`:
      clips + fps + size → xmeml text, `xml.etree`), tested without ffmpeg.
  - Each clip: a `clipitem` on V1 pointing at the take's own file (`pathurl`
    `file://localhost/C:/...`, percent-encoded), named `sh010 t03`, in = `trim_in`,
    out = `trim_in + used`. The frames a trim, a dialogue window (`keep`) or the take's own
    length leave out stay in the file as **handles** the editor can slip into, which the
    mp4 export can't give. Its linked audio on A1/A2 (stereo), from the same file.
  - Sound as Export lays it: a mute mp4's `_h3.wav`; a cut entry's `audio` source (another
    take's sound, a file) as that file's clipitem on A1 in place of the take's own, with its
    `start` / `offset` as in/out and a gap (`gain` as the clip's level). `source: none`: no
    audio clip.
  - The recorded dialogue (`master_track`, when the shotlist has one) on A3/A4, from the
    first clip's `audio_in` (assemble's `--audio master` rule), so the editor can check sync
    against it (at level: it's the reference, the editor mutes it). Stereo is two mono
    tracks (A1/A2), as FCP7 wrote it, which every importer reads; a mono file is A1 alone.
    A dissolve's and a fade's sound gets a Cross Fade (+3dB) where the clip's sound meets
    its edges.
  - Transitions: a dissolve as a centred Cross Dissolve of n frames on the join (the edit
    at its middle: the clip before's out `n/2` early, this one's in `n/2` late, the
    frames either side the handles; the same frames assemble's xfade uses). A fade in /
    out as a Cross Dissolve from / to black at the clip's head / tail (`start-black` /
    `end-black`), which Premiere and Resolve read as a fade.
  - The sequence: the episode's fps (`timebase` + `ntsc` for 23.976 / 29.97), the cut's
    size (the pass's, `--size`, or the upscales' as assemble decides), named
    `<episode> (<pass>)`. A clip at another rate (Wan's 16 fps) carries its own `rate`
    and the editor conforms it; a clip at another size is scaled to fit by the editor (say
    so in the report). Markers: one per sequence (`ms01`…) at its first clip.
  - Not carried, said in the report: a clip's colour (`color`: the editor grades), anything
    missing (skipped, as Export does; no gap left). Media stays where it is (absolute
    paths); moving the show means relinking. Gathering the media into one folder ("collect")
    is later, if wanted.
- [x] **The route and the edit:** `POST /seriesmith/assemble` takes `"xml": true` →
      `edit.assemble_episode(..., xml=True)` (output parsing takes `.xml` as well as `.mp4`).
      It never refuses a partial cut (it's a timeline; Titles' whole-cut rule doesn't
      apply; `xml` with `publish` is a 400). `seriesmith assemble --xml` from the command
      table as is; the MCP's assemble tool gets the flag.
- [x] **One Export menu on the timeline** (in place of the Export | 2x and Titles | 2x
      pairs and the Master button): an **Export ▾** button opening a menu in the overlay,
      as the Cut menu does (its positioning and dismissal now `OverlayMenu` in CutMenu.tsx,
      both menus on it; `ExportMenu.tsx`, `exportMenu` in the store), a spinner and what's
      running on the button:
  - Export (review mp4) · Export 2x
  - Titles · Titles 2x
  - Premiere / Resolve XML · Premiere / Resolve XML 2x (from the upscales; clips without
    a fresh one are upscaled first, as Export 2x does: `exportUpscaled`'s flow)
  - Master…
  
  Each item keeps today's tooltip; every one goes through `checkThenExport` (the XML items
  as a new `kind: "xml"`, whose missing shots are a note, not a stop). Master leaves the
  Cut menu (it's in the Export menu now); Upscale the cut and Post-process stay in Cut.
  The toast after an XML: its path, and "open it in Premiere (File ▸ Import) or Resolve
  (File ▸ Import ▸ Timeline)". The mock API gets the flag.
- [x] **Tests:** `tests/test_nle_xml.py` (the writer: tracks, in/out, handles, a dissolve's
      centred in/out, fades, an audio source, 23.976's `ntsc`, a 16 fps clip's own rate,
      paths with spaces percent-encoded, parses back with `xml.etree`); test_assemble: `--xml`
      on the fake takes picks what the mp4 export picks and writes no mp4; test_api's
      assemble with `xml`; web/test/exportMenu.test.ts.
- [x] **Docs:** EDITOR.md (the Export menu, the XML and what it carries), COMMANDS.md
      (`--xml`), API.md (`xml`), DESIGN.md's cut section; `npm run build:standalone` and
      `npm run build`; `tools/make_site_docs.py`.
- [x] **Live:** a real episode's XML (one with trims, a dissolve, a fade, an audio source,
      a placeholder and a 16 fps clip) opened in DaVinci Resolve and in Premiere Pro; the
      cut plays as Export's mp4 does, and a trimmed clip's handles are there. Opened in both
      by the user; and the other way, a Resolve export imported into seriesmith (2026-11-02).

## Faster episode open, and the CLI's `continuous: first` chains (2026-10-31)

A cold open of Porchlights ep01 (324 shots, 1,773 takes) took ~5.3 s from the server's
start to the shots on screen: status 0.9 s alone but 2.7 s beside targets, refs 1.5 s and
1.4 MB fetched with every open, targets 0.7 s.

- [x] Refs on first use (`useRefs`), not with the episode; one targets load per
      `GET /seriesmith/targets` (`TG.one_load`: 10,500 stats -> one listing); the takes'
      prompt ids only while queued, save notes only when failed. ~3.5 s now, 1.3 s of it the
      server starting. `render --dry-run` writes into the episode folder.
- [x] **Live** (2026-10-31): open Porchlights ep01 / ep02 after a restart; the Refs tab, a shot's
      pictures, the shot form's cast and the gallery each fill on first open.
- Left for now: the status's own 0.9 s (each take's upscale against the recipe 0.33 s, the
  takes listing 0.24 s, the retargeted shots' compile 0.23 s), cacheable per episode.

**`seriesmith render` and `continuous: first`.** The CLI renders every shot of every episode
it's given, one at a time in order, so a `continuous: latent` chain works: each holds the
take rendered just before it. A `continuous: first` chain doesn't, without `--only`:
`continuity_before_render` passes `shots=None`, and `refresh_continuity` counts only a
batch it's given as coming, so with `--redo` each shot is given a first frame cut from the
previous shot's *old* take (it reads as fresh, so nothing waits). The editor's queue passes
its batch (`api.py`, `cut_at_start=True`) and is right.

- [x] Plan the episode first, then the continuity: the shots that will actually run
      (`j.runs` after `--only`, `--redo` and the skips) are the batch, so a shot after one
      rendering in this run waits for it and its first frame is cut as its render starts
      (`cut_at_start=True`, as the editor). A shot held for want of a frame is dropped from
      the plan, as now. Without `--redo`, a shot with a finished take isn't in the batch, so
      the shot after it starts from that take. 2026-11-02 (`render.continuity_before_render`
      on the planned jobs; a chain runs in cut order; a shot after one that failed in this
      run isn't rendered; the "first frame cut from ..." line printed under each take. Also
      fixed by it: a chain with no takes yet ran only its first shot, each later one held
      for "no first frame yet")
- [x] Say it: `--list` / `--dry-run` print "sh020: opens on sh010's new take in this run".
      When the previous shot's cut entry is picked or locked on an older take, the chain
      starts from that pick (the take the cut uses, as the editor's), and the line says so.
      2026-11-02 (`refresh_continuity`'s `picked`: such a shot doesn't wait, in the editor's
      queue too)
- [x] **Tests** (test_render, fake backend): a three-shot FL2VA chain with `--redo` cuts
      sh020's first frame from sh010's new take and sh030's from sh020's; without `--redo`,
      only the shot with no take renders and opens on its finished neighbour; `--only sh030`
      starts from sh020's take in the cut. 2026-11-02 (`CommandLineChainTest`: takes as real
      mp4s of a colour each, the first frame matched pixel for pixel)
- [x] **Docs:** COMMANDS.md (`render` and continuous chains). 2026-11-02
- [x] **Live** (2026-11-02, local ComfyUI, a scratch copy of Pacing ep01_fl2va, proxy
      960x544): `--only sh010,sh020,sh030` with no takes rendered all three in 3:55 (before,
      sh020 and sh030 were held), then `--redo` in 3:51, each printing "first frame cut from
      <prev> proxy t0N as the render started". Each keyframe matched the previous shot's new
      take's last frame (mean abs difference 1.0 of 255 at 480x272, against 32-43 for that
      take's first frame), and each take's own first frame came out 3.2-3.4 from it.

## The episode's sound: dialogue, effects, ambience, music (built; 2026-11-02)

Four tracks under the picture, each optional with its own level: Dialogue (the take's own
sound, or its voices alone: voices only), Effects (foley from the picked take), Ambience (a place's bed across cuts),
Music (cues and songs as their own assets, anchored to shots and frames, written to land
named hit points on bar lines). The mix is the episode's (`mix.json` per pass), not the
script's: faders, item gain, fades, volume breakpoints, ducking under dialogue with "score
forward" regions, loudness to -16 LUFS; stems and the FCP7 export's eight tracks. The design,
the models found on this machine and the phases are docs/SOUND.md. Stable Audio 3 the default
score model, ACE-Step 1.5 XL beside it; YuE2 the song default (2026-11-01).

- [x] Phase 1: the mix with files (mix.json, lanes, ducking, loudness, stems, XML tracks)
      2026-11-01 (its docs checked 2026-11-02)
- [x] Phase 2: music (`music` kind, `ace_step15`, `yue2`, hits -> tempo, the arc -> sections
      -> words, refit); the cue window (Score, Arc, Orchestration & takes tabs) and the
      episode's spotting sheet; the `yue2` song target and the leitmotif reference (a cue's
      theme: ACE-Step's timbre, YuE2's melody) 2026-11-01; repaint (bars of an ACE-Step take
      made again, measured first: SOUND.md "Measured: repaint") 2026-11-02
- [x] Phase 3: ambience (`ambience` kind, a location's bed as a ref, three models compared)
      2026-11-01
- [x] Phase 4: effects (`foley` kind, LTX-2.3 Foley, H3 tried; Demucs split optional)
      2026-11-01; the Demucs split built as **voices only** 2026-11-02 (`voices.py`: each take
      the cut plays split into `<take>.voice.wav`, the Dialogue track playing the voices alone,
      a shot with no lines silent; live on Ballroom ep02's 11 shots, SOUND.md "Measured: voices
      only"; not yet heard by the user nor looked at in a browser); a shot's effects trimmed,
      faded and levelled within its clip 2026-11-02 (mix.json `fx` `trim_in` / `trim_out` /
      `fade_in` / `fade_out` / `points`: the block stays put, the trimmed ends silent; the XML
      clip trimmed to what's heard; not yet looked at in a browser)
- [x] Phase 5: cutting to music (beats as trim snaps), the loudness check on export
      2026-11-02 (the snapping still to be looked at in a browser)
- [x] Phase 6: tracks of your own (add, rename, delete; each its stem and XML pair)
      2026-11-02 (mix.json's `track_list`; not yet looked at in a browser)
- [x] Phase 7: song-first (a music video): the finished song is the episode's recording, as a
      recorded dub is (`audio.mode: source_track`, each shot its window); one real song tried
      (CupsMV), the vocal stem offered (optional, off by default: H3 lip-synced as well to the
      whole song) and the guide written (docs/MUSIC_VIDEO.md) 2026-11-02
- [x] Taking a cue out (2026-11-02): an item's `mute` (silent in the export, stems, loudness and
      Play all, disabled in the XML; "plays in the mix" on the Refs tab's Music row, an item's
      menu, the spotting map's cue menu) and `DELETE /seriesmith/cue` (its folder to
      `_history/cue-<id>.<stamp>/`, out of both mixes; "Delete cue…" there and in the cue
      window's head); not yet looked at in a browser
- [ ] Phase 8: themes across a season and a first-pass score (SOUND.md phase 8; designed
      2026-11-03 after measuring, SOUND.md "Measured: leitmotifs": SA3 audio-to-audio plays a
      recording's tune in a cue's instruments, ACE-Step's reference and every paid service
      tried on paper don't; a theme is a picked take, notes optional). In order:
  - [x] a theme's take under a cue of another length and tempo (looped or cut at bar
        lines, stretched): measure how far it holds (2026-11-03, SOUND.md: length free at
        bar lines, tempo not; 0.86 from a take, not 0.89; a theme must be clear to travel)
  - [x] by ear: the fit page's 0.86 cues (the user: 0.86 is fine, 2026-11-03)
  - [x] `sound.themes` in the series config (a pinned take of any episode's cue, or a file
        with its bpm); a cue's `theme: {"theme": "<name>"}` and `strength`; Stable Audio 3
        renders from a theme (target capability `theme: "audio"`, prompt.py cue_graph: the
        theme's sound encoded, SamplerCustom on 8 even steps from t0, 0.86 by default), the
        theme fitted to the cue first (cue.stage_theme: the cue's tempo, whole bars looped); a
        cue with a theme and no bpm takes its tempo; the melody score (core/abc.melody_match
        of SheetSage2's transcriptions of the take and the theme, in the take's job, when
        SheetSage2 is installed: optional, non-commercial) with takes under 30 % ranked last
        (a filter on a floor, not a band: from a take there is no synth to show through);
        a take pinned as a series theme from the editor (POST /seriesmith/cue/theme, written
        into every episode's series config); the cue window's Theme picker, strength, the
        takes' melody line and ★ Series theme (2026-11-03). Live on local ComfyUI: the graph
        runs, both transcriptions come back, the score lands in the sidecar and ranks
  - [x] the first-pass draft (2026-11-04): `seriesmith score-draft` (`--write`,
        `--replace`, `--keep-sound`), `POST /seriesmith/cue/draft`, the spotting sheet's
        **Draft…**, MCP `score_draft`. core/spotting.py the rules (stdlib), scoredraft.py the
        episode (the cut, the story IR, cue specs d01... and mix hits dh01..., voices only);
        the Music tables generated from STORY_STRUCTURES.md into core/structures.json
        (tools/make_structures.py, checked by test_docs)
  - [x] a show's own shape (2026-11-04): `sound.format` (`like`, `beats`, `other` with
        `talk_max` and `lead` / `theme_else`, `marks`); `gaps` (music only where no one
        speaks, runs within 10 s joined, under 10 s none); a cue split past 3 minutes at a
        sequence. Porch Lights' format in all 40 episodes' series configs
  - [x] drafting again (2026-11-04): a rendered draft cue kept on replace (`--rendered` /
        **Rendered ones too** replaces those too; a series theme's cue, and one a kept cue
        takes its theme from, always kept), a draft cue trimmed around a kept one (taking its
        take as the story theme where it made it), a trimmed cue's label its remaining beats
  - [x] character themes (2026-11-04): a series theme's `for` (whose it is: ★ Series theme's
        **whose**), the episode's story theme whenever its character leads it; a narrator's
        voice-over doesn't count toward who leads
  - [x] a script with no beat lines (2026-11-04): said at the top of Draft; a structure laid
        over the cut (spotting.layout: each beat at its `~%` from STORY_STRUCTURES' beat tables,
        in structures.json as `at`, on the nearest sequence start) and written into the script
        on ask (scoredraft.mark_script, the build's parse checked unchanged). Dean's seven built
        episodes (ep04-06, 15, 17, 19, 30) marked so, corrected by their narration
  - [x] the editor around it (2026-11-04): the cue window's cue picker (and ‹ ›, on the same
        tab); each cue fitted to the window on open (useSize watching a grid that appears
        later); hits dragged on the spotting map; the shot form's **Beat**, **Theme mark**
        (`// beat:` / `// theme:` lines above the shot) and **Hit** (on its first frame), its
        help linking the spotting sheet, a show's format's beats offered (GET
        /seriesmith/structures); a cue that can't be planned says why (a shot under it with no
        take yet, left out of the cut, gone from the script)
  - [x] docs (2026-11-04): SOUND_GUIDE.md (the user's guide to the whole sound, in order: voices
        only, ambience beds, effects, the drafted score, themes, the mix, export), SCORING's
        first pass, AUTHORING's score lines and `sound.format`, the site's Sound page
  - [ ] heard: the drafts on Porch Lights ep01 and Dean, themes made from their takes, then
        Draft again with them (the user's)
  - [x] the skill: `// structure:` and `// beat:` in STORY_STRUCTURES' From beats to shots
        and the skill's outline step (converted scripts too); a Music table under each of
        the 14 structures (treatment, mood and energy, `story`/`show`/`runner` theme, hit),
        Episodic Drama (teaser and acts) added for procedurals and serial drama, and "Music
        in every structure" (music in the scene, montage, titles, `// flashback`); prompts/
        and the site regenerated (2026-11-03)
  - [x] the draft's timing: a pre-lap (a cue starts a second before its beat's cut, in the
        shot before) and a button (it ends on the beat's last cut; ending on a line: not
        yet) (2026-11-04)
  - [x] mark Dean Stories (Story Spine) and Fair Trade (Sitcom) with beat lines and show
        their drafted spots as tables, to check the Music tables against real scripts
        (2026-11-03: Dean ep35, ep38, FRTEST; four fixes from it: beats in a row are one cue,
        bumpers at each new sequence location merged into stings, the Sitcom's fix held to
        its last scene, music in the scene flagged rather than silenced; `// theme:` in
        STORY_STRUCTURES for the moments the beats can't find)
  - [ ] notes, optionally: ABC or a hummed idea -> a sketch -> a piano take (two passes);
        deferred (2026-11-04: themes from takes cover it)
  - [ ] the season view (themes by episode); deferred (the user, 2026-11-04: not needed yet)
  - [ ] a cue that ends on a line rather than a cut (the draft's button, the rest of it)

## Fixed: the voice model is two lists (noted 2026-11-01)

The series settings' **voice model** (`voice_target`, refs.py / SeriesForm) offers only audio
targets, so LTX-2.5 audio-only is the one choice, while a **dub track** (the Sound dialog's
"Generate a dub track", `VOICE_TARGETS` in the editor) is made on video models: H3 Ref2VA and
FastH3 Omni, and could be on H3 FL2VA, H3 Singularity or any H3-compatible model. One list of
what can voice a line (audio targets and the video targets that render a dub track), the same
in Settings and the Sound dialog, read from the targets (a capability, not a list in the
editor), with the series' choice as the Sound dialog's default.

- [x] One list (2026-11-02): `capabilities.dub_track` in target.json (H3 Ref2VA, FastH3 Omni,
      LTX-2.5: the three the editor listed, each with a clone path a dub track already uses;
      H3 FL2VA left out, since its clone lines are LTX-2.5 audio-only's, and Singularity,
      untried), `targets.voice_targets` (the audio targets and those), the series config's
      `refs.voice_target` and the episode's choice taking any of them, Series settings'
      **Voices** offering them, the Sound dialog's models read from the targets
      (`VOICE_TARGETS` gone) and starting on the series' choice. Each consumer keeps its
      kind: voice samples are made on an audio target (a video choice leaves them on
      ltx2_voice: `defaults.voice_target`), a dub track on a video one (an audio choice
      leaves it on H3 Ref2VA: `defaults.dub_target`; jobs.dub_target for a request without
      a target). Docs: EDITOR, AUTHORING, API

## Importing an FCP7 XML (2026-11-02)

An edit made elsewhere (Premiere, DaVinci Resolve, Final Cut 7, or our own `assemble --xml`,
nle_xml.py) becomes a **new** show and episode that can then be enhanced: a shot regenerated,
cues, effects and ambience added, re-cut. `seriesmith/xmlimport.py` (stdlib xml.etree);
docs/IMPORT_XML.md is the user's side, API.md `POST /seriesmith/import/xml`, COMMANDS.md
`import-xml`, EDITOR.md the wizard's **From an edit (FCP7 XML)…**.

- [x] **Reading** the document's first sequence (a nested one isn't one): rate (timebase +
  ntsc: 24 NTSC is 23.976), the format's size, V1, the audio tracks, markers. A pathurl is
  decoded (`file://localhost/C%3a/...`, `file:///C:/...`, `file://server/share` as UNC); a
  file that isn't there is looked for beside the XML. A clip's `-1` start or end (in a
  transition, as Premiere writes it) is resolved by `out - in`. A transition is put on the
  clips by where it is, not where the track lists it: between two clips a dissolve, its
  frames given back to both (our export cuts at the dissolve's middle, nle_xml.lay; the
  import takes the handles back so the cut's `dissolve` overlaps the full spans again); a Dip
  to Black a fade out and in; at one clip's edge (or `start-black` / `end-black`) a fade.
- [x] **Decisions** (each said in the summary's warnings when it loses something):
  - **V1 only**; a clip above it is listed, not imported. (Splitting V1 under what covers it
    was the other choice; V1 alone is predictable.)
  - **A gap** (a generator, a disabled clip) is a shot of black of its length, so the timeline
    and every sound anchored after it stay where the edit put them.
  - **Shot ids** sh010, sh020, ... in order, black included; when every clip's name opens with
    a shot id (our own export's "sh010 t03") those ids.
  - **The series renders on `hold`**: an edit's 1920×1080 is off H3's 32 grid and a long clip
    past LTX's longest shot, so the machine's default model would refuse the build. Hold takes
    any even size and any length (14400 frames). Its required first keyframe is each shot's
    first used frame (refs/shots/<shot>/first.png, made with its take), which is also where an
    image-to-video model starts when the shot is rendered again on one.
  - **Sound**: an audio clip linked to a V1 clip, same file, is the take's own sound (its
    level a gain on the cut entry's `audio`, disabled: silent). Another file starting where the
    clip does on A1/A2 is the shot's sound from that file (our export's voice stems). A clip
    with neither is silent (`audio: none`): the XML had no sound for it. Every other audio clip
    is a mix item (both passes), its file copied into audio/ (a name clash named by its
    folder: sh020_t01.wav), anchored on shots that have a file (an anchor on a missing shot
    would drop the item until it's rendered), Audio Levels value + keyframes as gain_db +
    points, fades, mute. Stereo as two mono tracks is one item. Track by name (track, file,
    folder): sfx/fx/foley effects, amb/room/bed/atmos ambience, dialogue/dx/vo/adr dialogue,
    else music; a second lane of a kind is a track of its own (track_list). **The imported
    tracks' faders are 0 dB and `duck_db` 0**: the XML's levels are the mix as made (an NLE's
    own ducking is in its keyframes); ours would dip it twice.
  - **Markers**: comment `hit` (our export's) is a mix hit; any other opens a sequence at the
    shot playing there (its name the id when it is one, else a comment).
- [x] **Media**, an option:
  - `handles` (default): each clip's span + handles (1 s, clamped to the file) cut
    frame-accurately (a coarse seek, then trim by time with half a frame's margin) to H.264 at
    master quality (takeimport.encode_span), the cut's trims the handles.
  - `reference`: **a take can't point at an outside file**: every reader (the editor's video,
    peaks, thumbnails, upscale, post, assemble, discard) opens `<renders>/<shot>/<stem>.mp4`.
    So the take is the source whole, **hard-linked** where the volume allows (an NTFS hard link
    needs no admin rights; a symbolic link does), else copied, never re-encoded
    (takeimport.link_or_copy). Nothing writes into a take's mp4 in place, so the two never come
    apart. A non-H.264 source doesn't play in the editor: said per clip.
  - `proxies` (added the same day, the user's ask): reference, and a source the editor can't
    play (takeimport.playable) gets an H.264 proxy made once per source in `<ep>/_proxies/`
    (CRF 16, at most 1920 wide: a 4K/6K camera original plays as HD and encodes in a fraction
    of the time; every frame kept at the source's rate, so a frame of it is the same frame of
    the original), cached by the source's size and mtime; each take is the proxy, linked. The
    take's sidecar records `master: {path, size, mtime}`; **assemble cuts a take with a fresh
    master from the original**, always re-encoded at master quality (a ProRes stream can't be
    copied into the cut), and the XML export points at the original. A master that moved or
    changed: said, cut from the proxy. Separate playback and master files fit the take model
    this way (the playback file is the take's mp4, the master one record field), so "conform
    whole files" wasn't needed. An upscale or post of a proxied take works from the proxy.
- [x] **Jobs**: the show is written and built in the request (fast); each media group (a
  source's clips; the gaps' black) is a `cpu`-lane job (`xmlmedia`, api.LOCAL: journaled,
  Retry runs it again and keeps finished takes and a fresh proxy). The cut pins take 1 (a
  later render doesn't take the imported trims); the takes are reserved when the job runs,
  not at import, so a queued take never waits on a job a sweep can't see.
- [x] **Tests**: tests/test_xmlimport.py: a hand-written Premiere-shaped fixture
  (tests/fixtures/xml/premiere_edit.xml: 24 NTSC, file:// URLs, a fade in, a centred dissolve
  with -1 ends, a gap, a fade out, a missing file, V2, linked stereo, music with level
  keyframes, a disabled effect, a second music track, markers and a hit) read, then imported
  each way with testsrc media (an mpeg4 .mov the browser can't play, an H.264 mp4) and
  assembled (192 frames, the XML's); a round trip (a tiny episode `assemble --xml`, imported:
  the same cut.json, the music item, its point and the hit, and the same V1 exported again);
  the route (dry run, upload, errors, its jobs on the queue) and the command. web:
  test/xmlImport.test.ts (the choice in the wizard, the dry run, the media option, Import).
- [x] **Live** (2026-11-02, local only): Ballroom ep02's final cut exported (`assemble --xml
  --name` a scratch name, moved out of its renders/) and imported into
  ComfyProjects/_xmlimport_test: 10 shots, 10 takes (handles: 18 s), 13 mix items (10 effects,
  the park_table bed as an ambience item, 2 cues), 3 sequences (sq01-03 from its markers), the
  4 voice-stem shots their stem as their sound and the 6 silent ones silent. Exported again:
  V1 identical (every start, end, length), all 17 audio clips at the same spans, the same
  markers, 620 frames as the original. Through the API in-process: 10 shots, each take 1 ok
  and usable, no missing refs. `--media proxies` on the same (all H.264): each take a hard link
  of Ballroom's take (same file), removed again leaving Ballroom's at one link. What doesn't
  come back from our own export: the beds and per-shot effects as plain items (they're
  computed, not stored), voices-only as per-shot stems, and the ducking (off).
- Dropped (2026-11-09): **Describe shots**, a vision model writing each imported clip's action. No
  LLM goes into the application. Each action line stays its clip's name.
- [ ] Later, if wanted: V2+ as cutaways (split V1 under them), clip speed (timeremap), the
  linked audio's slip, a second sequence chosen (`--sequence`), FCPXML (Final Cut Pro X's
  own format), EDL.

## More music models, Pika H3 Flex, and a way to ComfyUI (2026-11-04)

- [x] **`minimax_music3`**: MiniMax Music 3 on ComfyUI's core nodes, for songs (its words the
      clearest measured; as score it leaks a voice). Decoded tiled: a two-minute song decoded
      whole aborted ComfyUI. Live: a 52 s score cue and a 125 s song (95.7 of 96 bpm, WER 0.12).
- [x] **`minimax_music3_cloud`** and **partner nodes on your own ComfyUI**: a workflow marks
      the node `_meta.partner`; the local backend sends the Comfy API key as the job's
      `extra_data.api_key_comfy_org` and the take counts against the paid limit. Not run live.
- [x] **`mrt2`**: Magenta RealTime 2 on seriesmith's own node (`comfy_nodes/mrt2.py`, the
      magenta-community PyTorch port carried in `comfy_nodes/_mrt2`), the arc a style a bar,
      a theme blended in by MusicCoCa. Live: shape error 0.28 over four seeds through the
      target (SA3: 0.34), the proxy on the small model, a theme, the Features download.
- [ ] Magenta RT 2 **theme as notes**: its MIDI conditioning played a theme's notes (measured);
      a cue's theme as notes (a YuE2 plan's ABC, or SheetSage2's) into the node's segments.
- [x] **`pika_music`** on Comfy Router, and **hosted music models** generally (a cue take as one
      Router call, `cue.hosted_call`). A draft: Router lists `pika/pika-music` but answered a
      valid request "does not run this model yet". Switch it on once it's served.
- [x] **`pika_h3_flex`** / **`pika_h3_flex_fl2va`**: Pika's six-step H3 (a LoRA per H3 model,
      its templates' LCM on six manual sigmas, no sigma shift). Live: last-light sh050 at
      1344x768 in 47 s.
- [x] **No ComfyUI yet**: the Features window shows ComfyUI's own installs for this system and
      finds one that's running (`seriesmith/comfysetup.py`, `POST /seriesmith/comfyui/find`).

## Export's dialogue (hotfix, 2026-11-05)

- [x] Export, 2x Export and Master follow Play all's audio switch: on **recording**, the recording as the mix's
      dialogue track, with effects, ambience and music (`assemble --audio recording`; `master` stays the recording
      alone, to check sync). They never used it.
- [x] A take dubbed to the recording with its effects kept had only those in its mp4 (the voice taken out by
      Demucs), so with Demucs installed its export had no voice. The saver now puts H3's whole mix in the mp4, a
      dub of any source gets it back on a backend without that, and a take already saved that way plays its
      `_h3.wav` (`peaks.clip_audio`). Those old takes still play effects alone in Play all, which plays the mp4.
- On this branch, each shot's Sound card says what the cut and export play (below), so Export no longer follows
  the switch, which is for listening. `POST /seriesmith/assemble` and `/master` still take `audio`.
- [x] A shot on dub plays its dub in the cut and export (2026-11-07, branch `h3-resample-any-take`):
      `takes.cut_dub_spec`, `edit.effective_cut_audio`, `audio_dub` in the status, assemble's clip sound. A cut
      entry's own `audio` still wins; the editor never saves the dub into cut.json, and Adjust… opens on it. Play all
      plays a clip's replaced sound on the Dialogue track (`lib/mix.sourcePlan`): it played only the `<video>`'s own,
      so a replacement was heard only in the export.

## H3 re-render of a frame range (branch `h3-rerender`, 2026-11-05)

- [x] H3 Ref2VA, H3 Singularity and Pika H3 Flex take eight subjects, as the node's nine sockets allow: `<Picture 1>`-`<Picture 3>`, the
      plate still `<Picture 4>`, then `<Picture 5>`-`<Picture 9>` (`recipe.subject_slots`, the graphs, `shotplan.MOST_SUBJECTS`
      and `plate_at`, `cloud._lower_loader`, `prompt.subject_pictures`). A shot of three or fewer is unchanged: same prompt,
      same pictures, no stale takes, no new placeholders. Pika H3 Flex too.
- [x] FastH3 Omni the same, its plate moved from `<Picture 9>` to `<Picture 4>`: one layout for the family (FL2VA aside), and no
      placeholders past the last subject. Its existing takes read as stale, since their prompt changed; a shotlist built before renders
      as it says (`defaults.subject_slots`).
- [x] Each job's picture sockets are set from the loader (`compile.wire_pictures`): a saved `H3_Ref2VA_Shotlist_v1.json` wins over the
      repo's graph, and its four sockets sent four pictures on an eight-subject shot, seen in ComfyUI's history on a live render.
- [x] Decided, measured live 2026-11-06: frames of a take are made again by sampling the whole clip with the rest held by a noise
      mask (`SeriesmithRangeLatent`), at any length. No slice with breathing room: the held frames are a first-generation decode, so a
      splice would add a join and save nothing. Outside the range the video latent holds to rounding (2.4e-07) and the
      sound to rounding; pixels change a little beyond the range (asked 74-123: 70 on; asked 52-87: about 47-104).
- [x] The wording goes with it (`redo_range.prompt`; else what the source take asked, its frozen shotlist, not today's script). On
      sh110 three new seeds alone kept the same exaggerated yawn; new wording (t14-t16) changed it, the seed the details.
- [x] A take with no latent on this model is held from its frames through the model's VAEs (`via: "frames"`). A 124-frame encode ran
      fine. Held frames: 36 dB against the source (42 with the kept latent). Sound through the audio VAE: correlation 0.91 on H3's own,
      1.5-3.5 dB less above 1 kHz. LTX-2 and FLUX.3 takes joined without a visible jump in stills (not yet watched).
- [x] Every range take has the source's own sound over the picture (`SeriesmithRangeFinish`; the held audio latent only guides the
      new frames). An encoded take keeps the source's size and frame count as near as the model's grids allow: frames rounded up to
      the grid for sampling, trimmed back after. A different frame rate is refused.
- [x] Tests (`tests/test_range_render.py`), `docs/API.md`.
- [x] The editor: **Re-render part of this take…**: the range picked on the take's video, the prompt ready to edit, a new seed. `docs/EDITOR.md`.
- [x] LTX-2 too (`range` in its target.json: `grid: "ltx"`, 8 frames a step; `stages: 2`). Decided, measured live 2026-11-06 on sh080 t03,
      frames 30-60: both stages hold the take. Only the second (A) kept the original action: 0.85 sigma can't make a new one from the old
      latents. Both (B: `SeriesmithRangeLatent` on the half-size stage, the take encoded at that size; `SeriesmithRangeRefine` on the second,
      the kept latent with the range's steps from the upscaled first stage, only those open) took the new wording. Steps outside the
      range held exactly, the audio latent identical, 55-70 s. Change reaches about 25-64.
- [x] LTX-2 with no kept latent: the take's frames through its VAEs at both stages (`via: "frames"`), and any model's take. Against the
      source outside the change: own take 38 dB (42-44 kept), sharpness down 4-11% (under 1% kept); H3 33 dB, FLUX.3 38 dB, sharpness down
      25-32%. Watched: no seams, and FLUX.3 came out clean. Encoding darkens the frame's outer 8-32 px by up to 6 levels out of 255 (2.5
      at the bottom; 0.1 kept), seen by the user on sh080 t09.
- [x] Decided, encoded edge darkening stays: minor, hard to see unless looked for (took the user a few viewings), and a crossfade or encoding with extended edges would add more complication than it saves. Part of the price of re-rendering a portion; a full new take avoids it.
- [x] A range re-render uses the take's own size and length, kept latent or not, rather than refusing when the shot has moved.

## H3 upscale on ComfyUI's own nodes (branch `h3-core-upscale`, 2026-11-06)

ComfyUI 0.44 has H3's latent upscaler (`MiniMaxH3LatentUpscaleWithModel`, `LatentUpscaleModelLoader`) and
context windows (`MiniMaxH3ContextWindows`), so the H3 targets use those by default, even with the packs
installed. The target's `fallback` is the pack: LBH's or its Plus (the same node id) and obvpm's windows. It's
used on an older ComfyUI, or when the recipe's `upscaler` / `windowing` (or `--upscaler pack`, `--windowing pack`)
asks for it. With neither, the upscale doesn't run and says what to do: update ComfyUI, or install a pack.
`upscale.not_ready` settles the nodes (`choose_nodes`) before a graph is built, by the node classes, not a version
number. The Plus refusal is gone, as is the user-facing wording on which pack is better: results are the user's to
judge. The Upscale dialog offers each choice only where both sets of nodes are on this ComfyUI (`node_choices`).

The A/B behind it (local ComfyUI, real graph with one node swapped, against the original take):

- **Upscaler**, LBH vs core: 40.9-44.2 dB at the default start, 41.1-44.2 dB at `--detail` 1 and 2. Core is LBH
  with chunking off (0.00% on the same latent, on CPU); LBH only chunks above 32 latent frames. Colour against
  the original: core equal or slightly closer on the four takes at the default start. No sparkles or marks in
  the crops checked. A two-take sample at `--detail`, plain prompts and a plate from the take.
- **Windows**, obvpm's vs core's at 124 frames / 39 overlap, pyramid, FreeNoise off (`window_frames`: the length
  rounds down, the overlap up): pixel-identical on two windows; on a 15 s stitched latent identical to about 60%,
  then ~43 dB; the same speed. The classic (non-dynamic-VRAM) loader wasn't tried: core skips its clamp for packed
  latents, which didn't crawl on the dynamic loader.
- **Open:** core's windows drop a first-frame keyframe from any window not containing it. With a first frame in
  the re-sample, obvpm's stayed closer to a no-window reference at the shot's end (34.4 vs 31.8 dB). It matters for
  a keyframed or continuity shot longer than a window.
- **The floor:** on the short control take, the same graph on ComfyUI 0.44 with PyTorch 2.15 is 43.6 dB from itself on
  0.43 with 2.14, for LBH and for core alike, and LBH vs core is 43.6 dB on either. A repeat on one setup is
  frame-identical. So a short take's LBH-vs-core gap is no bigger than what that software update moves; only the
  long takes (40.9-42 dB, LBH chunking) go below it. Live on the branch: the graphs match the A/B's, four cases.

- `--detail` 1 and 2, on the two takes: softer and further from the original than the default, on both upscalers.

## Upscales get their keyframes back (branch `h3-core-upscale`, 2026-11-06)

A queued render stages its inputs after writing its record (`runner`), so no record had `inputs` (0 of 134 here). So an
upscale's graph had no first or last keyframe, and `continuity_source` found nothing: `continuous: first` upscales
started from no frame at all rather than the previous shot's upscaled last frame, with no note. The tests mocked
`continuity_source`, so they stayed green. `continuous: latent` (`held_from`) never read `inputs` and wasn't affected.
The record now gets `inputs`, and `takes.recorded_inputs` recovers keyframes from `refs` for the takes already made.
A composed input (LTX ingredients' sheet) isn't in `refs`, so a take made before this fix still doesn't recover it.

Live, Dean ep02 sh010 t02 -> sh020 t02 (`continuous: first`, core upscaler, no windows), the upscaled last frame against the
next shot's upscaled first frame: 28.7 dB without the fix, 37.3 dB with it (the originals, scaled plainly: 34.4 dB). One pair,
measured at the join only; the keyframes coming back on other shots wasn't measured beyond the earlier first-frame test.

## H3 re-sample of another model's take (branch `h3-resample-any-take`, 2026-11-06)

Tested first on Ballroom ep03 sh070: a Wan 2.2 take (832x480, 109 frames) at 2x, against SeedVR2 7B. SeedVR2: 39.2 dB
to the take, the same performance, more texture, more shimmer (0.51-0.62 against the take's 0.37-0.40). H3 (`fasth3_omni`
from step 7 of 8): 31.6 dB, the characters pulled back toward their references, contrast steadier, shimmer 0.25-0.38. One
step earlier it pushed the skin pink. Decided by the user on watching it: worth offering, for going from about 768 to 2K/QHD.
H3 only: LTX's 2x upsampler is a stage of its own render and isn't offered.

- `upscale.through` (dialog, recipe rows, API, CLI by recipe): a target with `upscale.any_take`. A take of the same family
  (`family`: the upscaler's class) ignores it, keeping its own re-sample and kept latent.
- Ref-based models only. An FL2VA target would need a keyframe from every take: untested.
- It reuses the frames route the re-render has: `retarget` for the prompt, frames padded to the grid and cut back. Shot's
  length comes from the take. The compiled shotlist is kept as `.up.shotlist.json`.

## Step 15 — models behind other APIs (designed 2026-11-04; docs/DESIGN.md, section 9)

Add any hosted model on any provider, for video, image and sound, without code: the mapping
from a shot to the request, the prompt, how references get in, and how the result comes back
are all data, edited in the app. First providers: ElevenLabs, fal, Runway, BytePlus
(Seedance, Seedream), Atlas Cloud (many models, Suno among them), then OpenAI, xAI and others
as wanted. Decided with the user 2026-11-04: generic rather than per-API; overrides belong to
the show, keys to the machine; a voice is heard before any line is paid for. Each paid probe
is asked for first.

**1. The mapper apart from Router** (the goldens byte-identical)
- [x] One check for "this target is hosted" (`targets.is_hosted`) and one reader of its block
      (`targets.hosted_block`) in place of the `get("router")`-style checks across the package;
      only `targets/__init__.py` and `limits.py` (which writes into the block) name it, and the
      dry run's route, which takes a Router target by name (`tests/test_request_map.py` holds this).
- [x] The mapping's functions in one place (`targets/generic/request_map.py`), from `router_video`,
      `router_image` and `cue.hosted_call`, which now takes its prompt and lyrics in any place an
      input can name. The Router goldens unchanged. What a request contains stays with its
      caller; there's no one function for all three, as pictures differ too much.
- [x] One rule for the nearest ratio (2026-11-04). Video measured the plain difference of the
      shapes and image the difference of their logs. Plain difference favours tall ratios: on
      Veo's `16:9` / `9:16` anything from square to 1.17 wide was sent as 9:16; and it couldn't
      read `2.35:1`. Now the log rule for both, a tie to the ratio listed first. Requests
      change for video shapes between two ratios: a square on Veo is now 16:9 (was 9:16), and
      4:3 on Kling and MiniMax H3 is now 16:9 (was 1:1; an exact tie). The goldens didn't move.

**2. Prompt parts and templates** (the goldens byte-identical)
- [x] `targets/prompt_template.py`: `{part}`, and `[[...]]` sections that go whole when a part in
      them is empty; read in one pass, so a shot's words can't act as syntax.
- [x] The two prose writers give parts (`shot_parts`; what they share in `prose.scene_parts`), and
      each default template reproduces today's prompt exactly: every golden unchanged.
      `recipe.prompt_template` in a target.json changes a shot's prompt, on a Router model, a Wan
      model or LTX-2.
- [x] Seedance's definitions, its voices and Kling's mentions as request template values
      (`recipe.prompt_request`), placed by the template rather than by code in `router_call`.
      Their wording, and whether they're filled (`define`, `mention`), stay as they were.
- [x] Prompt profiles: `recipe.prompt` names one in `presets/prompt.json` (a writer and its two
      templates). Ships `prose`, `prose_silent` and `image` only: a `seedance` profile is worth
      having when a second provider serves Seedance (step 4), until then it'd say what `prose` says.
- Not templated yet: H3's `fields` writer and the other targets with a writer of their own, image
  prompts' own wording (their request template is), and sound (step 5). A wrong template stops
  the job and says why (`job.error`); checking one as it's saved comes with the tool (step 3).

**3. The mapping tool, on Router models** (no new connections)
- [x] The Models window: a job's values with the chosen shot's real ones, the API's fields,
      the prompt template below, a live dry run with the key hidden, several test shots
      (dialogue, several subjects, no keyframe); saving refused while a required field is
      unmapped. The same screen adds a model and edits one, video and hosted image alike.
- [x] Overrides in the show (`<show>/targets/overrides.json`: only the fields changed, only the
      ones `targets.SHOW_FIELDS` allows, so a shared show can't repoint a model), **Back to
      shipped**; the `mapping` stale reason (a prompt that differs only by its template is
      `mapping`, not `script`; a take with no template stays as its sidecar was).
- [x] First cut for a look: the **Prompt & mapping** panel (`components/PromptMapping.tsx`,
      `seriesmith/promptview.py`), every video model, adding and editing alike: the templates, the
      parts with the shot's values, the prompt as sent, the shotlist entry, the request.
      A model with a writer of its own (H3, the reference-sheet LTX-2s) shows it read-only.

**4. Providers, the step engine and reading an API's reference** (`backends/http.py`,
`providers.py`, `apispec.py`, stdlib only: nothing new for `requirements.txt`). Proved on the
hardest first: Atlas Seedance (upload first), ElevenLabs (bytes back), OpenAI (multipart in,
download with the key). Reading the reference moved up from step 7 (decided with the user
2026-11-04): without it, a provider can be added and its fields can't be read.
- [x] A model read from an OpenAPI document (a URL, or pasted) by the same proposer as
      Router's (`apispec.py`); else a pasted cURL or sample JSON (Atlas publishes per-model pages,
      no OpenAPI file). The definition is plain data, so an LLM can draft one from a provider's
      docs, and the validator and dry run check it. A key in a cURL is never kept.
- [x] A provider set up from scratch in the app (`providerdraft.py`, `AddProvider`): a cURL or OpenAPI
      document read into a form, example answers filling in more, a free key check, its first model
      from the same request, and **The calls** showing every call a take makes.
- [x] Provider definitions on this machine (`providers.py`, `presets/providers/` the shipped
      untested ones); **keys per provider** in its settings (never the series config),
      environment variables over them (`SERIESMITH_KEY_<ID>`); Settings lists them, write-only.
- [x] Steps: request, values taken, wait condition; JSON or multipart in; JSON or bytes out.
      Reattached after a restart by its job id, as Router's are; a lane per provider with its
      own parallel limit; the paid limit counts them; no submit retried blind.
- [x] Results by data: the status field, its done and failed values, where the files are,
      failure read from the result too (fal says `COMPLETED` for a failure), links saved when the
      take is collected.
- [x] Several outputs as several takes (Suno's two tracks), music only for now: `api.tracks` in a target
      says how many; each further one is its own take, recording `track` and `track_of`. One that fails
      leaves the first standing. Video and pictures still keep the first.
- [x] Authentication: a header, bearer or query key by data. The key goes only to the provider's
      own host and port, a redirect elsewhere drops it, an echoed one is cut from errors.
- [ ] Signed ways of authenticating (a JWT for Kling's old keys, then others as wanted) as named
      methods.
- [x] Pictures: inline (base64 / data URI) where the API takes it, a provider's upload route,
      multipart with the request.
- [ ] An asset library by data (Atlas turned out not to need one), and a link for an API that
      only fetches URLs: the Comfy asset store while there's a Comfy key, or a **media host** of
      the user's own (a bucket).
- [x] Atlas proved live (2026-11-04): Porchlights ep02 sh630, proxy, Seedance 2.5 reference to
      video, upload, generate, poll, download, 2:31. Two things no docs or local server showed:
      Cloudflare's 403 (1010) for Python's default User-Agent, and `uploadMedia` answering
      `data.download_url` where its docs say `url`. Its other models and kinds aren't proved.
- [x] One model, several ids (`api.models`, by what's sent: Atlas's Seedance image-to-video and
      reference-to-video). A provider's documented models as a list to pick from, needing nothing
      pasted (`presets/providers/atlas.models.json`, read from its docs 2026-11-04; only Seedance 2.5
      reference-to-video proved).
- [x] From a provider's docs, read for free 2026-11-05, no key: fal's FLUX 3 Max page (its address alone
      fills the form: the cURLs in its HTML, the OpenAPI document it links, `Key ` before the key, a
      failed job as done with `error` beside it) and BytePlus's cURL (a list of typed items, every item
      read). Neither proved by a real take. fal documents no plain-HTTP upload to its CDN, and takes
      data URIs ("not recommended for files larger than a few KB", no limit stated): frames go inline.
      BytePlus refuses a photoreal person as a URL; a face as a data URI is untested, and a direct
      key's way into its asset library unknown (its docs pages draw themselves in the browser).
- [x] Higgsfield shipped untested (2026-11-05, read from its docs, tried on local servers only, no key):
      `presets/providers/higgsfield.json` and its list. A file goes by an address its answer gives, a
      step's `body` (the file as the whole request), `headers` from an answer, and `key: false`; the
      form offers it. Its model pages' Markdown (`<page>.md`) has the whole schema where its OpenAPI
      document has a few models only. Status `nsfw` is a failure. No seed on its Seedance, H3 or
      Kling; H3 only at 2K, from 5 s. An `Idempotency-Key` could make a submit safe to ask again.
      Not proved: anything by a real take, and how its Seedance prompt names a picture.
- [x] Runway shipped untested (2026-11-05, from its OpenAPI document, local servers only, no key):
      `presets/providers/runwayml.json` and its list (`runwayml` because the Router's model is already
      `runway_gen4_turbo`). What it asked of the engine: `headers` on every request to its own hosts,
      a form posted to the address its answer gives (S3's way, `response: "none"`), `endpoints.video_text`
      and `values_text` for a shot with no pictures, `by_size` on a ratio that's also a resolution, a
      list's `arguments`. Its H3 is sent with `promptExpansionMode: disabled`. Not proved: a real take,
      how its Seedance prompt names a picture, a file under its 512-byte floor (no real frame is).
- [ ] A live paid proof of ElevenLabs (needs step 6) and OpenAI: tested against a local server
      answering as their docs say, and marked untested until a real take comes back.
- [ ] Router's `seedance_asset` moved onto the steps, as the proof the asset path is data.
- [ ] **Asset libraries** (Seedance and its resellers; 2026-10-21). Register a fetchable URL,
      poll until it's Active, send `asset://<id>`. Router does this already (`via="seedance"`,
      `RouterBackend.seedance_asset`, Comfy's `/proxy/seedance/virtual-library`) because
      BytePlus refuses a photoreal face as a plain URL; a face sent as base64 is untested.
      Atlas Cloud exposes the same BytePlus library differently: assets on
      `console.atlascloud.ai/api/v1/sd/assets` (register `{type, url}`, poll
      `/sd/assets/<id>` for `Active` / `Failed` with `error_code`), generation on
      `api.atlascloud.ai`, a public URL only (no base64; its `model/uploadMedia` gives one
      without a Comfy key). Video and audio must be registered there; images may go inline.
      **Read 2026-11-04: Atlas's Seedance 2.5 page says the opposite of these notes:** URL and
      Base64 are registered for you, and no page shows this route. So Atlas ships as upload,
      generate, poll, and this item waits for an API that does need it.
      Registration validates up front (Atlas: images 300-6000 px, aspect 0.4-2.5, < 30 MB;
      video mp4/mov 2-15 s, 24-60 fps, 409,600-927,408 px; audio wav/mp3 2-15 s): its
      refusal is the take's error, said plainly. Atlas's docs (read 2026-11-04) show
      `uploadMedia` but not this route: settle it from the per-model pages when building.
- [ ] **Keep registered asset ids**, by (provider account, file sha256): an id means nothing to
      another provider. Skips the ~4-5 s per picture each Router Seedance take spends
      uploading and registering again (step 14).
- Router's Seedance 2.5 schema takes an image or audio as URL, base64 or asset id; a video as
  URL or asset id only. Atlas's guide notes the asset step is the required way in for
  video and audio references; expect each reseller of a model to differ in exactly this.
- [ ] Costs where the API reports them (often it does, in its own units, as Router's
      providers do).

**5. Sound on hosted models**: each kind's job as a call as well as a graph.
- [x] Music, songs and score (2026-11-06): `suno_chirp_v6` on Atlas (`instrumental` for score) and
      `elevenlabs_music` (`force_instrumental`), one call a take, tested against a local server only. Shipped
      rather than added in the wizard, as a cue model needs its prompt writer. ElevenLabs' music is a
      way of its provider definition (`ways.music`), its address not being speech's. Suno's label says
      its licence is unverified: Atlas runs it "via APIMart", and sources say Suno has no public API.
- [x] Suno score, live (2026-11-06, `porchlights/ep02` cue d03, one run, listed at $0.132): asked 32 s at
      100 BPM with a 169-character `style`; two tracks back in about 30 s, 31.96 and 32.40 s, heard at 100.1 and
      100.19 BPM, both kept as takes, one paid run counted. One run at one tempo.
- [ ] Still to prove live: Suno singing lyrics as written (waits for a real song), a much longer `style`
      (Atlas states no limit), and all of Eleven Music (needs a key on this machine: the BPM in its words, a
      prompt's lyrics sung as written).
- [ ] Only if a prompt's words fall short: Eleven Music's composition plan (chunks with their lyrics and
      enforced lengths), which could also carry a cue's sections.
- Decided with the user 2026-11-06, not doing: ambience and effects on hosted models. A text-to-sound model
  makes effects from words, not foley matched to the picture, which is what the effects track needs.

**6. Voices, then lines**
- [x] A voice per character: a provider's speaker (an id per provider, on the subject in the
      series config: `voices.<provider>`; one private to an account fails plainly on another's),
      listed from the provider for free with its previews, auditioned on a short sample in the
      character's own words through the voice ref's takes (`generic/router_audio.py`, ElevenLabs'
      list). Built on local servers only, 2026-11-05: no key, no real take. A reference sample
      (cloning, a provider's IVC) isn't built. Tried live with no key the same day: `/v1/voices`
      answers with its 21 voices and their previews; `/v1/shared-voices` only at a page of 3 or so,
      with no search or later pages (401), so the library is behind the key, or on its site.
- [x] Lines refused until the voice is picked; the count of lines and characters shown first, and
      a generate must name the total it was shown (`lines.py`, the Recording window). 2026-11-05, on
      local servers only: no key, no real take.
- [x] A line per take, the words alone in the request; laid in script order, with the pauses
      silent shots' `dur:` give, into the episode's recording; `align` windows the shots from it.
- [x] The API's own timings where it gives them (ElevenLabs `with-timestamps`, a definition's
      `timed` way) in place of Whisper (`<recording>.words.json`, which align reads). The mp3 they
      come in may start a few ms late of its timings: only a real take will say if that shows.
- [x] A character's whole file (all of Crane's lines, from an actor or a site) cut into a take per
      line and mixed with lines made here (2026-11-05, `lines.cut_character`; heard by Whisper, tested
      on words beside the file: no real file yet). One recording, as a video model lip-syncs to one
      sound. People talking over each other isn't handled: Demucs splits voice from music, not voice
      from voice.
- [x] Generate all of a character's lines, on its voice row, as a take per line rather than one
      file to cut (2026-11-05). A local model too (LTX's voice): from the description, continuing the
      character's sample, else the first line made for it, leaving the ref's takes and sample alone.
      Measured on Dean Stories ep10 through refs, by hand the same way: Whisper heard 11 of 14 whole,
      one word-only line lost ("Goodnight."), two with words dropped or changed. A real run of this
      button hasn't been: those were voice takes by hand.
- [x] One choice for a shot's dialogue (decided 2026-11-05, after four unconnected places: Next take, Dub to,
      In the cut, an episode switch): on Generate or Clone the cut plays the take's own sound; on Dub the next
      take and the cut both play the dub (`takes.cut_dub_spec`). A take rendered to it also keeps what the model
      gave back (`_h3.wav`: the line copied, what it made around that; the saver muxes it into the mp4, ComfyUI's
      assets too, and `remux_dub` for a take from an older node pack), heard in the take's preview, and in the cut
      if asked for that shot (`dub_model_sound`, no render). Proved on Dean Stories ep10 sh020 t04, local H3: the mouth matched its
      line, from a whole-character file, 2026-11-05. Sources: its lines (`from: line`), the recording,
      a dub track, any take's sound, another shot's too. A cut entry's own `audio` still overrides. A shot on
      its lines or another shot's sound takes that length on its next render, with a little air. **Line up
      with the take** (Whisper, both first words; `dub_offset`) cheats a line under a good render, free.
      `assemble --audio recording` stays for the command line. Lay and align stay, for whole recordings and
      to lay lines end to end. Tested on local servers and the stand-in for ComfyUI: no real dub render yet.
- [ ] Text-to-dialogue (all the lines in one call, its segments per input) as an option for flow;
      one line can't be redone alone there. `previous_text` / `next_text` for flow between single
      lines. A script's delivery note as a v3/v4 tag ([whispers]): it's left out for now.
- [x] "Generate missing" (voices, refs, shots) in the paid colour (`h3-paid`) when a model it uses
      is hosted, 2026-11-05; voices ask first. A money total first, per provider, isn't built.
- [x] A redone line that changes length moves what follows: those windows go stale, and the
      shots they touch say so before anything is re-rendered (measured 2026-11-05: `script` from the
      moved window). Aligning again keeps a silent shot's length from its window (it was 3.04 s).
- [x] It said so too often, and each is a paid re-render if believed: every dub shot before the
      redone line went `ref` (its whole recording's sha1 changed, its own window's sound didn't), and
      every shot after went `script` for a window that only moved. A take on a laid recording now
      remembers which line takes it spoke (`lines_sound`) and the shot apart from where it sits
      (`place_free_hash`), so only a shot whose own sound or length changed goes stale. A take from
      before this, or a recording replaced by hand, can't say what changed, and goes stale as it did.
- [ ] Only if it proves needed: a script field for a pause between lines in one shot.
- Replaces "ElevenLabs and the like as voice models" under "Voices before the picture".
- [x] **Voice models that clone** (2026-11-07, decided with the user after a listening test in
      ComfyUI): `drama3` (Fish Audio Drama 3 on PedroMarinhoDev's ComfyUI-Drama3), `qwen3_tts`
      (Qwen3-TTS 1.7B on flybirdxx's ComfyUI-Qwen-TTS) and `fishaudio_drama3` (Drama 3 through
      ComfyUI's Fish Audio partner nodes, paid). Each is sent the words alone and clones the
      character's sample (`capabilities.reference_clip`: 5-20 s, 10-30 s for Fish, not LTX's
      1.5-2.5 s head; `reference_text`: the sample's words when seriesmith knows them, the line its
      take was asked to say or a recording's timings); Drama 3 hears them itself (Qwen3-ASR in the
      graph). With no sample: Drama 3 picks a voice steered by the `voice` line as a bracketed
      direction, Qwen designs one from the description (VoiceDesign's instruct). Features: Drama 3
      with W4A8 (24.6 GB), and W6A8 / int8 offered beside it, the largest installed used (a models
      spec's `prefer`); Qwen's three models fetched into `models/qwen-tts/<model>/` (a fetch's `dir`:
      the pack reads them there, not under `Qwen/` as its README draws, and downloaded them by itself
      when they weren't). A line's take on a local model is checked for fetches, and a partner node's
      take counted against the paid limit, as a ref's is. Live through `seriesmith refs --voices`
      (RTX 5090): every take's words right; Charming cloned at 136 Hz (Drama 3) and 119 Hz (Qwen)
      against his sample's 122; neither read a description aloud.
- [x] Drama 3 reloaded its 24.6 GB model for every job (23-30 s of a ~50 s take). Not the pack:
      ComfyUI's RAM-pressure cache (its default since 0.40) frees in-use outputs over 512 MB when
      free RAM falls under 10% of it, and with the experts in RAM (the pack's default) free RAM hit
      0 GB on a 64 GB machine. Now `experts: auto` (2026-11-07): in VRAM when the file and 4 GiB fit
      the GPU ComfyUI reports (refs.stage_gpu_memory, drama3/target.py experts_where), else in RAM;
      the Features text says what RAM the in-RAM case needs. Live: the next take 13 s, no reload.
- [ ] `fishaudio_drama3` live: not run, it's paid. Each take's Instant Voice Clone makes a private
      voice on Fish Audio's side; ComfyUI reuses the node's output while the sample is the same, but
      a restart makes another.
- [x] Qwen's cloning on transformers 5.21+: flybirdxx/ComfyUI-Qwen-TTS#115 merged 2026-11-10, so the
      pack's main clones again (before it, a clone failed with "property 'upsample' ... has no
      setter").

**7. Presets**
- [ ] Presets as data files: fal, Replicate, ElevenLabs, Runway, BytePlus, Atlas, OpenAI, xAI,
      Gemini / Vertex. Shipped as untested drafts, inert until a key is added; a user's own
      added without a release.

## The storyboard: an episode blocked in from a story structure (designing; 2026-11-08)

The structures shape the score (the `// structure:` and `// beat:` lines, the first-pass draft) but
nothing yet uses them to lay out the episode. The storyboard is a window of its own, opened like
the player or the scoring windows, with the room to see a whole episode: a structure and a
duration go in, and a script of held stand-in shots comes out, blocked in and ready to fill.

Its job is to build an episode, not to revisit one. Beats moved afterwards don't matter: the
story has been written by then.

**No LLM in seriesmith.** The board is arithmetic and forms. Whoever wants an LLM to fill a block
in uses their own client (the script skill, `seriesmith mcp`).

**The script stays the source, and its format doesn't change.** What the board shows is what's
already there:

| On the board | In the script |
|---|---|
| An act's row | the act its beats belong to in the structure's table; the script says nothing |
| The structure band, spanning its shots | `// structure:` and the `// beat:` lines, as the score reads them |
| The thin box opening a sequence (its place and cast) | the `#` header; the cast is written to each stand-in's `who:` |
| A stand-in tile | a real shot on `target: hold` |
| The episode's duration | the sum of the shots' `dur:` |

An act is part of the structure and a beat sits inside it; a beat is not a sequence (a sequence is
a place: STORY_STRUCTURES.md). A blocked shot:

```
// structure: Three-Act

// beat: Inciting Incident
# sq02  street

## sh050
target: hold
who: june
dur: 3.5
Something breaks the status quo and creates the central problem.
```

**What a stand-in is, exactly.** `target: hold`, no picture (no `first:` line and no file at
`refs/shots/<shot>/first.png`: a dropped picture may never reach the script), no `continuous:`,
no dialogue, and its action still the structure's guidance word for word. Anything else counts
as built and nothing here touches it.

Tried 2026-11-08 on copies of `examples/starter`: a `#` header with no shots under it passes
`check`; a `target: hold` shot with no picture passes `check` and `build` and gets its own
shotlist, with or without `who:` and `size:`; a shot with no action fails `check` ("has no action
and no dialogue"), so the guidance text is needed as well as useful. Not yet tried: rendering a
stand-in (the target's `keyframe_required` should refuse it, free either way), and Draft… on a
blocked episode.

**Duration comes first.** It's required before any shot exists, and until the shots are made it
only changes a preview. A beat's shots are its share of the duration divided by a typical shot
(3 to 4 s, as "From beats to shots" says). At 3.5 s: 3 minutes is about 51 shots, 7 minutes 120,
22 minutes 377, 100 minutes 1,714; Three-Act's Inciting Incident (2%) is one shot, 2 or 3, 7 or 8,
34. Beats that come out under a shot or two get the merge warning. A beat at a point (Midpoint,
Low Point: one percentage, no width) gets a minimum of a shot or two.

No music-video structure: a short that follows a structure is an option the board has already.

**Re-fit to duration (explicit, and last).** Never automatic. A button that shows what it will do
("Inciting Incident +2, Rising Complications -3") and applies on confirmation. A beat's budget is
its percentage of the new duration, less the time in its built shots; stand-ins fill what's left.
Longer adds stand-ins at the end of the beat; shorter takes them from the end of each beat, never
the end of the episode (that would eat the climax). A beat already over its budget is left alone
and reported, so the episode can land over the target, and the preview says the real total.

**The animatic.** A picture dropped on a tile is that shot's first frame, and it stays on
`target: hold`: it renders for nothing, on this machine. A dropped frame also makes the shot
built, so a re-fit leaves it alone.

**Filling a shot is Edit Shot**, opened on the stand-in; it's a real shot, not a new one. Saving
doesn't take `target: hold` off, or a frame with its words added would become a shot waiting on a
model. The form says it's a stand-in and the model is chosen when the shot is ready. The guidance
text must not survive into a prompt unnoticed.

**Changed on seeing it (2026-11-08): guidance, not boxes to fill.** At 22 minutes the board was
190 empty boxes for Act II alone, which reads as homework. So a beat's shot count is a target
("0 of 93 shots, about 5:25"), not tiles. Tiles are the shots that exist; a `+` at the end of a beat
adds one, and **Fill with stand-ins** (a beat, an act, or all of it) makes the rest for whoever
wants the animatic. A change of duration then only moves the targets, which takes most of the
weight off Re-fit below. Where this and the sections above differ, this wins.

**The board reads and writes the script.** That one path is drafts, bringing in an existing
script, and generation. An unfinished script is a normal script:

- Tried on copies of `examples/starter`: a script with beats and empty `#` sequences, or with no
  sequences at all, passes `check` and `build` (0:00 runtime). Comments the build doesn't know pass
  too, and a `// beat:` with no shot under it is harmless (`read_marks` keeps only the last before
  a shot, so the score ignores an empty beat and the board reads its own way).
- What the board adds is comments: `// duration: 22:00` once near the top, `// act: <name>` above
  an act's first beat, only where the act isn't the structure's own. Added beats are plain
  `// beat:` lines; the score treats a name that isn't in the table as `other`.

**A place isn't a picture.** The format does need one: `# sq01` alone fails ("needs an id and a
location") and the id must be in the series config. But a location can be words with no picture,
as the New Episode Wizard already makes, so a text-to-video episode never has to choose one on the
board. A sequence with no place reuses the one before it; the first with none gets a location in
words made for it, rather than a refusal. To try: a location with an empty description.

To build, each ending in something that runs:

- [x] **Act data** (2026-11-08). An `Act` column in every structure's table in
      STORY_STRUCTURES.md, so each is 3 to 6 rows on the board (`tests/test_structure_outline.py`
      has the counts). Three-Act's acts, Episodic Drama's, Kishōtenketsu's and Freytag's are the
      structure's own, Hero's Journey's the traditional Departure, Initiation, Return; the rest
      are groupings of ours. The Fable and the Parable are a row a beat. In Medias Res's Build-Up
      became two beats, `The Calm / Build-Up` and `The Slide`, so it could be two rows (a script
      that says `Build-Up` still scores). `make_structures.py` carries each beat's `act`,
      `guidance` ("what happens") and `point` (a beat at one percentage; `layout` still ignores
      it) into `structures.json`. The Pixar Spine's optional "(And the moral is…)" is named without
      its brackets in the outline table, so the two don't match: it takes the last act from the
      beat before it, and has no guidance.
- [x] **The arithmetic** (2026-11-08). `core/blocking.py`, stdlib: structure + duration -> acts,
      beats, shot counts and seconds. A beat's share of the shots is its share of the story (at
      least one each, largest remainder); every shot is one length, so the beats add up to the
      duration. A beat at a point gets one shot under 5 minutes and two from there. A beat coming
      to under 1.5 shots is flagged to merge. Tests at 3, 7, 22 and 100 minutes
      (`tests/test_blocking.py`).
- [x] **The window, up to generation** (2026-11-08). `components/Storyboard.tsx`, on
      `FloatingWindow`, opened for now from the Shots tab: structure, duration, the live preview as
      act rows, beat bands, sequence boxes and tiles; a place and a cast per box, a beat split
      across places (`lib/storyboard.ts`: each sequence's `weight`, so a split survives a change of
      duration). Its plan lives in the window until generation. Act rows collapse; a feature's
      1,700 tiles still to be tried, and tiles drawn as they scroll in only if it needs them.
- [x] **The board as a document** (2026-11-08). `core/board.py`: a script as an ordered list of
      blocks (a beat line, a sequence, a shot), each holding its own lines exactly, and acts, beats
      and runs of a sequence as a view over them, so a script comes back byte for byte by
      construction. `tests/test_board.py`. Tried read-only on this machine's 163 real scripts:
      all came back exactly, the shots agreed with `story.parse_script` on the 151 it could parse
      (actions, durations, lines), and the beats with `read_marks` on the 23 that have them.
      Reading only so far: the edits (adding a shot, a beat, an act) come with the steps below.
- [x] **Targets and `+`** (2026-11-08). A beat shows its target against its real shots; tiles are
      shots, and a click opens Edit Shot; `+` at the end of a beat, and **Fill with stand-ins** for
      a beat, an act or all of it. A sequence box sets its place, and its cast on the empty
      stand-ins only. `GET /seriesmith/storyboard`, `POST /seriesmith/storyboard/edit`.
- [x] **Open an existing script** (2026-11-08). Every edit is written as the script editor's are
      (its hash, 409 when it changed underneath, history, a rebuild), so a draft is simply the
      script. A script with shots and no beats is offered `spotting.layout`'s guess; the Minutes
      field starts at the length it has.
- [ ] **Your own acts and beats.** A structure is where it starts, not a limit. In (2026-11-08):
      changing the structure (only the `// structure:` line: beats match what they match, the rest
      stay as the script has them), renaming a beat (double-click), the episode picker, and a
      right-click menu with the `+` kept: a shot after a shot, delete a shot, a new sequence in a
      chosen place (after a sequence's last shot: a sequence's id is in its shots' seeds, so one
      is never split or renamed here), add, rename and remove beats and acts of your own. Undo and
      redo: Ctrl+Z on the board, each step the whole script, for as long as the window is open.
- [x] **Generation** (2026-11-08). **Block from a structure**, a third start in the New Episode
      Wizard: where, series, cast and places as ever, then a structure and a length, and the
      episode opens on the storyboard with no shots. A location needs a `description` (the build
      refuses one without), so a series with no locations is asked where it opens, in words:
      nothing is invented, and guidance never lands in a location. Tried on a scratch episode:
      Fill to 51 stand-ins, `check` passes and the score draft runs on it (11 beats, 2 cues).
- [x] **Edit Shot on a stand-in** (decided 2026-11-08: nothing to build). A click on a tile opens the
      ordinary form, with the guidance as its action, where the person giving it a model reads it.
      A held shot with no picture can't render, so guidance only reaches a model by someone
      choosing one for that shot.
- [x] **Frames** (2026-11-08). A picture dropped on a tile is that held shot's first frame (a new
      take of `shot:<id>:first`, picked: `uploadRef`); a folder or a selection on a sequence or
      beat fills its empty stand-ins in filename order, and says how many were left over. A tile
      shows its picture until it's rendered. **Render held** renders every held shot with no
      up-to-date take, free, on this machine: the animatic, in the cut. A new stand-in's
      `first.png` is a small flat gray card (`board.gray_card`, known by its bytes, so it still counts
      as empty), which a dropped picture replaces: a blocked episode renders as it is, and a title
      card someone wrote by hand, with no picture, stays blocked. No line in the script.
      `jobs.plan_job` takes the card away from a shot on any other model, so it can't become a first
      frame nobody chose. A picture on a tile is its first frame whatever the shot's model. Undo covers the
      script, not pictures: an earlier picture stays a take of that keyframe.
- [x] **Re-fit to duration: dropped** (2026-11-08). Targets follow the duration on their own.
- [x] **Dragging shots** (2026-11-08). A tile drags to either side of another: the script's order,
      and the open pass's cut after it, as the timeline's own drops do. It takes on the sequence
      it lands in, and its seed with it. A picture on a tile's edge is a new held shot there (on
      its middle, that tile's picture). Undo puts the script back; the cut's move has the
      timeline's own undo.
- [x] **Convert held shots** (2026-11-08). Right-click a sequence, beat or act: its held shots'
      `target: hold` to a model or the series default, nothing else. Whoever sends a paid render owns
      having read its shots: no guard on guidance text left in place.
- [x] **Your own structures** (2026-11-08). `own_structures.py`, `structures.json` beside the
      settings file, for every show on this machine (the file is the way to pass them along). Save
      as structure takes the shares from the open episode's shots, to adjust, with acts and
      guidance. The storyboard's only: not in `spotting.structure`, so the score is unchanged.
- [x] **Docs** (2026-11-08). `docs/STORYBOARD.md`, the tutorial `docs/site/tutorials/storyboard.mdx`.
- [x] **Shots, not stand-ins; clicks** (2026-11-09). The board's words say shots ("no model yet"
      for one on `hold`), with Add shot before and after. A click selects a tile, a double-click
      plays its take or opens Edit Shot when it has none, Enter edits the selected tile. A take
      opened from the board floats above it (`ViewerState.floating`): the standalone page's docked
      viewer is behind the board.

## The guided film path (designed 2026-11-09; docs/DESIGN.md, section 10)

- [x] **One wizard, six steps** (2026-11-09). Idea, Story and Cast in `components/NewEpisodeWizard.tsx`
      (from Simple and Advanced), then the guide (`components/FilmPath.tsx`, **Guide…** in the Shots
      tab) for Cast's pictures, Storyboard, Film and Watch. The Start from row stays above the steps:
      an FCP7 edit has no Idea step to go through.
- [x] **Automatic plumbing, "More" sections.** Folder, ids, model, sizes, dialogue, speech pace.
- [x] **Resumes from disk.** The step comes from the script, the pictures and the takes (`lib/filmPath.ts`).
- [x] **Story's starts.** A structure (default), paste or a file, an agent over MCP, a single
      shot, FCP7 XML.
- [x] **Cast from the script.** Cards for the names a script uses that the series lacks, under the
      script's ids; pictures made in the guide.
- [x] **Film and Watch.** Film the shots with no take; Play all, Export.
- [x] **Sketches.** `POST /seriesmith/storyboard/sketch`, **Sketch** on the board: first frames on `hold`
      shots through the keyframe path; a shot whose action is still its beat's guidance is left out
      and named.
- [ ] **A logline.** The Idea step's one line was left out: nothing reads it yet.

## The Registry's flags (branch `registry-hardening`, 2026-11-10)

Every published version is flagged by the Comfy Registry's scanner (policy v0.7/v0.8:
arbitrary-file-read, too-many-findings; a few command-injection, credential-exfiltration,
code-execution), so none is active. Audited by kind; what was real is fixed, what was a pattern
match made to say what it does.

- [x] **The package.** `node_modules/` (vitest's cache, committed by accident) untracked; the skill's
      zip (a second copy of the build) left out by `.comfyignore`, linked from the docs and the
      editor instead; MRT2's unused AOTI code and Hugging Face fallbacks removed (NOTICE.md). 802 files
      to 569.
- [x] **Other web pages.** `server/guard.py`: the server answers its own page and programs; Origin,
      Sec-Fetch-Site, Host (DNS rebinding), JSON bodies only. The network launcher, a laptop on Wi-Fi
      or Tailscale included, unchanged; `--allow-host` for other names.
- [x] **Keys.** A provider's saved key to the hosts it was saved for; the Hugging Face token to its
      hosts by name, never on a redirect; the Comfy key to comfy.org, comfy.app or this machine; the
      queue relay without ComfyUI's extra_data; tools without the keys in their environment.
- [x] **Paths.** The whole disk from the PC running seriesmith, the project folders from any other
      device (browse, every `source_path`, an XML's media); project folders, `ffmpeg_dir` and
      `comfyui_dir` changed on that PC only, never a whole drive or the user's folder; the node
      pack's file inputs inside ComfyUI's folders.
- [x] **Running code.** Tools through `seriesmith/_run.py` (the package's modules only), no `python
      -c`, no `cmd /c`; helpers run only ffmpeg/ffprobe; a show's own model runs builtin code only.
- [x] **Found on the way.** MRT2's seed cap (2**32-1) refused every cue; MRT2 inside ComfyUI with
      dynamic VRAM hit torch 2.15's own Triton kernels (comfy-aimdo's allocator), now avoided.
- [x] **Live** (2026-11-10, the user): Router and local renders, a latent chain, Export, an MRT2
      cue, a Qwen clone, align, a sheet stitched; the editor from a laptop on Wi-Fi (new show, refs,
      a render, drag and drop, imports inside the project folders, nothing outside them), Settings
      saved from it; on the PC, localhost and 127.0.0.1, the whole disk.
- [ ] **Pinned hashes** for the Features downloads (the ffmpeg build, models, hub files).
- [ ] **Paths in a series config or script** (a ref, a recording, a theme): absolute ones still
      followed; confine them to the show and the project folders.
- [ ] **The next release** scanned clean, or a manual review asked for with this list.
- [x] **The skill on seriesmith.com** (seriesmith-site#11): Get the skill and How to use it on the home page.

## Continuity at the cut's out point (branch `continuity-trim`, 2026-11-10)

- [x] `continuous: first` and `latent` carried on from the previous take's file end, not where the
      cut ends it, so a trimmed shot made the next one jump. `edit.cut_bounds` (the dialogue window,
      then the trims, another rate by duration); `refs.join_frame` cuts a continuity keyframe at the
      out point (a `last` one at the in point); `chain_source` and SeriesmithChainLatent's `skip_end`
      hold the frames ending there, from the mp4. A moved trim shows the keyframe or the chained
      take stale. CONTINUOUS.md, "At the cut's out point".
- [x] **Live** (2026-11-10, the user): a latent chain re-rendered after a trim; `continuous: first`
      and an FL2VA last frame cut anew at the trims.

## Later

- The gallery's zips (2026-10-27): kept an hour from when they're made, swept only as the next
  zip is made, so a big one can sit in `downloads/` until then. Fine on one machine; for a
  hosted seriesmith (or a laptop on Tailscale over a slow link), sweep at start too and keep
  each until it's been fetched rather than by the clock. A zip being streamed is never cut
  short meanwhile (Windows refuses the delete; elsewhere the open file streams on).
- Publishing: PyPI for the app (the Manager listing is its own step, above).
- RTX Video Super Resolution (`rtx_vsr`, among the pixel models; 2026-10-14). Measured
  2026-10-15 on the RTX 5090, 2x of two 5 s takes (Porchlights ep02 sh2440, H3 1344x768;
  sh190, Seedance 1280x720), whole job: RealESRGAN_x2 128-159 s, VSR ULTRA 14 s warm
  (35 s cold), VSR HIGHBITRATE_ULTRA 14-17 s, SeedVR2 7B 433-515 s. Flicker added over the
  take's own (frames back at its size, mean abs diff of frame-to-frame change):
  VSR ULTRA 1.14-1.20, HIGHBITRATE 0.86-0.95, RealESRGAN 1.39-1.43, SeedVR2 1.87-1.88.
  By eye: SeedVR2 adds real detail; RealESRGAN sharper than VSR ULTRA, edging to
  oversharp; VSR ULTRA clean, skin smoothed; HIGHBITRATE close to lanczos.
  **A long take at 4K needed windows (2026-11-02).** Comfy-Org's node holds its whole output
  in float32 (100 MB a frame at 3840x2160) and our finish after it as much again in half
  floats. Measured on local ComfyUI (RTX 5090, 64 GB RAM, 96 GB commit), 1920x1080 -> 3840x2160
  through `seriesmith upscale --method pixel --pixel-model rtx_vsr`: 59 frames took ComfyUI
  from 5.9 to 23.3 GB private (8.1 GB on the card), 119 frames to 33.0 GB (available RAM down
  to 19 GB): ~160 MB a frame over a ~8 GB base, so the 28 s take (669 frames) wanted ~120 GB
  and wasn't run that way (it would have paged the machine, then failed); about 8 s was the
  most this machine could do. ComfyUI also keeps the last run's outputs until the next one.
  Now `SeriesmithRTXUpscale` (comfy_nodes/finish.py) runs the RTX node 32 frames at a time,
  fits and finishes each window as it goes and keeps the result 8-bit (`compact`, when it goes
  straight to the saver; half floats otherwise, as a post's or Wan's start). Run outside the
  live ComfyUI (its own Python, the RTX pack registered as ComfyUI does, read -> node ->
  encode): 120 frames 9.6 s, 9.1 GB peak for the whole process; the 669-frame take completed,
  669 frames at 3840x2160, 46.8 s upscaling (+66 s reading, 7 s NVENC), 35.7 GB peak
  (the source's float32 frames and the 8-bit result: ~50 MB a 1080p frame, so about 40 s
  of 1080p on 64 GB), 9.6 GB on the card. Against the old graph on the 120-frame clip:
  PSNR 50 dB between the two (rounding, through NVENC), no dip at the window joins (49.6-55
  dB throughout), the same 30.84 dB each against the source scaled down. Not yet run inside
  ComfyUI itself: it loads the node on its next restart.
