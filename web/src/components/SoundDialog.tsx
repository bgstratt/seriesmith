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
import { closeSound, generateDubTracks, openClipAudio, renderShots, setSound } from "../actions";
import { setClipAudio } from "../cutActions";
import { api } from "../host";
import { audioOf } from "../lib/audioSource";
import { tn } from "../lib/format";
import { dubBlock, dubTrackBlock, dubTrackDefault, dubTrackModels } from "../lib/readiness";
import { seriesDefaultTarget, shotTarget, targetShort } from "../lib/targets";
import { statusKey, useApp } from "../store";
import type { CutAudioSource, DubOption, DubSource, DubSources, ShotSound } from "../types";
import { Dialog } from "./Dialogs";
import { WindowPlayer } from "./WindowPlayer";

type Mode = ShotSound["mode"] | "default";

const MODES: { mode: Mode; label: string; about: string }[] = [
  { mode: "generate", label: "Generate", about: "The model speaks the written lines in a voice made from each character's `voice` words." },
  { mode: "clone", label: "Clone", about: "The model speaks the lines in each character's voice sample (series.json's voice_sample)." },
  { mode: "dub", label: "Dub", about: "The shot is lip-synced to a track: the recording, a dub track, or a take's sound. The cut and export play that track too." },
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
  const targets = useApp((s) => s.targets);
  const st = useApp((s) => (s.ep ? s.status[statusKey(s.ep, s.pass)] : undefined));
  const status = st?.shots.find((x) => x.shot === shot);
  const current = status?.sound ?? null;
  const [mode, setMode] = useState<Mode>(current?.mode ?? "default");
  useEffect(() => setMode(current?.mode ?? "default"), [current?.mode]);
  const [src, setSrc] = useState<DubSources | null>(null);
  const [err, setErr] = useState<string | null>(null);
  // the series' voice model when it renders dub tracks (Series settings: Voices)
  const served = useApp((s) => (s.ep ? s.refDefaults[s.ep] : undefined));
  const [model, setModel] = useState(() => dubTrackDefault(served));
  const voices = dubTrackModels(targets);
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
    else if (!current?.dub) {
      // what the shot has ready, in that order; else Dub waits for one to be chosen
      if (src?.lines?.length && src.lines.every((l) => l.picked)) dubTo({ from: "line" });
      else if (src?.track) dubTo({ from: "track" });
    }
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

      {/* ---- a dub: one choice, for the next take and the cut ---- */}
      {mode === "dub" && (
        <div className="h3-col" style={{ gap: 6 }}>
          <b>Dub to</b>
          <span className="h3-small h3-muted">What you choose here is what the next take lip-syncs to, and what the cut plays.</span>
          {blocked && <div className="h3-note h3-note-warn">{blocked}</div>}
          {err && <div className="h3-note h3-note-err">{err}</div>}
          {!src && !err && <div className="h3-muted h3-small">Looking at what {shot} can be dubbed to…</div>}
          {src && (src.lines?.length ?? 0) > 0 && (
            <Choice chosen={current?.dub?.from === "line"} label={src.lines!.length > 1 ? "its lines" : "its line"}
              detail="made or brought in under Lines & recording" onPick={src.lines!.every((l) => l.picked) ? () => dubTo({ from: "line" }) : undefined}>
              {src.lines!.map((l) => (
                <div key={l.id} className="h3-col" style={{ gap: 2 }}>
                  <span className="h3-small h3-ell" title={l.text}><b>{l.name}:</b> {l.text}</span>
                  {l.takes.length === 0 && <span className="h3-small h3-muted">No take yet.</span>}
                  {l.takes.map((t) => (
                    <span key={t.take} className="h3-row h3-wrap" style={{ gap: 6 }}>
                      <span className={`h3-small h3-grow${l.picked === t.take ? "" : " h3-muted"}`}>{tn(t.take)}{t.voice_name ? ` · ${t.voice_name}` : ""}{t.seconds ? ` · ${t.seconds.toFixed(1)} s` : ""}</span>
                      <audio controls preload="none" src={api().fileUrl(ep, t.file)} style={{ height: 28 }} />
                      {l.picked === t.take ? <span className="h3-badge h3-b-cut">this one</span>
                        : <button className="h3-btn" onClick={() => void api().pickLine(ep, l.id, t.take).then(() => { dubTo({ from: "line" }); load(); })}>Use</button>}
                    </span>
                  ))}
                </div>
              ))}
            </Choice>
          )}
          {src?.track && (
            <Choice chosen={same(current?.dub, { from: "track" })} label="the recording"
              detail={`its aligned window, ${src.track.in.toFixed(2)}–${src.track.out.toFixed(2)} s`}
              onPick={() => dubTo({ from: "track" })}>
              <WindowPlayer url={api().fileUrl(ep, src.track.file)} from={src.track.in} to={src.track.out} title={`Hear ${shot}'s stretch of the recording`} />
            </Choice>
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
                  {voices.map((v) => <option key={v.id} value={v.id}>{v.short ?? v.label}</option>)}
                  {!voices.some((v) => v.id === model) && <option value={model}>{model}</option>}
                </select>
                <button className="h3-btn"
                  title={noModel ?? `Queue a dub track of ${shot} now on ${voices.find((v) => v.id === model)?.short ?? model}: its voices cloned, the picture tiny and dropped`}
                  onClick={() => { generateDubTracks([shot], model); setTimeout(load, 800); }}>
                  <i className={noModel ? "pi pi-exclamation-triangle" : "pi pi-microphone"} /> Generate a dub track
                </button>
              </span>
            </Choice>
          )}
          {src && (
            <Choice chosen={current?.dub?.from === "take"} label="a take's sound"
              detail={current?.dub?.from === "take" && current.dub.shot ? `${current.dub.shot}'s t${current.dub.take}` : "any finished take, this shot's or another's"}>
              <SoundSelect ep={ep} options={okTakes}
                what={(t) => `${tn(t.take)}${t.pass !== "final" ? ` (${t.pass})` : ""} · ${targetShort(targets, t.target ?? "") || "?"}`}
                value={current?.dub?.from === "take" && !current.dub.shot ? `${current.dub.pass}:${current.dub.take}` : null}
                keyOf={(t) => `${t.pass}:${t.take}`}
                onPick={(t) => dubTo({ from: "take", pass: t.pass!, take: t.take })} />
              <OtherShotTake ep={ep} shot={shot} onPick={(other, t) => dubTo({ from: "take", shot: other, pass: t.pass!, take: t.take })} />
            </Choice>
          )}
          <label className="h3-row h3-small" style={{ gap: 6 }}
            title="On: the model lays its own sound (room, footsteps, effects) under the voice. Off: the voice alone.">
            <input type="checkbox" checked={keep} disabled={!current?.dub}
              onChange={(e) => current?.dub && dubTo(current.dub, e.target.checked)} />
            keep the model's sound effects under the voice
          </label>
          {current?.dub && src && <DubStatus ep={ep} shot={shot} takeInCut={status?.cut?.take ?? null} lips={src.lips ?? []} offset={src.offset ?? 0} modelSound={!!src.model_sound} onChanged={load} />}
        </div>
      )}

      {/* ---- the cut, unless it's been told otherwise ---- */}
      {cut && (
        <div ref={cutRef} className="h3-col" style={{ gap: 4 }}>
          <b>In the cut</b>
          <CutSound shot={shot} dubbed={mode === "dub" && !!current?.dub} />
        </div>
      )}
    </div>
  );
}

/** Another shot's take to dub to: its takes read once a shot is chosen. */
function OtherShotTake({ ep, shot, onPick }: { ep: string; shot: string; onPick: (other: string, t: DubOption) => void }) {
  const st = useApp((s) => (s.ep ? s.status[statusKey(s.ep, s.pass)] : undefined));
  const [other, setOther] = useState("");
  const [takes, setTakes] = useState<DubOption[] | null>(null);
  useEffect(() => {
    if (!other) { setTakes(null); return; }
    let live = true;
    api().dubs(ep, other).then((d) => { if (live) setTakes(d.takes.filter((t) => t.file)); }).catch(() => { if (live) setTakes([]); });
    return () => { live = false; };
  }, [ep, other]);
  return (
    <span className="h3-col" style={{ gap: 2 }}>
      <label className="h3-row h3-small" style={{ gap: 6 }}>
        <span className="h3-muted">From another shot</span>
        <select className="h3-in" value={other} onChange={(e) => setOther(e.target.value)}>
          <option value="">(choose)</option>
          {(st?.shots ?? []).filter((x) => x.shot !== shot).map((x) => <option key={x.shot} value={x.shot}>{x.shot}</option>)}
        </select>
      </label>
      {takes && <SoundSelect ep={ep} options={takes} keyOf={(t) => `${t.pass}:${t.take}`} value={null}
        what={(t) => `${other} ${tn(t.take)}${t.pass !== "final" ? ` (${t.pass})` : ""}`} onPick={(t) => onPick(other, t)} />}
    </span>
  );
}

/** Whether the take in the cut's mouths follow the dub, and what to do if they don't: render to it,
 *  or cheat it, sliding the line to the take's own speech. */
function DubStatus({ ep, shot, takeInCut, lips, offset, modelSound, onChanged }: {
  ep: string; shot: string; takeInCut: number | null; lips: number[]; offset: number; modelSound: boolean; onChanged: () => void;
}) {
  const pass = useApp((s) => s.pass);
  const [said, setSaid] = useState<string | null>(null);
  const matches = takeInCut != null && lips.includes(takeInCut);
  async function lineUp() {
    setSaid("Hearing both with Whisper… the slide appears here when it's done.");
    try {
      await api().lineUpSound(ep, pass, shot);
      const was = offset;
      for (let i = 0; i < 20; i++) {
        await new Promise((r) => setTimeout(r, 3000));
        const d = await api().dubs(ep, shot);
        if ((d.offset ?? 0) !== was) { setSaid(null); onChanged(); return; }
      }
      setSaid("It hasn't finished: look in Jobs.");
    } catch (e) {
      setSaid((e as Error).message);
    }
  }
  return (
    <div className="h3-col" style={{ gap: 4 }}>
      <div className={`h3-note h3-small${matches ? " h3-note-info" : ""}`}>
        {matches
          ? `t${String(takeInCut).padStart(2, "0")} was rendered to this: the mouths follow it.`
          : "In the cut: this dub, over the take. The mouths won't follow it until a take is rendered to it."}
      </div>
      {matches && (
        <span className="h3-col" style={{ gap: 2 }}>
          <b className="h3-small">The cut plays</b>
          <label className="h3-row h3-small" style={{ gap: 6 }} title="What you chose above. Your own effects and music come from the mix">
            <input type="radio" checked={!modelSound} onChange={() => void api().setDubModelSound(ep, shot, false).then(onChanged)} /> the dub
          </label>
          <label className="h3-row h3-small" style={{ gap: 6 }} title="Your line as the model copied it, with any effects, room or music it made around it: what the take's preview plays">
            <input type="radio" checked={modelSound} onChange={() => void api().setDubModelSound(ep, shot, true).then(onChanged)} /> the model's sound: the voice, and whatever it made around it
          </label>
        </span>
      )}
      {!matches && (
        <span className="h3-row h3-wrap" style={{ gap: 6 }}>
          <button className="h3-btn h3-primary" title={`A new take of ${shot}, lip-synced to this`} onClick={() => renderShots([shot], true)}>
            <i className="pi pi-play" /> Render to this
          </button>
          <button className="h3-btn" title="Free: slides the dub so its first word lands on the first word of the take in the cut. Close enough on some shots" onClick={() => void lineUp()}>
            <i className="pi pi-arrows-h" /> Line up with the take
          </button>
          {offset !== 0 && (
            <>
              <span className="h3-small h3-muted">slid {offset > 0 ? "+" : ""}{offset.toFixed(2)} s</span>
              <button className="h3-link" onClick={() => void api().setSoundOffset(ep, shot, 0).then(onChanged)}>put it back</button>
            </>
          )}
        </span>
      )}
      {said && <span className="h3-small h3-muted">{said}</span>}
    </div>
  );
}

/** What overrides all that in the cut: silence, or another source with its timing (Adjust…). */
function CutSound({ shot, dubbed }: { shot: string; dubbed: boolean }) {
  const pass = useApp((s) => s.pass);
  const cut = useApp((s) => (s.ep ? s.status[statusKey(s.ep, s.pass)]?.shots.find((x) => x.shot === shot)?.cut : undefined));
  const own = audioOf(cut);
  const replace = (src: CutAudioSource | null) => void setClipAudio(shot, src);
  return (
    <div className="h3-col" style={{ gap: 4 }}>
      {own
        ? <div className="h3-note h3-small">The cut plays {cut?.audio_why ?? "another sound"} here, set by hand. <button className="h3-link" onClick={() => replace(null)}>{dubbed ? "back to the dub" : "back to its take's own sound"}</button></div>
        : !dubbed && <span className="h3-small h3-muted">The cut plays its take's own sound.</span>}
      <span className="h3-row h3-wrap" style={{ gap: 6 }}>
        <button className="h3-btn" disabled={own?.source === "none"} onClick={() => replace({ source: "none" })}>Silence</button>
        <button className="h3-btn" title="Another shot's take or a file, where it starts, its offset and level, with a preview against the picture. Changes no render"
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
