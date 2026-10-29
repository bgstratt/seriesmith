// A clip's fades and its dissolve from the clip before (the cut entry's fade_in /
// fade_out / dissolve): the cut carries them, and the playlist lays them as the
// export does (a dissolve gives half its length from each clip; its join has no
// fades), so the timeline's widths and Play all's clock are the export's.
import { beforeEach, describe, expect, it } from "vitest";
import { refreshEpisode } from "../src/actions";
import { setJoin } from "../src/cutActions";
import { setApi, setHost, type Host } from "../src/host";
import { fieldsOf, withFields } from "../src/lib/cutEdit";
import { buildPlaylist, fadeLevel } from "../src/lib/playlist";
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
