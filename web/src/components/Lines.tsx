// An episode's lines from a voice model (seriesmith/lines.py): what a generate would make, in
// characters, before anything is paid for; a take per line, each to hear and redo; then laid into
// the episode's recording, which the panel below aligns as it would an actor's.

import { useCallback, useEffect, useRef, useState } from "react";
import type { LineRow, LinesPlan } from "../api";
import { api } from "../host";
import { refreshEpisode } from "../actions";
import { HearSpeaker } from "./ProviderVoices";

export function LinesSection({ ep }: { ep: string }) {
  const [open, setOpen] = useState(false);
  const [plan, setPlan] = useState<LinesPlan | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [laid, setLaid] = useState<string | null>(null);
  const live = useRef(true);
  useEffect(() => { live.current = true; return () => { live.current = false; }; }, []);

  const read = useCallback(async () => {
    try {
      const got = await api().lines(ep);
      // whatever the server left out (one older than this page says only why it can't): an empty list
      if (live.current) {
        setPlan({ ...got, lines: got.lines ?? [], characters: got.characters ?? [], no_speaker: got.no_speaker ?? [],
                  to_make: got.to_make ?? { lines: 0, chars: 0 } });
        setErr(null);
      }
    } catch (e) {
      if (live.current) setErr((e as Error).message);
    }
  }, [ep]);

  // read when it's opened, and again while takes are out
  useEffect(() => { if (open) void read(); }, [open, read]);
  const out = !!plan?.lines?.some((l) => l.takes.some((t) => t.status === "running"))
    || !!plan?.characters?.some((c) => c.source?.status === "running");
  useEffect(() => {
    if (!open || !out) return;
    const timer = setInterval(() => void read(), 3000);
    return () => clearInterval(timer);
  }, [open, out, read]);

  async function make(ids: string[] | null, chars: number) {
    setBusy(true);
    setErr(null);
    try {
      const got = await api().generateLines({ ep, confirm_chars: chars, ...(ids ? { lines: ids } : {}) });
      if (got.errors.length) setErr(got.errors.map((e) => `${e.line}: ${e.error}`).join("\n"));
      await read();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function lay() {
    setBusy(true);
    setErr(null);
    setLaid(null);
    try {
      const got = await api().layLines(ep);
      setLaid(`Laid ${got.lines} lines into ${got.path} (${got.seconds.toFixed(1)} s).${got.notes.length ? ` ${got.notes.join(" ")}` : ""} Now align it below.`);
      await refreshEpisode(ep);
      await read();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function bring(who: string, file: File) {
    setBusy(true);
    setErr(null);
    try {
      await api().characterLines(ep, who, file);
      await read();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function pick(l: LineRow, take: number) {
    try {
      await api().pickLine(ep, l.id, take);
      await read();
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  return (
    <details onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary className="h3-h" style={{ cursor: "pointer" }}>Or build it from each character's lines</summary>
      <div className="h3-col" style={{ gap: 6, marginTop: 6 }}>
        {err && <div className="h3-note h3-note-err h3-small" style={{ whiteSpace: "pre-wrap" }}>{err}</div>}
        {!plan && !err && <span className="h3-small h3-muted">Reading the script…</span>}
        {plan && (
          <>
            <div className="h3-small h3-muted">
              {plan.available ? `Make lines with ${plan.label}, or b` : "B"}ring a file of one character's lines, from an actor or a voice model's site: each is cut into a take per line, so one can be redone alone.
              {plan.available ? "" : ` ${plan.why}`}
            </div>
            <div className="h3-col" style={{ gap: 2 }}>
              {plan.characters.map((c) => (
                <div key={c.who} className="h3-row h3-small" style={{ gap: 6 }}>
                  <b className="h3-ell" style={{ minWidth: 120 }}>{c.name}</b>
                  {c.speaker ? <span>{c.speaker.name || c.speaker.id}</span> : <span className="h3-warn">no speaker yet</span>}
                  {c.speaker?.preview && <HearSpeaker url={c.speaker.preview} name={c.speaker.name || c.speaker.id} />}
                  <span className="h3-grow" />
                  {c.source?.status === "running" && <span className="h3-muted"><i className="pi pi-spin pi-spinner" /> hearing {c.source.name}…</span>}
                  {c.source?.status === "failed" && <span className="h3-err h3-ell" title={c.source.error}>{c.source.error}</span>}
                  {c.source?.status === "ok" && <span className={c.source.unheard?.length ? "h3-warn" : "h3-muted"} title={(c.source.notes ?? []).join("\n")}>{c.source.cut} of {c.source.lines} from its file</span>}
                  <span className="h3-muted">{c.lines} {c.lines === 1 ? "line" : "lines"}, {c.chars.toLocaleString()} characters</span>
                  <label className="h3-btn" title={`A file with all of ${c.name}'s lines in script order, one voice, nobody else in it. Costs nothing`} style={{ cursor: "pointer" }}>
                    Use a file…
                    <input type="file" accept="audio/*,.wav,.mp3,.flac,.ogg,.m4a,.aac,.opus" style={{ display: "none" }} disabled={busy}
                      onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void bring(c.who, f); }} />
                  </label>
                </div>
              ))}
            </div>
            {plan.available && plan.no_speaker.length > 0 && (
              <div className="h3-note h3-small">Pick a speaker for {plan.no_speaker.join(", ")} on the Refs tab's voice rows first: no line is made in a voice nobody chose.</div>
            )}
            <div className="h3-row h3-wrap" style={{ gap: 6 }}>
              {plan.available && <button className="h3-btn h3-paid" disabled={busy || !plan.to_make.lines || plan.no_speaker.length > 0}
                title={`Sends ${plan.to_make.lines} requests to ${plan.service}, billed to your account by the character`}
                onClick={() => void make(null, plan.to_make.chars)}>
                <i className="pi pi-sparkles" /> {plan.to_make.lines
                  ? `Generate ${plan.to_make.lines} ${plan.to_make.lines === 1 ? "line" : "lines"} (paid: ${plan.to_make.chars.toLocaleString()} characters)`
                  : "Every line has a take"}
              </button>}
              <button className="h3-btn" disabled={busy || !plan.can_lay || out} title="Costs nothing: joins the takes picked, with the script's pauses" onClick={() => void lay()}>
                <i className="pi pi-align-justify" /> Lay them into the recording
              </button>
            </div>
            {laid && <div className="h3-note h3-note-info h3-small">{laid}</div>}
            <div className="h3-col" style={{ gap: 3, maxHeight: 320, overflow: "auto" }}>
              {plan.lines.map((l) => {
                const take = l.takes.find((t) => t.take === l.picked);
                const running = l.takes.some((t) => t.status === "running");
                const failed = !take && [...l.takes].reverse().find((t) => t.status === "failed");
                const done = l.takes.filter((t) => t.status === "ok");
                return (
                  <div key={l.id} className="h3-row h3-small" style={{ gap: 6 }} title={failed ? failed.error : l.id}>
                    <span className="h3-mono h3-muted">{l.id}</span>
                    <span className="h3-col h3-grow" style={{ gap: 0, minWidth: 0 }}>
                      <span className="h3-ell"><b>{l.name}:</b> {l.text}</span>
                      {failed && <span className="h3-err h3-ell">{failed.error}</span>}
                      {l.status === "changed" && <span className="h3-warn">its words or speaker changed since this take</span>}
                    </span>
                    {running && <i className="pi pi-spin pi-spinner" title="Being made" />}
                    {done.length > 1 && (
                      <select className="h3-in" value={l.picked ?? ""} onChange={(e) => void pick(l, Number(e.target.value))}>
                        {done.map((t) => <option key={t.take} value={t.take}>t{String(t.take).padStart(2, "0")}</option>)}
                      </select>
                    )}
                    {take?.file && <audio controls preload="none" src={api().refFileUrl(ep, take.file, String(take.take))} style={{ height: 26, width: 150 }} />}
                    {take?.source === "file" && <span className="h3-muted" title={take.voice_name}>file</span>}
                    {plan.available && <button className="h3-btn" disabled={busy || running || !l.speaker}
                      title={`${take ? "Redo" : "Make"} this line (paid: ${l.chars} characters)`}
                      onClick={() => void make([l.id], l.chars)}>{take ? "Redo" : "Make"}</button>}
                  </div>
                );
              })}
            </div>
          </>
        )}
      </div>
    </details>
  );
}
