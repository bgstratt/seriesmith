// The gallery's Sound tab: every take of the episode's sound (GET /seriesmith/sound/gallery) in
// one window: a section per cue (theme songs among them), place, shot, voice and line, each
// take a waveform tile, the one in use badged. A take opened plays over the grid with what it
// was made with beside it, the one in use beside it to compare (C, X to switch which is heard),
// and steps through the grid with the arrow keys. A video take's own sound isn't here (it's on
// the take), nor the stems made from other sound.

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { closeGallery, copyText, generateRef, pickRef, report, updateGallery } from "../actions";
import { loadCues } from "../cueActions";
import { api, host } from "../host";
import { fmtWhen, tn } from "../lib/format";
import { confirmPaid } from "../lib/paid";
import { SOUND_CHIPS, clock, inUse, soundSections, useLabel } from "../lib/soundGallery";
import { loadMix, makeBed, makeEffects, pickMixFx } from "../mixActions";
import { useApp, type GalleryState } from "../store";
import type { Pass, SoundItem, SoundListing, SoundSection, SoundTakeDetail } from "../types";
import { FloatingWindow } from "./FloatingWindow";
import { GALLERY_RECT_KEY, GALLERY_SIZE_KEY, defaultGalleryRect, downloadAll, usePref } from "./Gallery";
import { EpisodeSelect } from "./ShotsTab";
import { FullscreenButton, toggleFullscreen } from "./Viewer";
import { VoiceWave } from "./VoiceRef";
import { isTyping } from "../cutActions";

/** a tile's width and its waveform's height, px */
const SIZES = { s: [200, 40], m: [260, 56], l: [360, 80] } as const;
type Size = keyof typeof SIZES;

/** Everything the Sound tab changes when its scope does: back to the grid, nothing narrowed. */
const WIDE = { sound: null, section: null, open: null, at: null } as const;

/** One audio element for the grid's hover: a tile held under the pointer plays its start. */
let hoverAudio: HTMLAudioElement | null = null;
function hoverPlay(url: string | null) {
  if (!hoverAudio) {
    if (!url) return;
    hoverAudio = new Audio();
  }
  hoverAudio.pause();
  if (!url) return;
  hoverAudio.src = url;
  hoverAudio.currentTime = 0;
  void hoverAudio.play().catch(() => {});
}

/** The listing, fetched when the tab opens, again on `n`, and every 10 s while takes are on the way. */
function useListing(ep: string | null, pass: Pass, n: number): { got: SoundListing | null; err: string | null } {
  const [got, setGot] = useState<SoundListing | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    setGot(null);
  }, [ep, pass]);
  useEffect(() => {
    const fetchIt = api().soundGallery;
    if (!ep || !fetchIt) return;
    let live = true;
    fetchIt(ep, pass).then((r) => { if (live) { setGot(r); setErr(null); } })
      .catch((e) => { if (live) setErr(e instanceof Error ? e.message : String(e)); });
    return () => { live = false; };
  }, [ep, pass, n, tick]);
  const waiting = !!got?.sections.some((s) => s.queued > 0);
  useEffect(() => {
    if (!waiting) return;
    const t = setInterval(() => setTick((x) => x + 1), 10000);
    return () => clearInterval(t);
  }, [waiting]);
  return { got, err };
}

export function SoundGalleryWindow({ ep, g }: { ep: string | null; g: GalleryState }) {
  const pass = useApp((s) => s.pass);
  const winRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = usePref<Size>(GALLERY_SIZE_KEY, ["s", "m", "l"], "m");
  const [compare, setCompare] = useState(false);
  const [hear, setHear] = useState<"a" | "b">("a");
  const [n, setN] = useState(0);
  const refresh = () => setN((x) => x + 1);
  const { got, err } = useListing(ep, pass, n);
  const all = useMemo(() => got?.sections ?? [], [got]);
  const sections = useMemo(() => soundSections(all, g), [all, g.sound, g.section, g.picksOnly, g.query]); // eslint-disable-line react-hooks/exhaustive-deps
  const items = useMemo(() => sections.flatMap((s) => s.items.map((it) => ({ s, it }))), [sections]);
  const keys = useMemo(() => items.map((x) => x.it.key), [items]);
  const idx = g.open ? keys.indexOf(g.open) : -1;
  const open = idx >= 0 ? items[idx] : undefined;

  const [chosen, setChosen] = useState<ReadonlyMap<string, string>>(() => new Map());
  const lastChosen = useRef<string | null>(null);
  const [zipping, setZipping] = useState(false);
  useEffect(() => setChosen(new Map()), [ep]);
  const choose = (it: SoundItem, range: boolean) => {
    setChosen((m) => {
      const next = new Map(m);
      const from = range && lastChosen.current ? keys.indexOf(lastChosen.current) : -1;
      const to = keys.indexOf(it.key);
      if (from >= 0 && to >= 0) {
        for (const x of items.slice(Math.min(from, to), Math.max(from, to) + 1)) next.set(x.it.key, x.it.path);
      } else if (next.has(it.key)) next.delete(it.key);
      else next.set(it.key, it.path);
      return next;
    });
    lastChosen.current = it.key;
  };

  const step = (d: number) => {
    if (!keys.length) return;
    const cur = keys.indexOf(g.open ?? g.at ?? "");
    const k = keys[cur < 0 ? 0 : Math.min(keys.length - 1, Math.max(0, cur + d))];
    updateGallery(open ? { open: k, at: k } : { at: k });
  };

  useEffect(() => winRef.current?.focus(), []);
  // nothing plays on from the grid's hover once the tab closes
  useEffect(() => () => hoverPlay(null), []);

  const keyRef = useRef<(e: KeyboardEvent) => void>(() => {});
  keyRef.current = (e) => {
    if (isTyping(e.target) || e.ctrlKey || e.metaKey || e.altKey) return;
    const audio = open ? winRef.current?.querySelector<HTMLAudioElement>("audio.h3-sndgal-a") : null;
    if (e.key === "Escape") {
      if (document.fullscreenElement) return;
      if (open) updateGallery({ open: null });
      else if (chosen.size) setChosen(new Map());
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
    } else if (e.key === " " && audio) {
      if (audio.paused) void audio.play();
      else audio.pause();
    } else if (e.key === "c" || e.key === "C") {
      if (open) setCompare((c) => !c);
    } else if (e.key === "x" || e.key === "X") {
      if (open && compare) setHear((h) => (h === "a" ? "b" : "a"));
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

  const scoped = g.section ? all.find((s) => s.id === g.section) : undefined;
  const head = (
    <>
      <b>Gallery</b>
      <EpisodeSelect compact />
      <span className="h3-seg" title="The refs' pictures, the shots' takes, or the episode's sound">
        <button onClick={() => updateGallery({ kind: "refs", group: null, ref: null, seq: null, shot: null, ...WIDE, picksOnly: false })}>Refs</button>
        <button onClick={() => updateGallery({ kind: "shots", group: null, ref: null, seq: null, shot: null, ...WIDE, picksOnly: false })}>Shots</button>
        <button className="h3-on">Sound</button>
      </span>
      <span className="h3-gal-view-tools">
        <span className="h3-seg" title="Tile size">
          {(Object.keys(SIZES) as Size[]).map((k) => (
            <button key={k} className={size === k ? "h3-on" : ""} onClick={() => setSize(k)}>{k.toUpperCase()}</button>
          ))}
        </span>
        <label className="h3-row h3-small" style={{ gap: 4 }} title="Only the take in use: a cue's or a shot's effects in the mix, a bed's, voice's or line's picked one">
          <input type="checkbox" checked={g.picksOnly} onChange={(e) => updateGallery({ picksOnly: e.target.checked })} /> in use only
        </label>
        <button className="h3-btn h3-icon" title="Read the takes again" onClick={refresh}><i className="pi pi-refresh" /></button>
      </span>
      <FullscreenButton />
      <button className="h3-btn h3-icon" title="Close the gallery (Esc)" onClick={closeGallery}><i className="pi pi-times" /></button>
    </>
  );
  const tools = (
    <div className="h3-gal-tools">
      <input className="h3-in h3-gal-search" type="search" value={g.query ?? ""} placeholder="Search (cue, shot, place, voice, model, t03)"
        title="Only the takes whose section or take has every word: a cue's name or id, a shot, a place, a voice or line's words, the take (t03), its model, theme, mix or picked. Enter: back to the arrows; Esc clears it"
        onChange={(e) => updateGallery({ query: e.target.value })}
        onKeyDown={(e) => {
          if (e.key === "Enter") e.currentTarget.blur();
          else if (e.key === "Escape") {
            e.stopPropagation();
            if (g.query) updateGallery({ query: "" });
            else e.currentTarget.blur();
          }
        }} />
      <span className="h3-row h3-wrap" style={{ gap: 4 }}>
        <button className={`h3-chip${!g.sound && !g.section ? " h3-on" : ""}`} onClick={() => updateGallery(WIDE)}>Everything</button>
        {SOUND_CHIPS.map((x) => (
          <button key={x.id} className={`h3-chip${g.sound === x.id && !g.section ? " h3-on" : ""}`}
            title={x.id === "voices" ? "Each voice's samples, and each line's takes from a voice model" : undefined}
            onClick={() => updateGallery({ ...WIDE, sound: x.id })}>
            {x.label}
          </button>
        ))}
        {g.section && (
          <button className="h3-chip h3-on" title="Show its whole kind" onClick={() => updateGallery({ ...WIDE, sound: scoped ? (scoped.kind === "lines" ? "voices" : scoped.kind) : null })}>
            {scoped?.name ?? g.section} <i className="pi pi-times" />
          </button>
        )}
      </span>
      <span className="h3-grow" />
      {chosen.size > 0 ? (
        <span className="h3-row h3-gal-chosen" style={{ gap: 6 }}>
          <b className="h3-small">{chosen.size} selected</b>
          <button className="h3-btn h3-primary" disabled={zipping} title={chosen.size > 1 ? "Save them as one zip" : "Save it"}
            onClick={() => {
              setZipping(true);
              void downloadAll(ep, [...chosen.values()]).finally(() => setZipping(false));
            }}>
            <i className={zipping ? "pi pi-spin pi-spinner" : "pi pi-download"} /> {zipping ? "Zipping…" : "Download"}
          </button>
          <button className="h3-btn" title="Select every one shown" onClick={() => setChosen((m) => new Map([...m, ...items.map((x) => [x.it.key, x.it.path] as const)]))}>
            Select all
          </button>
          <button className="h3-btn" title="Clear the selection (Esc)" onClick={() => setChosen(new Map())}>Clear</button>
        </span>
      ) : (
        <span className="h3-muted h3-small">{keys.length} take{keys.length === 1 ? "" : "s"}</span>
      )}
    </div>
  );

  const [w, h] = SIZES[size];
  return (
    <FloatingWindow storageKey={GALLERY_RECT_KEY} defaultRect={defaultGalleryRect} head={head} winRef={winRef} className="h3-gallery" minW={480} minH={360}>
      <div className="h3-gal-body">
        {ep && tools}
        {!ep && <div className="h3-empty-state">Pick an episode.</div>}
        {ep && err && <div className="h3-note h3-err">Couldn't read the episode's sound: {err}</div>}
        {ep && got?.errors.map((x) => <div key={x.kind} className="h3-note h3-warn">The {x.kind} couldn't be read: {x.error}</div>)}
        {ep && !got && !err && <div className="h3-empty-state">Loading…</div>}
        {ep && got && (
          <SoundGrid ep={ep} sections={sections} at={g.at} width={w} height={h} chosen={chosen} choose={choose}
            hoverOk={!open} empty={all.length ? "Nothing here." : "No sound made for this episode yet: cues, beds, effects, voices and lines show here as their takes come in."} />
        )}
        {ep && open && (
          <SoundViewer ep={ep} pass={pass} s={open.s} it={open.it} use={inUse(all.find((x) => x.id === open.s.id))}
            n={idx + 1} of={keys.length} step={step} compare={compare} setCompare={setCompare} hear={hear} setHear={setHear}
            done={refresh} />
        )}
      </div>
    </FloatingWindow>
  );
}

function SoundGrid({ ep, sections, at, width, height, chosen, choose, hoverOk, empty }: {
  ep: string; sections: SoundSection[]; at: string | null; width: number; height: number;
  chosen: ReadonlyMap<string, string>; choose: (it: SoundItem, range: boolean) => void; hoverOk: boolean; empty: string;
}) {
  const [root, setRoot] = useState<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!at) return;
    root?.querySelector(`[data-key="${CSS.escape(at)}"]`)?.scrollIntoView({ block: "nearest" });
  }, [at, root]);
  if (!sections.length) return <div className="h3-empty-state">{empty}</div>;
  const picking = chosen.size > 0;
  return (
    <div className="h3-scroll h3-gal-grid" ref={setRoot}>
      {sections.map((s) => (
        <section key={s.id}>
          <div className="h3-row h3-gal-sec-head">
            <button className="h3-link" title="Only this one" onClick={() => updateGallery({ section: s.id, open: null })}>
              <b>{s.name}</b>
            </button>
            <span className="h3-muted h3-small h3-ell">
              {[`${s.items.length} take${s.items.length === 1 ? "" : "s"}`, s.queued ? `${s.queued} on the way` : "", s.failed ? `${s.failed} failed` : "", s.note]
                .filter(Boolean).join(" · ")}
            </span>
          </div>
          <div className="h3-sndgal-tiles">
            {s.items.map((it) => (
              <SoundTile key={it.key} ep={ep} s={s} it={it} sel={it.key === at} width={width} height={height}
                ticked={chosen.has(it.key)} picking={picking} choose={choose} hoverOk={hoverOk} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function SoundTile({ ep, s, it, sel, width, height, ticked, picking, choose, hoverOk }: {
  ep: string; s: SoundSection; it: SoundItem; sel: boolean; width: number; height: number;
  ticked: boolean; picking: boolean; choose: (it: SoundItem, range: boolean) => void; hoverOk: boolean;
}) {
  const timer = useRef<number | null>(null);
  const url = api().fileUrl(ep, it.path);
  const stop = () => {
    if (timer.current != null) window.clearTimeout(timer.current);
    timer.current = null;
    hoverPlay(null);
  };
  useEffect(() => stop, []);
  const title = [
    `${s.name} ${tn(it.take)}${it.use ? ` · ${useLabel(s.kind)}` : ""}${it.theme ? ` · the series theme ${it.theme}` : ""}`,
    it.text ? `“${it.text}”${it.who ? ` (${it.who})` : ""}` : "",
    [it.model, clock(it.seconds), it.made ? fmtWhen(it.made) : ""].filter(Boolean).join(" · "),
    "Hold the pointer on it to hear its start; click to open it",
  ].filter(Boolean).join("\n");
  return (
    <div data-key={it.key} role="button" title={title}
      className={`h3-sndgal-tile${sel ? " h3-sel" : ""}${it.use ? " h3-live" : ""}${ticked ? " h3-ticked" : ""}${picking ? " h3-picking" : ""}`}
      style={{ width }}
      onMouseEnter={() => {
        if (!hoverOk) return;
        timer.current = window.setTimeout(() => hoverPlay(url), 400);
      }}
      onMouseLeave={stop}
      onClick={(e) => {
        stop();
        if (picking) choose(it, e.shiftKey);
        else updateGallery({ open: it.key, at: it.key });
      }}>
      <div className="h3-row h3-sndgal-tile-head">
        <b>{tn(it.take)}</b>
        {it.use && <span className="h3-gal-in">{useLabel(s.kind)}</span>}
        {it.theme && <span className="h3-gal-up" title={`The series theme ${it.theme}`}>theme</span>}
        <span className="h3-grow" />
        <span className="h3-muted h3-small">{clock(it.seconds)}</span>
      </div>
      <VoiceWave ep={ep} path={it.path} width={width - 12} height={height} version={it.made} />
      <div className="h3-row h3-sndgal-tile-foot">
        <span className="h3-muted h3-small h3-ell">{it.text ? `“${it.text}”` : it.model ?? ""}</span>
      </div>
      <input type="checkbox" className="h3-gal-tick" checked={ticked} aria-label={`Select ${tn(it.take)}`} title="Select (shift: every one from the last)"
        onClick={(e) => { e.stopPropagation(); choose(it, e.shiftKey); }} onChange={() => {}} />
      <a className="h3-gal-dl" href={url} download={it.path.split(/[\\/]/).pop()} title={`Save ${it.path}`} onClick={(e) => e.stopPropagation()}>
        <i className="pi pi-download" />
      </a>
    </div>
  );
}

// what a take was made with, read once when it's opened, never for the grid
const details = new Map<string, SoundTakeDetail>();

function useDetail(ep: string, pass: Pass, s: SoundSection, it: SoundItem): { d?: SoundTakeDetail; err?: string } {
  const k = `${ep}|${pass}|${it.key}|${it.made ?? ""}`;
  const [got, setGot] = useState<{ k: string; d?: SoundTakeDetail; err?: string }>(() => ({ k, d: details.get(k) }));
  useEffect(() => {
    if (details.has(k)) return setGot({ k, d: details.get(k) });
    const fetchIt = api().soundTake;
    if (!fetchIt) return;
    let live = true;
    fetchIt(ep, pass, s.kind, s.id, it.take)
      .then((d) => { details.set(k, d); if (live) setGot({ k, d }); })
      .catch((e) => { if (live) setGot({ k, err: e instanceof Error ? e.message : String(e) }); });
    return () => { live = false; };
  }, [k]); // eslint-disable-line react-hooks/exhaustive-deps
  return got.k === k ? got : {};
}

/** The width of a box, followed as the window resizes. */
function useWidth(): [React.RefObject<HTMLDivElement>, number] {
  const ref = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(600);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setW(Math.max(200, Math.floor(el.clientWidth))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

/** A take's big waveform with the playhead, a click seeking. */
function BigWave({ ep, it, width, audio, label, heard, onPick }: {
  ep: string; it: SoundItem; width: number; audio: HTMLAudioElement | null; label: string; heard: boolean; onPick?: () => void;
}) {
  const [pos, setPos] = useState(0);
  useEffect(() => {
    if (!audio) return;
    let raf = 0;
    const tick = () => {
      setPos(audio.duration > 0 ? audio.currentTime / audio.duration : 0);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [audio]);
  return (
    <div className={`h3-sndgal-big${heard ? " h3-on" : ""}`} onClick={onPick}>
      <span className="h3-pane-label">{label}</span>
      <div style={{ position: "relative" }}
        onClick={(e) => {
          if (!audio || !(audio.duration > 0)) return;
          const r = e.currentTarget.getBoundingClientRect();
          audio.currentTime = ((e.clientX - r.left) / r.width) * audio.duration;
        }}>
        <VoiceWave ep={ep} path={it.path} width={width} height={120} version={it.made} />
        <span className="h3-sndgal-playhead" style={{ left: `${pos * 100}%` }} />
      </div>
    </div>
  );
}

function SoundViewer({ ep, pass, s, it, use, n, of, step, compare, setCompare, hear, setHear, done }: {
  ep: string; pass: Pass; s: SoundSection; it: SoundItem; use: SoundItem | undefined; n: number; of: number;
  step: (d: number) => void; compare: boolean; setCompare: (c: boolean) => void; hear: "a" | "b"; setHear: (h: "a" | "b") => void;
  /** after Use or Regenerate: the listing read again */
  done: () => void;
}) {
  const { d, err } = useDetail(ep, pass, s, it);
  const [boxRef, width] = useWidth();
  const [a, setA] = useState<HTMLAudioElement | null>(null);
  const [b, setB] = useState<HTMLAudioElement | null>(null);
  const [busy, setBusy] = useState<"use" | "regen" | null>(null);
  const other = use && use.key !== it.key ? use : undefined;
  const side = compare && !!other;
  const url = api().fileUrl(ep, it.path);

  // in step: B follows A's play, pause and seeks; only the one heard is unmuted
  useEffect(() => {
    if (!a) return;
    a.muted = side && hear === "b";
    if (!side || !b) return;
    b.muted = hear !== "b";
    const sync = () => {
      if (Math.abs(b.currentTime - a.currentTime) > 0.08) b.currentTime = Math.min(a.currentTime, b.duration || a.currentTime);
    };
    const play = () => { sync(); void b.play().catch(() => {}); };
    const pause = () => b.pause();
    a.addEventListener("play", play);
    a.addEventListener("pause", pause);
    a.addEventListener("seeked", sync);
    a.addEventListener("timeupdate", sync);
    if (!a.paused) play();
    return () => {
      a.removeEventListener("play", play);
      a.removeEventListener("pause", pause);
      a.removeEventListener("seeked", sync);
      a.removeEventListener("timeupdate", sync);
      b.pause();
    };
  }, [a, b, side, hear]);

  const act = async (what: "use" | "regen", f: () => Promise<unknown>) => {
    setBusy(what);
    try {
      await f();
    } finally {
      setBusy(null);
      done();
    }
  };
  const doUse = () => act("use", () => putInUse(ep, pass, s, it));
  const doRegen = () => act("regen", () => regenerate(ep, pass, s));

  return (
    <div className="h3-gal-lightbox">
      <div className="h3-gal-bar">
        <b>{s.name}</b>
        <span className="h3-muted">{tn(it.take)}{it.theme ? ` · the series theme ${it.theme}` : ""}</span>
        {it.use && <span className="h3-badge h3-b-ok">{useLabel(s.kind)}</span>}
        <span className="h3-grow" />
        <span className="h3-muted h3-small">{n} / {of}</span>
        <button className="h3-btn h3-icon" title="Back to the gallery (Esc)" onClick={() => updateGallery({ open: null })}>
          <i className="pi pi-times" />
        </button>
      </div>
      <div className="h3-gal-view">
        <div className="h3-gal-stage h3-sndgal-stage">
          <div ref={boxRef} className="h3-col" style={{ gap: 10, width: "100%", padding: "0 48px" }}>
            <BigWave ep={ep} it={it} width={Math.max(200, width - 96)} audio={a} label={side ? `${tn(it.take)} (A)` : tn(it.take)}
              heard={side && hear === "a"} onPick={side ? () => setHear("a") : undefined} />
            {side && other && (
              <BigWave ep={ep} it={other} width={Math.max(200, width - 96)} audio={b} label={`${useLabel(s.kind)} · ${tn(other.take)} (B)`}
                heard={hear === "b"} onPick={() => setHear("b")} />
            )}
            <audio key={it.key} ref={setA} className="h3-sndgal-a" src={url} controls autoPlay preload="auto" style={{ width: "100%" }} />
            {side && other && <audio key={other.key} ref={setB} src={api().fileUrl(ep, other.path)} preload="auto" style={{ display: "none" }} />}
            {side && (
              <span className="h3-seg" title="Which one you hear (X); they play in step">
                <button className={hear === "a" ? "h3-on" : ""} onClick={() => setHear("a")}>Hear {tn(it.take)}</button>
                <button className={hear === "b" ? "h3-on" : ""} onClick={() => setHear("b")}>Hear {tn(other!.take)} ({useLabel(s.kind)})</button>
              </span>
            )}
          </div>
          {n > 1 && <button className="h3-gal-nav h3-gal-prev" title="Previous (←)" onClick={() => step(-1)}><i className="pi pi-chevron-left" /></button>}
          {n < of && <button className="h3-gal-nav h3-gal-next" title="Next (→)" onClick={() => step(1)}><i className="pi pi-chevron-right" /></button>}
        </div>
        <aside className="h3-gal-info h3-col">
          <div className="h3-row h3-wrap" style={{ gap: 6 }}>
            <button className="h3-btn h3-primary" disabled={it.use || !!busy} title={it.use ? `Already ${useLabel(s.kind)}` : useText(s, it, pass)} onClick={() => void doUse()}>
              <i className={busy === "use" ? "pi pi-spin pi-spinner" : "pi pi-check"} /> {it.use ? (s.kind === "music" || s.kind === "effects" ? "In the mix" : "Picked") : "Use"}
            </button>
            <button className="h3-btn" disabled={!!busy} title={regenTitle(s)} onClick={() => void doRegen()}>
              <i className={busy === "regen" ? "pi pi-spin pi-spinner" : "pi pi-refresh"} /> Regenerate
            </button>
            {other && (
              <button className={`h3-btn${compare ? " h3-on" : ""}`} title={`${tn(it.take)} and ${tn(other.take)} (${useLabel(s.kind)}) in step, X switching which you hear (C); it stays on as you arrow through`}
                onClick={() => setCompare(!compare)}>
                <i className="pi pi-clone" /> Compare with {s.kind === "music" || s.kind === "effects" ? "the mix's" : "the picked"}
              </button>
            )}
            <a className="h3-btn" href={url} download={it.path.split(/[\\/]/).pop()} title={`Save ${it.path}`}>
              <i className="pi pi-download" /> Download
            </a>
            {d?.prompt && (
              <button className="h3-btn" onClick={() => void copyText(d.prompt!, s.kind === "lines" ? "Line" : "Prompt")}>
                <i className="pi pi-copy" /> Copy {s.kind === "lines" ? "line" : "prompt"}
              </button>
            )}
          </div>
          <div className="h3-kv">
            <span>file</span><span className="h3-ell" title={it.path}>{it.path}</span>
            {s.note && <><span>{s.kind === "ambience" ? "places" : s.kind === "music" ? "kind" : "line"}</span><span>{s.note}</span></>}
            {d?.rows.map(([k, v]) => <Row key={k} k={k} v={v} />)}
            {err && <><span>record</span><span className="h3-err">{err}</span></>}
          </div>
          {d?.prompt && <div className="h3-gal-prompt h3-small">{d.prompt}</div>}
        </aside>
      </div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  const shown = k === "Made" ? fmtWhen(v) : k === "Length" ? `${Number(v).toFixed(2)} s` : v;
  return <><span>{k.toLowerCase()}</span><span className={k === "Seed" ? "h3-mono" : undefined}>{shown}</span></>;
}

function useText(s: SoundSection, it: SoundItem, pass: Pass): string {
  switch (s.kind) {
    case "music": return `Put ${tn(it.take)} on the music track as ${s.id}'s item in the ${pass} mix, its level fitted to the cue's arc`;
    case "effects": return `Put ${tn(it.take)} in the ${pass} mix as ${s.id}'s effects`;
    case "ambience": return `Make ${tn(it.take)} the bed this place's shots are laid with`;
    case "voices": return `Make ${tn(it.take)} the voice sample renders and voice models read`;
    case "lines": return `Make ${tn(it.take)} the take of this line laid into the recording`;
  }
}

function regenTitle(s: SoundSection): string {
  switch (s.kind) {
    case "music": return `One more take of ${s.id} on its model, a new seed, planned against the cut as it is now${s.paid ? " (paid: it asks first)" : ""}`;
    case "effects": return `One more effects take for ${s.id}, from the take the cut plays now`;
    case "ambience": return "One more take of this place's bed, a new seed";
    case "voices": return "One more sample of this voice, a new seed";
    case "lines": return "One more take of this line on the voice model (paid on a provider: it asks first)";
  }
}

/** The take made the one in use, as its own window does it. */
async function putInUse(ep: string, pass: Pass, s: SoundSection, it: SoundItem): Promise<void> {
  try {
    if (s.kind === "music") {
      await api().pickCue({ ep, pass, cue: s.id, take: it.take, gain: true });
      host().toast("success", `${s.id}: ${tn(it.take)} in the mix`, "On the music track from the cue's in point, its level fitted to the arc.");
      await Promise.all([loadMix(ep, pass), loadCues(ep)]);
    } else if (s.kind === "effects") {
      await pickMixFx(s.id, it.take);
    } else if (s.kind === "ambience" || s.kind === "voices") {
      await pickRef(s.id, null, it.take);
    } else {
      await api().pickLine(ep, s.id, it.take);
      host().toast("success", `${s.id}: ${tn(it.take)} picked`, "Lay the lines again to put it in the recording.");
    }
  } catch (e) {
    report(`Couldn't use ${s.name} ${tn(it.take)}`, e);
  }
}

/** One more take, as its own window makes one. */
async function regenerate(ep: string, pass: Pass, s: SoundSection): Promise<void> {
  try {
    if (s.kind === "music") {
      if (!confirmPaid(s.paid, `Render one more take of ${s.name}?`)) return;
      const r = await api().renderCue({ ep, pass, cue: s.id, takes: 1 });
      host().toast("info", `${s.id}: ${r.queued.length} take${r.queued.length === 1 ? "" : "s"} queued`, "Each is measured as it lands.");
    } else if (s.kind === "effects") {
      await makeEffects([s.id]);
    } else if (s.kind === "ambience") {
      await makeBed(s.id.replace(/^ambience:/, ""));
    } else if (s.kind === "voices") {
      await generateRef({ ref: s.id, view: null, count: 1, seed_mode: "auto", seed: null, prompt: null, model: null, loras: null, steps: null, note: "" });
    } else {
      const plan = await api().lines(ep);
      const row = plan.lines.find((l) => l.id === s.id);
      if (!row) throw new Error(`the script has no line ${s.id} now`);
      if (plan.paid && !window.confirm(`Make one more take of ${s.id} on ${plan.label || plan.target}? ${row.chars} characters, paid on the provider.\n\n“${row.text}”`)) return;
      const r = await api().generateLines({ ep, confirm_chars: row.chars, lines: [s.id] });
      if (r.errors.length) host().toast("error", `Couldn't make ${s.id}`, r.errors.map((x) => x.error).join("\n"));
      else host().toast("info", `${s.id}: a take queued`, `On ${plan.label || plan.target}; it shows here when it's made.`);
    }
  } catch (e) {
    report(`Couldn't make another take of ${s.name}`, e);
  }
}
