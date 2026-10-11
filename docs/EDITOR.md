# The editor

The seriesmith editor is a page in your browser: `seriesmith serve` serves it at
http://127.0.0.1:8190. This is the guide to driving it: the order things happen in, what
every button does, and what each click, double-click and right-click means in each panel.

The page has the **Shots** and **Refs** tabs down the left, the **Viewer** docked in the
middle, the **Timeline** along the bottom, and the **Jobs** button (the queue) at the top
right. Everything else — the Script and Series config, the Inspector, Recording, What's
missing and the dialogs — opens as a floating window you can move, and dock beside the
viewer.

[INSTALL.md](../INSTALL.md) installs it. [AUTHORING.md](AUTHORING.md) is the format of the
two files you write. [API.md](API.md) is the HTTP contract underneath, for changing the
editor rather than using it.

## The order things happen in

The editor renders an episode. The writing is still yours, but it can make the episode for
you to write into:

1. **Install seriesmith**, the node pack and the model files ([INSTALL.md](../INSTALL.md)),
   or set up a cloud backend ([SETUP.md](SETUP.md)).
2. **Run `seriesmith serve`** (`--root C:\Shows` names your project folders) and open
   http://127.0.0.1:8190. It starts comfy-api-proxy in front of your ComfyUI if it isn't
   running.
3. **Open Shots → the folder button** and add the folder that *contains* your episode
   folders (the root), then pick the episode from the drop-down beside it.
4. **No episode yet? New episode…** in that same window writes the two files for you — see
   below. Otherwise write them yourself: `Shows\ep01\series.json` and `Shows\ep01\ep01.md`
   ([AUTHORING.md](AUTHORING.md) opens with a complete pair to copy).
5. **Build.** This runs `build` for both passes and fills the shot bin.
6. **Go to Refs and make the references** — character sheets, props, plates, voices.
   Renders are blocked until the pictures a shot needs are on disk, so this comes before
   rendering, not after.
7. **Come back to Shots and render**, proxy first. Each take is a job: watch them in
   **Jobs**.

**Proxy first, always.** The proxy pass is the same shots at the same seeds, rendered small
and cheap. It tells you whether the cut works, the timing lands and the characters hold,
for a fraction of the time. Switch the pass selector to `final` once the proxy says the
episode is right.

## Shots

### The toolbar

Left to right:

| Icon | What it does |
|---|---|
| folder-open | **Project folders** — browse, add or remove roots, open an episode |
| refresh | **Rescan the project roots** (after adding an episode folder outside the editor) |
| folder | The episode drop-down |
| *(pass)* | **final / proxy** — which pass you are looking at and rendering |
| play | **Build** — runs `build` for both passes from the script and series config |
| file-edit | **Edit the episode's script** — opens the Script window |
| book | **Edit the series config** (`series.json`) |
| volume-up | **Recording** — attach a dialogue recording and time the script against it (`align`). Lit when the episode has one |
| sliders | **Inspect the selected shot** |
| play | **Play all** — the cut, played from its takes, no export needed |
| film | **Open the timeline** |
| images | **Open the Refs tab** |
| refresh | **Refresh** — re-read the episode from disk |

### New series, new episode

In **Project folders** (the folder-open button), browse to a folder and press **New
series…** (a show of its own, in a folder made inside this one) or **New episode…** (in
this folder: the show's folder, not an episode's). Either opens a short wizard:

1. **Where**: for a new series its title and its show folder (made from the title); the
   episode's name (the next number there, `ep03` after `ep02`) and its title. When the
   folder already has episodes, it says so: the new one continues that series.
2. **Series** (a new series only): its id, the video model, the final and proxy sizes
   (864×480 by default), the look, how dialogue sounds and the speech pace. Everything
   else is in Series settings, any time.
3. **Cast and places**: who and where the episode is about — a character (name, design,
   voice), a location (a short name and its description), a prop or vehicle —
   each with its picture path filled in from the show's layout. A next episode carries its
   neighbour's whole cast over, so you add only who and what is new.
4. **First shot**: where it happens (the first sequence's location), who's in it, size,
   length, what happens, dialogue, camera and sound. The shot form adds the rest.

**Create** writes the two files in one go: a series config of the episode's own (a next
episode's is its newest neighbour's, with the new cast added) and the script. The episode
opens and builds, so its shots are there and the pictures it needs are listed as missing,
which is the next thing to do (the Refs tab). The paths are `../refs/...`: **one `refs`
folder beside the episodes, shared by all of them**, while each episode keeps its own
config. That is the layout to want: shared references, per episode cast lists.

The buttons are off when the folder isn't inside a project root: add it as a root first.
`seriesmith new Shows\ep02 --title "…"` makes an episode without the UI, from the newest
episode there or the starter pair (one character, one prop, one location, three shots).

One thing to know about sharing: a ref's *live file* is shared, its candidates and its pick
record are not. Picking a new take of a shared sheet in one episode replaces the file every
other episode reads, and their takes go `stale: ref`. That is usually what you want (fix
the sheet once, **Re-render stale** everywhere); when an episode genuinely needs its own
look for a character, give it an episode-local path (`refs/walker_ep02_sheet.png`, no `../`).
The Refs tab now warns you before that happens — see **Sharing refs between episodes**.

### Rendering the shots that need it

Two buttons beside Build ask for work in bulk:

| Button | What it queues |
|---|---|
| **Render missing (n)** | every shot with no finished take and nothing queued — the first pass, and anything that failed |
| **Re-render stale (n)** | every shot whose newest take is out of date: the script, a reference, the preset or the target changed since it rendered |

**Re-render stale** is the other half of the edit loop: change a line, rebuild, and the takes
that no longer match are badged `stale` — this queues exactly those. It renders each shot at
its **built seed** (`stable_seed`, the one a first take uses), so the new take differs from the
old one by your edit and nothing else. A take that was itself a redo on a rolled seed goes back
to the built seed, which is the shot as it would render now.

A take badged only `unknown` (no provenance: it predates take sidecars) is left out — it isn't
evidence of anything. A shot with a take already queued is left out too. Hover the button for
the reasons behind the count ("12 script, 3 ref").

### How far through a pass you are

Beside the filter box, the Shots tab reads out the pass as it goes:

```
37/240 · 12q · 24m · ~20s/shot · ~68m left
```

Shots with a finished take out of the shots in the pass, then takes queued, failed
shots when there are any, how long this run has been going, its rate, and what is left at that
rate. The timeline header shows the same line while anything is queued, since that is the
window you watch a long pass from. Hover either for the arithmetic.

The rate is **wall clock per finished take**, not how long a take takes: with 200 jobs on
the queue most of a take's own clock is waiting its turn, and that would read far slower
than the pass really goes. Takes from an earlier sitting don't count — a gap of more than
15 minutes starts a new run — and no rate is shown until two takes of a run have finished.
With nothing queued you see the last run's rate and no estimate.

### Shots and takes

The bin is grouped by sequence (`sq01`, `sq02`, …) with every shot under it and every take
under the shot.

- **Click a sequence header** to expand or collapse it.
- **Click a shot** to select it. The Script window follows the selection, and so does
  Inspect.
- **Click a take** to select that candidate; **double-click** opens it in the Viewer.
- **Use** puts that take in the cut. A take has to be finished and have video before it can
  go in.
- **The ⋯ button, or right-click anywhere on a shot or take**, opens the context menu. It is
  the same menu in the bin, the timeline and the viewer strip.

### The context menu

Everything you do to a shot lives here:

| Item | What it does |
|---|---|
| **Render this shot** | Queue it with its current settings, on its backend |
| **Render with settings…** | The same, after changing model, LoRAs, steps, seed or target for this run |
| **New take like this one…** | Re-render from *this* take's exact settings, with a new seed by default. The one you will reach for most |
| **Cancel this render** | Stop a queued or running take |
| **Use this take** | Put it in the cut |
| **Play** / **Compare with…** | Open in the viewer; compare two takes side by side or with a wipe |
| **Play from here** | Play the cut starting at this shot |
| **Inspect shot** | The Inspector: target, overrides, refs used, refs missing |
| **Show in script** | Jump the Script window to that shot's lines |
| **Edit shot…** / **Add a shot after** | The shot form (below) |
| **Show missing refs (n)** | Which pictures this shot is waiting on |
| **Discard take…** | Move a candidate to `_trash/` — nothing is deleted, but the bin stays readable |
| **Show details** / **Copy path** | The take's sidecar, and its file path |
| **Generate first frame** / **Clear keyframe** | Make (or drop) this shot's opening still |
| **Use previous shot's last frame as first frame** | Continuity: chain this shot onto the one before it |
| **Use this frame as the next shot's first frame** | The same, pushed forward |
| **Lock in the cut** / **Unlock** | Freeze a clip so it can't be moved, trimmed or re-picked |
| **Audio from…** | This clip's picture with another clip's (or a file's) sound |
| **Move left / right in the cut** | Reorder (`Alt+←` / `Alt+→` in the timeline) |

### Editing a shot

**+ Shot** in the Shots toolbar adds a shot after the selected one; the pencil (or
**Edit shot…** in the context menu) opens the selected one. The form is the shot's lines
in the script as fields:

- **Shot**: its id, in the script's own numbering (between sh010 and sh020 a new one is
  sh015), and for a new shot the sequence it goes in, or a new sequence with its location.
- **Who's in it** and **With**: picked from the cast in the series config, in order; **+
  Character** / **+ Prop** opens a new cast card.
- **Size**, **Length** (H3's grid, or auto to fit the dialogue), **Background** (another
  location than the sequence's).

Wherever the form (or the wizard, or the series settings' cast list) names someone or
somewhere, it shows their picture: a character's face, cut from the last panel of their
sheet (a whole body doesn't read that small), a group's or a prop's whole picture, a
location's plate; initials until there is one. **add…** and the location buttons open the
pictures to pick from, and pointing at a name shows it larger.
- **What happens**, **Dialogue** (a row per line: speaker, on screen / V.O. / O.S., how
  it's said, the words), **Camera** (type it, or build it from H3's moves), **Sound**,
  **Extras**, **On-screen text**.
- **More** (the arrow): music, a different video model, continuity, first and last frames
  (the default, generate, import, none, or **a picture you have…**, picked in the folder
  browser and kept relative to the episode), the audio policy, pace, profile, steps, and
  the LoRA and model file, each picked from what the shot's model can load.

Beside the fields is what will render on the current pass, compiled as you type: the
model, size and frames, the dialogue's pace against the shot's length (with how long it
needs when it's tight), the build's warnings for this shot, and the prompt the model is
told. **Save** writes only this shot's lines into the script (keeping its comments and
any line the form doesn't know), with a history copy, and rebuilds. **Save and render**
then queues a take on the current pass.

### Editing a prompt

**Inspect shot** is where a shot's prompt, seed, model, LoRAs and steps are edited, per
pass. Save, then render it — the Inspector has two buttons for that:

| Button | What it does |
|---|---|
| **Queue (new seed)** | queues another take immediately: the saved override and a new seed, no dialog ("Render" when the shot has no take yet) |
| **New take…** | opens the settings dialog first — model, LoRAs, steps, seed, target, note, keep the frames |

> **Don't edit while that shot is rendering.** A finishing render refreshes the panel and
> your unsaved edit goes with it. Let the take finish (or cancel it) first.

Story edits — action, camera, dialogue — belong in the **Script** window instead, not in an
override. **Promote** moves overrides that the authored files can express back into them.

### Rendering one shot on another model

The render and redo dialogs have **Target for this run**: a one-off, sent with the render,
leaving the shot's own target alone. Under it, the size and length are **that target's, for
this shot** — not a preset. That matters because a target's frame grid decides the length: one
shot came out 448×256 at 124 frames on H3, 448×256 at 129 on LTX and 640×352 at 125 on Wan.
The dialog asks the server for the real numbers (P9), so what it prints is what you get.

An override you set on the shot doesn't travel: overrides belong to a target, so a one-off run
on another one uses that target's own defaults. The Inspector says the same thing the other way
round — when a field is overridden it shows **Built: steps 4 · model …**, what the build
compiled, so you can see what you have changed it from.

### Noting what's wrong with a pass

A proxy pass exists to show you structure: what happens where, and what is wrong. **P10** gives
that review a notepad — `<episode>/_issues.json`, filled while you watch and emptied when the
problems are fixed.

**While you watch:** press **n** (in Play all it notes the clip on screen and pauses; otherwise
the selected clip), or right-click a clip and choose **Add issue…**.
A small box opens with the shot and the take it is about; type a sentence and press **Enter**
(Shift+Enter for a second line). `i` and `o` are still trim-in and trim-out at the playhead, as
in any NLE, which is why the note key is `n`.

**The note button** (a speech bubble) in the Shots toolbar shows how many are open and opens
the list, where
**Copy export** puts the whole document on the clipboard for an assistant, **✕** resolves one,
and **Clear addressed** empties the ones whose shots you have already fixed. A clip with open
notes shows the same speech bubble in the timeline.

The same thing from the command line:

```
seriesmith issues Shows\ep05 --proxy --add sh0140 "Kell enters from the wrong side"
seriesmith issues Shows\ep05 --proxy --add-from notes.txt    # one "sh0140: …" per line
seriesmith issues Shows\ep05 --proxy                         # the list
seriesmith issues Shows\ep05 --proxy --export                # one document to paste
seriesmith issues Shows\ep05 --clear --addressed             # empty what is done
```

Each note **snapshots what produced the take**: the script's lines for that shot, the prompt the
pipeline compiled from them, the reference pictures it used, and the rendered file. That is
deliberate — the note is about the shot *as it was rendered*, so when you paste the export into
an assistant it sees what actually caused the problem, not whatever the script says after you
have started editing. Editing the script later never rewrites a note.

A shot that has since been rebuilt or re-rendered reads **(addressed)**. Nothing is deleted for
you: `--clear --addressed` empties those when you are satisfied, and an episode with no issues
has no issue file at all.

### Flagging clips to come back to

A note is for an assistant: it snapshots the script and the prompt so the script or series
config can be rewritten. When you only want to remember a clip, to re-render it or change its
prompt yourself, **flag** it instead. In Play all, press **M** to flag the clip on screen.
Playback keeps going, so you can flag clips in one pass through the cut. Press **M** again on a
flagged clip to clear its flag. Outside Play all, M flags the selected clip; the clip's menu has
**Flag to come back to** too.

A flagged clip has a pink flag in its corner, and the timeline's header counts them. Click the
count, or press **Shift+M**, to go to the next one. A flag changes nothing that is played or
exported. A locked clip can still be flagged. Each pass's cut keeps its own flags (in
`cut.json`), and Ctrl+Z undoes a flag like any cut edit.

```
seriesmith cut Shows\ep05 --proxy --flag sh0140      # --unflag to clear; --show lists them
```

### Keeping a take's frames

**New take like this one…** (and the Inspector's **New take…**, which is the same dialog) has
**Keep the frames (PNG sequence)**. It writes every frame of that take beside its mp4:

```
<episode>/renders[_proxy]/<shot>/frames/<shot>_t<NN>_000000.png …
```

For a shot that is right but for a frame or two: retouch those PNGs and re-encode the
sequence yourself. It costs ~2.5 s a shot and a few hundred MB a take, so it is per render
rather than a setting — the one-click **Queue (new seed)** never keeps frames.

A render is reproducible, so you can also fetch the frames of a take you already like:
re-render it with **that take's seed** (New take… → seed *same*, or type it) and tick the box.
Verified 2026-09-22 on this machine — two renders at one seed gave byte-identical frames and
mp4 — but it is worth confirming after a ComfyUI or driver update before you rely on it.

### The graph a model renders with

Each target renders a ComfyUI workflow, and **What's missing** (the model status window)
shows which copy of it is in force, per target:

| It says | What that means |
|---|---|
| **repo** | the graph seriesmith ships, in `targets/<kind>/<id>/workflow.json` |
| **ComfyUI** | a workflow of that name is saved in this ComfyUI, and it wins |
| **$VAR** | that environment variable points at a file, which beats both |
| **edited here** | the graph in force isn't the repo's — ignoring everything a render
  patches anyway (model, LoRAs, prompt, size, seed, the episode's folder) |

To change how a model renders, press **Copy to ComfyUI**: the repo's graph is written into
ComfyUI's workflows under the name the target looks up. Open it on the canvas, change what
you like, save — from then on your saved copy is what that target renders. Your own graph
works the same way: save it in ComfyUI under that name (What's missing shows the name, with
a copy button). **Revert to the repo's copy** deletes the saved one and puts the shipped
graph back; it never touches an environment variable.

What a render sets per shot stays out of your hands: the prompt, size, length, seed, model
and LoRAs are written into the graph at queue time, so editing those widgets on the canvas
changes nothing. Everything else — samplers, extra nodes, upscalers, how the picture is
built — is yours.

From the command line: `seriesmith targets` prints the same per-target line, and
`--install-workflow <target>` / `--revert-workflow <target>` are the two buttons.

### Your own model, from your own workflow

A workflow that isn't a variant of one seriesmith ships can become a model of its own, for this
show, without touching the repo. Save the graph in ComfyUI, then in **What's missing** →
**This show's own targets** → **Add a target from a workflow…**:

1. **Pick the workflow and press Read it.** seriesmith works out which widget takes the prompt,
   the negative, the size, the length, the seed, the steps, the sampler and each model file,
   which node saves the video, whether the graph makes sound, and where a keyframe goes.
2. **Answer what no graph can state.** A name; the frame grid (`step`, `base`, longest); the
   size multiple; fps; whether the model makes sound; whether dialogue is spoken or acted
   silently. Anything ambiguous — two nodes that could take the same value — is a list to
   choose from, or title the node in ComfyUI and read it again.
3. **Save as a draft.** It lands in `<show>/targets/<id>/target.json`, beside series.json.
   It travels with the show and survives updating seriesmith.
4. **Probe render, then enable it.** The probe queues the episode's first shot on it at the
   proxy pass. Look at the take: a wrong frame grid stutters, a missing file is reported.
   When it looks right, **Enable for shots** — until then the shot and episode pickers leave
   it out, so a draft can't quietly become the episode's model.

What it can do: prompt, size, length, seed, steps, model and LoRAs per shot, plus one first
keyframe. What it can't, yet: subject reference sheets (character identity), which stay a
repo target's job. `seriesmith target-from-workflow <workflow> [<episode>] --save` is the
same thing without the UI.

## Refs

Used heavily at the start of a series and rarely afterwards, if the references come out
right. Every character view, prop, plate, voice and shot keyframe the series config and
script call for is listed here.

- **+ Add** at the top adds a character, group, prop, vehicle, location or voice to the
  series config, on its card (as a group's **+** does).
- **Click a ref** to expand it; **double-click the ref's row** to open its live file — a
  character's stitched sheet, a prop, a plate — in the viewer.
- **Double-click a candidate** (one of the four view images) and it opens against the live
  one, for comparison.
- **Right-click is your browser's menu here**, not the editor's context menu. The Refs tab
  has buttons instead.
- **Expand the prompt** (it shows the series config's wording) to edit it, change the
  model, add LoRAs, or change the seed and steps. Settings above the views are shared by
  all four; the prompt is per view.

### Making references

- **Generate** makes candidates. The view selector and the count beside it decide which
  view and how many, each with its own seed — **you do not have to redo all four views.**
  If only the back view is wrong, regenerate the back view.
- **Import…** takes an image from the machine `seriesmith serve` runs on, and you can drag a file onto a slot
  or use Upload. Hand-made and externally generated references are the expected case; the
  generators are the fallback.
- **Generate missing** fills everything the episode needs in one go. It does the pictures —
  **not the voices.** Generate a voice from its own ref row.
- **Clear** unpicks a ref; **Discard** bins a candidate.
- A character's sheet is stitched automatically once all four views are picked — or you
  supply a finished one, below.
- **A view's settings vs the character's.** Seed, model, LoRAs and steps set on a character's
  row are shared by all four views; open a view and its editor says which of the values on
  show it inherited ("Its steps come from Ada and are shared by all four views"). Change one
  there and it becomes that view's own; **Remove this view's own settings** drops only those
  and leaves the character's. A view's prompt has the series config's wording behind it, so
  **Diff** shows what you changed and **Series config** puts it back.

### References you already have

Three routes, and all of them are supported:

1. **Copy the file into the folder** `series.json` names. This has always worked and still
   does: the build counts it, renders read it, and if you replace it later the takes that
   used it go `stale: ref` so **Re-render stale** offers them. The row says the live file was
   "put there outside the editor", which is not a complaint — it means there is no candidate
   behind it to compare or go back to.
2. **Drop one file on a slot** (or **Upload…**). A prop, a plate, a voice, a keyframe, one of
   a character's four views — and, since P8, **a character's row takes a whole 4-panel
   sheet**: drop it there, or use **Upload sheet…**. It becomes a candidate and goes live
   without being stitched, so a second one can sit beside it and you can switch between them.
   Picking all four views afterwards stitches over it; the row always says which of the two
   the live file came from.
3. **Drop the whole lot on the Refs tab** (or **Supply files…**, which also takes a folder).
   Every file is matched to a slot by its name and you get the table *before* anything is
   sent: what goes where and why, and what was left alone with the reason. Press **Supply n**
   and they upload one at a time, each going live. Nothing is guessed — a name that could
   mean two slots, or two files wanting the same slot, are listed as left alone for you to
   rename.

Names are matched against the file each ref already names in the series config
(`walker_sheet_4panel.png`), the ref's id (`walker.png`), a view's tag or word
(`walker_02_side.png`, `walker_side.png`), a plate (`highway_dawn.png`, `bg_highway_dawn.png`)
and a voice (`walker.wav`). A trailing `_v2` or `_final` is ignored. The extension decides
between a picture and a sound, so `walker.png` is the sheet and `walker.wav` the voice.

`seriesmith supply <episode> <folder> --dry-run` prints the same table from the command
line, which is the quickest way to fill a show whose pictures are already on disk.

You can also paste an image onto a slot with Ctrl+V.

### Sharing refs between episodes

With one `refs` folder beside the episodes, a ref's **live file is the whole show's** — in a
real series that is every ref, so the editor does not badge them all as "shared". What it
tells you instead is when the file that is live *isn't your episode's doing*:

| On the row | What it means |
|---|---|
| **from ep03** | ep03's pick wrote the file that is live now |
| **not from here** | nothing has a candidate for it: it was copied in by hand, or replaced outside the editor |

**Generating candidates never touches it.** Candidates are private to the episode, and the
one automatic pick only happens for a ref with no live file at all. So regenerate freely — it
is picking, uploading, supplying and clearing that the other episodes feel.

You get a confirm when:

- **you pick over a file another episode picked.** Their pick loses and their takes go
  `stale: ref` — they can re-pick their own take to get it back.
- **you pick over a file nothing has a candidate for** (the "not from here" case). There is no
  copy anywhere: this one is gone for good, which is why the wording is blunter.
- **you clear, or discard the take that is live, on a shared file.** That *deletes* it, and
  every episode that needs it is blocked until something is picked again — so this one asks
  whoever owns it.

Picking over your own episode's pick says nothing, which is the case you are in all day while
making refs. On the command line, `seriesmith/kreagen.py --clear` refuses a shared live file unless you
pass `--yes`.

### Choosing a model

The target picker sets which image model generates. They are not interchangeable:

| Target | Reads references? | Notes |
|---|---|---|
| `krea2` | No | Text to image. The default, and it holds a character across four views well because they share one seed |
| `z_image_turbo`, `flux2_klein` | No | Text to image |
| `flux_kontext` | One | The only edit target that takes a negative prompt |
| `flux2_klein_edit` | Up to 4 | The default for keyframes when installed |
| `minimax_h3_still` | Up to 9 | The video model rendering 5 frames and keeping the first |
| `qwen_image_21` | Up to 16 | Text to image *or* an edit, decided by whether there is anything to edit from. The only one with a usable cfg, scheduler, denoise and negative prompt |

`seriesmith targets --kind image` says which are installed.

### Wardrobe variants

A subject with `of:` in the series config is the same character in different clothes, with
its own sheet ([AUTHORING.md](AUTHORING.md), "A wardrobe change is a new subject"). How its
views are made depends on the model:

- **On an edit model** (`qwen_image_21`, `flux2_klein_edit`, `flux_kontext`,
  `minimax_h3_still`) each view is generated **from the character's own matching view** —
  the towel's back panel is an edit of their back panel.
- **On a text-to-image model** there is nothing to edit from, so it draws the variant from
  its `design` **on the character's seed**. Closer than a fresh draw, but not the same
  thing.

**Order matters.** A whole pass plans every job before anything is picked, so in the first
pass a variant has nothing to edit from and comes out cold. Run the pass, let the
character's views pick, *then* regenerate the variant. To check which happened, select the
candidate and read the **drawn** row: `edited from Dana (three-quarter)`, or `from the
prompt alone`.

## Importing a series

**Import series…** (Shots, beside the project folders) brings a whole season in at once:
pick the scripts (`Files…`) or a folder of them (`Folder…`), with one series config for the
lot or one per episode (a `series.json` beside a script, or named after it). Each script
becomes an episode folder under the show you choose, named from its header; the import
says which went in and why any didn't (a script with no header, a config that doesn't
build it). Then build and render them as any other episode.

## Where shots render

Every render, reference, voice, upscale, post and tour is a **job**, and a job runs on a
**backend**: `local` (your own ComfyUI, through comfy-api-proxy), `cloud` (Comfy Cloud),
`deployment:<target>` or `router` (a hosted model). The Render dialog's **Render on**
row picks one for that request (every backend this machine is set up for, a greyed-out one
not answering); left at **each shot's own backend**, a shot uses its own (an override), the
episode's, the series config's `series.backend`, else its target's first. A hosted target
(Seedance, Krea 2 on Router) only runs on `router`; a shot sent somewhere its target can't
run says so in its error ([SETUP.md](SETUP.md) sets backends up). The take's record says
where it ran.

## Jobs

The **Jobs** button (top right) shows how many jobs are queued and running; it opens the
queue:

- One lane per backend. Your own ComfyUI runs one job at a time; a cloud backend several.
- Each job shows what it is (`ep02 sh140 t03`, a ref view, an upscale, a tour), its
  progress, and its log (where it ran, what it held or started from, how it ended).
- **Cancel** stops a running job or takes a waiting one off the queue (its take is marked
  failed, `canceled`). **Earlier** / **Later** reorder a waiting job; a lane can be
  **paused** (**Pause** / **Resume**), which lets the running job finish and starts nothing
new.
- **Again** runs a finished job once more, as a new take with the same settings.
- A job that waits for another says so: a `continuous:` shot waits for the shot it
  continues, a post for its upscale.

The queue lives in the server: closing the page leaves it running, and reopening it shows
where things are. Stopping `seriesmith serve` drops what hasn't run; those takes are marked
failed the next time the episode is opened.

## Settings

**Settings** in the top bar is this machine's own, never the series': the **Comfy API key**
(from platform.comfy.org; it turns on Comfy Cloud and Comfy Router, and paid use is billed
to that account), the Cloud address, where your **ComfyUI** and **comfy-api-proxy** are,
and **deployments** (a model built into a Comfy deployment of its own, which then shows in
**Render on** as `deployment:<model>`). Saving applies at once. They live in
`%APPDATA%\seriesmith\settings.json`; a value the environment sets (`COMFY_API_KEY`, ...)
wins and shows as such.

## The viewer

Docked in the middle of the page: the selected shot's takes (step with `←` `→`, compare two
**side by side** or under a **wipe**, **Play all** for the cut), a ref's candidates, a
location's tour (keep any frame as a hold), and a 360 in its own viewer. Drag its tab out to
float it, or dock another window beside it.

**Play all** has its own **Loop** (the cut starts over at the end; remembered).

**Full screen** (the button by Close, or `F`) puts the viewer on the whole screen, its
controls with it; `F` or `Esc` brings it back. The sidebar's right edge and the timeline's
top edge drag to resize the panes (double-click one to put it back); the sizes are kept
in this browser.

## The timeline

The cut as an editable track, along the bottom of the page.

- **Drag a clip** to reorder it; **drag its edges** to trim frame by frame.
- **Double-click** opens the clip; **right-click** is the same context menu as the bin, so
  everything above — new takes, keyframes, locking, audio — is available here too.
- **Ctrl + wheel** over the track zooms.
- **Turn on the waveform lane** to see the audio under the cut. Useful with a recording
  attached.
- **Export** assembles the mp4; **Play all** watches it straight from the takes without
  assembling anything.

Setting a shot's keyframe from its neighbour is how you make a cut continuous: use the
menu's **Use this frame as the next shot's first frame** on the take you like, and the
next shot starts where this one ended.

### Keyboard

These work while the timeline or Play all has focus, and never while you are typing in a field:

| Key | What |
|---|---|
| `Space` | Play / pause the cut |
| `J` `K` `L` | Shuttle back / pause / forward |
| `I` `O` | Trim the head or tail at the playhead |
| `N` | Note what is wrong with the clip (the one on screen in Play all) |
| `M` | Flag or unflag the clip to come back to (the one on screen in Play all) |
| `Shift+M` | Go to the next flagged clip |
| `Alt+←` `Alt+→` | Move the selected clip in the cut |
| `Ctrl+Z` / `Ctrl+Y`, `Ctrl+Shift+Z` | Undo / redo the cut |
| `Ctrl + wheel` | Zoom the track |
| `←` `→` | Step candidates, in the Viewer |
| `,` `.` | Step a frame back / forward, in the Viewer |
| `Escape` | Close a menu, or cancel a drag |
| `Ctrl+S` | Save, in the Script and Series config windows |

## Where it all lands

Everything the editor does is a file in the episode folder, and the command line does the
same things to the same files: `overrides.json` (prompts, seeds, models, targets),
`cut.json` (order, trims, locks, flags, per-clip audio), take sidecars beside each render, and
`_history/` copies of the script and series config each time you save. Nothing is hidden in
a database, and nothing is lost — a discarded take moves to `_trash/`.
