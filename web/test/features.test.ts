// The Features window's helpers (src/lib/features.ts): what a choice still downloads,
// each shared file once, and how its items and sizes read.
import { describe, expect, it } from "vitest";
import { downloadSize, fmtBytes, itemsLine, toInstall, type Feature, type FeatureItem } from "../src/lib/features";

const item = (over: Partial<FeatureItem>): FeatureItem => ({
  key: over.key ?? `model:${over.name}`, kind: "model", name: "x", status: "missing", ...over,
});

const feature = (id: string, items: FeatureItem[]): Feature => ({
  id, group: "upscale", label: id, about: "", items, restart: false, status: "missing",
});

describe("features", () => {
  const vae = item({ key: "model:vae/v", name: "v", url: "https://h/v" });
  const big = item({ key: "model:dm/7b", name: "7b", url: "https://h/7b" });
  const small = item({ key: "model:dm/3b", name: "3b", url: "https://h/3b" });

  it("counts a file two features share once, and leaves out what's installed", () => {
    const seven = feature("7b", [vae, big]);
    const three = feature("3b", [vae, { ...small, status: "installed" }]);
    const sizes = { "https://h/v": 100, "https://h/7b": 7000, "https://h/3b": 3000 };
    expect(downloadSize([seven, three], sizes)).toEqual({ bytes: 7100, unknown: 0 });
    expect(toInstall(three).map((i) => i.name)).toEqual(["v"]);
  });

  it("says how many sizes it doesn't know", () => {
    expect(downloadSize([feature("7b", [vae, big])], { "https://h/v": 100 })).toEqual({ bytes: 100, unknown: 1 });
  });

  it("describes a feature's items by kind", () => {
    const f = feature("vsr", [item({ kind: "pack", name: "RTX", key: "pack:RTX" }), item({ kind: "pip", name: "nvidia-vfx", key: "pip:nvidia-vfx" })]);
    expect(itemsLine(f)).toBe("1 node pack · 1 Python package");
    expect(itemsLine(feature("e", [vae, big]))).toBe("2 files");
  });

  it("writes sizes for people", () => {
    expect(fmtBytes(21_106_607)).toBe("21 MB");
    expect(fmtBytes(6_938_078_334)).toBe("6.9 GB");
    expect(fmtBytes(32_000_000_000)).toBe("32 GB");
  });
});
