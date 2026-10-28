// Through the mock API: several shots selected and queued together, a picture
// dropped on a shot as its first keyframe, and an image refused between clips.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { clickShot, loadRefs, refreshEpisode, renderSelected, select } from "../src/actions";
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

  it("a picture dropped between clips opens the shot form there, for a new shot with it as its first keyframe", async () => {
    expect(isPicture({ name: "a.PNG" })).toBe(true);
    expect(isPicture({ name: "a.webp" })).toBe(true);
    expect(isPicture({ name: "a.mp4" })).toBe(false);
    const [a] = shots();
    const pic = new File([], "frame.jpg");
    await dropFileBetween(1, pic);
    expect(store.get().shotForm).toMatchObject({ shot: null, after: a, file: pic, dur: null, left: a });
    await dropFileBetween(1, new File([], "notes.txt"));
    expect(toasts.at(-1)?.[1]).toBe("Not a video or a picture");
  });
});
