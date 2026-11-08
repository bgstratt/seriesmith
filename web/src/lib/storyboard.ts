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

/** A beat's width on the board: its tiles in one line, wrapping when that's wider than the row. */
export function beatWidth(shots: number): string {
  const line = Math.max(BEAT_MIN_W, shots * (TILE_W + TILE_GAP) - TILE_GAP);
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
