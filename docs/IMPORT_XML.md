# Importing an edit (FCP7 XML)

An edit cut somewhere else (Premiere Pro, DaVinci Resolve, Final Cut 7, or seriesmith's own
**Premiere / Resolve XML** export) comes into seriesmith as a **new show and episode**: a
shot per clip, its footage the shot's take, the cut's trims, dissolves and fades kept, and
the rest of the sound in the episode's mix. From there it is an episode like any other: write
what happens in a shot and render it again on a model, add music cues, effects and
ambience, re-cut it, master it.

## Exporting the XML

- **Premiere Pro**: select the sequence, **File › Export › Final Cut Pro XML…**
- **DaVinci Resolve**: **File › Export › Timeline…**, format **FCP 7 XML V5 Files**
- **Final Cut Pro 7**: **File › Export › XML…** (version 4 or 5)
- **seriesmith**: Export › **Premiere / Resolve XML** (or `seriesmith assemble <episode> --xml`)

The XML names its media where it was when you exported it. Import it on the machine that
holds that media; a file that moved is looked for beside the XML too.

## Importing it

In the editor: **Project folders**, pick the folder your shows live in, **New series/project…**,
then **From an edit (FCP7 XML)…** at the top of the wizard. Pick the `.xml` (or give its path
on the machine seriesmith runs on), choose how its footage comes in (below), and name the
show (its sequence's name by default). The wizard reads the edit as you change these and
says what it will make: the shots, the takes, the sounds, and anything that doesn't come
through. **Import** makes the show, builds it and opens it; the footage is made on the queue
(**Jobs**: a job per source file), each shot's take appearing as it's done.

From a terminal:

```
seriesmith import-xml cut.xml --into C:\Shows --dry-run          # what it would make
seriesmith import-xml cut.xml --into C:\Shows --name "The Pier"   # handles, 1 s
seriesmith import-xml cut.xml --into C:\Shows --media proxies
```

## How the footage comes in

| | What a shot's take is | Plays in the editor | Disk |
|---|---|---|---|
| **Used part + handles** (the default, `--media handles`) | the part of the source the clip uses, plus `--handles` seconds (1 by default) either side as far as the file goes, H.264 at master quality, frame-accurate | always | the used parts only |
| **Reference in place** (`--media reference`) | the source file whole, as it is: hard-linked where the drive allows (no second copy), else copied; never re-encoded | only when the source is H.264 in an mp4: the import says which clips won't | nothing more where it links |
| **Reference in place + playable proxies** (`--media proxies`) | as Reference in place; a source the editor can't play gets an H.264 proxy (review quality, at most 1920 wide, every frame of the original), made once per source in `<episode>\_proxies\`, and the take plays it | always | one proxy per source the editor can't play |

Every way, the cut's trims make it play exactly the XML's in to out, and the frames around
that are there to trim back into.

**Proxies**: the take the editor plays is the proxy; the original stays where it is and is
recorded as the take's **master**. Export, Master and the XML export cut from the original
(re-encoded at master quality), so nothing is lost to the proxy. If the original moves or
changes, they say so and cut from the proxy. A source is proxied once, however many clips use
it, and running its job again (Retry in Jobs) keeps the proxy while the source is unchanged.
An upscale of a proxied take works from the proxy.

## What becomes what

- **The sequence**: its frame rate (23.976 for 24 NTSC) and size are the series'; its name is
  the show's (the folder is made from it) unless you name one. The episode is `ep01`.
- **Clips on V1** are the shots, `sh010`, `sh020`, … (when every clip is named after a shot
  id, as seriesmith's own export names them, those ids). Each shot's length (`dur:`) is its
  length on the timeline; its action line is the clip's name, a placeholder until you say what
  happens in it, with the source file and its in and out in a comment under it.
- **Clips on V2 and above** aren't imported (the picture is V1's); each is listed.
- **A gap** on V1, a generator there (black video, a title, a colour matte) or a disabled clip
  becomes a shot of black of that length, so everything after it stays in place.
- **Transitions**: a dissolve between two clips is the second clip's dissolve, its overlap
  taken from the clips' own frames; a Dip to Black a fade out and a fade in; one at a clip's
  head or tail with nothing beside it (or a fade from or to black) a fade in or out.
- **A clip's own sound** (an audio clip linked to it, of the same file) is the take's sound; a
  level on it is the clip's gain, a disabled one plays silent. An audio clip of another file
  starting where the clip does on A1 or A2 (a voice stem, synced sound) is the shot's sound
  from that file. A clip with no sound in the XML plays silent.
- **Every other audio clip** is an item in the episode's mix, its file copied into
  `audio\`: anchored to the shot playing where it starts and ends, its offset into the file,
  its level (Audio Levels, the keyframes as points), its fades, muted when disabled. Its track
  is chosen by what its track, file and folder are called: `sfx`, `fx`, `foley` effects;
  `amb`, `room`, `bed`, `atmos` ambience; `dialogue`, `dx`, `vo`, `adr` dialogue; anything
  else music. A second track of a kind becomes a track of its own (Music 2). The XML's levels
  are the mix as it was made, so the imported tracks' faders sit at 0 dB and they don't duck
  under the dialogue (turn that back on in the mixer).
- **Markers**: one whose comment is `hit` (as seriesmith exports its hits) is a hit of the
  mix; every other marker starts a sequence at the shot playing there.
- **The model**: the series renders on **Hold** (seriesmith's own: no model, any size and
  length), so its shots build whatever their size and length, and each shot's first keyframe
  is its first frame as the cut plays it (`refs\shots\<shot>\first.png`). To make a shot
  again, say what happens in it and pick its model (the shot form, or the series' model in
  Series settings); a model that starts from a picture starts from that frame.

## What doesn't come through

Effects on clips (colour, scale and position, speed changes, keyed titles), nested sequences
(a clip that is a sequence has no take), clips above V1, audio pan, and a slipped sync
between a clip's picture and its own sound. The import's notes list each one it met. From
seriesmith's own export, the ambience beds and a shot's effects come back as plain items on
their tracks, voices-only as each shot's voice stem as its sound, and the ducking is off.

## Where it lands

```
<show>\ep01\
  series.json, ep01.md        the series config and script, as written
  cut.json, mix.json          the cut (both passes) and the mix
  audio\                      the mix's files and any shot's own sound file
  renders\<shot>\             each shot's take t01
  refs\shots\<shot>\first.png each shot's first keyframe
  _proxies\                   the proxies (Reference in place + proxies)
  _import\                    the XML as imported, and what its jobs make
```
