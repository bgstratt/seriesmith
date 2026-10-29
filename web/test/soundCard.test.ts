// The Sound card: a shot's next take (the default, generate, clone, dub), what a dub is
// lip-synced to, and what the cut plays, in one place (the shot form's, the dialog's).
import { createElement } from "react";
import { renderToString } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { openSound, refreshEpisode } from "../src/actions";
import { SoundCard, SoundDialog } from "../src/components/SoundDialog";
import { setApi, setHost, type Host } from "../src/host";
import { createMockApi } from "../src/mock/mockApi";
import { initialState, statusKey, store } from "../src/store";
import type { ShotStatus } from "../src/types";

describe("the Sound card", () => {
  let EP: string;
  beforeEach(async () => {
    setHost({ on: () => () => {}, toast: () => {}, show: () => {} } as Host);
    const api = createMockApi(() => {}, { latency: 0 });
    setApi(api);
    EP = (await api.episodes())[0].ep;
    store.set(initialState());
    store.set({ ep: EP, pass: "proxy" });
    await refreshEpisode(EP, "proxy");
  });
  afterEach(() => store.set(initialState()));

  const patchShot = (shot: string, p: Partial<ShotStatus>) => store.set((s) => {
    const st = s.status[statusKey(EP, "proxy")]!;
    return { status: { ...s.status, [statusKey(EP, "proxy")]: { ...st, shots: st.shots.map((x) => (x.shot === shot ? { ...x, ...p } : x)) } } };
  });

  it("shows the next take, its dub, and the cut's sound together", () => {
    const shot = store.get().status[statusKey(EP, "proxy")]!.shots[0];
    patchShot(shot.shot, {
      sound: { mode: "dub", dub: { from: "dub", take: 1 }, label: "dub track 1", file: "dub/x.wav" },
      cut: { ...shot.cut, audio: { source: "none" }, audio_why: "silent" },
    });
    const html = renderToString(createElement(SoundCard, { shot: shot.shot }));
    for (const words of ["Next take", "Default", "Generate", "Clone", "Dub", "Dub to", "a dub track",
                         "keep the model", "In the cut", "silent", "its take", "Adjust"]) {
      expect(html).toContain(words);
    }
  });

  it("the shot form's card is the next take's alone", () => {
    const shot = store.get().status[statusKey(EP, "proxy")]!.shots[0];
    const html = renderToString(createElement(SoundCard, { shot: shot.shot, cut: false }));
    expect(html).toContain("Next take");
    expect(html).not.toContain("In the cut");
  });

  it("with the script's sound, no dub part; Replace audio opens it at the cut", () => {
    const shot = store.get().status[statusKey(EP, "proxy")]!.shots[0];
    const html = renderToString(createElement(SoundCard, { shot: shot.shot }));
    expect(html).not.toContain("Dub to");
    expect(html).toContain("In the cut");
    openSound([shot.shot], "cut");
    expect(store.get().soundAsk).toEqual({ shots: [shot.shot], focus: "cut" });
    expect(renderToString(createElement(SoundDialog))).toContain(`Sound · ${shot.shot}`);
  });
});

import { DubTracksSection, dubMissing, dubShots } from "../src/components/DubTracks";
import type { EpisodeStatus } from "../src/types";

describe("the Refs tab's dub tracks", () => {
  const st = (shots: Partial<ShotStatus>[]) =>
    ({ shots: shots.map((s) => ({ orphan: false, takes: [], cut: {}, ...s })) } as unknown as EpisodeStatus);
  it("lists the speaking shots and any with a dub; the speaking ones with none are missing", () => {
    const s = st([
      { shot: "sh010" },                                                   // silent: not listed
      { shot: "sh020", speaks: true },                                     // missing
      { shot: "sh030", speaks: true, dub_tracks: 2 },
      { shot: "sh040", dub_tracks: 1 },                                    // a dub track, no lines now
      { shot: "sh050", sound: { mode: "dub", dub: { from: "track" } } },
      { shot: "sh060", speaks: true, orphan: true },                       // gone from the script
    ]);
    expect(dubShots(s).map((x) => x.shot)).toEqual(["sh020", "sh030", "sh040", "sh050"]);
    expect(dubMissing(s)).toEqual(["sh020"]);
    const html = renderToString(createElement(DubTracksSection, { st: s }));
    for (const words of ["Dub tracks", "Generate missing", "no dub track yet", "2 dub tracks", "dub · "]) {
      expect(html).toContain(words);
    }
    expect(renderToString(createElement(DubTracksSection, { st: st([{ shot: "sh010" }]) }))).toBe("");
  });
});
