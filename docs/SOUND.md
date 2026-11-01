# The episode's sound: four tracks, cues, a mix

Status (2026-11-01): **designing**, on the `sound-tracks` branch. This file is the design
record and the checklist; the contracts go into the docstrings, `docs/API.md` and the user
docs as each phase is built.

## Why

A shot's sound today is one stream: the model's mix (voice, effects, room, sometimes music,
all baked in), or a cut entry's `audio` source with `start` / `offset` / `gain`
(`assemble.clip_track`). Assemble joins the clips end to end, so the sound starts and stops
at every cut, and anything that should run across cuts (a room's tone, a score) has nowhere to
go. RECORDED_DIALOGUE.md still ends "final mix: do it in Resolve". The FCP7 export has two
audio tracks (four with a recording).

The episode gets four tracks under the picture, each optional, each with its own level:

| Track | What's on it | Made by |
|---|---|---|
| **Dialogue** | the take's own sound, as today (the model's mix, a dub, a clone) | the shot's render |
| **Effects** | sync sound for a shot: footsteps, doors, impacts | a video-to-audio (foley) model run on the picked take, or a file |
| **Ambience** | a place's room tone or air, running across the cuts of a sequence | a text-to-audio model, once per location; or a file |
| **Music** | score cues and songs, each its own asset spanning shots | a music model; or a file |

Nothing is split early: Dialogue holds the take's sound whole, effects and all, and the other
three are added to it. A shot whose model sound fights an added effects or score track gets
that track's level lowered, or (later, phase 4) its take split by Demucs into voice and the
rest.

## Where it lives: not in the script

A mix only makes sense against a cut, so it is the episode's, beside `cut.json`:

- **`<ep>/mix.json`**, one mix per pass as `cut.json` holds one list per pass (`seriesmith/mix.py`
  has the shape): the tracks' faders and mute, every item (where it sits, its gain, fades,
  volume breakpoints), the hit points, the regions, the ducking and the loudness target. Each
  write keeps the old file in `_history/`, as the cut's do.
- **`<ep>/sound/<item id>/`**: an item's spec (what it was asked for: model, prompt, length,
  bpm, hits) and its takes (`t01.wav` + sidecar, as a shot's takes), so a cue is re-rendered,
  picked and kept like a shot.
- **Series config**, only what carries across episodes: a `sound` block (default track levels,
  the loudness target, the series' score direction in words: "orchestral, John Williams-style
  leitmotifs, brass for the hero") and a location's `ambience` (a description, and a bed file
  like its `plate`, made from the description the way a plate is: a ref). Reuse beyond that
  is the gallery: any episode's cue or bed is dragged into another.
- **The script** keeps `music:` as a note, never as mix data: the cue form lists the `music:`
  notes of the shots a cue spans and they go into its prompt ("swells as the ship lifts off").

## Anchors, frame-accurate

Everything on the added tracks is anchored to **a shot and a frame of its take** (at the cut's
rate, counted from the take's first frame, before any trim), never to an absolute time. A trim
or a reorder moves an item with its shot, and a hit stays on the action it marks even when the
shot's head is trimmed; a change to a cue's span is a refit (below). The playhead's position
converts to an anchor and back through the cut, as the timeline already does for trims.

- An **item** has an in-anchor and an out-anchor (where it starts and stops in the cut), an
  offset into its source (where in the take it starts playing) and fades.
- A **hit point** is a named anchor ("the door bursts", "reveal", "the cut to the bridge"),
  placed on the timeline on a marker lane above the sound lanes. A cue lists the hits it must
  land: the frame in the cut and the beat of the cue that lands on it (a downbeat by default).
  A sequence can have any number of cues; a cue can span sequences.

## Music: a cue is written to its hits

A cue is generated to fit: its length is its span plus a pre-roll and tail, and its tempo is
chosen so the hits fall on bar lines.

- **Tempo from the hits.** A hit `t` seconds into the cue lands on a bar line when
  `t = n × beats_per_bar × 60 / bpm`. The prompt writer picks the `bpm` near the asked-for
  tempo (or the style's) that puts every hit within a frame of a bar line, moving the cue's
  start (the pre-roll) to absorb the rest. With more hits than one tempo can land, it lands the
  ones marked `must` and reports the others' error in frames.
- **Sections from the hits.** ACE-Step's lyrics field takes structure tags; an instrumental
  cue's "lyrics" are tags alone, one per stretch between hits, with its bar count: `[intro 4
  bars, solo horn, quiet]`, `[build 8 bars, strings enter, rising]`, `[climax 4 bars, full
  orchestra, brass]`, `[outro 2 bars]`. The dynamics are written into the music (a crescendo is
  composed, not only turned up), and the volume breakpoints shape it in the mix.
- **Songs.** YuE2 takes lyrics with `[verse]` / `[chorus]` and, optionally, a melody as ABC
  notation, whose header carries the tempo (`Q:1/4=96`), so a song is timed the same way.
  SheetSage2 transcribes a melody from a recording into ABC, so a theme heard in one cue can
  be sung or played in another (YuE2's `melody` mode).
- **Checked after rendering.** A take's beats are found (an onset envelope and its
  autocorrelation, numpy, no new dependency) and its tempo and downbeats compared to what was
  asked; the sidecar records each hit's error in frames, and the takes list shows it. A take
  that drifts more than its tolerance is fitted (next) or said to miss.
- **Refit, then stale.** When a cue's span or hits change after it is made, it is fitted when
  the change is small: cut at a bar line with a fade, stretched by up to ±3 % (`atempo`), or
  shifted so the main hit lands. Either way it is marked stale, with what was done; a change
  too big to fit is stale and plays as it was.

## The cue window: what happens inside a cue

The timeline decides where a cue sits against the picture; the cue window decides what
happens inside it, as the timeline and a shot's form split a shot. A cue has enough inner
structure (bars, sections, an arc, who plays) that it needs a time-based view, not a stacked
form. It opens in the main pane (where a take plays) on a double-click of a cue's block, with
the episode picker as everywhere else, and has three tabs on one bar grid:

- **Score** (the main view): a picture strip (the cue's span, its pre-roll and tail), the hits
  lane (each hit's bar and beat), the bar ruler at the cue's tempo and meter, the **sections**
  as blocks whose edges snap to bars, the **intensity** lane (the arc), the orchestra rows,
  and the takes. An inspector on the right edits the selected section: energy from and to
  (1-5), its shape (rising, steady, falling, swell), its instruments, direction text
  (prefilled from the series' score direction and the script's `music:` notes in the span),
  and the exact line ACE-Step will get for it, editable.
- **Arc**: the intensity lane large, to draw first: preset shapes (slow burn, build and
  release, sting, pulse, the script's `music:` notes), draw / points / smooth, **snap peaks to
  hits**. The sections are worked out from it: each peak or low becomes a section boundary at
  the nearest bar, so "the climax lands on the reveal" is structure, not a hope. A readout
  says what the model will hear, and flags detail it can't follow (a dip inside a section:
  split the section to keep it).
- **Orchestration & takes**: a grid of instrument families by bar, painted off / under /
  present / lead, which become each section's instrument tags; then the takes stacked, each
  its waveform, its measured loudness per bar over the arc drawn, each hit's error in frames
  (orange when it misses), its tempo. Selecting bars of a take offers the fixes: **repaint**
  those bars, **comp** them from another take (spliced at bar lines: same tempo and grid), or
  **lower them with breakpoints** (a mix fix, in `mix.json`).

**The spotting sheet** is one level up: the episode's view, where cues are placed before they
are shaped (the way a composer spots a film). A large viewer with frame stepping and jump to
hit; the episode's **music map**, every cue, song, bed and hit across the sequences (Music /
Ambience / Effects); **+ Hit at playhead**; and for the selected cue a table of its hits:
kind, anchor, cut timecode, the bar and beat it lands on, must, and each take's error in
frames; the script's `music:` notes, the series' direction and its leitmotif reference
(a cue or theme from the gallery, as ACE-Step's timbre reference and YuE2's melody), and how
the tempo was fitted, with the nearest alternatives. Render stale cues from there.

**The timeline** stays the simple view: each lane's waveform and fader, the items, the hit
markers coloured by kind, and the cue's arc drawn faintly over its block, for reference.

### Hit kinds

A hit's `kind` tells the section builder and the prompt writer what to do (mix.py stores it):
**accent** (a sting or downbeat on the frame; the default), **arrive** (the peak lands here, so
the section before it builds), **drop** (the music cuts out or thins: often the strongest cue,
silence before a reveal), **turn** (a change of key or mood: a new section, new instruments).
`must: false` lets a hit miss when one tempo can't land them all.

### From an arc to words

ACE-Step takes tags, structure tags with text, a bpm and a length; it can't follow a curve. The
turning of the arc into words is shown, not hidden:

- The arc's peaks and lows (and the hits that `arrive`, `drop` or `turn`) become section
  boundaries, snapped to bars.
- Each section's stretch of the arc becomes a **level** (1-5: sparse, quiet, moderate, full,
  full orchestra fortissimo) and a **direction** (rising, steady, falling: building,
  sustained, receding): `[build 6 bars, strings enter, french horn, timpani roll, rising from
  quiet to strong, building]`.
- The tags line: the series' direction, the cue's own, tempo, meter, key and length.
- Detail finer than a section is not honoured; the window says so where it sees it.

### Two curves, kept apart

| | The arc (intent) | Gain breakpoints |
|---|---|---|
| Lives in | the cue window | the timeline lane |
| Stored in | the cue's spec, `sound/<cue>/` | `mix.json` |
| Changes | the prompt: a re-render | the level: at once |
| Unit | energy 1-5 | dB |

Drawn in different colours, so a crescendo drawn with gain (the strings never enter) isn't
mistaken for one composed.

### A cue's files

`<ep>/sound/<cue id>/spec.json`: the model, tempo (auto from the hits, or fixed), meter, key,
seed, pre-roll and tail, the arc's points (each anchored to a shot and frame, like everything
else, with its level), section overrides (edges, text, instruments), the orchestration grid,
the hits it lands. Sections in bars are derived from the arc and the hits when the prompt is
written, so a trim inside the span makes the cue stale rather than leaving a section in the
wrong place. Its takes are `tNN.wav` with a sidecar each: the tempo and downbeats measured,
each hit's error, the loudness per bar and the shape error against the arc, what it was asked.

### Checking a take against the arc

Beside the beats (an onset envelope), a take's **loudness per bar** (short-term LUFS) is
measured and laid over the arc: its **shape error** sits beside its hit error, so a take is
picked for landing the hits and following the arc. That comparison is the strongest reason the
window exists; on a folded timeline lane it can't be read.

### Fixing part of a take

ComfyUI's ACE-Step 1.5 nodes have no repaint or extend (checked 2026-11-01, ComfyUI 0.43). It
can likely be done as `targets/held_audio.py` holds sound for LTX: the take encoded
(`VAEEncodeAudio`), the bars to keep masked out (`SetLatentNoiseMask`), the rest sampled
again. Measure it before the window offers Repaint; comping from another take at bar lines
works without it.

## Mixing: rules, not a console

- **Faders** per track (dB) and mute / solo; **gain** per item (dB); **fades** in and out;
  **volume breakpoints** on an item (a few points of dB at anchors: the crescendo, the score
  taking over).
- **Ducking**: dialogue first. Music and ambience dip under speech by a track setting (default
  -9 dB music, -6 dB ambience, attack and release in ms). A **duck region** on the timeline
  changes it for a stretch: "score forward" (no dip, the dialogue lowered instead), or a
  deeper dip. The dip is computed by seriesmith as a gain curve from the dialogue track's
  level, not by ffmpeg's `sidechaincompress`, so the editor's preview and the render apply the
  same curve.
- **Loudness**: the mix is normalised to the series' target (default -16 LUFS integrated,
  -1 dBTP), two-pass `loudnorm` on the mixed track. The master's report says what it measured.
- What stays in Resolve / Fairlight: drawn automation beyond breakpoints, EQ, reverb, noise
  cleanup. The FCP7 export carries the tracks and their levels so that's a hand-off, not a
  redo.

## Rendering and export

- **Assemble** renders each track as one continuous wav the length of the cut, every item
  placed by its frame, then applies the ducking curves and faders, mixes, normalises and muxes
  once. Today's per-clip audio joins stay for a cut with no `mix.json`, so nothing changes
  until a mix exists.
- **Stems** in `<cut>_stems/` beside the export (48 kHz, 24-bit): `dialogue.wav`,
  `effects.wav`, `ambience.wav`, `music.wav`, `me.wav` (everything but the dialogue: a dubbed
  language version is the M&E plus cloned or recorded lines) and `mix.wav`. The stems take the
  loudness gain, so they sum to the mix but for its limiter.
- **FCP7 XML**: A1-A2 the clips' own sound, the recording on the next pair when there is one,
  then effects, ambience and music a pair each, each item a clip of its file with its level
  (the track's fader folded in) and its breakpoints as Audio Levels keyframes, its fades as
  audio transitions, a loop as its file laid again end to end, the hits as sequence markers.
  The ducking is computed, so it stays in seriesmith's render. Items on the dialogue track
  aren't carried yet.
- **A single take's download** is the take: its own sound, nothing from the mix.

## The editor

- **Lanes under the timeline**, folded to one line by default; unfolded, each track a lane with
  its waveform (`peaks`), its fader, mute and solo on the left, its items as blocks you drag
  and trim, their breakpoints as points on a line. The hit lane sits above them. Playback mixes
  the lanes live (Web Audio: a gain node per track and item, the duck curve as gain
  automation).
- **A cue opens in the cue window** (above), not a form. A song is a cue with lyrics on its
  sections (YuE2). An ambience bed's form is its location's ambience; an effects item's is on
  the shot's Sound card ("Effects: from the take").
- **Import a file** onto any lane (your own music, a recorded room tone), and a cue or bed from
  the gallery.

## Models (checked on this machine 2026-11-01; ComfyUI 0.43, RTX 5090 32 GB)

Each is a target, as video models are (`targets/<kind>/<id>/target.json`, its prompt writer,
its workflow, its files and their downloads in Features), so a paid or Router model is a new
folder later. New kinds: **`music`** (spec -> a cue), **`ambience`** (text -> a bed),
**`foley`** (a take -> its effects). The existing `audio` kind stays the voice.

Music:

| Model | Status here | Use |
|---|---|---|
| **ACE-Step 1.5 XL** (core nodes: `TextEncodeAceStepAudio1.5` takes tags, lyrics, `bpm`, `duration`, time signature, key; `ReferenceTimbreAudio` a timbre reference) | **downloaded 2026-11-01**: XL Turbo (proxy pass, 8 steps) and XL SFT (final), `qwen_0.6b_ace15` + `qwen_4b_ace15`, `ace_1.5_vae` (Comfy-Org/ace_step_1.5_ComfyUI_files; templates `audio_ace_step1_5_xl_turbo` / `_sft`) | **default score model**; MIT |
| **MiniMax Music 3** (core nodes) | **downloaded 2026-11-01**: the template's files (`minimax_music3_dit_fp16`, the pruned int8 text encoder, `minimax_music3_dav`); its licence still to read | songs and score, a second opinion to ACE-Step |
| **YuE2** (core nodes: `YuE2GenerateMusic` style, lyrics, ABC, up to 900 s; `YuE2GenerateABC`) | installed: `yue2_3b_int8_convrot`; templates `audio_yue2_text2music`, `audio_yue2_music_cover` | songs; a melody carried from cue to cue |
| **SheetSage2** (`SheetSage2AudioToABC`) | installed | a recording's melody as ABC, for YuE2 |
| **Stable Audio 3 Medium** (core template `audio_stable_audio_3_medium`) | **downloaded 2026-11-01**: `stable_audio_3_medium`, `t5gemma_b_b_ul2` (and `qwen3.5_2b_bf16` for the template's optional reprompt) | **the score default candidate** (measured below: follows an arc told as a story); also stingers and an ambience candidate |
| HeartMuLa, DiffRhythm 2, SongBloom | no ComfyUI core nodes | not now |

Ambience: Stable Audio 3 Medium; LTX-2.5 audio-only (the `ltx2_voice` graph prompted for a
room, not a voice; up to 20 s, so a bed loops with a crossfade); ACE-Step for musical drones.
To be compared on three places before one is the default.

Foley (video -> sound):

| Model | Status here | Notes |
|---|---|---|
| **LTX-2.3 Foley LoRA** (`ltx-2.3-22b-lora-foley-v2a-1.0`, Lightricks) | LoRA installed; the saved workflow `LTX-2.3_-_V2V_Foley_Add_Sound_To_Any_Video_Foley-Lora.json` (ComfyUI user workflows) needs the LTX-2.3 dev transformer, VAEs, text projection and Gemma 3 12B encoder: **downloaded again 2026-11-01** (Kijai/LTX2.3_comfy, Comfy-Org/ltx-2) | the picture frozen (`LTXVSetAudioVideoMaskByTime`, mask_video false, mask_audio true), sound generated; LoRA 0.8-1.0, audio cfg ~6. Validated on 2.3 only; try it on 2.5 too |
| **MiniMax H3** | the models are here | untested as video-to-audio: the take's frames anchored with `MiniMaxH3AddGuide` (no sound), the prompt the shot's `sound:` line; the inverse of what `H3JointAudioMask` does |
| **HunyuanVideo-Foley** | **installed 2026-11-01**: phazei/ComfyUI-HunyuanVideo-Foley in custom_nodes; `hunyuanvideo_foley` (XXL) and `_xl`, its synchformer and DAC VAE in models/foley; SigLIP2 and CLAP in the Hugging Face cache | strong on Tencent's own benchmark against MMAudio and ThinkSound; Tencent's community licence (territory limits): read it |
| **MMAudio** | **installed 2026-11-01**: kijai/ComfyUI-MMAudio; the large 44k v2 model, its synchformer, VAE and CLIP (fp16) in models/mmaudio | MIT weights; BigVGAN fetched on first use |
| ControlFoley | official nodes | CC BY-NC: not offered |

Paid music models (MiniMax Music 3 on Comfy Cloud, Sonilo video-to-music, ByteDance Seed
Audio) are left out for now; they fit as targets of the same kinds.

Licences (read 2026-11-01): **MiniMax Music 3**'s community licence is free for commercial use
under $20M yearly revenue, the outputs the user's; it lists the US, EU, UK and South Korea as
regions with restrictions or a License Request Form by default, which is to be confirmed for a
US user (Comfy resells commercial licences). **HunyuanVideo-Foley** is under Tencent's
community licence, which claims no rights in the outputs. ACE-Step and MMAudio are MIT.

## Phases

Each phase is tested live on local ComfyUI before the next starts.

1. **The mix, with files.** `mix.json`; the Dialogue track is the take's sound; items on the
   other three from files; faders, gain, fades, breakpoints, ducking, loudness; assemble
   renders tracks and stems; the FCP7 export's tracks; the lanes in the editor. Useful before
   any model: a music file, a recorded room tone.
   - [x] `seriesmith/mix.py`, assemble's mix and stems (`--no-mix`), the XML's tracks,
         `GET` / `PUT /seriesmith/mix` (2026-11-01; tests/test_mix.py)
   - [x] the editor's lanes, faders and items; Play all hearing the mix (2026-11-01;
         `web/src/lib/mix.ts`, `components/SoundLanes.tsx`, `MixAudio.ts`; the preview
         doesn't duck yet, nor follow `points`; points and regions aren't drawn yet, and
         are kept as they are)
   - [ ] docs/API.md, COMMANDS.md and the user docs
2. **Music.** The `music` kind; `ace_step15` (default) and `yue2` targets; hits -> tempo,
   the arc and hits -> sections -> words; the cue's spec and takes; beat, hit and shape
   checking; refit and stale. Then the windows, in this order:
   - [x] measure first: whether energy words move ACE-Step's loudness and density (the shape
         check on a few cues), and how well it holds a tempo and a section's length (below:
         they don't; Stable Audio 3 follows an arc better and is the score default)
   - [x] the engine (2026-11-01): the `music` target kind with `stable_audio3` and
         `ace_step15`; `seriesmith/cue.py` (the spec, the plan against the cut, takes on the
         queue, each stretched and measured, ranked, the picked one placed in the mix with
         its gain fit); `beats.py`, `core/score.py`; the cue routes (docs/API.md "Music
         cues"). Live on local ComfyUI: eight Stable Audio 3 takes of a four-shot cue in about
         20 s, ranked, the best placed and exported with the mix. Hits that one tempo can't
         put on bar lines (two 4.5 s apart near 92 bpm) are fitted as near as it can, and the
         fit may go to the edge of its 8 % to land them
   - [ ] the script's `music:` notes in a cue's prompt (the shotlist doesn't carry them)
   - [ ] the cue window's Score tab (sections, the arc lane, takes with hit and shape errors)
   - [ ] the spotting sheet (the music map, hits table, tempo fit)
   - [ ] the Arc tab's drawing tools and presets
   - [ ] Orchestration & takes: the grid; comp at bar lines; Repaint once it's measured
3. **Ambience.** The `ambience` kind; a location's `ambience` as a ref; beds per sequence,
   looped; the three candidates compared.
4. **Effects.** The `foley` kind; LTX-2.3 Foley (2.3 files back, or on 2.5 if it holds), H3
   tried; effects stale when the pick changes; optionally Demucs to split a take's voice from
   its effects.
5. **Cutting to music.** Beats as snap points for trims (a montage cut to a cue); the loudness
   check on export (PLAN's "later, maybe").
6. **Tracks of your own.** Dialogue, effects, ambience and music become the default tracks
   rather than the only ones: add, rename and delete tracks (a second music track for a song
   under the score, a walla track), each with its kind (what it ducks under, which stem it
   joins: M&E or dialogue) and its own stem and XML pair. mix.py's fixed `TRACKS` becomes the
   mix's own list.

## Measured: ACE-Step 1.5 XL Turbo (2026-11-01, local, RTX 5090)

Twelve renders, then six more (scratch script; `seriesmith/beats.py` measuring, librosa's beat
tracker beside it):

- **Fast**: about 4 s for a 30-50 s cue once loaded (32 s for the first, loading). Eight seeds
  of a cue cost half a minute, so **picking the best of many takes** is cheap.
- **It holds a tempo** when the music has a pulse: asked 72 / 92 / 120 with "steady snare and
  timpani on every beat", it played 72.05, 72.05 / 92.19, 90.16 / 119.97, 119.90 (five of six
  within 0.3 %, one 2 % slow). Soft orchestral cues (legato strings, horn) defeat both beat
  trackers (librosa answered 123 for every file, whatever was asked), so a take's tempo is
  measured with confidence only where it has onsets; the window says when it can't tell.
- **The music doesn't start on 0**: the first beat came 0.03-3.1 s in. A take is **slipped to
  its measured downbeat** (the pre-roll moved) before its hits are checked.
- **Sections don't follow bar counts, and energy words don't move the level** (n = 3 each):
  `[intro 4 bars, ...] [build 8 bars, ...] [climax 4 bars, ...] [drop 2 bars ...]` at 92 bpm put
  the loudest bar at 9-11 (asked 13-16), the drop rarely at bar 17 (its dip -13 to +5 dB), and
  a fade from bar ~18; the shape error was 0.40-0.44 with energy words (quiet, fortissimo,
  building) and 0.40-0.45 without. So the arc can't be trusted to the prompt alone. What to try
  next, before building the Arc tab around words: ACE-Step's own section tags (`[Intro]`,
  `[Verse]`, `[Chorus]`, `[Bridge]`, `[Outro]`) with one descriptive line per bar or two (it
  may time sections by their lines, as it does lyrics); **a cue per section**, each its own
  length and tempo, joined at bar lines; and ranking many seeds by shape error. The volume
  breakpoints remain the sure way to shape a level.
- **It times sections by their lines** (the second probe, the same 20 bars, three seeds each):

  | Asked as | Loudest bar (asked 13-16) | Climax over intro | Drop (bars 17-18) | Shape error |
  |---|---|---|---|---|
  | **its own tags, one `(instrumental)` line per bar**: `[Intro]` + 4 lines, `[Build]` + 8 ... | **16, 13, 14** | +6.5, +6.1, +1.8 dB | **-8.7, -16.7, -4.8 dB** | **0.37, 0.37, 0.46** |
  | the same, the dynamics in the tag: `[Build - strings enter, crescendo]` | 7, 9, 9 | -0.4, +3.3, +17.4 | -4.2, -10.0, -6.1 | 0.47, 0.42, 0.37 |
  | a render per section, joined at bar lines | 15, 7, 9 | +0.1, +6.2, +1.9 | **+10.8, +8.5, +8.1** | 0.57, 0.53, 0.55 |

  A render per section is the worst: each comes out at the same level, so a quiet drop is as
  loud as the climax. **Three seeds misled**: on eight more (seeds 11-18), plain tags put the
  climax in bars 13-16 once, so the first probe's three of three was luck.
- **Nothing tried makes it follow the arc reliably** (eight seeds each, seeds 11-18):

  | Asked as | Climax in bars 13-16 | Drop of 4 dB or more | Climax over intro (median) | Shape error median (best) |
  |---|---|---|---|---|
  | its own tags, `(instrumental)` per bar | 1 / 8 | 4 / 8 | +4.9 dB | 0.44 (0.34) |
  | its own tags, the section's words on every line: `(solo piano, very quiet, sudden)` | 3 / 8 | 2 / 8 | +10.1 dB | 0.43 (0.31) |

  Over every seed so far, plain tags landed the climax 4 times in 14, words per line 5 in 11.
  The words make the climax louder (a median +10 dB over the intro, against +5), so the prompt
  writer writes them on every line, but the arc is not the prompt's to keep.

## Measured: Stable Audio 3 Medium (2026-11-01, local)

The same 20-bar arc, eight seeds each (`stable_audio_3_medium` with T5Gemma, 8 steps, lcm, cfg
1, as ComfyUI's template, without its Qwen reprompt). It takes text and a length only: no
bpm, sections or lyrics inputs, so the arc is written in prose.

| Asked as | Climax in bars 13-16 | Drop of 4 dB or more | Climax over intro (median) | Shape error median (best) |
|---|---|---|---|---|
| **the arc as a story**: "opens with a quiet solo horn, then strings and timpani build in a long crescendo to a fortissimo climax, then a sudden drop to a very quiet solo piano, ending with soft strings" | **6 / 8** | 3 / 8 | **+17.9 dB** | **0.36 (0.23)** |
| the arc with timestamps: "0:00-0:10 intro: ...; 0:10-0:31 build: ..." | 2 / 8 | 5 / 8 | +9.7 dB | 0.42 (0.22) |
| *ACE-Step XL Turbo, its best (words per line)* | *3 / 8* | *2 / 8* | *+10.1 dB* | *0.43 (0.31)* |

- **It follows an arc told as a story far better than ACE-Step follows sections**: the climax
  in place six times in eight, the climax 18 dB over the intro, the shape error a median of 0.36
  and a best of 0.23. The drop is still unsure (three in eight), which gain breakpoints fix.
- **It holds a tempo written in the text** when the music has a pulse: "72 BPM" played 72.16 and
  72.02, "120 BPM" 120.49 and 119.97; "92 BPM" 99.0 and 87.9 (7 % and 4 % off). So the tempo
  is measured on every take and fitted by stretch, as for ACE-Step.
- **Fast**: about 2 s a 52 s cue on this machine once loaded (6 s the first).
- Instrumental only (no vocals), up to about 6:20. The Stability AI Community License (free
  under a revenue threshold, to read); its T5Gemma encoder brings Gemma's terms.

So for score (underscore, a cue with an arc), **Stable Audio 3 Medium is the default
candidate** and the arc is written as a story; ACE-Step stays for songs (YuE2 too) and for a cue
that must sit on a bpm, where its integer `bpm` input is the surer tempo.

**What follows for phase 2.** The arc is kept by three things, in this order, not by the words:

1. **Many takes, ranked.** A take costs about 4 s on Turbo, so a cue renders eight by default
   (about 30 s) and they are ranked by hit error and shape error; the best of eight sat at
   0.31-0.34 against a median of 0.43-0.44. The window shows them ranked.
2. **The arc fitted by gain.** From the picked take's level per bar and the arc, breakpoints
   that pull it toward the arc (bounded, ±6 dB by default, moved to bar lines), written into
   `mix.json` as the item's points, where they can be seen and changed. This is the dependable
   part: it makes a drop drop.
3. **A better model or more steps**, measured the same way before any is the default: XL SFT
   at 50 steps, MiniMax Music 3 (installed), and ACE-Step's timbre reference.

## Open questions

- Ducking defaults (-9 / -6 dB) are guesses: tune on a real episode in phase 1.
- How well ACE-Step holds a tempo and a section's length: measure in phase 2 before the refit
  limits are fixed.
- Whether a cue should render longer than its span by default (more room to fit) or exact.
- Whether energy words (sparse ... full orchestra fortissimo) move ACE-Step's loudness and
  density reliably: measure with the shape check before building much window around them.
- Whether a masked latent repaints bars of an ACE-Step take cleanly (Fixing part of a take).
- LTX-2.3 Foley on 2.5: if it holds, no 2.3 files are needed.
