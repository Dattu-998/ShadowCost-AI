"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";
import useSWR from "swr";
import { API_URL, fetcher, useSlowRequests } from "@/lib/api";
import { DATASETS, useWorkspace } from "@/lib/workspace";

/*
 * Framed sheet shell: the sidebar and the 48px top bar share one slate-tinted frame with no rule
 * between them; the work sits on a white sheet inset 8px from the right and bottom edges, 16px
 * corners, a 1px edge and no shadow. Sidebar 228px. On a phone the frame folds away.
 */

const NAV = [
  { href: "/app", label: "Overview", icon: "M3 3h6v6H3zM11 3h6v4h-6zM11 9h6v8h-6zM3 11h6v6H3z" },
  { href: "/app/discover", label: "Discover", icon: "M8.5 14a5.5 5.5 0 1 0 0-11 5.5 5.5 0 0 0 0 11zM12.5 12.5 17 17" },
  { href: "/app/agents", label: "Agents", icon: "M10 3v3M5 8h10v8H5zM8 11.5h.01M12 11.5h.01M3 11v3M17 11v3" },
  { href: "/app/shadow", label: "Shadow mode", icon: "M3 16h3v-3H3zM8.5 16h3V9h-3zM14 16h3V4h-3z" },
  { href: "/app/execute", label: "Execute", icon: "M5 3.5v13l11-6.5z" },
  { href: "/app/report", label: "Report", icon: "M5 2.5h7l3 3v12H5zM8 9h6M8 12h6M8 15h4" },
];

export function Mark({ className = "h-5 w-5" }: { className?: string }) {
  // The ladder as the product's mark: four rising steps in the four stage colours.
  return (
    <svg viewBox="0 0 20 20" className={className} aria-hidden>
      <rect x="1" y="13" width="3.6" height="6" rx="1" fill="#a6b3bc" />
      <rect x="5.8" y="9.5" width="3.6" height="9.5" rx="1" fill="#d6c4b8" />
      <rect x="10.6" y="6" width="3.6" height="13" rx="1" fill="#b7c8be" />
      <rect x="15.4" y="2" width="3.6" height="17" rx="1" fill="#2c3620" />
    </svg>
  );
}

function Icon({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 20 20" className="h-4 w-4 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" aria-hidden>
      <path d={d} />
    </svg>
  );
}

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { dataset, setDataset, approver, setApprover } = useWorkspace();
  return (
    <div className="flex h-full flex-col px-3 pb-4 pt-3">
      <Link href="/" className="flex h-10 items-center gap-2.5 px-2 text-[15px] font-semibold" onClick={onNavigate}>
        <Mark />
        ShadowCost
      </Link>

      <div className="mt-4 px-2">
        <p className="text-[13px] font-semibold">Fernhill Supplies</p>
        <div role="radiogroup" aria-label="Data" className="mt-2 grid grid-cols-2 rounded-md bg-[#e2e7ea] p-0.5">
          {DATASETS.map((d) => (
            <button
              key={d.id}
              role="radio"
              aria-checked={dataset === d.id}
              title={d.detail}
              onClick={() => setDataset(d.id)}
              className={`press rounded-[5px] py-1 text-[13px] ${dataset === d.id ? "bg-sheet font-semibold" : "text-muted hover:text-ink"}`}
            >
              {d.label}
            </button>
          ))}
        </div>
      </div>

      <nav aria-label="App" className="mt-6 space-y-0.5">
        {NAV.map((item) => {
          const active = item.href === "/app" ? pathname === "/app" : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              className={`flex h-8 items-center gap-2.5 rounded-lg px-2.5 text-[14px] ${active ? "bg-[#dde3e7] font-semibold text-ink" : "text-[#4f5962] hover:bg-[#e4e9ec] hover:text-ink"}`}
            >
              <Icon d={item.icon} />
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="mt-auto space-y-3 px-2">
        <label className="block">
          <span className="text-[12px] text-muted">Approving as</span>
          <input
            value={approver}
            onChange={(e) => setApprover(e.target.value)}
            className="mt-1 h-8 w-full rounded-md border border-control bg-sheet px-2 text-[13px] outline-none focus:border-ink"
          />
        </label>
        <Link href="/" className="block text-[13px] text-muted hover:text-ink">
          Back to the site
        </Link>
      </div>
    </div>
  );
}

function Status() {
  const slow = useSlowRequests();
  const { error, data } = useSWR<{ status: string; version: string }>("/health", fetcher, {
    refreshInterval: 60_000,
  });
  if (slow) {
    return (
      <span className="text-[13px] text-wait" role="status">
        Waking the API: free hosting sleeps when idle, about a minute
      </span>
    );
  }
  if (error) return <span className="text-[13px] text-bad">API unreachable</span>;
  return (
    <a href={`${API_URL}/docs`} className="text-[13px] text-muted hover:text-ink">
      {data ? `API ${data.version}` : "Connecting…"}
    </a>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const current = NAV.find((n) => (n.href === "/app" ? pathname === "/app" : pathname.startsWith(n.href)));

  return (
    <div className="min-h-svh bg-frame text-ink md:grid md:h-svh md:grid-cols-[228px_1fr] md:grid-rows-[48px_1fr] md:overflow-hidden">
      <aside className="hidden md:row-span-2 md:block">
        <Sidebar />
      </aside>

      <header className="sticky top-0 z-20 flex h-12 items-center gap-3 bg-frame px-4 md:static md:px-2 md:pr-4">
        <button
          className="-ml-1 rounded-md p-1.5 hover:bg-[#e4e9ec] md:hidden"
          aria-label="Open menu"
          aria-expanded={open}
          onClick={() => setOpen(true)}
        >
          <svg viewBox="0 0 20 20" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden>
            <path d="M3 6h14M3 10h14M3 14h14" />
          </svg>
        </button>
        <p className="text-[14px]">
          <span className="text-muted">Fernhill Supplies /</span>{" "}
          <span className="font-semibold">{current?.label ?? "Overview"}</span>
        </p>
        <div className="ml-auto">
          <Status />
        </div>
      </header>

      <main className="bg-sheet md:mb-2 md:mr-2 md:overflow-y-auto md:rounded-2xl md:border md:border-edge">
        <div className="mx-auto max-w-[1360px] p-4 md:p-6">{children}</div>
      </main>

      {open && (
        <div className="fixed inset-0 z-30 md:hidden" role="dialog" aria-modal="true" aria-label="Menu">
          <button className="absolute inset-0 bg-ink/30" aria-label="Close menu" onClick={() => setOpen(false)} />
          <div className="absolute inset-y-0 left-0 w-[280px] bg-frame shadow-[0_8px_32px_rgba(0,0,0,0.2)]">
            <Sidebar onNavigate={() => setOpen(false)} />
          </div>
        </div>
      )}
    </div>
  );
}
