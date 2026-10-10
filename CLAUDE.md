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
- `seriesmith/cli.py` — the `seriesmith` command (`build`, `check`)

## Rules

- The core and build need nothing outside the standard library. Backends may
  use `comfy-sdk` and other dependencies.
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
