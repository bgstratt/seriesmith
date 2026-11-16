# Musical numbers

*The design record and checklist of songs sung on screen in a spoken show (One Horse Open Sleigh, 2026-11).*

## Decided (2026-11-15): a number is an episode of its own

A song that characters sing on screen is cut song-first: the song is the recording, the sung lines are
dialogue, `align` gives each shot its window, and the singing shots lip-sync to theirs (MUSIC_VIDEO.md). That
machinery is whole-episode (one recording, align over every shot, `source_track` in the series config), and it
is all extra to a spoken episode. So a number stays an episode of its own beside its act (`ep01_song1`,
`ep02_reprise`), cut as a music video, and the act keeps a `// song:` slot where it goes.

Considered and set aside: a number as a block of the act's script (a Song cue's picked take as the block's
recording, align scoped to the block, a window cut out of a shot's own `audio_file`). It would put the songs
in the act's export, but at the cost of song-first timing, scoped align and a second kind of recording inside
a spoken episode. The one thing it gave that separate episodes don't, a smooth way in and out of the song, is
had more cheaply by the joins below.

## The pieces

1. **The song is made first**, as a Song cue in a scratch episode (the show's `songbook`: a held title card
   per song, TITLES_GUIDE.md "The song first, the picture after"), its lyrics on its sections. Takes are
   rendered and one is picked.
2. **The number is a music video.** The picked take is the number's recording (`<number>\audio\song.wav`);
   its script has every sung line as dialogue, word for word (the hook lines on camera, the rest `(V.O.)`
   over the action); align, build, render, cut on the song's beats. The number has a series config of its own:
   align writes `source_track` into the config its episode uses, and the act's must stay `generate`.
3. **The joins.** The number's first shot opens on the act's last frame before the slot; the act's first shot
   after the slot opens on the number's last frame (a first keyframe: H3 Ref2VA, Singularity and Hybrid read
   one on a shot that asks for it; FL2VA and LTX also a last). So Fanny walks into the song and out of it in
   one movement. A keyframe is cut only from a take of the same episode (refs.keyframe_from_take), so the
   frame is copied in by hand: export it from the other episode's take and drop it on the shot's first
   keyframe in the editor (or save it as `refs\shots\<shot>\first.png` and give the shot `first: import`).
   Decided (2026-11-15): that's enough; no cross-episode keyframe.
4. **Singing in the characters' voices: a voice pass.** The song models can't sing in a given voice
   (MiniMax Music 3 and YuE2 take no voice at all; ACE-Step's timbre reference is untested on voices; Lyria 3
   takes no audio). After a take is picked: its vocal stem (vocals.py, Demucs), cut at each sung line's window
   (align on the stem), each piece converted to its singer's `voice_sample`, the pieces laid back into a
   converted stem and remixed over the take's band. The converted take becomes the number's recording.
   The converter is **SoulX-Singer-SVC** (Soul-AILab, Apache-2.0 code and weights, zero-shot from a short
   reference), installed beside ComfyUI in its own environment (`F:\tools\SoulX-Singer`, Python 3.11, torch
   2.7.1 cu128 for the 5090; only what conversion needs: no speech recognition, no separator) and run as a
   subprocess. Open: how well it sings from a *spoken* sample (test a line per character; then the best
   converted line can be that singer's reference), children's voices, chorus lines (several singers: left as
   sung).
5. **The whole show as one cut.** Acts and numbers are exported each, and joined in order (an NLE from each
   episode's `assemble --xml`, or the exports back to back).

## Checklist

- [x] the songbook: a Song cue per song over a held title card, its lyrics, style, tempo, meter and key
      (2026-11-14; nine cues, 27 takes rendered)
- [x] the numbers written as music-video episodes, every sung line in order (2026-11-15; nine)
- [x] SoulX-Singer-SVC: installed, and its own example converted on the 5090 (2026-11-15: `F:\tools\SoulX-Singer`,
      the 51.5 s example in 14 s of inference, about 25 s more to load; out at 24 kHz, resampled when remixed;
      fp16 with `--auto_shift`)
- [x] the voice pass tried by hand, from spoken voice samples (2026-11-15/16): a picked take's vocals converted
      per singer, a duet or ensemble spliced line by line from the lyric sheet's singer marks (Whisper's word
      times matched to the sheet), the result kept as a new take of the cue; songs 1–6 done this way
- [x] a number's recording starts about two bars before its first sung line (decided 2026-11-15): the take's
      long band intros are cut from the number (faded in at a bar line), kept whole as `audio\song_full.wav`;
      the act can carry the intro low under its last lines into the slot instead
- [ ] the voice pass in seriesmith: a job (stem, the lines' windows, a conversion per singer, remixed)
- [ ] the whole show as one cut (or say how in the docs)
