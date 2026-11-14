# The script-writing skill, shorter: plan

The plan for trimming the script-writing skill, from the audit of 2026-11-13/14
(`docs/AUTHORING.md` read whole, section by section, with `tools/make_prompts.py` and the
bundle). Nothing here is built yet.

Status: **agreed 2026-11-14**, in work. What was open (the check's packing, the demo) is
decided and written in below.

## Where it stands

- `docs/AUTHORING.md` is about 20,100 words (1,940 lines). `prompts/SKILL.md` is the whole
  of it under a preamble: 20,500 words, 120 KB, read in full each time the skill loads.
- Two parts are already references, loaded when needed: the screenplay conversion example
  and the story structures.
- The bundle (`prompts/seriesmith-episode-script.zip`) is 188 files against claude.ai's
  limit of 200 (`MAX_FILES`). Three are the skill's text, one is `scripts/check.py` (nine
  lines), and 184 are the real build, core and targets copied as they are. So the check is
  already the codebase's own, not a second one; the trouble is only the count. A new model
  adds one to three files, so there is room for only a few more.
- The MCP server gives a client `SKILL.md` whole as one resource (`seriesmith/mcp.py:58`,
  `724-735`). The preamble names `references/…` files such a client can't read.

## What must hold

1. **Nothing a writer can do today is lost.** A model with the shorter skill writes a
   script and a series config that pass `seriesmith check`, and uses each feature when the
   story calls for it.
2. **One source.** `docs/AUTHORING.md` stays the only place the format is written.
   `SKILL.md`, the references and `seriesmith-script.instructions.md` are all generated
   from it; none is edited by hand.
3. **The one-file instructions still build**, for a client with no references: everything,
   in the document's order.
4. **The docs site's page is the same page.** `tools/make_site_docs.py`,
   `tools/make_refs_md.py` and `tools/sync_starter_doc.py` read the same file and their
   output doesn't change, the markers aside.
5. **One check.** No check written for the skill apart from `seriesmith/build.py` and
   `seriesmith/core/`.

## The numbers aimed at

Estimates from each section's word count; the trimmed text is not drafted.

| | words |
|---|---|
| Today | about 20,100 |
| The core `SKILL.md` | about 7,800 |
| Moved to four new references | about 9,500 |
| Cut as said already elsewhere | about 2,800 |

## 1. Fix what contradicts itself

Before anything moves. Each is from the audit and is read again against the parser or the
target when it is fixed, so the document ends up saying what the code does.

- Line 990 has the writer put "no hard hat" in a design; 895-903 says `check` warns about a
  negative in a design.
- The master's default: 1440p at 143, "1080p is the usual" at 378.
- `post` with no answer from the user: written at 145, left out at 411.
- Keyframes on the Ref2VA family: "don't read them" at 1185 and in the table at 208-210,
  "first, when the shot asks" at 207, 1243-1245 and in the generated table.
- `latent` "off H3 Ref2VA" is an error at 1935; 1220 allows FastH3 Omni and Singularity.
- "A `clone` shot on LTX" warns at 1938; 213 and 1106 say `ltx2` clones, only
  `ltx2_ingredients` doesn't.
- `<Picture 1..3>` at 1049 and a "three-subject rule" at 1793; the limit is eight (1796-1800).
- The target list at 1069 leaves out `h3_singularity` and `h3_hybrid`.
- The check's command is written three ways (the preamble, 125, 1473 and 1922).
- Text under the wrong heading: shot IDs under Vehicles (1769-1788), the plate's scale
  under A group (1885-1892); "The same idea for people" at 912 no longer follows what it
  points back to.

## 2. Say each rule once

Each of these is said in the places listed. It stays in the first place a writer needs it,
whole, and the others shrink to a pointer or go.

- "Leave the target out": 221-224, 311-313, 497-499, the preamble.
- `continuous: first` moving the shot to FL2VA: 207, 211, 227-229, 1219, 1240-1245, 1665-1667.
- What each model takes in pictures: the hand-made table (205-219), the generated table
  (1384-1417), and prose at 1123, 1132, 1164. The generated table stays; the hand-made
  one keeps only what the generated one doesn't carry.
- The duration grids: 207-218, 1104, 1127, 1172, 1442-1444.
- The list of sizes: 1051, 1566-1580, 1587-1590, 1656.
- The plate scaled to the shot's size: 1608-1613, 1885-1889.
- `lora: none` and the full model: 472-484, 1065. The overlap's rounding: 1073, 1262-1265.
- Multishot doesn't mend a jump cut: 1312, 1673-1674.
- The filter on describing bodies: 614-620, 1360-1363, 1369-1372.
- No memory between shots: 192-199, 1555, 1647, 1711-1713.
- A name not in `who:` draws a stranger: 880-891, 1715-1719.
- Extras seen twice become a group: 292-293, 1720-1725, 1804-1805, 1832-1841.
- People stay out of the plate and the look: 641-647, 1874-1876.
- Light and the time of day belong to the location: 622-626, 657-659, 668-669, 689-690, 1896.
- The camera line: 1058, 1487; "holds still without one" at 1108, 1488; the static hold at
  1537, 1769.
- No master recipe: 185-188, 330, the preamble. The proxy too small: 325, 349-351.
- Examples: three of a series config (39-87, 158-178, 245-275), two of a script (91-123,
  1016-1042), the master's JSON twice (169-176, 382-390). One of each stays whole.
- Against the references: shot IDs (1772-1775 and `SCRIPT_CONVERSION.md` 209-213), the cold
  open (1072, 1081, 1314-1334 and `SCRIPT_CONVERSION.md` 200-207), `// structure` and
  `// beat` (the preamble, 1080-1081, `STORY_STRUCTURES.md` 77-90).
- Why a rule is so, where the writer doesn't act on the reason (about 450 words: 653-657,
  663-667, 886-888, 952-958, 1259-1261, 1460-1461, 1533-1535, 1592-1596, 1737-1738). These
  stay in AUTHORING.md for a person reading the docs and are marked to leave the skill
  (section 3's `omit`).

## 3. Markers in AUTHORING.md

The split is written into the document as comments, the way the pictures table's
`BEGIN PICTURES` block already is, and the generator reads them:

```
<!-- skill:ref models -->
…this part goes to references/models.md…
<!-- /skill:ref -->

<!-- skill:omit -->
…this part is for a person reading the docs, not for the skill…
<!-- /skill:omit -->
```

- `tools/make_prompts.py` lifts each `skill:ref` block into its reference, in the
  document's order, and leaves that reference's one-line trigger (section 4) where the
  first block was. `skill:omit` blocks are left out of `SKILL.md`, the references and the
  one-file instructions.
- `seriesmith-script.instructions.md` is the core and every `skill:ref` block in the
  document's order, with no triggers.
- `tools/make_site_docs.py` already drops a line that is only a comment (its line 124);
  a test holds that the site's page comes out the same with the markers in.
- A marker inside the generated pictures block, or an unclosed one, fails the generator.

## 4. The files

Six references: the two there are, and four new. Each is named once in `SKILL.md`, with
the line that says when to read it.

| Reference | What goes in it | Read it when |
|---|---|---|
| `series_config.md` (about 3,300 words) | Starting a series, render size, master, post, publish, the `look` line, profiles, the `refs`, `sound` and `ambience` blocks, relit plates | writing a new `series.json`, or any block of it besides `subjects` and `locations` |
| `models.md` (about 3,000) | The targets table, each target's section, hosted models and the generated pictures table, keyframes, `dur: model`, `target: hold` | the config or a shot names a `target:`, or the user asks which model |
| `continuity.md` (about 1,100) | `continuous: first`, `latent`, `multishot` | before writing any `continuous:` line |
| `people.md` (about 2,100) | Wardrobe variants, cutting round a change, groups, the bokeh plate, vehicles in motion | a costume change, the same background people twice, a moving vehicle |
| `script_conversion.md` | as now | as now |
| `story_structures.md` | as now | as now |

**The core keeps**, about 7,800 words: the first episode; the one thing (no memory between
shots); the series config's required and optional keys and `subjects`; the `design`
sentence; a location is one angle; crops for medium and close shots; two people talking;
say what is there; the script's table; durations, dialogue fit and the camera line;
breaking a scene; faces need room; cutting within a location; every shot starts from an
empty plate; shot IDs; reference slots and extras; sequences; validating.

**These stay in the core though their section moves**, each as one or two lines, because a
writer has to meet them before knowing a reference is wanted:

- Wardrobe is fixed within a shot ("takes off his hat" needs `people.md`).
- People seen twice in the background become a group.
- `continuous:` only when the picture really carries on.
- Dialogue needs a model with sound.
- The cold open's one line.
- The limit of eight subjects.
- The grid's table and the syllable rule (whole, not a line).

## 5. The preamble

- Its second paragraph, a copy of Starting a series (132-153), goes; it points to
  `series_config.md`.
- One order for checking, said once: the MCP tools when the client has them (`check_pair`,
  `check_source`, `preview_shot`), else `seriesmith check`, else the bundled
  `scripts/check.py`. Today the skill names only the command line.
- The one-file instructions get a preamble of their own that names no `references/` file
  and no bundled check, since they have neither.
- The description (the frontmatter) is right and is not changed.
- The skill cites eleven of the repo's docs its reader can't open (FINISHING, FULL_SETUP,
  RECORDED_DIALOGUE and others), and `outside_repo` turns a link to `STORY_STRUCTURES.md`
  into `docs/STORY_STRUCTURES.md` where it should be `references/story_structures.md`.
  Links to the two bundled docs point at the references; a link to any other repo doc
  becomes plain words.

## 6. The references over MCP

`seriesmith/mcp.py` lists one resource, the format. With the split, a client that reads
only that would lose the 9,500 words that moved. So each reference becomes a resource of
its own beside the core (`resources/list` names them with the same "read it when" line),
read from `prompts/` as the core is.

## 7. The check in the bundle

The check stays the real build. What changes is how it is packed.

- `tools/make_prompts.py` writes `scripts/check.py` as one Python file that carries the
  same 184 files inside it, writes them to a temporary folder when run, and calls
  `build.main` there. The skill is then about eight files, and a new model adds none.
- **No zip, in the skill or inside the file.** claude.ai refuses a zip in a skill, so the
  files are carried as text: a table of path to contents written into `check.py` itself
  (each file's bytes as base64, so nothing in a source can end the table early). Nothing
  in the skill is an archive, by name or by format.
- The table is made from the same `BUNDLE_FILES`, `BUNDLE_DIRS` and `BUNDLE_SKIP` as
  today, so what the check runs is unchanged.
- `SKILL.md` says to run the file and never to open it (it is about 2 MB of carried
  files).
- It needs a folder it can write to; when there is none it says so and points at
  `seriesmith check`.
- A test builds the file, runs it on `examples/starter` from outside the repo, and holds
  that it reports what `seriesmith check` reports.

Decided: the check is packed this way. If the one file turns out too large for a skill
when it is uploaded, the bundle goes back to separate files as it is today, and this
section is corrected to say so.

## 7a. The demo checks clean

The skill says to fix a script and run the check again until it is clean; `examples/demo`
checks with nine warnings. They are fixed in the demo itself:

- Seven locations whose medium and close shots play on the whole plate
  (`water_towers_door`, `water_towers_run`, `roof_edge_back`, `dish_roof`,
  `dish_roof_corner`, `cable_span`, `lower_roof`): each gets a crop for those shots, or
  `framing: medium` where its plate is already drawn that close, as the warning offers.
- Two negations: sh060's action ("never looking back") and Voss's `voice` ("never
  raised"), each rewritten to say what is there.
- `docs/site/last-light.mdx` quotes the demo's files whole (`tests/test_docs.py:115`), so
  it is brought up to date in the same commit.
- A test holds that `examples/starter` and `examples/demo` check with no warnings.

The demo has been rendered with the plates it has; the crops change what a new render of
those shots frames, which is what the warning is for. Its `// structure:` and `// beat:`
lines are not added here.

## 8. Holding the size

- `tests/test_docs.py` already holds that `prompts/` is what the generator writes; it gains:
  every marked block lands in exactly one reference; the one-file instructions hold every
  core section and every block; `SKILL.md` names each reference once.
- A word limit on the core in the generator (9,000), so it fails when the core grows back,
  the way `MAX_FILES` does for the bundle.

## 9. Knowing nothing was lost

Before the first edit and after the last, the same three requests go to a model with only
the skill, and what it writes is run through `seriesmith check`:

1. A new series and a first episode from a one-paragraph premise (the core and
   `series_config.md`).
2. An episode where a character changes costume and a crowd recurs (the core and
   `people.md`).
3. A scene of two shots that carry on from one another, on a model named in the config
   (the core, `continuity.md`, `models.md`).

Each passes `check` with no more warnings than before, and each reads the reference its
request needs. The transcripts are kept with this document's checklist, not in the repo.

## Not in this work

- Any change to the format, the parser or `check`'s messages. The unknown-key warnings,
  every error in one pass, sequence-level `extras:` and the rest of the audit's authoring
  list are not here.
- `// structure:` and `// beat:` lines in the examples.
- New MCP tools. Section 6 adds resources only.
- The description's wording.

## Checklist

Each line is a commit on this branch. `python tools/make_prompts.py` and
`python tools/make_site_docs.py` are run and their output committed with the change that
alters it; `.venv\Scripts\python -m pytest tests/test_docs.py -n 0` after each.

- [ ] 1. The three requests of section 9 run on today's skill and kept.
- [ ] 2. The contradictions fixed (section 1), each read against the code.
- [ ] 3. Each rule said once (section 2); the misfiled text moved.
- [ ] 4. The markers and the generator (section 3); the site's page unchanged; the tests
      of section 8.
- [ ] 5. The four references marked out and the core's kept lines written (section 4).
- [ ] 6. The preamble, the one-file instructions' own, the links (section 5).
- [ ] 7. The references as MCP resources (section 6).
- [ ] 8. The check as one file, no zip (section 7).
- [ ] 9. The demo checks clean; the test that both examples do (section 7a).
- [ ] 10. The word limit on the core (section 8).
- [ ] 11. The three requests run again and compared (section 9).
