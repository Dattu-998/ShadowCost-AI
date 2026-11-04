"use client";

import type { Session } from "@supabase/supabase-js";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { setAccessToken } from "@/lib/api";
import { accountsEnabled, supabase } from "@/lib/supabase";

type SessionState = { session: Session | null; ready: boolean };
const Context = createContext<SessionState>({ session: null, ready: false });

/** Tracks the signed-in session and hands its token to the API client. */
export function SessionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<SessionState>({ session: null, ready: !accountsEnabled });

  useEffect(() => {
    if (!accountsEnabled) return;
    const client = supabase();
    client.auth.getSession().then(({ data }) => {
      setAccessToken(data.session?.access_token ?? null);
      setState({ session: data.session, ready: true });
    });
    const { data } = client.auth.onAuthStateChange((_event, session) => {
      setAccessToken(session?.access_token ?? null);
      setState({ session, ready: true });
    });
    return () => data.subscription.unsubscribe();
  }, []);

  return <Context.Provider value={state}>{children}</Context.Provider>;
}

export function useSession(): SessionState {
  return useContext(Context);
}
