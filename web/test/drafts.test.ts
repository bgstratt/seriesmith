// Unsaved edits kept in this browser (lib/drafts), the inspector's detail kept on
// screen through a refresh (keepDetails), and the check before Export (lib/exportCheck).
import { beforeEach, describe, expect, it } from "vitest";
import { clearDraft, pruneDrafts, readDraft, writeDraft } from "../src/lib/drafts";
import { blocks, exportCheck, shotList } from "../src/lib/exportCheck";
import { keepDetails } from "../src/store";
import type { EpisodeStatus, ShotStatus, TakeRef } from "../src/types";

class MemStorage {
  private m = new Map<string, string>();
  get length() { return this.m.size; }
  key(i: number) { return [...this.m.keys()][i] ?? null; }
  getItem(k: string) { return this.m.get(k) ?? null; }
  setItem(k: string, v: string) { this.m.set(k, String(v)); }
  removeItem(k: string) { this.m.delete(k); }
  clear() { this.m.clear(); }
}

describe("drafts", () => {
  beforeEach(() => {
    (globalThis as { localStorage?: unknown }).localStorage = new MemStorage();
  });

  it("keeps a draft and its time, and clears it", () => {
    writeDraft("shot|C:/show/ep03|final|sh130", { prompt: "mine" }, 1000);
    expect(readDraft("shot|C:/show/ep03|final|sh130")).toEqual({ value: { prompt: "mine" }, at: 1000 });
    expect(readDraft("shot|C:/show/ep03|proxy|sh130")).toBeNull();
    clearDraft("shot|C:/show/ep03|final|sh130");
    expect(readDraft("shot|C:/show/ep03|final|sh130")).toBeNull();
  });

  it("drops drafts a month old, and anything unreadable; nothing else of the page's", () => {
    const day = 24 * 3600 * 1000;
    const now = 100 * day;
    writeDraft("old", { a: 1 }, now - 31 * day);
    writeDraft("new", { a: 2 }, now - day);
    localStorage.setItem("seriesmith.draft.junk", "{not json");
    localStorage.setItem("seriesmith.zoom", "3");
    pruneDrafts(now);
    expect(readDraft("old")).toBeNull();
    expect(readDraft("new")?.value).toEqual({ a: 2 });
    expect(localStorage.getItem("seriesmith.draft.junk")).toBeNull();
    expect(localStorage.getItem("seriesmith.zoom")).toBe("3");
  });

  it("reads nothing, and throws nothing, without storage", () => {
    delete (globalThis as { localStorage?: unknown }).localStorage;
    expect(readDraft("x")).toBeNull();
    expect(() => writeDraft("x", 1)).not.toThrow();
    expect(() => pruneDrafts()).not.toThrow();
  });
});

describe("a refresh keeps the details on screen", () => {
  // the bug: a take landing dropped every cached detail of the episode, the
  // inspector showed "Loading…" and its form (with an unsaved edit) unmounted
  it("drops the episode's other details, keeps the ones on screen and other episodes'", () => {
    const d = {
      "C:/a/ep03|final|sh130": 1, "C:/a/ep03|final|sh140": 2, "C:/a/ep03|proxy|sh130": 3,
      "C:/a/ep03|final|sh130|ltx2": 4, "C:/a/ep04|final|sh130": 5,
    };
    expect(keepDetails(d, "C:/a/ep03", new Set(["final|sh130"]))).toEqual({ "C:/a/ep03|final|sh130": 1, "C:/a/ep04|final|sh130": 5 });
  });
});

function shot(id: string, cut: Partial<ShotStatus["cut"]> = {}, extra: Partial<ShotStatus> = {}, take: object = {}): ShotStatus {
  return {
    shot: id, orphan: false, length: 48, seconds: 2, subjects: [], missing_refs: [],
    override: { fields: [], stale: false },
    cut: { take: 1, picked: false, pass: "final", placeholder: false, usable: true, trim_in: 0, trim_out: 0,
           locked: false, note: "", in_cut_file: true, frames: 48, fps: 24, ...cut },
    takes: [{ take: 1, status: "ok", has_video: true, mp4: `renders/${id}/${id}_t01.mp4`, frames: 48, fps: 24, ...take }],
    ...extra,
  } as unknown as ShotStatus;
}

const status = (shots: ShotStatus[]) => ({ pass: "final", fps: 24, shots } as unknown as EpisodeStatus);

describe("the check before Export", () => {
  it("a whole cut has nothing to say", () => {
    expect(exportCheck(status([shot("sh010"), shot("sh020")]), "C:/a/ep03", "final")).toEqual([]);
  });

  it("names the shots with no take, and says when one is on its way", () => {
    const st = status([
      shot("sh010"),
      shot("sh020", { take: null, usable: false }, { takes: [] }),
      shot("sh030", { take: null, usable: false }, { takes: [] }),
      shot("sh040", {}, {}, { status: "failed", has_video: false }),
    ]);
    const queued: TakeRef[] = [{ ep: "C:/a/ep03", pass: "final", shot: "sh030", take: 1 }, { ep: "C:/a/ep03", pass: "proxy", shot: "sh020", take: 1 }];
    const p = exportCheck(st, "C:/a/ep03", "final", queued);
    expect(p.map((x) => [x.shot, x.kind])).toEqual([["sh020", "missing"], ["sh030", "missing"], ["sh040", "missing"]]);
    expect(p[0].text).toBe("no take");
    expect(p[1].text).toBe("no take (one is rendering or queued)");
    expect(p[2].text).toBe("its take in the cut failed");
  });

  it("skips what the export skips on purpose: shots left out, orphans", () => {
    const st = status([shot("sh010", { out: true, take: null, usable: false }), shot("sh020", { take: null, usable: false }, { orphan: true })]);
    expect(exportCheck(st, "C:/a/ep03", "final")).toEqual([]);
  });

  it("trims that leave nothing, a take shorter than its dialogue, a stand-in from the other pass", () => {
    const st = status([
      shot("sh010", { trim_in: 30, trim_out: 18 }),
      shot("sh020", {}, { audio_in: 10, audio_out: 13 } as Partial<ShotStatus>),
      shot("sh030", {}, { audio_in: 13, audio_out: 15 } as Partial<ShotStatus>),
      shot("sh040", { placeholder: true, pass: "proxy" }),
    ]);
    const p = exportCheck(st, "C:/a/ep03", "final");
    expect(p).toEqual([
      { shot: "sh010", kind: "missing", text: "its trims leave nothing of the take" },
      { shot: "sh020", kind: "short", text: "the take is 2.0 s, its dialogue on the recording 3.0 s" },
      { shot: "sh040", kind: "placeholder", text: "its proxy take stands in" },
    ]);
  });

  it("Titles can't run past a missing shot; Export can", () => {
    const missing = exportCheck(status([shot("sh020", { take: null, usable: false }, { takes: [] })]), "C:/a/ep03", "final");
    const short = exportCheck(status([shot("sh020", {}, { audio_in: 0, audio_out: 3 } as Partial<ShotStatus>)]), "C:/a/ep03", "final");
    expect(blocks({ kind: "titles", upscaled: false }, missing)).toBe(true);
    expect(blocks({ kind: "titles", upscaled: true }, short)).toBe(false);
    expect(blocks({ kind: "export", upscaled: false }, missing)).toBe(false);
  });

  it("lists shots briefly", () => {
    const ps = Array.from({ length: 10 }, (_, i) => ({ shot: `sh${i}`, kind: "missing" as const, text: "" }));
    expect(shotList(ps.slice(0, 2))).toBe("sh0, sh1");
    expect(shotList(ps)).toBe("sh0, sh1, sh2, sh3, sh4, sh5, sh6, sh7 and 2 more");
  });
});
