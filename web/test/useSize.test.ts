// @vitest-environment happy-dom
//
// useSize (components/hooks.ts) watches the element when it appears after the first render: the
// cue window first shows a cue that can't be planned (no grid), then a planned one whose grid
// must be measured, or its fit falls to the least zoom (the grid crammed at the left).
import { act, createElement, type RefObject } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, expect, it, vi } from "vitest";
import { useSize } from "../src/components/hooks";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

afterEach(() => vi.unstubAllGlobals());

it("measures an element that appears later", async () => {
  const observers: { cb: ResizeObserverCallback; els: Element[]; off: boolean }[] = [];
  vi.stubGlobal("ResizeObserver", class {
    o: { cb: ResizeObserverCallback; els: Element[]; off: boolean };
    constructor(cb: ResizeObserverCallback) { this.o = { cb, els: [], off: false }; observers.push(this.o); }
    observe(el: Element) { this.o.els.push(el); }
    disconnect() { this.o.off = true; }
    unobserve() {}
  });
  let seen = 0;
  function Box({ on }: { on: boolean }) {
    const [ref, size] = useSize<HTMLDivElement>();
    seen = size.width;
    return on ? createElement("div", { ref: ref as RefObject<HTMLDivElement>, id: "box" }) : createElement("span", null, "no grid");
  }
  const el = document.createElement("div");
  const root = createRoot(el);
  act(() => root.render(createElement(Box, { on: false })));
  expect(observers).toHaveLength(0);
  act(() => root.render(createElement(Box, { on: true })));
  expect(observers).toHaveLength(1);
  expect((observers[0].els[0] as HTMLElement).id).toBe("box");
  act(() => observers[0].cb([{ contentRect: { width: 900, height: 300 } } as ResizeObserverEntry], {} as ResizeObserver));
  expect(seen).toBe(900);
  act(() => root.render(createElement(Box, { on: false })));
  expect(observers[0].off).toBe(true);
  act(() => root.unmount());
});
