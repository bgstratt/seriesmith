// The Refs tab's sound "+" (docs/EDITOR.md "Sound"): a new music cue over a span of the cut,
// effects for the shots picked, and a place's ambience bed (its words written to the series
// config first when they're new). One dialog, on the store's `soundAdd`; the Ambience lane's
// menu, the spotting map's and the scoring window's cue tabs open it too. What each shows is
// fetched when it opens: the shots' effects (GET /seriesmith/fx/shots), the beds (GET
// /seriesmith/ambience) and the series config (its places' words).

import { useEffect, useMemo, useState } from "react";
import { currentPlaylist } from "../actions";
import { newCue } from "../cueActions";
import { api } from "../host";
import { setPath, type Raw } from "../lib/seriesForm";
import { sequenceRows, type MapRow } from "../lib/spotting";
import { tn } from "../lib/format";
import { locate } from "../lib/playlist";
import { closeSoundAdd, currentMix, loadMix, makeBed, makeEffects } from "../mixActions";
import { statusKey, useApp, type SoundAddAsk } from "../store";
import type { AmbienceBed, CueKind, FxShotSummary } from "../types";
import { Dialog } from "./Dialogs";
import { useTargets } from "./Targets";
import { useSeriesConfig } from "./useSeriesConfig";

export function SoundAddDialog() {
  const ask = useApp((s) => s.soundAdd);
  const ep = useApp((s) => s.ep);
  if (!ask || !ep) return null;
  return <SoundAddBody key={JSON.stringify(ask)} ep={ep} ask={ask} />;
}

function SoundAddBody({ ep, ask }: { ep: string; ask: SoundAddAsk }) {
  if (ask.kind === "cue") return <CueAdd ask={ask} ep={ep} />;
  if (ask.kind === "fx") return <FxAdd ask={ask} ep={ep} />;
  return <BedAdd ask={ask} ep={ep} />;
}

/** The cut in rows (a run of one sequence's clips each), as the spotting map shows it. */
function useRows(ep: string): MapRow[] {
  const items = useApp((s) => currentPlaylist(s));
  const st = useApp((s) => s.status[statusKey(ep, s.pass)]);
  return useMemo(() => {
    const m = new Map((st?.shots ?? []).map((x) => [x.shot, x.sequence]));
    return sequenceRows(items, (shot) => m.get(shot) ?? null);
  }, [items, st]);
}

const seqName = (r: MapRow) => r.seq ?? "no sequence";

// ---------------------------------------------------------------------------
// music: a new cue
// ---------------------------------------------------------------------------

function CueAdd({ ep, ask }: { ep: string; ask: Extract<SoundAddAsk, { kind: "cue" }> }) {
  const rows = useRows(ep);
  const order = useMemo(() => rows.flatMap((r) => r.shots.map((s) => s.shot)), [rows]);
  const multi = useApp((s) => s.multi);
  const pos = useApp((s) => s.cutPlay.pos);
  const items = useApp((s) => currentPlaylist(s));
  // where it starts: the shots asked, else the selection, else the sequence under the playhead
  const initial = useMemo((): [string, string] => {
    const asked = (ask.shots?.length ? ask.shots : multi.length > 1 ? multi : []).filter((x) => order.includes(x));
    if (asked.length) {
      const idx = asked.map((x) => order.indexOf(x)).sort((a, b) => a - b);
      return [order[idx[0]], order[idx[idx.length - 1]]];
    }
    const at = items[locate(items, pos).index]?.shot;
    const row = rows.find((r) => r.shots.some((s) => s.shot === at)) ?? rows[0];
    return row ? [row.shots[0].shot, row.shots[row.shots.length - 1].shot] : ["", ""];
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const [from, setFrom] = useState(initial[0]);
  const [to, setTo] = useState(initial[1]);
  const [kind, setKind] = useState<CueKind>("score");
  const a = order.indexOf(from);
  const b = order.indexOf(to);
  const span = a >= 0 && b >= a ? order.slice(a, b + 1) : [];
  const make = () => {
    closeSoundAdd();
    void newCue(null, { shots: span, kind, ...(ask.tab ? { tab: ask.tab } : {}) });
  };
  const options = (min: number) => rows.map((r, i) => (
    <optgroup key={`${r.seq}|${i}`} label={seqName(r)}>
      {r.shots.map((s) => <option key={s.shot} value={s.shot} disabled={order.indexOf(s.shot) < min}>{s.shot}</option>)}
    </optgroup>
  ));
  return (
    <Dialog title="New cue" sub="A music cue over a span of the cut: its sections, arc and takes in the cue window, written to the hits in its span"
      onClose={closeSoundAdd}
      footer={
        <>
          <button className="h3-btn" onClick={closeSoundAdd}>Cancel</button>
          <button className="h3-btn h3-primary" disabled={!span.length} data-act="make-cue" onClick={make}>
            Make the cue{span.length ? ` (${span.length} shot${span.length === 1 ? "" : "s"})` : ""}
          </button>
        </>
      }>
      <div className="h3-col" style={{ gap: 8 }}>
        {!order.length && <div className="h3-note">The cut is empty: a cue goes over the cut's shots.</div>}
        {rows.length > 0 && (
          <div className="h3-row h3-wrap h3-small" style={{ gap: 4 }}>
            <span className="h3-muted">Over a sequence:</span>
            {rows.map((r, i) => {
              const on = from === r.shots[0].shot && to === r.shots[r.shots.length - 1].shot;
              return (
                <button key={`${r.seq}|${i}`} className={`h3-btn${on ? " h3-on" : ""}`} data-seq={r.seq ?? ""}
                  title={`${seqName(r)}: ${r.shots[0].shot} to ${r.shots[r.shots.length - 1].shot}`}
                  onClick={() => {
                    setFrom(r.shots[0].shot);
                    setTo(r.shots[r.shots.length - 1].shot);
                  }}>{seqName(r)}</button>
              );
            })}
          </div>
        )}
        <div className="h3-row h3-wrap h3-small" style={{ gap: 6 }}>
          <label className="h3-row" style={{ gap: 4 }} title="The shot it starts on (its first frame played)">
            From
            <select className="h3-in" style={{ width: "auto" }} value={from} data-field="from"
              onChange={(e) => {
                setFrom(e.target.value);
                if (order.indexOf(e.target.value) > order.indexOf(to)) setTo(e.target.value);
              }}>{options(0)}</select>
          </label>
          <label className="h3-row" style={{ gap: 4 }} title="The shot it ends on (its last frame played)">
            to
            <select className="h3-in" style={{ width: "auto" }} value={to} data-field="to" onChange={(e) => setTo(e.target.value)}>{options(a)}</select>
          </label>
          <span className="h3-seg" title="Score: underscore, instrumental. Song: sung, its sections' lyrics">
            <button className={kind === "score" ? "h3-on" : ""} data-kind="score" onClick={() => setKind("score")}>Score</button>
            <button className={kind === "song" ? "h3-on" : ""} data-kind="song" onClick={() => setKind("song")}>Song</button>
          </span>
        </div>
        <div className="h3-muted h3-small">
          It opens in {ask.tab ? "the scoring window" : "the cue window"} to shape: its style, tempo, sections and arc, then render its takes. Its span can be dragged there later.
        </div>
      </div>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// effects: shots to make them for
// ---------------------------------------------------------------------------

const hasFx = (x: FxShotSummary | undefined) => !!x && (x.ok > 0 || x.queued > 0);

function FxAdd({ ep, ask }: { ep: string; ask: Extract<SoundAddAsk, { kind: "fx" }> }) {
  const pass = useApp((s) => s.pass);
  const rows = useRows(ep);
  const order = useMemo(() => rows.flatMap((r) => r.shots.map((s) => s.shot)), [rows]);
  const { list } = useTargets();
  const models = (list?.targets ?? []).filter((t) => t.kind === "foley");
  const def = list?.default?.foley ?? null;
  const [model, setModel] = useState("");
  const [have, setHave] = useState<Map<string, FxShotSummary> | null>(null);
  const [on, setOn] = useState<Set<string> | null>(ask.shots ? new Set(ask.shots) : null);
  // the shots' effects, fetched when it opens; unasked, it starts on the shots without
  useEffect(() => {
    let live = true;
    const fn = api().fxShots;
    const done = (m: Map<string, FxShotSummary>) => {
      if (!live) return;
      setHave(m);
      setOn((was) => was ?? new Set(order.filter((x) => !hasFx(m.get(x)))));
    };
    if (!fn) done(new Map());
    else fn(ep, pass).then((r) => done(new Map(r.shots.map((x) => [x.shot, x])))).catch(() => done(new Map()));
    return () => {
      live = false;
    };
  }, [ep, pass]); // eslint-disable-line react-hooks/exhaustive-deps
  const picked = order.filter((x) => on?.has(x));
  const toggle = (shots: string[], v: boolean) => setOn((was) => {
    const next = new Set(was ?? []);
    for (const x of shots) {
      if (v) next.add(x);
      else next.delete(x);
    }
    return next;
  });
  const make = () => {
    closeSoundAdd();
    void makeEffects(picked, model || null);
  };
  return (
    <Dialog title="Make effects" sub={`Sync sound made from the frames of the take each shot plays in the ${pass} cut`}
      onClose={closeSoundAdd}
      footer={
        <>
          <button className="h3-btn" onClick={closeSoundAdd}>Cancel</button>
          <button className="h3-btn h3-primary" disabled={!picked.length} data-act="make-fx" onClick={make}>
            Make effects{picked.length ? ` for ${picked.length} shot${picked.length === 1 ? "" : "s"}` : ""}
          </button>
        </>
      }>
      <div className="h3-col" style={{ gap: 8 }}>
        {models.length > 0 && (
          <label className="h3-row h3-small" style={{ gap: 6 }} title="The foley model they're made on">
            Model
            <select className="h3-in" style={{ width: "auto" }} value={model} data-field="model" onChange={(e) => setModel(e.target.value)}>
              <option value="">{def ? `${models.find((m) => m.id === def)?.short ?? def} (default)` : "default model"}</option>
              {models.filter((m) => m.id !== def).map((m) => <option key={m.id} value={m.id}>{m.short ?? m.label}</option>)}
            </select>
          </label>
        )}
        {!have && <div className="h3-muted h3-small"><i className="pi pi-spin pi-spinner" /> Loading which shots have effects…</div>}
        {!order.length && <div className="h3-note">The cut is empty.</div>}
        {have && (
          <div className="h3-col" style={{ gap: 6, maxHeight: 360, overflow: "auto" }}>
            {rows.map((r, i) => {
              const ids = r.shots.map((s) => s.shot);
              const all = ids.every((x) => on?.has(x));
              return (
                <div key={`${r.seq}|${i}`} className="h3-col" style={{ gap: 2 }}>
                  <label className="h3-row h3-small" style={{ gap: 6 }} title={`Every shot of ${seqName(r)}`}>
                    <input type="checkbox" data-seq={r.seq ?? ""} checked={all} onChange={(e) => toggle(ids, e.target.checked)} />
                    <b>{seqName(r)}</b>
                    <span className="h3-muted">{ids.filter((x) => hasFx(have.get(x))).length}/{ids.length} with effects</span>
                  </label>
                  <div className="h3-row h3-wrap h3-small" style={{ gap: "2px 12px", paddingLeft: 22 }}>
                    {ids.map((x) => {
                      const f = have.get(x);
                      return (
                        <label key={x} className="h3-row" style={{ gap: 4 }}>
                          <input type="checkbox" data-shot={x} checked={!!on?.has(x)} onChange={(e) => toggle([x], e.target.checked)} />
                          {x}
                          {hasFx(f) && (
                            <span className="h3-badge h3-b-voice" title={`${f!.ok} take${f!.ok === 1 ? "" : "s"}${f!.queued ? `, ${f!.queued} on the way` : ""}${f!.picked != null ? `; ${tn(f!.picked)} in the mix` : ", none picked"}`}>
                              {f!.picked != null ? tn(f!.picked) : `${f!.ok + f!.queued} take${f!.ok + f!.queued === 1 ? "" : "s"}`}
                            </span>
                          )}
                        </label>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        )}
        <div className="h3-muted h3-small">Shots that already have effects get a new take; the first take a shot gets is picked into the mix.</div>
      </div>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// ambience: a place's bed
// ---------------------------------------------------------------------------

interface PlaceRow {
  place: string;
  name: string;
  shots: string[];
}

function BedAdd({ ep, ask }: { ep: string; ask: Extract<SoundAddAsk, { kind: "bed" }> }) {
  const mix = useApp((s) => currentMix(s));
  const items = useApp((s) => currentPlaylist(s));
  const sc = useSeriesConfig(ep);
  const { list } = useTargets();
  const models = (list?.targets ?? []).filter((t) => t.kind === "ambience");
  const [beds, setBeds] = useState<AmbienceBed[] | null>(null);
  const [place, setPlace] = useState(ask.place ?? "");
  const [words, setWords] = useState<string | null>(null);
  const [target, setTarget] = useState("");
  const [busy, setBusy] = useState(false);
  // a mix fetched from an older server (the page loaded before it restarted) has no places:
  // fetched again as this opens
  useEffect(() => {
    if (mix && !mix.places) void loadMix();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  // the beds, fetched when it opens
  useEffect(() => {
    let live = true;
    const fn = api().ambience;
    if (!fn) setBeds([]);
    else fn(ep).then((r) => live && setBeds(r.beds)).catch(() => live && setBeds([]));
    return () => {
      live = false;
    };
  }, [ep]);
  // the cut's places in cut order, each with its shots (beds are per place: an angle or a
  // relit version plays its place's, the server says which)
  const places = useMemo((): PlaceRow[] => {
    const out = new Map<string, PlaceRow>();
    for (const it of items) {
      const p = mix?.places?.[it.shot];
      if (!p) continue;
      const row = out.get(p.place) ?? { place: p.place, name: p.name, shots: [] };
      if (!row.shots.includes(it.shot)) row.shots.push(it.shot);
      out.set(p.place, row);
    }
    if (ask.place && !out.has(ask.place)) out.set(ask.place, { place: ask.place, name: ask.place, shots: [] });
    return [...out.values()];
  }, [items, mix?.places, ask.place]);
  useEffect(() => {
    if (!place && places.length) setPlace((places.find((p) => !bedOf(p.place)?.exists) ?? places[0]).place);
  }, [places, beds]); // eslint-disable-line react-hooks/exhaustive-deps
  const bedOf = (p: string) => beds?.find((b) => b.place === p);
  const entry = (p: string) => (sc.base?.locations as Raw | undefined)?.[p] as Raw | undefined;
  const wordsOf = (p: string) => String(entry(p)?.ambience ?? bedOf(p)?.words ?? "");
  const own = wordsOf(place);
  const text = words ?? own;
  const changed = text.trim() !== own.trim();
  const bed = bedOf(place);
  const row = places.find((p) => p.place === place);
  const make = async () => {
    if (!place || !text.trim()) return;
    setBusy(true);
    if (changed) {
      if (!sc.base) {
        setBusy(false);
        return;
      }
      const ok = await sc.save(setPath(sc.base, ["locations", place, "ambience"], text.trim()), `${row?.name ?? place}'s ambience`);
      if (!ok) {
        setBusy(false);
        return;
      }
    }
    closeSoundAdd();
    void makeBed(place, target || null);
  };
  return (
    <Dialog title="Make an ambience bed" sub="A place's room tone or air, made from its words and looped under every shot set there"
      onClose={closeSoundAdd} wide
      footer={
        <>
          <button className="h3-btn" onClick={closeSoundAdd}>Cancel</button>
          <button className="h3-btn h3-primary" data-act="make-bed" disabled={busy || !place || !text.trim() || (changed && !sc.base)} onClick={() => void make()}
            title={changed ? "Its words are written to the series config's location first (the episode is rebuilt), then the bed is made from them" : "A new take of the bed from its words"}>
            {busy ? "Saving…" : `${changed ? "Save the words and make" : bed?.takes ? "Make it again" : "Make it"}${row ? ` (${row.name})` : ""}`}
          </button>
        </>
      }>
      <div className="h3-col" style={{ gap: 8 }}>
        {mix && !mix.places && <div className="h3-note h3-small">This server doesn't say where the cut's shots are: update seriesmith, and restart it.</div>}
        {mix?.places && !places.length && <div className="h3-note h3-small">No shot of the cut is set at a location of the series config.</div>}
        {places.length > 0 && (
          <div className="h3-col" style={{ gap: 2, maxHeight: 240, overflow: "auto" }}>
            {places.map((p) => {
              const b = bedOf(p.place);
              const w = wordsOf(p.place);
              return (
                <label key={p.place} className="h3-row h3-small" style={{ gap: 6 }} title={w ? `“${w}”` : "No ambience words yet: say what's heard there below"}>
                  <input type="radio" name="bed-place" data-place={p.place} checked={place === p.place} onChange={() => { setPlace(p.place); setWords(null); }} />
                  <i className="pi pi-cloud" />
                  <b>{p.name}</b>
                  {p.name !== p.place && <span className="h3-muted">{p.place}</span>}
                  <span className="h3-grow" />
                  {p.shots.length > 0 && <span className="h3-muted">{p.shots.length} shot{p.shots.length === 1 ? "" : "s"}</span>}
                  {!w && <span className="h3-badge" title="Its location has no `ambience` words">no words</span>}
                  {b?.exists
                    ? <span className="h3-badge h3-b-voice">bed made{b.picked ? ` ${tn(b.picked)}` : ""}</span>
                    : b?.queued ? <span className="h3-badge"><i className="pi pi-spin pi-spinner" /> {b.queued}</span>
                    : w ? <span className="h3-badge">not made</span> : null}
                </label>
              );
            })}
          </div>
        )}
        {place && (
          <>
            <label className="h3-col h3-small" style={{ gap: 2 }}>
              <span>What's heard at {row?.name ?? place} <span className="h3-muted">(its location's <code>ambience</code> in the series config)</span></span>
              <textarea className="h3-in" rows={3} value={text} data-field="words"
                placeholder="e.g. “room tone of a small roadside diner at night: a refrigerator hum, a fluorescent buzz”"
                onChange={(e) => setWords(e.target.value)} />
            </label>
            <div className="h3-muted h3-small">The room tone or the air, never music or a voice. Its angles and relit versions play this bed too, unless one says its own.</div>
            {models.length > 1 && (
              <label className="h3-row h3-small" style={{ gap: 6 }} title="The model the bed is made on (empty: the bed's or the episode's)">
                Model
                <select className="h3-in" style={{ width: "auto" }} value={target} data-field="model" onChange={(e) => setTarget(e.target.value)}>
                  <option value="">{bed?.target ? `${models.find((m) => m.id === bed.target)?.short ?? bed.target} (default)` : "default model"}</option>
                  {models.filter((m) => m.id !== bed?.target).map((m) => <option key={m.id} value={m.id}>{m.short ?? m.label}</option>)}
                </select>
              </label>
            )}
            {bed && !bed.can_generate && bed.why_not && <div className="h3-note h3-small">{bed.why_not}</div>}
          </>
        )}
        {sc.error && <div className="h3-note h3-note-err h3-small">{sc.error}</div>}
        {sc.conflict && <div className="h3-note h3-note-err h3-small">The series config changed on disk meanwhile: close this and open it again.</div>}
      </div>
    </Dialog>
  );
}
