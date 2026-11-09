import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import {
  cancelTake, clearRef, closeMenu, copyText, discardTake, generateKeyframe, keyframeFromTake, loadRefs,
  openIssue,
  keepUpscale, openInspector, openRangeRedo, openRedo, openSidecar, openViewer, pickTake, playAll, removeUpscale, requestRender, openShotForm, showInScript, showMissingRefs,
  upscaleTake, postTake, removePost, openFrameUse, refocusAfterMenu, makeFinalsFromDrafts, renderSelected,
  generateDubTracks, openSound, setSound,
} from "../actions";
import { holdFrameAfter, pickTakeFile } from "../takeActions";
import { newCue } from "../cueActions";
import { currentMix, makeEffects, makeVoiceStems, pickSoundFile, setShotVoicesMix, toggleSound } from "../mixActions";
import { firstOf, voicePlays, voicesOnly } from "../lib/mix";
import { host } from "../host";
import { JOIN_DEFAULT, MATCH_WAYS, clearClipAudio, matchColors, nudgeClip, setColdOpenEnd, setJoin, setTrims, toggleFlag, toggleLock, toggleOut } from "../cutActions";
import { JOIN_KEYS } from "../lib/cutEdit";
import { audioOf, audioWhy } from "../lib/audioSource";
import { absPath, tn } from "../lib/format";
import { cutNeighbour, keyframeNote, keyframeRefId } from "../lib/keyframes";
import { missingOf } from "../lib/missingRefs";
import { shotTarget } from "../lib/targets";
import { dubBlock, dubTrackBlock } from "../lib/readiness";
import { statusKey, useApp } from "../store";
import { useTargets } from "./Targets";

/** A group of the menu's items, opened beside it on hover (in the page all along,
 * shown by CSS: .h3-submenu:hover). */
function Sub({ icon, label, note, children }: { icon: string; label: string; note?: string; children: ReactNode }) {
  return (
    <div className="h3-submenu">
      <button className="h3-submenu-head" tabIndex={-1}>
        <i className={`pi ${icon}`} /> {label}
        {note && <span className="h3-muted"> ({note})</span>}
        <i className="pi pi-angle-right h3-submenu-arrow" />
      </button>
      <div className="h3-menu h3-menu-flyout">{children}</div>
    </div>
  );
}

/** The thumbnail context menu, the same in the bin, the timeline and the viewer strip:
 * what's done to the take at the top, then the rest in groups (Cut, Fades and
 * dissolve, Colour, Frames, Sound, Shot), each opening beside it. */
export function ContextMenu() {
  const menu = useApp((s) => s.menu);
  const ep = useApp((s) => s.ep);
  const curPass = useApp((s) => s.pass);
  const st = useApp((s) => (s.ep && s.menu ? s.status[statusKey(s.ep, s.menu.pass)] : undefined));
  const cutSt = useApp((s) => (s.ep ? s.status[statusKey(s.ep, s.pass)] : undefined));
  // the cold open (the In the cut group's Cold open ends here): with the other hooks, before any return
  const coldOpen = useApp((s) => (s.ep ? s.coldOpen[statusKey(s.ep, s.pass)] : undefined));
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ left: number; top: number; flip: boolean; up: boolean } | null>(null);
  const { list: targets, seriesDefault } = useTargets();
  const refs = useApp((s) => (s.ep ? s.refs[s.ep] : undefined));
  const multi = useApp((s) => s.multi);
  // the mix's voices only (GET /seriesmith/mix `voices`, fetched with the pass: never per shot)
  const mixRes = useApp((s) => currentMix(s));
  const noVoice = dubTrackBlock(targets);

  useLayoutEffect(() => {
    if (!menu || !ref.current) return setPos(null);
    const r = ref.current.getBoundingClientRect();
    const left = Math.max(4, Math.min(menu.x, window.innerWidth - r.width - 4));
    const top = Math.max(4, Math.min(menu.y, window.innerHeight - r.height - 4));
    setPos({
      left, top,
      // the groups open to the left when there's no room on the right, upwards in the
      // bottom half of the window
      flip: left + r.width + 300 > window.innerWidth,
      up: top + r.height / 2 > window.innerHeight / 2,
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
  const joins = JOIN_KEYS.filter((k) => (cutShot?.cut[k] || 0) > 0).length;

  const frames = (
    <Sub icon="pi-image" label="Frames">
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
      {take && (
        <button disabled={!usable}
          title={usable ? `A new shot right after ${menu.shot}: ${frameLabel} of ${tn(take.take)} held still (a freeze frame), as long as you say`
            : "Only a finished take with video has frames"}
          onClick={run(() => void holdFrameAfter(menu.shot, take.take, menu.frame ?? "last", menu.pass))}>
          <i className="pi pi-pause" /> Hold this frame after it…
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
      <div className="h3-menu-sep" />
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
    </Sub>
  );

  // where the shot starts in the cut, as the mix anchors it: its take's first frame played
  const clipStart = { shot: menu.shot, frame: cutShot?.cut.trim_in ?? 0 };
  // effects: the selection when the clip right-clicked is one of several, else the clip;
  // the foley models this server has, the default first
  const fxShots = multi.length > 1 && multi.includes(menu.shot)
    ? multi.filter((x) => cutSt?.shots.some((c) => c.shot === x && !c.orphan && !c.cut.out))
    : [menu.shot];
  const fxModels = (targets?.targets ?? []).filter((t) => t.kind === "foley")
    .map((t) => ({ ...t, default: t.id === (targets?.default?.foley ?? "h3_foley") }));
  const soundGroup = (
    <Sub icon="pi-volume-up" label="Sound" note={clipAudio ? "replaced" : sound ? (sound.mode === "dub" ? "dub" : sound.mode) : undefined}>
      <button disabled={!!shot?.orphan} title="How the shot's sound is made: generate, clone, or dub a track" onClick={run(() => openSound([menu.shot]))}>
        <i className="pi pi-volume-up" /> Sound…{sound ? ` (${sound.mode === "dub" ? `dub · ${sound.label}` : sound.mode})` : ""}
      </button>
      {take?.status === "ok" && (
        <button disabled={!!noDub}
          title={noDub ?? `Dub ${menu.shot} to ${tn(take.take)}'s sound from now on (its next render; its takes go stale)`}
          onClick={run(() => void setSound([menu.shot], { mode: "dub", dub: { from: "take", pass: menu.pass, take: take.take } }))}>
          <i className="pi pi-volume-up" /> Dub the shot with this take's sound
        </button>
      )}
      <button disabled={!!shot?.orphan}
        title={noVoice ?? "Queue a dub track now: the shot rendered for its sound only (H3 Ref2VA, 64x64), its voices cloned; pick it in Sound… to dub the shot with"}
        onClick={run(() => generateDubTracks([menu.shot]))}>
        <i className={noVoice ? "pi pi-exclamation-triangle" : "pi pi-microphone"} /> Generate a dub track{noVoice ? " (install H3 Ref2VA…)" : ""}
      </button>
      <button disabled={!!shot?.orphan || !!noDub}
        title={noDub ?? noVoice ?? `Queue a dub track, and once it's made, dub ${menu.shot} with it and render it on its own model: for when there's no time to listen first`}
        onClick={run(() => generateDubTracks([menu.shot], undefined, true))}>
        <i className="pi pi-forward" /> Dub track, then render
      </button>
      <div className="h3-menu-sep" />
      <button
        disabled={!cutShot}
        title={clipAudio
          ? `${menu.shot} plays ${cutShot?.cut.audio_why || audioWhy(clipAudio, menu.shot)} instead of its own sound — change or clear it`
          : `This take's picture with another take's (or a file's) sound under it, cut to ${menu.shot}'s length`}
        onClick={run(() => openSound([menu.shot], "cut"))}
      >
        <i className={clipAudio?.source === "none" ? "pi pi-volume-off" : "pi pi-volume-up"} /> Replace audio…
        {clipAudio && <span className="h3-muted"> ({cutShot?.cut.audio_why || audioWhy(clipAudio, menu.shot)})</span>}
      </button>
      {clipAudio && (
        <button disabled={locked} title={locked ? `${menu.shot} is locked` : `${menu.shot} back to its own take's sound`} onClick={run(() => void clearClipAudio(menu.shot))}>
          <i className="pi pi-undo" /> Back to its own audio
        </button>
      )}
      <div className="h3-menu-sep" />
      {/* a shot's effects (docs/SOUND.md phase 4): made from the take the cut plays, only for the shots asked */}
      <button disabled={!cutShot || !!cutShot.cut.out}
        title={`Sync sound (footsteps, a door, the cups) made from the frames of the take the cut plays for ${fxShots.length > 1 ? `each of the ${fxShots.length} shots selected` : menu.shot}, on the Effects lane at its clip${fxModels.length ? ` (${fxModels.find((t) => t.default)?.short ?? fxModels[0].short ?? fxModels[0].label})` : ""}`}
        onClick={run(() => { toggleSound(true); void makeEffects(fxShots); })}>
        <i className="pi pi-bolt" /> Make effects{fxShots.length > 1 ? ` for ${fxShots.length} shots` : ""}
      </button>
      {fxModels.filter((t) => !t.default).map((t) => (
        <button key={t.id} disabled={!cutShot || !!cutShot.cut.out}
          title={`The same on ${t.label}`}
          onClick={run(() => { toggleSound(true); void makeEffects(fxShots, t.id); })}>
          <i className="pi pi-bolt" /> Make effects on {t.short ?? t.label}{fxShots.length > 1 ? ` (${fxShots.length})` : ""}
        </button>
      ))}
      <div className="h3-menu-sep" />
      {/* voices only (voices.py): the shot's own way over the Dialogue track's, and its stem made again */}
      {(() => {
        const v = mixRes?.voices?.shots.find((x) => x.shot === menu.shot);
        const own = mixRes?.mix.voices?.[menu.shot]?.voices_only;
        const track = voicesOnly(mixRes?.mix);
        const how = v ? voicePlays(mixRes?.mix, v) : null;
        const off = !cutShot || !!cutShot.cut.out || !v || v.state === "sourced" || v.state === "silent";
        const why = !v ? "Not in the cut (or the server is older: restart it)"
          : v.state === "sourced" ? `${menu.shot} plays sound the cut gives it (Replace audio…): voices only leaves it`
          : v.state === "silent" ? `${menu.shot}'s take has no sound` : "";
        const many = fxShots.length > 1 ? ` (${fxShots.length} shots)` : "";
        const now = how === "voice" ? "plays its voice stem" : how === "silence" ? "is silent (no lines)" : "plays its whole sound";
        return (
          <>
            <button disabled={off} data-voices="whole"
              title={why || `${menu.shot} plays its take's whole sound on the Dialogue track, the model's music and room tone with it, whatever the track says (now it ${now})`}
              onClick={run(() => void setShotVoicesMix(fxShots, own === false ? null : false))}>
              <i className={own === false ? "pi pi-check" : "pi pi-volume-up"} /> Keep its whole sound{many}
            </button>
            <button disabled={off} data-voices="only"
              title={why || `${menu.shot} plays its take's voice stem alone (its model's music and room tone split off)${v && !v.lines ? ", though the script gives it no lines" : ""}${v && v.state !== "ok" ? `; ${v.why ?? "its stem isn't made"}: make it below` : ""} (now it ${now})`}
              onClick={run(() => void setShotVoicesMix(fxShots, own === true ? null : true))}>
              <i className={own === true ? "pi pi-check" : "pi pi-user"} /> Voices only{many}
              {own == null && track && <span className="h3-muted"> (the track's)</span>}
            </button>
            <button disabled={off || v?.state === "queued"} data-voices="again"
              title={why || (v?.state === "queued" ? "Being split" : `Split ${fxShots.length > 1 ? "their takes" : `${menu.shot}'s take`} into voice and the rest again, on local ComfyUI${v?.state === "ok" ? "" : ` (${v?.why ?? "not split yet"})`}`)}
              onClick={run(() => { toggleSound(true); void makeVoiceStems(fxShots, true); })}>
              <i className="pi pi-refresh" /> {v?.state === "ok" ? "Split its voice again" : "Split its voice"}{many}
            </button>
            <div className="h3-menu-sep" />
          </>
        );
      })()}
      {/* the episode's mix (docs/SOUND.md): music, effects and ambience laid over the cut from here */}
      <button disabled={!cutShot || !!cutShot.cut.out}
        title={multi.length > 1 && multi.includes(menu.shot)
          ? `A cue over the ${multi.length} shots selected, in the cue window: its sections, arc and takes`
          : `A cue over ${menu.shot}, in the cue window (select several shots for a longer one)`}
        onClick={run(() => { toggleSound(true); void newCue(clipStart); })}>
        <i className="pi pi-volume-up" /> New music cue{multi.length > 1 && multi.includes(menu.shot) ? ` over ${multi.length} shots` : ""}…
      </button>
      {(["music", "effects", "ambience"] as const).map((t) => (
        <button key={t} disabled={!cutShot || !!cutShot.cut.out}
          title={`A wav, mp3, flac, ogg or m4a from this computer, on the ${t} lane from ${menu.shot}'s first frame in the cut (it moves with the shot)`}
          // onto the default track of that kind, else the first of it (the mix's own tracks)
          onClick={run(() => {
            const to = firstOf(currentMix()?.mix, t);
            if (to) pickSoundFile(to, clipStart);
            else host().toast("warn", `No ${t} track`, `Add one from a lane head's ⋮ under the timeline.`);
          })}>
          <i className="pi pi-upload" /> Add {t === "music" ? "music" : t === "effects" ? "an effect" : "ambience"} from a file…
        </button>
      ))}
    </Sub>
  );

  const cutGroup = (
    <Sub icon="pi-video" label="In the cut" note={[locked && "locked", cutShot?.cut.out && "left out", cutShot?.cut.flag && "flagged"].filter(Boolean).join(", ") || undefined}>
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
      <div className="h3-menu-sep" />
      <button disabled={locked || cutIdx <= 0} title="Alt+← in the timeline" onClick={run(() => void nudgeClip(menu.shot, -1))}>
        <i className="pi pi-arrow-left" /> Move left in the cut
      </button>
      <button disabled={locked || cutIdx < 0 || cutIdx >= (cutSt?.shots.length ?? 0) - 1} title="Alt+→ in the timeline" onClick={run(() => void nudgeClip(menu.shot, 1))}>
        <i className="pi pi-arrow-right" /> Move right in the cut
      </button>
      <div className="h3-menu-sep" />
      <button disabled={!cutShot || !!cutShot.cut.out || !!cutShot.orphan}
        title={`The cold open: every shot from the cut's first through ${menu.shot} plays before the opening titles, and a master puts the series intro in right after it. Written into the script as cold_open: true (on a sequence's # line when all its shots are in it), the old script kept in _history`}
        onClick={run(() => void setColdOpenEnd(menu.shot))}>
        <i className="pi pi-step-forward" /> Cold open ends here{coldOpen?.end === menu.shot && !coldOpen.error ? " ✓" : ""}
      </button>
      {(coldOpen?.end || (coldOpen?.gaps.length ?? 0) > 0) && (
        <button title="No cold open: the master opens on the series intro. Every cold_open: line comes out of the script (the old one kept in _history)"
          onClick={run(() => void setColdOpenEnd(null))}>
          <i className="pi pi-times" /> No cold open
        </button>
      )}
      {trimmed && (
        <button disabled={locked} title={locked ? `${menu.shot} is locked` : `Back to the whole take (${cutShot!.cut.trim_in || 0} + ${cutShot!.cut.trim_out || 0} frames trimmed)`} onClick={run(() => void setTrims(menu.shot, 0, 0, `Clear ${menu.shot} trims`))}>
          <i className="pi pi-arrows-h" /> Clear trims
        </button>
      )}
    </Sub>
  );

  const joinGroup = (
    <Sub icon="pi-sort-alt" label="Fades and dissolve" note={joins ? `${joins} on` : undefined}>
      {JOIN_KEYS.map((k) => {
        const on = (cutShot?.cut[k] || 0) > 0;
        const words = { fade_in: "Fade in from black", fade_out: "Fade out to black", dissolve: "Dissolve from the clip before" }[k];
        return (
          <button key={k} disabled={!cutShot || !!cutShot.orphan || locked}
            title={on ? `Take it off (${cutShot!.cut[k]} frames now; drag its handle on the timeline, or the inspector, to set the length)`
              : `${words}, ${JOIN_DEFAULT} frames (drag its handle on the timeline, or the inspector's In the cut, to change it); made on export`}
            onClick={run(() => void setJoin(menu.shot, k, on ? 0 : JOIN_DEFAULT))}>
            <i className={on ? "pi pi-check" : "pi pi-minus"} style={{ opacity: on ? 1 : 0.35 }} /> {words}
            {on && <span className="h3-muted"> ({cutShot!.cut[k]}f)</span>}
          </button>
        );
      })}
    </Sub>
  );

  const colourGroup = (
    <Sub icon="pi-palette" label="Colour">
      {MATCH_WAYS.map((w) => (
        <button
          key={w.by}
          disabled={!cutShot || !!cutShot.orphan}
          title={`Set the colour of the rest of ${menu.shot}'s sequence so it looks like ${menu.shot}, by ${w.title}: a starting point for each clip's sliders (the inspector). Locked clips are left alone; Ctrl+Z undoes it`}
          onClick={run(() => void matchColors(menu.shot, undefined, w.by))}
        >
          <i className="pi pi-clone" /> Match the sequence to this by {w.label.toLowerCase()}
        </button>
      ))}
    </Sub>
  );

  const shotGroup = (
    <Sub icon="pi-file-edit" label="Shot" note={missing.length ? `${missing.length} missing` : undefined}>
      <button disabled={!!shot?.orphan} title="Edit the shot as a form: who, size, length, action, dialogue, camera, sound" onClick={run(() => openShotForm({ shot: menu.shot, after: null }))}>
        <i className="pi pi-pencil" /> Edit shot…
      </button>
      <button disabled={!!shot?.orphan} title={shot?.orphan ? `${menu.shot} is no longer in the script` : `Open the script at ${menu.shot}'s lines`} onClick={run(() => showInScript(menu.shot))}>
        <i className="pi pi-file-edit" /> Show in script
      </button>
      <button title={`Add a shot after ${menu.shot}`} onClick={run(() => openShotForm({ shot: null, after: menu.shot }))}>
        <i className="pi pi-plus" /> Add a shot after
      </button>
      <button disabled={!!shot?.orphan} title={`A video file as a new take of ${menu.shot}, in the cut (or drop one on its row or clip)`} onClick={run(() => pickTakeFile(menu.shot))}>
        <i className="pi pi-upload" /> Import video…
      </button>
      {missing.length > 0 && (
        <button title={missing.map((m) => `${m.slot}: ${m.path}`).join("\n")} onClick={run(() => showMissingRefs(menu.shot))}>
          <i className="pi pi-exclamation-triangle" /> Show missing refs ({missing.length})
        </button>
      )}
      <button
        title={`Note what is wrong with ${menu.shot} as it rendered (n on the selected clip)`}
        onClick={run(() => openIssue(menu.shot, curPass, menu.take))}
      >
        <i className="pi pi-comment" /> Add issue…
      </button>
    </Sub>
  );

  const playFromHere = (
    <button disabled={!inCut} title="Play the cut from this shot, in the viewer" onClick={run(() => playAll(menu.shot))}>
      <i className="pi pi-forward" /> Play from here
    </button>
  );

  const groups = (
    <>
      <div className="h3-menu-sep" />
      {cutGroup}
      {joinGroup}
      {colourGroup}
      {frames}
      {soundGroup}
      {shotGroup}
      <div className="h3-menu-sep" />
      <button onClick={run(() => openInspector(menu.shot, take?.take ?? null))}>
        <i className="pi pi-sliders-h" /> Inspect shot
      </button>
    </>
  );

  return (
    <div
      ref={ref}
      className={`h3-menu${pos?.flip ? " h3-menu-flip" : ""}${pos?.up ? " h3-menu-up" : ""}`}
      style={pos ? { left: pos.left, top: pos.top } : { left: menu.x, top: menu.y, visibility: "hidden" }}
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
          {playFromHere}
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
          <button disabled={!usable}
            title={usable ? "Make a stretch of this take again as a new take, keeping the rest and its sound" : "Only a finished take with video"}
            onClick={run(() => openRangeRedo(menu.shot, take.take, menu.pass))}>
            <i className="pi pi-pencil" /> Re-render part of this take…
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
          {take.status === "queued" && (
            <button onClick={run(() => void cancelTake({ ep, pass: menu.pass, shot: menu.shot, take: take.take }))}>
              <i className="pi pi-ban" /> Cancel this render
            </button>
          )}
          <Sub icon="pi-arrow-up-right" label="Upscale and post"
            note={take.post?.fresh ? "posted" : take.upscale?.fresh ? "upscaled" : undefined}>
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
            <div className="h3-menu-sep" />
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
          </Sub>
          {groups}
          <button onClick={run(() => openSidecar(menu.shot, take.take, menu.pass))}>
            <i className="pi pi-info-circle" /> Show details
          </button>
          <button
            disabled={!take.mp4}
            onClick={run(() => take.mp4 && void copyText(absPath(ep, take.mp4), "Path"))}
          >
            <i className="pi pi-copy" /> Copy path
          </button>
          <div className="h3-menu-sep" />
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
        </>
      ) : (
        <>
          <button onClick={run(() => requestRender([menu.shot], false))}>
            <i className="pi pi-play" /> Render this shot{missing.length ? "…" : ""}
          </button>
          <button onClick={run(() => openRedo(menu.shot, null, menu.pass))}>
            <i className="pi pi-refresh" /> Render with settings…
          </button>
          {playFromHere}
          {groups}
        </>
      )}
    </div>
  );
}
