import { describe, expect, it } from "vitest";
import { newShot } from "../src/lib/shotForm";
import {
  castId, castOfConfig, castProblems, firstScript, seriesConfig, showFolder, withCast, type NewCast,
} from "../src/lib/wizard";

describe("the new episode wizard", () => {
  it("names things from what the user typed", () => {
    expect(castId("the porch lantern")).toBe("porch_lantern");
    expect(castId("Mabel Okafor")).toBe("mabel_okafor");
    expect(castId("2nd floor")).toBe("x_2nd_floor");
    expect(castId("")).toBe("");
    expect(showFolder("Porch Lights!")).toBe("Porch_Lights");
    const s = seriesConfig("First Light");
    expect(s.series).toMatchObject({ id: "first_light", title: "First Light", width: 1344, height: 768 });
    expect(s.proxy).toMatchObject({ width: 864, height: 480 });
  });

  it("adds the cast by the card's rules, and says what's wrong", () => {
    const base = seriesConfig("Dusk");
    const cast: NewCast[] = [
      { kind: "character", id: "nell", fields: { name: "Nell", design: "a woman in a red coat" } },
      { kind: "location", id: "pier", fields: { description: "a wooden pier at dusk" } },
      { kind: "prop", id: "", fields: {} },
      { kind: "character", id: "nell", fields: { name: "Nell" } },
    ];
    expect(castProblems(base, cast)).toEqual(["", "", "Give it a name.", "nell is here twice."]);
    const full = withCast(base, cast.slice(0, 2), "../refs/");
    expect(full.subjects).toEqual({ nell: { kind: "character", name: "Nell", design: "a woman in a red coat",
      sheet: "../refs/nell/nell_sheet_4panel.png" } });
    expect(full.locations).toEqual({ pier: { description: "a wooden pier at dusk", plate: "../refs/_bg/pier.png" } });
    expect(base.subjects).toEqual({});                     // the base is left as it was
    expect(castOfConfig(full)).toEqual({ characters: [{ id: "nell", name: "Nell" }], things: [], locations: ["pier"] });
  });

  it("writes the first script", () => {
    const shot = newShot("sh010");
    shot.keys.who = "nell";
    shot.action = "Nell walks to the end of the pier.";
    expect(firstScript("ep01", "The Pier", "sq01", "pier", shot)).toBe(
      "= ep01  The Pier\n\n# sq01  pier\n\n## sh010\nwho: nell\nsize: medium\ndur: 3.04\nNell walks to the end of the pier.\n");
    expect(firstScript("ep02", "", "sq01", "pier", newShot("sh010")).split("\n")[0]).toBe("= ep02");
  });
});
