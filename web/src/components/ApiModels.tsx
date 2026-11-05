// Providers of your own and a model on one (docs/DESIGN.md, section 9). ProvidersCard: their keys,
// write-only, and adding a definition. ApiModelWizard: a model's API reference pasted in, read into
// a proposed mapping, looked over in the same Prompt & mapping panel, saved as a draft.

import { useEffect, useMemo, useState } from "react";
import { saveCustomTarget } from "../actions";
import type { ProviderDraft, ProviderRow, ProviderSpecRead } from "../api";
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
            placeholder={row.has_key ? "a new key replaces the one saved" : row.key_hint || "its API key"}
            onChange={(e) => setKey(e.target.value)} />
          <button className="h3-btn" disabled={busy || !key.trim()} onClick={() => void put(key)}>Save key</button>
          {row.has_key && <button className="h3-btn" disabled={busy} onClick={() => void put(null)}>Remove</button>}
        </>
      )}
      {row.docs && <a className="h3-link" href={row.docs} target="_blank" rel="noreferrer">docs</a>}
    </div>
  );
}

function Field({ label, hint, value, onChange, mono = true, wide = false }: {
  label: string; hint?: string; value: unknown; onChange: (v: string) => void; mono?: boolean; wide?: boolean;
}) {
  return (
    <label className="h3-row h3-small" style={{ gap: 4, flex: wide ? "1 1 100%" : "1 1 240px" }} title={hint}>
      <span style={{ minWidth: 120 }}>{label}</span>
      <input className={`h3-in h3-grow${mono ? " h3-mono" : ""}`} spellCheck={false} placeholder={hint} value={String(value ?? "")}
        onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}

/** A provider set up from what its docs give: paste the request, look over what it comes to,
 * add the key, check it, save. The definition underneath is there to see and edit, not to write. */
export function AddProvider({ onSaved, onCancel }: {
  onSaved: (rows: ProviderRow[], id: string, model: string, reference: string) => void; onCancel: () => void;
}) {
  const [text, setText] = useState("");
  const [answer, setAnswer] = useState("");
  const [poll, setPoll] = useState("");
  const [pollAnswer, setPollAnswer] = useState("");
  const [draft, setDraft] = useState<ProviderDraft | null>(null);
  const [form, setForm] = useState<Record<string, unknown> | null>(null);
  const [model, setModel] = useState("");
  const [key, setKey] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [check, setCheck] = useState<{ reached: boolean; key_ok: boolean; proves_key?: boolean; status: number | null; says: string } | null>(null);
  const [path, setPath] = useState("");

  async function read(which?: string) {
    setBusy(true);
    setErr(null);
    try {
      const got = await api().draftProvider({ text, answer, poll, poll_answer: pollAnswer, ...(which ?? path ? { path: which ?? path } : {}) });
      setDraft(got);
      setForm(got.form);
      setModel(got.model ?? "");
      setCheck(null);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  // the definition follows the form: one place says what a form comes to
  useEffect(() => {
    if (!form) return;
    let live = true;
    const timer = setTimeout(() => {
      api().draftProvider({ form }).then((got) => { if (live) setDraft((was) => ({ ...was, ...got, notes: was?.notes, paths: was?.paths })); })
        .catch((e: Error) => { if (live) setErr(e.message); });
    }, 250);
    return () => { live = false; clearTimeout(timer); };
  }, [form]);

  const set = (k: string) => (v: unknown) => setForm((f) => ({ ...f, [k]: v }));
  const f = form ?? {};

  async function runCheck() {
    if (!draft) return;
    setBusy(true);
    setErr(null);
    try {
      setCheck(await api().checkProvider(draft.definition, key));
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    if (!draft) return;
    setBusy(true);
    setErr(null);
    try {
      await api().putProvider(draft.definition);
      const id = String(draft.definition.id);
      const got = key.trim() ? await api().putProviderKey(id, key) : await api().providers();
      onSaved(got.providers, id, model, text);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const left = draft?.problems ?? [];
  return (
    <div className="h3-col h3-mfile" style={{ gap: 6 }}>
      <div className="h3-row h3-small">
        <b className="h3-grow">Add a provider</b>
        <button className="h3-btn h3-icon" title="Close" onClick={onCancel}><i className="pi pi-times" /></button>
      </div>
      <div className="h3-small">
        <b>The request that starts a generation</b>{" "}
        <span className="h3-muted">its docs page's address, the example cURL from it, or its OpenAPI document (or that document's address). A key in it isn't kept.</span>
      </div>
      <textarea className="h3-in h3-mono" rows={7} spellCheck={false} value={text} style={{ fontSize: 11 }}
        placeholder={'curl -X POST https://api.example.com/v1/generate -H "Authorization: Bearer ..." -d \'{"model": "...", "prompt": "a cat"}\''}
        onChange={(e) => setText(e.target.value)} />
      <details className="h3-small">
        <summary style={{ cursor: "pointer" }}>More from the docs, if they show it <span className="h3-muted">each one fills in more below</span></summary>
        <div className="h3-col" style={{ gap: 4 }}>
          <label className="h3-col">Its example answer
            <textarea className="h3-in h3-mono" rows={4} spellCheck={false} value={answer} style={{ fontSize: 11 }} onChange={(e) => setAnswer(e.target.value)} />
          </label>
          <label className="h3-col">The cURL that checks on a job
            <textarea className="h3-in h3-mono" rows={2} spellCheck={false} value={poll} style={{ fontSize: 11 }} onChange={(e) => setPoll(e.target.value)} />
          </label>
          <label className="h3-col">That check's example answer, when finished
            <textarea className="h3-in h3-mono" rows={4} spellCheck={false} value={pollAnswer} style={{ fontSize: 11 }} onChange={(e) => setPollAnswer(e.target.value)} />
          </label>
        </div>
      </details>
      <button className="h3-btn h3-primary" style={{ alignSelf: "flex-start" }} disabled={busy || !text.trim()} onClick={() => void read()}>
        <i className={busy ? "pi pi-spin pi-spinner" : "pi pi-search"} /> Read it
      </button>
      {draft?.paths && !draft.model && !form?.url && (
        <label className="h3-row h3-small" style={{ gap: 4 }}>This document has several requests. Which starts a generation?
          <select className="h3-in" value={path} onChange={(e) => { setPath(e.target.value); if (e.target.value) void read(e.target.value); }}>
            <option value="">(choose)</option>
            {draft.paths.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </label>
      )}
      {err && <div className="h3-small h3-err">{err}</div>}
      {form && draft && (
        <>
          {(draft.notes ?? []).map((n) => <div key={n} className="h3-small h3-warn">{n}</div>)}
          <div className="h3-h">Who it is</div>
          <div className="h3-row h3-wrap" style={{ gap: 6 }}>
            <Field label="Name" value={f.label} mono={false} onChange={set("label")} />
            <Field label="id" value={f.id} onChange={set("id")} />
            <Field label="Address" hint="https://api.example.com/v1" value={f.base_url} wide onChange={set("base_url")} />
          </div>
          <div className="h3-h">Its key</div>
          <div className="h3-row h3-wrap h3-small" style={{ gap: 6 }}>
            <label className="h3-row" style={{ gap: 4 }}>Sent as
              <select className="h3-in" value={String(f.auth_type)} onChange={(e) => set("auth_type")(e.target.value)}>
                <option value="bearer">Authorization: Bearer</option>
                <option value="header">a header</option>
                <option value="query">part of the address</option>
              </select>
            </label>
            {f.auth_type !== "bearer" && <Field label="Named" hint="xi-api-key" value={f.auth_name} onChange={set("auth_name")} />}
            {f.auth_type === "header" && <Field label="Before the key" hint='"Key " for fal' value={f.auth_prefix} onChange={set("auth_prefix")} />}
          </div>
          <div className="h3-row h3-wrap h3-small" style={{ gap: 6 }}>
            <input className="h3-in h3-mono h3-grow" style={{ minWidth: 200 }} type="password" autoComplete="off" value={key}
              placeholder="its API key" onChange={(e) => setKey(e.target.value)} />
            <button className="h3-btn" disabled={busy || !key.trim() || !!left.length}
              title="One read that starts nothing and costs nothing: asking after a job that doesn't exist" onClick={() => void runCheck()}>
              <i className="pi pi-shield" /> Check it (free)
            </button>
          </div>
          {check && (
            <div className={`h3-small ${check.key_ok ? "" : "h3-err"}`}>
              {!check.reached ? "It couldn't be reached." : check.key_ok && check.proves_key === false
                ? `It answered (${check.status}), but this can't prove the key: its answers give the address that checks on a job, so there's none to ask yet. Paste the cURL that checks on a job under "More from the docs" for a check that does.`
                : check.key_ok
                ? `It answered (${check.status}), and didn't refuse the key. A 404 is what's expected here: the job asked after doesn't exist.`
                : `It refused that (${check.status}): usually the key, sometimes a firewall in front of it.`}
              <span className="h3-mono h3-muted"> {check.says}</span>
            </div>
          )}
          <div className="h3-h">The generate call</div>
          <div className="h3-row h3-wrap" style={{ gap: 6 }}>
            <Field label="Address" hint="/generate; {model} where the model's id goes" value={f.url} wide onChange={set("url")} />
            <Field label="Model id goes in" hint="the body's field; empty when it's in the address" value={f.model_field} onChange={set("model_field")} />
            <label className="h3-row h3-small" style={{ gap: 4 }}>Sent as
              <select className="h3-in" value={String(f.body)} onChange={(e) => set("body")(e.target.value)}>
                <option value="json">JSON</option><option value="multipart">a form (multipart)</option>
              </select>
            </label>
          </div>
          <div className="h3-h">How it answers</div>
          <select className="h3-in h3-small" style={{ alignSelf: "flex-start" }} value={String(f.answer)} onChange={(e) => set("answer")(e.target.value)}>
            <option value="job">It starts a job, and you check on it</option>
            <option value="links">It answers with links to the files</option>
            <option value="file">Its answer is the file itself</option>
          </select>
          {f.answer === "job" && (
            <div className="h3-row h3-wrap" style={{ gap: 6 }}>
              <Field label="Job's id is at" hint="data.id" value={f.id_path} onChange={set("id_path")} />
              <Field label="Check at" hint="/jobs/{task}" value={f.poll_url} onChange={set("poll_url")} />
              <Field label="Status is at" hint="data.status" value={f.status_path} onChange={set("status_path")} />
              <Field label="Done when" hint="completed, succeeded" value={f.done} onChange={set("done")} />
              <Field label="Failed when" hint="failed, error" value={f.failed} onChange={set("failed")} />
              <Field label="Error is at" hint="data.error" value={f.error_path} onChange={set("error_path")} />
              <Field label="Links are at" hint="data.outputs" value={f.files_path} onChange={set("files_path")} />
              <Field label="Then fetch" hint="only if the result is a further request" value={f.fetch_url} onChange={set("fetch_url")} />
            </div>
          )}
          {f.answer === "links" && <Field label="Links are at" hint="data.outputs" value={f.files_path} onChange={set("files_path")} />}
          <div className="h3-h">How pictures go in</div>
          <select className="h3-in h3-small" style={{ alignSelf: "flex-start" }} value={String(f.files_via)} onChange={(e) => set("files_via")(e.target.value)}>
            <option value="datauri">In the request, as a data: address</option>
            <option value="base64">In the request, as base64</option>
            <option value="upload">Uploaded first, then sent as a link</option>
            <option value="presigned">Sent to an address it gives, then as a link</option>
            <option value="multipart">As files in the form</option>
          </select>
          {f.files_via === "upload" && (
            <div className="h3-row h3-wrap" style={{ gap: 6 }}>
              <Field label="Upload to" hint="/uploads" value={f.upload_url} onChange={set("upload_url")} />
              <Field label="File's field" hint="file" value={f.upload_field} onChange={set("upload_field")} />
              <Field label="Link is at" hint="data.url" value={f.upload_link} onChange={set("upload_link")} />
            </div>
          )}
          {f.files_via === "presigned" && (
            <div className="h3-row h3-wrap" style={{ gap: 6 }}>
              <Field label="Ask at" hint="/files/generate-upload-url" value={f.upload_url} onChange={set("upload_url")} />
              <Field label="File's type goes in" hint="content_type" value={f.upload_type_field} onChange={set("upload_type_field")} />
              <Field label="Address is at" hint="upload_url" value={f.upload_put} onChange={set("upload_put")} />
              <Field label="Its headers are at" hint="upload_headers, if it gives any" value={f.upload_headers} onChange={set("upload_headers")} />
              <Field label="Link is at" hint="public_url" value={f.upload_link} onChange={set("upload_link")} />
            </div>
          )}
          <details className="h3-small">
            <summary style={{ cursor: "pointer" }}>The definition this comes to</summary>
            <pre className="h3-mono" style={{ fontSize: 11, maxHeight: 240, overflow: "auto", margin: "4px 0 0" }}>{JSON.stringify(draft.definition, null, 2)}</pre>
          </details>
          {left.map((p) => <div key={p} className="h3-small h3-warn">{p}</div>)}
          <div className="h3-row h3-small" style={{ gap: 6 }}>
            <span className="h3-muted h3-grow">Next: its first model, from the same request. Nothing is paid for until you probe one take.</span>
            <button className="h3-btn h3-primary" disabled={busy || !!left.length} onClick={() => void save()}>
              <i className="pi pi-save" /> Save provider, set up its model
            </button>
          </div>
        </>
      )}
    </div>
  );
}

/** The providers on this machine: a key for each (never shown again). Adding one is in the Models
 * window, where its first model follows. */
export function ProvidersCard() {
  const { rows, setRows, err, setErr } = useProviders();
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
      <div className="h3-small h3-muted">To add a provider: Models, then Add a model from another API.</div>
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
  const [addingProvider, setAddingProvider] = useState(false);
  const row = (rows ?? []).find((x) => x.id === service);
  const listed = row?.catalog ?? [];
  // a model on the provider's list needs nothing pasted
  const fromList = listed.find((m) => m.id === model.trim());

  async function read(which?: string) {
    setBusy(true);
    setErr(null);
    try {
      const got = await api().readProviderSpec({ service, model: model.trim(), kind, text: fromList ? "" : text, ...(which ?? path ? { path: which ?? path } : {}) });
      if (got.model && !model.trim()) setModel(got.model);
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
          <select className="h3-in" value={service} onChange={(e) => {
            if (e.target.value === "+") setAddingProvider(true);
            else setService(e.target.value);
          }}>
            <option value="">(choose)</option>
            {(rows ?? []).map((x) => <option key={x.id} value={x.id}>{x.label}{x.has_key ? "" : " (no key yet)"}</option>)}
            <option value="+">Add a provider…</option>
          </select>
        </label>
        {listed.length > 0 && (
          <label className="h3-row" style={{ gap: 4 }} title="Models whose docs have been read: nothing to paste">From its list
            <select className="h3-in" style={{ maxWidth: 240 }} value={fromList?.id ?? ""}
              onChange={(e) => {
                const m = listed.find((x) => x.id === e.target.value);
                setModel(m?.id ?? "");
                if (m) setKind(m.kind);
                setR(null);
              }}>
              <option value="">(another model)</option>
              {(["video", "image"] as const).map((k) => (
                <optgroup key={k} label={k === "video" ? "Video" : "Image"}>
                  {listed.filter((m) => m.kind === k).map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
                </optgroup>
              ))}
            </select>
          </label>
        )}
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
      {addingProvider && (
        <AddProvider onCancel={() => setAddingProvider(false)} onSaved={(saved, pid, m, reference) => {
          setRows(saved);
          setService(pid);
          setModel(m);
          setText(reference);
          setR(null);
          setAddingProvider(false);
        }} />
      )}
      {listErr && <div className="h3-small h3-err">{listErr}</div>}
      {row && !row.has_key && <ProviderKey row={row} onChanged={setRows} onError={setListErr} />}
      {row?.untested && (
        <div className="h3-small h3-warn">{row.label}'s definition was written from its docs and hasn't been proved by a real render yet.</div>
      )}
      {fromList?.note && <div className="h3-small h3-muted">{fromList.note}</div>}
      {fromList ? (
        <div className="h3-small h3-muted">This one's fields come from {row?.label}'s docs, so there's nothing to paste.</div>
      ) : (
        <>
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
        </>
      )}
      {r && !r.proposal && (
        <label className="h3-row h3-small" style={{ gap: 4 }}>This document has several requests. Which makes the {kind}?
          <select className="h3-in" value={path} onChange={(e) => { setPath(e.target.value); if (e.target.value) void read(e.target.value); }}>
            <option value="">(choose)</option>
            {r.paths.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </label>
      )}
      <button className="h3-btn h3-primary" style={{ alignSelf: "flex-start" }} disabled={busy || !service || (!model.trim() && !/^https?:\/\/\S+$/.test(text.trim())) || (!fromList && !text.trim())}
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
          {kind === "video" && (
            <details className="h3-small">
              <summary style={{ cursor: "pointer" }}>Different model ids by what's sent <span className="h3-muted">a provider can split one model into several</span></summary>
              <div className="h3-lora">
                {(["frames", "references", "text"] as const).map((m) => (
                  <label key={m} className="h3-row" style={{ gap: 4 }}>
                    <span style={{ minWidth: 110 }}>{m === "frames" ? "With a first frame" : m === "references" ? "With reference pictures" : "Words alone"}</span>
                    <input className="h3-in h3-mono h3-grow" spellCheck={false} placeholder="the model id above"
                      value={((draft as { api?: { models?: Record<string, string> } }).api?.models ?? {})[m] ?? ""}
                      onChange={(e) => setJson((was) => {
                        const spec = JSON.parse(was) as { api?: { models?: Record<string, string> } };
                        const ids = { ...spec.api?.models, [m]: e.target.value.trim() };
                        if (!ids[m]) delete ids[m];
                        return JSON.stringify({ ...spec, api: { ...spec.api, models: ids } }, null, 2);
                      })} />
                  </label>
                ))}
              </div>
            </details>
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
