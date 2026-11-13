# Dailies: takes reviewed by a vision-language model

Status (2026-11-12): **the notes and their history are built** (checklist 1), and **the count
check** (checklist 9); **the VLM review is set aside** (see "Set aside" below). This file is the design record
and the checklist; the contracts go in the docstrings, `docs/API.md` and `docs/EDITOR.md` as
they are built.

## Set aside: the VLM review (2026-11-12)

The bake-off and the tests after it (below) show where a local VLM (Qwen3.5-27B, 4-bit) helps
and where it doesn't:

- **reliable** on problems that appear at a moment: a cut, a change of place, a morph, an overlay;
- **mostly noise** on action, camera and lip sync (hence the strict rule);
- **blind** to a malformed body present from the first frame, unless given stills, and then
  with false flags;
- **never tested** on the lattice, the worst problem seen so far, whose cause turned out to be
  the Ref2V turbo LoRA meeting thin lines in a reference (fixed by a model, `h3_hybrid`, not by
  a review).

What a person watches for, acting and how people play off each other, is where it is weakest.
So the review (checklist 3-8) waits for a stronger model. What goes ahead without it: a
person's notes filed by category, with their history (checklist 1, done), and the **count
check** (people and faces against the script), which caught every extra-person take it was given
with no false flags, on CPU (checklist 9). The design below stands for when the review comes
back.

## Why

Watching every take of an episode is what tires a person out first. The take checks
(`takecheck.py`) catch what a signal can see (a cut it wasn't asked for, words dropped), and
miss what needs the picture understood: a place that drifts into another during one camera move
(FastH3 sh020, seed 1002), a morph (LAST LIGHT sh220 t03, 0.35-0.78 s), a person who isn't the
one in their picture, an action that never happens. A vision-language model (VLM) running on
this machine can watch each take against what it was asked to be and write notes on it. The
bad takes then sink before a person watches, and the notes are kept, so problems that keep
coming back show up as patterns in the script, the series config or a model.

A review is a reason to look, never a verdict: it picks nothing, deletes nothing, and never
changes the cut.

## What it does

**One take**, on demand: a clip's menu **Review this take**, or
`seriesmith dailies <episode> --shot sh0140 [--take N]`.

**A batch**, after the renders: the Render dialogs' **Review the takes when the batch is done**.
A step waits until every render in the batch has finished, and so has every retry those renders
started (the retry ladder runs first, untouched). Only then are the reviews queued, one job per
take on the same lane. The video model and the VLM therefore each load once, and never take
turns on the GPU. `seriesmith dailies <episode> [--proxy | --final]` does the same for every
take of a pass that hasn't been reviewed, for takes rendered before this existed.

Which takes a batch reviews: **one per shot**, the newest take the batch made for it that
passed its checks (after the retries, that's the one the ladder stopped on). A shot whose
takes all failed their checks is already flagged, and isn't reviewed. A shot's other takes can
still be reviewed one at a time. Later, maybe: when the reviewed take is a `reject`, review the
shot's next passing take from the batch.

## What a review sees

Everything about what the take was asked to be. Each part is labeled for the model, never given
as one mixed paragraph:

- the shot's script lines and its compiled prompt, split into parts (who, action, camera, place,
  lines);
- the reference pictures the render used, each named by role (a cast member, a location plate, a
  keyframe). These are the ones the take's sidecar records (`refs`: path and sha1), not the
  ones the shot points at now. A picture replaced since the render (its sha1 no longer matches)
  is left out and named in the review, so a take is never judged against a plate it never saw;
- the take itself, all of it: a 3-5 s take at 8-12 fps and about 480p is 4-10K tokens (the
  bake-off settles the frame rate);
- the take's check results, so the model doesn't redo them.

## What a review says

Each criterion gets a verdict on its own, rather than one score for the whole take. Recorded in
the take's sidecar under `dailies`:

```json
{
  "version": 1, "target": "qwen3_vl_32b", "when": "...",
  "source": {"size": 0, "mtime": 0},
  "video": {"fps": 8, "width": 848, "height": 480},
  "verdict": "ok | flag | reject",
  "findings": [
    {"criterion": "adherence | continuity | reference",
     "category": "morph",
     "verdict": "flag", "confidence": 0.8,
     "at": [0.35, 0.78],
     "about": "action",
     "note": "the hand becomes a second cup between 0.4 and 0.7 s"}
  ],
  "summary": "one line"
}
```

- **adherence**: one finding per prompt part (did the action happen, is the camera move the
  one asked for, is it the place asked for);
- **continuity**: anything that changes in a way nothing in the picture explains, with its span
  (`at`);
- **reference**: one finding per reference picture (wardrobe, props, place).

**Categories**, one fixed list, so notes can be counted:

- `identity`: the wrong face or person;
- `wardrobe`: clothes or props unlike their reference;
- `place`: a setting unlike the plate, or something appearing from nowhere;
- `light`: light or look unlike the prompt or the plate (a relit plate's snow against a neon
  prompt; a light with no source);
- `morph`: a shape changing, or a body malformed (an arm from the chest, a hand becoming a cup);
- `artifact`: the render itself breaking (lattice, lines growing from an edge or a reference's
  shape, blur or smears over part of the frame, an overlay): a model or settings problem, not
  the script's;
- `action`: the action not as written;
- `camera`: the move or framing not as written;
- `count`: too many or too few people or things;
- `cut`: a cut inside the take;
- `lipsync`: the mouth against the speech;
- `text`: lettering in the picture;
- `performance`: the acting (delivery, reactions, how people play off each other): a person's
  category, since what a person reviews for is mostly this;
- `other`: whatever fits none of the rest.

The list is `issues.CATEGORIES`, served at `GET /seriesmith/issues/categories`. A note may also
be left without a category.

`performance` was added when the review was set aside (2026-11-12). `light` and `artifact` were
added after the bake-off (2026-11-12): its overlay (sh1130) went to
`other`, a relit plate's look against its prompt (sh130, sh140) to `place`, and Porchlights'
lattice-and-blur takes (sh1460, sh1470, sh1495, sh1590, sh1610) had nowhere to go. The
criterion once called `artifact` is `continuity`, so the two words don't clash. Labeled cases of
`identity` and `text` are still wanted (the user has some to dig up).

**Stale**, as an effects take is (`fx.py`): when the take's mp4 has changed since it was
reviewed (its size or mtime), the review reads stale and is ignored.

**Shown**: a badge in the bin and the gallery, as the checks' badges are. A `reject` sinks the
take to the bottom of its shot's takes; nothing else changes, and a take the cut already plays
is never swapped.

Telling faces apart is where VLMs are weak. A face-embedding check (the take's faces against the
cast member's picture) may join later as a check of its own (`takecheck.register`); the VLM's
`identity` findings stand until then.

## The notes and their history

Today's issues (`issues.py`, `<episode>/_issues.json`) are a notepad meant to be emptied:
`resolve` and `clear` delete, and the file goes when it's empty. That stays how the editor's
notepad behaves. What changes:

- **Kept**: a note that is resolved or cleared is appended to the show's history,
  `_history.jsonl` beside `series.json` (only ever added to, one note a line), first stamped
  with how it ended: `rebuilt` (the shot's script or the series config changed), `rerendered`
  (a newer take), or `dismissed` (resolved by hand with nothing changed).
- **`source`** on every note: `human`, `dailies` (the VLM) or `check` (a take check).
- **`category`** on every note, from the list above: the **Add issue…** box has a dropdown
  of the same categories the VLM picks from (one list in the code, served to the editor and
  written into the VLM's instructions, so a person's notes and the model's count together).
  It may be left empty; the pattern pass below fills it in then. `seriesmith issues --add`
  takes `--category`.
- **A review's flags and rejects become issues** with `source: dailies`, one per finding, and
  carry the same snapshot as a person's note (script, prompt, refs, seed, take). The existing
  **Copy export** to an assistant therefore covers them unchanged. The notepad can show only
  your own notes, only the VLM's, or both.

Both pieces are useful before the VLM exists: your own notes start building the history now.

Built (2026-11-12): `issues.CATEGORIES` and `SOURCES`; `add(..., category, source)`;
`how_addressed` (`rebuilt`, `rerendered` or None) stamps each note `resolve` and `clear` drop,
appended to `_history.jsonl` (`history_path`: beside `series.json`) before the notepad is saved,
so a note is never in neither; `history(ep, episode, category)`; the note box's **Category**,
the list's **Show** filter (category, and source once there's more than one); `seriesmith
issues --category` and `--history` (the history, counted per category and ending). Not built
yet: the export's view of the history for an assistant (the MCP `history` tool, item 7).

## Patterns, and the script-writing skill

This part runs outside seriesmith. An LLM client reads the history over MCP and groups it by
category, target model and the shot's features (size, camera, how many people, which
references). Out come proposals such as "H3 Ref2VA loses identity in two-person close-ups;
fixed 4 of 5 times by a script change, never by a reroll". Each proposal lands in one of three
places:

- **AUTHORING.md**, which is where the skill and `prompts/` come from (`tools/make_prompts.py`);
- **`seriesmith check`**, as a warning, where the pattern can be checked before a render;
- **a target's prompt writer**, where one model needs something said differently.

What fixed a note (`rebuilt` or `rerendered`) is what tells these apart. A problem a script edit
fixes is one the writing skill can prevent; a problem only a reroll fixes is the model's luck,
and goes into the retries.

MCP tools: `dailies_review` (one take, or a pass), `dailies_of` (a take's review), `history` (the
show's notes, filtered by category, target, source and date).

## Where the model runs

**On ComfyUI, as every other model does.** A new target kind, `vision`, beside `foley` and
`ambience`: `seriesmith/targets/vision/<model>/` with its `target.json` and `workflow.json`. The
take goes up as a file (as an effects take's picture does), and the JSON comes back as text.

- Torch, transformers and the weights stay in ComfyUI's Python. Nothing new goes into
  `requirements.txt`, and nothing is installed at runtime. The Features window installs the
  weights.
- The queue already orders the GPU's work, and ComfyUI loads and unloads the models between
  jobs.
- A better VLM is a new target, not new code, so the bake-off can run again whenever one comes
  out.
- The node: an existing VLM node pack only if it takes the take as video (timestamps, with
  frames grouped in time). If it only takes frames as separate pictures, the node is ours, in
  `comfy_nodes/` (as `mrt2.py` is).
- Output as JSON is the node's job (a grammar or a schema, if the runtime has one), with one
  retry on JSON that doesn't parse, then `failed`.

The kind isn't called `review` because "the review cut" (`assemble`'s export) already uses the
word.

## The bake-off (first, outside the repo)

A throwaway script in the scratchpad: transformers in a venv of its own, nothing committed.

- **Models**: Qwen3-VL-32B at 4-bit; Qwen3.5 at whatever size fits in 32 GB, if it reads video;
  Molmo2-8B.
- **Frame rates**: 8 fps and 24 fps, at about 480p.
- **Takes**: the known misses (FastH3 sh020 seed 1002, LAST LIGHT sh220 t03); a dozen clean
  takes from the 213 the checks were measured on; a few that miss their prompt (a wrong action,
  a camera move that isn't the one asked for); and a person who doesn't match their picture.
- **Measured**: which misses each one catches, false flags on the clean takes, seconds per take,
  peak VRAM, and whether the JSON parses.

The winner and its frame rate become the first `vision` target; the numbers go into this file.

### Results (2026-11-11, RTX 5090, transformers 5.22)

Sixteen LAST LIGHT final takes:

- four known misses:
  - sh010 t1, a building appearing from nowhere (place);
  - sh040 t1, a cut into the character sheet's background (reference);
  - sh080 t1, the buildings too close (place);
  - sh220 t3, the morph at 0.35-0.78 s;
- twelve clean takes: the cut's takes with no note, *presumed* clean.

The Qwens ran at 4-bit (bitsandbytes NF4, vision tower left at bf16), the take at 360p and the
reference pictures at 448 px. Above that, the vision encoder's masked attention (the math SDPA
kernel, quadratic in patches) ran out of 32 GB. Thinking was off, and decoding was greedy.

| Model | Misses caught | Category right | Clean takes flagged | JSON | s/take | Peak GB |
|---|---|---|---|---|---|---|
| Molmo2-8B, bf16, 8 fps | 3/4 | 0/3 | 8/12 | 15/16 | 24 | 19.0 |
| Qwen3-VL-32B, 4 fps | 3/4 | 2/3 | 1/12 | 16/16 | 133 | 26.1 |
| Qwen3-VL-32B, 8 fps | 3/4 | 2/3 | 2/12 | 13/16 (3 out of memory) | 132 | 30.3 |
| **Qwen3.5-27B, 4 fps** | **4/4** | 3/4 | 5/12 | 16/16 | 123 | 20.8 |
| Qwen3.5-27B, 8 fps | 4/4 | 3/4 | 9/12 | 16/16 | 123 | 24.8 |

**Re-scored, counting the two the review found as misses.** sh130 t02 and sh140 t02 were
labeled clean, and the review flagged both. Their plate had been relit as snow, the prompt still
asked for neon, and the background may swing between the two. It may also be lightning against a
dark plate: unconfirmed, and to be checked against the plate. With both counted as misses, there
are six misses against ten clean takes. "Strict" means the take's verdict
comes only from its continuity and reference findings, at confidence 0.8 or more; its adherence
findings are kept as notes.

| Model | Plain: caught | Plain: clean flagged | Strict: caught | Strict: clean flagged |
|---|---|---|---|---|
| Qwen3-VL-32B, 4 fps | 4/6 | 0/10 | 3/6 | 0/10 |
| Qwen3-VL-32B, 8 fps | 4/6 | 1/10 | 4/6 | 1/10 |
| Qwen3.5-27B, 4 fps | 5/6 | 4/10 | 4/6 (sh130, sh140 missed) | 2/10 |
| **Qwen3.5-27B, 8 fps** | 6/6 | 7/10 | **6/6** | **2/10** |

What the results show:

- **Only Qwen3.5 caught sh010.** At 8 fps it reported "a large dark roof structure morphs into
  existence" at 0.18-0.43 s. Both Qwens put sh040's cut and sh220's change of place within
  0.1-0.3 s of the real span.
- **Molmo2 is out.** Its flags are adherence complaints that miss the actual problem. It can't
  take pictures and a video together, so the references go in as words only.
- **Most false flags are about adherence:** the script read word for word ("a single smash, not
  several steps", "stops mid-roof, not at the ledge"). Hence the re-scoring rule.
- **The review may have found two misses a person had passed** (sh130, sh140: a snow plate
  against a neon prompt, or lightning; unconfirmed). If it's lightning, Qwen3.5 at 4 fps strict
  (4/4 caught, 2/12 false) is as good as at 8 fps. Several other notes say the same of sh010 and sh080 ("the reference is a snowy
  daytime city, the take a rainy night"). That's a pattern of the kind the history is meant to
  surface: a relit plate whose look the prompt still contradicts. It could become a
  `seriesmith check` warning.
- **8 fps catches brief changes 4 fps misses** (sh130's 0.2 s of neon). The strict rule removes
  the extra noise that 8 fps brings.
- The two clean takes still flagged are wardrobe and prop readings: sh020's case "on the shoulder,
  not strapped across her back", and sh070's case "silver, not dark".

**Pick: Qwen3.5-27B at 8 fps, strict**: the take's verdict from continuity and reference findings
at confidence 0.8 or more, adherence as notes. On the 5090 that makes about 2 minutes a take,
about 3.5 hours for a 100-shot episode overnight, with a peak of 24.8 GB.

Two Porchlights ep02 takes, unlabeled, at 8 fps:

- **sh1130 t02** was rejected: "blue digital dots and lines overlay the entire scene" from 2.2 s
  (filed as `morph`, confidence 1.0; `artifact` on today's list). Everything else passed.
- **sh1210 t02** was flagged on adherence only: no push-in (camera), no lip movement for the
  whispered line (filed as `action`, not `lipsync`). The lip-sync flag is false (the lips do
  move).

  It missed what is wrong. Per the user: an arm coming out of his chest; unexplained blur either
  side of his head; a green light on frame right; lines coming out of the bed; and a bed and
  room unlike the plate (the plate is the one the take recorded, sha1 unchanged since). The
  model saw the blur and the light and called them "green bokeh". It rated the plate mismatch
  0.6.

  It was run again with a checklist (each limb where it joins the body, smears and lines around
  heads and edges, lights with no source, a whisper is speech), at 360p/8 fps and at 480p/4 fps.
  The result was the same: the arm read as "his hands raised near his face", the lip-sync flag
  still false, the plate mismatch 0.7. sh1130 stayed right at both, with no new flags.

**A stills pass** (same model, 4-bit): six frames of the full-resolution take (1344×768) as
still pictures, with the person and plate pictures. One question: what is malformed (bodies, merged
things, smears and lines, light with no source), with the plate as the comparison.

- **sh1210 t02** was rejected for the right reasons: "the right hand is malformed and merging into
  the chest/neck area" (morph 0.9, every frame; the user's arm from the chest), and a background
  unlike the plate (place 0.9). The blur and the lines from the bed weren't named on their own.
- **sh1190 t02** was rejected: two people in the bed (count 1.0). The user confirmed it: one man
  with two heads. The video pass caught it too.
- **sh1130 t02** was still caught (the overlay, filed as `other`).
- **sh110 t02** (LAST LIGHT, clean) was rejected: "gloved hands as amorphous blobs". It's a false
  flag (black gloves in the dark).
- **sh060** ran out of memory (about 7K tokens, 31 GB).
- Cost: 80-230 s a take on top of the video pass.

**Detectors, for comparison** (ComfyUI's own weights, CPU):

- **A count check:** YOLO people and faces per frame (Impact pack's `person_yolov8m-seg`,
  `face_yolov8m`, `hand_yolov8s`), against the shot's `who:` / `with:`. It caught sh1190 (2 faces
  for 1 cast member) and flagged none of eight clean takes, sh110's dark gloves included. It was
  blind to sh1210's arm. A cut to a street of extras (sh040) briefly counted 3 people. It also
  caught sh1420 t02 (a hooded third person swallowing Samir) and sh1510 t01 (two Emilys).

  It missed sh1570 t02 on its median. The script expects 4 (three cast and a nurse); per the user
  there are 5-6: a person behind Mills at 0.02 s who morphs into an old woman at 0.91 s and falls
  into a wheelchair at 1.41 s, then Mills duplicates at 3.64 s and Crane at 4.23 s. The frames
  peaked at 5 people and 5 faces, but the median frame read 4. **The rule:** more people or faces
  than the script has (`who:`, `with:`, `extras:`) for a run of frames (0.25 s or more), never the
  take's median.
- **DWPose** (`comfyui_controlnet_aux`, yolox_l + dw-ll_ucoco_384, 0.3 s a frame): it fitted
  sh1210's chest hand to a plausible arm from an off-frame shoulder, with all joints at 0.5-0.8 and
  normal bone ratios. A pose model fits the most likely skeleton, so a malformed limb is explained
  away. On sh1190 it put one face on one head and stretched an ear to the other; body confidence
  fell under 0.3 in 12 of 16 frames. That's a weaker signal than the face count. **Dropped.**

**What this shows:** the model catches problems that happen at a moment (a cut, a change of
place, an overlay appearing). It misses problems present from the first frame to the last (a
malformed body, a smeared background), where nothing changes to notice. Neither wording nor
resolution fixed it at 27B 4-bit. Where it's heading:

- **three layers**:
  - a count check (people and faces against the script; a take check, `takecheck.register`);
  - the video pass, for problems at a moment;
  - the stills pass, for bodies and the plate;
- the stills pass's false flags (dark gloves) are the next thing to fix: try a bigger model at
  full precision (a machine with more memory) before anything else;
- letting reference findings count from 0.7.

**The lattice takes, looked at (2026-11-12).** sh1460, sh1470, sh1495, sh1590 and sh1610 were
made with the same settings as the other 520 or so H3 Ref2VA takes of ep02 (int8, the 8-step
turbo LoRA, 1344×768, a character sheet and a plate), and their references are clean. What they
share:

- **Thin lines across the chest**: Denise's stethoscope and a phone's cord, Crane's lanyard and
  earpiece wire. In the takes, those lines are multiplied into a mesh or a diamond lattice over
  the clothes (sh1460, sh1470), or into gold loops on the jacket (sh1590, sh1610). sh1610 also
  has a checkerboard over the walls, likely the ceiling's tile grid spreading.
- **Close framing**: four of the five are CU or ECU (about a quarter of the episode is). sh1495,
  an ECU of a hand past the stethoscope, is a smear rather than a lattice.
- **The same seed twice**: each shot's second take kept its first take's seed (`same`) after a
  script change, with the same references, and came back with the same lattice. So the script
  edit didn't fix it. Whether a new seed would is untested.

**Tried on sh1460 (2026-11-12, local, a scratch copy of ep02):**

| Take | Lattice |
|---|---|
| the original seed, turbo LoRA, 8 steps | yes, as before |
| two new seeds | yes, both |
| the sheet's face panel only (`--panel-mode face`) | yes |
| Denise's sheet without the stethoscope | mostly gone (a patch on the sleeve by the phone cord, a smeared wrist) |
| **no turbo LoRA, 20 steps (res_multistep)** | **clean** throughout, the stethoscope drawn right (116 s against ~60 s) |

So the lattice is the Ref2V 8-step turbo LoRA turning a thin line in the reference (tubing, a
cord, a lanyard) into a texture; a new seed doesn't help. The fix for an `artifact` finding on
a Ref2VA turbo take is that take again without turbo. FL2VA doesn't show it (other weights,
the FL2V LoRA).

Singularity (`Minimax-h3_Singularity_ref2va_v2`) is a modified Ref2VA, not an FL2VA hybrid: of
932 tensors, 268 are Ref2VA's, 201 are the same in both, and 463 match neither. 

**An FL2VA hybrid** (`minimax_h3_hybrid_fl2va_ref2va_b25-49-int8`, a community merge on Hugging
Face; sha256 a629cfea…): FL2VA's weights, with `adaln_proj` in blocks 25-49 taken from Ref2VA.
Checked tensor by tensor against our two files, it is exactly that: 681 FL2VA's, 50 Ref2VA's,
201 the same in both. On sh1460, with the same seed and Denise's usual sheet:

| Model | Lattice | Time |
|---|---|---|
| hybrid + Ref2V turbo LoRA, 8 steps | **clean** (Denise, the stethoscope, the plate's station) | 67 s |
| hybrid, no turbo, 20 steps | clean | 125 s |

Then hybrid + turbo on the other four lattice shots and four others, each at its Porchlights
take's seed, against that take:

| Shot | Ref2VA + turbo (Porchlights) | Hybrid + turbo |
|---|---|---|
| sh1470 CU Denise | lattice on the scrubs | **a diamond mesh over the whole frame**; her locs gone |
| sh1495 ECU hand | smeared | clean: hand, cup, the stethoscope on the counter |
| sh1590 cowboy Crane | gold loops on the jacket | clean; badge and lanyard right |
| sh1610 CU Crane | loops, a checkerboard on the walls | clean |
| sh290 CU Denise | **stethoscope loops on the chest** (not on the list of five) | clean |
| sh140 MS Crane | fine | fine |
| sh170 MCU Samir | fine | fine (the phone held lower) |
| sh1620 CU doctor | fine | fine, the background softer |

sh1470 without turbo (20 steps, the same seed): on Ref2VA, no lattice and her locs kept, but the
stethoscope comes out as a pair of glasses and a stray chest piece at her shoulder; on the hybrid,
no lattice, the locs gone again.

So:

- **Without turbo, Ref2VA** has cleared the lattice on both shots tried (sh1460, sh1470) and
  kept identity; it costs about twice the time.
- **The hybrid with turbo** cleared four of five, at turbo's speed, and held identity on the
  clean shots; on sh1470 it moved the lattice to the whole frame and, with or without turbo,
  dropped Denise's locs. It holds references a little less well, as its README says.
- The lattice is likelier than the list of five suggested: sh290 had it too.
- A retry ladder for an `artifact` finding on a Ref2VA turbo take: the hybrid with turbo first
  (cheap), then Ref2VA without turbo.
- The hybrid is the video target `h3_hybrid` (2026-11-12; the Features window's **H3 Hybrid**),
  every other H3 target's model pattern excluding `*hybrid*`. Porchlights ep02's sh290, sh1460,
  sh1495, sh1590 and sh1610 were rendered on it in the episode itself.

Still open:

- the instructions: a speaking mouth is `lipsync`, never `action`;
- full precision and 480p on a machine with more memory (the 4-bit loss is unmeasured);
- prompting adherence as "the gist, not the wording";
- more labeled misses: identity, a wrong camera move, FastH3 sh020.

## Not doing (yet)

- **The VLM review** (checklist 3-8): set aside, above.

- **Retries driven by a review.** The batch review runs after the retries. Feeding a `reject`
  back into the ladder comes later, once its false flags are known.
- **Picking takes.** Choosing a take into the cut stays a person's job.
- **Paid VLMs.** Local only, as the line retries are; a hosted VLM could be a target later.

## Checklist

- [x] 1. The history: issues archived to `_history.jsonl` on resolve and clear, with how each
      ended; `source` and `category` on notes; the categories as one list in the code, the
      Add issue box's dropdown and `--category`; the notepad's filter (2026-11-12).
- [x] 2. The bake-off; its numbers in this file (2026-11-11: Qwen3.5-27B, 8 fps, strict).
Set aside with the review (3-8):

- [ ] 3. The `vision` target kind and the first target; the node (ours, or an existing pack's);
      the Features entry for the weights.
- [ ] 4. `dailies.py`: one take reviewed (what it sees, the job, the sidecar record, stale);
      `seriesmith dailies`; the clip's **Review this take**; the badges; a reject sinks.
- [ ] 5. The batch: the Render dialogs' option, and the step waiting on the batch and its
      retries.
- [ ] 6. A review's findings as issues; the export.
- [ ] 7. MCP: `dailies_review`, `dailies_of`, `history`.
- [ ] 8. Live: an overnight batch of one episode, reviewed; read against a person's own pass.

Next:

- [x] 9. The count check: people and faces per frame (YOLO, ComfyUI's own weights, on CPU)
      against the shot's `who:`, `with:` and `extras:`; flagged when more show for 0.25 s or
      more, never on the median; a take check (`takecheck.register`) with its badge, its
      weights in the Features window (2026-11-12: `countcheck.py`, `helpers/counts.py`).

**The count check, live (2026-11-12, Porchlights ep02, 8 fps, CPU, about 20 s a take).** It
caught all four takes the experiment did: sh1190 t02 (2 people for 1), sh1420 t02 (4 for 2),
sh1510 t01 (3 for 1), sh1570 t02 (5 for 4 at 1.25-1.5 s, the median 4). It passed sh140 t03,
sh290 t03, sh1590 t02 and sh1210 t02 (sh1210's arm from the chest isn't a count problem). It
flagged sh1460 t03, the H3 Hybrid take: 2 people for 1, and rightly so. A soft-focus man stands
behind Denise the whole take, and the script has no `extras:` for him. Whether a background
stranger matters is the person's call; the badge says to look, and to name them in `extras:` if
they belong. The extras are counted from their words; of ep02's 47 shots with extras, those
whose number isn't said ("day-shift nurses", "a few") aren't checked.
