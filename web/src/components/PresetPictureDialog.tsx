// A picture for one of your presets (a look or a relight of yours), three ways,
// each only when asked: render it on the sample scene on a model you pick (as
// the shipped presets' are), take it from your work (the shot take or the ref
// picture selected now), or import a picture of your own.

import { useMemo, useState } from "react";
import { closePresetPicture, setPresetPicture } from "../actions";
import { imageTargets, isEditTarget } from "../lib/imageTargets";
import { tn } from "../lib/format";
import { viewLabel } from "../lib/refs";
import { targetOptionText } from "../lib/readiness";
import { useApp } from "../store";
import { Dialog } from "./Dialogs";
import { ModelOptions, useTargets } from "./Targets";

export function PresetPictureDialog() {
  const ask = useApp((s) => s.presetPictureAsk);
  if (!ask) return null;
  return <Body key={`${ask.kind}|${ask.id}`} kind={ask.kind} id={ask.id} label={ask.label} />;
}

function Body({ kind, id, label }: { kind: "look" | "relight"; id: string; label: string }) {
  const { list } = useTargets();
  // a look is drawn from words; a relight is an edit of the sample street or the woman on it
  const models = useMemo(() => imageTargets(list).filter((t) => kind === "look" || isEditTarget(t)), [list, kind]);
  const [target, setTarget] = useState("");
  const [time, setTime] = useState("1");
  const [busy, setBusy] = useState(false);
  const ep = useApp((s) => s.ep);
  const pass = useApp((s) => s.pass);
  const shot = useApp((s) => s.shot);
  const take = useApp((s) => s.take);
  const refSel = useApp((s) => s.refSel);
  const run = async (how: Parameters<typeof setPresetPicture>[2]) => {
    setBusy(true);
    const ok = await setPresetPicture(kind, id, how);
    setBusy(false);
    if (ok) closePresetPicture();
  };
  const seconds = Number(time);
  return (
    <Dialog title={`A picture for “${label}”`} sub={`your ${kind}: its tile in the presets`} onClose={closePresetPicture}>
      <div className="h3-col" style={{ gap: 12 }}>
        <div className="h3-col" style={{ gap: 4 }}>
          <b>Render it</b>
          <span className="h3-small h3-muted">
            {kind === "look"
              ? "Your look drawn on the sample scene (the woman in red at the tram stop), like the built-in looks, so the tiles compare."
              : "Your relight as an edit of the sample street (or of the woman on it), like the built-in relights."}
            {" "}One picture on the queue.
          </span>
          <div className="h3-row" style={{ gap: 6 }}>
            <select className="h3-in h3-grow" value={target} onChange={(e) => setTarget(e.target.value)}
              title={kind === "look" ? "The image model it's drawn on" : "The edit model it's made on"}>
              <option value="">{kind === "look" ? "Pick an image model…" : "Pick an edit model…"}</option>
              <ModelOptions targets={models} text={(t) => targetOptionText(t)} />
            </select>
            <button className="h3-btn h3-primary" disabled={!target || busy} onClick={() => void run({ target })}>Render</button>
          </div>
        </div>

        <div className="h3-col" style={{ gap: 4 }}>
          <b>From your work</b>
          {ep && shot && take != null && (
            <div className="h3-row h3-small" style={{ gap: 6 }}>
              <span className="h3-grow">A frame of {shot} {tn(take)} ({pass}) at</span>
              <input className="h3-in" style={{ width: 56 }} value={time} onChange={(e) => setTime(e.target.value)} inputMode="decimal" />
              <span>s</span>
              <button className="h3-btn" disabled={busy || !Number.isFinite(seconds) || seconds < 0}
                onClick={() => void run({ from: { ep, pass, shot, take, time: seconds } })}>Use it</button>
            </div>
          )}
          {ep && refSel && (
            <div className="h3-row h3-small" style={{ gap: 6 }}>
              <span className="h3-grow">{refSel.ref}{refSel.view ? ` (${viewLabel(refSel.view)})` : ""} {tn(refSel.take)}</span>
              <button className="h3-btn" disabled={busy}
                onClick={() => void run({ from: { ep, ref: refSel.ref, view: refSel.view, take: refSel.take } })}>Use it</button>
            </div>
          )}
          {!(ep && shot && take != null) && !(ep && refSel) && (
            <span className="h3-small h3-muted">Select a take in Shots, or a picture in Refs, and it's offered here.</span>
          )}
        </div>

        <div className="h3-col" style={{ gap: 4 }}>
          <b>Import a picture</b>
          <input type="file" accept=".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp" disabled={busy}
            onChange={(e) => { const f = e.target.files?.[0]; if (f) void run({ file: f }); }} />
        </div>
      </div>
    </Dialog>
  );
}
