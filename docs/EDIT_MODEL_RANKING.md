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
rest, which is seven mascot renders and all nine recasts. The recast's cause isn't known: it could be its prompt, which
was written for this test where the mascot's is Viggle's, or the one seed. So FLUX.3's lead on a person-to-person
swap rests on the stills and the pin, and the recast still has this fault to solve.

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
consistency. With a real picture to work from, FLUX.3 Klein turbo still leads and Qwen 2.1 still jumps. A person hasn't been
run this way yet.

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
- **One seed per model through Viggle.** Whether the dough fault is the prompt or the seed needs more seeds on the
  recast. It's the first thing to add, since person-to-person is the most common use.
- **Local models only.** Hosted ones, such as GPT Image 2 (which Viggle paints with) and Nano Banana, weren't run.
- **Each model on its target's defaults**, with one wording. A model could do better with a prompt written for it.

The pictures and renders aren't in the repo, as the footage is Viggle's third-party example material. On the machine
they were made on: `C:\AI\ComfyUI\ComfyUI\output\viggle_remake\repaint_test\`.

## Other jobs

Earlier, smaller tests of the same models on other work, which came out differently:

- **Relighting** (2026-10-19, one seed per model): FLUX.2 Klein edit best and fastest; Qwen-Image 2.1 the most faithful
  but timid; H3 still cinematic but it invents things; Kontext grades the whole frame and loses identity; FLUX.3
  Klein weak.
- **Cutting a character out of a frame** (2026-10-11): Qwen-Image-Edit Rapid gave a clean, whole figure; FLUX.2 Klein
  edit left a ghost of the scene and kept the frame's crop. Removing people from a place, Klein was clean.
