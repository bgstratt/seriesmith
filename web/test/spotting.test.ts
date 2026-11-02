// @vitest-environment happy-dom
//
// The spotting sheet (docs/SOUND.md "The spotting sheet"): the music map's rows
// (a run of one sequence each, in cut order) and what's clipped to them, the
// hits on the cut's clock and the jump between them, the cues stale under the
// cut, a cue's hits table (bar and beat, the fit's error, each take's, ranked
// columns with the one in the mix), a take auditioned in the preview's mix and
// a tempo held; then the window on the mock: it opens on the cut player, lists
// the cue and the hits, a hit row seeks, a take auditions, an alternative tempo
// saves the cue's bpm (fixed), and a cue opens in the cue window and comes back.
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  auditionMix, auditionOf, bedBlocks, cueBlocks, cueIsStale, cutHits, hitTable, inRow, nextHit, sequenceRows, staleCues, takeColumns, takeOfItem,
  timecode, withTempo,
} from "../src/lib/spotting";
import type { PlayItem } from "../src/lib/playlist";
import type { CuePlan, CueSpec, CueSummary, CueTake, Mix } from "../src/types";

function clip(shot: string, start: number, dur: number, trimIn = 0): PlayItem {
  const inT = trimIn / 24;
  return {
    shot, index: 0, pass: "final", take: 1, mp4: `${shot}.mp4`, why: "", start, dur, inT, outT: inT + dur, trimIn, trimOut: 0,
    total: null, audioIn: null, audioOut: null, fadeIn: 0, fadeOut: 0, dissolveIn: 0, dissolveOut: 0,
  };
}

// four clips of 4 s: sh010 and sh020 in s1, sh030 in s2, sh040 back in s1 (the cut moved it)
const ITEMS: PlayItem[] = [clip("sh010", 0, 4), clip("sh020", 4, 4, 12), clip("sh030", 8, 4), clip("sh040", 12, 4)].map((x, i) => ({ ...x, index: i }));
const SEQ: Record<string, string> = { sh010: "s1", sh020: "s1", sh030: "s2", sh040: "s1" };
const seqOf = (shot: string) => SEQ[shot];
const a = (shot: string, frame = 0) => ({ shot, frame });

const summary = (spec: CueSpec, extra: Partial<CueSummary> = {}): CueSummary => ({ spec, takes: 0, ok: 0, placed: [], ...extra });

describe("the music map", () => {
  it("is a row per run of one sequence, in cut order", () => {
    const rows = sequenceRows(ITEMS, seqOf);
    expect(rows.map((r) => [r.seq, r.start, r.end, r.shots.map((s) => s.shot)])).toEqual([
      ["s1", 0, 8, ["sh010", "sh020"]], ["s2", 8, 12, ["sh030"]], ["s1", 12, 16, ["sh040"]],
    ]);
    expect(sequenceRows([], seqOf)).toEqual([]);
  });

  it("lays the cues on the cut's clock, clipped to each row they cross", () => {
    const mix: Mix = { items: [{ id: "m01", track: "music", path: "sound/m01/t03.wav", in: a("sh010") }] };
    const cues = [
      summary({ id: "m02", in: a("sh030", 24), out: a("sh040", 48) }, { ok: 2, in_mix: null, stale: [], stale_takes: [1, 2] }),
      summary({ id: "m01", label: "1M1", in: a("sh010", 48), out: a("sh030", 24) }, { ok: 1 }),
      summary({ id: "m09", in: a("sh900"), out: a("sh900", 10) }),
    ];
    const blocks = cueBlocks(cues, ITEMS, 24, mix);
    // by start; the one off the cut left out
    expect(blocks.map((b) => [b.id, b.start, b.end, b.inMix])).toEqual([["m01", 2, 9, 3], ["m02", 9, 14, null]]);
    expect(blocks[0].label).toBe("1M1");
    expect(blocks.map((b) => b.muted)).toEqual([false, false]);
    // its item muted: the block says so (drawn faint)
    expect(cueBlocks(cues, ITEMS, 24, { items: [{ ...mix.items![0], mute: true }] })[0].muted).toBe(true);
    // every finished take stale and none in the mix: stale
    expect(blocks[1].stale.length).toBe(1);
    const [s1, s2, s1b] = sequenceRows(ITEMS, seqOf);
    expect(inRow(s1, blocks).map((b) => [b.id, b.a, b.b, b.fromBefore, b.onAfter])).toEqual([["m01", 2, 8, false, true]]);
    expect(inRow(s2, blocks).map((b) => [b.id, b.a, b.b, b.fromBefore, b.onAfter])).toEqual([["m01", 8, 9, true, false], ["m02", 9, 12, false, true]]);
    expect(inRow(s1b, blocks).map((b) => b.id)).toEqual(["m02"]);
    expect(bedBlocks([{ place: "hall", label: "Hall", path: "x.wav", exists: true, words: "", shots: [], in: a("sh010"), out: a("sh020"), start: 0, end: 8, gain_db: 0, mute: false }]))
      .toEqual([{ id: "hall", label: "Hall", start: 0, end: 8, exists: true, mute: false }]);
  });

  it("reads the take in the mix from its item's file", () => {
    expect(takeOfItem("m01", { id: "m01", track: "music", path: "sound/m01/t12.wav", in: a("sh010") })).toBe(12);
    expect(takeOfItem("m01", { id: "m01", track: "music", path: "audio/score.wav", in: a("sh010") })).toBeNull();
    expect(takeOfItem("m01", undefined)).toBeNull();
  });

  it("a cue is stale when the take in the mix is, or (none placed) every finished take is", () => {
    const spec = { id: "m01", in: a("sh010"), out: a("sh020") };
    expect(cueIsStale(summary(spec, { ok: 2, in_mix: 1, stale: ["door moved -3 frames"], stale_takes: [1] }))).toBe(true);
    expect(cueIsStale(summary(spec, { ok: 2, in_mix: 2, stale: [], stale_takes: [1] }))).toBe(false);
    expect(cueIsStale(summary(spec, { ok: 2, in_mix: null, stale: [], stale_takes: [1] }))).toBe(false);
    expect(cueIsStale(summary(spec, { ok: 2, in_mix: null, stale: [], stale_takes: [1, 2] }))).toBe(true);
    expect(cueIsStale(summary(spec, { ok: 0, in_mix: null, stale: [], stale_takes: [] }))).toBe(false);
    expect(staleCues([summary({ ...spec, id: "m02" }, { ok: 1, stale: ["x"] }), summary(spec, { ok: 1, stale: ["y"] })]).map((c) => c.spec.id)).toEqual(["m01", "m02"]);
  });
});

describe("hits on the cut's clock", () => {
  const mix: Mix = {
    hits: [
      { id: "h2", name: "reveal", at: a("sh030", 12), kind: "arrive" },
      { id: "h1", at: a("sh020", 24) },
      { id: "h3", name: "gone", at: a("sh900", 0) },
    ],
  };
  const hits = cutHits(mix, ITEMS, 24);

  it("are the mix's hits in the cut, in time order, named", () => {
    expect(hits.map((h) => [h.id, h.name, h.kind, h.t])).toEqual([["h1", "h1", "accent", 4.5], ["h2", "reveal", "arrive", 8.5]]);
  });

  it("jump to the next or the one before, past the one the playhead is on", () => {
    expect(nextHit(hits, 0, 1, 24)?.id).toBe("h1");
    expect(nextHit(hits, 4.5, 1, 24)?.id).toBe("h2");
    expect(nextHit(hits, 4.51, -1, 24)?.id).toBeUndefined();
    expect(nextHit(hits, 8.5, -1, 24)?.id).toBe("h1");
    expect(nextHit(hits, 9, 1, 24)).toBeNull();
    expect(nextHit(hits, 4, -1, 24)).toBeNull();
  });

  it("timecode is hours, minutes, seconds and frames", () => {
    expect(timecode(0, 24)).toBe("00:00:00:00");
    expect(timecode(83.5, 24)).toBe("00:01:23:12");
    expect(timecode(3600 + 1 / 24, 24)).toBe("01:00:00:01");
  });
});

describe("a cue's hits table", () => {
  const spec: CueSpec = { id: "m01", in: a("sh010", 24), out: a("sh030", 48), bpm: 120 };
  // 120 bpm in 4/4 from 0.5 s before the in point (1 s into the cut)
  const plan = {
    fps: 24, bar: 2, bars: 6, preroll: 0.5,
    hits: [
      { id: "h1", name: "door", kind: "accent", must: true, t: 3.5, at: a("sh020", 60) },
      { id: "h2", name: "reveal", kind: "arrive", must: true, t: 5.5, at: a("sh020", 108) },
      { id: "h3", name: "out", kind: "drop", must: false, t: 9, at: a("sh030", 48), ends: true },
    ],
    fit: { bpm: 120, ask_bpm: 120, stretch: 1, errors: [0.2, -0.4, null], worst_must: 0.4 },
  } as unknown as CuePlan;
  const take = (n: number, errs: (number | null)[], score: number, extra: Partial<CueTake> = {}): CueTake => ({
    take: n, status: "ok", file: `sound/m01/t${String(n).padStart(2, "0")}.wav`,
    measured: { bpm_heard: 120, tempo_heard: true, stretch: 1, downbeat: 0.2, offset: 0.7, hit_errors: errs, worst_must: 0, levels: [], shape_error: 0.3, score },
    ...extra,
  });
  // best first, as the server ranks them; a failed one last
  const takes = [take(3, [0.5, -1, null], 0.2), take(1, [3, null, null], 0.9, { stale: ["door moved"] }), { take: 2, status: "failed" } as CueTake];

  it("has a column per measured take, best first, the one in the mix and the stale ones marked", () => {
    expect(takeColumns(takes, 1)).toEqual([{ take: 3, rank: 1, inMix: false, stale: false }, { take: 1, rank: 2, inMix: true, stale: true }]);
  });

  it("each hit: where it is in the cut, the bar and beat it lands on, the fit's error and each take's", () => {
    const rows = hitTable(spec, plan, takes, takeColumns(takes, 1), ITEMS, 24);
    expect(rows.map((r) => [r.id, r.t, r.barBeat, r.fit, r.takes, r.ends])).toEqual([
      ["h1", 4.5, "3.1", 0.2, [0.5, 3], false],
      ["h2", 6.5, "4.1", -0.4, [-1, null], false],
      ["h3", 10, "5.4", null, [null, null], true],
    ]);
    expect(rows[0].at).toEqual(a("sh020", 60));
    // its in point not in the cut: no cut time
    expect(hitTable({ ...spec, in: a("sh900") }, plan, takes, [], ITEMS, 24)[0].t).toBeNull();
  });

  it("a take auditioned takes its cue's place in the preview's mix only, its level kept", () => {
    const au = auditionOf("EP", "final", { ...spec, label: "1M1" }, plan, takes[0])!;
    expect(au).toEqual({ ep: "EP", pass: "final", cue: "m01", take: 3, path: "sound/m01/t03.wav", offset: 0.7, fadeOut: 48, in: spec.in, out: spec.out, label: "1M1" });
    expect(auditionOf("EP", "final", spec, plan, takes[2])).toBeNull();
    const mix: Mix = { items: [
      { id: "amb", track: "ambience", path: "a.wav", in: a("sh010") },
      { id: "m01", track: "music", path: "sound/m01/t01.wav", in: a("sh010", 24), out: a("sh030", 48), gain_db: -3, points: [{ at: a("sh020"), db: -6 }] },
    ] };
    const out = auditionMix(mix, au);
    expect(out.items!.map((i) => i.id)).toEqual(["amb", "m01"]);
    expect(out.items![1]).toEqual({ id: "m01", track: "music", path: "sound/m01/t03.wav", in: spec.in, out: spec.out, offset: 0.7, fade_out: 48, label: "1M1", gain_db: -3 });
    expect(mix.items![1].path).toBe("sound/m01/t01.wav");
    // a cue with no item yet: one added
    expect(auditionMix({}, au).items).toHaveLength(1);
  });

  it("a tempo picked holds the cue there", () => {
    expect(withTempo(spec, 117.004)).toEqual({ ...spec, bpm: 117.004, fixed_tempo: true });
  });
});

// ---------------------------------------------------------------------------
// the window on the mock
// ---------------------------------------------------------------------------

import { refreshEpisode } from "../src/actions";
import { Viewer } from "../src/components/Viewer";
import { SoundAddDialog } from "../src/components/SoundAdd";
import { cueKey, cueSettled, loadCue } from "../src/cueActions";
import { resetCutHistory } from "../src/cutActions";
import { setApi, setHost, type Host } from "../src/host";
import { createMockApi } from "../src/mock/mockApi";
import { loadMix, mixSettled } from "../src/mixActions";
import { loadCueStates, openSpotting } from "../src/spotActions";
import { initialState, statusKey, store } from "../src/store";
import { Fragment } from "react";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

describe("the spotting sheet", () => {
  let root: Root;
  let el: HTMLDivElement;
  let EP: string;
  let api: ReturnType<typeof createMockApi>;

  // a <video> that keeps the time it's sought to (happy-dom's stays at 0, and the player's clock follows the picture)
  const seekable = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, "currentTime");
  beforeEach(async () => {
    Object.defineProperty(HTMLMediaElement.prototype, "currentTime", {
      configurable: true,
      get(this: { _t?: number }) { return this._t ?? 0; },
      set(this: { _t?: number }, v: number) { this._t = v; },
    });
    setHost({ on: () => () => {}, toast: () => {}, show: () => {} } as Host);
    api = createMockApi(() => {}, { latency: 0, cueDemo: true });
    setApi(api);
    EP = (await api.episodes())[0].ep;
    store.set(initialState());
    resetCutHistory();
    store.set({ ep: EP, pass: "proxy" });
    await refreshEpisode(EP, "proxy");
    await loadMix(EP, "proxy");
    el = document.createElement("div");
    document.body.appendChild(el);
    root = createRoot(el);
  });
  afterEach(() => {
    act(() => root.unmount());
    el.remove();
    store.set(initialState());
    if (seekable) Object.defineProperty(HTMLMediaElement.prototype, "currentTime", seekable);
  });

  const q = (sel: string) => [...document.querySelectorAll<HTMLElement>(sel)];
  const open = async (cue: string | null = "m01") => {
    await act(async () => {
      openSpotting(cue);
      root.render(createElement(Viewer));
    });
    await act(async () => {
      await loadCueStates(EP, "proxy");
      if (cue) await loadCue(EP, "proxy", cue);
    });
  };

  it("opens on the cut player with the map: the cue, the hits by kind, the selected cue's hits table and takes", async () => {
    await open();
    const v = store.get().viewer!;
    expect([v.kind, v.spot, v.cue]).toEqual(["cut", true, "m01"]);
    expect(q(".h3-spot-win video")).toHaveLength(2);                  // Play all's picture
    expect(store.get().cueStates[statusKey(EP, "proxy")]!.map((c) => c.spec.id)).toEqual(["m01"]);
    // the cue on the music lane (once per row it crosses), selected
    const cues = q(".h3-spot-cue");
    expect(cues.length).toBeGreaterThan(0);
    expect(cues[0].textContent).toContain("1M1 The Reveal");
    expect(cues[0].className).toContain("h3-on");
    expect(cues[0].textContent).toContain("not placed");
    // the three hits, coloured by kind
    const hits = q(".h3-spot-hit");
    expect(hits.map((h) => h.textContent)).toEqual(["she looks up", "the reveal", "silence"]);
    expect(hits[1].className).toContain("h3-hit-arrive");
    expect(hits[2].className).toContain("h3-hit-may");
    // the hits table: a row each, a column per measured take, best first
    const res = store.get().cue[cueKey(EP, "proxy", "m01")]!;
    const rows = q(".h3-spot-hitrow");
    expect(rows).toHaveLength(3);
    expect(q(".h3-spot-table th").length).toBe(7 + 3);
    expect(rows[1].textContent).toContain("the reveal");
    expect(rows[1].textContent).toContain(`${res.plan!.hits[1].at!.shot}:${res.plan!.hits[1].at!.frame}`);
    // the tempo, its alternatives (the fitted one first, current), the series' direction and the script's notes
    const side = q(".h3-spot-side")[0];
    expect(side.textContent).toContain("The tempo");
    const alts = q(".h3-spot-alt");
    expect(alts.length).toBe(res.plan!.alternatives!.length);
    expect(alts[0].className).toContain("h3-on");
    expect(side.textContent).toContain("sincere, never comic");
    expect(side.textContent).toContain("tension rises");
    // a stale take is no stale cue (none in the mix, not every take stale)
    expect(side.textContent).toContain("None: every cue's takes match the cut.");
  });

  it("a hit row seeks the viewer to it; the next-hit button goes on to the next", async () => {
    await open();
    const res = store.get().cue[cueKey(EP, "proxy", "m01")]!;
    // each <video> loaded (happy-dom fires nothing), so the player parks at the seek
    const loaded = () => act(async () => {
      q("video").forEach((x) => x.dispatchEvent(new Event("loadedmetadata")));
      await new Promise((r) => setTimeout(r, 40));
    });
    await act(async () => q(".h3-spot-hitrow")[1].click());
    await loaded();
    const items = (await import("../src/actions")).currentPlaylist(store.get());
    const { anchorTime } = await import("../src/lib/mix");
    const fps = store.get().status[statusKey(EP, "proxy")]!.fps || 24;
    const t = anchorTime(items, res.plan!.hits[1].at!, fps)!;
    expect(store.get().cutPlay.pos).toBeCloseTo(Math.round(t * fps) / fps, 5);
    const next = [...document.querySelectorAll<HTMLButtonElement>(".h3-spot-transport button")].find((b) => b.title.startsWith("The next hit"))!;
    await act(async () => next.click());
    await loaded();
    const t3 = anchorTime(items, res.plan!.hits[2].at!, fps)!;
    expect(store.get().cutPlay.pos).toBeCloseTo(Math.round(t3 * fps) / fps, 5);
    // + Hit at the playhead: the hits lane's action
    const add = [...document.querySelectorAll<HTMLButtonElement>(".h3-spot-transport button")].find((b) => b.textContent?.includes("Hit at playhead"))!;
    await act(async () => {
      add.click();
      await mixSettled();
    });
    expect((await api.getMix(EP, "proxy")).mix.hits).toHaveLength(4);
  });

  it("a take auditioned plays in the cue's place from its in point, and back to the mix", async () => {
    await open();
    const res = store.get().cue[cueKey(EP, "proxy", "m01")]!;
    const second = res.takes[1];
    await act(async () => document.querySelector<HTMLButtonElement>(`[aria-label='Audition t${String(second.take).padStart(2, "0")}']`)!.click());
    const au = store.get().audition!;
    expect([au.cue, au.take, au.path]).toEqual(["m01", second.take, second.file]);
    expect(store.get().cutPlay.playing).toBe(true);
    expect(q(".h3-spot-aud")[0].textContent).toContain("Auditioning");
    // the mix itself unchanged
    expect((await api.getMix(EP, "proxy")).mix.items?.some((i) => i.id === "m01")).toBeFalsy();
    await act(async () => q(".h3-spot-aud button")[0].click());
    expect(store.get().audition).toBeNull();
  });

  it("an alternative tempo clicked holds the cue at it: its bpm saved, fixed", async () => {
    await open();
    const res = store.get().cue[cueKey(EP, "proxy", "m01")]!;
    const alt = res.plan!.alternatives![1];
    await act(async () => q(".h3-spot-alt")[1].click());
    await act(async () => {
      await cueSettled();
    });
    const saved = (await api.getCue(EP, "proxy", "m01")).spec;
    expect([saved.bpm, saved.fixed_tempo]).toEqual([alt.bpm, true]);
    expect(store.get().cue[cueKey(EP, "proxy", "m01")]!.plan!.fit.bpm).toBe(alt.bpm);
  });

  it("a cue picked shows its take in the mix; a double-click opens the cue window, whose head comes back", async () => {
    await api.pickCue({ ep: EP, pass: "proxy", cue: "m01", take: 2, gain: true });
    await loadMix(EP, "proxy");
    await open();
    expect(q(".h3-spot-cue")[0].textContent).toContain("t02");
    expect(q(".h3-spot-table th.h3-spot-inmix")).toHaveLength(1);
    await act(async () => q(".h3-spot-cue")[0].dispatchEvent(new MouseEvent("dblclick", { bubbles: true })));
    expect([store.get().viewer?.kind, store.get().viewer?.cue, store.get().viewer?.back]).toEqual(["cue", "m01", "spot"]);
    const back = [...document.querySelectorAll<HTMLButtonElement>(".h3-cue-win button")].find((b) => b.textContent?.includes("Spotting"))!;
    await act(async () => back.click());
    expect([store.get().viewer?.kind, store.get().viewer?.spot, store.get().viewer?.cue]).toEqual(["cut", true, "m01"]);
  });

  it("the scoring window's tabs: with no cue selected the cue tabs open the first, on their tab", async () => {
    await open();
    const tab = (name: string) => [...document.querySelectorAll<HTMLButtonElement>(".h3-spot-win .h3-seg button")].find((b) => b.textContent!.trim() === name)!;
    store.set((s) => ({ viewer: { ...s.viewer!, cue: undefined } }));
    await act(async () => {});
    expect([tab("Spotting").classList.contains("h3-on"), tab("Score").disabled, tab("Arc").disabled]).toEqual([true, false, false]);
    await act(async () => tab("Arc").click());
    expect([store.get().viewer?.kind, store.get().viewer?.cue, store.get().viewer?.cueTab]).toEqual(["cue", "m01", "arc"]);
    const on = [...document.querySelectorAll<HTMLButtonElement>(".h3-cue-win .h3-seg button")].find((b) => b.classList.contains("h3-on"))!;
    expect(on.textContent!.trim()).toBe("Arc");
  });

  it("with no cue in the episode the cue tabs ask for one, and the cue window opens on the tab clicked", async () => {
    // the episode with no cue (the demo's hidden); the one made is saved
    const put: string[] = [];
    setApi({ ...api, cues: async () => ({ cues: [] }), putCue: async (ep, cue) => {
      put.push(cue.id);
      return api.putCue(ep, cue);
    } });
    await act(async () => {
      openSpotting(null);
      root.render(createElement(Fragment, null, createElement(Viewer), createElement(SoundAddDialog)));
    });
    await act(async () => {
      await loadCueStates(EP, "proxy");
    });
    const tab = (name: string) => [...document.querySelectorAll<HTMLButtonElement>(".h3-spot-win .h3-seg button")].find((b) => b.textContent!.trim() === name)!;
    expect([tab("Score").disabled, tab("Arc").disabled, tab("Orchestration & takes").disabled]).toEqual([false, false, false]);
    expect(tab("Arc").title).toContain("No cue yet");
    await act(async () => tab("Arc").click());
    expect(store.get().soundAdd).toEqual({ kind: "cue", tab: "arc" });
    const make = document.querySelector<HTMLButtonElement>(".h3-dialog button[data-act='make-cue']")!;
    expect(make.disabled).toBe(false);
    await act(async () => make.click());
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
    const v = store.get().viewer!;
    expect(put).toHaveLength(1);
    expect([v.kind, v.cue, v.cueTab, v.back]).toEqual(["cue", put[0], "arc", "spot"]);
  });

  it("a right-click on a row of the map makes a cue over its sequence", async () => {
    await open();
    const rows = q(".h3-spot-row");
    const row = rows[rows.length > 1 ? 1 : 0];
    const seq = row.querySelector(".h3-spot-rowhead b")!.textContent!;
    const ids = [...row.querySelectorAll<HTMLElement>(".h3-spot-shots .h3-spot-shot")].map((x) => x.textContent!);
    await act(async () => row.querySelector(".h3-spot-rowhead")!.dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, cancelable: true, clientX: 40, clientY: 40 })));
    const menu = document.querySelector<HTMLElement>(".h3-spot-menu")!;
    expect(menu.textContent).toContain(`New cue over ${seq}`);
    expect(menu.textContent).toContain("Mark a hit here");
    expect(menu.textContent).toContain(`Make effects for ${seq}`);
    const before = (await api.cues(EP)).cues.map((c) => c.spec.id);
    await act(async () => menu.querySelector<HTMLButtonElement>("button[data-spot='cue-seq']")!.click());
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
    const made = (await api.cues(EP)).cues.find((c) => !before.includes(c.spec.id))!;
    expect([made.spec.in.shot, made.spec.out.shot]).toEqual([ids[0], ids[ids.length - 1]]);
    const v = store.get().viewer!;
    expect([v.kind, v.cue, v.cueTab, v.back]).toEqual(["cue", made.spec.id, "score", "spot"]);
    expect(document.querySelector(".h3-spot-menu")).toBeNull();
  });

  it("a right-click on a cue block offers its own: Open in Score", async () => {
    await open();
    await act(async () => q(".h3-spot-cue")[0].dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, cancelable: true, clientX: 40, clientY: 40 })));
    const open1 = document.querySelector<HTMLButtonElement>(".h3-spot-menu button[data-spot='open-score']")!;
    expect(open1.textContent).toContain("Open m01 in Score");
    await act(async () => open1.click());
    expect([store.get().viewer?.kind, store.get().viewer?.cue, store.get().viewer?.cueTab]).toEqual(["cue", "m01", "score"]);
  });

  it("a stale take in the mix lists the cue as stale, to render again", async () => {
    await api.pickCue({ ep: EP, pass: "proxy", cue: "m01", take: 3, gain: true });   // t03 is the stale one
    await loadMix(EP, "proxy");
    await open();
    const list = q(".h3-spot-stalelist")[0];
    expect(list.textContent).toContain("she looks up moved -6 frames");
    const before = (await api.getCue(EP, "proxy", "m01")).takes.length;
    await act(async () => [...list.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent === "Render")!.click());
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
    expect((await api.getCue(EP, "proxy", "m01")).takes.length).toBeGreaterThan(before);
  });
});
