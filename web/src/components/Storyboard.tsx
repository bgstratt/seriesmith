// The storyboard (docs/PLAN.md): a story structure and a duration as the episode's shots, an act
// to a row, each beat a band over the shots it comes to (GET /seriesmith/storyboard/block). This is
// the preview: nothing here writes a script yet.

import { useEffect, useState } from "react";
import { openStoryboard } from "../actions";
import { api } from "../host";
import { beatWidth, clock, placeOf, positive, type BlockBeat, type StoryboardBlock } from "../lib/storyboard";
import { useApp } from "../store";
import { FloatingWindow } from "./FloatingWindow";

export function StoryboardWindow() {
  const open = useApp((s) => s.storyboardOpen);
  return open ? <Storyboard /> : null;
}

function Beat({ beat, length }: { beat: BlockBeat; length: number }) {
  const place = placeOf(beat);
  return (
    <div className={`h3-sb-beat${beat.point !== undefined ? " h3-sb-point" : ""}${beat.thin ? " h3-sb-thin" : ""}`}
      style={{ width: beatWidth(beat.shots) }}>
      <div className="h3-sb-band" title={`${beat.beat}${place ? ` (${place})` : ""}: ${beat.guidance}`}>
        <span className="h3-sb-name">{beat.beat}</span>
        <span className="h3-sb-count">{beat.shots}</span>
      </div>
      <div className="h3-sb-tiles">
        {Array.from({ length: beat.shots }, (_, i) => (
          <div key={i} className="h3-sb-tile"
            title={`Shot ${beat.first_shot + i + 1}, about ${length.toFixed(1)} s`} />
        ))}
      </div>
    </div>
  );
}

function Storyboard() {
  const [names, setNames] = useState<string[]>([]);
  const [structure, setStructure] = useState("");
  const [minutes, setMinutes] = useState("7");
  const [shot, setShot] = useState("3.5");
  const [block, setBlock] = useState<StoryboardBlock | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [closed, setClosed] = useState<Record<string, boolean>>({});

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
            <select value={structure} onChange={(e) => setStructure(e.target.value)}>
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
                    {act.beats.map((b) => <Beat key={b.first_shot} beat={b} length={block.shot_seconds} />)}
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
