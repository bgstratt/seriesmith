// Cutting to music (docs/SOUND.md phase 5), pure: the beats of the music in the
// pass's mix on the cut's clock, and a trim's edge snapped to them. The server
// gives each music file's beat grid (GET /seriesmith/mix/beats: a cue take's
// from its sidecar, any other file's measured once and kept beside it); this
// places them as the mix places its items (lib/mix anchorTime), and the
// episode's recording as `assemble --audio master` lays it (lib/recording).

import type { Mix } from "../types";
import { anchorTime } from "./mix";
import { totalDuration, type PlayItem } from "./playlist";
import { masterStart } from "./recording";

/** A file's steady beat grid (seconds into the file). */
export interface BeatGrid {
  bpm: number;
  /** the first beat */
  first: number;
  /** the first downbeat (a beat of the same grid) */
  downbeat: number;
  beats_per_bar: number;
  /** the file's length (null: not read: a cue take) */
  seconds: number | null;
  /** a pulse to snap to (a measured file may have none: speech, soft score) */
  steady: boolean;
  source: "cue" | "measured";
}

/** GET /seriesmith/mix/beats */
export interface MixBeats {
  items: { id: string; path: string; grid: BeatGrid | null }[];
  recording: { path: string; grid: BeatGrid | null } | null;
}

/** A beat on the cut's clock. `shot`: the shot its music is anchored to (null: the
 * recording, which runs from the cut's first clip). */
export interface Beat {
  t: number;
  down: boolean;
  shot: string | null;
}

/** at most this many beats from one file (a 10-minute song at 180 bpm is 1800) */
const MOST = 4000;

/** A grid's beats from `a` to `b` seconds into its file: [seconds, downbeat]. */
export function gridBeats(g: BeatGrid, a: number, b: number): [number, boolean][] {
  const beat = 60 / g.bpm;
  if (!(beat > 0) || !(b > a)) return [];
  const per = Math.max(1, Math.round(g.beats_per_bar || 4));
  const out: [number, boolean][] = [];
  for (let k = Math.max(0, Math.ceil((a - g.first) / beat - 1e-9)); out.length < MOST; k++) {
    const s = g.first + k * beat;
    if (s > b + 1e-9) break;
    const n = Math.round((s - g.downbeat) / beat);
    out.push([s, ((n % per) + per) % per === 0]);
  }
  return out;
}

/**
 * The beats of the music in the mix on the cut's clock, in time order: each
 * music item with a steady grid, from its in to its out (or its file's end),
 * clamped to the cut; when none has one, the episode's recording's (as
 * `assemble --audio master` lays it under the cut), when that has one.
 */
export function cutBeats(items: PlayItem[], mix: Mix, beats: MixBeats | undefined, fps: number, recordingBase = 0): Beat[] {
  if (!beats || !items.length) return [];
  const f = fps || 24;
  const total = totalDuration(items);
  const out: Beat[] = [];
  for (const b of beats.items) {
    const it = mix.items?.find((x) => x.id === b.id && x.path === b.path);
    if (!it || !b.grid?.steady) continue;
    const s = anchorTime(items, it.in, f);
    if (s == null) continue;
    const offset = it.offset ?? 0;
    let e = it.out ? anchorTime(items, it.out, f) : b.grid.seconds != null ? s + b.grid.seconds - offset : total;
    if (e == null) continue;
    e = Math.min(total, e);
    const from = Math.max(0, s);
    if (!(e > from)) continue;
    // the file loops past its end when the item does: its grid isn't the loop's, so a
    // looped item's beats stop where the file does
    const fileEnd = b.grid.seconds != null ? s + b.grid.seconds - offset : e;
    for (const [x, down] of gridBeats(b.grid, offset + (from - s), offset + (Math.min(e, fileEnd) - s))) {
      out.push({ t: s + (x - offset), down, shot: it.in.shot });
    }
  }
  const rec = beats.recording?.grid;
  if (!out.length && rec?.steady) {
    const start = masterStart(items, f, recordingBase);
    for (const [x, down] of gridBeats(rec, start, start + total)) out.push({ t: x - start, down, shot: null });
  }
  return out.sort((a, b) => a.t - b.t);
}

/** Pixels within which a trim snaps to a beat, and to a downbeat (stronger). */
export const SNAP_PX = 7;
export const SNAP_DOWN_PX = 12;

/**
 * The beats a trim of `shot` can snap to: those that stay where they are while
 * it changes. A trim moves every clip after the shot, and music anchored to
 * them with it; music anchored before the shot stays, and music anchored to
 * the shot itself stays when its tail is trimmed (its frames don't move) but
 * not its head. The recording stays unless it's the first clip's head (the
 * recording starts there).
 */
export function fixedBeats(beats: Beat[], items: PlayItem[], shot: string, side: "in" | "out"): Beat[] {
  const at = new Map(items.map((i, k) => [i.shot, k]));
  const k = at.get(shot);
  if (k == null) return [];
  return beats.filter((b) => {
    if (b.shot == null) return !(k === 0 && side === "in");
    const j = at.get(b.shot);
    return j != null && (j < k || (j === k && side === "out"));
  });
}

/**
 * A trim of a clip's edge snapped so the clip ends on a beat (where the cut to
 * the next clip falls): the nearest of `beats` (fixedBeats) to where the drag
 * would put the cut, within `tol` seconds, a downbeat within `downTol` and
 * preferred over a beat as near. Either edge snaps the cut at the clip's end:
 * a head trim moves it as a tail trim does (the clip's start is the clip
 * before's end). `a` and `b` are the trims the drag would set; `a0` / `b0` the
 * clip's own (as `it` plays them). Returns the trims to set and the beat (null:
 * nothing near, the trims as given).
 */
export function snapTrim(p: {
  it: PlayItem; side: "in" | "out"; total: number; a0: number; b0: number; a: number; b: number;
  beats: Beat[]; fps: number; tol: number; downTol: number; clamp: (side: "in" | "out", want: number, other: number) => number;
}): { a: number; b: number; beat: Beat | null } {
  const f = p.fps || 24;
  const len0 = p.total - p.a0 - p.b0;
  const end0 = p.it.start + p.it.dur;
  const end = end0 + (p.total - p.a - p.b - len0) / f;
  let best: Beat | null = null;
  let score = Infinity;
  for (const beat of p.beats) {
    const d = Math.abs(beat.t - end);
    if (d > (beat.down ? p.downTol : p.tol)) continue;
    // a downbeat wins over a beat up to its stronger pull's share nearer
    const s = d / (beat.down ? p.downTol : p.tol);
    if (s < score) {
      score = s;
      best = beat;
    }
  }
  if (!best) return { a: p.a, b: p.b, beat: null };
  const len = len0 + Math.round((best.t - end0) * f);
  let { a, b } = p;
  if (p.side === "in") a = p.clamp("in", p.total - b - len, b);
  else b = p.clamp("out", p.total - a - len, a);
  const got = end0 + (p.total - a - b - len0) / f;
  // clamped short of it (the take ends first): no snap
  if (Math.abs(got - best.t) > 1 / f + 1e-6) return { a: p.a, b: p.b, beat: null };
  return { a, b, beat: best };
}

/** Which bar and beat a beat is, counted from its music's first downbeat (1-based), for the tip. */
export function beatLabel(beat: Beat, beats: Beat[]): string {
  const upTo = beats.filter((b) => b.shot === beat.shot && b.t <= beat.t + 1e-9);
  const bar = upTo.filter((b) => b.down).length;
  if (!bar) return "a beat";
  if (beat.down) return `bar ${bar}`;
  return `bar ${bar} beat ${upTo.length - upTo.map((b) => b.down).lastIndexOf(true)}`;
}
