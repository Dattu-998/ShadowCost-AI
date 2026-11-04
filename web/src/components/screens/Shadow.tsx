"use client";

import Link from "next/link";
import { useState } from "react";
import { AgreementChart } from "@/components/app/charts";
import { Empty, ErrorNote, fmt, Kpis, Ladder, Loading, Panel, Pill, STAGE_LABEL, Tabs, TitleRow } from "@/components/app/ui";
import { STAGES, type SpecEntry } from "@/lib/api";
import { useShadowRun } from "@/lib/hooks";
import { useSpecs, useWorkspace } from "@/lib/workspace";

/*
 * Shadow mode. Question: has this agent earned more trust, and on what evidence? The running
 * agreement with its promotions marked is the largest block; the ladder sits in the title row.
 */

function Run({ entry }: { entry: SpecEntry }) {
  const { dataset, base } = useWorkspace();
  const { data: run, error, isLoading, mutate } = useShadowRun(entry);

  if (!entry.approved_by) {
    return (
      <Empty>
        {entry.spec.name} hasn&apos;t been approved, so it hasn&apos;t started.{" "}
        <Link href={`${base}/agents`} className="font-semibold text-ink underline">
          Review it
        </Link>
      </Empty>
    );
  }
  if (isLoading) {
    return (
      <Panel>
        <Loading rows={6} label="Replaying the held-out days through the ladder" />
        <p className="mt-4 text-[13px] text-muted">
          Replaying every held-out day{dataset === "year" ? " of the year" : ""}: a few seconds.
        </p>
      </Panel>
    );
  }
  if (error) return <ErrorNote error={error} retry={() => mutate()} />;
  if (!run) return null;

  const agreement = run.points.length ? run.points.at(-1)!.agreement_so_far : 0;
  return (
    <div className="space-y-6">
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_380px] lg:items-end">
        <Kpis
          items={[
            { label: "Stage now", value: STAGE_LABEL[run.final_stage], caption: `after ${run.cases} cases` },
            { label: "Agreement", value: fmt.pct(agreement, 1), caption: "with the person, all stages" },
            {
              label: "Hours saved",
              value: fmt.num(run.hours_saved_estimated, 1),
              caption: `at ~${fmt.num(run.minutes_per_case, 1)} min a case, by stage share`,
            },
          ]}
        />
        <div className="rounded-[10px] border border-edge p-4">
          <Ladder stage={run.final_stage} />
          <p className="mt-3 text-[12px] text-muted">
            {fmt.date(run.from)} – {fmt.date(run.to)}
          </p>
        </div>
      </div>

      <Panel title="Agreement with the person, case by case">
        <AgreementChart run={run} />
      </Panel>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Stage changes">
          {run.changes.length === 0 ? (
            <Empty>
              Still in shadow: no 30-case run has cleared the bar. It keeps working silently while
              the person does the job.
            </Empty>
          ) : (
            <ol className="divide-y divide-rule">
              {run.changes.map((c) => (
                <li key={c.day + c.to} className="py-3 text-[14px]">
                  <div className="flex items-baseline justify-between gap-4">
                    <span className="font-semibold">
                      {c.action === "promote" ? "Promoted" : "Sent back"} to {STAGE_LABEL[c.to]}
                    </span>
                    <span className="tabular text-muted">{fmt.date(c.day)}</span>
                  </div>
                  <p className="mt-0.5 text-muted">
                    {c.cases} cases at {STAGE_LABEL[c.from]}, {fmt.pct(c.agreement)} agreed, lower bound{" "}
                    {fmt.num(c.lower_bound, 3)}
                  </p>
                </li>
              ))}
            </ol>
          )}
        </Panel>

        <Panel title="By stage">
          <table className="w-full text-[14px]">
            <thead>
              <tr className="text-left text-[12px] text-muted">
                <th className="pb-2 font-normal">Stage</th>
                <th className="pb-2 text-right font-normal">Cases</th>
                <th className="pb-2 text-right font-normal">Agreement</th>
                <th className="pb-2 text-right font-normal">Time saved per case</th>
              </tr>
            </thead>
            <tbody>
              {STAGES.map((s) => {
                const row = run.by_stage[s];
                return (
                  <tr key={s} className="border-t border-rule">
                    <td className="py-2.5">{STAGE_LABEL[s]}</td>
                    <td className="tabular py-2.5 text-right">{row ? row.cases : 0}</td>
                    <td className="tabular py-2.5 text-right">{row ? fmt.pct(row.agreement) : "—"}</td>
                    <td className="tabular py-2.5 text-right text-muted">{fmt.pct(run.policy.time_saved_share[s])}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="mt-3 text-[12px] text-muted">
            Time is credited only on cases where the agent agreed with the person.
          </p>
        </Panel>
      </div>
    </div>
  );
}

export default function ShadowPage() {
  const { data, error, isLoading, mutate } = useSpecs();
  const { dataset, setDataset, mode } = useWorkspace();
  const [current, setCurrent] = useState<string | null>(null);
  const selected = data?.find((d) => d.spec.workflow_id === current) ?? data?.find((d) => d.approved_by) ?? data?.[0];

  return (
    <div className="space-y-6">
      <TitleRow
        title="Shadow mode"
        line={
          mode === "demo" && dataset === "sample" ? (
            <>
              The sample holds 40 held-out days, enough for one promotion at most.{" "}
              <button className="font-semibold text-ink underline" onClick={() => setDataset("year")}>
                Switch to a full year
              </button>{" "}
              to see the whole climb.
            </>
          ) : (
            "Every held-out case, replayed in order through the autonomy ladder."
          )
        }
      />
      {error && <ErrorNote error={error} retry={() => mutate()} />}
      {isLoading && <Loading rows={6} />}
      {data && selected && (
        <>
          <Tabs
            label="Agents"
            value={selected.spec.workflow_id}
            onChange={setCurrent}
            items={data.map((d) => ({
              id: d.spec.workflow_id,
              label: (
                <span className="inline-flex items-center gap-2">
                  {d.spec.name}
                  {!d.approved_by && <Pill>not approved</Pill>}
                </span>
              ),
            }))}
          />
          <Run key={`${dataset}-${selected.spec_id}`} entry={selected} />
        </>
      )}
    </div>
  );
}
