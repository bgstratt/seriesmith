// The storyboard (docs/PLAN.md): a story structure and a duration as the episode's shots, an act
// to a row, each beat a band over the shots it comes to (GET /seriesmith/storyboard/block), and a
// thin box at the front of each sequence holding its place and cast. Nothing here writes a script
// yet.

import { useEffect, useState } from "react";
import { openStoryboard } from "../actions";
import { api } from "../host";
import {
  beatWidth, boxShots, clock, freshBoxes, placeOf, positive, removeBox, seriesChoices, splitBox,
  type BlockBeat, type SeqBox, type SeriesChoices, type StoryboardBlock,
} from "../lib/storyboard";
import { useApp } from "../store";
import { FloatingWindow } from "./FloatingWindow";

export function StoryboardWindow() {
  const open = useApp((s) => s.storyboardOpen);
  return open ? <Storyboard /> : null;
}

interface Picked { beat: string; box: number }

function placeName(id: string): string {
  return id.replace(/_/g, " ");
}

function Beat({ beat, length, boxes, picked, pick }: {
  beat: BlockBeat;
  length: number;
  boxes: SeqBox[];
  picked: number | null;
  pick: (box: number) => void;
}) {
  const place = placeOf(beat);
  const counts = boxShots(boxes, beat.shots);
  let shot = beat.first_shot;
  return (
    <div className={`h3-sb-beat${beat.point !== undefined ? " h3-sb-point" : ""}${beat.thin ? " h3-sb-thin" : ""}`}
      style={{ width: beatWidth(beat.shots, boxes.length) }}>
      <div className="h3-sb-band" title={`${beat.beat}${place ? ` (${place})` : ""}: ${beat.guidance}`}>
        <span className="h3-sb-name">{beat.beat}</span>
        <span className="h3-sb-count">{beat.shots}</span>
      </div>
      <div className="h3-sb-tiles">
        {boxes.map((box, b) => (
          <BoxAndTiles key={b} box={box} shots={counts[b]} first={(shot += b ? counts[b - 1] : 0)} length={length}
            selected={picked === b} onPick={() => pick(b)} />
        ))}
      </div>
    </div>
  );
}

function BoxAndTiles({ box, shots, first, length, selected, onPick }: {
  box: SeqBox;
  shots: number;
  first: number;
  length: number;
  selected: boolean;
  onPick: () => void;
}) {
  const label = box.place ? placeName(box.place) : "place…";
  const who = box.cast.length ? box.cast.join(", ") : "no cast yet";
  return (
    <>
      <button className={`h3-sb-box${box.place ? "" : " h3-sb-unset"}${selected ? " h3-sb-sel" : ""}`}
        title={`Sequence: ${box.place ? placeName(box.place) : "no place yet"}; ${who}. ${shots} shots. Click to set.`}
        onClick={onPick}>{label}</button>
      {Array.from({ length: shots }, (_, i) => (
        <div key={i} className="h3-sb-tile" title={`Shot ${first + i + 1}, about ${length.toFixed(1)} s`} />
      ))}
    </>
  );
}

function EditBar({ choices, boxes, index, beatShots, change, split, remove, close }: {
  choices: SeriesChoices | null;
  boxes: SeqBox[];
  index: number;
  beatShots: number;
  change: (next: Partial<SeqBox>) => void;
  split: () => void;
  remove: () => void;
  close: () => void;
}) {
  const box = boxes[index];
  return (
    <div className="h3-row h3-sb-editbar h3-small">
      {!choices && <span className="h3-muted">Open an episode to choose from its places and cast.</span>}
      {choices && (
        <>
          <label className="h3-row">Place
            <select value={box.place} onChange={(e) => change({ place: e.target.value })}>
              <option value="">Choose…</option>
              {choices.places.map((id) => <option key={id} value={id}>{placeName(id)}</option>)}
            </select>
          </label>
          <span className="h3-row" style={{ gap: 4 }}>Cast
            {choices.cast.map((c) => {
              const on = box.cast.includes(c.id);
              return (
                <button key={c.id} className={`h3-btn${on ? " h3-on" : ""}`}
                  onClick={() => change({ cast: on ? box.cast.filter((x) => x !== c.id) : [...box.cast, c.id] })}>
                  {c.name}
                </button>
              );
            })}
            {!choices.cast.length && <span className="h3-muted">none in this series</span>}
          </span>
        </>
      )}
      <span className="h3-grow" />
      <button className="h3-btn" disabled={beatShots <= boxes.length}
        title={beatShots <= boxes.length ? "This beat has no shot left for another sequence" : "Another sequence in this beat, somewhere else"}
        onClick={split}>Split</button>
      <button className="h3-btn" disabled={boxes.length < 2} title="Give this sequence's shots to the one beside it" onClick={remove}>Merge</button>
      <button className="h3-btn h3-icon" title="Done" onClick={close}><i className="pi pi-check" /></button>
    </div>
  );
}

function Storyboard() {
  const ep = useApp((s) => s.ep);
  const [names, setNames] = useState<string[]>([]);
  const [structure, setStructure] = useState("");
  const [minutes, setMinutes] = useState("7");
  const [shot, setShot] = useState("3.5");
  const [block, setBlock] = useState<StoryboardBlock | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [closed, setClosed] = useState<Record<string, boolean>>({});
  const [plan, setPlan] = useState<Record<string, SeqBox[]>>({});
  const [picked, setPicked] = useState<Picked | null>(null);
  const [choices, setChoices] = useState<SeriesChoices | null>(null);

  useEffect(() => {
    let live = true;
    api().structures().then((r) => {
      if (!live) return;
      const all = r.structures.map((s) => s.name);
      setNames(all);
      setStructure((now) => now || (all.find((n) => n.includes("Three-Act")) ?? all[0] ?? ""));
    }).catch((e) => live && setErr((e as Error).message));
    return () => { live = false; };
  }, []);

  useEffect(() => {
    setChoices(null);
    if (!ep) return undefined;
    let live = true;
    api().source(ep, "series").then((d) => {
      if (live) setChoices(seriesChoices(d.text));
    }).catch((e) => live && setErr(`The series config: ${(e as Error).message}`));
    return () => { live = false; };
  }, [ep]);

  const length = positive(minutes);
  const each = positive(shot);
  // the board follows the fields, a moment after the typing stops
  useEffect(() => {
    if (!structure || length === null || each === null) return undefined;
    let live = true;
    const wait = setTimeout(() => {
      api().storyboardBlock(structure, length * 60, each).then((r) => {
        if (!live) return;
        setBlock(r);
        setErr(null);
      }).catch((e) => live && setErr((e as Error).message));
    }, 150);
    return () => { live = false; clearTimeout(wait); };
  }, [structure, length, each]);

  const boxesOf = (beat: string) => plan[beat] ?? freshBoxes();
  const setBoxes = (beat: string, boxes: SeqBox[]) => setPlan((p) => ({ ...p, [beat]: boxes }));
  const shotsOf = (beat: string) => block?.acts.flatMap((a) => a.beats).find((b) => b.beat === beat)?.shots ?? 0;
  const shown = picked && picked.box < boxesOf(picked.beat).length ? picked : null;

  const head = (
    <>
      <i className="pi pi-th-large" />
      <b className="h3-grow">Storyboard</b>
      <button className="h3-btn h3-icon" title="Close" onClick={() => openStoryboard(false)}><i className="pi pi-times" /></button>
    </>
  );
  return (
    <FloatingWindow storageKey="seriesmith.storyboard.rect" head={head} minW={520} minH={320}
      defaultRect={() => ({ x: 40, y: 48, w: Math.min(1280, window.innerWidth - 80), h: Math.min(820, window.innerHeight - 96) })}>
      <div className="h3-col h3-sb" style={{ height: "100%" }}>
        <div className="h3-row h3-sb-controls">
          <label className="h3-row">Structure
            <select value={structure} onChange={(e) => { setStructure(e.target.value); setPlan({}); setPicked(null); }}>
              {names.map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
          <label className="h3-row" title="The whole episode. It sets how many shots every beat comes to.">Minutes
            <input className="h3-sb-num" type="number" min="0.1" step="any" value={minutes}
              onChange={(e) => setMinutes(e.target.value)} />
          </label>
          <label className="h3-row" title="A typical shot, in seconds.">Shot length
            <input className="h3-sb-num" type="number" min="0.1" step="0.1" value={shot}
              onChange={(e) => setShot(e.target.value)} />
          </label>
          {block && (
            <span className="h3-small h3-muted">
              {block.shots} shots, {block.shot_seconds.toFixed(2)} s each, {clock(block.duration)}
            </span>
          )}
        </div>
        {shown && (
          <EditBar choices={choices} boxes={boxesOf(shown.beat)} index={shown.box} beatShots={shotsOf(shown.beat)}
            change={(next) => setBoxes(shown.beat, boxesOf(shown.beat).map((b, i) => (i === shown.box ? { ...b, ...next } : b)))}
            split={() => { setBoxes(shown.beat, splitBox(boxesOf(shown.beat), shown.box)); setPicked({ ...shown, box: shown.box + 1 }); }}
            remove={() => { setBoxes(shown.beat, removeBox(boxesOf(shown.beat), shown.box)); setPicked(null); }}
            close={() => setPicked(null)} />
        )}
        {(length === null || each === null) && (
          <span className="h3-small h3-err" style={{ padding: "0 10px" }}>The minutes and the shot length need to be above zero.</span>
        )}
        {err && <span className="h3-small h3-err" style={{ padding: "0 10px" }}>{err}</span>}
        {block && block.warnings.length > 0 && (
          <details className="h3-small h3-sb-warnings">
            <summary>{block.warnings.length} {block.warnings.length === 1 ? "warning" : "warnings"} at this length</summary>
            <ul>{block.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
          </details>
        )}
        <div className="h3-sb-board">
          {block?.acts.map((act) => {
            const shut = closed[act.act];
            return (
              <section key={act.act} className="h3-sb-act">
                <button className="h3-sb-acthead" onClick={() => setClosed((c) => ({ ...c, [act.act]: !c[act.act] }))}>
                  <i className={`pi ${shut ? "pi-chevron-right" : "pi-chevron-down"}`} />
                  <b>{act.act}</b>
                  <span className="h3-small h3-muted">{act.shots} shots, {clock(act.seconds)}</span>
                </button>
                {!shut && (
                  <div className="h3-sb-row">
                    {act.beats.map((b) => (
                      <Beat key={b.beat} beat={b} length={block.shot_seconds} boxes={boxesOf(b.beat)}
                        picked={shown?.beat === b.beat ? shown.box : null}
                        pick={(box) => setPicked({ beat: b.beat, box })} />
                    ))}
                  </div>
                )}
              </section>
            );
          })}
        </div>
      </div>
    </FloatingWindow>
  );
}
