// The gallery: every picture of the episode's refs, large. A grid with a
// section per ref (every candidate, the live one badged), and a viewer that
// steps through the grid with the arrow keys. Opened from the Refs tab:
// double-click a ref (on it), a group's head (on that group), or Gallery.

import { useEffect, useMemo, useRef } from "react";
import { closeGallery, copyText, openImageCompare, pickRef, updateGallery } from "../actions";
import { isTyping } from "../cutActions";
import { api } from "../host";
import { GALLERY_GROUPS, gallerySections, type GalleryItem, type GallerySection } from "../lib/gallery";
import { fmtWhen, shortName, tn } from "../lib/format";
import { keyframeSource } from "../lib/keyframes";
import { PANO_VIEW, TOUR_VIEW, groupOf, pickedOf, viewLabel } from "../lib/refs";
import { useApp, type GalleryState } from "../store";
import { FloatingWindow, type Rect } from "./FloatingWindow";
import { FullscreenButton, toggleFullscreen } from "./Viewer";

const RECT_KEY = "seriesmith.gallery.rect";

function defaultGalleryRect(): Rect {
  const W = window.innerWidth || 1280;
  const H = window.innerHeight || 800;
  return { x: 24, y: 40, w: Math.max(480, W - 48), h: Math.max(360, H - 80) };
}

export function Gallery() {
  const g = useApp((s) => s.gallery);
  const ep = useApp((s) => s.ep);
  if (!g || !ep) return null;
  return <GalleryWindow ep={ep} g={g} />;
}

function GalleryWindow({ ep, g }: { ep: string; g: GalleryState }) {
  const refs = useApp((s) => s.refs[ep]);
  const pass = useApp((s) => s.pass);
  const winRef = useRef<HTMLDivElement>(null);
  const sections = useMemo(
    () => gallerySections(refs ?? [], g, pass),
    // the scope's fields, not `g`: moving through it changes `g` too
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [refs, g.group, g.ref, g.picksOnly, g.series, pass],
  );
  const items = useMemo(() => sections.flatMap((s) => s.items), [sections]);
  const idx = g.open ? items.findIndex((i) => i.key === g.open) : -1;
  // a picture discarded (or picked out of "picks only") while open: back to the grid
  const open = idx >= 0 ? items[idx] : null;

  const step = (d: number) => {
    if (!items.length) return;
    const cur = items.findIndex((i) => i.key === (g.open ?? g.at));
    const k = items[cur < 0 ? 0 : Math.min(items.length - 1, Math.max(0, cur + d))].key;
    updateGallery(open ? { open: k, at: k } : { at: k });
  };

  // focus comes in with it, so the arrows work before a click
  useEffect(() => winRef.current?.focus(), []);

  // keys while focus is inside it (ComfyUI owns them otherwise), stopped here
  // so ComfyUI's window-level shortcuts don't see them
  const keys = useRef<(e: KeyboardEvent) => void>(() => {});
  keys.current = (e) => {
    if (isTyping(e.target) || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === "Escape") {
      if (document.fullscreenElement) return; // the browser's: leaves full screen
      if (open) updateGallery({ open: null });
      else closeGallery();
    } else if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
      step(e.key === "ArrowLeft" ? -1 : 1);
    } else if (e.key === "Home" || e.key === "End") {
      if (items.length) {
        const k = items[e.key === "Home" ? 0 : items.length - 1].key;
        updateGallery(open ? { open: k, at: k } : { at: k });
      }
    } else if (e.key === "Enter" && !open && g.at) {
      updateGallery({ open: g.at });
    } else if (e.key === "f" || e.key === "F") {
      toggleFullscreen(winRef.current);
    } else return;
    e.preventDefault();
    e.stopPropagation();
  };
  useEffect(() => {
    const el = winRef.current;
    if (!el) return;
    const h = (e: KeyboardEvent) => keys.current(e);
    el.addEventListener("keydown", h);
    return () => el.removeEventListener("keydown", h);
  }, []);

  const scopeRef = g.ref ? refs?.find((r) => r.id === g.ref) : undefined;
  const head = (
    <>
      <b>Gallery</b>
      <span className="h3-row h3-wrap" style={{ gap: 4 }}>
        <button className={`h3-chip${!g.group && !g.ref ? " h3-on" : ""}`} onClick={() => updateGallery({ group: null, ref: null, open: null })}>
          Everything
        </button>
        {GALLERY_GROUPS.map((x) => (
          <button key={x.id} className={`h3-chip${g.group === x.id && !g.ref ? " h3-on" : ""}`}
            onClick={() => updateGallery({ group: x.id, ref: null, open: null })}>
            {x.label}
          </button>
        ))}
        {g.ref && (
          <button className="h3-chip h3-on" title="Show its whole group"
            onClick={() => updateGallery({ ref: null, group: scopeRef ? groupOf(scopeRef) as GalleryState["group"] : null })}>
            {scopeRef?.name ?? g.ref} <i className="pi pi-times" />
          </button>
        )}
      </span>
      <span className="h3-grow" />
      <label className="h3-row h3-small" style={{ gap: 4 }} title="Only the picture each ref uses now">
        <input type="checkbox" checked={g.picksOnly} onChange={(e) => updateGallery({ picksOnly: e.target.checked })} /> live only
      </label>
      {!g.ref && (
        <label className="h3-row h3-small" style={{ gap: 4 }} title="Every ref in the series config, not just those this episode uses">
          <input type="checkbox" checked={g.series} onChange={(e) => updateGallery({ series: e.target.checked })} /> whole series
        </label>
      )}
      <span className="h3-muted h3-small">{open ? `${idx + 1} / ${items.length}` : `${items.length} picture${items.length === 1 ? "" : "s"}`}</span>
      <FullscreenButton />
      <button className="h3-btn h3-icon" title="Close (Esc)" onClick={closeGallery}><i className="pi pi-times" /></button>
    </>
  );

  return (
    <FloatingWindow storageKey={RECT_KEY} defaultRect={defaultGalleryRect} head={head} winRef={winRef} className="h3-gallery" minW={480} minH={360}>
      {!refs && <div className="h3-empty-state">Loading the refs…</div>}
      {refs && open && <GalleryViewer ep={ep} item={open} prev={idx > 0} next={idx < items.length - 1} step={step} />}
      {refs && !open && <GalleryGrid ep={ep} sections={sections} at={g.at} />}
    </FloatingWindow>
  );
}

function GalleryGrid({ ep, sections, at }: { ep: string; sections: GallerySection[]; at: string | null }) {
  const scrollRef = useRef<HTMLDivElement>(null);
  // the cursor stays in view: coming back from the viewer, and as the arrows move it
  useEffect(() => {
    if (!at) return;
    const el = scrollRef.current?.querySelector(`[data-key="${CSS.escape(at)}"]`);
    el?.scrollIntoView({ block: "nearest" });
  }, [at]);
  if (!sections.length) return <div className="h3-empty-state">No pictures here yet.</div>;
  return (
    <div className="h3-scroll h3-gal-grid" ref={scrollRef}>
      {sections.map((s) => {
        const wide = s.ref.kind === "location" || groupOf(s.ref) === "keyframes";
        return (
          <section key={s.ref.id} className="h3-gal-sec">
            <div className="h3-row h3-gal-sec-head">
              <button className="h3-link" title="Only this ref" onClick={() => updateGallery({ ref: s.ref.id, open: null })}>
                <b>{s.ref.name}</b>
              </button>
              <span className="h3-muted h3-small">
                {[
                  `${s.items.length} picture${s.items.length === 1 ? "" : "s"}`,
                  s.queued ? `${s.queued} on the way` : "",
                  s.failed ? `${s.failed} failed` : "",
                ].filter(Boolean).join(" · ")}
              </span>
            </div>
            <div className={`h3-gal-tiles${wide ? " h3-gal-wide" : ""}`}>
              {s.items.map((it) => (
                <button key={it.key} data-key={it.key} className={`h3-gal-tile${it.key === at ? " h3-sel" : ""}${it.live ? " h3-live" : ""}`}
                  title={`${tileLabel(it)}${it.live ? " · live" : ""}${it.take.seed ? ` · seed ${it.take.seed}` : ""}`}
                  onClick={() => updateGallery({ open: it.key, at: it.key })}>
                  <img src={api().thumbUrl(ep, it.file, 320)} alt={tileLabel(it)} loading="lazy" draggable={false} />
                  <span className="h3-thumb-label">{tileLabel(it)}</span>
                  {it.live && <span className="h3-cand-live">live</span>}
                </button>
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}

function tileLabel(it: GalleryItem): string {
  return [viewLabel(it.view), tn(it.take.take)].filter(Boolean).join(" · ");
}

function GalleryViewer({ ep, item, prev, next, step }: {
  ep: string; item: GalleryItem; prev: boolean; next: boolean; step: (d: number) => void;
}) {
  const { ref: r, view, take: t } = item;
  const busy = useApp((s) => !!s.busy[`refpick|${r.id}`]);
  const url = api().refFileUrl(ep, item.file);
  const pickable = view !== PANO_VIEW && view !== TOUR_VIEW;
  const picked = pickable ? pickedOf(r, view) : null;
  const refs = t.references ?? [];
  return (
    <div className="h3-gal-view">
      <div className="h3-gal-stage">
        <img className="h3-still" src={url} alt={tileLabel(item)} draggable={false} />
        {prev && <button className="h3-gal-nav h3-gal-prev" title="Previous (←)" onClick={() => step(-1)}><i className="pi pi-chevron-left" /></button>}
        {next && <button className="h3-gal-nav h3-gal-next" title="Next (→)" onClick={() => step(1)}><i className="pi pi-chevron-right" /></button>}
      </div>
      <aside className="h3-gal-info h3-col">
        <div className="h3-row h3-wrap" style={{ gap: 6 }}>
          <b>{r.name}</b>
          <span className="h3-muted">{tileLabel(item)}</span>
          {item.live && <span className="h3-badge h3-b-ok">live</span>}
        </div>
        <div className="h3-row h3-wrap" style={{ gap: 6 }}>
          {pickable && (
            <button className="h3-btn h3-primary" disabled={item.live || busy}
              title={item.live ? "Already the live file" : `Make ${tn(t.take)} the picture renders use (${r.path})`}
              onClick={() => void pickRef(r.id, view, t.take)}>
              <i className="pi pi-check" /> {item.live ? "Live" : "Pick"}
            </button>
          )}
          {picked != null && !item.live && (
            <button className="h3-btn" title={`Open ${tn(t.take)} (A) against the live ${tn(picked)} (B)`}
              onClick={() => openImageCompare(r.id, view, t.take, picked)}>
              <i className="pi pi-clone" /> Compare with live
            </button>
          )}
          <a className="h3-btn" href={url} download={item.file.split(/[\\/]/).pop()} title={`Save ${item.file}`}>
            <i className="pi pi-download" /> Download
          </a>
          {t.prompt && (
            <button className="h3-btn" onClick={() => void copyText(t.prompt!, "Prompt")}>
              <i className="pi pi-copy" /> Copy prompt
            </button>
          )}
        </div>
        <div className="h3-kv">
          {t.source === "generated" && (
            <>
              <span>drawn</span>
              <span>
                {refs.length ? (
                  <>
                    edited from{" "}
                    {refs.map((x, i) => (
                      <span key={i}>
                        {i > 0 && ", "}
                        {x.id ? (
                          <button className="h3-link" title="Its pictures"
                            onClick={() => updateGallery({ ref: x.id!, open: null, at: null })}>
                            {x.name || x.id}{x.view ? ` (${viewLabel(x.view)})` : ""}
                          </button>
                        ) : (x.name || "a reference")}
                      </span>
                    ))}
                  </>
                ) : "from the prompt alone"}
              </span>
            </>
          )}
          {t.source === "edited" && t.edit && (
            <><span>edited</span><span>{t.edit.take != null ? `${tn(t.edit.take)}: ` : ""}“{t.edit.instruction}”</span></>
          )}
          {t.source === "imported" && <><span>imported</span><span>{t.original_name ?? "a file"}</span></>}
          {keyframeSource(t) && <><span>from</span><span>{keyframeSource(t)}</span></>}
          {t.target && <><span>model</span><span>{t.target}</span></>}
          {t.model && <><span>file</span><span title={t.model}>{shortName(t.model, 40)}</span></>}
          {t.seed && <><span>seed</span><span className="h3-mono">{t.seed}</span></>}
          {(t.steps != null || (t.width && t.height)) && (
            <>
              <span>settings</span>
              <span>
                {[
                  t.steps != null ? `${t.steps} steps` : "",
                  t.cfg != null ? `cfg ${t.cfg}` : "",
                  ...Object.entries(t.params ?? {}).map(([k, v]) => `${k} ${v}`),
                  t.width && t.height ? `${t.width}x${t.height}` : "",
                ].filter(Boolean).join(" · ")}
              </span>
            </>
          )}
          {t.finished && <><span>made</span><span>{fmtWhen(t.finished)}</span></>}
          {t.note && <><span>note</span><span>{t.note}</span></>}
        </div>
        {t.prompt && <div className="h3-gal-prompt h3-small">{t.prompt}</div>}
      </aside>
    </div>
  );
}
