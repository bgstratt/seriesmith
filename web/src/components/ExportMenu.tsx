// The timeline's Export menu (in the overlay, as the Cut menu is): the cut as a
// review mp4, with the series titles, or as an XML timeline for an editor, each
// from the takes or their upscales (2x); and Master.

import { useEffect, useState } from "react";
import { checkThenExport, masterCut } from "../actions";
import { api } from "../host";
import type { ExportRun } from "../lib/exportCheck";
import { store, useApp } from "../store";
import { OverlayMenu } from "./CutMenu";
import { Dialog } from "./Dialogs";
import { useStatus } from "./hooks";

const close = () => store.set({ exportMenu: null });

export function ExportMenu() {
  const menu = useApp((s) => s.exportMenu);
  const pass = useApp((s) => s.pass);
  const busy = useApp((s) => s.assemble.busy);
  if (!menu) return null;
  const go = (run: ExportRun) => () => {
    close();
    checkThenExport(run);
  };
  const up = (what: string) =>
    `${what} from the cut's upscales (2x). Clips without a fresh upscale are upscaled first (the series' upscale.master recipe, as Master does), and it runs when they're done`;
  return (
    <OverlayMenu menu={menu} btn="data-exportmenu-btn" close={close}>
      <div className="h3-menu-head">The {pass} cut</div>
      <button disabled={busy} onClick={go({ kind: "export", upscaled: false })}
        title={`Assemble the ${pass} review cut into one mp4 with ffmpeg (it says first what's missing, and missing shots are skipped). Not needed to watch the cut: use Play all.`}>
        <i className="pi pi-download" /> Export
      </button>
      <button disabled={busy} onClick={go({ kind: "export", upscaled: true })} title={`${up("The export")}. Writes <cut>_up.mp4 beside the plain cut`}>
        <i className="pi pi-download" /> Export 2x
      </button>
      <div className="h3-menu-sep" />
      <button disabled={busy} onClick={go({ kind: "titles", upscaled: false })}
        title={`Assemble the whole ${pass} cut (fails if a shot is missing), then put the series intro and outro around it with the episode's title (_titles/INTRO.mp4 and OUTRO.mp4 in the show folder). Writes <episode>/publish/`}>
        <i className="pi pi-bookmark" /> Titles
      </button>
      <button disabled={busy} onClick={go({ kind: "titles", upscaled: true })} title={up("Titles")}>
        <i className="pi pi-bookmark" /> Titles 2x
      </button>
      <div className="h3-menu-sep" />
      <button disabled={busy} onClick={go({ kind: "xml", upscaled: false })}
        title={`The ${pass} cut as a timeline for Premiere, Resolve and the like (FCP7 XML, <cut>.xml beside the mp4): each clip its take's own file, in and out where the cut uses it, so what a trim leaves out is there to slip into; fades and dissolves as cross dissolves. Nothing is encoded; missing shots are skipped; colour isn't carried.`}>
        <i className="pi pi-file-export" /> Premiere / Resolve XML
      </button>
      <button disabled={busy} onClick={go({ kind: "xml", upscaled: true })} title={`${up("The XML")}. Writes <cut>_up.xml`}>
        <i className="pi pi-file-export" /> Premiere / Resolve XML 2x
      </button>
      <div className="h3-menu-sep" />
      <button onClick={() => { close(); store.set({ exportReport: true }); }}
        title="The last export's whole log: what was laid, the mix (levels, the lines levelled), the loudness, the subtitles, the picture's checks. Kept beside the takes as last_export.txt">
        <i className="pi pi-list" /> Last export's report…
      </button>
      <button onClick={() => { close(); masterCut(); }}
        title={`The series recipe (upscale.master) on every shot of the ${pass} cut, then the master assembled into the episode's master folder, with the intro and outro when the show's _titles has them`}>
        <i className="pi pi-video" /> Master…
      </button>
    </OverlayMenu>
  );
}

/** The last export's whole log: this session's, else the one kept beside the pass's takes
 * (<renders folder>/last_export.txt, edit.assemble_episode). */
export function ExportReport() {
  const open = useApp((s) => s.exportReport);
  const ep = useApp((s) => s.ep);
  const pass = useApp((s) => s.pass);
  const session = useApp((s) => s.assemble.report);
  const st = useStatus(pass);
  const [kept, setKept] = useState<string | null>(null);
  const folder = st?.folder;
  useEffect(() => {
    if (!open || !ep || !folder) return;
    let live = true;
    fetch(api().fileUrl(ep, `${folder}/last_export.txt`), { credentials: "same-origin" })
      .then((r) => (r.ok ? r.text() : null)).then((t) => { if (live) setKept(t); })
      .catch(() => { if (live) setKept(null); });
    return () => { live = false; };
  }, [open, ep, folder]);
  if (!open) return null;
  const text = kept ?? session;
  return (
    <Dialog title={<>Last export's report <span className="h3-muted h3-small">{pass}</span></>} wide
      onClose={() => store.set({ exportReport: false })}>
      {text
        ? <pre className="h3-mono h3-small" style={{ whiteSpace: "pre-wrap", maxHeight: "70vh", overflow: "auto", margin: 0 }}>{text}</pre>
        : <div className="h3-muted">No export of the {pass} cut yet (or it was made before reports were kept).</div>}
    </Dialog>
  );
}
