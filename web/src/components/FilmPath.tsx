// The guide: the steps of an episode after its files exist (docs/DESIGN.md, section 10). It keeps no
// record of its own: the step comes from the script, the pictures and the takes (lib/filmPath.ts),
// and each step's buttons are the ones the rest of the editor has.

import { useEffect, useMemo, useState, type MouseEvent } from "react";
import { generateMissing, loadRefs, openFilmPath, openSeriesForm, openSource, openStoryboard, playAll, requestRender } from "../actions";
import { api, host } from "../host";
import { agentInstructions, FILM_STEPS, filmStep, scriptShots, type FilmFacts, type FilmStep } from "../lib/filmPath";
import { statusKey, store, useApp } from "../store";
import { FloatingWindow } from "./FloatingWindow";

export function FilmPathWindow() {
  const open = useApp((s) => s.filmPath);
  const ep = useApp((s) => s.ep);
  return open && ep ? <FilmPath key={ep} ep={ep} /> : null;
}

function FilmPath({ ep }: { ep: string }) {
  const status = useApp((s) => s.status[statusKey(ep, s.pass)]);
  const refs = useApp((s) => s.refs[ep]);
  const [script, setScript] = useState<string | null>(null);
  const [chosen, setChosen] = useState<FilmStep | null>(null);
  const [showAsk, setShowAsk] = useState(false);

  useEffect(() => {
    if (!refs) void loadRefs(ep);
  }, [ep, refs]);
  // the status changes when the script or the takes do, from here or anywhere else
  useEffect(() => {
    let live = true;
    api().source(ep, "script").then((d) => live && setScript(d.text), () => live && setScript(""));
    return () => { live = false; };
  }, [ep, status]);

  const missing = useMemo(() => (refs ?? []).filter((r) => r.scope !== "shot" && r.kind !== "voice" && r.path && !r.exists), [refs]);
  const shots = useMemo(() => scriptShots(script ?? ""), [script]);
  const taken = new Set((status?.shots ?? []).filter((s) => s.cut.take != null).map((s) => s.shot));
  const onModel = shots.filter((s) => !s.hold);
  const toRender = onModel.filter((s) => !taken.has(s.id)).map((s) => s.id);
  const facts: FilmFacts = {
    shots: shots.length,
    structure: /^\/\/\s*structure:/m.test(script ?? ""),
    missing: missing.length,
    held: shots.length - onModel.length,
    unrendered: toRender.length,
  };
  const now = filmStep(facts);
  const step = chosen ?? now;

  // the page over plain http on a network has no clipboard: the text is shown to copy by hand
  const copyAsk = async () => {
    try {
      await navigator.clipboard.writeText(agentInstructions(ep));
      host().toast("success", "Copied", "Paste it into your agent.");
    } catch {
      setShowAsk(true);
    }
  };

  const openExport = (e: MouseEvent<HTMLButtonElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    store.set({ exportMenu: { x: r.left, y: r.bottom + 2 } });
  };

  const head = (
    <>
      <i className="pi pi-compass" />
      <b>Guide</b>
      <span className="h3-grow" />
      <button className="h3-btn h3-icon" title="Close: it picks up from the episode when you come back" onClick={() => openFilmPath(false)}><i className="pi pi-times" /></button>
    </>
  );
  return (
    <FloatingWindow storageKey="seriesmith.guide.rect" head={head} minW={420} minH={300}
      defaultRect={() => ({ x: Math.max(16, window.innerWidth - 620), y: 64, w: 580, h: 420 })}>
      <div id="sm-guide" className="h3-col" style={{ height: "100%", minHeight: 0 }}>
        <div className="h3-row h3-wrap" style={{ padding: "6px 10px", gap: 6, borderBottom: "1px solid var(--h3-border)" }}>
          {FILM_STEPS.map((label, i) => (
            <button key={label} className={`h3-btn${i === step ? " h3-on" : ""}`} disabled={i === 0}
              title={i === 0 ? "Series settings has the look and the rest" : undefined}
              onClick={() => setChosen(i === now ? null : (i as FilmStep))}>
              {i < now && <i className="pi pi-check" />} {label}
            </button>
          ))}
        </div>
        <div className="h3-col" style={{ padding: 12, gap: 10, overflow: "auto", flex: 1, minHeight: 0 }}>
          {script === null && <span className="h3-muted">Reading the script…</span>}
          {script !== null && step === 1 && (
            <>
              {shots.length || facts.structure
                ? <span>The story is in: {shots.length} shots.</span>
                : (
                  <>
                    <span id="sm-guide-waiting">Waiting for the script. This moves on by itself when it's saved.</span>
                    <span className="h3-small h3-muted">
                      Write it with the script-writing skill in the agent you already use, connected with <code>seriesmith mcp</code>.
                      These instructions tell it where the episode is, and to add the cast and places to the series config too:
                    </span>
                    <div className="h3-row h3-wrap">
                      <button id="sm-guide-copy-ask" className="h3-btn h3-primary" onClick={() => void copyAsk()}><i className="pi pi-copy" /> Copy instructions for your agent</button>
                    </div>
                    {showAsk && <textarea id="sm-guide-ask" className="h3-in h3-mono h3-small" rows={9} readOnly value={agentInstructions(ep)} />}
                    <code className="h3-small h3-mono" style={{ userSelect: "all", wordBreak: "break-all" }}>{ep}</code>
                  </>
                )}
              <div className="h3-row h3-wrap">
                <button className="h3-btn" onClick={() => openSource("script")}><i className="pi pi-file-edit" /> Open the script</button>
              </div>
            </>
          )}
          {script !== null && step === 2 && (
            <>
              <span>{missing.length ? `${missing.length} ${missing.length === 1 ? "picture" : "pictures"} to make, so people and places stay the same from shot to shot.` : "Every person and place has a picture."}</span>
              {missing.length > 0 && <ul className="h3-small" style={{ margin: 0, paddingLeft: 18 }}>{missing.slice(0, 12).map((r) => <li key={r.id}>{r.name}</li>)}{missing.length > 12 && <li>and {missing.length - 12} more</li>}</ul>}
              <div className="h3-row h3-wrap">
                <button id="sm-guide-pictures" className="h3-btn h3-primary" disabled={!missing.length} onClick={() => void generateMissing(true, true)}><i className="pi pi-image" /> Make the pictures</button>
                <button className="h3-btn" onClick={() => openSeriesForm()}><i className="pi pi-cog" /> Cast and places</button>
              </div>
              <span className="h3-small h3-muted">To pick another candidate or use a picture you have, open the Refs tab.</span>
            </>
          )}
          {script !== null && step === 3 && (
            <>
              <span>{shots.length ? `${shots.length} shots, ${facts.held} with no model yet.` : "No shots yet."} Block it in, sketch or drop pictures to see it, then give the shots a model.</span>
              <div className="h3-row h3-wrap">
                <button id="sm-guide-board" className="h3-btn h3-primary" onClick={() => openStoryboard(true)}><i className="pi pi-th-large" /> Open the storyboard</button>
              </div>
            </>
          )}
          {script !== null && step === 4 && (
            <>
              <span>{toRender.length ? `${toRender.length} ${toRender.length === 1 ? "shot" : "shots"} to film.` : "Every shot on a model has a take."}{facts.held ? ` ${facts.held} still have no model and won't be filmed.` : ""}</span>
              <div className="h3-row h3-wrap">
                <button id="sm-guide-film" className="h3-btn h3-primary" disabled={!toRender.length} onClick={() => requestRender(toRender, false, `Film ${toRender.length} shots`)}><i className="pi pi-play" /> Film them</button>
              </div>
              <span className="h3-small h3-muted">Each take lands in the cut. On the Shots tab you can compare takes and re-do what's wrong.</span>
            </>
          )}
          {script !== null && step === 5 && (
            <>
              <span>{taken.size ? `${taken.size} shots in the cut.` : "Nothing in the cut yet."}</span>
              <div className="h3-row h3-wrap">
                <button id="sm-guide-play" className="h3-btn h3-primary" disabled={!taken.size} onClick={() => playAll()}><i className="pi pi-play" /> Play all</button>
                <button className="h3-btn" disabled={!taken.size} onClick={openExport}><i className="pi pi-download" /> Export…</button>
              </div>
            </>
          )}
        </div>
      </div>
    </FloatingWindow>
  );
}
