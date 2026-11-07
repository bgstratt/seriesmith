// A clip whose sound the cut replaces (cut.json's `audio`): Play all plays that sound on
// the dialogue track at the clip, placed as the export's clip_track places it, and the
// clip's own <video> stays muted.
import { describe, expect, it } from "vitest";
import { waveSource } from "../src/components/Waveform";
import { audioOf } from "../src/lib/audioSource";
import { sourcePlan, sourcedShots } from "../src/lib/mix";
import { buildPlaylist, type PlayItem } from "../src/lib/playlist";
import type { EpisodeStatus } from "../src/types";

function clip(over: Partial<PlayItem> = {}): PlayItem {
  return {
    shot: "sh070", index: 0, pass: "final", take: 4, mp4: "renders/sh070/sh070_t04.mp4", why: "", start: 10, dur: 4, inT: 0, outT: 4,
    trimIn: 0, trimOut: 0, total: null, audioIn: null, audioOut: null, fadeIn: 0, fadeOut: 0, dissolveIn: 0, dissolveOut: 0, ...over,
  };
}
const FILE = "renders/sh070/sh070_t02.mp4";
const sourced = (over = {}) => clip({ source: { path: FILE, start: 1.1, offset: 0, gain: 1, ...over } });

describe("sourcePlan", () => {
  it("plays the source from its start, over the clip, on the dialogue track", () => {
    expect(sourcePlan([sourced()])).toEqual([{
      id: "source:sh070", track: "dialogue", path: FILE, start: 10, end: 14, offset: 1.1, gain: 1, points: [], fadeIn: 0, fadeOut: 0, loop: false,
    }]);
  });

  it("a positive offset starts it later in the clip", () => {
    const [e] = sourcePlan([sourced({ offset: 0.5 })]);
    expect([e.start, e.end, e.offset]).toEqual([10.5, 14, 1.1]);
  });

  it("a negative offset eats into the source", () => {
    const [e] = sourcePlan([sourced({ offset: -0.5 })]);
    expect([e.start, e.end, e.offset]).toEqual([10, 14, 1.6]);
  });

  it("keeps its gain", () => {
    expect(sourcePlan([sourced({ gain: 2 })])[0].gain).toBe(2);
  });

  it("plays nothing for silence, its own sound, a missing picture, or an offset past the clip", () => {
    expect(sourcePlan([clip({ source: { path: null, start: 0, offset: 0, gain: 1 } })])).toEqual([]);
    expect(sourcePlan([clip()])).toEqual([]);
    expect(sourcePlan([clip({ mp4: null, source: { path: FILE, start: 0, offset: 0, gain: 1 } })])).toEqual([]);
    expect(sourcePlan([sourced({ offset: 5 })])).toEqual([]);
  });
});

describe("sourcedShots", () => {
  it("names the clips whose own sound is replaced, silence too", () => {
    expect(sourcedShots([clip({ shot: "a" }), sourced(), clip({ shot: "c", source: { path: null, start: 0, offset: 0, gain: 1 } })])).toEqual(["sh070", "c"]);
  });
});

describe("buildPlaylist", () => {
  function status(audio: unknown, audioFile: string | null, dub = false): EpisodeStatus {
    return {
      pass: "final", fps: 24,
      shots: [{
        shot: "sh070", seconds: 4,
        cut: { take: 4, picked: false, pass: "final", placeholder: false, usable: true, trim_in: 0, trim_out: 0, out: false, frames: 96, fps: 24,
               dissolve: 0, fade_in: 0, fade_out: 0, audio, audio_file: audioFile, ...(dub ? { audio_dub: true } : {}) },
        takes: [{ take: 4, status: "ok", has_video: true, mp4: "renders/sh070/sh070_t04.mp4", frames: 96, fps: 24 }],
      }],
    } as unknown as EpisodeStatus;
  }

  it("carries the replacement's file and placement", () => {
    const [it] = buildPlaylist(status({ source: "take", shot: "sh070", take: 2, pass: "final", start: 1.101, offset: -0.2, gain: 1.5 }, FILE));
    expect(it.source).toEqual({ path: FILE, start: 1.101, offset: -0.2, gain: 1.5 });
  });

  it("has no file for silence, and nothing for a clip's own sound", () => {
    expect(buildPlaylist(status({ source: "none" }, null))[0].source?.path).toBeNull();
    expect(buildPlaylist(status(null, null))[0].source).toBeNull();
  });

  it("plays a shot's dub, which is never the cut entry's own", () => {
    const st = status({ source: "file", path: "dub/sh070/sh070_t01.mp4" }, "dub/sh070/sh070_t01.mp4", true);
    expect(buildPlaylist(st)[0].source).toEqual({ path: "dub/sh070/sh070_t01.mp4", start: 0, offset: 0, gain: 1 });
    expect(audioOf(st.shots[0].cut)).toBeNull();
  });
});

describe("waveSource", () => {
  const st = { fps: 24, track: null } as unknown as EpisodeStatus;
  const take = { take: 4, audio: "renders/sh070/sh070_t04.mp4" } as never;

  it("draws the sound the cut plays in place of the clip's own", () => {
    expect(waveSource("E", sourced(), take, st, false, 40)).toMatchObject({ q: { path: FILE, start: 1.1, end: 5.1 } });
    expect(waveSource("E", sourced(), take, st, false, 40)?.lead).toBeUndefined();
  });

  it("a positive offset starts it into the clip, a negative one into the source", () => {
    const w = waveSource("E", sourced({ offset: 1 }), take, st, false, 40);
    expect([w?.q.start, w?.q.end, w?.lead]).toEqual([1.1, 4.1, 0.25]);
    expect(waveSource("E", sourced({ offset: -0.5 }), take, st, false, 40)?.q).toMatchObject({ start: 1.6, end: 5.6 });
  });

  it("draws nothing for silence, and its own sound with no replacement", () => {
    expect(waveSource("E", clip({ source: { path: null, start: 0, offset: 0, gain: 1 } }), take, st, false, 40)).toBeNull();
    expect(waveSource("E", clip(), take, st, false, 40)?.q.path).toBe("renders/sh070/sh070_t04.mp4");
  });
});
