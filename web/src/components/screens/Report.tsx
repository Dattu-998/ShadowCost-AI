"use client";

import useSWRMutation from "swr/mutation";
import { Button, Empty, ErrorNote, Loading, Panel, TitleRow } from "@/components/app/ui";
import { useSpecs, useWorkspace } from "@/lib/workspace";

/*
 * Report. Question: what did the agents save, measured, and on what assumptions? The report is
 * built by the API from the same pipeline and shown as it would be sent, in a sandboxed frame.
 */

export default function ReportPage() {
  const { api, dataset, mode } = useWorkspace();
  const specs = useSpecs();
  const report = useSWRMutation(`report/${mode}/${dataset}`, () => api.report(specs.data ?? []));

  function download() {
    if (!report.data) return;
    const url = URL.createObjectURL(new Blob([report.data.html], { type: "text/html" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `shadowcost-report-${dataset}.html`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-6">
      <TitleRow
        title="Savings report"
        line="What the repeated work costs, what each agent took over, and every assumption behind the numbers. On simulated data it also shows the hours measured against the person's real minutes."
        action={
          <div className="flex gap-2">
            {report.data && (
              <Button variant="secondary" onClick={download}>
                Download HTML
              </Button>
            )}
            <Button onClick={() => report.trigger()} disabled={report.isMutating || !specs.data?.length}>
              {report.isMutating ? "Building…" : report.data ? "Build again" : "Build the report"}
            </Button>
          </div>
        }
      />
      {report.error && <ErrorNote error={report.error} />}
      {report.isMutating && (
        <Panel>
          <Loading rows={8} label="Building the report" />
        </Panel>
      )}
      {!report.data && !report.isMutating && (
        <Empty>
          The report replays every agent through shadow mode on this data and adds up the time.
          It takes a few seconds{dataset === "year" ? " for a full year" : ""}.
        </Empty>
      )}
      {report.data && !report.isMutating && (
        <iframe
          title="Savings report"
          sandbox=""
          srcDoc={report.data.html}
          className="h-[78vh] w-full rounded-[10px] border border-edge bg-sheet"
        />
      )}
    </div>
  );
}
