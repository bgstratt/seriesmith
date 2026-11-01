// @vitest-environment happy-dom
//
// The timeline's sound lanes on the mock: the Sound toggle unfolds them (and
// is remembered), they draw the pass's mix (items as blocks, hits as markers
// coloured by kind), and a fader's mute is one edit of the mix.
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { refreshEpisode } from "../src/actions";
import { Timeline } from "../src/components/Timeline";
import { resetCutHistory } from "../src/cutActions";
import { setApi, setHost, type Host } from "../src/host";
import { createMockApi } from "../src/mock/mockApi";
import { currentMix, loadMix, mixSettled } from "../src/mixActions";
import { initialState, loadPrefs, savePrefs, statusKey, store } from "../src/store";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

describe("the sound lanes", () => {
  let root: Root;
  let el: HTMLDivElement;
  let EP: string;
  let api: ReturnType<typeof createMockApi>;

  beforeEach(async () => {
    setHost({ on: () => () => {}, toast: () => {}, show: () => {} } as Host);
    api = createMockApi(() => {}, { latency: 0 });
    setApi(api);
    EP = (await api.episodes())[0].ep;
    store.set(initialState());
    resetCutHistory();
    store.set({ ep: EP, pass: "proxy" });
    await refreshEpisode(EP, "proxy");
    const shots = store.get().status[statusKey(EP, "proxy")]!.shots;
    await api.putMix(EP, "proxy", {
      items: [{ id: "amb01", track: "ambience", path: "audio/room_tone.wav", in: { shot: shots[0].shot, frame: 0 }, out: { shot: shots[1].shot, frame: 10 }, loop: true }],
      hits: [{ id: "h01", name: "the door", at: { shot: shots[1].shot, frame: 4 }, kind: "drop" }],
    });
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

  it("the Sound toggle unfolds the lanes, and they draw the mix", async () => {
    await act(async () => root.render(createElement(Timeline)));
    expect(el.querySelector(".h3-snd")).toBeNull();
    const btn = [...el.querySelectorAll("button")].find((b) => b.textContent?.includes("Sound"))!;
    await act(async () => btn.click());
    expect(store.get().sound).toBe(true);
    expect(el.querySelectorAll(".h3-snd-lane")).toHaveLength(5);
    expect([...el.querySelectorAll(".h3-snd-name")].map((x) => x.textContent)).toEqual(["Dialogue", "Effects", "Ambience", "Music"]);
    expect(el.querySelector(".h3-snd-item.h3-snd-ambience")).not.toBeNull();
    const hit = el.querySelector(".h3-snd-hit")!;
    expect(hit.className).toContain("h3-hit-drop");
    expect(hit.textContent).toBe("the door");

    // mute the music: one edit of the mix
    const mute = el.querySelectorAll<HTMLButtonElement>(".h3-snd-head button[title='Mute']")[3];
    await act(async () => mute.click());
    await mixSettled();
    expect(currentMix()!.mix.tracks).toEqual({ music: { mute: true } });
    expect(store.get().cutUndo[statusKey(EP, "proxy")]?.undo).toBe("Mute music");
  });

  it("remembers whether the lanes are unfolded", () => {
    const m = new Map<string, string>();
    const kv = { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v) };
    savePrefs({ ep: "E", pass: "final", zoom: 40, sound: true }, kv);
    expect(loadPrefs(kv).sound).toBe(true);
    expect(initialState(loadPrefs(kv)).sound).toBe(true);
    expect(initialState({}).sound).toBe(false);
  });
});
