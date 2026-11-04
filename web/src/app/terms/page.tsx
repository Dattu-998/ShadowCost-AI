import type { Metadata } from "next";
import { DraftNotice, Prose, SitePage } from "@/components/site/Site";

export const metadata: Metadata = {
  title: "Terms · ShadowCost",
  description: "The terms for using ShadowCost.",
};

export default function TermsPage() {
  return (
    <SitePage band="paper" title="Terms" line="Last updated 3 November 2026.">
      <DraftNotice />
      <Prose>
        <h2 className="!mt-0">The service</h2>
        <p>
          ShadowCost analyses files and connected accounts you provide, finds repeated work, and runs software agents
          that propose, draft or make changes according to the stage each agent has reached. You decide which agents
          are approved and which actions are accepted.
        </p>

        <h2>Your account</h2>
        <ul>
          <li>You need to be able to enter a contract for the business you sign up for.</li>
          <li>Keep your password private. You&apos;re responsible for what happens under your account.</li>
          <li>Owners are responsible for who they invite and the roles they give.</li>
        </ul>

        <h2>Your data</h2>
        <p>
          You own the data you bring. You give ShadowCost permission to store and process it only to provide the
          service to your workspace. You confirm you&apos;re allowed to share it with us, including any personal data
          of your customers or suppliers that appears in it. The <a href="/privacy">privacy notice</a> explains how we
          handle it.
        </p>

        <h2>Agents and decisions</h2>
        <p>
          Agent proposals are predictions based on your history. They can be wrong. Until you approve an agent and it
          reaches a stage that acts on its own, nothing is applied without a person accepting it. You remain
          responsible for the business decisions taken with ShadowCost&apos;s help, including payments and messages to
          third parties.
        </p>

        <h2>Plans and payment</h2>
        <ul>
          <li>Paid plans are billed monthly in advance through Stripe and renew until cancelled.</li>
          <li>You can cancel at any time; the plan runs to the end of the paid period and then returns to Free.</li>
          <li>We&apos;ll give at least 30 days&apos; notice of a price change.</li>
        </ul>

        <h2>Acceptable use</h2>
        <p>
          Don&apos;t use ShadowCost to break the law, to process data you have no right to, to attack the service or
          other customers, or to send unsolicited email.
        </p>

        <h2>Availability and liability</h2>
        <p>
          We work to keep ShadowCost available but don&apos;t guarantee it will be uninterrupted. To the extent the law
          allows, the service is provided as is, and our total liability is limited to the fees you paid in the twelve
          months before the claim.
        </p>

        <h2>Ending</h2>
        <p>
          You can stop using ShadowCost and delete your datasets at any time. We may suspend accounts that break these
          terms. We&apos;ll tell you about material changes to these terms before they take effect.
        </p>
      </Prose>
    </SitePage>
  );
}
