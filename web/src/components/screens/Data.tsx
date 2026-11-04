"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useRef, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { Button, Empty, ErrorNote, fmt, Loading, Panel, Pill, TitleRow } from "@/components/app/ui";
import { del, fetcher, patch, post, upload, type Connection, type DatasetRow } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";

/*
 * Data. Question: what is ShadowCost watching, and where does it come from? Datasets list first,
 * then the two ways in: files and the Google connector. Grid: 1fr + 384px rail, 24px gap.
 */

const GOOGLE_NOTICE: Record<string, { tone: "good" | "bad"; text: string }> = {
  connected: { tone: "good", text: "Google is connected. Choose a sheet or a Gmail search below, then sync." },
  cancelled: { tone: "bad", text: "Google wasn't connected: the consent screen was closed." },
  "no-refresh-token": {
    tone: "bad",
    text: "Google didn't grant offline access. Remove ShadowCost from your Google account's third-party access and connect again.",
  },
};

function Datasets() {
  const { org, can, dataset, setDataset, base } = useWorkspace();
  const { mutate } = useSWRConfig();
  const key = org ? `/v1/orgs/${org.id}/datasets` : null;
  const rows = useSWR<DatasetRow[]>(key, fetcher, {
    refreshInterval: (data) => (data?.some((r) => r.status === "processing") ? 3000 : 0),
  });
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ tone: "good" | "bad"; text: string } | null>(null);

  async function act(id: string, run: () => Promise<string>) {
    setBusy(id);
    setMessage(null);
    try {
      setMessage({ tone: "good", text: await run() });
    } catch (err) {
      setMessage({ tone: "bad", text: (err as Error).message });
    } finally {
      setBusy(null);
      await mutate(key);
      if (org) await mutate(`/v1/orgs/${org.id}`);
    }
  }

  const draft = (row: DatasetRow) =>
    act(`draft-${row.id}`, async () => {
      const result = await post<{ created: number; skipped: number; problems: string[] }>(
        `/v1/orgs/${org!.id}/datasets/${row.id}/agents/draft`,
      );
      if (org) await mutate(`/v1/orgs/${org.id}/agents?dataset_id=${row.id}`);
      const problems = result.problems.length ? ` ${result.problems.join(" ")}` : "";
      return result.created
        ? `Drafted ${result.created} agent${result.created === 1 ? "" : "s"} from ${row.name}. Review them on Agents.${problems}`
        : `No new agents: ${result.skipped ? "the ones found are already drafted." : "no workflow was regular enough to draft."}${problems}`;
    });

  const remove = (row: DatasetRow) => {
    if (!window.confirm(`Delete ${row.name}? Its files and shadow runs go with it.`)) return;
    return act(`delete-${row.id}`, async () => {
      await del(`/v1/orgs/${org!.id}/datasets/${row.id}`);
      return `${row.name} was deleted.`;
    });
  };

  return (
    <Panel
      title="Datasets"
      aside={
        org && (
          <span className="text-[13px] text-muted">
            {org.usage.datasets} of {org.limits.datasets} on {org.plan_name}
          </span>
        )
      }
    >
      {message && (
        <p
          role={message.tone === "bad" ? "alert" : "status"}
          className={`mb-4 rounded-md px-3 py-2.5 text-[14px] ${message.tone === "bad" ? "bg-bad-tint text-bad" : "bg-good-tint text-good"}`}
        >
          {message.text}
        </p>
      )}
      {rows.error ? (
        <ErrorNote error={rows.error} retry={() => rows.mutate()} />
      ) : !rows.data ? (
        <Loading />
      ) : rows.data.length === 0 ? (
        <Empty>Nothing yet. Upload files or add the sample to start discovering repeated work.</Empty>
      ) : (
        <div className="-mx-5 overflow-x-auto">
          <table className="w-full min-w-[640px] text-[14px]">
            <thead>
              <tr className="border-b border-rule text-left text-[13px] text-muted">
                <th className="px-5 pb-2 font-normal">Name</th>
                <th className="pb-2 font-normal">Status</th>
                <th className="pb-2 text-right font-normal">Events</th>
                <th className="pb-2 pl-6 font-normal">Covers</th>
                <th className="px-5 pb-2 text-right font-normal">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-rule">
              {rows.data.map((row) => (
                <tr key={row.id} className="align-top">
                  <td className="px-5 py-3">
                    <p className="font-semibold">
                      {row.name}
                      {row.id === dataset && <span className="ml-2 text-[12px] font-normal text-muted">in use</span>}
                    </p>
                    <p className="text-[13px] text-muted">
                      {row.source === "google" ? "Google connector" : row.sample ? "Sample" : "Upload"} · added{" "}
                      {fmt.date(row.created_at)}
                    </p>
                    {row.error && <p className="mt-1 max-w-[60ch] text-[13px] text-bad">{row.error}</p>}
                  </td>
                  <td className="py-3">
                    <Pill tone={row.status === "ready" ? "good" : row.status === "error" ? "bad" : "wait"}>
                      {row.status === "ready" ? "Ready" : row.status === "error" ? "Couldn't read" : "Processing"}
                    </Pill>
                  </td>
                  <td className="tabular py-3 text-right">{fmt.num(row.events)}</td>
                  <td className="py-3 pl-6 text-muted">
                    {row.first_day ? `${fmt.date(row.first_day)} to ${fmt.date(row.last_day)}` : "—"}
                  </td>
                  <td className="px-5 py-3">
                    <div className="flex justify-end gap-2">
                      {row.status === "ready" && row.id !== dataset && (
                        <Button variant="quiet" onClick={() => setDataset(row.id)}>
                          Use
                        </Button>
                      )}
                      {row.status === "ready" && can("admin") && (
                        <Button variant="secondary" disabled={busy !== null} onClick={() => draft(row)}>
                          {busy === `draft-${row.id}` ? "Drafting…" : "Draft agents"}
                        </Button>
                      )}
                      {can("admin") && (
                        <Button
                          variant="quiet"
                          aria-label={`Delete ${row.name}`}
                          disabled={busy !== null}
                          onClick={() => remove(row)}
                          className="text-bad"
                        >
                          Delete
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {rows.data?.some((r) => r.status === "ready") && (
        <p className="mt-4 text-[13px] text-muted">
          Drafting reads the discovered workflows and writes one agent per regular workflow, each backtested
          before you see it. Approve them on{" "}
          <Link href={`${base}/agents`} className="underline">
            Agents
          </Link>
          .
        </p>
      )}
    </Panel>
  );
}

function AddData() {
  const { org, can } = useWorkspace();
  const { mutate } = useSWRConfig();
  const input = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState<"upload" | "sample" | null>(null);
  const [error, setError] = useState<string | null>(null);
  if (!org) return null;
  const full = org.usage.datasets >= org.limits.datasets;

  async function refresh() {
    await mutate(`/v1/orgs/${org!.id}/datasets`);
    await mutate(`/v1/orgs/${org!.id}`);
  }

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!files.length) return;
    setBusy("upload");
    setError(null);
    const form = new FormData();
    files.forEach((f) => form.append("files", f, f.webkitRelativePath || f.name));
    try {
      await upload(`/v1/orgs/${org!.id}/datasets?name=${encodeURIComponent(name.trim() || "Uploaded files")}`, form);
      setFiles([]);
      setName("");
      if (input.current) input.current.value = "";
      await refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function sample() {
    setBusy("sample");
    setError(null);
    try {
      await post(`/v1/orgs/${org!.id}/datasets/sample`);
      await refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  }

  if (!can("admin")) {
    return (
      <Panel title="Add data">
        <p className="text-[14px] text-muted">Admins and owners add data. Ask one to upload files or connect Google.</p>
      </Panel>
    );
  }
  return (
    <Panel title="Add data">
      {full && (
        <p className="mb-4 rounded-md bg-wait-tint px-3 py-2.5 text-[14px] text-wait">
          {org.plan_name} holds {org.limits.datasets} datasets. Delete one or{" "}
          <Link href="/app/settings?tab=billing" className="font-semibold underline">
            upgrade
          </Link>
          .
        </p>
      )}
      <form onSubmit={send} className="space-y-3">
        <label className="block">
          <span className="text-[14px] font-semibold">Files</span>
          <input
            ref={input}
            type="file"
            multiple
            accept=".csv,.xlsx,.xls,.json,.jsonl,.zip"
            onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
            className="mt-1.5 block w-full text-[14px] file:mr-3 file:h-9 file:rounded-md file:border file:border-control file:bg-sheet file:px-3 file:text-[14px] file:font-semibold hover:file:bg-hover"
          />
          <span className="mt-1 block text-[13px] text-muted">
            Dated copies of a spreadsheet (ledger_2026-03-01.csv), a bank export and an email export, or one zip
            of them. Up to 50 MB.
          </span>
        </label>
        <label className="block">
          <span className="text-[14px] font-semibold">Name</span>
          <input
            value={name}
            maxLength={80}
            placeholder="Accounts, spring 2026"
            onChange={(e) => setName(e.target.value)}
            className="mt-1.5 h-9 w-full rounded-md border border-control px-3 text-[14px] outline-none focus:border-ink"
          />
        </label>
        {error && (
          <p role="alert" className="rounded-md bg-bad-tint px-3 py-2.5 text-[14px] text-bad">
            {error}
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          <Button type="submit" disabled={!files.length || busy !== null || full}>
            {busy === "upload" ? "Reading the files…" : "Upload"}
          </Button>
          <Button type="button" variant="secondary" onClick={sample} disabled={busy !== null || full}>
            {busy === "sample" ? "Adding…" : "Add the sample"}
          </Button>
        </div>
      </form>
    </Panel>
  );
}

function Google() {
  const { org, can } = useWorkspace();
  const params = useSearchParams();
  const notice = GOOGLE_NOTICE[params.get("google") ?? ""];
  const { mutate } = useSWRConfig();
  const key = org ? `/v1/orgs/${org.id}/connectors` : null;
  const list = useSWR<Connection[]>(key, fetcher);
  const google = list.data?.find((c) => c.provider === "google");
  const [form, setForm] = useState<{ spreadsheet: string; sheet_range: string; gmail_query: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ tone: "good" | "bad"; text: string } | null>(null);
  if (!org) return null;

  const values = form ?? {
    spreadsheet: google?.settings.spreadsheet_id ?? "",
    sheet_range: google?.settings.sheet_range ?? "A1:Z5000",
    gmail_query: google?.settings.gmail_query ?? "newer_than:90d",
  };

  async function run(label: string, task: () => Promise<string | void>) {
    setBusy(label);
    setMessage(null);
    try {
      const text = await task();
      if (text) setMessage({ tone: "good", text });
    } catch (err) {
      setMessage({ tone: "bad", text: (err as Error).message });
    } finally {
      setBusy(null);
      await mutate(key);
    }
  }

  const connect = () =>
    run("connect", async () => {
      const { url } = await post<{ url: string }>(`/v1/orgs/${org.id}/connectors/google/start`);
      window.location.assign(url);
    });
  const save = (e: React.FormEvent) => {
    e.preventDefault();
    return run("save", async () => {
      await patch(`/v1/orgs/${org.id}/connectors/google`, values);
      setForm(null);
      return "Saved.";
    });
  };
  const sync = () =>
    run("sync", async () => {
      await post(`/v1/orgs/${org.id}/connectors/google/sync`);
      await mutate(`/v1/orgs/${org.id}/datasets`);
      return "Synced. Today's snapshot is in the Google dataset.";
    });
  const disconnect = () => {
    if (!window.confirm("Disconnect Google? The data already synced stays.")) return;
    return run("disconnect", async () => {
      await del(`/v1/orgs/${org.id}/connectors/google`);
      return "Disconnected.";
    });
  };

  let body;
  if (!org.features.google) {
    body = <p className="text-[14px] text-muted">The Google connector isn&apos;t configured on this server yet.</p>;
  } else if (!org.limits.connectors) {
    body = (
      <p className="text-[14px] text-muted">
        Connectors come with Starter and Growth.{" "}
        {can("owner") && (
          <Link href="/app/settings?tab=billing" className="font-semibold text-ink underline">
            See plans
          </Link>
        )}
      </p>
    );
  } else if (list.error) {
    body = <ErrorNote error={list.error} retry={() => list.mutate()} />;
  } else if (!list.data) {
    body = <Loading rows={2} />;
  } else if (!google) {
    body = (
      <>
        <p className="text-[14px] text-muted">
          Read-only access to Sheets and Gmail. ShadowCost copies one sheet once a day, and keeps only the
          sender, subject, date and first line of matching emails.
        </p>
        {can("admin") && (
          <Button className="mt-4" onClick={connect} disabled={busy !== null}>
            {busy === "connect" ? "Opening Google…" : "Connect Google"}
          </Button>
        )}
      </>
    );
  } else {
    body = (
      <>
        <p className="text-[14px]">
          Connected as <span className="font-semibold">{google.account_email ?? "a Google account"}</span>
        </p>
        <p className="mt-0.5 text-[13px] text-muted">
          {google.last_synced_at ? `Last synced ${fmt.date(google.last_synced_at)}` : "Not synced yet"}
        </p>
        {google.last_error && <p className="mt-2 text-[13px] text-bad">Last sync failed: {google.last_error}</p>}
        {can("admin") && (
          <form onSubmit={save} className="mt-4 space-y-3">
            {(
              [
                ["spreadsheet", "Spreadsheet", "Paste the sheet's link or ID"],
                ["sheet_range", "Range", "A1:Z5000"],
                ["gmail_query", "Gmail search", "newer_than:90d label:invoices"],
              ] as const
            ).map(([field, label, placeholder]) => (
              <label key={field} className="block">
                <span className="text-[14px] font-semibold">{label}</span>
                <input
                  value={values[field]}
                  placeholder={placeholder}
                  onChange={(e) => setForm({ ...values, [field]: e.target.value })}
                  className="mt-1.5 h-9 w-full rounded-md border border-control px-3 text-[14px] outline-none focus:border-ink"
                />
              </label>
            ))}
            <div className="flex flex-wrap gap-2">
              <Button type="submit" variant="secondary" disabled={busy !== null || form === null}>
                {busy === "save" ? "Saving…" : "Save"}
              </Button>
              <Button type="button" onClick={sync} disabled={busy !== null || form !== null}>
                {busy === "sync" ? "Syncing…" : "Sync now"}
              </Button>
              <Button type="button" variant="quiet" className="text-bad" onClick={disconnect} disabled={busy !== null}>
                Disconnect
              </Button>
            </div>
          </form>
        )}
      </>
    );
  }

  return (
    <Panel title={<span id="google">Google Sheets and Gmail</span>}>
      {notice && (
        <p
          role="status"
          className={`mb-4 rounded-md px-3 py-2.5 text-[14px] ${notice.tone === "bad" ? "bg-bad-tint text-bad" : "bg-good-tint text-good"}`}
        >
          {notice.text}
        </p>
      )}
      {message && (
        <p
          role={message.tone === "bad" ? "alert" : "status"}
          className={`mb-4 rounded-md px-3 py-2.5 text-[14px] ${message.tone === "bad" ? "bg-bad-tint text-bad" : "bg-good-tint text-good"}`}
        >
          {message.text}
        </p>
      )}
      {body}
    </Panel>
  );
}

export default function Data() {
  return (
    <div className="space-y-6">
      <TitleRow
        title="Data"
        line="What ShadowCost watches. Nothing here is changed: agents propose, people decide."
      />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_384px]">
        <Datasets />
        <div className="space-y-4">
          <AddData />
          <Suspense>
            <Google />
          </Suspense>
        </div>
      </div>
    </div>
  );
}
