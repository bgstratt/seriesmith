// The Refs tab's sound beyond the voices (docs/SOUND.md): Music (the episode's cues),
// Effects (the files on that lane of this pass's mix) and Ambience: each place's
// ambience bed (an `ambience:<place>` ref, made from its location's `ambience` words
// and laid under its shots by the mix), then the files on the ambience lane. Voices
// and dub tracks stay where they are, for the dialogue. Cues and files aren't refs,
// but they are what the episode's sound is made from, so they are listed beside them.

import { useEffect, useRef, useState } from "react";
import { generateRef, pickRef } from "../actions";
import { loadCues, openCue } from "../cueActions";
import { api } from "../host";
import { cueTitle } from "../lib/cue";
import { tn } from "../lib/format";
import { currentMix, deleteMixItem, loadMix, setMixBed, toggleSound } from "../mixActions";
import { store, useApp } from "../store";
import type { AmbienceBed, MixItem, Ref } from "../types";
import { useTargets } from "./Targets";
import { VoiceCandidate, VoiceLive } from "./VoiceRef";

/** One folding section, as the Refs tab's groups fold. */
function Section({ label, count, title, note, children }: {
  label: string; count: number; title: string; note?: string; children: React.ReactNode;
}) {
  const [folded, setFolded] = useState(false);
  return (
    <div className="h3-seq">
      <div className="h3-seq-head" onClick={() => setFolded((f) => !f)} title={title}>
        <span className="h3-chev">{folded ? "▶" : "▼"}</span>
        <b>{label}</b>
        <span className="h3-muted h3-small">{count}</span>
      </div>
      {!folded && (
        <>
          {children}
          {note && <div className="h3-muted h3-small h3-pad">{note}</div>}
        </>
      )}
    </div>
  );
}

function ItemRows({ items, empty }: { items: MixItem[]; empty: string }) {
  if (!items.length) return <div className="h3-muted h3-small h3-pad">{empty}</div>;
  return (
    <>
      {items.map((it) => (
        <div key={it.id} className="h3-kf-shot">
          <div className="h3-row h3-small" style={{ gap: 8 }}>
            <i className={it.loop ? "pi pi-replay" : "pi pi-volume-up"} title={it.loop ? "looped" : undefined} />
            <b>{it.label || it.id}</b>
            <span className="h3-muted" title={it.path}>{it.path.split("/").pop()}</span>
            <span className="h3-grow" />
            <span className="h3-muted" title="Where it starts: it moves with the shot">
              {it.in.shot} frame {it.in.frame}{it.out ? ` → ${it.out.shot} frame ${it.out.frame}` : ""}
            </span>
            {!!it.gain_db && <span className="h3-badge">{it.gain_db > 0 ? "+" : ""}{it.gain_db} dB</span>}
            <button className="h3-btn" title="Show it on the timeline's sound lanes" onClick={() => toggleSound(true)}>
              <i className="pi pi-wave-pulse" />
            </button>
            <button className="h3-btn" title={`Take ${it.label || it.id} out of the mix (the file stays in the episode)`}
              onClick={() => void deleteMixItem(it.id)}>
              <i className="pi pi-trash" />
            </button>
          </div>
        </div>
      ))}
    </>
  );
}

/** The places' beds (GET /seriesmith/ambience), fetched with the section and again when the
 * refs reload (a take landed, a pick); each row's takes when it opens (GET /seriesmith/refs/one). */
function useBeds(ep: string): { beds: AmbienceBed[] | null; error: string | null } {
  const refsSeen = useApp((s) => s.refs[ep]);
  const [state, setState] = useState<{ beds: AmbienceBed[] | null; error: string | null }>({ beds: null, error: null });
  useEffect(() => {
    let live = true;
    const call = api().ambience;
    if (!call) {
      setState({ beds: [], error: null });
      return;
    }
    call(ep).then((r) => live && setState({ beds: r.beds, error: null }))
      .catch((e) => live && setState((s) => ({ beds: s.beds, error: String((e as Error)?.message ?? e) })));
    return () => {
      live = false;
    };
  }, [ep, refsSeen]);
  return state;
}

/** One place's bed: its words, its file, and (open) its takes to play, pick and render again. */
function BedRow({ ep, bed }: { ep: string; bed: AmbienceBed }) {
  const open = useApp((s) => !!s.refOpen[bed.ref]);
  const focus = useApp((s) => (s.refFocus?.id === bed.ref ? s.refFocus.n : 0));
  const refsSeen = useApp((s) => s.refs[ep]);
  const mix = useApp((s) => currentMix(s));
  const busy = useApp((s) => !!s.busy[`refgen|${bed.ref}`] || !!s.busy[`refpick|${bed.ref}`]);
  const { list } = useTargets();
  const models = (list?.targets ?? []).filter((t) => t.kind === "ambience");
  const [target, setTarget] = useState<string>("");
  const [full, setFull] = useState<Ref | null>(null);
  const row = useRef<HTMLDivElement>(null);
  // fetched when it opens, and again when the refs reload while it's open
  useEffect(() => {
    if (!open) return;
    let live = true;
    void api().refsOne?.(ep, bed.ref).then((r) => live && setFull(r)).catch(() => live && setFull(null));
    return () => {
      live = false;
    };
  }, [ep, bed.ref, open, refsSeen, bed.takes, bed.picked]);
  useEffect(() => {
    if (!focus || !row.current) return;
    row.current.scrollIntoView({ block: "nearest" });
    row.current.classList.add("h3-flash");
    const t = setTimeout(() => row.current?.classList.remove("h3-flash"), 1200);
    return () => clearTimeout(t);
  }, [focus]);
  const toggle = () => store.set((s) => ({ refOpen: { ...s.refOpen, [bed.ref]: !open } }));
  const own = mix?.mix.beds?.[bed.place];
  const takes = (full?.takes ?? []).slice().sort((a, b) => b.take - a.take);
  const make = () => void generateRef({
    ref: bed.ref, view: null, count: 1, seed_mode: "auto", seed: null, prompt: null, model: null, loras: null, steps: null,
    note: "", ...(target ? { target } : {}),
  });
  return (
    <div ref={row} className="h3-kf-shot" data-ref={bed.ref}>
      <div className="h3-row h3-small" style={{ gap: 8, cursor: "pointer" }} onClick={toggle}
        title={`${bed.name}'s ambience bed (${bed.ref}): played under every shot set there (${bed.locations.join(", ")}). Click: its takes`}>
        <span className="h3-chev">{open ? "▼" : "▶"}</span>
        <i className="pi pi-cloud" />
        <b>{bed.name}</b>
        {bed.locations.length > 1 && <span className="h3-muted" title="The locations whose shots play over it (a place and its angles and relit versions)">+{bed.locations.length - 1} view{bed.locations.length > 2 ? "s" : ""}</span>}
        <span className="h3-grow" />
        <span className="h3-muted" title="The shots of this episode it plays under">{bed.used_by.length} shot{bed.used_by.length === 1 ? "" : "s"}</span>
        {bed.queued > 0 && <span className="h3-badge" title="Takes on their way"><i className="pi pi-spin pi-spinner" /> {bed.queued}</span>}
        <span className={bed.ok ? "" : "h3-muted"}>{bed.ok}/{bed.takes} take{bed.takes === 1 ? "" : "s"}</span>
        {bed.exists
          ? <span className="h3-badge h3-b-voice" title={`${bed.path}${bed.picked ? ` (${tn(bed.picked)})` : ""}`}>made{bed.picked ? ` ${tn(bed.picked)}` : ""}</span>
          : <span className="h3-badge" title={`${bed.path ?? ""} isn't there yet: its shots have no bed`}>not made</span>}
        {!!own?.gain_db && <span className="h3-badge" title="Its level in this pass's mix">{own.gain_db > 0 ? "+" : ""}{own.gain_db} dB</span>}
        {own?.mute && <span className="h3-badge" title="Muted in this pass's mix">muted</span>}
      </div>
      <div className="h3-small h3-muted h3-pad" style={{ paddingTop: 0 }} title="Its location's `ambience` in the series config (edit it in the location's form)">
        {bed.words ? `“${bed.words}”` : "No words: a file you supply (import it as a take)."}
      </div>
      {open && (
        <div className="h3-col h3-pad" style={{ gap: 6 }}>
          {full && <VoiceLive ep={ep} r={full} />}
          <div className="h3-row h3-small" style={{ gap: 6 }}>
            <button className="h3-btn h3-primary" disabled={busy || !bed.can_generate} onClick={make}
              title={bed.can_generate ? "A new take of this place's bed from its words (No music, no voices, no speech.), finished as it lands: its ends off, at the bed level. The first is picked when there's no bed yet."
                : bed.why_not ?? "It can't be made here"}>
              <i className={busy ? "pi pi-spin pi-spinner" : "pi pi-sparkles"} /> {bed.takes ? "Render again" : "Make it"}
            </button>
            {models.length > 1 && (
              <select className="h3-in" style={{ width: "auto" }} value={target} onChange={(e) => setTarget(e.target.value)}
                title="The model this take is made on (empty: the episode's)">
                <option value="">{bed.target ? `${models.find((m) => m.id === bed.target)?.short ?? bed.target} (default)` : "default model"}</option>
                {models.filter((m) => m.id !== bed.target).map((m) => <option key={m.id} value={m.id}>{m.short ?? m.label}</option>)}
              </select>
            )}
            <span className="h3-grow" />
            <button className="h3-btn" disabled={!mix} title={own?.mute ? "Hear this place's bed again in this pass's mix" : "Silence this place's bed in this pass's mix"}
              onClick={() => void setMixBed(bed.place, { mute: !own?.mute })}>
              <i className={own?.mute ? "pi pi-volume-up" : "pi pi-volume-off"} /> {own?.mute ? "Unmute" : "Mute"}
            </button>
            <button className="h3-btn" title="Show it on the timeline's sound lanes (the Ambience lane)" onClick={() => toggleSound(true)}>
              <i className="pi pi-wave-pulse" />
            </button>
          </div>
          {!bed.can_generate && bed.why_not && <div className="h3-note h3-small">{bed.why_not}</div>}
          {!full && <div className="h3-muted h3-small">Loading its takes…</div>}
          {full && !takes.length && <div className="h3-muted h3-small">No takes yet.</div>}
          {full && takes.map((t) => (
            <VoiceCandidate key={t.take} ep={ep} r={full} t={t} live={full.picked === t.take} selected={false}
              onClick={() => {
                if (t.status === "ok" && full.picked !== t.take) void pickRef(bed.ref, null, t.take);
              }} />
          ))}
          {full && takes.some((t) => t.status === "ok") && <div className="h3-muted h3-small">Click a take to make it the bed.</div>}
        </div>
      )}
    </div>
  );
}

export function SoundRefsSections({ ep }: { ep: string }) {
  const pass = useApp((s) => s.pass);
  const cues = useApp((s) => s.cues[ep]);
  const mix = useApp((s) => currentMix(s));
  // fetched when the tab shows them, then on the events that refresh the mix
  useEffect(() => {
    void loadCues(ep);
    if (!currentMix()) void loadMix(ep, pass);
  }, [ep, pass]);
  const items = mix?.mix.items ?? [];
  const { beds, error: bedsError } = useBeds(ep);
  const on = (t: string) => items.filter((x) => x.track === t);
  return (
    <>
      <Section label="Music" count={cues?.length ?? 0}
        title="The episode's music cues: each written to the hits in its span, its takes ranked in the cue window"
        note="A new cue: right-click a shot (Sound ▸ New music cue) or the music lane under the timeline.">
        {(cues ?? []).map((c) => (
          <div key={c.spec.id} className="h3-kf-shot">
            <div className="h3-row h3-small" style={{ gap: 8, cursor: "pointer" }} onClick={() => openCue(c.spec.id)}
              title="Open it in the cue window: its sections, arc and takes">
              <i className="pi pi-volume-up" />
              <b>{cueTitle(c.spec)}</b>
              <span className="h3-muted">{c.spec.in.shot} → {c.spec.out.shot}</span>
              <span className="h3-grow" />
              <span className={c.ok ? "" : "h3-muted"}>{c.ok}/{c.takes} take{c.takes === 1 ? "" : "s"}</span>
              {c.placed.includes(pass)
                ? <span className="h3-badge h3-b-voice" title={`In the ${pass} pass's mix`}>in the mix</span>
                : <span className="h3-badge" title={`Not in the ${pass} pass's mix yet: pick a take in the cue window`}>not placed</span>}
              <button className="h3-btn" onClick={(e) => { e.stopPropagation(); openCue(c.spec.id); }}>Open</button>
            </div>
          </div>
        ))}
      </Section>
      <Section label="Effects" count={on("effects").length}
        title="Sound effects on the effects lane of this pass's mix"
        note="Coming: a shot's effects made from its take by a foley model (docs/SOUND.md phase 4). For now: a file (right-click a shot: Sound ▸ Add an effect, or drop one on the lane).">
        <ItemRows items={on("effects")} empty="None on the effects lane." />
      </Section>
      <Section label="Ambience" count={(beds?.length ?? 0) + on("ambience").length}
        title="Each place's ambience bed, looped under its shots, and the files on the ambience lane of this pass's mix"
        note="A place's bed is made from its location's `ambience` words (the location's form, or series.json) and plays under every shot set there, its angles and relit versions too. A file of your own: drop one on the Ambience lane; it plays over the beds.">
        {bedsError && <div className="h3-note h3-note-err h3-small">The beds didn't load: {bedsError}</div>}
        {beds && !beds.length && <div className="h3-muted h3-small h3-pad">No place says what's heard there: give a location its `ambience` words.</div>}
        {(beds ?? []).map((b) => <BedRow key={b.ref} ep={ep} bed={b} />)}
        <ItemRows items={on("ambience")} empty="No files on the ambience lane." />
      </Section>
    </>
  );
}
