// Files dropped on an add button (+ Character, + Place, + Voice...): a new entry in the series
// config for each, with a made-up name, the file its live picture or voice sample.

import type { DragEvent } from "react";
import { afterAuthoredWrite, loadRefs, uploadRef } from "./actions";
import { api, host } from "./host";
import { filesFromDrag } from "./lib/dropped";
import { dragHasFiles, fileKindProblem } from "./lib/lookback";
import { blockOf, droppedEntries, isOnePicture, refIdOf, refsPrefix, serialize, setPath, type CardKind, type Raw } from "./lib/seriesForm";
import { store } from "./store";

/** What makes an element take dropped files, lit (`data-over`) while they're over it. */
export function fileDrop(take: (files: Promise<File[]>) => void) {
  return {
    onDragOver: (e: DragEvent<HTMLElement>) => {
      if (!dragHasFiles(e.dataTransfer)) return;
      e.preventDefault();
      e.stopPropagation();
      e.dataTransfer.dropEffect = "copy";
      e.currentTarget.dataset.over = "1";
    },
    onDragLeave: (e: DragEvent<HTMLElement>) => { delete e.currentTarget.dataset.over; },
    onDrop: (e: DragEvent<HTMLElement>) => {
      delete e.currentTarget.dataset.over;
      if (!dragHasFiles(e.dataTransfer)) return;
      e.preventDefault();
      e.stopPropagation();
      take(filesFromDrag(e.dataTransfer));
    },
  };
}

/** A picture's size, or nulls when the browser can't read it. */
async function pictureSize(file: File): Promise<[number | null, number | null]> {
  try {
    const bitmap = await createImageBitmap(file);
    const size: [number, number] = [bitmap.width, bitmap.height];
    bitmap.close();
    return size;
  } catch {
    return [null, null];
  }
}

/** One new `kind` per usable file, in filename order, its file made live. */
export async function addFromFiles(kind: CardKind, found: Promise<File[]>): Promise<void> {
  const ep = store.get().ep;
  if (!ep) return;
  const want = kind === "voice" ? "audio" : "image";
  const files = (await found).filter((f) => fileKindProblem(f, want) === "")
    .sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: "base" }));
  if (!files.length) {
    host().toast("warn", kind === "voice" ? "Not a sound file" : "Not a picture",
      kind === "voice" ? "Drop a wav, mp3, flac, ogg or m4a." : "Drop a png, jpg or webp.");
    return;
  }
  try {
    const sizes = kind === "character" ? await Promise.all(files.map(pictureSize)) : [];
    const cur = await api().source(ep, "series");
    const raw = JSON.parse(cur.text) as Raw;
    const made = droppedEntries(raw, kind, files.map((_, i) => kind === "character" && isOnePicture(...sizes[i])), refsPrefix(raw));
    const next = made.reduce((r, m) => setPath(r, [blockOf(kind), m.id], m.entry), raw);
    const r = await api().putSource({ ep, file: "series", text: serialize(next, cur.text), base_hash: cur.hash, rebuild: true });
    afterAuthoredWrite(r.build);
    await loadRefs(ep);
    let failed = 0;
    for (let i = 0; i < made.length; i += 1) {
      if (!await uploadRef(refIdOf(kind, made[i].id), kind === "character" ? "sheet" : null, files[i], true)) failed += 1;
    }
    await loadRefs(ep);
    const names = made.map((m) => m.entry.name).join(", ");
    if (failed) host().toast("error", `${failed} of ${made.length} files weren't taken`, `Added: ${names}. The Refs tab says why on each.`);
    else host().toast("success", `Added ${names}`, "Rename them and describe them on their cards.");
  } catch (e) {
    host().toast("error", "Couldn't add them", (e as Error).message);
  }
}
