// Music cues in the mock (seriesmith/cue.py, much simplified): a spec checked
// as check_spec does the shape, a plan worked out against Play all's layout
// (the tempo near the asked one that puts the first must-hit on a bar line,
// whole bars from the pre-roll, sections given or from the hits, an energy per
// bar), and made-up measurements for a take, enough for the dev page and the
// tests to draw the cue window and round-trip its edits.

import { anchorTime } from "../lib/mix";
import type { PlayItem } from "../lib/playlist";
import type { CueHit, CueMeasured, CuePlan, CueSection, CueSpec, Mix, Target } from "../types";

export class CueError extends Error {
  constructor(message: string, public status = 400) {
    super(message);
  }
}

export const MUSIC_TARGETS: Target[] = [
  {
    id: "stable_audio3", kind: "music", label: "Stable Audio 3 Medium", short: "Stable Audio 3", default: true,
    capabilities: { mode: "t2m", tempo: "text", structure: "story", lyrics: false, max_seconds: 380 },
    presets: { final: { takes: 8 }, proxy: { takes: 8 } },
  },
  {
    id: "ace_step15", kind: "music", label: "ACE-Step 1.5 XL", short: "ACE-Step 1.5",
    capabilities: { mode: "t2m", tempo: "bpm", structure: "sections", lyrics: true, max_seconds: 600 },
    presets: { final: { takes: 8 }, proxy: { takes: 8 } },
  },
];

const FIELDS = ["id", "kind", "label", "model", "in", "out", "style", "bpm", "fixed_tempo", "meter", "key", "orchestra", "tail", "sections", "arc", "hits", "takes", "seed"];
const ORCHESTRA_LEVELS = ["", "under", "present", "lead"];
const LEVEL_WORDS = ["", "sparse", "quiet", "moderate", "full", "full orchestra fortissimo"];

function level(v: unknown, what: string): number {
  if (typeof v !== "number" || v < 1 || v > 5) throw new CueError(`${what} is an energy from 1 to 5, not ${JSON.stringify(v)}`);
  return v;
}

/** A spec in its stored form (cue.check_spec, the shape only). */
export function checkCue(raw: CueSpec): CueSpec {
  if (!raw || typeof raw !== "object") throw new CueError("a cue must be an object");
  const unknown = Object.keys(raw).filter((k) => !FIELDS.includes(k));
  if (unknown.length) throw new CueError(`unknown cue field(s) ${unknown.sort().join(", ")}`);
  if (typeof raw.id !== "string" || !/^[A-Za-z0-9_-]{1,40}$/.test(raw.id)) throw new CueError(`a cue's id is 1-40 letters, digits, _ or -, not ${JSON.stringify(raw.id)}`);
  for (const k of ["in", "out"] as const) {
    const a = raw[k];
    if (!a || typeof a.shot !== "string" || !Number.isInteger(a.frame) || a.frame < 0) throw new CueError(`cue ${raw.id}'s ${k} needs its shot and frame`);
  }
  const out: CueSpec = { id: raw.id, in: { ...raw.in }, out: { ...raw.out } };
  if (raw.kind != null && raw.kind !== "score" && raw.kind !== "song") throw new CueError(`cue ${raw.id}'s kind is score or song, not ${JSON.stringify(raw.kind)}`);
  if (raw.kind === "song") out.kind = "song";
  for (const k of ["label", "style", "key"] as const) if (typeof raw[k] === "string" && raw[k]!.trim()) out[k] = raw[k]!.trim().split(/\s+/).join(" ");
  if (raw.model) {
    if (!MUSIC_TARGETS.some((t) => t.id === raw.model)) throw new CueError(`cue ${raw.id}'s model ${JSON.stringify(raw.model)} isn't a music target`);
    out.model = raw.model;
  }
  if (raw.bpm != null) {
    if (typeof raw.bpm !== "number" || raw.bpm < 30 || raw.bpm > 240) throw new CueError(`cue ${raw.id}'s bpm is 30 to 240, not ${raw.bpm}`);
    out.bpm = Math.round(raw.bpm * 1000) / 1000;
  }
  if (raw.fixed_tempo) out.fixed_tempo = true;
  const m = raw.meter ?? 4;
  if (![2, 3, 4, 6].includes(m)) throw new CueError(`cue ${raw.id}'s meter is 2, 3, 4 or 6 beats to the bar, not ${m}`);
  if (m !== 4) out.meter = m;
  const tail = raw.tail ?? 2;
  if (typeof tail !== "number" || tail < 0 || tail > 30) throw new CueError(`cue ${raw.id}'s tail is 0 to 30 seconds, not ${tail}`);
  if (tail !== 2) out.tail = tail;
  const secs = (raw.sections ?? []).map((s, i) => {
    const o: CueSection = { name: (s.name || `section ${i + 1}`).trim().slice(0, 40) };
    if (s.bars != null) {
      if (!Number.isInteger(s.bars) || s.bars < 1) throw new CueError(`cue ${raw.id}'s section ${i + 1}'s bars is a whole number, 1 or more`);
      o.bars = s.bars;
    }
    if (s.words) o.words = String(s.words).trim();
    if (s.lyrics) o.lyrics = String(s.lyrics).trim();
    if (s.from != null) o.from = level(s.from, `cue ${raw.id}'s section ${i + 1}'s from`);
    if (s.to != null) o.to = level(s.to, `cue ${raw.id}'s section ${i + 1}'s to`);
    return o;
  });
  if (secs.length) out.sections = secs;
  const arc = (raw.arc ?? []).map((p, i) => ({ at: { ...p.at }, level: level(p.level, `cue ${raw.id}'s arc point ${i + 1}`) }));
  if (arc.length) out.arc = arc;
  if (raw.orchestra && Object.keys(raw.orchestra).length) {
    if (typeof raw.orchestra !== "object" || Array.isArray(raw.orchestra)) throw new CueError(`cue ${raw.id}'s orchestra is {family: [level per bar]}`);
    const clean: Record<string, number[]> = {};
    for (const [fam, levels] of Object.entries(raw.orchestra)) {
      const name = fam.trim().split(/\s+/).join(" ").slice(0, 40);
      if (!name) throw new CueError(`cue ${raw.id}'s orchestra has a family with no name`);
      if (!Array.isArray(levels) || levels.length > 256 || !levels.every((x) => Number.isInteger(x) && x >= 0 && x <= 3)) {
        throw new CueError(`cue ${raw.id}'s orchestra ${name}: a level per bar, 0 (off) to 3 (lead)`);
      }
      const l = levels.slice();
      while (l.length && !l[l.length - 1]) l.pop();
      if (l.length) clean[name] = l;
    }
    if (Object.keys(clean).length) out.orchestra = clean;
  }
  if (raw.hits != null) out.hits = [...raw.hits];
  if (raw.takes != null) {
    if (!Number.isInteger(raw.takes) || raw.takes < 1 || raw.takes > 16) throw new CueError(`cue ${raw.id}'s takes is a whole number up to 16`);
    out.takes = raw.takes;
  }
  if (raw.seed != null) out.seed = raw.seed;
  return out;
}

function fill(sections: CueSection[], bars: number): (CueSection & { bars: number; from: number; to: number })[] {
  const secs = sections.map((s) => ({ ...s }));
  const fixed = secs.reduce((n, s) => n + (s.bars ?? 0), 0);
  const loose = secs.filter((s) => !s.bars);
  const left = Math.max(loose.length, bars - fixed);
  loose.forEach((s, i) => (s.bars = Math.floor(left / loose.length) + (i < left % loose.length ? 1 : 0)));
  const diff = bars - secs.reduce((n, s) => n + (s.bars ?? 0), 0);
  if (secs.length && diff) secs[secs.length - 1].bars = Math.max(1, secs[secs.length - 1].bars! + diff);
  return secs.map((s) => ({ ...s, bars: s.bars!, from: s.from ?? 3, to: s.to ?? s.from ?? 3 }));
}

function fromHits(bars: number, hits: CueHit[], preroll: number, bar: number): (CueSection & { bars: number; from: number; to: number })[] {
  const cuts: [number, string][] = [];
  for (const h of hits) {
    if (h.kind === "accent") continue;
    const b = Math.round((h.t + preroll) / bar);
    if (b > 0 && b < bars && !cuts.some((c) => c[0] === b)) cuts.push([b, h.kind]);
  }
  cuts.sort((a, b) => a[0] - b[0]);
  const edges = [0, ...cuts.map((c) => c[0]), bars];
  const kinds: (string | null)[] = [null, ...cuts.map((c) => c[1])];
  return edges.slice(0, -1).map((e, i) => {
    const start = kinds[i];
    const end = kinds[i + 1] ?? null;
    let [a, b] = [2, 3];
    if (end === "arrive") [a, b] = [2, 5];
    if (start === "arrive") [a, b] = [5, 4];
    if (start === "drop") [a, b] = [1, 1.5];
    const name = ({ arrive: "climax", drop: "drop", turn: "turn" } as Record<string, string>)[start ?? ""]
      ?? (end === "arrive" ? "build" : i === 0 ? "intro" : "section");
    return { name, bars: edges[i + 1] - e, from: a, to: b };
  });
}

function perBar(points: [number, number][], bars: number, bar: number, start: number): number[] {
  const pts = [...points].sort((a, b) => a[0] - b[0]);
  const out: number[] = [];
  for (let b = 0; b < bars; b++) {
    const t = start + (b + 0.5) * bar;
    let v = pts[pts.length - 1][1];
    if (t <= pts[0][0]) v = pts[0][1];
    else {
      for (let i = 0; i + 1 < pts.length; i++) {
        const [t0, a] = pts[i];
        const [t1, c] = pts[i + 1];
        if (t0 <= t && t <= t1) {
          v = t1 > t0 ? a + (c - a) * (t - t0) / (t1 - t0) : c;
          break;
        }
      }
    }
    out.push(Math.round(v * 100) / 100);
  }
  return out;
}

/** Sections with the orchestration grid in their words: each family's strongest level over the section's bars, strongest first, after its own words (cue.orchestrate). */
export function orchestrate<S extends CueSection & { bars: number }>(sections: S[], orchestra: Record<string, number[]>): S[] {
  let b0 = 0;
  return sections.map((s) => {
    const who: [number, string][] = [];
    for (const [fam, levels] of Object.entries(orchestra)) {
      const lv = Math.max(0, ...levels.slice(b0, b0 + s.bars));
      if (lv) who.push([lv, fam]);
    }
    b0 += s.bars;
    who.sort((x, y) => y[0] - x[0]);
    const words = who.map(([lv, fam]) => `${fam} ${ORCHESTRA_LEVELS[lv]}`).join(", ");
    const own = (s.words ?? "").trim().replace(/^[\s,.]+|[\s,.]+$/g, "");
    return words ? { ...s, words: [own, words].filter(Boolean).join(", ") } : { ...s };
  });
}

/** What a cue is asked against the cut (cue.plan, simplified). Throws a CueError when its anchors aren't in it. */
export function planCue(spec: CueSpec, items: PlayItem[], fps: number, mix: Mix, notes: Record<string, string> = {}): CuePlan {
  const a = anchorTime(items, spec.in, fps);
  const b = anchorTime(items, spec.out, fps);
  if (a == null || b == null) throw new CueError(`cue ${spec.id}: ${a == null ? spec.in.shot : spec.out.shot} isn't in the cut`);
  if (b <= a) throw new CueError(`cue ${spec.id}: its out is at or before its in`);
  const span = b - a;
  const want = spec.hits != null ? new Set(spec.hits) : null;
  const hits: CueHit[] = [];
  for (const h of mix.hits ?? []) {
    const t = anchorTime(items, h.at, fps);
    if (t == null || (want && !want.has(h.id)) || (!want && (t < a || t > b))) continue;
    hits.push({ id: h.id, name: h.name || h.id, kind: h.kind ?? "accent", must: h.must !== false, t: Math.round((t - a) * 10000) / 10000 });
  }
  hits.sort((x, y) => x.t - y.t);
  const meter = spec.meter ?? 4;
  const asked = spec.bpm ?? 100;
  // the tempo within 8 % whose bars put the must-hits nearest a line, from a pre-roll that lands the first
  const musts = hits.filter((h) => h.must);
  let bpm = asked;
  let best = Infinity;
  const spread = spec.fixed_tempo ? 0 : 0.08;
  for (let k = -40; k <= 40; k++) {
    const cand = asked * (1 + (spread * k) / 40);
    const bar = (60 * meter) / cand;
    const pre = musts.length ? (bar - (musts[0].t % bar)) % bar : 0;
    // an accent on a beat, the rest on bar lines; a tempo further from the asked one costs a little
    const err = musts.reduce((n, h) => {
      const unit = h.kind === "accent" ? bar / meter : bar;
      const x = (h.t + pre) / unit;
      return n + Math.abs(x - Math.round(x)) * unit;
    }, 0) + (Math.abs(cand - asked) / asked) * bar * 0.5;
    if (err < best - 1e-9) {
      best = err;
      bpm = cand;
    }
  }
  bpm = Math.round(bpm * 1000) / 1000;
  const bar = (60 * meter) / bpm;
  const beat = bar / meter;
  const first = musts[0] ?? hits[0];
  const preroll = Math.round((first ? (bar - (first.t % bar)) % bar || 0 : 0) * 10000) / 10000 || Math.round(bar * 10000) / 10000;
  const errors = hits.map((h) => {
    const unit = h.kind === "accent" ? beat : bar;
    const x = (h.t + preroll) / unit;
    return Math.round((x - Math.round(x)) * unit * fps * 100) / 100;
  });
  const worst = Math.max(0, ...errors.filter((_, i) => hits[i].must).map(Math.abs));
  const tail = spec.tail ?? 2;
  const bars = Math.max(1, Math.ceil((preroll + span + tail) / bar - 1e-6));
  const seconds = Math.round(bars * bar * 1000) / 1000;
  let sections = spec.sections?.length ? fill(spec.sections, bars) : fromHits(bars, hits, preroll, bar);
  if (spec.orchestra) sections = orchestrate(sections, spec.orchestra);
  let pts: [number, number][] = [];
  if (spec.arc?.length) {
    for (const p of spec.arc) {
      const t = anchorTime(items, p.at, fps);
      if (t != null) pts.push([t - a, p.level]);
    }
  }
  if (!pts.length) {
    let t = -preroll;
    for (const s of sections) {
      pts.push([t + 0.01, s.from], [t + s.bars * bar - 0.01, s.to]);
      t += s.bars * bar;
    }
  }
  const arc = pts.length ? perBar(pts, bars, bar, -preroll) : Array(bars).fill(3);
  const target = spec.model ?? "stable_audio3";
  const ask = Math.round(bpm);
  const stretch = Math.round((bpm / ask) * 100000) / 100000;
  const shotNotes = items.filter((it) => it.start < b && it.start + it.dur > a && notes[it.shot]).map((it) => ({ shot: it.shot, music: notes[it.shot] }));
  const head = `${spec.style || "cinematic orchestral film score"}, ${ask} BPM, ${meter}/4${spec.key ? `, ${spec.key}` : ""}.`;
  const mood = shotNotes.length ? ` Mood: ${shotNotes.map((n) => n.music).join("; ")}.` : "";
  const story = sections.map((s, i) => `${i === 0 ? "Opens with" : i === sections.length - 1 ? "ending with" : "then"} ${s.words || s.name}, ${LEVEL_WORDS[Math.round(s.from)]}${s.to !== s.from ? ` to ${LEVEL_WORDS[Math.round(s.to)]}` : ""}`).join(", ") + ".";
  const values: Record<string, unknown> = { seconds: Math.round(seconds * stretch * 1000) / 1000 };
  if (target === "ace_step15") values.lyrics = sections.map((s) => `[${s.name}]\n${s.lyrics || Array(s.bars).fill(`(${s.words || "instrumental"})`).join("\n")}`).join("\n\n");
  return {
    target, fps, span: Math.round(span * 1000) / 1000, hits,
    fit: { bpm, ask_bpm: ask, stretch, errors, worst_must: worst },
    bars, bar: Math.round(bar * 100000) / 100000, preroll, seconds, ask_seconds: values.seconds as number, sections, arc,
    prompt: { prompt: target === "ace_step15" ? head.replace(/, \d+ BPM/, "").replace(/\.$/, "") : head + mood + " " + story, negative: null, values },
    notes: shotNotes,
  };
}

function rng(seed: number) {
  let x = seed >>> 0 || 1;
  return () => {
    x ^= x << 13;
    x ^= x >>> 17;
    x ^= x << 5;
    return ((x >>> 0) % 100000) / 100000;
  };
}

/** A take's measurements, made up from its seed: near the plan, never exact. */
export function measureCue(plan: CuePlan, seed: number): CueMeasured {
  const r = rng(seed);
  const downbeat = Math.round(r() * 1.5 * 1000) / 1000;
  const errs = plan.hits.map(() => (r() < 0.15 ? null : Math.round((r() * 6 - 3) * 100) / 100));
  const musts = errs.filter((_, i) => plan.hits[i].must).map((e) => (e == null ? plan.bar / 8 * plan.fps : Math.abs(e)));
  const worst = Math.round(Math.max(0, ...musts) * 100) / 100;
  const levels = plan.arc.map((a) => Math.round((-30 + a * 4 + (r() * 8 - 4)) * 10) / 10);
  const shape = Math.round((0.2 + r() * 0.3) * 1000) / 1000;
  const heard = Math.round(plan.fit.ask_bpm * (1 + (r() - 0.5) * 0.04) * 100) / 100;
  return {
    bpm_heard: heard, tempo_heard: Math.abs(heard - plan.fit.ask_bpm) / plan.fit.ask_bpm <= 0.03,
    stretch: plan.fit.stretch, downbeat, offset: Math.round((downbeat + plan.preroll) * 10000) / 10000,
    hit_errors: errs, worst_must: worst, levels, shape_error: shape,
    score: Math.round((worst / Math.max(1, plan.fps / 8) + shape) * 10000) / 10000,
  };
}

/** A comp's measurements (cue.comp measures the spliced file): the base take's outside bars [a, b), the other's inside. */
export function compMeasured(plan: CuePlan, base: CueMeasured, other: CueMeasured, bars: [number, number]): CueMeasured {
  const [a, b] = bars;
  const inside = (bar: number) => bar >= a && bar < b;
  const levels = base.levels.map((x, k) => (inside(k) ? other.levels[k] ?? x : x));
  const hitErrors = plan.hits.map((h, i) => (inside(Math.floor((h.t + plan.preroll) / plan.bar)) ? other.hit_errors[i] : base.hit_errors[i]) ?? null);
  const musts = hitErrors.filter((_, i) => plan.hits[i]?.must).map((e) => (e == null ? plan.bar / 8 * plan.fps : Math.abs(e)));
  const worst = Math.round(Math.max(0, ...musts) * 100) / 100;
  const n = Math.max(1, levels.length);
  const shape = Math.round((((base.shape_error ?? 0.4) * (n - (b - a))) + (other.shape_error ?? 0.4) * (b - a)) / n * 1000) / 1000;
  return {
    ...base, hit_errors: hitErrors, worst_must: worst, levels, shape_error: shape,
    score: Math.round((worst / Math.max(1, plan.fps / 8) + shape) * 10000) / 10000,
  };
}
