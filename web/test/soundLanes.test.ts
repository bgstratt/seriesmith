// @vitest-environment happy-dom
//
// The timeline's sound lanes on the mock: the Sound toggle unfolds them (and
// is remembered), they draw the pass's mix (items as blocks, hits as markers
// coloured by kind), and a fader's mute is one edit of the mix.
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { currentPlaylist, refreshEpisode } from "../src/actions";
import { Timeline } from "../src/components/Timeline";
import { resetCutHistory } from "../src/cutActions";
import { setApi, setHost, type Host } from "../src/host";
import { createMockApi } from "../src/mock/mockApi";
import { currentMix, loadMix, mixSettled } from "../src/mixActions";
import { initialState, loadPrefs, savePrefs, statusKey, store } from "../src/store";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
const RECT = HTMLElement.prototype.getBoundingClientRect;

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
    HTMLElement.prototype.getBoundingClientRect = RECT;
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

  it("a place's ambience bed is a block on the Ambience lane, its menu mutes the place", async () => {
    const key = statusKey(EP, "proxy");
    const shots = store.get().status[key]!.shots;
    const bed = { place: "diner", label: "Diner", path: "../refs/_amb/diner.wav", exists: true, words: "a fridge hum",
                  shots: [shots[0].shot], in: { shot: shots[0].shot, frame: 0 }, out: { shot: shots[0].shot, frame: 24 },
                  start: 0, end: 1, gain_db: 0, mute: false };
    store.set((s) => ({ mix: { ...s.mix, [key]: { ...s.mix[key]!, beds: [bed] } } }));
    store.set({ sound: true });
    await act(async () => root.render(createElement(Timeline)));
    const block = el.querySelector<HTMLElement>(".h3-snd-bed")!;
    expect(block).not.toBeNull();
    expect(block.title).toContain("Diner's ambience bed");
    await act(async () => block.dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, clientX: 100, clientY: 100 })));
    const mute = [...document.querySelectorAll<HTMLButtonElement>(".h3-snd-pop button")].find((x) => x.textContent?.includes("Mute this place"))!;
    await act(async () => mute.click());
    await mixSettled();
    expect(currentMix()!.mix.beds).toEqual({ diner: { mute: true } });
  });

  it("a shot's effects are a block on the Effects lane, stale marked; its menu keeps them as they are", async () => {
    const key = statusKey(EP, "proxy");
    const shot = store.get().status[key]!.shots[0].shot;
    await api.putMix(EP, "proxy", { ...currentMix()!.mix, fx: { [shot]: { take: 1 } } });
    await loadMix(EP, "proxy");
    const fx = { shot, take: 1, model: "h3_foley", path: `sound/fx/proxy/${shot}/t01.wav`, exists: true,
                 in: { shot, frame: 0 }, out: { shot, frame: 24 }, start: 0, end: 1, offset: 0, gain_db: 0, mute: false,
                 keep_stale: false, stale: "made from t01; the cut plays t02", heard: false };
    store.set((s) => ({ mix: { ...s.mix, [key]: { ...s.mix[key]!, fx: [fx] } } }));
    store.set({ sound: true });
    await act(async () => root.render(createElement(Timeline)));
    const block = el.querySelector<HTMLElement>(".h3-snd-fx")!;
    expect(block).not.toBeNull();
    expect(block.className).toContain("h3-snd-fx-stale");
    expect(block.title).toContain(`${shot}'s effects`);
    expect(block.title).toContain("stale: made from t01; the cut plays t02");
    await act(async () => block.dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, clientX: 100, clientY: 100 })));
    const keep = [...document.querySelectorAll<HTMLButtonElement>(".h3-snd-pop button")].find((x) => x.textContent?.includes("Keep as it is"))!;
    expect(keep).toBeTruthy();
    await act(async () => keep.click());
    await mixSettled();
    expect(currentMix()!.mix.fx).toEqual({ [shot]: { take: 1, keep_stale: true } });
  });

  it("a shot's effects: an edge dragged trims it where it is, a point added on its line, the menu's numbers and Reset", async () => {
    const key = statusKey(EP, "proxy");
    const shots = store.get().status[key]!.shots;
    const shot = shots[0].shot;
    await api.putMix(EP, "proxy", { ...currentMix()!.mix, fx: { [shot]: { take: 1, gain_db: -2 } } });
    await loadMix(EP, "proxy");
    // the clip's own span, so the block fills its 100 px column
    const it0 = currentPlaylist()[0];
    const f0 = Math.round(it0.inT * 24);
    const f1 = Math.round((it0.inT + it0.dur) * 24);
    const fx = { shot, take: 1, model: "h3_foley", path: `sound/fx/proxy/${shot}/t01.wav`, exists: true,
                 in: { shot, frame: f0 }, out: { shot, frame: f1 }, start: 0, end: it0.dur, offset: it0.inT, gain_db: -2, mute: false,
                 keep_stale: false, stale: null, heard: true };
    store.set((s) => ({ mix: { ...s.mix, [key]: { ...s.mix[key]!, fx: [fx] } } }));
    store.set({ sound: true });
    const order = shots.map((s) => s.shot);
    HTMLElement.prototype.getBoundingClientRect = function (this: HTMLElement) {
      const i = this.dataset.shot ? order.indexOf(this.dataset.shot) : -1;
      return (i < 0 ? RECT.call(this) : { left: i * 100, width: 100, top: 0, height: 40, right: i * 100 + 100, bottom: 40, x: i * 100, y: 0 }) as DOMRect;
    };
    await act(async () => root.render(createElement(Timeline)));
    await act(async () => store.set((s) => ({ zoom: s.zoom + 1 })));
    const block = el.querySelector<HTMLElement>(".h3-snd-fx")!;
    const where = () => [block.style.left, block.style.width];
    const was = where();
    expect(was[1]).toBe("100px");
    expect(block.querySelector("[data-trim]")).toBeNull();

    // drag its right edge 20 px left: trim_out, the block where it was and as long, the tail hatched
    const handle = block.querySelector<HTMLElement>(".h3-trim-h.h3-r")!;
    await act(async () => handle.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, button: 0, clientX: 99, clientY: 5 })));
    await act(async () => window.dispatchEvent(new PointerEvent("pointermove", { clientX: 79, clientY: 5 })));
    expect(document.querySelector(".h3-trim-tip")?.textContent).toContain(`${shot}'s effects tail trimmed`);
    expect(block.querySelector("[data-trim=out]")).not.toBeNull();
    await act(async () => window.dispatchEvent(new PointerEvent("pointerup", {})));
    await mixSettled();
    const want = Math.round(0.2 * it0.dur * 24);
    const own = currentMix()!.mix.fx![shot];
    expect(Math.abs(own.trim_out! - want)).toBeLessThanOrEqual(1);
    expect(own.trim_in).toBeUndefined();
    expect(own.gain_db).toBe(-2);
    expect(store.get().cutUndo[key]?.undo).toBe(`Trim ${shot}'s effects tail`);
    expect(where()).toEqual(was);
    const cut = block.querySelector<HTMLElement>("[data-trim=out]")!;
    expect(Math.abs(parseFloat(cut.style.width) - 20)).toBeLessThan(5);

    // a double-click on the line (no points: held at 0 dB, y 5.3 of 16 below the border) adds a point on the shot
    await act(async () => block.dispatchEvent(new MouseEvent("dblclick", { bubbles: true, clientX: 40, clientY: 6 })));
    await mixSettled();
    const pts = currentMix()!.mix.fx![shot].points!;
    expect(pts).toHaveLength(1);
    expect(pts[0]).toEqual({ at: { shot, frame: expect.any(Number) }, db: 0 });
    expect(store.get().cutUndo[key]?.undo).toBe(`Add a volume point to ${shot}'s effects`);
    expect(block.querySelectorAll(".h3-snd-pt")).toHaveLength(1);
    // dragged down 8 px: -4 dB
    const pt = block.querySelector(".h3-snd-pt-hit")!;
    await act(async () => pt.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, button: 0, clientX: 40, clientY: 6 })));
    await act(async () => window.dispatchEvent(new PointerEvent("pointermove", { clientX: 40, clientY: 14 })));
    await act(async () => window.dispatchEvent(new PointerEvent("pointerup", {})));
    await mixSettled();
    expect(currentMix()!.mix.fx![shot].points![0].db).toBe(-4);

    // the menu: its numbers (a fade out), then Reset trims and levels (its level stays)
    await act(async () => block.dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, clientX: 100, clientY: 100 })));
    const fade = document.querySelector<HTMLInputElement>(".h3-snd-pop input[data-fx-field=fade_out]")!;
    expect(document.querySelector<HTMLInputElement>(".h3-snd-pop input[data-fx-field=trim_out]")!.value).toBe(String(own.trim_out));
    await act(async () => {
      const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
      set.call(fade, "6");
      fade.dispatchEvent(new Event("input", { bubbles: true }));
    });
    const apply = [...document.querySelectorAll<HTMLButtonElement>(".h3-snd-pop button")].find((b) => b.textContent === "Apply")!;
    await act(async () => apply.click());
    await mixSettled();
    expect(currentMix()!.mix.fx![shot].fade_out).toBe(6);
    expect(block.querySelector(".h3-snd-fade.h3-r")).not.toBeNull();
    await act(async () => block.dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, clientX: 100, clientY: 100 })));
    const reset = [...document.querySelectorAll<HTMLButtonElement>(".h3-snd-pop button")].find((b) => b.textContent?.includes("Reset trims and levels"))!;
    await act(async () => reset.click());
    await mixSettled();
    expect(currentMix()!.mix.fx).toEqual({ [shot]: { take: 1, gain_db: -2 } });
    expect(block.querySelector("[data-trim]")).toBeNull();
  });

  it("the music fader shows its -12 dB default", async () => {
    store.set({ sound: true });
    await act(async () => root.render(createElement(Timeline)));
    const faders = [...el.querySelectorAll<HTMLInputElement>(".h3-snd-fader")];
    expect(faders.map((f) => f.value)).toEqual(["0", "0", "0", "-12"]);
    expect(faders[3].title).toContain("-12 dB (the default)");
    expect(el.querySelectorAll(".h3-snd-db")[3].textContent).toBe("-12");
  });

  it("a block draws its volume points: a right-click deletes one, a double-click on the line adds one, a drag moves one, the menu clears them", async () => {
    const shots = store.get().status[statusKey(EP, "proxy")]!.shots;
    const pts = [{ at: { shot: shots[0].shot, frame: 6 }, db: -6 }, { at: { shot: shots[1].shot, frame: 4 }, db: 3 }];
    await api.putMix(EP, "proxy", {
      items: [{ id: "amb01", track: "ambience", path: "audio/room_tone.wav", in: { shot: shots[0].shot, frame: 0 }, out: { shot: shots[1].shot, frame: 10 }, loop: true, points: pts }],
    });
    await loadMix(EP, "proxy");
    store.set({ sound: true });
    // happy-dom lays nothing out: each clip's column 100 px wide, side by side (until afterEach)
    const order = shots.map((s) => s.shot);
    HTMLElement.prototype.getBoundingClientRect = function (this: HTMLElement) {
      const i = this.dataset.shot ? order.indexOf(this.dataset.shot) : -1;
      return (i < 0 ? RECT.call(this) : { left: i * 100, width: 100, top: 0, height: 40, right: i * 100 + 100, bottom: 40, x: i * 100, y: 0 }) as DOMRect;
    };
    await act(async () => root.render(createElement(Timeline)));
    // measured again (a browser's ResizeObserver does it on mount)
    await act(async () => store.set((s) => ({ zoom: s.zoom + 1 })));
    const block = el.querySelector<HTMLElement>(".h3-snd-item.h3-snd-ambience")!;
    expect(block.style.width).not.toBe("4px");
    expect(block.querySelectorAll(".h3-snd-pt")).toHaveLength(2);
    expect(block.querySelector(".h3-snd-gainline")).not.toBeNull();
    expect(block.querySelector(".h3-snd-zero")).not.toBeNull();

    // right-click the second point: one edit, and only the item's menu stays shut
    const hits = block.querySelectorAll(".h3-snd-pt-hit");
    await act(async () => hits[1].dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, cancelable: true })));
    await mixSettled();
    expect(currentMix()!.mix.items![0].points).toEqual([pts[0]]);
    expect(store.get().cutUndo[statusKey(EP, "proxy")]?.undo).toBe("Delete a volume point of amb01");
    expect(document.querySelector(".h3-snd-pop")).toBeNull();
    expect(block.querySelectorAll(".h3-snd-pt")).toHaveLength(1);

    // a double-click on the line (held at -6 dB: y 8 of 16, the block's border 1 above) adds one there
    await act(async () => block.dispatchEvent(new MouseEvent("dblclick", { bubbles: true, clientX: 150, clientY: 9 })));
    await mixSettled();
    expect(currentMix()!.mix.items![0].points!.map((p) => p.db)).toEqual([-6, -6]);
    expect(currentMix()!.mix.items![0].points![1].at.shot).toBe(shots[1].shot);
    expect(block.querySelectorAll(".h3-snd-pt")).toHaveLength(2);
    // off the line: nothing
    await act(async () => block.dispatchEvent(new MouseEvent("dblclick", { bubbles: true, clientX: 120, clientY: 16 })));
    await mixSettled();
    expect(currentMix()!.mix.items![0].points).toHaveLength(2);

    // drag the first point up 10 px: +5 dB, one edit; Esc cancels another
    const drag = async (dy: number, shown: string, end: () => void) => {
      const h = block.querySelector(".h3-snd-pt-hit")!;
      await act(async () => h.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, button: 0, clientX: 6, clientY: 9 })));
      await act(async () => window.dispatchEvent(new PointerEvent("pointermove", { clientX: 6, clientY: 9 + dy })));
      expect(document.querySelector(".h3-trim-tip")?.textContent).toContain(`amb01 volume point ${shown} dB · ${shots[0].shot} frame 6`);
      await act(async () => end());
      await mixSettled();
    };
    await drag(-10, "-1", () => window.dispatchEvent(new PointerEvent("pointerup", {})));
    expect(currentMix()!.mix.items![0].points![0]).toEqual({ at: { shot: shots[0].shot, frame: 6 }, db: -1 });
    expect(store.get().cutUndo[statusKey(EP, "proxy")]?.undo).toBe("Move a volume point of amb01");
    await drag(-4, "+1", () => window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })));
    expect(currentMix()!.mix.items![0].points![0].db).toBe(-1);
    expect(document.querySelector(".h3-trim-tip")).toBeNull();

    // the item's menu: Clear the volume points
    await act(async () => block.dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, cancelable: true })));
    const clear = [...document.querySelectorAll<HTMLButtonElement>(".h3-snd-pop button")].find((b) => b.textContent?.includes("Clear the volume points"))!;
    await act(async () => clear.click());
    await mixSettled();
    expect(currentMix()!.mix.items![0].points).toBeUndefined();
    expect(block.querySelectorAll(".h3-snd-pt")).toHaveLength(0);
  });

  /** happy-dom lays nothing out: each clip's column 100 px wide, side by side (until afterEach), then the timeline drawn and measured */
  const columns = async () => {
    const order = store.get().status[statusKey(EP, "proxy")]!.shots.map((x) => x.shot);
    HTMLElement.prototype.getBoundingClientRect = function (this: HTMLElement) {
      const i = this.dataset.shot ? order.indexOf(this.dataset.shot) : -1;
      return (i < 0 ? RECT.call(this) : { left: i * 100, width: 100, top: 0, height: 40, right: i * 100 + 100, bottom: 40, x: i * 100, y: 0 }) as DOMRect;
    };
    store.set({ sound: true });
    await act(async () => root.render(createElement(Timeline)));
    await act(async () => store.set((s) => ({ zoom: s.zoom + 1 })));
  };

  it("a block's fade handles: white squares at its top corners, dragged in to set a fade (undoable, Esc cancels)", async () => {
    await columns();
    const block = el.querySelector<HTMLElement>(".h3-snd-item.h3-snd-ambience")!;
    expect(parseFloat(block.style.width)).toBeGreaterThan(100);
    // no fades yet: both corners' squares, apart from the volume points' dots
    const handles = block.querySelectorAll<SVGRectElement>("rect.h3-snd-fadeh");
    expect(handles).toHaveLength(2);
    expect(handles[1].getAttribute("class")).toContain("h3-snd-fadeh-corner");
    expect(block.querySelector(".h3-snd-fadeline")).toBeNull();

    const drag = async (side: "in" | "out", dx: number, end: () => void) => {
      const h = block.querySelector<SVGRectElement>(`rect[data-fade=${side}]`)!;
      await act(async () => h.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, button: 0, clientX: 150, clientY: 2 })));
      await act(async () => window.dispatchEvent(new PointerEvent("pointermove", { clientX: 150 + dx, clientY: 2 })));
      const tip = document.querySelector(".h3-trim-tip")?.textContent ?? "";
      await act(async () => end());
      await mixSettled();
      return tip;
    };
    const in0 = currentMix()!.mix.items![0].in;
    // the tail's square dragged 30 px in: a fade out, one edit
    const tip = await drag("out", -30, () => window.dispatchEvent(new PointerEvent("pointerup", {})));
    expect(tip).toContain("amb01 · fade out");
    expect(tip).toContain("new · Esc cancels");
    const out = currentMix()!.mix.items![0].fade_out!;
    expect(out).toBeGreaterThan(0);
    expect(store.get().cutUndo[statusKey(EP, "proxy")]?.undo).toBe("amb01 fade out");
    expect(block.querySelector(".h3-snd-fadeline")).not.toBeNull();
    expect(block.querySelector("rect[data-fade=out]")!.getAttribute("class")).not.toContain("corner");
    expect(currentMix()!.mix.items![0].in).toEqual(in0);
    // dragged on but Esc: kept as it was
    expect(await drag("out", -20, () => window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })))).toContain(`was ${out} f`);
    expect(currentMix()!.mix.items![0].fade_out).toBe(out);
    // the head's dragged right: a fade in; then back past its start takes it off
    await drag("in", 15, () => window.dispatchEvent(new PointerEvent("pointerup", {})));
    expect(currentMix()!.mix.items![0].fade_in).toBeGreaterThan(0);
    await drag("in", -200, () => window.dispatchEvent(new PointerEvent("pointerup", {})));
    expect(currentMix()!.mix.items![0].fade_in).toBeUndefined();
    expect(store.get().cutUndo[statusKey(EP, "proxy")]?.undo).toBe("amb01 fade in taken off");
    // the item's menu still has the numbers
    await act(async () => block.dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, cancelable: true })));
    const fields = [...document.querySelectorAll<HTMLInputElement>(".h3-snd-pop input[type=number]")].map((x) => x.value);
    expect(fields).toContain(String(out));
  });

  it("a shot's effects take a fade from a handle at the edge of what's heard", async () => {
    const key = statusKey(EP, "proxy");
    const shot = store.get().status[key]!.shots[0].shot;
    await api.putMix(EP, "proxy", { ...currentMix()!.mix, fx: { [shot]: { take: 1, trim_in: 6 } } });
    await loadMix(EP, "proxy");
    const it0 = currentPlaylist()[0];
    const fx = { shot, take: 1, model: "h3_foley", path: `sound/fx/proxy/${shot}/t01.wav`, exists: true,
                 in: { shot, frame: Math.round(it0.inT * 24) }, out: { shot, frame: Math.round((it0.inT + it0.dur) * 24) }, start: 0, end: it0.dur,
                 offset: it0.inT, gain_db: 0, mute: false, keep_stale: false, stale: null, heard: true };
    store.set((s) => ({ mix: { ...s.mix, [key]: { ...s.mix[key]!, fx: [fx] } } }));
    await columns();
    const block = el.querySelector<HTMLElement>(".h3-snd-fx")!;
    const h = block.querySelector<SVGRectElement>("rect[data-fade=in]")!;
    // the head's square sits in from the trimmed head (the hatched part), not on the block's edge
    expect(Number(h.getAttribute("x"))).toBeGreaterThan(parseFloat(block.querySelector<HTMLElement>("[data-trim=in]")!.style.width));
    await act(async () => h.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, button: 0, clientX: 30, clientY: 2 })));
    await act(async () => window.dispatchEvent(new PointerEvent("pointermove", { clientX: 50, clientY: 2 })));
    expect(document.querySelector(".h3-trim-tip")?.textContent).toContain(`${shot}'s effects · fade in`);
    await act(async () => window.dispatchEvent(new PointerEvent("pointerup", {})));
    await mixSettled();
    const own = currentMix()!.mix.fx![shot];
    expect(own.fade_in).toBeGreaterThan(0);
    expect(own.trim_in).toBe(6);
    expect(store.get().cutUndo[key]?.undo).toBe(`${shot}'s effects fade in`);
  });

  it("a duck region from a lane's menu: score forward over the shot, drawn across the lanes; its menu gives it its own dip, then deletes it", async () => {
    const key = statusKey(EP, "proxy");
    const shots = store.get().status[key]!.shots;
    await columns();
    // right-click the Music lane over the second clip
    const music = el.querySelectorAll<HTMLElement>(".h3-snd-lane")[4];
    await act(async () => music.dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, clientX: 150, clientY: 100 })));
    const add = document.querySelector<HTMLButtonElement>(".h3-snd-pop button[data-region=add]")!;
    expect(add.textContent).toContain(`Duck region here (${shots[1].shot})`);
    await act(async () => add.click());
    await mixSettled();
    const it1 = currentPlaylist()[1];
    expect(currentMix()!.mix.regions).toEqual([{
      from: { shot: shots[1].shot, frame: Math.round(it1.inT * 24) }, to: { shot: shots[1].shot, frame: Math.round((it1.inT + it1.dur) * 24) },
      music_duck_db: 0, dialogue_db: -4,
    }]);
    expect(store.get().cutUndo[key]?.undo).toBe(`Add a duck region at ${shots[1].shot}`);
    // drawn: a span down the lanes over the clip, a tab on the hits lane that says what it does
    const span = el.querySelector<HTMLElement>(".h3-snd-region")!;
    expect(span.className).toContain("h3-snd-region-forward");
    expect(span.style.left).toBe("100px");
    expect(span.style.width).toBe("100px");
    const tab = el.querySelector<HTMLElement>(".h3-snd-region-tab")!;
    expect(tab.textContent).toBe("Score forward");
    expect(tab.title).toContain("Score forward: the music doesn't dip under the lines here; the dialogue -4 dB instead");

    // its menu opened with it: its own dip, -20 dB on the music, the dialogue as it is
    let menu = document.querySelector<HTMLElement>(".h3-snd-regionmenu")!;
    expect(menu).not.toBeNull();
    expect(menu.querySelector<HTMLInputElement>("input[data-region-mode=forward]")!.checked).toBe(true);
    await act(async () => menu.querySelector<HTMLInputElement>("input[data-region-mode=custom]")!.click());
    const type = async (input: HTMLInputElement, v: string) => {
      const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
      await act(async () => {
        set.call(input, v);
        input.dispatchEvent(new Event("input", { bubbles: true }));
      });
    };
    await type(menu.querySelector<HTMLInputElement>("input[data-region-field=music]")!, "-20");
    await type(menu.querySelector<HTMLInputElement>("input[data-region-field=dialogue]")!, "");
    await act(async () => [...menu.querySelectorAll("button")].find((b) => b.textContent === "Apply")!.click());
    await mixSettled();
    expect(currentMix()!.mix.regions![0]).toMatchObject({ music_duck_db: -20 });
    expect(currentMix()!.mix.regions![0].dialogue_db).toBeUndefined();
    expect(store.get().cutUndo[key]?.undo).toBe("Give a duck region its own dip");
    expect(el.querySelector(".h3-snd-region")!.className).toContain("h3-snd-region-custom");
    expect(el.querySelector(".h3-snd-region-tab")!.textContent).toBe("Dip -20 dB");

    // its tab's end dragged 50 px left: the region ends halfway through the clip
    const edge = el.querySelector<HTMLElement>("[data-region-edge=\"0:to\"]")!;
    await act(async () => edge.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, button: 0, clientX: 200, clientY: 5 })));
    await act(async () => window.dispatchEvent(new PointerEvent("pointermove", { clientX: 150, clientY: 5 })));
    expect(document.querySelector(".h3-trim-tip")?.textContent).toContain("the duck region's end");
    await act(async () => window.dispatchEvent(new PointerEvent("pointerup", {})));
    await mixSettled();
    expect(currentMix()!.mix.regions![0].to).toEqual({ shot: shots[1].shot, frame: Math.round((it1.inT + it1.dur / 2) * 24) });
    expect(store.get().cutUndo[key]?.undo).toBe("Move a duck region's end");

    // the lane menu over it offers it; its menu deletes it
    await act(async () => music.dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, clientX: 120, clientY: 100 })));
    const edit = document.querySelector<HTMLButtonElement>(".h3-snd-pop button[data-region=edit]")!;
    expect(edit.textContent).toContain("Duck region here: Dip -20 dB");
    await act(async () => edit.click());
    menu = document.querySelector<HTMLElement>(".h3-snd-regionmenu")!;
    await act(async () => menu.querySelector<HTMLButtonElement>("button[data-region=delete]")!.click());
    await mixSettled();
    expect(currentMix()!.mix.regions).toBeUndefined();
    expect(el.querySelector(".h3-snd-region")).toBeNull();
  });

  it("a duck region Shift+dragged on the hits lane", async () => {
    const shots = store.get().status[statusKey(EP, "proxy")]!.shots;
    await columns();
    const hits = el.querySelector<HTMLElement>(".h3-snd-hits")!;
    await act(async () => hits.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, button: 0, shiftKey: true, clientX: 50, clientY: 5 })));
    await act(async () => window.dispatchEvent(new PointerEvent("pointermove", { clientX: 150, clientY: 5 })));
    expect(document.querySelector(".h3-trim-tip")?.textContent).toContain("a new duck region");
    await act(async () => window.dispatchEvent(new PointerEvent("pointerup", {})));
    await mixSettled();
    const r = currentMix()!.mix.regions![0];
    expect(r.from.shot).toBe(shots[0].shot);
    expect(r.to.shot).toBe(shots[1].shot);
    expect(r.music_duck_db).toBe(0);
    expect(document.querySelector(".h3-snd-regionmenu")).not.toBeNull();
  });

  it("every lane has a menu, kept on screen", async () => {
    store.set({ sound: true });
    await act(async () => root.render(createElement(Timeline)));
    const lanes = [...el.querySelectorAll<HTMLElement>(".h3-snd-lane")];
    const menuOf = async (lane: HTMLElement) => {
      await act(async () => lane.dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, clientX: 300, clientY: 790 })));
      const m = document.querySelector<HTMLElement>(".h3-snd-pop");
      const texts = [...(m?.querySelectorAll("button") ?? [])].map((b) => b.textContent ?? "");
      await act(async () => window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })));
      return texts;
    };
    // hits, then dialogue, effects, ambience, music (happy-dom lays nothing out, so no shot
    // is under the click: the dialogue lane's own-sound entries, which need one, aren't there)
    expect((await menuOf(lanes[0])).some((t) => t.includes("New cue"))).toBe(true);
    expect((await menuOf(lanes[1])).some((t) => t.includes("Add a sound file"))).toBe(true);
    expect((await menuOf(lanes[2])).some((t) => t.includes("Add a sound file"))).toBe(true);
    expect((await menuOf(lanes[3])).some((t) => t.includes("ambience bed"))).toBe(true);
    const music = await menuOf(lanes[4]);
    expect(music.some((t) => t.includes("New cue")) && music.some((t) => t.includes("Add a sound file"))).toBe(true);
  });

  it("tracks of your own: a lane head's menu adds, renames and deletes a track (its items moved)", async () => {
    store.set({ sound: true });
    await act(async () => root.render(createElement(Timeline)));
    const headMenu = async (i: number) => {
      const btn = el.querySelectorAll<HTMLButtonElement>(".h3-snd-head button[aria-label$='track menu']")[i];
      await act(async () => btn.click());
      return document.querySelector<HTMLElement>(".h3-snd-trackmenu")!;
    };
    const type = async (input: HTMLInputElement, v: string) => {
      const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
      await act(async () => {
        set.call(input, v);
        input.dispatchEvent(new Event("input", { bubbles: true }));
      });
    };
    const button = (m: HTMLElement, f: (t: string) => boolean) => [...m.querySelectorAll("button")].find((b) => f(b.textContent ?? ""))!;
    // a music track called Song, from the Music lane's menu
    let m = await headMenu(3);
    expect(m.querySelector<HTMLSelectElement>("select")!.value).toBe("music");
    await type(m.querySelectorAll<HTMLInputElement>("input")[1], "Song");
    await act(async () => button(m, (t) => t.includes("Add")).click());
    await mixSettled();
    expect(currentMix()!.mix.track_list?.map((t) => t.id)).toEqual(["dialogue", "effects", "ambience", "music", "song"]);
    expect([...el.querySelectorAll(".h3-snd-name")].map((x) => x.textContent)).toEqual(["Dialogue", "Effects", "Ambience", "Music", "Song"]);
    expect(el.querySelectorAll(".h3-snd-lane")).toHaveLength(6);

    // Music renamed Score
    m = await headMenu(3);
    await type(m.querySelectorAll<HTMLInputElement>("input")[0], "Score");
    await act(async () => button(m, (t) => t === "Rename").click());
    await mixSettled();
    expect(currentMix()!.mix.track_list?.[3]).toEqual({ id: "music", kind: "music", label: "Score" });

    // Ambience deleted: its loop asks, and moves to the track chosen
    m = await headMenu(2);
    await act(async () => button(m, (t) => t.includes("Delete Ambience")).click());
    expect(m.textContent).toContain("has 1 item on it");
    const selects = m.querySelectorAll<HTMLSelectElement>("select");
    const to = selects[selects.length - 1];
    await act(async () => {
      to.value = "song";
      to.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await act(async () => button(m, (t) => t.startsWith("Move it to")).click());
    await mixSettled();
    const mix = currentMix()!.mix;
    expect(mix.track_list?.map((t) => t.id)).toEqual(["dialogue", "effects", "music", "song"]);
    expect(mix.items?.[0].track).toBe("song");
    expect(store.get().cutUndo[statusKey(EP, "proxy")]?.undo).toBe("Delete Ambience (1 item to Song)");

    // the dialogue track can be renamed, not deleted
    m = await headMenu(0);
    expect([...m.querySelectorAll("button")].some((b) => (b.textContent ?? "").includes("Delete"))).toBe(false);
    expect(m.textContent).toContain("can be renamed, not deleted");
  });

  it("a menu near the window's foot opens above the click", async () => {
    const { onScreen } = await import("../src/components/SoundLanes");
    const H = window.innerHeight;
    expect(onScreen(100, H - 10, { width: 200, height: 150 }).top).toBe(H - 10 - 150);
    expect(onScreen(100, 50, { width: 200, height: 150 }).top).toBe(50);
    expect(onScreen(window.innerWidth - 20, 50, { width: 200, height: 150 }).left).toBe(window.innerWidth - 204);
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
