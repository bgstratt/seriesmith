// A shot's length: the lengths offered (H3's grid, each with what it suits), or
// any length typed in (Custom…), as SizePicker does a size. With the model's
// template, what it renders is said under it: rounded up onto its frame grid,
// capped at its longest. Shared by the shot form and Simple mode.

import { useState } from "react";
import { DURATIONS } from "../lib/shotForm";
import { snapLength } from "../lib/simple";
import type { TargetTemplate } from "../types";

const CUSTOM = "__custom__";

export function LengthPicker(p: {
  value: string;
  onChange: (v: string) => void;
  /** offer `auto` (as long as the dialogue needs) */
  auto?: boolean;
  /** offer `model` (the video model chooses: LTX-2) */
  model?: boolean;
  /** an empty choice, so called ("—": the sequence's or the series' default) */
  empty?: string;
  /** the picked model's frame grid, to say what it renders */
  template?: TargetTemplate;
  /** the series' fps, for a model that renders at it */
  fps?: number;
  /** the model's short name, for "its longest" */
  short?: string;
  /** just the seconds in the list, not what each suits (a narrow row) */
  compact?: boolean;
}) {
  const offered = DURATIONS.filter((d) => (d.value !== "auto" || p.auto) && (d.value !== "model" || p.model));
  const listed = (v: string) => offered.some((d) => d.value === v) || (v === "" && p.empty !== undefined);
  const [custom, setCustom] = useState(() => !listed(p.value));
  const pick = (v: string) => {
    if (v === CUSTOM) {
      setCustom(true);
      const n = Number(p.value);
      p.onChange(p.value && Number.isFinite(n) && n > 0 ? p.value : "3");
    } else {
      setCustom(false);
      p.onChange(v);
    }
  };
  const snap = p.template ? snapLength(p.value, p.template, p.fps ?? 24) : null;
  const note = !snap ? "" : snap.capped ? `${snap.seconds} s: ${p.short ?? "the model"}'s longest`
    : Math.abs(snap.seconds - Number(p.value)) > 0.005 ? `${p.short ?? "the model"} renders ${snap.seconds} s` : "";
  return (
    <div className="h3-col" style={{ gap: 2 }}>
      <div className="h3-row h3-wrap" style={{ gap: 4 }}>
        <select className="h3-in" value={custom ? CUSTOM : p.value} onChange={(e) => pick(e.target.value)}>
          {p.empty !== undefined && <option value="">{p.empty}</option>}
          {offered.map((d) => <option key={d.value} value={d.value}>{p.compact ? d.label.split(" — ")[0] : d.label}</option>)}
          <option value={CUSTOM}>Custom…</option>
        </select>
        {custom && (
          <span className="h3-row" style={{ gap: 3 }}>
            <input className="h3-in" style={{ width: 64 }} inputMode="decimal" autoFocus value={p.value}
              title="Seconds" onChange={(e) => p.onChange(e.target.value.replace(/[^\d.]/g, ""))} />
            <span className="h3-small h3-muted">s</span>
          </span>
        )}
      </div>
      {note && <span className="h3-small h3-muted">{note}</span>}
    </div>
  );
}
