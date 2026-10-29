// A shot's sound, all in one card (the shot form's, and the Sound dialog's: its
// row's chip, its menu's Sound… and Replace audio…):
//
//   Next take   the series' default, or Generate / Clone / Dub for this shot
//   Dub to      the recording's aligned window, a dub track (the shot rendered tiny
//               on a voice model for its sound only), or a take's sound; the
//               model's own sound under the voice, or the voice alone
//   In the cut  what the cut plays for it: its take's own sound, or another sound
//               in its place (Replace audio: no render, the mouths don't follow)
//
// The first two are what the shot's next render does (its takes made otherwise go
// stale); the last changes no render. Several shots: the next take only.

import { useEffect, useRef, useState } from "react";
import { closeSound, generateDubTracks, openClipAudio, setSound } from "../actions";
import { setClipAudio } from "../cutActions";
import { api } from "../host";
import { tn } from "../lib/format";
import { VOICE_TARGET, VOICE_TARGETS, dubBlock, dubTrackBlock } from "../lib/readiness";
import { seriesDefaultTarget, shotTarget, targetShort } from "../lib/targets";
import { statusKey, useApp } from "../store";
import type { CutAudioSource, DubOption, DubSource, DubSources, ShotSound } from "../types";
import { Dialog } from "./Dialogs";

type Mode = ShotSound["mode"] | "default";

const MODES: { mode: Mode; label: string; about: string }[] = [
  { mode: "generate", label: "Generate", about: "The model speaks the written lines in a voice made from each character's `voice` words." },
  { mode: "clone", label: "Clone", about: "The model speaks the lines in each character's voice sample (series.json's voice_sample)." },
  { mode: "dub", label: "Dub", about: "The shot is lip-synced to a track: the recording, a dub track, or a take's sound." },
];

export function SoundDialog() {
  const ask = useApp((s) => s.soundAsk);
  if (!ask) return null;
  const one = ask.shots.length === 1 ? ask.shots[0] : null;
  return (
    <Dialog title={one ? `Sound · ${one}` : `Sound · ${ask.shots.length} shots`} onClose={closeSound} wide
      footer={<><span className="h3-grow" /><button className="h3-btn h3-big" onClick={closeSound}>Done</button></>}>
      {one ? <SoundCard key={one} shot={one} focus={ask.focus} /> : <ManyCard shots={ask.shots} />}
    </Dialog>
  );
}

/** The next take's sound for several shots: the default, generate, clone, or a dub of
 * each one's recorded window (a dub track or a take's sound is one shot's). */
function ManyCard({ shots }: { shots: string[] }) {
  return (
    <div className="h3-col" style={{ gap: 8 }}>
      <b>Next take</b>
      <span className="h3-seg">
        <button onClick={() => void setSound(shots, null)}>Default</button>
        <button onClick={() => void setSound(shots, { mode: "generate" })}>Generate</button>
        <button onClick={() => void setSound(shots, { mode: "clone" })}>Clone</button>
        <button title="Each lip-synced to its window of the recording" onClick={() => void setSound(shots, { mode: "dub", dub: { from: "track" } })}>Dub to the recording</button>
      </span>
      <div className="h3-small h3-muted">A dub track or a take's sound is one shot's: open one shot's Sound for those.</div>
    </div>
  );
}

function same(a: DubSource | undefined, b: DubSource): boolean {
  return !!a && a.from === b.from && ("take" in a ? a.take : null) === ("take" in b ? b.take : null)
    && ("pass" in a ? a.pass : null) === ("pass" in b ? b.pass : null);
}

/** The card itself: one shot's sound, its next take's and (`cut`, default on) the
 * cut's. The shot form leaves the cut's out: it is about the next render, and a
 * replacement is set on purpose, from the dialog (Replace audio…). */
export function SoundCard({ shot, focus, cut = true }: { shot: string; focus?: "cut" | null; cut?: boolean }) {
  const ep = useApp((s) => s.ep)!;
  const pass = useApp((s) => s.pass);
  const targets = useApp((s) => s.targets);
  const st = useApp((s) => (s.ep ? s.status[statusKey(s.ep, s.pass)] : undefined));
  const status = st?.shots.find((x) => x.shot === shot);
  const current = status?.sound ?? null;
  const [mode, setMode] = useState<Mode>(current?.mode ?? "default");
  useEffect(() => setMode(current?.mode ?? "default"), [current?.mode]);
  const [src, setSrc] = useState<DubSources | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [model, setModel] = useState(VOICE_TARGET);
  const cutRef = useRef<HTMLDivElement>(null);
  const n = status?.takes.length ?? 0;

  // what the shot can be dubbed to or play: asked when the card opens, when its
  // takes or sound change, and every few seconds while a dub track is on its way
  const load = () => {
    api().dubs(ep, shot).then((d) => { setSrc(d); setErr(null); }).catch((e) => setErr((e as Error).message));
  };
  useEffect(load, [shot, n, JSON.stringify(current)]);
  const waiting = !!src?.dubs.some((d) => d.status === "queued");
  useEffect(() => {
    if (!waiting) return;
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [waiting]);
  useEffect(() => {
    if (focus === "cut") requestAnimationFrame(() => cutRef.current?.scrollIntoView({ block: "center" }));
  }, [focus]);

  const def = seriesDefaultTarget(targets, st);
  const blocked = dubBlock(targets, shotTarget(status, def));
  const keep = current?.keep_foley !== false;
  const set = (sound: ShotSound | null) => void setSound([shot], sound);
  const dubTo = (dub: DubSource, keepFoley = keep) =>
    set({ mode: "dub", dub, ...(keepFoley ? {} : { keep_foley: false }) });
  const pick = (m: Mode) => {
    setMode(m);
    if (m === "default") set(null);
    else if (m !== "dub") set({ mode: m });
    // Dub waits for its track (below)
  };
  const noModel = dubTrackBlock(targets, model);
  const okDubs = (src?.dubs ?? []).filter((d) => d.status === "ok" && d.file);
  const okTakes = (src?.takes ?? []).filter((t) => t.file);

  return (
    <div className="h3-col" style={{ gap: 10 }}>
      {/* ---- the next take ---- */}
      <div className="h3-col" style={{ gap: 4 }}>
        <b>Next take</b>
        <span className="h3-seg">
          <button className={mode === "default" ? "h3-on" : ""}
            title="What the script and series config say for this shot" onClick={() => pick("default")}>
            Default{status?.audio_policy ? ` (${status.audio_policy})` : ""}
          </button>
          {MODES.map((m) => (
            <button key={m.mode} className={mode === m.mode ? "h3-on" : ""} title={m.about} onClick={() => pick(m.mode)}>{m.label}</button>
          ))}
        </span>
        <span className="h3-small h3-muted">
          {MODES.find((m) => m.mode === mode)?.about
            ?? "As the script and series config say. Choose another for this shot alone; its takes made otherwise go stale, so Re-render stale catches them."}
        </span>
      </div>

      {/* ---- what a dub is lip-synced to ---- */}
      {mode === "dub" && (
        <div className="h3-col" style={{ gap: 6 }}>
          <b>Dub to</b>
          {blocked && <div className="h3-note h3-note-warn">{blocked}</div>}
          {err && <div className="h3-note h3-note-err">{err}</div>}
          {!src && !err && <div className="h3-muted h3-small">Looking at what {shot} can be dubbed to…</div>}
          {src?.track && (
            <Choice chosen={same(current?.dub, { from: "track" })} label="the recording"
              detail={`its aligned window, ${src.track.in.toFixed(2)}–${src.track.out.toFixed(2)} s`}
              onPick={() => dubTo({ from: "track" })} />
          )}
          {src && (
            <Choice chosen={current?.dub?.from === "dub"} label="a dub track"
              detail="the shot rendered tiny on a voice model for its sound only">
              <SoundSelect ep={ep} options={okDubs} what={(d) => `dub track ${d.take} · ${targetShort(targets, d.target ?? "") || "?"}`}
                value={current?.dub?.from === "dub" ? current.dub.take : null}
                onPick={(d) => dubTo({ from: "dub", take: d.take })} />
              {(src.dubs.some((d) => d.status === "queued")) && <span className="h3-small h3-muted">one on its way…</span>}
              <span className="h3-row h3-wrap" style={{ gap: 6 }}>
                <select className="h3-in" value={model} onChange={(e) => setModel(e.target.value)} aria-label="Voice model">
                  {VOICE_TARGETS.map((v) => <option key={v.id} value={v.id}>{v.label}</option>)}
                </select>
                <button className="h3-btn h3-primary"
                  title={noModel ?? `Queue a dub track of ${shot} now on ${VOICE_TARGETS.find((v) => v.id === model)?.label}: its voices cloned, the picture tiny and dropped`}
                  onClick={() => { generateDubTracks([shot], model); setTimeout(load, 800); }}>
                  <i className={noModel ? "pi pi-exclamation-triangle" : "pi pi-microphone"} /> Generate a dub track
                </button>
                <button className="h3-btn"
                  title={noModel ?? `The same, and once it's made: ${shot} dubbed with it and rendered on its own model (no listening first)`}
                  onClick={() => { generateDubTracks([shot], model, true); setTimeout(load, 800); }}>
                  <i className="pi pi-forward" /> …then render
                </button>
              </span>
            </Choice>
          )}
          {src && okTakes.length > 0 && (
            <Choice chosen={current?.dub?.from === "take"} label="a take's sound"
              detail={`any finished take, either pass: the delivery you liked, for the ${pass} pass`}>
              <SoundSelect ep={ep} options={okTakes}
                what={(t) => `${tn(t.take)}${t.pass !== "final" ? ` (${t.pass})` : ""} · ${targetShort(targets, t.target ?? "") || "?"}`}
                value={current?.dub?.from === "take" ? `${current.dub.pass}:${current.dub.take}` : null}
                keyOf={(t) => `${t.pass}:${t.take}`}
                onPick={(t) => dubTo({ from: "take", pass: t.pass!, take: t.take })} />
            </Choice>
          )}
          <label className="h3-row h3-small" style={{ gap: 6 }}
            title="On: the model lays its own sound (room, footsteps, effects) under the voice. Off: the voice alone.">
            <input type="checkbox" checked={keep} disabled={!current?.dub}
              onChange={(e) => current?.dub && dubTo(current.dub, e.target.checked)} />
            keep the model's sound effects under the voice
          </label>
        </div>
      )}

      {/* ---- what the cut plays ---- */}
      {cut && (
        <div ref={cutRef} className="h3-col" style={{ gap: 4 }}>
          <b>In the cut</b>
          <CutSound ep={ep} shot={shot} dubs={okDubs} takes={okTakes} />
        </div>
      )}
    </div>
  );
}

/** What the cut plays for the shot: its take's own sound, or another in its place
 * (Replace audio: changes no render). Adjust… opens the timing window. */
function CutSound({ ep, shot, dubs, takes }: { ep: string; shot: string; dubs: DubOption[]; takes: DubOption[] }) {
  const pass = useApp((s) => s.pass);
  const cut = useApp((s) => (s.ep ? s.status[statusKey(s.ep, s.pass)]?.shots.find((x) => x.shot === shot)?.cut : undefined));
  const a = cut?.audio ?? null;
  const replace = (src: CutAudioSource | null) => void setClipAudio(shot, src);
  const dubFile = a?.source === "file" ? dubs.find((d) => d.file === a.path) : undefined;
  const kind = !a ? "own" : a.source === "none" ? "none" : dubFile ? "dub" : a.source === "take" && (a.shot ?? shot) === shot ? "take" : "other";
  return (
    <div className="h3-col" style={{ gap: 4 }}>
      <span className="h3-small h3-muted">
        The cut plays {a ? (cut?.audio_why ?? "another sound") : "its take's own sound"}. A replacement changes no render: the mouths don't follow it (for that, Dub above and render again).
      </span>
      <Choice chosen={kind === "own"} label="its take's own sound" onPick={() => replace(null)} />
      {dubs.length > 0 && (
        <Choice chosen={kind === "dub"} label="a dub track in its place">
          <SoundSelect ep={ep} options={dubs} what={(d) => `dub track ${d.take}`} value={dubFile?.take ?? null}
            onPick={(d) => replace({ ...(a ?? {}), source: "file", path: d.file! })} />
        </Choice>
      )}
      {takes.length > 0 && (
        <Choice chosen={kind === "take"} label="a take's sound in its place">
          <SoundSelect ep={ep} options={takes} keyOf={(t) => `${t.pass}:${t.take}`}
            what={(t) => `${tn(t.take)}${t.pass !== "final" ? ` (${t.pass})` : ""}`}
            value={kind === "take" ? `${a!.pass ?? pass}:${a!.take}` : null}
            onPick={(t) => replace({ ...(a ?? {}), source: "take", shot, take: t.take, pass: t.pass })} />
        </Choice>
      )}
      <Choice chosen={kind === "none"} label="silence" onPick={() => replace({ source: "none" })} />
      <span className="h3-row h3-wrap" style={{ gap: 6 }}>
        {kind === "other" && <span className="h3-small">another shot's take or a file: {cut?.audio_why}</span>}
        <button className="h3-btn" title="Another shot's take or a file, where it starts, its offset and level, with a preview against the picture"
          onClick={() => openClipAudio(shot, pass)}>
          Adjust… / another source
        </button>
      </span>
    </div>
  );
}

function Choice({ chosen, label, detail, onPick, children }: {
  chosen: boolean; label: string; detail?: string; onPick?: () => void; children?: React.ReactNode;
}) {
  return (
    <div className="h3-col" style={{ gap: 3, padding: "3px 6px", borderRadius: 4, ...(chosen ? { outline: "2px solid var(--h3-accent)" } : {}) }}>
      <span className="h3-row" style={{ gap: 6 }}>
        {onPick
          ? <label className="h3-row" style={{ gap: 6 }}><input type="radio" checked={chosen} onChange={onPick} /> <b>{label}</b></label>
          : <b>{label}</b>}
        {detail && <span className="h3-small h3-muted">{detail}</span>}
        {chosen && <span className="h3-badge h3-b-cut">in use</span>}
      </span>
      {children}
    </div>
  );
}

/** A list of sounds to choose from, each playable, the chosen one marked. */
function SoundSelect<T extends DubOption>({ ep, options, what, value, onPick, keyOf = (o) => o.take }: {
  ep: string; options: T[]; what: (o: T) => string; value: string | number | null;
  onPick: (o: T) => void; keyOf?: (o: T) => string | number;
}) {
  if (!options.length) return <span className="h3-small h3-muted">None yet.</span>;
  return (
    <div className="h3-col" style={{ gap: 2 }}>
      {options.map((o) => {
        const on = keyOf(o) === value;
        return (
          <span key={String(keyOf(o))} className="h3-row h3-wrap" style={{ gap: 6 }}>
            <span className={`h3-small h3-grow${on ? "" : " h3-muted"}`}>{what(o)}{o.seconds ? ` · ${o.seconds.toFixed(1)} s` : ""}</span>
            {o.file && <audio controls preload="none" src={api().fileUrl(ep, o.file)} style={{ height: 28 }} />}
            {on ? <span className="h3-badge h3-b-cut">this one</span>
              : <button className="h3-btn" onClick={() => onPick(o)}>Use</button>}
          </span>
        );
      })}
    </div>
  );
}
