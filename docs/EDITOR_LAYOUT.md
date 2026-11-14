# The editor's layout: plan

The plan for a pass over the editor's layout and style, from the audit of 2026-11-13/14
(the page run on a copy of a real episode at 1600×1000 and read screen by screen). Nothing
here is built yet. Each item says what changes, where, and what stays as it is; the
checklist at the end is the work in order.

Status: **agreed 2026-11-14**, in work. What was open (the toolbar's labels, the take
strip, the seed) is decided and written in below.

## What the audit saw

At 1600×1000 the Shots panel is 380 px wide and spends about 465 px on controls before the
first shot row, so eight shots show. An episode is 280 shots or more: the list is the
panel's job and gets half of it. The episode's title is cut short in three places while
the top bar is nearly empty; the proxy / final toggle is drawn in four; nine icon buttons
sit in a row without labels; a shot row can carry six badges in five colours at the same
weight, several of them the code's own identifiers; the viewer is black, with a hint, while
an episode is open; and buttons come in five styles, with some selects and number fields
left as the browser draws them.

## The three hosts

The same components run in three places, and the plan has to hold in each:

- **The standalone page** (`web/standalone.html`, `web/src/standalone.tsx`): its own top bar
  (`#sm-top`), the panel with the Shots and Refs tabs, the docked viewer, the timeline below.
- **ComfyUI** (`web/src/comfy.ts`): the Shots and Refs panels are sidebar tabs and the
  timeline a bottom panel tab. There is no top bar of ours, and the timeline can be open
  with the sidebar closed.
- **The dev page** (`web/src/dev.tsx`, `npm run dev`, `/dev.html`): the panels side by side
  at ComfyUI's widths on the mock API, with no top bar. It is where the ComfyUI side of
  each step is looked at.

So "moves to the top bar" below means the standalone page. In ComfyUI the same control
stays at the head of the panel it is in, on one line.

## 1. The Shots panel's top section

Today (`ShotsTab.tsx`): the episode's head (`EpisodeHeader`, line 113), the toolbar (682),
then `BuildBar` (156): the model line, proxy / final, Build, Re-render stale, Storyboard,
Guide, Generate missing, the multi-selection bar, the pass's progress, then the missing
refs line and the recording's line (`TrackLine`).

Change:

- **The episode card collapses.** A chevron on the card (`h3-epcard`) folds it to one line:
  the model, the pass, the progress ("11/11"), and counts that need something ("3 missing ·
  7 stale"). Open or folded is remembered in the browser (the editor's own
  `seriesmith.editor.v1` state), per host. The recording's line folds with it.
- **Folded, what needs doing still shows.** The one line's counts are buttons: "3 missing"
  queues them as Generate missing does, "7 stale" as Re-render stale does (the same paid
  confirmation as today). A build that failed opens the card.
- **Generate missing is the big button only when something is missing.** With every shot
  rendered it is not drawn as a wide greyed button; the progress line says so.
- The filter, List / Board and Gallery row is not part of the card and stays where it is.

Stays: every control in the card, its behaviour, the order inside it.

## 2. The episode's name, once and whole

Today the show and episode are named in the panel's head ("ep01 — Dean anc", cut short), in
the timeline's bar (`EpisodeSelect`, cut short at 170 px, `styles.css:1252`) and in the
storyboard's and gallery's own heads.

Change:

- **Standalone:** the show and episode switcher moves to the top bar, left, after the mark,
  with room for the whole title. The panel's head loses the title and keeps Refresh and
  Simple / Advanced on one line. The timeline's bar loses its episode select.
- **ComfyUI:** the picker stays where it is, at the head of the Shots panel, above the
  toolbar, under the Render on / Jobs / Settings lines. What changes there is only that
  the title isn't cut: the show's name, Refresh and Simple / Advanced share one line, and
  the episode's title has the line under it to itself, the panel's whole width (a tooltip
  with all of it when it is still too long). It opens the same list of episodes as now.
  The timeline's bar keeps its select, since that panel can be open alone.
- The storyboard and the gallery keep theirs: each is a window over the page, and covers
  the top bar on a small screen.

## 3. Proxy / final, once

Today `PassToggle` is drawn in `BuildBar` (`ShotsTab.tsx:184`), the Refs tab
(`RefsTab.tsx:1494`), the timeline's bar (`Timeline.tsx:671`) and the Inspector
(`Inspector.tsx:621`). All four set the same value.

Change:

- **Standalone:** one toggle in the top bar, beside the episode. The other four go.
- **ComfyUI:** one in each panel that can be open alone: the Shots panel's episode card
  (on the line that stays when the card is folded, section 1), the Refs panel's bar, the
  timeline's bar. The Inspector's goes.

## 4. The toolbar

Today eleven buttons in three groups (`ShotsTab.tsx:682-702`), nine of them icons only:
`+ Shot`, edit the shot, inspect the shot · the script, series settings, `series.json` as
text, the recording · Play all, the timeline, Issues, the Refs tab.

Change: the ones used through a session carry a label; the rest go behind one `More` menu,
each with its name.

- Labelled: **+ Shot**, **Script**, **Series**, **Issues** (with its count, as now).
- In `More`: edit the selected shot, inspect the selected shot, `series.json` as text, the
  recording.
- **Standalone:** Play all, Open the timeline and Open the Refs tab are dropped from the
  toolbar: the first two are in the timeline's bar, always on the page, and the Refs tab
  is above.
- **ComfyUI:** the timeline is a bottom panel that is opened from here, so **Timeline** is
  a fifth labelled button in the toolbar, never in `More`, and Play all stays beside it as
  its icon. Open the Refs tab goes in `More` (Refs is a sidebar tab of its own there).
- The ComfyUI panel can be narrower than the standalone one; the labelled buttons wrap to
  a second line there, as the toolbar does today, and none is hidden.

## 5. Badges

Today `shotBadges` (`lib/format.ts:83-142`) can add fifteen kinds to a row, the sound chip
and the model chip beside them, each a pill with its own colour (`styles.css` has 32
`h3-b-*` classes). In the episode looked at, seven of eleven rows said `stale`, and every
take under the viewer said `ok` and `stale`.

Change:

- **Three levels, three looks**, in place of a colour per kind:
  - *wrong* (failed, pick unusable, missing refs): the error colour, filled.
  - *needs a look* (stale, override stale, placeholder, no takes, orphan): the warning
    colour, outlined.
  - *a fact* (left out, moved, trimmed, override, the upscale's `2x`, the model, a
    continuity mode): grey, outlined.
  - *working* (rendering, queued) keeps its own look, since it moves.
- **Two on a row, then a count.** A row shows its two most serious badges and `+3`; the
  count's tooltip lists the rest with their reasons, and an expanded row shows them all.
- **Locked is a mark, not a pill.** Lock is the shot's approved take; it shows as a lock
  icon at the row's head and on the timeline's clip, always, outside the count of two.
- **Words, not identifiers.** `dub_keep_foley` reads "dub + foley" (the full name in the
  tooltip); `ovr: prompt` reads "prompt edited"; `cand.` reads "takes". The script's and
  the API's own names don't change.
- **Under the viewer, a take says only what is unusual.** `ok` is not drawn; a failed,
  stale or flagged take keeps its badge.
- **On the timeline**, a clip too narrow for a badge's words shows its level as a coloured
  edge, and the words in the tooltip, in place of "sta".

Stays: every badge's meaning and tooltip text, the check badges' own rules, what the
filter matches.

## 6. The viewer is never empty

Today the docked viewer shows "Open an episode, then double-click a take" with an episode
open (`standalone.html:116`).

Change (standalone, where the viewer is docked):

- Opening an episode shows the first shot's take in the cut, paused.
- Selecting a shot (one click) shows its take in the cut, paused. Double-click and the
  play icon play it, as now.
- The hint shows only with no episode open, and says only that.

In ComfyUI the viewer is a window of its own and is not opened by a selection; a selection
moves it only when it is already open.

## 7. The timeline

Not changing: the default zoom. Episodes run to 280 shots and more, so fitting the cut to
the width is wrong; the zoom stays as it is, and as the user left it.

Change:

- **The clips' height and the sound lanes' share a splitter.** Today a lane is 22 px
  (`SoundLanes.tsx:76`) and the clips take the rest, so a short clip is a tall sliver of
  its picture and four lanes share about 90 px. Dragging the line between them trades one
  for the other; the choice is remembered. A shorter clip shows more of its picture's
  width at the same zoom.
- **The last lane is never cut off.** With the panel too short for the clips and every
  lane, the lanes scroll; the Music lane does not run under the window's edge.
- Narrow clips' badges: as section 5.

## 8. One set of controls

Today: outlined buttons (`h3-btn`), the filled primary, segmented toggles (`h3-seg`), text
links used as actions (`h3-link`: "Re-render…", "Relight…", "Fill 2", "Change"), and
selects and number fields, some styled (`h3-in`) and some as the browser draws them (the
storyboard's Structure, Minutes and Shot length; the top bar's Render on).

Change:

- **Every select, number and text field takes `h3-in`** (or the top bar's equal). A sweep
  of the components for the ones without it; the storyboard's bar first.
- **A rule for links and buttons**, written at the head of `styles.css` and followed: a
  button does something; a text link goes somewhere or opens a list. "Re-render…" and
  "Relight…" on a sequence's row become small buttons; "Fill 2" and "Fill act" likewise.
- **One primary on a surface.** The filled teal is for the one thing the surface is for
  (Generate missing, Save, Export); "In the cut" under the viewer, a state, takes the
  state look, not the primary's.

Stays: the palette, the type, both themes.

## 9. The take strip and the take rows

Two places list a shot's takes. The **take strip** is the row of thumbnails under the
video in the viewer (`t01` … `t09`, each with its badges). The **take rows** are the list
that opens under a shot in the Shots panel, each with its seed, date, `Use` and `⋯`.
Neither is the timeline. Both stay.

Change:

- **The take strip becomes a column beside the video**, on its right, as wide as a
  thumbnail and its line of text, scrolling when the takes outnumber its height. It leaves
  the video its height and shows more takes at the viewer's usual shape. The strip's
  clicks are unchanged (click loads A, ctrl-click B, right-click the menu), as is the line
  of actions under the video (Details, New take from, Re-render part of, In the cut). In
  both hosts, and in the viewer's window in ComfyUI. Play all has no strip and is not
  changed.
- **A take row's seed moves to Details.** The row keeps its take, status, badges, date,
  `Use` and `⋯`; the seed and how it was chosen (same, new) are read in Details, where the
  rest of the take's record is.

## Not in this work

Left out on purpose, so the review can tell an omission from a decision:

- The timeline's default zoom, and fitting the cut to the width.
- The storyboard's layout: its width is for an episode's acts and beats, and a short
  episode leaves it empty.
- Anything from the audit's other lists: keys for the review pass, how failures surface,
  reconnecting, batch actions, native confirm dialogs and undo, accessibility, icons and
  fonts from a CDN, the first run, performance, the components' size.
- New functions of any kind. This is layout and style over what is there.

## Checklist

Each line is a commit on this branch. After the last one on a day: `npm run typecheck`,
`npm test`, then `npm run build:standalone` and `npm run build`, both built pages committed.
`docs/EDITOR.md` is corrected in the same commit as the screen it describes.

- [x] 1. The episode and pass in the standalone top bar (sections 2 and 3); the panel's
      head and the timeline's bar lose theirs there; ComfyUI's heads as described.
- [ ] 2. The episode card folds (section 1): the chevron, the one line, the remembered
      state, Generate missing as the big button only when something is missing.
- [ ] 3. The toolbar: four labelled, the rest in `More`; in ComfyUI Timeline labelled
      and Play all beside it (section 4).
- [ ] 4. Badges: the three levels, two and a count, the lock mark, the words, the viewer's
      takes, the timeline's narrow clips (section 5).
- [ ] 5. The viewer shows the selected shot's take (section 6).
- [ ] 6. The timeline's splitter and the lanes' scroll (section 7).
- [ ] 7. The controls: the fields' sweep, links and buttons, one primary (section 8).
- [ ] 8. The take strip as a column beside the video; the take rows' seed in Details
      (section 9).
- [ ] 9. Looked at live in both themes on the standalone page and in ComfyUI, at 1600×1000
      and at a narrow window, on an episode of 280 shots.
