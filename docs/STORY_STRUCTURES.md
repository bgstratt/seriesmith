# Story structures

A reference for [AUTHORING.md](AUTHORING.md): the major story structures, for outlining an
episode written from scratch. (Packaged with the script-writing skill as
`references/story_structures.md`.) Each entry gives a short pitch, what it suits, its beats
in order with roughly how much of the runtime each takes, an example, and the mistakes to
watch for. The menu near the top can be shown to someone choosing a structure, and
**From beats to shots** says how an outline becomes a seriesmith script.

The beat percentages are guides for timing, not rules. Multiply them by the episode's
runtime to estimate each beat's screen time, and so how many shots it gets.

---

## Quick selector

| Structure | Core engine | Ends with | Best runtime | Episodic fit |
|---|---|---|---|---|
| Hero's Journey | External quest that changes the hero | Hero returns home changed, with something to share | Long (feature, season arc) | Season arc; too big for one short episode |
| Virgin's Promise | Inner discovery of the true self | Community changed by the hero being herself | Medium–long | Season arc or character-focused episode |
| Three-Act / Change Arc | Goal + obstacles + a low point | Victory (or a meaningful loss) earned through growth | Any | Strong standalone episodes |
| Sitcom / Circular | A problem spirals into chaos, then is fixed | Back to the exact starting point | Short–half-hour | Built for it |
| Episodic Drama | A case of the week, act-outs at the breaks, a thread that runs on | The case solved, the thread moved a step, a hook | Half-hour–hour | Built for it: procedurals, serial drama |
| Dan Harmon's Story Circle | Want → get it → pay for it | Back home, but changed | Short–half-hour | Built for it |
| Kishōtenketsu | Contrast and a surprising turn, not conflict | A new understanding from combining the turn with the setup | Very short–medium | Quiet, reflective, slice-of-life episodes |
| Fable | A flaw meets its consequence | A moral, often stated outright | Very short | Bedtime / children's episodes |
| Parable | Everyday situation with a deeper meaning | A truth the audience has to recognize | Short | Anthology or ethics-driven episodes |
| Cautionary Tale | A warning ignored | Punishment | Very short–short | Horror, children's, anthology |
| Freytag's Pyramid | Rise to a central turning point, then the fall | Resolution or tragic catastrophe | Medium–long | Prestige drama, tragedy |
| Fichtean Curve | Crisis after rising crisis | An explosive climax and a quick ending | Any | Thrillers, action, cliffhanger serials |
| In Medias Res | Open on the crisis, rewind to explain | The opening moment, finally understood, then the finale | Any | A strong cold-open hook |
| Pixar Story Spine | A routine broken, with a chain of cause and effect | A new normal | Very short–short | Bedtime / children's, quick outlines |

---

## Asking the user (menu)

When someone starts an episode from scratch and hasn't named a structure, offer a short
menu like this one, in the same message as the questions in AUTHORING's **Starting a
series** (when the series is new). Describe the *shape* of each option and give one familiar
example. Then ask the two follow-ups at the end.

> **What kind of story shape do you want for this episode?**
> 1. **Big transformation (Hero's Journey)**: someone leaves their normal life, faces a huge trial and comes back changed. *Star Wars, The Lion King.*
> 2. **Finding yourself (Virgin's Promise)**: someone secretly becomes who they really are, and everyone around them is better for it. *Billy Elliot, Frozen.*
> 3. **Classic three-act**: a goal, rising obstacles, a darkest moment and a hard-won climax. *Most films.*
> 4. **Reset comedy (Sitcom)**: a small problem snowballs into chaos, gets fixed and everything goes back to normal. *Seinfeld, Friends.*
> 5. **Case of the week (Episodic Drama)**: a teaser, acts that each end on a twist, the case solved by the end, and an ongoing thread that leaves a hook for next week. *The Blacklist, House.*
> 6. **Story Circle**: someone wants something, gets it, pays for it and comes home a little different. *Rick and Morty, Community.*
> 7. **Quiet twist (Kishōtenketsu)**: no villain; a calm setup, then an unexpected turn that changes how you see it. *My Neighbor Totoro.*
> 8. **Fable**: a character's flaw leads straight to its consequence, and there's a lesson at the end. *The Tortoise and the Hare.*
> 9. **Parable**: an everyday human situation that carries a deeper moral meaning. *The Good Samaritan.*
> 10. **Cautionary tale**: someone ignores a warning, enjoys it for a while, then pays. *The Boy Who Cried Wolf, Gremlins.*
> 11. **Five-act drama (Freytag)**: rising action, a central turning point, then the fall. *Macbeth, Romeo and Juliet.*
> 12. **Nonstop escalation (Fichtean Curve)**: start straight in trouble, with each crisis bigger than the last. *Mad Max: Fury Road.*
> 13. **Start at the end (In Medias Res)**: open on the crisis, then jump back to show how we got there. *Breaking Bad pilot, Sunset Boulevard.*
> 14. **Story Spine**: "Once upon a time… every day… until one day…" A simple chain of cause and effect. *Most Pixar shorts.*
>
> Follow-ups: *About how long should the episode be?* and *Is this a standalone story, or part of a longer arc?*

If they aren't sure, suggest a structure from the tone and length they want (see
**Choosing by need** at the end). If they'd rather you just start, pick one, say which and
why in a line, and go on.

---

## From beats to shots

An outline is beats; a script is shots. A structure not listed here (one the person names)
works the same way: outline its beats, give each a share of the runtime, and the rules below
turn them into shots. Going from one to the other:

- **Count the shots.** A beat's share of the runtime, divided by the length of a typical
  shot (3 to 4 s; dialogue shots run longer, inserts shorter), is roughly how many shots it
  gets. A 3-minute episode is around 50 shots: a 10% beat is about 18 s, five shots or so.
- **Merge beats that come out under a shot or two.** A 12-stage Hero's Journey in a
  2-minute episode leaves several stages one shot each: combine them (the notes under each
  structure say which), or pick a shorter structure. For 1 to 3 minutes, the Fable, the
  Story Spine, Kishōtenketsu, the Story Circle and the Cautionary Tale fit best.
- **Mark the structure and the beats in the script**: `// structure: <name>` once near the
  top, and `// beat: <name>` above each beat's first shot, the names as in the structure's
  table. The outline then survives into the script, the next edit can see it, and the
  score can be drafted from it (each structure's **Music** table, below). The build ignores
  comments:

  ```
  // structure: Three-Act
  ...
  // beat: Inciting Incident
  ## sh060
  ```

  A beat can start on any shot, not only a sequence's first. A beat that repeats (the Story
  Spine's "Because of that…", the Fichtean Curve's crises) is marked each time. A converted
  screenplay is marked the same way, with the structure that fits it best.
- **Each structure's Music table** is a first pass at the score: how each beat is scored
  before anyone adjusts it. seriesmith drafts it from the beat lines (the spotting sheet's
  **Draft…**), so the beat names must be the table's.
  - **Music**: `score` (a cue), `under` (a cue held low under the lines or a narrator),
    `sting` (a few seconds at the beat's start or end, otherwise dry) or `dry` (no music:
    the scene and its room tone carry it).
  - **Mood**: words added to the show's sound (`sound.score`), so they stay in its world,
    with an energy from 1 (barely there) to 5 (everything).
  - **Theme**: `story` is the episode's own melody, made by its first scored beat and played
    again by the later ones; `show` is the series' theme, the same every episode; `runner`
    is the thread that carries on from episode to episode (a serial's ongoing story, the
    one character who follows the cast), the same across them. A *statement* plays it
    whole; an *echo* recalls it, changed as the mood says.
  - **Hit**: where the music lands on the picture: `turn` (it changes as the beat starts),
    `arrive` (it peaks), `drop` (it cuts out).
- **Music in every structure.** Whatever the structure, a few moments are scored the same
  way, so write them where the draft can see them:
  - **Music in the scene** (a radio, a band, a carousel, a song someone plays, in a shot's
    `sound:`): two musics fight, so the score sits out under it, or takes up its tune and
    becomes it. Which is a choice the first pass leaves to a person: it marks the spot.
  - **A montage** (a run of short shots with no lines): one scored cue across the cuts, at
    the beat's mood but fuller. Write it as a montage, not as scenes with a line or two.
  - **Titles and credits** (a card, a `target: hold` shot, at the open or the end): the
    `show` theme, stated.
  - **A flashback** (a memory, a whole sequence): its theme's echo, thinner and further
    away. Mark it, `// flashback` above the sequence, besides the card or the look that
    tells the viewer (**Time jumps need a marker**, below).
  - **A moment the beats can't find** (the heart of a comedy, a look that changes the
    scene, a show's recurring device): `// theme: <theme>, <words>` above its shot puts
    that theme there, held low from that shot to the end of its scene, or, when the words
    say `sting`, a few seconds on the shot. `<theme>` is `story`, `show`, `runner` or a
    theme the series names; `<words>` say how (`tender`, `sting`, a variant the series
    lists).
  - **Beats in a row with music are one cue**, its sections the beats: the music changes
    at each beat (its `turn`) rather than stopping and starting.
- **A beat is not a sequence.** A `#` sequence is a place; a beat can run across several of
  them, or share one with the next beat.
- **Every beat has to be on screen.** Each shot is rendered by a model with no memory of the
  others (AUTHORING's **The one thing that shapes every decision**), and an audience sees
  only what's in the picture and the sound. Inner beats (the Debate, the Dark Night of the
  Soul, Recognition, Power Within) need an action, a look held long enough to read, or a
  line: write "Mara puts the letter face down and stares at the wall", not "Mara realizes
  she was wrong". A narrator (`NAME (V.O.): line`) suits the Fable's moral and the Story
  Spine's "once upon a time".
- **Mirrored images are a framing choice.** The Three-Act's final image and the Story
  Circle's return mirror the opening: put them in the same location with the same `size:`
  and a matching `camera:`, so the plate and the framing do the rhyming.
- **Time jumps need a marker.** For In Medias Res or a flashback, put a card on screen
  (`target: hold` with a picture of "Three days earlier") or change the look unmistakably,
  so the viewer doesn't get lost.
- **A season arc lives outside the scripts.** When a long structure (Hero's Journey,
  Virgin's Promise, the 27 beats) runs across a season, keep the arc in the outline. Each
  episode still has its own shape, and the people and places it shares with the others come
  from `series.json`.

---

## 1. Mythic & transformational

These structures follow a deep change in one protagonist, who is forced out of their comfort
zone and grows.

### 1.1 The Hero's Journey (Monomyth)

**Origin:** Joseph Campbell, *The Hero with a Thousand Faces* (1949), condensed into 12
stages by Christopher Vogler, *The Writer's Journey*.

**Pitch:** A hero leaves the ordinary world, enters an unfamiliar (often supernatural)
realm, survives a supreme ordeal, wins a reward and comes home changed, bringing back
something that helps others.

**Best for:** Epic adventures, coming-of-age stories, fantasy and sci-fi, and season-long or
multi-episode arcs.

**Beats (Vogler's 12 stages):**

| Act | # | Beat | What happens | ~% |
|---|---|---|---|---|
| **Departure** | 1 | **Ordinary World** | Show the hero's normal life, their flaw or lack, and what's at stake if nothing changes. | 0–10 |
| | 2 | **Call to Adventure** | A problem, challenge or message disrupts the ordinary world. | 10 |
| | 3 | **Refusal of the Call** | The hero hesitates out of fear, duty or doubt. This shows the cost of going. | 10–15 |
| | 4 | **Meeting the Mentor** | A guide gives advice, training, a gift or the confidence to go. | 15–20 |
| | 5 | **Crossing the Threshold** | The hero commits and enters the special world. There's no easy way back. | 20–25 |
| **Initiation** | 6 | **Tests, Allies, Enemies** | The hero learns the new world's rules, makes friends and enemies, and faces smaller trials. | 25–45 |
| | 7 | **Approach to the Inmost Cave** | The team prepares to face the central danger. Tension and stakes build. | 45–50 |
| | 8 | **The Ordeal** | The central crisis: a brush with death (literal or symbolic) and the greatest fear faced. | 50–60 |
| | 9 | **Reward (Seizing the Sword)** | Having survived, the hero claims the prize: an object, knowledge or reconciliation. | 60–70 |
| **Return** | 10 | **The Road Back** | The hero heads home, but the consequences follow. Often there's a chase or a new threat. | 70–80 |
| | 11 | **Resurrection** | A final, higher-stakes test where the hero must use everything they've learned. They are purified and reborn. | 80–95 |
| | 12 | **Return with the Elixir** | The hero comes home changed, with something that heals or improves the ordinary world. | 95–100 |

**Music:**

| Beat | Music | Mood (energy) | Theme | Hit |
|---|---|---|---|---|
| Ordinary World | score | at home, settled (2) | story, statement | — |
| Call to Adventure | score | a stir, something calling (2→3) | story, echo | turn |
| Refusal of the Call | under | hesitant, held back (2) | story, echo, minor | — |
| Meeting the Mentor | under | warm, steady (2) | story, echo | — |
| Crossing the Threshold | score | bold, opening out (3→4) | story, statement, full | arrive |
| Tests, Allies, Enemies | score | lively, varied (3) | story, echo | — |
| Approach to the Inmost Cave | score | tense, gathering (3→4) | story, echo, low | — |
| The Ordeal | score | dark, at its fullest, then nothing (4→5) | story, echo, broken | drop |
| Reward | score | relief, glowing (3) | story, statement | arrive |
| The Road Back | score | urgent, driving (4) | story, echo | turn |
| Resurrection | score | the biggest, everything at once (5) | story, statement, full | arrive |
| Return with the Elixir | score | home again, warm, changed (2) | story, statement, soft | the end |

**Example:** *Star Wars: A New Hope*: Tatooine → Leia's message → Luke refuses → Obi-Wan →
leaving Tatooine → the cantina and the Falcon → the Death Star → the trash compactor and
Obi-Wan's death → rescuing Leia → escape and pursuit → the trench run → the medal ceremony.

**Pitfalls:**
- Running all 12 stages in a short episode makes every beat thin. For shorts, merge stages
  (1+2, 3+4, 9+10) or use the Story Circle instead.
- A mentor who solves the problem for the hero. The hero has to win the Ordeal and the
  Resurrection themselves.
- A Return that skips the "elixir". The change should be visible back in the ordinary world.

#### The 27 beats: the journey at length

For a season, or an episode long enough to need finer steps, the journey can be outlined as
27 beats: three acts of nine, each act three blocks of three (a setup, a conflict and a
resolution). Each beat is about 3.7% of the runtime; across a season of nine episodes, each
episode can take one block. Vogler's stages are in brackets.

| Act | # | Beat | What happens |
|---|---|---|---|
| **One** | 1 | **Intro** | The hero's ordinary world, and the flaw or lack they carry. [Ordinary World] |
| | 2 | **Inciting Incident** | The event that breaks it. [Call to Adventure] |
| | 3 | **Immediate Reaction** | The first, instinctive response: shock, denial, a joke. [Refusal] |
| | 4 | **Reaction** | The considered response: what they think they should do about it. |
| | 5 | **Action** | They act on that, usually the small or safe way. |
| | 6 | **Consequence** | The result raises the stakes: the small way doesn't work. |
| | 7 | **Pressure** | Staying put stops being possible. A mentor or ally often pushes here. [Mentor] |
| | 8 | **Pinch** | The opposing force shown directly, so its threat is real. |
| | 9 | **Push** | The final shove: the hero commits and goes. [Crossing the Threshold] |
| **Two** | 10 | **New World** | The new place or situation, and its rules. |
| | 11 | **Fun & Games** | The premise enjoyed: the hero tries things, wins some, meets friends and enemies. [Tests, Allies, Enemies] |
| | 12 | **Old Contrast** | A reminder of the old world or old self: what has changed, or what they miss. |
| | 13 | **Build Up** | Moving toward the central goal; the stakes climb. [Approach] |
| | 14 | **Midpoint** | A revelation or event that turns the hero from reacting to acting. [Ordeal] |
| | 15 | **Reversal** | The midpoint's consequence turns things against them. |
| | 16 | **Reaction** | The hero takes in the reversal. |
| | 17 | **Action** | A new plan, taken. [Reward] |
| | 18 | **Dedication** | Full commitment, the cost accepted. [The Road Back] |
| **Three** | 19 | **Trials** | The plan meets resistance and things go wrong. |
| | 20 | **Pinch** | The opposing force's second direct blow. |
| | 21 | **Darkest Point** | All seems lost. |
| | 22 | **Power Within** | The hero finds the strength or insight they lacked: the flaw from beat 1, faced. |
| | 23 | **Action** | They act on it, with a new plan. |
| | 24 | **Converge** | Every thread and character comes together for the end. |
| | 25 | **Battle** | The final confrontation. [Resurrection] |
| | 26 | **Climax** | The decisive moment the battle turns on. |
| | 27 | **Resolution** | The new ordinary world, and what the hero brought back. [Return with the Elixir] |

**Music:** score each of the 27 beats as the stage in brackets after it (the 12-stage
table above); a beat without one takes the stage of the beat before it.

The two Pinches (8 and 20) and the Midpoint (14) are what keep a long middle from sagging:
plan them first, then fill the beats between.

---

### 1.2 The Virgin's Promise

**Origin:** Kim Hudson, *The Virgin's Promise* (2009). "Virgin" is meant in the archetypal
sense of someone self-possessed and not defined by others. It isn't about gender or
sexuality, and the protagonist can be anyone.

**Pitch:** Where the hero goes outward to conquer, this protagonist goes inward to become who
they truly are. They find their gift, nurture it in secret, are found out, choose themselves
anyway, and the community that resisted is better for it.

**Best for:** Character-driven drama, artist or identity stories, family stories, and quiet
protagonists in a restrictive world.

**Beats (Hudson's 13):**

| Act | # | Beat | What happens | ~% |
|---|---|---|---|---|
| **Dependent World** | 1 | **Dependent World** | The protagonist relies on others (family, community, a system) for safety and identity. | 0–8 |
| | 2 | **Price of Conformity** | Fitting in costs them their true self. Show what's being suppressed. | 8–15 |
| | 3 | **Opportunity to Shine** | A chance comes to express their hidden gift or desire, often by accident. | 15–20 |
| | 4 | **Dresses the Part** | They take on the trappings of the true self: a costume, a role, a secret identity. | 20–25 |
| **Double Life** | 5 | **Secret World** | They live a double life, nurturing their gift away from the dependent world. | 25–40 |
| | 6 | **No Longer Fits Her World** | The two lives grate against each other. The old world feels wrong. | 40–50 |
| **Fallout** | 7 | **Caught Shining** | The secret is discovered, and the dependent world reacts. | 50–58 |
| | 8 | **Gives Up What Kept Her Stuck** | They let go of the attachment, fear or belief that kept them conforming. | 58–65 |
| | 9 | **Kingdom in Chaos** | The community is thrown into turmoil by the change. | 65–72 |
| | 10 | **Wanders in the Wilderness** | Doubt and temptation to go back to safety. This is the low point. | 72–80 |
| **Her Light** | 11 | **Chooses Her Light** | They fully commit to their true self, whatever it costs. | 80–88 |
| | 12 | **Re-ordering (Rescue)** | The community reorganizes around the new reality and often comes to their aid. | 88–95 |
| | 13 | **The Kingdom Is Brighter** | Everyone is better off because the protagonist became themselves. | 95–100 |

**Music:**

| Beat | Music | Mood (energy) | Theme | Hit |
|---|---|---|---|---|
| Dependent World | score | safe, contained, a little small (2) | story, statement, held back | — |
| Price of Conformity | under | muted, constrained (2) | story, echo, muted | — |
| Opportunity to Shine | score | a spark, the tune opening up (3) | story, statement, full for a moment | turn |
| Dresses the Part | score | playful, daring (3) | story, echo | — |
| Secret World | score | free, joyful (3) | story, echo, full | — |
| No Longer Fits Her World | under | uneasy, two sounds at odds (2→3) | story, echo | — |
| Caught Shining | sting (at its start) | exposed (4) | story, echo | turn |
| Gives Up What Kept Her Stuck | score | letting go, quiet (2) | story, echo, soft | — |
| Kingdom in Chaos | score | turmoil, clashing (4) | story, echo, broken | — |
| Wanders in the Wilderness | under | lonely, sparse (1) | story, echo, a fragment | — |
| Chooses Her Light | score | resolve, rising (3→4) | story, statement | arrive |
| Re-ordering (Rescue) | score | others joining in, fuller (3) | story, echo, full | — |
| The Kingdom Is Brighter | score | bright, open, warm (2→3) | story, statement | the end |

**Example:** *Billy Elliot*: a mining-town boy (Dependent World) is expected to box (Price of
Conformity), stumbles into a ballet class (Opportunity to Shine), trains in secret (Secret
World), is caught by his father (Caught Shining), goes through the strike-torn family crisis
(Kingdom in Chaos), commits to the audition (Chooses Her Light) and is backed by the town
(Re-ordering).

**Pitfalls:**
- Making the dependent world a cartoon villain. It should be loving but limiting, so the
  choice actually hurts.
- Skipping the community payoff. The defining feature is that the *world* changes, not just
  the protagonist.
- Turning it into a Hero's Journey by adding a big external enemy. The opposition is the
  pressure to conform.
- Dresses the Part (4) is a wardrobe change: a variant of the character in `series.json`
  (AUTHORING's **A wardrobe change is a new subject**), so plan it with the cast.

---

### 1.3 The Change Arc (Three-Act Structure)

**Origin:** It goes back to Aristotle's beginning, middle and end. Syd Field formalized it for
screenwriting in *Screenplay* (1979), and Blake Snyder's *Save the Cat!* refines it.

**Pitch:** A status quo is broken by an inciting incident. The protagonist pursues a goal
through rising complications, the stakes rise at the midpoint, everything collapses at the
low point ("dark night of the soul"), and the protagonist uses what they've learned to win
the climax.

**Best for:** Almost anything. It's the default for standalone episodes, films and most
drama.

**Beats:**

| Act | Beat | What happens | ~% |
|---|---|---|---|
| **I: Setup** | **Opening / Status Quo** | Show the world and the protagonist as they are, including the flaw or need. | 0–10 |
| | **Inciting Incident** | Something breaks the status quo and creates the central problem. | 10–12 |
| | **Debate** | The protagonist hesitates or weighs options. Stakes are made clear. | 12–20 |
| | **Plot Point 1 (Break into Two)** | The protagonist commits to a goal and enters a new situation. | 20–25 |
| **II: Confrontation** | **Rising Complications** | They chase the goal and meet obstacles. Often there's a B-story (relationship or theme). | 25–50 |
| | **Midpoint** | A false victory or false defeat. New information raises the stakes, and the protagonist shifts from reacting to acting. | 50 |
| | **Pressure Mounts** | The opposition closes in, alliances crack and inner flaws cause outer problems. | 50–75 |
| | **Low Point (Dark Night of the Soul)** | All seems lost. Something or someone dies, literally or symbolically. The protagonist faces the flaw. | 75 |
| **III: Resolution** | **Plot Point 2 (Break into Three)** | An insight, often from the B-story, gives a new plan. | 75–80 |
| | **Climax** | The final confrontation. The protagonist wins (or loses meaningfully) by acting as their changed self. | 80–95 |
| | **Resolution / Final Image** | The new normal, often a mirror of the opening image to show the change. | 95–100 |

**Music:**

| Beat | Music | Mood (energy) | Theme | Hit |
|---|---|---|---|---|
| Opening / Status Quo | score | the world as it is (2) | story, statement | — |
| Inciting Incident | score | a change, unsettling (3) | story, echo | turn |
| Debate | under | uncertain (2) | story, echo | — |
| Plot Point 1 | score | committed, moving out (3) | story, statement | arrive |
| Rising Complications | under | pressure building (3) | story, echo | — |
| Midpoint | score | a lift or a fall, the stakes raised (4) | story, statement | turn |
| Pressure Mounts | score | tightening, darker (3→4) | story, echo, low | — |
| Low Point | under | near silence, a held tone (1) | story, echo, a fragment | drop (as it starts) |
| Plot Point 2 | score | a new resolve (2→3) | story, echo | turn |
| Climax | score | full, driving (4→5) | story, statement, full | arrive |
| Resolution / Final Image | score | settled, the opening's music again (2) | story, statement, soft | the end |

**Example:** *Toy Story*: Woody is the top toy → Buzz arrives → rivalry → Woody knocks Buzz
out the window and both are lost → the gas station and Pizza Planet → Buzz learns he's a toy
(low point for Buzz) → trapped at Sid's (low point for Woody) → they work together → the
chase after the moving truck → Woody and Buzz as co-leaders.

**Pitfalls:**
- A saggy Act II. Use the midpoint to turn the story, not just to add more obstacles.
- A climax won by luck or by someone else. Win it through the change.
- Not planting the flaw in Act I, so the growth feels unearned.

---

## 2. Situational, episodic & media

These structures suit recurring formats, ensembles and fast pacing, where returning to the
status quo, or a small and repeatable change, matters.

### 2.1 The Sitcom Formula (Circular Structure)

**Origin:** Radio and TV situation comedy. It's built so a series can keep going
indefinitely.

**Pitch:** It works like a rubber band. A character makes a problem (usually by a lapse in
judgment, a lie or a scheme), the chaos snowballs, a misunderstanding peaks, and by the end
the mistake is undone. Everyone is back exactly where they started, ready for next week.

**Best for:** Comedy, ensembles, half-hour episodes and any series where the characters
shouldn't change much between episodes.

**Beats:**

| Act | # | Beat | What happens | ~% |
|---|---|---|---|---|
| **Setup** | 1 | **Cold Open / Teaser** | A self-contained gag or a quick setup that hooks the audience and often seeds the theme. | 0–8 |
| | 2 | **Status Quo** | The usual dynamics: who wants what, the running jokes and the setting. | 8–15 |
| | 3 | **The Problem** | The A-plot starts with a want, a mistake or an outside disruption. A B-plot (and sometimes C) starts with other characters. | 15–25 |
| **The Scheme** | 4 | **The Bad Decision / Scheme** | Instead of the sensible fix, the character lies, covers up or schemes. | 25–35 |
| | 5 | **Complications** | The scheme needs more lies. Other characters get pulled in. The B-plot starts to cross into the A-plot. | 35–65 |
| **The Blow-Up** | 6 | **Peak Chaos / Misunderstanding** | Everything collides, often with all the characters in one place, at the worst possible moment. | 65–80 |
| | 7 | **Confession / Fix** | The truth comes out or the mistake is undone. Sometimes there's a small emotional beat. | 80–92 |
| **Reset** | 8 | **Reset** | Back to the status quo. The lesson is learned, or comically not learned. | 92–97 |
| | 9 | **Tag** | A final callback joke after the resolution. | 97–100 |

**Music:**

| Beat | Music | Mood (energy) | Theme | Hit |
|---|---|---|---|---|
| Cold Open / Teaser | sting (at its end) | the main title (3) | show, statement | — |
| Status Quo | dry | — | — | — |
| The Problem | dry | — | — | — |
| The Bad Decision / Scheme | sting (at its end) | sneaky, playful (3) | show, echo | — |
| Complications | dry | — | — | — |
| Peak Chaos / Misunderstanding | sting (at its end) | the act out (4) | show, echo | — |
| Confession / Fix | under (its last scene) | warm, soft: the small emotional beat (1→2) | show, echo, slowed | — |
| Reset | dry | — | — | — |
| Tag | sting (at its end) | the end titles: a button (3) | show, statement | — |

The **Cold Open / Teaser** beat is a cold open: it plays before the opening titles. Mark its sequences
`cold_open: true` (AUTHORING.md, "A cold open"), and a master puts the series intro in after them.

A sitcom plays its scenes dry; its music is the show's theme between them. So besides the
beats above, a short `show` echo (a bumper) plays at each change of scene, a new place or a
jump in time (a new `#` sequence's location), unless a beat's sting is already there, and
there is no `story` theme. Its heart is rarely where the beats say (the late-night talk
in the Complications, the wrap-up in the Reset): mark that moment with `// theme:` (below)
to hold the theme low under it. A comedy that wants its scenes scored (a dramedy) uses the Story Circle's
Music table instead.

**Example:** A typical *Seinfeld* episode: four separate small problems escalate in parallel
and collide in one absurd climax, and nobody grows.

**Pitfalls:**
- Letting the reset erase emotional moments the audience cared about. Keep a sliver of
  warmth, or lean fully into "no lessons".
- A-, B- and C-plots that never connect. The payoff comes from them colliding.
- Characters who are dumb rather than flawed. Their bad decisions should come from
  consistent traits.
- Peak Chaos with the whole cast in one shot can run past a model's picture slots: check how
  many people the shot's model takes (AUTHORING's **Choosing a video target**), or cover the
  collision in several shots.

---

### 2.2 Episodic Drama (Teaser and Acts)

**Origin:** The hour (and half-hour) television drama, cut into acts for the commercial
breaks: the procedural, the legal and medical show, the prestige serial.

**Pitch:** A case of the week inside a story that keeps going. A teaser hooks; each act ends
on an **act-out**, a twist that makes you stay through the break; the case is solved by the
last act; and a **runner**, the serialized thread (the ongoing investigation, the
relationship, the one character who follows the cast), moves a step in the tag, leaving a
hook for next week. It's the drama's counterpart to the Sitcom: the case resets, the runner
doesn't.

**Best for:** Procedurals, crime, legal and medical dramas, thrillers with a case each
episode, and any drama series with a season-long thread.

**Beats:**

| Act | Beat | What happens | ~% |
|---|---|---|---|
| Teaser | **Teaser / Cold Open** | A hook: the case's first moment (a crime, a stranger, a body, a request), ending on a question. | 0–8 |
| Act One | **Act One** | The case set up: who, what's at stake, the first obstacle. Act-out: a complication. | 8–28 |
| Act Two | **Act Two** | The investigation or pursuit; the B-plot (often the runner) crosses it. Act-out: a reversal. | 28–50 |
| Act Three | **Act Three** | Pressure: the case at its worst and what it costs. Act-out: the low point. | 50–72 |
| Act Four | **Act Four** | The turn and the climax: the case resolved, won or lost. | 72–92 |
| Tag | **Tag / Stinger** | The aftermath, then the runner moves on: a hook for next week. | 92–100 |

**Music:**

| Beat | Music | Mood (energy) | Theme | Hit |
|---|---|---|---|---|
| Teaser / Cold Open | score | watchful, a question (2→3) | story, statement | turn (on the first shot), a sting at its end (the title) |
| Act One | under | building (2→3) | story, echo | a sting at its end (the act-out) |
| Act Two | under | pursuit, tightening (3) | story, echo; runner, echo, where the B-plot is the runner | a sting at its end (the act-out) |
| Act Three | score | heavy, the cost (3→4) | story, echo, low | drop (at its end, the act-out) |
| Act Four | score | the turn, then the release (4→2) | story, statement | arrive |
| Tag / Stinger | score | the aftermath, then a cold edge (2→3) | show, echo; then runner, statement | a sting at its end |

The **Teaser / Cold Open** beat is a cold open: it plays before the opening titles. Mark its sequences
`cold_open: true` (AUTHORING.md, "A cold open"), and a master puts the series intro in after them.

The act-outs are what this format adds to a score: a hit at the end of every act, which is
what keeps it sounding like television rather than a film. A show with its own names for
its beats (a recurring format of its own) is still this structure underneath.

**Example:** *The Blacklist*: a teaser with the week's blacklister, acts that end on the
case turning, the blacklister caught or killed in the last act, and a tag that moves Red
and Liz's story on.

**Pitfalls:**
- Act-outs that are only loud. Each should change what the case is about, not just raise
  the volume.
- A runner that takes over the episode. The case still has to be solved here.
- A tag that resolves the runner. It should open a question, not close one.

---

### 2.3 Dan Harmon's Story Circle

**Origin:** Dan Harmon (*Community*, *Rick and Morty*), a streamlined 8-step version of the
Monomyth for episodic TV.

**Pitch:** A circle split into a top half (the ordinary world, order) and a bottom half (the
unfamiliar world, chaos). The character goes down into chaos to get what they want, pays for
it, and comes back up changed. The change can be small, which is what makes it repeatable.

**Best for:** Episodic TV, short films, and any story under about 30 minutes that still
needs a real arc. It also works at scene level.

**Beats:**

| Act | # | Label | Beat | What happens | ~% |
|---|---|---|---|---|---|
| **Comfort** | 1 | **You** | Zone of comfort | Establish the character in their familiar world. | 0–10 |
| | 2 | **Need** | But they want something | A desire, lack or problem appears. | 10–20 |
| **Descent** | 3 | **Go** | Unfamiliar situation | They cross into somewhere, or something, new. | 20–30 |
| | 4 | **Search** | Adapt to it | They struggle, learn the rules and pick up tools or allies. | 30–50 |
| **The Price** | 5 | **Find** | Get what they wanted | They get it, often at the midpoint, the bottom of the circle. | 50–60 |
| | 6 | **Take** | Pay a heavy price | The cost hits: what they wanted wasn't what they needed, or it costs something dear. | 60–75 |
| **Return** | 7 | **Return** | Back to the familiar | They come back to where they started. | 75–90 |
| | 8 | **Change** | Having changed | They are different now, and can do or see something they couldn't before. | 90–100 |

**Music:**

| Beat | Music | Mood (energy) | Theme | Hit |
|---|---|---|---|---|
| You | score | at home (2) | story, statement | — |
| Need | under | a want, restless (2) | story, echo | turn |
| Go | score | crossing over, curious (3) | story, echo | turn |
| Search | under | adapting, busy (3) | story, echo | — |
| Find | score | getting it, a lift (3→4) | story, statement | arrive |
| Take | score | the cost: heavy, then nothing (4→1) | story, echo, minor | drop |
| Return | under | home again, quieter (2) | story, echo | — |
| Change | score | the opening's music, changed (2) | story, statement, changed | the end |

**Example:** A typical *Rick and Morty* episode: Morty wants something → an adventure in
another dimension → he gets it → it goes horribly wrong → he's back home, a little more
jaded or a little wiser.

**Pitfalls:**
- Making "Find" the end. The price (step 6) is where the meaning is.
- A change that's purely external. Step 8 should be a shift in the character's
  understanding.
- Forgetting that steps 1 and 8 should visibly mirror each other.

---

### 2.4 Kishōtenketsu (Four-Act Structure)

**Origin:** Classical Chinese poetry (起承轉合, *qǐ chéng zhuǎn hé*), adopted in Japanese
(起承転結) and Korean narrative. It's the basis of four-panel *yonkoma* comics.

**Pitch:** A structure that doesn't need conflict. Rather than a protagonist beating an
opponent, it builds on contrast and revelation. The story is set up and developed, then
something unexpected (and seemingly unrelated) appears, and the ending reconciles the two to
give a new understanding.

**Best for:** Slice-of-life, quiet or contemplative pieces, children's stories without
villains, poetry-like shorts and gentle twists.

**Beats:**

| Act | Beat | What happens | ~% |
|---|---|---|---|
| Act 1 | **Ki (起): Introduction** | Establish the characters, setting and situation. Calm, observational. | 0–25 |
| Act 2 | **Shō (承): Development** | Deepen and expand the introduction without any big change. More texture, routine and detail. | 25–50 |
| Act 3 | **Ten (転): Twist** | An unexpected element or a big shift in perspective. It may seem unrelated at first. | 50–75 |
| Act 4 | **Ketsu (結): Conclusion** | Link the twist back to the premise. The resolution comes from combining the two, not from defeating someone. | 75–100 |

**Music:**

| Beat | Music | Mood (energy) | Theme | Hit |
|---|---|---|---|---|
| Ki (起): Introduction | score | calm, observational (1→2) | story, statement | — |
| Shō (承): Development | under | texture, routine, gently moving (2) | story, echo | — |
| Ten (転): Twist | score | something new: another colour, another instrument (3) | a new figure, not the story's | turn |
| Ketsu (結): Conclusion | score | the two together, understanding (2) | story, statement, in the twist's colour | the end |

**Example:** *My Neighbor Totoro*: a family moves to the countryside (Ki) → everyday life,
exploring and settling in (Shō) → the forest spirits appear, and later Mei goes missing
(Ten) → the spirits help, the family reunites, and the world is seen with new wonder
(Ketsu). In four comic panels: a girl waits at a bus stop in the rain → she waits longer and
gets soaked → a stranger walks by holding two umbrellas → he hands her one, and he's her
father, who came to meet her.

**Pitfalls:**
- Sneaking in a villain to manufacture tension. Trust the contrast.
- A twist that's just random. It has to recontextualize the setup.
- A long Shō with no texture. The development should still be interesting to watch: vary the
  sizes and the camera from shot to shot.

---

## 3. Moral, allegorical & folk

These are historical structures for delivering a lesson, a thematic truth or a cultural
warning through tight, symbolic plotting.

### 3.1 The Fable (Aesop's Formula)

**Origin:** Aesop (ancient Greece), later La Fontaine and the Panchatantra.

**Pitch:** A tightly compressed structure. Its characters are usually animals or objects,
each embodying one human trait (pride, greed, laziness). The story moves straight from the
flaw to an immediate, often ironic consequence and ends with an explicit moral.

**Best for:** Bedtime and children's stories, very short episodes, and any piece where a
clear lesson is the point.

**Beats:**

| Act | Beat | What happens | ~% |
|---|---|---|---|
| Act 1 | **Character & Trait** | Introduce the character and their defining flaw or virtue quickly, often through a single action or line. | 0–15 |
| Act 2 | **Situation / Temptation** | A situation that tests the trait: a contest, a find or an encounter. | 15–35 |
| Act 3 | **The Choice** | The character acts in line with their flaw. | 35–60 |
| Act 4 | **Consequence** | The result follows immediately and is often ironic. The flaw backfires (or the virtue pays off). | 60–85 |
| Act 5 | **Moral** | The lesson, stated outright by a narrator or a character ("Slow and steady wins the race"). | 85–100 |

**Music:**

| Beat | Music | Mood (energy) | Theme | Hit |
|---|---|---|---|---|
| Character & Trait | score | light, characterful: the trait in one instrument (2) | story, statement | — |
| Situation / Temptation | score | playful, building (2→3) | story, echo | turn |
| The Choice | under | a wrong note, uneasy (3) | story, echo, bent | — |
| Consequence | score | ironic or sad: the flaw backfiring (3→2) | story, echo, minor | drop (at the backfire) |
| Moral | under | warm, simple, under the narrator (1) | story, statement, soft | the end |

**Example:** *The Tortoise and the Hare*: the boastful Hare challenges the Tortoise → the
race → the Hare naps because he's overconfident → the Tortoise wins → "Slow and steady wins
the race."

**Pitfalls:**
- More than one flaw or theme. A fable makes one point.
- A consequence that doesn't follow directly from the trait. It should feel inevitable and
  fitting.
- A moral that preaches beyond what the story actually showed.

---

### 3.2 The Parable

**Origin:** Religious and wisdom-literature traditions (the Gospels, Buddhist sutras, Sufi
and Zen teaching stories).

**Pitch:** Like a fable, but with human characters in realistic, everyday situations. The
surface story is ordinary; the meaning underneath is spiritual, ethical or philosophical.
The lesson is often left for the audience to recognize, and it usually overturns an
expectation.

**Best for:** Ethics-driven drama, anthology episodes, stories about kindness, judgment or
moral courage, and grounded realism with a message.

**Beats:**

| Act | Beat | What happens | ~% |
|---|---|---|---|
| Act 1 | **Ordinary Situation** | A recognizable, everyday setting: work, family, a road, a field. | 0–20 |
| Act 2 | **Expected Pattern** | Set up who the audience *expects* to act well or badly, or how things "should" go. | 20–40 |
| Act 3 | **The Test** | Someone in need, a choice or an opportunity appears. | 40–60 |
| Act 4 | **The Reversal** | The unlikely person does the right thing, or the expected one fails. | 60–85 |
| Act 5 | **Recognition** | The meaning lands, through a closing question, a quiet image or the consequence. It's rarely stated outright. | 85–100 |

**Music:**

| Beat | Music | Mood (energy) | Theme | Hit |
|---|---|---|---|---|
| Ordinary Situation | under | plain, everyday (1→2) | story, statement, simple | — |
| Expected Pattern | under | assured, conventional (2) | story, echo | — |
| The Test | score | a question hanging (2→3) | story, echo | turn |
| The Reversal | score | surprise, tender (3) | story, statement, warm | arrive |
| Recognition | under | quiet, open, unresolved (1) | story, echo, left hanging | the end |

**Example:** *The Good Samaritan*: a traveler is beaten and left by the road → a priest and
a Levite (the expected helpers) pass by → a Samaritan (the despised outsider) stops and
cares for him → "Which of these was a neighbor?"

**Pitfalls:**
- Spelling out the meaning. A parable trusts the audience.
- Characters who are just symbols. Keep them human and plausible.
- No reversal. Without a subverted expectation, it's just an anecdote.

---

### 3.3 The Cautionary Tale

**Origin:** Folk tradition: European folktales, *Struwwelpeter* (1845), Hilaire Belloc's
*Cautionary Tales for Children*, and modern horror and urban legends.

**Pitch:** A plain story designed as a warning. A character breaks a clear rule, taboo or
warning, enjoys a short stretch of success or thrills, and is then met with swift and often
severe punishment that serves as an example.

**Best for:** Horror, dark comedy, children's warnings, anthology episodes (*Twilight Zone*,
*Black Mirror* style) and morality plays.

**Beats:**

| Act | # | Beat | What happens | ~% |
|---|---|---|---|---|
| **The Rule** | 1 | **The Rule / Warning** | State the rule clearly: from a parent, a sign, an elder or a strange shopkeeper. | 0–15 |
| | 2 | **The Temptation** | Show why breaking it is appealing. | 15–25 |
| **The Fall** | 3 | **The Transgression** | The character breaks the rule, often casually or defiantly. | 25–35 |
| | 4 | **The Thrill** | At first it pays off. Fun, gain, power. The audience is lulled. | 35–60 |
| **The Reckoning** | 5 | **Warning Signs** | Small hints that something is wrong. They're ignored. | 60–75 |
| | 6 | **The Punishment** | A swift, fitting and often disproportionate consequence. | 75–95 |
| | 7 | **The Example** | A final image or line that turns the character into a warning for others. | 95–100 |

**Music:**

| Beat | Music | Mood (energy) | Theme | Hit |
|---|---|---|---|---|
| The Rule / Warning | under | ominous, a low hint (2) | story, statement, low | — |
| The Temptation | score | alluring, sweet (2→3) | story, echo, bright | — |
| The Transgression | sting (at its start) | a sly turn (3) | story, echo | turn |
| The Thrill | score | fun, carefree, too bright (3→4) | story, echo, bright | — |
| Warning Signs | under | something off: a sour note under the fun (3) | story, echo, a note wrong | — |
| The Punishment | score | dark, sudden (4→5) | story, echo, dark | turn, then drop at its end |
| The Example | under | cold, still (1) | story, echo, a fragment | the end |

**Example:** *Gremlins*: three rules (no bright light, no water, never feed after midnight)
→ a cute pet → the rules are broken → chaos → a town in ruins and the pet taken back. *The
Boy Who Cried Wolf* is the children's version.

**Pitfalls:**
- Not establishing the rule clearly up front. The audience must know it was broken: say it
  in a line, or show it (a sign in an insert).
- A punishment that doesn't fit the crime thematically. Poetic justice is what makes it
  satisfying.
- Too much sympathy without a payoff. Decide whether the tone is grim, darkly comic or
  tragic.

---

## 4. Structural geometry & plot-driven shapes

These structures are defined by the shape of the tension curve or by rearranging the
timeline.

### 4.1 Freytag's Pyramid (Five-Act Structure)

**Origin:** Gustav Freytag, *Die Technik des Dramas* (1863), based on classical Greek and
Shakespearean drama.

**Pitch:** A strict, symmetrical shape. The action rises to a climax in the *middle*, the
turning point where the protagonist's fortunes reverse, then falls to a denouement that ends
in either catastrophe (tragedy) or resolution.

**Best for:** Tragedy, prestige drama, rise-and-fall stories (crime, ambition, hubris) and
stories where the second half shows the fallout.

**Beats:**

| Act | Beat | What happens | ~% |
|---|---|---|---|
| Act I | **Exposition** | The world, characters and tensions. It ends with the *exciting force* (the inciting incident). | 0–20 |
| Act II | **Rising Action** | Complications build. The protagonist pursues the goal and tension climbs. | 20–45 |
| Act III | **Climax (Turning Point)** | The peak at the center: the decisive action that turns the protagonist's fortune. | 45–55 |
| Act IV | **Falling Action** | The consequences unfold and opposing forces gain ground. It includes a *moment of final suspense*, where the outcome seems briefly in doubt. | 55–85 |
| Act V | **Denouement** | The final outcome: **catastrophe** (the tragic fall) or **resolution** (order restored). | 85–100 |

**Music:**

| Beat | Music | Mood (energy) | Theme | Hit |
|---|---|---|---|---|
| Exposition | score | the world, tension under it (2) | story, statement | turn (at the exciting force) |
| Rising Action | score | climbing (3→4) | story, echo | — |
| Climax (Turning Point) | score | the peak, decisive (5) | story, statement, full | arrive |
| Falling Action | score | slower, heavier, a hush at the final suspense (3→2) | story, echo, minor | — |
| Denouement | score | catastrophe: dark and spare; resolution: calm (1→2) | story, statement, changed | the end |

**Example:** *Macbeth*: the witches' prophecy (exposition) → the murder of Duncan and the
rise to power (rising action) → Banquo's murder and Fleance's escape (the turning point) →
the descent into paranoia and the gathering opposition (falling action) → Birnam Wood,
Macduff and Macbeth's death (catastrophe).

**How it differs from three-act:** In three-act the climax comes near the end. In Freytag
it's in the middle, and the second half is about the consequences.

**Pitfalls:**
- A flat second half. The falling action still needs tension (the "moment of final
  suspense").
- A climax that's just a big event. It must *reverse* the protagonist's direction.

---

### 4.2 The Fichtean Curve

**Origin:** Described by John Gardner in *The Art of Fiction* (1983), and named after the
philosopher Johann Gottlieb Fichte. It's common in thrillers, pulp and short fiction.

**Pitch:** A high-intensity shape that skips the long setup. It drops characters straight
into the inciting crisis, then delivers a rapid series of crises, each bigger than the last,
separated by brief breathers, until a final, explosive climax. Exposition is woven in during
the action, and the falling action is short.

**Best for:** Thrillers, action, horror, survival stories, cliffhanger serials and short
episodes that need to hook immediately.

**Beats:**

| Act | # | Beat | What happens | ~% |
|---|---|---|---|---|
| **First Crisis** | 1 | **Immediate Inciting Crisis** | Open in trouble. Backstory is shown only as it becomes necessary. | 0–10 |
| | 2 | **Crisis 1** | The first obstacle. The protagonist reacts. | 10–25 |
| | 3 | **Breather** | A short pause to reveal character, give exposition and regroup. | 25–30 |
| **Second Crisis** | 4 | **Crisis 2** | A bigger obstacle. The stakes rise. | 30–45 |
| | 5 | **Breather** | A shorter pause. Maybe a revelation. | 45–50 |
| **Escalation** | 6 | **Crisis 3+** | Keep escalating, with each crisis worse than the last. | 50–80 |
| **Climax** | 7 | **Climax** | The biggest confrontation of all. | 80–95 |
| | 8 | **Brief Falling Action** | A short resolution. Get out fast. | 95–100 |

**Music:**

| Beat | Music | Mood (energy) | Theme | Hit |
|---|---|---|---|---|
| Immediate Inciting Crisis | score | urgent, already in it (4) | story, statement | turn (on the first shot) |
| Crisis 1 | score | driving (3→4) | story, echo | — |
| Breather | under | a breath, quiet (1) | story, echo, soft | — |
| Crisis 2 | score | bigger (4) | story, echo | turn |
| Breather | dry | the silence is the breath | — | — |
| Crisis 3+ | score | each harder than the last (4→5) | story, echo | turn (each) |
| Climax | score | everything (5) | story, statement, full | arrive |
| Brief Falling Action | score | out fast, a short release (2) | story, echo | the end |

**Example:** *Mad Max: Fury Road*: Max is captured in the first minutes, followed by one
escalating chase after another with short quiet stretches (the night in the bog, the Many
Mothers), ending in the final chase back to the Citadel.

**Pitfalls:**
- Crises that are bigger but not *different*. Each one should change the situation or reveal
  something new.
- No breathers. Without contrast, the intensity goes numb. Pace them in the shots too:
  short, moving shots for a crisis, longer and stiller ones for a breather.
- Characters who are only reacting. Use the breathers to show who they are.

---

### 4.3 In Medias Res (Flashback Structure)

**Origin:** Latin for "into the middle of things" (Horace). It goes back to Homer, since
*The Odyssey* opens late in the journey. The modern TV form opens with a flash-forward ("72
hours earlier…").

**Pitch:** The story opens in the thick of the action or at a late-stage crisis. Once the
hook is set, it jumps back to explain how the characters got there, catches up to the
opening scene (now understood differently) and carries on to the finale.

**Best for:** Hooking an audience fast, mysteries, crime, dramatic irony (we know where it's
heading, but not how), and cold opens.

**Beats:**

| Act | # | Beat | What happens | ~% |
|---|---|---|---|---|
| **The Hook** | 1 | **The Hook** | A vivid, puzzling, high-stakes moment from late in the story. Withhold the context. | 0–5 |
| | 2 | **The Jump Back** | A clear time marker ("Three days earlier", a title card, a match cut). | 5–7 |
| **The Calm** | 3 | **The Calm / Build-Up** | The story from an earlier, calmer point: who they were and what they wanted. | 7–30 |
| **The Slide** | 4 | **The Slide** | Each step leads toward the hook. Underneath can be any structure, often three-act. | 30–65 |
| **Convergence** | 5 | **Convergence** | The timeline catches up to the opening scene. Replay it with the new understanding: what it *really* meant. | 65–75 |
| **Past the Hook** | 6 | **Continuation & Climax** | Push past the opening moment into the true climax. | 75–95 |
| | 7 | **Resolution** | Resolve the aftermath. | 95–100 |

**Music:**

| Beat | Music | Mood (energy) | Theme | Hit |
|---|---|---|---|---|
| The Hook | score | tense, unexplained (4) | story, statement, in pieces | drop (at the cut away) |
| The Jump Back | sting (at its start) | time turned back (2) | — | turn |
| The Calm / Build-Up | as the structure underneath | that structure's Music table | story, echo | — |
| The Slide | as the structure underneath | that structure's Music table | story, echo | — |
| Convergence | score | the hook's music again, now understood (4) | story, statement, as in the hook | arrive |
| Continuation & Climax | score | past it, to the peak (5) | story, statement, full | arrive |
| Resolution | score | the aftermath (2) | story, echo, soft | the end |

**Example:** *Breaking Bad* pilot: a man in his underwear and a gas mask crashes an RV and
records a goodbye video with a gun in hand (the hook) → "three weeks earlier" he's a mild
chemistry teacher → the build-up → the RV scene again, now understood → the sirens turn out
to be fire trucks, not police.

**Pitfalls:**
- A hook that's just random action. It should raise a specific question ("How did he end up
  here?").
- A convergence that adds nothing. The replayed scene should land differently the second
  time. It can reuse the hook's shots: the same take placed twice in the cut, or new shots
  with the same location, size and camera so the two match.
- Using it to disguise a slow start instead of fixing one.
- An unclear time jump. Make it unmistakable (a card, a change of light or look) so viewers
  don't get lost.

---

## 5. Also worth knowing

### 5.1 The Pixar Story Spine

**Origin:** Kenn Adams, an improv teacher, popularized by Pixar storyboard artist Emma
Coats.

**Pitch:** A fill-in-the-blanks chain of cause and effect. It's very fast to outline with,
and its natural rhythm ("because of that…") suits narration. It pairs well with a Fable
ending.

**Beats:**

| Act | # | Prompt | What it does | ~% |
|---|---|---|---|---|
| **The World** | 1 | **Once upon a time…** | The character and the world. | 0–10 |
| | 2 | **Every day…** | The routine, the status quo. | 10–20 |
| **The Chain** | 3 | **Until one day…** | The disruption. | 20–30 |
| | 4 | **Because of that…** | The first consequence. | 30–50 |
| | 5 | **Because of that…** | The next consequence (repeat as needed, with each caused by the last). | 50–70 |
| **The End** | 6 | **Until finally…** | The climax and resolution. | 70–90 |
| | 7 | **And ever since then…** | The new normal. | 90–100 |
| | (8) | **And the moral is…** | *Optional:* add this when combining with the Fable. | — |

**Music:**

| Beat | Music | Mood (energy) | Theme | Hit |
|---|---|---|---|---|
| Once upon a time… | score | gentle, wondering (2) | story, statement | — |
| Every day… | under | light, a simple repeating figure: the routine (2) | story, echo | — |
| Until one day… | score | curious, a lift: something new (2→3) | story, echo | turn |
| Because of that… | score | unsettled (3) | story, echo, darker | — |
| Because of that… (again) | score | rising, each one darker (3→4) | story, echo, low | — |
| Until finally… | score | a hush at the low point, then warm (1→3) | story, statement | arrive |
| And ever since then… | score | warm, slowing to a close (2→1) | story, statement, soft | the end |
| (And the moral is…) | under | quiet, simple (1) | story, echo | — |

**Example:** *Finding Nemo*: once upon a time there was a widowed fish, Marlin, who was very
protective of his only son, Nemo. Every day, Marlin warned Nemo about the ocean's dangers.
One day, Nemo swam out to sea in defiance. Because of that, he was caught by a diver.
Because of that, Marlin set out across the ocean to find him… Until finally, Marlin and Nemo
found each other and learned that love depends on trust. And ever since then, Marlin has
let Nemo live his own life.

**Pitfalls:** Every "because of that" must actually be *caused* by the previous one. If the
honest link is "and then", the chain is broken.

---

## Combining structures

Structures can be stacked at different levels:

- **Season arc + episode shape:** A season can follow the Hero's Journey (or its 27 beats) or
  the Virgin's Promise while each episode uses the Story Circle, Sitcom or three-act
  structure. Each episode can then map to one or two stages of the season arc.
- **A-plot / B-plot:** Use different structures in parallel. For example, a three-act A-plot
  can carry a Kishōtenketsu B-plot that delivers the thematic twist.
- **Frame + core:** In Medias Res is a *frame*. The section after the jump back still needs
  its own structure (usually three-act or Fichtean).
- **Spine + fable:** The Story Spine gives the cause-and-effect chain, and the Fable gives the
  flaw → consequence → moral.
- **Scene level:** The Story Circle and Kishōtenketsu both scale down to a single scene or
  sequence.

In a script, `// structure:` names the episode's own shape (the season arc lives in the
outline), and the `// beat:` lines use that structure's beat names: in a frame, the frame's
(In Medias Res: Build-Up), with the core's beats inside it marked by the core's names; in a
spine + fable, the Spine's.

## Choosing by need

| If the user wants… | Suggest |
|---|---|
| A clear lesson for kids, in under 5 minutes | Fable, Story Spine, Cautionary Tale |
| A gentle, conflict-free, wonder-filled piece | Kishōtenketsu |
| A repeatable half-hour comedy | Sitcom Formula |
| A repeatable half-hour with real (small) change | Story Circle |
| A drama series: a case each episode, a story across them | Episodic Drama |
| A satisfying standalone drama | Three-Act |
| A grounded story about doing the right thing | Parable |
| A big transformation across many episodes | Hero's Journey or its 27 beats (outward), Virgin's Promise (inward) |
| Tragedy, or rise and fall | Freytag's Pyramid |
| Nonstop tension from the first shot | Fichtean Curve |
| An opening hook that grabs immediately | In Medias Res (wrapped around another structure) |
