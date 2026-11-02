// @vitest-environment happy-dom
//
// Voices only (voices.py, docs/SOUND.md): what the Dialogue track plays for a clip (its
// take's voice stem, its whole sound, or silence for a shot with no lines), worked out here
// as the server does so a toggle is heard at once; Play all playing the stem on the
// dialogue track at its clip (its <video> muted); the Dialogue lane head's toggle and Make
// voice stems with its count, the badge on a clip whose stem is missing, and a clip's Sound
// menu (keep its whole sound, voices only, split again).
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { renderToString } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { refreshEpisode } from "../src/actions";
import { ContextMenu } from "../src/components/ContextMenu";
import { MixEngine } from "../src/components/MixAudio";
import { Timeline } from "../src/components/Timeline";
import { resetCutHistory } from "../src/cutActions";
import { setApi, setHost, type Host } from "../src/host";
import { setShotVoices, setVoicesOnly, voiceBadge, voicePlan, voicePlays, voicedShots } from "../src/lib/mix";
import type { PlayItem } from "../src/lib/playlist";
import { createMockApi } from "../src/mock/mockApi";
import { currentMix, loadMix, mixSettled, setShotVoicesMix } from "../src/mixActions";
import { initialState, statusKey, store } from "../src/store";
import type { Mix, MixVoice, MixVoices } from "../src/types";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
const RECT = HTMLElement.prototype.getBoundingClientRect;

function clip(shot: string, index: number, start: number, dur: number, inT = 0): PlayItem {
  return {
    shot, index, pass: "final", take: 1, mp4: `renders/${shot}/${shot}_t01.mp4`, why: "", start, dur, inT, outT: inT + dur, trimIn: 0, trimOut: 0,
    total: null, audioIn: null, audioOut: null, fadeIn: 0, fadeOut: 0, dissolveIn: 0, dissolveOut: 0,
  };
}

function voice(shot: string, over: Partial<MixVoice> = {}): MixVoice {
  return {
    shot, pass: "final", take: 1, path: `renders/${shot}/${shot}_t01.voice.wav`, state: "ok", why: null,
    voices_only: false, override: null, plays: "whole", lines: true, ...over,
  };
}

const ITEMS = [clip("sh010", 0, 0, 2, 0.5), clip("sh020", 1, 2, 3), clip("sh030", 2, 5, 1)];
const VOICES: MixVoices = {
  voices_only: true, split: 1, of: 3, queued: 0,
  shots: [voice("sh010"), voice("sh020", { state: "stale", why: "t01 was rendered again since it was split" }), voice("sh030", { lines: false })],
};
const ON: Mix = { tracks: { dialogue: { voices_only: true } } };

describe("voices only, worked out", () => {
  it("plays the stem, the whole sound where it can't, silence where there are no lines", () => {
    expect(VOICES.shots.map((v) => voicePlays(ON, v))).toEqual(["voice", "whole", "silence"]);
    expect(VOICES.shots.map((v) => voicePlays({}, v))).toEqual(["whole", "whole", "whole"]);
    // a shot's own way: its whole sound, or its stem though it has no lines
    const own = setShotVoices(setShotVoices(ON, "sh010", false), "sh030", true);
    expect(own.voices).toEqual({ sh010: { voices_only: false }, sh030: { voices_only: true } });
    expect(VOICES.shots.map((v) => voicePlays(own, v))).toEqual(["whole", "whole", "voice"]);
    expect(setShotVoices(own, "sh010", null).voices).toEqual({ sh030: { voices_only: true } });
    // a clip with sound of its own, or none, is left as it is
    expect(voicePlays(ON, voice("sh040", { state: "sourced" }))).toBe("whole");
  });

  it("toggles on the dialogue track, off dropped as mix.json keeps it", () => {
    const m = setVoicesOnly({ tracks: { dialogue: { gain_db: -2 } } }, true);
    expect(m.tracks).toEqual({ dialogue: { gain_db: -2, voices_only: true } });
    expect(setVoicesOnly(m, false).tracks).toEqual({ dialogue: { gain_db: -2 } });
    expect(setVoicesOnly(ON, false)).toEqual({});
  });

  it("badges a clip whose stem voices only wants and hasn't", () => {
    expect(voiceBadge(ON, VOICES.shots[0])).toBeNull();
    expect(voiceBadge(ON, VOICES.shots[1])).toContain("rendered again");
    expect(voiceBadge(ON, VOICES.shots[2])).toBeNull();                    // silent: nothing to warn
    expect(voiceBadge({}, VOICES.shots[1])).toBeNull();
    expect(voiceBadge(ON, voice("sh040", { state: "queued" }))).toContain("being made");
  });

  it("Play all plays the stem at its clip on the dialogue track, the clips it replaces muted", () => {
    const res = { mix: ON, voices: VOICES };
    const plan = voicePlan(ITEMS, res);
    expect(plan).toEqual([{
      id: "voice:sh010", track: "dialogue", path: "renders/sh010/sh010_t01.voice.wav", start: 0, end: 2, offset: 0.5,
      gain: 1, points: [], fadeIn: 0, fadeOut: 0, loop: false,
    }]);
    expect(voicedShots(res)).toEqual(["sh010", "sh030"]);
    expect(voicePlan(ITEMS, { mix: {}, voices: VOICES })).toEqual([]);
    expect(voicedShots({ mix: {}, voices: VOICES })).toEqual([]);
    // another take in the cut than the stem's: not played
    expect(voicePlan([{ ...ITEMS[0], take: 2 }], res)).toEqual([]);
  });

  it("the engine starts the stem on the dialogue fader from the clip's in point", async () => {
    let made!: { gains: unknown[] };
    const started: { at: number; off: number }[] = [];
    const AC = function () {
      const ctx = {
        currentTime: 0, state: "running", destination: {}, gains: [] as unknown[],
        createGain() {
          const p = { setValueAtTime() {}, linearRampToValueAtTime() {}, setTargetAtTime() {}, cancelScheduledValues() {} };
          const n = { gain: p, connect() {}, disconnect() {} };
          this.gains.push(n);
          return n;
        },
        createBufferSource() {
          return { buffer: null, playbackRate: { value: 1 }, connect() {}, disconnect() {}, stop() {},
                   start(at: number, off: number) { started.push({ at, off }); } };
        },
        resume: () => Promise.resolve(), close: () => Promise.resolve(),
      };
      made = ctx;
      return ctx;
    } as unknown as new () => AudioContext;
    const e = new MixEngine((p) => p, AC);
    const plan = voicePlan(ITEMS, { mix: ON, voices: VOICES });
    (e as unknown as { context(): unknown }).context();
    (e as unknown as { buffers: Map<string, Promise<AudioBuffer>> }).buffers.set(plan[0].path, Promise.resolve({ duration: 3 } as AudioBuffer));
    e.play(plan, 6, 1, 1, { dialogue: 1, effects: 1, ambience: 1, music: 1 });
    await Promise.resolve();
    await Promise.resolve();
    // from the cut's 1 s: 1.5 s into the stem (the clip starts 0.5 s into its take)
    expect(started).toHaveLength(1);
    expect(started[0].off).toBeCloseTo(1.5, 1);
    expect(made.gains.length).toBeGreaterThan(0);
  });
});

describe("voices only in the editor", () => {
  let root: Root;
  let el: HTMLDivElement;
  let EP: string;
  let api: ReturnType<typeof createMockApi>;
  const toasts: string[] = [];

  beforeEach(async () => {
    toasts.length = 0;
    setHost({ on: () => () => {}, toast: (_k: string, t: string) => void toasts.push(t), show: () => {} } as unknown as Host);
    api = createMockApi(() => {}, { latency: 0 });
    setApi(api);
    EP = (await api.episodes())[0].ep;
    store.set(initialState());
    resetCutHistory();
    store.set({ ep: EP, pass: "proxy" });
    await refreshEpisode(EP, "proxy");
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

  const headMenu = async () => {
    const btn = el.querySelectorAll<HTMLButtonElement>(".h3-snd-head button[aria-label$='track menu']")[0];
    await act(async () => btn.click());
    return document.querySelector<HTMLElement>(".h3-snd-trackmenu")!;
  };

  it("the Dialogue lane head's menu: Voices only, and Make voice stems with its count", async () => {
    store.set({ sound: true });
    // happy-dom lays nothing out: each clip's column 100 px wide, side by side
    const order = store.get().status[statusKey(EP, "proxy")]!.shots.map((s) => s.shot);
    HTMLElement.prototype.getBoundingClientRect = function (this: HTMLElement) {
      const i = this.dataset.shot ? order.indexOf(this.dataset.shot) : -1;
      return (i < 0 ? RECT.call(this) : { left: i * 100, width: 100, top: 0, height: 40, right: i * 100 + 100, bottom: 40, x: i * 100, y: 0 }) as DOMRect;
    };
    await act(async () => root.render(createElement(Timeline)));
    await act(async () => store.set((s) => ({ zoom: s.zoom + 1 })));
    let m = await headMenu();
    const of = currentMix()!.voices!.of;
    expect(of).toBeGreaterThan(1);
    expect(m.querySelector("[data-voices='count']")!.textContent).toBe(`0/${of} shots split`);
    // the toggle: one undoable edit
    const box = m.querySelector<HTMLInputElement>("[data-voices='toggle'] input")!;
    expect(box.checked).toBe(false);
    await act(async () => box.click());
    await mixSettled();
    expect(currentMix()!.mix.tracks).toEqual({ dialogue: { voices_only: true } });
    expect(store.get().cutUndo[statusKey(EP, "proxy")]?.undo).toBe("Dialogue: voices only");
    // no stem yet: the clips with lines say they play whole
    expect(el.querySelectorAll("[data-voice='badge']").length).toBeGreaterThan(0);
    // make them: queued for the whole pass, and the count follows the mix as it's fetched again
    m = await headMenu();
    await act(async () => m.querySelector<HTMLButtonElement>("[data-voices='make']")!.click());
    expect(toasts.some((t) => t.startsWith(`Splitting ${of} takes`))).toBe(true);
    await act(async () => void (await loadMix(EP, "proxy")));
    m = await headMenu();
    expect(m.querySelector("[data-voices='count']")!.textContent).toBe(`${of}/${of} shots split`);
    expect(el.querySelectorAll("[data-voice='badge']")).toHaveLength(0);
    expect(el.querySelectorAll("[data-voice='voice']").length).toBeGreaterThan(0);
    expect(el.querySelectorAll(".h3-snd-voice-silent").length).toBeGreaterThan(0);  // the shots with no lines
  });

  it("each lane's right-click menu has its track's own things and Scoring; a double-click on a lane opens Scoring", async () => {
    store.set({ sound: true });
    const order = store.get().status[statusKey(EP, "proxy")]!.shots.map((s) => s.shot);
    HTMLElement.prototype.getBoundingClientRect = function (this: HTMLElement) {
      const i = this.dataset.shot ? order.indexOf(this.dataset.shot) : -1;
      return (i < 0 ? RECT.call(this) : { left: i * 100, width: 100, top: 0, height: 40, right: i * 100 + 100, bottom: 40, x: i * 100, y: 0 }) as DOMRect;
    };
    await act(async () => root.render(createElement(Timeline)));
    await act(async () => store.set((s) => ({ zoom: s.zoom + 1 })));
    const lane = (track: string) => el.querySelector<HTMLElement>(`.h3-snd-lane[data-track='${track}']`)!;
    const menuOf = async (track: string) => {
      await act(async () => lane(track).dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, clientX: 50, clientY: 5 })));
      const m = [...document.querySelectorAll<HTMLElement>(".h3-snd-pop")].pop()!;
      return [...m.querySelectorAll("button, label")].map((b) => b.textContent!.trim());
    };
    const dia = await menuOf("dialogue");
    expect(dia).toContain("Voices only");
    expect(dia.some((t) => t.endsWith("keep its whole sound"))).toBe(true);
    expect(dia).toContain("Scoring (spotting)…");
    await act(async () => document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })));
    const fx = await menuOf("effects");
    expect(fx.some((t) => t.startsWith("Make effects for"))).toBe(true);
    expect(fx).toContain("Scoring (spotting)…");
    await act(async () => document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })));
    await act(async () => lane("ambience").dispatchEvent(new MouseEvent("dblclick", { bubbles: true })));
    expect([store.get().viewer?.kind, store.get().viewer?.spot]).toEqual(["cut", true]);
  });

  it("a clip's Sound menu sets the shot its own way and splits it again", async () => {
    const key = statusKey(EP, "proxy");
    const shot = currentMix()!.voices!.shots[0].shot;
    store.set({ menu: { x: 0, y: 0, shot, pass: "proxy", take: 1 } });
    let html = renderToString(createElement(ContextMenu));
    expect(html).toContain("Keep its whole sound");
    expect(html).toContain("Voices only");
    expect(html).toContain("Split its voice");
    await setShotVoicesMix([shot], false);
    await mixSettled();
    expect(currentMix()!.mix.voices).toEqual({ [shot]: { voices_only: false } });
    expect(store.get().cutUndo[key]?.undo).toBe(`${shot}: its whole sound`);
    html = renderToString(createElement(ContextMenu));
    expect(html).toMatch(/pi-check"[^>]*><\/i> Keep its whole sound/);
    await setShotVoicesMix([shot], null);
    await mixSettled();
    expect(currentMix()!.mix.voices).toBeUndefined();
  });
});
