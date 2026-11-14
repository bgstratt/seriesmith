# Which model renders a shot

A reference for SKILL.md: the targets and what each takes, a section per model, the hosted models and their table of pictures, keyframes, `dur: model`, `target: hold`. Read it when the series config or a shot names a `target:`, or the person asks which model to use.

## Choosing a video target

| target | what pins the look | sound | keyframes | length grid | good for |
|---|---|---|---|---|---|
| `minimax_h3_ref2va` (default) | your sheets and plate, as up to nine reference pictures: eight subjects and the plate | generated, dubbed to a recording, or cloned from voice samples | first, when the series' `first_target` sends its continuing shots to it (otherwise they go to H3 FL2VA) | `17k+5` frames at 24 fps | recurring characters who talk; lip sync to your recording |
| `fasth3_omni` | as Ref2VA | as Ref2VA | not read | `17k+5` at 24 fps | crowded shots (up to eight characters, props and vehicles); FastVideo's 8-step H3, no turbo LoRA |
| `h3_singularity` | as Ref2VA | as Ref2VA | first, on a shot that asks for one | `17k+5` at 24 fps | Ref2VA shots on AIGC-Singularity's fine-tune of H3 Ref2VA (its v2 pruned INT8: sharper highlights, distant faces, motion). A shot that asks for a first frame (`continuous: first`, a `first:` line) opens on it here, its pictures kept |
| `h3_hybrid` | as Ref2VA | as Ref2VA | first, on a shot that asks for one | `17k+5` at 24 fps | Ref2VA shots on a merge of H3's two checkpoints: FL2VA's cleaner picture with Ref2VA's reference pictures. For shots where Ref2VA's turbo draws a lattice over thin things in a reference (a stethoscope, a phone cord, a lanyard); it holds a reference a little less tightly. A shot that asks for a first frame opens on it here, its pictures kept |
| `fasth3_fl2va`, `h3_singularity_fl2va` | the first/last keyframes, as FL2VA | as FL2VA | as FL2VA | as FL2VA | FL2VA's graph with FastH3 Omni's or Singularity's weights. `fasth3_fl2va` is where a `continuous: first` shot on FastH3 Omni goes, so it keeps FastH3's look; either can be named, or be the series' `first_target` |
| `minimax_h3_fl2va` | the shot's first/last keyframes, plus words | generated, dubbed, or cloned (the lines made by LTX first) | optional | `17k+5` at 24 fps, best 5–15 s | picking up exactly where the previous shot ended |
| `ltx2` | words, plus keyframes when there are any | generated, dubbed to a recording, or cloned from voice samples | optional | `8k+1` at 24 fps, up to ~20 s | fast text-to-video with sound; `dur: model` |
| `ltx2_ingredients` | a reference sheet made from your refs (required) | generated, or dubbed (no clone) | not read | `8k+1` at 24 fps, 2–20 s, best 5.04 s | identity on LTX |
| `ltx2_msr` | your sheets and plate as up to five pictures: four people or things and the place (required) | generated, dubbed, or cloned | not read | `8k+1` at 24 fps, up to ~20 s | identity on LTX-2.5, several people in a shot |
| `wan22_i2v` | a first frame (required) | none | first required, last optional | `4k+1` at 24 fps, best ≤ 3 s | animating a still |
| `wan22_ti2v` | words, or a first frame | none | first optional | `4k+1` at 24 fps | cheap proxies; where an I2V shot without a first frame can go |
| `wan22_vace` | a reference picture made from your sheets | none | optional | `4k+1` at 24 fps, best ≤ 3 s | identity without sound |
| hosted models on Comfy Router (`seedance_2_5`, `kling_v3_omni`, `veo_3_1_fast`, `wan_3_0`, `minimax_h3`, …) | your refs as pictures (one panel of a sheet, then the plate; Seedance 2.5 up to 30 pictures, 2.0 up to 9, the rest in the table under **Rendering a shot on a hosted model**) or the keyframes, plus words | generated (Runway: none); Seedance also dubbed or cloned | first, and last on most | whole seconds, each model's range | trying a shot on another model with no install; a Comfy API key, paid per take |

- **Leave the target out** unless the choice is a decision about the film. Shots with no
  `target:` render on the episode's target (set in the editor) or the series config's
  `series.target`, so a whole episode can be moved to another model without touching the
  script.
- **Name it** (`target:` on a shot, or under a `#` header for its sequence) when a shot
  needs something only one model does: a silent insert on Wan, a shot whose length you want
  LTX to choose (`dur: model`). A `continuous: first` shot moves to a model that reads a
  first frame by itself: H3 Ref2VA's to H3 FL2VA, FastH3 Omni's to its own FL2VA; H3
  Singularity opens on it itself (see **Continuous shots**).
- **Dialogue needs a target with sound**, and lip sync to a recording needs one of the H3
  workflow targets (`minimax_h3_ref2va`, `fasth3_omni`, `h3_singularity`, `h3_hybrid`, `minimax_h3_fl2va`). Wan acts the lines silently.
- **On a target that takes no reference pictures** (`ltx2`, `minimax_h3_fl2va`, `wan22_i2v`,
  `wan22_ti2v`; `wan22_vace` takes the sheets but not the plate), the `design` and location
  `description` sentences are what the model knows about the look, apart from any
  keyframe. Keep them complete.
- A keyframe is a picture: plan `first:` / `last:` lines (see **Keyframes**) for the
  targets that read them.

Details per target are under **Rendering a shot on …** below. A show can have models of
its own too (another hosted model, or a workflow saved in ComfyUI), named in `target:` like
any other.

### Which model a shot renders on

Most specific first:

1. the render request (`render --target`, the New take dialog);
2. the shot's override in the editor (`seriesmith override <ep> sh020 --target ltx2`);
3. the script: a `target:` line, or a profile's target, on the shot or its sequence;
4. the episode target set in the editor (kept in `overrides.json`, not `series.json`);
5. `series.target` in `series.json`;
6. this machine's default: the model picked in Settings, else the first installed.

So leave `target:` out of a script and `series.target` out of a config unless the choice is
the film's: the episode then follows whatever the person renders on. Which models are
installed, and what each still needs, is `seriesmith targets` (seriesmith's full setup guide).

### Rendering a shot on LTX-2

`target: ltx2` on a `##` shot, under a `#` header, or in a profile renders that shot (or
sequence) on LTX-2.5; one episode can mix models freely. What changes for an LTX shot:

- **Words first, pictures when they're there.** Everyone in `who:` / `with:` is described
  from their `design` and the place from its `description`, so those sentences must carry
  the look. When the pictures exist and LTX's ingredients LoRA is installed, they're also
  tiled into one reference sheet for the shot (`lora: none` turns that off). One person on
  the sheet holds well; with two or more LTX can render the sheet itself, so put a group
  shot on `ltx2_msr`, or render it from words with `lora: none`. A first or last keyframe
  pins the picture when there is one.
- **Its own grid:** `8k + 1` frames, up to about 20 s; a `dur:` lands slightly differently
  than on H3.
- **Sound** is made with the picture: generated, dubbed to the recording, or cloned from
  each speaker's `voice_sample`.
- **`camera:`** for a move you want; without it the camera stays still.
- **A quality pass:** the default transformer is distilled (8 fixed steps). The dev
  transformer renders a 30-step quality profile for crisper lines and steadier faces, at
  little extra cost; give the shots that want it a profile:

  ```json
  "profiles": { "quality": { "target": "ltx2",
                             "model": "ltx-2.5-22b-dev-transformer-comfy-int8-convrot.safetensors" } }
  ```

### Rendering a shot on LTX-2 with its refs: `target: ltx2_ingredients`

LTX-2.3 with the "ingredients" LoRA, which keeps a recurring character like its sheet.
As LTX-2 above, except:

- **Its pictures are required**: one sheet tiled from each character in `who:` (the face on
  a one-character close-up, else the body), each prop in `with:`, then the plate. The model
  only reproduces what's on the sheet, and bigger panels carry better: keep important shots
  to few subjects, and the plate clean.
- **Best at 5.04 s** (what it was trained on); 2 to 20 s render, with a warning off 5.04.
- No `clone`: such shots generate.

### Rendering a shot on LTX-2.5 with several people's pictures: `target: ltx2_msr`

LTX-2.5 with the MSR LoRA: up to four people or things as pictures, plus the plate. As
LTX-2 above, except:

- **Its pictures are required.** A person's face picture can be a variant named for it
  (`charming_face`, `"of": "charming"`); without one, the top of their picture is used.
- **Write the action plainly.** MSR follows the words closely: "the women behind him" in a
  close-up can put them in it. Name who is in frame and keep anyone else out of the sentence.
- **Give a group time.** Three people held in 4–5 s shots; in 1–2 s shots one or two often
  went missing. One person holds at any length.
- Speech varies by seed: reroll a garbled line. No `continuous: multishot`.

### Rendering a shot on H3 from keyframes: `target: minimax_h3_fl2va`

H3's first/last-frame model: H3's grid, sizes and dialogue, but **no reference pictures**.
What pins the look is the shot's keyframes (`first:` / `last:`, or the previous shot's last
frame with `continuous: first`); with neither it is text-to-video.

- Everyone is described from their `design`, the place from its `description`; a keyframe
  wins where it and the words differ.
- Sound: generated, dubbed, or cloned (the lines are made by LTX-2.5 first, so `clone` needs
  LTX-2.5 installed too).
- Best at 5 to 15 s; longer renders with a warning.

### Rendering a shot on Wan 2.2: `wan22_i2v`, `wan22_ti2v`, `wan22_vace`

Three silent models:

- **`wan22_i2v`** (14B) animates a picture: **a first frame is required** (`first:
  generate`, an imported picture, or `continuous: first`). A last frame too makes it a
  first/last-frame shot.
- **`wan22_ti2v`** (5B): text-to-video, or from a first frame when there is one. The fast,
  cheap one, and where an I2V shot with no first frame can go.
- **`wan22_vace`** (14B): keeps characters like their sheets (one picture made from the
  sheets of `who:` and `with:`; the place is in words). First and last frames optional.

What every Wan shot has in common:

- **No sound.** Dialogue is acted silently (`check` warns); the sound goes on in the edit.
  Keep a shot that needs lip sync on a model with sound.
- **Keep it to 3 s or less.** The 14B models were trained on 3.4 s and follow the prompt less
  after that; past 6.7 s a shot must be split. Lengths are on a `4k + 1` grid.
- **No `sound:` or `music:`**: they are ignored.
- Sizes are the model's own (832×480 or 1280×704 final, 640×352 proxy); the cut scales them.

### Keyframes: `first:` and `last:`

Some models start (or end) a shot on a picture: its **keyframes**. Which shots need one
follows from the model:

- `wan22_i2v` and `hold` **require** a first frame;
- `ltx2`, the FL2VA models, `wan22_ti2v` (first only), `wan22_vace` and the hosted models
  use them when they exist (a hosted model given a first frame is sent the keyframes instead
  of the character pictures);
- H3 Ref2VA, H3 Singularity and H3 Hybrid read a first frame on a shot that asks for one
  (**Continuous shots** says where such a shot renders), never a last;
- FastH3 Omni, `ltx2_ingredients` and `ltx2_msr` don't read them.

How each is made, on the shot or under a `#` header for all its shots:

```
# sq02  workshop
first: generate

## sh030
last: generate
first: refs/stills/sh030_open.png
```

| value | meaning |
|---|---|
| `generate` | a still made from the shot's own description (the default) |
| `import` | the person will import one |
| a path | this image, relative to the episode |
| `none` | no keyframe, even where the model could use one (a required one stays required) |

A generated still draws the shot's look, framing, place and cast at a moment of the action:
`first` from the action's first sentence (about to happen), `last` from its last (done). So
write the action as a short sequence of sentences, and both ends come out right.

A first frame from the previous shot isn't a `first:` value: the shot says
`continuous: first`.

### A picture held still: `target: hold`

`target: hold` holds the shot's first keyframe still for its `dur:`: a card ("Two hours
later"), a title, a still, a freeze frame. It runs on this machine and costs nothing.

```
## sh045
target: hold
dur: 2
first: cards/two_hours_later.png
A card: Two hours later.
```

- **The picture is required**: a picture of the person's (`first:` a path), or
  `continuous: first` for a freeze frame of the shot before.
- It reads nothing else, but write an action all the same: it's what the shot is.
- Silent unless its sound is set to a dub in the editor.

### Rendering a shot on a hosted model: Seedance, Kling, Veo, …

A hosted model (`target: seedance_2_5`, `kling_v3_omni`, `veo_3_1_fast`, `wan_3_0`, …)
renders in its provider's cloud, one paid call per take (it needs a Comfy API key). What it
is sent:

- **The prompt:** the same prose LTX and Wan get, with each character's `design` less what
  describes a body: the provider's content filter reads the request (see **Writing the
  `design` sentence**). The provider looks at the pictures too: a revealing reference can be
  refused whatever the prompt says.
- **The pictures:** the shot's keyframes when the model reads a first one and the shot has
  it. Otherwise one picture of each character in `who:`, each prop in `with:`, then the
  plate, up to the model's limit (the table below). Past the limit the rest are left to the
  words, and `check` says who wasn't sent: pick a model that takes more, or describe a
  subject in the action instead.
- **Who's who:** Seedance's prompt defines each picture from the opening of its `design`
  (*Define a young woman with blonde hair … in @Image 1 as Cindy*), so a design that leads
  with who they are, their hair and their clothes defines them best. Kling names each
  picture; the others take them in order.
- **FLUX 3 video** takes no character pictures, only keyframes: make the first keyframe of
  any shot whose people must look like themselves. 5 to 20 s a shot, no seed.
- **Sound on Seedance:** a `clone` shot sends each speaker's `voice_sample` (2 to 15 s), a
  `dub` shot its window of the recording; with audio, its keyframes are left out. A dub comes
  back re-performed at Seedance's own pace: keep the take's sound rather than the recording.
  The other hosted models make their own sound.

What each video model takes (generated from the models by `python tools/make_refs_md.py`):

<!-- BEGIN PICTURES (generated by tools/make_refs_md.py — do not edit) -->

| Video model | | Runs on | Reference pictures | Keyframes | Told who's who |
|---|---|---|---|---|---|
| `fasth3_fl2va` | FastH3 FL2V | your ComfyUI | none | first and last | — |
| `fasth3_omni` | Omni | your ComfyUI | 8 subjects + the plate | — | `<Subject N>` … `<Picture N>` |
| `h3_hybrid` | H3 Hybrid | your ComfyUI | 8 subjects + the plate | first, when the shot asks | `<Subject N>` … `<Picture N>` |
| `h3_singularity` | Singularity | your ComfyUI | 8 subjects + the plate | first, when the shot asks | `<Subject N>` … `<Picture N>` |
| `h3_singularity_fl2va` | Singularity FL2V | your ComfyUI | none | first and last | — |
| `hold` | Hold | this machine | none | first | — |
| `ltx2` | LTX-2 | your ComfyUI | none | first and last | — |
| `ltx2_ingredients` | LTX+refs | your ComfyUI | one sheet tiled from the subjects and the plate | — | by their order |
| `ltx2_msr` | LTX+MSR | your ComfyUI | 4 subjects + the plate | — | `Image N`, by their order |
| `minimax_h3_fl2va` | H3 FL2V | your ComfyUI | none | first and last | — |
| `minimax_h3_ref2va` | H3 | your ComfyUI | 8 subjects + the plate | first, when the shot asks | `<Subject N>` … `<Picture N>` |
| `pika_h3_flex` | Pika Flex | your ComfyUI | 8 subjects + the plate | first, when the shot asks | `<Subject N>` … `<Picture N>` |
| `pika_h3_flex_fl2va` | Pika Flex FL2VA | your ComfyUI | none | first and last | — |
| `wan22_i2v` | Wan I2V | your ComfyUI | none | first and last | — |
| `wan22_ti2v` | Wan 5B | your ComfyUI | none | first | — |
| `wan22_vace` | Wan+refs | your ComfyUI | one picture made from the subjects' sheets | first and last | by their order |
| `flux_3_video` | FLUX 3 | Comfy Router | none | first and last | — |
| `kling_v3_omni` | Kling | Comfy Router | up to 7: the subjects, then the plate; as links | first and last | names each: `<<<image_N>>>` is … |
| `kling_video_o1` | Kling O1 | Comfy Router | up to 4: the subjects, then the plate; as links | first and last | names each: `<<<image_N>>>` is … |
| `minimax_h3` | MiniMax | Comfy Router | up to 9: the subjects, then the plate; as links | first and last | by their order |
| `runway_gen4_turbo` | Runway | Comfy Router | none | first | — |
| `seedance_2_0` | Seedance | Comfy Router | up to 9: the subjects, then the plate; through the Seedance library (`asset://`) | first and last | defines each first: *Define … in @Image N as …* |
| `seedance_2_0_fast` | Seedance | Comfy Router | up to 9: the subjects, then the plate; through the Seedance library (`asset://`) | first and last | defines each first: *Define … in @Image N as …* |
| `seedance_2_0_mini` | Seedance | Comfy Router | up to 9: the subjects, then the plate; through the Seedance library (`asset://`) | first and last | defines each first: *Define … in @Image N as …* |
| `seedance_2_5` | Seedance | Comfy Router | up to 30: the subjects, then the plate; through the Seedance library (`asset://`) | first and last | defines each first: *Define … in @Image N as …* |
| `veo_3_1` | Veo | Comfy Router | up to 3: the subjects, then the plate; inline | first and last | by their order |
| `veo_3_1_fast` | Veo | Comfy Router | up to 3: the subjects, then the plate; inline | first and last | by their order |
| `veo_3_1_lite` | Veo | Comfy Router | up to 3: the subjects, then the plate; inline | first and last | by their order |
| `wan_2_7_i2v` | Wan | Comfy Router | none | first and last | — |
| `wan_2_7_r2v` | Wan | Comfy Router | up to 5: the subjects, then the plate; as links | first | by their order |
| `wan_3_0` | Wan | Comfy Router | up to 10: the subjects, then the plate; as links | first and last | by their order |
| `wan_3_0_prime` | Wan | Comfy Router | up to 10: the subjects, then the plate; as links | first and last | by their order |

<!-- END PICTURES -->

### Letting the model time a shot: `dur: model`

`dur: model` hands the shot's length to the video model: LTX-2.5 reads the prompt and
predicts how long the shot naturally runs, then renders that. `dur: model 3-8` keeps the
prediction between 3 and 8 seconds (without a range: 1 to 20).

- **The build still needs a length** for the cut and the runtime, so it writes an
  **estimate**: the `dur: auto` length when the shot has dialogue, else 5 seconds, inside
  your range. The take records the real length it came out at, and the editor's timeline
  and Play all use that once it's rendered.
- **Only `ltx2` can predict**, and only once its duration head is installed (the file
  `ltx-2.5-duration-head-bf16.safetensors` in ComfyUI's `models/model_patches`). Until then,
  and on every other target (H3, `ltx2_ingredients`, Wan), the shot renders at the estimate:
  `--check` warns and the take's notes say so.
- Use it for silent action and establishing shots whose length you don't care to pick. A
  dialogue shot is better with `dur: auto` or an `audio:` window, which keep the lines
  their room.
