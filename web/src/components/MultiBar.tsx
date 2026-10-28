// Several shots selected (Ctrl/⌘- or Shift-click): how many, queue them, clear.
// In the Shots tab and the Timeline's header; Esc clears it.

import { useEffect } from "react";
import { clearMulti, generateDubTracks, openSound, renderSelected } from "../actions";
import { dubTrackBlock } from "../lib/readiness";
import { useApp } from "../store";

export function MultiBar() {
  const multi = useApp((s) => s.multi);
  const pass = useApp((s) => s.pass);
  const noVoice = dubTrackBlock(useApp((s) => s.targets));
  const n = multi.length;
  useEffect(() => {
    if (!n) return;
    const key = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (e.key !== "Escape" || el?.closest("input, textarea, select, [contenteditable], .h3-dialog, .h3-menu")) return;
      clearMulti();
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [n]);
  if (n < 2) return null;
  return (
    <span className="h3-row h3-multibar" title={multi.join(", ")}>
      <b>{n} selected</b>
      <button className="h3-btn h3-primary" title={`Queue a ${pass} take of each: a shot's first at its built seed, a new seed otherwise (as Generate does)`}
        onClick={() => renderSelected()}>
        <i className="pi pi-play" /> Generate {n}
      </button>
      <button className="h3-btn h3-primary"
        title={noVoice ?? "Queue a dub track of each now: the shot rendered for its sound only (H3 Ref2VA, 64x64), its voices cloned; pick one in Sound… to dub the shot with"}
        onClick={() => generateDubTracks(multi)}>
        <i className={noVoice ? "pi pi-exclamation-triangle" : "pi pi-microphone"} /> Generate dub tracks
      </button>
      <button className="h3-btn" title="Their sound: generate, clone, or dub the recorded track" onClick={() => openSound(multi)}>
        Sound…
      </button>
      <button className="h3-btn" title="Choose first: the video model for this run, where they render" onClick={() => renderSelected(true)}>
        Render…
      </button>
      <button className="h3-btn h3-icon" title="Clear the selection (Esc)" onClick={clearMulti}><i className="pi pi-times" /></button>
    </span>
  );
}
