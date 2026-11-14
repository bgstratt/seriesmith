# seriesmith — releases

One entry per version published to the Comfy Registry, newest last. The publish workflow
sends a version's entry as its notes (the Registry's Updates, `tools/release_notes.py`), so a
release bumps `pyproject.toml` and adds its entry here in the same change, leading with what
a user gets. Releases up to 0.1.23 were listed in PLAN.md's "The ComfyUI Manager listing";
they moved here when PLAN.md was retired (2026-11-11).

- [x] **0.1.3** (2026-10-25, `release-0.1.3`): H3 dialogue keeps its delivery note out of
      the spoken line; close-ups blur the plate away and leave the location's words out;
      `seriesmith check` warns on light sources in a look; AUTHORING on blurred close-up
      plates and an ECU's tightness; the docs site's Tutorials; Simple mode's Who and Where
      from + Create; relights and looks name no places or things. Published by the merge's
      version bump (publish_action.yml); Pending until the Registry's scan passes.
- [x] **0.1.4** (2026-10-26, `release-0.1.4`): `continuous: multishot`, a run of shots as one
      generation (docs/MULTISHOT.md): timed `[Shot N]` sections on H3 (Ref2VA, FastH3 Omni,
      FL2VA), prose on Seedance 2.5/2.0, one brief prompt on Kling v3 Omni, the storyboard on
      Kling Video O1; the editor's timeline and Shots tab show a group; upscale and master
      walk the built order. Hosted models refuse a picture of a shape they won't take
      (0.4 to 2.5) before sending, never cropping it; WebP sizes read; Kling v3 Omni takes 7
      pictures; an input ComfyUI holds isn't uploaded again. Kling 4 isn't on Router yet
      (its catalog, 2026-10-26). Published by the merge's version bump.
- [x] **0.1.5** (2026-10-26, `release-0.1.5`): `target: ltx2_msr`, LTX-2.5 with Licon's MSR
      LoRA: up to four people's pictures and the plate on one shot (a group refused), two
      stages; the Features window's "LTX-2.5 + MSR" with its two node packs; a LoRA of the
      user's on it. AUTHORING says what LTX references hold: one person on `ltx2`'s
      ingredients sheet, a group on MSR, speech by seed. Published by the merge's version bump.
- [x] **0.1.6** (2026-10-27, `release-0.1.6`): the gallery (#55): every picture of an episode's
      refs and every take of its shots, large, in one window; arrow through them; what each
      was made with (a take's own prompt and the pictures it was sent); Regenerate; a selection
      saved as one zip; a shared ref's pictures from the other episodes. New routes
      `GET /seriesmith/take`, `GET /seriesmith/refs/shared-takes`, `POST` / `GET
      /seriesmith/download`. A bonus tutorial (https://youtu.be/KnWEI-0d6PA). Published by
      the merge's version bump.
- [x] **0.1.7** (2026-10-27, `release-0.1.7`): an LLM drives seriesmith and takes come from
      outside (#59). `seriesmith mcp`: the editor's API as an MCP server on stdio for an LLM
      client to start (44 tools: write, check and build episodes, refs, render, the cut,
      overrides and promote, upscale, post, master; `--read-only`), with Settings › This
      computer › Use from an LLM showing this install's command to copy. A video file, or
      another shot's take, as a shot's take: Import video…, a file or a gallery take dropped
      onto a timeline clip, or between two (a new shot in the script there). New routes
      `POST /seriesmith/check`, `GET /seriesmith/mcp`, `POST /seriesmith/take/import`,
      `POST /seriesmith/take/copy`; `GET /seriesmith/refs?fresh=1`. Published by the merge's
      version bump.
- [x] **0.1.8** (2026-10-28, `release-0.1.8`): a shot's sound and dub tracks (#67): each shot
      set to the series' default, generate, clone, or dub (a recording, a dub track, or a
      take's sound), in one Sound card (the shot form, Sound…, Replace audio…); dub tracks (the
      shot rendered tiny on H3 Ref2VA for its voice alone, kept in `dub/<shot>/`) listed in the
      Refs tab with the shot's lines, Voices' Generate missing; FL2VA clone; drafts that survive
      renders and reloads, a check before Export, multi-select queueing, a picture dropped on a
      shot as its first keyframe. Voices across models (#62: LTX dub and clone, Seedance
      audio), whole-picture keyframes (#63), FLUX 3 video on Router (#64), Adding models in the
      docs (#66), the gallery showing a ref's live file with no candidate behind it at its own
      shape (#68). New routes `GET /seriesmith/dubs`, `PUT /seriesmith/sound`. Published by the
      merge's version bump.
- [x] **0.1.9** (2026-10-29, `release-0.1.9`): finishing in the cut (#72): a picture held as
      a shot on seriesmith's own model (`target: hold`, ffmpeg, dub audio under it; dropped on
      the timeline, its edges set its length; Hold this frame after it…); a clip's colour
      (exposure, contrast, black point, saturation, warmth, tint, applied on export, previewed
      live); Match the sequence to this by skin, frame or luma; a badge on a clip out of line
      with its sequence; fades in and out and dissolves, drawn as curves. H3 Singularity as a
      local model, FastH3's and Singularity's own FL2VA, and `series.first_target` naming the
      first-frame model (Ref2VA can open on a frame itself). Fades and dissolves dragged on the
      timeline, the clip menu in groups, the gallery's search box and layout (#73). A dub
      track then the render in one request (#70); voice samples as long as the character's
      lines (#71). New routes `POST /seriesmith/color/match`, `POST /seriesmith/color/measure`.
      Published by the merge's version bump.
- [x] **0.1.10** (2026-10-30, `release-0.1.10`): the cut as an FCP7 XML timeline (#76):
      `assemble --xml`, each clip its take's own file with its handles, sound and the
      recording on their tracks, fades and dissolves as cross dissolves; tried in Resolve and
      FilmCraft. The timeline's buttons as one Export ▾ menu (Export, Titles, the XML, each
      2x; Master). The lost-tour test naming its own queue (#75). The `xml` flag on
      `POST /seriesmith/assemble` and the MCP's assemble. Published by the merge's version bump.
- [x] **0.1.11** (2026-10-31, `release-0.1.11`): how a shot continues shown in the inspector,
      the shot form and its badges (#78); the three continuous modes in one place, and latent
      continuing a take from any model (#79). The skill trimmed to the format (#80): finishing
      to FINISHING.md, setup to FULL_SETUP.md, a required/optional table; story structures
      bundled as `references/story_structures.md`. Defaults: an absent `audio.mode` generates
      (a named `audio.track` still dubs), a new series' proxy is 896×512 (1344×768's shape).
      Published by the merge's version bump.
- [x] **0.1.12** (2026-10-31, `release-0.1.12`): a faster episode open (#82): the refs fetched
      on first use instead of with every open, one targets load per `GET /seriesmith/targets`,
      the takes' prompt ids only while queued and save notes only when failed (Porchlights
      ep01 cold: ~5.3 s -> ~3.5 s). `render --dry-run` writes into the episode folder.
      Published by the merge's version bump.
- [x] **0.1.13** (2026-11-02, `release-0.1.13`): the episode's sound (#86): four tracks
      (Dialogue, Effects, Ambience, Music) in `mix.json` per pass, with faders, fades, volume
      points, ducking under speech and duck regions, loudness to -16 LUFS with a true-peak
      limiter, float stems and the XML's tracks; music cues on Stable Audio 3 / ACE-Step 1.5
      and songs on YuE2 (non-commercial), written to land hits, with the spotting sheet, the
      cue window (Score, Arc, Orchestration & takes), themes and repaint; a place's ambience
      bed; effects from the take (H3, LTX-2.3, HunyuanVideo-Foley) trimmed and faded; voices
      only; beats as trim snaps; tracks of your own; the export's checks; music videos (the
      song as the recording, an optional vocal stem; MUSIC_VIDEO.md, SCORING.md); one voice
      model list; align on the GPU (cuBLAS) and Whisper turbo. An edit as a new show or a
      show's next episode (#87): FCP7 XML from Premiere, Resolve, Final Cut 7 or our own,
      footage as handles, reference or proxies (`import-xml`, Import…, the wizard's From an
      edit; IMPORT_XML.md); the Edits and Turn models (`refs.edit_target`, `refs.turn_target`,
      ↻ Turn with); preview zoom; RTX VSR a window at a time; `continuous: first` chains on
      the CLI; frames read with `-fps_mode passthrough`. Features covers everything (#88,
      #89): a line for every pack, model, package and the API key (`key`, `hub` kinds), no
      download behind a job's back (Whisper, htdemucs, Hybrid Demucs, BigVGAN, SigLIP2/CLAP),
      demucs in ComfyUI's Python, quoted pip commands, align's packages naming their Python.
      Story structures not in the reference outlined the same way (#84); the skill with no
      links into the repo (#85). Published by the merge's version bump.
- [x] **0.1.14** (2026-11-04, `release-0.1.14`): themes across a show and a first-pass score
      (#92): a picked take made a series theme (★ Series theme, `sound.themes`, whose it is),
      any cue rendered from it on Stable Audio 3 (audio-to-audio at 0.86, fitted to the cue's
      tempo and bars) with a melody score where SheetSage2 is installed; the score drafted from
      the script's `// structure:` and `// beat:` lines and each structure's Music table
      (`seriesmith score-draft`, the spotting sheet's Draft…, MCP `score_draft`): beats in a row
      one cue, stings, a sitcom's bumpers, `// theme:` marks, a show's own `sound.format` with
      `gaps`, drafting again around rendered cues, a character's theme as the episode's, a
      structure laid over a script with no beat lines; the cue window's cue picker and fit on
      open, hits dragged on the spotting map, the shot form's beat, theme mark and hit, a cue
      that can't be planned saying why; SOUND_GUIDE.md. Render quality (#91): leaner H3
      prompts (a character with a sheet named by its picture), `check` on eyelines and
      letterboxed plates, the plate as the camera in AUTHORING. Published by the merge's
      version bump.
- [x] **0.1.15** (2026-11-04, `release-0.1.15`): more music models, Pika H3 Flex, a way to
      ComfyUI (#94): MiniMax Music 3 for songs (local, and on Comfy Cloud through a partner node
      on your own ComfyUI: the Comfy API key sent with the job, the take counted as paid);
      Magenta RealTime 2 for score on seriesmith's own node (the PyTorch port carried in the
      node pack, the arc a style a bar, a theme blended into its style); Pika Music on Comfy
      Router (a draft until Router serves it) and hosted music models generally; Pika H3 Flex
      (Ref2VA and FL2VA, six steps); without a ComfyUI, the Features window's guide to ComfyUI's
      own installs and Find my ComfyUI; startup checks naming what a ComfyUI update renamed or
      dropped. Published by the merge's version bump.
- [x] **0.1.16** (2026-11-05, `release-0.1.16`): Export's dialogue (#96): Export, 2x Export and
      Master follow Play all's audio switch, on recording the recording as the dialogue under the
      mix; a take dubbed to the recording with its effects kept no longer exports with no line (the
      model's whole mix in its video, an older take's `_h3.wav`). Published by the merge's version bump.
- [x] **0.1.17** (2026-11-06, `release-0.1.17`): re-render part of a take (#98): a stretch of a take made
      again as a new take on the H3 family or LTX-2, the rest held and its sound kept, from any model's take; H3 Ref2VA, Singularity,
      Pika H3 Flex and FastH3 Omni take eight subjects round the plate on `<Picture 4>` (existing FastH3 takes read as stale).
      Published by the merge's version bump.
- [x] **0.1.18** (2026-11-07, `release-0.1.18`): H3 upscales on ComfyUI's own latent upscaler and context windows
      from 0.44, the packs the fallback; upscales get their keyframes back; new default edit and keyframe models
      (#100). Any model's take re-sampled through an H3 model; Play all plays a replaced sound; on dub the cut and
      export play the dub (#101). Published by the merge's version bump.
- [x] **0.1.19** (2026-11-09, `release-0.1.19`): models and voices on providers of your own (#103); the
      storyboard (#104, #106); one guided wizard, the guide and sketches, drops on the board and the add
      buttons, Rename on an unused entry (#107); instructions for your own agent in the guide (#108).
      Published by the merge's version bump.
- [x] **0.1.20** (2026-11-09, `release-0.1.20`): the guide's Make the pictures makes the pictures no
      shot uses yet, as a new episode has no shots (#110); the shot form's model picker at the top, in
      What renders (#111). Published by the merge's version bump.
- [x] **0.1.21** (2026-11-09, `release-0.1.21`): the script-writing skill's zip under claude.ai's 200
      files, with no zip inside it (#113). Published by the merge's version bump.
- [x] **0.1.22** (2026-11-10, `release-0.1.22`): the Registry's flags answered (#115: the package
      trimmed, other web pages refused, keys only to their hosts, paths from other devices kept to
      the project folders, no `python -c`; MRT2's seed and torch 2.15 under dynamic VRAM fixed);
      continuity carries on from the cut's out point (#116). Published by the merge's version bump.
- [x] **0.1.23** (2026-11-10, `release-0.1.23`): a laptop or phone on your network now pairs
      once with a six-digit code from Settings on the PC before it can use seriesmith, and
      Settings lists the paired devices and removes them. A show's files must be inside the
      show or a project folder, so a show someone hands you can't read files from elsewhere on
      your PC. In Project folders, New episode, New series and Import now work in any folder
      on the PC (it becomes a project folder) and say where they'll make things. SECURITY.md
      says what seriesmith reaches and what bounds it, and releases publish from a pinned job
      with these notes (#118). Published by the merge's version bump.
- [x] **0.1.24** (2026-11-13, `release-0.1.24`): medium and close shots now get a crop of
      their place's plate, so they stop coming out as wide as the plate: Crop and Zoom on a
      location card, Upscale on the crop's row for detail, and `seriesmith check` warns where
      one still plays on a wide plate. Takes are checked as they land (a cut you didn't ask
      for, the words against the script's lines, more people than the shot has) and one that
      fails is rendered again. Finishing can refine faces on every shot or only the clips
      marked R, and upscaling has a fourth method, the LTX-2.5 detail pass. Play all plays
      the lines levelled as the export levels them, and the export writes the lines as SRT
      and VTT subtitles. New models: H3 Hybrid for video and MiniMax-H3-Image for pictures.
      Jobs: Cancel all, and a finished job opens what it made. A camera tour now saves when
      the project is on a different drive from the system's temp folder (#120 to #123).
      Published by the merge's version bump.
