# Wardrobe, groups and vehicles

A reference for SKILL.md: a wardrobe change as a variant and how to cut round it, the same background people in several shots as a group, a blurred plate for a close-up, vehicles in motion. Read it when a character changes clothes, the same background people are seen twice, a vehicle moves, or a close-up needs nothing but blur behind the face.

### A wardrobe change is a new subject

A character's clothes live in their `design` sentence and in their
model sheet, so a character who changes clothes is a second subject with `of:` — a
**variant** — not a note in the action line:

```json
"gina": {
  "kind": "character", "name": "Gina", "design": "a woman in her forties, dark hair cut short, a grey mechanic's coverall over a black tee, steel-toed boots",
  "sheet": "refs/gina/gina_sheet_4panel.png",
  "voice": "low and dry, never hurried",
  "voice_sample": "audio/voices/gina_sample.wav"
},
"gina_towel": {
  "of": "gina",
  "design": "a woman in her forties, dark hair cut short and soaked flat, a white bath towel wrapped and tucked at the chest, bare feet"
}
```

A variant needs exactly two lines: `of:` and its own `design`. Everything else — `kind`,
`name`, `voice`, `voice_sample` — is inherited, so one character still has one
voice, and a `sheet` path is derived from the original's (`refs/gina/gina_sheet_4panel.png`
becomes `refs/gina/gina_towel_sheet_4panel.png`). Give it its own `sheet` line to put it
somewhere else. Generate that sheet like any other reference; starting from the original's
approved views holds the face far better than generating it cold.

In the script, name the variant where it is on screen and go on calling the character by
their name:

```
## sh120
who: gina_towel
size: medium
dur: 3.04
Gina leans out of the bathroom door, one hand on the frame.
GINA (low): Don't come in.
```

`who:` takes the variant; `GINA:` still speaks, and the line is given to whichever of her is
in the shot. A shot names one or the other, never both, and never two variants of the same
subject — cut the shot where the change happens.

**Why not a `wear:` line on the shot?** Because the reference sheet would still show the old
clothes, and the prompt would have to argue with the picture. H3 preserves a subject as a
whole — its `fully_preserved` marker covers face, hair, proportions *and* wardrobe — so the
only way to contradict the sheet is to weaken the whole subject, which loosens the face in
order to change the clothes. A variant keeps the identity lock and swaps the picture. It also
costs nothing on the other targets: LTX-2 and Wan have no reference images and read the
`design` sentence, which is already the variant's.

A variant is for a state a shot is *in*, not a change it *makes*.

### Never show the change itself

No video model today can take a hat off, pull on a glove or shrug out of a jacket and keep it
off. The item comes back, doubles, or melts into the hands, and the next shot puts the sheet's
version straight back on him. So **a shot's wardrobe is fixed from its first frame to its last,
and it is what the subject's sheet shows.** Don't write dressing or undressing into an action
line: not taking off a hat, gloves or glasses, not hanging up a coat, not stepping into
coveralls or tying on an apron. Small things matter most, because they are the easiest to
forget. A mesh glove pulled off in one shot is back on in the next, because nothing told the
next shot it was gone.

When the story needs the change, cut around it:

- **Start it, then cut.** Show only the beginning (his hand going to the brim, fingers on the
  zipper) and end the shot there. The next shot is already in the new state.
- **Land on an insert.** Cut to the item or the hands, not the face: the hard hat held against
  his chest, framed below the chin, or a bare forearm hanging the navy jacket on a locker hook.
  Make the item a prop (`with: hard_hat`) and keep the character out of `who:`, or frame it
  tight enough that only the hands show. An insert has no face to drift and needs no new sheet.
- **Cut away.** Go to the other character's line or reaction, then come back to the variant.
- **Change off screen.** End one scene in the old clothes and open the next in the new ones.
  Luis walks into the locker room in his jacket, and the next scene finds him on the line as
  `luis_plant`.
- **Don't change at all.** The gesture is often not needed. Glasses can be looked over or
  pushed up instead of taken off, and a man can fold his hands and wait with his hat still on.

Once the new state is on screen it holds. Every later shot of that character names the
variant until another cut brings the old clothes back, so add the variant (a design sentence
that says how he looks now: "bareheaded, a hairnet over short grey hair") before writing the
shots that need it. Its sheet is an edit of the original's views, so it's cheap.

For example, the hat coming off in Kemp's office. Written as an action, the hat is on again
two shots later:

```
## sh320
who: luis_plant
Standing just inside the door, Luis takes off his hard hat and holds it in both hands, ...
```

Instead, let Kemp's shot before it be the cut-away, and have Luis enter his next shot already
bareheaded, holding the hat as a prop:

```
## sh320
who: luis_plant_bareheaded
with: hard_hat
Standing just inside the door, Luis holds his hard hat in both hands against his chest, ...
```

and every later shot of him in the office is `luis_plant_bareheaded` too.

**When the room still shows behind a close-up.** The blur is words, and the model follows the
plate's picture more than the prompt: a sharp plate still comes through, windows and candles
and all. For a close-up that must have nothing behind the face but soft bokeh, make its
background yourself:

1. Find where the subject's head sits in the plate (behind Cindy, the open doorway; behind
   Charming, the fireplace wall).
2. Crop a patch of the plate there, in the frame's shape: about an eighth of the plate's
   width for an `ecu`, a fifth for a `cu`.
3. Scale it up to the render size and blur it heavily, until nothing in it has an edge.
4. Give it a location of its own, an angle of the place (`of:`), with a description that names
   nothing in it, and name it with `plate:` on the shot:

```json
"hall_bokeh_cindy": {"of": "hall",
                     "description": "a magnified, completely out-of-focus crop of the background behind the subject: a soft wash of grey daylight framed by dark shadow, nothing recognizable",
                     "plate": "../refs/_bg/hall_bokeh_cindy.png"}
```

Don't name the room's things in that description (the fireplace, the door), even out of
focus: on H3 the words were drawn as a sharp room over the blurred picture. A plate that is
only a blurred patch can't show where someone stands in a two-shot, so keep it to singles.

### Vehicles in motion

A moving vehicle with a loose description wanders: it swerves toward the people in frame,
speeds up when it should stop, and smears.

- **Give it one clean path**: direction across frame, lane and speed. "The pickup rolls slowly
  left to right in the near lane, never leaving the road."
- **Arriving and getting out are separate shots.** One shot drives in; the next opens with the
  door already opening.
- **Parking is its own beat**, and the shot starts with the vehicle already slowing. Say where
  it stops, so the next shot can pick up from there.
- **Inside, a cab is a location with angles.** Its plate decides which way everyone faces, so
  give it one per kind of shot: the driver from the passenger seat (his window and the
  ridges sliding past behind him), the windshield from outside on the hood (both front seats
  facing camera), the back seat looking forward (both heads, the road ahead). The view
  forward out of the windshield is for a POV or a shot from behind, never a face.

### A group: the same extras every shot

`extras:` people are invented fresh every shot, so they change sex, size and colour from
cut to cut. When the same people recur in two shots or more — the clerk behind the register,
the ladies watching from the edge of the ballroom, a family at the next table — take them out of
`extras:` and give them a picture. One person is an ordinary character with a sheet (`name` can
be "the night clerk"). Several are one **group** subject: a character with `members`, whose
picture holds all of them. `seriesmith check` warns when two shots' `extras:` name the same
people (however alike the words: the same words twice mean the same people, and the model
still draws new ones), and says which to make. That goes for a crowd too: the lunch table's
three workers, the day-shift nurses round the station. Make the ones the camera sees clearly a
group subject, and leave only far-off, blurred people in `extras:`.

```json
"ladies": {
  "kind": "character",
  "name": "the ladies",
  "members": 4,
  "design": "four young women in Regency ball gowns: one in pale blue with dark curls, one in rose with a feathered headband, one in white with red hair, one in green silk with long gloves",
  "sheet": "../refs/ladies/ladies.png"
}
```

Cast it like anyone else (`who:` or `with:`), in every shot they're in, and drop them from those
shots' `extras:`. It takes one slot however many people it holds (H3 has eight besides the
plate): two named characters and a group of four is three subjects, six people who stay the
same. The prompt defines it as a picture of N
different people and counts its members in the shot's headcount ("Exactly six characters
appear in this shot: <Subject 1>, <Subject 2> and the four members of <Subject 3>"), which
is what keeps H3 from drawing the same woman twice. Put where they are in the action text
("the ladies watch from the far wall, soft in the background").

- **The picture is one whole image** of all of them (`sheet_panels: 1` is implied; a group is
  never a four-panel sheet). Generated, it is a row of everyone head to feet, apart and facing
  the viewer, at the plate's size. A picture you supply works the same way; keep every face
  and outfit visible, since a person half-hidden in the reference is one the model invents.
- **Describe each member** in `design`, with differences in age, build, hair and colour. A group
  of four identical gowns is read as one person four times.
- **A group that isn't people** says what its members are: `"members_are": "horses"` (a team of
  horses, a flock of geese). Every prompt calls them that instead of "people"; left out, a
  pair of carriage horses is drawn with a driver beside them.
- It works on every target. H3 Ref2VA defines it in the headcount. LTX-2, Wan and H3 from
  keyframes call it "N different people, each appearing once" in their prose, and their
  reference sheets carry its picture whole, never cut to one panel.
- A group can speak (`voice` is one voice for all of them: a murmur, children giggling).
- Twelve is the limit. A crowd bigger than that belongs in `extras:`.

Two habits go with it. **Keep people out of the plate**: a location described as "full of
masked dancers" is rebuilt as figures that compete with the subject and feed the duplication
— describe the empty space and let the far background fall off into bokeh. And **name the
subject in the camera move**: "arcs around them" leaves the model to decide who "them" is.

**Extras in the lead's wardrobe take the lead's face.** The prompt already tells H3 the extras are
strangers, each with their own face, build and clothes, but twenty white smocks and hard hats around a man in a white
smock and hard hat still turn into twenty of him. When the extras share the lead's uniform,
vary them in `extras:`: men and women, different ages and builds, hairnets instead of hard
hats, faces turned away or soft in the background.

Add a prop to `with:` only when its exact design matters and recurs. A generic mug is better
described in the action text, because every referenced prop spends a slot.
