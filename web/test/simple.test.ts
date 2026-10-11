import { describe, expect, it } from "vitest";
import { clipBlock, nextClipIds, placeFor, shotsBlock, withClip, type ClipSpec } from "../src/lib/simple";

const spec = (p: Partial<ClipSpec> = {}): ClipSpec => ({
  prompt: "A lighthouse at dusk, waves breaking on the rocks.", who: [], where: "", placeText: "",
  size: "wide", dur: "3.04", target: "", dialogue: [], ...p,
});

describe("simple mode's clips", () => {
  it("numbers clips after the ones there", () => {
    expect(nextClipIds("= clips  Clips\n")).toEqual({ seq: "cl001", shot: "c001", n: 1 });
    expect(nextClipIds("= clips  Clips\n\n# cl001  pier\n\n## c001\n\n# cl012  x\n## c012\n").shot).toBe("c013");
  });

  it("gives a clip without a place one of its own, from words or the prompt", () => {
    // words only by default: it renders at once
    expect(placeFor("c004", spec(), "../refs/")).toEqual({
      id: "c004_place", entry: { description: "A lighthouse at dusk, waves breaking on the rocks." },
    });
    // with a picture made first
    expect(placeFor("c004", spec(), "../refs/", true).entry.plate).toBe("../refs/_bg/c004_place.png");
    expect(placeFor("c004", spec({ placeText: "a rocky headland" }), "../refs/").entry.description).toBe("a rocky headland");
  });

  it("writes a clip as a sequence of one shot, naming its model only when it isn't the series'", () => {
    const block = clipBlock("cl002", "c002", "pier", spec({ who: ["nell"], target: "ltx2",
      dialogue: [{ speaker: "NELL", marker: "", note: "", text: "Here it comes." }] }), "minimax_h3_ref2va");
    expect(block).toEqual([
      "# cl002  pier", "", "## c002", "who: nell", "size: wide", "dur: 3.04", "target: ltx2",
      "A lighthouse at dusk, waves breaking on the rocks.", "NELL: Here it comes.",
    ]);
    expect(clipBlock("cl002", "c002", "pier", spec({ target: "minimax_h3_ref2va" }), "minimax_h3_ref2va"))
      .not.toContain("target: minimax_h3_ref2va");
    expect(withClip("= clips  Clips\n", ["# cl001  x", "", "## c001"])).toBe("= clips  Clips\n\n# cl001  x\n\n## c001\n");
  });

  it("writes a picture clip as a shot whose first keyframe is made", () => {
    expect(clipBlock("cl003", "c003", "pond", spec({ still: true, target: "krea2" }), "minimax_h3_ref2va")).toEqual([
      "# cl003  pond", "", "## c003", "// a picture", "size: wide", "dur: 3.04", "first: generate",
      "A lighthouse at dusk, waves breaking on the rocks.",
    ]);
  });

  it("writes several shots as one sequence, in order", () => {
    const { ids, lines } = shotsBlock("cl004", "c004", "pier", [spec({ prompt: "Wide on the pier." }),
      spec({ prompt: "Close on her hands.", size: "cu" })], "minimax_h3_ref2va");
    expect(ids).toEqual(["c004a", "c004b"]);
    expect(lines).toEqual(["# cl004  pier", "", "## c004a", "size: wide", "dur: 3.04", "Wide on the pier.",
      "", "## c004b", "size: cu", "dur: 3.04", "Close on her hands."]);
  });
});
