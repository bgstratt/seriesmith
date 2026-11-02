# The episode's sound: four tracks, cues, a mix

Status (2026-11-02): **building**, on the `sound-tracks` branch (phases 1-6 built, 7 tried). This file is the design
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
| **Dialogue** | the take's own sound, as today (the model's mix, a dub, a clone), or its voices alone (voices only) | the shot's render; its voice stem split by Demucs |
| **Effects** | sync sound for a shot: footsteps, doors, impacts | a video-to-audio (foley) model run on the picked take, or a file |
| **Ambience** | a place's room tone or air, running across the cuts of a sequence | a text-to-audio model, once per location; or a file |
| **Music** | score cues and songs, each its own asset spanning shots | a music model; or a file |

Nothing is split early: Dialogue holds the take's sound whole, effects and all, and the other
three are added to it. A shot whose model sound fights an added effects or score track gets
that track's level lowered, or the Dialogue track goes **voices only** (built 2026-11-02,
`seriesmith/voices.py`): each take the cut plays is split by Demucs into its voices and the
rest when asked (the vocal stem's job, phase 7), kept beside the take as
`<shot>_tNN.voice.wav`, and the Dialogue track plays the voices alone. H3, Seedance and
FastH3 Omni bake their own music and room tone into each take, different at every cut, so with
beds, effects and a score laid under the cut this is usually what's wanted. A shot can keep its
whole sound (`voices: {shot: {voices_only: false}}`); a shot the script gives no lines is
silent on Dialogue unless it asks for its stem; a stem not made, or stale since the take was
rendered again, plays the whole sound and is said so.

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
the tempo was fitted, with the nearest alternatives. Render stale cues from there. Built
2026-11-01, the leitmotif reference with the `yue2` target the same day; any take, not only
the picked one, playable under the picture from its cue's in point (in the preview only).

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
is done as `targets/held_audio.py` holds sound for LTX: the take encoded (`VAEEncodeAudio`),
a noise mask over the bars to make again (seriesmith's `SeriesmithAudioSpanMask`: ComfyUI's
`SetLatentNoiseMask` can't shape a 1-D audio latent's), the take's own graph sampled again,
and the take's own audio spliced back outside those bars at the bar lines (the VAE's round
trip changes them a little). Measured first ("Measured: repaint"): ACE-Step only, at the
take's own codes by default. Comping from another take at bar lines works on any model.

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
- **Stems** in `<cut>_stems/` beside the export (48 kHz, 32-bit float, so a stem the loudness
  gain pushes past full scale isn't clipped): `dialogue.wav`,
  `effects.wav`, `ambience.wav`, `music.wav`, `me.wav` (everything but the dialogue: a dubbed
  language version is the M&E plus cloned or recorded lines) and `mix.wav`. The stems take the
  loudness gain, so they sum to the mix but for its limiter. The limiter is true-peak (run at
  4x the rate) and holds the mix 1 dB under the ceiling: the AAC it's muxed as overshoots (CupsMV
  ep01, limited to -1.5 at 48 kHz, measured -0.5 dBTP exported; held to -2 at 4x, an ep01 mix
  pushed to -10 LUFS that peaked at +3.4 measured -1.8 dBTP exported, 2026-11-02).
- **Voices only** reaches every one of these: assemble lays a clip's voice stem as its sound
  (so the mix, the stems, the M&E and the ducking's speech curve hear only voices), the XML's
  A1/A2 clip of that shot is the stem's wav (at the same offset as its take), Play all mutes
  the clip's video and plays the stem on the dialogue track in sync, and `GET
  /seriesmith/mix/duck` hears the stems.
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
| **YuE2** (core nodes: `YuE2GenerateMusic` style, lyrics, ABC, up to 900 s; `YuE2GenerateABC`) | installed: `yue2_3b_int8_convrot`; templates `audio_yue2_text2music`, `audio_yue2_music_cover` | **default song model** (`yue2`, 2026-11-01); a melody carried from cue to cue; CC BY-NC 4.0 (non-commercial) |
| **SheetSage2** (`SheetSage2AudioToABC`) | installed | a recording's melody as ABC, for YuE2 (a theme that isn't a YuE2 take); CC BY-NC 4.0 |
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

Measured 2026-11-01 (local, RTX 5090): three LAST LIGHT takes (sh040 a steel door slamming,
sh060 boots splashing, sh140 an explosion; 2.3-3 s each), each prompted with its script
`sound:` line, through MMAudio (large 44k v2, 25 steps, cfg 4.5), HunyuanVideo-Foley (XXL and
XL, 50 steps, cfg 4.5), the LTX-2.3 Foley LoRA on LTX-2.3 dev (the saved workflow: distilled
LoRA 0.4, 30 steps, audio cfg 6) and the same LoRA on LTX-2.5 dev. Every one rendered: MMAudio
35-65 s a shot, Hunyuan 48-87 s, Hunyuan XL 68-125 s (not faster here), LTX 60-120 s (first
loads included). The saved LTX workflow's **STG fails on ComfyUI 0.43** (ComfyUI-LTXVideo's
stg.py: "'AttentionTensorContainer' object has no attribute 'shape'"); with `stg` 0, no
perturbed attention and no skip blocks it runs.

**Heard (the user, 2026-11-01), best first: LTX-2.3 Foley** ("best by a long shot"),
**HunyuanVideo-Foley XL** (hit the marks; a close second), HunyuanVideo-Foley (slightly off
key), MMAudio (hit the marks, the sounds not as good), and last the LTX-2.3 LoRA on LTX-2.5
(it added vocals that made no sense and few effects: the LoRA is 2.3's). So the effects
default is LTX-2.3 Foley (its files are needed: about 36 GB), Hunyuan XL the second choice,
and the 2.5 variant is dropped.

**H3 as video-to-audio** (tried after): H3 FL2VA with the take's frames anchored from frame 0
(`MiniMaxH3AddGuide`, an image batch), a small size, the prompt "The exact video given, with
its sound effects only: <sound:>. No dialogue, no voices, no singing, no music.", 20 steps
res_multistep, only the sound decoded (`VAEDecodeAudio`; the picture never goes through the
VAE). Fast: 8-10 s a shot at 256x160, 16-22 s at 512x288, once loaded (LTX-2.3: 60-120 s).
Heard (the user): **H3 at 256x160 is about as good as LTX-2.3** ("I couldn't say which is
better"), so with H3 the default video model elsewhere, **H3 FL2VA at 256x160 is the effects
default**, LTX-2.3 Foley and Hunyuan XL the choices beside it (phase 4).

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
         `web/src/lib/mix.ts`, `components/SoundLanes.tsx`, `MixAudio.ts`)
   - [x] Play all ducks as the export does and follows the volume points; the points drawn
         and edited on the blocks; faders default to GAIN_DEFAULT (music -12 dB)
         (2026-11-01; `GET /seriesmith/mix/duck`, `lib/mix.ts` duckTracks / pointsDb,
         `web/test/mixAudio.test.ts`). Regions are applied but not drawn or edited yet
         (kept as they are)
   - [x] docs/API.md, COMMANDS.md and the user docs (checked 2026-11-02: API.md "The mix"
         (GET / PUT /seriesmith/mix, /mix/duck), COMMANDS.md's assemble (the mix, the stems,
         `--no-mix`, `--xml`'s tracks), EDITOR.md "Sound: the episode's mix", SCORING.md
         "Levels"; the regions are still only in the mix's shape, unedited in the editor)
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
   - [x] score / song (2026-11-01): a cue's `kind`, score by default; a song's default model
         is one that sings (YuE2 since it is a target, ACE-Step before; the series config's
         `sound.song_model`, as `sound.music_model` for score); a song on a model that can't
         sing is refused; the prompt says instrumental only for score. The track, its stem and
         the XML stay Music: a song, a licensed track and source music sit there too
   - [x] the script's `music:` notes in a cue's prompt: each shot's the cue plays over, from
         the story IR (`shotlist/shots.json`); Stable Audio 3 hears them as its mood, ACE-Step in
         its tags
   - [x] the cue window's Score tab (sections, the arc lane, takes with hit and shape errors)
         (2026-11-01; `web/src/components/CueWindow.tsx`, `lib/cue.ts`, `cueActions.ts`: in the
         viewer's place from a cue's block or the Music lane's New cue; one bar grid of the
         picture, hits, ruler, sections, the arc and the takes ranked, an inspector for a
         section or the cue with the model's prompt; every edit a PUT then the plan again.
         Playing a take against the picture is the spotting sheet's: below)
   - [x] the spotting sheet (the music map, hits table, tempo fit) (2026-11-01;
         `web/src/components/SpottingSheet.tsx`, `lib/spotting.ts`, `spotActions.ts`: Play all's
         player (its engine shared: Viewer.tsx useCutEngine / CutStage) with frame stepping,
         jump to hit and + Hit; the music map by sequence; the selected cue's hits table with
         each take's error, the fit and `core/score.alternatives` (the plan's `alternatives`; a
         click holds the cue at one, fixed); a take auditioned under the picture in its cue's
         place, the preview's mix only (store `audition`, MixAudio); the stale cues from `GET
         /seriesmith/cues?pass=`, rendered from there. The leitmotif reference is left for
         later: it needs a timbre / melody reference the music targets don't take yet)
   - [x] the Arc tab's drawing tools and presets (2026-11-01; `CueWindow.tsx`, `lib/cue.ts`:
         draw / points / smooth, the preset shapes, snap peaks to hits, sections from the
         arc, and beside it what the model hears with the detail it can't follow)
   - [x] Orchestration & takes: the grid; comp at bar lines; lower bars with breakpoints
         (2026-11-01; the backend: the spec's `orchestra` folded into the sections' words, and
         `cue.comp` / `POST /seriesmith/cue/comp`; the editor: the grid painted into
         `orchestra`, bars of a take selected, comped, or lowered on the cue's mix item)
   - [x] sections added and removed on the Score tab (2026-11-01; `CueWindow.tsx`, `lib/cue.ts`:
         a double-click on the Sections lane splits the section there at the nearest bar line;
         its menu splits, merges with a neighbour, edits, or resets them from the hits)
   - [x] presets (2026-11-01; `seriesmith/presets/cue.json`, served by `GET
         /seriesmith/presets?kind=cue`; the cue inspector's Preset, `lib/cue.ts` applyPreset):
         a worked example of a score's or a song's fields, its sections as shares of the cue
         fitted to its bars at the preset's tempo, with who plays in each; it asks before
         replacing the cue's own sections, style or orchestration
   - [x] Repaint (2026-11-02; measured first: "Measured: repaint". `cue.repaint` / `POST
         /seriesmith/cue/repaint`: a new take from the take's own graph, its raw file encoded
         under `SeriesmithAudioSpanMask` (comfy_nodes/audio.py) over the bars, the text encoder
         at the take's codes (`fresh`: new ones), the take's audio spliced back outside the bars
         and the take measured on the take's grid, the beat in the span checked
         (`repaint_check`); `capabilities.repaint` on ACE-Step only; the editor's Repaint beside
         Comp and Lower, with **new music**. Live on local ComfyUI through `cue.repaint` and
         `cue.finish_take`, CupsMV ep01 m03 t02 (ACE-Step, a sung song with a timbre theme):
         bars 3-4 at its codes, t04 in 2.3 s, the beat 6 of 7 as the take's 6, the levels of the
         other six bars the take's to 0.02 dB; bars 7-8 with new music, t05 in 3.5 s, 6 of 7.
         This ComfyUI hadn't been restarted to load the new node, so the live check swapped in
         KJNodes' `LTXVAudioVideoMask` with the same span, as the probe did. After the restart
         (2026-11-02), through the server and `SeriesmithAudioSpanMask`: m03 t02 bars 4-6 at its
         codes, t06, the beat 6 of 7 as the take's 6, median 27 ms)
   - [x] `yue2`: YuE2 as a song target beside ACE-Step (lyrics by section, the tempo in its ABC
         header), measured as ACE-Step and Stable Audio 3 were before it's offered (2026-11-01;
         `targets/music/yue2/`, the song default; `core/abc.py` reads a plan: its sections in
         bars and beats, its tempo set where YuE2 writes it. A take is one job: the plan, its
         `Q:` set by two core RegexReplace nodes, the song; both plans saved (SaveText), the
         sung one kept as `tNN.abc` and read into the sidecar's `song`. A song with no lyrics is
         refused. Live on local ComfyUI, CupsMV ep01 sq04 (a 20 s cue over sh280-sh330, 96 bpm
         asked, verse and chorus of original lyrics, proxy pass): two takes in 24 s, the plans
         written at 94 and 93, set to 96, heard 95.4 and 94.2, 54.4 and 51.4 s against plans of
         55.0 and 52.5 s (0.6 and 1.1 s short), planned as intro / verse / chorus (13 / 16 / 15
         and 9 / 16 / 17 bars of 2/4). The `Q:` line put after the voices, before `K:`, was sung
         at 88.3 and 88.0 with the same plans and seeds: YuE2 reads it where it writes it, after
         `L:`. The first vocal sound (a Demucs vocal stem, -20 dB of its loud part) came at 4.45
         and 0.65 s against planned first notes at 16.25 and 1.25 s: t01 sings in its planned
         instrumental intro, so the early start isn't a shorter intro, and the plan's sections
         are where to look, not a frame-true map)
   - [x] the leitmotif reference (after `yue2`): a cue names a theme (another cue's take, or one
         in the gallery); ACE-Step hears it as its timbre reference (`ReferenceTimbreAudio`),
         YuE2 as its melody (SheetSage2's ABC of it, `melody` mode); Stable Audio 3 takes none,
         so a cue with a theme is on one of those; the spotting sheet shows and sets it
         (2026-11-01; a spec's `theme`: `{cue, take}` or `{file}`; `cue.theme_for`: a YuE2 take's
         own plan sung (its chords dropped, `melody` mode), anything else transcribed by
         SheetSage2 in the same job, ACE-Step's `LoadAudio -> VAEEncodeAudio -> ReferenceTimbreAudio`
         on the prompt's conditioning (no template wires it; wired as its inputs say), Stable
         Audio 3 warned and rendered without it; part of a take's fingerprint. The editor's
         Theme in the cue inspector and the spotting sheet, with the switch to ACE-Step / YuE2.
         Live, CupsMV ep01: m03 with m02 t01 as its theme: YuE2 from that plan in 10 s (heard
         94.9, 54.6 s of a 55.0 s plan, the same 13 / 16 / 15 bars); SheetSage2 from m02 t02's
         sound in the same job (it read 98 bpm of 96, set back to 96: heard 95.4, 52.0 s of
         52.5, t02's 9 / 16 / 17 bars carried); ACE-Step Turbo with it as its timbre, 20 s in
         13 s, heard 95.7. Whether ACE-Step's timbre reference is heard is for the ear: with a
         reference its conditioning drops the LM's audio codes and treats the reference as a
         cover's source (model_base `is_covers`))
3. **Ambience.** A place's bed under every sequence set there, from the cut, looping across
   its cuts. Decided 2026-11-01 (Measured: ambience beds):
   - **A place, by `of`.** A location's place is its root: follow `of` (a relit or reverse
     variant, the bokeh behind a close-up) to the location with none. The place's
     `ambience` (words: what's heard there) and bed (`ambience_bed`, a path like `plate`,
     default `../refs/_amb/<place>.wav`) serve every variant; a variant's own `ambience`
     gives it its own bed (a golden-hour hall with evening birds).
   - **A ref.** The bed is made like a plate: refs_todo lists a place with words and no bed,
     `seriesmith refs` and the Refs tab's Ambience make it, takes kept, one picked. The
     `ambience` target kind: `mmaudio_ambience` the default (text only, 10 s, 25 steps, cfg
     4.5, the negative "music, melody, singing, speech, talking, voices"), `sa3_sfx_ambience`
     beside it (Stable Audio 3 Small SFX, 30 s, 8 steps LCM); the prompt is the words and
     "No music, no voices, no speech." A take is finished as it lands: 1.5 s off each end,
     brought to the bed level (BED_LUFS, -32: room tone sits well under the lines at the
     fader's 0 dB), written as the bed.
   - **Laid from the cut, not placed.** The mix's ambience is worked out from the cut and the
     series config when the mix is read, never stored as items: each run of shots whose
     sequence is set in one place gets that place's bed, looped (equal power), the runs
     crossfaded 0.5 s into each other; a shot moved, trimmed or cut changes it with nothing to
     refit. The mix keeps only what you change: `beds: {place: {gain_db, mute}}`, the
     Ambience fader and its ducking (-6 dB under speech). An item you put on the Ambience
     track yourself (a recorded room tone) plays over the beds; `beds: {place: {mute}}`
     silences a place's.
   - **Shown on the lane** as blocks (the place's name), read-only but for a menu: its level,
     mute, open its ref.
   - [x] series config: a location's `ambience`, `ambience_bed`; the place by `of` (2026-11-01;
         `core/series_config.py` ambience_bed_of / ambience_beds: a location's own bed when it
         says `ambience` or `ambience_bed`, else its place's, location_master; nothing
         automatic. The default file is `_amb/<id>.wav` in the refs folder the plate is in:
         `../refs/_amb/diner.wav` beside `../refs/_bg/diner.png`, `refs/_amb/<id>.wav` for a
         plate under `refs/` or none, so a series config in the show's folder keeps its beds
         in the show)
   - [x] the `ambience` kind: `mmaudio_ambience`, `sa3_sfx_ambience`; the bed finished as it lands
         (2026-11-01; `targets/ambience/`, `seriesmith/ambience.py` finish_bed: 1.5 s off each
         end of a take of 4.5 s or more, one gain to BED_LUFS; the Features window's Ambience
         beds: ComfyUI-MMAudio and its four files, and Small SFX)
   - [x] refs: refs_todo's beds, `seriesmith refs` makes them, the Refs tab's Ambience
         (2026-11-01; `ambience:<place>` refs in refs.py, seeded from the place's id; build's
         with_beds lists them as kind "ambience bed"; kreagen makes them with the pictures;
         `GET /seriesmith/ambience`, a row's takes from `GET /seriesmith/refs/one` when it opens)
   - [x] the mix: beds from the cut (render, Play all, stems, XML), `beds` in mix.json
         (2026-11-01; `ambience.laid` / `render_beds` / `bed_lanes`, `mix.render(beds=)`,
         `mix.placed(beds=)`, assemble: a bed that's there and not muted makes a mix by itself;
         `GET /seriesmith/mix` `beds`, Play all's `lib/mix.ts` bedPlan)
   - [x] the editor: the beds on the Ambience lane; a location's ambience in its form
         (2026-11-01; `SoundLanes.tsx` BedBlock / BedMenu, `SoundRefs.tsx` BedRow, the location
         card's Ambience and Ambience file)
   - [x] docs: AUTHORING (a location's ambience), API, EDITOR, SCORING's Levels (2026-11-01)

   Live on local ComfyUI (2026-11-01, CupsMV ep01): the diner's words made one MMAudio take
   (10 s, 25 steps, about 15 s with the model loading) by `seriesmith refs --all --only
   ambience:diner`, finished to 7.0 s at -32.0 LUFS (it came at -27.2) and picked into
   `../refs/_amb/diner.wav`; a Small SFX take beside it came at -40.8 LUFS, 30 s -> 27.1 s.
   `assemble --pass proxy` laid it under sq01 and sq04 (the diner) and nothing under sq02
   (platform) and sq03 (car): the ambience stem measured -38.1 and -38.5 dBFS RMS over the
   diner sequences (second by second -39.6 to -34.6: the bed ducked 6 dB under the song, and
   the mix's -2.6 dB loudness gain), silence (no sample above zero) over the other two, and the
   0.5 s fades at the cuts (-41 -> -48 -> -64 dB out of sq01, the mirror into sq04).
4. **Effects.** A shot's sync sound (footsteps, a door, the cups) made from the frames of the
   take the cut uses. Decided 2026-11-01:
   - **Asked for, never automatic.** Many takes already carry the model's own effects in their
     sound (the Dialogue track: H3 makes picture and sound together), so effects are made only
     for the shots you ask (a clip's Sound menu, a selection, the CLI); a shot dubbed or cloned
     (its sound only the voice), or a picture model with no sound, is where they're wanted.
   - **The `foley` kind**: `h3_foley` the default (H3 FL2VA at 256x160, the take's frames
     anchored from frame 0 with `MiniMaxH3AddGuide`, 20 steps res_multistep, only the sound
     decoded), `ltx23_foley` (the LTX-2.3 Foley LoRA, STG off) and `hunyuan_xl_foley` beside
     it; graphs as measured (Measured: foley). The prompt is the shot's `sound:` line (else its
     action) and "No dialogue, no voices, no singing, no music."; the length is the take's,
     all of it, so the cut's trims trim the effects with the picture.
   - **A shot's effects takes**: `<ep>/sound/fx/<pass>/<shot>/tNN.wav` + `tNN.json` (the model,
     the prompt, the seed, and the take it was made from: its number and its mp4's size and
     mtime), several per shot, one picked.
   - **Laid from the cut, as the beds are**: each shot in the cut with a picked effects take
     gets it on the Effects track at its clip, anchored to the take's frame 0, trimmed with the
     clip; nothing stored as items. The mix keeps `fx: {shot: {take, gain_db, mute}}` (the pick
     is the pass's mix's).
   - **Stale when the picture changes**: effects made from another take than the cut's (or a
     take re-rendered since) are flagged and left out of the mix until made again, or kept
     on purpose (`fx: {shot: {keep_stale: true}}`): sound that doesn't match its picture is
     worse than none.
   - **Shown on the Effects lane** as a block per shot (its id, the model, stale marked),
     read-only but for a menu: level, mute, its takes (play, pick), make again (the model),
     keep as it is when stale.
   - [x] the `foley` kind: `h3_foley`, `ltx23_foley`, `hunyuan_xl_foley` (target.json, files
         and downloads for Features, the graphs) (2026-11-01; `targets/foley/`. The take goes up
         as a file through ComfyUI's own `LoadVideo` / `GetVideoComponents`, made the model's
         size and frame rate first by `fx.stage` (ffmpeg: 256x160 at 24 fps for H3, 512x288 cut
         to 8k+1 frames for LTX, 512 wide at the take's rate for Hunyuan), so nothing in the
         graph reads the episode folder and any backend runs it. LTX-2.3's audio VAE loads
         through core `VAELoader` (the saved workflow's `VAELoaderKJ` isn't needed). Features:
         Effects (H3), (LTX-2.3 Foley: ComfyUI-LTXVideo and 7 files), (HunyuanVideo-Foley XL:
         phazei's pack and 3 files); download URLs listed from the Hugging Face repos)
   - [x] a shot's effects takes, made on the queue (`seriesmith fx`, `POST /seriesmith/fx/render`
         for shots or a selection), stale against the cut's take (2026-11-01; `seriesmith/fx.py`,
         job kind `fx` with cue's limits, picked up again after a restart; the sound fitted to
         the picture's length as it lands; `GET /seriesmith/fx` a shot's takes with `stale`,
         `POST /seriesmith/fx/pick`; the series config's `sound.effects_model` names a series'
         own model; a job whose picture changed between asking and starting fails, saying so)
   - [x] the mix: effects from the cut (render, Play all, stems and M&E, XML), `fx` in mix.json
         (2026-11-01; `fx.laid` / `render_fx` / `fx_lanes`, `mix.render(fx=)`,
         `mix.placed(fx=)`, assemble: a heard one makes a mix by itself, a stale one is named
         in the report; `GET /seriesmith/mix` `fx`)
   - [x] the editor: the Effects lane's blocks and menu, a clip's Sound ▸ Make effects
         (the selection), the takes (2026-11-01; `SoundLanes.tsx` FxBlock / FxMenu, `lib/mix.ts`
         fxPlan, `mixActions.ts` makeEffects / pickMixFx / setMixFx: a pick is an undoable
         mix edit; not yet looked at in a browser)
   - [x] docs: API, EDITOR, COMMANDS, FULL_SETUP; live: CupsMV's cup shots on local ComfyUI
         (2026-11-01, below)
   - [x] **voices only** (2026-11-02; `seriesmith/voices.py`, "Measured: voices only" below):
         each take the cut plays split by the vocal stem's job (`SeriesmithVocals`, phase 7) into
         `<shot>_tNN.voice.wav` and its `.voice.json` (what it was split from: stale when the
         take's sound changes, as effects are), one queued job a take (`seriesmith voices`, `POST
         /seriesmith/voices`); mix.json's `tracks.dialogue.voices_only` and `voices: {shot:
         {voices_only}}`; assemble's clips, stems, XML, the speech curve and Play all hear the
         stems, a missing or stale one plays whole (said, `GET /seriesmith/mix` `voices`); a
         shot with no lines silent unless it asks (decided on ep02, below). The editor: the
         Dialogue lane head's ⋮ (Voices only, Make voice stems with "N/M shots split"), its clips'
         marks, a clip's Sound ▸ Keep its whole sound / Voices only / Split its voice again.
         Not yet heard by the user, nor looked at in a browser

   Live on local ComfyUI (2026-11-01, CupsMV ep01, proxy pass, RTX 5090): `seriesmith fx
   --proxy --shots sh010` made one `h3_foley` take in 40 s with H3 loading, then sh020 and
   sh030 in 21 s for the two (about 10 s a shot); each 5.167 s, the take's 124 frames (the model
   gave 5.175 s, cut to the picture). Prompted from the action (the script has no `sound:`
   lines): "The exact video given, with its sound effects only: Close on June's hands on the
   formica table: she claps twice, taps the upturned plastic cup three times, and lifts it. No
   dialogue, ...". Picked (`--pick`) and `assemble --proxy`: "effects under 3 shot(s)" beside
   the diner's two bed runs; the effects stem measured -37.9 / -29.8 / -16.7 dBFS RMS over
   sh010 / sh020 / sh030 (peaks -9.3 / -3.3 / -6.9; the clips trimmed to their song windows,
   118, 118 and 109 of 124 frames) and no sample above zero over the other 30 shots. Stale,
   on the same takes with the cut's take for sh010 seen as t02 (nothing re-rendered): sh010
   laid as "made from t01; the cut plays t02", not heard (silence over its clip), sh020 and
   sh030 unchanged; with `keep_stale` it played at -35.1 dBFS. The other two models on sh020:
   `ltx23_foley` 79 s with loading (121 frames, 5.01 s padded to 5.167; RMS -16.9 dB, peak
   0.0 dB: it reaches full scale), `hunyuan_xl_foley` 43 s with loading (RMS -31.8 dB). Not
   listened to yet; sh030's H3 take is loud (-14 dB RMS) and worth hearing first.
5. **Cutting to music.** Beats as snap points for trims (a montage cut to a cue); the loudness
   check on export (PLAN's "later, maybe").
   - [x] the beats (2026-11-02): a cue take's grid from its sidecar (`cue.take_grid`: the cue's
         tempo through its measured downbeat), any other file's measured once and kept beside
         it (`beats.file_grid` -> `<file>.beats.json`, by size and mtime: `comb_tempo` scores
         each tempo by the onset envelope's autocorrelation at one to four beats, as `tempo()`
         alone read an ACE-Step cue heard at 98 as 130; `refine` fits a line through the
         onsets near the beats so a song's grid doesn't drift; four beats a bar). `GET
         /seriesmith/mix/beats`: each music item's grid and the recording's. Measured: the
         CupsMV song 130.00 bpm (strength 1.72), its accompaniment and vocal stems 130.4 /
         130.0 (0.52), CupsMV m03 t01 (a YuE2 song cue, 96 asked) 96.16 with the downbeat 21 ms
         from its sidecar's, the ACE-Step repaint probe's score 97.99 (98 heard); not steady:
         Ballroom ep03's assembled cut (dialogue under soft score, 0.21) and ep01's (0.22).
         Measuring the 2:07 song took 1.1 s
   - [x] trims snap to them (2026-11-02; `web/src/lib/beats.ts`, `Timeline.tsx` onEdgeDown): the
         cut at a clip's end moves onto the nearest beat within 7 px (a downbeat within 12 px,
         preferred), either edge (a head trim moves that cut too), to the beats that stay put
         while it moves (`fixedBeats`: music anchored before the clip, or on it for a tail
         trim; the recording unless it's the first clip's head); **Alt** bypasses it; the tip
         says which beat ("bar 12"). The music items' beats, else the recording's when it has
         a steady one. Fetched when the mix's music files or the recording change
         (`mixActions.loadBeats`), never polled; drawn faintly on the Music lane, thinned when
         zoomed out (`BeatTicks`)
   - [x] the loudness check on export (2026-11-02; `mix.loudness_target` / `loudness_check`,
         assemble): the mp4 measured (loudnorm's integrated, range and true peak, the picture
         not decoded) against the mix's target, printed (`!` when more than 1 LU off or over
         the ceiling), kept as `<cut>_loudness.json`, answered by `POST /seriesmith/assemble`
         as `loudness` and said in Export's toast; the sound never changed. Live, CupsMV
         (proxy, 33 shots, 2:07): ep02 with its mix (the song on the Music track at 0 dB) -16.1
         LUFS integrated, range 13.7 LU, true peak -4.5 dBTP (the mix measured -5.3 before the
         AAC encode); ep01 with `--audio master` (the mastered song under the cut, no mix)
         -10.5 LUFS, 13.2 LU, +1.1 dBTP: "5.5 LU over the -16 target ... over the -1 ceiling;
         the cut's own sound, as it came"
   - [ ] looked at in a browser: the snapping and the ticks on CupsMV ep02 (the song) and
         ep01 (the cue m03)
6. **Tracks of your own.** Dialogue, effects, ambience and music become the default tracks
   rather than the only ones: add, rename and delete tracks (a second music track for a song
   under the score, a walla track), each with its kind (what it ducks under, which stem it
   joins: M&E or dialogue) and its own stem and XML pair. mix.py's fixed `TRACKS` becomes the
   mix's own list.
   - [x] mix.json's `track_list` (2026-11-02; `mix.check_track_list`, `track_list` / `kinds` /
         `first_of`): `[{"id", "kind", "label"}]` in lane order, none for the four defaults (an
         old mix.json loads and renders as it did: CupsMV ep01 proxy, every stem, the mp4 and
         the XML byte for byte the same before and after). A track's kind gives its default
         fader and duck depth, what a region's `music_duck_db` / `ambience_duck_db` reach, and
         whether it joins the M&E; the speech the mix ducks under is every dialogue-kind
         track's. The four default ids keep their kinds and can be renamed; `dialogue` (the
         takes' sound) can't be taken out; an id names its stem, so `me`, `mix` and Windows'
         device names are refused; at most 16. Beds go on `ambience`, else the first ambience
         track (none: left out, said); effects likewise; a cue placed again keeps the track
         it was moved to (`cue.place`). Decided here: a track's kind is fixed once made
         (delete and add to change it), and the default dialogue track's own items still
         aren't carried in the XML (another dialogue-kind track's are, a pair of its own)
   - [x] stems and XML (2026-11-02): `<id>.wav` per track, `me.wav` every track but the
         dialogue kind's, a stem of a track that's gone removed from `<cut>_stems/`; the XML a
         pair per track in the list's order after the clips (and the recording)
   - [x] the API (2026-11-02): `GET /seriesmith/mix` answers `track_list` (named) and the
         defaults' `labels`; `PUT` checks the list, and refuses an item on a track that isn't
         in it (so deleting a track with items is the editor's question, never a silent loss)
   - [x] the editor (2026-11-02; `lib/mix.ts` trackList / addTrack / renameTrack / moveTrack /
         deleteTrack / itemToTrack, `SoundLanes.tsx` TrackMenu, `MixAudio.ts`): a lane head's
         ⋮ (or right-click) renames the track, adds one below the lanes (its kind and name),
         moves it up or down, deletes it: a track with items asks there whether they move to
         another track (one of its kind first) or go with it; the dialogue track says it can't
         be deleted. A block dragged up or down onto another lane, or its menu's Track, moves
         it. Play all makes a fader per track as it's first heard. Not yet looked at in a
         browser
   - [x] live (2026-11-02, CupsMV ep01 proxy, the user's mix.json put back byte for byte
         after): a Song track (music kind, -6 dB) with the song from sh010 under the Score
         track's cue m03 (Diner reprise). The stems: dialogue, effects, ambience, music, song,
         me, mix; the M&E the four non-dialogue stems summed to 2e-7 where none clipped; over
         the cue's span the song -27.9 dBFS RMS against the score's -33.8. The XML: twelve
         audio tracks, A1/A2 the clips (33 each), A3/A4 the recording, A5/A6 effects (3), A7/A8
         the diner beds (4), A9/A10 "Diner reprise", A11/A12 "When I'm Gone". The export's
         loudness check said the AAC-encoded mix peaked at -0.5 dBTP over the -1 ceiling
         (the mix was limited to -1.5 before encoding); and the stems clip where the loudness
         gain (+6 dB here) pushes them past full scale (0.08 % of samples: the effects stem),
         as they did before: only the mix is limited
7. **Song-first (a music video).** The picture is cut to a finished song, not the music to
   the picture. The song arrives mastered, so nothing of the mix applies: it's the
   episode's recording, as a recorded dub is (docs/RECORDED_DIALOGUE.md): `audio.mode:
   source_track`, each shot an `audio: in-out` window of it, `retention: fully_copy` so a
   singer's lips follow their window, and `assemble --audio master` for the song unbroken
   under the cut. Most of it exists; what's left to find out on one real song:
   - [x] align with the lyrics as the script's lines (faster-whisper on a sung vocal; the
         vocal stem from Demucs, as RECORDED_DIALOGUE says for a recording with music)
         (2026-11-02; vocals.py, comfy_nodes/audio.py `SeriesmithVocals`): **opt-in, off by
         default**, since H3's lip-sync was as good to the full song as to the stem (below).
         The stem is made on local ComfyUI as a queued `vocals` job (LoadAudio ->
         SeriesmithVocals -> SaveAudio: torchaudio's HDEMUCS_HIGH_MUSDB_PLUS, 10 s chunks
         faded over 1 s, as torchaudio's tutorial; nothing installed, the weights read from
         models/demucs/ (Features: Vocal stem) or downloaded once by torchaudio), kept as
         `<recording>.vocals.wav` while it's as new as the recording. `align --vocals` (the
         Recording window's "from the vocal stem") transcribes and cuts from it, the series
         config still the song; `audio.dub_from: "vocals"` ("dub shots hear the vocal stem")
         has build write the shotlist's `defaults.dub_track`, which every dub window is cut
         from (held_audio.dub_recording), the episode's sound still the song. Live: the node's
         function in ComfyUI's own Python on CupsMV's song split the 2:07 in 5.1 s on the 5090,
         the same stem as the one-off script's (correlation 0.99999996); align --vocals on a
         scratch copy of ep01 (large-v3 on the CPU: this venv's CUDA has no cublas, 3 min)
         heard 241 words and matched all 30 sung lines 100 %; with dub_from on, sh050's render
         (dry run) uploads `song.wav.vocals.wav`. ComfyUI must restart once to load the node
         (a backend without it is told so before anything is sent). After the restart
         (2026-11-02), end to end: `POST /seriesmith/vocals` on CupsMV ep01 queued the job, the
         stem written back in 4.2 s, the same as the one-off's (correlation 1.0); with
         `nvidia-cublas-cu12` Whisper runs on the GPU: align --vocals (dry run) large-v3 28 s,
         all 30 lines 100 %; large-v3-turbo 11 s, 27 of 30 (three at 67-88 %)
   - [x] whether a singing shot lip-syncs better to the vocal stem than to the full song
         (the window sent the model could be the stem's, the episode's sound the song's)
   - [x] shots that don't sing (the band, b-roll) get their window with no lips to sync
   - [x] cutting to the song's beats: phase 5's snaps, on the recording instead of a cue
         (2026-11-02: the song on the Music track is measured as any file is; with no music
         on the lane, the recording's beats when it has a steady one (CupsMV ep01: the song as
         the recording, 130.00 bpm); not yet tried by hand in the editor)
   - [x] a guide: Making a music video (2026-11-02; docs/MUSIC_VIDEO.md, on the site after
         Scoring): the song as the recording, the lyrics as lines, align, render, cutting to
         the beat, the two exports, the vocal stem; CupsMV the example
   Tried 2026-11-01 on a 2:07 pop song (CupsMV, local, H3 Ref2VA proxy, 33 shots, 11:45 a
   pass on the 5090): the vocal stem split by torchaudio's Hybrid Demucs
   (`HDEMUCS_HIGH_MUSDB_PLUS`, in ComfyUI's own Python, nothing installed); the stem
   transcribed (faster-whisper large-v3; align's own transcriber, fixed for PyAV 19) and the
   script's lines taken from it, a singing shot at most 6 s cut at the phrase's widest gap;
   align run on each episode with `--words` from the stem. Two episodes, the same windows and
   seeds: ep01 dubbed with the full song (`--audio master` under the cut), ep02 with the stem
   (the song on the Music track at 0 dB, no ducking, Dialogue muted; it lands to the sample).
   The user's verdict: both spot on and hard to tell apart at proxy size (unlikely to differ
   much in full HD), so both ways are offered; the stem is the cleaner input. A shot with no lines renders in `generate`
   mode, its own sound, so the song must come from the master or the mix, never the clips.

## Measured: voices only (2026-11-02, local, RTX 5090)

Ballroom ep02 "Right of Way" (final pass, the 11 shots the cut plays: ten on H3 Ref2VA, sh100
on FastH3 Omni; four with a line), each take split by `seriesmith voices` through the queue
on local ComfyUI (the take's sound staged as a wav, LoadAudio -> SeriesmithVocals ->
SaveAudio). The levels are dBFS RMS over the take; "in the gaps" is over the 100 ms windows
where the stem is 25 dB under its own loudest (no one speaking), the whole sound there being
what voices only takes away. Whisper (large-v3-turbo) on each stem heard the four lines as
written.

| Shot | Lines | Split | Whole | Voice stem | The rest | Whole in the gaps | Stem in the gaps |
|---|---|---|---|---|---|---|---|
| sh010 | none | 4.7 s (Demucs loading) | -31.2 | -76.7 | -31.2 | -31.9 | -92.6 |
| sh020 | "King me." | 0.5 s | -27.6 | -28.1 | -36.9 | -34.9 | -56.9 |
| sh030 | "Lucky." | 0.4 s | -27.0 | -27.0 | -64.0 | -56.1 | -57.0 |
| sh040 | none | 0.4 s | -23.5 | -32.4 | -24.8 | -25.7 | -57.0 |
| sh050 | "Look out!" | 0.4 s | -24.5 | -24.5 | -51.9 | -47.4 | -52.7 |
| sh060 | none | 0.3 s | -23.8 | -46.2 | -24.0 | -48.2 | -66.4 |
| sh070 | none | 0.4 s | -21.1 | -70.4 | -21.1 | (none) | (none) |
| sh075 | none | 0.4 s | -26.3 | -77.6 | -26.3 | (none) | (none) |
| sh080 | "Sorry!" | 0.4 s | -30.3 | -30.4 | -48.4 | -45.7 | -57.1 |
| sh090 | none | 0.5 s | -40.7 | -49.1 | -42.0 | -42.8 | -79.2 |
| sh100 | none | 0.4 s | -42.0 | -59.8 | -42.2 | -54.8 | -75.9 |

- **Fast**: under half a second a take once Demucs is loaded (4.7 s the first).
- **The lines keep their level, the bed under them goes**: on sh020 the stem sits 22 dB under the
  whole sound between the words; sh030's and sh050's takes had little but the voice to begin
  with (the rest -64 and -52 dB).
- **The shots with no lines**: three stems are silence (-70 to -78 dB); four hold something,
  Whisper hearing "Yes." on sh040 (-32 dB, under a bicycle bell and a rattling chain), "Okay."
  on sh060 (-46), "Yeah." on sh090 (-49: the park's distant chatter), and sh100 at -60. That's
  the model's ad-libs and walla, not the script's lines. **Decided**: under voices only a shot
  the script gives no lines is silent on the Dialogue track, unless the shot itself is set to
  voices only (a gasp or a shriek the model gave it that's wanted). Easy to turn round: it's
  `voices.plays`.
- **Exported** (`assemble --name` a scratch cut, mix.json made for it and taken away after):
  "voices only: 4 of 11 shot(s) play their voice stem, 7 with no lines silent"; the dialogue stem
  over each line shot the stem's level plus the loudness gain (+4.7 dB), silence elsewhere (the
  AAC's bleed at -60 to -95 dB just after a line); -16.2 LUFS, true peak -2 dBTP. The XML's A1/A2
  clips of the four line shots are their stems' wavs. The speech curve over 0.5 fell from 470
  of 580 steps (the takes' music read as speech) to 106. The first export dropped the sound
  after sh030: with every clip a stem or silence nothing was copied with its own sound, and the
  stems' 44.1 kHz stereo met the silent clips' mono in the concat. Both are 44.1 kHz stereo now.

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

## Measured: YuE2 (2026-11-01, local)

`yue2_3b_int8_convrot` with the core nodes as the `audio_yue2_text2music` template wires them
(`YuE2GenerateABC` -> `YuE2GenerateMusic` -> `EmptyYuE2LatentAudio` from its seconds ->
KSampler 32 steps dpm_2 sgm_uniform cfg 1 -> `VAEDecodeAudio`), a warm acoustic pop style
asking 96 BPM, four sections of original lyrics, three seeds, three ways: **A** the tempo in the
style words only (no plan), **B** YuE2's own ABC plan, **C** that plan with its `Q:` line set
to `1/4=96`. Files in `ComfyProjects\_yue2_test`.

- **The plan comes first and is real structure**: ABC in ~23 s with `M:` (2/4 or 4/4), `Q:`
  (93-94, near the asked 96), `K:`, a vocal and an instrumental voice, and the sections as
  `% intro` / `% verse` / `% chorus` / `% outro` comments over whole bars.
- **Tempo: C holds it exactly.** Heard 96.0 / 96.1 / 96.0 (A drifted -4 to -20 %: 91.8, 88.1,
  77.0; B played each plan's own tempo: 93.1, 94.1, 94.0 against Q 93, 94, 94). The ABC's `Q:`
  drives it; the style words barely do. A song cue sets the fitted tempo in the plan.
- **Where the `Q:` line goes matters** (found building the target, CupsMV ep01, the same plans
  and seeds): set where YuE2 writes it (after `L:`), heard 95.4 and 94.2 of 96; moved after the
  `V:` lines, before `K:`, heard 88.3 and 88.0, the takes 4 s longer. The target sets it after `L:`.
- **Length follows the plan's bars**: every take 1.2-3.6 s short of its plan's bars at its
  tempo (~2 %), the shortfall seemingly at the start (the first sung bar early by 1.75 and
  4.1 s; the end of singing measured from the end of the song 0.9 and 3.2 s off). Sections
  land within a few seconds of the plan, not to the frame: a song is measured and ranked as a
  score cue is. (The bar counts here are a rough reading of the ABC; the target needs a real
  one: pickups, ties, multi-bar rests.)
- **Fast**: a 2-2.5 minute song in 18-22 s on the 5090, the plan included.
- So a `yue2` song cue: the plan first (or one carried over: the leitmotif), its `Q:` set to
  the fitted tempo, its sections' bar counts read to place them on the cue's bars; then the
  song, measured against the plan. Heard by the user: solid: go forward (2026-11-01).

## Measured: ambience beds (2026-11-01, local)

Four places with different kinds of sound (a quiet country-house hall, a park by day, a tar
rooftop in heavy rain, a diner at night), each written as what's heard there and "No music, no
voices, no speech.", two seeds each on Stable Audio 3 Medium (30 s, its 8-step LCM settings)
and MMAudio large 44k v2 with no video (10 s, 25 steps, cfg 4.5, negative "music, melody,
singing, speech, talking, voices"). The files are in `ComfyProjects\_ambience_test`, each also
looped to 60 s.

- **The loop's crossfade was linear and dipped 2-3 dB at every seam** on a steady bed (rain,
  hum): a linear fade between two unalike signals loses 3 dB halfway. `mix.looped` now fades at
  equal power (sine/cosine); the steady beds' seams measured within 1 dB after.
- **The ends aren't the bed.** Stable Audio 3 started its diner beds ~9 dB above where they
  settled and let most beds trail off in the last second; one MMAudio hall bed faded in from
  near silence. A bed is the middle: its first and last second or two are dropped before it
  loops.
- **Levels differ by model and seed:** Stable Audio 3 -23 to -41 LUFS, MMAudio -17 to -22. A
  bed is brought to one level when it's made, so the Ambience fader means the same for
  every place.
- **Steadiness:** MMAudio's diner, rooftop and park held within 0.5-1.8 dB second to second;
  Stable Audio 3's beds moved 2-5 dB (more events, more life, harder to loop). The quiet hall
  moved most on both (7-8 dB), as a room of clock ticks and creaks should.
- **A place, not a picture.** A series' locations are often variants of one place (a reverse
  angle, golden hour, the bokeh behind a close-up: Ballroom has 24 locations and five places).
  A bed belongs to the place, so variants share one; how a variant names its place is the
  design's open question.

Stable Audio 3 Small SFX (2.3 GB, sound effects only; 30 s in ~2 s) and H3 FL2VA (the
location's plate as the first frame of a locked-off empty shot, 256x160, ~10 s in 8-16 s, only
the sound decoded) were added to the test; Small SFX came out quiet (-24 to -49 LUFS).
Listened loudness-matched (-23 LUFS, 60 s loops), the user's ranking: **MMAudio** (the clear
winner: the diner's refrigerator hum far better), then Stable Audio 3 Small SFX, then Stable
Audio 3 Medium, then H3. Other open models looked at: Sony's Woosh (non-commercial weights,
and reportedly outputs), TangoFlux (research only), AudioX and AudioGen (non-commercial).

## Scored: Ballroom ep03 "Choice" (2026-11-01)

The first episode scored end to end (57 s, deadpan comedy played straight, wall-to-wall
dialogue): three cues, eight Stable Audio 3 takes each on local ComfyUI, ranked, the best placed.
1M1 The Selection (sh010 to "Oh.", a romantic swell arriving on "I choose you", cut dead on
"Oh."), silence under the family's moves, 1M2 The Departure (a pompous processional under the
exit, cut dead on the door's thud, found from the take's own sound at sh100 frame 111), silence
for "We should make preparations.", 1M3 Chosen (music box and pizzicato with the clock, a turn on
her question). What it taught:

- **A drop on a cue's out point is its end**: the music is cut there, so it's neither fitted to a
  bar line (two hits 2.3 s apart can't both be) nor measured in the takes; `cue.plan` marks it
  `ends`.
- **Takes can be measured again** against a new plan without rendering (`cue.remeasure`), when the
  tempo is still within 8 % of what they were played at.
- **Levels**: at a 0 dB (then -4 dB) music fader the score was louder than the dialogue under
  Charming's line even with the -9 dB dip; at **-12 dB** it sits 5-10 dB under the lines and level
  with the dialogue on the swell. So a music track's default is -12 dB (GAIN_DEFAULT), and Play
  all ducks as the export does (the server's speech curve, 2026-11-01), so the editor no longer
  plays it louder than the export.

## Measured: repaint (2026-11-02, local, RTX 5090)

Bars of a take made again, the rest kept: the take's raw file encoded (`VAEEncodeAudio`), a
noise mask of ones over the span and zeros elsewhere on the audio latent (ACE-Step 1.5's and
YuE2's are `[batch, 64, frames]` at 25 frames a second; ComfyUI's `SetLatentNoiseMask` makes a
picture's height-by-width mask, which a 1-D latent can't take, so the probe used KJNodes'
`LTXVAudioVideoMask`, audio only, `partial`; seriesmith's node pack has its own,
`SeriesmithAudioSpanMask`), the take's own graph and conditioning, KSampler at the take's
settings with a new seed, decoded; then the take's own audio spliced back outside the span
with 20 ms equal-power crossfades at the bar lines, as a comp is. Three sources: an ACE-Step
1.5 XL Turbo score cue of our own (96 bpm asked, 98.0 heard, 4/4, 40 s, a kick and snare on
every beat), CupsMV ep01 m03 t02 (ACE-Step, a sung song with m02 t01 as its timbre reference,
20 s) and m02 t01 (YuE2, a 54 s song); the CupsMV takes read only, copied. Spans of 2 and 4
bars mid-take and the last 2 bars to the end, three seeds (two on the CupsMV takes), and for
ACE-Step four ways: the text encoder at the take's seed (**its codes**: ACE-Step's language
model writes the same 5 Hz semantic codes the take was made from) or a new one (**new codes**),
at denoise 1.0, 0.85 and 0.7. Files and the probe's numbers in `ComfyProjects\_repaint_test`.

| | Kept bars (a) | Grid in the span (b) | Seams (c) | Change in the span (d) | Render (e) |
|---|---|---|---|---|---|
| ACE score, its codes, d1.0 (2 and 4 bars mid) | the round trip only: 0.975 | **every beat within 3 ms, as the take (24/24)**; 97.7-98.1 heard | level step at the bar line within -3.5 to +1.3 dB of the take's own; no click | spectra 0.92-0.95 (round trip 0.97), waveform 0.65-0.72 | 1.3 s (6 s cold) |
| ACE score, its codes, d0.7 | the same | the same | -2.8 to +1.2 dB | 0.93-0.95, waveform 0.76-0.83 | 1.3-3.7 s |
| ACE score, new codes, d1.0, 2 bars | the same | 8/8 on the beat | -6 to +0.6 dB | 0.88-0.91, waveform 0.26-0.42 | 3.3-3.7 s |
| ACE score, new codes, d1.0 / 0.85, **4 bars** | the same | **off the beat on 4 of 6** (1-4 of 16 beats on it, 70-96 ms late) | -8.6 to +1.6 dB | 0.76-0.91 | 3.3-3.7 s |
| ACE score, the last 2 bars (an ending, no beat) | the same | (none to hold) | -8.5 to +1.2 dB | 0.68-0.88 | 1.3-3.7 s |
| ACE song with a timbre reference (m03 t02), its graph | the round trip only: 0.995 | 95.2-97.0 heard (96 asked); as near the beat as the take (a sung song: few onsets) | -3.2 to +2.9 dB | 0.82-0.90, waveform 0.12-0.44 | 1.2-1.5 s (6 s cold) |
| YuE2 (m02 t01), the song made again at its seed | the round trip only: 0.994 | as the take | -1.5 to +0.1 dB | 0.91-0.95: the same notes, sung again | 4-9 s (the song's tokens made again) |
| YuE2, a new song seed | refused: "YuE2 latent duration must match the seconds output of YuE2 Text Encode" | | | | |

- **(a) Kept bars.** Outside the mask the sampler returns the encoded take untouched; what
  differs is the VAE round trip (correlation 0.975 with the ACE score take, 0.995 with the
  songs). So the take's own samples are spliced back outside the span, and the kept bars are
  the take's exactly.
- **(b) Tempo and beat.** With its own codes ACE-Step keeps the take's grid in every span
  (every beat within 3 ms of where the take had it). New codes keep it over 2 bars but lose it
  over 4 on two seeds of three (a new figure the masked sampler doesn't pull back onto the
  beat). With a timbre reference there are no codes (the reference's own hints stand in) and
  the span stayed near the take's tempo.
- **(c) Seams.** Spliced at the bar lines with 20 ms crossfades, the level step across a seam
  is within about 3 dB of the take's own step at that bar line (a downbeat is a step up in
  any take), and the sharpest sample step near the seam stays below the sharpest in the
  surrounding second: no click. New codes leave the span 5-9 dB quieter or louder at its far
  end on most seeds; with its codes it doesn't.
- **(d) Change.** With its own codes the span is a new performance of the same music (the
  spectra 0.92-0.95 alike against the round trip's 0.97, the waveform 0.65-0.72); new codes, or
  a timbre reference, make new music there (0.76-0.91). Denoise below 1 changes it less, not
  more safely; 1.0 it is.
- **(e) Fast**: 1.3 s a repaint warm on ACE-Step Turbo; YuE2 4-9 s, its song made again first.
- **YuE2 can't repaint.** Its conditioning is its own language model's song: the latent must
  be as long as that song, so a new seed (a new song, another length) is refused, and the same
  seed sings the same notes again (only its sound changes). Stable Audio 3 takes no codes or
  sections and wasn't tried. So **ACE-Step repaints, with the take's codes by default** (the
  grid held), new codes on request (more change, the beat checked on each take), YuE2 and
  Stable Audio 3 don't offer it.

## Open questions

- Ducking defaults (-9 / -6 dB) are guesses: tune on a real episode in phase 1.
- How well ACE-Step holds a tempo and a section's length: measure in phase 2 before the refit
  limits are fixed.
- Whether a cue should render longer than its span by default (more room to fit) or exact.
- Whether energy words (sparse ... full orchestra fortissimo) move ACE-Step's loudness and
  density reliably: measure with the shape check before building much window around them.
- LTX-2.3 Foley on 2.5: if it holds, no 2.3 files are needed.
