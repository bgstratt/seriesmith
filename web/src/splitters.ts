// The standalone page's two splitters: the sidebar's right edge and the
// timeline's top edge can be dragged (double-click puts one back). The sizes
// are this browser's own (localStorage), and the narrow, stacked layout has no
// splitters: its sizes come from the page's CSS.

const KEY = "seriesmith.layout";
const NARROW = 760;            // the page's own breakpoint (standalone.html)
const TOP = 40;                // the top bar's height
const SIDE_MIN = 240;
const VIEW_MIN = 320;          // the viewer keeps at least this much width
const TIME_MIN = 80;
const VIEW_MIN_H = 160;        // and this much height

interface Layout { side: number | null; time: number | null }

function load(): Layout {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) ?? "null") as Partial<Layout> | null;
    return { side: typeof v?.side === "number" ? v.side : null, time: typeof v?.time === "number" ? v.time : null };
  } catch {
    return { side: null, time: null };
  }
}

function save(l: Layout) {
  try {
    localStorage.setItem(KEY, JSON.stringify(l));
  } catch {
    /* private window: the sizes last until reload */
  }
}

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

export function installSplitters(page: HTMLElement) {
  const side = document.getElementById("sm-side");
  const time = document.getElementById("sm-time");
  if (!side || !time) return;
  let layout = load();
  page.style.position = "relative";

  const handle = (cls: "col" | "row", title: string) => {
    const h = document.createElement("div");
    h.className = `sm-split sm-split-${cls}`;
    h.title = title;
    Object.assign(h.style, {
      position: "absolute", zIndex: "5", touchAction: "none",
      cursor: cls === "col" ? "col-resize" : "row-resize",
    } as Partial<CSSStyleDeclaration>);
    page.appendChild(h);
    return h;
  };
  const col = handle("col", "Drag to resize the sidebar (double-click: back to its default)");
  const row = handle("row", "Drag to resize the timeline (double-click: back to its default)");

  const apply = () => {
    const narrow = window.innerWidth <= NARROW;
    col.style.display = row.style.display = narrow ? "none" : "block";
    if (narrow) {
      page.style.gridTemplateColumns = page.style.gridTemplateRows = "";
      return;
    }
    const W = window.innerWidth, H = window.innerHeight;
    const s = layout.side == null ? null : clamp(layout.side, SIDE_MIN, W - VIEW_MIN);
    const t = layout.time == null ? null : clamp(layout.time, TIME_MIN, H - TOP - VIEW_MIN_H);
    page.style.gridTemplateColumns = s == null ? "" : `${s}px minmax(0, 1fr)`;
    page.style.gridTemplateRows = t == null ? "" : `${TOP}px minmax(0, 1fr) ${t}px`;
    // the handles sit on the edges as laid out
    const sr = side.getBoundingClientRect(), tr = time.getBoundingClientRect(), pr = page.getBoundingClientRect();
    Object.assign(col.style, { left: `${sr.right - pr.left - 3}px`, top: `${TOP}px`, width: "6px", height: `${Math.max(0, tr.top - pr.top - TOP)}px` });
    Object.assign(row.style, { left: "0px", top: `${tr.top - pr.top - 3}px`, width: "100%", height: "6px" });
  };

  const drag = (h: HTMLElement, move: (e: PointerEvent) => void) => {
    h.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      h.setPointerCapture(e.pointerId);
      h.classList.add("on");
      document.body.style.userSelect = "none";
      const onMove = (ev: PointerEvent) => { move(ev); apply(); };
      const onUp = () => {
        h.removeEventListener("pointermove", onMove);
        h.removeEventListener("pointerup", onUp);
        h.removeEventListener("pointercancel", onUp);
        h.classList.remove("on");
        document.body.style.userSelect = "";
        save(layout);
        window.dispatchEvent(new Event("resize"));   // anything measuring itself measures again
      };
      h.addEventListener("pointermove", onMove);
      h.addEventListener("pointerup", onUp);
      h.addEventListener("pointercancel", onUp);
    });
  };
  drag(col, (e) => { layout = { ...layout, side: Math.round(e.clientX) }; });
  drag(row, (e) => { layout = { ...layout, time: Math.round(window.innerHeight - e.clientY) }; });
  col.addEventListener("dblclick", () => { layout = { ...layout, side: null }; save(layout); apply(); });
  row.addEventListener("dblclick", () => { layout = { ...layout, time: null }; save(layout); apply(); });

  window.addEventListener("resize", apply);
  if (typeof ResizeObserver !== "undefined") new ResizeObserver(apply).observe(page);
  apply();
}
