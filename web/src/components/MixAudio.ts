// Play all hears the mix: the items of the pass's mix played through Web Audio
// on the cut's clock (lib/mix's playPlan), each through its own gain (its dB
// and fades as gain automation) into its track's (the fader, mute and solo).
// It follows the store's cutPlay: started at the playhead on play, stopped on
// pause, laid again on a seek, a change of the mix or the cut, and when the
// video's clock and the audio's drift apart. The clips' own sound stays on the
// <video> elements (CutPlayer sets their volume from the dialogue fader).
// Left out for now: the ducking (the render computes it from the dialogue's
// level; the preview plays every track at its fader) and the volume points.

import { useEffect, useRef } from "react";
import { entryEnd, entryLevel, playPlan, trackGains, TRACKS, type PlayEntry } from "../lib/mix";
import { totalDuration, type PlayItem } from "../lib/playlist";
import { api } from "../host";
import { store } from "../store";
import { currentMix } from "../mixActions";
import type { MixTrack } from "../types";

/** seconds the audio may stray from the picture before it is laid again */
const DRIFT = 0.15;
/** and not more often than this (a clip's first frame can hold the picture a moment) */
const RELAY_GAP_MS = 600;

class MixEngine {
  private ctx: AudioContext | null = null;
  private tracks: Partial<Record<MixTrack, GainNode>> = {};
  private buffers = new Map<string, Promise<AudioBuffer | null>>();
  private live: { src: AudioBufferSourceNode; gain: GainNode }[] = [];
  /** the cut time playing at the context's `t0` */
  private pos0 = 0;
  private t0 = 0;
  private rate = 1;
  private gen = 0;
  running = false;
  lastLay = 0;

  constructor(private url: (path: string) => string) {}

  private context(): AudioContext | null {
    if (this.ctx) return this.ctx;
    const AC = typeof window !== "undefined" ? (window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext) : undefined;
    if (!AC) return null;
    this.ctx = new AC();
    for (const t of TRACKS) {
      const g = this.ctx.createGain();
      g.connect(this.ctx.destination);
      this.tracks[t] = g;
    }
    return this.ctx;
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
    for (const t of TRACKS) this.tracks[t]?.gain.setTargetAtTime(g[t], ctx.currentTime, 0.02);
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
    const ctxAt = (t: number) => this.t0 + (t - this.pos0) / this.rate;
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
    // its level now, then its fades as ramps
    const when = Math.max(ctx.currentTime, ctxAt(at));
    gain.gain.setValueAtTime(entryLevel(e, at, end), when);
    const marks = [e.start + e.fadeIn, end - e.fadeOut, end].filter((t) => t > at).sort((a, b) => a - b);
    for (const t of marks) gain.gain.linearRampToValueAtTime(entryLevel(e, Math.min(t, end), end), ctxAt(t));
    src.connect(gain);
    gain.connect(this.tracks[e.track]!);
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

/** The mix under Play all, for the cut player's lifetime. */
export function useMixAudio(ep: string, items: PlayItem[], fps: number): void {
  const itemsRef = useRef(items);
  itemsRef.current = items;

  useEffect(() => {
    const e = new MixEngine((path) => api().fileUrl(ep, path));
    let plan: PlayEntry[] = [];
    let planKey = "";
    let total = 0;
    let mixSeen: unknown = null;
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
      if (res?.mix !== mixSeen || its !== itemsSeen) {
        mixSeen = res?.mix;
        itemsSeen = its;
        // the faders apply at once; changed items (or a changed cut) are laid again
        e.setGains(trackGains(res));
        plan = playPlan(its, res?.mix ?? {}, fps);
        total = totalDuration(its);
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
