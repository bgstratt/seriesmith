// A music cue in its window (docs/SOUND.md "The cue window"), pure: the cue's
// bar grid, bar.beat labels, the sections' edges as bars, the arc's points
// between cue time and anchors, and how a take's measurements read. Cue time
// is seconds from the cue's in point: its first bar starts `preroll` before
// it, and the grid runs `bars` bars from there (cue.py's plan is the
// reference). The arc is energy 1-5; the timeline's gain breakpoints (dB) are
// another curve, kept apart.

import type { Anchor, CueKind, CuePlan, CuePlanTheme, CuePreset, CueSection, CueSong, CueSpec, CueTake, CueTheme, Target } from "../types";
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
  const meter = meterBeats(spec.meter);
  const bar = plan.bar > 0 ? plan.bar : 2.4;
  return { bar, beat: bar / meter, meter, bars: Math.max(1, plan.bars), preroll: plan.preroll, seconds: Math.max(1, plan.bars) * bar };
}

// ---------------------------------------------------------------------------
// meter and key (cue.py's parse_meter; ace_step15/prompt.py's keyscale)
// ---------------------------------------------------------------------------

/** The meters the inspector offers; another is "Other…" (beats/unit text). */
export const METERS = ["2/4", "3/4", "4/4", "5/4", "6/8", "7/8", "9/8", "12/8"];

/**
 * A meter's beats to the bar and the note a beat is, as cue.py's parse_meter reads it:
 * "7/8", "12/8", or a bare number of beats in 4 (the stored form before meters were
 * text); absent is 4/4. Null for one that isn't 1 to 16 beats of a 2, 4, 8 or 16.
 */
export function parseMeter(m: string | number | null | undefined): { beats: number; unit: number } | null {
  let beats: number;
  let unit: number;
  if (m == null) return { beats: 4, unit: 4 };
  if (typeof m === "number") {
    if (!Number.isInteger(m)) return null;
    [beats, unit] = [m, 4];
  } else {
    const x = /^\s*(\d{1,2})\s*\/\s*(\d{1,2})\s*$/.exec(m);
    if (!x) return null;
    [beats, unit] = [Number(x[1]), Number(x[2])];
  }
  return beats >= 1 && beats <= 16 && [2, 4, 8, 16].includes(unit) ? { beats, unit } : null;
}

/** A meter as the spec stores it ("7/8"), or null when it isn't one. */
export function meterText(m: string | number | null | undefined): string | null {
  const p = parseMeter(m);
  return p ? `${p.beats}/${p.unit}` : null;
}

/** The beats to a bar (the grid's), 4 for a meter that doesn't read. */
export const meterBeats = (m: string | number | null | undefined) => parseMeter(m)?.beats ?? 4;

/** ACE-Step's time signature: 2, 3, 4 or 6 beats, the nearest (the lower on a tie), as its prompt writer picks. */
export const aceBeats = (beats: number) => [2, 3, 4, 6].reduce((a, b) => (Math.abs(b - beats) < Math.abs(a - beats) ? b : a));

/** The keys the inspector offers, spelled as ACE-Step's keyscale combo spells them. */
export const KEY_NOTES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"];
export const KEYS = [...KEY_NOTES.map((n) => `${n} major`), ...KEY_NOTES.map((n) => `${n} minor`)];

/**
 * The section names the inspector offers, a score's and a song's: the ones
 * ACE-Step knows as structure tags ([Chorus]; its prompt writer title-cases
 * them). Stable Audio doesn't hear a name, only the words and energies.
 */
export const SCORE_SECTIONS = ["intro", "build", "climax", "release", "drop", "turn", "sting", "transition", "outro"];
export const SONG_SECTIONS = ["intro", "verse", "pre-chorus", "chorus", "bridge", "break", "instrumental", "solo", "outro"];

/** A section's name as the picker shows it: one it offers (any case or spacing), or null (Other: its own text). */
export function sectionChoice(name: string | undefined): string | null {
  const n = (name ?? "").trim().split(/\s+/).join(" ").toLowerCase();
  return [...SCORE_SECTIONS, ...SONG_SECTIONS].includes(n) ? n : null;
}

/** A spec's key as the picker shows it: "" (the model's choice), one of KEYS, or null (Other: its own text). */
export function keyChoice(key: string | undefined): string | null {
  const parts = (key ?? "").trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "";
  if (parts.length !== 2) return null;
  const k = `${parts[0][0].toUpperCase()}${parts[0].slice(1)} ${parts[1].toLowerCase()}`;
  return KEYS.includes(k) ? k : null;
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

/** The sections with the plan's energies where they give none (the server's: 3, or the arc's), so a split or a merge keeps what plays. */
export function withEnergies(sections: CueSection[], planned: { from?: number; to?: number }[]): CueSection[] {
  return sections.map((s, i) => ({ ...s, from: s.from ?? planned[i]?.from, to: s.to ?? planned[i]?.to }));
}

/** The section bar `bar` (0-based) is in, the last for one past the end. */
export function sectionAt(sections: { bars?: number }[], bar: number): number {
  const edges = sectionEdges(sections.map((s) => ({ bars: s.bars ?? 1 })));
  const b = Math.max(0, Math.floor(bar));
  const i = edges.findIndex((e, k) => k > 0 && b < e);
  return i < 0 ? sections.length - 1 : i - 1;
}

/**
 * Where a double-click `x` px from the first bar line splits: the bar line
 * nearest it and the section it's inside. Null on an edge or the cue's ends.
 */
export function splitPoint(sections: { bars?: number }[], x: number, barPx: number): { i: number; bar: number } | null {
  const edges = sectionEdges(sections.map((s) => ({ bars: s.bars ?? 1 })));
  const bar = Math.round(x / Math.max(1e-6, barPx));
  if (edges.includes(bar) || bar <= 0 || bar >= edges[edges.length - 1]) return null;
  return { i: sectionAt(sections, bar), bar };
}

/** A name for a section split off `name`: its stem and the first numeral none of the sections has ("build 2", then "build 3"). */
export function nextSectionName(sections: { name?: string }[], name: string): string {
  const stem = (name.replace(/\s+\d+$/, "") || name).slice(0, 36);
  const taken = new Set(sections.map((s) => s.name));
  let n = 2;
  while (taken.has(`${stem} ${n}`)) n++;
  return `${stem} ${n}`;
}

/**
 * Sections `i` and `i + 1` as one: the first's name and words (the second's
 * words when it has none), their bars summed, energy from the first's start to
 * the second's end, lyrics one after the other. Null when there's no next.
 */
export function mergeSections(sections: CueSection[], i: number): CueSection[] | null {
  const a = sections[i];
  const b = sections[i + 1];
  if (!a || !b) return null;
  const lyrics = [a.lyrics, b.lyrics].filter((x) => x && x.trim()).join("\n");
  const one = asSpec({
    ...a, bars: (a.bars ?? 1) + (b.bars ?? 1), words: a.words || b.words, from: a.from, to: b.to ?? a.to, lyrics,
  } as CueSection);
  return [...sections.slice(0, i), one, ...sections.slice(i + 2)];
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

// ---------------------------------------------------------------------------
// a song's plan, and a cue's theme (the leitmotif)
// ---------------------------------------------------------------------------

const tnum = (n: number) => `t${String(n).padStart(2, "0")}`;

/** A theme as the server says it: "m01 t02", or the file's path. */
export function themeLabel(th: CueTheme | null | undefined): string {
  if (!th) return "";
  return "cue" in th ? `${th.cue} ${tnum(th.take)}` : th.file;
}

/** How the plan's model hears the theme, in words ("" when it doesn't: the plan's warning says why). */
export function themeUseText(t: Pick<CuePlanTheme, "use">, model: string): string {
  switch (t.use) {
    case "plan": return `${model} sings its melody (the take's own plan), at this cue's tempo`;
    case "transcribe": return `${model} sings its melody (SheetSage2 transcribes it first, in the same job)`;
    case "timbre": return `${model} hears its sound as the timbre reference`;
    default: return "";
  }
}

/** The model that hears a theme, for a cue on one that doesn't: YuE2 for a song (sung), ACE-Step for score (its timbre). Null when the cue's model takes one, or the one to switch to isn't offered. */
export function themeModel(kind: CueKind | undefined, target: Target | undefined, targets: Target[]): Target | null {
  if (!target || target.capabilities?.theme) return null;
  const want = kind === "song" ? "melody" : "timbre";
  return targets.find((t) => t.capabilities?.theme === want && (kind !== "song" || t.capabilities?.lyrics))
    ?? targets.find((t) => !!t.capabilities?.theme && (kind !== "song" || t.capabilities?.lyrics)) ?? null;
}

/** A take a theme can be: a finished one of another cue. */
export const themeTakes = (takes: CueTake[]) => takes.filter((t) => t.status === "ok").map((t) => t.take).sort((a, b) => a - b);

/** A song take's plan in a line: "Plan: 44 bars of 2/4, intro, verse, chorus · 0.6 s short". */
export function songSummary(s: CueSong): string {
  const names = s.sections.map((x) => x.name).join(", ");
  const short = s.short == null ? "" : Math.abs(s.short) < 0.05 ? " · its length as planned" : s.short > 0 ? ` · ${s.short.toFixed(1)} s short of it` : ` · ${(-s.short).toFixed(1)} s over it`;
  return `Plan: ${s.bars} bars of ${s.meter}${names ? `, ${names}` : ""}${short}`;
}

/** Where a song's planned sections fall in the cue window (cue time τ: seconds from its in point), clipped to the grid: {name, a, b} in τ. */
export function songBlocks(sections: CueSong["sections"], g: Pick<Grid, "preroll" | "seconds">): { name: string; a: number; b: number; i: number }[] {
  const lo = -g.preroll;
  const hi = g.seconds - g.preroll;
  return sections.map((s, i) => ({ name: s.name, a: Math.max(lo, s.at), b: Math.min(hi, s.at + s.seconds), i }))
    .filter((x) => x.b > x.a);
}

/** A spec with a change, what's emptied left out (as spec.json keeps it). */
/** What a cue is called where it's listed: "Score · 1M3 The Proposal", "Song · m02". */
export function cueTitle(spec: Pick<CueSpec, "id" | "kind" | "label">): string {
  return `${spec.kind === "song" ? "Song" : "Score"} · ${spec.label || spec.id}`;
}

export function withSpec(spec: CueSpec, patch: Partial<CueSpec>): CueSpec {
  const o = { ...spec, ...patch } as Record<string, unknown>;
  for (const [k, v] of Object.entries(o)) {
    if (v == null || v === "" || v === false || (Array.isArray(v) && !v.length && k !== "hits")) delete o[k];
  }
  return o as unknown as CueSpec;
}

// ---------------------------------------------------------------------------
// presets (seriesmith/presets/cue.json): a worked example filling the cue's fields
// ---------------------------------------------------------------------------

/** Whole bars from shares, one at least each, summing to `bars` (the largest remainders get the bars left). Needs a bar a share. */
export function presetBars(shares: number[], bars: number): number[] {
  const total = shares.reduce((n, x) => n + x, 0) || 1;
  const raw = shares.map((x) => (x / total) * bars);
  const out = raw.map((x) => Math.max(1, Math.floor(x)));
  const order = raw.map((_, i) => i).sort((a, b) => (raw[b] - Math.floor(raw[b])) - (raw[a] - Math.floor(raw[a])) || a - b);
  const sum = () => out.reduce((n, x) => n + x, 0);
  for (let k = 0; sum() < bars; k++) out[order[k % order.length]]++;
  while (sum() > bars) {
    const big = out.indexOf(Math.max(...out));
    if (out[big] <= 1) break;
    out[big]--;
  }
  return out;
}

/** The cue's fields a preset sets: kind, style, tempo, meter, key; its sections, orchestra and arc cleared (presetShape fills them). A song on a model that doesn't sing goes to the kind's default model, as the Kind select does. */
export function presetBase(spec: CueSpec, p: CuePreset, modelSings: boolean): CueSpec {
  const f = p.fields;
  const song = f.kind === "song";
  const meter = meterText(f.meter);
  return withSpec(spec, {
    kind: song ? "song" : undefined,
    ...(song && spec.model && !modelSings ? { model: undefined } : {}),
    style: f.style, bpm: f.bpm, meter: meter && meter !== "4/4" ? meter : undefined, key: f.key || undefined,
    sections: undefined, orchestra: undefined, arc: undefined,
  });
}

/**
 * A preset's sections over `bars` bars (null: the plan's not known, so no
 * counts: the server shares them out), the tail merged when the cue has fewer
 * bars than it has sections, and who plays in each bar from each section's levels.
 */
export function presetShape(p: CuePreset, bars: number | null): { sections: CueSection[]; orchestra?: Orchestra } {
  const shape = p.fields.shape.map((s) => ({ ...s, orchestra: { ...(s.orchestra ?? {}) } }));
  while (bars != null && shape.length > Math.max(1, bars)) {
    const b = shape.pop()!;
    const a = shape[shape.length - 1];
    for (const [fam, lv] of Object.entries(b.orchestra)) a.orchestra[fam] = Math.max(a.orchestra[fam] ?? 0, lv);
    shape[shape.length - 1] = { ...a, share: a.share + b.share, to: b.to };
  }
  const counts = bars != null ? presetBars(shape.map((s) => s.share), bars) : null;
  const sections = shape.map((s, i) => asSpec({ name: s.name, bars: counts?.[i], words: s.words, from: s.from, to: s.to } as CueSection));
  if (!counts) return { sections };
  let o: Orchestra = {};
  const edges = sectionEdges(counts.map((n) => ({ bars: n })));
  shape.forEach((s, i) => {
    for (const [fam, lv] of Object.entries(s.orchestra)) o = paintOrchestra(o, [fam], edges[i], edges[i + 1] - 1, lv);
  });
  return Object.keys(o).length ? { sections, orchestra: o } : { sections };
}

/** A cue with a preset's fields, its sections fitted to `bars` bars; its label, span, model, hits, takes, tail and fixed tempo kept. */
export function applyPreset(spec: CueSpec, p: CuePreset, bars: number | null, modelSings: boolean): CueSpec {
  return withSpec(presetBase(spec, p, modelSings), presetShape(p, bars));
}

/** Whether a preset would replace something of the cue's own (its sections, style or orchestration): ask first. */
export const presetReplaces = (spec: CueSpec) => !!(spec.sections?.length || spec.style || Object.keys(spec.orchestra ?? {}).length);

/** The presets in the select's groups, the cue's kind's first. */
export function presetGroups(presets: CuePreset[], kind: CueKind | undefined): { group: string; presets: CuePreset[] }[] {
  const groups = [...new Set(presets.map((p) => p.group))];
  const mine = kind === "song" ? "Song" : "Score";
  groups.sort((a, b) => Number(b === mine) - Number(a === mine));
  return groups.map((group) => ({ group, presets: presets.filter((p) => p.group === group) }));
}

// ---------------------------------------------------------------------------
// the Arc tab: shapes, drawing, smoothing, peaks onto hits, sections from the arc
// ---------------------------------------------------------------------------

/** The level the points give at `tau`: linear between them, the first held before and the last after (cue.py's _arc_per_bar). */
export function levelAt(points: ArcPt[], tau: number): number {
  if (!points.length) return 3;
  if (tau <= points[0].tau) return points[0].level;
  for (let k = 1; k < points.length; k++) {
    const b = points[k];
    if (tau > b.tau) continue;
    const a = points[k - 1];
    return b.tau === a.tau ? b.level : a.level + ((tau - a.tau) / (b.tau - a.tau)) * (b.level - a.level);
  }
  return points[points.length - 1].level;
}

/** Points in time order, one a beat (the last given wins), levels to half a level. */
function onBeats(points: ArcPt[], g: Grid): ArcPt[] {
  const by = new Map<number, ArcPt>();
  for (const p of points) {
    const t = snapBeat(g, p.tau);
    by.set(Math.round((t + g.preroll) / g.beat), { tau: t, level: clampLevel(p.level) });
  }
  return [...by.entries()].sort((a, b) => a[0] - b[0]).map((e) => e[1]);
}

/** The preset shapes, each with what it does to the cue. */
export type ArcShape = "slow burn" | "build and release" | "sting" | "pulse" | "from the script";
export const ARC_SHAPES: { id: ArcShape; title: string }[] = [
  { id: "slow burn", title: "Slow burn: quiet for long, rising late to a peak at the out point" },
  { id: "build and release", title: "Build and release: rising to a peak two thirds in, then falling away" },
  { id: "sting", title: "Sting: loud at once, then falling away" },
  { id: "pulse", title: "Pulse: swelling on each bar line, easing between" },
  { id: "from the script", title: "From the script: a gentle default shape, a little rise that settles. The script's music: notes reach the model as words, not as a curve" },
];
// each shape as (fraction of the span, level)
const SHAPES: Record<Exclude<ArcShape, "pulse">, [number, number][]> = {
  "slow burn": [[0, 1], [0.5, 2], [0.85, 3.5], [1, 5]],
  "build and release": [[0, 2], [0.7, 5], [1, 1.5]],
  sting: [[0, 5], [0.2, 2], [1, 1.5]],
  "from the script": [[0, 2], [0.5, 3], [0.85, 3.5], [1, 2.5]],
};

/** The first and last beats inside the cue's span (its in point to its out point), cue time. */
function spanBeats(g: Grid, span: number): [number, number] {
  const first = Math.ceil(g.preroll / g.beat - 1e-6);
  const last = Math.min(g.bars * g.meter, Math.floor((span + g.preroll) / g.beat + 1e-6));
  return last > first ? [first * g.beat - g.preroll, last * g.beat - g.preroll] : [snapBeat(g, 0), snapBeat(g, span)];
}

/** A preset shape over the cue's span (its in point to its out point), on beats; beyond them the arc holds. */
export function presetPoints(shape: ArcShape, g: Grid, span: number): ArcPt[] {
  const [lo, hi] = spanBeats(g, span);
  if (shape === "pulse") {
    const out: ArcPt[] = [];
    for (let b = 0; b <= g.bars; b++) {
      const t = b * g.bar - g.preroll;
      if (t >= lo - 1e-6 && t <= hi + 1e-6) out.push({ tau: t, level: 4 });
      const mid = t + g.bar / 2;
      if (mid > lo + 1e-6 && mid < hi - 1e-6) out.push({ tau: mid, level: 2.5 });
    }
    return onBeats(out.length ? out : [{ tau: lo, level: 3 }], g);
  }
  return onBeats(SHAPES[shape].map(([f, level]) => ({ tau: lo + f * (hi - lo), level })), g);
}

/**
 * A freehand stroke as points: each sample snapped to a beat (the last on a
 * beat wins), then simplified (Douglas-Peucker: a point is kept when the line
 * without it would be `tol` levels or more off it).
 */
export function drawnPoints(samples: ArcPt[], g: Grid, tol = 0.4): ArcPt[] {
  const pts = onBeats(samples, g);
  if (pts.length <= 2) return pts;
  const keep = new Set([0, pts.length - 1]);
  const walk = (a: number, b: number) => {
    let worst = -1;
    let far = 0;
    for (let k = a + 1; k < b; k++) {
      const d = Math.abs(pts[k].level - levelAt([pts[a], pts[b]], pts[k].tau));
      if (d > far) [far, worst] = [d, k];
    }
    if (worst >= 0 && far >= tol) {
      keep.add(worst);
      walk(a, worst);
      walk(worst, b);
    }
  };
  walk(0, pts.length - 1);
  return pts.filter((_, k) => keep.has(k));
}

/** A stroke drawn over the points: those it spans replaced by it, the rest kept. */
export function mergeStroke(points: ArcPt[], stroke: ArcPt[]): ArcPt[] {
  if (!stroke.length) return points;
  const a = stroke[0].tau;
  const b = stroke[stroke.length - 1].tau;
  return [...points.filter((p) => p.tau < a - 1e-6 || p.tau > b + 1e-6), ...stroke].sort((x, y) => x.tau - y.tau);
}

/** Each point between two others moved toward them ((a + 2b + c) / 4, to half a level), then those on a straight line between their neighbours dropped. */
export function smoothPoints(points: ArcPt[]): ArcPt[] {
  if (points.length < 3) return points;
  const soft = points.map((p, k) => (k === 0 || k === points.length - 1 ? p
    : { tau: p.tau, level: clampLevel((points[k - 1].level + 2 * p.level + points[k + 1].level) / 4) }));
  return soft.filter((p, k) => k === 0 || k === soft.length - 1 || Math.abs(levelAt([soft[k - 1], soft[k + 1]], p.tau) - p.level) > 1e-6);
}

/**
 * Where the arc turns: each point where its direction changes (the arc held
 * flat before the first and after the last), a peak (or a high plateau's edge)
 * or a low.
 */
export function turningPoints(points: ArcPt[]): { i: number; kind: "peak" | "low" }[] {
  const out: { i: number; kind: "peak" | "low" }[] = [];
  const dir = (a: number, b: number) => Math.sign(Math.round((b - a) * 100));
  points.forEach((p, i) => {
    const before = i > 0 ? dir(points[i - 1].level, p.level) : 0;
    const after = i < points.length - 1 ? dir(p.level, points[i + 1].level) : 0;
    if (before !== after) out.push({ i, kind: before > 0 || after < 0 ? "peak" : "low" });
  });
  return out;
}

/** Which hits a turn of the arc goes to: a peak where the music arrives, a low where it drops, either on a turn. */
const SNAP_KINDS: Record<"peak" | "low", string[]> = { peak: ["arrive", "turn"], low: ["drop", "turn"] };

/**
 * Each peak and low of the arc moved onto the nearest hit within a bar (a peak
 * onto an arrive or a turn, a low onto a drop or a turn), kept between its
 * neighbours. `moved`: how many went.
 */
export function snapToHits(points: ArcPt[], hits: { t: number; kind: string }[], g: Grid): { points: ArcPt[]; moved: number } {
  const out = points.map((p) => ({ ...p }));
  let moved = 0;
  for (const { i, kind } of turningPoints(points)) {
    const lo = i > 0 ? out[i - 1].tau : -g.preroll - 1e-6;
    const hi = i < out.length - 1 ? out[i + 1].tau : g.seconds - g.preroll + 1e-6;
    let best: number | null = null;
    for (const h of hits) {
      if (!SNAP_KINDS[kind].includes(h.kind) || Math.abs(h.t - out[i].tau) > g.bar + 1e-6 || h.t <= lo || h.t >= hi) continue;
      if (best == null || Math.abs(h.t - out[i].tau) < Math.abs(best - out[i].tau)) best = h.t;
    }
    if (best != null && Math.abs(best - out[i].tau) > 1e-6) {
      out[i].tau = best;
      moved++;
    }
  }
  return { points: out, moved };
}

/** A section's direction as a name: build (rising), release (falling), hold. */
const shapeName = (from: number, to: number) => (to > from ? "build" : to < from ? "release" : "hold");

/**
 * Sections cut where the arc turns (its peaks and lows, on the nearest bar
 * line), each its energy from and to as the arc has them at its edges.
 */
export function sectionsFromArc(points: ArcPt[], g: Grid): (CueSection & { bars: number; from: number; to: number })[] {
  const cuts = [...new Set(turningPoints(points).map(({ i }) => Math.round((points[i].tau + g.preroll) / g.bar)))]
    .filter((b) => b > 0 && b < g.bars).sort((a, b) => a - b);
  const edges = [0, ...cuts, g.bars];
  return edges.slice(0, -1).map((e, k) => {
    const from = clampLevel(levelAt(points, e * g.bar - g.preroll));
    const to = clampLevel(levelAt(points, edges[k + 1] * g.bar - g.preroll));
    return { name: shapeName(from, to), bars: edges[k + 1] - e, from, to };
  });
}

/**
 * Detail inside a section the model can't follow: a bar inside it (not its
 * first or last) half a level or more above both its ends (a peak) or below
 * both (a dip), the furthest of each, from the plan's energy per bar.
 */
export function arcFlags(arc: number[], sections: { bars: number }[]): { section: number; bar: number; kind: "peak" | "dip" }[] {
  const out: { section: number; bar: number; kind: "peak" | "dip" }[] = [];
  const edges = sectionEdges(sections);
  sections.forEach((_, i) => {
    const a = edges[i];
    const b = Math.min(edges[i + 1], arc.length) - 1;
    if (b - a < 2) return;
    const hi = Math.max(arc[a], arc[b]);
    const lo = Math.min(arc[a], arc[b]);
    let peak = -1;
    let dip = -1;
    for (let k = a + 1; k < b; k++) {
      if (arc[k] >= hi + 0.5 && (peak < 0 || arc[k] > arc[peak])) peak = k;
      if (arc[k] <= lo - 0.5 && (dip < 0 || arc[k] < arc[dip])) dip = k;
    }
    if (peak >= 0) out.push({ section: i, bar: peak, kind: "peak" });
    if (dip >= 0) out.push({ section: i, bar: dip, kind: "dip" });
  });
  return out.sort((x, y) => x.bar - y.bar);
}

/**
 * The sections whose words don't say what the arc does there: their energy a
 * level or more from the arc's on average, or going another way (rising,
 * steady, falling: by three quarters of a level or more, over two bars or more).
 */
export function wordsOffArc(arc: number[], sections: { bars: number; from: number; to: number }[]): number[] {
  const out: number[] = [];
  const edges = sectionEdges(sections);
  const dir = (d: number) => (Math.abs(d) < 0.75 ? 0 : Math.sign(d));
  sections.forEach((s, i) => {
    const bars = arc.slice(edges[i], edges[i + 1]);
    if (!bars.length) return;
    const mean = bars.reduce((n, x) => n + x, 0) / bars.length;
    const way = bars.length >= 2 && dir(bars[bars.length - 1] - bars[0]) !== dir(s.to - s.from);
    if (Math.abs(mean - (s.from + s.to) / 2) >= 1 || way) out.push(i);
  });
  return out;
}

/**
 * Section `i` split at bar `bar` (from the first bar line), so a peak or a
 * dip inside it becomes an edge the model follows: the first part going to the
 * arc's level there, the second from it. Null when `bar` isn't inside it.
 */
export function splitSection(sections: CueSection[], i: number, bar: number, arc: number[]): CueSection[] | null {
  const edges = sectionEdges(sections.map((s) => ({ bars: s.bars ?? 1 })));
  if (!sections[i] || bar <= edges[i] || bar >= edges[i + 1]) return null;
  const s = sections[i];
  const at = clampLevel(arc[bar] ?? s.to ?? 3);
  const first = asSpec({ ...s, bars: bar - edges[i], to: at });
  const second = asSpec({ ...s, name: nextSectionName(sections, s.name), bars: edges[i + 1] - bar, from: at });
  return [...sections.slice(0, i), first, second, ...sections.slice(i + 1)];
}

// what the model hears of a section's energy (targets/music/common.py's dynamics)
const HEARD = ["", "very quiet", "quiet", "moderate", "strong", "fortissimo"];
const HEARD_FULL = ["", "very quiet, sparse", "quiet", "moderate", "strong, full", "fortissimo, full orchestra"];
const wholeLevel = (x: number | undefined) => Math.max(1, Math.min(5, Math.round(x ?? 3)));

/** A section's energy as the prompt writer words it: "rising from quiet to strong, building". */
export function dynamics(sec: { from?: number; to?: number }): string {
  const a = wholeLevel(sec.from);
  const b = wholeLevel(sec.to ?? sec.from);
  if (b > a) return `rising from ${HEARD[a]} to ${HEARD[b]}, building`;
  if (b < a) return `falling from ${HEARD[a]} to ${HEARD[b]}, receding`;
  return `${HEARD_FULL[a]}, sustained`;
}

/** What plays in a section and how loud, as the model is told it (common.py's section_words). */
export function sectionWords(sec: { words?: string; from?: number; to?: number }): string {
  const words = (sec.words ?? "").split(/\s+/).join(" ").replace(/^[\s,.]+|[\s,.]+$/g, "");
  return [words, dynamics(sec)].filter(Boolean).join(", ");
}

// ---------------------------------------------------------------------------
// the orchestration grid: {family: [level per bar]}, 0 off, 1 under, 2 present, 3 lead
// ---------------------------------------------------------------------------

export type Orchestra = Record<string, number[]>;
export const ORCH_LEVELS = ["off", "under", "present", "lead"];
/** the rows a cue starts with (a family off throughout isn't stored, so the rows are kept by the window) */
export const ORCH_FAMILIES = ["strings", "solo horn", "brass", "woodwinds", "timpani/percussion", "piano", "harp", "choir"];

/** As the server stores it: trailing offs trimmed, a family off throughout dropped. */
export function trimOrchestra(o: Orchestra | undefined): Orchestra {
  const out: Orchestra = {};
  for (const [fam, levels] of Object.entries(o ?? {})) {
    const l = levels.slice();
    while (l.length && !l[l.length - 1]) l.pop();
    if (l.length) out[fam] = l;
  }
  return out;
}

/** The families `fams`, bars `a` to `b` (both included, either order), painted `level`. */
export function paintOrchestra(o: Orchestra | undefined, fams: string[], a: number, b: number, level: number): Orchestra {
  const out: Orchestra = { ...(o ?? {}) };
  const [lo, hi] = a <= b ? [a, b] : [b, a];
  for (const fam of fams) {
    const l = (out[fam] ?? []).slice();
    while (l.length <= hi) l.push(0);
    for (let k = Math.max(0, lo); k <= hi; k++) l[k] = level;
    out[fam] = l;
  }
  return trimOrchestra(out);
}

/** The brush that steps a cell instead of painting a level (the grid's default). */
export const ORCH_STEP = ORCH_LEVELS.length;

/**
 * The level a stroke paints: a level brush's own; the step brush's, the first
 * cell's level stepped on (off, under, present, lead, off), or back with `down`
 * (Shift), and that level over the whole stroke.
 */
export function strokeLevel(o: Orchestra | undefined, fam: string, bar: number, brush: number, down = false): number {
  if (brush !== ORCH_STEP) return brush;
  const n = ORCH_LEVELS.length;
  return ((o?.[fam]?.[bar] ?? 0) + (down ? n - 1 : 1)) % n;
}

/** A family's name as the server keeps it (whitespace collapsed, 40 characters). */
export const familyName = (s: string) => s.split(/\s+/).join(" ").trim().slice(0, 40);

/** A family renamed, its place kept (null: the name is empty or taken). */
export function renameFamily(o: Orchestra | undefined, from: string, to: string): Orchestra | null {
  const name = familyName(to);
  if (!name || (name !== from && o && name in o)) return null;
  const out: Orchestra = {};
  for (const [fam, l] of Object.entries(o ?? {})) out[fam === from ? name : fam] = l;
  return out;
}

export function removeFamily(o: Orchestra | undefined, fam: string): Orchestra {
  const out = { ...(o ?? {}) };
  delete out[fam];
  return out;
}

/** The grid's rows: those kept for the cue (else the families it has, then the starting ones), and any family it has that they lack. */
export function orchestraRows(kept: string[] | undefined, o: Orchestra | undefined): string[] {
  const has = Object.keys(o ?? {});
  const rows = kept ? kept.slice() : [...has, ...ORCH_FAMILIES.filter((f) => !has.includes(f))];
  for (const f of has) if (!rows.includes(f)) rows.push(f);
  return rows;
}

/**
 * The cells the model won't hear as painted: in a section where a family
 * changes, each of its bars below its strongest there (the section is told
 * the strongest). Keys "family|bar".
 */
export function heldCells(o: Orchestra | undefined, sections: { bars: number }[]): Set<string> {
  const out = new Set<string>();
  const edges = sectionEdges(sections);
  for (const [fam, l] of Object.entries(o ?? {})) {
    sections.forEach((_, i) => {
      let top = 0;
      for (let k = edges[i]; k < edges[i + 1]; k++) top = Math.max(top, l[k] ?? 0);
      if (!top) return;
      for (let k = edges[i]; k < edges[i + 1]; k++) if ((l[k] ?? 0) < top) out.add(`${fam}|${k}`);
    });
  }
  return out;
}

// ---------------------------------------------------------------------------
// a take's bars: selected by dragging, comped, lowered
// ---------------------------------------------------------------------------

/** The bars `[a, b)` a drag from x0 to x1 (pixels from the first bar line) covers: one at least. */
export function barSpan(g: Grid, x0: number, x1: number, pps: number): [number, number] {
  const w = g.bar * pps;
  const a = Math.min(g.bars - 1, Math.max(0, Math.floor(Math.min(x0, x1) / w)));
  const b = Math.max(a + 1, Math.min(g.bars, Math.ceil(Math.max(x0, x1) / w - 1e-6)));
  return [a, b];
}

/** Bars `[a, b)` as the ruler numbers them: "bar 3", "bars 3-6". */
export const barsLabel = ([a, b]: [number, number]) => (b - a === 1 ? `bar ${a + 1}` : `bars ${a + 1}-${b}`);

/** A comp's label: "comp of t03 + t01 bars 5-8". */
/** A repaint's note in the takes list: "repainted bars 3-4 from t02" (new music: "freshly"). */
export const repaintLabel = (r: { from: number; bars: [number, number]; fresh?: boolean }) =>
  `${r.fresh ? "freshly " : ""}repainted ${barsLabel(r.bars)} from t${String(r.from).padStart(2, "0")}`;

/** Why a take's bars can't be repainted ("" when they can): its model can't, or it isn't finished. */
export function repaintWhy(t: { status: string; target?: string; measured?: unknown }, targets: { id: string; label: string; capabilities?: { repaint?: boolean } }[]): string {
  if (t.status !== "ok" || !t.measured) return "Only a finished take";
  const tg = targets.find((x) => x.id === t.target);
  if (!tg) return `Its model (${t.target ?? "unknown"}) isn't here`;
  if (!tg.capabilities?.repaint) return `${tg.label} can't make bars of a take again (measured: docs/SOUND.md 'Measured: repaint'): comp them from another take`;
  return "";
}

export const compLabel = (c: { base: number; from: number; bars: [number, number] }) =>
  `comp of t${String(c.base).padStart(2, "0")} + t${String(c.from).padStart(2, "0")} ${barsLabel(c.bars)}`;

/** Bars `[a, b)` in cue time, kept inside the cue's span (its mix item runs from its in point to its out point); null when none of them is. */
export function barsInSpan(g: Grid, bars: [number, number], span: number): [number, number] | null {
  const a = Math.max(0, bars[0] * g.bar - g.preroll);
  const b = Math.min(span, bars[1] * g.bar - g.preroll);
  return b > a ? [a, b] : null;
}
