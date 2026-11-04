"use client";

import { useState } from "react";
import { accountsEnabled, supabase } from "@/lib/supabase";

/** The demo request goes straight into the `leads` table; its policy allows inserts and nothing else. */
const SIZES = ["Just me", "2–5", "6–20", "21–100", "More than 100"];

export function DemoForm() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState<string | null>(null);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const value = (k: string) => String(form.get(k) ?? "").trim();
    setBusy(true);
    setError(null);
    try {
      const { error } = await supabase()
        .from("leads")
        .insert({
          name: value("name"),
          email: value("email"),
          company: value("company") || null,
          team_size: value("team_size") || null,
          message: value("message") || null,
        });
      if (error) throw error;
      setSent(value("email"));
    } catch (err) {
      setError((err as Error).message || "That didn't send. Try again in a moment.");
    } finally {
      setBusy(false);
    }
  }

  if (sent) {
    return (
      <div role="status" className="bg-[#eceae3] p-6 md:p-8">
        <p className="text-lead font-semibold">Thanks. We&apos;ll be in touch.</p>
        <p className="mt-2 text-body">A reply goes to {sent} within one working day.</p>
      </div>
    );
  }

  const input = "mt-1.5 h-11 w-full rounded-md border border-control bg-sheet px-3 text-body outline-none focus:border-ink";
  return (
    <form onSubmit={submit} className="space-y-5 bg-[#eceae3] p-6 md:p-8">
      <label className="block">
        <span className="text-small font-semibold">Your name</span>
        <input name="name" required maxLength={120} autoComplete="name" className={input} />
      </label>
      <label className="block">
        <span className="text-small font-semibold">Work email</span>
        <input name="email" type="email" required maxLength={254} autoComplete="email" className={input} />
      </label>
      <div className="grid gap-5 sm:grid-cols-2">
        <label className="block">
          <span className="text-small font-semibold">Company</span>
          <input name="company" maxLength={120} autoComplete="organization" className={input} />
        </label>
        <label className="block">
          <span className="text-small font-semibold">Team size</span>
          <select name="team_size" defaultValue="" className={input}>
            <option value="">Choose</option>
            {SIZES.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </label>
      </div>
      <label className="block">
        <span className="text-small font-semibold">What takes the most time?</span>
        <textarea
          name="message"
          rows={4}
          maxLength={2000}
          placeholder="Chasing unpaid invoices, matching bank lines to the ledger…"
          className="mt-1.5 w-full rounded-md border border-control bg-sheet px-3 py-2.5 text-body outline-none focus:border-ink"
        />
      </label>
      {error && (
        <p role="alert" className="rounded-md bg-bad-tint px-3 py-2.5 text-small text-bad">
          {error}
        </p>
      )}
      {!accountsEnabled && (
        <p className="text-small text-muted">The form isn&apos;t connected on this deployment yet.</p>
      )}
      <button
        type="submit"
        disabled={busy || !accountsEnabled}
        className="press h-12 w-full bg-olive text-body font-semibold text-paper hover:bg-ink disabled:opacity-60"
      >
        {busy ? "Sending…" : "Request a demo"}
      </button>
    </form>
  );
}
