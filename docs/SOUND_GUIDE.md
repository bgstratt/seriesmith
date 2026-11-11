# The episode's sound

Everything you hear in an episode besides the picture, made and mixed in seriesmith: the
dialogue, a bed of room tone for each place, the shots' effects, and a score written to the
cut. This page is the order of work and what each part does. Scoring itself, cue by cue, is
in [SCORING.md](SCORING.md); every button is in [EDITOR.md](EDITOR.md) ("Sound: the
episode's mix"), and every command in [COMMANDS.md](COMMANDS.md).

## The idea in one paragraph

A model like H3 renders each shot with its own sound: the lines, footsteps, a room tone and
often a bit of music, different in every take. Cut together, that sound changes at every
cut. So the episode's sound is rebuilt on four tracks under the picture. **Dialogue** keeps
only the voices from each take (the rest split off). **Ambience** lays one bed of room tone
under every shot of a place, so the room carries across its cuts. **Effects** adds a shot's
sync sound, made from its frames, where it needs one. **Music** is the score, drafted from
the script's story beats and rendered cue by cue. The mix sets the levels and dips the music
and ambience under the lines, and the export writes the finished sound, its stems and an M&E.

## Before you start

- **Lock the picture, mostly.** Everything on the sound tracks is anchored to a shot and a
  frame of its take, so it follows trims and reorders. But a cue is written to the cut's
  timing, and re-cutting a scene means making its cues again.
- **Every shot needs a take in the pass you're working on.** A cue, a bed and a shot's
  effects are all timed to the rendered shots. The proxy and final passes each have their own
  mix: score the pass you'll deliver, or the proxy first and the final once it's rendered.
- **Install what you'll use.** The editor's **Features** window lists each part under
  **Sound** and downloads it: the voice stems (Hybrid Demucs, seriesmith's own node), the
  ambience model (MMAudio, the default), the effects models (H3 FL2VA, the default) and the
  music models (Stable Audio 3, the default, and Magenta RealTime 2 for score; YuE2, the
  default, and MiniMax Music 3 for songs). What each needs is in
  [FULL_SETUP.md](FULL_SETUP.md), "Sound".
- **Open the sound lanes.** **Sound** in the timeline's header unfolds a hits lane and the
  four tracks under the clips: Dialogue, Effects, Ambience, Music. **Scoring**, beside it,
  opens the spotting sheet.

## The order of work

1. **Voices only**: the dialogue track keeps each take's voices, nothing else.
2. **Ambience beds**: a bed for each place, laid under its shots.
3. **Effects**: for the shots whose own sound is gone or wrong.
4. **The score**: a first pass drafted from the script, then each cue shaped and rendered.
5. **The mix**: levels, ducking, a place where the music should carry over the lines.
6. **Export**: the episode with its mix, the stems and the M&E.

Steps 1 to 3 change what's under the music, so do them first: the score is judged against
the sound it will sit on.

## 1. The dialogue: voices only

Each take's own sound has its lines and everything else the model added, its music and room
tone. **Voices only** splits each take into its voices and the rest (Hybrid Demucs, on your
ComfyUI) and plays only the voices, so the beds, effects and score aren't fighting a different
bit of music at every cut.

- **Turn it on**: right-click the Dialogue lane ▸ **Voices only**, or its head's **⋮**, or the
  Refs tab's **Dialogue** section.
- **Make voice stems** beside it splits every take the cut plays: a job a take in Jobs, about
  a second each once loaded. It says how many are split ("8/10 shots split"). A take rendered
  again is split again when you ask.
- A shot whose stem isn't there yet **plays its whole sound**, never silence, with a warning
  mark on the lane. A shot the script gives **no lines** is silent on the Dialogue track (its
  stem would only hold the model's ad-libs and murmurs).
- A shot can go its own way: its clip's **Sound** menu ▸ **Keep its whole sound** (a take
  whose own music you want), **Voices only** (a gasp the model gave a shot with no lines), or
  **Split its voice again**.
- Command line: `seriesmith voices <episode>` (`--proxy`, `--shots`, `--redo`, `--list`).

With the takes' own room tone and effects gone, the next two steps put them back, once and
consistently.

## 2. Ambience: a bed for each place

A place's **ambience bed** is its room tone or air (a refrigerator's hum and a neon sign's
buzz, rain on a window, wind and gulls) made once from words and looped under every shot set
there, crossfaded into the next place's at the cut. It's what makes a room sound like one
room across its cuts.

- **Say what's heard there.** A location's `ambience` in the series config, written as a
  sound designer would: the steady bed first, then a few sparse events, never music or voices
  ([AUTHORING.md](AUTHORING.md), "What a place sounds like"). Or write it in the editor (below).
- **Make it**: the Refs tab's **Ambience** section lists each place, its words, how many shots
  it plays under and whether its bed is made: open a row to **Make it**, hear the takes and
  pick one. **+ Bed** on the Ambience head lists the places the cut is at, takes new words
  (written into the series config) and makes the bed. Or right-click the Ambience lane over a
  shot ▸ **Make <place>'s ambience bed**.
- **On the lane** the beds are dashed blocks named for their place, laid from the cut (they
  follow trims and can't be dragged). Right-click one for its **level** or **Mute this place**.
  An angle or a relit version of a place plays its place's bed.
- A sound file dropped on the Ambience lane plays over the beds (a walla track, a passing
  train).

## 3. Effects: a shot's sync sound

**Effects** are a shot's footsteps, the door, the cups on the table, made from the frames of the
take the cut plays. Many takes already have good effects in their own sound; with voices only
on, those are gone too, so make effects for the shots where you miss them.

- **Give the shot a `sound:` line** first ("cup taps on formica, hands clapping"): the effects
  are made from it, else from the action, and an action written for the picture can mislead
  ("…looks up, about to sing" gets a voice).
- **Make them**: a clip's **Sound ▸ Make effects** (several clips selected: one take each), or
  **+ Effects** on the Effects head (the cut's shots by sequence, ticked where there are none),
  on MiniMax H3 (the default, about 10 s a shot) or, under **Make effects on…**, LTX-2.3 Foley
  or HunyuanVideo-Foley XL (a minute or two). Each new take is picked into the mix as it lands.
- **On the lane** a shot's effects sit at its clip. Drag an edge to trim them (a voice creeping
  in at the end), drag the corner squares for fades, double-click the line for a volume point;
  right-click for its level, its other takes (▶ to hear one, **Pick**) and **Make again**.
- When the cut plays another take of the shot, its effects are **stale**: dashed, left out of
  the mix until they're made again, or **Keep as it is**.
- Command line: `seriesmith fx <episode> --shots sh010,sh020` (`--target`, `--takes`, `--pick`,
  `--list`).

## 4. The score: from the script to cues

The music is made of **cues**: pieces of score over a stretch of shots, each rendered as
several takes, measured and ranked, one picked into the mix. You can place every cue by hand
([SCORING.md](SCORING.md) step by step), but the quickest start is a **first pass drafted from
the script**.

### Mark the story's beats

The draft reads the script's story structure, written as comments (they change nothing the
video models see, so nothing renders again):

```
// structure: Pixar Story Spine

// beat: Once upon a time…
# sq01  silk_road
## sh010
...
// beat: Until one day…
# sq02  portal_ruins
```

- `// structure:` names one of the structures in [STORY_STRUCTURES.md](STORY_STRUCTURES.md)
  (Pixar Story Spine, Sitcom, Fable, Episodic Drama, the Hero's Journey...), and `// beat:`
  sits above the first shot of each beat, with the beat's name as that structure writes it.
  The script-writing skill writes them for a new script.
- An older script without them: the Draft dialog says so, and its **Structure** list lays
  the beats out for you (each where it falls in a story, on the nearest sequence) and can write
  them into the script, to move by hand where a beat really starts. Or set a shot's **Beat**
  in its form (**More**).
- `// theme: show, tender` above a shot puts a theme on a moment the beats can't find (the
  heart of a comedy, a look that changes the scene): held low to the end of its scene, or a
  sting when the words say `sting`. `// flashback` above a sequence makes its music an echo,
  thinner and further away.

### Draft

**Scoring** ▸ the Spotting tab ▸ **Draft…** (or `seriesmith score-draft <episode>`, `--write`
to write it). It shows the cues it would make, and writes nothing until you press **Write**.

- Each structure has a **Music table**: each beat scored, held low under the lines, a short
  sting, or played dry, with its mood, its energy and where the music turns, peaks or drops.
- **Beats in a row with music are one cue**, a section each, so the score changes with the story
  rather than stopping at every beat. A story told straight through (a bedtime story on the
  Story Spine) is one cue across the episode; a sitcom plays its scenes dry with short stings and
  a bumper of the show's theme at each change of place.
- A show whose episodes share a shape of their own describes it once in the series config,
  `sound.format` ([AUTHORING.md](AUTHORING.md)): its beats' names and what each gets, and
  `gaps` for a talky beat (music only where no one speaks).
- **Write** adds the draft cues (`d01`, `d02`...) and their hits, and turns the Dialogue track
  to voices only. Nothing is rendered yet. A cue of your own is never touched; drafting again
  replaces only the draft cues you haven't rendered (or, ticked, the rendered ones too).

### Shape, render and pick

Open a cue (double-click it on the spotting map; the cue in the window's head picks another):
the **Score** tab shows its sections, hits, arc and takes on one bar grid. Adjust the words and
the energy, **Render** its takes (eight, a minute or so on a 5090 for Stable Audio 3), listen
under the picture (▶ beside a take on the spotting sheet) and **Pick** one: it lands on the
Music track, its level shaped to the arc. [SCORING.md](SCORING.md) has every step, fixing part
of a take and the levels.

### Themes across a show

A **theme** is a tune that comes back: the show's own, a character's, the thread of a serial.
Here a theme is a **picked take**: render a cue with no theme, pick the take you like, and on its
row press **★ Series theme**: a name, its role (`show`, `story`, `runner`), whose it is (a
character's theme) and what it is in words. It's written into every episode's series config.

- Any cue's **Theme** can then be that series theme: Stable Audio 3 renders the cue from the
  theme's take (at a strength, 0.86 by default), so the tune recurs in the cue's own
  instruments, fitted to its tempo and bars.
- With SheetSage2 installed, each take gets a **melody score** (how much of the theme it kept);
  takes that lost it rank last.
- The draft uses them: the Music tables name a beat's theme by role, `story` (the episode's own,
  made by its first scored cue), `show` and `runner`. A character's theme (**whose** set) is the
  episode's own whenever that character leads it, carried from episode to episode. Make the
  themes in the first episode, then draft the others with them.

### Hits

A **hit** is a moment the music must answer: a door slams (accent), the music peaks here
(arrive), cuts out (drop) or changes (turn). The draft places turns at each beat; add your own
on the hits lane (double-click), at Play all's playhead (**+ Hit at playhead** on the spotting sheet), or in a shot's form
(**More** ▸ **Hit**, on its first frame). Drag a hit on the hits lane or the spotting map to
move it. A cue's tempo is fitted so its hits fall on bar lines.

## 5. The mix

- **Levels**: each lane's fader (dB), **M** mute and **S** solo. Music starts at -12 dB, so the
  score sits under the lines. The series config's `sound.tracks` sets a show's defaults.
- **Level the lines** (the Dialogue lane's menu, beside Voices only): each speaking shot's lines
  brought to the same level as the others, the middle of them, at most 9 dB up or down, so a
  quiet take and a loud one sit together. Shots with no lines keep their level. The export's log
  says what moved ("sh190 +3.2"). Off until you tick it.
- **Ducking**: music and ambience dip under speech (music -9 dB, ambience -6 dB), worked out
  from the dialogue track, the same in Play all and the export.
- **Duck regions**: right-click a lane ▸ **Duck region here** for a stretch where the music
  carries the scene over the lines (**score forward**), or dips deeper under busy dialogue.
- **Items**: drop any sound file on a lane, drag it, trim it, fade it, shape it with volume
  points; **Plays in the mix** unticked keeps it but silent. More tracks of your own (a song
  under the score, a walla track) from a lane head's **⋮**.
- **Play all** plays the mix as the export will. Every change is saved at once and undone with
  Ctrl+Z.

## 6. Export

**Export ▾ ▸ Export** (or `seriesmith assemble`) renders the mix into the episode: every track at its level and ducking, brought to
the loudness target (the series config's `sound.loudness`, else -16 LUFS and -1 dBTP), with the
**stems** beside it (`<cut>_stems/`: one per track, `me` for music and effects without the
dialogue, and `mix`), a loudness report, and the lines as subtitles (`<cut>.srt` and `<cut>.vtt`,
see [FINISHING.md](FINISHING.md), "Subtitles"). **Export ▾ ▸ Premiere / Resolve XML** lays the same
on separate tracks for an editor to finish. See [COMMANDS.md](COMMANDS.md), "assemble", and
[FINISHING.md](FINISHING.md) for the loudness.

## From the command line

| Command | What it does |
|---|---|
| `seriesmith voices <episode>` | The cut's takes split into voice stems, for voices only |
| `seriesmith fx <episode> --shots sh010,...` | A shot's effects made from its take's frames (`--pick` into the mix) |
| `seriesmith score-draft <episode>` | The first-pass score shown; `--write` writes it (`--structure "Pixar Story Spine" --mark` for a script with no beat lines) |
| `seriesmith assemble <episode>` | The episode with its mix, its stems and the loudness report |

Ambience beds and cue takes are made from the editor (the Refs tab, the cue window), or by an
LLM over `seriesmith mcp`, whose `score_draft` tool drafts the score.

## Quick reference

| You want | Do |
|---|---|
| The takes' own music gone | Dialogue lane ▸ **Voices only**, then **Make voice stems** |
| A room that sounds the same across its cuts | the place's `ambience` words, then its bed (Refs tab ▸ Ambience) |
| Footsteps where there are none | the shot's `sound:` line, then **Sound ▸ Make effects** |
| A score to start from | `// structure:` and `// beat:` lines, then Spotting ▸ **Draft…** |
| A script with no beat lines | **Draft…** ▸ **Structure**, written into the script |
| A tune that comes back every episode | a take's **★ Series theme**, then a cue's **Theme** |
| A character's own theme | **★ Series theme** with **whose** set to them |
| The music to answer a moment | a hit (the hits lane, the spotting map, or the shot's form) |
| The music over the lines, not under | a duck region, **score forward** |
| The music only where nobody talks | a show's format with `gaps` for that beat |
| Stems and an M&E | **Export ▾ ▸ Export**: `<cut>_stems/` |
