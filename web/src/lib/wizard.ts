// The new episode wizard (docs/EDITOR.md, "New series, new episode"): where it
// goes, the series (a new one only), who and where it's about, and its first
// shot — then one POST /seriesmith/episode/new with the series config and the
// script it made. A next episode starts from its newest neighbour's config
// (GET /seriesmith/episode/new), so the cast, look and settings carry over and
// only what's new is added.

import { entryFor, getPath, idProblem, newSeries, slug, type CardKind, type Raw } from "./seriesForm";
import { writeShot, type ShotForm } from "./shotForm";

/** A cast entry the wizard adds: its kind, the id made from its name, and the
 * card's fields (name, design / description, voice, pronoun). */
export interface NewCast {
  kind: Extract<CardKind, "character" | "prop" | "vehicle" | "location">;
  id: string;
  fields: Raw;
}

/** The kinds the wizard's cast step offers, with what each is. */
export const WIZARD_KINDS: { kind: NewCast["kind"]; label: string; add: string }[] = [
  { kind: "character", label: "Character", add: "+ Character" },
  { kind: "location", label: "Location", add: "+ Location" },
  { kind: "prop", label: "Prop", add: "+ Prop" },
  { kind: "vehicle", label: "Vehicle", add: "+ Vehicle" },
];

/** A cast entry's id from its name ("the porch lantern" -> porch_lantern). */
export function castId(name: string): string {
  const s = slug(name.replace(/^(the|a|an)\s+/i, ""));
  return /^[a-z]/.test(s) ? s : s ? `x_${s}` : "";
}

/** Why the wizard's cast can't be saved as it is: per entry ("" when fine). */
export function castProblems(raw: Raw, cast: NewCast[]): string[] {
  return cast.map((c, i) => {
    const name = String(c.kind === "location" ? c.id : c.fields.name ?? "").trim();
    if (!name) return c.kind === "location" ? "Give the place a short name." : "Give it a name.";
    const p = idProblem(raw, c.id);
    if (p) return p;
    if (cast.slice(0, i).some((o) => o.id === c.id)) return `${c.id} is here twice.`;
    return "";
  });
}

/** The series config with the wizard's cast added (each by the card's rules:
 * its kind, its picture path by the show's layout). */
export function withCast(raw: Raw, cast: NewCast[], prefix: string): Raw {
  const out: Raw = { ...raw, subjects: { ...((raw.subjects ?? {}) as Raw) }, locations: { ...((raw.locations ?? {}) as Raw) } };
  for (const c of cast) {
    if (!c.id) continue;
    const block = c.kind === "location" ? "locations" : "subjects";
    (out[block] as Raw)[c.id] = entryFor(c.kind, undefined, c.fields, c.id, prefix);
  }
  return out;
}

/** A new series' config: its title and id, the starter's settings. */
export function seriesConfig(title: string): Raw {
  const raw = newSeries(title);
  (raw.series as Raw).title = title.trim() || "My Series";
  return raw;
}

/** The characters and places a config has (for the first shot's pickers). */
export function castOfConfig(raw: Raw): { characters: { id: string; name: string }[]; things: { id: string; name: string }[]; locations: string[] } {
  const subj = (getPath(raw, ["subjects"]) ?? {}) as Record<string, Raw>;
  const named = (id: string, e: Raw) => ({ id, name: typeof e?.name === "string" ? e.name : id });
  const kindOf = (e: Raw) => (typeof e?.kind === "string" ? e.kind : "character");
  return {
    characters: Object.entries(subj).filter(([, e]) => kindOf(e) === "character" && (e?.sheet || e?.of || e?.design)).map(([id, e]) => named(id, e)),
    things: Object.entries(subj).filter(([, e]) => kindOf(e) === "prop" || kindOf(e) === "vehicle").map(([id, e]) => named(id, e)),
    locations: Object.keys((getPath(raw, ["locations"]) ?? {}) as object),
  };
}

/** The new episode's script: its title line, the first sequence, the first shot. */
export function firstScript(name: string, title: string, seq: string, location: string, shot: ShotForm): string {
  const head = `= ${name}${title.trim() ? `  ${title.trim()}` : ""}`;
  return [head, "", `# ${seq || "sq01"}${location ? `  ${location}` : ""}`, "", ...writeShot(shot), ""].join("\n");
}

/** A show folder's name from the series title ("Porch Lights!" -> Porch_Lights). */
export function showFolder(title: string): string {
  return title.trim().replace(/[^A-Za-z0-9._-]+/g, "_").replace(/^[^A-Za-z0-9]+|[._-]+$/g, "").slice(0, 64);
}
