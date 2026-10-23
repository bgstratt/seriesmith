// A sequence relight (POST /seriesmith/refs/relight), from a sequence's header:
// every plate the sequence uses under another light, at once. Each becomes a
// location of its own (`<plate>_<preset>`: of the plate, relight: the preset or
// the instruction), generated as an edit of the plate on an edit model, and the
// sequence can be pointed at them (its header's location and its shots'
// `plate:` lines). A dry run lists what it would make as the light is chosen.

import { useEffect, useMemo, useState } from "react";
import { errText } from "../api";
import { closeRelight, relightSequence } from "../actions";
import { api } from "../host";
import { imageTargets, isEditTarget } from "../lib/imageTargets";
import { targetOptionText } from "../lib/readiness";
import { useApp } from "../store";
import type { RelightResult } from "../types";
import { Dialog } from "./Dialogs";
import { PresetPicker, useRelightTiles } from "./PresetPicker";
import { ModelOptions, useTargets } from "./Targets";

export function RelightDialog() {
  const ask = useApp((s) => s.relightAsk);
  if (!ask) return null;
  return <RelightBody key={ask.sequence} sequence={ask.sequence} />;
}

/** A custom suffix: letters, digits and _ (what a location id may hold). */
export function suffixOk(s: string): boolean {
  return /^[A-Za-z0-9_]+$/.test(s);
}

/** What goes in `relight`: a picked preset's id, else the typed instruction. */
export function relightValue(tiles: { id: string; text: string }[], text: string): string {
  const t = text.trim();
  return tiles.find((x) => x.text === t)?.id ?? t;
}

function RelightBody({ sequence }: { sequence: string }) {
  const tiles = useRelightTiles("location");
  const { list } = useTargets();
  const edits = useMemo(() => imageTargets(list).filter(isEditTarget), [list]);
  const ep = useApp((s) => s.ep);
  const busy = useApp((s) => !!s.busy[`relight|${sequence}`]);
  const [text, setText] = useState("");
  const [suffix, setSuffix] = useState("");
  const [target, setTarget] = useState("");
  const [repoint, setRepoint] = useState(true);
  const [plan, setPlan] = useState<RelightResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const relight = relightValue(tiles, text);
  const preset = tiles.some((t) => t.id === relight);
  const sfx = suffix.trim();
  const badSuffix = !!sfx && !suffixOk(sfx);

  // what it would make, as the light (and the name) are chosen
  useEffect(() => {
    if (!ep || !relight || badSuffix) {
      setPlan(null);
      setErr(null);
      return;
    }
    let live = true;
    const t = setTimeout(async () => {
      try {
        const r = await api().refsRelight({ ep, sequence, relight, suffix: sfx || null, dry_run: true });
        if (live) { setPlan(r); setErr(null); }
      } catch (e) {
        if (live) { setPlan(null); setErr(errText(e)); }
      }
    }, 300);
    return () => { live = false; clearTimeout(t); };
  }, [ep, sequence, relight, sfx, badSuffix]);

  const submit = async () => {
    const r = await relightSequence({ sequence, relight, suffix: sfx || null, target: target || null, repoint });
    if (r) closeRelight();
  };

  const fresh = plan?.locations.filter((l) => !l.exists).length ?? 0;
  return (
    <Dialog
      title={`Relight ${sequence}`}
      sub="Every plate this sequence uses, under another light"
      onClose={closeRelight}
      wide
      footer={
        <>
          <button className="h3-btn" onClick={closeRelight}>Cancel</button>
          <button className="h3-btn h3-primary" disabled={busy || !plan || !!err} onClick={submit}>
            {busy ? "Queuing…" : `Relight ${plan?.locations.length ?? ""} plate${plan?.locations.length === 1 ? "" : "s"}`}
          </button>
        </>
      }
    >
      <div className="h3-col" style={{ gap: 8 }}>
        <PresetPicker tiles={tiles} value={text} onPick={setText}
          title="Relight: the same plates at another time, in other weather or light" />
        <div className="h3-small h3-muted">A relight names its light, and the edit model may draw in what it names (a lamp, a sign, a fire) where there's none: read the instruction, cut what the picture hasn't got, and compare the result with the original.</div>
        <textarea className="h3-in" rows={3} value={text}
          placeholder="Or say it, e.g. “the same place at night in heavy rain, its windows glowing”"
          onChange={(e) => setText(e.target.value)} />
        <div className="h3-row h3-wrap" style={{ gap: 6 }}>
          <label className="h3-small" title="The relit locations are named <plate>_<this>: the preset's id, else “relit”">
            Name them <code>&lt;plate&gt;_</code>
            <input className="h3-in" style={{ width: 110 }} value={suffix}
              placeholder={preset ? relight : "relit"} onChange={(e) => setSuffix(e.target.value)} />
          </label>
          <select className="h3-in" value={target} onChange={(e) => setTarget(e.target.value)}
            title="The edit model: each relit plate is an edit of the plate it's from. The default is the episode's edit model.">
            <option value="">(the episode's edit model)</option>
            <ModelOptions targets={edits} text={(x) => targetOptionText(x)} />
          </select>
        </div>
        <label className="h3-small" title="Rewrite the sequence's header location and its shots' plate: lines to the relit plates (the script keeps a history copy)">
          <input type="checkbox" checked={repoint} onChange={(e) => setRepoint(e.target.checked)} /> Point {sequence} at the relit plates
        </label>
        {badSuffix && <div className="h3-warn h3-small">The name takes letters, digits and _ only.</div>}
        {err && <div className="h3-note h3-note-err">{err}</div>}
        {plan && (
          <div className="h3-col h3-small" style={{ gap: 2 }}>
            {plan.locations.map((l) => (
              <div key={l.id}>
                {l.source} → <b>{l.id}</b>{l.exists ? <span className="h3-muted"> (already there: a new candidate)</span> : null}
              </div>
            ))}
            <div className="h3-muted">
              {fresh ? `${fresh} new location${fresh === 1 ? "" : "s"} in the series config; ` : ""}
              each is an edit of its plate, so the place stays and only the light changes. Pick the takes in Refs.
            </div>
          </div>
        )}
      </div>
    </Dialog>
  );
}
