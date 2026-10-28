// Takes from outside (docs/API.md, "Takes from outside"): a take dragged from the
// gallery, or a video file, dropped on the timeline or a shot. Onto a clip, it
// becomes that shot's take; between two clips, a new shot in the script there
// (its lines copied from the take's shot, its length the take's), then the take
// copied into it. The pure parts: what a drag carries, where a drop lands, and
// the script with the new shot in it.

import { insertAfter, parseShot, shotIdBetween, writeShot } from "./shotForm";

/** The drag data type of a take (the gallery's tiles). */
export const TAKE_MIME = "application/x-seriesmith-take";

/** A take being dragged. */
export interface TakeDrag {
  ep: string;
  pass: "final" | "proxy";
  shot: string;
  take: number;
  /** its length, when known: a new shot's `dur:` */
  seconds?: number | null;
}

export function encodeTakeDrag(t: TakeDrag): string {
  return JSON.stringify(t);
}

export function decodeTakeDrag(text: string): TakeDrag | null {
  try {
    const t = JSON.parse(text) as TakeDrag;
    return t && typeof t.ep === "string" && typeof t.shot === "string" && Number.isInteger(t.take)
      && (t.pass === "final" || t.pass === "proxy") ? t : null;
  } catch {
    return null;
  }
}

/** Whether a drag carries a take (its data can't be read until the drop). */
export function dragHasTake(dt: DataTransfer | null): boolean {
  return !!dt && Array.from(dt.types ?? []).includes(TAKE_MIME);
}

/** The videos a take can be imported from (takeimport.VIDEO_EXTS). */
export const VIDEO_EXT = [".mp4", ".m4v", ".mov", ".webm", ".mkv", ".avi"];
/** POST /seriesmith/take/import's own upload limit. */
export const VIDEO_UPLOAD_LIMIT = 4 * 1024 * 1024 * 1024;

/** Why a file can't be a take ("" when it can). */
export function videoFileProblem(file: { name: string; size: number }): string {
  const ext = /\.[^.]+$/.exec(file.name)?.[0]?.toLowerCase() ?? "";
  if (!VIDEO_EXT.includes(ext)) return `${file.name} isn't a video (${VIDEO_EXT.join(", ")}).`;
  if (file.size > VIDEO_UPLOAD_LIMIT) return `${file.name} is over ${VIDEO_UPLOAD_LIMIT / 1024 ** 3} GB.`;
  return "";
}

/** Where a drop at `x` lands among clips with these [left, right] edges: onto
 * clip `index` (its middle), or `between` at insertion point `gap` (0..n, near
 * an edge or past either end). */
export type DropAt = { kind: "onto"; index: number } | { kind: "between"; gap: number; x: number };

export function dropAt(edges: { left: number; right: number }[], x: number): DropAt {
  for (let i = 0; i < edges.length; i++) {
    const e = edges[i];
    const edge = Math.min((e.right - e.left) * 0.25, 24);
    if (x > e.left + edge && x < e.right - edge) return { kind: "onto", index: i };
  }
  let gap = 0;
  let best = Infinity;
  for (let i = 0; i <= edges.length; i++) {
    const at = !edges.length ? x : i === 0 ? edges[0].left : i === edges.length ? edges[i - 1].right
      : (edges[i - 1].right + edges[i].left) / 2;
    if (Math.abs(x - at) < best) {
      best = Math.abs(x - at);
      gap = i;
    }
  }
  const at = !edges.length ? x : gap === 0 ? edges[0].left : gap === edges.length ? edges[gap - 1].right
    : (edges[gap - 1].right + edges[gap].left) / 2;
  return { kind: "between", gap, x: at };
}

/** The script shots either side of insertion point `gap` in a cut (orphans, not
 * in the script, skipped): the new shot goes after `after`, else before `before`. */
export function anchorAt(cut: { shot: string; orphan?: boolean }[], gap: number): { after: string } | { before: string } | null {
  for (let i = gap - 1; i >= 0; i--) if (!cut[i].orphan) return { after: cut[i].shot };
  for (let i = gap; i < cut.length; i++) if (!cut[i].orphan) return { before: cut[i].shot };
  return null;
}

/** Seconds as a `dur:` (one decimal at most). */
export function durOf(seconds: number): string {
  return String(Math.max(0.1, Math.round(seconds * 10) / 10));
}

/** Keys a copied shot doesn't keep: what ties it to its own neighbours. */
const NOT_COPIED = ["continuous", "first", "last", "overlap"];

/**
 * The script with a new shot inserted at `anchor`, its lines those of shot
 * `from` (less its continuity), its `dur:` `seconds`, and a comment saying where
 * it came from. Null when `from` or the anchor isn't in the script.
 */
export function insertedShot(text: string, spans: { id: string; line: number; end_line: number }[], from: string,
  anchor: { after: string } | { before: string }, seconds: number, note: string): { text: string; id: string } | null {
  const shots = [...spans].sort((a, b) => a.line - b.line);
  const src = shots.find((s) => s.id === from);
  const ids = shots.map((s) => s.id);
  const taken = new Set(ids);
  const lines = text.split("\n");
  if (!src) return null;
  const f = parseShot(lines.slice(src.line - 1, src.end_line));
  for (const k of NOT_COPIED) delete f.keys[k];
  f.keys.dur = durOf(seconds);
  f.comments = [...f.comments, `// ${note}`];
  let at: number;
  if ("after" in anchor) {
    const i = ids.indexOf(anchor.after);
    if (i < 0) return null;
    f.id = shotIdBetween(ids[i], ids[i + 1] ?? null, taken);
    at = shots[i].end_line;
  } else {
    const i = ids.indexOf(anchor.before);
    if (i < 0) return null;
    f.id = shotIdBetween(ids[i - 1] ?? null, ids[i], taken);
    at = shots[i].line - 1;
  }
  return { text: insertAfter(text, at, writeShot(f)), id: f.id };
}

/** Where the new shot goes in the cut: right after the drop's left neighbour,
 * else first (an insertion point in the cut as it is once the shot is in it). */
export function gapAfter(cut: { shot: string }[], left: string | null): number {
  if (!left) return 0;
  const i = cut.findIndex((e) => e.shot === left);
  return i < 0 ? cut.length : i + 1;
}
