# Keyframe framing: medium and close shots drawn too wide

A keyframe for a medium or close shot, made on an edit model from a character's
reference sheet, sometimes comes out wider than the shot's size: knees up or full length
where the script asks for a medium shot. On Ballroom the workaround was a separate close-up
reference of each lead. This file records what was tried and what's still open.

The prompt is `keyframe_prompt()` in `seriesmith/targets/image/common.py`. For each picture,
`reference_intro()` writes one line (for a character, "Picture 1 is Denise Carter: draw this
character exactly as in picture 1 (the same face, body, clothes and colours), posed for this
shot."). After those lines come the cast's design sentences from the series config, then the
shot's size, action and camera.

## Ada sh020 (the starter example, a cartoon), MiniMax-H3-Image, two seeds

| Change | Medium framing |
|---|---|
| none (as today) | too wide, full length |
| "and yellow rain boots" dropped from Ada's design | **fixed** on both seeds |
| every design sentence dropped | **fixed** on both seeds |
| "body" dropped from the reference line | no change |
| "layout" dropped from the plate's line | no change |
| the shot's size and framing put first | no change |

A design sentence that names footwear or anything else full-length pulls the shot wide: to
show the boots, the model draws the feet.

## Porchlights ep02, three edit models, four shots (2026-11-12)

Shots sh140 (MS Crane), sh285 (MS Denise), sh170 (MCU Samir) and sh290 (CU Denise), each on
MiniMax-H3-Image, Qwen-Image 2.1 and FLUX.3 Klein, with the same seed for each variant (each
shot's takes were cleared first):

- **A**: the prompt as it is today;
- **B**: no design sentences;
- **C**: no design sentences, with the reference line cut to "Picture 1 is Denise Carter."

| | H3-Image | Qwen-Image 2.1 | FLUX.3 Klein |
|---|---|---|---|
| sh140, MS | B and C the same, a touch tighter than A | all the same | all the same |
| sh285, MS | B and C knees up, **wider** than A | B and C **full length in a raincoat**, wider than A | all the same |
| sh170, MCU | all the same | C tighter, head turned | all the same |
| sh290, CU | all close-ups; C's crop slightly lower | C slightly wider (chest up) | all the same |

What it shows:

- **Identity holds without "exactly as".** Crane, Denise and Samir are as recognisable in C as
  in A on all three models. The picture carries identity; the wording adds nothing these
  models need. The shorter line could be adopted, but it gains nothing either, so the prompt
  stays as it is (no golden churn for no gain).
- **Neither change tightens framing.** Most of the A keyframes were already the right size;
  where B and C differ from A, they are as often wider.
- **A design sentence also chooses the clothes.** Without Denise's ("navy blue scrubs with a
  grey thermal…"), Qwen drew her in the raincoat her reference shows, though the action says
  it's hung up. The design sentence tells the model which clothes this moment calls for, against
  the picture.

## So far

The content of a design sentence matters, not the reference wording. A design sentence should
name what the camera sees in most shots (face, hair, top half, the clothes of the moment) and
leave footwear and full-length detail out unless the story needs them. That is guidance for
AUTHORING.md and the script-writing skill. It has two cases behind it and isn't written in yet.

## Still open

- [ ] **A head-and-shoulders reference for MCU and CU:** a crop of the character's sheet, or a
      close-up reference made once per character (Ballroom's workaround, done for you), passed
      in place of the full-body sheet. Untested.
- [ ] **A case that shows the problem:** Ballroom's Charming and Cindy, medium and close shots,
      before and after the crop. Porchlights mostly framed right already.
- [ ] **Sheet panels at 1024 px rather than the target's `view_size`:** less detail per face,
      possibly related.
- [ ] **The design-sentence guidance** in AUTHORING.md (and so the skill), once the crop test
      shows whether it's still needed.
