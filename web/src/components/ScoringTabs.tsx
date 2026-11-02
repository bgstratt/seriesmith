// The scoring window's tabs (docs/SCORING.md): Spotting, the episode's view where scoring
// starts, then the selected cue's Score, Arc and Orchestration & takes. One window: the
// spotting sheet and the cue window share its place and size, and switch on these tabs.

import { openSoundAdd } from "../mixActions";
import { openCueFromSpot, openSpotting } from "../spotActions";
import type { Rect } from "./FloatingWindow";

/** The scoring window's place and size, kept in this browser: both its views use it. */
export const SPOT_RECT_KEY = "seriesmith.spotting.rect";

/** Most of the page: scoring is the episode's view. */
export function defaultSpotRect(): Rect {
  const W = window.innerWidth || 1280;
  const H = window.innerHeight || 800;
  const w = Math.max(640, Math.min(1500, W - 48));
  const h = Math.max(480, Math.min(980, H - 80));
  return { x: Math.max(0, (W - w) / 2), y: 48, w, h };
}

export type CueTab = "score" | "arc" | "orch";
export type ScoringTab = "spot" | CueTab;

const CUE_TABS: [CueTab, string, string][] = [
  ["score", "Score", "Everything on one bar grid: the picture, hits, sections, the arc and the takes"],
  ["arc", "Arc", "The intensity lane large: draw it, shape it from a preset, snap its peaks to hits, cut sections from it"],
  ["orch", "Orchestration & takes", "Who plays in each bar; the takes, where bars are comped from another take or lowered"],
];

/**
 * `active` the tab showing; `cue` the cue the cue tabs open (null: the episode has none: they ask
 * for a new one, SoundAdd's dialog, and open on it);
 * `onCueTab` switches between the cue tabs in place (the cue window), else they open it.
 */
export function ScoringTabs({ active, cue, onCueTab }: { active: ScoringTab; cue: string | null; onCueTab?: (t: CueTab) => void }) {
  return (
    <span className="h3-seg" title="Scoring: the episode's spotting, then a cue's own views">
      <button className={active === "spot" ? "h3-on" : ""} onClick={() => active !== "spot" && openSpotting(cue)}
        title="Spotting: where scoring starts. The episode's music map under the cut with its sound: mark hits, place cues, see how each lands">
        <i className="pi pi-map" /> Spotting
      </button>
      {CUE_TABS.map(([t, name, title]) => (
        <button key={t} className={active === t ? "h3-on" : ""} data-tab={t}
          title={cue ? `${title} (${cue})` : `${title}. No cue yet: click to make one (its span and kind), then it opens here`}
          onClick={() => {
            if (!cue) {
              openSoundAdd({ kind: "cue", tab: t });
              return;
            }
            if (active === t) return;
            if (onCueTab && active !== "spot") onCueTab(t);
            else openCueFromSpot(cue, t);
          }}>
          {name}
        </button>
      ))}
    </span>
  );
}
