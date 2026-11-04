// @vitest-environment happy-dom
//
// The first-pass score (docs/SCORING.md "A first pass from the script"): the spotting sheet's
// Draft dialog asks what it would draft (POST /seriesmith/cue/draft, nothing written), shows its
// cues, sections, themes and flags, and writes them: the cue list and the mix fetched again, the
// dialogue to voices only unless the takes' sound is kept. A second draft waits for Replace.
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { refreshEpisode } from "../src/actions";
import { ScoreDraftDialog } from "../src/components/ScoreDraft";
import { setApi, setHost, type Host } from "../src/host";
import { createMockApi } from "../src/mock/mockApi";
import { currentMix, loadMix } from "../src/mixActions";
import { initialState, store } from "../src/store";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const flush = () => act(async () => { for (let i = 0; i < 5; i++) await new Promise((r) => setTimeout(r, 0)); });

describe("drafting the score", () => {
  let root: Root;
  let el: HTMLDivElement;
  let EP: string;
  let api: ReturnType<typeof createMockApi>;
  let asked: { write?: boolean; replace?: boolean; keep_sound?: boolean }[];
  let closed: number;

  beforeEach(async () => {
    setHost({ on: () => () => {}, toast: () => {}, show: () => {} } as Host);
    api = createMockApi(() => {}, { latency: 0, cueDemo: true });
    EP = (await api.episodes())[0].ep;
    asked = [];
    closed = 0;
    setApi({ ...api, scoreDraft: async (req) => { asked.push(req); return api.scoreDraft(req); } });
    store.set(initialState());
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
  });

  const open = async () => {
    act(() => root.render(createElement(ScoreDraftDialog, { ep: EP, pass: "proxy", onClose: () => closed++ })));
    await flush();
  };
  const button = (text: string) => [...el.querySelectorAll("button")].find((b) => b.textContent?.includes(text))!;

  it("shows the draft, then writes it", async () => {
    await open();
    expect(asked).toEqual([{ ep: EP, pass: "proxy", rendered: false }]); // shown, nothing written
    expect(el.textContent).toContain("The Pixar Story Spine");
    expect(el.textContent).toContain("Every day…: light, a simple repeating figure");
    expect(el.textContent).toContain("makes the episode's theme");
    expect(el.textContent).toContain("music in the scene");
    await act(async () => button("Write 1 cue").click());
    await flush();
    expect(asked[1]).toMatchObject({ write: true, replace: false, keep_sound: false });
    expect(closed).toBe(1);
    expect(currentMix()?.mix.hits?.some((h) => h.id === "dh01")).toBe(true);
    expect(currentMix()?.mix.tracks?.dialogue?.voices_only).toBe(true);
    expect(store.get().cues[EP]?.some((c) => c.spec.id === "d01")).toBe(true);
  });

  it("a script with no beat lines: says so, and lays a structure out when one is picked", async () => {
    setApi({ ...api, scoreDraft: async (req) => {
      asked.push(req);
      const r = await api.scoreDraft(req);
      return { ...r, draft: { ...r.draft, marked: false, laid: req.structure ?? null } };
    } });
    await open();
    expect(el.textContent).toContain("This script has no beat lines");
    const pick = el.querySelector("select[aria-label=Structure]") as HTMLSelectElement;
    expect([...pick.options].map((o) => o.value)).toEqual(["", "The Pixar Story Spine", "The Sitcom Formula (Circular Structure)"]);
    await act(async () => {
      pick.value = "The Pixar Story Spine";
      pick.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await flush();
    expect(asked.at(-1)).toMatchObject({ structure: "The Pixar Story Spine" });
    expect(el.textContent).toContain("Once upon a time… at");
    expect(el.textContent).toContain("Write these beat lines into the script");
    await act(async () => button("Write 1 cue").click());
    await flush();
    expect(asked.at(-1)).toMatchObject({ write: true, structure: "The Pixar Story Spine", mark: true });
  });

  it("a second draft waits for Replace", async () => {
    await api.scoreDraft({ ep: EP, pass: "proxy", write: true, keep_sound: true });
    await open();
    expect(button("Write 1 cue").disabled).toBe(true);
    const replace = [...el.querySelectorAll("label")].find((l) => l.textContent?.includes("Replace the earlier draft (d01)"))!;
    await act(async () => replace.querySelector("input")!.click());
    expect(button("Write 1 cue").disabled).toBe(false);
    await act(async () => button("Write 1 cue").click());
    await flush();
    expect(asked.at(-1)).toMatchObject({ write: true, replace: true });
  });
});
