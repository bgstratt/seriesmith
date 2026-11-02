// Cutting to music (docs/SOUND.md phase 5): the music's beats on the cut's clock,
// which of them stay put while a clip's edge is dragged, and a trim snapped so the
// cut lands on one.
import { describe, expect, it } from "vitest";
import { beatLabel, cutBeats, fixedBeats, gridBeats, snapTrim, type BeatGrid, type MixBeats } from "../src/lib/beats";
import { clampTrim } from "../src/lib/cutEdit";
import type { PlayItem } from "../src/lib/playlist";
import type { Mix } from "../src/types";

function clip(shot: string, start: number, dur: number, trimIn = 0, extra: Partial<PlayItem> = {}): PlayItem {
  const inT = trimIn / 24;
  return {
    shot, index: 0, pass: "final", take: 1, mp4: `${shot}.mp4`, why: "", start, dur, inT, outT: inT + dur, trimIn, trimOut: 0,
    total: dur * 24 + trimIn, audioIn: null, audioOut: null, fadeIn: 0, fadeOut: 0, dissolveIn: 0, dissolveOut: 0, ...extra,
  };
}

// sh010: 2 s from 0; sh020: 3 s from 2, its first 12 frames trimmed off; sh030: 3 s from 5
const ITEMS: PlayItem[] = [clip("sh010", 0, 2), clip("sh020", 2, 3, 12), clip("sh030", 5, 3)].map((x, i) => ({ ...x, index: i }));

// 120 bpm: a beat every 0.5 s, the first at 0.25, the first downbeat on the second beat (0.75)
const GRID: BeatGrid = { bpm: 120, first: 0.25, downbeat: 0.75, beats_per_bar: 4, seconds: 30, steady: true, source: "measured" };

describe("a grid's beats", () => {
  it("steps from the first beat and marks every bar's first", () => {
    const got = gridBeats(GRID, 0, 3);
    expect(got.map(([s]) => s)).toEqual([0.25, 0.75, 1.25, 1.75, 2.25, 2.75]);
    expect(got.map(([, d]) => d)).toEqual([false, true, false, false, false, true]);
    expect(gridBeats(GRID, 1, 1.3).map(([s]) => s)).toEqual([1.25]);
    expect(gridBeats(GRID, 2, 1)).toEqual([]);
  });
});

describe("the music's beats on the cut's clock", () => {
  const mix: Mix = { items: [{ id: "song", track: "music", path: "audio/song.wav", in: { shot: "sh010", frame: 0 }, offset: 1 }] };
  const beats: MixBeats = { items: [{ id: "song", path: "audio/song.wav", grid: GRID }], recording: null };

  it("places an item's beats from its in point, its offset into the file taken off", () => {
    const got = cutBeats(ITEMS, mix, beats, 24);
    // file 1.25 plays at cut 0.25; the downbeat at file 2.75 at 1.75; to the cut's end (8 s)
    expect(got[0]).toEqual({ t: 0.25, down: false, shot: "sh010" });
    expect(got[3]).toEqual({ t: 1.75, down: true, shot: "sh010" });
    expect(got[got.length - 1].t).toBeCloseTo(7.75);
  });

  it("leaves out a grid with no pulse, an item no longer in the mix, and uses the recording when no music has beats", () => {
    expect(cutBeats(ITEMS, mix, { ...beats, items: [{ ...beats.items[0], grid: { ...GRID, steady: false } }] }, 24)).toEqual([]);
    expect(cutBeats(ITEMS, {}, beats, 24)).toEqual([]);
    const rec: MixBeats = { items: [], recording: { path: "audio/song.wav", grid: GRID } };
    // the recording from the first clip's window (none: the base, 10 s in)
    const got = cutBeats(ITEMS, {}, rec, 24, 10);
    expect(got[0]).toEqual({ t: 0.25, down: false, shot: null });
    expect(got[1]).toEqual({ t: 0.75, down: true, shot: null });
    // with music beats there, the recording's aren't added
    expect(cutBeats(ITEMS, mix, { ...beats, recording: rec.recording }, 24).every((b) => b.shot === "sh010")).toBe(true);
  });

  it("names a beat by its bar", () => {
    const got = cutBeats(ITEMS, mix, beats, 24);
    expect(beatLabel(got[3], got)).toBe("bar 1");
    expect(beatLabel(got[5], got)).toBe("bar 1 beat 3");
    expect(beatLabel(got[7], got)).toBe("bar 2");
    expect(beatLabel(got[0], got)).toBe("a beat");
  });
});

describe("a trim's edge snapped to a beat", () => {
  // music anchored to sh010 (stays), to sh020 and to sh030
  const all = [
    { t: 3.75, down: true, shot: "sh010" }, { t: 4.25, down: false, shot: "sh010" },
    { t: 4.6, down: true, shot: "sh020" }, { t: 4.1, down: false, shot: "sh030" }, { t: 4.4, down: false, shot: null },
  ];

  it("keeps the beats that don't move with the trim", () => {
    // sh020's tail: music on sh010 and sh020 stays, sh030's moves with it, the recording stays
    expect(fixedBeats(all, ITEMS, "sh020", "out").map((b) => b.t)).toEqual([3.75, 4.25, 4.6, 4.4]);
    // its head: the music on sh020 moves with its frames
    expect(fixedBeats(all, ITEMS, "sh020", "in").map((b) => b.t)).toEqual([3.75, 4.25, 4.4]);
    // the first clip's head moves the recording too
    expect(fixedBeats(all, ITEMS, "sh010", "in").map((b) => b.t)).toEqual([]);
  });

  const clamp = (total: number) => (side: "in" | "out", want: number, other: number) =>
    side === "in" ? clampTrim("in", want, total, 0, other) : clampTrim("out", want, total, other, 0);
  const it2 = ITEMS[1];          // sh020 ends at 5 s; its take is 84 frames, 12 off the head
  const base = { it: it2, total: 84, a0: 12, b0: 0, fps: 24, clamp: clamp(84) };

  it("moves the cut at the clip's end onto the nearest beat within reach, a downbeat from further", () => {
    const beats = fixedBeats(all, ITEMS, "sh020", "out");
    // dragged to end at 4.3 s (17 frames off the tail): the beat at 4.25 is 0.05 s away
    let r = snapTrim({ ...base, side: "out", a: 12, b: 17, beats, tol: 0.1, downTol: 0.2 });
    expect(r.beat?.t).toBe(4.25);
    expect(r.b).toBe(18);                     // 72 - 54 frames: the clip ends at 4.25
    // to end at 3.9 s: no beat within 0.1, the downbeat at 3.75 within 0.2
    r = snapTrim({ ...base, side: "out", a: 12, b: 26, beats, tol: 0.1, downTol: 0.2 });
    expect(r.beat).toMatchObject({ t: 3.75, down: true });
    expect(r.b).toBe(30);
    // nothing near: as dragged
    r = snapTrim({ ...base, side: "out", a: 12, b: 2, beats, tol: 0.05, downTol: 0.05 });
    expect(r).toEqual({ a: 12, b: 2, beat: null });
  });

  it("snaps a head trim by the same cut (the clip's end), and not past what the take has", () => {
    const beats = fixedBeats(all, ITEMS, "sh020", "in");
    const r = snapTrim({ ...base, side: "in", a: 29, b: 0, beats, tol: 0.1, downTol: 0.2 });
    // 29 off the head would end it at 4.29: onto 4.25, one more frame off the head
    expect(r.beat?.t).toBe(4.25);
    expect(r.a).toBe(30);
    // a beat past the take's end can't be reached: no snap
    const far = snapTrim({ ...base, side: "out", a: 12, b: 0, beats: [{ t: 5.1, down: true, shot: "sh010" }], tol: 0.2, downTol: 0.2 });
    expect(far.beat).toBeNull();
  });
});
