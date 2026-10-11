// Simple mode (docs/PLAN.md, step 12): the sidebar as one panel for making a
// clip -- pick the model, write what happens, pick who and where by picture
// (or add them), queue some takes -- and the clips so far. A clip is a shot
// of the Clips project (seriesmith/clips.py), written by lib/simple.ts; its
// missing pictures are made first (POST /seriesmith/clip/queue). Everything
// else (settings, the text windows, the Refs tab) waits in Advanced.

import { useEffect, useMemo, useState } from "react";
import {
  afterAuthoredWrite, isPaidBackend, loadEpisodes, loadRefs, loadTargets, openBrowse, openSubjectCard,
  openViewer, openWizard, select, selectEpisode, setSimple,
} from "../actions";
import { api, host } from "../host";
import { pictureOf } from "../lib/pictures";
import { getPath, refsPrefix, serialize, setPath, type Raw } from "../lib/seriesForm";
import { DURATIONS, SIZES, type DialogueLine } from "../lib/shotForm";
import { MODEL_NOTES, clipBlock, nextClipIds, placeFor, withClip } from "../lib/simple";
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
  const video = (targets?.targets ?? []).filter((t) => t.kind === "video" && !t.draft);
  const [model, setModel] = useState("");
  const [prompt, setPrompt] = useState("");
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

  async function queue() {
    if (!raw || !prompt.trim()) return;
    if (isPaidBackend(backend) || target === "seedance_2_5") {
      if (!confirm(`${takes} take${takes > 1 ? "s" : ""} on a paid backend (${backend || "Router"}): each is billed to your Comfy account. Queue?`)) return;
    }
    setBusy(true);
    try {
      // the script: the clip's ids after the ones there
      const script = await api().source(ep, "script");
      const { seq, shot } = nextClipIds(script.text);
      const spec = { prompt, who, where, placeText, size, dur, target, dialogue };
      let location = where;
      if (!location) {
        // a place of the clip's own, its plate made before it renders
        const series = await api().source(ep, "series");
        const cur = JSON.parse(series.text) as Raw;
        const p = placeFor(shot, spec, refsPrefix(cur), placePicture);
        const next = setPath(cur, ["locations", p.id], p.entry);
        await api().putSource({ ep, file: "series", text: serialize(next, series.text), base_hash: series.hash, rebuild: false });
        location = p.id;
      }
      const block = clipBlock(seq, shot, location, spec, seriesTarget);
      const r = await api().putSource({ ep, file: "script", text: withClip(script.text, block), base_hash: script.hash, rebuild: true });
      afterAuthoredWrite(r.build);
      const bad = r.check.errors.find((m) => m.line == null || m.message.includes(shot) || m.message.includes(seq));
      if (bad) {
        host().toast("error", `${shot} was written, but it won't build`, bad.message);
        return;
      }
      const q = await api().clipQueue({ ep, shot, pass, takes, backend: backend || null });
      host().toast("success", `${shot} queued`, q.step
        ? `Its picture${q.refs.length === 1 ? " is" : "s are"} made first (${q.refs.map((x) => x.ref.split(":")[1]).join(", ") || "on their way"}), then ${takes} take${takes > 1 ? "s" : ""}.`
        : `${takes} take${takes > 1 ? "s" : ""} on the way.`);
      select(shot, null);
      setPrompt("");
      setDialogue([]);
      setPlaceText("");
    } catch (e) {
      host().toast("error", "The clip wasn't queued", (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const t = video.find((x) => x.id === target);
  return (
    <div className="h3-col" style={{ gap: 10, padding: 10, overflow: "auto", minHeight: 0, flex: 1 }}>
      <div className="h3-row h3-wrap" style={{ gap: 6 }}>
        <span className="h3-seg" title="What you're making">
          <button className="h3-on">A clip</button>
          <button disabled title="A few shots played as one clip: coming next">Several shots</button>
          <button title="A series with episodes: the step-by-step wizard (then Advanced)" disabled={!root}
            onClick={() => { if (root) { setSimple(false); openWizard({ parent: root, newSeries: true }); } }}>A series…</button>
        </span>
      </div>

      <Row label="Model" help={(MODEL_NOTES[target] ?? t?.label ?? "") + (t?.readiness?.status === "not_ready" ? " (its files aren't all installed)" : "")}>
        <select className="h3-in" value={target} onChange={(e) => setModel(e.target.value === seriesTarget ? "" : e.target.value)}>
          {video.map((v) => <option key={v.id} value={v.id}>{v.label}{v.id === seriesTarget ? " (default)" : ""}</option>)}
        </select>
      </Row>

      <Row label="What happens" help="What we see, as you'd describe it to a camera crew: who does what, where, in what light.">
        <textarea className="h3-in" rows={4} style={{ fontFamily: "inherit", resize: "vertical" }} value={prompt}
          placeholder="A lighthouse keeper climbs the spiral stairs with a lantern as the storm comes in."
          onChange={(e) => setPrompt(e.target.value)} />
      </Row>

      <Row label="Who's in it" help="Optional. Add someone with a picture you have, or a description to draw them from.">
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

      {who.length > 0 && (
        <Row label="What's said" help="Optional: a line, under who says it.">
          <DialogueRows rows={dialogue} speakers={cast.chars.filter((c) => who.includes(c.id))} onChange={setDialogue} />
        </Row>
      )}

      <div className="h3-row h3-wrap" style={{ gap: 10 }}>
        <Row label="Framing" help="">
          <select className="h3-in" value={size} onChange={(e) => setSize(e.target.value)}>
            {SIZES.map((s) => <option key={s.value} value={s.value}>{s.label.split(" — ")[0]}</option>)}
          </select>
        </Row>
        <Row label="Length" help="">
          <select className="h3-in" value={dur} onChange={(e) => setDur(e.target.value)}>
            {DURATIONS.filter((d) => d.value !== "model" || target.startsWith("ltx2")).map((d) => <option key={d.value} value={d.value}>{d.label.split(" — ")[0]}</option>)}
          </select>
        </Row>
        <Row label="Takes" help="">
          <select className="h3-in" value={takes} onChange={(e) => setTakes(Number(e.target.value))}>
            {[1, 2, 3, 4].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </Row>
      </div>

      <button className="h3-btn h3-primary" style={{ alignSelf: "flex-start" }} disabled={busy || !prompt.trim() || !raw} onClick={() => void queue()}>
        {busy ? <i className="pi pi-spin pi-spinner" /> : <i className="pi pi-play" />} Queue {takes} take{takes > 1 ? "s" : ""}
      </button>

      <ClipList ep={ep} pass={pass} />
    </div>
  );
}

/** The clips made so far, newest first: the newest take's picture, where it stands. */
function ClipList({ ep, pass }: { ep: string; pass: string }) {
  const st = useApp((s) => s.status[statusKey(ep, s.pass)]);
  const shots = [...(st?.shots ?? [])].filter((s) => !s.orphan).reverse();
  if (!shots.length) return <div className="h3-small h3-muted">Your clips appear here.</div>;
  return (
    <div className="h3-col" style={{ gap: 6 }}>
      <span className="h3-small"><b>Your clips</b> <span className="h3-muted">{pass}</span></span>
      {shots.map((s) => {
        const ts = s.takes ?? [];
        const last = ts[ts.length - 1];
        const ready = ts.filter((x) => x.status === "ok").length;
        const busy = ts.filter((x) => x.status === "queued").length;
        return (
          <button key={s.shot} className="h3-btn" style={{ justifyContent: "flex-start", gap: 8, height: "auto", padding: 4 }}
            title="Play its newest take"
            onClick={() => { select(s.shot, last?.take ?? null); if (last && last.status === "ok") openViewer(s.shot, last.take, null, "single"); }}>
            <span style={{ width: 72, height: 40, flex: "none", background: "var(--h3-bg3)", borderRadius: 3, overflow: "hidden" }}>
              {last?.thumb && <img src={api().fileUrl(ep, last.thumb)} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} />}
            </span>
            <span className="h3-col" style={{ alignItems: "flex-start", gap: 1 }}>
              <b className="h3-small">{s.shot}</b>
              <span className="h3-small h3-muted">
                {ready ? `${ready} take${ready > 1 ? "s" : ""}` : "no takes yet"}{busy ? ` · ${busy} on the way` : ""}
                {!ts.length && (s.missing_refs?.length ?? 0) > 0 ? " · pictures first" : ""}
                {ts.some((x) => x.status === "failed") ? " · some failed" : ""}
              </span>
            </span>
          </button>
        );
      })}
    </div>
  );
}
