// A stateful in-memory implementation of `Api`, built from a real rendered episode
// (fixtures.json, made by web/scripts/make_fixtures.py). Used only by the dev page.
// Renders are simulated: queued -> progress events -> ok, reusing real media.
// Round 2 / Phase 5: a fake folder tree for /browse (mockFs.ts) and stateful refs
// from the kitchen_sink series config (mockRefs.ts), which also decide each shot's
// `missing_refs`.

import type { Api } from "../api";
import { ApiError, UPLOAD_LIMIT, parseJsonSeedSafe, targetsQuery } from "../api";
import type { HostEvent } from "../host";
import type { SeriesTheme, XmlImportMedia, XmlImportSummary } from "../types";
import { reachable } from "../lib/browse";
import { insideRoot, nameError } from "../lib/newEpisode";
import { promptText } from "../lib/format";
import type {
  BuildResult, CutAudioSource, CutEntry, EpisodeStatus, EpisodeSummary, Issue, Lora, MissingRef, Override, OverrideResult, Pass,
  RefGenerateMissingResult, RefUsed, RenderResult, ShotDetail, ShotStatus, ShotTargetSource, SourceCheck, SourceFile,
  TakeDetail, TakeSummary, Target, TargetGraph, Track, TrackResult, ImportedShotTake,
  ShotSound,
} from "../types";
import { localShotSpans } from "../lib/source";
import { buildScript, buildSeries, checkScript, checkSeries, jsonErrorAt, mockHash, planPromote, type MockShotSource } from "./mockSource";
import { keyframeWanted } from "../lib/keyframes";
import { hasViews } from "../lib/refs";
import fixturesRaw from "./fixtures.json?raw";
import { FsError, browse as fsBrowse, fsExists, fsFileExists } from "./mockFs";
import { TRACK_RATE, makeTrack, makeVoice, slicePeaks, takePeaks, type MockWindow } from "./mockAudio";
import { AlignError, createMockAlign } from "./mockTrack";
import { MIX_DEFAULTS } from "../api";
import { MixError, checkMix, speechCurve } from "./mockMix";
import { CUE_PRESETS, CueError, MUSIC_TARGETS, SERIES_THEMES, checkCue, compMeasured, measureCue, planCue } from "./mockCue";
import { buildPlaylist } from "../lib/playlist";
import type { CueSpec, CueSummary, CueTake, MixVoice, MixVoices } from "../types";
import { CutError, applyCut, checkEntries, copyEntries, materialize, resetEntries } from "./mockCut";
import { RefError, createMockRefs } from "./mockRefs";
import { svgImage, type KeyframeNeedSpec } from "./mockRefs";
import {
  H3, H3_FL2V, LTX, LTX_REFS, MOCK_TARGETS, MOCK_WIDGET_CHOICES, WAN_I2V, ltxPrompt, mockModelFiles, mockReadiness, mockTakeResolved,
  preset, targetLength,
} from "./mockTargets";

/** series.json's `series.target` in the mock */
const SERIES_TARGET = H3;
/** shots whose script names a target (`target:` on the shot line). Phase 8.5:
 * two Wan 2.2 I2V shots (a required first frame: sh060's missing, sh070's a
 * generated still) and two H3 FL2V shots. */
const SCRIPT_TARGETS: Record<string, string> = { sh040: H3, sh060: WAN_I2V, sh070: WAN_I2V, sh080: H3_FL2V, sh090: H3_FL2V };
/** the script's `first:` / `last:` lines (Phase 8.5) */
const SCRIPT_KEYFRAMES: Record<string, Partial<Record<"first" | "last", string>>> = {
  sh030: { first: "continuity" },
  sh080: { first: "generate" },
  sh090: { first: "none", last: "import" },
};
/** shots built with `dur: model` (their length is an estimate until a take exists) */
const DUR_MODEL = new Set(["sh030", "sh080"]);
/** the episode's negative.txt */
const NEGATIVE_TXT = "blurry, extra fingers, text, watermark, photorealistic";

interface Fixtures {
  ep: string;
  summary: EpisodeSummary;
  status: Partial<Record<Pass, EpisodeStatus>>;
  detail: Partial<Record<Pass, Record<string, ShotDetail>>>;
  shotlist: Record<string, { shots: { prompt?: string | string[] }[] }>;
}

export type Emit = (event: HostEvent, detail: unknown) => void;

export interface MockOptions {
  /** start with no project roots, to see the first-run prompt */
  firstRun?: boolean;
  /** ms of simulated latency per call */
  latency?: number;
  /** base URL of the media folder */
  mediaBase?: string;
  /** a music cue to open (m01 over the first shots, three hits in the proxy mix, measured takes) */
  cueDemo?: boolean;
}

class MockError extends Error {
  constructor(message: string, public status: number, public data?: unknown) {
    super(message);
  }
}

const clone = <T>(x: T): T => JSON.parse(JSON.stringify(x));

/** Phase 9a: the dev page's hook for "edited in another editor" (see dev.tsx). */
export type OutsideEdit = (file: SourceFile, edit: (text: string) => string) => void;

export function createMockApi(emit: Emit, opts: MockOptions = {}): Api & { outsideEdit: OutsideEdit; unalign: () => void } {
  // seeds must survive: parse with the seed-safe parser, like the real client
  const fx = parseJsonSeedSafe<Fixtures>(fixturesRaw);
  const EP = fx.ep;
  /** the script's `target:` lines (Phase 9a: they follow the mock script's text) */
  const scriptTargets: Record<string, string> = { ...SCRIPT_TARGETS };
  /** series.json's `series.target` */
  let seriesTarget = SERIES_TARGET;
  let roots: string[] = opts.firstRun ? [] : [EP.replace(/[\\/][^\\/]+[\\/][^\\/]+$/, "")];
  // P10: the pass's notepad, in memory. The real one is `<ep>/_issues.json`;
  // `addressed` is computed on read there too, so the mock does the same rather
  // than storing it.
  const issues: Issue[] = [];
  // P5: episodes made through newEpisode. The mock has one real episode; a new
  // one is listed and opens as what it is on disk — unbuilt and empty.
  const made: { ep: string; name: string; title: string; simple?: boolean }[] = [];
  const status: Partial<Record<Pass, EpisodeStatus>> = clone(fx.status);
  const detail: Partial<Record<Pass, Record<string, ShotDetail>>> = clone(fx.detail);
  const cut: Record<Pass, CutEntry[]> = { final: [], proxy: [] };
  /** mix.json: one mix per pass */
  const mixes: Record<Pass, import("../types").Mix> = { final: {}, proxy: {} };
  const media = opts.mediaBase ?? "/mock/media/";
  /** a simulated take's files -> the real file it borrows */
  const alias = new Map<string, string>();
  let nextPrompt = 1;
  let chain: Promise<void> = Promise.resolve();
  /** the episode's master job (GET /seriesmith/master/job) */
  let masterJob: import("../types").MasterJob | null = null;

  const wait = (ms = opts.latency ?? 120) => (ms > 0 ? new Promise<void>((r) => setTimeout(r, ms)) : Promise.resolve());

  const shotIds = (fx.status.proxy ?? fx.status.final)!.shots.map((s) => s.shot);
  const refs = createMockRefs({
    ep: EP,
    emit,
    shots: shotIds,
    wait: (ms) => wait(ms),
    enqueue: (job) => {
      chain = chain.then(job);
    },
    nextPrompt: () => `mock-${nextPrompt++}-ref`,
    onLiveChange: (ref) => markRefStale(ref),
    needs: () => keyframeNeeds(),
  });

  /**
   * The build's keyframe needs (Phase 8.5): every shot whose target reads
   * keyframes, or whose script asks for one. Wan I2V's first frame is required.
   * The method: the script's (`continuous: first` is continuity), else generate.
   */
  function keyframeNeeds(): KeyframeNeedSpec[] {
    const s = status.proxy ?? status.final;
    if (!s) return [];
    const shots = s.shots.filter((x) => !x.orphan);
    const out: KeyframeNeedSpec[] = [];
    shots.forEach((sh) => {
      const d = detail.proxy?.[sh.shot] ?? detail.final?.[sh.shot];
      const target = shotTargetOf(sh.shot, d?.override ?? {}).target;
      const caps = MOCK_TARGETS.targets.find((t) => t.id === target)?.capabilities;
      const reads = (caps?.keyframes ?? []) as string[];
      const script = SCRIPT_KEYFRAMES[sh.shot] ?? {};
      for (const which of ["first", "last"] as const) {
        const asked = script[which];
        if (!reads.includes(which) && !asked) continue;
        out.push({
          shot: sh.shot, which, target,
          need: which === "first" && caps?.requires_first ? "required" : "optional",
          method: asked ?? "generate",
          requested: !!asked && asked !== "none",
        });
      }
    });
    return out;
  }

  /** The refs a shot's current target reads (GET /seriesmith/shot `refs_used`), as
   * edit.refs_used sends them: `kind` image | audio, `need` on every entry,
   * `thumb` only when the file is there, `id` null for a composed sheet. */
  function refsUsedOf(shot: string, target: string): RefUsed[] {
    const caps = MOCK_TARGETS.targets.find((t) => t.id === target)?.capabilities;
    const out: RefUsed[] = [];
    let pic = 1;
    if (caps?.subject_refs !== false) {
      for (const id of refs.usedByShot(shotIds.indexOf(shot))) {
        const r = refs.info(id);
        if (!r) continue;
        const audio = r.kind === "voice";
        // a voice sample is read only by targets that take one
        if (audio && !caps?.voice_reference) continue;
        out.push({
          id, kind: audio ? "audio" : "image", role: audio ? "voice" : r.kind === "location" ? "plate" : "subject", path: r.path,
          exists: r.exists, need: "required", thumb: r.exists ? r.path : null, slot: audio ? "Audio 1" : `Picture ${pic++}`,
        });
      }
    }
    for (const n of refs.keyframeNeeds(shot)) {
      if (n.method === "none") continue;
      const id = `shot:${shot}:${n.which}`;
      const r = refs.info(id);
      const path = r?.path ?? `refs/shots/${shot}/${n.which}.png`;
      out.push({ id, kind: "image", role: n.which, path, exists: !!r?.exists, need: n.need, thumb: r?.exists ? path : null, slot: `${n.which} frame` });
    }
    if (target === LTX_REFS) {
      const path = `refs/_sheets/${shot}_refsheet.png`;
      out.push({ id: null, kind: "image", role: "reference_sheet", path, exists: true, need: "required", thumb: path, slot: "reference sheet" });
    }
    return out;
  }

  /** The series refs a shot is missing, when its target reads subject pictures (not Wan I2V, LTX-2 or FL2V). */
  function seriesMissing(shot: string): MissingRef[] {
    const d = detail.proxy?.[shot] ?? detail.final?.[shot];
    const target = shotTargetOf(shot, d?.override ?? {}).target;
    const caps = MOCK_TARGETS.targets.find((t) => t.id === target)?.capabilities;
    return caps?.subject_refs === false ? [] : refs.missingFor(shot, shotIds.indexOf(shot));
  }

  /** Missing refs a render can't do without (Wan I2V's first frame): anyway false. */
  function keyframeMissing(shot: string): MissingRef[] {
    return refs.keyframeNeeds(shot)
      .filter((n) => n.need === "required" && !refs.info(`shot:${shot}:${n.which}`)?.exists)
      .map((n) => ({
        slot: n.which === "first" ? "First frame" : "Last frame", kind: "image" as const, path: `refs/shots/${shot}/${n.which}.png`,
        anyway: false,
        why: `${MOCK_TARGETS.targets.find((t) => t.id === n.target)?.label ?? n.target} needs a ${n.which} frame: use the previous shot's frame, generate a still or import one (Refs tab)`,
      }));
  }

  // a reference sheet the ingredients target kept (reference_image on a take)
  refs.addImage("refs/_sheets/sh010_refsheet.png", svgImage("sh010 reference sheet", "Ada · Narrator · kitchen", "sheet", "location", 768, 448));
  for (const shot of shotIds) refs.addImage(`refs/_sheets/${shot}_refsheet.png`, svgImage(`${shot} reference sheet`, "subjects + plate", shot, "location", 768, 448));

  /** A re-picked ref makes the finished takes of the shots using it ref-stale. */
  function markRefStale(ref: string) {
    const idx = new Set(refs.dependents(ref));
    for (const pass of ["final", "proxy"] as Pass[]) {
      const s = status[pass];
      if (!s) continue;
      s.shots.forEach((sh) => {
        const i = shotIds.indexOf(sh.shot);
        if (!idx.has(i)) return;
        for (const t of sh.takes) if (t.status === "ok" && !t.stale.includes("ref")) t.stale = [...t.stale.filter((x) => x !== "unknown"), "ref"];
        for (const t of detail[pass]?.[sh.shot]?.takes ?? []) if (t.status === "ok" && !t.stale.includes("ref")) t.stale = [...t.stale.filter((x) => x !== "unknown"), "ref"];
      });
    }
  }

  function withMissing(e: EpisodeStatus): EpisodeStatus {
    for (const s of e.shots) {
      s.missing_refs = s.orphan ? [] : [...seriesMissing(s.shot), ...keyframeMissing(s.shot)];
      // Phase 8.5: `dur: model` before a take exists: the length is an estimate
      if (DUR_MODEL.has(s.shot)) s.length_estimated = !s.takes.some((t) => t.status === "ok" && t.has_video);
    }
    return e;
  }

  function need(ep: string) {
    if (!roots.length) throw new MockError("No project roots are configured.", 403);
    if (ep !== EP && !made.some((m) => m.ep === ep)) {
      throw new MockError(`Unknown episode ${ep}`, 404);
    }
  }

  /** P10: the shot was re-rendered since the note (the mock has no rebuild, so
   *  a newer usable take is the whole rule here). */
  function issueAddressed(x: Issue): boolean {
    if (!x.take) return false;
    const sh = status[x.pass]?.shots.find((y) => y.shot === x.shot);
    if (!sh) return true;
    return sh.takes.some((t) => t.take > (x.take ?? 0) && t.status === "ok");
  }

  function madeSummary(m: { ep: string; name: string; title: string; simple?: boolean }): EpisodeSummary {
    return {
      ep: m.ep, name: m.name, series: fx.summary.series, title: m.title,
      built: { final: false, proxy: false }, shots: 0, script: `${m.name}.md`,
      ...(m.simple ? { simple: true } : {}),
    };
  }

  function emptyStatus(m: { ep: string; title: string }, pass: Pass): EpisodeStatus {
    const base = st("proxy");
    return {
      episode: m.title, title: m.title, pass, fps: base.fps, width: base.width,
      height: base.height, folder: m.ep, shots: [], target: base.target,
      target_source: base.target_source, series_target: base.series_target ?? null, track: null,
    };
  }

  function st(pass: Pass): EpisodeStatus {
    const s = status[pass];
    if (!s) throw new MockError(`${pass} isn't built`, 404);
    return s;
  }

  function shotSt(pass: Pass, shot: string): ShotStatus {
    const s = st(pass).shots.find((x) => x.shot === shot);
    if (!s) throw new MockError(`${shot} is not in the ${pass} shotlist`, 404);
    return s;
  }

  function det(pass: Pass, shot: string): ShotDetail {
    const d = detail[pass]?.[shot];
    if (!d) throw new MockError(`${shot} is not in the ${pass} shotlist`, 404);
    return d;
  }

  /** Each pass's script order (the build's; the fixture's shots come in it). */
  const scriptOrder: Record<Pass, string[]> = {
    final: (status.final?.shots ?? []).map((s) => s.shot),
    proxy: (status.proxy?.shots ?? []).map((s) => s.shot),
  };
  const otherPass = (p: Pass): Pass => (p === "proxy" ? "final" : "proxy");

  /** recompute the cut the way edit does: cut order (resolve_cut), each
   * shot's take (latest usable, or the pick), trims, locks (Phase 9b) */
  function recut(pass: Pass) {
    const e = status[pass];
    if (!e) return;
    e.shots = applyCut(
      e.shots, cut[pass], pass, scriptOrder[pass],
      (shot) => status[otherPass(pass)]?.shots.find((x) => x.shot === shot)?.takes ?? [],
      (shot, a) => audioSourceFile(shot, a),
    );
  }

  // ---- Phase 9b: the recorded dialogue track, dialogue windows, peaks ----
  /** shots with no dialogue (no window on the track) */
  const SILENT = new Set(["sh040", "sh100", "sh230", "sh330"]);
  const TRACK_PATH = "audio/ep05_dialogue.wav";
  /** windows laid end to end in script order from 1 s, as align would time them */
  let windows: Record<string, MockWindow> = {};
  let trackEnd = 1;
  for (const sh of (status.proxy ?? status.final)!.shots) {
    const secs = (sh.length ?? Math.round((sh.seconds ?? 3) * 24)) / 24;
    if (!SILENT.has(sh.shot)) windows[sh.shot] = { shot: sh.shot, audioIn: round3(trackEnd), audioOut: round3(trackEnd + secs) };
    trackEnd += secs;
  }
  const track = makeTrack(Object.values(windows), round3(trackEnd + 1.5));
  // Phase 9c-A: the series config's `audio.track` — attachable and clearable
  let trackPath: string | null = TRACK_PATH;
  /** a transcript sits beside the recording (re-aligning then needs no Whisper) */
  let trackWords = true;
  /** the recording's vocal stem sits beside it; the series config's audio.dub_from */
  let trackVocals = false;
  let dubFrom: "recording" | "vocals" = "recording";

  function round3(n: number) {
    return Math.round(n * 1000) / 1000;
  }

  // ---- Phase 9d: loose media files inside the episode, for a clip's audio ----
  /** `<episode>/audio/*`: synthetic, playable and drawable, like a voice sample. */
  const clipFiles = new Map<string, ReturnType<typeof makeVoice>>([
    ["audio/line_sh030.wav", makeVoice("clip|line_sh030", 3.5)],
    ["audio/room_tone.wav", makeVoice("clip|room_tone", 12)],
    ["audio/no_sound.wav", makeVoice("clip|silent", 0)],
  ]);

  /**
   * What an audio source will actually play, relative to the episode (null:
   * there is nothing to play, which PUT /seriesmith/cut answers 400 for).
   */
  function audioSourceFile(own: string, a: CutAudioSource): string | null {
    if (a.source === "none") return null;
    if (a.source === "file") {
      const p = (a.path ?? "").replace(/\\/g, "/");
      const f = clipFiles.get(p);
      if (f) return f.duration > 0 ? p : null;
      // a take's own media is a file inside the episode too
      return mediaSeconds(p) ? p : null;
    }
    const pass = a.pass ?? "proxy";
    const sh = status[pass]?.shots.find((x) => x.shot === (a.shot || own));
    const t = sh?.takes.find((x) => x.take === a.take);
    return t && t.status === "ok" && t.has_video && t.mp4 ? t.mp4 : null;
  }

  /** Phase 9b fields on a status copy: the track, windows, take audio and frames. */
  function with9b(e: EpisodeStatus): EpisodeStatus {
    e.track = trackPath
      ? {
        path: trackPath, duration: track.duration, rate: TRACK_RATE, exists: true, words: trackWords,
        vocals: trackVocals, vocals_words: false, dub_from: dubFrom,
        aligned: e.shots.filter((s) => windows[s.shot]).length,
      }
      : null;
    for (const sh of e.shots) {
      const w = windows[sh.shot];
      if (w) {
        sh.audio_in = w.audioIn;
        sh.audio_out = w.audioOut;
      }
      for (const t of sh.takes) {
        const ok = t.status === "ok" && t.has_video && !!t.mp4;
        t.audio = ok ? t.mp4 : null;
        if (ok && t.frames == null && sh.length) t.frames = sh.length;
      }
      if (sh.cut.usable && sh.cut.frames == null && !sh.cut.placeholder) {
        sh.cut.frames = sh.takes.find((t) => t.take === sh.cut.take)?.frames ?? null;
      }
    }
    return e;
  }

  /** The frames of the take a cut entry would use, and their rate (null: not known). */
  function entryFrames(pass: Pass, entry: CutEntry): [number, number] | null {
    const src = entry.pass ?? pass;
    const sh = status[src]?.shots.find((x) => x.shot === entry.shot);
    if (!sh) return null;
    const usable = sh.takes.filter((t) => t.status === "ok" && t.has_video);
    const t = entry.take != null ? sh.takes.find((x) => x.take === entry.take) : usable[usable.length - 1];
    const frames = t && t.status === "ok" && t.has_video ? t.frames ?? sh.length : null;
    return frames ? [frames, t?.fps || status[src]?.fps || 24] : null;
  }

  /** The files the peaks route knows: takes' audio, voice candidates and the
   * track, with their length. */
  function mediaSeconds(path: string): number | null {
    if (path === TRACK_PATH) return track.duration;
    const clip = clipFiles.get(path.replace(/\\/g, "/"));
    if (clip) return clip.duration;
    const voice = refs.audioSeconds(path);
    if (voice != null) return voice;
    for (const p of ["final", "proxy"] as Pass[]) {
      for (const sh of status[p]?.shots ?? []) {
        for (const t of sh.takes) if (t.mp4 === path) return (t.frames ?? sh.length ?? 72) / (t.fps || status[p]!.fps || 24);
      }
    }
    return null;
  }

  /** The sound of one take, for voice-from-take (peaks.clip_audio's rule:
   * the mp4 when it carries sound, else the take's `_h3.wav`). */
  function takeAudio(pass: Pass, shot: string, take: number): { path: string; seconds: number } | null {
    const sh = status[pass]?.shots.find((x) => x.shot === shot);
    const t = sh?.takes.find((x) => x.take === take);
    if (!sh || !t || t.status !== "ok" || !t.has_video || !t.mp4) return null;
    return { path: t.mp4, seconds: (t.frames ?? sh.length ?? 72) / (t.fps || status[pass]!.fps || 24) };
  }
  // the smoke episode's cut.json picks sh020 t01 in proxy
  for (const pass of ["final", "proxy"] as Pass[]) {
    for (const s of status[pass]?.shots ?? []) if (s.cut.picked && s.cut.take != null) cut[pass].push({ shot: s.shot, take: s.cut.take });
  }
  // Phase 9b: order, script_index, out_of_order from the start
  for (const pass of ["final", "proxy"] as Pass[]) recut(pass);

  // ---- music cues (seriesmith/cue.py): specs, takes, a plan against Play all's layout ----
  const cueSpecs = new Map<string, CueSpec>();
  const cueTakes = new Map<string, CueTake[]>();
  /** the script's music: notes, for a plan's prompt */
  const MUSIC_NOTES: Record<string, string> = { sh020: "tension rises as she looks up", sh030: "swells, full, on the reveal" };
  const cuePlaylist = (pass: Pass) => buildPlaylist(status[pass], status[pass === "proxy" ? "final" : "proxy"]);
  // the takes split into voice stems ("pass:shot:take"): made at once when asked
  const voiceStems = new Set<string>();
  // GET /seriesmith/mix's voices: every other clip has lines, as the speech curve has them speak
  const mockVoices = (pass: Pass): MixVoices => {
    const mix = mixes[pass] ?? {};
    const on = !!mix.tracks?.dialogue?.voices_only;
    const shots: MixVoice[] = cuePlaylist(pass).filter((it) => it.mp4 && it.take != null).map((it) => {
      const own = mix.voices?.[it.shot]?.voices_only;
      const want = own ?? on;
      const ok = voiceStems.has(`${pass}:${it.shot}:${it.take}`);
      const lines = it.index % 2 === 0;
      const plays = !want ? "whole" : !lines && own !== true ? "silence" : ok ? "voice" : "whole";
      return { shot: it.shot, pass: it.pass, take: it.take, path: it.mp4!.replace(/\.mp4$/, ".voice.wav"),
               state: ok ? "ok" : "missing", why: ok ? null : `${it.shot} hasn't been split`, voices_only: want,
               override: own ?? null, plays, lines };
    });
    return { voices_only: on, shots, split: shots.filter((x) => x.state === "ok").length, of: shots.length, queued: 0 };
  };
  /** the series config's score direction (sound.score) */
  const SCORE_DIRECTION = "sincere, never comic: strings and a solo horn";
  const cuePlan = (spec: CueSpec, pass: Pass) => planCue(spec, cuePlaylist(pass), st(pass).fps || 24, mixes[pass] ?? {}, MUSIC_NOTES, SCORE_DIRECTION);
  const cueFile = (cid: string, n: number) => `sound/${cid}/t${String(n).padStart(2, "0")}.wav`;
  function cueTakeDone(cid: string, t: CueTake, pass: Pass) {
    const spec = cueSpecs.get(cid)!;
    const p = cuePlan(spec, pass);
    t.status = "ok";
    t.measured = measureCue(p, t.seed ?? t.take);
    t.file = cueFile(cid, t.take);
    t.finished = new Date().toISOString();
    t.stale = [];
    clipFiles.set(t.file, makeVoice(`cue|${cid}|${t.take}`, p.seconds + t.measured.downbeat));
  }
  /** the takes best first (cue.ranked) */
  const rankedTakes = (cid: string) => {
    const all = cueTakes.get(cid) ?? [];
    const done = all.filter((t) => t.status === "ok" && t.measured).sort((a, b) => a.measured!.score - b.measured!.score);
    return [...done, ...all.filter((t) => !done.includes(t))];
  };
  if (opts.cueDemo) {
    const shots = status.proxy?.shots ?? [];
    mixes.proxy = {
      hits: [
        { id: "h01", name: "she looks up", at: { shot: shots[1].shot, frame: 30 } },
        { id: "h02", name: "the reveal", at: { shot: shots[2].shot, frame: 20 }, kind: "arrive" },
        { id: "h03", name: "silence", at: { shot: shots[3].shot, frame: 12 }, kind: "drop", must: false },
      ],
      // a bed under the first shots, brought up and down by its volume points (the gain line)
      items: [{
        id: "amb01", track: "ambience", path: "audio/room_tone.wav", in: { shot: shots[0].shot, frame: 0 }, out: { shot: shots[2].shot, frame: 40 }, loop: true,
        points: [{ at: { shot: shots[0].shot, frame: 30 }, db: -9 }, { at: { shot: shots[1].shot, frame: 20 }, db: 3 }, { at: { shot: shots[2].shot, frame: 10 }, db: -4 }],
      }],
    };
    cueSpecs.set("m01", {
      id: "m01", label: "1M1 The Reveal", in: { shot: shots[0].shot, frame: 24 }, out: { shot: shots[3].shot, frame: 60 },
      style: "romantic orchestral, solo horn", bpm: 92,
    });
    const takes: CueTake[] = [1, 2, 3, 4].map((n) => ({ take: n, status: "queued", seed: 1000 + n * 37, target: "stable_audio3", pass: "proxy" as Pass }));
    for (const t of takes.slice(0, 3)) cueTakeDone("m01", t, "proxy");
    takes[2].stale = ["she looks up moved -6 frames"];
    takes[3].status = "failed";
    takes[3].error = "the job ended failed: out of memory";
    cueTakes.set("m01", takes);
  }

  function effectiveOf(pass: Pass, shot: string): ShotDetail["effective"] {
    const d = det(pass, shot);
    const ov = d.override;
    const b = d.built as { seed?: string; model?: string; steps?: number };
    const base = fx.detail[pass]?.[shot]?.effective;
    const target = shotTargetOf(shot, ov).target;
    const frames = Number((d.built as { length?: number }).length ?? 0);
    const seed = ov.seed ?? (b.seed as string) ?? "0";
    const seed_source = ov.seed != null ? "override" : "stable";
    if (target !== H3) {
      // retargeted: the target's own prompt and defaults; the prompt override is ignored
      const p = preset(target, pass);
      const caps = MOCK_TARGETS.targets.find((t) => t.id === target)?.capabilities;
      const built = d.built as { audio_policy?: string; voice_refs?: unknown[] };
      const notes = [
        ...(ov.prompt != null ? [`the prompt override was ignored: a prompt written for ${H3} isn't valid for ${target}`] : []),
        ...(!caps?.voice_reference && (built.audio_policy === "clone" || built.voice_refs?.length)
          ? [`audio clone renders as generate on ${target}: it takes no voice reference (voices come from each voice line)`] : []),
      ];
      // Phase 8.5: request → shot override → negative.txt (Wan) → series.json → preset
      const neg = caps?.negative_prompt
        ? ov.negative != null
          ? { negative: ov.negative, negative_source: "override" }
          : target === WAN_I2V || target === "wan22_vace"
            ? { negative: NEGATIVE_TXT, negative_source: "negative.txt" }
            : { negative: "worst quality, inconsistent motion, blurry, jittery, distorted", negative_source: "preset" }
        : {};
      const low = typeof p?.model_low === "string" ? { model_low: ov.model_low ?? p.model_low } : {};
      return {
        prompt: ltxPrompt(d.built_prompt), seed, seed_source,
        model: ov.model ?? p?.model ?? "", loras: ov.loras !== undefined ? ov.loras : null, steps: ov.steps ?? p?.steps ?? 8,
        target, width: p?.width ?? null, height: p?.height ?? null, length: targetLength(target, frames),
        ...neg, ...low, ...(notes.length ? { notes } : {}),
      };
    }
    return {
      prompt: ov.prompt != null ? promptText(ov.prompt) : d.built_prompt,
      seed, seed_source,
      model: ov.model ?? base?.model ?? "",
      loras: ov.loras !== undefined ? ov.loras : base?.loras ?? null,
      steps: ov.steps ?? b.steps ?? 4,
      target, width: st(pass).width, height: st(pass).height, length: frames || null,
      // H3 takes no negative
      negative: null, negative_source: "none",
    };
  }

  function syncOverrideSummary(shot: string) {
    for (const pass of ["final", "proxy"] as Pass[]) {
      const s = status[pass]?.shots.find((x) => x.shot === shot);
      const d = detail[pass]?.[shot];
      if (!s || !d) continue;
      s.override = { fields: Object.keys(d.override).sort(), stale: d.override_stale && !!d.override.prompt };
      d.effective = effectiveOf(pass, shot);
      // Phase 8: the target the next render uses, and the one the build compiled for
      const tg = shotTargetOf(shot, d.override);
      d.target = s.target = tg.target;
      d.target_source = s.target_source = tg.source;
      d.built_target = s.built_target = scriptTargets[shot] ?? seriesTarget;
      s.profile = d.profile = null;
      for (const t of s.takes) {
        if (t.target === undefined) t.target = d.takes.find((x) => x.take === t.take)?.sidecar?.target as string | undefined ?? null;
      }
    }
  }

  /** The episode's default target: the editor's, else series.json's. */
  let episodeTarget: string | null = null;
  // shots' sounds (PUT /seriesmith/sound)
  const sounds: Record<string, ShotSound> = {};
  // Phase 11: which workflows this "ComfyUI" has saved (Copy to ComfyUI / Revert).
  // H3's is saved already, as it is on a machine that has rendered with it.
  const savedWorkflows = new Set<string>(
    [MOCK_TARGETS.targets.find((t) => t.id === H3)?.workflow].filter((x): x is string => !!x),
  );

  /** A target's `graph` block: $ENV isn't set in the mock, so a saved copy wins,
   * else the repo's. H3's saved copy is marked edited, to exercise the badge. */
  const mockGraph = (t: Target): TargetGraph => {
    const name = t.workflow || `${t.id}.json`;
    const saved = savedWorkflows.has(name);
    return {
      name,
      source: saved ? "comfy" : "repo",
      where: saved ? `http://127.0.0.1:8188 (user workflows/${name})`
        : `C:\repos\seriesmith\targets\${t.kind}\${t.id}\workflow.json`,
      env: "SERIESMITH_MINIMAX_H3_REF2VA_WORKFLOW",
      env_set: false,
      installed: saved,
      differs: saved && t.id === H3,
      repo: `C:\repos\seriesmith\targets\${t.kind}\${t.id}\workflow.json`,
      error: "",
    };
  };

  /** The target a shot's next render uses, and where it comes from (no request here). */
  function shotTargetOf(shot: string, ov: Override): { target: string; source: ShotTargetSource } {
    if (ov.target) return { target: ov.target, source: "override" };
    if (scriptTargets[shot]) return { target: scriptTargets[shot], source: "script" };
    // no target of its own: the editor's episode target, else series.json's
    return { target: episodeTarget ?? seriesTarget, source: episodeTarget ? "episode" : "series" };
  }

  function syncEpisodeTarget() {
    for (const pass of ["final", "proxy"] as Pass[]) {
      const s = status[pass];
      if (!s) continue;
      s.target = episodeTarget ?? seriesTarget;
      s.target_source = episodeTarget ? "editor" : "series";
      s.series_target = seriesTarget;
    }
    for (const id of shotIds) syncOverrideSummary(id);
  }

  // Fixtures for Phase 8: sh030 is retargeted to LTX-2 (its H3 takes now render
  // on another target than the shot), and sh020's t02 was a one-off LTX-2 run,
  // so its takes mix targets. Readiness: sh020's t02 ran without LTX's duration
  // head, and its t01 before the H3 turbo LoRA was installed.
  for (const pass of ["final", "proxy"] as Pass[]) {
    const d = detail[pass]?.sh030;
    if (d) d.override.target = LTX;
    const t2 = detail[pass]?.sh020?.takes.find((t) => t.take === 2);
    if (t2?.sidecar) {
      t2.sidecar.target = LTX;
      t2.sidecar.resolved = { duration_head: { want: "ltx-2.5-duration-head-bf16.safetensors", using: null, how: "off" } };
    }
    // Phase 8.5: sh010's t01 was a one-off run on the ingredients target, which kept its reference sheet
    const s1 = detail[pass]?.sh010?.takes.find((t) => t.take === 1);
    if (s1) {
      if (s1.sidecar) s1.sidecar.target = LTX_REFS;
      s1.reference_image = "refs/_sheets/sh010_refsheet.png";
    }
    const t1 = detail[pass]?.sh020?.takes.find((t) => t.take === 1);
    if (t1?.sidecar) {
      t1.sidecar.resolved = {
        model: { want: "minimax_h3_ref2va_pruned_int8_convrot.safetensors", using: "minimax_h3_ref2va_pruned_int8_convrot.safetensors", how: "exact" },
        loras: { want: "minimax_h3_ref2v_lightx2v_turbo_4step_v0.1_resized_avg_rank_20_bf16.safetensors", using: null, how: "base" },
      };
    }
  }
  syncEpisodeTarget();

  /** PUT / DELETE /seriesmith/override's answer: both passes, and the targets. */
  function overrideResult(shot: string): OverrideResult {
    const res: OverrideResult = { override: {} };
    for (const p of ["final", "proxy"] as Pass[]) {
      const d = detail[p]?.[shot];
      if (!d) continue;
      res.override[p] = { ...clone(d.override), stale: d.override_stale };
      res.target = d.target ?? undefined;
      res.built_target = d.built_target ?? undefined;
    }
    return res;
  }

  function randomSeed(): string {

    // new seeds stay below 2^53
    return String(Math.floor(Math.random() * 2 ** 52));
  }

  function donor(): { thumb: string; strip: string; mp4: string } {
    const all = Object.values(fx.status).flatMap((s) => s!.shots.flatMap((x) => x.takes));
    const pool = all.filter((t) => t.thumb && t.strip && t.mp4);
    const t = pool[Math.floor(Math.random() * pool.length)];
    return { thumb: t.thumb!, strip: t.strip!, mp4: t.mp4! };
  }

  function simulate(pass: Pass, shot: string, take: number, pid: string) {
    chain = chain.then(async () => {
      const s = shotSt(pass, shot);
      const t = s.takes.find((x) => x.take === take);
      if (!t || t.status !== "queued") return;
      await wait(500);
      emit("execution_start", { prompt_id: pid });
      const max = 8;
      for (let v = 1; v <= max; v++) {
        if (t.status !== "queued") return; // cancelled
        emit("progress", { value: v, max, prompt_id: pid, node: "3" });
        await wait(350);
      }
      const d = donor();
      const folder = st(pass).folder;
      const stem = `${folder}/${shot}/${shot}_t${String(take).padStart(2, "0")}`;
      const files = { thumb: `${stem}.jpg`, strip: `${stem}_strip.jpg`, mp4: `${stem}.mp4` };
      alias.set(files.thumb, d.thumb);
      alias.set(files.strip, d.strip);
      alias.set(files.mp4, d.mp4);
      Object.assign(t, { status: "ok", has_video: true, finished: new Date().toISOString(), save_notes: "mock render", ...files });
      const td = det(pass, shot).takes.find((x) => x.take === take);
      if (td) {
        td.status = "ok";
        td.has_video = true;
        td.files = { ...td.files, ...files };
        if (td.sidecar) Object.assign(td.sidecar, { status: "ok", finished: t.finished, frames: s.length });
      }
      recut(pass);
      emit("executing", null);
      emit("execution_success", { prompt_id: pid });
      emit("seriesmith.take", { ep: EP, pass, shot, take, status: "ok", thumb: files.thumb });
    });
  }

  // -------------------------------------------------------------------------
  // Phase 9a: the authored files (mockSource.ts builds them from the fixtures)
  // -------------------------------------------------------------------------

  const epStatus = (status.proxy ?? status.final)!;
  const sourceShots: MockShotSource[] = epStatus.shots.filter((s) => !s.orphan).map((s) => {
    const d = detail.proxy?.[s.shot] ?? detail.final?.[s.shot];
    const b = (d?.built ?? {}) as { prompt?: string | string[]; background?: string; voices?: string[] };
    return {
      shot: s.shot, sequence: s.sequence ?? "sq01", subjects: s.subjects, size: s.size ?? null, seconds: s.seconds ?? 0,
      background: b.background ?? null, prompt: Array.isArray(b.prompt) ? b.prompt.join("\n\n") : b.prompt ?? d?.built_prompt ?? "",
      voices: b.voices ?? [],
    };
  });
  const scriptName = fx.summary.script ?? `${epStatus.episode}.md`;
  const files: Record<SourceFile, { text: string; hash: string; mtime: number }> = {
    script: { text: "", hash: "", mtime: 0 },
    series: { text: "", hash: "", mtime: 0 },
  };
  const writeFile = (file: SourceFile, text: string) => {
    files[file] = { text, hash: mockHash(text), mtime: Date.now() / 1000 };
    if (file === "script") syncScriptTargets(text);
  };
  /** the script's `target:` lines decide the mock's script targets */
  function syncScriptTargets(text: string) {
    const lines = text.split("\n");
    for (const k of Object.keys(scriptTargets)) delete scriptTargets[k];
    for (const sp of localShotSpans(text)) {
      for (let n = sp.line; n < sp.end_line; n++) {
        const m = /^target:\s*(\S+)/.exec(lines[n]);
        if (m) scriptTargets[sp.id] = m[1];
      }
    }
  }
  function seriesCfg(): { series?: { target?: string } } | null {
    try {
      return JSON.parse(files.series.text);
    } catch {
      return null;
    }
  }
  writeFile("script", buildScript({ id: epStatus.episode, title: epStatus.title ?? fx.summary.title ?? "" }, sourceShots, {
    targets: SCRIPT_TARGETS, keyframes: SCRIPT_KEYFRAMES, durModel: DUR_MODEL,
  }));
  writeFile("series", buildSeries(fx.summary.title ?? epStatus.title ?? "", sourceShots));
  /** As built: the build stops at its first error, so `errors` has at most one. */
  const check = (file: SourceFile, text: string): SourceCheck => {
    const c = file === "script" ? checkScript(text, seriesCfg() ?? {}) : checkSeries(text, files.script.text);
    return { ...c, errors: c.errors.slice(0, 1), shots: file === "series" ? [] : c.shots };
  };
  const sourcePath = (file: SourceFile) => (file === "script" ? scriptName : "series.json");
  const conflict = (file: SourceFile) => new MockError("changed on disk", 409, { error: "changed on disk", file, hash: files[file].hash, text: files[file].text });

  /** The dev page's stand-in for an edit in another editor: h3mockEdit("script", t => t.replace(…)). */
  const outsideEdit: OutsideEdit = (file, edit) => {
    writeFile(file, edit(files[file].text));
  };

  /** After a write: the series target and the shots' targets follow the files. */
  function afterSourceWrite() {
    seriesTarget = seriesCfg()?.series?.target ?? SERIES_TARGET;
    syncEpisodeTarget();
  }

  // -------------------------------------------------------------------------
  // Phase 9c-A: attaching a recording, and running align
  // -------------------------------------------------------------------------

  /** `track` as GET /seriesmith/episode and the track routes send it. */
  function trackInfo(pass: Pass): Track | null {
    if (!trackPath) return null;
    const shots = status[pass]?.shots ?? [];
    return {
      path: trackPath, duration: track.duration, rate: TRACK_RATE, exists: true, words: trackWords,
        vocals: trackVocals, vocals_words: false, dub_from: dubFrom,
      aligned: shots.filter((s) => windows[s.shot]).length,
    };
  }

  /** POST /seriesmith/track: the file lands in <ep>/audio/ (or is used in place). */
  function attach(source: string, pass: Pass, upload: boolean): TrackResult {
    const name = source.replace(/\\/g, "/").split("/").pop() ?? "recording.wav";
    if (!/\.(wav|mp3|flac|ogg|m4a|aac|opus)$/i.test(name)) {
      throw new MockError(`${name} is not a recording: the track must be one of .wav, .mp3, .flac, .ogg, .m4a, .aac, .opus`, 400);
    }
    const inEp = /^audio[\\/]/i.test(source);
    if (!upload && !inEp && !fsFileExists(source)) {
      throw new MockError(`${source} doesn't exist on the ComfyUI machine`, 404);
    }
    // track.audio_name: anything outside A-Za-z0-9 ._()- becomes _, at most
    // 120 characters, and only the extension is lowercased (spaces are kept)
    const dot = name.lastIndexOf(".");
    const safe = name.slice(0, dot).replace(/[^A-Za-z0-9 ._()-]+/g, "_").slice(0, 120) + name.slice(dot).toLowerCase();
    // already inside the episode: used where it is
    const inside = !upload && inEp;
    const path = inside ? source.replace(/\\/g, "/") : `audio/${safe}`;
    const same = path === trackPath;
    trackPath = path;
    // a recording the editor just attached has no transcript beside it yet
    if (!same) { trackWords = false; trackVocals = false; }
    emit("seriesmith.episode", { ep: EP });
    return {
      track: trackInfo(pass),
      hash: mockHash(`${files.series.text}|${path}`),
      build: buildNow(),
      path,
      copied: !inside,
      reformatted: false,
    };
  }

  /**
   * The build after a track change. With a recording attached, every dialogue
   * shot is a dub, so the FINAL build fails while the script has no `audio:`
   * windows — the editor shows that as "align to finish".
   */
  function buildNow(): BuildResult {
    const report = `  ep05.md -> shotlist/shotlist.json\n  ${fx.summary.shots} shots, 0 warnings\n`;
    const spoken = (status.proxy ?? status.final)!.shots.filter((s) => !s.orphan && !SILENT.has(s.shot));
    const missing = trackPath && spoken.every((s) => !windows[s.shot]) ? spoken[0] : null;
    if (missing) {
      const error = `shot ${missing.shot}: policy dub_keep_foley needs an \`audio: in-out\` window (run align)`;
      return { ok: false, passes: { final: { ok: false, report: "", error }, proxy: { ok: false, report: "", error } } };
    }
    return {
      ok: true,
      passes: {
        final: { ok: true, report, error: "" },
        proxy: { ok: true, report: report.replace("shotlist.json", "shotlist_proxy.json"), error: "" },
      },
    };
  }

  const align = createMockAlign({
    ep: EP,
    emit: (event, detail) => emit(event, detail),
    wait: (ms) => wait(ms),
    shots: () => (status.proxy ?? status.final)!.shots
      .filter((s) => !s.orphan)
      .map((s) => ({ shot: s.shot, seconds: (s.length ?? 72) / 24, dialogue: !SILENT.has(s.shot) })),
    track: () => (trackPath ? { path: trackPath, duration: track.duration, words: trackWords } : null),
    write: (w) => {
      windows = Object.fromEntries(Object.entries(w).map(([shot, x]) => [shot, { shot, ...x }]));
    },
    cached: (w) => {
      trackWords = w;
    },
  });

  /** The dev page's `h3mockUnalign()`: the script loses its `audio:` windows,
   * so attaching a recording shows the "align to finish" build. */
  function unalign() {
    windows = {};
  }

  /** the promote plan's inputs, now */
  function promoteInput(only: string | null) {
    const shots = shotIds.map((shot) => ({
      shot, final: clone(detail.final?.[shot]?.override ?? {}), proxy: clone(detail.proxy?.[shot]?.override ?? {}),
    })).filter((s) => Object.keys(s.final).length || Object.keys(s.proxy).length);
    return {
      script: files.script.text, series: files.series.text, scriptName, shots, episodeTarget,
      refOverrides: refs.overrideList(), only,
    };
  }

  /** takeimport, mocked: a finished take of `shot` from a file or another take
   * (its pictures borrowed from one already there), picked if asked. */
  async function mockImportTake(pass: Pass, shot: string, name: string | null, pick: boolean,
    copied: { shot: string; take: number; pass: Pass; src: TakeSummary } | null): Promise<ImportedShotTake> {
    await wait(300);
    const s = shotSt(pass, shot);
    const take = (s.takes[s.takes.length - 1]?.take ?? 0) + 1;
    const like = copied?.src ?? st(pass).shots.flatMap((x) => x.takes).find((t) => t.status === "ok" && t.has_video);
    const now = new Date().toISOString();
    const note = copied ? `from ${copied.shot} t${String(copied.take).padStart(2, "0")}` : "";
    const sum: TakeSummary = {
      take, status: "ok", has_video: true, seed: null, seed_source: null, note, overrides: [], stale: [],
      thumb: like?.thumb ?? null, strip: like?.strip ?? null, mp4: like?.mp4 ?? null, queued: now, finished: now,
      save_notes: copied ? `copied from ${copied.shot} t${copied.take} (${copied.pass})` : `uploaded as ${name}`,
      target: null, frames: like?.frames ?? 72, fps: like?.fps ?? 24,
      source: "imported", original_name: copied ? null : name,
      copied_from: copied ? { shot: copied.shot, take: copied.take, pass: copied.pass } : null,
    };
    s.takes.push(sum);
    const sidecar = { status: "ok", source: "imported", shot, take, pass, note, seed: null,
      ...(copied ? { copied_from: { shot: copied.shot, take: copied.take, pass: copied.pass } } : { original_name: name }) };
    det(pass, shot).takes.push({ take, status: "ok", has_video: true, stale: [], sidecar: sidecar as unknown as TakeDetail["sidecar"], files: {} });
    let picked = false;
    if (pick) {
      const list = materialize(cut[pass], pass, scriptOrder[pass]);
      const entry = list.find((c) => c.shot === shot);
      if (entry && !entry.locked) {
        entry.take = take;
        cut[pass] = list;
        recut(pass);
        picked = true;
      }
    }
    emit("seriesmith.take", { ep: EP, pass, shot, take, status: "ok", thumb: sum.thumb });
    emit("seriesmith.episode", { ep: EP });
    return { shot, take, pass, status: "ok", sidecar: sidecar as unknown as ImportedShotTake["sidecar"], mp4: sum.mp4, thumb: sum.thumb, picked };
  }

  const api: Api = {
    fetch: (path: string, init?: RequestInit) => fetch(path, init),
    async getConfig() {
      await wait();
      return { roots: [...roots], comfy: "http://127.0.0.1:8188", version: 1 };
    },
    async putConfig(r) {
      await wait();
      if (r.some((x) => !x.trim())) throw new MockError("A root can't be empty.", 400);
      const bad = r.find((x) => !fsExists(x));
      if (bad) throw new MockError(`${bad} doesn't exist (the mock knows C:\\Shows, C:\\Users\\bgstr, D:\\Stock…).`, 400);
      roots = [...r];
      return { roots: [...roots], comfy: "http://127.0.0.1:8188", version: 1 };
    },
    async episodes() {
      await wait();
      return [
        // the fixture episode is the mock's Clips project too (clipsEnsure)
        ...(reachable(EP, roots) ? [{ ...clone(fx.summary), simple: true }] : []),
        ...made.filter((m) => reachable(m.ep, roots)).map(madeSummary),
      ];
    },
    async episode(ep, pass) {
      await wait();
      need(ep);
      const m = made.find((x) => x.ep === ep);
      if (m) return emptyStatus(m, pass);
      return with9b(withMissing(clone(st(pass))));
    },
    async shot(ep, pass, shot, target) {
      await wait();
      need(ep);
      const d = clone(det(pass, shot));
      refs.list(); // the keyframe needs follow the shot's target
      d.refs_used = refsUsedOf(shot, target || shotTargetOf(shot, d.override).target);
      // P9: what the build compiled, for the inspector to show an override
      // against. Only when there is an override -- as the server does.
      if (Object.keys(d.override ?? {}).length) {
        const p = preset(d.built_target ?? shotTargetOf(shot, {}).target, pass);
        d.built_values = {
          ...d.effective,
          target: d.built_target ?? d.effective.target,
          steps: p?.steps ?? d.effective.steps,
          model: p?.model ?? d.effective.model,
          loras: p?.lora ? [{ name: p.lora, strength: 1 }] : [],
          width: p?.width ?? d.effective.width,
          height: p?.height ?? d.effective.height,
          prompt: d.built_prompt,
          seed_source: "stable",
        };
      }
      // P9: a one-off target sizes the answer the way a render on it would --
      // its preset's size, and the shot's length on ITS frame grid
      if (target) {
        const p = preset(target, pass);
        d.effective = {
          ...d.effective,
          target,
          steps: p?.steps ?? d.effective.steps,
          model: p?.model ?? d.effective.model,
          width: p?.width ?? d.effective.width,
          height: p?.height ?? d.effective.height,
          length: targetLength(target, d.effective.length ?? 0),
        };
      }
      return d;
    },
    // the gallery's zip of a selection: the mock has no files to zip
    async download(ep, paths, name) {
      await wait();
      need(ep);
      return { id: "0".repeat(32), name: `${name || "mock"}.zip`, files: paths.length, bytes: 0 };
    },
    downloadUrl: (id: string) => `/mock/download/${id}.zip`,
    // the gallery's one take: its sidecar, and the shot's prompt and refs as
    // what it was made with (the mock keeps no frozen shotlists)
    async take(ep, pass, shot, take) {
      await wait();
      need(ep);
      const d = det(pass, shot);
      const t = d.takes.find((x) => x.take === take);
      if (!t) throw new MockError(`${shot} has no take ${take} in the ${pass} pass`, 404);
      return clone({
        shot, pass, take, status: t.status, has_video: t.has_video, sidecar: t.sidecar ?? {},
        prompt: d.built_prompt,
        refs: refsUsedOf(shot, shotTargetOf(shot, d.override).target).map((r) => ({
          id: r.id, kind: r.kind, role: r.role, slot: r.slot ?? null, path: r.path, sha1: null, exists: r.exists,
        })),
        reference_image: t.reference_image ?? null, files: t.files,
      });
    },
    async build(ep) {
      await wait(900);
      need(ep);
      const report = `  ep05.md -> shotlist/shotlist.json\n  ${fx.summary.shots} shots, 0 warnings\n`;
      emit("seriesmith.episode", { ep: EP });
      return {
        ok: true,
        passes: {
          final: { ok: true, report, error: "" },
          proxy: { ok: true, report: report.replace("shotlist.json", "shotlist_proxy.json"), error: "" },
        },
      };
    },
    // P5: a new episode from a template. No filesystem here, so the mock keeps
    // the folder in memory and lists it as what it would be: unbuilt, no shots.
    async importSeries(req) {
      return { show: req.parent, episodes: [], skipped: [],
               errors: [{ file: "", error: "the mock doesn't import series" }] };
    },
    // an edit's import: a dry run answers a made-up summary; the mock writes nothing
    async importXml(req) {
      return mockXmlImport(Boolean(req.dry_run), req.media ?? "handles", req.name ?? null);
    },
    async uploadXml(req) {
      return mockXmlImport(Boolean(req.dry_run), req.media ?? "handles", req.name ?? null);
    },
    async newEpisode(req) {
      await wait(400);
      if (!roots.length) throw new MockError("No project roots are configured.", 403);
      if (!req.parent || !insideRoot(req.parent, roots)) {
        throw new MockError(`${req.parent} is not inside a configured root`, 403);
      }
      const bad = nameError(req.name ?? "");
      if (bad) throw new MockError(bad, 400);
      const name = req.name.trim();
      const sep = req.parent.includes("\\") ? "\\" : "/";
      const parent = req.show ? `${req.parent.replace(/[\\/]+$/, "")}${sep}${req.show}` : req.parent;
      const ep = `${parent.replace(/[\\/]+$/, "")}${sep}${name}`;
      if (ep === EP || made.some((m) => m.ep === ep) || fsExists(ep)) {
        throw new MockError(`${ep} is already there`, 409);
      }
      const first = !fsExists(`${req.parent.replace(/[\\/]+$/, "")}${sep}ep01`) && !made.length;
      const m = { ep, name, title: req.title?.trim() || fx.summary.series };
      made.push(m);
      emit("seriesmith.episode", { ep });
      return {
        ep, template: req.series ? "form" : first ? "starter" : "episode",
        from: first ? "examples/starter" : EP,
        files: ["series.json", `${name}.md`],
        refs: `${req.parent.replace(/[\\/]+$/, "")}${sep}refs`,
        check: { ok: true, errors: [], warnings: [], shots: [] },
        episode: madeSummary(m),
      };
    },
    fileUrl(_ep, path) {
      const pic = refs.image(path); // a reference sheet a take kept
      if (pic) return pic;
      // Phase 9b: the synthetic dialogue track (a real clip's sound outside a browser)
      if (path === TRACK_PATH) return track.url() ?? media + "sh010_t01.mp4";
      // Phase 9d: a loose media file inside the episode, for a clip's audio
      const clip = clipFiles.get(path.replace(/\\/g, "/"));
      if (clip) return clip.url() ?? media + "sh010_t01.mp4";
      // Phase 9c-B: a voice candidate's synthetic wav
      const wav = refs.audio(path);
      if (wav) return wav;
      const real = alias.get(path) ?? path;
      return media + real.split("/").pop();
    },
    async readJson<T>(ep: string, path: string) {
      await wait();
      need(ep);
      const doc = fx.shotlist[path] ?? fx.shotlist[alias.get(path) ?? ""];
      if (!doc) throw new MockError(`No such file: ${path}`, 404);
      return clone(doc) as T;
    },
    async render(req) {
      await wait();
      need(req.ep);
      const out: RenderResult = { queued: [], skipped: [], errors: [] };
      for (const shot of req.shots) {
        let s: ShotStatus;
        try {
          s = shotSt(req.pass, shot);
        } catch (e) {
          out.errors.push({ shot, error: (e as Error).message });
          continue;
        }
        const d = det(req.pass, shot);
        // a target that isn't ready blocks the shot before a take is reserved
        const runOn = req.target || shotTargetOf(shot, d.override).target;
        const blockers = mockReadiness(runOn).missing.filter((m) => m.tier === "required");
        if (blockers.length) {
          out.skipped.push({
            shot,
            target: runOn,
            reason: `required file missing for ${runOn}: ${blockers.map((m) => `${m.want} (models/${m.folder})`).join(", ")}`,
            missing_files: blockers,
          });
          continue;
        }
        refs.list();
        const missing = [...seriesMissing(shot), ...keyframeMissing(shot)];
        // a required keyframe can't be rendered anyway (Wan I2V has nothing to start from)
        if (missing.length && (!req.allow_missing_refs || missing.some((m) => m.anyway === false))) {
          out.skipped.push({
            shot,
            reason: `missing refs: ${missing.map((m) => `${m.slot} (${m.path})`).join(", ")}; pass allow_missing_refs to render anyway`,
            missing_refs: missing,
          });
          continue;
        }
        if (!req.redo) {
          if (s.takes.some((t) => t.status === "queued")) { out.skipped.push({ shot, reason: "has a queued take" }); continue; }
          if (s.takes.some((t) => t.status === "ok" && t.has_video)) { out.skipped.push({ shot, reason: "has a usable take (pass redo: true)" }); continue; }
        }
        const take = (s.takes[s.takes.length - 1]?.take ?? 0) + 1;
        const cur = effectiveOf(req.pass, shot);
        // Phase 8: a one-off target beats the override; another target brings its
        // own prompt and defaults, and a prompt written for H3 doesn't apply
        const target = req.target || cur.target || H3;
        const p = preset(target, req.pass);
        const eff = target === cur.target ? cur : {
          ...cur, target, prompt: target === H3 ? d.built_prompt : ltxPrompt(d.built_prompt),
          model: p?.model ?? cur.model, loras: null, steps: p?.steps ?? cur.steps,
        };
        const prompt = target === H3 ? req.prompt ?? eff.prompt : eff.prompt;
        // a model file of another family is skipped unless allowed (jobs.check_models)
        const bad = mockModelFiles(target, "model")?.files.find((f) => f.name === (req.model ?? eff.model) && f.mismatch);
        if (bad && !req.allow_model_mismatch) {
          out.skipped.push({
            shot,
            reason: `model mismatch: ${bad.detail} (pass allow_model_mismatch: true to render anyway)`,
            model_mismatch: [{ param: "model", file: bad.name, family: bad.family ?? "", label: bad.label, message: bad.detail }],
          });
          continue;
        }
        let seed: string;
        let src: string;
        if (req.seed != null) { seed = req.seed; src = "typed"; }
        else if (d.override.seed != null && req.seed_mode !== "new") { seed = d.override.seed; src = "override"; }
        else if (req.seed_mode === "same") { seed = String(d.built.seed); src = "same"; }
        else if (req.seed_mode === "new" || (req.seed_mode === "auto" && s.takes.length)) { seed = randomSeed(); src = "new"; }
        else { seed = String(d.built.seed); src = "stable"; }
        const pid = `mock-${nextPrompt++}-${shot}`;
        const now = new Date().toISOString();
        const overrides = Object.keys(d.override).filter((k) => k !== "note" && (req as unknown as Record<string, unknown>)[k] == null);
        const sum: TakeSummary = {
          take, status: "queued", has_video: false, seed, seed_source: src, note: req.note ?? "",
          overrides, stale: [], thumb: null, strip: null, mp4: null, queued: now, finished: null, save_notes: "", target,
        };
        s.takes.push(sum);
        const loras: Lora[] | null = req.loras ?? eff.loras;
        const td: TakeDetail = {
          take, status: "queued", has_video: false, stale: [],
          sidecar: {
            target, status: "queued", queued: now, comfy_prompt_id: pid, seed, seed_source: src,
            model: req.model ?? eff.model, loras, steps: req.steps ?? eff.steps, overrides,
            parent_take: req.parent_take, note: req.note ?? "", shot, take, pass: req.pass,
            ...(missing.length ? { missing_refs: missing.map((m) => m.slot) } : {}),
            resolved: mockTakeResolved(target),
          },
          files: {},
        };
        d.takes.push(td);
        // the frozen shotlist, so "redo from this take" can read its prompt
        const stem = `${st(req.pass).folder}/${shot}/${shot}_t${String(take).padStart(2, "0")}`;
        fx.shotlist[`${stem}.shotlist.json`] = { shots: [{ prompt }] };
        td.files.shotlist = `${stem}.shotlist.json`;
        out.queued.push({ shot, take, prompt_id: pid, seed, seed_source: src, target });
        emit("seriesmith.take", { ep: EP, pass: req.pass, shot, take, status: "queued", thumb: null });
        simulate(req.pass, shot, take, pid);
      }
      return out;
    },
    async cancel(ref) {
      await wait();
      need(ref.ep);
      const s = shotSt(ref.pass, ref.shot);
      const t = s.takes.find((x) => x.take === ref.take);
      if (!t) throw new MockError(`${ref.shot} has no take ${ref.take}`, 404);
      if (t.status !== "queued") throw new MockError(`${ref.shot} t${ref.take} isn't queued (${t.status})`, 409);
      t.status = "failed";
      t.save_notes = "cancelled";
      const td = det(ref.pass, ref.shot).takes.find((x) => x.take === ref.take);
      if (td) td.status = "failed";
      emit("execution_interrupted", { prompt_id: String(td?.sidecar?.comfy_prompt_id ?? "") });
      emit("seriesmith.take", { ...ref, status: "failed", thumb: null });
      t.finished = new Date().toISOString();
      return { shot: ref.shot, pass: ref.pass, take: ref.take, status: "failed", save_notes: "cancelled", finished: t.finished };
    },
    async discard(ref) {
      await wait();
      need(ref.ep);
      const s = shotSt(ref.pass, ref.shot);
      const i = s.takes.findIndex((x) => x.take === ref.take);
      if (i < 0) throw new MockError(`${ref.shot} has no ${ref.pass} take ${ref.take}`, 404);
      const t = s.takes[i];
      if (t.status === "queued") throw new MockError(`${ref.shot} t${String(ref.take).padStart(2, "0")} is queued: cancel it first`, 409);
      // the files' new paths, under _trash/
      const stem = `${st(ref.pass).folder}/${ref.shot}/${ref.shot}_t${String(ref.take).padStart(2, "0")}`;
      const moved = [t.mp4, t.thumb, t.strip, `${stem}.json`].filter((x): x is string => !!x)
        .map((p) => p.replace(`${st(ref.pass).folder}/`, `${st(ref.pass).folder}/_trash/`));
      s.takes.splice(i, 1);
      const d = det(ref.pass, ref.shot);
      d.takes = d.takes.filter((x) => x.take !== ref.take);
      // a pick of that take goes (the entry stays where it is: back to the latest usable)
      let changed = false;
      cut[ref.pass] = cut[ref.pass].map((c) => {
        if (c.shot !== ref.shot || c.take !== ref.take) return c;
        changed = true;
        const { take: _t, ...rest } = c;
        return rest;
      });
      recut(ref.pass);
      emit("seriesmith.episode", { ep: EP });
      return { shot: ref.shot, take: ref.take, pass: ref.pass, moved, cut_changed: changed };
    },
    async pick(req) {
      await wait();
      need(req.ep);
      const from = req.from_pass ?? req.pass;
      shotSt(req.pass, req.shot);
      const s = shotSt(from, req.shot);
      // takes.pick: the whole resolved order goes into the file, this entry's take changed
      const list = materialize(cut[req.pass], req.pass, scriptOrder[req.pass]);
      const entry = list.find((c) => c.shot === req.shot)!;
      if (entry.locked && !req.force) {
        throw new MockError(`${req.shot} is locked in the ${req.pass} cut: unlock it, or force the pick`, 409, { error: `${req.shot} is locked`, locked: true });
      }
      if (req.take != null) {
        const t = s.takes.find((x) => x.take === req.take);
        if (!t) throw new MockError(`${req.shot} has no take ${req.take}`, 404);
        if (!(t.status === "ok" && t.has_video) && !req.force) {
          throw new MockError(`${req.shot} t${String(req.take).padStart(2, "0")} is ${t.status}${t.has_video ? "" : " with no mp4"}`, 409);
        }
        entry.take = req.take;
      } else {
        delete entry.take;
      }
      if (from !== req.pass) entry.pass = from;
      else delete entry.pass;
      cut[req.pass] = list;
      recut(req.pass);
      emit("seriesmith.episode", { ep: EP });
      return { cut: { episode: "ep05", ...cut } };
    },
    async putCut(ep, pass, entries) {
      await wait();
      need(ep);
      cut[pass] = clone(checkEntries(entries, st(pass).fps || 24, (e) => entryFrames(pass, e), (shot, a) => audioSourceFile(shot, a)));
      recut(pass);
      emit("seriesmith.episode", { ep: EP });
      return { cut: { episode: "ep05", ...clone(cut) } };
    },
    async getMix(ep, pass) {
      await wait();
      need(ep);
      return { mix: clone(mixes[pass] ?? {}), series: {}, defaults: clone(MIX_DEFAULTS), voices: mockVoices(pass) };
    },
    async makeVoices(req) {
      await wait();
      need(req.ep);
      const rows = mockVoices(req.pass).shots;
      const want = req.shots ?? rows.map((r) => r.shot);
      const queued: { shot: string; take: number; job: string }[] = [];
      const skipped: { shot: string; why: string }[] = [];
      for (const shot of want) {
        const r = rows.find((x) => x.shot === shot);
        if (!r || r.take == null) skipped.push({ shot, why: "it isn't in the cut" });
        else if (r.state === "ok" && !req.redo) skipped.push({ shot, why: "its voice stem is made" });
        else {
          voiceStems.add(`${req.pass}:${shot}:${r.take}`);
          queued.push({ shot, take: r.take, job: `voice-${shot}` });
        }
      }
      if (queued.length) emit("seriesmith.episode", { ep: EP });
      return { queued, skipped };
    },
    async putMix(ep, pass, mix) {
      await wait();
      need(ep);
      if (pass !== "final" && pass !== "proxy") throw new MockError(`pass must be final or proxy`, 400);
      const checked = checkMix(mix);
      for (const it of checked.items ?? []) {
        if (/^([\\/]|[a-zA-Z]:)/.test(it.path) || it.path.split("/").includes("..")) throw new MockError(`${it.path} is outside the episode`, 400);
        if (mediaSeconds(it.path) == null) throw new MockError(`No such file: ${it.path}`, 404);
      }
      const changed = JSON.stringify(checked) !== JSON.stringify(mixes[pass]);
      mixes[pass] = checked;
      if (changed) emit("seriesmith.episode", { ep: EP });
      return { mix: clone(checked) };
    },
    async getMixDuck(ep, pass) {
      await wait();
      need(ep);
      return speechCurve(cuePlaylist(pass));
    },
    async cues(ep, pass) {
      await wait();
      need(ep);
      return { cues: [...cueSpecs.values()].sort((a, b) => a.id.localeCompare(b.id)).map((spec) => {
        const ts = cueTakes.get(spec.id) ?? [];
        const row: CueSummary = { spec: clone(spec), takes: ts.length, ok: ts.filter((t) => t.status === "ok").length,
                                  placed: [...new Set(ts.map((t) => t.placed).filter((p): p is Pass => !!p))].sort() };
        if (!pass) return row;
        // planned against the pass: its tempo, the take its mix item plays, what's stale (the takes' own stale words)
        const item = (mixes[pass]?.items ?? []).find((i) => i.id === spec.id);
        const m = item?.path.match(/^sound\/[^/]+\/t(\d{2,3})\.wav$/);
        const inMix = m ? Number(m[1]) : null;
        const done = ts.filter((t) => t.status === "ok");
        try {
          row.bpm = cuePlan(spec, pass).fit.bpm;
          row.plan_error = null;
        } catch (e) {
          if (!(e instanceof CueError)) throw e;
          return { ...row, bpm: null, in_mix: inMix, stale: [], stale_takes: [], plan_error: e.message };
        }
        return { ...row, in_mix: inMix, stale: [...(done.find((t) => t.take === inMix)?.stale ?? [])],
                 stale_takes: done.filter((t) => t.stale?.length).map((t) => t.take) };
      }) };
    },
    async getCue(ep, pass, cue) {
      await wait();
      need(ep);
      const spec = cueSpecs.get(cue);
      if (!spec) throw new MockError(`no cue ${cue}`, 404);
      let plan = null;
      let why: string | null = null;
      try {
        plan = cuePlan(spec, pass);
      } catch (e) {
        if (!(e instanceof CueError)) throw e;
        why = e.message;
      }
      return { spec: clone(spec), plan, plan_error: why, takes: clone(rankedTakes(cue)), themes: clone(SERIES_THEMES) };
    },
    async putCue(ep, cue) {
      await wait();
      need(ep);
      const spec = checkCue(cue);
      cueSpecs.set(spec.id, spec);
      emit("seriesmith.episode", { ep: EP });
      return { spec: clone(spec) };
    },
    async structures() {
      await wait();
      return { structures: [
        { id: "5.1", name: "The Pixar Story Spine", beats: ["Once upon a time…", "Every day…", "Until one day…", "Because of that…", "Until finally…", "And ever since then…", "(And the moral is…)"] },
        { id: "2.1", name: "The Sitcom Formula (Circular Structure)", beats: ["Cold Open / Teaser", "Status Quo", "The Problem"] },
      ] };
    },
    async storyboardBlock(structure, duration, shot = 3.5) {
      await wait();
      if (!(duration > 0) || !(shot > 0)) throw new MockError("the episode needs a duration above zero", 400);
      // seriesmith/core/blocking.py in small: one shape, whatever the structure
      const shape: [string, [string, number][]][] = [
        ["I: Setup", [["Opening", 10], ["Inciting Incident", 2], ["Debate", 8], ["Plot Point 1", 5]]],
        ["II: Confrontation", [["Rising Complications", 25], ["Pressure Mounts", 25]]],
        ["III: Resolution", [["Plot Point 2", 5], ["Climax", 15], ["Final Image", 5]]],
      ];
      const wanted = Math.max(9, Math.round(duration / shot));
      const each = duration / wanted;
      let at = 0;
      let from = 0;
      const acts = shape.map(([act, beats]) => {
        const out = beats.map(([beat, width]) => {
          const shots = Math.max(1, Math.round(width / 100 * wanted));
          const b = { beat, act, guidance: `What happens in ${beat}.`, shots, seconds: shots * each, first_shot: at,
            thin: width / 100 * wanted < 1.5, at: [from, from + width] as [number, number] };
          at += shots;
          from += width;
          return b;
        });
        return { act, shots: out.reduce((n, b) => n + b.shots, 0), seconds: out.reduce((n, b) => n + b.seconds, 0), beats: out };
      });
      return { structure, duration, shot_seconds: each, wanted_shots: wanted, shots: at, warnings: [], acts };
    },
    async saveStructure() {
      await wait();
      return { own_file: "structures.json" };
    },
    async deleteStructure() {
      await wait();
      return { own_file: "structures.json" };
    },
    async storyboard(_ep, structure) {
      await wait();
      return { hash: "mock", plan: { id: "ep01", title: "Mock", structure, structure_known: true, duration: null, shots: 0, seconds: 0,
        untimed: 0, target_shots: null, shot_seconds: null, warnings: [], acts: [] } };
    },
    async storyboardSketch() {
      await wait();
      return { queued: [], skipped: [], errors: [], step: null };
    },
    async storyboardEdit(req) {
      await wait();
      return { hash: "mock", made: [], plan: { id: "ep01", title: "Mock", structure: req.structure, structure_known: true, duration: req.duration,
        shots: 0, seconds: 0, untimed: 0, target_shots: null, shot_seconds: null, warnings: [], acts: [] } };
    },
    async scoreDraft(req) {
      await wait();
      need(req.ep);
      // seriesmith/scoredraft.py in small: the first shots as one beat-joined cue that makes the story theme
      const shots = status[req.pass]?.shots ?? [];
      if (shots.length < 2) throw new MockError("the episode isn't built (shotlist/shots.json): build it first", 409);
      const drafted = [...cueSpecs.keys()].filter((k) => /^d\d{2,3}$/.test(k));
      const last = shots[Math.min(3, shots.length - 1)].shot;
      const spec: CueSpec = {
        id: "d01", label: "Draft: Once upon a time… → Every day…", in: { shot: shots[0].shot, frame: 0 }, out: { shot: last, frame: 96 },
        sections: [{ name: "Once upon a time…", from: 2, to: 2, bars: 4, words: "gentle, wondering" },
                   { name: "Every day…", from: 2, to: 2, bars: 6, words: "light, a simple repeating figure: the routine" }],
        hits: ["dh01"],
      };
      const draft: import("../types").ScoreDraft = {
        structure: "The Pixar Story Spine", pass: req.pass, missing: [], voices_only: false, drafted, kept: [], rendered: !!req.rendered,
        marked: true, laid: null, structures: [{ id: "5.1", name: "The Pixar Story Spine" }, { id: "2.1", name: "The Sitcom Formula (Circular Structure)" }],
        beats: [{ beat: "Once upon a time…", from: "structure", music: "score", t0: 0, t1: 8, shot: shots[0].shot },
                { beat: "Every day…", from: "structure", music: "under", t0: 8, t1: 20, shot: shots[1].shot }],
        cues: [{ kind: "cue", label: "Once upon a time… → Every day…", id: "d01", t0: 0, t1: 20, theme: null, makes: "story",
                 sections: [{ name: "Once upon a time…", words: "gentle, wondering", from: 2, to: 2, seconds: 8 },
                            { name: "Every day…", words: "light, a simple repeating figure: the routine", from: 2, to: 2, seconds: 12 }],
                 hits: [{ kind: "turn", shot: shots[1].shot, name: "Every day…: turn" }], spec }],
        flags: [{ kind: "in-scene", shot: shots[1].shot, text: "music in the scene (\"radio\"): the score sits out, or takes up its tune" }],
        notes: [],
      };
      const text = "The Pixar Story Spine: 2 beat(s), 1 cue(s)";
      if (!req.write) return { draft, text, written: null };
      if (drafted.length && !req.replace) throw new MockError(`the episode has a draft already (${drafted.join(", ")}): replace it, or delete those cues first`, 409);
      for (const k of drafted) { cueSpecs.delete(k); cueTakes.delete(k); }
      cueSpecs.set("d01", spec);
      const m = mixes[req.pass];
      mixes[req.pass] = { ...m, hits: [...(m.hits ?? []).filter((h) => !/^dh\d+$/.test(h.id)), { id: "dh01", name: "Every day…: turn", at: { shot: shots[1].shot, frame: 0 }, kind: "turn", must: false }],
                          ...(req.keep_sound ? {} : { tracks: { ...m.tracks, dialogue: { ...m.tracks?.dialogue, voices_only: true } } }) };
      emit("seriesmith.episode", { ep: EP });
      return { draft, text, written: { cues: ["d01"], hits: 1, removed: drafted, voices_only: !req.keep_sound } };
    },
    async deleteCue(ep, cue) {
      await wait();
      need(ep);
      const spec = cueSpecs.get(cue);
      if (!spec) throw new MockError(`no cue ${cue}`, 404);
      const ts = cueTakes.get(cue) ?? [];
      if (ts.some((t) => t.status === "queued")) throw new MockError(`${cue} has takes queued or rendering: cancel them in Jobs first`, 409);
      const users = [...cueSpecs.values()].filter((c) => c.id !== cue && c.theme && "cue" in c.theme && c.theme.cue === cue).map((c) => c.id);
      if (users.length) throw new MockError(`${cue} is the theme of ${users.join(", ")}: give it another theme first`, 409);
      const changed: Pass[] = [];
      for (const pass of ["final", "proxy"] as Pass[]) {
        const items = mixes[pass].items ?? [];
        const kept = items.filter((i) => i.id !== cue && !i.path.startsWith(`sound/${cue}/`));
        if (kept.length === items.length) continue;
        const m: import("../types").Mix = { ...mixes[pass], items: kept };
        if (!kept.length) delete m.items;
        mixes[pass] = m;
        changed.push(pass);
      }
      cueSpecs.delete(cue);
      cueTakes.delete(cue);
      emit("seriesmith.episode", { ep: EP });
      return { cue, moved_to: `_history/cue-${cue}.20261102-120000`, takes: ts.length, mixes: changed };
    },
    async renderCue(req) {
      await wait();
      need(req.ep);
      const spec = cueSpecs.get(req.cue);
      if (!spec) throw new MockError(`no cue ${req.cue}`, 404);
      try {
        cuePlan(spec, req.pass);
      } catch (e) {
        if (e instanceof CueError) throw new MockError(e.message, 400);
        throw e;
      }
      const list = cueTakes.get(req.cue) ?? [];
      cueTakes.set(req.cue, list);
      const n = req.takes ?? spec.takes ?? 8;
      const queued: { take: number; job: string; seed: number }[] = [];
      for (let k = 0; k < n; k++) {
        const take = Math.max(0, ...list.map((t) => t.take)) + 1;
        const seed = (spec.seed ?? 5000) + list.length;
        const t: CueTake = { take, status: "queued", seed, target: spec.model ?? "stable_audio3", pass: req.pass, created: new Date().toISOString() };
        list.push(t);
        queued.push({ take, job: `cue-${req.cue}-${take}`, seed });
        // each lands a little after the last, as the queue runs them
        setTimeout(() => {
          if (!cueSpecs.has(req.cue)) return;
          try {
            cueTakeDone(req.cue, t, req.pass);
          } catch (e) {
            t.status = "failed";
            t.error = e instanceof Error ? e.message : String(e);
          }
          emit("seriesmith.cue", { ep: EP, cue: req.cue, take, status: t.status });
          emit("seriesmith.episode", { ep: EP });
        }, (opts.latency ?? 120) * 4 + 400 * (k + 1));
      }
      emit("seriesmith.episode", { ep: EP });
      return { queued };
    },
    async pinCueTheme(req) {
      await wait();
      need(req.ep);
      const t = (cueTakes.get(req.cue) ?? []).find((x) => x.take === req.take);
      if (!cueSpecs.get(req.cue)) throw new MockError(`no cue ${req.cue}`, 404);
      if (!t || t.status !== "ok") throw new MockError(`cue ${req.cue} has no finished take ${req.take} to make a theme of`, 409);
      if (!/^[A-Za-z0-9_-]{1,40}$/.test(req.name)) throw new MockError(`a series theme's name is 1-40 letters, digits, _ or -, not ${JSON.stringify(req.name)}`, 400);
      const theme = { name: req.name, ep: "ep01", cue: req.cue, take: req.take, ...(req.role ? { role: req.role } : {}), ...(req.words ? { words: req.words } : {}), ...(req.for?.length ? { for: req.for } : {}) };
      const row = { name: req.name, label: `${req.name} (ep01 ${req.cue} t${String(req.take).padStart(2, "0")})`, role: (req.role ?? null) as SeriesTheme["role"],
                    words: req.words ?? null, for: req.for ?? null, error: null };
      const i = SERIES_THEMES.findIndex((x) => x.name === req.name);
      if (i >= 0) SERIES_THEMES[i] = row; else SERIES_THEMES.push(row);
      return { theme, written: req.everywhere === false ? ["ep01"] : ["ep01", "ep02"], same: [] };
    },
    async pickCue(req) {
      await wait();
      need(req.ep);
      const spec = cueSpecs.get(req.cue);
      const t = (cueTakes.get(req.cue) ?? []).find((x) => x.take === req.take);
      if (!spec) throw new MockError(`no cue ${req.cue}`, 404);
      if (!t || t.status !== "ok" || !t.measured || !t.file) throw new MockError(`cue ${req.cue} has no finished take ${req.take}`, 409);
      const p = cuePlan(spec, req.pass);
      const mix = clone(mixes[req.pass] ?? {});
      const items = (mix.items ?? []).filter((i) => i.id !== req.cue);
      items.push({ id: req.cue, track: "music", path: t.file, in: spec.in, out: spec.out, offset: Math.round(t.measured.offset * 1000) / 1000,
                   fade_out: Math.max(1, Math.round(p.bar * p.fps)), label: spec.label || req.cue });
      mix.items = items;
      mixes[req.pass] = checkMix(mix);
      for (const x of cueTakes.get(req.cue) ?? []) if (x.placed === req.pass) delete x.placed;
      t.placed = req.pass;
      emit("seriesmith.episode", { ep: EP });
      return { mix: clone(mixes[req.pass]) };
    },
    async compCue(req) {
      await wait();
      need(req.ep);
      const spec = cueSpecs.get(req.cue);
      if (!spec) throw new MockError(`no cue ${req.cue}`, 404);
      const list = cueTakes.get(req.cue) ?? [];
      const [base, src] = [req.take, req.from].map((n) => list.find((x) => x.take === n));
      for (const [n, t] of [[req.take, base], [req.from, src]] as const) {
        if (!t || t.status !== "ok" || !t.measured) throw new MockError(`cue ${req.cue} has no finished take ${n}`, 409);
      }
      const p = cuePlan(spec, req.pass);
      const [a, b] = req.bars;
      if (!(Number.isInteger(a) && Number.isInteger(b) && 0 <= a && a < b && b <= p.bars)) throw new MockError(`bars ${a}-${b} aren't inside cue ${req.cue}'s ${p.bars}`, 409);
      const take = Math.max(0, ...list.map((t) => t.take)) + 1;
      const t: CueTake = {
        take, status: "ok", target: base!.target, pass: req.pass, comp: { base: req.take, from: req.from, bars: [a, b] },
        measured: compMeasured(p, base!.measured!, src!.measured!, [a, b]), file: cueFile(req.cue, take),
        created: new Date().toISOString(), finished: new Date().toISOString(), stale: [],
      };
      list.push(t);
      cueTakes.set(req.cue, list);
      clipFiles.set(t.file!, makeVoice(`cue|${req.cue}|${take}`, p.seconds + t.measured!.downbeat));
      emit("seriesmith.cue", { ep: EP, cue: req.cue, take, status: "ok" });
      emit("seriesmith.episode", { ep: EP });
      return { take: clone(t) };
    },
    async repaintCue(req) {
      await wait();
      need(req.ep);
      const spec = cueSpecs.get(req.cue);
      if (!spec) throw new MockError(`no cue ${req.cue}`, 404);
      const list = cueTakes.get(req.cue) ?? [];
      const base = list.find((x) => x.take === req.take);
      if (!base || base.status !== "ok" || !base.measured) throw new MockError(`cue ${req.cue} has no finished take ${req.take}`, 409);
      if (!MUSIC_TARGETS.find((x) => x.id === base.target)?.capabilities?.repaint) {
        throw new MockError(`${base.target} can't make bars of a take again (docs/SOUND.md 'Measured: repaint'): comp them from another take instead`, 409);
      }
      const p = cuePlan(spec, req.pass);
      const [a, b] = req.bars;
      if (!(Number.isInteger(a) && Number.isInteger(b) && 0 <= a && a < b && b <= p.bars)) throw new MockError(`bars ${a}-${b} aren't inside cue ${req.cue}'s ${p.bars}`, 409);
      const take = Math.max(0, ...list.map((t) => t.take)) + 1;
      const seed = req.seed ?? (spec.seed ?? 5000) + list.length;
      const codes = req.fresh ? seed : base.repaint?.codes ?? base.seed;
      const t: CueTake = {
        take, status: "queued", seed, target: base.target, pass: base.pass ?? req.pass, created: new Date().toISOString(),
        repaint: { from: req.take, bars: [a, b], ...(codes != null ? { codes } : {}), fresh: !!req.fresh },
      };
      list.push(t);
      cueTakes.set(req.cue, list);
      setTimeout(() => {
        if (!cueSpecs.has(req.cue)) return;
        // its bars made again (a little louder or softer), the rest the take's own
        const m = clone(base.measured!);
        m.levels = m.levels.map((lv, k) => (k >= a && k < b ? Math.round((lv + 1.5 - 3 * ((seed + k) % 2)) * 100) / 100 : lv));
        Object.assign(t, { status: "ok", measured: m, file: cueFile(req.cue, take), finished: new Date().toISOString(), stale: [],
          repaint_check: { beats: (b - a) * 4, on: (b - a) * 4 - (req.fresh ? 1 : 0), on_before: (b - a) * 4, median_ms: 3 } });
        clipFiles.set(t.file!, makeVoice(`cue|${req.cue}|${take}`, p.seconds + m.downbeat));
        emit("seriesmith.cue", { ep: EP, cue: req.cue, take, status: "ok" });
        emit("seriesmith.episode", { ep: EP });
      }, (opts.latency ?? 120) * 4 + 400);
      emit("seriesmith.episode", { ep: EP });
      return { queued: { take, job: `cue-${req.cue}-${take}`, seed } };
    },
    async cutReset(ep, pass, what) {
      await wait();
      need(ep);
      if (!["order", "trims", "audio", "all"].includes(what)) throw new MockError(`what must be order, trims, audio or all`, 400);
      st(pass);
      cut[pass] = resetEntries(cut[pass], pass, scriptOrder[pass], what);
      recut(pass);
      emit("seriesmith.episode", { ep: EP });
      return { cut: { episode: "ep05", ...clone(cut) } };
    },
    async cutCopy(ep, from, to, what) {
      await wait();
      need(ep);
      if (from === to) throw new MockError("from and to are the same pass", 400);
      // Phase 9d: audio comes with "all" only (`/cut/copy` takes no "audio")
      if (!["order", "trims", "all"].includes(what)) throw new MockError(`what must be order, trims or all`, 400);
      cut[to] = copyEntries(cut[from], from, st(from).fps || 24, cut[to], to, st(to).fps || 24, scriptOrder[to], what, (e) => entryFrames(to, e));
      recut(to);
      emit("seriesmith.episode", { ep: EP });
      return { cut: { episode: "ep05", ...clone(cut) } };
    },
    async peaks(ep, path, bins, start, end) {
      await wait(40);
      need(ep);
      if (/^([\\/]|[a-zA-Z]:)/.test(path) || path.split(/[\\/]/).includes("..")) throw new MockError(`${path} is outside the episode`, 400);
      const secs = mediaSeconds(path);
      if (secs == null) throw new MockError(`No such file: ${path}`, 404);
      // the track and a voice candidate have real peaks (their wav is synthetic
      // but playable); a video take's are made up from its path
      const clip = clipFiles.get(path.replace(/\\/g, "/"));
      if (clip && !(clip.duration > 0)) return { duration: 0, bins: 0, peaks: [], silent: true };
      const full = path === TRACK_PATH ? track.peaks() : clip ? clip.peaks() : refs.audioPeaks(path) ?? takePeaks(path, secs);
      return slicePeaks(full, secs, bins, start, end);
    },
    async uploadClipAudio(req) {
      await wait(500);
      need(req.ep);
      const name = (req.name || "audio.wav").replace(/[^A-Za-z0-9 ._()-]/g, "_");
      if (!/\.(wav|mp3|flac|ogg|m4a|aac|opus|mp4)$/i.test(name)) {
        throw new MockError(`${name} is not a media file (wav, mp3, flac, ogg, m4a, aac, opus, mp4)`, 400);
      }
      const size = (req.file as Blob | undefined)?.size ?? 0;
      if (size > UPLOAD_LIMIT) throw new MockError(`${name} is too big`, 413);
      const path = `audio/${name}`;
      // its length stands in for the real file's: enough to draw and play
      clipFiles.set(path, makeVoice(`clip|${name}`, 2 + (name.length % 7)));
      return { path };
    },
    async putOverride(req) {
      await wait();
      need(req.ep);
      const passes: Pass[] = req.both ? ["final", "proxy"] : [req.pass];
      for (const pass of ["final", "proxy"] as Pass[]) {
        const d = detail[pass]?.[req.shot];
        if (!d) continue;
        const ov: Override = d.override;
        for (const [k, v] of Object.entries(req.fields) as [keyof Override, unknown][]) {
          const shared = k === "seed" || k === "note" || k === "target";
          if (!shared && !passes.includes(pass)) continue;
          // the target the shot would have anyway (script, else episode) clears the retarget
          if (v === null || (k === "target" && v === shotTargetOf(req.shot, {}).target)) delete ov[k];
          else (ov as Record<string, unknown>)[k] = v;
          if (k === "prompt" && passes.includes(pass)) d.override_stale = false;
        }
      }
      syncOverrideSummary(req.shot);
      emit("seriesmith.episode", { ep: EP });
      return overrideResult(req.shot);
    },
    async deleteOverride(ep, shot, pass) {
      await wait();
      need(ep);
      for (const p of ["final", "proxy"] as Pass[]) {
        const d = detail[p]?.[shot];
        if (!d) continue;
        if (!pass) d.override = {};
        else if (p === pass) d.override = Object.fromEntries(Object.entries(d.override).filter(([k]) => k === "seed" || k === "note" || k === "target"));
        d.override_stale = false;
      }
      syncOverrideSummary(shot);
      emit("seriesmith.episode", { ep: EP });
      return overrideResult(shot);
    },
    async assemble(ep, pass, _partial, opts) {
      await wait(1500);
      need(ep);
      const n = st(pass).shots.filter((s) => s.cut.usable).length;
      const name = `ep05_${pass}${opts?.upscaled ? "_up" : ""}.${opts?.xml ? "xml" : "mp4"}`;
      const cut = `${st(pass).folder}/${name}`;
      if (opts?.publish) return { ok: true, output: `publish/${name}`, cut, published: `publish/${name}`, report: `  ${n} shots\n  -> publish/${name}\n` };
      return { ok: true, output: cut, report: `  ${n} shots, partial cut\n  wrote ${cut}\n` };
    },
    async upscale(req) {
      await wait();
      need(req.ep);
      const fin = st(req.pass ?? "final");
      const want = req.takes ?? fin.shots
        .filter((s) => !req.shots || req.shots.includes(s.shot))
        .flatMap((s) => (s.cut.take != null && !s.cut.placeholder ? [{ shot: s.shot, take: s.cut.take }] : []));
      const out: import("../types").UpscaleResult = { queued: [], skipped: [], errors: [] };
      for (const w of want) {
        const t = fin.shots.find((s) => s.shot === w.shot)?.takes.find((x) => x.take === w.take);
        if (!t || t.status !== "ok") { out.skipped.push({ shot: w.shot, reason: "not a finished final take" }); continue; }
        if (t.upscale?.fresh && !req.redo) { out.skipped.push({ shot: w.shot, take: w.take, reason: "already upscaled" }); continue; }
        const stem = `${fin.folder}/${w.shot}/${w.shot}_t${String(w.take).padStart(2, "0")}`;
        const pixel = req.method === "pixel";
        t.upscale = { status: "ok", fresh: true, width: 1920, height: 1088, route: pixel ? "pixel" : req.vae ? "vae" : "latent",
                      method: pixel ? "pixel" : "latent", pixel_model: pixel ? (req.pixel_model ?? "RealESRGAN_x2.pth") : null,
                      start_step: pixel ? null : (req.start_step ?? 7 - (req.detail ?? 0)), comfy_prompt_id: null, mp4: t.mp4 ?? `${stem}.mp4`, save_notes: "mock" };
        out.queued.push({ shot: w.shot, take: w.take, route: t.upscale.route!, scale: 2, start_step: t.upscale.start_step!,
                          width: 1920, height: 1088, prompt_id: `mock-up-${w.shot}` });
        emit("seriesmith.upscale", { ep: EP, shot: w.shot, take: w.take, status: "ok" });
      }
      return out;
    },
    async master(req) {
      await wait();
      need(req.ep);
      if (req.action === "prores") {
        // the .mov of the master already made (the mock's last job), nothing assembled
        if (!masterJob?.output) throw new MockError("there is no master of this episode at the recipe's size yet", 409);
        const mov = masterJob.output.replace(/\.mp4$/, ".mov");
        return { plan: undefined as unknown as import("../types").MasterPlan, output: masterJob.output, mov };
      }
      const rows = st(req.pass ?? "final").shots.map((s) => {
        const t = s.takes.find((x) => x.take === s.cut.take);
        const up = !!t && t.upscale?.status === "ok" && !!t.upscale.fresh;
        const byRecipe = req.post === true || req.post === "recipe";
        const status = !t ? "gap" as const : !up ? "upscale" as const
          : byRecipe && !(t.post?.status === "ok" && t.post.fresh) ? "post" as const : "ok" as const;
        return { shot: s.shot, take: t?.take ?? null, target: t?.target ?? null, status,
                 why: status === "gap" ? "no usable pick" : status === "post" ? "not post-processed yet" : "",
                 recipe: "re-sample 2x → 1080p (crop)" + (req.post ? "; post: SeedVR2 7b, then motion blur 0.3" : ""),
                 upscale: null, post: req.post && t?.post ? { status: t.post.status, fresh: t.post.fresh, recipe: null } : null };
      });
      if (req.action === "queue") {
        for (const s of st(req.pass ?? "final").shots) {
          const t = s.takes.find((x) => x.take === s.cut.take);
          if (!t) continue;
          if (!(t.upscale?.status === "ok" && t.upscale.fresh)) {
            t.upscale = { status: "ok", fresh: true, width: 1920, height: 1080, route: "latent", method: "latent", start_step: 7,
                          comfy_prompt_id: null, mp4: t.mp4, save_notes: "mock" };
            emit("seriesmith.upscale", { ep: EP, shot: s.shot, take: t.take, status: "ok" });
          }
          if ((req.post === true || req.post === "recipe") && !(t.post?.status === "ok" && t.post.fresh)) {
            t.post = { status: "ok", fresh: true, width: 1920, height: 1080, mp4: t.mp4, save_notes: "mock",
                       recipe: { enhance: { method: "seedvr2" }, motion_blur: 0.3 } };
            emit("seriesmith.post", { ep: EP, shot: s.shot, take: t.take, status: "ok" });
          }
        }
      }
      const count = (k: string) => rows.filter((r) => r.status === k).length;
      const mode = req.post === true ? "recipe" as const : req.post === "present" || req.post === "recipe" ? req.post : "off" as const;
      const plan = { pass: req.pass ?? "final", post: mode !== "off", post_mode: mode, size: [1920, 1080] as [number, number], fit: "crop" as const, quality: "master" as const,
                     counts: { upscale: count("upscale"), post: count("post"), ok: count("ok"), kept: 0, queued: 0, gap: count("gap") },
                     ready: count("upscale") === 0 && count("post") === 0 && count("gap") === 0, rows };
      const existing = masterJob?.output ? { output: masterJob.output, mov: null } : null;
      if (req.action !== "assemble") return { plan, queued: [], errors: [], existing };
      if (masterJob?.state === "running") {
        throw new MockError("a master of this episode is already being assembled by the editor", 409, { job: masterJob });
      }
      // the job, step by step, as master reports it
      const job: import("../types").MasterJob = {
        ep: EP, pass: req.pass ?? "final", state: "running", elsewhere: false, by: "the editor",
        started: "2026-10-04T08:13:32-05:00", finished: null, step: "assemble", stage: "start",
        done: null, total: null, text: "", output: null, mov: null, report: null, titles: null, error: "",
      };
      const step = async (fields: Partial<typeof job>) => {
        Object.assign(job, fields);
        masterJob = { ...job };
        emit("seriesmith.master", { ...job });
        await wait();
      };
      const n = rows.length;
      await step({});
      await step({ stage: "probe", done: 0, total: n, text: rows[0]?.shot ?? "" });
      for (let i = 1; i <= n; i++) await step({ stage: "clips", done: i, total: n, text: rows[i - 1].shot });
      await step({ stage: "verify", done: null, total: null, text: "counting the output's frames" });
      await step({ step: "titles", stage: "titles", text: "intro" });
      await step({ stage: "titles", text: "outro" });
      await step({ stage: "verify", text: "checking the joins" });
      const titles = { intro: "../_titles/INTRO.mp4", outro: "../_titles/OUTRO.mp4", picture: "copied" as const, why: "" };
      await step({ state: "done", stage: "done", finished: "2026-10-04T08:42:48-05:00",
                   output: "master/ep01_master_1920x1080.mp4", mov: null, report: "master/ep01_master.md", titles });
      return { plan, output: job.output!, mov: null, report: job.report!, titles, job: { ...job } };
    },
    async alignJob() {
      await wait();
      return { job: null };   // the mock aligns in the request
    },
    async masterJob(ep) {
      await wait();
      need(ep);
      return { job: masterJob ? { ...masterJob } : null };
    },
    async putUpscaleKeep(ep, shot, take, keep, pass) {
      await wait();
      need(ep);
      const t = st(pass ?? "final").shots.find((s) => s.shot === shot)?.takes.find((x) => x.take === take);
      if (!t?.upscale || t.upscale.status !== "ok") throw new MockError(`${shot} take ${take} has no finished upscale`, 409);
      t.upscale.keep = keep;
      emit("seriesmith.upscale", { ep: EP, shot, take, status: keep ? "kept" : "unkept" });
      return { shot, take, keep };
    },
    async putUpscaleRecipe(ep, shot, recipe) {
      await wait();
      need(ep);
      return { shot, recipe, text: recipe ? "mock recipe" : null };
    },
    async upscaleOptions() {
      await wait();
      return {
        pixel: { status: "ready", missing: [], models: ["4x-UltraSharp.pth", "RealESRGAN_x2.pth", "RealESRGAN_x4.pth"], default: "RealESRGAN_x2.pth" },
        seedvr2: { status: "ready", missing: [], models: ["seedvr2_3b_int8_convrot.safetensors", "seedvr2_7b_int8_convrot.safetensors"],
                   default: "seedvr2_7b_int8_convrot.safetensors" },
        delivers: [{ id: "1080p", width: 1920, height: 1080 }, { id: "1440p", width: 2560, height: 1440 },
                   { id: "4k", width: 3840, height: 2160 }],
        fits: ["crop", "pad"],
        through: [{ id: "minimax_h3_ref2va", label: "MiniMax H3 Ref2VA", status: "ready", family: "MiniMaxH3LatentUpscaleWithModel" }],
        latent: { minimax_h3_ref2va: { status: "ready", missing: [], mode: "resample", align: 32, fixed_scale: null,
                                       family: "MiniMaxH3LatentUpscaleWithModel",
                                       upscalers: [{ id: "", label: "ComfyUI's own" }, { id: "pack", label: "LBH-123-AI's pack" }],
                                       windowings: [{ id: "", label: "ComfyUI's own" }, { id: "pack", label: "comfyui-obvpm-timeline" }] },
                  ltx2: { status: "ready", missing: [], mode: "second_stage", align: 32, fixed_scale: 2 },
                  ltx2_ingredients: null, minimax_h3_fl2va: null, wan22_vace: null,
                  wan22_i2v: { status: "ready", missing: [], mode: "pixel_refine", align: 32, fixed_scale: null },
                  wan22_ti2v: { status: "ready", missing: [], mode: "pixel_refine", align: 32, fixed_scale: null } },
        details: [0, 1, 2],
        max_scale: 4,
        encoders: ["auto", "nvenc", "x264"],
        precisions: ["fp16", "fp32"],
      };
    },
    async post(req) {
      await wait();
      need(req.ep);
      const fin = st(req.pass ?? "final");
      const want = req.takes ?? fin.shots
        .filter((s) => !req.shots || req.shots.includes(s.shot))
        .flatMap((s) => (s.cut.take != null && !s.cut.placeholder ? [{ shot: s.shot, take: s.cut.take }] : []));
      const out: import("../types").PostResult = { queued: [], skipped: [], errors: [] };
      for (const w of want) {
        const t = fin.shots.find((s) => s.shot === w.shot)?.takes.find((x) => x.take === w.take);
        if (!t || !(t.upscale?.status === "ok" && t.upscale.fresh)) { out.errors.push({ shot: w.shot, take: w.take, error: "no upscale yet (seriesmith upscale first)" }); continue; }
        if (t.post?.fresh && !req.redo) { out.skipped.push({ shot: w.shot, take: w.take, reason: "a fresh post with these settings" }); continue; }
        t.post = { status: "ok", fresh: true, width: t.upscale.width, height: t.upscale.height, mp4: t.mp4, save_notes: "mock",
                   recipe: { enhance: { method: "seedvr2" }, motion_blur: req.blur ?? 0.3 } };
        out.queued.push({ shot: w.shot, take: w.take, what: "SeedVR2 7b, then motion blur 0.3", width: 1920, height: 1080, prompt_id: `mock-post-${w.shot}` });
        emit("seriesmith.post", { ep: EP, shot: w.shot, take: w.take, status: "ok" });
      }
      return out;
    },
    async postOptions(ep) {
      await wait();
      const ready = { status: "ready" as const, missing: [] };
      return {
        tiers: [
          { id: "draft", enhance: { method: "pixel" }, text: "pixel", readiness: ready },
          { id: "production", enhance: { method: "seedvr2", seedvr2_model: "7b", chunk: "fit", overlap: 6 }, text: "SeedVR2 7b", readiness: ready },
          { id: "cinematic", enhance: { method: "supir", strength: 0.2 }, text: "SUPIR 0.2",
            readiness: { status: "not_ready" as const, missing: ["SUPIR-v0F_fp16.safetensors in models/model_patches/"] } },
        ],
        methods: ["pixel", "seedvr2", "supir"],
        blur: { min: 0, max: 1, default: 0.3, readiness: ready },
        strength: { min: 0.05, max: 0.5, default: 0.2 },
        recipe: ep ? { fields: { enhance: "production", motion_blur: 0.3 }, text: "SeedVR2 7b, then motion blur 0.3", shots: {}, problems: [] } : null,
      };
    },
    async deletePost(ep, shot, take, pass) {
      await wait();
      need(ep);
      const t = st(pass ?? "final").shots.find((s) => s.shot === shot)?.takes.find((x) => x.take === take);
      if (!t?.post) throw new MockError(`${shot} take ${take} has no post`, 404);
      t.post = null;
      emit("seriesmith.post", { ep: EP, shot, take, status: "deleted" });
      return { shot, take, deleted: true };
    },
    async deleteUpscale(ep, shot, take, pass) {
      await wait();
      need(ep);
      const t = st(pass ?? "final").shots.find((s) => s.shot === shot)?.takes.find((x) => x.take === take);
      if (!t?.upscale) throw new MockError(`${shot} take ${take} has no upscale`, 404);
      t.upscale = null;
      emit("seriesmith.upscale", { ep: EP, shot, take, status: "deleted" });
      return { shot, take, deleted: true };
    },
    async browse(path, files) {
      await wait();
      return fsBrowse(path, !!files);
    },
    async refs(ep) {
      await wait();
      need(ep);
      return { refs: refs.list(), defaults: refs.defaults() };
    },
    async putRefDefaults(ep, fields) {
      await wait();
      need(ep);
      if (!("target" in fields) && !("keyframe_target" in fields) && !("edit_target" in fields) && !("turn_target" in fields) && !("voice_target" in fields)) {
        throw new MockError("give target, keyframe_target, edit_target, turn_target and/or voice_target", 400);
      }
      const defaults = refs.setDefaults(fields);
      emit("seriesmith.episode", { ep: EP });
      return { defaults };
    },
    async refsGenerateMissing(req) {
      await wait();
      need(req.ep);
      const pass = req.pass ?? "proxy";
      const kinds = req.kinds ?? ["series", "keyframe"];
      const out: RefGenerateMissingResult = { queued: [], picked: [], skipped: [], errors: [] };
      const list = refs.list();
      const inFlight = (ts: { status: string }[]) => ts.some((t) => t.status === "queued" || t.status === "ok");
      if (kinds.includes("series")) {
        for (const r of list) {
          const used = (r.used_by[pass] ?? []).length || (req.unused && r.kind !== "voice");
          if (r.kind === "keyframe" || r.exists || !r.path || r.cleared || !used) continue;
          if (r.can_generate === false) {
            out.skipped.push({ ref: r.id, reason: r.why_not ?? "can't be generated" });
            continue;
          }
          // skipped if any candidate is queued or waits to be picked; a character
          // missing all four views gets one generate (view null, a shared seed)
          const all = hasViews(r) ? r.views!.flatMap((v) => v.takes) : r.takes;
          if (inFlight(all)) {
            out.skipped.push({ ref: r.id, reason: "a candidate is queued or waiting to be picked" });
            continue;
          }
          const missingViews = hasViews(r) ? r.views!.filter((v) => v.picked == null && !v.cleared).map((v) => v.view) : [];
          const views: (string | null)[] = !hasViews(r) || missingViews.length === r.views!.length ? [null] : missingViews;
          for (const view of views) {
            if (req.dry_run) {
              out.queued.push({ ref: r.id, view, take: null, prompt_id: null, seed: null, target: req.target ?? r.effective?.target ?? null, method: "generate" });
              continue;
            }
            const g = refs.generate({
              ep: req.ep, ref: r.id, view, count: 1, seed_mode: "auto", seed: null, prompt: null, model: null, loras: null, steps: null,
              note: "generate missing", ...(req.target ? { target: req.target } : {}),
            });
            out.queued.push(...g.queued.map((q) => ({ ...q, seed_source: "stable", method: "generate" })));
          }
        }
      }
      if (kinds.includes("keyframe")) {
        const s = st(pass);
        const order = s.shots.filter((x) => !x.orphan);
        for (const r of list) {
          if (r.kind !== "keyframe" || r.exists || r.cleared || r.need == null || !keyframeWanted(r)) continue;
          if (inFlight(r.takes)) {
            out.skipped.push({ ref: r.id, reason: "a candidate is already queued or waiting to go live" });
            continue;
          }
          const i = order.findIndex((x) => x.shot === r.shot);
          const src = order[i + (r.which === "first" ? -1 : 1)];
          if (r.method === "continuity" && src && src.cut.take != null && src.cut.usable) {
            if (req.dry_run) {
              out.picked.push({ ref: r.id, take: null, method: "continuity" });
              continue;
            }
            const k = await api.refsKeyframe({ ep: req.ep, pass, shot: r.shot!, which: r.which!, pick: true });
            out.picked.push({ ref: r.id, take: k.picked, method: "continuity" });
            continue;
          }
          if (r.method === "import") {
            out.skipped.push({ ref: r.id, reason: "the script asks for an imported file: drop one on it, or Import…" });
            continue;
          }
          if (req.dry_run) {
            out.queued.push({ ref: r.id, view: null, take: null, prompt_id: null, seed: null, target: req.keyframe_target ?? r.effective?.target ?? null, method: "generate" });
            continue;
          }
          const g = refs.generate({
            ep: req.ep, ref: r.id, view: null, count: 1, seed_mode: "auto", seed: null, prompt: null, model: null, loras: null, steps: null,
            note: "generate missing", ...(req.keyframe_target ? { target: req.keyframe_target } : {}),
          });
          out.queued.push(...g.queued.map((q) => ({ ...q, seed_source: "stable", method: "generate" })));
        }
      }

      if (!req.dry_run && (out.queued.length || out.picked.length)) emit("seriesmith.episode", { ep: EP });
      return out;
    },
    async refsUpload(req, onProgress) {
      need(req.ep);
      const name = req.name ?? "upload";
      const total = req.file.size;
      if (total > UPLOAD_LIMIT) throw new MockError(`${name} is over 64 MB`, 413);
      // simulated progress, in quarters
      for (let q = 1; q <= 4; q++) {
        await wait(80);
        onProgress?.(Math.round((total * q) / 4), total);
      }
      const t = refs.upload({ ref: req.ref, view: req.view ?? null, name, pick: !!req.pick });
      emit("seriesmith.episode", { ep: EP });
      return t;
    },
    async mcpLaunch(port) {
      const url = `http://127.0.0.1:${port || 8190}`;
      return {
        command: "C:\seriesmith\.venv\Scripts\seriesmith.exe", how: "seriesmith" as const, url, read_only: "--read-only",
        args: url === "http://127.0.0.1:8190" ? ["mcp"] : ["mcp", "--url", url],
      };
    },
    // ---- takes from outside (takeimport) ----
    async importTake(req) {
      return mockImportTake(req.pass, req.shot, req.source_path.split(/[\/]/).pop() || "video.mp4", !!req.pick, null);
    },
    async uploadTake(req, onProgress) {
      need(req.ep);
      const name = req.name ?? "video.mp4";
      const total = req.file.size;
      for (let q = 1; q <= 4; q++) {
        await wait(80);
        onProgress?.(Math.round((total * q) / 4), total);
      }
      return mockImportTake(req.pass, req.shot, name, !!req.pick, null);
    },
    async copyTake(req) {
      need(req.ep);
      const from = req.from_pass ?? req.pass;
      if (from === req.pass && req.from_shot === req.shot) {
        throw new MockError(`${req.shot} t${String(req.take).padStart(2, "0")} is already ${req.shot}'s: pick it instead`, 400);
      }
      const src = shotSt(from, req.from_shot).takes.find((t) => t.take === req.take);
      if (!src) throw new MockError(`${req.from_shot} has no take ${req.take} in ${from}`, 404);
      if (!(src.status === "ok" && src.has_video)) throw new MockError(`${req.from_shot} t${req.take} isn't a finished take`, 400);
      return mockImportTake(req.pass, req.shot, null, !!req.pick, { shot: req.from_shot, take: req.take, pass: from, src });
    },
    async colorMeasure(ep, pass) {
      await wait(200);
      need(ep);
      return { measured: [], had: status[pass]?.shots.length ?? 0 };
    },
    async colorMatch(ep, pass, base, shots, by) {
      await wait(300);
      need(ep);
      const st = status[pass];
      const sq = st?.shots.find((s) => s.shot === base)?.sequence;
      const ids = shots ?? (st?.shots ?? []).filter((s) => s.shot !== base && s.sequence === sq && !s.orphan && !s.cut?.out).map((s) => s.shot);
      const colors: Record<string, Record<string, number>> = {};
      const skipped: { shot: string; why: string }[] = [];
      ids.forEach((id, i) => {
        const s = st?.shots.find((x) => x.shot === id);
        if (!s || s.cut?.locked) skipped.push({ shot: id, why: s ? "it's locked" : "it isn't in the cut" });
        else {
          const exposure = Math.round(((i % 3) - 1) * 150) / 1000;
          // luma sets the brightness alone: the clip's own colour stays
          colors[id] = by === "luma" ? { ...(s.cut?.color ?? {}), exposure }
            : { exposure, warmth: Math.round(((i % 2) - 0.5) * 200) / 1000 };
        }
      });
      return { base, colors, skipped };
    },
    // ---- P10: a pass's issues (the notepad) ----
    async issues(ep, pass) {
      await wait();
      need(ep);
      return issues
        .filter((x) => !pass || x.pass === pass)
        .map((x) => ({ ...x, addressed: issueAddressed(x) }));
    },
    async addIssue(req) {
      await wait();
      need(req.ep);
      if (!req.note?.trim()) {
        throw new MockError("the note is the issue: say what is wrong with the shot", 400);
      }
      const sh = st(req.pass).shots.find((x) => x.shot === req.shot);
      if (!sh) throw new MockError(`${req.shot} is not in the ${req.pass} shotlist`, 404);
      const d = det(req.pass, req.shot);
      const take = req.take ?? sh.cut.take ?? null;
      const item: Issue = {
        id: `mk${issues.length + 1}${Math.random().toString(16).slice(2, 6)}`,
        shot: req.shot,
        pass: req.pass,
        take,
        note: req.note.trim(),
        when: new Date().toISOString(),
        // the snapshot: what produced the take, kept as it was
        shot_hash: `h${JSON.stringify(d.built).length}`,
        target: d.effective?.target ?? null,
        script: d.built_prompt || `## ${req.shot}`,
        prompt: d.effective?.prompt ?? "",
        seed: d.effective?.seed ?? null,
        refs: (d.refs_used ?? []).map((r) => ({ role: r.role, id: r.id, path: r.path })),
        take_file: take
          ? `renders_proxy/${req.shot}/${req.shot}_t${String(take).padStart(2, "0")}.mp4`
          : null,
      };
      issues.push(item);
      emit("seriesmith.issues", { ep: EP, pass: item.pass, shot: item.shot, id: item.id });
      return { ...item, addressed: false };
    },
    async resolveIssue(ep, id) {
      await wait();
      need(ep);
      const i = issues.findIndex((x) => x.id === id);
      if (i >= 0) issues.splice(i, 1);
      emit("seriesmith.issues", { ep: EP, removed: i >= 0 ? 1 : 0 });
      return issues.map((x) => ({ ...x, addressed: issueAddressed(x) }));
    },
    async clearIssues(ep, pass, addressedOnly) {
      await wait();
      need(ep);
      for (let i = issues.length - 1; i >= 0; i--) {
        if (pass && issues[i].pass !== pass) continue;
        if (addressedOnly && !issueAddressed(issues[i])) continue;
        issues.splice(i, 1);
      }
      emit("seriesmith.issues", { ep: EP, pass: pass ?? null });
      return issues
        .filter((x) => !pass || x.pass === pass)
        .map((x) => ({ ...x, addressed: issueAddressed(x) }));
    },
    async exportIssues(ep, pass) {
      await wait();
      need(ep);
      const items = issues
        .filter((x) => (!pass || x.pass === pass) && !issueAddressed(x));
      const out = [
        `# ${fx.summary.name}: ${items.length} issue${items.length === 1 ? "" : "s"}`
        + (pass ? ` (${pass} pass)` : ""),
        "",
        "These are notes taken while watching a rendered pass of an episode. For each shot, "
        + "propose the smallest edit to the script or the series config that would fix what "
        + "the note describes.",
        "",
      ];
      for (const x of items) {
        out.push(`## ${x.shot}${x.take ? ` · take ${x.take}` : ""}`, "", x.note, "");
        if (x.script) out.push("**The script, as rendered:**", "", "```", x.script, "```", "");
        if (x.prompt) {
          out.push("**What the pipeline compiled from it:**", "", "```", x.prompt, "```", "");
        }
      }
      return out.join("\n");
    },
    async refsMatch(ep, names) {
      await wait();
      need(ep);
      return refs.match(names);
    },
    async refsDiscard(req) {
      await wait();
      need(req.ep);
      const r = refs.discard({ ref: req.ref, view: req.view ?? null, take: req.take });
      emit("seriesmith.episode", { ep: EP });
      return r;
    },
    async refsUnpick(ep, ref, view) {
      await wait();
      need(ep);
      const r = refs.unpick(ref, view ?? null);
      emit("seriesmith.episode", { ep: EP });
      return r;
    },
    refFileUrl(_ep, path) {
      return refs.image(path) ?? refs.audio(path) ?? media + path.split("/").pop();
    },
    async presets() {
      await wait();
      return { relight: [], look: [], framing: [], camera: [], look_builder: [] };
    },
    async cuePresets() {
      await wait();
      return clone(CUE_PRESETS);
    },
    presetImageUrl(name) {
      return media + name.split("/").pop();
    },
    async presetSaveOwn(req) {
      await wait();
      return { id: req.id ?? req.label.toLowerCase().replace(/\W+/g, "_"), label: req.label, group: "yours",
        text: req.text ?? "", own: true };
    },
    async presetDeleteOwn() {
      await wait();
      return { ok: true };
    },
    async presetPicture(req) {
      await wait();
      return { id: req.id, label: req.id, group: "yours", text: "", own: true };
    },
    async presetPictureUpload(req) {
      await wait();
      return { id: req.id, label: req.id, group: "yours", text: "", own: true };
    },
    async presetRender() {
      await wait();
      throw new Error("the mock doesn't render");
    },
    thumbUrl(_ep, path) {
      // the mock has no small copies: the picture itself, as refFileUrl finds it
      return refs.image(path) ?? media + path.split("/").pop();
    },
    async refsGenerate(req) {
      await wait();
      need(req.ep);
      return refs.generate(req);
    },
    async refsTour(req) {
      await wait();
      need(req.ep);
      return { queued: [{ tour: 1, comfy_prompt_id: "mock-tour" }] };
    },
    async refsTourFrame(req) {
      await wait();
      need(req.ep);
      throw new Error(`the mock has no tour video for ${req.ref}`);
    },
    async refsCopyTake(req) {
      await wait();
      need(req.ep);
      throw new Error(`the mock can't copy ${req.ref} t${req.take} into ${req.to}`);
    },
    async refsRelight(req) {
      await wait();
      need(req.ep);
      const ids = req.locations ?? ["street"];
      return {
        locations: ids.map((source) => ({ source, id: `${source}_${req.suffix || req.relight}`, exists: false, entry: {} })),
        queued: [], errors: req.dry_run ? [] : [{ error: "the mock doesn't relight" }], repointed: [],
      };
    },
    async refsPick(req) {
      await wait();
      need(req.ep);
      const r = refs.pick(req);
      emit("seriesmith.episode", { ep: EP });
      return r;
    },
    async refsImport(req) {
      await wait(300);
      need(req.ep);
      return refs.import(req);
    },
    async refsKeyframe(req) {
      await wait(250);
      need(req.ep);
      const which = req.which ?? "first";
      if (which !== "first" && which !== "last") throw new MockError(`which must be "first" or "last", not ${String(which)}`, 400);
      const shots = st(req.pass).shots.filter((s) => !s.orphan);
      const i = shots.findIndex((s) => s.shot === req.shot);
      if (i < 0) throw new MockError(`${req.shot} is not in the ${req.pass} cut`, 404);
      let src: ShotStatus | undefined;
      if (req.source_shot) {
        src = st(req.pass).shots.find((s) => s.shot === req.source_shot);
        if (!src) throw new MockError(`${req.source_shot} is not in the ${req.pass} cut and has no takes`, 404);
      } else {
        src = shots[i + (which === "first" ? -1 : 1)];
        if (!src) {
          throw new MockError(`${req.shot} is the ${which} shot of the ${req.pass} cut: there is no ${which === "first" ? "previous" : "next"} shot to take a frame from`, 400);
        }
      }
      const takeNo = req.source_take ?? src.cut.take;
      if (takeNo == null) throw new MockError(`${src.shot} has no usable ${req.pass} take to take a frame from (render it first)`, 409);
      const t = src.takes.find((x) => x.take === takeNo);
      if (!t) throw new MockError(`${src.shot} has no ${req.pass} take ${takeNo}`, 404);
      if (t.status !== "ok" || !t.has_video) throw new MockError(`${src.shot} ${req.pass} t${String(takeNo).padStart(2, "0")} is ${t.status}`, 409);
      const frames = src.length ?? 73;
      const spec = req.frame ?? (which === "first" ? "last" : "first");
      const frame = spec === "first" ? 0 : spec === "last" ? frames - 1 : spec < 0 ? spec + frames : spec;
      if (!Number.isInteger(frame) || frame < 0 || frame >= frames) throw new MockError(`frame ${String(spec)} is outside the take (${frames} frames: 0 to ${frames - 1})`, 400);
      const r = refs.keyframe({ shot: req.shot, which, from: { shot: src.shot, take: takeNo, pass: req.pass, frame, frames }, pick: req.pick ?? null });
      if (r.picked === r.takes[r.takes.length - 1]?.take) {
        // the shot's takes that used the old keyframe are ref-stale now
        for (const pass of ["final", "proxy"] as Pass[]) {
          for (const x of status[pass]?.shots.find((s) => s.shot === req.shot)?.takes ?? []) {
            if (x.status === "ok" && !x.stale.includes("ref")) x.stale = [...x.stale.filter((y) => y !== "unknown"), "ref"];
          }
        }
      }
      emit("seriesmith.episode", { ep: EP });
      return r;
    },
    async putRefOverride(req) {
      await wait();
      need(req.ep);
      const override = refs.putOverride(req.ref, req.fields, req.view ?? null);
      emit("seriesmith.episode", { ep: EP });
      return { override };
    },
    async deleteRefOverride(ep, ref, view) {
      await wait();
      need(ep);
      const override = refs.deleteOverride(ref, view ?? null);
      emit("seriesmith.episode", { ep: EP });
      return { override };
    },
    async models() {
      await wait();
      return ["minimax_h3_ref2va_pruned_int8_convrot.safetensors", "minimax_h3_ref2va_bf16.safetensors", "wan2.2_t2v_14B_fp8.safetensors"];
    },
    async loras() {
      await wait();
      return [
        "minimax_h3_ref2v_lightx2v_turbo_4step_v0.1_resized_avg_rank_20_bf16.safetensors",
        "storybook_style_v2.safetensors",
        "film_grain_subtle.safetensors",
      ];
    },
    async targets(o) {
      const { kind, ready } = targetsQuery(o);
      await wait(ready ? 300 : undefined);
      if (kind === "music") return { targets: clone(MUSIC_TARGETS), default: { music: "stable_audio3" } };
      const all = clone(MOCK_TARGETS);
      if (ready) for (const t of all.targets) t.readiness = mockReadiness(t.id);
      for (const t of all.targets) t.graph = mockGraph(t);
      return kind ? { ...all, targets: all.targets.filter((t) => t.kind === kind) } : all;
    },
    async workflows() {
      await wait();
      return [...savedWorkflows].sort().map((name) => ({
        name, target: MOCK_TARGETS.targets.some((t) => t.workflow === name),
      })).concat([{ name: "my_own_wan_experiment.json", target: false }]);
    },
    async inspectTarget(req) {
      await wait(400);
      const name = req.workflow || "my_own_wan_experiment.json";
      const id = req.id || "my_wan";
      // the mock stands in for inspector: a plausible proposal with one thing
      // it couldn't settle and the warnings the real one always gives
      return {
        proposal: {
          id, kind: "video", label: req.label || "My Wan", short: "Mine", draft: true,
          capabilities: { audio: "none" },
          template: { fps: 16, frames: { step: 4, base: 1, max: 243 }, size_multiple: 16, size_fit: "snap" },
          recipe: { prompt: "prose", policies: ["silent"] },
          binding: { workflow_name: name, saver: { class_type: "H3SaveShot" }, params: {} },
          presets: { final: { model: "my_model.safetensors", steps: 20, width: 832, height: 480 } },
          models: { model: { family: "wan2.2-i2v-14b-high", patterns: ["my_model*"], tier: "required", folder: "diffusion_models" } },
        },
        matched: {
          model: "UNETLoader.unet_name", prompt: "CLIPTextEncode.text",
          negative: "CLIPTextEncode.text", width: "WanImageToVideo.width",
          height: "WanImageToVideo.height", length: "WanImageToVideo.length",
          seed: "KSampler.seed", steps: "KSampler.steps",
        },
        ambiguous: [{
          param: "cfg", ask: "2 nodes could take cfg: KSampler.cfg, KSamplerAdvanced.cfg. Pick one, or give it a title in ComfyUI and inspect again.",
          candidates: [
            { node: "7", class_type: "KSampler", field: "cfg", value: 5 },
            { node: "9", class_type: "KSamplerAdvanced", field: "cfg", value: 3.5 },
          ],
        }],
        warnings: [
          "frames: step 4 and base 1 come from the length widget's own step and default (81); `max` (243) is a guess — no graph states how long the model can go. Probe-render the longest shot you mean to use.",
          "loras: the graph has no LoRA loader, so one is inserted after the model loader when a shot or profile names a LoRA.",
        ],
        models: [{ param: "model", file: "my_model.safetensors", family: "wan2.2-i2v-14b-high", folder: "diffusion_models", label: "Wan 2.2 I2V 14B (high noise)" }],
        nodes: {},
        unbound: [{ class_type: "UNETLoader", field: "weight_dtype", value: "default" }],
        problems: [],
        can_save: true,
      };
    },
    async saveCustomTarget(ep, target) {
      await wait();
      need(ep);
      const id = String((target as { id?: string }).id || "my_wan");
      if (MOCK_TARGETS.targets.some((t) => t.id === id)) {
        throw new MockError(`'${id}' is a built-in target's name: choose another`, 400);
      }
      const existing = MOCK_TARGETS.targets.findIndex((t) => t.id === id && t.custom);
      const entry = {
        ...(target as object), id, kind: "video" as const, custom: true,
        draft: !!(target as { draft?: boolean }).draft,
        label: String((target as { label?: string }).label || id),
      } as (typeof MOCK_TARGETS)["targets"][number];
      if (existing >= 0) MOCK_TARGETS.targets[existing] = entry;
      else MOCK_TARGETS.targets.push(entry);
      emit("seriesmith.episode", { ep: EP });
      return { ok: true, id, path: `${ep}\targets\${id}\target.json`, draft: entry.draft };
    },
    async setTargetDraft(ep, id, draft) {
      await wait();
      need(ep);
      const t = MOCK_TARGETS.targets.find((x) => x.id === id && x.custom);
      if (!t) throw new MockError(`no custom target called '${id}'`, 404);
      t.draft = draft;
      emit("seriesmith.episode", { ep: EP });
      return { ok: true, id, draft };
    },
    async deleteCustomTarget(ep, id) {
      await wait();
      need(ep);
      const i = MOCK_TARGETS.targets.findIndex((t) => t.id === id && t.custom);
      if (i >= 0) MOCK_TARGETS.targets.splice(i, 1);
      emit("seriesmith.episode", { ep: EP });
      return { ok: true, id, deleted: i >= 0 };
    },
    async installWorkflow(target, opts) {
      await wait();
      const t = MOCK_TARGETS.targets.find((x) => x.id === target);
      if (!t) throw new MockError(`no target called '${target}'`, 400);
      const name = opts?.name || t.workflow || `${target}.json`;
      if (savedWorkflows.has(name) && !opts?.overwrite) {
        throw new MockError(`workflows/${name} is already saved in ComfyUI — pass overwrite: true to replace it`, 409);
      }
      savedWorkflows.add(name);
      return { ok: true, target, installed: name, renders: name === t.workflow, graph: mockGraph(t) };
    },
    async revertWorkflow(target, name) {
      await wait();
      const t = MOCK_TARGETS.targets.find((x) => x.id === target);
      if (!t) throw new MockError(`no target called '${target}'`, 400);
      const file = name || t.workflow || `${target}.json`;
      const had = savedWorkflows.delete(file);
      return { ok: true, target, deleted: had, name: file, graph: mockGraph(t) };
    },
    async dubs(ep, shot) {
      await wait();
      need(ep);
      return { shot, sound: sounds[shot] ?? null, track: null, dubs: [], takes: [] };
    },
    async putSound(ep, shots, sound) {
      await wait();
      need(ep);
      for (const s of shots) {
        if (sound) sounds[s] = sound;
        else delete sounds[s];
      }
      emit("seriesmith.episode", { ep: EP });
      return { shots, sound };
    },
    async putEpisodeTarget(ep, target) {
      await wait();
      need(ep);
      if (target !== null && !MOCK_TARGETS.targets.some((t) => t.id === target && t.kind === "video")) {
        throw new MockError(`${String(target)} isn't a video target (GET /seriesmith/targets?kind=video)`, 400);
      }
      episodeTarget = target;
      syncEpisodeTarget();
      emit("seriesmith.episode", { ep: EP });
      const s = st("proxy");
      return { target: s.target, target_source: s.target_source, series_target: s.series_target };
    },
    async widgetChoices(classType, field) {
      await wait();
      return MOCK_WIDGET_CHOICES[`${classType}|${field}`] ?? null;
    },
    async modelFiles(target, param) {
      await wait();
      const r = mockModelFiles(target, param);
      if (!r) throw new MockError(`${target} declares no model family for ${param}`, 400);
      return r;
    },
    async source(ep, file) {
      await wait();
      need(ep);
      const f = files[file];
      const shots = file === "script" ? check("script", f.text).shots : [];
      return { file, path: sourcePath(file), text: f.text, hash: f.hash, mtime: f.mtime, shots };
    },
    async refsFromFrame() {
      await wait(80);
      return { frame: null, edits: [], step: null };
    },
    async refsVideo(_ep, from) {
      await wait(80);
      const name = "source_path" in from ? from.source_path.split(/[\\/]/).pop() ?? "video.mp4" : from.name ?? "video.mp4";
      return { path: `refs/_videos/${name}`, name, size: 0, modified: Date.now() / 1000, copied: true, duration: 5 };
    },
    async refsVideos() {
      await wait(40);
      return { videos: [] };
    },
    async refsSharedTakes() {
      await wait();
      return { takes: [] };
    },
    async refsOwnerTakes() {
      await wait(40);
      return { owner: null, takes: [] };
    },
    async routerInspect(req) {
      await wait(60);
      return { proposal: { id: "mock_model", label: req.model, router: { model: req.model, inputs: { prompt: "prompt" } } },
               mapped: { prompt: "prompt" }, unplaced: [], warnings: [] };
    },
    async putTargetLimits(_ep, id) {
      await wait(40);
      const t = (await this.targets({})).targets.find((x) => x.id === id);
      if (!t) throw new MockError(`no target ${id}`, 404);
      return { ok: true, id, path: "(mock)", target: t };
    },
    async routerModels() {
      await wait(40);
      return { models: [
        { id: "kling/kling-v3-omni", provider: "kling", model: "kling-v3-omni", kind: "video" as const, text_only: false },
        { id: "wan/wan2.7-t2v", provider: "wan", model: "wan2.7-t2v", kind: "video" as const, text_only: true },
        { id: "byteplus/seedream-5-0-260128", provider: "byteplus", model: "seedream-5-0-260128", kind: "image" as const, text_only: false },
      ] };
    },
    async routerDryRun(req) {
      await wait(40);
      return { ok: true, shot: req.shot || "sh010", pass: req.pass || "proxy", model: "mock/model",
               arguments: { prompt: "(the shot's prompt)" }, prompt_chars: { written: 18 } };
    },
    async promptPreview(req) {
      await wait(40);
      const template = req.template ?? "{style} {action}";
      const request = req.request ?? "{prompt}";
      const parts = [{ name: "style", about: "The look", value: "Style: flat." }, { name: "action", about: "What happens", value: "She waits." }];
      const sent = template.replace("{style}", parts[0].value).replace("{action}", parts[1].value);
      return { ok: true, id: req.id ?? "mock", label: "Mock model", scope: "builtin", hosted: true, shot: req.shot || "sh010",
               pass: req.pass || "proxy", editable: true, changed: false, template, request,
               shipped: { template: "{style} {action}", request: "{prompt}" }, problems: { template: [], request: [] },
               parts, request_parts: [{ name: "prompt", about: "The shot's prompt", value: sent }], prompt: sent, sent,
               entry: { id: req.shot || "sh010", prompt: sent }, model: "mock/model", arguments: { prompt: sent },
               ...(req.count ? { takes_on_model: 3 } : {}) };
    },
    async putTargetPrompt(_ep, id, template, request, inputs, args) {
      await wait(40);
      return { ok: true, id, path: "targets/overrides.json", changed: !!(template || request || inputs || args) };
    },
    async providers() {
      await wait(40);
      return { providers: [] };
    },
    async putProvider(definition) {
      await wait(40);
      return { ok: true, id: String(definition.id), providers: [] };
    },
    async putProviderKey(id) {
      await wait(40);
      return { ok: true, id, providers: [] };
    },
    async draftProvider(req) {
      await wait(40);
      return { form: req.form ?? { id: "mine", answer: "job" }, definition: { id: "mine" }, problems: [], notes: [], model: "m" };
    },
    async checkProvider() {
      await wait(40);
      return { reached: true, key_ok: true, status: 404, says: "not found" };
    },
    async lines() {
      await wait(40);
      return { available: false, why: "the mock has no voice model on a provider", target: "", label: "", service: "", lines: [], characters: [],
               to_make: { lines: 0, chars: 0 }, no_speaker: [], recording: null, can_lay: false };
    },
    async generateLines() {
      await wait(40);
      return { queued: [], errors: [] };
    },
    async characterLines() {
      await wait(40);
      return { job: {} };
    },
    async lineUpSound() {
      await wait(40);
      return { job: {} };
    },
    async setDubModelSound(_ep, _shot, on) {
      await wait(40);
      return { ok: true, on };
    },
    async setSoundOffset(_ep, _shot, offset) {
      await wait(40);
      return { ok: true, offset };
    },
    async pickLine() {
      await wait(40);
      return { ok: true };
    },
    async layLines() {
      await wait(40);
      return { path: "audio/lines/lines_recording.wav", seconds: 0, lines: 0, timed: true, notes: [] };
    },
    async providerVoices() {
      await wait(40);
      return { voices: [{ id: "v1", name: "Sample voice", preview: "", about: "", category: "premade", labels: {} }], next: "" };
    },
    async putProviderVoice() {
      await wait(40);
      return { ok: true, changed: true };
    },
    async readProviderSpec() {
      await wait(40);
      return { form: "example", paths: ["/generate"], proposal: null };
    },
    async modelSchema() {
      await wait(40);
      return { available: true, required: ["prompt"], fields: [{ path: "prompt", type: "string", required: true }, { path: "seed", type: "integer", required: false }] };
    },
    async drafts() {
      await wait(40);
      return { drafts: [] };
    },
    async clipsEnsure() {
      await wait(60);
      return { ep: EP, made: false };
    },
    async clipsNew(title, root) {
      await wait(200);
      const at = root ?? roots[0];
      if (!at) throw new MockError("no project folder yet: add one (Project folders) first", 409);
      const show = title.trim().split(/\s+/).join(" ").replace(/[^A-Za-z0-9._-]+/g, "_").replace(/^[._-]+|[._-]+$/g, "");
      if (!show) throw new MockError("name the project: letters or digits", 400);
      const sep = at.includes("\\") ? "\\" : "/";
      const name = show.toLowerCase();
      const ep = `${at.replace(/[\\/]+$/, "")}${sep}${show}${sep}${name}`;
      if (made.some((m) => m.ep === ep)) throw new MockError(`there is already a ${show} folder in ${at}`, 409);
      made.push({ ep, name, title: title.trim(), simple: true });
      emit("seriesmith.episode", { ep });
      return { ep };
    },
    async clipQueue(req) {
      await wait(120);
      return { refs: [], waiting_on: [], step: null,
        renders: [{ queued: [{ shot: req.shot, take: 1, prompt_id: "mock-clip" }] }] };
    },
    async episodeTemplate(parent, show) {
      await wait(80);
      const sep = parent.includes("\\") ? "\\" : "/";
      const at = show ? `${parent.replace(/[\\/]+$/, "")}${sep}${show}` : parent;
      const here = EP.replace(/[\\/][^\\/]+[\\/]?$/, "");
      const mine = at === here;
      return { parent: at, from: mine ? EP : null, series: mine ? files.series.text : null,
        name: mine ? "ep02" : "ep01", episodes: mine ? [EP.split(/[\\/]/).pop() ?? ""] : [] };
    },
    async sourceHash(ep, file) {
      await wait(30);
      need(ep);
      return { file, hash: files[file].hash, mtime: files[file].mtime };
    },
    async checkSource(ep, file, text) {
      await wait(150);
      need(ep);
      return check(file, text);
    },
    async previewShot(ep, pass, text, shot) {
      await wait(120);
      need(ep);
      const lines = text.split(/\r?\n/);
      const at = lines.findIndex((l) => l.trim().startsWith(`## ${shot}`));
      if (at < 0) return { ok: false, error: `${shot} isn't in the script`, line: null };
      const action = lines.slice(at + 1).find((l) => l.trim() && !/^[a-z_]+:/.test(l.trim()) && !l.startsWith("#")) ?? "";
      return { ok: true, shot, target: "minimax_h3_ref2va", target_label: "MiniMax H3 Ref2VA", prompt: `The target video is the mock series. ${action}`,
        frames: 73, fps: 24, seconds: 3.04, width: pass === "proxy" ? 864 : 1344, height: pass === "proxy" ? 480 : 768,
        audio_policy: "generate", subjects: [], background: null, pacing: null, warnings: [] };
    },
    async renameEntry(req) {
      return { id: req.to, build: null };
    },
    async putSource(req) {
      await wait(300);
      need(req.ep);
      if (req.base_hash !== files[req.file].hash) throw conflict(req.file);
      if (req.file === "series") {
        try {
          JSON.parse(req.text);
        } catch (e) {
          const at = jsonErrorAt(req.text, e);
          throw new MockError(`series.json isn't valid JSON (line ${at.line}, column ${at.col}): ${at.message}`, 400, { error: at.message, line: at.line, col: at.col });
        }
      }
      writeFile(req.file, req.text);
      const c = check(req.file, req.text);
      afterSourceWrite();
      let build = null;
      if (req.rebuild) {
        if (c.ok) build = await api.build(req.ep);
        else {
          const first = c.errors[0];
          const error = `${first.file === "series" ? "series.json" : scriptName}: line ${first.line}: ${first.message}`;
          build = { ok: false, passes: { final: { ok: false, report: "", error }, proxy: { ok: false, report: "", error } } };
          emit("seriesmith.episode", { ep: EP });
        }
      } else emit("seriesmith.episode", { ep: EP });
      return { hash: files[req.file].hash, check: c, build };
    },
    async promotePlan(ep, shot) {
      await wait(250);
      need(ep);
      const p = planPromote(promoteInput(shot ?? null));
      return { items: p.items, left: p.left, diffs: p.diffs, hashes: { script: files.script.hash, series: files.series.hash } };
    },
    async promote(ep, items, hashes, shot) {
      await wait(400);
      need(ep);
      for (const f of ["script", "series"] as SourceFile[]) if (hashes?.[f] !== files[f].hash) throw conflict(f);
      const p = planPromote(promoteInput(shot ?? null));
      const unknown = items === "all" ? [] : items.filter((id) => !p.items.some((i) => i.id === id));
      if (unknown.length) throw new MockError(`${unknown.join(", ")} isn't in the plan: ask for the plan again`, 400);
      const r = p.apply(items);
      if (r.script !== files.script.text) writeFile("script", r.script);
      if (r.series !== files.series.text) writeFile("series", r.series);
      let refChanged = false;
      for (const d of r.drops) {
        if (d.scope === "shot" && d.shot) {
          for (const pass of ["final", "proxy"] as Pass[]) {
            const ov = detail[pass]?.[d.shot]?.override;
            if (ov) delete (ov as Record<string, unknown>)[d.field];
          }
          syncOverrideSummary(d.shot);
        } else if (d.scope === "episode" && d.field === "target") episodeTarget = null;
        else if (d.scope === "ref" && d.ref) {
          refs.dropOverrideFields(d.ref, d.view ?? null, [d.field]);
          refChanged = true;
        }
      }
      afterSourceWrite();
      const build = await api.build(ep);
      if (refChanged) emit("seriesmith.ref", { ep: EP });
      const after = planPromote(promoteInput(null));
      return { promoted: r.promoted, left: after.left, hashes: { script: files.script.hash, series: files.series.hash }, build };
    },
    // ---- Phase 9c-A: the recording and align ----
    async alignReady() {
      await wait(60);
      return align.ready();
    },
    async attachTrack(ep, sourcePath, pass) {
      await wait(300);
      need(ep);
      return attach(sourcePath, pass ?? "proxy", false);
    },
    async uploadTrack(req, onProgress) {
      need(req.ep);
      const name = req.name ?? "recording.wav";
      const total = req.file.size;
      if (total > UPLOAD_LIMIT) throw new MockError(`${name} is over 64 MB`, 413);
      for (let q = 1; q <= 4; q++) {
        await wait(80);
        onProgress?.(Math.round((total * q) / 4), total);
      }
      return attach(name, req.pass ?? "proxy", true);
    },
    async clearTrack(ep) {
      await wait(250);
      need(ep);
      if (!trackPath) throw new MockError("the series config names no recording", 400);
      trackPath = null;
      trackWords = false;
      trackVocals = false;
      dubFrom = "recording";
      emit("seriesmith.episode", { ep: EP });
      return { track: null, hash: mockHash(files.series.text + "|no-track"), build: await api.build(ep), path: null, copied: false, reformatted: false };
    },
    async align(req) {
      need(req.ep);
      const r = await align.run(req);
      const build = req.dry_run ? null : await api.build(req.ep);
      if (!req.dry_run) emit("seriesmith.episode", { ep: EP });
      return { ...r, track: trackInfo(req.pass ?? "proxy"), build };
    },
    async makeVocals(ep) {
      await wait(150);
      need(ep);
      if (!trackPath) throw new MockError("the episode has no recording (attach one first)", 409);
      trackVocals = true;
      emit("seriesmith.vocals", { ep: EP, recording: trackPath, status: "ok", error: "" });
      return { job: "vocals-1", stem: null };
    },
    async setDubFrom(ep, value, pass) {
      await wait(150);
      need(ep);
      if (value !== "recording" && value !== "vocals") throw new MockError("dub_from must be one of recording, vocals", 400);
      dubFrom = value;
      emit("seriesmith.episode", { ep: EP });
      return { track: trackInfo(pass ?? "proxy"), hash: mockHash(files.series.text + "|dub_from=" + value), build: await api.build(ep) };
    },
    // ---- Phase 9c-B: a line from a take as a voice sample ----
    async refsVoiceFromTake(req) {
      await wait(400);
      need(req.ep);
      const src = takeAudio(req.pass, req.shot, req.take);
      if (!status[req.pass]?.shots.some((s) => s.shot === req.shot)) {
        throw new MockError(`${req.shot} is not in the ${req.pass} shotlist`, 404);
      }
      const r = refs.voiceFromTake({
        ref: req.ref, shot: req.shot, take: req.take, pass: req.pass, start: req.start, end: req.end,
        pick: req.pick ?? null, note: req.note ?? "", duration: src?.seconds ?? null, sourceFile: src?.path ?? null,
      });
      emit("seriesmith.episode", { ep: EP });
      return r;
    },
    async comfyQueue() {
      await wait();
      return { running: [], pending: [] };
    },
  };

  // Errors from the mock look like the real client's ApiError (status + message)
  const wrapped = {} as Api;
  for (const [k, fn] of Object.entries(api) as [keyof Api, (...a: unknown[]) => unknown][]) {
    (wrapped as unknown as Record<string, unknown>)[k] = k === "fileUrl" || k === "refFileUrl" || k === "thumbUrl" || k === "presetImageUrl" || k === "downloadUrl" ? fn : async (...a: unknown[]) => {
      try {
        return await fn(...a);
      } catch (e) {
        if (e instanceof MockError) throw new ApiError(e.message, e.status, `/mock/${k}`, e.data);
        // an align 409 carries what is missing, as the route does
        if (e instanceof AlignError) throw new ApiError(e.message, e.status, `/mock/${k}`, e.data ? { error: e.message, ...(e.data as object) } : undefined);
        if (e instanceof FsError || e instanceof RefError || e instanceof CutError || e instanceof MixError || e instanceof CueError) throw new ApiError(e.message, e.status, `/mock/${k}`);
        throw e;
      }
    };
  }
  return Object.assign(wrapped, { outsideEdit, unalign });
}


/** What the mock answers for an edit's import: a dry run's summary of a made-up edit. */
function mockXmlImport(dry: boolean, media: XmlImportMedia, name: string | null): XmlImportSummary {
  if (!dry) throw new MockError("the mock doesn't import edits (seriesmith serve does)", 400);
  const title = name || "The Lighthouse (rough cut)";
  const show = title.replace(/[^A-Za-z0-9._-]+/g, "_").replace(/^[._-]+|[._-]+$/g, "");
  return {
    sequence: "The Lighthouse (rough cut)", title, show, episode: "ep01", in_show: false, from: null, ep: `C:\Shows\${show}\ep01`, fps: 23.976,
    size: [1920, 1080], media, handles: media === "handles" ? 1 : null, shots: 3, black: 1, takes: 2,
    missing: [], sequences: ["sq01"], audio_items: 1, hits: 0, tracks: ["music"],
    proxies: media === "proxies" ? ["sh010"] : [], unplayable: media === "reference" ? ["sh010"] : [],
    clips: [
      { shot: "sh010", name: "Wide on the pier", source: "C:\Footage\A001.mov", dur: 2.75, trim_in: 24, trim_out: 24,
        missing: null, codec: "prores", ...(media === "proxies" ? { proxy: true } : {}),
        ...(media === "reference" ? { plays: false, note: "prores in .mov: it won't play in the editor" } : {}) },
      { shot: "sh030", name: "Close on the lamp", source: "C:\Footage\B002.mp4", dur: 2.5, trim_in: 24, trim_out: 24,
        missing: null, codec: "h264" },
    ],
    warnings: ["a 12-frame gap at 00:00:02.753: a shot of black"],
  };
}
