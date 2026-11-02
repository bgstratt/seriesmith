// An edit made elsewhere (an FCP7 XML from Premiere, Resolve or Final Cut 7) into a new
// show: the choices the wizard offers and what it says of the answer
// (POST /seriesmith/import/xml; seriesmith/xmlimport.py, docs/IMPORT_XML.md).

import type { XmlImportMedia, XmlImportSummary } from "../types";

export const MEDIA_CHOICES: { value: XmlImportMedia; label: string; help: string }[] = [
  { value: "handles", label: "Used part + handles",
    help: "Each clip's span of its source and a little either side, as H.264 at master quality: small, plays everywhere, the trims can still move." },
  { value: "reference", label: "Reference in place",
    help: "Each source whole, as it is: hard-linked where the drive allows (no second copy), else copied. Not re-encoded, so a ProRes or HEVC source won't play in the editor." },
  { value: "proxies", label: "Reference in place + playable proxies",
    help: "As Reference in place, and each source the editor can't play gets an H.264 proxy, made once on the queue. The editor plays the proxy; the export cuts from the original." },
];

/** The handles box's seconds, or null when it isn't a number 0 to 60. */
export function handlesOf(text: string): number | null {
  const v = Number(text.trim());
  return text.trim() !== "" && Number.isFinite(v) && v >= 0 && v <= 60 ? v : null;
}

/** The summary's headline: what the import makes. */
export function summaryLines(s: XmlImportSummary): string[] {
  const n = (k: number, one: string, many = `${one}s`) => `${k} ${k === 1 ? one : many}`;
  const lines = [
    `${s.sequence}: ${n(s.shots, "shot")}${s.black ? ` (${s.black} black, for gaps)` : ""}, `
      + `${s.fps} fps, ${s.size[0]}×${s.size[1]}`,
    `${n(s.takes, "take")} to make${s.media === "handles" && s.handles != null ? ` (${s.handles} s handles)` : ""}`
      + (s.missing.length ? `; no file for ${s.missing.join(", ")}` : ""),
  ];
  if (s.audio_items || s.hits) {
    lines.push(`${n(s.audio_items, "sound")} in the mix${s.tracks.length ? ` (${s.tracks.join(", ")})` : ""}`
      + (s.hits ? `, ${n(s.hits, "hit")}` : ""));
  }
  if (s.sequences.length > 1) lines.push(`${n(s.sequences.length, "sequence")}: ${s.sequences.join(", ")}`);
  if (s.proxies.length) lines.push(`Proxies made for ${s.proxies.join(", ")}`);
  if (s.unplayable.length) lines.push(`Won't play in the editor: ${s.unplayable.join(", ")} (not H.264)`);
  return lines;
}

/** What the toast says once it's made: the episode, and that the media is on its way. */
export function doneMessage(s: XmlImportSummary): string {
  const jobs = s.jobs?.length ?? 0;
  return `${s.ep}\n${summaryLines(s).slice(0, 2).join("\n")}`
    + (jobs ? `\nThe footage is being made: ${jobs} job${jobs === 1 ? "" : "s"} in Jobs; each shot's take appears as it's done.` : "")
    + (s.build && !s.build.ok ? "\nThe build failed: open the script and check it." : "");
}
