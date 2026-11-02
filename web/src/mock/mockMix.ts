// The episode's mix in the mock: mix.py's check (the stored form, defaults
// dropped; a MixError for what the route answers 400 for), enough for the dev
// page and the tests to round-trip a mix.

import type { PlayItem } from "../lib/playlist";
import type { Anchor, Mix, MixHit, MixItem, MixRegion, MixTrack, MixTrackSettings } from "../types";

export class MixError extends Error {
  constructor(message: string, public status = 400) {
    super(message);
  }
}

const TRACKS: MixTrack[] = ["dialogue", "effects", "ambience", "music"];
const DUCK_DEFAULT: Partial<Record<MixTrack, number>> = { effects: 0, ambience: -6, music: -9 };
const HIT_KINDS = ["accent", "arrive", "drop", "turn"];
const ID = /^[A-Za-z0-9_-]{1,40}$/;
const ITEM_FIELDS = ["id", "track", "path", "in", "out", "offset", "gain_db", "fade_in", "fade_out", "points", "loop", "label"];

function num(v: unknown, what: string, lo: number, hi: number): number {
  if (typeof v !== "number" || !Number.isFinite(v)) throw new MixError(`${what} must be a number, not ${JSON.stringify(v)}`);
  if (v < lo || v > hi) throw new MixError(`${what} must be between ${lo} and ${hi}, not ${v}`);
  return Math.round(v * 1000) / 1000;
}

function anchor(raw: unknown, what: string): Anchor {
  const a = raw as Anchor | null;
  if (!a || typeof a !== "object" || typeof a.shot !== "string" || !a.shot.trim()) throw new MixError(`${what} needs its shot`);
  const frame = a.frame ?? 0;
  if (!Number.isInteger(frame) || frame < 0) throw new MixError(`${what}'s frame must be a whole number, 0 or more`);
  return { shot: a.shot.trim(), frame };
}

function id(v: unknown, what: string): string {
  if (typeof v !== "string" || !ID.test(v)) throw new MixError(`${what} id must be 1-40 letters, digits, _ or -, not ${JSON.stringify(v)}`);
  return v;
}

function item(raw: MixItem): MixItem {
  const unknown = Object.keys(raw).filter((k) => !ITEM_FIELDS.includes(k));
  if (unknown.length) throw new MixError(`unknown item field(s) ${unknown.join(", ")}`);
  const out: MixItem = { id: id(raw.id, "an item's"), track: raw.track, path: "", in: anchor(raw.in, `item ${raw.id}'s in`) };
  if (!TRACKS.includes(raw.track)) throw new MixError(`item ${out.id}: track must be one of ${TRACKS.join(", ")}`);
  if (typeof raw.path !== "string" || !raw.path.trim()) throw new MixError(`item ${out.id} needs the path of its sound`);
  out.path = raw.path.trim().replace(/\\/g, "/");
  if (raw.out != null) out.out = anchor(raw.out, `item ${out.id}'s out`);
  if (raw.offset) out.offset = num(raw.offset, `item ${out.id}'s offset`, 0, 86400);
  if (raw.gain_db) out.gain_db = num(raw.gain_db, `item ${out.id}'s gain_db`, -60, 12);
  for (const k of ["fade_in", "fade_out"] as const) {
    const v = raw[k];
    if (v == null || v === 0) continue;
    if (!Number.isInteger(v) || v < 0 || v > 2400) throw new MixError(`item ${out.id}'s ${k} is a whole number of frames, 0 to 2400`);
    out[k] = v;
  }
  if (raw.points?.length) out.points = raw.points.map((p, i) => ({ at: anchor(p.at, `point ${i + 1}`), db: num(p.db, `point ${i + 1}'s db`, -60, 12) }));
  if (raw.loop) out.loop = true;
  if (typeof raw.label === "string" && raw.label.trim()) out.label = raw.label.trim().slice(0, 120);
  return out;
}

/** A pass's mix as mix.json would store it. */
export function checkMix(raw: Mix | null | undefined): Mix {
  if (raw == null) return {};
  if (typeof raw !== "object") throw new MixError("a mix must be an object");
  const out: Mix = {};
  const tracks: Partial<Record<MixTrack, MixTrackSettings>> = {};
  for (const [name, t] of Object.entries(raw.tracks ?? {}) as [MixTrack, MixTrackSettings][]) {
    if (!TRACKS.includes(name)) throw new MixError(`unknown track ${name}`);
    const o: MixTrackSettings = {};
    // a fader is kept as given, 0 too: it overrides the series config's and the default (music -12)
    if (t.gain_db != null) o.gain_db = num(t.gain_db, `track ${name}'s gain_db`, -60, 12);
    if (t.mute) o.mute = true;
    if (t.solo) o.solo = true;
    if (t.duck_db != null) {
      if (name === "dialogue") throw new MixError("the dialogue track doesn't duck");
      const d = num(t.duck_db, `track ${name}'s duck_db`, -40, 0);
      if (d !== DUCK_DEFAULT[name]) o.duck_db = d;
    }
    if (Object.keys(o).length) tracks[name] = o;
  }
  if (Object.keys(tracks).length) out.tracks = tracks;
  const seen = new Set<string>();
  const items = (raw.items ?? []).map((r) => {
    const it = item(r);
    if (seen.has(it.id)) throw new MixError(`two items are called ${it.id}`);
    seen.add(it.id);
    return it;
  });
  if (items.length) out.items = items;
  const hseen = new Set<string>();
  const hits = (raw.hits ?? []).map((h): MixHit => {
    const hid = id(h.id, "a hit's");
    if (hseen.has(hid)) throw new MixError(`two hits are called ${hid}`);
    hseen.add(hid);
    const o: MixHit = { id: hid, at: anchor(h.at, `hit ${hid}`) };
    if (typeof h.name === "string" && h.name.trim()) o.name = h.name.trim().slice(0, 120);
    const kind = h.kind || "accent";
    if (!HIT_KINDS.includes(kind)) throw new MixError(`hit ${hid}'s kind must be one of ${HIT_KINDS.join(", ")}`);
    if (kind !== "accent") o.kind = kind;
    if (h.must === false) o.must = false;
    return o;
  });
  if (hits.length) out.hits = hits;
  // regions, the ducking and the loudness: kept as given (the editor doesn't edit them yet)
  if (raw.regions?.length) out.regions = raw.regions.map((r: MixRegion, i) => ({ ...r, from: anchor(r.from, `region ${i + 1}'s from`), to: anchor(r.to, `region ${i + 1}'s to`) }));
  if (raw.duck && Object.keys(raw.duck).length) out.duck = { ...raw.duck };
  if (raw.loudness && Object.keys(raw.loudness).length) out.loudness = { ...raw.loudness };
  // a place's ambience bed: its level and mute, defaults dropped
  const beds: NonNullable<Mix["beds"]> = {};
  for (const [place, b] of Object.entries(raw.beds ?? {})) {
    const o: { gain_db?: number; mute?: boolean } = {};
    if (b?.gain_db) o.gain_db = num(b.gain_db, `bed ${place}'s gain_db`, -60, 12);
    if (b?.mute) o.mute = true;
    if (Object.keys(o).length) beds[place] = o;
  }
  if (Object.keys(beds).length) out.beds = beds;
  // a shot's effects: its take, level, mute, kept though stale; defaults dropped
  const fx: NonNullable<Mix["fx"]> = {};
  for (const [shot, f] of Object.entries(raw.fx ?? {})) {
    if (!f || !Number.isInteger(f.take) || f.take < 1) throw new MixError(`effects ${shot}'s take is a take number`);
    const o: NonNullable<Mix["fx"]>[string] = { take: f.take };
    if (f.gain_db) o.gain_db = num(f.gain_db, `effects ${shot}'s gain_db`, -60, 12);
    if (f.mute) o.mute = true;
    if (f.keep_stale) o.keep_stale = true;
    fx[shot] = o;
  }
  if (Object.keys(fx).length) out.fx = fx;
  return out;
}

/**
 * GET /seriesmith/mix/duck in the mock: someone speaks over the middle half of
 * every other clip, eased in and out by mix.py's attack and release, a value
 * per 0.05 s of the cut.
 */
export function speechCurve(items: PlayItem[]): { step: number; curve: number[] } {
  const step = 0.05;
  const total = items.reduce((t, it) => Math.max(t, it.start + it.dur), 0);
  const up = 1 - Math.exp(-step * 1000 / 60);
  const down = 1 - Math.exp(-step * 1000 / 450);
  const curve: number[] = [];
  let level = 0;
  for (let i = 0; i * step < total; i++) {
    const t = i * step;
    const it = items.find((x) => t >= x.start && t < x.start + x.dur);
    const on = it && it.index % 2 === 0 && t >= it.start + it.dur * 0.25 && t < it.start + it.dur * 0.75 ? 1 : 0;
    level += (on - level) * (on > level ? up : down);
    curve.push(Math.round(level * 1000) / 1000);
  }
  return { step, curve };
}
