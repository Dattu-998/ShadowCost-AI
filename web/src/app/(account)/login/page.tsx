"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Field, Frame, Note, safeNext } from "@/components/account/Frame";
import { Button } from "@/components/app/ui";
import { useSession } from "@/lib/session";
import { accountsEnabled, supabase } from "@/lib/supabase";

function Login() {
  const params = useSearchParams();
  const next = safeNext(params.get("next"));
  const router = useRouter();
  const { session } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (session) router.replace(next);
  }, [session, next, router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const { error } = await supabase().auth.signInWithPassword({ email: email.trim(), password });
    setBusy(false);
    if (error) setError(error.message);
    else router.replace(next);
  }

  const signup = `/signup${next !== "/app" ? `?next=${encodeURIComponent(next)}` : ""}`;
  return (
    <Frame
      title="Sign in"
      line="Welcome back. Your agents kept watching while you were away."
      foot={
        <>
          New to ShadowCost?{" "}
          <Link href={signup} className="font-semibold text-ink underline-offset-4 hover:underline">
            Create an account
          </Link>
          {" · "}
          <Link href="/demo" className="font-semibold text-ink underline-offset-4 hover:underline">
            Just looking? Open the demo
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
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {error && <Note>{error}</Note>}
          <Button type="submit" disabled={busy} className="w-full">
            {busy ? "Signing in…" : "Sign in"}
          </Button>
          <p className="text-center text-[14px]">
            <Link href="/reset" className="text-muted underline-offset-4 hover:text-ink hover:underline">
              Forgot your password?
            </Link>
          </p>
        </form>
      )}
    </Frame>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <Login />
    </Suspense>
  );
}
