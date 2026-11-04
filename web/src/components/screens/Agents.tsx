"use client";

import { useState } from "react";
import useSWRMutation from "swr/mutation";
import { Button, Empty, ErrorNote, fmt, Loading, Panel, Pill, Tabs, TitleRow } from "@/components/app/ui";
import { type Backtest, type Condition, type SpecEntry } from "@/lib/api";
import { useApprove } from "@/lib/hooks";
import { useSpecs, useWorkspace } from "@/lib/workspace";

/*
 * Agents. Question: is this agent's spec right, and should I approve it? The held-out evidence
 * and the rules in plain words come first; the one action is Approve.
 */

const OPS: Record<string, string> = {
  eq: "is",
  ne: "is not",
  in: "is one of",
  not_in: "is none of",
  contains: "contains",
  not_contains: "does not contain",
  at_least: "is at least",
  at_most: "is at most",
  days_since_at_least: "was at least",
  days_since_at_most: "was at most",
  empty: "is empty",
  not_empty: "is filled in",
};

function sayCondition(c: Condition) {
  const value = Array.isArray(c.value) ? c.value.join(", ") : c.value === undefined ? "" : String(c.value);
  const days = c.op.startsWith("days_since") ? ` days ago` : "";
  return (
    <>
      <b>{c.column}</b> {OPS[c.op] ?? c.op} {value}
      {days}
    </>
  );
}

function trigger(spec: SpecEntry["spec"]) {
  const t = spec.trigger;
  if (t.kind === "schedule") {
    const days = ["Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays", "Saturdays", "Sundays"];
    return `Every row, on ${(t.weekdays ?? []).map((d) => days[d]).join(" and ")}`;
  }
  if (t.kind === "event") return `The row each ${t.activity} is linked to, on the day it arrives`;
  return "Each new row, on the day it is added";
}

function AgentDetail({ entry }: { entry: SpecEntry }) {
  const { api, approver, can, mode, dataset } = useWorkspace();
  const approve = useApprove();
  const [approving, setApproving] = useState(false);
  const [failure, setFailure] = useState<Error | null>(null);
  const backtest = useSWRMutation<Backtest>(`backtest/${mode}/${dataset}/${entry.spec_id}`, () =>
    api.backtest(entry),
  );
  const spec = entry.spec;
  const held = spec.evaluation?.held_out;

  async function onApprove() {
    setApproving(true);
    setFailure(null);
    try {
      await approve(entry);
    } catch (err) {
      setFailure(err as Error);
    } finally {
      setApproving(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <p className="text-[13px] text-muted">
            Agents / <span className="text-ink">{spec.workflow_id}</span>
          </p>
          <h2 className="mt-1 text-[20px] font-semibold tracking-tight">{spec.name}</h2>
          <p className="mt-1 max-w-[80ch] text-[14px] text-muted">{spec.summary}</p>
        </div>
        {entry.approved_by ? (
          <Pill tone="good">
            Approved by {entry.approved_by} · {fmt.date(entry.approved_at)}
          </Pill>
        ) : (
          <div className="flex items-center gap-3">
            <span className="text-[13px] text-muted">
              {can("approver") ? `as ${approver || "Office manager"}` : "Approvers approve agents"}
            </span>
            <Button onClick={onApprove} disabled={approving || !can("approver")}>
              {approving ? "Approving…" : "Approve this agent"}
            </Button>
          </div>
        )}
      </div>
      {failure && <ErrorNote error={failure} />}

      <div className="grid gap-4 md:grid-cols-3">
        {[
          {
            label: "Agreement on held-out days",
            value: fmt.pct(held?.agreement, 1),
            caption: held ? `${held.outcomes} cases, ${fmt.date(held.from)} – ${fmt.date(held.to)}` : "not backtested",
          },
          {
            label: "Acted when the person did",
            value: fmt.pct(held?.action_recall, 1),
            caption: "recall: the person's work it caught",
          },
          {
            label: "The person did what it did",
            value: fmt.pct(held?.action_precision, 1),
            caption: "precision: its actions the person also took",
          },
        ].map((k) => (
          <div key={k.label} className="rounded-[10px] border border-edge p-5">
            <p className="text-[32px] font-normal leading-none tracking-tight">{k.value}</p>
            <p className="mt-2 text-[14px] font-semibold">{k.label}</p>
            <p className="mt-0.5 text-[12px] text-muted">{k.caption}</p>
          </div>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)] lg:items-start">
        <Panel title="What it does">
          <p className="text-[14px]">
            <span className="text-muted">Looks at: </span>
            {trigger(spec)}.
          </p>
          <ol className="mt-4 space-y-4">
            {spec.rules.map((rule, i) => (
              <li key={rule.name} className="rounded-lg bg-hover p-4">
                <p className="text-[14px] font-semibold">
                  {i === 0 ? "If" : "Otherwise, if"} {rule.name.toLowerCase()}
                </p>
                <ul className="mt-2 space-y-1 text-[14px]">
                  {rule.when.length === 0 && <li className="text-muted">Always</li>}
                  {rule.when.map((c, j) => (
                    <li key={j}>
                      <span className="text-muted">{j === 0 ? "when " : "and "}</span>
                      {sayCondition(c)}
                    </li>
                  ))}
                </ul>
                {Object.keys(rule.set).length > 0 && (
                  <p className="mt-2 text-[14px]">
                    <span className="text-muted">sets </span>
                    {Object.entries(rule.set).map(([k, v], j) => (
                      <span key={k}>
                        {j > 0 && ", "}
                        <b>{k}</b> to <code className="rounded bg-sheet px-1 text-[13px]">{v}</code>
                      </span>
                    ))}
                  </p>
                )}
                {rule.email && (
                  <div className="mt-3 rounded-md border border-edge bg-sheet p-3 text-[13px]">
                    <p>
                      <span className="text-muted">To </span>
                      <code>{rule.email.to}</code>
                    </p>
                    <p className="mt-1 font-semibold">{rule.email.subject}</p>
                    <p className="mt-2 whitespace-pre-line text-muted">{rule.email.body}</p>
                  </div>
                )}
              </li>
            ))}
          </ol>
        </Panel>

        <div className="space-y-6">
          <Panel title="Where it came from">
            <dl className="space-y-2 text-[14px]">
              <div className="flex justify-between gap-4">
                <dt className="text-muted">Drafted by</dt>
                <dd>{spec.source.generated_by ?? "hand"}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-muted">From the days</dt>
                <dd className="tabular">
                  {fmt.date(spec.source.evidence_period?.[0])} – {fmt.date(spec.source.evidence_period?.[1])}
                </dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-muted">Attempts</dt>
                <dd className="tabular">{spec.source.attempts ?? "—"}</dd>
              </div>
            </dl>
            {spec.source.notes && spec.source.notes.length > 0 && (
              <ul className="mt-3 list-disc space-y-1 pl-5 text-[13px] text-muted">
                {spec.source.notes.map((n) => (
                  <li key={n}>{n}</li>
                ))}
              </ul>
            )}
          </Panel>

          <Panel
            title="Where it disagreed"
            aside={
              <Button variant="secondary" onClick={() => backtest.trigger()} disabled={backtest.isMutating}>
                {backtest.isMutating ? "Replaying…" : "Replay on this data"}
              </Button>
            }
          >
            {backtest.error && <ErrorNote error={backtest.error} />}
            {!backtest.data && !backtest.isMutating && (
              <p className="text-[14px] text-muted">
                Replays every held-out day on the selected data and lists the cases where the agent and
                the person did different things.
              </p>
            )}
            {backtest.isMutating && <Loading rows={4} label="Replaying held-out days" />}
            {backtest.data && (
              <div className="space-y-3 text-[14px]">
                <p>
                  <b>{fmt.pct(backtest.data.agreement, 1)}</b> of {backtest.data.outcomes} cases agree
                  <span className="text-muted"> (95% lower bound {fmt.pct(backtest.data.agreement_lower_bound, 1)})</span>.
                </p>
                {backtest.data.examples.length === 0 ? (
                  <Empty>No disagreements on this data.</Empty>
                ) : (
                  <table className="w-full text-[13px]">
                    <thead>
                      <tr className="text-left text-[12px] text-muted">
                        <th className="pb-1 font-normal">Invoice</th>
                        <th className="pb-1 font-normal">What happened</th>
                        <th className="pb-1 text-right font-normal">Day</th>
                      </tr>
                    </thead>
                    <tbody>
                      {backtest.data.examples.map((e, i) => (
                        <tr key={i} className="border-t border-rule">
                          <td className="py-2 font-semibold">{e.case_id}</td>
                          <td className="py-2">
                            {e.kind === "agent_only"
                              ? "Agent acted, the person didn't"
                              : e.kind === "human_only"
                                ? "The person acted, the agent didn't"
                                : `Both acted; ${e.differing.join(", ")} differed`}
                          </td>
                          <td className="tabular py-2 text-right text-muted">
                            {fmt.shortDate(e.agent_day ?? e.human_day ?? "")}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            )}
          </Panel>
        </div>
      </div>
    </div>
  );
}

export default function AgentsPage() {
  const { data, error, isLoading, mutate } = useSpecs();
  const [current, setCurrent] = useState<string | null>(null);
  const selected = data?.find((d) => d.spec.workflow_id === current) ?? data?.[0];

  return (
    <div className="space-y-6">
      <TitleRow
        title="Agents"
        line="Each was drafted by an LLM from measured evidence, then replayed on days it never saw. Nothing runs until a person approves it, and editing a spec voids the approval."
      />
      {error && <ErrorNote error={error} retry={() => mutate()} />}
      {isLoading && <Loading rows={6} />}
      {data && data.length === 0 && <Empty>No agents yet.</Empty>}
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
                  {d.approved_by ? <span className="h-1.5 w-1.5 rounded-full bg-good" aria-label="approved" /> : null}
                </span>
              ),
            }))}
          />
          <AgentDetail entry={selected} />
        </>
      )}
    </div>
  );
}
