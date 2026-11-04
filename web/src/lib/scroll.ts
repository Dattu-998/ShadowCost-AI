"use client";

import { useEffect, type RefObject } from "react";

/**
 * Scroll-linked progress for one element, written straight to its `--p` custom property (0 to 1)
 * on each animation frame, so a scrubbed move costs no React render. `mode`:
 * - "leave": 0 while the element's top is at the viewport top, 1 once its bottom reaches it;
 * - "hold": progress through a tall section whose sticky stage is held for (height - 1) screens.
 * `onChange` receives the same value for the few moves that need state. Reduced motion pins it at 1.
 */
export function useScrollProgress(
  ref: RefObject<HTMLElement | null>,
  mode: "leave" | "hold",
  onChange?: (p: number) => void,
) {
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      el.style.setProperty("--p", "1");
      onChange?.(1);
      return;
    }
    let frame = 0;
    const measure = () => {
      frame = 0;
      const box = el.getBoundingClientRect();
      const travel = mode === "leave" ? box.height : box.height - window.innerHeight;
      const p = travel > 0 ? Math.min(1, Math.max(0, -box.top / travel)) : 0;
      el.style.setProperty("--p", p.toFixed(4));
      onChange?.(p);
    };
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(measure);
    };
    measure();
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
    };
  }, [ref, mode, onChange]);
}
