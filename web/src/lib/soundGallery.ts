// The gallery's Sound tab: the episode's sound takes (GET /seriesmith/sound/gallery) narrowed
// to a kind, one section, the ones in use, and the search box's words.

import type { SoundItem, SoundKind, SoundSection } from "../types";
import { tn } from "./format";

/** The Sound tab's chips, in order (Voices is a voice's samples and the lines both). */
export const SOUND_CHIPS: { id: SoundChip; label: string }[] = [
  { id: "voices", label: "Voices" },
  { id: "music", label: "Music" },
  { id: "ambience", label: "Ambience" },
  { id: "effects", label: "Effects" },
];
export type SoundChip = Exclude<SoundKind, "lines">;

/** Which chip a kind is under. */
export function chipOf(kind: SoundKind): SoundChip {
  return kind === "lines" ? "voices" : kind;
}

/** What a kind's take in use is called on its badge. */
export function useLabel(kind: SoundKind): string {
  return kind === "music" || kind === "effects" ? "in the mix" : "picked";
}

/** The words a take can be found by: its section's name, id, note and kind, the take (t03),
 * its model, a theme, a line's words and voice, "mix" / "picked" for the one in use. */
function words(s: SoundSection, it: SoundItem): string {
  return [s.name, s.id, s.note, s.kind, chipOf(s.kind), tn(it.take), it.model ?? "", it.theme ? `theme ${it.theme}` : "",
    it.text ?? "", it.who ?? "", it.use ? useLabel(s.kind) : ""].join(" ").toLowerCase();
}

/** The sections shown: a kind's (`sound`) or one (`section`, which wins), only the takes in use
 * with `useOnly`, only the takes that have every word typed; a section left with none is
 * dropped unless it has takes on the way or failed (and no words are typed). */
export function soundSections(all: SoundSection[], scope: { sound?: SoundKind | null; section?: string | null; picksOnly?: boolean; query?: string }): SoundSection[] {
  const q = (scope.query ?? "").toLowerCase().split(/\s+/).filter(Boolean);
  const out: SoundSection[] = [];
  for (const s of all) {
    if (scope.section ? s.id !== scope.section : scope.sound ? chipOf(s.kind) !== scope.sound : false) continue;
    const items = s.items.filter((it) => (!scope.picksOnly || it.use) && q.every((w) => words(s, it).includes(w)));
    if (items.length || (!q.length && !scope.picksOnly && (s.queued || s.failed))) out.push({ ...s, items });
  }
  return out;
}

/** "0:07" / "1:04" for a take's length; "" when it isn't known. */
export function clock(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return "";
  const s = Math.round(seconds);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** The section's take in use, if it has one (what Compare plays against). */
export function inUse(s: SoundSection | undefined): SoundItem | undefined {
  return s?.items.find((i) => i.use);
}
