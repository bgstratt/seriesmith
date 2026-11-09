import { describe, expect, it } from "vitest";
import { filmStep, nameOfId, scriptForEpisode, scriptNames, scriptShots } from "../src/lib/filmPath";
import { withScriptNames } from "../src/lib/wizard";

const SCRIPT = `= ep09  The Pier

# sq01  porch

## sh010
who: ada, old_tom
with: lantern
dur: 3
Ada waits.

## sh020
target: hold
who: ada
dur: 3
Tom arrives.

# sq02  pier

## sh030
target: ltx2
dur: 3
The water.
`;

describe("what a script says", () => {
  it("lists its shots and which have no model", () => {
    expect(scriptShots(SCRIPT)).toEqual([{ id: "sh010", hold: false }, { id: "sh020", hold: true }, { id: "sh030", hold: false }]);
  });

  it("names its people, things and places once each", () => {
    expect(scriptNames(SCRIPT)).toEqual({ characters: ["ada", "old_tom"], things: ["lantern"], locations: ["porch", "pier"] });
  });

  it("makes a name from an id", () => {
    expect(nameOfId("old_tom")).toBe("Old Tom");
  });
});

describe("a script pasted in", () => {
  it("goes under this episode's name and keeps its own title", () => {
    expect(scriptForEpisode("ep01", "Other", "= ep09  The Pier\n\n# sq01  porch\n")).toBe("= ep01  The Pier\n\n# sq01  porch\n");
  });

  it("uses the title given when it has none", () => {
    expect(scriptForEpisode("ep01", "Other", "= ep09\n\n# sq01  porch\n")).toBe("= ep01  Other\n\n# sq01  porch\n");
  });

  it("gets a head when it has none", () => {
    expect(scriptForEpisode("ep01", "", "# sq01  porch\n")).toBe("= ep01\n\n# sq01  porch\n");
  });
});

describe("cards from a script", () => {
  const raw = { subjects: { ada: { kind: "character", name: "Ada", design: "x" } }, locations: { porch: { description: "y" } } };

  it("offers only what the series hasn't got, with the script's ids", () => {
    const out = withScriptNames([], raw, SCRIPT);
    expect(out.map((c) => [c.kind, c.id, c.fixed])).toEqual([["character", "old_tom", true], ["location", "pier", true], ["prop", "lantern", true]]);
    expect(out[0].fields.name).toBe("Old Tom");
  });

  it("adds nothing twice", () => {
    const once = withScriptNames([], raw, SCRIPT);
    expect(withScriptNames(once, raw, SCRIPT)).toEqual(once);
  });
});

describe("the step an episode is on", () => {
  const f = { shots: 3, structure: false, missing: 0, held: 0, unrendered: 0 };

  it("waits for a story", () => expect(filmStep({ ...f, shots: 0 })).toBe(1));
  it("makes the pictures next", () => expect(filmStep({ ...f, missing: 2, held: 3 })).toBe(2));
  it("goes to the board with a structure and no shots", () => expect(filmStep({ ...f, shots: 0, structure: true })).toBe(3));
  it("stays on the board while shots have no model", () => expect(filmStep({ ...f, held: 1, unrendered: 2 })).toBe(3));
  it("films what has no take", () => expect(filmStep({ ...f, unrendered: 2 })).toBe(4));
  it("is ready to watch", () => expect(filmStep(f)).toBe(5));
});
