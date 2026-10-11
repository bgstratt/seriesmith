import { describe, expect, it } from "vitest";
import {
  cardFields, cardKindOf, entryFor, idProblem, picturePath, refIdOf, refsPrefix, type Raw,
} from "../src/lib/seriesForm";

const show: Raw = {
  subjects: {
    ada: { kind: "character", name: "Ada", design: "a girl", sheet: "../refs/ada/ada_sheet_4panel.png", voice: "bright", note: "kept" },
    lantern: { kind: "prop", name: "the lantern", design: "brass", sheet: "../refs/props/lantern.png" },
    ladies: { kind: "character", name: "the ladies", members: 4, design: "four women", sheet: "../refs/ladies/ladies.png" },
    narrator: { kind: "character", name: "Narrator", voice: "low and slow" },
    ada_wet: { of: "ada", design: "a soaked girl" },
  },
  locations: { porch: { description: "a porch at dawn", plate: "../refs/_bg/porch.png" } },
};

describe("cast cards", () => {
  it("knows what each entry is", () => {
    expect(cardKindOf(show, "subjects", "ada")).toBe("character");
    expect(cardKindOf(show, "subjects", "lantern")).toBe("prop");
    expect(cardKindOf(show, "subjects", "ladies")).toBe("group");
    expect(cardKindOf(show, "subjects", "narrator")).toBe("voice");
    expect(cardKindOf(show, "subjects", "ada_wet")).toBe("character");
    expect(cardKindOf(show, "locations", "porch")).toBe("location");
  });

  it("names pictures the way the show already does", () => {
    expect(refsPrefix(show)).toBe("../refs/");
    expect(refsPrefix({ subjects: { a: { sheet: "refs/a/a.png" } } })).toBe("refs/");
    expect(refsPrefix({})).toBe("../refs/");
    expect(picturePath("character", "bo", "../refs/")).toBe("../refs/bo/bo_sheet_4panel.png");
    expect(picturePath("prop", "kettle", "refs/")).toBe("refs/props/kettle.png");
    expect(picturePath("location", "street", "../refs/")).toBe("../refs/_bg/street.png");
    expect(picturePath("group", "fam", "../refs/")).toBe("../refs/fam/fam.png");
    expect(picturePath("voice", "x", "../refs/")).toBeUndefined();
  });

  it("refuses an id that's taken or malformed", () => {
    expect(idProblem(show, "ada")).toMatch(/already a subject/);
    expect(idProblem(show, "porch")).toMatch(/already a location/);
    expect(idProblem(show, "Bo Smith")).toMatch(/lower case/);
    expect(idProblem(show, "")).toMatch(/Give it an id/);
    expect(idProblem(show, "bo")).toBe("");
  });

  it("a new character gets its kind and a sheet path", () => {
    const e = entryFor("character", undefined, { name: "Bo", design: "a boy", voice: "" }, "bo", "../refs/");
    expect(e).toEqual({ kind: "character", name: "Bo", design: "a boy", sheet: "../refs/bo/bo_sheet_4panel.png" });
  });

  it("a group's size is a number; a voice gets no picture; a variant derives its sheet", () => {
    expect(entryFor("group", undefined, { name: "the band", design: "five", members: "5" }, "band", "../refs/"))
      .toEqual({ kind: "character", name: "the band", design: "five", members: 5, sheet: "../refs/band/band.png" });
    expect(entryFor("voice", undefined, { name: "Radio", voice: "crackly" }, "radio", "../refs/"))
      .toEqual({ kind: "character", name: "Radio", voice: "crackly" });
    expect(entryFor("character", undefined, { of: "ada", design: "in a towel" }, "ada_towel", "../refs/"))
      .toEqual({ kind: "character", of: "ada", design: "in a towel" });
  });

  it("an edit keeps what the form doesn't show and drops what was cleared", () => {
    const before = (show.subjects as Record<string, Raw>).ada;
    const e = entryFor("character", before, { name: "Ada", design: "a taller girl", voice: "" }, "ada", "../refs/");
    expect(e.note).toBe("kept");
    expect(e.design).toBe("a taller girl");
    expect("voice" in e).toBe(false);
    expect(e.sheet).toBe("../refs/ada/ada_sheet_4panel.png");
    expect(Object.keys(e)).toEqual(["kind", "name", "design", "sheet", "note"]);
  });

  it("a location gets a plate; an angle names its master", () => {
    expect(entryFor("location", undefined, { description: "the porch from the lawn", of: "porch" }, "porch_lawn", "../refs/"))
      .toEqual({ description: "the porch from the lawn", of: "porch", plate: "../refs/_bg/porch_lawn.png" });
  });

  it("each kind's fields, and the choices for variant and angle", () => {
    const ids = (k: Parameters<typeof cardFields>[0]) => cardFields(k, show, "new").map((f) => f.path[0]);
    expect(ids("character")).toEqual(["name", "design", "voice", "of", "sheet", "sheet_panels", "voice_sample"]);
    expect(ids("group")).toContain("members");
    expect(ids("voice")).toEqual(["name", "voice", "voice_sample"]);
    expect(ids("location")).toEqual(["description", "of", "plate"]);
    const variantOf = cardFields("character", show, "new").find((f) => f.path[0] === "of")!.choices!.map((c) => c.value);
    expect(variantOf).toContain("ada");
    expect(variantOf).not.toContain("ada_wet");          // a variant isn't a base
    expect(variantOf).not.toContain("lantern");          // not a character
    expect(refIdOf("location", "porch")).toBe("location:porch");
    expect(refIdOf("character", "ada")).toBe("subject:ada");
  });
});
