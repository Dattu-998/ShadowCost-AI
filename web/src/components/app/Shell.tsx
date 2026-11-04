"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";
import useSWR from "swr";
import { API_URL, fetcher, useSlowRequests } from "@/lib/api";
import { supabase } from "@/lib/supabase";
import { remember, useWorkspace } from "@/lib/workspace";

/*
 * Framed sheet shell: the sidebar and the 48px top bar share one slate-tinted frame with no rule
 * between them; the work sits on a white sheet inset 8px from the right and bottom edges, 16px
 * corners, a 1px edge and no shadow. Sidebar 228px. On a phone the frame folds away.
 */

const SCREENS = [
  { path: "", label: "Overview", icon: "M3 3h6v6H3zM11 3h6v4h-6zM11 9h6v8h-6zM3 11h6v6H3z" },
  { path: "/discover", label: "Discover", icon: "M8.5 14a5.5 5.5 0 1 0 0-11 5.5 5.5 0 0 0 0 11zM12.5 12.5 17 17" },
  { path: "/agents", label: "Agents", icon: "M10 3v3M5 8h10v8H5zM8 11.5h.01M12 11.5h.01M3 11v3M17 11v3" },
  { path: "/shadow", label: "Shadow mode", icon: "M3 16h3v-3H3zM8.5 16h3V9h-3zM14 16h3V4h-3z" },
  { path: "/execute", label: "Execute", icon: "M5 3.5v13l11-6.5z" },
  { path: "/report", label: "Report", icon: "M5 2.5h7l3 3v12H5zM8 9h6M8 12h6M8 15h4" },
];
const ORG_SCREENS = [
  { path: "/data", label: "Data", icon: "M4 5c0-1.1 2.7-2 6-2s6 .9 6 2-2.7 2-6 2-6-.9-6-2zM4 5v10c0 1.1 2.7 2 6 2s6-.9 6-2V5M4 10c0 1.1 2.7 2 6 2s6-.9 6-2" },
  { path: "/settings", label: "Settings", icon: "M10 12.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5zM10 2v2M10 16v2M2 10h2M16 10h2M4.2 4.2l1.4 1.4M14.4 14.4l1.4 1.4M4.2 15.8l1.4-1.4M14.4 5.6l1.4-1.4" },
];

export function Mark({ className = "h-5 w-5" }: { className?: string }) {
  // The ladder as the product's mark: four rising steps in the four stage colours.
  return (
    <svg viewBox="0 0 20 20" className={className} aria-hidden>
      <rect x="1" y="13" width="3.6" height="6" rx="1" fill="#cbc3b4" />
      <rect x="5.8" y="9.5" width="3.6" height="9.5" rx="1" fill="#e0bfa0" />
      <rect x="10.6" y="6" width="3.6" height="13" rx="1" fill="#b4c3a3" />
      <rect x="15.4" y="2" width="3.6" height="17" rx="1" fill="#1f3527" />
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

function WorkspacePicker() {
  const { mode, name, org, workspaces: others } = useWorkspace();
  if (mode === "demo" || others.length < 2) {
    return (
      <p className="truncate text-[13px] font-semibold">
        {name}
        {mode === "demo" && <span className="ml-1.5 font-normal text-muted">demo</span>}
      </p>
    );
  }
  return (
    <label className="block">
      <span className="sr-only">Workspace</span>
      <select
        value={org?.id ?? ""}
        onChange={(e) => remember("shadowcost.org", e.target.value)}
        className="h-8 w-full rounded-md border border-control bg-sheet px-2 text-[13px] font-semibold"
      >
        {others.map((w) => (
          <option key={w.id} value={w.id}>
            {w.name}
          </option>
        ))}
      </select>
    </label>
  );
}

function DataPicker() {
  const { mode, dataset, setDataset, datasets, base } = useWorkspace();
  if (mode === "demo") {
    return (
      <div role="radiogroup" aria-label="Data" className="mt-2 grid grid-cols-2 rounded-md bg-[#e2e7ea] p-0.5">
        {datasets.map((d) => (
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
    );
  }
  if (!datasets.length) {
    return (
      <Link href={`${base}/data`} className="mt-2 block text-[13px] font-semibold underline-offset-4 hover:underline">
        Add your data
      </Link>
    );
  }
  return (
    <label className="mt-2 block">
      <span className="sr-only">Dataset</span>
      <select
        value={dataset ?? ""}
        onChange={(e) => setDataset(e.target.value)}
        className="h-8 w-full rounded-md border border-control bg-sheet px-2 text-[13px]"
      >
        {datasets.map((d) => (
          <option key={d.id} value={d.id}>
            {d.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const router = useRouter();
  const { mode, base, approver, setApprover } = useWorkspace();
  const nav = [...SCREENS, ...(mode === "org" ? ORG_SCREENS : [])];

  async function signOut() {
    await supabase().auth.signOut();
    router.replace("/login");
  }

  return (
    <div className="flex h-full flex-col px-3 pb-4 pt-3">
      <Link href="/" className="flex h-10 items-center gap-2.5 px-2 text-[15px] font-semibold" onClick={onNavigate}>
        <Mark />
        ShadowCost
      </Link>

      <div className="mt-4 px-2">
        <WorkspacePicker />
        <DataPicker />
      </div>

      <nav aria-label="App" className="mt-6 space-y-0.5">
        {nav.map((item) => {
          const href = `${base}${item.path}`;
          const active = item.path === "" ? pathname === base : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              className={`flex h-8 items-center gap-2.5 rounded-lg px-2.5 text-[14px] transition-colors duration-150 ${active ? "bg-[#dde3e7] font-semibold text-ink" : "text-[#4f5962] hover:bg-[#e4e9ec] hover:text-ink"}`}
            >
              <Icon d={item.icon} />
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="mt-auto space-y-3 px-2">
        {mode === "demo" ? (
          <>
            <label className="block">
              <span className="text-[12px] text-muted">Approving as</span>
              <input
                value={approver}
                onChange={(e) => setApprover(e.target.value)}
                className="mt-1 h-8 w-full rounded-md border border-control bg-sheet px-2 text-[13px] outline-none focus:border-ink"
              />
            </label>
            <Link href="/signup" className="block rounded-md bg-ink px-3 py-2 text-center text-[13px] font-semibold text-sheet hover:bg-olive">
              Use your own data
            </Link>
          </>
        ) : (
          <div>
            <p className="truncate text-[12px] text-muted">Signed in as</p>
            <p className="truncate text-[13px]">{approver}</p>
            <button onClick={signOut} className="mt-1 text-[13px] text-muted hover:text-ink">
              Sign out
            </button>
          </div>
        )}
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
  const { base, name, mode } = useWorkspace();
  const all = [...SCREENS, ...ORG_SCREENS];
  const current = all.find((n) => (n.path === "" ? pathname === base : pathname.startsWith(`${base}${n.path}`)));

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
        <p className="min-w-0 truncate text-[14px]">
          <span className="text-muted">{name} /</span>{" "}
          <span className="font-semibold">{current?.label ?? "Overview"}</span>
        </p>
        {mode === "demo" && (
          <span className="hidden rounded-full bg-wait-tint px-2.5 py-0.5 text-[12px] font-semibold text-wait sm:inline">
            Demo data
          </span>
        )}
        <div className="ml-auto">
          <Status />
        </div>
      </header>

      <main className="bg-sheet md:mb-2 md:mr-2 md:overflow-y-auto md:rounded-2xl md:border md:border-edge">
        <div key={pathname} className="screen-in mx-auto max-w-[1360px] p-4 md:p-6">
          {children}
        </div>
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
