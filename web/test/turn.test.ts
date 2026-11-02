// @vitest-environment happy-dom
//
// Turn's model and the Edits model: the Turn button runs on Qwen 2.1 + angles
// or any edit model (the viewer's choice, kept in this browser), and the Refs
// tab's Made with row has an Edits picker of the models that can edit.
import { act, createElement } from "react";
import { createRoot } from "react-dom/client";
import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ImageModelBar, TurnButton, TurnModelPick } from "../src/components/RefsTab";
import { TURN_TARGET, turnChoices, turnPlan } from "../src/lib/turn";
import { initialState, store } from "../src/store";
import { setApi, setHost, type Host } from "../src/host";
import type { Api } from "../src/api";
import type { Ref, TargetList } from "../src/types";

const READY = { status: "ready" as const, missing: [], resolved: {}, features_off: [], nodes_missing: [] };
const NOT_READY = {
  status: "not_ready" as const, resolved: {}, features_off: [], nodes_missing: [],
  missing: [{ param: "model", want: "qwen.safetensors", folder: "diffusion_models", tier: "required" as const, url: null }],
};

function listWith(qwenReady: boolean): TargetList {
  return {
    targets: [
      { id: "krea2", kind: "image", label: "Krea 2", capabilities: { mode: "t2i" }, readiness: READY },
      { id: "flux2_klein_edit", kind: "image", label: "Flux 2 Klein edit", capabilities: { mode: "edit", max_refs: 4 }, readiness: READY },
      { id: "flux_kontext", kind: "image", label: "Flux Kontext", capabilities: { mode: "edit", max_refs: 1 }, readiness: READY },
      { id: TURN_TARGET, kind: "image", label: "Qwen-Image 2.1", capabilities: { mode: "edit", max_refs: 16 }, readiness: qwenReady ? READY : NOT_READY },
    ],
    default: { image: "krea2" },
  } as unknown as TargetList;
}

const ADA = {
  id: "subject:ada", scope: "series", kind: "character", name: "Ada", path: "refs/ada.png", exists: true, sha1: "x",
  used_by: { proxy: [], final: [] }, prompt: "", override: { fields: [], stale: false }, takes: [], picked: null,
  views: [
    { view: "01_threequarter", picked: 1, takes: [] }, { view: "02_side", picked: null, takes: [] },
    { view: "03_back", picked: null, takes: [] }, { view: "04_face", picked: null, takes: [] },
  ],
} as unknown as Ref;

describe("Turn's model", () => {
  it("automatic: Qwen 2.1 + angles unless it can't render, else the Edits model in words", () => {
    const p = turnPlan(listWith(true), "", "flux2_klein_edit");
    expect(p.target).toBeNull();
    expect(p.how).toBe("angles");
    expect(p.uses).toContain("Qwen 2.1 + angles");
    expect(p.uses).toContain("Flux 2 Klein edit");
    const q = turnPlan(listWith(false), "", "flux2_klein_edit");
    expect(q.target).toBeNull();                 // the server picks the same
    expect(q.how).toBe("words");
    expect(q.uses).toContain("the episode's Edits model, Flux 2 Klein edit");
  });

  it("a chosen model (Turns with) is the one it runs on, with its readiness warning", () => {
    const k = turnPlan(listWith(true), "flux_kontext", "flux2_klein_edit");
    expect(k).toMatchObject({ target: "flux_kontext", how: "words", warn: null });
    const q = turnPlan(listWith(false), TURN_TARGET, "flux2_klein_edit");
    expect(q.target).toBe(TURN_TARGET);
    expect(q.warn?.severity).toBe("err");
    // a choice that is no longer a model here: automatic again
    expect(turnPlan(listWith(true), "gone_model", "flux2_klein_edit").target).toBeNull();
    // the other edit models: not Qwen (it's offered with its LoRA), not a text-to-image one
    expect(turnChoices(listWith(true)).map((t) => t.id)).toEqual(["flux2_klein_edit", "flux_kontext"]);
  });

  it("the button names the model it will use", () => {
    store.set({ ...initialState(), ep: "C:/ep02", targets: listWith(true), refs: { "C:/ep02": [ADA] },
      refDefaults: { "C:/ep02": { target: "krea2", keyframe_target: "flux2_klein_edit", edit_target: "flux_kontext", edit_target_source: "editor" } } });
    let html = renderToString(createElement(TurnButton, { r: ADA, view: "03_back", label: "Back" }));
    expect(html).toContain("↻ Turn");
    expect(html).not.toContain("▾");                       // the model is Made with's Turns with
    expect(html).toContain("Qwen 2.1 + angles when the angles LoRA is installed, else the episode&#x27;s Edits model (Flux Kontext)");
    store.set({ refDefaults: { "C:/ep02": { target: "krea2", keyframe_target: "flux2_klein_edit", edit_target: "flux_kontext",
      edit_target_source: "editor", turn_target: "flux2_klein_edit", turn_target_source: "editor" } } });
    html = renderToString(createElement(TurnButton, { r: ADA, view: "03_back", label: "Back" }));
    expect(html).toContain("on Flux 2 Klein edit, told the turn in words");
  });
});

describe("Turns with in Made with", () => {
  it("offers automatic, Qwen 2.1 + angles and the edit models, and saves the episode's choice", async () => {
    (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
    let sent: unknown = null;
    setApi({ putRefDefaults: async (_ep: string, f: unknown) => { sent = f; return { defaults: { turn_target: "flux_kontext", turn_target_source: "editor" } }; },
      refs: async () => ({ refs: [ADA], defaults: {} }) } as unknown as Api);
    setHost({ toast: () => {}, on: () => () => {} } as unknown as Host);
    store.set({ ...initialState(), ep: "C:/ep02", targets: listWith(true), refs: { "C:/ep02": [ADA] },
      refDefaults: { "C:/ep02": { target: "krea2", keyframe_target: "flux2_klein_edit", edit_target: "flux_kontext", edit_target_source: "editor" } } });
    const el = document.createElement("div");
    document.body.appendChild(el);
    const root = createRoot(el);
    act(() => root.render(createElement(ImageModelBar, { open0: true })));
    const label = Array.from(el.querySelectorAll("span")).find((x) => x.textContent === "Turns with:")!;
    const select = label.parentElement!.querySelector("select") as HTMLSelectElement;
    const texts = Array.from(select.options).map((o) => o.textContent);
    expect(texts[0]).toBe("Automatic: Qwen 2.1 + angles if installed, else the Edits model");
    expect(texts.some((t) => t?.includes("Qwen 2.1 + angles") && t.endsWith("(best for turning)"))).toBe(true);
    expect(texts.some((t) => t?.includes("Flux Kontext"))).toBe(true);
    expect(texts.some((t) => t?.includes("Krea 2"))).toBe(false);        // text to image only
    await act(async () => {
      select.value = "flux_kontext";
      select.dispatchEvent(new Event("change", { bubbles: true }));
    });
    expect(sent).toEqual({ turn_target: "flux_kontext" });
    act(() => root.unmount());
    el.remove();
  });
});

describe("Turn with, on a character", () => {
  it("is the same choice as Turns with, where the Turn buttons are", async () => {
    let sent: unknown = null;
    setApi({ putRefDefaults: async (_ep: string, f: unknown) => { sent = f; return { defaults: { turn_target: TURN_TARGET, turn_target_source: "editor" } }; },
      refs: async () => ({ refs: [ADA], defaults: {} }) } as unknown as Api);
    setHost({ toast: () => {}, on: () => () => {} } as unknown as Host);
    store.set({ ...initialState(), ep: "C:/ep02", targets: listWith(true), refs: { "C:/ep02": [ADA] },
      refDefaults: { "C:/ep02": { target: "krea2", keyframe_target: "flux2_klein_edit", edit_target: "flux_kontext", edit_target_source: "editor" } } });
    const el = document.createElement("div");
    document.body.appendChild(el);
    const root = createRoot(el);
    act(() => root.render(createElement(TurnModelPick)));
    const select = el.querySelector("#sm-turn-model") as HTMLSelectElement;
    expect(select.value).toBe("");
    expect(select.options[0].textContent).toBe("Automatic: Qwen 2.1 + angles if installed, else the Edits model (Flux Kontext)");
    await act(async () => {
      select.value = TURN_TARGET;
      select.dispatchEvent(new Event("change", { bubbles: true }));
    });
    expect(sent).toEqual({ turn_target: TURN_TARGET });
    act(() => root.unmount());
    el.remove();
  });
});

describe("the Edits model in Made with", () => {
  it("offers only the models that can edit", () => {
    store.set({ ...initialState(), ep: "C:/ep02", targets: listWith(true), refs: { "C:/ep02": [ADA] },
      refDefaults: { "C:/ep02": { target: "krea2", keyframe_target: "flux2_klein_edit", edit_target: "flux_kontext", edit_target_source: "editor" } } });
    const html = renderToString(createElement(ImageModelBar, { open0: true }));
    expect(html).toContain("Edits with:");
    // the folded line names all of them, the Edits model among them
    expect(html).toContain("Krea 2 · Flux 2 Klein edit · Flux Kontext");
    const edits = html.slice(html.indexOf("Edits with:"), html.indexOf("Voices with:") > 0 ? html.indexOf("Voices with:") : undefined);
    expect(edits).toContain("Flux Kontext");
    expect(edits).not.toContain("Krea 2");
    // an episode choice offers the series config snippet
    expect(html).toContain("&quot;edit_target&quot;: &quot;flux_kontext&quot;");
  });
});
