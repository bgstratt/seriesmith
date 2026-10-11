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

interface SettingsView {
  settings: { local_url: string; comfyui_url: string; cloud_url: string; api_key: "set" | null; deployments: Record<string, string>; path: string | null };
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

export function SettingsWindow() {
  const open = useApp((s) => s.settingsOpen);
  if (!open) return null;
  return <SettingsBody />;
}

function SettingsBody() {
  const targets = useApp((s) => s.targets);
  const [view, setView] = useState<SettingsView | null>(null);
  const [urls, setUrls] = useState({ comfyui_url: "", local_url: "", cloud_url: "" });
  const [key, setKey] = useState("");
  const [deps, setDeps] = useState<{ target: string; url: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const take = (v: SettingsView) => {
    setView(v);
    setUrls({ comfyui_url: v.settings.comfyui_url, local_url: v.settings.local_url, cloud_url: v.settings.cloud_url });
    setDeps(Object.entries(v.settings.deployments).map(([target, url]) => ({ target, url })));
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
                {video.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
                {d.target && !video.some((t) => t.id === d.target) && <option value={d.target}>{d.target}</option>}
              </select>
              <input className="h3-in h3-grow h3-mono" value={d.url} placeholder="https://….run.comfy.app"
                onChange={(e) => setDeps(deps.map((x, j) => (j === i ? { ...x, url: e.target.value } : x)))} />
              <button className="h3-link" title="Remove" onClick={() => setDeps(deps.filter((_, j) => j !== i))}>×</button>
            </div>
          ))}
          <div><button className="h3-btn" onClick={() => setDeps([...deps, { target: "", url: "" }])}>+ Deployment</button></div>
        </section>

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
