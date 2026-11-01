// Play all's mix engine (MixAudio) on a fake AudioContext that keeps each gain's
// automation: the ducking it lays on each track is the curve times the track's
// duck_db (regions applied), on the cut's clock from the play position, at any
// rate; an item's level follows its volume points as the export's render does.
import { describe, expect, it } from "vitest";
import { MixEngine } from "../src/components/MixAudio";
import { duckTracks, playPlan, pointsDb, type DuckCurve } from "../src/lib/mix";
import type { PlayItem } from "../src/lib/playlist";
import type { Mix, MixTrack } from "../src/types";

type Ev = { kind: "set" | "ramp"; v: number; t: number };

/** An AudioParam's events, and its value at a time (set holds, ramps are linear). */
class Param {
  value = 1;
  ev: Ev[] = [];
  setValueAtTime(v: number, t: number) {
    this.ev.push({ kind: "set", v, t });
  }
  linearRampToValueAtTime(v: number, t: number) {
    this.ev.push({ kind: "ramp", v, t });
  }
  setTargetAtTime(v: number) {
    this.value = v;
  }
  cancelScheduledValues() {
    this.ev = [];
  }
  at(t: number): number {
    let v = this.value;
    let vt = 0;
    for (const e of this.ev) {
      if (e.t <= t) {
        v = e.v;
        vt = e.t;
        continue;
      }
      if (e.kind === "ramp") return v + ((t - vt) / (e.t - vt)) * (e.v - v);
      break;
    }
    return v;
  }
}

class Node {
  gain = new Param();
  playbackRate = new Param();
  connect() {}
  disconnect() {}
}

class FakeContext {
  currentTime = 0;
  state = "running";
  destination = {};
  gains: Node[] = [];
  createGain() {
    const n = new Node();
    this.gains.push(n);
    return n;
  }
  resume() {
    return Promise.resolve();
  }
  close() {
    return Promise.resolve();
  }
}

function clip(shot: string, index: number, start: number, dur: number): PlayItem {
  return {
    shot, index, pass: "final", take: 1, mp4: `${shot}.mp4`, why: "", start, dur, inT: 0, outT: dur, trimIn: 0, trimOut: 0,
    total: null, audioIn: null, audioOut: null, fadeIn: 0, fadeOut: 0, dissolveIn: 0, dissolveOut: 0,
  };
}

const ITEMS = [clip("sh010", 0, 0, 4), clip("sh020", 1, 4, 4)];
const TOTAL = 8;
// someone speaks from 1 s, eased in and out (a value per 0.05 s)
const CURVE: DuckCurve = { step: 0.05, curve: Array.from({ length: 161 }, (_, i) => (i < 20 ? 0 : i < 60 ? Math.min(1, (i - 20) / 6) : Math.max(0, 1 - (i - 60) / 30))) };
const speech = (t: number) => {
  const k = t / CURVE.step;
  const i = Math.floor(k);
  return CURVE.curve[i] + ((CURVE.curve[i + 1] ?? CURVE.curve[i]) - CURVE.curve[i]) * (k - i);
};

function engine() {
  let ctx!: FakeContext;
  const AC = function () {
    ctx = new FakeContext();
    return ctx;
  } as unknown as new () => AudioContext;
  const e = new MixEngine((p) => p, AC);
  return { e, ctx: () => ctx };
}

/** each track's ducking gain: the second gain made for it (the fader is the first) */
const duckGain = (ctx: FakeContext, track: MixTrack) => ctx.gains[["dialogue", "effects", "ambience", "music"].indexOf(track) * 2 + 1].gain;

describe("Play all's ducking", () => {
  const gains = { dialogue: 1, effects: 1, ambience: 1, music: 1 };

  it("dips music and ambience by their depth times the curve, from the play position", () => {
    const { e, ctx } = engine();
    const res = { mix: {} as Mix, series: {}, defaults: { duck_db: { effects: 0, ambience: -6, music: -9 } } };
    e.setDucking(duckTracks(res, ITEMS, 24, CURVE, TOTAL));
    e.play([], TOTAL, 0.5, 1, gains);
    const c = ctx();
    // the context's clock: the cut's 0.5 s plays at 0.03
    const ctxAt = (t: number) => 0.03 + (t - 0.5);
    const db = (track: MixTrack, t: number) => 20 * Math.log10(duckGain(c, track).at(ctxAt(t)));
    // on each step of the curve: exactly its dB
    for (const t of [0.5, 1, 1.1, 1.3, 2, 3, 3.35, 4, 5, 7.9]) {
      expect(db("music", t)).toBeCloseTo(-9 * speech(t), 4);
      expect(db("ambience", t)).toBeCloseTo(-6 * speech(t), 4);
    }
    // between steps (ramped linear in gain), within a few hundredths of a dB; every 10 ms of the cut
    for (let t = 0.5; t < TOTAL; t += 0.01) {
      expect(Math.abs(db("music", t) + 9 * speech(t))).toBeLessThan(0.05);
      expect(Math.abs(db("ambience", t) + 6 * speech(t))).toBeLessThan(0.05);
    }
    // under speech, the music is 9 dB down; effects and dialogue never move
    expect(20 * Math.log10(duckGain(c, "music").at(ctxAt(2.5)))).toBeCloseTo(-9, 3);
    expect(duckGain(c, "effects").at(ctxAt(2.5))).toBe(1);
    expect(duckGain(c, "dialogue").at(ctxAt(2.5))).toBe(1);
  });

  it("is laid again on a seek, at 2x, and with a region (score forward, the dialogue lowered)", () => {
    const { e, ctx } = engine();
    const mix: Mix = { regions: [{ from: { shot: "sh010", frame: 48 }, to: { shot: "sh020", frame: 0 }, music_duck_db: 0, dialogue_db: -4 }] };
    e.setDucking(duckTracks({ mix, series: {} }, ITEMS, 24, CURVE, TOTAL));
    e.play([], TOTAL, 1.5, 2, gains);
    const c = ctx();
    const ctxAt = (t: number) => 0.03 + (t - 1.5) / 2;
    expect(20 * Math.log10(duckGain(c, "music").at(ctxAt(1.8)))).toBeCloseTo(-9 * speech(1.8), 3);
    // 2 s to 4 s: no dip on the music, the dialogue 4 dB down (ramped over a step at the edges)
    expect(duckGain(c, "music").at(ctxAt(2.5))).toBeCloseTo(1, 6);
    expect(20 * Math.log10(duckGain(c, "dialogue").at(ctxAt(3)))).toBeCloseTo(-4, 4);
    expect(duckGain(c, "dialogue").at(ctxAt(4.5))).toBeCloseTo(1, 6);
    // nothing before the play position is laid
    expect(duckGain(c, "music").ev.every((x) => x.t >= 0.03 - 1e-9)).toBe(true);
  });

  it("an item's level follows its volume points", async () => {
    const { e, ctx } = engine();
    const mix: Mix = {
      items: [{
        id: "m01", track: "music", path: "m.wav", in: { shot: "sh010", frame: 0 }, out: { shot: "sh020", frame: 48 }, gain_db: -2,
        points: [{ at: { shot: "sh010", frame: 24 }, db: -10 }, { at: { shot: "sh020", frame: 24 }, db: 4 }],
      }],
    };
    const plan = playPlan(ITEMS, mix, 24);
    // a decoded buffer, as decodeAudioData would give
    const buf = { duration: 30 } as AudioBuffer;
    const c0 = (e as unknown as { context(): FakeContext }).context();
    const src = { buffer: null, playbackRate: new Param(), loop: false, connect() {}, disconnect() {}, start() {}, stop() {} };
    (c0 as unknown as { createBufferSource(): unknown }).createBufferSource = () => src;
    (e as unknown as { buffers: Map<string, Promise<AudioBuffer>> }).buffers.set("m.wav", Promise.resolve(buf));
    e.play(plan, TOTAL, 0, 1, gains);
    await Promise.resolve();
    await Promise.resolve();
    const c = ctx();
    const g = c.gains[c.gains.length - 1].gain;
    const pts = plan[0].points;
    for (const t of [0.2, 1, 2, 3.3, 4.1, 5, 5.5, 6.9]) {
      const want = -2 + pointsDb(pts, t);
      expect(Math.abs(20 * Math.log10(g.at(0.03 + t)) - want)).toBeLessThan(0.05);
    }
  });
});
