// The shot form: one shot of the script as fields — who's in it, the framing
// and length, what happens, what's said, the camera and the sound — with what
// the model will be told beside it, compiled as you type
// (POST /seriesmith/shot/preview), and the dialogue's pace against the shot's
// length. Saving rewrites only this shot's lines in the script (lib/shotForm.ts)
// through PUT /seriesmith/source: the check, the history copy and the rebuild.

import { useEffect, useMemo, useRef, useState } from "react";
import { afterAuthoredWrite, loadRefs, openShotForm, openSubjectCard, requestRender, select, showInScript } from "../actions";
import { api, host } from "../host";
import { pictureOf } from "../lib/pictures";
import { getPath, type Raw } from "../lib/seriesForm";
import {
  CAMERA_AMPLITUDE, CAMERA_MOVES, KEYFRAME_METHODS, CAMERA_SPEED, SIZES, cameraLine, insertAfter, listOf, newShot,
  parseShot, replaceLines, sequenceAt, sequencesOf, shotIdBetween, writeShot, type DialogueLine, type ShotForm as Form,
} from "../lib/shotForm";
import { conflictOf } from "../lib/sourceSession";
import { isHosted } from "../lib/targets";
import { useApp } from "../store";
import type { Ref, ShotPreview, SourceDoc } from "../types";
import { LoraLine, ModelLine, MoreToggle } from "./Fields";
import { FloatingWindow, type Rect } from "./FloatingWindow";
import { LengthPicker } from "./LengthPicker";
import { Hover, PicturePicker, Thumb, usePictureBrowse, type Named } from "./Picture";
import { useSeriesConfig } from "./useSeriesConfig";
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
  return <ShotFormBody key={`${ep}|${f.shot ?? `+${f.after ?? ""}`}`} ep={ep} shot={f.shot} after={f.after} />;
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

function ShotFormBody({ ep, shot, after }: { ep: string; shot: string | null; after: string | null }) {
  const pass = useApp((s) => s.pass);
  const targets = useApp((s) => s.targets);
  const sc = useSeriesConfig(ep);
  const [doc, setDoc] = useState<SourceDoc | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [orig, setOrig] = useState<string>("");
  const [seq, setSeq] = useState<string>("");          // a new shot's sequence ("+": a new one)
  const [newSeq, setNewSeq] = useState({ id: "", location: "" });
  const [preview, setPreview] = useState<ShotPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [more, setMore] = useState(false);
  const [showPrompt, setShowPrompt] = useState(true);
  const isNew = shot === null;

  // the script, and the shot's block in it (or a new shot's place)
  async function load() {
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
        setForm(f);
        setOrig(writeShot(f).join("\n"));
      } else {
        const ids = d.shots.map((x) => x.id);
        const i = after ? ids.indexOf(after) : ids.length - 1;
        const id = shotIdBetween(i >= 0 ? ids[i] : null, i >= 0 && i + 1 < ids.length ? ids[i + 1] : null, new Set(ids));
        const seqs = sequencesOf(d.text);
        const at = i >= 0 ? sequenceAt(seqs, d.shots[i].line)?.id : seqs[seqs.length - 1]?.id;
        setSeq(at ?? "+");
        setForm(newShot(id));
        setOrig("");
      }
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    void load();
  }, [ep, shot]);

  const seqs = useMemo(() => (doc ? sequencesOf(doc.text) : []), [doc]);
  const refs = useApp((s) => s.refs[ep]);
  useEffect(() => {
    if (!refs) void loadRefs(ep);
  }, [ep]);
  const cast = useMemo(() => castOf(sc.base, refs), [sc.base, refs]);
  const block = form ? writeShot(form) : [];
  const dirty = !!form && block.join("\n") !== orig;

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


  const head = (
    <>
      <i className="pi pi-video" />
      <span className="h3-grow">{isNew ? `New shot ${form?.id ?? ""}` : `Shot ${shot}`}{dirty ? " •" : ""}</span>
      {!isNew && <button className="h3-btn h3-icon" title="Show this shot in the Script window" onClick={() => showInScript(shot!)}><i className="pi pi-file-edit" /></button>}
      <button className="h3-btn h3-icon" title="Close" onClick={() => {
        if (dirty && !window.confirm("Close without saving this shot?")) return;
        openShotForm(null);
      }}><i className="pi pi-times" /></button>
    </>
  );

  return (
    <FloatingWindow storageKey={RECT_KEY} defaultRect={defaultRect} head={head} minW={420} minH={320}>
      <div className="sm-shotform" style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.15fr) minmax(0, 1fr)", gap: 12, padding: 10, height: "100%", overflow: "hidden" }}>
        <div className="h3-col" style={{ gap: 9, overflow: "auto", paddingRight: 4 }}>
          {error && <div className="h3-err">{error} <button className="h3-btn" onClick={() => void load()}>Reload</button></div>}
          {!form && !error && <div className="h3-muted">Loading…</div>}
          {form && (
            <>
              <Row label="Shot" help={isNew ? "Its id: in the script's own numbering, between the shots around it." : "Its id stays: takes, the cut and notes name it."}>
                <div className="h3-row h3-wrap">
                  <input className="h3-in" style={{ width: 110 }} value={form.id} disabled={!isNew}
                    onChange={(e) => setForm({ ...form, id: e.target.value.trim() })} />
                  {isNew && (
                    <select className="h3-in" value={seq} onChange={(e) => setSeq(e.target.value)} title="The sequence it goes in">
                      {seqs.map((s) => <option key={s.id} value={s.id}>{s.id}{s.location ? ` · ${s.location}` : ""}</option>)}
                      <option value="+">+ a new sequence</option>
                    </select>
                  )}
                  {isNew && seq === "+" && (
                    <>
                      <input className="h3-in" style={{ width: 80 }} placeholder={`sq${String(seqs.length + 1).padStart(2, "0")}`}
                        value={newSeq.id} onChange={(e) => setNewSeq({ ...newSeq, id: e.target.value.trim() })} />
                      <PlacePick ep={ep} value={newSeq.location} places={cast.places} empty="its location…"
                        onChange={(v) => setNewSeq({ ...newSeq, location: v })} />
                      <button className="h3-btn" onClick={() => openSubjectCard({ kind: "location", id: null })}>+ Location</button>
                    </>
                  )}
                </div>
              </Row>

              <Row label="Who's in it" help="The characters on screen, in this order (on H3 they are the shot's pictures 1 to 3). Someone who only speaks off screen isn't here: give their line V.O. or O.S.">
                <Chips ep={ep} value={listOf(form.keys.who)} options={cast.chars.filter((c) => c.onScreen)}
                  onChange={(v) => set("who", v.join(", "))} add={() => openSubjectCard({ kind: "character", id: null })} addLabel="+ Character" />
              </Row>
              <Row label="With" help="Props and vehicles whose exact look matters and recurs (each takes a picture slot). A generic mug is better in the action.">
                <Chips ep={ep} value={listOf(form.keys.with)} options={cast.things}
                  onChange={(v) => set("with", v.join(", "))} add={() => openSubjectCard({ kind: "prop", id: null })} addLabel="+ Prop" />
              </Row>

              <div className="h3-row h3-wrap" style={{ gap: 10, alignItems: "flex-start" }}>
                <Row label="Size" help="How much of them the frame holds; the prompt opens with it.">
                  <select className="h3-in" value={form.keys.size ?? ""} onChange={(e) => set("size", e.target.value)}>
                    <option value="">—</option>
                    {SIZES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
                    {form.keys.size && !SIZES.some((s) => s.value === form.keys.size) && <option value={form.keys.size}>{form.keys.size}</option>}
                  </select>
                </Row>
                <Row label="Length" help="Seconds on H3's grid (other lengths round up onto the model's own; the preview says what renders); auto fits the dialogue.">
                  <LengthPicker value={form.keys.dur ?? ""} onChange={(v) => set("dur", v)} empty="—" auto model />
                </Row>
                <Row label="Background" help="The location behind this shot. Empty: the sequence's location.">
                  <PlacePick ep={ep} value={form.keys.plate ?? ""} places={cast.places} empty="the sequence's location"
                    onChange={(v) => set("plate", v)} />
                </Row>
              </div>

              <Row label="What happens" help="What is visibly happening, present tense, concrete and physical. This shot only: the model remembers nothing of the shot before, so say it fresh. Not how anyone feels.">
                <textarea className="h3-in" rows={4} style={{ fontFamily: "inherit", resize: "vertical" }} value={form.action}
                  placeholder="Ada steps out onto the wet porch and stops, looking at the mist on the lawn."
                  onChange={(e) => setForm({ ...form, action: e.target.value })} />
              </Row>

              <Row label="Dialogue" help="Each line as spoken, under the speaker. A note (breathless, flat) is how it's said, never spoken. V.O. is a voice not in the scene (narration, a phone); O.S. is someone in the space, out of frame.">
                <DialogueRows rows={form.dialogue} speakers={cast.chars} onChange={setDialogue} />
              </Row>

              <Row label="Camera" help="The move only, in H3's words: a motion, then how far and how fast. Empty: it holds still.">
                <CameraField value={form.keys.camera ?? ""} onChange={(v) => set("camera", v)} />
              </Row>
              <Row label="Sound" help="Ambience and the sounds of the action: footsteps, doors, wind. Not dialogue, not music.">
                <input className="h3-in" value={form.keys.sound ?? ""} placeholder="dawn birdsong, dripping water, a faint breeze" onChange={(e) => set("sound", e.target.value)} />
              </Row>
              <Row label="Extras" help="Other people in frame, described (they're invented fresh each shot; for the same people every shot, make a group).">
                <input className="h3-in" value={form.keys.extras ?? ""} placeholder="two nurses chatting at the far end of the corridor" onChange={(e) => set("extras", e.target.value)} />
              </Row>
              <Row label="On-screen text" help="Words the picture must show: a sign, a note, a screen. Never titles or credits.">
                <input className="h3-in" value={form.keys.text ?? ""} placeholder="OPEN 24 HOURS" onChange={(e) => set("text", e.target.value)} />
              </Row>

              <MoreToggle open={more} onToggle={setMore} label="More: music, the model, keyframes, continuity, audio, render settings" />
              {more && (
                <div className="h3-col" style={{ gap: 8 }}>
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
                  <Row label="Continues" help="Carries straight on from the shot before in the cut: first opens on its last frame, latent holds its last frames and goes on from them.">
                    <select className="h3-in" value={form.keys.continuous ?? ""} onChange={(e) => set("continuous", e.target.value)}>
                      <option value="">no</option><option value="first">first: from the last frame</option><option value="latent">latent: held and carried on</option><option value="none">none: break a sequence's chain</option>
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
                  {cast.profiles.length > 0 && (
                    <Row label="Profile" help="A render profile from the series config.">
                      <select className="h3-in" value={form.keys.profile ?? ""} onChange={(e) => set("profile", e.target.value)}>
                        <option value="">—</option>
                        {cast.profiles.map((p) => <option key={p} value={p}>{p}</option>)}
                      </select>
                    </Row>
                  )}
                </div>
              )}
            </>
          )}
        </div>
        <Preview p={preview} pass={pass} show={showPrompt} setShow={setShowPrompt} />
      </div>
      <div className="h3-row" style={{ padding: "6px 10px", borderTop: "1px solid var(--h3-border)" }}>
        <span className="h3-small h3-muted h3-grow">{dirty ? "Unsaved changes" : "Saved"}</span>
        <button className="h3-btn" disabled={!dirty || busy} onClick={() => void load()}>Revert</button>
        <button className="h3-btn" disabled={!form || busy || (!dirty && !isNew)} onClick={() => void save(false)}
          title="Write this shot into the script and rebuild">
          {busy ? <i className="pi pi-spin pi-spinner" /> : <i className="pi pi-save" />} Save
        </button>
        <button className="h3-btn h3-primary" disabled={!form || busy || preview?.ok === false} onClick={() => void save(true)}
          title={`Save, then render a new ${pass} take of it`}>
          <i className="pi pi-play" /> Save and render {pass}
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
      <PicturePicker ep={ep} options={left} label={<><i className="pi pi-plus" /> add…</>} title="Pick from the cast"
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
  const build = (m: string, a: string, s: string) => {
    setMove(m); setAmp(a); setSpeed(s);
    if (m) onChange(cameraLine(m, a, s));
  };
  return (
    <div className="h3-col" style={{ gap: 3 }}>
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
      </div>
    </div>
  );
}

function Preview({ p, pass, show, setShow }: { p: ShotPreview | null; pass: string; show: boolean; setShow: (b: boolean) => void }) {
  if (!p) return <div className="h3-muted h3-small">The preview appears as you fill it in.</div>;
  if (!p.ok) {
    return (
      <div className="h3-col" style={{ gap: 6 }}>
        <div className="h3-h">Won't build yet</div>
        <div className="h3-err">{p.error}</div>
      </div>
    );
  }
  const pc = p.pacing;
  const pct = pc ? Math.min(100, Math.round((pc.rate / pc.ceiling) * 100)) : 0;
  return (
    <div className="h3-col" style={{ gap: 8, overflow: "auto" }}>
      <div className="h3-h">What renders ({pass})</div>
      <div className="h3-small">
        <b>{p.target_label}</b> · {p.width}×{p.height} · {p.frames} frames ({p.seconds} s) · audio {p.audio_policy ?? "—"}
      </div>
      {pc && (
        <div className="h3-col" style={{ gap: 2 }}>
          <div className="h3-small">
            Dialogue: {pc.syllables} syllables in {pc.held.toFixed(2)} s = <b>{pc.rate.toFixed(1)}</b>/s
            {" "}({pc.pace} is {pc.pace_rate}/s) — <span className={pc.verdict === "ok" ? "h3-ok" : pc.verdict === "tight" ? "h3-warn" : "h3-err"}>{pc.verdict.toLowerCase()}</span>
          </div>
          <div style={{ height: 6, background: "var(--h3-border)", borderRadius: 3 }}>
            <div style={{ width: `${pct}%`, height: 6, borderRadius: 3, background: pc.verdict === "ok" ? "var(--h3-ok)" : pc.verdict === "tight" ? "var(--h3-queued)" : "var(--h3-error)" }} />
          </div>
          {pc.verdict !== "ok" && <span className="h3-small h3-muted">It needs {pc.fits.toFixed(2)} s at this pace: lengthen it (or auto), cut words, or split the shot.</span>}
        </div>
      )}
      {(p.warnings ?? []).map((w, i) => <div key={i} className="h3-small h3-warn">! {w}</div>)}
      <div className="h3-row">
        <span className="h3-h h3-grow">What the model is told</span>
        <button className="h3-link" onClick={() => setShow(!show)}>{show ? "hide" : "show"}</button>
      </div>
      {show && (
        <pre className="h3-small" style={{ whiteSpace: "pre-wrap", margin: 0, padding: 8, background: "var(--h3-bg-2, rgba(127,127,127,0.08))", borderRadius: 4 }}>{p.prompt}</pre>
      )}
    </div>
  );
}
