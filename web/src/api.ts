// The typed client for docs/API.md: one function per route. The same `Api`
// interface is implemented by the mock (src/mock/) for the dev page.
//
// What the contract still leaves open (the UI works around each one):
//  - TODO(contract): a placeholder cut entry's take lives in the other pass;
//    episode_status gives its number but not its thumb/strip/mp4, so the UI
//    loads the other pass's status to draw it.
//  - TODO(contract): there is no prompt override per target: a retargeted
//    shot's per-pass prompt override is ignored, so the inspector shows its
//    `effective.prompt` read-only.

import type {
  AlignReady, AlignRequest, AlignResult, AssembleOptions, AssembleResult, BrowseFiles, BrowseResult, BuildResult, CancelResult, ComfyQueue, Config, CutEntry,
  CutFile, CutWhat, DiscardResult, EpisodeStatus, EpisodeSummary, ClipQueueResult, EpisodeTargetResult, EpisodeTemplate, Issue, IssueAddRequest, ModelList, NewEpisodeRequest,
  ImportSeriesRequest, ImportSeriesResult, NewEpisodeResult, OverrideRequest, OverrideResult, Pass,
  PeaksResult, PickRequest, Ref, RefDefaults, RefDiscardRequest, RefGenerateMissingRequest, RefGenerateMissingResult, RefGenerateRequest,
  RefGenerateResult, RefImportRequest, RefKeyframeRequest, RefList, RefMatchResult, RefOverrideInfo, RefOverrideRequest, RefPickRequest, RefPickResult,
  RefTake, RefUploadRequest, RenderRequest, RenderResult, Seed, ShotDetail, TakeRef, TargetKind, TargetList, TrackResult,
  MasterJob, MasterResult, UpscaleOptions, UpscaleRequest, UpscaleResult,
  PostOptions, PostRequest, PostResult,
  CustomTargetResult, Limits, SharedField, Target, TargetProposal, VoiceFromTakeRequest, VoiceFromTakeResult,
  WorkflowFile, WorkflowInstallResult,
  PromoteHashes, PromotePlan, PromoteResult, ShotPreview, SourceCheck, SourceDoc, SourceFile, SourceHash, SourceSaveRequest, SourceSaveResult,
} from "./types";
import { comboChoices } from "./lib/targets";

/** A ref take as the import routes return it. */
export type ImportedTake = RefTake & { view?: string | null };

/** Upload progress: bytes sent so far, and the total (0 when unknown). */
export type UploadProgress = (sent: number, total: number) => void;

/** POST /seriesmith/refs/import (multipart) refuses a file over this (413). */
export const UPLOAD_LIMIT = 64 * 1024 * 1024;

/** Where a frame comes from: a take's frame, or a time into a kept video. */
export type FrameSource =
  | { pass: string; shot: string; take: number; frame: number | "last" }
  | { video: string; time: number };

/** A Router model's proposed target (POST /seriesmith/targets/router-inspect). */
export interface RouterProposal {
  proposal: Record<string, unknown> & { id: string; label: string; router: { model: string; inputs: Record<string, unknown> } };
  /** input -> where it goes in the model's request */
  mapped: Record<string, string>;
  /** fields the model requires that nothing was placed in */
  unplaced: string[];
  warnings: string[];
  /** the proposal's limits, to look over before saving */
  limits?: Limits;
  /** limits section -> the schema fields written for several models at once */
  shared?: Record<string, SharedField[]>;
}

/** One of Router's models (GET /seriesmith/router/models): its kind guessed from its name. */
export interface RouterCatalogModel {
  id: string;
  provider: string;
  model: string;
  kind: "video" | "image" | "other";
  /** its name says text-to-video: seriesmith can't use it for shots */
  text_only: boolean;
  /** the target that already drives it */
  added?: string;
}

/** POST /seriesmith/targets/router-dryrun: a Router target's request for one shot. */
export interface RouterDryRun {
  ok: boolean;
  shot: string;
  why?: string;
  pass?: string;
  model?: string;
  arguments?: Record<string, unknown>;
  routing?: Record<string, unknown>;
  prompt_chars?: { written: number };
}

/** A Seedance draft its shot's final can be made from (GET /seriesmith/drafts). */
export interface DraftItem {
  shot: string;
  take: number;
  thumb: string | null;
  mp4: string | null;
  expires: string;
  expired: boolean;
  /** the shot's final takes, and those made from this draft */
  finals: number;
  made_from_it: number[];
  target: string | null;
}

/** A video kept to take frames from (POST /seriesmith/refs/video). */
export interface KeptVideo {
  /** relative to the episode */
  path: string;
  name: string;
  size: number;
  modified: number;
  copied?: boolean;
  duration?: number | null;
}

export interface Api {
  getConfig(): Promise<Config>;
  putConfig(roots: string[]): Promise<Config>;
  episodes(): Promise<EpisodeSummary[]>;
  episode(ep: string, pass: Pass): Promise<EpisodeStatus>;
  /** P9: `target` answers for a one-off run on that video target -- the size and
   * length it would really produce. Nothing is saved. */
  shot(ep: string, pass: Pass, shot: string, target?: string | null): Promise<ShotDetail>;
  build(ep: string): Promise<BuildResult>;
  /** P5: POST /seriesmith/episode/new — a new episode from a template, in `parent`. */
  newEpisode(req: NewEpisodeRequest): Promise<NewEpisodeResult>;
  /** A frame of a take -- or of a video of your own, at a time -- as a
   * character's or a place's picture (steps 13 and 5). */
  refsFromFrame(req: FrameSource & { ep: string; ref: string;
                       view?: string | null; instruction?: string; target?: string | null; views?: boolean; pick?: boolean }):
    Promise<{ frame: unknown; edits: string[]; step: string | null }>;
  /** A video of your own kept in the show's refs/_videos/ to take frames from:
   * a path on this machine, or a file uploaded from this computer. */
  refsVideo(ep: string, from: { source_path: string } | { file: Blob; name?: string }, onProgress?: UploadProgress): Promise<KeptVideo>;
  /** The videos kept to take frames from, newest first. */
  refsVideos(ep: string): Promise<{ videos: KeptVideo[] }>;
  /** The Seedance drafts the proxy cut uses: what finals can be made from. */
  drafts(ep: string): Promise<{ drafts: DraftItem[] }>;
  /** Simple mode: the Clips project (made the first time). */
  clipsEnsure(root?: string | null): Promise<{ ep: string; made: boolean }>;
  /** Simple mode: a project of its own, `<root>/<Name>/<name>/` (default the first root). */
  clipsNew(title: string, root?: string | null): Promise<{ ep: string }>;
  /** Simple mode: a clip's missing pictures, then its takes. */
  clipQueue(req: { ep: string; shot: string; pass?: Pass; takes?: number; backend?: string | null }): Promise<ClipQueueResult>;
  /** GET /seriesmith/episode/new — what a new episode in `parent` (or its new show folder) starts from. */
  episodeTemplate(parent: string, show?: string | null): Promise<EpisodeTemplate>;
  /** seriesmith: a series config and scripts into episode folders (POST /seriesmith/import) */
  importSeries(req: ImportSeriesRequest): Promise<ImportSeriesResult>;
  /** URL of a file inside the episode (for <img>/<video>); supports Range. */
  fileUrl(ep: string, path: string): string;
  /** A JSON file inside the episode (e.g. a frozen shotlist), seeds as strings. */
  readJson<T = unknown>(ep: string, path: string): Promise<T>;
  render(req: RenderRequest): Promise<RenderResult>;
  cancel(take: TakeRef): Promise<CancelResult>;
  /** POST /seriesmith/discard: move a take's files to `_trash/` (409 while queued). */
  discard(take: TakeRef): Promise<DiscardResult>;
  pick(req: PickRequest): Promise<{ cut: CutFile }>;
  putCut(ep: string, pass: Pass, entries: CutEntry[]): Promise<{ cut: CutFile }>;
  /** Phase 9b: POST /seriesmith/cut/reset: script order and/or zero trims (picks, locks, notes kept). */
  cutReset(ep: string, pass: Pass, what: CutWhat): Promise<{ cut: CutFile }>;
  /** Phase 9b: POST /seriesmith/cut/copy: one pass's order and/or trims onto the other (never picks). */
  cutCopy(ep: string, from: Pass, to: Pass, what: CutWhat): Promise<{ cut: CutFile }>;
  /** Phase 9b: GET /seriesmith/peaks: `bins` peaks (0..255) of a media file over start..end seconds. */
  peaks(ep: string, path: string, bins: number, start?: number | null, end?: number | null): Promise<PeaksResult>;
  /** Phase 9d: POST /seriesmith/audio/import as multipart: a media file from this
   * computer into the episode, to be one clip's audio source. Answers where it
   * landed, relative to the episode. See the contract gap above. */
  uploadClipAudio(req: ClipAudioUploadRequest, onProgress?: UploadProgress): Promise<{ path: string }>;
  putOverride(req: OverrideRequest): Promise<OverrideResult>;
  deleteOverride(ep: string, shot: string, pass?: Pass): Promise<OverrideResult>;
  assemble(ep: string, pass: Pass, partial: boolean, opts?: AssembleOptions): Promise<AssembleResult>;
  /** Phase 13: POST /seriesmith/upscale: queue upscales of final takes (409: this ComfyUI can't). */
  upscale(req: UpscaleRequest): Promise<UpscaleResult>;
  /** Phase 13: GET /seriesmith/upscale/options: pixel models and each target's latent upscale. */
  upscaleOptions(ep?: string | null): Promise<UpscaleOptions>;
  /** Phase 13e: PUT /seriesmith/upscale/recipe: one shot's upscale recipe (the
   * request's fields; null clears it) */
  /** Phase 13e: POST /seriesmith/master: plan, queue the upscales, or assemble the master */
  master(req: { ep: string; pass?: Pass; action: "plan" | "queue" | "assemble" | "prores"; conform?: boolean;
                allow_gaps?: boolean; prores?: boolean; order?: "cut" | "target";
                post?: boolean | "off" | "present" | "recipe" }): Promise<MasterResult>;
  /** POST /seriesmith/post: queue posts (each take's fresh upscale finished: enhance, motion blur) */
  post(req: PostRequest): Promise<PostResult>;
  /** GET /seriesmith/post/options: the tiers, the blur, readiness, the episode's post recipe */
  postOptions(ep?: string | null): Promise<PostOptions>;
  /** DELETE /seriesmith/post: remove a take's post (409 while it is queued) */
  deletePost(ep: string, shot: string, take: number, pass?: Pass): Promise<{ shot: string; take: number; deleted: boolean }>;
  /** GET /seriesmith/master/job: the master being assembled (or the last one), null: none */
  masterJob(ep: string): Promise<{ job: MasterJob | null }>;
  /** Phase 13e: PUT /seriesmith/upscale/keep: mark a take's upscale Keep, or clear it */
  putUpscaleKeep(ep: string, shot: string, take: number, keep: boolean, pass?: Pass): Promise<{ shot: string; take: number; keep: boolean }>;
  putUpscaleRecipe(ep: string, shot: string, recipe: Record<string, unknown> | null): Promise<{ shot: string; recipe: Record<string, unknown> | null; text: string | null }>;
  /** Phase 13: DELETE /seriesmith/upscale: remove a take's upscale (409 while it is queued). */
  deleteUpscale(ep: string, shot: string, take: number, pass?: Pass): Promise<{ shot: string; take: number; deleted: boolean }>;
  /** Folders on the ComfyUI machine; no path = the starting points. `files`
   * lists image or audio files too (for importing a ref). */
  browse(path?: string | null, files?: BrowseFiles | null): Promise<BrowseResult>;
  refs(ep: string): Promise<RefList>;
  /** URL of a ref file (live file or a candidate, `../` beside a parent-folder
   * series config); `version` busts the image cache after a re-pick. */
  refFileUrl(ep: string, path: string, version?: string | null): string;
  refsGenerate(req: RefGenerateRequest): Promise<RefGenerateResult>;
  /** P5: POST /seriesmith/refs/tour, a camera tour of a location (answers once queued) */
  refsTour(req: { ep: string; ref: string; move: string; seconds?: number; count?: number }): Promise<{ queued: { tour: number; comfy_prompt_id: string }[] }>;
  /** P5: POST /seriesmith/refs/copy-take, a finished take copied into another ref as a candidate */
  refsCopyTake(req: { ep: string; ref: string; view?: string | null; take: number; to: string }): Promise<RefTake>;
  /** P5: POST /seriesmith/refs/tour-frame, any moment of a finished tour as a hold */
  refsTourFrame(req: { ep: string; ref: string; tour: number; seconds: number }): Promise<RefTake>;
  /** POST /seriesmith/refs/generate-missing: one candidate for every missing series
   * ref, and every needed keyframe filled (continuity, a still, or the script's file). */
  refsGenerateMissing(req: RefGenerateMissingRequest): Promise<RefGenerateMissingResult>;
  /** PUT /seriesmith/refs/pick. Phase 9c-B: picking a voice may write the series
   * config's `voice_sample` (`series_changed: true` in the answer). */
  refsPick(req: RefPickRequest): Promise<RefPickResult>;
  refsImport(req: RefImportRequest): Promise<ImportedTake>;
  /** POST /seriesmith/refs/import as multipart (drag and drop, a file picker), with
   * upload progress where the transport can report it. */
  refsUpload(req: RefUploadRequest, onProgress?: UploadProgress): Promise<ImportedTake>;
  // ---- P10: a pass's issues (the notepad) ----
  /** GET /seriesmith/issues: what was noted for a pass, each with `addressed`. */
  issues(ep: string, pass?: Pass | null): Promise<Issue[]>;
  /** POST /seriesmith/issues: note what is wrong with a shot as it was rendered. */
  addIssue(req: IssueAddRequest): Promise<Issue>;
  /** DELETE /seriesmith/issues: drop one by id. */
  resolveIssue(ep: string, id: string): Promise<Issue[]>;
  /** DELETE /seriesmith/issues?clear=1: empty a pass, or only what has been addressed. */
  clearIssues(ep: string, pass?: Pass | null, addressedOnly?: boolean): Promise<Issue[]>;
  /** GET /seriesmith/issues/export: the markdown to hand to an assistant. */
  exportIssues(ep: string, pass?: Pass | null): Promise<string>;
  /** P8: POST /seriesmith/refs/match -- which slot each file name means. Read-only,
   * names only (no file bodies), so the table can be shown before anything is sent. */
  refsMatch(ep: string, names: string[]): Promise<RefMatchResult>;
  /** POST /seriesmith/refs/discard: move a candidate to `_trash/`; its pick is cleared.
   * Returns the ref as `refs` lists it. */
  refsDiscard(req: RefDiscardRequest): Promise<Ref>;
  /** A shot's first / last keyframe from a frame of a video take (continuity);
   * returns the keyframe ref as `refs` lists it. */
  refsKeyframe(req: RefKeyframeRequest): Promise<Ref>;
  /** DELETE /seriesmith/refs/pick: unpick a ref (its live file is removed; its takes
   * stay). For a keyframe this is Clear: the shot renders without one. */
  refsUnpick(ep: string, ref: string, view?: string | null): Promise<Ref>;
  /** PUT /seriesmith/refs/defaults: the episode's ref targets (null clears one; a
   * key left out is kept). `voice_target` is an audio target (Phase 9c-B). */
  putRefDefaults(ep: string, fields: RefDefaultFields): Promise<{ defaults: RefDefaults }>;
  /** POST /seriesmith/refs/voice-from-take: a span of a take's sound as a voice candidate. */
  refsVoiceFromTake(req: VoiceFromTakeRequest): Promise<VoiceFromTakeResult>;
  /** Phase 9c-A: GET /seriesmith/align/ready: what align needs, and in which Python. */
  alignReady(): Promise<AlignReady>;
  /** POST /seriesmith/track: attach a recording by its path on the ComfyUI machine. */
  attachTrack(ep: string, sourcePath: string, pass?: Pass): Promise<TrackResult>;
  /** POST /seriesmith/track as multipart: upload a recording from this computer. */
  uploadTrack(req: TrackUploadRequest, onProgress?: UploadProgress): Promise<TrackResult>;
  /** POST /seriesmith/track `{track: null}`: forget the recording (the file stays). */
  clearTrack(ep: string, pass?: Pass): Promise<TrackResult>;
  /** POST /seriesmith/align: run align (a 409's ApiError.data is an AlignMissing). */
  align(req: AlignRequest): Promise<AlignResult>;
  putRefOverride(req: RefOverrideRequest): Promise<{ override: RefOverrideResult }>;
  deleteRefOverride(ep: string, ref: string, view?: string | null): Promise<{ override: RefOverrideResult }>;
  /** ComfyUI's own lists (not seriesmith routes). */
  models(): Promise<string[]>;
  loras(): Promise<string[]>;
  comfyQueue(): Promise<ComfyQueue>;
  /** Phase 7: every target (video and image), for the target picker. A kind
   * filters; `ready: true` asks for each target's `readiness` (`?ready=1`). */
  targets(opts?: TargetKind | TargetsQuery): Promise<TargetList>;
  /** PUT /seriesmith/episode-target: the episode's default target; null clears it
   * (back to series.json's). */
  putEpisodeTarget(ep: string, target: string | null): Promise<EpisodeTargetResult>;
  /** Phase 11: copy a target's repo workflow into ComfyUI's saved workflows, to
   * edit it on the canvas. Its renders use that copy from then on. 409
   * (ApiError) when one of that name is already saved and `overwrite` is off. */
  installWorkflow(target: string, opts?: { name?: string; overwrite?: boolean }): Promise<WorkflowInstallResult>;
  /** Phase 11: delete that saved copy, so the target renders the repo's again. */
  revertWorkflow(target: string, name?: string): Promise<WorkflowInstallResult>;
  /** Phase 12b: the workflows saved in this ComfyUI, for the target wizard. */
  workflows(): Promise<WorkflowFile[]>;
  /** Phase 12b: propose the target.json for one workflow. Read-only. */
  inspectTarget(req: { ep?: string | null; workflow?: string; graph?: unknown; id?: string; label?: string; kind?: "auto" | "video" | "image" }): Promise<TargetProposal>;
  /** A Comfy Router model proposed as a target, from its published schema. */
  routerInspect(req: { model: string; ep?: string | null }): Promise<RouterProposal>;
  /** Phase 12b: save a show's own target (validated first; 400 lists every problem). */
  saveCustomTarget(ep: string, target: Record<string, unknown>, opts?: { scope?: "show" | "user"; limits?: Partial<Limits> | null }): Promise<CustomTargetResult>;
  /** PUT /seriesmith/targets/limits: null puts a built-in back as shipped */
  putTargetLimits(ep: string | null, id: string, limits: Partial<Limits> | null): Promise<{ ok: boolean; id: string; path: string; target: Target }>;
  routerModels(ep: string | null): Promise<{ models: RouterCatalogModel[] }>;
  routerDryRun(req: { ep: string; target: Record<string, unknown> | string; limits?: Partial<Limits> | null; shot?: string | null; pass?: string; ref?: string | null; view?: string | null }): Promise<RouterDryRun>;
  /** Phase 12b: remove one. */
  deleteCustomTarget(ep: string, id: string): Promise<CustomTargetResult>;
  /** Phase 12c: stop being a draft (a probe render proved it), or go back to one. */
  setTargetDraft(ep: string, id: string, draft: boolean): Promise<CustomTargetResult>;
  /** ComfyUI's choices for one combo widget (`/object_info/<class_type>`), or
   * null when the node or widget isn't there. */
  widgetChoices(classType: string, field: string): Promise<string[] | null>;
  /** GET /seriesmith/models: one model param's files, matching the target's family first. */
  modelFiles(target: string, param: string, ep?: string | null): Promise<ModelList>;
  /** Phase 9a: GET /seriesmith/source: the script or the series config, with its hash. */
  source(ep: string, file: SourceFile): Promise<SourceDoc>;
  /** GET /seriesmith/source?…&hash_only=1: has the file changed on disk? */
  sourceHash(ep: string, file: SourceFile): Promise<SourceHash>;
  /** POST /seriesmith/source/check: parse and check `text` without writing it. */
  checkSource(ep: string, file: SourceFile, text: string): Promise<SourceCheck>;
  /** PUT /seriesmith/source: 409 (ApiError.data = {error, hash, text}) when the file
   * changed since `base_hash`; 400 for a series config that isn't JSON. */
  putSource(req: SourceSaveRequest): Promise<SourceSaveResult>;
  /** The shot form's preview: the script with a shot as edited, compiled in memory. */
  previewShot(ep: string, pass: Pass, text: string, shot: string): Promise<ShotPreview>;
  /** GET /seriesmith/promote: what the authored files can take from the overrides. */
  promotePlan(ep: string, shot?: string | null): Promise<PromotePlan>;
  /** POST /seriesmith/promote: 409 when either file changed since the plan; 400 for
   * an id the plan (for the same `shot`) doesn't offer. */
  promote(ep: string, items: string[] | "all", hashes: PromoteHashes, shot?: string | null): Promise<PromoteResult>;
}

/** A ref override route's answer: the (effective) override values, plus `stale`. */
export type RefOverrideResult = NonNullable<RefOverrideInfo["values"]> & { stale?: boolean };

/** PUT /seriesmith/refs/defaults: any of the three; null clears one. */
export interface RefDefaultFields {
  target?: string | null;
  keyframe_target?: string | null;
  voice_target?: string | null;
}

/** Phase 9d: POST /seriesmith/audio/import as multipart/form-data. */
export interface ClipAudioUploadRequest {
  ep: string;
  file: Blob;
  /** the file's name (a File has its own) */
  name?: string;
}

/** POST /seriesmith/track as multipart/form-data (drag and drop, a file picker). */
export interface TrackUploadRequest {
  ep: string;
  file: Blob;
  /** the file's name (a File has its own) */
  name?: string;
  pass?: Pass;
}

export interface TargetsQuery {
  kind?: TargetKind;
  /** ask for readiness (`?ready=1`) */
  ready?: boolean;
  /** the episode open: its show's own targets are listed too */
  ep?: string | null;
}

/** `targets("video")` and `targets({kind, ready})` both work. */
export function targetsQuery(opts?: TargetKind | TargetsQuery): TargetsQuery {
  if (!opts) return {};
  return typeof opts === "string" ? { kind: opts } : opts;
}

export class ApiError extends Error {
  /** `data`: the error response's JSON body, when it had one (a 409's `{hash, text}`). */
  constructor(message: string, public status: number, public route: string, public data?: unknown) {
    super(message);
    this.name = "ApiError";
  }
}

// ---------------------------------------------------------------------------
// seeds
// ---------------------------------------------------------------------------

const SEED_RE = /^\d{1,20}$/;

export function isSeed(s: unknown): s is Seed {
  return typeof s === "string" && SEED_RE.test(s);
}

/** A typed seed from a text field: digits only, trimmed. Throws a readable error. */
export function parseSeed(text: string): Seed {
  const s = text.trim();
  if (!SEED_RE.test(s)) throw new Error(`A seed is a whole number (digits only), not "${text}".`);
  // no leading zeros, but keep "0"
  const t = s.replace(/^0+(?=\d)/, "");
  if (BigInt(t) >= 2n ** 64n) throw new Error("That seed is larger than 64 bits.");
  return t;
}

/**
 * JSON.parse that keeps every `"seed": <integer>` as a string. The routes already
 * send strings, but files read through /seriesmith/file (frozen shotlists, sidecars)
 * are raw JSON, and JSON.parse would round a 63-bit seed to the nearest double.
 * Only matches a real key (a `"seed"` inside a JSON string has escaped quotes).
 */
export function parseJsonSeedSafe<T = unknown>(text: string): T {
  const quoted = text.replace(/("seed"\s*:\s*)(-?\d+)(?=\s*[,}\]\r\n])/g, '$1"$2"');
  return JSON.parse(quoted) as T;
}

// ---------------------------------------------------------------------------
// the HTTP client
// ---------------------------------------------------------------------------

export interface Transport {
  /** fetch a server path such as "/seriesmith/episodes" */
  fetch(path: string, init?: RequestInit): Promise<Response>;
  /** the absolute URL of a server path, for <img src> / <video src> */
  url(path: string): string;
  /** POST a multipart form with upload progress (XMLHttpRequest); without it,
   * uploads go through `fetch` and report no progress. */
  upload?(path: string, form: FormData, onProgress?: UploadProgress): Promise<{ status: number; statusText: string; text: string }>;
}

/** An XMLHttpRequest upload to `url`, for a Transport's `upload`. */
export function xhrUpload(url: string, form: FormData, onProgress?: UploadProgress): Promise<{ status: number; statusText: string; text: string }> {
  return new Promise((resolve, reject) => {
    const x = new XMLHttpRequest();
    x.open("POST", url);
    if (onProgress) x.upload.onprogress = (e) => onProgress(e.loaded, e.lengthComputable ? e.total : 0);
    x.onload = () => resolve({ status: x.status, statusText: x.statusText, text: x.responseText });
    x.onerror = () => reject(new Error("the upload didn't reach ComfyUI"));
    x.onabort = () => reject(new Error("the upload was cancelled"));
    x.send(form);
  });
}

/** The server's JSON (seeds kept as strings), or an ApiError for a failed status. */
function answer<T>(method: string, route: string, status: number, statusText: string, text: string): T {
  let data: unknown = undefined;
  if (text) {
    try {
      data = parseJsonSeedSafe(text);
    } catch {
      data = undefined;
    }
  }
  if (status < 200 || status >= 300) {
    const msg = (data && typeof data === "object" && typeof (data as { error?: unknown }).error === "string")
      ? (data as { error: string }).error
      : status === 413
        ? `The file is too big to upload (the limit is ${UPLOAD_LIMIT / 1024 / 1024} MB).`
        : status === 404 && route.startsWith("/seriesmith/") && data === undefined
          ? `${route} isn't there (HTTP 404). Is the seriesmith server up to date?`
          : `${method} ${route} failed: HTTP ${status} ${statusText}`.trim();
    throw new ApiError(msg, status, route, data);
  }
  if (data === undefined && text) {
    throw new ApiError(`${method} ${route} answered with something that isn't JSON.`, status, route);
  }
  return data as T;
}

function qs(params: Record<string, string | undefined | null>): string {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v != null) u.set(k, v);
  return u.toString();
}

export function createHttpApi(t: Transport): Api {
  async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
    const route = path.split("?")[0];
    let res: Response;
    try {
      res = await t.fetch(path, {
        method,
        headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
        body: body !== undefined ? JSON.stringify(body) : undefined,
      });
    } catch (e) {
      throw new ApiError(`Can't reach ComfyUI (${method} ${route}): ${errText(e)}`, 0, route);
    }
    return answer<T>(method, route, res.status, res.statusText, await res.text());
  }

  const get = <T>(path: string) => call<T>("GET", path);

  /** A multipart POST (the browser sets the boundary): with progress through
   * the transport's `upload` when it has one, else plain `fetch`. */
  async function postForm<T>(path: string, form: FormData, onProgress?: UploadProgress): Promise<T> {
    const route = path.split("?")[0];
    try {
      if (t.upload) {
        const r = await t.upload(path, form, onProgress);
        return answer<T>("POST", route, r.status, r.statusText, r.text);
      }
      const res = await t.fetch(path, { method: "POST", body: form });
      return answer<T>("POST", route, res.status, res.statusText, await res.text());
    } catch (e) {
      if (e instanceof ApiError) throw e;
      throw new ApiError(`Can't reach ComfyUI (POST ${route}): ${errText(e)}`, 0, route);
    }
  }

  return {
    getConfig: () => get("/seriesmith/config"),
    putConfig: (roots) => call("PUT", "/seriesmith/config", { roots }),
    episodes: () => get("/seriesmith/episodes"),
    episode: (ep, pass) => get(`/seriesmith/episode?${qs({ ep, pass })}`),
    shot: (ep, pass, shot, target) => get(`/seriesmith/shot?${qs({ ep, pass, shot, target: target || undefined })}`),
    build: (ep) => call("POST", "/seriesmith/build", { ep }),
    newEpisode: (req) => call("POST", "/seriesmith/episode/new", req),
    refsFromFrame: (req) => call("POST", "/seriesmith/refs/from-frame", req),
    refsVideo: (ep, from, onProgress) => {
      if ("source_path" in from) return call("POST", "/seriesmith/refs/video", { ep, source_path: from.source_path });
      const form = new FormData();
      form.append("ep", ep);
      const name = from.name ?? (typeof File !== "undefined" && from.file instanceof File ? from.file.name : "video.mp4");
      form.append("file", from.file, name);
      return postForm("/seriesmith/refs/video", form, onProgress);
    },
    refsVideos: (ep) => get(`/seriesmith/refs/videos?${qs({ ep })}`),
    drafts: (ep) => get(`/seriesmith/drafts?${qs({ ep })}`),
    clipsEnsure: (root) => call("POST", "/seriesmith/clips/ensure", root ? { root } : {}),
    clipsNew: (title, root) => call("POST", "/seriesmith/clips/new", root ? { title, root } : { title }),
    clipQueue: (req) => call("POST", "/seriesmith/clip/queue", req),
    episodeTemplate: (parent, show) => get(`/seriesmith/episode/new?${qs({ parent, show: show || undefined })}`),
    importSeries: (req) => call("POST", "/seriesmith/import", req),
    fileUrl: (ep, path) => t.url(`/seriesmith/file?${qs({ ep, path })}`),
    readJson: (ep, path) => get(`/seriesmith/file?${qs({ ep, path })}`),
    render: (req) => {
      if (req.seed !== null && !isSeed(req.seed)) {
        return Promise.reject(new Error(`Seed must be a string of digits, got ${String(req.seed)}`));
      }
      return call("POST", "/seriesmith/render", req);
    },
    cancel: (take) => call("POST", "/seriesmith/cancel", take),
    discard: ({ ep, pass, shot, take }) => call("POST", "/seriesmith/discard", { ep, shot, take, pass }),
    pick: (req) => call("PUT", "/seriesmith/pick", req),
    putCut: (ep, pass, entries) => call("PUT", "/seriesmith/cut", { ep, pass, entries }),
    cutReset: (ep, pass, what) => call("POST", "/seriesmith/cut/reset", { ep, pass, what }),
    cutCopy: (ep, from, to, what) => call("POST", "/seriesmith/cut/copy", { ep, from, to, what }),
    peaks: async (ep, path, bins, start, end) => {
      const n = Math.max(1, Math.round(bins));
      const r = await get<Partial<PeaksResult>>(`/seriesmith/peaks?${qs({
        ep, path, bins: String(n),
        start: start != null && Number.isFinite(start) ? String(round6(start)) : undefined,
        end: end != null && Number.isFinite(end) ? String(round6(end)) : undefined,
      })}`);
      const peaks = Array.isArray(r?.peaks) ? r.peaks.map((x) => (typeof x === "number" && Number.isFinite(x) ? x : 0)) : [];
      return {
        duration: typeof r?.duration === "number" ? r.duration : 0, bins: peaks.length, peaks, silent: !!r?.silent,
        start: typeof r?.start === "number" ? r.start : null, end: typeof r?.end === "number" ? r.end : null,
      };
    },
    uploadClipAudio: (req, onProgress) => {
      const form = new FormData();
      form.append("ep", req.ep);
      const name = req.name ?? (typeof File !== "undefined" && req.file instanceof File ? req.file.name : "audio.wav");
      form.append("file", req.file, name);
      return postForm("/seriesmith/audio/import", form, onProgress);
    },
    putOverride: (req) => {
      const s = req.fields.seed;
      if (s !== undefined && s !== null && !isSeed(s)) {
        return Promise.reject(new Error(`Seed must be a string of digits, got ${String(s)}`));
      }
      return call("PUT", "/seriesmith/override", req);
    },
    deleteOverride: (ep, shot, pass) => call("DELETE", `/seriesmith/override?${qs({ ep, shot, pass })}`),
    assemble: (ep, pass, partial, opts) => call("POST", "/seriesmith/assemble", {
      ep, pass, partial,
      // only when set: older servers don't know them
      ...(opts?.upscaled ? { upscaled: true } : {}),
      ...(opts?.size ? { size: opts.size } : {}),
      ...(opts?.publish ? { publish: true } : {}),
    }),
    upscale: (req) => call("POST", "/seriesmith/upscale", req),
    upscaleOptions: (ep) => get(`/seriesmith/upscale/options${ep ? `?${qs({ ep })}` : ""}`),
    master: (req) => call("POST", "/seriesmith/master", req),
    post: (req) => call("POST", "/seriesmith/post", req),
    postOptions: (ep) => get(`/seriesmith/post/options${ep ? `?${qs({ ep })}` : ""}`),
    deletePost: (ep, shot, take, pass) => call("DELETE", `/seriesmith/post?${qs({ ep, shot, take: String(take), pass })}`),
    masterJob: (ep) => get(`/seriesmith/master/job?${qs({ ep })}`),
    putUpscaleKeep: (ep, shot, take, keep, pass) => call("PUT", "/seriesmith/upscale/keep", { ep, shot, take, keep, ...(pass ? { pass } : {}) }),
    putUpscaleRecipe: (ep, shot, recipe) => call("PUT", "/seriesmith/upscale/recipe", { ep, shot, recipe }),
    deleteUpscale: (ep, shot, take, pass) => call("DELETE", `/seriesmith/upscale?${qs({ ep, shot, take: String(take), pass })}`),
    browse: (path, files) => get(`/seriesmith/browse?${qs({ path: path || undefined, files: files || undefined })}`),
    refs: (ep) => get(`/seriesmith/refs?${qs({ ep })}`),
    refFileUrl: (ep, path, version) => t.url(`/seriesmith/file?${qs({ ep, path, v: version || undefined })}`),
    refsGenerate: (req) => {
      if (req.seed !== null && !isSeed(req.seed)) {
        return Promise.reject(new Error(`Seed must be a string of digits, got ${String(req.seed)}`));
      }
      // `target` and `seconds` only when set (an older server may reject an
      // unknown field's null, and `seconds` is 400 on anything but a voice ref)
      const { target, seconds, ...rest } = req;
      const body: Record<string, unknown> = { ...rest };
      if (target) body.target = target;
      if (seconds != null) body.seconds = seconds;
      return call("POST", "/seriesmith/refs/generate", body);
    },
    refsTour: (req) => call("POST", "/seriesmith/refs/tour", req),
    refsCopyTake: (req) => call("POST", "/seriesmith/refs/copy-take", req),
    refsTourFrame: (req) => call("POST", "/seriesmith/refs/tour-frame", req),
    refsGenerateMissing: (req) => {
      // only what's set: the server's defaults apply to the rest
      const body: Record<string, unknown> = { ep: req.ep };
      for (const k of ["pass", "kinds", "target", "keyframe_target", "backend"] as const) if (req[k] != null) body[k] = req[k];
      if (req.dry_run) body.dry_run = true;
      return call("POST", "/seriesmith/refs/generate-missing", body);
    },
    refsPick: (req) => call("PUT", "/seriesmith/refs/pick", req),
    refsVoiceFromTake: (req) => call("POST", "/seriesmith/refs/voice-from-take", req),
    alignReady: async () => {
      const r = await get<Partial<AlignReady>>("/seriesmith/align/ready");
      return {
        ready: !!r?.ready,
        ffmpeg: r?.ffmpeg ?? null,
        missing: Array.isArray(r?.missing) ? r.missing.filter((x): x is string => typeof x === "string") : [],
        python: r?.python ?? "",
        install: r?.install ?? "",
        ...(r?.ffmpeg_hint ? { ffmpeg_hint: r.ffmpeg_hint } : {}),
        ...(r?.packages ? { packages: r.packages } : {}),
        ...(r?.models ? { models: r.models } : {}),
      };
    },
    attachTrack: (ep, sourcePath, pass) =>
      call("POST", "/seriesmith/track", pass ? { ep, source_path: sourcePath, pass } : { ep, source_path: sourcePath }),
    uploadTrack: (req, onProgress) => {
      const form = new FormData();
      form.append("ep", req.ep);
      if (req.pass) form.append("pass", req.pass);
      const name = req.name ?? (typeof File !== "undefined" && req.file instanceof File ? req.file.name : "recording.wav");
      form.append("file", req.file, name);
      return postForm("/seriesmith/track", form, onProgress);
    },
    clearTrack: (ep, pass) => call("POST", "/seriesmith/track", pass ? { ep, track: null, pass } : { ep, track: null }),
    align: (req) => {
      // only what's set: the server's own defaults (snap true, dry_run false) apply
      const body: Record<string, unknown> = { ep: req.ep };
      if (req.track) body.track = req.track;
      if (req.model) body.model = req.model;
      if (req.snap === false) body.snap = false;
      if (req.dry_run) body.dry_run = true;
      if (req.pass) body.pass = req.pass;
      return call("POST", "/seriesmith/align", body);
    },
    refsImport: ({ pick, ...req }) => call("POST", "/seriesmith/refs/import", pick ? { ...req, pick: true } : req),
    refsUpload: (req, onProgress) => {
      const form = new FormData();
      form.append("ep", req.ep);
      form.append("ref", req.ref);
      if (req.view) form.append("view", req.view);
      if (req.pick) form.append("pick", "1");
      const name = req.name ?? (typeof File !== "undefined" && req.file instanceof File ? req.file.name : "upload");
      form.append("file", req.file, name);
      return postForm("/seriesmith/refs/import", form, onProgress);
    },
    issues: (ep, pass) => get<{ issues: Issue[] }>(`/seriesmith/issues?${qs({ ep, pass: pass || undefined })}`)
      .then((r) => r.issues),
    addIssue: (req) => call("POST", "/seriesmith/issues", req),
    resolveIssue: (ep, id) => call<{ issues: Issue[] }>("DELETE", `/seriesmith/issues?${qs({ ep, id })}`)
      .then((r) => r.issues),
    clearIssues: (ep, pass, addressedOnly) => call<{ issues: Issue[] }>(
      "DELETE",
      `/seriesmith/issues?${qs({ ep, pass: pass || undefined, clear: "1",
                             addressed: addressedOnly ? "1" : undefined })}`,
    ).then((r) => r.issues),
    exportIssues: (ep, pass) => get<{ text: string }>(`/seriesmith/issues/export?${qs({ ep, pass: pass || undefined })}`)
      .then((r) => r.text),
    refsMatch: (ep, names) => call("POST", "/seriesmith/refs/match", { ep, names }),
    refsDiscard: ({ ep, ref, view, take }) => call("POST", "/seriesmith/refs/discard", view ? { ep, ref, view, take } : { ep, ref, take }),
    refsKeyframe: (req) => call("POST", "/seriesmith/refs/keyframe", req),
    refsUnpick: (ep, ref, view) => call("DELETE", `/seriesmith/refs/pick?${qs({ ep, ref, view: view || undefined })}`),
    putRefDefaults: (ep, fields) => call("PUT", "/seriesmith/refs/defaults", { ep, ...fields }),

    putRefOverride: (req) => {
      const s = req.fields.seed;
      if (s !== undefined && s !== null && !isSeed(s)) {
        return Promise.reject(new Error(`Seed must be a string of digits, got ${String(s)}`));
      }
      return call("PUT", "/seriesmith/refs/override", req);
    },
    deleteRefOverride: (ep, ref, view) => call("DELETE", `/seriesmith/refs/override?${qs({ ep, ref, view: view || undefined })}`),
    models: async () => {
      try {
        const m = await get<string[]>("/models/diffusion_models");
        if (Array.isArray(m) && m.length) return m;
      } catch {
        /* older installs: fall through to unet */
      }
      return get<string[]>("/models/unet");
    },
    loras: () => get("/models/loras"),
    targets: async (opts) => {
      const { kind, ready, ep } = targetsQuery(opts);
      const r = await get<Partial<TargetList>>(`/seriesmith/targets?${qs({ kind, ready: ready ? "1" : undefined, ep: ep || undefined })}`);
      return { targets: Array.isArray(r?.targets) ? r.targets : [], default: r?.default ?? {} };
    },
    installWorkflow: async (target, opts) => {
      const r = await call<WorkflowInstallResult | undefined>("POST", "/seriesmith/workflow/install", {
        target, name: opts?.name, overwrite: opts?.overwrite ?? false,
      });
      return r ?? {};
    },
    revertWorkflow: async (target, name) => {
      const r = await call<WorkflowInstallResult | undefined>("DELETE", `/seriesmith/workflow/install?${qs({ target, name })}`);
      return r ?? {};
    },
    workflows: async () => {
      const r = await get<{ workflows?: WorkflowFile[] }>("/seriesmith/workflows");
      return Array.isArray(r?.workflows) ? r.workflows : [];
    },
    inspectTarget: (req) => call("POST", "/seriesmith/targets/inspect", req),
    routerInspect: (req) => call("POST", "/seriesmith/targets/router-inspect", req),
    saveCustomTarget: (ep, target, opts) => call("PUT", "/seriesmith/targets/custom", {
      ep, target, ...(opts?.scope ? { scope: opts.scope } : {}), ...(opts?.limits ? { limits: opts.limits } : {}),
    }),
    putTargetLimits: (ep, id, limits) => call("PUT", "/seriesmith/targets/limits", { ...(ep ? { ep } : {}), id, limits }),
    routerDryRun: (req) => call("POST", "/seriesmith/targets/router-dryrun", req),
    routerModels: (ep) => get(`/seriesmith/router/models?${qs({ ep: ep || undefined })}`),
    deleteCustomTarget: (ep, id) => call("DELETE", `/seriesmith/targets/custom?${qs({ ep, id })}`),
    setTargetDraft: (ep, id, draft) => call("PUT", "/seriesmith/targets/custom", { ep, id, draft }),
    putEpisodeTarget: async (ep, target) => {
      if (target !== null && (typeof target !== "string" || !target)) {
        return Promise.reject(new Error(`An episode target is a target id or null, got ${String(target)}`));
      }
      const r = await call<EpisodeTargetResult | undefined>("PUT", "/seriesmith/episode-target", { ep, target });
      return r ?? {};
    },
    widgetChoices: async (classType, field) => {
      const info = await get<unknown>(`/object_info/${encodeURIComponent(classType)}`);
      return comboChoices(info, classType, field);
    },
    modelFiles: async (target, param, ep) => {
      const r = await get<Partial<ModelList>>(`/seriesmith/models?${qs({ target, param, ep: ep || undefined })}`);
      return {
        target: r?.target ?? target, param: r?.param ?? param, family: r?.family ?? "", label: r?.label ?? r?.family ?? "",
        patterns: Array.isArray(r?.patterns) ? r.patterns : [], fingerprint: !!r?.fingerprint,
        files: Array.isArray(r?.files) ? r.files : [],
      };
    },
    source: (ep, file) => get(`/seriesmith/source?${qs({ ep, file })}`),
    sourceHash: (ep, file) => get(`/seriesmith/source?${qs({ ep, file, hash_only: "1" })}`),
    checkSource: (ep, file, text) => call("POST", "/seriesmith/source/check", { ep, file, text }),
    putSource: (req) => call("PUT", "/seriesmith/source", req),
    previewShot: (ep, pass, text, shot) => call("POST", "/seriesmith/shot/preview", { ep, pass, text, shot }),
    promotePlan: (ep, shot) => get(`/seriesmith/promote?${qs({ ep, shot: shot || undefined })}`),
    promote: (ep, items, hashes, shot) => call("POST", "/seriesmith/promote", shot ? { ep, items, hashes, shot } : { ep, items, hashes }),
    comfyQueue: async () => {
      const q = await get<{ queue_running?: unknown[][]; queue_pending?: unknown[][] }>("/queue");
      const ids = (xs?: unknown[][]) => (xs ?? []).map((x) => String(x[1]));
      return { running: ids(q.queue_running), pending: ids(q.queue_pending) };
    },
  };
}

function round6(n: number): number {
  return Math.round(n * 1e6) / 1e6;
}

export function errText(e: unknown): string {
  if (e instanceof Error) return e.message;
  if (typeof e === "string") return e;
  try {
    return JSON.stringify(e);
  } catch {
    return String(e);
  }
}
