"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Field, Frame, Note } from "@/components/account/Frame";
import { Button } from "@/components/app/ui";
import { useSession } from "@/lib/session";
import { accountsEnabled, supabase } from "@/lib/supabase";

/** Ask for a recovery link; arriving back through that link (signed in) sets the new password. */
export default function ResetPage() {
  const { session } = useSession();
  const router = useRouter();
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  async function requestLink(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const { error } = await supabase().auth.resetPasswordForEmail(value.trim(), {
      redirectTo: `${window.location.origin}/auth/callback?next=/reset`,
    });
    setBusy(false);
    if (error) setError(error.message);
    else setSent(true);
  }

  async function setPassword(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const { error } = await supabase().auth.updateUser({ password: value });
    setBusy(false);
    if (error) setError(error.message);
    else router.replace("/app");
  }

  if (!accountsEnabled) {
    return (
      <Frame title="Reset your password">
        <Note>Accounts aren&apos;t set up on this deployment.</Note>
      </Frame>
    );
  }
  if (session) {
    return (
      <Frame title="Choose a new password" line={`For ${session.user.email}.`}>
        <form onSubmit={setPassword} className="space-y-4">
          <Field
            label="New password"
            type="password"
            autoComplete="new-password"
            minLength={8}
            required
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
          {error && <Note>{error}</Note>}
          <Button type="submit" disabled={busy} className="w-full">
            {busy ? "Saving…" : "Save password"}
          </Button>
        </form>
      </Frame>
    );
  }
  return (
    <Frame
      title="Reset your password"
      line="We'll email you a link to choose a new one."
      foot={
        <Link href="/login" className="font-semibold text-ink underline-offset-4 hover:underline">
          Back to sign in
        </Link>
      }
    >
      {sent ? (
        <Note tone="good">If {value.trim()} has an account, the link is on its way.</Note>
      ) : (
        <form onSubmit={requestLink} className="space-y-4">
          <Field label="Work email" type="email" autoComplete="email" required value={value} onChange={(e) => setValue(e.target.value)} />
          {error && <Note>{error}</Note>}
          <Button type="submit" disabled={busy} className="w-full">
            {busy ? "Sending…" : "Send the link"}
          </Button>
        </form>
      )}
    </Frame>
  );
}
