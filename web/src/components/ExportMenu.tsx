// The timeline's Export menu (in the overlay, as the Cut menu is): the cut as a
// review mp4, with the series titles, or as an XML timeline for an editor, each
// from the takes or their upscales (2x); and Master.

import { checkThenExport, masterCut } from "../actions";
import type { ExportRun } from "../lib/exportCheck";
import { store, useApp } from "../store";
import { OverlayMenu } from "./CutMenu";

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
      <button onClick={() => { close(); masterCut(); }}
        title={`The series recipe (upscale.master) on every shot of the ${pass} cut, then the master assembled into the episode's master folder, with the intro and outro when the show's _titles has them`}>
        <i className="pi pi-video" /> Master…
      </button>
    </OverlayMenu>
  );
}
