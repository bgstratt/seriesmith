# The H3 Ref2VA target in detail

The default video target, `minimax_h3_ref2va`: how a shot reaches MiniMax H3 Ref2VA, what each reference slot holds, how sheets, voices and audio policies work, and what comes out.

How the default target works. The other targets are described in
[AUTHORING.md](AUTHORING.md) and their own `seriesmith/targets/video/<id>/` folders.
`minimax_h3` is a different target: H3 hosted on Comfy Router (`builtin:router_video`),
with none of the slots, sheets or audio policies below.

## The Ref2VA ComfyUI workflow (`H3_Ref2VA_Shotlist_v1.json`)

seriesmith drives this graph for you: load
`seriesmith/targets/video/minimax_h3_ref2va/workflow.json` to see it (save your own copy
in ComfyUI under the name above to change how H3 renders; [INSTALL.md](../INSTALL.md#3-workflows)).
For each take its loader becomes **SeriesmithShotLoader**, given the one shot as JSON
and its reference pictures as uploads, and its saver **SeriesmithSaveTake**, which reports
every file it writes for seriesmith to put in the take (`comfy_nodes/shot.py`; restart
ComfyUI when it changes).

No audio dependencies. The nodes read and write PCM wav with the Python
standard library and fall back to ffmpeg for mp3/m4a/flac. In particular they
do **not** call `torchaudio.save`, which since torchaudio 2.13 routes through
torchcodec and raises `ImportError` when it is missing — you do not need to
install torchcodec.

## Reference slots

Slots 1–3 carry the shot's **subjects** — characters first, then props and
vehicles, in the order the script lists them. Slot 4 always carries the
**location plate**.

There is no style reference image. The style is already carried by every sheet
and plate (all drawn in it) and stated in the prompt text, so a dedicated style
slot buys redundant conditioning. The background buys concrete layout, palette,
lighting direction and depth for *this* shot — and keeps one location looking
like one place across every cut in a sequence.

The background is written into the prompt as a proper `<Subject N>` sourced
from `<Picture 4>`, because H3's spec lists scenes and environments as Subject
content; a bare `<Picture N>` means "use this exact frame as a keyframe", which
is not what a location plate is for. Its retention marker is
`partially_preserved` — layout and light are kept, framing is not.

## Reference sheets

Author each character as a **horizontal 4-panel strip** — 3/4 body, side, back,
face close-up — at 4096×1024 or larger. `ref_image_size: max` scales the *short*
side to 2048, so a horizontal strip keeps every panel sharp where a square grid
would halve it.

Each shot uses only **one panel** of each sheet (`panel_mode: auto`): the face
close-up for a single-character close shot, the three-quarter body everywhere
else. A reference image with more than one figure in it gets drawn as more than
one person, so multi-panel strips are no longer fed by default. `full`, `pair`,
`face` and `body` force a crop (`render --panel-mode`). The socket-to-prompt
mapping is fixed, so prompts are stable regardless of cast size:

| Socket | 1 subject | 2 subjects | 3 subjects |
|---|---|---|---|
| `<Picture 1>` | subject 1 | subject 1 | subject 1 |
| `<Picture 2>` | background | subject 2 | subject 2 |
| `<Picture 3>` | background | background | subject 3 |
| `<Picture 4>` | background | background | background |

**A change of clothes is a second subject**, not a note in the prompt. Give it `of:` in the
series config and its own `design`; it inherits the character's name and voice, and
its sheet path is derived from theirs (`refs/gina/gina_sheet_4panel.png` →
`refs/gina/gina_towel_sheet_4panel.png`). The script names the variant on `who:` and goes on
calling the character by name in the dialogue. The point is that the retention marker stays
`fully_preserved` against a sheet that is actually wearing the towel: H3 preserves a subject
whole — face, hair, proportions *and* wardrobe — so the only way to contradict the sheet is
to weaken the whole subject, which loosens the face in order to change the clothes.

A variant's views are generated **from the character's own**: the towel's back panel is an
edit of their back panel, on any image target that reads references (`flux2_klein_edit`,
`flux_kontext`, `minimax_h3_still`). On a text-to-image target there is nothing to edit
from, so it draws the variant from its `design` on the character's seed — closer than a
fresh draw, but not the same thing.

Props and vehicles are single clean images on a flat background and are never
panel-cropped; only character sheets get `panel_mode`. Unused
subject sockets take the background plate — it is smaller than a character
strip and reinforces the location rather than biasing identity toward whichever
subject got duplicated.

## Voices without bodies

`NAME (V.O.):` and `NAME (O.S.):` mark a line as spoken by someone who is not
on screen. Such a speaker is **not** added to the visible cast: they cost no
reference slot, are never drawn, and need no character sheet — only a `voice`
description in the series config (and a `voice_sample` if the shot uses `clone`).

Only `who:` puts a character on screen. Before this existed, any speaking name
was auto-added to the cast, so a phone voice from another house burned a slot
and got rendered into frame.

| Form | Meaning | Slot? | Prompt |
|---|---|---|---|
| `RILEY: line` | on screen, speaking | yes | `<Subject N> (Sx) says,` |
| `RILEY (V.O.): line` | voiceover / narration / phone | only if also in `who:` | `says in an off-screen voiceover` |
| `RILEY (O.S.): line` | in the space, outside frame | only if also in `who:` | `says from off-screen, outside the frame` |

A `(V.O.)` speaker who *is* in `who:` — a character narrating over their own
shot — additionally gets H3's required lips-closed clause ("while their lips remain
completely closed"), so H3 doesn't animate their mouth over the narration.
A speaker with no visual reference is identified by their voice description
followed by `(Sx)`, per H3's spec, rather than an invented `<Subject>`.

A shot may have no `who:` at all — an establishing plate with voiceover over
it. The location then fills all four slots and becomes `<Subject 1>`.

## Audio references

`ref_audio_0..2` carry one clip each, and how many are used depends on the
policy:

| Policy | Clips fed | What each one is |
|---|---|---|
| `clone` | **one per speaker** | that character's voice-timbre sample |
| `dub` / `dub_keep_foley` | one | the slice of the recorded mix, which already contains every voice in the shot |
| `generate` | none | — |

The per-speaker rule is the one that bites: a two-hander in `clone` mode needs
two samples, and feeding one voices the second character from the first one's
sample. Unused sockets receive null. H3 takes at most three standalone audio
references, so a `clone` shot is capped at three speakers and the compiler
errors above that rather than silently dropping one.

## Audio policies

Set per shot with `policy:` in the script, else from the series config's `audio.mode`.
H3 emits **one mixed track** — there are no stems — which is what these policies work
around.

| Policy | Reference fed | mp4 audio | Use for |
|---|---|---|---|
| `generate` | none | H3's mix | Non-dialogue shots. H3's synced foley is genuinely good and free. |
| `dub` | your recorded line | **mute** | Dialogue. H3 drives lip-sync; the clean vocal goes in at conform. |
| `dub_keep_foley` | your recorded line | foley bed | Dialogue where you want H3's synced foley under your own vocal. Needs demucs. |
| `clone` | a voice sample | mute | Incidentals and the proxy pass. H3 speaks the `<d>` line in the sampled timbre. |

`generate` deliberately passes **None**, not silence — a silent clip on a
*reference* socket tells H3 to match silence.

A dub shot also has a `retention` setting (`fully_copy`, `partially_copy`, `reference`); see
[RECORDED_DIALOGUE.md](RECORDED_DIALOGUE.md#audio-policy-and-retention).

## Speech pacing

A shot's length has to hold its dialogue. H3 will fit any line into any window
by speeding the delivery up, so an over-packed shot doesn't fail — it just
comes back sounding like a chipmunk reading a contract.

```bash
seriesmith check Shows\ep01      # --check and --pace: every dialogue shot, measured
```

The model counts syllables, adds a beat at each speaker change plus air at the
head and tail, and reports the rate the shot forces on the performance.
Conversational English is ~4.0 syllables/second; brisk cartoon delivery ~4.4;
deliberate patter ~5.4. Past 5.8 it stops reading as a person talking fast.

| Field | Meaning |
|---|---|
| `pace: slow\|normal\|fast` | per shot, or `speech.pace` in the series config. 3.6 / 4.4 / 5.4 syl/s. |
| `dur: auto` | derive the length from the dialogue at that pace, then snap to the grid. |

`--check` and a normal compile emit the same findings as warnings, each with
the `dur:` that would fit and how many syllables the window actually holds.
Three ways out of a crammed shot: lengthen it, cut words, or split it in two —
and splitting is often the right answer, because a line that needs 6 seconds
usually wanted a reaction cut in the middle of it anyway.

## Resolution

`1344×768` is H3's native canvas and both axes are multiples of 32.
**1280×720 is not legal** — 720 is not divisible by 32, and the loader raises
rather than letting H3 fail deep in the graph. Crop to 1344×756 and upscale at
conform for true 16:9.

Or render the final pass at `960×544` and upscale the picked takes to `1920×1088`
(`seriesmith upscale`, then `seriesmith assemble --upscaled --size 1920x1080`): a take costs
under half as much to try, and only the kept ones are upscaled. docs/FINISHING.md,
**Render size**, says which to choose.

## Continuous shots

Ref2VA renders `continuous: latent`: the previous take's last frames (39 by default) are
held at the head of the render, video and audio, by **SeriesmithChainLatent**, and trimmed
off again before the saver (**SeriesmithChainTrim**). `continuous: first` needs a first
keyframe, which Ref2VA doesn't read: such a shot builds on `minimax_h3_fl2va` instead.
[CONTINUOUS.md](CONTINUOUS.md) has how it works.

## What you get out

`VAEDecode` emits the full frame batch as IMAGE *before* anything muxes it, so
`save_frames` gives you a PNG sequence, and H3's audio is always written
separately as `_h3.wav`. **There is no alpha channel** — compositing here means
grading, effects and titles, not lifting a character off a background. Budget
16–50 GB of PNG per 12-minute episode at 1344×768.

The mp4 is pinned with `-frames:v` and never uses `-shortest`: H3's audio often
runs a few milliseconds short of `length/fps`, and `-shortest` silently drops
the final frame, which breaks conform.

The saver also writes two JPEGs straight from the frames in memory: `_tNN.jpg`
(the middle frame) and `_tNN_strip.jpg` (8 evenly spaced frames, for hover
scrub), and a record of what it did (`status`, `finished`, `frames`, the names
of the files it wrote and its status line), which seriesmith merges into the
take's `_tNN.json` (written `queued` when the take was reserved). A failure in
the thumbnails is reported in the status line, never raised, so it can't cost
you the mp4.

---

