// Several shots selected at once (a row, a tile or a clip clicked with Ctrl/⌘ or
// Shift), to queue them together. `shot` stays the one the inspector shows;
// `multi` is the whole selection in the cut's order, empty when it's one shot.

export interface Selection {
  shot: string | null;
  multi: string[];
  /** where a Shift-click's range starts: the last plain or Ctrl click */
  anchor: string | null;
}

export interface Mods {
  ctrlKey?: boolean;
  metaKey?: boolean;
  shiftKey?: boolean;
}

/** The selection after a click on `clicked`; `order`: the shots in the cut's order. */
export function clickSelection(cur: Selection, clicked: string, order: string[], mods: Mods): Selection {
  const inOrder = (ids: Set<string>) => order.filter((x) => ids.has(x));
  if (mods.shiftKey) {
    const from = cur.anchor ?? cur.shot;
    const a = from == null ? -1 : order.indexOf(from);
    const b = order.indexOf(clicked);
    if (a >= 0 && b >= 0) {
      const range = order.slice(Math.min(a, b), Math.max(a, b) + 1);
      return { shot: clicked, multi: range.length > 1 ? range : [], anchor: from };
    }
  }
  if (mods.ctrlKey || mods.metaKey) {
    const was = new Set(cur.multi.length ? cur.multi : cur.shot ? [cur.shot] : []);
    if (was.has(clicked)) {
      was.delete(clicked);
      const left = inOrder(was);
      const shot = cur.shot === clicked ? left[0] ?? null : cur.shot;
      return { shot, multi: left.length > 1 ? left : [], anchor: clicked };
    }
    was.add(clicked);
    const all = inOrder(was);
    return { shot: clicked, multi: all.length > 1 ? all : [], anchor: clicked };
  }
  return { shot: clicked, multi: [], anchor: clicked };
}

/** The shots a selection covers: all of `multi`, else the one shot. */
export function selectedShots(sel: Selection): string[] {
  return sel.multi.length ? sel.multi : sel.shot ? [sel.shot] : [];
}
