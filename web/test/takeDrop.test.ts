// Takes from outside (lib/takeDrop.ts): what a gallery take's drag carries, where
// a drop on the timeline lands (onto a clip or between two), and the script with
// a new shot inserted for a take dropped between clips. Plus the mock API's
// import and copy, as the editor calls them.
import { describe, expect, it } from "vitest";
import {
  anchorAt, decodeTakeDrag, dropAt, durOf, encodeTakeDrag, gapAfter, insertedShot, videoFileProblem,
} from "../src/lib/takeDrop";
import { createMockApi } from "../src/mock/mockApi";

const SCRIPT = `= ep01  Test

# sq01  porch

## sh010
who: ada
size: wide
dur: 3
Ada steps out.

## sh020
// the lantern
who: ada
with: lantern
size: medium
dur: 4
continuous: first
Ada lifts the lantern.
ADA: There it is.
sound: a hook

# sq02  lawn

## sh030
who: ada
size: close
dur: auto
Ada grins.
`;

function spans(text: string) {
  const lines = text.split("\n");
  const heads = lines.flatMap((l, i) => (l.startsWith("## ") ? [i + 1] : []));
  const seqs = lines.flatMap((l, i) => (/^# /.test(l) ? [i + 1] : []));
  return heads.map((line, k) => {
    const next = Math.min(heads[k + 1] ?? lines.length + 1, ...seqs.filter((s) => s > line));
    let end = next - 1;
    while (end > line && !lines[end - 1].trim()) end--;
    return { id: lines[line - 1].slice(3).trim(), line, end_line: end };
  });
}

describe("a take's drag", () => {
  it("round-trips, and refuses what isn't one", () => {
    const t = { ep: "C:/S/ep01", pass: "proxy" as const, shot: "sh020", take: 3, seconds: 4.2 };
    expect(decodeTakeDrag(encodeTakeDrag(t))).toEqual(t);
    expect(decodeTakeDrag("{}")).toBeNull();
    expect(decodeTakeDrag("not json")).toBeNull();
    expect(decodeTakeDrag(JSON.stringify({ ...t, pass: "draft" }))).toBeNull();
  });
});

describe("where a drop lands", () => {
  const edges = [{ left: 0, right: 100 }, { left: 104, right: 204 }, { left: 208, right: 228 }];
  it("onto a clip's middle", () => {
    expect(dropAt(edges, 50)).toEqual({ kind: "onto", index: 0 });
    expect(dropAt(edges, 150)).toEqual({ kind: "onto", index: 1 });
    expect(dropAt(edges, 218)).toEqual({ kind: "onto", index: 2 });   // a short clip: a quarter each side
  });
  it("between two near their edges, or past either end", () => {
    expect(dropAt(edges, 98)).toEqual({ kind: "between", gap: 1, x: 102 });
    expect(dropAt(edges, 106)).toEqual({ kind: "between", gap: 1, x: 102 });
    expect(dropAt(edges, 2)).toEqual({ kind: "between", gap: 0, x: 0 });
    expect(dropAt(edges, 400)).toEqual({ kind: "between", gap: 3, x: 228 });
    expect(dropAt([], 10)).toEqual({ kind: "between", gap: 0, x: 10 });
  });
});

describe("the new shot's place", () => {
  const cut = [{ shot: "sh020" }, { shot: "sh099", orphan: true }, { shot: "sh010" }, { shot: "sh030" }];
  it("after the script shot left of the gap, skipping orphans; else before the next", () => {
    expect(anchorAt(cut, 1)).toEqual({ after: "sh020" });
    expect(anchorAt(cut, 2)).toEqual({ after: "sh020" });
    expect(anchorAt(cut, 3)).toEqual({ after: "sh010" });
    expect(anchorAt(cut, 0)).toEqual({ before: "sh020" });
    expect(anchorAt([{ shot: "x", orphan: true }], 0)).toBeNull();
  });
  it("in the cut: right after the left neighbour, else first", () => {
    expect(gapAfter(cut, "sh010")).toBe(3);
    expect(gapAfter(cut, null)).toBe(0);
  });
});

describe("the script with a dropped take's shot", () => {
  it("copies the take's shot after the anchor: its lines, the take's length, no continuity", () => {
    const got = insertedShot(SCRIPT, spans(SCRIPT), "sh020", { after: "sh010" }, 4.26, "sh020 t03, dropped on the timeline")!;
    expect(got.id).toBe("sh015");
    const lines = got.text.split("\n");
    const at = lines.indexOf("## sh015");
    expect(lines.slice(at - 2, at)).toEqual(["Ada steps out.", ""]);
    const block = lines.slice(at, lines.indexOf("## sh020"));
    expect(block).toContain("// sh020 t03, dropped on the timeline");
    expect(block).toContain("with: lantern");
    expect(block).toContain("dur: 4.3");
    expect(block).toContain("ADA: There it is.");
    expect(block.some((l) => l.startsWith("continuous"))).toBe(false);
    // the rest of the script as it was
    expect(got.text.replace(block.join("\n") + "\n", "")).toBe(SCRIPT);
  });
  it("before the first shot of a sequence, inside it", () => {
    const got = insertedShot(SCRIPT, spans(SCRIPT), "sh010", { before: "sh030" }, 2, "x")!;
    expect(got.id).toBe("sh025");
    const lines = got.text.split("\n");
    expect(lines.indexOf("## sh025")).toBeGreaterThan(lines.indexOf("# sq02  lawn"));
    expect(lines.indexOf("## sh025")).toBeLessThan(lines.indexOf("## sh030"));
  });
  it("a held frame: its action instead, no dialogue, nothing that moves or sounds", () => {
    const got = insertedShot(SCRIPT, spans(SCRIPT), "sh020", { after: "sh020" }, 2, "frame 40 of sh020 t03, held",
      "A still: frame 40 of sh020 t03, held.")!;
    const lines = got.text.split("\n");
    const at = lines.indexOf(`## ${got.id}`);
    const block = lines.slice(at);
    expect(block).toContain("A still: frame 40 of sh020 t03, held.");
    expect(block).toContain("dur: 2");
    expect(block.some((l) => l.startsWith("ADA:"))).toBe(false);
    expect(block.some((l) => l.startsWith("Ada lifts") || l.startsWith("sound:"))).toBe(false);
    expect(block).toContain("with: lantern");
  });
  it("after the last shot", () => {
    expect(insertedShot(SCRIPT, spans(SCRIPT), "sh010", { after: "sh030" }, 2, "x")!.id).toBe("sh040");
  });
  it("nothing for a shot that isn't there", () => {
    expect(insertedShot(SCRIPT, spans(SCRIPT), "sh999", { after: "sh010" }, 2, "x")).toBeNull();
    expect(insertedShot(SCRIPT, spans(SCRIPT), "sh010", { after: "sh999" }, 2, "x")).toBeNull();
  });
  it("a dur of one decimal", () => {
    expect(durOf(4.04)).toBe("4");
    expect(durOf(0.01)).toBe("0.1");
  });
});

describe("a file that can be a take", () => {
  it("is a video under the limit", () => {
    expect(videoFileProblem({ name: "a.MOV", size: 10 })).toBe("");
    expect(videoFileProblem({ name: "a.png", size: 10 })).toMatch(/isn't a video/);
    expect(videoFileProblem({ name: "a.mp4", size: 5 * 1024 ** 3 })).toMatch(/over 4 GB/);
  });
});

describe("the mock's import and copy", () => {
  it("adds a picked, never-stale take that says where it came from", async () => {
    const api = createMockApi(() => {});
    const eps = await api.episodes();
    const ep = eps[0].ep;
    const st = await api.episode(ep, "proxy");
    const [a, b] = st.shots;
    const up = await api.uploadTake({ ep, pass: "proxy", shot: a.shot, file: new Blob(["x"]), name: "phone.mov", pick: true });
    expect(up.picked).toBe(true);
    const done = await api.episode(ep, "proxy");
    const t = done.shots.find((s) => s.shot === a.shot)!.takes.find((x) => x.take === up.take)!;
    expect([t.source, t.original_name, t.stale]).toEqual(["imported", "phone.mov", []]);
    expect(done.shots.find((s) => s.shot === a.shot)!.cut.take).toBe(up.take);
    const c = await api.copyTake({ ep, pass: "proxy", shot: b.shot, from_shot: a.shot, take: up.take, pick: true });
    const t2 = (await api.episode(ep, "proxy")).shots.find((s) => s.shot === b.shot)!.takes.find((x) => x.take === c.take)!;
    expect(t2.copied_from).toEqual({ shot: a.shot, take: up.take, pass: "proxy" });
    await expect(api.copyTake({ ep, pass: "proxy", shot: a.shot, from_shot: a.shot, take: up.take })).rejects.toThrow(/pick it instead/);
  });
});
