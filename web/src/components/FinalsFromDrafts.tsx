// Finals from drafts: the Seedance drafts the proxy cut uses (GET
// /seriesmith/drafts), each with its thumbnail; the ones whose shot has no
// final yet start ticked. Each ticked one becomes a paid 1080p render of that
// draft exactly as drawn (POST /seriesmith/render with from_draft), so the
// list is there to leave some out.

import { useEffect, useState } from "react";
import { makeFinalsFromDrafts, openDrafts } from "../actions";
import type { DraftItem } from "../api";
import { api } from "../host";
import { tn } from "../lib/format";
import { useApp } from "../store";
import { FloatingWindow } from "./FloatingWindow";

export function FinalsFromDraftsWindow() {
  const open = useApp((s) => s.draftsOpen);
  const ep = useApp((s) => s.ep);
  if (!open || !ep) return null;
  return <FinalsFromDrafts ep={ep} />;
}

/** "in 5 days", "in 20 hours", "expired" */
function left(expires: string, expired: boolean): string {
  if (expired) return "expired";
  const h = (new Date(expires).getTime() - Date.now()) / 3600000;
  if (!Number.isFinite(h)) return "";
  return h >= 48 ? `${Math.floor(h / 24)} days left` : `${Math.max(1, Math.floor(h))} hours left`;
}

function FinalsFromDrafts({ ep }: { ep: string }) {
  const [items, setItems] = useState<DraftItem[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [on, setOn] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api().drafts(ep).then((r) => {
      setItems(r.drafts);
      // the shots with no final yet start ticked; an expired draft can't be made
      setOn(Object.fromEntries(r.drafts.map((d) => [d.shot, !d.expired && d.finals === 0])));
    }).catch((e) => setErr((e as Error).message));
  }, [ep]);
  const picked = (items ?? []).filter((d) => on[d.shot] && !d.expired);

  async function go() {
    if (!picked.length) return;
    setBusy(true);
    const ok = await makeFinalsFromDrafts(Object.fromEntries(picked.map((d) => [d.shot, d.take])));
    setBusy(false);
    if (ok) openDrafts(false);
  }

  const head = (
    <>
      <i className="pi pi-forward" />
      <b className="h3-grow">Finals from drafts</b>
      <button className="h3-btn h3-icon" title="Close" onClick={() => openDrafts(false)}><i className="pi pi-times" /></button>
    </>
  );
  return (
    <FloatingWindow storageKey="seriesmith.drafts.rect" head={head} minW={380} minH={260}
      defaultRect={() => ({ x: Math.max(16, Math.round((window.innerWidth - 560) / 2)), y: 80, w: 560, h: Math.min(640, window.innerHeight - 120) })}>
      <div className="h3-col" style={{ padding: 10, gap: 8, overflow: "auto", height: "100%" }}>
        <span className="h3-small h3-muted">
          Each ticked draft becomes its shot's final: Seedance renders that draft again at 1080p, exactly as drawn (its
          prompt, pictures, seed and sound). Each one is a paid render. The shots with no final yet start ticked.
        </span>
        {err && <span className="h3-small h3-err">{err}</span>}
        {items === null && !err && <span className="h3-small h3-muted"><i className="pi pi-spin pi-spinner" /> Looking for drafts…</span>}
        {items && !items.length && (
          <span className="h3-small h3-muted">The proxy cut uses no Seedance drafts: render the shots on Seedance in proxy first.</span>
        )}
        {items && items.length > 0 && (
          <div className="h3-row h3-small" style={{ gap: 8 }}>
            <button className="h3-link" onClick={() => setOn(Object.fromEntries(items.map((d) => [d.shot, !d.expired])))}>all</button>
            <button className="h3-link" onClick={() => setOn({})}>none</button>
            <button className="h3-link" onClick={() => setOn(Object.fromEntries(items.map((d) => [d.shot, !d.expired && d.finals === 0])))}>no final yet</button>
          </div>
        )}
        {(items ?? []).map((d) => (
          <label key={d.shot} className="h3-row" style={{ gap: 8, alignItems: "center", opacity: d.expired ? 0.5 : 1, cursor: d.expired ? "default" : "pointer" }}
            title={d.expired ? "Its draft has expired (they last 7 days): render the shot's final instead" : `${d.shot} proxy ${tn(d.take)}`}>
            <input type="checkbox" disabled={d.expired} checked={!!on[d.shot] && !d.expired}
              onChange={(e) => setOn({ ...on, [d.shot]: e.target.checked })} />
            {d.thumb
              ? <img src={api().fileUrl(ep, d.thumb)} alt="" style={{ width: 128, height: 72, objectFit: "cover", borderRadius: 3, background: "#000" }} />
              : <span style={{ width: 128, height: 72, background: "#000", borderRadius: 3 }} />}
            <span className="h3-col" style={{ gap: 2 }}>
              <b>{d.shot} <span className="h3-muted">draft {tn(d.take)}</span></b>
              <span className="h3-small h3-muted">
                {d.made_from_it.length
                  ? `its final is ${d.made_from_it.map(tn).join(", ")}`
                  : d.finals ? `${d.finals} final take${d.finals > 1 ? "s" : ""} already (not from this draft)` : "no final yet"}
                {" · "}{left(d.expires, d.expired)}
              </span>
            </span>
          </label>
        ))}
      </div>
      <div className="h3-row" style={{ padding: "6px 10px", borderTop: "1px solid var(--h3-border)" }}>
        <span className="h3-small h3-muted h3-grow">{picked.length} of {(items ?? []).length} ticked · 1080p · paid</span>
        <button className="h3-btn" onClick={() => openDrafts(false)}>Cancel</button>
        <button className="h3-btn h3-primary" disabled={!picked.length || busy} onClick={() => void go()}>
          {busy ? <i className="pi pi-spin pi-spinner" /> : <i className="pi pi-forward" />} Make {picked.length} final{picked.length === 1 ? "" : "s"}
        </button>
      </div>
    </FloatingWindow>
  );
}
