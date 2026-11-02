// Turn (a character's view drawn from another it has): which model it runs on.
// Qwen-Image 2.1 with the Multiple-Angles LoRA turns a figure best; any other
// edit model is told the turn in words (refs.py VIEW_TURNS_PROSE). With nothing
// chosen, the server picks: Qwen 2.1 + angles when it is installed, else the
// episode's Edits model. The choice is this viewer's, kept in this browser.

import { useSyncExternalStore } from "react";
import type { Target, TargetList } from "../types";
import { imageTargets, isEditTarget } from "./imageTargets";
import { normReadiness, pickWarning } from "./readiness";
import { targetLabel } from "./targets";

/** refs.py TURN_TARGET: the model the angles LoRA is for. */
export const TURN_TARGET = "qwen_image_21";
export const TURN_ANGLES_LABEL = "Qwen 2.1 + angles";
const KEY = "seriesmith.turnModel";

export function readTurnModel(): string {
  try {
    return localStorage.getItem(KEY) ?? "";
  } catch {
    return "";
  }
}

let current: string | null = null;
const listeners = new Set<() => void>();

/** The chosen model ("" = automatic), shared by every Turn button on the page. */
export function turnModel(): string {
  if (current === null) current = readTurnModel();
  return current;
}

export function setTurnModel(id: string): void {
  current = id;
  try {
    if (id) localStorage.setItem(KEY, id);
    else localStorage.removeItem(KEY);
  } catch {
    /* private window: until reload */
  }
  listeners.forEach((f) => f());
}

function subscribe(f: () => void): () => void {
  listeners.add(f);
  return () => { listeners.delete(f); };
}

export function useTurnModel(): [string, (id: string) => void] {
  return [useSyncExternalStore(subscribe, turnModel, turnModel), setTurnModel];
}

/** The other edit models a turn can run on (in words): every edit-capable image target but Qwen 2.1. */
export function turnChoices(list: TargetList | null | undefined): Target[] {
  return imageTargets(list).filter((t) => isEditTarget(t) && t.id !== TURN_TARGET);
}

export interface TurnPlan {
  /** the request's `target`: null lets the server choose */
  target: string | null;
  /** the model it will run on, as said in the tooltip */
  uses: string;
  /** with the angles LoRA, or told in words */
  how: "angles" | "words";
  /** the chosen model's readiness warning, if any */
  warn: { severity: "err" | "warn"; text: string } | null;
}

/**
 * What a Turn sends and runs on: the viewer's choice when it is still a model
 * here, else automatic (Qwen 2.1 + angles unless it's known not to be ready,
 * else the episode's Edits model `edits`).
 */
export function turnPlan(list: TargetList | null | undefined, chosen: string, edits: string): TurnPlan {
  const qwen = imageTargets(list).find((t) => t.id === TURN_TARGET);
  if (chosen === TURN_TARGET && qwen) {
    return { target: TURN_TARGET, uses: `${TURN_ANGLES_LABEL} (the multiple-angles LoRA)`, how: "angles",
      warn: pickWarning(TURN_ANGLES_LABEL, qwen.readiness) };
  }
  const own = chosen ? turnChoices(list).find((t) => t.id === chosen) : undefined;
  if (own) {
    return { target: own.id, uses: `${targetLabel(list, own.id)}, told the turn in words`, how: "words",
      warn: pickWarning(targetLabel(list, own.id), own.readiness) };
  }
  const qwenOut = !qwen || (qwen.readiness ? normReadiness(qwen.readiness).status === "not_ready" : false);
  if (!qwenOut) {
    return { target: null, how: "angles", warn: null,
      uses: `${TURN_ANGLES_LABEL} when the angles LoRA is installed, else the episode's Edits model${edits ? ` (${targetLabel(list, edits)})` : ""}` };
  }
  const t = imageTargets(list).find((x) => x.id === edits);
  return { target: null, how: "words", warn: t ? pickWarning(targetLabel(list, edits), t.readiness) : null,
    uses: edits ? `the episode's Edits model, ${targetLabel(list, edits)}, told the turn in words (${TURN_ANGLES_LABEL} isn't installed)`
      : "the episode's Edits model (none is chosen: pick one under Made with)" };
}
