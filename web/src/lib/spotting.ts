// The spotting sheet's arithmetic (docs/SOUND.md "The spotting sheet"): the
// episode's music map (a row per sequence in cut order, with its cues, beds,
// effects and hits clipped to it), the hits on the cut's clock and the next
// one either way, a cue's hits table (bar and beat, the fit's error and each
// take's), the cues stale under the cut, and a take auditioned in its cue's
// place (the preview's mix only). Pure: the window (SpottingSheet.tsx) and
// the actions (spotActions.ts) use them.

import { barBeat, gridOf, ranks } from "./cue";
import { anchorTime, firstOf } from "./mix";
import type { PlayItem } from "./playlist";
import type { Audition } from "../store";
import type { Anchor, CuePlan, CueSpec, CueSummary, CueTake, HitKind, Mix, MixBed, MixFx, MixItem } from "../types";

// ---------------------------------------------------------------------------
// the map
// ---------------------------------------------------------------------------

/** A row of the music map: a run of the cut's clips of one sequence. */
export interface MapRow {
  /** the sequence's id (null: shots with none) */
  seq: string | null;
  /** cut seconds it covers */
  start: number;
  end: number;
  shots: { shot: string; start: number; end: number }[];
}

/** The cut in rows: each run of consecutive clips of one sequence, in cut order (a sequence the cut splits is two rows). */
export function sequenceRows(items: PlayItem[], seqOf: (shot: string) => string | null | undefined): MapRow[] {
  const rows: MapRow[] = [];
  for (const it of items) {
    const seq = seqOf(it.shot) ?? null;
    const last = rows[rows.length - 1];
    const shot = { shot: it.shot, start: it.start, end: it.start + it.dur };
    if (last && last.seq === seq) {
      last.shots.push(shot);
      last.end = shot.end;
    } else {
      rows.push({ seq, start: shot.start, end: shot.end, shots: [shot] });
    }
  }
  return rows;
}

/** A cue on the cut's clock, with what the map marks on it. */
export interface CueBlock {
  id: string;
  label: string;
  kind: "score" | "song";
  start: number;
  end: number;
  /** the take its mix item plays (null: none placed on this pass) */
  inMix: number | null;
  /** finished takes */
  ok: number;
  /** what's moved under the take in the mix (or, with none placed, under every finished take: the first's words) */
  stale: string[];
}

/** The take a mix item of cue `cue` plays (`sound/<cue>/tNN.wav`), else null. */
export function takeOfItem(cue: string, it: MixItem | undefined): number | null {
  const m = it?.path.match(/^sound\/([^/]+)\/t(\d{2,3})\.wav$/);
  return m && m[1] === cue ? Number(m[2]) : null;
}

/** Whether a cue wants rendering again: the take in the mix is stale, or, with none placed, every finished one is. */
export function cueIsStale(c: CueSummary): boolean {
  if (c.stale?.length) return true;
  return c.in_mix == null && c.ok > 0 && (c.stale_takes?.length ?? 0) >= c.ok;
}

/** The cues stale under the cut (cueIsStale), in id order. */
export function staleCues(cues: CueSummary[]): CueSummary[] {
  return cues.filter(cueIsStale).sort((a, b) => a.spec.id.localeCompare(b.spec.id));
}

/** The cues on the cut's clock (those whose anchors are in it), by start. The take in the mix is the mix's when the list doesn't say. */
export function cueBlocks(cues: CueSummary[], items: PlayItem[], fps: number, mix: Mix | undefined): CueBlock[] {
  const out: CueBlock[] = [];
  for (const c of cues) {
    const a = anchorTime(items, c.spec.in, fps);
    const b = anchorTime(items, c.spec.out, fps);
    if (a == null || b == null || b <= a) continue;
    const inMix = c.in_mix !== undefined ? c.in_mix : takeOfItem(c.spec.id, mix?.items?.find((i) => i.id === c.spec.id));
    const stale = c.stale?.length ? c.stale : cueIsStale(c) ? ["every finished take: the cut has moved since it was rendered"] : [];
    out.push({ id: c.spec.id, label: c.spec.label || c.spec.id, kind: c.spec.kind ?? "score", start: a, end: b, inMix, ok: c.ok, stale });
  }
  return out.sort((x, y) => x.start - y.start || x.id.localeCompare(y.id));
}

/** A block clipped to a row: where it starts and ends in it, and whether it runs on from the row before or into the next. */
export type InRow<T> = T & { a: number; b: number; fromBefore: boolean; onAfter: boolean };

export function inRow<T extends { start: number; end: number }>(row: Pick<MapRow, "start" | "end">, blocks: T[]): InRow<T>[] {
  const out: InRow<T>[] = [];
  for (const x of blocks) {
    if (x.end <= row.start || x.start >= row.end) continue;
    out.push({ ...x, a: Math.max(x.start, row.start), b: Math.min(x.end, row.end), fromBefore: x.start < row.start - 1e-6, onAfter: x.end > row.end + 1e-6 });
  }
  return out;
}

/** The places' beds as map blocks (the server lays them: their own cut seconds). */
export const bedBlocks = (beds: MixBed[] | undefined) =>
  (beds ?? []).map((b) => ({ id: b.place, label: b.label || b.place, start: b.start, end: b.end, exists: b.exists, mute: b.mute }));

/** The shots' effects as map blocks, the stale ones marked. */
export const fxBlocks = (fx: MixFx[] | undefined) =>
  (fx ?? []).map((f) => ({ id: f.shot, label: `${f.shot} t${String(f.take).padStart(2, "0")}`, start: f.start, end: f.end, exists: f.exists, stale: f.stale, heard: f.heard }));

// ---------------------------------------------------------------------------
// hits on the cut's clock
// ---------------------------------------------------------------------------

export interface CutHit {
  id: string;
  name: string;
  kind: HitKind;
  must: boolean;
  at: Anchor;
  /** cut seconds */
  t: number;
}

/** The mix's hits whose shots are in the cut, in time order. */
export function cutHits(mix: Mix | undefined, items: PlayItem[], fps: number): CutHit[] {
  const out: CutHit[] = [];
  for (const h of mix?.hits ?? []) {
    const t = anchorTime(items, h.at, fps);
    if (t != null) out.push({ id: h.id, name: h.name || h.id, kind: h.kind ?? "accent", must: h.must !== false, at: h.at, t });
  }
  return out.sort((a, b) => a.t - b.t || a.id.localeCompare(b.id));
}

/** The next hit after `pos` (dir 1) or before it (-1), more than half a frame away; null: none that way. */
export function nextHit<T extends { t: number }>(hits: T[], pos: number, dir: 1 | -1, fps: number): T | null {
  const eps = 0.5 / (fps || 24);
  if (dir > 0) return hits.find((h) => h.t > pos + eps) ?? null;
  for (let i = hits.length - 1; i >= 0; i--) if (hits[i].t < pos - eps) return hits[i];
  return null;
}

/** "00:01:23:12": cut seconds as hours, minutes, seconds and frames. */
export function timecode(t: number, fps: number): string {
  const r = Math.max(1, Math.round(fps || 24));
  const f = Math.max(0, Math.round(t * (fps || 24)));
  const ff = f % r;
  const s = Math.floor(f / r);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(Math.floor(s / 3600))}:${p(Math.floor(s / 60) % 60)}:${p(s % 60)}:${p(ff)}`;
}

// ---------------------------------------------------------------------------
// the selected cue: its hits table
// ---------------------------------------------------------------------------

/** A take's column in the hits table. */
export interface TakeColumn {
  take: number;
  /** 1 for the best (as the server ranks them) */
  rank: number;
  inMix: boolean;
  stale: boolean;
}

export interface HitRow {
  id: string;
  name: string;
  kind: HitKind;
  must: boolean;
  /** the cue's end: cut there, neither fitted nor measured */
  ends: boolean;
  at: Anchor | null;
  /** cut seconds (null: its cue's in point isn't in the cut) */
  t: number | null;
  /** seconds from the cue's in point */
  tau: number;
  /** "5.3": the bar and beat it lands on */
  barBeat: string;
  /** frames the fit leaves it off its line (null: an end) */
  fit: number | null;
  /** frames, one per take column (null: nothing heard there) */
  takes: (number | null)[];
}

/** The measured takes, best first, as the table's columns. */
export function takeColumns(takes: CueTake[], inMix: number | null): TakeColumn[] {
  const rk = ranks(takes);
  const out: TakeColumn[] = [];
  takes.forEach((t, i) => {
    if (rk[i] != null) out.push({ take: t.take, rank: rk[i]!, inMix: t.take === inMix, stale: !!t.stale?.length });
  });
  return out;
}

/** A cue's hits as the table's rows: each where it is, where it lands in the music, the fit's error and each take's. */
export function hitTable(spec: CueSpec, plan: CuePlan, takes: CueTake[], columns: TakeColumn[], items: PlayItem[], fps: number): HitRow[] {
  const g = gridOf(plan, spec);
  const t0 = anchorTime(items, spec.in, fps);
  const byTake = new Map(takes.map((t) => [t.take, t]));
  return plan.hits.map((h, i) => ({
    id: h.id, name: h.name, kind: h.kind, must: h.must, ends: !!h.ends, at: h.at ?? null,
    t: t0 == null ? null : t0 + h.t, tau: h.t, barBeat: barBeat(g, h.t).label,
    fit: plan.fit.errors[i] ?? null,
    takes: columns.map((c) => byTake.get(c.take)?.measured?.hit_errors?.[i] ?? null),
  }));
}

/** The fit as words: asked, fitted, the stretch, the worst must-hit. */
export function fitWords(spec: CueSpec, plan: CuePlan): { asked: number; fitted: number; change: string; stretch: number; askBpm: number; worst: number } {
  const asked = spec.bpm ?? 100;
  const d = (plan.fit.bpm / asked - 1) * 100;
  return { asked, fitted: plan.fit.bpm, change: Math.abs(d) < 0.05 ? "" : `${d > 0 ? "+" : ""}${d.toFixed(1)} %`, stretch: plan.fit.stretch, askBpm: plan.fit.ask_bpm, worst: plan.fit.worst_must };
}

/** A tempo picked from the alternatives: the cue held at it (fixed), as the cue window's tempo field with fixed ticked. */
export function withTempo(spec: CueSpec, bpm: number): CueSpec {
  return { ...spec, bpm: Math.round(bpm * 1000) / 1000, fixed_tempo: true };
}

// ---------------------------------------------------------------------------
// audition
// ---------------------------------------------------------------------------

/** What a take auditioned against the picture needs: its file, where its in point is, a bar's fade (null: it isn't finished). */
export function auditionOf(ep: string, pass: Audition["pass"], spec: CueSpec, plan: CuePlan, take: CueTake): Audition | null {
  if (take.status !== "ok" || !take.file || !take.measured) return null;
  return {
    ep, pass, cue: spec.id, take: take.take, path: take.file,
    offset: Math.max(0, Math.round(take.measured.offset * 1000) / 1000),
    fadeOut: Math.max(1, Math.round(plan.bar * plan.fps)), in: spec.in, out: spec.out, label: spec.label || spec.id,
  };
}

/**
 * The mix with the auditioned take in its cue's place: the cue's music item
 * replaced (or one added) from the cue's in point to its out point, with its
 * offset and a bar's fade, as a pick would lay it but without the gain fit (its
 * item's level kept). The mix itself isn't changed.
 */
export function auditionMix(mix: Mix, a: Audition): Mix {
  const was = mix.items?.find((i) => i.id === a.cue);
  const item: MixItem = {
    id: a.cue, track: was?.track ?? firstOf(mix, "music") ?? "music", path: a.path, in: a.in, out: a.out,
    offset: a.offset, fade_out: a.fadeOut, label: a.label,
    ...(was?.gain_db != null ? { gain_db: was.gain_db } : {}),
  };
  return { ...mix, items: [...(mix.items ?? []).filter((i) => i.id !== a.cue), item] };
}
