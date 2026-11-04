"use client";

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

/**
 * The browser's Supabase client: sign-up, sign-in and the session token sent to the API.
 * The publishable key is public by design; every table is protected by row-level security, and
 * all writes go through the API.
 */
const URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const KEY = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;

let client: SupabaseClient | null = null;

export const accountsEnabled = Boolean(URL && KEY);

export function supabase(): SupabaseClient {
  if (!URL || !KEY) throw new Error("Accounts aren't configured (NEXT_PUBLIC_SUPABASE_URL).");
  client ??= createClient(URL, KEY, {
    auth: { flowType: "pkce", persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
  });
  return client;
}
