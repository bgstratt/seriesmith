# Performance: lines read again, and sound that runs across a cut

The design record and checklist of two pieces of work that make the acting better after the
picture is finished:

1. **A line read again on its own timing** (re-perform): a shot's line given a new reading
   (more feeling, other stresses, a breath) without rendering the shot again. The new reading
   is fitted word by word onto the timing the take's mouth already has, so the lips stay in sync.
2. **J and L cuts** (split edits): a shot's sound starting before its picture, under the shot
   before it (J), or running on past its picture, under the shot after it (L).

Both are about rhythm, and neither renders video. The third way to change a performance, a dub
pass (the shot rendered again against new sound, `retention: fully_copy`), is already there
(RECORDED_DIALOGUE.md) and is what a line that needs new timing inside it gets. Repainting the
mouth alone, by a lip-sync model on the finished frames, is not part of this: the mouth it
paints doesn't belong to the face it's on.

## Why

A clean shot is a solved problem: the checks, reseeding and a first-last model get there. The
performance isn't. The picture's movement is usually right, but a line's reading comes from
the video model in the same render as the picture, and it is often flat, rushed or stressed
on the wrong word. The parenthetical in the script asks for it; the model doesn't always give
it. Rendering the shot again for a reading risks the picture that's already right.

Most of what makes a reading good is pitch, colour, breath and emphasis, none of which changes
when the words start. So a new reading laid on the old timing keeps the picture and the sync,
and changes most of what was wrong.

## 1. A line read again (re-perform)

### What the person does

Watches the cut and marks the lines that could be better: an issue on the shot (the Issues
panel, `seriesmith issues <ep> --add <shot> <note>`) whose note names the line and what the
reading should be ("Thorne's 'every year' is flat: bitter, slower on 'alone'"), or the shot's
flag. Then asks for readings of those lines, listens to them beside the take's own, and picks
one, or keeps the take's.

### What a reading is made from

- **The words**: the line as the script has it.
- **The direction**: the script's parenthetical, the issue's note when there is one, and the
  character's `voice` line.
- **The voice**: the character's, as the show already has it. In a show whose voices the video
  model made (`audio.mode: generate`), that's the voice in the takes, not a sample anyone
  recorded. The sample is cut from the character's own lines in the cut's takes: from their
  voice stems (voices.py), a stretch of 5-20 s where only they speak, cut between words
  (audiocut), chosen once per character and kept (`<show>/refs/voices/<who>_perform.wav`,
  so every reading of that character clones the same thing). A `voice_sample` in the series
  config wins.
- **The timing**: the take's own reading of the line. Its voice stem, heard by Whisper with word
  timings (align's model, faster-whisper), matched to the script's words: when each word starts
  and ends, and the pauses between them. This is the guide every new reading is fitted to.

### Making the readings

Several readings a line (3-4 by default), seeds from the line's id (`stable_seed`), on
seriesmith's queue as jobs of their own (kind `perform`), from one of these sources, by
whichever the live test says reads best:

1. **The video model voicing its own take.** H3 given the take's frames and asked for its sound,
   as `h3_foley` makes a shot's effects (MiniMaxH3AddGuide with the frames, only the sound
   decoded), but asked for the line with its direction, the character's voice as a voice
   reference (H3 Ref2VA's `voice_refs`). It sees the mouth it's voicing, so the reading should
   land in sync without stretching; the fit still checks it. LTX-2.5 the same way (a video
   model that makes its sound with its picture, given the frames). The risk is what H3 Foley
   did: music in the sound, so the prompt's music is `N/A` and a take with music is set aside.
2. **A voice-clone model on this machine**, speaking the words with the direction, fitted
   afterwards: Fish Audio Drama 3 (`drama3`), Qwen3-TTS (`qwen3_tts`), LTX-2.5's voice
   continuation (`ltx2_voice`). Not installed, worth a target each if these fall short:
   IndexTTS2 (emotion, and the length of the speech asked for, which suits fitting), CosyVoice
   3 (direction in words), Chatterbox (a strength for the emotion).
3. **A hosted voice model**, paid, so only when asked: ElevenLabs through ComfyUI's partner
   nodes (`eleven_v3` text to speech, which reads bracketed cues such as [whispers] and
   [sighs]; Instant Voice Clone), Fish Audio's hosted Drama 3 (`fishaudio_drama3`).
4. **The person's own reading**, converted to the character's voice: they record the line, and
   speech to speech (ElevenLabs Speech to Speech, paid; a local voice conversion model if one is
   added) gives it the character's voice with their timing and feeling. Fitted as any other.

How each model takes direction (H3's prompt, Drama 3's bracketed cues, Qwen3's instruct, which
its clone mode may not read, ElevenLabs' tags) is the first thing to try live, before the rest is
built.

### Fitting a reading to the take's timing

Each reading is heard by Whisper the same way, its words matched to the guide's one by one. Each
word's stretch of sound is then stretched or squeezed, pitch kept, so it starts and ends where the
guide's word does; a pause in the reading is fitted to the guide's pause (silence cut or added,
breaths kept). A reading that heard a word wrong, dropped one or added one is set aside.

How far a reading had to bend says whether the fit can be heard: the **stretch** (the furthest
any word went, and the mean). Under about ±15% it can't be heard; past about ±30% it's dropped.
A **sync score** says whether it sits on the mouth: the fitted reading's loudness envelope
against the take's voice stem's, syllable for syllable (the correlation of the two over the
line). The readings are ranked by the two together, and the person hears them in that order.

### Laying it in

Only the voice changes. The take's sound is its voice stem and the rest (effects, room tone,
the walla the model made): the rest stays, and the fitted reading goes in at the voice stem's
level (its loudness over the line matched), so the mix, the ducking, the levelling (LEVELLING.md)
and the export hear it as they heard the take's own voice. A reading is a take of the line:

    <ep>/audio/perform/<shot>.<n>_t<take>.wav     a fitted reading (the raw one beside it)
    <ep>/audio/perform/<shot>.<n>_t<take>.json    words, direction, model, seed, stretch, sync score
    <ep>/audio/perform/perform.json               which line plays which reading

A picked reading plays wherever the take's voice does: assemble, Play all, the FCP7 XML, the
stems. A reading is **stale** when the take under it changes (another take picked, re-rendered)
or the line's words do, and is never played without saying so: the take's own voice plays.

### In the editor

The Sound tab gets a section per line read again, as cues and effects have: the take's own
reading first, each new one under it with its stretch and sync score, a play button for each
against the picture, and a pick. The Issues panel's note opens that section. Edit shot shows
which of its lines plays a reading.

## 2. J and L cuts

### What the person does

On the timeline, drags a clip's sound edge past its picture's: its head earlier (J: the sound
starts under the shot before), or its tail later (L: the sound runs under the shot after).
Or types the frames in the clip's cut entry. Common uses: the next speaker's line starts under
the end of the listener's shot; a reaction is seen while the line that caused it finishes.

### The cut entry

Two fields on a cut entry, in frames: `audio_lead` (J) and `audio_lag` (L). The picture's in and
out don't change; the clip's sound starts `audio_lead` frames before the picture and ends
`audio_lag` frames after it.

**Where the extra sound comes from.** The clip's own take, outside the frames the cut shows: a
lead plays the frames before `trim_in`, a lag those after `trim_out`. So a split edit needs
handles. A take with no frames to spare (no trim on that end) can't be split there, and the
editor says how much it can (the trim's length). A clip whose sound comes from elsewhere
(`audio`: a file, another take) uses that file's sound either side, as far as it goes.

**What happens to the neighbour's sound under the overlap.** It's replaced: the neighbour's sound
fades out over a few frames as the split sound fades in, and stays out across the overlap. The
voice stems make a choice possible later (`overlap: "under"`: the neighbour's effects and room
tone kept under the split voice), but replaced is what an editor's split edit does by default.

### What has to follow

Everything that lays a clip's sound at its picture lays it at its sound's edges instead:

- **assemble**: the audio track is laid from each clip's sound span, overlaps crossfaded; the
  picture unchanged.
- **the mix** (mix.py): the dialogue track's clips at their sound spans (`shot_origins` gets the
  sound's edges beside the picture's), the ducking's speech curve and LEVELLING's lines with them.
  An anchor (`{shot, frame}`) still means the picture's frame.
- **Play all**: the clip's sound starts under the clip before (its stem, or its own `<video>`'s
  sound played ahead of its picture).
- **The FCP7 XML** (nle_xml): a split edit is native there: the clip's audio item's in and out
  differ from its video item's.
- **Subtitles**: a line's subtitle follows its sound.
- **The voices-only stems** and **checks**: follow the sound spans.

### In the editor

The timeline draws each clip's sound as a band under its picture, its edges draggable past the
picture's, as far as the take's handles go. The cut entry's popover has the two fields. A dissolve
and a split edit can be on the same cut.

## Checklist

### Re-perform

- [ ] Live test first, on a few lines of this show marked as needing it: H3 voicing the take
      from its frames (with the voice reference; sync and music checked), Drama 3 and Qwen3-TTS
      cloned from a sample cut from the character's takes; with the person's go-ahead, ElevenLabs
      v3 and Speech to Speech. Does each read the direction, how close is the voice to the take's,
      and how far does each have to be stretched to fit?
- [ ] The guide: a take's line heard with word timings on its voice stem, matched to the script.
- [ ] The character's sample: cut from their voice stems, chosen once, kept.
- [ ] The fit: per-word stretch (pitch kept) and pauses; the stretch and sync scores; the limits.
- [ ] Readings as takes: files, records, stale, picked (`perform.json`).
- [ ] Laying in: the take's sound less its voice, plus the reading at the voice's level; assemble,
      Play all, the XML, the stems, the levelling.
- [ ] The queue's `perform` jobs; the routes (`GET /seriesmith/perform`, `POST .../perform/render`,
      `POST .../perform/pick`) and their API.md entries.
- [ ] The Sound tab's section; the Issues note's link; Edit shot's mark.
- [ ] Tests; the user guide (SOUND_GUIDE.md: a section on reading a line again).

### J and L cuts

- [ ] `audio_lead` / `audio_lag` on a cut entry: checked against the take's handles; PUT /cut and API.md.
- [ ] assemble lays the sound spans with crossfades.
- [ ] mix.py: origins with sound edges; the ducking, levels and voices only.
- [ ] Play all.
- [ ] nle_xml: split audio items; import-xml reads them back.
- [ ] Subtitles follow the sound.
- [ ] The timeline's sound band and its drag; the popover's fields.
- [ ] Tests (golden outputs unchanged for a cut with no split edits); EDITOR.md, AUTHORING or
      the cut's docs.

## Open questions

- Does either local model read a direction while cloning, and is it enough? (The live test.)
- Is Whisper's word timing on a video model's voice stem good enough to fit to, on fast lines and
  lines with two people speaking over each other? A line too close to another speaker may need
  the guide from the script's pacing instead.
- A reading that's better but can't fit (a pause it needs, a word longer): it's the dub pass's,
  and the Sound tab should say so and offer it.
