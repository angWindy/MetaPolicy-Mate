"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

/**
 * Lightweight IntersectionObserver-based reveal wrapper. Replaces the
 * `motion/react`-based version from the Luu branch so the page can render
 * even before the `motion` npm package is installed. Adds a CSS class once
 * the element scrolls into view — animations are driven by CSS.
 *
 * To enable spring animations in the future, install `motion` and swap
 * the inner implementation for the `motion/react` `motion.div` primitive.
 */
type MotionRevealProps = {
  children: ReactNode;
  className?: string;
  delay?: number;
  distance?: number;
};

export function MotionReveal({
  children,
  className,
  delay = 0,
  distance = 12,
}: MotionRevealProps) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [shown, setShown] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const el = ref.current;
    if (!el) return;
    if (typeof IntersectionObserver === "undefined") {
      // Defer to avoid cascading-render warnings — the state change
      // happens in a microtask instead of the effect body.
      const handle = window.setTimeout(() => setShown(true), 0);
      return () => window.clearTimeout(handle);
    }
    const obs = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setShown(true);
            obs.disconnect();
            break;
          }
        }
      },
      { threshold: 0.08, rootMargin: "0px 0px -4%" },
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  const cls = [
    className,
    "motion-reveal",
    shown ? "motion-reveal--shown" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div
      ref={ref}
      className={cls}
      style={{
        // The CSS module is inlined here so we don't need a separate
        // stylesheet; consumers can override with their own class.
        transitionDelay: `${delay}s`,
        transitionDuration: "0.54s",
        transitionProperty: "opacity, transform",
        transitionTimingFunction: "cubic-bezier(0.16, 1, 0.3, 1)",
        opacity: shown ? 1 : 0.82,
        transform: shown ? "translateY(0)" : `translateY(${Math.min(distance, 12)}px)`,
      }}
    >
      {children}
    </div>
  );
}

export default MotionReveal;
