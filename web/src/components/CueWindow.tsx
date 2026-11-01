// The cue window (docs/SOUND.md "The cue window"): what happens inside a music
// cue, in the viewer's place, three tabs on one bar grid at the plan's tempo,
// from the pre-roll through the tail. Score: the picture, the hits (each at the
// bar and beat it lands on, and the fit's error), the bar ruler, the sections
// (drag an edge: whole bars), the intensity lane (the arc: drag a point,
// double-click adds one, right-click removes it) and the takes, best first,
// each its waveform and its loudness per bar over the arc; the inspector on the
// right edits the section selected, or the cue. Arc: the intensity lane large,
// drawn freehand or by points, smoothed, a preset shape, its peaks and lows
// snapped to hits, sections cut from it, and beside it what the model will
// hear. Orchestration & takes: who plays in each bar, painted off / under /
// present / lead, then the takes, where bars dragged across are comped from
// another take or lowered with the mix's breakpoints. Every cue edit is one PUT
// of the spec, then the cue fetched again (cueActions): the plan is the
// server's. The arc is energy 1-5, drawn in its own colour: the timeline's gain
// breakpoints (dB) are another curve.

import { useCallback, useEffect, useRef, useState, type MouseEvent as RMouseEvent, type PointerEvent as RPointerEvent, type ReactNode } from "react";
import { closeViewer, currentPlaylist } from "../actions";
import { compCueTake, cueKey, loadCue, pickCueTake, renderCue, saveCue } from "../cueActions";
import { isTyping } from "../cutActions";
import { api, host } from "../host";
import {
  ARC_SHAPES, LEVEL_WORDS, ORCH_LEVELS, addPoint, arcFlags, arcPoints, arcSpec, barBeat, barSpan, barsInSpan, barsLabel, clipsOver, compLabel, cueStart,
  cueTitle, drawnPoints, editableSections, familyName, gridOf, heldCells, hitChip, impliedPoints, levelY, levelsAsEnergy, mergeStroke, moveEdge,
  movePoint, orchestraRows, paintOrchestra, patchSection, presetPoints, ranks, removeFamily, removePoint, renameFamily, sectionEdges, sectionWords,
  sectionsFromArc, smoothPoints, snapToHits, splitSection, tauX, trimOrchestra, withSpec, wordsOffArc, xTau, yLevel,
  type ArcPt, type Grid, type Orchestra,
} from "../lib/cue";
import { fmtClock } from "../lib/format";
import { HIT_KIND_TITLE } from "../lib/mix";
import { lowerMixItem } from "../mixActions";
import { clipTake, type PlayItem } from "../lib/playlist";
import { useApp, statusKey, type ViewerState } from "../store";
import type { CuePlan, CueResult, CueSection, CueSpec, CueTake, Target } from "../types";
import { FloatingWindow, defaultViewerRect } from "./FloatingWindow";
import { trackPointer, useSize } from "./hooks";
import { mediaStyle } from "./Thumb";
import { FullscreenButton } from "./Viewer";
import { PeaksCanvas, usePeaks } from "./Waveform";

// the viewer's place (the standalone page docks it in the middle)
const RECT_KEY = "seriesmith.viewer.rect.v2";
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
const REPAINT_TITLE = "not measured yet (docs/SOUND.md 'Fixing part of a take')";

export type CueTab = "score" | "arc" | "orch";
type ArcMode = "draw" | "points";

let musicTargets: Promise<Target[]> | null = null;
/** The orchestration grid's rows by episode and cue, either pass (a family off throughout isn't stored, so the window keeps the rows) */
const keptRows = new Map<string, string[]>();

/** The music targets (GET /seriesmith/targets?kind=music), asked once. */
function useMusicTargets(): Target[] {
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
  const [tab, setTab] = useState<CueTab>("score");
  // fetched on open, and for each pass it's shown on (its takes' landing fetches it again: cueActions)
  useEffect(() => {
    if (id) void loadCue(ep, pass, id);
  }, [ep, pass, id]);

  // Esc: the section selected, else the window
  useEffect(() => {
    const el = winRef.current;
    if (!el) return;
    const h = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || isTyping(e.target)) return;
      e.preventDefault();
      e.stopPropagation();
      if (sel != null) setSel(null);
      else closeViewer();
    };
    el.addEventListener("keydown", h);
    return () => el.removeEventListener("keydown", h);
  }, [sel]);

  const tabBtn = (name: string, t: CueTab, title: string) => (
    <button className={tab === t ? "h3-on" : ""} title={title} onClick={() => setTab(t)}>{name}</button>
  );
  const head = (
    <>
      <i className="pi pi-volume-up" style={{ color: "var(--h3-arc)" }} />
      <b>{id}</b>
      <span className="h3-muted h3-small">{res ? cueTitle(res.spec) : ""} · {v.pass}</span>
      <span className="h3-seg" title="The cue window's views">
        {tabBtn("Score", "score", "Everything on one bar grid: the picture, hits, sections, the arc and the takes")}
        {tabBtn("Arc", "arc", "The intensity lane large: draw it, shape it from a preset, snap its peaks to hits, cut sections from it")}
        {tabBtn("Orchestration & takes", "orch", "Who plays in each bar; the takes, where bars are comped from another take or lowered")}
      </span>
      <span className="h3-grow" />
      <button className="h3-btn" title="Back to the timeline (Esc)" onClick={closeViewer}><i className="pi pi-arrow-left" /> Timeline</button>
      <FullscreenButton />
      <button className="h3-btn h3-icon" title="Close (Esc)" onClick={closeViewer}><i className="pi pi-times" /></button>
    </>
  );
  return (
    <FloatingWindow storageKey={RECT_KEY} defaultRect={defaultViewerRect} head={head} winRef={winRef} className="h3-cue-win">
      {!res ? (
        <div className="h3-empty-state">{err ? <span className="h3-err">{id}: {err}</span> : <><i className="pi pi-spin pi-spinner" /> {id}…</>}</div>
      ) : (
        <CueBody ep={ep} v={v} res={res} sel={sel} setSel={setSel} tab={tab} />
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

function CueBody({ ep, v, res, sel, setSel, tab }: {
  ep: string; v: ViewerState; res: CueResult; sel: number | null; setSel: (i: number | null) => void; tab: CueTab;
}) {
  const { spec, plan } = res;
  const items = useApp((s) => currentPlaylist(s));
  const fps = useApp((s) => s.status[statusKey(ep, v.pass)]?.fps) || plan?.fps || 24;
  const targets = useMusicTargets();
  const target = targets.find((t) => t.id === (plan?.target ?? spec.model));
  const [scrollRef, size] = useSize<HTMLDivElement>();
  const [zoom, setZoom] = useState<number | null>(null);
  const [count, setCount] = useState<number>(spec.takes ?? TAKES_DEFAULT);
  const [mode, setMode] = useState<ArcMode>("draw");
  const [brush, setBrush] = useState(2);
  const rowsKey = `${ep}|${spec.id}`;
  const [kept, setKept] = useState<string[] | undefined>(() => keptRows.get(rowsKey));
  useEffect(() => setKept(keptRows.get(rowsKey)), [rowsKey]);
  useEffect(() => setCount(spec.takes ?? TAKES_DEFAULT), [spec.takes]);
  const sections = plan ? editableSections(spec, plan) : [];
  const selected = sel != null && sel < sections.length ? sel : null;

  const inspector = (
    <CueInspector res={res} target={target} targets={targets} sel={selected} sections={sections} setSel={setSel} />
  );
  if (!plan) {
    return (
      <div className="h3-cue-body">
        <div className="h3-cue-main h3-empty-state">
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
        <div className="h3-cue-bar">
          <span className="h3-mono h3-small" title={`the cue's exact tempo (the model is asked ${plan.fit.ask_bpm}, stretched by ${plan.fit.stretch})`}>
            {plan.fit.bpm} bpm · {g.meter}/4 · {plan.bars} bars · {fmtClock(plan.seconds)}
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
            <span className="h3-small h3-muted">Brush</span>
            <span className="h3-seg" title="Paint cells with this level: click one, or drag across bars and rows">
              {ORCH_LEVELS.map((name, k) => (
                <button key={k} className={brush === k ? "h3-on" : ""} onClick={() => setBrush(k)}><i className={`h3-cue-swatch h3-lv-${k}`} /> {name}</button>
              ))}
            </span>
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
    <Lane label={`${g.meter}/4`} h={RULER_H} W={W} cls="h3-cue-ruler" title={`Bars at ${plan.fit.bpm} bpm, beats as ticks`}>
      {bars.map((b) => (
        <div key={b} className="h3-cue-bnum" style={{ left: b * g.bar * pps, width: g.bar * pps }}>
          {g.bar * pps > 14 && <span>{b + 1}</span>}
          {g.beat * pps > 5 && Array.from({ length: g.meter - 1 }, (_, k) => <i key={k} style={{ left: (k + 1) * g.beat * pps }} />)}
        </div>
      ))}
    </Lane>
  );
  const sectionLane = (
    <Lane label="Sections" h={SECT_H} W={W}
      title={editable ? "The cue's sections, in whole bars: click one to edit it (the inspector), drag an edge to move it" : "The cue's sections, for reference (edit them in the Score tab)"}>
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
          <span className="h3-muted h3-small" style={{ padding: 8 }}>No takes yet: Render makes several, each measured against the hits and the arc, best first.</span>
        </Lane>
      )}
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
    const next = splitSection(sections, i, bar, plan.arc);
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
  const [paint, setPaint] = useState<{ r0: number; r1: number; b0: number; b1: number } | null>(null);
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
    let p = { r0: c.row, r1: c.row, b0: c.bar, b1: c.bar };
    setPaint(p);
    trackPointer((ev) => {
      const d = cell(ev);
      p = { ...p, r1: d.row, b1: d.bar };
      setPaint(p);
    }, (cancelled) => {
      setPaint(null);
      if (cancelled) return;
      const fams = rows.slice(Math.min(p.r0, p.r1), Math.max(p.r0, p.r1) + 1);
      const next = paintOrchestra(orch, fams, p.b0, p.b1, brush);
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
            const lv = inStroke(r, b) ? brush : orch[fam]?.[b] ?? 0;
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
      <span className={`h3-small ${t.status === "failed" ? "h3-err" : "h3-muted"}`}>{t.status === "ok" ? (placed ? "in the mix" : t.comp ? "comp" : "") : t.status}</span>
    </span>
  );
  return (
    <div className={`h3-cue-take${placed ? " h3-on" : ""}`}>
      <Lane label={label} h={TAKE_H} W={W} cls={`h3-cue-wave${select && ok ? " h3-cue-selectable" : ""}`}
        onPointerDown={select && ok ? select.onDown : undefined}
        title={ok ? `${name}: its waveform from its first bar line, its loudness per bar (white) over the arc${select ? ". Drag across bars to select them: comp them from another take, or lower them in the mix" : ""}` : t.error ?? t.status}>
        {ok && <PeaksCanvas peaks={peaks?.ok ? peaks.data.peaks : EMPTY} width={W} height={TAKE_H - 4} />}
        {ok && (
          <svg width={W} height={TAKE_H} className="h3-cue-svg">
            <polyline points={arcLine} className="h3-cue-arcline h3-dim" />
            <polyline points={levelLine} className="h3-cue-heard" />
          </svg>
        )}
        {range && <div className="h3-cue-range" style={{ left: range[0] * g.bar * pps, width: (range[1] - range[0]) * g.bar * pps }} />}
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

/** What can be done to a take's bars: comp them from another take, lower them in the mix, repaint them (not yet). */
function BarFixes({ t, bars, g, plan, placed, sel, viewW }: {
  t: CueTake; bars: [number, number]; g: Grid; plan: CuePlan; placed: boolean; sel: TakeSelect; viewW: number;
}) {
  const others = sel.takes.filter((x) => x.take !== t.take && x.status === "ok" && !!x.measured);
  const [from, setFrom] = useState<number | null>(null);
  const [db, setDb] = useState(LOWER_DB);
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
      <span title={REPAINT_TITLE}><button className="h3-btn" style={{ width: "auto" }} disabled title={REPAINT_TITLE}>Repaint {what}</button></span>
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

function CueInspector({ res, target, targets, sel, sections, setSel }: {
  res: CueResult; target: Target | undefined; targets: Target[]; sel: number | null; sections: CueSection[]; setSel: (i: number | null) => void;
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
        {field("Name", <Draft label="Section name" value={s.name} onCommit={(name) => set({ name: name || `section ${sel + 1}` })} />)}
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
      ), target?.capabilities?.structure === "story" ? "It takes the arc as a story told in words, the tempo in the text" : target ? "It takes sections as tags and a bpm of its own" : undefined)}
      {field("Tempo", (
        <span className="h3-row" style={{ gap: 6 }}>
          <Draft label="Cue bpm" value={spec.bpm != null ? String(spec.bpm) : ""} placeholder="100" onCommit={(b) => edit({ bpm: num(b) })} />
          <label className="h3-check" title="Keep this tempo exactly: the pre-roll alone lands the hits"><input type="checkbox" checked={!!spec.fixed_tempo} onChange={(e) => edit({ fixed_tempo: e.target.checked })} /> fixed</label>
        </span>
      ), "bpm asked; the fit moves it up to 8 % to put the must-hits on bar lines, unless fixed")}
      {field("Meter", (
        <select className="h3-in" aria-label="Meter" value={String(spec.meter ?? 4)} onChange={(e) => edit({ meter: Number(e.target.value) === 4 ? undefined : Number(e.target.value) })}>
          {[2, 3, 4, 6].map((m) => <option key={m} value={String(m)}>{m}/4</option>)}
        </select>
      ))}
      {field("Key", <Draft label="Key" value={spec.key ?? ""} placeholder="D minor" onCommit={(key) => edit({ key })} />)}
      {field("Style", <Draft label="Style" multiline value={spec.style ?? ""} placeholder="romantic, solo horn for Edmund (after the series' score direction)" onCommit={(style) => edit({ style })} />)}
      {field("Tail", <Draft label="Tail seconds" value={String(spec.tail ?? 2)} onCommit={(t) => edit({ tail: num(t) === 2 ? undefined : num(t) })} />, "seconds after its out point, to ring out")}
      {field("Takes", <Draft label="Takes per render" value={spec.takes != null ? String(spec.takes) : ""} placeholder={String(TAKES_DEFAULT)} onCommit={(t) => edit({ takes: num(t) })} />, "how many takes a render makes (the model's preset's when empty)")}
      <div className="h3-cue-h">The fit</div>
      {res.plan_error && <div className="h3-err h3-small">{res.plan_error}</div>}
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
