// The storyboard (docs/PLAN.md): the open episode's script against a story structure, an act to a
// row. A beat shows its target and its real shots; `+` adds a stand-in and Fill makes the rest. The
// script is what's saved: every edit here goes to disk the way the script editor's do.

import { useCallback, useEffect, useMemo, useState, type KeyboardEvent, type MouseEvent } from "react";
import { openShotForm, openStoryboard, refreshEpisode } from "../actions";
import { api } from "../host";
import { clipTake } from "../lib/playlist";
import {
  bandShare, bareBeats, clock, fillable, fillCount, meter, placeOf, positive, runWidth, seriesChoices, TILE_W,
  pushed, type BoardAct, type BoardBeat, type BoardRun, type BoardShot, type SeriesChoices, type StoryboardAnswer, type StoryboardEdit,
} from "../lib/storyboard";
import { statusKey, useApp } from "../store";
import { FloatingWindow } from "./FloatingWindow";
import { EpisodeSelect } from "./ShotsTab";

export function StoryboardWindow() {
  const open = useApp((s) => s.storyboardOpen);
  const ep = useApp((s) => s.ep);
  return open && ep ? <Storyboard key={ep} ep={ep} /> : null;
}

const BIG_FILL = 50;

function placeName(id: string): string {
  return id.replace(/_/g, " ");
}

interface Picked { block: number; place: string; who: string[] }

type Menu =
  | { x: number; y: number; kind: "shot"; shot: BoardShot; last: boolean; rendered: boolean }
  | { x: number; y: number; kind: "sequence"; run: BoardRun }
  | { x: number; y: number; kind: "beat"; beat: BoardBeat }
  | { x: number; y: number; kind: "act"; act: BoardAct };

/** Right-click on anything on the board. The name fields stand in for a prompt, which ComfyUI's
 * desktop app doesn't have. */
function BoardMenu({ menu, choices, busy, edit, close, rename }: {
  menu: Menu;
  choices: SeriesChoices | null;
  busy: boolean;
  edit: (e: StoryboardEdit) => void;
  close: () => void;
  rename: (beat: BoardBeat) => void;
}) {
  const [asking, setAsking] = useState<"beat" | "act" | "rename" | "place" | null>(null);
  const run = (e: StoryboardEdit) => () => { edit(e); close(); };
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
            <div className="h3-menu-head">{menu.shot.id}{menu.shot.held_empty ? " (stand-in)" : ""}</div>
            <button onClick={() => { openShotForm({ shot: menu.shot.id, after: null }); close(); }}><i className="pi pi-pencil" /> Edit shot…</button>
            <button disabled={busy} onClick={run({ op: "add_after", block: menu.shot.block })}><i className="pi pi-plus" /> Add a stand-in after</button>
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

function Run({ run, selected, pick, thumbs, onShotMenu, onRunMenu }: {
  onShotMenu: (e: MouseEvent, shot: BoardShot, last: boolean) => void;
  onRunMenu: (e: MouseEvent, run: BoardRun) => void;
  run: BoardRun;
  selected: boolean;
  pick: () => void;
  thumbs: Map<string, string>;
}) {
  const who = [...new Set(run.shots.flatMap((s) => s.who))];
  return (
    <div className="h3-sb-run" style={{ width: runWidth(run.shots.length) }}>
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
            <button key={s.id} className={`h3-sb-tile${s.held_empty ? " h3-sb-standin" : ""}`}
              style={thumb ? { backgroundImage: `url("${thumb}")` } : undefined}
              title={`${s.id}${s.held_empty ? " (stand-in)" : ""}: ${s.action}`} onClick={() => openShotForm({ shot: s.id, after: null })}
              onContextMenu={(e) => onShotMenu(e, s, s === run.shots[run.shots.length - 1])} />
          );
        })}
      </div>
    </div>
  );
}

function Beat({ beat, biggest, picked, pick, busy, edit, thumbs, onShotMenu, onRunMenu, onBeatMenu, renaming, setRenaming }: {
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
  return (
    <div className="h3-sb-beat">
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
          <Run key={`${run.sequence}${i}`} run={run} selected={picked === run.block} pick={() => pick(run)} thumbs={thumbs} onShotMenu={onShotMenu} onRunMenu={onRunMenu} />
        ))}
        {named && (
          <button className="h3-sb-add" disabled={busy} title="Add a stand-in shot at the end of this beat"
            onClick={() => edit({ op: "add", beat: named })}>+</button>
        )}
        {named && left > 0 && (
          <button className="h3-link h3-small" disabled={busy} title={`Make the ${left} stand-ins this beat is short of its target`}
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
          <span className="h3-row" style={{ gap: 4 }} title="Set on this sequence's stand-ins. A shot someone has worked on keeps its own.">Cast
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

function ActRow({ act, label, biggest, shut, toggle, picked, pick, busy, edit, fill, thumbs, onShotMenu, onRunMenu, onBeatMenu, onActMenu, renamingBeat, setRenamingBeat }: {
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
          onShotMenu={onShotMenu} onRunMenu={onRunMenu} onBeatMenu={onBeatMenu} renaming={renamingBeat !== null && renamingBeat === b.block}
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
  const [undo, setUndo] = useState<string[]>([]);
  const [redo, setRedo] = useState<string[]>([]);
  const [menu, setMenu] = useState<Menu | null>(null);
  const [renamingBeat, setRenamingBeat] = useState<number | null>(null);
  const openAt = (e: MouseEvent, next: Omit<Extract<Menu, { kind: "shot" }>, "x" | "y"> | Omit<Extract<Menu, { kind: "sequence" }>, "x" | "y"> | Omit<Extract<Menu, { kind: "beat" }>, "x" | "y"> | Omit<Extract<Menu, { kind: "act" }>, "x" | "y">) => {
    e.preventDefault();
    setMenu({ ...next, x: Math.min(e.clientX, window.innerWidth - 240), y: Math.min(e.clientY, window.innerHeight - 280) } as Menu);
  };

  useEffect(() => {
    let live = true;
    api().structures().then((r) => live && setNames(r.structures.map((s) => s.name)))
      .catch((e) => live && setErr((e as Error).message));
    api().source(ep, "series").then((d) => live && setChoices(seriesChoices(d.text)))
      .catch((e) => live && setErr(`The series config: ${(e as Error).message}`));
    return () => { live = false; };
  }, [ep]);

  const length = positive(minutes);
  const each = positive(shot);
  // a script that names its structure goes by it, whether or not there's a table for it
  const scriptStructure = data?.plan.structure ?? null;
  const pass = useApp((s) => s.pass);
  const status = useApp((s) => s.status[statusKey(ep, s.pass)]);
  const other = useApp((s) => s.status[statusKey(ep, s.pass === "proxy" ? "final" : "proxy")]);
  const thumbs = useMemo(() => {
    const out = new Map<string, string>();
    for (const s of status?.shots ?? []) {
      const path = clipTake(s, s.cut.placeholder ? other : undefined)?.thumb;
      if (path) out.set(s.shot, api().thumbUrl(ep, path, TILE_W * 2));
    }
    return out;
  }, [ep, pass, status, other]);
  const chosen = scriptStructure ?? (structure || (names.find((n) => n.includes("Three-Act")) ?? names[0] ?? ""));

  // what the script already says wins, once, as the board opens
  useEffect(() => {
    if (seeded || !data) return;
    setSeeded(true);
    if (data.plan.structure && !data.plan.structure_known) setOwnFormat(data.plan.structure);
    if (data.plan.duration) setMinutes(String(Math.round((data.plan.duration / 60) * 100) / 100));
  }, [data, seeded]);

  const ask = useCallback(() => {
    if (!chosen || length === null || each === null) return undefined;
    let live = true;
    const wait = setTimeout(() => {
      api().storyboard(ep, chosen, length * 60, each).then((r) => {
        if (!live) return;
        setData(r);
        setErr(null);
      }).catch((e) => live && setErr((e as Error).message));
    }, 150);
    return () => { live = false; clearTimeout(wait); };
  }, [ep, chosen, length, each]);
  useEffect(() => ask(), [ask]);

  async function edit(e: StoryboardEdit) {
    if (!data || !chosen || length === null || each === null) return;
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
    } catch (x) {
      setErr((x as Error).message);
    } finally {
      setBusy(false);
    }
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

  function keys(e: KeyboardEvent) {
    if (!(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== "z") return;
    if ((e.target as HTMLElement).closest("input, select, textarea")) return;
    e.preventDefault();
    e.stopPropagation();
    if (e.shiftKey) redoEdit(); else undoEdit();
  }

  function fill(beats: BoardBeat[]) {
    const n = fillCount(beats);
    if (n >= BIG_FILL && !window.confirm(`Add ${n} stand-in shots to the script?`)) return;
    void edit({ op: "fill", beats: fillable(beats) });
  }

  const plan = data?.plan;
  const allBeats = plan?.acts.flatMap((a) => a.beats) ?? [];
  const biggest = Math.max(0, ...allBeats.map((b) => b.target_shots ?? 0));
  const left = fillCount(allBeats);
  const bare = bareBeats(allBeats);

  const head = (
    <>
      <i className="pi pi-th-large" />
      <b className="h3-grow">Storyboard{plan?.title ? `: ${plan.title}` : ""}</b>
      <button className="h3-btn h3-icon" title="Close" onClick={() => openStoryboard(false)}><i className="pi pi-times" /></button>
    </>
  );
  return (
    <FloatingWindow storageKey="seriesmith.storyboard.rect" head={head} minW={520} minH={320}
      defaultRect={() => ({ x: 40, y: 48, w: Math.min(1280, window.innerWidth - 80), h: Math.min(820, window.innerHeight - 96) })}>
      <div className="h3-col h3-sb" style={{ height: "100%", outline: "none" }} tabIndex={-1} onKeyDown={keys}>
        <div className="h3-row h3-sb-controls">
          <EpisodeSelect compact />
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
          <label className="h3-row" title="The length it's aiming at. It sets every beat's target, and only that.">Minutes
            <input className="h3-sb-num" type="number" min="0.1" step="any" value={minutes}
              onChange={(e) => setMinutes(e.target.value)} />
          </label>
          <label className="h3-row" title="A typical shot, in seconds: what a stand-in is made at.">Shot length
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
          <button className="h3-btn h3-icon" disabled={busy || !undo.length} title="Undo (Ctrl+Z)" onClick={undoEdit}><i className="pi pi-undo" /></button>
          <button className="h3-btn h3-icon" disabled={busy || !redo.length} title="Redo (Ctrl+Shift+Z)" onClick={redoEdit}><i className="pi pi-refresh" /></button>
          {bare.length > 0 && (
            <button className="h3-btn" disabled={busy} title="One held shot on every beat that has none: the episode blocked in, from start to end"
              onClick={() => void edit({ op: "fill", beats: bare, each: 1 })}>One per beat ({bare.length})</button>
          )}
          {left > 0 && <button className="h3-btn" disabled={busy} title="Make every beat's missing stand-ins" onClick={() => fill(allBeats)}>Fill all ({left})</button>}
        </div>
        {picked && (
          <EditBar choices={choices} picked={picked} busy={busy} edit={(e) => void edit(e)} close={() => setPicked(null)} />
        )}
        {(length === null || each === null) && (
          <span className="h3-small h3-err" style={{ padding: "0 10px" }}>The minutes and the shot length need to be above zero.</span>
        )}
        {err && <span className="h3-small h3-err" style={{ padding: "0 10px" }}>{err}</span>}
        {plan && plan.warnings.length > 0 && (
          <details className="h3-small h3-sb-warnings">
            <summary>{plan.warnings.length} {plan.warnings.length === 1 ? "warning" : "warnings"} at this length</summary>
            <ul>{plan.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
          </details>
        )}
        {menu && (
          <BoardMenu menu={menu} choices={choices} busy={busy} edit={(e) => void edit(e)} close={() => setMenu(null)}
            rename={(b) => setRenamingBeat(b.block)} />
        )}
        <div className="h3-sb-board">
          {plan?.acts.map((act, i) => {
            const key = `${act.act}${i}`;
            return (
              <ActRow key={key} act={act} label={act.act || plan.structure || "Episode"} biggest={biggest} shut={!!closed[key]} busy={busy} thumbs={thumbs}
                toggle={() => setClosed((c) => ({ ...c, [key]: !c[key] }))}
                picked={picked?.block ?? null}
                pick={(run) => run.block !== null && setPicked({
                  block: run.block, place: run.place, who: [...new Set(run.shots.flatMap((s) => s.who))] })}
                onShotMenu={(e, s, last) => openAt(e, { kind: "shot", shot: s, last, rendered: thumbs.has(s.id) })}
                onRunMenu={(e, r) => openAt(e, { kind: "sequence", run: r })}
                onBeatMenu={(e, b) => openAt(e, { kind: "beat", beat: b })}
                onActMenu={(e, a) => openAt(e, { kind: "act", act: a })}
                renamingBeat={renamingBeat} setRenamingBeat={setRenamingBeat}
                edit={(e) => void edit(e)} fill={fill} />
            );
          })}
        </div>
      </div>
    </FloatingWindow>
  );
}
