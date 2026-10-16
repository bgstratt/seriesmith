// Simple mode (docs/PLAN.md, step 12): the sidebar as one panel for making a
// clip -- pick the model, write what happens, pick who and where by picture
// (or add them), queue some takes -- and the clips so far. A clip is a shot
// of a Simple project (seriesmith/clips.py: Clips, made first, or one of its
// own from + New project), written by lib/simple.ts; its missing pictures are
// made first (POST /seriesmith/clip/queue). Everything else (settings, the
// text windows, the Refs tab) waits in Advanced.

import { useEffect, useMemo, useState } from "react";
import {
  afterAuthoredWrite, isPaidBackend, loadEpisodes, loadRefs, loadTargets, openBrowse, openImageCompare, openSubjectCard,
  openViewer, openWizard, playAll, select, selectEpisode, setSimple,
} from "../actions";
import { api, host } from "../host";
import { pictureOf } from "../lib/pictures";
import { getPath, refsPrefix, serialize, setPath, type Raw } from "../lib/seriesForm";
import { SIZES, type DialogueLine } from "../lib/shotForm";
import {
  IMAGE_NOTES, MODEL_NOTES, QUICK_LENGTHS, clipBlock, durFor, nextClipIds, pictureModel, placeFor, shotsBlock, snapLength,
  withClip,
} from "../lib/simple";
import { QUICK_SIZES, fitSize } from "../lib/size";
import type { TargetTemplate } from "../types";
import { statusKey, store, useApp } from "../store";
import type { Named } from "./Picture";
import { Chips, DialogueRows, PlacePick, Row, type Cast } from "./ShotForm";
import { useSeriesConfig } from "./useSeriesConfig";
import { ModelOptions } from "./Targets";

/** Simple / Advanced, at the top of the sidebar. */
export function ModeSwitch() {
  const simple = useApp((s) => s.simple);
  return (
    <span className="h3-seg" title="Simple: make clips with a few fields. Advanced: everything, series and episodes.">
      <button className={simple ? "h3-on" : ""} onClick={() => setSimple(true)}>Simple</button>
      <button className={simple ? "" : "h3-on"} onClick={() => setSimple(false)}>Advanced</button>
    </span>
  );
}

export function SimplePanel() {
  const ep = useApp((s) => s.ep);
  const config = useApp((s) => s.config);
  const episodes = useApp((s) => s.episodes);
  const [clipsEp, setClipsEp] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const isSimple = (e: string | null) => !!e && (e === clipsEp || !!episodes?.some((x) => x.ep === e && x.simple));

  // the Clips project, made the first time; opened unless a Simple project is
  useEffect(() => {
    let gone = false;
    api().clipsEnsure()
      .then(async (r) => {
        if (gone) return;
        setClipsEp(r.ep);
        if (r.made || !store.get().episodes) await loadEpisodes();
        const cur = store.get().ep;
        const keep = cur && (cur === r.ep || (store.get().episodes ?? []).some((x) => x.ep === cur && x.simple));
        if (!keep) selectEpisode(r.ep);
      })
      .catch((e) => !gone && setError((e as Error).message));
    return () => { gone = true; };
  }, [config?.roots?.join("|")]);
  // an episode of Advanced's opened meanwhile: back to Clips
  useEffect(() => {
    if (clipsEp && episodes && ep && !isSimple(ep)) selectEpisode(clipsEp);
  }, [ep, clipsEp, episodes]);

  const head = (
    <div className="h3-bar" style={{ justifyContent: "space-between" }}>
      <span className="h3-title">Make</span>
      <ModeSwitch />
    </div>
  );
  if (error) {
    return (
      <div className="h3-surface">
        {head}
        <div className="h3-pad h3-col" style={{ gap: 8 }}>
          <div className="h3-note h3-small">{error}</div>
          <div><button className="h3-btn" onClick={() => openBrowse({ purpose: "roots" })}>Project folders…</button></div>
        </div>
      </div>
    );
  }
  if (!clipsEp || !ep || !isSimple(ep)) {
    return <div className="h3-surface">{head}<div className="h3-pad h3-muted h3-small">Opening your clips…</div></div>;
  }
  return (
    <div className="h3-surface">
      {head}
      <ClipMaker key={ep} ep={ep} root={config?.roots?.[0] ?? null} />
    </div>
  );
}

/** Which Simple project the clips go in: Clips, or one of its own (+ New project). */
function ProjectPick({ ep, root }: { ep: string; root: string | null }) {
  const episodes = useApp((s) => s.episodes);
  const [name, setName] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const mine = (episodes ?? []).filter((e) => e.simple || e.ep === ep);
  async function make() {
    if (!name?.trim()) return;
    setBusy(true);
    try {
      const r = await api().clipsNew(name.trim(), root);
      await loadEpisodes();
      selectEpisode(r.ep);
      setName(null);
    } catch (e) {
      host().toast("error", "The project wasn't made", (e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (name !== null) {
    return (
      <Row label="New project" help="A folder of its own for its clips, people and places.">
        <span className="h3-row" style={{ gap: 4 }}>
          <input className="h3-in h3-grow" autoFocus value={name} placeholder="Storm at the lighthouse"
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") void make(); if (e.key === "Escape") setName(null); }} />
          <button className="h3-btn h3-primary" disabled={busy || !name.trim()} onClick={() => void make()}>Make</button>
          <button className="h3-btn" disabled={busy} onClick={() => setName(null)}>Cancel</button>
        </span>
      </Row>
    );
  }
  return (
    <Row label="Project" help="">
      <span className="h3-row" style={{ gap: 4 }}>
        <select className="h3-in h3-grow" value={ep} onChange={(e) => selectEpisode(e.target.value)}>
          {mine.map((e) => <option key={e.ep} value={e.ep}>{e.series || e.title || e.name}</option>)}
        </select>
        <button className="h3-btn" disabled={!root} title="A project of its own: its clips, people and places kept together"
          onClick={() => setName("")}>+ New project</button>
      </span>
    </Row>
  );
}

/** A length in seconds: typed, or one of the quick ones; under it, what the
 * model renders (its frame grid rounds it up, and caps it at its longest). */
function LengthInput({ value, onChange, template, fps, auto, model, short }: {
  value: string; onChange: (v: string) => void; template: TargetTemplate | undefined; fps: number;
  auto?: boolean; model?: boolean; short?: string;
}) {
  const snap = snapLength(value, template, fps);
  const note = !snap ? "" : snap.capped ? `${snap.seconds} s, ${short ?? "the model"}'s longest`
    : Math.abs(snap.seconds - Number(value)) > 0.005 ? `renders ${snap.seconds} s` : "";
  return (
    <span className="h3-col" style={{ gap: 1 }}>
      <span className="h3-row" style={{ gap: 3 }}>
        <input className="h3-in" style={{ width: 70 }} list="sm-lengths" value={value} inputMode="decimal"
          title={"Seconds: type any length, or pick one" + (auto ? "; auto fits the dialogue" : "")}
          onChange={(e) => onChange(e.target.value)} />
        <span className="h3-small h3-muted">s</span>
      </span>
      <datalist id="sm-lengths">
        {QUICK_LENGTHS.map((v) => <option key={v} value={v} />)}
        {auto && <option value="auto">as long as the dialogue needs</option>}
        {model && <option value="model">the model chooses</option>}
      </datalist>
      {note && <span className="h3-small h3-muted">{note}</span>}
    </span>
  );
}

/** The project's picture size for the pass on (`series` for final, `proxy`
 * for proxy, in its series config): width and height, or a quick size. It is
 * written as the project's model takes it; under it, what the clip's model
 * renders when that differs. */
function SizeRow({ raw, pass, status, seriesTemplate, template, short, save }: {
  raw: Raw; pass: string; status: { width: number | null; height: number | null } | null;
  seriesTemplate: TargetTemplate | undefined; template: TargetTemplate | undefined; short: string;
  save: (w: number, h: number) => Promise<boolean>;
}) {
  const block = pass === "final" ? "series" : "proxy";
  const cw = Number(getPath(raw, [block, "width"])) || status?.width || 0;
  const ch = Number(getPath(raw, [block, "height"])) || status?.height || 0;
  const [w, setW] = useState(cw ? String(cw) : "");
  const [h, setH] = useState(ch ? String(ch) : "");
  const [busy, setBusy] = useState(false);
  useEffect(() => { setW(cw ? String(cw) : ""); setH(ch ? String(ch) : ""); }, [cw, ch]);
  const nw = Math.round(Number(w)), nh = Math.round(Number(h));
  const valid = nw >= 64 && nh >= 64 && nw <= 8192 && nh <= 8192;
  const [sw, sh] = valid ? fitSize(nw, nh, seriesTemplate) : [0, 0];
  const [rw, rh] = valid ? fitSize(sw, sh, template) : [0, 0];
  const dirty = valid && (sw !== cw || sh !== ch);
  async function set() {
    setBusy(true);
    try { await save(sw, sh); } finally { setBusy(false); }
  }
  const quick = (q: { width: number; height: number }) => {
    const tall = nh > nw;
    setW(String(tall ? q.height : q.width));
    setH(String(tall ? q.width : q.height));
  };
  const notes = [
    valid && (sw !== nw || sh !== nh) ? `the project's model takes ${sw}×${sh}` : "",
    valid && template && (rw !== sw || rh !== sh) ? `${short} renders ${rw}×${rh}` : "",
  ].filter(Boolean);
  return (
    <Row label={`Size (${pass})`} help="">
      <span className="h3-col" style={{ gap: 2 }}>
        <span className="h3-row h3-wrap" style={{ gap: 4 }}>
          <input className="h3-in" style={{ width: 64 }} inputMode="numeric" value={w} onChange={(e) => setW(e.target.value)} title="Width, pixels" />
          <span className="h3-small">×</span>
          <input className="h3-in" style={{ width: 64 }} inputMode="numeric" value={h} onChange={(e) => setH(e.target.value)} title="Height, pixels" />
          <button className="h3-link" title="Swap: landscape / portrait" onClick={() => { setW(h); setH(w); }}>⇄</button>
          {QUICK_SIZES.map((q) => <button key={q.label} className="h3-btn" onClick={() => quick(q)}>{q.label}</button>)}
          {dirty && (
            <button className="h3-btn h3-primary" disabled={busy} onClick={() => void set()}
              title={`Every clip of this project renders at it (${pass})`}>Set</button>
          )}
        </span>
        {notes.length > 0 && <span className="h3-small h3-muted">{notes.join("; ")}</span>}
      </span>
    </Row>
  );
}

type Mode = "clip" | "picture" | "shots";
interface ShotRow { prompt: string; size: string; dur: string }

function ClipMaker({ ep, root }: { ep: string; root: string | null }) {
  const pass = useApp((s) => s.pass);
  const targets = useApp((s) => s.targets);
  const backend = useApp((s) => s.renderBackend);
  const refs = useApp((s) => s.refs[ep]);
  const sourceN = useApp((s) => s.sourceN);
  const sc = useSeriesConfig(ep);
  useEffect(() => {
    void loadTargets();
    void loadRefs(ep);
  }, [ep]);
  useEffect(() => {
    if (sourceN) void sc.reload();                 // a card saved a new character or place
  }, [sourceN]);

  const raw = sc.base;
  const seriesTarget = (raw && (getPath(raw, ["series", "target"]) as string)) || targets?.default?.video || "minimax_h3_ref2va";
  const imageDefault = (raw && (getPath(raw, ["refs", "target"]) as string)) || targets?.default?.image || "krea2";
  const video = (targets?.targets ?? []).filter((t) => t.kind === "video" && !t.draft);
  const images = (targets?.targets ?? []).filter((t) => t.kind === "image" && !t.draft && pictureModel(t.capabilities?.mode));
  const [mode, setMode] = useState<Mode>("clip");
  const [model, setModel] = useState("");
  const [imageModel, setImageModel] = useState("");
  const [prompt, setPrompt] = useState("");
  const [rows, setRows] = useState<ShotRow[]>([{ prompt: "", size: "wide", dur: "3" }, { prompt: "", size: "medium", dur: "3" }]);
  const [who, setWho] = useState<string[]>([]);
  const [where, setWhere] = useState("");
  const [placeText, setPlaceText] = useState("");
  // a new place: words only (renders at once), or a picture made first
  const [placePicture, setPlacePicture] = useState(false);
  const [dialogue, setDialogue] = useState<DialogueLine[]>([]);
  const [size, setSize] = useState("medium");
  const [dur, setDur] = useState("3");
  const [takes, setTakes] = useState(1);
  const [busy, setBusy] = useState(false);
  const target = model || seriesTarget;
  const imageTarget = imageModel || imageDefault;
  const picture = mode === "picture";
  const status = useApp((s) => s.status[statusKey(ep, s.pass)]);
  const fps = Number(raw && getPath(raw, ["series", "fps"])) || 24;
  const all = targets?.targets ?? [];
  const tpl = all.find((x) => x.id === target)?.template;
  const seriesTpl = all.find((x) => x.id === seriesTarget)?.template;

  const cast = useMemo(() => {
    const subj = (getPath(raw ?? {}, ["subjects"]) ?? {}) as Record<string, Raw>;
    const chars: Cast[] = Object.entries(subj)
      .filter(([, e]) => (typeof e?.kind === "string" ? e.kind : "character") === "character")
      .map(([id, e]) => ({ id, name: typeof e?.name === "string" ? e.name : id, kind: "character", onScreen: true,
        pic: pictureOf(raw, refs, "subjects", id) }));
    const places: Named[] = Object.keys((getPath(raw ?? {}, ["locations"]) ?? {}) as object)
      .filter((id) => !/^c\d+_place$/.test(id) || id === where)
      .map((id) => ({ id, name: id.replace(/_/g, " "), pic: pictureOf(raw, refs, "locations", id) }));
    return { chars, places };
  }, [raw, refs, where]);

  const filled = mode === "shots" ? rows.filter((r) => r.prompt.trim()) : [];
  const ready = mode === "shots" ? filled.length > 0 : !!prompt.trim();
  const runs = mode === "shots" ? filled.length * takes : takes;
  const paid = isPaidBackend(backend) || (picture ? imageTarget === "krea_2_router" : target === "seedance_2_5");

  async function queue() {
    if (!raw || !ready) return;
    if (paid && !confirm(`${runs} ${picture ? "picture" : "take"}${runs > 1 ? "s" : ""} on a paid backend (${backend || "Router"}): each is billed to your Comfy account. Queue?`)) return;
    setBusy(true);
    try {
      // the script: the clip's ids after the ones there
      const script = await api().source(ep, "script");
      const { seq, shot } = nextClipIds(script.text);
      const base = { who, where, placeText, target, dialogue: mode === "clip" ? dialogue : [] };
      const specs = mode === "shots"
        ? filled.map((r) => ({ ...base, prompt: r.prompt, size: r.size, dur: durFor(r.dur, tpl, fps) }))
        : [{ ...base, prompt, size, dur: durFor(dur, tpl, fps), still: picture }];
      let location = where;
      if (!location) {
        // a place of the clip's own: words only, or its plate made first
        const series = await api().source(ep, "series");
        const cur = JSON.parse(series.text) as Raw;
        const p = placeFor(shot, specs[0], refsPrefix(cur), placePicture);
        await api().putSource({ ep, file: "series", text: serialize(setPath(cur, ["locations", p.id], p.entry), series.text),
                                base_hash: series.hash, rebuild: false });
        location = p.id;
      }
      const { ids, lines } = mode === "shots"
        ? shotsBlock(seq, shot, location, specs, seriesTarget)
        : { ids: [shot], lines: clipBlock(seq, shot, location, specs[0], seriesTarget) };
      const r = await api().putSource({ ep, file: "script", text: withClip(script.text, lines), base_hash: script.hash, rebuild: true });
      afterAuthoredWrite(r.build);
      const bad = r.check.errors.find((m) => m.line == null || ids.some((i) => m.message.includes(i)) || m.message.includes(seq));
      if (bad) {
        host().toast("error", `${shot} was written, but it won't build`, bad.message);
        return;
      }
      let first = true;
      for (const id of ids) {
        const q = await api().clipQueue({ ep, shot: id, pass, takes, backend: backend || null,
                                          ...(picture ? { still: true, image_target: imageTarget } : {}) });
        if (first && q.step) {
          host().toast("success", `${shot} queued`, `Its picture${q.refs.length === 1 ? " is" : "s are"} made first, then the rest.`);
          first = false;
        }
      }
      if (first) host().toast("success", `${shot} queued`, picture
        ? `${takes} picture${takes > 1 ? "s" : ""} on the way.`
        : `${runs} take${runs > 1 ? "s" : ""} on the way.`);
      select(ids[0], null);
      void loadRefs(ep);                           // a picture's keyframe, for the list
      setPrompt("");
      setRows((rs) => rs.map((x) => ({ ...x, prompt: "" })));
      setDialogue([]);
      setPlaceText("");
    } catch (e) {
      host().toast("error", "The clip wasn't queued", (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const t = video.find((x) => x.id === target);
  const it = images.find((x) => x.id === imageTarget);
  const what = picture ? "picture" : "take";
  return (
    <div className="h3-col" style={{ gap: 10, padding: 10, overflow: "auto", minHeight: 0, flex: 1 }}>
      <ProjectPick ep={ep} root={root} />
      <div className="h3-row h3-wrap" style={{ gap: 6 }}>
        <span className="h3-seg" title="What you're making">
          <button className={mode === "clip" ? "h3-on" : ""} onClick={() => setMode("clip")}>A clip</button>
          <button className={picture ? "h3-on" : ""} onClick={() => setMode("picture")}>A picture</button>
          <button className={mode === "shots" ? "h3-on" : ""} onClick={() => setMode("shots")} title="A few shots, cut together and played as one clip">Several shots</button>
          <button title="A series with episodes: the step-by-step wizard (then Advanced)" disabled={!root}
            onClick={() => { if (root) { setSimple(false); openWizard({ parent: root, newSeries: true }); } }}>A series…</button>
        </span>
      </div>

      {picture ? (
        <Row label="Model" help={(IMAGE_NOTES[imageTarget] ?? it?.label ?? "") + (it?.readiness?.status === "not_ready" ? " (its files aren't all installed)" : "")}>
          <select className="h3-in" value={imageTarget} onChange={(e) => setImageModel(e.target.value === imageDefault ? "" : e.target.value)}>
            <ModelOptions targets={images} text={(v) => `${v.label}${v.id === imageDefault ? " (default)" : ""}`} />
          </select>
        </Row>
      ) : (
        <Row label="Model" help={(MODEL_NOTES[target] ?? t?.label ?? "") + (t?.readiness?.status === "not_ready" ? " (its files aren't all installed)" : "")}>
          <select className="h3-in" value={target} onChange={(e) => setModel(e.target.value === seriesTarget ? "" : e.target.value)}>
            <ModelOptions targets={video} text={(v) => `${v.label}${v.id === seriesTarget ? " (default)" : ""}`} />
          </select>
        </Row>
      )}

      {mode === "shots" ? (
        <Row label="The shots" help="In order: each is a cut. Say what we see in each; the people and the place are below, for all of them.">
          <div className="h3-col" style={{ gap: 6 }}>
            {rows.map((r, i) => (
              <div key={i} className="h3-col" style={{ gap: 3, borderLeft: "2px solid var(--h3-border)", paddingLeft: 6 }}>
                <div className="h3-row" style={{ gap: 4 }}>
                  <b className="h3-small">{i + 1}</b>
                  <select className="h3-in" value={r.size} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, size: e.target.value } : x)))}>
                    {SIZES.map((s) => <option key={s.value} value={s.value}>{s.label.split(" — ")[0]}</option>)}
                  </select>
                  <LengthInput value={r.dur} template={tpl} fps={fps} short={t?.short}
                    onChange={(v) => setRows(rows.map((x, j) => (j === i ? { ...x, dur: v } : x)))} />
                  <span className="h3-grow" />
                  {rows.length > 1 && <button className="h3-link" title="Remove this shot" onClick={() => setRows(rows.filter((_, j) => j !== i))}>×</button>}
                </div>
                <textarea className="h3-in" rows={2} style={{ fontFamily: "inherit", resize: "vertical" }} value={r.prompt}
                  placeholder={i === 0 ? "Wide: the keeper climbs the cliff path toward the lighthouse." : "Close: his hand on the cold iron door."}
                  onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, prompt: e.target.value } : x)))} />
              </div>
            ))}
            {rows.length < 8 && <div><button className="h3-btn" onClick={() => setRows([...rows, { prompt: "", size: "medium", dur: "3" }])}>+ Shot</button></div>}
          </div>
        </Row>
      ) : (
        <Row label={picture ? "What's in it" : "What happens"} help={picture
          ? "The picture, as you'd describe it to a photographer: who, where, the light."
          : "What we see, as you'd describe it to a camera crew: who does what, where, in what light."}>
          <textarea className="h3-in" rows={4} style={{ fontFamily: "inherit", resize: "vertical" }} value={prompt}
            placeholder={picture ? "A lighthouse keeper at the top of the stairs, lantern raised, storm clouds through the window."
              : "A lighthouse keeper climbs the spiral stairs with a lantern as the storm comes in."}
            onChange={(e) => setPrompt(e.target.value)} />
        </Row>
      )}

      <Row label="Who's in it" help={picture && it?.capabilities?.mode !== "edit"
        ? "Optional. This model works from words: they're described, not drawn from their pictures (an edit model draws from those)."
        : "Optional. Add someone with a picture you have, or a description to draw them from."}>
        <Chips ep={ep} value={who} options={cast.chars} onChange={setWho}
          add={() => openSubjectCard({ kind: "character", id: null })} addLabel="+ Someone" />
      </Row>

      <Row label="Where" help={where ? "That place's picture is the background." : placePicture
        ? "Said in words (empty: from what happens); a picture of it is made first, and the clip renders after."
        : "Said in words (empty: from what happens). With no picture, each clip imagines it its own way."}>
        <div className="h3-col" style={{ gap: 4 }}>
          <span className="h3-row h3-wrap" style={{ gap: 4 }}>
            <PlacePick ep={ep} value={where} places={cast.places} empty="a new place" onChange={setWhere} />
            {where && (
              <button className="h3-btn" title="Its pictures: make it again, edit it, or take a Tour through it for new angles"
                onClick={() => openSubjectCard({ kind: "location", id: where })}>Open</button>
            )}
            <button className="h3-btn" onClick={() => openSubjectCard({ kind: "location", id: null })}>+ Place</button>
          </span>
          {!where && (
            <>
              <input className="h3-in" value={placeText} placeholder="a stone lighthouse on a cliff at dusk, storm clouds"
                onChange={(e) => setPlaceText(e.target.value)} />
              <label className="h3-row h3-small" title="Slower to start, but the place then looks the same in every clip that picks it">
                <input type="checkbox" checked={placePicture} onChange={(e) => setPlacePicture(e.target.checked)} />
                Make a picture of it first (so it looks the same each time)
              </label>
            </>
          )}
        </div>
      </Row>

      {mode === "clip" && who.length > 0 && (
        <Row label="What's said" help="Optional: a line, under who says it.">
          <DialogueRows rows={dialogue} speakers={cast.chars.filter((c) => who.includes(c.id))} onChange={setDialogue} />
        </Row>
      )}

      <div className="h3-row h3-wrap" style={{ gap: 10 }}>
        {mode !== "shots" && (
          <Row label="Framing" help="">
            <select className="h3-in" value={size} onChange={(e) => setSize(e.target.value)}>
              {SIZES.map((s) => <option key={s.value} value={s.value}>{s.label.split(" — ")[0]}</option>)}
            </select>
          </Row>
        )}
        {mode === "clip" && (
          <Row label="Length" help="">
            <LengthInput value={dur} onChange={setDur} template={tpl} fps={fps} short={t?.short} auto model={target.startsWith("ltx2")} />
          </Row>
        )}
        <Row label={picture ? "Pictures" : mode === "shots" ? "Takes of each" : "Takes"} help="">
          <select className="h3-in" value={takes} onChange={(e) => setTakes(Number(e.target.value))}>
            {[1, 2, 3, 4].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </Row>
      </div>

      {raw && (
        <SizeRow raw={raw} pass={pass} status={status ? { width: status.width, height: status.height } : null}
          seriesTemplate={seriesTpl} template={picture ? undefined : tpl} short={t?.short ?? target}
          save={(w, h) => {
            const block = pass === "final" ? "series" : "proxy";
            return sc.save(setPath(setPath(raw, [block, "width"], w), [block, "height"], h), "the size");
          }} />
      )}

      <button className="h3-btn h3-primary" style={{ alignSelf: "flex-start" }} disabled={busy || !ready || !raw} onClick={() => void queue()}>
        {busy ? <i className="pi pi-spin pi-spinner" /> : <i className="pi pi-play" />} Queue {runs} {what}{runs > 1 ? "s" : ""}
      </button>

      <ClipList ep={ep} pass={pass} />
    </div>
  );
}

/** The clips made so far, newest first: a picture by its picture, several
 * shots as one (played together), a clip by its newest take. */
function ClipList({ ep, pass }: { ep: string; pass: string }) {
  const st = useApp((s) => s.status[statusKey(ep, s.pass)]);
  const refs = useApp((s) => s.refs[ep]);
  const shots = (st?.shots ?? []).filter((s) => !s.orphan);
  if (!shots.length) return <div className="h3-small h3-muted">Your clips appear here.</div>;
  // one entry per clip (its sequence), newest first
  const groups: { seq: string; shots: typeof shots }[] = [];
  for (const s of shots) {
    const key = s.sequence ?? s.shot;
    const g = groups.find((x) => x.seq === key);
    if (g) g.shots.push(s);
    else groups.push({ seq: key, shots: [s] });
  }
  groups.reverse();
  return (
    <div className="h3-col" style={{ gap: 6 }}>
      <span className="h3-small"><b>Your clips</b> <span className="h3-muted">{pass}</span></span>
      {groups.map((g) => {
        const first = g.shots[0];
        const ts = g.shots.flatMap((s) => s.takes ?? []);
        const kf = refs?.find((r) => r.id === `shot:${first.shot}:first`);
        const pics = (kf?.takes ?? []).filter((x) => x.status === "ok" && x.image);
        const isPicture = g.shots.length === 1 && !ts.length && !!kf && (kf.takes ?? []).length > 0;
        const lastVideo = (first.takes ?? [])[(first.takes ?? []).length - 1];
        const thumb = isPicture ? (pics[pics.length - 1]?.image ?? (kf?.exists ? kf.path : null)) : lastVideo?.thumb ?? null;
        const ready = isPicture ? pics.length : ts.filter((x) => x.status === "ok").length;
        const busy = isPicture ? (kf?.takes ?? []).filter((x) => x.status === "queued").length : ts.filter((x) => x.status === "queued").length;
        const label = g.shots.length > 1 ? `${first.shot.replace(/a$/, "")} · ${g.shots.length} shots` : first.shot;
        const play = () => {
          if (isPicture && kf) {
            const last = pics[pics.length - 1];
            if (last) openImageCompare(kf.id, null, last.take);
            return;
          }
          if (g.shots.length > 1) {
            playAll(first.shot, g.shots.map((s) => s.shot));
            return;
          }
          select(first.shot, lastVideo?.take ?? null);
          if (lastVideo && lastVideo.status === "ok") openViewer(first.shot, lastVideo.take, null, "single");
        };
        return (
          <button key={g.seq} className="h3-btn" style={{ justifyContent: "flex-start", gap: 8, height: "auto", padding: 4 }}
            title={isPicture ? "Open its pictures" : g.shots.length > 1 ? "Play its shots, cut together" : "Play its newest take"}
            onClick={play}>
            <span style={{ width: 72, height: 40, flex: "none", background: "var(--h3-bg3)", borderRadius: 3, overflow: "hidden" }}>
              {thumb && <img src={api().fileUrl(ep, thumb)} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} />}
            </span>
            <span className="h3-col" style={{ alignItems: "flex-start", gap: 1 }}>
              <b className="h3-small">{label}{isPicture ? <span className="h3-muted"> · picture</span> : null}</b>
              <span className="h3-small h3-muted">
                {ready ? `${ready} ${isPicture ? "picture" : "take"}${ready > 1 ? "s" : ""}` : "nothing yet"}{busy ? ` · ${busy} on the way` : ""}
                {!ts.length && !isPicture && (first.missing_refs?.length ?? 0) > 0 ? " · pictures first" : ""}
                {ts.some((x) => x.status === "failed") ? " · some failed" : ""}
              </span>
            </span>
          </button>
        );
      })}
    </div>
  );
}
