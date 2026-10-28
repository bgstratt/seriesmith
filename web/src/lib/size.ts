// A take's render size: "WxH" as the server takes it (docs/API.md, `size`).
// A shot renders at its shotlist's size unless a take or its override asks for
// another: a good 1344x768 take in a 960x544 episode, mastered by its own size.

import type { TargetTemplate } from "../types";

/** The sizes offered besides the shot's own (H3's 32 grid; 1344x768 is its native size). */
export const SIZE_CHOICES = ["1344x768", "1024x576", "960x544"];

export function sizeText(w: number | null | undefined, h: number | null | undefined): string {
  return w && h ? `${w}x${h}` : "";
}

/** "1344x768" (or "1344×768"), trimmed, as the server wants it; Error otherwise. */
export function parseSize(text: string): string {
  const m = /^\s*(\d+)\s*[xX×]\s*(\d+)\s*$/.exec(text);
  if (!m) throw new Error(`Size must look like 1344x768, not "${text}".`);
  const w = Number(m[1]), h = Number(m[2]);
  if (w < 32 || h < 32 || w > 8192 || h > 8192) throw new Error(`Size ${w}x${h}: each side 32 to 8192.`);
  return `${w}x${h}`;
}

/** A target's size rules, from its template (GET /seriesmith/targets): the grid, and
 * whether a size off it is snapped (LTX, Wan) or refused (H3). */
export interface SizeRule {
  multiple: number;
  snap: boolean;
}

export function sizeRule(template: { size_multiple?: number; size_fit?: string } | null | undefined): SizeRule {
  return { multiple: Math.max(1, Number(template?.size_multiple) || 1), snap: template?.size_fit === "snap" };
}

/** The offered sizes that are legal as they are under `rule`, plus `extra` (a take's own). */
export function sizeChoices(rule: SizeRule = { multiple: 1, snap: false }, ...extra: string[]): string[] {
  const onGrid = SIZE_CHOICES.filter((s) => {
    const [w, h] = s.split("x").map(Number);
    return w % rule.multiple === 0 && h % rule.multiple === 0;
  });
  return [...onGrid, ...extra.filter((s) => s && !onGrid.includes(s))];
}

/** What's wrong with a typed size under `rule`: null when it's fine, an error
 * (not a size; off a grid the target refuses, naming the nearest legal sides),
 * or, for a target that snaps, a note saying what it becomes. */
export function sizeCheck(text: string, rule: SizeRule): { level: "err" | "info"; text: string } | null {
  if (!text.trim()) return null;
  let size: string;
  try {
    size = parseSize(text);
  } catch (e) {
    return { level: "err", text: (e as Error).message };
  }
  const [w, h] = size.split("x").map(Number);
  const m = rule.multiple;
  if (m <= 1 || (w % m === 0 && h % m === 0)) return null;
  if (rule.snap) return { level: "info", text: `snaps to ${Math.floor(w / m) * m}x${Math.floor(h / m) * m} (a multiple of ${m})` };
  const near = (v: number) => `${Math.floor(v / m) * m} or ${Math.ceil(v / m) * m}`;
  const bad = [w % m ? `width ${near(w)}` : "", h % m ? `height ${near(h)}` : ""].filter(Boolean).join(", ");
  return { level: "err", text: `Not a multiple of ${m}, which this target needs: ${bad}.` };
}

/** (width, height) as `template`'s model renders it (targets.Template.fit_size):
 * the nearest of its listed sizes, else rounded down to its grid and shrunk
 * under its maximum, keeping the shape. A model that refuses an off-grid size
 * is rounded the same way here, so what is written is a size it takes. */
export function fitSize(width: number, height: number, template: TargetTemplate | null | undefined): [number, number] {
  const sizes = template?.sizes ?? [];
  if (sizes.length) {
    const want = width / height;
    const key = ([w, h]: [number, number]) => [Math.round(Math.abs(Math.log(w / h / want)) * 1000), Math.abs(w * h - width * height)];
    return [...sizes].sort((a, b) => {
      const [x1, y1] = key(a), [x2, y2] = key(b);
      return x1 - x2 || y1 - y2;
    })[0];
  }
  const m = Math.max(1, Number(template?.size_multiple) || 1);
  let k = 1;
  const long = template?.max_size?.long_side;
  if (long && Math.max(width, height) > long) k = Math.min(k, long / Math.max(width, height));
  const pixels = template?.max_size?.pixels;
  if (pixels && width * height * k * k > pixels) k = Math.min(k, Math.sqrt(pixels / (width * height)));
  return [Math.max(m, Math.floor(Math.floor(width * k) / m) * m), Math.max(m, Math.floor(Math.floor(height * k) / m) * m)];
}

/** Simple mode's common sizes, to fill its width and height from. */
export const COMMON_SIZES: { label: string; width: number; height: number }[] = [
  { label: "1344×768 (H3's own)", width: 1344, height: 768 },
  { label: "854×480 (480p)", width: 854, height: 480 },
  { label: "1280×720 (720p)", width: 1280, height: 720 },
  { label: "1920×1080 (1080p)", width: 1920, height: 1080 },
  { label: "768×1344 (H3, vertical)", width: 768, height: 1344 },
  { label: "720×1280 (720p vertical)", width: 720, height: 1280 },
  { label: "1080×1920 (1080p vertical)", width: 1080, height: 1920 },
  { label: "1024×1024 (square)", width: 1024, height: 1024 },
];
