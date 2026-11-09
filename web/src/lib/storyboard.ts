// The storyboard's shapes and sums: GET /seriesmith/storyboard/block (core/blocking.py) and
// GET /seriesmith/storyboard (core/board.py: the script against a structure's targets).

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

export interface BoardShot {
  id: string;
  who: string[];
  target: string | null;
  seconds: number | null;
  action: string;
  /** a stand-in nobody has worked on yet */
  held_empty: boolean;
  /** its first frame, when it has one of its own */
  picture?: string | null;
  /** still holding the gray card it was made with: it renders, gray */
  card?: boolean;
  picture_version?: string | null;
  block: number;
}

export interface BoardRun {
  sequence: string;
  place: string;
  /** false: it carries on a sequence begun in an earlier beat */
  opens: boolean;
  block: number | null;
  shots: BoardShot[];
}

export interface BoardBeat {
  beat: string | null;
  /** the name as a script writes it; null: shots before any beat */
  plain: string | null;
  /** which time this name comes in the script */
  nth: number;
  /** its line in the script; null until it has one */
  block: number | null;
  known: boolean;
  in_script: boolean;
  guidance: string;
  shots: number;
  seconds: number;
  target_shots: number | null;
  target_seconds: number | null;
  thin: boolean;
  at?: [number, number];
  point?: number;
  runs: BoardRun[];
}

export interface BoardAct {
  act: string;
  own: boolean;
  shots: number;
  target_shots: number;
  beats: BoardBeat[];
}

export interface BoardPlan {
  id: string;
  title: string;
  structure: string | null;
  structure_known: boolean;
  /** the length the script says it's aiming at, in seconds */
  duration: number | null;
  shots: number;
  seconds: number;
  untimed: number;
  target_shots: number | null;
  shot_seconds: number | null;
  warnings: string[];
  acts: BoardAct[];
}

export interface StoryboardAnswer {
  plan: BoardPlan;
  hash: string;
  made?: string[];
}

export type StoryboardEdit =
  | { op: "add"; beat: { plain: string; nth: number }; place?: string }
  | { op: "fill"; beats: { plain: string; nth: number }[]; each?: number }
  | { op: "place"; block: number; place: string }
  | { op: "cast"; block: number; who: string[] }
  | { op: "structure"; name: string }
  | { op: "rename_beat"; block: number; name: string }
  | { op: "add_after"; block: number; before?: boolean }
  | { op: "move_shot"; block: number; target: number; after: boolean }
  | { op: "delete_shot"; block: number }
  | { op: "convert"; shots: string[]; target: string | null }
  | { op: "add_sequence"; block: number; place: string }
  | { op: "add_beat"; beat: { plain: string; nth: number }; name: string; act?: string }
  | { op: "remove_beat"; block: number }
  | { op: "lay_out"; name: string }
  | { op: "rename_act"; block: number; name: string }
  | { op: "remove_act"; block: number };

/** Steps of undo a window keeps: each is the whole script, so not without limit. */
export const UNDO_STEPS = 50;

/** `stack` with `item` on top, the oldest falling off past UNDO_STEPS. */
export function pushed<T>(stack: T[], item: T): T[] {
  return [...stack, item].slice(-UNDO_STEPS);
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
export function placeOf(beat: Pick<BoardBeat, "at" | "point">): string {
  if (beat.at) return `${beat.at[0]}–${beat.at[1]}%`;
  return beat.point === undefined ? "" : `at ${beat.point}%`;
}

/** "3 of 93 shots, about 5:25 to go" and its kin. */
export function meter(beat: Pick<BoardBeat, "shots" | "target_shots" | "target_seconds" | "seconds">): string {
  if (beat.target_shots === null || beat.target_seconds === null) return `${beat.shots} ${beat.shots === 1 ? "shot" : "shots"}`;
  const left = beat.target_seconds - beat.seconds;
  const rest = left >= 1 ? `, about ${clock(left)} to go` : "";
  return `${beat.shots} of ${beat.target_shots} shots${rest}`;
}

/** How many stand-ins Fill would make on these beats. */
export function fillCount(beats: Pick<BoardBeat, "shots" | "target_shots" | "plain">[]): number {
  return beats.reduce((n, b) => n + (b.plain === null ? 0 : Math.max(0, (b.target_shots ?? 0) - b.shots)), 0);
}

/** The beats Fill has something to do on, as the edit names them. */
export function fillable(beats: BoardBeat[]): { plain: string; nth: number }[] {
  return beats.flatMap((b) => (b.plain !== null && (b.target_shots ?? 0) > b.shots ? [{ plain: b.plain, nth: b.nth }] : []));
}

/** The beats with no shot at all, as the edit names them: one held shot each is the episode blocked in. */
export function bareBeats(beats: BoardBeat[]): { plain: string; nth: number }[] {
  return beats.flatMap((b) => (b.plain !== null && b.shots === 0 ? [{ plain: b.plain, nth: b.nth }] : []));
}

/** The tiles' widths; each is 16:9. */
export const TILE_SIZES = { s: 72, m: 108, l: 162 } as const;
export type TileSize = keyof typeof TILE_SIZES;
export const TILE_GAP = 3;
export const RUN_MIN_W = 96;

/** A sequence's width on the board: its shots in a line under its bar, wrapping past the row. */
export function runWidth(shots: number): string {
  return `min(100%, max(${RUN_MIN_W}px, calc(${shots} * (var(--sb-tile) + ${TILE_GAP}px) - ${TILE_GAP}px)))`;
}

/** A remembered tile size, or S for anything else. */
export function tileSize(saved: string | null): TileSize {
  return saved === "s" || saved === "m" || saved === "l" ? saved : "s";
}

/** A beat's share of the width: the biggest target fills the row, and no band is too narrow to read. */
export function bandShare(target: number | null, biggest: number): string {
  if (!target || biggest <= 0) return "100%";
  return `max(220px, ${Math.round((target / biggest) * 100)}%)`;
}

/** The episode's length so far in minutes, as the Minutes field writes it: untimed shots as typical ones. */
export function runtimeMinutes(seconds: number, untimed: number, typical: number): string {
  return String(Math.max(0.1, Math.round(((seconds + untimed * typical) / 60) * 10) / 10));
}

/** The pictures in a drop, in filename order (frame2 before frame10). */
export function picturesInOrder<T extends { name: string; type: string }>(files: T[]): T[] {
  return files.filter((f) => f.type.startsWith("image/"))
    .sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: "base" }));
}

/** Which shots a drop lands on: a tile always takes it, as its first frame, as a timeline clip does;
 * a sequence or a beat fills its empty stand-ins and leaves the rest alone. */
export function dropTargets<T extends Pick<BoardShot, "held_empty">>(shots: T[], single: boolean): T[] {
  return single ? shots : shots.filter((s) => s.held_empty);
}

/** The held shots that can render and have no up-to-date take: the animatic's to-do. */
export function heldToRender<T extends Pick<BoardShot, "id" | "target" | "picture" | "card">>(shots: T[], fresh: Set<string>): string[] {
  return shots.filter((s) => s.target === "hold" && (s.picture || s.card) && !fresh.has(s.id)).map((s) => s.id);
}

/** The ids of the held shots among these: what Convert would change. */
export function heldIds(shots: Pick<BoardShot, "id" | "target">[]): string[] {
  return shots.filter((s) => s.target === "hold").map((s) => s.id);
}

/** The shots without an up-to-date take: what Generate does for a sequence, a beat or an act. */
export function toGenerate(shots: Pick<BoardShot, "id">[], fresh: Set<string>): string[] {
  return shots.filter((s) => !fresh.has(s.id)).map((s) => s.id);
}

export type DropSide = "before" | "after";

/** Where on a tile a drop lands. A shot being moved goes to the nearer side. A file on the middle
 * of a tile is that tile's picture (null), and only near an edge goes between shots. */
export function dropSide(fraction: number, moving: boolean): DropSide | null {
  if (moving) return fraction < 0.5 ? "before" : "after";
  if (fraction < 0.25) return "before";
  return fraction > 0.75 ? "after" : null;
}

/** The shot a moved or new one ends up right after, in the script: null at the very start. */
export function shotBefore(order: string[], target: string, side: DropSide, moved?: string): string | null {
  const list = order.filter((id) => id !== moved);
  const at = list.indexOf(target);
  if (at < 0) return null;
  return side === "after" ? target : (list[at - 1] ?? null);
}

export interface SeriesChoices {
  places: string[];
  cast: { id: string; name: string }[];
}

/** The places and characters a series config offers. A prop or vehicle isn't cast: it's a shot's `with:`. */
export function seriesChoices(text: string): SeriesChoices {
  const raw = JSON.parse(text) as {
    locations?: Record<string, unknown>;
    subjects?: Record<string, { kind?: string; name?: string } | string>;
  };
  return {
    places: Object.keys(raw.locations ?? {}).filter((k) => !k.startsWith("_")),
    cast: Object.entries(raw.subjects ?? {}).flatMap(([id, s]) =>
      typeof s === "object" && s.kind !== "prop" && s.kind !== "vehicle" ? [{ id, name: s.name || id }] : []),
  };
}
