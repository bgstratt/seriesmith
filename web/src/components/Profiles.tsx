// Series settings' Profiles: the series config's named render profiles, each a
// set of choices a shot or a sequence takes with `profile: <name>` (a flashback,
// a dream, a close-up dialogue setup): words added to the look, a lens, and the
// model settings (video model, steps, LoRAs, sparse attention).

import { useEffect, useState } from "react";
import { loadPresets } from "../actions";
import { lorasText, lorasValue, profileNameOk, profilesOf, setProfile, type Profile } from "../lib/profiles";
import type { Raw } from "../lib/seriesForm";
import { useApp } from "../store";
import type { LookBuilderRow, Target } from "../types";
import { ModelOptions } from "./Targets";

const NO_ROWS: LookBuilderRow[] = [];

export function ProfilesSection({ raw, onChange, videoTargets }: {
  raw: Raw; onChange: (next: Raw) => void; videoTargets: Target[];
}) {
  const profiles = profilesOf(raw);
  const names = Object.keys(profiles);
  const rows = useApp((s) => s.presets?.look_builder) ?? NO_ROWS;
  const lenses = rows.find((r) => r.id === "lens")?.options ?? [];
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { void loadPresets(); }, []);

  const add = () => {
    const name = window.prompt("Name the profile (what a shot names with profile:), e.g. flashback")?.trim();
    if (!name) return;
    if (!profileNameOk(name)) return setErr("A profile's name takes letters, digits, _ and - only.");
    if (profiles[name]) return setErr(`There is already a profile “${name}”.`);
    setErr(null);
    onChange(setProfile(raw, name, {}));
  };
  const put = (name: string, p: Profile) => onChange(setProfile(raw, name, p));

  return (
    <details open={names.length > 0} className="sm-form-section">
      <summary>
        <b>Profiles</b>{" "}
        <span className="h3-small h3-muted">
          named sets of choices a shot or sequence takes with <code>profile:</code> (a flashback, a dream): look, lens, model
        </span>
      </summary>
      <div className="h3-col" style={{ gap: 8, marginTop: 6 }}>
        {names.map((name) => {
          const p = profiles[name];
          return (
            <div key={name} className="h3-card h3-col" style={{ gap: 6 }}>
              <div className="h3-row" style={{ gap: 6 }}>
                <b className="h3-grow"><code>profile: {name}</code></b>
                <button type="button" className="h3-btn h3-small h3-danger" title={`Remove the profile “${name}” (shots that name it then fail to build until you change them)`}
                  onClick={() => { if (confirm(`Remove the profile “${name}”?`)) onChange(setProfile(raw, name, null)); }}>
                  <i className="pi pi-trash" />
                </button>
              </div>
              <label className="h3-col h3-small" style={{ gap: 2 }}>
                <span title="Added to the series look for these shots, at the start of each shot's prompt">Look words</span>
                <textarea className="h3-in" rows={2} value={p.look ?? ""}
                  placeholder="a faded, desaturated memory with soft halation and a dreamy haze"
                  onChange={(e) => put(name, { ...p, look: e.target.value })} />
              </label>
              <div className="h3-row h3-wrap" style={{ gap: 8 }}>
                <label className="h3-row h3-small" style={{ gap: 4 }} title="The lens these shots are shot on (a shot's own lens: line still wins)">
                  Lens
                  <select className="h3-in" value={p.lens ?? ""} onChange={(e) => put(name, { ...p, lens: e.target.value })}>
                    <option value="">—</option>
                    {lenses.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
                  </select>
                </label>
                <label className="h3-row h3-small" style={{ gap: 4 }} title="The video model these shots render on">
                  Model
                  <select className="h3-in" value={p.target ?? ""} onChange={(e) => put(name, { ...p, target: e.target.value })}>
                    <option value="">(the shot's)</option>
                    <ModelOptions targets={videoTargets} />
                  </select>
                </label>
                <label className="h3-row h3-small" style={{ gap: 4 }} title="Sampler steps (empty: the model's own)">
                  Steps
                  <input className="h3-in" style={{ width: 56 }} inputMode="numeric" value={p.steps ?? ""}
                    onChange={(e) => {
                      const n = parseInt(e.target.value, 10);
                      put(name, { ...p, steps: Number.isFinite(n) && n > 0 ? n : undefined });
                    }} />
                </label>
                <label className="h3-row h3-small" style={{ gap: 4 }} title="Leave H3's sparse attention out: about 40% slower, a little smoother">
                  <input type="checkbox" checked={p.sla === "off"} onChange={(e) => put(name, { ...p, sla: e.target.checked ? "off" : undefined })} />
                  sla off
                </label>
              </div>
              <label className="h3-row h3-small" style={{ gap: 4 }} title="LoRA files, comma-separated, each with :strength if not 1; none for no LoRA (the full model)">
                LoRAs
                <LorasInput value={p.loras} onChange={(v) => put(name, { ...p, loras: v })} />
              </label>
            </div>
          );
        })}
        {err && <div className="h3-warn h3-small">{err}</div>}
        <button type="button" className="h3-btn h3-small" style={{ alignSelf: "flex-start" }} onClick={add}>
          <i className="pi pi-plus" /> Profile
        </button>
      </div>
    </details>
  );
}

/** The LoRA line: typed freely, read into the profile when it loses focus. */
function LorasInput({ value, onChange }: { value: unknown; onChange: (v: string[] | undefined) => void }) {
  const shown = lorasText(value);
  const [text, setText] = useState(shown);
  useEffect(() => setText(shown), [shown]);
  return (
    <input className="h3-in h3-grow" value={text} placeholder="none, or a.safetensors:0.6"
      onChange={(e) => setText(e.target.value)} onBlur={() => onChange(lorasValue(text))} />
  );
}
