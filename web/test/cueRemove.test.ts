// @vitest-environment happy-dom
//
// Taking a cue out (docs/SCORING.md "Muting or deleting a cue"): its item's "plays in the mix"
// on the Refs tab's Music row (an undoable mix edit: `mute`), silent in Play all; and "Delete
// cue…" (DELETE /seriesmith/cue) after a confirm, the cue list and mix fetched again and the
// cue window showing it back on the spotting sheet.
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { refreshEpisode } from "../src/actions";
import { SoundRefsSections } from "../src/components/SoundRefs";
import { deleteCue, deleteCueAsk, loadCues, openCue } from "../src/cueActions";
import { resetCutHistory, undoCut } from "../src/cutActions";
import { setApi, setHost, type Host } from "../src/host";
import { playPlan } from "../src/lib/mix";
import { createMockApi } from "../src/mock/mockApi";
import { currentMix, loadMix, mixSettled } from "../src/mixActions";
import { initialState, store } from "../src/store";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

describe("taking a cue out", () => {
  let root: Root;
  let el: HTMLDivElement;
  let EP: string;
  let api: ReturnType<typeof createMockApi>;
  let deleted: string[];

  beforeEach(async () => {
    setHost({ on: () => () => {}, toast: () => {}, show: () => {} } as Host);
    api = createMockApi(() => {}, { latency: 0, cueDemo: true });
    EP = (await api.episodes())[0].ep;
    deleted = [];
    resetCutHistory();
    setApi({
      ...api,
      deleteCue: async (ep, cue) => {
        deleted.push(cue);
        return api.deleteCue(ep, cue);
      },
    });
    store.set(initialState());
    store.set({ ep: EP, pass: "proxy" });
    await refreshEpisode(EP, "proxy");
    // m01's take 1 in the proxy mix
    await api.pickCue({ ep: EP, pass: "proxy", cue: "m01", take: 1 });
    await loadMix(EP, "proxy");
    await loadCues(EP);
    el = document.createElement("div");
    document.body.appendChild(el);
    root = createRoot(el);
  });
  afterEach(() => {
    act(() => root.unmount());
    el.remove();
    store.set(initialState());
    vi.unstubAllGlobals();
  });

  const item = () => currentMix()?.mix.items?.find((i) => i.id === "m01");

  it("unticking plays in the mix mutes its item, silent in Play all; Ctrl+Z hears it again", async () => {
    await act(async () => root.render(createElement(SoundRefsSections, { ep: EP })));
    await act(async () => {});
    const box = el.querySelector<HTMLInputElement>('[data-cue-plays="m01"]')!;
    expect(box).toBeTruthy();
    expect(box.checked).toBe(true);
    await act(async () => box.click());
    await mixSettled();
    expect(item()?.mute).toBe(true);
    expect((await api.getMix(EP, "proxy")).mix.items?.find((i) => i.id === "m01")?.mute).toBe(true);
    expect(el.querySelector<HTMLInputElement>('[data-cue-plays="m01"]')!.checked).toBe(false);
    // Play all leaves it out
    expect(playPlan([], currentMix()!.mix, 24).some((e) => e.id === "m01")).toBe(false);
    await act(async () => void undoCut());
    await mixSettled();
    expect(item()?.mute).toBeUndefined();
  });

  it("Delete cue… asks, calls the route, and the cue window goes back to Spotting", async () => {
    const ask = vi.fn(() => false);
    vi.stubGlobal("confirm", ask);
    openCue("m01");
    await act(async () => root.render(createElement(SoundRefsSections, { ep: EP })));
    await act(async () => {});
    const btn = el.querySelector<HTMLButtonElement>('[data-cue-delete="m01"]')!;
    await act(async () => btn.click());
    // cancelled: nothing asked of the server
    expect(ask).toHaveBeenCalledTimes(1);
    expect(deleted).toEqual([]);
    const text = deleteCueAsk(store.get(), EP, "m01");
    expect(text).toContain("m01 and its 4 takes go to the episode's _history folder");
    expect(text).toContain("taken out of the proxy mix");
    expect(text).toContain("Ctrl+Z can't");

    ask.mockReturnValue(true);
    await act(async () => btn.click());
    await act(async () => {});
    expect(deleted).toEqual(["m01"]);
    const v = store.get().viewer;
    expect(v?.kind).toBe("cut");
    expect(v?.spot).toBe(true);
    expect(v?.cue).toBeUndefined();
    expect((store.get().cues[EP] ?? []).map((c) => c.spec.id)).not.toContain("m01");
    expect(item()).toBeUndefined();
    expect(el.querySelector('[data-cue-delete="m01"]')).toBeNull();
  });

  it("a refusal is said, and nothing moves", async () => {
    vi.stubGlobal("confirm", () => true);
    const errs: string[] = [];
    setHost({ on: () => () => {}, toast: (_k: string, t: string) => errs.push(t), show: () => {} } as unknown as Host);
    setApi({ ...api, deleteCue: async () => { throw new Error("m01 has 2 takes queued or rendering"); } });
    openCue("m01");
    expect(await deleteCue("m01")).toBe(false);
    expect(store.get().viewer?.kind).toBe("cue");
    expect(errs.some((t) => t.includes("Couldn't delete cue m01"))).toBe(true);
  });
});
