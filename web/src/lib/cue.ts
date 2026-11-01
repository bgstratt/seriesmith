// A music cue in its window (docs/SOUND.md "The cue window"), pure: the cue's
// bar grid, bar.beat labels, the sections' edges as bars, the arc's points
// between cue time and anchors, and how a take's measurements read. Cue time
// is seconds from the cue's in point: its first bar starts `preroll` before
// it, and the grid runs `bars` bars from there (cue.py's plan is the
// reference). The arc is energy 1-5; the timeline's gain breakpoints (dB) are
// another curve, kept apart.

import type { Anchor, CuePlan, CueSection, CueSpec, CueTake } from "../types";
import { anchorTime, newId, timeAnchor } from "./mix";
import type { PlayItem } from "./playlist";

export const LEVEL_MIN = 1;
export const LEVEL_MAX = 5;
export const LEVEL_WORDS = ["", "sparse", "quiet", "moderate", "full", "fortissimo"];
/** a hit this many frames off its line (or more) shows orange */
export const HIT_TOLERANCE = 2;

/** The cue's grid: bar and beat in seconds, from `-preroll` for `bars` bars. */
export interface Grid {
  bar: number;
  beat: number;
  meter: number;
  bars: number;
  preroll: number;
  seconds: number;
}

export function gridOf(plan: Pick<CuePlan, "bar" | "bars" | "preroll">, spec: Pick<CueSpec, "meter">): Grid {
  const meter = spec.meter || 4;
  const bar = plan.bar > 0 ? plan.bar : 2.4;
  return { bar, beat: bar / meter, meter, bars: Math.max(1, plan.bars), preroll: plan.preroll, seconds: Math.max(1, plan.bars) * bar };
}

/** x of cue time `tau`, `pps` pixels a second, 0 at the first bar line. */
export const tauX = (g: Grid, tau: number, pps: number) => (tau + g.preroll) * pps;
export const xTau = (g: Grid, x: number, pps: number) => x / pps - g.preroll;

/** Cue time on the nearest beat, kept on the grid. */
export function snapBeat(g: Grid, tau: number): number {
  const n = Math.round((tau + g.preroll) / g.beat);
  return Math.min(g.bars * g.meter, Math.max(0, n)) * g.beat - g.preroll;
}

/** The bar and beat (1-based) nearest cue time `tau`: "5.3". */
export function barBeat(g: Grid, tau: number): { bar: number; beat: number; label: string } {
  const n = Math.max(0, Math.round((tau + g.preroll) / g.beat));
  const bar = Math.floor(n / g.meter) + 1;
  const beat = (n % g.meter) + 1;
  return { bar, beat, label: `${bar}.${beat}` };
}

// ---------------------------------------------------------------------------
// sections
// ---------------------------------------------------------------------------

/** Where each section starts, in bars from the first, and where the last ends. */
export function sectionEdges(sections: { bars: number }[]): number[] {
  const out = [0];
  for (const s of sections) out.push(out[out.length - 1] + Math.max(1, s.bars));
  return out;
}

const SECTION_KEYS: (keyof CueSection)[] = ["name", "bars", "words", "from", "to", "lyrics"];

/** A section as a spec keeps it (what the plan adds to it left out but its fields). */
function asSpec(s: CueSection): CueSection {
  const o = {} as Record<string, unknown>;
  for (const k of SECTION_KEYS) if (s[k] != null && s[k] !== "") o[k] = s[k];
  return o as unknown as CueSection;
}

/**
 * The sections to edit: the spec's when it has them (with the plan's bars,
 * since the plan fits them to the cue), else the plan's, which become the
 * spec's on the first edit.
 */
export function editableSections(spec: CueSpec, plan: CuePlan): CueSection[] {
  const own = spec.sections ?? [];
  if (own.length && own.length === plan.sections.length) return own.map((s, i) => asSpec({ ...s, bars: plan.sections[i].bars }));
  if (own.length) return own.map(asSpec);
  return plan.sections.map(asSpec);
}

/**
 * The edge between section `i` and the next moved to bar `bar` (0-based, from
 * the first bar line): the two sides' bars change, each keeping one at least.
 * Null when it doesn't move.
 */
export function moveEdge(sections: CueSection[], i: number, bar: number): CueSection[] | null {
  if (i < 0 || i + 1 >= sections.length) return null;
  const bars = sections.map((s) => s.bars ?? 1);
  const edges = sectionEdges(bars.map((b) => ({ bars: b })));
  const lo = edges[i] + 1;
  const hi = edges[i + 2] - 1;
  const at = Math.min(hi, Math.max(lo, Math.round(bar)));
  if (at === edges[i + 1] || lo > hi) return null;
  const out = sections.map((s, k) => ({ ...s, bars: bars[k] }));
  out[i] = { ...out[i], bars: at - edges[i] };
  out[i + 1] = { ...out[i + 1], bars: edges[i + 2] - at };
  return out;
}

/** One section changed (fields set to "" or null are dropped). */
export function patchSection(sections: CueSection[], i: number, patch: Partial<CueSection>): CueSection[] {
  return sections.map((s, k) => (k === i ? asSpec({ ...s, ...patch } as CueSection) : s));
}

// ---------------------------------------------------------------------------
// the arc: points in cue time, anchors in the spec
// ---------------------------------------------------------------------------

/** A point of the arc in cue time. */
export interface ArcPt {
  tau: number;
  level: number;
}

export const clampLevel = (v: number) => Math.min(LEVEL_MAX, Math.max(LEVEL_MIN, Math.round(v * 2) / 2));

/** y of a level in a lane `h` tall (5 at the top, 1 at the bottom, `pad` clear of each edge). */
export const levelY = (level: number, h: number, pad = 4) => pad + (LEVEL_MAX - level) / (LEVEL_MAX - LEVEL_MIN) * (h - 2 * pad);
/** The level at y, to half a level. */
export const yLevel = (y: number, h: number, pad = 4) => clampLevel(LEVEL_MAX - (y - pad) / Math.max(1, h - 2 * pad) * (LEVEL_MAX - LEVEL_MIN));

/** Where the cue's in point plays on the cut's clock (null: not in the cut). */
export const cueStart = (items: PlayItem[], spec: CueSpec, fps: number) => anchorTime(items, spec.in, fps);

/** The spec's arc points in cue time, in order (those off the cut left out). */
export function arcPoints(spec: CueSpec, items: PlayItem[], t0: number, fps: number): ArcPt[] {
  const out: ArcPt[] = [];
  for (const p of spec.arc ?? []) {
    const t = anchorTime(items, p.at, fps);
    if (t != null) out.push({ tau: t - t0, level: p.level });
  }
  return out.sort((a, b) => a.tau - b.tau);
}

/**
 * The points the sections imply when the spec has none: each section's start
 * at its `from`, and its `to` a beat before the next starts (where it differs),
 * the last's at the grid's end. Dragging one makes them all the spec's.
 */
export function impliedPoints(g: Grid, sections: { bars: number; from: number; to: number }[]): ArcPt[] {
  const out: ArcPt[] = [];
  const edges = sectionEdges(sections);
  sections.forEach((s, i) => {
    const a = edges[i] * g.bar - g.preroll;
    const b = edges[i + 1] * g.bar - g.preroll;
    out.push({ tau: a, level: s.from });
    const last = i === sections.length - 1;
    if (last || s.to !== s.from || sections[i + 1].from !== s.to) out.push({ tau: last ? b : b - g.beat, level: s.to });
  });
  return out;
}

/** The arc's points as the spec keeps them: an anchor each, in order. */
export function arcSpec(points: ArcPt[], items: PlayItem[], t0: number, fps: number): { at: Anchor; level: number }[] {
  const out: { at: Anchor; level: number }[] = [];
  for (const p of [...points].sort((a, b) => a.tau - b.tau)) {
    const at = timeAnchor(items, t0 + p.tau, fps);
    if (at) out.push({ at, level: clampLevel(p.level) });
  }
  return out;
}

/** A point moved (snapped to a beat, its level to half a level), kept between its neighbours. */
export function movePoint(points: ArcPt[], i: number, g: Grid, tau: number, level: number): ArcPt[] {
  const lo = i > 0 ? points[i - 1].tau : -g.preroll;
  const hi = i < points.length - 1 ? points[i + 1].tau : g.seconds - g.preroll;
  const t = Math.min(hi, Math.max(lo, snapBeat(g, tau)));
  return points.map((p, k) => (k === i ? { tau: t, level: clampLevel(level) } : p));
}

export function addPoint(points: ArcPt[], g: Grid, tau: number, level: number): ArcPt[] {
  const t = snapBeat(g, tau);
  return [...points.filter((p) => Math.abs(p.tau - t) > 1e-6), { tau: t, level: clampLevel(level) }].sort((a, b) => a.tau - b.tau);
}

export function removePoint(points: ArcPt[], i: number): ArcPt[] {
  return points.filter((_, k) => k !== i);
}

// ---------------------------------------------------------------------------
// takes
// ---------------------------------------------------------------------------

/** A hit's error as a chip: frames signed to a tenth, "—" for nothing there. */
export function hitChip(e: number | null | undefined): { text: string; cls: "ok" | "off" | "none" } {
  if (e == null) return { text: "—", cls: "none" };
  const r = Math.round(e * 10) / 10;
  return { text: `${r > 0 ? "+" : ""}${r}`, cls: Math.abs(e) > HIT_TOLERANCE ? "off" : "ok" };
}

/** Each take's place: 1, 2, 3 for the measured ones (best first, as the server ranks them), null for the rest. */
export function ranks(takes: CueTake[]): (number | null)[] {
  let n = 0;
  return takes.map((t) => (t.status === "ok" && t.measured?.score != null ? ++n : null));
}

/**
 * A take's level per bar as energies on the arc's scale: its own loudest bar
 * at 5, its quietest heard bar at 1 (a silent bar at 1), so its shape lies over
 * the arc whatever its loudness.
 */
export function levelsAsEnergy(levels: number[]): number[] {
  const heard = levels.filter((x) => x > -60);
  if (!heard.length) return levels.map(() => LEVEL_MIN);
  const lo = Math.min(...heard);
  const span = Math.max(Math.max(...heard) - lo, 1);
  return levels.map((x) => (x <= -60 ? LEVEL_MIN : LEVEL_MIN + (x - lo) / span * (LEVEL_MAX - LEVEL_MIN)));
}

// ---------------------------------------------------------------------------
// a new cue
// ---------------------------------------------------------------------------

/** A new cue's id: m01, m02, ... clear of the cues and the mix's items (a cue's item takes its id). */
export const newCueId = (cues: string[], items: string[]) => newId("m", [...cues, ...items]);

/**
 * A new cue's span: over the selected shots (the first's first frame shown to
 * the last's last), else from `at` to the end of the shot it's in. Null when
 * none of it is in the cut.
 */
export function newCueSpan(items: PlayItem[], fps: number, shots: string[], at: Anchor | null): { in: Anchor; out: Anchor } | null {
  const f = fps || 24;
  const sel = items.filter((it) => shots.includes(it.shot));
  if (sel.length) {
    const a = sel[0];
    const b = sel[sel.length - 1];
    return { in: { shot: a.shot, frame: Math.round(a.inT * f) }, out: { shot: b.shot, frame: Math.max(Math.round(b.inT * f) + 1, Math.round(b.outT * f)) } };
  }
  const it = at ? items.find((x) => x.shot === at.shot) : undefined;
  if (!it || !at) return null;
  const end = Math.round(it.outT * f);
  return { in: at, out: { shot: it.shot, frame: Math.max(at.frame + 1, end) } };
}

/** The clips the cue's grid shows, each its stretch in cue time (clipped to the grid). */
export function clipsOver(items: PlayItem[], t0: number, g: Grid): { it: PlayItem; a: number; b: number }[] {
  const lo = -g.preroll;
  const hi = g.seconds - g.preroll;
  const out: { it: PlayItem; a: number; b: number }[] = [];
  for (const it of items) {
    const a = it.start - t0;
    const b = a + it.dur;
    if (b <= lo || a >= hi) continue;
    out.push({ it, a: Math.max(lo, a), b: Math.min(hi, b) });
  }
  return out;
}

/** A spec with a change, what's emptied left out (as spec.json keeps it). */
export function withSpec(spec: CueSpec, patch: Partial<CueSpec>): CueSpec {
  const o = { ...spec, ...patch } as Record<string, unknown>;
  for (const [k, v] of Object.entries(o)) {
    if (v == null || v === "" || v === false || (Array.isArray(v) && !v.length && k !== "hits")) delete o[k];
  }
  return o as unknown as CueSpec;
}
