// The new episode wizard: a new series or its next episode in four short steps
// — where it goes, the series (a new one only), who and where it's about, and
// its first shot — written in one POST /seriesmith/episode/new (lib/wizard.ts).
// A next episode starts from its newest neighbour's series config, so the cast,
// look and settings carry over and only what's new is added.

import { useEffect, useMemo, useState } from "react";
import { build, loadEpisodes, loadTargets, openEpisodeAt, openShotForm, openWizard } from "../actions";
import { api, host } from "../host";
import { nameError } from "../lib/newEpisode";
import {
  DEFAULT_PROXY, FINAL_SIZES, PROXY_SIZES, SECTIONS, cardFields, getPath, parsed, refsPrefix, serialize, setPath, setSize,
  shapeNote, shown, sizeOf, slug, type Field, type Raw,
} from "../lib/seriesForm";
import { DURATIONS, SIZES, listOf, newShot, type ShotForm as Shot } from "../lib/shotForm";
import { pictureOf } from "../lib/pictures";
import { sizeRule } from "../lib/size";
import {
  WIZARD_KINDS, castId, castOfConfig, castProblems, firstScript, seriesConfig, showFolder, withCast, type NewCast,
} from "../lib/wizard";
import { useApp } from "../store";
import type { EpisodeTemplate } from "../types";
import { FloatingWindow, type Rect } from "./FloatingWindow";
import { FieldRow, SizeField } from "./SeriesForm";
import { Hover, Thumb, type Named } from "./Picture";
import { CameraField, Chips, DialogueRows, PlacePick, Row, type Cast } from "./ShotForm";

const RECT_KEY = "seriesmith.wizard.rect";
const STEPS = ["Where", "Series", "Cast and places", "First shot"] as const;

function defaultRect(): Rect {
  const W = window.innerWidth || 1280;
  const H = window.innerHeight || 800;
  const w = Math.max(420, Math.min(760, Math.round(W * 0.5)));
  return { x: Math.max(16, Math.round((W - w) / 2)), y: 52, w, h: Math.max(420, H - 110) };
}

export function NewEpisodeWizard() {
  const w = useApp((s) => s.wizard);
  if (!w) return null;
  return <Wizard key={`${w.parent}|${w.newSeries}`} parent={w.parent} startNew={w.newSeries} />;
}

const FIELD = (p: string): Field => SECTIONS.flatMap((s) => s.fields).find((f) => f.path.join(".") === p)!;

function Wizard({ parent, startNew }: { parent: string; startNew: boolean }) {
  const targets = useApp((s) => s.targets);
  const [step, setStep] = useState(0);
  const [title, setTitle] = useState("");           // the series' (a new one)
  const [show, setShow] = useState("");
  const [showTouched, setShowTouched] = useState(false);
  const [tpl, setTpl] = useState<EpisodeTemplate | null>(null);
  const [tplErr, setTplErr] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [nameTouched, setNameTouched] = useState(false);
  const [epTitle, setEpTitle] = useState("");
  const [series, setSeries] = useState<Raw>(() => seriesConfig(""));
  const [idTouched, setIdTouched] = useState(false);
  const [cast, setCast] = useState<NewCast[]>([]);
  const [shot, setShot] = useState<Shot>(() => newShot("sh010"));
  const [location, setLocation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void loadTargets();
  }, []);

  // what it starts from: the newest episode in the folder, or nothing (a new series)
  const showName = startNew ? show : "";
  useEffect(() => {
    if (startNew && (!show || nameError(show))) {
      setTpl(null);
      return;
    }
    const t = window.setTimeout(() => {
      api().episodeTemplate(parent, showName || null)
        .then((r) => { setTpl(r); setTplErr(null); if (!nameTouched) setName(r.name); })
        .catch((e) => setTplErr((e as Error).message));
    }, 250);
    return () => window.clearTimeout(t);
  }, [parent, showName]);

  const isNewSeries = !tpl?.from;
  const base: Raw | null = useMemo(() => {
    if (!tpl) return null;
    if (!tpl.series) return series;
    try {
      return JSON.parse(tpl.series) as Raw;
    } catch {
      return null;
    }
  }, [tpl, series]);
  const prefix = base ? refsPrefix(base) : "../refs/";
  const full = base ? withCast(base, cast, prefix) : null;
  const known = full ? castOfConfig(full) : { characters: [], things: [], locations: [] };
  const problems = base ? castProblems(base, cast) : [];
  const steps = STEPS.map((s, i) => ({ s, i })).filter(({ i }) => i !== 1 || isNewSeries);

  // a first location is the sequence's until one is picked
  useEffect(() => {
    if (!location && known.locations.length) setLocation(known.locations[0]);
  }, [known.locations.join(",")]);

  const setTitleAll = (t: string) => {
    setTitle(t);
    if (!showTouched) setShow(showFolder(t));
    setSeries((r) => {
      let next = setPath(r, ["series", "title"], t);
      if (!idTouched) next = setPath(next, ["series", "id"], slug(t));
      return next;
    });
  };

  // what stops each step
  const blockers: Record<number, string | null> = {
    0: !tpl ? (tplErr ?? (startNew && !title.trim() ? "Give the series a title." : startNew ? nameError(show) : "…"))
      : startNew && !title.trim() && isNewSeries ? "Give the series a title."
      : nameError(name) ?? (tpl.episodes.includes(name.trim()) ? `${name} is already there.` : null),
    1: !String(getPath(series, ["series", "id"]) ?? "").trim() ? "Give the series an id." : null,
    2: problems.find(Boolean) ?? (known.locations.length ? null : "Add a location: every sequence happens somewhere."),
    3: !location ? "Pick where it happens." : !shot.action.trim() ? "Say what happens in it." : null,
  };
  const at = steps.findIndex((x) => x.i === step);
  const last = at === steps.length - 1;
  const go = (d: number) => setStep(steps[Math.max(0, Math.min(steps.length - 1, at + d))].i);

  async function create() {
    if (!tpl || !full) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api().newEpisode({
        parent, name: name.trim(), title: epTitle.trim() || null,
        show: showName || null,
        series: serialize(full, tpl.series ?? "\n"),
        script: firstScript(name.trim(), epTitle.trim() || (isNewSeries ? title.trim() : ""), "sq01", location, shot),
      });
      host().toast(res.check.ok ? "success" : "warn", `Made ${res.episode.name}`,
        res.check.ok ? `${res.ep}\nNext: the pictures (Refs tab), then Build.` : res.check.errors[0]?.message ?? "");
      await loadEpisodes();
      openWizard(null);
      openShotForm(null);
      // opened and built, so the shots are there and the refs it needs are listed
      if (await openEpisodeAt(res.ep, tpl.parent)) await build();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const head = (
    <>
      <i className="pi pi-file-plus" />
      <span className="h3-grow">{startNew && isNewSeries ? "New series" : "New episode"}</span>
      <button className="h3-btn h3-icon" title="Close" onClick={() => {
        if ((title || cast.length || shot.action) && !window.confirm("Close the wizard? Nothing has been written yet.")) return;
        openWizard(null);
      }}><i className="pi pi-times" /></button>
    </>
  );

  const list = targets?.targets ?? [];
  const videoId = (getPath(series, ["series", "target"]) as string) || targets?.default?.video || "minimax_h3_ref2va";
  const rule = sizeRule(list.find((t) => t.id === videoId)?.template);
  // pictures: the neighbour's (its `../refs/...` paths are the show's); a new series has none yet
  const picEp = tpl?.from ?? null;
  const castList: Cast[] = known.characters.map((c) => ({ ...c, kind: "character", onScreen: true, pic: pictureOf(full, null, "subjects", c.id) }));
  const thingList: Cast[] = known.things.map((c) => ({ ...c, kind: "prop", onScreen: true, pic: pictureOf(full, null, "subjects", c.id) }));
  const placeList: Named[] = known.locations.map((id) => ({ id, name: id.replace(/_/g, " "), pic: pictureOf(full, null, "locations", id) }));
  const setKey = (k: string, v: string) => setShot((s) => ({ ...s, keys: { ...s.keys, [k]: v } }));
  const block = blockers[step];

  return (
    <FloatingWindow storageKey={RECT_KEY} defaultRect={defaultRect} head={head} minW={420} minH={360}>
      <div className="h3-row" style={{ padding: "6px 10px", gap: 6, borderBottom: "1px solid var(--h3-border)" }}>
        {steps.map(({ s, i }, n) => (
          <button key={s} className={`h3-btn${i === step ? " h3-on" : ""}`} disabled={n > at && !!blockers[step]}
            onClick={() => setStep(i)}>{n + 1}. {s}</button>
        ))}
      </div>
      <div id="sm-wizard" className="h3-col" style={{ padding: 10, gap: 10, overflow: "auto", flex: 1, minHeight: 0 }}>
        {step === 0 && (
          <>
            {startNew && (
              <>
                <Row label="Series title" help="The show's name: on the intro and outro of every master, and the start of its id.">
                  <input className="h3-in" autoFocus value={title} placeholder="First Light" onChange={(e) => setTitleAll(e.target.value)} />
                </Row>
                <Row label="Show folder" help={`A folder of its own in ${parent}: its episodes go in it, with one refs folder beside them that they share.`}>
                  <input className="h3-in h3-mono" value={show} placeholder="First_Light"
                    onChange={(e) => { setShow(e.target.value.trim()); setShowTouched(true); }} />
                </Row>
              </>
            )}
            {tpl && (
              <div className="h3-small h3-muted">
                {tpl.from
                  ? <>In {tpl.parent}: continues the series of {tpl.episodes.length} episode{tpl.episodes.length === 1 ? "" : "s"} there ({tpl.episodes.slice(-3).join(", ")}), from {tpl.episodes[tpl.episodes.length - 1]}'s series config — its cast, look and settings carry over.</>
                  : startNew ? <>A new series in {tpl.parent}.</>
                  : <>No series in {tpl.parent} yet, so this starts one.</>}
              </div>
            )}
            {!startNew && isNewSeries && tpl && (
              <Row label="Series title" help="The show's name: on the intro and outro of every master.">
                <input className="h3-in" value={title} placeholder="First Light" onChange={(e) => setTitleAll(e.target.value)} />
              </Row>
            )}
            <div className="h3-row h3-wrap" style={{ gap: 10, alignItems: "flex-start" }}>
              <Row label="Episode" help="The folder and the script's name (ep01 → ep01/ep01.md).">
                <input className="h3-in h3-mono" style={{ width: 120 }} value={name}
                  onChange={(e) => { setName(e.target.value.trim()); setNameTouched(true); }} />
              </Row>
              <div className="h3-grow">
                <Row label="Episode title" help="Written under the series title on the master; optional.">
                  <input className="h3-in" value={epTitle} placeholder="The Pier" onChange={(e) => setEpTitle(e.target.value)} />
                </Row>
              </div>
            </div>
          </>
        )}

        {step === 1 && (
          <>
            <FieldRow f={FIELD("series.id")} value={shown(series, FIELD("series.id"))}
              onChange={(v) => { setSeries((r) => setPath(r, ["series", "id"], v)); setIdTouched(true); }} />
            <FieldRow f={FIELD("series.target")} value={shown(series, FIELD("series.target"))} targets={list} defaults={targets?.default}
              onChange={(v) => setSeries((r) => setPath(r, ["series", "target"], v))} />
            <SizeField label="Size (final)" value={sizeOf(series, "series")} choices={FINAL_SIZES} rule={rule}
              help="The size the final pass renders at. 1344×768 is H3's own; a master is upscaled from it."
              onChange={(v) => setSeries((r) => setSize(r, "series", v))} />
            <SizeField label="Size (proxy)" value={sizeOf(series, "proxy")} choices={PROXY_SIZES} rule={rule}
              placeholder={DEFAULT_PROXY} note={shapeNote(sizeOf(series, "series"), sizeOf(series, "proxy"))}
              help="The animatic: the same shots, small and quick, to judge the cut by. 480p is the smallest that still reads."
              onChange={(v) => setSeries((r) => setSize(r, "proxy", v))} />
            {["style.look", "audio.mode", "speech.pace"].map((p) => (
              <FieldRow key={p} f={FIELD(p)} value={shown(series, FIELD(p))}
                onChange={(v) => setSeries((r) => setPath(r, FIELD(p).path, parsed(FIELD(p), v)))} />
            ))}
            <div className="h3-small h3-muted">The rest (models for pictures and voices, finishing, the intro and outro) is in Series settings, any time.</div>
          </>
        )}

        {step === 2 && base && (
          <>
            <div className="h3-small h3-muted">
              {isNewSeries
                ? "Who and where the episode is about. Each gets a picture next (the Refs tab draws it from the design, or takes one you have); more can be added any time."
                : `Carried over: ${castOfConfig(base).characters.length} characters, ${castOfConfig(base).locations.length} locations, ${castOfConfig(base).things.length} props and vehicles. Add only who and what is new in this episode.`}
            </div>
            {!isNewSeries && (
              <div className="h3-row h3-wrap" style={{ gap: 4 }}>
                {[...castList, ...thingList, ...placeList]
                  .filter((o) => !cast.some((c) => c.id === o.id))
                  .map((o) => (
                    <Hover key={o.id} ep={picEp} item={o}>
                      <Thumb ep={picEp} pic={o.pic} name={o.name} size={36} />
                    </Hover>
                  ))}
              </div>
            )}
            {cast.map((c, i) => (
              <CastCard key={i} c={c} raw={full ?? base} problem={problems[i]}
                onChange={(n) => setCast(cast.map((x, j) => (j === i ? n : x)))}
                onRemove={() => setCast(cast.filter((_, j) => j !== i))} />
            ))}
            <div className="h3-row h3-wrap">
              {WIZARD_KINDS.map((k) => (
                <button key={k.kind} className="h3-btn" onClick={() => setCast([...cast, { kind: k.kind, id: "", fields: {} }])}>{k.add}</button>
              ))}
            </div>
          </>
        )}

        {step === 3 && (
          <>
            <div className="h3-small h3-muted">The episode's first shot, to start from; the shot form adds the rest.</div>
            <Row label="Where" help="The first sequence's location: every shot in it happens here.">
              <PlacePick ep={picEp} value={location} places={placeList} empty="pick a location…" onChange={setLocation} />
            </Row>
            <Row label="Who's in it" help="The characters on screen, in order.">
              <Chips ep={picEp} value={listOf(shot.keys.who)} options={castList} onChange={(v) => setKey("who", v.join(", "))}
                add={() => { setStep(2); setCast([...cast, { kind: "character", id: "", fields: {} }]); }} addLabel="+ Character" />
            </Row>
            {thingList.length > 0 && (
              <Row label="With" help="Props and vehicles whose look matters.">
                <Chips ep={picEp} value={listOf(shot.keys.with)} options={thingList} onChange={(v) => setKey("with", v.join(", "))}
                  add={() => { setStep(2); setCast([...cast, { kind: "prop", id: "", fields: {} }]); }} addLabel="+ Prop" />
              </Row>
            )}
            <div className="h3-row h3-wrap" style={{ gap: 10 }}>
              <Row label="Size" help="How much of them the frame holds.">
                <select className="h3-in" value={shot.keys.size ?? ""} onChange={(e) => setKey("size", e.target.value)}>
                  {SIZES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
                </select>
              </Row>
              <Row label="Length" help="Seconds on H3's grid; auto fits the dialogue.">
                <select className="h3-in" value={shot.keys.dur ?? ""} onChange={(e) => setKey("dur", e.target.value)}>
                  {DURATIONS.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
                </select>
              </Row>
            </div>
            <Row label="What happens" help="What is visibly happening, present tense, concrete and physical.">
              <textarea className="h3-in" rows={3} style={{ fontFamily: "inherit", resize: "vertical" }} value={shot.action}
                placeholder="Ada steps out onto the wet porch and stops, looking at the mist on the lawn."
                onChange={(e) => setShot({ ...shot, action: e.target.value })} />
            </Row>
            <Row label="Dialogue" help="Optional: each line under its speaker.">
              <DialogueRows rows={shot.dialogue} speakers={castList} onChange={(d) => setShot({ ...shot, dialogue: d })} />
            </Row>
            <Row label="Camera" help="The move, in H3's words. Empty: it holds still.">
              <CameraField value={shot.keys.camera ?? ""} onChange={(v) => setKey("camera", v)} />
            </Row>
            <Row label="Sound" help="Ambience and the sounds of the action.">
              <input className="h3-in" value={shot.keys.sound ?? ""} placeholder="dawn birdsong, dripping water" onChange={(e) => setKey("sound", e.target.value)} />
            </Row>
          </>
        )}
        {error && <div className="h3-err">{error}</div>}
      </div>
      <div className="h3-row" style={{ padding: "6px 10px", borderTop: "1px solid var(--h3-border)" }}>
        <span className="h3-small h3-grow h3-muted">{block && block !== "…" ? block : ""}</span>
        <button className="h3-btn" disabled={at === 0 || busy} onClick={() => go(-1)}>Back</button>
        {!last && <button className="h3-btn h3-primary" disabled={!!block} onClick={() => go(1)}>Next</button>}
        {last && (
          <button className="h3-btn h3-primary" disabled={!!block || busy || Object.values(blockers).some(Boolean)}
            title={tpl ? `Makes ${tpl.parent}\\${name}\\ with its series.json and script` : ""} onClick={() => void create()}>
            {busy ? <i className="pi pi-spin pi-spinner" /> : <i className="pi pi-check" />} Create {name}
          </button>
        )}
      </div>
    </FloatingWindow>
  );
}

/** One new cast entry: the cast card's main fields, its id made from its name. */
function CastCard({ c, raw, problem, onChange, onRemove }: {
  c: NewCast; raw: Raw; problem: string; onChange: (c: NewCast) => void; onRemove: () => void;
}) {
  const label = WIZARD_KINDS.find((k) => k.kind === c.kind)?.label ?? c.kind;
  const fields = cardFields(c.kind, raw, c.id).filter((f) => !f.more && f.path[0] !== "of");
  return (
    <div className="h3-col" style={{ gap: 6, padding: 8, border: "1px solid var(--h3-border)", borderRadius: 4 }}>
      <div className="h3-row">
        <b className="h3-grow">{label}{c.id ? <span className="h3-muted h3-small h3-mono"> {c.id}</span> : null}</b>
        <button className="h3-link" title="Leave it out" onClick={onRemove}>×</button>
      </div>
      {c.kind === "location" && (
        <Row label="Short name" help="How the script names it on a sequence (# sq01  porch): a word or two.">
          <input className="h3-in" value={c.id} placeholder="porch" onChange={(e) => onChange({ ...c, id: castId(e.target.value) })} />
        </Row>
      )}
      {fields.map((f) => (
        <FieldRow key={f.path.join(".")} f={f} value={shown(c.fields, f)}
          onChange={(v) => {
            const fields2 = { ...c.fields, [f.path[0]]: parsed(f, v) };
            onChange({ ...c, fields: fields2, id: f.path[0] === "name" ? castId(v) : c.id });
          }} />
      ))}
      {problem && <span className="h3-small h3-err">{problem}</span>}
    </div>
  );
}
