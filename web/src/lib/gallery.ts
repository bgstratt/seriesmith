// The gallery: every picture of the episode's refs in one grid, a section per
// ref, and the order its viewer steps through with the arrow keys.

import type { Pass, Ref, RefTake } from "../types";
import { PANO_VIEW, REF_GROUPS, SHEET_VIEW, TOUR_VIEW, VIEWS, groupOf, hasViews, passesFilter, pickedOf, takesOf, type RefGroupId } from "./refs";

/** The Refs tab's groups that have pictures (a voice has none). */
export type GalleryGroup = Exclude<RefGroupId, "voices">;
export const GALLERY_GROUPS = REF_GROUPS.filter((g) => g.id !== "voices") as { id: GalleryGroup; label: string }[];

export interface GalleryScope {
  /** one group, or null for every group */
  group: GalleryGroup | null;
  /** one ref, or null; it wins over `group` */
  ref: string | null;
  picksOnly: boolean;
  /** every ref of the series, not just those this episode uses */
  series: boolean;
}

export interface GalleryItem {
  key: string;
  ref: Ref;
  /** the character view, SHEET_VIEW, PANO_VIEW, TOUR_VIEW, or null */
  view: string | null;
  take: RefTake;
  file: string;
  live: boolean;
}

export interface GallerySection {
  ref: Ref;
  items: GalleryItem[];
  /** candidates not shown: still on the way, or failed */
  queued: number;
  failed: number;
}

export function itemKey(ref: string, view: string | null, take: number): string {
  return `${ref}|${view ?? ""}|${take}`;
}

/** Where a ref keeps candidates: a character's four views and its sheets; a
 * location's plate, 360s and tour holds; anything else its own. */
export function galleryViews(r: Ref): (string | null)[] {
  if (hasViews(r)) return [...VIEWS.map((v) => v.view), SHEET_VIEW];
  if (r.kind === "location") return [null, PANO_VIEW, TOUR_VIEW];
  return [null];
}

/** Newest first: a character's four views come from one Generate, so by when
 * they were made, not by view; the take number where there's no time. */
function newestFirst(a: GalleryItem, b: GalleryItem): number {
  const ta = a.take.finished ?? a.take.queued ?? "";
  const tb = b.take.finished ?? b.take.queued ?? "";
  return tb.localeCompare(ta) || b.take.take - a.take.take;
}

export function gallerySections(refs: Ref[], scope: GalleryScope, pass: Pass): GallerySection[] {
  const shown = refs.filter((r) => {
    const g = groupOf(r);
    if (g === "voices") return false;
    if (scope.ref) return r.id === scope.ref;
    if (scope.group && g !== scope.group) return false;
    return passesFilter(r, scope.series ? "all" : "episode", pass);
  });
  const order = new Map(GALLERY_GROUPS.map((g, i) => [g.id as RefGroupId, i]));
  shown.sort((a, b) => (order.get(groupOf(a))! - order.get(groupOf(b))!)
    || a.name.localeCompare(b.name, undefined, { sensitivity: "base" }) || a.id.localeCompare(b.id));
  const out: GallerySection[] = [];
  for (const r of shown) {
    const items: GalleryItem[] = [];
    let queued = 0;
    let failed = 0;
    for (const view of galleryViews(r)) {
      const picked = view === PANO_VIEW || view === TOUR_VIEW ? null : pickedOf(r, view);
      for (const t of takesOf(r, view)) {
        if (t.status === "queued") queued++;
        else if (t.status === "failed") failed++;
        if (t.status !== "ok" || !t.image) continue;
        const live = picked === t.take;
        if (scope.picksOnly && !live) continue;
        items.push({ key: itemKey(r.id, view, t.take), ref: r, view, take: t, file: t.image, live });
      }
    }
    items.sort(newestFirst);
    if (items.length || queued || failed || scope.ref) out.push({ ref: r, items, queued, failed });
  }
  return out;
}

/** The key the gallery opens a ref on: its live picture, else its newest. */
export function liveKey(sections: GallerySection[], ref: string): string | null {
  const items = sections.find((s) => s.ref.id === ref)?.items ?? [];
  return (items.find((i) => i.live) ?? items[0])?.key ?? null;
}

/** A picture's shape (width / height), for a tile that fits it with no bars:
 * its own size where the record has it, else what its kind usually is. */
export function itemAspect(it: Pick<GalleryItem, "ref" | "view" | "take">): number {
  const { width: w, height: h } = it.take;
  if (w && h) return w / h;
  if (it.view === SHEET_VIEW) return 4;
  if (it.view === PANO_VIEW) return 2;
  return it.ref.kind === "location" || groupOf(it.ref) === "keyframes" ? 16 / 9 : 1;
}
