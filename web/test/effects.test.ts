// A shot's effects in the editor (docs/SOUND.md phase 4): what the mix keeps of them (the
// take, a level, mute, kept though stale), whether one is heard, and what Play all plays.
import { describe, expect, it } from "vitest";
import { addPoint, dbToGain, entryLevel, fxAnchor, fxHeard, fxKept, fxPlan, fxSettings, fxSpan, pickFxTake, removePoint, resetFxShape, setFx, trimFx } from "../src/lib/mix";
import type { PlayItem } from "../src/lib/playlist";
import type { MixFx } from "../src/types";

function clip(shot: string, start: number, dur: number, trimIn = 0): PlayItem {
  const inT = trimIn / 24;
  return {
    shot, index: 0, pass: "final", take: 1, mp4: `${shot}.mp4`, why: "", start, dur, inT, outT: inT + dur, trimIn, trimOut: 0,
    total: null, audioIn: null, audioOut: null, fadeIn: 0, fadeOut: 0, dissolveIn: 0, dissolveOut: 0,
  };
}

// sh010 2 s, sh020 3 s (12 frames trimmed off its head)
const ITEMS: PlayItem[] = [clip("sh010", 0, 2), clip("sh020", 2, 3, 12)].map((x, i) => ({ ...x, index: i }));

function laid(shot: string, f0: number, f1: number, extra: Partial<MixFx> = {}): MixFx {
  return { shot, take: 1, model: "h3_foley", path: `sound/fx/final/${shot}/t01.wav`, exists: true,
           in: { shot, frame: f0 }, out: { shot, frame: f1 }, start: 0, end: 0, offset: f0 / 24,
           gain_db: 0, mute: false, keep_stale: false, stale: null, heard: true, ...extra };
}

describe("what the mix keeps", () => {
  it("picks a take, keeps its level, drops a keep_stale", () => {
    expect(fxSettings({}, "sh010")).toBeNull();
    let m = pickFxTake({}, "sh010", 2);
    expect(m.fx).toEqual({ sh010: { take: 2 } });
    m = setFx(m, "sh010", { gain_db: -4.04, keep_stale: true });
    expect(m.fx).toEqual({ sh010: { take: 2, gain_db: -4, keep_stale: true } });
    m = pickFxTake(m, "sh010", 3);
    expect(m.fx).toEqual({ sh010: { take: 3, gain_db: -4 } });
    expect(setFx(m, "sh010", { gain_db: 0 }).fx).toEqual({ sh010: { take: 3 } });
    expect(pickFxTake(m, "sh010", null)).toEqual({});
    expect(setFx({}, "sh010", { mute: true })).toEqual({});        // nothing picked: nothing to set
  });

  it("keeps its trims, fades and points when another take is picked; Reset takes them out", () => {
    const at = { shot: "sh010", frame: 30 };
    let m = setFx(pickFxTake({}, "sh010", 1), "sh010", { trim_out: 20.4, fade_out: 6, trim_in: 0, points: [{ at, db: -6 }] });
    expect(m.fx).toEqual({ sh010: { take: 1, trim_out: 20, fade_out: 6, points: [{ at, db: -6 }] } });
    m = pickFxTake(m, "sh010", 2);
    expect(m.fx).toEqual({ sh010: { take: 2, trim_out: 20, fade_out: 6, points: [{ at, db: -6 }] } });
    expect(resetFxShape(m, "sh010").fx).toEqual({ sh010: { take: 2 } });
  });
});

describe("trimmed and levelled within its clip", () => {
  const f = laid("sh010", 0, 48);

  it("an edge dragged sets its trim (the clip's span unchanged), a frame clear of the other", () => {
    let m = pickFxTake({}, "sh010", 1);
    m = trimFx(m, "sh010", "out", 1.5, ITEMS, f, 24)!;
    expect(m.fx!.sh010).toEqual({ take: 1, trim_out: 12 });
    expect(fxSpan(ITEMS, f, 24)).toEqual({ start: 0, end: 2 });
    expect(fxKept(ITEMS, f, m, 24)).toEqual({ start: 0, end: 1.5 });
    expect(trimFx(m, "sh010", "out", 1.5, ITEMS, f, 24)).toBeNull();               // nothing changes
    m = trimFx(m, "sh010", "in", 1.9, ITEMS, f, 24)!;                               // past the other: a frame clear
    expect(m.fx!.sh010.trim_in).toBe(35);
    expect(trimFx(m, "sh010", "in", -1, ITEMS, f, 24)!.fx!.sh010.trim_in).toBeUndefined();
  });

  it("its points go on its own shot, as an item's", () => {
    const m = pickFxTake({}, "sh010", 1);
    expect(fxAnchor(ITEMS, f, 1, 24)).toEqual({ shot: "sh010", frame: 24 });
    const p = addPoint(m, { fx: "sh010" }, fxAnchor(ITEMS, f, 1, 24), ITEMS, 24, -3)!;
    expect(p.fx!.sh010.points).toEqual([{ at: { shot: "sh010", frame: 24 }, db: -3 }]);
    expect(removePoint(p, { fx: "sh010" }, 0)!.fx!.sh010).toEqual({ take: 1 });
    expect(addPoint({}, { fx: "sh010" }, { shot: "sh010", frame: 2 }, ITEMS, 24)).toBeNull();   // no effects picked
  });

  it("Play all plays only the kept span, faded, at its points", () => {
    const mix = { fx: { sh010: { take: 1, gain_db: -2, trim_in: 6, trim_out: 12, fade_out: 6, points: [{ at: { shot: "sh010", frame: 24 }, db: -6 }] } } };
    const [e] = fxPlan(ITEMS, [f], mix, 24);
    expect([e.start, e.end, e.offset, e.fadeOut]).toEqual([0.25, 1.5, 0.25, 0.25]);
    expect(20 * Math.log10(entryLevel(e, 1, e.end!))).toBeCloseTo(-8, 5);
    expect(entryLevel(e, 1.5, e.end!)).toBe(0);
    expect(fxPlan(ITEMS, [f], { fx: { sh010: { take: 1, trim_in: 24, trim_out: 24 } } }, 24)).toEqual([]);   // nothing left
  });
});

describe("heard and played", () => {
  const fx = [laid("sh010", 0, 48), laid("sh020", 12, 84, { stale: "made from t01; the cut plays t02" })];

  it("lays each at its clip, from the clip's first frame of the take", () => {
    expect(fxSpan(ITEMS, fx[0], 24)).toEqual({ start: 0, end: 2 });
    expect(fxSpan(ITEMS, fx[1], 24)).toEqual({ start: 2, end: 5 });
  });

  it("leaves out a stale one unless kept, and a muted one", () => {
    const mix = { fx: { sh010: { take: 1, gain_db: -6 }, sh020: { take: 1 } } };
    expect(fx.map((f) => fxHeard(mix, f))).toEqual([true, false]);
    let plan = fxPlan(ITEMS, fx, mix, 24);
    expect(plan.map((p) => [p.id, p.track, p.start, p.end, p.offset, p.loop])).toEqual([["fx:sh010", "effects", 0, 2, 0, false]]);
    expect(plan[0].gain).toBeCloseTo(dbToGain(-6));
    plan = fxPlan(ITEMS, fx, { fx: { sh010: { take: 1, mute: true }, sh020: { take: 1, keep_stale: true } } }, 24);
    expect(plan.map((p) => [p.id, p.start, p.end, p.offset])).toEqual([["fx:sh020", 2, 5, 0.5]]);
    // another take picked since the server laid it: not this one
    expect(fxHeard({ fx: { sh010: { take: 2 } } }, fx[0])).toBe(false);
  });
});
