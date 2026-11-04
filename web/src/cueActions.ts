// Music cues from the editor (docs/SOUND.md "The cue window"): the episode's
// list (GET /seriesmith/cues, with the mix while the lanes are unfolded), the
// cue open (GET /seriesmith/cue, fetched when it opens and when one of its
// takes lands: seriesmith.cue), and the edits. Every edit is one PUT of the
// spec, shown at once, then the cue fetched again: the plan (tempo, bars,
// sections, arc, prompt) is the server's to work out.

import { errText } from "./api";
import { currentPlaylist, onCueEvent, report } from "./actions";
import { api, host } from "./host";
import { applyPreset, barsLabel, meterText, newCueId, newCueSpan, presetBase } from "./lib/cue";
import { loadMix } from "./mixActions";
import { loadCueStates, openSpotting, selectSpotCue, spotOpen } from "./spotActions";
import { statusKey, store, type AppState } from "./store";
import type { Anchor, CueKind, CuePlan, CuePreset, CueResult, CueSpec, Pass } from "./types";

const set = store.set;
const get = store.get;

export const cueKey = (ep: string, pass: Pass, cue: string) => `${ep}|${pass}|${cue}`;

/** The cue the viewer has open, on the pass the editor shows, with its key (null: none). */
export function openCueRef(s: AppState = get()): { ep: string; pass: Pass; cue: string; key: string } | null {
  const v = s.viewer;
  if (!s.ep || v?.kind !== "cue" || !v.cue) return null;
  return { ep: s.ep, pass: s.pass, cue: v.cue, key: cueKey(s.ep, s.pass, v.cue) };
}

// ---------------------------------------------------------------------------
// loading
// ---------------------------------------------------------------------------

export async function loadCues(ep = get().ep): Promise<void> {
  if (!ep) return;
  try {
    const r = await api().cues(ep);
    const was = get().cues[ep];
    if (!was || JSON.stringify(was) !== JSON.stringify(r.cues)) set((s) => ({ cues: { ...s.cues, [ep]: r.cues } }));
  } catch {
    // a server without cues: the lanes don't offer the window
    if (!get().cues[ep]) set((s) => ({ cues: { ...s.cues, [ep]: [] } }));
  }
}

/** Saves in flight by key, and when the last began: a fetch begun before it is stale. */
const inFlight = new Map<string, number>();
const savedAt = new Map<string, number>();
let clock = 0;

export async function loadCue(ep: string, pass: Pass, cue: string): Promise<CueResult | undefined> {
  const key = cueKey(ep, pass, cue);
  const started = ++clock;
  try {
    const r = await api().getCue(ep, pass, cue);
    if (inFlight.get(key) || (savedAt.get(key) ?? 0) > started) return get().cue[key];
    set((s) => {
      const cueError = { ...s.cueError };
      delete cueError[key];
      return { cue: { ...s.cue, [key]: r }, cueError };
    });
    return r;
  } catch (e) {
    set((s) => ({ cueError: { ...s.cueError, [key]: errText(e) } }));
    return undefined;
  }
}

/** The cue window, in the viewer's place (it fetches the cue: CueWindow). */
export function openCue(cue: string) {
  if (!get().ep) return;
  set({ viewer: { kind: "cue", shot: "", pass: get().pass, a: null, b: null, mode: "single", target: "a", cue }, menu: null });
}

// a take landed: the open cue again (once for a burst), and the list
let eventTimer: ReturnType<typeof setTimeout> | null = null;
onCueEvent((d) => {
  const o = openCueRef();
  if (o && d.cue === o.cue) {
    if (eventTimer) clearTimeout(eventTimer);
    eventTimer = setTimeout(() => {
      eventTimer = null;
      const now = openCueRef();
      if (now) void loadCue(now.ep, now.pass, now.cue);
    }, 150);
  }
  const ep = get().ep;
  if (ep && get().cues[ep]) void loadCues(ep);
});

// ---------------------------------------------------------------------------
// editing
// ---------------------------------------------------------------------------

let chain: Promise<unknown> = Promise.resolve();

/** Resolves once every cue save started so far has finished (tests). */
export function cueSettled(): Promise<void> {
  return chain.then(() => undefined, () => undefined);
}

/**
 * The open cue's spec replaced: shown at once (with `plan` patched, so a
 * dragged edge stays where it was let go), saved, then the cue fetched again.
 */
export function saveCue(spec: CueSpec, plan?: Partial<CuePlan>): Promise<boolean> {
  return saveCueAt(openCueRef(), spec, plan);
}

/** saveCue for cue `o` (the spotting sheet's selected one, which isn't open in the cue window). */
export function saveCueAt(o: { ep: string; pass: Pass; cue: string; key: string } | null, spec: CueSpec, plan?: Partial<CuePlan>): Promise<boolean> {
  if (!o) return Promise.resolve(false);
  const prev = get().cue[o.key];
  if (prev) set((s) => ({ cue: { ...s.cue, [o.key]: { ...prev, spec, plan: prev.plan && plan ? { ...prev.plan, ...plan } : prev.plan } } }));
  inFlight.set(o.key, (inFlight.get(o.key) ?? 0) + 1);
  savedAt.set(o.key, ++clock);
  const done = () => inFlight.set(o.key, (inFlight.get(o.key) ?? 1) - 1);
  const run = chain.then(async () => {
    try {
      await api().putCue(o.ep, spec);
      done();
      await loadCue(o.ep, o.pass, o.cue);
      return true;
    } catch (e) {
      done();
      report(`Couldn't save cue ${spec.id}`, e);
      await loadCue(o.ep, o.pass, o.cue);
      return false;
    }
  });
  chain = run;
  return run;
}

/** How a new cue is asked for beyond its anchor (the "+" dialog, the spotting map's menu). */
export interface NewCueOpts {
  /** over these shots (their first frame played to their last), not the selection */
  shots?: string[];
  /** from `at` to the end of this shot */
  until?: string;
  /** score (the default) or song */
  kind?: CueKind;
  /** open it in the scoring window on this tab (from the spotting sheet), not the cue window's first */
  tab?: "score" | "arc" | "orch";
}

/**
 * A new cue over the shots selected (several), else from `at` to the end of its shot,
 * saved with the next free id and opened; `opts` says the span (and kind) instead.
 */
export async function newCue(at: Anchor | null, opts: NewCueOpts = {}): Promise<string | null> {
  const s = get();
  const ep = s.ep;
  if (!ep) return null;
  const fps = s.status[statusKey(ep, s.pass)]?.fps || 24;
  // shots asked for: over them; several shots selected: over them; else from where it was asked
  const shots = opts.shots?.length ? opts.shots : !opts.until && s.multi.length > 1 ? s.multi : [];
  const span = newCueSpan(currentPlaylist(s), fps, shots, at, opts.until ?? null);
  if (!span) {
    host().toast("info", "A cue goes over the cut", "Right-click the music lane over a clip, or select the shots it plays over first.");
    return null;
  }
  if (!s.cues[ep]) await loadCues(ep);
  const taken = (get().cues[ep] ?? []).map((c) => c.spec.id);
  const items = (s.mix[statusKey(ep, s.pass)]?.mix.items ?? []).map((i) => i.id);
  const id = newCueId(taken, items);
  try {
    await api().putCue(ep, { id, ...(opts.kind && opts.kind !== "score" ? { kind: opts.kind } : {}), in: span.in, out: span.out });
  } catch (e) {
    report("Couldn't make the cue", e);
    return null;
  }
  void loadCues(ep);
  if (opts.tab) {
    const now = get();
    set({ viewer: { kind: "cue", shot: "", pass: now.pass, a: null, b: null, mode: "single", target: "a", cue: id, back: "spot", cueTab: opts.tab }, menu: null, audition: null,
          cutPlay: { ...now.cutPlay, playing: false } });
  } else openCue(id);
  return id;
}

/** The passes whose mix (as loaded) has cue `cue`'s item, with those its takes say they were placed in. */
function cueMixes(s: AppState, ep: string, cue: string): Pass[] {
  const placed = new Set<Pass>((s.cues[ep] ?? []).find((c) => c.spec.id === cue)?.placed ?? []);
  for (const p of ["proxy", "final"] as Pass[]) {
    if ((s.mix[statusKey(ep, p)]?.mix.items ?? []).some((i) => i.id === cue || i.path.startsWith(`sound/${cue}/`))) placed.add(p);
  }
  return (["proxy", "final"] as Pass[]).filter((p) => placed.has(p));
}

/** What the delete asks, in words (the confirm's text). */
export function deleteCueAsk(s: AppState, ep: string, cue: string): string {
  const n = (s.cues[ep] ?? []).find((c) => c.spec.id === cue)?.takes ?? (s.cue[cueKey(ep, s.pass, cue)]?.takes.length ?? 0);
  const mixes = cueMixes(s, ep, cue);
  const what = n ? `${cue} and its ${n} take${n === 1 ? "" : "s"} go` : `${cue} goes`;
  const out = mixes.length ? `it's taken out of the ${mixes.join(" and ")} mix${mixes.length > 1 ? "es" : ""}` : "it isn't in either pass's mix";
  return `Delete cue ${cue}?

${what} to the episode's _history folder; ${out}.

Ctrl+Z can't bring it back (move the folder back to sound/${cue}/ by hand). To keep it but not hear it, untick "plays in the mix" instead.`;
}

/**
 * Cue `cue` deleted after asking (DELETE /seriesmith/cue): its folder to the episode's
 * _history, its items out of both passes' mixes. Not undoable here. The cue list, the mix and
 * the spotting sheet's cues are fetched again; the cue window showing it goes back to Spotting.
 */
export async function deleteCue(cue: string): Promise<boolean> {
  const s = get();
  const ep = s.ep;
  if (!ep) return false;
  if (!confirm(deleteCueAsk(s, ep, cue))) return false;
  let r: Awaited<ReturnType<ReturnType<typeof api>["deleteCue"]>>;
  try {
    r = await api().deleteCue(ep, cue);
  } catch (e) {
    report(`Couldn't delete cue ${cue}`, e);
    return false;
  }
  const now = get();
  if (now.ep === ep) {
    if (now.viewer?.kind === "cue" && now.viewer.cue === cue) openSpotting(null);
    else if (spotOpen(now) && now.viewer?.cue === cue) selectSpotCue(null);
    set((x) => {
      const cueMap = { ...x.cue };
      for (const p of ["final", "proxy"] as Pass[]) delete cueMap[cueKey(ep, p, cue)];
      return { cue: cueMap, ...(x.audition?.cue === cue ? { audition: null } : {}) };
    });
  }
  host().toast("success", `Cue ${cue} deleted`,
    `${r.takes ? `It and its ${r.takes} take${r.takes === 1 ? "" : "s"}` : "It"} went to ${r.moved_to}${r.mixes.length ? `; taken out of the ${r.mixes.join(" and ")} mix${r.mixes.length > 1 ? "es" : ""}` : ""}.`);
  await Promise.all([loadCues(ep), loadMix(ep, get().pass), loadCueStates(ep, get().pass)]);
  return true;
}

/** Render `takes` takes of the open cue (absent: its model's preset's). */
export async function renderCue(takes?: number): Promise<boolean> {
  const o = openCueRef();
  if (!o) return false;
  await cueSettled();
  try {
    const r = await api().renderCue({ ep: o.ep, pass: o.pass, cue: o.cue, ...(takes ? { takes } : {}) });
    host().toast("info", `${o.cue}: ${r.queued.length} take${r.queued.length === 1 ? "" : "s"} queued`, "Each is measured as it lands, and the list ranks them.");
  } catch (e) {
    report(`Couldn't render ${o.cue}`, e);
    return false;
  }
  await loadCue(o.ep, o.pass, o.cue);
  return true;
}

/** A take as the cue's item on the music track, its level fitted to the arc; the mix fetched again. */
export async function pickCueTake(take: number): Promise<boolean> {
  const o = openCueRef();
  if (!o) return false;
  try {
    await api().pickCue({ ep: o.ep, pass: o.pass, cue: o.cue, take, gain: true });
  } catch (e) {
    report(`Couldn't place ${o.cue} t${String(take).padStart(2, "0")}`, e);
    return false;
  }
  host().toast("success", `${o.cue}: t${String(take).padStart(2, "0")} in the mix`, "On the music track from the cue's in point, its level fitted to the arc.");
  await Promise.all([loadMix(o.ep, o.pass), loadCue(o.ep, o.pass, o.cue), loadCues(o.ep)]);
  return true;
}

/** A take of the open cue made a series theme (sound.themes.<name>), in this episode's series config
 * and (everywhere) every one beside it; the cue fetched again, so its theme list has it. */
export async function pinCueTheme(take: number, name: string, role: string | null, words: string | null, everywhere: boolean,
  who: string[] | null = null): Promise<boolean> {
  const o = openCueRef();
  if (!o) return false;
  let r;
  try {
    r = await api().pinCueTheme({ ep: o.ep, cue: o.cue, take, name, role, words, everywhere, ...(who?.length ? { for: who } : {}) });
  } catch (e) {
    report(`Couldn't make ${o.cue} t${String(take).padStart(2, "0")} a series theme`, e);
    return false;
  }
  const where = r.written.length ? `Written into the series config of ${r.written.join(", ")}` : "Every series config had it already";
  host().toast("success", `${name}: ${o.cue} t${String(take).padStart(2, "0")}`, `${where}. A cue's Theme can now be this series theme.`);
  await loadCue(o.ep, o.pass, o.cue);
  return true;
}

/**
 * A comp: take `take` with the cue's bars [a, b) from take `from`, spliced on
 * bar lines into a new take, measured and ranked (POST /seriesmith/cue/comp).
 * Returns its number (null: refused).
 */
export async function compCueTake(take: number, from: number, bars: [number, number]): Promise<number | null> {
  const o = openCueRef();
  if (!o) return null;
  await cueSettled();
  const tn = (n: number) => `t${String(n).padStart(2, "0")}`;
  let made: number;
  try {
    made = (await api().compCue({ ep: o.ep, pass: o.pass, cue: o.cue, take, from, bars })).take.take;
  } catch (e) {
    report(`Couldn't comp ${o.cue} ${tn(take)} with ${tn(from)}`, e);
    return null;
  }
  host().toast("success", `${o.cue}: ${tn(made)}, ${tn(take)} with ${barsLabel(bars)} from ${tn(from)}`, "Spliced on the bar lines, measured and ranked with the others.");
  await Promise.all([loadCue(o.ep, o.pass, o.cue), loadCues(o.ep)]);
  return made;
}

/**
 * A repaint: take `take`'s bars [a, b) made again on its own model, the rest of it kept, as a
 * new take queued (POST /seriesmith/cue/repaint); `fresh` asks for new music there rather than
 * the same music played again. Returns its number (null: refused).
 */
export async function repaintCueTake(take: number, bars: [number, number], fresh = false): Promise<number | null> {
  const o = openCueRef();
  if (!o) return null;
  await cueSettled();
  const tn = (n: number) => `t${String(n).padStart(2, "0")}`;
  let made: number;
  try {
    made = (await api().repaintCue({ ep: o.ep, pass: o.pass, cue: o.cue, take, bars, ...(fresh ? { fresh } : {}) })).queued.take;
  } catch (e) {
    report(`Couldn't repaint ${barsLabel(bars)} of ${o.cue} ${tn(take)}`, e);
    return null;
  }
  host().toast("info", `${o.cue}: ${tn(made)} queued, ${tn(take)} with ${barsLabel(bars)} made again`,
    "The rest is the take's own; it's measured and ranked with the others when it lands.");
  await Promise.all([loadCue(o.ep, o.pass, o.cue), loadCues(o.ep)]);
  return made;
}

/**
 * A preset's fields on the open cue (lib/cue.ts applyPreset). Its sections are
 * whole bars of the cue, and the bars follow the tempo and meter: when those
 * change, they're saved first and the sections fitted to the plan that comes back.
 */
export async function applyCuePreset(preset: CuePreset, modelSings: boolean): Promise<boolean> {
  const o = openCueRef();
  const r = o ? get().cue[o.key] : undefined;
  if (!o || !r) return false;
  const base = presetBase(r.spec, preset, modelSings);
  let plan = r.plan;
  if (!plan || (r.spec.bpm ?? 100) !== (base.bpm ?? 100) || meterText(r.spec.meter) !== meterText(base.meter)) {
    if (!(await saveCue(base))) return false;
    plan = get().cue[o.key]?.plan ?? null;
  }
  return saveCue(applyPreset(base, preset, plan?.bars ?? null, modelSings));
}
