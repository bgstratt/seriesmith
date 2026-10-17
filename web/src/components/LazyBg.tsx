// A picture drawn as a background only once its box is near the screen: the
// Refs tab lists hundreds of refs, and asking for every thumbnail at once
// queues them all, while only the dozen in view are seen. Where there is no
// IntersectionObserver (tests, old browsers) the picture loads at once.

import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";

/** [a ref for the element, whether it has come near the screen (it stays true)] */
export function useNearScreen<T extends Element>(margin = "300px"): [React.RefObject<T | null>, boolean] {
  const ref = useRef<T | null>(null);
  const [near, setNear] = useState(() => typeof IntersectionObserver === "undefined");
  useEffect(() => {
    if (near || !ref.current || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) {
        setNear(true);
        io.disconnect();
      }
    }, { rootMargin: margin });
    io.observe(ref.current);
    return () => io.disconnect();
  }, [near, margin]);
  return [ref, near];
}

/** A `div` whose `style.backgroundImage` waits until it is near the screen. */
export function LazyBg({ className, style, title, children, as = "div" }: {
  className?: string; style?: CSSProperties; title?: string; children?: ReactNode; as?: "div" | "span";
}) {
  const [ref, near] = useNearScreen<HTMLElement>();
  const shown = near ? style : { ...style, backgroundImage: undefined };
  const Tag = as;
  return <Tag ref={ref as React.RefObject<never>} className={className} style={shown} title={title}>{children}</Tag>;
}
