// Presets as pictures (GET /seriesmith/presets): a tile per preset, grouped,
// each with its sample when one is made (a picture, or for a camera move a
// short clip that plays while the pointer is on it). Picking one hands its
// value to the field it serves, which stays editable: the preset is a start,
// not a lock. The edit window's Relight, the series form's Look and the shot
// form's Framing and Camera use it.

import { useEffect, useRef, useState } from "react";
import { api } from "../host";
import { deleteOwnPreset, loadPresets, openPresetPicture } from "../actions";
import { useApp } from "../store";
import type { RelightWording } from "../types";

export interface PresetTile {
  id: string;
  label: string;
  group: string;
  /** what picking it hands over (an instruction, a look line, a size, a move) */
  text: string;
  /** a second line under the label (a framing's "chest up") */
  sub?: string;
  /** the sample's name (GET /seriesmith/presets/image), when made: .jpg, or a camera move's .mp4 */
  image?: string;
  /** one of yours: it can be removed, and given a picture */
  own?: { kind: "look" | "relight"; rendering?: boolean; error?: string };
}

const GROUP_LABEL: Record<string, string> = {
  time: "Time of day", weather: "Weather", light: "Light", portrait: "Portrait light",
  yours: "Yours", "live action": "Live action", genre: "Genre", animation: "Animation", illustration: "Illustration",
  close: "Close", medium: "Medium", wide: "Wide", angle: "Angle",
  frame: "Still", dolly: "Dolly", lens: "Zoom", pivot: "Pan and tilt", slide: "Truck and pedestal",
  orbit: "Around", handheld: "Handheld and roll", lenses: "Lens",
};

function usePresets() {
  const presets = useApp((s) => s.presets);
  useEffect(() => { void loadPresets(); }, []);
  return presets;
}

/** The relight presets for a ref of `kind`, in its wording (a plate's or a figure's). */
export function useRelightTiles(kind: string): PresetTile[] {
  const presets = usePresets();
  const wording: RelightWording = kind === "location" ? "place" : "subject";
  return (presets?.relight ?? [])
    .filter((p) => p.for.includes(wording) && p.texts[wording])
    .map((p) => ({ id: p.id, label: p.label, group: p.group, text: p.texts[wording]!, image: p.images[wording],
      ...(p.own ? { own: { kind: "relight" as const, rendering: p.rendering, error: p.picture_error } } : {}) }));
}

/** The look presets, as tiles. */
export function useLookTiles(): PresetTile[] {
  const presets = usePresets();
  return (presets?.look ?? []).map((p) => ({ id: p.id, label: p.label, group: p.group, text: p.text, image: p.image,
    ...(p.own ? { own: { kind: "look" as const, rendering: p.rendering, error: p.picture_error } } : {}) }));
}

/** The framings: picking one hands over the `size:` value (its id). */
export function useFramingTiles(): PresetTile[] {
  const presets = usePresets();
  return (presets?.framing ?? []).map((p) => ({ id: p.id, label: p.label, group: p.group, text: p.id, sub: p.hint, image: p.image }));
}

/** The lenses a shot's `lens:` takes (core/framing.py LENSES): the look builder's Lens row;
 * picking one hands over its id. */
export function useLensTiles(): PresetTile[] {
  const presets = usePresets();
  const row = (presets?.look_builder ?? []).find((r) => r.id === "lens");
  if (!row) return [];
  return row.options.map((o) => ({ id: o.id, label: o.label, group: "lenses", text: o.id, image: o.image }));
}

/** The camera moves: picking one hands over the move (a `camera:` line's start). */
export function useCameraTiles(): PresetTile[] {
  const presets = usePresets();
  return (presets?.camera ?? []).map((p) => ({ id: p.id, label: p.label, group: p.group, text: p.move, image: p.image }));
}

/** A tile's sample: a picture, or a clip shown on its first frame and played while hovered. */
function Sample({ name, w, h, hover }: { name?: string; w: number; h: number; hover: boolean }) {
  const ref = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    const v = ref.current;
    if (!v) return;
    if (hover) void v.play().catch(() => {});
    else { v.pause(); v.currentTime = 0; }
  }, [hover]);
  if (!name) return <div style={{ width: w, height: h, background: "linear-gradient(135deg, var(--h3-chip), transparent)" }} />;
  const src = api().presetImageUrl(name);
  const style = { display: "block", width: w, height: h, objectFit: "cover" as const };
  return name.endsWith(".mp4")
    ? <video ref={ref} src={src} muted loop playsInline preload="metadata" style={style} />
    : <img src={src} alt="" loading="lazy" style={style} />;
}

/**
 * The tiles, grouped. `value` is the field's value: the tile it is shows as
 * picked (or `picked`, a tile's id, when the field holds more than the tile
 * gives, as a camera line does). `square`: figures are drawn square, places,
 * looks and shots wide.
 */
export function PresetPicker({ tiles, value, onPick, square = false, title, open: open0 = true, picked: pickedId, size = 1 }: {
  tiles: PresetTile[];
  value: string;
  onPick: (text: string) => void;
  square?: boolean;
  title?: string;
  open?: boolean;
  picked?: string | null;
  /** the tiles' scale (the shot form's are smaller) */
  size?: number;
}) {
  const [open, setOpen] = useState(open0);
  const [hover, setHover] = useState<string | null>(null);
  if (!tiles.length) return null;
  const groups = [...new Set(tiles.map((t) => t.group))];
  const picked = pickedId !== undefined ? tiles.find((t) => t.id === pickedId) : tiles.find((t) => t.text === value.trim());
  const w = Math.round((square ? 76 : 112) * size);
  const h = Math.round((square ? 76 : 63) * size);
  return (
    <div className="h3-col sm-presets" style={{ gap: 4 }}>
      <button type="button" className="h3-link h3-small" style={{ alignSelf: "flex-start" }} onClick={() => setOpen(!open)}
        title="Presets fill the field; you can still edit it, or write your own">
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
                  onMouseEnter={() => setHover(t.id)} onMouseLeave={() => setHover(null)}
                  className={`sm-preset${on ? " h3-on" : ""}`}
                  style={{ flex: "0 0 auto", width: w, padding: 0, border: `2px solid ${on ? "var(--h3-primary)" : "var(--h3-border)"}`,
                    borderRadius: 8, overflow: "hidden", background: "var(--h3-card, transparent)", cursor: "pointer", textAlign: "left" }}>
                  {t.image || !t.own
                    ? <Sample name={t.image} w={w} h={h} hover={hover === t.id} />
                    : <div className="h3-small h3-muted" style={{ width: w, height: h, padding: 4, overflow: "hidden", lineHeight: 1.2,
                        background: "linear-gradient(135deg, var(--h3-chip), transparent)" }}>{t.text}</div>}
                  <div className="h3-small h3-row" style={{ padding: "3px 6px", gap: 4 }}>
                    <span style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", flex: 1 }}>{t.label}</span>
                    {t.own?.rendering && <i className="pi pi-spin pi-spinner h3-muted" title="Its picture is rendering" />}
                    {t.own && (
                      <span role="button" tabIndex={0} className="h3-link"
                        title={t.own.error ? `The last render failed: ${t.own.error}. Give it a picture…` : `Give “${t.label}” a picture: render it, take one from your work, or import one`}
                        onClick={(e) => { e.stopPropagation(); openPresetPicture(t.own!.kind, t.id, t.label); }}
                        onKeyDown={(e) => { if (e.key === "Enter") { e.stopPropagation(); openPresetPicture(t.own!.kind, t.id, t.label); } }}>
                        <i className={`pi pi-image${t.own.error ? " h3-warn" : ""}`} />
                      </span>
                    )}
                    {t.own && (
                      <span role="button" tabIndex={0} className="h3-link" title={`Remove your ${t.own.kind} “${t.label}”`}
                        onClick={(e) => { e.stopPropagation(); void deleteOwnPreset(t.own!.kind, t.id, t.label); }}
                        onKeyDown={(e) => { if (e.key === "Enter") { e.stopPropagation(); void deleteOwnPreset(t.own!.kind, t.id, t.label); } }}>
                        ✕
                      </span>
                    )}
                  </div>
                  {t.sub && <div className="h3-small h3-muted" style={{ padding: "0 6px 3px", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{t.sub}</div>}
                </button>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
