// The folder browser (GET /seriesmith/browse): choosing project roots, opening an
// episode, and picking a file on the ComfyUI machine to import as a ref.

import { useCallback, useEffect, useState } from "react";
import { addRoot, attachTrack, closeBrowse, openWizard, importRef, importSeries, openEpisodeAt, refLabel, removeRoot, useClipAudioFile } from "../actions";
import { errText } from "../api";
import { api } from "../host";
import { AUDIO_EXT, CLIP_AUDIO_EXT, IMAGE_EXT, crumbs } from "../lib/browse";
import { insideRoot } from "../lib/newEpisode";
import { TRACK_EXT } from "../lib/track";
import { viewLabel } from "../lib/refs";
import { useApp, type BrowseState } from "../store";
import type { BrowseDir, BrowseFile, BrowseResult } from "../types";
import { Dialog } from "./Dialogs";

const LAST_KEY = "seriesmith.browse.last";

function lastPath(purpose: string): string | null {
  try {
    return localStorage.getItem(`${LAST_KEY}.${purpose}`);
  } catch {
    return null;
  }
}

function rememberPath(purpose: string, path: string) {
  try {
    if (path) localStorage.setItem(`${LAST_KEY}.${purpose}`, path);
  } catch {
    /* ignore */
  }
}

export function BrowseDialog() {
  const b = useApp((s) => s.browse);
  if (!b) return null;
  return <BrowseBody key={`${b.purpose}|${b.ref ?? ""}|${b.view ?? ""}`} b={b} />;
}

type Sel = { kind: "dir"; d: BrowseDir } | { kind: "file"; f: BrowseFile } | null;

function BrowseBody({ b }: { b: BrowseState }) {
  const config = useApp((s) => s.config);
  const busyRoots = useApp((s) => !!s.busy.config);
  const busyImport = useApp((s) => !!b.ref && !!s.busy[`refimport|${b.ref}`]);
  const [res, setRes] = useState<BrowseResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [sel, setSel] = useState<Sel>(null);
  const [typed, setTyped] = useState("");
  // P5: New episode… — the folder it goes in is the show's, not the episode's
  // seriesmith: Import series… — a series config and a stack of scripts
  const [importingSeries, setImportingSeries] = useState(false);
  const [showName, setShowName] = useState("");
  const [seriesFiles, setSeriesFiles] = useState<File[]>([]);
  const busySeries = useApp((s) => !!s.busy.importSeries);
  const forTrack = b.purpose === "track";
  const busyTrack = useApp((s) => !!s.busy.track);
  // Phase 9d: picking one clip's audio file — the same file list, but the
  // path only becomes the draft's (it has to be inside the episode)
  const forClip = b.purpose === "clip-audio";
  const ep = useApp((s) => s.ep);
  // Phase 9c-A: picking the episode's recording works like an import, but the
  // file goes to POST /seriesmith/track instead of becoming a ref candidate
  const importing = b.purpose === "import" || forTrack || forClip;
  const roots = config?.roots ?? [];

  const go = useCallback(async (path: string | null) => {
    setLoading(true);
    setErr(null);
    try {
      const r = await api().browse(path, importing ? b.files ?? "image" : null);
      setRes(r);
      setSel(null);
      rememberPath(b.purpose, r.path);
    } catch (e) {
      setErr(errText(e));
    } finally {
      setLoading(false);
    }
  }, [b.purpose, b.files, importing]);

  useEffect(() => {
    void go(lastPath(b.purpose) ?? roots[0] ?? null);
    // only on open
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const openEpisode = async (d: { path: string }, parent: string | null) => {
    if (await openEpisodeAt(d.path, parent)) closeBrowse();
  };
  const doImport = async (path: string) => {
    if (forClip) {
      if (useClipAudioFile(path)) closeBrowse();
      return;
    }
    if (forTrack) {
      if (await attachTrack(path)) closeBrowse();
      return;
    }
    if (!b.ref) return;
    if (await importRef(b.ref, b.view ?? null, path)) closeBrowse();
  };

  const here = res?.path ?? "";
  const filesListed = res?.files !== undefined;
  // a recording may also be .aac / .opus, which the server's `files=audio`
  // listing leaves out (see the contract gaps): the typed path takes those
  const ext = forTrack ? TRACK_EXT : forClip ? CLIP_AUDIO_EXT : b.files === "audio" ? AUDIO_EXT : IMAGE_EXT;
  const files = (res?.files ?? []).filter((f) => ext.test(f.name));
  const selDir = sel?.kind === "dir" ? sel.d : null;
  const selFile = sel?.kind === "file" ? sel.f : null;
  // "Open episode" works on the selected folder, else the one we're in
  const epTarget = selDir?.episode ? { path: selDir.path, parent: here || null } : res?.episode ? { path: here, parent: res.parent || null } : null;
  const rootTarget = selDir?.path ?? (here || null);
  // a new episode goes in the show's folder: the selected one, unless that is
  // itself an episode (then the folder we're in is the show's)
  const newParent = selDir && !selDir.episode ? selDir.path : here;
  const outsideRoots = !!newParent && !insideRoot(newParent, roots);


  const title = forClip
    ? <>A file for {b.shot ?? "this clip"}'s audio <span className="h3-muted h3-small">inside the episode</span></>
    : forTrack
    ? "Choose the episode's dialogue recording"
    : importing
      ? <>Import into {refLabel(b.ref ?? "", b.view)} {b.view ? <span className="h3-muted h3-small">{viewLabel(b.view)}</span> : null}</>
      : "Project folders";

  return (
    <Dialog
      title={title}
      onClose={closeBrowse}
      wide
      footer={
        <>
          {importing ? (
            <>
              <span className="h3-muted h3-small h3-grow h3-ell">
                {selFile ? selFile.path : forTrack ? "Pick a recording" : forClip ? `Pick a file inside ${ep ?? "the episode"}` : "Pick a file"}
              </span>
              <button className="h3-btn" onClick={closeBrowse}>Cancel</button>
              <button
                className="h3-btn h3-primary"
                disabled={!selFile || busyImport || busyTrack}
                title={forTrack
                  ? "It goes to <episode>/audio/ (a file already inside the episode is used where it is), and series.json starts naming it"
                  : forClip
                    ? "cut.json keeps it as a path inside the episode, so it has to live there (or beside a parent-folder series config)"
                    : undefined}
                onClick={() => selFile && void doImport(selFile.path)}
              >
                <i className={busyImport || busyTrack ? "pi pi-spin pi-spinner" : "pi pi-download"} /> {forTrack ? "Attach" : forClip ? "Use this file" : "Import"}
              </button>
            </>
          ) : (
            <>
              <span className="h3-muted h3-small h3-grow">Double-click an episode to open it.</span>
              <button
                className="h3-btn"
                disabled={!newParent || outsideRoots}
                title={outsideRoots ? `${newParent} isn't inside a project root: add it as one first` : newParent ? `A new episode in ${newParent}, step by step` : "Browse to the folder your episodes live in"}
                onClick={() => { closeBrowse(); openWizard({ parent: newParent, newSeries: false }); }}
              >
                <i className="pi pi-file-plus" /> New episode…
              </button>
              <button
                className="h3-btn"
                disabled={!newParent || outsideRoots}
                title={outsideRoots ? `${newParent} isn't inside a project root: add it as one first` : newParent ? `Start a new series in a show folder inside ${newParent}` : "Browse to the folder your shows live in"}
                onClick={() => { closeBrowse(); openWizard({ parent: newParent, newSeries: true }); }}
              >
                <i className="pi pi-star" /> New series…
              </button>
              <button
                className="h3-btn"
                disabled={!newParent || importingSeries}
                title={newParent ? `Make episodes in ${newParent} from a series config and scripts` : "Browse to the folder your shows live in"}
                onClick={() => { setImportingSeries(true); }}
              >
                <i className="pi pi-upload" /> Import series…
              </button>
              <button className="h3-btn" disabled={!rootTarget || busyRoots} title={rootTarget ? `Add ${rootTarget} as a project root` : "Browse into a folder first"} onClick={() => rootTarget && void addRoot(rootTarget)}>
                <i className="pi pi-plus" /> Add as root
              </button>
              <button className="h3-btn h3-primary" disabled={!epTarget || busyRoots} title={epTarget ? `Open ${epTarget.path}` : "Select an episode folder"} onClick={() => epTarget && void openEpisode(epTarget, epTarget.parent)}>
                <i className="pi pi-folder-open" /> Open episode
              </button>
              <button className="h3-btn" onClick={closeBrowse}>Close</button>
            </>
          )}
        </>
      }
    >
      <div className="h3-row h3-browse-bar">
        <button className="h3-btn h3-icon" title="Up" disabled={!res || res.parent === null || loading} onClick={() => void go(res?.parent || null)}>
          <i className="pi pi-arrow-up" />
        </button>
        <div className="h3-crumbs h3-grow">
          <button className="h3-link" onClick={() => void go(null)} title="Home and drives">
            <i className="pi pi-desktop" />
          </button>
          {crumbs(here).map((c, i) => (
            <span key={c.path + i}>
              {i > 0 && <span className="h3-muted"> › </span>}
              <button className="h3-link" onClick={() => void go(c.path)}>{c.label}</button>
            </span>
          ))}
        </div>
        {loading && <i className="pi pi-spin pi-spinner h3-muted" />}
        <button className="h3-btn h3-icon" title="Refresh" onClick={() => void go(here || null)}><i className="pi pi-refresh" /></button>
      </div>
      {err && <div className="h3-note h3-note-err">{err}</div>}
      <div className="h3-browse-list" role="listbox">
        {res?.dirs.map((d) => (
          <div
            key={d.path}
            role="option"
            aria-selected={selDir?.path === d.path}
            className={`h3-browse-item${selDir?.path === d.path ? " h3-sel" : ""}${d.episode ? " h3-episode" : ""}`}
            onClick={() => setSel({ kind: "dir", d })}
            onDoubleClick={() => (d.episode && !importing ? void openEpisode(d, here || null) : void go(d.path))}
            title={d.episode && !importing ? `${d.path}\nDouble-click to open this episode` : d.path}
          >
            <i className={d.episode ? "h3-ico-film" : "pi pi-folder"} />
            <span className="h3-grow h3-ell">{d.name}</span>
            {d.episode && <span className="h3-badge h3-b-cut">episode</span>}
            {!d.episode && d.series_config && <span className="h3-badge">series</span>}
            {roots.some((r) => r.replace(/[\\/]+$/, "").toLowerCase() === d.path.replace(/[\\/]+$/, "").toLowerCase()) && <span className="h3-badge h3-b-ok">root</span>}
          </div>
        ))}
        {importing && files.map((f) => (
          <div
            key={f.path}
            role="option"
            aria-selected={selFile?.path === f.path}
            className={`h3-browse-item${selFile?.path === f.path ? " h3-sel" : ""}`}
            onClick={() => setSel({ kind: "file", f })}
            onDoubleClick={() => void doImport(f.path)}
            title={f.path}
          >
            <i className={b.files === "audio" ? "pi pi-volume-up" : "pi pi-image"} />
            <span className="h3-grow h3-ell">{f.name}</span>
            {f.size != null && <span className="h3-muted h3-small">{Math.max(1, Math.round(f.size / 1024))} KB</span>}
          </div>
        ))}
        {res && !res.dirs.length && !(importing && files.length) && <div className="h3-empty-state">Empty folder.</div>}
        {res?.truncated && <div className="h3-muted h3-small h3-pad">The list was cut short: this folder holds a lot.</div>}
      </div>
      {importing && res && !filesListed && (
        <div className="h3-note">
          This server's folder browser lists folders only, not files. Type the file's full path below.
        </div>
      )}
      <div className="h3-row">
        <input
          className="h3-in h3-grow h3-mono"
          placeholder={importing ? `or type a ${forTrack ? "recording's" : forClip ? "file path inside the episode" : "file"} path on the ComfyUI machine` : "or type a folder path"}
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && typed.trim() && !importing) void go(typed.trim());
          }}
        />
        {!importing && <button className="h3-btn" disabled={!typed.trim()} onClick={() => void go(typed.trim())}>Go</button>}
        {!importing && (
          <button className="h3-btn" disabled={!typed.trim() || busyRoots} onClick={() => void addRoot(typed.trim())} title="Add the typed folder as a root without browsing to it">
            Add typed path
          </button>
        )}
        {importing && (
          <button className="h3-btn" disabled={!typed.trim() || busyImport || busyTrack} onClick={() => void doImport(typed.trim())}>
            {forTrack ? "Attach typed path" : forClip ? "Use typed path" : "Import typed path"}
          </button>
        )}
      </div>
      {!importing && importingSeries && newParent && (
        <div className="h3-col" style={{ gap: 4 }}>
          <div className="h3-h">Import a series into {newParent}</div>
          <div className="h3-row">
            <input
              className="h3-in h3-mono"
              style={{ width: 180 }}
              placeholder="show folder (optional)"
              value={showName}
              onChange={(e) => setShowName(e.target.value)}
            />
            <label className="h3-btn" title="The series config and the scripts, picked together">
              <i className="pi pi-file" /> Files…
              <input type="file" multiple accept=".json,.md,.txt" hidden
                     onChange={(e) => setSeriesFiles(Array.from(e.target.files ?? []))} />
            </label>
            <label className="h3-btn" title="A season's folder: each episode folder with its script and its own series.json">
              <i className="pi pi-folder" /> Folder…
              <input type="file" multiple hidden {...{ webkitdirectory: "", directory: "" }}
                     onChange={(e) => setSeriesFiles(Array.from(e.target.files ?? []))} />
            </label>
            <span className="h3-grow" />
            <button
              className="h3-btn h3-primary"
              disabled={!seriesFiles.length || busySeries}
              onClick={() => void importSeries(newParent, showName, seriesFiles).then((r) => r && setImportingSeries(false))}
            >
              <i className={busySeries ? "pi pi-spin pi-spinner" : "pi pi-check"} /> Import
            </button>
            <button className="h3-btn" onClick={() => setImportingSeries(false)}>Cancel</button>
          </div>
          <div className="h3-small h3-muted">
            Pick the series config (series.json) and the scripts together, or a season's folder in which each
            episode folder has its script and its own series.json (episodes that add a character carry their own).
            Each script becomes a folder named by its header (<span className="h3-mono">= ep02  Title</span> → ep02)
            {showName.trim() ? `, all in ${newParent}\\${showName.trim()}` : ""}; other .md files are left out.
            An episode already there is left alone. Nothing is built yet: open each and Build.
            {seriesFiles.length > 0 && ` — ${seriesFiles.length} file${seriesFiles.length === 1 ? "" : "s"} picked.`}
          </div>
        </div>
      )}
      {!importing && (
        <div className="h3-col" style={{ gap: 2 }}>
          <div className="h3-h">Project roots</div>
          {!roots.length && <div className="h3-muted h3-small">None yet. Browse to the folder that holds your shows (or one show), then Add as root.</div>}
          {roots.map((r) => (
            <div key={r} className="h3-row h3-small">
              <i className="pi pi-folder h3-muted" />
              <button className="h3-link h3-grow h3-ell" style={{ textAlign: "left" }} title="Browse here" onClick={() => void go(r)}>{r}</button>
              <button className="h3-btn h3-icon" title="Remove this root" disabled={busyRoots} onClick={() => confirm(`Stop looking for episodes in ${r}?`) && void removeRoot(r)}>✕</button>
            </div>
          ))}
          <div className="h3-muted h3-small">Episodes are found up to two levels below a root.</div>
        </div>
      )}
    </Dialog>
  );
}
