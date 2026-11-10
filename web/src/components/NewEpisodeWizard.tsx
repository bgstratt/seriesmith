// The new episode wizard: a new series or its next episode, in Simple and in Advanced — the idea,
// the story and who and where it's about, written in one POST /seriesmith/episode/new
// (lib/wizard.ts); the guide (FilmPath.tsx) takes it from there. Everything a person needn't decide
// is filled in, in "More". A next episode starts from its newest neighbour's series config, so the
// cast, look and settings carry over and only what's new is added. An edit made elsewhere is a
// start of its own: XmlImportPanel.

import { useEffect, useMemo, useState } from "react";
import { build, loadEpisodes, loadTargets, openBrowse, openEpisodeAt, openFilmPath, openShotForm, openWizard, setSimple } from "../actions";
import { api, host } from "../host";
import { scriptForEpisode } from "../lib/filmPath";
import { nameError } from "../lib/newEpisode";
import {
  DEFAULT_PROXY, FINAL_SIZES, PROXY_SIZES, SECTIONS, cardFields, getPath, parsed, refsPrefix, serialize, setPath, setSize,
  shapeNote, shown, sizeOf, slug, type Field, type Raw,
} from "../lib/seriesForm";
import { SIZES, listOf, newShot, type ShotForm as Shot } from "../lib/shotForm";
import { pictureOf } from "../lib/pictures";
import { sizeRule } from "../lib/size";
import {
  WIZARD_KINDS, castId, castOfConfig, castProblems, blockedScript, firstScript, seriesConfig, showFolder, withCast, withScriptNames, type NewCast,
} from "../lib/wizard";
import { useApp } from "../store";
import type { EpisodeTemplate } from "../types";
import { FloatingWindow, type Rect } from "./FloatingWindow";
import { LengthPicker } from "./LengthPicker";
import { FieldRow, SizeField } from "./SeriesForm";
import { Hover, Thumb, type Named } from "./Picture";
import { CameraField, Chips, DialogueRows, PlacePick, Row, type Cast } from "./ShotForm";
import { SkillLink } from "./SkillLink";
import { XmlImportPanel } from "./XmlImportPanel";

const RECT_KEY = "seriesmith.wizard.rect";
const IDEA = 0;
const STORY = 1;
const CAST = 2;
const STEP_NAMES = ["Idea", "Story", "Cast and places"] as const;
type Start = "board" | "script" | "agent" | "write" | "xml";

function defaultRect(): Rect {
  const W = window.innerWidth || 1280;
  const H = window.innerHeight || 800;
  const w = Math.max(420, Math.min(760, Math.round(W * 0.5)));
  return { x: Math.max(16, Math.round((W - w) / 2)), y: 52, w, h: Math.max(420, H - 110) };
}

export function NewEpisodeWizard() {
  const w = useApp((s) => s.wizard);
  if (!w) return null;
  return <Wizard key={`${w.parent}|${w.newSeries}|${w.from ?? ""}`} parent={w.parent} startNew={w.newSeries} startFrom={w.from} />;
}

const FIELD = (p: string): Field => SECTIONS.flatMap((s) => s.fields).find((f) => f.path.join(".") === p)!;

function Wizard({ parent, startNew, startFrom }: { parent: string; startNew: boolean; startFrom?: Start }) {
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
  // no locations: the first shot's place, in words (no picture of it)
  const [placeText, setPlaceText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // where the story comes from; an edit made elsewhere is imported (XmlImportPanel): a new show,
  // or the next episode of the show in `parent`
  const [from, setFrom] = useState<Start>(startFrom ?? "board");
  const [scriptText, setScriptText] = useState("");
  const onBoard = from === "board";
  const fromScript = from === "script";
  const fromAgent = from === "agent";
  const [structures, setStructures] = useState<string[]>([]);
  const [structure, setStructure] = useState("");
  const [boardMinutes, setBoardMinutes] = useState("7");
  useEffect(() => {
    if (!onBoard || structures.length) return;
    void api().structures().then((r) => {
      const all = r.structures.map((s) => s.name);
      setStructures(all);
      setStructure((now) => now || (all.find((n) => n.includes("Three-Act")) ?? all[0] ?? ""));
    }, (e) => setError((e as Error).message));
  }, [onBoard, structures.length]);
  const fromXml = from === "xml";

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
  // a single shot picks its people, so they come before it; an agent's script brings its own
  const order = from === "write" ? [IDEA, CAST, STORY] : fromAgent ? [IDEA, STORY] : [IDEA, STORY, CAST];
  const steps = order.map((i) => ({ s: STEP_NAMES[i], i }));

  // the first sequence's place: the one picked while it still exists, else the
  // first there is (worked out each time, so a place renamed while its name was
  // being typed -- "p", "po", "pond" -- is never kept)
  const place = known.locations.includes(location) ? location : (known.locations[0] ?? "");

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
    [IDEA]: !tpl ? (tplErr ?? (startNew && !title.trim() ? "Give the series a title." : startNew ? nameError(show) : "…"))
      : startNew && !title.trim() && isNewSeries ? "Give the series a title."
      : nameError(name) ?? (tpl.episodes.includes(name.trim()) ? `${name} is already there.`
        : !String(getPath(series, ["series", "id"]) ?? "").trim() ? "Give the series an id (under More)."
        : isNewSeries && !String(getPath(series, ["style", "look"]) ?? "").trim() ? "Say the look: every shot's prompt opens with it." : null),
    [STORY]: onBoard
      ? (!structure ? "Pick a structure." : !(Number(boardMinutes) > 0) ? "Say how long it runs." : null)
      : fromScript ? (!scriptText.trim() ? "Paste the script, or load its file." : null)
      : fromAgent ? null
      : !shot.action.trim() ? "Say what happens in it." : null,
    [CAST]: problems.find(Boolean)
      ?? (onBoard && !place && !placeText.trim() ? "Say where it opens: a location needs words, even with no picture." : null),
  };
  const at = Math.max(0, steps.findIndex((x) => x.i === step));
  const last = at === steps.length - 1;
  const moveTo = (i: number) => {
    // the script's people and places are the next step's cards
    if (i === CAST && fromScript && base) setCast((c) => withScriptNames(c, base, scriptText));
    setStep(i);
  };
  const go = (d: number) => moveTo(steps[Math.max(0, Math.min(steps.length - 1, at + d))].i);

  /** the shot with only the cast that still exists (one renamed after it was
   * picked would otherwise break the script) */
  const current = (sh: Shot): Shot => {
    const keep = (k: string, ids: string[]) => listOf(sh.keys[k]).filter((x) => ids.includes(x)).join(", ");
    return { ...sh, keys: { ...sh.keys, who: keep("who", known.characters.map((c) => c.id)),
      with: keep("with", known.things.map((c) => c.id)) } };
  };

  async function create() {
    if (!tpl || !full) return;
    // no location: a place of the first shot's own, described in words only
    const inWords = !place && !fromScript && !fromAgent;
    const where = inWords ? "place" : place;
    const config = inWords
      ? setPath(full, ["locations", where], { description: placeText.trim() || shot.action.trim() })
      : full;
    const epName = epTitle.trim() || (isNewSeries ? title.trim() : "");
    const scriptOut = onBoard ? blockedScript(name.trim(), epName, structure, Number(boardMinutes) * 60)
      : fromScript ? scriptForEpisode(name.trim(), epName, scriptText)
      : fromAgent ? `= ${name.trim()}${epName ? `  ${epName}` : ""}\n`
      : firstScript(name.trim(), epName, "sq01", where, current(shot));
    setBusy(true);
    setError(null);
    try {
      const res = await api().newEpisode({
        parent, name: name.trim(), title: epTitle.trim() || null,
        show: showName || null,
        series: serialize(config, tpl.series ?? "\n"),
        script: scriptOut,
      });
      host().toast(res.check.ok ? "success" : "warn", `Made ${res.episode.name}`,
        res.check.ok ? res.ep : res.check.errors[0]?.message ?? "");
      if (!fromAgent && (inWords || !known.characters.length)) {
        host().toast("warn", "Shots won't stay consistent yet",
          `${inWords ? "The place is described in words, with no picture" : "There are no characters with pictures"}: `
          + "each shot imagines it its own way. Add pictures (Refs tab: a location's plate, a character's sheet) "
          + "and the shots after that keep them.");
      }
      await loadEpisodes();
      openWizard(null);
      openShotForm(null);
      setSimple(false);                                  // a series' episodes open in Advanced
      // opened and built, so the shots are there and the refs it needs are listed
      if (await openEpisodeAt(res.ep, tpl.parent)) {
        await build();
        openFilmPath(true);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const head = (
    <>
      <button id="sm-wizard-back" className="h3-btn h3-link" title="Back to Project folders (where you were)" onClick={() => {
        if (!fromXml && (title || cast.length || shot.action || scriptText) && !window.confirm("Leave the wizard? Nothing has been written yet.")) return;
        openWizard(null);
        openBrowse({ purpose: "roots" });
      }}><i className="pi pi-angle-left" /> Project folders</button>
      <span className="h3-muted">›</span>
      <span className="h3-grow">{fromXml ? (startNew ? "New series from an edit" : "New episode from an edit") : startNew && isNewSeries ? "New series" : "New episode"}</span>
      <button className="h3-btn h3-icon" title="Close" onClick={() => {
        if (!fromXml && (title || cast.length || shot.action || scriptText) && !window.confirm("Close the wizard? Nothing has been written yet.")) return;
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
  // the steps differ by start; the one you're on stays if the new start has it
  const pickStart = (next: Start) => {
    setFrom(next);
    if (next === "agent" && step === CAST) setStep(STORY);
  };
  const loadScript = (file: File | undefined) => {
    if (file) void file.text().then(setScriptText, (e) => setError((e as Error).message));
  };

  return (
    <FloatingWindow storageKey={RECT_KEY} defaultRect={defaultRect} head={head} minW={420} minH={360}>
      {(
        <div id="sm-wizard-from" className="h3-row" style={{ padding: "6px 10px", gap: 6, borderBottom: "1px solid var(--h3-border)" }}>
          <span className="h3-small h3-muted">Start from</span>
          <button id="sm-wizard-board" className={`h3-btn${onBoard ? " h3-on" : ""}`} title="A story structure and a length: you block it in on the storyboard" onClick={() => pickStart("board")}>A structure</button>
          <button id="sm-wizard-script" className={`h3-btn${fromScript ? " h3-on" : ""}`} title="A finished seriesmith script, pasted or from a file" onClick={() => pickStart("script")}>A script</button>
          <button id="sm-wizard-agent" className={`h3-btn${fromAgent ? " h3-on" : ""}`} title="Written by the script-writing skill in your own agent, and sent here over MCP" onClick={() => pickStart("agent")}>My agent</button>
          <button id="sm-wizard-write" className={`h3-btn${from === "write" ? " h3-on" : ""}`} title="One shot you describe now; add the rest later" onClick={() => pickStart("write")}>A single shot</button>
          <button id="sm-wizard-xml" className={`h3-btn${from === "xml" ? " h3-on" : ""}`} onClick={() => pickStart("xml")}>An edit (FCP7 XML)…</button>
        </div>
      )}
      {fromXml ? (
        <div className="h3-col" style={{ padding: 10, overflow: "auto", flex: 1, minHeight: 0 }}>
          <XmlImportPanel parent={parent} inShow={!startNew} />
        </div>
      ) : (<>
      <div className="h3-row" style={{ padding: "6px 10px", gap: 6, borderBottom: "1px solid var(--h3-border)" }}>
        {steps.map(({ s, i }, n) => (
          <button key={s} className={`h3-btn${i === step ? " h3-on" : ""}`} disabled={n > at && !!blockers[step]}
            onClick={() => moveTo(i)}>{n + 1}. {i === STORY && from === "write" ? "First shot" : s}</button>
        ))}
      </div>
      <div id="sm-wizard" className="h3-col" style={{ padding: 10, gap: 10, overflow: "auto", flex: 1, minHeight: 0 }}>
        {step === IDEA && (
          <>
            {startNew && (
              <Row label="Series title" help="The show's name, and the start of its id.">
                <input className="h3-in" autoFocus value={title} placeholder="First Light" onChange={(e) => setTitleAll(e.target.value)} />
              </Row>
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
              <Row label="Series title" help="The show's name.">
                <input className="h3-in" value={title} placeholder="First Light" onChange={(e) => setTitleAll(e.target.value)} />
              </Row>
            )}
            {(!startNew || !isNewSeries) && (
              <Row label="Episode title" help="Written under the series title on the master; optional.">
                <input className="h3-in" value={epTitle} placeholder="The Pier" onChange={(e) => setEpTitle(e.target.value)} />
              </Row>
            )}
            {isNewSeries && (
              <FieldRow f={FIELD("style.look")} value={shown(series, FIELD("style.look"))}
                onChange={(v) => setSeries((r) => setPath(r, FIELD("style.look").path, parsed(FIELD("style.look"), v)))}
                lookParts={(getPath(series, ["style", "look_parts"]) as Record<string, string> | undefined) ?? null}
                onLookParts={(lp) => setSeries((r) => setPath(r, ["style", "look_parts"], lp))} />
            )}
            <details id="sm-wizard-more">
              <summary className="h3-small">More: folders, model, sizes</summary>
              <div className="h3-col" style={{ gap: 10, paddingTop: 8 }}>
                {startNew && (
                  <Row label="Show folder" help={`A folder of its own in ${parent}: its episodes go in it, with one refs folder beside them that they share.`}>
                    <input className="h3-in h3-mono" value={show} placeholder="First_Light"
                      onChange={(e) => { setShow(e.target.value.trim()); setShowTouched(true); }} />
                  </Row>
                )}
                <Row label="Episode" help="The folder and the script's name (ep01 → ep01/ep01.md).">
                  <input className="h3-in h3-mono" style={{ width: 120 }} value={name}
                    onChange={(e) => { setName(e.target.value.trim()); setNameTouched(true); }} />
                </Row>
                {startNew && isNewSeries && (
                  <Row label="Episode title" help="Written under the series title on the master; optional.">
                    <input className="h3-in" value={epTitle} placeholder="The Pier" onChange={(e) => setEpTitle(e.target.value)} />
                  </Row>
                )}
                {isNewSeries && (
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
                    {["audio.mode", "speech.pace"].map((p) => (
                      <FieldRow key={p} f={FIELD(p)} value={shown(series, FIELD(p))}
                        onChange={(v) => setSeries((r) => setPath(r, FIELD(p).path, parsed(FIELD(p), v)))} />
                    ))}
                    <div className="h3-small h3-muted">The rest (models for pictures and voices, finishing, the intro and outro) is in Series settings, any time.</div>
                  </>
                )}
              </div>
            </details>
          </>
        )}

        {step === STORY && fromScript && (
          <>
            <Row label="The script" help="A seriesmith script. To turn a screenplay into one, use the script-writing skill in your agent.">
              <textarea id="sm-wizard-script-text" className="h3-in h3-mono" rows={14} style={{ resize: "vertical" }} value={scriptText}
                onChange={(e) => setScriptText(e.target.value)} />
            </Row>
            <label className="h3-row h3-small">Or load a file
              <input type="file" accept=".md,.txt" onChange={(e) => loadScript(e.target.files?.[0])} />
            </label>
            <div className="h3-small h3-muted">The people, things and places it names get cards on the next step.</div>
            <SkillLink />
          </>
        )}
        {step === STORY && fromAgent && (
          <div className="h3-col h3-small" style={{ gap: 6 }}>
            <span>This makes the series and an empty episode. Then write the script with the script-writing skill in the agent you already use, connected with <code>seriesmith mcp</code>, and have it save the script to the episode.</span>
            <SkillLink />
            <span>After Create, the guide gives you instructions to paste into your agent.</span>
            <span className="h3-muted">It moves on by itself when the script arrives.</span>
          </div>
        )}

        {step === CAST && base && (
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
            {!known.locations.length && !fromScript && (
              <div className="h3-note h3-small">
                No location yet. That's allowed: the first place can be described in words. But
                H3 keeps a series looking the same from shot to shot by its pictures: without a picture of the place (and
                of the people), each shot imagines them its own way. Add them here, or later in the Refs tab.
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
            {onBoard && !place && (
              <Row label="Where it opens" help="This series has no locations yet, and a sequence needs one. Words are enough: it has no picture, so it may look different from shot to shot.">
                <input className="h3-in" value={placeText} placeholder="a small pond at dawn, reeds, mist on the water" onChange={(e) => setPlaceText(e.target.value)} />
              </Row>
            )}
          </>
        )}

        {step === STORY && onBoard && (
          <>
            <Row label="Structure" help="The beats it starts from. You can change it, and add your own, on the storyboard.">
              <select className="h3-in" value={structure} onChange={(e) => setStructure(e.target.value)}>
                {structures.map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </Row>
            <Row label="Minutes" help="How long it's meant to run. It sets every beat's target, and you can change it later.">
              <input className="h3-in" type="number" min="0.1" step="any" value={boardMinutes} onChange={(e) => setBoardMinutes(e.target.value)} />
            </Row>
          </>
        )}
        {step === STORY && from === "write" && (
          <>
            <div className="h3-small h3-muted">The episode's first shot, to start from; the shot form adds the rest.</div>
            <Row label="Where" help={known.locations.length
              ? "The first sequence's location: every shot in it happens here."
              : "Described in words (empty: from what happens). It has no picture, so it may look different from shot to shot."}>
              {known.locations.length
                ? <PlacePick ep={picEp} value={place} places={placeList} empty="pick a location…" onChange={setLocation} />
                : <input className="h3-in" value={placeText} placeholder="a small pond at dawn, reeds, mist on the water"
                    onChange={(e) => setPlaceText(e.target.value)} />}
            </Row>
            <Row label="Who's in it" help="The characters on screen, in order.">
              <Chips ep={picEp} value={listOf(shot.keys.who)} options={castList} onChange={(v) => setKey("who", v.join(", "))}
                add={() => { setStep(CAST); setCast([...cast, { kind: "character", id: "", fields: {} }]); }} addLabel="+ Character" />
            </Row>
            {thingList.length > 0 && (
              <Row label="With" help="Props and vehicles whose look matters.">
                <Chips ep={picEp} value={listOf(shot.keys.with)} options={thingList} onChange={(v) => setKey("with", v.join(", "))}
                  add={() => { setStep(CAST); setCast([...cast, { kind: "prop", id: "", fields: {} }]); }} addLabel="+ Prop" />
              </Row>
            )}
            <div className="h3-row h3-wrap" style={{ gap: 10 }}>
              <Row label="Size" help="How much of them the frame holds.">
                <select className="h3-in" value={shot.keys.size ?? ""} onChange={(e) => setKey("size", e.target.value)}>
                  {SIZES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
                </select>
              </Row>
              <Row label="Length" help="Seconds on H3's grid; auto fits the dialogue.">
                <LengthPicker value={shot.keys.dur ?? ""} onChange={(v) => setKey("dur", v)} auto model />
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
      </>)}
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
          <input className="h3-in" value={c.id} placeholder="porch" disabled={c.fixed} onChange={(e) => onChange({ ...c, id: castId(e.target.value) })} />
        </Row>
      )}
      {fields.map((f) => (
        <FieldRow key={f.path.join(".")} f={f} value={shown(c.fields, f)}
          onChange={(v) => {
            const fields2 = { ...c.fields, [f.path[0]]: parsed(f, v) };
            onChange({ ...c, fields: fields2, id: f.path[0] === "name" && !c.fixed ? castId(v) : c.id });
          }} />
      ))}
      {problem && <span className="h3-small h3-err">{problem}</span>}
    </div>
  );
}
