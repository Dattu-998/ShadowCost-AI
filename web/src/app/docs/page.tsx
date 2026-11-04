import type { Metadata } from "next";
import Link from "next/link";
import { Prose, SitePage } from "@/components/site/Site";

export const metadata: Metadata = {
  title: "Docs · ShadowCost",
  description: "Getting started with ShadowCost: data formats, discovery, the autonomy ladder, approvals and the API.",
};

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const REPO = process.env.NEXT_PUBLIC_REPO_URL || "https://github.com/Dattu-998/ShadowCost-AI";

const CONTENTS = [
  ["start", "Getting started"],
  ["data", "What data to bring"],
  ["discover", "How discovery works"],
  ["agents", "Agents and the autonomy ladder"],
  ["queue", "Approvals and the queue"],
  ["google", "The Google connector"],
  ["team", "Team and roles"],
  ["api", "API"],
] as const;

export default function DocsPage() {
  return (
    <SitePage
      eyebrow="Docs"
      band="blush"
      title="From a folder of files to an agent you trust"
      line="Everything a new workspace needs, in the order you'll need it."
    >
      <div className="grid gap-10 md:grid-cols-12">
        <nav aria-label="On this page" className="md:col-span-3">
          <ol className="space-y-1.5 text-body md:sticky md:top-6">
            {CONTENTS.map(([id, label]) => (
              <li key={id}>
                <a href={`#${id}`} className="hover:underline">
                  {label}
                </a>
              </li>
            ))}
          </ol>
        </nav>
        <div className="md:col-span-8 md:col-start-5">
          <Prose>
            <h2 id="start" className="!mt-0">Getting started</h2>
            <ol>
              <li>
                <Link href="/signup">Create an account</Link> and name your workspace.
              </li>
              <li>Add data: the sample company, your own files, or a Google connection.</li>
              <li>Open <strong>Discover</strong> to see the repeated workflows ShadowCost found, with how often each runs and how many hours it takes.</li>
              <li>On <strong>Data</strong>, choose <strong>Draft agents</strong>. Each regular workflow gets an agent spec, backtested on cases it hasn&apos;t seen.</li>
              <li>On <strong>Agents</strong>, read the spec and its backtest, then approve the ones you&apos;d trust to watch.</li>
              <li><strong>Shadow mode</strong> replays your history day by day and shows each agent climbing, or not.</li>
            </ol>

            <h2 id="data">What data to bring</h2>
            <p>ShadowCost works from the files a small office already has. It doesn&apos;t need event logs.</p>
            <ul>
              <li>
                <strong>Dated copies of a working spreadsheet</strong>, such as <code>ledger_2026-03-01.csv</code>,{" "}
                <code>ledger_2026-03-02.csv</code>. The date in the file name is when the copy was taken. Changes between
                copies become events.
              </li>
              <li><strong>A bank export</strong> (CSV or Excel) with a date, an amount and a description or reference.</li>
              <li><strong>An email export</strong> as JSON lines with sender, recipients, subject, date and a short preview.</li>
            </ul>
            <p>Upload them loose or as one zip, up to 50 MB. Daily copies for two months or more give the best results.</p>

            <h2 id="discover">How discovery works</h2>
            <p>
              Events from the three sources are linked to cases (an invoice number found in a bank reference, an email
              subject or a spreadsheet row). Each case becomes a sequence of steps. Sequences that repeat with a regular
              trigger and a consistent shape are reported as workflows, with the hours they take each month and an
              automation score. The full method is in the{" "}
              <a href={`${REPO}/blob/main/docs/discovery.md`}>discovery notes</a>.
            </p>

            <h2 id="agents">Agents and the autonomy ladder</h2>
            <p>An agent is a short, readable spec: when it runs, which rows it looks at, and what it would change or send.</p>
            <ul>
              <li><strong>Shadow</strong>: predicts only. Nothing is applied.</li>
              <li><strong>Draft</strong>: prepares the change and the email for a person to finish.</li>
              <li><strong>Approval</strong>: proposes the change; an approver accepts or rejects it.</li>
              <li><strong>Autonomous</strong>: applies the change itself.</li>
            </ul>
            <p>
              An agent climbs a stage when the lower bound of its agreement with the person clears the bar over enough
              cases, and drops a stage when it falls under. How agents earn trust is in the{" "}
              <a href={`${REPO}/blob/main/docs/agents.md`}>agent notes</a>.
            </p>

            <h2 id="queue">Approvals and the queue</h2>
            <p>
              At the Approval stage, each proposal waits on <strong>Execute</strong> until an approver decides. Approvers
              get an email when actions are waiting and when an agent is promoted or demoted. Every decision records who
              made it.
            </p>

            <h2 id="google">The Google connector</h2>
            <p>
              On Starter and Growth, an admin can connect a Google account on the <strong>Data</strong> screen. Choose a
              spreadsheet (paste its link), the range to read, and a Gmail search such as{" "}
              <code>newer_than:90d label:invoices</code>. ShadowCost takes a dated copy of the sheet every day and adds
              new matching email headers, so the evidence grows on its own. <strong>Sync now</strong> takes a snapshot
              straight away.
            </p>

            <h2 id="team">Team and roles</h2>
            <p>
              Invite people from <strong>Settings → Team</strong>. Owners manage billing; admins manage data, agents and
              the team; approvers approve agents and decide on actions; viewers read. Seats depend on the plan.
            </p>

            <h2 id="api">API</h2>
            <p>
              Everything in the app goes through a documented HTTP API, authenticated with the session token. The
              reference is at <a href={`${API}/docs`}>{API.replace(/^https?:\/\//, "")}/docs</a>. Workspace routes live
              under <code>/v1/orgs/&#123;id&#125;</code>.
            </p>
          </Prose>
        </div>
      </div>
    </SitePage>
  );
}
