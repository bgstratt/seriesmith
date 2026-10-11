// A cast card: one character, group, prop, vehicle, voice or location of the
// series config as a form (lib/seriesForm.ts cardFields), with its picture's
// takes beneath it — the Refs tab's own detail (generate, import, pick) — so
// you write the design and make the picture in one place. A new one is added
// to series.json on Save; an existing one changes only its own entry.

import { useEffect, useMemo, useState } from "react";
import { loadRefs, openSubjectCard } from "../actions";
import {
  CARD_KINDS, blockOf, cardFields, cardKindOf, entryFor, getPath, idProblem, isEmpty, refIdOf, refsPrefix, setPath, slug,
  type CardKind, type Raw,
} from "../lib/seriesForm";
import { useApp } from "../store";
import { MoreToggle } from "./Fields";
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
    if (!sc.base || problem || missing) return;
    const entry = entryFor(kind, before, form, id, prefix);
    const next = setPath(sc.base, [block, id], entry);
    if (await sc.save(next, `${label} ${id}`)) {
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
            <div className="h3-col" style={{ gap: 2 }}>
              <span className="h3-small"><b>Id</b></span>
              <input className="h3-in" value={id} disabled={!isNew}
                onChange={(e) => { setIdTouched(true); setId(e.target.value.trim()); }} />
              <span className={`h3-small ${problem ? "h3-err" : "h3-muted"}`}>
                {problem || (isNew
                  ? `What the script calls it (who: ${id || "ada"}${kind === "location" ? `, plate: ${id || "porch"}` : ""}). Made from the name; it can't change once saved.`
                  : "What the script calls it. It can't change here: shots name it.")}
              </span>
            </div>
            {fields.filter((f) => !f.more).map((f) => (
              <FieldRow key={f.path.join(".")} f={f} value={form[f.path[0]] == null ? "" : String(form[f.path[0]])}
                onChange={(v) => setField(f.path[0], v)} />
            ))}
            {fields.some((f) => f.more) && (
              <MoreToggle open={more} onToggle={setMore}
                label={`More: ${fields.filter((f) => f.more).map((f) => f.label.toLowerCase()).join(", ")}`} />
            )}
            {more && (
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
            {isNew && (
              <div className="h3-small h3-muted">
                Save it, and its picture can be generated, imported or picked here.
              </div>
            )}
          </>
        )}
      </div>
      <SaveBar dirty={changed && !problem && !missing} saving={sc.saving}
        status={isNew && !changed ? "Not added yet" : changed && (problem || missing) ? "Not saved: fill in what's missing above" : undefined}
        onRevert={() => {
          const e = isNew ? {} : ((getPath(sc.base ?? {}, [block, id]) ?? {}) as Raw);
          setForm(Object.fromEntries(Object.entries(e).filter(([, v]) => typeof v !== "object")));
        }}
        onSave={() => void save()} saveLabel={isNew ? "Add" : "Save"}
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
