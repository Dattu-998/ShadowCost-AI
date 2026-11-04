"use client";

import { useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { Button, Empty, ErrorNote, fmt, Loading, Panel, Pill, STAGE_LABEL, TitleRow } from "@/components/app/ui";
import { fetcher, STAGES, type Execution, type QueuedAction, type Stage } from "@/lib/api";
import { useShadowRun } from "@/lib/hooks";
import { useDataset, useSpecs, useWorkspace } from "@/lib/workspace";

/*
 * Execute. Question: what would the agent do today, and what is waiting for my approval? The
 * day's proposals answer first; the approval queue, the screen's queue that needs action, is the
 * rail beside them.
 */

const DOES: Record<Stage, string> = {
  shadow: "Logs what it would do. Nothing leaves.",
  draft: "Writes email drafts and suggested cell changes for the person to use.",
  approval: "Queues each action; it happens only after someone approves it.",
  autonomous: "Writes the emails to the outbox and the changes to a new copy of the sheet.",
};

function Queue() {
  const { approver, api, can } = useWorkspace();
  const { mutate } = useSWRConfig();
  const { data, error, isLoading } = useSWR<QueuedAction[]>(api.actions, fetcher, { refreshInterval: 15_000 });
  const [busy, setBusy] = useState<number | null>(null);
  const [failure, setFailure] = useState<Error | null>(null);

  async function decide(id: number, approve: boolean) {
    setBusy(id);
    setFailure(null);
    try {
      await api.decide(id, approve);
      await mutate(api.actions);
    } catch (err) {
      setFailure(err as Error);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div>
      <h2 className="mb-2 text-[15px] font-semibold">
        Waiting for approval {data && data.length > 0 && <span className="tabular text-muted">{data.length}</span>}
      </h2>
      <div className="rounded-[10px] border border-edge px-4">
        {isLoading && <div className="py-4"><Loading /></div>}
        {error && <div className="py-4"><ErrorNote error={error} /></div>}
        {failure && <div className="pt-4"><ErrorNote error={failure} /></div>}
        {data && data.length === 0 && (
          <p className="py-4 text-[14px] text-muted">Nothing is waiting. Run a day at the approval stage to queue actions.</p>
        )}
        <ul>
          {data?.slice(0, 8).map((a) => (
            <li key={a.action_id} className="border-b border-rule py-3 last:border-0">
              <div className="flex items-baseline justify-between gap-3 text-[13px]">
                <span className="font-semibold">{a.case_id}</span>
                <span className="tabular text-muted">{fmt.shortDate(a.day)}</span>
              </div>
              <p className="mt-0.5 text-[13px] text-muted">
                {a.proposal.rule}: {Object.entries(a.proposal.updates).map(([k, v]) => `${k} → ${v}`).join(", ") || "email"}
              </p>
              <div className="mt-2 flex gap-2">
                <Button className="h-8 px-3" onClick={() => decide(a.action_id, true)} disabled={busy === a.action_id || !can("approver")}>
                  Approve
                </Button>
                <Button variant="secondary" className="h-8 px-3" onClick={() => decide(a.action_id, false)} disabled={busy === a.action_id || !can("approver")}>
                  Reject
                </Button>
              </div>
            </li>
          ))}
        </ul>
      </div>
      <p className="mt-2 text-[12px] text-muted">Decisions are signed as {approver || "Office manager"} and can&apos;t be changed.</p>
    </div>
  );
}

export default function ExecutePage() {
  const { api, can } = useWorkspace();
  const summary = useDataset();
  const specs = useSpecs();
  const { mutate } = useSWRConfig();
  const approved = specs.data?.filter((s) => s.approved_by) ?? [];
  const [specId, setSpecId] = useState<string>("");
  const entry = approved.find((s) => s.spec_id === specId) ?? approved[0];
  const run = useShadowRun(entry);
  const firstDay = entry?.spec.source.evidence_period?.[1];
  const [day, setDay] = useState("");
  const [stage, setStage] = useState<Stage | "">("");
  const [result, setResult] = useState<Execution | null>(null);
  const [failure, setFailure] = useState<Error | null>(null);
  const [running, setRunning] = useState(false);
  const chosenStage: Stage = stage || run.data?.final_stage || "shadow";
  const minDay = firstDay ? new Date(new Date(firstDay).getTime() + 86_400_000).toISOString().slice(0, 10) : undefined;
  const chosenDay = day || minDay || "";

  async function execute() {
    if (!entry || !chosenDay) return;
    setRunning(true);
    setFailure(null);
    try {
      const r = await api.execute(entry, chosenDay, chosenStage);
      setResult(r);
      await mutate(api.actions);
    } catch (err) {
      setFailure(err as Error);
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="space-y-6">
      <TitleRow
        title="Execute a day"
        line="Run an approved agent on one day of the data at a stage of your choice. Nothing is ever sent or overwritten: emails go to an outbox and changes to a new copy of the sheet."
      />
      {specs.error && <ErrorNote error={specs.error} />}
      {specs.data && approved.length === 0 && <Empty>Approve an agent first, on the Agents screen.</Empty>}

      {entry && (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_384px]">
          <div className="min-w-0 space-y-4">
            <Panel>
              <div className="grid gap-4 md:grid-cols-[1.4fr_1fr_1fr_auto] md:items-end">
                <label className="block">
                  <span className="text-[13px] text-muted">Agent</span>
                  <select
                    value={entry.spec_id}
                    onChange={(e) => setSpecId(e.target.value)}
                    className="mt-1 h-9 w-full rounded-md border border-control bg-sheet px-2 text-[14px]"
                  >
                    {approved.map((s) => (
                      <option key={s.spec_id} value={s.spec_id}>
                        {s.spec.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block">
                  <span className="text-[13px] text-muted">Day</span>
                  <input
                    type="date"
                    value={chosenDay}
                    min={minDay}
                    max={summary.data?.last_day ?? undefined}
                    onChange={(e) => setDay(e.target.value)}
                    className="tabular mt-1 h-9 w-full rounded-md border border-control px-2 text-[14px]"
                  />
                </label>
                <label className="block">
                  <span className="text-[13px] text-muted">Stage</span>
                  <select
                    value={chosenStage}
                    onChange={(e) => setStage(e.target.value as Stage)}
                    className="mt-1 h-9 w-full rounded-md border border-control bg-sheet px-2 text-[14px]"
                  >
                    {STAGES.map((s) => (
                      <option key={s} value={s}>
                        {STAGE_LABEL[s]}
                        {run.data?.final_stage === s ? " (earned)" : ""}
                      </option>
                    ))}
                  </select>
                </label>
                <Button onClick={execute} disabled={running || !chosenDay || !can("approver")}>
                  {running ? "Running…" : "Run the day"}
                </Button>
              </div>
              <p className="mt-3 text-[13px] text-muted">
                {STAGE_LABEL[chosenStage]}: {DOES[chosenStage]}
              </p>
            </Panel>

            {failure && <ErrorNote error={failure} />}
            {result && (
              <Panel
                title={`${fmt.date(result.day)}: ${result.proposals.length} proposal${result.proposals.length === 1 ? "" : "s"}`}
                aside={
                  <span className="text-[13px] text-muted">
                    {result.stage === "draft" && `${result.drafts} drafts written`}
                    {result.stage === "approval" && `${result.queued.length} queued`}
                    {result.stage === "autonomous" && `${result.ready} emails in the outbox${result.sheet_written ? ", sheet copy written" : ""}`}
                    {result.stage === "shadow" && "logged only"}
                  </span>
                }
              >
                {result.proposals.length === 0 ? (
                  <Empty>Nothing to do on this day: the trigger didn&apos;t fire for any invoice.</Empty>
                ) : (
                  <ul className="space-y-3">
                    {result.proposals.map((p) => (
                      <li key={p.case_id} className="rounded-lg bg-hover p-4 text-[14px]">
                        <div className="flex items-baseline justify-between gap-3">
                          <span className="font-semibold">{p.case_id}</span>
                          <Pill>{p.rule}</Pill>
                        </div>
                        {Object.keys(p.updates).length > 0 && (
                          <p className="mt-2">
                            {Object.entries(p.updates).map(([k, v], i) => (
                              <span key={k}>
                                {i > 0 && ", "}
                                <b>{k}</b> → {v}
                              </span>
                            ))}
                          </p>
                        )}
                        {p.email && (
                          <div className="mt-3 rounded-md border border-edge bg-sheet p-3 text-[13px]">
                            <p className="text-muted">To {p.email.to}</p>
                            <p className="mt-1 font-semibold">{p.email.subject}</p>
                            <p className="mt-2 whitespace-pre-line text-muted">{p.email.body}</p>
                          </div>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>
            )}
          </div>
          <Queue />
        </div>
      )}
    </div>
  );
}
