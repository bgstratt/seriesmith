// The timeline's Export menu: every export in one place, and the XML timeline
// asked of the server as `xml` (partial, never with titles).
import { createElement } from "react";
import { renderToString } from "react-dom/server";
import { beforeEach, describe, expect, it } from "vitest";
import { refreshEpisode, runExport } from "../src/actions";
import { CutMenu } from "../src/components/CutMenu";
import { ExportMenu } from "../src/components/ExportMenu";
import { setApi, setHost, type Host } from "../src/host";
import { createMockApi } from "../src/mock/mockApi";
import { initialState, store } from "../src/store";
import type { AssembleOptions } from "../src/types";

describe("the Export menu", () => {
  let EP: string;
  let calls: { partial: boolean; opts?: AssembleOptions }[];
  let toasts: string[];

  beforeEach(async () => {
    toasts = [];
    setHost({ on: () => () => {}, toast: (_k: string, title: string) => void toasts.push(title), show: () => {} } as unknown as Host);
    const api = createMockApi(() => {}, { latency: 0 });
    calls = [];
    api.assemble = async (_ep, _pass, partial, opts) => {
      calls.push({ partial, opts });
      return { ok: true, output: `renders_proxy/ep05.${opts?.xml ? "xml" : "mp4"}`, report: "" };
    };
    setApi(api);
    EP = (await api.episodes())[0].ep;
    store.set(initialState());
    store.set({ ep: EP, pass: "proxy" });
    await refreshEpisode(EP, "proxy");
  });

  it("holds every export, and Master; the Cut menu no longer has Master", () => {
    store.set({ exportMenu: { x: 1, y: 1 } });
    const html = renderToString(createElement(ExportMenu));
    for (const item of ["Export", "Export 2x", "Titles", "Titles 2x", "Premiere / Resolve XML", "Premiere / Resolve XML 2x", "Master…"]) {
      expect(html).toContain(`</i> ${item}</button>`);
    }
    store.set({ cutMenu: { x: 1, y: 1 } });
    expect(renderToString(createElement(CutMenu))).not.toContain("Master…");
  });

  it("asks for the XML as a partial cut, and says where it went", async () => {
    await runExport({ kind: "xml", upscaled: false });
    expect(calls).toEqual([{ partial: true, opts: { xml: true } }]);
    expect(toasts).toContain("Timeline written");
  });

  it("Export and Titles ask as they always did", async () => {
    await runExport({ kind: "export", upscaled: false });
    await runExport({ kind: "titles", upscaled: false });
    expect(calls).toEqual([{ partial: true, opts: undefined }, { partial: false, opts: { publish: true } }]);
  });
});
