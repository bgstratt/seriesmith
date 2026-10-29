// Takes from outside (docs/API.md, "Takes from outside"): a video file or another
// shot's take as a shot's take. Onto a clip or a shot's row: imported or copied
// in, and picked. Between two clips: a new shot in the script there first (a
// take: its shot's lines, its length; a file: the shot form, prefilled), the
// take into it, and the clip moved to where it was dropped.

import { afterAuthoredWrite, openShotForm, pickTake, refreshEpisode, select, uploadRef } from "./actions";
import { errText } from "./api";
import { moveClip } from "./cutActions";
import { api, host } from "./host";
import { tn } from "./lib/format";
import { keyframeNote, keyframeRefId } from "./lib/keyframes";
import { fileKindProblem } from "./lib/lookback";
import { seriesDefaultTarget, shotTarget } from "./lib/targets";
import { anchorAt, gapAfter, insertedShot, videoFileProblem, type TakeDrag } from "./lib/takeDrop";
import { statusKey, store, uploadKey } from "./store";
import type { ShotStatus } from "./types";

const set = store.set;
const get = store.get;

/** Where a shot's take upload shows (uploads[...], as a ref's does). */
export function takeUploadKey(shot: string): string {
  return uploadKey(`take:${shot}`, null);
}

function putUpload(key: string, u: { name: string; sent: number; total: number; error?: string } | null) {
  set((s) => {
    const uploads = { ...s.uploads };
    if (u) uploads[key] = u;
    else delete uploads[key];
    return { uploads };
  });
}

export function dismissTakeUpload(shot: string) {
  putUpload(takeUploadKey(shot), null);
}

function cutShots(): ShotStatus[] {
  const s = get();
  return (s.ep && s.status[statusKey(s.ep, s.pass)]?.shots) || [];
}

/** A video file as `shot`'s new take in the current pass, picked. The take's
 * number, or null (the reason is on the shot's upload line). */
/** png, jpg or webp: what a keyframe can be */
export function isPicture(file: { name: string }): boolean {
  return fileKindProblem(file, "image") === "";
}

export async function importTakeFile(shot: string, file: File, pick = true): Promise<number | null> {
  const { ep, pass } = get();
  if (!ep) return null;
  const key = takeUploadKey(shot);
  const problem = videoFileProblem(file);
  if (problem) {
    putUpload(key, { name: file.name, sent: 0, total: file.size, error: problem });
    return null;
  }
  const cur = get().uploads[key];
  if (cur && !cur.error) return null;                       // one at a time per shot
  putUpload(key, { name: file.name, sent: 0, total: file.size });
  try {
    const r = await api().uploadTake({ ep, pass, shot, file, name: file.name, pick }, (sent, total) => {
      const u = get().uploads[key];
      if (u && !u.error) putUpload(key, { ...u, sent, total: total || u.total });
    });
    putUpload(key, null);
    host().toast("success", `${shot}: ${file.name} imported`,
      `${tn(r.take)}${r.picked ? " is in the cut" : r.why ? `: ${r.why}` : ""}${r.sidecar?.converted ? " (converted to H.264)" : ""}.`);
    await refreshEpisode(ep, pass);
    select(shot, r.take);
    return r.take;
  } catch (e) {
    putUpload(key, { name: file.name, sent: 0, total: file.size, error: errText(e) });
    return null;
  }
}

/** The file picker's way to the same. */
export function pickTakeFile(shot: string) {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = "video/*,.mkv,.avi";
  input.onchange = () => {
    const f = input.files?.[0];
    if (f) void importTakeFile(shot, f);
  };
  input.click();
}

/** A dragged take onto `shot`'s clip: its own shot's is a pick; another's is
 * copied in and picked. */
export async function dropTakeOnto(shot: string, from: TakeDrag): Promise<void> {
  const { ep, pass } = get();
  if (!ep || from.ep !== ep) {
    host().toast("warn", "Another episode's take", "Only this episode's takes can be dropped here.");
    return;
  }
  if (from.shot === shot) {
    await pickTake(shot, from.take, from.pass !== pass ? from.pass : null);
    return;
  }
  try {
    const r = await api().copyTake({ ep, pass, shot, from_shot: from.shot, take: from.take, from_pass: from.pass, pick: true });
    host().toast("success", `${from.shot} ${tn(from.take)} into ${shot}`,
      `${tn(r.take)} of ${shot}${r.picked ? ", in the cut" : r.why ? `: ${r.why}` : ""}.`);
    await refreshEpisode(ep, pass);
    select(shot, r.take);
  } catch (e) {
    host().toast("error", `Couldn't copy ${from.shot} ${tn(from.take)} into ${shot}`, errText(e));
  }
}

/** A dragged take between two clips: a new shot in the script there (its
 * lines the take's shot's, its length the take's), the take copied into it and
 * picked, the clip where it was dropped. */
export async function dropTakeBetween(gap: number, from: TakeDrag): Promise<void> {
  const { ep, pass } = get();
  if (!ep || from.ep !== ep) {
    host().toast("warn", "Another episode's take", "Only this episode's takes can be dropped here.");
    return;
  }
  const cut = cutShots();
  const anchor = anchorAt(cut, gap);
  const left = gap > 0 ? cut[gap - 1].shot : null;
  const srcShot = get().status[statusKey(ep, from.pass)]?.shots.find((s) => s.shot === from.shot);
  const srcTake = srcShot?.takes.find((t) => t.take === from.take);
  const seconds = from.seconds ?? (srcTake?.frames && srcTake.fps ? srcTake.frames / srcTake.fps : srcShot?.seconds ?? 3);
  try {
    const doc = await api().source(ep, "script");
    const made = anchor && insertedShot(doc.text, doc.shots, from.shot, anchor, seconds,
      `${from.shot} ${tn(from.take)}${from.pass !== pass ? ` (${from.pass})` : ""}, dropped on the timeline`);
    if (!made) {
      host().toast("error", "Nowhere to put it", `${from.shot} isn't in the script, or there's no shot beside the drop.`);
      return;
    }
    const r = await api().putSource({ ep, file: "script", text: made.text, base_hash: doc.hash, rebuild: true });
    afterAuthoredWrite(r.build);
    if (r.build && !r.build.ok) return;                     // the build said why
    const c = await api().copyTake({ ep, pass, shot: made.id, from_shot: from.shot, take: from.take, from_pass: from.pass, pick: true });
    await refreshEpisode(ep, pass);
    await moveClip(made.id, gapAfter(cutShots(), left));
    select(made.id, c.take);
    host().toast("success", `${made.id} added`, `A new shot with ${from.shot}'s lines and ${from.shot} ${tn(from.take)} as its take.`);
  } catch (e) {
    host().toast("error", "Couldn't add the shot", errText(e));
  }
}

/** A video file between two clips: the shot form there, its length the file's;
 * Save makes the shot, imports the file as its take and puts the clip there. */
/** A file dropped on a shot's row or clip: a video becomes a take of it (in the
 * cut), a picture its first keyframe (live at once, as an upload in Refs is). */
export async function dropFileOnto(shot: string, file: File): Promise<void> {
  if (isPicture(file)) await keyframeFromFile(shot, file);
  else await importTakeFile(shot, file);
}

async function keyframeFromFile(shot: string, file: File) {
  const ref = keyframeRefId(shot, "first");
  if (await uploadRef(ref, null, file, true)) {
    // a model that reads no keyframes keeps the picture, unused
    const s = store.get();
    const st = s.ep ? s.status[statusKey(s.ep, s.pass)] : undefined;
    const target = shotTarget(st?.shots.find((x) => x.shot === shot), seriesDefaultTarget(s.targets, st));
    const note = keyframeNote(s.targets, target);
    if (note) host().toast("warn", `${shot}'s model reads no keyframe`, `The picture is ${shot}'s first keyframe, but keyframes are ${note}.`);
    return;
  }
  // the slot's error shows in the Refs tab; here, a toast
  const key = uploadKey(ref, null);
  const err = store.get().uploads[key]?.error;
  if (err) {
    host().toast("error", `${shot}: ${file.name} isn't its first keyframe`, err);
    store.set((st) => {
      const uploads = { ...st.uploads };
      delete uploads[key];
      return { uploads };
    });
  }
}

export async function dropFileBetween(gap: number, file: File): Promise<void> {
  // a picture: the new shot's first keyframe, its length the form's
  const picture = isPicture(file);
  const problem = picture ? "" : videoFileProblem(file);
  if (problem) {
    host().toast("warn", "Not a video or a picture", problem);
    return;
  }
  const cut = cutShots();
  const anchor = anchorAt(cut, gap);
  const seconds = picture ? null : await videoSeconds(file);
  openShotForm({
    shot: null,
    after: anchor && "after" in anchor ? anchor.after : null,
    before: anchor && "before" in anchor ? anchor.before : null,
    file, dur: seconds ? String(Math.round(seconds * 10) / 10) : null,
    left: gap > 0 ? cut[gap - 1].shot : null,
  });
}

/** After the shot form saved a new shot that came with a file: the file as its
 * take, and the clip where it was dropped. */
export async function finishDroppedFile(shot: string, file: File, left: string | null): Promise<void> {
  if (isPicture(file)) {
    await keyframeFromFile(shot, file);
    const { ep, pass } = store.get();
    if (ep) await refreshEpisode(ep, pass);         // the new shot in the status, to be moved
  } else if ((await importTakeFile(shot, file)) == null) return;
  await moveClip(shot, gapAfter(cutShots(), left));
}

/** A video file's length in seconds, read by the browser (null when it can't). */
export function videoSeconds(file: File): Promise<number | null> {
  return new Promise((resolve) => {
    const v = document.createElement("video");
    const url = URL.createObjectURL(file);
    const done = (s: number | null) => {
      URL.revokeObjectURL(url);
      resolve(s);
    };
    v.preload = "metadata";
    v.onloadedmetadata = () => done(Number.isFinite(v.duration) && v.duration > 0 ? v.duration : null);
    v.onerror = () => done(null);
    v.src = url;
  });
}
