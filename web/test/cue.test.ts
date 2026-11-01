// @vitest-environment happy-dom
//
// The cue window (docs/SOUND.md "The cue window"): the bar grid's arithmetic,
// a section edge dragged to whole bars, an arc point dragged to an anchor and
// a level, how the takes read; then the window on the mock's cue (its hits,
// sections, arc and ranked takes), an edit, a pick, and a new cue.
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  addPoint, arcPoints, arcSpec, barBeat, clipsOver, editableSections, gridOf, hitChip, impliedPoints, levelY, levelsAsEnergy, moveEdge,
  movePoint, newCueId, newCueSpan, patchSection, ranks, removePoint, snapBeat, tauX, withSpec, xTau, yLevel,
} from "../src/lib/cue";
import type { PlayItem } from "../src/lib/playlist";
import type { CuePlan, CueSpec, CueTake } from "../src/types";

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

// ---------------------------------------------------------------------------
// the window, on the mock
// ---------------------------------------------------------------------------

import { refreshEpisode } from "../src/actions";
import { Viewer } from "../src/components/Viewer";
import { cueKey, cueSettled, loadCue, newCue, openCue, pickCueTake } from "../src/cueActions";
import { resetCutHistory } from "../src/cutActions";
import { setApi, setHost, type Host } from "../src/host";
import { createMockApi } from "../src/mock/mockApi";
import { currentMix, loadMix } from "../src/mixActions";
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
    // the other tabs are coming
    const tabs = [...side.ownerDocument.querySelectorAll<HTMLButtonElement>(".h3-cue-win .h3-seg button")];
    expect(tabs.map((b) => [b.textContent, b.disabled])).toEqual([["Score", false], ["Arc", true], ["Orchestration & takes", true]]);
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
});
