// @vitest-environment happy-dom
//
// Zooming a preview (lib/zoom.ts): the wheel zooms about the pointer, a drag looks
// round without showing past the picture, a double-click is the whole picture again,
// panes of one group zoom alike, and a drag doesn't count as the click that plays.
import { act, createElement, useState } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it } from "vitest";
import { clampPan, useZoom, zoomAt } from "../src/lib/zoom";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const BOX = { w: 400, h: 200 };

describe("zoomAt / clampPan", () => {
  it("keeps the point under the pointer where it is", () => {
    const z = zoomAt({ s: 1, x: 0, y: 0 }, { x: 100, y: 50 }, 1, BOX);
    expect(z.s).toBeCloseTo(1.2);
    // the picture's point (100, 50) is still at (100, 50) on screen
    expect(z.x + 100 * z.s).toBeCloseTo(100);
    expect(z.y + 50 * z.s).toBeCloseTo(50);
  });

  it("never goes below the whole picture or past ten times", () => {
    expect(zoomAt({ s: 1.1, x: -5, y: -5 }, { x: 0, y: 0 }, -3, BOX)).toEqual({ s: 1, x: 0, y: 0 });
    let z = { s: 1, x: 0, y: 0 };
    for (let i = 0; i < 40; i++) z = zoomAt(z, { x: 200, y: 100 }, 3, BOX);
    expect(z.s).toBe(10);
  });

  it("doesn't show past the picture's edges", () => {
    expect(clampPan({ s: 2, x: 50, y: 50 }, BOX)).toEqual({ s: 2, x: 0, y: 0 });
    expect(clampPan({ s: 2, x: -1000, y: -1000 }, BOX)).toEqual({ s: 2, x: -400, y: -200 });
  });
});

describe("useZoom", () => {
  it("zooms both panes of a group, pans by dragging, and a double-click is whole again", () => {
    let clicks = 0;
    function Panes() {
      const [a, setA] = useState<HTMLImageElement | null>(null);
      const [b, setB] = useState<HTMLImageElement | null>(null);
      useZoom(a, "test");
      useZoom(b, "test");
      return createElement("div", null,
        createElement("img", { ref: setA, id: "a", onClick: () => clicks++ }),
        createElement("img", { ref: setB, id: "b" }));
    }
    const el = document.createElement("div");
    document.body.appendChild(el);
    const root = createRoot(el);
    act(() => root.render(createElement(Panes)));
    const a = el.querySelector("#a") as HTMLImageElement;
    const b = el.querySelector("#b") as HTMLImageElement;
    Object.defineProperty(a, "offsetWidth", { value: 400 });
    Object.defineProperty(a, "offsetHeight", { value: 200 });
    a.getBoundingClientRect = () => ({ left: 0, top: 0, right: 400, bottom: 200, width: 400, height: 200, x: 0, y: 0, toJSON: () => ({}) });

    // a plain click (no zoom) is a click
    act(() => a.click());
    expect(clicks).toBe(1);

    const wheel = new WheelEvent("wheel", { deltaY: -100, bubbles: true, cancelable: true });
    // happy-dom's WheelEvent leaves the pointer's place out
    Object.defineProperty(wheel, "clientX", { value: 0 });
    Object.defineProperty(wheel, "clientY", { value: 0 });
    act(() => { a.dispatchEvent(wheel); });
    expect(wheel.defaultPrevented).toBe(true);                // the page doesn't scroll
    expect(a.style.transform).toContain("scale(1.2)");
    expect(b.style.transform).toBe(a.style.transform);        // B alike

    // a drag moves it (left: it can't go right of its own edge) and isn't a click
    act(() => {
      a.dispatchEvent(new MouseEvent("pointerdown", { button: 0, clientX: 200, clientY: 100, bubbles: true }));
      a.dispatchEvent(new MouseEvent("pointermove", { clientX: 150, clientY: 100, bubbles: true }));
      a.dispatchEvent(new MouseEvent("pointerup", { clientX: 150, clientY: 100, bubbles: true }));
    });
    expect(a.style.transform).toContain("translate(-50px, 0px)");
    act(() => a.click());
    expect(clicks).toBe(1);

    act(() => { a.dispatchEvent(new MouseEvent("dblclick", { bubbles: true })); });
    expect(a.style.transform).toBe("");
    expect(b.style.transform).toBe("");
    act(() => root.unmount());
    el.remove();
  });
});
