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
- ~~Found: Ballroom ep01's sh040 prompt override holds `â€”` for an em dash.~~ Withdrawn
  in 2.6: the file holds proper em dashes; my own check read it without
  `encoding="utf-8"` (Windows then reads cp1252) and made the `â€”` itself.

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

#### 2.6 Small copies ✅
Prompt helpers (`_sentence`, `_and`, `_article`, `_subject_sentence`, 4 copies) into
`targets/prose.py`; graph helpers (`_consumers`, `_new_id`, …, 7 copies) into one module;
`assemble.say` and `publish.say` onto `edit.progress_line`; `api._preset_picture` onto
`preset_pictures.shrink`; image flattening with `exif_transpose` everywhere (thumbnails
from phone photos stop coming out sideways).
- **Goldens:** prompts must be byte-identical.
- **Live check (you):** an upright phone photo uploaded as a ref shows upright.
- **Done:**
  - Phone photos: the editor's thumbnails, a preset's tile and mksheet's sheets now read
    the orientation tag (only the sheet composer did; ComfyUI turns it itself, so renders
    were right). Reproduced first: a tagged 400x200 photo came out 160x80 / 400x200
    sideways, now portrait. Thumbnails are keyed `upright`, so sideways ones are remade;
    untagged pictures' thumbnails are pixel-identical (48 of 24 real pictures, both widths).
    `api._preset_picture` is `preset_pictures.shrink(path, size)`.
  - `targets/prose.py` (sentence, join_and, article, subject_sentence: 4 copies) and
    `targets/graph.py` (of, consumers, new_id, abs_path: 7 copies; inspector's consumers,
    finishing's _abs and jobs' _next_id differ on purpose and stay). Goldens identical.
  - Not done: assemble.say onto edit.progress_line, which would load the whole editor
    into every assemble for one print.
- Live: three real episodes (DeanStories ep05, Porchlights ep01, Ballroom ep01) rebuilt in
  scratch on main and on this branch: every shotlist, prompt and refs_todo identical. A
  local render of Ballroom-refactor sh010 through the editor: ok in 57 s, mp4 with audio,
  record, thumbnail and strip saved. Suite 1557 passed (it caught one bug of mine, a
  missing import, fixed).

---

## Phase 3 — structural (one PR each, in this order)

Each starts with a short design note here (what changes, what stays, what you'll see)
for you to agree before code.

#### 3.1 Targets: the shared compile steps, light ✅ (decided 2026-10-20)
**Design note, as agreed.** The video targets are vertical slices on purpose: each model
takes its inputs its own way, and new models mostly arrive as data (a target.json on
`builtin:video_prose` / `builtin:router_video`), which already share their compile. A
base class with hooks would make the next hand-built model fit someone else's steps. So
only what is model-agnostic and identical moves, as plain functions each target calls in
its own order (`targets/video_compile.py`); prompts, keys, length checks, the shotlist
doc and every render-time difference (router_video's request: max_chars, picture
mentions, ratio and resolution, Seedance's library and drafts) stay where they are. H3
Ref2VA's legacy path stays its own (its entries' shape, voices and retention, the latent
hold). Reference-sheet staging and panel picking: not moved (render-time, per model).
- **First: the Router request goldens** (`tests/test_router_golden.py`, from main before
  any change). The 15 Router models had none: every shot's request pinned offline, with a
  long-prompt case per model so the max_chars cut shows (Runway and Veo at 902 chars,
  Kling 2448 with its picture mentions, the line and the sound kept), a Seedance draft's
  final, and the refusals of models that need a first keyframe.
- **Done:** check_shot, shot_duration (FL2VA's private copy gone: the one that missed
  `dur: model` in 1.1), snap_frames, crammed, shot_audio, shot_layers, entry_head,
  entry_tail, legal_size, fallback / override warnings, episode_report. ltx2, FL2VA,
  ingredients and video_prose: 486 lines out, 74 in, ~230 in the module. Every golden
  byte-identical (Router ones included); three real episodes rebuild identically on main
  and here.
- **Changed on purpose** (approved): a shot past ltx2's or FL2VA's longest names itself
  in the seconds asked, as the others did ("2160 frames is longer than LTX-2's maximum
  of 481 (20.04s)" before); a Router or prose model that makes sound says in `--check`
  which shots ask for a cloned voice or a dub it renders as generate (a silent one's
  "makes no sound" line already did).
- **Found and fixed:** every Router model's audio fallback reason said "Seedance makes
  its own sound..." (the generator copies Seedance's recipe): Kling, hosted H3, Veo,
  Wan 2.7 and 3.0 now name themselves; the Router goldens change by that name only.
- Live: one local render each through the editor on the new compile, Ballroom-refactor
  proxy: ltx2 (sh010, 49 s, 73 frames with sound), H3 FL2VA (sh030, 24 s, 39 frames with
  sound), Wan 2.2 5B on the prose path (sh050, 18 s, 73 frames, mute as it should be):
  each take's mp4, record, thumbnail and strip saved. Suite 1563 passed.

#### 3.2 Server: one route list, one error standard ✅ (decided 2026-10-20)
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
- **Done:** `server/routes.py`: the API's, the queue's (Jobs, backends, Settings, SDK)
  and Features' routes in one list, which both hosts register once each at its path and
  under `/api` (17 standalone `/api` paths that were 404 now answer; ComfyUI's clash
  check sees all of them). The queue, Settings and Features routes are `@handler`
  functions served by `make_view` like the API's (JSON, gzip, executor, the error body in
  one place); `get_file`/`get_thumb`/`get_preset_image` say `reply = "file"` and the thumb
  pool on themselves. Thirteen domain errors carry `http_status` (RefError 400,
  UnknownRef 404, MasterError 409, ...) and the handler answers by it: 25 pass-through
  `except X: raise ApiError(...)` blocks gone from `api.py`.
- **Changed on purpose** (approved): a Jobs action missing its id answers 400 "id is
  required" (404 before), an unknown job 404 "no such job: 'x'", an unknown action names
  the valid ones, a bad body reads "the request body must be JSON" everywhere.
- **Found and fixed:** inside ComfyUI a queue that failed to start took the Features
  routes down with it (they now register on their own); Jobs, Settings and Features
  called a bare `fetch("/seriesmith/...")`, which misses `api.fetchApi`'s prefix and a
  ComfyUI served under a sub-path: they go through the host now (`Api.fetch`).
- Not done: one startup sequence (proxy, detect, recover) for both hosts; each host's
  start differs where it must (ComfyUI owns its loop and port) and the rest is already
  shared calls.
- Evidence: a probe of 84 requests (every read route and malformed requests, bare and
  `/api`) on main and after each commit: only the changes above, the last two commits
  84 of 84 identical.

#### 3.3 Long work goes on the queue, light ✅ (decided 2026-10-20)
**Design note, as agreed.** Master keeps a registry of its own (`_MASTER_JOBS`, a guard
lock, its `seriesmith.master` events, `GET /master/job` for a reopened dialog); align runs
inside its request with `seriesmith.align` events, so a reload mid-run loses it; neither
shows in Jobs or can be cancelled. Build, track and assemble also run inside their
request, but they are short (assemble 0.75-3.3 s on Ballroom-refactor, build well under a
second): they stay. Master and align become queue jobs on one serial `cpu` lane, beside
the renders; the routes check their input as before (400 / 409 at once) and answer the
job; the dialogs follow the same events.
- **Done:** `Runner.local_job` / `enqueue_local` (the `cpu` lane, `queue.SERIAL`);
  `api._master_task` / `_align_task` (what runs, the result the page follows),
  `start_master`, `GET /seriesmith/align/job`; `_MASTER_JOBS` and its guard gone (the
  master's job is the queue's). Cancel: a `stop` hook through `edit.run_tool` and align's
  `_stream` to `Queue.arm_cancel`, so Jobs' Cancel kills the tool running; a canceled
  master removes what it made. Restart: journaled (`resume` kind `local`), and
  `api.rebuild_local` lists one that was running as failed for Retry, queues again one
  that was waiting. `Queue.close` on the server's shutdown (ComfyUI's exit too) keeps the
  journal as it stands and kills the run, which Windows would otherwise leave going. The
  page: Master shows a queued job at once (`stage: "waiting"` while the lane is busy), its
  ProRes waits for the job's end; Align follows its job to the answer, and the Recording
  window picks up an align still running after a reload. Without a queue both still run
  in the request, as the mock does. Tidy: ROUTES' two entries on one line.
- **Changed on purpose:** `POST /master` (assemble, prores) and `POST /align` answer
  `{job}`; the align events open with `start` and close with `done` / `failed`; a second
  align of an episode while one runs is 409 with the job; `prores_only`'s refusal is
  `master.check_prores`, asked before queuing.
- **Found and fixed:** every align that had to transcribe failed from the editor since
  step 7b: align.py put the package's folder on sys.path (an h3pipe leftover), so Whisper's
  `import queue` found seriesmith/queue.py ("module 'queue' has no attribute
  'SimpleQueue'"); re-aligning from a cached transcript never imports Whisper, so it went
  unnoticed. A test now loads align the way the runner does and checks `queue`.
- Live, 8190, Ballroom-refactor (local only): an align episode (`ep90_align`: ep01's
  script with three lines, a Windows TTS recording): a dry run transcribed with Whisper
  medium.en in 20 s while a ProRes asked meanwhile waited (`stage: waiting`) and ran after;
  a second align 409; the real run timed every shot, wrote the script, the build passed;
  cancel mid-transcribe killed it, the script untouched; a restart mid-transcribe left no
  align process, listed it failed, Retry aligned it in 18 s. Master on ep01 (its three
  upscales queued from the plan first, on local ComfyUI): a second assemble 409; cancel at
  `clips` left the earlier master byte-identical and the lock released; the full master in
  18 s with its titles (picture copied), a local render running beside it; Jobs at 100%.
- **Live check (you):** Master and Align from the editor on both hosts (ComfyUI needs a
  restart to load this); each in Jobs with progress and Cancel; reopen the Recording
  window (or reload) mid-align and it is still followed.

#### 3.4 Loads that don't redo unchanged work ✅ (decided 2026-10-20)
**What's there.** Opening Porchlights ep01 (final pass, 324 shots, 1,773 takes) after a
restart: `GET /episode` 4.1 s on the live server (2.9 s alone; 7.4 s before the refactor),
`GET /refs` 2.1 s beside it; no request is made twice (headless Chrome against a traced
copy of the server). Every load re-derives every take from its files: ~2,500 sidecars read,
~20,000 paths checked, each take's staleness, sound and upscale recipe worked out again,
though almost nothing changed since the last load. The answer is 1.7 MB, nearly all of it
per-take detail (upscale record 203 KB, save notes 136 KB, ids, times) that the shots list
doesn't draw and `GET /shot` already gives when a shot is opened.

**Change: a take's entry is kept until something it depends on changes.**
- **One listing per shot folder.** `os.scandir` of the shot's renders folder gives every
  file's name, size and mtime in one call (on Windows the stat comes with the listing):
  ~324 calls, not ~20,000 `isfile`s. A take's files (sidecar, mp4, thumb, strip, `_h3.wav`,
  its upscale's and post's records and outputs) are looked up in it.
- **A take's entry is cached on what it is made from:** the (name, size, mtime) of each of
  its files from that listing; its shot's built entry (story hash, length, target) and
  override; the target the shot renders on; and a small episode-wide stamp (the series
  config, which holds the upscale recipe and audio; the episode's fps; the targets'
  catalog stamp). Same key, same entry; anything different and that take alone is worked
  out again. Nothing relies on folder mtimes or on writes going through seriesmith: a take
  deleted, a sidecar edited by hand or an upscale written by ComfyUI changes its files'
  stats, so it's seen on the next load.
- **Kept on disk** (`diskcache`, as media probes are): a restart starts warm. Bounded (the
  last few episodes per pass), dropped whole on a version change of the entry's shape.
- **Per-shot fields stay computed each time** (cut, override, target, missing refs): they
  are cheap and depend on files the listing doesn't cover.
- **`/refs` the same way** (per ref folder: its takes and picks), measured first and done
  only where the profile says the time is.
- **The page:** the remembered episode is asked for at once (not after the episodes list),
  and refs after the shots are in, not beside them (they share one Python and slowed each
  other: 2.9 s alone, 4.1 s together).
- **Folds in the original 3.4** where it touches: the new cache is a `memo` primitive
  (`FileMemo`-style, locked, bounded, `forget_all()` for tests and Settings); the other
  hand-rolled caches move onto it only where they're on this path.
- **Not in this item:** slimming the answer (per-take detail only in `GET /shot`). Smaller
  and faster again, but the timeline, Master planning, cut playback and the badges may
  read those fields from the episode today; it needs that audit first, as its own item.

**What you'll see:** an episode opens in well under a second after a restart when nothing
changed (target: Porchlights ep01 final under 0.6 s, from 4.1); a change shows on the next
load whoever made it.
- **Evidence:** `/episode` and `/refs` answers byte-identical with the cache on and off,
  cold and warm, on Porchlights ep01/ep02, DeanStories ep05, Ballroom-refactor; tests that
  change a take outside the editor (delete it, edit its sidecar, add an upscale, change the
  recipe, an override, the target) and see it on the next load; the headless page load
  timed before and after.
- **Live check (you):** restart, open Porchlights ep01 and a couple of others; render,
  upscale and pick takes and see each show; edit a script and rebuild.
- **Done:** `seriesmith/takefiles.py`: `listing` (one scandir per shot folder),
  `take_facts` (sidecar, upscale and post records with `fresh`, which file plays the
  sound) kept on the (size, mtime) of the take's nine possible files, `list_takes` from
  them; per episode-pass diskcache stores, the newest 24 kept, a version stamp. `Take`
  answers `has_video` / `exists` from its listing. The status and sweep list through it;
  `take_rel`, `take_audio`, `upscale_summary`, `post_summary` read the facts. Ref takes:
  one listing per folder within an answer (`takefiles.looked`), sidecars kept the same
  way (the show's "refs" store); `GET /refs` within `cut_memo` and `takes.one_look` (each
  reference file's sha1 looked up once per answer, not once per take).
- **How the key came out:** the design note keyed a whole take entry on its files, its
  shot's build entry, override, target and an episode stamp. Staleness, the chain check
  and the recipe match also read the cut, the neighbouring shots' takes and the refs, so
  caching them on that key could answer stale. Kept instead: what a take's *files* say
  (the I/O, keyed on those files alone, nothing else needed); the judgments are worked
  out each time from it. Same promise: anything changed shows on the next load.
- **Page:** the remembered episode is asked for as the page starts (loadEpisodes leaves
  it be while it loads); refs wait for the shots (`afterShots`: the Refs tab, a switch).
- **Measured** (Porchlights ep01, final pass, 324 shots / 1,773 takes):
  - In-process, a fresh process with the disk cache: `/episode` 2.1 -> 0.79 s, `/refs`
    1.3 -> 0.97 s; ep02 0.5 -> 0.21 s.
  - The page, headless Chrome on a traced copy of the server, cold process: the episode
    asked at 0.02 s (0.22), answered in 1.01 s (2.88); shots on screen at ~1.0 s (~3.1);
    thumbnails done 1.97 s (3.68); refs after, done 2.3 s, no longer slowing the shots.
  - Missed the 0.6 s target: what's left is the judgments (~0.5 s: staleness with
    retargeted entries, the upscale recipe check), worked out each time by design.
- **Evidence:** every answer byte-identical to main: Porchlights ep01 / ep02, DeanStories
  ep05, Ballroom-refactor ep01, `/episode` both passes and `/refs`, twice each (24).
  `tests/test_takefiles.py`: a sidecar edited by hand, an mp4 deleted, an upscale written
  elsewhere, a take deleted each read on the next load; queued and just-written files not
  kept; a caller changing its copy leaves the kept one; an old store version dropped; the
  status the same with the cache, without it, and after a hand edit.

#### 3.5 The backend interface ✅ (decided 2026-10-20)
**What's there.** The base `Backend` promises ping, submit, call and attach; everything
else callers find out by its kind: ~11 checks of `kind == "local"` / `"cloud"` /
`run.backend != "router"` across `render.py`, `runner.py` and `edit.py`, and the queue
makes a lane serial by its name. How Comfy Cloud differs is split: `render.py` lowers a
graph to Cloud's nodes (`cloud.lower` with Cloud's object_info) and lists Cloud's model
files; `backends/comfy.py` has the rest. The runner's four enqueue methods (render, ref,
finish, tour) repeat the same steps: the backend looked up ("isn't set up"), disk room,
a paid run charged before anything is reserved, the progress adapter, Cancel armed and
"on X: run id" logged when the run starts, the ending mapped to the queue's status.

**Change** (no speed change: dispatch is microseconds next to a render):
- **Named questions on the backend instead of its kind:** `shares_disk` (this machine's
  ComfyUI: reads the episode folder, probed for its nodes and files), `serial` (one job
  at a time; the queue asks it for a backend's lane), `own_models` (its model files are
  its own: Comfy Cloud), `prepare(graph, job, take)` (the graph as it runs there, and
  what collecting it needs), and a run's `reports_position` (Router). Each gives today's
  answer for each backend.
- **Cloud's lowering moves into the Cloud backend** (`ComfyBackend.prepare`); `render.py`
  asks the backend.
- **The enqueue methods share plain helpers** for the repeated steps; each keeps its own
  staging and collecting (a take, a ref picture, an upscale/post, a tour differ there).
- **Evidence:** every Router golden and Cloud test unchanged; the requests and the lowered
  Cloud graph captured offline on main and the branch, identical. Live, local (free): a
  render, a ref, an upscale, a post, a tour. Live, paid, the limit raised to exactly 3 and
  back to 0: one Comfy Cloud render (cheapest target, shortest shot), one Router image,
  one Seedance video (its asset registration). A deployment only if one is set up.
- **Live check (you):** a render on each backend you use; Jobs shows where each ran.
- **Done:** `Backend.shares_disk`, `serial`, `own_models`, `prepare()`, `Run.reports_position`
  (RouterRun); `ComfyBackend.prepare` lowers for Comfy Cloud; `render.py`, `runner.py`
  and `edit.py` ask them (no `kind ==` left outside the backends); the server's queue asks
  a backend's lane whether it is serial. Runner: `backend_for`, `reserve` (disk room, then
  the paid charge before anything is reserved), `started` (Cancel armed, where it runs and
  the backend's notes logged), `progress_to`, `ending`, used by render, ref, finish, tour
  and the restart re-attach. Line count about flat (the helpers are documented); each rule
  is in one place instead of four or five.
- **Evidence:** `render.prepare` on the test fixture's 15 shots for Cloud, local and a
  deployment (graphs, Cloud's notes and the uploaded files' bytes; 45 cases): identical to
  main, before and after the runner change. Suite 1579 passed. Live, local (free): render
  33 s, ref 23 s, upscale 92 s, post 222 s, tour 31 s (1 hold), each on `local` through the
  new code. Live, paid (the limit raised to allow exactly one each, back to 0 after):
  Seedream 5.0 image on Router (a 2544x1456 ballroom ref, 43 s); Seedance 2.5 on Router
  (sh010 with Cindy's and Ella's pictures through the Seedance library: 97 frames with
  sound, 126 s); Wan 2.2 5B on Comfy Cloud (sh020 lowered to Cloud's nodes: 41 frames,
  mute as it should be, 47 s). Three paid runs in all.

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
