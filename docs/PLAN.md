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
      More. A new series' proxy is 864×480 (480p is the minimum that reads;
      896×512 offered for 1344×768's exact shape, and the form says when the shapes
      differ). Checked live on an imported Porchlights S2 episode: a proxy change
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
- [ ] **Live:** a clean ComfyUI (no clone, no link), installed from Manager: the nodes, the
      editor in the sidebar, a local render, a Router render.
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
      cancel); pick a take; assemble. The tools that queue say QUEUES in their descriptions
      and the server's instructions ask the model to confirm with the user first;
      `--read-only` leaves out everything that writes or queues. Checked live, read-only,
      against `seriesmith serve`.
- [x] **Resources:** the script format (`prompts/SKILL.md`, read from the repo), so a
      client without the skill still writes scripts that check.
- [x] Docs: COMMANDS ("An LLM driving seriesmith"), with Claude Code's and Desktop's config.
- [ ] Not yet: the upscale / post / master tools, the cut (order, trims), overrides; a take
      imported from a video file or another shot (with the gallery's drag onto the timeline,
      a design of its own); MCP prompts (a client's slash commands) if a flow proves worth one.

## Step 15 — models behind other APIs (after the Manager listing)

Router reaches most providers through one key; some are only (or more cheaply, or
sooner) behind their own API, a gateway (fal, Replicate, WaveSpeed, Runware), or a
self-hosted endpoint. The same data-driven model, a different transport:

- [ ] **An HTTP backend** (`backends/http.py`): a request built as `router_video` /
      `router_image` build theirs (the same `inputs` mapping), sent to the model's own
      endpoint; then the result found by data: synchronous (the answer is the result),
      or submit → poll → result (the job id's path in the answer, the status URL, which
      values mean done or failed, where the files are). Reattached after a restart by its
      job id, as Router's are; a lane per provider with its own parallel limit.
- [ ] **Keys per provider** in this machine's settings (never the series config),
      environment variables over them; Settings lists them, write-only like the Comfy key.
- [ ] **Pictures:** inline (base64 / data URI) where the API takes it, else a link it can
      fetch (the Comfy asset store while there's a Comfy key; a provider's own upload
      route where it has one).
- [ ] **Asset libraries** (Seedance and its resellers; 2026-10-21): the fourth way in, beside
      inline, a link and an upload route. Register a fetchable URL, poll until it's Active,
      send `asset://<id>`. Router does this already (`via="seedance"`,
      `RouterBackend.seedance_asset`, Comfy's `/proxy/seedance/virtual-library`) because
      BytePlus refuses a photoreal face as a plain URL; a face sent as base64 is untested.
      Atlas Cloud exposes the same BytePlus library differently: assets on
      `console.atlascloud.ai/api/v1/sd/assets` (register `{type, url}`, poll
      `/sd/assets/<id>` for `Active` / `Failed` with `error_code`), generation on
      `api.atlascloud.ai`, a public URL only (no base64; its `model/uploadMedia` gives one
      without a Comfy key). Video and audio must be registered there; images may go inline.
      So a preset describes the step as data (upload route, register route, status field and
      its done/failed values, the reference's form), as the `via` on a file does today.
      Registration validates up front (Atlas: images 300-6000 px, aspect 0.4-2.5, < 30 MB;
      video mp4/mov 2-15 s, 24-60 fps, 409,600-927,408 px; audio wav/mp3 2-15 s): its
      refusal is the take's error, said plainly.
- [ ] **Keep registered asset ids**, by (provider account, file sha256): an id means nothing to
      another provider. Skips the ~4-5 s per picture each Router Seedance take spends
      uploading and registering again (step 14).
- Router's Seedance 2.5 schema takes an image or audio as URL, base64 or asset id; a video as
  URL or asset id only. Atlas's guide notes the asset step is the required way in for
  video and audio references; expect each reseller of a model to differ in exactly this.
- [ ] **Gateway presets** for the common shapes, so a model is a pick, not a mapping:
      fal's queue API, Replicate's predictions, OpenAI-style images, Google's Gemini /
      Vertex, then direct providers as needed (Runway, Kling, BFL).
- [ ] **The wizard:** a model's OpenAPI document (a URL, or pasted) read by the same
      proposer as Router's, else a mapping started from the closest preset; dry run and
      probe as for Router models.
- [ ] Costs where the API reports them (often it does, in its own units, as Router's
      providers do).

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
  oversharp; VSR ULTRA clean, skin smoothed; HIGHBITRATE close to lanczos. Still open:
  whether its full-size float output needs chunking for a long 4K take.
