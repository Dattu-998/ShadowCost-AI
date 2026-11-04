"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Reveal } from "@/lib/reveal";

/**
 * First step, already open (dealt). The close is the app's own first step at true size: name who
 * approves agents and pick the data, and the demo opens with both already set.
 */
const DATASETS = [
  { id: "sample", label: "4 months" },
  { id: "year", label: "A full year" },
] as const;

export function Cta() {
  const router = useRouter();
  const [name, setName] = useState("Office manager");
  const [dataset, setDataset] = useState<(typeof DATASETS)[number]["id"]>("year");

  function open(event: React.FormEvent) {
    event.preventDefault();
    try {
      localStorage.setItem("shadowcost.approver", name.trim() || "Office manager");
      localStorage.setItem("shadowcost.dataset", dataset);
    } catch {
      // Storage can be unavailable (private mode); the demo then uses its defaults.
    }
    router.push("/demo");
  }

  return (
    <section
      aria-labelledby="cta-title"
      className="grid min-h-[90svh] gap-12 bg-olive px-4 py-20 text-paper md:grid-cols-12 md:gap-6 md:px-7 md:py-10"
    >
      <div className="flex flex-col md:col-span-5 md:justify-end md:pb-10">
        <Reveal
          as="h2"
          id="cta-title"
          className="reveal-mask display text-[13vw] [line-height:0.92] md:text-section"
        >
          <span>Watch one earn trust</span>
        </Reveal>
        <Reveal as="p" delay={80} className="reveal mt-6 max-w-[40ch] text-body leading-snug">
          The demo opens on {`Fernhill Supplies'`} files. Approve an agent there and it starts by
          watching, climbing only as its cases agree with the person&apos;s.
        </Reveal>
      </div>

      <div className="flex items-end md:col-span-5 md:col-start-7 md:items-start md:pt-[14svh]">
        <Reveal delay={120} className="reveal w-full">
          <form
            data-ui
            onSubmit={open}
            className="floating-dialog w-full max-w-[440px] rounded-[12px] bg-sheet p-6 text-ink"
          >
            <h3 className="text-lead font-semibold">Open the demo</h3>
            <p className="mt-1 text-small text-muted">Approvals are signed with this name.</p>

            <label htmlFor="approver" className="mt-5 block text-small font-semibold">
              Who approves agents
            </label>
            <input
              id="approver"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoComplete="name"
              className="mt-1.5 h-11 w-full rounded-md border border-control px-3 text-body outline-none focus:border-ink"
            />

            <fieldset className="mt-5">
              <legend className="text-small font-semibold">Data</legend>
              <div className="mt-1.5 grid grid-cols-2 rounded-md bg-frame p-1">
                {DATASETS.map((d) => (
                  <label
                    key={d.id}
                    className="press cursor-pointer rounded-[5px] py-2 text-center text-body has-checked:bg-sheet has-checked:font-semibold has-focus-visible:outline-2"
                  >
                    <input
                      type="radio"
                      name="dataset"
                      value={d.id}
                      checked={dataset === d.id}
                      onChange={() => setDataset(d.id)}
                      className="sr-only"
                    />
                    {d.label}
                  </label>
                ))}
              </div>
            </fieldset>

            <button
              type="submit"
              className="press mt-6 h-[52px] w-full bg-olive text-body font-semibold text-paper hover:bg-ink md:h-12"
            >
              Open the demo
            </button>
            <p className="mt-4 text-center text-small text-muted">
              Ready for your own files?{" "}
              <Link href="/signup" className="font-semibold text-ink underline-offset-4 hover:underline">
                Start free
              </Link>
            </p>
          </form>
        </Reveal>
      </div>
    </section>
  );
}
