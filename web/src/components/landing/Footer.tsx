import Link from "next/link";

/** A footer of tiles (dealt): the last two rows of the board, every cell used. */
const REPO = process.env.NEXT_PUBLIC_REPO_URL || "https://github.com";
const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function Footer() {
  return (
    <footer className="grid grid-cols-2 gap-1.5 bg-olive p-2 md:grid-cols-12 md:gap-2 md:p-3">
      <Link
        href="/"
        className="col-span-2 flex h-40 items-center justify-center bg-ink text-paper md:order-5 md:col-span-8 md:h-80"
      >
        <span className="display text-[14vw] md:text-[9vw]">ShadowCost</span>
      </Link>
      <Link
        href="/app"
        className="press group col-span-2 flex h-40 flex-col justify-between bg-paper p-5 hover:bg-white md:order-6 md:col-span-4 md:h-80 md:p-6"
      >
        <span className="text-lead font-semibold leading-tight">Open the demo</span>
        <svg
          aria-hidden
          viewBox="0 0 48 48"
          className="ml-auto h-12 w-12 transition-transform group-hover:translate-x-1"
          fill="none"
          stroke="currentColor"
          strokeWidth="4"
        >
          <path d="M6 24h34M28 12l12 12-12 12" />
        </svg>
      </Link>
      <nav
        aria-label="Footer"
        className="flex min-h-40 flex-col justify-between bg-sage p-5 md:order-2 md:col-span-3 md:min-h-[220px] md:p-6"
      >
        <ul className="space-y-1.5 text-body">
          <li>
            <a className="hover:underline" href={REPO}>
              Source code
            </a>
          </li>
          <li>
            <a className="hover:underline" href={`${REPO}/blob/main/docs/discovery.md`}>
              How discovery works
            </a>
          </li>
          <li>
            <a className="hover:underline" href={`${REPO}/blob/main/docs/agents.md`}>
              How agents earn trust
            </a>
          </li>
          <li>
            <a className="hover:underline" href={`${API}/docs`}>
              API reference
            </a>
          </li>
        </ul>
      </nav>
      <div className="flex min-h-40 flex-col justify-between bg-blush p-5 md:order-4 md:col-span-3 md:min-h-[220px] md:p-6">
        <p className="text-body font-semibold">Stack</p>
        <p className="text-small leading-snug">
          Python, scikit-learn and FastAPI on Render; Next.js on Vercel; Groq drafts the specs.
        </p>
      </div>
      <div className="flex min-h-40 flex-col justify-between bg-slate p-5 md:order-3 md:col-span-2 md:min-h-[220px] md:p-6">
        <p className="text-body font-semibold">The company</p>
        <p className="text-small leading-snug">Fernhill Supplies is simulated. Every domain ends in .example.</p>
      </div>
      <div className="col-span-2 flex min-h-40 flex-col justify-between bg-paper p-5 md:order-1 md:col-span-4 md:min-h-[220px] md:p-6">
        <p className="text-lead leading-tight">
          Agents that prove themselves against real human work before they get autonomy.
        </p>
        <p className="text-small">
          MIT licence · 2026. Pictures:{" "}
          <a className="underline" href="https://commons.wikimedia.org/wiki/File:Pittsboro_Merchant_Business_Ledger_-_DPLA_-_4cbfce8f8f08c14f851ab74af046c082_(page_258).jpg">
            Pittsboro Merchant Business Ledger
          </a>
          , public domain;{" "}
          <a className="underline" href="https://commons.wikimedia.org/wiki/File:Remington_Adding_Machine_Model_102.jpg">
            Remington Adding Machine Model 102
          </a>{" "}
          by Issac I Navarro,{" "}
          <a className="underline" href="https://creativecommons.org/licenses/by/4.0">
            CC BY 4.0
          </a>
          ; both via Wikimedia Commons.
        </p>
      </div>
    </footer>
  );
}
