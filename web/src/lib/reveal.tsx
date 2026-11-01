"use client";

import { useEffect, useRef, type ElementType, type ReactNode } from "react";

/**
 * Adds `is-in` once the element scrolls into view, which plays the CSS entrance (`.reveal`) or the
 * bar growth (`.grow`). Content is only hidden while `html.js` is set, so it never stays invisible
 * without scripts, and reduced motion skips the travel in CSS.
 */
export function Reveal({
  as: Tag = "div",
  className = "",
  delay = 0,
  children,
  ...rest
}: {
  as?: ElementType;
  className?: string;
  delay?: number;
  children: ReactNode;
} & Record<string, unknown>) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          el.classList.add("is-in");
          observer.disconnect();
        }
      },
      { threshold: 0.15 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return (
    <Tag
      ref={ref}
      className={className}
      style={{ "--delay": `${delay}ms` } as React.CSSProperties}
      {...rest}
    >
      {children}
    </Tag>
  );
}
