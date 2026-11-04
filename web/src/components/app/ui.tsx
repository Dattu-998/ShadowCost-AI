import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";
import { STAGES, type Stage } from "@/lib/api";

/* Framed sheet (app style): flat panels with a 1px edge, one 10px radius, colour only on data. */

export const fmt = {
  pct: (v: number | null | undefined, digits = 0) =>
    v === null || v === undefined ? "—" : `${(v * 100).toFixed(digits)}%`,
  num: (v: number | null | undefined, digits = 0) =>
    v === null || v === undefined
      ? "—"
      : v.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits }),
  date: (iso: string | null | undefined) =>
    iso
      ? new Date(`${iso.slice(0, 10)}T00:00:00Z`).toLocaleDateString("en-GB", {
          day: "numeric",
          month: "short",
          year: "numeric",
          timeZone: "UTC",
        })
      : "—",
  shortDate: (iso: string) =>
    new Date(`${iso.slice(0, 10)}T00:00:00Z`).toLocaleDateString("en-GB", {
      day: "numeric",
      month: "short",
      timeZone: "UTC",
    }),
};

export const STAGE_LABEL: Record<Stage, string> = {
  shadow: "Shadow",
  draft: "Draft",
  approval: "Approval",
  autonomous: "Autonomous",
};
const STAGE_FILL: Record<Stage, string> = {
  shadow: "bg-slate",
  draft: "bg-blush",
  approval: "bg-sage",
  autonomous: "bg-olive",
};

export function Panel({
  title,
  aside,
  children,
  className = "",
}: {
  title?: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-[10px] border border-edge bg-sheet ${className}`}>
      {title && (
        <header className="flex min-h-12 items-center justify-between gap-4 px-5 pt-4">
          <h2 className="text-[15px] font-semibold">{title}</h2>
          {aside}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

/** One container split by dividers: label over value, a caption naming the baseline. */
export function Kpis({
  items,
}: {
  items: { label: string; value: ReactNode; caption?: ReactNode }[];
}) {
  return (
    <dl className="grid grid-cols-2 overflow-hidden rounded-[10px] border border-edge bg-sheet md:grid-flow-col md:grid-cols-none md:auto-cols-fr">
      {items.map((item, i) => (
        <div
          key={item.label}
          className={`px-5 py-4 ${i > 0 ? "border-edge md:border-l" : ""} ${i > 1 ? "border-t md:border-t-0" : ""} ${i % 2 === 1 ? "border-l" : ""}`}
        >
          <dt className="text-[13px] text-muted">{item.label}</dt>
          <dd className="mt-1 text-[26px] font-semibold leading-tight tracking-tight">
            {item.value}
          </dd>
          {item.caption && <dd className="mt-1 text-[12px] text-muted">{item.caption}</dd>}
        </div>
      ))}
    </dl>
  );
}

export function TitleRow({
  title,
  line,
  action,
}: {
  title: ReactNode;
  line?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-[24px] font-semibold tracking-tight">{title}</h1>
        {line && <p className="mt-1 max-w-[80ch] text-[15px] text-muted">{line}</p>}
      </div>
      {action}
    </div>
  );
}

export function ButtonLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link
      href={href}
      className="press inline-flex h-9 items-center rounded-md bg-ink px-4 text-[14px] font-semibold text-sheet hover:bg-olive"
    >
      {children}
    </Link>
  );
}

export function Button({
  variant = "primary",
  className = "",
  ...props
}: ComponentProps<"button"> & { variant?: "primary" | "secondary" | "quiet" }) {
  const styles = {
    primary: "bg-ink text-sheet hover:bg-olive disabled:bg-control disabled:text-muted",
    secondary: "border border-control bg-sheet hover:bg-hover disabled:text-muted",
    quiet: "text-ink hover:bg-hover",
  }[variant];
  return (
    <button
      {...props}
      className={`press inline-flex h-9 items-center justify-center whitespace-nowrap rounded-md px-4 text-[14px] font-semibold disabled:cursor-not-allowed ${styles} ${className}`}
    />
  );
}

export function Pill({
  tone = "neutral",
  children,
}: {
  tone?: "neutral" | "good" | "bad" | "wait";
  children: ReactNode;
}) {
  const styles = {
    neutral: "bg-frame text-ink",
    good: "bg-good-tint text-good",
    bad: "bg-bad-tint text-bad",
    wait: "bg-wait-tint text-wait",
  }[tone];
  return (
    <span className={`inline-flex h-6 items-center rounded-full px-2.5 text-[12px] font-semibold ${styles}`}>
      {children}
    </span>
  );
}

/**
 * The signature element: an agent's place on the autonomy ladder. Each stage it has reached is
 * filled in that stage's colour, the same colours as the landing page's chapters.
 */
export function Ladder({ stage, approved = true }: { stage: Stage | null; approved?: boolean }) {
  const reached = stage ? STAGES.indexOf(stage) : -1;
  return (
    <div
      role="img"
      aria-label={approved ? `On the ladder at ${stage ? STAGE_LABEL[stage] : "not started"}` : "Waiting for approval"}
      className="grid grid-cols-4 gap-1"
    >
      {STAGES.map((s, i) => (
        <div key={s} className="min-w-0">
          <div className={`h-2 rounded-full ${approved && i <= reached ? STAGE_FILL[s] : "bg-rule"}`} />
          <p
            className={`mt-1.5 truncate text-[12px] ${approved && i === reached ? "font-semibold text-ink" : "text-muted"}`}
          >
            {STAGE_LABEL[s]}
          </p>
        </div>
      ))}
    </div>
  );
}

export function Loading({ label = "Loading", rows = 3 }: { label?: string; rows?: number }) {
  return (
    <div role="status" aria-label={label} className="space-y-3">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="h-4 rounded bg-rule" style={{ width: `${90 - i * 18}%` }} />
      ))}
    </div>
  );
}

export function ErrorNote({ error, retry }: { error: Error; retry?: () => void }) {
  return (
    <div role="alert" className="rounded-md bg-bad-tint px-4 py-3 text-[14px] text-bad">
      <p className="font-semibold">That didn&apos;t load.</p>
      <p className="mt-1">{error.message}</p>
      {retry && (
        <button onClick={retry} className="mt-2 font-semibold underline">
          Try again
        </button>
      )}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-md border border-dashed border-control px-4 py-6 text-center text-[14px] text-muted">
      {children}
    </div>
  );
}

export function Tabs<T extends string>({
  items,
  value,
  onChange,
  label,
}: {
  items: { id: T; label: ReactNode }[];
  value: T;
  onChange: (id: T) => void;
  label: string;
}) {
  return (
    <div role="tablist" aria-label={label} className="flex gap-6 border-b border-rule">
      {items.map((item) => (
        <button
          key={item.id}
          role="tab"
          aria-selected={item.id === value}
          onClick={() => onChange(item.id)}
          className={`-mb-px border-b-2 pb-2.5 text-[14px] ${item.id === value ? "border-ink font-semibold text-ink" : "border-transparent text-muted hover:text-ink"}`}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
