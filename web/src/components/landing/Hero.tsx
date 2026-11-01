import Link from "next/link";

/**
 * Waterline headline (dealt). Two flat fields meet at half height: paper above, slate below.
 * The product's name crosses the seam in the olive of autonomy, its second line half in the
 * light and half below the waterline, as if the work were still being done out of sight.
 *
 * The blueprint draws the headline twice, each copy clipped to its field so the ink can change
 * at the seam. Olive and ink are nearly the same darkness here, so one copy carries the effect
 * and the headline stays whole for readers and for the inspector.
 */
const LINES = ["SHADOW", "COST"];

export function Hero() {
  return (
    <header className="relative h-[100svh] min-h-[560px] overflow-hidden [--hero-size:15.5vw] [--seam-px:max(46svh,258px)] md:[--hero-size:clamp(72px,9vw,140px)] md:[--seam-px:max(50svh,280px)]">
      <div aria-hidden className="absolute inset-x-0 top-0 h-[var(--seam-px)] bg-paper" />
      <div aria-hidden className="absolute inset-x-0 bottom-0 top-[var(--seam-px)] bg-slate" />

      <h1 className="display absolute inset-x-0 top-[calc(var(--seam-px)-1.29*var(--hero-size))] text-center text-olive [font-size:var(--hero-size)] [line-height:0.86]">
        {LINES.map((line) => (
          <span key={line} className="line-mask">
            <span>{line}</span>
          </span>
        ))}
      </h1>

      <nav
        aria-label="Main"
        className="absolute inset-x-0 top-0 flex items-center justify-between px-4 pt-4 md:px-7 md:pt-7"
      >
        <Link href="/" className="text-lead font-semibold tracking-tight">
          ShadowCost
        </Link>
        <Link
          href="/app"
          className="press bg-olive px-4 py-2.5 text-body font-semibold text-paper hover:bg-ink md:px-5 md:py-3"
        >
          Open the demo
        </Link>
      </nav>

      <p className="fade-after-lines absolute inset-x-4 bottom-8 max-w-[34ch] text-lead leading-snug md:inset-x-0 md:bottom-10 md:mx-auto md:max-w-[46ch] md:text-center">
        It finds the repetitive invoice, payment and email work in a small company, and hands it to
        an agent only after the agent has matched the person, case by case.
      </p>
    </header>
  );
}
