// A character or a place from a frame (docs/PLAN.md step 13): a frame of a
// take, picked in the viewer, made into a reference -- a new character (cut
// out onto a plain background by an edit model, its other views drawn from
// it), a new place (the people removed), or a new picture for one that
// exists -- through POST /seriesmith/refs/from-frame.

import { useEffect, useMemo, useState } from "react";
import { afterAuthoredWrite, loadRefs, loadTargets, openFrameUse } from "../actions";
import { api, host } from "../host";
import { tn } from "../lib/format";
import { VIEWS } from "../lib/refs";
import { getPath, idProblem, picturePath, refsPrefix, serialize, setPath, slug, type Raw } from "../lib/seriesForm";
import { useApp } from "../store";
import { FloatingWindow } from "./FloatingWindow";
import { Row } from "./ShotForm";

type Make = "character" | "place" | "existing";

const CUT_OUT = (who: string) =>
  `Cut out ${who.trim()} from this picture: the whole figure, standing, in a three-quarter view, on a plain light grey background. ` +
  "Keep their face, hair, build, clothes and colours exactly as they are.";
const EMPTY_PLACE = "Remove every person from this picture. Keep the place exactly as it is: the same layout, light and colours.";

export function FrameUseWindow() {
  const f = useApp((s) => s.frameUse);
  const ep = useApp((s) => s.ep);
  if (!f || !ep) return null;
  return <FrameUse key={`${f.shot}|${f.take}|${f.frame}`} ep={ep} {...f} />;
}

function FrameUse({ ep, shot, take, pass, frame }: { ep: string; shot: string; take: number; pass: string; frame: number | "last" }) {
  const targets = useApp((s) => s.targets);
  const refs = useApp((s) => s.refs[ep]);
  const [make, setMake] = useState<Make>("character");
  const [name, setName] = useState("");
  const [who, setWho] = useState("");
  const [design, setDesign] = useState("");
  const [existing, setExisting] = useState("");
  const [view, setView] = useState("01_threequarter");
  const [views, setViews] = useState(true);
  const [asIs, setAsIs] = useState(false);
  const [model, setModel] = useState("");
  const [busy, setBusy] = useState(false);
  const [raw, setRaw] = useState<Raw | null>(null);
  useEffect(() => {
    void loadTargets();
    void loadRefs(ep);
    api().source(ep, "series").then((d) => setRaw(JSON.parse(d.text) as Raw)).catch(() => setRaw(null));
  }, [ep]);

  const edits = (targets?.targets ?? []).filter((t) => t.kind === "image" && !t.draft && t.capabilities?.mode === "edit");
  const pickable = (refs ?? []).filter((r) => (r.kind === "character" && !r.of) || r.kind === "location");
  const target = existing ? pickable.find((r) => r.id === existing) : undefined;
  const isChar = make === "character" || (make === "existing" && target?.kind === "character");
  const id = make === "place" ? slug(name) : slug(name.replace(/^(the|a|an)\s+/i, ""));
  const problem = make !== "existing" && raw ? (id ? idProblem(raw, id) : "Give it a name.") : "";
  const ready = make === "existing" ? !!existing : !problem && (make === "place" || asIs || !!who.trim());
  const frameLabel = frame === "last" ? "the last frame" : `frame ${frame}`;

  const instruction = useMemo(() => {
    if (asIs) return "";
    if (isChar) return CUT_OUT(who.trim() || (make === "existing" ? (target?.name ?? "the character") : name) || "the person");
    return EMPTY_PLACE;
  }, [asIs, isChar, who, make, target, name]);

  async function go() {
    if (!ready) return;
    setBusy(true);
    try {
      let refId = existing;
      if (make !== "existing") {
        // the new entry first: a character's sheet, a place's plate, where the show keeps them
        const d = await api().source(ep, "series");
        const cur = JSON.parse(d.text) as Raw;
        const prefix = refsPrefix(cur);
        const entry: Raw = make === "character"
          ? { kind: "character", name: name.trim(), design: (design.trim() || who.trim()),
              sheet: picturePath("character", id, prefix) }
          : { description: design.trim() || `the place in ${shot} ${tn(take)}`, plate: picturePath("location", id, prefix) };
        const next = setPath(cur, [make === "character" ? "subjects" : "locations", id], entry);
        const r = await api().putSource({ ep, file: "series", text: serialize(next, d.text), base_hash: d.hash, rebuild: true });
        afterAuthoredWrite(r.build);
        refId = make === "character" ? `subject:${id}` : `location:${id}`;
      }
      const res = await api().refsFromFrame({
        ep, pass, shot, take, frame, ref: refId,
        view: isChar ? (make === "existing" ? view : "01_threequarter") : null,
        instruction, target: model || null,
        views: isChar && (make !== "existing" || views),
        pick: make !== "existing",
      });
      host().toast("success", `From ${shot} ${tn(take)}, ${frameLabel}`, res.edits.length
        ? `${refId}: the frame is in; ${isChar && (make !== "existing" || views) ? "the cut-out, then its other views, are" : "the edit is"} on the queue.`
        : `${refId}: the frame is in${make !== "existing" ? ", picked" : ""}.`);
      void loadRefs(ep);
      openFrameUse(null);
    } catch (e) {
      host().toast("error", "That didn't work", (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const head = (
    <>
      <i className="pi pi-user" />
      <b className="h3-grow">From {shot} {tn(take)}, {frameLabel}</b>
      <button className="h3-btn h3-icon" title="Close" onClick={() => openFrameUse(null)}><i className="pi pi-times" /></button>
    </>
  );
  return (
    <FloatingWindow storageKey="seriesmith.frameuse.rect" head={head} minW={380} minH={300}
      defaultRect={() => ({ x: Math.max(16, Math.round((window.innerWidth - 520) / 2)), y: 80, w: 520, h: Math.min(620, window.innerHeight - 120) })}>
      <div className="h3-col" style={{ padding: 12, gap: 10, overflow: "auto", height: "100%" }}>
        <span className="h3-seg">
          <button className={make === "character" ? "h3-on" : ""} onClick={() => setMake("character")}>A new character</button>
          <button className={make === "place" ? "h3-on" : ""} onClick={() => setMake("place")}>A new place</button>
          <button className={make === "existing" ? "h3-on" : ""} onClick={() => setMake("existing")}>For one there is</button>
        </span>

        {make === "existing" ? (
          <Row label="Which" help="The frame becomes a new candidate of it, beside what it has; you pick which is live.">
            <select className="h3-in" value={existing} onChange={(e) => setExisting(e.target.value)}>
              <option value="">pick one…</option>
              {pickable.map((r) => <option key={r.id} value={r.id}>{r.name}{r.kind === "location" ? " (a place)" : ""}</option>)}
            </select>
          </Row>
        ) : (
          <Row label={make === "character" ? "Name" : "Name of the place"} help={problem && name ? problem : make === "character"
            ? "How the script and the prompts will call them."
            : "A word or two: how clips and the script pick it."}>
            <input className="h3-in" value={name} placeholder={make === "character" ? "Nell" : "harbour"} onChange={(e) => setName(e.target.value)} />
          </Row>
        )}

        {isChar && !asIs && (
          <Row label="Who, in the frame" help="Enough to point them out: what they wear, where they stand.">
            <input className="h3-in" value={who} placeholder="the woman in the red coat, on the left" onChange={(e) => setWho(e.target.value)} />
          </Row>
        )}
        {make !== "existing" && (
          <Row label={make === "character" ? "What they look like" : "What it is"} help={make === "character"
            ? "Said in every shot they're in, beside their picture (empty: from who, above)."
            : "Said in every shot there (empty: the place in this frame)."}>
            <textarea className="h3-in" rows={2} style={{ fontFamily: "inherit", resize: "vertical" }} value={design}
              placeholder={make === "character" ? "a woman in her forties, short auburn hair, a long red wool coat" : "a small harbour at dusk, wooden jetty, calm water"}
              onChange={(e) => setDesign(e.target.value)} />
          </Row>
        )}
        {make === "existing" && isChar && (
          <Row label="Which view" help="The frame, cut out, goes into this one.">
            <select className="h3-in" value={view} onChange={(e) => setView(e.target.value)}>
              {VIEWS.map((v) => <option key={v.view} value={v.view}>{v.label}</option>)}
            </select>
          </Row>
        )}

        {!asIs && (
          <Row label="Edit model" help={isChar
            ? "Cuts them out onto a plain background, then draws their other views from that."
            : "Takes the people out, leaving the place."}>
            <select className="h3-in" value={model} onChange={(e) => setModel(e.target.value)}>
              <option value="">the series' edit model</option>
              {edits.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
            </select>
          </Row>
        )}
        <label className="h3-row h3-small" title="No edit: the frame itself is the picture">
          <input type="checkbox" checked={asIs} onChange={(e) => setAsIs(e.target.checked)} /> Use the frame as it is
        </label>
        {make === "existing" && isChar && (
          <label className="h3-row h3-small">
            <input type="checkbox" checked={views} onChange={(e) => setViews(e.target.checked)} /> Draw its other views from it too (as candidates)
          </label>
        )}
        {make === "character" && (
          <div className="h3-small h3-muted">
            Their four views (three-quarter, side, back, face) are drawn from the cut-out and picked as they come out, then
            stitched into their sheet. Any of them can be made again or picked otherwise in the Refs tab.
          </div>
        )}
        {!asIs && <div className="h3-small h3-muted"><b>Instruction:</b> {instruction}</div>}
      </div>
      <div className="h3-row" style={{ padding: "6px 10px", borderTop: "1px solid var(--h3-border)" }}>
        <span className="h3-small h3-muted h3-grow">{make === "existing" ? "" : getPath(raw ?? {}, ["series", "id"]) ? `Into ${String(getPath(raw ?? {}, ["series", "title"]) ?? "")}'s series config` : ""}</span>
        <button className="h3-btn h3-primary" disabled={!ready || busy} onClick={() => void go()}>
          {busy ? <i className="pi pi-spin pi-spinner" /> : <i className="pi pi-check" />} Make it
        </button>
      </div>
    </FloatingWindow>
  );
}
