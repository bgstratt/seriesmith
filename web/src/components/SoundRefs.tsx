// The Refs tab's sound beyond the voices (docs/SOUND.md): Music (the episode's cues),
// Effects and Ambience (the files on those lanes of this pass's mix). Voices and dub
// tracks stay where they are, for the dialogue. Like dub tracks they aren't refs, but
// they are what the episode's sound is made from, so they are listed beside the refs.

import { useEffect, useState } from "react";
import { loadCues, openCue } from "../cueActions";
import { cueTitle } from "../lib/cue";
import { currentMix, deleteMixItem, loadMix, toggleSound } from "../mixActions";
import { useApp } from "../store";
import type { MixItem } from "../types";

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
      <Section label="Ambience" count={on("ambience").length}
        title="Room tone and air on the ambience lane of this pass's mix"
        note="Coming: a location's ambience bed, made once and looped under its shots (docs/SOUND.md phase 3). For now: a file (right-click a shot: Sound ▸ Add ambience, or drop one on the lane).">
        <ItemRows items={on("ambience")} empty="None on the ambience lane." />
      </Section>
    </>
  );
}
