// The render size picker: width and height boxes, empty for the shot's own size
// (shown greyed in them), and beside them the sizes offered to fill them from
// (those the target takes as they are, or snaps), checked against its grid as
// you type. Shared by the New take dialog (this take only) and the inspector's
// override.

import { COMMON_SIZES, SIZE_CHOICES, sizeCheck, type SizeRule } from "../lib/size";
import { PickMenu } from "./PickMenu";

const OWN = "__own__";

/** The sizes offered under `rule`: H3's and the common ones, each once, those
 * a refusing grid would refuse left out. */
export function offeredSizes(rule: SizeRule): { value: string; label: string }[] {
  const out: { value: string; label: string }[] = [];
  const add = (w: number, h: number, label: string) => {
    const value = `${w}x${h}`;
    if (out.some((o) => o.value === value)) return;
    if (!rule.snap && rule.multiple > 1 && (w % rule.multiple || h % rule.multiple)) return;
    out.push({ value, label });
  };
  for (const q of COMMON_SIZES) add(q.width, q.height, q.label);
  for (const s of SIZE_CHOICES) {
    const [w, h] = s.split("x").map(Number);
    add(w, h, `${w}×${h}`);
  }
  return out;
}

export function SizePicker(p: {
  /** "" = the shot's own size; else "WxH" (or text being typed) */
  value: string;
  onChange: (v: string) => void;
  /** the shot's own size, "WxH" ("" when unknown) */
  own: string;
  /** what the empty choice is called: "the shot's", "built" */
  ownLabel: string;
  rule: SizeRule;
}) {
  const [w = "", h = ""] = p.value ? p.value.split(/[xX×]/) : [];
  const [ow, oh] = p.own ? p.own.split("x") : ["", ""];
  const put = (nw: string, nh: string) => p.onChange(nw || nh ? `${nw}x${nh}` : "");
  const check = sizeCheck(p.value, p.rule);
  const options = [{ value: OWN, label: `${p.ownLabel}${p.own ? ` (${p.own.replace("x", "×")})` : ""}` },
    ...offeredSizes(p.rule)];
  const tip = p.rule.multiple > 1 ? `, a multiple of ${p.rule.multiple}` : "";
  return (
    <div className="h3-col" style={{ gap: 2 }}>
      <div className="h3-row" style={{ gap: 4 }}>
        <input className="h3-in" style={{ width: 60 }} inputMode="numeric" placeholder={ow} value={w}
          title={`Width, pixels${tip}. Empty: ${p.ownLabel}`} onChange={(e) => put(e.target.value.replace(/\D/g, ""), h)} />
        <span className="h3-small">×</span>
        <input className="h3-in" style={{ width: 60 }} inputMode="numeric" placeholder={oh} value={h}
          title={`Height, pixels${tip}. Empty: ${p.ownLabel}`} onChange={(e) => put(w, e.target.value.replace(/\D/g, ""))} />
        <PickMenu label="sizes" options={options} title="A size to start from"
          onPick={(v) => p.onChange(v === OWN ? "" : v)} />
      </div>
      {check && <span className={`h3-small ${check.level === "err" ? "h3-err" : "h3-muted"}`}>{check.text}</span>}
    </div>
  );
}
