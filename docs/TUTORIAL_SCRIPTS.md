# Tutorial scripts

What to show and what to say, for filming. Not part of the docs site. Each section is **SCREEN**
(do this) then **SAY** (read this). Lines in [brackets] are yours to fill from your own work.

Record the wizard first: it makes the episode the storyboard tutorial uses.

## Before you record

- A clean projects folder, with no show called First Light.
- A free local image model, so **Make the pictures** and **Sketch** run without a paid prompt.
- One folder on the desktop to drag from, holding:
  - `frame1.png`, `frame2.png`, `frame3.png`, `frame4.png`, `frame5.png` and `frame10.png`, rough
    stills or sketches (`frame10` shows that it lands after `frame2`)
  - `pier_walk.mp4`, a short clip of a few seconds
- ComfyUI or `seriesmith serve` freshly restarted, the page refreshed, Simple mode showing.
- The Guide and Storyboard windows closed. They remember where they were, so set them where the
  camera can see them.

The running example: series **First Light**, episode **The Pier**, seven minutes, one character
(June) and one place (the pier).

---

## Tutorial 16: From an idea to a film (about 4 minutes)

### 1. Why this exists (0:00)

**SCREEN:** The editor in Advanced, Shots tab and timeline full of a real episode. Hold on it.

**SAY:** seriesmith turned into an editing workhorse. Timelines, references, sound, finishing. Fine
once you're in the middle of a show, and a lot to look at when all you have is an idea. So there's
one way in now. Six steps, from an idea to something you can watch. The settings are all still
there. You just don't have to meet them first.

### 2. Open the wizard (0:25)

**SCREEN:** Switch to **Simple**. Press **A series…**. The wizard opens on **1. Idea**. Move the
pointer along the **Start from** row without clicking.

**SAY:** Five ways to start. A story structure, a script you already have, your own agent, a single
shot, or an edit from Premiere or Resolve as FCP7 XML. There's no script writer in here, on purpose.
If you want a script written, use the script-writing skill in whatever agent you already use and
send it in over MCP. Today we'll start from a structure.

### 3. Idea (0:50)

**SCREEN:** **A structure** stays selected. Type **First Light** in **Series title**. Pick a look.
Open **More: folders, model, sizes**, let it sit a beat, close it.

**SAY:** A title and a look. Everything under More is filled in for you: the folders, the model, the
sizes. Open it when you care. Close it when you don't.

### 4. Story (1:15)

**SCREEN:** Press **2. Story**. Choose **The Change Arc (Three-Act Structure)**. Enter **7** in
**Minutes**.

**SAY:** Pick a structure and a length. Nothing here is a commitment. It sets targets for each beat,
and you can stray from them as far as you like.

### 5. Cast and places (1:35)

**SCREEN:** Press **3. Cast and places**. Add a character: name **June**, a one-line design. Add a
location: **pier**, a one-line description.

**SAY:** Who and where. A name and a sentence each. That sentence is what the picture gets drawn from,
so say what someone could actually draw.

### 6. Create, and the guide (2:00)

**SCREEN:** Press **Create ep01**. The **Guide** window opens, showing **Cast and places** and the
pictures to make. Press **Make the pictures**. Wait, or cut to them done.

**SAY:** Create writes two ordinary files, a series config and a script, and from here the guide takes
over. It tells you where the episode has got to and what's next. These pictures are what keeps June
looking like June from shot to shot.

### 7. The guide works it out (2:35)

**SCREEN:** The guide moves on to **Storyboard**. Close it with the X. Click around the editor. In
the Shots tab press **Guide…**. It comes back on the same step.

**SAY:** The guide keeps no record of its own. It reads the script, the pictures and the takes, and
works out the step from those. Close it, work somewhere else for a week, come back. Same place.

### 8. Storyboard, Film, Watch (3:00)

**SCREEN:** Press **Open the storyboard**, show it, close it. In the guide press **Film**, then
**Watch**, pausing on **Film them**, then **Play all** and **Export…**.

**SAY:** Storyboard is its own tutorial, so here's the short version: block it in, see it, give the
shots a model. Film renders whatever's on a model and has no take yet. A shot with no model waits,
and the guide tells you how many. Watch is Play all and Export.

### 9. Close (3:40)

**SCREEN:** Back to the wizard's **Start from** row, or the finished episode.

**SAY:** It's a first pass at this. Simple still takes you through a separate wizard and then the
guide, and it's a little clunky. [What you've found after using it.] What did you expect to be
able to do in the first five minutes that it doesn't let you do?

---

## Tutorial 15: The storyboard (about 5 minutes)

Uses The Pier from Tutorial 16. Replaces nothing: there is no earlier video.

### 1. See it before you pay for it (0:00)

**SCREEN:** The Pier open. In the Shots tab press **Storyboard…**. Hold on the empty board: act
rows, beats as bars, each with a target.

**SAY:** [A time you rendered too much before you knew the story worked.] The board is for finding
out cheaply. Every act is a row, every beat a bar, and each bar says how far it is from its target.
And it's not a separate file. An unfinished storyboard is an unfinished script.

### 2. The targets (0:30)

**SCREEN:** Hover a beat's bar to show its guidance. Change **Minutes** and watch the targets move.
Change it back.

**SAY:** Hover a beat to read what should happen there. Minutes only moves the targets. It never adds
or removes a shot.

### 3. Block it in (0:55)

**SCREEN:** Press **One per beat**. Press **+** on one beat. Right-click a tile, **Add shot after**.
Drag a tile somewhere else.

**SAY:** One shot on every beat, and the whole story exists from start to end. Plus adds one. Right-click
adds one exactly where you want it. Drag to reorder. These are real shots with no model yet, on a
gray card, so you can already render and watch them.

### 4. Drop pictures in (1:30)

**SCREEN:** Undo with **Ctrl+Z** until a beat is empty, or use a beat with no shots. Show the dashed
**Drag pictures or videos here for a shot each**. Drag all six frames onto it. Six shots
appear in order. Press **Ctrl+Z** once: all six go. **Ctrl+Shift+Z** to bring them back.

**SAY:** Got sketches already? Drop them on a beat. One new shot per picture, in filename order, and
frame2 comes before frame10. It's one undo, for all of them.

### 5. Drop a video (2:05)

**SCREEN:** Drag `pier_walk.mp4` onto a beat's **+**. A new shot appears at the end of the beat.
Double-click it to play. Close the viewer.

**SAY:** Same plus, with a video. It gets a shot of its own at the video's length, and the clip is that
shot's take, already in the cut. So a board can mix sketches with footage you already have. Reference
clips, a scene you shot on your phone, whatever you've got.

### 6. Sketch (2:35)

**SCREEN:** Select a shot with no picture. Press **Enter**. Replace the action with "June walks
to the end of the pier at dawn", set `who` to June, save. Do one more. Leave one alone. Press
**Sketch (2)**. Show the jobs running, the note naming the shot left out, then the tiles filling in.

**SAY:** No pictures at all? Write what happens, and Sketch draws a first frame for each shot, using
your cast's pictures. One still per shot. It won't touch a picture you've put there, and it skips any
shot still carrying the beat's guidance, because all it could draw is the guidance. That note up
top names them.

### 7. The animatic (3:20)

**SCREEN:** Press **Render held**. When it's done, press **Play all**. Let it play for several
seconds.

**SAY:** Render held makes a clip from every picture, at each shot's length, on this machine, for free.
And that's an animatic. The whole film, in order, at its planned length. Your video clip stays as it
is. Now you can tell if the story works.

### 8. From no model to a model (4:00)

**SCREEN:** Right-click a beat, **Convert held shots**, pick a model. Open Edit Shot on one shot to
show its model. Do not render.

**SAY:** When a stretch is ready, convert it. This changes the model and nothing else. Check what you're
converting first: a shot you never rewrote still says the beat's guidance, and that's what the model
gets sent. A paid model charges for it like any other render.

### 9. Close (4:35)

**SCREEN:** The full board, with pictures on it.

**SAY:** Every edit here is an ordinary script line, so you can walk off to the script editor and come
back. Next, film it, or see the guide for the whole path. How do you plan a film right now, before
any of this?

---

## Check on the day

Labels here were read from the code on 2026-11-09. Two things were not confirmed in the running app:

- The wizard's buttons for adding a character and a location, and the name of the structure list
  (Tutorial 16, sections 4 and 5).
- Which step the guide lands on right after Create, with no shots yet (section 6). It should be
  Cast and places while pictures are missing.
