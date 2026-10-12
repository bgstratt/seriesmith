// The standalone page (standalone.html, served by `seriesmith serve`): the
// editor without ComfyUI. Its host: the HTTP transport to the same API paths
// ComfyUI serves, events from the server's /ws, the editor's own toasts, and
// the page's layout -- the Shots / Refs sidebar, the docked viewer in the
// middle, the timeline along the bottom. The floating windows (inspector,
// dialogs, Issues, Script) float over it as they do in ComfyUI.

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { openJobs, openSettings, pushToast, setBackends, start } from "./actions";
import { SettingsWindow } from "./components/SettingsWindow";
import { createHttpApi, xhrUpload } from "./api";
import { Boundary } from "./components/ErrorBoundary";
import { dockWindow } from "./components/FloatingWindow";
import { BackendChoice, JobsButton, JobsWindow } from "./components/Jobs";
import { VIEWER_RECT_KEY } from "./components/Viewer";
import { setApi, setHost, type Host, type HostEvent, type Surface } from "./host";
import { store, type BackendInfo } from "./store";
import { injectStyles, mountOverlay, mountSurface } from "./surfaces";
import { installSplitters } from "./splitters";

// ---- events: the server's websocket, reconnecting -------------------------

const listeners = new Map<string, Set<(d: unknown) => void>>();
const status = document.getElementById("sm-conn");

function connect(wait = 500) {
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
  ws.onopen = () => {
    wait = 500;
    if (status) status.dataset.state = "on";
  };
  ws.onmessage = (m) => {
    try {
      const { type, data } = JSON.parse(m.data as string);
      listeners.get(type)?.forEach((cb) => cb(data));
    } catch {
      /* not ours */
    }
  };
  ws.onclose = () => {
    if (status) status.dataset.state = "off";
    setTimeout(() => connect(Math.min(wait * 2, 10000)), wait);
  };
}

// ---- the sidebar's tabs -----------------------------------------------------

type Tab = "shots" | "refs";
const TAB_KEY = "seriesmith.tab";

function showTab(tab: Tab) {
  for (const t of ["shots", "refs"] as Tab[]) {
    document.getElementById(`sm-${t}`)?.toggleAttribute("hidden", t !== tab);
    document.querySelector(`[data-tab="${t}"]`)?.classList.toggle("on", t === tab);
  }
  try {
    localStorage.setItem(TAB_KEY, tab);
  } catch {
    /* ignore */
  }
}

const host: Host = {
  on(event: HostEvent, cb) {
    if (!listeners.has(event)) listeners.set(event, new Set());
    listeners.get(event)!.add(cb);
    return () => listeners.get(event)?.delete(cb);
  },
  toast(severity, summary, detail, action) {
    pushToast({ severity, summary, detail, action }, action ? 12000 : severity === "error" ? 10000 : 4000);
  },
  show(surface: Surface) {
    // the timeline is always in view; Shots and Refs share the sidebar
    if (surface === "shots" || surface === "refs") showTab(surface);
  },
};

setHost(host);
setApi(
  createHttpApi({
    fetch: (p, init) => fetch(p, init),
    url: (p) => p,
    upload: (p, form, onProgress) => xhrUpload(p, form, onProgress),
  }),
);

for (const t of ["shots", "refs"] as Tab[]) {
  document.querySelector(`[data-tab="${t}"]`)?.addEventListener("click", () => showTab(t));
}
let first: Tab = "shots";
try {
  first = (localStorage.getItem(TAB_KEY) as Tab) || "shots";
} catch {
  /* ignore */
}
showTab(first === "refs" ? "refs" : "shots");

// simple mode: one panel, "Make"; the Refs tab waits in Advanced
let wasSimple: boolean | null = null;
function syncSimple() {
  const on = store.get().simple;
  if (on === wasSimple) return;
  wasSimple = on;
  const refsTab = document.querySelector<HTMLElement>('[data-tab="refs"]');
  const shotsTab = document.querySelector<HTMLElement>('[data-tab="shots"]');
  if (refsTab) refsTab.style.display = on ? "none" : "";
  if (shotsTab) shotsTab.textContent = on ? "Make" : "Shots";
  if (on) showTab("shots");
}
store.subscribe(syncSimple);
syncSimple();

mountSurface("shots", document.getElementById("sm-shots")!);
mountSurface("refs", document.getElementById("sm-refs")!);
mountSurface("timeline", document.getElementById("sm-timeline")!);
dockWindow(VIEWER_RECT_KEY, document.getElementById("sm-viewer"));
installSplitters(document.getElementById("sm")!);
mountOverlay();

// the top bar's queue controls, and the Jobs window over the page
injectStyles();
createRoot(document.getElementById("sm-queue")!).render(
  <StrictMode>
    <Boundary name="Queue">
      <BackendChoice />
      <JobsButton />
    </Boundary>
  </StrictMode>,
);
const jobsEl = document.createElement("div");
jobsEl.className = "h3-root";
document.body.appendChild(jobsEl);
createRoot(jobsEl).render(
  <StrictMode>
    <Boundary name="Jobs">
      <JobsWindow />
      <SettingsWindow server />
    </Boundary>
  </StrictMode>,
);

/** The backends renders can go to, and whether each answers (every 30 s). */
async function loadBackends() {
  try {
    const r = await fetch("/seriesmith/backends");
    if (r.ok) setBackends(((await r.json()) as { backends: BackendInfo[] }).backends);
  } catch {
    /* the server is away */
  }
}
void loadBackends();
setInterval(() => void loadBackends(), 30000);
// ?jobs opens the Jobs window (a link to the queue)
if (new URLSearchParams(location.search).has("jobs")) openJobs(true);

connect();
void start();

document.getElementById("sm-settings")?.addEventListener("click", () => openSettings(!store.get().settingsOpen));

document.getElementById("sm-theme")?.addEventListener("click", () => {
  const light = document.documentElement.classList.toggle("light");
  try {
    localStorage.setItem("seriesmith.theme", light ? "light" : "dark");
  } catch {
    /* ignore */
  }
});
