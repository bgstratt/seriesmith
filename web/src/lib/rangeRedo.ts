// Frames of a take made again (POST /seriesmith/render's redo_range, docs/API.md):
// the times asked in the dialog as the frames the server takes, and what's wrong
// with them.

/** The frame on screen at `seconds`. */
export function frameAt(seconds: number, fps: number): number {
  return Math.floor(seconds * fps + 1e-6);
}

/** The time a frame starts, as the dialog shows it. */
export function timeOf(frame: number, fps: number): string {
  return (frame / fps).toFixed(2);
}

export interface RangeAsked {
  first: number;
  last: number;
  /** what's wrong with it, or "" */
  problem: string;
}

/** Start and end, in seconds as typed, inside a take of `frames` frames. The end
 * frame is the one showing at the end time, so both ends are made again. */
export function rangeAsked(start: string, end: string, frames: number, fps: number): RangeAsked {
  const a = Number(start);
  const b = Number(end);
  if (start.trim() === "" || end.trim() === "" || !Number.isFinite(a) || !Number.isFinite(b)) {
    return { first: 0, last: 0, problem: "Type a start and an end, in seconds." };
  }
  const first = frameAt(a, fps);
  const last = Math.min(frameAt(b, fps), frames - 1);
  if (a < 0 || first >= frames) {
    return { first, last, problem: `The start has to be inside the take (0 to ${timeOf(frames - 1, fps)}s).` };
  }
  if (last < first) return { first, last, problem: "The end has to be after the start." };
  return { first, last, problem: "" };
}

/** How the range reads: "frames 74-123, 2.08 s". */
export function rangeText(first: number, last: number, fps: number): string {
  return `frames ${first}-${last}, ${((last - first + 1) / fps).toFixed(2)} s`;
}
