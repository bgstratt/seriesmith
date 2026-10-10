import { describe, expect, it } from "vitest";
import { isScript, pairFiles } from "../src/lib/importSeries";

const script = (id: string) => `= ${id}  A title\n\n## sq01 — somewhere\n`;
const cfg = (n = 1) => JSON.stringify({ series: { id: "show", title: "Show" }, n });

describe("pairFiles", () => {
  it("shares one config among loose scripts", () => {
    const p = pairFiles([
      { path: "series.json", text: cfg() },
      { path: "ep01.md", text: script("ep01") },
      { path: "ep02.md", text: script("ep02") },
    ]);
    expect(p.problems).toEqual([]);
    expect(p.shared?.path).toBe("series.json");
    expect(p.scripts.map((s) => [s.script.path, s.config])).toEqual([["ep01.md", null], ["ep02.md", null]]);
  });

  it("pairs each episode folder's own config (a season's folder picked)", () => {
    const p = pairFiles([
      { path: "S2/s2ep01/series.json", text: cfg(1) },
      { path: "S2/s2ep01/s2ep01.md", text: script("s2ep01") },
      { path: "S2/s2ep01/refs_todo.md", text: "# Asset work order\n" },
      { path: "S2/s2ep02/series.json", text: cfg(2) },
      { path: "S2/s2ep02/s2ep02.md", text: script("s2ep02") },
      { path: "S2/CAST.md", text: "# Cast\n" },
    ]);
    expect(p.problems).toEqual([]);
    expect(p.shared).toBeNull();
    expect(p.scripts.map((s) => [s.script.path, s.config?.path])).toEqual([
      ["S2/s2ep01/s2ep01.md", "S2/s2ep01/series.json"],
      ["S2/s2ep02/s2ep02.md", "S2/s2ep02/series.json"],
    ]);
    expect(p.notScripts).toEqual(["S2/s2ep01/refs_todo.md", "S2/CAST.md"]);
  });

  it("pairs a config named for its script, and shares the rest", () => {
    const p = pairFiles([
      { path: "series.json", text: cfg(1) },
      { path: "ep02.json", text: cfg(2) },
      { path: "ep01.md", text: script("ep01") },
      { path: "ep02.md", text: script("ep02") },
    ]);
    expect(p.scripts.map((s) => s.config?.path ?? null)).toEqual([null, "ep02.json"]);
    expect(p.shared?.path).toBe("series.json");
  });

  it("says what is missing or unclear", () => {
    expect(pairFiles([{ path: "ep01.md", text: script("ep01") }]).problems[0]).toMatch(/no series config/);
    expect(pairFiles([{ path: "a.json", text: cfg() }, { path: "b.json", text: cfg() },
                      { path: "ep01.md", text: script("ep01") }]).problems[0]).toMatch(/aren't any one episode's/);
    expect(pairFiles([{ path: "notes.md", text: "hello" }]).problems).toContain(
      "no scripts: a script is a .md whose first line is its header, like `= ep01  Title`");
  });

  it("knows a script by its header", () => {
    expect(isScript("\n\n= ep05  Title\n")).toBe(true);
    expect(isScript("# Notes\n= ep05")).toBe(false);
  });
});
