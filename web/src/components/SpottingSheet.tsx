// The spotting sheet (docs/SOUND.md "The spotting sheet"): the episode's view of
// its music, where cues are placed before they're shaped. It is Play all's cut
// player (the same engine and picture: Viewer.tsx useCutEngine / CutStage, the
// mix under it) in a larger window, with frame stepping (, .), jump to the
// previous / next hit and + Hit at the playhead; under it the music map, a row
// per sequence in cut order with its cues (Music), the places' beds
// (Ambience), the shots' effects (Effects) and the hits coloured by kind; on
// the right the selected cue: its hits table (where each lands in the music,
// the fit's error and each take's), the script's music: notes and the series'
// direction, how the tempo was fitted with the nearest other tempos (a click
// holds the cue at one), its takes auditioned under the picture from its in
// point (the preview's mix only), and the cues stale under the cut, to render
// again. The map reads what's loaded (the mix with its beds and effects, the
// cues planned against the pass); the selected cue is fetched when selected.

import { useEffect, useLayoutEffect, useMemo, useRef, useState, type MouseEvent as RMouseEvent } from "react";
import { closeViewer, currentPlaylist, setCutPlaying } from "../actions";
import { cueKey, deleteCue, newCue, saveCueAt } from "../cueActions";
import { fmtClock, tn } from "../lib/format";
import { hitChip, cueTitle, melodyText, withSpec } from "../lib/cue";
import { HIT_KIND_TITLE, anchorTime, regionLabel, regionMode, timeAnchor, type RegionMode } from "../lib/mix";
import {
  bedBlocks, cueBlocks, cutHits, fitWords, fxBlocks, hitTable, inRow, sequenceRows, staleCues, takeColumns, timecode,
  type CueBlock, type CutHit, type MapRow,
} from "../lib/spotting";
import { addMixHit, currentMix, makeBed, makeEffects, moveMixHit, openSoundAdd, setMixItemMute } from "../mixActions";
import {
  auditionTake, jumpToHit, loadCueStates, openCueFromSpot, renderCues, seekToTime, selectSpotCue, setCueTempo, stopAudition,
} from "../spotActions";
import { statusKey, store, useApp, type ViewerState } from "../store";
import { ScoreDraftDialog } from "./ScoreDraft";
import { trackPointer } from "./hooks";
import type { CueResult, CueSummary, Pass } from "../types";
import { FloatingWindow } from "./FloatingWindow";
import { ScoringTabs, SPOT_RECT_KEY, defaultSpotRect } from "./ScoringTabs";
import { SCORING_URL, useMusicTargets } from "./CueWindow";
import { SongLine, ThemeField } from "./CueTheme";
import { CutStage, FullscreenButton, useCutEngine } from "./Viewer";
import { onScreen } from "./SoundLanes";

/** its help strip, open or closed, kept in this browser */
export const SPOT_HELP_KEY = "seriesmith.spotting.help";
const EMPTY_CUES: CueSummary[] = [];


const HELP_STEPS = [
  "Watch the cut with its sound and decide where music goes and where silence is stronger. Stop on a frame (, and . step one) and + Hit marks a moment the music must answer; ◀ Hit / Hit ▶ jump between them.",
  "The map is the whole episode, a row per sequence: Music (the cues), Ambience (the places' beds), Effects (the shots'), the hits by kind. Click a cue to see it here, double-click to shape it in the cue window; click a hit or a row to go there. Right-click a row for a new cue (here, over the sequence, to its end), a hit, the sequence's effects or its place's bed; right-click a cue for its tabs and takes.",
  "For the selected cue: where each hit lands in the music (bar.beat) and how far off each take is; how its tempo was fitted, and the nearest other tempos (a click holds the cue at one); ▶ plays a take under the picture from the cue's in point without changing the mix.",
  "Cues stale under the cut (it moved since their takes were made) are listed at the foot: render them again from there.",
];

function helpOpen(): boolean {
  try {
    return localStorage.getItem(SPOT_HELP_KEY) === "1";
  } catch {
    return false;
  }
}

/** [ and ]: the hit before, the next (the rest are Play all's: space, J/K/L, , and ., the arrows) */
function hitKey(k: KeyboardEvent): boolean {
  if ((k.key !== "[" && k.key !== "]") || k.ctrlKey || k.metaKey || k.altKey) return false;
  jumpToHit(k.key === "]" ? 1 : -1);
  return true;
}

export function SpottingSheet({ ep, v }: { ep: string; v: ViewerState }) {
  const winRef = useRef<HTMLDivElement>(null);
  const e = useCutEngine(ep, winRef, hitKey);
  const { items, cp, fps, total } = e;
  const pass = useApp((s) => s.pass);
  const res = useApp((s) => currentMix(s));
  const states = useApp((s) => s.cueStates[statusKey(ep, pass)]);
  const plain = useApp((s) => s.cues[ep]) ?? EMPTY_CUES;
  const st = useApp((s) => s.status[statusKey(ep, pass)]);
  const audition = useApp((s) => s.audition);
  const sel = v.cue ?? null;
  const [help, setHelp] = useState(helpOpen);
  const [menu, setMenu] = useState<SpotMenuAt | null>(null);
  const [drafting, setDrafting] = useState(false);
  const showHelp = (on: boolean) => {
    try {
      localStorage.setItem(SPOT_HELP_KEY, on ? "1" : "0");
    } catch { /* not kept */ }
    setHelp(on);
  };

  // the cues against this pass: on open (spotActions), when the pass, the cut or the mix changes
  const mixRef = res?.mix;
  useEffect(() => {
    const t = setTimeout(() => void loadCueStates(ep, pass), 300);
    return () => clearTimeout(t);
  }, [ep, pass, mixRef, items]);
  // leaving the sheet: the mix as it is
  useEffect(() => () => stopAudition(), []);

  const cues = states ?? plain;
  const seqOf = useMemo(() => {
    const m = new Map((st?.shots ?? []).map((s) => [s.shot, s.sequence]));
    return (shot: string) => m.get(shot) ?? null;
  }, [st]);
  const rows = useMemo(() => sequenceRows(items, seqOf), [items, seqOf]);
  const blocks = useMemo(() => cueBlocks(cues, items, fps, res?.mix), [cues, items, fps, res?.mix]);
  const beds = useMemo(() => bedBlocks(res?.beds), [res?.beds]);
  const fx = useMemo(() => fxBlocks(res?.fx), [res?.fx]);
  const hits = useMemo(() => cutHits(res?.mix, items, fps), [res?.mix, items, fps]);
  const regions = useMemo(() => regionBlocks(res?.mix.regions, items, fps), [res?.mix.regions, items, fps]);
  const stale = useMemo(() => staleCues(cues), [cues]);
  const offCut = cues.filter((c) => !blocks.some((b) => b.id === c.spec.id));
  // the cue the cue tabs open: the selected one, else the one under the playhead, else the first
  const tabCue = sel ?? (blocks.find((b) => cp.pos >= b.start && cp.pos < b.end) ?? blocks[0])?.id ?? cues[0]?.spec.id ?? null;


  const head = (
    <>
      <i className="pi pi-map" style={{ color: "var(--h3-arc)" }} />
      <b>Scoring</b>
      <ScoringTabs active="spot" cue={tabCue} />
      <span className="h3-muted h3-small">{pass} · {cues.length} cue{cues.length === 1 ? "" : "s"} · {hits.length} hit{hits.length === 1 ? "" : "s"} · {fmtClock(total)}</span>
      <button className="h3-btn" title="A first-pass score from the script's structure and beat lines (// structure:, // beat:): draft cues to shape, nothing rendered"
        onClick={() => setDrafting(true)}><i className="pi pi-sparkles" /> Draft…</button>
      <button className={`h3-btn h3-icon${help ? " h3-on" : ""}`} title="How to use the spotting sheet" aria-label="How to use the spotting sheet" aria-pressed={help}
        onClick={() => showHelp(!help)}><i className="pi pi-question" /></button>
      <span className="h3-grow" />
      <FullscreenButton />
      <button className="h3-btn h3-icon" title="Close (Esc)" onClick={closeViewer}><i className="pi pi-times" /></button>
    </>
  );

  return (
    <FloatingWindow storageKey={SPOT_RECT_KEY} defaultRect={defaultSpotRect} head={head} winRef={winRef} className="h3-spot-win" minW={560} minH={420}>
      {help && (
        <div className="h3-cue-help">
          <ol>{HELP_STEPS.map((s, i) => <li key={i}>{s}</li>)}</ol>
          <span className="h3-col" style={{ gap: 4, alignItems: "flex-end" }}>
            <button className="h3-btn h3-icon" title="Hide this help (? shows it again)" aria-label="Hide the help" onClick={() => showHelp(false)}><i className="pi pi-times" /></button>
            <a className="h3-small" href={`${SCORING_URL}#the-spotting-sheet`} target="_blank" rel="noopener noreferrer">The full guide</a>
          </span>
        </div>
      )}
      <div className="h3-spot-body">
        <div className="h3-spot-main">
          <div className="h3-spot-picture">
            <CutStage ep={ep} e={e} pass={v.pass} />
          </div>
          <SpotTransport fps={fps} total={total} pos={cp.pos} playing={cp.playing} hits={hits} />
          {audition && (
            <div className="h3-spot-aud">
              <i className="pi pi-headphones" /> Auditioning <b>{audition.cue} {tn(audition.take)}</b> in place of the mix's music for this cue (the mix isn't changed)
              <span className="h3-grow" />
              <button className="h3-btn" onClick={stopAudition}><i className="pi pi-stop" /> Back to the mix</button>
            </div>
          )}
          <MusicMap rows={rows} blocks={blocks} beds={beds} fx={fx} hits={hits} regions={regions} pos={cp.pos} fps={fps} sel={sel} onMenu={setMenu} />
          {menu && <SpotMenu at={menu} fps={fps} onClose={() => setMenu(null)} />}
          {drafting && <ScoreDraftDialog ep={ep} pass={pass} onClose={() => setDrafting(false)} />}
          {offCut.length > 0 && (
            <div className="h3-small h3-muted" style={{ padding: "2px 8px" }}>
              Not in this cut: {offCut.map((c) => (
                <button key={c.spec.id} className="h3-linkbtn" onClick={() => selectSpotCue(c.spec.id)} onDoubleClick={() => openCueFromSpot(c.spec.id)}>{c.spec.id}</button>
              ))}
            </div>
          )}
        </div>
        <div className="h3-cue-side h3-spot-side">
          <CuePanel ep={ep} pass={pass} cue={sel} block={blocks.find((b) => b.id === sel)} />
          <StaleCues stale={stale} />
        </div>
      </div>
    </FloatingWindow>
  );
}

// ---------------------------------------------------------------------------
// the transport
// ---------------------------------------------------------------------------

function SpotTransport({ fps, total, pos, playing, hits }: { fps: number; total: number; pos: number; playing: boolean; hits: CutHit[] }) {
  const eps = 0.5 / fps;
  const prev = hits.some((h) => h.t < pos - eps);
  const next = hits.some((h) => h.t > pos + eps);
  const on = hits.find((h) => Math.abs(h.t - pos) <= eps);
  const step = (d: number) => seekToTime(Math.round(pos * fps + 1e-6) / fps + d / fps);
  return (
    <div className="h3-transport h3-spot-transport">
      <button className="h3-btn" title="The hit before ([)" disabled={!prev} onClick={() => jumpToHit(-1)}><i className="pi pi-angle-double-left" /> Hit</button>
      <button className="h3-btn h3-icon" title="A frame back (,)" onClick={() => step(-1)}><i className="pi pi-angle-left" /></button>
      <button className="h3-btn h3-icon" title="Play / pause (space)" onClick={() => setCutPlaying(!playing)}><i className={playing ? "pi pi-pause" : "pi pi-play"} /></button>
      <button className="h3-btn h3-icon" title="A frame on (.)" onClick={() => step(1)}><i className="pi pi-angle-right" /></button>
      <button className="h3-btn" title="The next hit (])" disabled={!next} onClick={() => jumpToHit(1)}>Hit <i className="pi pi-angle-double-right" /></button>
      <button className="h3-btn" title="A hit at the playhead: a moment the music must answer (name it and set its kind on the timeline's Hits lane, right-click)"
        onClick={() => void addMixHit()}><i className="pi pi-plus" /> Hit at playhead</button>
      <input type="range" min={0} max={total || 1} step={1 / fps} value={Math.min(pos, total)} aria-label="Playhead" onChange={(e) => seekToTime(Number(e.target.value))} />
      <span className="h3-mono" title="The cut's timecode (hours:minutes:seconds:frames)">{timecode(pos, fps)}</span>
      {on && <span className={`h3-spot-hitname h3-hit-${on.kind}`} title={HIT_KIND_TITLE[on.kind]}>{on.name}</span>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// the music map
// ---------------------------------------------------------------------------

type Bed = ReturnType<typeof bedBlocks>[number];
type Fx = ReturnType<typeof fxBlocks>[number];

/** Where the map was right-clicked: a row, the cut time under the pointer, the cue block if on one. */
interface SpotMenuAt {
  x: number;
  y: number;
  row: MapRow;
  t: number;
  cue?: string;
}

/** A duck region on the map (the timeline's sound lanes make and edit them): its span, mode and what it does. */
type RegionBlock = { id: string; start: number; end: number; mode: RegionMode; label: string };

function regionBlocks(regions: Parameters<typeof regionLabel>[0][] | undefined, items: Parameters<typeof anchorTime>[0], fps: number): RegionBlock[] {
  return (regions ?? []).flatMap((r, i) => {
    const a = anchorTime(items, r.from, fps);
    const b = anchorTime(items, r.to, fps);
    return a == null || b == null || b <= a ? [] : [{ id: `r${i}`, start: a, end: b, mode: regionMode(r), label: regionLabel(r) }];
  });
}

function MusicMap({ rows, blocks, beds, fx, hits, regions, pos, fps, sel, onMenu }: {
  rows: MapRow[]; blocks: CueBlock[]; beds: Bed[]; fx: Fx[]; hits: CutHit[]; regions: RegionBlock[]; pos: number; fps: number; sel: string | null;
  onMenu: (m: SpotMenuAt) => void;
}) {
  if (!rows.length) return <div className="h3-empty-state">The cut is empty.</div>;
  return (
    <div className="h3-spot-map" aria-label="The music map">
      {rows.map((r, i) => <MapRowView key={`${r.seq}|${i}`} row={r} blocks={blocks} beds={beds} fx={fx} hits={hits} regions={regions} pos={pos} fps={fps} sel={sel} onMenu={onMenu} />)}
    </div>
  );
}

function MapRowView({ row, blocks, beds, fx, hits, regions, pos, fps, sel, onMenu }: {
  row: MapRow; blocks: CueBlock[]; beds: Bed[]; fx: Fx[]; hits: CutHit[]; regions: RegionBlock[]; pos: number; fps: number; sel: string | null;
  onMenu: (m: SpotMenuAt) => void;
}) {
  const span = Math.max(1e-6, row.end - row.start);
  const pct = (t: number) => `${((t - row.start) / span) * 100}%`;
  const wid = (a: number, b: number) => `${((b - a) / span) * 100}%`;
  const seekAt = (e: RMouseEvent<HTMLElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    if (r.width > 0) seekToTime(row.start + ((e.clientX - r.left) / r.width) * span);
  };
  const rowHits = hits.filter((h) => h.t >= row.start - 1e-6 && h.t < row.end + 1e-6);
  const items = useApp((s) => currentPlaylist(s));
  // a hit dragged along its row: where it is while the pointer moves (cut seconds)
  const [drag, setDrag] = useState<{ id: string; t: number } | null>(null);
  const onHitDown = (e: React.PointerEvent<HTMLButtonElement>, h: CutHit) => {
    if (e.button !== 0) return;
    e.stopPropagation();
    const laneEl = e.currentTarget.parentElement;
    const r = laneEl?.getBoundingClientRect();
    if (!r || r.width <= 0) return;
    const x0 = e.clientX;
    let t: number | null = null;
    trackPointer((ev) => {
      if (t == null && Math.abs(ev.clientX - x0) < 3) return;
      const f = Math.min(1, Math.max(0, (ev.clientX - r.left) / r.width));
      t = Math.round((row.start + f * span) * fps) / fps;
      setDrag({ id: h.id, t });
    }, (cancelled) => {
      setDrag(null);
      if (t == null) return seekToTime(h.t);
      const at = cancelled ? null : timeAnchor(items, Math.min(t, row.end - 1 / fps), fps);
      if (at) void moveMixHit(h.id, at);
    });
  };
  const here = pos >= row.start && pos < row.end;
  // right-click: on a lane, the time under the pointer; on the row's head, the playhead (in the row) or its start
  const menuAt = (e: RMouseEvent<HTMLElement>, cue?: string) => {
    e.preventDefault();
    e.stopPropagation();
    const laneEl = (e.target as HTMLElement).closest?.(".h3-spot-lane") as HTMLElement | null;
    let t = here ? pos : row.start;
    const r = laneEl?.getBoundingClientRect();
    if (r && r.width > 0) t = row.start + Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)) * span;
    onMenu({ x: e.clientX, y: e.clientY, row, t, ...(cue ? { cue } : {}) });
  };
  const lane =(name: string, cls: string, children: React.ReactNode) => (
    <div className="h3-spot-lanerow">
      <span className="h3-spot-lab">{name}</span>
      <div className={`h3-spot-lane ${cls}`} onClick={seekAt}>{children}</div>
    </div>
  );
  return (
    <div className={`h3-spot-row${here ? " h3-on" : ""}`} onContextMenu={(e) => menuAt(e)}>
      <div className="h3-spot-rowhead">
        <b>{row.seq ?? "no sequence"}</b>
        <span className="h3-mono h3-muted">{timecode(row.start, fps)} – {timecode(row.end, fps)}</span>
        <span className="h3-muted h3-small">{row.shots.length} shot{row.shots.length === 1 ? "" : "s"}</span>
      </div>
      <div className="h3-spot-lanes">
        {lane("Shots", "h3-spot-shots", row.shots.map((s) => (
          <span key={s.shot} className="h3-spot-shot" style={{ left: pct(s.start), width: wid(s.start, s.end) }} title={`${s.shot} · ${fmtClock(s.start)}`}>{s.shot}</span>
        )))}
        {lane("Hits", "h3-spot-hits", rowHits.map((h) => (
          <button key={h.id} className={`h3-spot-hit h3-hit-${h.kind}${h.must ? "" : " h3-hit-may"}${drag?.id === h.id ? " h3-on" : ""}`}
            style={{ left: pct(drag?.id === h.id ? drag.t : h.t), touchAction: "none" }}
            title={`${h.name} · ${HIT_KIND_TITLE[h.kind]}${h.must ? "" : " (may miss)"} · ${h.at.shot} frame ${h.at.frame} · ${timecode(h.t, fps)}: click to go there, drag to move it (along its row; Esc cancels, Ctrl+Z undoes)`}
            onPointerDown={(e) => onHitDown(e, h)}
            onClick={(e) => e.stopPropagation()}>
            {h.name}{drag?.id === h.id && <span className="h3-spot-tag">{timecode(drag.t, fps)}</span>}
          </button>
        )))}
        {lane("Music", "h3-snd-music", [...inRow(row, regions).map((g) => (
          <span key={g.id} className={`h3-spot-region h3-snd-region-${g.mode}`} style={{ left: pct(g.a), width: wid(g.a, g.b) }} data-region={g.id}
            title={`${g.label} (a duck region: right-click its tab on the timeline's hits lane to change it)`} />
        )), ...inRow(row, blocks).map((c) => (
          <button key={c.id} className={`h3-spot-blk h3-spot-cue${c.id === sel ? " h3-on" : ""}${c.stale.length ? " h3-spot-stale" : ""}${c.inMix == null ? " h3-spot-unplaced" : ""}${c.muted ? " h3-snd-silent" : ""}`}
            style={{ left: pct(c.a), width: wid(c.a, c.b) }}
            title={`${c.label} (${c.kind}) · ${c.inMix != null ? `${tn(c.inMix)} in the mix` : c.ok ? `${c.ok} take${c.ok === 1 ? "" : "s"}, none picked` : "no takes yet"}${c.muted ? " · muted" : ""}${c.stale.length ? `\nstale: ${c.stale.join("; ")}` : ""}\nclick: select · double-click: the cue window`}
            onClick={(e) => {
              e.stopPropagation();
              selectSpotCue(c.id);
            }}
            onDoubleClick={(e) => {
              e.stopPropagation();
              openCueFromSpot(c.id);
            }}
            onContextMenu={(e) => {
              selectSpotCue(c.id);
              menuAt(e, c.id);
            }}>
            {c.fromBefore ? "… " : ""}{c.label}
            <span className="h3-spot-tag">{c.kind === "song" ? "song" : "score"}</span>
            {c.inMix != null ? <span className="h3-spot-tag">{tn(c.inMix)}</span> : <span className="h3-spot-tag h3-muted">not placed</span>}
            {c.muted && <span className="h3-spot-tag">muted</span>}
            {c.stale.length > 0 && <span className="h3-spot-tag h3-b-stale">stale</span>}
          </button>
        ))])}
        {lane("Ambience", "h3-snd-ambience", inRow(row, beds).map((b) => (
          <span key={b.id} className={`h3-spot-blk${b.exists ? "" : " h3-spot-unplaced"}${b.mute ? " h3-snd-silent" : ""}`} style={{ left: pct(b.a), width: wid(b.a, b.b) }}
            title={`${b.label}${b.exists ? "" : " (not made yet: the Refs tab's Ambience)"}${b.mute ? " · muted" : ""}`}>{b.label}</span>
        )))}
        {lane("Effects", "h3-snd-effects", inRow(row, fx).map((f) => (
          <span key={f.id} className={`h3-spot-blk${f.stale ? " h3-spot-stale" : ""}${f.heard ? "" : " h3-snd-silent"}`} style={{ left: pct(f.a), width: wid(f.a, f.b) }}
            title={`${f.label}${f.stale ? ` · stale: ${f.stale}` : ""}`}>{f.label}{f.stale ? <span className="h3-spot-tag h3-b-stale">stale</span> : null}</span>
        )))}
        {here && <div className="h3-spot-playhead" style={{ left: `calc(64px + (100% - 64px) * ${(pos - row.start) / span})` }} />}
      </div>
    </div>
  );
}

/** The map's right-click menu (h3-menu, as the lanes'): a cue from here, over the row's
 * sequence or to its end; a hit here; the sequence's effects and its place's bed; on a cue
 * block, the cue's own (its tabs, render its takes). */
function SpotMenu({ at, fps, onClose }: { at: SpotMenuAt; fps: number; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ left: at.x, top: at.y });
  const items = useApp((s) => currentPlaylist(s));
  const res = useApp((s) => currentMix(s));
  useLayoutEffect(() => {
    const r = ref.current?.getBoundingClientRect();
    if (r) setPos(onScreen(at.x, at.y, r));
  }, [at]);
  useEffect(() => {
    const down = (e: Event) => ref.current && !ref.current.contains(e.target as Node) && onClose();
    const key = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.stopPropagation();
      onClose();
    };
    window.addEventListener("pointerdown", down, true);
    window.addEventListener("keydown", key, true);
    return () => {
      window.removeEventListener("pointerdown", down, true);
      window.removeEventListener("keydown", key, true);
    };
  }, [onClose]);
  const { row, cue } = at;
  // the cue's item in this pass's mix (picked): its "plays in the mix"
  const item = cue ? res?.mix.items?.find((i) => i.id === cue) : undefined;
  const seq = row.seq ?? "these shots";
  const shots = row.shots.map((s) => s.shot);
  const last = shots[shots.length - 1];
  // the frame under the pointer, kept inside the row
  const anchor = timeAnchor(items, Math.min(Math.max(at.t, row.start), row.end - 0.5 / (fps || 24)), fps);
  // the sequence's place, when its shots share one
  const placed = shots.map((x) => res?.places?.[x]).filter((p) => !!p);
  const place = placed.length && placed.every((p) => p!.place === placed[0]!.place) ? placed[0]! : undefined;
  const laid = place ? res?.beds?.find((b) => b.place === place.place) : undefined;
  const run = (fn: () => void) => () => {
    onClose();
    fn();
  };
  return (
    <div ref={ref} className="h3-menu h3-snd-pop h3-spot-menu" style={pos} onClick={(e) => e.stopPropagation()} onPointerDown={(e) => e.stopPropagation()}
      onContextMenu={(e) => e.preventDefault()}>
      <div className="h3-menu-head">{row.seq ?? "no sequence"}{anchor ? ` · ${anchor.shot} frame ${anchor.frame}` : ""}</div>
      {cue && (
        <>
          <button data-spot="open-score" title="Shape it in the scoring window: everything on one bar grid" onClick={run(() => openCueFromSpot(cue, "score"))}>
            <i className="pi pi-external-link" /> Open {cue} in Score
          </button>
          <button title="Its intensity lane, large" onClick={run(() => openCueFromSpot(cue, "arc"))}>
            <i className="pi pi-chart-line" /> Its arc…
          </button>
          <button title="Who plays in each bar; its takes" onClick={run(() => openCueFromSpot(cue, "orch"))}>
            <i className="pi pi-sliders-h" /> Its orchestration &amp; takes…
          </button>
          <button title="Render its takes again (its model's preset's number), on the queue" onClick={run(() => void renderCues([cue]))}>
            <i className="pi pi-play" /> Render its takes
          </button>
          {item && (
            <button data-spot="plays" title={item.mute ? "Hear it again in this pass's mix and Play all" : "Silence it in this pass's mix and Play all, kept where it is (undo: Ctrl+Z)"}
              onClick={run(() => void setMixItemMute(item.id, !item.mute))}>
              <i className={item.mute ? "pi pi-stop" : "pi pi-check-square"} /> Plays in the mix
            </button>
          )}
          <button data-spot="delete-cue" title="Its takes go to the episode's _history folder and it comes out of both passes' mixes (asks first; Ctrl+Z can't bring it back)"
            onClick={run(() => void deleteCue(cue))}>
            <i className="pi pi-trash" /> Delete cue {cue}…
          </button>
          <div className="h3-menu-sep" />
        </>
      )}
      <button data-spot="cue-here" disabled={!anchor} title="A cue from this frame to the end of its shot (drag its out point later)"
        onClick={run(() => anchor && void newCue(anchor, { until: anchor.shot, tab: "score" }))}>
        <i className="pi pi-volume-up" /> New cue here{anchor ? ` (to the end of ${anchor.shot})` : ""}
      </button>
      <button data-spot="cue-seq" title={`A cue over every shot of ${seq} in this row: ${shots[0]} to ${last}`}
        onClick={run(() => void newCue(null, { shots, tab: "score" }))}>
        <i className="pi pi-volume-up" /> New cue over {seq}
      </button>
      <button data-spot="cue-to-end" disabled={!anchor} title={`A cue from this frame to the end of ${last}`}
        onClick={run(() => anchor && void newCue(anchor, { until: last, tab: "score" }))}>
        <i className="pi pi-volume-up" /> New cue from here to the end of {seq}
      </button>
      <button data-spot="hit" disabled={!anchor} title="A hit on this frame: a moment the music must answer (name it and set its kind on the timeline's Hits lane)"
        onClick={run(() => anchor && void addMixHit(anchor))}>
        <i className="pi pi-flag" /> Mark a hit here
      </button>
      <div className="h3-menu-sep" />
      <button data-spot="fx" title={`Sync sound made from the frames of the take each of ${seq}'s ${shots.length} shot${shots.length === 1 ? "" : "s"} plays`}
        onClick={run(() => void makeEffects(shots))}>
        <i className="pi pi-bolt" /> Make effects for {seq}
      </button>
      {place && (laid
        ? (
          <button data-spot="bed" title={`${laid.exists ? "A new take of" : "Make"} ${place.name}'s bed from its words (“${laid.words}”)`} onClick={run(() => void makeBed(place.place))}>
            <i className="pi pi-cloud" /> Make {place.name}'s bed{laid.exists ? " again" : ""}
          </button>
        ) : (
          <button data-spot="bed" title={`${place.name} has no ambience words yet: say what's heard there, and make its bed`}
            onClick={run(() => openSoundAdd({ kind: "bed", place: place.place }))}>
            <i className="pi pi-cloud" /> Make {place.name}'s ambience bed…
          </button>
        ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// the selected cue
// ---------------------------------------------------------------------------

function CuePanel({ ep, pass, cue, block }: { ep: string; pass: Pass; cue: string | null; block: CueBlock | undefined }) {
  const key = cue ? cueKey(ep, pass, cue) : "";
  const res = useApp((s) => (key ? s.cue[key] : undefined));
  const err = useApp((s) => (key ? s.cueError[key] : undefined));
  if (!cue) {
    return <div className="h3-muted h3-small">Click a cue on the map to see its hits, its tempo and its takes here; double-click to shape it in the cue window.</div>;
  }
  if (!res) return <div className="h3-small">{err ? <span className="h3-err">{cue}: {err}</span> : <><i className="pi pi-spin pi-spinner" /> {cue}…</>}</div>;
  return <CueDetail ep={ep} pass={pass} res={res} block={block} />;
}

function CueDetail({ ep, pass, res, block }: { ep: string; pass: Pass; res: CueResult; block: CueBlock | undefined }) {
  const { spec, plan, takes } = res;
  const targets = useMusicTargets();
  const target = targets.find((t) => t.id === (plan?.target ?? spec.model));
  const items = useApp((s) => currentPlaylist(s));
  const fps = plan?.fps || 24;
  const pos = useApp((s) => s.cutPlay.pos);
  const audition = useApp((s) => s.audition);
  const inMix = block?.inMix ?? takes.find((t) => t.placed === store.get().pass)?.take ?? null;
  const cols = useMemo(() => takeColumns(takes, inMix), [takes, inMix]);
  const rows = useMemo(() => (plan ? hitTable(spec, plan, takes, cols, items, fps) : []), [spec, plan, takes, cols, items, fps]);
  const [busy, setBusy] = useState(false);
  return (
    <div className="h3-col h3-spot-cue-detail" style={{ gap: 6 }}>
      <div className="h3-row" style={{ gap: 6 }}>
        <b>{cueTitle(spec)}</b>
        <span className="h3-grow" />
        <button className="h3-btn" title="Shape it: its sections, arc, orchestration and takes (double-click on the map does the same)" onClick={() => openCueFromSpot(spec.id)}>
          <i className="pi pi-external-link" /> Cue window
        </button>
      </div>
      {res.plan_error && <div className="h3-err h3-small">{res.plan_error}</div>}
      {plan && (
        <>
          <div className="h3-cue-h">Hits</div>
          {!rows.length ? <div className="h3-muted h3-small">No hits in its span: mark them with + Hit at playhead.</div> : (
            <div className="h3-spot-tablewrap">
              <table className="h3-spot-table">
                <thead>
                  <tr>
                    <th>Hit</th><th>Kind</th><th title="Must land: the tempo is fitted to put it on its line">Must</th><th>Anchor</th><th>Cut</th>
                    <th title="The bar and beat it lands on">Bar</th><th title="Frames the fit leaves it off its line">Fit</th>
                    {cols.map((c) => (
                      <th key={c.take} className={c.inMix ? "h3-spot-inmix" : ""} title={`${tn(c.take)}, #${c.rank}${c.inMix ? ", in the mix" : ""}${c.stale ? ", stale" : ""}: frames from each hit to the nearest event in its music`}>
                        {tn(c.take)}{c.inMix ? " ●" : ""}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.id} className={`h3-spot-hitrow${r.t != null && Math.abs(r.t - pos) <= 0.5 / fps ? " h3-on" : ""}`}
                      title={r.t != null ? "Click: the viewer to this hit" : "Its cue isn't in this cut"}
                      onClick={() => r.t != null && seekToTime(r.t)}>
                      <td><span className={`h3-spot-dot h3-hit-${r.kind}`} /> {r.name}</td>
                      <td>{r.kind}{r.ends ? " (end)" : ""}</td>
                      <td>{r.must ? "yes" : "may miss"}</td>
                      <td className="h3-mono">{r.at ? `${r.at.shot}:${r.at.frame}` : "—"}</td>
                      <td className="h3-mono">{r.t != null ? timecode(r.t, fps) : "—"}</td>
                      <td className="h3-mono">{r.barBeat}</td>
                      <td className="h3-mono">{r.fit == null ? "—" : hitChip(r.fit).text}</td>
                      {r.takes.map((x, i) => {
                        const c = hitChip(x);
                        return <td key={cols[i].take} className={`h3-mono h3-spot-err-${r.ends ? "none" : c.cls}`}>{r.ends ? "" : c.text}</td>;
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <TempoFit res={res} />
          <div className="h3-cue-h">Takes</div>
          {!takes.length && <div className="h3-muted h3-small">None yet.</div>}
          <div className="h3-col" style={{ gap: 2 }}>
            {takes.map((t) => {
              const c = cols.find((x) => x.take === t.take);
              const on = audition?.cue === spec.id && audition.take === t.take;
              return (
                <div key={t.take} className={`h3-row h3-small h3-spot-take${on ? " h3-on" : ""}`} style={{ gap: 6 }}>
                  <button className="h3-btn h3-icon" disabled={t.status !== "ok"} aria-label={`Audition ${tn(t.take)}`}
                    title={on ? "Back to the mix" : `Play ${tn(t.take)} under the picture from the cue's in point, in its place (the mix isn't changed)`}
                    onClick={() => (on ? stopAudition() : auditionTake(spec.id, t))}>
                    <i className={on ? "pi pi-stop" : "pi pi-play"} />
                  </button>
                  <b className="h3-mono">{tn(t.take)}</b>
                  {c && <span className="h3-muted">#{c.rank}</span>}
                  {t.take === inMix && <span className="h3-badge" title="the take in the mix">in mix</span>}
                  {t.status !== "ok" && <span className="h3-muted">{t.status}{t.error ? `: ${t.error}` : ""}</span>}
                  {t.measured && <span className="h3-muted">worst {t.measured.worst_must} f · shape {t.measured.shape_error ?? "—"}</span>}
                  {t.measured?.melody != null && <span className={t.measured.on_theme === false ? "h3-cue-offtext" : "h3-muted"} title="How much of the theme's melody it kept (SheetSage2): under 30 % it lost the theme">{melodyText(t.measured)}</span>}
                  {t.song && <SongLine song={t.song} />}
                  {!!t.stale?.length && <span className="h3-badge h3-b-stale" title={t.stale.join("\n")}>stale</span>}
                </div>
              );
            })}
          </div>
          <button className="h3-btn" disabled={busy} title="Render its takes again (its model's preset's number), on the queue"
            onClick={() => {
              setBusy(true);
              void renderCues([spec.id]).finally(() => setBusy(false));
            }}><i className="pi pi-play" /> Render {spec.id}'s takes</button>
          <div className="h3-cue-h" title="A theme carried from cue to cue (the leitmotif): a series theme, another cue's take, or a sound file">Theme</div>
          <ThemeField ep={ep} pass={pass} spec={spec} plan={plan} target={target} targets={targets} themes={res.themes}
            save={(patch) => void saveCueAt({ ep, pass, cue: spec.id, key: cueKey(ep, pass, spec.id) }, withSpec(spec, patch))} />
          {plan.blocked && <div className="h3-err h3-small">{plan.blocked}</div>}
          {(plan.direction || plan.notes?.length) ? <div className="h3-cue-h">Direction</div> : null}
          {plan.direction && <div className="h3-small" title="the series config's score direction (sound.score), before every cue's style"><b>Series</b> {plan.direction}</div>}
          {plan.notes?.map((n) => <div key={n.shot} className="h3-small" title="the script's music: note for this shot"><b>{n.shot}</b> {n.music}</div>)}
        </>
      )}
    </div>
  );
}

/** How the tempo was fitted, and the nearest others: a click holds the cue at one. */
function TempoFit({ res }: { res: CueResult }) {
  const { spec, plan } = res;
  const [saving, setSaving] = useState<number | null>(null);
  if (!plan) return null;
  const f = fitWords(spec, plan);
  const fitted = plan.hits.filter((h) => !h.ends).length;
  const alts = plan.alternatives ?? [];
  return (
    <>
      <div className="h3-cue-h">The tempo</div>
      <div className="h3-small h3-col" style={{ gap: 2 }}>
        <span>asked {f.asked} bpm{spec.fixed_tempo ? " (fixed)" : ""}, fitted <b className="h3-mono">{f.fitted}</b>{f.change ? ` (${f.change})` : ""}</span>
        <span className="h3-muted">the model is asked {f.askBpm} bpm, each take stretched by {f.stretch}</span>
        <span>worst must-hit: <b className={`h3-mono${f.worst > 1 ? " h3-cue-offtext" : ""}`}>{f.worst} frames</b> off its line</span>
      </div>
      {alts.length > 0 && (
        <>
          <span className="h3-small h3-muted">
            {fitted <= 1 ? "One hit to land: any tempo lands it, the pre-roll moves. Nearest tempos:" : "The nearest tempos that land the hits (worst must-hit, frames):"}
          </span>
          <div className="h3-row h3-spot-alts" style={{ gap: 4, flexWrap: "wrap" }}>
            {alts.map((a) => {
              const cur = Math.abs(a.bpm - plan.fit.bpm) < 0.005;
              return (
                <button key={a.bpm} className={`h3-btn h3-spot-alt${cur ? " h3-on" : ""}`} disabled={cur || saving != null}
                  title={cur ? "The tempo it's at" : `Hold ${spec.id} at ${a.bpm} bpm (the tempo fixed): worst must-hit ${a.worst_must} frames, all hits ${a.total}, ${a.preroll.toFixed(2)} s of pre-roll. Its takes go stale.`}
                  onClick={() => {
                    setSaving(a.bpm);
                    void setCueTempo(spec.id, a.bpm).finally(() => setSaving(null));
                  }}>
                  <span className="h3-mono">{a.bpm}</span> <span className="h3-muted">{a.worst_must} f</span>
                </button>
              );
            })}
          </div>
        </>
      )}
    </>
  );
}

/** The episode's cues stale under the cut, to render again. */
function StaleCues({ stale }: { stale: CueSummary[] }) {
  const [busy, setBusy] = useState(false);
  const run = (ids: string[]) => {
    setBusy(true);
    void renderCues(ids).finally(() => setBusy(false));
  };
  return (
    <div className="h3-col h3-spot-stalelist" style={{ gap: 4 }}>
      <div className="h3-cue-h">Stale cues</div>
      {!stale.length ? <span className="h3-small h3-muted">None: every cue's takes match the cut.</span> : (
        <>
          {stale.map((c) => (
            <div key={c.spec.id} className="h3-row h3-small" style={{ gap: 6 }}>
              <button className="h3-linkbtn" onClick={() => selectSpotCue(c.spec.id)}>{cueTitle(c.spec)}</button>
              <span className="h3-muted h3-ell" title={(c.stale ?? []).join("\n")}>{c.stale?.length ? c.stale[0] : "every take"}</span>
              <span className="h3-grow" />
              <button className="h3-btn" disabled={busy} onClick={() => run([c.spec.id])}>Render</button>
            </div>
          ))}
          {stale.length > 1 && <button className="h3-btn" disabled={busy} onClick={() => run(stale.map((c) => c.spec.id))}><i className="pi pi-play" /> Render all {stale.length} stale</button>}
        </>
      )}
    </div>
  );
}
