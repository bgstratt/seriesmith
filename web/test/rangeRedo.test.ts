// Frames of a take made again: the dialog's times as frames.
import { describe, expect, it } from "vitest";
import { frameAt, rangeAsked, rangeText, timeOf } from "../src/lib/rangeRedo";

describe("a range of a take", () => {
  it("takes the frame on screen at a time", () => {
    expect(frameAt(3.1, 24)).toBe(74);
    expect(frameAt(0, 24)).toBe(0);
    expect(frameAt(74 / 24, 24)).toBe(74);
  });

  it("reads a start and an end to the end of the take", () => {
    expect(rangeAsked("3.10", timeOf(123, 24), 124, 24)).toEqual({ first: 74, last: 123, problem: "" });
  });

  it("stops an end past the take at its last frame", () => {
    expect(rangeAsked("3.10", "99", 124, 24)).toEqual({ first: 74, last: 123, problem: "" });
  });

  it("refuses what isn't a range inside the take", () => {
    expect(rangeAsked("", "2", 124, 24).problem).toMatch(/start and an end/);
    expect(rangeAsked("x", "2", 124, 24).problem).toMatch(/start and an end/);
    expect(rangeAsked("-1", "2", 124, 24).problem).toMatch(/inside the take/);
    expect(rangeAsked("9", "10", 124, 24).problem).toMatch(/inside the take/);
    expect(rangeAsked("3", "2", 124, 24).problem).toMatch(/after the start/);
  });

  it("takes one frame", () => {
    expect(rangeAsked("1", "1", 124, 24)).toEqual({ first: 24, last: 24, problem: "" });
  });

  it("says what it is", () => {
    expect(rangeText(74, 123, 24)).toBe("frames 74-123, 2.08 s");
  });
});
