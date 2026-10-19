import { useEffect, useMemo, useState } from "react";
import { loadModelFiles, loadModels, modelFilesKey } from "../actions";
import { diffStats, diffWords } from "../lib/diff";
import type { LoraRow } from "../lib/overrideForm";
import { loraChainLine, parseLoraChain } from "../lib/shotForm";
import { shortName } from "../lib/format";
import { isModelMismatch, modelGroups, modelWarning } from "../lib/targets";
import { useApp } from "../store";
import type { ModelList } from "../types";
import { useListBackend, useTargetPickers } from "./Targets";

/** Model picker from ComfyUI's diffusion_models (or unet) list. `""` = the placeholder. */
/** `choices` (a target's own list) replaces ComfyUI's generic one. `grouped`
 * (GET /seriesmith/models) puts the files of the target's family first, the rest
 * under "Other files (unverified)", and warns when one of those is picked. */
export function ModelSelect({ value, onChange, placeholder, choices, grouped }: { value: string; onChange: (v: string) => void; placeholder?: string; choices?: string[]; grouped?: ModelList }) {
  const models = useApp((s) => s.models);
  const err = useApp((s) => s.modelsError);
  useEffect(() => {
    void loadModels();
  }, []);
  const groups = modelGroups(grouped);
  if (groups && grouped) {
    const all = grouped.files.map((f) => f.name);
    const warn = modelWarning(grouped, value);
    const mismatch = isModelMismatch(grouped, value);
    return (
      <div className="h3-col" style={{ gap: 3 }}>
        <select className="h3-in" value={value} onChange={(e) => onChange(e.target.value)} title={value || placeholder || ""}>
          {placeholder != null && <option value="">{placeholder}</option>}
          {value && !all.includes(value) && <option value={value}>{shortName(value, 48)} (not installed)</option>}
          {groups.matching.map((f) => (
            <option key={f.name} value={f.name} title={f.match === "fingerprint" ? `${f.name}\n${f.detail}` : f.name}>
              {shortName(f.name, 48)}{f.match === "fingerprint" ? ` (${grouped.label} by its header)` : ""}
            </option>
          ))}
          {groups.other.length > 0 && (
            <optgroup label="Other files (unverified)">
              {groups.other.map((f) => (
                <option key={f.name} value={f.name} title={f.detail ? `${f.name}\n${f.detail}` : f.name}>
                  {shortName(f.name, 48)}{f.mismatch ? ` (${f.label || "another family"})` : ""}
                </option>
              ))}
            </optgroup>
          )}
        </select>
        {warn && <div className={`h3-note ${mismatch ? "h3-note-err" : "h3-note-info"} h3-small`}>{warn}</div>}
      </div>
    );
  }
  const list = choices ?? models ?? [];
  const missing = value && !list.includes(value);
  return (
    <select className="h3-in" value={value} onChange={(e) => onChange(e.target.value)} title={value || placeholder || ""}>
      {placeholder != null && <option value="">{placeholder}</option>}
      {missing && <option value={value}>{shortName(value, 48)} ({choices ? "not offered by this target" : "not installed"})</option>}
      {list.map((m) => (
        <option key={m} value={m} title={m}>
          {shortName(m, 48)}
        </option>
      ))}
      {!choices && !models && !err && <option disabled>Loading models…</option>}
      {!choices && err && <option disabled>Couldn't list models: {err}</option>}
    </select>
  );
}

/** A stack of LoRA rows with strength. `empty` says what no rows means where it is
 * shown: an override's custom list of none bypasses the workflow's LoRA, while
 * an edit with none simply adds nothing. */
export function LoraEditor({ rows, onChange, choices, empty }: { rows: LoraRow[]; onChange: (rows: LoraRow[]) => void; choices?: string[]; empty?: string }) {
  const loras = useApp((s) => s.loras);
  useEffect(() => {
    void loadModels();
  }, []);
  const list = choices ?? loras ?? [];
  const set = (i: number, patch: Partial<LoraRow>) => onChange(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  return (
    <div className="h3-col" style={{ gap: 3 }}>
      {rows.map((r, i) => (
        <div key={i} className="h3-lora">
          <select className="h3-in" value={r.name} onChange={(e) => set(i, { name: e.target.value })} title={r.name}>
            <option value="">(choose a LoRA)</option>
            {r.name && !list.includes(r.name) && <option value={r.name}>{shortName(r.name, 44)} ({choices ? "not offered by this target" : "not installed"})</option>}
            {list.map((l) => (
              <option key={l} value={l} title={l}>{shortName(l, 44)}</option>
            ))}
          </select>
          <input
            className="h3-in"
            type="number"
            step={0.05}
            value={r.strength}
            title="Strength"
            onChange={(e) => set(i, { strength: e.target.value })}
          />
          <button className="h3-btn h3-icon" title="Remove" onClick={() => onChange(rows.filter((_, j) => j !== i))}>✕</button>
        </div>
      ))}
      <div className="h3-row">
        <button className="h3-btn" onClick={() => onChange([...rows, { name: "", strength: "1" }])}>+ LoRA</button>
        {!rows.length && <span className="h3-muted h3-small">{empty ?? "No LoRAs (the workflow's LoRA is bypassed)"}</span>}
      </div>
    </div>
  );
}

/** The built prompt (old) against the edited one (new), word by word. */
export function DiffView({ oldText, newText }: { oldText: string; newText: string }) {
  const parts = useMemo(() => diffWords(oldText, newText), [oldText, newText]);
  const stats = useMemo(() => diffStats(parts), [parts]);
  if (oldText === newText) return <div className="h3-muted h3-small">Same as the built prompt.</div>;
  return (
    <div className="h3-col" style={{ gap: 2 }}>
      <div className="h3-small h3-muted">
        vs the built prompt: <span style={{ color: "var(--h3-ok)" }}>+{stats.added}</span> / <span style={{ color: "var(--h3-failed)" }}>−{stats.removed}</span> words
      </div>
      <pre className="h3-pre h3-diff">
        {parts.map((p, i) =>
          p.op === "eq" ? <span key={i}>{p.text}</span> : p.op === "add" ? <ins key={i}>{p.text}</ins> : <del key={i}>{p.text}</del>,
        )}
      </pre>
    </div>
  );
}

/** The "more settings" disclosure: an arrow, like a section's, not a checkbox. */
export function MoreToggle({ open, onToggle, label }: { open: boolean; onToggle: (open: boolean) => void; label: string }) {
  return (
    <button type="button" className="h3-link sm-more" aria-expanded={open} onClick={() => onToggle(!open)}
      style={{ display: "inline-flex", alignItems: "center", gap: 6, alignSelf: "flex-start", padding: "2px 0" }}>
      <i className={`pi ${open ? "pi-chevron-down" : "pi-chevron-right"}`} style={{ fontSize: 10 }} />
      <span className="h3-small">{label}</span>
    </button>
  );
}

/** A `lora:` line's LoRAs (`name`, `name:0.7`, a chain "a:0.6, b" applied in
 * that order, or `none`), picked from what `target` loads: one row per LoRA,
 * "+ LoRA" for another. "" is the default (the series' or the target's preset).
 * `backend`: where it renders (the series form's own field), for whose list:
 * Comfy Cloud's files when that is Comfy Cloud (useListBackend). */
export function LoraLine({ value, onChange, target, empty = "the default", backend }: {
  value: string; onChange: (v: string) => void; target: string | null; empty?: string; backend?: string | null;
}) {
  const pickers = useTargetPickers(target, backend);
  const on = useListBackend(backend);
  const loras = useApp((s) => s.loras);
  // the files of the model's LoRA family (GET /seriesmith/models?param=loras): the
  // list where ComfyUI's own isn't served (the standalone app)
  const t = pickers.target;
  const family = useApp((s) => (t?.models?.loras ? s.modelFiles[modelFilesKey(t.id, "loras", on)] : undefined));
  useEffect(() => {
    void loadModels();
    if (t?.models?.loras) void loadModelFiles(t.id, "loras", false, on);
  }, [t?.id, on]);
  const list = pickers.loras?.length ? pickers.loras : family?.files.length ? family.files.map((f) => f.name)
    : pickers.cloud ? [] : loras ?? [];
  const cur = parseLoraChain(value);
  // rows added with "+ LoRA" and not chosen yet (the line can't hold them)
  const [blank, setBlank] = useState(0);
  const rows = [...cur.rows, ...Array.from({ length: blank }, () => ({ name: "", strength: "1" }))];
  if (!rows.length) rows.push({ name: "", strength: "1" });
  const emit = (next: { name: string; strength: string }[]) => {
    setBlank(next.some((r) => r.name) ? next.filter((r) => !r.name).length : 0);
    onChange(loraChainLine(next));
  };
  const setRow = (i: number, patch: Partial<{ name: string; strength: string }>) =>
    emit(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  return (
    <div className="h3-col" style={{ gap: 3 }}>
      {rows.map((r, i) => {
        // the first row also says the default, or none at all
        const pick = i === 0 && cur.off ? "__none" : r.name;
        return (
          <div key={i} className="h3-row" style={{ gap: 4 }}>
            <select className="h3-in h3-grow" style={{ minWidth: 0 }} value={pick} title={r.name || undefined}
              onChange={(e) => {
                const v = e.target.value;
                if (i === 0 && v === "__none") return onChange("none");
                if (v === "" && rows.length === 1) return onChange("");
                setRow(i, { name: v });
              }}>
              <option value="">{i === 0 ? empty : "(choose a LoRA)"}</option>
              {i === 0 && <option value="__none">none (no LoRA)</option>}
              {r.name && !list.includes(r.name) && <option value={r.name}>{shortName(r.name, 44)} ({pickers.cloud ? "not on Comfy Cloud" : "not installed"})</option>}
              {list.map((l) => <option key={l} value={l} title={l}>{shortName(l, 44)}</option>)}
            </select>
            {r.name && (
              <input className="h3-in" type="number" step={0.05} style={{ width: 70 }} title="Strength" value={r.strength}
                onChange={(e) => setRow(i, { strength: e.target.value })} />
            )}
            {rows.length > 1 && (
              <button className="h3-btn h3-icon" title="Remove this LoRA" onClick={() => emit(rows.filter((_, j) => j !== i))}>✕</button>
            )}
          </div>
        );
      })}
      {!cur.off && rows.some((r) => r.name) && (
        <button className="h3-link h3-small" style={{ alignSelf: "flex-start" }} title="Add another LoRA: they're applied in this order"
          onClick={() => setBlank(blank + 1)}>+ LoRA</button>
      )}
    </div>
  );
}

/** A model file for `target`, from what it can load; "" is the default. A target
 * without a model widget gets a text box. */
export function ModelLine({ value, onChange, target, empty = "the default", backend }: {
  value: string; onChange: (v: string) => void; target: string | null; empty?: string; backend?: string | null;
}) {
  const pickers = useTargetPickers(target, backend);
  if (pickers.models === null) {
    return <input className="h3-in" value={value} placeholder={empty} onChange={(e) => onChange(e.target.value)} />;
  }
  return <ModelSelect value={value} onChange={onChange} placeholder={empty} choices={pickers.models ?? undefined} grouped={pickers.modelFiles} />;
}
