# seriesmith

Series config (`series.json`) + episode scripts (`epNN.md`) -> finished episodes,
any shot on any model, local ComfyUI or Comfy's cloud (Comfy API, Router, via the
Comfy SDK). Successor to h3pipe (`../h3pipe`), ported from it step by step.

The design is `docs/DESIGN.md` and the work list `docs/PLAN.md`; keep them current
when a decision changes. `docs/AUTHORING.md` is the script/series config format (the
source of `prompts/` and the script-writing skill); `docs/API.md` the editor's HTTP
contract; `INSTALL.md`, `docs/SETUP.md`, `docs/EDITOR.md`, `docs/COMMANDS.md` the
user's side.

## Layout

- `seriesmith/core/` — model-free: script parser -> story IR, series config, framing, speech pacing
- `seriesmith/targets/` — one folder per model (`target.json`, prompt writer, compile, workflow); `generic/` the code data-only models use (`video_prose`, `router_video` / `router_image` for Comfy Router models, `workflow_image` for an image workflow of the user's); models for every show live beside the settings (`targets/`), a show's own in `<show>/targets/`
- `seriesmith/build.py` — script + series config -> story IR -> each target's shotlist, refs_todo
- `seriesmith/cli.py` — the `seriesmith` command (`build`, `check`, `render`, `backends`, `serve`, `stop`; the rest through `commands.py`)
- `seriesmith/backends/` — where a job runs: local ComfyUI (via comfy-api-proxy), Cloud, deployments (`comfy.py`), Router (`router.py`), a fake for tests
- `seriesmith/settings.py` — this machine's settings (backend URLs, API key, built-in drafts switched on, limit overrides); never the series config
- `seriesmith/limits.py` — a video or hosted image model's limits read into one form and written back where each lives; `router_inspect.py` — a Router model's schema read into a proposed target (video and image), its catalog
- `seriesmith/jobs.py`, `takes.py`, `render.py` — planning a take, its files and record, rendering through a backend (portable graphs)
- `seriesmith/queue.py`, `runner.py`, `finishing.py` — the server's job queue, what puts renders, refs, upscales and posts on it, and the upscale/post graphs made portable when their job starts
- the rest of h3pipe, ported as is: `refs`, `edit`, `source`, `promote`, `issues`, `tour`, `track`, `align`, `upscale`, `master`, `post`, `assemble`, `publish`, `inspector`, `kreagen`, `mksheet`; `api.py` (the editor's routes as functions); `commands.py` (the stage and editing commands, reached as `seriesmith <command>`); also `clips` (Simple mode's scratch series), `finish` (a hosted take's thumbnail and strip), `peaks`, `shotnodes` (what the pipeline knows of `comfy_nodes/shot.py`)
- `seriesmith/helpers/` — PIL/numpy helpers run as subprocesses (sheets, tour stills, 360 canvas)
- `comfy_nodes/` — seriesmith's ComfyUI node pack (the portable shot loader and saver, the chain nodes, the upscale loaders and saver, the upscale and post compute nodes); link it into ComfyUI's custom_nodes
- `seriesmith/server/` — `seriesmith serve` (`standalone.py`: the editor page, its API, the queue, comfy-api-proxy started, `POST /seriesmith/server/stop` for `seriesmith stop` and Settings' Stop / Restart, exit code 3 to restart), `views.py` (the API on aiohttp), `queue_views.py` (Jobs, backends, Settings: registered by both hosts), `comfyui.py` (the same app on a ComfyUI's own server, loaded by the node pack, its own journal `queue-comfyui.json`); `static/` is the built page
- `run_seriesmith.bat` / `run_seriesmith_ext.bat` — Windows launchers (this PC / the network, `--host 0.0.0.0`); they start the server again on exit code 3
- `web/` — the editor (React/Vite); `npm run build:standalone` writes `seriesmith/server/static/`, `npm run build` the ComfyUI page `comfy_nodes/web/seriesmith-editor.js`; commit both
- `docs/` — DESIGN, PLAN, SETUP, AUTHORING, SCRIPT_CONVERSION, EDITOR, COMMANDS, API, H3_TARGET, CONTINUOUS, POST_PROCESSING, RECORDED_DIALOGUE, KREAGEN; `docs/site/` the Mintlify docs site (docs.seriesmith.com; Mintlify's monorepo path): `docs.json`, `index.mdx` and the logos by hand, every other page generated from INSTALL.md and the user docs (never DESIGN or PLAN). The marketing site (seriesmith.com) is its own repo, `../seriesmith-site`
- `tools/` — `make_prompts.py` (prompts/ and the skill from AUTHORING.md), `make_models_md.py` (INSTALL.md's model list), `sync_starter_doc.py` (AUTHORING.md's first example is `examples/starter/`), `make_router_targets.py` (the Comfy Router video and image models in `seriesmith/targets/{video,image}/`, from the schemas in `tests/fixtures/router_schemas/`), `make_site_docs.py` (docs/site/'s pages from the user docs); `tests/test_docs.py`, `tests/test_new_episode.py` and `tests/test_router_inspect.py` check them

## Rules

- The core and build need nothing outside the standard library. The rest may
  use the declared dependencies (comfy-sdk, Pillow, numpy).
- Tests: `.venv\Scripts\python -m pytest` (the whole suite takes ~8 minutes;
  run the files you touched first). `tests/conftest.py` points every test at empty
  settings and unreachable backends; keep it that way. This machine's own models
  (`targets\` beside the settings file) must never reach a test or a generated file
  (`tools/make_models_md.py` reads the shipped targets only).
- Never hand-edit generated files (`shotlist/`, `refs_todo.*`, `prompts/`, INSTALL.md's
  model block, `seriesmith/server/static/`, `comfy_nodes/web/seriesmith-editor.js`, the
  Router models' target.json, docs/site/'s generated pages); change the script, the series config, the docs or the
  code and regenerate (`python tools/make_prompts.py`, `python tools/make_models_md.py`,
  `python tools/make_router_targets.py`, `python tools/make_site_docs.py`, `npm run build:standalone`
  and `npm run build`).
- Refactors keep the golden outputs byte-identical (`python -m pytest`) unless the
  change is intended and the goldens are updated in the same commit with the
  reason stated (`python tests/test_golden.py --update`, then review the diff).
  Real-episode fixtures live in the gitignored `tests/local/`; never commit them.
- Seeds come from episode/sequence/shot ids (`stable_seed`); don't change that
  derivation.
- When porting from h3pipe, the H3 name stays only on what really is MiniMax H3
  (e.g. `minimax_h3_ref2va`); everything generic gets a seriesmith name.
- Windows is the dev machine: use `os.path`/`pathlib`, not hardcoded `/`.
- Terminology: `series.json` is the **series config**, never the bible.
