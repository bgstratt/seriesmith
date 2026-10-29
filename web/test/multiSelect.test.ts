// Several shots selected: Ctrl/⌘-click adds or takes one out, Shift-click a range
// in the cut's order, a plain click goes back to one (lib/multiSelect).
import { describe, expect, it } from "vitest";
import { clickSelection, selectedShots, type Selection } from "../src/lib/multiSelect";

const order = ["sh010", "sh020", "sh030", "sh040", "sh050"];
const one = (shot: string): Selection => ({ shot, multi: [], anchor: shot });

describe("selecting several shots", () => {
  it("a plain click selects one", () => {
    const s = clickSelection({ shot: "sh010", multi: ["sh010", "sh020"], anchor: "sh010" }, "sh040", order, {});
    expect(s).toEqual({ shot: "sh040", multi: [], anchor: "sh040" });
    expect(selectedShots(s)).toEqual(["sh040"]);
  });

  it("Ctrl adds to the selected shot, in the cut's order, and the inspector follows", () => {
    let s = clickSelection(one("sh040"), "sh010", order, { ctrlKey: true });
    expect(s).toEqual({ shot: "sh010", multi: ["sh010", "sh040"], anchor: "sh010" });
    s = clickSelection(s, "sh020", order, { metaKey: true });
    expect(s.multi).toEqual(["sh010", "sh020", "sh040"]);
  });

  it("Ctrl on a selected shot takes it out; down to one is no selection of several", () => {
    let s: Selection = { shot: "sh020", multi: ["sh010", "sh020", "sh040"], anchor: "sh020" };
    s = clickSelection(s, "sh020", order, { ctrlKey: true });
    expect(s).toEqual({ shot: "sh010", multi: ["sh010", "sh040"], anchor: "sh020" });
    s = clickSelection(s, "sh040", order, { ctrlKey: true });
    expect(s).toEqual({ shot: "sh010", multi: [], anchor: "sh040" });
  });

  it("Shift takes the range from the last click, either way, and keeps its start", () => {
    let s = clickSelection(one("sh020"), "sh040", order, { shiftKey: true });
    expect(s).toEqual({ shot: "sh040", multi: ["sh020", "sh030", "sh040"], anchor: "sh020" });
    s = clickSelection(s, "sh010", order, { shiftKey: true });
    expect(s.multi).toEqual(["sh010", "sh020"]);
  });

  it("Shift with nothing selected, or on a shot not in the cut, is a plain click", () => {
    expect(clickSelection({ shot: null, multi: [], anchor: null }, "sh030", order, { shiftKey: true }))
      .toEqual({ shot: "sh030", multi: [], anchor: "sh030" });
    expect(clickSelection(one("sh010"), "orphan", order, { shiftKey: true }).multi).toEqual([]);
  });
});
