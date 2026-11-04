"use client";

import { useState } from "react";
import type { ShadowRun } from "@/lib/api";
import { fmt, STAGE_LABEL } from "./ui";

/*
 * Charts drawn to the app rules: one hue on the main data (olive), neutrals for the rest, 3-5
 * faint gridlines, no y-axis line, values in the tooltip rather than on every mark.
 */

const OLIVE = "#1f3527";
const NEUTRAL = ["#b3bcc3", "#d9dee2"];

/** Events per week, stacked: the company's own spreadsheet work in olive, the outside world grey. */
export function WeeklyActivity({
  weeks,
}: {
  weeks: ({ week: string } & Record<string, number | string>)[];
}) {
  const [hover, setHover] = useState<number | null>(null);
  const series = ["spreadsheet", "email", "bank"] as const;
  const colors = { spreadsheet: OLIVE, email: NEUTRAL[0], bank: NEUTRAL[1] };
  const totals = weeks.map((w) => series.reduce((sum, s) => sum + Number(w[s] ?? 0), 0));
  const max = Math.max(...totals, 1);
  const top = Math.ceil(max / 10) * 10;
  const W = 640;
  const H = 180;
  const band = W / weeks.length;
  const bar = Math.max(band * 0.62, 2);
  const shown = hover === null ? null : weeks[hover];

  return (
    <figure>
      <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-muted">
        {series.map((s) => (
          <span key={s} className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-[2px]" style={{ background: colors[s] }} />
            {s === "spreadsheet" ? "Spreadsheet edits" : s === "email" ? "Emails" : "Bank payments"}
          </span>
        ))}
        <span className="ml-auto tabular text-ink">
          {shown
            ? `Week of ${fmt.shortDate(String(shown.week))}: ${series.map((s) => `${shown[s] ?? 0}`).join(" / ")}`
            : `${fmt.num(totals.reduce((a, b) => a + b, 0))} events`}
        </span>
      </div>
      <svg
        viewBox={`0 0 ${W} ${H + 22}`}
        className="h-auto w-full"
        role="img"
        aria-label="Events per week by source"
        onMouseLeave={() => setHover(null)}
      >
        {[0, 0.5, 1].map((f) => (
          <g key={f}>
            <line x1={0} x2={W} y1={H - f * H} y2={H - f * H} stroke="#eef0f2" />
            <text x={W} y={H - f * H - 4} textAnchor="end" fontSize="11" fill="#5b6670">
              {Math.round(top * f)}
            </text>
          </g>
        ))}
        {weeks.map((w, i) => {
          let y = H;
          return (
            <g key={String(w.week)} onMouseEnter={() => setHover(i)}>
              <rect x={i * band} y={0} width={band} height={H} fill="transparent" />
              {series.map((s) => {
                const h = (Number(w[s] ?? 0) / top) * H;
                y -= h;
                return (
                  <rect
                    key={s}
                    x={i * band + (band - bar) / 2}
                    y={y}
                    width={bar}
                    height={h}
                    fill={colors[s]}
                    opacity={hover === null || hover === i ? 1 : 0.45}
                  />
                );
              })}
            </g>
          );
        })}
        {weeks.map((w, i) =>
          i % Math.ceil(weeks.length / 6) === 0 ? (
            <text key={String(w.week)} x={i * band + band / 2} y={H + 16} fontSize="11" fill="#5b6670" textAnchor="middle">
              {fmt.shortDate(String(w.week))}
            </text>
          ) : null,
        )}
      </svg>
    </figure>
  );
}

/** Agreement with the person so far, case by case, with each promotion marked where it happened. */
export function AgreementChart({ run }: { run: ShadowRun }) {
  // Drawn near its rendered width so 12px labels stay 12px; agreement is plotted from 40% up.
  const W = 1100;
  const H = 230;
  const TOP = 26;
  const FLOOR = 0.4;
  const n = run.points.length;
  if (!n) return null;
  const x = (i: number) => (i / Math.max(n - 1, 1)) * W;
  const y = (v: number) => TOP + (1 - (Math.max(v, FLOOR) - FLOOR) / (1 - FLOOR)) * (H - TOP);
  const path = run.points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.agreement_so_far).toFixed(1)}`).join(" ");
  const changeIndex = run.changes.map((c) => ({
    ...c,
    i: Math.max(0, run.points.findIndex((p) => p.day >= c.day)),
  }));
  const bound = run.policy.promote_lower_bound;

  return (
    <figure>
      <svg viewBox={`0 0 ${W} ${H + 24}`} className="h-auto w-full" role="img" aria-label="Running agreement with the person">
        {[0.5, 0.75, 1].map((v) => (
          <g key={v}>
            <line x1={0} x2={W} y1={y(v)} y2={y(v)} stroke="#eef0f2" />
            <text x={4} y={y(v) - 5} fontSize="12" fill="#5b6670">
              {fmt.pct(v)}
            </text>
          </g>
        ))}
        <line x1={0} x2={W} y1={y(bound)} y2={y(bound)} stroke="#5b6670" strokeDasharray="4 4" />
        <text x={W - 4} y={y(bound) + 15} fontSize="12" fill="#5b6670" textAnchor="end">
          bar to clear: lower bound {bound}
        </text>
        {changeIndex.map((c) => (
          <g key={c.day + c.to}>
            <line x1={x(c.i)} x2={x(c.i)} y1={TOP - 8} y2={H} stroke="#c9d0d6" />
            <text x={x(c.i) + 5} y={14} fontSize="12" fill="#1c1c1c">
              {c.action === "promote" ? "to" : "back to"} {STAGE_LABEL[c.to]}
            </text>
          </g>
        ))}
        <path d={path} fill="none" stroke={OLIVE} strokeWidth={2} />
        <text x={0} y={H + 18} fontSize="12" fill="#5b6670">
          {fmt.shortDate(run.points[0].day)}
        </text>
        <text x={W} y={H + 18} fontSize="12" fill="#5b6670" textAnchor="end">
          {fmt.shortDate(run.points[n - 1].day)}
        </text>
      </svg>
      <figcaption className="mt-2 text-[12px] text-muted">
        Running share of cases where the agent did what the person did. Promotion needs{" "}
        {run.policy.min_cases} cases at a stage with a 95% lower bound of {bound} or more.
      </figcaption>
    </figure>
  );
}
