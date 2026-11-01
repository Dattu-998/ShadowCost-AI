import data from "@/data/landing.json";
import { Reveal } from "@/lib/reveal";

/**
 * Stages as one bar (dealt). The diagram is the invoice agent's real path through a simulated
 * year: each segment is one stage of the autonomy ladder, as wide as the days it really spent
 * there, in that stage's chapter colour.
 */
const STAGES = {
  shadow: {
    color: "bg-slate text-ink",
    clause: "First it watches: every case is compared with what the person did, and nothing is sent.",
  },
  draft: {
    color: "bg-blush text-ink",
    clause: "Then it drafts: emails wait in an outbox for the person to check and send.",
  },
  approval: {
    color: "bg-sage text-ink",
    clause: "Next it asks: each action waits for one click of approval.",
  },
  autonomous: {
    color: "bg-olive text-paper",
    clause: "Finally it acts alone, and goes back to watching the moment it slips.",
  },
} as const;

const agent = data.agents[0];
const format = (iso: string) =>
  new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });

export function Stages() {
  return (
    <section
      aria-labelledby="stages-title"
      className="flex min-h-[90svh] flex-col justify-center bg-paper px-4 py-24 md:px-7"
    >
      <div className="grid gap-6 md:grid-cols-12 md:items-end md:gap-6">
      <Reveal
        as="h2"
        id="stages-title"
        className="reveal display max-w-[14ch] text-[11vw] md:col-span-7 md:text-section"
      >
        Trust, earned in four steps
      </Reveal>
      <Reveal as="p" delay={80} className="reveal max-w-[44ch] text-body leading-relaxed md:col-span-5 md:col-start-8">
        The invoice agent&apos;s real path through a simulated year at {data.company}. A stage is
        earned with 30 cases whose agreement with the person clears 0.85 at 95% confidence, and the
        count starts again at every step.
      </Reveal>
      </div>

      <Reveal
        data-ui
        delay={160}
        className="reveal mt-16 flex flex-col gap-1.5 md:h-[22vh] md:min-h-[150px] md:flex-row"
        role="img"
        aria-label={agent.spans.map((s) => `${s.stage} for ${s.days} days`).join(", ")}
      >
        {agent.spans.map((span) => (
          <div
            key={span.stage}
            className={`flex min-h-[72px] flex-col justify-between p-5 ${STAGES[span.stage as keyof typeof STAGES].color}`}
            style={{ flexGrow: Math.max(span.days, 25), flexBasis: 0 }}
          >
            <span className="text-lead font-semibold leading-none">
              {span.days} days
            </span>
            <span className="text-small">
              {span.stage[0].toUpperCase() + span.stage.slice(1)} from {format(span.from)}
            </span>
          </div>
        ))}
      </Reveal>
      <ol className="mt-5 grid gap-5 md:flex md:gap-1.5">
        {agent.spans.map((span, i) => (
          <Reveal
            as="li"
            key={span.stage}
            delay={240 + i * 70}
            className="reveal max-w-[24ch] text-body leading-snug"
            style={{ flexGrow: Math.max(span.days, 25), flexBasis: 0 }}
          >
            {STAGES[span.stage as keyof typeof STAGES].clause}
          </Reveal>
        ))}
      </ol>
    </section>
  );
}
