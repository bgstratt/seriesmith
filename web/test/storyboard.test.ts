import { describe, expect, it } from "vitest";
import { blockedScript } from "../src/lib/wizard";
import { bandShare, bareBeats, clock, dropSide, dropTargets, heldIds, shotBefore, toGenerate, fillable, fillCount, heldToRender, meter, picturesInOrder, placeOf, positive, pushed, runtimeMinutes, runWidth, seriesChoices, UNDO_STEPS, type BoardBeat } from "../src/lib/storyboard";

function beat(over: Partial<BoardBeat>): BoardBeat {
  return { beat: "A", plain: "A", nth: 0, block: null, known: true, in_script: true, guidance: "", shots: 0, seconds: 0,
    target_shots: null, target_seconds: null, thin: false, runs: [], ...over };
}

describe("clock", () => {
  it("writes minutes and seconds", () => {
    expect(clock(0)).toBe("0:00");
    expect(clock(65)).toBe("1:05");
    expect(clock(1320)).toBe("22:00");
  });

  it("writes hours from an hour", () => {
    expect(clock(6000)).toBe("1:40:00");
    expect(clock(3723)).toBe("1:02:03");
  });
});

describe("positive", () => {
  it("reads a number above zero", () => {
    expect(positive("7")).toBe(7);
    expect(positive(" 3.5 ")).toBe(3.5);
  });

  it("is null for anything else", () => {
    for (const text of ["", "  ", "0", "-2", "abc", "Infinity"]) expect(positive(text)).toBeNull();
  });
});

describe("placeOf", () => {
  it("writes a span and a point", () => {
    expect(placeOf({ at: [10, 12] })).toBe("10–12%");
    expect(placeOf({ point: 50 })).toBe("at 50%");
  });

  it("is empty for a beat with no place", () => {
    expect(placeOf({})).toBe("");
  });
});

describe("meter", () => {
  it("shows what's there against the target and the time to go", () => {
    expect(meter(beat({ shots: 3, seconds: 10, target_shots: 93, target_seconds: 325 }))).toBe("3 of 93 shots, about 5:15 to go");
  });

  it("drops the time once it's met", () => {
    expect(meter(beat({ shots: 5, seconds: 20, target_shots: 5, target_seconds: 18 }))).toBe("5 of 5 shots");
  });

  it("just counts a beat with no target", () => {
    expect(meter(beat({ shots: 1 }))).toBe("1 shot");
    expect(meter(beat({ shots: 4 }))).toBe("4 shots");
  });
});

describe("fill", () => {
  const beats = [
    beat({ plain: "A", shots: 2, target_shots: 5 }),
    beat({ plain: "B", nth: 1, shots: 6, target_shots: 5 }),
    beat({ plain: null, shots: 3, target_shots: null }),
    beat({ plain: "C", shots: 0, target_shots: null }),
    beat({ plain: "D", nth: 1, shots: 0, target_shots: 4 }),
  ];

  it("counts only what's missing", () => {
    expect(fillCount(beats)).toBe(3 + 4);
  });

  it("names only the beats with something to do", () => {
    expect(fillable(beats)).toEqual([{ plain: "A", nth: 0 }, { plain: "D", nth: 1 }]);
  });
});

describe("runtimeMinutes", () => {
  it("counts untimed shots as typical ones", () => {
    expect(runtimeMinutes(600, 60, 5)).toBe("15");
  });

  it("never comes to nothing", () => {
    expect(runtimeMinutes(0, 0, 3.5)).toBe("0.1");
  });
});

describe("frames", () => {
  const file = (name: string, type = "image/png") => ({ name, type });

  it("takes pictures in filename order, numbers as numbers", () => {
    const out = picturesInOrder([file("f10.png"), file("f2.png"), file("notes.txt", "text/plain"), file("f1.jpg", "image/jpeg")]);
    expect(out.map((f) => f.name)).toEqual(["f1.jpg", "f2.png", "f10.png"]);
  });

  const shots = [
    { id: "a", target: "hold", held_empty: true, picture: null, card: true },
    { id: "b", target: "hold", held_empty: false, picture: "x.png", card: false },
    { id: "c", target: null, held_empty: false, picture: null, card: false },
    { id: "d", target: "hold", held_empty: true, picture: null, card: false },
  ];

  it("fills only empty stand-ins from a sequence or a beat", () => {
    expect(dropTargets(shots, false).map((s) => s.id)).toEqual(["a", "d"]);
  });

  it("lets a single tile take a picture whatever model it's on", () => {
    expect(dropTargets([shots[1]], true).map((s) => s.id)).toEqual(["b"]);
    expect(dropTargets([shots[2]], true).map((s) => s.id)).toEqual(["c"]);
  });

  it("renders held shots on a picture or the gray card, unless their take is up to date", () => {
    expect(heldToRender(shots, new Set())).toEqual(["a", "b"]);
    expect(heldToRender(shots, new Set(["a", "b"]))).toEqual([]);
  });
});

describe("dropSide", () => {
  it("sends a moved shot to the nearer side", () => {
    expect(dropSide(0.4, true)).toBe("before");
    expect(dropSide(0.6, true)).toBe("after");
  });

  it("makes a file a tile's picture, except near an edge", () => {
    expect(dropSide(0.5, false)).toBeNull();
    expect(dropSide(0.1, false)).toBe("before");
    expect(dropSide(0.9, false)).toBe("after");
  });
});

describe("shotBefore", () => {
  const order = ["a", "b", "c"];

  it("is the target when landing after it", () => {
    expect(shotBefore(order, "b", "after")).toBe("b");
  });

  it("is the one before the target when landing before it", () => {
    expect(shotBefore(order, "b", "before")).toBe("a");
    expect(shotBefore(order, "a", "before")).toBeNull();
  });

  it("doesn't count the shot being moved", () => {
    expect(shotBefore(order, "c", "before", "b")).toBe("a");
    expect(shotBefore(order, "b", "after", "b")).toBeNull();
  });
});

describe("toGenerate", () => {
  it("leaves out shots with an up-to-date take", () => {
    expect(toGenerate([{ id: "a" }, { id: "b" }], new Set(["a"]))).toEqual(["b"]);
  });
});

describe("heldIds", () => {
  it("names only the held shots", () => {
    expect(heldIds([{ id: "a", target: "hold" }, { id: "b", target: "ltx2" }, { id: "c", target: null }])).toEqual(["a"]);
  });
});

describe("pushed", () => {
  it("adds on top", () => {
    expect(pushed(["a"], "b")).toEqual(["a", "b"]);
  });

  it("drops the oldest past the limit", () => {
    const full = Array.from({ length: UNDO_STEPS }, (_, i) => String(i));
    const out = pushed(full, "new");
    expect(out).toHaveLength(UNDO_STEPS);
    expect(out[0]).toBe("1");
    expect(out[out.length - 1]).toBe("new");
  });
});

describe("bareBeats", () => {
  it("names only the beats with no shot yet", () => {
    const beats = [beat({ plain: "A", shots: 1 }), beat({ plain: "B", nth: 1 }), beat({ plain: null })];
    expect(bareBeats(beats)).toEqual([{ plain: "B", nth: 1 }]);
  });
});

describe("runWidth", () => {
  it("is its shots in a line, no wider than the row", () => {
    expect(runWidth(10)).toBe("min(100%, 507px)");
  });

  it("leaves a one-shot sequence room for its name", () => {
    expect(runWidth(1)).toBe("min(100%, 96px)");
  });
});

describe("bandShare", () => {
  it("is the beat's share of the biggest, and never too narrow to read", () => {
    expect(bandShare(50, 100)).toBe("max(220px, 50%)");
  });

  it("is the whole row with no target", () => {
    expect(bandShare(null, 100)).toBe("100%");
    expect(bandShare(5, 0)).toBe("100%");
  });
});

describe("seriesChoices", () => {
  const text = JSON.stringify({
    subjects: { _note: "a note", june: { kind: "character", name: "June" }, lantern: { kind: "prop" }, car: { kind: "vehicle" }, ada: {} },
    locations: { _note: "a note", diner: {}, street_gate: {} },
  });

  it("offers the locations", () => {
    expect(seriesChoices(text).places).toEqual(["diner", "street_gate"]);
  });

  it("leaves props, vehicles and notes out of the cast", () => {
    expect(seriesChoices(text).cast).toEqual([{ id: "june", name: "June" }, { id: "ada", name: "ada" }]);
  });

  it("copes with a series that has neither", () => {
    expect(seriesChoices("{}")).toEqual({ places: [], cast: [] });
  });
});

describe("blockedScript", () => {
  it("is a title, a structure and a length, and no shots", () => {
    expect(blockedScript("ep03", "The Long Way", "Three-Act", 420)).toBe("= ep03  The Long Way\n\n// structure: Three-Act\n// duration: 7:00\n");
  });

  it("writes hours and copes with no title", () => {
    expect(blockedScript("ep03", "", "Fable", 3723)).toBe("= ep03\n\n// structure: Fable\n// duration: 1:02:03\n");
  });
});
