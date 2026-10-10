// Cast pictures where the cast is named: a small one (a character's face, a
// location's plate; lib/pictures.ts), a larger one on hover, and a picker that
// shows them all to choose from.

import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { api } from "../host";
import { initials, type Picture } from "../lib/pictures";

const Z = 2100; // above the floating windows

/** What a picker or a chip names: an id, its name, its picture. */
export interface Named {
  id: string;
  name: string;
  pic: Picture | null;
}

function urlOf(ep: string, pic: Picture): string {
  const u = api().fileUrl(ep, pic.path);
  return pic.version && u.includes("?") ? `${u}&v=${pic.version.slice(0, 10)}` : u;
}

/** A picture at `size` px: the face panel for a character's sheet, the whole
 * picture otherwise, or the initials when there's none (yet). */
export function Thumb({ ep, pic, name, size = 24, round = false }: {
  ep: string | null; pic: Picture | null; name: string; size?: number; round?: boolean;
}) {
  const [broken, setBroken] = useState(false);
  const url = ep && pic ? urlOf(ep, pic) : null;
  useEffect(() => setBroken(false), [url]);
  const box = {
    width: size, height: size, flex: "none", borderRadius: round ? "50%" : 3, overflow: "hidden",
    background: "var(--h3-bg3)", display: "inline-flex", alignItems: "center", justifyContent: "center",
  } as const;
  if (!url || broken) {
    return <span style={{ ...box, fontSize: Math.max(9, size * 0.38), color: "var(--h3-muted)" }}>{initials(name)}</span>;
  }
  return (
    <span style={{
      ...box, backgroundImage: `url("${url}")`, backgroundRepeat: "no-repeat",
      // the face: the sheet's last quarter, filling the box from its top
      backgroundSize: pic!.face ? "400% auto" : "cover",
      backgroundPosition: pic!.face ? "100% 25%" : "center",
    }}>
      <img src={url} alt="" style={{ display: "none" }} onError={() => setBroken(true)} />
    </span>
  );
}

/** `children`, with a larger picture beside the pointer while it's over them. */
export function Hover({ ep, item, children, big = 200 }: { ep: string | null; item: Named; children: ReactNode; big?: number }) {
  const [at, setAt] = useState<{ x: number; y: number } | null>(null);
  return (
    <span style={{ display: "inline-flex" }}
      onMouseEnter={(e) => setAt({ x: e.clientX, y: e.clientY })}
      onMouseMove={(e) => setAt({ x: e.clientX, y: e.clientY })}
      onMouseLeave={() => setAt(null)}>
      {children}
      {at && item.pic && ep && createPortal(
        <div className="h3-root sm-picture-hover" style={{
          position: "fixed", zIndex: Z, pointerEvents: "none",
          left: Math.min(at.x + 16, window.innerWidth - big - 24), top: Math.min(at.y + 16, window.innerHeight - big - 48),
          padding: 6, background: "var(--h3-bg2)", border: "1px solid var(--h3-border)", borderRadius: 4,
          boxShadow: "0 6px 18px rgba(0,0,0,0.35)",
        }}>
          <Thumb ep={ep} pic={item.pic} name={item.name} size={big} />
          <div className="h3-small" style={{ marginTop: 4, maxWidth: big }}>{item.name}{item.name !== item.id ? <span className="h3-muted"> ({item.id})</span> : null}</div>
        </div>,
        document.body,
      )}
    </span>
  );
}

/** A button that opens the options as pictures to pick one from. */
export function PicturePicker({ ep, options, onPick, label, title, none }: {
  ep: string | null; options: Named[]; onPick: (id: string) => void; label: ReactNode; title?: string;
  /** an option for "none" (its label), first */
  none?: string;
}) {
  const [open, setOpen] = useState<DOMRect | null>(null);
  const [q, setQ] = useState("");
  const btn = useRef<HTMLButtonElement>(null);
  const pop = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (!pop.current?.contains(e.target as Node) && !btn.current?.contains(e.target as Node)) setOpen(null);
    };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(null); };
    window.addEventListener("mousedown", close);
    window.addEventListener("keydown", esc);
    return () => { window.removeEventListener("mousedown", close); window.removeEventListener("keydown", esc); };
  }, [open]);
  const needle = q.trim().toLowerCase();
  const shown = needle ? options.filter((o) => o.id.includes(needle) || o.name.toLowerCase().includes(needle)) : options;
  const pick = (id: string) => { onPick(id); setOpen(null); setQ(""); };
  const W = 360;
  return (
    <>
      <button ref={btn} type="button" className="h3-btn" title={title}
        onClick={() => setOpen(open ? null : btn.current!.getBoundingClientRect())}>{label}</button>
      {open && createPortal(
        <div ref={pop} className="h3-root sm-picture-picker" style={{
          position: "fixed", zIndex: Z, width: W, maxHeight: 340, overflow: "auto",
          left: Math.max(8, Math.min(open.left, window.innerWidth - W - 8)),
          top: open.bottom + 340 < window.innerHeight ? open.bottom + 4 : Math.max(8, open.top - 344),
          padding: 8, background: "var(--h3-bg2)", border: "1px solid var(--h3-border)", borderRadius: 4,
          boxShadow: "0 6px 18px rgba(0,0,0,0.35)",
        }}>
          {options.length > 12 && (
            <input className="h3-in" autoFocus placeholder="Find by name" value={q} onChange={(e) => setQ(e.target.value)}
              style={{ width: "100%", marginBottom: 6 }} />
          )}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(76px, 1fr))", gap: 6 }}>
            {none !== undefined && (
              <button type="button" className="h3-btn sm-pick-tile" onClick={() => pick("")}
                style={{ flexDirection: "column", height: "auto", padding: 4, gap: 3 }}>
                <span style={{ width: 64, height: 64, display: "inline-flex", alignItems: "center", justifyContent: "center", color: "var(--h3-muted)" }}>—</span>
                <span className="h3-small" style={{ lineHeight: 1.15, textAlign: "center", whiteSpace: "normal" }}>{none}</span>
              </button>
            )}
            {shown.map((o) => (
              <button key={o.id} type="button" className="h3-btn sm-pick-tile" title={o.name !== o.id ? `${o.name} (${o.id})` : o.id}
                onClick={() => pick(o.id)} style={{ flexDirection: "column", height: "auto", padding: 4, gap: 3 }}>
                <Thumb ep={ep} pic={o.pic} name={o.name} size={64} />
                <span className="h3-small" style={{ lineHeight: 1.15, textAlign: "center", whiteSpace: "normal", overflowWrap: "anywhere" }}>{o.name}</span>
              </button>
            ))}
          </div>
          {!shown.length && none === undefined && <div className="h3-small h3-muted">{options.length ? "Nothing by that name." : "Nobody to add yet."}</div>}
        </div>,
        document.body,
      )}
    </>
  );
}
