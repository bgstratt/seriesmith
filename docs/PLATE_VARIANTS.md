# Plate variants: a closer part of a plate for medium and close shots

Status (2026-11-12): **built**; the Refs tab's view of a crop still to check. This file is the
design record and the checklist.

## Why

A video model given a plate takes it as what the place *is*, not as what the camera sees: H3
Ref2VA encodes a plate as it encodes a character, an identity to keep, and draws a new picture.
Asked for a medium shot in front of a wide establishing plate, it either keeps the plate's
framing (the whole room, the person small in it) or, told less about the room so it frames
closer, invents what fills the closer view, and on some seeds pulls that from a character's
sheet. Porchlights ep02 sh1115, four seeds by four prompts (docs/KEYFRAME_FRAMING.md):

| Prompt | Framed as a medium | Problems |
|---|---|---|
| the full description | 0 of 4 | none |
| the plate alone in the shot line | 3 of 4 | an artifact, a changed place |
| the place's first clause | 3 of 4 | an artifact |
| a centre crop of the plate, and the first clause | **4 of 4** | none (one seed went to the corridor beside it) |

Given a picture that already is the closer view, the model has nothing to invent. It's the same
lesson Ballroom taught for reverse angles: a speaker facing the other way needs a plate of that
view (an angle), not words asking for it.

## What it is

A **crop** is a location of its own, beside its master, as an angle or a relit plate is:

```json
"vending_alcove_drinks": {
  "of": "vending_alcove_night",
  "crop": "left",
  "description": "the drinks machine and the water fountain of the vending alcove"
}
```

- `of`: the location it is a part of (a master, an angle or a relit plate: anything with a plate).
- `crop`: which part: `center`, `left`, `right`, `top`, `bottom`, `top-left`, `top-right`,
  `bottom-left`, `bottom-right`.
- `zoom` (optional): how much closer, 1.2 to 3; 1.6 when left out (about the middle 60% of the
  plate, what sh1115 was tested at).
- `description` (optional): what that part shows; the master's when left out.
- `plate` (optional): its picture. Left out, it's `refs/_bg/<id>.png`.

The **writer decides** (a person, or the script-writing skill): when a run of medium or close
shots plays in one part of a wide plate, that part becomes a crop, and those shots name it with
`plate:`. Nothing is cropped behind the writer's back; a wide shot keeps the whole plate.

## Its picture

- **Made by seriesmith**, when the crop's picture isn't there: the master's plate cut to that part
  and enlarged to the plate's size (Pillow, no model), before a render or a keyframe needs it,
  and from the Refs tab. A record beside it (`<id>.crop.json`: the master's sha1, the crop, the
  zoom) says what it was made from: when the master's plate changes, or the crop or zoom does,
  it's made again.
- **Or yours**: a picture that isn't the one seriesmith made (its sha1 isn't the record's) is
  kept and never replaced. Made by hand, or as an edit of the master in the Refs tab (an angle's
  generate, told which part).
- A crop of a crop isn't one: `of` names a location with a plate of its own that isn't a crop.

## Checklist

- [x] The series config: `crop` and `zoom` on a location with `of`, checked; its description
      and plate filled in from the master (`core/series_config.py`: `CROPS`, `crop_box`).
- [x] The picture: made when missing or out of date, kept when it's yours (`plates.py`), at the
      end of a build (`seriesmith build` prints each one), before a render (the command and
      `POST /seriesmith/render`) and before any ref generation (`refs.queue_generate`: a
      keyframe's plate).
- [x] Generate in the Refs tab: an edit of the master told which part, how much closer
      (`refs.built_prompt`).
- [ ] The Refs tab: check a crop shows as a location with its picture (it's one like any other).
- [x] AUTHORING.md (and so the skill): **Medium and close shots get a crop of the plate**.
- [x] Live (2026-11-12, Porchlights ep02 on a scratch copy, H3 Hybrid): sh1115 (MS) on
      `alcove_drinks` (left, 1.6): waist up between the drinks machine and the fountain, clean,
      at its stable seed and at the seed that grew a jacket on the machine with the plate-only
      prompt and black shapes with the first clause. sh1110 (MWS) on a looser crop (left, 1.3):
      knees up, bending to the tray, seen from the side with a corridor door behind; clean.
      The cut between them is no longer a jump.
- [ ] Live: a Ballroom close-up on a crop of an angle.
