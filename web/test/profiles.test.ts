// The series config's profiles in the editor: editing them, and applying one to a new take.
import { describe, expect, it } from "vitest";
import { lorasList, lorasText, lorasValue, profileNameOk, profileRunPatch, profilesOf, setProfile, styledPrompt } from "../src/lib/profiles";

describe("profiles", () => {
  it("are read without the comments", () => {
    expect(Object.keys(profilesOf({ profiles: { _note: "x", flashback: { lens: "vintage" } } }))).toEqual(["flashback"]);
    expect(profilesOf({})).toEqual({});
  });
  it("are written without empty fields, and removed", () => {
    const raw = { series: { id: "s" }, profiles: { _note: "keep", a: { steps: 20, mine: 1 } } };
    const next = setProfile(raw, "a", { steps: 20, mine: 1, look: "", lens: undefined, loras: [] });
    expect(next.profiles).toEqual({ _note: "keep", a: { steps: 20, mine: 1 } });
    expect(setProfile(setProfile({}, "b", {}), "b", null)).toEqual({});
  });
  it("take a name a script line can say", () => {
    expect(profileNameOk("dream-seq_2")).toBe(true);
    expect(profileNameOk("a b")).toBe(false);
  });
  it("keep their LoRAs as a line", () => {
    expect(lorasText(["a.safetensors:0.6", { name: "b.safetensors", strength: 1 }])).toBe("a.safetensors:0.6, b.safetensors");
    expect(lorasValue(" a , ,b ")).toEqual(["a", "b"]);
    expect(lorasValue("")).toBeUndefined();
    expect(lorasList(["none"])).toEqual([]);
    expect(lorasList(["a.safetensors:0.6"])).toEqual([{ name: "a.safetensors", strength: 0.6 }]);
  });
  it("open a prompt as the build opens a shot's action", () => {
    expect(styledPrompt("Ada waits.", "a faded memory.", "vintage lenses: soft edges"))
      .toBe("A faded memory. Vintage lenses: soft edges. Ada waits.");
    const once = styledPrompt("Ada waits.", "a faded memory");
    expect(styledPrompt(once, "a faded memory")).toBe(once);              // not twice
  });
  it("change a new take", () => {
    const p = { target: "minimax_h3_ref2va", steps: 20, loras: ["none"], look: "a faded memory" };
    expect(profileRunPatch(p, "Ada waits.", false)).toEqual({
      target: "minimax_h3_ref2va", steps: "20", loras: [], prompt: "A faded memory. Ada waits." });
    expect(profileRunPatch(p, "Ada waits.", true).prompt).toBeUndefined();   // the model's own prompt
  });
});
