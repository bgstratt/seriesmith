// The first-pass score (docs/SOUND.md phase 8, "The simple first pass"; POST /seriesmith/cue/draft):
// the spotting sheet's Draft, a dialog that asks the server what it would draft from the script's
// `// structure:` and `// beat:` lines (fetched when opened, nothing written), shows its cues (a
// section per beat, their themes and hits), what it flags for a person (music in the scene, a
// montage, a card) and its notes (a theme the series doesn't have yet), then writes it: the cues
// (d01...), their hits, and the dialogue to voices only unless the takes' sound is kept. An
// earlier draft is replaced only when asked; a cue of the episode's own is never touched.

import { useEffect, useState } from "react";
import { report } from "../actions";
import { loadCues } from "../cueActions";
import { api, host } from "../host";
import { fmtClock } from "../lib/format";
import { loadMix } from "../mixActions";
import { loadCueStates } from "../spotActions";
import type { DraftCue, Pass, ScoreDraftResult } from "../types";
import { Dialog } from "./Dialogs";

const KIND: Record<DraftCue["kind"], string> = { cue: "cue", sting: "sting", bumper: "bumper", mark: "theme mark" };

function themeText(c: DraftCue): string {
  if (c.makes === "story") return "makes the episode's theme";
  if (c.theme === "story") return "the episode's theme";
  return c.theme ?? "";
}

export function ScoreDraftDialog({ ep, pass, onClose }: { ep: string; pass: Pass; onClose: () => void }) {
  const [res, setRes] = useState<ScoreDraftResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [replace, setReplace] = useState(false);
  const [keep, setKeep] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let live = true;
    api().scoreDraft({ ep, pass }).then((r) => live && setRes(r), (e) => live && setErr(String((e as Error)?.message ?? e)));
    return () => {
      live = false;
    };
  }, [ep, pass]);
  const d = res?.draft;
  const cues = d?.cues ?? [];
  const writes = cues.filter((c) => c.spec);
  const blocked = !!d?.drafted.length && !replace;

  const write = async () => {
    setBusy(true);
    try {
      const r = await api().scoreDraft({ ep, pass, write: true, replace, keep_sound: keep });
      const w = r.written!;
      host().toast("success", `Drafted ${w.cues.length} cue${w.cues.length === 1 ? "" : "s"}`,
        `${w.hits} hit${w.hits === 1 ? "" : "s"} in the ${pass} mix${w.removed.length ? `; the earlier draft (${w.removed.join(", ")}) went to _history` : ""}`
        + `${keep ? "" : "; the dialogue plays voices only"}. Nothing is rendered yet: shape each cue, then render it.`);
      await Promise.all([loadCues(ep), loadMix(ep, pass), loadCueStates(ep, pass)]);
      onClose();
    } catch (e) {
      report("Couldn't write the draft", e);
    } finally {
      setBusy(false);
    }
  };

  const footer = (
    <>
      {d && d.drafted.length > 0 && (
        <label className="h3-row h3-small" title="Its cues go to the episode's _history folder with their takes; its hits come out of the mix">
          <input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} />
          Replace the earlier draft ({d.drafted.join(", ")})
        </label>
      )}
      <label className="h3-row h3-small" title="Without it, the dialogue track plays each take's voice stem (the models' own music and room tone gone), so the score and the beds run across the cuts">
        <input type="checkbox" checked={keep} onChange={(e) => setKeep(e.target.checked)} />
        Keep the takes' own sound
      </label>
      <span className="h3-grow" />
      <button className="h3-btn" onClick={onClose}>Cancel</button>
      <button className="h3-btn h3-primary" disabled={!d || busy || blocked || !writes.length}
        title={blocked ? "The episode has a draft already: tick Replace" : "Write the cues and hits; nothing is rendered"}
        onClick={() => void write()}>
        {busy ? "Writing…" : `Write ${writes.length} cue${writes.length === 1 ? "" : "s"}`}
      </button>
    </>
  );

  return (
    <Dialog title="Draft the score" wide onClose={onClose} footer={footer}
      sub={d ? `${d.structure ?? "No structure"} · ${d.beats.length} beat${d.beats.length === 1 ? "" : "s"} · ${pass}` : "From the script's structure and beat lines"}>
      {err && <div className="h3-small h3-cue-offtext">{err}</div>}
      {!d && !err && <div className="h3-small h3-muted">Reading the script…</div>}
      {d && (
        <>
          <div className="h3-small h3-muted">
            A first pass from each beat's row of its structure's Music table (or the series config's <code>sound.format</code>):
            cues not rendered, for you to shape. Beats in a row with music are one cue, a section each.
          </div>
          {cues.length ? (
            <table className="h3-table h3-small">
              <thead><tr><th>Cue</th><th>Time</th><th>Beats: mood (energy)</th><th>Theme</th></tr></thead>
              <tbody>
                {cues.map((c, i) => (
                  <tr key={i} style={{ cursor: "default", opacity: c.skip ? 0.5 : 1 }} title={c.skip ? `Left out: ${c.skip}` : undefined}>
                    <td className="h3-mono">{c.id ?? "—"} <span className="h3-muted">{KIND[c.kind]}</span></td>
                    <td className="h3-mono">{fmtClock(c.t0)}–{fmtClock(c.t1)}</td>
                    <td>
                      {c.sections.map((s, j) => (
                        <div key={j}>{s.name}: {s.words || "—"} <span className="h3-muted">({s.from}→{s.to})</span></div>
                      ))}
                      {c.hits.length > 0 && <div className="h3-muted">{c.hits.map((h) => `${h.kind} ${h.shot}`).join(", ")}</div>}
                      {c.skip && <div className="h3-cue-offtext">left out: {c.skip}</div>}
                    </td>
                    <td>{themeText(c)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <div className="h3-small">No music drafted: every beat plays dry.</div>}
          {d.flags.length > 0 && (
            <div className="h3-small">
              <b>For you to decide</b>
              <ul style={{ margin: "2px 0 0 18px", padding: 0 }}>{d.flags.map((f, i) => <li key={i}><span className="h3-mono">{f.shot}</span>: {f.text}</li>)}</ul>
            </div>
          )}
          {(d.notes.length > 0 || d.missing.length > 0 || d.kept.length > 0) && (
            <ul className="h3-small h3-muted" style={{ margin: 0, paddingLeft: 18 }}>
              {d.notes.map((n, i) => <li key={i}>{n}</li>)}
              {d.kept.length > 0 && <li>Kept, rendered already: {d.kept.join(", ")} (yours now; the draft works around them)</li>}
              {d.missing.length > 0 && <li>{d.missing.length} shot{d.missing.length === 1 ? " has" : "s have"} no take yet: timed at the shotlist's length, and a cue over one plans when it has a take</li>}
            </ul>
          )}
        </>
      )}
    </Dialog>
  );
}
