// The places' ambience beds in the editor (docs/SOUND.md phase 3): a place's level and
// mute as the mix keeps them, and the beds Play all plays (looped, crossfaded at cuts).
import { describe, expect, it } from "vitest";
import { BED_XFADE, bedPlan, bedSettings, bedSpan, dbToGain, setBed } from "../src/lib/mix";
import type { PlayItem } from "../src/lib/playlist";
import type { MixBed } from "../src/types";

function clip(shot: string, start: number, dur: number, trimIn = 0): PlayItem {
  const inT = trimIn / 24;
  return {
    shot, index: 0, pass: "final", take: 1, mp4: `${shot}.mp4`, why: "", start, dur, inT, outT: inT + dur, trimIn, trimOut: 0,
    total: null, audioIn: null, audioOut: null, fadeIn: 0, fadeOut: 0, dissolveIn: 0, dissolveOut: 0,
  };
}

// sh010 2 s, sh020 3 s (12 frames trimmed), sh030 1 s
const ITEMS: PlayItem[] = [clip("sh010", 0, 2), clip("sh020", 2, 3, 12), clip("sh030", 5, 1)].map((x, i) => ({ ...x, index: i }));

function bed(place: string, first: string, f0: number, last: string, f1: number, extra: Partial<MixBed> = {}): MixBed {
  return { place, label: place, path: `../refs/_amb/${place}.wav`, exists: true, words: "", shots: [first, last],
           in: { shot: first, frame: f0 }, out: { shot: last, frame: f1 }, start: 0, end: 0, gain_db: 0, mute: false, ...extra };
}

describe("a place's settings", () => {
  it("keeps only what changes", () => {
    expect(bedSettings({}, "diner")).toEqual({ gain_db: 0, mute: false });
    const m = setBed({}, "diner", { gain_db: -3.04 });
    expect(m.beds).toEqual({ diner: { gain_db: -3 } });
    expect(setBed(m, "diner", { gain_db: 0 })).toEqual({});
    expect(setBed({}, "diner", { mute: true }).beds).toEqual({ diner: { mute: true } });
  });
});

describe("the beds Play all plays", () => {
  const beds = [bed("diner", "sh010", 0, "sh020", 84), bed("road", "sh030", 0, "sh030", 24)];

  it("follows the anchors", () => {
    expect(bedSpan(ITEMS, beds[0], 24)).toEqual({ start: 0, end: 5 });
    expect(bedSpan(ITEMS, beds[1], 24)).toEqual({ start: 5, end: 6 });
  });

  it("crossfades at the cut between two places, not at the cut's ends", () => {
    const plan = bedPlan(ITEMS, beds, {}, 24);
    expect(plan.map((p) => [p.start, p.end, p.fadeIn, p.fadeOut, p.loop, p.track]))
      .toEqual([[0, 5 + BED_XFADE / 2, 0, BED_XFADE, true, "ambience"], [5 - BED_XFADE / 2, 6, BED_XFADE, 0, true, "ambience"]]);
  });

  it("plays a place at its level, leaves out a muted one and one not made", () => {
    const plan = bedPlan(ITEMS, [...beds, bed("x", "sh030", 0, "sh030", 24, { exists: false })], { beds: { diner: { gain_db: -6 }, road: { mute: true } } }, 24);
    expect(plan.map((p) => p.id)).toEqual(["bed:diner:0"]);
    expect(plan[0].gain).toBeCloseTo(dbToGain(-6));
  });
});
