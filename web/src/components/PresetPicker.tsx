// Presets as pictures (GET /seriesmith/presets): a tile per preset, grouped,
// each with its sample picture when one is made. Picking one hands its text to
// the field it serves, which stays editable: the preset is a start, not a lock.
// The edit window's Relight and the series form's Look use it.

import { useEffect, useState } from "react";
import { api } from "../host";
import { loadPresets } from "../actions";
import { useApp } from "../store";
import type { RelightWording } from "../types";

export interface PresetTile {
  id: string;
  label: string;
  group: string;
  text: string;
  /** the sample picture's name (GET /seriesmith/presets/image), when made */
  image?: string;
}

const GROUP_LABEL: Record<string, string> = {
  time: "Time of day", weather: "Weather", light: "Light", portrait: "Portrait light",
  "live action": "Live action", animation: "Animation", illustration: "Illustration",
};

/** The relight presets for a ref of `kind`, in its wording (a plate's or a figure's). */
export function useRelightTiles(kind: string): PresetTile[] {
  const presets = useApp((s) => s.presets);
  useEffect(() => { void loadPresets(); }, []);
  const wording: RelightWording = kind === "location" ? "place" : "subject";
  return (presets?.relight ?? [])
    .filter((p) => p.for.includes(wording) && p.texts[wording])
    .map((p) => ({ id: p.id, label: p.label, group: p.group, text: p.texts[wording]!, image: p.images[wording] }));
}

/** The look presets, as tiles. */
export function useLookTiles(): PresetTile[] {
  const presets = useApp((s) => s.presets);
  useEffect(() => { void loadPresets(); }, []);
  return (presets?.look ?? []).map((p) => ({ id: p.id, label: p.label, group: p.group, text: p.text, image: p.image }));
}

/**
 * The tiles, grouped. `value` is the field's text: the tile whose text it is
 * shows as picked. `square`: figures (a character's view) are drawn square,
 * places and looks wide.
 */
export function PresetPicker({ tiles, value, onPick, square = false, title, open: open0 = true }: {
  tiles: PresetTile[];
  value: string;
  onPick: (text: string) => void;
  square?: boolean;
  title?: string;
  open?: boolean;
}) {
  const [open, setOpen] = useState(open0);
  if (!tiles.length) return null;
  const groups = [...new Set(tiles.map((t) => t.group))];
  const picked = tiles.find((t) => t.text === value.trim());
  const w = square ? 76 : 112;
  const h = square ? 76 : 63;
  return (
    <div className="h3-col sm-presets" style={{ gap: 4 }}>
      <button className="h3-link h3-small" style={{ alignSelf: "flex-start" }} onClick={() => setOpen(!open)}
        title="Presets fill the text below; you can still edit it, or write your own">
        <i className={`pi ${open ? "pi-chevron-down" : "pi-chevron-right"}`} /> {title ?? "Presets"}
        {picked ? <span className="h3-muted"> · {picked.label}</span> : null}
      </button>
      {open && groups.map((g) => (
        <div key={g} className="h3-col" style={{ gap: 2 }}>
          <span className="h3-small h3-muted">{GROUP_LABEL[g] ?? g}</span>
          <div className="h3-row" style={{ gap: 6, overflowX: "auto", paddingBottom: 4 }}>
            {tiles.filter((t) => t.group === g).map((t) => {
              const on = picked?.id === t.id;
              return (
                <button key={t.id} type="button" title={t.text} onClick={() => onPick(t.text)}
                  className={`sm-preset${on ? " h3-on" : ""}`}
                  style={{ flex: "0 0 auto", width: w, padding: 0, border: `2px solid ${on ? "var(--h3-primary)" : "var(--h3-border)"}`,
                    borderRadius: 8, overflow: "hidden", background: "var(--h3-card, transparent)", cursor: "pointer", textAlign: "left" }}>
                  {t.image
                    ? <img src={api().presetImageUrl(t.image)} alt="" loading="lazy" style={{ display: "block", width: w, height: h, objectFit: "cover" }} />
                    : <div style={{ width: w, height: h, background: "linear-gradient(135deg, var(--h3-chip), transparent)" }} />}
                  <div className="h3-small" style={{ padding: "3px 6px", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{t.label}</div>
                </button>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
