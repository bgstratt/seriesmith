// The storyboard's sums and shapes: GET /seriesmith/storyboard/block's answer
// (seriesmith/core/blocking.py) and how much of the board each beat takes.

export interface BlockBeat {
  beat: string;
  act: string;
  guidance: string;
  shots: number;
  seconds: number;
  first_shot: number;
  thin: boolean;
  /** the beat's span of the story, in percent */
  at?: [number, number];
  /** or the one point it sits at */
  point?: number;
}

export interface BlockAct {
  act: string;
  shots: number;
  seconds: number;
  beats: BlockBeat[];
}

export interface StoryboardBlock {
  structure: string;
  duration: number;
  /** the length each shot comes to */
  shot_seconds: number;
  wanted_shots: number;
  shots: number;
  warnings: string[];
  acts: BlockAct[];
}

export const TILE_W = 28;
export const TILE_GAP = 3;
export const BEAT_MIN_W = 76;

/** A beat's width on the board: its tiles and sequence boxes in one line, wrapping when that's wider than the row. */
export function beatWidth(shots: number, boxes = 0): string {
  const line = Math.max(BEAT_MIN_W, shots * (TILE_W + TILE_GAP) + boxes * (BOX_W + TILE_GAP) - TILE_GAP);
  return `min(100%, ${line}px)`;
}

/** 12:34, or 1:02:03 from an hour. */
export function clock(seconds: number): string {
  const whole = Math.max(0, Math.round(seconds));
  const h = Math.floor(whole / 3600);
  const m = Math.floor((whole % 3600) / 60);
  const s = String(whole % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
}

/** A number typed in a field, above zero, or null while it isn't one. */
export function positive(text: string): number | null {
  const n = Number(text.trim());
  return text.trim() && Number.isFinite(n) && n > 0 ? n : null;
}

/** "10–12%", or "at 50%" for a beat at one point of the story. */
export function placeOf(beat: Pick<BlockBeat, "at" | "point">): string {
  if (beat.at) return `${beat.at[0]}–${beat.at[1]}%`;
  return beat.point === undefined ? "" : `at ${beat.point}%`;
}

/** A sequence on the board: the thin box at the front of its shots. `weight` is its part of the
 * beat, so a beat split in two stays split in the same proportion when the duration changes. */
export interface SeqBox {
  /** the location's id in the series config; "" until one is chosen */
  place: string;
  /** the characters' ids, written to each of its shots' `who:` */
  cast: string[];
  weight: number;
}

export const BOX_W = 54;

/** What a beat starts as: one sequence, no place chosen yet. */
export function freshBoxes(): SeqBox[] {
  return [{ place: "", cast: [], weight: 1 }];
}

/** A beat's shots shared among its sequences by weight: at least one each while there are enough
 * to go round, the rest by largest remainder. A sequence the beat has no shot left for gets 0. */
export function boxShots(boxes: Pick<SeqBox, "weight">[], shots: number): number[] {
  const whole = boxes.reduce((n, b) => n + b.weight, 0);
  const ideal = boxes.map((b) => (b.weight / whole) * shots);
  const out = boxes.map(() => 0);
  let left = shots;
  for (let i = 0; i < boxes.length && left > 0; i++) {
    out[i] = 1;
    left -= 1;
  }
  // from here, whoever is furthest under its share (the earlier one on a tie)
  while (left > 0) {
    let best = 0;
    for (let i = 1; i < boxes.length; i++) if (ideal[i] - out[i] > ideal[best] - out[best]) best = i;
    out[best] += 1;
    left -= 1;
  }
  return out;
}

/** Sequence `i` split in two, the second keeping its place and cast. */
export function splitBox(boxes: SeqBox[], i: number): SeqBox[] {
  const half = { ...boxes[i], cast: [...boxes[i].cast], weight: boxes[i].weight / 2 };
  return [...boxes.slice(0, i), { ...boxes[i], weight: half.weight }, half, ...boxes.slice(i + 1)];
}

/** Sequence `i` gone, its share to the one before it (the next, for the first). The last one stays. */
export function removeBox(boxes: SeqBox[], i: number): SeqBox[] {
  if (boxes.length < 2) return boxes;
  const heir = i > 0 ? i - 1 : 1;
  return boxes.flatMap((b, k) => (k === i ? [] : k === heir ? [{ ...b, weight: b.weight + boxes[i].weight }] : [b]));
}

export interface SeriesChoices {
  places: string[];
  cast: { id: string; name: string }[];
}

/** The places and characters a series config offers. A prop or vehicle isn't cast: it's a shot's `with:`. */
export function seriesChoices(text: string): SeriesChoices {
  const raw = JSON.parse(text) as {
    locations?: Record<string, unknown>;
    subjects?: Record<string, { kind?: string; name?: string }>;
  };
  return {
    places: Object.keys(raw.locations ?? {}),
    cast: Object.entries(raw.subjects ?? {})
      .filter(([, s]) => s.kind !== "prop" && s.kind !== "vehicle")
      .map(([id, s]) => ({ id, name: s.name || id })),
  };
}
