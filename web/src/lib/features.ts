// The Features window's server side (GET /seriesmith/features, /features/sizes,
// POST /features/install, /features/cancel: seriesmith/server/features_views.py).
// Pure helpers and the calls; the window is components/FeaturesWindow.tsx.

import { api } from "../host";

export type ItemStatus = "installed" | "missing" | "restart" | "unknown";
export type FeatureStatus = ItemStatus | "partial" | "unavailable";

export interface FeatureItem {
  key: string;
  kind: "model" | "pack" | "link" | "pip" | "ffmpeg";
  name: string;
  folder?: string;
  url?: string;
  target?: string;
  where?: string;
  gated?: boolean;
  licence?: string;
  /** a node pack or Python package: you put it in (ComfyUI-Manager, pip), not seriesmith */
  manual?: boolean;
  /** how, while it's missing */
  how?: string;
  status: ItemStatus;
}

export interface Feature {
  id: string;
  group: string;
  label: string;
  about: string;
  items: FeatureItem[];
  restart: boolean;
  status: FeatureStatus;
}

export interface InstallTask {
  key: string;
  kind: string;
  name: string;
  folder?: string;
  status: "queued" | "running" | "done" | "failed" | "canceled";
  bytes: number;
  total: number | null;
  error: string | null;
  note: string | null;
}

export interface InstallJob {
  running: boolean;
  tasks: InstallTask[];
  restart: boolean;
}

export interface FeaturesView {
  groups: { id: string; label: string; about: string }[];
  features: Feature[];
  place: { root: string | null; custom_nodes: string | null; python: string | null; why_not: string | null };
  hf_token: boolean;
  job: InstallJob;
}

async function call<T>(path: string, body?: unknown): Promise<T> {
  const r = await api().fetch(path, body === undefined ? undefined : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error((data as { error?: string }).error ?? `HTTP ${r.status}`);
  return data as T;
}

export const getFeatures = () => call<FeaturesView>("/seriesmith/features");
export const getSizes = () => call<{ sizes: Record<string, number | null> }>("/seriesmith/features/sizes");
export const cancelInstall = () => call<{ job: InstallJob }>("/seriesmith/features/cancel", {});

export interface InstallAsk { features?: string[]; files?: string[]; classes?: string[] }
export const startInstall = (ask: InstallAsk) =>
  call<{ job: InstallJob; queued: string[]; skipped: string[] }>("/seriesmith/features/install", ask);

/** The items of a feature still to put in. */
export function toInstall(f: Feature): FeatureItem[] {
  return f.items.filter((i) => i.status !== "installed" && i.status !== "restart");
}

/** Of those, what seriesmith installs (files, ffmpeg, its own pack's link). */
export function installable(f: Feature): FeatureItem[] {
  return toInstall(f).filter((i) => !i.manual);
}

/** Of those, what you put in yourself, each with how. */
export function yours(f: Feature): FeatureItem[] {
  return toInstall(f).filter((i) => i.manual && i.how);
}

/** What the selected features still download, in bytes (each file once; null
 * when a size isn't known). */
export function downloadSize(features: Feature[], sizes: Record<string, number | null>): { bytes: number; unknown: number } {
  const seen = new Set<string>();
  let bytes = 0;
  let unknown = 0;
  for (const f of features) {
    for (const i of toInstall(f)) {
      if (seen.has(i.key)) continue;
      seen.add(i.key);
      if (i.kind !== "model" || !i.url) continue;
      const n = sizes[i.url];
      if (n == null) unknown += 1;
      else bytes += n;
    }
  }
  return { bytes, unknown };
}

export function fmtBytes(n: number): string {
  if (n >= 1e9) return `${(n / 1e9).toFixed(n >= 1e10 ? 0 : 1)} GB`;
  if (n >= 1e6) return `${Math.round(n / 1e6)} MB`;
  if (n >= 1e3) return `${Math.round(n / 1e3)} KB`;
  return `${n} B`;
}

export const STATUS_TEXT: Record<FeatureStatus, string> = {
  installed: "Installed",
  partial: "Partly installed",
  missing: "Not installed",
  restart: "Restart ComfyUI",
  unknown: "Can't tell",
  unavailable: "Not available",
};

/** One line for a feature's items, by kind: "4 files · 1 node pack". */
export function itemsLine(f: Feature): string {
  const n = (k: FeatureItem["kind"]) => f.items.filter((i) => i.kind === k).length;
  const parts: string[] = [];
  const files = n("model");
  if (files) parts.push(`${files} file${files === 1 ? "" : "s"}`);
  const packs = n("pack") + n("link");
  if (packs) parts.push(`${packs} node pack${packs === 1 ? "" : "s"}`);
  const pips = n("pip");
  if (pips) parts.push(`${pips} Python package${pips === 1 ? "" : "s"}`);
  if (n("ffmpeg")) parts.push("a download");
  return parts.join(" · ");
}
