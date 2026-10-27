// The gallery's sections: which refs, which pictures, in what order.
import { describe, expect, it } from "vitest";
import {
  cutKey, gallerySections, itemAspect, itemKey, liveKey, sequencesOf, shotKey, shotSections, takeAspect, type GalleryScope,
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
    const none = ref("subject:bo", "character", { views: [{ view: "04_face", picked: null, takes: [take(1), take(2)] }] });
    expect(liveKey(gallerySections([none], { ...ALL, ref: "subject:bo" }, "proxy"), "subject:bo"))
      .toBe(itemKey("subject:bo", "04_face", 2));
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
