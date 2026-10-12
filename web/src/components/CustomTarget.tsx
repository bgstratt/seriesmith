// A show's own targets (Phase 12c): turn one of ComfyUI's saved workflows into
// a target, confirm what seriesmith worked out and what it guessed, save it as a
// draft, probe-render one shot on it, then enable it for shots.

import { useEffect, useMemo, useState } from "react";
import {
  deleteCustomTarget, enableCustomTarget, inspectTarget, loadWorkflows, probeTarget,
  saveCustomTarget,
} from "../actions";
import { customTargets, isHosted } from "../lib/targets";
import type { RouterDryRun, RouterProposal } from "../api";
import { LimitsForm, changedLimits } from "./Limits";
import { api } from "../host";
import { useStatus } from "./hooks";
import { useApp } from "../store";
import type { Limits, Target, TargetList, TargetProposal, WorkflowFile } from "../types";

/** The fields no graph states, so a person has to (the rest is detected). */
interface Answers {
  id: string;
  label: string;
  short: string;
  fps: string;
  step: string;
  base: string;
  max: string;
  sizeMultiple: string;
  audio: "generate" | "none";
  prompt: "prose" | "prose_silent";
  /** param -> "class_type.field" of the candidate picked for an ambiguity */
  chosen: Record<string, string>;
}

function answersFrom(p: TargetProposal): Answers {
  const spec = p.proposal as Record<string, any>;
  const frames = spec.template?.frames ?? {};
  return {
    id: String(spec.id ?? ""),
    label: String(spec.label ?? ""),
    short: String(spec.short ?? ""),
    fps: String(spec.template?.fps ?? "series"),
    step: String(frames.step ?? 4),
    base: String(frames.base ?? 1),
    max: String(frames.max ?? 121),
    sizeMultiple: String(spec.template?.size_multiple ?? 16),
    audio: spec.capabilities?.audio === "none" ? "none" : "generate",
    prompt: spec.recipe?.prompt === "prose_silent" ? "prose_silent" : "prose",
    chosen: {},
  };
}

/** The proposal with the author's answers in it, ready to save. */
function applyAnswers(p: TargetProposal, a: Answers): Record<string, unknown> {
  const spec = JSON.parse(JSON.stringify(p.proposal)) as Record<string, any>;
  spec.id = a.id.trim();
  spec.label = a.label.trim() || spec.id;
  spec.short = a.short.trim() || spec.label;
  spec.template = {
    ...spec.template,
    fps: a.fps === "series" ? "series" : Number(a.fps) || 24,
    size_multiple: Number(a.sizeMultiple) || 16,
    frames: { step: Number(a.step) || 1, base: Number(a.base) || 1, max: Number(a.max) || 121 },
  };
  spec.capabilities = { ...spec.capabilities, audio: a.audio };
  spec.recipe = { ...spec.recipe, prompt: a.prompt };
  if (a.audio === "none") {
    spec.recipe.policies = ["silent"];
    spec.recipe.policy_fallback = { to: "silent", why: "this model makes no sound" };
  } else {
    spec.recipe.policies = ["generate"];
    delete spec.recipe.policy_fallback;
  }
  for (const amb of p.ambiguous) {
    const picked = a.chosen[amb.param];
    const cand = amb.candidates.find((c) => `${c.class_type}.${c.field}` === picked);
    if (!cand) continue;
    spec.binding.params[amb.param] = {
      class_type: cand.class_type, field: cand.field,
      ...(cand.title ? { title: cand.title } : {}),
    };
  }
  spec.draft = true;
  return spec;
}

/** "Add a target from a workflow", and the show's own targets as they stand. */
export function CustomTargets({ list }: { list: TargetList | null }) {
  const ep = useApp((s) => s.ep);
  const [open, setOpen] = useState(false);
  const [routerOpen, setRouterOpen] = useState(false);
  const mine = useMemo(() => customTargets(list), [list]);
  const shipped = useMemo(() => (list?.targets ?? []).filter((t) => t.shipped_draft), [list]);
  if (!ep) return null;
  return (
    <div className="h3-col" style={{ gap: 6 }}>
      {shipped.length > 0 && (
        <>
          <div className="h3-h">
            Hosted models to try
            <span className="h3-muted h3-small" style={{ textTransform: "none", fontWeight: 400 }}>
              {" "}— Comfy Router models seriesmith ships untested: probe a shot, then enable it for every show
            </span>
          </div>
          {shipped.map((t) => <MineRow key={t.id} t={t} builtin />)}
        </>
      )}
      <div className="h3-h">
        This show's own targets
        <span className="h3-muted h3-small" style={{ textTransform: "none", fontWeight: 400 }}>
          {" "}— a ComfyUI workflow of yours, or a Comfy Router model, driven like any other
        </span>
      </div>
      {mine.map((t) => <MineRow key={t.id} t={t} />)}
      {!mine.length && (
        <div className="h3-small h3-muted">
          None yet. Save a workflow in ComfyUI, then add it here: seriesmith reads the graph and works
          out which widget takes the prompt, the size, the length, the seed and the model.
        </div>
      )}
      {open && <Wizard onClose={() => setOpen(false)} />}
      {routerOpen && <RouterWizard onClose={() => setRouterOpen(false)} />}
      {!open && !routerOpen && (
        <div className="h3-row h3-wrap" style={{ gap: 6 }}>
          <button className="h3-btn" onClick={() => setOpen(true)}>
            <i className="pi pi-plus" /> Add a target from a workflow…
          </button>
          <button className="h3-btn" title="A hosted model by its Router id (provider/model): seriesmith reads its schema and proposes how a shot goes in"
            onClick={() => setRouterOpen(true)}>
            <i className="pi pi-cloud" /> Add a Comfy Router model…
          </button>
        </div>
      )}
    </div>
  );
}

function MineRow({ t, builtin = false }: { t: Target; builtin?: boolean }) {
  const busy = useApp((s) => !!s.busy["target-save"] || !!s.busy["target-probe"]);
  const st = useStatus();
  const [shot, setShot] = useState("");
  const hosted = isHosted(t);
  return (
    <div className="h3-mfile">
      <div className="h3-row">
        <span className={`h3-tier h3-tier-${t.draft ? "accelerator" : "node"}`}>
          {t.draft ? "draft" : "ready"}
        </span>
        <b className="h3-ell h3-grow" title={t.id}>{t.label || t.id}</b>
        <span className="h3-mono h3-small h3-muted h3-ell" style={{ maxWidth: 220 }}
              title={t.graph?.name}>{hosted ? "Comfy Router" : t.graph?.name}</span>
      </div>
      {t.draft && (
        <div className="h3-small">
          Nothing renders on it yet. Probe one shot, look at the take, then enable it — a wrong
          frame grid or a missing file shows up here rather than mid-episode.
        </div>
      )}
      <div className="h3-row h3-small">
        {t.draft && (
          <>
            <select className="h3-in" value={shot} onChange={(e) => setShot(e.target.value)}
              title="The shot the probe renders (proxy)" style={{ maxWidth: 140 }}>
              <option value="">the first shot</option>
              {(st?.shots ?? []).map((x) => <option key={x.shot} value={x.shot}>{x.shot}</option>)}
            </select>
            <button className="h3-btn" disabled={busy} title={hosted ? "A paid render of that shot, in proxy" : "Render that shot in proxy"}
              onClick={() => void probeTarget(t.id, shot || null)}>
              <i className="pi pi-play" /> Probe render{hosted ? " (paid)" : ""}
            </button>
            <button className="h3-btn" disabled={busy} onClick={() => void enableCustomTarget(t.id)}
              title={builtin ? "Offer it for shots in every show (saved in seriesmith's settings)" : undefined}>
              <i className="pi pi-check" /> Enable for shots{builtin ? " (every show)" : ""}
            </button>
          </>
        )}
        {!t.draft && (
          <button className="h3-btn" disabled={busy} onClick={() => void enableCustomTarget(t.id, true)}>
            <i className="pi pi-undo" /> Back to draft
          </button>
        )}
        {!builtin && (
          <button className="h3-btn" disabled={busy} title={`Remove ${t.id} from this show`}
                  onClick={() => { if (confirm(`Remove ${t.label || t.id} from this show? Takes already rendered on it are kept.`)) void deleteCustomTarget(t.id); }}>
            <i className="pi pi-trash" /> Remove
          </button>
        )}
      </div>
    </div>
  );
}

// the providers Router can serve a model from (not every model has each)
const PROVIDERS: [string, string][] = [["fal", "fal"], ["higgsfield", "Higgsfield"], ["runware", "Runware"], ["wavespeed", "WaveSpeed"]];

/** A Comfy Router model by its id: its schema read, the target proposed
 * (where each part of a shot goes, its limits), looked over, saved as a draft. */
function RouterWizard({ onClose }: { onClose: () => void }) {
  const ep = useApp((s) => s.ep);
  const saving = useApp((s) => !!s.busy["target-save"]);
  const [model, setModel] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [r, setR] = useState<RouterProposal | null>(null);
  const [id, setId] = useState("");
  const [label, setLabel] = useState("");
  const [json, setJson] = useState("");
  const [showJson, setShowJson] = useState(false);
  // which provider serves it ("" the model's own), and whether Router may fall back
  const [provider, setProvider] = useState("");
  const [fallback, setFallback] = useState(true);
  // its limits as proposed, looked over here (the server writes them in)
  const [limits, setLimits] = useState<Limits | null>(null);
  // every show's (beside the settings), or this show's own
  const [scope, setScope] = useState<"user" | "show">("user");
  const st = useStatus();
  const [dryShot, setDryShot] = useState("");
  const [dry, setDry] = useState<RouterDryRun | null>(null);
  const [dryBusy, setDryBusy] = useState(false);

  async function read() {
    setBusy(true);
    setErr(null);
    try {
      const got = await api().routerInspect({ model: model.trim(), ep });
      setR(got);
      setId(got.proposal.id);
      setLabel(got.proposal.label);
      setJson(JSON.stringify(got.proposal, null, 2));
      setLimits(got.limits ?? null);
      setDry(null);
    } catch (e) {
      setErr((e as Error).message);
      setR(null);
    } finally {
      setBusy(false);
    }
  }

  /** The target.json as it stands here (the JSON box, the id, the provider). */
  function current(): Record<string, unknown> | null {
    let spec: Record<string, unknown>;
    try {
      spec = JSON.parse(json) as Record<string, unknown>;
    } catch (e) {
      setErr(`The target.json isn't valid JSON: ${(e as Error).message}`);
      return null;
    }
    const router = { ...(spec.router as Record<string, unknown>) };
    delete router.provider;
    delete router.fallback;
    if (provider) router.provider = provider;
    if (!fallback) router.fallback = false;
    return { ...spec, id, label, draft: true, router };
  }

  /** The limits that differ from the proposal's, for the server to write in. */
  const changes = () => (limits && r?.limits ? changedLimits(limits, r.limits) : {});

  async function dryRun() {
    const spec = current();
    if (!spec || !ep) return;
    setDryBusy(true);
    setErr(null);
    try {
      setDry(await api().routerDryRun({ ep, target: spec, limits: changes(), shot: dryShot || null }));
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setDryBusy(false);
    }
  }

  async function save() {
    const spec = current();
    if (spec && await saveCustomTarget(spec, { scope, limits: changes() })) onClose();
  }

  const WHAT: Record<string, string> = {
    prompt: "the prompt", negative: "what to avoid", duration: "the length", resolution: "the size",
    ratio: "the shape", seed: "the seed", audio: "the sound", references: "the reference pictures",
    first: "the first frame", last: "the last frame",
  };
  return (
    <div className="h3-col h3-mfile" style={{ gap: 6 }}>
      <div className="h3-row" style={{ gap: 6 }}>
        <input className="h3-in h3-grow h3-mono" value={model} placeholder="minimax/minimax-h3"
          title="The model's Router id, provider/model (comfy.org's model catalog lists them)"
          onChange={(e) => setModel(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && model.includes("/")) void read(); }} />
        <button className="h3-btn h3-primary" disabled={busy || !model.includes("/")} onClick={() => void read()}>
          <i className={busy ? "pi pi-spin pi-spinner" : "pi pi-search"} /> Read it
        </button>
        <button className="h3-btn" onClick={onClose}>Cancel</button>
      </div>
      {err && <div className="h3-small h3-err">{err}</div>}
      {r && (
        <>
          <div className="h3-row h3-wrap" style={{ gap: 6 }}>
            <label className="h3-small h3-row" style={{ gap: 4 }}>id
              <input className="h3-in h3-mono" style={{ width: 170 }} value={id} onChange={(e) => setId(e.target.value)} /></label>
            <label className="h3-small h3-row h3-grow" style={{ gap: 4 }}>name
              <input className="h3-in h3-grow" value={label} onChange={(e) => setLabel(e.target.value)} /></label>
          </div>
          <table className="h3-table h3-small">
            <thead><tr><th>A shot's</th><th>goes in the model's</th></tr></thead>
            <tbody>
              {Object.keys(WHAT).map((k) => (
                <tr key={k}>
                  <td>{WHAT[k]}</td>
                  <td className="h3-mono">{r.mapped[k] ?? <span className="h3-muted">— (the model doesn't take it, or it wasn't found)</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="h3-row h3-wrap h3-small" style={{ gap: 8 }}>
            <label className="h3-row" style={{ gap: 4 }}
              title="Who runs the model: its own provider, or another that serves it (Router translates the request). Prices and limits differ.">
              Provider
              <select className="h3-in" value={provider} onChange={(e) => setProvider(e.target.value)}>
                <option value="">the model's own (Comfy)</option>
                {PROVIDERS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </label>
            <label className="h3-row" style={{ gap: 4 }} title="When the provider is down, Router tries another (on unless turned off)">
              <input type="checkbox" checked={fallback} onChange={(e) => setFallback(e.target.checked)} /> let Router fall back to another
            </label>
          </div>
          {limits && (
            <div className="h3-col" style={{ gap: 4 }}>
              <div className="h3-h">
                Its limits
                <span className="h3-muted h3-small" style={{ textTransform: "none", fontWeight: 400 }}>
                  {" "}— from the schema; a field marked "check this" states this model's limit only in its prose
                </span>
              </div>
              <LimitsForm value={limits} onChange={setLimits} shared={r.shared}
                resolutionChoices={r.limits?.size.resolutions} />
            </div>
          )}
          <div className="h3-row h3-wrap h3-small" style={{ gap: 6 }}>
            <span>Try it on</span>
            <select className="h3-in" value={dryShot} onChange={(e) => setDryShot(e.target.value)} style={{ maxWidth: 140 }}>
              <option value="">the first shot with a subject</option>
              {(st?.shots ?? []).map((x) => <option key={x.shot} value={x.shot}>{x.shot}</option>)}
            </select>
            <button className="h3-btn" disabled={dryBusy} title="What it would send for that shot (proxy): nothing is uploaded or paid for"
              onClick={() => void dryRun()}>
              <i className={dryBusy ? "pi pi-spin pi-spinner" : "pi pi-eye"} /> Dry run (free)
            </button>
          </div>
          {dry && (dry.ok ? (
            <details open className="h3-small">
              <summary style={{ cursor: "pointer" }}>
                {dry.shot}: the request to {dry.model} ({dry.prompt_chars?.written ?? "?"} characters of prompt written)
              </summary>
              <pre className="h3-mono" style={{ whiteSpace: "pre-wrap", fontSize: 10, maxHeight: 260, overflow: "auto", margin: "4px 0 0" }}>
                {JSON.stringify(dry.arguments, null, 2)}
              </pre>
            </details>
          ) : <div className="h3-small h3-err">{dry.shot}: {dry.why}</div>)}
          {r.unplaced.length > 0 && (
            <div className="h3-small h3-err">It requires {r.unplaced.join(", ")}, which nothing was placed in: set it in the target.json below.</div>
          )}
          {r.warnings.map((w) => <div key={w} className="h3-small h3-warn">{w}</div>)}
          <button className="h3-link h3-small" style={{ alignSelf: "flex-start" }} onClick={() => setShowJson(!showJson)}>
            {showJson ? "Hide" : "Show"} the target.json (limits, presets, fixed arguments)
          </button>
          {showJson && (
            <textarea className="h3-in h3-mono" rows={16} value={json} spellCheck={false}
              onChange={(e) => setJson(e.target.value)} style={{ fontSize: 11 }} />
          )}
          <div className="h3-row" style={{ gap: 6 }}>
            <span className="h3-small h3-muted h3-grow">Saved as a draft: probe one shot (a paid render), look at the take, then enable it.</span>
            <select className="h3-in" value={scope} onChange={(e) => setScope(e.target.value as "user" | "show")}
              title="Every show: kept beside seriesmith's settings. This show: in its targets folder.">
              <option value="user">for every show</option>
              <option value="show">for this show only</option>
            </select>
            <button className="h3-btn h3-primary" disabled={saving || !id} onClick={() => void save()}>
              <i className={saving ? "pi pi-spin pi-spinner" : "pi pi-save"} /> Save as draft
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function Wizard({ onClose }: { onClose: () => void }) {
  const busy = useApp((s) => !!s.busy["target-inspect"]);
  const saving = useApp((s) => !!s.busy["target-save"]);
  const [files, setFiles] = useState<WorkflowFile[] | null>(null);
  const [pick, setPick] = useState("");
  const [proposal, setProposal] = useState<TargetProposal | null>(null);
  const [a, setA] = useState<Answers | null>(null);

  useEffect(() => {
    void loadWorkflows().then(setFiles);
  }, []);

  const set = (patch: Partial<Answers>) => setA((prev) => (prev ? { ...prev, ...patch } : prev));
  const read = async () => {
    const r = await inspectTarget({ workflow: pick });
    setProposal(r);
    setA(r ? answersFrom(r) : null);
  };
  const save = async () => {
    if (!proposal || !a) return;
    if (await saveCustomTarget(applyAnswers(proposal, a))) onClose();
  };
  const unanswered = proposal?.ambiguous.filter((x) => !a?.chosen[x.param]) ?? [];

  return (
    <div className="h3-mfile h3-col" style={{ gap: 6 }}>
      <div className="h3-row">
        <b className="h3-grow">Add a target from a workflow</b>
        <button className="h3-btn h3-icon" title="Close" onClick={onClose}>
          <i className="pi pi-times" />
        </button>
      </div>
      <div className="h3-row h3-small">
        <span className="h3-muted">Workflow</span>
        <select className="h3-in h3-grow" value={pick} onChange={(e) => setPick(e.target.value)}>
          <option value="">(choose one of ComfyUI's saved workflows)</option>
          {(files ?? []).map((f) => (
            <option key={f.name} value={f.name}>{f.name}{f.target ? "  (seriesmith's own)" : ""}</option>
          ))}
        </select>
        <button className="h3-btn" disabled={!pick || busy} onClick={() => void read()}>
          <i className={busy ? "pi pi-spin pi-spinner" : "pi pi-search"} /> Read it
        </button>
      </div>
      {!files && <div className="h3-small h3-muted">Asking ComfyUI what it has saved…</div>}
      {proposal && a && (
        <>
          {!!proposal.problems.length && (
            <div className="h3-note h3-note-err h3-small">
              This graph can't be a target yet:
              <ul className="h3-missing-list">{proposal.problems.map((p) => <li key={p}>{p}</li>)}</ul>
            </div>
          )}
          <div className="h3-small">
            Detected: {Object.entries(proposal.matched).map(([k, v]) => `${k} → ${v}`).join(", ") || "nothing"}
          </div>
          <div className="h3-lora">
            <label className="h3-small h3-muted">id</label>
            <input className="h3-in" value={a.id} onChange={(e) => set({ id: e.target.value })} />
            <label className="h3-small h3-muted">name</label>
            <input className="h3-in" value={a.label} onChange={(e) => set({ label: e.target.value })} />
          </div>
          <div className="h3-row h3-small">
            <span className="h3-muted" title="Frames are step × n + base, up to max">frames</span>
            <input className="h3-in" style={{ width: 70 }} value={a.step} onChange={(e) => set({ step: e.target.value })} title="step" />
            <input className="h3-in" style={{ width: 70 }} value={a.base} onChange={(e) => set({ base: e.target.value })} title="base" />
            <input className="h3-in" style={{ width: 90 }} value={a.max} onChange={(e) => set({ max: e.target.value })} title="longest" />
            <span className="h3-muted">size ×</span>
            <input className="h3-in" style={{ width: 70 }} value={a.sizeMultiple} onChange={(e) => set({ sizeMultiple: e.target.value })} />
            <span className="h3-muted">fps</span>
            <input className="h3-in" style={{ width: 80 }} value={a.fps} onChange={(e) => set({ fps: e.target.value })} title={`A number, or "series" to follow the series config`} />
          </div>
          <div className="h3-row h3-small">
            <span className="h3-muted">sound</span>
            <select className="h3-in" value={a.audio} onChange={(e) => set({ audio: e.target.value as Answers["audio"] })}>
              <option value="generate">the model makes it</option>
              <option value="none">silent (lay it in at the edit)</option>
            </select>
            <span className="h3-muted">prompt</span>
            <select className="h3-in" value={a.prompt} onChange={(e) => set({ prompt: e.target.value as Answers["prompt"] })}>
              <option value="prose">prose, with sound and spoken lines</option>
              <option value="prose_silent">prose, dialogue as silent acting</option>
            </select>
          </div>
          {proposal.ambiguous.map((amb) => (
            <div key={amb.param} className="h3-note h3-note-info h3-small">
              <div>{amb.ask}</div>
              <select className="h3-in" value={a.chosen[amb.param] ?? ""}
                      onChange={(e) => set({ chosen: { ...a.chosen, [amb.param]: e.target.value } })}>
                <option value="">(leave {amb.param} out)</option>
                {amb.candidates.map((c) => (
                  <option key={c.node} value={`${c.class_type}.${c.field}`}>
                    {c.class_type}.{c.field}{c.title ? ` — ${c.title}` : ""}
                    {c.value !== undefined ? ` (now ${String(c.value)})` : ""}
                  </option>
                ))}
              </select>
            </div>
          ))}
          {!!proposal.models.length && (
            <div className="h3-small">
              Model files: {proposal.models.map((m) => `${m.param} ${m.file}${m.family ? "" : " (family unknown)"}`).join(", ")}
            </div>
          )}
          {!!proposal.warnings.length && (
            <details className="h3-small">
              <summary>{proposal.warnings.length} thing(s) seriesmith guessed or couldn't bind</summary>
              <ul className="h3-missing-list">{proposal.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
            </details>
          )}
          <div className="h3-row h3-small">
            <button className="h3-btn" disabled={saving || !a.id || !!proposal.problems.length}
                    onClick={() => void save()}>
              <i className={saving ? "pi pi-spin pi-spinner" : "pi pi-save"} /> Save as a draft
            </button>
            {!!unanswered.length && (
              <span className="h3-muted">
                {unanswered.map((x) => x.param).join(", ")} stays unbound until you choose.
              </span>
            )}
          </div>
        </>
      )}
    </div>
  );
}
