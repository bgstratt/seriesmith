// The sequence relight dialog's choices: a picked preset goes as its id, typed words as they are.
import { describe, expect, it } from "vitest";
import { relightValue, suffixOk } from "../src/components/RelightDialog";

const tiles = [{ id: "dusk", text: "Change only the time of day and the light: it is dusk" }];

describe("relight dialog", () => {
  it("sends a picked preset by its id", () => {
    expect(relightValue(tiles, " Change only the time of day and the light: it is dusk ")).toBe("dusk");
  });
  it("sends typed words as they are", () => {
    expect(relightValue(tiles, " night, heavy rain ")).toBe("night, heavy rain");
    expect(relightValue(tiles, "")).toBe("");
  });
  it("takes a name of letters, digits and _", () => {
    expect(suffixOk("flashback_2")).toBe(true);
    expect(suffixOk("a b")).toBe(false);
    expect(suffixOk("dusk-1")).toBe(false);
  });
});
