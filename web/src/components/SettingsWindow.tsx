// Settings: this machine's own (GET / PUT /seriesmith/settings, the standalone
// server's): the Comfy API key that turns on Comfy Cloud and Comfy Router,
// where the local ComfyUI is, and the deployments a model can render on. Never
// the series config's business, which is shared. A setting the environment
// gives (COMFY_API_KEY, ...) wins over the file, so it shows here but can't be
// changed here.

import { useEffect, useState } from "react";
import { loadTargets, openSettings, setBackends } from "../actions";
import { useApp } from "../store";
import type { BackendInfo } from "../store";
import { FloatingWindow } from "./FloatingWindow";
import { ModelOptions } from "./Targets";

interface SettingsView {
  settings: { local_url: string; comfyui_url: string; cloud_url: string; api_key: "set" | null; deployments: Record<string, string>; path: string | null; paid_limit?: number | null };
  file: string;
  from_env: Record<string, string>;
}

async function call(method: "GET" | "PUT", body?: unknown): Promise<SettingsView> {
  const r = await fetch("/seriesmith/settings", {
    method, headers: body ? { "Content-Type": "application/json" } : undefined, body: body ? JSON.stringify(body) : undefined,
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error((data as { error?: string }).error ?? `HTTP ${r.status}`);
  return data as SettingsView;
}

async function refreshBackends() {
  try {
    const r = await fetch("/seriesmith/backends");
    if (r.ok) setBackends(((await r.json()) as { backends: BackendInfo[] }).backends);
  } catch {
    /* the server is away */
  }
}

/** `server`: the standalone page, whose own server this is (Stop / Restart);
 * inside ComfyUI the server is ComfyUI's, so it has none. */
export function SettingsWindow({ server = false }: { server?: boolean }) {
  const open = useApp((s) => s.settingsOpen);
  if (!open) return null;
  return <SettingsBody server={server} />;
}

/** The standalone server: stopped (start it again from run_seriesmith.bat), or
 * restarted under that launcher, the page reloading once it answers again. */
function ServerSection() {
  const [state, setState] = useState<"" | "stopping" | "stopped" | "restarting" | "gone">("");
  const [err, setErr] = useState<string | null>(null);
  async function stop(restart: boolean) {
    if (!restart && !confirm("Stop seriesmith's server? Jobs on Router carry on and are picked up "
      + "when it starts again; start it with run_seriesmith.bat.")) return;
    setErr(null);
    setState(restart ? "restarting" : "stopping");
    try {
      const r = await fetch("/seriesmith/server/stop", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ restart }),
      });
      if (!r.ok) throw new Error(((await r.json().catch(() => ({}))) as { error?: string }).error || r.statusText);
    } catch (e) {
      setErr((e as Error).message);
      setState("");
      return;
    }
    if (!restart) {
      setState("stopped");
      return;
    }
    // back up (the launcher starts it again): reload onto the new server
    await new Promise((res) => setTimeout(res, 1500));
    for (let i = 0; i < 60; i++) {
      try {
        const r = await fetch("/seriesmith/config", { cache: "no-store" });
        if (r.ok) {
          location.reload();
          return;
        }
      } catch { /* not up yet */ }
      await new Promise((res) => setTimeout(res, 1000));
    }
    setState("gone");
  }
  return (
    <section className="h3-col" style={{ gap: 6 }}>
      <span className="h3-h">This server</span>
      <div className="h3-row h3-wrap" style={{ gap: 6 }}>
        <button className="h3-btn" disabled={!!state && state !== "gone"}
          title="Stop and start again (under run_seriesmith.bat): new code, settings read afresh. The page reloads."
          onClick={() => void stop(true)}>
          <i className={state === "restarting" ? "pi pi-spin pi-spinner" : "pi pi-refresh"} /> Restart
        </button>
        <button className="h3-btn" disabled={!!state && state !== "gone"} onClick={() => void stop(false)}>
          <i className="pi pi-power-off" /> Stop
        </button>
        <span className="h3-small h3-muted h3-grow">
          {state === "stopping" ? "Stopping…"
            : state === "stopped" ? "Stopped. Start it again with run_seriesmith.bat."
            : state === "restarting" ? "Restarting: the page reloads when it's back…"
            : state === "gone" ? "It didn't come back: was it started with run_seriesmith.bat? Start it again there."
            : "Jobs on Router carry on through a stop and are picked up on the next start."}
        </span>
      </div>
      {err && <div className="h3-small h3-err">{err}</div>}
    </section>
  );
}

function SettingsBody({ server }: { server: boolean }) {
  const targets = useApp((s) => s.targets);
  const [view, setView] = useState<SettingsView | null>(null);
  const [urls, setUrls] = useState({ comfyui_url: "", local_url: "", cloud_url: "" });
  const [key, setKey] = useState("");
  const [deps, setDeps] = useState<{ target: string; url: string }[]>([]);
  const [limit, setLimit] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const take = (v: SettingsView) => {
    setView(v);
    setUrls({ comfyui_url: v.settings.comfyui_url, local_url: v.settings.local_url, cloud_url: v.settings.cloud_url });
    setDeps(Object.entries(v.settings.deployments).map(([target, url]) => ({ target, url })));
    setLimit(v.settings.paid_limit == null ? "" : String(v.settings.paid_limit));
    setKey("");
  };
  useEffect(() => {
    void loadTargets();
    call("GET").then(take).catch((e) => setError((e as Error).message));
  }, []);

  async function save(extra: Record<string, unknown> = {}, what = "Saved") {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      const body: Record<string, unknown> = { ...extra };
      for (const k of ["comfyui_url", "local_url", "cloud_url"] as const) if (!view?.from_env[k]) body[k] = urls[k];
      body.deployments = Object.fromEntries(deps.filter((d) => d.target && d.url.trim()).map((d) => [d.target, d.url.trim()]));
      if (key.trim() && !view?.from_env.api_key) body.api_key = key.trim();
      body.paid_limit = limit.trim() === "" ? null : Math.max(0, Math.floor(Number(limit)));
      take(await call("PUT", body));
      await refreshBackends();
      setNote(what);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const env = view?.from_env ?? {};
  const video = (targets?.targets ?? []).filter((t) => t.kind === "video" && !t.draft);
  const head = (
    <>
      <i className="pi pi-cog" />
      <b className="h3-grow">Settings</b>
      <button className="h3-btn h3-icon" title="Close" onClick={() => openSettings(false)}><i className="pi pi-times" /></button>
    </>
  );
  const url = (k: "comfyui_url" | "local_url" | "cloud_url", label: string, help: string) => (
    <div className="h3-col" style={{ gap: 2 }}>
      <span className="h3-small"><b>{label}</b></span>
      <input className="h3-in h3-mono" value={urls[k]} disabled={!!env[k]} onChange={(e) => setUrls({ ...urls, [k]: e.target.value })} />
      <span className="h3-small h3-muted">{env[k] ? `Set by the environment (${env[k]}): change it there.` : help}</span>
    </div>
  );

  return (
    <FloatingWindow storageKey="seriesmith.settings.rect" head={head}
      defaultRect={() => ({ x: Math.max(16, Math.round((window.innerWidth - 560) / 2)), y: 60, w: 560, h: Math.min(680, window.innerHeight - 100) })}>
      <div className="h3-col" style={{ padding: 12, gap: 14, overflow: "auto", height: "100%" }}>
        <div className="h3-small h3-muted">
          This machine's settings, not the series': where renders can run. Kept in{" "}
          <span className="h3-mono">{view?.file ?? "…"}</span>.
        </div>

        <section className="h3-col" style={{ gap: 6 }}>
          <span className="h3-h">Comfy account</span>
          <div className="h3-col" style={{ gap: 2 }}>
            <span className="h3-small"><b>API key</b> {view && (
              <span className={view.settings.api_key ? "h3-ok" : "h3-muted"}>· {view.settings.api_key ? "set" : "not set"}</span>
            )}</span>
            {env.api_key ? (
              <span className="h3-small h3-muted">Set by the environment ({env.api_key}): change it there.</span>
            ) : (
              <div className="h3-row" style={{ gap: 4 }}>
                <input className="h3-in h3-grow h3-mono" type="password" autoComplete="off" value={key}
                  placeholder={view?.settings.api_key ? "a new key replaces the one saved" : "comfyui-…"}
                  onChange={(e) => setKey(e.target.value)} />
                {view?.settings.api_key && (
                  <button className="h3-btn" disabled={busy} onClick={() => {
                    if (window.confirm("Remove the saved API key? Comfy Cloud and Comfy Router stop until a key is set again.")) void save({ api_key: null }, "Key removed");
                  }}>Remove</button>
                )}
              </div>
            )}
            <span className="h3-small h3-muted">
              From your Comfy account (platform.comfy.org, API keys). It turns on Comfy Cloud (any graph, on Comfy's GPUs) and
              Comfy Router (hosted models: Seedance, Krea 2, ...), which uploads its input pictures through Cloud. Paid use is billed to that account.
            </span>
          </div>
          {url("cloud_url", "Comfy Cloud address", "Leave it unless Comfy tells you otherwise.")}
          <div className="h3-col" style={{ gap: 2 }}>
            <span className="h3-small"><b>Paid runs per session</b></span>
            <input className="h3-in" type="number" min={0} step={1} style={{ width: 120 }} value={limit}
              placeholder="no limit" onChange={(e) => setLimit(e.target.value)} />
            <span className="h3-small h3-muted">
              The most runs on Comfy Cloud, Router or a deployment the server sends before it stops and asks you to raise
              this (or reset the count in Jobs). Empty: no limit. A batch of paid renders asks before it goes either way.
            </span>
          </div>
        </section>

        <section className="h3-col" style={{ gap: 6 }}>
          <span className="h3-h">This computer</span>
          {url("comfyui_url", "ComfyUI", "Your ComfyUI: model lists and node checks come from it.")}
          {url("local_url", "comfy-api-proxy", "What local renders are sent to: started beside your ComfyUI when it isn't running.")}
        </section>

        <section className="h3-col" style={{ gap: 6 }}>
          <span className="h3-h">Deployments</span>
          <span className="h3-small h3-muted">
            A model built into a Comfy deployment of its own (its address ends .run.comfy.app). Each shows up in Render on as
            deployment:&lt;model&gt;; it uses the API key above.
          </span>
          {deps.map((d, i) => (
            <div key={i} className="h3-row" style={{ gap: 4 }}>
              <select className="h3-in" value={d.target} onChange={(e) => setDeps(deps.map((x, j) => (j === i ? { ...x, target: e.target.value } : x)))}>
                <option value="">a model…</option>
                <ModelOptions targets={video} />
                {d.target && !video.some((t) => t.id === d.target) && <option value={d.target}>{d.target}</option>}
              </select>
              <input className="h3-in h3-grow h3-mono" value={d.url} placeholder="https://….run.comfy.app"
                onChange={(e) => setDeps(deps.map((x, j) => (j === i ? { ...x, url: e.target.value } : x)))} />
              <button className="h3-link" title="Remove" onClick={() => setDeps(deps.filter((_, j) => j !== i))}>×</button>
            </div>
          ))}
          <div><button className="h3-btn" onClick={() => setDeps([...deps, { target: "", url: "" }])}>+ Deployment</button></div>
        </section>

        {server && <ServerSection />}

        {error && <div className="h3-err">{error}</div>}
      </div>
      <div className="h3-row" style={{ padding: "6px 10px", borderTop: "1px solid var(--h3-border)" }}>
        <span className="h3-small h3-muted h3-grow">{note ?? "Saving applies at once: Render on lists what is set up."}</span>
        <button className="h3-btn h3-primary" disabled={busy || !view} onClick={() => void save()}>
          {busy ? <i className="pi pi-spin pi-spinner" /> : <i className="pi pi-save" />} Save
        </button>
      </div>
    </FloatingWindow>
  );
}
