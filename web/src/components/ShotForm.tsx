// The shot form: one shot of the script as fields — who's in it, the framing
// and length, what happens, what's said, the camera and the sound — with what
// the model will be told beside it, compiled as you type
// (POST /seriesmith/shot/preview), and the dialogue's pace against the shot's
// length. Saving rewrites only this shot's lines in the script (lib/shotForm.ts)
// through PUT /seriesmith/source: the check, the history copy and the rebuild.

import { useEffect, useMemo, useRef, useState } from "react";
import { afterAuthoredWrite, copyText, loadRefs, openShotForm, openSubjectCard, requestRender, select, showInScript } from "../actions";
import { api, host } from "../host";
import { pictureOf } from "../lib/pictures";
import { getPath, type Raw } from "../lib/seriesForm";
import {
  CAMERA_AMPLITUDE, CAMERA_MOVES, KEYFRAME_METHODS, CAMERA_SPEED, SIZES, cameraLine, insertAfter, listOf, newShot,
  parseShot, replaceLines, sequenceAt, sequencesOf, shotIdBetween, writeShot, type DialogueLine, type ShotForm as Form,
} from "../lib/shotForm";
import { clearDraft, keptAt, readDraft, useDraft } from "../lib/drafts";
import { conflictOf } from "../lib/sourceSession";
import { isHosted } from "../lib/targets";
import { useApp } from "../store";
import type { Ref, ShotPreview, SourceDoc } from "../types";
import { LoraLine, ModelLine, MoreToggle } from "./Fields";
import { FloatingWindow, type Rect } from "./FloatingWindow";
import { LengthPicker } from "./LengthPicker";
import { PresetPicker, useCameraTiles, useFramingTiles, useLensTiles } from "./PresetPicker";
import { Hover, PicturePicker, Thumb, usePictureBrowse, type Named } from "./Picture";
import { useSeriesConfig } from "./useSeriesConfig";
import { finishDroppedFile, isPicture } from "../takeActions";
import { profileFromShot, profileNameOk, profilesOf, setProfile, shotOnProfile } from "../lib/profiles";
import { ModelOptions, ModelsButton } from "./Targets";

const RECT_KEY = "seriesmith.shotform.rect";
const PREVIEW_MS = 600;

function defaultRect(): Rect {
  const W = window.innerWidth || 1280;
  const H = window.innerHeight || 800;
  const w = Math.max(420, Math.min(900, Math.round(W * 0.6)));
  return { x: Math.max(16, Math.min(390, W - w - 16)), y: 52, w, h: Math.max(400, H - 110) };
}

export function ShotFormWindow() {
  const f = useApp((s) => s.shotForm);
  const ep = useApp((s) => s.ep);
  if (!f || !ep) return null;
  return <ShotFormBody key={`${ep}|${f.shot ?? `+${f.after ?? ""}|${f.before ?? ""}|${f.file?.name ?? ""}`}`} ep={ep} shot={f.shot} after={f.after}
    before={f.before ?? null} file={f.file ?? null} dur={f.dur ?? null} left={f.left ?? null} />;
}

export interface Cast extends Named { kind: string; onScreen: boolean }

function castOf(raw: Raw | null, refs: Ref[] | undefined): { chars: Cast[]; things: Cast[]; places: Named[]; profiles: string[] } {
  const subj = (getPath(raw ?? {}, ["subjects"]) ?? {}) as Record<string, Raw>;
  const all = Object.entries(subj).map(([id, e]) => ({
    id, name: typeof e?.name === "string" ? e.name : id,
    kind: typeof e?.kind === "string" ? e.kind : (e?.of && typeof subj[e.of as string]?.kind === "string" ? subj[e.of as string].kind as string : "character"),
    onScreen: !!(e?.sheet || e?.of || e?.design),
    pic: pictureOf(raw, refs, "subjects", id),
  }));
  const locs = (getPath(raw ?? {}, ["locations"]) ?? {}) as Record<string, Raw>;
  return {
    chars: all.filter((c) => c.kind === "character"),
    things: all.filter((c) => c.kind === "prop" || c.kind === "vehicle"),
    places: Object.keys(locs).map((id) => ({ id, name: id.replace(/_/g, " "), pic: pictureOf(raw, refs, "locations", id) })),
    profiles: Object.keys((getPath(raw ?? {}, ["profiles"]) ?? {}) as object),
  };
}

function ShotFormBody({ ep, shot, after, before = null, file = null, dur = null, left = null }: {
  ep: string; shot: string | null; after: string | null;
  /** a new shot ahead of this one (a file dropped before the first clip) */
  before?: string | null;
  /** a video dropped between two clips: imported as the new shot's take on Save
   * (a picture: its first keyframe) */
  file?: File | null; dur?: string | null; left?: string | null;
}) {
  const pass = useApp((s) => s.pass);
  const targets = useApp((s) => s.targets);
  const sc = useSeriesConfig(ep);
  const [doc, setDoc] = useState<SourceDoc | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  // the framings as pictures (seriesmith/presets/framing.json)
  const framings = useFramingTiles();
  const lenses = useLensTiles();
  const [orig, setOrig] = useState<string>("");
  const [seq, setSeq] = useState<string>("");          // a new shot's sequence ("+": a new one)
  const [newSeq, setNewSeq] = useState({ id: "", location: "" });
  const [preview, setPreview] = useState<ShotPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [more, setMore] = useState(false);
  const [showPrompt, setShowPrompt] = useState(true);
  const isNew = shot === null;
  // unsaved edits from before a reload (lib/drafts): put back when the form opens on
  // the shot as they were made against; offered when the script has changed it since
  const draftKey = `shotform|${ep}|${shot ?? ""}`;
  const [kept, setKept] = useState<{ form: Form; at: number; stale: boolean } | null>(null);

  // the script, and the shot's block in it (or a new shot's place); `restore`: a
  // draft kept from before a reload goes back in (opening, not Revert or a reload)
  async function load(restore = false) {
    setError(null);
    try {
      const d = await api().source(ep, "script");
      setDoc(d);
      const lines = d.text.split("\n");
      if (!isNew) {
        const span = d.shots.find((x) => x.id === shot);
        if (!span) {
          setError(`${shot} isn't in the script any more.`);
          return;
        }
        const f = parseShot(lines.slice(span.line - 1, span.end_line));
        const text = writeShot(f).join("\n");
        const dr = restore ? readDraft<{ form: Form; orig: string }>(draftKey) : null;
        const k = dr ? { form: dr.value.form, at: dr.at, stale: dr.value.orig !== text } : null;
        setKept(k);
        setForm(k && !k.stale ? k.form : f);
        setOrig(text);
      } else {
        const ids = d.shots.map((x) => x.id);
        const b = before ? ids.indexOf(before) : -1;
        const i = b >= 0 ? b - 1 : after ? ids.indexOf(after) : ids.length - 1;
        const id = shotIdBetween(i >= 0 ? ids[i] : null, (b >= 0 || i >= 0) && i + 1 < ids.length ? ids[i + 1] : null, new Set(ids));
        const seqs = sequencesOf(d.text);
        const at = b >= 0 ? sequenceAt(seqs, d.shots[b].line)?.id
          : i >= 0 ? sequenceAt(seqs, d.shots[i].line)?.id : seqs[seqs.length - 1]?.id;
        setSeq(at ?? "+");
        const f = newShot(id);
        if (dur) f.keys.dur = dur;
        setForm(f);
        setOrig("");
      }
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    void load(true);
  }, [ep, shot]);

  const seqs = useMemo(() => (doc ? sequencesOf(doc.text) : []), [doc]);
  const refs = useApp((s) => s.refs[ep]);
  useEffect(() => {
    if (!refs) void loadRefs(ep);
  }, [ep]);
  const cast = useMemo(() => castOf(sc.base, refs), [sc.base, refs]);
  // a card saved a new character or place (+ Character, + Location): the series
  // config again, so it can be picked without reopening the form
  const sourceN = useApp((s) => s.sourceN);
  useEffect(() => {
    if (sourceN) void sc.reload();
  }, [sourceN]);
  // ... and one added from this form goes straight into the field it was added from
  const card = useApp((s) => s.subjectCard);
  const adding = useRef<{ kind: string; put: (id: string) => void } | null>(null);
  const addFrom = (kind: "character" | "prop" | "location", put: (id: string) => void) => {
    adding.current = { kind, put };
    openSubjectCard({ kind, id: null });
  };
  useEffect(() => {
    const a = adding.current;
    if (!a) return;
    if (!card || card.kind !== a.kind) {
      adding.current = null;                       // closed without saving one
    } else if (card.id) {
      adding.current = null;
      a.put(card.id);
    }
  }, [card]);
  const block = form ? writeShot(form) : [];
  const dirty = !!form && block.join("\n") !== orig;
  const forgetDraft = useDraft(draftKey, useMemo(() => ({ form, orig }), [form, orig]), dirty && !isNew);

  /** "Save as profile…": this shot's own lens and render settings as a profile in the
   * series config (saved now), and the shot put on it (saved with the shot). */
  async function saveAsProfile() {
    if (!form || !sc.base) return;
    const p = profileFromShot(form.keys, form.other);
    const name = window.prompt("Name the profile (what shots name with profile:), e.g. flashback", "")?.trim();
    if (!name) return;
    if (!profileNameOk(name)) {
      setError("A profile's name takes letters, digits, _ and - only.");
      return;
    }
    if (profilesOf(sc.base)[name] && !window.confirm(`Replace the profile “${name}” with this shot's settings?`)) return;
    if (await sc.save(setProfile(sc.base, name, p), `Profile “${name}”`)) setForm(shotOnProfile(form, name));
  }

  /** the script with this shot as the form has it */
  function scriptText(): string | null {
    if (!doc || !form) return null;
    if (!isNew) {
      const span = doc.shots.find((x) => x.id === shot);
      return span ? replaceLines(doc.text, span.line, span.end_line, block) : null;
    }
    const lines = doc.text.split("\n");
    if (seq === "+") {
      const id = newSeq.id.trim() || `sq${String(seqs.length + 1).padStart(2, "0")}`;
      const header = `# ${id}${newSeq.location ? `  ${newSeq.location}` : ""}`;
      return insertAfter(doc.text, lines.length, [header, "", ...block]);
    }
    // after the chosen shot when it's in this sequence, else at the end of the sequence
    const s = seqs.find((x) => x.id === seq);
    const nextSeq = seqs.find((x) => s && x.line > s.line);
    const inSeq = doc.shots.filter((x) => s && x.line > s.line && (!nextSeq || x.line < nextSeq.line));
    const ahead = before ? inSeq.find((x) => x.id === before) : undefined;
    if (ahead) return insertAfter(doc.text, ahead.line - 1, block);
    const anchor = (after && inSeq.find((x) => x.id === after)) || inSeq[inSeq.length - 1];
    return insertAfter(doc.text, anchor ? anchor.end_line : (s ? s.line : lines.length), block);
  }

  // the preview, a moment after the last change
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => {
    window.clearTimeout(timer.current);
    const text = scriptText();
    if (!text || !form?.id) return;
    timer.current = window.setTimeout(() => {
      void api().previewShot(ep, pass, text, form.id).then(setPreview).catch((e) => setPreview({ ok: false, error: (e as Error).message }));
    }, PREVIEW_MS);
    return () => window.clearTimeout(timer.current);
  }, [JSON.stringify(block), seq, newSeq.id, newSeq.location, pass, doc?.hash]);

  async function save(render: boolean) {
    const text = scriptText();
    if (!doc || !form || !text) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api().putSource({ ep, file: "script", text, base_hash: doc.hash, rebuild: true });
      afterAuthoredWrite(r.build);
      const mine = r.check.errors.filter((m) => m.line == null || m.message.includes(form.id));
      if (mine.length) host().toast("warn", `${form.id} saved, with problems`, mine[0].message);
      else host().toast("success", `${form.id} saved`, "The episode was rebuilt.");
      select(form.id, null);
      // a file dropped between two clips: its take (a picture: its first keyframe) now, and the clip where it was dropped
      if (isNew && file && !(r.build && !r.build.ok)) await finishDroppedFile(form.id, file, left);
      if (render && !mine.length) requestRender([form.id], true, `Render ${form.id}`);
      // the script as it is now: a new shot opens as itself; an edited one
      // reads the script again (its new hash, the shot as saved), or the form
      // would still look unsaved and its next save would be refused as stale
      if (isNew) openShotForm({ shot: form.id, after: null });
      else await load();
    } catch (e) {
      setError(conflictOf(e) ? "The script changed on disk since this form opened: reload it (your edits here are lost) or save them in the Script window." : (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const set = (k: string, v: string) => setForm((f) => (f ? { ...f, keys: { ...f.keys, [k]: v } } : f));
  const setDialogue = (d: DialogueLine[]) => setForm((f) => (f ? { ...f, dialogue: d } : f));
  const videoTargets = (targets?.targets ?? []).filter((t) => t.kind === "video" && !t.draft);
  // the model this shot renders on: its own, else what the preview compiled it for
  const renderTarget = form?.keys.target || (preview?.ok ? preview.target ?? null : null);
  // a model with no steps setting (a hosted one: its preset says 0 steps)
  const renderT = videoTargets.find((t) => t.id === renderTarget);
  const noSteps = renderT?.presets?.final?.steps === 0;
  // a Comfy Router model has no file or LoRAs to pick
  const hosted = !!renderT && isHosted(renderT);


  const after0 = isNew ? after : null;
  const head = (
    <>
      <div className="h3-head-text">
        <span className="h3-kicker">{isNew ? `New shot${before ? ` · before ${before}` : after0 ? ` · after ${after0}` : ""}${file ? ` · ${file.name} as its ${isPicture(file) ? "first keyframe" : "take"}` : ""}` : "Shot"}</span>
        <div className="h3-row">
          <span className="h3-win-title">{form?.id ?? shot ?? ""}</span>
          {dirty && <span className="h3-small h3-muted">not saved</span>}
        </div>
      </div>
      {!isNew && <button className="h3-btn" title="Show this shot in the Script window" onClick={() => showInScript(shot!)}><i className="pi pi-file-edit" /> Show in script</button>}
      <button className="h3-btn h3-icon" title="Close" onClick={() => {
        if (dirty && !window.confirm("Close without saving this shot?")) return;
        forgetDraft();
        openShotForm(null);
      }}><i className="pi pi-times" /></button>
    </>
  );

  return (
    <FloatingWindow storageKey={RECT_KEY} defaultRect={defaultRect} head={head} minW={420} minH={320}>
      <div className="sm-shotform">
        <div className="h3-col sm-shotform-main">
          {error && <div className="h3-note h3-note-err">{error} <button className="h3-btn" onClick={() => void load()}>Reload</button></div>}
          {kept?.stale && form && (
            <div className="h3-note">
              You left unsaved edits to {shot} at {keptAt(kept.at)}, and the script has changed this shot since.
              {" "}<button className="h3-btn" title="Your version of the shot in place of the script's: the changes made to it since are lost when you save (Revert takes yours out again)" onClick={() => { setForm(kept.form); setKept(null); }}>Put them back</button>
              {" "}<button className="h3-btn" onClick={() => { clearDraft(draftKey); setKept(null); }}>Drop them</button>
            </div>
          )}
          {!form && !error && <div className="h3-muted">Loading…</div>}
          {form && (
            <>
              {isNew && (
                <div className="h3-card">
                  <div className="sm-form">
                    <Tip label="Shot" help="Its id: in the script's own numbering, between the shots around it." />
                    <div className="h3-row h3-wrap">
                      <input className="h3-in" aria-label="Shot id" style={{ width: 110 }} value={form.id}
                        onChange={(e) => setForm({ ...form, id: e.target.value.trim() })} />
                      <select className="h3-in" aria-label="Sequence" value={seq} onChange={(e) => setSeq(e.target.value)} title="The sequence it goes in">
                        {seqs.map((s) => <option key={s.id} value={s.id}>{s.id}{s.location ? ` · ${s.location}` : ""}</option>)}
                        <option value="+">+ a new sequence</option>
                      </select>
                      {seq === "+" && (
                        <>
                          <input className="h3-in" aria-label="New sequence id" style={{ width: 80 }} placeholder={`sq${String(seqs.length + 1).padStart(2, "0")}`}
                            value={newSeq.id} onChange={(e) => setNewSeq({ ...newSeq, id: e.target.value.trim() })} />
                          <PlacePick ep={ep} value={newSeq.location} places={cast.places} empty="its location…"
                            onChange={(v) => setNewSeq({ ...newSeq, location: v })} />
                          <button className="h3-btn h3-add"
                            onClick={() => addFrom("location", (id) => setNewSeq((n) => ({ ...n, location: id })))}>+ Location</button>
                        </>
                      )}
                    </div>
                  </div>
                </div>
              )}

              <div className="h3-card">
                <div className="sm-form">
                  <Tip label="Who" help="The characters on screen, in this order (on H3 they are the shot's pictures 1 to 3). Someone who only speaks off screen isn't here: give their line V.O. or O.S." />
                  <Chips ep={ep} value={listOf(form.keys.who)} options={cast.chars.filter((c) => c.onScreen)}
                    onChange={(v) => set("who", v.join(", "))} addLabel="+ Character"
                    add={() => addFrom("character", (id) => setForm((f) => (f ? { ...f, keys: { ...f.keys, who: [...listOf(f.keys.who), id].join(", ") } } : f)))} />
                  <Tip label="With" help="Props and vehicles whose exact look matters and recurs (each takes a picture slot). A generic mug is better in the action." />
                  <Chips ep={ep} value={listOf(form.keys.with)} options={cast.things}
                    onChange={(v) => set("with", v.join(", "))} addLabel="+ Prop"
                    add={() => addFrom("prop", (id) => setForm((f) => (f ? { ...f, keys: { ...f.keys, with: [...listOf(f.keys.with), id].join(", ") } } : f)))} />
                  <Tip label="Where" help="The location behind this shot. Empty: the sequence's location." />
                  <span className="h3-row" style={{ gap: 6 }}>
                    <PlacePick ep={ep} value={form.keys.plate ?? ""} places={cast.places} empty="the sequence's location"
                      onChange={(v) => set("plate", v)} />
                    <button className="h3-btn h3-add" onClick={() => addFrom("location", (id) => set("plate", id))}>+ Location</button>
                  </span>
                </div>
              </div>

              <div className="h3-card">
                <div className="h3-row h3-wrap" style={{ gap: 14 }}>
                  <span className="h3-row" style={{ gap: 6 }}>
                    <Tip label="Framing" help="How much of them the frame holds; the prompt opens with it." htmlFor="sm-sf-framing" />
                    <select id="sm-sf-framing" className="h3-in" value={form.keys.size ?? ""} onChange={(e) => set("size", e.target.value)}>
                      <option value="">—</option>
                      {SIZES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
                      {form.keys.size && !SIZES.some((s) => s.value === form.keys.size) && <option value={form.keys.size}>{form.keys.size}</option>}
                    </select>
                  </span>
                  <span className="h3-row" style={{ gap: 6 }}>
                    <Tip label="Lens" help="The lens this shot is shot on: one sentence the action opens with. It changes only this shot's prompt, never the pictures. With a plate as the reference, the plate keeps its own focus and framing, so a lens shows most on models that draw the place from words (LTX-2, Wan)." htmlFor="sm-sf-lens" />
                    <select id="sm-sf-lens" className="h3-in" value={form.keys.lens ?? ""} onChange={(e) => set("lens", e.target.value)}>
                      <option value="">— (the look's)</option>
                      {lenses.map((l) => <option key={l.id} value={l.id}>{l.label}</option>)}
                      {form.keys.lens && !lenses.some((l) => l.id === form.keys.lens) && <option value={form.keys.lens}>{form.keys.lens}</option>}
                    </select>
                  </span>
                  <span className="h3-row" style={{ gap: 6 }}>
                    <Tip label="Length" help="Seconds on H3's grid (other lengths round up onto the model's own; the preview says what renders); auto fits the dialogue." />
                    <LengthPicker value={form.keys.dur ?? ""} onChange={(v) => set("dur", v)} empty="—" auto model />
                  </span>
                </div>
                <PresetPicker tiles={framings} value={form.keys.size ?? ""} picked={framingId(form.keys.size)}
                  onPick={(v) => set("size", v)} title="Framing, as pictures" open={!form.keys.size} size={0.8} />
                <PresetPicker tiles={lenses} value={form.keys.lens ?? ""} picked={form.keys.lens || null}
                  onPick={(v) => set("lens", form.keys.lens === v ? "" : v)} title="Lens, as pictures" open={false} size={0.8} />
                {form.keys.lens && (
                  <span className="h3-small h3-muted">
                    A lens is one sentence in this shot's prompt. With a plate, the plate keeps its own focus and framing, so it may show little: it shows most on models that draw the place from words (LTX-2, Wan).
                  </span>
                )}
                <div className="h3-col" style={{ gap: 4 }}>
                  <span className="h3-card-title" title="What is visibly happening, present tense, concrete and physical. This shot only: the model remembers nothing of the shot before, so say it fresh. Not how anyone feels.">
                    What happens <i className="pi pi-info-circle sm-tip-i" />
                  </span>
                  <textarea className="h3-in sm-prompt" aria-label="What happens" rows={4} value={form.action}
                    placeholder="Ada steps out onto the wet porch and stops, looking at the mist on the lawn."
                    onChange={(e) => setForm({ ...form, action: e.target.value })} />
                </div>
              </div>

              <div className="h3-card">
                <span className="h3-card-title" title="Each line as spoken, under the speaker. A note (breathless, flat) is how it's said, never spoken. V.O. is a voice not in the scene (narration, a phone); O.S. is someone in the space, out of frame.">
                  Dialogue <i className="pi pi-info-circle sm-tip-i" />
                </span>
                <DialogueRows rows={form.dialogue} speakers={cast.chars} onChange={setDialogue} />
              </div>

              <div className="h3-card">
                <div className="sm-form">
                  <Tip label="Camera" help="The move only, in H3's words: a motion, then how far and how fast (build one from the three lists). Empty: it holds still." />
                  <CameraField value={form.keys.camera ?? ""} onChange={(v) => set("camera", v)} />
                  <Tip label="Sound" help="Ambience and the sounds of the action: footsteps, doors, wind. Not dialogue, not music." htmlFor="sm-sf-sound" />
                  <input id="sm-sf-sound" className="h3-in" value={form.keys.sound ?? ""} placeholder="dawn birdsong, dripping water, a faint breeze" onChange={(e) => set("sound", e.target.value)} />
                  <Tip label="Extras" help="Other people in frame, described (they're invented fresh each shot; for the same people every shot, make a group)." htmlFor="sm-sf-extras" />
                  <input id="sm-sf-extras" className="h3-in" value={form.keys.extras ?? ""} placeholder="two nurses chatting at the far end of the corridor" onChange={(e) => set("extras", e.target.value)} />
                  <Tip label="On-screen text" help="Words the picture must show: a sign, a note, a screen. Never titles or credits." htmlFor="sm-sf-text" />
                  <input id="sm-sf-text" className="h3-in" value={form.keys.text ?? ""} placeholder="OPEN 24 HOURS" onChange={(e) => set("text", e.target.value)} />
                </div>
              </div>

              <MoreToggle open={more} onToggle={setMore} label="More: music, the model, keyframes, continuity, audio, render settings" />
              {more && (
                <div className="h3-card" style={{ gap: 8 }}>
                  <Row label="Music" help="Audience-only score; usually left out and decided in the edit.">
                    <input className="h3-in" value={form.keys.music ?? ""} onChange={(e) => set("music", e.target.value)} />
                  </Row>
                  <Row label="Video model class" help="Which model draws this shot, only when it needs something one model does; empty: the episode's.">
                    <div className="h3-row" style={{ gap: 4 }}>
                      <select className="h3-in h3-grow" value={form.keys.target ?? ""} onChange={(e) => set("target", e.target.value)}>
                        <option value="">the episode's</option>
                        <ModelOptions targets={videoTargets} />
                      </select>
                      <ModelsButton />
                    </div>
                  </Row>
                  {/* what that model loads: its file, its LoRAs, its steps */}
                  {!hosted && <Row label="Model file" help="Another file of the same model for this shot (a different quantization, a fine-tune).">
                    <ModelLine value={form.keys.model ?? ""} onChange={(v) => set("model", v)} target={renderTarget} empty="the series' (or the model's own)" />
                  </Row>}
                  {!hosted && <Row label="LoRAs" help={`LoRAs for this shot, from what ${renderTarget ?? "its model"} loads, each with its strength, applied in this order; none for none.`}>
                    <LoraLine value={form.keys.lora ?? ""} onChange={(v) => set("lora", v)} target={renderTarget} empty="the series' (or the model's own)" />
                  </Row>}
                  {noSteps
                    ? <Row label="Steps" help="This model has no steps setting: the provider decides."><span className="h3-small h3-muted">none (the provider's)</span></Row>
                    : <SmallKey label="Steps" k="steps" form={form} set={set} help="Sampler steps for this shot." />}
                  <Row label="Continues" help="Carries straight on from the shot before in the cut: first opens on its last frame, latent holds its last frames and goes on from them; multishot renders it in one generation with the shot before (one take for the group).">
                    <select className="h3-in" value={form.keys.continuous ?? ""} onChange={(e) => set("continuous", e.target.value)}>
                      <option value="">no</option><option value="first">first: from the last frame</option><option value="latent">latent: held and carried on</option><option value="multishot">multishot: one generation with the shot before</option><option value="none">none: break a sequence's chain</option>
                    </select>
                  </Row>
                  <Row label="First frame" help="The picture the shot opens on, for models that read keyframes (H3 FL2VA, LTX-2, Wan); others ignore it.">
                    <KeyframeField ep={ep} k="first" value={form.keys.first ?? ""} onChange={(v) => set("first", v)} />
                  </Row>
                  <Row label="Last frame" help="The picture it ends on, for the models that take one.">
                    <KeyframeField ep={ep} k="last" value={form.keys.last ?? ""} onChange={(v) => set("last", v)} />
                  </Row>
                  <Row label="Audio" help="This shot's sound: generate, dub (lip-sync to the recording), dub_keep_foley, clone. Empty: the series' dialogue setting.">
                    <select className="h3-in" value={form.keys.policy ?? ""} onChange={(e) => set("policy", e.target.value)}>
                      <option value="">the series'</option>
                      {["generate", "dub", "dub_keep_foley", "clone"].map((p) => <option key={p} value={p}>{p}</option>)}
                    </select>
                  </Row>
                  <Row label="Pace" help="How fast its lines are spoken: slow 3.6, normal 4.4, fast 5.4 syllables a second (fast marks a deliberate rush).">
                    <select className="h3-in" value={form.keys.pace ?? ""} onChange={(e) => set("pace", e.target.value)}>
                      <option value="">the series'</option><option value="slow">slow</option><option value="normal">normal</option><option value="fast">fast</option>
                    </select>
                  </Row>
                  <Row label="Profile" help="A profile from the series config: look words, a lens and render settings, shared by the shots that name it. Save as profile… makes one from this shot's own lens, model, LoRAs, steps and sla.">
                    <span className="h3-row" style={{ gap: 6 }}>
                      {cast.profiles.length > 0 && (
                        <select className="h3-in" value={form.keys.profile ?? ""} onChange={(e) => set("profile", e.target.value)}>
                          <option value="">—</option>
                          {cast.profiles.map((p) => <option key={p} value={p}>{p}</option>)}
                        </select>
                      )}
                      <button type="button" className="h3-btn h3-small" disabled={busy || !Object.keys(profileFromShot(form.keys, form.other)).length}
                        title={Object.keys(profileFromShot(form.keys, form.other)).length
                          ? "Keep this shot's lens, video model, model file, LoRAs, steps and sla as a profile in the series config, and put this shot on it"
                          : "Set a lens, a video model, LoRAs or steps on this shot first: those are what a profile keeps"}
                        onClick={() => void saveAsProfile()}>
                        <i className="pi pi-bookmark" /> Save as profile…
                      </button>
                    </span>
                  </Row>
                </div>
              )}
            </>
          )}
        </div>
        <div className="h3-col sm-shotform-side">
          <Preview p={preview} pass={pass} show={showPrompt} setShow={setShowPrompt} />
        </div>
      </div>
      <div className="h3-dialog-foot">
        <span className="h3-small h3-muted h3-grow">
          {dirty || isNew ? `Not saved yet${kept && !kept.stale && dirty ? ` (your edits from ${keptAt(kept.at)}, kept in this browser)` : ""}: Save writes only this shot's lines into the script and rebuilds.` : "Saved"}
        </span>
        <button className="h3-btn h3-big" disabled={!dirty || busy} onClick={() => void load()}>Revert</button>
        <button className="h3-btn h3-big" disabled={!form || busy || (!dirty && !isNew)} onClick={() => void save(false)}
          title="Write this shot into the script and rebuild">
          {busy && <i className="pi pi-spin pi-spinner" />} Save
        </button>
        <button className="h3-btn h3-primary h3-big" disabled={!form || busy || preview?.ok === false} onClick={() => void save(true)}
          title={`Save, then render a new ${pass} take of it`}>
          <i className="pi pi-play" /> Save and generate {pass}
        </button>
      </div>
    </FloatingWindow>
  );
}

export function Row({ label, help, children }: { label: string; help: string; children: React.ReactNode }) {
  return (
    <div className="h3-col" style={{ gap: 2, minWidth: 0 }}>
      <span className="h3-small"><b>{label}</b></span>
      {children}
      <span className="h3-small h3-muted">{help}</span>
    </div>
  );
}

/** A field's label, its help on hover (the shot form keeps its fields to one line each). */
function Tip({ label, help, htmlFor }: { label: string; help: string; htmlFor?: string }) {
  return (
    <label className="sm-tip" title={help} htmlFor={htmlFor}>
      {label} <i className="pi pi-info-circle sm-tip-i" />
    </label>
  );
}

/** A `first:` / `last:` value: the default, a method, or a picture (browsed for). */
function KeyframeField({ ep, k, value, onChange }: { ep: string; k: "first" | "last"; value: string; onChange: (v: string) => void }) {
  const isPath = !!value && !KEYFRAME_METHODS.includes(value.toLowerCase());
  const browse = usePictureBrowse(`shot:${k}`, k === "first" ? "the first frame" : "the last frame", onChange);
  return (
    <div className="h3-row h3-wrap" style={{ gap: 4 }}>
      <select className="h3-in" value={isPath ? "__path" : value} onChange={(e) => {
        if (e.target.value === "__path") browse();
        else onChange(e.target.value);
      }}>
        <option value="">the default (generate, when the model reads one)</option>
        <option value="generate">generate: a still from the shot's description</option>
        <option value="import">import: one you'll bring in on the Refs tab</option>
        <option value="none">none</option>
        <option value="__path">{isPath ? "this picture" : "a picture you have…"}</option>
      </select>
      {isPath && (
        <>
          <Hover ep={ep} item={{ id: value, name: value, pic: { path: value, face: false, version: null } }} big={260}>
            <Thumb ep={ep} pic={{ path: value, face: false, version: null }} name={k} size={28} />
          </Hover>
          <span className="h3-small h3-mono h3-ell" style={{ maxWidth: 220 }} title={value}>{value}</span>
          <button className="h3-btn" onClick={browse}>Change…</button>
        </>
      )}
    </div>
  );
}

function SmallKey({ label, k, form, set, help }: { label: string; k: string; form: Form; set: (k: string, v: string) => void; help: string }) {
  return (
    <Row label={label} help={help}>
      <input className="h3-in" value={form.keys[k] ?? ""} onChange={(e) => set(k, e.target.value)} />
    </Row>
  );
}

export function Chips({ ep, value, options, onChange, add, addLabel }: {
  ep: string | null; value: string[]; options: Cast[]; onChange: (v: string[]) => void; add: () => void; addLabel: string;
}) {
  const left = options.filter((o) => !value.includes(o.id));
  return (
    <div className="h3-row h3-wrap" style={{ gap: 4 }}>
      {value.map((id, i) => {
        const o: Named = options.find((x) => x.id === id) ?? { id, name: id, pic: null };
        return (
          <Hover key={id} ep={ep} item={o}>
            <span className="h3-badge sm-chip" style={{ display: "inline-flex", alignItems: "center", gap: 4 }}
              title={options.some((x) => x.id === id) ? undefined : `${id} isn't in the series config`}>
              <Thumb ep={ep} pic={o.pic} name={o.name} size={22} round />
              {i + 1}. {o.name}
              <button className="h3-link" title="Earlier" disabled={i === 0} onClick={() => {
                const v = [...value]; [v[i - 1], v[i]] = [v[i], v[i - 1]]; onChange(v);
              }}>‹</button>
              <button className="h3-link" title="Remove" onClick={() => onChange(value.filter((x) => x !== id))}>×</button>
            </span>
          </Hover>
        );
      })}
      <PicturePicker ep={ep} options={left} label={<><i className="pi pi-plus" /> select…</>} title="Pick from the cast"
        onPick={(id) => id && onChange([...value, id])} />
      <button className="h3-btn" onClick={add}>{addLabel}</button>
    </div>
  );
}

/** A location, picked by its plate; `empty` names the choice of none. */
export function PlacePick({ ep, value, places, empty, onChange }: {
  ep: string | null; value: string; places: Named[]; empty: string; onChange: (v: string) => void;
}) {
  const cur: Named | null = value ? places.find((p) => p.id === value) ?? { id: value, name: value, pic: null } : null;
  return (
    <span className="h3-row" style={{ gap: 4 }}>
      {cur && (
        <Hover ep={ep} item={cur} big={260}>
          <Thumb ep={ep} pic={cur.pic} name={cur.name} size={28} />
        </Hover>
      )}
      <PicturePicker ep={ep} options={places} none={empty} onPick={onChange} title="Pick a location by its plate"
        label={<>{cur ? cur.name : empty} <i className="pi pi-chevron-down" style={{ fontSize: 10 }} /></>} />
    </span>
  );
}

export function DialogueRows({ rows, speakers, onChange }: { rows: DialogueLine[]; speakers: Cast[]; onChange: (d: DialogueLine[]) => void }) {
  const up = (i: number, p: Partial<DialogueLine>) => onChange(rows.map((r, j) => (j === i ? { ...r, ...p } : r)));
  return (
    <div className="h3-col" style={{ gap: 4 }}>
      {rows.map((r, i) => (
        <div key={i} className="h3-col" style={{ gap: 2, borderLeft: "2px solid var(--h3-border)", paddingLeft: 6 }}>
          <div className="h3-row h3-wrap">
            <select className="h3-in" value={r.speaker} onChange={(e) => up(i, { speaker: e.target.value })}>
              <option value="">speaker…</option>
              {speakers.map((s) => <option key={s.id} value={s.id.toUpperCase()}>{s.name} ({s.id.toUpperCase()})</option>)}
              {r.speaker && !speakers.some((s) => s.id.toUpperCase() === r.speaker) && <option value={r.speaker}>{r.speaker}</option>}
            </select>
            <select className="h3-in" value={r.marker} onChange={(e) => up(i, { marker: e.target.value as DialogueLine["marker"] })}>
              <option value="">on screen</option><option value="V.O.">V.O. (voiceover)</option><option value="O.S.">O.S. (off screen)</option>
            </select>
            <input className="h3-in" style={{ width: 130 }} placeholder="how (optional)" value={r.note} onChange={(e) => up(i, { note: e.target.value })} />
            <span className="h3-grow" />
            <button className="h3-link" disabled={i === 0} title="Earlier" onClick={() => {
              const v = [...rows]; [v[i - 1], v[i]] = [v[i], v[i - 1]]; onChange(v);
            }}>↑</button>
            <button className="h3-link" title="Remove the line" onClick={() => onChange(rows.filter((_, j) => j !== i))}>×</button>
          </div>
          <input className="h3-in" placeholder="what they say" value={r.text} onChange={(e) => up(i, { text: e.target.value })} />
        </div>
      ))}
      <div><button className="h3-btn" onClick={() => onChange([...rows, { speaker: "", marker: "", note: "", text: "" }])}>+ Line</button></div>
    </div>
  );
}

export function CameraField({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const [move, setMove] = useState("");
  const [amp, setAmp] = useState("");
  const [speed, setSpeed] = useState("");
  const [toward, setToward] = useState("");
  const moves = useCameraTiles();
  const build = (m: string, a: string, s: string, t = toward) => {
    setMove(m); setAmp(a); setSpeed(s); setToward(t);
    if (m) onChange(cameraLine(m, a, s, t));
  };
  // the move the line starts with (its amplitude and speed after it), longest first
  const current = [...moves].sort((a, b) => b.text.length - a.text.length).find((t) => value.trim().startsWith(t.text));
  return (
    <div className="h3-col" style={{ gap: 3 }}>
      <PresetPicker tiles={moves} value={value} picked={current?.id ?? null} onPick={(m) => build(m, amp, speed)}
        title="Camera moves, as clips (hover to play)" open={!value.trim()} size={0.8} />
      <input className="h3-in" value={value} placeholder="holds a static shot" onChange={(e) => onChange(e.target.value)} />
      <div className="h3-row h3-wrap">
        <span className="h3-small h3-muted">build:</span>
        <select className="h3-in" value={move} onChange={(e) => build(e.target.value, amp, speed)}>
          <option value="">a move…</option>
          {CAMERA_MOVES.map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
        <select className="h3-in" value={amp} onChange={(e) => build(move, e.target.value, speed)}>
          {CAMERA_AMPLITUDE.map((m) => <option key={m} value={m}>{m || "any amplitude"}</option>)}
        </select>
        <select className="h3-in" value={speed} onChange={(e) => build(move, amp, e.target.value)}>
          {CAMERA_SPEED.map((m) => <option key={m} value={m}>{m || "any speed"}</option>)}
        </select>
        <input className="h3-in h3-grow" style={{ minWidth: 180 }} value={toward} placeholder="where it goes: toward her face / revealing the square"
          title="What the move travels toward or reveals: the model frames the end of the move from it, and a bare move often barely moves"
          onChange={(e) => build(move, amp, speed, e.target.value)} />
      </div>
    </div>
  );
}

/** A `size:` as the framing presets name it (the script's own aliases read too). */
function framingId(size: string | undefined): string | null {
  const v = (size ?? "").toLowerCase().replace(/[^a-z]/g, "");
  if (!v) return null;
  const alias: Record<string, string> = {
    xcu: "ecu", extremecloseup: "ecu", close: "cu", closeup: "cu", mediumcloseup: "mcu", ms: "medium",
    mid: "medium", midshot: "medium", mediumshot: "medium", cowboyshot: "cowboy", americanshot: "cowboy",
    mediumwide: "mws", mls: "mws", mediumlong: "mws", fs: "full", fullshot: "full", ws: "wide", ls: "wide",
    long: "wide", wideshot: "wide", longshot: "wide", xws: "ews", els: "ews", extremewide: "ews", extremelong: "ews",
    povshot: "pov", pointofview: "pov", overtheshoulder: "ots", overshoulder: "ots", lowangle: "low",
    lowangleshot: "low", highangle: "high", highangleshot: "high",
  };
  return alias[v] ?? v;
}

function Preview({ p, pass, show, setShow }: { p: ShotPreview | null; pass: string; show: boolean; setShow: (b: boolean) => void }) {
  if (!p) return <div className="h3-card"><span className="h3-muted h3-small">What renders appears as you fill it in.</span></div>;
  if (!p.ok) {
    return (
      <div className="h3-card">
        <span className="h3-card-title">Won't build yet</span>
        <div className="h3-note h3-note-err h3-small">{p.error}</div>
      </div>
    );
  }
  const pc = p.pacing;
  const pct = pc ? Math.min(100, Math.round((pc.rate / pc.ceiling) * 100)) : 0;
  const tone = pc ? (pc.verdict === "ok" ? "var(--h3-ok)" : pc.verdict === "tight" ? "var(--h3-queued)" : "var(--h3-error)") : "";
  return (
    <>
      <div className="h3-card">
        <div className="h3-card-head">
          <span className="h3-card-title h3-grow">What renders</span>
          <span className="h3-small h3-muted">{pass}</span>
        </div>
        <div className="h3-chips">
          <span className="h3-sum">{p.target_label}</span>
          <span className="h3-sum">{p.width}×{p.height}</span>
          <span className="h3-sum">{p.seconds} s · {p.frames} frames</span>
          <span className="h3-sum">audio: {p.audio_policy ?? "—"}</span>
        </div>
        {pc && (
          <div className="h3-col" style={{ gap: 3 }}>
            <div className="h3-row h3-small">
              <span className="h3-grow">Dialogue pace · {pc.syllables} syllables in {pc.held.toFixed(2)} s</span>
              <b style={{ color: tone }}>{pc.verdict === "ok" ? "fits" : pc.verdict.toLowerCase()}</b>
            </div>
            <div className="h3-meter"><span style={{ width: `${pct}%`, background: tone }} /></div>
            <span className="h3-small h3-muted">
              {pc.rate.toFixed(1)} syllables a second; {pc.pace} pace is {pc.pace_rate}
              {pc.verdict !== "ok" ? `. It needs ${pc.fits.toFixed(2)} s at this pace: lengthen it (or auto), cut words, or split the shot.` : ""}
            </span>
          </div>
        )}
        {(p.warnings ?? []).map((w, i) => <div key={i} className="h3-note h3-small">{w}</div>)}
      </div>
      <div className="h3-card sm-told">
        <div className="h3-card-head">
          <span className="h3-card-title h3-grow">What the model is told</span>
          <button className="h3-link h3-small" onClick={() => void copyText(p.prompt ?? "", "Prompt")}>copy</button>
          <span className="h3-muted">·</span>
          <button className="h3-link h3-small" onClick={() => setShow(!show)}>{show ? "hide" : "show"}</button>
        </div>
        {show && <div className="sm-told-text">{p.prompt}</div>}
      </div>
    </>
  );
}
