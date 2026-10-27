// P4: a ref's cfg and sampler knobs as override fields, and a take's
// settings made the ref's ("Use these settings").
import { describe, expect, it } from "vitest";
import { knobFields, knobsOf, regenerateRequest, takeSettings } from "../src/lib/refSettings";
import type { RefTake } from "../src/types";

describe("ref sampler settings", () => {
  const none = knobsOf({});

  it("reads an override as text", () => {
    const k = knobsOf({ cfg: 3.5, params: { sampler: "er_sde", denoise: 0.8 } });
    expect(k).toMatchObject({ cfg: "3.5", sampler: "er_sde", denoise: "0.8", scheduler: "" });
  });

  it("sends only what changed, params whole", () => {
    expect(knobFields(none, none)).toEqual({});
    expect(knobFields({ ...none, cfg: "2" }, none)).toEqual({ cfg: 2 });
    expect(knobFields({ ...none, sampler: "er_sde", scheduler: "beta" }, none))
      .toEqual({ params: { sampler: "er_sde", scheduler: "beta" } });
    const set = knobsOf({ cfg: 2, params: { sampler: "euler" } });
    expect(knobFields({ ...set, cfg: "", sampler: "" }, set)).toEqual({ cfg: null, params: null });
  });

  it("refuses a knob that isn't a number", () => {
    expect(() => knobFields({ ...none, denoise: "high" }, none)).toThrow(/denoise/);
  });

  it("a take's settings become the override (not its prompt)", () => {
    const t = {
      take: 2, status: "ok", source: "generated", seed: "77", model: "", loras: null, steps: 25,
      cfg: 1, params: { sampler: "euler" }, width: 1344, height: 768, prompt: "x", note: "", image: null,
    } as unknown as RefTake;
    expect(takeSettings(t, false)).toEqual({
      seed: "77", model: null, loras: null, steps: 25, cfg: 1, params: { sampler: "euler" }, size: "1344x768",
    });
    expect(takeSettings(t, true)).not.toHaveProperty("size");     // a keyframe's size is its shot's
  });
});

describe("the gallery's Regenerate", () => {
  const drawn = {
    take: 3, status: "ok", source: "generated", seed: "77", image: "a.png", note: "", prompt: "the whole prompt",
    model: "m.safetensors", loras: [{ name: "l", strength: 1 }], steps: 25, cfg: 3.5, params: { sampler: "euler" },
    width: 1024, height: 1024, target: "krea2",
  } as RefTake;

  it("is the candidate's own settings with a new seed", () => {
    expect(regenerateRequest(drawn, "subject:ada", "04_face", false)).toEqual({
      ref: "subject:ada", view: "04_face", count: 1, seed_mode: "new", seed: null, note: "", target: "krea2",
      prompt: "the whole prompt", model: "m.safetensors", loras: [{ name: "l", strength: 1 }], steps: 25,
      cfg: 3.5, params: { sampler: "euler" }, size: "1024x1024",
    });
    expect(regenerateRequest(drawn, "shot:sh010:first", null, true)).not.toHaveProperty("size");
  });

  it("an edit is the same edit again", () => {
    const edited = { ...drawn, source: "edited", edit: { take: 1, view: "01_threequarter", instruction: "a red coat", wrap: true } } as RefTake;
    expect(regenerateRequest(edited, "subject:ada", "04_face", false)).toMatchObject({
      prompt: "a red coat", model: null, edit: { take: 1, wrap: true, from_view: "01_threequarter" },
    });
  });

  it("nothing for what wasn't drawn, or didn't finish", () => {
    expect(regenerateRequest({ ...drawn, source: "imported" }, "subject:ada", null, false)).toBeNull();
    expect(regenerateRequest({ ...drawn, status: "failed" }, "subject:ada", null, false)).toBeNull();
  });
});
