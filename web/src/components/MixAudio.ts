// Play all hears the mix: the items of the pass's mix played through Web Audio
// on the cut's clock (lib/mix's playPlan), each through its own gain (its dB,
// volume points and fades as gain automation) into its track's fader (mute and
// solo too, set at once), then the track's ducking: the server's speech curve
// times its duck_db, regions applied (lib/mix's duckTracks), as automation on a
// gain of its own after the fader, so the preview dips where the export does.
// It follows the store's cutPlay: started at the playhead on play, stopped on
// pause, laid again on a seek, a change of the mix or the cut, and when the
// video's clock and the audio's drift apart. A take auditioned (the spotting
// sheet's: store `audition`) plays in its cue's place, in the preview only. The clips' own sound stays on the
// <video> elements (the Viewer sets their volume from the dialogue fader and a
// region's dialogue_db: a video only goes down), but for voices only: a clip that
// plays its take's voice stem has its <video> muted (the Viewer: lib/mix voicedShots)
// and the stem played here on the dialogue track at its clip (lib/mix voicePlan), its
// fader and regions as the other tracks'; not while the recording plays instead.

import { useEffect, useRef } from "react";
import { bedPlan, duckTracks, fxPlan, entryEnd, entryLevel, entryMarks, playPlan, trackGains, voicePlan, type PlayEntry } from "../lib/mix";
import { totalDuration, type PlayItem } from "../lib/playlist";
import { api } from "../host";
import { statusKey, store } from "../store";
import { currentMix } from "../mixActions";
import { auditionMix } from "../lib/spotting";
import type { MixTrack } from "../types";

/** seconds the audio may stray from the picture before it is laid again */
const DRIFT = 0.15;
/** and not more often than this (a clip's first frame can hold the picture a moment) */
const RELAY_GAP_MS = 600;

/** each track's dip in dB, a value per `step` seconds of the cut (lib/mix's duckTracks) */
export type Ducking = ReturnType<typeof duckTracks>;

export class MixEngine {
  private ctx: AudioContext | null = null;
  private tracks: Partial<Record<MixTrack, GainNode>> = {};
  /** after each fader: the ducking and the regions, as automation on the cut's clock */
  private ducks: Partial<Record<MixTrack, GainNode>> = {};
  private ducking: Ducking | null = null;
  private buffers = new Map<string, Promise<AudioBuffer | null>>();
  private live: { src: AudioBufferSourceNode; gain: GainNode }[] = [];
  /** the cut time playing at the context's `t0` */
  private pos0 = 0;
  private t0 = 0;
  private rate = 1;
  private gen = 0;
  running = false;
  lastLay = 0;

  /** `AC`: the AudioContext to make (tests); the window's by default */
  constructor(private url: (path: string) => string, private AC?: new () => AudioContext) {}

  private context(): AudioContext | null {
    if (this.ctx) return this.ctx;
    const AC = this.AC ?? (typeof window !== "undefined" ? (window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext) : undefined);
    if (!AC) return null;
    this.ctx = new AC();
    return this.ctx;
  }

  /** A track's fader, its ducking after it (made the first time the track is heard: the
   * mix's own tracks as well as the four, docs/SOUND.md phase 6). */
  private fader(t: MixTrack): GainNode | null {
    const ctx = this.ctx;
    if (!ctx) return null;
    let g = this.tracks[t];
    if (!g) {
      g = ctx.createGain();
      const d = ctx.createGain();
      g.connect(d);
      d.connect(ctx.destination);
      this.tracks[t] = g;
      this.ducks[t] = d;
    }
    return g;
  }

  /** A file decoded once (null: it can't be). */
  buffer(path: string): Promise<AudioBuffer | null> {
    let p = this.buffers.get(path);
    if (!p) {
      const ctx = this.context();
      p = !ctx ? Promise.resolve(null) : fetch(this.url(path))
        .then((r) => (r.ok ? r.arrayBuffer() : Promise.reject(new Error(`${r.status}`))))
        .then((b) => ctx.decodeAudioData(b))
        .catch((e) => {
          console.warn("seriesmith mix: can't play", path, e);
          return null;
        });
      this.buffers.set(path, p);
    }
    return p;
  }

  setGains(g: Record<MixTrack, number>) {
    const ctx = this.ctx;
    if (!ctx) return;
    for (const t of Object.keys(g)) this.fader(t)?.gain.setTargetAtTime(g[t], ctx.currentTime, 0.02);
    // a track no longer in the mix: silent
    for (const t of Object.keys(this.tracks)) if (!(t in g)) this.tracks[t]?.gain.setTargetAtTime(0, ctx.currentTime, 0.02);
  }

  /** The ducking changed: laid again from where the audio is, if it's playing. */
  setDucking(d: Ducking | null) {
    this.ducking = d;
    if (this.running) this.layDucking();
  }

  /** The context's time of cut time `t`. */
  private ctxAt(t: number): number {
    return this.t0 + (t - this.pos0) / this.rate;
  }

  /** Each track's dip from where the audio is to the cut's end: a ramp to each step of the curve. */
  private layDucking() {
    const ctx = this.ctx;
    if (!ctx) return;
    const from = Math.max(this.pos0, this.now());
    const when = Math.max(ctx.currentTime, this.ctxAt(from));
    for (const t of Object.keys(this.ducks)) {
      const g = this.ducks[t]?.gain;
      if (!g) continue;
      g.cancelScheduledValues(0);
      const db = this.ducking?.db[t];
      if (!db) {
        g.setValueAtTime(1, ctx.currentTime);
        continue;
      }
      const step = this.ducking!.step;
      const k = Math.min(db.length - 1, Math.max(0, from / step));
      const i0 = Math.floor(k);
      const v0 = db[i0] + (i0 + 1 < db.length ? (db[i0 + 1] - db[i0]) * (k - i0) : 0);
      g.setValueAtTime(10 ** (v0 / 20), when);
      for (let i = i0 + 1; i < db.length; i++) g.linearRampToValueAtTime(10 ** (db[i] / 20), this.ctxAt(i * step));
    }
  }

  /** Where the audio is on the cut's clock now. */
  now(): number {
    return this.ctx ? this.pos0 + (this.ctx.currentTime - this.t0) * this.rate : this.pos0;
  }

  stop() {
    this.gen++;
    this.running = false;
    for (const { src, gain } of this.live) {
      try {
        src.stop();
      } catch {
        /* never started */
      }
      src.disconnect();
      gain.disconnect();
    }
    this.live = [];
  }

  /** Lay the plan from cut time `pos` at `rate` (forwards only). */
  play(plan: PlayEntry[], total: number, pos: number, rate: number, gains: Record<MixTrack, number>) {
    this.stop();
    const ctx = this.context();
    if (!ctx) return;
    if (ctx.state === "suspended") void ctx.resume().catch(() => {});
    this.setGains(gains);
    this.running = true;
    this.lastLay = performance.now();
    // a little ahead, so every source starts on time
    this.t0 = ctx.currentTime + 0.03;
    this.pos0 = pos;
    this.rate = rate;
    this.layDucking();
    const gen = this.gen;
    for (const e of plan) {
      if (e.end != null && e.end <= pos) continue;
      void this.buffer(e.path).then((buf) => {
        if (buf && gen === this.gen) this.start(ctx, e, buf, total);
      });
    }
  }

  private start(ctx: AudioContext, e: PlayEntry, buf: AudioBuffer, total: number) {
    const end = entryEnd(e, buf.duration, total);
    const at = Math.max(e.start, this.now());
    if (end <= at) return;
    const ctxAt = (t: number) => this.ctxAt(t);
    let fileAt = e.offset + (at - e.start);
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.playbackRate.value = this.rate;
    if (e.loop && buf.duration > 0) {
      src.loop = true;
      src.loopStart = 0;
      src.loopEnd = buf.duration;
      fileAt %= buf.duration;
    } else if (fileAt >= buf.duration) {
      return;
    }
    const gain = ctx.createGain();
    // its level now, then its fades and points as ramps
    const when = Math.max(ctx.currentTime, ctxAt(at));
    gain.gain.setValueAtTime(entryLevel(e, at, end), when);
    for (const t of entryMarks(e, at, end)) gain.gain.linearRampToValueAtTime(entryLevel(e, t, end), ctxAt(t));
    src.connect(gain);
    const fader = this.fader(e.track);
    if (!fader) return;
    gain.connect(fader);
    src.start(when, fileAt);
    src.stop(ctxAt(end));
    this.live.push({ src, gain });
  }

  close() {
    this.stop();
    void this.ctx?.close().catch(() => {});
    this.ctx = null;
  }
}

/** The mix under Play all, for the cut player's lifetime. `clips`: the clips' own sound is
 * heard (false while the recording plays in its place: no voice stems then either). */
export function useMixAudio(ep: string, items: PlayItem[], fps: number, clips = true): void {
  const itemsRef = useRef(items);
  itemsRef.current = items;
  const clipsRef = useRef(clips);
  clipsRef.current = clips;

  useEffect(() => {
    const e = new MixEngine((path) => api().fileUrl(ep, path));
    let plan: PlayEntry[] = [];
    let planKey = "";
    let total = 0;
    let mixSeen: unknown = null;
    let bedsSeen: unknown = null;
    let fxSeen: unknown = null;
    let voicesSeen: unknown = null;
    let clipsSeen: boolean | null = null;
    let duckSeen: unknown = null;
    let auditionSeen: unknown = null;
    let itemsSeen: PlayItem[] | null = null;
    let seekN: number | undefined;
    let want = false;
    let rate = 1;
    // every change of the store (the playhead moves it each frame while playing)
    const sync = () => {
      const s = store.get();
      const res = currentMix(s);
      const its = itemsRef.current;
      const open = s.viewer?.kind === "cut";
      let relay = false;
      const duck = s.mixDuck[statusKey(ep, s.pass)];
      const aud = s.audition && s.audition.ep === ep && s.audition.pass === s.pass ? s.audition : null;
      const clipsOn = clipsRef.current;
      if (res?.mix !== mixSeen || res?.beds !== bedsSeen || res?.fx !== fxSeen || res?.voices !== voicesSeen || clipsOn !== clipsSeen
          || its !== itemsSeen || duck !== duckSeen || aud !== auditionSeen) {
        auditionSeen = aud;
        voicesSeen = res?.voices;
        clipsSeen = clipsOn;
        mixSeen = res?.mix;
        bedsSeen = res?.beds;
        fxSeen = res?.fx;
        duckSeen = duck;
        itemsSeen = its;
        // the faders apply at once; changed items (or a changed cut) are laid again
        e.setGains(trackGains(res));
        // the items, and the places' ambience beds under them (looped, crossfaded at their runs' cuts)
        // and the shots' picked effects at their clips
        // and voices only's stems in place of their clips' own sound
        plan = [...(clipsOn ? voicePlan(its, res) : []), ...bedPlan(its, res?.beds, res?.mix ?? {}, fps), ...fxPlan(its, res?.fx, res?.mix ?? {}, fps),
                ...playPlan(its, aud ? auditionMix(res?.mix ?? {}, aud) : res?.mix ?? {}, fps)];
        total = totalDuration(its);
        e.setDucking(duckTracks(res, its, fps, duck, total));
        const key = JSON.stringify(plan);
        relay = key !== planKey;
        planKey = key;
        // decoded ahead of the first play
        if (open) for (const p of plan) void e.buffer(p.path);
      }
      if (s.cutPlay.seek?.n !== seekN) {
        seekN = s.cutPlay.seek?.n;
        relay = true;
      }
      const r = s.cutPlay.rate ?? 1;
      const playing = open && s.cutPlay.playing && r > 0;
      if (playing !== want || r !== rate) {
        want = playing;
        rate = r;
        relay = true;
      }
      if (!want) {
        if (e.running) e.stop();
        return;
      }
      if (!relay && e.running && Math.abs(e.now() - s.cutPlay.pos) > DRIFT && performance.now() - e.lastLay > RELAY_GAP_MS) relay = true;
      if (relay || !e.running) e.play(plan, total, s.cutPlay.pos, rate, trackGains(res));
    };
    sync();
    const off = store.subscribe(sync);
    return () => {
      off();
      e.close();
    };
  }, [ep, fps]);
}
