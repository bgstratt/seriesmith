// The series config as an object to edit, for the forms (Series settings, the
// cast cards): read through GET /seriesmith/source, saved through PUT with the
// hash it was read at (a 409 when it changed on disk meanwhile), which checks
// it, keeps a history copy and rebuilds — as the Series config text window does.
// `keep` (one form only: Series settings) keeps its unsaved edits in this browser
// (lib/drafts): put back when it opens on the file they were made against,
// offered when the file has changed since.

import { useEffect, useMemo, useState } from "react";
import { afterAuthoredWrite } from "../actions";
import { api, host } from "../host";
import { clearDraft, readDraft, useDraft } from "../lib/drafts";
import { same, serialize, type Raw } from "../lib/seriesForm";
import { conflictOf } from "../lib/sourceSession";
import type { SourceCheck, SourceDoc } from "../types";

export interface SeriesConfig {
  doc: SourceDoc | null;
  /** as on disk */
  base: Raw | null;
  /** as edited */
  draft: Raw | null;
  setDraft: (f: (d: Raw) => Raw) => void;
  revert: () => void;
  dirty: boolean;
  error: string | null;
  conflict: boolean;
  saving: boolean;
  check: SourceCheck | null;
  reload: () => Promise<void>;
  /** save `next` (default: the draft); resolves true when written */
  save: (next?: Raw, what?: string) => Promise<boolean>;
  /** (keep) unsaved edits from before a reload: in the draft now, or (stale) made
   * against an older file and only offered */
  kept: { at: number; stale: boolean } | null;
  /** (keep) the stale kept edits into the draft, or dropped */
  putBack: () => void;
  dropKept: () => void;
  /** (keep) clear the kept edits and keep nothing more (closing unsaved) */
  forget: () => void;
}

interface KeptSeries {
  raw: Raw;
  hash: string;
}

export function useSeriesConfig(ep: string, keep = false): SeriesConfig {
  const [doc, setDoc] = useState<SourceDoc | null>(null);
  const [base, setBase] = useState<Raw | null>(null);
  const [draft, setDraftState] = useState<Raw | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [check, setCheck] = useState<SourceCheck | null>(null);
  const [saving, setSaving] = useState(false);
  const [conflict, setConflict] = useState(false);
  const draftKey = `series|${ep}`;
  const [kept, setKept] = useState<{ raw: Raw; at: number; stale: boolean } | null>(null);
  const dirty = !!draft && !!base && !same(draft, base);
  const forget = useDraft(draftKey, useMemo(() => ({ raw: draft, hash: doc?.hash ?? "" }), [draft, doc]), keep && dirty);

  async function reload(restore = false) {
    setError(null);
    setConflict(false);
    try {
      const d = await api().source(ep, "series");
      setDoc(d);
      try {
        const raw = JSON.parse(d.text) as Raw;
        const k = restore && keep ? readDraft<KeptSeries>(draftKey) : null;
        const back = k && !same(k.value.raw, raw) ? { raw: k.value.raw, at: k.at, stale: k.value.hash !== d.hash } : null;
        setKept(back);
        setBase(raw);
        setDraftState(back && !back.stale ? back.raw : raw);
      } catch (e) {
        setBase(null);
        setDraftState(null);
        setError(`series.json isn't valid JSON (${(e as Error).message}): fix it as text first.`);
      }
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    void reload(true);
  }, [ep]);

  async function save(next?: Raw, what = "Series settings"): Promise<boolean> {
    const raw = next ?? draft;
    if (!doc || !raw) return false;
    setSaving(true);
    setError(null);
    try {
      const text = serialize(raw, doc.text);
      const r = await api().putSource({ ep, file: "series", text, base_hash: doc.hash, rebuild: true });
      setCheck(r.check);
      setDoc({ ...doc, text, hash: r.hash });
      setBase(raw);
      setDraftState(raw);
      afterAuthoredWrite(r.build);
      if (r.check.errors.length) host().toast("warn", `${what} saved, with problems`, r.check.errors[0].message);
      else host().toast("success", `${what} saved`, "The episode was rebuilt.");
      return true;
    } catch (e) {
      if (conflictOf(e)) setConflict(true);
      else setError((e as Error).message);
      return false;
    } finally {
      setSaving(false);
    }
  }

  return {
    doc, base, draft, error, conflict, saving, check, reload: () => reload(), save,
    setDraft: (f) => setDraftState((d) => (d ? f(d) : d)),
    revert: () => setDraftState(base),
    dirty,
    kept: kept && { at: kept.at, stale: kept.stale },
    putBack: () => {
      if (kept) setDraftState(kept.raw);
      setKept(null);
    },
    dropKept: () => {
      clearDraft(draftKey);
      setKept(null);
    },
    forget,
  };
}
