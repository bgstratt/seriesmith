// The Refs tab's Dub tracks: the shots that have one, or whose sound is set to dub
// (as shot keyframes list only those there are), how many each has and what its
// next take does for its sound. A row opens to the shot's Sound card (its
// dub tracks fetched then: playable, Use, Generate a dub track). Dub tracks aren't
// refs (they are the shot rendered tiny for its sound, kept in dub/<shot>/), but
// they are references a render reads, so they are listed beside the refs.

import { useState } from "react";
import { generateDubTracks, openSound } from "../actions";
import { dubTrackBlock } from "../lib/readiness";
import { useApp } from "../store";
import type { EpisodeStatus, ShotStatus } from "../types";
import { SoundCard } from "./SoundDialog";

/** The shots the section lists: those with a dub track, and any whose sound is a dub. */
export function dubShots(st: EpisodeStatus | undefined): ShotStatus[] {
  return (st?.shots ?? []).filter((s) => !s.orphan && ((s.dub_tracks ?? 0) > 0 || s.sound?.mode === "dub"));
}

function soundLabel(s: ShotStatus): string {
  const set = s.sound;
  if (!set) return s.audio_policy ? `${s.audio_policy} (default)` : "default";
  return set.mode === "dub" ? `dub · ${set.label ?? "?"}` : set.mode;
}

export function DubTracksSection({ st }: { st: EpisodeStatus | undefined }) {
  const targets = useApp((s) => s.targets);
  const [folded, setFolded] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const shots = dubShots(st);
  const noModel = dubTrackBlock(targets);
  if (!shots.length) return null;
  return (
    <div className="h3-seq">
      <div className="h3-seq-head" onClick={() => setFolded((f) => !f)}
        title="The shot's lines rendered tiny on a voice model for their sound only: what a shot set to Dub is lip-synced to">
        <span className="h3-chev">{folded ? "▶" : "▼"}</span>
        <b>Dub tracks</b>
        <span className="h3-muted h3-small">{shots.length}</span>
      </div>
      {!folded && shots.map((s) => {
        const n = s.dub_tracks ?? 0;
        const isOpen = open === s.shot;
        return (
          <div key={s.shot} className="h3-kf-shot">
            <div className="h3-row h3-small" style={{ gap: 8, cursor: "pointer" }} onClick={() => setOpen(isOpen ? null : s.shot)}
              title={isOpen ? "Fold" : "Its dub tracks (play, use, make another) and its sound"}>
              <span className="h3-chev">{isOpen ? "▼" : "▶"}</span>
              <b>{s.shot}</b>
              <span className={n ? "" : "h3-muted"}>{n ? `${n} dub track${n > 1 ? "s" : ""}` : "dubbed to the recording"}</span>
              <span className="h3-grow" />
              <span className={`h3-badge${s.sound ? " h3-b-voice" : ""}`}>{soundLabel(s)}</span>
              <button className="h3-btn" title={noModel ?? "Queue a dub track of this shot now (H3 Ref2VA, 64x64)"}
                onClick={(e) => { e.stopPropagation(); generateDubTracks([s.shot]); }}>
                <i className={noModel ? "pi pi-exclamation-triangle" : "pi pi-microphone"} /> Generate
              </button>
              <button className="h3-btn" title="The shot's whole Sound card, in a dialog (the cut's sound too)"
                onClick={(e) => { e.stopPropagation(); openSound([s.shot]); }}>Sound…</button>
            </div>
            {isOpen && <div className="h3-pad"><SoundCard shot={s.shot} cut={false} /></div>}
          </div>
        );
      })}
    </div>
  );
}
