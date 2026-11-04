import type { Metadata } from "next";
import { DemoForm } from "@/components/site/DemoForm";
import { SitePage } from "@/components/site/Site";

export const metadata: Metadata = {
  title: "Book a demo · ShadowCost",
  description: "Tell us about the repeated work in your office and we'll walk you through ShadowCost on it.",
};

export default function ContactPage() {
  return (
    <SitePage
      eyebrow="Book a demo"
      band="sage"
      title="Show us the spreadsheet everyone dreads"
      line="Thirty minutes. We'll run discovery on a sample of your files and show you which workflows an agent could take, and how long it would take to earn it."
    >
      <div className="grid gap-12 md:grid-cols-12">
        <div className="md:col-span-5">
          <h2 className="text-lead font-semibold">What happens next</h2>
          <ol className="mt-5 space-y-4 text-body leading-relaxed">
            <li className="border-t border-[#cfcdc3] pt-3">We reply within one working day to find a time.</li>
            <li className="border-t border-[#cfcdc3] pt-3">
              If you&apos;d like, you share a few weeks of exports beforehand. Nothing leaves the workspace we set up for you.
            </li>
            <li className="border-t border-[#cfcdc3] pt-3">
              On the call, you see your own workflows ranked by hours, and an agent replayed through shadow mode.
            </li>
          </ol>
        </div>
        <div className="md:col-span-6 md:col-start-7">
          <DemoForm />
        </div>
      </div>
    </SitePage>
  );
}
