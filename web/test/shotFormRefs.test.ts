// @vitest-environment happy-dom
//
// The shot form's lists follow the series config: a location added while the form is open
// (the Refs tab writes series.json without telling the form) is offered as soon as the
// episode's refs change, without reopening the form or reloading the page.
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { loadRefs, refreshEpisode } from "../src/actions";
import { ShotFormWindow } from "../src/components/ShotForm";
import { setApi, setHost, type Host } from "../src/host";
import { createMockApi } from "../src/mock/mockApi";
import { initialState, statusKey, store } from "../src/store";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

describe("the shot form's places", () => {
  let root: Root;
  let el: HTMLDivElement;
  let EP: string;
  let api: ReturnType<typeof createMockApi>;

  beforeEach(async () => {
    setHost({ on: () => () => {}, toast: () => {}, show: () => {} } as unknown as Host);
    api = createMockApi(() => {}, { latency: 0 });
    setApi(api);
    EP = (await api.episodes())[0].ep;
    store.set(initialState());
    store.set({ ep: EP, pass: "proxy" });
    await refreshEpisode(EP, "proxy");
    await loadRefs(EP);
    el = document.createElement("div");
    document.body.appendChild(el);
    root = createRoot(el);
  });
  afterEach(() => {
    act(() => root.unmount());
    el.remove();
    store.set(initialState());
  });

  const places = async () => {
    const btn = [...el.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.title === "Pick a location by its plate")!;
    await act(async () => btn.click());
    const names = [...document.querySelectorAll<HTMLElement>(".sm-picture-picker .sm-pick-tile")].map((b) => b.textContent!.trim());
    await act(async () => btn.click());
    return names.join(" | ");
  };

  it("offers a location added while it's open, once the refs change", async () => {
    const shot = store.get().status[statusKey(EP, "proxy")]!.shots[0].shot;
    store.set({ shotForm: { shot, after: null } });
    await act(async () => root.render(createElement(ShotFormWindow)));
    await act(async () => {});
    expect(await places()).not.toContain("grass closeup");
    // the series config gains a location behind the form's back
    const doc = await api.source(EP, "series");
    const raw = JSON.parse(doc.text);
    raw.locations = { ...(raw.locations ?? {}), grass_closeup: { description: "the grass, close" } };
    await api.putSource({ ep: EP, file: "series", text: JSON.stringify(raw, null, 2), base_hash: doc.hash, rebuild: false });
    await act(async () => void (await loadRefs(EP)));
    await act(async () => store.set((s) => ({ refs: { ...s.refs, [EP]: [...(s.refs[EP] ?? [])] } })));
    await act(async () => {});
    expect(await places()).toContain("grass closeup");
  });
});
