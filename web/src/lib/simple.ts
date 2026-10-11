// Simple mode (docs/PLAN.md, step 12): a clip is one sequence of one shot in
// the Clips project (seriesmith/clips.py) -- `# cl007  <place>` / `## c007` --
// written from a few fields. A clip with no place picked gets a place of its
// own, described in words (or by the prompt), whose plate is made before it
// renders (POST /seriesmith/clip/queue).

import { picturePath, type Raw } from "./seriesForm";
import { writeShot, type DialogueLine } from "./shotForm";

/** What each video model is good at, in a line, for the model picker. */
export const MODEL_NOTES: Record<string, string> = {
  minimax_h3_ref2va: "Keeps your characters and places looking like their pictures, and lip-syncs what they say. The default.",
  minimax_h3_fl2va: "H3 between a first and a last frame you give it.",
  ltx2: "Quick, and makes its own sound; can start from a picture.",
  ltx2_ingredients: "LTX-2 that takes your characters and places as pictures to work from.",
  wan22_i2v: "Brings one picture to life, with very good motion (slower).",
  wan22_ti2v: "Wan 5B: quick, from words or a first picture.",
  wan22_vace: "Wan with control: reference pictures and keyframes.",
  seedance_2_5: "ByteDance's Seedance, hosted through Comfy Router (a paid run each take).",
};

/** The next clip's ids, after the clips already in the script. */
export function nextClipIds(script: string): { seq: string; shot: string; n: number } {
  let n = 0;
  for (const m of script.matchAll(/^#\s+cl(\d+)\b/gm)) n = Math.max(n, Number(m[1]));
  n += 1;
  const id = String(n).padStart(3, "0");
  return { seq: `cl${id}`, shot: `c${id}`, n };
}

export interface ClipSpec {
  prompt: string;
  who: string[];
  /** a location id, or "" for a place of the clip's own */
  where: string;
  /** that place, in words (empty: the prompt is the place) */
  placeText: string;
  size: string;
  dur: string;
  /** the clip's model ("" or the series' own: none written) */
  target: string;
  dialogue: DialogueLine[];
}

/** The place a clip without one gets: an id of its own, described in words,
 * its plate where the show keeps plates. */
export function placeFor(shot: string, spec: ClipSpec, prefix: string): { id: string; entry: Raw } {
  const id = `${shot}_place`;
  const description = (spec.placeText.trim() || spec.prompt.trim()).replace(/\s+/g, " ");
  return { id, entry: { description, plate: picturePath("location", id, prefix)! } };
}

/** The clip's lines: its sequence header, then its shot. */
export function clipBlock(seq: string, shot: string, location: string, spec: ClipSpec, seriesTarget: string): string[] {
  const keys: Record<string, string> = { size: spec.size, dur: spec.dur };
  if (spec.who.length) keys.who = spec.who.join(", ");
  if (spec.target && spec.target !== seriesTarget) keys.target = spec.target;
  const lines = writeShot({ id: shot, keys, action: spec.prompt.trim(), dialogue: spec.dialogue, comments: [], other: [] });
  return [`# ${seq}  ${location}`, "", ...lines];
}

/** The script with a clip added at its end. */
export function withClip(script: string, block: string[]): string {
  const body = script.replace(/\s+$/, "");
  return `${body}\n\n${block.join("\n")}\n`;
}
