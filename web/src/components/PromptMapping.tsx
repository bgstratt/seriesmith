// How a shot becomes what a model is sent, on a real shot. On top, what's edited: the prompt's
// templates beside the parts they can use (Prompt), and where each value goes in a hosted model's
// request (Fields). Underneath, what it comes to: the prompt as sent, the shotlist entry and the
// request. The same panel adds a model (`spec`, a target.json not saved yet, reporting edits to the
// wizard) and edits one (`id`, saved here). Nothing here is uploaded or paid for.

import { useEffect, useRef, useState } from "react";
import { savePromptTemplates } from "../actions";
import type { MappingRow, ModelSchema, PromptPart, PromptPreview } from "../api";
import { api } from "../host";
import { useApp } from "../store";
import { useRefs, useStatus } from "./hooks";

const PRE: React.CSSProperties = {
  whiteSpace: "pre-wrap", fontSize: 11, maxHeight: 280, overflow: "auto", margin: "4px 0 0",
  padding: 6, background: "rgba(127,127,127,0.1)", borderRadius: 3,
};

const SAMPLES: [string, string][] = [
  ["dialogue", "Dialogue"], ["voiceover", "Voiceover"], ["several", "Several subjects"], ["silent", "Silent"],
  ["first_frame", "First frame"], ["no_first_frame", "No first frame"],
];

/** A mapping's value, its field set to `field` and the rest of its shape kept. */
export function withField(role: string, spec: unknown, field: string): unknown {
  const f = field.trim();
  if (!f) return null;
  if (typeof spec === "string" || (spec === null || spec === undefined) && role === "prompt") return f;
  if (spec && typeof spec === "object") {
    const s = spec as Record<string, unknown>;
    for (const key of ["list", "name", "field", "switch"]) if (key in s) return { ...s, [key]: f };
    if ("fields" in s) return { ...s, fields: f.split(",").map((x) => x.trim()).filter(Boolean) };
  }
  // a value that had no place yet: a list for pictures, a named field for the rest
  if (role === "resolution") return { name: f, values: ["480p", "720p", "1080p"] };
  return ["references", "images", "voices"].includes(role) ? { list: f } : { name: f };
}

function show(v: unknown): string {
  if (v === null || v === undefined) return "";
  return typeof v === "string" ? v : JSON.stringify(v);
}

function Parts({ parts, onPick }: { parts: PromptPart[]; onPick: (name: string) => void }) {
  return (
    // scrolls both ways: a part's value is shown whole, on one line
    <div style={{ maxHeight: 190, overflow: "auto" }}>
      <div className="h3-col" style={{ gap: 1, width: "max-content", minWidth: "100%" }}>
        {parts.map((p) => (
          <button key={p.name} className="h3-pick-row h3-row" style={{ gap: 6, textAlign: "left", whiteSpace: "nowrap" }}
            title={`${p.about}. Click to put {${p.name}} in the template.`} onClick={() => onPick(p.name)}>
            <span className="h3-mono h3-small" style={{ flex: "0 0 96px" }}>{p.name}</span>
            <span className={`h3-small${p.value ? "" : " h3-muted"}`}>{p.value || "(empty on this shot)"}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function TemplateBox({ label, hint, value, parts, problems, onChange }: {
  label: string; hint: string; value: string; parts: PromptPart[]; problems: string[];
  onChange: (v: string) => void;
}) {
  const area = useRef<HTMLTextAreaElement>(null);
  function insert(name: string) {
    const el = area.current;
    const at = el?.selectionStart ?? value.length;
    const to = el?.selectionEnd ?? value.length;
    const text = `{${name}}`;
    onChange(value.slice(0, at) + text + value.slice(to));
    requestAnimationFrame(() => {
      el?.focus();
      el?.setSelectionRange(at + text.length, at + text.length);
    });
  }
  return (
    <div className="h3-col" style={{ gap: 4 }}>
      <div className="h3-small"><b>{label}</b> <span className="h3-muted">{hint}</span></div>
      <div className="h3-row" style={{ gap: 8, alignItems: "stretch", flexWrap: "wrap" }}>
        <textarea ref={area} className="h3-in h3-mono" rows={5} spellCheck={false} value={value}
          style={{ flex: "1 1 280px", fontSize: 12 }} onChange={(e) => onChange(e.target.value)} />
        <div style={{ flex: "1 1 280px", minWidth: 0 }}><Parts parts={parts} onPick={insert} /></div>
      </div>
      {problems.map((p) => <div key={p} className="h3-small h3-err">{p}</div>)}
    </div>
  );
}

/** A JSON box that only reports text that parses, and says when it doesn't. */
function JsonBox({ value, rows, onChange }: { value: unknown; rows: number; onChange: (v: unknown) => void }) {
  const [text, setText] = useState(() => JSON.stringify(value ?? null, null, 2));
  const [bad, setBad] = useState("");
  return (
    <div className="h3-col" style={{ gap: 2 }}>
      <textarea className="h3-in h3-mono" rows={rows} spellCheck={false} value={text} style={{ fontSize: 11 }}
        onChange={(e) => {
          setText(e.target.value);
          try {
            onChange(JSON.parse(e.target.value));
            setBad("");
          } catch (err) {
            setBad((err as Error).message);
          }
        }} />
      {bad && <div className="h3-small h3-err">{bad}</div>}
    </div>
  );
}

function FieldRow({ row, changed, listId, onChange }: {
  row: MappingRow; changed: boolean; listId: string; onChange: (spec: unknown) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <tr>
        <td>{row.what}{changed && <span className="h3-warn" title="Changed from the model's own"> •</span>}</td>
        <td className="h3-mono h3-ell" style={{ maxWidth: 170 }} title={show(row.now)}>
          {row.now === null || row.now === undefined ? <span className="h3-muted">not sent</span> : show(row.now)}
        </td>
        <td>
          <input className="h3-in h3-mono" list={listId} style={{ width: "100%", minWidth: 120 }} value={row.field}
            placeholder="not sent" spellCheck={false} onChange={(e) => onChange(withField(row.role, row.spec, e.target.value))} />
        </td>
        <td>
          <button className="h3-link h3-small" title="Everything about this value: its limits, its list item, how it's written"
            onClick={() => setOpen(!open)}>{open ? "hide" : "more"}</button>
        </td>
      </tr>
      {open && (
        <tr>
          <td colSpan={4}>
            {/* remade when the field box changes the value under it */}
            <JsonBox key={JSON.stringify(row.spec)} value={row.spec} rows={6} onChange={onChange} />
          </td>
        </tr>
      )}
    </>
  );
}

function FieldsTab({ view, schema, inputs, setInput, setArguments }: {
  view: PromptPreview; schema: ModelSchema | null; inputs: Record<string, unknown>;
  setInput: (role: string, spec: unknown) => void; setArguments: (a: Record<string, unknown>) => void;
}) {
  const rows = view.rows ?? [];
  const placed = new Set(rows.flatMap((r) => r.field.split(",").map((x) => x.trim())).filter(Boolean));
  const fixed = Object.keys(view.fixed_arguments ?? {});
  const free = (schema?.fields ?? []).filter((f) => !f.path.includes(".") && !placed.has(f.path) && !fixed.includes(f.path));
  const listId = `h3-fields-${view.id}`;
  const lacking = view.unfilled ?? [];
  return (
    <div className="h3-col" style={{ gap: 6 }}>
      <datalist id={listId}>
        {(schema?.fields ?? []).map((f) => <option key={f.path} value={f.path}>{f.type}{f.required ? " (required)" : ""}</option>)}
      </datalist>
      <table className="h3-table h3-small">
        <thead><tr><th>Value</th><th>On {view.shot}</th><th>The API's field</th><th /></tr></thead>
        <tbody>
          {rows.map((r) => (
            <FieldRow key={r.role} row={r} changed={r.role in inputs} listId={listId}
              onChange={(spec) => setInput(r.role, spec)} />
          ))}
        </tbody>
      </table>
      {lacking.map((f) => (
        <div key={f} className="h3-small h3-err">The model requires {f}, and nothing fills it: map a value to it, or set it below.</div>
      ))}
      {schema && !schema.available && (
        <div className="h3-small h3-muted">Couldn't read the model's fields, so required ones aren't checked: {schema.why}</div>
      )}
      {free.length > 0 && (
        <details className="h3-small">
          <summary style={{ cursor: "pointer" }}>The model's other fields ({free.length})</summary>
          <table className="h3-table h3-small">
            <tbody>
              {free.map((f) => (
                <tr key={f.path} title={f.about}>
                  <td className={`h3-mono${f.required ? " h3-err" : ""}`}>{f.path}{f.required ? " *" : ""}</td>
                  <td className="h3-muted">{f.type}</td>
                  <td className="h3-muted h3-ell" style={{ maxWidth: 260 }}>
                    {f.values ? f.values.join(", ") : f.min !== undefined || f.max !== undefined ? `${f.min ?? ""} to ${f.max ?? ""}` : f.about}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
      <details className="h3-small">
        <summary style={{ cursor: "pointer" }}>Sent as they are ({fixed.length})</summary>
        <JsonBox value={view.fixed_arguments ?? {}} rows={5}
          onChange={(v) => { if (v && typeof v === "object" && !Array.isArray(v)) setArguments(v as Record<string, unknown>); }} />
      </details>
    </div>
  );
}

/** Where a model's mapping differs from its own: {value: its place, or null when it sends none}.
 * What a save replaces, so a mapping saved earlier has to start in the panel's edits. */
export function mappingChanges(now: Record<string, unknown> = {}, own: Record<string, unknown> = {}): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const k of new Set([...Object.keys(now), ...Object.keys(own)])) {
    if (JSON.stringify(now[k] ?? null) !== JSON.stringify(own[k] ?? null)) out[k] = now[k] ?? null;
  }
  return out;
}

/** What the panel has that differs from the model's own. */
export interface PanelEdits {
  template: string;
  request: string;
  /** a value's new place, or null to send none */
  inputs: Record<string, unknown>;
  /** the arguments sent as they are, when changed */
  arguments?: Record<string, unknown>;
}

export function PromptMapping({ id, kind = "video", spec, limits, onEdit, onBlocked }: {
  id?: string;
  kind?: string;
  spec?: Record<string, unknown>;
  /** the limit changes the wizard's form has made */
  limits?: Record<string, unknown>;
  onEdit?: (edits: PanelEdits, shipped: PromptPreview["shipped"]) => void;
  /** whether this can't be saved as it stands (a wrong template, a required field unfilled) */
  onBlocked?: (blocked: boolean) => void;
}) {
  const ep = useApp((s) => s.ep);
  const saving = useApp((s) => !!s.busy["prompt-save"]);
  const st = useStatus();
  const refs = useRefs(kind === "image" ? ep : null);
  const [shot, setShot] = useState("");
  const [pass, setPass] = useState<"proxy" | "final">("proxy");
  const [tab, setTab] = useState<"prompt" | "fields">(kind === "image" ? "fields" : "prompt");
  const [template, setTemplate] = useState<string | null>(null);
  const [request, setRequest] = useState<string | null>(null);
  const [inputs, setInputs] = useState<Record<string, unknown>>({});
  const [fixed, setFixed] = useState<Record<string, unknown> | undefined>(undefined);
  const [saved, setSaved] = useState<{ template: string; request: string; mapping: string } | null>(null);
  const [view, setView] = useState<PromptPreview | null>(null);
  const [takes, setTakes] = useState<number | null>(null);
  const [samples, setSamples] = useState<Record<string, string>>({});
  const [schema, setSchema] = useState<ModelSchema | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // a save changes what the server says, whether or not the text changed
  const [revision, setRevision] = useState(0);
  const asked = useRef(0);
  // the model's own, as first read: a wizard's target.json takes the panel's edits as it goes
  const own = useRef<PromptPreview["shipped"] | null>(null);
  const specKey = spec ? JSON.stringify(spec) : "";
  const inputsKey = JSON.stringify(inputs);
  const fixedKey = JSON.stringify(fixed ?? null);
  const limitsKey = JSON.stringify(limits ?? null);
  // Router's is read by its model id; a provider's came with what was pasted
  const hostedModel = view?.hosted && !view.schema && !spec?.api
    ? view.model ?? (spec?.router as { model?: string } | undefined)?.model : undefined;

  // the model's fields, once: reading a schema is free, and kept an hour by the server
  useEffect(() => {
    if (!hostedModel || schema) return;
    let live = true;
    api().modelSchema(hostedModel).then((s) => { if (live) setSchema(s); })
      .catch((e: Error) => { if (live) setSchema({ available: false, why: e.message, required: [], fields: [] }); });
    return () => { live = false; };
  }, [hostedModel]);  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!ep) return;
    const mine = ++asked.current;
    setBusy(true);
    const timer = setTimeout(() => {
      api().promptPreview({
        ep, ...(spec ? { target: spec, ...(limits ? { limits } : {}) } : { id }),
        pass, ...(kind === "image" ? { ref: shot || null } : { shot: shot || null }),
        ...(template !== null && kind !== "image" ? { template } : {}), ...(request !== null ? { request } : {}),
        ...(Object.keys(inputs).length ? { inputs } : {}), ...(fixed ? { arguments: fixed } : {}),
        ...(schema?.available ? { required: schema.required } : {}),
        count: takes === null && kind !== "image",
      }).then((v) => {
        if (mine !== asked.current) return;
        setView(v);
        setErr(null);
        if (!own.current) own.current = v.shipped;
        if (v.takes_on_model !== undefined) setTakes(v.takes_on_model);
        if (v.samples) setSamples(v.samples);
        if (template === null) {
          const was = mappingChanges(v.inputs, v.shipped.inputs);
          const argsWere = JSON.stringify(v.fixed_arguments ?? {}) !== JSON.stringify(v.shipped.arguments ?? {})
            ? v.fixed_arguments : undefined;
          setTemplate(v.template);
          setRequest(v.request);
          setInputs(was);
          setFixed(argsWere);
          setSaved({ template: v.template, request: v.request, mapping: JSON.stringify([was, argsWere ?? null]) });
        }
      }).catch((e: Error) => {
        if (mine === asked.current) setErr(e.message);
      }).finally(() => {
        if (mine === asked.current) setBusy(false);
      });
    }, template === null ? 0 : 250);
    return () => clearTimeout(timer);
    // the keys stand for spec, inputs and fixed; takes is only asked for once
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ep, id, specKey, limitsKey, pass, shot, template, request, inputsKey, fixedKey, revision, schema]);

  const wrongNow = view ? [...view.problems.template, ...view.problems.request] : [];
  const blocked = !!wrongNow.length || !!view?.unfilled?.length;
  useEffect(() => { onBlocked?.(blocked); }, [blocked]);  // eslint-disable-line react-hooks/exhaustive-deps

  if (err && !view) return <div className="h3-small h3-err">{err}</div>;
  if (!view || template === null || request === null) {
    return <div className="h3-small h3-muted"><i className="pi pi-spin pi-spinner" /> Reading the {kind === "image" ? "ref" : "shot"}…</div>;
  }
  const shipped = own.current ?? view.shipped;
  const dirty = !!saved && (template !== saved.template || request !== saved.request
    || JSON.stringify([inputs, fixed ?? null]) !== saved.mapping);
  const atShipped = template === shipped.template && request === shipped.request
    && !Object.keys(inputs).length && !fixed;
  const image = kind === "image";

  function report(next: Partial<PanelEdits>) {
    onEdit?.({ template: template!, request: request!, inputs, ...(fixed ? { arguments: fixed } : {}), ...next }, shipped);
  }
  function editPrompt(t: string, r: string) {
    setTemplate(t);
    setRequest(r);
    report({ template: t, request: r });
  }
  function setInput(role: string, s: unknown) {
    const next = { ...inputs, [role]: s };
    if (JSON.stringify(s ?? null) === JSON.stringify(shipped.inputs?.[role] ?? null)) delete next[role];
    setInputs(next);
    report({ inputs: next });
  }
  function setArguments(a: Record<string, unknown>) {
    const same = JSON.stringify(a) === JSON.stringify(shipped.arguments ?? {});
    setFixed(same ? undefined : a);
    report({ arguments: same ? undefined : a });
  }

  async function save() {
    const ok = await savePromptTemplates(id!, template! === shipped.template ? "" : template!,
      request! === shipped.request ? "" : request!, inputs, fixed);
    if (ok) {
      setSaved({ template: template!, request: request!, mapping: JSON.stringify([inputs, fixed ?? null]) });
      setRevision((n) => n + 1);
    }
  }

  async function backToShipped() {
    const ok = await savePromptTemplates(id!, "", "", {}, undefined);
    if (ok) {
      setTemplate(shipped.template);
      setRequest(shipped.request);
      setInputs({});
      setFixed(undefined);
      setSaved({ template: shipped.template, request: shipped.request, mapping: JSON.stringify([{}, null]) });
      setRevision((n) => n + 1);
    }
  }

  return (
    <div className="h3-col" style={{ gap: 8 }}>
      <div className="h3-row h3-wrap h3-small" style={{ gap: 8 }}>
        <span>Try on</span>
        {image ? (
          <select className="h3-in" value={shot || view.shot} onChange={(e) => setShot(e.target.value)} style={{ maxWidth: 180 }}>
            {(refs ?? []).filter((r) => r.kind !== "voice").map((r) => <option key={r.id} value={r.id}>{r.name || r.id}</option>)}
          </select>
        ) : (
          <>
            <select className="h3-in" value={shot || view.shot} onChange={(e) => setShot(e.target.value)} style={{ maxWidth: 160 }}>
              {(st?.shots ?? []).map((x) => <option key={x.shot} value={x.shot}>{x.shot}</option>)}
            </select>
            <span className="h3-seg">
              {(["proxy", "final"] as const).map((p) => (
                <button key={p} className={pass === p ? "h3-on" : ""} onClick={() => setPass(p)}>{p === "proxy" ? "Proxy" : "Final"}</button>
              ))}
            </span>
          </>
        )}
        <span className="h3-muted h3-grow">Free: nothing is uploaded or sent{busy ? " …" : ""}</span>
        {view.changed && <span className="h3-warn">Changed for this show</span>}
      </div>
      {!image && Object.keys(samples).length > 0 && (
        <div className="h3-row h3-wrap h3-small" style={{ gap: 4 }}>
          {SAMPLES.filter(([k]) => samples[k]).map(([k, label]) => (
            <button key={k} className={`h3-btn${view.shot === samples[k] ? " h3-on" : ""}`} title={`${samples[k]}: the first shot of this kind`}
              onClick={() => setShot(samples[k])}>{label}</button>
          ))}
        </div>
      )}

      {err && <div className="h3-small h3-err">{err}</div>}
      {!view.ok && <div className="h3-note h3-note-err h3-small">{view.shot}: {view.why}</div>}

      {view.hosted && (
        <span className="h3-seg" style={{ alignSelf: "flex-start" }}>
          {(["prompt", "fields"] as const).map((x) => (
            <button key={x} className={tab === x ? "h3-on" : ""} onClick={() => setTab(x)}>
              {x === "prompt" ? "Prompt" : "Fields"}{x === "fields" && view.unfilled?.length ? " !" : ""}
            </button>
          ))}
        </span>
      )}

      {tab === "fields" && view.hosted ? (
        <FieldsTab view={view} schema={view.schema ?? schema} inputs={inputs} setInput={setInput} setArguments={setArguments} />
      ) : (
        <>
          {view.editable && (
            <TemplateBox label="Shot's prompt" hint="what the shotlist holds" value={template}
              parts={view.parts} problems={view.problems.template} onChange={(v) => editPrompt(v, request)} />
          )}
          {view.hosted && (
            <TemplateBox label="What's sent around it" hint="what only the request knows: the pictures' numbers" value={request}
              parts={view.request_parts} problems={view.problems.request} onChange={(v) => editPrompt(template, v)} />
          )}
          {view.editable || view.hosted ? (
            <div className="h3-small h3-muted">
              {"{part}"} puts a part in. An empty part leaves no gap. [[ … ]] is a section: it goes whole if a part in it is empty.
            </div>
          ) : (
            <div className="h3-note h3-small">
              This model writes its own prompt, so it has no template to change yet. Here's what it writes for this {image ? "ref" : "shot"}.
            </div>
          )}
        </>
      )}

      {view.overridden && (
        <div className="h3-note h3-small">{view.shot} has its own prompt edit, which wins over the template on this shot.</div>
      )}
      {view.request_error && <div className="h3-small h3-err">The request can't be made: {view.request_error}</div>}

      <div style={{ opacity: wrongNow.length ? 0.5 : 1 }}>
        <div className="h3-small">
          <b>Prompt as sent</b>{" "}
          <span className="h3-muted">
            {view.sent?.length ?? 0}{view.limit ? ` of ${view.limit}` : ""} characters
            {wrongNow.length ? " · without the template that's wrong" : ""}
          </span>
        </div>
        <pre className="h3-mono" style={PRE}>{view.sent}</pre>
      </div>

      {view.entry && (
        <details open className="h3-small">
          <summary style={{ cursor: "pointer" }}><b>Shotlist entry</b> <span className="h3-muted">{view.shot}, {view.pass}</span></summary>
          <pre className="h3-mono" style={PRE}>{JSON.stringify(view.entry, null, 2)}</pre>
        </details>
      )}
      {view.calls && (
        <details open className="h3-small">
          <summary style={{ cursor: "pointer" }}><b>The calls</b> <span className="h3-muted">what a take would do, in order; your key is hidden</span></summary>
          <div className="h3-col" style={{ gap: 4 }}>
            {view.calls.map((c, i) => (
              <div key={i}>
                <div className="h3-mono" style={{ wordBreak: "break-all" }}>
                  <span className="h3-muted">{i + 1}. {c.what}:</span> {c.method} {c.url}
                </div>
                <div className="h3-muted" style={{ marginLeft: 12 }}>
                  {c.key}{c.answers ? ` · answers with ${c.answers}` : ""}{c.takes ? ` · takes ${JSON.stringify(c.takes)}` : ""}
                  {c.until ? ` · until ${JSON.stringify((c.until as { status?: unknown; done?: unknown }).status)} is ${JSON.stringify((c.until as { done?: unknown }).done)}` : ""}
                </div>
                {c.sends !== undefined && (
                  <pre className="h3-mono" style={{ ...PRE, maxHeight: 180 }}>{JSON.stringify(c.sends, null, 2)}</pre>
                )}
              </div>
            ))}
          </div>
        </details>
      )}
      {view.arguments && !view.calls && (
        <details open={tab === "fields"} className="h3-small">
          <summary style={{ cursor: "pointer" }}><b>Request</b> <span className="h3-muted">to {view.model}; pictures shown as local files</span></summary>
          <pre className="h3-mono" style={PRE}>{JSON.stringify(view.arguments, null, 2)}</pre>
        </details>
      )}

      {(view.editable || view.hosted) && !spec && (
        <div className="h3-row h3-wrap h3-small" style={{ gap: 6 }}>
          <span className="h3-muted h3-grow">
            {takes ? `${takes} take${takes === 1 ? "" : "s"} on this model in this episode would be marked stale. Nothing is re-rendered. ` : ""}
            Saved in this show, for everyone who has it.
          </span>
          {(view.changed || !atShipped) && (
            <button className="h3-btn" disabled={saving} title="Drop this show's change: the model's own again"
              onClick={() => void backToShipped()}>
              <i className="pi pi-undo" /> Back to shipped
            </button>
          )}
          <button className="h3-btn h3-primary" disabled={saving || !dirty || blocked}
            title={blocked ? "Fix what's marked first" : undefined} onClick={() => void save()}>
            <i className={saving ? "pi pi-spin pi-spinner" : "pi pi-save"} /> Save for this show
          </button>
        </div>
      )}
    </div>
  );
}
