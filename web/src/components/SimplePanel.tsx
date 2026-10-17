// Simple mode (docs/PLAN.md, step 12): the sidebar as one panel for making a
// clip -- pick the model, write what happens, pick who and where by picture
// (or add them), queue some takes -- and the clips so far. A clip is a shot
// of a Simple project (seriesmith/clips.py: Clips, made first, or one of its
// own from + New project), written by lib/simple.ts; its missing pictures are
// made first (POST /seriesmith/clip/queue). Everything else (settings, the
// text windows, the Refs tab) waits in Advanced.

import { useEffect, useMemo, useRef, useState } from "react";
import {
  afterAuthoredWrite, isPaidBackend, loadEpisodes, loadRefs, loadTargets, openBrowse, openImageCompare, openSubjectCard,
  openViewer, openWizard, playAll, select, selectEpisode, setSimple,
} from "../actions";
import { api, host } from "../host";
import { pictureOf } from "../lib/pictures";
import { getPath, refsPrefix, serialize, setPath, type Raw } from "../lib/seriesForm";
import { SIZES, type DialogueLine } from "../lib/shotForm";
import {
  IMAGE_NOTES, MODEL_NOTES, clipBlock, clipOwnSize, durFor, nextClipIds, pictureModel, placeFor, shotsBlock, withClip,
} from "../lib/simple";
import { COMMON_SIZES, fitSize } from "../lib/size";
import type { TargetTemplate } from "../types";
import { statusKey, store, useApp } from "../store";
import type { Named } from "./Picture";
import { LengthPicker } from "./LengthPicker";
import { PickMenu } from "./PickMenu";
import { ADD_NEW, PanelHead, TitleSelect } from "./ProjectHead";
import { Chips, DialogueRows, PlacePick, type Cast } from "./ShotForm";
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
  // once Simple is showing a project: an episode of a series opened meanwhile
  // (Project folders, the Refs tab's dropdown) is Advanced's, so switch to it
  const settled = useRef(false);
  useEffect(() => {
    if (!clipsEp || !episodes || !ep) return;
    if (isSimple(ep)) settled.current = true;
    else if (settled.current) setSimple(false);
  }, [ep, clipsEp, episodes]);

  const ready = !error && !!clipsEp && !!ep && isSimple(ep);
  const root = config?.roots?.[0] ?? null;
  return (
    <div className="h3-surface sm-simple">
      {ready ? <ProjectHead ep={ep!} /> : (
        <PanelHead side={<ModeSwitch />}><span className="sm-project-name">Make</span></PanelHead>
      )}
      {error ? (
        <div className="sm-body">
          <div className="h3-note h3-small">{error}</div>
          <div><button className="h3-btn" onClick={() => openBrowse({ purpose: "roots" })}>Project folders…</button></div>
        </div>
      ) : !ready ? (
        <div className="sm-body h3-muted">Opening your clips…</div>
      ) : (
        <ClipMaker key={ep} ep={ep!} root={root} />
      )}
    </div>
  );
}

/** The panel's head: the project as its title, a dropdown of Simple's
 * projects over it, Simple / Advanced. "Browse and add new…" opens Project
 * folders, where a project is made (New project…), opened or added. */
function ProjectHead({ ep }: { ep: string }) {
  const episodes = useApp((s) => s.episodes);
  const mine = (episodes ?? []).filter((e) => e.simple || e.ep === ep);
  const label = (e: (typeof mine)[number]) => e.series || e.title || e.name;
  const cur = mine.find((e) => e.ep === ep);
  return (
    <PanelHead side={<ModeSwitch />}>
      <TitleSelect kicker="Project" label="Project" name={cur ? label(cur) : "Clips"} value={ep}
        options={mine.map((e) => ({ value: e.ep, label: label(e), title: e.ep }))}
        onPick={(v) => (v === ADD_NEW ? openBrowse({ purpose: "roots" }) : selectEpisode(v))} />
    </PanelHead>
  );
}

/** A labelled field of the settings card; `wide` spans both columns. */
function Field({ label, note, wide, htmlFor, children }: {
  label: string; note?: string; wide?: boolean; htmlFor?: string; children: React.ReactNode;
}) {
  return (
    <div className={`sm-field${wide ? " sm-wide" : ""}`}>
      <label className="sm-label" htmlFor={htmlFor}>{label}</label>
      {children}
      {note && <span className="sm-note">{note}</span>}
    </div>
  );
}

/** The project's saved picture size for the pass on (`series` for final, `proxy`
 * for proxy, in its series config); 0 when it says none. */
function projectSize(raw: Raw | null, pass: string, status: { width: number | null; height: number | null } | null | undefined): [number, number] {
  const block = pass === "final" ? "series" : "proxy";
  return [
    Number(raw && getPath(raw, [block, "width"])) || status?.width || 0,
    Number(raw && getPath(raw, [block, "height"])) || status?.height || 0,
  ];
}

/** The clip's picture size: width and height, typed or filled from a common size.
 * Generate renders at it (a clip at another size than the project's keeps it as
 * its own size override, as Inspect shot does); **Save as the project's size**
 * makes it every later clip's. Under it, what the clip's model renders when that
 * differs. */
function SizeRow({ w, h, setW, setH, pass, project, seriesTemplate, template, short, save }: {
  w: string; h: string; setW: (v: string) => void; setH: (v: string) => void; pass: string;
  project: [number, number]; seriesTemplate: TargetTemplate | undefined; template: TargetTemplate | undefined; short: string;
  save: (w: number, h: number) => Promise<boolean>;
}) {
  const [busy, setBusy] = useState(false);
  const nw = Math.round(Number(w)), nh = Math.round(Number(h));
  const valid = nw >= 64 && nh >= 64 && nw <= 8192 && nh <= 8192;
  const [sw, sh] = valid ? fitSize(nw, nh, seriesTemplate) : [0, 0];
  const [rw, rh] = valid ? fitSize(sw, sh, template) : [0, 0];
  const dirty = valid && (sw !== project[0] || sh !== project[1]);
  async function set() {
    setBusy(true);
    try { await save(sw, sh); } finally { setBusy(false); }
  }
  const notes = [
    valid && (sw !== nw || sh !== nh) ? `the project's model takes ${sw}×${sh}` : "",
    valid && template && (rw !== sw || rh !== sh) ? `${short} renders ${rw}×${rh}` : "",
    dirty && project[0] ? `the project's is ${project[0]}×${project[1]}: this clip keeps its own` : "",
  ].filter(Boolean);
  return (
    <Field label={`Size (${pass})`} wide note={notes.join("; ")} htmlFor="sm-size-w">
      <span className="h3-row h3-wrap" style={{ gap: 6 }}>
        <input id="sm-size-w" className="h3-in" style={{ width: 64 }} inputMode="numeric" value={w} onChange={(e) => setW(e.target.value.replace(/\D/g, ""))} title="Width, pixels" />
        <span className="h3-muted">×</span>
        <input className="h3-in" style={{ width: 64 }} inputMode="numeric" value={h} aria-label="Height, pixels" onChange={(e) => setH(e.target.value.replace(/\D/g, ""))} title="Height, pixels" />
        <PickMenu label="sizes" title="A common size to start from"
          options={COMMON_SIZES.map((q) => ({ value: `${q.width}x${q.height}`, label: q.label }))}
          onPick={(v) => { const [a, b] = v.split("x"); setW(a); setH(b); }} />
        {dirty && (
          <button className="h3-btn" disabled={busy} onClick={() => void set()}
            title={`Make it the project's size: every later clip renders at it (${pass}). Generate uses the boxes either way.`}>
            Save as the project's size
          </button>
        )}
      </span>
    </Field>
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
  const [rows, setRows] = useState<ShotRow[]>([{ prompt: "", size: "wide", dur: "3.04" }, { prompt: "", size: "medium", dur: "3.04" }]);
  const [who, setWho] = useState<string[]>([]);
  const [where, setWhere] = useState("");
  const [placeText, setPlaceText] = useState("");
  // a new place: words only (renders at once), or a picture made first
  const [placePicture, setPlacePicture] = useState(false);
  const [dialogue, setDialogue] = useState<DialogueLine[]>([]);
  const [size, setSize] = useState("medium");
  const [dur, setDur] = useState("3.04");
  const [busy, setBusy] = useState(false);
  const target = model || seriesTarget;
  const imageTarget = imageModel || imageDefault;
  const picture = mode === "picture";
  const status = useApp((s) => s.status[statusKey(ep, s.pass)]);
  const fps = Number(raw && getPath(raw, ["series", "fps"])) || 24;
  const all = targets?.targets ?? [];
  const tpl = all.find((x) => x.id === target)?.template;
  const seriesTpl = all.find((x) => x.id === seriesTarget)?.template;
  // the size boxes: the project's until typed over (another project or pass: its own again)
  const [pw, ph] = projectSize(raw, pass, status);
  const [sizeW, setSizeW] = useState(pw ? String(pw) : "");
  const [sizeH, setSizeH] = useState(ph ? String(ph) : "");
  useEffect(() => { setSizeW(pw ? String(pw) : ""); setSizeH(ph ? String(ph) : ""); }, [pw, ph, ep]);

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
  // one take (or picture) a click; another is another click
  const runs = mode === "shots" ? filled.length : 1;
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
      // a size of its own: the shot's size override (this pass), as Inspect shot saves one
      const own = picture ? null : clipOwnSize(sizeW, sizeH, [pw, ph], seriesTpl, tpl);
      if (own) for (const id of ids) await api().putOverride({ ep, pass, shot: id, both: false, fields: { size: own } });
      let first = true;
      for (const id of ids) {
        const q = await api().clipQueue({ ep, shot: id, pass, takes: 1, backend: backend || null,
                                          ...(picture ? { still: true, image_target: imageTarget } : {}) });
        if (first && q.step) {
          host().toast("success", `${shot} queued`, `Its picture${q.refs.length === 1 ? " is" : "s are"} made first, then the rest.`);
          first = false;
        }
      }
      if (first) host().toast("success", `${shot} queued`, picture
        ? "Its picture is on the way."
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
  const make = mode === "shots" && runs > 1 ? `Generate ${runs} shots` : "Generate";
  const tabs: { id: Mode; label: string; title?: string }[] = [
    { id: "clip", label: "A clip" },
    { id: "picture", label: "A picture" },
    { id: "shots", label: "Several shots", title: "A few shots, cut together and played as one clip" },
  ];
  return (
    <div className="sm-body">
      <nav className="sm-modes" aria-label="What you're making">
        {tabs.map((x) => (
          <button key={x.id} className={mode === x.id ? "sm-on" : ""} title={x.title} onClick={() => setMode(x.id)}>{x.label}</button>
        ))}
        <button title="A series with episodes: the step-by-step wizard (then Advanced)" disabled={!root}
          onClick={() => { if (root) { setSimple(false); openWizard({ parent: root, newSeries: true }); } }}>A series…</button>
      </nav>

      <section className="sm-card">
        {mode === "shots" ? (
          <>
            <span className="sm-card-title">The shots</span>
            <span className="sm-note">In order: each is a cut. Say what we see in each; the people and the place below are for all of them.</span>
            {rows.map((r, i) => (
              <div key={i} className="sm-shot">
                <div className="h3-row h3-wrap" style={{ gap: 6 }}>
                  <b className="sm-shot-n">{i + 1}</b>
                  <select className="h3-in" aria-label={`Shot ${i + 1}'s framing`} value={r.size}
                    onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, size: e.target.value } : x)))}>
                    {SIZES.map((s) => <option key={s.value} value={s.value}>{s.label.split(" — ")[0]}</option>)}
                  </select>
                  <LengthPicker value={r.dur} template={tpl} fps={fps} short={t?.short} compact
                    onChange={(v) => setRows(rows.map((x, j) => (j === i ? { ...x, dur: v } : x)))} />
                  <span className="h3-grow" />
                  {rows.length > 1 && (
                    <button className="h3-link" aria-label={`Remove shot ${i + 1}`} title="Remove this shot"
                      onClick={() => setRows(rows.filter((_, j) => j !== i))}>×</button>
                  )}
                </div>
                <textarea className="h3-in sm-prompt" rows={2} aria-label={`Shot ${i + 1}: what we see`} value={r.prompt}
                  placeholder={i === 0 ? "Wide: the keeper climbs the cliff path toward the lighthouse." : "Close: his hand on the cold iron door."}
                  onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, prompt: e.target.value } : x)))} />
              </div>
            ))}
            {rows.length < 8 && (
              <div><button className="h3-btn" onClick={() => setRows([...rows, { prompt: "", size: "medium", dur: "3.04" }])}>+ Shot</button></div>
            )}
          </>
        ) : (
          <>
            <label className="sm-card-title" htmlFor="sm-prompt">{picture ? "What's in it?" : "What happens?"}</label>
            <textarea id="sm-prompt" className="h3-in sm-prompt" rows={4} value={prompt}
              placeholder={picture ? "A lighthouse keeper at the top of the stairs, lantern raised, storm clouds through the window."
                : "A lighthouse keeper climbs the spiral stairs with a lantern as the storm comes in."}
              onChange={(e) => setPrompt(e.target.value)} />
          </>
        )}

        <div className="sm-cast">
          <span className="sm-label">Who</span>
          <div className="h3-col" style={{ gap: 4 }}>
            <Chips ep={ep} value={who} options={cast.chars} onChange={setWho}
              add={() => openSubjectCard({ kind: "character", id: null })} addLabel="+ Someone" />
            {picture && it?.capabilities?.mode !== "edit" && who.length > 0 && (
              <span className="sm-note">This model works from words: they're described, not drawn from their pictures.</span>
            )}
          </div>

          <span className="sm-label">Where</span>
          <div className="h3-col" style={{ gap: 6 }}>
            <span className="h3-row h3-wrap" style={{ gap: 6 }}>
              <PlacePick ep={ep} value={where} places={cast.places} empty="a new place" onChange={setWhere} />
              {where && (
                <button className="h3-btn" title="Its pictures: make it again, edit it, or take a Tour through it for new angles"
                  onClick={() => openSubjectCard({ kind: "location", id: where })}>Open</button>
              )}
              <button className="h3-btn" onClick={() => openSubjectCard({ kind: "location", id: null })}>+ Place</button>
            </span>
            {!where && (
              <>
                <input className="h3-in" aria-label="The new place, in words" value={placeText}
                  placeholder="a stone lighthouse on a cliff at dusk, storm clouds (empty: from what happens)"
                  onChange={(e) => setPlaceText(e.target.value)} />
                <label className="sm-check" title="Slower to start, but the place then looks the same in every clip that picks it">
                  <input type="checkbox" checked={placePicture} onChange={(e) => setPlacePicture(e.target.checked)} />
                  <span>Make a picture of it first (so it looks the same each time)</span>
                </label>
              </>
            )}
          </div>

          {mode === "clip" && who.length > 0 && (
            <>
              <span className="sm-label">Said</span>
              <DialogueRows rows={dialogue} speakers={cast.chars.filter((c) => who.includes(c.id))} onChange={setDialogue} />
            </>
          )}
        </div>
      </section>

      <section className="sm-card sm-settings">
        {picture ? (
          <Field label="Model" htmlFor="sm-model"
            note={it?.readiness?.status === "not_ready" ? "Its files aren't all installed." : undefined}>
            <select id="sm-model" className="h3-in" title={IMAGE_NOTES[imageTarget] ?? it?.label} value={imageTarget} onChange={(e) => setImageModel(e.target.value === imageDefault ? "" : e.target.value)}>
              <ModelOptions targets={images} text={(v) => `${v.label}${v.id === imageDefault ? " (default)" : ""}`} />
            </select>
          </Field>
        ) : (
          <Field label="Model" htmlFor="sm-model" wide={mode === "shots"}
            note={t?.readiness?.status === "not_ready" ? "Its files aren't all installed." : undefined}>
            <select id="sm-model" className="h3-in" title={MODEL_NOTES[target] ?? t?.label} value={target} onChange={(e) => setModel(e.target.value === seriesTarget ? "" : e.target.value)}>
              <ModelOptions targets={video} text={(v) => `${v.label}${v.id === seriesTarget ? " (default)" : ""}`} />
            </select>
          </Field>
        )}
        {mode !== "shots" && (
          <Field label="Framing" htmlFor="sm-framing">
            <select id="sm-framing" className="h3-in" value={size} onChange={(e) => setSize(e.target.value)}>
              {SIZES.map((s) => <option key={s.value} value={s.value}>{s.label.split(" — ")[0]}</option>)}
            </select>
          </Field>
        )}
        {mode === "clip" && (
          <Field label="Length" wide>
            <LengthPicker value={dur} onChange={setDur} template={tpl} fps={fps} short={t?.short} auto model={target.startsWith("ltx2")} />
          </Field>
        )}
        {raw && (
          <SizeRow w={sizeW} h={sizeH} setW={setSizeW} setH={setSizeH} pass={pass} project={[pw, ph]}
            seriesTemplate={seriesTpl} template={picture ? undefined : tpl} short={t?.short ?? target}
            save={(w, h) => {
              const block = pass === "final" ? "series" : "proxy";
              return sc.save(setPath(setPath(raw, [block, "width"], w), [block, "height"], h), "the size");
            }} />
        )}
      </section>

      <button className="h3-btn h3-primary sm-make" disabled={busy || !ready || !raw} onClick={() => void queue()}>
        {busy && <i className="pi pi-spin pi-spinner" />} {make}
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
  const head = (
    <div className="sm-clips-head">
      <span className="sm-card-title">Your clips</span>
      <span className="sm-note">{pass} · newest first</span>
    </div>
  );
  if (!shots.length) return <div className="sm-clips">{head}<span className="sm-note">Your clips appear here.</span></div>;
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
    <div className="sm-clips">
      {head}
      <div className="sm-clip-grid">
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
          <button key={g.seq} className="sm-clip"
            title={isPicture ? "Open its pictures" : g.shots.length > 1 ? "Play its shots, cut together" : "Play its newest take"}
            onClick={play}>
            <span className="sm-clip-thumb">
              {thumb ? <img src={isPicture ? api().thumbUrl(ep, thumb, 512) : api().fileUrl(ep, thumb)} alt="" />
                : <span className="sm-note">{busy ? "on the way…" : "nothing yet"}</span>}
            </span>
            <span className="sm-clip-label">
              <b>{label}</b>{isPicture ? " · picture" : ""}
            </span>
            <span className="sm-note">
              {[
                ready ? `${ready} ${isPicture ? "picture" : "take"}${ready > 1 ? "s" : ""}` : "",
                busy ? `${busy} on the way` : "",
                !ts.length && !isPicture && (first.missing_refs?.length ?? 0) > 0 ? "pictures first" : "",
                ts.some((x) => x.status === "failed") ? "some failed" : "",
              ].filter(Boolean).join(" · ")}
            </span>
          </button>
        );
      })}
      </div>
    </div>
  );
}
