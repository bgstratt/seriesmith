// The storyboard (docs/PLAN.md): the open episode's script against a story structure, an act to a
// row. A beat shows its target and its real shots; `+` adds a stand-in and Fill makes the rest. The
// script is what's saved: every edit here goes to disk the way the script editor's do.

import { useCallback, useEffect, useMemo, useState } from "react";
import { openShotForm, openStoryboard, refreshEpisode } from "../actions";
import { api } from "../host";
import { clipTake } from "../lib/playlist";
import {
  bandShare, bareBeats, clock, fillable, fillCount, meter, placeOf, positive, runWidth, seriesChoices, TILE_W,
  type BoardAct, type BoardBeat, type BoardRun, type SeriesChoices, type StoryboardAnswer, type StoryboardEdit,
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

interface Picked { block: number; id: string; place: string; who: string[]; rendered: number }

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

function Run({ run, selected, pick, thumbs }: {
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
        onClick={pick}>
        <span className="h3-sb-name">{placeName(run.place)}</span>
        {who.length > 0 && <span className="h3-sb-who">{who.join(", ")}</span>}
      </button>
      <div className="h3-sb-tiles">
        {run.shots.map((s) => {
          const thumb = thumbs.get(s.id);
          return (
            <button key={s.id} className={`h3-sb-tile${s.held_empty ? " h3-sb-standin" : ""}`}
              style={thumb ? { backgroundImage: `url("${thumb}")` } : undefined}
              title={`${s.id}${s.held_empty ? " (stand-in)" : ""}: ${s.action}`} onClick={() => openShotForm({ shot: s.id, after: null })} />
          );
        })}
      </div>
    </div>
  );
}

function Beat({ beat, biggest, picked, pick, busy, edit, thumbs }: {
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
  const [renaming, setRenaming] = useState(false);
  const block = beat.block;
  return (
    <div className="h3-sb-beat">
      <div className={`h3-sb-band${point ? " h3-sb-point" : ""}${beat.thin ? " h3-sb-thin" : ""}${beat.plain !== null && !beat.known ? " h3-sb-own" : ""}`}
        style={{ width: bandShare(beat.target_shots, biggest) }}
        title={`${beat.guidance ? `${name}${place ? ` (${place})` : ""}: ${beat.guidance}` : name}${block !== null ? "\nDouble-click its name to rename it." : ""}`}>
        {renaming && block !== null
          ? <NameField className="h3-sb-rename" value={name} busy={busy} cancel={() => setRenaming(false)}
              commit={(text) => { setRenaming(false); edit({ op: "rename_beat", block, name: text }); }} />
          : <span className="h3-sb-name" onDoubleClick={() => block !== null && setRenaming(true)}>{name}</span>}
        <span className="h3-sb-count">{meter(beat)}</span>
      </div>
      {beat.guidance && <div className="h3-small h3-muted h3-sb-guide">{beat.guidance}</div>}
      <div className="h3-sb-runs">
        {beat.runs.map((run, i) => (
          <Run key={`${run.sequence}${i}`} run={run} selected={picked === run.block} pick={() => pick(run)} thumbs={thumbs} />
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
      <label className="h3-row" title="The sequence's id in the script">Sequence
        <NameField value={picked.id} busy={busy} size={8} commit={(name) => {
          if (picked.rendered && !window.confirm(
            `${picked.rendered} of this sequence's shots have takes. A shot's seed is built from its sequence's id, so new takes won't match a re-render of the old ones. Rename it to ${name}?`)) return;
          edit({ op: "rename_sequence", block: picked.block, name });
        }} />
      </label>
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

function ActRow({ act, label, biggest, shut, toggle, picked, pick, busy, edit, fill, thumbs }: {
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
      <div className="h3-sb-acthead">
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
        <Beat key={`${b.plain}${b.nth}${i}`} beat={b} biggest={biggest} picked={picked} pick={pick} busy={busy} edit={edit} thumbs={thumbs} />
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
      const r = await api().storyboardEdit({ ep, base_hash: data.hash, structure: chosen, duration: length * 60, shot: each, ...e });
      setData(r);
      setErr(null);
      if (e.op === "place") setPicked((p) => (p ? { ...p, place: e.place } : p));
      if (e.op === "cast") setPicked((p) => (p ? { ...p, who: e.who } : p));
      if (e.op === "rename_sequence") setPicked((p) => (p ? { ...p, id: e.name } : p));
      void refreshEpisode(ep);
    } catch (x) {
      setErr((x as Error).message);
    } finally {
      setBusy(false);
    }
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
      <div className="h3-col h3-sb" style={{ height: "100%" }}>
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
        <div className="h3-sb-board">
          {plan?.acts.map((act, i) => {
            const key = `${act.act}${i}`;
            return (
              <ActRow key={key} act={act} label={act.act || plan.structure || "Episode"} biggest={biggest} shut={!!closed[key]} busy={busy} thumbs={thumbs}
                toggle={() => setClosed((c) => ({ ...c, [key]: !c[key] }))}
                picked={picked?.block ?? null}
                pick={(run) => run.block !== null && setPicked({
                  block: run.block, id: run.sequence, place: run.place, who: [...new Set(run.shots.flatMap((s) => s.who))],
                  rendered: run.shots.filter((s) => thumbs.has(s.id)).length })}
                edit={(e) => void edit(e)} fill={fill} />
            );
          })}
        </div>
      </div>
    </FloatingWindow>
  );
}
