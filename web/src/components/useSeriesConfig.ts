// The series config as an object to edit, for the forms (Series settings, the
// cast cards): read through GET /seriesmith/source, saved through PUT with the
// hash it was read at (a 409 when it changed on disk meanwhile), which checks
// it, keeps a history copy and rebuilds — as the Series config text window does.

import { useEffect, useState } from "react";
import { afterAuthoredWrite } from "../actions";
import { api, host } from "../host";
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
}

export function useSeriesConfig(ep: string): SeriesConfig {
  const [doc, setDoc] = useState<SourceDoc | null>(null);
  const [base, setBase] = useState<Raw | null>(null);
  const [draft, setDraftState] = useState<Raw | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [check, setCheck] = useState<SourceCheck | null>(null);
  const [saving, setSaving] = useState(false);
  const [conflict, setConflict] = useState(false);

  async function reload() {
    setError(null);
    setConflict(false);
    try {
      const d = await api().source(ep, "series");
      setDoc(d);
      try {
        const raw = JSON.parse(d.text) as Raw;
        setBase(raw);
        setDraftState(raw);
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
    void reload();
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
    doc, base, draft, error, conflict, saving, check, reload, save,
    setDraft: (f) => setDraftState((d) => (d ? f(d) : d)),
    revert: () => setDraftState(base),
    dirty: !!draft && !!base && !same(draft, base),
  };
}
