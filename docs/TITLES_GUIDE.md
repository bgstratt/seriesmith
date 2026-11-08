# The opening and the closing

A show opens and closes the same way every week: the theme, the series title, the episode's
name. seriesmith doesn't render those inside each episode. They are two clips made once, the
**intro** and the **outro**, and every master is wrapped in them, with the episode's title
written on by seriesmith. This guide covers how that works, where the clips go, and how to make
them: a montage of the season's best shots under the show's theme song.

## What a master does with them

A master (the editor's **Export ▾ › Master…**, or `seriesmith master`) is the intro, then the
episode, then the outro, as one file; with a [cold open](#a-cold-open), the cold open comes
first and the intro after it. **Export ▾ › Titles** does the same with the review cut, into
`<episode>\publish\`. Export and Play all never add the titles.

- **The intro and outro play as they are**, picture and sound. The theme song is the intro's own
  soundtrack, so put it in the clip.
- **The series title is in the clips.** seriesmith doesn't draw it: put it in the picture when you
  make the intro (a title card, or lettering added in your editor).
- **The episode's title is drawn on by seriesmith**, from the script's `= ep05  Title` line,
  under the series title: it fades in on the intro and fades in and out on the outro. Every
  episode gets the same font, size, colour and place, so the titles match from week to week.
- **The intro and outro are brought to the episode's loudness** (below).
- The cut's picture is copied, not re-encoded; only the two clips are encoded to match it.

## Where the clips go

By default, seriesmith looks for `_titles\INTRO.mp4` and `_titles\OUTRO.mp4` in the episode
folder, then in the show folder above it:

```
Porchlights\
  _titles\INTRO.mp4
  _titles\OUTRO.mp4
  ep01\
  ep02\
```

With no clips, a master is made without titles. To use other clips, name them in the series
config's `publish` block, relative to the episode folder:

```json
"publish": { "intro": "../_titles/INTRO.mp4", "outro": "../_titles/OUTRO.mp4" }
```

**Every episode has its own series config**, so the intro can change wherever you like:

- **One for the whole show**: the `_titles` files, and nothing in `publish`.
- **One per season**: `../_titles/S2_INTRO.mp4` in the series config of each season-two episode.
- **One for a single episode**: a clip in that episode's folder (`"intro": "intro.mp4"`), or
  `_titles\INTRO.mp4` inside the episode folder, which is found before the show's.

## The episode's title: where and how it's drawn

The `subtitle` object in `publish` sets how the episode's title looks. Every key is optional;
these are the defaults:

```json
"publish": {
  "subtitle": {
    "font": "C:/Windows/Fonts/segoescb.ttf",
    "size": 0.058,
    "y": 0.56,
    "color": "#F4E6D0", "glow": "#FFB45A@0.8", "glow_size": 0.008,
    "intro_in": [4.0, 5.0],
    "outro_in": [0.0, 1.0],
    "outro_out": [4.5, 5.5]
  }
}
```

- **`size` and `y`** are fractions of the frame's height: the text's height, and where its top
  sits (0.56 is just below the middle). Line `y` up with the space the series title leaves.
- **`intro_in`** is when, in seconds into the intro, the title starts to fade in and when it's
  fully on. Time it to the music: the moment the series title lands, or a beat after.
- **`outro_in` and `outro_out`** are its fade in and fade out on the outro.
- **`font`** is a font file. Choose one that's on every machine you master on, or keep a copy in
  the show folder and give its path.
- **The text** is the episode's title, from the script's `=` line: change it there.

## A cold open

A cold open is a scene before the titles: the episode starts, and the intro comes in after
it. Mark it in the script, under the sequence's `#` line (or on single shots):

```
# sq01  diner_night
cold_open: true
```

A master plays those shots, then the intro, then the rest of the episode. The timeline shows
an **▸ Opening** marker on the cold open's last clip, where the intro will go.

- **Set it from the timeline.** Right-click the clip the cold open should end on: **In the cut
  › Cold open ends here**. Every shot from the cut's first up to that one is marked in the
  script (a sequence's `#` line when all its shots are in it, else each shot's own line), and
  every other mark comes out. The old script is kept in the episode's `_history\` folder.
  **No cold open** takes them all out.
- **It follows the cut.** The cold open is the cut's first shots, one after another. When you
  move a clip so a marked shot plays after one that isn't, the timeline shows a red **Cold
  open** badge (hover it for which shots), the marker turns red, and a master refuses until
  you fix it: **Cold open ends here** on the right clip rewrites the marks to the cut as it is.
- **The intro goes in on a cut.** A dissolve from the cold open's last shot into the next is
  refused; take it out there.
- **Music across the break** is cut there, as the picture is. End the cold open's music on
  its last shot (a button on the cut is the classic way into the titles).
- **The break is read from the file being titled.** Every cut assemble writes (an export, a
  master) has its shot list beside it (`<cut>_shots.txt`), and the intro goes in where that
  list says the cold open's last shot ends, so a take a frame or two shorter than its record
  doesn't move it. Change the cold open after exporting, and export (or master) again.

## The intro's and outro's loudness

Every episode's mix is brought to one loudness (the series config's `sound.loudness`: -16
LUFS and a -1 dBTP ceiling unless you set it, FINISHING.md "The export's loudness"). When a
master puts the intro and outro on, each is measured the same way and moved by one gain to
that loudness, its peaks held under the same ceiling. A clip made outside seriesmith, at
whatever level it came, lands where the episode is. Nothing is compressed and nothing is
changed bar by bar: it's one gain, as the mix's.

A theme at the same loudness as dialogue can feel louder, being music all the way through. To
tuck it under, set how many LU under the episode it sits:

```json
"publish": { "loudness": { "under_lu": 1.5 } }
```

`"match": false` leaves the clips as they came. The master's log says what it did
(`intro sound: -21.3 LUFS, +5.3 dB to -16`).

## Making the intro: a montage as its own episode

An intro is easiest made as **an episode of its own** in the show (for example `intro` or
`s2intro`): a short cut you can score, preview, change and export like any other, without
touching the real episodes. Make a new one per season, or for any episode that needs its own.

1. **Make the episode.** **New episode…** in the show, with a short script: one sequence and
   a shot per moment of the montage. A shot's `dur:` is how long it holds; the action says what
   it is ("Dale on the porch at dusk").
2. **Fill the shots with takes you already have.** Every take is a video file in its episode's
   `renders` folder (`ep01\renders\sh040\sh040_t03.mp4`). Drag one onto a clip on the timeline
   and it becomes that shot's take. Drop one **between** two clips and the shot form opens there
   with its length filled in: write the action and **Save**. Nothing renders, so it costs
   nothing. Trim each clip on the timeline to the moment you want.
3. **Add the series title as a held picture.** Drop a title card (a png) between two clips: it
   becomes a shot on the **Hold** model, held still for as long as you drag it. A video model
   can't spell the show's name reliably, so the title is best as a picture you made.
4. **Silence the clips' own sound.** The takes keep their dialogue and effects. In the sound
   lanes under the timeline (**Sound**), mute the Dialogue track (**M**), so only the music
   plays.
5. **Score it.** **+ Cue** in the Refs tab's Music section, over the whole cut, as a **song**
   with the theme's lyrics, or as a score cue for an instrumental opening. Render its takes and
   pick one ([SCORING.md](SCORING.md)). ACE-Step and MiniMax Music fit their length to the cue.
   YuE2 writes a whole song, often two or three minutes, so it runs past the cue's end. The cue
   window shows the whole take, with the part past the out point hatched. Only the cut's length
   is heard.
6. **Export it.** **Export ▾ › Export** (or **Export 2x** for the upscales) writes the montage as
   one mp4 with its mix. Copy it to `_titles\INTRO.mp4`, or point the series config's `intro`
   at it.

Use **Export**, not **Master** or **Titles**, for the intro episode: those wrap a cut in the
show's intro and outro, so the intro would come out wrapped in the old one.

The outro is made the same way: a few shots under the theme's ending, with room left for the
episode's title to fade in and out.

## The song first, the picture after: a held picture

A montage is often cut to the music rather than the other way round. To get the song before
there's a cut:

1. **Make a scratch episode with a single shot on the Hold model** (`target: hold`), any picture,
   its `dur:` as long as the song should be (`dur: 60`). It renders in a moment, on this
   machine, so the episode has a cut of that length.
2. **Make a cue over it**, as a song, render takes and pick one. The cue window gives you the
   whole song, with its tempo, sections and lyrics.
3. **Lay the song under the real montage.** Each take is a wav in the scratch episode's
   `sound\<cue>\` folder. Import it onto the intro episode's Music lane and cut the shots to it.

This works for any music you want before there's picture, not only a theme. You can also make
the song in ComfyUI directly, with the same models, and import the file the same way.

## Changing it later

- **A new intro for a new season**: a new intro episode, a new file, and its path in that
  season's episodes' series configs. Masters made after the change use it.
- **A custom intro for one episode**: that episode's series config, or a `_titles` folder in
  its own folder.
- **Re-master to apply a change.** A master already made keeps the clips it was made with.
