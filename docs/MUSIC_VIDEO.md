# Making a music video

A music video is cut to a finished song, not scored to a cut: the song comes first and the picture follows it. seriesmith treats the song the way it treats recorded dialogue ([RECORDED_DIALOGUE.md](RECORDED_DIALOGUE.md)). The song is the episode's **recording**, the lyrics are the script's lines, every shot gets a window of the song, and a singer's lips follow their window. This guide goes through it in order, with CupsMV as the example: a 2:07 pop song as 33 shots on H3 Ref2VA.

## The idea in one paragraph

Attach the song as the episode's recording. Write the script with the lyrics as one character's lines, a line or two per singing shot, and shots without lines for the band and the b-roll. **align** hears the song, finds each line in it, and gives every shot an `audio: in-out` window, so the shots run end to end through the song. Singing shots dub to their window with `retention: fully_copy`, so the picture is made to the singing. The other shots render as usual, with their own sound. On export the song goes under the cut whole, either as it came (`--audio master`) or on the Music track of the mix. The shots' own sound is never the soundtrack.

## 1. The song as the recording

Put the song in the episode folder (for example `ep01\audio\song.wav`), then attach it from the editor's **Recording** window, or write it into the series config:

```json
"audio": {"mode": "source_track", "track": "audio/song.wav",
          "default_policy": "dub", "retention": "fully_copy"}
```

- `source_track` makes every shot with lines a dub of the recording.
- `default_policy: dub` lets the song be the shot's whole soundtrack. The default, `dub_keep_foley`, keeps the model's own sound effects under a recorded line, which a song doesn't want.
- `retention: fully_copy` makes the window the shot's entire sound on H3, so the lips follow it. You can also set it per shot (`retention: fully_copy` in the shot).

Until align has run, the build says **Align to finish**: with a recording attached, every shot with lines needs a window. That's expected.

## 2. The lyrics as the script's lines

The singer is a character like any other, and each sung phrase is a line:

```
## sh040
who: june
size: close
June sings to the camera, tapping the upturned plastic cup on the table in rhythm.
camera: holds static
JUNE: I got my ticket for the long way
```

- **Keep a singing shot short.** About 6 seconds at most on H3. CupsMV split each longer phrase at its widest gap, so one phrase ended a shot and the next began the next shot.
- **Shots that don't sing have no lines.** An intro, the band, a cutaway, the instrumental break. align fills the pauses between sung lines with them, stretched or squeezed from their scripted `dur:` to fit, and warns you when the stretch is large. On CupsMV, align stretched a shot scripted at 3 seconds to fill the 7.6-second instrumental break, and said so.
- **Write the lyrics as they're sung.** Take them from the lyric sheet, or from the transcript. align caches the transcript as `<recording>.words.json`, even when the script has no lines yet (it then stops at "the script has no dialogue to align"). The more closely the lines follow the singing, the better the match.

## 3. align

```
seriesmith align    Shows\CupsMV\ep01 --dry-run     # look first
seriesmith align    Shows\CupsMV\ep01
seriesmith build    Shows\CupsMV\ep01
```

align writes an `audio: in-out` line on every shot, so the windows run end to end through the song, and writes `align_report.md`. In the editor, use the Recording window's **Dry run** and **Align**. Check the report's coverage column: CupsMV's 30 sung lines all matched 100%. For better transcription of singing, use `--model large-v3` (the Recording window's **Whisper model**).

**The vocal stem** is optional, and off by default. A song's singing can be split from the band on your local ComfyUI (seriesmith's Vocal Stem node, Hybrid Demucs) and kept beside the song as `<recording>.vocals.wav`. It can be used in two places:

- `align --vocals` (the Recording window's **from the vocal stem**) transcribes the stem, and cuts in the pauses of the singing rather than of the whole mix.
- `"audio": {"dub_from": "vocals"}` (**dub shots hear the vocal stem**) sends each singing shot's window from the stem instead of the song.

The episode's sound is the whole song either way. CupsMV's ep01 was dubbed to the full song and ep02 to the stem, with the same windows and seeds, and H3 Ref2VA's lip-sync was as good either way. That's why the stem is offered, not forced. Try it when align misses lines under a loud band, or when a model mouths the instruments. Details are in [RECORDED_DIALOGUE.md](RECORDED_DIALOGUE.md#a-recording-with-music-the-vocal-stem).

## 4. Render

```
seriesmith render   Shows\CupsMV\ep01 --proxy
```

Singing shots render as dubs. H3 holds each one's window as the shot's soundtrack and makes the picture to it. Shots without lines render in `generate` mode, with their own sound and nothing to lip-sync. Each shot still renders to its window's length. Frame singing shots as close-ups or medium shots: the reference picture's framing matters more than the prompt. CupsMV's 33 proxies took 11:45 on an RTX 5090.

## 5. Cutting to the beat

The cut already follows the song: assemble trims every timed shot back to its exact window, so the picture lines up with the song from the first window's start. When you trim by hand in the timeline, trims **snap to the song's beats**:

- With no music on the Music lane, the beats are the recording's own when it has a steady beat. A song does: CupsMV's measured 130.00 bpm. With a song or cue on the Music lane, the beats are that item's.
- A trim's cut moves onto the nearest beat within a few pixels, or onto a downbeat from a little further, which it prefers. The tip names the beat ("bar 12").
- Hold **Alt** while you drag to trim freely.

The beats are drawn faintly on the Music lane. [EDITOR.md](EDITOR.md) has the rest of the timeline.

## 6. Export with the song unbroken

The song must come from the export, never from the clips. A shot without lines has its own generated sound, so the clips' sound joined end to end isn't the song. There are two ways:

- **The song as it came** (CupsMV ep01): `seriesmith assemble Shows\CupsMV\ep01 --audio master` lays the recording under the whole cut, starting at the first window, and ignores the mix. The mastered song is louder than seriesmith's -16 LUFS target (ep01 measured -10.5 LUFS and +1.1 dBTP). The export's loudness check says so and changes nothing.
- **The song on the Music track** (CupsMV ep02): put the song on the Music lane from the first shot to the last, at 0 dB with no ducking, and **mute the Dialogue track** (the clips' own sound). Export then takes the mix, which brings the song to the loudness target (ep02 measured -16.1 LUFS) and lands it to the sample. The mix's other tracks still work: an effect, an ambience bed, or a second music track under the song ([SCORING.md](SCORING.md) has the levels).

In `mix.json` the second way is:

```json
"tracks": {"dialogue": {"mute": true}, "music": {"gain_db": 0.0, "duck_db": 0.0}},
"items": [{"id": "song", "track": "music", "path": "audio/song.wav",
           "in": {"shot": "sh010", "frame": 0}, "out": {"shot": "sh330", "frame": 67},
           "label": "When I'm Gone (the song)"}]
```

## Things to know

- **A window can't move without moving the song.** Re-time a shot by editing its `audio:` line, or by changing the lines and running align again. The shot then needs rendering again, because its picture was made to the old window.
- **Replace the song, then align again** with `--retranscribe`. The cached transcript and the vocal stem belong to the old file. The stem is made again when it's older than the recording.
- **Proxies first.** As with any episode, judge timing and lip-sync on proxies, then render the final pass.
