// @vitest-environment happy-dom
//
// The Refs tab's Effects (docs/SOUND.md phase 4): every shot with effects takes in the pass,
// picked or not, from GET /seriesmith/fx/shots; a row's takes fetched only when it opens
// (GET /seriesmith/fx), where another is picked into the pass's mix.
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { refreshEpisode } from "../src/actions";
import { SoundRefsSections } from "../src/components/SoundRefs";
import { setApi, setHost, type Host } from "../src/host";
import { createMockApi } from "../src/mock/mockApi";
import { currentMix, loadMix, mixSettled } from "../src/mixActions";
import { initialState, statusKey, store } from "../src/store";
import type { FxShot } from "../src/types";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

describe("the Refs tab's effects", () => {
  let root: Root;
  let el: HTMLDivElement;
  let EP: string;
  let shot: string;
  let asked: string[];

  beforeEach(async () => {
    setHost({ on: () => () => {}, toast: () => {}, show: () => {} } as Host);
    const api = createMockApi(() => {}, { latency: 0 });
    EP = (await api.episodes())[0].ep;
    asked = [];
    const takes = (s: string): FxShot => ({
      shot: s, pass: "proxy", cut_take: { pass: "proxy", take: 1 }, picked: 1, settings: { take: 1 },
      text: "hands tap a plastic cup on a formica table", text_from: "action",
      takes: [
        { take: 2, status: "ok", target: "ltx23_foley", path: `sound/fx/proxy/${s}/t02.wav`, picked: false, stale: null, source: { pass: "proxy", take: 1 } },
        { take: 1, status: "ok", target: "h3_foley", path: `sound/fx/proxy/${s}/t01.wav`, picked: true, stale: null, source: { pass: "proxy", take: 1 } },
      ],
    });
    setApi({
      ...api,
      fxShots: async () => {
        asked.push("shots");
        return { shots: [{ shot, takes: 2, ok: 2, queued: 0, failed: 0, picked: 1 }] };
      },
      fxTakes: async (_ep, _pass, s) => {
        asked.push(`takes:${s}`);
        return takes(s);
      },
    });
    store.set(initialState());
    store.set({ ep: EP, pass: "proxy" });
    await refreshEpisode(EP, "proxy");
    shot = store.get().status[statusKey(EP, "proxy")]!.shots[0].shot;
    await loadMix(EP, "proxy");
    el = document.createElement("div");
    document.body.appendChild(el);
    root = createRoot(el);
  });
  afterEach(() => {
    act(() => root.unmount());
    el.remove();
    store.set(initialState());
  });

  it("lists the shots, fetches a row's takes when it opens, and picks another", async () => {
    await act(async () => root.render(createElement(SoundRefsSections, { ep: EP })));
    await act(async () => {});
    const row = [...el.querySelectorAll<HTMLElement>(".h3-kf-shot")].find((r) => r.textContent?.includes(shot) && r.querySelector(".pi-bolt"))!;
    expect(row).toBeTruthy();
    expect(row.textContent).toContain("2/2 takes");
    expect(asked).toEqual(["shots"]);                                  // no takes until it opens
    await act(async () => row.querySelector<HTMLElement>(".h3-row")!.click());
    await act(async () => {});
    expect(asked).toContain(`takes:${shot}`);
    expect(row.textContent).toContain("From its action");
    expect(row.textContent).toContain("in the mix");
    const pick = [...row.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent === "Pick")!;
    expect(pick).toBeTruthy();
    await act(async () => pick.click());
    await mixSettled();
    expect(currentMix()!.mix.fx).toEqual({ [shot]: { take: 2 } });
  });
});
