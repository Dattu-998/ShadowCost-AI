"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useSWRConfig } from "swr";
import { Field, Frame, Note } from "@/components/account/Frame";
import { Button } from "@/components/app/ui";
import { get, post, type DatasetRow, type Me, type OrgDetail } from "@/lib/api";
import { useSession } from "@/lib/session";
import { remember } from "@/lib/workspace";

/*
 * Self-serve onboarding, two steps: name the workspace, then give it data. The sample is the
 * fastest way to see agents climb the ladder; real files and Google come in on the Data screen.
 */

function guessName(email: string): string {
  const domain = email.split("@")[1]?.split(".")[0] ?? "";
  const generic = ["gmail", "outlook", "hotmail", "yahoo", "icloud", "proton", "live"];
  if (!domain || generic.includes(domain)) return "";
  return domain.charAt(0).toUpperCase() + domain.slice(1);
}

export default function OnboardingPage() {
  const { session, ready } = useSession();
  const router = useRouter();
  const { mutate } = useSWRConfig();
  const [name, setName] = useState<string | null>(null);
  const [org, setOrg] = useState<OrgDetail | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (ready && !session) router.replace("/login?next=/onboarding");
  }, [ready, session, router]);

  const email = session?.user.email ?? "";
  const value = name ?? guessName(email);

  async function refreshMe() {
    if (session) await mutate(["me", session.user.id], await get<Me>("/v1/me"), { revalidate: false });
  }

  async function createWorkspace(e: React.FormEvent) {
    e.preventDefault();
    setBusy("create");
    setError(null);
    try {
      const created = await post<OrgDetail>("/v1/orgs", { name: value.trim() });
      remember("shadowcost.org", created.id);
      await refreshMe();
      setOrg(created);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function addSample() {
    if (!org) return;
    setBusy("sample");
    setError(null);
    try {
      const dataset = await post<DatasetRow>(`/v1/orgs/${org.id}/datasets/sample`);
      remember(`shadowcost.dataset.${org.id}`, dataset.id);
      if (dataset.status === "ready") await post(`/v1/orgs/${org.id}/datasets/${dataset.id}/agents/draft`);
      router.push("/app");
    } catch (err) {
      setError((err as Error).message);
      setBusy(null);
    }
  }

  if (!session) return <Frame title="One moment…">{null}</Frame>;

  if (!org) {
    return (
      <Frame
        title="Name your workspace"
        line="A workspace holds one company's data, agents and team. You can rename it later."
        foot={`Signed in as ${email}`}
      >
        <form onSubmit={createWorkspace} className="space-y-4">
          <Field
            label="Company or team name"
            required
            maxLength={80}
            placeholder="Fernhill Supplies"
            value={value}
            onChange={(e) => setName(e.target.value)}
          />
          {error && <Note>{error}</Note>}
          <Button type="submit" disabled={busy !== null || !value.trim()} className="w-full">
            {busy ? "Creating…" : "Continue"}
          </Button>
        </form>
      </Frame>
    );
  }

  return (
    <Frame wide title="Give it something to watch" line={`${org.name} is ready. Pick where its first evidence comes from.`}>
      <ul className="divide-y divide-rule rounded-[10px] border border-edge">
        <li className="grid items-center gap-4 p-5 sm:grid-cols-[minmax(0,1fr)_auto]">
          <div className="min-w-0">
            <p className="text-[15px] font-semibold">Start with the sample company</p>
            <p className="mt-0.5 text-[14px] text-muted">
              Four months of a wholesaler&apos;s ledger, bank feed and inbox, with two agents already drafted.
            </p>
          </div>
          <Button onClick={addSample} disabled={busy !== null}>
            {busy === "sample" ? "Loading the sample…" : "Use the sample"}
          </Button>
        </li>
        <li className="grid items-center gap-4 p-5 sm:grid-cols-[minmax(0,1fr)_auto]">
          <div className="min-w-0">
            <p className="text-[15px] font-semibold">Upload your own files</p>
            <p className="mt-0.5 text-[14px] text-muted">
              Dated spreadsheet copies, a bank export and an email export: CSV, Excel, JSON or one zip.
            </p>
          </div>
          <Link
            href="/app/data"
            className="press inline-flex h-9 items-center rounded-md border border-control px-4 text-[14px] font-semibold hover:bg-hover"
          >
            Upload files
          </Link>
        </li>
        <li className="grid items-center gap-4 p-5 sm:grid-cols-[minmax(0,1fr)_auto]">
          <div className="min-w-0">
            <p className="text-[15px] font-semibold">Connect Google Sheets and Gmail</p>
            <p className="mt-0.5 text-[14px] text-muted">
              Read-only. A daily snapshot of one sheet and the headers of matching emails. Starter plan and up.
            </p>
          </div>
          <Link
            href="/app/data#google"
            className="press inline-flex h-9 items-center rounded-md border border-control px-4 text-[14px] font-semibold hover:bg-hover"
          >
            Connect Google
          </Link>
        </li>
      </ul>
      {error && (
        <div className="mt-4">
          <Note>{error}</Note>
        </div>
      )}
    </Frame>
  );
}
