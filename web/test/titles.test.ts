import { describe, expect, it } from "vitest";
import { cssColor, titleAlpha } from "../src/lib/titles";

const SUB = { size: 0.058, y: 0.56, color: "#F4E6D0", glow: "#FFB45A@0.8", intro_in: [4, 5] as [number, number],
              outro_in: [0, 1] as [number, number], outro_out: [4.5, 5.5] as [number, number] };

describe("titleAlpha", () => {
  it("fades the title in on the intro and keeps it", () => {
    expect(titleAlpha("intro", SUB, 3)).toBe(0);
    expect(titleAlpha("intro", SUB, 4.5)).toBeCloseTo(0.5);
    expect(titleAlpha("intro", SUB, 7)).toBe(1);
  });
  it("fades it in and out on the outro", () => {
    expect(titleAlpha("outro", SUB, 0.5)).toBeCloseTo(0.5);
    expect(titleAlpha("outro", SUB, 3)).toBe(1);
    expect(titleAlpha("outro", SUB, 5)).toBeCloseTo(0.5);
    expect(titleAlpha("outro", SUB, 6)).toBe(0);
  });
});

describe("cssColor", () => {
  it("reads ffmpeg's colour@alpha", () => {
    expect(cssColor("#FFB45A@0.8")).toBe("rgba(255, 180, 90, 0.8)");
    expect(cssColor("#F4E6D0")).toBe("rgba(244, 230, 208, 1)");
    expect(cssColor("white")).toBe("white");
  });
});
