"use client";

import { useCallback, useRef, useState } from "react";
import data from "@/data/landing.json";
import { useScrollProgress } from "@/lib/scroll";

/**
 * The climb (scroll scene, held for three screens). The page's four chapter colours are the four
 * rungs of the autonomy ladder, so the scene turns the whole field into each rung in turn while
 * the invoice agent's cases fill in, one square per case compared with the person. The figures
 * are the real rule: 30 cases, and the 95% Wilson lower bound of agreement must clear 0.85. The
 * invoice agent agreed on every case, so its bound is n / (n + 1.96²) and clears 0.85 at case 22.
 *
 * Without scripts or with reduced motion the section is one screen showing where it ended.
 */
const CASES = 30;
const BAR = 0.85;
const Z2 = 1.96 * 1.96;
const agent = data.agents[0];
const date = (iso: string) =>
  new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });

const RUNGS = [
  {
    word: "Shadow",
    title: "First it watches",
    field: "bg-slate text-ink",
    does: "Every case is compared with what the person did, and nothing is sent.",
    next: "Promoted to drafting",
  },
  {
    word: "Draft",
    title: "Then it drafts",
    field: "bg-blush text-ink",
    does: "Emails wait in an outbox for the person to check and send.",
    next: "Promoted to asking",
  },
  {
    word: "Approval",
    title: "Next it asks",
    field: "bg-sage text-ink",
    does: "Each action waits for one click from an approver.",
    next: "Promoted to acting alone",
  },
  {
    word: "Autonomous",
    title: "Finally it acts alone",
    field: "bg-olive text-paper",
    does: "And it drops back to watching the moment its agreement slips.",
    next: "Still agreeing",
  },
];

export function Climb() {
  const ref = useRef<HTMLElement>(null);
  // Server render and reduced motion show where the climb ends.
  const [state, setState] = useState({ rung: 3, cases: CASES });
  const onChange = useCallback((p: number) => {
    const scaled = Math.min(p * RUNGS.length, RUNGS.length - 0.0001);
    const rung = Math.floor(scaled);
    const cases = Math.min(CASES, Math.floor(((scaled - rung) / 0.75) * CASES));
    setState((s) => (s.rung === rung && s.cases === cases ? s : { rung, cases }));
  }, []);
  useScrollProgress(ref, "hold", onChange);

  const { rung, cases } = state;
  const r = RUNGS[rung];
  const span = agent.spans[rung];
  const bound = cases ? cases / (cases + Z2) : 0;
  const done = cases === CASES;
  const light = rung === 3;

  return (
    <section ref={ref} aria-label="Trust, earned case by case" className="climb relative">
      <div className={`climb-field climb-stage flex min-h-[100svh] flex-col px-4 pb-8 pt-16 md:px-7 md:pb-10 md:pt-20 ${r.field}`}>
        <div className="grid gap-8 md:grid-cols-12 md:gap-6">
          <div className="md:col-span-7">
            <h2 className="display overflow-hidden pb-[0.06em] text-head">
              <span key={r.title} className="climb-word block">
                {r.title}
              </span>
            </h2>
            <p className="mt-5 max-w-[40ch] text-lead leading-snug" aria-live="polite">
              {r.does}
            </p>
          </div>

          <div
            data-ui
            className="w-full max-w-[460px] rounded-[10px] bg-sheet p-5 text-ink md:col-span-5 md:col-start-8 md:justify-self-end lg:col-span-4 lg:col-start-9 md:p-6"
          >
            <div className="flex items-baseline justify-between gap-4">
              <p className="text-body font-semibold">{agent.name}</p>
              <p className="whitespace-nowrap text-small text-muted">from {date(span.from)}</p>
            </div>
            <div
              className="mt-4 grid grid-cols-10 gap-1.5"
              role="img"
              aria-label={`${cases} of ${CASES} cases compared, all agreeing with the person`}
            >
              {Array.from({ length: CASES }, (_, i) => (
                <span
                  key={i}
                  data-on={i < cases || undefined}
                  className={`climb-cell aspect-square rounded-[3px] ${i < cases ? (light ? "bg-olive" : "bg-ink") : "bg-rule"}`}
                />
              ))}
            </div>
            <dl className="mt-5 grid grid-cols-3 gap-3">
              <div>
                <dt className="text-small text-muted">Cases</dt>
                <dd className="text-lead font-semibold">
                  {cases}
                  <span className="text-small font-normal text-muted"> of {CASES}</span>
                </dd>
              </div>
              <div>
                <dt className="text-small text-muted">Agreed</dt>
                <dd className="text-lead font-semibold">{cases ? "100%" : "—"}</dd>
              </div>
              <div>
                <dt className="text-small text-muted">Lower bound</dt>
                <dd className={`text-lead font-semibold ${bound >= BAR ? "text-good" : ""}`}>
                  {cases ? bound.toFixed(2) : "—"}
                </dd>
              </div>
            </dl>
            <p
              className={`mt-4 rounded-md px-3 py-2.5 text-small ${done ? "bg-good-tint text-good" : "bg-hover text-muted"}`}
            >
              {done
                ? `${r.next}${rung < 3 ? ` on ${date(agent.spans[rung + 1].from)}` : `: ${span.days} days alone`}`
                : `Needs ${CASES} cases and a bound of ${BAR} or more`}
            </p>
          </div>
        </div>

        <p aria-hidden className="mt-auto overflow-hidden pt-10">
          <span key={r.word} className="climb-word display block text-[13vw] leading-[0.86] md:text-[clamp(96px,16vw,280px)]">
            {r.word}
          </span>
        </p>
      </div>
    </section>
  );
}
