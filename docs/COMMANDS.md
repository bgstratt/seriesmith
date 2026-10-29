# The command line

Every stage as a command, the files each one reads and writes, and how to work an
episode from a terminal. The editor ([EDITOR.md](EDITOR.md)) does the same through its own
server; both write the same files. `seriesmith` with no arguments lists every command, and
`seriesmith <command> --help` gives each one's usage and flags. A command asked for wrongly
(no episode, an unknown flag) exits 2 with its usage line, as argparse does; one that ran and
failed exits 1.

## Every command

| Command | What it does |
|---|---|
| `seriesmith new <show>\<name>` | A new episode (`series.json` + script) that builds, from the newest episode beside it, else `examples/starter/` (`--title`, `--series-id`) |
| `seriesmith build <episode>` | The script and series config compiled into the shotlists and `refs_todo` (final and proxy) |
| `seriesmith check <episode>` | `build --check` and `--pace`: errors, warnings, crammed lines; writes nothing |
| `seriesmith refs <episode>` | Reference pictures (and with `--voices`, voice samples): kreagen |
| `seriesmith supply <episode> <file-or-folder>…` | Pictures you already have put into their ref slots (`--ref id[:view]`, `--no-pick`, `--dry-run`) |
| `seriesmith render <episode>…` | Each shot as a take, on its backend |
| `seriesmith takes` / `pick` / `override` / `keyframe` / `discard` / `cut` | Takes, the cut and per-shot tweaks (below) |
| `seriesmith promote <episode>` | Overrides moved into the script or the series config |
| `seriesmith issues <episode>` | The pass's notepad (`--add <shot> <note>`, `--export`, `--clear`, `--resolve <id>`) |
| `seriesmith align <episode> <recording>` | The script timed against a dialogue recording |
| `seriesmith assemble <episode>` | The review cut |
| `seriesmith upscale` / `post` / `master` / `publish` | Finishing (below) |
| `seriesmith all <episode>` | build → refs → render → assemble (`--skip-build` keeps the shotlists on disk) |
| `seriesmith targets [<episode>]` | Which models the running ComfyUI can render, what to download for the rest |
| `seriesmith target-from-workflow <workflow> [<episode>]` | A ComfyUI workflow proposed as a model (`--save` writes it into the show; `--save --every-show` for every show) |
| `seriesmith backends` | Where jobs can run on this machine, and whether each answers (`--try local`) |
| `seriesmith serve` / `stop` | The editor's server (below) |
| `seriesmith mcp` | That server's API as an MCP server, for an LLM client (Claude Code or Desktop, Cursor, …) to make and drive episodes with (below) |

`build`, `check`, `refs`, `assemble` and `all` take several episode folders at once, or a
parent with `--each`; `render` and `master` take several folders.

## The modules

| Module | What it does | Reads | Writes |
|---|---|---|---|
| `seriesmith` (`cli.py`, `commands.py`) | One command for every step | an episode folder | — |
| `seriesmith build` | Parses the script into the story IR, picks each shot's target and compiles it: prompts, frame counts, seeds, reference slots, audio settings. Checks pacing | `series.json`, `epNN.md` | `shotlist/shots.json`, `shotlist.json`, `shotlist.<target>.json`, `_proxy` twins, `refs_todo.md/.json` |
| `seriesmith/kreagen.py` (`seriesmith refs`) | Generates every missing reference image through the image target, on its backend, and saves it where the series config names | `refs_todo.json`, `series.json` | `refs/…` (takes in `refs/_takes/`) |
| `seriesmith/mksheet.py` | Joins four character views into one 4096×1024 sheet (kreagen calls it) | 4 images | `refs/<char>/<char>_sheet_4panel.png` |
| `seriesmith/render.py` | Renders each shot through its target on its backend, one take at a time, skips finished shots | `shotlist*.json`, `overrides.json`, the workflows | `renders/` or `renders_proxy/` |
| `seriesmith/edit.py` | `takes`, `pick`, `override`, `keyframe`, `discard`, `cut`, `targets` (through `seriesmith`) | the episode | `cut.json`, `overrides.json`, `refs/shots/` |
| `seriesmith/promote.py` | Moves an override into the script or the series config where it belongs, and rebuilds | `overrides.json`, `epNN.md`, `series.json` | updated script and series config, `_history/` |
| `seriesmith/align.py` | Times the script against a dialogue recording and writes the `audio:` windows | recording, `epNN.md`, `series.json` | updated script and series config, `align_report.md` |
| `seriesmith/upscale.py` | Upscales takes 2x (either pass): re-sampled from late in the take's schedule under its frozen shotlist (H3, LTX-2, Wan), through a pixel upscale model (`--method pixel`) or SeedVR2 (`--method seedvr2`); the audio held and copied on | a take, its frozen shotlist and latent | `<stem>.up.mp4`, `<stem>.up.json` beside the take |
| `seriesmith/post.py` | The post pass on a take's upscale: enhance (draft / production / cinematic), then motion blur | a take's `.up.mp4` | `<stem>.post.mp4`, `<stem>.post.json` beside the take |
| `seriesmith/master.py` | The series' `upscale.master` recipe on every shot of the cut (and `post.master` with `--post`), then the master assembled and titled | the episode, its cut | `<episode>/master/` |
| `seriesmith/publish.py` | The review cut between the series intro and outro, with the episode title | a cut, `_titles/` | `<episode>/publish/` |
| `seriesmith/issues.py` | The pass's review notepad, each note snapshotting the shot's script lines and compiled prompt | the episode | `<episode>/_issues.json` |
| `seriesmith/inspector.py` (`seriesmith target-from-workflow`) | Proposes a `target.json` from a ComfyUI workflow, video or image, ending in any save node | a workflow, ComfyUI's `/object_info` | `<show>/targets/<id>/target.json` |
| `seriesmith/assemble.py` | Joins the rendered shots in cut order (`cut.json`, else script order), trimming timed shots to their windows and using each clip's chosen audio | `shotlist*.json`, `cut.json`, renders | `renders/epNN.mp4`, `epNN_shots.txt` |

`seriesmith/core/` (parser, story IR, series config, speech pacing), `jobs.py`,
`takes.py`, `refs.py`, `source.py` (the authored files), `track.py` (recordings and
alignment) and `peaks.py` (waveforms) are the library the commands and the editor's routes
share. `backends/` (local, cloud, deployments, Router), `queue.py` and `runner.py` (the
job queue, and what puts renders, refs, upscales, posts and tours on it), `finishing.py`
(the upscale and post graphs made portable) and `server/` (the editor's server) are how
work gets done; `comfy_nodes/` is what runs inside ComfyUI. `settings.py` is this
machine's settings, `limits.py` a model's limits, and `router_inspect.py` reads a Comfy
Router model's schema (the editor's Models window; no command of its own).

### What you write

- **`series.json`** — the series config: style, characters and props (with a `design`
  sentence each), locations (one entry per camera angle, with the light), voices, audio
  mode, and optionally the series target, render profiles, the `refs` image targets and a
  `negative` prompt. A character who changes clothes gets a second entry with `of:` — a
  **wardrobe variant**, its own `design` and its own sheet, everything else inherited. See
  `examples/series_example.json`.
- **`epNN.md`** — the script: `# sq` sequences, `## sh` shots with `who:`, `with:`, `size:`,
  `dur:` or `audio:`, `plate:`, `camera:`, `sound:`, `music:`, optionally `target:`,
  `first:` / `last:`, action prose and `NAME:` lines. See `examples/script_example.md`.
- **`negative.txt`** (optional, beside the script): the episode's negative prompt, for the
  targets that take one.

**[AUTHORING.md](AUTHORING.md) is the full format**: every field, choosing a
target, keyframes, the frame grids, the syllable budget, the camera vocabulary, how to
break a scene into shots, giving two people in one scene an angle each, and the
reference-slot rules. Read it once before writing an episode.

Only three things are actually required of a script: the `= ep01 Title` header, at least one
`# sq01 <location>` naming a location the series config defines, and per `## shNNN` a unique
id, action or dialogue, and a length (`dur:` seconds / `auto` / `model`, or an `audio:`
window). Everything else has a default — a speaker joins the cast from their own `NAME:`
line, `size:` is medium, `plate:` is the sequence's location, and the camera holds still.
The series config must have a `series` block, `style.look`, `subjects` (each with `name`,
and `design` unless they are only ever a voice), and `locations` with a `description` and a
`plate` each. `--check` names whichever is missing.

Drafting with an AI assistant: the guide comes as a skill, `seriesmith-episode-script`.
`prompts/seriesmith-episode-script.zip` is the whole skill (the guide, a worked screenplay
conversion from `docs/SCRIPT_CONVERSION.md`, and a copy of `build` to validate with): upload it
in Claude (Settings → Skills → Upload a skill), or unzip it into `.claude/skills/` for Claude
Code. `python tools/make_prompts.py` rebuilds it. `prompts/SKILL.md` is the skill's
text alone, and `prompts/seriesmith-script.instructions.md` the same guide for Cursor, Copilot or
any system prompt. Edit the docs, not the copies. Whatever writes the script, `--check`
and `--pace` are what say it is correct.

Change the series config or script and run `build` again rather than editing the generated
files: `steps:`, `model:`, `lora:`, `profile:` and `target:` are script fields, so
experiments survive a rebuild, and `overrides.json` holds the editor's tweaks. If you do
hand-edit a shotlist, `all --skip-build` and the individual stages leave it alone.

### build

```
seriesmith build Shows\ep05           # final + proxy
seriesmith check Shows\ep05           # --check and --pace, writes nothing
```

- Snaps every shot to its target's legal lengths (H3: 17k+5 frames at 24fps, so 2.33, 3.04,
  3.75, 4.46, 5.17s…; LTX: 8k+1; Wan: 4k+1).
- `dur: auto` sizes a shot from its dialogue. `--pace` flags lines crammed into too short a shot.
- Seeds come from the episode, sequence and shot IDs, so untouched shots render identically after edits.
- `refs_todo.md` lists every image and voice sample still missing, with the prompt to make it.
- Writes `defaults.steps`, `defaults.model` and `defaults.lora` into each shotlist, and warns
  when a shot overrides them or when the step count does not match the LoRA.

#### Steps, model and LoRA

Each pass has its own sampling setup, and the render stage applies it per shot, in memory —
the workflow file on disk is never rewritten. The table is H3 Ref2VA's; every target has
its own presets in its `target.json`, and a series written for H3 doesn't hand another
target H3's model, LoRA or steps.

| | final | proxy |
|---|---|---|
| steps | 8 | 4 |
| turbo LoRA | `minimax_h3_ref2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors` | `minimax_h3_ref2v_lightx2v_turbo_4step_v0.1_resized_avg_rank_20_bf16.safetensors` |
| model | `minimax_h3_ref2va_pruned_int8_convrot.safetensors` | same |

A distilled LoRA is trained on a fixed set of timesteps, so it does its best work at its own
step count: the 8-step v1.0 was distilled at 768p for 8 steps, and the proxy keeps the 4-step
v0.1 both for speed and because its 544p training is closer to the animatic's 512×288.

Override per pass in the series config (`series` for the final, `proxy` for the animatic):

```json
"series": { "steps": 8, "model": "minimax_h3_ref2va_pruned_bf16.safetensors" },
"proxy":  { "steps": 4, "lora": "…4step_v0.1….safetensors" }
```

Override one shot — or one sequence, by putting the line under the `#` header — in the script:

```
## sh170
model: minimax_h3_ref2va_pruned_bf16.safetensors
lora: none
steps: 30
```

`lora: none` (or `off`) sets the LoRA strength to 0 instead of swapping files, which renders
that shot on the base model — the honest comparison for what the turbo LoRA costs you.
A shot's line beats its sequence's, which beats the pass default. `--check` lists every
override so an experiment left in a script cannot surprise you later.

Names must match ComfyUI's dropdowns exactly, subfolder prefix included. A wrong name fails
the first shot instead of quietly rendering with something else. ComfyUI reloads whenever the
model or LoRA changes, so group experiments rather than scattering them through an episode.

### kreagen

```
seriesmith refs Shows\ep05 --list        # what would run
seriesmith refs Shows\ep05 --only dean   # one asset first
seriesmith refs Shows\ep05               # everything missing, most-needed first
seriesmith refs Shows\ep05 --voices      # also the voice samples, on the audio target
```

- Each take is a job on this command's own queue: `--backend` picks where (`local`, `cloud`,
  `deployment:<target>`; default each image target's own, so a hosted one goes to Router).
  `--target` picks the image model, a hosted one included.
- Skips anything already on disk. `--redo` makes a new take (kept in `refs/_takes/`) and
  leaves the live file alone unless you add `--pick`; combine it with `--only`. `--all`
  works from the whole series config instead of `refs_todo.json`.
- `--only` matches part of the file path, so `dean` also matches `dean_grown` — which is
  also how a character and their wardrobe variants regenerate together.
- **Wardrobe variants come second.** A variant's views are edited from the character's own
  (see **Reference sheets**), and a whole pass plans every job before any take is picked —
  so in the first pass the variant has nothing to edit from and is drawn cold. Run the pass,
  let the character's views pick (anything with no live file takes its first usable
  candidate automatically), then regenerate just the variant on a model that reads
  references: `--only gina_towel --target flux2_klein_edit --redo`. Set that target once on
  the ref instead — in the editor's per-ref target picker — and every later generate of it
  uses the edit model while everything else stays on krea2. The new take does **not** go
  live on its own once the variant already has a file: pick it (`--pick`, or in the Refs
  tab).
- **Voices.** Images only, unless `--voices`: then each character's voice ref is generated
  on the audio target (`--voice-target`, `--voice-seconds`; default `ltx2_voice`) into
  `refs/voices/<char>.wav`, as takes like any other ref. `--from-take sh020:2:1.5-6.0`
  needs no model at all — it cuts those seconds out of a rendered take's sound into a
  voice candidate.
- `--discard subject:ada:02_side:2` moves a candidate to `refs/_takes/_trash/` (nothing is
  deleted; if it was the pick, the ref is cleared).
- `--edit location:kitchen --instruction "night, the lights off"` changes a picture the ref
  already has on an edit model, into new candidates (`--with` brings in another ref's
  picture, `--count`, `--seed`, `--as-typed`).
- Each character is made as four square views sharing a seed, then joined by mksheet.
  Every view is a take in `refs/_takes/subject__<char>/`, so one angle can be redone and
  re-picked in the editor's Refs tab (seriesmith/refs.py).
- Negative prompts do nothing on krea2 turbo: no negative field, and no guidance branch at
  cfg 1. kreagen leaves a workflow's negative side as saved, so a NAG or negpip setup passes
  through; `--negative-file` only bites above `--cfg 1.0`, on a model that expects guidance.
  H3 takes no negative prompt at all. Details in [KREAGEN.md](KREAGEN.md). The other image targets
  take the episode's `negative.txt` or the series config's `negative` (inert at cfg 1 too);
  `--negative-file` beats both for its run.
- `--target z_image_turbo` (or any image target) draws with another model; `--clear
  location:kitchen` unpicks a ref (its file goes, the takes stay).
- No style LoRA by default. `--lora <file> --lora-strength 0.7` adds one, `--unet` swaps the
  image model. Match the LoRA to the look in `series.json`: a realism LoRA helps live action
  and hurts a flat 2D show.
- **With krea2, drives your own ComfyUI workflow when it finds one.** Save a text-to-image graph as
  `krea2_refs_t2i.json` among ComfyUI's workflows (or set `$KREA_WORKFLOW`, or pass `--workflow`), and
  kreagen sets the prompt, size, seed, steps and cfg on it per image instead of using its
  built-in graph. That is the no-Python way to change the model, LoRA, sampler or scheduler
  for reference art. `--no-workflow` forces the built-in graph.

  The graph needs one KSampler, one EmptyLatentImage and one SaveImage; positive and negative
  are found by following the sampler's own links. At cfg 1.0 the negative encoder is replaced
  with `ConditioningZeroOut`, since guidance is off and encoding it would be wasted; above 1.0
  with `--negative-file`, a graph wired straight to `ConditioningZeroOut` gets a text encoder
  put back. `seriesmith/targets/image/krea2/workflow.json` is a working example with no LoRA — point its
  loaders at your own models. `--lora` splices a LoRA node into a graph that has none, or
  sets the one that is already there. If a graph carries a step-distilled LoRA, pass the
  matching `--steps`.

### render

```
seriesmith render Shows\ep05 --list                  # what would run, where, and why not
seriesmith render Shows\ep05 --proxy                 # animatic, to renders_proxy\
seriesmith render Shows\ep05 --only sh040,sh050 --redo
seriesmith render Shows\ep05 Shows\ep06 --proxy      # several episodes
seriesmith render Shows\ep05 --only sh040 --backend cloud
seriesmith render Shows\ep05 --only sh040 --target seedance_2_5            # a hosted model, on Router
seriesmith render Shows\ep05 --only sh040 --target seedance_2_5 --dry-run  # the request, nothing sent
```

- Runs each shot through its target on its backend (`--backend`, else the shot's, the
  episode's, the series config's `series.backend`, else the target's own; see
  [SETUP.md](SETUP.md); `seriesmith backends` lists them). A workflow target's graph goes as
  a job, with the shot and its reference pictures as uploads; the files that come back are
  written into the take. A hosted target (Seedance, Kling, Veo, hosted H3, …) is one Router
  call, and its takes are marked `reproducible: false`. Each take is a job on this command's own
  queue, run one at a time and waited for; a `continuous: latent` shot holds the take
  rendered just before it.
- It runs anywhere the episode folder is: the backend never reads it. It checks the render
  folders to skip finished shots, so Ctrl-C (which cancels the running job) and re-running
  resumes where it stopped.
- Every take gets a sidecar, `<shot>_tNN.json`, holding its seed, model, LoRAs, steps, the refs
  it used (with checksums) and its status (`queued`, `ok`, `failed`). It also gets
  `<shot>_tNN.shotlist.json`, the exact shot it rendered. Nothing about a take is lost when the
  script changes.
- `--redo` renders a new take (t02, t03…) and never overwrites. `--take N` overwrites that take.
- **Seeds:** a shot's first take uses its built seed. `--redo` picks a **new** seed, so a redo
  is really a new attempt. `--same-seed` keeps the built one, `--seed N` uses N, and
  `--new-seed` forces a fresh one.
- Takes the model, LoRA and step count from each shot, falling back to the shotlist defaults,
  then applies the episode's `overrides.json` (see `seriesmith override` below). `--model`, `--lora`
  and `--steps` override all of that for one run. `--lora` repeats to stack LoRAs
  (`--lora a.safetensors --lora b.safetensors:0.6`); the extras are chained after the
  workflow's LoRA loader. `--note` stores a remark in each take's sidecar.
  It prints what it will use, and warns when one episode needs more than one model or LoRA.
- **Targets.** Each shot renders with its own target: H3 shots through the shot loader
  (the shot as JSON, its pictures as uploads), `ltx2` shots with every value patched into
  the LTX-2.5 graph, a hosted target as a model call. `--target ltx2`
  renders the chosen shots on another target for this run (their story is compiled for it
  on the spot, no rebuild); `seriesmith override <ep> <shot> --target ltx2` does it for every
  run. An LTX shot's keyframes (`refs/shots/<shot>/first.png`, `last.png`) go up with its
  job. `--dry-run` writes what the first shot would send (`render_graph.json`, or
  `render_call.json` for a hosted model) and runs nothing.
- Failed shots are reported and skipped; `--stop-on-error` halts instead. A shot whose
  reference images are still missing is **blocked**, and the report names the exact files;
  `--allow-missing-refs` renders it against flat grey stand-ins.
- Other flags: `--panel-mode`, `--save-frames`, `--latent` / `--no-latent`, `--size WxH`,
  `--allow-model-mismatch`.
- Each target's workflow comes from the running ComfyUI's saved workflows (the name in its
  `target.json` binding: `H3_Ref2VA_Shotlist_v1.json` for H3, `krea2_refs_t2i.json` for
  reference images), so it always matches your ComfyUI's node versions; failing that,
  `$COMFYUI_PATH`'s workflows folder, then the copy in this repo. The target's own env var
  (`$SERIESMITH_MINIMAX_H3_REF2VA_WORKFLOW`, `$KREA_WORKFLOW`, …) beats all of those (kreagen
  also takes `--workflow`). Every target's name and variable is in
  [INSTALL.md](../INSTALL.md#3-workflows); `seriesmith targets --install-workflow <target>`
  copies a target's graph into ComfyUI to edit on the canvas. Keep the saved
  `krea2_refs_t2i.json` free of style LoRAs (experiment under another name), since the
  references must follow the series config's look.
- It converts the canvas workflow to API format itself. If ComfyUI rejects it, save
  **Workflow → Export (API)** and point the target's env var at that file.

### assemble

```
seriesmith assemble Shows\ep05 --proxy --check   # report only
seriesmith assemble Shows\ep05 --partial         # join what exists so far
```

- Follows the episode's `cut.json` if there is one (a list per pass of
  `{"shot", "take", "pass", "trim_in", "trim_out", "audio"}` entries). The list sets the order and,
  with `take: N`, the exact take. Without `cut.json`, or for a shot the list leaves out,
  a shot goes in script order and uses its latest usable take: status `ok` and the mp4 is
  there, so a `--redo` still queued or failed is skipped. Takes from before sidecars count
  as ok.
- A picked take that is queued, failed or has no mp4 makes the shot missing, and the report
  says why. `--take N` forces take N for every shot and beats `cut.json`.
- Entries for shots deleted from the script are skipped with a note. An entry with
  `"pass": "proxy"` in the final list is a placeholder: the proxy take is scaled to the final
  size. `trim_in`/`trim_out` drop frames from the head and tail.
- The pass comes from the shotlist's name (`_proxy` means proxy); `--pass` overrides it.
- `--check` lists the resolved cut (order, take, pass, trims, placeholders, orphans) and
  writes nothing. `--name` sets the output filename, `--shotlist` picks the proxy files,
  `--subfolder` reads this pass's takes from another folder.
- Mute clips (dub, clone) get their `_h3.wav` added so the join works.
  `--audio auto|mp4|h3|none|master` chooses the sound for the clips that have none of
  their own. A clip **can** have its own: `cut.json`'s `audio` lays another take's sound,
  a file's, or silence under it, cut or padded to the clip so the length never changes
  (the Timeline's **Replace audio…**, or `seriesmith cut --audio`). `--audio master` and `none`
  override those; the others leave them alone.
- Shots with an `audio:` window are trimmed to it (re-encoded, x264 CRF 16) so the cut lines up
  with the recording. `--no-trim` keeps the padding.
- A clip's colour in `cut.json` (`color`: exposure, contrast, black point, saturation,
  warmth, tint; the editor's sliders) is applied as it's re-encoded. `--no-color` leaves every clip as shot.
- `epNN_shots.txt` lists every shot's start time in the cut.
- `--upscaled` (either pass) plays each clip's fresh upscale (`seriesmith upscale`) and writes
  `epNN_up.mp4` at the upscales' size beside the plain cut; a clip without one is scaled up
  and named in the report. `--size WxH` sets the cut's size (`1920x1080` for a 1920×1088
  upscale), letterboxing a clip whose aspect differs.
- This is a review cut. Mix the final audio in Resolve.

### Takes, picks and overrides

```
seriesmith takes    Shows\ep05 --proxy          # every take: status, seed, why stale, which is in the cut
seriesmith pick     Shows\ep05 sh020 1          # the cut uses take 1 of sh020 (writes cut.json)
seriesmith pick     Shows\ep05 sh020 latest     # back to the newest usable take
seriesmith override Shows\ep05 sh020 --dump-prompt > sh020.txt     # the prompt it would use
seriesmith override Shows\ep05 sh020 --prompt-file sh020.txt --seed 1234
seriesmith override Shows\ep05 sh020 --lora a.safetensors --lora b.safetensors:0.6 --steps 10
seriesmith override Shows\ep05 sh020 --clear prompt
seriesmith render   Shows\ep05 --only sh020 --redo                 # renders with the override
seriesmith discard  Shows\ep05 sh020 2          # take 2 goes to renders\_trash\sh020\
```

- `takes` marks a take **stale** when rendering the shot now would differ: `script` (the
  shot changed in the script or series config), `ref` (a reference image or voice changed) or
  `preset` (model, LoRA, steps or size defaults changed). Stale is a hint, not an error.
- `overrides.json` is how you tweak one shot without touching the script: the exact prompt,
  a seed, model, LoRAs, steps. Prompt, model, LoRAs and steps are per pass (final unless
  `--proxy`; `--both` sets both), because the proxy's prompt differs when it generates its
  audio. The seed applies to both passes. A rebuild never loses an override. If the shot has
  changed since you wrote it, `takes` and `override` flag it STALE, and it is still applied.
- Model, LoRAs and steps belong in the script when they're decisions about the film.
  `overrides.json` is for the tweak loop. When a tweak turns out to be a decision,
  `seriesmith promote` moves it into the script or the series config for you — it prints the
  plan and the diffs first, and `--all` (or `--item shot:sh020:steps`) writes them, drops
  those overrides and rebuilds. The old files are kept in `<episode>\_history\`.

### Editing the cut

```
seriesmith cut Shows\ep05 --proxy --show                     # the cut: order, takes, trims, audio
seriesmith cut Shows\ep05 --proxy --move sh050 --before sh020
seriesmith cut Shows\ep05 --proxy --trim sh020 4 0           # drop 4 frames off the head
seriesmith cut Shows\ep05 --proxy --lock sh020               # reordering leaves it alone
seriesmith cut Shows\ep05 --out sh040                         # leave it out (still in the script)
seriesmith cut Shows\ep05 --copy-from proxy order            # take the proxy's order into the final
seriesmith cut Shows\ep05 --proxy --audio sh020 take sh030:2 # sh020's picture, sh030 take 2's sound
seriesmith cut Shows\ep05 --proxy --audio sh020 file audio\line_b.wav --at 0.4 --gain 1.2
```

`cut.json` holds it all — order, the take each shot uses, trims, locks and per-clip audio —
per pass, and `assemble` follows it. The editor's Timeline writes the same file.

### Finishing: upscale, post, master, publish

```
seriesmith upscale Shows\ep05 --check                  # the final cut's takes at 2x: the plan
seriesmith upscale Shows\ep05 --only sh020 --method pixel
seriesmith post    Shows\ep05 --enhance production --blur 0.25
seriesmith master  Shows\ep05 --check                  # the series' recipe on the cut: the plan
seriesmith master  Shows\ep05 --post --prores          # upscales, posts, the master, a ProRes copy
seriesmith publish Shows\ep05                          # intro + review cut + outro, titled
```

- `upscale` refines each take of the pass's cut that has no fresh upscale into
  `<stem>.up.mp4` beside it: `--method latent` (re-sampled late in the take's own schedule;
  the default where the target has one), `pixel` (an upscale model; `--pixel-model rtx_vsr` for
  NVIDIA RTX Video Super Resolution) or `seedvr2`.
  `--start-step`, `--scale`, `--vae`, `--deliver WxH`, `--quality review|master`, `--redo`.
- `post` finishes an upscale into `<stem>.post.mp4`: `--enhance draft|production|cinematic`
  (or `pixel|seedvr2|supir|none`), `--blur`, `--grain`; with neither, the series config's
  `post.master` recipe ([POST_PROCESSING.md](POST_PROCESSING.md)).
- `master` runs the series config's `upscale.master` recipe (and `post.master` with
  `--post`) on every shot of the cut, waits for them, then assembles and titles the master
  into `<episode>/master/`. `--conform`, `--allow-gaps`, `--order cut|target`,
  `--prores` / `--prores-only`.
- `publish` puts the show's `_titles/INTRO.mp4` and `OUTRO.mp4` around a cut (`--input`,
  default the review cut) with the episode title, into `<episode>/publish/`.
- `upscale`, `post` and `master` queue on a backend like a render (`--backend`, default
  `local`); `publish` is ffmpeg on this machine.

### Models

```
seriesmith targets                                   # what the running ComfyUI can render, what's missing
seriesmith targets Shows\ep05 --kind video --json
seriesmith targets --install-workflow ltx2           # its graph into ComfyUI to edit (--revert-workflow undoes it)
seriesmith target-from-workflow my_wan.json Shows\ep05            # the proposal and its notes
seriesmith target-from-workflow my_wan.json Shows\ep05 --save --id my_wan
seriesmith target-from-workflow my_wan.json --save --every-show --id my_wan   # for every show
```

- `target-from-workflow` reads a saved workflow (a name among ComfyUI's, or a `.json`
  path) against the running ComfyUI's `/object_info`, and proposes a video or image model:
  which widget takes the prompt, size, length, seed, steps and each model file, and which
  output node saves the take. `--save` writes it into `<show>/targets/<id>/target.json`;
  `--save --every-show` into `targets/<id>/` beside the settings, for every show.
- A Comfy Router model, limits, and switching on a built-in draft are done in the editor's
  Models window ([EDITOR.md](EDITOR.md), "The Models window").

### Backends and the editor's server

```
seriesmith backends                    # each configured backend, and whether it answers
seriesmith backends --try local        # a picture up to ComfyUI, inverted, and back
seriesmith serve                       # the editor on http://127.0.0.1:8190/
seriesmith serve --host 0.0.0.0 --root D:\Shows    # open to your network; a folder of shows
seriesmith stop                        # stop that server cleanly (--restart: start it again)
```

- `backends` reads this machine's settings and `COMFY_API_KEY` ([SETUP.md](SETUP.md)):
  `local` always, `cloud` and `router` with a key, a `deployment:<target>` per deployment.
- `serve` finds the default models installed in ComfyUI once it answers (docs/SETUP.md,
  "The default models"), starts comfy-api-proxy if local renders go through it
  (`local_via: "proxy"`), and picks up the jobs the last run left. `--port` (default 8190), `--host`, `--root` (repeatable), `--auto-launch` (open the
  editor in the browser once it is listening, as the .bat launchers do).
- `stop` asks the server on this machine to stop (`--port`); `--restart` restarts it when
  it runs under `run_seriesmith.bat` / `run_seriesmith_ext.bat` (a bare `seriesmith serve`
  just stops). Jobs still running on a backend are picked up on the next start.

### An LLM driving seriesmith: `seriesmith mcp`

```
seriesmith mcp                         # MCP on stdio, to the server on http://127.0.0.1:8190
seriesmith mcp --url http://127.0.0.1:8188    # to ComfyUI's, when the editor runs inside it
seriesmith mcp --read-only             # nothing that writes a file or queues a job
python <seriesmith>\seriesmith\mcp.py ...   # the same, with any Python 3.10+ (nothing installed)
```

With it, an LLM you already use (Claude Code or Desktop, Cursor, any client that speaks MCP)
can work on your episodes: check a series config and script it wrote, make the episode,
build it, generate or import and pick the pictures, render, look at the takes, pick them,
trim and reorder the cut, import a video or copy a take in, override a shot's settings (and
promote them into the script), assemble, and finish the final pass (upscale, post, master).
Every step goes through the same routes the editor uses, so an open editor shows it as it
happens. The model is the client's; seriesmith needs no key for it. Tools that queue jobs on
the GPU or spend Comfy credits say so, and the server asks the model to confirm with you
first. The script format is a resource (`seriesmith://script-format`), for a client without
the script-writing skill.

**Nothing to switch on, nothing left running.** seriesmith never starts it. Your LLM client
starts `seriesmith mcp` when it needs it and stops it when it closes; it listens on no port
(it talks to the client over stdin and stdout, and to the editor's server like the page
does). The editor's server has to be running: `seriesmith serve`, or ComfyUI with
seriesmith. Until it is, every tool answers that nothing answers there.

**Adding it to your client.** The editor writes it out for your install: **Settings › This
computer › Use from an LLM (MCP)** has the command line, the JSON block and the bare command,
each with Copy, and a read-only switch. By hand: each client needs the command that starts
it, written with full paths (a client doesn't start it in the seriesmith folder):

- **Installed with the launchers or `pip install -e .`** (a `.venv` in the seriesmith folder):
  `C:\path\to\seriesmith\.venv\Scripts\seriesmith.exe mcp` (Linux, macOS:
  `/path/to/seriesmith/.venv/bin/seriesmith mcp`).
- **Installed by ComfyUI-Manager** (no `.venv`): ComfyUI's own Python, or any Python 3.10+,
  running the file, pointed at ComfyUI: `C:\ComfyUI\python_embeded\python.exe
  C:\ComfyUI\ComfyUI\custom_nodes\seriesmith\seriesmith\mcp.py --url http://127.0.0.1:8188`.

A client's command line takes its name, then `--`, then that command (Claude Code, Codex and
GitHub Copilot CLI alike; Claude Code's `--scope user` adds it for every project):

```
claude mcp add --scope user seriesmith -- C:\path\to\seriesmith\.venv\Scripts\seriesmith.exe mcp
codex mcp add seriesmith -- C:\path\to\seriesmith\.venv\Scripts\seriesmith.exe mcp
copilot mcp add seriesmith -- C:\path\to\seriesmith\.venv\Scripts\seriesmith.exe mcp
```

`claude mcp list` shows it, and `/mcp` in a session shows its tools.

Claude Desktop: **Settings → Developer → Edit Config** opens `claude_desktop_config.json`
(`%APPDATA%\Claude\` on Windows, `~/Library/Application Support/Claude/` on macOS). Add the
server, save, and restart Claude Desktop:

```json
{
  "mcpServers": {
    "seriesmith": {
      "command": "C:\\path\\to\\seriesmith\\.venv\\Scripts\\seriesmith.exe",
      "args": ["mcp"]
    }
  }
}
```

For a ComfyUI-Manager install, `command` is the Python and `args` are the file and its
options: `"args": ["C:\\ComfyUI\\ComfyUI\\custom_nodes\\seriesmith\\seriesmith\\mcp.py",
"--url", "http://127.0.0.1:8188"]`.

Cursor, Gemini CLI, Windsurf and most other clients take the same `mcpServers` block (Cursor:
`~/.cursor/mcp.json`; Gemini CLI: `~/.gemini/settings.json`). VS Code (Copilot) keeps its own
in `.vscode/mcp.json` under `servers`, each with `"type": "stdio"`. Add `"--read-only"` to the args for a model that should
only look. `--url` can also come from `SERIESMITH_URL`.

## Recorded dialogue (lip sync)

Full guide: [RECORDED_DIALOGUE.md](RECORDED_DIALOGUE.md).

```
pip install faster-whisper numpy                    # once; the model downloads on first run
seriesmith align    Shows\ep05 audio\ep05_dialogue.wav --dry-run
seriesmith align    Shows\ep05 audio\ep05_dialogue.wav
seriesmith build    Shows\ep05
seriesmith render   Shows\ep05 --proxy
seriesmith assemble Shows\ep05 --proxy --audio master          # picture over the recording
```

- The editor does the same from its **Recording** window: attach the file (browse the
  ComfyUI machine, type a path, or drop it in), then align, with progress and the report.
  It runs align in whichever Python has `faster-whisper` and `numpy` — see
  [INSTALL.md](../INSTALL.md#1-requirements) if it picks the wrong one.
- align transcribes the recording with word timings, matches it to the script, and cuts it
  into one continuous run of windows with cuts at the quietest point of each pause.
- It writes `audio: in-out` on every shot, points the series config at the recording, keeps the
  old copy of each in `<episode>\_history\` (the editor's history), and writes `align_report.md`.
- Speaking shots then default to `dub_keep_foley`: H3 lip-syncs to your line and keeps its own
  sound effects as `_foley.wav`.
- The `retention` setting controls how much of your line H3 copies:

| `retention` | What H3 does with the line | Default for |
|---|---|---|
| `fully_copy` | Your clip is the shot's whole soundtrack; no sound effects added | `dub` |
| `partially_copy` | Copies the line exactly and adds ambience and action sounds | `dub_keep_foley` |
| `reference` | Borrows voice and timing only; loose lip sync | — |

Set it per shot (`retention: fully_copy`) or for the episode (`"audio": {"retention": ...}` in
the series config). `clone` and `generate` shots don't use it.

## Project layout

```
<episode>/
  series.json                  series config (you write)
  epNN.md                      script (you write)
  negative.txt                 negative prompt for targets that take one (optional)
  shotlist/shots.json          generated: the story IR (model-free)
  shotlist/shotlist.json       generated: the series target's shots
  shotlist/shotlist.<target>.json   generated: shots on another target
  shotlist/*_proxy.json        generated: the same for the proxy pass
  refs_todo.md / .json         generated work order
  overrides.json               editor / `seriesmith override`: per-shot tweaks, retargets, episode target,
                               where a shot or the episode renders (`backend`)
  cut.json                     editor / `seriesmith cut` / `pick`: per pass, the order, the take
                               each shot uses, trims, locks and each clip's audio source
  align_report.md              generated: what align matched (seriesmith align)
  _history/                    old copies of the script, series config and cut.json,
                               kept by the editor, promote and align
  _cache/peaks/                generated: cached waveforms for the timeline
  refs/<char>/<char>_sheet_4panel.png   horizontal 4-panel strip
  refs/props/<name>.png                 single clean object image
  refs/_bg/<location>.png               background plate -> <Picture 4>
  refs/voices/<char>.wav                a generated voice sample (audio target)
  refs/_takes/<ref>/…_tNN.png/.json     every ref candidate (refs)
  refs/_takes/_trash/<ref>/             discarded ref candidates
  refs/_picks.json, _overrides.json     which take is live; ref prompt/seed/target tweaks
  refs/shots/<shot>/first.png, last.png a shot's keyframes
  audio/voices/<char>_sample.wav        clone mode
  audio/<episode>_dialogue.wav          recorded dialogue (align)
  renders/<shot_id>/
    <shot_id>_t01.mp4
    <shot_id>_t01_h3.wav
    <shot_id>_t01_foley.wav      (dub_keep_foley only)
    <shot_id>_t01.jpg            mid-frame thumbnail (480 px long side)
    <shot_id>_t01_strip.jpg      8 frames side by side, for hover scrub
    <shot_id>_t01.json           take record: written queued, closed when its job's files come back
    <shot_id>_t01.shotlist.json  the exact shot that was rendered
    frames/<shot_id>_t01_%06d.png
  renders/_trash/<shot_id>/      discarded takes (`seriesmith discard`; nothing is deleted)
  renders_proxy/...            same layout for the animatic
```

---

