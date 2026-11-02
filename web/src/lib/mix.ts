// The episode's mix (docs/SOUND.md), pure: anchors on the cut's clock and on
// the timeline, and the edits (items, hits, tracks) as new mixes. An anchor is
// a shot and a frame of its take at the cut's rate, counted before trims, so a
// clip whose take starts `inT` seconds in shows frame f at (f / fps - inT)
// seconds into it (mix.py's shot_origins / place are the Python reference).
// The timeline isn't one time axis (sequence labels, the narrowest clips,
// left-out stubs take room), so x is measured per clip: each clip's own
// pixels per second, from its box.

import type { Anchor, HitKind, Mix, MixBed, MixBedSettings, MixFx, MixFxSettings, MixHit, MixItem, MixPoint, MixTrack, MixTrackDef, MixTrackSettings, MixResult, MixVoice, TrackKind } from "../types";
import { locate, totalDuration, type PlayItem } from "./playlist";

/** the default tracks, each its own kind (the kinds a track can be) */
export const TRACKS: TrackKind[] = ["dialogue", "effects", "ambience", "music"];
export const KINDS: TrackKind[] = TRACKS;
/** the default tracks' names, and a kind's in words */
export const TRACK_LABEL: Record<TrackKind, string> = { dialogue: "Dialogue", effects: "Effects", ambience: "Ambience", music: "Music" };
export const HIT_KINDS: HitKind[] = ["accent", "arrive", "drop", "turn"];
export const HIT_KIND_TITLE: Record<HitKind, string> = {
  accent: "a sting or a downbeat on the frame",
  arrive: "the music's peak arrives here",
  drop: "the music cuts out or thins",
  turn: "a change of key or mood",
};
/** each track's fader when nothing sets it (mix.py's GAIN_DEFAULT; the server's `defaults.gain_db`) */
export const GAIN_DEFAULT: Record<TrackKind, number> = { dialogue: 0, effects: 0, ambience: 0, music: -12 };
/** how far each track dips under speech when nothing sets it (mix.py's DUCK_DEFAULT) */
export const DUCK_DEFAULT: Partial<Record<TrackKind, number>> = { effects: 0, ambience: -6, music: -9 };
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
// the mix's tracks (docs/SOUND.md phase 6): its own list (`track_list`), else the four
// defaults; a track's kind decides its default fader and duck depth, what a region
// reaches and whether it joins the M&E (mix.py's track_list / kinds / first_of)
// ---------------------------------------------------------------------------

/** a mix has at most this many tracks (mix.py's MAX_TRACKS) */
export const MAX_TRACKS = 16;
/** ids a track can't have: its stem would be one of these (mix.py's RESERVED_IDS) */
const RESERVED = new Set(["me", "mix", "con", "prn", "aux", "nul", ...[1, 2, 3, 4, 5, 6, 7, 8, 9].flatMap((i) => [`com${i}`, `lpt${i}`])]);

export interface TrackDef {
  id: MixTrack;
  kind: TrackKind;
  label: string;
}

const DEFAULT_LIST: MixTrackDef[] = TRACKS.map((k) => ({ id: k, kind: k }));

/** The mix's tracks in lane order, each named. */
export function trackList(mix: Mix | undefined): TrackDef[] {
  return (mix?.track_list?.length ? mix.track_list : DEFAULT_LIST)
    .map((t) => ({ id: t.id, kind: t.kind, label: t.label || TRACK_LABEL[t.id as TrackKind] || t.id }));
}

/** A track's kind (an id not in the list: a default's own, else music). */
export function kindOf(mix: Mix | undefined, id: MixTrack): TrackKind {
  return trackList(mix).find((t) => t.id === id)?.kind ?? (TRACKS.includes(id as TrackKind) ? (id as TrackKind) : "music");
}

/** A track's name. */
export function labelOf(mix: Mix | undefined, id: MixTrack): string {
  return trackList(mix).find((t) => t.id === id)?.label ?? TRACK_LABEL[id as TrackKind] ?? id;
}

/** The track things of `kind` go on when nothing says which: the default of that name, else the
 * first of that kind (null: none left). The beds go on the ambience one, the effects on the effects one. */
export function firstOf(mix: Mix | undefined, kind: TrackKind): MixTrack | null {
  const list = trackList(mix);
  if (list.some((t) => t.id === kind && t.kind === kind)) return kind;
  return list.find((t) => t.kind === kind)?.id ?? null;
}

/** A list stored as mix.json keeps it: labels that are the default's dropped, and none at all
 * when it's the four defaults as they are. */
function storeList(list: TrackDef[] | MixTrackDef[]): MixTrackDef[] | undefined {
  const out = list.map((t) => {
    const o: MixTrackDef = { id: t.id, kind: t.kind };
    const label = (t.label ?? "").split(/\s+/).filter(Boolean).join(" ").slice(0, 40);
    if (label && label !== (TRACK_LABEL[t.id as TrackKind] ?? t.id)) o.label = label;
    return o;
  });
  return JSON.stringify(out) === JSON.stringify(DEFAULT_LIST) ? undefined : out;
}

function withList(mix: Mix, list: TrackDef[] | MixTrackDef[]): Mix {
  const out: Mix = { ...mix };
  const stored = storeList(list);
  if (stored) out.track_list = stored;
  else delete out.track_list;
  return out;
}

/** A new track's id from its name: its letters and digits (a kind and a number when that's taken or empty). */
export function newTrackId(label: string, kind: TrackKind, taken: Iterable<string>): string {
  const used = new Set([...taken].map((x) => x.toLowerCase()));
  const slug = label.toLowerCase().normalize("NFKD").replace(/[^a-z0-9_-]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 32);
  if (slug && !used.has(slug) && !RESERVED.has(slug) && ID.test(slug)) return slug;
  for (let n = 2; ; n++) {
    const id = `${kind}${n}`;
    if (!used.has(id)) return id;
  }
}

/** A track added at the end of the lanes (null: the mix has as many as it can). */
export function addTrack(mix: Mix, kind: TrackKind, label: string): { mix: Mix; id: string } | null {
  const list = trackList(mix);
  if (list.length >= MAX_TRACKS) return null;
  const id = newTrackId(label, kind, list.map((t) => t.id));
  const name = label.trim() || `${TRACK_LABEL[kind]} ${list.filter((t) => t.kind === kind).length + 1}`;
  return { mix: withList(mix, [...list, { id, kind, label: name }]), id };
}

/** A track renamed (an empty name: its default's; null: nothing changes). */
export function renameTrack(mix: Mix, id: MixTrack, label: string): Mix | null {
  const list = trackList(mix);
  const i = list.findIndex((t) => t.id === id);
  if (i < 0) return null;
  const next = list.slice();
  next[i] = { ...list[i], label: label.trim() || (TRACK_LABEL[id as TrackKind] ?? id) };
  const out = withList(mix, next);
  return JSON.stringify(out) === JSON.stringify(mix) ? null : out;
}

/** A track moved one lane up (-1) or down (+1); null at either end. */
export function moveTrack(mix: Mix, id: MixTrack, by: -1 | 1): Mix | null {
  const list = trackList(mix);
  const i = list.findIndex((t) => t.id === id);
  const j = i + by;
  if (i < 0 || j < 0 || j >= list.length) return null;
  const next = list.slice();
  [next[i], next[j]] = [next[j], next[i]];
  return withList(mix, next);
}

/** Whether a track can be taken out: any but the dialogue one (the takes' own sound). */
export const canDeleteTrack = (id: MixTrack) => id !== "dialogue";

/** The items on a track. */
export const itemsOn = (mix: Mix, id: MixTrack) => (mix.items ?? []).filter((x) => x.track === id);

/**
 * A track taken out: its items moved to `moveTo` (another track), or taken out with it (null),
 * its levels with it. Null for the dialogue track, or a track that isn't there.
 */
export function deleteTrack(mix: Mix, id: MixTrack, moveTo: MixTrack | null): Mix | null {
  const list = trackList(mix);
  if (!canDeleteTrack(id) || !list.some((t) => t.id === id) || moveTo === id) return null;
  if (moveTo != null && !list.some((t) => t.id === moveTo)) return null;
  let out = withList(mix, list.filter((t) => t.id !== id));
  const items = (mix.items ?? []).flatMap((x) => (x.track !== id ? [x] : moveTo != null ? [{ ...x, track: moveTo }] : []));
  if (items.length) out.items = items;
  else delete out.items;
  if (out.tracks?.[id]) {
    const tracks = { ...out.tracks };
    delete tracks[id];
    out = { ...out, tracks };
    if (!Object.keys(tracks).length) delete out.tracks;
  }
  return out;
}

/** An item moved to another track (a dialogue-kind track's level and ducking, say); null: nothing changes. */
export function itemToTrack(mix: Mix, itemId: string, track: MixTrack): Mix | null {
  const it = mix.items?.find((x) => x.id === itemId);
  if (!it || it.track === track || !trackList(mix).some((t) => t.id === track)) return null;
  return patchItem(mix, itemId, { track });
}

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
  /** its volume points on the cut's clock (dB on its gain), in time order */
  points: TimedPoint[];
  /** seconds */
  fadeIn: number;
  fadeOut: number;
  loop: boolean;
}

/** The mix's items as Play all plays them. */
export function playPlan(items: PlayItem[], mix: Mix, fps: number): PlayEntry[] {
  const f = fps || 24;
  const total = totalDuration(items);
  const out: PlayEntry[] = [];
  for (const it of mix.items ?? []) {
    // a muted item is silent where it is
    if (it.mute) continue;
    const s = anchorTime(items, it.in, f);
    const e = it.out ? anchorTime(items, it.out, f) : null;
    if (s == null || (it.out && e == null)) continue;
    // an item starting before the cut plays from where the cut does
    const start = Math.max(0, s);
    const end = e == null ? null : Math.min(total, e);
    if (end != null && end <= start) continue;
    out.push({
      id: it.id, track: it.track, path: it.path, start, end, offset: (it.offset ?? 0) + (start - s),
      gain: dbToGain(it.gain_db ?? 0), points: timedPoints(items, it, f), fadeIn: (it.fade_in ?? 0) / f, fadeOut: (it.fade_out ?? 0) / f, loop: !!it.loop,
    });
  }
  return out;
}

/** An entry's end once its file's length is known (and the cut's end). */
export function entryEnd(e: PlayEntry, fileSecs: number, total: number): number {
  return Math.min(total, e.end ?? e.start + Math.max(0, fileSecs - e.offset));
}

/** An entry's level (its gain, points and fades) `t` cut seconds in, `end` its end. */
export function entryLevel(e: PlayEntry, t: number, end: number): number {
  let v = 1;
  if (e.fadeIn > 0) v = Math.min(v, (t - e.start) / e.fadeIn);
  if (e.fadeOut > 0) v = Math.min(v, (end - t) / e.fadeOut);
  const p = e.points?.length ? 10 ** (pointsDb(e.points, t) / 20) : 1;
  return e.gain * p * Math.max(0, Math.min(1, v));
}

/** seconds between the marks a slope between two points is ramped through (it's linear in dB, a ramp in gain) */
const SLOPE_STEP = 0.1;

/**
 * The cut times after `at` (to `end`) an entry's level is ramped to: its
 * fades' corners, its points, and steps along a slope between two points.
 */
export function entryMarks(e: PlayEntry, at: number, end: number): number[] {
  const marks = [e.start + e.fadeIn, end - e.fadeOut, end];
  const pts = e.points ?? [];
  for (let k = 0; k < pts.length; k++) {
    marks.push(pts[k].t);
    const n = pts[k + 1];
    if (!n || n.db === pts[k].db) continue;
    for (let j = 1; pts[k].t + j * SLOPE_STEP < n.t - 1e-6; j++) marks.push(pts[k].t + j * SLOPE_STEP);
  }
  return [...new Set(marks.filter((t) => t > at && t <= end))].sort((a, b) => a - b);
}

// ---------------------------------------------------------------------------
// volume points: dB at anchors on an item's gain, linear between, held beyond
// the first and last (mix.py's render_item)
// ---------------------------------------------------------------------------

/** A point on the cut's clock; `i` its index in the item's `points`. */
export interface TimedPoint {
  t: number;
  db: number;
  i: number;
}

/** An item's points on the cut's clock, in time order (one whose shot isn't in the cut left out, as mix.py does). */
export function timedPoints(items: PlayItem[], it: MixItem, fps: number): TimedPoint[] {
  const out: TimedPoint[] = [];
  (it.points ?? []).forEach((p, i) => {
    const t = anchorTime(items, p.at, fps);
    if (t != null) out.push({ t, db: p.db, i });
  });
  return out.sort((a, b) => a.t - b.t);
}

/** The points' dB at `t`, as np.interp: the first held before it, the last after (none: 0). */
export function pointsDb(pts: { t: number; db: number }[], t: number): number {
  if (!pts.length) return 0;
  if (t <= pts[0].t) return pts[0].db;
  for (let k = 1; k < pts.length; k++) {
    const b = pts[k];
    if (t > b.t) continue;
    const a = pts[k - 1];
    return b.t === a.t ? b.db : a.db + ((t - a.t) / (b.t - a.t)) * (b.db - a.db);
  }
  return pts[pts.length - 1].db;
}

/** the range a block's gain line is drawn over, dB */
export const POINT_DB_LO = -24;
export const POINT_DB_HI = 12;

/** y of `db` in a block `h` high (beyond the drawn range: its edge). */
export function dbY(db: number, h: number): number {
  const d = Math.min(POINT_DB_HI, Math.max(POINT_DB_LO, db));
  return ((POINT_DB_HI - d) / (POINT_DB_HI - POINT_DB_LO)) * h;
}

/** dB at y in a block `h` high. */
export const yDb = (y: number, h: number) => POINT_DB_HI - (y / Math.max(1, h)) * (POINT_DB_HI - POINT_DB_LO);

/** dB snapped to 0.5, in the fader's range. */
export const snapDb = (db: number) => Math.round(Math.min(GAIN_MAX, Math.max(GAIN_MIN, Number.isFinite(db) ? db : 0)) * 2) / 2;

/** An item's points replaced, in time order (null: nothing changes). */
export function setPoints(mix: Mix, id: string, points: MixPoint[], items: PlayItem[], fps: number): Mix | null {
  const it = mix.items?.find((x) => x.id === id);
  if (!it) return null;
  const t = (p: MixPoint) => anchorTime(items, p.at, fps) ?? Infinity;
  const next = points.map((p) => ({ at: p.at, db: snapDb(p.db) })).sort((a, b) => t(a) - t(b));
  if (JSON.stringify(next) === JSON.stringify(it.points ?? [])) return null;
  return patchItem(mix, id, { points: next });
}

/** A point added at `at`: at `db`, else at the line's level there (so nothing sounds different yet). */
export function addPoint(mix: Mix, id: string, at: Anchor, items: PlayItem[], fps: number, db?: number): Mix | null {
  const it = mix.items?.find((x) => x.id === id);
  const t = anchorTime(items, at, fps);
  if (!it || t == null || (it.points ?? []).some((p) => sameAnchor(p.at, at))) return null;
  return setPoints(mix, id, [...(it.points ?? []), { at, db: db ?? pointsDb(timedPoints(items, it, fps), t) }], items, fps);
}

/** Point `i` moved to `at` and `db`. */
export function movePoint(mix: Mix, id: string, i: number, at: Anchor, db: number, items: PlayItem[], fps: number): Mix | null {
  const it = mix.items?.find((x) => x.id === id);
  if (!it?.points?.[i]) return null;
  const next = it.points.slice();
  next[i] = { at, db };
  return setPoints(mix, id, next, items, fps);
}

/** Point `i` taken out (the last one leaves the item without points). */
export function removePoint(mix: Mix, id: string, i: number): Mix | null {
  const it = mix.items?.find((x) => x.id === id);
  if (!it?.points?.[i]) return null;
  return patchItem(mix, id, { points: it.points.filter((_, k) => k !== i) });
}

/**
 * An item lowered `db` from `t0` to `t1` (the cut's clock) with volume points:
 * a point at each end at the line's level there, ramped over `ramp` seconds to
 * the line `db` lower, the points between lowered with it (those in a ramp
 * replaced), the line outside kept. Null when nothing changes.
 */
export function lowerStretch(mix: Mix, id: string, t0: number, t1: number, db: number, ramp: number, items: PlayItem[], fps: number): Mix | null {
  const it = mix.items?.find((x) => x.id === id);
  if (!it || !(t1 > t0) || !db) return null;
  const r = Math.max(0, Math.min(ramp, (t1 - t0) / 4));
  const timed = timedPoints(items, it, fps);
  const line = (t: number) => pointsDb(timed, t);
  const when = new Map(timed.map((p) => [p.i, p.t]));
  const kept: MixPoint[] = [];
  (it.points ?? []).forEach((p, i) => {
    const t = when.get(i);
    if (t == null || t < t0 - 1e-6 || t > t1 + 1e-6) kept.push(p);
    else if (t > t0 + r + 1e-6 && t < t1 - r - 1e-6) kept.push({ at: p.at, db: p.db + db });
  });
  const ends: MixPoint[] = [];
  for (const [t, d] of [[t0, line(t0)], [t0 + r, line(t0 + r) + db], [t1 - r, line(t1 - r) + db], [t1, line(t1)]]) {
    const at = timeAnchor(items, t, fps);
    if (at && !ends.some((p) => sameAnchor(p.at, at))) ends.push({ at, db: d });
  }
  return setPoints(mix, id, [...kept.filter((p) => !ends.some((e) => sameAnchor(e.at, p.at))), ...ends], items, fps);
}

// ---------------------------------------------------------------------------
// ducking: the server's speech curve (GET /seriesmith/mix/duck) times each
// track's duck_db, a region's depth where it says one, and the dialogue
// lowered under a region (mix.py's render)
// ---------------------------------------------------------------------------

/** GET /seriesmith/mix/duck: how much someone is speaking, 0..1 per `step` seconds of the cut. */
export interface DuckCurve {
  step: number;
  curve: number[];
}

/** A region on the cut's clock: the depths it puts in place, the dialogue's dB under it. */
export interface RegionSpan {
  start: number;
  end: number;
  music?: number;
  ambience?: number;
  dialogue?: number;
}

/** The mix's regions on the cut's clock (one whose shots aren't in it, or that ends before it starts, left out). */
export function regionSpans(items: PlayItem[], mix: Mix, fps: number): RegionSpan[] {
  const out: RegionSpan[] = [];
  for (const r of mix.regions ?? []) {
    const a = anchorTime(items, r.from, fps);
    const b = anchorTime(items, r.to, fps);
    if (a == null || b == null || b <= a) continue;
    const s: RegionSpan = { start: a, end: b };
    if (r.music_duck_db != null) s.music = r.music_duck_db;
    if (r.ambience_duck_db != null) s.ambience = r.ambience_duck_db;
    if (r.dialogue_db) s.dialogue = r.dialogue_db;
    out.push(s);
  }
  return out;
}

const regionDepth = (r: RegionSpan, kind: TrackKind) => (kind === "music" ? r.music : kind === "ambience" ? r.ambience : undefined);

/** How far a track dips under speech: the mix's, the series config's, else its kind's default (the dialogue kind: 0). */
export function duckDepth(res: TrackSource | undefined, name: MixTrack): number {
  const kind = kindOf(res?.mix, name);
  if (kind === "dialogue") return 0;
  return res?.mix?.tracks?.[name]?.duck_db ?? res?.series?.tracks?.[name]?.duck_db ?? res?.defaults?.duck_db?.[kind] ?? DUCK_DEFAULT[kind] ?? 0;
}

/**
 * A track's dip at cut time `t` in dB, `speech` the curve there: its depth
 * (a region's for its kind, the later one winning) times the curve; for the
 * dialogue kind, the regions' dialogue_db added up.
 */
export function duckDbAt(kind: TrackKind, depth: number, spans: RegionSpan[], speech: number, t: number): number {
  let d = kind === "dialogue" ? 0 : depth;
  for (const r of spans) {
    if (t < r.start || t >= r.end) continue;
    if (kind === "dialogue") d += r.dialogue ?? 0;
    else d = regionDepth(r, kind) ?? d;
  }
  // (no dip is 0, not -0)
  return (kind === "dialogue" ? d : d * speech) || 0;
}

/** The dialogue's dB at cut time `t` from the regions over it (0: none). */
export function dialogueDbAt(items: PlayItem[], mix: Mix, fps: number, t: number): number {
  return mix.regions?.length ? duckDbAt("dialogue", 0, regionSpans(items, mix, fps), 0, t) : 0;
}

/** Each track's dip in dB, a value per `step` seconds from 0 through `total` (null: it never dips). */
export function duckTracks(res: TrackSource | undefined, items: PlayItem[], fps: number, duck: DuckCurve | undefined, total: number):
  { step: number; db: Record<MixTrack, number[] | null> } {
  const step = duck && duck.step > 0 ? duck.step : 0.05;
  const spans = regionSpans(items, res?.mix ?? {}, fps || 24);
  const n = Math.max(0, Math.ceil(total / step)) + 1;
  const curve = duck?.curve ?? [];
  const db = {} as Record<MixTrack, number[] | null>;
  for (const { id: name, kind } of trackList(res?.mix)) {
    const depth = duckDepth(res, name);
    const out: number[] = new Array(n);
    let any = false;
    for (let i = 0; i < n; i++) {
      out[i] = duckDbAt(kind, depth, spans, curve[i] ?? 0, i * step);
      if (out[i]) any = true;
    }
    db[name] = any ? out : null;
  }
  return { step, db };
}

// ---------------------------------------------------------------------------
// tracks: the mix's over the series config's, over the defaults
// ---------------------------------------------------------------------------

export interface TrackState {
  gain_db: number;
  mute: boolean;
  solo: boolean;
}

/** What a track's settings come from: the mix, over the series config's, over the defaults. */
export type TrackSource = Pick<MixResult, "mix" | "series"> & { defaults?: Partial<MixResult["defaults"]> };

/** A track's fader when neither the mix nor the series config sets it: its kind's (music: -12 dB). */
export function defaultGain(res: TrackSource | undefined, name: MixTrack): number {
  const kind = kindOf(res?.mix, name);
  return res?.defaults?.gain_db?.[kind] ?? GAIN_DEFAULT[kind];
}

export function trackState(res: TrackSource | undefined, name: MixTrack): TrackState {
  const s = res?.series?.tracks?.[name] ?? {};
  const m = res?.mix?.tracks?.[name] ?? {};
  return { gain_db: m.gain_db ?? s.gain_db ?? defaultGain(res, name), mute: !!(m.mute ?? s.mute), solo: !!(m.solo ?? s.solo) };
}

/** What each track sounds at: its fader, silenced when muted or another is soloed. */
export function trackGains(res: TrackSource | undefined): Record<MixTrack, number> {
  const ids = trackList(res?.mix).map((t) => t.id);
  const st = Object.fromEntries(ids.map((t) => [t, trackState(res, t)])) as Record<MixTrack, TrackState>;
  const soloed = ids.some((t) => st[t].solo);
  return Object.fromEntries(ids.map((t) => {
    const x = st[t];
    return [t, x.mute || (soloed && !x.solo) ? 0 : dbToGain(x.gain_db)];
  })) as Record<MixTrack, number>;
}

/** A track's settings, a fader of null meaning "none of the mix's own". */
export type TrackPatch = Omit<Partial<MixTrackSettings>, "gain_db"> & { gain_db?: number | null };

/**
 * A track's settings changed. A fader is kept as given, 0 too (it overrides
 * the series config's and the default: music's is -12); null drops it, for the
 * one under it. Mute, solo and duck_db drop their defaults (as mix.json keeps them).
 */
export function setTrack(mix: Mix, name: MixTrack, patch: TrackPatch): Mix {
  const t: TrackPatch = { ...(mix.tracks?.[name] ?? {}), ...patch };
  if (t.gain_db == null) delete t.gain_db;
  else t.gain_db = clampDb(t.gain_db);
  if (!t.mute) delete t.mute;
  if (!t.solo) delete t.solo;
  if (t.duck_db == null) delete t.duck_db;
  const tracks = { ...(mix.tracks ?? {}) };
  if (Object.keys(t).length) tracks[name] = t as MixTrackSettings;
  else delete tracks[name];
  const out: Mix = { ...mix, tracks };
  if (!Object.keys(tracks).length) delete out.tracks;
  return out;
}

// ---------------------------------------------------------------------------
// items
// ---------------------------------------------------------------------------

const PREFIX: Record<TrackKind, string> = { dialogue: "d", effects: "fx", ambience: "amb", music: "m" };

/** A new id: `prefix` and the next free two-digit number. */
export function newId(prefix: string, taken: Iterable<string>): string {
  const used = new Set(taken);
  for (let n = 1; ; n++) {
    const id = `${prefix}${String(n).padStart(2, "0")}`;
    if (!used.has(id)) return id;
  }
}

export const newItemId = (mix: Mix, track: MixTrack) => newId(PREFIX[kindOf(mix, track)], (mix.items ?? []).map((i) => i.id));
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
  if (!o.mute) delete o.mute;
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

// ---------------------------------------------------------------------------
// ambience beds (docs/SOUND.md phase 3): laid by the server from the cut and the
// series config (GET /seriesmith/mix `beds`), never items; the mix keeps only a
// place's level and mute (`beds`), so a change shows at once
// ---------------------------------------------------------------------------

/** seconds two places' beds crossfade over at the cut between them (ambience.RUN_XFADE_S) */
export const BED_XFADE = 0.5;

/** A place's own settings in the mix (gain 0, not muted: none). */
export function bedSettings(mix: Mix, place: string): { gain_db: number; mute: boolean } {
  const b = mix.beds?.[place];
  return { gain_db: b?.gain_db ?? 0, mute: !!b?.mute };
}

/** A place's level or mute changed; defaults dropped (as mix.json keeps them). */
export function setBed(mix: Mix, place: string, patch: MixBedSettings): Mix {
  const b: MixBedSettings = { ...(mix.beds?.[place] ?? {}), ...patch };
  if (!b.gain_db) delete b.gain_db;
  else b.gain_db = clampDb(b.gain_db);
  if (!b.mute) delete b.mute;
  const beds = { ...(mix.beds ?? {}) };
  if (Object.keys(b).length) beds[place] = b;
  else delete beds[place];
  const out: Mix = { ...mix, beds };
  if (!Object.keys(beds).length) delete out.beds;
  return out;
}

/** A bed's run on the cut's clock: from its anchors (so a trim shows at once), else as laid. */
export function bedSpan(items: PlayItem[], bed: MixBed, fps: number): { start: number; end: number } {
  const s = anchorTime(items, bed.in, fps);
  const e = anchorTime(items, bed.out, fps);
  const total = totalDuration(items);
  return { start: Math.max(0, s ?? bed.start), end: Math.min(total, e ?? bed.end) };
}

/** The beds Play all plays: each run its file looped, at the place's gain, crossfaded over
 * BED_XFADE at a boundary inside the cut (a muted place, or one not made yet, left out). */
export function bedPlan(items: PlayItem[], beds: MixBed[] | undefined, mix: Mix, fps: number): PlayEntry[] {
  const total = totalDuration(items);
  const out: PlayEntry[] = [];
  const track = firstOf(mix, "ambience");
  if (!track) return out;
  const half = BED_XFADE / 2;
  (beds ?? []).forEach((b, i) => {
    const own = bedSettings(mix, b.place);
    if (!b.exists || own.mute) return;
    const { start, end } = bedSpan(items, b, fps);
    if (!(end > start)) return;
    const head = start > 1e-6;
    const tail = end < total - 1e-6;
    out.push({
      id: `bed:${b.place}:${i}`, track, path: b.path,
      start: head ? start - half : start, end: tail ? end + half : end, offset: 0,
      gain: dbToGain(own.gain_db), points: [], fadeIn: head ? BED_XFADE : 0, fadeOut: tail ? BED_XFADE : 0, loop: true,
    });
  });
  return out;
}

// ---------------------------------------------------------------------------
// effects (docs/SOUND.md phase 4): a shot's picked effects take, laid by the server at
// its clip from the cut (GET /seriesmith/mix `fx`), never an item; the mix keeps which
// take, its level, mute and whether to keep it though stale (`fx`), so a change shows
// at once
// ---------------------------------------------------------------------------

/** A shot's settings in the mix (null: no effects picked). */
export function fxSettings(mix: Mix, shot: string): { take: number; gain_db: number; mute: boolean; keep_stale: boolean } | null {
  const f = mix.fx?.[shot];
  return f ? { take: f.take, gain_db: f.gain_db ?? 0, mute: !!f.mute, keep_stale: !!f.keep_stale } : null;
}

/** A shot's level, mute or keep_stale changed (its take kept); defaults dropped, as mix.json keeps them. */
export function setFx(mix: Mix, shot: string, patch: Partial<Omit<MixFxSettings, "take">>): Mix {
  const was = mix.fx?.[shot];
  if (!was) return mix;
  const f: MixFxSettings = { ...was, ...patch };
  if (!f.gain_db) delete f.gain_db;
  else f.gain_db = clampDb(f.gain_db);
  if (!f.mute) delete f.mute;
  if (!f.keep_stale) delete f.keep_stale;
  return { ...mix, fx: { ...(mix.fx ?? {}), [shot]: f } };
}

/** A shot's effects take picked (its level and mute kept, a keep_stale dropped: a new pick is
 * judged afresh), or taken out (null). */
export function pickFxTake(mix: Mix, shot: string, take: number | null): Mix {
  const fx = { ...(mix.fx ?? {}) };
  if (take == null) delete fx[shot];
  else {
    const was = fx[shot];
    fx[shot] = { take, ...(was?.gain_db ? { gain_db: was.gain_db } : {}), ...(was?.mute ? { mute: true } : {}) };
  }
  const out: Mix = { ...mix, fx };
  if (!Object.keys(fx).length) delete out.fx;
  return out;
}

/** Whether a laid shot's effects play, with the mix as it is now (a mute or keep shows at once). */
export function fxHeard(mix: Mix, f: MixFx): boolean {
  const own = fxSettings(mix, f.shot);
  if (!own || own.take !== f.take) return false;
  return f.exists && !own.mute && (!f.stale || own.keep_stale);
}

/** A shot's effects on the cut's clock: from its anchors (a trim shows at once), else as laid. */
export function fxSpan(items: PlayItem[], f: MixFx, fps: number): { start: number; end: number } {
  const s = anchorTime(items, f.in, fps);
  const e = anchorTime(items, f.out, fps);
  return { start: Math.max(0, s ?? f.start), end: e ?? f.end };
}

/** The effects Play all plays: each heard one at its clip, from the clip's first frame of the take. */
export function fxPlan(items: PlayItem[], fx: MixFx[] | undefined, mix: Mix, fps: number): PlayEntry[] {
  const out: PlayEntry[] = [];
  const track = firstOf(mix, "effects");
  if (!track) return out;
  for (const f of fx ?? []) {
    if (!fxHeard(mix, f)) continue;
    const { start, end } = fxSpan(items, f, fps);
    if (!(end > start)) continue;
    out.push({
      id: `fx:${f.shot}`, track, path: f.path, start, end, offset: f.in.frame / (fps || 24),
      gain: dbToGain(fxSettings(mix, f.shot)?.gain_db ?? 0), points: [], fadeIn: 0, fadeOut: 0, loop: false,
    });
  }
  return out;
}

// ---------------------------------------------------------------------------
// voices only (voices.py): the Dialogue track's clips from their takes' voice stems
// ---------------------------------------------------------------------------

/** Whether the dialogue track plays voices only. */
export function voicesOnly(mix: Mix | undefined): boolean {
  return !!mix?.tracks?.dialogue?.voices_only;
}

/** The dialogue track's voices only on or off (off is dropped, as mix.json keeps it). */
export function setVoicesOnly(mix: Mix, on: boolean): Mix {
  const t: MixTrackSettings = { ...(mix.tracks?.dialogue ?? {}) };
  if (on) t.voices_only = true;
  else delete t.voices_only;
  const tracks = { ...(mix.tracks ?? {}) };
  if (Object.keys(t).length) tracks.dialogue = t;
  else delete tracks.dialogue;
  const out: Mix = { ...mix, tracks };
  if (!Object.keys(tracks).length) delete out.tracks;
  return out;
}

/** A shot's own voices only (true: its stem; false: its whole sound; null: the track's). */
export function setShotVoices(mix: Mix, shot: string, v: boolean | null): Mix {
  const voices = { ...(mix.voices ?? {}) };
  if (v == null) delete voices[shot];
  else voices[shot] = { voices_only: v };
  const out: Mix = { ...mix, voices };
  if (!Object.keys(voices).length) delete out.voices;
  return out;
}

/**
 * What the Dialogue track plays for a clip under `mix` (voices.plays, worked out here too so
 * a toggle is heard at once): its stem, its whole sound, or silence (a shot with no lines,
 * unless it asks for voices only itself). A stem that isn't there plays the whole sound.
 */
export function voicePlays(mix: Mix | undefined, v: MixVoice): MixVoice["plays"] {
  const own = mix?.voices?.[v.shot]?.voices_only;
  const want = own ?? voicesOnly(mix);
  if (!want || v.state === "sourced" || v.state === "silent") return "whole";
  if (!v.lines && own !== true) return "silence";
  return v.state === "ok" ? "voice" : "whole";
}

/** The shots whose clip's own sound isn't heard under Play all (their stem plays, or nothing). */
export function voicedShots(res: Pick<MixResult, "mix" | "voices"> | undefined): string[] {
  return (res?.voices?.shots ?? []).filter((v) => voicePlays(res?.mix, v) !== "whole").map((v) => v.shot);
}

/** The voice stems Play all plays, each on the dialogue track at its clip (its <video> muted). */
export function voicePlan(items: PlayItem[], res: Pick<MixResult, "mix" | "voices"> | undefined): PlayEntry[] {
  const out: PlayEntry[] = [];
  for (const v of res?.voices?.shots ?? []) {
    if (!v.path || voicePlays(res?.mix, v) !== "voice") continue;
    const it = items.find((x) => x.shot === v.shot);
    if (!it || !it.mp4 || it.take !== v.take || !(it.dur > 0)) continue;
    out.push({
      id: `voice:${v.shot}`, track: "dialogue", path: v.path, start: it.start, end: it.start + it.dur, offset: it.inT,
      gain: 1, points: [], fadeIn: 0, fadeOut: 0, loop: false,
    });
  }
  return out;
}

/** A clip's voice stem that's missing or stale while voices only wants it (null: nothing to say). */
export function voiceBadge(mix: Mix | undefined, v: MixVoice | undefined): string | null {
  if (!v) return null;
  const own = mix?.voices?.[v.shot]?.voices_only;
  const want = own ?? voicesOnly(mix);
  if (!want || voicePlays(mix, v) !== "whole" || v.state === "sourced" || v.state === "silent") return null;
  return v.state === "queued" ? "its voice stem is being made" : `its whole sound plays: ${v.why ?? `its voice stem is ${v.state}`}`;
}
