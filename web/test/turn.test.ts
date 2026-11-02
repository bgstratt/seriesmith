// Turn's model and the Edits model: the Turn button runs on Qwen 2.1 + angles
// or any edit model (the viewer's choice, kept in this browser), and the Refs
// tab's Made with row has an Edits picker of the models that can edit.
import { createElement } from "react";
import { renderToString } from "react-dom/server";
import { afterEach, describe, expect, it } from "vitest";
import { ImageModelBar, TurnButton } from "../src/components/RefsTab";
import { TURN_TARGET, readTurnModel, setTurnModel, turnChoices, turnPlan } from "../src/lib/turn";
import { initialState, store } from "../src/store";
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

afterEach(() => setTurnModel(""));

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

  it("a chosen model is sent, with its readiness warning", () => {
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

  it("is remembered in this browser", () => {
    const m = new Map<string, string>();
    (globalThis as { localStorage?: unknown }).localStorage = {
      getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => m.set(k, v), removeItem: (k: string) => m.delete(k),
    };
    setTurnModel("flux_kontext");
    expect(m.get("seriesmith.turnModel")).toBe("flux_kontext");
    expect(readTurnModel()).toBe("flux_kontext");
    setTurnModel("");
    expect(readTurnModel()).toBe("");
    delete (globalThis as { localStorage?: unknown }).localStorage;
  });

  it("the button names the model it will use", () => {
    store.set({ ...initialState(), ep: "C:/ep02", targets: listWith(true), refs: { "C:/ep02": [ADA] },
      refDefaults: { "C:/ep02": { target: "krea2", keyframe_target: "flux2_klein_edit", edit_target: "flux_kontext", edit_target_source: "editor" } } });
    let html = renderToString(createElement(TurnButton, { r: ADA, view: "03_back", label: "Back" }));
    expect(html).toContain("↻ Turn");
    expect(html).toContain("▾");
    expect(html).toContain("Qwen 2.1 + angles when the angles LoRA is installed, else the episode&#x27;s Edits model (Flux Kontext)");
    setTurnModel("flux2_klein_edit");
    html = renderToString(createElement(TurnButton, { r: ADA, view: "03_back", label: "Back" }));
    expect(html).toContain("on Flux 2 Klein edit, told the turn in words");
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
