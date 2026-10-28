// A shot's sound: generate, clone, or dub a track -- the recorded track's window,
// any take's sound (either pass), or a dub track made for it (the shot rendered tiny
// on a voice model for its sound only). What's picked is what the shot's next render
// does; its takes made otherwise go stale. Several shots: generate, clone or the
// recorded track (a take or a dub track is one shot's).

import { useEffect, useState } from "react";
import { closeSound, generateDubTracks, setSound } from "../actions";
import { api } from "../host";
import { tn } from "../lib/format";
import { VOICE_TARGET, VOICE_TARGETS, dubBlock, dubTrackBlock } from "../lib/readiness";
import { shotTarget, seriesDefaultTarget, targetShort } from "../lib/targets";
import { statusKey, useApp } from "../store";
import type { DubOption, DubSource, DubSources, ShotSound } from "../types";
import { Dialog } from "./Dialogs";

const MODES: { mode: ShotSound["mode"]; label: string; about: string }[] = [
  { mode: "generate", label: "Generate", about: "The model speaks the written lines in a voice made from each character's `voice` words." },
  { mode: "clone", label: "Clone", about: "The model speaks the lines in each character's voice sample (series.json's voice_sample)." },
  { mode: "dub", label: "Dub", about: "The shot is dubbed to a track: the recorded track, a take's sound, or a dub track made for it." },
];

function same(a: DubSource | undefined, b: DubSource): boolean {
  return !!a && a.from === b.from && ("take" in a ? a.take : null) === ("take" in b ? b.take : null)
    && ("pass" in a ? a.pass : null) === ("pass" in b ? b.pass : null);
}

export function SoundDialog() {
  const ask = useApp((s) => s.soundAsk);
  if (!ask) return null;
  return <SoundBody key={ask.shots.join(",")} shots={ask.shots} />;
}

function SoundBody({ shots }: { shots: string[] }) {
  const ep = useApp((s) => s.ep)!;
  const pass = useApp((s) => s.pass);
  const targets = useApp((s) => s.targets);
  const st = useApp((s) => (s.ep ? s.status[statusKey(s.ep, s.pass)] : undefined));
  const one = shots.length === 1 ? shots[0] : null;
  const status = one ? st?.shots.find((x) => x.shot === one) : undefined;
  const current: ShotSound | null = one ? status?.sound ?? null : null;
  const [mode, setMode] = useState<ShotSound["mode"] | null>(current?.mode ?? null);
  const [src, setSrc] = useState<DubSources | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [model, setModel] = useState(VOICE_TARGET);
  const n = st?.shots.find((x) => x.shot === one)?.takes.length ?? 0;

  // what a shot can be dubbed to: asked when the dialog opens, again when its takes
  // change (a dub track landing), and every few seconds while one is on its way
  const load = () => {
    if (!one) return;
    api().dubs(ep, one).then((d) => { setSrc(d); setErr(null); }).catch((e) => setErr((e as Error).message));
  };
  useEffect(load, [one, n, current?.dub?.from, current?.dub && "take" in current.dub ? current.dub.take : 0]);
  const waiting = !!src?.dubs.some((d) => d.status === "queued");
  useEffect(() => {
    if (!waiting) return;
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [waiting]);

  const def = seriesDefaultTarget(targets, st);
  const blocked = one ? dubBlock(targets, shotTarget(status, def)) : null;
  const choose = (sound: ShotSound | null) => void setSound(shots, sound).then((ok) => ok && one && load());
  const pickMode = (m: ShotSound["mode"]) => {
    setMode(m);
    if (m !== "dub") choose({ mode: m });
  };
  const use = (dub: DubSource) => choose({ mode: "dub", dub });
  const noModel = dubTrackBlock(targets, model);

  return (
    <Dialog
      title={one ? `Sound · ${one}` : `Sound · ${shots.length} shots`}
      sub={one ? (current ? `Set here: ${current.mode}${current.label ? ` · ${current.label}` : ""}` : `As the script says (${status?.audio_policy ?? "?"})`) : "Applies to each of them"}
      onClose={closeSound}
      wide
      footer={
        <>
          <button className="h3-btn" title="Back to what the script and series.json say" onClick={() => { setMode(null); choose(null); }}>
            As the script says
          </button>
          <span className="h3-grow" />
          <button className="h3-btn h3-big" onClick={closeSound}>Done</button>
        </>
      }
    >
      <span className="h3-seg">
        {MODES.map((m) => (
          <button key={m.mode} className={mode === m.mode ? "h3-on" : ""} title={m.about} onClick={() => pickMode(m.mode)}>{m.label}</button>
        ))}
      </span>
      <div className="h3-small h3-muted">{MODES.find((m) => m.mode === mode)?.about ?? "Pick how the shot's sound is made. Its takes made otherwise go stale, so Re-render stale catches them."}</div>

      {mode === "dub" && !one && (
        <div className="h3-col" style={{ gap: 6 }}>
          <div className="h3-note">A take's sound or a dub track is one shot's: open one shot for those. For several, each can dub its window of the recorded track.</div>
          <button className="h3-btn" onClick={() => use({ from: "track" })}>Dub each to the recorded track</button>
        </div>
      )}

      {mode === "dub" && one && (
        <div className="h3-col" style={{ gap: 8 }}>
          {blocked && <div className="h3-note h3-note-warn">{blocked}</div>}
          {err && <div className="h3-note h3-note-err">{err}</div>}
          {!src && !err && <div className="h3-muted">Looking at what {one} can be dubbed to…</div>}
          {src?.track && (
            <Group title="The recorded track">
              <Row chosen={same(current?.dub, { from: "track" })} label={`its window, ${src.track.in.toFixed(2)}–${src.track.out.toFixed(2)} s`}
                onUse={() => use({ from: "track" })} />
            </Group>
          )}
          {src && (
            <Group title="Dub tracks" note="The shot rendered tiny on a voice model for its sound only. Make several; keep the one you like.">
              {!src.dubs.length && <div className="h3-small h3-muted">None yet.</div>}
              {src.dubs.map((d) => (
                <Row key={d.take} ep={ep} opt={d} chosen={same(current?.dub, { from: "dub", take: d.take })}
                  label={`dub track ${d.take} · ${targetShort(targets, d.target ?? "") || "?"}`}
                  onUse={() => use({ from: "dub", take: d.take })} />
              ))}
              <div className="h3-row h3-wrap" style={{ gap: 6 }}>
                <select className="h3-in" value={model} onChange={(e) => setModel(e.target.value)} aria-label="Voice model">
                  {VOICE_TARGETS.map((v) => <option key={v.id} value={v.id}>{v.label}</option>)}
                </select>
                <button className="h3-btn h3-primary" title={noModel ?? `Queue a dub track of ${one} now on ${VOICE_TARGETS.find((v) => v.id === model)?.label}: its voices cloned, the picture tiny and dropped`}
                  onClick={() => { generateDubTracks([one], model); setTimeout(load, 800); }}>
                  <i className={noModel ? "pi pi-exclamation-triangle" : "pi pi-microphone"} /> Generate a dub track
                </button>
              </div>
            </Group>
          )}
          {src && src.takes.length > 0 && (
            <Group title="Its takes' sound" note={`Any finished take with sound, either pass: the delivery you liked, for the ${pass} pass.`}>
              {src.takes.map((t) => (
                <Row key={`${t.pass}${t.take}`} ep={ep} opt={t}
                  chosen={same(current?.dub, { from: "take", pass: t.pass!, take: t.take })}
                  label={`${tn(t.take)}${t.pass !== "final" ? ` (${t.pass})` : ""} · ${targetShort(targets, t.target ?? "") || "?"}`}
                  onUse={() => use({ from: "take", pass: t.pass!, take: t.take })} />
              ))}
            </Group>
          )}
        </div>
      )}
    </Dialog>
  );
}

function Group({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <div className="h3-col" style={{ gap: 4 }}>
      <b>{title}</b>
      {note && <span className="h3-small h3-muted">{note}</span>}
      {children}
    </div>
  );
}

function Row({ ep, opt, label, chosen, onUse }: {
  ep?: string; opt?: DubOption; label: string; chosen: boolean; onUse: () => void;
}) {
  const ready = !opt || (opt.status === "ok" && !!opt.file);
  return (
    <div className="h3-row h3-wrap" style={{ gap: 8, padding: "2px 0", ...(chosen ? { outline: "2px solid var(--h3-accent)", borderRadius: 4, padding: 4 } : {}) }}>
      <span className="h3-grow h3-small">{label}{opt?.seconds ? ` · ${opt.seconds.toFixed(1)} s` : ""}
        {opt && opt.status !== "ok" && <span className="h3-muted"> · {opt.status === "queued" ? "on its way…" : opt.status}</span>}
      </span>
      {opt?.file && ep && <audio controls preload="none" src={api().fileUrl(ep, opt.file)} style={{ height: 28 }} />}
      {chosen ? <span className="h3-badge h3-b-cut">dubbing to this</span>
        : <button className="h3-btn" disabled={!ready} title={ready ? "Dub the shot to this" : "Not finished, or no sound"} onClick={onUse}>Use</button>}
    </div>
  );
}
