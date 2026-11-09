import { describe, expect, it } from "vitest";
import { chipOf, clock, inUse, soundSections, useLabel } from "../src/lib/soundGallery";
import type { SoundSection } from "../src/types";

const take = (key: string, take: number, use = false, more = {}) => ({
  key, take, path: `${key}.wav`, use, model: "stable_audio3", seed: 1, made: null, seconds: 7.2, ...more,
});
const ALL: SoundSection[] = [
  { kind: "music", id: "theme_c", name: "Theme C: When the Knock Comes", note: "song", queued: 0, failed: 0,
    items: [take("m|2", 2, true), take("m|1", 1, false, { theme: "knock" })] },
  { kind: "effects", id: "sh010", name: "sh010", note: "", queued: 1, failed: 0, items: [] },
  { kind: "lines", id: "sh010_l1", name: "sh010_l1", note: "Ada", queued: 0, failed: 0,
    items: [take("l|1", 1, true, { text: "Coffee's cold.", who: "Ada", model: "elevenlabs_tts" })] },
];

describe("soundSections", () => {
  it("narrows to a kind, one section, the ones in use", () => {
    expect(soundSections(ALL, {}).map((s) => s.id)).toEqual(["theme_c", "sh010", "sh010_l1"]);
    expect(soundSections(ALL, { sound: "voices" }).map((s) => s.id)).toEqual(["sh010_l1"]);
    expect(soundSections(ALL, { sound: "music", section: "sh010" }).map((s) => s.id)).toEqual(["sh010"]);
    // in use only: the effects with only a take on the way drop out
    expect(soundSections(ALL, { picksOnly: true }).map((s) => [s.id, s.items.map((i) => i.take)]))
      .toEqual([["theme_c", [2]], ["sh010_l1", [1]]]);
  });
  it("searches a section's words and a take's", () => {
    expect(soundSections(ALL, { query: "knock t01" }).map((s) => s.items.map((i) => i.key))).toEqual([["m|1"]]);
    expect(soundSections(ALL, { query: "theme" })[0].items.map((i) => i.key)).toEqual(["m|2", "m|1"]);
    expect(soundSections(ALL, { query: "coffee ada" }).map((s) => s.id)).toEqual(["sh010_l1"]);
    expect(soundSections(ALL, { query: "mix" }).map((s) => s.id)).toEqual(["theme_c"]);
    expect(soundSections(ALL, { query: "nothing-like-it" })).toEqual([]);
  });
});

describe("the rest", () => {
  it("names and times", () => {
    expect(chipOf("lines")).toBe("voices");
    expect(useLabel("music")).toBe("in the mix");
    expect(useLabel("ambience")).toBe("picked");
    expect(clock(7.2)).toBe("0:07");
    expect(clock(64)).toBe("1:04");
    expect(clock(null)).toBe("");
    expect(inUse(ALL[0])?.take).toBe(2);
  });
});
