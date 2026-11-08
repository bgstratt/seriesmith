import { describe, expect, it } from "vitest";
import { BEAT_MIN_W, beatWidth, BOX_W, boxShots, clock, freshBoxes, placeOf, positive, removeBox, seriesChoices, splitBox, TILE_GAP, TILE_W } from "../src/lib/storyboard";

describe("beatWidth", () => {
  it("is its tiles in a line, and no wider than the row", () => {
    expect(beatWidth(10)).toBe(`min(100%, ${10 * (TILE_W + TILE_GAP) - TILE_GAP}px)`);
  });

  it("leaves a one-shot beat room for its name", () => {
    expect(beatWidth(1)).toBe(`min(100%, ${BEAT_MIN_W}px)`);
  });
});

describe("clock", () => {
  it("writes minutes and seconds", () => {
    expect(clock(0)).toBe("0:00");
    expect(clock(65)).toBe("1:05");
    expect(clock(1320)).toBe("22:00");
  });

  it("writes hours from an hour", () => {
    expect(clock(6000)).toBe("1:40:00");
    expect(clock(3723)).toBe("1:02:03");
  });
});

describe("positive", () => {
  it("reads a number above zero", () => {
    expect(positive("7")).toBe(7);
    expect(positive(" 3.5 ")).toBe(3.5);
  });

  it("is null for anything else", () => {
    for (const text of ["", "  ", "0", "-2", "abc", "Infinity"]) expect(positive(text)).toBeNull();
  });
});

describe("placeOf", () => {
  it("writes a span and a point", () => {
    expect(placeOf({ at: [10, 12] })).toBe("10–12%");
    expect(placeOf({ point: 50 })).toBe("at 50%");
  });

  it("is empty for a beat with no place", () => {
    expect(placeOf({})).toBe("");
  });
});

describe("sequence boxes", () => {
  const box = (weight: number, place = "") => ({ place, cast: [] as string[], weight });

  it("starts a beat as one sequence with no place", () => {
    expect(freshBoxes()).toEqual([{ place: "", cast: [], weight: 1 }]);
  });

  it("gives one sequence all the beat's shots", () => {
    expect(boxShots([box(1)], 7)).toEqual([7]);
  });

  it("shares shots by weight and adds up", () => {
    expect(boxShots([box(1), box(1)], 7)).toEqual([4, 3]);
    expect(boxShots([box(3), box(1)], 8)).toEqual([6, 2]);
  });

  it("keeps the proportion as the beat changes length", () => {
    const boxes = [box(0.5), box(0.25), box(0.25)];
    for (const shots of [8, 40, 400]) {
      const out = boxShots(boxes, shots);
      expect(out.reduce((a, b) => a + b, 0)).toBe(shots);
      expect(out[0]).toBe(shots / 2);
    }
  });

  it("gives each sequence a shot first, and the last ones none when the beat runs out", () => {
    expect(boxShots([box(9), box(1), box(1)], 3)).toEqual([1, 1, 1]);
    expect(boxShots([box(1), box(1), box(1)], 2)).toEqual([1, 1, 0]);
  });

  it("splits a sequence in half, the new one keeping its place and cast", () => {
    const out = splitBox([{ place: "diner", cast: ["june"], weight: 1 }], 0);
    expect(out).toEqual([{ place: "diner", cast: ["june"], weight: 0.5 }, { place: "diner", cast: ["june"], weight: 0.5 }]);
    expect(out[0].cast).not.toBe(out[1].cast);
  });

  it("gives a removed sequence's share to the one before, or the next for the first", () => {
    expect(removeBox([box(1, "a"), box(2, "b")], 1)).toEqual([box(3, "a")]);
    expect(removeBox([box(1, "a"), box(2, "b")], 0)).toEqual([box(3, "b")]);
  });

  it("keeps the last sequence", () => {
    expect(removeBox([box(1, "a")], 0)).toEqual([box(1, "a")]);
  });

  it("makes room for its boxes in the beat's width", () => {
    expect(beatWidth(10, 2)).toBe(`min(100%, ${10 * (TILE_W + TILE_GAP) + 2 * (BOX_W + TILE_GAP) - TILE_GAP}px)`);
  });
});

describe("seriesChoices", () => {
  const text = JSON.stringify({
    subjects: { june: { kind: "character", name: "June" }, lantern: { kind: "prop" }, car: { kind: "vehicle" }, ada: {} },
    locations: { diner: {}, street_gate: {} },
  });

  it("offers the locations", () => {
    expect(seriesChoices(text).places).toEqual(["diner", "street_gate"]);
  });

  it("leaves props and vehicles out of the cast", () => {
    expect(seriesChoices(text).cast).toEqual([{ id: "june", name: "June" }, { id: "ada", name: "ada" }]);
  });

  it("copes with a series that has neither", () => {
    expect(seriesChoices("{}")).toEqual({ places: [], cast: [] });
  });
});
