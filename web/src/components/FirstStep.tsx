// What a new cast card does once it's added: its first picture, chosen on the
// form so Add is the one click (Add and generate, Add and tour…) rather than
// Add, then the same card again for the picture. A location that's an angle of
// another place can start from that place's plate: a tour or a 360 of it, the
// results landing as this angle's candidates (tour.tour_source,
// refs._start_of). Importing a picture is the card's own picture-you-have.

import { useState } from "react";
import { generateRef, loadRefs, refLabel } from "../actions";
import { api, host } from "../host";
import { refIdOf, type CardKind } from "../lib/seriesForm";
import { useApp } from "../store";
import { PANO_ENGINE_TITLE, PANO_SIZES } from "./PanoViewer";
import { PICTURE_SIZES } from "./RefsTab";
import { TourMoveFields } from "./TourSection";

export type FirstKind = "none" | "generate" | "import" | "tour" | "pano";

const VERB: Record<FirstKind, string> = {
  none: "Add", generate: "Add and generate", import: "Add and import", tour: "Add and tour", pano: "Add and make 360",
};

export interface FirstStep {
  kind: FirstKind;
  /** the Save button's label */
  verb: string;
  /** what's missing before it can run ("" when nothing) */
  missing: string;
  ui: JSX.Element | null;
  run: (ep: string, id: string) => Promise<void>;
}

/** The first-step choice of a new card of `kind`; `of` is a location's place
 *  it's an angle of; `pic` / `browse` the card's picture-you-have. */
export function useFirstStep({ ep, kind, of, pic, browse, clearPic }: {
  ep: string; kind: CardKind; of: string; pic: string; browse: () => void; clearPic: () => void;
}): FirstStep {
  const refs = useApp((s) => s.refs[ep]);
  const place = of ? refs?.find((r) => r.id === `location:${of}`) : undefined;
  const placePlate = !!place?.exists;
  const pictured = kind !== "voice" && kind !== "group";
  const canStart = kind === "location" && !!of;
  const [chosen, setChosen] = useState<FirstKind | null>(null);
  const kindNow: FirstKind = !pictured ? "none"
    : chosen && (canStart || (chosen !== "tour" && chosen !== "pano")) ? chosen
    : "generate";
  const [count, setCount] = useState(1);
  const [size, setSize] = useState("");
  const [move, setMove] = useState("");
  const [seconds, setSeconds] = useState(6);
  const [engine, setEngine] = useState<"klein" | "qwen">("klein");
  const [psize, setPsize] = useState(PANO_SIZES[0]);

  const missing = kindNow === "import" && !pic ? "Choose the picture to import."
    : kindNow === "tour" && !move.trim() ? "Say (or pick) the camera move."
    : (kindNow === "tour" || kindNow === "pano") && !placePlate ? `${of} has no plate yet to start from.`
    : "";

  const run = async (ep: string, id: string) => {
    const ref = refIdOf(kind, id);
    if (kindNow === "generate") {
      await generateRef({ ref, view: null, count, seed_mode: "auto", seed: null, prompt: null, model: null,
                          loras: null, steps: null, note: "", ...(size ? { size } : {}) });
    } else if (kindNow === "pano") {
      await generateRef({ ref, view: null, count: 1, seed_mode: "new", seed: null, prompt: null, model: null,
                          loras: null, steps: null, note: "360", pano: { engine }, size: psize });
    } else if (kindNow === "tour") {
      try {
        const res = await api().refsTour({ ep, ref, move, seconds, count: 1 });
        host().toast("success", `${refLabel(ref, null)}: tour queued`,
          `from ${of}'s plate, t${res.queued.map((q) => String(q.tour).padStart(2, "0")).join(", t")}: its held frames arrive as candidates when it finishes`);
        await loadRefs(ep);
      } catch (e) {
        host().toast("error", "The tour didn't queue", e instanceof Error ? e.message : String(e));
      }
    }
    // "import" is the card's picture-you-have, taken on save
  };

  if (!pictured) return { kind: "none", verb: VERB.none, missing: "", ui: null, run };

  const opt = (k: FirstKind, label: string, title: string, disabled = false) => (
    <button key={k} className={kindNow === k ? "h3-on" : ""} disabled={disabled} title={title}
      onClick={() => { setChosen(k); if (k !== "import") clearPic(); }}>{label}</button>
  );
  const what = kind === "location" ? "plate" : kind === "character" ? "sheet" : "picture";
  const ui = (
    <div className="h3-col" style={{ gap: 6 }}>
      <span className="h3-small"><b>Then</b> <span className="h3-muted">(once it's added)</span></span>
      <span className="h3-seg h3-wrap">
        {opt("generate", "Generate", `Make its ${what} from the description`)}
        {opt("import", "Import", `A picture you have, as its ${what}`)}
        {canStart && opt("tour", `Tour from ${of}`, placePlate
          ? `A camera move through ${of} from its plate: where the camera holds becomes this angle's candidates`
          : `${of} has no plate yet`, !placePlate)}
        {canStart && opt("pano", `360 of ${of}`, placePlate
          ? `A 360 of ${of}'s plate: aim a camera into it and save the view as this angle`
          : `${of} has no plate yet`, !placePlate)}
        {opt("none", "Nothing yet", "Just add it: its picture can be made later, here or on the Refs tab")}
      </span>
      {kindNow === "generate" && (
        <div className="h3-row h3-wrap" style={{ gap: 6 }}>
          <select className="h3-in" value={count} onChange={(e) => setCount(Number(e.target.value))} title="How many candidates (each with its own seed)">
            {[1, 2, 3, 4].map((n) => <option key={n} value={n}>{n}×</option>)}
          </select>
          <select className="h3-in" value={size} onChange={(e) => setSize(e.target.value)} title="The picture's size (the model snaps it to its own grid)">
            <option value="">its own size</option>
            {PICTURE_SIZES.map((x) => <option key={x} value={x}>{x.replace("x", "×")}</option>)}
          </select>
          <span className="h3-small h3-muted">{kind === "character" ? "All four views, from the design."
            : canStart && placePlate ? `From the description, drawn from ${of}'s plate on an edit model (the same place, seen as it says).`
            : "From the description."}</span>
        </div>
      )}
      {kindNow === "import" && (
        <div className="h3-row" style={{ gap: 4 }}>
          <span className="h3-small h3-mono h3-ell h3-grow" title={pic}>{pic ? pic.split(/[\\/]/).pop() : "none chosen"}</span>
          <button className="h3-btn" onClick={browse}>Choose…</button>
        </div>
      )}
      {kindNow === "tour" && (
        <div className="h3-col" style={{ gap: 4 }}>
          <span className="h3-small h3-muted">From {of}'s plate: where the camera holds becomes this angle's candidates, to pick from.</span>
          <TourMoveFields move={move} setMove={setMove} seconds={seconds} setSeconds={setSeconds} />
        </div>
      )}
      {kindNow === "pano" && (
        <div className="h3-col" style={{ gap: 4 }}>
          <div className="h3-row h3-wrap" style={{ gap: 6 }}>
            <select className="h3-in" value={engine} onChange={(e) => setEngine(e.target.value as "klein" | "qwen")} title={PANO_ENGINE_TITLE}>
              <option value="klein">Klein (outpaint)</option>
              <option value="qwen">Qwen (pano360)</option>
            </select>
            <select className="h3-in" value={psize} onChange={(e) => setPsize(e.target.value)} title="The 360's size: 2048x1024 has a third more detail in every view; 1536x768 is about twice as fast">
              {PANO_SIZES.map((x) => <option key={x} value={x}>{x}</option>)}
            </select>
          </div>
          <span className="h3-small h3-muted">From {of}'s plate. When it's done, open it under 360, aim the camera, and save the view as this angle.</span>
        </div>
      )}
    </div>
  );
  return { kind: kindNow, verb: VERB[kindNow], missing, ui, run };
}
