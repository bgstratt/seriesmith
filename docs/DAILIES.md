# Dailies: takes reviewed by a vision-language model

Status (2026-11-11): **designing**, nothing built. This file is the design record and the
checklist; the contracts go in the docstrings, `docs/API.md` and `docs/EDITOR.md` as they are
built.

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
    {"criterion": "adherence | artifact | reference",
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
- **artifact**: anything that changes in a way nothing in the picture explains, with its span
  (`at`);
- **reference**: one finding per reference picture (wardrobe, props, place).

**Categories**, one fixed list, so notes can be counted: `identity`, `wardrobe`, `place`,
`morph`, `action`, `camera`, `count` (too many or too few people or things), `cut`, `lipsync`,
`text` (lettering in the picture), `other`.

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
comes only from its artifact and reference findings, at confidence 0.8 or more; its adherence
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

**Pick: Qwen3.5-27B at 8 fps, strict**: the take's verdict from artifact and reference findings
at confidence 0.8 or more, adherence as notes. On the 5090 that makes about 2 minutes a take,
about 3.5 hours for a 100-shot episode overnight, with a peak of 24.8 GB.

Two Porchlights ep02 takes, unlabeled, at 8 fps:

- **sh1130 t02** was rejected: "blue digital dots and lines overlay the entire scene" from 2.2 s
  (morph/artifact, confidence 1.0). Everything else passed.
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

Still open:

- the instructions: a speaking mouth is `lipsync`, never `action`;
- full precision and 480p on a machine with more memory (the 4-bit loss is unmeasured);
- prompting adherence as "the gist, not the wording";
- more labeled misses: identity, a wrong camera move, FastH3 sh020.

## Not doing (yet)

- **Retries driven by a review.** The batch review runs after the retries. Feeding a `reject`
  back into the ladder comes later, once its false flags are known.
- **Picking takes.** Choosing a take into the cut stays a person's job.
- **Paid VLMs.** Local only, as the line retries are; a hosted VLM could be a target later.

## Checklist

- [ ] 1. The history: issues archived to `_history.jsonl` on resolve and clear, with how each
      ended; `source` and `category` on notes; the categories as one list in the code, the
      Add issue box's dropdown and `--category`; the notepad's filter.
- [x] 2. The bake-off; its numbers in this file (2026-11-11: Qwen3.5-27B, 8 fps, strict).
- [ ] 3. The `vision` target kind and the first target; the node (ours, or an existing pack's);
      the Features entry for the weights.
- [ ] 4. `dailies.py`: one take reviewed (what it sees, the job, the sidecar record, stale);
      `seriesmith dailies`; the clip's **Review this take**; the badges; a reject sinks.
- [ ] 5. The batch: the Render dialogs' option, and the step waiting on the batch and its
      retries.
- [ ] 6. A review's findings as issues; the export.
- [ ] 7. MCP: `dailies_review`, `dailies_of`, `history`.
- [ ] 8. Live: an overnight batch of one episode, reviewed; read against a person's own pass.
