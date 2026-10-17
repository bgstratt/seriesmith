// The sidebars' head (Simple mode, the Shots tab, the Refs tab): what is open,
// as the panel's title, with a dropdown over it to switch, and "Browse and add
// new…" as its last choice. The name is cut off at the edge, never wrapped.

import type { ReactNode } from "react";

export const ADD_NEW = "__add_new__";

export function TitleSelect(p: {
  /** the small line above: "Project", the series' title */
  kicker: string;
  /** the title: what is open */
  name: string;
  value: string;
  options: { value: string; label: string; title?: string }[];
  onPick: (value: string) => void;
  /** the dropdown's name for a screen reader */
  label: string;
  /** a tooltip: the full name, the path */
  title?: string;
}) {
  return (
    <>
      <div className="sm-kicker">{p.kicker}</div>
      <span className="sm-project" title={p.title ?? p.name}>
        <span className="sm-project-name">{p.name}</span>
        <i className="pi pi-chevron-down sm-caret" />
        <select aria-label={p.label} className="sm-project-select" value={p.value}
          onChange={(e) => p.onPick(e.target.value)}>
          {!p.options.some((o) => o.value === p.value) && <option value={p.value}>{p.name}</option>}
          {p.options.map((o) => <option key={o.value} value={o.value} title={o.title}>{o.label}</option>)}
          <option value={ADD_NEW}>Browse and add new…</option>
        </select>
      </span>
    </>
  );
}

/** The head's frame: the title on the left, `side` (the mode switch, a few
 * buttons) on the right. */
export function PanelHead({ children, side }: { children: ReactNode; side?: ReactNode }) {
  return (
    <div className="sm-head">
      <div className="sm-head-main">{children}</div>
      {side && <div className="sm-head-side">{side}</div>}
    </div>
  );
}
