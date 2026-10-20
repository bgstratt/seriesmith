// A picture for one of your presets: the window offers rendering it (an edit model
// for a relight), the take or ref picture selected now, and importing one; your
// tiles carry its button and their remove.
import { createElement } from "react";
import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { PresetPictureDialog } from "../src/components/PresetPictureDialog";
import { PresetPicker } from "../src/components/PresetPicker";
import { MOCK_TARGETS } from "../src/mock/mockTargets";
import { initialState, store } from "../src/store";
import { setApi } from "../src/host";
import type { Api } from "../src/api";

setApi({ presetImageUrl: (name: string) => `/seriesmith/presets/image?name=${name}` } as unknown as Api);

function show(sel: Partial<ReturnType<typeof store.get>>) {
  store.set({ ...initialState(), targets: MOCK_TARGETS, ep: "C:/Shows/ep01", pass: "proxy",
    presetPictureAsk: { kind: "relight", id: "glow", label: "Glow" }, ...sel });
  return renderToString(createElement(PresetPictureDialog)).replace(/<!-- -->/g, "");
}

describe("a picture for a preset of yours", () => {
  it("offers the three ways", () => {
    const html = show({});
    expect(html).toContain("Render it");
    expect(html).toContain("Pick an edit model");
    expect(html).toContain("Select a take in Shots");                // nothing selected yet
    expect(html).toContain("Import a picture");
  });
  it("offers what is selected", () => {
    const html = show({ shot: "sh020", take: 3, refSel: { ref: "location:street", view: null, take: 4 } });
    expect(html).toContain("A frame of sh020 t03 (proxy)");
    expect(html).toContain("location:street t04");
    expect(html).not.toContain("Select a take in Shots");
  });
  it("is reached from your tile", () => {
    const html = renderToString(createElement(PresetPicker, {
      tiles: [{ id: "glow", label: "Glow", group: "yours", text: "a green glow", own: { kind: "relight", rendering: true } }],
      value: "", onPick: () => {},
    }));
    expect(html).toContain("Yours");
    expect(html).toContain("a green glow");                          // no picture yet: its words
    expect(html).toContain("Its picture is rendering");
    expect(html).toContain("Give “Glow” a picture");
    expect(html).toContain("Remove your relight");
  });
});
