// Frames of a take made again (docs/EDITOR.md, "Re-rendering part of a take"): the
// range picked on the take's own video, the prompt ready to change, a new seed.
// The whole clip is sampled and everything outside the range held, its sound kept.
import { useEffect, useRef, useState } from "react";
import { baseRender, closeRangeRedo, queueRender, takePrompt } from "../actions";
import { errText } from "../api";
import { api } from "../host";
import { tn } from "../lib/format";
import { frameAt, rangeAsked, rangeText, timeOf } from "../lib/rangeRedo";
import { findTarget, isRetargeted, shotTarget, targetLabel } from "../lib/targets";
import { useApp } from "../store";
import type { Pass, ShotDetail, TakeDetail } from "../types";
import { Dialog } from "./Dialogs";
import { useDetail, useDetailError } from "./hooks";
import { useTargets } from "./Targets";

export function RangeDialog() {
  const r = useApp((s) => s.rangeRedo);
  const ep = useApp((s) => s.ep);
  const d = useDetail(r?.shot, r?.pass);
  const derr = useDetailError(r?.shot, r?.pass);
  if (!r || !ep) return null;
  const take = d?.takes.find((t) => t.take === r.take);
  return (
    <Dialog title={<>Re-render part of {r.shot} {tn(r.take)}</>}
      sub="A new take: the frames you pick are made again, the rest of the clip and its sound are kept"
      onClose={closeRangeRedo} wide bare>
      {!d && !derr && <div className="h3-dialog-body h3-muted">Loading {r.shot}…</div>}
      {derr && !d && <div className="h3-dialog-body"><div className="h3-note h3-note-err">{derr}</div></div>}
      {d && !take && <div className="h3-dialog-body"><div className="h3-note h3-note-err">{r.shot} has no {tn(r.take)}.</div></div>}
      {d && take && <RangeBody key={`${r.shot}|${r.pass}|${r.take}`} ep={ep} d={d} shot={r.shot} pass={r.pass} take={take} />}
    </Dialog>
  );
}

function RangeBody({ ep, d, shot, pass, take }: { ep: string; d: ShotDetail; shot: string; pass: Pass; take: TakeDetail }) {
  const { list, video, seriesDefault } = useTargets();
  const sc = take.sidecar;
  const fps = Number(sc?.fps) || 24;
  const frames = Number(sc?.frames) || Number(sc?.length) || 0;
  const madeOn = typeof sc?.target === "string" ? sc.target : "";
  const shotOwn = shotTarget(d, seriesDefault);
  // the models that can hold a take while they make part of it again
  const options = video.filter((t) => t.capabilities?.remakes_frames).map((t) => t.id);
  const [picked, setPicked] = useState("");
  const target = picked || (options.includes(madeOn) ? madeOn : options.includes(shotOwn) ? shotOwn : options[0] ?? "");
  const keptLatent = !!sc?.latent && target === madeOn;
  // the take's own words on its own model; on another, what that model writes for this
  // shot: editable when that's the shot's own, else written when the run is queued
  const ownWords = target === madeOn;
  const lockPrompt = !ownWords && target !== shotOwn;

  const [start, setStart] = useState("0.00");
  const [end, setEnd] = useState(frames ? timeOf(frames - 1, fps) : "0.00");
  const [time, setTime] = useState(0);
  const [loaded, setLoaded] = useState<string | null>(null);
  const [prompt, setPrompt] = useState("");
  const [note, setNote] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const player = useRef<HTMLVideoElement | null>(null);

  useEffect(() => {
    let live = true;
    setLoaded(null);
    setErr(null);
    if (lockPrompt) return;
    const built = d.effective.prompt;
    if (!ownWords) {
      setLoaded(built);
      setPrompt(built);
      return;
    }
    takePrompt(shot, take.take, pass)
      .then((text) => {
        if (!live) return;
        setLoaded(text ?? built);
        setPrompt(text ?? built);
      })
      .catch((e) => live && setErr(errText(e)));
    return () => { live = false; };
  }, [ownWords, lockPrompt, shot, take.take, pass, d.effective.prompt]);

  const asked = rangeAsked(start, end, frames, fps);
  const stepBy = (s: number) => {
    const v = player.current;
    if (!v) return;
    v.pause();
    v.currentTime = Math.max(0, v.currentTime + s);
  };
  const atPlayer = () => timeOf(frameAt(time, fps), fps);

  const submit = async () => {
    if (asked.problem) { setErr(asked.problem); return; }
    if (!target) { setErr("No model installed here can re-render part of a take."); return; }
    if (!lockPrompt && !prompt.trim()) { setErr("The prompt is empty."); return; }
    setBusy(true);
    try {
      const changed = !lockPrompt && prompt !== loaded;
      const req = {
        ...baseRender(ep, pass, [shot], false, target !== shotOwn || isRetargeted(d) ? target : null),
        redo: true, seed_mode: "new" as const, parent_take: take.take,
        note: note.trim() || `${rangeText(asked.first, asked.last, fps)} of ${tn(take.take)} made again`,
        redo_range: { take: take.take, first: asked.first, last: asked.last, ...(changed ? { prompt } : {}) },
      };
      const r = await queueRender(req);
      if (r && r.queued.length > 0) closeRangeRedo();
    } finally {
      setBusy(false);
    }
  };

  const label = targetLabel(list, target);
  return (
    <>
      <div className="h3-dialog-body">
        <video ref={player} src={api().fileUrl(ep, take.files.mp4 ?? "")} controls preload="auto"
          style={{ width: "100%", maxHeight: 340, background: "#000", borderRadius: 4 }}
          onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)} onSeeked={(e) => setTime(e.currentTarget.currentTime)} />
        <div className="h3-row" style={{ gap: 6, flexWrap: "wrap", alignItems: "center" }}>
          <button className="h3-btn h3-small" title="Back one frame" onClick={() => stepBy(-1 / fps)}><i className="pi pi-step-backward" /></button>
          <button className="h3-btn h3-small" title="On one frame" onClick={() => stepBy(1 / fps)}><i className="pi pi-step-forward" /></button>
          <span className="h3-small h3-mono">{time.toFixed(2)}s</span>
          <button className="h3-btn h3-small" onClick={() => { setStart(atPlayer()); setErr(null); }}>Start here</button>
          <button className="h3-btn h3-small" onClick={() => { setEnd(atPlayer()); setErr(null); }}>End here</button>
          <button className="h3-btn h3-small" disabled={!frames} onClick={() => { setEnd(timeOf(frames - 1, fps)); setErr(null); }}>To the end</button>
        </div>
        <div className="h3-row" style={{ gap: 12, flexWrap: "wrap", alignItems: "center" }}>
          <label className="h3-small">Start <input className="h3-in" aria-label="Start, in seconds" style={{ width: 70 }} value={start} onChange={(e) => { setStart(e.target.value); setErr(null); }} /> s</label>
          <label className="h3-small">End <input className="h3-in" aria-label="End, in seconds" style={{ width: 70 }} value={end} onChange={(e) => { setEnd(e.target.value); setErr(null); }} /> s</label>
          <span className="h3-small h3-muted">{asked.problem || rangeText(asked.first, asked.last, fps)}</span>
        </div>
        <div className="h3-row" style={{ gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <label className="h3-small">Model{" "}
            <select className="h3-in" aria-label="Model" value={target} onChange={(e) => setPicked(e.target.value)}>
              {options.map((id) => <option key={id} value={id}>{findTarget(list, id)?.short ?? id}</option>)}
            </select>
          </label>
          <span className="h3-small h3-muted">
            {keptLatent ? "Held from the take's latent."
              : madeOn && !ownWords ? `Made on ${targetLabel(list, madeOn)}: encoded from its video into ${label}, which softens the kept frames slightly and takes a little longer.`
                : "It kept no latent: encoded from its video, which softens the kept frames slightly and takes a little longer."}
          </span>
        </div>
        {lockPrompt ? (
          <div className="h3-note h3-note-info h3-small">{label} writes its own prompt for this shot when the run is queued.</div>
        ) : (
          <div className="h3-col" style={{ gap: 3 }}>
            <span className="h3-small h3-muted">
              {ownWords ? `The prompt ${tn(take.take)} used.` : `The prompt ${label} writes for this shot.`} Describe what should happen in these frames: a new seed alone usually keeps the same action.
            </span>
            {loaded == null && !err
              ? <div className="h3-muted">Loading the prompt…</div>
              : <textarea className="h3-in h3-prompt-box" aria-label="The prompt" rows={8} value={prompt} spellCheck={false} onChange={(e) => { setPrompt(e.target.value); setErr(null); }} />}
          </div>
        )}
        <input className="h3-in" aria-label="A note on this take" placeholder="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
        <div className="h3-small h3-muted">A few frames either side of the range change slightly too. The rest stays, as does the take's sound, so a changed mouth can drift from the dialogue.</div>
        {err && <div className="h3-note h3-note-err">{err}</div>}
      </div>
      <div className="h3-dialog-foot">
        <span className="h3-chips h3-grow">
          {label && <span className="h3-sum">{label}</span>}
          <span className="h3-sum">new seed</span>
          {!asked.problem && <span className="h3-sum">{rangeText(asked.first, asked.last, fps)}</span>}
        </span>
        <button className="h3-btn h3-big" onClick={closeRangeRedo}>Cancel</button>
        <button className="h3-btn h3-primary h3-big" disabled={busy || !!asked.problem || !target} onClick={() => void submit()}>
          <i className={busy ? "pi pi-spin pi-spinner" : "pi pi-play"} /> Re-render these frames
        </button>
      </div>
    </>
  );
}
