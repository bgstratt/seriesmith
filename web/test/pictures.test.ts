import { describe, expect, it } from "vitest";
import { initials, pictureOf } from "../src/lib/pictures";
import type { Ref } from "../src/types";

const RAW = {
  subjects: {
    ada: { kind: "character", name: "Ada", sheet: "../refs/ada/ada_sheet_4panel.png" },
    ada_coat: { of: "ada", design: "in a coat" },
    mo: { kind: "character", name: "Mo", sheet: "../refs/mo.png", sheet_panels: 1 },
    ladies: { kind: "character", name: "the ladies", members: 4, sheet: "../refs/ladies/ladies.png" },
    lantern: { kind: "prop", name: "the lantern", sheet: "../refs/props/lantern.png" },
    voice: { kind: "character", name: "Radio", voice: "crackly" },
  },
  locations: { porch: { description: "a porch", plate: "../refs/_bg/porch.png" } },
};

const ref = (id: string, path: string | null, exists = true, sha1: string | null = "abc"): Ref =>
  ({ id, path, exists, sha1 } as unknown as Ref);

describe("cast pictures", () => {
  it("a character's face, everything else whole", () => {
    expect(pictureOf(RAW, null, "subjects", "ada")).toEqual({ path: "../refs/ada/ada_sheet_4panel.png", face: true, version: null });
    expect(pictureOf(RAW, null, "subjects", "mo")?.face).toBe(false);          // one picture, not a sheet
    expect(pictureOf(RAW, null, "subjects", "ladies")?.face).toBe(false);      // a group
    expect(pictureOf(RAW, null, "subjects", "lantern")?.face).toBe(false);
    expect(pictureOf(RAW, null, "locations", "porch")).toEqual({ path: "../refs/_bg/porch.png", face: false, version: null });
    expect(pictureOf(RAW, null, "subjects", "voice")).toBeNull();
    expect(pictureOf(RAW, null, "subjects", "ada_coat")).toBeNull();           // derived: only the Refs list knows it
  });

  it("the Refs list's path, presence and version win", () => {
    const refs = [
      ref("subject:ada_coat", "../refs/ada_coat/ada_coat_sheet_4panel.png"),
      ref("subject:ada", "../refs/ada/ada_sheet_4panel.png", false),
      ref("location:porch", "../refs/_bg/porch.png", true, "f00d"),
    ];
    expect(pictureOf(RAW, refs, "subjects", "ada_coat")).toEqual({ path: "../refs/ada_coat/ada_coat_sheet_4panel.png", face: true, version: "abc" });
    expect(pictureOf(RAW, refs, "subjects", "ada")).toBeNull();                // not on disk
    expect(pictureOf(RAW, refs, "locations", "porch")?.version).toBe("f00d");
  });

  it("initials stand in", () => {
    expect(initials("Nell Moran")).toBe("NM");
    expect(initials("the porch lantern")).toBe("PL");
    expect(initials("ada")).toBe("AD");
  });
});
