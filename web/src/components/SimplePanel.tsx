// Simple mode (docs/PLAN.md, step 12): the sidebar as one panel for making a
// clip -- pick the model, write what happens, pick who and where by picture
// (or add them), queue some takes -- and the clips so far. A clip is a shot
// of the Clips project (seriesmith/clips.py), written by lib/simple.ts; its
// missing pictures are made first (POST /seriesmith/clip/queue). Everything
// else (settings, the text windows, the Refs tab) waits in Advanced.

import { useEffect, useMemo, useState } from "react";
import {
  afterAuthoredWrite, isPaidBackend, loadEpisodes, loadRefs, loadTargets, openBrowse, openImageCompare, openSubjectCard,
  openViewer, openWizard, playAll, select, selectEpisode, setSimple,
} from "../actions";
import { api, host } from "../host";
import { pictureOf } from "../lib/pictures";
import { getPath, refsPrefix, serialize, setPath, type Raw } from "../lib/seriesForm";
import { DURATIONS, SIZES, type DialogueLine } from "../lib/shotForm";
import { IMAGE_NOTES, MODEL_NOTES, clipBlock, nextClipIds, pictureModel, placeFor, shotsBlock, withClip } from "../lib/simple";
import { statusKey, store, useApp } from "../store";
import type { Named } from "./Picture";
import { Chips, DialogueRows, PlacePick, Row, type Cast } from "./ShotForm";
import { useSeriesConfig } from "./useSeriesConfig";

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
  const [clipsEp, setClipsEp] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // the Clips project, made the first time, and opened
  useEffect(() => {
    let gone = false;
    api().clipsEnsure()
      .then(async (r) => {
        if (gone) return;
        setClipsEp(r.ep);
        if (r.made) await loadEpisodes();
        if (store.get().ep !== r.ep) selectEpisode(r.ep);
      })
      .catch((e) => !gone && setError((e as Error).message));
    return () => { gone = true; };
  }, [config?.roots?.join("|")]);

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
  if (!clipsEp || ep !== clipsEp) {
    return <div className="h3-surface">{head}<div className="h3-pad h3-muted h3-small">Opening your clips…</div></div>;
  }
  return (
    <div className="h3-surface">
      {head}
      <ClipMaker ep={clipsEp} root={config?.roots?.[0] ?? null} />
    </div>
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
  const [takes, setTakes] = useState(2);
  const [busy, setBusy] = useState(false);
  const target = model || seriesTarget;
  const imageTarget = imageModel || imageDefault;
  const picture = mode === "picture";

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
        ? filled.map((r) => ({ ...base, prompt: r.prompt, size: r.size, dur: r.dur }))
        : [{ ...base, prompt, size, dur, still: picture }];
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
            {images.map((v) => <option key={v.id} value={v.id}>{v.label}{v.id === imageDefault ? " (default)" : ""}</option>)}
          </select>
        </Row>
      ) : (
        <Row label="Model" help={(MODEL_NOTES[target] ?? t?.label ?? "") + (t?.readiness?.status === "not_ready" ? " (its files aren't all installed)" : "")}>
          <select className="h3-in" value={target} onChange={(e) => setModel(e.target.value === seriesTarget ? "" : e.target.value)}>
            {video.map((v) => <option key={v.id} value={v.id}>{v.label}{v.id === seriesTarget ? " (default)" : ""}</option>)}
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
                  <select className="h3-in" value={r.dur} onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, dur: e.target.value } : x)))}>
                    {DURATIONS.filter((d) => d.value !== "model" && d.value !== "auto").map((d) => <option key={d.value} value={d.value}>{d.label.split(" — ")[0]}</option>)}
                  </select>
                  <span className="h3-grow" />
                  {rows.length > 1 && <button className="h3-link" title="Remove this shot" onClick={() => setRows(rows.filter((_, j) => j !== i))}>×</button>}
                </div>
                <textarea className="h3-in" rows={2} style={{ fontFamily: "inherit", resize: "vertical" }} value={r.prompt}
                  placeholder={i === 0 ? "Wide: the keeper climbs the cliff path toward the lighthouse." : "Close: his hand on the cold iron door."}
                  onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, prompt: e.target.value } : x)))} />
              </div>
            ))}
            {rows.length < 8 && <div><button className="h3-btn" onClick={() => setRows([...rows, { prompt: "", size: "medium", dur: "3.04" }])}>+ Shot</button></div>}
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
            <select className="h3-in" value={dur} onChange={(e) => setDur(e.target.value)}>
              {DURATIONS.filter((d) => d.value !== "model" || target.startsWith("ltx2")).map((d) => <option key={d.value} value={d.value}>{d.label.split(" — ")[0]}</option>)}
            </select>
          </Row>
        )}
        <Row label={picture ? "Pictures" : mode === "shots" ? "Takes of each" : "Takes"} help="">
          <select className="h3-in" value={takes} onChange={(e) => setTakes(Number(e.target.value))}>
            {[1, 2, 3, 4].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </Row>
      </div>

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
