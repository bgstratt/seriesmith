// A panel's List / Board choice, remembered in this browser (the Shots and
// Refs tabs each keep their own).

import { useState } from "react";

export type View = "list" | "board";

export function readView(key: string): View {
  try {
    return localStorage.getItem(key) === "board" ? "board" : "list";
  } catch {
    return "list";
  }
}

export function useView(key: string): [View, (v: View) => void] {
  const [view, setView] = useState<View>(() => readView(key));
  const set = (v: View) => {
    setView(v);
    try {
      localStorage.setItem(key, v);
    } catch {
      /* private window: until reload */
    }
  };
  return [view, set];
}
