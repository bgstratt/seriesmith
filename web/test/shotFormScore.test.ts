// @vitest-environment happy-dom
//
// The shot form's score marks (docs/EDITOR.md "Editing a shot"): the beat a shot starts and a
// theme marked on it, written as // beat: and // theme: lines above its ## line (not in its
// block), read back when it opens; and a hit on its first frame in the mix.
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { refreshEpisode } from "../src/actions";
import { ShotFormWindow } from "../src/components/ShotForm";
import { setApi, setHost, type Host } from "../src/host";
import { marksAbove, withMarks } from "../src/lib/shotForm";
import { createMockApi } from "../src/mock/mockApi";
import { loadMix, mixSettled } from "../src/mixActions";
import { initialState, statusKey, store } from "../src/store";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

describe("a shot's score marks, in the script", () => {
  const text = ["// structure: Pixar Story Spine", "", "// beat: Once upon a time…", "# sq01  porch", "", "## sh010",
    "Ada waits.", "", "// a note", "// theme: show, tender", "## sh020", "Ada sits.", "", "## sh030", "Ada goes."].join("\n");

  it("are read from above the shot: past comments, blank lines and its sequence's header", () => {
    expect(marksAbove(text, 6)).toEqual({ beat: "Once upon a time…", theme: "", lines: [3] });
    expect(marksAbove(text, 11)).toEqual({ beat: "", theme: "show, tender", lines: [10] });
    expect(marksAbove(text, 14)).toEqual({ beat: "", theme: "", lines: [] });
  });

  it("are written just above its ## line, the old ones taken out", () => {
    const t = withMarks(text, "sh010", { beat: "Every day…", theme: "" });
    expect(t).toContain("// beat: Every day…\n## sh010");
    expect(t).not.toContain("Once upon a time");
    expect(t.startsWith("// structure: Pixar Story Spine\n\n# sq01  porch")).toBe(true);
    const u = withMarks(text, "sh020", { beat: "Until one day…", theme: "" });
    expect(u).toContain("// a note\n// beat: Until one day…\n## sh020");
    expect(u).not.toContain("show, tender");
    expect(withMarks(text, "sh999", { beat: "x", theme: "" })).toBe(text);
  });
});

describe("the shot form's score marks", () => {
  let root: Root;
  let el: HTMLDivElement;
  let EP: string;
  let api: ReturnType<typeof createMockApi>;
  let sent: string;

  beforeEach(async () => {
    setHost({ on: () => () => {}, toast: () => {}, show: () => {} } as unknown as Host);
    api = createMockApi(() => {}, { latency: 0 });
    sent = "";
    // what the form writes (the mock's script is rebuilt from its shotlist: comments aren't kept)
    setApi({ ...api, putSource: async (r) => {
      if (r.file === "script") sent = r.text;
      return api.putSource(r);
    } });
    EP = (await api.episodes())[0].ep;
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

  const change = async (sel: string, value: string) => {
    const x = el.querySelector(sel) as HTMLInputElement | HTMLSelectElement;
    await act(async () => {
      const proto = x instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto, "value")!.set!.call(x, value);
      x.dispatchEvent(new Event(x instanceof HTMLSelectElement ? "change" : "input", { bubbles: true }));
    });
  };

  it("writes the beat and theme above the shot, and its hit in the mix", async () => {
    const shot = store.get().status[statusKey(EP, "proxy")]!.shots[1].shot;
    store.set({ shotForm: { shot, after: null } });
    await act(async () => root.render(createElement(ShotFormWindow)));
    await act(async () => {});
    const more = [...el.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent?.includes("the score's beat"))!;
    await act(async () => more.click());
    await act(async () => {});
    await change("input[aria-label=Beat]", "Until one day…");
    await change("input[aria-label='Theme mark']", "show, tender");
    await change("select[aria-label=Hit]", "turn");
    expect(el.textContent).toContain("not saved");
    const save = [...el.querySelectorAll<HTMLButtonElement>("button")].find((b) => b.textContent?.trim() === "Save")!;
    await act(async () => save.click());
    // the save: the script, its rebuild, then the hit in the mix
    for (let i = 0; i < 100 && !(await api.getMix(EP, "proxy")).mix.hits?.some((h) => h.at.shot === shot); i++) {
      await act(async () => {
        await new Promise((r) => setTimeout(r, 20));
        await mixSettled();
      });
    }
    expect(sent).toContain(`// beat: Until one day…\n// theme: show, tender\n## ${shot}`);
    const hit = (await api.getMix(EP, "proxy")).mix.hits?.find((h) => h.at.shot === shot);
    expect(hit?.kind).toBe("turn");
    expect(hit?.name).toBe("Until one day…");
  });
});
