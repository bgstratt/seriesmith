// Series settings: the series config (series.json) as a form, for people who
// would rather fill in fields than edit JSON. It reads the file through
// GET /seriesmith/source, changes only the keys it shows (lib/seriesForm.ts),
// and saves through PUT /seriesmith/source — the same save, check, history copy
// and rebuild as the Series config text window, which "Edit as text" opens.

import { useEffect, useMemo, useState } from "react";
import { afterAuthoredWrite, loadTargets, openSeriesForm, openSource } from "../actions";
import { api, host } from "../host";
import {
  DEFAULT_PROXY, FINAL_SIZES, PROXY_SIZES, SECTIONS, getPath, parsed, same, serialize, setPath, setSize,
  shapeNote, shown, sizeOf, slug, type Field, type Raw,
} from "../lib/seriesForm";
import { conflictOf } from "../lib/sourceSession";
import { sizeCheck, sizeRule, type SizeRule } from "../lib/size";
import { useApp } from "../store";
import type { SourceCheck, SourceDoc, Target, TargetKind } from "../types";
import { FloatingWindow, type Rect } from "./FloatingWindow";

const RECT_KEY = "seriesmith.seriesform.rect";

function defaultRect(): Rect {
  const W = window.innerWidth || 1280;
  const H = window.innerHeight || 800;
  const w = Math.max(380, Math.min(560, Math.round(W * 0.36)));
  return { x: Math.max(16, Math.min(380, W - w - 16)), y: 56, w, h: Math.max(360, H - 120) };
}

export function SeriesFormWindow() {
  const open = useApp((s) => s.seriesFormOpen);
  const ep = useApp((s) => s.ep);
  if (!open || !ep) return null;
  return <SeriesForm key={ep} ep={ep} />;
}

function SeriesForm({ ep }: { ep: string }) {
  const [doc, setDoc] = useState<SourceDoc | null>(null);
  const [base, setBase] = useState<Raw | null>(null);
  const [draft, setDraft] = useState<Raw | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [check, setCheck] = useState<SourceCheck | null>(null);
  const [saving, setSaving] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [more, setMore] = useState(false);
  const targets = useApp((s) => s.targets);
  const backends = useApp((s) => s.backends);

  async function load() {
    setError(null);
    setConflict(false);
    try {
      const d = await api().source(ep, "series");
      let raw: Raw;
      try {
        raw = JSON.parse(d.text) as Raw;
      } catch (e) {
        setDoc(d);
        setBase(null);
        setDraft(null);
        setError(`series.json isn't valid JSON (${(e as Error).message}): fix it as text first.`);
        return;
      }
      setDoc(d);
      setBase(raw);
      setDraft(raw);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    void load();
    void loadTargets();
  }, [ep]);

  const dirty = !!draft && !!base && !same(draft, base);

  async function save() {
    if (!doc || !draft) return;
    setSaving(true);
    setError(null);
    try {
      const text = serialize(draft, doc.text);
      const r = await api().putSource({ ep, file: "series", text, base_hash: doc.hash, rebuild: true });
      setCheck(r.check);
      setDoc({ ...doc, text, hash: r.hash });
      setBase(draft);
      afterAuthoredWrite(r.build);
      if (r.check.errors.length) host().toast("warn", "Saved, with problems", r.check.errors[0].message);
      else host().toast("info", "Series settings saved", "The episode was rebuilt.");
    } catch (e) {
      if (conflictOf(e)) setConflict(true);
      else setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  // Ctrl+S saves while the window has focus
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s" && dirty) {
        const el = document.getElementById("sm-seriesform");
        if (el && el.contains(document.activeElement)) {
          e.preventDefault();
          void save();
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const set = (path: readonly string[], value: unknown) => setDraft((d) => (d ? setPath(d, path, value) : d));
  const list = targets?.targets ?? [];
  const videoId = (draft && (getPath(draft, ["series", "target"]) as string)) || targets?.default?.video || "minimax_h3_ref2va";
  const rule = sizeRule(list.find((t) => t.id === videoId)?.template);

  const head = (
    <>
      <i className="pi pi-sliders-h" />
      <span className="h3-grow">Series settings{dirty ? " •" : ""}</span>
      <button className="h3-btn h3-icon" title="Edit series.json as text" onClick={() => openSource("series")}><i className="pi pi-code" /></button>
      <button className="h3-btn h3-icon" title="Close" onClick={() => {
        if (dirty && !window.confirm("Close without saving your changes to the series settings?")) return;
        openSeriesForm(false);
      }}><i className="pi pi-times" /></button>
    </>
  );

  return (
    <FloatingWindow storageKey={RECT_KEY} defaultRect={defaultRect} head={head} minW={360} minH={280}>
      <div id="sm-seriesform" className="h3-col" style={{ padding: 10, overflow: "auto", height: "100%", gap: 10 }}>
        {doc && (
          <div className="h3-small h3-muted">
            Editing <code>{doc.path}</code>{doc.path.startsWith("..") ? " — the show's, shared by its episodes" : ""}
          </div>
        )}
        {doc && base && serialize(base, doc.text) !== doc.text && (
          <div className="h3-small h3-muted">
            Saving lays series.json out the standard way (two-space indent, one key a line); what it
            says doesn't change.
          </div>
        )}
        {error && <div className="h3-err">{error}</div>}
        {conflict && (
          <div className="h3-err">
            series.json changed on disk since it was opened.{" "}
            <button className="h3-btn" onClick={() => void load()}>Reload (drops your changes)</button>
          </div>
        )}
        {!draft && !error && <div className="h3-muted">Loading…</div>}
        {draft && (
          <>
            {SECTIONS.map((sec) => {
              const fields = sec.fields.filter((f) => (!f.when || f.when(draft)) && (more || !f.more));
              return (
                <details key={sec.id} open className="sm-form-section">
                  <summary><b>{sec.title}</b> <span className="h3-small h3-muted">{sec.help}</span></summary>
                  <div className="h3-col" style={{ gap: 8, marginTop: 6 }}>
                    {sec.id === "series" && (
                      <>
                        <SizeField label="Size (final)" value={sizeOf(draft, "series")} choices={FINAL_SIZES} rule={rule}
                          help={`The size the final pass renders at, on the video model's grid${rule.multiple > 1 ? ` (multiples of ${rule.multiple})` : ""}. 1344×768 is H3's own; render smaller and upscale for a master (Finishing).`}
                          onChange={(v) => setDraft((d) => (d ? setSize(d, "series", v) : d))} />
                        <SizeField label="Size (proxy)" value={sizeOf(draft, "proxy")} choices={PROXY_SIZES} rule={rule}
                          placeholder={DEFAULT_PROXY} note={shapeNote(sizeOf(draft, "series"), sizeOf(draft, "proxy"))}
                          help="The animatic: the same shots at the same seeds, rendered small and quick to judge the cut by. 480p is the smallest that still reads; 896×512 is exactly 1344×768's shape."
                          onChange={(v) => setDraft((d) => (d ? setSize(d, "proxy", v) : d))} />
                      </>
                    )}
                    {fields.map((f) => (
                      <FieldRow key={f.path.join(".")} f={f} value={shown(draft, f)} targets={list} defaults={targets?.default}
                        backends={(backends ?? []).map((b) => b.name)}
                        onChange={(v) => {
                          set(f.path, parsed(f, v));
                          // a new series' id follows its title until it's set by hand
                          if (f.path.join(".") === "series.title" && base && !getPath(base, ["series", "id"])) {
                            set(["series", "id"], slug(v));
                          }
                        }} />
                    ))}
                  </div>
                </details>
              );
            })}
            <label className="h3-row h3-small h3-muted">
              <input type="checkbox" checked={more} onChange={(e) => setMore(e.target.checked)} /> Show more settings (steps, LoRAs, model files, negative prompt, where jobs run)
            </label>
            <CastSummary raw={draft} />
            {check && (check.errors.length > 0 || check.warnings.length > 0) && (
              <div className="h3-col" style={{ gap: 2 }}>
                {check.errors.map((m, i) => <span key={`e${i}`} className="h3-err h3-small">✗ {m.message}</span>)}
                {check.warnings.map((m, i) => <span key={`w${i}`} className="h3-warn h3-small">! {m.message}</span>)}
              </div>
            )}
          </>
        )}
      </div>
      <div className="h3-row" style={{ padding: "6px 10px", borderTop: "1px solid var(--h3-border)" }}>
        <span className="h3-small h3-muted h3-grow">{dirty ? "Unsaved changes" : "Saved"}</span>
        <button className="h3-btn" disabled={!dirty || saving} onClick={() => setDraft(base)}>Revert</button>
        <button className="h3-btn h3-primary" disabled={!dirty || saving} onClick={() => void save()}
          title="Save series.json and rebuild the episode (Ctrl+S)">
          {saving ? <i className="pi pi-spin pi-spinner" /> : <i className="pi pi-save" />} Save
        </button>
      </div>
    </FloatingWindow>
  );
}

function FieldRow({ f, value, onChange, targets, defaults, backends }: {
  f: Field; value: string; onChange: (v: string) => void; targets: Target[];
  defaults?: Partial<Record<TargetKind, string>>; backends: string[];
}) {
  const kind = f.kind === "video_target" ? "video" : f.kind === "image_target" ? "image" : f.kind === "audio_target" ? "audio" : null;
  let input;
  if (f.kind === "long") {
    input = <textarea className="h3-in" rows={3} style={{ fontFamily: "inherit", resize: "vertical" }} value={value}
      placeholder={f.placeholder} onChange={(e) => onChange(e.target.value)} />;
  } else if (f.kind === "select") {
    input = (
      <select className="h3-in" value={value} onChange={(e) => onChange(e.target.value)}>
        {(f.choices ?? []).map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
        {value && !(f.choices ?? []).some((c) => c.value === value) && <option value={value}>{value}</option>}
      </select>
    );
  } else if (kind) {
    const mine = targets.filter((t) => t.kind === kind && !t.draft);
    const dflt = defaults?.[kind as TargetKind];
    input = (
      <select className="h3-in" value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{dflt ? `default (${mine.find((t) => t.id === dflt)?.label ?? dflt})` : "default"}</option>
        {mine.map((t) => (
          <option key={t.id} value={t.id}>{t.label}{readinessNote(t)}</option>
        ))}
        {value && !mine.some((t) => t.id === value) && <option value={value}>{value} (not known here)</option>}
      </select>
    );
  } else if (f.kind === "backend") {
    input = (
      <select className="h3-in" value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">each model's own</option>
        {backends.map((b) => <option key={b} value={b}>{b}</option>)}
        {value && !backends.includes(value) && <option value={value}>{value}</option>}
      </select>
    );
  } else {
    input = (
      <input className="h3-in" type={f.kind === "number" ? "number" : "text"} value={value} placeholder={f.placeholder}
        min={f.min} max={f.max} step={f.step} onChange={(e) => onChange(e.target.value)} />
    );
  }
  return (
    <div className="h3-col" style={{ gap: 2 }}>
      <span className="h3-small"><b>{f.label}</b></span>
      {input}
      <span className="h3-small h3-muted">{f.help}</span>
    </div>
  );
}

function readinessNote(t: Target): string {
  const st = t.readiness?.status;
  if (!st || st === "ready") return "";
  if (st === "not_ready") return " — missing files";
  if (st === "degraded") return " — runs slower (an accelerator is missing)";
  return "";
}

function SizeField({ label, value, choices, rule, help, onChange, placeholder, note }: {
  label: string; value: string; choices: string[]; rule: SizeRule; help: string;
  onChange: (v: string) => void; placeholder?: string; note?: string | null;
}) {
  const onGrid = choices.filter((s) => {
    const [w, h] = s.split("x").map(Number);
    return w % rule.multiple === 0 && h % rule.multiple === 0;
  });
  const [custom, setCustom] = useState(() => !!value && !onGrid.includes(value));
  const bad = sizeCheck(value, rule);
  return (
    <div className="h3-col" style={{ gap: 2 }}>
      <span className="h3-small"><b>{label}</b></span>
      <div className="h3-row h3-wrap">
        <select className="h3-in" value={custom ? "__custom__" : value} onChange={(e) => {
          if (e.target.value === "__custom__") setCustom(true);
          else {
            setCustom(false);
            onChange(e.target.value);
          }
        }}>
          <option value="">{placeholder ? `not set (${placeholder.replace("x", "×")})` : "not set"}</option>
          {onGrid.map((s) => <option key={s} value={s}>{s.replace("x", "×")}</option>)}
          <option value="__custom__">Custom…</option>
        </select>
        {custom && (
          <input className="h3-in" style={{ width: 120 }} placeholder="1344x768" value={value}
            onChange={(e) => onChange(e.target.value.replace(/[^\dxX×]/g, ""))} />
        )}
      </div>
      {bad && <span className={`h3-small ${bad.level === "err" ? "h3-err" : "h3-muted"}`}>{bad.text}</span>}
      {note && <span className="h3-small h3-warn">{note}</span>}
      <span className="h3-small h3-muted">{help}</span>
    </div>
  );
}

/** The cast and places, counted: their own forms come next (docs/PLAN.md). */
function CastSummary({ raw }: { raw: Raw }) {
  const subjects = (getPath(raw, ["subjects"]) ?? {}) as Record<string, { kind?: string }>;
  const locations = Object.keys((getPath(raw, ["locations"]) ?? {}) as object);
  const by = useMemo(() => {
    const m: Record<string, number> = {};
    for (const s of Object.values(subjects)) m[s?.kind ?? "character"] = (m[s?.kind ?? "character"] ?? 0) + 1;
    return m;
  }, [subjects]);
  const parts = [...Object.entries(by).map(([k, n]) => `${n} ${k}${n === 1 ? "" : "s"}`),
    `${locations.length} location${locations.length === 1 ? "" : "s"}`];
  return (
    <div className="h3-small h3-muted">
      Cast and places: {parts.join(", ")} — edit them in the Refs tab.
    </div>
  );
}
