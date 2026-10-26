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

1. **A subject's picture in a group: decided (2026-10-26), the first one named, with a
   warning.** One picture per subject per generation: a group that names Charming
   full-length in its wide and as `charming_face` in its close-up sends the first.
2. **H3's length for a group: decided, no limit.** The proof was 8 s; how long a group runs
   is the user's call. A target that has a hard maximum (Seedance's 30 s, Kling's) still
   refuses past it.
3. **Plates: the first member's, for now.** H3 takes one plate a generation (Kling four
   pictures in all; Seedance up to 30, so every plate fits there). A member naming another
   plate is described in words in its own section, and `check` says that plate isn't sent as
   a picture. The widest shot's plate, or one named on the first shot, are the alternatives
   if the first member's proves the wrong pick.
4. **A group continuing a single shot: `latent` yes, `first` with a warning.** `latent` on
   the group's first member holds the previous take's last frames at the head of the
   group's generation, as a single latent shot does on Omni and Ref2VA; the `[Shot N]` cut
   times shift by the held frames. `first` gives the group a first keyframe, which Omni and
   Ref2VA don't read (a single shot switches to FL2VA, which takes no character pictures)
   and which a hosted model is sent instead of the pictures: the group renders, but drawn
   from words, and `check` says so.
5. **Seedance timing: decided, test once the `prose` writer exists.** It cuts where it
   chooses; whether writing each member's duration into its paragraph helps is tried then.
6. **Kling: storyboard or prose.** Tried once each (checklist d'): the storyboard holds its
   durations to the frame but lost the faces; one prose prompt held the faces and cut within
   about 0.9 s of what it was asked. Which form Kling v3 Omni is built in is open; until then
   a prose prompt reaches it as a prompt override.

## Checklist

- [x] (a) The field (2026-10-26): `continuous: multishot` parsed (shot and `#` header),
      `Sequence.multishot_groups()`; a target renders it when its target.json has a
      `multishot` form (`timed`: H3 Ref2VA, Omni, FL2VA); a group renders on its first
      shot's target (`multishot_target`; so a group opening `continuous: first` moves to
      FL2VA with it); `multishot_check`: errors for a group on the first shot of a sequence,
      on a target without a form, a member naming another target, more subjects than the
      target's slots; warnings for a second picture of one person, another plate, a group
      opening on a first keyframe. A cut inside a group still gets the jump-cut warning.
      tests/test_multishot.py.
- [x] (b) The build (2026-10-26): a group is one shotlist entry under its first shot's id,
      each shot compiled as itself first (its pacing, pictures, policy checks), then joined:
      the group's subjects (each person once, the first picture named; a later wardrobe
      variant and its lines drawn as that picture), the first shot's plate, seed and
      settings, one length on the grid (its padding the last shot's), and `multishot`
      (each shot's id, start frame, frames, size). The `timed` writers: Ref2VA/Omni's
      (`build_multishot_prompt`: shared subject definitions counted "in this video",
      retention naming the shots each subject appears in, one speaker register for the
      group, a `[Shot N] At MM:SS.mmm, the shot cuts.` section per shot; a close-up on
      another plate is a blurred crop of the plate sent, a wider shot on one is in words)
      and FL2VA's (its own per-shot text joined into the same sections, the look said
      once, the speakers renumbered to the group's; the first shot's first keyframe, the
      last shot's last). A group opening `continuous: latent` counts the held frames in
      its cut times. Generated sound only: a dubbed or cloned shot in a group is refused
      for now. Single shots compile byte for byte as before (the goldens).
- [x] (c) End to end (2026-10-26): ep04's sh040-sh060 as a group, built from the script and
      rendered on local Omni (192 frames, 3:47): the same three women back after the cut,
      Charming's close-up from his face picture. Its cuts landed at **4.917 s and 6.500 s**
      for 4.458 and 6.083 (11 and 10 frames late; the hand-written proof was within 3): H3
      cuts within about half a second of the times asked, so a later slice or splice snaps
      to the cut found near each one (frame difference: 38.6 at both against a median of
      0.9). The cut was already one item for a group (it is built from the shotlist's ids);
      the editor's status carries `multishot`, the timeline clip is labelled `sh040–sh060`
      with dashed marks where the script times the cuts, the Shots tab tile lists the
      group's shots, and the shot form's Continues menu offers `multishot`. AUTHORING
      ("Several shots in one generation") and API.md say how.
- [x] (d) The writers (2026-10-26), offline: a group on a hosted model compiles in
      video_prose (`compile_group`: each shot as itself, then one call: every person once,
      the target's `multishot.plates` of plates, "all" for Seedance, one length on the
      model's whole seconds, a group past its maximum or its `max_shots` refused). `prose`
      (Seedance 2.5, 2.0, 2.0 fast/mini): the look once, "A scene in N shots, each a hard
      cut from the one before.", then `Shot N, a hard cut:` paragraphs, after Seedance's own
      "Define ... in @Image N" line. `storyboard` (Kling v3 Omni, Video O1): the entry's
      `storyboard` (each shot's prose and whole seconds, summing to the call's), sent by
      router_call as `multi_shot` / `shot_type: customize` / `multi_prompt` (each part at most
      512 characters, the pictures named in each), no `prompt`. The generated targets carry
      the forms by tools/make_router_targets.py's corrections; Seedance 2.5's by hand. A
      group's first shot rendered from the editor on a model without a form is refused with
      the reason. tests/test_multishot.py pins both requests (router_call, offline).
      Refined on the ep04 beat's dry runs (render --dry-run, nothing sent): Seedance's prose
      says a place once ("the same place" after) and a person's look once, and with several
      plates its "Define ... as the scene" says whose (`of Shot 1 and Shot 3`); Kling's parts
      are built for 512 characters (video_prose.board_parts, router_video.board_prompt): the
      framing and the lines always, then the action, camera and sound while they fit, then
      the pictures of who is in that shot, by name. A busy shot loses its action there: three
      lines and a long action don't fit 512 characters with the names, and a storyboard has
      no prompt for the look or the place (the schema: "when multi_shot is true, the prompt
      parameter is invalid").
- [x] (d') Tried once each, live (2026-10-26, the ep04 group, 8 s at 720p, paid and asked
      first). The first sends were refused before generating: the hall plate is 3.7:1, and
      Seedance's library answered 400 AspectRatioTooLarge ("between 0.4 and 2.5"), Kling a
      bare provider_error. A paid call never crops or pads a picture by itself: the targets
      now carry `router.picture_ratio` [0.4, 2.5], and router_call refuses an out-of-shape
      picture before sending, naming it and the crop that fits (refs.image_size reads WebP
      now). With the plate cropped to 2.5:1 (the scratch copy; its middle kept):

      | | asked | shot 1 → 2 | shot 2 → 3 |
      |---|---|---|---|
      | FastH3 Omni (timed) | 4.458 / 6.083 | 4.917 | 6.500 |
      | Seedance 2.5 (prose) | 4.458 / 6.083 | 4.625 | 6.625 |
      | Kling v3 Omni (storyboard 4/2/2 s) | 4 / 6 | 3.958 | 6.042 |

      Kling keeps its storyboard's durations to the frame (whole seconds: the script's
      4.46/1.62/1.62 sent as 4/2/2), and staged shot 1 over Charming's shoulder; its shot 2
      came out a medium shot where a close-up was asked. Seedance timed its own cuts within
      about half a second from prose alone (open question 5: no durations in the paragraphs
      needed so far), framing tighter; its "Fine." in shot 2 is faint or missing (to listen
      to). Omni holds the pictures closest and stages most plainly. All three bring the same
      people back after the cut. On a closer look Kling's storyboard lost its people's faces
      (Seedance and Omni held them).

      Kling's other form, tried once (paid, asked first): the same group as one prose prompt
      (`multi_shot` off; a prompt override of 1516 characters, 1673 with the picture names,
      under its 2500): the look and the place once, who's who once with a short look each,
      then `Shot N (Xs), a hard cut:` paragraphs. It cut at 4.792 / 6.875 (asked 4 / 6 s, so
      looser than the storyboard's frame-exact cuts) and held the three women's faces, hair
      and dresses close to their pictures, Charming's hair and coat; the storyboard parts,
      512 characters each with no room for the look, had lost them. So the prose carries
      identity on Kling, the storyboard only timing. router_video sends an overridden prompt
      as one prompt (as ltx2's), which is how this was tried; whether Kling's built form
      should become `prose` (with each shot's seconds in its paragraph) is open question 6.
- [ ] (d'') Seedance and Kling once more, for a second sample each (paid: asked first): Seedance 2.5 on the ep04 beat, and
      whether writing each shot's seconds into its paragraph moves Seedance's cuts (open
      question 5); Kling v3 Omni's storyboard and whether it holds the durations (6).
- [x] (e) Upscale and master of a group take (2026-10-26, the ep04 group on local Omni).
      The upscale needed nothing: H3's latent re-sample of the 8 s take ran in 5.5 s windows,
      each under the whole group's prompt, and kept both cuts on the take's frames (4.917 s,
      6.5 s), 2688x1536 with the take's sound, in 207 s. The master needed two fixes: it
      walked the script's ids (J.script_order), so a group's later shots were gaps and no
      master was ever whole; the cut, upscale, master and render's held-back list now walk
      the built ids (J.built_order: a group once, as the editor's cut). And a general one:
      a second upload of an input ComfyUI still held open (the latent the first upscale read)
      failed as a bare 500 on Windows; an input is named by its content, so one already
      there at that name and size isn't sent again (Comfy.upload_input). The master: one
      item, sh040, 2560x1440 with sound, its cuts at 4.958 s and 6.542 s.
- [ ] (f) Later: the splice (a range of a group take, bridged).
