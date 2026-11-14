---
name: seriesmith-episode-script
description: Write episode scripts and series configs for seriesmith, the script-to-episode AI video pipeline, fresh or converted from an existing screenplay. Covers the epNN.md script format (sequences, shots, ALL-CAPS dialogue, who/with/size/dur/plate/camera/sound fields, continuity and keyframe lines) and the series config (series.json) with what's required, what each optional block defaults to, the cast, locations, look, voices, profiles, render size and master recipe. Shots render on a video model per shot or episode (MiniMax H3, LTX-2, Wan 2.2, Seedance and others). Use it whenever the user wants to write, outline or extend an episode, pick a story structure, start a series, break a screenplay or scene into shots, add characters, props or locations to a series config, choose which model renders a shot, re-time shots whose dialogue doesn't fit, or fix a script seriesmith check rejected, even if they never name seriesmith or the file formats.
---

# Writing an episode for seriesmith

You are writing for seriesmith. Follow this format exactly: the output is compiled
by `seriesmith build`, and anything that does not match is a build error, not a style
preference.

Before writing anything, ask for the series config (`series.json`) if the series has one.
Adding a character means adding to that file, not inventing a new one: if you write `riley`
when the series config already has `riley_freeman`, every reference path breaks. An existing
series config is the show's: add what the episode needs and change nothing else unasked (if
it has no `upscale.master` block, say once that it can't be mastered by recipe until it has
one). With no series config yet you are starting a series: write both files,
and read `references/series_config.md` first. It says what to settle before the first shot
(ask what the brief doesn't say, in one message) and the defaults to use, and to list, when
the person would rather you just start.

Converting an existing screenplay, keep its story and dialogue and break it into shots
(`references/script_conversion.md` works a scene through). Writing fresh, outline the story
before the shots: if the person hasn't given it a shape, offer the menu in
`references/story_structures.md` (with the questions about the series, in the same message;
if they'd rather you just start, pick one from it and say which and why in a line).
Either way, mark the structure and each beat in the script (`// structure:` near the top,
`// beat:` above each beat's first shot; the structure that fits a converted screenplay
best), so the score can be drafted from them (that file's **From beats to shots**).

Write the film, not the model. Leave `target:` lines out unless a shot needs something only
one model does (`references/models.md`); advice that holds for one target only is marked
with that target's name.

Validate before calling a script finished, with the first of these you have: seriesmith's MCP
tools (`check_pair` for a series config and a script not on disk yet, `check_source` for an
episode's, `preview_shot` for what one shot would render); the command `seriesmith check
<episode folder>`; this skill's `scripts/check.py`. Fix what it reports and check again until
it is clean. Rendering, upscaling and mastering are the person's to run, not part of
writing.

## Your first episode

Two files in one folder — and `seriesmith new Shows\ep01` writes both of them for
you (so does **New episode…** in the editor's project folders). This is what it writes,
and it is also `examples/starter/`, so you can read it before you run anything.

`Shows\ep01\series.json` first. `audio.mode: generate` means the model invents the
voices from each character's `voice` line, so nothing has to be recorded first. The
pictures are named `../refs/...`, one level up: that way every episode of the show
shares one `refs` folder while each keeps a series config of its own (a config in the
episode wins, the one beside it is the fallback), which is what lets episode four add
a character without touching the first three.

Every file a series config or script names (a picture, the recording, a theme, a title
clip, a font of the show's) is inside the show (the folder holding its episodes) or a
project folder; a path that leads anywhere else is refused when it's used. A file from
elsewhere on the PC comes in by importing it, which copies it into the show. A title font
may also be one of this machine's own.

The folder can be called anything — `ep01` here, but `s2ep01`, `s3ep07` or `pilot`
just as well, which is how a show with seasons keeps them apart. Name the script
after the folder (`s2ep01\s2ep01.md`) and everything finds it: that is the only
name that still works when the episodes share one `series.json` in the folder above
them, and it is what lets `seriesmith build Shows --each` pick up every episode
under a show at once.

```json
{
  "series": {
    "id": "first_light",
    "title": "First Light",
    "fps": 24,
    "width": 1344,
    "height": 768
  },
  "proxy": { "width": 896, "height": 512 },
  "style": {
    "look": "a 2D hand-drawn cartoon animation with flat 2D illustration, clean black line art, flat solid colors, and cel-shaded artwork"
  },
  "subjects": {
    "ada": {
      "kind": "character",
      "name": "Ada",
      "design": "a nine-year-old girl with short curly black hair, a green raincoat, and yellow rain boots, drawn with thick confident outlines",
      "sheet": "../refs/ada/ada_sheet_4panel.png",
      "voice": "bright, quick, a little breathless"
    },
    "lantern": {
      "kind": "prop",
      "name": "the porch lantern",
      "design": "a dented brass hurricane lantern with a smoke-stained glass chimney and a wire handle",
      "sheet": "../refs/props/lantern.png"
    }
  },
  "locations": {
    "porch": {
      "description": "a wooden front porch at dawn, wet boards, a hanging lamp still lit, mist over the lawn beyond",
      "plate": "../refs/_bg/porch.png"
    },
    "porch_lamp": {
      "of": "porch",
      "crop": "center",
      "zoom": 1.5,
      "description": "the wet porch boards and the hanging lamp by the door, mist beyond the rail"
    },
    "porch_lamp_close": {
      "of": "porch",
      "crop": "center",
      "zoom": 2.2,
      "description": "the porch wall and the hanging lamp, close"
    }
  },
  "audio": { "mode": "generate" }
}
```

`Shows\ep01\ep01.md`:

```
= ep01  First Light

# sq01  porch

## sh010
who: ada
size: wide
dur: 3
Ada steps out onto the wet porch and stops, looking at the mist on the lawn.
camera: holds a static wide shot
sound: dawn birdsong, dripping water, a faint breeze

## sh020
who: ada
with: lantern
size: medium
plate: porch_lamp
dur: 4
Ada lifts the lantern off its hook and turns the flame down until it gutters out.
camera: holds static
sound: a metal hook ringing, the soft pop of a flame going out

## sh030
who: ada
size: close
plate: porch_lamp_close
dur: auto
Ada grins and pulls her hood up, her eyes out over the lawn, off to frame left.
camera: pushes in with small amplitude at slow speed
ADA: It rained all night and nobody saw it but me.
sound: rustling raincoat, dripping water, distant birds
```

Build it with `seriesmith check Shows\ep01` and then `seriesmith build Shows\ep01`.

> **Read `references/series_config.md`** when writing a new `series.json` or any block of one besides `subjects` and `locations`, relighting a plate, or marking a cold open. It holds **Starting a series: what to settle first**, **Render size and delivery**, **The master recipe: `upscale.master`**, **Post-process: the `post` block**, **Series intro and outro: the `publish` block**, **Render profiles**, **Reference images and voices: the `refs` block**, **The episode's sound: the `sound` block**, **Negative prompts**, **Writing the `look` line**, **What a place sounds like: `ambience`**, **A cold open: `cold_open:`**.

## The one thing that shapes every decision

A screenplay is read once, front to back, by someone who remembers. A shot list is consumed
**once per shot, independently, by a model with no memory**. Shot 94 knows nothing about
shot 93. So:

- Every shot's action must stand on its own. "He keeps walking" means nothing — write
  "Riley walks down the dirt path, already halfway along."
- Never write "as before", "same as the last shot", "still holding the ball". State it fresh
  or it does not exist.
- Character descriptions live in the series config, written once, injected into every prompt they
  appear in. Never repeat a character's appearance in the script.

> **Read `references/models.md`** when the series config or a shot names a `target:`, or the person asks which model to use. It holds **Choosing a video target**, **Which model a shot renders on**, **Rendering a shot on LTX-2**, **Rendering a shot on LTX-2 with its refs: `target: ltx2_ingredients`**, **Rendering a shot on LTX-2.5 with several people's pictures: `target: ltx2_msr`**, **Rendering a shot on H3 from keyframes: `target: minimax_h3_fl2va`**, **Rendering a shot on Wan 2.2: `wan22_i2v`, `wan22_ti2v`, `wan22_vace`**, **Keyframes: `first:` and `last:`**, **A picture held still: `target: hold`**, **Rendering a shot on a hosted model: Seedance, Kling, Veo, …**, **Letting the model time a shot: `dur: model`**.

## The series config: series.json

- `style.look` opens every shot's description ("The target video is …"), so it sets the
  photography of the whole series. See **Writing the `look` line**.
- `kind` is `character`, `prop` or `vehicle`. Only characters speak.
- A character's `sheet` is a **four-panel strip** (three-quarter body, side, back, face),
  and a shot gets one panel of it: the three-quarter body, or the face on a one-character
  close-up. A picture you supply that is **one image** of the character (a portrait, a
  full-length shot on white) needs `"sheet_panels": 1`, or it is cut into quarters and the
  model gets a strip from its left edge. With it the picture is sent whole on H3 Ref2VA.
- **No picture yet.** A location with a `description` and no `plate`, or a subject with a
  `design` and no `sheet`, is described **in words** on H3 Ref2VA: it takes no Picture slot
  and nothing waits for a picture. That's fine for a one-off clip or a first try, but a
  series stays consistent through its pictures: without one, each shot imagines the place
  or the person its own way. Add the `plate` / `sheet` (and make the picture) when it
  should look the same every time.
- `members` makes a character a **group**: one picture of that many people (2–12), cast
  like any character and costing one slot. See **A group: the same extras every shot**.
- `of` makes the subject a **wardrobe variant** of another one — the same character in
  different clothes, the same prop in a different state. See **A wardrobe change is a new
  subject**.
- `audio.mode` sets how dialogue shots sound: `clone` (the model speaks the written lines in
  each character's sampled voice, their `voice_sample`), `source_track` (you supply a recorded mix, `audio.track`,
  and shots dub to it; see seriesmith's recorded dialogue guide) or `generate` (the default: the model
  invents the voices from each `voice` line; no recordings or samples needed).
  `proxy.audio_mode` can use another mode for the animatic (`generate` is the usual one),
  `audio.default_policy` forces one policy for every dialogue shot, and `audio.retention`
  sets the dub `retention:` default. A target that can't do a mode says so and generates.
  For a song as the recording, `audio.dub_from: "vocals"` sends each dub shot's window from
  the song's vocal stem instead of the whole mix (optional; off by default; see
  seriesmith's recorded dialogue guide).
- `series.width` / `height` and the `proxy` block: see **Render size and delivery**.
- `steps`, `lora` and `model` are optional per pass (the model's own otherwise). `lora`
  takes one LoRA or a chain, as the script's `lora:` line does
  (`"lora": "turbo_8step.safetensors, soft_light.safetensors:0.6"`).
- `series.target` names the video model the episode renders on (one of the ids in
  **Choosing a video target**). Leave it out unless they want one in particular: the series
  then renders on this machine's default. `series.backend` says where its jobs run
  (`local`, `cloud`, `deployment:<target>`, `router`), else each model's own.

**Required and optional.** A series config must have `series` with an `id` and a `title`,
`style.look`, and `subjects` and `locations` blocks (either may be empty); every subject a
`name` and a `design` (or only a `voice`, for someone who is never seen), every location a
`description`. Everything else is optional, and left out means:

| Key | Left out |
|---|---|
| `series.fps` | 24 |
| `series.width` / `height` | the model's own (1344×768 on H3) |
| `proxy` | the model's own proxy (512×288 on H3: too small; write one) |
| `series.target` | this machine's default model |
| `audio.mode` | `generate` (`source_track` when `audio.track` names a recording) |
| `speech.pace` | `normal` |
| `refs` | Krea 2 for pictures, LTX-2.5 for voices |
| `upscale.master`, `post` | no recipe: the episode can't be mastered by recipe |
| a subject's `sheet`, a location's `plate` | described in words only (fine for a first try) |

### Writing the `design` sentence

This is the highest-leverage sentence in the pipeline. The model sheet is generated from it,
and a model that gets no picture of the character draws them from it alone. Where the sheet
goes with the shot, H3 Ref2VA's prompt names the character by their picture and leaves the
sentence out: the sheet already shows it, and wardrobe listed in words gets drawn whether the
framing has room for it or not. Other models get the sentence beside the picture.

Describe **what a model sheet artist could draw**. Age and build, silhouette, hair, wardrobe
with specific colors, one or two distinctive accessories, line quality. Concrete nouns.

Weak: *"a mischievous kid with boundless energy who never sits still"* — none of that is
drawable, and it crowds out detail that is.

Lead with who they are (*"a young woman"*), then hair, then wardrobe and accessories; keep the
body to build and silhouette (*tall*, *stocky*, *slight*). A design that leads with clothes
and hair reads the same on every model, a hosted one behind its provider's filter included.

Location descriptions work the same way and must include the light: time of day, direction,
quality. The plate is generated from that sentence. **Name the sources**: the pendant lamp
over the table, the chandeliers, the TV's glow, the streetlight through the blinds. A room
lit by things you can point at renders as a lit set, with pools of light and shadow
between them; "warm lighting" renders as an evenly lit showroom.

### A location is one angle, not one place

One plate per location means every cut rebuilds the same view, and characters appear to pop
into an unchanged picture instead of being discovered by a camera. Author two to four angles
per place and let each shot name its own with `plate:`:

```
office_desk    the desk against the wall, bulb overhead
office_lid     looking up at the propped lid and the moonlight
office_boxes   the wall of file boxes
office_wide    the whole interior at once
```

**Time of day is part of the location.** `street_day` and `street_night` are two entries with
two plates, because the plate carries the light. (A plate can also be made from another by
relighting it: a location with `of:` and `relight:`.)

**Write the angles as one place.** Each plate is drawn from its own `description`, so unless
those sentences share fixed features they describe several rooms with the same name rather
than one room from several sides. Anchor every angle to the same things: *"the kitchen from
the hallway door, sink under the window on the left, the living-room arch behind camera"* and
*"the kitchen from the sink, the hallway door on the right, the arch beyond it"*. That is what
makes the geography hold together across a cut.

**Tie the angles to one master with `of`.** Words alone still give each angle its own
walls and furniture. Give one entry the plate you like (the master) and mark the others as
angles of it:

```json
"ambulance_bay_night":    {"description": "the ambulance bay of a county hospital at night ...",
                           "plate": "../refs/_bg/ambulance_bay_night.png"},
"ambulance_bay_on_drive": {"of": "ambulance_bay_night",
                           "description": "looking back down the covered drive from the doors ...",
                           "plate": "../refs/_bg/ambulance_bay_on_drive.png"}
```

- An angle inherits nothing. It keeps its own `description` and `plate`, and shots still name
  it with `plate:`.
- On an edit model (Klein, Qwen, Rapid AIO, H3 still), an angle's plate is generated **from
  the master's plate**: the same building, materials and light, with only the camera moved.
  On a text-to-image model (Krea 2) it is drawn from its words as before.
- An angle's master must be a location that isn't itself an angle.

### Medium and close shots get a crop of the plate

A video model takes a plate as what the place *is*, not what the camera sees. In front of a
wide establishing plate, a medium shot comes out as wide as the plate, or, told less about
the room, the model invents what fills the closer view. Give it the closer view as a picture:
a **crop**, a location that is one part of another's plate, closer.

```json
"vending_alcove_drinks": {"of": "vending_alcove_night", "crop": "left",
                          "description": "the drinks machine and the water fountain of a small hospital vending alcove at night"}
```

- `crop` says which part: `center`, `left`, `right`, `top`, `bottom`, `top-left`, `top-right`,
  `bottom-left` or `bottom-right`. `zoom` says how much closer, 1.2 to 3 (1.6 when left out):
  the crop keeps 1/zoom of the plate's width and height, centred on that part.
- `description` says what that part shows; left out, it's the master's. Its picture is made
  from the master's plate, cut and enlarged, when you build or render (**Upscale** on its row in
  the Refs tab gives it the detail a stretch can't); `plate` names it if you want it somewhere
  else. A picture you put there yourself (or make in the Refs tab with an edit model) is kept.
- A crop's master may be an angle or a relit plate, not another crop: crop the master with a
  larger `zoom` instead.

seriesmith never crops by itself: the script decides. Go through every medium and close shot:

1. **Every `ms`, `mws`, `cowboy`, `mcu` and `cu` gets a crop**, unless its plate is already that
   close: a location whose description is one thing filling the frame, just what is directly
   behind a person at that size (a door, a counter seen from a stool, the wall behind a desk
   chair). **An angle is not close because it is an angle**: an `_on_` location whose description
   names a whole wall, a room's corner, a car seat with the dash and windows, a row of pews, or
   more than one or two things, is wide for a medium shot. Go by what the description says it
   shows, not by its name; when in doubt, crop. Mark a location that is already close
   `"framing": "close"` (or `"medium"`): `seriesmith check` warns about every medium and close
   shot on a wide location's whole plate (and the Refs tab badges the place **uncropped**),
   and a location marked so, or a crop, is never flagged.
2. **The zoom follows the size**: `mws` and `cowboy` about 1.4 to 1.5, `ms` 1.5, `mcu` and `cu`
   2.2 (2.0 when 2.2 would cut away the thing the person is at: the door, the desk, the pump).
   A plate with both medium and close shots in one part gets two crops of that part, one for
   each (`<master>_<part>` at 1.5 and `<master>_<part>_close` at 2.2): a close-up on the 1.5
   crop comes out medium.
3. **The part is what is behind the person**: where they stand or sit in the plate, so the crop
   keeps the thing the action puts them at (the door they wait by, the desk they lean on).
   Take it from the words: the location's description ("the office door on the right", "the
   drinks machine on the left") and the shot's staging; when neither says where the thing is,
   `center`, which is where a plate's subject usually sits. Shots in different parts of one
   plate get different crops.
4. **Two people facing each other** never share a crop: each gets a crop of their own angle
   (**Two people talking need an angle each**), or of another part.
5. **Keep the full plate** for wide shots (`ws`, `fs`, `ews`); `ecu` inserts of hands, papers and
   screens, where the object fills the frame; a shot the action composes against the whole
   view ("small on the left third, the pickup on the right", "walks toward camera down the
   corridor"); and a plate that is what the person looks at rather than what is behind them.
6. **Ids are the show's, not the episode's**: crop pictures live beside their master in the
   show's `refs/`, so an id another episode already uses for a different crop (another part or
   zoom, or a master with another plate) needs a different id.
7. **Give each crop a `description` of what that part must show** ("the green side door with its
   padlock and the brick around it"): it says what the crop is for, and lets whoever builds the
   episode check it. Each crop is cut at the build and shown on its row in the Refs tab; one that
   shows only wall, floor or sky, or misses what its description names, has the wrong part or too
   much zoom: move the part or lower the zoom. Working from the script alone, without the
   pictures, say so when you hand it over, so the crops get that look. A crop without one
   speaks with its master's description, and an insert (a close shot of a thing, no one in
   it) names its place by the first clause, up to the first comma: start the crop's
   description with the thing itself ("close on the cracked dashboard of an old pickup
   truck, its air vents and an old radio"), not with the room it's in.

### Two people talking need an angle each

This is the one that spoils scenes most often, and the build warns about it.

One plate is one picture. Two singles built on it are drawn against the same background from
the same view, so cutting between them looks like one locked-off camera that people step into
and out of — not a conversation. No wording fixes it, because the plate is a picture and the
prompt is only words.

Author the scene as three entries and name one per shot:

```
cafe_couch          the whole seating area, both of them in it — the establishing shot
cafe_couch_on_skye  past Walter's shoulder to Skye on the left of the couch, window behind her
cafe_couch_on_walt  past Skye's shoulder to Walter in the armchair, the counter behind him
```

```
## sh768
who: skye, walter
plate: cafe_couch
size: medium
dur: 3.04
They settle in with their cups.

## sh772
who: skye
plate: cafe_couch_on_skye
size: close
dur: 2.33
Skye looks up over the rim of her cup, her eyes off to frame right.
SKYE: You're early.
```

**Keep them on one side of the line.** Decide who sits on which side and keep it: if Skye is
on the left of the two-shot, she stays screen-left in her single and looks off to frame
right, and Walter looks off to frame left. Write that into the **action** line — *"her eyes
off to frame right"*, *"he answers with his head bowed, his eyes down and to frame left"*.
There is no field for it; the action sentence reaches every target's prompt and is where a
real script would put it anyway. Without it a model does what it was trained to do and talks
to the camera. Say only where the eyes go: "not at the camera" puts the camera in the prompt,
and the model turns to it (see **Say what is there**).

The same applies to a character alone in a room who is meant to be aware of someone off
screen: say where they are looking. `seriesmith check` warns about a single whose one person
speaks and whose action never says where they look.

**An eyeline is a direction, never a person.** In a single, the one being spoken to isn't in
the shot, so don't name them in it: write where the eyes go, "looking off to frame left", not
"looking off to frame left at Junior", "at him" or even "at Junior, who is out of frame". The model draws whoever the words mention, wherever the sentence puts them.
The same goes for anyone the action reaches toward or stages ("holds up a hand to stop her at
the foot of the steps", "slides the folder toward him") or puts where the frame can see in
passing ("her shoulder soft in the foreground", "past her"): say the gesture and its
direction ("holds up a flat hand off to frame right"). In one H3 test, a single of Earl,
"looking off to frame right down at her", with no one else in `who:`, got an invented girl
in a plaid bow. Who they're looking at is the cut's job: the reverse shot shows them. If the
shot really does hold both people, put both in `who:` (an over-the-shoulder is `size: ots`),
and then naming them is right. `seriesmith check` warns when the action names a character
who isn't in the shot's `who:`.

### Say what is there

A video model attends to every word of its prompt, and most have no negative prompt to steer
away from anything. A thing named in order to forbid it is still
named: "no photographs on the wall" hangs the wall with photographs, "never looks at the
camera" turns the head to it, "without a cut" asks for a cut. Say what is there instead:
"bare plaster walls", "her eyes off to frame left", "one unbroken take". This holds for
every line that reaches a prompt: a shot's action, `camera:`, `extras:` and `sound:`, and
the series config's look, the designs and voices of the people in the shots, and the
locations' descriptions. `seriesmith check` warns about each such phrase ("no", "not",
"never", "without" and the rest, passing over "no more than" and its like).

Words someone says go in a dialogue line, never in quotation marks in the action (`Ada says,
"Run."`): a line is what the model voices and the cut times. `seriesmith check` warns about
quoted words with a speaking verb in the action; quoted lettering (a sign that reads "OPEN")
is left alone, though on-screen lettering has its own field, `text:`.

**Clothes are fixed within a shot.** They come from the character's `design` and sheet, so
"takes off his hat" or "pulls on her coat" can't be written as action: a character who
changes is a second subject (a variant), and the change itself is cut round.

> **Read `references/people.md`** when a character changes clothes, the same background people are seen twice, a vehicle moves, or a close-up needs nothing but blur behind the face. It holds **A wardrobe change is a new subject**, **Never show the change itself**, **Vehicles in motion**, **A group: the same extras every shot**.

## The script: epNN.md

```
= ep01  The Gold Path

# sq01  street_gate

## sh010
who: huey
size: wide
dur: 3.04
Huey drifts to a stop at the edge of the yard and looks off down the empty street.
camera: pushes in on him at slow speed
sound: late-afternoon suburban ambience, distant birds, a faint breeze

## sh020
who: riley, huey
with: backpack
size: medium
dur: 4.46
plate: street_yard
Riley runs into frame from the left and pulls up hard beside Huey.
Huey does not turn his head.
camera: arcs around behind them with small amplitude at slow speed
RILEY (breathless): There's gold at the end of the path.
HUEY (flat): There is not.
MOM (V.O.): Shoes off in the house!
sound: running footsteps on grass, fabric movement
```

| Line | Meaning |
|---|---|
| `= id  Title` | episode header, once at the top |
| `# sqNN  location` | sequence; the location must be a series config key |
| `## shNNN` | a shot. **Every `##` is a cut** — no `CUT TO:` needed |
| `who: a, b` | characters on screen, in this order (on H3 Ref2VA they become `<Picture 1>`, `<Picture 2>`, … in it); `cast:` is the same |
| `with: x, y` | props and vehicles, after the characters; `props:` is the same |
| `size: mcu` | shot size, from extreme close-up to extreme wide (`ecu`, `cu`/`close`, `mcu`, `ms`/`medium`, `cowboy`, `mws`, `fs`/`full`, `ws`/`wide`, `ews`), or an angle (`pov`, `ots`, `low`, `high`); the full names work too. Opens the shot's prompt as its framing ("A medium close-up frames… from the chest up"), and decides how much of the location and of the sheet is used. See **Faces need room** |
| `plate: street_gate` | this shot's angle; defaults to the sequence's location |
| `dur: 3.04` | duration in seconds, from the grid below (`duration:` is the same) |
| `dur: auto` | derive the duration from the dialogue at this shot's pace |
| `dur: model` / `dur: model 3-8` | let the video model choose the length when it renders, optionally between 3 and 8 seconds; see **Letting the model time a shot** |
| `audio: 3.10-7.40` | window on a locked dialogue mix; sets the duration instead |
| `pace: slow/normal/fast` | 3.6 / 4.4 / 5.4 syllables per second |
| `camera: pushes in…` | camera move, **without** the words "The camera" |
| `sound: …` | ambience and physical action sounds |
| `music: …` | audience-only score; omit for none |
| `extras: …` | other people in frame, described; see **Crowds and extras** |
| `text: OPEN 24 HOURS` | on-screen text the picture must show (a sign, a note, a screen), quoted into the prompt. Never the series title or credits: those are added in the edit, not rendered into a shot |
| `policy: generate` | this shot's audio: `generate` (the model makes all of it), `dub` (lip sync to the recording's `audio:` window, which becomes the soundtrack), `dub_keep_foley` (the same, keeping the model's sound effects under it) or `clone` (spoken in each speaker's `voice_sample`). Without it, dialogue shots follow `audio.mode` and silent ones generate |
| `retention: partially_copy` | how closely a dubbed shot copies the recording: `fully_copy`, `partially_copy` or `reference` (H3 Ref2VA; dub shots only) |
| `model:`, `lora:`, `steps:` | per-shot render overrides; also valid under a `#` header. `lora:` takes one LoRA (`soft_light.safetensors`, `soft_light.safetensors:0.6` for a strength) or a chain of them separated by commas, applied in that order (`lora: turbo_8step.safetensors, soft_light.safetensors:0.6`); `lora: none` for none: where the pass's LoRA is a turbo (H3's), that renders the full model, the pass's base preset (20 steps, `res_multistep` on H3); a shot's own `steps:` still wins |
| `sla: off` | H3's sparse attention (PlagueKind's `H3SLAAttention`) left out: about 40% slower, a little smoother frame to frame. Also under a `#` header, in a profile (`"sla": "off"`) or for the series (`"sla": "off"` in its `series` block); `on` is the default |
| `lens: shallow` | the lens the shot is shot on: `spherical`, `anamorphic`, `vintage`, `wide`, `long`, `shallow`, `tilt_shift` or `deep` (the look builder's Lens row). The action opens with its words ("Shallow depth of field: the subject sharp, the background falling into soft bokeh."), so every model reads it. Also under a `#` header, for its shots. Shallow focus shows the most; with a plate as the reference, the plate keeps its own geometry and the rest show less |
| `profile: dialogue_close` | a render profile from the series config; also valid under a `#` header |
| `target: ltx2` | the video model for this shot or sequence (`minimax_h3_ref2va`, `fasth3_omni`, `h3_singularity`, `h3_hybrid`, `ltx2`, `ltx2_ingredients`, `ltx2_msr`, `minimax_h3_fl2va`, `wan22_i2v`, `wan22_ti2v`, `wan22_vace`, a hosted model such as `seedance_2_5`, `hold` for a picture held still, or a show's own); see **Choosing a video target** |
| `first: generate` / `last: refs/x.png` | how this shot's first / last keyframe is made: `generate`, `import`, `none`, or a path to an image; also valid under a `#` header (the default of its shots); see **Keyframes** |
| `continuous: first` | this shot carries straight on from the previous one in the cut: `first` (open on its last frame) or `latent` (hold the previous take's last frames and carry on from them); `multishot` renders it in one generation with the shot before (see **Several shots in one generation**); under a `#` header, every shot after the sequence's first; `none` breaks the chain; see **Continuous shots** |
| `cold_open: true` | it plays before the opening titles: a master puts the series intro in right after the cold open's last shot. Under a `#` header, every shot of the sequence; on a shot, that shot (`cold_open: false` takes one out of its sequence's). The cold open is the cut's first shots, one after another: see **A cold open** |
| `overlap: 39` | frames of the previous take a `continuous: latent` shot holds (39, the default, is right almost always; any other number rounds up to 22, 39, 56, 73, ...); also valid under a `#` header |
| `NAME: line` | dialogue from someone on screen (the name is a character's key, in capitals) |
| `NAME (breathless): line` | a delivery direction, written into the prompt |
| `NAME (V.O.): line` | voiceover: speaks, is not drawn, costs no reference slot |
| `NAME (O.S.): line` | off-screen: in the space, outside the frame |
| `NAME (V.O., on the truck radio): line` | a voice marker and a delivery together; the note describes the voice and is never spoken |
| `// text` | comment |
| `// structure: Pixar Story Spine` | the episode's story structure (`references/story_structures.md`), near the top: the first-pass score reads it. A comment: nothing renders from it |
| `// beat: Until one day…` | above the first shot of a beat (or its sequence's `#` header), the beat's name as its structure writes it: the score's sections and turns. A **Cold Open** or **Teaser** beat's sequences also get `cold_open: true` |
| `// duration: 22:00` | near the top: the length the episode is aiming at, which sets the storyboard's targets (seriesmith's storyboard guide). Nothing else reads it |
| `// act: My Own Act` | above a beat: an act of your own on the storyboard, for a beat its structure doesn't place. Nothing else reads it |
| `// theme: show, tender` | above a shot: a theme on that moment, held low to the end of its scene (`sting` in the words: a sting on the shot). The theme is `story`, `show`, `runner` or one the series config names |
| `// flashback` | above a sequence that's a flashback: its music an echo, thinner and further away |

Any other line is action prose. Prose under a `#` header before its first shot is a
scene-setting note and is ignored. A line under a `#` header (`model:`, `lora:`, `steps:`,
`profile:`, `target:`, `first:`, `last:`, `overlap:`) is the default for every shot in the
sequence (`continuous:` for every shot after the first); a shot's own line beats it.

> **Read `references/continuity.md`** when you are about to write a `continuous:` line. It holds **Continuous shots: `continuous:`**, **Several shots in one generation: `continuous: multishot`**.

## Durations land on a grid

Every video model takes only certain frame counts, and a `dur:` between two of them rounds
**up**, so you pay for frames you throw away. The grid is the target's: `17k + 5` frames on
the H3 targets, `8k + 1` on LTX, `4k + 1` on Wan (at 24 fps; best kept to 3 s), whole
seconds in each model's range on a hosted one. The build
snaps each shot to its own target's grid, and the check's runtime line says how many frames
that added (`+16f grid pad`).

Write for H3's grid, the default; the other grids are fine-grained enough that these
lengths land close on them too. At 24fps these are free on H3:

| Frames | Seconds | Use for |
|---|---|---|
| 39 | **1.62** | a single word, a snap |
| 56 | **2.33** | a quick reaction, one short line |
| 73 | **3.04** | the workhorse shot |
| 90 | **3.75** | a beat with a little air |
| 107 | **4.46** | two lines of dialogue |
| 124 | **5.17** | a long beat, a small piece of business |
| 192 | **8.00** | rare: a sustained action run |

Render cost scales as roughly `duration^1.29`, so long shots are *less* efficient per second
than short ones. Cartoon pacing, 2 to 5 seconds, is both better filmmaking and cheaper.

## Dialogue has to fit the shot

Dialogue needs a model with sound: H3 and LTX have it, the Wan models are silent, and a
spoken line on one of those is a warning.

This is the easiest way to wreck an episode, and it does not announce itself: a model that
speaks (H3, LTX) will fit any line into any window by speeding the delivery up. The words
are all there, the lip sync is fine, and the performance is gone. On Wan, which acts the
lines silently, the recording laid in at the edit still needs the room.

A 2.33s shot holds about **seven syllables**. Never guess — the check measures it, in its
pacing table:

```
seriesmith check Shows\ep01
```

Three ways out of a crammed shot, in the order worth trying:

1. **Split it.** A line needing six seconds usually wanted a reaction cut in the middle
   anyway, and the split buys the second angle the scene was missing.
2. **Cut words.** Over-packed shots are usually over-written.
3. **Lengthen it.** `dur: auto` derives the length and snaps it to the grid.

`pace: fast` marks a rush that is deliberate and silences the warning.

## Camera moves use H3's vocabulary

Every target inserts the `camera:` line after the words "The camera", so write the verb
phrase only. Without one, the camera holds still. The vocabulary below is H3's training
vocabulary; the other models read it as plain English.
Compose from **motion + amplitude + speed**; the last two are optional.

**Motion:** zooms in / out · pushes in / pulls out · pans left / right · trucks left / right ·
tilts up / down · pedestals up / down · arcs around · tracks · holds a static shot · shakes
slightly / strongly · takes the subject's POV · rolls clockwise / counterclockwise

**Amplitude:** with small amplitude · with large amplitude
**Speed:** at slow speed · at fast speed

**Say where the move goes.** A move alone tells the model how the camera travels, not what
the frame should hold at the end, and a bare `pulls out` often barely moves. Finish the line
with what it travels toward or reveals, the way H3's own prompt guide writes every move:

```
camera: pushes in with small amplitude at slow speed toward the folded letter in her hands
camera: pulls out with large amplitude at slow speed, revealing the whole square around her
camera: pans right with large amplitude at slow speed from the cafe along the street to the station
camera: tilts down at slow speed from the rooftops to her standing by the bench
camera: trucks left at slow speed along the shop fronts, the street lamp sliding past in the foreground
```

A large move wants `at slow speed`: a large, fast one can flash or smear on the way. A truck
or a pedestal reads by what slides past in the foreground (parallax), so name something
there. For what a character sees, use `size: pov` and say in the action whose eyes they are.

"Arcs around them with large amplitude at fast speed" beats "swoops around dramatically",
because it names a move the model was trained on.

Film terms translate into that vocabulary:

| You mean | Write |
|---|---|
| dolly in / dolly out (back) | `pushes in…` / `pulls out…` |
| slide, crab | `trucks left…` / `trucks right…` |
| pivot, swivel | `pans left…` / `pans right…` |
| whip pan | `pans right with large amplitude at fast speed` |
| crane / jib up or down | `pedestals up…` / `pedestals down…` |
| orbit | `arcs around <name>…` |
| follow, lead | `tracks <name> as she walks…` (in front of or behind, in the action) |
| handheld | `shakes slightly` |
| over the shoulder | not a move: `size: ots`, with both in `who:`, and say whose shoulder in the action ("over Ada's shoulder, Bo faces camera") |
| rack focus | not a move: say it in the action, "the focus shifts from the cup to Ada's face" |

On a wide full of big architecture (a plant, a street front, a church), prefer holding still,
a pan or a slow push over a track, truck or arc. A camera that moves through the space makes
the model redraw the buildings as it goes, and they build and unbuild themselves on screen.

A static hold (`camera: holds a static shot`) suits a reaction, or any shot where stillness
is the point. On another wide you have just cut to, a slow push gives the space depth, and
costs nothing extra.

## Breaking a scene into shots

A scene with three paragraphs of action is six to ten shots, and deciding where they fall is
the job.

**Cut when** the subject changes, a new beat lands, someone new speaks, time skips, or the
framing must change materially. **Don't cut** when only the distance shifts a little — use a
camera move. A cut should bring new information; a cut to the same thing slightly closer is a
jump cut, and it will render as one (see **Cutting within a location**).

A workable rhythm for a dialogue scene: wide establishing → medium two-shot for the exchange →
close on the reaction that matters → back out. Keep the wide short and empty of anything
that has to read on a face (see **Faces need room**).

**Open every shot on movement.** The model has no memory of the previous cut, so a shot whose
action describes a *position* renders that position and then looks for something to do with
it. Write the state change: "Dex swings his boots onto the desk and settles back", not "Dex
sits with his boots on the desk".

### Faces need room

`size:` is written into the prompt as the shot's framing (`A close-up frames <Subject 1>…`,
`A medium shot frames…`, `A wide shot takes in…`), so it is what the model frames, not a
label. Choose it by what the shot has to show:

| `size:` | Framing | Holds | Use it for |
|---|---|---|---|
| `ecu` | extreme close-up | one detail: the eyes, a hand on the latch | an insert; tension |
| `cu` (`close`) | close-up | the face, chin to hairline | the reaction or line that matters |
| `mcu` | medium close-up | chest up | **most dialogue**: face and a little body language |
| `ms` (`medium`) | medium shot | waist up | two-shots, business at a counter |
| `cowboy` | cowboy shot | mid-thigh up | standing confrontations, a hand at the hip |
| `mws` | medium-wide shot | knees up | walking and talking, a figure with their surroundings |
| `fs` (`full`) | full shot | head to toe | a whole-body action: a trip, a dance step, a fall |
| `ws` (`wide`) | wide shot | the subject in the room | geography, entrances |
| `ews` | extreme wide shot | the subject small in a big setting | scale, isolation, establishing a place |
| `pov` | POV shot | what a character sees, through their eyes | discovery, a threat approaching, reaching for something |
| `ots` (`over-the-shoulder`) | over-the-shoulder shot | past one person's shoulder onto the other | dialogue coverage, a confrontation; put both in `who:` |
| `low` (`low-angle`) | low-angle shot | the subject seen from below | power, menace, a hero moment |
| `high` (`high-angle`) | high-angle shot | the subject seen from above | weakness, isolation, a fall seen from the top |

The last four are angles, framings H3's guide names beside the sizes: they say where the
camera looks from rather than how much it holds, act like a medium for the plate and the
sheet, and are never counted as a jump cut against another size. Say the distance in the
action when it matters ("a low-angle close-up of his face", "a high-angle wide of the square").

The full names work too (`size: medium close-up`), and so do `ls` (long shot) and `els`. The
in-between sizes put what the frame holds into the prompt ("from the chest up"), so a model
that doesn't know the term still frames it. For the plate and the sheet, `ecu`/`mcu` act like
a close-up, `cowboy`/`mws` like a medium, and `fs`/`ews` like a wide.

**A face needs pixels to have a face.** H3 draws in cells of 16×16 pixels. On a wide of a
standing person, the face is a few cells across, too few for eyes and a mouth: it comes out
soft and smeared, and an upscale sharpens the smear rather than finding the face. At 960×544
it is worse than at 1344×768. Measured on a 1344-wide full-body walk, the face was 50 pixels
tall: three cells.

- **Dialogue, reactions, and anything the audience must read on a face: `mcu`, `cu`, or
  `ms`.** A medium close-up gives the face a few hundred pixels at 960×544; a close-up fills
  the frame with it.
- **Wides (`fs`, `ws`, `ews`) carry geography, entrances, crowds and big physical action**,
  where nobody's expression has to read: a figure crossing a room, a back to camera, two
  people seen from across a lot. Don't hold a wide on a face and expect the face to be there.
- **Cut in for the face.** A fall, a collision or an entrance plays as `fs` for the action →
  `cu` on the face that reacts → `mws` or `ms` for the result, not one wide shot that holds the
  face at a distance.

The prompt also scales the location to the framing: a wide describes the whole place around
the subjects, a medium the part behind them, a medium close-up a magnified, softly focused
slice of it, and a close-up or an extreme close-up (`cu`, `ecu`) a tightly cropped portion of
the plate, completely blurred into soft bokeh. On H3 Ref2VA that last is named by its picture
alone, without the location's description, so the model isn't asked to draw the room. That is
why a close-up on H3 has the room behind the face, blurred, and not a studio backdrop. A
close-up still leaves the room's layout to the shots around it, so stage the space on a
medium first. (When a sharp plate still shows through behind a close-up, it can be given a
blurred plate of its own.)

**Say how tight an extreme close-up is, in its action.** The framing's name alone gives a
close-up of the whole face; the action says what fills the frame: "an extreme close-up of
Cindy's face from her eyebrows to her lips", "an extreme close-up of Cindy's hand, the diamond
ring on her finger". Keep the subject's picture an ordinary face or full-length one: a
picture cropped to the eyes was read as part of someone to be placed in a room, and the model
drew the room and moved her into it.

### Cutting within a location

Every shot is generated on its own, so a shot never continues the one before it: it poses
everyone from scratch. Cut between two shots that look alike and the eye reads it as a
glitch, with people jerking into new positions or appearing out of nowhere. That's a jump
cut. Two consecutive shots with **the same people on the same plate** need one of these
between them:

1. **A new angle.** Give the second shot another `plate:` of the place. A real change of
   camera position (film's 30-degree rule) makes the new pose read as a new view. This is
   the cheapest fix and why a location wants several angles.
2. **A size two or more steps away**, along `ecu` `cu` `mcu` `ms` `cowboy` `mws` `fs` `ws`
   `ews`: `mws` → `mcu`, `ms` → `cu`, `ws` → `ms`. One step (`ms` → `mcu`, `fs` → `ws`) reads
   as the camera twitching.
3. **A cutaway**, then back: the other character's reaction, an `ecu` insert of hands or a
   prop, what she's looking at. Under a second is enough (H3's shortest take is 0.92 s), and
   after it the return can be in any pose.
4. **A cut on action.** Open the second shot mid-movement ("already turning to the door"),
   not at rest: movement across the cut hides the change of pose. It helps the other three;
   on its own it seldom saves a cut.
5. **Continue the picture**, only when the second shot really is the same moment carrying
   on: a `continuous:` line opens it on the previous shot's last frame, or carries its
   motion and sound across (see **Continuous shots** before writing one).

`continuous: multishot` is no fix for a jump cut: the model draws the cut the script asks
for, so two near-identical shots in one generation still cut as one.

`seriesmith check` warns about consecutive shots that do none of the first two and don't continue:
the same people, the same plate, sizes less than two steps apart, the second not
continuing the first (`continuous:`). It can't see a cutaway or a cut on
action in the action text, so treat it as a question to answer, not an error.

Worked through: Ada at the counter, then closer for her line. As written, a jump cut:

```
## sh020
who: ada
size: ms

## sh030
who: ada
size: mcu
```

With Bo's reaction between them, and the return two steps tighter:

```
## sh020
who: ada
size: ms

## sh025
who: bo
size: mcu

## sh030
who: ada
size: cu
```

### Every shot starts from an empty plate

Plates are drawn empty, and the model sees one shot at a time. Whatever the scene established
three cuts ago — who is in the car, the diners at the other tables, that Harold sat down — is
gone unless this shot says it again.

- **Everyone physically in frame is in `who:`**, even mostly unseen: the driver of a two-shot
  in a car is both people, the passenger's shoulder included. Leave one out and the plate's empty
  seat is all H3 gets, so they vanish for a shot and come back on the next. The same goes for
  anyone the action touches or looks at in frame: "Harold reaches for Cora's elbow" with no
  Cora in `who:` gets an invented stranger.
- **A populated room is populated in every shot of it**, closes included: nothing carries
  over from the previous shot, and without its people the room is empty on the cut. A shot's
  `extras:` says who else is there ("diners at the far tables, blurred behind him"), drawn
  afresh each time. So **anyone who comes back and is seen** (the clerk behind the register,
  the nurse at the desk, two paramedics, the workers at the next table) is a character, or
  for several a group subject, cast in each shot: `seriesmith check` warns when two shots at
  one place name the same people in `extras:` (see **A group: the same extras every shot**).
- **Say the posture.** A plate of a kitchen table is an empty table, and the sheet shows the
  character standing. Open on the posture plus the movement: "Seated at the kitchen table,
  Harold turns his head slowly…", not "Harold turns his head slowly…".
- **Give every moving object a hand.** "The briefcase opens" opens by itself; "Mills lifts the
  lid of the briefcase" puts Mills in `who:` and in frame.
- **Settle carried props.** If a character's `design` has a bag on the arm and the shot seats
  them, set the bag down in the action ("her handbag set beside the ledger"), or H3 draws a
  second, standing copy of them to carry it.
- **The plate is where the camera stands.** The model keeps the plate's point of view and
  puts the people into it; it doesn't move the camera. A shot that faces someone needs a
  plate seen from the camera's side of them. A plate looking forward out through a truck's
  windshield sees the road, not the driver's face. In one H3 test, a shot asking for the
  driver's face on that plate failed on eight takes of ten, whatever the prompt said. Pick
  the angle whose camera is where this shot's is, or author one (**A location is one angle,
  not one place**). The same holds for things: a plate shot from the visitors' side sees the
  back of the monitor; if the screen matters, have someone turn it.
- **One or two physical steps per shot.** Crossing a lot, climbing steps and knocking is three
  shots, not one 4-second shot; crammed motion smears into interlace-like lines. Start the shot
  where its plate is.
- **Pick people up where the last shot left them.** If sh160 parks the truck by the building,
  sh170 doesn't walk him across the lot. Name the spot in the first shot ("parks at the far
  end of the lot") so the next one can start from it.
- **The crowd is already there.** On an empty plate, people written as arriving materialise
  in the middle of the shot. Write them as present from the first frame: "the line already
  running, a worker at every station".

## Shot IDs

Shot IDs go `sh010, sh020, sh030`, leaving gaps so you can insert `sh015` later. Renumbering
changes seeds and invalidates renders. An ID is unique across the whole episode, not just its
sequence: continue the numbering (`sh110` in the next sequence, or keep counting) rather than
restarting at `sh010`.

**A shot's ID is its identity**, beyond its seed: its takes, its overrides and everything the
cut says about it (the pick, trims, lock, audio source, and whether it's left out of the cut)
are kept by ID. So when revising a script:

- **the same shot, rewritten:** keep its ID. Its takes are flagged stale where the prompt
  changed, and the cut's decisions about it still apply;
- **a different shot:** give it a new ID, and never reuse an ID you removed; the old one's
  takes and cut decisions (a pick, trims, "left out") would land on the new shot;
- **a shot added between two others:** an in-between ID (`sh065` between `sh060` and `sh070`),
  so every other shot keeps its ID;
- **a shot removed:** just delete it; its takes stay on disk, and its cut entry is skipped.
  To try the cut without a shot, leave it out of the cut in the editor instead of deleting it.

## Reference slots (H3 Ref2VA)

This section is about the default target, `minimax_h3_ref2va`. The other targets take no
slots (their limits are under **Rendering a shot on …**), but one habit holds everywhere:
a shot about more than three things is usually two shots.

Every shot hands H3 its subjects and the plate. Slots 1–3 are the first three subjects —
characters first, then props and vehicles, in the order `who:` and `with:` list them. **Slot 4
is always the location plate**, and subjects four to eight take slots 5–9.

That caps you at **eight subjects on screen**, and a ninth is an error, not a silent drop. Each
picture costs render time, and the model tells people apart less well as the count grows. When
a scene is too full, stage someone out of frame, split the shot, or describe the
extra in the action text without referencing it. Crowds cost nothing that way — they just
won't look the same from shot to shot, unless they are a group (one slot for all of them;
see **A group: the same extras every shot**).

A `(V.O.)` or `(O.S.)` speaker costs no slot, is never drawn, and needs no sheet — only a
`voice` in the series config. A shot may have no `who:` at all: an establishing plate with narration
over it.

### Crowds and extras

On H3 Ref2VA a shot's prompt states that exactly one person appears in it per referenced
character, which is what stops H3 drawing the same face twice. The moment the action puts
someone else in frame — a dance partner, a mob, a crowd at a door — that sentence contradicts
the action, and H3 resolves the contradiction by **duplicating the referenced character**,
often with interlace-looking smearing where the copies overlap.

`extras:` names those people, so the prompt keeps identity locked for the subject and allows
everyone else:

```
## sh090
who: eleanor_30
extras: one masked man in black tails, his back mostly to camera, and far-off dancers blurred into bokeh
Eleanor circles a masked man in black tails, one hand in his, laughing as she turns around him.
camera: arcs around Eleanor with small amplitude at slow speed
```

## Sequences

A sequence is one location, continuously. A new place — or the same place at a different time
of day — starts a new `#` sequence. Intercutting is just alternating sequences: `# sq03
kitchen`, `# sq04 phone_room`, `# sq05 kitchen`.

Keep a sequence intact and vary the shots with `plate:` rather than splitting a scene into
one-shot sequences, which re-seeds every shot in it.

## What goes on which line

These map to different fields in the generated prompt, and mixing them dilutes all three.

- **action** — what is visibly happening, present tense, concrete and physical. Not
  motivation, not backstory, not what a character feels.
- **camera** — the move only.
- **sound** — ambience and physical action sounds: footsteps, fabric, doors, wind, impacts.
  Not dialogue, not score.
- **music** — audience-only score. Omit it on most shots; scoring is usually a conform
  decision.

## Finish by validating

```
seriesmith check Shows\ep01     # counts, runtime, references, warnings, then dialogue pacing per shot
```

(It runs `seriesmith build series.json ep01.md --check` and then `--pace`; those take the two
files by name where there is no episode folder.) The check compiles every shot for the
target it renders on, so it also reports each target's limits.

Errors name the line and quote it. Common ones: a name in `who:` that is not in the series config; a
location that isn't in the series config, or one with no `description`; an ALL-CAPS `NAME:` line for someone who cannot speak (usually a typo,
which would otherwise become action prose); more than eight subjects on H3 Ref2VA; a shot
with neither `dur:` nor `audio:`; `dur: auto` on a shot with no dialogue; a `dur: model`
range that isn't `min-max` seconds with min below max; a `target:` or `profile:` name that
doesn't exist; a `first:` / `last:` that isn't a method or an image path; a `continuous:`
the shot's own target can't render (`latent` on a model that isn't H3 Ref2VA or one of its
family, `first` on a target that reads no first frame). Warnings cover
crammed dialogue and what a target can't do (a dialogue shot on Wan,
a `clone` shot on `ltx2_ingredients`).

A script that does not compile is not a draft, it is a bug. Fix and re-run until it is clean.
