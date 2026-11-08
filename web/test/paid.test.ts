import { describe, expect, it } from "vitest";
import { paidAsk } from "../src/lib/paid";

describe("paidAsk", () => {
  it("asks only when it's billed, saying where", () => {
    expect(paidAsk(null, "Render 2 takes of m01?")).toBeNull();
    expect(paidAsk(undefined, "Render 2 takes of m01?")).toBeNull();
    expect(paidAsk("Pika Music runs on Comfy Router: each take is billed to your Comfy account", "Render 2 takes of m01?"))
      .toBe("Render 2 takes of m01?\n\nPika Music runs on Comfy Router: each take is billed to your Comfy account. Go ahead?");
  });
});
