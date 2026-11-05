// Providers of your own and a model on one (docs/DESIGN.md, section 9). ProvidersCard: their keys,
// write-only, and adding a definition. ApiModelWizard: a model's API reference pasted in, read into
// a proposed mapping, looked over in the same Prompt & mapping panel, saved as a draft.

import { useEffect, useMemo, useState } from "react";
import { saveCustomTarget } from "../actions";
import type { ProviderRow, ProviderSpecRead } from "../api";
import { api } from "../host";
import { useApp } from "../store";
import { PromptMapping, type PanelEdits } from "./PromptMapping";
import type { PromptPreview } from "../api";

function useProviders() {
  const [rows, setRows] = useState<ProviderRow[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    api().providers().then((d) => { if (live) setRows(d.providers); })
      .catch((e: Error) => { if (live) setErr(e.message); });
    return () => { live = false; };
  }, []);
  return { rows, setRows, err, setErr };
}

function ProviderKey({ row, onChanged, onError }: {
  row: ProviderRow; onChanged: (rows: ProviderRow[]) => void; onError: (m: string) => void;
}) {
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  async function put(value: string | null) {
    setBusy(true);
    try {
      onChanged((await api().putProviderKey(row.id, value)).providers);
      setKey("");
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="h3-row h3-wrap h3-small" style={{ gap: 6 }}>
      <b style={{ minWidth: 110 }} title={row.base_url}>{row.label}</b>
      {row.untested && <span className="h3-warn" title="Written from its docs, and not yet proved by a real render">untested</span>}
      {row.key_from_env ? (
        <span className="h3-muted">Key set by the environment ({row.key_from_env}): change it there.</span>
      ) : (
        <>
          <input className="h3-in h3-mono h3-grow" style={{ minWidth: 160 }} type="password" autoComplete="off" value={key}
            placeholder={row.has_key ? "a new key replaces the one saved" : "its API key"}
            onChange={(e) => setKey(e.target.value)} />
          <button className="h3-btn" disabled={busy || !key.trim()} onClick={() => void put(key)}>Save key</button>
          {row.has_key && <button className="h3-btn" disabled={busy} onClick={() => void put(null)}>Remove</button>}
        </>
      )}
      {row.docs && <a className="h3-link" href={row.docs} target="_blank" rel="noreferrer">docs</a>}
    </div>
  );
}

const DEFINITION_EXAMPLE = JSON.stringify({
  id: "mine", label: "My provider", base_url: "https://api.example.com/v1", auth: { type: "bearer" }, parallel: 3,
  files: { via: "datauri" },
  steps: [
    { method: "POST", url: "/generate", json: { model: "$model", "...": "$args" }, take: { task: "id" } },
    { method: "GET", url: "/jobs/{task}", until: { status: "status", done: ["completed"], failed: ["failed"], error: "error", every: 5, timeout: 3600 } },
  ],
  result: { files: "outputs" },
}, null, 2);

/** The providers on this machine: a key for each (never shown again), and adding your own. */
export function ProvidersCard() {
  const { rows, setRows, err, setErr } = useProviders();
  const [adding, setAdding] = useState(false);
  const [text, setText] = useState(DEFINITION_EXAMPLE);
  const [busy, setBusy] = useState(false);
  async function add() {
    let definition: Record<string, unknown>;
    try {
      definition = JSON.parse(text) as Record<string, unknown>;
    } catch (e) {
      setErr(`That isn't valid JSON: ${(e as Error).message}`);
      return;
    }
    setBusy(true);
    try {
      setRows((await api().putProvider(definition)).providers);
      setAdding(false);
      setErr(null);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="h3-col" style={{ gap: 4 }}>
      <div className="h3-h">
        API providers
        <span className="h3-muted h3-small" style={{ textTransform: "none", fontWeight: 400 }}>
          {" "}— keys stay on this machine, and go only to that provider's own address
        </span>
      </div>
      {!rows && !err && <div className="h3-small h3-muted"><i className="pi pi-spin pi-spinner" /> Reading the providers…</div>}
      {(rows ?? []).map((r) => (
        <ProviderKey key={r.id} row={r} onChanged={setRows} onError={setErr} />
      ))}
      {err && <div className="h3-small h3-err">{err}</div>}
      <button className="h3-link h3-small" style={{ alignSelf: "flex-start" }} onClick={() => setAdding(!adding)}>
        {adding ? "Cancel" : "Add a provider…"}
      </button>
      {adding && (
        <div className="h3-col" style={{ gap: 4 }}>
          <div className="h3-small h3-muted">
            How it's reached, as data: its address, how it takes its key, the requests a job makes, and where the files are.
            An LLM can draft this from a provider's docs. The key isn't part of it.
          </div>
          <textarea className="h3-in h3-mono" rows={16} spellCheck={false} value={text} style={{ fontSize: 11 }}
            onChange={(e) => setText(e.target.value)} />
          <button className="h3-btn h3-primary" style={{ alignSelf: "flex-start" }} disabled={busy} onClick={() => void add()}>
            <i className="pi pi-save" /> Save provider
          </button>
        </div>
      )}
    </div>
  );
}

/** A model on a provider: its reference pasted, its mapping proposed and looked over, saved as a draft. */
export function ApiModelWizard({ onClose }: { onClose: () => void }) {
  const saving = useApp((s) => !!s.busy["target-save"]);
  const { rows, setRows, err: listErr, setErr: setListErr } = useProviders();
  const [service, setService] = useState("");
  const [model, setModel] = useState("");
  const [kind, setKind] = useState<"video" | "image">("video");
  const [text, setText] = useState("");
  const [path, setPath] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [r, setR] = useState<ProviderSpecRead | null>(null);
  const [id, setId] = useState("");
  const [label, setLabel] = useState("");
  const [json, setJson] = useState("");
  const [scope, setScope] = useState<"user" | "show">("user");
  const [blocked, setBlocked] = useState(false);
  const row = (rows ?? []).find((x) => x.id === service);

  async function read(which?: string) {
    setBusy(true);
    setErr(null);
    try {
      const got = await api().readProviderSpec({ service, model: model.trim(), kind, text, ...(which ?? path ? { path: which ?? path } : {}) });
      setR(got);
      if (got.proposal) {
        setId(String(got.proposal.id));
        setLabel(String(got.proposal.label));
        setJson(JSON.stringify(got.proposal, null, 2));
      }
    } catch (e) {
      setErr((e as Error).message);
      setR(null);
    } finally {
      setBusy(false);
    }
  }

  const draft = useMemo(() => {
    if (!json) return null;
    try {
      return { ...(JSON.parse(json) as Record<string, unknown>), id: id || "new_model" };
    } catch {
      return null;
    }
  }, [json, id]);

  function setEdits(edits: PanelEdits, own: PromptPreview["shipped"]) {
    setJson((was) => {
      const spec = JSON.parse(was) as { recipe?: Record<string, unknown>; api?: Record<string, unknown> };
      const recipe = { ...spec.recipe };
      delete recipe.prompt_template;
      delete recipe.prompt_request;
      if (edits.template !== own.template) recipe.prompt_template = edits.template;
      if (edits.request !== own.request) recipe.prompt_request = edits.request;
      const inputs: Record<string, unknown> = { ...own.inputs };
      for (const [k, v] of Object.entries(edits.inputs)) {
        if (v === null) delete inputs[k];
        else inputs[k] = v;
      }
      return JSON.stringify({ ...spec, recipe, api: { ...spec.api, inputs, arguments: edits.arguments ?? own.arguments ?? {} } }, null, 2);
    });
  }

  async function save() {
    if (!draft) return;
    if (await saveCustomTarget({ ...draft, id, label, draft: true }, { scope })) onClose();
  }

  return (
    <div className="h3-col h3-mfile" style={{ gap: 6 }}>
      <div className="h3-row h3-wrap h3-small" style={{ gap: 6 }}>
        <b className="h3-grow">Add a model from another API</b>
        <button className="h3-btn h3-icon" title="Close" onClick={onClose}><i className="pi pi-times" /></button>
      </div>
      <div className="h3-row h3-wrap h3-small" style={{ gap: 6 }}>
        <label className="h3-row" style={{ gap: 4 }}>Provider
          <select className="h3-in" value={service} onChange={(e) => setService(e.target.value)}>
            <option value="">(choose)</option>
            {(rows ?? []).map((x) => <option key={x.id} value={x.id}>{x.label}{x.has_key ? "" : " (no key yet)"}</option>)}
          </select>
        </label>
        <label className="h3-row h3-grow" style={{ gap: 4 }}>Model id
          <input className="h3-in h3-mono h3-grow" spellCheck={false} value={model} placeholder="the id the provider knows it by"
            onChange={(e) => setModel(e.target.value)} />
        </label>
        <span className="h3-seg">
          {(["video", "image"] as const).map((k) => (
            <button key={k} className={kind === k ? "h3-on" : ""} onClick={() => setKind(k)}>{k === "video" ? "Video" : "Image"}</button>
          ))}
        </span>
      </div>
      {listErr && <div className="h3-small h3-err">{listErr}</div>}
      {row && !row.has_key && <ProviderKey row={row} onChanged={setRows} onError={setListErr} />}
      {row?.untested && (
        <div className="h3-small h3-warn">{row.label}'s definition was written from its docs and hasn't been proved by a real render yet.</div>
      )}
      <div className="h3-small">
        <b>The API's reference</b>{" "}
        <span className="h3-muted">
          an OpenAPI document (paste it, or its address), an example cURL from the docs, or an example request's JSON.
          A key in a pasted cURL isn't kept.
        </span>
      </div>
      <textarea className="h3-in h3-mono" rows={8} spellCheck={false} value={text} style={{ fontSize: 11 }}
        placeholder={'curl -X POST https://api.example.com/v1/generate -H "Authorization: Bearer ..." -d \'{"prompt": "a cat", "duration": 5, "image_url": "https://..."}\''}
        onChange={(e) => setText(e.target.value)} />
      {r && !r.proposal && (
        <label className="h3-row h3-small" style={{ gap: 4 }}>This document has several requests. Which makes the {kind}?
          <select className="h3-in" value={path} onChange={(e) => { setPath(e.target.value); if (e.target.value) void read(e.target.value); }}>
            <option value="">(choose)</option>
            {r.paths.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </label>
      )}
      <button className="h3-btn h3-primary" style={{ alignSelf: "flex-start" }} disabled={busy || !service || !model.trim() || !text.trim()}
        onClick={() => void read()}>
        <i className={busy ? "pi pi-spin pi-spinner" : "pi pi-search"} /> Read it
      </button>
      {err && <div className="h3-small h3-err">{err}</div>}
      {r?.proposal && draft && (
        <>
          <div className="h3-row h3-wrap" style={{ gap: 6 }}>
            <label className="h3-small h3-row" style={{ gap: 4 }}>id
              <input className="h3-in h3-mono" style={{ width: 200 }} value={id} onChange={(e) => setId(e.target.value)} /></label>
            <label className="h3-small h3-row h3-grow" style={{ gap: 4 }}>name
              <input className="h3-in h3-grow" value={label} onChange={(e) => setLabel(e.target.value)} /></label>
          </div>
          {(r.warnings ?? []).map((w) => <div key={w} className="h3-small h3-warn">{w}</div>)}
          {(r.unplaced ?? []).length > 0 && (
            <div className="h3-small h3-warn">As first read, it requires {r.unplaced!.join(", ")}, which nothing was placed in: map it under Fields.</div>
          )}
          <PromptMapping key={String(r.proposal.id)} kind={kind} spec={draft} onEdit={setEdits} onBlocked={setBlocked} />
          <div className="h3-row" style={{ gap: 6 }}>
            <span className="h3-small h3-muted h3-grow">Saved as a draft: probe one take (paid), look at it, then enable it.</span>
            <select className="h3-in" value={scope} onChange={(e) => setScope(e.target.value as "user" | "show")}
              title="Every show: kept beside seriesmith's settings. This show: in its targets folder.">
              <option value="user">for every show</option>
              <option value="show">for this show only</option>
            </select>
            <button className="h3-btn h3-primary" disabled={saving || !id || blocked}
              title={blocked ? "A template is wrong, or a required field is unfilled: see above" : undefined} onClick={() => void save()}>
              <i className={saving ? "pi pi-spin pi-spinner" : "pi pi-save"} /> Save as draft
            </button>
          </div>
        </>
      )}
    </div>
  );
}
