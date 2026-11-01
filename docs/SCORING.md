# Scoring an episode

Music under a cut, made to fit it: where it goes, what it does, which take, how loud. This
guide walks through it in the order you'd do it, with Ballroom's ep03 "Choice" as the example.
The editor's buttons are listed in [EDITOR.md](EDITOR.md); the design and the measurements
behind it are in [SOUND.md](SOUND.md).

## The idea in one paragraph

The timeline decides **where** music goes; the **cue window** decides **what it does** there.
You mark the moments the music must answer (**hits**: a door slams, she says yes), make a **cue**
over a stretch of shots, say how it should rise and fall (its **sections** and **arc**), and
render **eight takes** of it. seriesmith fits the tempo so the hits fall on bar lines, measures
every take (does something happen at each hit? does its loudness follow the arc?) and ranks
them. You listen to the top two or three, **Pick** one, and it lands on the Music track with its
level already shaped to the arc. A cue stays tied to its shots: trim or move them and it moves
with them, and tells you when the change means it should be made again.

## Before you start

- **Lock the picture first, mostly.** A cue is written to the cut's timing. Small changes later
  are fine (it follows its shots, and tells you what moved); re-cutting a whole scene means
  re-rendering its cues.
- **Open the sound lanes**: **Sound** in the timeline's header. Under the clips you get a
  **Hits** lane and four tracks: Dialogue (each clip's own sound), Effects, Ambience, Music.
- **Decide where the music goes before what it is.** Watch the scene with the sound on and note
  where music would help and where silence is stronger. A comedy played straight, like ep03, wants
  the music to be sincere and to **stop dead** on the deflating beats, so the jokes land in
  silence.

## 1. Mark the hits

A **hit** is a moment the music must answer. Make one on the Hits lane: **double-click** where it
goes (or **+** for one at Play all's playhead), then right-click it to name it and set its kind:

| Kind | What the music does there | Use it for |
|---|---|---|
| **accent** | a sting or a downbeat lands on the frame | a door slam, a reveal shot, a punch |
| **arrive** | the music's peak arrives here; the section before builds to it | "I choose you", the kiss, the summit |
| **drop** | the music cuts out or thins | the deadpan "Oh.", silence before a reveal |
| **turn** | a change of key or mood; a new section starts | the scene turns, a new character enters |

**Must land** (on by default) means the tempo is fitted to put it exactly on its line; turn it
off for a hit that's nice to land but not essential. Two must-land hits a distance apart that no
nearby tempo divides into whole bars can't both land; the window tells you how far off each is.

A hit is anchored to a shot and a frame of its take, so trimming or moving the shot carries it.
Tip: an onscreen sound (a door, a footstep) is easiest to place by finding it in the take's own
sound on the Dialogue lane's waveform.

In ep03: *I choose you* (arrive, sh020), *Oh.* (drop, sh030), *the door shuts* (drop, sh100 frame
111, found from the take's sound), *What did I get chosen for?* (turn, sh130).

## 2. Make a cue

Select the shots the music plays over (Ctrl-click), right-click one and choose **Sound ▸ New
music cue**, or right-click the Music lane: **New cue…**. The cue window opens where takes play.

A cue is **Score** (instrumental, under the picture: the usual) or **Song** (sung; its sections
take lyrics). Set it top right in the inspector, with:

- **Label**: how it's listed ("1M3 The Proposal": reel 1, music cue 3, a name).
- **Model**: empty uses the kind's default: **Stable Audio 3** for score (it follows a rise and
  fall best), **ACE-Step** for a song (it sings) or when a cue must sit exactly on a bpm.
- **Tempo** in bpm (the fit may move it up to 8 % to land the hits; tick **fixed** to stop that),
  **Meter** (4/4, 3/4, 6/8, 7/8, or your own), **Key** (pick one, or leave it to the model),
  **Style** (the sound: "romantic period strings, solo horn, no percussion"), **Tail** (seconds
  it rings on past its out point), **Takes** per render.

In ep03: *1M1 The Selection* (sh010 to sh030, 72 bpm, D major), *1M2 The Departure* (sh080 to the
door, 96 bpm), *1M3 Chosen* (sh120 to the end, 66 bpm); no music under sh040-sh070 or sh110.

## 3. Shape it: the Score tab

The **Score** tab is the cue on one bar grid, top to bottom:

- **Picture**: the shots it plays over, with the pre-roll before (music that starts before its
  in point, so the first hit falls on a bar line) and the tail after.
- **Hits**: each one, the bar and beat it lands on, and how far off its line the fit leaves it
  (frames). A drop on the cue's out point is its **end**: the music is cut there, so it isn't
  fitted.
- **Bars**, then **Sections**: blocks of whole bars. Drag an edge to move it; click one to edit
  it in the inspector: its **name**, **words** (what plays: "strings enter, timpani roll"), and
  its energy **from** and **to** (1 sparse … 5 fortissimo). With no sections given, they're worked
  out from the hits (a build into an arrive, quiet after a drop).
- **Intensity**: the arc, the energy you want bar by bar (green). Drag its points, double-click
  to add one, right-click to remove one. A drawn arc **sets the sections' energies**, so what the
  model is told follows it.
- **Takes** (below; see step 5).

The inspector's foot shows **exactly what the model is told** for the cue or the selected
section, and the script's `music:` notes for the shots it covers, which go in too.

## 4. Optional: the Arc and Orchestration & takes tabs

**Arc** is the intensity lane large, for drawing the shape first:

- **Draw** freehand, edit **Points**, or **Smooth** them.
- **Presets**: slow burn, build and release, sting, pulse (and one from the script's notes).
- **Snap peaks to hits**: moves the arc's peaks onto arrive hits and its lows onto drops.
- **Sections from the arc**: cuts the sections where the arc turns, on bar lines (it asks first:
  it replaces your sections' names and words).
- The readout says what each section will be told, and flags detail the model can't follow: a
  dip inside one section won't happen (models follow sections, not bars) — **Split at bar N** keeps
  it.

**Orchestration & takes** is who plays when:

- **The grid**: a row per instrument family, a column per bar, each cell **off**, **under**,
  **present** or **lead**. The **step** brush (the one it opens on) moves a clicked cell up a
  level (off, under, present, lead, off) and **Shift**-click down; a drag gives every cell it
  crosses the first one's new level. The other brushes paint their level: click a cell, or drag
  across bars and rows. Keys **1-5** pick the brush (off, under, present, lead, step). Each
  section is told its families, loudest first ("solo horn present, strings under"). A family
  that changes inside a section is marked: the strongest level wins.
- **The rows** start as an orchestra's families; **+ Family** adds one, and a row's name can be
  any sound (celesta, fiddle, 808 bass, analog synth pad, gospel choir): it goes to the model as
  written, so name it as you'd describe it.
- **The takes** on the same bars, for fixing part of one (step 6).

## 5. Render and choose a take

**Render 8 takes** in the window's bar. Each lands in a few seconds (Stable Audio 3, about 2-4 s
a take on a 5090) and is measured as it does:

- **Its waveform**, from its first bar line.
- **The white dotted line**: its loudness per bar; the faint green under it is your arc. The
  closer they run, the better it follows the shape.
- **Hit chips**: at each hit, how far (frames) the nearest real event in the music is; orange
  past 2 frames, **—** when nothing happens there.
- **Shape** (0 is your arc exactly), the **tempo heard**, and a **stale** badge if the cut has
  moved since it was made (hover it for what moved).

The list is **ranked**: #1 best lands the must-land hits and follows the arc. It can't hear
whether the music is any good, so **listen to the top two or three** (▶) and **Pick** the one you
like. Picking puts it on the Music track from the cue's in point to its out point, with volume
points that pull its loudness toward the arc (a drop really drops). Render again for eight more
if none is right; the models vary a lot from take to take, which is why it makes eight.

What the measurements found (so you know what to expect): Stable Audio 3 put the climax where it
was asked six times in eight; ACE-Step followed sections far less reliably, so the arc is kept by
ranking and by the volume points, not by the words alone.

## 6. Fix part of a take

On **Orchestration & takes**, drag across bars on a take:

- **Comp bars a-b from…** another take: a new take, this one with those bars from the other,
  spliced on bar lines. It's measured and ranked like the rest.
- **Lower bars a-b with breakpoints…** (the take in the mix): volume points that dip those bars,
  shown on the timeline lane.
- **Repaint bars a-b** (re-render just those bars) isn't ready yet.

## 7. Levels

- **Faders**: one level per track. Music starts at **-12 dB**, under the lines. In ep03, at 0 dB
  the score was louder than the dialogue it sat under; at -12 it sat 5-10 dB under the lines and
  level with them on the swell.
- **Ducking**: music dips 9 dB (ambience 6) whenever someone speaks, automatically, in Play all
  and in the export alike.
- **Volume points**: the pink line on a block. Drag a point up or down, double-click to add,
  right-click to delete. Picking a take adds them (the fit to the arc); the block's menu clears
  them. A crescendo the music doesn't have can't be made with points; that's what the arc and the
  words are for. Points shape the level of what's there.
- **Mute / solo** a track on its lane's head.

The export (**Export**) mixes everything to -16 LUFS and writes the stems (dialogue, effects,
ambience, music, and music-and-effects) beside it; the **Premiere / Resolve XML** puts each
track on its own audio tracks with the levels.

## 8. When the cut changes

A cue follows its shots. If the cut moves under it, its takes say what changed (the span is
longer or shorter, a hit moved): a shorter span just ends on its out point, faded; a moved hit
or a longer span means rendering again (or measuring again, from the takes' measure, when the
tempo still fits).

## Quick reference

| You want | Do |
|---|---|
| Music to land on a moment | a hit, kind arrive (peak) or accent (sting) |
| Music to stop for a joke | a drop hit, and end the cue there |
| A swell | an arc rising to 5 into an arrive hit |
| A different feel bar by bar | Orchestration's grid, or sections with their own words |
| It's too loud | the Music fader (it starts at -12), or volume points |
| Most of a take is right | Comp the bad bars from another take |
| A song | Kind: Song; lyrics on its sections |
