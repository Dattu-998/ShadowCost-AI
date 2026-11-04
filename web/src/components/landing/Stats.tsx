import data from "@/data/landing.json";
import { CountUp } from "@/lib/countup";
import { Reveal } from "@/lib/reveal";

/**
 * Bars standing on the edge (dealt). Hours saved each month over the simulated year, measured
 * against the minutes the office manager actually spent. The olive bar is July, the month the
 * invoice agent first acted alone; every other bar is one tone two steps from the field.
 */
const months = data.monthly_hours_saved;
const max = Math.max(...months.map((m) => m.hours));
const autonomousMonth = data.agents[0].spans.find((s) => s.stage === "autonomous")?.from.slice(0, 7);
const peak = months.reduce((a, b) => (b.hours > a.hours ? b : a)).month;
const labelled = new Set([autonomousMonth, peak, months.at(-2)?.month]);
const monthName = (ym: string, month: "long" | "short" = "long") =>
  new Date(`${ym}-01T00:00:00Z`).toLocaleDateString("en-GB", {
    month,
    ...(month === "long" ? { year: "numeric" } : {}),
    timeZone: "UTC",
  });
const BAR = "#c9a07f";
const GAP = 1.4; // percent of the chart width between bars
const height = (hours: number) => Math.max((hours / max) * 86, 0.6);

export function Stats() {
  const width = 100 / months.length;
  return (
    <section aria-labelledby="stats-title" className="relative flex flex-col bg-blush pt-24 md:pt-28">
      <div className="px-4 md:px-7">
        <Reveal as="p" className="reveal display text-[26vw] md:text-[clamp(88px,10vw,168px)]">
          <CountUp value={data.hours_saved.measured} digits={1} /> h
        </Reveal>
        <Reveal as="h2" id="stats-title" delay={120} className="reveal mt-3 text-lead font-semibold">
          Saved in a year, measured
        </Reveal>
        <Reveal as="p" delay={140} className="reveal mt-3 max-w-[52ch] text-body leading-relaxed">
          Counted from the minutes the office manager really spent on the cases the agents took
          over, month by month. The estimate from stated assumptions was 40.9 h; the measurement
          came in higher. The olive bar is July, when the invoice agent first acted alone.
        </Reveal>
      </div>

      {/* Desktop and tablet: bars standing on the bottom edge, full bleed. */}
      <Reveal data-ui className="grow relative mt-16 hidden h-[58vh] min-h-[320px] md:block">
        <svg
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          className="absolute inset-0 h-full w-full"
          role="img"
          aria-label={months.map((m) => `${monthName(m.month)} ${m.hours} hours`).join(", ")}
        >
          {months.map((m, i) => (
            <rect
              key={m.month}
              className="bar"
              x={i * width + GAP / 2}
              y={100 - height(m.hours)}
              width={width - GAP}
              height={height(m.hours)}
              fill={m.month === autonomousMonth ? "var(--color-olive)" : BAR}
              style={{ ["--delay" as string]: `${i * 50}ms` }}
            />
          ))}
        </svg>
        {months.map((m, i) => (
          <div
            key={m.month}
            tabIndex={0}
            className="group absolute bottom-0 top-0 outline-none"
            style={{ left: `${i * width}%`, width: `${width}%` }}
            aria-label={`${monthName(m.month)}: ${m.hours} hours`}
          >
            {labelled.has(m.month) && (
              <span
                className="absolute left-1/2 -translate-x-1/2 whitespace-nowrap text-lead font-semibold"
                style={{ bottom: `calc(${height(m.hours)}% + 10px)` }}
              >
                {m.hours}
              </span>
            )}
            <span className="absolute left-1/2 top-2 hidden -translate-x-1/2 whitespace-nowrap bg-ink px-2 py-1 text-small text-paper group-hover:block group-focus-visible:block">
              {monthName(m.month)}: {m.hours} h
            </span>
          </div>
        ))}
      </Reveal>

      {/* Phone: bars run sideways from the left edge. */}
      <ol className="mt-12 flex flex-col gap-1.5 pb-10 md:hidden" aria-label="Hours saved per month">
        {months.map((m) => (
          <li key={m.month} className="flex h-7 items-center">
            <span
              className="flex h-full items-center justify-end pr-2 text-small font-semibold"
              style={{
                width: `max(${(m.hours / max) * 82}%, 3.2rem)`,
                background: m.month === autonomousMonth ? "var(--color-olive)" : BAR,
                color: m.month === autonomousMonth ? "var(--color-paper)" : "var(--color-ink)",
              }}
            >
              {m.hours}
            </span>
            <span className="pl-2 text-small">{monthName(m.month, "short")}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}
