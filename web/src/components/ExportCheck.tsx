// Before Export / Titles: what the cut is missing (lib/exportCheck), with the
// shots to go to, and Export anyway where the export can still run.

import { closeExportCheck, runExport, select } from "../actions";
import { blocks, EXPORT_NAMES, type ExportProblem, type ExportProblemKind } from "../lib/exportCheck";
import { useApp } from "../store";
import { Dialog } from "./Dialogs";

const GROUPS: { kind: ExportProblemKind; head: (n: number, titles: boolean) => string }[] = [
  {
    kind: "missing",
    head: (n, titles) => `${n} shot${n === 1 ? " has" : "s have"} nothing to play: ${titles ? "Titles needs every shot" : "the export skips them"}`,
  },
  { kind: "short", head: (n) => `${n} take${n === 1 ? " is" : "s are"} shorter than ${n === 1 ? "its" : "their"} dialogue on the recording` },
  { kind: "placeholder", head: (n) => `${n} shot${n === 1 ? " plays" : "s play"} the other pass's take` },
];

export function ExportCheckDialog() {
  const c = useApp((s) => s.exportCheck);
  if (!c) return null;
  const { run, problems, pass } = c;
  const stop = blocks(run, problems);
  const what = `${EXPORT_NAMES[run.kind]}${run.upscaled ? " 2x" : ""}`;
  const go = (p: ExportProblem) => {
    closeExportCheck();
    select(p.shot, null);
  };
  return (
    <Dialog
      title={`Before ${what}`}
      sub={`The ${pass} cut, as it is now`}
      onClose={closeExportCheck}
      footer={
        <>
          <span className="h3-grow" />
          <button className="h3-btn h3-big" onClick={closeExportCheck}>Cancel</button>
          {!stop && (
            <button className="h3-btn h3-primary h3-big" onClick={() => void runExport(run)}>
              {what} anyway
            </button>
          )}
        </>
      }
    >
      {GROUPS.map(({ kind, head }) => {
        const rows = problems.filter((p) => p.kind === kind);
        if (!rows.length) return null;
        return (
          <div key={kind} className="h3-col" style={{ gap: 4 }}>
            <b>{head(rows.length, run.kind === "titles")}</b>
            <ul className="h3-missing-list">
              {rows.map((p) => (
                <li key={p.shot}>
                  <button className="h3-link h3-mono" title={`Select ${p.shot}`} onClick={() => go(p)}>{p.shot}</button> {p.text}
                </li>
              ))}
            </ul>
          </div>
        );
      })}
      {stop && <div className="h3-note">Render or pick a take for each, or leave them out (right-click a clip ▸ Leave out of the cut), then add titles.</div>}
    </Dialog>
  );
}
