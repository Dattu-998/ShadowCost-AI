"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import useSWR from "swr";
import { Shell } from "@/components/app/Shell";
import { ErrorNote } from "@/components/app/ui";
import { fetcher, type Me } from "@/lib/api";
import { useSession } from "@/lib/session";
import { accountsEnabled } from "@/lib/supabase";
import { OrgWorkspaceProvider } from "@/lib/workspace";

/** A quiet full-screen holding state while the session and workspace load. */
export function Holding({ children }: { children: ReactNode }) {
  return (
    <div className="grid min-h-svh place-items-center bg-frame px-4 text-center text-[14px] text-muted">
      <div className="max-w-sm">{children}</div>
    </div>
  );
}

/** Signed-in only: sends visitors to sign in, and new accounts to create their first workspace. */
export function AppGate({ children }: { children: ReactNode }) {
  const { session, ready } = useSession();
  const router = useRouter();
  const pathname = usePathname();
  const me = useSWR<Me>(session ? ["me", session.user.id] : null, () => fetcher<Me>("/v1/me"));

  const signedOut = ready && !session;
  // Wait for a fresh answer: a cached one from before the first workspace was made would loop.
  const noWorkspace = me.data && me.data.workspaces.length === 0 && !me.isValidating;
  useEffect(() => {
    if (signedOut) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    else if (noWorkspace) router.replace("/onboarding");
  }, [signedOut, noWorkspace, pathname, router]);

  if (!accountsEnabled) {
    return (
      <Holding>
        <p className="font-semibold text-ink">Accounts aren&apos;t set up on this deployment.</p>
        <p className="mt-1">
          The <Link className="underline" href="/demo">demo workspace</Link> works without one.
        </p>
      </Holding>
    );
  }
  if (me.error) {
    return (
      <Holding>
        <ErrorNote error={me.error} retry={() => me.mutate()} />
      </Holding>
    );
  }
  if (!me.data || me.data.workspaces.length === 0) return <Holding>Opening your workspace…</Holding>;

  return (
    <OrgWorkspaceProvider me={me.data}>
      <Shell>{children}</Shell>
    </OrgWorkspaceProvider>
  );
}
