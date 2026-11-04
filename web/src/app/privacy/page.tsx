import type { Metadata } from "next";
import { DraftNotice, Prose, SitePage } from "@/components/site/Site";

export const metadata: Metadata = {
  title: "Privacy · ShadowCost",
  description: "What ShadowCost collects, why, who processes it, and how to have it deleted.",
};

const PROCESSORS = [
  ["Supabase", "Accounts, database and file storage", "United States (us-west-1)"],
  ["Render", "The API that processes your data", "United States"],
  ["Vercel", "The website", "Global edge network"],
  ["Stripe", "Payments and invoices", "United States"],
  ["Resend", "Notification emails", "United States"],
  ["Groq", "Drafting agent specs: workflow summaries plus a few example rows and emails", "United States"],
  ["Google", "Only if you connect Sheets and Gmail", "Google's own regions"],
] as const;

export default function PrivacyPage() {
  return (
    <SitePage eyebrow="Privacy notice" band="paper" title="Privacy" line="Last updated 3 November 2026.">
      <DraftNotice />
      <Prose>
        <h2 className="!mt-0">What we collect</h2>
        <ul>
          <li><strong>Account details</strong>: your email address and a hashed password.</li>
          <li><strong>Workspace data</strong>: the files you upload or that the Google connector copies, and what ShadowCost derives from them (events, workflows, agent specs, shadow runs, queued actions).</li>
          <li><strong>From Gmail, if connected</strong>: sender, recipients, subject, date and the short preview line of messages matching your search. Not full bodies or attachments.</li>
          <li><strong>Billing</strong>: your plan and Stripe customer reference. Card details stay with Stripe.</li>
          <li><strong>Demo requests</strong>: the name, email, company and message you send through the contact form.</li>
        </ul>

        <h2>Why</h2>
        <p>
          To run the service for your workspace, to email the people you choose about agents and approvals, to bill paid
          plans, and to reply to demo requests. We don&apos;t sell data and don&apos;t use your workspace data to train
          models.
        </p>

        <h2>Who processes it</h2>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[520px] text-small">
            <thead>
              <tr className="border-b-2 border-ink text-left">
                <th className="py-2 pr-4">Provider</th>
                <th className="py-2 pr-4">For</th>
                <th className="py-2">Where</th>
              </tr>
            </thead>
            <tbody>
              {PROCESSORS.map(([name, use, where]) => (
                <tr key={name} className="border-b border-[#cfcdc3]">
                  <td className="py-2 pr-4 font-semibold">{name}</td>
                  <td className="py-2 pr-4">{use}</td>
                  <td className="py-2">{where}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <h2>How long we keep it</h2>
        <p>
          Workspace data stays until you delete it or close the workspace. Deleting a dataset removes its files.
          Disconnecting Google removes the stored access token immediately. Notification logs are kept for the life of
          the workspace so you can see what was sent.
        </p>

        <h2>Your rights</h2>
        <p>
          You can see, export or delete your data, and correct your account details. Ask through the{" "}
          <a href="/contact">contact page</a> and we&apos;ll answer within 30 days.
        </p>
      </Prose>
    </SitePage>
  );
}
