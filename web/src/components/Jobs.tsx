// seriesmith's queue, on the standalone page (docs/DESIGN.md, "The queue"):
// the top bar's jobs button (running and queued counts, the current job's
// progress) and "Render on" choice, and the Jobs window -- every job by
// backend, with cancel, retry, move and pause, and each job's log.
//
// The queue lives in the server (GET /seriesmith/jobs); "seriesmith.job" and
// "seriesmith.queue" events keep this copy current.

import { useEffect, useState, useSyncExternalStore } from "react";
import { openJobs, setRenderBackend } from "../actions";
import { host } from "../host";
import { store, useApp } from "../store";
import { FloatingWindow } from "./FloatingWindow";

export interface QJob {
  id: string;
  kind: string;
  lane: string;
  title: string;
  info: Record<string, unknown>;
  status: "queued" | "running" | "succeeded" | "failed" | "canceled";
  progress: number;
  step: number | null;
  steps: number | null;
  created: number;
  started: number | null;
  finished: number | null;
  error: string;
  log: string[];
  can_retry: boolean;
}

interface Lane { paused: boolean; parallel: number; waiting: string[]; running: string[] }
interface Snapshot { jobs: QJob[]; lanes: Record<string, Lane>; paid?: { count: number; limit: number | null } }

// ---- a copy of the server's queue -------------------------------------------

let snap: Snapshot = { jobs: [], lanes: {} };
const subs = new Set<() => void>();
const notify = () => subs.forEach((f) => f());
let wired = false;

async function refresh() {
  try {
    const r = await fetch("/seriesmith/jobs");
    if (r.ok) {
      snap = (await r.json()) as Snapshot;
      notify();
    }
  } catch {
    /* the server is away: the dot in the top bar says so */
  }
}

function wire() {
  if (wired) return;
  wired = true;
  host().on("seriesmith.job", (d) => {
    const j = d as QJob;
    const jobs = snap.jobs.some((x) => x.id === j.id)
      ? snap.jobs.map((x) => (x.id === j.id ? j : x))
      : [j, ...snap.jobs];
    snap = { ...snap, jobs };
    notify();
    if (j.status === "queued" || j.status === "running") return;
    void refresh(); // a lane's lists moved
  });
  host().on("seriesmith.queue", () => void refresh());
  void refresh();
}

function useQueue(): Snapshot {
  wire();
  return useSyncExternalStore(
    (f) => {
      subs.add(f);
      return () => subs.delete(f);
    },
    () => snap,
  );
}

async function act(action: string, body: Record<string, unknown>) {
  try {
    const r = await fetch(`/seriesmith/jobs/${action}`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    const data = await r.json();
    if (!r.ok) host().toast("error", `Couldn't ${action} that job`, String(data.error ?? r.statusText));
    else {
      snap = data as Snapshot;
      notify();
    }
  } catch (e) {
    host().toast("error", `Couldn't ${action} that job`, String(e));
  }
}

function fmt(sec: number): string {
  const s = Math.max(0, Math.round(sec));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function elapsed(j: QJob, now: number): string {
  if (!j.started) return "";
  return fmt((j.finished ?? now) - j.started);
}

// ---- the top bar -------------------------------------------------------------

/** The jobs button: what is running and waiting, the current job's progress. */
export function JobsButton() {
  const q = useQueue();
  const running = q.jobs.filter((j) => j.status === "running");
  const queued = q.jobs.filter((j) => j.status === "queued").length;
  const failed = q.jobs.filter((j) => j.status === "failed").length;
  const cur = running[0];
  const label = running.length || queued
    ? `${running.length} running · ${queued} queued`
    : failed ? `${failed} failed` : "Jobs";
  return (
    <button className="sm-jobs-btn" onClick={() => openJobs(!store.get().jobsOpen)} title="seriesmith's queue">
      <i className={running.length ? "pi pi-spin pi-spinner" : "pi pi-list"} />
      <span>{label}</span>
      {cur && (
        <span className="sm-bar" title={`${cur.title}: ${Math.round(cur.progress * 100)}%`}>
          <span style={{ width: `${Math.round(cur.progress * 100)}%` }} />
        </span>
      )}
    </button>
  );
}

/** Where renders go this session, for the whole page. */
export function BackendChoice() {
  const backends = useApp((s) => s.backends);
  const chosen = useApp((s) => s.renderBackend);
  if (!backends || !backends.length) return null;
  return (
    <label className="sm-backend" title="Where renders from this page go (each shot's own: its target decides)">
      Render on
      <select value={chosen} onChange={(e) => setRenderBackend(e.target.value)}>
        <option value="">each shot's own</option>
        {backends.map((b) => (
          <option key={b.name} value={b.name} disabled={!!b.down} title={b.down ?? b.where}>
            {b.name}{b.down ? " (not answering)" : ""}
          </option>
        ))}
      </select>
    </label>
  );
}

// ---- the window --------------------------------------------------------------

export function JobsWindow() {
  const open = useApp((s) => s.jobsOpen);
  if (!open) return null;
  return <JobsBody />;
}

function JobsBody() {
  const q = useQueue();
  const [now, setNow] = useState(Date.now() / 1000);
  const [openLog, setOpenLog] = useState<string | null>(null);
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => clearInterval(t);
  }, []);
  const lanes = [...new Set([...Object.keys(q.lanes), ...q.jobs.map((j) => j.lane)])].sort();
  const paid = q.paid;
  const head = (
    <>
      <b className="h3-grow">Jobs</b>
      {paid && (paid.count > 0 || paid.limit != null) && (
        <span className={`h3-small ${paid.limit != null && paid.count >= paid.limit ? "h3-warn" : "h3-muted"}`}
          title="Runs sent to a paid backend (Comfy Cloud, Router, a deployment) since the server started; the limit is in Settings">
          paid runs {paid.count}{paid.limit != null ? ` of ${paid.limit}` : ""}
          {paid.count > 0 && (
            <button className="h3-link" style={{ marginLeft: 6 }} title="Start the count again"
              onClick={() => void act("paid-reset", {})}>reset</button>
          )}
        </span>
      )}
      <button className="h3-btn" onClick={() => void refresh()} title="Refresh"><i className="pi pi-refresh" /></button>
      <button className="h3-btn" onClick={() => openJobs(false)} title="Close"><i className="pi pi-times" /></button>
    </>
  );
  return (
    <FloatingWindow storageKey="seriesmith.jobs.rect" head={head}
                    defaultRect={() => ({ x: Math.max(0, window.innerWidth - 480), y: 48, w: 460, h: 520 })}>
      <div className="sm-jobs">
        {!q.jobs.length && <div className="h3-muted h3-small" style={{ padding: 12 }}>No jobs yet. Renders from this page queue here.</div>}
        {lanes.map((name) => {
          const lane = q.lanes[name];
          const jobs = q.jobs.filter((j) => j.lane === name);
          const waiting = lane?.waiting ?? [];
          return (
            <section key={name} className="sm-lane">
              <header>
                <b>{name}</b>
                <span className="h3-muted h3-small">
                  {lane ? (lane.parallel === 1 ? "one at a time" : `${lane.parallel} at once`) : ""}
                  {lane?.paused ? " · paused" : ""}
                </span>
                <span className="h3-grow" />
                {lane && (
                  <button className="h3-btn" onClick={() => void act("pause", { lane: name, paused: !lane.paused })}>
                    <i className={lane.paused ? "pi pi-play" : "pi pi-pause"} /> {lane.paused ? "Resume" : "Pause"}
                  </button>
                )}
              </header>
              {jobs.map((j) => {
                const w = waiting.indexOf(j.id);
                return (
                  <div key={j.id} className={`sm-job sm-${j.status}`}>
                    <div className="sm-job-row">
                      <span className="sm-job-title" title={j.id}>{j.title}</span>
                      <span className="h3-muted h3-small">
                        {j.status}{j.status === "running" && j.step && j.steps ? ` · step ${j.step}/${j.steps}` : ""}
                        {j.started ? ` · ${elapsed(j, now)}` : ""}
                      </span>
                      <span className="h3-grow" />
                      {j.status === "queued" && w > 0 && (
                        <button className="h3-btn" title="Earlier" onClick={() => void act("move", { id: j.id, index: w - 1 })}><i className="pi pi-arrow-up" /></button>
                      )}
                      {j.status === "queued" && w >= 0 && w < waiting.length - 1 && (
                        <button className="h3-btn" title="Later" onClick={() => void act("move", { id: j.id, index: w + 1 })}><i className="pi pi-arrow-down" /></button>
                      )}
                      {(j.status === "queued" || j.status === "running") && (
                        <button className="h3-btn" title="Cancel" onClick={() => void act("cancel", { id: j.id })}><i className="pi pi-times" /></button>
                      )}
                      {(j.status === "failed" || j.status === "canceled") && j.can_retry && (
                        <button className="h3-btn" title="Again, as a new take" onClick={() => void act("retry", { id: j.id })}><i className="pi pi-replay" /></button>
                      )}
                      <button className="h3-btn" title="Log" onClick={() => setOpenLog(openLog === j.id ? null : j.id)}><i className="pi pi-align-left" /></button>
                    </div>
                    {j.status === "running" && (
                      <div className="sm-bar wide"><span style={{ width: `${Math.round(j.progress * 100)}%` }} /></div>
                    )}
                    {j.error && <div className="h3-small" style={{ color: "var(--error-text)" }}>{j.error}</div>}
                    {openLog === j.id && (
                      <pre className="sm-log">{j.log.length ? j.log.join("\n") : "(nothing logged)"}</pre>
                    )}
                  </div>
                );
              })}
            </section>
          );
        })}
      </div>
    </FloatingWindow>
  );
}
