# Edit models ranked for repainting a video frame

Tested 2026-11-05 on the local RTX 5090 (32 GB). Which edit model to use when repainting a frame of a clip
into its target look, the input [Viggle Remake](https://huggingface.co/Viggle/Viggle-Remake) reads. The
question here is narrow: the picture has to change what was asked and leave the pose and framing where they were,
because a pinned frame copies its composition into the video.

This ranks this one job, on one clip per Viggle mode. It says nothing about relighting or cut-outs
([Other jobs](#other-jobs)), and models change quickly, so treat it as dated.

## The ranking

**Replacing a person or character** (Viggle's `swap` mode), painted the way the work is really done: the first frame
from the instruction, the later frame from its source frame with the first frame's result as a reference, then that
pair through Viggle:

| # | Model | Time with a reference | Scene held, mascot / recast | Jumps near the pin, mascot / recast | What it did |
|---|---|---|---|---|---|
| 1 | FLUX.3 Klein turbo (`flux3_klein_turbo`) | 13 s | 20.9 / 23.1 dB | 0 / 0 | The same character in both frames, no jump, and the mascot render kept the dough over the lens. Start here |
| 2 | FLUX.3 Klein (`flux3_klein`) | 32 s | 26.8 / 27.5 dB | 0 / 1 | As turbo, holding the scene closer, but it lifted the dough over the mascot's mouth on the later frame |
| 3 | Qwen-Image 2.1 (`qwen_image_21`) | 4 s | 14.6 / 14.9 dB | 9 / 3 | The same character, but copied the first frame's scene and framing into the later one, with a gravelly road. The render jumps to it |
| 4 | FLUX.2 Klein edit (`flux2_klein_edit`) | 5 s | 15.7 / 14.3 dB | 8 / 8 | Moved the figure and left a dark object at the frame's edge, so the render jumps at the pin |
| 5 | MiniMax H3 still (`minimax_h3_still`) | 9 s | 14.0 / 15.5 dB | 8 / 6 | A consistent character, but an oversized mascot with the dough over its face, and the recast copied the first frame's scene |
| 6 | FastH3 Omni still (`fasth3_omni_still`) | 13 s | 14.5 / 15.6 dB | 7 / 6 | As H3, and the recast's pinned frame collapsed into a blur |
| 7 | Fibo 2.0 Edit Turbo (`fibo2_edit_turbo`) | 7 s | 16.6 / 15.2 dB | 4 / 5 | Turns the dough into a disc, which comes through in the render, with a smear at the pin. Non-commercial licence |
| 8 | Qwen-Image-Edit Rapid (`qwen_rapid_aio`) | 9 s | 15.3 / 15.8 dB | 7 / 6 | Copied the first frame's scene, and drew the recast woman as a cartoon, so not for live action |
| 9 | Fibo 2.0 Dev (`fibo2_dev`) | 134 s | 16.6 / 15.1 dB | 7 / 4 | The disc again, held for several frames, and far the slowest. Non-commercial licence |

**FLUX Kontext isn't ranked for this.** It reads one picture, so it can't be given the character at all. Painted without
one, it also moved the camera and the figure.

The top two are clear. Everything below them jumps at the pin, so that order is close and a judgement.

Turbo and full FLUX.3 Klein are a tie on the renders. Full holds the scene closer in its still, but nothing separates
them to the eye once rendered, so turbo is first because it is faster.

**Removing an object or changing the scene** (Viggle's `edit` mode):

| # | Model | Median time | Against baseline / scene vs source | What it did |
|---|---|---|---|---|
| 1 | Qwen-Image 2.1 | 3 s | 30.5 / 32.2 dB | Clean removal, framing and colour held. The pick for commercial work |
| 2 | Fibo 2.0 Edit Turbo | 3 s | 30.5 / 33.3 dB | The same quality or a shade better, but non-commercial |
| 3 | MiniMax H3 still | 6 s | 30.8 / 32.3 dB | Clean: its drift only showed on figures |
| 4 | FastH3 Omni still | 8 s | 30.9 / 31.3 dB | Clean, with a slight regrade of the sky and grass |
| 5 | FLUX.3 Klein | 19 s | 28.3 / 32.0 dB | Clean, slower for no gain |
| 6 | FLUX Kontext | 17 s | 29.7 / 33.4 dB | Numbers near the top, but its stills shift the framing and soften the picture |
| 7 | Qwen-Image-Edit Rapid | 4 s | 26.8 / 29.8 dB | Clean, with some colour drift |
| 8 | FLUX.3 Klein turbo | 7 s | 24.9 / 28.0 dB | Removes them but regrades, so it's the wrong FLUX.3 for this job |
| 9 | FLUX.2 Klein edit | 3 s | 21.8 / 23.8 dB | Removes them but brightens the whole frame |
| 10 | Fibo 2.0 Dev | 61 s | 23.0 / 24.4 dB | Reframed the shot and added people and paths that weren't there. Don't use |

The main finding is that **no model wins both**. FLUX.3 Klein turbo is first for a person and eighth for a
scene; H3 is fifth for a person and third for a scene. To use one model for both, Qwen-Image 2.1 is third and
first, but expect the jump on a person.

**A painted frame has to keep its own source frame's composition.** Where it didn't, the render lurched to that
composition at the pin and back again, or smeared. So check a later frame against its source before rendering it.
The reference can cause this: Qwen 2.1 and Rapid took the first frame's scene from it in both cases, and H3 and FastH3
on the recast. On the mascot, Qwen 2.1 and Rapid had 1 jump each at that pin without a reference, against 9 and 7 with one,
though without one they gave Viggle two different characters.

**Most renders didn't keep the dough over the lens.** At frames 145 to 153 of the source, the dough fills most of the
frame. Viggle's baseline and FLUX.3's two mascot renders follow that. The other renders drop the dough and show the figure
instead: seen directly on FLUX.3's two recasts and on both Qwen 2.1 renders and FLUX.2's mascot, and in the frame scan on the
rest, which is seven mascot renders and all nine recasts. On one render each, it looks to come from the invented paintings, not the recast's prompt or the
seed: FLUX.3 Klein turbo painting her from a character picture kept the dough with that same prompt and seed (below).

**In the table above, each model invented its own character from the instruction.** None of them saw a picture of the
mascot, so none could match Viggle's. Four more renders on the same source and seed started from a character picture,
Viggle's mascot cut out of its own painted frame (with Qwen-Image-Edit Rapid). They are one seed each, on the mascot only:

| Run | Dough over the lens | Jumps, near the pin / elsewhere | Likeness and look |
|---|---|---|---|
| Viggle's result: its painted frames, pinned | Kept | 0 / 5 | The target |
| Viggle's painted frames, no pins | Kept | 0 / 1 | Closest to the target. Pins weren't what held the motion here |
| FLUX.3 Klein turbo paints frames 12 and 184 from the picture, pinned | Kept | 0 / 3 | Recognisably the same mascot, with a taller crown. The closest of the runs without Viggle's paintings |
| The character picture alone, no painted frames, no pins | Kept | 0 / 7 | Follows the source's motion. A looser likeness: puffier suit and bigger eyes, and the head and crown change size between frames |
| Qwen-Image 2.1 paints frames 12 and 184 from the picture, pinned | Lost | 2 / 16 | Right mascot, but the figure shrinks to a whole-body view at the pin |

So the source video carries the motion even with no painted frame at all, and a painted frame buys likeness and
consistency. With a real picture to work from, FLUX.3 Klein turbo still leads and Qwen 2.1 still jumps.

The woman, on the same source, from a full-length picture of her and in one run a close-up too. Both pictures were made
from FLUX.3's painted frame 12 with Qwen-Image 2.1:

| Run | Seed | Dough over the lens | Jumps, near the pin / elsewhere | Likeness and look |
|---|---|---|---|---|
| Full-length and close-up pictures, no pins | 0 | Kept | 0 / 0 | The freckles come through. Jacket paler than the picture. Follows the source's expressions |
| Full-length picture, no pins | 0 | Kept | 0 / 0 | Few freckles, and the jacket paler |
| Full-length picture, no pins | 1 | Kept | 0 / 1 | As seed 0, a slightly different face |
| FLUX.3 Klein turbo paints frames 12 and 184 from the picture, pinned | 0 | Kept | 0 / 7 | Colours closest to the picture, but it drifts from the source's framing around frame 120, and her expression at the start is flatter |
| Earlier: FLUX.3 Klein turbo's own invented woman, pinned | 0 | Lost | 0 / 16 | For comparison |

For a person as for the mascot, then: the pictures alone hold the motion best, and a painted frame holds the look best.

**The face doesn't hold in any of the four new renders.** Watched through, it melts several times over the run. The sampled
frames and the jump scan didn't show this. Resolution is the main cause: the same pictures, prompt, seed and 124 frames
were clearly better watched at 1280x736 than at 832x480, the size Viggle's own tool treats as a draft. That took 260 s for
124 frames on the int8 weights. So render faces at 1280x736. The talking close-ups after frame 124 haven't been run at that size.

**H3 Ref2VA with a character LoRA looked better than Viggle at that size.** With
[H3 Character Swap V1.5](https://huggingface.co/akatz-ai/MiniMax-H3-Character-Swap-LoRA) at strength 1, on the same pictures,
frames, size and seed, both the Turbo render (8 steps, 217 s) and the full one (20 steps, 462 s) were preferred to Viggle's when
watched. Viggle stayed closer to the source's scene and motion (20.0 dB, against 16.4 and 16.6), and it keeps the source's
sound, where these generate their own. These ran on ComfyUI's own nodes, without the SAM mask of the author's full recipe.

**What the face does across a shot.** InsightFace scored every frame's face against her picture, a stand-in for melting and not
a measure of it. At 1280x736 Character Swap averaged 0.47 on the first 124 frames (worst tenth 0.25 to 0.29) against Viggle's 0.43
(0.18). The score falls by half or more in every render when the head turns fast, though blur comes with those frames; holding an
angle costs little, and a bigger face scores much higher. The dough over the lens dips it (0.52 to 0.53 at 736), and it recovers
straight after. Watched on the frames with the dough and the talking close-ups, Turbo8 stayed cleaner than Viggle.

**Two people, one clip, seed 0, 124 frames at 1280x736.** The pink jacket became the woman and the white suit the mascot, with no mix-up
in any run, and SAM 3.1 kept a mask on each man in every frame:

| Run | Time | Scene outside the two men, against the source | What it did |
|---|---|---|---|
| Viggle Remake, one pass, three pictures | 264 s | 24.6 dB (lowest 23.9) | Both characters whole, no clipping. The rest of the frame is redrawn |
| IV Studio Replace Advanced, one pass, one picture each | 315 s | 30.0 dB (lowest 28.4) | **The mascot never appeared:** the white suit stayed a man, redrawn, and the woman kept a hat. The tracks and the prompt were right, so this was H3 on this pass, on one seed |
| Character Swap, unmasked, woman's pass alone | 386 s | 24.3 dB (lowest 21.7) | Whole frame redrawn |
| Character Swap, unmasked, mascot's pass alone | 380 s | 20.9 dB (lowest 12.9) | Whole frame redrawn, and the camera drifts at points |
| Those two composited through the men's SAM masks | | 42.9 dB (lowest 42.6) | Scene unchanged but for the encode. The mascot's crown is cut off, because the mask is the man's shape |
| Character Swap, masked as in Comfy's OpenJutsu, woman's pass alone | | 34.7 dB (lowest 33.5) | Only the area round her is redrawn |
| Character Swap, masked, mascot's pass alone | | 30.5 dB (lowest 28.3) | The same, on the mascot |
| Those two masked passes composited | about 4 min each | 32.2 dB (lowest 29.0) | Both characters whole, with the crown intact. The score counts the 64 px margin round each man that was redrawn; beyond it, the picture is the source but for the encode |

The composites were scored after encoding to H.264, so 43 dB is about what the encode itself costs here.

So one masked Character Swap pass per person, each from the source and composited, gave both characters in full with the
scene kept, without stacking one pass on another. Viggle's one pass is the simpler way to two whole characters, and redraws more of the
frame. These are stills and scores of one clip on one seed, with a mascot, and IV Studio's result may differ with two people. Nobody has
tested stacked passes or Fix faces here.

## Reading the numbers

- **Scene held** is PSNR of the later painted frame (frame 184) against its source frame, over the part Viggle's own
  painted frame left alone (62% of the picture). Against the source's frame 12, Qwen 2.1 and Rapid score higher (about
  20 to 22 dB) on both cases, and H3 and FastH3 on the recast (about 24 dB), which is how the copying shows.
- **Jumps near the pin** counts the steps between neighbouring frames, from 170 to 192, that change more than 8 levels
  (of 255) above the source's own change at that step. The baseline has 0. It's a coarse count of how much a render
  lurches, read alongside strips of those frames, not a measure of how bad each one looks.
- **Swap scores against the baseline aren't used.** They ran from 14.5 to 18.3 dB, and they only measure closeness to
  Viggle's particular mascot. Viggle's own notes warn that a few dB on this clip is noise.
- **Edit scores mean more**, since that clip is stable, but a higher score only says the picture stayed
  near the baseline. Kontext's is why looking still counts.
- **Times** in the edit table are the median of 12 stills through seriesmith's Edit at about 1168x672, loading excluded
  in effect (the first job on a model took 12 to 66 s). In the swap table they are one still each, with the model
  already loaded and a second picture to read.

## What was tested

- **120 stills:** 10 models, 3 cases, 2 frames each, seeds 111 and 222, through seriesmith's own Edit
  (`refs.plan_edit`, the instruction wrapped as usual).
- **20 Viggle renders:** each model's seed 111 pair through `viggle_remake_swap_v2v` and `viggle_remake_edit_v2v` on
  the merged int8 weights, with Viggle's example prompt, seed 0, 226 frames at 832x480, pins as in Viggle's examples.
  The edit ranking comes from these. The swap ones gave each model's two frames as two different characters, so the
  chained test replaced them.
- **The chained swap test:** 9 models, mascot and recast. Frame 12 was the seed 111 still above; frame 184 was painted
  from its source frame with frame 12 as image 2; then 18 renders on the same graph and seed. The mascot used Viggle's
  example prompt, the recast that prompt rewritten for the woman.
- **Baseline:** the same render from Viggle's own painted frames (made with `gpt-image`). The scores are PSNR over
  every 4th frame: against that render, and against the source wherever the baseline matches the source.

The instructions, as typed:

- **Mascot:** Replace the man with a person wholly hidden inside a full-body plush pineapple mascot costume: a big
  round golden-yellow pineapple head with a raised diamond-pattern rind and a spiky crown of stiff green leaves on
  top, two big round black-and-white cartoon eyes and a wide stitched black smile on the front of the pineapple, a
  padded golden-yellow bodysuit with the same diamond-pattern rind over the torso, arms and legs, bright-green padded
  five-finger gloves and bright-green padded boots. The costume covers the whole body. It has exactly the man's pose,
  position and size in the frame, and holds the white pizza dough the same way.
- **Recast:** Replace the man with a different person: a tall woman in her thirties with a long copper-red braid and
  freckles, wearing a dark green canvas work jacket, a cream apron and tan trousers. She has exactly the man's pose,
  position and size in the frame, and she holds the white pizza dough the same way.
- **Remove:** Remove all the wind turbines, towers and blades included, and continue the sky, the clouds and the
  horizon where they stood.

## How far this goes

- **The rankings are one person's reading** of contact sheets, backed by the numbers above. Each swap render was seen as 5
  frames plus strips around the pin, and scanned frame by frame for jumps, but not watched through, so subtler flicker
  wouldn't show. The edit renders were judged from 3 frames each.
- **One clip per mode.** Swap is one handheld single take; edit is one drone shot.
- **One seed per model through Viggle**, and two on the woman from her picture.
- **The character-picture runs are few:** one clip at 832x480, one invented woman and one mascot.
- **Local models only.** Hosted ones, such as GPT Image 2 (which Viggle paints with) and Nano Banana, weren't run.
- **Each model on its target's defaults**, with one wording. A model could do better with a prompt written for it.

The pictures and renders aren't in the repo, as the footage is Viggle's third-party example material. On the machine
they were made on: `C:\AI\ComfyUI\ComfyUI\output\viggle_remake\repaint_test\`.

## Other jobs

Earlier, smaller tests of the same models on other work, which came out differently:

- **Relighting** (2026-10-19, one seed per model): FLUX.2 Klein edit best and fastest; Qwen-Image 2.1 the most faithful
  but timid; H3 still cinematic but it invents things; Kontext grades the whole frame and loses identity; FLUX.3
  Klein weak.
- **Cutting a character out of a frame, and clearing a frame to its plate** (2026-11-05): see below. These supersede the
  smaller notes on the same jobs.
- **Cutting a character out of a frame** (2026-10-11): Qwen-Image-Edit Rapid gave a clean, whole figure; FLUX.2 Klein
  edit left a ghost of the scene and kept the frame's crop. Removing people from a place, Klein was clean.

## Extraction

Tested 2026-11-05 on one frame each of a Ballroom take (ep03 sh040 t02, a FastH3 Omni render at 1344x768), through seriesmith's
Edit, the 10 local models, seeds 111 and 222. The pictures stay out of the repo.

**Cutting a character out** of a three-shot at 3.63 s, the one on frame left, whose neighbour's arm overlaps her. It asks for her in
place on plain grey. The scores are her area against the frame, where a figure that moved scores low, and InsightFace's match of her
face against the frame's.

| # | Model | Time | Her area | Face | What it did |
|---|---|---|---|---|---|
| 1 | FLUX.3 Klein | 22 s | 16.5 dB | 0.96 | In place, the neighbour gone, a little more colour. Start here |
| 2 | Qwen-Image 2.1 | 7 s | 12.9 dB | 0.93 | In place and clean on both seeds, but lifts the picture, and one seed is pale |
| 3 | Fibo 2.0 Edit Turbo | 4 s | 19.6 dB | 0.97 | The most faithful figure, but keeps the neighbour's sleeve on both seeds. Non-commercial |
| 4 | FastH3 Omni still | 10 s | 18.9 dB | 0.74 | Exactly in place on clean white, but darkens the skin and changes the face |
| 5 | FLUX.2 Klein edit | 3 s | 11.4 dB | 0.92 | Clean, but the colour and hair are oversaturated |
| 6 | Fibo 2.0 Dev | 83 s | 12.8 dB | 0.94 | Moves her right and crops her. Non-commercial |
| 7 | Qwen-Image-Edit Rapid | 5 s | 16.5 dB | 0.88 | Fine on one seed; the other keeps the sleeve and draws an outline |
| 8 | FLUX.3 Klein turbo | 8 s | 11.9 dB | 0.92 | Moves her right and crops her |
| 9 | MiniMax H3 still | 9 s | 12.7 dB | 0.77 | Good on one seed; on the other she fades to a ghost |
| 10 | FLUX Kontext | 20 s | 6.5 dB | 0.71 | Loses her head and most of her body on both seeds. Don't use |

This doesn't repeat the 2026-10-11 result, where Rapid was the clean one; there the job was a whole figure, here a close, overlapped one.

**Clearing a frame to its plate** at 0.21 s, one woman walking through the room. The take's plate turned out not to be the frame's
view, since H3 reframed the room when it rendered: straight against the plate every model scores about 17 dB, so that says nothing.
So the first score is the room outside her against the frame, from SAM 3.1's mask. Aligning the plate on 29 matched points gives a second
score over the 60% of her area it reaches, from 19 to 22.5 dB, too close to rank on.

| # | Model | Room kept | What it painted where she stood |
|---|---|---|---|
| 1 | Qwen-Image 2.1 | 31.7 dB | Clean floor and rug on both seeds, framing and colour held |
| 2 | Fibo 2.0 Edit Turbo | 33.4 dB | Clean on one seed, invents chairs on the other. Non-commercial |
| 3 | MiniMax H3 still | 31.9 dB | Armchairs on both seeds. The real plate has one about there, not these |
| 4 | Fibo 2.0 Dev | 31.6 dB | One seed clean, the other a chair; 36 and 27 dB. Non-commercial |
| 5 | FastH3 Omni still | 29.2 dB | Armchairs and a table on both seeds |
| 6 | FLUX.3 Klein | 26.6 dB | Clean on both seeds, with a slight regrade |
| 7 | FLUX.3 Klein turbo | 24.8 dB | Clean on both seeds, with a stronger regrade |
| 8 | Qwen-Image-Edit Rapid | 23.4 dB | A chair on one seed, a notch in the rug on the other |
| 9 | FLUX.2 Klein edit | 23.6 dB | Invents a chair or a table, and brightens |
| 10 | FLUX Kontext | 20.1 dB | Clean, but moves the camera and reshapes the rug |

Both agree with the swap and edit tables above: FLUX.3 Klein for a person, Qwen-Image 2.1 for a scene. One frame each, two seeds, and the
orders are a reading of the pictures with the numbers beside them.
