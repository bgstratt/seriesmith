import { useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  cancelTake, clearRef, closeMenu, copyText, discardTake, generateKeyframe, keyframeFromTake, loadRefs, openClipAudio,
  openIssue,
  keepUpscale, openInspector, openRedo, openSidecar, openViewer, pickTake, playAll, removeUpscale, requestRender, openShotForm, showInScript, showMissingRefs,
  upscaleTake, postTake, removePost, openFrameUse, refocusAfterMenu, makeFinalsFromDrafts, renderSelected,
  generateDubTracks, openSound, setSound,
} from "../actions";
import { pickTakeFile } from "../takeActions";
import { clearClipAudio, nudgeClip, setTrims, toggleFlag, toggleLock, toggleOut } from "../cutActions";
import { audioOf, audioWhy } from "../lib/audioSource";
import { absPath, tn } from "../lib/format";
import { cutNeighbour, keyframeNote, keyframeRefId } from "../lib/keyframes";
import { missingOf } from "../lib/missingRefs";
import { shotTarget } from "../lib/targets";
import { dubBlock, dubTrackBlock } from "../lib/readiness";
import { statusKey, useApp } from "../store";
import { useTargets } from "./Targets";

/** The thumbnail context menu, the same in the bin, the timeline and the viewer strip. */
export function ContextMenu() {
  const menu = useApp((s) => s.menu);
  const ep = useApp((s) => s.ep);
  const curPass = useApp((s) => s.pass);
  const st = useApp((s) => (s.ep && s.menu ? s.status[statusKey(s.ep, s.menu.pass)] : undefined));
  const cutSt = useApp((s) => (s.ep ? s.status[statusKey(s.ep, s.pass)] : undefined));
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);
  const { list: targets, seriesDefault } = useTargets();
  const refs = useApp((s) => (s.ep ? s.refs[s.ep] : undefined));
  const multi = useApp((s) => s.multi);
  const noVoice = dubTrackBlock(targets);

  useLayoutEffect(() => {
    if (!menu || !ref.current) return setPos(null);
    const r = ref.current.getBoundingClientRect();
    setPos({
      left: Math.max(4, Math.min(menu.x, window.innerWidth - r.width - 4)),
      top: Math.max(4, Math.min(menu.y, window.innerHeight - r.height - 4)),
    });
  }, [menu]);

  useEffect(() => {
    if (!menu) return;
    const down = (e: Event) => {
      if (ref.current && !ref.current.contains(e.target as Node)) closeMenu();
    };
    const key = (e: KeyboardEvent) => e.key === "Escape" && closeMenu();
    window.addEventListener("pointerdown", down, true);
    window.addEventListener("keydown", key, true);
    window.addEventListener("blur", closeMenu);
    window.addEventListener("wheel", closeMenu, { passive: true });
    return () => {
      window.removeEventListener("pointerdown", down, true);
      window.removeEventListener("keydown", key, true);
      window.removeEventListener("blur", closeMenu);
      window.removeEventListener("wheel", closeMenu);
    };
  }, [menu]);

  // "Clear keyframe" needs to know whether the shot has one
  useEffect(() => {
    if (menu && ep && !refs) void loadRefs(ep);
  }, [menu, ep, refs]);

  if (!menu || !ep) return null;
  // a voice take: whether the shot's model can be dubbed to it
  const noDub = dubBlock(targets, shotTarget(st?.shots.find((x) => x.shot === menu.shot), seriesDefault));
  const sound = st?.shots.find((x) => x.shot === menu.shot)?.sound;
  // right-clicked one of several selected shots, on the pass they're selected on
  const several = multi.length > 1 && multi.includes(menu.shot) && menu.pass === curPass;
  const shot = st?.shots.find((x) => x.shot === menu.shot);
  const take = menu.take != null ? shot?.takes.find((t) => t.take === menu.take) : undefined;
  const cutShot = cutSt?.shots.find((x) => x.shot === menu.shot);
  const isCut = !!take && !!cutShot && cutShot.cut.take === take.take && cutShot.cut.pass === menu.pass;
  const videos = (shot?.takes ?? []).filter((t) => t.mp4);
  const other = menu.take != null
    ? (cutShot && cutShot.cut.pass === menu.pass && cutShot.cut.take !== menu.take && videos.find((t) => t.take === cutShot.cut.take)) ||
      videos.filter((t) => t.take !== menu.take).pop()
    : undefined;
  const usable = !!take && take.status === "ok" && take.has_video;
  // Phase 9b: the clip in the current pass's cut
  const locked = !!cutShot?.cut?.locked;
  const trimmed = !!cutShot && ((cutShot.cut.trim_in ?? 0) > 0 || (cutShot.cut.trim_out ?? 0) > 0);
  const cutIdx = cutSt?.shots.findIndex((x) => x.shot === menu.shot) ?? -1;
  // Phase 9d: what this clip plays, if not its own take's sound
  const clipAudio = audioOf(cutShot?.cut);
  const run = (fn: () => void) => () => {
    closeMenu();
    fn();
    refocusAfterMenu();
  };
  const missing = shot ? missingOf(shot) : [];
  // the timeline plays the current pass's cut
  const inCut = !!cutShot && !cutShot.orphan;
  // continuity keyframes: neighbours in the menu's pass's cut
  const prev = cutNeighbour(st, menu.shot, -1);
  const next = cutNeighbour(st, menu.shot, 1);
  const nextSt = next ? st?.shots.find((x) => x.shot === next) : undefined;
  const kfNote = (s: typeof shot) => {
    const n = keyframeNote(targets, shotTarget(s, seriesDefault));
    return n ? `\nKeyframes are ${n}.` : "";
  };
  const firstKf = refs?.find((r) => r.id === keyframeRefId(menu.shot, "first"));
  const frameLabel = menu.frame == null || menu.frame === "last" ? "its last frame" : `frame ${menu.frame}`;
  const keyframes = (
    <>
      <div className="h3-menu-sep" />
      <button
        disabled={!prev}
        title={(prev
          ? `${menu.shot}'s first keyframe = ${prev}'s last frame, from the take the ${menu.pass} cut uses`
          : `${menu.shot} is the first shot of the ${menu.pass} cut`) + kfNote(shot)}
        onClick={run(() => void keyframeFromTake({ shot: menu.shot, which: "first", pass: menu.pass }))}
      >
        <i className="pi pi-link" /> Use previous shot's last frame as first frame
      </button>
      {take && (
        <button
          disabled={!next || !usable}
          title={(!usable
            ? "Only a finished take with video has frames"
            : next
              ? `${next}'s first keyframe = ${frameLabel} of ${menu.shot} ${tn(take.take)}`
              : `${menu.shot} is the last shot of the ${menu.pass} cut`) + kfNote(nextSt)}
          onClick={run(() => next && void keyframeFromTake({
            shot: next, which: "first", sourceShot: menu.shot, sourceTake: take.take, frame: menu.frame ?? "last", pass: menu.pass,
          }))}
        >
          <i className="pi pi-arrow-right" /> Use this frame as the next shot's first frame
          <span className="h3-muted"> ({frameLabel === "its last frame" ? "last frame" : frameLabel})</span>
        </button>
      )}
      {take && menu.frame == null && (
        // the menu from a thumbnail or the timeline has no frame to take: say where it is
        <button disabled title="Play or scrub the take in the viewer to the frame you want, then right-click the picture itself">
          <i className="pi pi-user-plus" /> Character or place from a frame…
          <span className="h3-muted"> (right-click the picture in the viewer)</span>
        </button>
      )}
      {take && menu.frame != null && (
        <button disabled={!usable}
          title={usable ? `Make a new character or place from ${frameLabel} of ${menu.shot} ${tn(take.take)}, or a new picture for one there is`
            : "Only a finished take with video has frames"}
          onClick={run(() => openFrameUse({ shot: menu.shot, take: take.take, pass: menu.pass, frame: menu.frame ?? "last" }))}>
          <i className="pi pi-user-plus" /> Character or place from this frame…
        </button>
      )}
      <button
        title={`A still of ${menu.shot}'s opening moment, made by the keyframe image model; it goes live if ${menu.shot} has no first keyframe yet` + kfNote(shot)}
        onClick={run(() => void generateKeyframe(menu.shot, "first"))}
      >
        <i className="pi pi-sparkles" /> Generate first frame
      </button>
      <button
        disabled={!firstKf?.exists}
        title={firstKf?.exists
          ? `Remove ${menu.shot}'s live first keyframe (its candidates stay)${firstKf.need === "required" ? `; ${menu.shot} can't render without one` : `; ${menu.shot} then renders without it`}`
          : `${menu.shot} has no live first keyframe`}
        onClick={run(() => void clearRef(keyframeRefId(menu.shot, "first")))}
      >
        <i className="pi pi-times" /> Clear keyframe
      </button>
    </>
  );
  const common = (
    <>
      {keyframes}
      <div className="h3-menu-sep" />
      <button disabled={!!shot?.orphan} title="How the shot's sound is made: generate, clone, or dub a track" onClick={run(() => openSound([menu.shot]))}>
        <i className="pi pi-volume-up" /> Sound…{sound ? ` (${sound.mode === "dub" ? `dub · ${sound.label}` : sound.mode})` : ""}
      </button>
      <button disabled={!!shot?.orphan}
        title={noVoice ?? "Queue a dub track now: the shot rendered for its sound only (H3 Ref2VA, 64x64), its voices cloned; pick it in Sound… to dub the shot with"}
        onClick={run(() => generateDubTracks([menu.shot]))}>
        <i className={noVoice ? "pi pi-exclamation-triangle" : "pi pi-microphone"} /> Generate a dub track{noVoice ? " (install H3 Ref2VA…)" : ""}
      </button>
      <div className="h3-menu-sep" />
      <button disabled={!inCut} title="Play the cut from this shot, in the viewer" onClick={run(() => playAll(menu.shot))}>
        <i className="pi pi-forward" /> Play from here
      </button>
      <div className="h3-menu-sep" />
      <button
        disabled={!cutShot}
        title={cutShot?.cut.flag ? `Clear ${menu.shot}'s flag (M)` : `Flag ${menu.shot} to come back to: re-render it, change its prompt (M; Shift+M goes to the next flagged clip)`}
        onClick={run(() => void toggleFlag(menu.shot))}
      >
        <i className={cutShot?.cut.flag ? "pi pi-flag" : "pi pi-flag-fill"} /> {cutShot?.cut.flag ? "Unflag" : "Flag to come back to"}
      </button>
      <button
        disabled={!cutShot}
        title={locked ? `Let ${menu.shot} be moved, trimmed and re-picked again in the ${curPass} cut` : `Keep ${menu.shot} where it is in the ${curPass} cut: no moves, trims or re-picks until unlocked`}
        onClick={run(() => void toggleLock(menu.shot))}
      >
        <i className={locked ? "pi pi-lock-open" : "pi pi-lock"} /> {locked ? "Unlock in the cut" : "Lock in the cut"}
      </button>
      <button
        disabled={!cutShot || locked}
        title={locked ? `${menu.shot} is locked: unlock it first`
          : cutShot?.cut.out ? `Put ${menu.shot} back in the ${curPass} cut, where it was`
          : `Leave ${menu.shot} out of the ${curPass} cut: it stays in the script with its takes, and assemble, Play all and Master skip it`}
        onClick={run(() => void toggleOut(menu.shot))}
      >
        <i className={cutShot?.cut.out ? "pi pi-plus-circle" : "pi pi-minus-circle"} /> {cutShot?.cut.out ? "Put back in the cut" : "Leave out of the cut"}
      </button>
      {trimmed && (
        <button disabled={locked} title={locked ? `${menu.shot} is locked` : `Back to the whole take (${cutShot!.cut.trim_in || 0} + ${cutShot!.cut.trim_out || 0} frames trimmed)`} onClick={run(() => void setTrims(menu.shot, 0, 0, `Clear ${menu.shot} trims`))}>
          <i className="pi pi-arrows-h" /> Clear trims
        </button>
      )}
      <button
        title={`Note what is wrong with ${menu.shot} as it rendered (n on the selected clip)`}
        onClick={run(() => openIssue(menu.shot, curPass, menu.take))}
      >
        <i className="pi pi-comment" /> Add issue…
      </button>
      <button
        disabled={!cutShot}
        title={clipAudio
          ? `${menu.shot} plays ${cutShot?.cut.audio_why || audioWhy(clipAudio, menu.shot)} instead of its own sound — change or clear it`
          : `This take's picture with another take's (or a file's) sound under it, cut to ${menu.shot}'s length`}
        onClick={run(() => openClipAudio(menu.shot, curPass))}
      >
        <i className={clipAudio?.source === "none" ? "pi pi-volume-off" : "pi pi-volume-up"} /> Audio from…
        {clipAudio && <span className="h3-muted"> ({cutShot?.cut.audio_why || audioWhy(clipAudio, menu.shot)})</span>}
      </button>
      {clipAudio && (
        <button disabled={locked} title={locked ? `${menu.shot} is locked` : `${menu.shot} back to its own take's sound`} onClick={run(() => void clearClipAudio(menu.shot))}>
          <i className="pi pi-undo" /> Back to its own audio
        </button>
      )}
      <button disabled={locked || cutIdx <= 0} title="Alt+← in the timeline" onClick={run(() => void nudgeClip(menu.shot, -1))}>
        <i className="pi pi-arrow-left" /> Move left in the cut
      </button>
      <button disabled={locked || cutIdx < 0 || cutIdx >= (cutSt?.shots.length ?? 0) - 1} title="Alt+→ in the timeline" onClick={run(() => void nudgeClip(menu.shot, 1))}>
        <i className="pi pi-arrow-right" /> Move right in the cut
      </button>
      {missing.length > 0 && (
        <button title={missing.map((m) => `${m.slot}: ${m.path}`).join("\n")} onClick={run(() => showMissingRefs(menu.shot))}>
          <i className="pi pi-exclamation-triangle" /> Show missing refs ({missing.length})
        </button>
      )}
      <button onClick={run(() => openInspector(menu.shot, take?.take ?? null))}>
        <i className="pi pi-sliders-h" /> Inspect shot
      </button>
      <button disabled={!!shot?.orphan} title={shot?.orphan ? `${menu.shot} is no longer in the script` : `Open the script at ${menu.shot}'s lines`} onClick={run(() => showInScript(menu.shot))}>
        <i className="pi pi-file-edit" /> Show in script
      </button>
      <button disabled={!!shot?.orphan} title="Edit the shot as a form: who, size, length, action, dialogue, camera, sound" onClick={run(() => openShotForm({ shot: menu.shot, after: null }))}>
        <i className="pi pi-pencil" /> Edit shot…
      </button>
      <button title={`Add a shot after ${menu.shot}`} onClick={run(() => openShotForm({ shot: null, after: menu.shot }))}>
        <i className="pi pi-plus" /> Add a shot after
      </button>
      <button disabled={!!shot?.orphan} title={`A video file as a new take of ${menu.shot}, in the cut (or drop one on its row or clip)`} onClick={run(() => pickTakeFile(menu.shot))}>
        <i className="pi pi-upload" /> Import video…
      </button>
    </>
  );

  return (
    <div
      ref={ref}
      className="h3-menu"
      style={pos ?? { left: menu.x, top: menu.y, visibility: "hidden" }}
      onContextMenu={(e) => e.preventDefault()}
    >
      <div className="h3-menu-head">
        {menu.shot} {take ? tn(take.take) : ""} {menu.pass !== curPass ? `(${menu.pass})` : ""}
        {take ? ` · ${take.status}` : ""}
      </div>
      {several && (
        <>
          <button title="A new take of each: a shot's first at its built seed, a new seed otherwise (as Generate does)" onClick={run(() => renderSelected())}>
            <i className="pi pi-play" /> Generate the {multi.length} selected
          </button>
          <button title="The Render dialog first: the video model for this run, where they render" onClick={run(() => renderSelected(true))}>
            <i className="pi pi-sliders-h" /> Render the {multi.length} selected…
          </button>
          <div className="h3-menu-sep" />
        </>
      )}
      {take ? (
        <>
          <button disabled={!take.mp4} onClick={run(() => openViewer(menu.shot, take.take, null, "single", menu.pass))}>
            <i className="pi pi-play" /> Play
          </button>
          <button
            disabled={!take.mp4 || !other}
            title={other ? `Opens the viewer with ${tn(take.take)} as A and ${tn(other.take)} as B; click another take to change B` : "Needs another take with video"}
            onClick={run(() => other && openViewer(menu.shot, take.take, other.take, "side", menu.pass))}
          >
            <i className="pi pi-clone" /> Compare with…
          </button>
          <button
            disabled={!usable || isCut || locked}
            title={isCut ? "The cut already uses this take" : locked ? `${menu.shot} is locked in the cut: unlock it to change its take` : usable ? "" : "Only a finished take with video can go in the cut"}
            onClick={run(() => void pickTake(menu.shot, take.take, menu.pass))}
          >
            <i className="pi pi-check" /> Use this take{isCut ? " (in the cut)" : ""}
          </button>
          <button onClick={run(() => openRedo(menu.shot, take.take, menu.pass))}>
            <i className="pi pi-refresh" /> New take like this one…
          </button>
          {menu.pass === "proxy" && take.draft && take.status === "ok" && (
            <button disabled={take.draft.expired}
              title={take.draft.expired ? "Its draft has expired (they last 7 days): render the shot's final instead"
                : "A paid 1080p render of this draft exactly as drawn (its prompt, pictures, seed and sound), as the shot's final"}
              onClick={run(() => {
                const changed = take.stale.length
                  ? `\n\nThe shot has changed since this draft (${take.stale.join(", ")}): the final will match the draft, not the script.` : "";
                if (confirm(`Make ${menu.shot}'s final from draft ${tn(take.take)}? A paid 1080p render of this draft as drawn.${changed}`)) {
                  void makeFinalsFromDrafts({ [menu.shot]: take.take });
                }
              })}>
              <i className="pi pi-forward" /> Make final from draft (1080p)…
            </button>
          )}
          <button onClick={run(() => openSidecar(menu.shot, take.take, menu.pass))}>
            <i className="pi pi-info-circle" /> Show details
          </button>
          <button
            disabled={!take.mp4}
            onClick={run(() => take.mp4 && void copyText(absPath(ep, take.mp4), "Path"))}
          >
            <i className="pi pi-copy" /> Copy path
          </button>
          {take.status === "queued" && (
            <button onClick={run(() => void cancelTake({ ep, pass: menu.pass, shot: menu.shot, take: take.take }))}>
              <i className="pi pi-ban" /> Cancel this render
            </button>
          )}
          <button
            disabled={!usable || take.upscale?.status === "queued"}
            title={take.upscale?.status === "queued"
              ? "Its upscale is queued"
              : "Upscale this take 2x: a re-sample (more detail, the same performance) or an upscale model, its own audio kept"}
            onClick={run(() => void upscaleTake({ ep, pass: menu.pass, shot: menu.shot, take: take.take }, !!take.upscale?.fresh))}
          >
            <i className="pi pi-arrow-up-right" /> {take.upscale?.fresh ? "Upscale again (2x)…" : "Upscale (2x)…"}
          </button>
          {take.upscale?.status === "ok" && (
            <button
              title={take.upscale.keep
                ? "Let Master and a whole-cut redo replace this upscale again"
                : "Keep this upscale: Master and a whole-cut redo leave it alone, even when the series recipe changes (naming this take still redoes it)"}
              onClick={run(() => void keepUpscale({ ep, pass: menu.pass, shot: menu.shot, take: take.take }, !take.upscale!.keep))}
            >
              <i className={`pi ${take.upscale.keep ? "pi-lock-open" : "pi-lock"}`} /> {take.upscale.keep ? "Unkeep upscale" : "Keep upscale"}
            </button>
          )}
          {take.upscale && take.upscale.status !== "queued" && (
            <button onClick={run(() => void removeUpscale({ ep, pass: menu.pass, shot: menu.shot, take: take.take }))}>
              <i className="pi pi-times" /> Remove upscale
            </button>
          )}
          <button
            disabled={!take.upscale?.fresh || take.upscale.status !== "ok" || take.post?.status === "queued"}
            title={take.post?.status === "queued" ? "Its post is queued"
              : !take.upscale?.fresh || take.upscale.status !== "ok" ? "Upscale it first: a post finishes the upscale"
              : "Finish its upscale: SeedVR2 clean-up and/or motion blur, by the series recipe or your choice"}
            onClick={run(() => void postTake({ ep, pass: menu.pass, shot: menu.shot, take: take.take }, !!take.post?.fresh))}
          >
            <i className="pi pi-sparkles" /> {take.post?.fresh ? "Post-process again…" : "Post-process…"}
          </button>
          {take.post && take.post.status !== "queued" && (
            <button onClick={run(() => void removePost({ ep, pass: menu.pass, shot: menu.shot, take: take.take }))}>
              <i className="pi pi-times" /> Remove post
            </button>
          )}
          <button
            className="h3-menu-danger"
            disabled={take.status === "queued"}
            title={take.status === "queued"
              ? "Still queued: cancel the render first"
              : `Move ${tn(take.take)}'s files to the _trash folder beside them (nothing is deleted)${isCut ? "; the cut goes back to the latest usable take" : ""}`}
            onClick={run(() => void discardTake({ ep, pass: menu.pass, shot: menu.shot, take: take.take }))}
          >
            <i className="pi pi-trash" /> Discard take…
          </button>
          {take.status === "ok" && (
            <button disabled={!!noDub}
              title={noDub ?? `Dub ${menu.shot} to ${tn(take.take)}'s sound from now on (its next render; its takes go stale)`}
              onClick={run(() => void setSound([menu.shot], { mode: "dub", dub: { from: "take", pass: menu.pass, take: take.take } }))}>
              <i className="pi pi-volume-up" /> Dub the shot with this take's sound
            </button>
          )}
          {common}
        </>
      ) : (
        <>
          <button onClick={run(() => requestRender([menu.shot], false))}>
            <i className="pi pi-play" /> Render this shot{missing.length ? "…" : ""}
          </button>
          <button onClick={run(() => openRedo(menu.shot, null, menu.pass))}>
            <i className="pi pi-refresh" /> Render with settings…
          </button>
          {common}
        </>
      )}
    </div>
  );
}
