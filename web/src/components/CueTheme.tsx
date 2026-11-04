// A cue's theme, the leitmotif (docs/SOUND.md phases 2 and 8; seriesmith/cue.py theme_for): none,
// another cue's take (by default the one that cue has in the mix, followed as it's picked again;
// or a given finished take), a sound file relative to the episode, or one of the series config's
// themes (`sound.themes`, by name: a picked take of any episode's cue). On a model that renders
// from the theme's sound (Stable Audio 3), its strength. The cue inspector
// and the spotting sheet's selected cue both set it here. The other cue's takes are fetched
// when it's picked (GET /seriesmith/cue), never for the whole list. Beside it, how the cue's
// model hears it, and when it can't (Stable Audio 3), an offer of the model that does.
//
// Also a song take's plan (YuE2): its line ("Plan: 44 bars of 2/4, intro, verse...") and
// its sections as a strip on the cue's bar grid.

import { useEffect, useState } from "react";
import { loadCues } from "../cueActions";
import { api } from "../host";
import { songBlocks, songSummary, themeLabel, themeModel, themeTakes, themeUseText, type Grid } from "../lib/cue";
import { useApp } from "../store";
import type { CuePlan, CueSong, CueSpec, CueTheme, Pass, SeriesTheme, Target } from "../types";
import { usePictureBrowse } from "./Picture";

type Mode = "none" | "series" | "take" | "file";

const modeOf = (th: CueTheme | null): Mode => (th ? ("theme" in th ? "series" : "cue" in th ? "take" : "file") : "none");
const STRENGTH: [number, number] = [0.5, 0.99];

const tn = (n: number) => `t${String(n).padStart(2, "0")}`;

/** The theme's field: what it is, how the model hears it, and the switch when it can't. */
export function ThemeField({ ep, pass, spec, plan, target, targets, themes, save }: {
  ep: string; pass: Pass; spec: CueSpec; plan: CuePlan | null; target: Target | undefined; targets: Target[];
  /** the series config's themes (GET /seriesmith/cue's `themes`) */
  themes?: SeriesTheme[];
  save: (patch: Partial<CueSpec>) => void;
}) {
  const th = spec.theme ?? null;
  const [mode, setMode] = useState<Mode>(modeOf(th));
  useEffect(() => setMode(modeOf(th)), [th && JSON.stringify(th)]);
  const strength = th?.strength;
  const [str, setStr] = useState(strength != null ? String(strength) : "");
  useEffect(() => setStr(strength != null ? String(strength) : ""), [strength]);
  const cues = useApp((s) => s.cues[ep]);
  useEffect(() => {
    if (mode === "take" && !cues) void loadCues(ep);
  }, [mode, ep, !cues]);
  const others = (cues ?? []).filter((c) => c.spec.id !== spec.id && c.ok > 0);
  const [cue, setCue] = useState(th && "cue" in th ? th.cue : "");
  useEffect(() => setCue(th && "cue" in th ? th.cue : ""), [th && "cue" in th ? th.cue : ""]);
  // the picked cue's finished takes, fetched when it's picked
  const [takes, setTakes] = useState<number[] | null>(null);
  useEffect(() => {
    setTakes(null);
    if (!cue) return;
    let live = true;
    api().getCue(ep, pass, cue).then((r) => live && setTakes(themeTakes(r.takes)), () => live && setTakes([]));
    return () => {
      live = false;
    };
  }, [ep, pass, cue]);
  const [file, setFile] = useState(th && "file" in th ? th.file : "");
  useEffect(() => setFile(th && "file" in th ? th.file : ""), [th && "file" in th ? th.file : ""]);
  // a new source keeps the strength set for the old one
  const set = (t: CueTheme | null) => save({ theme: t && strength != null ? { ...t, strength } : t });
  const series = themes ?? [];
  const named = th && "theme" in th ? th.theme : "";
  const browse = usePictureBrowse(`cue-theme-${spec.id}`, "the cue's theme", (p) => {
    setFile(p);
    set({ file: p });
  }, false, "audio");
  const model = target?.short ?? target?.label ?? plan?.target ?? "its model";
  const swap = th ? themeModel(spec.kind, target, targets) : null;
  return (
    <div className="h3-col" style={{ gap: 3 }}>
      <select className="h3-in" aria-label="Theme" value={mode} onChange={(e) => {
        const m = e.target.value as Mode;
        setMode(m);
        if (m === "none" && th) set(null);
      }}>
        <option value="none">none</option>
        <option value="series" title="One of the series config's themes (sound.themes): a picked take of any episode's cue, or a file">a series theme</option>
        <option value="take">another cue's take</option>
        <option value="file">a sound file</option>
      </select>
      {mode === "series" && (
        <select className="h3-in" aria-label="Series theme" value={named}
          title="The series config's themes (sound.themes). Make one from a finished take: its row's ★ Series theme"
          onChange={(e) => e.target.value && set({ theme: e.target.value })}>
          <option value="">{series.length ? "a theme…" : "the series has none yet: make one from a take (★)"}</option>
          {series.map((s) => (
            <option key={s.name} value={s.name} title={[s.words, s.error].filter(Boolean).join(" · ")}>
              {s.name}{s.role ? ` · ${s.role}` : ""}{s.error ? " (can't be used)" : ` · ${s.label.replace(/^[^(]*(|)$/g, "")}`}
            </option>
          ))}
          {named && !series.some((s) => s.name === named) && <option value={named}>{named} (not in the series config)</option>}
        </select>
      )}
      {mode === "take" && (
        <span className="h3-row" style={{ gap: 4 }}>
          <select className="h3-in h3-grow" aria-label="Theme cue" value={cue} onChange={(e) => {
            setCue(e.target.value);
            // a cue picked: the take it has in the mix, until a take is named
            if (e.target.value) set({ cue: e.target.value });
          }}>
            <option value="">{cues ? (others.length ? "a cue…" : "no other cue has a finished take") : "…"}</option>
            {others.map((c) => <option key={c.spec.id} value={c.spec.id}>{c.spec.label ? `${c.spec.id} · ${c.spec.label}` : c.spec.id}</option>)}
            {cue && !others.some((c) => c.spec.id === cue) && <option value={cue}>{cue}</option>}
          </select>
          <select className="h3-in" aria-label="Theme take" style={{ width: "auto" }} disabled={!cue}
            title="The take in the mix: whichever take that cue has in this pass's mix (its best finished one while none is), followed when another is picked (this cue's takes go stale then). A take number: that take, whatever is picked"
            value={th && "cue" in th && th.cue === cue ? (th.take != null ? String(th.take) : "mix") : ""}
            onChange={(e) => e.target.value && set(e.target.value === "mix" ? { cue } : { cue, take: Number(e.target.value) })}>
            {!(th && "cue" in th && th.cue === cue) && <option value="">{cue ? "…" : "take"}</option>}
            <option value="mix">the take in the mix</option>
            {(takes ?? []).map((n) => <option key={n} value={n}>{tn(n)}</option>)}
            {th && "cue" in th && th.cue === cue && th.take != null && takes && !takes.includes(th.take) && <option value={th.take}>{tn(th.take)}</option>}
          </select>
        </span>
      )}
      {mode === "file" && (
        <span className="h3-row" style={{ gap: 4 }}>
          <input className="h3-in h3-grow h3-mono" style={{ minWidth: 0 }} value={file} spellCheck={false}
            placeholder="a sound inside the episode, e.g. audio/theme.wav" aria-label="Theme file"
            onChange={(e) => setFile(e.target.value)}
            onBlur={() => file.trim() && file.trim() !== (th && "file" in th ? th.file : "") && set({ file: file.trim() })}
            onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()} />
          <button type="button" className="h3-btn" title="Pick a sound file in the folder browser (inside the episode, or the show's folder)" onClick={browse}>Browse…</button>
        </span>
      )}
      {th && plan?.theme && plan.theme.use && <span className="h3-small h3-muted">{themeLabel(th, plan.theme)}: {themeUseText(plan.theme, model)}</span>}
      {th && plan?.theme?.use === "audio" && (
        <span className="h3-row h3-small" style={{ gap: 4 }}
          title={`Where the take starts from the theme's sound: lower keeps more of it (its instruments too), higher moves further toward this cue's words. ${target?.capabilities?.theme_strength ?? 0.86} by default: measured, 0.86 kept the tune in five of eight takes, 0.89 in three, and past 0.9 it goes`}>
          strength
          <input className="h3-in h3-mono" style={{ width: 64 }} type="number" step={0.01} min={STRENGTH[0]} max={STRENGTH[1]}
            aria-label="Theme strength" placeholder={String(target?.capabilities?.theme_strength ?? 0.86)} value={str}
            onChange={(e) => setStr(e.target.value)}
            onBlur={() => {
              const v = str.trim() === "" ? null : Number(str);
              if (v != null && (!Number.isFinite(v) || v < STRENGTH[0] || v > STRENGTH[1])) {
                setStr(strength != null ? String(strength) : "");
                return;
              }
              if ((v ?? undefined) === strength || !th) return;
              const { strength: _, ...rest } = th;
              save({ theme: (v == null ? rest : { ...rest, strength: Math.round(v * 100) / 100 }) as CueTheme });
            }}
            onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()} />
          <span className="h3-muted">{strength == null ? "(the model's)" : ""}</span>
        </span>
      )}
      {th && plan?.theme?.warning && <span className="h3-small h3-cue-offtext">{plan.theme.warning}</span>}
      {swap && (
        <button className="h3-btn" style={{ width: "auto", alignSelf: "flex-start" }}
          title={`${swap.label} ${swap.capabilities?.theme === "melody" ? "sings a theme's melody" : "hears a theme as its timbre"}`}
          onClick={() => save({ model: swap.id })}>
          Use {swap.short ?? swap.label} for the theme
        </button>
      )}
    </div>
  );
}

/** A song take's plan in a line, with its tempo before and after the cue's was set. */
export function SongLine({ song }: { song: CueSong }) {
  const tempo = song.tempo_written != null && song.tempo != null && song.tempo_written !== song.tempo
    ? `its plan written at ${song.tempo_written}, sung at ${song.tempo}` : song.tempo != null ? `sung at ${song.tempo}` : "";
  const how = song.source === "theme plan" ? "the theme's plan" : song.source === "theme transcribed" ? "the theme, transcribed" : "planned by YuE2";
  return (
    <span className="h3-small h3-muted" title={`${how}; ${tempo} bpm; ${song.key ? `key ${song.key}; ` : ""}its first sung note ${song.first_note != null ? `${song.first_note.toFixed(1)} s in` : "—"}; the plan: ${song.file}`}>
      {songSummary(song)}
    </span>
  );
}

/** A song take's planned sections on the cue's bar grid (cue time τ to x: tauX). */
export function SongStrip({ song, g, pps, h = 12 }: { song: CueSong; g: Grid; pps: number; h?: number }) {
  return (
    <div className="h3-cue-songstrip" style={{ position: "relative", height: h }}>
      {songBlocks(song.sections, g).map((b) => (
        <div key={b.i} className={`h3-cue-songsec h3-cue-songsec-${b.i % 2}`}
          style={{ position: "absolute", left: (b.a + g.preroll) * pps, width: (b.b - b.a) * pps, top: 0, bottom: 0 }}
          title={`${b.name}: planned from ${(song.sections[b.i].at).toFixed(1)} s (the cue's in point is 0), ${song.sections[b.i].cue_bars} of the cue's bars`}>
          <span className="h3-small">{b.name}</span>
        </div>
      ))}
    </div>
  );
}
