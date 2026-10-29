// The gallery's sections: which refs, which pictures, in what order.
import { describe, expect, it } from "vitest";
import {
  cutKey, gallerySections, itemAspect, itemKey, liveKey, searchRefSections, searchShotSections, sequencesOf, shotKey, shotSections, takeAspect,
  type GalleryScope,
} from "../src/lib/gallery";
import type { EpisodeStatus, Ref, RefTake, ShotStatus, TakeSummary } from "../src/types";

function ref(id: string, kind: Ref["kind"], over: Partial<Ref> = {}): Ref {
  return {
    id, scope: id.startsWith("shot:") ? "shot" : "series", kind, name: id.split(":")[1], path: `refs/${id.split(":")[1]}.png`,
    exists: true, sha1: "x", used_by: { proxy: ["sh010"], final: [] }, prompt: "", override: { fields: [], stale: false },
    takes: [], picked: null, ...over,
  };
}

function take(n: number, over: Partial<RefTake> = {}): RefTake {
  return {
    take: n, status: "ok", seed: "1", image: `refs/_takes/t${n}.png`, source: "generated", note: "",
    finished: `2026-10-0${n}T00:00:00`, ...over,
  };
}

const ALL: GalleryScope = { kind: "refs", group: null, ref: null, seq: null, shot: null, picksOnly: false, series: false };

describe("gallery sections", () => {
  const ada = ref("subject:ada", "character", {
    views: [
      { view: "01_threequarter", picked: 1, takes: [take(1), take(3)] },
      { view: "04_face", picked: null, takes: [take(2)] },
    ],
  });
  const street = ref("location:street", "location", {
    takes: [take(1), take(2, { status: "failed", image: null }), take(4, { status: "queued", image: null })],
    picked: 1, panos: [take(5)],
  });
  const voice = ref("voice:ada", "voice", { takes: [take(1, { image: null, audio: "a.wav" })] });
  const unused = ref("subject:kettle", "prop", { used_by: { proxy: [] }, takes: [take(1)] });
  const refs = [street, voice, unused, ada];

  it("groups in the Refs tab's order, leaves voices out and keeps to the episode", () => {
    expect(gallerySections(refs, ALL, "proxy").map((s) => s.ref.id)).toEqual(["subject:ada", "location:street"]);
    expect(gallerySections(refs, { ...ALL, series: true }, "proxy").map((s) => s.ref.id))
      .toEqual(["subject:ada", "subject:kettle", "location:street"]);
  });

  it("shows every finished picture newest first across views, live badged", () => {
    const [a] = gallerySections(refs, { ...ALL, ref: "subject:ada" }, "proxy");
    expect(a.items.map((i) => [i.view, i.take.take, i.live])).toEqual([
      ["01_threequarter", 3, false], ["04_face", 2, false], ["01_threequarter", 1, true],
    ]);
  });

  it("counts what it doesn't show, and never makes a 360 live", () => {
    const [s] = gallerySections(refs, { ...ALL, group: "locations" }, "proxy");
    expect(s.items.map((i) => [i.view, i.take.take, i.live])).toEqual([["pano", 5, false], [null, 1, true]]);
    expect([s.queued, s.failed]).toEqual([1, 1]);
  });

  it("live only keeps the picks", () => {
    const items = gallerySections(refs, { ...ALL, picksOnly: true }, "proxy").flatMap((s) => s.items);
    expect(items.map((i) => i.key)).toEqual([itemKey("subject:ada", "01_threequarter", 1), itemKey("location:street", null, 1)]);
  });

  it("opens a ref on its live picture, else its newest", () => {
    const secs = gallerySections(refs, ALL, "proxy");
    expect(liveKey(secs, "subject:ada")).toBe(itemKey("subject:ada", "01_threequarter", 1));
    const none = ref("subject:bo", "character", { exists: false, views: [{ view: "04_face", picked: null, takes: [take(1), take(2)] }] });
    expect(liveKey(gallerySections([none], { ...ALL, ref: "subject:bo" }, "proxy"), "subject:bo"))
      .toBe(itemKey("subject:bo", "04_face", 2));
  });

  it("a live file with no candidate behind it shows first, live, and is what it opens on", () => {
    const mia = ref("subject:mia", "character", { views: [{ view: "04_face", picked: null, takes: [take(1)] }] });
    const [s] = gallerySections([mia], { ...ALL, ref: "subject:mia" }, "proxy");
    expect(s.items.map((i) => [i.key, i.view, i.file, i.live, !!i.outside])).toEqual([
      ["subject:mia|live", "sheet", "refs/mia.png", true, true], [itemKey("subject:mia", "04_face", 1), "04_face", "refs/_takes/t1.png", false, false],
    ]);
    expect(liveKey([s], "subject:mia")).toBe("subject:mia|live");
    // at its own shape: one whole portrait, not a sheet's strip
    expect(itemAspect(s.items[0])).toBe(4);
    const [own] = gallerySections([{ ...mia, size: [600, 900] }], { ...ALL, ref: "subject:mia" }, "proxy");
    expect(itemAspect(own.items[0])).toBeCloseTo(2 / 3);
    expect(gallerySections([mia], { ...ALL, picksOnly: true }, "proxy")[0].items.map((i) => i.key)).toEqual(["subject:mia|live"]);
    // a plain ref with nothing but its file
    const hall = ref("location:hall", "location");
    expect(gallerySections([hall], ALL, "proxy")[0].items.map((i) => [i.view, i.file])).toEqual([[null, "refs/hall.png"]]);
    // no file, nothing to show
    expect(gallerySections([{ ...hall, exists: false }], ALL, "proxy")).toEqual([]);
  });

  it("sizes a tile by the picture, else by what its kind usually is", () => {
    expect(itemAspect({ ref: ada, view: "04_face", take: take(1, { width: 1024, height: 1024 }) })).toBe(1);
    expect(itemAspect({ ref: ada, view: "sheet", take: take(1) })).toBe(4);
    expect(itemAspect({ ref: street, view: null, take: take(1) })).toBeCloseTo(16 / 9);
    expect(itemAspect({ ref: street, view: "pano", take: take(5) })).toBe(2);
  });
});

function tk(n: number, over: Partial<TakeSummary> = {}): TakeSummary {
  return {
    take: n, status: "ok", has_video: true, seed: "1", seed_source: "stable", note: "", overrides: [], stale: [],
    thumb: `renders/t${n}.jpg`, strip: null, mp4: `renders/t${n}.mp4`, queued: null, finished: null, save_notes: "", ...over,
  };
}

function shot(id: string, sequence: string, takes: TakeSummary[], cut: number | null = null): ShotStatus {
  return {
    shot: id, orphan: false, sequence, length: 24, seconds: 1, size: null, subjects: [], audio_policy: null,
    cut: { take: cut, picked: cut != null, pass: "final", placeholder: false, usable: true, trim_in: 0, trim_out: 0, locked: false, note: "", in_cut_file: false },
    override: { fields: [], stale: false }, takes,
  };
}

describe("gallery shot sections", () => {
  const SHOTS: GalleryScope = { ...ALL, kind: "shots" };
  const st = { shots: [
    shot("sh010", "sq01", [tk(1), tk(2), tk(3, { status: "failed", mp4: null, thumb: null })], 1),
    shot("sh020", "sq01", [tk(1, { status: "queued", mp4: null, thumb: null })]),
    shot("sh030", "sq02", [tk(1), tk(2)], 2),
  ] } as unknown as EpisodeStatus;

  it("lists finished takes newest first in script order, the cut's badged", () => {
    const secs = shotSections(st, SHOTS, "final");
    expect(secs.map((s) => [s.shot.shot, s.seq, s.items.map((i) => [i.take.take, i.cut]), s.queued, s.failed])).toEqual([
      ["sh010", "sq01", [[2, false], [1, true]], 0, 1],
      ["sh020", "sq01", [], 1, 0],
      ["sh030", "sq02", [[2, true], [1, false]], 0, 0],
    ]);
    expect(sequencesOf(st)).toEqual(["sq01", "sq02"]);
  });

  it("narrows to a sequence or a shot, and to the cut", () => {
    expect(shotSections(st, { ...SHOTS, seq: "sq02" }, "final").map((s) => s.shot.shot)).toEqual(["sh030"]);
    expect(shotSections(st, { ...SHOTS, seq: "sq02", shot: "sh010" }, "final").map((s) => s.shot.shot)).toEqual(["sh010"]);
    expect(shotSections(st, { ...SHOTS, picksOnly: true }, "final").flatMap((s) => s.items.map((i) => i.key)))
      .toEqual([shotKey("sh010", 1), shotKey("sh030", 2)]);
  });

  it("a cut of the other pass isn't this pass's", () => {
    expect(shotSections(st, SHOTS, "proxy").flatMap((s) => s.items).some((i) => i.cut)).toBe(false);
  });

  it("opens a shot on its cut take, else its newest; a take at its own shape", () => {
    const secs = shotSections(st, SHOTS, "final");
    expect(cutKey(secs, "sh030")).toBe(shotKey("sh030", 2));
    expect(cutKey(shotSections(st, { ...SHOTS, shot: "sh010" }, "proxy"), "sh010")).toBe(shotKey("sh010", 2));
    expect(takeAspect({ width: 1280, height: 720 }, 1)).toBeCloseTo(16 / 9);
    expect(takeAspect({}, 2.35)).toBe(2.35);
  });
});

describe("gallery: a shared ref's other episodes", () => {
  const ada = ref("subject:ada", "character", {
    shared_with: ["ep01", "ep03"], live_owner: "ep01",
    views: [{ view: "04_face", picked: 1, takes: [take(1)] }],
  });
  const other = (episode: string, n: number, picked: boolean, over: Partial<RefTake> = {}) =>
    ({ ...take(n, over), view: "04_face", episode, picked });

  it("leaves the section to ask until they're read", () => {
    const [s] = gallerySections([ada], ALL, "proxy");
    expect([s.unread, s.items.length]).toEqual([true, 1]);
  });

  it("puts them after this episode's, by episode; live only where they wrote the file read here", () => {
    const shared = new Map([["subject:ada", [other("ep03", 2, true), other("ep01", 1, true), other("ep01", 2, false)]]]);
    const [s] = gallerySections([ada], ALL, "proxy", shared);
    expect(s.unread).toBe(false);
    expect(s.items.map((i) => [i.episode ?? "here", i.take.take, i.live])).toEqual([
      ["here", 1, true], ["ep01", 2, false], ["ep01", 1, true], ["ep03", 2, false],
    ]);
    expect(new Set(s.items.map((i) => i.key)).size).toBe(4);
  });

  it("a shared file nobody's pick wrote shows as it is; a sibling's pick waits to be read", () => {
    const ava = ref("subject:ava", "character", { shared_with: ["ep01"], live_owner: null, views: [] });
    expect(gallerySections([ava], ALL, "proxy")[0].items.map((i) => i.key)).toEqual(["subject:ava|live"]);
    const theirs = { ...ava, live_owner: "ep01" };
    expect(gallerySections([theirs], ALL, "proxy")[0].items).toEqual([]);
    const read = gallerySections([theirs], ALL, "proxy", new Map([["subject:ava", [other("ep01", 1, true)]]]))[0];
    expect(read.items.map((i) => [i.episode, i.live])).toEqual([["ep01", true]]);
  });

  it("a shared ref nobody here uses still asks, then goes when there's nothing", () => {
    const quiet = ref("subject:bo", "character", { used_by: { proxy: [] }, shared_with: ["ep01"], exists: false, views: [] });
    expect(gallerySections([quiet], { ...ALL, series: true }, "proxy").map((s) => s.unread)).toEqual([true]);
    expect(gallerySections([quiet], { ...ALL, series: true }, "proxy", new Map([["subject:bo", []]]))).toEqual([]);
  });
});

describe("gallery: the search box", () => {
  const ada = ref("subject:ada", "character", {
    views: [
      { view: "01_threequarter", picked: 1, takes: [take(1)] },
      { view: "04_face", picked: null, takes: [take(2)] },
    ],
  });
  const street = ref("location:street", "location", { takes: [take(1)], picked: 1, panos: [take(5)] });
  const refs = [street, ada];

  it("keeps the refs and pictures with every word, nothing for no words", () => {
    const all = gallerySections(refs, ALL, "proxy");
    expect(searchRefSections(all, "  ")).toBe(all);
    expect(searchRefSections(all, "ADA").map((s) => s.ref.id)).toEqual(["subject:ada"]);
    // a view narrows to its pictures; words together must all be there
    expect(searchRefSections(all, "ada face").flatMap((s) => s.items.map((i) => i.view))).toEqual(["04_face"]);
    expect(searchRefSections(all, "location 360").flatMap((s) => s.items.map((i) => i.view))).toEqual(["pano"]);
    expect(searchRefSections(all, "live").flatMap((s) => s.items.map((i) => i.key)))
      .toEqual([itemKey("subject:ada", "01_threequarter", 1), itemKey("location:street", null, 1)]);
    expect(searchRefSections(all, "ada street")).toEqual([]);
  });

  it("finds shots by id, size, who's in it, the take and its model", () => {
    const st = { shots: [
      { ...shot("sh010", "sq01", [tk(1, { target: "ltx2_msr" }), tk(2, { target: "seedance_2_5" })], 2), size: "ecu", subjects: ["cindy"] },
      { ...shot("sh020", "sq02", [tk(1)]), size: "ws", subjects: ["mia", "ava"] },
    ] } as unknown as EpisodeStatus;
    const all = shotSections(st, { ...ALL, kind: "shots" }, "final");
    const keys = (q: string) => searchShotSections(all, q).flatMap((s) => s.items.map((i) => i.key));
    expect(keys("cindy")).toEqual([shotKey("sh010", 2), shotKey("sh010", 1)]);
    expect(keys("ecu seedance")).toEqual([shotKey("sh010", 2)]);
    expect(keys("sh010 t01")).toEqual([shotKey("sh010", 1)]);
    expect(keys("cut")).toEqual([shotKey("sh010", 2)]);
    expect(keys("ava sq02")).toEqual([shotKey("sh020", 1)]);
  });
});
