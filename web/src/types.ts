// Shapes from docs/API.md. Seeds are ALWAYS strings: built seeds are 63-bit and a
// JS number loses precision above 2^53. Never pass a Seed through Number().

import type { ShotColor } from "./lib/color";

export type Pass = "final" | "proxy";
export const PASSES: Pass[] = ["final", "proxy"];

/** A seed as decimal digits. */
export type Seed = string;

export interface Config {
  roots: string[];
  comfy: string;
  version: number;
}

export interface EpisodeSummary {
  ep: string;
  name: string;
  series: string;
  title: string;
  built: Record<Pass, boolean>;
  shots: number;
  script: string;
  /** one of Simple mode's projects (its series config says `"simple": true`, or it is Clips) */
  simple?: boolean;
}

/** A target's frame grid and size rules (GET /seriesmith/targets, `template`). */
export interface TargetTemplate {
  /** a number, or "series": the series config's fps */
  fps?: number | "series";
  frames?: { step?: number; base?: number; max?: number };
  size_multiple?: number;
  /** "snap": an off-grid size is rounded down; otherwise it is refused */
  size_fit?: string;
  max_size?: { long_side?: number; pixels?: number };
  /** the only sizes the model takes */
  sizes?: [number, number][];
}

export type TakeStatus = "queued" | "ok" | "failed";
/** script | ref | preset, or unknown for a take from before sidecars */
export type StaleReason = string;

export interface TakeSummary {
  take: number;
  status: TakeStatus;
  has_video: boolean;
  seed: Seed | null;
  seed_source: string | null;
  note: string;
  overrides: string[];
  /** a Seedance draft: its final can be made from it, until `expires` (7 days) */
  draft?: { task: string; made: string; expires: string; expired: boolean } | null;
  /** a final made from a draft (that proxy take) */
  from_draft?: { task: string; take: number; pass: string } | null;
  /** the sound overrides.json set when it rendered (a dub's source) */
  sound?: ShotSound;
  stale: StaleReason[];
  thumb: string | null;
  strip: string | null;
  mp4: string | null;
  queued: string | null;
  finished: string | null;
  save_notes: string;
  /** the ComfyUI prompt id of a queued take (its progress events) */
  comfy_prompt_id?: string;
  /** Phase 7: the video target the take rendered with, from its sidecar
   * (null for a take from before sidecars; absent from older servers). */
  target?: string | null;
  /** The take's real frame count, as the saver wrote it (null: not rendered;
   * absent from older servers). A `dur: model` take's is the model's choice. */
  frames?: number | null;
  /** The frame rate the take was rendered at, from its sidecar (a Wan 14B
   * take is 16 fps in a 24 fps episode); null/absent: the episode's. */
  fps?: number | null;
  /** Phase 9b: the file whose sound the cut plays for this take (the mp4 when
   * it has an audio stream, else its `_h3.wav`, else null), relative to the episode. */
  audio?: string | null;
  /** Phase 13: the take's upscale (null: never upscaled; absent from older servers). */
  upscale?: TakeUpscale | null;
  /** its post (post: the upscale finished; null: never post-processed; absent from older servers) */
  post?: TakePost | null;
  /** Phase 13: the take's size, from its sidecar (the Upscale dialog's arithmetic) */
  width?: number | null;
  height?: number | null;
  /** a take seriesmith didn't render (takeimport): "imported", with the file's name or
   * the take it was copied from; absent on a rendered take */
  source?: "imported";
  original_name?: string | null;
  copied_from?: { shot: string; take: number; pass: Pass; target?: string | null } | null;
}

export interface CutInfo {
  take: number | null;
  picked: boolean;
  pass: Pass;
  placeholder: boolean;
  usable: boolean;
  trim_in: number;
  trim_out: number;
  locked: boolean;
  note: string;
  in_cut_file: boolean;
  /** left out of the cut: still in the script, with its takes and place; assemble,
   * Play all and Master skip it. Absent from older servers. */
  out?: boolean;
  /** flagged to come back to (re-render it, change its prompt); changes nothing
   * played. Absent from older servers. */
  flag?: boolean;
  /** its colour in the cut (exposure, contrast, black, saturation, warmth, tint; null: as shot),
   * applied by assemble. Absent from older servers. */
  color?: ShotColor | null;
  /** frames from / to black at its head / tail, and of a dissolve from the clip before
   * (0: none; absent from older servers) */
  fade_in?: number;
  fade_out?: number;
  dissolve?: number;
  /** what's out of line with the rest of its sequence ("0.8 stop darker", "cooler"),
   * its colour counted; null: in line, or not measured. Absent from older servers. */
  look_off?: string[] | null;
  /** The cut take's real frame count (its sidecar's), or null. The shot's
   * `seconds` is the build's (for `dur: model`, an estimate); the timeline and
   * Play all use this when present. Absent from older servers. */
  frames?: number | null;
  /** The frame rate of `frames` (and of the build's `length` when there is no
   * take): the cut take's, else the shot's target's. Absent: the episode's. */
  fps?: number | null;
  /** Phase 9b: the shot's index in the pass's cut (absent from older servers). */
  order?: number | null;
  /** Phase 9b: the shot's index in script order (null for an orphan). */
  script_index?: number | null;
  /** Phase 9b: not where script order would put it (the timeline badges it). */
  out_of_order?: boolean;
  /** Phase 9d: the clip's audio source, as cut.json stores it (null / absent:
   * the clip's own take's sound). */
  audio?: CutAudioSource | null;
  /** Phase 9d: what will actually play, relative to the episode (null for
   * `none`, and for a source the server couldn't resolve). */
  audio_file?: string | null;
  /** Phase 9d: short text for the speaker badge ("sh020 t01", "line.wav"). */
  audio_why?: string | null;
  /** `audio` is the shot's dub, which its take wasn't rendered to: not set by hand */
  audio_dub?: boolean;
}

/** One script shot of a multishot group (ShotStatus.multishot). */
export interface MultishotPart {
  id: string;
  start: number;
  frames: number;
  size: string;
}

/** Where a dub's track comes from (overrides.json `sound.dub`). */
export type DubSource =
  | { from: "track" }
  | { from: "take"; pass: Pass; take: number; shot?: string }
  | { from: "dub"; take: number }
  | { from: "line" };

/** A shot's sound as the editor sets it (overrides.json `sound`); none: the script's. */
export interface ShotSound {
  mode: "generate" | "clone" | "dub";
  dub?: DubSource;
  /** a dub: false for the voice alone (no sound of the model's under it); absent: kept */
  keep_foley?: boolean;
  /** a dub: its source as the editor says it ("dub track 2", "t02 (proxy)") */
  label?: string;
  /** a dub: the file its source plays (episode-relative), null for the track or one missing */
  file?: string | null;
}

/** One sound a shot can be dubbed to (GET /seriesmith/dubs). */
export interface DubOption {
  take: number;
  status: string;
  file: string | null;
  target: string | null;
  seed: string | null;
  note: string;
  finished: string | null;
  save_notes: string;
  seconds: number | null;
  /** a take's pass (a dub track has none) */
  pass?: Pass;
}

export interface DubSources {
  shot: string;
  sound: ShotSound | null;
  /** the shot's window of the recorded track, when it has one */
  track: { file: string; in: number; out: number } | null;
  dubs: DubOption[];
  takes: DubOption[];
  /** the shot's lines (lines.py), each with its finished takes */
  lines?: { id: string; who: string; name: string; text: string; picked?: number | null;
    takes: { take: number; file: string; seconds?: number; voice_name?: string; source?: string }[] }[];
  /** how far its dub is slid in the cut, in seconds */
  offset?: number;
  /** the takes whose mouths follow its dub */
  lips?: number[];
  /** a take rendered to its dub plays what the model gave back, not the dub */
  model_sound?: boolean;
}

export interface ShotStatus {
  shot: string;
  /** the sound overrides.json sets; absent: the script's (audio_policy) */
  sound?: ShotSound;
  /** how many dub tracks it has (absent: none) */
  dub_tracks?: number;
  /** its lines (who: the speaker's name), sent for the shots with a dub track or a dub set */
  lines?: { who: string; line: string }[];
  orphan: boolean;
  sequence: string | null;
  length: number | null;
  seconds: number | null;
  size: string | null;
  subjects: string[];
  /** the first sentence of what happens in it, as the script says it (the board) */
  action?: string;
  audio_policy: string | null;
  cut: CutInfo;
  override: { fields: string[]; stale: boolean };
  takes: TakeSummary[];
  /** References its render needs that aren't on disk (API.md "Missing references").
   * Optional: a server from before round 2 doesn't send it. Empty = ready. */
  missing_refs?: MissingRef[];
  /** Phase 7/8: the video target the shot's next render uses (request, then
   * override, then script, then series config). Absent from older servers. */
  target?: string | null;
  /** Phase 8: the target the build compiled the shot for. */
  built_target?: string | null;
  /** Phase 7: the render profile the shot was built with, or null. */
  profile?: string | null;
  /** Where `target` comes from: the render request, a shot override, the script
   * (a shot/sequence line or a profile), or the episode default. Absent from
   * older servers. */
  target_source?: ShotTargetSource | null;
  /** Phase 8.5: the length is an estimate (`dur: model` before a take exists):
   * the model decides it at render time. The UI marks it "≈". */
  length_estimated?: boolean;
  /** A `continuous: multishot` group (docs/MULTISHOT.md): the script shots this one
   * generation renders, each with the frame it starts on in the take (as the script
   * times it: the model lands its cuts near there), its frames and size. */
  multishot?: MultishotPart[];
  /** How it carries on from the shot before it in the cut (docs/CONTINUOUS.md), from
   * the script (its own `continuous:`, else its sequence's); absent: it doesn't. */
  continuous?: ShotContinuous;
  /** Phase 9b: the shot's dialogue window on the episode's `track`, seconds
   * (a shot timed against recorded dialogue); absent otherwise. */
  audio_in?: number | null;
  audio_out?: number | null;
}

/** A continuous shot's chain (ShotStatus.continuous). */
export interface ShotContinuous {
  /** first: opens on that shot's last frame; latent: holds its last frames and goes
   * on from them; multishot: one generation with it */
  mode: "first" | "latent" | "multishot" | (string & {});
  /** the shot before it in this pass's cut (null: it's the first) */
  from: string | null;
  /** latent: the frames of that take held at the head of the render */
  hold?: number;
}

/** "series" / "default": the shot has no target of its own and follows the episode's
 * default (series.json's, or MiniMax H3), as "episode" does for an editor-set one. */
export type ShotTargetSource = "request" | "override" | "script" | "episode" | "series" | "default";
/** Where the episode's default target comes from: set in the editor
 * (overrides.json `episode.target`), the series config's `series.target`, or
 * the built-in default. */
export type EpisodeTargetSource = "editor" | "series" | "default";

export interface MissingRef {
  /** the loader slot, e.g. "Picture 4" or "Audio 1" */
  slot: string;
  kind: "image" | "audio";
  /** relative to the episode (or its series config) */
  path: string;
  subject?: string;
  /** false: the shot can't be rendered without it, even with render anyway
   * (Wan 14B I2V's first frame); `why` says what to do instead */
  anyway?: boolean;
  why?: string;
}

export interface EpisodeStatus {
  episode: string;
  title: string;
  pass: Pass;
  fps: number;
  width: number | null;
  height: number | null;
  folder: string;
  shots: ShotStatus[];
  /** The episode's default video target now in force (the editor's episode
   * target, else the series config's `series.target`, else the built-in default). */
  target?: string | null;
  /** Where `target` comes from (absent from older servers). */
  target_source?: EpisodeTargetSource | null;
  /** The series config's `series.target` (null when it names none). */
  series_target?: string | null;
  /** Phase 9b: the series config's recorded dialogue (`audio.track`), or null. */
  track?: Track | null;
}

/** Phase 9b: the episode's recorded dialogue track. */
export interface Track {
  /** relative to the episode (`../` for a parent-folder series config) */
  path: string;
  /** seconds (null when unknown) */
  duration?: number | null;
  /** sample rate (null when unknown) */
  rate?: number | null;
  /** the file is there (as built: false for a missing file; `duration` / `rate` are then null) */
  exists?: boolean;
  /** Phase 9c: a usable transcript sits beside the recording (`<rec>.words.json`,
   * newer than it): re-aligning then needs no Whisper, only ffmpeg. */
  words?: boolean;
  /** Phase 9c: how many of the pass's shots carry a dialogue window (0 until
   * the script has `audio:` lines and the episode is rebuilt). */
  aligned?: number;
  /** the recording's vocal stem sits beside it (`<rec>.vocals.wav`, newer than it) */
  vocals?: boolean;
  /** the stem has a transcript of its own (`<rec>.vocals.wav.words.json`) */
  vocals_words?: boolean;
  /** the series config's `audio.dub_from`: where each dub shot's window is cut from */
  dub_from?: "recording" | "vocals";
}

/** Phase 9b: GET /seriesmith/peaks. */
export interface PeaksResult {
  /** seconds of the whole file */
  duration: number;
  bins: number;
  /** max absolute amplitude per bin, 0..255 */
  peaks: number[];
  /** the file has no audio stream (then `bins` 0 and `peaks` []) */
  silent?: boolean;
  /** as built: the range actually used, clamped to the file */
  start?: number | null;
  end?: number | null;
}

/** Phase 9b: what POST /seriesmith/cut/reset and /cut/copy touch. Phase 9d adds
 * "audio" (and "all" clears it too). */
export type CutWhat = "order" | "trims" | "audio" | "all";

// ---------------------------------------------------------------------------
// Phase 9d: a shot's audio from elsewhere
// ---------------------------------------------------------------------------

/** Where a clip's sound comes from: another take, a file, or silence. */
export type CutAudioKind = "take" | "file" | "none";

/**
 * A cut entry's `audio` (absent or null: the clip's own take's sound). The
 * audio is cut or padded with silence to the clip's length on the cut's
 * clock, so a clip's length never changes.
 */
export interface CutAudioSource {
  source: CutAudioKind;
  /** take: the shot it comes from (absent: this entry's own shot) */
  shot?: string;
  /** take: which take (its mp4's sound, else its `_h3.wav`) */
  take?: number;
  /** take: which pass the take is in */
  pass?: Pass;
  /** file: a media file inside the episode (`../` beside a parent-folder series config) */
  path?: string;
  /** seconds into the source where the audio begins (0 or more) */
  start?: number;
  /** seconds it is shifted against the picture (positive = later; the gap is silence) */
  offset?: number;
  /** a linear multiplier, 1.0 unchanged (0–4) */
  gain?: number;
}

// ---------------------------------------------------------------------------
// Phase 9c-A: attaching and aligning a recording
// ---------------------------------------------------------------------------

/** GET /seriesmith/align/ready: what align needs, in the Python that would run it. */
export interface AlignReady {
  ready: boolean;
  /** the ffmpeg on PATH, or null */
  ffmpeg: string | null;
  /** pip names, in order: ffmpeg, numpy, faster-whisper */
  missing: string[];
  /** the interpreter the answer is about (ComfyUI's own) */
  python: string;
  /** the pip line for the missing packages ("" when only ffmpeg is missing) */
  install: string;
  /** as built: what to do when ffmpeg is missing */
  ffmpeg_hint?: string;
  /** as built: the installed version ("" without metadata), null when it isn't installed */
  packages?: Record<string, string | null>;
  models?: { default?: string; choices?: string[] };
}

/** POST /seriesmith/track: attach (or clear) the episode's dialogue recording. */
export interface TrackResult {
  track: Track | null;
  /** the series config's hash after the write */
  hash: string;
  /** the rebuild; it FAILS when the script has no `audio:` windows yet — that
   * is "align to finish", not an error (API.md "Phase 9c-A as built") */
  build: BuildResult | null;
  /** the recording's path relative to the episode */
  path?: string | null;
  /** it was copied into `<ep>/audio/` (false: used where it already was) */
  copied?: boolean;
  /** the whole series config was rewritten in the promote's format */
  reformatted?: boolean;
}

export interface AlignRequest {
  ep: string;
  /** a path relative to the episode; without it, the series config's `audio.track` */
  track?: string | null;
  model?: string | null;
  /** snap the windows to the frame grid (default true) */
  snap?: boolean;
  dry_run?: boolean;
  /** hear the recording's vocal stem (align --vocals; made first when it isn't there) */
  vocals?: boolean;
  pass?: Pass;
}

/** POST /seriesmith/vocals: the stem queued (`job`), or already there (`stem`). */
export interface VocalsResult {
  job: string | null;
  stem: string | null;
}

/** The `seriesmith.vocals` event: a vocal stem made, or not. */
export interface VocalsEvent {
  ep: string | null;
  recording: string;
  status: "ok" | "failed";
  error?: string;
}

/** One shot in an align report: null times mean it keeps its `dur:`. */
export interface AlignChange {
  shot: string;
  audio_in: number | null;
  audio_out: number | null;
  note?: string;
}

/** POST /seriesmith/align. */
export interface AlignResult {
  ok: boolean;
  dry_run: boolean;
  /** align_report.md's text (a dry run has it too) */
  report: string;
  /** "align_report.md", or null on a dry run */
  report_path: string | null;
  changes: AlignChange[];
  notes: string[];
  recording: string | null;
  duration: number | null;
  /** a cached transcript was used (no Whisper ran) */
  words: boolean;
  script_hash: string | null;
  series_hash: string | null;
  track: Track | null;
  build: BuildResult | null;
  /** everything align printed (progress lines removed) */
  log: string;
}

/** The body of POST /seriesmith/align's 409: a dependency isn't installed. */
export interface AlignMissing {
  error: string;
  missing: string[];
  install: string;
  python: string;
  ffmpeg: string | null;
  /** a transcript was found: no Whisper is needed, only what's still listed */
  words?: boolean;
}

/** The `seriesmith.align` event, while a run is going. */
export interface AlignEvent {
  ep: string;
  stage: "start" | "transcribe" | "match" | "write" | "done" | (string & {});
  pct: number;
  text: string;
  /** the queue's job (refactor 3.3: align is a job on the cpu lane) */
  job?: string;
  /** its last event: how it ended, with the answer or why not */
  state?: "done" | "failed";
  result?: AlignResult;
  error?: string;
}

/** An align on the queue (POST /seriesmith/align's answer, GET /seriesmith/align/job). */
export interface AlignJob {
  id: string;
  ep: string;
  state: "running" | "done" | "failed";
  dry_run: boolean;
  /** "waiting" while another job has the cpu lane, then align's stages */
  stage: string;
  pct: number;
  text: string;
  result: AlignResult | null;
  error: string;
  started: string | null;
  finished: string | null;
}

/** PUT /seriesmith/episode-target: the episode's target fields, as GET /seriesmith/episode has them. */
export interface EpisodeTargetResult {
  target?: string | null;
  target_source?: EpisodeTargetSource | null;
  series_target?: string | null;
}

export interface Lora {
  name: string;
  strength: number;
}

export interface Sidecar {
  shot?: string;
  take?: number;
  pass?: Pass;
  status?: TakeStatus;
  seed?: Seed | null;
  seed_source?: string;
  model?: string;
  loras?: Lora[] | null;
  steps?: number;
  parent_take?: number | null;
  comfy_prompt_id?: string;
  note?: string;
  /** How each model param resolved to an installed file when the take was queued. */
  resolved?: Record<string, Resolution> | null;
  /** Phase 8.5: the negative prompt the take rendered with, and where it came from */
  negative?: string | null;
  negative_source?: NegativeSource | null;
  [key: string]: unknown;
}

export type TakeFileKind = "mp4" | "thumb" | "strip" | "shotlist" | "h3_wav";

export interface TakeDetail {
  take: number;
  status: TakeStatus;
  has_video: boolean;
  stale: StaleReason[];
  sidecar: Sidecar | null;
  files: Partial<Record<TakeFileKind, string>>;
  /** Phase 8.5: the reference sheet (or VACE reference) the take rendered
   * with, relative to the episode, when it was kept. */
  reference_image?: string | null;
}

/** GET /seriesmith/take: what one take was made with (the gallery opens one at a time). */
export interface TakeInfo {
  shot: string;
  pass: Pass;
  take: number;
  status: TakeStatus;
  has_video: boolean;
  sidecar: Sidecar;
  /** the prompt as it rendered (the take's frozen shotlist); null with none kept */
  prompt: string | null;
  /** the pictures it was sent; `id` the ref each is (null: none matches), `sha1` the file's then */
  refs: { id: string | null; kind: string; role: string | null; slot: string | null; path: string | null; sha1: string | null; exists: boolean }[];
  reference_image: string | null;
  files: Partial<Record<TakeFileKind, string>>;
}

/** A pass's effective override, as shot_detail returns it (no base_hash). */
export interface Override {
  prompt?: string | string[] | null;
  seed?: Seed | null;
  model?: string | null;
  loras?: Lora[] | null;
  steps?: number | null;
  note?: string | null;
  /** Phase 8: the shot's video target, shared by both passes. (On a ref's
   * override: the image target it generates with.) */
  target?: string | null;
  /** Phase 8.5: the negative prompt, per pass (targets with a `negative` param). */
  negative?: string | null;
  /** Phase 8.5: a two-stage target's (Wan) low-noise model, per pass. */
  model_low?: string | null;
  /** "WxH": the pass renders at this size, not the shotlist's (per pass). */
  size?: string | null;
  /** P4, a ref's override: cfg and the sampler knobs the image target has */
  cfg?: number | null;
  params?: RefParams | null;
}

/** P4: the sampler knobs a ref override may set (refs.TUNABLE_PARAMS), each
 * only where the image target has that widget. */
export type RefParams = Partial<Record<"sampler" | "scheduler" | "denoise" | "shift" | "guidance", string | number>>;
export const TUNABLE_PARAMS = ["sampler", "scheduler", "denoise", "shift", "guidance"] as const;

/**
 * Where a negative prompt comes from (API.md "Phase 8.5 as built"): the request,
 * the shot's override, the episode's negative.txt, the series config, the
 * target's preset, or none (a target without a negative param: H3, Klein edit).
 */
export type NegativeSource = "request" | "override" | "negative.txt" | "series" | "preset" | "none" | (string & {});

export interface Effective {
  prompt: string;
  seed: Seed;
  seed_source: string;
  model: string;
  loras: Lora[] | null;
  steps: number;
  /** Phase 8: the target a render would use, and its size and length. */
  target?: string | null;
  width?: number | null;
  height?: number | null;
  length?: number | null;
  /** Phase 8.5: the negative a render would use now (null for `none`), and where it comes from. */
  negative?: string | null;
  negative_source?: NegativeSource | null;
  /** a two-stage target's low-noise model a render would use now */
  model_low?: string | null;
  /** Phase 8: what to know before rendering (an ignored prompt override, an
   * audio fallback), and why the shot can't render on its target. */
  notes?: string[];
  error?: string;
}

/** What a ref is to a shot (API.md "Inspector: the refs a shot uses"). */
export type RefRole = "subject" | "plate" | "first" | "last" | "reference_sheet" | "voice" | "recording";

/** One ref a shot's current target reads (`GET /seriesmith/shot` `refs_used`). */
export interface RefUsed {
  /** null for a recording, or a plate the series config doesn't name */
  id: string | null;
  kind: string;
  role: RefRole | (string & {});
  /** the live file, relative to the episode (`../` beside a parent-folder series config) */
  path: string | null;
  exists: boolean;
  need?: KeyframeNeed | null;
  /** the picture to show, relative like `path`; null when the file isn't on disk */
  thumb?: string | null;
  /** the loader slot ("Picture 1", "sheet panel 2") */
  slot?: string;
}

export interface ShotDetail {
  shot: string;
  pass: Pass;
  index: number;
  built: Record<string, unknown>;
  built_prompt: string;
  override: Override;
  override_stale: boolean;
  effective: Effective;
  /**
   * P9: the same shape as `effective` with every override dropped — what the
   * build compiled, on `built_target`. Absent when the shot has no override
   * (it would only repeat `effective`). It comes from the same planner as
   * `effective`, so a field can be compared to it directly.
   */
  built_values?: Effective;
  takes: TakeDetail[];
  /** Phase 7/8 (see ShotStatus) */
  target?: string | null;
  built_target?: string | null;
  profile?: string | null;
  target_source?: ShotTargetSource | null;
  /** Phase 8.5: the refs the shot's current target reads. Absent from older servers. */
  refs_used?: RefUsed[];
}

export interface BuildPassResult {
  ok: boolean;
  report: string;
  error: string;
}

export interface BuildResult {
  ok: boolean;
  passes: Partial<Record<Pass, BuildPassResult>>;
  /** As built: set (with no passes at all) when the build couldn't start —
   * no series.json, or the folder has more than one candidate script
   * ("can't tell which .md in the folder is the script"). */
  error?: string;
}

/** P5: POST /seriesmith/episode/new. `parent` is the show's folder, inside a root;
 *  `name` becomes the folder and the script's stem. `series_id` and `title`
 *  name the series only when this is its first episode. */
export interface NewEpisodeRequest {
  parent: string;
  name: string;
  title?: string | null;
  series_id?: string | null;
  /** the wizard: a new show folder to make inside `parent` */
  show?: string | null;
  /** the wizard: the series config's text to write (else the template's) */
  series?: string | null;
  /** the wizard: the script's text to write (else the template's) */
  script?: string | null;
}

/** POST /seriesmith/clip/queue: the pictures asked for first (and the step
 * that renders once they're made), or the renders asked for at once. */
export interface ClipQueueResult {
  refs: { ref: string; view: string | null; take: number; prompt_id: string }[];
  waiting_on: string[];
  step: string | null;
  renders: { queued?: { shot: string; take: number; prompt_id: string }[]; errors?: { error: string }[] }[];
}

/** GET /seriesmith/episode/new: what a new episode in `parent` starts from. */
export interface EpisodeTemplate {
  /** the folder the episode goes in (with the show folder, when one was named) */
  parent: string;
  /** the newest episode there, whose series config it copies; null: a new series */
  from: string | null;
  /** that episode's series config, as text */
  series: string | null;
  /** the name to offer (ep03 after ep02) */
  name: string;
  /** the episodes already there */
  episodes: string[];
}

/** seriesmith: a series config and a stack of scripts, made into episode folders */
export interface ImportSeriesRequest {
  /** a folder of shows (inside a root) */
  parent: string;
  /** the show's folder to make or fill; null: the episodes go straight into parent */
  show: string | null;
  /** the series config's text, for every script without its own (null: each has its own) */
  series: string | null;
  /** each script, with its own series config when it brings one */
  scripts: { name: string; text: string; series?: string }[];
}

export interface ImportSeriesResult {
  show: string;
  episodes: { ep: string; name: string; own_config: boolean; check: SourceCheck }[];
  skipped: { name: string; why: string }[];
  errors: { file: string; error: string }[];
}

/** How an imported edit's footage becomes its shots' takes (POST /seriesmith/import/xml):
 *  each clip's span plus handles, H.264; each source whole, linked or copied as it is; or
 *  that, with a playable proxy of each source the editor can't play. */
export type XmlImportMedia = "handles" | "reference" | "proxies";

/** POST /seriesmith/import/xml (JSON: an XML on the server's machine). */
export interface XmlImportRequest {
  /** the folder of shows the new show goes in (default: the first project root); with
   *  `in_show`, the show's folder the edit becomes the next episode of */
  parent?: string | null;
  path: string;
  /** the show's name; with `in_show`, the episode's title */
  name?: string | null;
  media?: XmlImportMedia;
  handles?: number;
  in_show?: boolean;
  dry_run?: boolean;
}

/** POST /seriesmith/import/xml as multipart: the XML picked in the browser. */
export interface XmlImportUpload extends Omit<XmlImportRequest, "path"> {
  file: Blob;
  filename?: string;
}

/** One clip of the edit as the import makes it. */
export interface XmlImportClip {
  shot: string;
  name: string;
  source: string | null;
  dur: number;
  trim_in: number;
  trim_out: number;
  /** why it has no take (its file isn't there, a nested sequence) */
  missing: string | null;
  codec?: string;
  /** a proxy is made for it (media "proxies") */
  proxy?: boolean;
  /** false: its take won't play in the editor (media "reference", not H.264 in an mp4) */
  plays?: boolean;
  note?: string;
}

/** What POST /seriesmith/import/xml answers (a dry run: what it would make). */
export interface XmlImportSummary {
  sequence: string;
  title: string;
  show: string | null;
  /** the episode's folder name (ep01 for a new show; the next one in a show) */
  episode: string;
  in_show: boolean;
  /** the episode whose series config it copies (in a show), or null */
  from: string | null;
  ep: string;
  fps: number;
  size: [number, number];
  media: XmlImportMedia;
  handles: number | null;
  shots: number;
  black: number;
  takes: number;
  missing: string[];
  sequences: string[];
  audio_items: number;
  hits: number;
  tracks: string[];
  proxies: string[];
  unplayable: string[];
  clips: XmlImportClip[];
  warnings: string[];
  /** not a dry run: */
  build?: BuildResult;
  groups?: { index: number; kind: "source" | "black"; source: string | null; clips: number }[];
  /** the queue's jobs making the media, one per source (and the gaps' black) */
  jobs?: string[];
}

export interface NewEpisodeResult {
  ep: string;
  /** "episode" = the newest episode beside it was the template, "starter" = the
   *  shipped pair, "form" = the wizard's own series config and script */
  template: "episode" | "starter" | "form";
  /** the folder the template came from (null: the wizard's new series) */
  from: string | null;
  files: string[];
  /** where this config's reference pictures go, null when it names none */
  refs: string | null;
  check: SourceCheck;
  episode: EpisodeSummary;
}

export type SeedMode = "auto" | "new" | "same";

export interface RenderRequest {
  ep: string;
  pass: Pass;
  shots: string[];
  redo: boolean;
  seed_mode: SeedMode;
  seed: Seed | null;
  model: string | null;
  loras: Lora[] | null;
  steps: number | null;
  prompt: string | null;
  parent_take: number | null;
  note: string;
  /** Queue shots with missing refs anyway (flat grey pictures, no audio ref). */
  allow_missing_refs?: boolean;
  /** Also write the take's frames as a PNG sequence (`<take>/frames/`), for
   * retouching a shot that is right but for a frame or two. Absent leaves the
   * workflow's own setting (off). Costs ~2.5 s a shot and 16-50 GB an episode. */
  save_frames?: boolean;
  /** Phase 8: the video target for this run only, beating the override. Only
   * sent when set. */
  target?: string | null;
  /** Queue shots whose model file is another family than the target needs. Only sent when set. */
  allow_model_mismatch?: boolean;
  /** "WxH": render this run at that size, beating the override. Only sent when set. */
  size?: string | null;
  /** finals made from Seedance drafts: {shot: its proxy draft take} (pass final). Only sent when set. */
  from_draft?: Record<string, number>;
  /** Phase 13: keep the take's latent beside it for an upscale later. Absent: the
   * server's default (the series config's upscale.save_latents; final pass only). */
  save_latent?: boolean;
  /** a dub track: the shot for its sound only (H3 Ref2VA at 64x64 unless target / size say
   * otherwise), kept apart from its takes. Only sent when set. */
  dub_track?: boolean;
  /** with dub_track: once each track is made, the shot dubbed with it and rendered on its own
   * model (a queue step per shot, in `steps`). Only sent when set. */
  then_render?: boolean;
  /** seriesmith: render on this backend (absent: each shot's own). Only sent when set. */
  backend?: string | null;
  /** frames of a take made again, the rest and its sound held; `prompt` when they
   * should ask something else than the take did. Only sent when set. */
  redo_range?: { take: number; first: number; last: number; prompt?: string };
}

export interface RenderSkip {
  shot: string;
  reason: string;
  take?: number;
  missing_refs?: MissingRef[];
  /** the files that stopped a shot whose target isn't ready (no take reserved) */
  missing_files?: MissingFile[];
  /** the shot's target (a missing-files skip) */
  target?: string;
  /** the model checks that stopped the shot (jobs.check_models) */
  model_mismatch?: { param: string; file: string; family: string; label: string; message: string }[];
}

/** POST /seriesmith/render. What a render will change (an audio fallback, an ignored
 * prompt override) isn't here: it is in shot detail's `effective.notes`
 * beforehand and the take's sidecar `notes` after. */
export interface RenderResult {
  queued: { shot: string; take: number; prompt_id: string; seed: Seed; seed_source: string; target?: string }[];
  skipped: RenderSkip[];
  errors: { shot: string; error: string; take?: number }[];
}

export interface TakeRef {
  ep: string;
  pass: Pass;
  shot: string;
  take: number;
}

/** POST /seriesmith/cancel: the take's new status (failed, "cancelled"). */
export interface CancelResult {
  shot: string;
  pass: Pass;
  take: number;
  status: TakeStatus;
  save_notes: string;
  finished: string | null;
}

/** POST /seriesmith/discard (Phase 8.6): the take's files moved to `_trash/`. */
export interface DiscardResult {
  shot: string;
  take: number;
  pass?: Pass;
  /** the files' new paths (under `_trash/`), relative to the episode */
  moved: string[];
  /** the pass's cut picked that take: the pick is gone (back to the latest usable) */
  cut_changed: boolean;
}

export interface PickRequest {
  ep: string;
  pass: Pass;
  shot: string;
  take: number | null;
  from_pass: Pass | null;
  force?: boolean;
}

export interface CutEntry {
  shot: string;
  take?: number;
  pass?: Pass;
  trim_in?: number;
  trim_out?: number;
  locked?: boolean;
  note?: string;
  /** Phase 9d: this clip's audio from elsewhere (absent / null: its own). */
  audio?: CutAudioSource | null;
  /** left out of the cut (still in the script) */
  out?: boolean;
  /** flagged to come back to */
  flag?: boolean;
  /** its colour (seriesmith/color.py): the fields that aren't 0 */
  color?: ShotColor | null;
  /** frames from / to black at its head / tail; of a dissolve from the clip before */
  fade_in?: number;
  fade_out?: number;
  dissolve?: number;
}

/** What a colour match compares (color.MATCH_BY): the whole frame (six sliders), the
 * skin in it (exposure, warmth, tint, saturation) or its brightness alone (exposure,
 * contrast, black point); the sliders it doesn't set stay the clip's own. */
export type MatchBy = "frame" | "skin" | "luma";

/** POST /seriesmith/color/match: the colour bringing clips in line with a base clip. */
export interface ColorMatch {
  base: string;
  colors: Record<string, ShotColor>;
  skipped: { shot: string; why: string }[];
}

export interface CutFile {
  episode?: string;
  final?: CutEntry[];
  proxy?: CutEntry[];
}

export interface OverrideFields {
  prompt?: string | null;
  seed?: Seed | null;
  model?: string | null;
  loras?: Lora[] | null;
  steps?: number | null;
  note?: string | null;
  /** Phase 8: the shot's video target, shared by both passes; null = the built one.
   * (A ref override: its image target.) */
  target?: string | null;
  /** Phase 8.5: per pass; null clears */
  negative?: string | null;
  model_low?: string | null;
  /** "WxH", per pass; null clears (back to the shotlist's size) */
  size?: string | null;
  /** P4, a ref override only: cfg, and the sampler knobs; null clears */
  cfg?: number | null;
  params?: RefParams | null;
}

export interface OverrideRequest {
  ep: string;
  pass: Pass;
  shot: string;
  both: boolean;
  fields: OverrideFields;
}

/** PUT / DELETE /seriesmith/override: each pass's override (with its `stale`),
 * the target the next render uses and the one the build compiled for. */
export interface OverrideResult {
  override: Partial<Record<Pass, Override & { stale?: boolean }>>;
  target?: string;
  built_target?: string;
}

export interface AssembleResult {
  ok: boolean;
  output: string;
  report: string;
  error?: string;
  /** with `publish`: the assembled cut, and the published file (null if publishing failed) */
  cut?: string;
  published?: string | null;
  /** the loudness check on the export (docs/SOUND.md phase 5; `<cut>_loudness.json`): measured
   * against the mix's target, never changing it. Null: no sound, the XML, or an older server */
  loudness?: LoudnessCheck | null;
  /** the picture's checks on the export (docs/FINISHING.md "The export's checks"; `<cut>_checks.json`):
   * black and frozen runs and flashes, never changing it. Null: skipped, the XML, or an older server */
  checks?: ExportChecks | null;
}

/** A run the export's checks found: seconds in the cut, and the shots playing then. */
export interface ExportCheckRun {
  start: number;
  end: number;
  seconds: number;
  shot: string | null;
  shots: string[];
  /** a flashing run: the most flashes in any one second */
  flashes?: number;
}

/** The export's picture checked (checks.check): what the cut's own fades and held shots explain is left out. */
export interface ExportChecks {
  black: ExportCheckRun[];
  frozen: ExportCheckRun[];
  flashes: ExportCheckRun[];
  explained: { black: number; frozen: number };
  ok: boolean;
  /** in words */
  verdict: string;
}

/** An export's loudness against its target (mix.loudness_check). */
export interface LoudnessCheck {
  integrated_lufs: number;
  range_lu: number;
  true_peak_dbtp: number;
  target_lufs: number;
  /** the true peak's ceiling */
  true_peak_db: number;
  /** integrated minus target, LU */
  off_lu: number;
  /** within 1 LU of the target */
  on_target: boolean;
  over_peak: boolean;
  /** the mix brought it to the target (false: the cut's own sound as it came) */
  mixed: boolean;
  /** in words */
  verdict: string;
}

/** Phase 13: POST /seriesmith/assemble's extras. `upscaled` (final pass): each clip
 * from its fresh upscale, as <ep>_up.mp4; `size`: the cut's size ("1920x1080");
 * `publish`: then the series intro and outro around it, titled (publish). */
export interface AssembleOptions {
  upscaled?: boolean;
  size?: string | null;
  publish?: boolean;
  /** the cut as an FCP7 XML timeline (<cut>.xml), nothing encoded */
  xml?: boolean;
  /** "recording": the episode's recording as the dialogue, under the mix (as Play all plays it) */
  audio?: "recording";
}

/** Phase 13: a final take's upscale (<stem>.up.mp4), as GET /seriesmith/episode says it. */
export interface TakeUpscale {
  status: "queued" | "ok" | "failed";
  /** made from the take's mp4 as it is now (false once the take is re-rendered) */
  fresh: boolean;
  width: number | null;
  height: number | null;
  route: "latent" | "vae" | "pixel" | "seedvr2" | null;
  start_step: number | null;
  /** latent (a re-sample), pixel (an upscale model over the frames) or seedvr2 */
  method?: "latent" | "pixel" | "seedvr2";
  /** the pixel method's model file */
  pixel_model?: string | null;
  /** the SeedVR2 method's model file */
  seedvr2_model?: string | null;
  /** a pixel step after the re-sample: its model, scale and the re-sample's size */
  then_pixel?: { model: string; scale: number; from: [number, number]; method?: "seedvr2" } | null;
  /** Phase 13e: marked Keep (a wholesale redo or Master leaves it alone) */
  keep?: boolean;
  /** against the series' master recipe: same, different, unknown (made before
   * upscales recorded their settings); null: no recipe */
  recipe_match?: "same" | "different" | "unknown" | null;
  /** a delivery size: what was asked for, the fit, and what the last step made */
  deliver?: { width: number; height: number; fit: "crop" | "pad"; made: [number, number] } | null;
  /** a pixel upscale run on an earlier upscale: that one's record (nested for a longer chain) */
  on_upscale?: Record<string, unknown> | null;
  /** the encoder the .up.mp4 was written with (h264_nvenc, hevc_nvenc, libx264) */
  encoder?: string | null;
  precision?: string | null;
  finish?: { frequency_split: boolean; keep_soft: number; grain: number } | null;
  comfy_prompt_id: string | null;
  /** the upscale's mp4, relative to the episode (null until it is written) */
  mp4: string | null;
  save_notes: string;
}

/** Phase 13: POST /seriesmith/upscale. `shots`: their takes in the pass's cut
 * (null: the whole cut); `takes`: that pass's takes named directly (wins). */
export interface UpscaleRequest {
  ep: string;
  /** whose takes: final (the server's default) or proxy */
  pass?: Pass;
  shots?: string[] | null;
  takes?: { shot: string; take: number }[];
  redo?: boolean;
  scale?: number | null;
  start_step?: number | null;
  vae?: boolean;
  /** latent: "pack": the node pack's upscaler in place of ComfyUI's own */
  upscaler?: string;
  /** latent: "pack": the node pack's windows in place of ComfyUI's own */
  windowing?: string;
  /** latent: re-sample takes of other models through this one (a target id) */
  through?: string;
  /** null: each take's default (latent where its target has one, else pixel) */
  method?: "latent" | "pixel" | "seedvr2" | null;
  /** seedvr2: "7b" (the default), "3b" or a model file name */
  seedvr2_model?: string | null;
  /** the pixel method's model (models/upscale_models); null: the default */
  pixel_model?: string | null;
  /** latent: start 0-2 steps earlier than the default (more detail, more change) */
  detail?: 0 | 1 | 2 | null;
  /** latent: then an upscale model takes the re-sample on by `then_scale` (default 2) */
  then_pixel_model?: string | null;
  then_scale?: number | null;
  /** latent: the then step is SeedVR2 (`seedvr2_model`) instead of an upscale model */
  then_method?: "pixel" | "seedvr2";
  /** Phase 13e3: how the .up.mp4 is encoded: review (the default) or master (x264 CRF 12) */
  quality?: "review" | "master";
  /** Phase 13e: each take by the series config's upscale.master recipe (the
   * other choices are ignored) */
  recipe?: boolean;
  /** an exact size: "1080p", "1440p", "4k" or "WxH"; the last pixel step is sized to it
   * and the result cropped (`fit` crop, the default) or padded to it */
  deliver?: string | null;
  fit?: "crop" | "pad";
  /** pixel: run on each take's existing upscale (its .up.mp4, replaced) instead of the take */
  from_upscale?: boolean;
  /** how the .up.mp4 is encoded: auto (NVENC when there, else x264), nvenc, x264 */
  encoder?: "auto" | "nvenc" | "x264";
  /** the upscale model's precision: fp16 (the default, faster) or fp32 */
  precision?: "fp16" | "fp32";
  /** a pixel model's finish: colour and tone from the source (default true), invented
   * detail faded where the source was soft (0-1), film grain (0-0.2) */
  frequency_split?: boolean;
  keep_soft?: number;
  grain?: number;
}

/** A take's post (docs/API.md "A take's `post`"): its fresh upscale finished
 * (enhance, motion blur). `fresh`: made from the upscale as it is now. */
export interface TakePost {
  status: "queued" | "ok" | "failed";
  fresh: boolean;
  /** what made it: {size, enhance?: {method, ...}, motion_blur?} */
  recipe?: { size?: [number, number]; enhance?: Record<string, unknown>; motion_blur?: number } | null;
  width?: number | null;
  height?: number | null;
  comfy_prompt_id?: string | null;
  mp4: string | null;
  save_notes: string;
}

/** POST /seriesmith/post. `recipe` (or neither `enhance` nor `blur`): the series' post.master. */
export interface PostRequest {
  ep: string;
  pass?: Pass;
  shots?: string[] | null;
  takes?: { shot: string; take: number }[];
  redo?: boolean;
  recipe?: boolean;
  /** a tier (draft, production, cinematic), a method, an object, or "none" */
  enhance?: string | Record<string, unknown> | null;
  /** motion blur, 0-1 of the frame interval */
  blur?: number | null;
  quality?: "review" | "master" | null;
}

export interface PostResult {
  queued: { shot: string; take: number; what: string; width: number; height: number; prompt_id: string }[];
  skipped: { shot: string; take?: number; reason: string }[];
  errors: { shot: string; take?: number; error: string }[];
}

/** whether this ComfyUI can run a post step (post.not_ready's sentences) */
export interface PostReadiness {
  status: "ready" | "not_ready" | "unknown";
  missing: string[];
}

/** GET /seriesmith/post/options */
export interface PostOptions {
  tiers: { id: string; enhance: Record<string, unknown>; text: string; readiness: PostReadiness }[];
  methods: string[];
  blur: { min: number; max: number; default: number; readiness: PostReadiness };
  strength: { min: number; max: number; default: number };
  /** the episode's post.master (asked with `ep`; null: none) */
  recipe: { fields: Record<string, unknown>; text: string;
            shots: Record<string, { fields: Record<string, unknown>; text: string }>;
            problems: string[] } | null;
}

/** GET /seriesmith/upscale/options: what the Upscale dialog can offer here. */
export interface UpscaleOptions {
  pixel: { status: "ready" | "not_ready" | "unknown"; missing: string[]; models: string[]; default: string };
  /** SeedVR2 (core nodes, its own model files): absent from older servers */
  seedvr2?: { status: "ready" | "not_ready" | "unknown"; missing: string[]; models: string[]; default: string };
  /** each video target's latent upscale: null when it has none */
  latent: Record<string, {
    status: "ready" | "not_ready" | "unknown"; missing: string[];
    /** resample (H3: any scale on the `align` grid) or second_stage (LTX-2: `fixed_scale`) */
    /** resample (H3), second_stage (LTX-2), pixel_refine (Wan: a pixel model, then its sampler) */
    mode?: "resample" | "second_stage" | "pixel_refine"; align?: number; fixed_scale?: number | null;
    /** the nodes a re-sample can use, when there's a choice here ("": ComfyUI's own; "pack") */
    upscalers?: { id: string; label: string }[];
    /** the same, for a take long enough to be sampled in windows */
    windowings?: { id: string; label: string }[];
    /** what its re-sample's latents are: takes of the same family keep their own re-sample */
    family?: string | null;
  } | null>;
  /** the models any take can be re-sampled through */
  through?: { id: string; label: string; status: string | null; family: string | null }[];
  details: number[];
  max_scale?: number;
  encoders?: string[];
  precisions?: string[];
  delivers?: { id: string; width: number; height: number }[];
  fits?: string[];
  /** Phase 13e: the episode's master recipe (asked with `ep`; null: none) */
  recipe?: RecipeView | null;
}

/** Phase 13e: POST /seriesmith/master's plan: each shot of the cut against the recipe. */
export interface MasterPlan {
  pass: Pass;
  size: [number, number];
  fit: "crop" | "pad";
  quality: "review" | "master";
  /** Post-process on: posts where present or by the recipe (absent from older servers) */
  post?: boolean;
  /** off, present (each shot's fresh post where it has one, else its upscale) or recipe */
  post_mode?: "off" | "present" | "recipe";
  counts: { upscale: number; post?: number; ok: number; kept: number; queued: number; gap: number };
  ready: boolean;
  rows: {
    shot: string; take: number | null; target: string | null;
    status: "upscale" | "post" | "ok" | "kept" | "queued" | "gap"; why: string; recipe: string;
    upscale: { width: number | null; height: number | null; status: string; keep: boolean } | null;
    post?: { status: string; fresh: boolean; recipe: Record<string, unknown> | null } | null;
  }[];
}

export interface MasterResult {
  plan: MasterPlan;
  queued?: string[];
  errors?: { shot: string; error: string }[];
  /** assemble: the master, its ProRes .mov and the report, relative to the episode */
  output?: string;
  mov?: string | null;
  report?: string;
  /** the intro / outro the master was made with (publish), null: none found */
  titles?: MasterTitles | null;
  /** assemble: the job as it ended (GET /seriesmith/master/job has the same) */
  job?: MasterJob;
  /** the master already made at the recipe's size and its ProRes .mov (null: none yet) */
  existing?: { output: string; mov: string | null } | null;
}

/** The titles publish put on a master, and how it laid the cut in between:
 * `copied` (only the title clips encoded) or `re-encoded` (the whole cut; `why`). */
export interface MasterTitles {
  intro: string | null;
  outro: string | null;
  picture?: "copied" | "re-encoded" | null;
  why?: string;
}

/** A master being assembled, or the last one this ComfyUI assembled
 * (GET /seriesmith/master/job, and every `seriesmith.master` event). */
export interface MasterJob {
  /** the queue's job (absent for a run elsewhere) */
  id?: string;
  /** what it makes: the master, or only the ProRes .mov of the one made */
  action?: "assemble" | "prores";
  ep: string;
  pass: Pass | null;
  state: "running" | "done" | "failed";
  /** started by something other than this editor (`seriesmith master`): no progress to show */
  elsewhere: boolean;
  by: string | null;
  started: string | null;
  finished: string | null;
  /** where it is: assemble (assemble) or titles (publish) */
  step: "assemble" | "titles" | null;
  /** probe, clips, join, prores, verify (assemble); titles, join, verify, reencode, prores (titles) */
  stage: string | null;
  done: number | null;
  total: number | null;
  text: string;
  output: string | null;
  mov: string | null;
  report: string | null;
  titles: MasterTitles | null;
  error: string;
}

/** The series config's upscale.master, as the Upscale dialog shows it. */
export interface RecipeView {
  deliver: string | null;
  fit: "crop" | "pad";
  quality: "review" | "master";
  encoder: string;
  /** each video target's section (null: none covers it) */
  targets: Record<string, { key: string; fields: Record<string, unknown>; text: string } | null>;
  /** shots with their own recipe (overrides.json) */
  shots: Record<string, { fields: Record<string, unknown>; text: string }>;
  problems: string[];
}

export interface UpscaleResult {
  queued: { shot: string; take: number; route: "latent" | "vae" | "pixel" | "seedvr2"; scale: number; start_step: number | null;
            method?: "latent" | "pixel" | "seedvr2"; pixel_model?: string | null; then_pixel_model?: string | null;
            seedvr2_model?: string | null;
            width: number; height: number; prompt_id: string }[];
  skipped: { shot: string; take?: number; reason: string }[];
  errors: { shot: string; take?: number; error: string }[];
}

export interface UpscaleEvent {
  ep: string;
  shot: string;
  take: number;
  status: "queued" | "ok" | "failed" | "deleted";
}

// websocket events (docs/API.md "Live updates")
export interface TakeEvent {
  ep: string;
  pass: Pass;
  shot: string;
  take: number;
  status: TakeStatus;
  thumb?: string | null;
}

export interface EpisodeEvent {
  ep: string;
}

export interface ProgressEvent {
  value: number;
  max: number;
  prompt_id?: string;
  node?: string | null;
}

export interface PromptEvent {
  prompt_id?: string;
  exception_message?: string;
  node_type?: string;
  [key: string]: unknown;
}

export interface ComfyQueue {
  running: string[];
  pending: string[];
}

// ---------------------------------------------------------------------------
// folder browser (API.md "Round 2 additions")
// ---------------------------------------------------------------------------

export interface BrowseDir {
  name: string;
  path: string;
  /** has a series.json and a script */
  episode: boolean;
  /** has a series.json */
  series_config: boolean;
}

export interface BrowseFile {
  name: string;
  path: string;
  size?: number;
}

export interface BrowseResult {
  /** "" (or absent) at the starting points */
  path: string;
  /** null at the starting points; "" at a drive root (up = the starting points) */
  parent: string | null;
  episode: boolean;
  truncated: boolean;
  dirs: BrowseDir[];
  /** only when the request asks for files (`files=image|audio`) */
  files?: BrowseFile[];
}

export type BrowseFiles = "image" | "audio" | "video";

// ---------------------------------------------------------------------------
// references (API.md "References (Phase 5)")
// ---------------------------------------------------------------------------

export type RefScope = "series" | "shot";
export type RefKind = "character" | "prop" | "vehicle" | "location" | "voice" | "keyframe";

export interface RefTake {
  /**
   * the reference images this take was generated FROM, in order; `[]` when it
   * was generated from the prompt alone. On a target that does both (Qwen-Image
   * 2.1) this is the only way to tell an edit from a text-to-image generate.
   */
  references?: { id?: string | null; name?: string | null; view?: string | null; path?: string | null }[];
  take: number;
  /** the character view it belongs to (null for every other ref) */
  view?: string | null;
  status: TakeStatus;
  /** finished with a file: it can be picked */
  usable?: boolean;
  seed: Seed | null;
  seed_source?: string | null;
  /** the candidate image, relative like `path`; null for a voice (see `audio`) or no file */
  image: string | null;
  /** a voice's candidate recording (then `image` is null) */
  audio?: string | null;
  /** "frame": a keyframe cut out of a video take (POST /seriesmith/refs/keyframe);
   * "from_take" (Phase 9c): a voice sample cut out of a take's sound */
  source: "generated" | "imported" | "frame" | "from_take" | "edited" | "pano" | "tour";
  /** where a "frame" or "from_take" take came from */
  from?: RefFrameSource;
  /** an "edited" take: the picture it started from and the instruction */
  edit?: RefEditRecord;
  /** P4: what else it was drawn with */
  cfg?: number | null;
  params?: RefParams;
  note: string;
  prompt?: string | null;
  model?: string | null;
  steps?: number | null;
  loras?: Lora[] | null;
  overrides?: string[];
  queued?: string | null;
  finished?: string | null;
  save_notes?: string;
  comfy_prompt_id?: string | null;
  /** image size, once the saver or the import has written it */
  width?: number | null;
  height?: number | null;
  /** the image target it was generated with */
  target?: string | null;
  /** an upload's file name (POST /seriesmith/refs/import, multipart) */
  original_name?: string;
  // ---- Phase 9c-B: a voice candidate ----
  /** how long it was asked to be (whole seconds after the grid snapped it) */
  seconds?: number | null;
  /** the line it says */
  line?: string | null;
  /** where that line came from */
  line_source?: VoiceLineSource | null;
}

/** Where a generated voice's line comes from: the character's longest line in
 * this episode's script, the fixed neutral sentence, this call's prompt, or
 * the ref's prompt override. */
export type VoiceLineSource = "script" | "neutral" | "request" | "override" | (string & {});

/** A ref's override as `/refs` lists it: the field names, `stale`, and the values. */
export interface RefOverrideInfo {
  fields: string[];
  stale: boolean;
  values?: Override;
  /**
   * P9, a character's view only: the fields set on THIS view, as opposed to
   * inherited from the character (`fields` and `values` are the two merged).
   * "Remove this view's own settings" drops exactly these.
   */
  own?: string[];
}

/** A candidate of a shared ref from the episode that picked its live file
 * (GET /seriesmith/refs/owner-takes): read-only, `picked` its pick. */
export type OwnerTake = RefTake & { episode: string; picked: boolean };

/** POST /seriesmith/refs/relight: a sequence's plates (or some locations) under another light */
export interface RelightRequest {
  ep: string;
  relight: string;
  sequence?: string;
  locations?: string[];
  suffix?: string | null;
  target?: string | null;
  count?: number;
  repoint?: boolean;
  dry_run?: boolean;
  backend?: string;
}

export interface RelightResult {
  locations: { source: string; id: string; exists: boolean; entry: Record<string, unknown> }[];
  queued: { ref: string; view: string | null; take: number; prompt_id: string; seed: string; target?: string }[];
  errors: { ref?: string; view?: string | null; take?: number; error: string }[];
  /** what re-pointing changed: the sequence id, shot ids */
  repointed: string[];
}

export interface RefView {
  /** 01_threequarter | 02_side | 03_back | 04_face */
  view: string;
  picked: number | null;
  /** Clear (DELETE /seriesmith/refs/pick) removed its pick; auto-pick leaves it alone */
  cleared?: boolean;
  /** what this view generates with now */
  prompt?: string | null;
  /**
   * P9: the series config's wording for this view, before any override — what a
   * prompt edit is diffed against and reverted to. (Before P9 the editor had no
   * text to compare an overridden view prompt with.)
   */
  built_prompt?: string;
  /** the view's override: its values are the character's own fields, then the view's */
  override?: RefOverrideInfo;
  effective?: RefEffective | null;
  takes: RefTake[];
}

/** What a generate (seed_mode auto, nothing else set) would use now. A
 * character's top-level `effective` is just `{target}`: each view has the rest. */
export interface RefEffective {
  prompt?: string;
  /** null when a generate would pick a new seed */
  seed?: Seed | null;
  seed_source?: string;
  model?: string | null;
  loras?: Lora[] | null;
  steps?: number | null;
  width?: number | null;
  height?: number | null;
  /** the image target a generate uses now (an audio one for a voice) */
  target?: string | null;
  /** P4: cfg, the sampler knobs and the negative a generate would use */
  cfg?: number | null;
  params?: RefParams;
  negative?: string;
  negative_source?: NegativeSource;
  // ---- Phase 9c-B, a voice ref ----
  /** how long a generate would be, after the target's grid snapped it */
  seconds?: number | null;
  /** the line it would say, and where that line comes from */
  line?: string | null;
  line_source?: VoiceLineSource | null;
  /** the audio target's longest sample */
  max_seconds?: number | null;
}

/** Phase 8.5: whether a shot's target needs a keyframe to render. */
export type KeyframeNeed = "required" | "optional";
/** How a keyframe is filled: the script's `first:` / `last:` line, else
 * continuity (a shot with a previous shot), else generate. A path is also
 * allowed (the script names a file). */
export type KeyframeMethod = "continuity" | "generate" | "import" | "none" | (string & {});

/** A reference image an edit target receives with a keyframe generate. */
export interface EditRef {
  /** null for a composite (a single-reference target gets one collage of the parts) */
  id: string | null;
  role?: "subject" | "plate" | "composite" | (string & {});
  view?: string | null;
  /** null for a composite until a generate composes it */
  path?: string | null;
  /** a composite's name, and what it is made of */
  name?: string;
  parts?: { role?: string; subject?: string; location?: string; name?: string; kind?: string; view?: string | null; path?: string | null }[];
}

/** Where an image-target default comes from: set in the editor for the episode
 * (PUT /seriesmith/refs/defaults), the series config's `refs` block, or built in. */
export type RefDefaultSource = "editor" | "series" | "default";

/** GET /seriesmith/refs `defaults`: the image targets refs and keyframes generate with. */
export interface RefDefaults {
  /** the image target series refs generate with */
  target?: string | null;
  target_source?: RefDefaultSource | null;
  /** the image target keyframes generate with */
  keyframe_target?: string | null;
  keyframe_target_source?: RefDefaultSource | null;
  /** the image target an edit of a picture uses (one that can edit; null when none can) */
  edit_target?: string | null;
  /** the same for a character (differs only when no edit model is chosen) */
  edit_target_person?: string | null;
  edit_target_source?: RefDefaultSource | null;
  /** the image target Turn runs on (one that can edit); null: automatic (Qwen 2.1 + angles
   *  when it's installed, else the edit target) */
  turn_target?: string | null;
  turn_target_source?: RefDefaultSource | null;
  /** Phase 9c-B: the audio target voice refs generate with */
  voice_target?: string | null;
  voice_target_source?: RefDefaultSource | null;
  /** the video model a dub track renders on: the voice model when it's one, else H3 Ref2VA */
  dub_target?: string | null;
  dub_target_source?: RefDefaultSource | null;
}

export interface Ref {
  /** subject:<id> | location:<id> | voice:<id> | shot:<shot>:first|last */
  id: string;
  scope: RefScope;
  kind: RefKind;
  name: string;
  /** the file renders read; null when the series config names none (a voice-only character) */
  path: string | null;
  exists: boolean;
  sha1: string | null;
  /** the live picture's [width, height]; null for a sample or no file (absent: an older server) */
  size?: [number, number] | null;
  used_by: Partial<Record<Pass, string[]>>;
  /** the prompt a generate would use now; null when the series config lacks what it needs */
  prompt: string | null;
  /** the id as a file-name stem (`:` as `__`) */
  key?: string;
  /** the series config subject it belongs to (null for a location or a keyframe) */
  subject?: string | null;
  /** a voice: the speaker it has on each provider (voices.<provider> in the series config) */
  speakers?: Record<string, { id: string; name?: string; preview?: string }>;
  /**
   * a wardrobe variant's base: the subject it is a variant of (`of:` in the
   * series config), null for everything else. A variant keeps that character's
   * `name` — it is the same character, and that name goes into every prompt —
   * so this is what tells the two rows apart.
   */
  of?: string | null;
  /** a relit location (sequence relight): the relight preset id or instruction; `of` its source */
  relight?: string | null;
  /** false when this ref can't be generated; `why_not` says why */
  can_generate?: boolean;
  why_not?: string | null;
  override: RefOverrideInfo;
  /** a character's four views; `[]` for every other ref */
  views?: RefView[];
  /**
   * The ref's own takes. For a character (P8) these are supplied whole sheets
   * on the reserved `sheet` view -- nothing else can be a take of a character,
   * since its views each have their own.
   */
  takes: RefTake[];
  picked: number | null;
  /** P5, a location: its 360 panoramas (never picked into the plate) */
  panos?: RefTake[];
  /** a location: the picture a tour starts from (its plate, or an angle's place's); null: none */
  tour_from?: string | null;
  /** P5, a location: its camera tours, and their held frames (never picked where they are) */
  tours?: RefTour[];
  tour_holds?: RefTake[];
  /** a character: its supplied sheet was cleared */
  sheet_cleared?: boolean;
  /**
   * The OTHER episodes beside this one whose series config names the same live
   * file (the `../refs/...` layout). Empty when nothing is shared. A pick or a
   * clear here is a change every one of them sees, and their takes then go
   * `stale: ref`.
   */
  shared_with?: string[];
  /**
   * Which episode's pick wrote the file that is live now, by sha1 -- this one, a
   * sibling, or null. Null means nobody's record matches it: it was put there by
   * hand or replaced outside the editor, so no candidate anywhere can put it
   * back. See `web/src/lib/shared.ts` for what that changes.
   */
  live_owner?: string | null;

  /** A character: its sheet's panels, 4 (the views) or 1 (one whole picture, `sheet_panels: 1`). */
  panels?: number;
  /** marked one whole picture (`panels` 1), but its file is a strip of panels (4:1): renders send the whole strip */
  panels_conflict?: boolean;
  /**
   * P8, a character only: which route wrote the sheet that is live now --
   * "sheet" (one supplied as a take), "views" (stitched from the four picks),
   * or null. Null also covers a sheet copied into the folder by hand, which is
   * a perfectly good way to supply one: the file is used, it just has no take
   * behind it.
   */
  live_from?: "sheet" | "views" | null;
  /** Clear removed its pick (auto-pick leaves it alone until something is picked) */
  cleared?: boolean;
  /** the ref's own override values (the same as `override.values`) */
  override_values?: Override;
  /** what a generate uses now; null when it can't be generated */
  effective?: RefEffective | null;
  /** the series config's prompt before any override (a character's: its sheet text) */
  built_prompt?: string;
  // ---- Phase 8.5: keyframes as needed refs ----
  /** required (e.g. Wan 14B I2V's first frame) or optional; absent from older
   * servers, and null for a keyframe no target reads */
  need?: KeyframeNeed | null;
  method?: KeyframeMethod | null;
  shot?: string | null;
  which?: "first" | "last" | null;
  /** a keyframe: the video target that will read it */
  target?: string | null;
  /** the script's `first:` / `last:` line asks for this keyframe (so
   * "missing" and Generate missing include it when optional) */
  requested?: boolean;
  /** the script's raw `first:` / `last:` value */
  script?: string | null;
  /** whether the shot's target reads that end */
  reads?: boolean | null;
  /** a path the script names (method "import") */
  import_path?: string;
  /** a continuity first frame, per pass: whether the live keyframe still shows the
   * take that pass's cut uses for the previous shot (a render cuts it again when
   * "missing" or "stale"; "own" = imported or generated, left alone) */
  continuity?: Partial<Record<Pass, { state: "ok" | "missing" | "stale" | "cleared" | "own" | "unknown"; why: string }>>;
  /** with an edit keyframe target: exactly the references a generate feeds it */
  edit_refs?: EditRef[];
}

export interface RefList {
  refs: Ref[];
  /** the episode's image targets (null when the series config's `refs` block is bad) */
  defaults?: RefDefaults | null;
}

export interface RefGenerateRequest {
  ep: string;
  ref: string;
  view: string | null;
  count: number;
  seed_mode: SeedMode;
  seed: Seed | null;
  prompt: string | null;
  model: string | null;
  loras: Lora[] | null;
  steps: number | null;
  note: string;
  /** Phase 8.5: an image target for this call, beating the ref's override and
   * the series default. Only sent when set. */
  target?: string | null;
  /** Phase 9c-B: how many seconds of voice (a voice ref only; 400 on anything
   * else, or outside the audio target's range). Only sent when set. */
  seconds?: number | null;
  /** an edit of a picture the ref already has (`prompt` is the instruction) */
  edit?: RefEditRequest | null;
  /** P5: a 360 panorama of a location (its live plate, then `with`'s) */
  pano?: { with?: string[]; engine?: "qwen" | "klein" } | null;
  /** P4: the picture's size, "WxH" (a 360's: 2:1) */
  size?: string | null;
  /** P4: cfg and the target's sampler knobs for this call (the gallery's Regenerate) */
  cfg?: number | null;
  params?: RefParams | null;
  /** seriesmith: make it on this backend (absent: its target's own). Only sent when set. */
  backend?: string;
}

/** P5: one camera tour of a location (tour.py) */
export interface RefTour {
  tour: number;
  status: "queued" | "ok" | "failed" | (string & {});
  move: string;
  seconds: number;
  seed?: number;
  holds: number[];
  error?: string;
  queued?: string;
  finished?: string | null;
  video?: string | null;
}

/** A picture brought into an edit (image 2 onward): a ref's live picture, or one take. */
export interface RefEditWith {
  ref: string;
  view?: string | null;
  take?: number | null;
}

/** POST /seriesmith/refs/generate `edit`: change a picture the ref already has.
 * `take` null edits the live picture; `wrap` false sends the instruction
 * (the request's `prompt`) exactly as typed, for a LoRA's trigger syntax. */
export interface RefEditRequest {
  take: number | null;
  with?: RefEditWith[];
  wrap?: boolean;
  /** P5: the picture comes from another of the character's views (the take lands on `view`) */
  from_view?: string | null;
  /** P5: draw the view by turning the camera (Qwen 2.1 + the multi-angle LoRA) */
  turn?: boolean;
}

/** What an edited take's sidecar records. */
export interface RefEditRecord {
  take: number | null;
  view?: string | null;
  instruction: string;
  wrap?: boolean;
  with?: RefEditWith[];
}

export interface RefGenerateResult {
  queued: { ref: string; view: string | null; take: number; prompt_id: string; seed: Seed; target?: string }[];
  errors: { ref?: string; view?: string | null; error: string; take?: number }[];
}

/** POST /seriesmith/refs/generate-missing (Phase 8.6). */
export interface RefGenerateMissingRequest {
  ep: string;
  pass?: Pass;
  /** default both */
  kinds?: ("series" | "keyframe")[];
  target?: string | null;
  keyframe_target?: string | null;
  /** plan only: the same shape, nothing queued (take / prompt_id null) */
  dry_run?: boolean;
  /** seriesmith: make it on this backend (absent: its target's own). Only sent when set. */
  backend?: string;
}

/** How Generate missing filled a ref: a generated candidate, a frame from the
 * neighbouring take (continuity), or the script's file (import). */
export type MissingMethod = "generate" | "continuity" | "import" | (string & {});

export interface RefGenerateMissingResult {
  /** a still (method generate); a dry run's take / prompt_id are null, and seed when a new one would be drawn */
  queued: { ref: string; view?: string | null; take: number | null; prompt_id: string | null; seed?: Seed | null; seed_source?: string | null; target?: string | null; method?: MissingMethod }[];
  /** filled at once: a continuity frame or the script's file (a dry run's take is null) */
  picked: { ref: string; take: number | null; method?: MissingMethod; view?: string | null }[];
  skipped: { ref: string; reason: string; view?: string | null }[];
  /** as `/refs/generate`'s errors (`missing_files` when a model isn't installed) */
  errors: { ref?: string; view?: string | null; error: string; take?: number; missing_files?: MissingFile[] }[];
}


/** P8: POST /seriesmith/refs/match -- which slot does each file name mean? */
export interface RefMatch {
  file: string;
  ref: string;
  view: string | null;
  /** the slot's display name */
  name: string;
  kind: RefKind;
  /** the slot takes audio (a voice), not an image */
  audio: boolean;
  /** the live file, relative to the episode */
  path: string | null;
  /** why it matched, in words -- shown in the table before anything is sent */
  why: string;
}

export interface RefMatchResult {
  matched: RefMatch[];
  unmatched: { file: string; why: string }[];
}

export interface RefPickRequest {
  ep: string;
  ref: string;
  view?: string | null;
  take: number;
}

export interface RefImportRequest {
  ep: string;
  ref: string;
  view?: string | null;
  source_path: string;
  /** Phase 8.6: pick it at once */
  pick?: boolean;
}

/** POST /seriesmith/refs/import as multipart/form-data (Phase 8.6, drag and drop). */
/** POST /seriesmith/take/import (JSON: a video on the server's machine). */
export interface TakeImportRequest {
  ep: string;
  pass: Pass;
  shot: string;
  source_path: string;
  pick?: boolean;
  note?: string;
}

/** POST /seriesmith/take/import as multipart. */
export interface TakeUploadRequest {
  ep: string;
  pass: Pass;
  shot: string;
  file: Blob;
  name?: string;
  pick?: boolean;
}

/** POST /seriesmith/take/copy: another shot's take as this shot's new one. */
export interface TakeCopyRequest {
  ep: string;
  pass: Pass;
  shot: string;
  from_shot: string;
  take: number;
  from_pass?: Pass;
  pick?: boolean;
}

/** What take/import and take/copy answer. */
export interface ImportedShotTake {
  shot: string;
  take: number;
  pass: Pass;
  status: TakeStatus;
  sidecar: Sidecar;
  mp4: string | null;
  thumb: string | null;
  picked: boolean;
  /** why it wasn't picked (a locked cut entry) */
  why?: string;
}

export interface RefUploadRequest {
  ep: string;
  ref: string;
  view?: string | null;
  /** pick it at once (sent as "1") */
  pick?: boolean;
  file: Blob;
  /** the file's name (a File has its own) */
  name?: string;
}

/** POST /seriesmith/refs/discard (Phase 8.6): move a candidate to `_trash/`. */
export interface RefDiscardRequest {
  ep: string;
  ref: string;
  view?: string | null;
  take: number;
}

/** A keyframe take's source: shot, take and pass, and the frame index used.
 * Phase 9c: a voice cut out of a take carries `start` / `end` seconds instead
 * of a frame. */
export interface RefFrameSource {
  shot: string;
  take: number | null;
  pass: Pass | null;
  frame?: number | null;
  frames?: number | null;
  /** seconds into the take's sound (source "from_take") */
  start?: number | null;
  end?: number | null;
}

/** Where a voice sample was cut from (the answer's `source`, as built). */
export interface VoiceClipSource {
  shot: string;
  take: number | null;
  pass: Pass | null;
  start: number;
  end: number;
  /** the file the sound came from, relative to the episode */
  file?: string | null;
}

/** POST /seriesmith/refs/voice-from-take: a line a take already spoke as a sample. */
export interface VoiceFromTakeRequest {
  ep: string;
  ref: string;
  shot: string;
  take: number;
  pass: Pass;
  start: number;
  end: number;
  /** null (the default): pick it only when the voice has no live file */
  pick?: boolean | null;
  note?: string;
}

/**
 * The ref as `/refs` lists it, plus what the cut became. Careful: as built,
 * the answer's `picked` is a BOOLEAN (whether the new candidate went live),
 * not the ref listing's picked take number, which it overwrites — so the
 * editor refetches the listing instead of using this as a Ref.
 */
export type VoiceFromTakeResult = Omit<Ref, "picked"> & {
  picked: boolean;
  /** the new candidate */
  take: number;
  /** where the sound came from. As built this is an OBJECT (the contract only
   * said "source"): the shot, take, pass, span and the file it was cut from. */
  source?: VoiceClipSource | null;
  /** the pick wrote `voice_sample` into the series config */
  series_changed?: boolean;
};

/** PUT /seriesmith/refs/pick: the ref, and whether the series config gained a
 * `voice_sample` line (Phase 9c-B). */
export type RefPickResult = Ref & { series_changed?: boolean };

/** POST /seriesmith/refs/keyframe: a shot's first / last keyframe from a frame of a take. */
export interface RefKeyframeRequest {
  ep: string;
  pass: Pass;
  shot: string;
  which: "first" | "last";
  /** default: the previous (first) / next (last) shot in the cut */
  source_shot?: string | null;
  /** default: the take that shot's cut entry uses */
  source_take?: number | null;
  /** a frame number (negative from the end), "first" or "last"; default: last for first, first for last */
  frame?: number | "first" | "last" | null;
  /** null: picked only if the keyframe has no live file; true: always; false: never */
  pick?: boolean | null;
}

export interface RefOverrideRequest {
  ep: string;
  ref: string;
  view?: string | null;
  fields: OverrideFields;
}

export interface RefEvent {
  ep: string;
  ref: string;
  view: string | null;
  take: number | null;
  /** queued | ok | failed | picked, or cleared (DELETE /seriesmith/refs/pick) */
  status: TakeStatus | "picked" | "cleared" | (string & {});

}

// ---------------------------------------------------------------------------
// targets (API.md "Targets (Phase 7)", "Phase 8 additions")
// ---------------------------------------------------------------------------

/** music: a score cue (docs/SOUND.md; GET /seriesmith/targets?kind=music) */
export type TargetKind = "video" | "image" | "audio" | "music" | "ambience" | "foley";

/** One binding entry: a graph widget (`class_type` + `field`, or for LoRAs
 * `name`/`strength`/`input`/`chain`), or `{"via": "loader"}`. */
export type TargetWidget =
  | { class_type: string; field?: string; name?: string; strength?: string; input?: string; chain?: boolean }
  | { via: string };

export interface TargetPreset {
  model?: string | null;
  lora?: string | null;
  loras?: Lora[] | null;
  steps?: number | null;
  width?: number | null;
  height?: number | null;
  [key: string]: unknown;
}

export interface Target {
  id: string;
  kind: TargetKind;
  label: string;
  /** the provider of the user's own that runs it */
  service?: string;
  /** that provider's name */
  service_label?: string;
  /** that provider's speakers can be listed (GET /seriesmith/providers/voices) */
  service_voices?: boolean;
  /** what this show changes of the model (<show>/targets/overrides.json) */
  show_fields?: string[];
  default?: boolean;
  presets?: Partial<Record<Pass, TargetPreset>>;
  widgets?: {
    model?: TargetWidget;
    loras?: TargetWidget;
    /** tolerated alias */
    lora?: TargetWidget;
    steps?: TargetWidget;
    seed?: TargetWidget;
    [key: string]: TargetWidget | undefined;
  };
  workflow?: string;
  loader?: string;
  saver?: string;
  /** Phase 8: a short label ("H3", "LTX-2") */
  short?: string;
  /** Phase 8: what the target can use; `keyframes` lists the ends it reads ([] for none) */
  capabilities?: {
    keyframes?: string[];
    policies?: string[];
    voice_reference?: boolean;
    /** it can dub a track of its own: a take's sound, a dub track */
    dubs_tracks?: boolean;
    /** it can make frames of a take again, the rest held (redo_range) */
    remakes_frames?: boolean;
    /** it can make a dub track (a voice model beside the audio targets: refs.voice_target) */
    dub_track?: boolean;
    subject_refs?: boolean;
    prompt?: string;
    negative_prompt?: boolean;
    /** Phase 8.5, image targets: text-to-image, or an edit with reference images */
    mode?: "t2i" | "edit" | (string & {});
    /** Phase 8.5, image edit targets: how many reference images it takes */
    max_refs?: number;
    /** Phase 8.5, video: the first keyframe is required (Wan 14B I2V) */
    requires_first?: boolean;
    /** Phase 9c-B, audio targets: it can copy a voice from a sample
     * (`ltx2_voice` says false: the ID-LoRA weights aren't installed) */
    reference_audio?: boolean;
    /** Phase 9c-B, audio targets: the longest sample it generates, seconds */
    max_seconds?: number;
    /** music targets: the tempo is asked in words ("text"), as its own input ("bpm"), or in its plan's Q: line ("abc": YuE2) */
    tempo?: "text" | "bpm" | "abc";
    /** music targets: an arc told as a story, sections as tags, its own plan (YuE2), or a style a bar (Magenta RT 2) */
    structure?: "story" | "sections" | "plan" | "schedule";
    /** music targets: it sings a section's lyrics */
    lyrics?: boolean;
    /** music targets: bars of a take can be made again (POST /seriesmith/cue/repaint; ACE-Step) */
    repaint?: boolean;
    /** music targets: a song on it must have lyrics (YuE2 sings words) */
    needs_lyrics?: boolean;
    /** music targets: how it hears a cue's theme: sung as its melody (YuE2), as its timbre (ACE-Step),
     * rendered from its sound (Stable Audio 3: at `theme_strength`), or not at all */
    theme?: "melody" | "timbre" | "audio" | null;
    /** a target that renders from a theme's sound: where its schedule starts by default (0.86) */
    theme_strength?: number;
    [key: string]: unknown;
  };
  template?: TargetTemplate;
  /** The family each model param must be (target.json `models`), by param. */
  models?: Record<string, { family: string; label?: string; patterns?: string[]; folder?: string | null; tier?: RequirementTier }>;
  /** Only with `?ready=1`: what's installed, what's missing and where to get it. */
  readiness?: Readiness | null;
  /** Phase 11: which workflow this target's next render uses. */
  graph?: TargetGraph;
  /** Phase 12: a show's own target, from `<show>/targets/<id>/target.json`. */
  custom?: boolean;
  /** Phase 12: saved but not proved yet — no probe render has succeeded, so the
   * shot and episode pickers leave it out. */
  draft?: boolean;
  /** A built-in that ships as a draft (an untested Router model): switched on
   * for every show in the settings (PUT /seriesmith/targets/custom {draft}). */
  shipped_draft?: boolean;
  /** where it lives: seriesmith's own, every show's (beside the settings), or one show's */
  scope?: "builtin" | "user" | "show";
  /** a video or (hosted) image target's limits (seriesmith.limits; PUT /seriesmith/targets/limits) */
  limits?: Limits | ImageLimits;
}

/** What a hosted image model takes (seriesmith/limits.py describe_image): no
 * length or sound; its size as the ratios / named resolutions / sizes it
 * offers or a pixel range; how many pictures (0: text to image only). */
export interface ImageLimits {
  size: { ratios?: string[]; resolutions?: string[]; sizes?: string[]; min_pixels?: number; max_pixels?: number };
  prompt: { max_chars?: number };
  pictures: { references?: number; via?: string };
  editable?: string[];
  overridden?: boolean;
  shipped?: Omit<ImageLimits, "editable" | "overridden" | "shipped">;
}

/** What a video target takes (seriesmith/limits.py): read from its target.json,
 * written back where each lives. */
export interface Limits {
  length: {
    frames?: { step: number; base: number; max: number };
    fps?: number;
    fps_from_series?: boolean;
    /** the length the model was trained on (frames) */
    trained?: number;
    /** a hosted model's whole seconds: a range, or a set */
    seconds?: { min?: number; max?: number; values?: number[] };
  };
  size: {
    multiple?: number;
    fit?: "error" | "snap";
    long_side?: number;
    pixels?: number;
    /** the only sizes a model takes, [width, height] */
    sizes?: [number, number][];
    /** a hosted model's named resolutions ("720p", "1280x720") */
    resolutions?: string[];
  };
  prompt: { max_chars?: number };
  pictures: {
    references?: number | null;
    first?: boolean;
    last?: boolean;
    needs_first?: boolean;
    /** how pictures are sent: "" a link, "base64" inline bytes, "datauri", "seedance" its library */
    via?: string;
  };
  sound: boolean;
  /** the sections (or "pictures.needs_first") that can change */
  editable?: string[];
  /** a built-in's limits changed on this machine, and what it shipped with */
  overridden?: boolean;
  shipped?: Omit<Limits, "editable" | "overridden" | "shipped">;
}

/** A schema field written for several models at once (router_inspect.shared_fields):
 * this model's limit is in its prose. */
export interface SharedField { input: string; field: string; text: string }

/** Phase 12b: one saved ComfyUI workflow (GET /seriesmith/workflows). */
export interface WorkflowFile {
  name: string;
  /** a workflow one of seriesmith's own targets already drives */
  target?: boolean;
}

/** Phase 12b: POST /seriesmith/targets/inspect — the target.json it proposes, and
 * what it could not work out. `proposal` is saved as-is once confirmed. */
export interface TargetProposal {
  proposal: Record<string, unknown>;
  matched: Record<string, string>;
  ambiguous: {
    param: string;
    ask: string;
    candidates: { node: string; class_type: string; field: string; title?: string; value?: unknown }[];
  }[];
  warnings: string[];
  models: { param: string; file: string; family?: string; folder?: string; label?: string }[];
  /** node classes outside ComfyUI core, by the pack they come from */
  nodes: Record<string, string>;
  /** widgets no param covers: they keep the graph's own value */
  unbound?: { class_type: string; field: string; value?: unknown; title?: string }[];
  /** the graph itself is wrong: nothing can be saved until these are fixed */
  problems: string[];
  can_save?: boolean;
  /** everything read, by level: an error stops it being saved, a warning is
   * worth checking, info is how the graph was read */
  notes?: { level: "error" | "warning" | "info"; text: string }[];
}

/** PUT / DELETE /seriesmith/targets/custom. */
export interface CustomTargetResult {
  ok?: boolean;
  id?: string;
  path?: string;
  draft?: boolean;
  deleted?: boolean;
  targets?: { id: string; kind: string; label: string; short: string; draft: boolean; workflow: string; path: string }[];
}

/**
 * Phase 11: the graph a target renders with (GET /seriesmith/targets `graph`).
 * `source` is where it comes from, in the order a render resolves it: the
 * target's env var, a workflow saved in the running ComfyUI, $COMFYUI_PATH's
 * workflows folder, then the repo's own copy.
 */
export interface TargetGraph {
  /** the workflow file name the binding looks up */
  name: string;
  source: "env" | "comfy" | "saved" | "repo" | "none";
  /** the path, or the saved workflow it was read from */
  where: string;
  /** the environment variable that would win, and whether it is set */
  env?: string;
  env_set?: boolean;
  /** a copy is saved in this ComfyUI under `name` (it may not be the one in force) */
  installed: boolean;
  /** the graph in force isn't the repo's copy, ignoring what a job patches */
  differs: boolean;
  /** the repo copy's path, "" when the target ships none */
  repo?: string;
  /** why a candidate couldn't be read (the rest still applies) */
  error?: string;
}

// ---------------------------------------------------------------------------
// readiness (API.md "Readiness, requirement tiers, and the episode target")
// ---------------------------------------------------------------------------

/** required: the target can't render without it; accelerator: renders fall back
 * to the slower `base` preset; optional: one feature is off. */
export type RequirementTier = "required" | "accelerator" | "optional";

export type ReadinessStatus = "ready" | "degraded" | "not_ready" | "unknown";

export interface MissingFile {
  param: string;
  tier: RequirementTier;
  /** the file the preset names */
  want: string;
  family?: string | null;
  /** the ComfyUI models folder it belongs in, e.g. "loras" */
  folder?: string | null;
  /** only from a trustworthy record; never guessed */
  url?: string | null;
  /** what to search for when there's no URL */
  source?: string | null;
  /** an optional file: the feature it enables (the same words as its `features_off` entry) */
  feature?: string | null;
  /** the family's label */
  label?: string | null;
  /** which passes miss the file */
  passes?: Pass[];
}


/**
 * What one model param resolved to when the take was queued (targets/__init__.py).
 * A file name — except the `loras` param, whose want/using are LISTS of names.
 */
export interface Resolution {
  want?: string | string[] | null;
  using?: string | string[] | null;
  how: "exact" | "family" | "base" | "off" | string;
}

export interface Readiness {
  status: ReadinessStatus;
  missing: MissingFile[];
  resolved: Record<string, Resolution>;
  features_off: string[];
  nodes_missing: string[];
}

/** POST / DELETE /seriesmith/workflow/install (Phase 11). */
export interface WorkflowInstallResult {
  ok?: boolean;
  target?: string;
  /** POST: the name it was saved as */
  installed?: string;
  /** POST: whether that name is the one renders pick up */
  renders?: boolean;
  /** DELETE: whether a saved copy was there */
  deleted?: boolean;
  name?: string;
  graph?: TargetGraph;
}

/** One file of GET /seriesmith/models: how it stands against the param's family. */
export interface ModelFile {
  name: string;
  /** named like the family, its header says so, or anything else */
  match: "name" | "fingerprint" | "other";
  /** its header says another family: the server skips the shot unless allow_model_mismatch */
  mismatch: boolean;
  family: string | null;
  label: string;
  confidence: "metadata" | "tensors" | "name" | "unknown";
  detail: string;
  base?: string;
}

/** GET /seriesmith/models?target=…&param=… */
export interface ModelList {
  target: string;
  param: string;
  family: string;
  label: string;
  patterns: string[];
  /** false: the server can't read model files, so only names were checked */
  fingerprint: boolean;
  /** where these files are: "local" (this machine's ComfyUI) or a Comfy Cloud
   * backend's name ("cloud": its own files, and any the account imported) */
  backend?: string;
  files: ModelFile[];
}

/** A look preset (GET /seriesmith/presets): a series' look line, with its sample picture when made */
export interface LookPreset { id: string; label: string; group: string; text: string; image?: string;
  /** the preset in the look builder's rows ({row: option id}) */
  parts?: Record<string, string>;
  /** one of yours (kept beside this machine's settings), group "yours" */
  own?: boolean;
  /** one of yours: its picture is being rendered, or why the last render failed */
  rendering?: boolean; picture_error?: string }
/** A row of the look builder (medium, camera, lens, film, light, grade): each option a clause of the look line */
export interface LookBuilderRow {
  id: string; label: string;
  /** folded away under a drawn medium (camera, lens, film) */
  camera_row: boolean;
  options: { id: string; label: string; clause: string; drawn?: boolean; image?: string }[];
}
/** "place": a location plate's wording; "subject": a character's view or a prop's */
export type RelightWording = "place" | "subject";
/** A relight preset: the instruction per wording, and each wording's sample picture when made */
export interface RelightPreset {
  id: string; label: string; group: string; for: RelightWording[];
  texts: Partial<Record<RelightWording, string>>; images: Partial<Record<RelightWording, string>>;
  /** one of yours (kept beside this machine's settings), group "yours" */
  own?: boolean;
  /** one of yours: its picture is being rendered, or why the last render failed */
  rendering?: boolean; picture_error?: string;
}

/** Where one of your presets' pictures comes from (POST /seriesmith/presets/own/picture) */
export type PresetPictureSource =
  | { ep: string; ref: string; view?: string | null; take?: number | null }
  | { ep: string; pass: Pass; shot: string; take: number; time: number };

/** POST /seriesmith/presets/own: one of your own looks or relights, kept for every show */
export interface OwnPresetRequest {
  kind: "look" | "relight";
  label: string;
  /** replace that one of yours */
  id?: string | null;
  text?: string;
  parts?: Record<string, string>;
  place?: string;
  subject?: string;
  /** its tile: a ref's take (or its live picture) */
  picture?: { ep: string; ref: string; view?: string | null; take?: number | null } | null;
}
/** A framing preset: a shot's `size:` (its id), how much the frame holds, its sample picture when made */
export interface FramingPreset { id: string; label: string; group: string; hint: string; image?: string }
/** A camera-move preset: how a shot's `camera:` line starts, its sample clip (mp4) when made */
export interface CameraPreset { id: string; label: string; group: string; move: string; image?: string }
export interface PresetList {
  relight: RelightPreset[]; look: LookPreset[]; framing: FramingPreset[]; camera: CameraPreset[];
  look_builder: LookBuilderRow[];
}

export interface TargetList {
  targets: Target[];
  default: Partial<Record<TargetKind, string>>;
}

// ---------------------------------------------------------------------------
// Phase 9a: the script and series config windows, promote
// ---------------------------------------------------------------------------

/** Which authored file: the episode's epNN.md, or its series.json. */
export type SourceFile = "script" | "series";

/** A shot's line span in the script (1-based, inclusive). */
export interface SourceShotSpan {
  id: string;
  line: number;
  end_line: number;
}

/** GET /seriesmith/source */
export interface SourceDoc {
  file: SourceFile;
  /** relative to the episode (`../series.json` for a parent-folder series config) */
  path: string;
  text: string;
  /** sha1 of the bytes on disk */
  hash: string;
  mtime: number;
  /** script only; empty if it doesn't parse */
  shots: SourceShotSpan[];
}

/** GET /seriesmith/source?…&hash_only=1 */
export interface SourceHash {
  file: SourceFile;
  hash: string;
  mtime: number;
}

/** One error or warning of a check, 1-based line (and col) into the checked text.
 * As built: `file` is "script" | "series"; `line` is null for a series config
 * message that names no key; `col` only for a JSON syntax error. */
export interface SourceMessage {
  /** which file it's in (a check can report on the other file too) */
  file: string;
  line: number | null;
  col?: number;
  message: string;
}

/** POST /seriesmith/source/check (and `check` of PUT /seriesmith/source) */
/**
 * P10: an issue noted while watching a pass — what is wrong with a shot **as it
 * was rendered**. The snapshot fields are taken when the note is made and never
 * updated: the note is about that render, so editing the script afterwards must
 * not rewrite it.
 */
export interface Issue {
  id: string;
  shot: string;
  pass: Pass;
  /** the take it is about (null: nothing had rendered yet) */
  take: number | null;
  note: string;
  when: string;
  /** the shot's story hash when the note was made */
  shot_hash?: string;
  target?: string | null;
  /** the script's lines for that shot, as they were */
  script?: string;
  /** what the pipeline compiled from them */
  prompt?: string;
  seed?: Seed | null;
  refs?: { role?: string | null; id?: string | null; path?: string | null }[];
  /** the rendered file, relative to the episode */
  take_file?: string | null;
  /**
   * The shot has been rebuilt or rendered again since: computed on every read,
   * never stored. The list fades these and **Clear addressed** empties them —
   * nothing is dropped for you.
   */
  addressed?: boolean;
}

export interface IssueAddRequest {
  ep: string;
  pass: Pass;
  shot: string;
  note: string;
  take?: number | null;
}

export interface SourceCheck {
  ok: boolean;
  errors: SourceMessage[];
  warnings: SourceMessage[];
  shots: SourceShotSpan[];
}

export interface SourceSaveRequest {
  ep: string;
  file: SourceFile;
  text: string;
  base_hash: string;
  rebuild: boolean;
}

/** PUT /seriesmith/source */
export interface SourceSaveResult {
  hash: string;
  check: SourceCheck;
  build: BuildResult | null;
}

/** POST /seriesmith/shot/preview: a shot as the form has it, compiled in memory. */
export interface ShotPreview {
  ok: boolean;
  /** when !ok: why (the message `check` gives), and the script line if known */
  error?: string;
  line?: number | null;
  shot?: string;
  target?: string;
  target_label?: string;
  /** what the model is told */
  prompt?: string;
  negative?: string | null;
  frames?: number | null;
  fps?: number;
  seconds?: number | null;
  width?: number | null;
  height?: number | null;
  audio_policy?: string | null;
  subjects?: string[];
  background?: string | null;
  /** the dialogue's pace against the shot's length (null: no dialogue) */
  pacing?: { held: number; syllables: number; rate: number; fits: number; verdict: "ok" | "tight" | "CRAMMED";
             pace: string; pace_rate: number; ceiling: number } | null;
  warnings?: string[];
}

/** The body of a 409 from PUT /seriesmith/source or POST /seriesmith/promote. */
export interface SourceConflictBody {
  error: string;
  /** as built: which file changed */
  file?: SourceFile;
  hash: string;
  text: string;
}

export type PromoteScope = "shot" | "episode" | "ref";

export interface PromoteItem {
  id: string;
  scope: PromoteScope;
  shot?: string;
  ref?: string;
  view?: string | null;
  field: string;
  value: unknown;
  dest: SourceFile;
  line?: number;
  summary: string;
}

export interface PromoteLeft {
  scope: PromoteScope;
  shot?: string;
  ref?: string;
  view?: string | null;
  /** as built: a per-pass field left in one pass (a prompt, a negative, model_low) */
  pass?: Pass | null;
  field: string;
  reason: string;
}

export interface PromoteHashes {
  script: string;
  series: string;
}

/** GET /seriesmith/promote */
export interface PromotePlan {
  items: PromoteItem[];
  left: PromoteLeft[];
  diffs: { script: string; series: string };
  hashes: PromoteHashes;
}

/** POST /seriesmith/promote */
export interface PromoteResult {
  promoted: string[];
  left: PromoteLeft[];
  hashes: PromoteHashes;
  build: BuildResult | null;
}

// ---------------------------------------------------------------------------
// the episode's mix (docs/SOUND.md; seriesmith/mix.py's docstring has the shape)
// ---------------------------------------------------------------------------

/** What a track is (docs/SOUND.md phase 6): its default fader and duck depth, what a region
 * reaches, whether it joins the M&E. The four default tracks are each their own kind. */
export type TrackKind = "dialogue" | "effects" | "ambience" | "music";
/** A track's id: one of the defaults ("dialogue", "effects", "ambience", "music") or one of the mix's own. */
export type MixTrack = string;

/** A track in the mix's own list (`track_list`): its id, kind and name (none: the default's, or its id). */
export interface MixTrackDef {
  id: MixTrack;
  kind: TrackKind;
  label?: string;
}

/** A shot and a frame of its take at the cut's rate, counted from the take's
 * first frame before any trim: a trim or a reorder moves it with its shot. */
export interface Anchor {
  shot: string;
  frame: number;
}

/** A track's fader (dB), mute, solo, and how far it dips under speech (not dialogue). */
export interface MixTrackSettings {
  gain_db?: number;
  mute?: boolean;
  solo?: boolean;
  duck_db?: number;
  /** the dialogue track only: each clip plays its take's voice stem (voices.py), the model's
   * music and room tone split off */
  voices_only?: boolean;
}

/** A volume breakpoint: dB at an anchor (linear between, held beyond the ends). */
export interface MixPoint {
  at: Anchor;
  db: number;
}

/** A file on a track: plays `path` from `offset` seconds into it, from `in` to
 * `out` (none: until the file ends). Defaults are left out, as mix.json keeps it. */
export interface MixItem {
  id: string;
  track: MixTrack;
  /** relative to the episode, "/" separators */
  path: string;
  in: Anchor;
  out?: Anchor | null;
  offset?: number;
  gain_db?: number;
  /** frames */
  fade_in?: number;
  fade_out?: number;
  points?: MixPoint[];
  loop?: boolean;
  label?: string;
  /** silent where it is: left out of the render, its stem and the loudness, and of Play all (absent: plays) */
  mute?: boolean;
}

/** What a hit asks of the music: a sting or downbeat on the frame (accent, the
 * default), the peak arriving there, the music cutting out or thinning, a turn. */
export type HitKind = "accent" | "arrive" | "drop" | "turn";

/** A named anchor ("the door bursts") a cue can land on. */
export interface MixHit {
  id: string;
  name?: string;
  at: Anchor;
  /** absent: accent */
  kind?: HitKind;
  /** only false is stored: it may miss when one tempo can't land every hit */
  must?: boolean;
}

/** A stretch that changes the ducking (score forward, a deeper dip). */
export interface MixRegion {
  from: Anchor;
  to: Anchor;
  music_duck_db?: number;
  ambience_duck_db?: number;
  dialogue_db?: number;
}

/** One pass's mix, as mix.json holds it ({} for none). */
export interface Mix {
  tracks?: Partial<Record<MixTrack, MixTrackSettings>>;
  items?: MixItem[];
  hits?: MixHit[];
  regions?: MixRegion[];
  duck?: { threshold_db?: number; attack_ms?: number; release_ms?: number };
  loudness?: { target_lufs?: number; true_peak_db?: number };
  /** what you changed of a place's ambience bed (docs/SOUND.md phase 3): its level, mute */
  beds?: Record<string, MixBedSettings>;
  /** a shot's picked effects take (docs/SOUND.md phase 4), its level, mute, kept though stale */
  fx?: Record<string, MixFxSettings>;
  /** the mix's own tracks in lane order (docs/SOUND.md phase 6); none: the four defaults */
  track_list?: MixTrackDef[];
  /** a shot's own voices only, over the dialogue track's (false: its whole sound) */
  voices?: Record<string, { voices_only: boolean }>;
}

/** What a clip's take's voice stem is (voices.py). */
export type VoiceState = "ok" | "missing" | "stale" | "queued" | "failed" | "sourced" | "silent";

/** A cut shot's voice stem and what voices only does to it (GET /seriesmith/mix `voices.shots`). */
export interface MixVoice {
  shot: string;
  pass: Pass;
  take: number | null;
  /** the stem, relative to the episode (null: no take) */
  path: string | null;
  state: VoiceState;
  why: string | null;
  /** the shot's, the track's under it */
  voices_only: boolean;
  /** the shot's own setting (null: the track's) */
  override: boolean | null;
  /** what the Dialogue track plays for it */
  plays: "voice" | "whole" | "silence";
  /** the script gives it a line */
  lines: boolean;
  measured?: { whole_rms_db?: number | null; voice_rms_db?: number | null; rest_rms_db?: number | null } | null;
  seconds?: number | null;
}

/** GET /seriesmith/mix `voices`: the Dialogue track's voices only. */
export interface MixVoices {
  /** the track's setting */
  voices_only: boolean;
  shots: MixVoice[];
  /** of the cut's shots that can be split, how many are, and how many are queued */
  split: number;
  of: number;
  queued: number;
}

export interface MixFxSettings {
  take: number;
  gain_db?: number;
  mute?: boolean;
  /** play it though the cut's picture changed under it */
  keep_stale?: boolean;
  /** frames silent from the clip's head and tail: the block keeps its place and length */
  trim_in?: number;
  trim_out?: number;
  /** frames, at the kept span's edges */
  fade_in?: number;
  fade_out?: number;
  /** its volume points (dB on its gain at anchors on the shot), as an item's */
  points?: MixPoint[];
}

/** A shot's picked effects laid at its clip (GET /seriesmith/mix `fx`: worked out from the
 * cut and the mix's `fx`, never stored as an item; fx.laid). */
export interface MixFx {
  shot: string;
  take: number;
  /** the foley target it was made on */
  model: string;
  /** its wav, relative to the episode */
  path: string;
  exists: boolean;
  /** the clip's first frame of the take, and the frame after its last */
  in: Anchor;
  out: Anchor;
  /** cut seconds, as the server laid it */
  start: number;
  end: number;
  /** seconds into the file at `start` (the clip's trim) */
  offset: number;
  gain_db: number;
  mute: boolean;
  keep_stale: boolean;
  /** why it no longer matches the cut's picture (null: it does) */
  stale: string | null;
  heard: boolean;
}

/** One effects take's sidecar (GET /seriesmith/fx). */
export interface FxTake {
  take: number;
  status: "queued" | "ok" | "failed";
  target: string;
  seed?: number;
  prompt?: string;
  text?: string;
  error?: string;
  path: string;
  picked: boolean;
  stale: string | null;
  source?: { pass: Pass; take: number };
  measured?: { seconds: number; peak_db: number | null; rms_db: number | null };
  created?: string;
}

/** GET /seriesmith/fx/shots: a shot with effects takes in the pass, from their sidecars. */
export interface FxShotSummary {
  shot: string;
  takes: number;
  ok: number;
  queued: number;
  failed: number;
  /** the take the pass's mix plays (null: none picked) */
  picked: number | null;
}

/** GET /seriesmith/fx: one shot's effects takes, newest first. */
export interface FxShot {
  shot: string;
  pass: Pass;
  cut_take: { pass: Pass; take: number } | null;
  picked: number | null;
  settings: Partial<MixFxSettings>;
  /** the words a new take is made from: the shot's sound: line, else its action */
  text: string;
  text_from: "sound" | "action" | "";
  takes: FxTake[];
}

export interface MixBedSettings {
  gain_db?: number;
  mute?: boolean;
}

/** A place's ambience bed under a run of the cut's shots (GET /seriesmith/mix `beds`: worked
 * out from the cut and the series config, never stored; ambience.laid). */
export interface MixBed {
  /** the place's id (its location, or the variant with its own ambience) */
  place: string;
  label: string;
  /** the bed's file, relative to the episode */
  path: string;
  /** made yet */
  exists: boolean;
  words: string;
  shots: string[];
  /** from the first shot's first frame played to the frame after the last's */
  in: Anchor;
  out: Anchor;
  /** cut seconds, as the server laid it */
  start: number;
  end: number;
  gain_db: number;
  mute: boolean;
}

/** GET /seriesmith/ambience: a place's bed as a ref (`ambience:<place>`), without its takes. */
export interface AmbienceBed {
  ref: string;
  place: string;
  name: string;
  words: string;
  path: string | null;
  exists: boolean;
  /** the locations whose shots play over it */
  locations: string[];
  used_by: string[];
  takes: number;
  ok: number;
  queued: number;
  picked: number | null;
  can_generate: boolean;
  why_not: string | null;
  target: string | null;
}

/** A cut shot's place (GET /seriesmith/mix `places`): its bed's place, else its location's master. */
export interface MixPlace {
  place: string;
  name: string;
  /** the place has a bed (words or a file) */
  bed: boolean;
}

/** GET /seriesmith/mix */
export interface MixResult {
  mix: Mix;
  /** the places' ambience beds under the cut (none: the server has none to lay) */
  beds?: MixBed[];
  /** the shots' picked effects at their clips */
  fx?: MixFx[];
  /** the Dialogue track's voices only: each cut shot's voice stem (none: an older server) */
  voices?: MixVoices;
  /** each cut shot's place: the place whose bed it plays over, or would (none: an older server) */
  places?: Record<string, MixPlace>;
  /** the series config's `sound` defaults the mix sits on */
  series: { tracks?: Partial<Record<MixTrack, MixTrackSettings>>; loudness?: Mix["loudness"] };
  /** the mix's tracks in lane order, each named (the server's; the editor works it out from `mix` too) */
  track_list?: (MixTrackDef & { label: string })[];
  defaults: {
    tracks: MixTrack[];
    /** the default tracks' names */
    labels?: Record<TrackKind, string>;
    /** each track's fader when neither the mix nor the series config sets it (music -12) */
    gain_db: Record<MixTrack, number>;
    duck_db: Partial<Record<MixTrack, number>>;
    duck: { threshold_db: number; attack_ms: number; release_ms: number };
    loudness: { target_lufs: number; true_peak_db: number };
  };
}

// ---------------------------------------------------------------------------
// music cues (docs/SOUND.md "The cue window"; seriesmith/cue.py's docstring has the shape)
// ---------------------------------------------------------------------------

/** A stretch of a cue: its bars (omitted: the plan fills them), its words, its
 * energy 1-5 at its start and end, a song's lyrics. */
export interface CueSection {
  name: string;
  bars?: number;
  words?: string;
  from?: number;
  to?: number;
  lyrics?: string;
}

/** A point of a cue's arc: an energy (1-5) at an anchor. */
export interface CueArcPoint {
  at: Anchor;
  level: number;
}

/** A cue's spec (`<ep>/sound/<cue>/spec.json`), defaults left out. */
export type CueKind = "score" | "song";

/** A cue's theme: another cue's take in the episode (`take`; without one, whichever take that cue
 * has in the pass's mix, else its best finished one), a file relative to it (a gallery item, a
 * recording), or one of the series config's `sound.themes` by name; `strength`: where a model that
 * renders from its sound starts (0.5 to 0.99; absent: the model's own, 0.86 for Stable Audio 3). */
export type CueTheme = ({ cue: string; take?: number } | { file: string } | { theme: string }) & { strength?: number };

/** One of the series config's themes, as GET /seriesmith/cue offers them (cue.theme_list). */
export interface SeriesTheme {
  name: string;
  /** "porch (ep01 m03 t02)": the take or file it is */
  label: string;
  role?: "show" | "story" | "runner" | null;
  words?: string | null;
  for?: string[] | null;
  /** why it doesn't read, or isn't there to render from (null: fine) */
  error?: string | null;
}

/** A first-pass score's cue (POST /seriesmith/cue/draft: scoredraft.draft): a cue, a sting, a sitcom's
 * bumper or a theme marked by hand (`// theme:`), its sections (a beat each) and hits; `spec` is what
 * would be written (absent with `skip`: a cue of the episode's own plays there). */
export interface DraftCue {
  kind: "cue" | "sting" | "bumper" | "mark";
  label: string;
  id?: string;
  t0: number;
  t1: number;
  /** "story" (the episode's own melody, the take of the cue that makes it), a series theme's name, or none */
  theme: string | null;
  makes?: "story" | null;
  sections: { name: string; words: string; from: number; to: number; seconds: number }[];
  hits: { kind: "turn" | "arrive" | "drop"; shot: string; name: string }[];
  spec?: CueSpec;
  skip?: string;
  /** "trimmed around d01": cut to the stretch a kept cue leaves free */
  trim?: string;
}

export interface ScoreDraft {
  /** the structure whose Music table it read (null: none) */
  structure: string | null;
  beats: { beat: string | null; from: string; music: string; t0: number; t1: number; shot: string }[];
  cues: DraftCue[];
  /** what the rules found and left to a person: music in the scene, a montage, a card, a flashback */
  flags: { kind: string; shot: string; text: string }[];
  notes: string[];
  pass: Pass;
  /** shots with no take yet, timed at their shotlist length */
  missing: string[];
  voices_only: boolean;
  /** the earlier draft's cues (dNN) in the episode: writing replaces them only when asked */
  drafted: string[];
  /** earlier draft cues kept: a series theme's, and (unless `rendered`) those with a finished take */
  kept: string[];
  /** whether the earlier draft's rendered cues are replaced too */
  rendered: boolean;
  /** whether the script has its own beat lines (none: drafted flat, unless a structure is laid out) */
  marked: boolean;
  /** the structure laid over the cut (asked for, the script having no beat lines): `beats` are where it put them */
  laid: string | null;
  /** every structure with a Music table, to lay one out */
  structures: { id: string; name: string }[];
}

export interface ScoreDraftResult {
  draft: ScoreDraft;
  text: string;
  written: { cues: string[]; hits: number; removed: string[]; voices_only: boolean; marked?: boolean } | null;
}

/** How the plan's model hears the cue's theme (cue.theme_for): "plan" (YuE2 sings a YuE2 take's own
 * plan), "transcribe" (YuE2 sings SheetSage2's transcription), "timbre" (ACE-Step), "audio" (Stable
 * Audio 3 renders from its sound, fitted to the cue, at `strength`), or null and a warning (it isn't
 * there, or the model takes none: rendered without it). */
export interface CuePlanTheme {
  spec: CueTheme;
  label: string;
  use: "plan" | "transcribe" | "timbre" | "audio" | null;
  /** "audio": where the schedule starts */
  strength?: number | null;
  /** a theme take's tempo, as it was measured (null: a file that doesn't say its own) */
  grid?: { bpm: number; downbeat: number; beats: number } | null;
  warning: string | null;
  /** a theme that follows another cue's pick: how its take was found ("mix": the one in the pass's
   * mix; "best": none there, its best finished take); `label` names that take. null otherwise */
  from?: "mix" | "best" | null;
}

/** A section of a song's plan (YuE2's ABC, read by core/abc.py) where a take puts it. */
export interface CueSongSection {
  name: string;
  /** seconds into the take (at the cue's tempo) */
  start: number;
  seconds: number;
  /** seconds from the cue's in point (negative: before it) */
  at: number;
  /** the plan's own bars (its meter's) and beats */
  bars: number;
  beats: number;
  /** its length in the cue's bars */
  cue_bars: number;
}

/** A song take's plan (tNN.abc) read against what came back. */
export interface CueSong {
  /** tNN.abc, relative to the episode */
  file: string;
  source: "planned" | "theme plan" | "theme transcribed";
  /** the plan's own tempo, before the cue's was set (null: it had none) */
  tempo_written: number | null;
  tempo: number | null;
  meter: string;
  key: string;
  bars: number;
  /** its bars at the tempo asked, against the take as it came */
  plan_seconds: number;
  raw_seconds: number | null;
  short: number | null;
  /** the plan's first sung note, seconds into the take */
  first_note: number | null;
  sections: CueSongSection[];
}

export interface CueSpec {
  id: string;
  /** score (underscore, instrumental; the default) or a song (sung: its sections' lyrics) */
  kind?: CueKind;
  label?: string;
  /** a music target (absent: the series' or the default) */
  model?: string;
  in: Anchor;
  out: Anchor;
  style?: string;
  bpm?: number;
  fixed_tempo?: boolean;
  /** beats/unit: "3/4", "6/8", "7/8", "12/8" (absent: 4/4; a bare number, the older form, is N/4) */
  meter?: string | number;
  key?: string;
  /** seconds after its out point (absent: 2) */
  tail?: number;
  sections?: CueSection[];
  arc?: CueArcPoint[];
  /** the orchestration grid: {family: [level per bar]}, 0 off, 1 under, 2 present, 3 lead
   * (trailing offs and a family off throughout dropped); folded into each section's words */
  orchestra?: Record<string, number[]>;
  /** the mix's hits it lands (absent: every hit in its span) */
  hits?: string[] | null;
  /** its theme (the leitmotif): another cue's take, or a sound file relative to the episode */
  theme?: CueTheme | null;
  /** takes a render makes (absent: its model's preset's) */
  takes?: number | null;
  seed?: number | null;
}

/** A section of a cue preset: its share of the cue's bars, its words and energies, who plays ({family: 0-3}). */
export interface CuePresetSection {
  name: string;
  share: number;
  words?: string;
  from: number;
  to: number;
  orchestra?: Record<string, number>;
}

/** GET /seriesmith/presets?kind=cue: a worked example of a cue's fields (seriesmith/presets/cue.json). */
export interface CuePreset {
  id: string;
  label: string;
  /** "Score" or "Song" */
  group: string;
  /** when to use it */
  hint: string;
  fields: { kind: CueKind; style: string; bpm: number; meter?: string; key?: string; shape: CuePresetSection[] };
}

/** GET /seriesmith/cues: one cue. */
export interface CueSummary {
  spec: CueSpec;
  takes: number;
  ok: number;
  /** the passes whose mix it's in */
  placed: Pass[];
  /** with `pass` asked (GET /seriesmith/cues?pass=): the cue planned against that pass's cut */
  bpm?: number | null;
  /** the take its item in the pass's mix plays (null: none) */
  in_mix?: number | null;
  /** what has moved under that take since it was rendered ([]: nothing, or none in the mix) */
  stale?: string[];
  /** the finished takes something has moved under */
  stale_takes?: number[];
  /** its anchors aren't in the cut (null: planned) */
  plan_error?: string | null;
}

/** A tempo the cue's hits could be fitted to (core/score.alternatives). */
export interface CueTempo {
  bpm: number;
  preroll: number;
  /** frames: the must-hits' worst error there */
  worst_must: number;
  /** frames: every hit's error added up */
  total: number;
}

/** A hit of the cue's plan: seconds from its in point. */
export interface CueHit {
  id: string;
  name: string;
  kind: HitKind;
  must: boolean;
  t: number;
  /** where it is in the cut (the mix's anchor) */
  at?: Anchor;
  /** a drop on its out point: the music's end, neither fitted to a bar line nor measured */
  ends?: boolean;
}

/** What a cue would be asked now, against the pass's cut. */
export interface CuePlan {
  target: string;
  fps: number;
  /** seconds from its in point to its out point */
  span: number;
  hits: CueHit[];
  /** the cue's exact tempo, the whole bpm the model is asked, the stretch
   * between them, each hit's distance to its line (frames), the worst must-hit's */
  fit: { bpm: number; ask_bpm: number; stretch: number; errors: (number | null)[]; worst_must: number };
  /** the best few tempos within 8 % of the asked one, best first (the fit's first unless fixed) */
  alternatives?: CueTempo[];
  /** the series config's score direction (`sound.score`; "" when none), before the cue's style in the prompt */
  direction?: string;
  bars: number;
  /** seconds a bar */
  bar: number;
  /** seconds before the in point where the first bar starts */
  preroll: number;
  seconds: number;
  ask_seconds: number;
  /** every section with its bars and levels filled */
  sections: (CueSection & { bars: number; from: number; to: number })[];
  /** an energy per bar */
  arc: number[];
  prompt: { prompt: string; negative: string | null; values: Record<string, unknown> };
  /** the script's music: notes of the shots it plays over (folded into the prompt) */
  notes?: { shot: string; music: string }[];
  /** how its model hears the cue's theme (absent: it has none) */
  theme?: CuePlanTheme;
  /** what it will render without, in words (a theme it can't take, or that isn't there) */
  warnings?: string[];
  /** why it can't render (a YuE2 song with no lyrics) */
  blocked?: string;
  /** a theme's plan, known before it renders (YuE2 singing a YuE2 take's plan) */
  song?: { source: string; bars: number; meter: string; sections: CueSongSection[] };
}

/** A take, once back, measured against the plan. */
export interface CueMeasured {
  bpm_heard: number | null;
  /** the heard tempo was believed (else the plan's stretch was used) */
  tempo_heard: boolean;
  stretch: number;
  /** seconds into the wav of its first bar line */
  downbeat: number;
  /** seconds into the wav of the cue's in point */
  offset: number;
  /** frames, one per hit of the plan (null: nothing in the music there) */
  hit_errors: (number | null)[];
  worst_must: number;
  /** dB per bar */
  levels: number[];
  shape_error: number | null;
  /** lower is better */
  score: number;
  /** a take rendered from a theme, with SheetSage2: how much of the theme's melody it kept, 0..1 */
  melody?: number;
  /** `melody` at least 0.3 (under it the theme is lost; a take with none keeps ~0.2) */
  on_theme?: boolean;
}

/** A take's sidecar (tNN.json) with its number. */
export interface CueTake {
  take: number;
  status: "queued" | "ok" | "failed" | (string & {});
  seed?: number;
  target?: string;
  pass?: Pass;
  /** relative to the episode: tNN.wav */
  file?: string;
  error?: string;
  measured?: CueMeasured;
  /** the pass whose mix it's in, once picked */
  placed?: Pass;
  /** what has moved in the cut since it was rendered ([] or absent: nothing) */
  stale?: string[];
  /** a finished take's length (its wav; a YuE2 song can run past the cue's grid); null or absent: not known */
  seconds?: number | null;
  /** a comp (POST /seriesmith/cue/comp): take `base` with the cue's bars [a, b) from take `from` */
  comp?: { base: number; from: number; bars: [number, number] };
  /** a repaint (POST /seriesmith/cue/repaint): take `from` with the cue's bars [a, b) made again
   * (`codes`: the seed its music was written from; `fresh`: new music there; `span`: the bars in
   * seconds of the take's file) */
  repaint?: { from: number; bars: [number, number]; codes?: number; fresh?: boolean; span?: [number, number] };
  /** a repaint's bars against the take's beat: of `beats` beats, the onsets within 40 ms, in the new bars and the take's */
  repaint_check?: { beats: number; on: number; on_before: number; median_ms: number | null };
  /** a song's plan (YuE2): its sections against the cue, its length against the take's */
  song?: CueSong;
  /** the theme it was rendered with, and how its model heard it */
  theme?: { label: string; use: CuePlanTheme["use"]; from?: "mix" | "best"; strength?: number;
             staged?: { stretch: number; bars: number; seconds: number } };
  finished?: string;
  created?: string;
}

/** GET /seriesmith/cue */
export interface CueResult {
  spec: CueSpec;
  plan: CuePlan | null;
  plan_error: string | null;
  /** best first */
  takes: CueTake[];
  /** the series config's themes, to pick from (absent from older servers) */
  themes?: SeriesTheme[];
}
