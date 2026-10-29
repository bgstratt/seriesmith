// A clip's fades and dissolves on the timeline (the cut entry's fade_in / fade_out /
// dissolve; src/lib/playlist.ts lays them as the export does): thin curves over its
// picture, each as long as it lasts. A fade in rises from the clip's bottom-left
// corner (black) to full, a fade out falls to its bottom-right; a dissolve is an X
// across the join, each clip drawing its half (the one going out falls through the
// middle as the one coming in rises through it).
//
// Each has a handle at its inner end, dragged to set its length (to nothing takes it
// off); a clip with no fade has one in each top corner, shown on hover, to drag one
// out. While one is dragged the curves follow it (`drag`); the timeline saves it on
// release (Timeline's onJoinDown).
import type { PointerEvent as RPointerEvent } from "react";
import { framesLabel, type JoinKey } from "../lib/cutEdit";
import type { PlayItem } from "../lib/playlist";

/** A fade or dissolve being dragged: the shot whose entry has it, and its frames now. */
export interface JoinDrag {
  shot: string;
  key: JoinKey;
  frames: number;
}

/** What a handle hands the timeline: whose entry, which field, its frames now, and how
 * the pointer's travel maps to frames (`per`: frames for a second of drag, signed). */
export interface JoinGrab {
  shot: string;
  key: JoinKey;
  frames: number;
  per: number;
  max: number;
}

const HANDLE = 4;                                    // its radius, px

export function JoinCurves({ it, next, width, height, fps, locked, drag, onDown }: {
  it: PlayItem;
  /** the clip after it (its dissolve is drawn half on this clip) */
  next?: string;
  width: number;
  height: number;
  fps: number;
  locked?: boolean;
  drag?: JoinDrag | null;
  onDown?: (e: RPointerEvent<SVGElement>, grab: JoinGrab) => void;
}) {
  if (!(it.dur > 0)) return null;
  const sec = (k: JoinKey, shot: string, now: number) =>
    drag && drag.shot === shot && drag.key === k ? drag.frames / fps : now;
  const fadeIn = sec("fade_in", it.shot, it.fadeIn);
  const fadeOut = sec("fade_out", it.shot, it.fadeOut);
  const dissolveIn = sec("dissolve", it.shot, it.dissolveIn);
  const dissolveOut = next ? sec("dissolve", next, it.dissolveOut) : it.dissolveOut;
  const px = width / it.dur;                         // the clip's own scale: px a second
  const editable = !locked && !!onDown && !!it.mp4;
  if (!(fadeIn || fadeOut || dissolveIn || dissolveOut) && !editable) return null;
  const h = height - 2;
  const top = 1;
  const bottom = 1 + h;
  const mid = 1 + h / 2;
  const paths: { d: string; title: string }[] = [];
  const handles: { x: number; title: string; grab: JoinGrab; corner?: boolean }[] = [];
  const label = (s: number) => framesLabel(Math.round(s * fps), fps);
  const frames = (s: number) => Math.round(s * fps);
  // a fade can't be longer than the clip; a dissolve's half no longer than this clip
  const own = Math.max(1, Math.round(it.dur * fps));
  if (fadeIn) {
    const w = Math.min(width, fadeIn * px);
    const t = `fade in from black, ${label(fadeIn)}`;
    paths.push({ d: `M0,${bottom} Q${w * 0.3},${top + h * 0.15} ${w},${top}`, title: t });
    handles.push({ x: w, title: `${t}: drag to change, to the clip's start to take it off`, grab: { shot: it.shot, key: "fade_in", frames: frames(fadeIn), per: fps, max: own } });
  } else if (!dissolveIn) {
    handles.push({ x: HANDLE + 6, corner: true, title: "Drag right: a fade in from black", grab: { shot: it.shot, key: "fade_in", frames: 0, per: fps, max: own } });
  }
  if (fadeOut) {
    const w = Math.min(width, fadeOut * px);
    const t = `fade out to black, ${label(fadeOut)}`;
    paths.push({ d: `M${width - w},${top} Q${width - w * 0.3},${top + h * 0.15} ${width},${bottom}`, title: t });
    handles.push({ x: width - w, title: `${t}: drag to change, to the clip's end to take it off`, grab: { shot: it.shot, key: "fade_out", frames: frames(fadeOut), per: -fps, max: own } });
  } else if (!dissolveOut) {
    handles.push({ x: width - HANDLE - 6, corner: true, title: "Drag left: a fade out to black", grab: { shot: it.shot, key: "fade_out", frames: 0, per: -fps, max: own } });
  }
  if (dissolveIn) {
    // the half after the join: the clip before falls from the middle to nothing, this rises to full
    const w = Math.min(width, (dissolveIn / 2) * px);
    const t = `dissolve from the clip before, ${label(dissolveIn)}`;
    paths.push({ d: `M0,${mid} Q${w * 0.5},${mid - h * 0.3} ${w},${top}`, title: t });
    paths.push({ d: `M0,${mid} Q${w * 0.5},${mid + h * 0.3} ${w},${bottom}`, title: t });
    // each side's half: a second of drag is two of dissolve
    handles.push({ x: w, title: `${t}: drag to change, to the join to take it off`, grab: { shot: it.shot, key: "dissolve", frames: frames(dissolveIn), per: 2 * fps, max: 2 * own } });
  }
  if (dissolveOut) {
    // the half before it: this falls from full to the middle, the clip after rises to it
    const w = Math.min(width, (dissolveOut / 2) * px);
    const t = `dissolve into the clip after, ${label(dissolveOut)}`;
    paths.push({ d: `M${width - w},${top} Q${width - w * 0.5},${mid - h * 0.3} ${width},${mid}`, title: t });
    paths.push({ d: `M${width - w},${bottom} Q${width - w * 0.5},${mid + h * 0.3} ${width},${mid}`, title: t });
    if (next) handles.push({ x: width - w, title: `${t}: drag to change, to the join to take it off`, grab: { shot: next, key: "dissolve", frames: frames(dissolveOut), per: -2 * fps, max: 2 * own } });
  }
  return (
    <svg className="h3-join-curves" width={width} height={height} aria-hidden>
      {paths.map((p, i) => (
        <path key={i} d={p.d}><title>{p.title}</title></path>
      ))}
      {editable && handles.map((hd) => {
        const active = drag && drag.shot === hd.grab.shot && drag.key === hd.grab.key;
        return (
          <circle key={`${hd.grab.shot}:${hd.grab.key}`} className={`h3-join-handle${hd.corner && !active ? " h3-join-corner" : ""}${active ? " h3-join-active" : ""}`}
            cx={Math.max(HANDLE, Math.min(width - HANDLE, hd.x))} cy={top + HANDLE + 1} r={HANDLE}
            onPointerDown={(e) => onDown!(e, { ...hd.grab, per: hd.grab.per / px })}
            onClick={(e) => e.stopPropagation()}>
            <title>{hd.title}</title>
          </circle>
        );
      })}
    </svg>
  );
}
