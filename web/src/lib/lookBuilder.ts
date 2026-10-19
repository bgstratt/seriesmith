// The look builder's line (seriesmith/presets/__init__.py compose_look, the same
// rule): the medium's clause, then the other rows' in order, all joined by
// semicolons; a drawn medium leaves the camera rows (camera, lens, film) out.

import type { LookBuilderRow } from "../types";

/** {row: option id}: the builder's picks (the series config's style.look_parts). */
export type LookParts = Record<string, string>;

export function composeLook(rows: LookBuilderRow[], parts: LookParts): string {
  const medium = rows.find((r) => r.id === "medium")?.options.find((o) => o.id === parts.medium);
  if (!medium) return "";
  const clauses = [medium.clause];
  for (const r of rows) {
    if (r.id === "medium" || (medium.drawn && r.camera_row)) continue;
    const o = r.options.find((x) => x.id === parts[r.id]);
    if (o) clauses.push(o.clause);
  }
  return clauses.join("; ");
}

/** The rows the builder shows under its medium: a drawn one folds the camera rows away. */
export function visibleRows(rows: LookBuilderRow[], parts: LookParts): LookBuilderRow[] {
  const medium = rows.find((r) => r.id === "medium")?.options.find((o) => o.id === parts.medium);
  return rows.filter((r) => !(medium?.drawn && r.camera_row));
}

/** `parts` with `row` set to `id`, or cleared when it already is (a second click). */
export function togglePart(parts: LookParts, row: string, id: string): LookParts {
  const next = { ...parts };
  if (next[row] === id) delete next[row];
  else next[row] = id;
  return next;
}
