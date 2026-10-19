// @vitest-environment happy-dom
//
// The series form's Look field, mounted as Series settings mounts it: before the
// presets have loaded it must not loop (a selector that made a fresh `[]` on every
// read re-rendered forever: React error #185), and once they have, the builder's
// rows write the line.
import { act, createElement, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { Api } from "../src/api";
import { FieldRow } from "../src/components/SeriesForm";
import { setApi } from "../src/host";
import { SECTIONS } from "../src/lib/seriesForm";
import { initialState, store } from "../src/store";
import type { PresetList } from "../src/types";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const LOOK = SECTIONS.flatMap((s) => s.fields).find((f) => f.path.join(".") === "style.look")!;
const PRESETS: PresetList = {
  relight: [], framing: [], camera: [],
  look: [{ id: "noir", label: "Neon noir", group: "live action", text: "a neon noir", parts: { medium: "live" } }],
  look_builder: [
    { id: "medium", label: "Medium", camera_row: false, options: [{ id: "live", label: "Live action", clause: "a live-action film" }] },
    { id: "grade", label: "Grade", camera_row: false, options: [{ id: "warm", label: "Warm", clause: "a warm grade" }] },
  ],
};
let resolve: (p: PresetList) => void = () => {};
let line = "";
let parts: Record<string, string> = {};

function Harness() {
  const [v, setV] = useState("");
  const [p, setP] = useState<Record<string, string>>({});
  line = v; parts = p;
  return createElement(FieldRow, { f: LOOK, value: v, onChange: setV, lookParts: p, onLookParts: setP });
}

let host: HTMLDivElement;
let root: Root;
beforeEach(() => {
  store.set({ ...initialState(), presets: null });
  setApi({ presets: () => new Promise<PresetList>((r) => { resolve = r; }),
           presetImageUrl: (n: string) => `/img/${n}` } as unknown as Api);
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});
afterEach(() => { act(() => root.unmount()); host.remove(); });

describe("the Look field", () => {
  it("mounts before the presets load, without looping", () => {
    expect(() => act(() => root.render(createElement(Harness)))).not.toThrow();
    expect(host.querySelector("textarea")).not.toBeNull();
  });

  it("builds the line once they have", async () => {
    act(() => root.render(createElement(Harness)));
    await act(async () => { resolve(PRESETS); });
    const open = [...host.querySelectorAll("button")].find((b) => b.textContent?.includes("Build the look"))!;
    act(() => open.click());
    const tile = (label: string) => [...host.querySelectorAll("button.sm-preset")].find((b) => b.textContent?.includes(label))! as HTMLButtonElement;
    act(() => tile("Live action").click());
    act(() => tile("Warm").click());
    expect(parts).toEqual({ medium: "live", grade: "warm" });
    expect(line).toBe("a live-action film; a warm grade");
  });
});
