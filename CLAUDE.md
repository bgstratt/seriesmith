# seriesmith

Series config (`series.json`) + episode scripts (`epNN.md`) -> finished episodes,
any shot on any model, local ComfyUI or Comfy's cloud (Comfy API, Router, via the
Comfy SDK). Successor to h3pipe (`../h3pipe`), ported from it step by step.

The plan and the build order are in `docs/DESIGN.md`; keep it current when a
decision changes. h3pipe's `docs/AUTHORING.md` is still the script/series config
format.

## Layout

- `seriesmith/core/` — model-free: script parser -> story IR, series config, framing, speech pacing
- `seriesmith/targets/` — one folder per model (`target.json`, prompt writer, compile, workflow)
- `seriesmith/build.py` — script + series config -> story IR -> each target's shotlist, refs_todo
- `seriesmith/cli.py` — the `seriesmith` command (`build`, `check`, `backends`)
- `seriesmith/backends/` — where a job runs: local ComfyUI (via comfy-api-proxy), Cloud, deployments (`comfy.py`), Router (`router.py`), a fake for tests
- `seriesmith/settings.py` — this machine's settings (backend URLs, API key); never the series config
- `seriesmith/jobs.py`, `takes.py`, `render.py` — planning a take, its files and record, rendering through a backend (portable graphs)
- the rest of h3pipe, ported as is: `refs`, `edit`, `source`, `promote`, `issues`, `tour`, `track`, `align`, `upscale`, `master`, `post`, `assemble`, `publish`, `inspector`, `kreagen`, `mksheet`; `api.py` (the editor's routes as functions); `h3cli.py` (h3.py's commands, reached as `seriesmith <command>`)
- `seriesmith/helpers/` — PIL/numpy helpers run as subprocesses (sheets, tour stills, 360 canvas)
- `comfy_nodes/` — seriesmith's ComfyUI node pack (the portable shot loader and saver); link it into ComfyUI's custom_nodes

## Rules

- The core and build need nothing outside the standard library. The rest may
  use the declared dependencies (comfy-sdk, Pillow, numpy).
- Tests: `.venv\Scripts\python -m pytest` (the whole suite takes ~8 minutes;
  run the files you touched first).
- Never hand-edit generated files (`shotlist/`, `refs_todo.*`); change the script,
  the series config or the code and rebuild.
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
