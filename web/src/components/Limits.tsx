// A video target's limits (seriesmith/limits.py) as one form: how long a shot
// may be, what sizes, how long a prompt, which pictures and how they're sent,
// whether it makes sound. The details window shows it for every target (a
// built-in's changes stay on this machine; "Back to shipped" undoes them); the
// Router wizard edits a proposal's before it's saved.

import { useState } from "react";
import { saveTargetLimits } from "../actions";
import type { ImageLimits, Limits, SharedField, Target } from "../types";
import { useApp } from "../store";

const VIAS: [string, string][] = [
  ["", "a link (uploaded to Comfy)"],
  ["base64", "inline bytes (Veo)"],
  ["datauri", "a data: URI"],
  ["seedance", "the Seedance library (BytePlus)"],
];

type Section = "length" | "size" | "prompt" | "pictures" | "sound";

function canEdit(l: Limits, section: Section, sub?: string): boolean {
  const e = l.editable ?? [];
  return e.includes(section) || (!!sub && e.includes(`${section}.${sub}`));
}

/** A number field: blank is "none" (undefined). */
function Num({ value, onChange, disabled, placeholder, width = 70, title }: {
  value: number | null | undefined; onChange: (v: number | undefined) => void; disabled?: boolean;
  placeholder?: string; width?: number; title?: string;
}) {
  return (
    <input className="h3-in h3-mono" type="number" min={0} style={{ width }} disabled={disabled} title={title}
      value={value ?? ""} placeholder={placeholder}
      onChange={(e) => onChange(e.target.value === "" ? undefined : Math.max(0, Math.round(Number(e.target.value))))} />
  );
}

function sizesText(s?: [number, number][]): string {
  return (s ?? []).map(([w, h]) => `${w}x${h}`).join(", ");
}

function parseSizes(t: string): [number, number][] | null {
  const out: [number, number][] = [];
  for (const part of t.split(/[,\s]+/).filter(Boolean)) {
    const m = part.match(/^(\d+)[x*](\d+)$/i);
    if (!m) return null;
    out.push([Number(m[1]), Number(m[2])]);
  }
  return out;
}

/** Where a schema field is written for several models at once: this model's
 * limit is in that prose, so it's shown to check. */
function SharedNote({ fields }: { fields?: SharedField[] }) {
  if (!fields?.length) return null;
  return (
    <>
      {fields.map((f) => (
        <details key={f.field} className="h3-small" style={{ gridColumn: "1 / -1" }}>
          <summary className="h3-warn" style={{ cursor: "pointer" }}>
            Check this: the schema's <span className="h3-mono">{f.field}</span> is written for several models
          </summary>
          <pre className="h3-mono" style={{ whiteSpace: "pre-wrap", fontSize: 10, margin: "4px 0 0", maxHeight: 180, overflow: "auto" }}>{f.text}</pre>
        </details>
      ))}
    </>
  );
}

export function LimitsForm({ value, onChange, shared, resolutionChoices }: {
  value: Limits;
  onChange: (l: Limits) => void;
  /** limits section -> schema fields written for several models (the Router wizard) */
  shared?: Record<string, SharedField[]>;
  /** every resolution the model's schema lists (the wizard), to tick */
  resolutionChoices?: string[];
}) {
  const l = value;
  // a hosted model's request is all data (every section editable); a local
  // workflow's pictures and sound are what its graph wires
  const hosted = (l.editable ?? []).includes("prompt");
  const set = <K extends Section>(k: K, patch: Partial<Limits[K]> | Limits[K]) =>
    onChange({ ...l, [k]: typeof l[k] === "object" ? { ...(l[k] as object), ...(patch as object) } : patch });
  const sec = l.length.seconds;
  const [sizesDraft, setSizesDraft] = useState(sizesText(l.size.sizes));
  const sizesBad = parseSizes(sizesDraft) === null;
  const resChoices = Array.from(new Set([...(resolutionChoices ?? []), ...(l.shipped?.size.resolutions ?? []),
                                         ...(l.size.resolutions ?? [])]));
  const fps = l.length.fps || 24;
  const fr = l.length.frames;
  return (
    <div className="h3-col" style={{ gap: 8 }}>
      {/* length */}
      <div className="h3-field h3-field-top">
        <label>Length</label>
        {hosted && sec ? (
          <div className="h3-row h3-wrap" style={{ gap: 6 }}>
            <select className="h3-in" disabled={!canEdit(l, "length")} value={sec.values ? "set" : "range"}
              onChange={(e) => set("length", { seconds: e.target.value === "set"
                ? { values: [sec.min ?? 4, sec.max ?? 8].filter((v, i, a) => a.indexOf(v) === i) }
                : { min: Math.min(...(sec.values ?? [4])), max: Math.max(...(sec.values ?? [10])) } })}>
              <option value="range">from … to … seconds</option>
              <option value="set">only these seconds</option>
            </select>
            {sec.values ? (
              <input className="h3-in h3-mono" style={{ width: 120 }} disabled={!canEdit(l, "length")}
                value={sec.values.join(", ")} placeholder="4, 6, 8" title="Whole seconds, comma-separated"
                onChange={(e) => set("length", { seconds: { values: e.target.value.split(/[,\s]+/).map(Number).filter((n) => n > 0) } })} />
            ) : (
              <>
                <Num value={sec.min} disabled={!canEdit(l, "length")} title="Shortest, in seconds"
                  onChange={(v) => set("length", { seconds: { ...sec, min: v ?? 1 } })} />
                <span className="h3-small">to</span>
                <Num value={sec.max} disabled={!canEdit(l, "length")} title="Longest, in seconds"
                  onChange={(v) => set("length", { seconds: { ...sec, max: v ?? sec.min ?? 1 } })} />
                <span className="h3-small h3-muted">s</span>
              </>
            )}
          </div>
        ) : (
          <div className="h3-row h3-wrap" style={{ gap: 6 }}>
            <span className="h3-small">frames</span>
            <Num value={fr?.step} disabled={!canEdit(l, "length")} width={56} title="Step: lengths go up by this many frames"
              onChange={(v) => set("length", { frames: { step: v ?? 1, base: fr?.base ?? 1, max: fr?.max ?? 1 } })} />
            <span className="h3-small">× k +</span>
            <Num value={fr?.base} disabled={!canEdit(l, "length")} width={56} title="Base: the shortest length"
              onChange={(v) => set("length", { frames: { step: fr?.step ?? 1, base: v ?? 1, max: fr?.max ?? 1 } })} />
            <span className="h3-small">up to</span>
            <Num value={fr?.max} disabled={!canEdit(l, "length")} title="The longest, in frames"
              onChange={(v) => set("length", { frames: { step: fr?.step ?? 1, base: fr?.base ?? 1, max: v ?? 1 } })} />
            <span className="h3-small h3-muted">({fr ? (fr.max / fps).toFixed(1) : "?"}s at {fps} fps)</span>
            <span className="h3-small">trained on</span>
            <Num value={l.length.trained} disabled={!canEdit(l, "length")} width={60} placeholder="—"
              title="The length the model was trained on, in frames: longer shots get a warning"
              onChange={(v) => set("length", { trained: v ?? 0 })} />
          </div>
        )}
        <SharedNote fields={shared?.length} />
      </div>

      {/* size */}
      <div className="h3-field h3-field-top">
        <label>Size</label>
        <div className="h3-col" style={{ gap: 4 }}>
          {hosted && l.size.resolutions !== undefined ? (
            <div className="h3-row h3-wrap" style={{ gap: 8 }}>
              {resChoices.map((r) => (
                <label key={r} className="h3-check h3-small">
                  <input type="checkbox" disabled={!canEdit(l, "size")} checked={l.size.resolutions!.includes(r)}
                    onChange={(e) => set("size", { resolutions: e.target.checked
                      ? resChoices.filter((x) => x === r || l.size.resolutions!.includes(x))
                      : l.size.resolutions!.filter((x) => x !== r) })} />
                  {r}
                </label>
              ))}
            </div>
          ) : (
            <>
              <div className="h3-row h3-wrap" style={{ gap: 6 }}>
                <span className="h3-small">multiple of</span>
                <Num value={l.size.multiple} disabled={!canEdit(l, "size")} width={56}
                  title="Width and height must divide by this (LTX 32 or 64, Wan 16)"
                  onChange={(v) => set("size", { multiple: v || 1 })} />
                <select className="h3-in" disabled={!canEdit(l, "size")} value={l.size.fit ?? "error"}
                  title="A size that isn't legal: snapped to the nearest legal one, or an error naming it"
                  onChange={(e) => set("size", { fit: e.target.value as "error" | "snap" })}>
                  <option value="snap">snap to a legal size</option>
                  <option value="error">refuse it</option>
                </select>
              </div>
              <div className="h3-row h3-wrap" style={{ gap: 6 }}>
                <span className="h3-small">at most</span>
                <Num value={l.size.long_side} disabled={!canEdit(l, "size")} placeholder="—" title="Longest side, in pixels (blank: no limit)"
                  onChange={(v) => set("size", { long_side: v })} />
                <span className="h3-small">long side,</span>
                <Num value={l.size.pixels} disabled={!canEdit(l, "size")} width={96} placeholder="—" title="Width × height (blank: no limit)"
                  onChange={(v) => set("size", { pixels: v })} />
                <span className="h3-small">pixels</span>
              </div>
              <div className="h3-row" style={{ gap: 6 }}>
                <span className="h3-small" style={{ whiteSpace: "nowrap" }}>only these</span>
                <input className="h3-in h3-mono h3-grow" disabled={!canEdit(l, "size")} value={sizesDraft}
                  placeholder="any size (or e.g. 1280x720, 720x1280)"
                  title="A model that takes set resolutions only: each shot goes to the nearest of these"
                  onChange={(e) => {
                    setSizesDraft(e.target.value);
                    const s = parseSizes(e.target.value);
                    if (s) set("size", { sizes: s });
                  }} />
              </div>
              {sizesBad && <div className="h3-small h3-err">Write sizes as 1280x720, separated by commas.</div>}
            </>
          )}
        </div>
        <SharedNote fields={shared?.size} />
      </div>

      {/* prompt */}
      {hosted && (
        <div className="h3-field h3-field-top">
          <label>Prompt</label>
          <div className="h3-row" style={{ gap: 6 }}>
            <span className="h3-small">at most</span>
            <Num value={l.prompt.max_chars} disabled={!canEdit(l, "prompt")} width={80} placeholder="—"
              title="The longest prompt the model takes, in characters: a longer one loses its style line first, then the place and looks (which the pictures carry); the action and dialogue stay"
              onChange={(v) => set("prompt", { max_chars: v })} />
            <span className="h3-small">characters</span>
          </div>
          <SharedNote fields={shared?.prompt} />
        </div>
      )}

      {/* pictures */}
      <div className="h3-field h3-field-top">
        <label>Pictures</label>
        <div className="h3-col" style={{ gap: 4 }}>
          {hosted && (
            <div className="h3-row h3-wrap" style={{ gap: 8 }}>
              <span className="h3-small">references</span>
              <Num value={l.pictures.references ?? 0} disabled={!canEdit(l, "pictures")} width={50}
                title="How many reference pictures (subjects, then the place); 0: it takes none"
                onChange={(v) => set("pictures", { references: v ?? 0 })} />
              <label className="h3-check h3-small">
                <input type="checkbox" disabled={!canEdit(l, "pictures")} checked={!!l.pictures.first}
                  onChange={(e) => set("pictures", { first: e.target.checked })} /> first frame
              </label>
              <label className="h3-check h3-small">
                <input type="checkbox" disabled={!canEdit(l, "pictures")} checked={!!l.pictures.last}
                  onChange={(e) => set("pictures", { last: e.target.checked })} /> last frame
              </label>
            </div>
          )}
          <label className="h3-check h3-small">
            <input type="checkbox" disabled={!canEdit(l, "pictures", "needs_first")} checked={!!l.pictures.needs_first}
              onChange={(e) => set("pictures", { needs_first: e.target.checked })} />
            every shot needs its first keyframe (image to video)
          </label>
          {hosted && (
            <div className="h3-row" style={{ gap: 6 }}>
              <span className="h3-small">sent as</span>
              <select className="h3-in" disabled={!canEdit(l, "pictures")} value={l.pictures.via ?? ""}
                onChange={(e) => set("pictures", { via: e.target.value })}>
                {VIAS.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
              </select>
            </div>
          )}
          {!hosted && (
            <span className="h3-small h3-muted">
              {l.pictures.references == null ? "References packed in one sheet" : `Up to ${l.pictures.references} reference pictures`}
              {l.pictures.first ? ", a first frame" : ""}{l.pictures.last ? ", a last frame" : ""}: what the workflow wires.
            </span>
          )}
        </div>
        <SharedNote fields={shared?.pictures} />
      </div>

      {/* sound */}
      {hosted && (
        <div className="h3-field h3-field-top">
          <label>Sound</label>
          <label className="h3-check h3-small">
            <input type="checkbox" disabled={!canEdit(l, "sound")} checked={l.sound}
              onChange={(e) => onChange({ ...l, sound: e.target.checked })} />
            makes sound {l.sound ? "" : "— off: the silent prompt (no quoted lines; Runway refuses them)"}
          </label>
        </div>
      )}
    </div>
  );
}

/** The sections of `draft` that differ from `from`, and that may change. */
export function changedLimits(draft: Limits, from: Limits): Partial<Limits> {
  const out: Record<string, unknown> = {};
  for (const k of ["length", "size", "prompt", "pictures", "sound"] as Section[]) {
    if (!canEdit(draft, k) && !(k === "pictures" && canEdit(draft, "pictures", "needs_first"))) continue;
    let v: unknown = draft[k];
    if (k === "pictures" && !canEdit(draft, "pictures")) v = { needs_first: draft.pictures.needs_first };
    const was = k === "pictures" && !canEdit(draft, "pictures") ? { needs_first: from.pictures.needs_first } : from[k];
    if (JSON.stringify(v) !== JSON.stringify(was)) out[k] = v;
  }
  return out as Partial<Limits>;
}

const SCOPE: Record<string, string> = {
  builtin: "seriesmith's own: a change applies on this machine, for every show",
  user: "yours, for every show",
  show: "this show's own",
};

/** The details window's limits card (a video target's, or a hosted image
 * model's): read, then Edit; a built-in's changes go back with "Back to
 * shipped". */
export function LimitsCard({ t }: { t: Target }) {
  const saving = useApp((s) => !!s.busy["target-save"]);
  const [draft, setDraft] = useState<Limits | ImageLimits | null>(null);
  const l = t.limits;
  if (!l) return null;
  const image = t.kind === "image";
  if (image && !(l.editable ?? []).length) return null;          // a local workflow's: its graph's
  const base = (l.overridden && l.shipped ? { ...l, ...l.shipped } : l) as Limits | ImageLimits;
  const changed = (d: Limits | ImageLimits, from: Limits | ImageLimits) => (image
    ? changedImageLimits(d as ImageLimits, from as ImageLimits)
    : changedLimits(d as Limits, from as Limits));
  async function save() {
    if (!draft) return;
    // a built-in's override is everything that differs from what it shipped with
    const diff = changed(draft, t.scope === "builtin" ? base : l!);
    if (t.scope === "builtin" && !Object.keys(diff).length) {
      if (await saveTargetLimits(t.id, null)) setDraft(null);
      return;
    }
    if (await saveTargetLimits(t.id, diff as Partial<Limits>)) setDraft(null);
  }
  return (
    <div className="h3-col" style={{ gap: 6 }}>
      <div className="h3-h">
        Limits
        <span className="h3-muted h3-small" style={{ textTransform: "none", fontWeight: 400 }}>
          {" "}— {SCOPE[t.scope ?? "builtin"]}{l.overridden ? " (changed here)" : ""}
        </span>
      </div>
      {draft ? (
        <>
          {image
            ? <ImageLimitsForm value={draft as ImageLimits} onChange={setDraft} />
            : <LimitsForm value={draft as Limits} onChange={setDraft} />}
          <div className="h3-row" style={{ gap: 6 }}>
            <span className="h3-grow" />
            <button className="h3-btn" onClick={() => setDraft(null)}>Cancel</button>
            <button className="h3-btn h3-primary" disabled={saving} onClick={() => void save()}>
              <i className={saving ? "pi pi-spin pi-spinner" : "pi pi-save"} /> Save limits
            </button>
          </div>
        </>
      ) : (
        <div className="h3-row h3-wrap h3-small" style={{ gap: 8 }}>
          <span className="h3-grow">{image ? imageLimitsSummary(l as ImageLimits) : limitsSummary(l as Limits)}</span>
          {l.overridden && (
            <button className="h3-btn" disabled={saving} title="Drop this machine's changes: the limits seriesmith ships"
              onClick={() => void saveTargetLimits(t.id, null)}>
              <i className="pi pi-undo" /> Back to shipped
            </button>
          )}
          <button className="h3-btn" onClick={() => setDraft(structuredClone(l))}>
            <i className="pi pi-pencil" /> Edit
          </button>
        </div>
      )}
    </div>
  );
}

/** Ticks over a set of choices (ratios, resolutions, sizes), at least one kept. */
function Ticks({ all, value, onChange, disabled }: {
  all: string[]; value: string[]; onChange: (v: string[]) => void; disabled?: boolean;
}) {
  return (
    <div className="h3-row h3-wrap" style={{ gap: 8 }}>
      {all.map((r) => (
        <label key={r} className="h3-check h3-small">
          <input type="checkbox" disabled={disabled || (value.length === 1 && value[0] === r)} checked={value.includes(r)}
            onChange={(e) => onChange(e.target.checked ? all.filter((x) => x === r || value.includes(x))
                                                       : value.filter((x) => x !== r))} />
          {r}
        </label>
      ))}
    </div>
  );
}

/** A hosted image model's limits: the size it's asked for in, its prompt, its
 * pictures (how many; 0 is text to image only) and how they're sent. */
export function ImageLimitsForm({ value, onChange, shared, choices }: {
  value: ImageLimits;
  onChange: (l: ImageLimits) => void;
  shared?: Record<string, SharedField[]>;
  /** every ratio / resolution / size the schema lists (the wizard), to tick */
  choices?: ImageLimits["size"];
}) {
  const l = value;
  const set = <K extends "size" | "prompt" | "pictures">(k: K, patch: Partial<ImageLimits[K]>) =>
    onChange({ ...l, [k]: { ...l[k], ...patch } });
  const all = (k: "ratios" | "resolutions" | "sizes") =>
    Array.from(new Set([...(choices?.[k] ?? []), ...(l.shipped?.size[k] ?? []), ...(l.size[k] ?? [])]));
  return (
    <div className="h3-col" style={{ gap: 8 }}>
      <div className="h3-field h3-field-top">
        <label>Size</label>
        <div className="h3-col" style={{ gap: 4 }}>
          {l.size.ratios && (<><span className="h3-small h3-muted">shapes it's asked for in</span>
            <Ticks all={all("ratios")} value={l.size.ratios} onChange={(v) => set("size", { ratios: v })} /></>)}
          {l.size.resolutions && (<><span className="h3-small h3-muted">sizes (1K is about a megapixel; the smallest that fits is asked for)</span>
            <Ticks all={all("resolutions")} value={l.size.resolutions} onChange={(v) => set("size", { resolutions: v })} /></>)}
          {l.size.sizes && (<><span className="h3-small h3-muted">only these sizes (the nearest in shape is asked for)</span>
            <Ticks all={all("sizes")} value={l.size.sizes} onChange={(v) => set("size", { sizes: v })} /></>)}
          {(l.size.min_pixels !== undefined || l.size.max_pixels !== undefined || (!l.size.ratios && !l.size.resolutions && !l.size.sizes)) && (
            <div className="h3-row h3-wrap" style={{ gap: 6 }}>
              <span className="h3-small">from</span>
              <Num value={l.size.min_pixels} width={100} placeholder="—" title="The fewest pixels it draws (a smaller ref is asked for bigger)"
                onChange={(v) => set("size", { min_pixels: v })} />
              <span className="h3-small">to</span>
              <Num value={l.size.max_pixels} width={100} placeholder="—" title="The most pixels it draws"
                onChange={(v) => set("size", { max_pixels: v })} />
              <span className="h3-small">pixels</span>
            </div>
          )}
        </div>
        <SharedNote fields={shared?.size} />
      </div>
      <div className="h3-field h3-field-top">
        <label>Prompt</label>
        <div className="h3-row" style={{ gap: 6 }}>
          <span className="h3-small">at most</span>
          <Num value={l.prompt.max_chars} width={80} placeholder="—" title="The longest prompt it takes, in characters"
            onChange={(v) => set("prompt", { max_chars: v })} />
          <span className="h3-small">characters</span>
        </div>
        <SharedNote fields={shared?.prompt} />
      </div>
      <div className="h3-field h3-field-top">
        <label>Pictures</label>
        <div className="h3-col" style={{ gap: 4 }}>
          <div className="h3-row h3-wrap" style={{ gap: 8 }}>
            <span className="h3-small">takes up to</span>
            <Num value={l.pictures.references ?? 0} width={50}
              title="Reference pictures: an edit's source, a keyframe's characters and plate, a variant's base view. 0: text to image only."
              onChange={(v) => set("pictures", { references: v ?? 0 })} />
            <span className="h3-small">{(l.pictures.references ?? 0) ? "pictures (edits and references)" : "— text to image only"}</span>
          </div>
          <div className="h3-row" style={{ gap: 6 }}>
            <span className="h3-small">sent as</span>
            <select className="h3-in" value={l.pictures.via ?? ""} onChange={(e) => set("pictures", { via: e.target.value })}>
              {VIAS.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
            </select>
          </div>
        </div>
        <SharedNote fields={shared?.pictures} />
      </div>
    </div>
  );
}

/** The sections of an image model's `draft` that differ from `from`. */
export function changedImageLimits(draft: ImageLimits, from: ImageLimits): Partial<ImageLimits> {
  const out: Record<string, unknown> = {};
  for (const k of ["size", "prompt", "pictures"] as const) {
    if (JSON.stringify(draft[k]) !== JSON.stringify(from[k])) out[k] = draft[k];
  }
  return out as Partial<ImageLimits>;
}

/** One line: "16:9, 1:1… · 1K, 2K · up to 6 pictures, inline". */
export function imageLimitsSummary(l: ImageLimits): string {
  const parts: string[] = [];
  const z = l.size;
  if (z.ratios?.length) parts.push(z.ratios.length > 4 ? `${z.ratios.length} shapes` : z.ratios.join(", "));
  if (z.resolutions?.length) parts.push(z.resolutions.join(", "));
  if (z.sizes?.length) parts.push(z.sizes.join(", "));
  if (z.min_pixels || z.max_pixels) {
    parts.push(`${z.min_pixels ? (z.min_pixels / 1e6).toFixed(1) : "?"}–${z.max_pixels ? (z.max_pixels / 1e6).toFixed(1) : "?"} MP`);
  }
  if (l.prompt.max_chars) parts.push(`prompt ≤ ${l.prompt.max_chars}`);
  const n = l.pictures.references ?? 0;
  parts.push(n ? `up to ${n} picture${n > 1 ? "s" : ""}${l.pictures.via ? `, ${l.pictures.via === "base64" ? "inline" : l.pictures.via}` : ""}`
               : "text to image only");
  return parts.join(" · ");
}

/** One line: "2–10 s · 720P, 1080P · prompt ≤ 1000 · 5 references, first frame · silent". */
export function limitsSummary(l: Limits): string {
  const parts: string[] = [];
  const s = l.length.seconds;
  if (s) parts.push(s.values ? `${s.values.join("/")} s` : `${s.min ?? "?"}–${s.max ?? "?"} s`);
  else if (l.length.frames) {
    const f = l.length.frames;
    parts.push(`${f.step}k+${f.base} frames, up to ${f.max} (${(f.max / (l.length.fps || 24)).toFixed(1)}s)`);
  }
  if (l.size.resolutions) parts.push(l.size.resolutions.join(", "));
  else if (l.size.sizes?.length) parts.push(`only ${sizesText(l.size.sizes)}`);
  else {
    const z = [`×${l.size.multiple ?? 1}`];
    if (l.size.long_side) z.push(`≤ ${l.size.long_side} long side`);
    parts.push(z.join(" "));
  }
  if (l.prompt.max_chars) parts.push(`prompt ≤ ${l.prompt.max_chars}`);
  const p: string[] = [];
  if (l.pictures.references) p.push(`${l.pictures.references} references`);
  if (l.pictures.first) p.push("first frame");
  if (l.pictures.last) p.push("last frame");
  if (l.pictures.needs_first) p.push("needs a first frame");
  if (p.length) parts.push(p.join(", "));
  if (!l.sound) parts.push("silent");
  return parts.join(" · ");
}
