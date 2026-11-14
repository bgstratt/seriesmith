# The series config, block by block

A reference for SKILL.md: starting a series and what to settle first, render size and delivery, the master recipe, post, the intro and outro and a cold open before them, the `look` line, render profiles, the `refs`, `sound` and `ambience` blocks, relit plates. Read it when writing a new `series.json` or any block of one besides `subjects` and `locations`, relighting a plate, or marking a cold open.

## Starting a series: what to settle first

The first episode (**Your first episode**) is the smallest series config that builds. A series that will be
finished (upscaled, mastered and published) needs a few more decisions. They're made once,
and they all live in the series config. Settle them before the first script: changing the
size later only changes the takes rendered after the change, and a master needs its
recipe before it can run.

| Decision | What to ask | Where it goes | With no answer |
|---|---|---|---|
| **Look** | Live action or animated? What should it look like (film stock, lens, palette, drawing style)? | `style.look` | Ask: there's no good default. See **Writing the `look` line** |
| **Delivery** | 1080p, 1440p or 4K? An exact 16:9 frame, or is H3's 7:4 fine? Fast iterations, or every take at full size? | `series.width` / `height`, `proxy`, `upscale.master` | Render at 1344×768 (it renders on every target with nothing extra installed), proxy 896×512, and master 1440p: the **Render at size** setup. See **Render size and delivery** |
| **Voices** | Generated from a description, cloned from voice samples, or lip-synced to dialogue you've recorded? | `audio.mode` (`generate`, `clone`, `source_track`), each character's `voice` / `voice_sample` | `generate` |
| **Finishing** | Clean up the upscale (edges, blocky motion) before the master? | `post` | `"enhance": "production"`, `"motion_blur": 0.3` for a 1080p or 1440p master; none for 4K. See **Post-process** |
| **Titles** | Is there a series intro and outro (clips made once for the whole show)? | `_titles/INTRO.mp4` and `OUTRO.mp4` in the show folder; `publish` only to name other files or style the episode title | Nothing to write: a master picks the clips up when they're there. See **Series intro and outro** |
| **Model** | Does it have to render on one model (what's installed, a hosted one)? | `series.target`, `series.first_target`, `refs` | Leave both out: the series renders on the machine's default models |
| **Pace** | How fast do people talk? | `speech.pace` | `normal` |

Ask these in **one message**, only the ones the brief doesn't already answer ("for
YouTube at 4K", "the voices are recorded" answer two). If the person would rather you
just start, use the defaults and say which ones you used. Then write the whole config:
its other blocks, not only the cast and the places.

A series rendered at size and mastered at 1440p, with generated voices, the finishing
pass, and the intro and outro picked up from `_titles/`:

```json
{
  "series": { "id": "last_light", "title": "Last Light", "fps": 24,
              "width": 1344, "height": 768 },
  "proxy": { "width": 896, "height": 512, "steps": 8,
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
| **At size, master 1440p** | 1344×768 | 896×512, 8 steps | 2560×1440 (23 rows cropped) | live action with close dialogue, where faces need the pixels |

- 1344×768 is 7:4, H3's native canvas, not 16:9: a 16:9 delivery crops it slightly
  (`fit: crop`) or pads it with bars (`fit: pad`). Say so when someone names a 16:9 size.
- A proxy under 480 rows is too small to judge faces and hands by (16:9's 512×288 is the
  exception: H3's grid has no 16:9 size between it and 1024×576). Without a `proxy` block
  the proxy is the model's own (512×288 on H3), so write one.
- Changing the size later changes only the takes rendered after it; never change an
  existing series' size unasked.
- Why each setup, its timings, and the upscale methods are in seriesmith's finishing guide.

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
  `seedvr2_model`; `ltx`: the LTX-2.5 detail pass, `ltx_lora` `refine` or `restore`), `scale` (a number, or `"auto"`: the smallest that covers `deliver`),
  `then` (an upscale model file, or `"seedvr2"`, after a re-sample).
- FastH3 Omni re-samples as H3 does but isn't `minimax_h3_*`: give `fasth3_*` its own
  section, or its shots fall to `"*"`.
- `upscale.save_latents` (`"final"`, the default) keeps each final take's latent so a
  re-sample can start from it.

One recipe per delivery; pick the one they asked for. With no answer it is 1440p, which the
default render size (1344×768) doubles to; 1080p for a series rendered small or at 16:9; 4K
only when asked:

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
1440p master, asked for or not (it is the default); leave it out for 4K (unmeasured there).
`"faces": true` redraws each character's face from their sheet where it's too small to
have eyes and a mouth (wides and full shots; about a minute a character a shot; a large
face is barely touched). Leave it out by default: the user marks the clips that need it
with R while watching the dailies. Put it in `post.master` (Series settings → Finishing →
**Post: refine faces** → every shot) only when they ask for every shot without marking; a
shot's own `post` in overrides.json (`true` or `false`) is over it, and a clip's R mark
(either way) is over both.

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

### Reference images and voices: the `refs` block

The pictures (character sheets, props, plates) and shot keyframes are made by an image
model, a character's voice sample by an audio model. Leave the block out for the defaults
(Krea 2 for pictures, Qwen-Image 2.1 for keyframes when it's installed, then FLUX.2 Klein edit,
LTX-2.5 for voices), or name others:

```json
"refs": {"target": "krea2", "keyframe_target": "flux2_klein_edit", "edit_target": "qwen_image_21",
         "turn_target": "qwen_image_21", "voice_target": "ltx2_voice", "ambience_target": "mmaudio_ambience"}
```

(`edit_target` is the model that edits a picture you already have: the editor's Edit and
Relight. It must be one that reads reference images; left out, it's `flux3_klein` for a
character and `qwen_image_21` for anything else, each the other when it isn't installed, then
the first of `keyframe_target` and `target` that can. `turn_target` is the one a character's view is
turned on: `qwen_image_21` adds the multiple-angles LoRA, any other edit model is told the
turn in words; left out, Qwen 2.1 + angles when it's installed, else `edit_target`.)

(`ambience_target` makes the places' ambience beds: `mmaudio_ambience`, the default, or
`sa3_sfx_ambience`. `voice_target` can also name a video model that renders a dub track,
`minimax_h3_ref2va`, `fasth3_omni` or `ltx2`: the editor's dub tracks then start on it, and
voice samples stay on `ltx2_voice`. Three voice models clone a character's sample rather than
continue it: `drama3` and `qwen3_tts` on your GPU, `fishaudio_drama3` hosted and paid; each
is sent the words alone, and without a sample makes the voice from the `voice` line.)

The picture models, and what each needs installed, are in seriesmith's full setup guide
(**Pictures**). Two things matter when writing:

- A **variant**'s pictures (a subject with `of:`) are edits of its original's, on a model
  that reads reference images, so the face carries. On a text-to-image model (Krea 2) the
  variant is drawn from its `design` alone: write that sentence as close to the
  original's as the change allows.
- `voices`, on a character, is the speaker it has on a provider, by provider, written when you
  pick one in the editor: `"voices": {"elevenlabs": {"id": "JBFqnCBsd6RMkjVDRZzb", "name": "George"}}`.
  An id belongs to the provider, and one private to an account fails on another's.
- A character with no `voice_sample` still gets one: generating and picking a voice in the
  editor (or `seriesmith refs <ep> --voices`) writes `refs/voices/<id>.wav` and adds the
  `voice_sample` line to `series.json`. Don't invent a `voice_sample` path for a file that
  doesn't exist.

### The episode's sound: the `sound` block

The sound under the cut (the Dialogue, Effects, Ambience and Music tracks, the cues, the
levels) is made in the editor and kept in each episode's `mix.json`, not in the series
config. The `sound` block holds only what carries across a series, and every key is
optional; leave the block out for the defaults:

```json
"sound": {"score": "orchestral, a solo horn for the hero, low strings for the sea",
          "music_model": "stable_audio3", "song_model": "yue2", "effects_model": "h3_foley",
          "tracks": {"music": {"gain_db": -14}, "ambience": {"duck_db": -9}},
          "loudness": {"target_lufs": -16, "true_peak_db": -1}}
```

- `score` is the series' score direction in words. It goes before each score cue's own
  style in the music model's prompt, so write the sound of the show, not of one scene.
- `music_model` is what score cues render on (`stable_audio3`, the default, or
  `ace_step15`); `song_model` what songs render on (`yue2`, the default, non-commercial).
  A cue given its own model in the editor keeps it.
- `effects_model` is what a shot's effects are made on (`h3_foley`, the default,
  `ltx23_foley` or `hunyuan_xl_foley`).
- `tracks` are each track's default level: `gain_db` (the fader; music sits at -12 dB when
  nothing sets it), `duck_db` (how far it dips under speech), `mute`. A level set in the
  editor's mix wins over these.
- `loudness` is the export's target: `target_lufs` (default -16) and `true_peak_db` (the
  limiter's ceiling, default -1). The episode's mix can set its own.
- `themes` are the show's recurring music, by name, for any episode's cue to carry: each a
  picked take of a cue (`{"ep": "ep01", "cue": "m04", "take": 3}`, the episode's folder beside
  this one) or a file (`{"file": "themes/glance.wav", "bpm": 80}`, relative to the series
  config), with `role` (`show`, `story` or `runner`), `words` (what it is) and `for` (whose it
  is: cast ids; a character's theme is the episode's own whenever they lead it). They're made
  in the editor from a take you pick (its **★ Series theme**), not written by hand; leave the
  key out when writing a new series.
- `format` is a show's own first-pass score, for a show whose episodes share a shape of their
  own (Porch Lights' Cold Open, The Read, The Cost...): what the draft (**Draft…** on the
  spotting sheet, `seriesmith score-draft`) does with each of its `// beat:` names, in place
  of a structure's Music table (`references/story_structures.md`). `{"like": "episodic drama", "beats":
  {"Cold Open": {"music": "score", "words": "felt piano, a low pulse", "energy": [2, 3],
  "theme": "mark", "hits": ["turn"]}}, "other": {...}, "marks": {"glance": "sting"}}`:
  `music` is `score`, `under`, `gaps` (only where no one speaks), `sting` or `dry`; `theme`
  a role (`story`, `show`, `runner`), `lead` (the theme `for` the beat's lead, else
  `theme_else`) or a theme's name; `like` the structure for the beats it doesn't name;
  `other` any beat neither names (`talk_max`: dry above that share of lines); `marks` how a
  `// theme:` mark of that theme plays. A show that follows one of the structures needs none.

The place's ambience bed is the location's `ambience` (below) and its model
`refs.ambience_target` (above). How to score an episode is in seriesmith's scoring guide; a
music video, with the song as the recording, in seriesmith's music video guide.

### Negative prompts

Targets that take a negative prompt (LTX-2, Wan 2.2 and the image models; not H3) use, most
specific first: the render request's, the shot's override (the editor, per pass), the
episode's **`negative.txt`** (a text file beside the script), the series config's
`"negative": "..."`, then the model's own. The take records which one it used. Turbo and
distilled models sample without guidance (cfg 1): there a negative does nothing, and the
take says so.

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

**A series with day exteriors keeps the light's level out of the look too.** "Low-key" and
"pools of light" ask every shot for night. Under a look of "low-key light motivated by the
practical lamps, windows, screens and signs in each place", an H3 shot on a sunlit morning
parking-lot plate came out at dusk, string lights and all, on every take. For a show that
goes outdoors in daylight, say only how the light behaves ("natural motivated light with
soft contrast, deep soft shadows") and let each location say day or night (**Time of day is
part of the location**).

Each clause is something the model can see: shallow focus and bokeh separate the subject
from the room and soften what the model draws worst, low-key practical light gives the frame
contrast and shape, and grain gives the image the texture of film. Keep it to one sentence;
the per-shot light belongs in the location descriptions and the action.

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

### What a place sounds like: `ambience`

A location may say what is **heard** there, its room tone or air, in `ambience`. An
ambience bed is made from those words (on MMAudio by default, with "No music, no voices,
no speech." added) and looped under every shot of every sequence set there, so a room's
hum runs across its cuts instead of starting and stopping with each take:

```json
"diner": {"description": "a small roadside diner at night, a red vinyl booth ...",
          "plate": "../refs/_bg/diner.png",
          "ambience": "Room tone of a small roadside diner at night: a refrigerator hum, the buzz of a neon sign, the faint clink of dishes from the kitchen, an occasional car passing outside."}
```

- Write what is heard, as a sound designer would: the steady bed first (a hum, rain, wind,
  traffic), then a few sparse events (a clink, a car passing). Never music, a voice or a
  line someone says.
- A bed belongs to the **place**: an angle or a relit version (`of:`) plays its place's bed,
  so the cut between them doesn't change the room. Give a variant its own `ambience` only
  when it sounds different (the hall at golden hour, with evening birds).
- The bed's file is `ambience_bed`, a path like `plate`'s. Leave it out: it is `_amb/<id>.wav`
  in the refs folder the plate is in (`../refs/_amb/diner.wav` beside `../refs/_bg/diner.png`).
  A recording of your own can be named there with no `ambience` words.
- Nothing is automatic: a location with no `ambience` (and whose place has none) gets no
  bed. `seriesmith refs` makes the beds refs_todo lists; the editor's Refs tab has them under
  **Ambience**. Its level is the mix's (the Ambience lane, seriesmith's editor guide).

### A cold open: `cold_open:`

A teaser before the opening titles: the episode's first scene, then the series intro, then
the rest. Mark the sequences (or shots) that play before the titles:

```
# sq01  diner_night
cold_open: true
```

- **It's the cut's first shots, one after another.** A master (and the editor's **Titles**)
  puts the series intro in right after the last of them; without any, at the start.
- **The cut's order decides.** A marked shot moved after one that isn't is a gap: master
  refuses until it's fixed. In the editor, right-click the clip the cold open should end on,
  **In the cut › Cold open ends here**: the marks are rewritten to the cut as it is.
- **A dissolve can't cross the break**: the titles go in on a cut.
- Export and the mix are the cut as it is, with no titles; Play all's **Titles** plays the
  intro and outro where a master puts them.
- **Writing one:** a structure's **Cold Open** or **Teaser** beat is a cold open, and so is a
  screenplay's `COLD OPEN` or `TEASER` heading (`references/script_conversion.md`): mark those
  sequences, and only those.
