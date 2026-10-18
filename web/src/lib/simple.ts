// Simple mode (docs/PLAN.md, step 12): a clip is one sequence of one shot in
// the Clips project (seriesmith/clips.py) -- `# cl007  <place>` / `## c007` --
// written from a few fields. A clip with no place picked gets a place of its
// own, described in words (or by the prompt): words only (it renders at once,
// imagined its own way), or with a plate made before it renders, so the place
// looks the same in every clip that uses it (POST /seriesmith/clip/queue).

import type { TargetTemplate } from "../types";
import { picturePath, type Raw } from "./seriesForm";
import { writeShot, type DialogueLine } from "./shotForm";
import { fitSize } from "./size";

/** What each video model is good at, in a line, for the model picker. */
export const MODEL_NOTES: Record<string, string> = {
  minimax_h3_ref2va: "Keeps your characters and places looking like their pictures, and lip-syncs what they say.",
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
  /** a picture, not a video: its first keyframe is what's made (on an image model) */
  still?: boolean;
}

/** What each image model is good at, in a line (a picture clip's picker). */
export const IMAGE_NOTES: Record<string, string> = {
  krea2: "Natural-looking pictures from words, quickly. The default.",
  z_image_turbo: "Very fast pictures from words.",
  flux2_klein: "Detailed pictures from words.",
  krea_2_router: "Krea 2, hosted through Comfy Router (a paid run each picture).",
  flux2_klein_edit: "Draws your people and places into the scene from their pictures.",
  flux_kontext: "Works from one reference picture.",
  qwen_image_21: "From words, or with your people's and places' pictures.",
  flux3_klein: "FLUX.3: from words, or with up to ten of your pictures.",
  flux3_klein_turbo: "FLUX.3, faster: from words, or with up to ten of your pictures.",
  qwen_rapid_aio: "Quick, from up to three of your pictures.",
  minimax_h3_still: "A frame as H3 would render it, from your pictures.",
};

/** The image models a picture clip can use (not the 360 outpaint). */
export function pictureModel(mode: string | undefined): boolean {
  return mode !== "pano";
}

/** The place a clip without one gets: an id of its own, described in words;
 * with `picture`, a plate (where the show keeps plates) to be made first. */
export function placeFor(shot: string, spec: ClipSpec, prefix: string, picture = false): { id: string; entry: Raw } {
  const id = `${shot}_place`;
  const description = (spec.placeText.trim() || spec.prompt.trim()).replace(/\s+/g, " ");
  return { id, entry: picture ? { description, plate: picturePath("location", id, prefix)! } : { description } };
}

/** The clip's lines: its sequence header, then its shot. */
export function clipBlock(seq: string, shot: string, location: string, spec: ClipSpec, seriesTarget: string): string[] {
  return [`# ${seq}  ${location}`, "", ...shotLines(shot, spec, seriesTarget)];
}

/** One shot of a clip: a picture's says `first: generate` (its keyframe is the
 * picture) and is marked so; a video's names its model when it isn't the series'. */
export function shotLines(shot: string, spec: ClipSpec, seriesTarget: string): string[] {
  const keys: Record<string, string> = { size: spec.size, dur: spec.dur };
  if (spec.who.length) keys.who = spec.who.join(", ");
  if (spec.still) keys.first = "generate";
  else if (spec.target && spec.target !== seriesTarget) keys.target = spec.target;
  return writeShot({ id: shot, keys, action: spec.prompt.trim(), dialogue: spec.still ? [] : spec.dialogue,
                     comments: spec.still ? ["// a picture"] : [], other: [] });
}

/** Several shots as one clip: one sequence, its shots `c007a`, `c007b`, ...
 * in order, cut together. */
export function shotsBlock(seq: string, shot: string, location: string, specs: ClipSpec[], seriesTarget: string): { ids: string[]; lines: string[] } {
  const ids = specs.map((_, i) => `${shot}${String.fromCharCode(97 + i)}`);
  const lines = [`# ${seq}  ${location}`];
  specs.forEach((s, i) => lines.push("", ...shotLines(ids[i], s, seriesTarget)));
  return { ids, lines };
}

/** The script with a clip added at its end. */
export function withClip(script: string, block: string[]): string {
  const body = script.replace(/\s+$/, "");
  return `${body}\n\n${block.join("\n")}\n`;
}

/** A typed length as `template`'s model renders it (targets.Template.snap):
 * rounded UP onto its frame grid, at least its shortest, and capped at its
 * longest (`capped`: the length typed was past it). null when the text isn't
 * a length in seconds. */
export function snapLength(text: string, template: TargetTemplate | null | undefined, seriesFps = 24):
    { seconds: number; frames: number; capped: boolean } | null {
  const s = Number(String(text).trim());
  if (!String(text).trim() || !Number.isFinite(s) || s <= 0) return null;
  const fps = typeof template?.fps === "number" ? template.fps : seriesFps;
  const step = Math.max(1, template?.frames?.step ?? 1), base = Math.max(1, template?.frames?.base ?? 1);
  const max = template?.frames?.max ?? Number.MAX_SAFE_INTEGER;
  const want = Math.max(1, Math.round(s * fps));
  let frames = want <= base ? base : step * Math.ceil((want - base) / step) + base;
  let capped = false;
  if (frames > max) {
    frames = base + Math.floor((max - base) / step) * step;
    capped = true;
  }
  return { seconds: Math.round((frames / fps) * 100) / 100, frames, capped };
}

/** What a script's `dur:` should say for a typed length: as typed, or the
 * model's longest when it's past that (the build refuses a longer one). */
export function durFor(text: string, template: TargetTemplate | null | undefined, seriesFps = 24): string {
  const t = String(text).trim();
  const snap = snapLength(t, template, seriesFps);
  return snap?.capped ? String(snap.seconds) : t;
}

/** A clip's own size ("WxH", as its model renders it) when the typed width and
 * height differ from the project's saved size once both are fitted (to the
 * project's model, then the clip's); null when it renders at the project's, or
 * the boxes don't hold a size. Saved as the clip's size override. */
export function clipOwnSize(w: string, h: string, project: [number, number],
                            seriesTemplate: TargetTemplate | null | undefined,
                            template: TargetTemplate | null | undefined): string | null {
  const nw = Math.round(Number(w)), nh = Math.round(Number(h));
  if (!(nw >= 64 && nh >= 64 && nw <= 8192 && nh <= 8192)) return null;
  const [rw, rh] = fitSize(...fitSize(nw, nh, seriesTemplate ?? undefined), template ?? undefined);
  const [pw, ph] = project;
  const [dw, dh] = pw && ph ? fitSize(...fitSize(pw, ph, seriesTemplate ?? undefined), template ?? undefined) : [0, 0];
  return rw === dw && rh === dh ? null : `${rw}x${rh}`;
}
