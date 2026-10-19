// The look builder's line, from the real presets (seriesmith/presets/look_builder.json):
// the same strings tests/test_presets.py expects of compose_look, so the two agree.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { composeLook, togglePart, visibleRows } from "../src/lib/lookBuilder";
import type { LookBuilderRow } from "../src/types";

const rows = JSON.parse(readFileSync(join(__dirname, "..", "..", "seriesmith", "presets", "look_builder.json"), "utf8")).rows as LookBuilderRow[];

describe("the look builder", () => {
  it("writes the brief: the medium, then each part", () => {
    expect(composeLook(rows, { medium: "live_action", camera: "film35", lens: "anamorphic", light: "low_key", grade: "muted" })).toBe(
      "a live-action film; shot on 35mm film; anamorphic lenses: oval bokeh, horizontal lens flares, slight distortion at the edges; "
      + "low-key light from the practical lamps in each space, pools of light and deep soft shadow; a muted, desaturated grade with lifted blacks");
  });
  it("leaves the camera rows out of a drawn medium, and writes nothing without one", () => {
    expect(composeLook(rows, { medium: "anime", camera: "film35", light: "soft" })).toBe(
      "a hand-drawn Japanese anime: expressive line art, cel-shaded figures over richly painted backgrounds; soft naturalistic window and daylight, gentle shadows");
    expect(visibleRows(rows, { medium: "anime" }).map((r) => r.id)).toEqual(["medium", "light", "grade"]);
    expect(visibleRows(rows, { medium: "live_action" }).length).toBe(6);
    expect(composeLook(rows, { camera: "film35" })).toBe("");
  });
  it("a second click clears a pick", () => {
    expect(togglePart({ grade: "muted" }, "grade", "muted")).toEqual({});
    expect(togglePart({ grade: "muted" }, "grade", "warm")).toEqual({ grade: "warm" });
  });
});
