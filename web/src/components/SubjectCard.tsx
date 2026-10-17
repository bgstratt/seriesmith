// A cast card: one character, group, prop, vehicle, voice or location of the
// series config as a form (lib/seriesForm.ts cardFields), with its picture's
// takes beneath it — the Refs tab's own detail (generate, import, pick) — so
// you write the design and make the picture in one place. A new one is added
// to series.json on Save, its first picture queued with it (FirstStep: Add and
// generate, Add and tour…); an existing one changes only its own entry.

import { useEffect, useMemo, useState } from "react";
import { afterAuthoredWrite, loadRefs, openSubjectCard } from "../actions";
import { api, host } from "../host";
import {
  CARD_KINDS, blockOf, cardFields, cardKindOf, entryFor, getPath, idProblem, isEmpty, refIdOf, refsPrefix, serialize, setPath, slug,
  type CardKind, type Raw,
} from "../lib/seriesForm";
import { useApp } from "../store";
import { MoreToggle } from "./Fields";
import { useFirstStep } from "./FirstStep";
import { usePictureBrowse } from "./Picture";
import { FloatingWindow, type Rect } from "./FloatingWindow";
import { RefDetail } from "./RefsTab";
import { CheckMessages, FieldRow, FileLine, SaveBar } from "./SeriesForm";
import { useSeriesConfig } from "./useSeriesConfig";

const RECT_KEY = "seriesmith.subjectcard.rect";

function defaultRect(): Rect {
  const W = window.innerWidth || 1280;
  const H = window.innerHeight || 800;
  const w = Math.max(380, Math.min(620, Math.round(W * 0.4)));
  return { x: Math.max(16, Math.min(420, W - w - 16)), y: 72, w, h: Math.max(360, H - 140) };
}

/** A supplied picture of a character is one whole picture of them unless it is
 * shaped like a sheet of panels side by side (refs.STRIP_RATIO: 4:1 is a
 * four-panel sheet). An unknown size is taken as one picture, as before. */
export function isOnePicture(width: number | null | undefined, height: number | null | undefined): boolean {
  return !(width && height && width / height >= 2.5);
}

/** `sheet_panels: 1` on a character, written to the series config as it is now. */
async function markOnePicture(ep: string, block: string, id: string) {
  const cur = await api().source(ep, "series");
  const raw = JSON.parse(cur.text) as Raw;
  if (!getPath(raw, [block, id])) return;
  const r = await api().putSource({ ep, file: "series", text: serialize(setPath(raw, [block, id, "sheet_panels"], 1), cur.text),
                                    base_hash: cur.hash, rebuild: true });
  afterAuthoredWrite(r.build);
}

export function SubjectCardWindow() {
  const card = useApp((s) => s.subjectCard);
  const ep = useApp((s) => s.ep);
  if (!card || !ep) return null;
  return <SubjectCard key={`${ep}|${card.kind}|${card.id ?? "+"}`} ep={ep} kind={card.kind} id0={card.id} />;
}

function SubjectCard({ ep, kind: asked, id0 }: { ep: string; kind: CardKind; id0: string | null }) {
  const sc = useSeriesConfig(ep);
  const isNew = id0 === null;
  // an existing entry is what the config says it is (the Refs tab can't tell a
  // group or a voice-only character from a character)
  const kind: CardKind = !isNew && sc.base ? cardKindOf(sc.base, blockOf(asked), id0!) : asked;
  const [id, setId] = useState(id0 ?? "");
  const [idTouched, setIdTouched] = useState(false);
  const [form, setForm] = useState<Raw>({});
  const [more, setMore] = useState(false);
  // simple mode: the main fields, and a picture you have (imported on save);
  // nothing under More
  const simple = useApp((s) => s.simple);
  const [ownPic, setOwnPic] = useState("");
  const browsePic = usePictureBrowse(`card:${asked}:${id0 ?? "new"}`, `${asked} picture`, (p) => setOwnPic(p), true);
  // a new card's first picture, queued with Add (not simple mode: its picture
  // is the one you have, or made from the words when it's used)
  const first = useFirstStep({ ep, kind, of: form.of == null ? "" : String(form.of), pic: ownPic, browse: browsePic,
                               clearPic: () => setOwnPic("") });
  const firstStep = isNew && !simple;
  const block = blockOf(kind);
  const label = CARD_KINDS.find((c) => c.kind === kind)!.label;
  const before = sc.base && !isNew ? (getPath(sc.base, [block, id]) as Raw | undefined) : undefined;

  // the fields start from the entry as it is on disk
  useEffect(() => {
    if (!sc.base) return;
    const e = isNew ? {} : ((getPath(sc.base, [block, id0!]) ?? {}) as Raw);
    setForm(Object.fromEntries(Object.entries(e).filter(([, v]) => typeof v !== "object")));
  }, [sc.base]);

  const fields = useMemo(() => (sc.base ? cardFields(kind, sc.base, id) : []), [sc.base, kind, id]);

  const prefix = sc.base ? refsPrefix(sc.base) : "../refs/";
  const problem = isNew && sc.base ? idProblem(sc.base, id) : "";
  const changed = !!sc.base && JSON.stringify(entryFor(kind, before, form, id, prefix)) !== JSON.stringify(before ?? {});
  const required = kind === "location" ? "description" : kind === "voice" ? "voice" : "design";
  const missing = isEmpty(form[required])
    ? `${required[0].toUpperCase()}${required.slice(1)} is what the ${kind === "location" ? "plate" : kind === "voice" ? "voice" : "picture"} is made from: fill it in.`
    : "";

  const setField = (k: string, v: string) => {
    setForm((f) => ({ ...f, [k]: v }));
    if (isNew && k === "name" && !idTouched) setId(slug(v.replace(/^(the|a|an)\s+/i, "")));
  };

  async function save() {
    if (!sc.base || problem || missing || (firstStep && first.missing)) return;
    const entry = entryFor(kind, before, form, id, prefix);
    const next = setPath(sc.base, [block, id], entry);
    if (await sc.save(next, `${label} ${id}`)) {
      if (ownPic) {
        // the picture you have, as its first candidate, made live
        try {
          const t = await api().refsImport({ ep, ref: refIdOf(kind, id), view: kind === "character" ? "sheet" : null,
                                             source_path: ownPic, pick: true });
          setOwnPic("");
          // a character's picture is one whole picture of them (sheet_panels: 1)
          // unless it is shaped like a sheet of panels side by side
          if (kind === "character" && !form.sheet_panels && isOnePicture(t.width, t.height)) await markOnePicture(ep, block, id);
        } catch (e) {
          host().toast("error", `${id}: the picture wasn't taken`, (e as Error).message);
        }
      }
      if (firstStep) await first.run(ep, id);
      void loadRefs(ep);
      if (isNew) openSubjectCard({ kind, id });
    }
  }

  async function remove() {
    if (!sc.base || isNew) return;
    if (!window.confirm(`Remove ${id} from series.json? Its pictures stay on disk; shots that name it stop building until they don't.`)) return;
    const blk = { ...((getPath(sc.base, [block]) ?? {}) as Raw) };
    delete blk[id];
    if (await sc.save({ ...sc.base, [block]: blk }, `${label} ${id} removed`)) {
      void loadRefs(ep);
      openSubjectCard(null);
    }
  }

  const head = (
    <>
      <i className={kind === "location" ? "pi pi-image" : kind === "voice" ? "pi pi-volume-up" : kind === "prop" || kind === "vehicle" ? "pi pi-box" : "pi pi-user"} />
      <span className="h3-grow">{isNew ? `New ${label.toLowerCase()}` : `${label}: ${(form.name as string) || id}`}{changed ? " •" : ""}</span>
      <button className="h3-btn h3-icon" title="Close" onClick={() => {
        if (changed && !window.confirm("Close without saving?")) return;
        openSubjectCard(null);
      }}><i className="pi pi-times" /></button>
    </>
  );

  return (
    <FloatingWindow storageKey={RECT_KEY} defaultRect={defaultRect} head={head} minW={360} minH={280}>
      <div className="h3-col" style={{ padding: 10, overflow: "auto", height: "100%", gap: 10 }}>
        <FileLine sc={sc} />
        {sc.base && (
          <>
            {/* simple mode: a place's id is its name; anyone else's follows their
                name, shown only when it clashes */}
            {(!simple || kind === "location" || (!!id && !!problem)) && (
              <div className="h3-col" style={{ gap: 2 }}>
                <span className="h3-small"><b>{simple && kind === "location" ? "Name" : "Id"}</b></span>
                <input className="h3-in" value={id} disabled={!isNew}
                  placeholder={simple && kind === "location" ? "harbour" : ""}
                  onChange={(e) => { setIdTouched(true); setId(simple ? slug(e.target.value) : e.target.value.trim()); }} />
                <span className={`h3-small ${problem && id ? "h3-err" : "h3-muted"}`}>
                  {(problem && id) ? problem : simple
                    ? (kind === "location" ? "A word or two to pick it by." : "")
                    : (isNew
                      ? `What the script calls it (who: ${id || "ada"}${kind === "location" ? `, plate: ${id || "porch"}` : ""}). Made from the name; it can't change once saved.`
                      : "What the script calls it. It can't change here: shots name it.")}
                </span>
              </div>
            )}
            {fields.filter((f) => !f.more && !(simple && f.path[0] === "of")).map((f) => (
              <FieldRow key={f.path.join(".")} f={f} value={form[f.path[0]] == null ? "" : String(form[f.path[0]])}
                onChange={(v) => setField(f.path[0], v)} />
            ))}
            {simple && kind !== "voice" && kind !== "group" && (
              <div className="h3-col" style={{ gap: 2 }}>
                <span className="h3-small"><b>A picture you have</b> <span className="h3-muted">(optional)</span></span>
                <div className="h3-row" style={{ gap: 4 }}>
                  <span className="h3-small h3-mono h3-ell h3-grow" title={ownPic}>{ownPic ? ownPic.split(/[\\/]/).pop() : "none"}</span>
                  <button className="h3-btn" onClick={browsePic}>Choose…</button>
                  {ownPic && <button className="h3-link" title="No picture" onClick={() => setOwnPic("")}>×</button>}
                </div>
                <span className="h3-small h3-muted">
                  {kind === "location" ? "A picture of the place; without one it is made from the description." :
                    "A picture of them (a portrait, a full figure); without one it is made from the description."}
                </span>
              </div>
            )}
            {!simple && fields.some((f) => f.more) && (
              <MoreToggle open={more} onToggle={setMore}
                label={`More: ${fields.filter((f) => f.more).map((f) => f.label.toLowerCase()).join(", ")}`} />
            )}
            {more && !simple && (
              <div className="h3-col" style={{ gap: 10, paddingLeft: 14, borderLeft: "2px solid var(--h3-border)" }}>
                {fields.filter((f) => f.more).map((f) => (
                  <FieldRow key={f.path.join(".")} f={f} value={form[f.path[0]] == null ? "" : String(form[f.path[0]])}
                    onChange={(v) => setField(f.path[0], v)} />
                ))}
              </div>
            )}
            {missing && <span className="h3-small h3-warn">{missing}</span>}
            <CheckMessages sc={sc} />
            {!isNew && <Pictures ep={ep} kind={kind} id={id} changed={changed} />}
            {firstStep && first.ui}
            {firstStep && first.missing && <span className="h3-small h3-warn">{first.missing}</span>}
          </>
        )}
      </div>
      <SaveBar dirty={changed && !problem && !missing && !(firstStep && first.missing)} saving={sc.saving}
        status={isNew && !changed ? "Not added yet" : changed && (problem || missing || (firstStep && first.missing)) ? "Not saved: fill in what's missing above" : undefined}
        onRevert={() => {
          const e = isNew ? {} : ((getPath(sc.base ?? {}, [block, id]) ?? {}) as Raw);
          setForm(Object.fromEntries(Object.entries(e).filter(([, v]) => typeof v !== "object")));
        }}
        onSave={() => void save()} saveLabel={isNew ? (firstStep ? first.verb : "Add") : "Save"}
        extra={!isNew ? <button className="h3-btn" title={`Remove ${id} from series.json`} onClick={() => void remove()}><i className="pi pi-trash" /></button> : undefined} />
    </FloatingWindow>
  );
}

/** The entry's picture (and a character's voice) as the Refs tab shows it. */
function Pictures({ ep, kind, id, changed }: { ep: string; kind: CardKind; id: string; changed: boolean }) {
  const refs = useApp((s) => s.refs[ep]);
  useEffect(() => {
    if (!refs) void loadRefs(ep);
  }, [ep]);
  const pic = kind === "voice" ? null : refs?.find((r) => r.id === refIdOf(kind, id));
  const voice = kind === "character" || kind === "voice" ? refs?.find((r) => r.id === `voice:${id}`) : null;
  return (
    <div className="h3-col" style={{ gap: 6 }}>
      {changed && <span className="h3-small h3-muted">Save first: a picture is made from what's saved.</span>}
      {pic && (
        <div className="h3-col" style={{ gap: 4 }}>
          <div className="h3-h">{kind === "location" ? "Plate" : kind === "character" ? "Sheet" : "Picture"}</div>
          <RefDetail ep={ep} r={pic} />
        </div>
      )}
      {voice && (
        <div className="h3-col" style={{ gap: 4 }}>
          <div className="h3-h">Voice sample</div>
          <RefDetail ep={ep} r={voice} />
        </div>
      )}
      {refs && !pic && kind !== "voice" && <span className="h3-small h3-muted">Not in the refs list yet (refresh the Refs tab after saving).</span>}
    </div>
  );
}
