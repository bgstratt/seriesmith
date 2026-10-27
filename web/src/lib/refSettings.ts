// P4: a ref's sampler settings in the Refs tab -- cfg and the image target's
// knobs (refs.TUNABLE_PARAMS) as form text, turned into override fields, and
// a take's settings made the ref's ("Use these settings"). Pure functions.

import { TUNABLE_PARAMS, type OverrideFields, type RefGenerateRequest, type RefParams, type RefTake } from "../types";

export type Knobs = Record<"cfg" | (typeof TUNABLE_PARAMS)[number], string>;

/** An override's (or effective's) cfg and knobs as form text ("" = not set). */
export function knobsOf(o: { cfg?: number | null; params?: RefParams | null }): Knobs {
  return {
    cfg: o.cfg != null ? String(o.cfg) : "",
    ...(Object.fromEntries(TUNABLE_PARAMS.map((k) => [k, o.params?.[k] != null ? String(o.params[k]) : ""])) as Omit<Knobs, "cfg">),
  };
}

/** The changed knobs as override fields: `cfg`, and `params` whole when any knob changed. */
export function knobFields(k: Knobs, base: Knobs): OverrideFields {
  const out: OverrideFields = {};
  const num = (name: string, v: string) => {
    const n = Number(v);
    if (!Number.isFinite(n)) throw new Error(`${name} must be a number, not "${v}"`);
    return n;
  };
  if (k.cfg !== base.cfg) out.cfg = k.cfg.trim() === "" ? null : num("CFG", k.cfg);
  if (TUNABLE_PARAMS.some((p) => k[p] !== base[p])) {
    const params: RefParams = {};
    for (const p of TUNABLE_PARAMS) {
      const v = k[p].trim();
      if (v) params[p] = p === "sampler" || p === "scheduler" ? v : num(p, v);
    }
    out.params = Object.keys(params).length ? params : null;
  }
  return out;
}

/** "Use these settings": a take's seed, model, LoRAs, steps, cfg, knobs and size as the override. */
export function takeSettings(t: RefTake, keyframe: boolean): OverrideFields {
  const f: OverrideFields = {};
  if (t.seed != null) f.seed = t.seed;
  f.model = t.model || null;
  f.loras = t.loras ?? null;
  if (t.steps != null) f.steps = t.steps;
  if (t.cfg != null) f.cfg = t.cfg;
  f.params = t.params && Object.keys(t.params).length ? t.params : null;
  if (!keyframe && t.width && t.height) f.size = `${t.width}x${t.height}`;
  return f;
}


/**
 * The gallery's Regenerate: this candidate again with a new seed -- its own
 * prompt (as it was drawn, the look included), target, model, LoRAs, steps,
 * cfg, knobs and size; an edited one, the same edit of the same picture. Null
 * for a candidate nothing drew (imported, a frame, a 360, a tour's hold).
 */
export function regenerateRequest(t: RefTake, ref: string, view: string | null, keyframe: boolean): Omit<RefGenerateRequest, "ep"> | null {
  if (t.status !== "ok") return null;
  const base = { ref, view, count: 1, seed_mode: "new" as const, seed: null, note: "", ...(t.target ? { target: t.target } : {}) };
  if (t.source === "edited" && t.edit) {
    return {
      ...base, prompt: t.edit.instruction, model: null, loras: null, steps: null,
      edit: {
        take: t.edit.take, ...(t.edit.with ? { with: t.edit.with } : {}), ...(t.edit.wrap != null ? { wrap: t.edit.wrap } : {}),
        // the picture came from another of the character's views
        ...(t.edit.view && t.edit.view !== view ? { from_view: t.edit.view } : {}),
      },
    };
  }
  if (t.source !== "generated") return null;
  return {
    ...base, prompt: t.prompt ?? null, model: t.model || null, loras: t.loras ?? null, steps: t.steps ?? null,
    ...(t.cfg != null ? { cfg: t.cfg } : {}),
    ...(t.params && Object.keys(t.params).length ? { params: t.params } : {}),
    ...(!keyframe && t.width && t.height ? { size: `${t.width}x${t.height}` } : {}),
  };
}
