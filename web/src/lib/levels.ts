// Play all's levelling (docs/LEVELLING.md): the lines brought to one level the way the export's
// mix brings them (mix.level_dialogue), read from the server (POST /seriesmith/levels), which
// measures each clip's sound once and caches it. Play all can't play a clip's own sound louder
// than its file (a <video>'s volume stops at 1), so it only turns down: every clip is moved by
// its gain less the biggest boost, which keeps the lines' balance the export's, a little
// quieter overall.

import type { MixResult } from "../types";
import type { PlayEntry } from "./mix";
import { voicePlays } from "./mix";
import type { PlayItem } from "./playlist";

/** One clip's sound as the server measures it: the file Play all plays for its lines and the
 * seconds of that file the cut plays (`to` null: to its end). */
export interface LevelClip {
  shot: string;
  path: string;
  from: number;
  to: number | null;
}

export interface DialogueLevels {
  /** the request these answer (levelRequestKey), so a changed cut asks again */
  key: string;
  /** the pass's mix.json level.limit_db (0: levelling off) */
  limit: number;
  /** each speaking clip's change, dB, as the export makes it */
  gains: Record<string, number>;
}

/** The sound each clip of `items` plays for its lines under the mix: its own audio source (a
 * dub, a replaced sound), its voice stem (voices only), nothing (voices only on a shot with no
 * lines), else the take's own sound; as the files and spans Play all plays them. */
export function levelClips(items: PlayItem[], res: Pick<MixResult, "mix" | "voices"> | undefined): LevelClip[] {
  const out: LevelClip[] = [];
  const voices = new Map((res?.voices?.shots ?? []).map((v) => [v.shot, v]));
  for (const it of items) {
    if (!it.mp4 || !(it.dur > 0)) continue;
    const s = it.source;
    if (s) {
      // as sourcePlan places it: from `start`, moved by `offset`, cut at the clip's end
      if (!s.path) continue;
      const head = Math.max(0, s.offset);
      if (head >= it.dur) continue;
      const from = s.start + Math.max(0, -s.offset);
      out.push({ shot: it.shot, path: s.path, from, to: from + (it.dur - head) });
      continue;
    }
    const v = voices.get(it.shot);
    const plays = v ? voicePlays(res?.mix, v) : "whole";
    if (plays === "silence") continue;
    if (plays === "voice" && v?.path && v.take === it.take) {
      out.push({ shot: it.shot, path: v.path, from: it.inT, to: it.outT });
      continue;
    }
    out.push({ shot: it.shot, path: it.mp4, from: it.inT, to: it.outT });
  }
  return out;
}

/** What a levels answer is for: the clips and the limit (a change of either asks again). */
export function levelRequestKey(clips: LevelClip[], limit: number): string {
  return JSON.stringify([limit, clips.map((c) => [c.shot, c.path, Math.round(c.from * 100), c.to == null ? null : Math.round(c.to * 100)])]);
}

/** Each clip's change in Play all, dB: its gain less the biggest boost, so nothing goes over
 * its file's own level (a clip the export doesn't move is moved by the same shift, keeping the
 * balance). {} when levelling is off. */
export function playAllDb(lv: DialogueLevels | undefined, shots: string[]): Record<string, number> {
  if (!lv || !(lv.limit > 0)) return {};
  const gains = Object.values(lv.gains);
  if (!gains.length) return {};
  const shift = Math.max(0, ...gains);
  const out: Record<string, number> = {};
  for (const s of shots) out[s] = (lv.gains[s] ?? 0) - shift;
  return out;
}

/** dB as a linear gain. */
export function dbGain(db: number | undefined): number {
  return db ? 10 ** (db / 20) : 1;
}

/** Play entries (voice stems, clips' own audio sources) with their clip's levelling applied. */
export function levelled(entries: PlayEntry[], db: Record<string, number>): PlayEntry[] {
  if (!Object.keys(db).length) return entries;
  return entries.map((e) => {
    const shot = e.id.replace(/^(voice|source):/, "");
    const g = dbGain(db[shot]);
    return g === 1 ? e : { ...e, gain: e.gain * g };
  });
}
