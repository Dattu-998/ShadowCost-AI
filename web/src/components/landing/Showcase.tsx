"use client";

import { useMemo, useState } from "react";
import data from "@/data/landing.json";
import { Reveal } from "@/lib/reveal";
import { linkPayment, money, parseBankLine, type Invoice } from "@/lib/linker";

/**
 * Input half, output half (dealt). The one live thing on the page: type a bank line the way a
 * statement prints it, and ShadowCost links it to the invoice it pays, or says why it won't.
 */
const invoices: Invoice[] = data.invoices;
const examples = data.bank_examples.map((b) => ({
  label: b.reference ? `Reference "${b.reference}"` : "No reference",
  text: `${b.payer}\n${Number(b.amount).toFixed(2)}\nref: ${b.reference || "none"}`,
}));

export function Showcase() {
  const [text, setText] = useState(examples[2].text);
  const line = useMemo(() => parseBankLine(text), [text]);
  const link = useMemo(() => linkPayment(line, invoices), [line]);

  return (
    <section
      aria-labelledby="showcase-title"
      className="relative grid md:min-h-[90svh] md:grid-cols-2"
    >
      <h2 id="showcase-title" className="sr-only">
        Bank line in, invoice out
      </h2>

      {/* Input: what the bank hands over, raw. */}
      <div className="relative flex min-h-[62svh] flex-col bg-slate px-5 pb-28 pt-[18svh] md:min-h-0 md:pl-[8.33vw] md:pr-10 md:pt-[27svh]">
        <label htmlFor="bank-line" className="mb-3 text-body font-semibold">
          A line from Fernhill Supplies&apos; bank statement. Edit it.
        </label>
        <textarea
          id="bank-line"
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={3}
          spellCheck={false}
          className="w-full max-w-[34ch] resize-none bg-transparent text-lead font-semibold leading-snug outline-none"
        />
        <div className="mt-6 flex flex-wrap gap-2" role="group" aria-label="Try a real line">
          {examples.map((ex) => (
            <button
              key={ex.label}
              type="button"
              onClick={() => setText(ex.text)}
              aria-pressed={ex.text === text}
              className="press bg-ink/10 px-3 py-2 text-small font-semibold hover:bg-ink/20 aria-pressed:bg-ink aria-pressed:text-paper"
            >
              {ex.label}
            </button>
          ))}
        </div>
        <Reveal
          as="p"
          aria-hidden
          className="reveal-mask display absolute bottom-8 left-5 text-[11vw] md:left-[8.33vw] md:text-section"
        >
          <span>Bank line in,</span>
        </Reveal>
      </div>

      {/* Output: the record ShadowCost makes of it. */}
      <div className="relative flex min-h-[62svh] flex-col bg-blush px-5 pb-28 pt-12 md:min-h-0 md:px-10 md:pt-[27svh]">
        <div
          data-ui
          aria-live="polite"
          className="w-full max-w-[500px] rounded-[10px] border border-ink/10 bg-sheet p-6 text-body text-ink"
        >
          <div className="flex items-baseline justify-between gap-4">
            <span className="text-small text-muted">Payment received</span>
            <span className="text-small text-muted">
              {line.amount !== null ? money(line.amount) : "—"}
            </span>
          </div>
          <p className="mt-1 truncate text-lead font-semibold">{line.payer || "Unknown payer"}</p>

          <div key={link.kind === "none" ? `none:${line.payer}` : link.invoice.id} className="arrive">
          {link.kind === "none" ? (
            <div className="mt-5 rounded-md bg-wait-tint px-4 py-3 text-wait">
              <p className="font-semibold">Not linked</p>
              <p className="mt-1 leading-snug">{link.reason}</p>
            </div>
          ) : (
            <>
              <dl className="mt-5 grid grid-cols-[auto_1fr] gap-x-6 gap-y-2.5">
                <dt className="text-muted">Invoice</dt>
                <dd className="font-semibold">{link.invoice.id}</dd>
                <dt className="text-muted">Customer</dt>
                <dd>{link.invoice.customer}</dd>
                <dt className="text-muted">Amount due</dt>
                <dd>{money(link.invoice.amount)}</dd>
                <dt className="text-muted">Matched by</dt>
                <dd>
                  {link.kind === "reference"
                    ? `the reference "${link.read}"`
                    : `exact amount, and a payer name ${Math.round(link.similarity * 100)}% like the customer's`}
                </dd>
              </dl>
              <p className="mt-5 rounded-md bg-good-tint px-4 py-3 leading-snug text-good">
                The payments agent would set <b>status</b> to paid and <b>paid_date</b> to the bank
                date.
              </p>
            </>
          )}
          </div>
        </div>
        <Reveal
          as="p"
          aria-hidden
          delay={140}
          className="reveal-mask display absolute bottom-8 right-5 text-[11vw] md:right-10 md:text-section"
        >
          <span>invoice out.</span>
        </Reveal>
      </div>
    </section>
  );
}
