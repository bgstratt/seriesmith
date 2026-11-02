// The new episode wizard's "From an edit (FCP7 XML)": an XML picked (uploaded) or named by
// its path on the server's machine, how its footage comes in, a dry run's summary of what
// it makes, then the show made and opened (POST /seriesmith/import/xml; lib/xmlImport.ts).

import { useEffect, useRef, useState } from "react";
import { loadEpisodes, openEpisodeAt, openWizard } from "../actions";
import { api, host } from "../host";
import { MEDIA_CHOICES, doneMessage, handlesOf, summaryLines } from "../lib/xmlImport";
import type { XmlImportMedia, XmlImportSummary } from "../types";
import { Row } from "./ShotForm";

export function XmlImportPanel({ parent }: { parent: string }) {
  const [file, setFile] = useState<File | null>(null);
  const [path, setPath] = useState("");
  const [media, setMedia] = useState<XmlImportMedia>("handles");
  const [handlesText, setHandlesText] = useState("1");
  const [name, setName] = useState("");
  const [summary, setSummary] = useState<XmlImportSummary | null>(null);
  const [checking, setChecking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const asked = useRef(0);

  const handles = handlesOf(handlesText);
  const have = !!file || !!path.trim();

  function send(dry: boolean): Promise<XmlImportSummary> {
    const opts = { parent, media, handles: handles ?? 1, name: name.trim() || null, dry_run: dry };
    return file
      ? api().uploadXml({ ...opts, file, filename: file.name })
      : api().importXml({ ...opts, path: path.trim() });
  }

  // a dry run whenever what it would make changes
  useEffect(() => {
    if (!have || handles == null) {
      setSummary(null);
      return;
    }
    const n = ++asked.current;
    const t = window.setTimeout(() => {
      setChecking(true);
      send(true)
        .then((s) => { if (n === asked.current) { setSummary(s); setError(null); } })
        .catch((e) => { if (n === asked.current) { setSummary(null); setError((e as Error).message); } })
        .finally(() => { if (n === asked.current) setChecking(false); });
    }, 300);
    return () => window.clearTimeout(t);
  }, [file, path, media, handles, name, parent]);

  async function make() {
    setBusy(true);
    setError(null);
    try {
      const s = await send(false);
      host().toast(s.build?.ok === false ? "warn" : "success", `Imported ${s.title}`, doneMessage(s));
      await loadEpisodes();
      openWizard(null);
      await openEpisodeAt(s.ep, parent);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div id="sm-xml-import" className="h3-col" style={{ gap: 10 }}>
      <div className="h3-small h3-muted">
        An edit made in Premiere, DaVinci Resolve or Final Cut 7, exported as an FCP7 XML (File › Export ›
        Final Cut Pro XML), becomes a new show in {parent}: a shot per clip on V1, its footage the shot's take,
        the cut's trims, dissolves and fades kept, the other sound in the mix. Each shot's description is its
        clip's name until you write one.
      </div>
      <Row label="The XML" help="Pick the .xml file, or give its path on the machine seriesmith runs on. Its media is found where the XML says (or beside the XML).">
        <div className="h3-row h3-wrap" style={{ gap: 6 }}>
          <input id="sm-xml-file" type="file" accept=".xml,text/xml,application/xml"
            onChange={(e) => { setFile(e.target.files?.[0] ?? null); if (e.target.files?.[0]) setPath(""); }} />
          <input id="sm-xml-path" className="h3-in h3-mono h3-grow" value={path} placeholder="or C:\Edits\cut.xml"
            onChange={(e) => { setPath(e.target.value); if (e.target.value) setFile(null); }} />
        </div>
      </Row>
      <Row label="The footage" help="How each clip's footage becomes its shot's take.">
        <div className="h3-col" style={{ gap: 4 }}>
          {MEDIA_CHOICES.map((c) => (
            <label key={c.value} className="h3-row" style={{ gap: 6, alignItems: "flex-start" }}>
              <input type="radio" name="sm-xml-media" value={c.value} checked={media === c.value}
                onChange={() => setMedia(c.value)} />
              <span><b>{c.label}</b><br /><span className="h3-small h3-muted">{c.help}</span></span>
            </label>
          ))}
        </div>
      </Row>
      {media === "handles" && (
        <Row label="Handles" help="Seconds of footage kept either side of each clip (as far as its file goes).">
          <input id="sm-xml-handles" className="h3-in" style={{ width: 80 }} value={handlesText}
            onChange={(e) => setHandlesText(e.target.value)} />
          {handles == null && <span className="h3-small h3-err"> 0 to 60 seconds</span>}
        </Row>
      )}
      <Row label="Show" help="The new show's name; its folder is made from it. Empty: the sequence's name.">
        <input id="sm-xml-name" className="h3-in" value={name} placeholder={summary?.sequence ?? "the sequence's name"}
          onChange={(e) => setName(e.target.value)} />
      </Row>
      {checking && <div className="h3-small h3-muted"><i className="pi pi-spin pi-spinner" /> Reading the edit…</div>}
      {summary && (
        <div id="sm-xml-summary" className="h3-col" style={{ gap: 4, padding: 8, border: "1px solid var(--h3-border)", borderRadius: 4 }}>
          <b>{summary.ep}</b>
          {summaryLines(summary).map((l) => <div key={l} className="h3-small">{l}</div>)}
          {summary.clips.filter((c) => c.note || c.missing).map((c) => (
            <div key={c.shot} className="h3-small h3-warn">{c.shot} ({c.name}): {c.missing ?? c.note}</div>
          ))}
          {summary.warnings.length > 0 && (
            <details>
              <summary className="h3-small">{summary.warnings.length} note{summary.warnings.length === 1 ? "" : "s"} on what doesn't come through</summary>
              {summary.warnings.map((w, i) => <div key={i} className="h3-small h3-muted">{w}</div>)}
            </details>
          )}
        </div>
      )}
      {error && <div className="h3-err">{error}</div>}
      <div className="h3-row" style={{ justifyContent: "flex-end" }}>
        <button id="sm-xml-go" className="h3-btn h3-primary" disabled={!summary || busy || checking || handles == null}
          onClick={() => void make()}>
          {busy ? <i className="pi pi-spin pi-spinner" /> : <i className="pi pi-file-import" />} Import {summary?.show ?? ""}
        </button>
      </div>
    </div>
  );
}
