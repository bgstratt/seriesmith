// The master's titles as Play all shows them (docs/TITLES_GUIDE.md): the episode's title fading
// on the intro and outro as publish.titled draws it, and ffmpeg's colours as CSS.

import type { TitlesInfo } from "../types";

/** How visible the episode's title is `t` seconds into the intro or outro: the intro fades it in
 * over `intro_in` and keeps it; the outro fades it in over `outro_in` and out over `outro_out`. */
export function titleAlpha(kind: "intro" | "outro", sub: TitlesInfo["subtitle"], t: number): number {
  const ramp = (a: number, b: number) => (t <= a ? 0 : t >= b ? 1 : (t - a) / Math.max(1e-6, b - a));
  if (kind === "intro") return ramp(sub.intro_in[0], sub.intro_in[1]);
  return Math.min(ramp(sub.outro_in[0], sub.outro_in[1]), 1 - ramp(sub.outro_out[0], sub.outro_out[1]));
}

/** "#FFB45A@0.8" (ffmpeg's colour@alpha) as CSS; anything else as it is. */
export function cssColor(c: string): string {
  const [hex, a] = c.split("@");
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a ? Number(a) : 1})`;
}
