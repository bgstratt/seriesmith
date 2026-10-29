// A shot's colour in the cut, previewed (src/lib/color.ts): one SVG filter per
// clip with a colour (or the one whose sliders are being dragged), which a
// <video> or a thumbnail uses as its CSS `filter` (colorFilterCss). The same
// matrix assemble applies, so the preview is what the export will be.
import { useMemo } from "react";
import { colorFilterCss, colorFilterId, feColorMatrixValues, hasColor, type ShotColor } from "../lib/color";
import { statusKey, useApp } from "../store";

/** Each clip's colour in the current pass's cut, the one being dragged over its saved one. */
export function useClipColors(): Record<string, ShotColor> {
  const st = useApp((s) => (s.ep ? s.status[statusKey(s.ep, s.pass)] : undefined));
  const preview = useApp((s) => s.colorPreview);
  return useMemo(() => {
    const out: Record<string, ShotColor> = {};
    for (const s of st?.shots ?? []) if (hasColor(s.cut?.color)) out[s.shot] = s.cut.color!;
    if (preview) {
      if (hasColor(preview.color)) out[preview.shot] = preview.color;
      else delete out[preview.shot];
    }
    return out;
  }, [st, preview]);
}

/** The CSS filter for `shot`'s clip under `prefix`'s defs (undefined: as shot). */
export function useClipFilter(shot: string | null | undefined, prefix: string): string | undefined {
  const colors = useClipColors();
  return shot ? colorFilterCss(shot, colors[shot], prefix) : undefined;
}

/** The filters themselves, once per surface that uses them (`prefix` keeps their ids apart). */
export function ColorDefs({ prefix }: { prefix: string }) {
  const colors = useClipColors();
  const shots = Object.keys(colors);
  if (!shots.length) return null;
  return (
    <svg width={0} height={0} style={{ position: "absolute" }} aria-hidden>
      <defs>
        {shots.map((shot) => (
          <filter key={shot} id={colorFilterId(shot, prefix)} colorInterpolationFilters="sRGB">
            <feColorMatrix type="matrix" values={feColorMatrixValues(colors[shot])} />
          </filter>
        ))}
      </defs>
    </svg>
  );
}
