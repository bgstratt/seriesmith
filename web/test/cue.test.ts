// @vitest-environment happy-dom
//
// The cue window (docs/SOUND.md "The cue window"): the bar grid's arithmetic,
// a section edge dragged to whole bars, an arc point dragged to an anchor and
// a level, how the takes read; the Arc tab's shapes, drawing, smoothing, peaks
// snapped to hits and sections cut from the arc; the orchestration grid painted
// into the spec's lists; a take's bars selected and lowered; then the window on
// the mock's cue (its hits, sections, arc and ranked takes), an edit, a pick, a
// new cue, and the Arc and Orchestration & takes tabs; the meter (beats/unit) and
// key pickers, and each tab's help strip.
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  KEYS, ORCH_FAMILIES, SCORE_SECTIONS, SONG_SECTIONS, sectionChoice, aceBeats, addPoint, arcFlags, arcPoints, arcSpec, barBeat, barSpan, barsInSpan, barsLabel, clipsOver, compLabel, drawnPoints, dynamics,
  editableSections, gridOf, mergeSections, nextSectionName, sectionAt, splitPoint, withEnergies, heldCells, hitChip, impliedPoints, keyChoice, levelY, levelsAsEnergy, mergeStroke, meterText, moveEdge, movePoint, newCueId, newCueSpan,
  orchestraRows, paintOrchestra, parseMeter, patchSection, presetPoints, ranks, removePoint, renameFamily, sectionsFromArc, sectionWords, smoothPoints, snapBeat,
  snapToHits, splitSection, strokeLevel, ORCH_STEP, tauX, trimOrchestra, withSpec, wordsOffArc, xTau, yLevel,
} from "../src/lib/cue";
import { lowerStretch } from "../src/lib/mix";
import type { PlayItem } from "../src/lib/playlist";
import type { CuePlan, CueSpec, CueTake, Mix } from "../src/types";

/** A clip on the cut's clock at 24 fps. */
function clip(shot: string, start: number, dur: number, trimIn = 0): PlayItem {
  const inT = trimIn / 24;
  return {
    shot, index: 0, pass: "final", take: 1, mp4: `${shot}.mp4`, why: "", start, dur, inT, outT: inT + dur, trimIn, trimOut: 0,
    total: null, audioIn: null, audioOut: null, fadeIn: 0, fadeOut: 0, dissolveIn: 0, dissolveOut: 0,
  };
}

// sh010: 4 s from 0; sh020: 4 s from 4, its first 12 frames trimmed off; sh030: 4 s from 8
const ITEMS: PlayItem[] = [clip("sh010", 0, 4), clip("sh020", 4, 4, 12), clip("sh030", 8, 4)].map((x, i) => ({ ...x, index: i }));
// 120 bpm in 4/4: a bar is 2 s, a beat 0.5 s; the first bar starts 0.5 s before the in point
const PLAN = { bar: 2, bars: 6, preroll: 0.5 };

describe("a cue's meter and key", () => {
  it("reads a meter as the server does: beats/unit text, or a bare number of beats in 4", () => {
    expect(parseMeter("7/8")).toEqual({ beats: 7, unit: 8 });
    expect(parseMeter(" 12 / 8 ")).toEqual({ beats: 12, unit: 8 });
    expect(parseMeter(3)).toEqual({ beats: 3, unit: 4 });
    expect(parseMeter(undefined)).toEqual({ beats: 4, unit: 4 });
    for (const bad of ["7", "7/6", "17/8", "0/4", "x/4", "", 3.5, 0]) expect(parseMeter(bad)).toBeNull();
    expect(meterText(6)).toBe("6/4");
    expect(meterText("6 /8")).toBe("6/8");
    expect(meterText("6/5")).toBeNull();
  });

  it("the grid's beats to the bar are the meter's top number", () => {
    const g7 = gridOf(PLAN, { meter: "7/8" });
    expect(g7).toMatchObject({ meter: 7, bar: 2 });
    expect(g7.beat).toBeCloseTo(2 / 7);
    // the second bar's first beat is 2 s from the first bar line; the beat before it is 1.7
    expect(barBeat(g7, 1.5).label).toBe("2.1");
    expect(barBeat(g7, 1.5 - 2 / 7).label).toBe("1.7");
    const g12 = gridOf(PLAN, { meter: "12/8" });
    expect(g12.meter).toBe(12);
    expect(barBeat(g12, 1.5 + 11 * (2 / 12)).label).toBe("2.12");
    expect(snapBeat(g12, 100)).toBeCloseTo(11.5);
    // a stored number, the older form, is beats in 4; a meter that doesn't read is 4
    expect(gridOf(PLAN, { meter: 3 }).meter).toBe(3);
    expect(gridOf(PLAN, { meter: "nonsense" }).meter).toBe(4);
  });

  it("ACE-Step's time signature gets the nearest of 2, 3, 4 or 6 beats", () => {
    expect([1, 2, 5, 7, 9, 12].map(aceBeats)).toEqual([2, 2, 4, 6, 6, 6]);
  });

  it("the key picker offers the 24 keys as ACE-Step spells them; another key is Other", () => {
    expect(KEYS).toHaveLength(24);
    expect(KEYS).toContain("C# major");
    expect(KEYS).toContain("Eb minor");
    expect(keyChoice(undefined)).toBe("");
    expect(keyChoice("D minor")).toBe("D minor");
    expect(keyChoice("c#  MAJOR")).toBe("C# major");
    expect(keyChoice("D dorian")).toBeNull();
    expect(keyChoice("Db major")).toBeNull();
  });

  it("the section name picker offers a score's and a song's names; another name is Other", () => {
    expect(SCORE_SECTIONS).toContain("climax");
    expect(SONG_SECTIONS).toContain("chorus");
    expect(sectionChoice("build")).toBe("build");
    expect(sectionChoice(" Pre-Chorus ")).toBe("pre-chorus");
    expect(sectionChoice("the waltz")).toBeNull();
    expect(sectionChoice("section 2")).toBeNull();
  });

  it("the mock stores a meter as the server does", async () => {
    const { checkCue } = await import("../src/mock/mockCue");
    const base = { id: "m01", in: { shot: "sh010", frame: 0 }, out: { shot: "sh030", frame: 0 } };
    expect(checkCue({ ...base, meter: 7 }).meter).toBe("7/4");
    expect(checkCue({ ...base, meter: "12/8" }).meter).toBe("12/8");
    expect(checkCue({ ...base, meter: "4/4" }).meter).toBeUndefined();
    expect(() => checkCue({ ...base, meter: "7/6" })).toThrow(/meter/);
  });
});

describe("a cue's kind", () => {
  it("names it score or song where it's listed", async () => {
    const { cueTitle } = await import("../src/lib/cue");
    expect(cueTitle({ id: "m01", label: "1M3 The Proposal" })).toBe("Score · 1M3 The Proposal");
    expect(cueTitle({ id: "m02", kind: "song" })).toBe("Song · m02");
  });
});

describe("the cue's grid", () => {
  const g = gridOf(PLAN, {});

  it("is bars and beats from the pre-roll", () => {
    expect(g).toEqual({ bar: 2, beat: 0.5, meter: 4, bars: 6, preroll: 0.5, seconds: 12 });
    expect(gridOf(PLAN, { meter: 3 }).beat).toBeCloseTo(2 / 3);
    // x is 0 at the first bar line, so the in point is the pre-roll in
    expect(tauX(g, 0, 10)).toBe(5);
    expect(xTau(g, 25, 10)).toBe(2);
  });

  it("names the bar and beat a time lands on", () => {
    expect(barBeat(g, -0.5).label).toBe("1.1");
    expect(barBeat(g, 0).label).toBe("1.2");
    // 3.5 s from the in point is 4 s from the first bar line: bar 3, beat 1
    expect(barBeat(g, 3.5)).toEqual({ bar: 3, beat: 1, label: "3.1" });
    expect(barBeat(g, 3.74).label).toBe("3.1");
    expect(barBeat(g, 3.76).label).toBe("3.2");
  });

  it("snaps to beats, on the grid", () => {
    expect(snapBeat(g, 1.1)).toBe(1);
    expect(snapBeat(g, -3)).toBe(-0.5);
    expect(snapBeat(g, 99)).toBe(11.5);
  });
});

describe("sections", () => {
  const secs = [{ name: "intro", bars: 2 }, { name: "build", bars: 3 }, { name: "climax", bars: 1 }];

  it("an edge dragged moves whole bars between its two sections", () => {
    expect(moveEdge(secs, 0, 3.4)!.map((s) => s.bars)).toEqual([3, 2, 1]);
    expect(moveEdge(secs, 1, 4)!.map((s) => s.bars)).toEqual([2, 2, 2]);
    // each keeps a bar at least
    expect(moveEdge(secs, 0, 9)!.map((s) => s.bars)).toEqual([4, 1, 1]);
    expect(moveEdge(secs, 1, 0)!.map((s) => s.bars)).toEqual([2, 1, 3]);
    // where it was, or the last edge (the cue's end): nothing
    expect(moveEdge(secs, 0, 2)).toBeNull();
    expect(moveEdge(secs, 2, 4)).toBeNull();
  });

  it("a double-click splits at the nearest bar line inside a section, never on an edge or the ends", () => {
    // 10 px a bar: edges at bars 0, 2, 5, 6
    expect(splitPoint(secs, 31, 10)).toEqual({ i: 1, bar: 3 });
    expect(splitPoint(secs, 9, 10)).toEqual({ i: 0, bar: 1 });
    expect(splitPoint(secs, 22, 10)).toBeNull();
    expect(splitPoint(secs, 2, 10)).toBeNull();
    expect(splitPoint(secs, 58, 10)).toBeNull();
    expect(sectionAt(secs, 0)).toBe(0);
    expect(sectionAt(secs, 4.9)).toBe(1);
    expect(sectionAt(secs, 5)).toBe(2);
    expect(sectionAt(secs, 99)).toBe(2);
  });

  it("a split names its second half with the next numeral free", () => {
    expect(nextSectionName(secs, "build")).toBe("build 2");
    expect(nextSectionName([...secs, { name: "build 2" }], "build 2")).toBe("build 3");
    const two = splitSection([{ name: "build", bars: 4, words: "strings", from: 2, to: 4 }], 0, 2, [2, 3, 3.5, 4])!;
    expect(two).toEqual([{ name: "build", bars: 2, words: "strings", from: 2, to: 3.5 }, { name: "build 2", bars: 2, words: "strings", from: 3.5, to: 4 }]);
    expect(splitSection(two, 1, 3, [2, 3, 3.5, 4])![2].name).toBe("build 3");
  });

  it("two sections merged: the first's name and words, bars summed, energy first's start to second's end, lyrics joined", () => {
    const s = [
      { name: "verse", bars: 4, words: "piano", from: 2, to: 3, lyrics: "one" },
      { name: "chorus", bars: 4, words: "full band", from: 4, to: 5, lyrics: "two" },
      { name: "outro", bars: 2, from: 3, to: 1 },
    ];
    expect(mergeSections(s, 0)).toEqual([
      { name: "verse", bars: 8, words: "piano", from: 2, to: 5, lyrics: "one\ntwo" },
      { name: "outro", bars: 2, from: 3, to: 1 },
    ]);
    expect(mergeSections(s, 1)![1]).toEqual({ name: "chorus", bars: 6, words: "full band", from: 4, to: 1, lyrics: "two" });
    expect(mergeSections(s, 2)).toBeNull();
    expect(mergeSections([s[0]], 0)).toBeNull();
    // the plan's energies where the spec gives none
    expect(withEnergies([{ name: "a", bars: 2 }, { name: "b", bars: 2, from: 4 }], [{ from: 2, to: 3 }, { from: 3, to: 5 }]))
      .toEqual([{ name: "a", bars: 2, from: 2, to: 3 }, { name: "b", bars: 2, from: 4, to: 5 }]);
  });

  it("are the spec's to edit, with the plan's bars; else the plan's", () => {
    const plan = { sections: [{ name: "a", bars: 4, from: 2, to: 3 }, { name: "b", bars: 2, from: 3, to: 3 }] } as CuePlan;
    expect(editableSections({ id: "m01", in: { shot: "a", frame: 0 }, out: { shot: "a", frame: 1 } }, plan))
      .toEqual([{ name: "a", bars: 4, from: 2, to: 3 }, { name: "b", bars: 2, from: 3, to: 3 }]);
    const spec: CueSpec = { id: "m01", in: { shot: "a", frame: 0 }, out: { shot: "a", frame: 1 }, sections: [{ name: "a", words: "horn" }, { name: "b" }] };
    expect(editableSections(spec, plan)).toEqual([{ name: "a", bars: 4, words: "horn" }, { name: "b", bars: 2 }]);
    expect(patchSection(editableSections(spec, plan), 1, { words: "strings", from: 4 })[1]).toEqual({ name: "b", bars: 2, words: "strings", from: 4 });
    expect(patchSection([{ name: "a", words: "horn" }], 0, { words: "" })[0]).toEqual({ name: "a" });
  });
});

describe("the arc", () => {
  const g = gridOf(PLAN, {});
  const spec: CueSpec = {
    id: "m01", in: { shot: "sh010", frame: 24 }, out: { shot: "sh030", frame: 48 },
    arc: [{ at: { shot: "sh020", frame: 36 }, level: 5 }, { at: { shot: "sh010", frame: 48 }, level: 2 }],
  };
  // the in point plays 1 s into the cut
  const t0 = 1;

  it("reads the spec's points into cue time, in order", () => {
    // sh020 frame 36 is 1 s after its first frame shown (frame 12): cut 5 s, cue 4 s
    expect(arcPoints(spec, ITEMS, t0, 24)).toEqual([{ tau: 1, level: 2 }, { tau: 4, level: 5 }]);
  });

  it("a point dragged snaps to a beat and half a level, between its neighbours, and goes back to an anchor", () => {
    const pts = arcPoints(spec, ITEMS, t0, 24);
    const moved = movePoint(pts, 1, g, 5.2, 3.8);
    expect(moved[1]).toEqual({ tau: 5, level: 4 });
    // not past the point before it
    expect(movePoint(pts, 1, g, -2, 1)[1].tau).toBe(1);
    // cue 5 s is cut 6 s: sh020's 2 s in, its frame 12 + 48
    expect(arcSpec(moved, ITEMS, t0, 24)).toEqual([
      { at: { shot: "sh010", frame: 48 }, level: 2 }, { at: { shot: "sh020", frame: 60 }, level: 4 },
    ]);
    expect(addPoint(pts, g, 2.1, 9).map((p) => [p.tau, p.level])).toEqual([[1, 2], [2, 5], [4, 5]]);
    expect(removePoint(pts, 0)).toEqual([{ tau: 4, level: 5 }]);
  });

  it("levels go to y and back, 5 at the top", () => {
    expect(levelY(5, 84)).toBe(4);
    expect(levelY(1, 84)).toBe(80);
    expect(yLevel(42, 84)).toBe(3);
    expect(yLevel(0, 84)).toBe(5);
    expect(yLevel(200, 84)).toBe(1);
  });

  it("with no points, the sections imply them", () => {
    const pts = impliedPoints(g, [{ bars: 2, from: 1, to: 3 }, { bars: 2, from: 3, to: 3 }, { bars: 2, from: 5, to: 2 }]);
    // each start at its from; a to a beat before the next starts where it differs; the last's to at the end
    expect(pts).toEqual([
      { tau: -0.5, level: 1 }, { tau: 3, level: 3 }, { tau: 3.5, level: 3 }, { tau: 7, level: 3 }, { tau: 7.5, level: 5 }, { tau: 11.5, level: 2 },
    ]);
  });
});

describe("takes", () => {
  it("hit errors read as chips: orange past two frames, a dash for nothing there", () => {
    expect(hitChip(0.42)).toEqual({ text: "+0.4", cls: "ok" });
    expect(hitChip(-2.5)).toEqual({ text: "-2.5", cls: "off" });
    expect(hitChip(null)).toEqual({ text: "—", cls: "none" });
  });

  it("are ranked as the server orders them, the measured ones only", () => {
    const m = { score: 1 } as CueTake["measured"];
    const takes: CueTake[] = [
      { take: 3, status: "ok", measured: m }, { take: 1, status: "ok", measured: m }, { take: 4, status: "queued" }, { take: 2, status: "failed" },
    ];
    expect(ranks(takes)).toEqual([1, 2, null, null]);
  });

  it("a take's loudness per bar lies on the arc's scale", () => {
    expect(levelsAsEnergy([-30, -20, -10, -80])).toEqual([1, 3, 5, 1]);
    expect(levelsAsEnergy([-80])).toEqual([1]);
  });
});

describe("a new cue", () => {
  it("takes the next id clear of the cues and the mix's items", () => {
    expect(newCueId([], [])).toBe("m01");
    expect(newCueId(["m01"], ["m02", "amb01"])).toBe("m03");
  });

  it("spans the shots selected, else from where it was asked to its shot's end", () => {
    expect(newCueSpan(ITEMS, 24, ["sh020", "sh030"], null)).toEqual({ in: { shot: "sh020", frame: 12 }, out: { shot: "sh030", frame: 96 } });
    expect(newCueSpan(ITEMS, 24, [], { shot: "sh010", frame: 30 })).toEqual({ in: { shot: "sh010", frame: 30 }, out: { shot: "sh010", frame: 96 } });
    expect(newCueSpan(ITEMS, 24, [], null)).toBeNull();
  });

  it("the picture strip shows the clips over the grid, clipped to it", () => {
    const g = gridOf(PLAN, {});
    expect(clipsOver(ITEMS, 1, g).map((c) => [c.it.shot, c.a, c.b])).toEqual([["sh010", -0.5, 3], ["sh020", 3, 7], ["sh030", 7, 11]]);
  });

  it("a spec edit drops what's emptied", () => {
    const spec: CueSpec = { id: "m01", in: { shot: "a", frame: 0 }, out: { shot: "a", frame: 1 }, label: "x", bpm: 92 };
    expect(withSpec(spec, { label: "", bpm: undefined, fixed_tempo: false, key: "D minor" })).toEqual({ id: "m01", in: spec.in, out: spec.out, key: "D minor" });
  });
});

describe("the Arc tab", () => {
  const g = gridOf(PLAN, {});
  // the cue's span: its in point (cue 0 s) to its out point (cue 10 s)
  const SPAN = 10;
  const pairs = (pts: { tau: number; level: number }[]) => pts.map((p) => [p.tau, p.level]);

  it("a preset shape lays points on beats over the cue's span", () => {
    expect(pairs(presetPoints("slow burn", g, SPAN))).toEqual([[0, 1], [5, 2], [8.5, 3.5], [10, 5]]);
    expect(pairs(presetPoints("build and release", g, SPAN))).toEqual([[0, 2], [7, 5], [10, 1.5]]);
    expect(pairs(presetPoints("sting", g, SPAN))).toEqual([[0, 5], [2, 2], [10, 1.5]]);
    expect(pairs(presetPoints("from the script", g, SPAN))).toEqual([[0, 2], [5, 3], [8.5, 3.5], [10, 2.5]]);
    // a swell on each bar line inside the span, easing at each half bar
    expect(pairs(presetPoints("pulse", g, SPAN))).toEqual([
      [0.5, 2.5], [1.5, 4], [2.5, 2.5], [3.5, 4], [4.5, 2.5], [5.5, 4], [6.5, 2.5], [7.5, 4], [8.5, 2.5], [9.5, 4],
    ]);
  });

  it("a freehand stroke is put on beats and simplified", () => {
    const stroke = [[0, 1], [0.26, 1.2], [0.5, 1.4], [1, 2], [1.5, 2.5], [2, 5], [2.5, 3], [3, 3.5], [4, 4]].map(([tau, level]) => ({ tau, level }));
    // 0.26 and 0.5 fall on one beat (the later wins); what a straight line between its neighbours draws is dropped
    expect(pairs(drawnPoints(stroke, g))).toEqual([[0, 1], [1.5, 2.5], [2, 5], [2.5, 3], [4, 4]]);
    // drawn over the points, it replaces those it spans
    const pts = [[0, 1], [2, 2], [5, 3], [8, 4]].map(([tau, level]) => ({ tau, level }));
    expect(pairs(mergeStroke(pts, [{ tau: 1, level: 5 }, { tau: 6, level: 5 }]))).toEqual([[0, 1], [1, 5], [6, 5], [8, 4]]);
  });

  it("smoothing eases each point toward its neighbours", () => {
    const zig = [[0, 1], [1, 5], [2, 1], [3, 5], [4, 1]].map(([tau, level]) => ({ tau, level }));
    expect(pairs(smoothPoints(zig))).toEqual([[0, 1], [1, 3], [3, 3], [4, 1]]);
  });

  it("snaps each peak to an arrive (or turn) and each low to a drop (or turn), within a bar", () => {
    const pts = presetPoints("build and release", g, SPAN);
    const hits = [
      { t: 0.4, kind: "turn" }, { t: 4, kind: "arrive" }, { t: 7.1, kind: "accent" }, { t: 7.8, kind: "arrive" }, { t: 9.9, kind: "drop" },
    ];
    const r = snapToHits(pts, hits, g);
    expect(r.moved).toBe(3);
    // the peak at 7 goes to the arrive at 7.8 (the one at 4 is more than a bar off; an accent isn't a peak's)
    expect(pairs(r.points)).toEqual([[0.4, 2], [7.8, 5], [9.9, 1.5]]);
    expect(snapToHits(pts, [{ t: 3, kind: "arrive" }], g).moved).toBe(0);
  });

  it("sections are cut at the arc's peaks and lows, on bar lines, their energies the arc's", () => {
    // up to a plateau from bar 4 to bar 5, then down
    const pts = [[-0.5, 1], [5.5, 5], [7.5, 5], [11.5, 2]].map(([tau, level]) => ({ tau, level }));
    expect(sectionsFromArc(pts, g)).toEqual([
      { name: "build", bars: 3, from: 1, to: 5 }, { name: "hold", bars: 1, from: 5, to: 5 }, { name: "release", bars: 2, from: 5, to: 2 },
    ]);
    // a flat arc: one section
    expect(sectionsFromArc([{ tau: 0, level: 3 }], g)).toEqual([{ name: "hold", bars: 6, from: 3, to: 3 }]);
  });

  it("flags a peak or a dip inside a section, and words that don't say what the arc does", () => {
    const arc = [1, 2, 4, 2, 1, 1];
    expect(arcFlags(arc, [{ bars: 6 }])).toEqual([{ section: 0, bar: 2, kind: "peak" }]);
    expect(arcFlags(arc, [{ bars: 3 }, { bars: 3 }])).toEqual([]);
    expect(arcFlags([4, 4, 1, 4], [{ bars: 4 }])).toEqual([{ section: 0, bar: 2, kind: "dip" }]);
    // split there, the peak is an edge
    expect(splitSection([{ name: "a", bars: 6, from: 1, to: 1 }], 0, 2, arc)).toEqual([
      { name: "a", bars: 2, from: 1, to: 4 }, { name: "a 2", bars: 4, from: 4, to: 1 },
    ]);
    expect(splitSection([{ name: "a", bars: 6 }], 0, 6, arc)).toBeNull();
    expect(wordsOffArc(arc, [{ bars: 3, from: 1, to: 4 }, { bars: 3, from: 2, to: 1 }])).toEqual([]);
    expect(wordsOffArc(arc, [{ bars: 3, from: 1, to: 4 }, { bars: 3, from: 4, to: 4 }])).toEqual([1]);
  });

  it("words a section's energy as the prompt writer does", () => {
    expect(dynamics({ from: 2, to: 4 })).toBe("rising from quiet to strong, building");
    expect(dynamics({ from: 5, to: 1 })).toBe("falling from fortissimo to very quiet, receding");
    expect(sectionWords({ words: " strings lead, ", from: 3, to: 3 })).toBe("strings lead, moderate, sustained");
  });
});

describe("the orchestration grid", () => {
  it("painting cells writes each family's level per bar, trailing offs trimmed", () => {
    expect(paintOrchestra({}, ["strings"], 2, 4, 2)).toEqual({ strings: [0, 0, 2, 2, 2] });
    expect(paintOrchestra({ strings: [0, 0, 2, 2, 2] }, ["strings"], 3, 4, 0)).toEqual({ strings: [0, 0, 2] });
    // a family off throughout is dropped
    expect(paintOrchestra({ strings: [0, 0, 2] }, ["strings"], 2, 2, 0)).toEqual({});
    // a stroke over two rows, dragged backwards
    expect(paintOrchestra({ strings: [1] }, ["brass", "harp"], 3, 1, 3)).toEqual({ strings: [1], brass: [0, 3, 3, 3], harp: [0, 3, 3, 3] });
    expect(trimOrchestra({ a: [0, 0], b: [1, 0, 0] })).toEqual({ b: [1] });
    // a level brush paints its level; the step brush steps the first cell on (Shift: back), round
    expect(strokeLevel({ strings: [0, 1] }, "strings", 1, 2)).toBe(2);
    expect(strokeLevel({ strings: [0, 2] }, "strings", 1, ORCH_STEP)).toBe(3);
    expect(strokeLevel({ strings: [0, 3] }, "strings", 1, ORCH_STEP)).toBe(0);
    expect(strokeLevel({}, "strings", 4, ORCH_STEP)).toBe(1);
    expect(strokeLevel({ strings: [0, 2] }, "strings", 1, ORCH_STEP, true)).toBe(1);
    expect(strokeLevel({}, "brass", 0, ORCH_STEP, true)).toBe(3);
  });

  it("keeps its rows, renames a family in its place and refuses a name taken", () => {
    expect(orchestraRows(undefined, { harp: [1] })).toEqual(["harp", ...ORCH_FAMILIES.filter((f) => f !== "harp")]);
    expect(orchestraRows(["strings"], { harp: [1] })).toEqual(["strings", "harp"]);
    expect(Object.keys(renameFamily({ strings: [1], brass: [2] }, "strings", " violins  I ")!)).toEqual(["violins I", "brass"]);
    expect(renameFamily({ strings: [1], brass: [2] }, "strings", "brass")).toBeNull();
    expect(renameFamily({ strings: [1] }, "strings", "  ")).toBeNull();
  });

  it("marks the cells a section won't follow: below the family's strongest there", () => {
    expect([...heldCells({ strings: [1, 3, 3, 0, 2, 2] }, [{ bars: 3 }, { bars: 3 }])].sort()).toEqual(["strings|0", "strings|3"]);
    expect(heldCells({ strings: [2, 2, 2] }, [{ bars: 3 }]).size).toBe(0);
  });
});

describe("a take's bars", () => {
  const g = gridOf(PLAN, {});

  it("a drag selects whole bars, one at least", () => {
    // 10 px a second: a bar is 20 px
    expect(barSpan(g, 5, 5, 10)).toEqual([0, 1]);
    expect(barSpan(g, 45, 15, 10)).toEqual([0, 3]);
    expect(barSpan(g, 40, 40, 10)).toEqual([2, 3]);
    expect(barSpan(g, -10, 500, 10)).toEqual([0, 6]);
    expect(barsLabel([2, 3])).toBe("bar 3");
    expect(barsLabel([0, 3])).toBe("bars 1-3");
    expect(compLabel({ base: 3, from: 1, bars: [4, 8] })).toBe("comp of t03 + t01 bars 5-8");
  });

  it("bars lowered in the mix stay inside the cue's span", () => {
    expect(barsInSpan(g, [0, 2], 10)).toEqual([0, 3.5]);
    expect(barsInSpan(g, [5, 6], 10)).toEqual([9.5, 10]);
    expect(barsInSpan(g, [3, 6], 3)).toBeNull();
  });

  it("lowering a stretch adds points at its ends, ramped, and lowers those between", () => {
    const item = { id: "m01", track: "music" as const, path: "sound/m01/t01.wav", in: { shot: "sh010", frame: 0 } };
    const at = (frame: number) => ({ shot: "sh010", frame });
    expect(lowerStretch({ items: [item] }, "m01", 1, 3, -6, 0.25, ITEMS, 24)!.items![0].points).toEqual([
      { at: at(24), db: 0 }, { at: at(30), db: -6 }, { at: at(66), db: -6 }, { at: at(72), db: 0 },
    ]);
    // the line it had: kept outside, lowered inside, the ends at its level there
    const mix: Mix = { items: [{ ...item, points: [{ at: at(12), db: -3 }, { at: at(48), db: 2 }] }] };
    expect(lowerStretch(mix, "m01", 1, 3, -6, 0.25, ITEMS, 24)!.items![0].points).toEqual([
      { at: at(12), db: -3 }, { at: at(24), db: -1.5 }, { at: at(30), db: -6.5 }, { at: at(48), db: -4 }, { at: at(66), db: -4 }, { at: at(72), db: 2 },
    ]);
    expect(lowerStretch(mix, "m01", 3, 1, -6, 0.25, ITEMS, 24)).toBeNull();
    expect(lowerStretch(mix, "nope", 1, 3, -6, 0.25, ITEMS, 24)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// the window, on the mock
// ---------------------------------------------------------------------------

import { refreshEpisode } from "../src/actions";
import { Viewer } from "../src/components/Viewer";
import { HELP_KEY } from "../src/components/CueWindow";
import { cueKey, cueSettled, loadCue, newCue, openCue, pickCueTake, saveCue } from "../src/cueActions";
import { resetCutHistory } from "../src/cutActions";
import { setApi, setHost, type Host } from "../src/host";
import { createMockApi } from "../src/mock/mockApi";
import { currentMix, loadMix, mixSettled } from "../src/mixActions";
import { initialState, statusKey, store } from "../src/store";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

describe("the cue window", () => {
  let root: Root;
  let el: HTMLDivElement;
  let EP: string;
  let api: ReturnType<typeof createMockApi>;

  beforeEach(async () => {
    setHost({ on: () => () => {}, toast: () => {}, show: () => {} } as Host);
    api = createMockApi(() => {}, { latency: 0, cueDemo: true });
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
    act(() => root.unmount());
    el.remove();
    store.set(initialState());
  });

  const q = (sel: string) => [...document.querySelectorAll<HTMLElement>(sel)];
  const open = async () => {
    await act(async () => {
      openCue("m01");
      root.render(createElement(Viewer));
    });
    await act(async () => {
      await loadCue(EP, "proxy", "m01");
    });
  };

  it("lays the cue's hits, sections, arc and ranked takes on its bar grid", async () => {
    await open();
    expect(store.get().viewer?.kind).toBe("cue");
    const res = store.get().cue[cueKey(EP, "proxy", "m01")]!;
    expect(res.plan).not.toBeNull();
    // the three hits, each with its bar.beat and the fit's error
    const hits = q(".h3-cue-hit");
    expect(hits).toHaveLength(3);
    expect(hits[0].className).toContain("h3-hit-accent");
    expect(hits[2].className).toContain("h3-hit-may");
    expect(hits[0].textContent).toMatch(/she looks up\d+\.\d · [-+]?[\d.]+f/);
    // sections from the hits: a block each
    expect(q(".h3-cue-sect")).toHaveLength(res.plan!.sections.length);
    expect(q(".h3-cue-bnum")).toHaveLength(res.plan!.bars);
    // no points in the spec: the sections' implied ones, hollow
    expect(q(".h3-cue-pt.h3-implied").length).toBeGreaterThan(1);
    // the takes, best first: three measured, one failed
    const takes = q(".h3-cue-take");
    expect(takes).toHaveLength(4);
    expect(takes[0].textContent).toContain("#1");
    expect(takes[3].textContent).toContain("out of memory");
    expect(q(".h3-cue-take .h3-b-stale")).toHaveLength(1);
    expect(q(".h3-cue-take .h3-b-stale")[0].title).toBe("she looks up moved -6 frames");
    expect(q(".h3-cue-chip").length).toBe(9);
    // the inspector: the cue, its fit and its prompt, the script's notes
    const side = q(".h3-cue-side")[0];
    expect(side.textContent).toContain("Cue m01");
    expect(side.textContent).toContain("The fit");
    expect(side.textContent).toContain("From the script");
    expect(side.querySelector("pre")!.textContent).toBe(res.plan!.prompt.prompt);
    // the three tabs, Score open
    const tabs = [...side.ownerDocument.querySelectorAll<HTMLButtonElement>(".h3-cue-win .h3-seg button")].slice(0, 3);
    expect(tabs.map((b) => [b.textContent, b.disabled, b.classList.contains("h3-on")])).toEqual([
      ["Score", false, true], ["Arc", false, false], ["Orchestration & takes", false, false],
    ]);
  });

  it("a section clicked is the inspector's; its energy edited is one PUT, then the plan again", async () => {
    await open();
    await act(async () => q(".h3-cue-sect")[0].click());
    const side = q(".h3-cue-side")[0];
    expect(side.textContent).toContain("Section 1");
    // Stable Audio has no lyrics
    expect(side.querySelector("[aria-label='Section lyrics']")).toBeNull();
    const to = side.querySelector<HTMLSelectElement>("[aria-label='Energy at its end']")!;
    await act(async () => {
      to.value = "4.5";
      to.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await act(async () => {
      await cueSettled();
    });
    const res = store.get().cue[cueKey(EP, "proxy", "m01")]!;
    // the plan's sections became the spec's, with the change
    expect(res.spec.sections![0].to).toBe(4.5);
    expect(res.plan!.sections[0].to).toBe(4.5);
    expect((await api.getCue(EP, "proxy", "m01")).spec.sections![0].to).toBe(4.5);
  });

  it("the Sections lane: a double-click splits a new cue's one section; the menu merges them and resets from the hits", async () => {
    const shots = store.get().status[statusKey(EP, "proxy")]!.shots;
    let id: string | null = null;
    await act(async () => {
      id = await newCue({ shot: shots[4].shot, frame: 0 });
      root.render(createElement(Viewer));
    });
    const key = cueKey(EP, "proxy", id!);
    await act(async () => {
      await loadCue(EP, "proxy", id!);
    });
    const cur = () => store.get().cue[key]!;
    expect(cur().plan!.sections).toHaveLength(1);
    const bars = cur().plan!.bars;
    expect(bars).toBeGreaterThan(2);
    // 4 px a second (the window has no width here): bar line 2
    const barPx = cur().plan!.bar * 4;
    const lane = () => q(".h3-cue-sect")[0].parentElement!;
    await act(async () => lane().dispatchEvent(new MouseEvent("dblclick", { bubbles: true, clientX: 2 * barPx + 1 })));
    await act(async () => {
      await cueSettled();
    });
    expect(cur().spec.sections!.map((s) => [s.name, s.bars])).toEqual([[cur().plan!.sections[0].name, 2], [`${cur().plan!.sections[0].name} 2`, bars - 2]]);
    expect(q(".h3-cue-sect")).toHaveLength(2);
    // on an edge: nothing
    await act(async () => lane().dispatchEvent(new MouseEvent("dblclick", { bubbles: true, clientX: 2 * barPx })));
    await act(async () => {
      await cueSettled();
    });
    expect(cur().spec.sections).toHaveLength(2);
    // the first's menu: no previous, merge with next
    const menu = async (x: number) => {
      await act(async () => lane().dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, cancelable: true, clientX: x, clientY: 10 })));
      return [...document.querySelectorAll<HTMLButtonElement>(".h3-cue-sectmenu button")];
    };
    let items = await menu(barPx / 2 + 1);
    expect(items.map((b) => [b.textContent!.trim(), b.disabled])).toEqual([
      ["Split at bar 2", false], ["Merge with previous", true], ["Merge with next", false], ["Edit", false], ["Reset sections from the hits", false],
    ]);
    await act(async () => items[2].click());
    await act(async () => {
      await cueSettled();
    });
    expect(q(".h3-cue-sectmenu")).toHaveLength(0);
    expect(cur().spec.sections!.map((s) => s.bars)).toEqual([bars]);
    // one section: neither merge
    items = await menu(barPx / 2 + 1);
    expect(items.filter((b) => b.textContent!.includes("Merge")).every((b) => b.disabled)).toBe(true);
    // reset asks first
    const ask = vi.fn().mockReturnValueOnce(false).mockReturnValueOnce(true);
    vi.stubGlobal("confirm", ask);
    try {
      await act(async () => items[4].click());
      await act(async () => {
        await cueSettled();
      });
      expect(cur().spec.sections).toHaveLength(1);
      items = await menu(barPx / 2 + 1);
      await act(async () => items[4].click());
      await act(async () => {
        await cueSettled();
      });
      expect(ask).toHaveBeenCalledTimes(2);
      expect(cur().spec.sections).toBeUndefined();
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("Pick puts the take on the music track and marks it", async () => {
    await open();
    const best = store.get().cue[cueKey(EP, "proxy", "m01")]!.takes[0];
    await act(async () => {
      await pickCueTake(best.take);
    });
    const item = currentMix()!.mix.items!.find((i) => i.id === "m01")!;
    expect(item).toMatchObject({ track: "music", path: best.file });
    expect(q(".h3-cue-take")[0].textContent).toContain("In the mix");
  });

  const res = () => store.get().cue[cueKey(EP, "proxy", "m01")]!;
  const tab = async (name: string) => {
    const b = q(".h3-cue-win .h3-seg button").find((x) => x.textContent === name)!;
    await act(async () => b.click());
  };
  const button = (text: string | RegExp) => (q(".h3-cue-win button") as HTMLButtonElement[]).find((b) => (typeof text === "string" ? b.textContent?.trim() === text : text.test(b.textContent?.trim() ?? "")));
  const settle = async () => {
    await act(async () => {
      await cueSettled();
      await mixSettled();
    });
  };

  it("the Arc tab: the lane large, a shape, sections cut from it, a stroke drawn, and what the model hears", async () => {
    await open();
    await tab("Arc");
    const plan = res().plan!;
    // the lane large, the hits and sections above it for reference, no takes
    expect(q(".h3-cue-arc svg")[0].getAttribute("height")).toBe("220");
    expect(q(".h3-cue-hit")).toHaveLength(3);
    expect(q(".h3-cue-sect.h3-ro")).toHaveLength(plan.sections.length);
    expect(q(".h3-cue-take")).toHaveLength(0);
    // beside it: each section's words, and the prompt as it is
    const side = q(".h3-cue-readout")[0];
    expect(side.textContent).toContain("What the model hears");
    expect(q(".h3-cue-read")).toHaveLength(plan.sections.length);
    expect(side.querySelector("pre")!.textContent).toBe(plan.prompt.prompt);
    // the script has music: notes here, so its shape is offered; no points yet, so no sections from them
    expect(button("from the script")!.title).toContain("gentle default shape");
    expect(button("Sections from the arc")!.disabled).toBe(true);
    await act(async () => button("build and release")!.click());
    await settle();
    expect(res().spec.arc!.map((p) => p.level)).toEqual([2, 5, 1.5]);
    // the sections from it: up to the peak, then down
    expect(button("Sections from the arc")!.disabled).toBe(false);
    await act(async () => button("Sections from the arc")!.click());
    await settle();
    expect(res().spec.sections!.map((s) => s.name)).toEqual(expect.arrayContaining(["build", "release"]));
    // a stroke drawn freehand (4 px a second): its points replace those it spans
    const lane = q(".h3-cue-arc .h3-cue-lane")[0];
    await act(async () => lane.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, button: 0, clientX: 4, clientY: 200 })));
    for (const [cx, cy] of [[10, 150], [16, 10], [22, 120], [30, 180]]) {
      await act(async () => window.dispatchEvent(new PointerEvent("pointermove", { clientX: cx, clientY: cy })));
    }
    expect(q(".h3-cue-stroke")).toHaveLength(1);
    await act(async () => window.dispatchEvent(new PointerEvent("pointerup", {})));
    await settle();
    const levels = res().spec.arc!.map((p) => p.level);
    expect(levels).toContain(5);
    expect(levels.length).toBeGreaterThan(3);
  });

  it("Orchestration & takes: a stroke painted is the spec's orchestra and the sections' words; bars of a take comped and lowered", async () => {
    await open();
    await tab("Orchestration & takes");
    expect(q(".h3-cue-orow")).toHaveLength(ORCH_FAMILIES.length);
    const plan = res().plan!;
    const barPx = plan.bar * 4;
    // strings, bars 1 to 3, with the present brush (key 3; the window opens on step)
    const grid = q(".h3-cue-orch")[0];
    const brushOn = () => { const s = q(".h3-cue-tools select")[0] as HTMLSelectElement; return s.options[s.selectedIndex].text; };
    expect(brushOn()).toBe("5 - step");
    await act(async () => grid.dispatchEvent(new KeyboardEvent("keydown", { key: "3", bubbles: true })));
    expect(brushOn()).toBe("3 - present");
    await act(async () => grid.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, button: 0, clientX: 76 + 1, clientY: 1 })));
    await act(async () => window.dispatchEvent(new PointerEvent("pointermove", { clientX: 76 + 2 * barPx + 1, clientY: 2 })));
    await act(async () => window.dispatchEvent(new PointerEvent("pointerup", {})));
    await settle();
    expect(res().spec.orchestra).toEqual({ strings: [2, 2, 2] });
    expect(res().plan!.sections[0].words).toContain("strings present");
    expect(res().plan!.prompt.prompt).toContain("strings present");
    expect(q(".h3-cue-cell.h3-lv-2")).toHaveLength(3);
    // step (key 5): a click on bar 2 moves it up to lead, a Shift-click back down to present
    await act(async () => grid.dispatchEvent(new KeyboardEvent("keydown", { key: "5", bubbles: true })));
    expect(brushOn()).toBe("5 - step");
    const click = async (shiftKey: boolean) => {
      await act(async () => grid.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, button: 0, shiftKey, clientX: 76 + barPx + 1, clientY: 1 })));
      await act(async () => window.dispatchEvent(new PointerEvent("pointerup", {})));
      await settle();
    };
    await click(false);
    expect(res().spec.orchestra).toEqual({ strings: [2, 3, 2] });
    await click(true);
    expect(res().spec.orchestra).toEqual({ strings: [2, 2, 2] });
    // removing the painted row clears it from the spec
    await act(async () => q(".h3-cue-orow .h3-snd-btn")[0].click());
    await settle();
    expect(res().spec.orchestra).toBeUndefined();
    expect(q(".h3-cue-orow")).toHaveLength(ORCH_FAMILIES.length - 1);

    // bars 1 to 3 of the best take, dragged across
    const best = res().takes[0];
    const wave = () => q(".h3-cue-take .h3-cue-lane")[0];
    const select = async () => {
      await act(async () => wave().dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, button: 0, clientX: 1 })));
      await act(async () => window.dispatchEvent(new PointerEvent("pointermove", { clientX: 2 * barPx + 1 })));
      await act(async () => window.dispatchEvent(new PointerEvent("pointerup", {})));
    };
    await select();
    const fixes = q(".h3-cue-fixes")[0];
    expect(fixes.textContent).toContain("Bars 1-3");
    // not in the mix yet: no breakpoints; repaint isn't measured
    expect(button(/^Lower bars 1-3/)!.disabled).toBe(true);
    expect(button(/^Repaint/)!.disabled).toBe(true);
    expect(button(/^Repaint/)!.title).toBe("not measured yet (docs/SOUND.md 'Fixing part of a take')");
    const src = Number(fixes.querySelector<HTMLSelectElement>("[aria-label='Comp from take']")!.value);
    await act(async () => button(/^Comp bars 1-3/)!.click());
    await settle();
    const comp = res().takes.find((t) => t.comp)!;
    expect(comp.comp).toEqual({ base: best.take, from: src, bars: [0, 3] });
    expect(q(".h3-cue-take")).toHaveLength(5);
    expect(q(".h3-cue-comp")[0].textContent).toBe(`comp of t${String(best.take).padStart(2, "0")} + t${String(src).padStart(2, "0")} bars 1-3`);
    expect(q(".h3-cue-fixes")).toHaveLength(0);

    // picked, its bars lowered with the mix's points
    await act(async () => {
      await pickCueTake(res().takes[0].take);
    });
    await select();
    expect((q(".h3-cue-fixes input[aria-label='Lower by dB']")[0] as HTMLInputElement).value).toBe("-6");
    expect(button(/^Lower bars 1-3/)!.disabled).toBe(false);
    await act(async () => button(/^Lower bars 1-3/)!.click());
    await settle();
    const item = currentMix()!.mix.items!.find((i) => i.id === "m01")!;
    expect(item.points!.length).toBeGreaterThanOrEqual(3);
    expect(Math.min(...item.points!.map((p) => p.db))).toBe(-6);
  });

  it("a new cue from the music lane takes the next id and opens", async () => {
    const shots = store.get().status[statusKey(EP, "proxy")]!.shots;
    let id: string | null = null;
    await act(async () => {
      id = await newCue({ shot: shots[4].shot, frame: 10 });
    });
    expect(id).toBe("m02");
    expect(store.get().viewer).toMatchObject({ kind: "cue", cue: "m02" });
    const spec = (await api.getCue(EP, "proxy", "m02")).spec;
    expect(spec.in).toEqual({ shot: shots[4].shot, frame: 10 });
    expect(spec.out.shot).toBe(shots[4].shot);
  });

  // the inspector's pickers and the help strips
  const side = () => q(".h3-cue-side")[0];
  const choose = async (sel: HTMLSelectElement, value: string) => {
    await act(async () => {
      sel.value = value;
      sel.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await settle();
  };
  const typeIn = async (input: HTMLInputElement, value: string) => {
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value);
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => {
      input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    });
    await settle();
  };
  const field = <T extends HTMLElement>(label: string) => side().querySelector<T>(`[aria-label='${label}']`);

  it("the meter: a choice of eight, or Other (beats/unit, checked), the grid's beats its top number, ACE-Step told the nearest", async () => {
    await open();
    const meter = field<HTMLSelectElement>("Meter")!;
    expect(meter.value).toBe("4/4");
    expect([...meter.options].map((o) => o.value)).toEqual(["2/4", "3/4", "4/4", "5/4", "6/8", "7/8", "9/8", "12/8", "other"]);
    await choose(meter, "7/8");
    expect(res().spec.meter).toBe("7/8");
    expect((await api.getCue(EP, "proxy", "m01")).spec.meter).toBe("7/8");
    expect(q(".h3-cue-ruler .h3-cue-lab")[0].textContent).toBe("7/8");
    // Other: its own text, refused here when it isn't a meter
    await choose(field<HTMLSelectElement>("Meter")!, "other");
    const own = field<HTMLInputElement>("Meter (beats/unit)")!;
    expect(own.value).toBe("7/8");
    await typeIn(own, "11");
    expect(side().querySelector(".h3-err")!.textContent).toMatch(/beats\/unit/);
    expect(res().spec.meter).toBe("7/8");
    await typeIn(field<HTMLInputElement>("Meter (beats/unit)")!, "11/8");
    expect(res().spec.meter).toBe("11/8");
    expect(side().querySelector(".h3-err")).toBeNull();
    expect(field<HTMLSelectElement>("Meter")!.value).toBe("other");
    // ACE-Step's time signature takes 2, 3, 4 or 6 beats
    expect(side().textContent).not.toContain("ACE-Step's time signature");
    await choose(field<HTMLSelectElement>("Music model")!, "ace_step15");
    expect(side().textContent).toContain("ACE-Step's time signature takes 2, 3, 4 or 6 beats: it gets 6 and '11/8' in its tags");
    // 4/4 is the default: dropped
    await choose(field<HTMLSelectElement>("Meter")!, "4/4");
    expect(res().spec.meter).toBeUndefined();
    expect(side().textContent).not.toContain("ACE-Step's time signature");
  });

  it("the key: none, one of the 24, or Other (a mode) kept as its text", async () => {
    await open();
    const key = field<HTMLSelectElement>("Key")!;
    expect(key.value).toBe("");
    expect(field("Key (other)")).toBeNull();
    await choose(key, "other");
    expect(side().textContent).toContain("Only Stable Audio reads a key that isn't major or minor");
    await typeIn(field<HTMLInputElement>("Key (other)")!, "D dorian");
    expect(res().spec.key).toBe("D dorian");
    expect(field<HTMLSelectElement>("Key")!.value).toBe("other");
    await choose(field<HTMLSelectElement>("Key")!, "Eb minor");
    expect(res().spec.key).toBe("Eb minor");
    expect(field("Key (other)")).toBeNull();
    // a key of its own already in the spec shows as Other, with its text
    await act(async () => {
      await saveCue({ ...res().spec, key: "A phrygian" });
    });
    await settle();
    expect(field<HTMLSelectElement>("Key")!.value).toBe("other");
    expect(field<HTMLInputElement>("Key (other)")!.value).toBe("A phrygian");
    await choose(field<HTMLSelectElement>("Key")!, "");
    expect(res().spec.key).toBeUndefined();
  });

  it("each tab's help: the ? toggles it, remembered per tab; a cue with no takes links the guide", async () => {
    localStorage.clear();
    await open();
    const help = () => q(".h3-cue-win button[aria-label='How to use this tab']")[0];
    expect(q(".h3-cue-help")).toHaveLength(0);
    await act(async () => help().click());
    expect(q(".h3-cue-help li")).toHaveLength(4);
    expect(q(".h3-cue-help a")[0].getAttribute("href")).toBe("https://docs.seriesmith.com/scoring#3-shape-it-the-score-tab");
    expect(localStorage.getItem(`${HELP_KEY}.score`)).toBe("1");
    // the Arc tab's is its own, closed
    await tab("Arc");
    expect(q(".h3-cue-help")).toHaveLength(0);
    await act(async () => help().click());
    expect(q(".h3-cue-help li")[0].textContent).toMatch(/^Draw/);
    await tab("Score");
    expect(q(".h3-cue-help li")[0].textContent).toMatch(/^Mark the hits/);
    await act(async () => q(".h3-cue-help button[aria-label='Hide the help']")[0].click());
    expect(q(".h3-cue-help")).toHaveLength(0);
    expect(localStorage.getItem(`${HELP_KEY}.score`)).toBe("0");
    // opened again: as it was left
    act(() => root.unmount());
    root = createRoot(el);
    await open();
    expect(q(".h3-cue-help")).toHaveLength(0);
    await tab("Arc");
    expect(q(".h3-cue-help")).toHaveLength(1);
    // a browser that keeps nothing: closed, and the ? still works
    act(() => root.unmount());
    root = createRoot(el);
    const spy = vi.spyOn(localStorage, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const spySet = vi.spyOn(localStorage, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    try {
      await open();
      await tab("Arc");
      expect(q(".h3-cue-help")).toHaveLength(0);
      await act(async () => help().click());
      expect(q(".h3-cue-help")).toHaveLength(1);
    } finally {
      spy.mockRestore();
      spySet.mockRestore();
    }
    // no takes yet: the guide
    let id: string | null = null;
    await act(async () => {
      id = await newCue({ shot: store.get().status[statusKey(EP, "proxy")]!.shots[4].shot, frame: 10 });
    });
    await act(async () => {
      await loadCue(EP, "proxy", id!);
    });
    await tab("Score");
    const link = q(".h3-cue-win a").find((a) => a.textContent === "Read Scoring an episode")!;
    expect(link.getAttribute("href")).toBe("https://docs.seriesmith.com/scoring");
    localStorage.clear();
  });
});
