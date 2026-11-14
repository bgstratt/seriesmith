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

## The video prompt: a medium drawn as wide as its plate (2026-11-12)

Porchlights ep02 sh1110 (MWS) and sh1115 (MS), Mills at a vending alcove, came out as the same
wide frontal framing as the alcove's plate, so the cut between them read as a jump cut.
`seriesmith check`'s jump-cut warning doesn't fire on them: MWS to MS is two size steps.

sh1115 on H3 Hybrid at its seed, one change each:

| Variant | Framing |
|---|---|
| A: as rendered | wide, the plate's own framing |
| B: the location's description cut to its name and light | **medium**, waist up |
| C: B, and "from the waist up" | medium, a little tighter |
| D: B, and a crop of the plate closer on the drink machine | medium, as B |
| E: no plate, the full description | **still wide** |
| F: the full description in the location's definition, the shot line naming the plate alone | **medium** |

The plate isn't what pulled it wide; the shot line was. A medium's line said "frames Mills in
<Subject 2>, a small hospital vending alcove ..., two glowing vending machines, one for drinks
and one for snacks, a water fountain and a trash can, showing the part of the space directly
behind them": an inventory, and to show all of it the model draws the room. The same lesson as
the boots above, from the location's side. So a medium (MS, cowboy, MWS) with a plate now names
the place by its plate alone in the shot line (`framing_sentence` in
`targets/video/minimax_h3_ref2va/prompt.py`, used by every Ref2VA-style target); the
description stays in the location's definition. Checked on sh140 (MS) and sh285 (MS), already
framed right: unchanged. sh1590 (cowboy): a little tighter. sh1110 (MWS) stayed wide: its own
action asks for the room ("in the little alcove, seen from a low angle in its glow").

No crop of the plate was needed. A close-up already names its plate alone; a wide still gets
the full description, which it should.

## The keyframe prompt: the same change (2026-11-12)

The keyframe prompt opened "the first frame of a medium shot of <the location's whole
description>" at every size. Now a medium or close keyframe whose plate is among its pictures
leaves the place to the plate's own line ("Picture 2 is the background plate ..."); one without
the plate keeps the place's first clause ("a small hospital vending alcove at night off a
corridor"); a wide keeps the full description (`keyframe_prompt` in `targets/image/common.py`).

Six Porchlights ep02 shots on MiniMax-H3-Image, Qwen-Image 2.1 and FLUX.3 Klein, A as before and
B with the change, at each shot's take-1 seed (the stable one):

| Shot | H3-Image | Qwen-Image 2.1 | FLUX.3 Klein |
|---|---|---|---|
| sh1110 MWS | about the same | the same | B wider |
| sh1115 MS | about the same | **B tighter** | **B much tighter** (A full-length in the room) |
| sh140 MS | B wider | the same | the same |
| sh285 MS | the same | the same | the same |
| sh170 MCU | **B tighter** | **B tighter** | **B tighter** |
| sh290 CU | the same | a touch wider | **B tighter** |

Again on sh1110, sh1115, sh140 and sh290 at take 2. A later take's seed is random
(`seed_source: new`), so A and B aren't paired there: sh1115 tighter on H3-Image and Qwen, sh290
tighter on Klein, the two losses above not repeated. Identity, clothes and the plate held
throughout. The keyframe models were less wrong than H3 video to begin with (H3-Image and Qwen
drew sh1115 roughly medium already), so the gain is smaller.

## Still open

- [ ] **A head-and-shoulders reference for MCU and CU:** a crop of the character's sheet, or a
      close-up reference made once per character (Ballroom's workaround, done for you), passed
      in place of the full-body sheet. Mostly there already (checked 2026-11-13): a close-up
      (`cu`, `mcu`, `ecu`) of one character gets the face panel on the keyframe
      (`refs._reference_parts`, the picked `04_face` take first) and on the video model (the
      targets' `face_sizes`, `panel_view`). Mediums keep the three-quarter body (the user: an MS
      is waist up, a face reference would fight it). Left: a close-up of two characters, or a
      character with a prop, still gets bodies; a one-picture sheet (`sheet_panels: 1`) is
      sent whole.
- [ ] **A case that shows the problem:** Ballroom's Charming and Cindy, medium and close shots,
      before and after the crop. Porchlights mostly framed right already.
- [ ] **Sheet panels at 1024 px rather than the target's `view_size`:** less detail per face,
      possibly related.
- [ ] **A picture check for jump cuts:** the two takes' frames either side of a cut, same people
      on the same plate, nearly the same framing (what the script check can't see from sizes).
- [ ] **The design-sentence guidance** in AUTHORING.md (and so the skill), once the crop test
      shows whether it's still needed.
