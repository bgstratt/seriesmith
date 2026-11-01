// The episode's mix under the timeline's clips (docs/SOUND.md): a hits lane,
// then dialogue, effects, ambience and music, inside the scrolling track so
// they scroll with the clips. Each lane's head sticks to the left (its fader,
// mute, solo); its items are blocks placed from their anchors, measured
// against the clips' boxes (lib/mix: the timeline isn't one time axis), with
// their file's waveform and their gain line (the volume points, dB at anchors:
// drag a point, double-click the line for one, right-click one to delete it).
// Drag a block to move it, an edge to trim it, Esc cancels; right-click for its
// gain, fades, loop, label. A sound file dropped
// on a lane is imported and laid where it fell. Every edit is one PUT of the
// pass's mix (mixActions), undone with the cut's Ctrl+Z. A music cue's block
// opens the cue window on a double-click; right-click the music or hits lane
// for a new cue there (cueActions).

import {
  memo, useCallback, useEffect, useLayoutEffect, useRef, useState,
  type DragEvent, type MouseEvent as RMouseEvent, type PointerEvent as RPointerEvent, type RefObject,
} from "react";
import { seekCutAt } from "../cutActions";
import { framesLabel } from "../lib/cutEdit";
import { fmtClock } from "../lib/format";
import { dragHasFiles } from "../lib/lookback";
import {
  GAIN_MAX, GAIN_MIN, HIT_KINDS, HIT_KIND_TITLE, TRACKS, TRACK_LABEL, anchorTime, clampDb, dbY, defaultGain, fileName, itemSpan, layout,
  moveItem, movePoint, patchHit, pointsDb, snapDb, timeX, timedPoints, trackState, trimItem, xAnchor, xTime, type ClipBox, type Lay,
} from "../lib/mix";
import { binsFor } from "../lib/peaks";
import { clipTake, type PlayItem } from "../lib/playlist";
import {
  addMixHit, addMixPoint, clearMixPoints, currentMix, deleteMixHit, deleteMixItem, deleteMixPoint, dropOnLane, moveMixHit, moveMixItem,
  moveMixPoint, pickSoundFile, setMixHit, setMixItem, setTrackMix, trimMixItem,
} from "../mixActions";
import { host } from "../host";
import { openSound } from "../actions";
import { loadCues, newCue, openCue } from "../cueActions";
import { cueTitle } from "../lib/cue";
import { statusKey, store, useApp } from "../store";
import type { Anchor, CueKind, EpisodeStatus, HitKind, Mix, MixHit, MixItem, MixTrack } from "../types";
import { trackPointer } from "./hooks";
import { PeaksCanvas, WaveLane, usePeaks, useSeen } from "./Waveform";

/** the hits lane */
export const HITS_H = 16;
/** each track's lane */
export const LANE_H = 22;
/** the lanes' heads (sticky, on the left) */
export const HEAD_W = 184;
/** all of it, gaps included */
export const LANES_H = HITS_H + TRACKS.length * (LANE_H + 1) + 1;
/** a block's inside, where its waveform and gain line are drawn */
const BLOCK_H = LANE_H - 6;
/** px from a volume point that pick it up; from the gain line that a double-click adds one */
const POINT_HIT = 5;
const LINE_HIT = 4;
/** dB per px of a point dragged up or down (the block is too short to put it where the pointer is) */
const DB_PER_PX = 0.5;

const EMPTY: number[] = [];

/** A sound file, by its type or its name (the server checks it too). */
export function isSoundFile(f: { name: string; type?: string }): boolean {
  return (f.type ?? "").startsWith("audio/") || /\.(wav|mp3|flac|ogg|oga|m4a|aac|opus|aiff?|caf|mp4|mov|webm)$/i.test(f.name);
}

/** What is being dragged, and the mix it would make (drawn instead of the stored one). */
interface Drag {
  what: "move" | "in" | "out" | "hit" | "point";
  id: string;
  at: Anchor;
  mix: Mix;
  px: number;
  py: number;
  /** a volume point's level */
  db?: number;
}

/** The item or hit menu, at the pointer. */
type Pop = { kind: "item" | "hit"; id: string; x: number; y: number };

/** The lane menu (a new cue), at the pointer: `at` where it was asked. */
/** A lane's right-click: where, the lane (null: the hits lane) and the anchor under it. */
type LaneMenu = { x: number; y: number; track: MixTrack | null; at: Anchor | null };

const NO_CUES: [string, string][] = [];

export const SoundLanes = memo(function SoundLanes({ ep, st, other, items, innerRef, fps, zoom, measureKey }: {
  ep: string; st: EpisodeStatus; other: EpisodeStatus | undefined; items: PlayItem[];
  innerRef: RefObject<HTMLDivElement>; fps: number; zoom: number;
  /** changes whenever the clips may have moved (zoom, the cut, a trim preview) */
  measureKey: unknown;
}) {
  const res = useApp((s) => currentMix(s));
  const err = useApp((s) => s.mixError[statusKey(ep, s.pass)]);
  const [boxes, setBoxes] = useState<ClipBox[]>([]);
  const [drag, setDrag] = useState<Drag | null>(null);
  const [pop, setPop] = useState<Pop | null>(null);
  const [over, setOver] = useState<MixTrack | null>(null);
  const [laneMenu, setLaneMenu] = useState<LaneMenu | null>(null);
  const suppress = useRef(false);
  // the episode's cues: which music blocks open the cue window (fetched again with the mix)
  const cueIds = useApp((s) => s.cues[ep]?.map((c) => `${c.spec.id}:${c.spec.kind ?? "score"}`).join(" ") ?? "");
  const cueKinds = new Map(cueIds ? cueIds.split(" ").map((x) => x.split(":") as [string, string]) : NO_CUES);
  useEffect(() => {
    void loadCues(ep);
  }, [ep, res?.mix]);

  // the clips' boxes, in the track's coordinates
  const measure = useCallback(() => {
    const inner = innerRef.current;
    if (!inner) return;
    const ir = inner.getBoundingClientRect();
    const next = [...inner.querySelectorAll<HTMLElement>("[data-shot]")].map((el) => {
      const r = el.getBoundingClientRect();
      return { shot: el.dataset.shot ?? "", left: r.left - ir.left, width: r.width };
    });
    setBoxes((b) => (JSON.stringify(b) === JSON.stringify(next) ? b : next));
  }, [innerRef]);
  useLayoutEffect(measure, [measure, measureKey, items, st]);
  useEffect(() => {
    const inner = innerRef.current;
    if (!inner || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => measure());
    ro.observe(inner);
    return () => ro.disconnect();
  }, [innerRef, measure]);

  const lay = layout(boxes, items);
  const mix = drag?.mix ?? res?.mix ?? {};
  const xOf = (clientX: number) => clientX - (innerRef.current?.getBoundingClientRect().left ?? 0);
  const endDrag = () => {
    suppress.current = true;
    setTimeout(() => (suppress.current = false), 0);
  };
  const focusSurface = () => (innerRef.current?.closest(".h3-timeline") as HTMLElement | null)?.focus({ preventScroll: true });

  // ---- items: move, trim ----
  const onItemDown = (e: RPointerEvent<HTMLElement>, it: MixItem, what: "move" | "in" | "out", fileSecs: number | null) => {
    if (e.button !== 0 || !res) return;
    e.stopPropagation();
    e.preventDefault();
    focusSurface();
    const base = res.mix;
    const span = itemSpan(items, it, fps, fileSecs);
    if (!span) return;
    const x0 = e.clientX;
    const from = what === "out" ? timeX(lay, span.end ?? span.start) : timeX(lay, span.start);
    let at: Anchor | null = null;
    let moved = false;
    trackPointer((ev) => {
      if (!moved && Math.abs(ev.clientX - x0) < 3) return;
      moved = true;
      at = xAnchor(lay, from + ev.clientX - x0, fps);
      if (!at) return;
      const next = what === "move" ? moveItem(base, it.id, at, items, fps) : trimItem(base, it.id, what, at, items, fps, fileSecs);
      setDrag({ what, id: it.id, at, mix: next ?? base, px: ev.clientX, py: ev.clientY });
    }, (cancelled) => {
      setDrag(null);
      if (!moved) return;
      endDrag();
      if (cancelled || !at) return;
      if (what === "move") void moveMixItem(it.id, at);
      else void trimMixItem(it.id, what, at, fileSecs);
    });
  };

  // ---- hits: move ----
  const onHitDown = (e: RPointerEvent<HTMLElement>, h: MixHit) => {
    if (e.button !== 0 || !res) return;
    e.stopPropagation();
    e.preventDefault();
    focusSurface();
    const base = res.mix;
    const t = anchorTime(items, h.at, fps);
    if (t == null) return;
    const from = timeX(lay, t);
    const x0 = e.clientX;
    let at: Anchor | null = null;
    trackPointer((ev) => {
      if (!at && Math.abs(ev.clientX - x0) < 3) return;
      at = xAnchor(lay, from + ev.clientX - x0, fps);
      if (at) setDrag({ what: "hit", id: h.id, at, mix: patchHit(base, h.id, { at }) ?? base, px: ev.clientX, py: ev.clientY });
    }, (cancelled) => {
      setDrag(null);
      if (!at) return;
      endDrag();
      if (!cancelled) void moveMixHit(h.id, at);
    });
  };

  // ---- volume points: dragged up and down (dB) and along (re-anchored), added, deleted ----
  const onPointDown = (e: RPointerEvent<Element>, it: MixItem, i: number, fileSecs: number | null) => {
    if (e.button !== 0 || !res) return;
    e.stopPropagation();
    e.preventDefault();
    focusSurface();
    const base = res.mix;
    const p = it.points?.[i];
    const t = p ? anchorTime(items, p.at, fps) : null;
    const span = itemSpan(items, it, fps, fileSecs);
    if (!p || t == null || !span) return;
    const x0 = e.clientX;
    const y0 = e.clientY;
    const from = timeX(lay, t);
    const lo = timeX(lay, span.start);
    const hi = timeX(lay, span.end ?? span.start);
    let at: Anchor = p.at;
    let db = p.db;
    let moved = false;
    trackPointer((ev) => {
      if (!moved && Math.abs(ev.clientX - x0) < 3 && Math.abs(ev.clientY - y0) < 3) return;
      moved = true;
      // along: the shot and frame under it, kept on the block (a nudge leaves it where it was)
      at = Math.abs(ev.clientX - x0) < 3 ? p.at : xAnchor(lay, Math.min(hi, Math.max(lo, from + ev.clientX - x0)), fps) ?? p.at;
      db = snapDb(p.db - (ev.clientY - y0) * DB_PER_PX);
      setDrag({ what: "point", id: it.id, at, db, mix: movePoint(base, it.id, i, at, db, items, fps) ?? base, px: ev.clientX, py: ev.clientY });
    }, (cancelled) => {
      setDrag(null);
      if (!moved) return;
      endDrag();
      if (!cancelled) void moveMixPoint(it.id, i, at, db);
    });
  };
  const onAddPoint = (e: RMouseEvent<HTMLElement>, it: MixItem) => {
    const at = lay.length ? xAnchor(lay, xOf(e.clientX), fps) : null;    if (at) void addMixPoint(it.id, at);
  };

  // ---- a click on a lane seeks; a double-click on the hits lane adds a hit there ----
  const onLaneClick = (e: RMouseEvent<HTMLElement>) => {
    if (suppress.current || !lay.length) return;
    seekCutAt(xTime(lay, xOf(e.clientX)));
  };
  const onLaneMenu = (e: RMouseEvent<HTMLElement>, track: MixTrack | null) => {
    e.preventDefault();
    e.stopPropagation();
    setLaneMenu({ x: e.clientX, y: e.clientY, track, at: lay.length ? xAnchor(lay, xOf(e.clientX), fps) : null });
  };
  const onHitsDouble = async (e: RMouseEvent<HTMLElement>) => {
    const at = lay.length ? xAnchor(lay, xOf(e.clientX), fps) : null;
    const x = e.clientX;
    const y = e.clientY;
    const id = at ? await addMixHit(at) : null;
    if (id) setPop({ kind: "hit", id, x, y });
  };

  // ---- a sound file from the desktop onto a lane ----
  const onDragOver = (e: DragEvent<HTMLElement>, track: MixTrack) => {
    if (!dragHasFiles(e.dataTransfer)) return;
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = "copy";
    if (over !== track) setOver(track);
  };
  const onDrop = (e: DragEvent<HTMLElement>, track: MixTrack) => {
    if (!dragHasFiles(e.dataTransfer)) return;
    e.preventDefault();
    e.stopPropagation();
    setOver(null);
    const files = [...(e.dataTransfer.files ?? [])];
    const file = files.find(isSoundFile);
    if (!file) {
      host().toast("warn", "Not a sound file", `${files.map((f) => f.name).join(", ")}: drop a wav, mp3, flac, ogg or m4a on a lane.`);
      return;
    }
    if (files.length > 1) host().toast("warn", "One file at a time", `${file.name} is used; drop the others one by one.`);
    const at = lay.length ? xAnchor(lay, xOf(e.clientX), fps) : null;
    if (at) void dropOnLane(track, file, at);
  };

  const hits = mix.hits ?? [];
  const hitXs = hits.map((h) => {
    const t = anchorTime(items, h.at, fps);
    return { h, x: t == null ? null : timeX(lay, t) };
  });
  const soloed = TRACKS.some((t) => trackState(res, t).solo);

  return (
    <div className="h3-snd" style={{ height: LANES_H }}>
      <div className="h3-snd-lane h3-snd-hits" style={{ height: HITS_H }} onClick={onLaneClick} onDoubleClick={(e) => void onHitsDouble(e)}
        onContextMenu={(e) => onLaneMenu(e, null)}
        title="Hits: the moments a cue lands on. Double-click: a hit here · the + adds one at the Play all playhead · drag a hit to move it · right-click or double-click it: name, kind, delete · right-click the lane: a new cue">
        <div className="h3-snd-head" style={{ width: HEAD_W }}>
          <span>Hits</span>
          {err && <i className="pi pi-exclamation-triangle h3-err" title={`The mix didn't load: ${err}`} />}
          <span className="h3-grow" />
          <button className="h3-snd-btn" title="Add a hit at the Play all playhead" onClick={(e) => {
            e.stopPropagation();
            const x = e.clientX;
            const y = e.clientY;
            void addMixHit().then((id) => id && setPop({ kind: "hit", id, x, y }));
          }}><i className="pi pi-plus" /></button>
        </div>
        {hitXs.map(({ h, x }) => x != null && (
          <div key={h.id} className={`h3-snd-hit h3-hit-${h.kind ?? "accent"}${h.must === false ? " h3-hit-may" : ""}${drag?.what === "hit" && drag.id === h.id ? " h3-on" : ""}`}
            style={{ left: x }}
            title={`${h.name || h.id} · ${h.at.shot} frame ${h.at.frame} · ${h.kind ?? "accent"}: ${HIT_KIND_TITLE[h.kind ?? "accent"]}${h.must === false ? " · may miss" : ""}\ndrag: move · double-click or right-click: name, kind, delete`}
            onPointerDown={(e) => onHitDown(e, h)}
            onClick={(e) => e.stopPropagation()}
            onDoubleClick={(e) => {
              e.stopPropagation();
              setPop({ kind: "hit", id: h.id, x: e.clientX, y: e.clientY });
            }}
            onContextMenu={(e) => {
              e.preventDefault();
              e.stopPropagation();
              setPop({ kind: "hit", id: h.id, x: e.clientX, y: e.clientY });
            }}>
            <span>{h.name || h.id}</span>
          </div>
        ))}
      </div>
      {TRACKS.map((track) => {
        const ts = trackState(res, track);
        const silent = ts.mute || (soloed && !ts.solo);
        return (
          <div key={track} className={`h3-snd-lane${over === track ? " h3-drop-onto" : ""}${silent ? " h3-snd-silent" : ""}`} style={{ height: LANE_H }}
            onClick={onLaneClick}
            onDragOver={(e) => onDragOver(e, track)}
            onDragLeave={(e) => !e.currentTarget.contains(e.relatedTarget as Node | null) && setOver(null)}
            onDrop={(e) => onDrop(e, track)}
            onContextMenu={(e) => onLaneMenu(e, track)}
            title={`${TRACK_LABEL[track]}: drop a sound file here to lay it from where it falls · click: seek · right-click: ${track === "music" ? "a new cue here, a sound file" : track === "dialogue" ? "the shot's sound, a sound file" : "a sound file"}`}>
            <LaneHead track={track} gain={ts.gain_db} mute={ts.mute} solo={ts.solo} ready={!!res}
              series={res?.series?.tracks?.[track]?.gain_db ?? null} fallback={defaultGain(res, track)}
              own={res?.mix.tracks?.[track]?.gain_db != null} />
            {track === "dialogue" && lay.map((l) => {
              const s = st.shots.find((x) => x.shot === l.shot);
              const it = items.find((x) => x.shot === l.shot);
              return s && (
                <div key={l.shot} className="h3-snd-own" style={{ left: l.left, width: l.width }}>
                  <WaveLane ep={ep} s={s} item={it} take={clipTake(s, s.cut.placeholder ? other : undefined)} st={st} width={l.width} height={LANE_H - 4} zoom={zoom} />
                </div>
              );
            })}
            {(mix.items ?? []).filter((it) => it.track === track).map((it) => (
              <Block key={it.id} ep={ep} it={it} lay={lay} items={items} fps={fps} cue={it.track === "music" ? (cueKinds.get(it.id) as CueKind | undefined) ?? null : null}
                dragging={!!drag && drag.what !== "hit" && drag.what !== "point" && drag.id === it.id}
                onDown={onItemDown} onPointDown={onPointDown} onAddPoint={onAddPoint}
                onPointMenu={(i) => void deleteMixPoint(it.id, i)}
                onMenu={(e) => setPop({ kind: "item", id: it.id, x: e.clientX, y: e.clientY })} />
            ))}
          </div>
        );
      })}
      {hitXs.map(({ h, x }) => x != null && (
        <div key={h.id} className={`h3-snd-hitline h3-hit-${h.kind ?? "accent"}`} style={{ left: x, top: HITS_H }} />
      ))}
      {drag && (
        <div className="h3-trim-tip" style={{ left: drag.px + 14, top: drag.py - 34 }}>
          {drag.what === "hit" ? `hit ${drag.id}` : drag.what === "point" ? `${drag.id} volume point ${(drag.db ?? 0) > 0 ? "+" : ""}${drag.db ?? 0} dB`
            : `${drag.id} ${drag.what === "move" ? "start" : drag.what === "in" ? "head" : "tail"}`} · {drag.at.shot} frame {drag.at.frame}
          {(() => {
            const t = anchorTime(items, drag.at, fps);
            return t == null ? null : <> · {fmtClock(t)}</>;
          })()}
          <br />
          <span className="h3-muted">anchored to {drag.at.shot}: it moves with the shot · Esc cancels</span>
        </div>
      )}
      {pop && <MixPopover pop={pop} mix={res?.mix ?? {}} fps={fps} onClose={() => setPop(null)} />}
      {laneMenu && <LaneMenu menu={laneMenu} onClose={() => setLaneMenu(null)} />}
    </div>
  );
});

/**
 * A lane's head: the name, the fader (dB), mute and solo. A level set here is
 * the mix's own, kept as given (0 on music too: its default is -12); a
 * double-click drops it, back to the series config's or the default.
 */
function LaneHead({ track, gain, mute, solo, ready, series, fallback, own }: {
  track: MixTrack; gain: number; mute: boolean; solo: boolean; ready: boolean;
  /** the series config's level (null: none), and the default under it */
  series: number | null; fallback: number;
  /** the mix sets its own */
  own: boolean;
}) {
  const under = series ?? fallback;
  const db = (x: number) => `${x > 0 ? "+" : ""}${x} dB`;
  const [v, setV] = useState(gain);
  const held = useRef(false);
  useEffect(() => {
    if (!held.current) setV(gain);
  }, [gain]);
  const commit = (x: number) => {
    held.current = false;
    const db = clampDb(x);
    if (db !== gain) void setTrackMix(track, { gain_db: db });
  };
  return (
    <div className="h3-snd-head" style={{ width: HEAD_W }} onClick={(e) => e.stopPropagation()}
      onPointerDown={(e) => e.stopPropagation()}>
      <span className="h3-snd-name">{TRACK_LABEL[track]}</span>
      <input type="range" className="h3-snd-fader" min={GAIN_MIN} max={GAIN_MAX} step={0.5} value={v} disabled={!ready}
        aria-label={`${TRACK_LABEL[track]} fader`}
        title={`${TRACK_LABEL[track]}: ${db(v)}${own ? "" : series != null ? " (the series config's)" : " (the default)"} · double-click: ${db(under)}, ${series != null ? "the series config's" : "the default"}${track === "dialogue" ? "\nThe clips' own sound, and anything put on this lane" : ""}`}
        onPointerDown={() => (held.current = true)}
        onChange={(e) => {
          setV(Number(e.target.value));
          // a key press changes it at once; a drag when the pointer comes up
          if (!held.current) commit(Number(e.target.value));
        }}
        onPointerUp={(e) => commit(Number((e.target as HTMLInputElement).value))}
        onDoubleClick={() => {
          held.current = false;
          setV(under);
          // (no level of its own: nothing to change, and no edit)
          void setTrackMix(track, { gain_db: null });
        }} />
      <span className={`h3-snd-db h3-mono${own ? "" : " h3-muted"}`} title={own ? "the mix's own level" : series != null ? "the series config's level" : "the default level"}>{v <= GAIN_MIN ? "-∞" : `${v > 0 ? "+" : ""}${v}`}</span>
      <button className={`h3-snd-btn${mute ? " h3-on h3-snd-mute" : ""}`} disabled={!ready} title={mute ? "Unmute" : "Mute"}
        onClick={() => void setTrackMix(track, { mute: !mute })}>M</button>
      <button className={`h3-snd-btn${solo ? " h3-on h3-snd-solo" : ""}`} disabled={!ready} title={solo ? "Unsolo" : "Solo: hear only the soloed tracks"}
        onClick={() => void setTrackMix(track, { solo: !solo })}>S</button>
    </div>
  );
}

/** An item: a block from its in to its out (or its file's end), with its waveform. */
const Block = memo(function Block({ ep, it, lay, items, fps, cue, dragging, onDown, onMenu, onPointDown, onAddPoint, onPointMenu }: {
  ep: string; it: MixItem; lay: Lay[]; items: PlayItem[]; fps: number; dragging: boolean;
  /** a music cue's kind (null: not a cue): a double-click opens its window */
  cue: CueKind | null;
  onDown: (e: RPointerEvent<HTMLElement>, it: MixItem, what: "move" | "in" | "out", fileSecs: number | null) => void;
  onMenu: (e: RMouseEvent<HTMLElement>) => void;
  /** a volume point picked up (`i`: its index in the item's points) */
  onPointDown: (e: RPointerEvent<Element>, it: MixItem, i: number, fileSecs: number | null) => void;
  /** a double-click on the gain line: a point there */
  onAddPoint: (e: RMouseEvent<HTMLElement>, it: MixItem) => void;
  /** a right-click on a point: delete it */
  onPointMenu: (i: number) => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const seen = useSeen(box);
  // the file's length first (one bin), then its waveform over what plays
  const info = usePeaks({ ep, path: it.path, bins: 1 }, seen);
  const fileSecs = info?.ok ? info.data.duration : null;
  const span = itemSpan(items, it, fps, fileSecs);
  const start = span ? timeX(lay, span.start) : 0;
  const endT = span ? span.end ?? span.start + 1 : 0;
  const end = span ? timeX(lay, endT) : 0;
  const width = Math.max(4, end - start);
  const offset = it.offset ?? 0;
  const secs = Math.max(0, endT - (span?.start ?? 0));
  const fileEnd = fileSecs != null && !it.loop ? Math.min(fileSecs, offset + secs) : offset + secs;
  const q = span && fileEnd > offset ? { ep, path: it.path, bins: binsFor(fileEnd - offset, width / Math.max(0.01, secs)), start: offset, end: fileEnd } : null;
  const peaks = usePeaks(q, seen && fileSecs != null);
  if (!span) {
    return null;
  }
  const label = it.label || fileName(it.path);
  const fadeW = (frames: number | undefined) => (frames ? Math.min(width, (frames / fps) * (width / Math.max(0.01, secs))) : 0);
  const title = [
    `${label} (${it.id}) · ${it.path}`,
    `from ${it.in.shot} frame ${it.in.frame}${it.out ? ` to ${it.out.shot} frame ${it.out.frame}` : ", to the file's end"}${offset ? ` · ${offset.toFixed(2)} s into the file` : ""}`,
    [it.gain_db ? `${it.gain_db > 0 ? "+" : ""}${it.gain_db} dB` : "", it.fade_in ? `fade in ${framesLabel(it.fade_in, fps)}` : "",
     it.fade_out ? `fade out ${framesLabel(it.fade_out, fps)}` : "", it.loop ? "loops" : "", it.points?.length ? `${it.points.length} level points` : ""].filter(Boolean).join(" · "),
    info && !info.ok ? `can't read it: ${info.error}` : "",
    `${cue ? `music cue ${it.id}: double-click opens it (its sections, arc and takes) · ` : ""}drag: move (it stays on the shot it starts in) · drag an edge: trim · right-click: gain, fades, loop, label, delete`,
    "the line: its volume points (dB on its gain) · double-click on the line: a point · drag a point: up and down its dB, along its shot and frame · right-click a point: delete it",
  ].filter(Boolean).join("\n");
  // the gain line: its points over the block, the first held to its head, the last to its tail
  const pts = timedPoints(items, it, fps).map((p) => ({ ...p, x: timeX(lay, p.t) - start }));
  const lineY = (x: number) => dbY(pointsDb(pts.map((p) => ({ t: p.x, db: p.db })), x), BLOCK_H);
  return (
    <div ref={box} className={`h3-snd-item h3-snd-${it.track}${dragging ? " h3-on" : ""}`} style={{ left: start, width }} title={title}
      onPointerDown={(e) => onDown(e, it, "move", fileSecs)}
      onClick={(e) => e.stopPropagation()}
      onDoubleClick={(e) => {
        e.stopPropagation();
        // on the gain line: a point there; elsewhere a cue's block opens its window
        const r = e.currentTarget.getBoundingClientRect();
        if (Math.abs(e.clientY - r.top - 1 - lineY(e.clientX - r.left - 1)) <= LINE_HIT) onAddPoint(e, it);
        else if (cue) openCue(it.id);
      }}
      onContextMenu={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onMenu(e);
      }}>
      {q && <PeaksCanvas peaks={peaks?.ok ? peaks.data.peaks : EMPTY} width={Math.max(1, (Math.min(fileEnd, offset + secs) - offset) / Math.max(0.01, secs) * width)} height={LANE_H - 6} />}
      {fadeW(it.fade_in) > 0 && <div className="h3-snd-fade h3-l" style={{ width: fadeW(it.fade_in) }} />}
      {fadeW(it.fade_out) > 0 && <div className="h3-snd-fade h3-r" style={{ width: fadeW(it.fade_out) }} />}
      <svg className="h3-snd-gain" width={width} height={BLOCK_H}>
        <line className="h3-snd-zero" x1={0} x2={width} y1={dbY(0, BLOCK_H)} y2={dbY(0, BLOCK_H)} />
        {pts.length > 0 && (
          <>
            <polyline className="h3-snd-gainline"
              points={[`0,${dbY(pts[0].db, BLOCK_H)}`, ...pts.map((p) => `${p.x},${dbY(p.db, BLOCK_H)}`), `${width},${dbY(pts[pts.length - 1].db, BLOCK_H)}`].join(" ")} />
            {pts.map((p) => (
              <g key={p.i}>
                <circle className="h3-snd-pt" cx={p.x} cy={dbY(p.db, BLOCK_H)} r={2.5} />
                <circle className="h3-snd-pt-hit" cx={p.x} cy={dbY(p.db, BLOCK_H)} r={POINT_HIT}
                  onPointerDown={(e) => onPointDown(e, it, p.i, fileSecs)}
                  onDoubleClick={(e) => e.stopPropagation()}
                  onContextMenu={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    onPointMenu(p.i);
                  }}>
                  <title>{`${p.db > 0 ? "+" : ""}${p.db} dB at ${it.points![p.i].at.shot} frame ${it.points![p.i].at.frame} · drag: its level and place · right-click: delete`}</title>
                </circle>
              </g>
            ))}
          </>
        )}
      </svg>
      {width > 30 && <span className="h3-snd-label">{it.loop && <i className="pi pi-replay" />}{cue && <i className="pi pi-volume-up" />} {cue ? cueTitle({ id: it.id, kind: cue, label: it.label }) : label}</span>}
      <div className="h3-trim-h h3-l" title="Drag: where it starts (the sound stays where it was)" onPointerDown={(e) => onDown(e, it, "in", fileSecs)} />
      <div className="h3-trim-h h3-r" title="Drag: where it stops" onPointerDown={(e) => onDown(e, it, "out", fileSecs)} />
    </div>
  );
});

/** An item's or a hit's settings, at the pointer: Enter or Apply saves (one edit), Esc closes. */
function MixPopover({ pop, mix, fps, onClose }: { pop: Pop; mix: Mix; fps: number; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const item = pop.kind === "item" ? mix.items?.find((x) => x.id === pop.id) : undefined;
  const hit = pop.kind === "hit" ? mix.hits?.find((x) => x.id === pop.id) : undefined;
  const [f, setF] = useState(() => ({
    label: item?.label ?? hit?.name ?? "",
    gain: String(item?.gain_db ?? 0),
    fadeIn: String(item?.fade_in ?? 0),
    fadeOut: String(item?.fade_out ?? 0),
    loop: !!item?.loop,
    kind: (hit?.kind ?? "accent") as HitKind,
    must: hit?.must !== false,
  }));
  const [pos, setPos] = useState({ left: pop.x, top: pop.y });
  useLayoutEffect(() => {
    const r = ref.current?.getBoundingClientRect();
    if (r) setPos(onScreen(pop.x, pop.y, r));
  }, [pop]);
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
  if (!item && !hit) return null;
  const frames = (s: string) => Math.max(0, Math.round(Number(s) || 0));
  const apply = () => {
    if (item) {
      void setMixItem(item.id, {
        label: f.label, gain_db: clampDb(Number(f.gain)), fade_in: frames(f.fadeIn), fade_out: frames(f.fadeOut), loop: f.loop,
      }, `Change ${item.id}`);
    } else if (hit) {
      void setMixHit(hit.id, { name: f.label, kind: f.kind, must: f.must }, `Change hit ${hit.id}`);
    }
    onClose();
  };
  const field = (label: string, el: JSX.Element, title?: string) => (
    <label className="h3-snd-field" title={title}><span>{label}</span>{el}</label>
  );
  return (
    <div ref={ref} className="h3-menu h3-snd-pop" style={pos} onClick={(e) => e.stopPropagation()} onPointerDown={(e) => e.stopPropagation()}
      onKeyDown={(e) => {
        e.stopPropagation();
        if (e.key === "Enter") apply();
      }}>
      <div className="h3-menu-head">
        {item ? `${item.id} · ${fileName(item.path)}` : `hit ${hit!.id} · ${hit!.at.shot} frame ${hit!.at.frame}`}
      </div>
      {field(item ? "Label" : "Name", <input className="h3-in" autoFocus value={f.label} onChange={(e) => setF({ ...f, label: e.target.value })} />)}
      {item && (
        <>
          {field("Gain dB", <input className="h3-in" type="number" step={0.5} min={GAIN_MIN} max={GAIN_MAX} value={f.gain} onChange={(e) => setF({ ...f, gain: e.target.value })} />)}
          {field("Fade in", <input className="h3-in" type="number" min={0} max={2400} value={f.fadeIn} onChange={(e) => setF({ ...f, fadeIn: e.target.value })} />, `frames (${framesLabel(frames(f.fadeIn), fps)})`)}
          {field("Fade out", <input className="h3-in" type="number" min={0} max={2400} value={f.fadeOut} onChange={(e) => setF({ ...f, fadeOut: e.target.value })} />, `frames (${framesLabel(frames(f.fadeOut), fps)})`)}
          {field("Loop", <input type="checkbox" checked={f.loop} onChange={(e) => setF({ ...f, loop: e.target.checked })} />, "Play the file again, crossfaded, until its out")}
          {!!item.points?.length && (
            <button title={`Its ${item.points.length} volume point${item.points.length === 1 ? "" : "s"} taken out: it plays at its gain throughout`}
              onClick={() => {
                void clearMixPoints(item.id);
                onClose();
              }}>
              <i className="pi pi-eraser" /> Clear the volume points
            </button>
          )}
        </>
      )}
      {hit && (
        <>
          {field("Kind", (
            <select className="h3-in" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value as HitKind })}>
              {HIT_KINDS.map((k) => <option key={k} value={k} title={HIT_KIND_TITLE[k]}>{k}</option>)}
            </select>
          ), HIT_KIND_TITLE[f.kind])}
          {field("Must land", <input type="checkbox" checked={f.must} onChange={(e) => setF({ ...f, must: e.target.checked })} />,
            "Off: it may miss when one tempo can't land every hit")}
        </>
      )}
      <div className="h3-row" style={{ gap: 6, padding: "4px 8px" }}>
        <button className="h3-btn h3-primary" style={{ width: "auto" }} onClick={apply}>Apply</button>
        <span className="h3-grow" />
        <button className="h3-btn" style={{ width: "auto" }} onClick={() => {
          void (item ? deleteMixItem(item.id) : deleteMixHit(hit!.id));
          onClose();
        }}><i className="pi pi-trash" /> Delete</button>
      </div>
    </div>
  );
}

/** A lane's menu at the pointer (kept on screen: the lanes sit at the window's foot): a sound
 * file from this computer onto it; on music and hits, a new cue; on dialogue, the shot's own
 * sound (its Sound card, Replace audio); on effects and ambience, what will make them. */
function LaneMenu({ menu, onClose }: { menu: LaneMenu; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const multi = useApp((s) => s.multi);
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
  const over = multi.length > 1;
  const at = menu.at;
  const track = menu.track;
  const run = (fn: () => void) => () => {
    onClose();
    fn();
  };
  return (
    <div ref={ref} className="h3-menu h3-snd-pop" style={pos} onClick={(e) => e.stopPropagation()} onPointerDown={(e) => e.stopPropagation()}>
      <div className="h3-menu-head">{track ? TRACK_LABEL[track] : "Hits"} · {at ? `${at.shot} frame ${at.frame}` : "outside the cut"} · {store.get().pass}</div>
      {(track === "music" || !track) && (
        <button disabled={!over && !at} title="A cue: its sections, arc and takes in the cue window, written to the hits in its span"
          onClick={run(() => void newCue(at))}>
          <i className="pi pi-volume-up" /> {over ? `New cue over the ${multi.length} shots selected…` : `New cue here (to the end of ${at?.shot ?? "the shot"})…`}
        </button>
      )}
      {track === "dialogue" && at && (
        <>
          <button title={`How ${at.shot}'s sound is made: generate, clone, or dub a track (its voices and dub tracks)`} onClick={run(() => openSound([at.shot]))}>
            <i className="pi pi-microphone" /> {at.shot}'s sound…
          </button>
          <button title={`${at.shot}'s picture with another take's (or a file's) sound under it`} onClick={run(() => openSound([at.shot], "cut"))}>
            <i className="pi pi-volume-up" /> Replace {at.shot}'s audio…
          </button>
        </>
      )}
      {track === "effects" && (
        <button disabled title="Coming (docs/SOUND.md phase 4): the shot's effects made from its take by a foley model">
          <i className="pi pi-bolt" /> Effects from {at?.shot ?? "the shot"}'s take…
        </button>
      )}
      {track === "ambience" && (
        <button disabled title="Coming (docs/SOUND.md phase 3): the location's room tone or air, made once and looped under its shots">
          <i className="pi pi-cloud" /> The location's ambience bed…
        </button>
      )}
      {track && (
        <button disabled={!at} title={`A wav, mp3, flac, ogg or m4a from this computer, laid on ${TRACK_LABEL[track].toLowerCase()} from here (or drop one on the lane)`}
          onClick={run(() => at && pickSoundFile(track, at))}>
          <i className="pi pi-upload" /> Add a sound file here…
        </button>
      )}
    </div>
  );
}

/** Where a menu of `r`'s size goes for a click at (x, y): there, moved in from the window's
 * right and bottom edges (above the click when there's no room below). */
export function onScreen(x: number, y: number, r: { width: number; height: number }): { left: number; top: number } {
  const W = window.innerWidth || 1280;
  const H = window.innerHeight || 800;
  const top = y + r.height > H - 4 ? Math.max(4, y - r.height) : y;
  return { left: Math.max(4, Math.min(x, W - r.width - 4)), top };
}
