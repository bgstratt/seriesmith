// @vitest-environment happy-dom
//
// The Refs tab's sound "+" (docs/EDITOR.md "Sound"): Music's makes a cue over the span
// picked (a sequence) and opens it; Effects' makes effects for the shots picked (to start,
// those without any) on the model picked; Ambience's writes a place's new words to the series
// config and makes its bed. And the Ambience lane's menu offers the shot's place's bed.
import { act, createElement, Fragment } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { currentPlaylist, refreshEpisode } from "../src/actions";
import { SoundAddDialog } from "../src/components/SoundAdd";
import { SoundRefsSections } from "../src/components/SoundRefs";
import { Timeline } from "../src/components/Timeline";
import { resetCutHistory } from "../src/cutActions";
import { setApi, setHost, type Host } from "../src/host";
import { createMockApi } from "../src/mock/mockApi";
import { loadMix } from "../src/mixActions";
import { initialState, statusKey, store } from "../src/store";
import type { AmbienceBed, CueSpec, MixPlace, RefGenerateRequest } from "../src/types";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
const RECT = HTMLElement.prototype.getBoundingClientRect;

describe("the sound sections' +", () => {
  let root: Root;
  let el: HTMLDivElement;
  let EP: string;
  let api: ReturnType<typeof createMockApi>;
  let cues: CueSpec[];
  let fxAsked: { shots: string[]; target?: string }[];
  let gens: RefGenerateRequest[];
  let saved: string[];
  let place: string;
  let shots: { shot: string; sequence: string | null }[];

  beforeEach(async () => {
    setHost({ on: () => () => {}, toast: () => {}, show: () => {} } as Host);
    api = createMockApi(() => {}, { latency: 0 });
    EP = (await api.episodes())[0].ep;
    cues = [];
    fxAsked = [];
    gens = [];
    saved = [];
    const series = JSON.parse((await api.source(EP, "series")).text) as { locations: Record<string, unknown> };
    place = Object.keys(series.locations).find((k) => !k.startsWith("_"))!;
    setApi({
      ...api,
      putCue: async (ep, cue) => {
        cues.push(cue);
        return api.putCue(ep, cue);
      },
      fxShots: async () => ({ shots: [{ shot: shots[0].shot, takes: 1, ok: 1, queued: 0, failed: 0, picked: 1 }] }),
      renderFx: async (req) => {
        fxAsked.push({ shots: req.shots, ...(req.target ? { target: req.target } : {}) });
        return { queued: req.shots.map((shot) => ({ shot, take: 1, job: `fx-${shot}`, seed: 1, target: req.target ?? "h3_foley" })), skipped: [] };
      },
      ambience: async () => ({ beds: [] as AmbienceBed[], target: null }),
      getMix: async (ep, pass) => {
        const r = await api.getMix(ep, pass);
        const places: Record<string, MixPlace> = {};
        for (const s of shots) places[s.shot] = { place, name: "The Diner", bed: false };
        return { ...r, places };
      },
      putSource: async (req) => {
        saved.push(req.text);
        return api.putSource(req);
      },
      refsGenerate: async (req) => {
        gens.push(req);
        return { queued: [], errors: [] };
      },
    });
    store.set(initialState());
    resetCutHistory();
    store.set({ ep: EP, pass: "proxy" });
    await refreshEpisode(EP, "proxy");
    shots = store.get().status[statusKey(EP, "proxy")]!.shots.map((s) => ({ shot: s.shot, sequence: s.sequence }));
    await loadMix(EP, "proxy");
    el = document.createElement("div");
    document.body.appendChild(el);
    root = createRoot(el);
  });
  afterEach(() => {
    HTMLElement.prototype.getBoundingClientRect = RECT;
    act(() => root.unmount());
    el.remove();
    store.set(initialState());
  });

  const render = async () => {
    await act(async () => root.render(createElement(Fragment, null, createElement(SoundRefsSections, { ep: EP }), createElement(SoundAddDialog))));
    await act(async () => {});
  };
  const plus = async (which: string) => {
    await act(async () => el.querySelector<HTMLButtonElement>(`button[data-add='${which}']`)!.click());
    await act(async () => {});
    return el.querySelector<HTMLElement>(".h3-dialog")!;
  };
  const settle = () => act(async () => {
    await new Promise((r) => setTimeout(r, 0));
  });

  it("Music's + makes a cue over the sequence picked, and opens it", async () => {
    await render();
    const dlg = await plus("music");
    expect(dlg.textContent).toContain("New cue");
    // the second sequence of the cut, over all its shots, as a song
    const seqs = [...dlg.querySelectorAll<HTMLButtonElement>("button[data-seq]")];
    const seq = seqs[seqs.length > 1 ? 1 : 0];
    await act(async () => seq.click());
    await act(async () => dlg.querySelector<HTMLButtonElement>("button[data-kind='song']")!.click());
    await act(async () => dlg.querySelector<HTMLButtonElement>("button[data-act='make-cue']")!.click());
    await settle();
    const items = currentPlaylist(store.get());
    const of = items.filter((it) => shots.find((s) => s.shot === it.shot)?.sequence === seq.dataset.seq);
    expect(cues).toHaveLength(1);
    expect(cues[0].kind).toBe("song");
    expect(cues[0].in.shot).toBe(of[0].shot);
    expect(cues[0].out.shot).toBe(of[of.length - 1].shot);
    expect([store.get().viewer?.kind, store.get().viewer?.cue]).toEqual(["cue", cues[0].id]);
    expect(store.get().soundAdd).toBeNull();
  });

  it("Effects' + starts on the shots without effects, shows the one with, and makes them", async () => {
    await render();
    const dlg = await plus("effects");
    await act(async () => {});
    const box = (shot: string) => dlg.querySelector<HTMLInputElement>(`input[data-shot='${shot}']`)!;
    expect(box(shots[0].shot).checked).toBe(false);               // it has effects: t01 shown
    expect(box(shots[0].shot).parentElement!.textContent).toContain("t01");
    expect(box(shots[1].shot).checked).toBe(true);
    // its sequence's toggle takes its shots out
    const seq = shots[1].sequence ?? "";
    const toggle = dlg.querySelector<HTMLInputElement>(`input[data-seq='${seq}']`)!;
    await act(async () => toggle.click());                          // not all on: all on
    expect(box(shots.find((s) => s.sequence === seq)!.shot).checked).toBe(true);
    await act(async () => toggle.click());                          // all on: all off
    const left = shots.filter((s) => s.sequence !== seq && s.shot !== shots[0].shot).map((s) => s.shot);
    expect(left.length).toBeGreaterThan(0);
    await act(async () => dlg.querySelector<HTMLButtonElement>("button[data-act='make-fx']")!.click());
    await settle();
    expect(fxAsked).toEqual([{ shots: currentPlaylist(store.get()).map((it) => it.shot).filter((x) => left.includes(x)) }]);
  });

  it("Ambience's + writes a place's new words to the series config, then makes its bed", async () => {
    await render();
    const dlg = await plus("ambience");
    await act(async () => {});
    const radio = dlg.querySelector<HTMLInputElement>(`input[data-place='${place}']`)!;
    expect(radio.checked).toBe(true);
    expect(radio.parentElement!.textContent).toContain("no words");
    const words = dlg.querySelector<HTMLTextAreaElement>("textarea[data-field='words']")!;
    const set = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!;
    await act(async () => {
      set.call(words, "a refrigerator hum, rain on the glass");
      words.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => dlg.querySelector<HTMLButtonElement>("button[data-act='make-bed']")!.click());
    // the mock writes and rebuilds (1.2 s), then the bed is asked for
    for (let i = 0; i < 60 && !gens.length; i++) await act(async () => new Promise((r) => setTimeout(r, 50)));
    expect(saved).toHaveLength(1);
    expect((JSON.parse(saved[0]) as { locations: Record<string, { ambience?: string }> }).locations[place].ambience).toBe("a refrigerator hum, rain on the glass");
    expect(gens.map((g) => g.ref)).toEqual([`ambience:${place}`]);
  });

  it("the Ambience lane's menu offers the shot's place's bed", async () => {
    store.set({ sound: true });
    const order = currentPlaylist(store.get()).map((it) => it.shot);
    HTMLElement.prototype.getBoundingClientRect = function (this: HTMLElement) {
      const i = this.dataset.shot ? order.indexOf(this.dataset.shot) : -1;
      return (i < 0 ? RECT.call(this) : { left: i * 100, width: 100, top: 0, height: 40, right: i * 100 + 100, bottom: 40, x: i * 100, y: 0 }) as DOMRect;
    };
    await act(async () => root.render(createElement(Fragment, null, createElement(Timeline), createElement(SoundAddDialog))));
    await act(async () => store.set((s) => ({ zoom: s.zoom + 1 })));
    const lane = el.querySelectorAll<HTMLElement>(".h3-snd-lane")[3];
    const menu = async () => {
      await act(async () => lane.dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, clientX: 50, clientY: 100 })));
      return document.querySelector<HTMLElement>(".h3-snd-pop")!;
    };
    // no words: the dialog, on its place
    let m = await menu();
    const add = m.querySelector<HTMLButtonElement>("button[data-bed='add']")!;
    expect(add.textContent).toContain("Make The Diner's ambience bed");
    await act(async () => add.click());
    expect(store.get().soundAdd).toEqual({ kind: "bed", place });
    await act(async () => store.set({ soundAdd: null }));
    // its bed laid (words, not made): made at once; made: again, or opened
    const key = statusKey(EP, "proxy");
    const bed = (exists: boolean) => ({ place, label: "The Diner", path: "../refs/_amb/diner.wav", exists, words: "a fridge hum",
                                         shots: [order[0]], in: { shot: order[0], frame: 0 }, out: { shot: order[0], frame: 24 }, start: 0, end: 1, gain_db: 0, mute: false });
    await act(async () => store.set((s) => ({ mix: { ...s.mix, [key]: { ...s.mix[key]!, beds: [bed(false)] } } })));
    m = await menu();
    expect(m.querySelector("button[data-bed='make']")!.textContent).toContain("Make The Diner's ambience bed");
    await act(async () => m.querySelector<HTMLButtonElement>("button[data-bed='make']")!.click());
    await settle();
    expect(gens.map((g) => g.ref)).toEqual([`ambience:${place}`]);
    await act(async () => store.set((s) => ({ mix: { ...s.mix, [key]: { ...s.mix[key]!, beds: [bed(true)] } } })));
    m = await menu();
    expect(m.querySelector("button[data-bed='make']")!.textContent).toContain("Make The Diner's bed again");
    expect(m.querySelector("button[data-bed='open']")).not.toBeNull();
  });
});
