"use client";

import Link from "next/link";
import { useRef } from "react";
import data from "@/data/landing.json";
import { useScrollProgress } from "@/lib/scroll";

/**
 * Waterline headline (dealt). Two flat fields meet at half height: paper above, slate below.
 * The product's name crosses the seam in the olive of autonomy, its second line half in the
 * light and half below the waterline, as if the work were still being done out of sight.
 *
 * Below the waterline that work really moves: the sample company's invoices going out and the
 * three workflows ShadowCost found, at their measured rates. Scrolling away lifts the paper off
 * the seam, so the slate floods up into the next chapter.
 *
 * The blueprint draws the headline twice, each copy clipped to its field so the ink can change
 * at the seam. Olive and ink are nearly the same darkness here, so one copy carries the effect
 * and the headline stays whole for readers and for the inspector.
 */
const LINES = ["SHADOW", "COST"];
const money = (n: number) => `$${n.toLocaleString("en-US", { minimumFractionDigits: 2 })}`;
const SENT = data.invoices.slice(0, 14).map((i) => `${i.id} to ${i.customer}, ${money(i.amount)}`);
const FOUND = [
  `Invoice emails, ${data.discovery.workflows[0].per_month} a month`,
  `Marking invoices paid, ${data.discovery.workflows[1].per_month} a month`,
  `Payment reminders, ${data.discovery.workflows[2].per_month} a month`,
];

function Flow({ items, reverse = false, time }: { items: string[]; reverse?: boolean; time: string }) {
  // Two copies side by side, moved by half their width, loop without a seam.
  return (
    <div className="flow" data-reverse={reverse || undefined} style={{ ["--flow-time" as string]: time }}>
      {[0, 1].map((copy) => (
        <ul key={copy} className="flex shrink-0">
          {items.map((item, i) => (
            <li key={`${i}:${item}`} className="whitespace-nowrap pr-[clamp(32px,4vw,64px)]">
              {item}
            </li>
          ))}
        </ul>
      ))}
    </div>
  );
}

export function Hero() {
  const ref = useRef<HTMLElement>(null);
  useScrollProgress(ref, "leave");

  return (
    <header
      ref={ref}
      className="relative h-[100svh] min-h-[560px] overflow-hidden bg-slate [--hero-size:15.5vw] [--seam-px:max(46svh,258px)] md:[--hero-size:clamp(72px,9vw,140px)] md:[--seam-px:max(50svh,280px)]"
    >
      <div aria-hidden className="hero-paper absolute inset-x-0 top-0 h-[var(--seam-px)] bg-paper" />

      <div className="hero-rise absolute inset-x-0 top-[calc(var(--seam-px)-1.29*var(--hero-size))]">
        <h1 className="display text-center text-olive [font-size:var(--hero-size)] [line-height:0.86]">
          {LINES.map((line) => (
            <span key={line} className="line-mask">
              <span>{line}</span>
            </span>
          ))}
        </h1>
      </div>

      <div
        aria-hidden
        className="flow-band fade-after-lines absolute inset-x-4 top-[calc(var(--seam-px)+0.62*var(--hero-size)+5svh)] space-y-2 overflow-hidden text-ink md:inset-x-7 [@media(max-height:699px)]:hidden"
      >
        <div className="text-lead font-semibold">
          <Flow items={SENT} time="90s" />
        </div>
        <div className="hidden text-body md:block">
          <Flow items={[...FOUND, ...FOUND]} reverse time="70s" />
        </div>
      </div>

      <nav
        aria-label="Main"
        className="absolute inset-x-0 top-0 flex items-center justify-between px-4 pt-4 md:px-7 md:pt-7"
      >
        <Link href="/" className="text-lead font-semibold tracking-tight">
          ShadowCost
        </Link>
        <div className="flex items-center gap-4 md:gap-7">
          <Link href="/demo" className="draw-link hidden text-body font-semibold sm:inline">
            Demo
          </Link>
          <Link href="/pricing" className="draw-link hidden text-body font-semibold sm:inline">
            Pricing
          </Link>
          <Link href="/login" className="draw-link text-body font-semibold">
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

      <p className="fade-after-lines absolute inset-x-4 bottom-8 max-w-[34ch] text-lead leading-snug md:inset-x-0 md:bottom-10 md:mx-auto md:max-w-[46ch] md:text-center">
        It finds the repetitive invoice, payment and email work in a small company, and hands it to
        an agent only after the agent has matched the person, case by case.
      </p>
    </header>
  );
}
