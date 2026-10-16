// A shot's length: a box for seconds (or auto / model), and beside it the
// lengths offered (H3's grid, each with what it suits) to fill it from. Under
// it, what the length suits and, with the model's template, what it renders:
// rounded up onto its frame grid, capped at its longest. Shared by the shot
// form, the new episode wizard and Simple mode.

import { DURATIONS } from "../lib/shotForm";
import { snapLength } from "../lib/simple";
import type { TargetTemplate } from "../types";
import { PickMenu } from "./PickMenu";

const EMPTY = "__empty__";

export function LengthPicker(p: {
  value: string;
  onChange: (v: string) => void;
  /** offer `auto` (as long as the dialogue needs) */
  auto?: boolean;
  /** offer `model` (the video model chooses: LTX-2) */
  model?: boolean;
  /** what an empty box means ("the sequence's"): offered to go back to */
  empty?: string;
  /** the picked model's frame grid, to say what it renders */
  template?: TargetTemplate;
  /** the series' fps, for a model that renders at it */
  fps?: number;
  /** the model's short name, for "its longest" */
  short?: string;
  /** no line under it (a narrow row): what it suits goes in the box's tooltip */
  compact?: boolean;
}) {
  const offered = DURATIONS.filter((d) => (d.value !== "auto" || p.auto) && (d.value !== "model" || p.model));
  const v = p.value.trim();
  const listed = DURATIONS.find((d) => d.value === v);
  const suits = listed?.label.split(" — ")[1] ?? (v === "auto" ? "as long as the dialogue needs" : "");
  const bad = v !== "" && !listed && !(Number(v) > 0);
  const snap = p.template ? snapLength(v, p.template, p.fps ?? 24) : null;
  const who = p.short ?? "the model";
  const renders = !snap ? "" : snap.capped ? `${snap.seconds} s: ${who}'s longest`
    : Math.abs(snap.seconds - Number(v)) > 0.005 ? `${who} renders ${snap.seconds} s` : "";
  const note = bad ? "seconds, auto or model" : [suits, renders].filter(Boolean).join("; ");
  const options = [
    ...(p.empty !== undefined ? [{ value: EMPTY, label: `— ${p.empty}` }] : []),
    ...offered.map((d) => ({ value: d.value, label: p.compact ? d.label.split(" — ")[0] : d.label })),
  ];
  return (
    <div className="h3-col" style={{ gap: 2 }}>
      <div className="h3-row" style={{ gap: 4 }}>
        <input className="h3-in" style={{ width: 64 }} value={p.value} placeholder={p.empty !== undefined ? "—" : "3.04"}
          title={["Seconds" + (p.auto ? ", or auto" : "") + (p.model ? ", or model" : ""), p.compact ? note : ""].filter(Boolean).join(": ")}
          onChange={(e) => p.onChange(e.target.value)} />
        <span className="h3-small h3-muted">s</span>
        <PickMenu label="lengths" options={options} title="A length to start from"
          onPick={(x) => p.onChange(x === EMPTY ? "" : x)} />
      </div>
      {!p.compact && note && <span className={`h3-small ${bad ? "h3-err" : "h3-muted"}`}>{note}</span>}
    </div>
  );
}
