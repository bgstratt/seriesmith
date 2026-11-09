import { describe, expect, it } from "vitest";
import { mappingChanges, withField } from "../src/components/PromptMapping";

describe("withField", () => {
  it("keeps the rest of a value's shape", () => {
    expect(withField("duration", { name: "duration", min: 4 }, "seconds")).toEqual({ name: "seconds", min: 4 });
    expect(withField("prompt", { list: "content", item: { text: "$prompt" } }, "messages"))
      .toEqual({ list: "messages", item: { text: "$prompt" } });
    expect(withField("first", { field: "image_url" }, "start")).toEqual({ field: "start" });
    expect(withField("prompt", "prompt", "text")).toBe("text");
  });
  it("sends none when it's emptied", () => {
    expect(withField("seed", { name: "seed" }, "  ")).toBeNull();
  });
  it("gives a value with no place yet the form its kind takes", () => {
    expect(withField("seed", null, "seed")).toEqual({ name: "seed" });
    expect(withField("references", null, "image_urls")).toEqual({ list: "image_urls" });
    expect(withField("prompt", null, "prompt")).toBe("prompt");
  });
});

describe("mappingChanges", () => {
  it("is what differs from the model's own, a removed value as null", () => {
    expect(mappingChanges({ a: 1, b: { name: "x" } }, { a: 1, b: { name: "y" }, c: 2 }))
      .toEqual({ b: { name: "x" }, c: null });
    expect(mappingChanges({ a: 1 }, { a: 1 })).toEqual({});
  });
});
