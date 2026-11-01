// The episode's mix (docs/SOUND.md), pure: anchors on the cut's clock and on
// the timeline, and the edits (items, hits, tracks) as new mixes. An anchor is
// a shot and a frame of its take at the cut's rate, counted before trims, so a
// clip whose take starts `inT` seconds in shows frame f at (f / fps - inT)
// seconds into it (mix.py's shot_origins / place are the Python reference).
// The timeline isn't one time axis (sequence labels, the narrowest clips,
// left-out stubs take room), so x is measured per clip: each clip's own
// pixels per second, from its box.

import type { Anchor, HitKind, Mix, MixHit, MixItem, MixTrack, MixTrackSettings, MixResult } from "../types";
import { locate, totalDuration, type PlayItem } from "./playlist";

export const TRACKS: MixTrack[] = ["dialogue", "effects", "ambience", "music"];
export const TRACK_LABEL: Record<MixTrack, string> = { dialogue: "Dialogue", effects: "Effects", ambience: "Ambience", music: "Music" };
export const HIT_KINDS: HitKind[] = ["accent", "arrive", "drop", "turn"];
export const HIT_KIND_TITLE: Record<HitKind, string> = {
  accent: "a sting or a downbeat on the frame",
  arrive: "the music's peak arrives here",
  drop: "the music cuts out or thins",
  turn: "a change of key or mood",
};
export const GAIN_MIN = -60;
export const GAIN_MAX = 12;
export const FADE_MAX = 2400;
const ID = /^[A-Za-z0-9_-]{1,40}$/;

export const validId = (id: string) => ID.test(id);

/** dB as a gain (the floor is silence). */
export function dbToGain(db: number): number {
  return !Number.isFinite(db) || db <= GAIN_MIN ? 0 : 10 ** (db / 20);
}

export const clampDb = (db: number) => Math.round(Math.min(GAIN_MAX, Math.max(GAIN_MIN, Number.isFinite(db) ? db : 0)) * 10) / 10;

// ---------------------------------------------------------------------------
// anchors on the cut's clock
// ---------------------------------------------------------------------------

/** Where an anchor plays on the cut's clock (seconds), or null when its shot isn't in it. */
export function anchorTime(items: PlayItem[], a: Anchor, fps: number): number | null {
  const it = items.find((i) => i.shot === a.shot);
  return it ? it.start + a.frame / (fps || 24) - it.inT : null;
}

/** The anchor at cut time `t`: the clip playing then, and the frame of its take. */
export function timeAnchor(items: PlayItem[], t: number, fps: number): Anchor | null {
  const { index, offset } = locate(items, t);
  const it = items[index];
  return it ? { shot: it.shot, frame: Math.max(0, Math.round((it.inT + offset) * (fps || 24))) } : null;
}

/** An anchor moved by `dt` seconds on the cut's clock, re-anchored to the clip there. */
export function shiftAnchor(items: PlayItem[], a: Anchor, dt: number, fps: number): Anchor | null {
  const t = anchorTime(items, a, fps);
  return t == null ? null : timeAnchor(items, Math.min(totalDuration(items), Math.max(0, t + dt)), fps);
}

export const sameAnchor = (a: Anchor | null | undefined, b: Anchor | null | undefined) =>
  (!a && !b) || (!!a && !!b && a.shot === b.shot && a.frame === b.frame);

// ---------------------------------------------------------------------------
// the timeline's x
// ---------------------------------------------------------------------------

/** A clip's box on the track (measured: its `[data-shot]` column). */
export interface ClipBox {
  shot: string;
  left: number;
  width: number;
}

/** A playing clip's box with its time: what x <-> time goes through. */
export interface Lay extends ClipBox {
  start: number;
  dur: number;
  inT: number;
  /** pixels per second in this clip */
  pps: number;
}

/** The boxes of the clips Play all plays, in its order (stubs and orphans left out). */
export function layout(boxes: ClipBox[], items: PlayItem[]): Lay[] {
  const by = new Map(boxes.map((b) => [b.shot, b]));
  const out: Lay[] = [];
  for (const it of items) {
    const b = by.get(it.shot);
    if (!b) continue;
    out.push({ ...b, start: it.start, dur: it.dur, inT: it.inT, pps: it.dur > 0 ? b.width / it.dur : 0 });
  }
  return out;
}

/** x of cut time `t`: in the clip playing then, at its own scale; past either end, at the last clip's. */
export function timeX(lay: Lay[], t: number): number {
  if (!lay.length) return 0;
  let g = lay[0];
  for (const l of lay) {
    if (l.start <= t) g = l;
    else break;
  }
  return g.left + (t - g.start) * g.pps;
}

/** The clip under x, or the nearest one. */
function layAt(lay: Lay[], x: number): Lay | null {
  let best: Lay | null = null;
  let dist = Infinity;
  for (const l of lay) {
    if (x >= l.left && x <= l.left + l.width) return l;
    const d = x < l.left ? l.left - x : x - (l.left + l.width);
    if (d < dist) {
      dist = d;
      best = l;
    }
  }
  return best;
}

/** Cut time at x (a gap between clips: the nearer clip's edge). */
export function xTime(lay: Lay[], x: number): number {
  const l = layAt(lay, x);
  if (!l || !(l.pps > 0)) return l?.start ?? 0;
  return l.start + Math.min(l.dur, Math.max(0, (x - l.left) / l.pps));
}

/** The anchor at x: the clip under it and the frame of its take there. */
export function xAnchor(lay: Lay[], x: number, fps: number): Anchor | null {
  const l = layAt(lay, x);
  if (!l) return null;
  const off = l.pps > 0 ? Math.min(l.dur, Math.max(0, (x - l.left) / l.pps)) : 0;
  return { shot: l.shot, frame: Math.max(0, Math.round((l.inT + off) * (fps || 24))) };
}

/** x of an anchor, or null when its shot isn't in the cut. */
export function anchorX(lay: Lay[], items: PlayItem[], a: Anchor, fps: number): number | null {
  const t = anchorTime(items, a, fps);
  return t == null ? null : timeX(lay, t);
}

// ---------------------------------------------------------------------------
// items on the cut's clock
// ---------------------------------------------------------------------------

/**
 * Where an item plays on the cut's clock: from its `in` to its `out`, or (no
 * out) until its file ends (`fileSecs`, null while unknown: then `end` is
 * null). Clamped to the cut, as assemble lays it. Null when an anchor's shot
 * isn't in the cut (assemble drops it).
 */
export function itemSpan(items: PlayItem[], it: MixItem, fps: number, fileSecs: number | null): { start: number; end: number | null } | null {
  const s = anchorTime(items, it.in, fps);
  if (s == null) return null;
  let e: number | null;
  if (it.out) {
    e = anchorTime(items, it.out, fps);
    if (e == null) return null;
  } else {
    e = fileSecs != null ? s + Math.max(0, fileSecs - (it.offset ?? 0)) : null;
  }
  const total = totalDuration(items);
  return { start: Math.max(0, s), end: e == null ? null : Math.min(total, e) };
}

/** An item to play: its span on the cut's clock and how (Web Audio, MixAudio). */
export interface PlayEntry {
  id: string;
  track: MixTrack;
  path: string;
  /** cut seconds */
  start: number;
  /** null: until the file ends (from `offset`) */
  end: number | null;
  /** seconds into the file at `start` */
  offset: number;
  gain: number;
  /** seconds */
  fadeIn: number;
  fadeOut: number;
  loop: boolean;
}

/** The mix's items as Play all plays them (points are left out: the preview holds each item's gain). */
export function playPlan(items: PlayItem[], mix: Mix, fps: number): PlayEntry[] {
  const f = fps || 24;
  const total = totalDuration(items);
  const out: PlayEntry[] = [];
  for (const it of mix.items ?? []) {
    const s = anchorTime(items, it.in, f);
    const e = it.out ? anchorTime(items, it.out, f) : null;
    if (s == null || (it.out && e == null)) continue;
    // an item starting before the cut plays from where the cut does
    const start = Math.max(0, s);
    const end = e == null ? null : Math.min(total, e);
    if (end != null && end <= start) continue;
    out.push({
      id: it.id, track: it.track, path: it.path, start, end, offset: (it.offset ?? 0) + (start - s),
      gain: dbToGain(it.gain_db ?? 0), fadeIn: (it.fade_in ?? 0) / f, fadeOut: (it.fade_out ?? 0) / f, loop: !!it.loop,
    });
  }
  return out;
}

/** An entry's end once its file's length is known (and the cut's end). */
export function entryEnd(e: PlayEntry, fileSecs: number, total: number): number {
  return Math.min(total, e.end ?? e.start + Math.max(0, fileSecs - e.offset));
}

/** An entry's level (its gain and fades) `t` cut seconds in, `end` its end. */
export function entryLevel(e: PlayEntry, t: number, end: number): number {
  let v = 1;
  if (e.fadeIn > 0) v = Math.min(v, (t - e.start) / e.fadeIn);
  if (e.fadeOut > 0) v = Math.min(v, (end - t) / e.fadeOut);
  return e.gain * Math.max(0, Math.min(1, v));
}

// ---------------------------------------------------------------------------
// tracks: the mix's over the series config's, over the defaults
// ---------------------------------------------------------------------------

export interface TrackState {
  gain_db: number;
  mute: boolean;
  solo: boolean;
}

export function trackState(res: Pick<MixResult, "mix" | "series"> | undefined, name: MixTrack): TrackState {
  const s = res?.series?.tracks?.[name] ?? {};
  const m = res?.mix?.tracks?.[name] ?? {};
  return { gain_db: m.gain_db ?? s.gain_db ?? 0, mute: !!(m.mute ?? s.mute), solo: !!(m.solo ?? s.solo) };
}

/** What each track sounds at: its fader, silenced when muted or another is soloed. */
export function trackGains(res: Pick<MixResult, "mix" | "series"> | undefined): Record<MixTrack, number> {
  const st = Object.fromEntries(TRACKS.map((t) => [t, trackState(res, t)])) as Record<MixTrack, TrackState>;
  const soloed = TRACKS.some((t) => st[t].solo);
  return Object.fromEntries(TRACKS.map((t) => {
    const x = st[t];
    return [t, x.mute || (soloed && !x.solo) ? 0 : dbToGain(x.gain_db)];
  })) as Record<MixTrack, number>;
}

/** A track's settings changed, defaults dropped (as mix.json keeps them). */
export function setTrack(mix: Mix, name: MixTrack, patch: Partial<MixTrackSettings>): Mix {
  const t: MixTrackSettings = { ...(mix.tracks?.[name] ?? {}), ...patch };
  if (!t.gain_db) delete t.gain_db;
  else t.gain_db = clampDb(t.gain_db);
  if (!t.mute) delete t.mute;
  if (!t.solo) delete t.solo;
  if (t.duck_db == null) delete t.duck_db;
  const tracks = { ...(mix.tracks ?? {}) };
  if (Object.keys(t).length) tracks[name] = t;
  else delete tracks[name];
  const out: Mix = { ...mix, tracks };
  if (!Object.keys(tracks).length) delete out.tracks;
  return out;
}

// ---------------------------------------------------------------------------
// items
// ---------------------------------------------------------------------------

const PREFIX: Record<MixTrack, string> = { dialogue: "d", effects: "fx", ambience: "amb", music: "m" };

/** A new id: `prefix` and the next free two-digit number. */
export function newId(prefix: string, taken: Iterable<string>): string {
  const used = new Set(taken);
  for (let n = 1; ; n++) {
    const id = `${prefix}${String(n).padStart(2, "0")}`;
    if (!used.has(id)) return id;
  }
}

export const newItemId = (mix: Mix, track: MixTrack) => newId(PREFIX[track], (mix.items ?? []).map((i) => i.id));
export const newHitId = (mix: Mix) => newId("h", (mix.hits ?? []).map((h) => h.id));

/** An item with its defaults dropped. */
export function cleanItem(it: MixItem): MixItem {
  const o: MixItem = { ...it };
  if (!o.out) delete o.out;
  for (const k of ["offset", "gain_db", "fade_in", "fade_out"] as const) if (!o[k]) delete o[k];
  if (o.gain_db != null) o.gain_db = clampDb(o.gain_db);
  for (const k of ["fade_in", "fade_out"] as const) if (o[k] != null) o[k] = Math.max(0, Math.min(FADE_MAX, Math.round(o[k]!)));
  if (o.offset != null) o.offset = Math.round(Math.max(0, o.offset) * 1000) / 1000;
  if (!o.loop) delete o.loop;
  if (!o.label?.trim()) delete o.label;
  else o.label = o.label.trim().slice(0, 120);
  if (!o.points?.length) delete o.points;
  return o;
}

export function addItem(mix: Mix, it: MixItem): Mix {
  return { ...mix, items: [...(mix.items ?? []), cleanItem(it)] };
}

/** One item changed (null: no such item). */
export function patchItem(mix: Mix, id: string, patch: Partial<MixItem>): Mix | null {
  const items = mix.items ?? [];
  const i = items.findIndex((x) => x.id === id);
  if (i < 0) return null;
  const next = items.slice();
  next[i] = cleanItem({ ...items[i], ...patch });
  return { ...mix, items: next };
}

export function removeItem(mix: Mix, id: string): Mix | null {
  const items = (mix.items ?? []).filter((x) => x.id !== id);
  if (items.length === (mix.items ?? []).length) return null;
  const out: Mix = { ...mix, items };
  if (!items.length) delete out.items;
  return out;
}

/**
 * An item moved so it starts at `at`: its `out` moves by as much on the cut's
 * clock, re-anchored to the clip it then falls in. Null when nothing moves.
 */
export function moveItem(mix: Mix, id: string, at: Anchor, items: PlayItem[], fps: number): Mix | null {
  const it = mix.items?.find((x) => x.id === id);
  if (!it || sameAnchor(it.in, at)) return null;
  const t0 = anchorTime(items, it.in, fps);
  const t1 = anchorTime(items, at, fps);
  if (t0 == null || t1 == null) return null;
  const out = it.out ? shiftAnchor(items, it.out, t1 - t0, fps) : null;
  if (it.out && !out) return null;
  return patchItem(mix, id, { in: at, out: it.out ? out : undefined });
}

/**
 * An edge of an item set to `at`. Its head keeps the sound where it was (the
 * offset into the file moves with it, never below 0; a loop's stays); its
 * tail is its `out`. Either edge stays a frame clear of the other. Null when
 * that leaves nothing or changes nothing.
 */
export function trimItem(mix: Mix, id: string, side: "in" | "out", at: Anchor, items: PlayItem[], fps: number, fileSecs: number | null): Mix | null {
  const it = mix.items?.find((x) => x.id === id);
  if (!it) return null;
  const f = fps || 24;
  const span = itemSpan(items, it, f, fileSecs);
  const t = anchorTime(items, at, f);
  if (!span || t == null) return null;
  if (side === "in") {
    if (sameAnchor(it.in, at)) return null;
    const t0 = anchorTime(items, it.in, f)!;
    if (span.end != null && t > span.end - 1 / f) return null;
    if (it.loop) return patchItem(mix, id, { in: at });
    const offset = (it.offset ?? 0) + (t - t0);
    if (offset < -0.5 / f) return null;
    return patchItem(mix, id, { in: at, offset: Math.max(0, offset) });
  }
  if (sameAnchor(it.out, at) || t < span.start + 1 / f) return null;
  return patchItem(mix, id, { out: at });
}

// ---------------------------------------------------------------------------
// hits
// ---------------------------------------------------------------------------

/** A hit with its defaults dropped (accent, must). */
export function cleanHit(h: MixHit): MixHit {
  const o: MixHit = { ...h };
  if (!o.name?.trim()) delete o.name;
  else o.name = o.name.trim().slice(0, 120);
  if (!o.kind || o.kind === "accent") delete o.kind;
  if (o.must !== false) delete o.must;
  return o;
}

export function addHit(mix: Mix, at: Anchor, name = ""): { mix: Mix; id: string } {
  const id = newHitId(mix);
  return { mix: { ...mix, hits: [...(mix.hits ?? []), cleanHit({ id, at, name })] }, id };
}

export function patchHit(mix: Mix, id: string, patch: Partial<MixHit>): Mix | null {
  const hits = mix.hits ?? [];
  const i = hits.findIndex((x) => x.id === id);
  if (i < 0) return null;
  const next = hits.slice();
  next[i] = cleanHit({ ...hits[i], ...patch });
  return { ...mix, hits: next };
}

export function removeHit(mix: Mix, id: string): Mix | null {
  const hits = (mix.hits ?? []).filter((x) => x.id !== id);
  if (hits.length === (mix.hits ?? []).length) return null;
  const out: Mix = { ...mix, hits };
  if (!hits.length) delete out.hits;
  return out;
}

/** The hits in cut order (those whose shot isn't in the cut last). */
export function hitsInOrder(mix: Mix, items: PlayItem[], fps: number): (MixHit & { t: number | null })[] {
  return (mix.hits ?? []).map((h) => ({ ...h, t: anchorTime(items, h.at, fps) }))
    .sort((a, b) => (a.t ?? Infinity) - (b.t ?? Infinity));
}

/** Two mixes say the same (key order aside: both come from the same code). */
export function sameMix(a: Mix, b: Mix): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

/** A file's name from its path, for a block's label. */
export const fileName = (path: string) => path.split("/").pop() ?? path;
