import type { Metadata } from "next";
import Link from "next/link";
import { SitePage } from "@/components/site/Site";
import { PLANS } from "@/data/plans";

export const metadata: Metadata = {
  title: "Pricing · ShadowCost",
  description: "Free to find your repeated work. $49 a month for a small office, $149 for a finance team.",
};

const ROWS: { label: string; value: (p: (typeof PLANS)[number]) => string }[] = [
  { label: "Seats", value: (p) => String(p.members) },
  { label: "Datasets", value: (p) => String(p.datasets) },
  { label: "Approved agents", value: (p) => (p.approved_agents === null ? "Unlimited" : String(p.approved_agents)) },
  { label: "File uploads (CSV, Excel, JSON, zip)", value: () => "Yes" },
  { label: "Google Sheets and Gmail connector", value: (p) => (p.connectors ? "Daily sync" : "—") },
  { label: "Shadow mode and the autonomy ladder", value: () => "Yes" },
  { label: "Approval queue and email alerts", value: () => "Yes" },
  { label: "Savings report", value: () => "Yes" },
  { label: "Roles: owner, admin, approver, viewer", value: (p) => (p.members > 1 ? "Yes" : "Owner only") },
];

const FAQ = [
  [
    "What does ShadowCost need from us?",
    "Dated copies of the spreadsheet your team works in, a bank export and an email export, or a Google connection that takes those snapshots for you. No event logs, no integration project.",
  ],
  [
    "Will an agent change anything without asking?",
    "Not until it has earned it. Every agent starts in shadow mode, where it only predicts. It moves to drafting, then to asking for approval, and only then to acting alone, each step gated by how often its cases matched the person's. A drop in agreement moves it back down.",
  ],
  [
    "How are the savings measured?",
    "From the cases themselves: the minutes a person spent on each kind of case, multiplied by the cases the agent handled at each stage and the share of the work that stage removes. The report shows every number it used.",
  ],
  [
    "Can we cancel?",
    "Any time, from Manage billing. The workspace drops back to Free at the end of the period and keeps its data.",
  ],
] as const;

export default function PricingPage() {
  return (
    <SitePage
      eyebrow="Pricing"
      band="sage"
      title="Pay once the agents are earning"
      line="Find your repeated work for free. Pay when you want more of it handed over."
    >
      <div className="grid gap-2 md:grid-cols-3">
        {PLANS.map((p) => (
          <section
            key={p.id}
            className={`flex flex-col p-6 md:p-8 ${p.id === "starter" ? "bg-olive text-paper" : "bg-[#eceae3]"}`}
          >
            <h2 className="text-lead font-semibold">{p.name}</h2>
            <p className="mt-6">
              <span className="display text-[64px]">${p.monthly_usd}</span>
              <span className="ml-2 text-body">a month</span>
            </p>
            <p className="mt-4 max-w-[34ch] text-body leading-snug">{p.blurb}</p>
            <ul className="mt-6 space-y-1.5 text-body">
              <li>{p.members === 1 ? "1 seat" : `${p.members} seats`}</li>
              <li>{p.datasets} datasets</li>
              <li>{p.approved_agents === null ? "Unlimited agents" : `${p.approved_agents} approved agent${p.approved_agents === 1 ? "" : "s"}`}</li>
              <li>{p.connectors ? "Google Sheets and Gmail" : "File uploads"}</li>
            </ul>
            <Link
              href="/signup"
              className={`press mt-10 inline-flex h-12 items-center justify-center px-5 text-body font-semibold ${p.id === "starter" ? "bg-paper text-ink hover:bg-white" : "bg-olive text-paper hover:bg-ink"}`}
            >
              {p.cta}
            </Link>
          </section>
        ))}
      </div>
      <p className="mt-4 text-small">
        Prices in US dollars, billed monthly through Stripe. Paid plans start from Settings after you sign up. Larger
        team? <Link href="/contact" className="underline">Book a demo</Link>.
      </p>

      <section aria-labelledby="compare" className="mt-20">
        <h2 id="compare" className="text-lead font-semibold">
          Compare plans
        </h2>
        <div className="mt-6 overflow-x-auto">
          <table className="w-full min-w-[620px] text-body">
            <thead>
              <tr className="border-b-2 border-ink text-left">
                <th className="py-3 pr-4 font-normal">
                  <span className="sr-only">Feature</span>
                </th>
                {PLANS.map((p) => (
                  <th key={p.id} className="w-[18%] py-3 font-semibold">
                    {p.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ROWS.map((row) => (
                <tr key={row.label} className="border-b border-[#cfcdc3]">
                  <th scope="row" className="py-3 pr-4 text-left font-normal">
                    {row.label}
                  </th>
                  {PLANS.map((p) => (
                    <td key={p.id} className="tabular py-3">
                      {row.value(p)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section aria-labelledby="faq" className="mt-20 grid gap-8 md:grid-cols-12">
        <h2 id="faq" className="text-lead font-semibold md:col-span-4">
          Questions before you start
        </h2>
        <dl className="space-y-8 md:col-span-7 md:col-start-6">
          {FAQ.map(([q, a]) => (
            <div key={q}>
              <dt className="text-body font-semibold">{q}</dt>
              <dd className="mt-2 max-w-[60ch] text-body leading-relaxed">{a}</dd>
            </div>
          ))}
        </dl>
      </section>
    </SitePage>
  );
}
