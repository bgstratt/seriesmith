// What Export (and Titles, the XML, Master) would find wrong with the cut, from the status
// the page already has, before ffmpeg starts: shots with no take (assemble skips
// them; Titles fails on them), trims that leave nothing, takes shorter than their
// dialogue window on the recording, and other-pass takes standing in.

import type { EpisodeStatus, Pass, TakeRef } from "../types";
import { cutTake, sameEp } from "./format";
import { fpsOf, trimWindow } from "./playlist";

/** What was asked for: Export, Titles or the XML timeline, from the takes or from
 * their upscales (2x). */
export interface ExportRun {
  kind: "export" | "titles" | "xml";
  upscaled: boolean;
}

/** Each run's name, as its menu item and the dialog before it say it. */
export const EXPORT_NAMES: Record<ExportRun["kind"], string> = { export: "Export", titles: "Titles", xml: "XML" };

export type ExportProblemKind = "missing" | "short" | "placeholder";

export interface ExportProblem {
  shot: string;
  kind: ExportProblemKind;
  text: string;
}

/** Each shot of the cut that won't export as it should. `queued`: the takes on
 * their way (rendering or queued), so a missing shot can say one is coming. */
export function exportCheck(st: EpisodeStatus | undefined, ep: string, pass: Pass, queued: TakeRef[] = []): ExportProblem[] {
  const out: ExportProblem[] = [];
  const coming = new Set(queued.filter((q) => sameEp(q.ep, ep) && q.pass === pass).map((q) => q.shot));
  const fps = st?.fps || 24;
  for (const s of st?.shots ?? []) {
    if (s.orphan || s.cut.out) continue;
    if (s.cut.placeholder) {
      out.push({ shot: s.shot, kind: "placeholder", text: `its ${s.cut.pass} take stands in` });
      continue;
    }
    const t = cutTake(s);
    if (!s.cut.usable || !t || t.status !== "ok" || !t.has_video) {
      const failed = t && t.status === "failed";
      out.push({
        shot: s.shot, kind: "missing",
        text: (failed ? "its take in the cut failed" : "no take") + (coming.has(s.shot) ? " (one is rendering or queued)" : ""),
      });
      continue;
    }
    const frames = t.frames ?? s.cut.frames;
    if (frames == null || !(frames > 0)) continue;
    const w = trimWindow(frames, s.cut.trim_in, s.cut.trim_out, fps, fpsOf(s, fps, t));
    if (!w) {
      out.push({ shot: s.shot, kind: "missing", text: "its trims leave nothing of the take" });
      continue;
    }
    if (s.audio_in != null && s.audio_out != null) {
      const need = s.audio_out - s.audio_in;
      const has = frames / fpsOf(s, fps, t);
      if (has + 0.5 / fps < need) {
        out.push({ shot: s.shot, kind: "short", text: `the take is ${has.toFixed(1)} s, its dialogue on the recording ${need.toFixed(1)} s` });
      }
    }
  }
  return out;
}

/** Titles assembles the whole cut and fails on a shot that's missing. */
export function blocks(run: ExportRun, problems: ExportProblem[]): boolean {
  return run.kind === "titles" && problems.some((p) => p.kind === "missing");
}

/** "sh040, sh110 and 3 more" */
export function shotList(problems: ExportProblem[], most = 8): string {
  const ids = problems.map((p) => p.shot);
  return ids.length > most ? `${ids.slice(0, most).join(", ")} and ${ids.length - most} more` : ids.join(", ");
}
