// The cue window (docs/SOUND.md "The cue window"): what happens inside a music
// cue, in the viewer's place, three tabs on one bar grid at the plan's tempo,
// from the pre-roll through the tail. Score: the picture, the hits (each at the
// bar and beat it lands on, and the fit's error), the bar ruler, the sections
// (drag an edge: whole bars; double-click splits one, right-click: split, merge,
// reset from the hits), the intensity lane (the arc: drag a point,
// double-click adds one, right-click removes it) and the takes, best first,
// each its waveform and its loudness per bar over the arc; the inspector on the
// right edits the section selected, or the cue (a preset fills its fields). Arc: the intensity lane large,
// drawn freehand or by points, smoothed, a preset shape, its peaks and lows
// snapped to hits, sections cut from it, and beside it what the model will
// hear. Orchestration & takes: who plays in each bar, painted off / under /
// present / lead, then the takes, where bars dragged across are comped from
// another take or lowered with the mix's breakpoints. Every cue edit is one PUT
// of the spec, then the cue fetched again (cueActions): the plan is the
// server's. The arc is energy 1-5, drawn in its own colour: the timeline's gain
// breakpoints (dB) are another curve.

import { useCallback, useEffect, useLayoutEffect, useRef, useState, type MouseEvent as RMouseEvent, type PointerEvent as RPointerEvent, type ReactNode } from "react";
import { closeViewer, currentPlaylist } from "../actions";
import { applyCuePreset, compCueTake, cueKey, deleteCue, loadCue, loadCues, pickCueTake, pinCueTheme, renderCue, repaintCueTake, saveCue } from "../cueActions";
import { isTyping } from "../cutActions";
import { api, host } from "../host";
import {
  ARC_SHAPES, KEYS, LEVEL_WORDS, METERS, ORCH_LEVELS, aceBeats, addPoint, arcFlags, arcPoints, arcSpec, barBeat, barSpan, barsInSpan, barsLabel, clipsOver, compLabel, repaintLabel, repaintWhy, cueStart,
  drawnPoints, editableSections, familyName, gridOf, heldCells, hitChip, impliedPoints, keyChoice, levelY, levelsAsEnergy, melodyText, mergeStroke, meterBeats,
  meterText, mergeSections, moveEdge,
  movePoint, orchestraRows, sectionChoice, SCORE_SECTIONS, SONG_SECTIONS, paintOrchestra, patchSection, presetPoints, ranks, removeFamily, removePoint, renameFamily, sectionAt, sectionEdges, sectionWords, strokeLevel, ORCH_STEP,
  presetGroups, presetReplaces, sectionsFromArc, smoothPoints, snapToHits, splitPoint, splitSection, tauX, trimOrchestra, withEnergies, withSpec, wordsOffArc, xTau, yLevel,
  type ArcPt, type Grid, type Orchestra,
} from "../lib/cue";
import { fmtClock } from "../lib/format";
import { HIT_KIND_TITLE } from "../lib/mix";
import { lowerMixItem } from "../mixActions";
import { clipTake, type PlayItem } from "../lib/playlist";
import { openCueFromSpot } from "../spotActions";
import { useApp, statusKey, type ViewerState } from "../store";
import type { CuePlan, CuePreset, CueResult, CueSection, CueSpec, CueTake, Pass, Target } from "../types";
import { SongLine, SongStrip, ThemeField } from "./CueTheme";
import { FloatingWindow } from "./FloatingWindow";
import { ScoringTabs, SPOT_RECT_KEY, defaultSpotRect, type CueTab } from "./ScoringTabs";
import { trackPointer, useSize } from "./hooks";
import { mediaStyle } from "./Thumb";
import { onScreen } from "./SoundLanes";
import { FullscreenButton } from "./Viewer";
import { PeaksCanvas, usePeaks } from "./Waveform";

// the viewer's place (the standalone page docks it in the middle)
/** the lanes' labels, stuck to the left */
const LAB_W = 76;
const PIC_H = 38;
const HITS_H = 30;
const RULER_H = 18;
const SECT_H = 30;
const ARC_H = 84;
/** the Arc tab's intensity lane */
const ARC_BIG_H = 220;
/** a row of the orchestration grid */
const ORCH_H = 20;
const TAKE_H = 40;
const PPS_MIN = 4;
const PPS_MAX = 160;
const TAKES_DEFAULT = 8;
const LOWER_DB = -6;
const EMPTY: number[] = [];
const LEVELS = [1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5];
/** the user's guide to the cue window (docs/SCORING.md on the docs site) */
export const SCORING_URL = "https://docs.seriesmith.com/scoring";
/** each tab's help strip, open or closed, kept in this browser */
export const HELP_KEY = "seriesmith.cue.help";

export type { CueTab } from "./ScoringTabs";
type ArcMode = "draw" | "points";

/** How to use each tab: a few steps from docs/SCORING.md, and the section of it that has the rest. */
const HELP: Record<CueTab, { steps: string[]; anchor: string }> = {
  score: {
    anchor: "3-shape-it-the-score-tab",
    steps: [
      "Mark the hits first: double-click the timeline's Hits lane where the music must answer (accent, arrive, drop or turn); Must land fits the tempo to put it on its line.",
      "Shape the sections: drag an edge (whole bars), double-click to split one, right-click to merge (or reset them from the hits); click one for its words and energy from and to. Drag the green energy line's points.",
      "No idea where to start? Pick a Preset in the inspector (romantic swell, chase, pop ballad…): it fills the style, tempo, sections and orchestration; then adjust. Render 8 takes: each is measured against the hits and the arc, best first.",
      "Listen to the top few (the playhead runs over the grid), then Pick one: it goes on the Music lane, its level fitted to the arc.",
    ],
  },
  arc: {
    anchor: "4-optional-the-arc-and-orchestration-&-takes-tabs",
    steps: [
      "Draw the energy freehand (or edit Points), or start from a shape: slow burn, build and release, sting, pulse.",
      "Snap peaks to hits: the arc's peaks move onto arrive hits and its lows onto drops, within a bar.",
      "Sections from the arc cuts the sections where it turns, on bar lines (it replaces their names and words).",
      "Mind the flags on the right: a peak or dip inside one section won't be heard (models follow sections, not bars); Split at bar N keeps it.",
    ],
  },
  orch: {
    anchor: "4-optional-the-arc-and-orchestration-&-takes-tabs",
    steps: [
      "Paint who plays in each bar. Step (the default) moves a clicked cell up a level, Shift-click down, and a drag gives every cell the first one's new level; or pick a level and paint it. Keys 1-5 pick the brush; Family adds a row.",
      "It becomes each section's words, loudest first (\"solo horn present, strings under\"); a change inside a section is hatched: the strongest level wins.",
      "On a take, drag across bars to select them: repaint them (made again on its model, the rest kept: ACE-Step), comp them from another take, or lower them in the mix with breakpoints (the take in the mix).",
    ],
  },
};

/** Whether a tab's help strip is open (closed when this browser keeps nothing). */
export function helpOpen(tab: CueTab): boolean {
  try {
    return localStorage.getItem(`${HELP_KEY}.${tab}`) === "1";
  } catch {
    return false;
  }
}

function keepHelp(tab: CueTab, on: boolean) {
  try {
    localStorage.setItem(`${HELP_KEY}.${tab}`, on ? "1" : "0");
  } catch { /* not kept */ }
}

/** A tab's "how to use this tab": its steps and a link to the guide's section. */
function HelpStrip({ tab, onClose }: { tab: CueTab; onClose: () => void }) {
  const h = HELP[tab];
  return (
    <div className="h3-cue-help">
      <ol>{h.steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
      <span className="h3-col" style={{ gap: 4, alignItems: "flex-end" }}>
        <button className="h3-btn h3-icon" title="Hide this help (? shows it again)" aria-label="Hide the help" onClick={onClose}><i className="pi pi-times" /></button>
        <a className="h3-small" href={`${SCORING_URL}#${h.anchor}`} target="_blank" rel="noopener noreferrer">The full guide</a>
      </span>
    </div>
  );
}

let musicTargets: Promise<Target[]> | null = null;
let cuePresets: Promise<CuePreset[]> | null = null;
/** The orchestration grid's rows by episode and cue, either pass (a family off throughout isn't stored, so the window keeps the rows) */
const keptRows = new Map<string, string[]>();

/** The music targets (GET /seriesmith/targets?kind=music), asked once. */
export function useMusicTargets(): Target[] {
  const [list, setList] = useState<Target[]>([]);
  useEffect(() => {
    let live = true;
    musicTargets ??= api().targets({ kind: "music" }).then((r) => r.targets, () => {
      musicTargets = null;
      return [];
    });
    void musicTargets.then((t) => live && setList(t));
    return () => {
      live = false;
    };
  }, []);
  return list;
}

/** The cue presets (GET /seriesmith/presets?kind=cue), asked once a page load. */
function useCuePresets(): CuePreset[] {
  const [list, setList] = useState<CuePreset[]>([]);
  useEffect(() => {
    let live = true;
    cuePresets ??= api().cuePresets().then((r) => r, () => {
      cuePresets = null;
      return [];
    });
    void cuePresets.then((p) => live && setList(p));
    return () => {
      live = false;
    };
  }, []);
  return list;
}

/** The cue the window shows, picked from the episode's cues (and ‹ › to the one before or after),
 * on the same tab; the list is the episode's (loaded when the window first needs it). */
function CuePicker({ ep, cue, tab }: { ep: string; cue: string; tab: CueTab }) {
  const cues = useApp((s) => s.cues[ep]);
  useEffect(() => {
    if (!cues) void loadCues(ep);
  }, [ep, !cues]);
  const list = cues ?? [];
  const i = list.findIndex((c) => c.spec.id === cue);
  const go = (to: string | undefined) => to && to !== cue && openCueFromSpot(to, tab);
  return (
    <span className="h3-row" style={{ gap: 2 }}>
      <button className="h3-btn h3-icon" aria-label="The cue before" title="The cue before" disabled={i <= 0}
        onClick={() => go(list[i - 1]?.spec.id)}><i className="pi pi-angle-left" /></button>
      <select className="h3-in" aria-label="Cue" title="The cue shown: pick another to see it on this tab" value={cue}
        style={{ width: "auto", maxWidth: 260, fontWeight: 600 }} onChange={(e) => go(e.target.value)}>
        {i < 0 && <option value={cue}>{cue}</option>}
        {list.map((c) => <option key={c.spec.id} value={c.spec.id}>{[c.spec.id, c.spec.label, c.spec.kind === "song" ? "song" : ""].filter(Boolean).join(" · ")}</option>)}
      </select>
      <button className="h3-btn h3-icon" aria-label="The cue after" title="The cue after" disabled={i < 0 || i >= list.length - 1}
        onClick={() => go(list[i + 1]?.spec.id)}><i className="pi pi-angle-right" /></button>
    </span>
  );
}

/** A level as words: "3 moderate", "3.5". */
const levelText = (v: number) => (Number.isInteger(v) ? `${v} ${LEVEL_WORDS[v]}` : String(v));
const tn = (n: number) => `t${String(n).padStart(2, "0")}`;

export function CueWindow({ ep, v: opened }: { ep: string; v: ViewerState }) {
  // the pass the editor shows (the toggle switches the cue's plan and mix with it)
  const pass = useApp((s) => s.pass);
  const v = opened.pass === pass ? opened : { ...opened, pass };
  const id = v.cue ?? "";
  const key = cueKey(ep, v.pass, id);
  const res = useApp((s) => s.cue[key]);
  const err = useApp((s) => s.cueError[key]);
  const winRef = useRef<HTMLDivElement>(null);
  const [sel, setSel] = useState<number | null>(null);
  const [tab, setTab] = useState<CueTab>(opened.cueTab ?? "score");
  // a tab asked for again from the scoring window's tabs (the spotting sheet's)
  useEffect(() => {
    if (opened.cueTab) setTab(opened.cueTab);
  }, [opened.cueTab, id]);
  const [brush, setBrush] = useState(ORCH_STEP);
  const [help, setHelp] = useState<Record<CueTab, boolean>>(() => ({ score: helpOpen("score"), arc: helpOpen("arc"), orch: helpOpen("orch") }));
  const showHelp = (on: boolean) => {
    keepHelp(tab, on);
    setHelp((h) => ({ ...h, [tab]: on }));
  };
  // fetched on open, and for each pass it's shown on (its takes' landing fetches it again: cueActions)
  useEffect(() => {
    if (id) void loadCue(ep, pass, id);
  }, [ep, pass, id]);

  // Esc: the section selected, else the window; 1-5 on Orchestration: the brush (off, under, present, lead, step)
  useEffect(() => {
    const el = winRef.current;
    if (!el) return;
    const h = (e: KeyboardEvent) => {
      if (isTyping(e.target)) return;
      const k = Number(e.key);
      if (tab === "orch" && k >= 1 && k <= ORCH_STEP + 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault();
        setBrush(k - 1);
        return;
      }
      if (e.key !== "Escape") return;
      e.preventDefault();
      e.stopPropagation();
      if (sel != null) setSel(null);
      else closeViewer();
    };
    el.addEventListener("keydown", h);
    return () => el.removeEventListener("keydown", h);
  }, [sel, tab]);

  const head = (
    <>
      <i className="pi pi-volume-up" style={{ color: "var(--h3-arc)" }} />
      <CuePicker ep={ep} cue={id} tab={tab} />
      <span className="h3-muted h3-small">{v.pass}</span>
      <ScoringTabs active={tab} cue={id || null} onCueTab={setTab} />
      <button className={`h3-btn h3-icon${help[tab] ? " h3-on" : ""}`} title="How to use this tab" aria-label="How to use this tab" aria-pressed={help[tab]}
        onClick={() => showHelp(!help[tab])}><i className="pi pi-question" /></button>
      <span className="h3-grow" />
      {id && (
        <button className="h3-btn h3-icon" data-cue-delete={id} aria-label={`Delete cue ${id}…`}
          title={`Delete cue ${id}…: its takes go to the episode's _history folder and it comes out of both passes' mixes (asks first; Ctrl+Z can't bring it back). To keep it but not hear it, untick "plays in the mix" on the Refs tab's Music row.`}
          onClick={() => void deleteCue(id)}><i className="pi pi-trash" /></button>
      )}
      <button className="h3-btn" title="Back to the timeline (Esc)" onClick={closeViewer}><i className="pi pi-arrow-left" /> Timeline</button>
      <FullscreenButton />
      <button className="h3-btn h3-icon" title="Close (Esc)" onClick={closeViewer}><i className="pi pi-times" /></button>
    </>
  );
  return (
    <FloatingWindow storageKey={SPOT_RECT_KEY} defaultRect={defaultSpotRect} head={head} winRef={winRef} className="h3-cue-win">
      {!res ? (
        <div className="h3-empty-state">{err ? <span className="h3-err">{id}: {err}</span> : <><i className="pi pi-spin pi-spinner" /> {id}…</>}</div>
      ) : (
        <CueBody ep={ep} v={v} res={res} sel={sel} setSel={setSel} tab={tab} brush={brush} setBrush={setBrush}
          help={help[tab] ? <HelpStrip tab={tab} onClose={() => showHelp(false)} /> : null} />
      )}
    </FloatingWindow>
  );
}

// ---------------------------------------------------------------------------
// the tabs: one bar grid
// ---------------------------------------------------------------------------

/** The arc as the lanes edit it: the spec's points, else the ones the sections imply. */
interface ArcState {
  base: ArcPt[];
  implied: boolean;
  /** the cue's in point is in Play all's cut (else nothing can be anchored) */
  can: boolean;
  commit: (next: ArcPt[]) => void;
}

function CueBody({ ep, v, res, sel, setSel, tab, brush, setBrush, help }: {
  ep: string; v: ViewerState; res: CueResult; sel: number | null; setSel: (i: number | null) => void; tab: CueTab;
  brush: number; setBrush: (b: number) => void; help: ReactNode;
}) {
  const { spec, plan } = res;
  const items = useApp((s) => currentPlaylist(s));
  const fps = useApp((s) => s.status[statusKey(ep, v.pass)]?.fps) || plan?.fps || 24;
  const targets = useMusicTargets();
  const presets = useCuePresets();
  const target = targets.find((t) => t.id === (plan?.target ?? spec.model));
  const [scrollRef, size] = useSize<HTMLDivElement>();
  const [zoom, setZoom] = useState<number | null>(null);
  // each cue opens fitted to the window (null: fit), whatever zoom the last one was left at
  useEffect(() => setZoom(null), [ep, spec.id, v.pass]);
  const [count, setCount] = useState<number>(spec.takes ?? TAKES_DEFAULT);
  const [mode, setMode] = useState<ArcMode>("draw");
  const rowsKey = `${ep}|${spec.id}`;
  const [kept, setKept] = useState<string[] | undefined>(() => keptRows.get(rowsKey));
  useEffect(() => setKept(keptRows.get(rowsKey)), [rowsKey]);
  useEffect(() => setCount(spec.takes ?? TAKES_DEFAULT), [spec.takes]);
  const sections = plan ? editableSections(spec, plan) : [];
  const selected = sel != null && sel < sections.length ? sel : null;

  const inspector = (
    <CueInspector ep={ep} pass={v.pass} res={res} target={target} targets={targets} presets={presets} sel={selected} sections={sections} setSel={setSel} />
  );
  if (!plan) {
    return (
      <div className="h3-cue-body">
        <div className="h3-cue-main h3-empty-state">
          {help}
          <div><b>{spec.id} can't be planned.</b><div className="h3-err" style={{ marginTop: 6 }}>{res.plan_error ?? "no plan"}</div>
            <div className="h3-muted h3-small" style={{ marginTop: 6 }}>Its in and out are anchored to shots of the cut; put them back in the {v.pass} cut, or make the cue again over the shots it plays over.</div></div>
        </div>
        {inspector}
      </div>
    );
  }
  const g = gridOf(plan, spec);
  const t0 = cueStart(items, spec, fps);
  const fit = Math.max(PPS_MIN, (size.width - LAB_W - 16) / g.seconds);
  const pps = Math.min(PPS_MAX, zoom ?? fit);
  const W = Math.ceil(g.seconds * pps);
  const placed = res.takes.find((t) => t.placed === v.pass);

  // the arc: the spec's points, else the ones the sections imply
  const own = t0 == null ? [] : arcPoints(spec, items, t0, fps);
  const arc: ArcState = {
    base: own.length ? own : impliedPoints(g, plan.sections),
    implied: !own.length,
    can: t0 != null,
    commit: (next) => {
      if (t0 == null) return;
      void saveCue(withSpec(spec, { arc: next.length ? arcSpec(next, items, t0, fps) : undefined }));
    },
  };
  const rows = orchestraRows(kept, spec.orchestra);
  const setRows = (r: string[]) => {
    keptRows.set(rowsKey, r);
    setKept(r);
  };

  const side = tab === "arc" ? <ArcReadout res={res} plan={plan} sections={sections} target={target} /> : inspector;
  return (
    <div className="h3-cue-body">
      <div className="h3-cue-main">
        {help}
        <div className="h3-cue-bar">
          <span className="h3-mono h3-small" title={`the cue's exact tempo (the model is asked ${plan.fit.ask_bpm}, stretched by ${plan.fit.stretch})`}>
            {plan.fit.bpm} bpm · {meterText(spec.meter) ?? "4/4"} · {plan.bars} bars · {fmtClock(plan.seconds)}
          </span>
          <span className="h3-muted h3-small" title="the bars before the cue's in point, and after its out point">pre-roll {plan.preroll.toFixed(2)} s</span>
          {placed && <span className="h3-badge h3-b-ok" title={`${tn(placed.take)} is the cue's item on the music track of the ${v.pass} mix`}>{tn(placed.take)} in the mix</span>}
          <span className="h3-grow" />
          <label className="h3-row h3-small" style={{ gap: 4 }} title="Zoom (double-click: fit)">
            <i className="pi pi-search-plus h3-muted" />
            <input type="range" min={PPS_MIN} max={PPS_MAX} step={1} value={pps} onChange={(e) => setZoom(Number(e.target.value))}
              onDoubleClick={() => setZoom(null)} style={{ width: 90 }} />
          </label>
          <input className="h3-in" type="number" min={1} max={16} value={count} style={{ width: 46 }} aria-label="Takes to render"
            onChange={(e) => setCount(Math.max(1, Math.min(16, Math.round(Number(e.target.value) || 1))))} />
          <button className="h3-btn h3-primary" style={{ width: "auto" }} title="Render this many takes of the cue, each its own seed; they are measured and ranked as they land"
            onClick={() => void renderCue(count)}>
            <i className="pi pi-play" /> Render {count} take{count === 1 ? "" : "s"}
          </button>
        </div>
        {tab === "arc" && <ArcTools g={g} plan={plan} spec={spec} arc={arc} mode={mode} setMode={setMode} />}
        {tab === "orch" && (
          <div className="h3-cue-bar h3-cue-tools">
            <label className="h3-row h3-small" style={{ gap: 4 }}
              title={brush === ORCH_STEP
                ? "Step: a click moves a cell up a level (off, under, present, lead, off), Shift-click down; a drag gives every cell the first one's new level. Keys 1-5 pick the brush."
                : `Paint ${ORCH_LEVELS[brush]}: click a cell, or drag across bars and rows. Keys 1-5 pick the brush.`}>
              <span className="h3-muted">Brush</span>
              {brush === ORCH_STEP ? <i className="pi pi-sort-alt" /> : <i className={`h3-cue-swatch h3-lv-${brush}`} />}
              <select className="h3-in" aria-label="Brush" value={String(brush)} onChange={(e) => setBrush(Number(e.target.value))} style={{ width: "auto" }}>
                {[...ORCH_LEVELS, "step"].map((name, k) => <option key={k} value={String(k)}>{k + 1} - {name}</option>)}
              </select>
            </label>
            <button className="h3-btn" title="Add a row for another family (rename it in its label)" onClick={() => {
              let n = rows.length + 1;
              while (rows.includes(`family ${n}`)) n++;
              setRows([...rows, `family ${n}`]);
            }}><i className="pi pi-plus" /> Family</button>
            <span className="h3-small h3-muted" title="A section is the finest the models follow: each is told each family's strongest level in it">
              A change inside a section isn't followed: the strongest level wins (cells marked <i className="h3-cue-swatch h3-held" />)
            </span>
          </div>
        )}
        <div className="h3-cue-scroll" ref={scrollRef}>
          <GridView g={g} pps={pps} W={W} viewW={Math.max(320, size.width - LAB_W - 24)} plan={plan} ep={ep} v={v} items={items} t0={t0} spec={spec}
            sections={sections} sel={selected} setSel={setSel} takes={res.takes} tab={tab} arc={arc} mode={mode} rows={rows} setRows={setRows} brush={brush} />
        </div>
      </div>
      {side}
    </div>
  );
}

function Lane({ label, title, h, W, children, cls, onPointerDown, onDoubleClick, onContextMenu, laneRef }: {
  label: ReactNode; title?: string; h: number; W: number; children?: ReactNode; cls?: string;
  onPointerDown?: (e: RPointerEvent<HTMLDivElement>) => void;
  onDoubleClick?: (e: RMouseEvent<HTMLDivElement>) => void;
  onContextMenu?: (e: RMouseEvent<HTMLDivElement>) => void;
  laneRef?: React.Ref<HTMLDivElement>;
}) {
  return (
    <div className={`h3-cue-row${cls ? ` ${cls}` : ""}`} style={{ height: h }}>
      <div className="h3-cue-lab" style={{ width: LAB_W }} title={title}>{label}</div>
      <div ref={laneRef} className="h3-cue-lane" style={{ width: W }} title={title} onPointerDown={onPointerDown} onDoubleClick={onDoubleClick} onContextMenu={onContextMenu}>
        {children}
      </div>
    </div>
  );
}

function GridView({ g, pps, W, viewW, plan, ep, v, items, t0, spec, sections, sel, setSel, takes, tab, arc, mode, rows, setRows, brush }: {
  g: Grid; pps: number; W: number; viewW: number; plan: CuePlan; ep: string; v: ViewerState; items: PlayItem[]; t0: number | null;
  spec: CueSpec; sections: CueSection[]; sel: number | null; setSel: (i: number | null) => void; takes: CueTake[];
  tab: CueTab; arc: ArcState; mode: ArcMode; rows: string[]; setRows: (r: string[]) => void; brush: number;
}) {
  const x = (tau: number) => tauX(g, tau, pps);
  const st = useApp((s) => s.status[statusKey(ep, v.pass)]);
  const other = useApp((s) => s.status[statusKey(ep, v.pass === "proxy" ? "final" : "proxy")]);
  const [edge, setEdge] = useState<{ i: number; sections: CueSection[] } | null>(null);
  const [sectMenu, setSectMenu] = useState<SectMenu | null>(null);
  const sectRef = useRef<HTMLDivElement>(null);
  const [playing, setPlaying] = useState<{ take: number; tau: number } | null>(null);
  const [range, setRange] = useState<{ take: number; bars: [number, number] } | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);
  useEffect(() => () => audio.current?.pause(), []);
  const editable = tab === "score";

  // ---- the picture ----
  const clips = t0 == null ? [] : clipsOver(items, t0, g);

  // ---- sections: drag an edge (the Score tab; the others show them for reference) ----
  const shown = edge?.sections ?? sections;
  const edges = sectionEdges(shown.map((s) => ({ bars: s.bars ?? 1 })));
  const onEdgeDown = (e: RPointerEvent<HTMLElement>, i: number) => {
    if (e.button !== 0) return;
    e.stopPropagation();
    e.preventDefault();
    const x0 = e.clientX;
    const from = edges[i + 1] * g.bar * pps;
    let next: CueSection[] | null = null;
    trackPointer((ev) => {
      next = moveEdge(sections, i, (from + ev.clientX - x0) / (g.bar * pps));
      setEdge({ i, sections: next ?? sections });
    }, (cancelled) => {
      setEdge(null);
      if (cancelled || !next) return;
      const moved = next;
      void saveCue(withSpec(spec, { sections: moved }),
        { sections: plan.sections.map((s, k) => ({ ...s, bars: moved[k]?.bars ?? s.bars })) });
    });
  };

  // ---- sections: double-click splits one at the nearest bar line; right-click: split, merge, reset ----
  const barPx = g.bar * pps;
  const laneX = (e: { clientX: number }) => e.clientX - (sectRef.current?.getBoundingClientRect().left ?? 0);
  const saveSections = (next: CueSection[] | null) => {
    if (next) void saveCue(withSpec(spec, { sections: next }));
  };
  const split = (i: number, bar: number) => saveSections(splitSection(withEnergies(sections, plan.sections), i, bar, plan.arc));
  const merge = (i: number) => {
    setSel(null);
    saveSections(mergeSections(withEnergies(sections, plan.sections), i));
  };
  const onSectDouble = (e: RMouseEvent<HTMLDivElement>) => {
    if (!editable) return;
    const at = splitPoint(sections, laneX(e), barPx);
    if (at) split(at.i, at.bar);
  };
  const onSectMenu = (e: RMouseEvent<HTMLDivElement>) => {
    if (!editable) return;
    e.preventDefault();
    e.stopPropagation();
    const x = laneX(e);
    setSectMenu({ x: e.clientX, y: e.clientY, i: sectionAt(sections, x / barPx), split: splitPoint(sections, x, barPx) });
  };
  const resetSections = () => {
    if (!confirm(`Work ${spec.id}'s sections out from the hits again? Their names, words, energies and lyrics go.`)) return;
    setSel(null);
    void saveCue(withSpec(spec, { sections: undefined }));
  };

  // ---- a take played: the playhead on the grid ----
  const play = (t: CueTake) => {
    const a = audio.current ?? (audio.current = new Audio());
    if (playing?.take === t.take) {
      a.pause();
      setPlaying(null);
      return;
    }
    if (!t.file || !t.measured) return;
    const m = t.measured;
    a.src = api().fileUrl(ep, t.file);
    a.currentTime = m.downbeat;
    void a.play().catch(() => setPlaying(null));
    setPlaying({ take: t.take, tau: -g.preroll });
    let raf = 0;
    const tick = () => {
      if (a.paused || a.ended || audio.current !== a) {
        setPlaying((p) => (p?.take === t.take ? null : p));
        return;
      }
      setPlaying({ take: t.take, tau: a.currentTime - m.downbeat - g.preroll });
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    a.onpause = () => cancelAnimationFrame(raf);
  };

  // ---- bars of a take selected by dragging across them (Orchestration & takes) ----
  const onRangeDown = (e: RPointerEvent<HTMLDivElement>, t: CueTake) => {
    if (e.button !== 0) return;
    e.preventDefault();
    const left = e.currentTarget.getBoundingClientRect().left;
    const x0 = e.clientX - left;
    setRange({ take: t.take, bars: barSpan(g, x0, x0, pps) });
    trackPointer((ev) => setRange({ take: t.take, bars: barSpan(g, x0, ev.clientX - left, pps) }), (cancelled) => {
      if (cancelled) setRange(null);
    });
  };

  const bars = Array.from({ length: g.bars }, (_, b) => b);
  const order = ranks(takes);

  // the bar lines, the pre-roll and the tail, under the lanes (the head's and the takes')
  const under = (
    <div className="h3-cue-under" style={{ left: LAB_W, width: W }}>
      {bars.map((b) => <div key={b} className="h3-cue-barline" style={{ left: b * g.bar * pps }} />)}
      <div className="h3-cue-outside" style={{ left: 0, width: x(0) }} />
      <div className="h3-cue-outside" style={{ left: x(plan.span), width: Math.max(0, W - x(plan.span)) }} />
      <div className="h3-cue-inout" style={{ left: x(0) }} />
      <div className="h3-cue-inout" style={{ left: x(plan.span) }} />
      {playing && <div className="h3-cue-playhead" style={{ left: x(playing.tau) }} />}
    </div>
  );

  const picture = (
    <Lane label="Picture" h={PIC_H} W={W} title={`${spec.in.shot} frame ${spec.in.frame} to ${spec.out.shot} frame ${spec.out.frame}: the shots it plays over, with the pre-roll and tail`}>
      {clips.map(({ it, a, b }) => {
        const s = st?.shots.find((z) => z.shot === it.shot);
        const take = s ? clipTake(s, s.cut.placeholder ? other : undefined) : undefined;
        return (
          <div key={it.shot} className="h3-cue-pic" style={{ left: x(a), width: Math.max(2, x(b) - x(a)), ...mediaStyle(ep, take, null) }}
            title={`${it.shot}${take ? ` ${tn(take.take)}` : ""}`}>
            <span>{it.shot}</span>
          </div>
        );
      })}
      {t0 == null && <span className="h3-muted h3-small" style={{ padding: 4 }}>{spec.in.shot} isn't in Play all's cut</span>}
    </Lane>
  );
  const hits = (
    <Lane label="Hits" h={HITS_H} W={W} title="The mix's hits in the cue's span: the bar and beat each lands on, and how far off its line the tempo fit leaves it (frames)">
      {plan.hits.map((h, i) => {
        const bb = barBeat(g, h.t);
        const e = plan.fit.errors[i] ?? 0;
        return (
          <div key={h.id} className={`h3-cue-hit h3-hit-${h.kind}${h.must ? "" : " h3-hit-may"}${Math.abs(e) > 1 ? " h3-cue-off" : ""}`} style={{ left: x(h.t) }}
            title={`${h.name} (${h.id}) · ${h.kind}: ${HIT_KIND_TITLE[h.kind]}\nlands on bar ${bb.bar} beat ${bb.beat} · ${e > 0 ? "+" : ""}${e} frames off the line${h.must ? "" : " · may miss"}`}>
            <span>{h.name}</span>
            <span className="h3-mono">{bb.label} · {e > 0 ? "+" : ""}{e}f</span>
          </div>
        );
      })}
      {!plan.hits.length && <span className="h3-muted h3-small" style={{ padding: 6 }}>No hits in its span: double-click the timeline's hits lane to add one</span>}
    </Lane>
  );
  const ruler = (
    <Lane label={meterText(spec.meter) ?? "4/4"} h={RULER_H} W={W} cls="h3-cue-ruler" title={`Bars at ${plan.fit.bpm} bpm, beats as ticks`}>
      {bars.map((b) => (
        <div key={b} className="h3-cue-bnum" style={{ left: b * g.bar * pps, width: g.bar * pps }}>
          {g.bar * pps > 14 && <span>{b + 1}</span>}
          {g.beat * pps > 5 && Array.from({ length: g.meter - 1 }, (_, k) => <i key={k} style={{ left: (k + 1) * g.beat * pps }} />)}
        </div>
      ))}
    </Lane>
  );
  const sectionLane = (
    <Lane label="Sections" h={SECT_H} W={W} laneRef={sectRef} onDoubleClick={onSectDouble} onContextMenu={onSectMenu}
      title={editable
        ? "The cue's sections, in whole bars: click one to edit it (the inspector), drag an edge to move it, double-click to split one at that bar line; right-click: split, merge, reset from the hits"
        : "The cue's sections, for reference (edit them in the Score tab)"}>
      {shown.map((s, i) => (
        <div key={i} className={`h3-cue-sect${editable && sel === i ? " h3-on" : ""}${editable ? "" : " h3-ro"}`} style={{ left: edges[i] * g.bar * pps, width: (edges[i + 1] - edges[i]) * g.bar * pps }}
          title={`${s.name}: ${s.bars} bar${s.bars === 1 ? "" : "s"}${s.words ? ` · ${s.words}` : ""} · energy ${plan.sections[i]?.from ?? "?"} to ${plan.sections[i]?.to ?? "?"}`}
          onClick={editable ? (e) => {
            e.stopPropagation();
            setSel(sel === i ? null : i);
          } : undefined}>
          <span>{s.name}</span>
          <span className="h3-muted">{s.bars}</span>
          {editable && i < shown.length - 1 && <div className="h3-cue-edge" title="Drag: move this edge (whole bars; Esc cancels)" onPointerDown={(e) => onEdgeDown(e, i)} onClick={(e) => e.stopPropagation()} />}
        </div>
      ))}
      {edge && <div className="h3-cue-tip" style={{ left: edges[edge.i + 1] * g.bar * pps + 6 }}>bar {edges[edge.i + 1] + 1}</div>}
      {sectMenu && (
        <SectionMenu menu={sectMenu} sections={sections} own={!!spec.sections?.length} onClose={() => setSectMenu(null)}
          split={split} merge={merge} edit={(i) => setSel(i)} reset={resetSections} />
      )}
    </Lane>
  );

  return (
    <div className="h3-cue-grid" style={{ width: LAB_W + W }}>
      {under}
      {/* the head's lanes stay in view over the takes */}
      <div className="h3-cue-head">
        {under}
        {tab !== "orch" && picture}
        {tab !== "orch" && hits}
        {ruler}
        {sectionLane}
        {tab === "score" && <ArcLane g={g} pps={pps} W={W} h={ARC_H} plan={plan} spec={spec} arc={arc} mode="points" />}
        {tab === "arc" && <ArcLane g={g} pps={pps} W={W} h={ARC_BIG_H} plan={plan} spec={spec} arc={arc} mode={mode} />}
        {tab === "orch" && <OrchestraRows g={g} pps={pps} W={W} spec={spec} plan={plan} rows={rows} setRows={setRows} brush={brush} />}
      </div>

      {tab !== "arc" && takes.map((t, i) => (
        <TakeRow key={t.take} ep={ep} t={t} rank={order[i]} g={g} pps={pps} W={W} viewW={viewW} plan={plan} pass={v.pass}
          playing={playing?.take === t.take} onPlay={() => play(t)}
          select={tab === "orch" ? {
            bars: range?.take === t.take ? range.bars : null, onDown: (e) => onRangeDown(e, t), clear: () => setRange(null),
            takes, spec, t0,
          } : undefined} />
      ))}
      {tab !== "arc" && !takes.length && (
        <Lane label="Takes" h={TAKE_H} W={W}>
          <span className="h3-muted h3-small" style={{ padding: 8 }}>
            No takes yet: Render makes several, each measured against the hits and the arc, best first.
            {" "}New to this? <a href={SCORING_URL} target="_blank" rel="noopener noreferrer">Read Scoring an episode</a>
          </span>
        </Lane>
      )}
    </div>
  );
}

/** A section's menu: where it was asked, the section there and the split it would make (null: on an edge). */
interface SectMenu {
  x: number;
  y: number;
  i: number;
  split: { i: number; bar: number } | null;
}

/** The Sections lane's menu at the pointer: split there, merge with a neighbour, edit, the sections from the hits again. */
function SectionMenu({ menu, sections, own, onClose, split, merge, edit, reset }: {
  menu: SectMenu; sections: CueSection[]; own: boolean; onClose: () => void;
  split: (i: number, bar: number) => void; merge: (i: number) => void; edit: (i: number) => void; reset: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ left: menu.x, top: menu.y });
  useLayoutEffect(() => {
    const r = ref.current?.getBoundingClientRect();
    if (r) setPos(onScreen(menu.x, menu.y, r));
  }, [menu]);
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
  const run = (fn: () => void) => () => {
    onClose();
    fn();
  };
  const { i, split: at } = menu;
  const s = sections[i];
  const prev = sections[i - 1];
  const next = sections[i + 1];
  return (
    <div ref={ref} className="h3-menu h3-snd-pop h3-cue-sectmenu" style={pos} onClick={(e) => e.stopPropagation()} onPointerDown={(e) => e.stopPropagation()}
      onDoubleClick={(e) => e.stopPropagation()} onContextMenu={(e) => {
        e.preventDefault();
        e.stopPropagation();
      }}>
      <div className="h3-menu-head">{s?.name ?? "section"} · section {i + 1} of {sections.length}</div>
      <button disabled={!at}
        title={at ? `Two sections: ${sections[at.i]?.name} to bar ${at.bar}, the rest from bar ${at.bar + 1} (both keep its words and energies)` : "On an edge or the cue's end: right-click inside a section, away from its edges"}
        onClick={run(() => at && split(at.i, at.bar))}>
        <i className="pi pi-arrows-h" /> {at ? `Split at bar ${at.bar + 1}` : "Split here"}
      </button>
      <button disabled={!prev} title={prev ? `One section: ${prev.name}'s name and words, the bars of both` : "It's the first section"} onClick={run(() => merge(i - 1))}>
        <i className="pi pi-angle-double-left" /> Merge with previous
      </button>
      <button disabled={!next} title={next ? `One section: ${s?.name}'s name and words, the bars of both` : "It's the last section"} onClick={run(() => merge(i))}>
        <i className="pi pi-angle-double-right" /> Merge with next
      </button>
      <button title="Its name, words and energies in the inspector" onClick={run(() => edit(i))}>
        <i className="pi pi-pencil" /> Edit
      </button>
      <button disabled={!own} title={own ? "Clear the cue's sections: they're worked out from the hits again (asks first)" : "They're the hits' already"} onClick={run(reset)}>
        <i className="pi pi-refresh" /> Reset sections from the hits
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// the arc: its lane (the Score tab's, and the Arc tab's large), its tools, what the model hears
// ---------------------------------------------------------------------------

function ArcLane({ g, pps, W, h, plan, spec, arc, mode }: {
  g: Grid; pps: number; W: number; h: number; plan: CuePlan; spec: CueSpec; arc: ArcState; mode: ArcMode;
}) {
  const x = (tau: number) => tauX(g, tau, pps);
  const [drag, setDrag] = useState<ArcPt[] | null>(null);
  const [stroke, setStroke] = useState<ArcPt[] | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  const { base, implied } = arc;
  const pts = drag ?? base;
  const laneXY = (ev: { clientX: number; clientY: number }) => {
    const r = ref.current!.getBoundingClientRect();
    return { tau: xTau(g, ev.clientX - r.left, pps), level: yLevel(ev.clientY - r.top, h) };
  };

  // points: drag one, double-click adds one, right-click removes one
  const onPointDown = (e: RPointerEvent<SVGElement>, i: number) => {
    if (e.button !== 0 || mode !== "points") return;
    e.stopPropagation();
    e.preventDefault();
    let next: ArcPt[] | null = null;
    trackPointer((ev) => {
      const p = laneXY(ev);
      next = movePoint(base, i, g, p.tau, p.level);
      setDrag(next);
    }, (cancelled) => {
      setDrag(null);
      if (!cancelled && next) arc.commit(next);
    });
  };
  const onDouble = (e: RMouseEvent<HTMLDivElement>) => {
    if (!arc.can || mode !== "points") return;
    const p = laneXY(e);
    arc.commit(addPoint(base, g, p.tau, p.level));
  };
  const onPointMenu = (e: RMouseEvent<SVGElement>, i: number) => {
    e.preventDefault();
    e.stopPropagation();
    if (mode === "points") arc.commit(removePoint(base, i));
  };
  // draw: a freehand stroke, on beats and simplified, over the points it spans
  const onDraw = (e: RPointerEvent<HTMLDivElement>) => {
    if (mode !== "draw" || e.button !== 0 || !arc.can) return;
    e.preventDefault();
    const samples = [laneXY(e)];
    setStroke(samples.slice());
    trackPointer((ev) => {
      samples.push(laneXY(ev));
      setStroke(samples.slice());
    }, (cancelled) => {
      setStroke(null);
      if (!cancelled) arc.commit(mergeStroke(base, drawnPoints(samples, g)));
    });
  };

  const arcLine = plan.arc.map((lv, b) => `${(b + 0.5) * g.bar * pps},${levelY(lv, h)}`).join(" ");
  const dragLine = drag ? drag.map((p) => `${x(p.tau)},${levelY(p.level, h)}`).join(" ") : null;
  const strokeLine = stroke ? stroke.map((p) => `${x(p.tau)},${levelY(p.level, h)}`).join(" ") : null;
  const how = mode === "draw"
    ? "Draw: drag across the lane, the stroke put on beats and simplified into points (it replaces the points it spans)"
    : "Drag a point (to a beat, half a level); double-click: a point; right-click a point: remove it";
  return (
    <Lane label={<>Intensity{!implied && <button className="h3-snd-btn" title="Clear the points: the sections' energies again" onClick={() => void saveCue(withSpec(spec, { arc: undefined }))}><i className="pi pi-times" /></button>}</>}
      h={h} W={W} cls={`h3-cue-arc${mode === "draw" ? " h3-cue-draw" : ""}`} laneRef={ref} onDoubleClick={onDouble} onPointerDown={onDraw}
      title={`The arc: energy 1 (sparse) to 5 (fortissimo), which the prompt tells the model and the takes are ranked against. ${how}.${implied ? "\nNo points yet: the line the sections imply; an edit makes them the cue's own." : ""}\nNot the mix's gain: that's the timeline's.`}>
      <svg width={W} height={h} className="h3-cue-svg">
        {[1, 2, 3, 4, 5].map((lv) => <line key={lv} x1={0} x2={W} y1={levelY(lv, h)} y2={levelY(lv, h)} className="h3-cue-level" />)}
        {h > ARC_H && [1, 2, 3, 4, 5].map((lv) => <text key={lv} x={3} y={levelY(lv, h) - 2} className="h3-cue-lvtext">{LEVEL_WORDS[lv]}</text>)}
        <polyline points={arcLine} className={`h3-cue-arcline${dragLine || strokeLine ? " h3-dim" : ""}`} />
        {dragLine && <polyline points={dragLine} className="h3-cue-arcline" />}
        {strokeLine && <polyline points={strokeLine} className="h3-cue-stroke" />}
        {!implied && !dragLine && <polyline points={pts.map((p) => `${x(p.tau)},${levelY(p.level, h)}`).join(" ")} className="h3-cue-ptline" />}
        {pts.map((p, i) => (
          <circle key={i} cx={x(p.tau)} cy={levelY(p.level, h)} r={4.5} className={`h3-cue-pt${implied && !drag ? " h3-implied" : ""}${mode === "draw" ? " h3-passive" : ""}`}
            onPointerDown={(e) => onPointDown(e, i)} onContextMenu={(e) => onPointMenu(e, i)} onDoubleClick={(e) => e.stopPropagation()}>
            <title>{`${barBeat(g, p.tau).label} · ${levelText(p.level)}${implied ? " (from the sections)" : ""}`}</title>
          </circle>
        ))}
      </svg>
    </Lane>
  );
}

/** The Arc tab's tools: draw or points, smooth, preset shapes, peaks to hits, sections from the arc. */
function ArcTools({ g, plan, spec, arc, mode, setMode }: {
  g: Grid; plan: CuePlan; spec: CueSpec; arc: ArcState; mode: ArcMode; setMode: (m: ArcMode) => void;
}) {
  const snapHits = plan.hits.filter((h) => !h.ends && h.kind !== "accent");
  const shapes = ARC_SHAPES.filter((s) => s.id !== "from the script" || !!plan.notes?.length);
  const snap = () => {
    const r = snapToHits(arc.base, snapHits, g);
    if (!r.moved) {
      host().toast("info", "Nothing to snap", "No peak or low of the arc is within a bar of an arrive, drop or turn hit.");
      return;
    }
    arc.commit(r.points);
    host().toast("success", `${r.moved} point${r.moved === 1 ? "" : "s"} snapped to hits`, "Each peak to an arrive or turn, each low to a drop or turn, within a bar.");
  };
  const fromArc = () => {
    const given = spec.sections?.length ?? 0;
    if (given && !confirm(`Replace the cue's ${given} section${given === 1 ? "" : "s"} with ones cut at the arc's peaks and lows? Their names and words go.`)) return;
    void saveCue(withSpec(spec, { sections: sectionsFromArc(arc.base, g) }));
  };
  return (
    <div className="h3-cue-bar h3-cue-tools">
      <span className="h3-seg" title="How the lane is edited">
        <button className={mode === "draw" ? "h3-on" : ""} title="Draw freehand: the stroke is put on beats and simplified into points" onClick={() => setMode("draw")}><i className="pi pi-pencil" /> Draw</button>
        <button className={mode === "points" ? "h3-on" : ""} title="Points: drag one, double-click adds one, right-click removes one" onClick={() => setMode("points")}><i className="pi pi-circle" /> Points</button>
      </span>
      <button className="h3-btn" disabled={!arc.can || arc.base.length < 3} title="Smooth the points: each eased toward its neighbours" onClick={() => arc.commit(smoothPoints(arc.base))}>Smooth</button>
      <span className="h3-small h3-muted">Shapes</span>
      {shapes.map((s) => (
        <button key={s.id} className="h3-btn" disabled={!arc.can} title={`${s.title}. Replaces the points over the cue's span.`}
          onClick={() => arc.commit(presetPoints(s.id, g, plan.span))}>{s.id}</button>
      ))}
      <span className="h3-grow" />
      <button className="h3-btn" disabled={!arc.can || !snapHits.length}
        title={snapHits.length ? "Move each peak of the arc to the nearest arrive (or turn) hit, each low to the nearest drop (or turn), within a bar" : "No arrive, drop or turn hits in the cue's span"}
        onClick={snap}><i className="pi pi-bolt" /> Snap peaks to hits</button>
      <button className="h3-btn" disabled={arc.implied}
        title={arc.implied ? "Draw an arc first: with no points of its own, the arc is the sections'" : "Cut the sections at the arc's peaks and lows (on bar lines), each its energy from and to from the arc"}
        onClick={fromArc}>Sections from the arc</button>
    </div>
  );
}

/** Beside the Arc tab: what the model will hear, section by section, and the detail it can't follow. */
function ArcReadout({ res, plan, sections, target }: { res: CueResult; plan: CuePlan; sections: CueSection[]; target: Target | undefined }) {
  const { spec } = res;
  const edges = sectionEdges(plan.sections);
  const flags = arcFlags(plan.arc, plan.sections);
  // with no points of its own the arc is the sections', so the words say what it does
  const off = spec.arc?.length ? wordsOffArc(plan.arc, plan.sections) : [];
  const half = (x: number | undefined) => (x == null ? "?" : String(Math.round(x * 2) / 2));
  const split = (i: number, bar: number) => {
    const next = splitSection(withEnergies(sections, plan.sections), i, bar, plan.arc);
    if (next) void saveCue(withSpec(spec, { sections: next }));
  };
  return (
    <div className="h3-cue-side h3-cue-readout">
      <div className="h3-row" style={{ gap: 6 }}><b>What the model hears</b></div>
      <div className="h3-small h3-muted">Sections are the finest it follows: each is told its words and its energy, not the curve. The takes are ranked against the curve, and a picked one is fitted to it with gain.</div>
      {plan.sections.map((s, i) => (
        <div key={i} className="h3-cue-read">
          <div className="h3-row" style={{ gap: 6 }}><b>{s.name}</b><span className="h3-muted h3-small">{barsLabel([edges[i], edges[i + 1]])}</span></div>
          <div className="h3-mono h3-small">{sectionWords(s)}</div>
          {flags.filter((f) => f.section === i).map((f) => (
            <div key={`${f.kind}${f.bar}`} className="h3-cue-flag">
              <i className="pi pi-exclamation-triangle" /> a {f.kind} at bar {f.bar + 1} inside {s.name}: split the section to keep it
              <button className="h3-btn" style={{ width: "auto" }} title={`Split ${s.name} at bar ${f.bar + 1}, so the ${f.kind} is an edge the model follows`}
                onClick={() => split(i, f.bar)}>Split at bar {f.bar + 1}</button>
            </div>
          ))}
          {off.includes(i) && (
            <div className="h3-cue-flag">
              <i className="pi pi-exclamation-triangle" /> the arc goes {half(plan.arc[edges[i]])} to {half(plan.arc[Math.min(edges[i + 1], plan.arc.length) - 1])} here, the words {s.from} to {s.to}: Sections from the arc follows it
            </div>
          )}
        </div>
      ))}
      <div className="h3-cue-prompt">
        <div className="h3-cue-h">What {target?.short ?? target?.label ?? plan.target} is told</div>
        <pre className="h3-mono">{plan.prompt.prompt}</pre>
        {typeof plan.prompt.values?.lyrics === "string" && plan.prompt.values.lyrics && (
          <>
            <div className="h3-cue-h">Its lyrics (the sections)</div>
            <pre className="h3-mono">{plan.prompt.values.lyrics}</pre>
          </>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// the orchestration grid
// ---------------------------------------------------------------------------

function OrchestraRows({ g, pps, W, spec, plan, rows, setRows, brush }: {
  g: Grid; pps: number; W: number; spec: CueSpec; plan: CuePlan; rows: string[]; setRows: (r: string[]) => void; brush: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [paint, setPaint] = useState<{ r0: number; r1: number; b0: number; b1: number; level: number } | null>(null);
  const orch: Orchestra = spec.orchestra ?? {};
  const held = heldCells(orch, plan.sections);
  const save = (next: Orchestra) => void saveCue(withSpec(spec, { orchestra: Object.keys(next).length ? next : undefined }));
  const cell = (ev: { clientX: number; clientY: number }) => {
    const r = ref.current!.getBoundingClientRect();
    const x = ev.clientX - r.left - LAB_W;
    return {
      x,
      row: Math.min(rows.length - 1, Math.max(0, Math.floor((ev.clientY - r.top) / ORCH_H))),
      bar: Math.min(g.bars - 1, Math.max(0, Math.floor(x / (g.bar * pps)))),
    };
  };
  // a stroke: the cells from where it began to where it is (rows and bars), one save
  const onDown = (e: RPointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    const c = cell(e);
    if (c.x < 0) return;
    e.preventDefault();
    // the level the stroke paints: the brush's, or the first cell's stepped (Shift: down)
    let p = { r0: c.row, r1: c.row, b0: c.bar, b1: c.bar, level: strokeLevel(orch, rows[c.row], c.bar, brush, e.shiftKey) };
    setPaint(p);
    trackPointer((ev) => {
      const d = cell(ev);
      p = { ...p, r1: d.row, b1: d.bar };
      setPaint(p);
    }, (cancelled) => {
      setPaint(null);
      if (cancelled) return;
      const fams = rows.slice(Math.min(p.r0, p.r1), Math.max(p.r0, p.r1) + 1);
      const next = paintOrchestra(orch, fams, p.b0, p.b1, p.level);
      if (JSON.stringify(next) !== JSON.stringify(trimOrchestra(orch))) save(next);
    });
  };
  const inStroke = (r: number, b: number) => !!paint && r >= Math.min(paint.r0, paint.r1) && r <= Math.max(paint.r0, paint.r1)
    && b >= Math.min(paint.b0, paint.b1) && b <= Math.max(paint.b0, paint.b1);
  const rename = (fam: string, to: string) => {
    const name = familyName(to);
    if (!name || name === fam) return;
    const next = renameFamily(orch, fam, name);
    if (!next || rows.includes(name)) {
      host().toast("warn", `There's a ${name} row already`, "Each family is one row.");
      return;
    }
    setRows(rows.map((r) => (r === fam ? name : r)));
    if (fam in orch) save(next);
  };
  const remove = (fam: string) => {
    setRows(rows.filter((r) => r !== fam));
    if (fam in orch) save(removeFamily(orch, fam));
  };
  return (
    <div ref={ref} className="h3-cue-orch" onPointerDown={onDown}>
      {rows.map((fam, r) => (
        <Lane key={fam} h={ORCH_H} W={W} cls="h3-cue-orow"
          label={(
            <span className="h3-row" style={{ gap: 2, minWidth: 0 }} onPointerDown={(e) => e.stopPropagation()}>
              <Draft label={`Family ${fam}`} value={fam} onCommit={(to) => rename(fam, to)} />
              <button className="h3-snd-btn" title={`Remove the ${fam} row`} onClick={() => remove(fam)}><i className="pi pi-times" /></button>
            </span>
          )}
          title={`${fam}: paint who plays in each bar (off, under, present, lead)`}>
          {Array.from({ length: g.bars }, (_, b) => {
            const lv = paint && inStroke(r, b) ? paint.level : orch[fam]?.[b] ?? 0;
            const isHeld = !inStroke(r, b) && held.has(`${fam}|${b}`);
            if (!lv && !isHeld) return null;
            return (
              <div key={b} className={`h3-cue-cell h3-lv-${lv}${isHeld ? " h3-held" : ""}`} style={{ left: b * g.bar * pps, width: g.bar * pps }}
                title={`${fam}, bar ${b + 1}: ${ORCH_LEVELS[lv]}${isHeld ? " (heard as its strongest in this section: a change inside a section isn't followed)" : ""}`} />
            );
          })}
        </Lane>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// a take
// ---------------------------------------------------------------------------

/** A take's bars selected (Orchestration & takes): the selection, the drag that makes it, and what the fixes need. */
interface TakeSelect {
  bars: [number, number] | null;
  onDown: (e: RPointerEvent<HTMLDivElement>) => void;
  clear: () => void;
  takes: CueTake[];
  spec: CueSpec;
  t0: number | null;
}

/** A take: its waveform on the grid with its loudness per bar over the arc, then what was measured. */
function TakeRow({ ep, t, rank, g, pps, W, viewW, plan, pass, playing, onPlay, select }: {
  ep: string; t: CueTake; rank: number | null; g: Grid; pps: number; W: number; viewW: number; plan: CuePlan; pass: string; playing: boolean; onPlay: () => void;
  select?: TakeSelect;
}) {
  const m = t.measured;
  const ok = t.status === "ok" && !!m && !!t.file;
  const q = ok ? { ep, path: t.file!, bins: Math.max(16, Math.min(4096, Math.round(W / 2))), start: m!.downbeat, end: m!.downbeat + g.seconds, version: t.finished ?? null } : null;
  const peaks = usePeaks(q);
  const name = tn(t.take);
  const lv = m ? levelsAsEnergy(m.levels) : [];
  const levelLine = lv.map((e, b) => `${(b + 0.5) * g.bar * pps},${levelY(e, TAKE_H, 3)}`).join(" ");
  const arcLine = plan.arc.map((e, b) => `${(b + 0.5) * g.bar * pps},${levelY(e, TAKE_H, 3)}`).join(" ");
  const stale = t.stale ?? [];
  const placed = t.placed === pass;
  const range = select?.bars ?? null;
  const label = (
    <span className="h3-col" style={{ gap: 0 }}>
      <b>{rank != null ? `#${rank} ` : ""}{name}</b>
      <span className={`h3-small ${t.status === "failed" ? "h3-err" : "h3-muted"}`}>{t.status === "ok" ? (placed ? "in the mix" : t.comp ? "comp" : t.repaint ? "repaint" : "") : t.status === "queued" && t.repaint ? "repaint queued" : t.status}</span>
    </span>
  );
  return (
    <div className={`h3-cue-take${placed ? " h3-on" : ""}`}>
      <Lane label={label} h={TAKE_H} W={W} cls={`h3-cue-wave${select && ok ? " h3-cue-selectable" : ""}`}
        onPointerDown={select && ok ? select.onDown : undefined}
        title={ok ? `${name}: its waveform from its first bar line, its loudness per bar (white) over the arc${select ? ". Drag across bars to select them: repaint them, comp them from another take, or lower them in the mix" : ""}` : t.error ?? t.status}>
        {ok && <PeaksCanvas peaks={peaks?.ok ? peaks.data.peaks : EMPTY} width={W} height={TAKE_H - 4} />}
        {ok && (
          <svg width={W} height={TAKE_H} className="h3-cue-svg">
            <polyline points={arcLine} className="h3-cue-arcline h3-dim" />
            <polyline points={levelLine} className="h3-cue-heard" />
          </svg>
        )}
        {range && <div className="h3-cue-range" style={{ left: range[0] * g.bar * pps, width: (range[1] - range[0]) * g.bar * pps }} />}
        {ok && t.song && <div className="h3-cue-songrow"><SongStrip song={t.song} g={g} pps={pps} /></div>}
        {t.status === "queued" && <span className="h3-muted h3-small" style={{ padding: 8 }}><i className="pi pi-spin pi-spinner" /> queued</span>}
        {t.status === "failed" && <span className="h3-err h3-small" style={{ padding: 8 }}>{t.error ?? "failed"}</span>}
      </Lane>
      <div className="h3-cue-meas" style={{ marginLeft: LAB_W, maxWidth: viewW }}>
        {ok && (
          <>
            <button className="h3-btn h3-icon" title={playing ? "Stop" : `Play ${name} (the playhead runs over the grid)`} onClick={onPlay}>
              <i className={`pi ${playing ? "pi-pause" : "pi-play"}`} />
            </button>
            {t.comp && <span className="h3-small h3-cue-comp" title="spliced on bar lines from two takes (both at the cue's tempo)">{compLabel(t.comp)}</span>}
            {t.repaint && <span className="h3-small h3-cue-comp" title={`those bars made again on its model (${t.repaint.fresh ? "new music there" : "the same music played again"}); the rest is the take's own, spliced at the bar lines`}>{repaintLabel(t.repaint)}</span>}
            {t.repaint_check && t.repaint_check.beats > 0 && (
              <span className={`h3-small ${t.repaint_check.on < t.repaint_check.on_before - 1 ? "h3-warn" : "h3-muted"}`}
                title="the repainted bars against the take's beat: onsets within 40 ms of its beats, the new bars' and (in brackets) the take's own there">
                on the beat {t.repaint_check.on}/{t.repaint_check.beats} ({t.repaint_check.on_before})
              </span>
            )}
            {t.song && <SongLine song={t.song} />}
            {t.theme && <span className="h3-small h3-muted" title={`the theme it was rendered with, and how its model heard it${t.theme.staged ? `: fitted to the cue, ${t.theme.staged.bars} bars looped${Math.abs(t.theme.staged.stretch - 1) > 0.005 ? `, played ${t.theme.staged.stretch.toFixed(2)}x` : ""}` : ""}`}>theme {t.theme.label}{t.theme.use ? ` (${t.theme.use}${t.theme.strength != null ? ` ${t.theme.strength}` : ""})` : " (left out)"}</span>}
            {m!.melody != null && (
              <span className={`h3-small ${m!.on_theme === false ? "h3-cue-offtext" : ""}`}
                title="How much of the theme's melody it kept (SheetSage2 transcribed both): a take with no theme in it keeps about 20 %; under 30 % it lost the theme, and ranks after those that kept it">
                <b>{melodyText(m)}</b>
              </span>
            )}
            <span className="h3-small h3-muted">hits</span>
            {m!.hit_errors.map((e, i) => {
              const c = hitChip(e);
              const h = plan.hits[i];
              return <span key={i} className={`h3-cue-chip h3-cue-${c.cls}`} title={`${h?.name ?? `hit ${i + 1}`}: ${e == null ? "nothing in the music there" : `the music's nearest onset ${c.text} frames from it`}${h && !h.must ? " (may miss)" : ""}`}>{c.text}</span>;
            })}
            {!m!.hit_errors.length && <span className="h3-small h3-muted">none</span>}
            <span className="h3-small" title="how far its loudness per bar is from the arc's shape (0 follows it exactly)">shape <b className="h3-mono">{m!.shape_error ?? "—"}</b></span>
            <span className="h3-small" title="what ranks the takes: the worst must-hit error, then the shape (lower is better)">score <b className="h3-mono">{m!.score}</b></span>
            <span className="h3-small h3-muted" title={m!.tempo_heard ? "the tempo heard, believed: it was stretched by it" : "the tempo couldn't be told (soft music) or was far off: stretched by the plan's"}>
              {m!.bpm_heard != null ? `${m!.bpm_heard} bpm heard` : "tempo not heard"}{m!.tempo_heard ? "" : " ?"}
            </span>
            {stale.length > 0 && <span className="h3-badge h3-b-stale" title={stale.join("\n")}>stale</span>}
            <span className="h3-grow" />
            <PinTheme take={t.take} />
            <button className={`h3-btn${placed ? "" : " h3-primary"}`} style={{ width: "auto" }} disabled={placed}
              title={placed ? `${name} is the cue's item on the music track` : `Put ${name} on the music track of the ${pass} mix, its level fitted to the arc (breakpoints you can change on the timeline)`}
              onClick={() => void pickCueTake(t.take)}>
              <i className="pi pi-check" /> {placed ? "In the mix" : "Pick"}
            </button>
          </>
        )}
        {t.seed != null && <span className="h3-small h3-muted h3-mono" title="its seed">{t.seed}</span>}
      </div>
      {ok && select && range && <BarFixes t={t} bars={range} g={g} plan={plan} placed={placed} sel={select} viewW={viewW} />}
    </div>
  );
}

/** A finished take made a series theme (POST /seriesmith/cue/theme): its name, its role, and
 * whether every episode's series config beside this one gets it too (each has its own). */
function PinTheme({ take }: { take: number }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [role, setRole] = useState("");
  const [words, setWords] = useState("");
  const [everywhere, setEverywhere] = useState(true);
  const [busy, setBusy] = useState(false);
  const bad = !/^[A-Za-z0-9_-]{1,40}$/.test(name);
  if (!open) {
    return (
      <button className="h3-btn" style={{ width: "auto" }}
        title={`Make ${tn(take)} a series theme: named in the series config (sound.themes), any episode's cue can then carry it (its Theme: a series theme)`}
        onClick={() => setOpen(true)}>
        <i className="pi pi-star" /> Series theme
      </button>
    );
  }
  return (
    <span className="h3-row h3-small" style={{ gap: 4 }}>
      <input className="h3-in h3-mono" style={{ width: 110 }} placeholder="name, e.g. porch" aria-label="Theme name" autoFocus
        value={name} onChange={(e) => setName(e.target.value.trim())} />
      <select className="h3-in" style={{ width: "auto" }} aria-label="Theme role" value={role} onChange={(e) => setRole(e.target.value)}
        title="What the first-pass score uses it for: the show's theme, an episode's own, or the thread that runs on">
        <option value="">no role</option>
        <option value="show">show</option>
        <option value="story">story</option>
        <option value="runner">runner</option>
      </select>
      <input className="h3-in" style={{ width: 160 }} placeholder="what it is, in words" aria-label="Theme words"
        value={words} onChange={(e) => setWords(e.target.value)} />
      <label className="h3-row" style={{ gap: 2 }} title="Each episode has a series config of its own: write it into every one beside this episode too, not only this one">
        <input type="checkbox" checked={everywhere} onChange={(e) => setEverywhere(e.target.checked)} /> every episode
      </label>
      <button className="h3-btn h3-primary" style={{ width: "auto" }} disabled={bad || busy}
        title={bad ? "A name: letters, digits, _ or -" : `Write sound.themes.${name} into the series config${everywhere ? "s" : ""}`}
        onClick={() => {
          setBusy(true);
          void pinCueTheme(take, name, role || null, words.trim() || null, everywhere).then((ok) => ok && setOpen(false)).finally(() => setBusy(false));
        }}>Save</button>
      <button className="h3-btn h3-icon" title="Cancel" onClick={() => setOpen(false)}><i className="pi pi-times" /></button>
    </span>
  );
}

/** What can be done to a take's bars: repaint them, comp them from another take, lower them in the mix. */
function BarFixes({ t, bars, g, plan, placed, sel, viewW }: {
  t: CueTake; bars: [number, number]; g: Grid; plan: CuePlan; placed: boolean; sel: TakeSelect; viewW: number;
}) {
  const others = sel.takes.filter((x) => x.take !== t.take && x.status === "ok" && !!x.measured);
  const [from, setFrom] = useState<number | null>(null);
  const [db, setDb] = useState(LOWER_DB);
  const [fresh, setFresh] = useState(false);
  const targets = useMusicTargets();
  const repaintNo = repaintWhy(t, targets);
  const src = others.some((x) => x.take === from) ? from : others[0]?.take ?? null;
  const what = barsLabel(bars);
  const span = barsInSpan(g, bars, plan.span);
  const lower = () => {
    if (!span || sel.t0 == null) return;
    void lowerMixItem(sel.spec.id, sel.t0 + span[0], sel.t0 + span[1], db, g.beat / 4, what).then((ok) => {
      if (ok) host().toast("success", `${sel.spec.id}: ${what} ${Math.abs(db)} dB ${db < 0 ? "lower" : "higher"}`, "Volume points on its block on the Music lane: drag them there to change them.");
    });
  };
  const lowerWhy = !placed ? `Only for the take in the mix: Pick ${tn(t.take)} first`
    : !span ? "Those bars are outside the cue's span: its item plays from its in point to its out point"
    : sel.t0 == null ? `${sel.spec.in.shot} isn't in Play all's cut` : "";
  return (
    <div className="h3-cue-fixes" style={{ marginLeft: LAB_W, maxWidth: viewW }}>
      <b className="h3-small">{what[0].toUpperCase() + what.slice(1)}</b>
      <span className="h3-row" style={{ gap: 4 }}>
        <button className="h3-btn" style={{ width: "auto" }} disabled={src == null}
          title={src == null ? "No other finished take to comp from" : `A new take: ${tn(t.take)} with ${what} from ${tn(src)}, spliced on the bar lines, measured and ranked`}
          onClick={() => src != null && void compCueTake(t.take, src, bars).then((n) => n != null && sel.clear())}>
          Comp {what} from…
        </button>
        <select className="h3-in" aria-label="Comp from take" value={src ?? ""} disabled={src == null} onChange={(e) => setFrom(Number(e.target.value))} style={{ width: "auto" }}>
          {others.map((x) => <option key={x.take} value={x.take}>{tn(x.take)}{x.measured ? ` (score ${x.measured.score})` : ""}</option>)}
        </select>
      </span>
      <span className="h3-row" style={{ gap: 4 }} title={lowerWhy || `Volume points on the cue's block in the mix: ${what} this many dB lower, the line kept either side`}>
        <button className="h3-btn" style={{ width: "auto" }} disabled={!!lowerWhy} onClick={lower}>Lower {what} with breakpoints…</button>
        <input className="h3-in" type="number" aria-label="Lower by dB" step={0.5} min={-24} max={6} value={db} disabled={!!lowerWhy} style={{ width: 56 }}
          onChange={(e) => setDb(Math.max(-24, Math.min(6, Number(e.target.value) || 0)))} />
        <span className="h3-small h3-muted">dB</span>
      </span>
      <span className="h3-row" style={{ gap: 4 }} title={repaintNo || `A new take: ${tn(t.take)} with ${what} made again on its model, the rest of it its own (spliced at the bar lines), measured and ranked`}>
        <button className="h3-btn" style={{ width: "auto" }} disabled={!!repaintNo}
          onClick={() => void repaintCueTake(t.take, bars, fresh).then((n) => n != null && sel.clear())}>
          Repaint {what}
        </button>
        <label className="h3-row h3-small" style={{ gap: 2 }} title="New music in those bars, not the same music played again: more change, but over four bars or more it can leave the beat (checked on the take)">
          <input type="checkbox" aria-label="Repaint with new music" checked={fresh} disabled={!!repaintNo} onChange={(e) => setFresh(e.target.checked)} /> new music
        </label>
      </span>
      <span className="h3-grow" />
      <button className="h3-btn h3-icon" title="Clear the selection" onClick={sel.clear}><i className="pi pi-times" /></button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// the inspector
// ---------------------------------------------------------------------------

/** A text field saved a moment after typing stops (or on leaving it), not on every key. */
function Draft({ value, onCommit, multiline, placeholder, label, rows = 3 }: {
  value: string; onCommit: (v: string) => void; multiline?: boolean; placeholder?: string; label: string; rows?: number;
}) {
  const [v, setV] = useState(value);
  const dirty = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const latest = useRef({ v, value, onCommit });
  latest.current = { v, value, onCommit };
  useEffect(() => {
    if (!dirty.current) setV(value);
  }, [value]);
  const commit = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    if (!dirty.current) return;
    dirty.current = false;
    const l = latest.current;
    if (l.v !== l.value) l.onCommit(l.v);
  }, []);
  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);
  const change = (x: string) => {
    setV(x);
    dirty.current = true;
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(commit, 700);
  };
  return multiline
    ? <textarea className="h3-in" aria-label={label} rows={rows} value={v} placeholder={placeholder} onChange={(e) => change(e.target.value)} onBlur={commit} />
    : <input className="h3-in" aria-label={label} value={v} placeholder={placeholder} onChange={(e) => change(e.target.value)} onBlur={commit} onKeyDown={(e) => e.key === "Enter" && commit()} />;
}

function LevelSelect({ value, onChange, label }: { value: number; onChange: (v: number) => void; label: string }) {
  return (
    <select className="h3-in" aria-label={label} value={String(value)} onChange={(e) => onChange(Number(e.target.value))}>
      {LEVELS.map((l) => <option key={l} value={String(l)}>{levelText(l)}</option>)}
    </select>
  );
}

/** The meter: one of METERS, or Other… (beats/unit text, checked as the server does). */
function MeterPicker({ spec, target, edit }: { spec: CueSpec; target: Target | undefined; edit: (patch: Partial<CueSpec>) => void }) {
  const text = meterText(spec.meter) ?? String(spec.meter);
  const listed = METERS.includes(text);
  const [other, setOther] = useState(!listed);
  const [bad, setBad] = useState<string | null>(null);
  useEffect(() => {
    if (!listed) setOther(true);
  }, [listed]);
  const save = (m: string) => edit({ meter: m === "4/4" ? undefined : m });
  const beats = meterBeats(spec.meter);
  const ace = target?.capabilities?.tempo === "bpm" && ![2, 3, 4, 6].includes(beats);
  return (
    <span className="h3-col" style={{ gap: 4 }}>
      <select className="h3-in" aria-label="Meter" value={other ? "other" : text} onChange={(e) => {
        const m = e.target.value;
        setBad(null);
        setOther(m === "other");
        if (m !== "other") save(m);
      }}>
        {METERS.map((m) => <option key={m} value={m}>{m}</option>)}
        <option value="other">Other…</option>
      </select>
      {other && (
        <Draft label="Meter (beats/unit)" value={text} placeholder="5/8" onCommit={(x) => {
          const m = meterText(x);
          setBad(m ? null : `A meter is beats/unit: 1 to 16 beats of a 2, 4, 8 or 16 (5/8, 11/8), not "${x.trim()}"`);
          if (m) save(m);
        }} />
      )}
      {bad && <span className="h3-err h3-small">{bad}</span>}
      {ace && <span className="h3-small h3-muted">ACE-Step's time signature takes 2, 3, 4 or 6 beats: it gets {aceBeats(beats)} and '{text}' in its tags</span>}
    </span>
  );
}

/** The key: none (the model's choice), a major or minor key, or Other… (its own text: a mode). */
/** A section's name: a score's or a song's (the cue's kind first), or Other… (its own text). */
function SectionNamePicker({ name, song, onChange }: { name: string; song: boolean; onChange: (name: string) => void }) {
  const choice = sectionChoice(name);
  const [other, setOther] = useState(choice == null);
  useEffect(() => {
    if (choice == null) setOther(true);
  }, [choice]);
  const group = (label: string, names: string[]) => (
    <optgroup label={label}>{names.map((n) => <option key={`${label}-${n}`} value={n}>{n}</option>)}</optgroup>
  );
  const groups = [group("Score", SCORE_SECTIONS), group("Song", SONG_SECTIONS.filter((n) => !SCORE_SECTIONS.includes(n)))];
  return (
    <span className="h3-col" style={{ gap: 4 }}>
      <select className="h3-in" aria-label="Section name" value={other ? "other" : choice ?? ""} onChange={(e) => {
        const n = e.target.value;
        setOther(n === "other");
        if (n !== "other") onChange(n);
      }}>
        {song ? [groups[1], groups[0]] : groups}
        <option value="other">Other…</option>
      </select>
      {other && <Draft label="Section name (other)" value={name} placeholder="the waltz" onCommit={onChange} />}
    </span>
  );
}

function KeyPicker({ spec, edit }: { spec: CueSpec; edit: (patch: Partial<CueSpec>) => void }) {
  const choice = keyChoice(spec.key);
  const [other, setOther] = useState(choice == null);
  useEffect(() => {
    if (choice == null) setOther(true);
  }, [choice]);
  return (
    <span className="h3-col" style={{ gap: 4 }}>
      <select className="h3-in" aria-label="Key" value={other ? "other" : choice ?? ""} onChange={(e) => {
        const k = e.target.value;
        setOther(k === "other");
        if (k !== "other") edit({ key: k || undefined });
      }}>
        <option value="">(none: the model's choice)</option>
        <optgroup label="Major">{KEYS.filter((k) => k.endsWith("major")).map((k) => <option key={k} value={k}>{k}</option>)}</optgroup>
        <optgroup label="Minor">{KEYS.filter((k) => k.endsWith("minor")).map((k) => <option key={k} value={k}>{k}</option>)}</optgroup>
        <option value="other">Other…</option>
      </select>
      {other && (
        <>
          <Draft label="Key (other)" value={spec.key ?? ""} placeholder="D dorian" onCommit={(key) => edit({ key: key.trim() || undefined })} />
          <span className="h3-small h3-muted">Only Stable Audio reads a key that isn't major or minor</span>
        </>
      )}
    </span>
  );
}

/** Start from a preset: picking one fills the cue's kind, style, tempo, meter, key, sections and orchestration (asking first when it has its own). */
function PresetSelect({ spec, presets, targets }: { spec: CueSpec; presets: CuePreset[]; targets: Target[] }) {
  const pick = (id: string) => {
    const p = presets.find((x) => x.id === id);
    if (!p) return;
    if (presetReplaces(spec) && !confirm(`Replace this cue's style, sections and orchestration with ${p.label}?`)) return;
    void applyCuePreset(p, !!targets.find((t) => t.id === spec.model)?.capabilities?.lyrics);
  };
  return (
    <select className="h3-in" aria-label="Preset" value="" onChange={(e) => pick(e.target.value)}>
      <option value="">Start from a preset…</option>
      {presetGroups(presets, spec.kind).map(({ group, presets: ps }) => (
        <optgroup key={group} label={group}>
          {ps.map((p) => <option key={p.id} value={p.id} title={p.hint}>{p.label}</option>)}
        </optgroup>
      ))}
    </select>
  );
}

function CueInspector({ ep, pass, res, target, targets, presets, sel, sections, setSel }: {
  ep: string; pass: Pass; res: CueResult; target: Target | undefined; targets: Target[]; presets: CuePreset[]; sel: number | null; sections: CueSection[]; setSel: (i: number | null) => void;
}) {
  const { spec, plan } = res;
  const edit = (patch: Partial<CueSpec>) => void saveCue(withSpec(spec, patch));
  const lyrics = !!target?.capabilities?.lyrics;
  const field = (label: string, el: ReactNode, title?: string) => (
    <div className="h3-field" title={title}><label>{label}</label>{el}</div>
  );
  const prompt = plan && (
    <div className="h3-cue-prompt">
      <div className="h3-cue-h">What {target?.short ?? target?.label ?? plan.target} is told</div>
      <pre className="h3-mono">{plan.prompt.prompt}</pre>
      {typeof plan.prompt.values?.lyrics === "string" && plan.prompt.values.lyrics && (
        <>
          <div className="h3-cue-h">Its lyrics (the sections)</div>
          <pre className="h3-mono">{plan.prompt.values.lyrics}</pre>
        </>
      )}
      {!!plan.notes?.length && (
        <>
          <div className="h3-cue-h" title="the script's music: notes of the shots the cue plays over, in the prompt above">From the script</div>
          {plan.notes.map((n) => <div key={n.shot} className="h3-small"><b>{n.shot}</b> {n.music}</div>)}
        </>
      )}
    </div>
  );
  if (sel != null && plan) {
    const s = sections[sel];
    const p = plan.sections[sel];
    const set = (patch: Partial<CueSection>) => edit({ sections: patchSection(sections, sel, patch) });
    return (
      <div className="h3-cue-side">
        <div className="h3-row" style={{ gap: 6 }}>
          <b>Section {sel + 1}</b><span className="h3-muted h3-small">{p?.bars} bars</span>
          <span className="h3-grow" />
          <button className="h3-btn h3-icon" title="The cue (Esc)" onClick={() => setSel(null)}><i className="pi pi-times" /></button>
        </div>
        {field("Name", <SectionNamePicker key={sel} name={s.name} song={spec.kind === "song"} onChange={(name) => set({ name: name || `section ${sel + 1}` })} />,
          "ACE-Step hears it as the section's tag ([Chorus]); Stable Audio doesn't hear names")}
        {field("Words", <Draft label="Section words" multiline value={s.words ?? ""} placeholder="instruments, texture, direction: solo french horn, strings enter…" onCommit={(words) => set({ words })} />,
          "What plays and how: told to the model for this stretch")}
        {field("From", <LevelSelect label="Energy at its start" value={p?.from ?? s.from ?? 3} onChange={(from) => set({ from })} />, "Energy at its start, 1 (sparse) to 5 (fortissimo)")}
        {field("To", <LevelSelect label="Energy at its end" value={p?.to ?? s.to ?? 3} onChange={(to) => set({ to })} />, "Energy at its end")}
        {lyrics && field("Lyrics", <Draft label="Section lyrics" multiline rows={4} value={s.lyrics ?? ""} placeholder="a song's lines (else one line per bar of its words)" onCommit={(l) => set({ lyrics: l })} />)}
        {prompt}
      </div>
    );
  }
  const num = (s: string) => (s.trim() === "" ? undefined : Number(s));
  return (
    <div className="h3-cue-side">
      <div className="h3-row" style={{ gap: 6 }}><b>Cue {spec.id}</b><span className="h3-muted h3-small">click a section to edit it</span></div>
      {presets.length > 0 && field("Preset", <PresetSelect spec={spec} presets={presets} targets={targets} />,
        "A worked example to start from: it fills the kind, style, tempo, meter, key, the sections (names, words, energies) and who plays, fitted to the cue's bars. Then adjust them")}
      {field("Kind", (
        <select className="h3-in" aria-label="Cue kind" value={spec.kind ?? "score"}
          onChange={(e) => {
            const kind = e.target.value === "song" ? "song" as const : undefined;
            // a song needs a model that sings: one that doesn't goes back to the kind's default
            const sings = !!targets.find((t) => t.id === spec.model)?.capabilities?.lyrics;
            edit({ kind, ...(kind === "song" && spec.model && !sings ? { model: undefined } : {}) });
          }}>
          <option value="score">Score (instrumental, under the picture)</option>
          <option value="song">Song (sung: its sections' lyrics)</option>
        </select>
      ), "Score is composed to the picture, instrumental; a song is sung, each section's lyrics its lines. Each has its own default model")}
      {field("Label", <Draft label="Cue label" value={spec.label ?? ""} placeholder="1M3 The Proposal" onCommit={(label) => edit({ label })} />)}
      {field("Model", (
        <select className="h3-in" aria-label="Music model" value={spec.model ?? ""} onChange={(e) => edit({ model: e.target.value || undefined })}>
          <option value="">the default{plan && !spec.model ? ` (${targets.find((t) => t.id === plan.target)?.short ?? plan.target})` : ""}</option>
          {targets.filter((t) => spec.kind !== "song" || t.capabilities?.lyrics).map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
        </select>
      ), target?.capabilities?.structure === "story" ? "It takes the arc as a story told in words, the tempo in the text"
        : target?.capabilities?.structure === "plan" ? "It plans the song itself (sections and bars, as ABC), its tempo set to the cue's; then sings the lyrics to that plan"
        : target ? "It takes sections as tags and a bpm of its own" : undefined)}
      {field("Theme", <ThemeField ep={ep} pass={pass} spec={spec} plan={plan} target={target} targets={targets} themes={res.themes} save={edit} />,
        "A theme carried from cue to cue (the leitmotif): a series theme, another cue's take, or a sound file. Stable Audio 3 renders from its sound (at a strength); YuE2 sings its melody; ACE-Step hears it as its timbre")}
      {field("Tempo", (
        <span className="h3-row" style={{ gap: 6 }}>
          <Draft label="Cue bpm" value={spec.bpm != null ? String(spec.bpm) : ""} placeholder="100" onCommit={(b) => edit({ bpm: num(b) })} />
          <label className="h3-check" title="Keep this tempo exactly: the pre-roll alone lands the hits"><input type="checkbox" checked={!!spec.fixed_tempo} onChange={(e) => edit({ fixed_tempo: e.target.checked })} /> fixed</label>
        </span>
      ), "bpm asked; the fit moves it up to 8 % to put the must-hits on bar lines, unless fixed")}
      {field("Meter", <MeterPicker spec={spec} target={target} edit={edit} />, "Beats to the bar and the note a beat is; the tempo counts the beats")}
      {field("Key", <KeyPicker spec={spec} edit={edit} />)}
      {field("Style", <Draft label="Style" multiline value={spec.style ?? ""} placeholder="romantic, solo horn for Edmund (after the series' score direction)" onCommit={(style) => edit({ style })} />)}
      {field("Tail", <Draft label="Tail seconds" value={String(spec.tail ?? 2)} onCommit={(t) => edit({ tail: num(t) === 2 ? undefined : num(t) })} />, "seconds after its out point, to ring out")}
      {field("Takes", <Draft label="Takes per render" value={spec.takes != null ? String(spec.takes) : ""} placeholder={String(TAKES_DEFAULT)} onCommit={(t) => edit({ takes: num(t) })} />, "how many takes a render makes (the model's preset's when empty)")}
      <div className="h3-cue-h">The fit</div>
      {res.plan_error && <div className="h3-err h3-small">{res.plan_error}</div>}
      {plan?.blocked && <div className="h3-err h3-small">{plan.blocked}</div>}
      {plan?.warnings?.filter((w) => w !== plan.theme?.warning).map((w) => <div key={w} className="h3-small h3-cue-offtext">{w}</div>)}
      {plan?.song && <div className="h3-small h3-muted" title="the theme's plan, at this cue's tempo, against its in point">The theme's plan: {plan.song.bars} bars of {plan.song.meter}: {plan.song.sections.map((x) => `${x.name} at ${x.at.toFixed(1)} s`).join(", ")}</div>}
      {plan && (
        <div className="h3-small h3-col" style={{ gap: 2 }}>
          <span>asked {spec.bpm ?? 100} bpm, fitted <b className="h3-mono">{plan.fit.bpm}</b> {plan.fit.bpm !== (spec.bpm ?? 100) ? `(${((plan.fit.bpm / (spec.bpm ?? 100) - 1) * 100).toFixed(1)} %)` : ""}</span>
          <span className="h3-muted">the model is asked {plan.fit.ask_bpm} bpm and {plan.ask_seconds} s, each take stretched by {plan.fit.stretch}</span>
          <span>worst must-hit: <b className={`h3-mono${plan.fit.worst_must > 1 ? " h3-cue-offtext" : ""}`}>{plan.fit.worst_must} frames</b> off its line</span>
          <span className="h3-muted">{plan.bars} bars from {plan.preroll.toFixed(2)} s before its in point · {fmtClock(plan.seconds)}</span>
        </div>
      )}
      {prompt}
    </div>
  );
}
