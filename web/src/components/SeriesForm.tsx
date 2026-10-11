// Series settings: the series config (series.json) as a form, for people who
// would rather fill in fields than edit JSON. It reads the file through
// GET /seriesmith/source, changes only the keys it shows (lib/seriesForm.ts),
// and saves through PUT /seriesmith/source — the same save, check, history copy
// and rebuild as the Series config text window, which "Edit as text" opens.
// The cast and places are listed at the end; each opens its own card
// (SubjectCard.tsx).

import { useEffect, useState } from "react";
import { loadTargets, openSeriesForm, openSource, openSubjectCard } from "../actions";
import {
  CARD_KINDS, DEFAULT_PROXY, FINAL_SIZES, PROXY_SIZES, SECTIONS, cardKindOf, getPath, parsed, serialize, setPath,
  setSize, shapeNote, shown, sizeOf, slug, type CardKind, type Field, type Raw,
} from "../lib/seriesForm";
import { sizeCheck, sizeRule, type SizeRule } from "../lib/size";
import { useApp } from "../store";
import type { Target, TargetKind } from "../types";
import { pictureOf } from "../lib/pictures";
import { Hover, PicturePath, Thumb } from "./Picture";
import { LoraLine, ModelLine, MoreToggle } from "./Fields";
import { FloatingWindow, type Rect } from "./FloatingWindow";
import { useSeriesConfig } from "./useSeriesConfig";

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
  const sc = useSeriesConfig(ep);
  const { base, draft, dirty, saving } = sc;
  const [more, setMore] = useState(false);
  const targets = useApp((s) => s.targets);
  const backends = useApp((s) => s.backends);
  // a card saved: show what it wrote (unless this form has edits of its own)
  const sourceN = useApp((s) => s.sourceN);
  useEffect(() => {
    void loadTargets();
  }, []);
  useEffect(() => {
    if (sourceN && !dirty) void sc.reload();
  }, [sourceN]);

  // Ctrl+S saves while the window has focus
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s" && dirty) {
        const el = document.getElementById("sm-seriesform");
        if (el && el.contains(document.activeElement)) {
          e.preventDefault();
          void sc.save();
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const set = (path: readonly string[], value: unknown) => sc.setDraft((d) => setPath(d, path, value));
  const list = targets?.targets ?? [];
  const videoId = (draft && (getPath(draft, ["series", "target"]) as string)) || targets?.default?.video || "minimax_h3_ref2va";
  const rule = sizeRule(list.find((t) => t.id === videoId)?.template);

  const head = (
    <>
      <i className="pi pi-cog" />
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
        <FileLine sc={sc} />
        {draft && (
          <>
            {SECTIONS.map((sec) => {
              const fields = sec.fields.filter((f) => (!f.when || f.when(draft)) && !f.more);
              return (
                <details key={sec.id} open className="sm-form-section">
                  <summary><b>{sec.title}</b> <span className="h3-small h3-muted">{sec.help}</span></summary>
                  <div className="h3-col" style={{ gap: 8, marginTop: 6 }}>
                    {sec.id === "series" && (
                      <>
                        <SizeField label="Size (final)" value={sizeOf(draft, "series")} choices={FINAL_SIZES} rule={rule}
                          help={`The size the final pass renders at, on the video model's grid${rule.multiple > 1 ? ` (multiples of ${rule.multiple})` : ""}. 1344×768 is H3's own; render smaller and upscale for a master (Finishing).`}
                          onChange={(v) => sc.setDraft((d) => setSize(d, "series", v))} />
                        <SizeField label="Size (proxy)" value={sizeOf(draft, "proxy")} choices={PROXY_SIZES} rule={rule}
                          placeholder={DEFAULT_PROXY} note={shapeNote(sizeOf(draft, "series"), sizeOf(draft, "proxy"))}
                          help="The animatic: the same shots at the same seeds, rendered small and quick to judge the cut by. 480p is the smallest that still reads; 896×512 is exactly 1344×768's shape."
                          onChange={(v) => sc.setDraft((d) => setSize(d, "proxy", v))} />
                      </>
                    )}
                    {fields.map((f) => (
                      <FieldRow key={f.path.join(".")} f={f} value={shown(draft, f)} targets={list} defaults={targets?.default}
                        backends={(backends ?? []).map((b) => b.name)} videoTarget={videoId}
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
            <MoreToggle open={more} onToggle={setMore} label="More settings: steps, LoRAs, model files, negative prompt, where jobs run" />
            {more && (
              <div className="h3-col" style={{ gap: 10, paddingLeft: 14, borderLeft: "2px solid var(--h3-border)" }}>
                {SECTIONS.map((sec) => {
                  const fields = sec.fields.filter((f) => (!f.when || f.when(draft)) && f.more);
                  if (!fields.length) return null;
                  return (
                    <div key={sec.id} className="h3-col" style={{ gap: 8 }}>
                      <span className="h3-small h3-muted"><b>{sec.title}</b></span>
                      {fields.map((f) => (
                        <FieldRow key={f.path.join(".")} f={f} value={shown(draft, f)} targets={list} defaults={targets?.default}
                          backends={(backends ?? []).map((b) => b.name)} videoTarget={videoId}
                          onChange={(v) => set(f.path, parsed(f, v))} />
                      ))}
                    </div>
                  );
                })}
              </div>
            )}
            <CastList raw={draft} />
            <CheckMessages sc={sc} />
          </>
        )}
      </div>
      <SaveBar dirty={dirty} saving={saving} onRevert={sc.revert} onSave={() => void sc.save()} />
    </FloatingWindow>
  );
}

/** Which file is being edited, a layout note, errors and a conflict. */
export function FileLine({ sc }: { sc: ReturnType<typeof useSeriesConfig> }) {
  const { doc, base, error, conflict, draft } = sc;
  return (
    <>
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
          <button className="h3-btn" onClick={() => void sc.reload()}>Reload (drops your changes)</button>
        </div>
      )}
      {!draft && !error && <div className="h3-muted">Loading…</div>}
    </>
  );
}

export function CheckMessages({ sc }: { sc: ReturnType<typeof useSeriesConfig> }) {
  const check = sc.check;
  if (!check || (!check.errors.length && !check.warnings.length)) return null;
  return (
    <div className="h3-col" style={{ gap: 2 }}>
      {check.errors.map((m, i) => <span key={`e${i}`} className="h3-err h3-small">✗ {m.message}</span>)}
      {check.warnings.map((m, i) => <span key={`w${i}`} className="h3-warn h3-small">! {m.message}</span>)}
    </div>
  );
}

export function SaveBar({ dirty, saving, onRevert, onSave, saveLabel = "Save", extra, status }: {
  dirty: boolean; saving: boolean; onRevert: () => void; onSave: () => void; saveLabel?: string; extra?: React.ReactNode;
  /** what to say instead of Saved / Unsaved changes (an edit that can't be saved yet) */
  status?: string;
}) {
  return (
    <div className="h3-row" style={{ padding: "6px 10px", borderTop: "1px solid var(--h3-border)" }}>
      <span className="h3-small h3-muted h3-grow">{status ?? (dirty ? "Unsaved changes" : "Saved")}</span>
      {extra}
      <button className="h3-btn" disabled={!dirty || saving} onClick={onRevert}>Revert</button>
      <button className="h3-btn h3-primary" disabled={!dirty || saving} onClick={onSave}
        title="Save series.json and rebuild the episode (Ctrl+S)">
        {saving ? <i className="pi pi-spin pi-spinner" /> : <i className="pi pi-save" />} {saveLabel}
      </button>
    </div>
  );
}

export function FieldRow({ f, value, onChange, targets, defaults, backends, videoTarget }: {
  f: Field; value: string; onChange: (v: string) => void; targets?: Target[];
  defaults?: Partial<Record<TargetKind, string>>; backends?: string[];
  /** the video model a LoRA or model file field picks for */
  videoTarget?: string | null;
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
    const mine = (targets ?? []).filter((t) => t.kind === kind && !t.draft);
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
  } else if (f.kind === "picture") {
    input = <PicturePath value={value} onChange={onChange} pickKey={`field:${f.path.join(".")}`} what={f.label.toLowerCase()} placeholder={f.placeholder} />;
  } else if (f.kind === "lora") {
    input = <LoraLine value={value} onChange={onChange} target={videoTarget ?? null} empty="the video model's preset" />;
  } else if (f.kind === "model") {
    input = <ModelLine value={value} onChange={onChange} target={videoTarget ?? null} empty="the video model's preset" />;
  } else if (f.kind === "backend") {
    const bs = backends ?? [];
    input = (
      <select className="h3-in" value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">each model's own</option>
        {bs.map((b) => <option key={b} value={b}>{b}</option>)}
        {value && !bs.includes(value) && <option value={value}>{value}</option>}
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

export function SizeField({ label, value, choices, rule, help, onChange, placeholder, note }: {
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

/** The cast and places, each opening its card, and the buttons that add one. */
const CAST_SHOWN = 60;

function CastList({ raw }: { raw: Raw }) {
  const [q, setQ] = useState("");
  const ep = useApp((s) => s.ep);
  const refs = useApp((s) => (s.ep ? s.refs[s.ep] : undefined));
  const groups: { label: string; block: "subjects" | "locations"; kinds: CardKind[] }[] = [
    { label: "Characters", block: "subjects", kinds: ["character", "group", "voice"] },
    { label: "Props and vehicles", block: "subjects", kinds: ["prop", "vehicle"] },
    { label: "Locations", block: "locations", kinds: ["location"] },
  ];
  return (
    <details open className="sm-form-section">
      <summary><b>Cast and places</b> <span className="h3-small h3-muted">Everyone and everything the shots can name, each with its picture.</span></summary>
      <div className="h3-col" style={{ gap: 8, marginTop: 6 }}>
        <input className="h3-in" placeholder="Find by name or id" value={q} onChange={(e) => setQ(e.target.value)} />
        {groups.map((g) => {
          const all = Object.keys((getPath(raw, [g.block]) ?? {}) as object)
            .filter((id) => g.kinds.includes(cardKindOf(raw, g.block, id)));
          const needle = q.trim().toLowerCase();
          const hits = needle
            ? all.filter((id) => {
              const n = (getPath(raw, [g.block, id, "name"]) as string | undefined) ?? "";
              return id.toLowerCase().includes(needle) || n.toLowerCase().includes(needle);
            })
            : all;
          const ids = hits.slice(0, CAST_SHOWN);
          return (
            <div key={g.label} className="h3-col" style={{ gap: 4 }}>
              <div className="h3-row h3-wrap">
                <span className="h3-small"><b>{g.label}</b> <span className="h3-muted">{needle ? `${hits.length} of ${all.length}` : all.length}</span></span>
                <span className="h3-grow" />
                {g.kinds.map((k) => (
                  <button key={k} className="h3-btn" onClick={() => openSubjectCard({ kind: k, id: null })}>
                    {CARD_KINDS.find((c) => c.kind === k)!.add}
                  </button>
                ))}
              </div>
              <div className="h3-row h3-wrap" style={{ gap: 4 }}>
                {ids.map((id) => {
                  const e = (getPath(raw, [g.block, id]) ?? {}) as Raw;
                  const item = { id, name: typeof e.name === "string" ? e.name : id.replace(/_/g, " "), pic: pictureOf(raw, refs, g.block, id) };
                  return (
                    <Hover key={id} ep={ep} item={item}>
                      <button className="h3-btn" title={`Edit ${id}`} style={{ gap: 5 }}
                        onClick={() => openSubjectCard({ kind: cardKindOf(raw, g.block, id), id })}>
                        <Thumb ep={ep} pic={item.pic} name={item.name} size={20} round={g.block === "subjects"} />
                        {item.name}
                      </button>
                    </Hover>
                  );
                })}
                {hits.length > ids.length && (
                  <span className="h3-small h3-muted">and {hits.length - ids.length} more: find them by name</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </details>
  );
}
