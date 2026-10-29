// A shot's colour in the cut (seriesmith/color.py, the same numbers): exposure,
// contrast, black point, saturation, warmth and tint, six sliders at 0, kept on the cut entry
// and applied by assemble. Here: the ranges, the check, and the matrix as an
// SVG feColorMatrix, so the viewer and the timeline preview what the export
// will be.

export type ColorField = "exposure" | "contrast" | "black" | "saturation" | "warmth" | "tint";
export type ShotColor = Partial<Record<ColorField, number>>;

export const COLOR_RANGES: Record<ColorField, [number, number]> = {
  exposure: [-2, 2], contrast: [-1, 1], black: [-0.25, 0.25], saturation: [-1, 1], warmth: [-1, 1], tint: [-1, 1],
};
export const COLOR_FIELDS = Object.keys(COLOR_RANGES) as ColorField[];
const LUMA = [0.2126, 0.7152, 0.0722];
const SHIFT = 0.15;

/** The non-zero fields, rounded to 3 places and clamped to their ranges. */
export function cleanColor(c: ShotColor | null | undefined): ShotColor {
  const out: ShotColor = {};
  for (const k of COLOR_FIELDS) {
    const v = c?.[k];
    if (typeof v !== "number" || !Number.isFinite(v)) continue;
    const [lo, hi] = COLOR_RANGES[k];
    const r = Math.round(Math.min(hi, Math.max(lo, v)) * 1000) / 1000;
    if (r) out[k] = r;
  }
  return out;
}

export function hasColor(c: ShotColor | null | undefined): boolean {
  return Object.keys(cleanColor(c)).length > 0;
}

export function sameColor(a: ShotColor | null | undefined, b: ShotColor | null | undefined): boolean {
  const x = cleanColor(a);
  const y = cleanColor(b);
  return COLOR_FIELDS.every((k) => (x[k] ?? 0) === (y[k] ?? 0));
}

/** The CSS `filter` previewing `c` (the SVG filter colorDefs defines for `shot`), or undefined as shot. */
export function colorFilterCss(shot: string, c: ShotColor | null | undefined, prefix = "sm"): string | undefined {
  return hasColor(c) ? `url(#${colorFilterId(shot, prefix)})` : undefined;
}

export function colorFilterId(shot: string, prefix = "sm"): string {
  return `${prefix}-color-${shot.replace(/[^A-Za-z0-9_-]/g, "_")}`;
}

/** out = m . rgb + offset (rgb 0..1): color.py's matrix(). */
export function colorMatrix(c: ShotColor): { m: number[][]; offset: number[] } {
  const k = cleanColor(c);
  const s = 1 + (k.saturation ?? 0);
  const sat = [0, 1, 2].map((i) => [0, 1, 2].map((j) => (1 - s) * LUMA[j] + (i === j ? s : 0)));
  const w = k.warmth ?? 0;
  const t = k.tint ?? 0;
  const gain = 2 ** (k.exposure ?? 0);
  const gains = [gain * (1 + SHIFT * w), gain * (1 - SHIFT * t), gain * (1 - SHIFT * w)];
  const ctr = 2 ** (k.contrast ?? 0);
  const b = k.black ?? 0;
  const o = (1 - b) * 0.5 * (1 - ctr) + b;
  return { m: [0, 1, 2].map((i) => [0, 1, 2].map((j) => (1 - b) * ctr * gains[i] * sat[i][j])), offset: [o, o, o] };
}

/** The feColorMatrix `values` (20 numbers: four rows of r g b a offset). */
export function feColorMatrixValues(c: ShotColor): string {
  const { m, offset } = colorMatrix(c);
  const rows = [0, 1, 2].map((i) => [...m[i], 0, offset[i]]);
  rows.push([0, 0, 0, 1, 0]);
  return rows.flat().map((v) => +v.toFixed(6)).join(" ");
}
