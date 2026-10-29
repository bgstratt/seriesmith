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
      expect(offset).toEqual(c.offset);
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
