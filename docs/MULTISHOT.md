# Multi-shot generations: `continuous: multishot`

Status (2026-10-26): **designing**, on the `multishot` branch. This file is the design record
and the checklist; the contracts will be in the docstrings, `docs/API.md` and
`docs/AUTHORING.md` once built. `continuous: first` and `latent` are docs/CONTINUOUS.md.

## Why

Every shot is its own generation today, so a model never sees the scene around a shot. A
Seedance 2.5 clip of a 13-shot scene made in one call (Higgsfield, 2026-10-25) showed what
that costs: in one generation, lines run across cuts (Harrow's "Case closed." on his close-up,
the rest of the line over the walk-out), blocking and light hold from shot to shot, and a
performance knows what came before it. Rendered shot by shot, the same script took 55.8 s
against Seedance's 30.1 s, mostly because every line had to fit inside its own shot.

Several models take more than one shot in a single generation, each in its own form. A run
of shots marked in the script can be rendered as one generation, on the models that can, and
the episode keeps its shots.

## What the models do (measured 2026-10-26)

One three-shot beat, the same on each (ep04 of Ballroom, sh040-sh060: the Stepmother, Mia and
Ava; a cut to Charming's "Fine."; back for "Excellent."), asked to cut at 4.458 s and 6.083 s:

| Model | How it is asked | Cuts | Notes |
|---|---|---|---|
| H3 Omni (FastH3) | its spec's timed sections: `[Shot 2] At 00:04.458, the shot cuts to ...` | **4.583 s, 6.083 s** | every line in its shot; shot 3 came back to the same three women, places and light; the close-up of Charming drawn from his full-length picture |
| LTX-2.5, text | Lightricks' multi-shot paragraph ("in three shots ... A hard cut transitions to ...") | 5.417 s, 6.708 s (its own) | lines in the right shots; identity loose (no reference) |
| LTX-2.5 + ingredients sheet | the same, with the sheet named | none | animated the reference sheet itself, twice (two wordings) |
| LTX-2.5 + Licon MSR + PromptRelay | PromptRelay segments of exact frame counts | none, three seeds | one continuous shot; Charming never cut to; faces generic (hair and dress kept, not identity) |
| Seedance 2.5 (Higgsfield) | prose, a `SHOT N` block per shot | its own (13 cuts in 30 s) | the reason for this design |

So: H3 cuts where it is told, within a few frames; Seedance and LTX cut where they choose;
LTX with references doesn't cut at all. LTX stays off the multi-shot list.

From the Router schemas: **Kling** v3, v3 Omni and Video O1 take a storyboard as fields
(`multi_shot: true`, `shot_type: customize`, `multi_prompt`: up to 6 entries of `prompt`,
`duration` of at least 1 s, `index`; the durations sum to the total); **Kling 3.0 Turbo** in its
prompt (`"shot n, m, words; ..."`); **Wan** 2.6/2.7 R2V and 3.0 by `shot_type: multi`, which works
only with `prompt_extend` (the provider rewrites the prompt). **Veo 3.1** and **Runway Gen-4
Turbo** have no form for it.

## The design

### In the script

```
## sh040
who: stepmother, mia, ava
dur: 4.46
...
## sh050
continuous: multishot
who: charming_face
size: cu
dur: 1.62
...
## sh060
continuous: multishot
who: stepmother, ava, mia
dur: 1.62
...
```

- **A third mode of `continuous:`**, on the shot that joins the generation of the shot before
  it, as `first` and `latent` are written on the shot that continues. A run of such shots and
  the shot they start from is a **group**.
- **On a `#` header** it covers every shot after the first in that sequence; `continuous: none`
  on a shot starts a new group (or a single shot). A group never crosses a `#` header.
- **Every shot keeps everything it has**: its id, `who:`, `size:`, `dur:`, action, lines,
  `camera:`, `sound:`. Nothing in the script says "group" but the field.
- **The other modes don't mix with it**: a shot is `first`, `latent` or `multishot`. A group's
  first shot may itself be `continuous: first` or `latent` from the shot before the group (a
  group can carry on from a single shot) — open question 4.

### In the build

- **A group is one shotlist entry**, under its first shot's id (`sh040`): one render, one seed,
  one take. It lists its members and where each starts:
  `"multishot": [{"id": "sh040", "start": 0, "frames": 107}, {"id": "sh050", "start": 107, ...}]`.
  Its length is the members' summed frames, put on the target's grid (H3 rounds the total up
  to 17k+5; the padding goes to the last member).
- **Its references are the union of its members'**: every subject in member order, first
  appearance first, each once. One picture per subject per generation, so a group that names
  `charming` in one member and the variant `charming_face` in another sends the first and
  `check` warns (open question 1). **One plate**: the first member's; a member naming another
  plate is described in words in its section and `check` warns.
- **Its prompt is written in the target's multi-shot form** (`target.json`
  `"multishot": {"form": ..., "max_shots": ..., "max_seconds": ...}`):
  - **`timed`** (H3 Ref2VA, Omni, FL2VA; `minimax_h3`): one prompt, its description a
    `[Shot N]` section per member, `[Shot 1]` without a time and every later one
    `At MM:SS.mmm, the shot cuts to ...`, at the member's start. Each section has the member's
    framing, action, `camera:` and lines (speaker ids shared across the group: a person is
    the same `(Sx)` in every section). `retention_analysis` names the shots each subject
    appears in. One `overall_soundscape` (the members' `sound:` lines, in order).
  - **`storyboard`** (Kling v3, v3 Omni, O1): `multi_shot: true`, `shot_type: customize`,
    `multi_prompt` an entry per member (its prose, at most 512 characters, its duration in
    whole seconds), at most 6 members, at least 1 s each.
  - **`prose`** (Seedance 2.0/2.5; Kling 3.0 Turbo in its own `shot n, m, ...` form): one
    prompt, a paragraph per member opened by the cut ("A hard cut to a close-up of ..."),
    re-establishing the framing and naming who is in it, the sound carried across. The model
    times the cuts.
- **A target without a form** refuses the group in `check`: which shots, and which targets
  can render it (or `continuous: none` to render them one by one).

### Rendering, takes and the cut

- **First version: a group is one item in the cut.** It renders as one take, is picked,
  trimmed, upscaled, posted and mastered like any shot, under its first shot's id; its
  members show in the editor as the group's sections (their lines, their start times), not
  as separate clips.
- **Upscales re-sample the group take as one** (H3's re-sample keeps the take's prompt, so
  the cuts stay where they were).
- **Later (the splice):** a range of a group take chosen in the editor (start and end, any
  frames, not necessarily a cut) is rendered again on its own as a bridge: its first frame
  the take's frame at the range's start, its last frame the one at its end, the same length
  (FL2VA, or a hosted model's first/last), and laid over that range. The group take's sound
  stays under it by default, so a line running across the cut holds; the bridge's own sound
  is a choice. Nothing is detected: the range is the user's. Cuts can still be found to snap
  a range to (frame-to-frame difference: ffmpeg's scene score missed LTX's cuts on steady
  light, a plain mean difference found them at 29 against a median of 1.6).

## Open questions

1. **A subject's picture in a group.** One picture per subject per generation: a group that
   wants Charming full-length in its wide and as `charming_face` in its close-up can't have
   both. First version: the first one named, with a warning. Better may be choosing the
   picture by the group's tightest framing of that subject.
2. **H3's length for a group.** The proof was 8 s. H3 FL2VA's notes say it was trained on
   5-15 s; Omni's grid goes far past that. Render one ~15 s group before setting
   `max_seconds` for the H3 targets.
3. **Plates.** H3 takes one plate a generation. A group that cuts between angles of a place
   (the hall and its reverse) loses the second as a picture. Is the first member's plate the
   right one, or the group's widest shot's?
4. **A group continuing a single shot** (`continuous: first` or `latent` on its first member):
   allowed, or not in the first version?
5. **Seedance timing.** It cuts where it chooses. Write each member's duration into its
   paragraph ("for about four seconds")? Test before deciding.
6. **The Kling storyboard** is untested (one paid call): whether it holds the durations.

## Checklist

- [ ] (a) The field: `continuous: multishot` parsed (shot and `#` header), groups formed,
      `check` errors and warnings, the golden fixtures.
- [ ] (b) The build: a group as one shotlist entry (members, starts, union of subjects, one
      plate); the `timed` writer for H3 Ref2VA/Omni/FL2VA.
- [ ] (c) Rendering a group on H3 Omni end to end (the proof, from a script); the take, the
      cut and the editor showing a group as one item.
- [ ] (d) The `prose` writer (Seedance) and the `storyboard` writer (Kling v3), each tried
      once.
- [ ] (e) Upscale and master of a group take.
- [ ] (f) Later: the splice (a range of a group take, bridged).
