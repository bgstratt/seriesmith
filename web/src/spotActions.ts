// The spotting sheet from the editor (docs/SOUND.md "The spotting sheet"):
// it is Play all's cut player (viewer kind "cut", `spot`) laid out with the
// episode's music map, so every "Play all is open" action (the playhead, + hit
// at the playhead, the keys) works in it unchanged. The cues planned against
// the pass (GET /seriesmith/cues?pass=) are fetched when it opens and when a
// take lands; the selected cue (GET /seriesmith/cue) when it's selected. A take
// auditioned plays in its cue's place in the preview only (store `audition`).

import { currentPlaylist, onCueEvent, report, seekCut } from "./actions";
import { cueKey, loadCue, loadCues, saveCueAt } from "./cueActions";
import { api, host } from "./host";
import { anchorTime } from "./lib/mix";
import { auditionOf, cutHits, nextHit, withTempo } from "./lib/spotting";
import { totalDuration } from "./lib/playlist";
import { currentMix, loadMix } from "./mixActions";
import { statusKey, store, type AppState } from "./store";
import type { CueTake, Pass } from "./types";

const set = store.set;
const get = store.get;

const fpsOf = (s: AppState) => (s.ep ? s.status[statusKey(s.ep, s.pass)]?.fps : 0) || 24;

/** The spotting sheet is open (and on which cue). */
export function spotOpen(s: AppState = get()): boolean {
  return s.viewer?.kind === "cut" && !!s.viewer.spot;
}

/** The cues planned against the pass, for the sheet. */
export async function loadCueStates(ep = get().ep, pass: Pass = get().pass): Promise<void> {
  if (!ep) return;
  try {
    const r = await api().cues(ep, pass);
    set((s) => ({ cueStates: { ...s.cueStates, [statusKey(ep, pass)]: r.cues } }));
  } catch (e) {
    report("Couldn't list the cues", e);
  }
}

/** Open the spotting sheet (on `cue`, selected): the cut player at the playhead, paused. */
export function openSpotting(cue?: string | null) {
  const s = get();
  if (!s.ep) return;
  const items = currentPlaylist(s);
  const wasCut = s.viewer?.kind === "cut";
  const pos = wasCut ? s.cutPlay.pos : Math.min(s.cutPlay.pos, totalDuration(items));
  set({
    viewer: { kind: "cut", spot: true, shot: items[0]?.shot ?? "", pass: s.pass, a: null, b: null, mode: "single", target: "a", cue: cue ?? (wasCut ? s.viewer?.cue : undefined) },
    menu: null,
    cutPlay: { playing: false, pos, seek: { t: pos, n: (s.cutPlay.seek?.n ?? 0) + 1 } },
  });
  void loadMix(s.ep, s.pass);
  void loadCues(s.ep);
  void loadCueStates(s.ep, s.pass);
  const sel = get().viewer?.cue;
  if (sel) void loadCue(s.ep, s.pass, sel);
}

/** The sheet's selected cue (fetched when it's selected); a take auditioned from another cue stops. */
export function selectSpotCue(cue: string | null) {
  const s = get();
  if (!spotOpen(s) || !s.ep) return;
  set({ viewer: { ...s.viewer!, cue: cue ?? undefined }, ...(s.audition && s.audition.cue !== cue ? { audition: null } : {}) });
  if (cue) void loadCue(s.ep, s.pass, cue);
}

/** The cue window, from the sheet (its head goes back to the sheet). */
export function openCueFromSpot(cue: string) {
  const s = get();
  if (!s.ep) return;
  set({ viewer: { kind: "cue", shot: "", pass: s.pass, a: null, b: null, mode: "single", target: "a", cue, back: "spot" }, menu: null, audition: null,
        cutPlay: { ...s.cutPlay, playing: false } });
}

/** The playhead on the next hit (dir 1) or the one before (-1). False: none that way. */
export function jumpToHit(dir: 1 | -1): boolean {
  const s = get();
  const items = currentPlaylist(s);
  const fps = fpsOf(s);
  const h = nextHit(cutHits(currentMix(s)?.mix, items, fps), s.cutPlay.pos, dir, fps);
  if (!h) return false;
  seekToTime(h.t);
  return true;
}

/** The playhead at cut time `t` (a hit's, a row's), paused, on its frame. */
export function seekToTime(t: number) {
  const s = get();
  if (s.cutPlay.playing) set({ cutPlay: { ...s.cutPlay, playing: false, rate: 1 } });
  const fps = fpsOf(s);
  seekCut(Math.round(t * fps + 1e-6) / fps);
}

/**
 * Take `take` of cue `cue` under the picture from the cue's in point, in the
 * cue's place: the preview's mix only (the mix isn't changed). Needs the cue
 * fetched (its plan) and the take finished.
 */
export function auditionTake(cue: string, take: CueTake): boolean {
  const s = get();
  if (!s.ep || !spotOpen(s)) return false;
  const r = s.cue[cueKey(s.ep, s.pass, cue)];
  const a = r?.plan ? auditionOf(s.ep, s.pass, r.spec, r.plan, take) : null;
  if (!r || !a) return false;
  const t0 = anchorTime(currentPlaylist(s), r.spec.in, fpsOf(s));
  if (t0 == null) return false;
  set({ audition: a });
  seekCut(t0);
  set((x) => ({ cutPlay: { ...x.cutPlay, playing: true, rate: 1 } }));
  return true;
}

/** Back to the mix as it is. */
export function stopAudition() {
  if (get().audition) set({ audition: null });
}

/**
 * Cue `cue` held at `bpm` (one of the fit's alternatives): its bpm set and the
 * tempo fixed, as the cue window's tempo field does with fixed ticked; the cue
 * and the list fetched again.
 */
export async function setCueTempo(cue: string, bpm: number): Promise<boolean> {
  const s = get();
  if (!s.ep) return false;
  const key = cueKey(s.ep, s.pass, cue);
  const r = s.cue[key];
  if (!r) return false;
  const ok = await saveCueAt({ ep: s.ep, pass: s.pass, cue, key }, withTempo(r.spec, bpm));
  if (ok) {
    host().toast("info", `${cue} at ${bpm} bpm`, "Fixed at that tempo; its takes are stale until rendered again.");
    void loadCueStates(s.ep, s.pass);
  }
  return ok;
}

/** Render the cues' takes again (each its model's preset's number), on the queue. */
export async function renderCues(cues: string[]): Promise<number> {
  const s = get();
  if (!s.ep || !cues.length) return 0;
  let n = 0;
  for (const cue of cues) {
    try {
      n += (await api().renderCue({ ep: s.ep, pass: s.pass, cue })).queued.length;
    } catch (e) {
      report(`Couldn't render ${cue}`, e);
    }
  }
  if (n) host().toast("info", `${n} take${n === 1 ? "" : "s"} queued for ${cues.join(", ")}`, "Each is measured as it lands; pick one in the cue window.");
  void loadCueStates(s.ep, s.pass);
  return n;
}

// a take landed: the list again (once for a burst), and the selected cue
let timer: ReturnType<typeof setTimeout> | null = null;
onCueEvent((d) => {
  if (!spotOpen()) return;
  if (timer) clearTimeout(timer);
  timer = setTimeout(() => {
    timer = null;
    const s = get();
    if (!spotOpen(s) || !s.ep) return;
    void loadCueStates(s.ep, s.pass);
    if (d.cue && s.viewer?.cue === d.cue) void loadCue(s.ep, s.pass, d.cue);
  }, 150);
});
