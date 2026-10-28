// Unsaved edits kept in this browser (localStorage), so a reload, a closed tab or
// a refresh that remounts a form doesn't lose them. One draft per form and what
// it edits (a shot's override on a pass, a ref's view, the script). A form reads
// its draft when it opens, writes it half a second after each change and at once
// when the page goes, and clears it when it's clean again (saved, discarded).
// Drafts no form has opened for a month are dropped.

import { useEffect, useRef } from "react";

const PREFIX = "seriesmith.draft.";
const MAX_AGE = 30 * 24 * 3600 * 1000;
export const DRAFT_DELAY = 500;

export interface Draft<T> {
  value: T;
  /** when it was last written (ms) */
  at: number;
}

export function readDraft<T>(key: string): Draft<T> | null {
  try {
    const d = JSON.parse(localStorage.getItem(PREFIX + key) ?? "null") as Draft<T> | null;
    return d && typeof d.at === "number" && d.value != null ? d : null;
  } catch {
    return null;
  }
}

export function writeDraft(key: string, value: unknown, at = Date.now()) {
  try {
    localStorage.setItem(PREFIX + key, JSON.stringify({ value, at }));
  } catch {
    /* not kept: storage off or full */
  }
}

export function clearDraft(key: string) {
  try {
    localStorage.removeItem(PREFIX + key);
  } catch {
    /* nothing to clear */
  }
}

/** Drop drafts older than a month. */
export function pruneDrafts(now = Date.now()) {
  try {
    const old: string[] = [];
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (!k?.startsWith(PREFIX)) continue;
      const d = readDraft(k.slice(PREFIX.length));
      if (!d || now - d.at > MAX_AGE) old.push(k);
    }
    old.forEach((k) => localStorage.removeItem(k));
  } catch {
    /* storage off */
  }
}

/** "14:32" today, else "Oct 27, 14:32". */
export function keptAt(at: number, now = Date.now()): string {
  const d = new Date(at);
  const time = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return new Date(now).toDateString() === d.toDateString() ? time : `${d.toLocaleDateString([], { month: "short", day: "numeric" })}, ${time}`;
}

/**
 * Keep `value` as `key`'s draft while `dirty`; clear it when not. Returns
 * forget(): clear it now and keep nothing more (closing a form without saving).
 */
export function useDraft<T>(key: string, value: T, dirty: boolean): () => void {
  const now = useRef({ key, value, dirty, gone: false });
  now.current = { ...now.current, key, value, dirty };
  const keep = () => {
    const c = now.current;
    if (c.gone) return;
    if (c.dirty) writeDraft(c.key, c.value);
    else clearDraft(c.key);
  };
  useEffect(() => {
    const t = setTimeout(keep, DRAFT_DELAY);
    return () => clearTimeout(t);
  }, [key, value, dirty]);
  useEffect(() => {
    window.addEventListener("pagehide", keep);
    return () => {
      window.removeEventListener("pagehide", keep);
      keep();
    };
  }, []);
  return () => {
    now.current.gone = true;
    clearDraft(now.current.key);
  };
}

pruneDrafts();
