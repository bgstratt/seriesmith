// A stretch of a longer sound, heard on its own: a shot's aligned window of the recording.

import { useEffect, useRef, useState } from "react";

export function WindowPlayer({ url, from, to, title }: { url: string; from: number; to: number; title?: string }) {
  const audio = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [at, setAt] = useState(0);
  useEffect(() => () => audio.current?.pause(), []);
  // another window, or another recording: start again from the new one
  useEffect(() => {
    audio.current?.pause();
    audio.current = null;
    setPlaying(false);
    setAt(0);
  }, [url, from, to]);

  function toggle() {
    if (playing) {
      audio.current?.pause();
      setPlaying(false);
      return;
    }
    const a = audio.current ?? new Audio(url);
    audio.current = a;
    const stop = () => {
      a.pause();
      a.currentTime = from;
      setPlaying(false);
      setAt(0);
    };
    a.ontimeupdate = () => {
      if (a.currentTime >= to) stop();
      else setAt(Math.max(0, a.currentTime - from));
    };
    a.onended = stop;
    a.onerror = () => setPlaying(false);
    const start = () => {
      if (a.currentTime < from || a.currentTime >= to) a.currentTime = from;
      setPlaying(true);
      void a.play().catch(() => setPlaying(false));
    };
    if (a.readyState >= 1) start();
    else a.addEventListener("loadedmetadata", start, { once: true });
  }

  return (
    <span className="h3-row" style={{ gap: 6 }}>
      <button className="h3-btn h3-icon" type="button" title={title ?? `Hear ${from.toFixed(2)}–${to.toFixed(2)} s`} aria-label={playing ? "Stop" : "Hear this stretch"} onClick={toggle}>
        <i className={`pi ${playing ? "pi-stop" : "pi-play"}`} />
      </button>
      <span className="h3-small h3-muted h3-mono">{at.toFixed(1)} / {(to - from).toFixed(1)} s</span>
    </span>
  );
}
