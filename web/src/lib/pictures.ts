// A cast entry's picture, for the pickers and lists that name it: a
// character's face (the last panel of its four-panel sheet: three-quarter,
// side, back, face — a whole body won't read at the size of a chip), a
// group's, a one-picture character's or a prop's whole picture, a location's
// plate. The path is the Refs list's when it's loaded (it knows a variant's
// derived sheet, whether the file is there, and its hash to refresh by), else
// the series config's own.

import type { Ref } from "../types";
import { getPath, type Raw } from "./seriesForm";

export interface Picture {
  /** relative to the episode, as the series config names it */
  path: string;
  /** show only the sheet's last quarter (the face panel) */
  face: boolean;
  /** changes when the file does (its sha1), so a new pick shows */
  version: string | null;
}

/** The picture of subject or location `id` (null: none named, or none on disk). */
export function pictureOf(raw: Raw | null, refs: Ref[] | null | undefined, block: "subjects" | "locations", id: string): Picture | null {
  const e = (getPath(raw ?? {}, [block, id]) ?? {}) as Raw;
  const ref = refs?.find((r) => r.id === `${block === "locations" ? "location" : "subject"}:${id}`);
  if (ref && (!ref.path || !ref.exists)) return null;
  const path = ref?.path ?? (typeof e[block === "locations" ? "plate" : "sheet"] === "string" ? (e[block === "locations" ? "plate" : "sheet"] as string) : null);
  if (!path) return null;
  if (block === "locations") return { path, face: false, version: ref?.sha1 ?? null };
  const kind = typeof e.kind === "string" ? e.kind : ref?.kind ?? "character";
  const base = typeof e.of === "string" ? ((getPath(raw ?? {}, ["subjects", e.of]) ?? {}) as Raw) : {};
  const panels = e.sheet_panels ?? base.sheet_panels;
  const face = kind === "character" && typeof e.members !== "number" && Number(panels ?? 4) !== 1;
  return { path, face, version: ref?.sha1 ?? null };
}

/** One or two letters for an entry without a picture yet ("Nell Moran" -> NM). */
export function initials(name: string): string {
  const words = name.replace(/^(the|a|an)\s+/i, "").split(/[\s_]+/).filter(Boolean);
  return (words.length > 1 ? words[0][0] + words[1][0] : (words[0] ?? "?").slice(0, 2)).toUpperCase();
}
