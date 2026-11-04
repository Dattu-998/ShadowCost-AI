"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { useSWRConfig } from "swr";
import { Frame, Note } from "@/components/account/Frame";
import { Button } from "@/components/app/ui";
import { get, post, type Me } from "@/lib/api";
import { useSession } from "@/lib/session";
import { remember } from "@/lib/workspace";

function Invite() {
  const params = useSearchParams();
  const token = params.get("token") ?? "";
  const here = `/invite?token=${encodeURIComponent(token)}`;
  const { session, ready } = useSession();
  const router = useRouter();
  const { mutate } = useSWRConfig();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function accept() {
    setBusy(true);
    setError(null);
    try {
      const joined = await post<{ org_id: string }>("/v1/invitations/accept", { token });
      remember("shadowcost.org", joined.org_id);
      if (session) await mutate(["me", session.user.id], await get<Me>("/v1/me"), { revalidate: false });
      router.push("/app");
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  if (!token) {
    return (
      <Frame title="This invitation link is incomplete">
        <Note>Open the link from the invitation email again, or ask for a new one.</Note>
      </Frame>
    );
  }
  if (!ready) return <Frame title="One moment…">{null}</Frame>;
  if (!session) {
    return (
      <Frame title="You've been invited" line="Sign in or create an account with the email the invitation was sent to.">
        <div className="flex flex-wrap gap-3">
          <Link
            href={`/signup?next=${encodeURIComponent(here)}`}
            className="press inline-flex h-9 items-center rounded-md bg-ink px-4 text-[14px] font-semibold text-sheet hover:bg-olive"
          >
            Create an account
          </Link>
          <Link
            href={`/login?next=${encodeURIComponent(here)}`}
            className="press inline-flex h-9 items-center rounded-md border border-control px-4 text-[14px] font-semibold hover:bg-hover"
          >
            Sign in
          </Link>
        </div>
      </Frame>
    );
  }
  return (
    <Frame title="Join the workspace" line={`You're signed in as ${session.user.email}.`}>
      {error && (
        <div className="mb-4">
          <Note>{error}</Note>
        </div>
      )}
      <Button onClick={accept} disabled={busy} className="w-full">
        {busy ? "Joining…" : "Accept the invitation"}
      </Button>
    </Frame>
  );
}

export default function InvitePage() {
  return (
    <Suspense>
      <Invite />
    </Suspense>
  );
}
