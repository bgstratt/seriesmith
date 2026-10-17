import { describe, expect, it } from "vitest";
import { clipBlock, durFor, nextClipIds, placeFor, shotsBlock, snapLength, withClip, type ClipSpec } from "../src/lib/simple";
import { fitSize } from "../src/lib/size";

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

describe("simple mode's length and size", () => {
  const H3 = { fps: 24, frames: { step: 17, base: 5, max: 3592 }, size_multiple: 32 };
  const SEEDANCE = { fps: 24, frames: { step: 24, base: 96, max: 720 }, size_multiple: 2, size_fit: "snap",
                     max_size: { long_side: 1920 } };
  it("a typed length rounds up onto the model's grid", () => {
    expect(snapLength("5", H3)).toEqual({ seconds: 5.17, frames: 124, capped: false });
    expect(snapLength("3.04", H3)?.frames).toBe(73);
    expect(snapLength("5", SEEDANCE)).toEqual({ seconds: 5, frames: 120, capped: false });
    expect(snapLength("4.2", SEEDANCE)?.seconds).toBe(5);
    expect(snapLength("2", SEEDANCE)?.seconds).toBe(4);              // its shortest
    expect(snapLength("", H3)).toBeNull();
    expect(snapLength("auto", H3)).toBeNull();
  });
  it("past the model's longest it is capped, and that is what the script says", () => {
    expect(snapLength("45", SEEDANCE)).toEqual({ seconds: 30, frames: 720, capped: true });
    expect(durFor("45", SEEDANCE)).toBe("30");
    expect(durFor(" 5 ", SEEDANCE)).toBe("5");
    expect(durFor("auto", H3)).toBe("auto");
  });
  it("a size is made one the model takes", () => {
    expect(fitSize(1280, 720, H3)).toEqual([1280, 704]);
    expect(fitSize(1920, 1080, SEEDANCE)).toEqual([1920, 1080]);
    expect(fitSize(3840, 2160, SEEDANCE)).toEqual([1920, 1080]);
    expect(fitSize(1000, 1000, { sizes: [[1280, 720], [720, 1280], [960, 960]] })).toEqual([960, 960]);
  });
});

describe("a supplied character picture", () => {
  it("is one whole picture unless shaped like a sheet of panels", async () => {
    const { isOnePicture } = await import("../src/components/SubjectCard");
    expect(isOnePicture(1328, 1760)).toBe(true);      // a portrait (Ballroom's Cindy)
    expect(isOnePicture(1920, 1080)).toBe(true);      // a wide photo is still one picture
    expect(isOnePicture(4096, 1024)).toBe(false);     // four panels side by side (Red)
    expect(isOnePicture(null, null)).toBe(true);      // size unknown: as before
  });
});
