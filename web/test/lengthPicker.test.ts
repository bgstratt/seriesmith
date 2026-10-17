// @vitest-environment happy-dom
//
// The length picker: a box for seconds, always there, and the lengths offered
// to fill it from. (The shot form's "other…" it replaces copied a length
// already in the list, so the list jumped back to it and its box never opened.)
import { act, createElement, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { LengthPicker } from "../src/components/LengthPicker";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const SEEDANCE = { fps: 24, frames: { step: 24, base: 96, max: 720 } };
let last = "";

function Harness(p: { start: string; template?: object; auto?: boolean }) {
  const [v, setV] = useState(p.start);
  last = v;
  return createElement(LengthPicker, { value: v, onChange: setV, template: p.template, auto: p.auto, short: "Seedance" });
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

  it("the box is always there; the menu fills it and goes back to its label", () => {
    act(() => root.render(createElement(Harness, { start: "3.04" })));
    const box = host.querySelector("input")!;
    expect(box.value).toBe("3.04");
    expect(host.textContent).toContain("the workhorse shot");
    choose(host.querySelector("select")!, "5.17");
    expect(last).toBe("5.17");
    expect(host.querySelector("select")!.value).toBe("");            // reads "lengths" again
    type(host.querySelector("input")!, "7.5");
    expect(last).toBe("7.5");
    expect(host.querySelectorAll("input").length).toBe(1);           // nothing opened
  });

  it("auto goes in the box like a length; anything else says what it takes", () => {
    act(() => root.render(createElement(Harness, { start: "", auto: true })));
    choose(host.querySelector("select")!, "auto");
    expect(last).toBe("auto");
    expect(host.textContent).toContain("as long as the dialogue needs");
    type(host.querySelector("input")!, "soon");
    expect(host.textContent).toContain("seconds, auto or model");
  });

  it("says what the model renders", () => {
    act(() => root.render(createElement(Harness, { start: "1.62", template: SEEDANCE })));
    expect(host.textContent).toContain("Seedance renders 4 s");
    type(host.querySelector("input")!, "45");
    expect(host.textContent).toContain("30 s: Seedance's longest");
  });
});
