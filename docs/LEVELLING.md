# Levelling in Play all

The design record and checklist of the lines levelled in Play all as the export levels them.
Started 2026-11-13.

## Why

The mix's **Level the lines** (mix.json `level.limit_db`, off by default, 9 when ticked) brings
each speaking clip's lines to the middle of their speech levels, at most the limit up or down
(`mix.level_dialogue`). Until now only the export did it: Play all played each clip at its own
level, so the cut you judged wasn't the cut you'd export.

## Design

- **What's measured:** what each clip plays for its lines: the take's own sound, its voice stem
  (voices only), or its own audio source (a dub, a replaced sound); nothing for a shot voices
  only leaves silent. The editor works that out as it plays it (`lib/levels.ts`, `levelClips`)
  and sends the files and the spans the cut plays (`POST /seriesmith/levels`).
- **When:** as each sound is made, so Play all finds it ready: a finished take's sound beside
  its checks (`runner._check_take`), a voice stem as it's split off (`runner`, the voice job),
  and when an episode opens, whatever its cut still lacks (`api.warm_levels`, once a minute an
  episode at most). Anything else is measured when it's asked for: about 70 ms a clip (LAST
  LIGHT's 27-clip cut, 0.35 s the first time, 0.02 s cached).
- **What's kept:** a file's speech readings (its power every 50 ms, from its start), not one
  number, keyed to the file (path, size, modified time) like the waveform peaks: a new take, stem
  or dub is a new file and is measured fresh, and a trim reads its span from the same readings.
- **The arithmetic is the export's** (`levels.py`): `level_of` and `gains_of` are what
  `mix.speech_level` and `mix.level_dialogue` call. The export measures the dialogue it lays
  (it has decoded it anyway); measured on LAST LIGHT's four speaking clips the two agree to
  0.001 dB (the readings are decoded stereo and averaged, as the export lays them: ffmpeg's own
  mono downmix read 3.01 dB over).
- **Turned down only:** a clip's own sound plays through its `<video>`, whose volume stops at
  1, so Play all moves every clip by its gain less the biggest boost (`playAllDb`): the lines'
  balance is the export's, the cut a few dB quieter. Voice stems and audio sources go through
  the mix engine (their entries' gain, `levelled`); the take's sound through the viewer's
  volume, with the dialogue fader and a region's dialogue dB. Routing the videos through Web
  Audio would let it boost instead; not done (it changes how every clip's sound plays).
- **Not levelled in Play all:** the recording (one file under the whole cut). A clip whose
  levels haven't come back plays at its own level.
- **The quiet floor:** left as it is (the user, 2026-11-13: speech all at one level). A line
  meant to be quiet is pulled up as far as the limit; a "don't level" mark per clip if that
  ever sounds wrong.

## Checklist

- [x] `levels.py`: readings, cache, `level_of`, `gains_of`, `clip_gains`, `warm`, `cut_sounds`;
      `mix.py` measures with them.
- [x] Measured as made: the take checks' thread, the voice job, an opened episode.
- [x] `POST /seriesmith/levels`.
- [x] The editor: `lib/levels.ts`, the store's `dialogueLevels`, `loadDialogueLevels`, the mix
      engine's stems and sources, the viewer's volume.
- [x] Tests: `tests/test_levels.py`, `web/test/levels.test.ts`.
- [x] Docs: SOUND_GUIDE, API.
- [x] Live (you, 2026-11-13): Play all on a cut with Level the lines on, a quiet clip next to a
      loud one: levelled, playback unaffected.
