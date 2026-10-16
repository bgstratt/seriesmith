// @vitest-environment happy-dom
//
// The length picker: the lengths offered, or Custom… with a box to type in.
// The bug it replaces: the shot form's "other…" copied a length already in the
// list, so the list jumped back to it and the box never opened.
import { act, createElement, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { LengthPicker } from "../src/components/LengthPicker";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const SEEDANCE = { fps: 24, frames: { step: 24, base: 96, max: 720 } };
let last = "";

function Harness(p: { start: string; template?: object }) {
  const [v, setV] = useState(p.start);
  last = v;
  return createElement(LengthPicker, { value: v, onChange: setV, template: p.template, short: "Seedance" });
}

function choose(select: HTMLSelectElement, value: string) {
  act(() => {
    const set = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value")!.set!;
    set.call(select, value);
    select.dispatchEvent(new Event("change", { bubbles: true }));
  });
}

function type(input: HTMLInputElement, value: string) {
  act(() => {
    const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
    set.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

describe("the length picker", () => {
  let root: Root;
  let host: HTMLDivElement;
  beforeEach(() => {
    host = document.createElement("div");
    document.body.appendChild(host);
    root = createRoot(host);
  });
  afterEach(() => {
    act(() => root.unmount());
    host.remove();
  });

  it("Custom… opens a box even from a length in the list, and keeps it open", () => {
    act(() => root.render(createElement(Harness, { start: "3.04" })));
    expect(host.querySelector("input")).toBeNull();
    choose(host.querySelector("select")!, "__custom__");
    const box = host.querySelector("input")!;
    expect(box).not.toBeNull();
    type(box, "7.5");
    expect(last).toBe("7.5");
    expect(host.querySelector("select")!.value).toBe("__custom__");
  });

  it("a length not in the list starts in Custom…; picking one from the list closes it", () => {
    act(() => root.render(createElement(Harness, { start: "12" })));
    expect(host.querySelector("input")!.value).toBe("12");
    choose(host.querySelector("select")!, "5.17");
    expect(host.querySelector("input")).toBeNull();
    expect(last).toBe("5.17");
  });

  it("says what the model renders", () => {
    act(() => root.render(createElement(Harness, { start: "1.62", template: SEEDANCE })));
    expect(host.textContent).toContain("Seedance renders 4 s");
    choose(host.querySelector("select")!, "__custom__");
    type(host.querySelector("input")!, "45");
    expect(host.textContent).toContain("30 s: Seedance's longest");
  });
});
