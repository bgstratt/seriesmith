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
- `seriesmith/targets/` — one folder per model (`target.json`, prompt writer, compile, workflow)
- `seriesmith/build.py` — script + series config -> story IR -> each target's shotlist, refs_todo
- `seriesmith/cli.py` — the `seriesmith` command (`build`, `check`, `render`, `backends`, `serve`; the rest through `commands.py`)
- `seriesmith/backends/` — where a job runs: local ComfyUI (via comfy-api-proxy), Cloud, deployments (`comfy.py`), Router (`router.py`), a fake for tests
- `seriesmith/settings.py` — this machine's settings (backend URLs, API key); never the series config
- `seriesmith/jobs.py`, `takes.py`, `render.py` — planning a take, its files and record, rendering through a backend (portable graphs)
- `seriesmith/queue.py`, `runner.py`, `finishing.py` — the server's job queue, what puts renders, refs, upscales and posts on it, and the upscale/post graphs made portable when their job starts
- the rest of h3pipe, ported as is: `refs`, `edit`, `source`, `promote`, `issues`, `tour`, `track`, `align`, `upscale`, `master`, `post`, `assemble`, `publish`, `inspector`, `kreagen`, `mksheet`; `api.py` (the editor's routes as functions); `commands.py` (the stage and editing commands, reached as `seriesmith <command>`)
- `seriesmith/helpers/` — PIL/numpy helpers run as subprocesses (sheets, tour stills, 360 canvas)
- `comfy_nodes/` — seriesmith's ComfyUI node pack (the portable shot loader and saver, the chain nodes, the upscale loaders and saver, the upscale and post compute nodes); link it into ComfyUI's custom_nodes
- `seriesmith/server/` — `seriesmith serve` (`standalone.py`: the editor page, its API, the queue, comfy-api-proxy started), `views.py` (the API on aiohttp), `comfyui.py` (the same API on a ComfyUI's own server); `static/` is the built page
- `web/` — the editor (React/Vite); `npm run build:standalone` writes `seriesmith/server/static/`
- `docs/` — DESIGN, PLAN, SETUP, AUTHORING, SCRIPT_CONVERSION, EDITOR, COMMANDS, API, H3_TARGET, CONTINUOUS, POST_PROCESSING, RECORDED_DIALOGUE, KREAGEN
- `tools/` — `make_prompts.py` (prompts/ and the skill from AUTHORING.md), `make_models_md.py` (INSTALL.md's model list), `sync_starter_doc.py` (AUTHORING.md's first example is `examples/starter/`); `tests/test_docs.py` and `tests/test_new_episode.py` check them

## Rules

- The core and build need nothing outside the standard library. The rest may
  use the declared dependencies (comfy-sdk, Pillow, numpy).
- Tests: `.venv\Scripts\python -m pytest` (the whole suite takes ~8 minutes;
  run the files you touched first).
- Never hand-edit generated files (`shotlist/`, `refs_todo.*`, `prompts/`, INSTALL.md's
  model block, `seriesmith/server/static/`); change the script, the series config, the
  docs or the code and regenerate (`python tools/make_prompts.py`,
  `python tools/make_models_md.py`, `npm run build:standalone`).
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
