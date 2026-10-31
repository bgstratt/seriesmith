---
name: seriesmith-episode-script
description: Write episode scripts and series configs for seriesmith, the script-to-episode AI video pipeline, fresh or converted from an existing screenplay. Covers the epNN.md script format (sequences, shots, ALL-CAPS dialogue, who/with/size/dur/plate/camera/sound fields, continuity and keyframe lines) and the series config (series.json) with what's required, what each optional block defaults to, the cast, locations, look, voices, profiles, render size and master recipe. Shots render on a video model per shot or episode (MiniMax H3, LTX-2, Wan 2.2, Seedance and others). Use it whenever the user wants to write, outline or extend an episode, pick a story structure, start a series, break a screenplay or scene into shots, add characters, props or locations to a series config, choose which model renders a shot, re-time shots whose dialogue doesn't fit, or fix a script seriesmith check rejected, even if they never name seriesmith or the file formats.
---

# Writing an episode for seriesmith

You are writing for seriesmith. Follow this format exactly: the output is compiled
by `seriesmith build`, and anything that does not match is a build error, not a style
preference.

Before writing anything, ask for the series config (`series.json`) if the series has one.
Adding a character means adding to that file, not inventing a new one: if you write `riley`
when the series config already has `riley_freeman`, every reference path breaks. With no
series config yet you are starting a series: write both files.

Starting a series, settle what **Starting a series: what to settle first** lists before the
first shot: the look, the delivery (1080p, 1440p or 4K, which sets the render size, the
proxy and the master recipe), the voices, the finishing pass and the titles. Ask what the
brief doesn't already say, in one message, then write the whole config: `upscale.master`
and `post` as well as the cast and the places. If the person would rather you just start,
use that section's defaults and list what you assumed. An existing series config is the
show's: add what the episode needs and change nothing else unasked, but if it has no
`upscale.master` block, say once that it can't be mastered by recipe until it has one.

Converting an existing screenplay, keep its story and dialogue and break it into shots
(`references/script_conversion.md` works a scene through). Writing fresh, outline the story
before the shots: if the person hasn't given it a shape, offer the menu in
`references/story_structures.md` (with the questions above, in the same message), then mark
each beat in the script with a `//` comment. Either way, write the film, not the model. Leave `target:` lines out unless a shot
needs something only one model does (see **Choosing a video target**); advice that holds for
one target only is marked with that target's name. Validate with `seriesmith check
series.json <script>` and `--pace` before calling a script finished. Rendering, upscaling
and mastering are the person's to run, not part of writing: point to `docs/FINISHING.md`
and `docs/COMMANDS.md` for those.

## Your first episode

Two files in one folder — and `seriesmith new Shows\ep01` writes both of them for
you (so does **New episode…** in the editor's project folders). This is what it writes,
and it is also `examples/starter/`, so you can read it before you run anything.

`Shows\ep01\series.json` first. `audio.mode: generate` means the model invents the
voices from each character's `voice` line, so nothing has to be recorded first. The
pictures are named `../refs/...`, one level up: that way every episode of the show
shares one `refs` folder while each keeps a series config of its own (a config in the
episode wins, the one beside it is the fallback), which is what lets episode four add
a character without touching the first three.

The folder can be called anything — `ep01` here, but `s2ep01`, `s3ep07` or `pilot`
just as well, which is how a show with seasons keeps them apart. Name the script
after the folder (`s2ep01\s2ep01.md`) and everything finds it: that is the only
name that still works when the episodes share one `series.json` in the folder above
them, and it is what lets `seriesmith build Shows --each` pick up every episode
under a show at once.

```json
{
  "series": {
    "id": "first_light",
    "title": "First Light",
    "fps": 24,
    "width": 1344,
    "height": 768
  },
  "proxy": { "width": 896, "height": 512 },
  "style": {
    "look": "a 2D hand-drawn cartoon animation with flat 2D illustration, clean black line art, flat solid colors, and cel-shaded artwork"
  },
  "subjects": {
    "ada": {
      "kind": "character",
      "name": "Ada",
      "design": "a nine-year-old girl with short curly black hair, a green raincoat, and yellow rain boots, drawn with thick confident outlines",
      "sheet": "../refs/ada/ada_sheet_4panel.png",
      "voice": "bright, quick, a little breathless"
    },
    "lantern": {
      "kind": "prop",
      "name": "the porch lantern",
      "design": "a dented brass hurricane lantern with a smoke-stained glass chimney and a wire handle",
      "sheet": "../refs/props/lantern.png"
    }
  },
  "locations": {
    "porch": {
      "description": "a wooden front porch at dawn, wet boards, a hanging lamp still lit, mist over the lawn beyond",
      "plate": "../refs/_bg/porch.png"
    }
  },
  "audio": { "mode": "generate" }
}
```

`Shows\ep01\ep01.md`:

```
= ep01  First Light

# sq01  porch

## sh010
who: ada
size: wide
dur: 3
Ada steps out onto the wet porch and stops, looking at the mist on the lawn.
camera: holds a static wide shot
sound: dawn birdsong, dripping water, a faint breeze

## sh020
who: ada
with: lantern
size: medium
dur: 4
Ada lifts the lantern off its hook and turns the flame down until it gutters out.
camera: holds static
sound: a metal hook ringing, the soft pop of a flame going out

## sh030
who: ada
size: close
dur: auto
Ada grins and pulls her hood up.
camera: pushes in with small amplitude at slow speed
ADA: It rained all night and nobody saw it but me.
sound: rustling raincoat, dripping water, distant birds
```

Build it with `seriesmith check Shows\ep01` and then `seriesmith build
Shows\ep01`; [INSTALL.md](../INSTALL.md) has the rest of the commands, and
`docs/SCRIPT_CONVERSION.md` works a real screenplay scene through to
shots if you are starting from one (the script-writing skill bundles it as
`references/script_conversion.md`); `docs/STORY_STRUCTURES.md` has the story structures
for outlining one from scratch (`references/story_structures.md`).

## Starting a series: what to settle first

The first episode above is the smallest series config that builds. A series that will be
finished (upscaled, mastered and published) needs a few more decisions. They're made once,
and they all live in the series config. Settle them before the first script: changing the
size later only changes the takes rendered after the change, and a master needs its
recipe before it can run.

| Decision | What to ask | Where it goes | With no answer |
|---|---|---|---|
| **Look** | Live action or animated? What should it look like (film stock, lens, palette, drawing style)? | `style.look` | Ask: there's no good default. See **Writing the `look` line** |
| **Delivery** | 1080p, 1440p or 4K? An exact 16:9 frame, or is H3's 7:4 fine? Fast iterations, or every take at full size? | `series.width` / `height`, `proxy`, `upscale.master` | Render at 1344×768 (it renders on every target with nothing extra installed) and master 1440p. See **Render size and delivery** |
| **Voices** | Generated from a description, cloned from voice samples, or lip-synced to dialogue you've recorded? | `audio.mode` (`generate`, `clone`, `source_track`), each character's `voice` / `voice_sample` | `generate` |
| **Finishing** | Clean up the upscale (edges, blocky motion) before the master? | `post` | `"enhance": "production"`, `"motion_blur": 0.3` for a 1080p or 1440p master; none for 4K. See **Post-process** |
| **Titles** | Is there a series intro and outro (clips made once for the whole show)? | `_titles/INTRO.mp4` and `OUTRO.mp4` in the show folder; `publish` only to name other files or style the episode title | Nothing to write: a master picks the clips up when they're there. See **Series intro and outro** |
| **Model** | Does it have to render on one model (what's installed, a hosted one)? | `series.target`, `series.first_target`, `refs` | Leave both out: the series renders on the machine's default models |
| **Pace** | How fast do people talk? | `speech.pace` | `normal` |

Ask these in **one message**, only the ones the brief doesn't already answer ("for
YouTube at 4K", "the voices are recorded" answer two). If the person would rather you
just start, use the defaults and say which ones you used. Then write the whole config:
the blocks below, not only the cast and the places.

A series rendered at size and mastered at 1440p, with generated voices, the finishing
pass, and the intro and outro picked up from `_titles/`:

```json
{
  "series": { "id": "last_light", "title": "Last Light", "fps": 24,
              "width": 1344, "height": 768 },
  "proxy": { "width": 960, "height": 544, "steps": 8,
             "lora": "minimax_h3_ref2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors" },
  "style": { "look": "a live-action film shot on 35mm, anamorphic lenses, sodium-vapour night light, wet streets, shallow depth of field" },
  "speech": { "pace": "normal" },
  "subjects": { },
  "locations": { },
  "audio": { "mode": "generate" },
  "upscale": { "save_latents": "final",
    "master": { "deliver": "1440p", "fit": "crop", "quality": "master",
      "finish": { "frequency_split": true },
      "targets": {
        "minimax_h3_*": { "method": "latent", "scale": 2 },
        "ltx2*":        { "method": "latent", "scale": 2 },
        "wan22_*":      { "method": "seedvr2", "seedvr2_model": "7b" },
        "*":            { "method": "pixel", "pixel_model": "RealESRGAN_x2.pth" } } } },
  "post": { "master": { "enhance": "production", "motion_blur": 0.3 } }
}
```

The other deliveries change the size and the recipe together (**Render size and
delivery**). Add `"fasth3_*": { "method": "latent", "scale": 2 }` beside the H3 section
when the series renders on FastH3 Omni.

**An existing series config** is the show's, not yours to restyle. Add the subjects and
locations a new episode needs, and change nothing else unasked. If it has no
`upscale.master` or `post` block, say once that the show can't be mastered by recipe
until it has one, and offer to add one.

## The one thing that shapes every decision

A screenplay is read once, front to back, by someone who remembers. A shot list is consumed
**once per shot, independently, by a model with no memory**. Shot 94 knows nothing about
shot 93. So:

- Every shot's action must stand on its own. "He keeps walking" means nothing — write
  "Riley walks down the dirt path, already halfway along."
- Never write "as before", "same as the last shot", "still holding the ball". State it fresh
  or it does not exist.
- Character descriptions live in the series config, written once, injected into every prompt they
  appear in. Never repeat a character's appearance in the script.

## Choosing a video target

| target | what pins the look | sound | keyframes | length grid | good for |
|---|---|---|---|---|---|
| `minimax_h3_ref2va` (default) | your sheets and plate, as four reference pictures | generated, dubbed to a recording, or cloned from voice samples | first, when the series' `first_target` sends its continuing shots to it (otherwise they go to H3 FL2VA) | `17k+5` frames at 24 fps | recurring characters who talk; lip sync to your recording |
| `fasth3_omni` | your sheets and plate, as up to nine reference pictures: eight subjects and the plate | as Ref2VA | not read | `17k+5` at 24 fps | crowded shots (up to eight characters, props and vehicles); FastVideo's 8-step H3, no turbo LoRA |
| `h3_singularity` | as Ref2VA | as Ref2VA | not read | `17k+5` at 24 fps | Ref2VA shots on AIGC-Singularity's fine-tune of H3 Ref2VA (its v2 pruned INT8: sharper highlights, distant faces, motion). A shot that asks for a first frame (`continuous: first`, a `first:` line) opens on it here, its pictures kept |
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
  workflow targets (`minimax_h3_ref2va`, `fasth3_omni`, `h3_singularity`, `minimax_h3_fl2va`). Wan acts the lines silently.
- **On a target that takes no reference pictures** (`ltx2`, `minimax_h3_fl2va`, `wan22_i2v`,
  `wan22_ti2v`; `wan22_vace` takes the sheets but not the plate), the `design` and location
  `description` sentences are what the model knows about the look, apart from any
  keyframe. Keep them complete.
- A keyframe is a picture: plan `first:` / `last:` lines (see **Keyframes**) for the
  targets that read them.

Details per target are under **Rendering a shot on …** below. A show can have models of
its own too (another hosted model, or a workflow saved in ComfyUI), named in `target:` like
any other.

## The series config: series.json

```json
{
  "series": { "id": "gold_path", "title": "The Gold Path",
              "fps": 24, "width": 1344, "height": 768, "steps": 8 },
  "proxy":  { "width": 896, "height": 512, "steps": 4, "audio_mode": "generate" },
  "style":  { "look": "a 2D hand-drawn cartoon animation with clean black line art, flat solid colors and cel shading" },
  "speech": { "pace": "normal" },
  "subjects": {
    "riley": {
      "kind": "character",
      "name": "Riley",
      "design": "an eight-year-old boy with cornrow braids, an oversized yellow hoodie, baggy grey shorts and worn high-top sneakers, drawn with thick confident outlines",
      "sheet": "refs/riley/riley_sheet_4panel.png",
      "voice": "fast, bright, always slightly too loud",
      "voice_sample": "audio/voices/riley_sample.wav"
    },
    "backpack": {
      "kind": "prop",
      "name": "Riley's backpack",
      "design": "a battered olive-green canvas backpack with two front buckles and a shoelace for a zipper pull",
      "sheet": "refs/props/backpack.png"
    }
  },
  "locations": {
    "street_gate": {
      "description": "a late-afternoon suburban street seen from the yard gate, dense treeline beyond, warm low sun raking in from the left and long shadows across the asphalt",
      "plate": "refs/_bg/street_gate.png"
    }
  },
  "audio": { "mode": "clone" }
}
```

- `style.look` opens every shot's description ("The target video is …"), so it sets the
  photography of the whole series. See **Writing the `look` line**.
- `kind` is `character`, `prop` or `vehicle`. Only characters speak.
- A character's `sheet` is a **four-panel strip** (three-quarter body, side, back, face),
  and a shot gets one panel of it: the three-quarter body, or the face on a one-character
  close-up. A picture you supply that is **one image** of the character (a portrait, a
  full-length shot on white) needs `"sheet_panels": 1`, or it is cut into quarters and the
  model gets a strip from its left edge. With it the picture is sent whole on H3 Ref2VA.
- **No picture yet.** A location with a `description` and no `plate`, or a subject with a
  `design` and no `sheet`, is described **in words** on H3 Ref2VA: it takes no Picture slot
  and nothing waits for a picture. That's fine for a one-off clip or a first try, but a
  series stays consistent through its pictures: without one, each shot imagines the place
  or the person its own way. Add the `plate` / `sheet` (and make the picture) when it
  should look the same every time.
- `members` makes a character a **group**: one picture of that many people (2–12), cast
  like any character and costing one slot. See **A group: the same extras every shot**.
- `of` makes the subject a **wardrobe variant** of another one — the same character in
  different clothes, the same prop in a different state. See **A wardrobe change is a new
  subject**.
- `audio.mode` sets how dialogue shots sound: `clone` (the model speaks the written lines in
  each character's sampled voice), `source_track` (you supply a recorded mix, `audio.track`,
  and shots dub to it; see `RECORDED_DIALOGUE.md`) or `generate` (the default: the model
  invents the voices from each `voice` line; no recordings or samples needed).
  `proxy.audio_mode` can use another mode for the animatic (`generate` is the usual one),
  `audio.default_policy` forces one policy for every dialogue shot, and `audio.retention`
  sets the dub `retention:` default. A target that can't do a mode says so and generates.
- `series.width` / `height` and the `proxy` block: **Render size and delivery** below.
- `steps`, `lora` and `model` are optional per pass (the model's own otherwise). `lora`
  takes one LoRA or a chain, as the script's `lora:` line does
  (`"lora": "turbo_8step.safetensors, soft_light.safetensors:0.6"`).
- `series.target` names the video model the episode renders on (one of the ids in
  **Choosing a video target**). Leave it out unless they want one in particular: the series
  then renders on this machine's default. `series.backend` says where its jobs run
  (`local`, `cloud`, `deployment:<target>`, `router`), else each model's own.

**Required and optional.** A series config must have `series` with an `id` and a `title`,
`style.look`, and `subjects` and `locations` blocks (either may be empty); every subject a
`name` and a `design` (or only a `voice`, for someone who is never seen), every location a
`description`. Everything else is optional, and left out means:

| Key | Left out |
|---|---|
| `series.fps` | 24 |
| `series.width` / `height` | the model's own (1344×768 on H3) |
| `proxy` | the model's own proxy (512×288 on H3: too small; write one) |
| `series.target` | this machine's default model |
| `audio.mode` | `generate` (`source_track` when `audio.track` names a recording) |
| `speech.pace` | `normal` |
| `refs` | Krea 2 for pictures, LTX-2.5 for voices |
| `upscale.master`, `post` | no recipe: the episode can't be mastered by recipe |
| a subject's `sheet`, a location's `plate` | described in words only (fine for a first try) |

### Render size and delivery

`series.width` / `series.height` is the size every final take renders at, and
`proxy.width` / `proxy.height` the proxy pass's. Sizes on H3 must be multiples of 32 on
both axes (**1280×720 is illegal**: 720 isn't); the other models snap a size to their own
grid. The four setups, and the master each delivers:

| Setup | final | proxy | delivers | for |
|---|---|---|---|---|
| **Render at size** (the default) | 1344×768 | 896×512 | 1344×768, or a 1440p master | anything; renders on every model with nothing extra installed |
| **Render small, master 1080p** | 960×544 | 864×480 | 1920×1080 (8 rows cropped) | the cheapest takes; mostly H3 shots, upscaled after the cut is locked |
| **16:9, master 1080p or 4K** | 1024×576 | 512×288 | 1920×1080 or 3840×2160 exactly | an exact 16:9 frame; many shots on LTX |
| **At size, master 1440p** | 1344×768 | 960×544, 8 steps | 2560×1440 (23 rows cropped) | live action with close dialogue, where faces need the pixels |

- 1344×768 is 7:4, H3's native canvas, not 16:9: a 16:9 delivery crops it slightly
  (`fit: crop`) or pads it with bars (`fit: pad`). Say so when someone names a 16:9 size.
- A proxy under 480 rows is too small to judge faces and hands by (16:9's 512×288 is the
  exception: H3's grid has no 16:9 size between it and 1024×576). Without a `proxy` block
  the proxy is the model's own (512×288 on H3), so write one.
- Changing the size later changes only the takes rendered after it; never change an
  existing series' size unasked.
- Why each setup, its timings, and the upscale methods are in [FINISHING.md](FINISHING.md).

```json
"series": { "id": "porchlight", "title": "Porchlight", "fps": 24, "width": 960, "height": 544 },
"proxy":  { "width": 864, "height": 480 }
```

### The master recipe: `upscale.master`

A **master** is the locked cut delivered at one size, every shot upscaled the same way.
The recipe says how, per video model (an id or a glob; the exact id wins, then the most
specific glob, then `"*"`):

- `deliver` (`1080p`, `1440p`, `4k` or `WxH`), `fit` (`crop` or `pad`), `quality`
  (`master` for delivery, `review` quicker).
- Per model: `method` (`latent`: re-sampled by the take's own model, the best for H3 and
  LTX; `pixel`: an upscale model, `pixel_model`; `seedvr2`: a restoration model,
  `seedvr2_model`), `scale` (a number, or `"auto"`: the smallest that covers `deliver`),
  `then` (an upscale model file, or `"seedvr2"`, after a re-sample).
- FastH3 Omni re-samples as H3 does but isn't `minimax_h3_*`: give `fasth3_*` its own
  section, or its shots fall to `"*"`.
- `upscale.save_latents` (`"final"`, the default) keeps each final take's latent so a
  re-sample can start from it.

One recipe per delivery; pick the one they asked for (1080p is the usual, 1440p for a
series rendered at 1344×768, 4K only when asked):

```json
"upscale": { "save_latents": "final",
  "master": { "deliver": "1080p", "fit": "crop", "quality": "master",
    "finish": { "frequency_split": true },
    "targets": {
      "minimax_h3_*": { "method": "latent" },
      "fasth3_*":     { "method": "latent" },
      "ltx2*":        { "method": "latent" },
      "wan22_*":      { "method": "seedvr2", "seedvr2_model": "7b" },
      "*":            { "method": "pixel", "pixel_model": "RealESRGAN_x2.pth" } } } }
```

- **1440p** (rendered at 1344×768): `"deliver": "1440p"` and `"scale": 2` on the H3,
  FastH3 and LTX sections.
- **4K** (rendered at 960×544 or 1024×576): `"deliver": "4k"`, `"then": "RealESRGAN_x2.pth"`
  on the H3, FastH3 and LTX sections, and `RealESRGAN_x4.pth` as the pixel model for Wan
  and `"*"`.

### Post-process: the `post` block

A clean-up pass over each upscale before the master (blocky edges and shadows, smeared
motion), then motion blur:

```json
"post": { "master": { "enhance": "production", "motion_blur": 0.3 } }
```

`enhance` is `production` (SeedVR2 7B, the one to use), `draft` (a quick upscale-model
sharpen), `cinematic` (SUPIR, very slow) or `none`; `motion_blur` is a fraction of the
frame interval (0.3 smooths blocky motion, 0.5 is a 180° shutter). Write it for a 1080p or
1440p master; leave it out for 4K (unmeasured there) or when they haven't asked.

### Series intro and outro: the `publish` block

The show's opening and closing are two clips made once for the whole series, not shots in
a script: `_titles\INTRO.mp4` and `_titles\OUTRO.mp4` in the show folder. Every master is
made with them when they're there, the episode's title (its `=` line) written under the
series title. Nothing to write unless the clips live elsewhere:

```json
"publish": { "intro": "../_titles/INTRO.mp4", "outro": "../_titles/OUTRO.mp4" }
```

An optional `subtitle` object sets the title's `font`, `size`, `y`, `color`, `glow` and fades.

### Render profiles

A profile is a named render setup for a kind of shot, so you set it once instead of
repeating `model:` / `lora:` / `steps:` on every shot. Declare profiles in the series config
and pick one with `profile:` under a `#` sequence header or on a `##` shot:

```json
"profiles": {
  "dialogue_close": { "model": "h3_finetune_faces.safetensors",
                      "loras": ["turbo_8step.safetensors", "soft_light.safetensors:0.6"],
                      "steps": 8 },
  "action_wide":    { "steps": 10 }
}
```

- Every key is optional: `target`, `model`, `loras` (a list of LoRA names; `name:0.6`
  sets a strength, `"none"` means no LoRA), `steps`, `sla`, and two that change the
  picture rather than the render: `look`, words added to the series look for these shots,
  and `lens`, a `lens:` value. Each shot's prompt opens with them (the look words, then the
  lens), so every model reads them. A shot's own `lens:` line still wins over its profile's.
- **A flashback, a dream sequence:** a profile is how a stretch of the story looks
  different without touching the series look:

  ```json
  "profiles": { "flashback": { "look": "a faded, desaturated memory with soft halation",
                               "lens": "vintage" },
                "dream":     { "look": "a hazy dreamlike glow, soft focus at the edges",
                               "lens": "shallow" } }
  ```

  then `profile: flashback` under the sequence's `#` header. Pair it with relit plates
  (**A relit plate is a location too**) for the flashback's light.
- A profile applies to both passes, like a shot's own `model:` line.
- **What wins**, from weakest to strongest: the series config's `series` / `proxy` block →
  the sequence's profile → the sequence's own `model:` / `lora:` / `steps:` lines → the
  shot's profile → the shot's own lines. So `profile: dialogue_close` plus `steps: 9` on a
  shot renders the profile's model and LoRAs at 9 steps. A `lora:` line replaces the
  profile's whole LoRA list.
- A profile name that isn't in the series config is an error.
- **The full model for the shots that need it.** H3's 8-step turbo is fast but weak on big
  camera moves (a pull out, a pan, a tilt from the rooftops), which it leaves faint or
  flickering. A profile with no LoRA renders those on the full model instead, H3's base
  preset (20 steps, `res_multistep`), about twice as slow; add `"sla": "off"` for the
  smoothest frames, slower again:

  ```json
  "profiles": { "full": { "loras": ["none"] },
                "full_smooth": { "loras": ["none"], "sla": "off" } }
  ```

  then `profile: full` on the shots with a big move (or `lora: none` on one shot, or
  `"lora": "none"` in the series config's `series` block for all of them).

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
installed, and what each still needs, is `seriesmith targets` ([FULL_SETUP.md](FULL_SETUP.md)).

### Reference images and voices: the `refs` block

The pictures (character sheets, props, plates) and shot keyframes are made by an image
model, a character's voice sample by an audio model. Leave the block out for the defaults
(Krea 2 for pictures, FLUX.2 Klein edit for keyframes when it's installed, LTX-2.5 for
voices), or name others:

```json
"refs": {"target": "krea2", "keyframe_target": "flux2_klein_edit", "voice_target": "ltx2_voice"}
```

The picture models, and what each needs installed, are in [FULL_SETUP.md](FULL_SETUP.md)
(**Pictures**). Two things matter when writing:

- A **variant**'s pictures (a subject with `of:`) are edits of its original's, on a model
  that reads reference images, so the face carries. On a text-to-image model (Krea 2) the
  variant is drawn from its `design` alone: write that sentence as close to the
  original's as the change allows.
- A character with no `voice_sample` still gets one: generating and picking a voice in the
  editor (or `seriesmith refs <ep> --voices`) writes `refs/voices/<id>.wav` and adds the
  `voice_sample` line to `series.json`. Don't invent a `voice_sample` path for a file that
  doesn't exist.

### Negative prompts

Targets that take a negative prompt (LTX-2, Wan 2.2 and the image models; not H3) use, most
specific first: the render request's, the shot's override (the editor, per pass), the
episode's **`negative.txt`** (a text file beside the script), the series config's
`"negative": "..."`, then the model's own. The take records which one it used. Turbo and
distilled models sample without guidance (cfg 1): there a negative does nothing, and the
take says so.

### Writing the `design` sentence

This is the highest-leverage sentence in the pipeline. It is injected verbatim into every
prompt the character appears in, and the model sheet is generated from it.

Describe **what a model sheet artist could draw**. Age and build, silhouette, hair, wardrobe
with specific colors, one or two distinctive accessories, line quality. Concrete nouns.

Weak: *"a mischievous kid with boundless energy who never sits still"* — none of that is
drawable, and it crowds out detail that is.

Lead with who they are (*"a young woman"*), then hair, then wardrobe and accessories; keep the
body to build and silhouette (*tall*, *stocky*, *slight*). Hosted models (Seedance, Kling,
Veo, Seedream, …) run behind their provider's content filter, and an explicit description of
a body is what it refuses: for those, seriesmith tells the model the design without it, in
the shot's prose and a reference picture's prompt alike (the pictures carry the look). Your
own ComfyUI's models get the sentence as you wrote it. A design that leads with clothes and
hair loses nothing either way.

Location descriptions work the same way and must include the light: time of day, direction,
quality. The plate is generated from that sentence. **Name the sources**: the pendant lamp
over the table, the chandeliers, the TV's glow, the streetlight through the blinds. A room
lit by things you can point at renders as a lit set, with pools of light and shadow
between them; "warm lighting" renders as an evenly lit showroom.

### Writing the `look` line

`style.look` is the first sentence of every shot's description, so it is the series'
photography. Write it the way a director of photography would brief a crew: what the lens,
the focus, the light and the film stock do. Adjectives about quality ("cinematic",
"beautiful", "high quality") give the model nothing to draw.

Weak: *"a cinematic prestige drama with moody lighting"*.

Strong: *"a naturalistic live-action prestige drama shot on 35mm anamorphic lenses: shallow
depth of field with the background falling into soft bokeh, low-key practical light with pools
of light and deep soft shadows, lifted blacks, muted desaturated color and fine film grain"*.

**Leave people and places out of it.** The look also opens every reference picture's
prompt, a place's empty plate included, and every shot's. Words about characters, faces,
figures or skin ("soft rounded character design with expressive faces") draw people into a
place that should be empty; words about places or things ("night streets lit by neon
signs", "practical lamps in each room", "luminous skies") draw those in, or fight the
shot's own place (a lighthouse gallery asked to be a neon street). Say how things are lit
and rendered (soft rounded forms, magenta and cyan light, warm tones) and let the cast and
the locations bring the people and the places. A picture's whole prompt, look and all, is under **What the model is
told** in its row in Refs.

**Name the light's quality, not its sources.** "Practical light from the windows and candles"
asks every shot for windows and candles, and a close-up is framed wider to fit them in or has
them invented behind the face. In one H3 test, an extreme close-up asked for "eyes and mouth"
came out a close-up, hairline to collar with candle flames behind, until only that clause of
the look changed to "soft practical light". On the same seed it was then eyes to lips, with
nothing behind but the plate's blur, and a wide of the same room lost nothing but an invented
chandelier. Write "low-key practical light, pools of light and deep soft shadow"; the
windows, candles and lamps go in each location's description, where the shots that see them
read them. `seriesmith check` warns when a look (the series' or a profile's) names a light
source. (`style.look_parts` is the editor's look builder's own record; only `style.look`
reaches a prompt.)

Each clause is something the model can see: shallow focus and bokeh separate the subject
from the room and soften what the model draws worst, low-key practical light gives the frame
contrast and shape, and grain gives the image the texture of film. Keep it to one sentence;
the per-shot light belongs in the location descriptions and the action.

### A location is one angle, not one place

One plate per location means every cut rebuilds the same view, and characters appear to pop
into an unchanged picture instead of being discovered by a camera. Author two to four angles
per place and let each shot name its own with `plate:`:

```
office_desk    the desk against the wall, bulb overhead
office_lid     looking up at the propped lid and the moonlight
office_boxes   the wall of file boxes
office_wide    the whole interior at once
```

**Time of day is part of the location.** `street_day` and `street_night` are two entries with
two plates, because the plate carries the light.

**Write the angles as one place.** Each plate is drawn from its own `description`, so unless
those sentences share fixed features they describe several rooms with the same name rather
than one room from several sides. Anchor every angle to the same things: *"the kitchen from
the hallway door, sink under the window on the left, the living-room arch behind camera"* and
*"the kitchen from the sink, the hallway door on the right, the arch beyond it"*. That is what
makes the geography hold together across a cut.

**Tie the angles to one master with `of`.** Words alone still give each angle its own
walls and furniture. Give one entry the plate you like (the master) and mark the others as
angles of it:

```json
"ambulance_bay_night":    {"description": "the ambulance bay of a county hospital at night ...",
                           "plate": "../refs/_bg/ambulance_bay_night.png"},
"ambulance_bay_on_drive": {"of": "ambulance_bay_night",
                           "description": "looking back down the covered drive from the doors ...",
                           "plate": "../refs/_bg/ambulance_bay_on_drive.png"}
```

- An angle inherits nothing. It keeps its own `description` and `plate`, and shots still name
  it with `plate:`.
- On an edit model (Klein, Qwen, Rapid AIO, H3 still), an angle's plate is generated **from
  the master's plate**: the same building, materials and light, with only the camera moved.
  On a text-to-image model (Krea 2) it is drawn from its words as before.
- An angle's master must be a location that isn't itself an angle.

**A relit plate is a location too.** The same view under another light (the street at dusk
for a flashback, the porch at night) is a location with `of:` and `relight:`, a relight
preset's id (`dusk`, `night`, `rain`, `neon`, …) or the instruction in your own words:

```json
"street_dusk": {"name": "Street (Dusk)", "of": "street", "relight": "dusk",
                "description": "a wet night street ... It is dusk, a deep blue evening sky ...",
                "plate": "../refs/_bg/street_dusk.png"}
```

- On an edit model its plate is made **from the source's plate** with that relight: the
  same place, only the light changed. Its description should carry the new light, since
  shots read it.
- Name it like any location: `# sq04 street_dusk`, or `plate: street_dusk` on a shot.
- The source may be an angle; a relit plate's source can't itself be relit.
- The editor can also make these from the plates (Relight on a sequence; a 360 panorama or a
  camera tour of a master for its angles' pictures): in a config you only name them.

### Two people talking need an angle each

This is the one that spoils scenes most often, and the build warns about it:

```
sequence sq11: Skye and Dr. Walter each get their own shot on the same plate (cafe_couch), so
they are drawn against one background from one view and the cut reads as a single camera
rather than a reverse angle. Give the location an angle per speaker and name it with `plate:`.
```

One plate is one picture. Two singles built on it are drawn against the same background from
the same view, so cutting between them looks like one locked-off camera that people step into
and out of — not a conversation. No wording fixes it, because the plate is a picture and the
prompt is only words.

Author the scene as three entries and name one per shot:

```
cafe_couch          the whole seating area, both of them in it — the establishing shot
cafe_couch_on_skye  past Walter's shoulder to Skye on the left of the couch, window behind her
cafe_couch_on_walt  past Skye's shoulder to Walter in the armchair, the counter behind him
```

```
## sh768
who: skye, walter
plate: cafe_couch
size: medium
dur: 3.04
They settle in with their cups.

## sh772
who: skye
plate: cafe_couch_on_skye
size: close
dur: 2.33
Skye watches him over the rim of her cup, her eyes off to frame right where he sits.
SKYE: You're early.
```

**Keep them on one side of the line.** Decide who sits on which side and keep it: if Skye is
on the left of the two-shot, she stays screen-left in her single and looks off to frame
right, and Walter looks off to frame left. Write that into the **action** line — *"her eyes
off to frame right where he sits"*, *"he answers without looking up, his eyes down and to
frame left"*. There is no field for it; the action sentence reaches every target's prompt and
is where a real script would put it anyway. Without it a model does what it was trained to do
and talks to the camera.

The same applies to a character alone in a room who is meant to be aware of someone off
screen: say where they are looking, and say that it is not at the camera.

### A wardrobe change is a new subject

The same idea for people. A character's clothes live in their `design` sentence and in their
model sheet, so a character who changes clothes is a second subject with `of:` — a
**variant** — not a note in the action line:

```json
"gina": {
  "kind": "character", "name": "Gina", "design": "a woman in her forties, dark hair cut short, a grey mechanic's coverall over a black tee, steel-toed boots",
  "sheet": "refs/gina/gina_sheet_4panel.png",
  "voice": "low and dry, never hurried",
  "voice_sample": "audio/voices/gina_sample.wav"
},
"gina_towel": {
  "of": "gina",
  "design": "a woman in her forties, dark hair cut short and soaked flat, a white bath towel wrapped and tucked at the chest, bare feet"
}
```

A variant needs exactly two lines: `of:` and its own `design`. Everything else — `kind`,
`name`, `voice`, `voice_sample` — is inherited, so one character still has one
voice, and a `sheet` path is derived from the original's (`refs/gina/gina_sheet_4panel.png`
becomes `refs/gina/gina_towel_sheet_4panel.png`). Give it its own `sheet` line to put it
somewhere else. Generate that sheet like any other reference; starting from the original's
approved views holds the face far better than generating it cold.

In the script, name the variant where it is on screen and go on calling the character by
their name:

```
## sh120
who: gina_towel
size: medium
dur: 3.04
Gina leans out of the bathroom door, one hand on the frame.
GINA (low): Don't come in.
```

`who:` takes the variant; `GINA:` still speaks, and the line is given to whichever of her is
in the shot. A shot names one or the other, never both, and never two variants of the same
subject — cut the shot where the change happens.

**Why not a `wear:` line on the shot?** Because the reference sheet would still show the old
clothes, and the prompt would have to argue with the picture. H3 preserves a subject as a
whole — its `fully_preserved` marker covers face, hair, proportions *and* wardrobe — so the
only way to contradict the sheet is to weaken the whole subject, which loosens the face in
order to change the clothes. A variant keeps the identity lock and swaps the picture. It also
costs nothing on the other targets: LTX-2 and Wan have no reference images and read the
`design` sentence, which is already the variant's.

A variant is for a state a shot is *in*, not a change it *makes*.

### Never show the change itself

No video model today can take a hat off, pull on a glove or shrug out of a jacket and keep it
off. The item comes back, doubles, or melts into the hands, and the next shot puts the sheet's
version straight back on him. So **a shot's wardrobe is fixed from its first frame to its last,
and it is what the subject's sheet shows.** Don't write dressing or undressing into an action
line: not taking off a hat, gloves or glasses, not hanging up a coat, not stepping into
coveralls or tying on an apron. Small things matter most, because they are the easiest to
forget. A mesh glove pulled off in one shot is back on in the next, because nothing told the
next shot it was gone.

When the story needs the change, cut around it:

- **Start it, then cut.** Show only the beginning (his hand going to the brim, fingers on the
  zipper) and end the shot there. The next shot is already in the new state.
- **Land on an insert.** Cut to the item or the hands, not the face: the hard hat held against
  his chest, framed below the chin, or a bare forearm hanging the navy jacket on a locker hook.
  Make the item a prop (`with: hard_hat`) and keep the character out of `who:`, or frame it
  tight enough that only the hands show. An insert has no face to drift and needs no new sheet.
- **Cut away.** Go to the other character's line or reaction, then come back to the variant.
- **Change off screen.** End one scene in the old clothes and open the next in the new ones.
  Luis walks into the locker room in his jacket, and the next scene finds him on the line as
  `luis_plant`.
- **Don't change at all.** The gesture is often not needed. Glasses can be looked over or
  pushed up instead of taken off, and a man can fold his hands and wait with his hat still on.

Once the new state is on screen it holds. Every later shot of that character names the
variant until another cut brings the old clothes back, so add the variant (a design sentence
that says what is gone: "no hard hat, a hairnet over short grey hair") before writing the
shots that need it. Its sheet is an edit of the original's views, so it's cheap.

For example, the hat coming off in Kemp's office. Written as an action, the hat is on again
two shots later:

```
## sh320
who: luis_plant
Standing just inside the door, Luis takes off his hard hat and holds it in both hands, ...
```

Instead, let Kemp's shot before it be the cut-away, and have Luis enter his next shot already
bareheaded, holding the hat as a prop:

```
## sh320
who: luis_plant_bareheaded
with: hard_hat
Standing just inside the door, Luis holds his hard hat in both hands against his chest, ...
```

and every later shot of him in the office is `luis_plant_bareheaded` too.

## The script: epNN.md

```
= ep01  The Gold Path

# sq01  street_gate

## sh010
who: huey
size: wide
dur: 3.04
Huey drifts to a stop at the edge of the yard and looks off down the empty street.
camera: pushes in on him at slow speed
sound: late-afternoon suburban ambience, distant birds, a faint breeze

## sh020
who: riley, huey
with: backpack
size: medium
dur: 4.46
plate: street_yard
Riley runs into frame from the left and pulls up hard beside Huey.
Huey does not turn his head.
camera: arcs around behind them with small amplitude at slow speed
RILEY (breathless): There's gold at the end of the path.
HUEY (flat): There is not.
MOM (V.O.): Shoes off in the house!
sound: running footsteps on grass, fabric movement
```

| Line | Meaning |
|---|---|
| `= id  Title` | episode header, once at the top |
| `# sqNN  location` | sequence; the location must be a series config key |
| `## shNNN` | a shot. **Every `##` is a cut** — no `CUT TO:` needed |
| `who: a, b` | characters on screen, in this order (on H3 Ref2VA they become `<Picture 1..3>`); `cast:` is the same |
| `with: x, y` | props and vehicles, after the characters; `props:` is the same |
| `size: mcu` | shot size, from extreme close-up to extreme wide (`ecu`, `cu`/`close`, `mcu`, `ms`/`medium`, `cowboy`, `mws`, `fs`/`full`, `ws`/`wide`, `ews`), or an angle (`pov`, `ots`, `low`, `high`); the full names work too. Opens the shot's prompt as its framing ("A medium close-up frames… from the chest up"), and decides how much of the location and of the sheet is used. See **Faces need room** |
| `plate: street_gate` | this shot's angle; defaults to the sequence's location |
| `dur: 3.04` | duration in seconds, from the grid below (`duration:` is the same) |
| `dur: auto` | derive the duration from the dialogue at this shot's pace |
| `dur: model` / `dur: model 3-8` | let the video model choose the length when it renders, optionally between 3 and 8 seconds; see **Letting the model time a shot** |
| `audio: 3.10-7.40` | window on a locked dialogue mix; sets the duration instead |
| `pace: slow/normal/fast` | 3.6 / 4.4 / 5.4 syllables per second |
| `camera: pushes in…` | camera move, **without** the words "The camera" |
| `sound: …` | ambience and physical action sounds |
| `music: …` | audience-only score; omit for none |
| `extras: …` | other people in frame, described; see **Crowds and extras** |
| `text: OPEN 24 HOURS` | on-screen text the picture must show (a sign, a note, a screen), quoted into the prompt. Never the series title or credits: those are added in the edit, not rendered into a shot |
| `policy: generate` | this shot's audio: `generate` (the model makes all of it), `dub` (lip sync to the recording's `audio:` window, which becomes the soundtrack), `dub_keep_foley` (the same, keeping the model's sound effects under it) or `clone` (spoken in each speaker's `voice_sample`). Without it, dialogue shots follow `audio.mode` and silent ones generate |
| `retention: partially_copy` | how closely a dubbed shot copies the recording: `fully_copy`, `partially_copy` or `reference` (H3 Ref2VA; dub shots only) |
| `model:`, `lora:`, `steps:` | per-shot render overrides; also valid under a `#` header. `lora:` takes one LoRA (`soft_light.safetensors`, `soft_light.safetensors:0.6` for a strength) or a chain of them separated by commas, applied in that order (`lora: turbo_8step.safetensors, soft_light.safetensors:0.6`); `lora: none` for none: where the pass's LoRA is a turbo (H3's), that renders the full model, the pass's base preset (20 steps, `res_multistep` on H3); a shot's own `steps:` still wins |
| `sla: off` | H3's sparse attention (PlagueKind's `H3SLAAttention`) left out: about 40% slower, a little smoother frame to frame. Also under a `#` header, in a profile (`"sla": "off"`) or for the series (`"sla": "off"` in its `series` block); `on` is the default |
| `lens: shallow` | the lens the shot is shot on: `spherical`, `anamorphic`, `vintage`, `wide`, `long`, `shallow`, `tilt_shift` or `deep` (the look builder's Lens row). The action opens with its words ("Shallow depth of field: the subject sharp, the background falling into soft bokeh."), so every model reads it. Also under a `#` header, for its shots. Shallow focus shows the most; with a plate as the reference, the plate keeps its own geometry and the rest show less |
| `profile: dialogue_close` | a render profile from the series config; also valid under a `#` header |
| `target: ltx2` | the video model for this shot or sequence (`minimax_h3_ref2va`, `fasth3_omni`, `ltx2`, `ltx2_ingredients`, `ltx2_msr`, `minimax_h3_fl2va`, `wan22_i2v`, `wan22_ti2v`, `wan22_vace`, a hosted model such as `seedance_2_5`, `hold` for a picture held still, or a show's own); see below |
| `first: generate` / `last: refs/x.png` | how this shot's first / last keyframe is made: `generate`, `import`, `none`, or a path to an image; also valid under a `#` header (the default of its shots); see **Keyframes** |
| `continuous: first` | this shot carries straight on from the previous one in the cut: `first` (open on its last frame) or `latent` (hold the previous take's last frames and carry on from them); `multishot` renders it in one generation with the shot before (see **Several shots in one generation**); under a `#` header, every shot after the sequence's first; `none` breaks the chain; see **Continuous shots** |
| `overlap: 39` | frames of the previous take a `continuous: latent` shot holds (39, the default, is right almost always; any other number rounds up to 22, 39, 56, 73, ...); also valid under a `#` header |
| `NAME: line` | dialogue from someone on screen (the name is a character's key, in capitals) |
| `NAME (breathless): line` | a delivery direction, written into the prompt |
| `NAME (V.O.): line` | voiceover: speaks, is not drawn, costs no reference slot |
| `NAME (O.S.): line` | off-screen: in the space, outside the frame |
| `NAME (V.O., on the truck radio): line` | a voice marker and a delivery together; the note describes the voice and is never spoken |
| `// text` | comment |

Any other line is action prose. Prose under a `#` header before its first shot is a
scene-setting note and is ignored. A line under a `#` header (`model:`, `lora:`, `steps:`,
`profile:`, `target:`, `first:`, `last:`, `overlap:`) is the default for every shot in the
sequence (`continuous:` for every shot after the first); a shot's own line beats it.

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
- H3 Ref2VA, FastH3 Omni and `ltx2_ingredients` don't read them.

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

### Continuous shots: `continuous:`

A shot that carries on from the one before it says so, and how. There are three ways, and
they answer different needs:

| `continuous:` | What it does | Use it for | Renders on |
|---|---|---|---|
| `first` | opens on the previous shot's last frame | picking up exactly where a shot ended, on almost any model | every model that reads a first frame; H3 Ref2VA's and FastH3 Omni's move to their FL2VA |
| `latent` | holds the previous take's last 1.6 s (picture and sound) and goes on from them | one unbroken take built from several renders: the camera and the action keep running, no cut | H3 Ref2VA, FastH3 Omni, H3 Singularity; the shot it continues can be from any model |
| `multishot` | renders it **in the same generation** as the shot before: one clip with cuts in it | a scene cut between angles, where the model sees every shot at once | the H3 family (Ref2VA, FastH3 Omni, FL2VA, Singularity), Seedance, Kling v3 Omni, Kling O1 |

`first` and `latent` make a **continuous take**: each shot is its own render, joined so the
cut doesn't show. `multishot` makes **real cuts inside one render**: the model draws a shot,
cuts, and draws the next, keeping the people, the light and the blocking the same across
them because it sees them all at once.

```
## sh090
continuous: first
```

- Only the shot that continues says it, and "previous" is the previous shot in the cut.
- Under a `#` header, `continuous:` covers every shot after the first **in that sequence**.
  A shot breaks the chain with `continuous: none`.
- Use `first` or `latent` only when the shot really picks up the previous picture (the same
  framing carrying on, a match on action). After a real cut (a new subject, a new angle, a
  different size) leave it off.

**`first`.** A shot on a model that reads a first frame (LTX-2, Wan, the hosted ones) stays
on it. One on H3 Ref2VA moves to H3 FL2VA, and one on FastH3 Omni to its own FL2VA, unless
the shot names its own `target:`. FL2VA draws everyone from words, without their pictures.
H3 Singularity opens on the frame itself with its pictures kept, and so can Ref2VA with
`"first_target": "minimax_h3_ref2va"` in the `series` block (`"h3_singularity"` sends the
continuing H3 shots there instead).

**`latent`.** The render holds the end of the previous take at its head and generates the
rest from there, so motion, sound and the camera carry across the join; the held frames are
cut off again, so the take starts where the previous one ended. It keeps its own pictures.
The previous shot can be on any model: when it isn't H3's, its last frames are encoded
instead (a silent one, such as Wan, holds no sound).

- **Keep the framing and the camera move the same across a latent chain**, and open each
  shot's action on what the held frames show. A shot that asks for a new size, a new move or
  a new place in the room is read as a new shot, and H3 cuts to it right after the held
  frames.
- **Over a long chain, prefer `latent` to `first`.** Every latent shot gets its pictures
  again, so the look stays anchored; a `first` shot on FL2VA has only the frame it opens on,
  so whatever drifts in one shot is where the next starts. In a ten-shot test of one man
  pacing a room, the latent chain held its brightness (36 to 39 of 255) while the FL2VA
  chain climbed to 90, doubled its contrast and redrew the room.
- **`overlap:`** is how many frames are held: leave it at the default, 39 (1.6 s). Fewer
  give H3 too little motion to carry on; more cost time for nothing. Any other number rounds
  up to H3's next (22, 39, 56, 73, …). Per shot, under a header, or for the series:
  `"continuous": { "overlap": 39 }`.
- A latent shot costs about 40% more render time, and its take can run up to 0.7 s longer
  than its `dur:`.

### Several shots in one generation: `continuous: multishot`

`continuous: multishot` on a shot renders it **in one generation with the shot before it**.
A run of such shots, with the shot they follow, is a **group**: the model sees the whole
scene at once, so blocking, light and performance carry across the cuts, and the same
people come back after a cutaway as themselves.

```
## sh040
who: stepmother, mia, ava
size: ms
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

- **Every shot stays a shot in the script**, with its own `who:`, `size:`, `dur:`, action,
  lines and `sound:`. Under a `#` header it groups every shot after the sequence's first;
  `continuous: none` starts a new group. A group never crosses a `#`.
- **It renders as one take**, under the group's first shot, its length the shots' `dur:`
  together. The model lands its cuts near the script's times: H3 within about half a second,
  Kling v3 Omni within about a second, Kling O1 to the frame; Seedance times them itself.
- **Limits:** Kling, at most 6 shots and 15 s; Seedance 2.5, 30 s (2.0: 15 s). `check`
  refuses a group on a model that renders one shot a call (Veo, Runway, Wan, LTX).
- **One set of pictures for the whole generation**: every person in the group once (a
  wardrobe variant in a later shot isn't sent), up to the model's slots (FastH3 Omni eight,
  Ref2VA three: background people can be one group subject, `members`), and **one plate**,
  the first shot's (Seedance: every shot's). A close-up on another plate is drawn as a
  blurred crop of the one sent; a wider shot on another plate gets its place in words.
- **A group can carry on from the shot before it** with `continuous: latent` on its first
  shot. `continuous: first` works too, but renders the group from words and that frame,
  without its pictures.
- **Sound is generated**: a dubbed or cloned shot can't be in a group.
- It is no fix for a jump cut: two near-identical shots in one generation still cut as one.

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
| `h3_singularity` | Singularity | your ComfyUI | 3 subjects + the plate | first, when the shot asks | `<Subject N>` … `<Picture N>` |
| `h3_singularity_fl2va` | Singularity FL2V | your ComfyUI | none | first and last | — |
| `hold` | Hold | this machine | none | first | — |
| `ltx2` | LTX-2 | your ComfyUI | none | first and last | — |
| `ltx2_ingredients` | LTX+refs | your ComfyUI | one sheet tiled from the subjects and the plate | — | by their order |
| `ltx2_msr` | LTX+MSR | your ComfyUI | 4 subjects + the plate | — | `Image N`, by their order |
| `minimax_h3_fl2va` | H3 FL2V | your ComfyUI | none | first and last | — |
| `minimax_h3_ref2va` | H3 | your ComfyUI | 3 subjects + the plate | first, when the shot asks | `<Subject N>` … `<Picture N>` |
| `wan22_i2v` | Wan I2V | your ComfyUI | none | first and last | — |
| `wan22_ti2v` | Wan 5B | your ComfyUI | none | first | — |
| `wan22_vace` | Wan+refs | your ComfyUI | one picture made from the subjects' sheets | first and last | by their order |
| `flux_3_video` | FLUX 3 | Comfy Router | none | first and last | — |
| `kling_v3_omni` | Kling | Comfy Router | up to 7: the subjects, then the plate; as links | first and last | names each: `<<<image_N>>>` is … |
| `kling_video_o1` | Kling O1 | Comfy Router | up to 4: the subjects, then the plate; as links | first and last | names each: `<<<image_N>>>` is … |
| `minimax_h3` | MiniMax | Comfy Router | up to 4: the subjects, then the plate; as links | first and last | by their order |
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

## Durations land on a grid

Every video model takes only certain frame counts, and a `dur:` between two of them rounds
**up**, so you pay for frames you throw away. The grid is the target's: `17k + 5` frames on
the H3 targets, `8k + 1` on LTX, `4k + 1` on Wan (at 24 fps; best kept to 3 s), whole
seconds in each model's range on a hosted one. The build
snaps each shot to its own target's grid, and `--check` warns about wasted padding.

Write for H3's grid, the default; the other grids are fine-grained enough that these
lengths land close on them too. At 24fps these are free on H3:

| Frames | Seconds | Use for |
|---|---|---|
| 39 | **1.62** | a single word, a snap |
| 56 | **2.33** | a quick reaction, one short line |
| 73 | **3.04** | the workhorse shot |
| 90 | **3.75** | a beat with a little air |
| 107 | **4.46** | two lines of dialogue |
| 124 | **5.17** | a long beat, a small piece of business |
| 192 | **8.00** | rare: a sustained action run |

Render cost scales as roughly `duration^1.29`, so long shots are *less* efficient per second
than short ones. Cartoon pacing, 2 to 5 seconds, is both better filmmaking and cheaper.

## Dialogue has to fit the shot

This is the easiest way to wreck an episode, and it does not announce itself: a model that
speaks (H3, LTX) will fit any line into any window by speeding the delivery up. The words
are all there, the lip sync is fine, and the performance is gone. On Wan, which acts the
lines silently, the recording laid in at the edit still needs the room.

A 2.33s shot holds about **seven syllables**. Never guess — the compiler measures it:

```
seriesmith build series.json ep01.md --pace
```

Three ways out of a crammed shot, in the order worth trying:

1. **Split it.** A line needing six seconds usually wanted a reaction cut in the middle
   anyway, and the split buys the second angle the scene was missing.
2. **Cut words.** Over-packed shots are usually over-written.
3. **Lengthen it.** `dur: auto` derives the length and snaps it to the grid.

`pace: fast` marks a rush that is deliberate and silences the warning.

## Camera moves use H3's vocabulary

Every target inserts the `camera:` line after the words "The camera", so write the verb
phrase only. Without one, the camera holds still. The vocabulary below is H3's training
vocabulary; the other models read it as plain English.
Compose from **motion + amplitude + speed**; the last two are optional.

**Motion:** zooms in / out · pushes in / pulls out · pans left / right · trucks left / right ·
tilts up / down · pedestals up / down · arcs around · tracks · holds a static shot · shakes
slightly / strongly · takes the subject's POV · rolls clockwise / counterclockwise

**Amplitude:** with small amplitude · with large amplitude
**Speed:** at slow speed · at fast speed

**Say where the move goes.** A move alone tells the model how the camera travels, not what
the frame should hold at the end, and a bare `pulls out` often barely moves. Finish the line
with what it travels toward or reveals, the way H3's own prompt guide writes every move:

```
camera: pushes in with small amplitude at slow speed toward the folded letter in her hands
camera: pulls out with large amplitude at slow speed, revealing the whole square around her
camera: pans right with large amplitude at slow speed from the cafe along the street to the station
camera: tilts down at slow speed from the rooftops to her standing by the bench
camera: trucks left at slow speed along the shop fronts, the street lamp sliding past in the foreground
```

A large move wants `at slow speed`: a large, fast one can flash or smear on the way. A truck
or a pedestal reads by what slides past in the foreground (parallax), so name something
there. For what a character sees, use `size: pov` and say in the action whose eyes they are.

"Arcs around them with large amplitude at fast speed" beats "swoops around dramatically",
because it names a move the model was trained on.

Film terms translate into that vocabulary:

| You mean | Write |
|---|---|
| dolly in / dolly out (back) | `pushes in…` / `pulls out…` |
| slide, crab | `trucks left…` / `trucks right…` |
| pivot, swivel | `pans left…` / `pans right…` |
| whip pan | `pans right with large amplitude at fast speed` |
| crane / jib up or down | `pedestals up…` / `pedestals down…` |
| orbit | `arcs around <name>…` |
| follow, lead | `tracks <name> as she walks…` (in front of or behind, in the action) |
| handheld | `shakes slightly` |
| over the shoulder | not a move: `size: ots`, with both in `who:`, and say whose shoulder in the action ("over Ada's shoulder, Bo faces camera") |
| rack focus | not a move: say it in the action, "the focus shifts from the cup to Ada's face" |

Staging (where people stand, who faces camera, how a scene's angles cut together) is the
director's craft and is best learned from a book like Christopher Kenworthy's *Master
Shots*; this guide covers only how to say the result to the model.

On a wide full of big architecture (a plant, a street front, a church), prefer holding still,
a pan or a slow push over a track, truck or arc. A camera that moves through the space makes
the model redraw the buildings as it goes, and they build and unbuild themselves on screen.

## Breaking a scene into shots

A scene with three paragraphs of action is six to ten shots, and deciding where they fall is
the job.

**Cut when** the subject changes, a new beat lands, someone new speaks, time skips, or the
framing must change materially. **Don't cut** when only the distance shifts a little — use a
camera move. A cut should bring new information; a cut to the same thing slightly closer is a
jump cut, and it will render as one (see **Cutting within a location**).

A workable rhythm for a dialogue scene: wide establishing → medium two-shot for the exchange →
close on the reaction that matters → back out. Keep the wide short and empty of anything
that has to read on a face (see **Faces need room**).

**Open every shot on movement.** The model has no memory of the previous cut, so a shot whose
action describes a *position* renders that position and then looks for something to do with
it. Write the state change: "Dex swings his boots onto the desk and settles back", not "Dex
sits with his boots on the desk".

### Faces need room

`size:` is written into the prompt as the shot's framing (`A close-up frames <Subject 1>…`,
`A medium shot frames…`, `A wide shot takes in…`), so it is what the model frames, not a
label. Choose it by what the shot has to show:

| `size:` | Framing | Holds | Use it for |
|---|---|---|---|
| `ecu` | extreme close-up | one detail: the eyes, a hand on the latch | an insert; tension |
| `cu` (`close`) | close-up | the face, chin to hairline | the reaction or line that matters |
| `mcu` | medium close-up | chest up | **most dialogue**: face and a little body language |
| `ms` (`medium`) | medium shot | waist up | two-shots, business at a counter |
| `cowboy` | cowboy shot | mid-thigh up | standing confrontations, a hand at the hip |
| `mws` | medium-wide shot | knees up | walking and talking, a figure with their surroundings |
| `fs` (`full`) | full shot | head to toe | a whole-body action: a trip, a dance step, a fall |
| `ws` (`wide`) | wide shot | the subject in the room | geography, entrances |
| `ews` | extreme wide shot | the subject small in a big setting | scale, isolation, establishing a place |
| `pov` | POV shot | what a character sees, through their eyes | discovery, a threat approaching, reaching for something |
| `ots` (`over-the-shoulder`) | over-the-shoulder shot | past one person's shoulder onto the other | dialogue coverage, a confrontation; put both in `who:` |
| `low` (`low-angle`) | low-angle shot | the subject seen from below | power, menace, a hero moment |
| `high` (`high-angle`) | high-angle shot | the subject seen from above | weakness, isolation, a fall seen from the top |

The last four are angles, framings H3's guide names beside the sizes: they say where the
camera looks from rather than how much it holds, act like a medium for the plate and the
sheet, and are never counted as a jump cut against another size. Say the distance in the
action when it matters ("a low-angle close-up of his face", "a high-angle wide of the square").

The full names work too (`size: medium close-up`), and so do `ls` (long shot) and `els`. The
in-between sizes put what the frame holds into the prompt ("from the chest up"), so a model
that doesn't know the term still frames it. For the plate and the sheet, `ecu`/`mcu` act like
a close-up, `cowboy`/`mws` like a medium, and `fs`/`ews` like a wide.

**A face needs pixels to have a face.** H3 draws in cells of 16×16 pixels. On a wide of a
standing person, the face is a few cells across, too few for eyes and a mouth: it comes out
soft and smeared, and an upscale sharpens the smear rather than finding the face. At 960×544
it is worse than at 1344×768. Measured on a 1344-wide full-body walk, the face was 50 pixels
tall: three cells.

- **Dialogue, reactions, and anything the audience must read on a face: `mcu`, `cu`, or
  `ms`.** A medium close-up gives the face a few hundred pixels at 960×544; a close-up fills
  the frame with it.
- **Wides (`fs`, `ws`, `ews`) carry geography, entrances, crowds and big physical action**,
  where nobody's expression has to read: a figure crossing a room, a back to camera, two
  people seen from across a lot. Don't hold a wide on a face and expect the face to be there.
- **Cut in for the face.** A fall, a collision or an entrance plays as `fs` for the action →
  `cu` on the face that reacts → `mws` or `ms` for the result, not one wide shot that holds the
  face at a distance.

The prompt also scales the location to the framing: a wide describes the whole place around
the subjects, a medium the part behind them, a medium close-up a magnified, softly focused
slice of it, and a close-up or an extreme close-up (`cu`, `ecu`) a tightly cropped portion of
the plate, completely blurred into soft bokeh. On H3 Ref2VA that last is named by its picture
alone, without the location's description, so the model isn't asked to draw the room. That is
why a close-up on H3 has the room behind the face, blurred, and not a studio backdrop.

**When the room still shows behind a close-up.** The blur is words, and the model follows the
plate's picture more than the prompt: a sharp plate still comes through, windows and candles
and all. For a close-up that must have nothing behind the face but soft bokeh, make its
background yourself:

1. Find where the subject's head sits in the plate (behind Cindy, the open doorway; behind
   Charming, the fireplace wall).
2. Crop a patch of the plate there, in the frame's shape: about an eighth of the plate's
   width for an `ecu`, a fifth for a `cu`.
3. Scale it up to the render size and blur it heavily, until nothing in it has an edge.
4. Give it a location of its own, an angle of the place (`of:`), with a description that names
   nothing in it, and name it with `plate:` on the shot:

```json
"hall_bokeh_cindy": {"of": "hall",
                     "description": "a magnified, completely out-of-focus crop of the background behind the subject: a soft wash of grey daylight framed by dark shadow, nothing recognizable",
                     "plate": "../refs/_bg/hall_bokeh_cindy.png"}
```

Don't name the room's things in that description (the fireplace, the door), even out of
focus: on H3 the words were drawn as a sharp room over the blurred picture. A plate that is
only a blurred patch can't show where someone stands in a two-shot, so keep it to singles.

**Say how tight an extreme close-up is, in its action.** The framing's name alone gives a
close-up of the whole face; the action says what fills the frame: "an extreme close-up of
Cindy's face from her eyebrows to her lips", "an extreme close-up of Cindy's hand, the diamond
ring on her finger". Keep the subject's picture an ordinary face or full-length one: a
picture cropped to the eyes was read as part of someone to be placed in a room, and the model
drew the room and moved her into it.

### Cutting within a location

Every shot is generated on its own, so a shot never continues the one before it: it poses
everyone from scratch. Cut between two shots that look alike and the eye reads it as a
glitch, with people jerking into new positions or appearing out of nowhere. That's a jump
cut. Two consecutive shots with **the same people on the same plate** need one of these
between them:

1. **A new angle.** Give the second shot another `plate:` of the place. A real change of
   camera position (film's 30-degree rule) makes the new pose read as a new view. This is
   the cheapest fix and why a location wants several angles.
2. **A size two or more steps away**, along `ecu` `cu` `mcu` `ms` `cowboy` `mws` `fs` `ws`
   `ews`: `mws` → `mcu`, `ms` → `cu`, `ws` → `ms`. One step (`ms` → `mcu`, `fs` → `ws`) reads
   as the camera twitching.
3. **A cutaway**, then back: the other character's reaction, an `ecu` insert of hands or a
   prop, what she's looking at. Under a second is enough (H3's shortest take is 0.92 s), and
   after it the return can be in any pose.
4. **A cut on action.** Open the second shot mid-movement ("already turning to the door"),
   not at rest: movement across the cut hides the change of pose. It helps the other three;
   on its own it seldom saves a cut.
5. **Continue the picture** when the second shot really is the same moment carrying on:
   `continuous: first` opens the shot on the previous shot's last frame, so nothing
   re-poses (on H3 FL2VA, which the shot moves to by itself; see **Continuous shots**). Its
   upscale starts from the previous shot's upscaled last frame, so the two meet on one
   picture. When the action itself runs across the cut (someone walking into the next
   framing), `continuous: latent` carries the motion and sound too, on H3 Ref2VA, FastH3
   Omni or H3 Singularity.

`continuous: multishot` is no fix for a jump cut: the model draws the cut the script asks
for, so two near-identical shots in one generation still cut as one.

`seriesmith check` warns about consecutive shots that do none of the first two and don't continue:
the same people, the same plate, sizes less than two steps apart, the second not
continuing the first (`continuous:`). It can't see a cutaway or a cut on
action in the action text, so treat it as a question to answer, not an error.

Worked through: Ada at the counter, then closer for her line. As written, a jump cut:

```
## sh020
who: ada
size: ms

## sh030
who: ada
size: mcu
```

With Bo's reaction between them, and the return two steps tighter:

```
## sh020
who: ada
size: ms

## sh025
who: bo
size: mcu

## sh030
who: ada
size: cu
```

### Every shot starts from an empty plate

Plates are drawn empty, and the model sees one shot at a time. Whatever the scene established
three cuts ago — who is in the car, the diners at the other tables, that Harold sat down — is
gone unless this shot says it again.

- **Everyone physically in frame is in `who:`**, even mostly unseen: the driver of a two-shot
  in a car is both people, the passenger's shoulder included. Leave one out and the plate's empty
  seat is all H3 gets, so they vanish for a shot and come back on the next. The same goes for
  anyone the action touches or looks at in frame: "Harold reaches for Cora's elbow" with no
  Cora in `who:` gets an invented stranger.
- **Repeat `extras:` on every shot of a populated room**, closes included ("diners at the far
  tables, blurred behind him"). It does not carry over from the previous shot, and without it
  the room is empty on the cut.
- **Say the posture.** A plate of a kitchen table is an empty table, and the sheet shows the
  character standing. Open on the posture plus the movement: "Seated at the kitchen table,
  Harold turns his head slowly…", not "Harold turns his head slowly…".
- **Give every moving object a hand.** "The briefcase opens" opens by itself; "Mills lifts the
  lid of the briefcase" puts Mills in `who:` and in frame.
- **Settle carried props.** If a character's `design` has a bag on the arm and the shot seats
  them, set the bag down in the action ("her handbag set beside the ledger"), or H3 draws a
  second, standing copy of them to carry it.
- **Write to the plate's angle.** A plate shot from the visitors' side sees the back of the
  monitor; if the screen matters, have someone turn it.
- **One or two physical steps per shot.** Crossing a lot, climbing steps and knocking is three
  shots, not one 4-second shot; crammed motion smears into interlace-like lines. Start the shot
  where its plate is.
- **Pick people up where the last shot left them.** If sh160 parks the truck by the building,
  sh170 doesn't walk him across the lot. Name the spot in the first shot ("parks at the far
  end of the lot") so the next one can start from it.
- **The crowd is already there.** On an empty plate, people written as arriving materialise
  in the middle of the shot. Write them as present from the first frame: "the line already
  running, a worker at every station".

### Vehicles in motion

A moving vehicle with a loose description wanders: it swerves toward the people in frame,
speeds up when it should stop, and smears.

- **Give it one clean path**: direction across frame, lane and speed. "The pickup rolls slowly
  left to right in the near lane, never leaving the road."
- **Arriving and getting out are separate shots.** One shot drives in; the next opens with the
  door already opening.
- **Parking is its own beat**, and the shot starts with the vehicle already slowing. Say where
  it stops, so the next shot can pick up from there.

Reserve `camera: holds a static shot` for reactions where stillness is the point. On a wide
you have just cut to, a slow push gives the space depth, and costs nothing extra.

Shot IDs go `sh010, sh020, sh030`, leaving gaps so you can insert `sh015` later. Renumbering
changes seeds and invalidates renders. An ID is unique across the whole episode, not just its
sequence: continue the numbering (`sh110` in the next sequence, or keep counting) rather than
restarting at `sh010`.

**A shot's ID is its identity**, beyond its seed: its takes, its overrides and everything the
cut says about it (the pick, trims, lock, audio source, and whether it's left out of the cut)
are kept by ID. So when revising a script:

- **the same shot, rewritten:** keep its ID. Its takes are flagged stale where the prompt
  changed, and the cut's decisions about it still apply;
- **a different shot:** give it a new ID, and never reuse an ID you removed; the old one's
  takes and cut decisions (a pick, trims, "left out") would land on the new shot;
- **a shot added between two others:** an in-between ID (`sh065` between `sh060` and `sh070`),
  so every other shot keeps its ID;
- **a shot removed:** just delete it; its takes stay on disk, and its cut entry is skipped.
  To try the cut without a shot, leave it out of the cut in the editor instead of deleting it.

## Reference slots (H3 Ref2VA)

This section is about the default target, `minimax_h3_ref2va`. The other targets take no
slots (their limits are under **Rendering a shot on …**), but the three-subject rule is a
good habit everywhere: a shot about more than three things is usually two shots.

Every shot hands H3 four images. Slots 1–3 are the subjects — characters first, then props
and vehicles, in the order `who:` and `with:` list them. **Slot 4 is always the location
plate.**

That caps you at **three subjects on screen**, and a fourth is an error, not a silent drop.
When a scene has four characters, stage one out of frame, split the shot, or describe the
extra in the action text without referencing it. Crowds cost nothing that way — they just
won't look the same from shot to shot, unless they are a group (one slot for all of them;
see **A group: the same extras every shot**).

A `(V.O.)` or `(O.S.)` speaker costs no slot, is never drawn, and needs no sheet — only a
`voice` in the series config. A shot may have no `who:` at all: an establishing plate with narration
over it.

### Crowds and extras

On H3 Ref2VA a shot's prompt states that exactly one person appears in it per referenced
character, which is what stops H3 drawing the same face twice. The moment the action puts
someone else in frame — a dance partner, a mob, a crowd at a door — that sentence contradicts
the action, and H3 resolves the contradiction by **duplicating the referenced character**,
often with interlace-looking smearing where the copies overlap.

`extras:` names those people, so the prompt keeps identity locked for the subject and allows
everyone else:

```
## sh090
who: eleanor_30
extras: one masked man in black tails, his back mostly to camera, and far-off dancers blurred into bokeh
Eleanor circles a masked man in black tails, one hand in his, laughing as she turns around him.
camera: arcs around Eleanor with small amplitude at slow speed
```

### A group: the same extras every shot

`extras:` people are invented fresh every shot, so they change sex, size and colour from
cut to cut. When the same few people recur — the ladies watching from the edge of the
ballroom, a family at the next table — make them one **group** subject: a character with
`members`, whose picture holds all of them.

```json
"ladies": {
  "kind": "character",
  "name": "the ladies",
  "members": 4,
  "design": "four young women in Regency ball gowns: one in pale blue with dark curls, one in rose with a feathered headband, one in white with red hair, one in green silk with long gloves",
  "sheet": "../refs/ladies/ladies.png"
}
```

Cast it like anyone else (`who:` or `with:`). It takes one slot however many people it
holds, which is how a shot gets more than three people who stay the same: two named
characters and a group of four is three subjects. The prompt defines it as a picture of N
different people and counts its members in the shot's headcount ("Exactly six characters
appear in this shot: <Subject 1>, <Subject 2> and the four members of <Subject 3>"), which
is what keeps H3 from drawing the same woman twice. Put where they are in the action text
("the ladies watch from the far wall, soft in the background").

- **The picture is one whole image** of all of them (`sheet_panels: 1` is implied; a group is
  never a four-panel sheet). Generated, it is a row of everyone head to feet, apart and facing
  the viewer, at the plate's size. A picture you supply works the same way; keep every face
  and outfit visible, since a person half-hidden in the reference is one the model invents.
- **Describe each member** in `design`, with differences in age, build, hair and colour. A group
  of four identical gowns is read as one person four times.
- It works on every target. H3 Ref2VA defines it in the headcount. LTX-2, Wan and H3 from
  keyframes call it "N different people, each appearing once" in their prose, and their
  reference sheets carry its picture whole, never cut to one panel.
- A group can speak (`voice` is one voice for all of them: a murmur, children giggling).
- Twelve is the limit. A crowd bigger than that belongs in `extras:`.

Two habits go with it. **Keep people out of the plate**: a location described as "full of
masked dancers" is rebuilt as figures that compete with the subject and feed the duplication
— describe the empty space and let the far background fall off into bokeh. And **name the
subject in the camera move**: "arcs around them" leaves the model to decide who "them" is.

**Extras in the lead's wardrobe take the lead's face.** The prompt already tells H3 the extras
look nothing like the subject, but twenty white smocks and hard hats around a man in a white
smock and hard hat still turn into twenty of him. When the extras share the lead's uniform,
vary them in `extras:`: men and women, different ages and builds, hairnets instead of hard
hats, faces turned away or soft in the background.

On H3 Ref2VA, `size:` also decides what the plate means (besides the framing words; see
**Faces need room**): on a wide or medium the room's layout
is kept, and on a close-up the background is a zoomed-in crop of the plate — the part of the room
right behind the subject — and never the plain backdrop of the character sheet. A close-up
still leaves the room's layout to the shots around it, so stage the space on a medium first.

Add a prop to `with:` only when its exact design matters and recurs. A generic mug is better
described in the action text, because every referenced prop spends a slot.

## Sequences

A sequence is one location, continuously. A new place — or the same place at a different time
of day — starts a new `#` sequence. Intercutting is just alternating sequences: `# sq03
kitchen`, `# sq04 phone_room`, `# sq05 kitchen`.

Keep a sequence intact and vary the shots with `plate:` rather than splitting a scene into
one-shot sequences, which re-seeds every shot in it.

`continuous:` under the `#` header applies to every shot after the first: `first` or
`latent` chains each onto the one before as one continuous take, and `multishot` renders the
whole sequence as one generation with cuts in it (see **Continuous shots**).

## What goes on which line

These map to different fields in the generated prompt, and mixing them dilutes all three.

- **action** — what is visibly happening, present tense, concrete and physical. Not
  motivation, not backstory, not what a character feels.
- **camera** — the move only.
- **sound** — ambience and physical action sounds: footsteps, fabric, doors, wind, impacts.
  Not dialogue, not score.
- **music** — audience-only score. Omit it on most shots; scoring is usually a conform
  decision.

## Finish by validating

```
seriesmith build series.json ep01.md --check     # counts, runtime, references, warnings
seriesmith build series.json ep01.md --pace      # dialogue pacing per shot
```

(`seriesmith check <episode folder>` runs both.) The check compiles every shot for the
target it renders on, so it also reports each target's limits.

Errors name the line and quote it. Common ones: a name in `who:` that is not in the series config; a
location that isn't in the series config, or one with no `description`; an ALL-CAPS `NAME:` line for someone who cannot speak (usually a typo,
which would otherwise become action prose); more than three subjects on H3 Ref2VA; a shot
with neither `dur:` nor `audio:`; `dur: auto` on a shot with no dialogue; a `dur: model`
range that isn't `min-max` seconds with min below max; a `target:` or `profile:` name that
doesn't exist; a `first:` / `last:` that isn't a method or an image path; a `continuous:`
the shot's own target can't render (`latent` off H3 Ref2VA, `first` on a target that reads
no first frame). Warnings cover
crammed dialogue, wasted grid padding, and what a target can't do (a dialogue shot on Wan,
a `clone` shot on LTX).

A script that does not compile is not a draft, it is a bug. Fix and re-run until it is clean.
