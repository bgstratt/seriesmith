// Features: everything that can be added to this install (seriesmith/features.py),
// ticked to install: model files into ComfyUI's models folders, node packs into
// custom_nodes, Python packages, a full ffmpeg. What's installed already shows
// as such; the installer's progress is at the top while it runs. Opened from
// Settings, and by the What's missing window's Install buttons.

import { useEffect, useMemo, useState } from "react";
import { closeFeatures, loadTargets, openSettings } from "../actions";
import { useApp } from "../store";
import {
  STATUS_TEXT, cancelInstall, downloadSize, fmtBytes, getFeatures, getSizes, itemsLine, startInstall, toInstall,
  type Feature, type FeaturesView, type InstallJob, type InstallTask,
} from "../lib/features";
import { FloatingWindow, type Rect } from "./FloatingWindow";

function defaultRect(): Rect {
  const W = window.innerWidth || 1280;
  const H = window.innerHeight || 800;
  const w = Math.min(680, Math.max(360, W - 32));
  return { x: Math.max(0, Math.round((W - w) / 2)), y: 56, w, h: Math.max(360, Math.min(760, H - 100)) };
}

export function FeaturesWindow() {
  const open = useApp((s) => s.featuresOpen);
  if (!open) return null;
  return <FeaturesBody />;
}

function FeaturesBody() {
  const [view, setView] = useState<FeaturesView | null>(null);
  const [sizes, setSizes] = useState<Record<string, number | null>>({});
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [openRows, setOpenRows] = useState<Set<string>>(new Set());

  const load = () => getFeatures().then((v) => { setView(v); setError(null); }).catch((e) => setError((e as Error).message));
  useEffect(() => {
    void load();
    getSizes().then((r) => setSizes(r.sizes)).catch(() => { /* sizes are a nicety */ });
  }, []);
  // while it installs, ask how it's going; when it's done, readiness again
  const running = !!view?.job.running;
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => {
      getFeatures().then((v) => {
        setView(v);
        if (!v.job.running) void loadTargets(true);
      }).catch(() => { /* away for a moment */ });
    }, 1500);
    return () => clearInterval(t);
  }, [running]);

  const features = view?.features ?? [];
  const chosen = useMemo(() => features.filter((f) => picked.has(f.id)), [features, picked]);
  const size = downloadSize(chosen, sizes);
  const gatedPicked = chosen.some((f) => toInstall(f).some((i) => i.gated));

  function toggle(id: string) {
    const next = new Set(picked);
    if (next.has(id)) next.delete(id); else next.add(id);
    setPicked(next);
  }
  function toggleRow(id: string) {
    const next = new Set(openRows);
    if (next.has(id)) next.delete(id); else next.add(id);
    setOpenRows(next);
  }
  async function install() {
    setBusy(true);
    setError(null);
    try {
      const r = await startInstall({ features: [...picked] });
      if (r.skipped.length) setError(r.skipped.join("; "));
      setPicked(new Set());
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function cancel() {
    try {
      const r = await cancelInstall();
      setView((v) => (v ? { ...v, job: r.job } : v));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const head = (
    <>
      <i className="pi pi-box h3-muted" />
      <div className="h3-head-text">
        <span className="h3-win-title">Features</span>
        <span className="h3-small h3-muted">Add models, node packs and tools. Installed ones are ticked.</span>
      </div>
      <span className="h3-grow" />
      <button className="h3-btn" title="Check again what's installed" onClick={() => void load()}><i className="pi pi-refresh" /></button>
      <button className="h3-btn h3-icon" title="Close" onClick={closeFeatures}><i className="pi pi-times" /></button>
    </>
  );
  return (
    <FloatingWindow storageKey="seriesmith.features.rect" defaultRect={defaultRect} head={head} minW={340}>
      <div className="h3-cards" style={{ overflow: "auto", flex: "1 1 auto", minHeight: 0 }}>
        {!view && !error && <div className="h3-muted h3-pad">Looking at what's installed…</div>}
        {view?.place.why_not && <div className="h3-note h3-note-err">{view.place.why_not}</div>}
        {view && !view.place.why_not && view.place.root && (
          <div className="h3-small h3-muted">Installs into <span className="h3-mono">{view.place.root}</span></div>
        )}
        {view && view.job.tasks.length > 0 && <JobCard job={view.job} onCancel={() => void cancel()} />}
        {view?.groups.map((g) => {
          const fs = features.filter((f) => f.group === g.id);
          if (!fs.length) return null;
          return (
            <section key={g.id} className="h3-card">
              <div className="h3-card-head">
                <span className="h3-card-title h3-grow">{g.label}</span>
              </div>
              <span className="h3-small h3-muted">{g.about}</span>
              {fs.map((f) => (
                <FeatureRow key={f.id} f={f} sizes={sizes} checked={f.status === "installed" || picked.has(f.id)}
                  open={openRows.has(f.id)} onToggle={() => toggle(f.id)} onOpen={() => toggleRow(f.id)} />
              ))}
            </section>
          );
        })}
        {error && <div className="h3-note h3-note-err">{error}</div>}
      </div>
      <div className="h3-dialog-foot">
        <span className="h3-small h3-muted h3-grow">
          {picked.size === 0 ? "Tick what you want, then Install."
            : `${picked.size} selected${size.bytes ? ` · ${fmtBytes(size.bytes)} to download` : ""}${size.unknown ? ` (+${size.unknown} of unknown size)` : ""}`}
          {gatedPicked && !view?.hf_token && (
            <> · <a href="#" onClick={(e) => { e.preventDefault(); openSettings(true); }}>Hugging Face token needed</a></>
          )}
        </span>
        <button className="h3-btn h3-primary h3-big" disabled={busy || picked.size === 0 || !!view?.place.why_not} onClick={() => void install()}>
          {busy ? <i className="pi pi-spin pi-spinner" /> : <i className="pi pi-download" />} Install
        </button>
      </div>
    </FloatingWindow>
  );
}

function FeatureRow({ f, sizes, checked, open, onToggle, onOpen }: {
  f: Feature; sizes: Record<string, number | null>; checked: boolean; open: boolean; onToggle: () => void; onOpen: () => void;
}) {
  const installed = f.status === "installed";
  const left = downloadSize([f], sizes);
  const gated = toInstall(f).some((i) => i.gated);
  const chip = f.status === "installed" ? " h3-s-ok" : f.status === "restart" ? " h3-s-rendering" : "";
  return (
    <div className="h3-col" style={{ gap: 2, padding: "4px 0", borderTop: "1px solid var(--h3-border, #8882)" }}>
      <div className="h3-row" style={{ gap: 8 }}>
        <input type="checkbox" checked={checked} disabled={installed || f.status === "unavailable"} onChange={onToggle}
          aria-label={`Install ${f.label}`} />
        <b className="h3-grow h3-ell" title={f.label}>{f.label}</b>
        {!installed && left.bytes > 0 && <span className="h3-small h3-muted">{fmtBytes(left.bytes)}</span>}
        {gated && <span className="h3-status" title="Accept the licence on Hugging Face and set a token in Settings">gated</span>}
        <span className={`h3-status${chip}`}>{STATUS_TEXT[f.status]}</span>
        <button className="h3-btn h3-icon" title={open ? "Hide what's in it" : "What's in it"} onClick={onOpen}>
          <i className={open ? "pi pi-chevron-up" : "pi pi-chevron-down"} />
        </button>
      </div>
      <span className="h3-small h3-muted" style={{ paddingLeft: 24 }}>{f.about} <span className="h3-muted">({itemsLine(f)})</span></span>
      {open && (
        <ul className="h3-missing-list h3-small" style={{ paddingLeft: 40, margin: 0 }}>
          {f.items.map((i) => (
            <li key={i.key}>
              <span className="h3-mono">{i.name}</span>
              {i.folder && <span className="h3-muted"> → models/{i.folder}</span>}
              {i.kind === "pack" && <span className="h3-muted"> → custom_nodes</span>}
              {i.kind === "link" && <span className="h3-muted"> → linked into custom_nodes from this repo</span>}
              {i.kind === "pip" && <span className="h3-muted"> → pip, {i.where === "comfyui" ? "ComfyUI's Python" : i.where === "align" ? "align's Python" : "seriesmith's Python"}</span>}
              {i.url && sizes[i.url] != null && <span className="h3-muted"> · {fmtBytes(sizes[i.url]!)}</span>}
              {" "}<span className={i.status === "installed" ? "h3-ok" : "h3-muted"}>{i.status === "installed" ? "✓" : i.status === "restart" ? "(restart ComfyUI)" : ""}</span>
              {i.gated && i.status !== "installed" && i.licence && (
                <> · <a href={i.licence} target="_blank" rel="noopener noreferrer">accept the licence</a></>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function TaskLine({ t }: { t: InstallTask }) {
  const pct = t.total ? Math.min(100, Math.round((t.bytes / t.total) * 100)) : null;
  const icon = t.status === "done" ? "pi pi-check h3-ok" : t.status === "failed" ? "pi pi-times h3-err"
    : t.status === "running" ? "pi pi-spin pi-spinner" : t.status === "canceled" ? "pi pi-ban h3-muted" : "pi pi-clock h3-muted";
  return (
    <div className="h3-col" style={{ gap: 2 }}>
      <div className="h3-row h3-small" style={{ gap: 6 }}>
        <i className={icon} />
        <span className="h3-mono h3-ell h3-grow" title={t.name}>{t.name}</span>
        {t.status === "running" && t.total ? <span className="h3-muted">{fmtBytes(t.bytes)} / {fmtBytes(t.total)}</span> : null}
        {t.status === "done" && t.note && <span className="h3-muted h3-ell" title={t.note}>{t.note}</span>}
      </div>
      {t.status === "running" && pct != null && <div className="h3-progress"><div style={{ width: `${pct}%` }} /></div>}
      {t.error && <div className="h3-small h3-err" style={{ whiteSpace: "pre-wrap" }}>{t.error}</div>}
    </div>
  );
}

function JobCard({ job, onCancel }: { job: InstallJob; onCancel: () => void }) {
  const done = job.tasks.filter((t) => t.status === "done").length;
  return (
    <section className="h3-card">
      <div className="h3-card-head">
        <span className="h3-card-title h3-grow">
          {job.running ? `Installing… ${done} of ${job.tasks.length}` : `Installed ${done} of ${job.tasks.length}`}
        </span>
        {job.running && <button className="h3-btn" onClick={onCancel}><i className="pi pi-stop" /> Stop</button>}
      </div>
      {job.tasks.map((t) => <TaskLine key={t.key} t={t} />)}
      {job.restart && !job.running && (
        <div className="h3-note h3-note-info">Restart ComfyUI to load the new node packs.</div>
      )}
      {job.running && <span className="h3-small h3-muted">A stopped download resumes where it left off next time.</span>}
    </section>
  );
}
