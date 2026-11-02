// The episode's mix from the timeline's sound lanes (docs/SOUND.md): fetched
// with its pass's status, and each edit one PUT /seriesmith/mix of the whole
// pass's mix, shown at once (optimistic) and rolled back if the server refuses
// it. Edits go on the cut's undo stack, so Ctrl+Z undoes cut and mix edits in
// the order they were made.

import { errText } from "./api";
import { currentPlaylist, onStatusLoaded, report } from "./actions";
import { pushEdit, setMixUndo } from "./cutActions";
import { api, host } from "./host";
import {
  addTrack, deleteTrack, itemToTrack, itemsOn, kindOf, labelOf, moveTrack, renameTrack, addHit, addItem, addPoint, pickFxTake, setBed, setFx, lowerStretch, moveItem, movePoint, newItemId, patchHit, patchItem, removeHit, removeItem, removePoint, sameMix,
  setShotVoices, setVoicesOnly,
  setTrack, timeAnchor, trimItem, type TrackPatch,
} from "./lib/mix";
import { locate } from "./lib/playlist";
import { trackList as trackListOf } from "./lib/mix";
import { statusKey, store, type AppState } from "./store";
import { tn } from "./lib/format";
import type { Anchor, Mix, MixBedSettings, MixFxSettings, MixHit, MixItem, MixResult, MixTrack, Pass, TrackKind } from "./types";

const set = store.set;
const get = store.get;

/** The pass open's mix (undefined until fetched). */
export function currentMix(s: AppState = get()): MixResult | undefined {
  return s.ep ? s.mix[statusKey(s.ep, s.pass)] : undefined;
}

// ---------------------------------------------------------------------------
// loading: with the pass's status (opened, and on every seriesmith.episode)
// ---------------------------------------------------------------------------

/** Saves in flight by statusKey: a mix fetched meanwhile would put the old one back. */
const inFlight = new Map<string, number>();
/** When each key's last save started: a fetch begun before it is stale. */
const savedAt = new Map<string, number>();
let clock = 0;

export async function loadMix(ep = get().ep, pass = get().pass): Promise<MixResult | undefined> {
  if (!ep) return undefined;
  const key = statusKey(ep, pass);
  const started = ++clock;
  void loadDuck(ep, pass);
  try {
    const r = await api().getMix(ep, pass);
    if (inFlight.get(key) || (savedAt.get(key) ?? 0) > started) return currentMix();
    set((s) => {
      const mixError = { ...s.mixError };
      delete mixError[key];
      const was = s.mix[key];
      // the same mix keeps its object, so nothing redraws
      const same = was && sameMix(was.mix, r.mix) && JSON.stringify(was.series) === JSON.stringify(r.series)
        && JSON.stringify(was.beds ?? []) === JSON.stringify(r.beds ?? [])
        && JSON.stringify(was.fx ?? []) === JSON.stringify(r.fx ?? [])
        && JSON.stringify(was.voices ?? null) === JSON.stringify(r.voices ?? null);
      return same ? { mixError } : { mix: { ...s.mix, [key]: r }, mixError };
    });
    void loadBeats(ep, pass);
    return r;
  } catch (e) {
    set((s) => ({ mixError: { ...s.mixError, [key]: errText(e) } }));
    return undefined;
  }
}

/** The pass's speech curve (Play all ducks with it), fetched with the mix; one the server can't
 * make is no ducking in the preview. The same curve keeps its object. */
async function loadDuck(ep: string, pass: Pass): Promise<void> {
  const key = statusKey(ep, pass);
  let r: { step: number; curve: number[] } | null = null;
  try {
    r = (await api().getMixDuck?.(ep, pass)) ?? null;
  } catch (e) {
    console.warn("seriesmith mix: no speech curve", e);
  }
  set((s) => {
    const was = s.mixDuck[key];
    if (!r) {
      if (!was) return {};
      const mixDuck = { ...s.mixDuck };
      delete mixDuck[key];
      return { mixDuck };
    }
    const same = was && was.step === r.step && was.curve.length === r.curve.length && was.curve.every((v, i) => v === r!.curve[i]);
    return same ? {} : { mixDuck: { ...s.mixDuck, [key]: r } };
  });
}

/** What the pass's beats are fetched for: its music items' files and the recording (null: nothing to cut to). */
export function beatsSig(s: AppState, ep: string, pass: Pass): string | null {
  const key = statusKey(ep, pass);
  const m = s.mix[key]?.mix;
  const music = (m?.items ?? []).filter((i) => kindOf(m, i.track) === "music").map((i) => `${i.id}=${i.path}`);
  const rec = s.status[key]?.track;
  const track = rec?.exists !== false && rec?.path ? rec.path : "";
  return music.length || track ? JSON.stringify([music, track]) : null;
}

/** The pass's beats (the timeline snaps trims to them, the Music lane draws them): fetched
 * only when the mix's music files or the recording have changed since the last fetch. */
export async function loadBeats(ep: string, pass: Pass): Promise<void> {
  const key = statusKey(ep, pass);
  const sig = beatsSig(get(), ep, pass);
  const was = get().mixBeats[key];
  if (sig == null) {
    if (was) set((s) => {
      const mixBeats = { ...s.mixBeats };
      delete mixBeats[key];
      return { mixBeats };
    });
    return;
  }
  if (was?.sig === sig || beatsAsked.get(key) === sig) return;
  beatsAsked.set(key, sig);
  try {
    const beats = await api().getMixBeats?.(ep, pass);
    if (beats) set((s) => ({ mixBeats: { ...s.mixBeats, [key]: { sig, beats } } }));
  } catch (e) {
    console.warn("seriesmith mix: no beats", e);
  } finally {
    if (beatsAsked.get(key) === sig) beatsAsked.delete(key);
  }
}
/** a fetch in flight, by statusKey: what it was for */
const beatsAsked = new Map<string, string>();

onStatusLoaded((ep, pass) => {
  const s = get();
  if (s.ep === ep && s.pass === pass) void loadMix(ep, pass);
});

// ---------------------------------------------------------------------------
// saving
// ---------------------------------------------------------------------------

let chain: Promise<unknown> = Promise.resolve();

/** Resolves once every mix save started so far has finished (tests). */
export function mixSettled(): Promise<void> {
  return chain.then(() => undefined, () => undefined);
}

function save(ep: string, pass: Pass, prev: MixResult, mix: Mix, what: string): Promise<boolean> {
  const key = statusKey(ep, pass);
  const optimistic: MixResult = { ...prev, mix };
  set((s) => ({ mix: { ...s.mix, [key]: optimistic } }));
  inFlight.set(key, (inFlight.get(key) ?? 0) + 1);
  savedAt.set(key, ++clock);
  const done = () => inFlight.set(key, (inFlight.get(key) ?? 1) - 1);
  const run = chain.then(async () => {
    try {
      const r = await api().putMix(ep, pass, mix);
      done();
      // as stored (defaults dropped), unless another edit has been shown since
      if (get().mix[key] === optimistic) set((s) => ({ mix: { ...s.mix, [key]: { ...optimistic, mix: r.mix } } }));
      return true;
    } catch (e) {
      done();
      if (get().mix[key] === optimistic) set((s) => ({ mix: { ...s.mix, [key]: prev } }));
      report(`Couldn't save the mix (${what})`, e);
      void loadMix(ep, pass);
      return false;
    }
  });
  chain = run;
  return run;
}

setMixUndo((ep, pass, mix, what) => {
  const prev = get().mix[statusKey(ep, pass)];
  return prev ? save(ep, pass, prev, mix, what) : Promise.resolve(false);
});

/**
 * One undoable mix edit: `change` turns the pass's mix into the new one (null:
 * nothing to do). Returns whether it was saved.
 */
export async function editMix(label: string, change: (mix: Mix) => Mix | null): Promise<boolean> {
  const s = get();
  if (!s.ep) return false;
  const ep = s.ep;
  const pass = s.pass;
  const prev = currentMix(s);
  if (!prev) {
    host().toast("warn", "The mix isn't loaded", get().mixError[statusKey(ep, pass)] ?? "Refresh, then try again.");
    return false;
  }
  const after = change(prev.mix);
  if (!after || sameMix(prev.mix, after)) return false;
  const ok = await save(ep, pass, prev, after, label.toLowerCase());
  if (ok) pushEdit(ep, pass, { label, order: null, fields: {}, mix: { before: prev.mix, after } });
  return ok;
}

// ---------------------------------------------------------------------------
// the edits
// ---------------------------------------------------------------------------

export function toggleSound(on?: boolean) {
  set((s) => ({ sound: on ?? !s.sound }));
}

const fps = () => {
  const s = get();
  return (s.ep ? s.status[statusKey(s.ep, s.pass)]?.fps : 0) || 24;
};

export function setTrackMix(track: MixTrack, patch: TrackPatch, label?: string): Promise<boolean> {
  const name = labelOf(currentMix()?.mix, track);
  const text = label ?? (patch.gain_db === null ? `${name} fader to its default`
    : patch.gain_db != null ? `${name} fader ${patch.gain_db > 0 ? "+" : ""}${patch.gain_db} dB`
    : patch.mute != null ? `${patch.mute ? "Mute" : "Unmute"} ${name.toLowerCase()}`
      : patch.solo != null ? `${patch.solo ? "Solo" : "Unsolo"} ${name.toLowerCase()}` : `${name} track`);
  return editMix(text, (m) => setTrack(m, track, patch));
}

// ---- tracks of your own (docs/SOUND.md phase 6) ----

/** A track added at the foot of the lanes, of `kind`, named `label`; its id, or null. */
export async function addMixTrack(kind: TrackKind, label: string): Promise<string | null> {
  let id: string | null = null;
  const ok = await editMix(`Add the ${label || kind} track`, (m) => {
    const r = addTrack(m, kind, label);
    if (!r) {
      host().toast("warn", "No more tracks", "A mix has at most 16.");
      return null;
    }
    id = r.id;
    return r.mix;
  });
  return ok ? id : null;
}

export function renameMixTrack(track: MixTrack, label: string): Promise<boolean> {
  return editMix(`Rename ${labelOf(currentMix()?.mix, track)} to ${label || "its default"}`, (m) => renameTrack(m, track, label));
}

export function moveMixTrack(track: MixTrack, by: -1 | 1): Promise<boolean> {
  return editMix(`Move ${labelOf(currentMix()?.mix, track)} ${by < 0 ? "up" : "down"}`, (m) => moveTrack(m, track, by));
}

/**
 * A track taken out, after asking when it has items: they move to another track (OK names
 * which) or go with it. The dialogue track can't be. Returns whether it was taken out.
 */
export async function deleteMixTrack(track: MixTrack, moveTo?: MixTrack | null): Promise<boolean> {
  const m = currentMix()?.mix;
  if (!m) return false;
  const name = labelOf(m, track);
  const n = itemsOn(m, track).length;
  let to: MixTrack | null = moveTo ?? null;
  if (n && moveTo === undefined) {
    // the first other track of its kind, else none: asked
    const same = trackListOf(m).find((t) => t.id !== track && t.kind === kindOf(m, track));
    const ask = same
      ? `${name} has ${n} item${n === 1 ? "" : "s"} on it.

OK: move ${n === 1 ? "it" : "them"} to ${same.label}.
Cancel: keep the track.`
      : `${name} has ${n} item${n === 1 ? "" : "s"} on it and no other track is of its kind.

OK: delete ${n === 1 ? "it" : "them"} with the track.
Cancel: keep the track.`;
    if (!confirm(ask)) return false;
    to = same?.id ?? null;
  }
  return editMix(n ? `Delete ${name} (${n} item${n === 1 ? "" : "s"} ${to ? `to ${labelOf(m, to)}` : "with it"})` : `Delete ${name}`,
    (mm) => deleteTrack(mm, track, to));
}

/** An item moved to another track (its menu's "Move to"). */
export function moveItemToTrack(id: string, track: MixTrack): Promise<boolean> {
  return editMix(`Move ${id} to ${labelOf(currentMix()?.mix, track)}`, (m) => itemToTrack(m, id, track));
}

/** A place's ambience bed: its level (dB, 0 the bed's own) or mute, the mix's `beds`. */
export function setMixBed(place: string, patch: MixBedSettings, label = `Change ${place}'s ambience`): Promise<boolean> {
  return editMix(label, (m) => setBed(m, place, patch));
}

/** A shot's effects: its level (dB), mute or keep_stale, the mix's `fx`. */
export function setMixFx(shot: string, patch: Partial<Omit<MixFxSettings, "take">>, label = `Change ${shot}'s effects`): Promise<boolean> {
  return editMix(label, (m) => setFx(m, shot, patch));
}

/** A shot's effects take into the pass's mix (null: its effects out); undoable like any mix edit. */
export function pickMixFx(shot: string, take: number | null): Promise<boolean> {
  return editMix(take == null ? `Effects off ${shot}` : `${shot}'s effects ${tn(take)}`, (m) => pickFxTake(m, shot, take));
}

/**
 * Make effects for `shots` from the takes the pass's cut plays (POST /seriesmith/fx/render),
 * on `target` (null: the series' or this machine's default, h3_foley). Nothing automatic:
 * only the shots asked for. Says what was queued and what couldn't be.
 */
export async function makeEffects(shots: string[], target: string | null = null): Promise<void> {
  const s = get();
  if (!s.ep || !shots.length) return;
  const fn = api().renderFx;
  if (!fn) {
    host().toast("warn", "This server can't make effects", "Update seriesmith.");
    return;
  }
  try {
    const r = await fn({ ep: s.ep, pass: s.pass, shots, ...(target ? { target } : {}) });
    const n = r.queued.length;
    const on = r.queued[0]?.target ?? target ?? "";
    host().toast("info", `Effects queued for ${n} shot${n === 1 ? "" : "s"}${on ? ` on ${on}` : ""}`,
      [r.skipped.length ? `Not made: ${r.skipped.map((x) => `${x.shot} (${x.why})`).join("; ")}.` : "",
       "Each is made from the take the cut plays; pick it on the Effects lane when it lands."].filter(Boolean).join(" "));
  } catch (e) {
    host().toast("error", "No effects were queued", errText(e));
  }
}

// ---- voices only (voices.py): the Dialogue track from the takes' voice stems ----

/** The Dialogue track's voices only on or off: one undoable edit. */
export function setVoicesOnlyMix(on: boolean): Promise<boolean> {
  return editMix(on ? "Dialogue: voices only" : "Dialogue: the takes' whole sound", (m) => setVoicesOnly(m, on));
}

/** Shots' own voices only (true: the stem; false: the whole sound; null: as the track): one edit. */
export function setShotVoicesMix(shots: string[], v: boolean | null): Promise<boolean> {
  const what = v == null ? "as the Dialogue track" : v ? "voices only" : "its whole sound";
  return editMix(`${shots.length === 1 ? shots[0] : `${shots.length} shots`}: ${what}`, (m) => {
    let out = m;
    for (const shot of shots) out = setShotVoices(out, shot, v);
    return sameMix(out, m) ? null : out;
  });
}

/** Split the cut's takes into their voice stems on the queue (shots: default the whole cut). */
export async function makeVoiceStems(shots?: string[], redo = false): Promise<void> {
  const s = get();
  if (!s.ep) return;
  const fn = api().makeVoices;
  if (!fn) {
    host().toast("warn", "This server can't make voice stems", "Update seriesmith, and restart it.");
    return;
  }
  try {
    const r = await fn({ ep: s.ep, pass: s.pass, ...(shots ? { shots } : {}), ...(redo ? { redo } : {}) });
    const n = r.queued.length;
    if (!n) {
      host().toast("info", "No voice stems to make", r.skipped.map((x) => `${x.shot}: ${x.why}`).join("; ") || "Nothing in the cut.");
      return;
    }
    host().toast("info", `Splitting ${n} take${n === 1 ? "" : "s"} into voice stems`,
      "On local ComfyUI (Hybrid Demucs), about a second each. They show in Jobs; the Dialogue lane says when they're there.");
  } catch (e) {
    host().toast("error", "No voice stems were queued", errText(e));
  }
}

/** The Refs tab's Ambience section on a place's bed, its row open (its takes, render again). */
export function openBedRef(place: string) {
  const id = `ambience:${place}`;
  set((s) => ({ menu: null, refOpen: { ...s.refOpen, [id]: true }, refFocus: { id, n: (s.refFocus?.n ?? 0) + 1 } }));
  host().show("refs");
}

/** An item moved to start at `at` (and onto `track`, dragged to another lane): one edit. */
export function moveMixItem(id: string, at: Anchor, track?: MixTrack): Promise<boolean> {
  return editMix(track ? `Move ${id} to ${labelOf(currentMix()?.mix, track)}` : `Move ${id}`, (m) => {
    const moved = moveItem(m, id, at, currentPlaylist(), fps()) ?? m;
    const out = track ? itemToTrack(moved, id, track) ?? moved : moved;
    return out === m ? null : out;
  });
}

export function trimMixItem(id: string, side: "in" | "out", at: Anchor, fileSecs: number | null): Promise<boolean> {
  return editMix(`Trim ${id} ${side === "in" ? "head" : "tail"}`, (m) => trimItem(m, id, side, at, currentPlaylist(), fps(), fileSecs));
}

export function setMixItem(id: string, patch: Partial<MixItem>, label = `Change ${id}`): Promise<boolean> {
  return editMix(label, (m) => patchItem(m, id, patch));
}

export function deleteMixItem(id: string): Promise<boolean> {
  return editMix(`Delete ${id}`, (m) => removeItem(m, id));
}

/** A volume point on an item at `at`, at the level its line has there. */
export function addMixPoint(id: string, at: Anchor): Promise<boolean> {
  return editMix(`Add a volume point to ${id}`, (m) => addPoint(m, id, at, currentPlaylist(), fps()));
}

/** Point `i` of an item moved (a finished drag: one edit). */
export function moveMixPoint(id: string, i: number, at: Anchor, db: number): Promise<boolean> {
  return editMix(`Move a volume point of ${id}`, (m) => movePoint(m, id, i, at, db, currentPlaylist(), fps()));
}

export function deleteMixPoint(id: string, i: number): Promise<boolean> {
  return editMix(`Delete a volume point of ${id}`, (m) => removePoint(m, id, i));
}

export function clearMixPoints(id: string): Promise<boolean> {
  return editMix(`Clear ${id}'s volume points`, (m) => patchItem(m, id, { points: [] }));
}

/**
 * An item lowered `db` from `t0` to `t1` (the cut's clock) with volume points
 * (the cue window's "Lower bars with breakpoints"), ramped over `ramp` seconds
 * at each end: one undoable edit, drawn on the timeline's lane.
 */
export function lowerMixItem(id: string, t0: number, t1: number, db: number, ramp: number, what = ""): Promise<boolean> {
  return editMix(`${db < 0 ? "Lower" : "Raise"} ${id}${what ? ` ${what}` : ""} ${Math.abs(db)} dB`,
    (m) => lowerStretch(m, id, t0, t1, db, ramp, currentPlaylist(), fps()));
}

/**
 * A sound file dropped on a lane: imported into the episode's `audio/`
 * (POST /seriesmith/audio/import), then an item there from `at`, playing to
 * the file's end.
 */
export async function dropOnLane(track: MixTrack, file: File, at: Anchor): Promise<boolean> {
  const ep = get().ep;
  if (!ep) return false;
  if (!currentMix()) {
    host().toast("warn", "The mix isn't loaded", "Refresh, then drop the file again.");
    return false;
  }
  let path: string;
  try {
    path = (await api().uploadClipAudio({ ep, file, name: file.name })).path;
  } catch (e) {
    report(`Couldn't import ${file.name}`, e);
    return false;
  }
  if (get().ep !== ep) return false;
  const lane = labelOf(currentMix()?.mix, track);
  const ok = await editMix(`Add ${file.name} to ${lane}`, (m) =>
    addItem(m, { id: newItemId(m, track), track, path, in: at, label: file.name.replace(/\.[^.]+$/, "") }));
  if (ok) host().toast("success", `${file.name} on ${lane}`, `From ${at.shot} frame ${at.frame}, to the file's end (drag its tail to stop it sooner).`);
  return ok;
}

/** A sound file picked from this computer onto a lane at `at` (a menu's "Add a sound file"):
 * the file dialog, then as dropOnLane. The sound lanes are opened to show it. */
export function pickSoundFile(track: MixTrack, at: Anchor): void {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = "audio/*,.wav,.mp3,.flac,.ogg,.m4a,.aac";
  input.onchange = () => {
    const file = input.files?.[0];
    if (!file) return;
    toggleSound(true);
    void dropOnLane(track, file, at);
  };
  input.click();
}

/** The anchor under the Play all playhead (null: Play all isn't open). */
export function playheadAnchor(): Anchor | null {
  const s = get();
  if (s.viewer?.kind !== "cut") return null;
  const items = currentPlaylist(s);
  return locate(items, s.cutPlay.pos).index >= 0 ? timeAnchor(items, s.cutPlay.pos, fps()) : null;
}

/** A hit at `at`, else at the Play all playhead. Returns its id (null: none added). */
export async function addMixHit(at?: Anchor | null, name = ""): Promise<string | null> {
  const where = at ?? playheadAnchor();
  if (!where) {
    host().toast("info", "A hit goes at the playhead", "Open Play all (or click the ruler) and stop on the frame, or double-click the hits lane.");
    return null;
  }
  let id: string | null = null;
  const ok = await editMix(`Add a hit at ${where.shot} frame ${where.frame}`, (m) => {
    const r = addHit(m, where, name);
    id = r.id;
    return r.mix;
  });
  return ok ? id : null;
}

export function moveMixHit(id: string, at: Anchor): Promise<boolean> {
  return editMix(`Move hit ${id}`, (m) => patchHit(m, id, { at }));
}

export function setMixHit(id: string, patch: Partial<MixHit>, label = `Change hit ${id}`): Promise<boolean> {
  return editMix(label, (m) => patchHit(m, id, patch));
}

export function deleteMixHit(id: string): Promise<boolean> {
  return editMix(`Delete hit ${id}`, (m) => removeHit(m, id));
}
