// A continuous shot in words (ShotStatus.continuous): the badge every shot list
// shows, and the inspector's and shot form's line saying how and on what model.
import { describe, expect, it } from "vitest";
import { continuityBadge, continuityText } from "../src/lib/continuity";
import { shotBadges } from "../src/lib/format";
import type { ShotStatus } from "../src/types";

const shot = (p: Partial<ShotStatus>): ShotStatus => ({
  shot: "sh020", orphan: false, sequence: "sq01", length: 124, seconds: 124 / 24, size: "mws",
  subjects: [], audio_policy: null, override: { fields: [], stale: false }, takes: [],
  cut: { take: null, picked: false, pass: "final", placeholder: false, usable: false } as ShotStatus["cut"],
  ...p,
});

describe("continuity", () => {
  it("a shot that doesn't continue has no badge and no line", () => {
    const s = shot({});
    expect(continuityBadge(s)).toBeNull();
    expect(continuityText(s, null)).toBeNull();
    expect(shotBadges(s).some((b) => b.kind === "continuous")).toBe(false);
  });
  it("latent: the shot it holds, how many frames, on its model", () => {
    const s = shot({ target: "fasth3_omni", continuous: { mode: "latent", from: "sh010", hold: 39 } });
    expect(continuityBadge(s)!.label).toBe("latent ← sh010");
    const t = continuityText(s, null)!;
    expect(t).toMatch(/sh010 by latent on fasth3_omni/);
    expect(t).toMatch(/last 39 frames \(1\.6 s\)/);
    expect(shotBadges(s).find((b) => b.kind === "continuous")?.label).toBe("latent ← sh010");
  });
  it("first: FL2VA draws from words; Ref2VA and Singularity keep their pictures", () => {
    const fl = shot({ target: "fasth3_fl2va", continuous: { mode: "first", from: "sh010" } });
    expect(continuityBadge(fl)!.label).toBe("first frame ← sh010");
    expect(continuityText(fl, null)).toMatch(/first\/last-frame model.*without the character or place pictures/);
    const ref = shot({ target: "minimax_h3_ref2va", continuous: { mode: "first", from: "sh010" } });
    expect(continuityText(ref, null)).toMatch(/pictures kept/);
    const ltx = shot({ target: "ltx2", continuous: { mode: "first", from: "sh010" } });
    expect(continuityText(ltx, null)).toMatch(/as its first keyframe/);
  });
  it("the first shot in the cut has nothing to carry on from", () => {
    const s = shot({ continuous: { mode: "latent", from: null } });
    expect(continuityBadge(s)!.label).toBe("latent (first in cut)");
    expect(continuityText(s, null)).toMatch(/first shot in the cut/);
  });
});
