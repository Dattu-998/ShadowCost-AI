"use client";

import Link from "next/link";
import useSWR from "swr";
import { WeeklyActivity } from "@/components/app/charts";
import {
  ButtonLink,
  Empty,
  ErrorNote,
  fmt,
  Kpis,
  Ladder,
  Loading,
  Panel,
  Pill,
  TitleRow,
} from "@/components/app/ui";
import { fetcher, type EventRow, type SpecEntry } from "@/lib/api";
import { useDiscovery, useShadowRun } from "@/lib/hooks";
import { useDataset, useSpecs, useWorkspace } from "@/lib/workspace";

/*
 * Overview. Question: how much repeated work is there, and how far has each agent got toward
 * doing it? The agents block (the ladder per agent) is the largest thing on the screen.
 * Grid: 1fr + 384px rail, 24px gap; main blocks 16px apart.
 */

function AgentRow({ entry }: { entry: SpecEntry }) {
  const { base } = useWorkspace();
  const run = useShadowRun(entry);
  const held = entry.spec.evaluation?.held_out;
  const approved = Boolean(entry.approved_by);
  return (
    <li className="grid gap-4 py-4 md:grid-cols-[minmax(0,1.2fr)_minmax(0,1.4fr)_120px] md:items-center">
      <div className="min-w-0">
        <p className="truncate text-[15px] font-semibold">{entry.spec.name}</p>
        <p className="mt-0.5 text-[13px] text-muted">
          {held ? `${fmt.pct(held.agreement)} agreement on ${held.outcomes} held-out cases` : "Not backtested"}
        </p>
      </div>
      <div>
        {!approved ? (
          <Ladder stage={null} approved={false} />
        ) : run.isLoading ? (
          <Loading rows={1} label="Running shadow mode" />
        ) : run.error ? (
          <p className="text-[13px] text-bad">{run.error.message}</p>
        ) : (
          <Ladder stage={run.data?.final_stage ?? "shadow"} />
        )}
      </div>
      <div className="md:text-right">
        {!approved ? (
          <Link href={`${base}/agents`} className="text-[14px] font-semibold underline-offset-4 hover:underline">
            Review it
          </Link>
        ) : run.data ? (
          <p className="text-[14px]">
            {fmt.num(run.data.hours_saved_estimated, 1)} h saved
            <span className="block text-[12px] text-muted">{run.data.cases} cases</span>
          </p>
        ) : null}
      </div>
    </li>
  );
}

function LatestEvents() {
  const { api } = useWorkspace();
  const { data, error, isLoading, mutate } = useSWR<EventRow[]>(api.events(6), fetcher);
  return (
    <div>
      <h2 className="mb-2 text-[15px] font-semibold">Latest in the files</h2>
      <div className="rounded-[10px] border border-edge bg-sheet px-4">
        {isLoading && <div className="py-4"><Loading /></div>}
        {error && <div className="py-4"><ErrorNote error={error} retry={() => mutate()} /></div>}
        <ul>
          {data?.map((e) => (
            <li key={e.event_id} className="border-b border-rule py-3 last:border-0">
              <div className="flex items-baseline justify-between gap-3 text-[13px]">
                <span className="font-semibold">{e.case_id || "No invoice"}</span>
                <span className="tabular text-muted">{fmt.shortDate(e.timestamp)}</span>
              </div>
              <p className="mt-0.5 truncate text-[13px] text-muted">
                {e.source === "spreadsheet" ? "Sheet" : e.source === "bank" ? "Bank" : "Email"}: {e.detail}
              </p>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export default function Overview() {
  const { base } = useWorkspace();
  const dataset = useDataset();
  const discovery = useDiscovery();
  const specs = useSpecs();
  const approved = specs.data?.filter((s) => s.approved_by).length ?? 0;
  const hours = discovery.data?.workflows.reduce((sum, w) => sum + w.hours_per_month, 0);
  const helds = specs.data
    ?.map((s) => ({ name: s.spec.name, a: s.spec.evaluation?.held_out.agreement ?? 0 }))
    .sort((a, b) => b.a - a.a);

  return (
    <div className="space-y-6">
      <TitleRow
        title="Overview"
        line={
          helds && helds.length ? (
            <>
              On days they never saw, the agents matched the person on {fmt.pct(helds.at(-1)!.a)} to{" "}
              {fmt.pct(helds[0].a)} of cases.{" "}
              {approved === 0 ? "None is approved yet, so none has started shadow mode." : `${approved} of ${helds.length} approved.`}
            </>
          ) : (
            "Reading the files…"
          )
        }
        action={<ButtonLink href={`${base}/agents`}>{approved ? "Review agents" : "Approve an agent"}</ButtonLink>}
      />

      {dataset.error && <ErrorNote error={dataset.error} retry={() => dataset.mutate()} />}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_384px]">
        <div className="min-w-0 space-y-4">
          <Kpis
            items={[
              {
                label: "Repeated work",
                value: hours === undefined ? "—" : `${fmt.num(hours, 1)} h`,
                caption: "per month, estimated",
              },
              {
                label: "Workflows found",
                value: discovery.data ? discovery.data.workflows.length : "—",
                caption: discovery.data ? `from ${discovery.data.episodes} episodes of work` : "first 80 days",
              },
              {
                label: "Agents approved",
                value: specs.data ? `${approved} of ${specs.data.length}` : "—",
                caption: "nothing runs unapproved",
              },
              {
                label: "Events tied to an invoice",
                value: dataset.data ? fmt.pct(dataset.data.linked_share) : "—",
                caption: dataset.data ? `of ${fmt.num(dataset.data.events)} events read` : "edits, payments, emails",
              },
            ]}
          />

          <Panel
            title="Agents on the ladder"
            aside={<span className="hidden text-[12px] text-muted sm:inline">Shadow, draft, approval, autonomous</span>}
          >
            {specs.isLoading && <Loading rows={3} />}
            {specs.error && <ErrorNote error={specs.error} retry={() => specs.mutate()} />}
            {specs.data && specs.data.length === 0 && <Empty>No agents drafted for this data yet.</Empty>}
            <ul className="-my-4 divide-y divide-rule">
              {specs.data?.map((entry) => <AgentRow key={entry.spec_id} entry={entry} />)}
            </ul>
          </Panel>

          <Panel title="Activity in the files, by week">
            {dataset.isLoading && <Loading rows={4} label="Reading the files" />}
            {dataset.data && <WeeklyActivity weeks={dataset.data.weekly} />}
          </Panel>
        </div>

        <div className="space-y-4">
          <LatestEvents />
          <div>
            <h2 className="mb-2 text-[15px] font-semibold">What was read</h2>
            <div className="rounded-[10px] border border-edge bg-sheet px-4">
              {dataset.isLoading && <div className="py-4"><Loading /></div>}
              {dataset.data && (
                <dl className="divide-y divide-rule text-[13px]">
                  {[
                    ["Daily sheet copies", dataset.data.files.snapshot ?? 0],
                    ["Bank exports", dataset.data.files.bank ?? 0],
                    ["Email logs", dataset.data.files.email ?? 0],
                    ["Reference tables", dataset.data.files.table ?? 0],
                  ].map(([k, v]) => (
                    <div key={k} className="flex justify-between py-2.5">
                      <dt className="text-muted">{k}</dt>
                      <dd className="tabular font-semibold">{v}</dd>
                    </div>
                  ))}
                  <div className="flex justify-between py-2.5">
                    <dt className="text-muted">Period</dt>
                    <dd className="tabular">
                      {fmt.date(dataset.data.first_day)} – {fmt.date(dataset.data.last_day)}
                    </dd>
                  </div>
                </dl>
              )}
            </div>
            {dataset.data?.has_ground_truth && (
              <p className="mt-2 text-[12px] text-muted">
                This is simulated data with a hidden answer key, so <Pill>measured</Pill> figures can be checked.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
