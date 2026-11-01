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
| Stable Audio 3 Medium (core template `audio_stable_audio_3_medium`) | not downloaded; licence unchecked | short cues, stingers; strong on sound design, so also an ambience candidate |
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

## Phases

Each phase is tested live on local ComfyUI before the next starts.

1. **The mix, with files.** `mix.json`; the Dialogue track is the take's sound; items on the
   other three from files; faders, gain, fades, breakpoints, ducking, loudness; assemble
   renders tracks and stems; the FCP7 export's tracks; the lanes in the editor. Useful before
   any model: a music file, a recorded room tone.
   - [x] `seriesmith/mix.py`, assemble's mix and stems (`--no-mix`), the XML's tracks,
         `GET` / `PUT /seriesmith/mix` (2026-11-01; tests/test_mix.py)
   - [ ] the editor's lanes, faders and items; Play all hearing the mix
   - [ ] docs/API.md, COMMANDS.md and the user docs
2. **Music.** The `music` kind; `ace_step15` (default) and `yue2` targets; hits -> tempo,
   the arc and hits -> sections -> words; the cue's spec and takes; beat, hit and shape
   checking; refit and stale. Then the windows, in this order:
   - [ ] measure first: whether energy words move ACE-Step's loudness and density (the shape
         check on a few cues), and how well it holds a tempo and a section's length
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

## Open questions

- Ducking defaults (-9 / -6 dB) are guesses: tune on a real episode in phase 1.
- How well ACE-Step holds a tempo and a section's length: measure in phase 2 before the refit
  limits are fixed.
- Whether a cue should render longer than its span by default (more room to fit) or exact.
- Whether energy words (sparse ... full orchestra fortissimo) move ACE-Step's loudness and
  density reliably: measure with the shape check before building much window around them.
- Whether a masked latent repaints bars of an ACE-Step take cleanly (Fixing part of a take).
- LTX-2.3 Foley on 2.5: if it holds, no 2.3 files are needed.
