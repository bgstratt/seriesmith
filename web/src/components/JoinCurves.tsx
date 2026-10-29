// A clip's fades and dissolves on the timeline (the cut entry's fade_in / fade_out /
// dissolve; src/lib/playlist.ts lays them as the export does): thin curves over its
// picture, each as long as it lasts. A fade in rises from the clip's bottom-left
// corner (black) to full, a fade out falls to its bottom-right; a dissolve is an X
// across the join, each clip drawing its half (the one going out falls through the
// middle as the one coming in rises through it).
import { framesLabel } from "../lib/cutEdit";
import type { PlayItem } from "../lib/playlist";

export function JoinCurves({ it, width, height, fps }: { it: PlayItem; width: number; height: number; fps: number }) {
  if (!(it.fadeIn || it.fadeOut || it.dissolveIn || it.dissolveOut) || !(it.dur > 0)) return null;
  const px = width / it.dur;                         // the clip's own scale: px a second
  const h = height - 2;
  const top = 1;
  const bottom = 1 + h;
  const mid = 1 + h / 2;
  const paths: { d: string; title: string }[] = [];
  const label = (s: number) => framesLabel(Math.round(s * fps), fps);
  if (it.fadeIn) {
    const w = Math.min(width, it.fadeIn * px);
    paths.push({ d: `M0,${bottom} Q${w * 0.3},${top + h * 0.15} ${w},${top}`, title: `fade in from black, ${label(it.fadeIn)}` });
  }
  if (it.fadeOut) {
    const w = Math.min(width, it.fadeOut * px);
    paths.push({ d: `M${width - w},${top} Q${width - w * 0.3},${top + h * 0.15} ${width},${bottom}`, title: `fade out to black, ${label(it.fadeOut)}` });
  }
  if (it.dissolveIn) {
    // the half after the join: the clip before falls from the middle to nothing, this rises to full
    const w = Math.min(width, (it.dissolveIn / 2) * px);
    const t = `dissolve from the clip before, ${label(it.dissolveIn)}`;
    paths.push({ d: `M0,${mid} Q${w * 0.5},${mid - h * 0.3} ${w},${top}`, title: t });
    paths.push({ d: `M0,${mid} Q${w * 0.5},${mid + h * 0.3} ${w},${bottom}`, title: t });
  }
  if (it.dissolveOut) {
    // the half before it: this falls from full to the middle, the clip after rises to it
    const w = Math.min(width, (it.dissolveOut / 2) * px);
    const t = `dissolve into the clip after, ${label(it.dissolveOut)}`;
    paths.push({ d: `M${width - w},${top} Q${width - w * 0.5},${mid - h * 0.3} ${width},${mid}`, title: t });
    paths.push({ d: `M${width - w},${bottom} Q${width - w * 0.5},${mid + h * 0.3} ${width},${mid}`, title: t });
  }
  return (
    <svg className="h3-join-curves" width={width} height={height} aria-hidden>
      {paths.map((p, i) => (
        <path key={i} d={p.d}><title>{p.title}</title></path>
      ))}
    </svg>
  );
}
