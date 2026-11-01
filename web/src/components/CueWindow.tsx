// The cue window (docs/SOUND.md "The cue window"): what happens inside a music
// cue, in the viewer's place. The Score tab lays everything on one bar grid at
// the plan's tempo, from the pre-roll through the tail: the picture, the hits
// (each at the bar and beat it lands on, and the fit's error), the bar ruler,
// the sections (drag an edge: whole bars), the intensity lane (the arc: drag a
// point, double-click adds one, right-click removes it) and the takes, best
// first, each its waveform and its loudness per bar over the arc. The inspector
// on the right edits the section selected, or the cue. Every edit is one PUT
// of the spec, then the cue fetched again (cueActions): the plan is the
// server's. The arc is energy 1-5, drawn in its own colour: the timeline's
// gain breakpoints (dB) are another curve.

import { useCallback, useEffect, useRef, useState, type MouseEvent as RMouseEvent, type PointerEvent as RPointerEvent, type ReactNode } from "react";
import { closeViewer, currentPlaylist } from "../actions";
import { cueKey, loadCue, pickCueTake, renderCue, saveCue } from "../cueActions";
import { isTyping } from "../cutActions";
import { api } from "../host";
import {
  LEVEL_WORDS, addPoint, arcPoints, arcSpec, barBeat, clipsOver, cueStart, editableSections, gridOf, hitChip,
  impliedPoints, levelY, levelsAsEnergy, moveEdge, movePoint, patchSection, ranks, removePoint, sectionEdges, tauX, withSpec, xTau, yLevel,
  type ArcPt, type Grid,
} from "../lib/cue";
import { fmtClock } from "../lib/format";
import { HIT_KIND_TITLE } from "../lib/mix";
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
const TAKE_H = 40;
const PPS_MIN = 4;
const PPS_MAX = 160;
const TAKES_DEFAULT = 8;
const EMPTY: number[] = [];
const LEVELS = [1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5];

let musicTargets: Promise<Target[]> | null = null;

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

  const tab = (name: string, on: boolean, title?: string) => (
    <button className={on ? "h3-on" : ""} disabled={!on} title={title}>{name}</button>
  );
  const head = (
    <>
      <i className="pi pi-volume-up" style={{ color: "var(--h3-arc)" }} />
      <b>{id}</b>
      <span className="h3-muted h3-small">{res?.spec.label ?? ""} · {v.pass}</span>
      <span className="h3-seg" title="The cue window's views">
        {tab("Score", true)}
        {tab("Arc", false, "coming: the intensity lane large, presets, snap peaks to hits")}
        {tab("Orchestration & takes", false, "coming: who plays in each bar; comp and repaint")}
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
        <Score ep={ep} v={v} res={res} sel={sel} setSel={setSel} />
      )}
    </FloatingWindow>
  );
}

// ---------------------------------------------------------------------------
// the Score tab
// ---------------------------------------------------------------------------

function Score({ ep, v, res, sel, setSel }: { ep: string; v: ViewerState; res: CueResult; sel: number | null; setSel: (i: number | null) => void }) {
  const { spec, plan } = res;
  const items = useApp((s) => currentPlaylist(s));
  const fps = useApp((s) => s.status[statusKey(ep, v.pass)]?.fps) || plan?.fps || 24;
  const targets = useMusicTargets();
  const target = targets.find((t) => t.id === (plan?.target ?? spec.model));
  const [scrollRef, size] = useSize<HTMLDivElement>();
  const [zoom, setZoom] = useState<number | null>(null);
  const [count, setCount] = useState<number>(spec.takes ?? TAKES_DEFAULT);
  useEffect(() => setCount(spec.takes ?? TAKES_DEFAULT), [spec.takes]);
  const sections = plan ? editableSections(spec, plan) : [];
  const selected = sel != null && sel < sections.length ? sel : null;

  const side = (
    <CueInspector res={res} target={target} targets={targets} sel={selected} sections={sections} setSel={setSel} />
  );
  if (!plan) {
    return (
      <div className="h3-cue-body">
        <div className="h3-cue-main h3-empty-state">
          <div><b>{spec.id} can't be planned.</b><div className="h3-err" style={{ marginTop: 6 }}>{res.plan_error ?? "no plan"}</div>
            <div className="h3-muted h3-small" style={{ marginTop: 6 }}>Its in and out are anchored to shots of the cut; put them back in the {v.pass} cut, or make the cue again over the shots it plays over.</div></div>
        </div>
        {side}
      </div>
    );
  }
  const g = gridOf(plan, spec);
  const t0 = cueStart(items, spec, fps);
  const fit = Math.max(PPS_MIN, (size.width - LAB_W - 16) / g.seconds);
  const pps = Math.min(PPS_MAX, zoom ?? fit);
  const W = Math.ceil(g.seconds * pps);
  const placed = res.takes.find((t) => t.placed === v.pass);
  return (
    <div className="h3-cue-body">
      <div className="h3-cue-main">
        <div className="h3-cue-bar">
          <span className="h3-mono h3-small" title={`the cue's exact tempo (the model is asked ${plan.fit.ask_bpm}, stretched by ${plan.fit.stretch})`}>
            {plan.fit.bpm} bpm · {g.meter}/4 · {plan.bars} bars · {fmtClock(plan.seconds)}
          </span>
          <span className="h3-muted h3-small" title="the bars before the cue's in point, and after its out point">pre-roll {plan.preroll.toFixed(2)} s</span>
          {placed && <span className="h3-badge h3-b-ok" title={`t${String(placed.take).padStart(2, "0")} is the cue's item on the music track of the ${v.pass} mix`}>t{String(placed.take).padStart(2, "0")} in the mix</span>}
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
        <div className="h3-cue-scroll" ref={scrollRef}>
          <Grid g={g} pps={pps} W={W} viewW={Math.max(320, size.width - LAB_W - 24)} plan={plan} ep={ep} v={v} items={items} t0={t0} fps={fps} spec={spec} sections={sections}
            sel={selected} setSel={setSel} takes={res.takes} />
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

function Grid({ g, pps, W, viewW, plan, ep, v, items, t0, fps, spec, sections, sel, setSel, takes }: {
  g: Grid; pps: number; W: number; viewW: number; plan: CuePlan; ep: string; v: ViewerState; items: PlayItem[]; t0: number | null; fps: number;
  spec: CueSpec; sections: CueSection[]; sel: number | null; setSel: (i: number | null) => void; takes: CueTake[];
}) {
  const x = (tau: number) => tauX(g, tau, pps);
  const st = useApp((s) => s.status[statusKey(ep, v.pass)]);
  const other = useApp((s) => s.status[statusKey(ep, v.pass === "proxy" ? "final" : "proxy")]);
  const [edge, setEdge] = useState<{ i: number; sections: CueSection[] } | null>(null);
  const [arcDrag, setArcDrag] = useState<ArcPt[] | null>(null);
  const [playing, setPlaying] = useState<{ take: number; tau: number } | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);
  const arcRef = useRef<HTMLDivElement>(null);
  useEffect(() => () => audio.current?.pause(), []);

  // ---- the picture ----
  const clips = t0 == null ? [] : clipsOver(items, t0, g);

  // ---- sections: drag an edge ----
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

  // ---- the arc: the spec's points, else the ones the sections imply ----
  const own = t0 == null ? [] : arcPoints(spec, items, t0, fps);
  const implied = !own.length;
  const base = implied ? impliedPoints(g, plan.sections) : own;
  const pts = arcDrag ?? base;
  const commitArc = (next: ArcPt[]) => {
    if (t0 == null) return;
    void saveCue(withSpec(spec, { arc: arcSpec(next, items, t0, fps) }));
  };
  const laneXY = (ev: { clientX: number; clientY: number }) => {
    const r = arcRef.current!.getBoundingClientRect();
    return { tau: xTau(g, ev.clientX - r.left, pps), level: yLevel(ev.clientY - r.top, ARC_H) };
  };
  const onPointDown = (e: RPointerEvent<SVGElement>, i: number) => {
    if (e.button !== 0) return;
    e.stopPropagation();
    e.preventDefault();
    let next: ArcPt[] | null = null;
    trackPointer((ev) => {
      const p = laneXY(ev);
      next = movePoint(base, i, g, p.tau, p.level);
      setArcDrag(next);
    }, (cancelled) => {
      setArcDrag(null);
      if (!cancelled && next) commitArc(next);
    });
  };
  const onArcDouble = (e: RMouseEvent<HTMLDivElement>) => {
    if (t0 == null) return;
    const p = laneXY(e);
    commitArc(addPoint(base, g, p.tau, p.level));
  };
  const onPointMenu = (e: RMouseEvent<SVGElement>, i: number) => {
    e.preventDefault();
    e.stopPropagation();
    const next = removePoint(base, i);
    if (!next.length) void saveCue(withSpec(spec, { arc: undefined }));
    else commitArc(next);
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

  const bars = Array.from({ length: g.bars }, (_, b) => b);
  const arcLine = plan.arc.map((lv, b) => `${(b + 0.5) * g.bar * pps},${levelY(lv, ARC_H)}`).join(" ");
  const dragLine = arcDrag ? arcDrag.map((p) => `${x(p.tau)},${levelY(p.level, ARC_H)}`).join(" ") : null;
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

  return (
    <div className="h3-cue-grid" style={{ width: LAB_W + W }}>
      {under}
      {/* the picture, hits, bars, sections and arc stay in view over the takes */}
      <div className="h3-cue-head">
        {under}
        <Lane label="Picture" h={PIC_H} W={W} title={`${spec.in.shot} frame ${spec.in.frame} to ${spec.out.shot} frame ${spec.out.frame}: the shots it plays over, with the pre-roll and tail`}>
          {clips.map(({ it, a, b }) => {
            const s = st?.shots.find((z) => z.shot === it.shot);
            const take = s ? clipTake(s, s.cut.placeholder ? other : undefined) : undefined;
            return (
              <div key={it.shot} className="h3-cue-pic" style={{ left: x(a), width: Math.max(2, x(b) - x(a)), ...mediaStyle(ep, take, null) }}
                title={`${it.shot}${take ? ` t${String(take.take).padStart(2, "0")}` : ""}`}>
                <span>{it.shot}</span>
              </div>
            );
          })}
          {t0 == null && <span className="h3-muted h3-small" style={{ padding: 4 }}>{spec.in.shot} isn't in Play all's cut</span>}
        </Lane>

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

        <Lane label={`${g.meter}/4`} h={RULER_H} W={W} cls="h3-cue-ruler" title={`Bars at ${plan.fit.bpm} bpm, beats as ticks`}>
          {bars.map((b) => (
            <div key={b} className="h3-cue-bnum" style={{ left: b * g.bar * pps, width: g.bar * pps }}>
              {g.bar * pps > 14 && <span>{b + 1}</span>}
              {g.beat * pps > 5 && Array.from({ length: g.meter - 1 }, (_, k) => <i key={k} style={{ left: (k + 1) * g.beat * pps }} />)}
            </div>
          ))}
        </Lane>

        <Lane label="Sections" h={SECT_H} W={W} title="The cue's sections, in whole bars: click one to edit it (the inspector), drag an edge to move it">
          {shown.map((s, i) => (
            <div key={i} className={`h3-cue-sect${sel === i ? " h3-on" : ""}`} style={{ left: edges[i] * g.bar * pps, width: (edges[i + 1] - edges[i]) * g.bar * pps }}
              title={`${s.name}: ${s.bars} bar${s.bars === 1 ? "" : "s"}${s.words ? ` · ${s.words}` : ""} · energy ${plan.sections[i]?.from ?? "?"} to ${plan.sections[i]?.to ?? "?"}`}
              onClick={(e) => {
                e.stopPropagation();
                setSel(sel === i ? null : i);
              }}>
              <span>{s.name}</span>
              <span className="h3-muted">{s.bars}</span>
              {i < shown.length - 1 && <div className="h3-cue-edge" title="Drag: move this edge (whole bars; Esc cancels)" onPointerDown={(e) => onEdgeDown(e, i)} onClick={(e) => e.stopPropagation()} />}
            </div>
          ))}
          {edge && <div className="h3-cue-tip" style={{ left: edges[edge.i + 1] * g.bar * pps + 6 }}>bar {edges[edge.i + 1] + 1}</div>}
        </Lane>

        <Lane label={<>Intensity{!implied && <button className="h3-snd-btn" title="Clear the points: the sections' energies again" onClick={() => void saveCue(withSpec(spec, { arc: undefined }))}><i className="pi pi-times" /></button>}</>}
          h={ARC_H} W={W} cls="h3-cue-arc" laneRef={arcRef} onDoubleClick={onArcDouble}
          title={`The arc: energy 1 (sparse) to 5 (fortissimo), which the prompt tells the model and the takes are ranked against. Drag a point (to a beat, half a level); double-click: a point; right-click a point: remove it.${implied ? "\nNo points yet: the line the sections imply; dragging one makes them the cue's own." : ""}\nNot the mix's gain: that's the timeline's.`}>
          <svg width={W} height={ARC_H} className="h3-cue-svg">
            {[1, 2, 3, 4, 5].map((lv) => <line key={lv} x1={0} x2={W} y1={levelY(lv, ARC_H)} y2={levelY(lv, ARC_H)} className="h3-cue-level" />)}
            <polyline points={arcLine} className={`h3-cue-arcline${dragLine ? " h3-dim" : ""}`} />
            {dragLine && <polyline points={dragLine} className="h3-cue-arcline" />}
            {!implied && !dragLine && <polyline points={pts.map((p) => `${x(p.tau)},${levelY(p.level, ARC_H)}`).join(" ")} className="h3-cue-ptline" />}
            {pts.map((p, i) => (
              <circle key={i} cx={x(p.tau)} cy={levelY(p.level, ARC_H)} r={4.5} className={`h3-cue-pt${implied && !arcDrag ? " h3-implied" : ""}`}
                onPointerDown={(e) => onPointDown(e, i)} onContextMenu={(e) => onPointMenu(e, i)} onDoubleClick={(e) => e.stopPropagation()}>
                <title>{`${barBeat(g, p.tau).label} · ${levelText(p.level)}${implied ? " (from the sections)" : ""}`}</title>
              </circle>
            ))}
          </svg>
        </Lane>
      </div>

      {takes.map((t, i) => (
        <TakeRow key={t.take} ep={ep} t={t} rank={order[i]} g={g} pps={pps} W={W} viewW={viewW} plan={plan} pass={v.pass}
          playing={playing?.take === t.take} onPlay={() => play(t)} />
      ))}
      {!takes.length && (
        <Lane label="Takes" h={TAKE_H} W={W}>
          <span className="h3-muted h3-small" style={{ padding: 8 }}>No takes yet: Render makes several, each measured against the hits and the arc, best first.</span>
        </Lane>
      )}
    </div>
  );
}

/** A take: its waveform on the grid with its loudness per bar over the arc, then what was measured. */
function TakeRow({ ep, t, rank, g, pps, W, viewW, plan, pass, playing, onPlay }: {
  ep: string; t: CueTake; rank: number | null; g: Grid; pps: number; W: number; viewW: number; plan: CuePlan; pass: string; playing: boolean; onPlay: () => void;
}) {
  const m = t.measured;
  const ok = t.status === "ok" && !!m && !!t.file;
  const q = ok ? { ep, path: t.file!, bins: Math.max(16, Math.min(4096, Math.round(W / 2))), start: m!.downbeat, end: m!.downbeat + g.seconds, version: t.finished ?? null } : null;
  const peaks = usePeaks(q);
  const tn = `t${String(t.take).padStart(2, "0")}`;
  const lv = m ? levelsAsEnergy(m.levels) : [];
  const levelLine = lv.map((e, b) => `${(b + 0.5) * g.bar * pps},${levelY(e, TAKE_H, 3)}`).join(" ");
  const arcLine = plan.arc.map((e, b) => `${(b + 0.5) * g.bar * pps},${levelY(e, TAKE_H, 3)}`).join(" ");
  const stale = t.stale ?? [];
  const placed = t.placed === pass;
  const label = (
    <span className="h3-col" style={{ gap: 0 }}>
      <b>{rank != null ? `#${rank} ` : ""}{tn}</b>
      <span className={`h3-small ${t.status === "failed" ? "h3-err" : "h3-muted"}`}>{t.status === "ok" ? (placed ? "in the mix" : "") : t.status}</span>
    </span>
  );
  return (
    <div className={`h3-cue-take${placed ? " h3-on" : ""}`}>
      <Lane label={label} h={TAKE_H} W={W} cls="h3-cue-wave"
        title={ok ? `${tn}: its waveform from its first bar line, its loudness per bar (white) over the arc` : t.error ?? t.status}>
        {ok && <PeaksCanvas peaks={peaks?.ok ? peaks.data.peaks : EMPTY} width={W} height={TAKE_H - 4} />}
        {ok && (
          <svg width={W} height={TAKE_H} className="h3-cue-svg">
            <polyline points={arcLine} className="h3-cue-arcline h3-dim" />
            <polyline points={levelLine} className="h3-cue-heard" />
          </svg>
        )}
        {t.status === "queued" && <span className="h3-muted h3-small" style={{ padding: 8 }}><i className="pi pi-spin pi-spinner" /> queued</span>}
        {t.status === "failed" && <span className="h3-err h3-small" style={{ padding: 8 }}>{t.error ?? "failed"}</span>}
      </Lane>
      <div className="h3-cue-meas" style={{ marginLeft: LAB_W, maxWidth: viewW }}>
        {ok && (
          <>
            <button className="h3-btn h3-icon" title={playing ? "Stop" : `Play ${tn} (the playhead runs over the grid)`} onClick={onPlay}>
              <i className={`pi ${playing ? "pi-pause" : "pi-play"}`} />
            </button>
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
              title={placed ? `${tn} is the cue's item on the music track` : `Put ${tn} on the music track of the ${pass} mix, its level fitted to the arc (breakpoints you can change on the timeline)`}
              onClick={() => void pickCueTake(t.take)}>
              <i className="pi pi-check" /> {placed ? "In the mix" : "Pick"}
            </button>
          </>
        )}
        {t.seed != null && <span className="h3-small h3-muted h3-mono" title="its seed">{t.seed}</span>}
      </div>
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
      {field("Label", <Draft label="Cue label" value={spec.label ?? ""} placeholder="1M3 The Proposal" onCommit={(label) => edit({ label })} />)}
      {field("Model", (
        <select className="h3-in" aria-label="Music model" value={spec.model ?? ""} onChange={(e) => edit({ model: e.target.value || undefined })}>
          <option value="">the default{plan && !spec.model ? ` (${targets.find((t) => t.id === plan.target)?.short ?? plan.target})` : ""}</option>
          {targets.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
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
