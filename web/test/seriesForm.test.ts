import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  DEFAULT_PROXY, SECTIONS, getPath, newSeries, parsed, same, serialize, setPath, setSize, shown, sizeOf, slug,
} from "../src/lib/seriesForm";

describe("series settings form", () => {
  const raw = { series: { id: "x", title: "X", fps: 24, width: 1344, height: 768 }, _note: "kept",
    proxy: { width: 448, height: 256 }, subjects: { ada: { kind: "character" } } };

  it("sets a path without touching anything else, keeping key order", () => {
    const out = setPath(raw, ["series", "title"], "First Light");
    expect(Object.keys(out)).toEqual(Object.keys(raw));
    expect(Object.keys(out.series as object)).toEqual(["id", "title", "fps", "width", "height"]);
    expect(getPath(out, ["series", "title"])).toBe("First Light");
    expect(raw.series.title).toBe("X");                 // a copy
    expect(out._note).toBe("kept");
    expect(out.subjects).toBe(raw.subjects);              // untouched blocks are shared, not rebuilt
  });

  it("a new key goes at the end of its block, a new block at the end of the file", () => {
    const out = setPath(raw, ["refs", "target"], "krea2");
    expect(Object.keys(out).pop()).toBe("refs");
    expect(Object.keys(setPath(raw, ["series", "steps"], 8).series as object).pop()).toBe("steps");
  });

  it("clearing a field removes the key, and a block it leaves empty", () => {
    const one = setPath(raw, ["style", "look"], "film");
    expect(getPath(one, ["style", "look"])).toBe("film");
    const cleared = setPath(one, ["style", "look"], "  ");
    expect("style" in cleared).toBe(false);
    expect(setPath(raw, ["series", "fps"], undefined).series).not.toHaveProperty("fps");
  });

  it("sizes go in as numbers and come out as WxH", () => {
    const out = setSize(raw, "proxy", "864x480");
    expect(out.proxy).toEqual({ width: 864, height: 480 });
    expect(sizeOf(out, "proxy")).toBe("864x480");
    expect("proxy" in setSize(raw, "proxy", "")).toBe(false);
  });

  it("numbers are stored as numbers, an empty number field clears", () => {
    const f = SECTIONS[0].fields.find((x) => x.path.join(".") === "series.fps")!;
    expect(parsed(f, "25")).toBe(25);
    expect(parsed(f, "")).toBeUndefined();
    expect(shown(raw, f)).toBe("24");
  });

  it("slugs a title into an id", () => {
    expect(slug("Porchlights: Season Two!")).toBe("porchlights_season_two");
    expect(slug("Café Noir")).toBe("cafe_noir");
  });

  it("writes the file exactly as the server does (source.dump_series)", () => {
    // series_example.json is already in the server's layout: parsing and writing it back changes nothing
    const text = readFileSync(new URL("../../examples/series_example.json", import.meta.url), "utf8").replace(/\r\n/g, "\n");
    expect(serialize(JSON.parse(text), text)).toBe(text);
    expect(same(JSON.parse(text), JSON.parse(text))).toBe(true);
  });

  it("a new series starts from the starter's settings with a 480p proxy", () => {
    const s = newSeries("First Light");
    expect(getPath(s, ["series", "id"])).toBe("first_light");
    expect(sizeOf(s, "series")).toBe("1344x768");
    expect(sizeOf(s, "proxy")).toBe(DEFAULT_PROXY);
    expect(DEFAULT_PROXY).toBe("864x480");
  });

  it("every field has a label and help, and paths are unique", () => {
    const paths = SECTIONS.flatMap((s) => s.fields.map((f) => f.path.join(".")));
    expect(new Set(paths).size).toBe(paths.length);
    for (const s of SECTIONS) for (const f of s.fields) {
      expect(f.label).toBeTruthy();
      expect(f.help.length).toBeGreaterThan(20);
    }
  });
});

describe("proxy shape", () => {
  it("says when the proxy isn't the final's shape", async () => {
    const { shapeNote } = await import("../src/lib/seriesForm");
    expect(shapeNote("1344x768", "896x512")).toBeNull();
    expect(shapeNote("1344x768", "864x480")).toMatch(/different shape/);
    expect(shapeNote("1344x768", "672x384")).toBeNull();
    expect(shapeNote("1344x768", "")).toBeNull();
  });
});

describe("the master recipe's per-model sections", () => {
  it("are written with a size, when there are none", async () => {
    const { MASTER_TARGETS, masterLacksTargets, withMasterTargets } = await import("../src/lib/seriesForm");
    const bare = { upscale: { master: { deliver: "1440p", quality: "master" } } };
    expect(masterLacksTargets(bare)).toBe(true);
    const full = withMasterTargets(bare) as { upscale: { master: Record<string, unknown> } };
    expect(full.upscale.master.targets).toEqual(MASTER_TARGETS);
    expect(full.upscale.master.finish).toEqual({ frequency_split: true });
    expect(full.upscale.master.deliver).toBe("1440p");
    expect(masterLacksTargets(full)).toBe(false);
    // its own sections are never replaced
    const own = { upscale: { master: { deliver: "4k", targets: { "*": { method: "pixel" } } } } };
    expect(withMasterTargets(own)).toBe(own);
    expect(masterLacksTargets({})).toBe(false);
  });
});
