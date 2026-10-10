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
- Run the tests before opening a PR: `python -m pytest` (no test reaches a real
  backend). The golden outputs in `tests/golden/` must stay byte-identical unless the
  change means to alter them; then regenerate them with
  `python tests/test_golden.py --update`, review the diff and say why in the PR. If a
  change touches rendering, say what you rendered to verify it.
- The editor lives in `web/` (React/Vite): `npm run build:standalone` there writes the
  committed page in `seriesmith/server/static/`, so commit both; `npx vitest run` runs
  its tests.
- `prompts/` and the skill in `build/skill/` are generated. Edit `docs/AUTHORING.md` (and
  `docs/SCRIPT_CONVERSION.md`) and run `python tools/make_prompts.py`.
- INSTALL.md's model list is generated too. If you change a target's `models`, `presets`
  or `downloads`, run `python tools/make_models_md.py` and commit the result;
  `tests/test_docs.py` fails when it is out of date (`--check` does the same without
  writing). Never add a download URL you cannot trace to a ComfyUI template, a saved
  workflow or ComfyUI-Manager's model list — leave `url` null and say so in `source`.
- `series.json` is the **series config**, never the bible.
