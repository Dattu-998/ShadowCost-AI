"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Field, Frame, Note, safeNext } from "@/components/account/Frame";
import { Button } from "@/components/app/ui";
import { useSession } from "@/lib/session";
import { accountsEnabled, supabase } from "@/lib/supabase";

function Signup() {
  const params = useSearchParams();
  const next = safeNext(params.get("next"));
  const router = useRouter();
  const { session } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sentTo, setSentTo] = useState<string | null>(null);

  useEffect(() => {
    if (session) router.replace(next);
  }, [session, next, router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const { data, error } = await supabase().auth.signUp({
      email: email.trim(),
      password,
      options: {
        emailRedirectTo: `${window.location.origin}/auth/callback?next=${encodeURIComponent(next)}`,
      },
    });
    setBusy(false);
    if (error) setError(error.message);
    else if (data.session) router.replace(next);
    else setSentTo(email.trim());
  }

  const login = `/login${next !== "/app" ? `?next=${encodeURIComponent(next)}` : ""}`;
  if (sentTo) {
    return (
      <Frame title="Check your email" line={`We sent a confirmation link to ${sentTo}.`}>
        <p className="text-[15px]">
          Open it on this device to finish signing up. It can take a minute to arrive; check spam if it
          doesn&apos;t.
        </p>
        <Button variant="secondary" className="mt-6" onClick={() => setSentTo(null)}>
          Use a different email
        </Button>
      </Frame>
    );
  }
  return (
    <Frame
      title="Start free"
      line="One workspace, two datasets and one agent on the house. No card needed."
      foot={
        <>
          Already have an account?{" "}
          <Link href={login} className="font-semibold text-ink underline-offset-4 hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      {!accountsEnabled ? (
        <Note>Accounts aren&apos;t set up on this deployment. The demo works without one.</Note>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <Field label="Work email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          <Field
            label="Password"
            type="password"
            autoComplete="new-password"
            minLength={8}
            required
            hint="At least 8 characters."
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {error && <Note>{error}</Note>}
          <Button type="submit" disabled={busy} className="w-full">
            {busy ? "Creating your account…" : "Create account"}
          </Button>
          <p className="text-[13px] text-muted">
            By creating an account you agree to the{" "}
            <Link href="/terms" className="underline">
              terms
            </Link>{" "}
            and{" "}
            <Link href="/privacy" className="underline">
              privacy notice
            </Link>
            .
          </p>
        </form>
      )}
    </Frame>
  );
}

export default function SignupPage() {
  return (
    <Suspense>
      <Signup />
    </Suspense>
  );
}
