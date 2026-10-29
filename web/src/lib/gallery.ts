// The gallery: every picture of the episode's refs, or every take of its shots,
// in one grid (a section per ref or shot), and the order its viewer steps
// through with the arrow keys.

import type { EpisodeStatus, OwnerTake, Pass, Ref, RefTake, ShotStatus, TakeSummary } from "../types";
import { PANO_VIEW, REF_GROUPS, SHEET_VIEW, TOUR_VIEW, VIEWS, groupOf, hasViews, passesFilter, pickedOf, takesOf, type RefGroupId } from "./refs";

/** The Refs tab's groups that have pictures (a voice has none). */
export type GalleryGroup = Exclude<RefGroupId, "voices">;
export const GALLERY_GROUPS = REF_GROUPS.filter((g) => g.id !== "voices") as { id: GalleryGroup; label: string }[];

export type GalleryKind = "refs" | "shots";

export interface GalleryScope {
  kind: GalleryKind;
  /** refs: one group, or null for every group */
  group: GalleryGroup | null;
  /** one ref, or null; it wins over `group` */
  ref: string | null;
  /** shots: one sequence, or null for all */
  seq: string | null;
  /** shots: one shot, or null; it wins over `seq` */
  shot: string | null;
  /** only what's in use: a ref's live picture, a shot's cut take */
  picksOnly: boolean;
  /** refs: the series config's refs this episode's shots don't use, too */
  series: boolean;
}

export interface GalleryItem {
  key: string;
  ref: Ref;
  /** the character view, SHEET_VIEW, PANO_VIEW, TOUR_VIEW, or null */
  view: string | null;
  take: RefTake;
  file: string;
  /** the picture this episode's renders read */
  live: boolean;
  /** another episode's candidate for a shared ref (read-only here); absent: this episode's */
  episode?: string;
  /** the live file itself, with no candidate behind it (put there outside the editor:
   * by hand, or brought in with the series); nothing to pick, nothing it was made with */
  outside?: boolean;
}

export interface GallerySection {
  ref: Ref;
  items: GalleryItem[];
  /** candidates not shown: still on the way, or failed */
  queued: number;
  failed: number;
  /** a shared ref whose other episodes' candidates haven't been asked for yet */
  unread: boolean;
}

export function itemKey(ref: string, view: string | null, take: number, episode?: string): string {
  return `${ref}|${view ?? ""}|${take}${episode ? `|${episode}` : ""}`;
}

/** The other episodes' candidates of the shared refs read so far, by ref id. */
export type SharedTakes = ReadonlyMap<string, OwnerTake[]>;

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

/** The ref's live file as an item: shown when no candidate is live, so a picture put
 * there outside the editor can still be seen. */
export function liveFileItem(r: Ref): GalleryItem {
  const view = hasViews(r) ? SHEET_VIEW : null;
  const [width, height] = r.size ?? [];
  const take: RefTake = { take: 0, view, status: "ok", seed: null, image: r.path, source: "imported", note: "", width, height };
  return { key: `${r.id}|live`, ref: r, view, take, file: r.path!, live: true, outside: true };
}

/** A ref other episodes share (`shared_with`): its candidates there are asked for as it comes into view. */
export function isShared(r: Pick<Ref, "shared_with">): boolean {
  return !!r.shared_with?.length;
}

/**
 * A section per ref: this episode's candidates newest first, then (a shared
 * ref, once `shared` has them) the other episodes', by episode, newest first.
 * Another episode's pick is live only when it wrote the file this one reads.
 */
export function gallerySections(refs: Ref[], scope: GalleryScope, pass: Pass, shared: SharedTakes = new Map()): GallerySection[] {
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
    const theirs = shared.get(r.id);
    const unread = isShared(r) && !theirs;
    if (theirs) {
      const others: GalleryItem[] = [];
      for (const t of theirs) {
        if (t.status !== "ok" || !t.image) continue;
        const live = t.picked && t.episode === r.live_owner;
        if (scope.picksOnly && !live) continue;
        const view = t.view ?? null;
        others.push({ key: itemKey(r.id, view, t.take, t.episode), ref: r, view, take: t, file: t.image, live, episode: t.episode });
      }
      others.sort((a, b) => a.episode!.localeCompare(b.episode!, undefined, { numeric: true }) || newestFirst(a, b));
      items.push(...others);
    }
    // nothing here is the file renders read (it was put there outside the editor):
    // show it first; a sibling's pick not read yet shows once it is
    if (r.exists && r.path && !items.some((i) => i.live) && !(unread && r.live_owner)) items.unshift(liveFileItem(r));
    if (items.length || queued || failed || unread || scope.ref) out.push({ ref: r, items, queued, failed, unread });
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

// ---------------------------------------------------------------------------
// shots: every finished take, a section per shot
// ---------------------------------------------------------------------------

export interface ShotItem {
  key: string;
  shot: ShotStatus;
  take: TakeSummary;
  /** the take is the one the cut uses */
  cut: boolean;
}

export interface ShotSection {
  shot: ShotStatus;
  /** the sequence it belongs to, as the Shots tab heads it */
  seq: string;
  items: ShotItem[];
  queued: number;
  failed: number;
}

export function shotKey(shot: string, take: number): string {
  return `${shot}|${take}`;
}

export function seqOf(s: Pick<ShotStatus, "sequence" | "orphan">): string {
  return s.sequence ?? (s.orphan ? "orphans" : "—");
}

/** The episode's sequences, in script order. */
export function sequencesOf(st: EpisodeStatus | undefined): string[] {
  return [...new Set((st?.shots ?? []).map(seqOf))];
}

/** A shot's takes that have a picture to show, newest first; the cut's
 * badged. In script order, as the Shots tab lists them. */
export function shotSections(st: EpisodeStatus | undefined, scope: GalleryScope, pass: Pass): ShotSection[] {
  const out: ShotSection[] = [];
  for (const s of st?.shots ?? []) {
    if (scope.shot ? s.shot !== scope.shot : scope.seq != null && seqOf(s) !== scope.seq) continue;
    let queued = 0;
    let failed = 0;
    const items: ShotItem[] = [];
    for (const t of s.takes) {
      if (t.status === "queued") queued++;
      else if (t.status === "failed") failed++;
      if (t.status !== "ok" || !t.mp4 || !t.thumb) continue;
      const cut = s.cut.pass === pass && s.cut.take === t.take;
      if (scope.picksOnly && !cut) continue;
      items.push({ key: shotKey(s.shot, t.take), shot: s, take: t, cut });
    }
    items.sort((a, b) => b.take.take - a.take.take);
    if (items.length || queued || failed || scope.shot) out.push({ shot: s, seq: seqOf(s), items, queued, failed });
  }
  return out;
}

/** The key the gallery opens a shot on: its cut take, else its newest. */
export function cutKey(sections: ShotSection[], shot: string): string | null {
  const items = sections.find((s) => s.shot.shot === shot)?.items ?? [];
  return (items.find((i) => i.cut) ?? items[0])?.key ?? null;
}

/** A take's shape: its own size, else the episode's. */
export function takeAspect(t: Pick<TakeSummary, "width" | "height">, fallback: number): number {
  return t.width && t.height ? t.width / t.height : fallback;
}
