// A provider's speakers: heard from its own previews, for free, one at a time, and read only when
// this is opened. A list marked free plays with no key, so someone can hear them before signing up.

import { useEffect, useRef, useState } from "react";
import type { ProviderRow, ProviderVoice } from "../api";
import { api } from "../host";

/** Lists already read this session: a show can have dozens of characters choosing from one list. */
const READ = new Map<string, { voices: ProviderVoice[]; next: string }>();

/** What a voice is, in a few words: who and from where, as a person would say it. */
function about(v: ProviderVoice): string {
  const words = ["gender", "age", "accent", "descriptive"].map((k) => v.labels[k]).filter(Boolean);
  return (words.length ? words : Object.values(v.labels)).map((w) => w.replace(/_/g, " ")).join(", ") || v.category;
}

/** The one player, so starting a voice stops the last. */
function usePlayer() {
  const audio = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState<string | null>(null);
  useEffect(() => () => audio.current?.pause(), []);
  function toggle(url: string) {
    audio.current?.pause();
    if (playing === url) {
      setPlaying(null);
      return;
    }
    const a = new Audio(url);
    a.onended = () => setPlaying(null);
    a.onerror = () => setPlaying(null);
    audio.current = a;
    setPlaying(url);
    void a.play().catch(() => setPlaying(null));
  }
  return { playing, toggle };
}

/** Play or stop one provider preview. */
export function PreviewButton({ url, playing, onToggle, name }: { url: string; playing: boolean; onToggle: () => void; name: string }) {
  return (
    <button className="h3-btn h3-icon" type="button" disabled={!url} title={url ? `${playing ? "Stop" : "Hear"} ${name}` : "It has no preview"}
      aria-label={`${playing ? "Stop" : "Hear"} ${name}`} onClick={onToggle}>
      <i className={`pi ${playing ? "pi-stop" : "pi-play"}`} />
    </button>
  );
}

/** A speaker already picked, to hear again without opening the list. */
export function HearSpeaker({ url, name }: { url: string; name: string }) {
  const { playing, toggle } = usePlayer();
  return <PreviewButton url={url} name={name} playing={playing === url} onToggle={() => toggle(url)} />;
}

export function ProviderVoices({ service, picked, busy: picking, onPick }: {
  service: string;
  picked?: string;
  busy?: boolean;
  /** choosing for a character; without it, this is only for listening */
  onPick?: (id: string, name: string, preview: string) => void;
}) {
  const [row, setRow] = useState<ProviderRow | null>(null);
  const [which, setWhich] = useState("");
  const [search, setSearch] = useState("");
  const [voices, setVoices] = useState<ProviderVoice[] | null>(null);
  const [next, setNext] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [typed, setTyped] = useState("");
  const { playing, toggle } = usePlayer();

  async function read(list: string, words: string, after = "") {
    const key = `${service}|${list}`;
    const plain = !words.trim() && !after;
    const had = plain ? READ.get(key) : undefined;
    if (had) {
      setVoices(had.voices);
      setNext(had.next);
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const got = await api().providerVoices({ service, list, search: words.trim() || undefined, after: after || undefined });
      if (plain) READ.set(key, got);
      setVoices((was) => (after ? [...(was ?? []), ...got.voices] : got.voices));
      setNext(got.next);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    let live = true;
    api().providers().then((d) => {
      if (!live) return;
      const mine = d.providers.find((x) => x.id === service) ?? null;
      setRow(mine);
      const first = mine?.voices?.lists.find((x) => x.free || mine.has_key) ?? mine?.voices?.lists[0];
      if (first) {
        setWhich(first.id);
        void read(first.id, "");
      }
    }).catch((e: Error) => { if (live) setErr(e.message); });
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- read when opened, once per provider
  }, [service]);

  const lists = row?.voices?.lists ?? [];
  const list = lists.find((x) => x.id === which);
  const hasKey = !!row?.has_key;
  // with no key, a free list has no search of its own: looked through here
  const local = !hasKey || !list?.searches;
  const words = search.trim().toLowerCase();
  const shown = local && words
    ? (voices ?? []).filter((v) => `${v.name} ${Object.values(v.labels).join(" ")}`.toLowerCase().includes(words))
    : voices;

  return (
    <div className="h3-col" style={{ gap: 4 }}>
      <div className="h3-row h3-wrap" style={{ gap: 4 }}>
        {lists.length > 1 && (
          <select className="h3-in h3-small" value={which} onChange={(e) => {
            setWhich(e.target.value);
            setVoices(null);
            void read(e.target.value, local ? "" : search);
          }}>
            {lists.map((x) => <option key={x.id} value={x.id} disabled={!x.free && !hasKey}>{x.label}{!x.free && !hasKey ? " (needs its key)" : ""}</option>)}
          </select>
        )}
        <input className="h3-in h3-grow" placeholder="search these voices" value={search} onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !local) void read(which, search); }} />
        {!local && <button className="h3-btn" disabled={busy} onClick={() => void read(which, search)}>Search</button>}
      </div>
      {!hasKey && row && (
        <span className="h3-small h3-muted">
          These play with no key. To generate with one{row.voices?.browse ? " or hear its whole library" : ""}, you'll need{" "}
          {row.key_url ? <a className="h3-link" href={row.key_url} target="_blank" rel="noreferrer">a key from {row.label}</a> : `a key from ${row.label}`}
          {row.voices?.browse ? <>, or <a className="h3-link" href={row.voices.browse} target="_blank" rel="noreferrer">browse its library</a> on its site</> : ""}.
        </span>
      )}
      {err && <span className="h3-small h3-err">{err}</span>}
      {busy && !voices && <span className="h3-small h3-muted">Reading its voices…</span>}
      {shown?.length === 0 && <span className="h3-small h3-muted">No voices found.</span>}
      <div className="h3-col" style={{ gap: 2, maxHeight: 280, overflow: "auto" }}>
        {shown?.map((v) => {
          const [name, ...more] = v.name.split(" - ");
          return (
            <div key={v.id} className="h3-row h3-small" style={{ gap: 6 }} title={[v.about, v.id].filter(Boolean).join("\n")}>
              <PreviewButton url={v.preview} name={name} playing={playing === v.preview && !!v.preview} onToggle={() => toggle(v.preview)} />
              <span className="h3-col h3-grow" style={{ gap: 0, minWidth: 0 }}>
                <span className="h3-ell"><b>{name}</b>{more.length ? <span className="h3-muted"> · {more.join(" - ")}</span> : null}</span>
                <span className="h3-muted h3-ell">{about(v)}</span>
              </span>
              {onPick && <button className="h3-btn" disabled={picking || picked === v.id} onClick={() => onPick(v.id, name, v.preview)}>{picked === v.id ? "Picked" : "Pick"}</button>}
            </div>
          );
        })}
      </div>
      {next && !local && <button className="h3-link" style={{ alignSelf: "flex-start" }} disabled={busy} onClick={() => void read(which, search, next)}>more…</button>}
      {onPick && (
        <details className="h3-small">
          <summary style={{ cursor: "pointer" }} className="h3-muted">Use a voice from its site, by its id</summary>
          <div className="h3-row" style={{ gap: 4, marginTop: 4 }}>
            <input className="h3-in h3-mono h3-grow" spellCheck={false} placeholder="its voice id" value={typed} onChange={(e) => setTyped(e.target.value)} />
            <button className="h3-btn" disabled={picking || !typed.trim()} onClick={() => onPick(typed.trim(), typed.trim(), "")}>Use it</button>
          </div>
        </details>
      )}
    </div>
  );
}
