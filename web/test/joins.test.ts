// A clip's fades and its dissolve from the clip before (the cut entry's fade_in /
// fade_out / dissolve): the cut carries them, and the playlist lays them as the
// export does (a dissolve gives half its length from each clip; its join has no
// fades), so the timeline's widths and Play all's clock are the export's.
import { beforeEach, describe, expect, it } from "vitest";
import { refreshEpisode } from "../src/actions";
import { setJoin } from "../src/cutActions";
import { setApi, setHost, type Host } from "../src/host";
import { fieldsOf, withFields } from "../src/lib/cutEdit";
import { buildPlaylist, fadeLevel, type PlayItem } from "../src/lib/playlist";
import { createElement } from "react";
import { renderToString } from "react-dom/server";
import { JoinCurves } from "../src/components/JoinCurves";
import { createMockApi } from "../src/mock/mockApi";
import { initialState, statusKey, store } from "../src/store";

describe("fades and dissolves", () => {
  let EP: string;
  const st = () => store.get().status[statusKey(EP, "proxy")]!;

  beforeEach(async () => {
    setHost({ on: () => () => {}, toast: () => {}, show: () => {} } as unknown as Host);
    const api = createMockApi(() => {}, { latency: 0 });
    setApi(api);
    EP = (await api.episodes())[0].ep;
    store.set(initialState());
    store.set({ ep: EP, pass: "proxy" });
    await refreshEpisode(EP, "proxy");
  });

  it("travel with the cut entry, each its own", () => {
    const list = withFields([{ shot: "a" }], "a", { fade_out: 12 });
    expect(list[0]).toEqual({ shot: "a", fade_out: 12 });
    expect(fieldsOf(list[0])).toMatchObject({ fade_in: 0, fade_out: 12, dissolve: 0 });
  });

  it("a dissolve takes half from each clip; the cut is that much shorter", async () => {
    const before = buildPlaylist(st());
    // two playable clips side by side, each long enough for it
    const k = before.findIndex((x, i) => i > 0 && x.mp4 && before[i - 1].mp4 && x.dur > 1 && before[i - 1].dur > 1);
    const [a, b] = [before[k - 1], before[k]];
    const total = before.reduce((t, x) => t + x.dur, 0);
    expect(await setJoin(b.shot, "dissolve", 12)).toBe(true);
    const after = buildPlaylist(st());
    const a2 = after.find((x) => x.shot === a.shot)!;
    const b2 = after.find((x) => x.shot === b.shot)!;
    const fps = st().fps || 24;
    expect(a2.dur).toBeCloseTo(a.dur - 6 / fps, 6);
    expect(b2.dur).toBeCloseTo(b.dur - 6 / fps, 6);
    expect(b2.inT).toBeCloseTo(b.inT + 6 / fps, 6);
    expect(a2.dissolveOut).toBeCloseTo(12 / fps, 6);
    expect(after.reduce((t, x) => t + x.dur, 0)).toBeCloseTo(total - 12 / fps, 6);
    expect(b2.start).toBeCloseTo(a2.start + a2.dur, 6);
  });

  it("a fade dims its own end only", async () => {
    const a = buildPlaylist(st()).find((x) => x.mp4 && x.dur > 2)!;
    await setJoin(a.shot, "fade_out", 24);
    const it = buildPlaylist(st()).find((x) => x.shot === a.shot)!;
    const fps = st().fps || 24;
    expect(it.fadeOut).toBeCloseTo(24 / fps, 6);
    expect(it.fadeIn).toBe(0);
    expect(fadeLevel(it, 0)).toBe(1);
    expect(fadeLevel(it, it.dur)).toBe(0);
    expect(fadeLevel(it, it.dur - 12 / fps)).toBeCloseTo(0.5, 6);
  });
});

describe("dragging a fade or a dissolve", () => {
  const item = (over: Partial<PlayItem> = {}): PlayItem => ({
    shot: "sh020", mp4: "x.mp4", start: 0, dur: 4, inT: 0, outT: 4, trimIn: 0, trimOut: 0, total: 96,
    audioIn: null, audioOut: null, fadeIn: 0, fadeOut: 0, dissolveIn: 0, dissolveOut: 0, ...over,
  } as PlayItem);
  const html = (props: Parameters<typeof JoinCurves>[0]) => renderToString(createElement(JoinCurves, props));
  const onDown = () => {};

  it("a clip with none has a corner handle each end, to drag one out", () => {
    const h = html({ it: item(), width: 400, height: 60, fps: 24, onDown });
    expect(h.match(/h3-join-corner/g)?.length).toBe(2);
    expect(h).toContain("Drag right: a fade in from black");
    expect(h).toContain("Drag left: a fade out to black");
  });

  it("each curve has its handle at its inner end; a locked clip has none", () => {
    const h = html({ it: item({ fadeIn: 0.5, dissolveOut: 1 }), next: "sh030", width: 400, height: 60, fps: 24, onDown });
    expect(h.match(/<circle/g)?.length).toBe(2);
    expect(h).toContain('cx="50"');                       // half a second at 100 px a second
    expect(h).toContain('cx="350"');                      // half of a 1 s dissolve, from the end
    expect(h).not.toContain("h3-join-corner");
    expect(html({ it: item({ fadeIn: 0.5 }), width: 400, height: 60, fps: 24, onDown, locked: true })).not.toContain("<circle");
  });

  it("the curves follow the drag, the dissolve on both its clips", () => {
    const drag = { shot: "sh030", key: "dissolve" as const, frames: 48 };
    // sh020 draws its half of sh030's dissolve: 1 s of 2 s, from its end
    expect(html({ it: item(), next: "sh030", width: 400, height: 60, fps: 24, onDown, drag })).toContain('cx="300"');
    expect(html({ it: item({ shot: "sh030" }), width: 400, height: 60, fps: 24, onDown, drag })).toContain('cx="100"');
  });
});
