import type { Metadata } from "next";
import { SitePage } from "@/components/site/Site";
import { Reveal } from "@/lib/reveal";

export const metadata: Metadata = {
  title: "Security · ShadowCost",
  description: "How ShadowCost keeps a company's spreadsheets, bank exports and email headers separate and safe.",
};

const SECTIONS = [
  {
    title: "Agents don't act until they've earned it",
    points: [
      "Every agent starts in shadow mode: it predicts, and nothing it predicts is applied.",
      "Promotion is gated on measured agreement with the person, using a lower confidence bound rather than a raw percentage, so a lucky streak doesn't count.",
      "Agreement that falls moves the agent back down the ladder automatically.",
      "Proposed changes wait in an approval queue. Only an approver or above can accept one, and every decision records who made it.",
    ],
  },
  {
    title: "Each workspace is walled off",
    points: [
      "Data lives in Postgres and private object storage (Supabase), with row-level security on every table.",
      "Every API request carries a signed session token that is verified against the identity provider's published keys, then checked against the workspace's membership list.",
      "Requests for a workspace you aren't in get the same answer as one that doesn't exist.",
      "Uploaded files are stored under the workspace's own prefix in a private bucket; zip archives are unpacked with path checks so a file can't escape its folder.",
    ],
  },
  {
    title: "We take as little as we can",
    points: [
      "The Google connector asks for read-only access to Sheets and Gmail.",
      "From Gmail it keeps the sender, recipients, subject, date and the short preview line, never the full body or attachments.",
      "Google refresh tokens are encrypted at rest and never sent to the browser.",
      "Disconnecting Google deletes the stored token at once; deleting a dataset deletes its files.",
    ],
  },
  {
    title: "Payments and email",
    points: [
      "Card details go straight to Stripe's hosted checkout; ShadowCost never sees them.",
      "Stripe webhooks are verified with their signing secret before anything changes.",
      "Notification emails are sent through Resend and logged in the workspace, so you can see exactly what went out and to whom.",
    ],
  },
  {
    title: "Roles",
    points: [
      "Owner: everything, including billing and deleting the workspace's data.",
      "Admin: data, connectors, drafting agents and the team.",
      "Approver: approves agents and decides on queued actions.",
      "Viewer: reads everything and changes nothing.",
    ],
  },
];

export default function SecurityPage() {
  return (
    <SitePage
      band="slate"
      title="Built to be trusted slowly"
      line="ShadowCost is the agent that asks first. The platform underneath is built the same way."
    >
      <div className="grid gap-x-6 gap-y-14 md:grid-cols-2">
        {SECTIONS.map((s, i) => (
          <Reveal as="section" key={s.title} delay={(i % 2) * 90} className="reveal">
            <h2 className="text-lead font-semibold leading-tight">{s.title}</h2>
            <ul className="mt-5 space-y-4 text-body leading-relaxed">
              {s.points.map((p) => (
                <li key={p} className="max-w-[56ch]">
                  {p}
                </li>
              ))}
            </ul>
          </Reveal>
        ))}
      </div>
      <p className="mt-16 max-w-[60ch] text-small">
        ShadowCost is an early product and has not been through a formal audit such as SOC 2. The source code is public,
        so every claim on this page can be checked.
      </p>
    </SitePage>
  );
}
