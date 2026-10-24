// The master recipe's per-model sections (upscale.master.targets), as rows:
// which video model (or family) a row is for, and how its takes are upscaled —
// re-sampled with their own model (and optionally a pixel model or SeedVR2
// after), a pixel upscale model, or SeedVR2 — with the models this ComfyUI has
// (GET /seriesmith/upscale/options). The standard settings are one button.
// Keys a row doesn't show (keep_soft, grain, window, ...) are kept as they are.

import { useEffect, useState } from "react";
import { api } from "../host";
import { MASTER_TARGETS, getPath, setPath, type Raw } from "../lib/seriesForm";
import { modelLabel } from "../lib/upscale";
import { useApp } from "../store";
import type { UpscaleOptions } from "../types";

type Section = Record<string, unknown>;

const FAMILIES: { value: string; label: string }[] = [
  { value: "minimax_h3_*", label: "MiniMax H3 (any)" },
  { value: "fasth3_*", label: "FastH3 (any)" },
  { value: "ltx2*", label: "LTX-2 (any)" },
  { value: "wan22_*", label: "Wan 2.2 (any)" },
  { value: "*", label: "any other model" },
];

const SCALES = ["auto", "1.5", "2", "3", "4"];
const DETAILS = [
  { value: "", label: "as rendered (the default)" },
  { value: "1", label: "a little more detail" },
  { value: "2", label: "more detail (can drift from the take)" },
];

/** Whether `pattern` (an id or a glob) covers target `id`. */
export function covers(pattern: string, id: string): boolean {
  const re = new RegExp(`^${pattern.replace(/[.+^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*").replace(/\?/g, ".")}$`);
  return re.test(id);
}

export function MasterRecipe({ ep, raw, onChange }: { ep: string; raw: Raw; onChange: (next: Raw) => void }) {
  const targets = useApp((s) => s.targets);
  const [opts, setOpts] = useState<UpscaleOptions | null>(null);
  useEffect(() => {
    api().upscaleOptions(ep).then(setOpts).catch(() => setOpts(null));
  }, [ep]);

  const secs = (getPath(raw, ["upscale", "master", "targets"]) ?? {}) as Record<string, Section>;
  const keys = Object.keys(secs);
  const video = (targets?.targets ?? []).filter((t) => t.kind === "video" && !t.draft);
  const write = (next: Record<string, Section>) =>
    onChange(setPath(raw, ["upscale", "master", "targets"], Object.keys(next).length ? next : undefined));
  const setSec = (key: string, sec: Section) => write({ ...secs, [key]: sec });
  const rename = (from: string, to: string) => {
    if (!to || to === from || secs[to]) return;
    write(Object.fromEntries(keys.map((k) => (k === from ? [to, secs[k]] : [k, secs[k]]))));
  };
  const finish = (getPath(raw, ["upscale", "master", "finish"]) ?? {}) as Section;
  const pixelModels = opts?.pixel.models ?? [];
  const latentFor = (pattern: string) => Object.entries(opts?.latent ?? {}).filter(([id, r]) => r && covers(pattern, id));
  const free = [...FAMILIES.map((f) => f.value), ...video.map((t) => t.id)].filter((v) => !secs[v]);

  return (
    <div className="h3-col" style={{ gap: 8 }}>
      <span className="h3-small"><b>How each model's shots are upscaled</b></span>
      <span className="h3-small h3-muted">
        A shot goes through the row for its video model: its exact id first, then the closest family, then "any other model".
        Re-sampling runs the take through its own model again at the bigger size (the best detail, where the model can);
        an upscale model or SeedVR2 works on the pictures alone.
      </span>
      {!keys.length && <div className="h3-note h3-small">No rows yet: every shot would be a gap. Add one, or use the standard settings.</div>}
      {keys.map((key) => {
        const sec = secs[key];
        const method = (sec.method as string) ?? "latent";
        const canResample = latentFor(key).length > 0 || !opts;
        const scale = sec.scale == null ? "" : String(sec.scale);
        const then = (sec.then as string) ?? "";
        const problem = sec.scale === "auto" && then ? 'Scale "auto" is for a re-sample alone: pick a scale, or nothing after.' : "";
        const set = (patch: Section) => {
          const n: Section = { ...sec, ...patch };
          for (const [k, v] of Object.entries(patch)) if (v === undefined || v === "") delete n[k];
          setSec(key, n);
        };
        return (
          <div key={key} className="h3-col" style={{ gap: 6, padding: 8, border: "1px solid var(--h3-border)", borderRadius: 4 }}>
            <div className="h3-row h3-wrap" style={{ gap: 6 }}>
              <span className="h3-small">For</span>
              <select className="h3-in" value={key} onChange={(e) => rename(key, e.target.value)}>
                {[key, ...free].map((v) => (
                  <option key={v} value={v}>{FAMILIES.find((f) => f.value === v)?.label ?? video.find((t) => t.id === v)?.label ?? v}</option>
                ))}
              </select>
              <span className="h3-small">by</span>
              <select className="h3-in" value={method} onChange={(e) => {
                const m = e.target.value;
                set(m === "latent" ? { method: m, pixel_model: undefined, seedvr2_model: undefined }
                  : m === "pixel" ? { method: m, scale: undefined, then: undefined, then_scale: undefined, detail: undefined, pixel_model: (sec.pixel_model as string) || opts?.pixel.default || "RealESRGAN_x2.pth" }
                    : { method: m, scale: undefined, then: undefined, then_scale: undefined, detail: undefined, seedvr2_model: (sec.seedvr2_model as string) || "7b" });
              }}>
                <option value="latent" disabled={!canResample}>re-sampling with its own model{canResample ? "" : " (it can't)"}</option>
                <option value="pixel">an upscale model</option>
                <option value="seedvr2">SeedVR2</option>
              </select>
              <span className="h3-grow" />
              <button className="h3-link" title="Remove this row" onClick={() => write(Object.fromEntries(keys.filter((k) => k !== key).map((k) => [k, secs[k]])))}>×</button>
            </div>
            {method === "latent" && (
              <div className="h3-row h3-wrap" style={{ gap: 6 }}>
                <span className="h3-small">at</span>
                <select className="h3-in" value={SCALES.includes(scale) ? scale : scale ? "__n" : ""}
                  onChange={(e) => set({ scale: e.target.value === "auto" ? "auto" : e.target.value === "" ? undefined : e.target.value === "__n" ? 2 : Number(e.target.value) })}>
                  <option value="">its default scale</option>
                  <option value="auto">auto: just enough for the delivery</option>
                  {SCALES.slice(1).map((s) => <option key={s} value={s}>{s}x</option>)}
                  {scale && !SCALES.includes(scale) && <option value="__n">{scale}x</option>}
                </select>
                <select className="h3-in" value={sec.detail == null ? "" : String(sec.detail)}
                  onChange={(e) => set({ detail: e.target.value === "" ? undefined : Number(e.target.value) })}>
                  {DETAILS.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
                </select>
                <span className="h3-small">then</span>
                <select className="h3-in" value={then} onChange={(e) => set({ then: e.target.value || undefined, then_scale: e.target.value ? sec.then_scale : undefined })}>
                  <option value="">nothing</option>
                  <option value="seedvr2">SeedVR2</option>
                  {[...new Set([...pixelModels, ...(then && then !== "seedvr2" ? [then] : [])])].map((m) => <option key={m} value={m}>{modelLabel(m)}</option>)}
                </select>
              </div>
            )}
            {method === "pixel" && (
              <div className="h3-row h3-wrap" style={{ gap: 6 }}>
                <span className="h3-small">model</span>
                <select className="h3-in" value={(sec.pixel_model as string) ?? ""} onChange={(e) => set({ pixel_model: e.target.value || undefined })}>
                  {[...new Set([...pixelModels, ...(sec.pixel_model ? [sec.pixel_model as string] : [])])].map((m) => <option key={m} value={m}>{modelLabel(m)}{pixelModels.includes(m) ? "" : " (not installed)"}</option>)}
                  {!pixelModels.length && !sec.pixel_model && <option value="">no upscale models found</option>}
                </select>
              </div>
            )}
            {method === "seedvr2" && (
              <div className="h3-row h3-wrap" style={{ gap: 6 }}>
                <span className="h3-small">model</span>
                <select className="h3-in" value={(sec.seedvr2_model as string) ?? "7b"} onChange={(e) => set({ seedvr2_model: e.target.value })}>
                  <option value="7b">7B (better, slower)</option>
                  <option value="3b">3B (quicker)</option>
                </select>
              </div>
            )}
            {problem && <span className="h3-small h3-err">{problem}</span>}
          </div>
        );
      })}
      <div className="h3-row h3-wrap" style={{ gap: 6 }}>
        <button className="h3-btn" disabled={!free.length} onClick={() => {
          const k = free.find((v) => v === "*") ?? free[0];
          setSec(k, k.startsWith("minimax_h3") || k.startsWith("ltx2") ? { method: "latent", scale: "auto" } : { method: "pixel", pixel_model: opts?.pixel.default || "RealESRGAN_x2.pth" });
        }}><i className="pi pi-plus" /> A model</button>
        <button className="h3-btn" title="H3: re-sampled at the size that covers the delivery; LTX-2: re-sampled 2x; Wan: SeedVR2 7B; anything else: RealESRGAN x2"
          onClick={() => {
            if (keys.length && !window.confirm("Replace these rows with the standard settings?")) return;
            write(structuredClone(MASTER_TARGETS) as Record<string, Section>);
          }}>Use the standard settings</button>
      </div>
      <label className="h3-row h3-small" title="Keep the take's own colours and shapes from the source, only the fine detail from the upscale: an upscale can't drift in colour">
        <input type="checkbox" checked={finish.frequency_split === true}
          onChange={(e) => onChange(setPath(raw, ["upscale", "master", "finish", "frequency_split"], e.target.checked ? true : undefined))} />
        Keep the take's own colours (only the fine detail from the upscale)
      </label>
    </div>
  );
}
