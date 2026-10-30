# seriesmith

Series config (`series.json`) + episode scripts (`epNN.md`) -> finished episodes,
any shot on any model, local ComfyUI or Comfy's cloud (Comfy API, Router, via the
Comfy SDK). Successor to h3pipe (`../h3pipe`), ported from it step by step.

The design is `docs/DESIGN.md` and the work list `docs/PLAN.md`; keep them current
when a decision changes. `docs/REFACTOR.md` is the record of the 2026-10-20 refactor pass
(complete): why things are as they are, what was left alone, and the evidence; read the
item before redoing one. `docs/AUTHORING.md` is the script/series config format (the
source of `prompts/` and the script-writing skill); `docs/API.md` the editor's HTTP
contract; `docs/QUICKSTART.md` (getting started: ComfyUI-Manager, the page of its own, a linked clone), `docs/FULL_SETUP.md` (what each
feature needs), `INSTALL.md`, `docs/SETUP.md`, `docs/EDITOR.md`, `docs/COMMANDS.md` the
user's side.

## Layout

- `seriesmith/core/` — model-free: script parser -> story IR, series config, framing, speech pacing
- `seriesmith/targets/` — one folder per model (`target.json`, prompt writer, compile, workflow); `generic/` the code data-only models use (`video_prose`, `router_video` / `router_image` for Comfy Router models, `workflow_image` for an image workflow of the user's); models for every show live beside the settings (`targets/`), a show's own in `<show>/targets/`
- `seriesmith/build.py` — script + series config -> story IR -> each target's shotlist, refs_todo
- `seriesmith/commands.py` — the `seriesmith` command: every subcommand in one table (`COMMANDS`: usage, help, what runs it; stages in-process, align a subprocess; usage errors exit 2); `cli.py` is its entry point
- `seriesmith/backends/` — where a job runs: local ComfyUI straight to its own API (`native.py`; or via comfy-api-proxy with `local_via: "proxy"`), Cloud, deployments (`comfy.py`), Router (`router.py`), a fake for tests
- `seriesmith/settings.py` — this machine's settings (backend URLs, API key, built-in drafts switched on, limit overrides); never the series config
- `seriesmith/limits.py` — a video or hosted image model's limits read into one form and written back where each lives; `router_inspect.py` — a Router model's schema read into a proposed target (video and image), its catalog
- `seriesmith/jobs.py`, `takes.py`, `render.py` — planning a take, its files and record, rendering through a backend (portable graphs)
- `seriesmith/queue.py`, `runner.py`, `finishing.py` — the server's job queue, what puts renders, refs, upscales and posts on it, and the upscale/post graphs made portable when their job starts
- the rest of h3pipe, ported as is: `refs`, `edit`, `source`, `promote`, `issues`, `tour`, `track`, `align`, `upscale`, `master`, `post`, `assemble` (and `nle_xml`: its plan as an FCP7 XML timeline, `assemble --xml`), `publish`, `inspector`, `kreagen`, `mksheet`; `api.py` (the editor's routes as functions); also `clips` (Simple mode's scratch series), `finish` (a hosted take's thumbnail and strip), `relight` (a sequence's plates under another light, as relit locations), `peaks`, `shotnodes` (what the pipeline knows of `comfy_nodes/shot.py`), `takeimport` (a video from outside, or another shot's take, as a shot's take), `mcp` (`seriesmith mcp`: the API's routes as MCP tools on stdio, for an LLM client; stdlib only)
- `seriesmith/helpers/` — PIL/numpy helpers run as subprocesses (sheets, tour stills, 360 canvas, `ffprobe_av.py`: ffprobe through PyAV)
- `seriesmith/ff.py` — the ffmpeg / ffprobe commands, found once (PATH, imageio-ffmpeg, PyAV)
- `seriesmith/sdk.py` — comfy-sdk installed into the running Python when a Comfy API key is set (Cloud, deployments, Router need it; nothing else does)
- `seriesmith/presets/` — what the editor offers as pictures to pick from: relight presets for a ref's picture (`relight.json`) and series looks (`look.json`), their sample pictures in `img/` (made by `tools/make_preset_samples.py`; commit them)
- `seriesmith/features.py`, `installer.py`, `server/features_views.py` — the Features window: what can be added (each target's files from the target; only URLs the code records), whether it's there, and installing it (downloads into ComfyUI's models folders, node packs cloned into custom_nodes, pip, a full ffmpeg)
- `comfy_nodes/` — seriesmith's ComfyUI node pack (the portable shot loader and saver, the chain nodes, the upscale loaders and saver, the upscale and post compute nodes); link it into ComfyUI's custom_nodes
- `__init__.py`, `requirements.txt`, `.comfyignore`, pyproject's `[tool.comfy]` — the whole repo as that node pack, as the Comfy Registry / ComfyUI-Manager install it (`comfy node pack` zips the tracked files less `.comfyignore`); `requirements.txt` is what Manager pip-installs into ComfyUI's Python, so nothing optional goes there, and no shipped code installs a Python package or another node pack at runtime (the Registry's rules: the Features window says how instead)
- `seriesmith/server/` — `seriesmith serve` (`standalone.py`: the editor page, its API, the queue, the installed models found (`detect_models`), comfy-api-proxy started when renders go through it, `POST /seriesmith/server/stop` for `seriesmith stop` and Settings' Stop / Restart, exit code 3 to restart), `views.py` (the API on aiohttp), `queue_views.py` (Jobs, backends, Settings: registered by both hosts), `comfyui.py` (the same app on a ComfyUI's own server, loaded by the node pack from the repo it's linked from — nothing installed in ComfyUI's Python — its own journal `queue-comfyui.json`); `static/` is the built page
- `run_seriesmith.bat` / `run_seriesmith_ext.bat` / `run_seriesmith.sh` — launchers (this PC / the network, `--host 0.0.0.0`); they make the repo's `.venv` on first start and start the server again on exit code 3
- `web/` — the editor (React/Vite); `npm run build:standalone` writes `seriesmith/server/static/`, `npm run build` the ComfyUI page `comfy_nodes/web/seriesmith-editor.js`; commit both
- `docs/` — DESIGN, PLAN, REFACTOR (the refactor's record), QUICKSTART, FULL_SETUP, SETUP, AUTHORING, SCRIPT_CONVERSION, EDITOR, COMMANDS, API, H3_TARGET, CONTINUOUS, MULTISHOT (the design record of `continuous: multishot`), POST_PROCESSING, RECORDED_DIALOGUE, KREAGEN, ADDING_MODELS (adding a model: in the app, and in the code, with every file a new one touches); `docs/site/` the Mintlify docs site (docs.seriesmith.com; Mintlify's monorepo path): `docs.json`, `index.mdx`, `last-light.mdx` (LAST LIGHT, quoting `examples/demo/` verbatim), the logos, `images/` (pictures the docs show, e.g. the gallery's) and `tutorials/` (a page per video tutorial, the steps it shows) by hand, every other page generated from INSTALL.md and the user docs (never DESIGN or PLAN). The marketing site (seriesmith.com) is its own repo, `../seriesmith-site`
- `tools/` — `make_prompts.py` (prompts/ and the skill from AUTHORING.md), `make_models_md.py` (INSTALL.md's model list), `make_refs_md.py` (AUTHORING.md's table of what each model takes in pictures), `sync_starter_doc.py` (AUTHORING.md's first example is `examples/starter/`), `make_router_targets.py` (the Comfy Router video and image models in `seriesmith/targets/{video,image}/`, from the schemas in `tests/fixtures/router_schemas/`), `make_site_docs.py` (docs/site/'s pages from the user docs), `make_preset_samples.py` (the presets' sample pictures, rendered with seriesmith on a scratch episode); `tests/test_docs.py`, `tests/test_new_episode.py` and `tests/test_router_inspect.py` check them

## Rules

- The core and build need nothing outside the standard library. The rest may
  use the declared dependencies (comfy-sdk, aiohttp, Pillow, numpy, imageio-ffmpeg, PyAV).
- Run ffmpeg and ffprobe through `seriesmith/ff.py` (`FF.tool("ffmpeg")`, `FF.have`), never
  a bare `"ffmpeg"`: it finds imageio-ffmpeg's binary and PyAV's ffprobe stand-in when
  PATH has none (the node pack: `comfy_nodes/_ff.py`).
- Write files through `seriesmith/core/fileio.py` (`write_json`, `write_bytes`, `replace`,
  `read_json_or`, ...): atomic, LF, the Windows retry. Never a bare `open(path, "w")` for
  a file something else reads, nor a bare `os.replace`.
- Tests: `.venv\Scripts\python -m pytest` (six workers, pytest-xdist from the `test` extra,
  at below-normal priority; `-n 0` for one process, as for a file or two). Run the files you
  touched first. Never set the worker count from a conftest hook (xdist workers run
  `pytest_cmdline_main` too: it became a fork bomb that froze the PC), and never `-n auto`
  here (24 workers, each test starting ffmpegs). Unreachable backends are `127.0.0.1:0`, refused at once:
  a closed port such as 9 takes ~2 s to refuse on Windows, which made the serial suite 11
  minutes. `tests/conftest.py` points every test at empty
  settings and unreachable backends; keep it that way. This machine's own models
  (`targets\` beside the settings file) must never reach a test or a generated file
  (`tools/make_models_md.py` and `tools/make_refs_md.py` read the shipped targets only).
- Never hand-edit generated files (`shotlist/`, `refs_todo.*`, `prompts/`, INSTALL.md's
  model block, AUTHORING.md's pictures table, `seriesmith/server/static/`, `comfy_nodes/web/seriesmith-editor.js`, the
  Router models' target.json, docs/site/'s generated pages); change the script, the series config, the docs or the
  code and regenerate (`python tools/make_prompts.py`, `python tools/make_models_md.py`, `python tools/make_refs_md.py`,
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
