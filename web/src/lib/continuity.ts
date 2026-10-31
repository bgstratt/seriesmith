// A continuous shot (docs/CONTINUOUS.md) in words: how it carries on from the
// shot before it in the cut, and which model does it (ShotStatus.continuous).

import type { ShotContinuous, ShotStatus, TargetList } from "../types";
import type { Badge } from "./format";
import { targetLabel } from "./targets";

const MODE_LABEL: Record<string, string> = {
  latent: "latent",
  first: "first frame",
  multishot: "multishot",
};

/** The shot's frame rate, from its length and seconds (24 when it has neither). */
function fpsOf(s: ShotStatus): number {
  return s.length && s.seconds ? s.length / s.seconds : 24;
}

/** How a `continuous: first` shot opens on the frame, by the model it renders on. */
function firstHow(target: string | null | undefined): string {
  const id = target ?? "";
  if (/fl2va/.test(id)) return "a first/last-frame model: it opens on that frame and draws the rest from words, without the character or place pictures";
  if (id === "minimax_h3_ref2va" || id.startsWith("h3_singularity")) return "the frame anchored at the start of the render, its character and place pictures kept";
  return "the frame as its first keyframe";
}

/** One line: how the shot continues and on what (null: it doesn't). */
export function continuityText(s: ShotStatus, list: TargetList | null | undefined): string | null {
  const c = s.continuous;
  if (!c) return null;
  const on = targetLabel(list, s.target);
  const from = c.from ?? "the shot before it";
  if (!c.from) return `continuous: ${c.mode}, but it's the first shot in the cut: there's no shot before it to carry on from`;
  switch (c.mode) {
    case "latent": {
      const held = c.hold ? `its last ${c.hold} frames (${(c.hold / fpsOf(s)).toFixed(1)} s)` : "its last frames";
      return `Carries on from ${from} by latent on ${on}: ${held}, picture and sound, are held at the head of the render and it goes on from them; the held frames are cut off again, so the take starts where ${from}'s ended.`;
    }
    case "first":
      return `Opens on ${from}'s last frame, cut when the render starts, on ${on}: ${firstHow(s.target)}.`;
    case "multishot":
      return `Rendered in one generation with ${from} on ${on}: one take for the group.`;
    default:
      return `Continues ${from} (${c.mode}).`;
  }
}

/** The badge a continuous shot wears (null: it doesn't continue). */
export function continuityBadge(s: ShotStatus): Badge | null {
  const c: ShotContinuous | undefined = s.continuous;
  if (!c) return null;
  const mode = MODE_LABEL[c.mode] ?? c.mode;
  return {
    kind: "continuous",
    label: c.from ? `${mode} ← ${c.from}` : `${mode} (first in cut)`,
    title: continuityText(s, null) ?? "",
  };
}
