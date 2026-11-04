import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";
import { Mark } from "@/components/app/Shell";

/*
 * Account pages (sign-in, sign-up, onboarding, invitations) use the app's framed sheet: one white
 * sheet, 440px wide, on the slate frame. Nothing else on the page competes with the form.
 */

export function Frame({
  title,
  line,
  children,
  foot,
  wide = false,
}: {
  title: ReactNode;
  line?: ReactNode;
  children: ReactNode;
  foot?: ReactNode;
  wide?: boolean;
}) {
  return (
    <div className="flex min-h-svh flex-col bg-frame px-4 text-ink">
      <header className="mx-auto flex h-16 w-full max-w-[1100px] items-center">
        <Link href="/" className="flex items-center gap-2.5 text-[15px] font-semibold">
          <Mark />
          ShadowCost
        </Link>
      </header>
      <main className="flex flex-1 items-start justify-center pb-16 pt-[6vh]">
        <div className={`w-full ${wide ? "max-w-[640px]" : "max-w-[440px]"}`}>
          <section className="rounded-2xl border border-edge bg-sheet p-6 md:p-8">
            <h1 className="text-[24px] font-semibold tracking-tight">{title}</h1>
            {line && <p className="mt-1.5 text-[15px] text-muted">{line}</p>}
            <div className="mt-6">{children}</div>
          </section>
          {foot && <p className="mt-4 text-center text-[14px] text-muted">{foot}</p>}
        </div>
      </main>
    </div>
  );
}

export function Field({
  label,
  hint,
  ...props
}: ComponentProps<"input"> & { label: string; hint?: ReactNode }) {
  return (
    <label className="block">
      <span className="text-[14px] font-semibold">{label}</span>
      <input
        {...props}
        className="mt-1.5 h-10 w-full rounded-md border border-control bg-sheet px-3 text-[15px] outline-none placeholder:text-[#8a949c] focus:border-ink"
      />
      {hint && <span className="mt-1 block text-[13px] text-muted">{hint}</span>}
    </label>
  );
}

export function Note({ tone = "bad", children }: { tone?: "bad" | "good"; children: ReactNode }) {
  return (
    <p
      role={tone === "bad" ? "alert" : "status"}
      className={`rounded-md px-3 py-2.5 text-[14px] ${tone === "bad" ? "bg-bad-tint text-bad" : "bg-good-tint text-good"}`}
    >
      {children}
    </p>
  );
}

/** Only same-site paths survive as a post-sign-in destination. */
export function safeNext(next: string | null, fallback = "/app"): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : fallback;
}
