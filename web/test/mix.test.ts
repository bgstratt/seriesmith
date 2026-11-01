// The episode's mix (docs/SOUND.md): anchors on the cut's clock and the
// timeline, the edits as new mixes, and the actions' save / undo round trip.
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  addHit, addItem, anchorTime, cleanHit, entryEnd, entryLevel, itemSpan, layout, moveItem, newId, patchHit, patchItem, playPlan,
  removeHit, removeItem, setTrack, shiftAnchor, timeAnchor, timeX, trackGains, trimItem, xAnchor, xTime, type ClipBox,
} from "../src/lib/mix";
import type { PlayItem } from "../src/lib/playlist";
import type { Mix, MixItem } from "../src/types";

/** A clip on the cut's clock: `trimIn` frames off its head at 24 fps. */
function clip(shot: string, start: number, dur: number, trimIn = 0, extra: Partial<PlayItem> = {}): PlayItem {
  const inT = trimIn / 24;
  return {
    shot, index: 0, pass: "final", take: 1, mp4: `${shot}.mp4`, why: "", start, dur, inT, outT: inT + dur, trimIn, trimOut: 0,
    total: null, audioIn: null, audioOut: null, fadeIn: 0, fadeOut: 0, dissolveIn: 0, dissolveOut: 0, ...extra,
  };
}

// sh010: 2 s from 0; sh020: 3 s from 2, its first 12 frames trimmed off; sh030: 1 s from 5
const ITEMS: PlayItem[] = [clip("sh010", 0, 2), clip("sh020", 2, 3, 12), clip("sh030", 5, 1)].map((x, i) => ({ ...x, index: i }));

describe("anchors on the cut's clock", () => {
  it("counts a frame of the take from its first frame, before trims", () => {
    expect(anchorTime(ITEMS, { shot: "sh010", frame: 24 }, 24)).toBe(1);
    // frame 12 of sh020 is the first it plays: the clip's start
    expect(anchorTime(ITEMS, { shot: "sh020", frame: 12 }, 24)).toBe(2);
    expect(anchorTime(ITEMS, { shot: "sh020", frame: 36 }, 24)).toBe(3);
    // a trimmed-off frame plays before the clip (as mix.place puts it)
    expect(anchorTime(ITEMS, { shot: "sh020", frame: 0 }, 24)).toBe(1.5);
    expect(anchorTime(ITEMS, { shot: "sh999", frame: 0 }, 24)).toBeNull();
  });

  it("goes back from a time to the clip playing and its frame", () => {
    expect(timeAnchor(ITEMS, 1, 24)).toEqual({ shot: "sh010", frame: 24 });
    expect(timeAnchor(ITEMS, 2.5, 24)).toEqual({ shot: "sh020", frame: 24 });
    expect(timeAnchor(ITEMS, 5.5, 24)).toEqual({ shot: "sh030", frame: 12 });
  });

  it("a dissolve's half-overlap matches mix.shot_origins", () => {
    // a 12-frame dissolve into b: Play all cuts at its middle, so b starts 6 frames later in its file
    const d = 12 / 24;
    const a = clip("a", 0, 2 - d / 2);
    const b = { ...clip("b", 2 - d / 2, 2 - d / 2), inT: d / 2, index: 1 };
    // assemble lays b from 2 - d: its frame 0 plays there
    expect(anchorTime([a, b], { shot: "b", frame: 0 }, 24)).toBeCloseTo(2 - d);
  });

  it("shifts an anchor along the cut, onto the clip it lands in", () => {
    expect(shiftAnchor(ITEMS, { shot: "sh010", frame: 36 }, 1, 24)).toEqual({ shot: "sh020", frame: 24 });
    expect(shiftAnchor(ITEMS, { shot: "sh020", frame: 12 }, -10, 24)).toEqual({ shot: "sh010", frame: 0 });
  });
});

describe("the timeline's x, clip by clip", () => {
  // sh010 is 2 s at 40 px/s; sh020 a MIN_CLIP-wide 30 px for 3 s (10 px/s), after a sequence label; sh030 stub-free
  const boxes: ClipBox[] = [
    { shot: "sh010", left: 6, width: 80 }, { shot: "sh020", left: 120, width: 30 }, { shot: "sh030", left: 152, width: 40 },
    { shot: "out", left: 194, width: 16 },
  ];
  const lay = layout(boxes, ITEMS);

  it("measures only the clips Play all plays, each at its own scale", () => {
    expect(lay.map((l) => [l.shot, l.pps])).toEqual([["sh010", 40], ["sh020", 10], ["sh030", 40]]);
  });

  it("maps time to x and back", () => {
    expect(timeX(lay, 1)).toBe(46);
    expect(timeX(lay, 3.5)).toBe(135);
    expect(xTime(lay, 46)).toBe(1);
    expect(xTime(lay, 135)).toBe(3.5);
    // a gap (the sequence label): the nearer clip's edge
    expect(xTime(lay, 90)).toBe(2);
    expect(xTime(lay, 115)).toBe(2);
  });

  it("an x is an anchor in the clip under it", () => {
    expect(xAnchor(lay, 46, 24)).toEqual({ shot: "sh010", frame: 24 });
    expect(xAnchor(lay, 135, 24)).toEqual({ shot: "sh020", frame: 48 });
    expect(xAnchor(lay, 0, 24)).toEqual({ shot: "sh010", frame: 0 });
  });
});

const ITEM: MixItem = { id: "m01", track: "music", path: "audio/cue.wav", in: { shot: "sh010", frame: 24 }, out: { shot: "sh020", frame: 36 } };

describe("items", () => {
  it("spans from in to out, or to the file's end", () => {
    expect(itemSpan(ITEMS, ITEM, 24, null)).toEqual({ start: 1, end: 3 });
    const open = { ...ITEM, out: null, offset: 0.5 };
    expect(itemSpan(ITEMS, open, 24, null)).toEqual({ start: 1, end: null });
    expect(itemSpan(ITEMS, open, 24, 2.5)).toEqual({ start: 1, end: 3 });
    // never past the cut
    expect(itemSpan(ITEMS, open, 24, 60)?.end).toBe(6);
    expect(itemSpan(ITEMS, { ...ITEM, in: { shot: "gone", frame: 0 } }, 24, null)).toBeNull();
  });

  it("new ids follow the track's prefix", () => {
    expect(newId("m", ["m01", "m03"])).toBe("m02");
    expect(newId("fx", [])).toBe("fx01");
  });

  it("adds, changes and removes immutably, defaults dropped", () => {
    const m0: Mix = { hits: [{ id: "h01", at: { shot: "sh010", frame: 0 } }] };
    const m1 = addItem(m0, { ...ITEM, gain_db: 0, fade_in: 0, loop: false, label: " " });
    expect(m0.items).toBeUndefined();
    expect(m1.items).toEqual([ITEM]);
    const m2 = patchItem(m1, "m01", { gain_db: -3.04, fade_in: 12.4, loop: true, label: "theme" })!;
    expect(m2.items![0]).toEqual({ ...ITEM, gain_db: -3, fade_in: 12, loop: true, label: "theme" });
    expect(m1.items![0]).toEqual(ITEM);
    expect(patchItem(m1, "nope", {})).toBeNull();
    expect(removeItem(m2, "m01")).toEqual(m0);
  });

  it("keeps what the UI doesn't edit (breakpoints, regions) through an edit", () => {
    const m: Mix = {
      items: [{ ...ITEM, points: [{ at: { shot: "sh010", frame: 30 }, db: 3 }] }],
      regions: [{ from: { shot: "sh010", frame: 0 }, to: { shot: "sh020", frame: 20 }, music_duck_db: 0 }],
      duck: { attack_ms: 30 },
    };
    const m2 = patchItem(m, "m01", { gain_db: -6 })!;
    expect(m2.items![0].points).toEqual(m.items![0].points);
    expect(m2.regions).toBe(m.regions);
    expect(m2.duck).toBe(m.duck);
  });

  it("a move re-anchors in, and out by as much", () => {
    const m = moveItem({ items: [ITEM] }, "m01", { shot: "sh020", frame: 24 }, ITEMS, 24)!;
    // in moved from 1 s to 2.5 s: out from 3 s to 4.5 s, frame 48 of sh020's take
    expect(m.items![0].in).toEqual({ shot: "sh020", frame: 24 });
    expect(m.items![0].out).toEqual({ shot: "sh020", frame: 72 });
    expect(moveItem({ items: [ITEM] }, "m01", ITEM.in, ITEMS, 24)).toBeNull();
  });

  it("a head trim keeps the sound where it was; a tail trim sets out", () => {
    const m = trimItem({ items: [ITEM] }, "m01", "in", { shot: "sh010", frame: 36 }, ITEMS, 24, null)!;
    expect(m.items![0]).toMatchObject({ in: { shot: "sh010", frame: 36 }, offset: 0.5 });
    // not before the file's start
    expect(trimItem({ items: [ITEM] }, "m01", "in", { shot: "sh010", frame: 0 }, ITEMS, 24, null)).toBeNull();
    // a loop's head moves alone
    const loop = trimItem({ items: [{ ...ITEM, loop: true }] }, "m01", "in", { shot: "sh010", frame: 36 }, ITEMS, 24, null)!;
    expect(loop.items![0].offset).toBeUndefined();
    // the tail
    const t = trimItem({ items: [ITEM] }, "m01", "out", { shot: "sh030", frame: 6 }, ITEMS, 24, null)!;
    expect(t.items![0].out).toEqual({ shot: "sh030", frame: 6 });
    // never past the other edge
    expect(trimItem({ items: [ITEM] }, "m01", "out", { shot: "sh010", frame: 10 }, ITEMS, 24, null)).toBeNull();
    expect(trimItem({ items: [ITEM] }, "m01", "in", { shot: "sh030", frame: 0 }, ITEMS, 24, null)).toBeNull();
  });
});

describe("hits", () => {
  it("add, change, remove, with kind and must's defaults dropped", () => {
    const { mix, id } = addHit({}, { shot: "sh020", frame: 17 }, "the door bursts");
    expect(id).toBe("h01");
    expect(mix.hits).toEqual([{ id: "h01", name: "the door bursts", at: { shot: "sh020", frame: 17 } }]);
    const m2 = patchHit(mix, "h01", { kind: "arrive", must: false })!;
    expect(m2.hits![0]).toMatchObject({ kind: "arrive", must: false });
    const m3 = patchHit(m2, "h01", { kind: "accent", must: true, name: "" })!;
    expect(m3.hits![0]).toEqual({ id: "h01", at: { shot: "sh020", frame: 17 } });
    expect(cleanHit({ id: "x", at: { shot: "a", frame: 0 }, kind: "drop", must: true })).toEqual({ id: "x", at: { shot: "a", frame: 0 }, kind: "drop" });
    expect(removeHit(m3, "h01")).toEqual({});
    expect(addHit(m3, { shot: "sh010", frame: 0 }).id).toBe("h02");
  });
});

describe("tracks and playback", () => {
  it("a track's settings drop their defaults", () => {
    let m = setTrack({}, "music", { gain_db: -3 });
    expect(m).toEqual({ tracks: { music: { gain_db: -3 } } });
    m = setTrack(m, "music", { gain_db: 0 });
    expect(m).toEqual({});
    expect(setTrack({}, "effects", { gain_db: 40 }).tracks!.effects!.gain_db).toBe(12);
  });

  it("faders sit on the series config's, and mute and solo silence", () => {
    const series = { tracks: { music: { gain_db: -6 } } };
    expect(trackGains({ mix: {}, series }).music).toBeCloseTo(0.501, 3);
    expect(trackGains({ mix: { tracks: { music: { gain_db: -20 } } }, series }).music).toBeCloseTo(0.1);
    const g = trackGains({ mix: { tracks: { effects: { solo: true }, dialogue: { mute: true } } }, series: {} });
    expect(g).toEqual({ dialogue: 0, effects: 1, ambience: 0, music: 0 });
  });

  it("plans each item on the cut's clock with its gain and fades", () => {
    const mix: Mix = { items: [{ ...ITEM, gain_db: -6, fade_in: 12, fade_out: 24 }, { id: "a01", track: "ambience", path: "b.wav", in: { shot: "sh020", frame: 0 }, loop: true }, { ...ITEM, id: "gone", in: { shot: "x", frame: 0 } }] };
    const plan = playPlan(ITEMS, mix, 24);
    expect(plan.map((e) => e.id)).toEqual(["m01", "a01"]);
    expect(plan[0]).toMatchObject({ start: 1, end: 3, offset: 0, fadeIn: 0.5, fadeOut: 1, loop: false });
    expect(plan[0].gain).toBeCloseTo(0.501, 3);
    expect(entryLevel(plan[0], 1.25, 3)).toBeCloseTo(0.2506, 3);
    expect(entryLevel(plan[0], 2, 3)).toBeCloseTo(0.501, 3);
    expect(entryLevel(plan[0], 2.5, 3)).toBeCloseTo(0.2506, 3);
    expect(plan[1]).toMatchObject({ start: 1.5, end: null, loop: true });
    expect(entryEnd(plan[1], 2, 6)).toBe(3.5);
    expect(entryEnd(plan[1], 60, 6)).toBe(6);
  });
});

// ---------------------------------------------------------------------------
// the actions, on the mock
// ---------------------------------------------------------------------------

import { refreshEpisode } from "../src/actions";
import { cutSettled, redoCut, resetCutHistory, undoCut } from "../src/cutActions";
import { setApi, setHost, type Host } from "../src/host";
import { createMockApi } from "../src/mock/mockApi";
import { addMixHit, currentMix, dropOnLane, loadMix, mixSettled, moveMixItem, setTrackMix } from "../src/mixActions";
import { initialState, statusKey, store } from "../src/store";

describe("the mix in the editor", () => {
  let api: ReturnType<typeof createMockApi>;
  let EP: string;
  const toasts: string[] = [];

  beforeEach(async () => {
    toasts.length = 0;
    setHost({ on: () => () => {}, toast: (_s, summary) => void toasts.push(summary), show: () => {} } as Host);
    api = createMockApi(() => {}, { latency: 0 });
    setApi(api);
    EP = (await api.episodes())[0].ep;
    store.set(initialState());
    resetCutHistory();
    store.set({ ep: EP, pass: "proxy" });
    await refreshEpisode(EP, "proxy");
    await loadMix(EP, "proxy");
  });
  afterEach(() => store.set(initialState()));

  it("is fetched with the pass's status", () => {
    expect(store.get().mix[statusKey(EP, "proxy")]?.mix).toEqual({});
    expect(store.get().mix[statusKey(EP, "proxy")]?.defaults.tracks).toEqual(["dialogue", "effects", "ambience", "music"]);
  });

  it("a dropped file is imported and laid where it was dropped, then moved, undone and redone", async () => {
    const file = new File([new Uint8Array(16)], "harbour.wav", { type: "audio/wav" });
    const shot = store.get().status[statusKey(EP, "proxy")]!.shots[0].shot;
    expect(await dropOnLane("ambience", file, { shot, frame: 5 })).toBe(true);
    const it = currentMix()!.mix.items![0];
    expect(it).toMatchObject({ id: "amb01", track: "ambience", path: "audio/harbour.wav", in: { shot, frame: 5 }, label: "harbour" });
    expect(it.out).toBeUndefined();
    // the server has it
    expect((await api.getMix(EP, "proxy")).mix.items).toHaveLength(1);

    expect(await moveMixItem("amb01", { shot, frame: 9 })).toBe(true);
    expect(currentMix()!.mix.items![0].in.frame).toBe(9);
    expect(store.get().cutUndo[statusKey(EP, "proxy")]?.undo).toBe("Move amb01");
    await undoCut();
    await mixSettled();
    expect(currentMix()!.mix.items![0].in.frame).toBe(5);
    expect((await api.getMix(EP, "proxy")).mix.items![0].in.frame).toBe(5);
    await redoCut();
    await mixSettled();
    expect(currentMix()!.mix.items![0].in.frame).toBe(9);
    await cutSettled();
  });

  it("faders, hits; a refused save goes back", async () => {
    expect(await setTrackMix("music", { gain_db: -4 })).toBe(true);
    expect(currentMix()!.mix.tracks).toEqual({ music: { gain_db: -4 } });
    const shot = store.get().status[statusKey(EP, "proxy")]!.shots[1].shot;
    expect(await addMixHit({ shot, frame: 3 }, "reveal")).toBe("h01");
    expect(currentMix()!.mix.hits).toEqual([{ id: "h01", name: "reveal", at: { shot, frame: 3 } }]);
    // no playhead and no anchor: nothing added
    expect(await addMixHit()).toBeNull();
    // a file that isn't there: 404, rolled back
    const before = currentMix()!.mix;
    const { editMix } = await import("../src/mixActions");
    expect(await editMix("bad", (m) => addItem(m, { id: "x01", track: "effects", path: "audio/nope.wav", in: { shot, frame: 0 } }))).toBe(false);
    expect(currentMix()!.mix).toEqual(before);
  });
});
