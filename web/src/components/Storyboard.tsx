// The storyboard (docs/PLAN.md): the open episode's script against a story structure, an act to a
// row. A beat shows its target and its real shots; `+` adds a shot and Fill makes the rest. The
// script is what's saved: every edit here goes to disk the way the script editor's do.

import { createContext, Fragment, useCallback, useContext, useEffect, useMemo, useRef, useState, type CSSProperties, type DragEvent, type KeyboardEvent, type MouseEvent } from "react";
import { isPaidBackend, openSeriesForm, openShotForm, openSource, openStoryboard, openViewer, refreshEpisode, requestRender, updateViewer, uploadRef } from "../actions";
import { moveClip } from "../cutActions";
import { dropFileOnto, importTakeFile, videoSeconds } from "../takeActions";
import { gapAfter } from "../lib/takeDrop";
import { api } from "../host";
import { filesFromDrag } from "../lib/dropped";
import { keyframeRefId } from "../lib/keyframes";
import { videoTargets } from "../lib/targets";
import { clipTake } from "../lib/playlist";
import {
  bandShare, bareBeats, clock, dropSide, dropTargets, fillThenAdd, isVideoFile, mediaInOrder, heldIds, shotBefore, sketchable, takeToOpen, toGenerate, fillable, fillCount, heldToRender, meter, picturesInOrder, placeOf, positive, runtimeMinutes, runWidth, seriesChoices, TILE_SIZES, tileSize, type TileSize,
  actGroups, moveDivider, ownBeatsFrom, pushed, toggleActBreak, type DropSide, type OwnBeat, type BoardPlan, type BoardAct, type BoardBeat, type BoardRun, type BoardShot, type SeriesChoices, type StoryboardAnswer, type StoryboardEdit,
} from "../lib/storyboard";
import { statusKey, store, useApp } from "../store";
import { FloatingWindow, raiseWindow } from "./FloatingWindow";
import { EpisodeSelect } from "./ShotsTab";
import { VIEWER_RECT_KEY } from "./Viewer";
import type { Pass } from "../types";

export function StoryboardWindow() {
  const open = useApp((s) => s.storyboardOpen);
  const ep = useApp((s) => s.ep);
  return open && ep ? <Storyboard key={ep} ep={ep} /> : null;
}

const BIG_FILL = 50;

/** The selected tile and what a click and a double-click on one do. */
const Tiles = createContext<{
  selected: string | null;
  select: (id: string) => void;
  open: (shot: BoardShot) => void;
  /** Pictures dropped on a beat: into `empties` first, then a new shot each at the beat's end. */
  pictures: (e: DragEvent, beat: { plain: string; nth: number }, empties: BoardShot[]) => void;
}>({
  selected: null, select: () => undefined, open: () => undefined, pictures: () => undefined,
});

function placeName(id: string): string {
  return id.replace(/_/g, " ");
}

interface Picked { block: number; place: string; who: string[] }

/** Save as structure: the episode's beats as a table, a guide to adjust before it's kept. */
function SaveStructure({ plan, saved, file, close, done }: {
  plan: BoardPlan;
  saved: string[];
  file: string;
  close: () => void;
  done: (name: string) => void;
}) {
  const [name, setName] = useState(plan.structure ?? "");
  const [rows, setRows] = useState<OwnBeat[]>(() => ownBeatsFrom(plan.acts));
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const exists = saved.some((s) => s.toLowerCase() === name.trim().toLowerCase());
  const total = rows.reduce((n, r) => n + (Number(r.share) || 0), 0);
  const setRow = (i: number, next: Partial<OwnBeat>) => setRows((all) => all.map((r, k) => (k === i ? { ...r, ...next } : r)));
  const [selected, setSelected] = useState(0);
  const [view, setView] = useState<"table" | "timeline">("table");
  const track = useRef<HTMLDivElement>(null);
  const dragging = useRef<{ i: number; x: number; from: OwnBeat[]; moved: boolean } | null>(null);
  const groups = actGroups(rows);
  const picked = rows[selected];
  const share = (from: number, to: number) => rows.slice(from, to).reduce((n, r) => n + r.share, 0);
  /** The divider after beat `i`: drag it to trade share with the next beat, click it for an act break. */
  const divider = (i: number) => (
    <div className={`h3-sb-gantt-div${(rows[i + 1].act ?? "").trim() ? " h3-sb-actbreak" : ""}`}
      title="Drag to change the two beats' shares. Click to start or end an act here."
      onPointerDown={(e) => {
        e.currentTarget.setPointerCapture(e.pointerId);
        dragging.current = { i, x: e.clientX, from: rows, moved: false };
      }}
      onPointerMove={(e) => {
        const d = dragging.current;
        const width = track.current?.clientWidth;
        if (!d || !width || Math.abs(e.clientX - d.x) < 3) return;
        d.moved = true;
        setRows(moveDivider(d.from, d.i, ((e.clientX - d.x) / width) * total));
      }}
      onPointerUp={() => {
        const d = dragging.current;
        dragging.current = null;
        if (d && !d.moved) setRows((all) => toggleActBreak(all, d.i + 1));
      }} />
  );

  async function run(work: () => Promise<unknown>, after: string) {
    setBusy(true);
    setErr(null);
    try {
      await work();
      done(after);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const head = (
    <>
      <i className="pi pi-bookmark" />
      <b className="h3-grow">Save as structure</b>
      <button className="h3-btn h3-icon" title="Close" onClick={close}><i className="pi pi-times" /></button>
    </>
  );
  return (
    <FloatingWindow storageKey="seriesmith.storyboard.save.rect" head={head} minW={520} minH={320}
      defaultRect={() => ({ x: 120, y: 90, w: Math.min(860, window.innerWidth - 160), h: Math.min(640, window.innerHeight - 140) })}>
      <div className="h3-col" style={{ padding: 10, gap: 8, height: "100%", boxSizing: "border-box" }}>
        <label className="h3-row" style={{ gap: 6 }}>Name
          <input className="h3-in h3-grow" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <div className="h3-row" style={{ gap: 8, alignItems: "flex-start" }}>
          <span className="h3-small h3-muted h3-grow">
            {view === "table"
              ? "Each share comes from this episode's shots. An act runs until the next one starts: the arrow beside a beat starts a new act there. These are guides, and an episode can stray from them."
              : "Each beat's width is its share of the story, from this episode's shots: drag a divider to adjust it. Click a divider to start or end an act there. These are guides, and an episode can stray from them."}
          </span>
          <span className="h3-seg">
            <button className={view === "table" ? "h3-on" : ""} onClick={() => setView("table")}>Table</button>
            <button className={view === "timeline" ? "h3-on" : ""} onClick={() => setView("timeline")}>Timeline</button>
          </span>
        </div>
        {view === "table" ? (
          <div style={{ flex: 1, minHeight: 0, overflow: "auto" }}>
            <table className="h3-table h3-sb-acttable">
              <thead><tr><th>Act</th><th /><th>Beat</th><th>Share %</th><th>Guidance</th></tr></thead>
              <tbody>
                {groups.flatMap((g) => rows.slice(g.start, g.end).map((r, k) => {
                  const i = g.start + k;
                  return (
                    <tr key={i} className={k === 0 && i > 0 ? "h3-sb-actstart" : ""}>
                      {k === 0 && (
                        <td rowSpan={g.end - g.start} className="h3-sb-actcell">
                          <input className="h3-in" value={g.name} placeholder="Act" aria-label="Act" onChange={(e) => setRow(g.start, { act: e.target.value })} />
                        </td>
                      )}
                      <td>
                        {i > 0 && (
                          <button className={`h3-btn h3-icon${(r.act ?? "").trim() ? " h3-on" : ""}`}
                            title={(r.act ?? "").trim() ? "Join this beat to the act above" : "Start a new act at this beat"}
                            onClick={() => setRows((all) => toggleActBreak(all, i))}><i className="pi pi-arrow-down-left" /></button>
                        )}
                      </td>
                      <td>{r.beat}</td>
                      <td><input className="h3-in h3-sb-num" type="number" min="0.1" step="any" value={r.share}
                        onChange={(e) => setRow(i, { share: Number(e.target.value) })} /></td>
                      <td><input className="h3-in" style={{ width: "100%" }} value={r.guidance ?? ""} placeholder="What this beat is for"
                        onChange={(e) => setRow(i, { guidance: e.target.value })} /></td>
                    </tr>
                  );
                }))}
              </tbody>
            </table>
          </div>
        ) : (
          <>
            <div className="h3-sb-gantt" ref={track}>
              {groups.map((g, n) => (
                <Fragment key={g.start}>
                  {n > 0 && divider(g.start - 1)}
                  <div className="h3-sb-gantt-act" style={{ flexGrow: share(g.start, g.end), flexBasis: 0 }}>
                    <input className="h3-sb-gantt-actname" value={g.name} placeholder={groups.length > 1 ? "Name this act" : "One act: click a divider below to split"}
                      onChange={(e) => setRow(g.start, { act: e.target.value })} />
                    <div className="h3-sb-gantt-beats">
                      {rows.slice(g.start, g.end).map((r, k) => {
                        const i = g.start + k;
                        return (
                          <Fragment key={i}>
                            {k > 0 && divider(i - 1)}
                            <button className={`h3-sb-gantt-beat${selected === i ? " h3-sb-sel" : ""}`} style={{ flexGrow: r.share, flexBasis: 0 }}
                              title={`${r.beat}: ${r.share}%`} onClick={() => setSelected(i)}>
                              <span className="h3-sb-name">{r.beat}</span>
                            </button>
                          </Fragment>
                        );
                      })}
                    </div>
                  </div>
                </Fragment>
              ))}
            </div>
            {picked && (
              <div className="h3-col" style={{ gap: 6 }}>
                <div className="h3-row" style={{ gap: 8 }}>
                  <b>{picked.beat}</b>
                  <label className="h3-row" style={{ gap: 6 }}>Share %
                    <input className="h3-in h3-sb-num" type="number" min="0.1" step="any" value={picked.share}
                      onChange={(e) => setRow(selected, { share: Number(e.target.value) })} />
                  </label>
                </div>
                <label className="h3-col" style={{ gap: 3 }}>
                  <span className="h3-small h3-muted">Guidance: what this beat is for. It shows under the beat on the board, and a new shot starts with it as its action.</span>
                  <textarea className="h3-in" rows={2} value={picked.guidance ?? ""} onChange={(e) => setRow(selected, { guidance: e.target.value })} />
                </label>
              </div>
            )}
          </>
        )}
        {view === "timeline" && <span className="h3-grow" />}
        <span className="h3-small h3-muted">Adds up to {Math.round(total * 10) / 10}%; it's scaled to the whole story when saved. Kept on this machine, in {file}: copy that file to pass them along.</span>
        {err && <span className="h3-small h3-err">{err}</span>}
        <div className="h3-row" style={{ gap: 8 }}>
          {exists && (
            <button className="h3-btn" disabled={busy} onClick={() => {
              if (window.confirm(`Forget your saved structure ${name.trim()}? Scripts that name it keep their beats.`)) void run(() => api().deleteStructure(name.trim()), "");
            }}><i className="pi pi-trash" /> Delete saved</button>
          )}
          <span className="h3-grow" />
          <button className="h3-btn" onClick={close}>Cancel</button>
          <button className="h3-btn h3-primary" disabled={busy || !name.trim() || !rows.length}
            onClick={() => void run(() => api().saveStructure({ name: name.trim(), beats: rows, replace: exists }), name.trim())}>
            {exists ? "Replace saved" : "Save"}
          </button>
        </div>
      </div>
    </FloatingWindow>
  );
}

type Menu =
  | { x: number; y: number; kind: "shot"; shot: BoardShot; last: boolean; rendered: boolean }
  | { x: number; y: number; kind: "sequence"; run: BoardRun }
  | { x: number; y: number; kind: "beat"; beat: BoardBeat }
  | { x: number; y: number; kind: "act"; act: BoardAct };

/** Right-click on anything on the board. The name fields stand in for a prompt, which ComfyUI's
 * desktop app doesn't have. */
function BoardMenu({ menu, choices, busy, edit, close, rename, fresh }: {
  fresh: Set<string>;
  menu: Menu;
  choices: SeriesChoices | null;
  busy: boolean;
  edit: (e: StoryboardEdit) => void;
  close: () => void;
  rename: (beat: BoardBeat) => void;
}) {
  const [asking, setAsking] = useState<"beat" | "act" | "rename" | "place" | "convert" | null>(null);
  const models = videoTargets(useApp((s) => s.targets)).filter((t) => t.id !== "hold");
  const held = heldIds(menu.kind === "sequence" ? menu.run.shots
    : menu.kind === "beat" ? menu.beat.runs.flatMap((r) => r.shots)
    : menu.kind === "act" ? menu.act.beats.flatMap((b) => b.runs.flatMap((r) => r.shots)) : []);
  const run = (e: StoryboardEdit) => () => { edit(e); close(); };
  const group = menu.kind === "sequence" ? menu.run.shots
    : menu.kind === "beat" ? menu.beat.runs.flatMap((r) => r.shots)
    : menu.kind === "act" ? menu.act.beats.flatMap((b) => b.runs.flatMap((r) => r.shots)) : [];
  const wanted = toGenerate(group, fresh);
  const convert = (
    <>
      <button disabled={busy || !wanted.length} title={wanted.length ? "Render the shots here with no up-to-date take, each on its own model" : "Every shot here has an up-to-date take"}
        onClick={() => { requestRender(wanted, true, `Generate ${wanted.length} shots`); close(); }}><i className="pi pi-play" /> Generate ({wanted.length})</button>
      <button disabled={busy || !held.length} title={held.length ? "Change these held shots' model. Read them first: a new shot's action is what the model is sent." : "No held shots here"}
        onClick={() => setAsking("convert")}><i className="pi pi-video" /> Convert held shots ({held.length})…</button>
      {asking === "convert" && (
        <div className="h3-sb-models">
          <button className="h3-sb-menuchoice" disabled={busy} onClick={run({ op: "convert", shots: held, target: null })}>The series' default</button>
          {models.map((t) => (
            <button key={t.id} className="h3-sb-menuchoice" disabled={busy} onClick={run({ op: "convert", shots: held, target: t.id })}>{t.label || t.id}</button>
          ))}
        </div>
      )}
    </>
  );
  const named = menu.kind === "beat" && menu.beat.plain !== null ? { plain: menu.beat.plain, nth: menu.beat.nth } : null;
  const lastBeat = menu.kind === "act" ? menu.act.beats[menu.act.beats.length - 1] : null;
  const lastNamed = lastBeat && lastBeat.plain !== null ? { plain: lastBeat.plain, nth: lastBeat.nth } : null;
  const opener = menu.kind === "act" ? menu.act.beats[0]?.block ?? null : null;
  const ask = (label: string, commit: (text: string) => void) => (
    <div className="h3-sb-menuask">
      <span className="h3-small h3-muted">{label}</span>
      <NameField value="" busy={busy} cancel={close} commit={(text) => { commit(text); close(); }} />
    </div>
  );
  return (
    <>
      <div className="h3-sb-menuback" onPointerDown={close} onContextMenu={(e) => { e.preventDefault(); close(); }} />
      <div className="h3-menu h3-sb-menu" style={{ left: menu.x, top: menu.y }} onContextMenu={(e) => e.preventDefault()}>
        {menu.kind === "shot" && (
          <>
            <div className="h3-menu-head">{menu.shot.id}{menu.shot.target === "hold" ? " (no model yet)" : ""}</div>
            <button onClick={() => { openShotForm({ shot: menu.shot.id, after: null }); close(); }}><i className="pi pi-pencil" /> Edit shot…</button>
            <button disabled={busy} title="Render this shot on its own model" onClick={() => { requestRender([menu.shot.id], true, `Generate ${menu.shot.id}`); close(); }}>
              <i className="pi pi-play" /> {fresh.has(menu.shot.id) ? "Generate again" : "Generate"}
            </button>
            <button disabled={busy} onClick={run({ op: "add_after", block: menu.shot.block, before: true })}><i className="pi pi-plus" /> Add shot before</button>
            <button disabled={busy} onClick={run({ op: "add_after", block: menu.shot.block })}><i className="pi pi-plus" /> Add shot after</button>
            <button disabled={busy || !menu.last} title={menu.last ? "" : "Only after a sequence's last shot: a new one in the middle would move the shots after it"}
              onClick={() => setAsking("place")}><i className="pi pi-map-marker" /> New sequence after…</button>
            {asking === "place" && choices && choices.places.map((p) => (
              <button key={p} className="h3-sb-menuchoice" disabled={busy} onClick={run({ op: "add_sequence", block: menu.shot.block, place: p })}>{placeName(p)}</button>
            ))}
            <div className="h3-menu-sep" />
            <button disabled={busy} onClick={() => {
              if (menu.rendered && !window.confirm(`${menu.shot.id} has takes. Take it out of the script? The takes stay on disk.`)) return;
              run({ op: "delete_shot", block: menu.shot.block })();
            }}><i className="pi pi-trash" /> Delete shot</button>
          </>
        )}
        {menu.kind === "sequence" && (() => {
          const last = menu.run.shots[menu.run.shots.length - 1];
          return (
            <>
              <div className="h3-menu-head">{menu.run.sequence}: {placeName(menu.run.place)}</div>
              <button disabled={busy || !last} title={last ? "" : "This sequence has no shots yet"} onClick={() => setAsking("place")}>
                <i className="pi pi-map-marker" /> New sequence after…
              </button>
              {asking === "place" && last && choices && choices.places.map((p) => (
                <button key={p} className="h3-sb-menuchoice" disabled={busy} onClick={run({ op: "add_sequence", block: last.block, place: p })}>{placeName(p)}</button>
              ))}
              {convert}
            </>
          );
        })()}
        {menu.kind === "beat" && named && (
          <>
            <div className="h3-menu-head">{named.plain}</div>
            <button disabled={busy || menu.beat.block === null} onClick={() => { rename(menu.beat); close(); }}><i className="pi pi-pencil" /> Rename beat</button>
            <button disabled={busy} onClick={() => setAsking("beat")}><i className="pi pi-plus" /> Add a beat after…</button>
            {asking === "beat" && ask("The new beat's name", (name) => edit({ op: "add_beat", beat: named, name }))}
            <button disabled={busy || menu.beat.block === null} title="Its shots stay and join the beat before"
              onClick={run({ op: "remove_beat", block: menu.beat.block ?? -1 })}><i className="pi pi-trash" /> Remove beat</button>
            {convert}
          </>
        )}
        {menu.kind === "act" && (
          <>
            <div className="h3-menu-head">{menu.act.act || "Episode"}</div>
            <button disabled={busy || !lastNamed} onClick={() => setAsking("act")}><i className="pi pi-plus" /> Add an act after…</button>
            {asking === "act" && lastNamed && ask("The new act's name", (name) => edit({ op: "add_beat", beat: lastNamed, name: "New beat", act: name }))}
            <button disabled={busy || !menu.act.own || opener === null} title={menu.act.own ? "" : "The structure's own acts keep their names"}
              onClick={() => setAsking("rename")}><i className="pi pi-pencil" /> Rename act…</button>
            {asking === "rename" && opener !== null && ask("Its new name", (name) => edit({ op: "rename_act", block: opener, name }))}
            <button disabled={busy || !menu.act.own || opener === null} title="Its beats stay"
              onClick={run({ op: "remove_act", block: opener ?? -1 })}><i className="pi pi-trash" /> Remove act</button>
            {convert}
          </>
        )}
      </div>
    </>
  );
}

/** Text that's committed on Enter or leaving the field; Escape puts it back. */
function NameField({ value, busy, commit, cancel, className, size }: {
  value: string;
  busy: boolean;
  commit: (text: string) => void;
  cancel?: () => void;
  className?: string;
  size?: number;
}) {
  const [text, setText] = useState(value);
  useEffect(() => setText(value), [value]);
  const done = () => {
    const next = text.trim();
    if (next && next !== value) commit(next);
    else { setText(value); cancel?.(); }
  };
  return (
    <input className={className ?? "h3-in"} size={size} value={text} disabled={busy} autoFocus={!!cancel}
      onChange={(e) => setText(e.target.value)} onBlur={done} onClick={(e) => e.stopPropagation()}
      onKeyDown={(e) => {
        if (e.key === "Enter") e.currentTarget.blur();
        if (e.key === "Escape") { setText(value); cancel?.(); }
      }} />
  );
}

type FrameDrop = (e: DragEvent, shots: BoardShot[], single: boolean, side?: DropSide | null) => void;

const SHOT_MIME = "application/x-seriesmith-board-shot";
const SIZE_KEY = "seriesmith.storyboard.tile";

/** Lets a drop of files land here rather than on the page behind. */
function allowFiles(e: DragEvent) {
  if (Array.from(e.dataTransfer.types).includes("Files")) {
    e.preventDefault();
    e.stopPropagation();
  }
}

/** The side of a tile the pointer is on, for what's being dragged over it. */
function sideOf(e: DragEvent<HTMLElement>): DropSide | null {
  const box = e.currentTarget.getBoundingClientRect();
  return dropSide((e.clientX - box.left) / box.width, Array.from(e.dataTransfer.types).includes(SHOT_MIME));
}

/** A place that takes pictures, lit while they're over it. */
function overLanding(e: DragEvent<HTMLElement>) {
  if (!Array.from(e.dataTransfer.types).includes("Files")) return;
  allowFiles(e);
  e.currentTarget.dataset.over = "1";
}

function overTile(e: DragEvent<HTMLElement>) {
  const types = Array.from(e.dataTransfer.types);
  if (!types.includes("Files") && !types.includes(SHOT_MIME)) return;
  e.preventDefault();
  e.stopPropagation();
  const side = sideOf(e);
  if (side) e.currentTarget.dataset.side = side;
  else delete e.currentTarget.dataset.side;
}

function Run({ run, selected, pick, thumbs, onShotMenu, onRunMenu, onFrames }: {
  onFrames: FrameDrop;
  onShotMenu: (e: MouseEvent, shot: BoardShot, last: boolean) => void;
  onRunMenu: (e: MouseEvent, run: BoardRun) => void;
  run: BoardRun;
  selected: boolean;
  pick: () => void;
  thumbs: Map<string, string>;
}) {
  const who = [...new Set(run.shots.flatMap((s) => s.who))];
  const tiles = useContext(Tiles);
  return (
    <div className="h3-sb-run" style={{ width: runWidth(run.shots.length) }} onDragOver={allowFiles}
      onDrop={(e) => onFrames(e, run.shots, false)}>
      <button className={`h3-sb-seqbar${run.opens ? "" : " h3-sb-goeson"}${selected ? " h3-sb-sel" : ""}`} disabled={run.block === null}
        title={`${run.sequence}: ${placeName(run.place)}${who.length ? `; ${who.join(", ")}` : ""}${run.opens ? "" : " (carried on from the beat before)"}. Click to change.`}
        onClick={pick} onContextMenu={(e) => onRunMenu(e, run)}>
        <span className="h3-sb-name">{placeName(run.place)}</span>
        {who.length > 0 && <span className="h3-sb-who">{who.join(", ")}</span>}
      </button>
      <div className="h3-sb-tiles">
        {run.shots.map((s) => {
          const thumb = thumbs.get(s.id);
          return (
            <button key={s.id} className={`h3-sb-tile${s.held_empty ? " h3-sb-standin" : ""}${tiles.selected === s.id ? " h3-sb-picked" : ""}`}
              style={thumb ? { backgroundImage: `url("${thumb}")` } : undefined}
              title={`${s.id}${s.target === "hold" ? " (no model yet)" : ""}: ${s.action}${s.held_empty ? "\nDrop a picture on it." : ""}\nDouble-click to open it; right-click for more.`}
              onClick={() => tiles.select(s.id)} onDoubleClick={() => tiles.open(s)}
              onContextMenu={(e) => onShotMenu(e, s, s === run.shots[run.shots.length - 1])}
              draggable onDragStart={(e) => { e.dataTransfer.setData(SHOT_MIME, s.id); e.dataTransfer.effectAllowed = "move"; }}
              onDragOver={overTile} onDragLeave={(e) => delete e.currentTarget.dataset.side}
              onDrop={(e) => { const side = sideOf(e); delete e.currentTarget.dataset.side; onFrames(e, [s], true, side); }} />
          );
        })}
      </div>
    </div>
  );
}

function Beat({ beat, biggest, picked, pick, busy, edit, thumbs, onShotMenu, onRunMenu, onBeatMenu, renaming, setRenaming, onFrames }: {
  onFrames: FrameDrop;
  onShotMenu: (e: MouseEvent, shot: BoardShot, last: boolean) => void;
  onRunMenu: (e: MouseEvent, run: BoardRun) => void;
  onBeatMenu: (e: MouseEvent, beat: BoardBeat) => void;
  renaming: boolean;
  setRenaming: (on: boolean) => void;
  thumbs: Map<string, string>;
  beat: BoardBeat;
  biggest: number;
  picked: number | null;
  pick: (run: BoardRun) => void;
  busy: boolean;
  edit: (e: StoryboardEdit) => void;
}) {
  const place = placeOf(beat);
  const name = beat.plain ?? "Before any beat";
  const named = beat.plain === null ? null : { plain: beat.plain, nth: beat.nth };
  const left = fillCount([beat]);
  const point = beat.point !== undefined;
  const block = beat.block;
  const tiles = useContext(Tiles);
  const shots = beat.runs.flatMap((r) => r.shots);
  const land = (e: DragEvent<HTMLElement>, empties: BoardShot[]) => {
    delete e.currentTarget.dataset.over;
    if (named) tiles.pictures(e, named, empties);
  };
  return (
    <div className="h3-sb-beat" onDragOver={allowFiles} onDrop={(e) => (named ? land(e, shots) : onFrames(e, shots, false))}>
      <div className={`h3-sb-band${point ? " h3-sb-point" : ""}${beat.thin ? " h3-sb-thin" : ""}${beat.plain !== null && !beat.known ? " h3-sb-own" : ""}`}
        style={{ width: bandShare(beat.target_shots, biggest) }}
        onContextMenu={(e) => onBeatMenu(e, beat)}
        title={`${beat.guidance ? `${name}${place ? ` (${place})` : ""}: ${beat.guidance}` : name}${block !== null ? "\nDouble-click its name to rename it; right-click for more." : ""}`}>
        {renaming && block !== null
          ? <NameField className="h3-sb-rename" value={name} busy={busy} cancel={() => setRenaming(false)}
              commit={(text) => { setRenaming(false); edit({ op: "rename_beat", block, name: text }); }} />
          : <span className="h3-sb-name" onDoubleClick={() => block !== null && setRenaming(true)}>{name}</span>}
        <span className="h3-sb-count">{meter(beat)}</span>
      </div>
      {beat.guidance && <div className="h3-small h3-muted h3-sb-guide">{beat.guidance}</div>}
      <div className="h3-sb-runs">
        {beat.runs.map((run, i) => (
          <Run key={`${run.sequence}${i}`} run={run} selected={picked === run.block} pick={() => pick(run)} thumbs={thumbs} onShotMenu={onShotMenu} onRunMenu={onRunMenu} onFrames={onFrames} />
        ))}
        {named && (
          <button className="h3-sb-add" disabled={busy} title="Add a shot at the end of this beat, or drop pictures or videos here for a new shot each"
            onDragOver={overLanding} onDragLeave={(e) => delete e.currentTarget.dataset.over}
            onDrop={(e) => land(e, [])}
            onClick={() => edit({ op: "add", beat: named })}>+</button>
        )}
        {named && !shots.length && (
          <div className="h3-small h3-muted h3-sb-drophint" onDragOver={overLanding} onDragLeave={(e) => delete e.currentTarget.dataset.over}
            onDrop={(e) => land(e, [])}>Drag pictures or videos here for a shot each</div>
        )}
        {named && left > 0 && (
          <button className="h3-link h3-small" disabled={busy} title={`Make the ${left} shots this beat is short of its target`}
            onClick={() => edit({ op: "fill", beats: [named] })}>Fill {left}</button>
        )}
      </div>
    </div>
  );
}

function EditBar({ choices, picked, busy, edit, close }: {
  choices: SeriesChoices | null;
  picked: Picked;
  busy: boolean;
  edit: (e: StoryboardEdit) => void;
  close: () => void;
}) {
  return (
    <div className="h3-row h3-sb-editbar h3-small">
      {!choices && <span className="h3-muted">Reading the series config…</span>}
      {choices && (
        <>
          <label className="h3-row">Place
            <select value={picked.place} disabled={busy}
              onChange={(e) => edit({ op: "place", block: picked.block, place: e.target.value })}>
              {!choices.places.includes(picked.place) && <option value={picked.place}>{placeName(picked.place)}</option>}
              {choices.places.map((id) => <option key={id} value={id}>{placeName(id)}</option>)}
            </select>
          </label>
          <span className="h3-row" style={{ gap: 4 }} title="Set on this sequence's new shots. A shot someone has worked on keeps its own.">Cast
            {choices.cast.map((c) => {
              const on = picked.who.includes(c.id);
              return (
                <button key={c.id} className={`h3-btn${on ? " h3-on" : ""}`} disabled={busy}
                  onClick={() => edit({ op: "cast", block: picked.block, who: on ? picked.who.filter((x) => x !== c.id) : [...picked.who, c.id] })}>
                  {c.name}
                </button>
              );
            })}
            {!choices.cast.length && <span className="h3-muted">none in this series</span>}
          </span>
        </>
      )}
      <span className="h3-grow" />
      <button className="h3-btn h3-icon" title="Done" onClick={close}><i className="pi pi-check" /></button>
    </div>
  );
}

function ActRow({ act, label, biggest, shut, toggle, picked, pick, busy, edit, fill, thumbs, onShotMenu, onRunMenu, onBeatMenu, onActMenu, renamingBeat, setRenamingBeat, onFrames }: {
  onFrames: FrameDrop;
  onShotMenu: (e: MouseEvent, shot: BoardShot, last: boolean) => void;
  onRunMenu: (e: MouseEvent, run: BoardRun) => void;
  onBeatMenu: (e: MouseEvent, beat: BoardBeat) => void;
  onActMenu: (e: MouseEvent, act: BoardAct) => void;
  renamingBeat: number | null;
  setRenamingBeat: (block: number | null) => void;
  thumbs: Map<string, string>;
  label: string;
  act: BoardAct;
  biggest: number;
  shut: boolean;
  toggle: () => void;
  picked: number | null;
  pick: (run: BoardRun) => void;
  busy: boolean;
  edit: (e: StoryboardEdit) => void;
  fill: (beats: BoardBeat[]) => void;
}) {
  const left = fillCount(act.beats);
  return (
    <section className="h3-sb-act">
      <div className="h3-sb-acthead" onContextMenu={(e) => onActMenu(e, act)}>
        <button className="h3-sb-acttoggle" onClick={toggle}>
          <i className={`pi ${shut ? "pi-chevron-right" : "pi-chevron-down"}`} />
          <b>{label}</b>
          <span className="h3-small h3-muted">{act.target_shots ? `${act.shots} of ${act.target_shots} shots` : `${act.shots} shots`}</span>
        </button>
        {left > 0 && (
          <button className="h3-link h3-small" disabled={busy} onClick={() => fill(act.beats)}>Fill act ({left})</button>
        )}
      </div>
      {!shut && act.beats.map((b, i) => (
        <Beat key={`${b.plain}${b.nth}${i}`} beat={b} biggest={biggest} picked={picked} pick={pick} busy={busy} edit={edit} thumbs={thumbs}
          onFrames={onFrames} onShotMenu={onShotMenu} onRunMenu={onRunMenu} onBeatMenu={onBeatMenu} renaming={renamingBeat !== null && renamingBeat === b.block}
          setRenaming={(on) => setRenamingBeat(on ? b.block : null)} />
      ))}
    </section>
  );
}

function Storyboard({ ep }: { ep: string }) {
  const [names, setNames] = useState<string[]>([]);
  const [structure, setStructure] = useState("");
  const [minutes, setMinutes] = useState("7");
  const [shot, setShot] = useState("3.5");
  const [data, setData] = useState<StoryboardAnswer | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [closed, setClosed] = useState<Record<string, boolean>>({});
  const [picked, setPicked] = useState<Picked | null>(null);
  const [choices, setChoices] = useState<SeriesChoices | null>(null);
  const [busy, setBusy] = useState(false);
  const [seeded, setSeeded] = useState(false);
  // the show's own format the script opened with: still offered after changing away from it
  const [ownFormat, setOwnFormat] = useState<string | null>(null);
  const [dropping, setDropping] = useState<string | null>(null);
  const [ownNames, setOwnNames] = useState<string[]>([]);
  const [ownFile, setOwnFile] = useState("");
  const [saving, setSaving] = useState(false);
  const [undo, setUndo] = useState<string[]>([]);
  const [redo, setRedo] = useState<string[]>([]);
  const [menu, setMenu] = useState<Menu | null>(null);
  const [renamingBeat, setRenamingBeat] = useState<number | null>(null);
  const [tile, setTile] = useState<string | null>(null);
  const openAt = (e: MouseEvent, next: Omit<Extract<Menu, { kind: "shot" }>, "x" | "y"> | Omit<Extract<Menu, { kind: "sequence" }>, "x" | "y"> | Omit<Extract<Menu, { kind: "beat" }>, "x" | "y"> | Omit<Extract<Menu, { kind: "act" }>, "x" | "y">) => {
    e.preventDefault();
    setMenu({ ...next, x: Math.min(e.clientX, window.innerWidth - 240), y: Math.min(e.clientY, window.innerHeight - 280) } as Menu);
  };

  const loadStructures = useCallback(() => api().structures().then((r) => {
    setNames(r.structures.map((s) => s.name));
    setOwnNames(r.structures.filter((s) => s.own).map((s) => s.name));
    setOwnFile(r.own_file ?? "");
  }), []);
  useEffect(() => {
    let live = true;
    loadStructures().catch((e) => live && setErr((e as Error).message));
    return () => { live = false; };
  }, [ep, loadStructures]);

  // the places and cast on offer, again when the series settings close
  const seriesOpen = useApp((s) => s.seriesFormOpen);
  useEffect(() => {
    if (seriesOpen) return undefined;
    let live = true;
    api().source(ep, "series").then((d) => live && setChoices(seriesChoices(d.text)))
      .catch((e) => live && setErr(`The series config: ${(e as Error).message}`));
    return () => { live = false; };
  }, [ep, seriesOpen]);

  const length = positive(minutes);
  const each = positive(shot);
  // a script that names its structure goes by it, whether or not there's a table for it
  const scriptStructure = data?.plan.structure ?? null;
  const pass = useApp((s) => s.pass);
  const [size, setSize] = useState<TileSize>(() => {
    try {
      return tileSize(localStorage.getItem(SIZE_KEY));
    } catch {
      return "s";
    }
  });
  const pickSize = (next: TileSize) => {
    setSize(next);
    try {
      localStorage.setItem(SIZE_KEY, next);
    } catch {
      // private window: it just won't be remembered
    }
  };
  const rendered = useRef<Set<string>>(new Set());
  const status = useApp((s) => s.status[statusKey(ep, s.pass)]);
  const other = useApp((s) => s.status[statusKey(ep, s.pass === "proxy" ? "final" : "proxy")]);
  const thumbs = useMemo(() => {
    const out = new Map<string, string>();
    const fresh = new Set<string>();
    for (const s of status?.shots ?? []) {
      const take = clipTake(s, s.cut.placeholder ? other : undefined);
      if (take?.thumb) out.set(s.shot, api().thumbUrl(ep, take.thumb, TILE_SIZES[size] * 2));
      if (take && take.status === "ok" && (!take.stale?.length || take.source === "imported")) fresh.add(s.shot);
    }
    rendered.current = fresh;
    // a held shot shows its picture: a take of an earlier one, or of the gray card, is out of date
    for (const act of data?.plan.acts ?? []) {
      for (const beat of act.beats) {
        for (const run of beat.runs) {
          for (const s of run.shots) {
            if (s.picture && s.target === "hold") out.set(s.id, api().thumbUrl(ep, s.picture, TILE_SIZES[size] * 2, s.picture_version));
          }
        }
      }
    }
    return out;
  }, [ep, pass, status, other, data, size]);
  /** Shots whose take in the cut is a video from outside: not empty, and nothing to sketch or hold. */
  const videos = useMemo(() => {
    const out = new Set<string>();
    for (const s of status?.shots ?? []) {
      if (clipTake(s, s.cut.placeholder ? other : undefined)?.source === "imported") out.add(s.shot);
    }
    return out;
  }, [status, other]);
  const playable = useMemo(() => {
    const out = new Map<string, { take: number; pass: Pass }>();
    for (const s of status?.shots ?? []) {
      const inCut = clipTake(s, s.cut.placeholder ? other : undefined);
      const take = takeToOpen(inCut, s.takes);
      if (take) out.set(s.shot, { take: take.take, pass: take === inCut && s.cut.placeholder ? s.cut.pass : pass });
    }
    return out;
  }, [pass, status, other]);
  const tiles = useMemo(() => ({
    selected: tile,
    select: setTile,
    open: (s: BoardShot) => {
      const t = playable.get(s.id);
      if (!t) { openShotForm({ shot: s.id, after: null }); return; }
      openViewer(s.id, t.take, null, "single", t.pass);
      // over the board: a docked viewer, or one already open, would be behind it
      updateViewer({ floating: true });
      raiseWindow(VIEWER_RECT_KEY);
    },
  }), [tile, playable]);
  const chosen = scriptStructure ?? (structure || (names.find((n) => n.includes("Three-Act")) ?? names[0] ?? ""));

  // what the script already says wins, once, as the board opens
  useEffect(() => {
    if (seeded || !data) return;
    setSeeded(true);
    if (data.plan.structure && !data.plan.structure_known) setOwnFormat(data.plan.structure);
    if (data.plan.duration) setMinutes(String(Math.round((data.plan.duration / 60) * 100) / 100));
    else if (data.plan.shots) setMinutes(runtimeMinutes(data.plan.seconds, data.plan.untimed, each ?? 3.5));
  }, [data, seeded]);

  const seenHash = useRef<string | null>(null);
  const working = useRef(false);
  seenHash.current = data?.hash ?? null;
  working.current = busy;

  const ask = useCallback(() => {
    if (!chosen || length === null || each === null) return undefined;
    let live = true;
    const wait = setTimeout(() => {
      api().storyboard(ep, chosen, length * 60, each).then((r) => {
        if (!live) return;
        // changed by something other than this board: its undo steps no longer lead back from here
        if (seenHash.current && seenHash.current !== r.hash && !working.current) {
          setUndo([]);
          setRedo([]);
        }
        setData(r);
        setErr(null);
      }).catch((e) => live && setErr((e as Error).message));
    }, 150);
    return () => { live = false; clearTimeout(wait); };
    // status too: a save anywhere else (Edit Shot, the script editor) changes the script under the board
  }, [ep, chosen, length, each, status]);
  useEffect(() => ask(), [ask]);

  async function edit(e: StoryboardEdit): Promise<StoryboardAnswer | null> {
    if (!data || !chosen || length === null || each === null) return null;
    setBusy(true);
    try {
      const before = (await api().source(ep, "script")).text;
      const r = await api().storyboardEdit({ ep, base_hash: data.hash, structure: chosen, duration: length * 60, shot: each, ...e });
      setData(r);
      setErr(null);
      setUndo((u) => pushed(u, before));
      setRedo([]);
      if (e.op === "place") setPicked((p) => (p ? { ...p, place: e.place } : p));
      if (e.op === "cast") setPicked((p) => (p ? { ...p, who: e.who } : p));
      // deleting or adding moves the blocks the edit bar points at
      if (e.op !== "place" && e.op !== "cast") setPicked(null);
      void refreshEpisode(ep);
      return r;
    } catch (x) {
      setErr((x as Error).message);
      return null;
    } finally {
      setBusy(false);
    }
  }

  /** The timeline's order follows the script's for a shot just placed, as its own drops do. */
  async function followInCut(shot: string, left: string | null) {
    await refreshEpisode(ep);
    const cut = store.get().status[statusKey(ep, store.get().pass)]?.shots ?? [];
    if (cut.some((s) => s.shot === shot)) await moveClip(shot, gapAfter(cut, left));
  }

  const scriptOrder = () => (data?.plan.acts ?? []).flatMap((a) => a.beats.flatMap((b) => b.runs.flatMap((r) => r.shots)));

  async function moveShot(id: string, target: BoardShot, side: DropSide) {
    const all = scriptOrder();
    const moved = all.find((s) => s.id === id);
    if (!moved || moved.id === target.id) return;
    const left = shotBefore(all.map((s) => s.id), target.id, side, id);
    if (await edit({ op: "move_shot", block: moved.block, target: target.block, after: side === "after" })) await followInCut(id, left);
  }

  /** A picture dropped between two shots: a new held shot there, holding it. */
  async function pictureBetween(found: Promise<File[]>, target: BoardShot, side: DropSide) {
    const [file, ...more] = picturesInOrder(await found);
    if (!file) { setErr("Only a picture can go between shots here."); return; }
    const left = shotBefore(scriptOrder().map((s) => s.id), target.id, side);
    const r = await edit({ op: "add_after", block: target.block, before: side === "before" });
    const made = r?.made?.[0];
    if (!made) return;
    setBusy(true);
    await uploadRef(keyframeRefId(made, "first"), null, file, true);
    setBusy(false);
    if (more.length) setErr(`One picture at a time between shots: ${file.name} was used.`);
    if (length !== null && each !== null) setData(await api().storyboard(ep, chosen, length * 60, each));
    await followInCut(made, left);
  }

  /** The script back to `text`, saved as any edit is; the file's text now goes on `onto`. */
  async function restore(text: string, onto: (now: string) => void) {
    if (!data) return;
    setBusy(true);
    try {
      const now = await api().source(ep, "script");
      if (now.hash !== data.hash) throw new Error("The script changed somewhere else since this board read it: close and reopen the board before undoing.");
      await api().putSource({ ep, file: "script", text, base_hash: now.hash, rebuild: true });
      onto(now.text);
      setPicked(null);
      setErr(null);
      const r = await api().storyboard(ep, chosen, (length ?? 1) * 60, each ?? 3.5);
      setData(r);
      void refreshEpisode(ep);
    } catch (x) {
      setErr((x as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function undoEdit() {
    const text = undo[undo.length - 1];
    if (text === undefined || busy) return;
    setUndo((u) => u.slice(0, -1));
    void restore(text, (now) => setRedo((r) => pushed(r, now)));
  }

  function redoEdit() {
    const text = redo[redo.length - 1];
    if (text === undefined || busy) return;
    setRedo((r) => r.slice(0, -1));
    void restore(text, (now) => setUndo((u) => pushed(u, now)));
  }

  /** Pictures dropped on the board: each becomes its shot's first frame, in filename order. */
  async function frames(found: Promise<File[]>, shots: BoardShot[], single: boolean) {
    // a tile takes a video as its take; a sequence's empty shots are for pictures
    const files = single ? mediaInOrder(await found) : picturesInOrder(await found);
    const targets = dropTargets(single ? shots : shots.filter((s) => !videos.has(s.id)), single);
    if (!files.length) { setErr(single ? "That drop has no picture or video in it." : "That drop has no pictures in it."); return; }
    if (!targets.length) { setErr("There are no empty shots there to fill. Drop on the beat's + for a new shot each."); return; }
    const pairs = targets.slice(0, single ? 1 : files.length).map((s, i) => ({ shot: s, file: files[i] })).filter((p) => p.file);
    setBusy(true);
    setErr(null);
    let done = 0;
    let failed = 0;
    for (const { shot: target, file } of pairs) {
      setDropping(`Adding pictures: ${done + failed + 1} of ${pairs.length}`);
      if (single) {
        // the timeline's own drop: it also warns when the shot's model reads no first frame
        await dropFileOnto(target.id, file);
        done += 1;
      } else if (await uploadRef(keyframeRefId(target.id, "first"), null, file, true)) done += 1;
      else failed += 1;
    }
    setDropping(null);
    setBusy(false);
    const spare = files.length - pairs.length;
    if (failed || spare) setErr(`${done} added.${failed ? ` ${failed} couldn't be added.` : ""}${spare ? ` ${spare} left over: not enough empty shots.` : ""}`);
    if (length !== null && each !== null) setData(await api().storyboard(ep, chosen, length * 60, each));
    void refreshEpisode(ep);
  }

  /** Pictures and videos dropped on a beat, in filename order: the empty shots first, then a new
   * shot each, at its video's length, made in one edit so it's one undo. */
  async function picturesOnBeat(found: Promise<File[]>, beat: { plain: string; nth: number }, empties: BoardShot[]) {
    const files = mediaInOrder(await found);
    if (!files.length) { setErr("That drop has no pictures or videos in it."); return; }
    const { fill, extra } = fillThenAdd(files, dropTargets(empties.filter((s) => !videos.has(s.id)), false));
    let made: string[] = [];
    let order: string[] = [];
    if (extra.length) {
      const durs = await Promise.all(extra.map(async (f) => {
        const seconds = isVideoFile(f) ? await videoSeconds(f) : null;
        return seconds === null ? null : Math.max(0.1, Math.round(seconds * 10) / 10);
      }));
      const r = await edit({ op: "add", beat, durs });
      if (!r) return;
      made = r.made ?? [];
      order = r.plan.acts.flatMap((a) => a.beats.flatMap((b) => b.runs.flatMap((x) => x.shots.map((s) => s.id))));
    }
    const pairs = [...fill.map((p) => ({ id: p.shot.id, file: p.file })), ...extra.map((file, i) => ({ id: made[i], file }))].filter((p) => p.id);
    setBusy(true);
    setErr(null);
    let failed = 0;
    for (let i = 0; i < pairs.length; i += 1) {
      setDropping(`Adding pictures: ${i + 1} of ${pairs.length}`);
      const { id, file } = pairs[i];
      const ok = isVideoFile(file)
        ? (await importTakeFile(id, file)) !== null
        : await uploadRef(keyframeRefId(id, "first"), null, file, true);
      if (!ok) failed += 1;
      else if (isVideoFile(file) && made.includes(id)) await followInCut(id, order[order.indexOf(id) - 1] ?? null);
    }
    setDropping(null);
    setBusy(false);
    if (failed) setErr(`${pairs.length - failed} added. ${failed} couldn't be added.`);
    if (length !== null && each !== null) setData(await api().storyboard(ep, chosen, length * 60, each));
    void refreshEpisode(ep);
  }

  function keys(e: KeyboardEvent) {
    if (e.key === "Enter" && tile && !e.ctrlKey && !e.metaKey && !e.altKey) {
      const on = e.target as HTMLElement;
      if (on.closest("input, select, textarea") || !on.closest("button, .h3-sb")?.matches(".h3-sb-tile, .h3-sb")) return;
      e.preventDefault();
      openShotForm({ shot: tile, after: null });
      return;
    }
    if (!(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== "z") return;
    if ((e.target as HTMLElement).closest("input, select, textarea")) return;
    e.preventDefault();
    e.stopPropagation();
    if (e.shiftKey) redoEdit(); else undoEdit();
  }

  function fill(beats: BoardBeat[]) {
    const n = fillCount(beats);
    if (n >= BIG_FILL && !window.confirm(`Add ${n} shots to the script?`)) return;
    void edit({ op: "fill", beats: fillable(beats) });
  }

  async function sketch(ready: string[], unwritten: string[]) {
    const backend = store.get().renderBackend || undefined;
    if (isPaidBackend(backend) && !window.confirm(`Sketch ${ready.length} shots on ${backend}? Each is a paid run on your Comfy account.`)) return;
    setBusy(true);
    try {
      const r = await api().storyboardSketch({ ep, shots: ready, ...(backend ? { backend } : {}) });
      const notes = [
        ...(unwritten.length ? [`Left out, still the beat's guidance: ${unwritten.join(", ")}.`] : []),
        ...r.errors.map((x: { shot: string; error: string }) => `${x.shot}: ${x.error}`),
      ];
      setErr(notes.length ? notes.join(" ") : null);
    } catch (x) {
      setErr((x as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const plan = data?.plan;
  const allBeats = plan?.acts.flatMap((a) => a.beats) ?? [];
  const sketches = sketchable(allBeats, videos);
  const biggest = Math.max(0, ...allBeats.map((b) => b.target_shots ?? 0));
  const left = fillCount(allBeats);
  const bare = bareBeats(allBeats);
  const toRender = heldToRender(allBeats.flatMap((b) => b.runs.flatMap((r) => r.shots)), rendered.current);
  // shots and no beat lines: a structure can be laid over them
  const canLayOut = !!plan && plan.shots > 0 && !allBeats.some((b) => b.plain !== null && b.in_script) && names.includes(chosen);

  const head = (
    <>
      <i className="pi pi-th-large" />
      <b>Storyboard</b>
      <EpisodeSelect compact />
      <span className="h3-grow" />
      <button className="h3-btn h3-icon" aria-label="Edit the script" title="Edit the episode's script"
        onClick={() => openSource("script")}><i className="pi pi-file-edit" /></button>
      <button className="h3-btn h3-icon" aria-label="Series settings" title="Series settings: the series config as a form (its cast and places)"
        onClick={() => openSeriesForm()}><i className="pi pi-cog" /></button>
      <button className="h3-btn h3-icon" title="Close" onClick={() => openStoryboard(false)}><i className="pi pi-times" /></button>
    </>
  );
  return (
    <FloatingWindow storageKey="seriesmith.storyboard.rect" head={head} minW={520} minH={320}
      defaultRect={() => ({ x: 40, y: 48, w: Math.min(1280, window.innerWidth - 80), h: Math.min(820, window.innerHeight - 96) })}>
      <div className="h3-col h3-sb" style={{ height: "100%", outline: "none", "--sb-tile": `${TILE_SIZES[size]}px` } as CSSProperties} tabIndex={-1} onKeyDown={keys}>
        <div className="h3-row h3-sb-controls">
          <label className="h3-row" title={scriptStructure
            ? `Changes the script's // structure: line. Beats keep their names: the ones that match this structure take its acts and targets, the rest stay as the script has them.${data?.plan.structure_known ? "" : " A show's own format has no targets."}`
            : "Written to the script with the first edit"}>Structure
            <select value={chosen} disabled={busy} onChange={(e) => {
              if (scriptStructure) void edit({ op: "structure", name: e.target.value });
              else setStructure(e.target.value);
            }}>
              {ownFormat && <option value={ownFormat}>{ownFormat} (this show's own)</option>}
              {!names.includes(chosen) && chosen !== ownFormat && <option value={chosen}>{chosen}</option>}
              {names.map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
          <button className="h3-btn h3-icon" aria-label="Save as structure" disabled={!allBeats.some((b) => b.plain !== null && b.in_script)}
            title="Save this episode's beats as a structure of your own, to start other episodes from" onClick={() => setSaving(true)}><i className="pi pi-bookmark" /></button>
          <label className="h3-row" title="The length it's aiming at. It sets every beat's target, and only that.">Minutes
            <input className="h3-sb-num" type="number" min="0.1" step="any" value={minutes}
              onChange={(e) => setMinutes(e.target.value)} />
          </label>
          <label className="h3-row" title="A typical shot, in seconds: what a new shot is made at.">Shot length
            <input className="h3-sb-num" type="number" min="0.1" step="0.1" value={shot}
              onChange={(e) => setShot(e.target.value)} />
          </label>
          {plan && (
            <span className="h3-small h3-muted">
              {plan.shots}{plan.target_shots ? ` of ${plan.target_shots}` : ""} shots, {clock(plan.seconds)}
              {plan.untimed > 0 ? ` and ${plan.untimed} untimed` : ""}
            </span>
          )}
          <span className="h3-grow" />
          <span className="h3-seg" title="Thumbnail size">
            {(Object.keys(TILE_SIZES) as TileSize[]).map((k) => (
              <button key={k} className={size === k ? "h3-on" : ""} onClick={() => pickSize(k)}>{k.toUpperCase()}</button>
            ))}
          </span>
          <button className="h3-btn h3-icon" disabled={busy || !undo.length} title="Undo (Ctrl+Z)" onClick={undoEdit}><i className="pi pi-undo" /></button>
          <button className="h3-btn h3-icon" disabled={busy || !redo.length} title="Redo (Ctrl+Shift+Z)" onClick={redoEdit}><i className="pi pi-refresh" /></button>
          {sketches.ready.length + sketches.unwritten.length > 0 && (
            <button id="sm-sb-sketch" className="h3-btn" disabled={busy || !sketches.ready.length}
              title={`A first frame for each shot with no picture, from its action and the cast's pictures.${sketches.unwritten.length ? ` ${sketches.unwritten.length} still have the beat's guidance as their action and are left out: rewrite them first.` : ""}`}
              onClick={() => void sketch(sketches.ready, sketches.unwritten)}>Sketch ({sketches.ready.length})</button>
          )}
          {toRender.length > 0 && (
            <button className="h3-btn" disabled={busy} title="Render every held shot with no up-to-date take, on its picture or the gray card. Free, on this machine: the animatic, in the cut."
              onClick={() => requestRender(toRender, false, "Render the animatic")}>Render held ({toRender.length})</button>
          )}
          {bare.length > 0 && (
            <button className="h3-btn" disabled={busy} title="One held shot on every beat that has none: the episode blocked in, from start to end"
              onClick={() => void edit({ op: "fill", beats: bare, each: 1 })}>One per beat ({bare.length})</button>
          )}
          {left > 0 && <button className="h3-btn" disabled={busy} title="Make every beat's missing shots" onClick={() => fill(allBeats)}>Fill all ({left})</button>}
        </div>
        {picked && (
          <EditBar choices={choices} picked={picked} busy={busy} edit={(e) => void edit(e)} close={() => setPicked(null)} />
        )}
        {canLayOut && plan && (
          <div className="h3-row h3-sb-editbar h3-small">
            <span className="h3-grow">This script has {plan.shots} shots and no beats yet. Lay {chosen} over them, each beat on the shot nearest its place in the story? You can move and rename them after.</span>
            <button className="h3-btn h3-primary" disabled={busy} onClick={() => void edit({ op: "lay_out", name: chosen })}>Lay out beats</button>
          </div>
        )}
        {(length === null || each === null) && (
          <span className="h3-small h3-err" style={{ padding: "0 10px" }}>The minutes and the shot length need to be above zero.</span>
        )}
        {err && <span className="h3-small h3-err" style={{ padding: "0 10px" }}>{err}</span>}
        {dropping && <span className="h3-small h3-muted" style={{ padding: "0 10px" }}><i className="pi pi-spin pi-spinner" /> {dropping}</span>}
        {plan && plan.warnings.length > 0 && (
          <details className="h3-small h3-sb-warnings">
            <summary>{plan.warnings.length} {plan.warnings.length === 1 ? "warning" : "warnings"} at this length</summary>
            <ul>{plan.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
          </details>
        )}
        {saving && plan && (
          <SaveStructure plan={plan} saved={ownNames} file={ownFile} close={() => setSaving(false)} done={() => {
            setSaving(false);
            void loadStructures();
            if (length !== null && each !== null) void api().storyboard(ep, chosen, length * 60, each).then(setData);
          }} />
        )}
        {menu && (
          <BoardMenu menu={menu} choices={choices} busy={busy} edit={(e) => void edit(e)} close={() => setMenu(null)}
            rename={(b) => setRenamingBeat(b.block)} fresh={rendered.current} />
        )}
        <Tiles.Provider value={{ ...tiles, pictures: (e, beat, empties) => {
          if (!e.dataTransfer.types.includes("Files")) return;
          e.preventDefault();
          e.stopPropagation();
          void picturesOnBeat(filesFromDrag(e.dataTransfer), beat, empties);
        } }}>
        <div className="h3-sb-board">
          {plan?.acts.map((act, i) => {
            const key = `${act.act}${i}`;
            return (
              <ActRow key={key} act={act} label={act.act || plan.structure || "Episode"} biggest={biggest} shut={!!closed[key]} busy={busy} thumbs={thumbs}
                toggle={() => setClosed((c) => ({ ...c, [key]: !c[key] }))}
                picked={picked?.block ?? null}
                pick={(run) => run.block !== null && setPicked({
                  block: run.block, place: run.place, who: [...new Set(run.shots.flatMap((s) => s.who))] })}
                onFrames={(e, shots, single, side) => {
                  const moving = e.dataTransfer.getData(SHOT_MIME);
                  if (moving) {
                    e.preventDefault();
                    e.stopPropagation();
                    if (single && side) void moveShot(moving, shots[0], side);
                    return;
                  }
                  if (!e.dataTransfer.types.includes("Files")) return;
                  e.preventDefault();
                  e.stopPropagation();
                  if (single && side) void pictureBetween(filesFromDrag(e.dataTransfer), shots[0], side);
                  else void frames(filesFromDrag(e.dataTransfer), shots, single);
                }}
                onShotMenu={(e, s, last) => openAt(e, { kind: "shot", shot: s, last, rendered: thumbs.has(s.id) })}
                onRunMenu={(e, r) => openAt(e, { kind: "sequence", run: r })}
                onBeatMenu={(e, b) => openAt(e, { kind: "beat", beat: b })}
                onActMenu={(e, a) => openAt(e, { kind: "act", act: a })}
                renamingBeat={renamingBeat} setRenamingBeat={setRenamingBeat}
                edit={(e) => void edit(e)} fill={fill} />
            );
          })}
        </div>
        </Tiles.Provider>
      </div>
    </FloatingWindow>
  );
}
