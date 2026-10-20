# seriesmith — refactor pass

A pass over the whole codebase (started 2026-10-20): fix what the survey found broken,
make the slow paths fast, combine duplicated code, and standardize the architecture.
Behaviour stays the same unless an item says otherwise. Tick items off as they land;
when an item teaches us something, change the plan here.

The survey's findings, with file:line evidence, are summarized under each item. Numbers
were measured on the dev machine against real shows, the running `seriesmith serve`
(8190) and ComfyUI (8188).

## Ground rules

- **Never paid.** Every live test runs on the local ComfyUI only. Before the pass
  starts, set **Settings → paid limit = 0**: the queue then refuses every Cloud,
  Router and deployment run (`queue.charge` → PaidLimit), so a slip can't bill.
  Put it back when the pass ends. Never pick Cloud, Router or a deployment in
  *Render on*.
- **A scratch show for anything that writes.** Live tests that render, assemble,
  upscale, post or pick go to a copy: `ComfyProjects/Ballroom-refactor` (a copy of
  Ballroom ep01, ep02 and refs; it's under a root, so the editor lists it). Your
  shows are read but never written by a test. FRTEST and Porchlights are read-only
  benchmarks.
- **One item per commit.** Each item's commit holds its code, its tests, and (if its
  output changes on purpose) its golden update, with the reason stated. The DESIGN,
  PLAN and user docs change in the same commit when the item changes something they
  describe.
- **Every item passes three gates before the next one starts:**
  1. **Automated:** the test files the item touches first, then the whole suite
     (`.venv\Scripts\python -m pytest`, about 12 min; must stay 1503 passed or more).
     Golden outputs stay byte-identical unless the item says otherwise.
  2. **Measured** (speed items): `tools/bench.py` before and after, numbers recorded
     in the item.
  3. **Live:** the item's *Live check*, done in the editor (restart the server
     first: Settings → Restart) or at the command line. Items marked **(you)** need
     your eyes, because they change something you see or hear; we stop there until
     you've looked. The others I run and report.
- **Branches.** Phase 1 goes on one branch (`refactor-fixes-speed`), one commit per
  item, and is merged as one PR once every live check passes. Phases 2 and 3 get a
  branch and PR per item, so each can be reviewed and reverted alone.
- **Rebuild the page** (`npm run build:standalone` and `npm run build`) only in
  items that touch `web/`; commit both outputs.

## Baseline (2026-10-20, before any change)

| What | Time | Size |
|---|---|---|
| `GET /refs`, Porchlights ep01 (324 shots) | 6.1 s first, 3.3 s after | 1.4 MB |
| `GET /refs`, FRTEST (229 shots) | 1.8 s / 0.6 s | 0.8 MB |
| `GET /episode`, FRTEST | 5.3 s (cold disk) / 0.57 s | 0.46 MB |
| `GET /episode`, Porchlights ep01 | 0.38 s / 0.25 s | 0.26 MB |
| `GET /promote`, Porchlights ep01 | 0.67 s / 0.61 s | |
| `GET /upscale/options` | 1.1 s | |
| `GET /post/options` | 1.5 s | |
| `GET /episodes` | 0.27 s | |
| ComfyUI `/object_info` (what the two above fetch) | 1.1 s | 4.2 MB |
| `GET /targets?ready=1` with ComfyUI down | ~96 s (test_readiness) | |
| `seriesmith assemble`, Ballroom ep01 copy (5 shots, 249 frames) | 3.9 s: 2.6 s ffmpeg (17 runs), 1.25 s ffprobe (34 runs) | |
| `seriesmith build`, examples/demo / starter | 0.56 s / 0.44 s | |
| Server import | 0.5 s (aiohttp; nothing to win) | |
| Test suite | 735 s; `test_readiness::test_route` 96 s, `test_resilience::…numbers` 49 s | |

On Windows a connect to `localhost` from Python costs ~2 s (it tries `::1` first) and a
connect to a closed local port ~2 s; benchmarks use `127.0.0.1`.

---

## Phase 0 — measuring

### 0.1 `tools/bench.py` ✅
The benchmark used for the baseline, kept so every speed item is measured the same
way: times each read route on `127.0.0.1:8190` twice (first, then repeat) per
episode, with sizes; `--ep` limits it to named shows; `--profile ROUTE EP` runs a
handler in-process under cProfile. Also `--assemble EP`: counts and times the
ffmpeg/ffprobe runs of an assemble of a scratch copy. Not a test; nothing imports it.
- **Live check:** run it; the numbers match the baseline within noise. Done: Porchlights
  ep01 `/refs` 2.3 / 2.4 s, FRTEST `/episode` 0.60 / 0.50 s, upscale/post options 0.96 /
  0.93 s; assemble of Ballroom-refactor ep01 3.8 s, 34 ffprobe runs, and its output is
  byte-identical run to run (sha1 358a3dcb…), so 1.10 can compare by hash.

---

## Phase 1 — fixes and speed (branch `refactor-fixes-speed`)

### Fixes

#### 1.1 H3 FL2VA accepts `dur: model` ✅
`targets/video/minimax_h3_fl2va/compile.py:84` `_duration` has no `model` branch, so a
`dur: model` shot on fl2va fails with "needs `audio:`…" although AUTHORING.md says
every non-LTX target renders at the estimate (ref2va, ltx2, ingredients and prose do).
**Change:** use the shared `model_duration` estimate and `put_model_duration`, as ltx2
does, with the "renders at the estimate" warning.
- **Tests:** a new fl2va case beside the ref2va one; goldens unchanged (no golden uses
  `dur: model` on fl2va; if one does, its update is intended and stated).
- **Live check:** in Ballroom-refactor, set one shot to `target: minimax_h3_fl2va` with
  `dur: model`; Build; `seriesmith check` shows the estimate warning; the shot's
  length in the editor is the estimate. No render needed.
- **Done:** reproduced ("needs `audio:`…"), fixed with ltx2's `model_duration` /
  `put_model_duration` (as prose and ingredients use; 3.1 moves them to the shared base).
  Live: sh020 as fl2va `dur: model 2-4` built at 4.00 s / 107 frames, check warned "H3
  FL2V can't predict", the editor showed it; the script restored after.

#### 1.2 Saving Settings refreshes every field ✅
`server/queue_views.py:102` copies a hand-written field list into the live settings
after a save, missing `enabled_drafts` and `target_limits`; the reply, Settings and
`/info` show the old values until a restart. **Change:** copy `settings.FIELDS` (plus
`path`) so a new field can't be missed again.
- **Tests:** a settings PUT test asserting every field in FIELDS round-trips.
- **Live check (you):** the Models window (Model: → Add / validate models…), Hosted models
  to try: **Enable** a draft; Settings shows it among `enabled_drafts` without a restart;
  **Back to draft**. (Not Probe: that's a paid Router run.)
- **Done:** test failed first (`[] != ['some_draft']`), passes now. Live through the API on
  the restarted server: `seedance_2_0_fast` enabled showed at once in the reply and
  `/info`; reverted.

#### 1.3 `commands.py` stops adding the package folder to `sys.path` ✅
`commands.main` inserts `seriesmith/` itself on `sys.path` in 11 branches, after which
`import queue` is `seriesmith/queue.py`, not the standard library's, and modules load
twice under two names. **Change:** delete the inserts; fix any import that relied on
them (expected: none; the modules are imported as `seriesmith.x`).
- **Tests:** a test that runs a command and asserts `sys.modules["queue"]` is the
  standard library's; the suite.
- **Live check:** each command's `--help`, then `seriesmith takes`, `seriesmith cut`
  and `seriesmith issues` on Ballroom-refactor; output as before.
- **Done:** confirmed real: before the fix `import queue` after a command was
  `seriesmith/queue.py`. No module relied on the inserts. Live: every command's `--help`
  exits as before (most say usage with exit 1: 3.6's business), and `takes`, `cut --show`,
  `issues --export`, `promote` on Ballroom-refactor print byte-identical output.

#### 1.4 The align transcript cache is written safely ✅
`align.py:498-510` reads the cache with unclosed `open()`s and writes it in place, so
an interrupted align leaves half a JSON file that the next run trusts. **Change:**
`takes.write_json` (temp file + replace), `with` blocks, and a damaged cache is
transcribed again instead of crashing.
- **Tests:** a broken `.words.json` is ignored and rewritten.
- **Live check:** none needed beyond the test unless you use align on a show; if you
  do, **(you)** run Align on a recorded-dialogue episode copy and compare the shots
  it times with before.
- **Done:** `align.cached_words` (whole, a list, at least as new as the recording, else
  None) and `takes.write_json` for the cache. Live on a copy of ArchTest (the one show
  with a cached transcript): `align --dry-run` output identical before/after; with the
  cache cut short, before crashed with a JSONDecodeError traceback, after goes to
  transcribe again (here: "no Whisper installed", the venv has none).

#### 1.5 Queue actions run off the event loop ✅
`server/queue_views.py`: cancel, move, pause and the Settings save run on the event
loop; cancel makes a network call to ComfyUI or the cloud there, so every open editor
freezes until it returns. **Change:** run them in the executor (as every `api.py`
route already is).
- **Tests:** existing queue tests; one asserting a slow cancel doesn't block a
  concurrent `GET /jobs`.
- **Live check (you):** queue two short local renders in Ballroom-refactor; cancel the
  running one; the editor stays responsive, the take says canceled, the second starts.
- **Done:** cancel/move/pause/retry and the Settings save run in the executor; the new
  backends are made before the old are swapped out. The test (a 1.5 s cancel) held the
  whole server 1.50 s before, not at all after. (A ValueError past the save itself now
  answers 400, not 500.)

#### 1.5b A cancel asked while a job is staging isn't lost ✅
Found by 1.5's live check: cancelled the instant it started, a local render ran its full
59 s and succeeded. A cancel that arrives while the work is still staging (uploads, before
its run exists) sets `cancel_asked` with nothing to call, and the five places the runner
then gave the run's cancel (`qjob.cancel_run = run.cancel`) never looked back. **Change:**
`Queue.arm_cancel(job, fn)` gives it under the queue's lock and calls it at once if a
cancel (or the time limit) was asked; `Queue.cancel` reads `cancel_run` under the same
lock, so exactly one of them stops the run.
- **Done:** a queue test for both orders (cancel before / after the run starts; stopped
  once either way). Live: cancelled at 0.0 s into a local render: the job ended
  canceled in 1 s, "the job was canceled in ComfyUI", take sh010 t02 failed/canceled,
  ComfyUI's queue empty. A cancel 15 s in (sh050) stops it too, as before.

### Speed

#### 1.6 One `object_info` fetch per ComfyUI per 30 s ✅
17 call sites fetch ComfyUI's full node list (4.2 MB, 1.1 s) on every call, uncached,
and the Context (and so the client) is new per request. **Change:** a shared cache in
`jobs.Comfy.object_info`, keyed by base URL, with the readiness cache's TTL
(`READY_TTL`, 30 s), cleared wherever `_READY` is (an install, a Settings change,
Features' refresh) and on a failed fetch (a down ComfyUI isn't remembered). Graph
lowering for a submit (`render.py:399,438`) keeps asking fresh, since a node pack
installed mid-session must be seen.
- **Target:** Upscale and Post dialogs ≤ 0.1 s once warm (from 1.1 / 1.5 s).
- **Tests:** a second call within the TTL doesn't fetch; `clear` forces a fetch.
- **Live check (you):** open Upscale and Post on a take: both open at once and show
  the same models and readiness as before. Install-state change: in Features, a
  missing item still shows missing then present after Refresh.

#### 1.7 Target workflows: stop after ComfyUI doesn't answer ✅
`edit.target_graphs` asks ComfyUI's userdata for each target's workflow, one request
per target (46), even after `list_userdata` showed ComfyUI isn't answering: ~96 s
with ComfyUI down, 46 sequential requests with it up. **Change:** fetch only the
workflows `list_userdata` listed; none if it failed (the repo's copies are used, as
today).
- **Target:** `test_readiness::test_route` from 96 s to under 1 s; `/targets?ready=1`
  with ComfyUI down from ~96 s to ~2 s.
- **Tests:** a fake ComfyUI counting requests.
- **Live check:** stop ComfyUI briefly (or point a scratch setting at a dead port),
  open the targets list: answers in seconds, marks targets unchecked as before. With
  ComfyUI back, a workflow saved in ComfyUI's user folder still wins over the repo's.
- **Done:** the listing already existed to save the per-target requests, but any failure
  fell back to asking per target; now a connection failure (OSError) means none is asked,
  any other keeps the fallback. Old code: 47 requests with ComfyUI away (the test lists
  them), now 1. Live, all 47 targets: ComfyUI up 0.37 → 0.33 s, identical answer (the 3
  workflows saved in ComfyUI still win); a dead port 98.4 → 2.35 s, identical answer.
  `test_readiness::test_route` 96 → 2.3 s.

#### 1.8 The Refs tab: each file read once per request ✅ (target half met)
`GET /refs` on Porchlights ep01 makes 3,200 JSON reads: the shotlist is parsed 378
times (1.1 s), `episode_shots` and `cut_entries` rebuilt 56 times, `built_shot_ids` 43,
`keyframe_refs` computed twice, takes listed again by the sweep, auto-pick and listing.
**Change:** a stat-keyed parse cache for the shotlist and cut (key `(path, mtime_ns,
size)`, with takes.file_sha1's racy-write guard), handing out read-only data (an audit
of callers that mutate what `load_shotlist` returns comes first; any that do take a
copy); `keyframe_refs` once per listing.
- **Target:** Porchlights ep01 `/refs` under 1 s warm (from 3.3 s); FRTEST under 0.3 s.
- **Tests:** a shotlist rewritten within the same mtime tick is read again; a caller
  can't change the cached copy; `tests/test_caches.py` extended.
- **Live check (you):** Refs tab on Porchlights ep01 and Ballroom-refactor: same refs,
  states and pictures as before (compare against a saved `/refs` reply from before the
  change: identical JSON). Then in Ballroom-refactor: generate one ref locally, pick a
  take, Build; the tab updates each time without a reload.
- **Done:** `takes.read_json_kept` (parsed once while size and mtime hold, never while
  written in the last RACY_S, failures never kept; the parse is shared) behind
  `load_shotlist` and `script_order`; `read_json_copy` (a private copy of the kept parse)
  for overrides, ref overrides and the cut, which are read, changed and saved;
  `refs.read_picks` (the shared parse) for the 13 places that only read picks, the 3
  that save keep `load_picks`. An audit of every shotlist caller found none that changes
  the doc (one test did; it copies now). The series config stays a plain read: deep
  copies of it cost more than parsing.
- **Measured over HTTP:** Porchlights ep01 `/refs` 2.27 / 2.39 s → 1.13 / 1.24 s; FRTEST
  0.41 / 0.54 → 0.39 / 0.45 s (the < 0.3 s target not met). In the server the sweep and
  auto-pick run after the reply (`sweep_later`), so the listing is what the tab waits
  on: 1.0 s, spread over ~200 refs each working out its own state. Going further means
  computing that once per request (3.4's request scope), not more file caching.
- **Same answers:** the refs listing (3.07 MB over Porchlights ep01, FRTEST,
  Ballroom-refactor, DeanStories ep05, ArchTest) and the episode status of both passes
  (3.71 MB) are byte-identical between the old code and the new. Live on
  Ballroom-refactor: a location ref generated locally (krea2, 16 s), its new take
  picked, the original picked back: the listing showed each change on the next request.

#### 1.9 The Episode tab: takes read once per request ✅
`GET /episode` lists every shot's takes twice (the sweep, then the status) and reads
every sidecar twice (FRTEST: 846 reads of 423). **Change:** the sweep only looks at
takes still queued and hands its listing to `episode_status`.
- **Target:** FRTEST `/episode` warm from 0.57 s to under 0.3 s.
- **Tests:** existing sweep tests; the reply is identical before and after on a fixture.
- **Live check (you):** Episode tab on FRTEST and Ballroom-refactor: identical reply
  (saved JSON). Queue a local render, then stop ComfyUI's job from ComfyUI's own
  queue: on the next load the take is closed as before.
- **Done:** `sweep_takes(listed=)` hands its listing to `episode_status(listed=)`; a sweep
  that closed a take, or failed partway, means the status lists afresh. Each shot's takes
  listed once per load (the test counts; twice before). The `/episode` replies of five
  shows, both passes, are byte-identical old vs new (3.8 MB).
- **Measured** A/B on the live server (same conditions, 4 runs each, first / again):
  FRTEST ~700 / 650 ms → ~410 / 400 ms; Porchlights ep01 repeat loads ~205 → ~140 ms.
  (The baseline table's FRTEST 0.57 s was taken under other load; this A/B is the fair
  one.) A cold first load right after a server start can still take seconds while the
  startup readiness check runs beside it.

#### 1.10 Assemble probes each file once ✅
An assemble of 5 shots runs ffprobe 34 times, field by field (start time, streams,
frame count, size, colour, duration), about a third of its time. **Change:**
`ff.probe(path)` returns one dict of what assemble asks for, cached per (path, mtime,
size) for the run; the `nb_frames`-first frame count stays (`-count_frames` takes
minutes on a master).
- **Target:** ffprobe runs per assemble ≈ one per input; Ballroom-refactor ep01 from
  3.9 s to about 2.7 s.
- **Tests:** test_assemble, test_bt709, test_cut_out, test_phase9d; an assemble of a
  fixture is byte-identical before and after.
- **Live check (you):** Assemble Ballroom-refactor ep01 from the editor; play it: same
  cut, same audio, same length; the new file's hash matches the one assembled before
  the change.
- **Done:** `assemble.probe(path)`: one `ffprobe -of json` per file with every field the
  helpers read (frame count, rate, size, colour, start times, durations, audio layout,
  the stream signature with its codec headers), kept per (path, size, mtime); the
  helpers read their field from it and `-count_frames` stays the fallback. Outputs are
  byte-identical to the old code's: Ballroom-refactor ep01 (sha1 358a3dcb…, 3 clips
  re-encoded) and ep02 (d486e3d2…, every clip copied). ffprobe runs 34 → 12 (ep01) and
  32 → 11 (ep02); ep01 3.8 → 3.3 s, ep02 1.84 → 0.75 s.

#### 1.11 Opening an episode doesn't wait on readiness or repeat itself ✅
Found by your check of 1.6 / 1.9 ("the first load of an episode still takes several
seconds"), with a per-request timing log on the live server: opening an episode sent
`/episodes` four times (0.3-0.45 s each) and `/episode` twice, and `/targets?ready=1`
took 1.6-2.5 s whenever its 30 s cache had lapsed (`/object_info` again, then every
target's workflow); all of it at once, so each waited on the others (Python's lock):
Porchlights ep01's `/episode` ran 5.0 s on the server, 0.28 s alone. **Change:**
- The page: `ensureEpisodes()`, one request for the episode list however many pickers
  ask for it while it's coming (each answer had opened the episode again, the doubled
  `/episode`). An explicit reload (after a save, a new episode) is `loadEpisodes()` as
  before.
- The server (`api.REFRESH_BEHIND`, set by both hosts): readiness, `/object_info` and the
  targets' workflows past READY_TTL are answered from what was kept while a thread asks
  ComfyUI again (one per kind at a time, with the request's shows in force); an install
  (`forget_comfy`) still makes the next answer wait, and a refresh started before an
  install isn't kept. Off for tests and the CLI.
- **Measured:** `/targets?ready=1` with its cache lapsed 1.6-2.5 s → 0.025 s.

#### 1.12 A workflow with a system prompt imports as a model ✅
Found by your check: adding `image_netayume_lumina_t2i` failed at save ("binding.params.prompt:
workflow must contain exactly one StringConcatenate titled 'StringConcatenate'"). Two
things were wrong. Its prompt and negative are each a StringConcatenate of a fixed system
prompt (string_a) and the text (string_b); both nodes keep the class's own title, so the
title the inspector narrowed by matched both. And it chose string_a: every render would
have written the prompt over the system prompt. **Change:**
- `inspector._spec` narrows by whatever picks the node alone: its title if no other shares
  it, else what it feeds, else both, else what it feeds and that node's title (a `feeds`
  selector may be `[class, input, title]`: the Positive / Negative Prompt encoders).
- `text_widget` puts the prompt in a node's last text field when it has several (a prefix
  first, the text after), and the inspector says which it chose.
- What still can't be told apart is a problem when the workflow is inspected, not only at
  save, and `select_nodes`' error says to give the node a title of its own.
- Live: the Lumina workflow inspects with no problems: prompt → string_b of the positive
  concatenation, negative → string_b of the negative one, the system prompts kept.

Phase 1 ends with the whole bench rerun, the table above filled with after-numbers,
and one PR.

### Phase 1 results (2026-10-20, branch `refactor-fixes-speed`)

Your checks (2026-10-20): cancel fast and correct, Upscale and Post instant, refs pick
faster, assembly quicker and the cut plays the same, episodes open without the wait
(after 1.11), the drafts switch and the Lumina workflow import work (1.12).

Suite: 1522 passed, 14 skipped (1503 before; 19 new tests), 10:28 (12:15 before).
Bench on the live server, restarted on the final commit (first / again):

| What | Before | After |
|---|---|---|
| `/refs`, Porchlights ep01 | 2.27 / 2.39 s | 1.03 / 1.19 s |
| `/refs`, FRTEST | 0.41 / 0.54 s | 0.36 / 0.45 s |
| `/episode`, FRTEST (A/B, same load) | ~0.70 / 0.65 s | ~0.41 / 0.40 s |
| `/episode`, Porchlights ep01 | 0.17 / 0.16 s | 0.16 / 0.11 s |
| `/upscale/options` | 0.96 s | 0.004 s |
| `/post/options` | 0.93 s | 0.003 s |
| `/targets?ready=1`, ComfyUI down | ~98 s | ~2.4 s |
| assemble, Ballroom-refactor ep01 / ep02 | 3.8 / 1.84 s | 3.3 / 0.75 s |
| `test_readiness::test_route` | 96 s | 2.3 s |

Unchanged on purpose: `/router/models` (2 s once, then kept an hour: Router's catalog),
`/episodes` (0.26 s), `/promote` (0.5 s on Porchlights: a candidate for Phase 2/3).

---

## Phase 2 — shared helpers (one PR each)

Plain consolidation: each replaces near-copies with one function and settles their
differences on purpose (listed). Live checks are the flows that use each helper.

#### 2.1 `core/fileio.py`: safe writes and reads ✅
About 14 atomic-write copies (`takes.write_json` the best; others without the Windows
share-retry, with fixed `.tmp` names two threads can collide on, or writing CRLF), about
15 read-with-default blocks, 5 file hashers, 8 stat-key shapes. **One module:**
`write_json` / `write_bytes` / `copy` (atomic, LF, share-retry), `read_json(path,
default, want=dict)`, `file_digest`, `stat_key`. Standard library only (build uses it).
- **Differences settled:** settings.json and the presets file are written with LF from
  now on (their content is unchanged).
- **Live check:** change a setting, save a preset, pick a take, Build, edit an
  override; each file reads back.
- **Done:** `seriesmith/core/fileio.py` (stdlib): `write_json` / `write_text` /
  `write_bytes` / `copy` (atomic, LF, a temp name of each writer's own, removed on
  failure), `replace` and `shared` (the Windows retry), `temp_beside`, `read_json`,
  `read_json_or` (a default for a missing, unreadable or broken cache / journal / lock),
  `read_json_kept` / `read_json_copy` (from 1.8), `file_digest` (chunked). Moved onto
  it: takes (its names kept as aliases), settings, presets, the inspector's target
  save, the queue journal, diskcache, the modelid cache, peaks, source's saves, refs'
  two private copies, the thumbnail (its temp name was per process: the two thumbnail
  threads could share it), native's output fetch, the build's outputs (written in place
  before: a reader could see half a shotlist), align's result; every swap of a file a
  tool wrote (refs, runner, jobs, finishing, installer, the trash) gets the retry; three
  hashers (one read a whole video into memory for sha256). Each JSON file keeps its
  layout; what changes is line ends (LF everywhere; the goldens normalise them).
- Live: settings saved (LF, reads back); Ballroom-refactor built (every output LF and
  the same content as the original's); align's readiness probe; a ref generated locally,
  picked, picked back (the queue journal LF); an override set and cleared (and the file
  restored). No `.tmp_` left anywhere. Suite 1537 passed.
- Found: Ballroom ep01's sh040 prompt override holds `â€”` for an em dash (UTF-8 read
  as cp1252 somewhere, before this pass). Traced in 2.6.

#### 2.2 `core/paths.py`: the series config and ids ✅
11 ways to find `series.json` (episode folder then parent), three ways to parse it, 7
`safe_id` copies (three without the empty-id fallback). `align` and the commands look
in the episode folder only. **One module:** `series_home`, `series_config_path`,
`episode_script`, `safe_id`; one cached loader.
- **Differences settled:** align and the commands find a parent-folder series config,
  like everything else.
- **Live check:** `seriesmith takes`/`cut`/`align --help` on a show whose series.json is
  in the parent folder (Ballroom-refactor).
- **Done:** `seriesmith/core/paths.py` (stdlib): `series_home`, `series_config_path`,
  `episode_script`, `episode_files` (says what's missing), `safe_id(text, fallback)`.
  edit's two finders are its aliases; jobs (5 copies), assemble, the targets' show folder,
  edit's plate home, align and the commands use it; the safe-id copies in takes, cloud,
  jobs, finishing and three targets' keyframe paths (each keeps its own fallback).
- Reproduced first: `seriesmith build` of an episode whose series.json is in its series
  folder said "series.json not found" (the editor built it). Now it builds, `--each`
  takes such episodes (and skips a folder with no script, as `refs/`), and align finds
  its files. The episode list, Refs listings and `/episode` of five shows: byte-identical
  old vs new (6.9 MB). Suite 1542 passed.

#### 2.3 `ff.py`: probe and run ✅ (smaller than planned)
Two `video_duration`s that mean different things (stream vs container), two frame
counters, three JSON probes, five run wrappers, three "is ffmpeg here" checks; frame
hashes and join checks in both assemble and publish; publish rebuilding the BT.709
filter. **Into ff.py** (extends 1.10): `run`, `probe`, `duration(source=)`,
`frame_count`, `frame_md5s`, `check_joins`. helpers/ and comfy_nodes/ keep their own
(they run without the package).
- **Live check (you):** Publish a Ballroom-refactor master; a ref from a video frame;
  peaks on the timeline.
- **Done, and why it's smaller than planned:** read closely, the probes weren't copies.
  Each asks for different fields at a different exactness (finish and refs decode every
  frame on purpose: a provider's mp4 can carry an edit list that makes the header's count
  wrong; assemble and peaks trust the header), once per operation, with its own error
  policy. Folding them into one probe would trade correctness for tidiness. What was
  copied: running ffprobe for JSON and parsing it (now `ff.probe_json`, under assemble,
  publish, finish and peaks, each keeping its flags and messages) and the framemd5 run
  (now `ff.frame_md5s`, under assemble and publish, each keeping its error policy);
  publish's title clips use assemble's BT.601 → 709 filter text (`BT601_TO_709`).
- Checked first: 1.10's single probe answers the same through the PyAV ffprobe stand-in
  (a ComfyUI-only machine), field for field, and assembles byte-identically there.
- Live: Ballroom-refactor ep01 / ep02 assemble byte-identically (358a3dcb…, d486e3d2…);
  ep01 publishes byte-identically old vs new (0c77dfc1…, with test title clips in the
  scratch show's `_titles`); finish's and peaks' probes identical on 6 real takes.
  Suite 1547 passed.

#### 2.4 HTTP JSON in one place ✅
7 urllib+TLS copies (router, router_inspect ×2, cloud, comfy health, features, installer)
with different TLS, error and User-Agent handling. **One** `backends.http_json`.
- **Live check:** Settings → backends answer; Features lists sizes; nothing paid is
  called (Router/Cloud paths are covered by their tests with fakes only).
- **Done:** `backends.http_json(url, method, body, headers, timeout)` (tls() for https,
  `HTTPFailure(status, text)` for an error status, no answer / not JSON as they come)
  under the four that were the same job: Router's `_api`, router_inspect's schema and
  catalog, Cloud's node list; each still says its errors in its own words. The other
  three aren't JSON calls and stay: the health check (reads a status, tells a refused key
  from a missing route), `head_size` (a HEAD), the installer's downloads (streamed).
  Router's header now spelled `X-API-Key` like the others (HTTP ignores case).
- Live, read-only (no renders, nothing billed): Router's catalog (252 models), a
  Seedance schema, a missing model's error, Cloud's node list (3,796): identical old vs
  new. The Seedance library POST is a paid render's step, so only its local-server test
  (`tests/test_http.py`) covers it. Suite 1552 passed.
- Your smoke-test questions, answered: renders that come back from Router or Cloud are
  saved by code 2.4 didn't touch (its router diff is `_api` alone; cloud's, the node
  list). Seedance registration, run against a local fake of the library endpoints on
  old and new code: byte-identical requests (method, path, headers, body with the file's
  sha256), the same `asset://` id after polling to Active, the same refusal message.
  That check also caught one difference of mine (an empty answer returned None instead
  of raising, as before), fixed.

#### 2.5 Take records: `mark_failed` / `mark_queued` ✅
The same failed/queued sidecar update in jobs, refs, finishing, upscale and post;
`settings_hash` identical in upscale and post. **Into takes.py.**
- **Live check (you):** a local upscale and a post that fail (missing model) and one
  that succeed, in Ballroom-refactor; their takes read the same as before.
- **Done:** `takes.record_queued` / `record_failed` / `settings_hash`; the seven
  mark_queued / mark_failed of jobs, refs, finishing, upscale and post call them (each
  keeps its name and signature); upscale's and post's settings_hash are takes' (a test
  pins its value: records store it); post.rel is upscale's.
- Found: test_ref_queue failed whenever it ran after test_refs (its module teardown
  deleted the shared episode but kept pointing at it); the suite passed only by running
  them alphabetically. Fixed in the test.

#### 2.6 Small copies ☐
Prompt helpers (`_sentence`, `_and`, `_article`, `_subject_sentence`, 4 copies) into
`targets/prose.py`; graph helpers (`_consumers`, `_new_id`, …, 7 copies) into one module;
`assemble.say` and `publish.say` onto `edit.progress_line`; `api._preset_picture` onto
`preset_pictures.shrink`; image flattening with `exif_transpose` everywhere (thumbnails
from phone photos stop coming out sideways).
- **Goldens:** prompts must be byte-identical.
- **Live check (you):** an upright phone photo uploaded as a ref shows upright.

---

## Phase 3 — structural (one PR each, in this order)

Each starts with a short design note here (what changes, what stays, what you'll see)
for you to agree before code.

#### 3.1 Targets: one shot-compile base ☐
The shot entry is compiled in 5 near-copies (ltx2, fl2va, ltx2_ingredients,
video_prose, ref2va's legacy path): checks, length, cram warning, layers, the entry,
the model/LoRA/profile tail, the episode doc and report. **`targets/video_compile.py`**
with the shared steps and per-target hooks; the reference-sheet staging (3 copies:
ltx2, ingredients, wan) and panel picking (2) go with it.
- **Goldens:** every target's shotlist and prompts byte-identical; warning wording kept
  per target.
- **Live check (you):** Build every show you have (read-only: into a scratch copy);
  shotlists identical to before (a diff of the shotlist folders). One local render each
  on ref2va, fl2va and ltx2 in Ballroom-refactor.

#### 3.2 Server: one route list, one error standard ☐
Three route tables registered differently by the two hosts (`/api/seriesmith/jobs` is
404 standalone, fine under ComfyUI; ComfyUI's clash check sees only one table; a queue
failure drops the features routes too); 77 hand-written `except X: raise
ApiError(4xx)`; the queue, settings and features views parse, answer and fail their own
way. **Change:** a `routes.py` list both hosts register in one loop with the `/api`
alias; domain errors carry their status; queue/settings/features handlers become plain
functions served by `make_view` (JSON, gzip, executor, errors in one place); one
startup sequence (proxy, detect, recover) for both hosts.
- **Live check (you):** every window of the editor on the standalone server, then the
  same through ComfyUI's page (`/seriesmith` in ComfyUI): Jobs, Settings, Features,
  Refs, Episode, Upscale, Post, Master. Error messages read as before.

#### 3.3 Long work goes on the queue ☐
Master assembly keeps its own registry and events; `POST /assemble`, `/align`, `/track`
and `/build` hold a server thread for the whole run (minutes for align). **Change:**
each becomes a queue job in a CPU lane, the route answers `{job}` at once, progress is
the queue's own; `_MASTER_JOBS` goes. **Visible:** these show in Jobs and survive a
restart like renders do. Needs page changes.
- **Live check (you):** Assemble, Master and Align in Ballroom-refactor from the editor;
  each shows in Jobs with progress; restart the server mid-assemble and it's picked up
  or failed with a clear reason; the editor stays responsive throughout.

#### 3.4 One cache module ☐
About 20 hand-rolled module caches with different keys, bounds and locking (some
unbounded, some unlocked). **`seriesmith/memo.py`**: `stamp`, `FileMemo`, `TTLMemo`
(locked, bounded), one `forget_all()` for tests and a Settings change. Absorbs 1.6 and
1.8's caches.
- **Live check:** the bench (no slower); edit a script, a series config and a take
  outside the editor; each shows on the next load.

#### 3.5 The backend interface ☐
Callers rely on methods only some backends have (`object_info`, `choices`, `has_node`,
`without_missing`), so `render.py`/`runner.py`/`queue.py` branch on `kind == "cloud"`,
`!= "router"`, `lane == "local"`. **Change:** the base class grows `where`,
`object_info`, `choices`, `shares_disk`, `serial`, `prepare(graph, job, take)`; the cloud
lowering moves into the Comfy backend; runner's four enqueue methods share one skeleton.
- **Live check (you):** local renders of a ref, a shot, an upscale and a post; the Cloud
  and Router paths are covered by their fake-backed tests only (paid limit stays 0).

#### 3.6 One command registry ☐
`cli.py` runs some stages in-process, `commands.py` re-launches others as subprocesses,
with three entry signatures and two usage-error conventions. **Change:** one
`COMMANDS` table; stages in-process unless isolation is needed; usage errors exit 2.
- **Live check:** every command's `--help`; `seriesmith all` on Ballroom-refactor with
  local renders.

---

## Not doing (for now)

- **Import time.** The server's 0.5 s is aiohttp; `api` importing all of edit/refs/jobs
  eagerly costs ~120 ms. Not worth the churn.
- **The node pack's own copies** (`fit_size`, the encoder, strip indices) stay: the pack
  must run when copied without seriesmith. 2.6 adds a test that they match.
- **Splitting `api.py` / `refs.py`** by size alone. 3.2 moves routes beside their
  handlers; a split can follow if it still helps.
