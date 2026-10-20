// The series config's render profiles (`profiles`, named by `profile:` in the
// script): model settings (target, model, loras, steps, sla) and what they add to
// a shot's prompt (look words, a lens). targets/__init__.py series_profiles and
// core/series_config.py profile_styles read them; core/story.py opens a shot's
// action with the look words, then the lens sentence, as styledPrompt does here.

import { getPath, type Raw } from "./seriesForm";

export interface Profile {
  target?: string;
  model?: string;
  /** LoRA names ("name" or "name:0.6"), or ["none"] for none */
  loras?: unknown;
  steps?: number;
  sla?: "on" | "off";
  /** words added to the series look for this profile's shots */
  look?: string;
  /** a lens id (core/framing.py LENSES) */
  lens?: string;
  [k: string]: unknown;
}

/** The profiles, by name (keys starting with _ are comments, left out). */
export function profilesOf(raw: Raw | null | undefined): Record<string, Profile> {
  const all = (getPath(raw ?? {}, ["profiles"]) ?? {}) as Record<string, unknown>;
  const out: Record<string, Profile> = {};
  for (const [k, v] of Object.entries(all)) {
    if (!k.startsWith("_") && v && typeof v === "object" && !Array.isArray(v)) out[k] = v as Profile;
  }
  return out;
}

/** `raw` with profile `name` set to `p` (empty fields left out), or removed (null).
 * Other profiles, comments and the profile's own unknown keys are kept as they were. */
export function setProfile(raw: Raw, name: string, p: Profile | null): Raw {
  const all = { ...((getPath(raw, ["profiles"]) ?? {}) as Record<string, unknown>) };
  if (p === null) delete all[name];
  else {
    const clean: Profile = {};
    for (const [k, v] of Object.entries(p)) {
      if (v === undefined || v === null || v === "" || (Array.isArray(v) && !v.length)) continue;
      clean[k] = v;
    }
    all[name] = clean;
  }
  const next = { ...raw };
  if (Object.keys(all).length) next.profiles = all;
  else delete next.profiles;
  return next;
}

/** A name a profile can have (what `profile:` names): letters, digits, _ and -. */
export function profileNameOk(name: string): boolean {
  return /^[A-Za-z0-9_-]+$/.test(name);
}

/** A profile's LoRAs as one line of text ("a.safetensors:0.6, b.safetensors"). */
export function lorasText(v: unknown): string {
  const list = Array.isArray(v) ? v : typeof v === "string" ? [v] : [];
  return list.map((x) => (typeof x === "string" ? x
    : x && typeof x === "object" && "name" in x
      ? `${(x as { name: string }).name}${(x as { strength?: number }).strength != null && (x as { strength?: number }).strength !== 1
        ? `:${(x as { strength: number }).strength}` : ""}`
      : "")).filter(Boolean).join(", ");
}

/** That line back as a profile's `loras` (undefined when empty). */
export function lorasValue(text: string): string[] | undefined {
  const list = text.split(",").map((s) => s.trim()).filter(Boolean);
  return list.length ? list : undefined;
}

/** A sentence: the first letter up, one full stop. */
function sentence(words: string): string {
  const w = words.trim().replace(/\.+$/, "");
  return w ? `${w[0].toUpperCase()}${w.slice(1)}.` : "";
}

/** A prompt opened by a profile's look words and its lens clause (as core/story.py
 * opens a shot's action), unless it already opens with them. */
export function styledPrompt(prompt: string, look?: string, lensClause?: string): string {
  const lead = [look ? sentence(look) : "", lensClause ? sentence(lensClause) : ""].filter(Boolean).join(" ");
  if (!lead || prompt.startsWith(lead)) return prompt;
  return prompt ? `${lead} ${prompt}` : lead;
}

/** A profile's LoRAs as {name, strength} ("none" is none: an empty list). */
export function lorasList(v: unknown): { name: string; strength: number }[] {
  const out: { name: string; strength: number }[] = [];
  for (const x of Array.isArray(v) ? v : typeof v === "string" ? [v] : []) {
    if (typeof x === "string") {
      const s = x.trim();
      if (!s || ["none", "off", "-"].includes(s.toLowerCase())) continue;
      const m = s.match(/^(.*):(\d*\.?\d+)$/);
      out.push(m ? { name: m[1], strength: Number(m[2]) } : { name: s, strength: 1 });
    } else if (x && typeof x === "object" && typeof (x as { name?: unknown }).name === "string") {
      const o = x as { name: string; strength?: number };
      out.push({ name: o.name, strength: o.strength ?? 1 });
    }
  }
  return out;
}

/** What a profile changes in a new take (the New take dialog): the model settings
 * it sets, and the prompt opened by its look words and lens (unless the prompt
 * is the model's own, `lockPrompt`). Only what the profile sets is returned. */
export function profileRunPatch(p: Profile, prompt: string, lockPrompt: boolean, lensClause?: string): {
  target?: string; model?: string; steps?: string; loras?: { name: string; strength: number }[]; prompt?: string;
} {
  const out: ReturnType<typeof profileRunPatch> = {};
  if (p.target) out.target = p.target;
  if (p.model) out.model = p.model;
  if (p.steps) out.steps = String(p.steps);
  if (p.loras !== undefined) out.loras = lorasList(p.loras);
  if (!lockPrompt && (p.look || lensClause)) {
    const next = styledPrompt(prompt, p.look, lensClause);
    if (next !== prompt) out.prompt = next;
  }
  return out;
}

/** The shot form's keys a profile can carry (with `sla:`, which the form keeps
 * among its other lines). */
const SHOT_PROFILE_KEYS = ["lens", "target", "model", "lora", "steps"] as const;
const SLA_LINE = /^sla\s*:\s*(on|off)\s*$/i;

/** A profile made from a shot's own settings (the shot form's "Save as profile…"):
 * its lens, video model, model file, LoRAs, steps and `sla:`. Empty when it sets none. */
export function profileFromShot(keys: Record<string, string>, other: string[] = []): Profile {
  const p: Profile = {};
  const v = (k: string) => (keys[k] ?? "").trim();
  if (v("lens")) p.lens = v("lens");
  if (v("target")) p.target = v("target");
  if (v("model")) p.model = v("model");
  if (v("lora")) p.loras = lorasValue(v("lora"));
  const steps = parseInt(v("steps"), 10);
  if (Number.isFinite(steps) && steps > 0) p.steps = steps;
  const sla = other.map((l) => l.trim().match(SLA_LINE)).find(Boolean);
  if (sla) p.sla = sla[1].toLowerCase() as "on" | "off";
  return p;
}

/** The shot's form on profile `name`: `profile:` set, and the lines the profile now
 * carries taken off the shot (they would otherwise still win over it). */
export function shotOnProfile<F extends { keys: Record<string, string>; other: string[] }>(form: F, name: string): F {
  const keys: Record<string, string> = { ...form.keys, profile: name };
  for (const k of SHOT_PROFILE_KEYS) delete keys[k];
  return { ...form, keys, other: form.other.filter((l) => !SLA_LINE.test(l.trim())) };
}
