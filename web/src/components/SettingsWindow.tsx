// Settings: this machine's own (GET / PUT /seriesmith/settings, the standalone
// server's): the Comfy API key that turns on Comfy Cloud and Comfy Router,
// where the local ComfyUI is (and whether renders go to it through
// comfy-api-proxy), the models a series naming none renders on (found
// installed, or picked here), and the deployments a model can render on. Never
// the series config's business, which is shared. A setting the environment
// gives (COMFY_API_KEY, ...) wins over the file, so it shows here but can't be
// changed here.

import { useEffect, useState } from "react";
import { loadTargets, openFeatures, openSettings, setBackends } from "../actions";
import { useApp } from "../store";
import type { BackendInfo } from "../store";
import { FloatingWindow } from "./FloatingWindow";
import { ModelOptions } from "./Targets";

interface SettingsView {
  settings: {
    local_url: string; comfyui_url: string; cloud_url: string; api_key: "set" | null; deployments: Record<string, string>;
    path: string | null; paid_limit?: number | null; local_via?: "comfyui" | "proxy";
    hf_token?: "set" | null; ffmpeg_dir?: string | null; comfyui_dir?: string | null;
    default_targets?: Record<string, string>; detected_targets?: Record<string, string>;
  };
  file: string;
  from_env: Record<string, string>;
  /** comfy-sdk, which Cloud and Router run on: installed when a key is set */
  sdk?: SdkState;
}

interface SdkState {
  status: "ready" | "missing" | "installing" | "failed";
  error: string | null;
  command: string;
  python: string;
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

/** Whether the backends of one kind answer, as a dot and a word (null: none set up). */
function KindStatus({ kinds, ok, none }: { kinds: string[]; ok: string; none?: string }) {
  const backends = useApp((s) => s.backends);
  const of = (backends ?? []).filter((b) => kinds.includes(b.kind) || kinds.includes(b.name));
  if (!backends) return null;
  if (!of.length) return none ? <span className="h3-status">{none}</span> : null;
  const down = of.find((b) => b.down);
  return down
    ? <span className="h3-status h3-s-failed" title={down.down ?? ""}>{down.name} not answering</span>
    : <span className="h3-status h3-s-ok">{ok}</span>;
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
    <section className="h3-card">
      <div className="h3-card-head">
        <span className="h3-card-title h3-grow">This server</span>
        <span className="h3-small h3-muted">{location.host}</span>
      </div>
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
  const [hfToken, setHfToken] = useState("");
  const [dirs, setDirs] = useState({ ffmpeg_dir: "", comfyui_dir: "" });
  const [deps, setDeps] = useState<{ target: string; url: string }[]>([]);
  const [limit, setLimit] = useState("");
  const [viaProxy, setViaProxy] = useState(false);
  const [defaults, setDefaults] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [sdk, setSdk] = useState<SdkState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const take = (v: SettingsView) => {
    setView(v);
    setUrls({ comfyui_url: v.settings.comfyui_url, local_url: v.settings.local_url, cloud_url: v.settings.cloud_url });
    setDeps(Object.entries(v.settings.deployments).map(([target, url]) => ({ target, url })));
    setLimit(v.settings.paid_limit == null ? "" : String(v.settings.paid_limit));
    setViaProxy(v.settings.local_via === "proxy");
    setDefaults({ ...(v.settings.default_targets ?? {}) });
    if (v.sdk) setSdk(v.sdk);
    setKey("");
    setHfToken("");
    setDirs({ ffmpeg_dir: v.settings.ffmpeg_dir ?? "", comfyui_dir: v.settings.comfyui_dir ?? "" });
  };
  // while comfy-sdk installs, ask how it's going; once it's in, Cloud and Router answer
  useEffect(() => {
    if (sdk?.status !== "installing") return;
    const t = setInterval(() => {
      call("GET").then((v) => {
        if (v.sdk) setSdk(v.sdk);
        if (v.sdk?.status !== "installing") void refreshBackends();
      }).catch(() => { /* the server is away */ });
    }, 2000);
    return () => clearInterval(t);
  }, [sdk?.status]);
  async function installSdk() {
    setError(null);
    try {
      const r = await fetch("/seriesmith/sdk/install", { method: "POST" });
      const data = (await r.json()) as { sdk?: SdkState; error?: string };
      if (!r.ok) throw new Error(data.error ?? `HTTP ${r.status}`);
      if (data.sdk) setSdk(data.sdk);
    } catch (e) {
      setError((e as Error).message);
    }
  }
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
      if (hfToken.trim() && !view?.from_env.hf_token) body.hf_token = hfToken.trim();
      for (const k of ["ffmpeg_dir", "comfyui_dir"] as const) body[k] = dirs[k].trim() || null;
      body.paid_limit = limit.trim() === "" ? null : Math.max(0, Math.floor(Number(limit)));
      if (!view?.from_env.local_via) body.local_via = viaProxy ? "proxy" : null;
      body.default_targets = Object.fromEntries(Object.entries(defaults).filter(([, v]) => v));
      take(await call("PUT", body));
      await refreshBackends();
      void loadTargets(true);
      setNote(what);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const env = view?.from_env ?? {};
  const video = (targets?.targets ?? []).filter((t) => t.kind === "video" && !t.draft);
  const images = (targets?.targets ?? []).filter((t) => t.kind === "image" && !t.draft);
  const detected = view?.settings.detected_targets ?? {};
  const labelOf = (id: string | undefined) => (targets?.targets ?? []).find((t) => t.id === id)?.label || id || "";
  const defaultPick = (kind: "video" | "image", list: typeof video, builtin: string) => (
    <>
      <label htmlFor={`sm-set-def-${kind}`}>{kind === "video" ? "Video model" : "Picture model"}</label>
      <select id={`sm-set-def-${kind}`} className="h3-in" value={defaults[kind] ?? ""}
        onChange={(e) => setDefaults({ ...defaults, [kind]: e.target.value })}>
        <option value="">{detected[kind] ? `What's installed: ${labelOf(detected[kind])}` : `Built-in: ${labelOf(builtin)}`}</option>
        <ModelOptions targets={list} />
      </select>
    </>
  );
  const head = (
    <>
      <div className="h3-head-text">
        <span className="h3-win-title">Settings</span>
        <span className="h3-small h3-muted">This computer's: where renders can run. A show's own are in Series settings.</span>
      </div>
      <button className="h3-btn h3-icon" title="Close" onClick={() => openSettings(false)}><i className="pi pi-times" /></button>
    </>
  );
  const url = (k: "comfyui_url" | "local_url" | "cloud_url", label: string, help: string) => (
    <>
      <label htmlFor={`sm-set-${k}`} title={help}>{label}</label>
      <div className="h3-col" style={{ gap: 2 }}>
        <input id={`sm-set-${k}`} className="h3-in h3-mono" value={urls[k]} disabled={!!env[k]} onChange={(e) => setUrls({ ...urls, [k]: e.target.value })} />
        {env[k] && <span className="h3-small h3-muted">Set by the environment ({env[k]}): change it there.</span>}
      </div>
    </>
  );

  return (
    <FloatingWindow storageKey="seriesmith.settings.rect" head={head}
      defaultRect={() => ({ x: Math.max(16, Math.round((window.innerWidth - 560) / 2)), y: 60, w: 560, h: Math.min(680, window.innerHeight - 100) })}>
      <div className="h3-cards" style={{ overflow: "auto", flex: "1 1 auto", minHeight: 0 }}>
        <section className="h3-card">
          <div className="h3-card-head">
            <span className="h3-card-title h3-grow">This computer</span>
            <KindStatus kinds={["local"]} ok="ComfyUI answering" />
          </div>
          <div className="h3-form">
            {url("comfyui_url", "ComfyUI", "Your ComfyUI: local renders go to it, and model lists and node checks come from it.")}
            {defaultPick("video", video, "minimax_h3_ref2va")}
            {defaultPick("image", images, "krea2")}
          </div>
          <span className="h3-small h3-muted">
            Local renders go straight to ComfyUI. A series that names no model renders on the ones above: what seriesmith
            found installed in ComfyUI unless you pick one.
          </span>
          <div className="h3-row h3-wrap" style={{ gap: 8 }}>
            <button className="h3-btn" onClick={() => openFeatures(true)}>
              <i className="pi pi-box" /> Features…
            </button>
            <span className="h3-small h3-muted">Add models, node packs and tools: H3 at full quality, voices, upscale, post, ffmpeg.</span>
          </div>
          <details open={!!(view?.settings.ffmpeg_dir || view?.settings.comfyui_dir)}>
            <summary className="h3-small">Folders (ffmpeg, ComfyUI)</summary>
            <div className="h3-form" style={{ marginTop: 6 }}>
              <label htmlFor="sm-set-ffmpeg" title="A folder holding your own ffmpeg and ffprobe: used before anything else">ffmpeg folder</label>
              <input id="sm-set-ffmpeg" className="h3-in h3-mono" value={dirs.ffmpeg_dir} placeholder="empty: found by itself"
                onChange={(e) => setDirs({ ...dirs, ffmpeg_dir: e.target.value })} />
              <label htmlFor="sm-set-comfydir" title="The folder with ComfyUI's main.py, for Features to install into when it can't ask ComfyUI">ComfyUI folder</label>
              <input id="sm-set-comfydir" className="h3-in h3-mono" value={dirs.comfyui_dir} placeholder="empty: asked of ComfyUI"
                onChange={(e) => setDirs({ ...dirs, comfyui_dir: e.target.value })} />
            </div>
          </details>
          <details open={viaProxy}>
            <summary className="h3-small">Through comfy-api-proxy (advanced)</summary>
            <label className="h3-row h3-small" style={{ gap: 6, marginTop: 6 }}>
              <input type="checkbox" checked={viaProxy} disabled={!!env.local_via} onChange={(e) => setViaProxy(e.target.checked)} />
              Send local renders through comfy-api-proxy (pip install comfy-api-proxy; started beside ComfyUI)
            </label>
            {viaProxy && <div className="h3-form" style={{ marginTop: 6 }}>{url("local_url", "comfy-api-proxy", "Where the proxy answers.")}</div>}
          </details>
        </section>

        <section className="h3-card">
          <div className="h3-card-head">
            <span className="h3-card-title h3-grow">Comfy account</span>
            {view && (
              <span className={`h3-status${view.settings.api_key ? " h3-s-ok" : ""}`}>
                {view.settings.api_key ? "key set · Cloud and Router" : "no key"}
              </span>
            )}
          </div>
          <div className="h3-form">
            <label htmlFor="sm-set-key">API key</label>
            {env.api_key ? (
              <span className="h3-small h3-muted">Set by the environment ({env.api_key}): change it there.</span>
            ) : (
              <div className="h3-row" style={{ gap: 4 }}>
                <input id="sm-set-key" className="h3-in h3-grow h3-mono" type="password" autoComplete="off" value={key}
                  placeholder={view?.settings.api_key ? "a new key replaces the one saved" : "comfyui-…"}
                  onChange={(e) => setKey(e.target.value)} />
                {view?.settings.api_key && (
                  <button className="h3-btn" disabled={busy} onClick={() => {
                    if (window.confirm("Remove the saved API key? Comfy Cloud and Comfy Router stop until a key is set again.")) void save({ api_key: null }, "Key removed");
                  }}>Remove</button>
                )}
              </div>
            )}
            <label htmlFor="sm-set-hf" title="For the gated downloads (FLUX, LTX-2.5) in Features: huggingface.co, Settings, Access Tokens (read)">Hugging Face token</label>
            {env.hf_token ? (
              <span className="h3-small h3-muted">Set by the environment ({env.hf_token}): change it there.</span>
            ) : (
              <div className="h3-row" style={{ gap: 4 }}>
                <input id="sm-set-hf" className="h3-in h3-grow h3-mono" type="password" autoComplete="off" value={hfToken}
                  placeholder={view?.settings.hf_token ? "a new token replaces the one saved" : "hf_… (for gated model downloads)"}
                  onChange={(e) => setHfToken(e.target.value)} />
                {view?.settings.hf_token && (
                  <button className="h3-btn" disabled={busy} onClick={() => void save({ hf_token: null }, "Token removed")}>Remove</button>
                )}
              </div>
            )}
            <label htmlFor="sm-set-limit">Paid runs</label>
            <div className="h3-row h3-wrap" style={{ gap: 8 }}>
              <input id="sm-set-limit" className="h3-in" type="number" min={0} step={1} style={{ width: 90 }} value={limit}
                placeholder="no limit" onChange={(e) => setLimit(e.target.value)} />
              <span className="h3-small h3-muted">a session, then it stops and asks</span>
            </div>
          </div>
          {view?.settings.api_key && sdk && sdk.status !== "ready" && (
            <div className="h3-col" style={{ gap: 4 }}>
              <div className="h3-row h3-wrap" style={{ gap: 8 }}>
                <span className={`h3-status${sdk.status === "failed" ? " h3-s-failed" : ""}`}>
                  {sdk.status === "installing" ? <><i className="pi pi-spin pi-spinner" /> Installing Comfy's SDK for Cloud and Router…</>
                    : sdk.status === "failed" ? "Installing Comfy's SDK failed"
                    : "Cloud and Router need Comfy's SDK"}
                </span>
                {sdk.status !== "installing" && (
                  <button className="h3-btn" onClick={() => void installSdk()}>
                    <i className="pi pi-download" /> {sdk.status === "failed" ? "Try again" : "Install"}
                  </button>
                )}
              </div>
              {sdk.status === "failed" && sdk.error && <pre className="h3-small h3-err" style={{ whiteSpace: "pre-wrap", margin: 0 }}>{sdk.error}</pre>}
              {sdk.status !== "installing" && (
                <span className="h3-small h3-muted">Or run it yourself: <span className="h3-mono">{sdk.command}</span></span>
              )}
            </div>
          )}
          <span className="h3-small h3-muted">
            From your Comfy account (platform.comfy.org, API keys). It turns on Comfy Cloud (any graph, on Comfy's GPUs) and
            Comfy Router (hosted models: Seedance, Krea 2, ...), which uploads its input pictures through Cloud. Paid use is billed
            to that account. The paid-run limit counts runs on Cloud, Router or a deployment; empty: no limit (reset the count in Jobs).
          </span>
          <details>
            <summary className="h3-small">Comfy Cloud address (leave it unless told otherwise)</summary>
            <div className="h3-form" style={{ marginTop: 6 }}>
              {url("cloud_url", "Address", "Leave it unless Comfy tells you otherwise.")}
            </div>
          </details>
        </section>

        <section className="h3-card">
          <div className="h3-card-head">
            <span className="h3-card-title h3-grow">Deployments</span>
            <KindStatus kinds={["deployment"]} ok="answering" />
            <button className="h3-btn h3-add" onClick={() => setDeps([...deps, { target: "", url: "" }])}>+ Deployment</button>
          </div>
          {deps.map((d, i) => (
            <div key={i} className="h3-row" style={{ gap: 4 }}>
              <select className="h3-in" aria-label="The model" value={d.target} onChange={(e) => setDeps(deps.map((x, j) => (j === i ? { ...x, target: e.target.value } : x)))}>
                <option value="">a model…</option>
                <ModelOptions targets={video} />
                {d.target && !video.some((t) => t.id === d.target) && <option value={d.target}>{d.target}</option>}
              </select>
              <input className="h3-in h3-grow h3-mono" aria-label="Its address" value={d.url} placeholder="https://….run.comfy.app"
                onChange={(e) => setDeps(deps.map((x, j) => (j === i ? { ...x, url: e.target.value } : x)))} />
              <button className="h3-btn h3-icon" title="Remove" onClick={() => setDeps(deps.filter((_, j) => j !== i))}><i className="pi pi-times" /></button>
            </div>
          ))}
          <span className="h3-small h3-muted">
            A model built into a Comfy deployment of its own (its address ends .run.comfy.app). Each shows up in Render on as
            deployment:&lt;model&gt;; it uses the API key above.
          </span>
        </section>

        {/* only on the PC itself: the server refuses a stop from another device (no password
            on the network), so the buttons aren't offered there */}
        {server && ["127.0.0.1", "localhost", "[::1]", "::1"].includes(location.hostname) && <ServerSection />}

        {error && <div className="h3-err">{error}</div>}
        <span className="h3-small h3-muted">Kept in <span className="h3-mono">{view?.file ?? "…"}</span>.</span>
      </div>
      <div className="h3-dialog-foot">
        <span className="h3-small h3-muted h3-grow">{note ?? "Saving applies at once: Render on lists what is set up."}</span>
        <button className="h3-btn h3-primary h3-big" disabled={busy || !view} onClick={() => void save()}>
          {busy ? <i className="pi pi-spin pi-spinner" /> : <i className="pi pi-save" />} Save
        </button>
      </div>
    </FloatingWindow>
  );
}
