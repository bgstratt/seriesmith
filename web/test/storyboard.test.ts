import { describe, expect, it } from "vitest";
import { BEAT_MIN_W, beatWidth, clock, placeOf, positive, TILE_GAP, TILE_W } from "../src/lib/storyboard";

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
