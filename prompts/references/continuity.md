# Shots that carry on from one another

A reference for SKILL.md: `continuous: first`, `latent` and `multishot`: what each does, where it renders, how to write it. Read it when you are about to write a `continuous:` line.

### Continuous shots: `continuous:`

A shot that carries on from the one before it says so, and how. There are three ways, and
they answer different needs:

| `continuous:` | What it does | Use it for | Renders on |
|---|---|---|---|
| `first` | opens on the previous shot's last frame | picking up exactly where a shot ended, on almost any model | every model that reads a first frame; H3 Ref2VA's and FastH3 Omni's move to their FL2VA |
| `latent` | holds the previous take's last 1.6 s (picture and sound) and goes on from them | one unbroken take built from several renders: the camera and the action keep running, no cut | H3 Ref2VA, FastH3 Omni, H3 Singularity, H3 Hybrid; the shot it continues can be from any model |
| `multishot` | renders it **in the same generation** as the shot before: one clip with cuts in it | a scene cut between angles, where the model sees every shot at once | the H3 family (Ref2VA, FastH3 Omni, FL2VA, Singularity), Seedance, Kling v3 Omni, Kling O1 |

`first` and `latent` make a **continuous take**: each shot is its own render, joined so the
cut doesn't show. `multishot` makes **real cuts inside one render**: the model draws a shot,
cuts, and draws the next, keeping the people, the light and the blocking the same across
them because it sees them all at once.

```
## sh090
continuous: first
```

- Only the shot that continues says it, and "previous" is the previous shot in the cut.
- Under a `#` header, `continuous:` covers every shot after the first **in that sequence**.
  A shot breaks the chain with `continuous: none`.
- Use `first` or `latent` only when the shot really picks up the previous picture (the same
  framing carrying on, a match on action). After a real cut (a new subject, a new angle, a
  different size) leave it off.

**`first`.** A shot on a model that reads a first frame (LTX-2, Wan, the hosted ones) stays
on it. One on H3 Ref2VA moves to H3 FL2VA, and one on FastH3 Omni to its own FL2VA, unless
the shot names its own `target:`. FL2VA draws everyone from words, without their pictures.
H3 Singularity opens on the frame itself with its pictures kept, and so can Ref2VA with
`"first_target": "minimax_h3_ref2va"` in the `series` block (`"h3_singularity"` sends the
continuing H3 shots there instead).

**`latent`.** The render holds the end of the previous take at its head and generates the
rest from there, so motion, sound and the camera carry across the join; the held frames are
cut off again, so the take starts where the previous one ended. It keeps its own pictures.
The previous shot can be on any model: when it isn't H3's, its last frames are encoded
instead (a silent one, such as Wan, holds no sound).

- **Keep the framing and the camera move the same across a latent chain**, and open each
  shot's action on what the held frames show. A shot that asks for a new size, a new move or
  a new place in the room is read as a new shot, and H3 cuts to it right after the held
  frames.
- **Over a long chain, prefer `latent` to `first`.** Every latent shot gets its pictures
  again, so the look stays anchored; a `first` shot on FL2VA has only the frame it opens on,
  so whatever drifts in one shot is where the next starts. In a ten-shot test of one man
  pacing a room, the latent chain held its brightness (36 to 39 of 255) while the FL2VA
  chain climbed to 90, doubled its contrast and redrew the room.
- **`overlap:`** is how many frames are held: leave it at the default, 39 (1.6 s). Fewer
  give H3 too little motion to carry on; more cost time for nothing. Any other number rounds
  up to H3's next (22, 39, 56, 73, …). Per shot, under a header, or for the series:
  `"continuous": { "overlap": 39 }`.
- A latent shot costs about 40% more render time, and its take can run up to 0.7 s longer
  than its `dur:`.

### Several shots in one generation: `continuous: multishot`

`continuous: multishot` on a shot renders it **in one generation with the shot before it**.
A run of such shots, with the shot they follow, is a **group**: the model sees the whole
scene at once, so blocking, light and performance carry across the cuts, and the same
people come back after a cutaway as themselves.

```
## sh040
who: stepmother, mia, ava
size: ms
dur: 4.46
...
## sh050
continuous: multishot
who: charming_face
size: cu
dur: 1.62
...
## sh060
continuous: multishot
who: stepmother, ava, mia
dur: 1.62
...
```

- **Every shot stays a shot in the script**, with its own `who:`, `size:`, `dur:`, action,
  lines and `sound:`. Under a `#` header it groups every shot after the sequence's first;
  `continuous: none` starts a new group. A group never crosses a `#`.
- **It renders as one take**, under the group's first shot, its length the shots' `dur:`
  together. The model lands its cuts near the script's times: H3 within about half a second,
  Kling v3 Omni within about a second, Kling O1 to the frame; Seedance times them itself.
- **Limits:** Kling, at most 6 shots and 15 s; Seedance 2.5, 30 s (2.0: 15 s). `check`
  refuses a group on a model that renders one shot a call (Veo, Runway, Wan, LTX).
- **One set of pictures for the whole generation**: every person in the group once (a
  wardrobe variant in a later shot isn't sent), up to the model's slots (Ref2VA, Singularity and
  FastH3 Omni eight: background people can be one group subject, `members`), and **one plate**,
  the first shot's (Seedance: every shot's). A close-up on another plate is drawn as a
  blurred crop of the one sent; a wider shot on another plate gets its place in words.
- **A group can carry on from the shot before it** with `continuous: latent` on its first
  shot. `continuous: first` works too, but renders the group from words and that frame,
  without its pictures.
- **Sound is generated**: a dubbed or cloned shot can't be in a group.
- It is no fix for a jump cut: two near-identical shots in one generation still cut as one.

**Nobody pops in or out.** On the same plate at sizes less than two steps apart, someone who
wasn't in the shot before has to come into frame in the action ("walks in from the left",
"steps up behind her"), and someone who leaves has to go out of frame in the shot before
("hurries out of frame", "slides away out of frame"). An empty room and then the same view with
someone standing in it is a jump cut, and so is a shot of two people followed by one of them
alone. `seriesmith check` warns about both. An insert between them is the usual fix: an extreme
close-up, or a close shot of a prop with nobody in it, is what the next shot looks at, not the
same view.
