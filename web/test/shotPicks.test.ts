// Through the mock API: several shots selected and queued together, a picture
// dropped on a shot as its first keyframe or between clips (held), a text file refused.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { clickShot, generateDubTracks, loadRefs, refreshEpisode, renderSelected, select, setSound } from "../src/actions";
import { VOICE_TARGET, VOICE_TARGETS } from "../src/lib/readiness";
import type { TargetList } from "../src/types";
import { setApi, setHost, type Host } from "../src/host";
import { keyframeRefId } from "../src/lib/keyframes";
import { createMockApi } from "../src/mock/mockApi";
import { initialState, statusKey, store } from "../src/store";
import { dropFileBetween, dropFileOnto, isPicture } from "../src/takeActions";

describe("several shots, and a picture as a keyframe", () => {
  let api: ReturnType<typeof createMockApi>;
  let EP: string;
  const toasts: [string, string, string?][] = [];
  const shots = () => store.get().status[statusKey(EP, "proxy")]!.shots.filter((s) => !s.orphan).map((s) => s.shot);

  beforeEach(async () => {
    toasts.length = 0;
    setHost({ on: () => () => {}, toast: (k: string, t: string, b?: string) => toasts.push([k, t, b]), show: () => {} } as unknown as Host);
    api = createMockApi(() => {}, { latency: 0 });
    setApi(api);
    EP = (await api.episodes())[0].ep;
    store.set(initialState());
    store.set({ ep: EP, pass: "proxy" });
    await refreshEpisode(EP, "proxy");
  });
  afterEach(() => store.set(initialState()));

  it("Shift-click selects a run of shots; Generate queues each, redone at auto seeds", async () => {
    const [a, b, c] = shots();
    clickShot(a, null, {});
    clickShot(c, null, { shiftKey: true });
    expect(store.get().multi).toEqual([a, b, c]);
    const spy = vi.spyOn(api, "render");
    renderSelected();
    await vi.waitFor(() => expect(spy).toHaveBeenCalled());
    expect(spy.mock.calls[0][0]).toMatchObject({ shots: [a, b, c], redo: true, seed_mode: "auto" });
  });

  it("Render… asks first, with the selection; selecting a shot outside it ends it", () => {
    const [a, b, , d] = shots();
    clickShot(a, null, {});
    clickShot(b, null, { ctrlKey: true });
    renderSelected(true);
    expect(store.get().renderAsk).toMatchObject({ shots: [a, b], redo: true, seedMode: "auto" });
    select(b);
    expect(store.get().multi).toEqual([a, b]);
    select(d);
    expect(store.get().multi).toEqual([]);
  });

  it("a picture dropped on a shot is its live first keyframe", async () => {
    const shot = shots()[1];
    await loadRefs(EP);
    const spy = vi.spyOn(api, "refsUpload");
    await dropFileOnto(shot, new File([new Uint8Array([137, 80, 78, 71])], "frame.png", { type: "image/png" }));
    expect(spy).toHaveBeenCalledOnce();
    expect(spy.mock.calls[0][0]).toMatchObject({ ref: keyframeRefId(shot, "first"), view: null, pick: true });
  });

  it("a picture dropped between clips is held there: a new shot in the script, the picture its take", async () => {
    expect(isPicture({ name: "a.PNG" })).toBe(true);
    expect(isPicture({ name: "a.webp" })).toBe(true);
    expect(isPicture({ name: "a.mp4" })).toBe(false);
    const put = vi.spyOn(api, "putSource");
    const hold = vi.spyOn(api, "holdTake");
    const pic = new File([], "frame.jpg");
    await dropFileBetween(1, pic);
    expect(store.get().shotForm).toBeNull();
    expect(put.mock.calls[0][0].text).toContain("A held picture: frame.jpg.");
    expect(hold).toHaveBeenCalledTimes(1);
    expect(hold.mock.calls[0][0]).toMatchObject({ file: pic, seconds: 3, pick: true });
    await dropFileBetween(1, new File([], "notes.txt"));
    expect(toasts.at(-1)?.[1]).toBe("Not a video or a picture");
  });

  it("a dub track without its voice model opens Features on it, and queues nothing", () => {
    const spy = vi.spyOn(api, "render");
    store.set({ targets: { targets: [{ id: VOICE_TARGET, readiness: { status: "not_ready", missing: [] } }] } as unknown as TargetList });
    generateDubTracks([shots()[0]]);
    expect(store.get()).toMatchObject({ featuresOpen: true, featuresFocus: VOICE_TARGETS[0].feature });
    expect(spy).not.toHaveBeenCalled();
  });

  it("a dub track renders on the voice model, kept apart; a sound is set for the shots", async () => {
    const render = vi.spyOn(api, "render");
    generateDubTracks([shots()[0]], "fasth3_omni");
    await vi.waitFor(() => expect(render).toHaveBeenCalled());
    expect(render.mock.calls[0][0]).toMatchObject({ shots: [shots()[0]], dub_track: true, target: "fasth3_omni", redo: true });
    const put = vi.spyOn(api, "putSound");
    expect(await setSound([shots()[0]], { mode: "dub", dub: { from: "dub", take: 1 } })).toBe(true);
    expect(put).toHaveBeenCalledWith(EP, [shots()[0]], { mode: "dub", dub: { from: "dub", take: 1 } });
  });
});
