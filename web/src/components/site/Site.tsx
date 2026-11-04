import Link from "next/link";
import type { ReactNode } from "react";
import { Footer } from "@/components/landing/Footer";

/*
 * The sales pages (pricing, security, docs, legal, contact) share the landing page's paper and
 * type: a plain top bar, one chapter-coloured title band, then reading-width content. Olive stays
 * the only colour that acts.
 */

const NAV = [
  ["/demo", "Demo"],
  ["/pricing", "Pricing"],
  ["/security", "Security"],
  ["/docs", "Docs"],
] as const;

export function SiteHeader() {
  return (
    <nav aria-label="Main" className="flex items-center justify-between gap-4 px-4 py-4 md:px-7 md:py-6">
      <Link href="/" className="text-lead font-semibold tracking-tight">
        ShadowCost
      </Link>
      <div className="flex items-center gap-4 md:gap-7">
        {NAV.map(([href, label]) => (
          <Link key={href} href={href} className="hidden text-body font-semibold hover:underline md:inline">
            {label}
          </Link>
        ))}
        <Link href="/login" className="text-body font-semibold hover:underline">
          Sign in
        </Link>
        <Link
          href="/signup"
          className="press bg-olive px-4 py-2.5 text-body font-semibold text-paper hover:bg-ink md:px-5 md:py-3"
        >
          Start free
        </Link>
      </div>
    </nav>
  );
}

const BAND = { slate: "bg-slate", blush: "bg-blush", sage: "bg-sage", paper: "bg-paper" } as const;

export function SitePage({
  eyebrow,
  title,
  line,
  band = "sage",
  children,
}: {
  eyebrow: string;
  title: ReactNode;
  line?: ReactNode;
  band?: keyof typeof BAND;
  children: ReactNode;
}) {
  return (
    <div className="min-h-svh bg-paper">
      <header className={BAND[band]}>
        <SiteHeader />
        <div className="px-4 pb-14 pt-10 md:px-7 md:pb-20 md:pt-16">
          <p className="text-small font-semibold uppercase tracking-[0.08em]">{eyebrow}</p>
          <h1 className="display mt-4 max-w-[16ch] text-head">{title}</h1>
          {line && <p className="mt-6 max-w-[52ch] text-lead leading-snug">{line}</p>}
        </div>
      </header>
      <main className="px-4 py-14 md:px-7 md:py-20">{children}</main>
      <Footer />
    </div>
  );
}

/** Long-form reading column for docs and legal pages. */
export function Prose({ children }: { children: ReactNode }) {
  return (
    <div className="max-w-[68ch] text-body leading-relaxed [&_a]:underline [&_code]:rounded [&_code]:bg-[#d8d7ce] [&_code]:px-1 [&_code]:text-[0.9em] [&_h2]:mt-12 [&_h2]:text-lead [&_h2]:font-semibold [&_h2]:leading-tight [&_h3]:mt-8 [&_h3]:font-semibold [&_li]:mt-1.5 [&_ol]:mt-4 [&_ol]:list-decimal [&_ol]:pl-6 [&_p]:mt-4 [&_ul]:mt-4 [&_ul]:list-disc [&_ul]:pl-6">
      {children}
    </div>
  );
}

/** Legal pages say plainly that they are a starting draft, not reviewed terms. */
export function DraftNotice() {
  return (
    <p className="mb-10 max-w-[68ch] border-l-4 border-olive bg-[#d8d7ce] px-4 py-3 text-small">
      Draft for an early product: written in plain language and not yet reviewed by a lawyer. Questions go to the
      address on the <Link href="/contact" className="underline">contact page</Link>.
    </p>
  );
}
