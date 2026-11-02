// Zoom and pan a preview's picture (a still or a video): the wheel zooms in and
// out about the pointer, a drag moves round while zoomed in, a double-click goes
// back to the whole picture. Panes that show two pictures side by side (A and B,
// a take and the cut's) share a group, so both stay framed alike for comparing.
//
// The element itself is transformed (its pane clips it), so the layout that fits
// a picture to its pane is untouched. A drag that moved swallows the click that
// ends it, so a click on a video still plays or pauses it.

import { useEffect } from "react";

export interface ZoomState {
  s: number;
  x: number;
  y: number;
}

const MAX = 10;
const STEP = 1.2;
const WHOLE: ZoomState = { s: 1, x: 0, y: 0 };

const groups = new Map<string, { z: ZoomState; els: Set<HTMLElement> }>();

function groupOf(key: string) {
  let g = groups.get(key);
  if (!g) {
    g = { z: WHOLE, els: new Set() };
    groups.set(key, g);
  }
  return g;
}

/** The zoom after a wheel step at `c` (the pointer, from the element's top left). */
export function zoomAt(z: ZoomState, c: { x: number; y: number }, steps: number, box: { w: number; h: number }): ZoomState {
  const s = Math.min(MAX, Math.max(1, z.s * Math.pow(STEP, steps)));
  if (s === 1) return WHOLE;
  const k = s / z.s;
  return clampPan({ s, x: c.x - (c.x - z.x) * k, y: c.y - (c.y - z.y) * k }, box);
}

/** Kept from showing past the picture's box: its edges never come inside the pane's. */
export function clampPan(z: ZoomState, box: { w: number; h: number }): ZoomState {
  const minX = box.w - box.w * z.s;
  const minY = box.h - box.h * z.s;
  return { s: z.s, x: Math.min(0, Math.max(minX, z.x)), y: Math.min(0, Math.max(minY, z.y)) };
}

function paint(g: { z: ZoomState; els: Set<HTMLElement> }) {
  for (const el of g.els) {
    el.style.transformOrigin = "0 0";
    el.style.transform = g.z.s === 1 ? "" : `translate(${g.z.x}px, ${g.z.y}px) scale(${g.z.s})`;
    el.style.cursor = g.z.s === 1 ? "" : "grab";
  }
}

/** Back to the whole picture (a group's every pane). */
export function resetZoom(group: string): void {
  const g = groups.get(group);
  if (!g) return;
  g.z = WHOLE;
  paint(g);
}

/**
 * Zoom `el` (a preview's <img> or <video>) with the wheel, pan it by dragging.
 * `group` ties panes that zoom together; `resetOn` names the element's events
 * that bring it back to the whole picture (an <img>'s "load": another picture).
 */
export function useZoom(el: HTMLElement | null, group: string, resetOn: string[] = []): void {
  useEffect(() => {
    if (!el) return;
    const g = groupOf(group);
    g.els.add(el);
    paint(g);
    const box = () => ({ w: el.offsetWidth || 1, h: el.offsetHeight || 1 });
    const local = (e: { clientX: number; clientY: number }) => {
      // the element's layout box: where it would be unzoomed
      const r = el.getBoundingClientRect();
      const x0 = r.left - g.z.x, y0 = r.top - g.z.y;
      return { x: e.clientX - x0, y: e.clientY - y0 };
    };
    const wheel = (e: WheelEvent) => {
      e.preventDefault();
      const steps = -Math.sign(e.deltaY) * Math.min(3, Math.max(1, Math.abs(e.deltaY) / 100));
      g.z = zoomAt(g.z, local(e), steps, box());
      paint(g);
    };
    let drag: { x: number; y: number; z: ZoomState; moved: boolean; id: number } | null = null;
    const down = (e: PointerEvent) => {
      if (e.button !== 0 || g.z.s === 1) return;
      e.preventDefault();
      drag = { x: e.clientX, y: e.clientY, z: g.z, moved: false, id: e.pointerId };
      try { el.setPointerCapture(e.pointerId); } catch { /* not capturable */ }
    };
    const move = (e: PointerEvent) => {
      if (!drag) return;
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      if (!drag.moved && Math.hypot(dx, dy) < 3) return;
      drag.moved = true;
      el.style.cursor = "grabbing";
      g.z = clampPan({ s: drag.z.s, x: drag.z.x + dx, y: drag.z.y + dy }, box());
      paint(g);
      for (const o of g.els) if (o !== el) o.style.cursor = "grabbing";
    };
    const up = () => {
      if (!drag) return;
      const moved = drag.moved;
      try { el.releasePointerCapture(drag.id); } catch { /* released */ }
      drag = null;
      paint(g);
      if (moved) {
        // the click this drag ends isn't a click (a video would play or pause)
        const swallow = (c: MouseEvent) => { c.stopPropagation(); c.preventDefault(); };
        window.addEventListener("click", swallow, { capture: true, once: true });
        window.setTimeout(() => window.removeEventListener("click", swallow, { capture: true }), 0);
      }
    };
    const dbl = (e: MouseEvent) => {
      if (g.z.s === 1) return;
      e.stopPropagation();
      resetZoom(group);
    };
    const reset = () => resetZoom(group);
    el.addEventListener("wheel", wheel, { passive: false });
    el.addEventListener("pointerdown", down);
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerup", up);
    el.addEventListener("pointercancel", up);
    el.addEventListener("dblclick", dbl);
    for (const ev of resetOn) el.addEventListener(ev, reset);
    return () => {
      el.removeEventListener("wheel", wheel);
      el.removeEventListener("pointerdown", down);
      el.removeEventListener("pointermove", move);
      el.removeEventListener("pointerup", up);
      el.removeEventListener("pointercancel", up);
      el.removeEventListener("dblclick", dbl);
      for (const ev of resetOn) el.removeEventListener(ev, reset);
      el.style.transform = "";
      el.style.cursor = "";
      g.els.delete(el);
      if (!g.els.size) groups.delete(group);
    };
  }, [el, group, resetOn.join(",")]);
}
