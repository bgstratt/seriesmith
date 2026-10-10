import { describe, expect, it } from "vitest";
import {
  cameraLine, dialogueText, insertAfter, listOf, parseShot, replaceLines, sequenceAt, sequencesOf, shotIdBetween,
  writeShot,
} from "../src/lib/shotForm";

const SH020 = `## sh020
// keep the lantern lit
cast: riley, huey
with: backpack
size: medium
dur: 4.46
plate: street_yard
Riley runs into frame from the left and pulls up hard beside Huey.
Huey does not turn his head.
camera: arcs around behind them with small amplitude at slow speed
RILEY (breathless): There's gold at the end of the path.
HUEY (flat): There is not.
MOM (V.O.): Shoes off in the house!
RADIO (V.O., on the truck radio): And now the weather.
sound: running footsteps on grass, fabric movement
mystery: kept as it was`.split("\n");

describe("the shot form", () => {
  it("reads a shot's lines into fields", () => {
    const f = parseShot(SH020);
    expect(f.id).toBe("sh020");
    expect(f.keys.who).toBe("riley, huey");          // cast: is who:
    expect(f.keys.with).toBe("backpack");
    expect(f.keys.size).toBe("medium");
    expect(f.keys.dur).toBe("4.46");
    expect(f.keys.camera).toMatch(/^arcs around/);
    expect(f.action).toBe("Riley runs into frame from the left and pulls up hard beside Huey. Huey does not turn his head.");
    expect(f.dialogue).toEqual([
      { speaker: "RILEY", marker: "", note: "breathless", text: "There's gold at the end of the path." },
      { speaker: "HUEY", marker: "", note: "flat", text: "There is not." },
      { speaker: "MOM", marker: "V.O.", note: "", text: "Shoes off in the house!" },
      { speaker: "RADIO", marker: "V.O.", note: "on the truck radio", text: "And now the weather." },
    ]);
    expect(f.comments).toEqual(["// keep the lantern lit"]);
    expect(f.other).toEqual(["mystery: kept as it was"]);
  });

  it("writes it back in one order, keeping everything", () => {
    const back = writeShot(parseShot(SH020));
    expect(back).toEqual([
      "## sh020",
      "// keep the lantern lit",
      "who: riley, huey",
      "with: backpack",
      "size: medium",
      "dur: 4.46",
      "plate: street_yard",
      "Riley runs into frame from the left and pulls up hard beside Huey. Huey does not turn his head.",
      "camera: arcs around behind them with small amplitude at slow speed",
      "RILEY (breathless): There's gold at the end of the path.",
      "HUEY (flat): There is not.",
      "MOM (V.O.): Shoes off in the house!",
      "RADIO (V.O., on the truck radio): And now the weather.",
      "sound: running footsteps on grass, fabric movement",
      "mystery: kept as it was",
    ]);
    // and that is stable
    expect(writeShot(parseShot(back))).toEqual(back);
  });

  it("an empty field is left out; a dialogue row without words too", () => {
    const f = parseShot(["## sh010", "who: ada", "size: wide"]);
    f.keys.who = " ";
    f.dialogue.push({ speaker: "ADA", marker: "", note: "", text: "" });
    expect(writeShot(f)).toEqual(["## sh010", "size: wide"]);
    expect(dialogueText({ speaker: "ada", marker: "O.S.", note: "far off", text: "Hello?" })).toBe("ADA (O.S., far off): Hello?");
  });

  it("finds the sequences and suggests ids in the script's numbering", () => {
    const text = "= ep01  X\n\n# sq01  porch\n\n## sh010\n\n# sq02  lawn\n## sh020\n";
    const seqs = sequencesOf(text);
    expect(seqs.map((s) => [s.id, s.location, s.line])).toEqual([["sq01", "porch", 3], ["sq02", "lawn", 7]]);
    expect(sequenceAt(seqs, 5)?.id).toBe("sq01");
    expect(sequenceAt(seqs, 8)?.id).toBe("sq02");
    const taken = new Set(["sh010", "sh020"]);
    expect(shotIdBetween("sh010", "sh020", taken)).toBe("sh015");
    expect(shotIdBetween("sh020", null, taken)).toBe("sh030");
    expect(shotIdBetween(null, "sh010", taken)).toBe("sh005");
    expect(shotIdBetween(null, null, new Set())).toBe("sh010");
    expect(shotIdBetween("sh0140", "sh0150", new Set(["sh0140", "sh0150", "sh0145"]))).toBe("sh0141");
  });

  it("splices a block in place, or after a shot", () => {
    const text = "# sq01  porch\n\n## sh010\nwho: ada\n\n## sh020\nsize: wide\n";
    const replaced = replaceLines(text, 3, 5, ["## sh010", "who: ada, bo"]);
    expect(replaced).toBe("# sq01  porch\n\n## sh010\nwho: ada, bo\n\n## sh020\nsize: wide\n");
    const added = insertAfter(text, 5, ["## sh015", "size: close"]);
    expect(added).toBe("# sq01  porch\n\n## sh010\nwho: ada\n\n## sh015\nsize: close\n\n## sh020\nsize: wide\n");
    expect(insertAfter("# sq01  porch\n", 1, ["## sh010"])).toBe("# sq01  porch\n\n## sh010\n");
  });

  it("builds a camera line from H3's vocabulary", () => {
    expect(cameraLine("pushes in", "", "at slow speed")).toBe("pushes in at slow speed");
    expect(listOf(" ada, bo ,")).toEqual(["ada", "bo"]);
  });
});
