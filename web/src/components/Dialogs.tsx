import { useEffect, useMemo, useState, type ReactNode } from "react";
import { closeRedo, closeSidecar, copyText, loadDetail, runRedo, takePrompt, type RedoSeed } from "../actions";
import { errText, parseSeed } from "../api";
import { api } from "../host";
import { absPath, shortName, tn } from "../lib/format";
import { missingOf } from "../lib/missingRefs";
import { loraRow, parseLoras, parseSteps, type LoraRow } from "../lib/overrideForm";
import { findTarget, isModelMismatch, isRetargeted, MODEL_MISMATCH_LABEL, modelWarning, runSize, shotTarget, targetLabel } from "../lib/targets";
import { parseSize, sizeCheck, sizeRule, sizeText } from "../lib/size";
import { SizePicker } from "./SizePicker";
import { useApp } from "../store";
import type { Pass, ShotDetail, TakeDetail, TargetList } from "../types";
import { DiffView, LoraEditor, ModelSelect } from "./Fields";
import { useDetail, useDetailError, useShotStatus } from "./hooks";
import { MissingRefsNote } from "./MissingRefs";
import { ResolvedNotes, TargetReadinessNote } from "./Readiness";
import { ModelsButton, TargetSelect, useTargetPickers, useTargets } from "./Targets";

/** `sub`: a line under the title; `lead`: a picture before it; `bare`: the children
 * bring their own body and foot (.h3-dialog-body, .h3-dialog-foot). */
export function Dialog({ title, onClose, children, footer, wide, sub, lead, bare }: {
  title: ReactNode; onClose: () => void; children: ReactNode; footer?: ReactNode; wide?: boolean;
  sub?: ReactNode; lead?: ReactNode; bare?: boolean;
}) {
  useEffect(() => {
    const key = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [onClose]);
  return (
    <div className="h3-backdrop" onPointerDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="h3-dialog" style={wide ? { width: "min(760px, 100%)" } : undefined} role="dialog">
        <div className="h3-dialog-head">
          {lead}
          <div className="h3-head-text">
            <span className="h3-title">{title}</span>
            {sub && <span className="h3-small h3-muted">{sub}</span>}
          </div>
          <button className="h3-btn h3-icon" title="Close" onClick={onClose}><i className="pi pi-times" /></button>
        </div>
        {bare ? children : <div className="h3-dialog-body">{children}</div>}
        {footer && <div className="h3-dialog-foot">{footer}</div>}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// redo
// ---------------------------------------------------------------------------

type SeedChoice = "new" | "same" | "typed";
type PromptSource = "current" | "parent";

interface RedoForm {
  parent: number | null;
  seedChoice: SeedChoice;
  typedSeed: string;
  model: string;
  loras: LoraRow[];
  lorasOn: boolean;
  steps: string;
  pass: Pass;
  note: string;
  source: PromptSource;
  prompt: string;
  save: boolean;
  /** Phase 8: the target for this run; "" = the shot's own */
  target: string;
  /** keep this take's frames as a PNG sequence, for retouching a frame or two */
  frames: boolean;
  /** keep this take's latent for an upscale; null = the server's default (final pass) */
  latent: boolean | null;
  /** "WxH" for this run only; "" = the shot's own (its override, else the shotlist's) */
  size: string;
}

/** A take's own size when it isn't what the shot renders at now: "New take like this
 * one" of a 1344x768 take stays 1344x768. "" otherwise. */
function takeSize(d: ShotDetail, sc: Record<string, unknown> | null): string {
  const own = sc ? sizeText(sc.width as number, sc.height as number) : "";
  return own && own !== sizeText(d.effective.width, d.effective.height) ? own : "";
}

/** The settings a run on another target starts from: that target's preset for the pass. */
function presetForm(list: TargetList | null, target: string, pass: Pass): Pick<RedoForm, "model" | "loras" | "lorasOn" | "steps"> {
  const p = findTarget(list, target)?.presets?.[pass] ?? findTarget(list, target)?.presets?.final;
  const loras = p?.loras ?? (p?.lora ? [{ name: p.lora, strength: 1 }] : null);
  return {
    model: p?.model ?? "",
    loras: (loras ?? []).map(loraRow),
    lorasOn: loras != null,
    steps: p?.steps != null ? String(p.steps) : "",
  };
}

/** `current`: the shot's own target. A parent take rendered on another target
 * lends its seed, not its model/LoRAs/steps (they belong to that model). */
function initForm(d: ShotDetail, parent: TakeDetail | undefined, pass: Pass, current: string | null = null): RedoForm {
  const sc = parent?.sidecar ?? null;
  const scTarget = typeof sc?.target === "string" ? sc.target : null;
  const settings = sc && (!scTarget || !current || scTarget === current) ? sc : null;
  const loras = settings?.loras !== undefined ? settings.loras : d.effective.loras;
  return {
    target: "",
    parent: parent?.take ?? null,
    seedChoice: "new",
    typedSeed: sc?.seed ?? d.effective.seed ?? "",
    model: settings?.model ?? d.effective.model ?? "",
    loras: (loras ?? []).map(loraRow),
    lorasOn: loras != null,
    steps: String(settings?.steps ?? d.effective.steps ?? ""),
    pass,
    note: "",
    source: "current",
    prompt: d.effective.prompt,
    save: true,
    frames: false,
    latent: null,
    size: takeSize(d, settings),
  };
}

export function RedoDialog() {
  const r = useApp((s) => s.redo);
  const ep = useApp((s) => s.ep);
  const d = useDetail(r?.shot, r?.pass);
  const derr = useDetailError(r?.shot, r?.pass);
  if (!r || !ep) return null;
  const from = d?.takes.find((t) => t.take === r.parent);
  const thumb = from?.files.thumb ? api().thumbUrl(ep, from.files.thumb, 256) : null;
  const seed = from?.sidecar?.seed;
  return (
    <Dialog
      title={<>New take of {r.shot}</>}
      sub={r.parent != null ? <>starting from {tn(r.parent)}{seed ? <> · seed <span className="h3-mono">{seed}</span></> : null}</> : "from the shot's current settings"}
      lead={<div className="h3-dialog-thumb" style={thumb ? { backgroundImage: `url("${thumb}")` } : undefined} />}
      onClose={closeRedo}
      wide
      bare
    >
      {!d && !derr && <div className="h3-dialog-body h3-muted">Loading {r.shot}…</div>}
      {derr && !d && <div className="h3-dialog-body"><div className="h3-note h3-note-err">{derr}</div></div>}
      {d && <RedoBody key={`${r.shot}|${r.pass}|${r.parent}`} d={d} shot={r.shot} openPass={r.pass} parent={r.parent} />}
    </Dialog>
  );
}

function RedoBody({ d, shot, openPass, parent }: { d: ShotDetail; shot: string; openPass: Pass; parent: number | null }) {
  const parentTake = d.takes.find((t) => t.take === parent);
  const { list, video, seriesDefault } = useTargets();
  // the shot's own target, and the one this run uses ("" in the form = the shot's own)
  const current = list || d.target || d.built_target ? shotTarget(d, seriesDefault) : null;
  const [f, setF] = useState<RedoForm>(() => initForm(d, parentTake, openPass, current));
  const runTarget = f.target || current || "";
  const oneOff = !!f.target && f.target !== current;
  const pickers = useTargetPickers(runTarget || null);
  // the prompt is the target's when the shot is retargeted or this run is on another target
  const lockPrompt = oneOff || isRetargeted(d);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [parentPrompt, setParentPrompt] = useState<{ take: number; text: string | null; error?: string } | null>(null);
  const [showDiff, setShowDiff] = useState(false);
  const [allowMissing, setAllowMissing] = useState(false);
  const [allowMismatch, setAllowMismatch] = useState(false);
  const targetStatus = useShotStatus(shot, f.pass);
  const missing = targetStatus ? missingOf(targetStatus) : [];
  const set = (p: Partial<RedoForm>) => {
    setErr(null);
    setF((x) => ({ ...x, ...p }));
  };
  const pt = d.takes.find((t) => t.take === f.parent);
  const parentSeed = pt?.sidecar?.seed ?? null;
  // the target pass's detail (for its built prompt and effective values)
  const targetD = useDetail(shot, f.pass) ?? (f.pass === d.pass ? d : undefined);
  useEffect(() => {
    if (f.pass !== d.pass) void loadDetail(shot, f.pass);
  }, [f.pass, d.pass, shot]);

  // parent's prompt from its frozen shotlist
  useEffect(() => {
    if (f.source !== "parent" || f.parent == null) return;
    if (parentPrompt?.take === f.parent) return;
    let live = true;
    const take = f.parent;
    takePrompt(shot, take, d.pass)
      .then((text) => {
        if (!live) return;
        setParentPrompt({ take, text });
        if (text != null) setF((x) => ({ ...x, prompt: text }));
      })
      .catch((e) => live && setParentPrompt({ take, text: null, error: errText(e) }));
    return () => {
      live = false;
    };
  }, [f.source, f.parent, shot, d.pass, parentPrompt?.take]);

  const chooseParent = (n: number | null) => {
    const t = d.takes.find((x) => x.take === n);
    const init = initForm(d, t, f.pass, current);
    set({
      parent: n, typedSeed: init.typedSeed,
      // on another target, keep that target's settings
      ...(oneOff ? {} : { model: init.model, loras: init.loras, lorasOn: init.lorasOn, steps: init.steps, size: init.size }),
      ...(f.source === "parent" ? { prompt: "" } : {}),
    });
    setParentPrompt(null);
  };

  const chooseTarget = (id: string) => {
    if (!id || id === current) {
      // back to the shot's own target: its current settings
      const init = initForm(d, pt, f.pass, current);
      set({ target: "", model: init.model, loras: init.loras, lorasOn: init.lorasOn, steps: init.steps, prompt: (targetD ?? d).effective.prompt, source: "current" });
    } else {
      set({ target: id, ...presetForm(list, id, f.pass), source: "current", save: false });
    }
  };

  const submit = async () => {
    let seed: RedoSeed;
    let steps: number | null;
    let loras;
    try {
      if (f.seedChoice === "new") seed = { mode: "new" };
      else if (f.seedChoice === "same") {
        if (!parentSeed) throw new Error("The parent take has no recorded seed; type one instead.");
        seed = { mode: "same", seed: parentSeed };
      } else seed = { mode: "typed", seed: parseSeed(f.typedSeed) };
      // a model with no steps (a hosted one: its preset says 0) gets none
      steps = noSteps ? null : parseSteps(f.steps);
      if (f.size) {
        const bad = sizeCheck(f.size, sizeRule(findTarget(list, runTarget)?.template));
        if (bad?.level === "err") throw new Error(bad.text);
      }
      loras = f.lorasOn && pickers.loras !== null ? parseLoras(f.loras) : null;
      if (!lockPrompt && !f.prompt.trim()) throw new Error("The prompt is empty.");
    } catch (e) {
      setErr(errText(e));
      return;
    }
    setBusy(true);
    try {
      const ok = await runRedo({
        shot, pass: f.pass, parent: f.parent, seed, model: pickers.models === null ? "" : f.model, loras, steps, prompt: f.prompt, note: f.note.trim(),
        saveAsOverride: f.save && !oneOff, allowMissingRefs: allowMissing,
        allowModelMismatch: mismatch && allowMismatch,
        target: oneOff ? f.target : null, lockPrompt, keepFrames: f.frames, keepLatent: f.latent,
        size: f.size ? parseSize(f.size) : null,
      });
      if (ok) closeRedo();
    } finally {
      setBusy(false);
    }
  };

  const builtPrompt = targetD?.built_prompt ?? d.built_prompt;
  // a model with no steps setting (a hosted one, Seedance: its presets say 0)
  const runPreset = findTarget(list, runTarget)?.presets?.[f.pass] ?? findTarget(list, runTarget)?.presets?.final;
  const noSteps = runPreset?.steps === 0;
  // the model this run loads is another family than the target needs: the server skips it unless allowed
  const runModel = f.model || (oneOff ? "" : (targetD ?? d).effective.model);
  const mismatch = isModelMismatch(pickers.modelFiles, runModel);
  const size = runSize(targetD, runTarget, seriesDefault, list);
  const effSize = oneOff ? "" : sizeText((targetD ?? d).effective.width, (targetD ?? d).effective.height);
  const rule = sizeRule(findTarget(list, runTarget)?.template);
  const runLabel = targetLabel(list, runTarget);
  const seedText = f.seedChoice === "new" ? "new seed" : f.seedChoice === "same" ? `seed ${parentSeed}` : `seed ${f.typedSeed || "?"}`;
  const sizeShown = f.size || effSize;
  return (
    <>
      <div className="h3-dialog-body">
        <div className="h3-card-grid">
          <div className="h3-card">
            <span className="h3-card-title">What changes</span>
            <div className="h3-field" style={{ gridTemplateColumns: "64px minmax(0,1fr)" }}>
              <label>From take</label>
              <select className="h3-in" value={f.parent ?? ""} onChange={(e) => chooseParent(e.target.value === "" ? null : Number(e.target.value))}>
                <option value="">(none: the shot's current settings)</option>
                {d.takes.map((t) => (
                  <option key={t.take} value={t.take}>
                    {tn(t.take)} · {t.status}{t.sidecar?.seed ? ` · seed ${t.sidecar.seed}` : " · no sidecar"}{typeof t.sidecar?.target === "string" && current && t.sidecar.target !== current ? ` · on ${targetLabel(list, t.sidecar.target)}` : ""}
                  </option>
                ))}
              </select>
              <label>Seed</label>
              <div className="h3-col" style={{ gap: 3 }}>
                <span className="h3-seg">
                  <button className={f.seedChoice === "new" ? "h3-on" : ""} onClick={() => set({ seedChoice: "new" })}>new</button>
                  <button
                    className={f.seedChoice === "same" ? "h3-on" : ""}
                    disabled={!parentSeed}
                    title={parentSeed ? `seed ${parentSeed}` : "The parent take has no recorded seed"}
                    onClick={() => set({ seedChoice: "same" })}
                  >
                    same as {pt ? tn(pt.take) : "parent"}
                  </button>
                  <button className={f.seedChoice === "typed" ? "h3-on" : ""} onClick={() => set({ seedChoice: "typed" })}>typed</button>
                </span>
                {f.seedChoice === "same" && parentSeed && <span className="h3-mono h3-muted">{parentSeed}</span>}
                {f.seedChoice === "typed" && (
                  <input className="h3-in h3-mono" inputMode="numeric" aria-label="Seed" value={f.typedSeed} onChange={(e) => set({ typedSeed: e.target.value.replace(/[^\d]/g, "") })} />
                )}
              </div>
              <label>Note</label>
              <input className="h3-in" placeholder="what this take tries" value={f.note} onChange={(e) => set({ note: e.target.value })} />
            </div>
            <div className="h3-col" style={{ gap: 5 }}>
              <label
                className="h3-check"
                title={oneOff
                  ? `A run on another target isn't saved: the override belongs to ${targetLabel(list, current)}. To keep ${runLabel}, change the shot's target in the inspector.`
                  : "Writes the prompt, model, LoRAs, steps (and a typed/same seed) to overrides.json first, so later renders keep them"}
              >
                <input type="checkbox" disabled={oneOff} checked={f.save && !oneOff} onChange={(e) => set({ save: e.target.checked })} />
                Save these as the shot's {f.pass} override{oneOff ? " (not for a one-off target)" : ""}
              </label>
              <label
                className="h3-check"
                title={"Also writes this take's frames as PNGs in its frames/ folder, so a shot that is "
                  + "right but for a frame or two can be retouched and re-encoded. Costs a couple of "
                  + "seconds and a few hundred MB a take."}
              >
                <input type="checkbox" checked={f.frames} onChange={(e) => set({ frames: e.target.checked })} />
                Keep the frames (PNG sequence)
              </label>
              <label
                className="h3-check"
                title={"Also writes the take's latent beside it (a few MB), so the take can be upscaled "
                  + "later without going back through the VAE. On for the final pass unless the series "
                  + "config's upscale.save_latents says otherwise."}
              >
                <input type="checkbox" checked={f.latent ?? f.pass === "final"} onChange={(e) => set({ latent: e.target.checked })} />
                Keep the latent (for an upscale)
              </label>
            </div>
          </div>

          <div className="h3-card">
            <span className="h3-card-title">Model</span>
            {list && current && (
              <div className="h3-col" style={{ gap: 2 }}>
                <div className="h3-row" style={{ gap: 4 }}>
                  <TargetSelect
                    value={runTarget}
                    list={list}
                    video={video}
                    title="Target for this run only (sent with the render). The shot's own target is changed in the inspector."
                    onChange={chooseTarget}
                  />
                  <ModelsButton />
                </div>
                <span className="h3-small h3-muted">
                  for this run{oneOff ? ` (the shot stays on ${targetLabel(list, current)})` : ""} · {size.text}
                </span>
                <TargetReadinessNote id={runTarget} list={list} />
              </div>
            )}
            <div className="h3-field" style={{ gridTemplateColumns: "48px minmax(0,1fr)" }}>
              {!pickers.hosted && <label>File</label>}
              {pickers.hosted ? null : pickers.models === null ? (
                <span className="h3-muted h3-small">set by the target (it has no model widget)</span>
              ) : (
                <ModelSelect value={f.model} onChange={(model) => set({ model })} placeholder="(the workflow's model)" choices={pickers.models} grouped={pickers.modelFiles} />
              )}
              {pickers.loras !== null && (
                <>
                  <label>LoRAs</label>
                  <div className="h3-col" style={{ gap: 3 }}>
                    <label className="h3-check h3-small">
                      <input type="checkbox" checked={f.lorasOn} onChange={(e) => set({ lorasOn: e.target.checked })} />
                      set LoRAs {f.lorasOn ? "" : "(off: the workflow's own LoRA)"}
                    </label>
                    {f.lorasOn && <LoraEditor rows={f.loras} onChange={(loras) => set({ loras })} choices={pickers.loras} />}
                  </div>
                </>
              )}
              <label>Steps</label>
              {noSteps ? (
                <span className="h3-small h3-muted" title="This model has no steps setting: the provider decides">none (the provider's)</span>
              ) : (
                <input className="h3-in" aria-label="Steps" style={{ width: 80 }} inputMode="numeric" value={f.steps} onChange={(e) => set({ steps: e.target.value.replace(/[^\d]/g, "") })} />
              )}
            </div>
          </div>

          <div className="h3-card h3-card-wide">
            <div className="h3-card-head">
              <span className="h3-card-title">Output</span>
              <span title="The size this take renders at. For this run only: set it on the shot's override (inspector) to keep it. A master re-samples each take by its own size.">
                <SizePicker value={f.size} onChange={(size) => set({ size })} own={effSize} ownLabel="the shot's" rule={rule} />
              </span>
              {f.size && <span className="h3-small h3-muted">this take only</span>}
              <span className="h3-grow" />
              <span className="h3-seg" title="Which pass this take is for">
                {(["proxy", "final"] as Pass[]).map((p) => (
                  <button key={p} className={f.pass === p ? "h3-on" : ""} onClick={() => set({ pass: p, ...(oneOff ? presetForm(list, f.target, p) : {}) })}>{p}</button>
                ))}
              </span>
            </div>
          </div>

          <div className="h3-card h3-card-wide">
            <div className="h3-card-head">
              <span className="h3-card-title h3-grow">Prompt</span>
              {!lockPrompt && (
                <>
                  <span className="h3-seg">
                    <button className={f.source === "current" ? "h3-on" : ""} onClick={() => set({ source: "current", prompt: (targetD ?? d).effective.prompt })}>
                      {(targetD ?? d).override.prompt != null ? "the override" : "as built now"}
                    </button>
                    <button
                      className={f.source === "parent" ? "h3-on" : ""}
                      disabled={!pt?.files.shotlist}
                      title={pt?.files.shotlist ? "From the take's frozen shotlist" : "That take has no frozen shotlist"}
                      onClick={() => set({ source: "parent" })}
                    >
                      {pt ? tn(pt.take) : "parent take"}'s
                    </button>
                  </span>
                  <label className="h3-check h3-small"><input type="checkbox" checked={showDiff} onChange={(e) => setShowDiff(e.target.checked)} /> diff vs built</label>
                </>
              )}
            </div>
            {lockPrompt ? (
              <div className="h3-col" style={{ gap: 3 }}>
                <div className="h3-note h3-note-info h3-small">
                  {oneOff
                    ? <>{runLabel} writes its own prompt for this shot when the run is queued; a prompt written for {targetLabel(list, current)} doesn't apply.</>
                    : <>This shot is retargeted to {runLabel}: per-pass prompt overrides are ignored, and this is the prompt {runLabel} writes for it (read-only).</>}
                </div>
                {!oneOff && <pre className="h3-pre" style={{ maxHeight: 220 }}>{(targetD ?? d).effective.prompt}</pre>}
              </div>
            ) : (
              <>
                {f.source === "parent" && parentPrompt?.error && <div className="h3-note h3-note-err">{parentPrompt.error}</div>}
                {f.source === "parent" && f.parent != null && parentPrompt?.take !== f.parent && <div className="h3-muted">Loading {tn(f.parent)}'s prompt…</div>}
                {showDiff ? (
                  <DiffView oldText={builtPrompt} newText={f.prompt} />
                ) : (
                  <textarea className="h3-in h3-prompt-box" aria-label="The prompt" rows={8} value={f.prompt} spellCheck={false} onChange={(e) => set({ prompt: e.target.value })} />
                )}
              </>
            )}
          </div>
        </div>
        <MissingRefsNote blocked={missing.length ? [{ shot, refs: missing }] : []} allow={allowMissing} setAllow={setAllowMissing} />
        {mismatch && (
          <label className="h3-check" title={modelWarning(pickers.modelFiles, runModel) ?? ""}>
            <input type="checkbox" checked={allowMismatch} onChange={(e) => setAllowMismatch(e.target.checked)} />
            {MODEL_MISMATCH_LABEL}
          </label>
        )}
        {err && <div className="h3-note h3-note-err">{err}</div>}
      </div>
      <div className="h3-dialog-foot">
        <span className="h3-chips h3-grow">
          {runLabel && <span className="h3-sum">{runLabel}</span>}
          {f.model && <span className="h3-sum" title={f.model}>{shortName(f.model, 32)}</span>}
          <span className="h3-sum">{noSteps ? "provider's steps" : `${f.steps} steps`}</span>
          <span className="h3-sum">{seedText}</span>
          {sizeShown && <span className="h3-sum">{sizeShown}</span>}
        </span>
        <button className="h3-btn h3-big" onClick={closeRedo}>Cancel</button>
        <button className="h3-btn h3-primary h3-big" disabled={busy} onClick={() => void submit()}>
          <i className={busy ? "pi pi-spin pi-spinner" : "pi pi-play"} /> Generate {f.pass} take
        </button>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// sidecar details
// ---------------------------------------------------------------------------

export function SidecarDialog() {
  const sc = useApp((s) => s.sidecar);
  const ep = useApp((s) => s.ep);
  const d = useDetail(sc?.shot, sc?.pass);
  const derr = useDetailError(sc?.shot, sc?.pass);
  const t = useMemo(() => d?.takes.find((x) => x.take === sc?.take), [d, sc?.take]);
  const targets = useApp((s) => s.targets);
  if (!sc || !ep) return null;
  const json = t ? JSON.stringify(t.sidecar, null, 2) : "";
  return (
    <Dialog
      title={<>{sc.shot} {tn(sc.take)} <span className="h3-muted h3-small">{sc.pass}</span></>}
      onClose={closeSidecar}
      wide
      footer={
        <>
          {t && <button className="h3-btn" onClick={() => void copyText(json, "Sidecar")}>Copy JSON</button>}
          <button className="h3-btn" onClick={closeSidecar}>Close</button>
        </>
      }
    >
      {!d && !derr && <div className="h3-muted">Loading…</div>}
      {derr && !d && <div className="h3-note h3-note-err">{derr}</div>}
      {d && !t && <div className="h3-note h3-note-err">{sc.shot} has no take {sc.take} in {sc.pass}.</div>}
      {t && (
        <>
          <div className="h3-kv">
            <span>status</span><span>{t.status}{t.has_video ? "" : " (no video)"}</span>
            <span>stale</span><span>{t.stale.length ? t.stale.join(", ") : "no"}</span>
            {Object.entries(t.files).map(([k, v]) => [
              <span key={k + "k"}>{k}</span>,
              <span key={k + "v"} className="h3-mono">
                <button className="h3-link" title="Copy the absolute path" onClick={() => void copyText(absPath(ep, v!), "Path")}>{v}</button>
              </span>,
            ])}
          </div>
          {t.sidecar?.resolved && (
            <ResolvedNotes resolved={t.sidecar.resolved} target={typeof t.sidecar.target === "string" ? t.sidecar.target : d?.target} list={targets} />
          )}
          {t.sidecar ? <pre className="h3-pre">{json}</pre> : <div className="h3-muted">No sidecar: this take is from before sidecars.</div>}
        </>
      )}
    </Dialog>
  );
}
