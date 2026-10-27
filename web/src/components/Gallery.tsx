// The gallery: every picture of the episode's refs, or every take of its
// shots, large. A grid (a section per ref or shot, or one flow of them, each
// one's together), every version with the one in use badged, and a picture or
// take opened over it that steps through the grid with the arrow keys and
// closes back to it. Opened from the Refs tab (double-click a ref, a group's
// head, or Gallery) and the Shots tab (double-click a sequence's head, or
// Gallery).

import { createContext, useContext, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { closeGallery, copyText, pickRef, pickTake, toggleUpscaled, updateGallery } from "../actions";
import { errText } from "../api";
import { isTyping } from "../cutActions";
import { api } from "../host";
import {
  GALLERY_GROUPS, gallerySections, itemAspect, sequencesOf, shotSections, takeAspect,
  type GalleryItem, type ShotItem,
} from "../lib/gallery";
import { fmtWhen, shortName, tn } from "../lib/format";
import { keyframeSource } from "../lib/keyframes";
import { PANO_VIEW, TOUR_VIEW, groupOf, pickedOf, takesOf, viewLabel } from "../lib/refs";
import { stripStyle } from "../lib/strip";
import { targetLabel } from "../lib/targets";
import { useApp, type GalleryState } from "../store";
import type { Pass, TakeInfo, TakeSummary } from "../types";
import { FloatingWindow, type Rect } from "./FloatingWindow";
import { aspectOf, useStatus } from "./hooks";
import { EpisodeSelect } from "./ShotsTab";
import { useTargets } from "./Targets";
import { useScrub } from "./Thumb";
import { FullscreenButton, Transport, toggleFullscreen, useSync } from "./Viewer";

const RECT_KEY = "seriesmith.gallery.rect";
const LAYOUT_KEY = "seriesmith.gallery.layout";
const SIZE_KEY = "seriesmith.gallery.size";

type Layout = "sections" | "flow";
/** a row's height, px: the tiles fill each row at their own shapes */
const SIZES = { s: 140, m: 210, l: 320 } as const;
type Size = keyof typeof SIZES;

/** the sequence list's "In the cut": not a sequence id (an id is a word) */
const IN_CUT = "@cut";

/** Everything the gallery changes when its scope does: back to the grid, nothing narrowed. */
const WIDE = { group: null, ref: null, seq: null, shot: null, open: null, at: null } as const;

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

/** A section of the grid, a ref's or a shot's, as the grid draws it. */
interface GridSection {
  id: string;
  name: string;
  /** a heading above it when it changes (a shot's sequence) */
  group?: string;
  note: string;
  narrow: () => void;
  items: GridItem[];
}

interface GridItem {
  key: string;
  /** the picture, relative to the episode */
  thumb: string;
  aspect: number;
  label: string;
  title: string;
  /** "live" or "cut" (green, top right), and "2x" for a take's fresh upscale */
  badges: string[];
  /** a take's strip, scrubbed on hover */
  strip?: string | null;
}

function counts(n: number, queued: number, failed: number, what: string): string {
  return [
    `${n} ${what}${n === 1 ? "" : "s"}`,
    queued ? `${queued} on the way` : "",
    failed ? `${failed} failed` : "",
  ].filter(Boolean).join(" · ");
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
  const st = useStatus();
  const winRef = useRef<HTMLDivElement>(null);
  const [layout, setLayout] = usePref<Layout>(LAYOUT_KEY, ["sections", "flow"], "sections");
  const [size, setSize] = usePref<Size>(SIZE_KEY, ["s", "m", "l"], "m");
  const [compare, setCompare] = useState(false);
  const shots = g.kind === "shots";

  const refSecs = useMemo(
    () => (shots ? [] : gallerySections(refs ?? [], g, pass)),
    // the scope's fields, not `g`: moving through it changes `g` too
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [shots, refs, g.group, g.ref, g.picksOnly, g.series, pass],
  );
  const shotSecs = useMemo(
    () => (shots ? shotSections(st, g, pass) : []),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [shots, st, g.seq, g.shot, g.picksOnly, pass],
  );
  const epAspect = aspectOf(st);
  const sections: GridSection[] = useMemo(() => shots
    ? shotSecs.map((s) => ({
        id: s.shot.shot, name: s.shot.shot, group: s.seq,
        note: [counts(s.items.length, s.queued, s.failed, "take"), s.shot.action ?? ""].filter(Boolean).join(" · "),
        narrow: () => updateGallery({ shot: s.shot.shot, open: null }),
        items: s.items.map((it) => ({
          key: it.key, thumb: it.take.thumb!, aspect: takeAspect(it.take, epAspect), label: tn(it.take.take),
          // what happens in it, as the script says; the rest is in the panel when it's open
          title: [`${it.shot.shot} ${tn(it.take.take)}${it.cut ? " · in the cut" : ""}`, it.shot.action ?? ""].filter(Boolean).join("\n"),
          badges: [...(it.cut ? ["cut"] : []), ...(freshUp(it.take) ? ["2x"] : [])], strip: it.take.strip,
        })),
      }))
    : refSecs.map((s) => ({
        id: s.ref.id, name: s.ref.name,
        note: counts(s.items.length, s.queued, s.failed, "picture"),
        narrow: () => updateGallery({ ref: s.ref.id, open: null }),
        items: s.items.map((it) => ({
          key: it.key, thumb: it.file, aspect: itemAspect(it), label: refLabel(it),
          title: `${it.ref.name} · ${refLabel(it)}${it.live ? " · live" : ""}${it.take.seed ? ` · seed ${it.take.seed}` : ""}`,
          badges: it.live ? ["live"] : [],
        })),
      })), [shots, shotSecs, refSecs, epAspect]);
  const keys = useMemo(() => sections.flatMap((s) => s.items.map((i) => i.key)), [sections]);
  const idx = g.open ? keys.indexOf(g.open) : -1;
  // a picture discarded (or out of "live only") while open: back to the grid
  const openRef = !shots && idx >= 0 ? refSecs.flatMap((s) => s.items).find((i) => i.key === g.open) : undefined;
  const openShot = shots && idx >= 0 ? shotSecs.flatMap((s) => s.items).find((i) => i.key === g.open) : undefined;
  const open = openRef ?? openShot;

  const step = (d: number) => {
    if (!keys.length) return;
    const cur = keys.indexOf(g.open ?? g.at ?? "");
    const k = keys[cur < 0 ? 0 : Math.min(keys.length - 1, Math.max(0, cur + d))];
    updateGallery(open ? { open: k, at: k } : { at: k });
  };

  // focus comes in with it, so the arrows work before a click
  useEffect(() => winRef.current?.focus(), []);

  // keys while focus is inside it (ComfyUI owns them otherwise), stopped here
  // so ComfyUI's window-level shortcuts don't see them
  const keyRef = useRef<(e: KeyboardEvent) => void>(() => {});
  keyRef.current = (e) => {
    if (isTyping(e.target) || e.ctrlKey || e.metaKey || e.altKey) return;
    const video = openShot ? winRef.current?.querySelector<HTMLVideoElement>("video.h3-gal-a") : null;
    if (e.key === "Escape") {
      if (document.fullscreenElement) return; // the browser's: leaves full screen
      if (open) updateGallery({ open: null });
      else closeGallery();
    } else if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
      step(e.key === "ArrowLeft" ? -1 : 1);
    } else if (e.key === "Home" || e.key === "End") {
      if (keys.length) {
        const k = keys[e.key === "Home" ? 0 : keys.length - 1];
        updateGallery(open ? { open: k, at: k } : { at: k });
      }
    } else if (e.key === "Enter" && !open && g.at) {
      updateGallery({ open: g.at });
    } else if (e.key === " " && video) {
      if (video.paused) void video.play();
      else video.pause();
    } else if ((e.key === "," || e.key === ".") && video) {
      video.pause();
      video.currentTime = Math.max(0, video.currentTime + (e.key === "," ? -1 : 1) / (openShot?.take.fps || 24));
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
    const h = (e: KeyboardEvent) => keyRef.current(e);
    el.addEventListener("keydown", h);
    return () => el.removeEventListener("keydown", h);
  }, []);

  const scopeRef = g.ref ? refs?.find((r) => r.id === g.ref) : undefined;
  const scopeShot = g.shot ? st?.shots.find((s) => s.shot === g.shot) : undefined;
  const seqs = useMemo(() => (shots ? sequencesOf(st) : []), [shots, st]);
  const head = (
    <>
      <b>Gallery</b>
      <EpisodeSelect compact />
      <span className="h3-seg" title="The refs' pictures, or the shots' takes">
        <button className={!shots ? "h3-on" : ""} onClick={() => updateGallery({ kind: "refs", ...WIDE, picksOnly: false })}>Refs</button>
        <button className={shots ? "h3-on" : ""} onClick={() => updateGallery({ kind: "shots", ...WIDE, picksOnly: false })}>Shots</button>
      </span>
      <span className="h3-row h3-wrap" style={{ gap: 4 }}>
        {!shots && (
          <button className={`h3-chip${!g.group && !g.ref ? " h3-on" : ""}`} onClick={() => updateGallery(WIDE)}>
            Everything
          </button>
        )}
        {!shots && GALLERY_GROUPS.map((x) => (
          <button key={x.id} className={`h3-chip${g.group === x.id && !g.ref ? " h3-on" : ""}`}
            onClick={() => updateGallery({ ...WIDE, group: x.id })}>
            {x.label}
          </button>
        ))}
        {/* an episode can have dozens of sequences: a list, not a chip each;
            "In the cut" is every sequence with "cut only" on, and a sequence
            picked keeps "cut only" as it is (one sequence's cut takes) */}
        {shots && (
          <select className="h3-in" style={{ minWidth: 0 }} aria-label="Sequence" title="Every take, the cut's, or one sequence's"
            value={g.seq ?? (g.picksOnly ? IN_CUT : "")}
            onChange={(e) => {
              const v = e.target.value;
              updateGallery(v && v !== IN_CUT ? { ...WIDE, seq: v } : { ...WIDE, picksOnly: v === IN_CUT });
            }}>
            <option value="">Every sequence</option>
            <option value={IN_CUT}>In the cut</option>
            {seqs.map((q) => <option key={q} value={q}>{q}</option>)}
          </select>
        )}
        {!shots && g.ref && (
          <button className="h3-chip h3-on" title="Show its whole group"
            onClick={() => updateGallery({ ...WIDE, group: scopeRef ? groupOf(scopeRef) as GalleryState["group"] : null })}>
            {scopeRef?.name ?? g.ref} <i className="pi pi-times" />
          </button>
        )}
        {shots && g.shot && (
          <button className="h3-chip h3-on" title="Show its whole sequence"
            onClick={() => updateGallery({ ...WIDE, seq: scopeShot?.sequence ?? null })}>
            {g.shot} <i className="pi pi-times" />
          </button>
        )}
      </span>
      <span className="h3-grow" />
      <span className="h3-seg" title={`A section per ${shots ? "shot" : "ref"}, or one flow that fills each row (each one's together)`}>
        <button className={layout === "sections" ? "h3-on" : ""} onClick={() => setLayout("sections")}>Sections</button>
        <button className={layout === "flow" ? "h3-on" : ""} onClick={() => setLayout("flow")}>Flow</button>
      </span>
      <span className="h3-seg" title="Picture size">
        {(Object.keys(SIZES) as Size[]).map((k) => (
          <button key={k} className={size === k ? "h3-on" : ""} onClick={() => setSize(k)}>{k.toUpperCase()}</button>
        ))}
      </span>
      <label className="h3-row h3-small" style={{ gap: 4 }} title={shots ? "Only the take each shot's cut uses" : "Only the picture each ref uses now"}>
        <input type="checkbox" checked={g.picksOnly} onChange={(e) => updateGallery({ picksOnly: e.target.checked })} /> {shots ? "cut only" : "live only"}
      </label>
      {!shots && !g.ref && (
        <label className="h3-row h3-small" style={{ gap: 4 }} title="Every ref in the series config, not just those this episode uses">
          <input type="checkbox" checked={g.series} onChange={(e) => updateGallery({ series: e.target.checked })} /> whole series
        </label>
      )}
      <span className="h3-muted h3-small">{keys.length} {shots ? "take" : "picture"}{keys.length === 1 ? "" : "s"}</span>
      <FullscreenButton />
      <button className="h3-btn h3-icon" title="Close the gallery (Esc)" onClick={closeGallery}><i className="pi pi-times" /></button>
    </>
  );

  const loading = shots ? !st : !refs;
  return (
    <FloatingWindow storageKey={RECT_KEY} defaultRect={defaultGalleryRect} head={head} winRef={winRef} className="h3-gallery" minW={480} minH={360}>
      <div className="h3-gal-body">
        {!ep && <div className="h3-empty-state">Pick an episode.</div>}
        {ep && loading && <div className="h3-empty-state">Loading…</div>}
        {/* the grid stays under an open picture, so closing it comes back to where it was */}
        {ep && !loading && <GalleryGrid ep={ep} sections={sections} at={g.at} layout={layout} row={SIZES[size]} />}
        {ep && openRef && (
          <RefViewer ep={ep} item={openRef} n={idx + 1} of={keys.length} compare={compare} setCompare={setCompare} step={step}
            around={[keys[idx - 1], keys[idx + 1]].map((k) => refSecs.flatMap((s) => s.items).find((i) => i.key === k)?.file).filter((f): f is string => !!f)} />
        )}
        {ep && openShot && (
          <ShotViewer ep={ep} pass={pass} item={openShot} n={idx + 1} of={keys.length} compare={compare} setCompare={setCompare} step={step} />
        )}
      </div>
    </FloatingWindow>
  );
}

function GalleryGrid({ ep, sections, at, layout, row }: {
  ep: string; sections: GridSection[]; at: string | null; layout: Layout; row: number;
}) {
  // the scroll box: what pictures are near, and where the cursor is kept in view
  const [root, setRoot] = useState<HTMLDivElement | null>(null);
  // the cursor stays in view: coming back from a picture, and as the arrows move it
  useEffect(() => {
    if (!at) return;
    root?.querySelector(`[data-key="${CSS.escape(at)}"]`)?.scrollIntoView({ block: "nearest" });
  }, [at, root]);
  if (!sections.length) return <div className="h3-empty-state">Nothing here yet.</div>;
  const tile = (it: GridItem, name: string | null) => <Tile key={it.key} ep={ep} it={it} sel={it.key === at} row={row} name={name} />;
  return (
    <div className="h3-scroll h3-gal-grid" ref={setRoot}>
      <NearRoot.Provider value={root}>
        {layout === "flow" ? (
          <div className="h3-gal-tiles">{sections.flatMap((s) => s.items.map((it, i) => tile(it, i === 0 ? s.name : null)))}</div>
        ) : sections.map((s, i) => (
          <section key={s.id}>
            {s.group != null && s.group !== sections[i - 1]?.group && <h3 className="h3-gal-group">{s.group}</h3>}
            <div className="h3-row h3-gal-sec-head">
              <button className="h3-link" title="Only this one" onClick={s.narrow}>
                <b>{s.name}</b>
              </button>
              <span className="h3-muted h3-small h3-ell">{s.note}</span>
            </div>
            <div className="h3-gal-tiles">{s.items.map((it) => tile(it, null))}</div>
          </section>
        ))}
      </NearRoot.Provider>
    </div>
  );
}

/** A picture at its own shape, so a row of them fills with no bars; its
 * label on hover, a take's strip scrubbed under the pointer. In the flow, a
 * ref's or shot's first picture carries its name. */
function Tile({ ep, it, sel, row, name }: { ep: string; it: GridItem; sel: boolean; row: number; name: string | null }) {
  const [ref, near] = useNear<HTMLButtonElement>();
  const [cell, scrub] = useScrub();
  // the tile's own width on this screen: the server keeps a few widths made
  // (the Refs tab's 256 among them), and rounds up to the next
  const w = Math.round(it.aspect * row * (window.devicePixelRatio || 1));
  const scrubbing: CSSProperties | null = cell != null && it.strip ? stripStyle(api().fileUrl(ep, it.strip), cell) : null;
  return (
    <button ref={ref} data-key={it.key} className={`h3-gal-tile${sel ? " h3-sel" : ""}${it.badges.some((b) => b !== "2x") ? " h3-live" : ""}`}
      style={{ flex: `${it.aspect} 1 ${Math.round(it.aspect * row)}px`, aspectRatio: String(it.aspect) }}
      title={it.title}
      onClick={() => updateGallery({ open: it.key, at: it.key })}
      {...(it.strip ? scrub : {})}>
      {near && <img src={api().thumbUrl(ep, it.thumb, w)} alt={it.label} draggable={false} />}
      {scrubbing && <span className="h3-gal-scrub" style={scrubbing} />}
      {name && <span className="h3-gal-name">{name}</span>}
      {it.badges.length > 0 && (
        <span className="h3-gal-badges">
          {it.badges.map((b) => <span key={b} className={b === "2x" ? "h3-gal-up" : "h3-gal-in"}>{b}</span>)}
        </span>
      )}
      <span className="h3-thumb-label">{it.label}</span>
    </button>
  );
}

/** A take's upscale made from it as it is now: what the 2x switch plays. */
function freshUp(t: TakeSummary): string | null {
  return t.upscale?.status === "ok" && t.upscale.fresh && t.upscale.mp4 ? t.upscale.mp4 : null;
}

function refLabel(it: GalleryItem): string {
  return [viewLabel(it.view), tn(it.take.take)].filter(Boolean).join(" · ");
}

/** The bar over an open picture or take: what it is, where, and back. */
function ViewerBar({ name, label, badge, n, of }: { name: string; label: string; badge: string | null; n: number; of: number }) {
  return (
    <div className="h3-gal-bar">
      <b>{name}</b>
      <span className="h3-muted">{label}</span>
      {badge && <span className="h3-badge h3-b-ok">{badge}</span>}
      <span className="h3-grow" />
      <span className="h3-muted h3-small">{n} / {of}</span>
      <button className="h3-btn h3-icon" title="Back to the gallery (Esc)" onClick={() => updateGallery({ open: null })}>
        <i className="pi pi-times" />
      </button>
    </div>
  );
}

function NavButtons({ n, of, step }: { n: number; of: number; step: (d: number) => void }) {
  return (
    <>
      {n > 1 && <button className="h3-gal-nav h3-gal-prev" title="Previous (←)" onClick={() => step(-1)}><i className="pi pi-chevron-left" /></button>}
      {n < of && <button className="h3-gal-nav h3-gal-next" title="Next (→)" onClick={() => step(1)}><i className="pi pi-chevron-right" /></button>}
    </>
  );
}

/** A ref's picture opened over the grid: large, what it was made with beside
 * it, and the live one beside it to compare (C). */
function RefViewer({ ep, item, n, of, compare, setCompare, step, around }: {
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
      <ViewerBar name={r.name} label={refLabel(item)} badge={item.live ? "live" : null} n={n} of={of} />
      <div className="h3-gal-view">
        <div className={`h3-gal-stage${side ? " h3-gal-side" : ""}`}>
          <div className="h3-gal-pane">
            {side && <span className="h3-pane-label">{tn(t.take)}</span>}
            <img src={url} alt={refLabel(item)} draggable={false} />
          </div>
          {side && (
            <div className="h3-gal-pane">
              <span className="h3-pane-label">live · {tn(liveTake!.take)}</span>
              <img src={api().refFileUrl(ep, liveTake!.image!)} alt="the live picture" draggable={false} />
            </div>
          )}
          <NavButtons n={n} of={of} step={step} />
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
                              onClick={() => updateGallery({ ...WIDE, ref: x.id! })}>
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

// a take's record, read once when it's opened (GET /seriesmith/take), never
// for the grid; kept while the page is, by the take and when it finished
const takeInfos = new Map<string, TakeInfo>();

function useTakeInfo(ep: string, pass: Pass, it: ShotItem): { info?: TakeInfo; err?: string } {
  const k = `${ep}|${pass}|${it.shot.shot}|${it.take.take}|${it.take.finished ?? ""}`;
  const [, bump] = useState(0);
  const [err, setErr] = useState<{ k: string; text: string } | null>(null);
  useEffect(() => {
    if (takeInfos.has(k)) return;
    let live = true;
    api().take(ep, pass, it.shot.shot, it.take.take).then(
      (d) => { takeInfos.set(k, d); if (live) bump((n) => n + 1); },
      (e) => { if (live) setErr({ k, text: errText(e) }); },
    );
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [k]);
  return { info: takeInfos.get(k), err: err?.k === k ? err.text : undefined };
}

/** A shot's take opened over the grid: it plays, what it was made with beside
 * it (read now, for this take only), and the cut's take beside it to compare (C). */
function ShotViewer({ ep, pass, item, n, of, compare, setCompare, step }: {
  ep: string; pass: Pass; item: ShotItem; n: number; of: number; compare: boolean; setCompare: (c: boolean) => void; step: (d: number) => void;
}) {
  const { shot: s, take: t } = item;
  const { info, err } = useTakeInfo(ep, pass, item);
  const refs = useApp((x) => x.refs[ep]);
  const { list: targets } = useTargets();
  const [aEl, setAEl] = useState<HTMLVideoElement | null>(null);
  const [bEl, setBEl] = useState<HTMLVideoElement | null>(null);
  const [audio, setAudio] = useState<"a" | "b" | "off">("a");
  const cutTake = !item.cut && s.cut.pass === pass ? s.takes.find((x) => x.take === s.cut.take && x.mp4) : undefined;
  const side = compare && !!cutTake;
  // the take viewer's and Play all's switch: a take's fresh upscale instead of the take
  const hi = useApp((x) => x.upscaled);
  const play = (x: TakeSummary) => (hi && freshUp(x)) || x.mp4!;
  const up = t.upscale?.status === "ok" && t.upscale.fresh ? t.upscale : null;
  useSync(aEl, side ? bEl : null);
  useEffect(() => {
    if (aEl) aEl.muted = audio !== "a";
    if (bEl) bEl.muted = audio !== "b";
  }, [aEl, bEl, audio, side]);
  const file = play(t);
  const url = api().fileUrl(ep, file);
  const sc = info?.sidecar;
  const fps = t.fps || 24;
  const prompt = info?.prompt;
  return (
    <div className="h3-gal-lightbox">
      <ViewerBar name={s.shot} label={[tn(t.take), s.sequence ?? "", file !== t.mp4 ? "2x" : ""].filter(Boolean).join(" · ")} badge={item.cut ? "cut" : null} n={n} of={of} />
      <div className="h3-gal-view">
        <div className="h3-col h3-grow" style={{ minWidth: 0 }}>
          <div className={`h3-gal-stage${side ? " h3-gal-side" : ""}`}>
            <div className="h3-gal-pane">
              {side && <span className="h3-pane-label">{tn(t.take)}</span>}
              <video key={url} ref={setAEl} className="h3-gal-a" src={url} autoPlay loop playsInline preload="auto"
                onClick={(e) => (e.currentTarget.paused ? void e.currentTarget.play() : e.currentTarget.pause())} />
            </div>
            {side && (
              <div className="h3-gal-pane">
                <span className="h3-pane-label">cut · {tn(cutTake!.take)}</span>
                <video key={play(cutTake!)} ref={setBEl} src={api().fileUrl(ep, play(cutTake!))} loop playsInline preload="auto" muted />
              </div>
            )}
            <NavButtons n={n} of={of} step={step} />
          </div>
          <Transport a={aEl} fps={fps} audio={audio} setAudio={setAudio} hasB={side} />
        </div>
        <aside className="h3-gal-info h3-col">
          <div className="h3-row h3-wrap" style={{ gap: 6 }}>
            <button className="h3-btn h3-primary" disabled={item.cut} title={item.cut ? "Already in the cut" : `Use ${tn(t.take)} in the cut`}
              onClick={() => void pickTake(s.shot, t.take)}>
              <i className="pi pi-check" /> {item.cut ? "In the cut" : "Use"}
            </button>
            {cutTake && (
              <button className={`h3-btn${compare ? " h3-on" : ""}`} title={`${tn(t.take)} beside the cut's ${tn(cutTake.take)}, in step (C); it stays on as you arrow through`}
                onClick={() => setCompare(!compare)}>
                <i className="pi pi-clone" /> Compare with cut
              </button>
            )}
            {up && (
              <button className={`h3-btn${hi ? " h3-on" : ""}`} title="Play the take's upscale (2x) instead of the take (remembered; the take viewer and Play all share it)"
                onClick={() => toggleUpscaled()}>
                2x
              </button>
            )}
            <a className="h3-btn" href={url} download={file.split(/[\\/]/).pop()} title={`Save ${file}`}>
              <i className="pi pi-download" /> Download
            </a>
            {prompt && (
              <button className="h3-btn" onClick={() => void copyText(prompt, "Prompt")}>
                <i className="pi pi-copy" /> Copy prompt
              </button>
            )}
          </div>
          <div className="h3-kv">
            {t.target && <><span>model</span><span>{targetLabel(targets, t.target)}</span></>}
            {sc?.model && <><span>file</span><span title={String(sc.model)}>{shortName(sc.model, 40)}</span></>}
            {sc?.loras && sc.loras.length > 0 && (
              <><span>LoRAs</span><span>{sc.loras.map((l) => `${shortName(l.name, 32)}${l.strength !== 1 ? ` ${l.strength}` : ""}`).join(", ")}</span></>
            )}
            {t.seed && <><span>seed</span><span className="h3-mono">{t.seed}{t.seed_source && t.seed_source !== "stable" ? ` (${t.seed_source})` : ""}</span></>}
            <span>settings</span>
            <span>
              {[
                sc?.steps != null ? `${sc.steps} steps` : "",
                t.width && t.height ? `${t.width}x${t.height}` : "",
                t.frames ? `${t.frames} frames · ${(t.frames / fps).toFixed(1)} s @ ${fps}` : "",
              ].filter(Boolean).join(" · ") || "—"}
            </span>
            {up && <><span>upscale</span><span>{[up.width && up.height ? `${up.width}x${up.height}` : "", up.method ?? up.route ?? ""].filter(Boolean).join(" · ")}</span></>}
            {t.overrides.length > 0 && <><span>override</span><span>{t.overrides.join(", ")}</span></>}
            {t.finished && <><span>made</span><span>{fmtWhen(t.finished)}</span></>}
            {t.note && <><span>note</span><span>{t.note}</span></>}
          </div>
          {err && <div className="h3-note h3-note-err h3-small">Couldn't read what it was made with: {err}</div>}
          {!info && !err && <div className="h3-muted h3-small"><i className="pi pi-spin pi-spinner" /> Reading what it was made with…</div>}
          {info && info.refs.some((r) => r.path) && (
            <div className="h3-col" style={{ gap: 4 }}>
              <span className="h3-muted h3-small">The pictures it was sent</span>
              <div className="h3-gal-sent">
                {info.refs.filter((r) => r.path).map((r, i) => {
                  const ref = r.id ? refs?.find((x) => x.id === r.id) : undefined;
                  const changed = !!(ref && r.sha1 && ref.sha1 && ref.sha1 !== r.sha1);
                  const name = ref?.name ?? r.slot ?? r.role ?? "a picture";
                  const pic = r.kind === "image" && r.exists;
                  return (
                    <button key={i} className="h3-gal-sent-one" disabled={!ref || r.kind !== "image"}
                      title={`${r.slot ? `${r.slot}: ` : ""}${r.path}${changed ? "\nChanged since: the file there now isn't the one this take was sent" : ""}${ref && r.kind === "image" ? "\nClick for its pictures" : ""}`}
                      onClick={() => ref && updateGallery({ kind: "refs", ...WIDE, ref: ref.id })}>
                      {pic ? <img src={api().thumbUrl(ep, r.path!, 128)} alt={name} draggable={false} /> : <span className="h3-gal-sent-none"><i className={`pi ${r.kind === "audio" ? "pi-volume-up" : "pi-image"}`} /></span>}
                      <span className="h3-small h3-ell">{name}</span>
                      {changed && <span className="h3-badge h3-b-stale">changed since</span>}
                    </button>
                  );
                })}
              </div>
            </div>
          )}
          {info && !prompt && <div className="h3-muted h3-small">No prompt was kept with this take.</div>}
          {prompt && <div className="h3-gal-prompt h3-small">{prompt}</div>}
        </aside>
      </div>
    </div>
  );
}
