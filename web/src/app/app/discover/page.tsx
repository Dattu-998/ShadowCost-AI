"use client";

import { useState } from "react";
import { Empty, ErrorNote, fmt, Kpis, Loading, Panel, Pill, TitleRow } from "@/components/app/ui";
import { TRAIN_DAYS, useDiscovery } from "@/lib/hooks";

/*
 * Discover. Question: which repeated work is worth handing over, and why do we believe it
 * repeats? The share table (rows filled by their share of the hours) answers first; the
 * selected workflow's evidence sits beside it.
 */

const TRIGGER_KIND: Record<string, string> = {
  event: "Set off by an outside event",
  new_row: "Set off by a new row",
  schedule: "On a weekly schedule",
  none: "No consistent trigger",
};

export default function DiscoverPage() {
  const { data, error, isLoading, mutate } = useDiscovery();
  const [selected, setSelected] = useState(0);
  const workflows = data?.workflows ?? [];
  const totalHours = workflows.reduce((s, w) => s + w.hours_per_month, 0);
  const maxHours = Math.max(...workflows.map((w) => w.hours_per_month), 1);
  const w = workflows[Math.min(selected, workflows.length - 1)];

  return (
    <div className="space-y-6">
      <TitleRow
        title="Repeated work"
        line={
          data
            ? `Learned from ${fmt.date(data.evidence_from)} to ${fmt.date(data.evidence_to)} (the first ${TRAIN_DAYS} days). Every time estimate lists its assumptions.`
            : "Looking for work that keeps coming back…"
        }
      />
      {error && <ErrorNote error={error} retry={() => mutate()} />}

      <Kpis
        items={[
          { label: "Workflows", value: data ? workflows.length : "—", caption: "repeated and explained by a trigger" },
          { label: "Episodes of work", value: data ? fmt.num(data.episodes) : "—", caption: "one case, one day" },
          { label: "Email templates", value: data ? data.templates : "—", caption: "kinds of email, whatever the wording" },
          { label: "Repeated work", value: data ? `${fmt.num(totalHours, 1)} h` : "—", caption: "per month, estimated" },
        ]}
      />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Panel title="Workflows, by hours a month">
          {isLoading && <Loading rows={3} />}
          {data && workflows.length === 0 && <Empty>No work repeats often enough in this period.</Empty>}
          {workflows.length > 0 && (
            <table className="w-full text-[14px]">
              <thead>
                <tr className="text-left text-[12px] text-muted">
                  <th className="pb-2 font-normal">Work</th>
                  <th className="pb-2 text-right font-normal">Per month</th>
                  <th className="pb-2 text-right font-normal">Hours</th>
                </tr>
              </thead>
              <tbody>
                {workflows.map((wf, i) => (
                  <tr
                    key={wf.workflow_id}
                    onClick={() => setSelected(i)}
                    className="cursor-pointer"
                    aria-selected={i === selected}
                  >
                    <td className="py-1 pr-3">
                      <button
                        onClick={() => setSelected(i)}
                        className={`relative w-full overflow-hidden rounded-lg px-3 py-2.5 text-left ${i === selected ? "outline outline-2 outline-ink" : ""}`}
                      >
                        <span
                          aria-hidden
                          className="absolute inset-y-0 left-0 bg-[#e3e9e5]"
                          style={{ width: `${(wf.hours_per_month / maxHours) * 100}%` }}
                        />
                        <span className="relative block truncate font-semibold">{wf.trigger.description}</span>
                        <span className="relative block truncate text-[12px] text-muted">{wf.name}</span>
                      </button>
                    </td>
                    <td className="tabular py-1 text-right">{fmt.num(wf.instances_per_month, 1)}</td>
                    <td className="tabular py-1 pl-3 text-right font-semibold">{fmt.num(wf.hours_per_month, 1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {data && data.irregular.length > 0 && (
            <p className="mt-4 text-[13px] text-muted">
              Also repeated, but with no consistent trigger (poor targets):{" "}
              {data.irregular.map((x) => `${x.name} (${x.instances})`).join("; ")}.
            </p>
          )}
        </Panel>

        <Panel title={w ? `Evidence for ${w.workflow_id}` : "Evidence"}>
          {!w && <Loading rows={5} />}
          {w && (
            <div className="space-y-5 text-[14px]">
              <div>
                <p className="text-[12px] text-muted">{TRIGGER_KIND[w.trigger.kind] ?? w.trigger.kind}</p>
                <p className="mt-0.5 text-[16px] font-semibold">{w.trigger.description}</p>
                <p className="mt-1 text-muted">
                  Explains {fmt.pct(w.trigger.support)} of {w.instances} cases. Consistency{" "}
                  {fmt.pct(w.consistency)}; automation score {fmt.num(w.automation_score, 2)}.
                </p>
              </div>
              {w.condition && (
                <div>
                  <p className="text-[12px] text-muted">Rule recovered from the rows</p>
                  <p className="mt-0.5 font-semibold">{w.condition.description}</p>
                  <p className="mt-1 text-muted">
                    Covers {fmt.pct(w.condition.support)} of cases. Of the rows meeting it on those days,{" "}
                    {fmt.pct(w.condition.precision)} were worked on; the rest is the person&apos;s judgment.
                  </p>
                </div>
              )}
              <div>
                <p className="text-[12px] text-muted">How it was done</p>
                <ul className="mt-1 divide-y divide-rule">
                  {w.variants.map((v) => (
                    <li key={v.steps.join("|")} className="flex justify-between gap-4 py-2">
                      <span className="min-w-0">{v.steps.join(" + ")}</span>
                      <span className="tabular shrink-0 text-muted">{v.count}×</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <p className="text-[12px] text-muted">Time per case</p>
                <p className="tabular mt-0.5">
                  <span className="font-semibold">{fmt.num(w.minutes_per_instance, 1)} min</span> estimated
                  {w.observed_minutes !== null && (
                    <span className="text-muted"> · at most {fmt.num(w.observed_minutes, 1)} min observed from email gaps</span>
                  )}
                </p>
                <p className="mt-1 text-[13px] text-muted">Assumes {w.assumptions.join("; ")}.</p>
              </div>
              {w.caveats.map((c) => (
                <Pill key={c} tone="wait">
                  {c}
                </Pill>
              ))}
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}
