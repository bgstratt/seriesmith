# Contributing

Issues and pull requests are welcome.

- The core and the build (`seriesmith/core/`, `seriesmith/build.py`, the targets'
  compile code) need nothing outside the Python standard library, so a script can be
  checked anywhere (the script-writing skill bundles them). The rest may use the
  declared dependencies (comfy-sdk, aiohttp, Pillow, numpy). `ffmpeg` and `ffprobe`
  are the only external tools (assemble, master, publish, the waveform peaks and the
  audio work need them).
- `comfy_nodes/` runs inside ComfyUI, on whatever backend renders, so torch, numpy and
  PIL are fair game there. Nothing seriesmith sends a backend may read or write an
  episode folder: files go up as uploads and come back as reported outputs.
- Shot IDs, seeds and the shotlist schema are load-bearing: a change that re-seeds shots
  invalidates renders people may already have approved. Call that out in the PR.
- Run the tests before opening a PR: `python -m pytest` (six workers in parallel, with
  `pip install -e .[test]`; no test reaches a real backend). The golden outputs in `tests/golden/` must stay byte-identical unless the
  change means to alter them; then regenerate them with
  `python tests/test_golden.py --update`, review the diff and say why in the PR. If a
  change touches rendering, say what you rendered to verify it.
- The editor lives in `web/` (React/Vite) and is built twice: `npm run build:standalone`
  writes the page `seriesmith serve` serves (`seriesmith/server/static/`), `npm run build`
  the one inside ComfyUI (`comfy_nodes/web/seriesmith-editor.js`). Both are committed, so
  rebuild and commit them with the source; `npx vitest run` runs its tests.
- `prompts/` (with the skill's zip, `prompts/seriesmith-episode-script.zip`) is generated.
  Edit `docs/AUTHORING.md` (and `docs/SCRIPT_CONVERSION.md`) and run
  `python tools/make_prompts.py`; run it before a release too, since the zip bundles the
  build (the core and the targets).
- INSTALL.md's model list is generated too. If you change a target's `models`, `presets`
  or `downloads`, run `python tools/make_models_md.py` and commit the result;
  `tests/test_docs.py` fails when it is out of date (`--check` does the same without
  writing). It lists the shipped targets only, never the models you saved. Never add a
  download URL you cannot trace to a ComfyUI template, a saved workflow or ComfyUI-Manager's model list — leave `url` null and say so in `source`.
- The built-in Comfy Router models (`seriesmith/targets/{video,image}/` whose `code` is
  `builtin:router_video` / `builtin:router_image`) are generated too, from the schemas in
  `tests/fixtures/router_schemas/` and the limit corrections in
  `tools/make_router_targets.py`. Change those and run it; `tests/test_router_inspect.py`
  fails when they are out of date.
- The tests run on settings of their own (`tests/conftest.py`), so your machine's
  settings, API key and own models never reach them.
- `series.json` is the **series config**, never the bible.
