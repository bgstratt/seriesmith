// The editor's copy of a shot's colour maths (src/lib/color.ts), held to the
// cases seriesmith/color.py's test holds the server's to.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { cleanColor, colorMatrix, feColorMatrixValues, hasColor } from "../src/lib/color";

const CASES = JSON.parse(readFileSync(new URL("../../tests/fixtures/color_cases.json", import.meta.url), "utf-8")).cases as
  { color: Record<string, number>; m: number[][]; offset: number[] }[];

describe("a shot's colour", () => {
  it("is the server's matrix, case for case", () => {
    for (const c of CASES) {
      const { m, offset } = colorMatrix(c.color);
      m.forEach((row, i) => row.forEach((v, j) => expect(v).toBeCloseTo(c.m[i][j], 7)));
      offset.forEach((v, i) => expect(v).toBeCloseTo(c.offset[i], 7));
    }
  });
  it("keeps what isn't 0, in range", () => {
    expect(cleanColor({ exposure: 0, warmth: 0.12345, black: 9 })).toEqual({ warmth: 0.123, black: 0.25 });
    expect(hasColor({ exposure: 0 })).toBe(false);
    expect(hasColor(null)).toBe(false);
  });
  it("as an feColorMatrix: identity at 0", () => {
    expect(feColorMatrixValues({})).toBe("1 0 0 0 0 0 1 0 0 0 0 0 1 0 0 0 0 0 1 0");
  });
});

describe("a clip's colour in the cut", () => {
  it("travels with the entry, and an edit of it is undoable", async () => {
    const { withFields, entryOf, sameEntries } = await import("../src/lib/cutEdit");
    const { diffEdit, applyEdit } = await import("../src/lib/undo");
    const before = [{ shot: "a" }, { shot: "b", trim_in: 3 }];
    const after = withFields(before, "b", { color: { warmth: 0.2, exposure: 0 } });
    expect(after[1]).toEqual({ shot: "b", trim_in: 3, color: { warmth: 0.2 } });
    expect(sameEntries(before, after)).toBe(false);
    const edit = diffEdit("Colour b", before, after)!;
    expect(applyEdit(after, edit, "undo")[1]).toEqual({ shot: "b", trim_in: 3 });
    expect(withFields(after, "b", { trim_in: 5 })[1].color).toEqual({ warmth: 0.2 });
    const st = { shot: "b", cut: { color: { saturation: -0.5 }, trim_in: 0, trim_out: 0 } };
    expect(entryOf(st as never, "proxy")).toEqual({ shot: "b", color: { saturation: -0.5 } });
  });
});

describe("matching a sequence's colour to a clip", () => {
  it("sets every match as one cut edit, through the mock", async () => {
    const { setApi, setHost } = await import("../src/host");
    const { createMockApi } = await import("../src/mock/mockApi");
    const { store, initialState, statusKey } = await import("../src/store");
    const { refreshEpisode } = await import("../src/actions");
    const { matchColors } = await import("../src/cutActions");
    const toasts: string[] = [];
    setHost({ on: () => () => {}, toast: (_k: string, t: string) => toasts.push(t), show: () => {} } as never);
    const api = createMockApi(() => {}, { latency: 0 });
    setApi(api);
    const ep = (await api.episodes())[0].ep;
    store.set(initialState());
    store.set({ ep, pass: "proxy" });
    await refreshEpisode(ep, "proxy");
    const st = store.get().status[statusKey(ep, "proxy")]!;
    const base = st.shots[0];
    const put = (await import("vitest")).vi.spyOn(api, "putCut");
    expect(await matchColors(base.shot)).toBe(true);
    expect(put).toHaveBeenCalledTimes(1);
    const coloured = put.mock.calls[0][2].filter((e) => e.color);
    expect(coloured.length).toBeGreaterThan(0);
    expect(coloured.every((e) => st.shots.find((s) => s.shot === e.shot)?.sequence === base.sequence)).toBe(true);
    expect(toasts.at(-1)).toContain(`matched to ${base.shot}`);
  });

  it("asks the server to compare the way the button says", async () => {
    const { setApi, setHost } = await import("../src/host");
    const { createMockApi } = await import("../src/mock/mockApi");
    const { store, initialState } = await import("../src/store");
    const { refreshEpisode } = await import("../src/actions");
    const { MATCH_WAYS, matchColors } = await import("../src/cutActions");
    setHost({ on: () => () => {}, toast: () => {}, show: () => {} } as never);
    const api = createMockApi(() => {}, { latency: 0 });
    setApi(api);
    const ep = (await api.episodes())[0].ep;
    store.set(initialState());
    store.set({ ep, pass: "proxy" });
    await refreshEpisode(ep, "proxy");
    const base = store.get().status[`${ep}|proxy`]?.shots[0] ?? Object.values(store.get().status)[0]!.shots[0];
    const ask = (await import("vitest")).vi.spyOn(api, "colorMatch");
    expect(MATCH_WAYS.map((w) => w.by)).toEqual(["skin", "frame", "luma"]);
    for (const w of MATCH_WAYS) await matchColors(base.shot, undefined, w.by);
    expect(ask.mock.calls.map((c) => c[4])).toEqual(["skin", "frame", "luma"]);
    expect(store.get().busy[`colormatch|${base.shot}`]).toBeUndefined();
  });
});
