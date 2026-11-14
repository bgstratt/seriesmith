import { describe, expect, it } from "vitest";
import { dbGain, levelClips, levelRequestKey, levelled, playAllDb } from "../src/lib/levels";
import type { PlayEntry } from "../src/lib/mix";
import type { PlayItem } from "../src/lib/playlist";
import type { MixResult, MixVoice } from "../src/types";

const item = (shot: string, over: Partial<PlayItem> = {}): PlayItem =>
  ({ shot, index: 0, pass: "final", take: 1, mp4: `renders/${shot}/${shot}_t01.mp4`, why: null, start: 0, dur: 3,
     inT: 0.5, outT: 3.5, trimIn: 12, trimOut: 0, total: 96, audioIn: null, audioOut: null, fadeIn: 0, fadeOut: 0,
     dissolveIn: 0, dissolveOut: 0, source: null, ...over }) as unknown as PlayItem;

const voice = (shot: string, over: Partial<MixVoice> = {}): MixVoice =>
  ({ shot, take: 1, state: "ok", lines: true, path: `renders/${shot}/${shot}_t01.voice.wav`, ...over }) as unknown as MixVoice;

describe("levelClips (Play all's levelling, lib/levels.ts)", () => {
  it("the take's own sound over the span the cut plays", () => {
    expect(levelClips([item("sh010")], undefined)).toEqual([{ shot: "sh010", path: "renders/sh010/sh010_t01.mp4", from: 0.5, to: 3.5 }]);
  });
  it("a voice stem when voices only plays it; nothing for a shot with no lines; a placeholder left out", () => {
    const res = { mix: { tracks: { dialogue: { voices_only: true } } }, voices: { shots: [voice("sh010"), voice("sh020", { lines: false })] } } as unknown as MixResult;
    const got = levelClips([item("sh010"), item("sh020"), item("sh030", { mp4: null })], res);
    expect(got).toEqual([{ shot: "sh010", path: "renders/sh010/sh010_t01.voice.wav", from: 0.5, to: 3.5 }]);
  });
  it("a clip's own audio source, placed as sourcePlan places it", () => {
    const it2 = item("sh010", { source: { path: "audio/dub.wav", start: 10, offset: -0.5, gain: 1 } } as Partial<PlayItem>);
    expect(levelClips([it2], undefined)).toEqual([{ shot: "sh010", path: "audio/dub.wav", from: 10.5, to: 13.5 }]);
    const late = item("sh010", { source: { path: "audio/dub.wav", start: 10, offset: 1, gain: 1 } } as Partial<PlayItem>);
    expect(levelClips([late], undefined)).toEqual([{ shot: "sh010", path: "audio/dub.wav", from: 10, to: 12 }]);
    expect(levelClips([item("sh010", { source: { path: null, start: 0, offset: 0, gain: 1 } } as Partial<PlayItem>)], undefined)).toEqual([]);
  });
  it("a changed clip or limit is another request", () => {
    const c = levelClips([item("sh010")], undefined);
    expect(levelRequestKey(c, 9)).toBe(levelRequestKey(levelClips([item("sh010")], undefined), 9));
    expect(levelRequestKey(c, 9)).not.toBe(levelRequestKey(c, 6));
    expect(levelRequestKey(c, 9)).not.toBe(levelRequestKey(levelClips([item("sh010", { inT: 1 })], undefined), 9));
  });
});

describe("playAllDb: turned down only", () => {
  it("every clip less the biggest boost, so none goes over its own level", () => {
    const db = playAllDb({ key: "", limit: 9, gains: { a: -4, b: 3 } }, ["a", "b", "c"]);
    expect(db).toEqual({ a: -7, b: 0, c: -3 });              // c (no lines) keeps the balance
  });
  it("nothing when levelling is off or nothing moved", () => {
    expect(playAllDb({ key: "", limit: 0, gains: { a: 3 } }, ["a"])).toEqual({});
    expect(playAllDb({ key: "", limit: 9, gains: {} }, ["a"])).toEqual({});
    expect(playAllDb(undefined, ["a"])).toEqual({});
  });
  it("only cuts: all moves down when every gain is", () => {
    expect(playAllDb({ key: "", limit: 9, gains: { a: -2, b: -6 } }, ["a", "b"])).toEqual({ a: -2, b: -6 });
  });
  it("stems and sources carry their clip's change", () => {
    const e = (id: string, gain = 1): PlayEntry => ({ id, track: "dialogue", path: "p", start: 0, end: 1, offset: 0, gain, points: [], fadeIn: 0, fadeOut: 0, loop: false });
    const out = levelled([e("voice:a"), e("source:b", 2), e("bed:x")], { a: -6, b: -20 });
    expect(out[0].gain).toBeCloseTo(dbGain(-6));
    expect(out[1].gain).toBeCloseTo(0.2);
    expect(out[2].gain).toBe(1);
  });
});
