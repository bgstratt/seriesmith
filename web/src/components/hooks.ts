import { useEffect, useRef, useState } from "react";
import { loadRefs } from "../actions";
import { detailKey, statusKey, useApp } from "../store";
import type { EpisodeStatus, Pass, Ref, ShotDetail, ShotStatus } from "../types";

export function useStatus(pass?: Pass): EpisodeStatus | undefined {
  return useApp((s) => (s.ep ? s.status[statusKey(s.ep, pass ?? s.pass)] : undefined));
}

/** The episode's refs, fetched the first time something shows them: not with the
 *  episode, whose shots come first and whose opens mostly never look at a ref. A
 *  failed fetch isn't retried here (the Refs tab has Retry). */
export function useRefs(ep: string | null | undefined): Ref[] | undefined {
  const refs = useApp((s) => (ep ? s.refs[ep] : undefined));
  const failed = useApp((s) => !!(ep && s.refsError[ep]));
  useEffect(() => {
    if (ep && !refs && !failed) void loadRefs(ep);
  }, [ep, refs, failed]);
  return refs;
}

export function useShotStatus(shot: string | null | undefined, pass?: Pass): ShotStatus | undefined {
  const st = useStatus(pass);
  return shot ? st?.shots.find((x) => x.shot === shot) : undefined;
}

/** P9: `target` reads the detail for a one-off run on that target (its own
 *  cache entry), so a dialog can show the size and length it would produce. */
export function useDetail(shot: string | null | undefined, pass?: Pass,
                          target?: string | null): ShotDetail | undefined {
  return useApp((s) => (s.ep && shot
    ? s.details[detailKey(s.ep, pass ?? s.pass, shot, target)]
    : undefined));
}

export function useDetailError(shot: string | null | undefined, pass?: Pass): string | undefined {
  return useApp((s) => (s.ep && shot ? s.detailError[detailKey(s.ep, pass ?? s.pass, shot)] : undefined));
}

/** width / height of the episode's frames, for thumbnail boxes */
export function aspectOf(st: EpisodeStatus | undefined): number {
  const w = st?.width;
  const h = st?.height;
  return w && h ? w / h : 16 / 9;
}

/** The element's current size (ResizeObserver). */
export function useSize<T extends HTMLElement>(): [React.RefObject<T>, { width: number; height: number }] {
  const ref = useRef<T>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([e]) => {
      const r = e.contentRect;
      setSize((s) => (s.width === r.width && s.height === r.height ? s : { width: r.width, height: r.height }));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, size];
}
