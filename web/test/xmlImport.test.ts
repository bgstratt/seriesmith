// @vitest-environment happy-dom
//
// The new episode wizard's "From an edit (FCP7 XML)": the choice opens the import panel,
// a path (or a picked file) is read in a dry run whose summary is shown, the footage
// option goes with it, and Import makes the show and opens it.
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { openWizard } from "../src/actions";
import { NewEpisodeWizard } from "../src/components/NewEpisodeWizard";
import { setApi, setHost, type Host } from "../src/host";
import { MEDIA_CHOICES, doneMessage, handlesOf, summaryLines } from "../src/lib/xmlImport";
import { createMockApi } from "../src/mock/mockApi";
import { initialState, store } from "../src/store";
import type { XmlImportRequest, XmlImportSummary, XmlImportUpload } from "../src/types";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const SUMMARY: XmlImportSummary = {
  sequence: "The Lighthouse (rough cut)", title: "The Lighthouse (rough cut)", show: "The_Lighthouse_rough_cut",
  episode: "ep01", in_show: false, from: null,
  ep:"C:\\Shows\\The_Lighthouse_rough_cut\\ep01", fps: 23.976, size: [1920, 1080], media: "handles", handles: 1,
  shots: 5, black: 1, takes: 4, missing: ["sh050"], sequences: ["Arrival", "sq02"], audio_items: 3, hits: 1,
  tracks: ["effects", "music", "music2"], proxies: [], unplayable: [], warnings: ["V2: Logo bug at 00:00:00.000 isn't imported"],
  clips: [{ shot: "sh050", name: "Pickup", source: null, dur: 1, trim_in: 0, trim_out: 0, missing: "its file isn't there" }],
};

const wait = (ms: number) => act(() => new Promise<void>((r) => setTimeout(r, ms)));

function type(input: HTMLInputElement, value: string) {
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

describe("what the import says", () => {
  it("offers the three ways in, handles first", () => {
    expect(MEDIA_CHOICES.map((c) => c.value)).toEqual(["handles", "reference", "proxies"]);
  });
  it("reads the handles box", () => {
    expect(handlesOf("1")).toBe(1);
    expect(handlesOf(" 0.5 ")).toBe(0.5);
    expect(handlesOf("0")).toBe(0);
    for (const bad of ["", "x", "-1", "61"]) expect(handlesOf(bad)).toBeNull();
  });
  it("sums it up", () => {
    expect(summaryLines(SUMMARY)).toEqual([
      "The Lighthouse (rough cut): 5 shots (1 black, for gaps), 23.976 fps, 1920×1080",
      "4 takes to make (1 s handles); no file for sh050",
      "3 sounds in the mix (effects, music, music2), 1 hit",
      "2 sequences: Arrival, sq02",
    ]);
    const prox = summaryLines({ ...SUMMARY, media: "proxies", handles: null, proxies: ["sh010", "sh020"] });
    expect(prox[1]).toBe("4 takes to make; no file for sh050");
    expect(prox).toContain("Proxies made for sh010, sh020");
    expect(summaryLines({ ...SUMMARY, media: "reference", unplayable: ["sh010"] }))
      .toContain("Won't play in the editor: sh010 (not H.264)");
    expect(doneMessage({ ...SUMMARY, jobs: ["a", "b"] })).toContain("2 jobs in Jobs");
  });
});

describe("the wizard's From an edit", () => {
  let root: Root;
  let host: HTMLDivElement;
  let sent: (XmlImportRequest | XmlImportUpload)[];
  let toasts: string[];
  let EP: string;

  beforeEach(async () => {
    toasts = [];
    sent = [];
    setHost({ on: () => () => {}, toast: (_k: string, title: string) => void toasts.push(title), show: () => {} } as unknown as Host);
    const api = createMockApi(() => {}, { latency: 0 });
    EP = (await api.episodes())[0].ep;
    const answer = async (req: XmlImportRequest | XmlImportUpload): Promise<XmlImportSummary> => {
      sent.push(req);
      const media = req.media ?? "handles";
      return { ...SUMMARY, media, proxies: media === "proxies" ? ["sh010"] : [],
        ...(req.dry_run ? {} : { ep: EP, jobs: ["j1", "j2"], build: { ok: true, passes: {} } }) } as XmlImportSummary;
    };
    api.importXml = answer;
    api.uploadXml = answer;
    setApi(api);
    store.set(initialState());
    store.set({ config: await api.getConfig() });
    openWizard({ parent: "C:\\Shows", newSeries: true });
    host = document.createElement("div");
    document.body.appendChild(host);
    root = createRoot(host);
    act(() => root.render(createElement(NewEpisodeWizard)));
  });

  afterEach(() => {
    act(() => root.unmount());
    host.remove();
  });

  it("is a choice for a new series, and imports what the dry run showed", async () => {
    expect(host.querySelector("#sm-xml-import")).toBeNull();
    act(() => (host.querySelector("#sm-wizard-xml") as HTMLButtonElement).click());
    expect(host.querySelector("#sm-xml-import")).not.toBeNull();
    const go = () => host.querySelector("#sm-xml-go") as HTMLButtonElement;
    expect(go().disabled).toBe(true);                       // nothing read yet

    type(host.querySelector("#sm-xml-path") as HTMLInputElement, "C:\\Edits\\cut.xml");
    await wait(400);
    expect(sent).toEqual([{ parent: "C:\\Shows", media: "handles", handles: 1, name: null, in_show: false,
      dry_run: true, path: "C:\\Edits\\cut.xml" }]);
    expect(host.querySelector("#sm-xml-summary")!.textContent).toContain("5 shots (1 black, for gaps)");
    expect(host.querySelector("#sm-xml-summary")!.textContent).toContain("sh050 (Pickup): its file isn't there");

    // the footage option asks again
    act(() => (host.querySelector('input[value="proxies"]') as HTMLInputElement).click());
    await wait(400);
    expect(sent.at(-1)).toMatchObject({ media: "proxies", dry_run: true });
    expect(host.querySelector("#sm-xml-summary")!.textContent).toContain("Proxies made for sh010");
    expect(host.querySelector("#sm-xml-handles")).toBeNull();      // handles are the first option's

    act(() => go().click());
    await wait(50);
    expect(sent.at(-1)).toMatchObject({ media: "proxies", dry_run: false, path: "C:\\Edits\\cut.xml" });
    expect(toasts).toContain("Imported The Lighthouse (rough cut)");
    expect(store.get().wizard).toBeNull();
    expect(store.get().ep).toBe(EP);
  });

  it("a picked file is uploaded", async () => {
    act(() => (host.querySelector("#sm-wizard-xml") as HTMLButtonElement).click());
    const input = host.querySelector("#sm-xml-file") as HTMLInputElement;
    const file = new File(["<xmeml/>"], "cut.xml", { type: "text/xml" });
    Object.defineProperty(input, "files", { value: [file] });
    act(() => { input.dispatchEvent(new Event("change", { bubbles: true })); });
    await wait(400);
    expect(sent).toHaveLength(1);
    expect(sent[0]).toMatchObject({ filename: "cut.xml", dry_run: true, media: "handles" });
    expect((sent[0] as XmlImportUpload).file).toBe(file);
  });

  it("is a choice for a new episode too: the edit is the show's next episode", async () => {
    act(() => openWizard({ parent: "C:\\Shows\\Lighthouse", newSeries: false }));
    expect(host.querySelector("#sm-xml-import")).toBeNull();
    act(() => (host.querySelector("#sm-wizard-xml") as HTMLButtonElement).click());
    expect(host.textContent).toContain("New episode from an edit");
    type(host.querySelector("#sm-xml-path") as HTMLInputElement, "C:\\Edits\\cut.xml");
    await wait(400);
    expect(sent.at(-1)).toMatchObject({ parent: "C:\\Shows\\Lighthouse", in_show: true, dry_run: true });
  });

  it("opens on the edit when asked to (the episode browser's Import…)", async () => {
    act(() => openWizard({ parent: "C:\\Shows", newSeries: true, from: "xml" }));
    expect(host.querySelector("#sm-xml-import")).not.toBeNull();
    expect(host.textContent).toContain("New series from an edit");
  });
});
