"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Frame, Note, safeNext } from "@/components/account/Frame";
import { useSession } from "@/lib/session";

/*
 * Where email links land (confirmation, password recovery). The Supabase client exchanges the
 * code in the URL by itself; this page waits for the session and moves on.
 */
function Callback() {
  const params = useSearchParams();
  const next = safeNext(params.get("next"));
  const failure = params.get("error_description");
  const router = useRouter();
  const { session, ready } = useSession();
  const [late, setLate] = useState(false);

  useEffect(() => {
    if (session) router.replace(next);
  }, [session, next, router]);
  useEffect(() => {
    const timer = setTimeout(() => setLate(true), 6000);
    return () => clearTimeout(timer);
  }, []);

  if (failure || (ready && late && !session)) {
    return (
      <Frame title="That link didn't work">
        <Note>{failure ?? "The link may have expired or already been used."}</Note>
        <p className="mt-4 text-[15px]">
          <Link href="/login" className="font-semibold underline-offset-4 hover:underline">
            Sign in
          </Link>{" "}
          or{" "}
          <Link href="/reset" className="font-semibold underline-offset-4 hover:underline">
            get a new link
          </Link>
          .
        </p>
      </Frame>
    );
  }
  return <Frame title="Signing you in…" line="One moment.">{null}</Frame>;
}

export default function CallbackPage() {
  return (
    <Suspense>
      <Callback />
    </Suspense>
  );
}
