// The gallery: every picture of the episode's refs, large. A grid (a section
// per ref, or one flow of them, each ref's pictures together), every candidate
// with the live one badged, and a picture opened over it that steps through
// the grid with the arrow keys and closes back to it. Opened from the Refs
// tab: double-click a ref (on it), a group's head (on that group), or Gallery.

import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import { closeGallery, copyText, pickRef, updateGallery } from "../actions";
import { isTyping } from "../cutActions";
import { api } from "../host";
import { GALLERY_GROUPS, gallerySections, itemAspect, type GalleryItem, type GallerySection } from "../lib/gallery";
import { fmtWhen, shortName, tn } from "../lib/format";
import { keyframeSource } from "../lib/keyframes";
import { PANO_VIEW, TOUR_VIEW, groupOf, pickedOf, takesOf, viewLabel } from "../lib/refs";
import { useApp, type GalleryState } from "../store";
import { FloatingWindow, type Rect } from "./FloatingWindow";
import { EpisodeSelect } from "./ShotsTab";
import { FullscreenButton, toggleFullscreen } from "./Viewer";

const RECT_KEY = "seriesmith.gallery.rect";
const LAYOUT_KEY = "seriesmith.gallery.layout";
const SIZE_KEY = "seriesmith.gallery.size";

type Layout = "sections" | "flow";
/** a row's height, px: the tiles fill each row at their own shapes */
const SIZES = { s: 140, m: 210, l: 320 } as const;
type Size = keyof typeof SIZES;

/**
 * Pictures load as they come within a screen of the grid's view, watched
 * against the grid's own scroll box: `loading="lazy"` measures against the
 * page, and the gallery scrolls inside a window, so it loaded hundreds at once.
 */
const NearRoot = createContext<HTMLElement | null>(null);

function useNear<T extends Element>(): [React.RefObject<T>, boolean] {
  const root = useContext(NearRoot);
  const ref = useRef<T>(null);
  const [near, setNear] = useState(() => typeof IntersectionObserver === "undefined");
  useEffect(() => {
    if (near || !root || !ref.current) return;
    const io = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) {
        setNear(true);
        io.disconnect();
      }
    }, { root, rootMargin: "100% 0px" });
    io.observe(ref.current);
    return () => io.disconnect();
  }, [near, root]);
  return [ref, near];
}

function defaultGalleryRect(): Rect {
  const W = window.innerWidth || 1280;
  const H = window.innerHeight || 800;
  return { x: 24, y: 40, w: Math.max(480, W - 48), h: Math.max(360, H - 80) };
}

/** A choice remembered in this browser. */
function usePref<T extends string>(key: string, allowed: readonly T[], fallback: T): [T, (v: T) => void] {
  const [v, setV] = useState<T>(() => {
    try {
      const x = localStorage.getItem(key) as T | null;
      return x && allowed.includes(x) ? x : fallback;
    } catch {
      return fallback;
    }
  });
  const set = (x: T) => {
    setV(x);
    try {
      localStorage.setItem(key, x);
    } catch {
      /* private window: until reload */
    }
  };
  return [v, set];
}

export function Gallery() {
  const g = useApp((s) => s.gallery);
  const ep = useApp((s) => s.ep);
  if (!g) return null;
  return <GalleryWindow ep={ep} g={g} />;
}

function GalleryWindow({ ep, g }: { ep: string | null; g: GalleryState }) {
  const refs = useApp((s) => (ep ? s.refs[ep] : undefined));
  const pass = useApp((s) => s.pass);
  const winRef = useRef<HTMLDivElement>(null);
  const [layout, setLayout] = usePref<Layout>(LAYOUT_KEY, ["sections", "flow"], "sections");
  const [size, setSize] = usePref<Size>(SIZE_KEY, ["s", "m", "l"], "m");
  const [compare, setCompare] = useState(false);
  const sections = useMemo(
    () => gallerySections(refs ?? [], g, pass),
    // the scope's fields, not `g`: moving through it changes `g` too
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [refs, g.group, g.ref, g.picksOnly, g.series, pass],
  );
  const items = useMemo(() => sections.flatMap((s) => s.items), [sections]);
  const idx = g.open ? items.findIndex((i) => i.key === g.open) : -1;
  // a picture discarded (or picked out of "live only") while open: back to the grid
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
    } else if (e.key === "c" || e.key === "C") {
      if (open) setCompare((c) => !c);
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
      <EpisodeSelect compact />
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
      <span className="h3-seg" title="A section per ref, or one flow that fills each row (each ref's pictures still together)">
        <button className={layout === "sections" ? "h3-on" : ""} onClick={() => setLayout("sections")}>Sections</button>
        <button className={layout === "flow" ? "h3-on" : ""} onClick={() => setLayout("flow")}>Flow</button>
      </span>
      <span className="h3-seg" title="Picture size">
        {(Object.keys(SIZES) as Size[]).map((k) => (
          <button key={k} className={size === k ? "h3-on" : ""} onClick={() => setSize(k)}>{k.toUpperCase()}</button>
        ))}
      </span>
      <label className="h3-row h3-small" style={{ gap: 4 }} title="Only the picture each ref uses now">
        <input type="checkbox" checked={g.picksOnly} onChange={(e) => updateGallery({ picksOnly: e.target.checked })} /> live only
      </label>
      {!g.ref && (
        <label className="h3-row h3-small" style={{ gap: 4 }} title="Every ref in the series config, not just those this episode uses">
          <input type="checkbox" checked={g.series} onChange={(e) => updateGallery({ series: e.target.checked })} /> whole series
        </label>
      )}
      <span className="h3-muted h3-small">{items.length} picture{items.length === 1 ? "" : "s"}</span>
      <FullscreenButton />
      <button className="h3-btn h3-icon" title="Close the gallery (Esc)" onClick={closeGallery}><i className="pi pi-times" /></button>
    </>
  );

  return (
    <FloatingWindow storageKey={RECT_KEY} defaultRect={defaultGalleryRect} head={head} winRef={winRef} className="h3-gallery" minW={480} minH={360}>
      <div className="h3-gal-body">
        {!ep && <div className="h3-empty-state">Pick an episode.</div>}
        {ep && !refs && <div className="h3-empty-state">Loading the refs…</div>}
        {/* the grid stays under an open picture, so closing it comes back to where it was */}
        {ep && refs && <GalleryGrid ep={ep} sections={sections} at={g.at} layout={layout} row={SIZES[size]} />}
        {ep && open && (
          <GalleryViewer ep={ep} item={open} n={idx + 1} of={items.length} compare={compare} setCompare={setCompare} step={step}
            around={[items[idx - 1], items[idx + 1]].filter(Boolean).map((i) => i.file)} />
        )}
      </div>
    </FloatingWindow>
  );
}

function GalleryGrid({ ep, sections, at, layout, row }: {
  ep: string; sections: GallerySection[]; at: string | null; layout: Layout; row: number;
}) {
  // the scroll box: what pictures are near, and where the cursor is kept in view
  const [root, setRoot] = useState<HTMLDivElement | null>(null);
  // the cursor stays in view: coming back from a picture, and as the arrows move it
  useEffect(() => {
    if (!at) return;
    root?.querySelector(`[data-key="${CSS.escape(at)}"]`)?.scrollIntoView({ block: "nearest" });
  }, [at, root]);
  if (!sections.length) return <div className="h3-empty-state">No pictures here yet.</div>;
  const tile = (it: GalleryItem, named: boolean) => <Tile key={it.key} ep={ep} it={it} sel={it.key === at} row={row} named={named} />;
  return (
    <div className="h3-scroll h3-gal-grid" ref={setRoot}>
      <NearRoot.Provider value={root}>
        {layout === "flow" ? (
          <div className="h3-gal-tiles">{sections.flatMap((s) => s.items.map((it, i) => tile(it, i === 0)))}</div>
        ) : sections.map((s) => (
          <section key={s.ref.id}>
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
            <div className="h3-gal-tiles">{s.items.map((it) => tile(it, false))}</div>
          </section>
        ))}
      </NearRoot.Provider>
    </div>
  );
}

/** A picture at its own shape, so a row of them fills with no bars; its
 * view and take on hover. In the flow, a ref's first picture carries its name. */
function Tile({ ep, it, sel, row, named }: { ep: string; it: GalleryItem; sel: boolean; row: number; named: boolean }) {
  const a = itemAspect(it);
  const label = tileLabel(it);
  const [ref, near] = useNear<HTMLButtonElement>();
  // the tile's own width on this screen: the server keeps a few widths made
  // (the Refs tab's 256 among them), and rounds up to the next
  const w = Math.round(a * row * (window.devicePixelRatio || 1));
  return (
    <button ref={ref} data-key={it.key} className={`h3-gal-tile${sel ? " h3-sel" : ""}${it.live ? " h3-live" : ""}`}
      style={{ flex: `${a} 1 ${Math.round(a * row)}px`, aspectRatio: String(a) }}
      title={`${it.ref.name} · ${label}${it.live ? " · live" : ""}${it.take.seed ? ` · seed ${it.take.seed}` : ""}`}
      onClick={() => updateGallery({ open: it.key, at: it.key })}>
      {near && <img src={api().thumbUrl(ep, it.file, w)} alt={label} draggable={false} />}
      {named && <span className="h3-gal-name">{it.ref.name}</span>}
      {it.live && <span className="h3-cand-live">live</span>}
      <span className="h3-thumb-label">{label}</span>
    </button>
  );
}

function tileLabel(it: GalleryItem): string {
  return [viewLabel(it.view), tn(it.take.take)].filter(Boolean).join(" · ");
}

/** A picture opened over the grid: large, what it was made with beside it,
 * the arrows to the next, and the live one beside it to compare (C). */
function GalleryViewer({ ep, item, n, of, compare, setCompare, step, around }: {
  ep: string; item: GalleryItem; n: number; of: number; compare: boolean; setCompare: (c: boolean) => void; step: (d: number) => void;
  /** the pictures either side, fetched ahead so an arrow shows the next at once */
  around: string[];
}) {
  const { ref: r, view, take: t } = item;
  useEffect(() => {
    for (const f of around) new Image().src = api().refFileUrl(ep, f);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ep, around.join("|")]);
  const busy = useApp((s) => !!s.busy[`refpick|${r.id}`]);
  const url = api().refFileUrl(ep, item.file);
  const pickable = view !== PANO_VIEW && view !== TOUR_VIEW;
  const picked = pickable ? pickedOf(r, view) : null;
  const liveTake = picked != null && !item.live ? takesOf(r, view).find((x) => x.take === picked && x.image) : undefined;
  const side = compare && !!liveTake;
  const refs = t.references ?? [];
  return (
    <div className="h3-gal-lightbox">
      <div className="h3-gal-bar">
        <b>{r.name}</b>
        <span className="h3-muted">{tileLabel(item)}</span>
        {item.live && <span className="h3-badge h3-b-ok">live</span>}
        <span className="h3-grow" />
        <span className="h3-muted h3-small">{n} / {of}</span>
        <button className="h3-btn h3-icon" title="Back to the gallery (Esc)" onClick={() => updateGallery({ open: null })}>
          <i className="pi pi-times" />
        </button>
      </div>
      <div className="h3-gal-view">
        <div className={`h3-gal-stage${side ? " h3-gal-side" : ""}`}>
          <div className="h3-gal-pane">
            {side && <span className="h3-pane-label">{tn(t.take)}</span>}
            <img src={url} alt={tileLabel(item)} draggable={false} />
          </div>
          {side && (
            <div className="h3-gal-pane">
              <span className="h3-pane-label">live · {tn(liveTake!.take)}</span>
              <img src={api().refFileUrl(ep, liveTake!.image!)} alt="the live picture" draggable={false} />
            </div>
          )}
          {n > 1 && <button className="h3-gal-nav h3-gal-prev" title="Previous (←)" onClick={() => step(-1)}><i className="pi pi-chevron-left" /></button>}
          {n < of && <button className="h3-gal-nav h3-gal-next" title="Next (→)" onClick={() => step(1)}><i className="pi pi-chevron-right" /></button>}
        </div>
        <aside className="h3-gal-info h3-col">
          <div className="h3-row h3-wrap" style={{ gap: 6 }}>
            {pickable && (
              <button className="h3-btn h3-primary" disabled={item.live || busy}
                title={item.live ? "Already the live file" : `Make ${tn(t.take)} the picture renders use (${r.path})`}
                onClick={() => void pickRef(r.id, view, t.take)}>
                <i className="pi pi-check" /> {item.live ? "Live" : "Pick"}
              </button>
            )}
            {liveTake && (
              <button className={`h3-btn${compare ? " h3-on" : ""}`} title={`${tn(t.take)} beside the live ${tn(liveTake.take)} (C); it stays on as you arrow through`}
                onClick={() => setCompare(!compare)}>
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
    </div>
  );
}
